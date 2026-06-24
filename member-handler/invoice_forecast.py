"""
Forecast Engine — projected full-month invoice for the current, in-progress month.

Implements the Forecast_Invoice capability (Requirements 6-12):
  - Decides whether to produce a forecast for the Current_Month (AWS only).
  - Pulls DAILY unblended cost (excluding Tax) for the elapsed days.
  - Computes a median-based variable projection plus detected fixed-cost
    components from the single most recent closed month.
  - Emits a synthetic Forecast_Invoice record (invoiceId="Forecast-<YYYY-MM>",
    status "Forecast", paymentDate="").

The pure-math functions (median, variable/fixed forecast, rounding, id format,
window predicate) take plain values and are property-testable without AWS.
AWS I/O (Cost Explorer, STS) is isolated in thin fetch wrappers reusing the
established SHA-256 ExternalId assume-role pattern.
"""

import calendar
import hashlib
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import boto3
from botocore.exceptions import ClientError

from ce_account_scope import apply_account_scope

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Module constants ─────────────────────────────────────────────────────────

FORECAST_START_DAY = 4              # forecast window begins on UTC day-of-month 4 (Req 6.2)
RECORD_TYPE_FORECAST = "forecast"
RECORD_TYPE_REAL = "real"
FORECAST_SK_PREFIX = "FCST#"
DEFAULT_ISSUER = "Amazon Web Services"

_MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
_FORECAST_ID_RE = re.compile(r'^Forecast-\d{4}-(0[1-9]|1[0-2])$')


class ForecastError(Exception):
    """Raised when a forecast cannot be computed due to an invalid input
    (for example an unparseable current month)."""
    pass


# ─── Predicates and identifier formatting (pure) ──────────────────────────────

def is_in_forecast_window(now):
    """True iff now (UTC) day-of-month is >= FORECAST_START_DAY and <= last day
    of that month. (Req 6.1, 6.2)"""
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    return FORECAST_START_DAY <= now.day <= days_in_month


def is_aws_provider(provider_key):
    """True iff provider_key.strip().lower() == 'aws'. None/empty/other -> False.
    (Req 11.1-11.3)"""
    if provider_key is None:
        return False
    return str(provider_key).strip().lower() == 'aws'


def forecast_invoice_id(year, month):
    """Build the forecast invoice id 'Forecast-<YYYY-MM>'.

    Raises ForecastError when month is outside 1-12 or year/month are not
    integers. (Req 7.1, 7.2)
    """
    try:
        y = int(year)
        m = int(month)
    except (TypeError, ValueError):
        raise ForecastError(f"Invalid year/month for forecast id: {year!r}-{month!r}")
    if m < 1 or m > 12:
        raise ForecastError(f"Invalid month for forecast id: {month!r}")
    return f"Forecast-{y:04d}-{m:02d}"


# ─── Pure math ────────────────────────────────────────────────────────────────

def median(values):
    """Median of a list: middle value when len is odd, mean of the two middle
    values when even. Empty list -> 0.0. (Req 8.4)"""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def compute_variable_forecast(mtd_cost, median_daily, remaining_days):
    """Variable_Cost_Forecast = mtd + median_daily * remaining_days. (Req 8.2)"""
    return float(mtd_cost) + (float(median_daily) * int(remaining_days))


def compute_fixed_forecast(components, projected_total):
    """Apply each Fixed_Cost_Model to the Current_Month and sum.

    Fixed-amount components contribute their amount; percentage components
    contribute share * projected_total. Empty list -> 0.0. (Req 8.6, 8.7)
    """
    if not components:
        return 0.0
    total = 0.0
    for comp in components:
        model = str(comp.get('model', 'fixed')).lower()
        if model == 'percentage':
            total += float(comp.get('share', 0.0)) * float(projected_total)
        else:
            total += float(comp.get('amount', 0.0))
    return total


