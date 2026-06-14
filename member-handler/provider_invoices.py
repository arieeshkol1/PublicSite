"""
Provider Invoices — Synthetic monthly invoice generation for non-AWS providers.

Extends the existing AWS synthetic-monthly-invoice model to Azure, GCP, and the
OpenAI AI vendor. Each connected non-AWS account produces one Synthetic_Monthly_Invoice
per Billing_Period (calendar month) for which a Month_Total is available, using the
identical canonical invoice shape and the identical MemberPortal-Invoices caching scheme
that the AWS path uses.

This module holds the non-AWS generation logic so that invoice_drilldown.py only gains a
thin provider-router branch. It depends only on the provider connector abstraction
(`connectors`), the shared cost normalizer (`cost_normalizer`), and the Python standard
library, keeping it unit-testable in isolation.

AWS behavior is never modified here: AWS accounts continue to flow through the existing
fetch_invoice_list path in invoice_drilldown.py. The AWS current-month forecast also
remains handled by invoice_forecast/invoice_drilldown. This module additionally provides
an OpenAI-specific current-month forecast row (generate_openai_forecast) and an OpenAI
service-level breakdown (generate_openai_service_breakdown), both built in the same shapes
the AWS path uses so the frontend renders them identically.

Failure boundary: generate_provider_invoices converts all connector/credential failures
into an (records, unavailable_flag) tuple so the HTTP list path always stays successful.
Decrypted secrets live only in local variables and are never returned, stored, or logged.
"""

import os
import logging
import calendar
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

import connectors
import cost_normalizer
from connectors.kms_helpers import decrypt_credential

# Forecast helpers are reused to build the OpenAI current-month forecast row in
# the identical shape the AWS forecast uses. The import is best-effort: if the
# module is missing from the deployment package, OpenAI forecasting simply
# degrades to "no forecast row" instead of crashing invoice generation.
try:
    import invoice_forecast
except Exception:  # pragma: no cover
    invoice_forecast = None
from connectors.base_connector import (
    AuthenticationError,
    CostRetrievalError,
    ConnectorError,
)

logger = logging.getLogger()

# Account records live in the same MemberPortal-Accounts table the rest of the
# portal reads from; the env var override mirrors invoice_drilldown.py.
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')

# ─── Shared constants ─────────────────────────────────────────────────────────

# Stored Issuer_Label per Provider_Key. The OpenAI issuer is stored as "OpenAI";
# the user-facing "AI Cost" rename is applied only at the presentation layer
# (members/members.js) and never alters the stored value.
ISSUER_LABELS = {
    'aws': 'Amazon Web Services',
    'azure': 'Microsoft Azure',
    'gcp': 'Google Cloud',
    'openai': 'OpenAI',
}


# ─── Public API (stubs — bodies filled in by later tasks) ──────────────────────

def _is_unusable_cost_data(cost_data):
    """Return True when a connector get_cost_data result carries no usable data.

    Treats a falsy result (``None``, empty list, empty dict) as unusable, and a
    dict carrying a truthy ``error`` field as unusable. A populated dict whose
    ``cost_by_service`` list is empty but whose ``error`` is ``None`` is a
    legitimate zero-cost month and is NOT treated as unusable — it reduces to a
    Month_Total of 0 and is then omitted by the <0.01 threshold.
    """
    if not cost_data:
        return True
    if isinstance(cost_data, dict) and cost_data.get('error'):
        return True
    return False


