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
fetch_invoice_list path in invoice_drilldown.py. Forecasting remains AWS-only — this
module never emits a forecast row.

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
         unusable result aborts further fetches and sets ``unavailable=True``,
         while already-computed months are still returned.
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
    unavailable = False

    for month in _reporting_window():
        period = month['period']
        start_date = month['start_date']
        end_date = month['end_date']

        try:
            cost_data = connector.get_cost_data(
                auth_context, account_id, start_date, end_date
            )
        except CostRetrievalError as e:
            logger.warning(
                f"Cost retrieval failed for provider '{provider_key}' "
                f"account {account_id} period {period}: {e.message}"
            )
            unavailable = True
            break
        except Exception as e:
            logger.warning(
                f"Unexpected cost-retrieval error for provider '{provider_key}' "
                f"account {account_id} period {period}: {type(e).__name__}"
            )
            unavailable = True
            break

        if _is_unusable_cost_data(cost_data):
            logger.info(
                f"No usable cost data for provider '{provider_key}' "
                f"account {account_id} period {period}; aborting further fetches"
            )
            unavailable = True
            break

        month_total = month_total_from_cost_data(provider_key, cost_data)
        if abs(month_total) >= 0.01:
            records.append(_build_invoice_record(provider_key, period, month_total))

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

    return {
        'invoiceId': f'{period}-monthly',
        'issuer': ISSUER_LABELS[provider_key],
        'paymentDate': payment_date,
        'paymentStatus': 'paid',
        'totalAmount': round(month_total, 2),
        'currency': 'USD',
        'period': period,
        'source': f'{provider_key}_connector',
    }


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