def round_half_up_2dp(value):
    """Round to 2 decimal places using ROUND_HALF_UP. Returns a Decimal. (Req 8.9)"""
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def build_forecast_record(current_month, total, issuer, mtd, median_daily,
                          variable, fixed, elapsed_days, remaining_days):
    """Assemble the Forecast_Invoice record dict. (Req 7.1, 7.3, 8.10, 9.5)"""
    year, month = current_month.split('-')

    # Human-readable explanation of how the projection was derived, so the
    # forecast row can surface a populated cost explanation (not blank).
    cost_explanation = (
        f"Projected total for {current_month}. Based on ${float(mtd):,.2f} "
        f"month-to-date over {int(elapsed_days)} day(s), plus a median daily "
        f"run-rate of ${float(median_daily):,.2f} across the {int(remaining_days)} "
        f"remaining day(s). Fixed/recurring: ${float(fixed):,.2f}; "
        f"variable/usage-based: ${float(variable):,.2f}."
    )

    # Actionable guidance for the in-progress month.
    tips = (
        "This is an estimate for the in-progress month and will be replaced by "
        "the final invoice once the month closes. Expand the rows below to see "
        "which services are driving the projected spend and where to optimize."
    )

    return {
        'recordType': RECORD_TYPE_FORECAST,
        'invoiceId': forecast_invoice_id(year, month),
        'issuer': issuer or DEFAULT_ISSUER,
        'paymentDate': '',                       # rendered as em-dash (Req 9.5)
        'paymentStatus': 'Forecast',             # (Req 7.3)
        'totalAmount': float(total),
        'currency': 'USD',                       # (Req 8.10)
        'period': current_month,
        'forecastMonth': current_month,          # staleness check (Req 12.2, 12.3)
        'monthToDateCost': round(float(mtd), 2),
        'medianDailyCost': round(float(median_daily), 4),
        'variableCostForecast': round(float(variable), 2),
        'fixedCostForecast': round(float(fixed), 2),
        'elapsedDays': int(elapsed_days),
        'remainingDays': int(remaining_days),
        'costExplanation': cost_explanation,
        'tips': tips,
        'source': 'forecast_engine',
    }


# ─── Cross-account role assumption ────────────────────────────────────────────