def generate_provider_invoices(member_email, account_id, provider_key):
    """Return (invoice_records, unavailable_flag) for a non-AWS account.

    invoice_records are dicts in the canonical invoice shape ready for
    _write_invoice_cache. unavailable_flag is True when cost retrieval failed
    (the caller preserves any existing cached rows and returns them).

    This function is the failure boundary: it catches connector/credential
    exceptions internally and converts them into the (records, unavailable)
    tuple so the endpoint stays 200. It never writes to or mutates the account's
    stored ``cloudProvider``/Provider_Key — it only reads the account record (via
    ``_load_credentials``) to obtain credentials.

    Flow:
      1. Resolve the connector. If none is registered, return ``([], True)``.
      2. Load + decrypt credentials and authenticate. Any credential/auth
         failure becomes ``([], True)``.
      3. Walk the 12-month reporting window calling ``get_cost_data`` per month,
         reducing each result to a Month_Total. A ``CostRetrievalError`` or an
         unusable/empty result for one month is skipped and iteration CONTINUES
         so every month that does have usable data (especially the most recent
         months) still produces a row. The provider is reported unavailable only
         when NO month produced a record AND a real retrieval error occurred.
      4. Build a Synthetic_Monthly_Invoice for each period whose Month_Total has
         an absolute value ``>= 0.01``; periods below the threshold are omitted.
    """
    connector = connectors.get_connector(provider_key)
    if connector is None:
        logger.warning(
            f"No connector registered for provider '{provider_key}' "
            f"(account {account_id}); invoice data unavailable"
        )
        return ([], True)

    # Load credentials and authenticate. All credential/auth failures degrade to
    # the unavailable flag — they must never propagate to the HTTP handler.
    try:
        credentials = _load_credentials(member_email, account_id, provider_key)
        auth_context = connector.authenticate(credentials)
    except AuthenticationError as e:
        logger.warning(
            f"Authentication failed for provider '{provider_key}' "
            f"account {account_id}: {e.message}"
        )
        return ([], True)
    except Exception as e:  # credential loading/decryption or unexpected errors
        # Reference only provider + account id; never the credential payload.
        logger.warning(
            f"Credential loading/authentication failed for provider "
            f"'{provider_key}' account {account_id}: {type(e).__name__}"
        )
        return ([], True)

    records = []
    # had_retrieval_error records whether a *real* retrieval failure occurred
    # (a connector exception, or a dict result carrying a truthy 'error'). It is
    # used only to decide the final unavailable flag — it never aborts the loop.
    had_retrieval_error = False

    for month in _reporting_window():
        period = month['period']
        start_date = month['start_date']
        end_date = month['end_date']

        try:
            cost_data = connector.get_cost_data(
                auth_context, account_id, start_date, end_date
            )
        except CostRetrievalError as e:
            # A single month failing must NOT abort the remaining months. OpenAI
            # cost data is typically only available for recent months, so an
            # older month with no data would otherwise prevent the newest months
            # (e.g. last month) from ever being generated. Record the error and
            # continue so every month that DOES have data still produces a row.
            logger.warning(
                f"Cost retrieval failed for provider '{provider_key}' "
                f"account {account_id} period {period}: {e.message}"
            )
            had_retrieval_error = True
            continue
        except Exception as e:
            # Reference only provider/account/period — never the credentials.
            logger.warning(
                f"Unexpected cost-retrieval error for provider '{provider_key}' "
                f"account {account_id} period {period}: {type(e).__name__}"
            )
            had_retrieval_error = True
            continue

        if _is_unusable_cost_data(cost_data):
            # Distinguish a genuine error payload from a legitimately empty
            # month. A dict carrying a truthy 'error' is a real retrieval failure
            # (azure/gcp); a falsy/empty result is simply a month with no data
            # (common for OpenAI in older months) and is skipped without marking
            # the provider unavailable.
            if isinstance(cost_data, dict) and cost_data.get('error'):
                had_retrieval_error = True
            logger.info(
                f"No usable cost data for provider '{provider_key}' "
                f"account {account_id} period {period}; skipping this month"
            )
            continue

        month_total = month_total_from_cost_data(provider_key, cost_data)
        if abs(month_total) >= 0.01:
            records.append(_build_invoice_record(provider_key, period, month_total))

    # Only surface the provider as unavailable when NO month produced a record
    # AND a real retrieval error occurred. An all-empty-but-error-free account
    # stays a clean empty list (not an error), while a genuine outage with no
    # usable months still degrades to unavailable so cached rows are preserved.
    unavailable = (not records) and had_retrieval_error

    return (records, unavailable)


def _is_tax_classified(name):
    """Return True when a service/line-item name is tax-classified.

    An entry is tax-classified when its name, case-folded and trimmed, equals
    "tax" — consistent with the AWS path that filters RECORD_TYPE == 'Tax'.
    """
    if not isinstance(name, str):
        return False
    return name.strip().casefold() == 'tax'