def _assume_role(member_email, account_id):
    """Assume the cross-account SlashMyBill role (same pattern as
    invoice_drilldown._assume_role): ExternalId = SHA-256 of member email."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts = boto3.client('sts')
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SlashMyBillForecast',
        ExternalId=external_id,
    )
    return resp['Credentials']


def _ce_client(creds):
    return boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',
    )


# ─── Cost Explorer fetch wrappers ─────────────────────────────────────────────

def fetch_daily_cost_series(creds, year, month, now, account_id=None):
    """Fetch DAILY UnblendedCost (excluding Tax) for the elapsed days of the
    Current_Month. Returns one float per fully elapsed day. (Req 8.3)

    The CE end date is exclusive, so we request up to today's date which yields
    daily buckets for days strictly before today (fully elapsed days).
    """
    ce = _ce_client(creds)
    start_date = f'{year:04d}-{month:02d}-01'
    end_date = now.strftime('%Y-%m-%d')   # exclusive — yields fully elapsed days only

    if end_date <= start_date:
        return []

    resp = ce.get_cost_and_usage(
        **apply_account_scope({
            'TimePeriod': {'Start': start_date, 'End': end_date},
            'Granularity': 'DAILY',
            'Metrics': ['UnblendedCost'],
            'Filter': {'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Tax']}}},
        }, account_id)
    )

    series = []
    for period in resp.get('ResultsByTime', []):
        amount = float(period.get('Total', {}).get('UnblendedCost', {}).get('Amount', 0))
        series.append(amount)
    return series


def detect_fixed_components(creds, account_id, prev_period):
    """Analyze the single most recent Closed_Month (prev_period, 'YYYY-MM') via
    GetCostAndUsage (SERVICE grouping, exclude Tax). For each service record
    both its absolute amount and its share of that month's total so it can be
    applied as a fixed amount or a percentage. (Req 8.5, 8.7)

    Heuristic: a service is treated as a recurring fixed component when it is a
    flat support/subscription-style charge. Since reliable multi-month history
    is not guaranteed, every detected service is recorded with both an amount
    and a share; the default model is 'fixed' (apply the amount). Returns []
    when the month has no usable total.
    """
    if not _MONTH_RE.match(str(prev_period)):
        return []

    ce = _ce_client(creds)
    year, month = int(prev_period[:4]), int(prev_period[5:7])
    start_date = f'{year:04d}-{month:02d}-01'
    if month == 12:
        end_date = f'{year + 1:04d}-01-01'
    else:
        end_date = f'{year:04d}-{month + 1:02d}-01'

    try:
        resp = ce.get_cost_and_usage(
            **apply_account_scope({
                'TimePeriod': {'Start': start_date, 'End': end_date},
                'Granularity': 'MONTHLY',
                'Metrics': ['UnblendedCost'],
                'GroupBy': [{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
                'Filter': {'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Tax']}}},
            }, account_id)
        )
    except ClientError as e:
        logger.warning(f"Fixed-cost detection failed for {account_id} {prev_period}: {e}")
        return []

    services = {}
    for period in resp.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            name = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            if cost > 0.0:
                services[name] = services.get(name, 0.0) + cost

    month_total = sum(services.values())
    if month_total <= 0.0:
        return []

    components = []
    for name, amount in services.items():
        # Recurring fixed-style charges: support plans and flat subscriptions.
        lowered = name.lower()
        is_fixed = ('support' in lowered) or ('subscription' in lowered)
        if not is_fixed:
            continue
        components.append({
            'service': name,
            'amount': round(amount, 2),
            'share': amount / month_total,
            'model': 'fixed',
        })
    return components


# ─── Orchestration ────────────────────────────────────────────────────────────

def _prev_period(year, month):
    if month == 1:
        return f'{year - 1:04d}-12'
    return f'{year:04d}-{month - 1:02d}'


def compute_forecast(member_email, account_id, provider_key, now=None,
                     default_issuer=DEFAULT_ISSUER, latest_real_issuer=None,
                     creds=None):
    """Produce a Forecast_Invoice record for the Current_Month, or None.

    Returns None (forecast omitted) when, per Requirements 6/8/11:
      - provider_key is not 'aws'                                   (Req 11.1-11.3)
      - now (UTC) is before FORECAST_START_DAY / out of window      (Req 6.2)
      - Month_To_Date_Cost is null/<= 0.00                          (Req 6.4)
      - Elapsed_Days == 0                                           (Req 8.8)
    Raises on Cost Explorer failure so the caller omits and retains the prior
    record (Req 8.11). Raises ForecastError when the month is invalid (Req 7.2).
    """
    now = now or datetime.now(timezone.utc)

    # 1. Provider scope (Req 11)
    if not is_aws_provider(provider_key):
        logger.info(f"Forecast skipped for {account_id}: provider '{provider_key}' is not aws")
        return None

    # 2. Forecast window (Req 6.2)
    if not is_in_forecast_window(now):
        return None

    # 3. Current month + validation (Req 7.2)
    current_month = now.strftime('%Y-%m')
    if not _MONTH_RE.match(current_month):
        raise ForecastError(f"Invalid current month: {current_month}")

    # 4. Fetch daily series (Req 8.3); CE failure propagates (Req 8.11)
    if creds is None:
        creds = _assume_role(member_email, account_id)
    daily = fetch_daily_cost_series(creds, now.year, now.month, now, account_id)

    # 5. Elapsed days (Req 8.8)
    elapsed_days = len(daily)
    if elapsed_days == 0:
        return None

    # 6. Month-to-date cost (Req 6.4)
    mtd = sum(daily)
    if mtd is None or mtd <= 0.0:
        return None

    # 7. Remaining days
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_days = days_in_month - elapsed_days

    # 8. Median + variable forecast (Req 8.2, 8.4)
    median_daily = median(daily)
    variable = compute_variable_forecast(mtd, median_daily, remaining_days)

    # 9. Fixed-cost components from single prior closed month (Req 8.5-8.7)
    prev_period = _prev_period(now.year, now.month)
    try:
        components = detect_fixed_components(creds, account_id, prev_period)
    except Exception as e:
        logger.warning(f"Fixed-cost detection error for {account_id}: {e}")
        components = []
    fixed = compute_fixed_forecast(components, variable)

    # 10. Total composition + rounding (Req 8.1, 8.9)
    total = round_half_up_2dp(variable + fixed)

    # 11. Issuer derivation (Req 9.3, 9.4)
    issuer = latest_real_issuer if latest_real_issuer else default_issuer

    # 12. Build record (Req 7.1)
    return build_forecast_record(
        current_month, total, issuer, mtd, median_daily,
        variable, fixed, elapsed_days, remaining_days,
    )