def month_total_from_cost_data(provider_key, cost_data):
    """Reduce a connector get_cost_data result for one month to a USD total.

    - dict shape (azure/gcp): sum cost_usd over cost_by_service entries,
      skipping any entry whose service name is tax-classified.
    - list shape (openai): normalize via cost_normalizer.normalize_openai, sum
      cost_amount, excluding any tax-classified records.

    Returns a float rounded to 2 decimals.
    """
    total = 0.0

    if isinstance(cost_data, dict):
        # Azure/GCP shape: {'cost_by_service': [{'service', 'cost_usd'}], ...}
        for entry in cost_data.get('cost_by_service', []) or []:
            if not isinstance(entry, dict):
                continue
            if _is_tax_classified(entry.get('service')):
                continue
            try:
                total += float(entry.get('cost_usd', 0) or 0)
            except (TypeError, ValueError):
                continue
    elif isinstance(cost_data, list):
        # OpenAI shape: raw bucket list normalized into the common schema.
        # account_id is provenance-only metadata for aggregation, so a
        # placeholder is sufficient here.
        normalized = cost_normalizer.normalize_openai(cost_data, '')
        for record in normalized:
            if _is_tax_classified(record.get('service_name')):
                continue
            try:
                total += float(record.get('cost_amount', 0) or 0)
            except (TypeError, ValueError):
                continue

    return round(total, 2)


class MonthlyCostAggregator:
    """Pure reducer that turns connector cost data into a single USD Month_Total
    per Billing_Period, excluding tax-classified amounts.

    Bodies are filled in by later tasks (task 3); this stub establishes the
    public surface so dependent modules can import it.
    """

    def __init__(self):
        raise NotImplementedError("MonthlyCostAggregator is implemented in task 3.1")


def _reporting_window(now=None):
    """Build the reporting window of 12 calendar months ending with the current
    (in-progress) month.

    The window mirrors the AWS Cost Explorer fallback window: it spans the 12
    calendar months whose newest period is the current month. For each
    Billing_Period it emits the per-month connector request range — the
    start_date is the first day of the period and the end_date is the first day
    of the following period — so the union of the ranges covers exactly the 12
    reporting months.

    Args:
        now: Optional reference datetime treated as "now". Defaults to the
            current UTC time. Accepting it keeps the helper pure and testable
            across arbitrary current dates.

    Returns:
        A list of 12 dicts ordered oldest-first, each shaped:
            {'period': 'YYYY-MM', 'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD'}
        where start_date is the first day of the period and end_date is the
        first day of the immediately following month.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Month index of the current (newest) period, counted in absolute months.
    current_index = now.year * 12 + (now.month - 1)

    window = []
    # Walk from 11 months ago up to the current month so the result is
    # ordered oldest-first and ends with the in-progress month.
    for offset in range(11, -1, -1):
        index = current_index - offset
        year, month = divmod(index, 12)
        month += 1  # divmod yields a 0-based month; shift to 1-based

        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        window.append({
            'period': f'{year:04d}-{month:02d}',
            'start_date': f'{year:04d}-{month:02d}-01',
            'end_date': f'{next_year:04d}-{next_month:02d}-01',
        })

    return window


def _build_invoice_record(provider_key, period, month_total):
    """Produce the canonical Synthetic_Monthly_Invoice dict consumed by the cache
    writer and the response shaper.

    Fields: invoiceId, issuer, paymentDate, paymentStatus, totalAmount, currency,
    period, plus a source provenance tag.

    Args:
        provider_key: Internal Provider_Key ('aws', 'azure', 'gcp', 'openai').
        period: Billing_Period as a 'YYYY-MM' string.
        month_total: Month_Total for the period (numeric, may be unrounded).

    The paymentDate is the 15th day of the calendar month immediately following
    the period, in 'YYYY-MM-DD' format, rolling the year forward when the period
    is December — identical to the existing AWS synthetic invoice model.
    """
    year_val, month_val = int(period[:4]), int(period[5:7])
    if month_val == 12:
        pay_year, pay_month = year_val + 1, 1
    else:
        pay_year, pay_month = year_val, month_val + 1
    payment_date = f'{pay_year}-{pay_month:02d}-15'

    record = {
        'invoiceId': f'{period}-monthly',
        'issuer': ISSUER_LABELS[provider_key],
        'paymentDate': payment_date,
        'paymentStatus': 'paid',
        'totalAmount': round(month_total, 2),
        'currency': 'USD',
        'period': period,
        'source': f'{provider_key}_connector',
    }

    # Honest tax disclosure (scoped to OpenAI). The OpenAI Organization Costs API
    # returns pre-tax USAGE charges only — it exposes no tax line item and no
    # taxed invoice total via API (unlike AWS Cost Explorer, which has a queryable
    # RECORD_TYPE='Tax'). Surface that explicitly so this "paid" total is not
    # mistaken for the taxed amount OpenAI actually billed on the receipt.
    if provider_key == 'openai':
        record['costExplanation'] = (
            'Total reflects OpenAI usage charges only and excludes any sales '
            'tax/VAT. OpenAI does not expose tax or final invoice amounts via '
            'API, so the taxed total on your OpenAI receipt may be higher.'
        )

    return record


def _load_credentials(member_email, account_id, provider_key):
    """Read the account record from MemberPortal-Accounts and build the
    provider-specific credentials dict expected by each connector's authenticate.

    Mirrors the credential-loading conventions already used in
    lambda_function.py / provider_router.py:

      - azure: ``{tenant_id, client_id, client_secret}`` where ``client_secret``
        is the decrypted ``encryptedClientSecret`` (decrypt_credential).
      - gcp:   ``{client_email, private_key, project_id}`` where ``private_key``
        is the decrypted ``encryptedPrivateKey`` (the service-account private
        key, decrypt_credential).
      - openai: ``{encrypted_api_key, member_email, account_id, org_name}`` —
        the OpenAI connector itself decrypts the key with KMS, supplying
        ``{memberEmail, accountId}`` as the encryption context.

    Encryption-context rule (Req 6.2): wherever a connector or helper decrypts
    with KMS it is given ``{memberEmail, accountId}`` as the encryption context.
    For OpenAI this is delegated to ``decrypt_openai_key`` inside the connector
    (which is why ``member_email``/``account_id`` are passed through here); for
    Azure/GCP the existing ``decrypt_credential`` path is used as-is.

    Secret-safety rule (Req 6.3): decrypted secrets live only in local variables
    that are handed straight to ``authenticate``. They are never returned to the
    caller's invoice records, written to storage, or logged. Failure logs
    reference only the provider and account id.

    Args:
        member_email: The authenticated member's email (Accounts partition key).
        account_id: The Selected_Account's id (Accounts sort key).
        provider_key: Internal Provider_Key ('azure', 'gcp', or 'openai').

    Returns:
        A credentials dict ready to pass to the provider connector's
        ``authenticate``.

    Raises:
        ValueError: If ``provider_key`` is not a supported non-AWS provider.
        RuntimeError: If the account record is missing, the account read fails,
            or the required encrypted credential field is absent. The message
            never contains a plaintext secret.
    """
    accounts_table = boto3.resource('dynamodb').Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.get_item(
            Key={'memberEmail': member_email, 'accountId': account_id}
        )
    except ClientError as e:
        # Log provider + account only; never the credential payload.
        logger.error(
            f"Account read failed loading {provider_key} credentials for {account_id}: {e}"
        )
        raise RuntimeError("Unable to read account record for credential loading.")

    account = result.get('Item')
    if not account:
        logger.warning(
            f"No account record found loading {provider_key} credentials for {account_id}"
        )
        raise RuntimeError("Account record not found for credential loading.")

    stored = account.get('credentials', {}) or {}

    if provider_key == 'azure':
        encrypted_secret = stored.get('encryptedClientSecret', '')
        if not encrypted_secret:
            logger.warning(f"Azure account {account_id} has no stored client secret")
            raise RuntimeError("Azure credentials are not available for this account.")
        # Decrypted secret stays a local variable handed to authenticate.
        client_secret = decrypt_credential(encrypted_secret)
        return {
            'tenant_id': stored.get('tenantId', ''),
            'client_id': stored.get('clientId', ''),
            'client_secret': client_secret,
        }

    if provider_key == 'gcp':
        encrypted_private_key = stored.get('encryptedPrivateKey', '')
        if not encrypted_private_key:
            logger.warning(f"GCP account {account_id} has no stored private key")
            raise RuntimeError("GCP credentials are not available for this account.")
        # Decrypted service-account private key stays a local variable.
        private_key = decrypt_credential(encrypted_private_key)
        return {
            'client_email': stored.get('clientEmail', ''),
            'private_key': private_key,
            'project_id': stored.get('projectId', ''),
        }

    if provider_key == 'openai':
        encrypted_api_key = stored.get('encryptedApiKey', '')
        if not encrypted_api_key:
            logger.warning(f"OpenAI account {account_id} has no stored API key")
            raise RuntimeError("OpenAI credentials are not available for this account.")
        # The OpenAI connector decrypts with the {memberEmail, accountId}
        # encryption context, so we only pass the still-encrypted key through.
        return {
            'encrypted_api_key': encrypted_api_key,
            'member_email': member_email,
            'account_id': account_id,
            'org_name': account.get('accountName', '') or '',
        }

    raise ValueError(f"Unsupported provider for credential loading: {provider_key}")


# ─── OpenAI current-month forecast ────────────────────────────────────────────

def generate_openai_forecast(member_email, account_id, now=None):
    """Build a Current_Month forecast invoice row for an OpenAI account, or None.

    Mirrors the AWS forecast record shape (invoice_forecast.build_forecast_record)
    so the frontend renders it identically: recordType 'forecast', paymentStatus
    'Forecast', invoiceId 'Forecast-YYYY-MM', period = current month, empty
    paymentDate. The projection is the simple, robust month-to-date run-rate:

        projected_total = (month_to_date / days_elapsed) * days_in_month

    Returns None (no forecast row) when the forecast module is unavailable, the
    current date is outside the forecast window, credentials/cost retrieval fail,
    or there is no usable month-to-date spend. This function never raises — the
    forecast is an additive, best-effort capability and must never break the
    invoice list response. Decrypted secrets stay inside the connector and are
    never logged.
    """
    if invoice_forecast is None:
        return None

    now = now or datetime.now(timezone.utc)

    # Only emit a forecast inside the same window the AWS path uses (Req 6).
    if not invoice_forecast.is_in_forecast_window(now):
        return None

    connector = connectors.get_connector('openai')
    if connector is None:
        return None

    current_month = now.strftime('%Y-%m')
    start_date = f'{now.year:04d}-{now.month:02d}-01'
    # Month-to-date through today. The OpenAI connector treats the range as a
    # cost window, so passing today's date yields the elapsed days' usage.
    end_date = now.strftime('%Y-%m-%d')

    try:
        credentials = _load_credentials(member_email, account_id, 'openai')
        auth_context = connector.authenticate(credentials)
        cost_data = connector.get_cost_data(
            auth_context, account_id, start_date, end_date
        )
    except Exception as e:  # auth/credential/retrieval failure — degrade silently
        logger.warning(
            f"OpenAI forecast cost retrieval failed for account {account_id}: "
            f"{type(e).__name__}"
        )
        return None

    if _is_unusable_cost_data(cost_data):
        return None

    # Month-to-date total (exclude tax-classified line items), reusing the same
    # normalizer the invoice total uses for consistency.
    mtd = 0.0
    for record in cost_normalizer.normalize_openai(cost_data, account_id):
        if _is_tax_classified(record.get('service_name')):
            continue
        try:
            mtd += float(record.get('cost_amount', 0) or 0)
        except (TypeError, ValueError):
            continue

    if mtd <= 0.0:
        return None

    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = now.day
    if days_elapsed <= 0:
        return None

    daily_rate = mtd / days_elapsed
    projected = daily_rate * days_in_month
    remaining_days = days_in_month - days_elapsed
    total = invoice_forecast.round_half_up_2dp(projected)

    # OpenAI has no detected fixed-cost components, so the whole projection is
    # variable; pass the average daily run-rate as the "median daily" figure so
    # the shared explanation text reads sensibly.
    return invoice_forecast.build_forecast_record(
        current_month, total, ISSUER_LABELS['openai'], mtd, daily_rate,
        projected, 0.0, days_elapsed, remaining_days,
    )


# ─── OpenAI service-level breakdown ───────────────────────────────────────────

def generate_openai_service_breakdown(member_email, account_id, period):
    """Build a service-level breakdown for an OpenAI account + period, or [].

    Each "service" row is an OpenAI model / line-item, in the same shape the AWS
    service breakdown returns (serviceName, amount, percentage, usageTypes,
    costExplanation) so the frontend renders it identically. Costs are grouped
    by model/line-item from the connector's get_cost_data result (normalized via
    cost_normalizer.normalize_openai), summing cost_amount and excluding any
    tax-classified entries.

    Returns [] on any auth/credential/retrieval failure or when there is no
    usable cost data. Never raises — a failed breakdown must not break the
    drill-down response. Decrypted secrets stay inside the connector.
    """
    connector = connectors.get_connector('openai')
    if connector is None:
        return []

    year_val, month_val = int(period[:4]), int(period[5:7])
    start_date = f'{year_val:04d}-{month_val:02d}-01'
    if month_val == 12:
        end_date = f'{year_val + 1:04d}-01-01'
    else:
        end_date = f'{year_val:04d}-{month_val + 1:02d}-01'

    try:
        credentials = _load_credentials(member_email, account_id, 'openai')
        auth_context = connector.authenticate(credentials)
        cost_data = connector.get_cost_data(
            auth_context, account_id, start_date, end_date
        )
    except Exception as e:
        logger.warning(
            f"OpenAI service breakdown unavailable for account {account_id} "
            f"period {period}: {type(e).__name__}"
        )
        return []

    if _is_unusable_cost_data(cost_data):
        return []

    # Group normalized records by model/line-item, summing cost and tokens.
    grouped = {}
    for record in cost_normalizer.normalize_openai(cost_data, account_id):
        name = record.get('service_name', 'unknown')
        if _is_tax_classified(name):
            continue
        try:
            cost = float(record.get('cost_amount', 0) or 0)
        except (TypeError, ValueError):
            cost = 0.0
        entry = grouped.setdefault(
            name, {'cost': 0.0, 'input_tokens': 0, 'output_tokens': 0}
        )
        entry['cost'] += cost
        try:
            entry['input_tokens'] += int(record.get('input_tokens', 0) or 0)
            entry['output_tokens'] += int(record.get('output_tokens', 0) or 0)
        except (TypeError, ValueError):
            pass

    total = sum(e['cost'] for e in grouped.values())

    rows = []
    for name, entry in grouped.items():
        amount = round(entry['cost'], 2)
        # Mirror the AWS path's per-service $0.01 floor so zero/near-zero
        # (e.g. token-only) line items do not clutter the breakdown.
        if abs(amount) < 0.01:
            continue
        percentage = round((entry['cost'] / total) * 100, 1) if total > 0 else 0.0

        # Surface token usage as usageTypes entries in the AWS shape
        # (type/cost/unit/quantity). Per-token cost is not separable, so cost 0.
        usage_types = []
        if entry['input_tokens']:
            usage_types.append({
                'type': 'Input tokens', 'cost': 0.0,
                'unit': 'tokens', 'quantity': entry['input_tokens'],
            })
        if entry['output_tokens']:
            usage_types.append({
                'type': 'Output tokens', 'cost': 0.0,
                'unit': 'tokens', 'quantity': entry['output_tokens'],
            })

        if entry['input_tokens'] or entry['output_tokens']:
            cost_explanation = (
                f"{name}: ${amount:,.2f} across {entry['input_tokens']:,} input "
                f"and {entry['output_tokens']:,} output tokens for {period}."
            )
        else:
            cost_explanation = f"{name}: ${amount:,.2f} in usage for {period}."

        rows.append({
            'serviceName': name,
            'amount': amount,
            'percentage': percentage,
            'costExplanation': cost_explanation,
            'usageTypes': usage_types,
        })

    rows.sort(key=lambda x: x['amount'], reverse=True)
    return rows
