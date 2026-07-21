"""
Invoice Drilldown — Three-Level Hierarchical Invoice Data Service.

Provides handlers for the invoice drill-down endpoints:
  - Invoice list (Level 1): Invoice metadata from AWS Invoicing API
  - Service breakdown (Level 2): Service-level costs from Cost Explorer
  - Resource breakdown (Level 3): Resource-level costs with metadata enrichment
  - Refresh: Force re-sync all levels for an account+period

Uses the existing SlashMyBill-{AccountID} cross-account role pattern
for accessing customer AWS accounts. Integrates Amazon Bedrock (Nova Lite)
for AI-powered cost explanations at the resource level.
"""

import json
import os
import re
import time
import logging
import math
import hashlib
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ce_account_scope import apply_account_scope

# Forecast is an additive, best-effort capability. If the module is missing
# from the deployment package, invoice endpoints must still work — so the
# import never crashes the module load. (forecast simply disabled when None)
try:
    import invoice_forecast
except Exception as _forecast_import_err:  # pragma: no cover
    invoice_forecast = None
    logging.getLogger().warning(
        f"invoice_forecast unavailable; forecasts disabled: {_forecast_import_err}"
    )

# Provider router for non-AWS invoice generation. Additive and best-effort: if
# the module is missing from the deployment package, the import must not crash
# the module load — non-AWS generation simply degrades to "unavailable".
try:
    from provider_invoices import (
        generate_provider_invoices,
        generate_openai_forecast,
        generate_openai_service_breakdown,
    )
except Exception as _provider_invoices_import_err:  # pragma: no cover
    generate_provider_invoices = None
    generate_openai_forecast = None
    generate_openai_service_breakdown = None
    logging.getLogger().warning(
        "provider_invoices unavailable; non-AWS invoice generation disabled: "
        f"{_provider_invoices_import_err}"
    )

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Module-level constants ───────────────────────────────────────────────────

INVOICES_TABLE_NAME = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-opus-4-0-20250514-v1:0')

# TTL: 90 days in seconds
TTL_SECONDS = 7776000

# Refresh cooldown: 5 minutes in seconds
REFRESH_COOLDOWN = 300

# AI explanation cost threshold — only generate for resources above this amount
AI_COST_THRESHOLD = 1.00

# Bedrock AI call timeout in seconds
AI_TIMEOUT = 15

# Resource metadata enrichment timeout in seconds
RESOURCE_TIMEOUT = 10

# AWS clients
dynamodb = boto3.resource('dynamodb')

# Validation constants
ACCOUNT_ID_REGEX = re.compile(r'^\d{12}$')
# Non-AWS providers (azure/gcp/openai) use their own identifier formats —
# Azure subscription/tenant UUIDs, GCP project IDs, OpenAI org/account IDs —
# which are not 12-digit AWS account numbers. This bounded, permissive pattern
# is input hygiene only; account ownership verification is the real security
# gate.
NON_AWS_ACCOUNT_ID_REGEX = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$')
PERIOD_REGEX = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
VALID_SORT_BY = ['paymentDate', 'amount', 'status', 'cost', 'date', 'service']
VALID_SORT_ORDER = ['asc', 'desc']
# Alias mapping: frontend may send 'cost'/'date'/'service' from the main invoice view
SORT_BY_ALIASES = {'cost': 'amount', 'date': 'paymentDate', 'service': 'paymentDate'}
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# Provider-specific account ID format validation patterns.
# Used by validate_account_id_format() to verify parsed account IDs before
# acceptance. Each provider has distinct identifier formats.
PROVIDER_ACCOUNT_ID_PATTERNS = {
    'aws': re.compile(r'^\d{12}$'),
    'azure': re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ),
    'gcp': re.compile(r'^[a-z][a-z0-9\-]{4,28}[a-z0-9]$'),
    'openai': re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$'),
}


# ─── Response helpers ─────────────────────────────────────────────────────────

def _cors_headers():
    """Return CORS headers for member API responses."""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    }


def create_response(status_code, body):
    """Return an API Gateway v2 response dict with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': _cors_headers(),
        'body': json.dumps(body),
    }


def create_error_response(status_code, error_type, message, extra=None):
    """Return an error response following the existing Lambda pattern."""
    body = {
        'error': error_type,
        'message': message,
        'code': status_code,
    }
    if extra:
        body.update(extra)
    return {
        'statusCode': status_code,
        'headers': _cors_headers(),
        'body': json.dumps(body),
    }


# ─── Input validation utilities ───────────────────────────────────────────────

def validate_account_id(account_id):
    """Validate that account_id is exactly 12 digits.

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if not account_id:
        return ('ValidationError', 'Account ID is required')
    if not ACCOUNT_ID_REGEX.match(str(account_id)):
        return ('ValidationError', 'Account ID must be exactly 12 digits')
    return None


def validate_account_id_for_provider(account_id, provider_key):
    """Validate account_id using a provider-appropriate format.

    AWS accounts keep the strict 12-digit rule (unchanged behaviour and error
    message). Non-AWS providers (azure/gcp/openai) use a bounded permissive
    identifier format because their account identifiers are UUIDs, project IDs,
    or organisation IDs rather than 12-digit AWS account numbers. An absent or
    empty provider defaults to 'aws'.

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if not account_id:
        return ('ValidationError', 'Account ID is required')
    if str(provider_key or 'aws').strip().lower() == 'aws':
        if not ACCOUNT_ID_REGEX.match(str(account_id)):
            return ('ValidationError', 'Account ID must be exactly 12 digits')
        return None
    if not NON_AWS_ACCOUNT_ID_REGEX.match(str(account_id)):
        return ('ValidationError', 'Account ID format is invalid for this provider')
    return None


def validate_period(period):
    """Validate that period is in YYYY-MM format with valid month (01-12).

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if not period:
        return ('ValidationError', 'Period is required')
    if not PERIOD_REGEX.match(str(period)):
        return ('ValidationError', 'Period must be in YYYY-MM format with a valid month (01-12)')
    return None


def validate_service(service):
    """Validate that service is a non-empty string.

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if not service or not str(service).strip():
        return ('ValidationError', 'Service name is required and must be non-empty')
    return None


def validate_pagination(page, page_size):
    """Validate pagination parameters.

    Args:
        page: Page number (must be >= 1).
        page_size: Items per page (must be 1-100, defaults to 25).

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if page is not None:
        try:
            page_int = int(page)
        except (ValueError, TypeError):
            return ('ValidationError', 'Page must be a positive integer')
        if page_int < 1:
            return ('ValidationError', 'Page must be >= 1')

    if page_size is not None:
        try:
            page_size_int = int(page_size)
        except (ValueError, TypeError):
            return ('ValidationError', 'Page size must be a positive integer')
        if page_size_int < 1 or page_size_int > MAX_PAGE_SIZE:
            return ('ValidationError', f'Page size must be between 1 and {MAX_PAGE_SIZE}')

    return None


def validate_sort(sort_by, sort_order):
    """Validate sort parameters.

    Args:
        sort_by: Sort field (must be one of paymentDate, amount, status).
        sort_order: Sort direction (must be one of asc, desc).

    Returns:
        None on success, or a tuple (error_code, message) on failure.
    """
    if sort_by is not None and sort_by not in VALID_SORT_BY:
        return ('ValidationError', f'sortBy must be one of: {", ".join(VALID_SORT_BY)}')
    if sort_order is not None and sort_order not in VALID_SORT_ORDER:
        return ('ValidationError', f'sortOrder must be one of: {", ".join(VALID_SORT_ORDER)}')
    return None


# ─── Account ID resolution utilities ─────────────────────────────────────────

def validate_account_id_format(account_id, provider_key='aws'):
    """Validate that an account_id matches the expected format for the provider.

    Uses PROVIDER_ACCOUNT_ID_PATTERNS for provider-specific format validation.
    Unknown providers use the permissive NON_AWS_ACCOUNT_ID_REGEX.

    Args:
        account_id: The value to validate.
        provider_key: The provider type (e.g., 'aws', 'azure', 'gcp', 'openai').

    Returns:
        True if the format is valid, False otherwise.
    """
    if not account_id or not str(account_id).strip():
        return False
    account_id_str = str(account_id).strip()
    provider = str(provider_key or 'aws').strip().lower()
    pattern = PROVIDER_ACCOUNT_ID_PATTERNS.get(provider, NON_AWS_ACCOUNT_ID_REGEX)
    return bool(pattern.match(account_id_str))


def resolve_account_id(parsed_account_id, account_metadata_id, provider_key='aws'):
    """Resolve the Account ID for an invoice record.

    Priority:
        1. parsed_account_id (if non-empty, not "N/A", and passes format validation)
        2. account_metadata_id (if non-empty and not "N/A")
        3. "N/A" as final fallback

    Args:
        parsed_account_id: Value extracted by the bill parser (may be None, "N/A", or empty).
        account_metadata_id: Value from the accounts table.
        provider_key: Provider identifier for format validation.

    Returns:
        Resolved Account ID string.
    """
    # Try parsed value first
    parsed = str(parsed_account_id or '').strip()
    if parsed and parsed.upper() != 'N/A':
        if validate_account_id_format(parsed, provider_key):
            return parsed
        else:
            logger.warning(
                f"Parsed account ID failed format validation: value='{parsed}', "
                f"provider='{provider_key}', expected pattern="
                f"'{PROVIDER_ACCOUNT_ID_PATTERNS.get(str(provider_key or 'aws').strip().lower(), NON_AWS_ACCOUNT_ID_REGEX).pattern}'"
            )

    # Fallback to metadata value
    metadata = str(account_metadata_id or '').strip()
    if metadata and metadata.upper() != 'N/A':
        return metadata

    # Final fallback
    return 'N/A'


def aggregate_by_account(invoice_items):
    """Aggregate invoice line items by Account ID.

    For each distinct accountId, computes:
        - totalCost: sum of all line item costs for that account
        - serviceCount: number of distinct services with charges > 0
        - accountId: the account identifier
        - currency: currency code (from first record per account, default "USD")

    Results are sorted by totalCost descending.

    Args:
        invoice_items: List of invoice record dicts, each with 'accountId',
                       'totalAmount'/'amount', and optionally 'serviceName' fields.

    Returns:
        List of aggregation dicts sorted by totalCost descending.
    """
    account_data = {}
    for item in invoice_items:
        acct_id = item.get('accountId', 'N/A') or 'N/A'
        if acct_id not in account_data:
            account_data[acct_id] = {
                'totalCost': 0.0,
                'services': set(),
                'currency': item.get('currency', 'USD'),
            }
        amount = float(item.get('totalAmount', item.get('amount', 0)) or 0)
        account_data[acct_id]['totalCost'] += amount
        service_name = item.get('serviceName', '') or ''
        if service_name and amount > 0:
            account_data[acct_id]['services'].add(service_name)

    results = []
    for acct_id, data in account_data.items():
        results.append({
            'accountId': acct_id,
            'totalCost': round(data['totalCost'], 2),
            'serviceCount': len(data['services']),
            'currency': data['currency'],
        })

    results.sort(key=lambda x: x['totalCost'], reverse=True)
    return results


# ─── Account ownership verification ──────────────────────────────────────────

def _verify_account_ownership(member_email, account_id):
    """Verify that the given account ID belongs to the authenticated member.

    Queries MemberPortal-Accounts table to confirm accountId belongs to
    the authenticated member.

    Args:
        member_email: The authenticated member's email address.
        account_id: The AWS account ID to verify ownership of.

    Returns:
        True if the account is owned by the member, or an error response
        dict (403) if not.
    """
    if not account_id:
        return create_error_response(400, 'ValidationError', 'Account ID is required')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email),
            ProjectionExpression='accountId',
        )
        owned_ids = {item['accountId'] for item in result.get('Items', [])}
    except ClientError as e:
        logger.error(f"Failed to verify account ownership: {e}")
        return create_error_response(500, 'ServerError', 'Failed to verify account ownership')

    if account_id not in owned_ids:
        logger.warning(f"Lateral access attempt: {member_email} tried to access account {account_id}")
        return create_error_response(403, 'AccessDenied', f'Account {account_id} does not belong to you')

    return True


# ─── Helper: extract query params ────────────────────────────────────────────

def _get_query_params(event):
    """Extract query string parameters from the API Gateway event."""
    return event.get('queryStringParameters') or {}


# ─── Handler functions (API route delegates) ──────────────────────────────────

def handle_invoice_list_request(event, member_email):
    """
    Handle GET /members/invoices/list.

    Returns a paginated list of invoice-level records for the specified
    account. Checks DynamoDB cache first; on cache miss, fetches from
    AWS Invoicing API (with Cost Explorer fallback) and stores results.

    Query params: accountId (required), page, pageSize, sortBy, sortOrder.
    """
    params = _get_query_params(event)

    # Extract and validate inputs
    account_id = params.get('accountId')
    page = params.get('page', '1')
    page_size = params.get('pageSize', str(DEFAULT_PAGE_SIZE))
    sort_by = params.get('sortBy')
    sort_order = params.get('sortOrder')
    group_by_account = params.get('groupByAccount', 'false')

    # Validate accountId presence
    if not account_id:
        return create_error_response(400, 'ValidationError', 'Account ID is required')

    # Resolve the account's provider early so account-id validation can be
    # provider-aware: AWS keeps the strict 12-digit rule; non-AWS providers
    # (azure/gcp/openai) use their own identifier formats. Absent/empty -> 'aws'.
    provider_key = _get_account_provider(member_email, account_id) or 'aws'

    # Validate accountId format per provider
    validation_error = validate_account_id_for_provider(account_id, provider_key)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate pagination
    validation_error = validate_pagination(page, page_size)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate sort
    validation_error = validate_sort(sort_by, sort_order)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Verify account ownership
    ownership = _verify_account_ownership(member_email, account_id)
    if ownership is not True:
        return ownership

    # Parse validated pagination values
    page_int = int(page)
    page_size_int = int(page_size)

    # provider_key resolved above (used for both the generation branch below
    # and the AWS-only forecast merge further down).

    # invoiceDataUnavailable surfaces a non-AWS provider cost-retrieval failure
    # to the client alongside the existing forecast flags. It stays False for
    # the AWS path and on cache hits (Req 6.4, 7.2).
    invoice_data_unavailable = False

    # Task 4.1: Check DynamoDB cache first
    cached_records = _read_invoice_cache(member_email, account_id)

    if cached_records:
        items = cached_records
    else:
        # Cache miss — branch on provider. AWS keeps its existing path
        # unchanged; every other provider routes through the additive
        # generate_provider_invoices generator (Req 1.1-1.3, 4.1).
        if provider_key == 'aws':
            # Task 4.2/4.4: Cache miss — fetch from AWS APIs
            try:
                items = fetch_invoice_list(member_email, account_id)
                logger.info(f"Invoice drilldown: fetched {len(items)} invoices for {account_id}")
            except Exception as e:
                logger.error(f"Failed to fetch invoice list for {account_id}: {type(e).__name__}: {e}")
                return create_error_response(502, 'FetchError', f'Failed to retrieve invoice data: {str(e)}')
        else:
            # Non-AWS providers (azure/gcp/openai). generate_provider_invoices is
            # the failure boundary: it never raises for provider failures, instead
            # returning ([], True). On failure we preserve any cached rows (already
            # empty here) and surface the unavailable indication, keeping the
            # response 200 (Req 5.1-5.5, 6.4, 7.1, 7.2, 7.4, 8.2).
            if generate_provider_invoices is None:
                items = []
                invoice_data_unavailable = True
                logger.warning(
                    "provider_invoices module unavailable; cannot generate "
                    f"invoices for {account_id} provider={provider_key}"
                )
            else:
                items, invoice_data_unavailable = generate_provider_invoices(
                    member_email, account_id, provider_key)
                logger.info(
                    f"Invoice drilldown: generated {len(items)} invoices for "
                    f"{account_id} provider={provider_key} unavailable={invoice_data_unavailable}"
                )

        # Task 4.3: Store fetched/generated records in cache. A failing provider
        # fetch returns no records, so nothing is written and no cached rows are
        # overwritten (Req 5.1-5.3, 7.3).
        if items:
            _write_invoice_cache(member_email, account_id, items)

    # groupByAccount: when "true", aggregate invoices by account and return
    # per-account totals instead of individual invoice records.
    if str(group_by_account).strip().lower() == 'true':
        aggregated = aggregate_by_account(items)
        # Paginate aggregated results
        total_items = len(aggregated)
        total_pages = math.ceil(total_items / page_size_int) if total_items > 0 else 0
        start_idx = (page_int - 1) * page_size_int
        end_idx = start_idx + page_size_int
        page_items = aggregated[start_idx:end_idx]
        return create_response(200, {
            'items': page_items,
            'pagination': {
                'page': page_int,
                'pageSize': page_size_int,
                'totalItems': total_items,
                'totalPages': total_pages,
            }
        })

    # Apply sorting (default: paymentDate desc)
    effective_sort_by = sort_by or 'paymentDate'
    effective_sort_order = sort_order or 'desc'
    # Resolve aliases (cost->amount, date->paymentDate, service->paymentDate)
    effective_sort_by = SORT_BY_ALIASES.get(effective_sort_by, effective_sort_by)

    sort_key_map = {
        'paymentDate': lambda x: x.get('paymentDate', ''),
        'amount': lambda x: float(x.get('totalAmount', 0)),
        'status': lambda x: x.get('paymentStatus', ''),
    }
    sort_fn = sort_key_map.get(effective_sort_by, sort_key_map['paymentDate'])
    items = sorted(items, key=sort_fn, reverse=(effective_sort_order == 'desc'))

    # Forecast merge/supersede: compute or retrieve the Current_Month forecast
    # for AWS accounts and place it at the top, ahead of all real invoices
    # (Req 9.1, 9.6). Any failure leaves the real-invoice list intact (Req 8.11).
    forecast_unavailable = False
    forecast_diag = {'status': 'none', 'reason': 'not_evaluated'}
    try:
        now_utc = datetime.now(timezone.utc)
        forecast_diag['provider'] = provider_key
        forecast_diag['currentMonth'] = now_utc.strftime('%Y-%m')
        forecast_diag['inWindow'] = (invoice_forecast is not None
                                     and invoice_forecast.is_in_forecast_window(now_utc))
        forecast, forecast_unavailable = _get_or_refresh_forecast(
            member_email, account_id, provider_key, items, now=now_utc)
        if forecast:
            items = [forecast] + items
            forecast_diag = {'status': 'shown', 'reason': 'computed',
                             'provider': provider_key,
                             'currentMonth': now_utc.strftime('%Y-%m')}
        elif forecast_unavailable:
            forecast_diag['status'] = 'unavailable'
            forecast_diag['reason'] = 'compute_error'
        elif invoice_forecast is None:
            forecast_diag['status'] = 'disabled'
            forecast_diag['reason'] = 'module_unavailable'
        elif not invoice_forecast.is_aws_provider(provider_key):
            forecast_diag['status'] = 'skipped'
            forecast_diag['reason'] = 'not_aws_provider'
        elif not forecast_diag.get('inWindow'):
            forecast_diag['status'] = 'skipped'
            forecast_diag['reason'] = 'outside_forecast_window'
        elif now_utc.strftime('%Y-%m') in {str(i.get('period', '')) for i in items if i.get('period')}:
            forecast_diag['status'] = 'superseded'
            forecast_diag['reason'] = 'real_invoice_exists_for_current_month'
        else:
            forecast_diag['status'] = 'omitted'
            forecast_diag['reason'] = 'no_usable_month_to_date_cost'
    except Exception as e:
        logger.warning(f"Forecast integration skipped for {account_id}: {e}")
        forecast_diag = {'status': 'error', 'reason': str(e)[:200]}

    # OpenAI current-month forecast. The AWS-only path above never produces a
    # forecast for OpenAI, so emit one here and place it at the top (newest).
    # It supersedes any in-progress real invoice for the same month so the
    # current month is represented as a single "Forecast" row instead of a
    # misleading partial "paid" invoice. Any failure leaves the real list intact.
    if (provider_key == 'openai'
            and generate_openai_forecast is not None
            and not any(str(i.get('paymentStatus', '')).lower() == 'forecast'
                        for i in items)):
        try:
            now_oa = datetime.now(timezone.utc)
            current_month_oa = now_oa.strftime('%Y-%m')
            oa_forecast = generate_openai_forecast(member_email, account_id, now=now_oa)
            if oa_forecast:
                fc_period = oa_forecast.get('period', current_month_oa)
                # Drop the in-progress real invoice for the forecast month so the
                # forecast does not duplicate a real row for the same period.
                items = [
                    i for i in items
                    if not (str(i.get('period', '')) == fc_period
                            and str(i.get('paymentStatus', '')).lower() != 'forecast')
                ]
                items = [oa_forecast] + items
                forecast_diag = {'status': 'shown', 'reason': 'openai_forecast',
                                 'provider': provider_key,
                                 'currentMonth': current_month_oa}
        except Exception as e:
            logger.warning(f"OpenAI forecast integration skipped for {account_id}: {e}")

    # Apply pagination
    total_items = len(items)
    total_pages = math.ceil(total_items / page_size_int) if total_items > 0 else 0
    start_idx = (page_int - 1) * page_size_int
    end_idx = start_idx + page_size_int
    page_items = items[start_idx:end_idx]

    # Build response items (strip internal DynamoDB fields)
    response_items = []
    for item in page_items:
        shaped = {
            'invoiceId': item.get('invoiceId', ''),
            'accountId': item.get('accountId', 'N/A') or 'N/A',
            'issuer': item.get('issuer', 'Amazon Web Services'),
            'paymentDate': item.get('paymentDate', ''),
            'paymentStatus': item.get('paymentStatus', ''),
            'totalAmount': float(item.get('totalAmount', 0)),
            'currency': item.get('currency', 'USD'),
            'period': item.get('period', ''),
        }
        # Preserve forecast explanation/tips so the forecast row can render them.
        if item.get('costExplanation'):
            shaped['costExplanation'] = item.get('costExplanation')
        if item.get('tips'):
            shaped['tips'] = item.get('tips')
        response_items.append(shaped)

    return create_response(200, {
        'items': response_items,
        'forecastUnavailable': forecast_unavailable,
        'forecastDiag': forecast_diag,
        'invoiceDataUnavailable': invoice_data_unavailable,
        'pagination': {
            'page': page_int,
            'pageSize': page_size_int,
            'totalItems': total_items,
            'totalPages': total_pages,
        }
    })


def handle_service_breakdown_request(event, member_email):
    """
    Handle GET /members/invoices/services-breakdown.

    Returns the service-level cost breakdown for a specific invoice period.
    Checks DynamoDB cache first; on cache miss, fetches from Cost Explorer
    with SERVICE dimension grouping and generates cost explanations.

    Query params: accountId (required), period (required, YYYY-MM).
    """
    params = _get_query_params(event)

    # Extract and validate inputs
    account_id = params.get('accountId')
    period = params.get('period')

    # Validate accountId presence, then resolve the provider so account-id
    # validation can be provider-aware: AWS keeps the strict 12-digit rule;
    # non-AWS providers (azure/gcp/openai) use their own identifier formats.
    # Absent/empty -> 'aws'.
    if not account_id:
        return create_error_response(400, 'ValidationError', 'Account ID is required')

    provider_key = _get_account_provider(member_email, account_id) or 'aws'

    validation_error = validate_account_id_for_provider(account_id, provider_key)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate period
    validation_error = validate_period(period)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Verify account ownership
    ownership = _verify_account_ownership(member_email, account_id)
    if ownership is not True:
        return ownership

    # Task 5.1: Check DynamoDB cache first
    cached_records = _read_service_cache(member_email, account_id, period)

    if cached_records:
        services = cached_records
    elif provider_key == 'openai':
        # OpenAI exposes per-model cost data, so build a real service breakdown
        # (each "service" row is a model/line-item) instead of a graceful empty
        # one. Failures degrade to [] without raising. Cache populated results
        # using the same mechanism the AWS path uses, keyed by period.
        if generate_openai_service_breakdown is None:
            services = []
        else:
            services = generate_openai_service_breakdown(member_email, account_id, period)
            if services:
                _write_service_cache(member_email, account_id, period, services)
    elif provider_key in ('groundcover', 'anthropic'):
        # GroundCover/Anthropic: synthesize per-model breakdown from USAGE# items
        services = _synthesize_groundcover_service_breakdown(member_email, account_id, period)
        if services:
            _write_service_cache(member_email, account_id, period, services)
    elif provider_key != 'aws':
        # Service-level breakdown is derived from AWS Cost Explorer, which is
        # AWS-only. Azure/GCP have no equivalent per-service drill-down source
        # here, so return a graceful empty breakdown instead of attempting a
        # Cost Explorer call (which would fail with a 502). The synthetic monthly
        # invoice total still renders.
        services = []
    else:
        # Task 5.2/5.6: Cache miss — fetch from Cost Explorer
        try:
            services = fetch_service_breakdown(member_email, account_id, period)
        except Exception as e:
            logger.error(f"Failed to fetch service breakdown for {account_id} period={period}: {e}")
            return create_error_response(502, 'FetchError', f'Failed to retrieve service data: {str(e)}')

        # Task 5.5: Store fetched records in cache
        if services:
            _write_service_cache(member_email, account_id, period, services)

    # Sort by cost descending
    services = sorted(services, key=lambda x: float(x.get('amount', 0)), reverse=True)

    # Calculate total amount
    total_amount = round(sum(float(s.get('amount', 0)) for s in services), 2)

    # Build response
    response_services = []
    for svc in services:
        amount = float(svc.get('amount', 0))
        # Recompute the percentage from the authoritative period total so it is
        # always present and correct, regardless of which writer populated the
        # cache. The AWS invoice-sync refresh path (invoice_sync._normalize_records)
        # writes per-service records under the same "{period}#{service}" sort key
        # but WITHOUT a percentage field; reading those back previously surfaced
        # 0%/missing percentages for recently-refreshed (paid) months while older
        # drill-down-cached months still showed it. Deriving it here from
        # amount / total restores the percentage for all invoices.
        percentage = round((amount / total_amount) * 100, 1) if total_amount > 0 else 0.0
        response_services.append({
            'serviceName': svc.get('serviceName', ''),
            'amount': amount,
            'percentage': percentage,
            'costExplanation': svc.get('costExplanation', ''),
            'usageTypes': svc.get('usageTypes', []),
        })

    return create_response(200, {
        'accountId': account_id,
        'period': period,
        'totalAmount': total_amount,
        'services': response_services,
    })


def handle_resource_breakdown_request(event, member_email):
    """
    Handle GET /members/invoices/resources.

    Returns the resource-level cost breakdown for a specific service and
    period. Checks DynamoDB cache first; on cache miss, fetches from
    Cost Explorer with resource granularity, enriches with metadata from
    service-specific Describe APIs, and generates AI explanations via Bedrock.

    Query params: accountId (required), period (required), service (required).
    """
    params = _get_query_params(event)

    # Extract and validate inputs
    account_id = params.get('accountId')
    period = params.get('period')
    service = params.get('service')

    # Validate accountId presence, then resolve the provider so account-id
    # validation can be provider-aware: AWS keeps the strict 12-digit rule;
    # non-AWS providers (azure/gcp/openai) use their own identifier formats.
    # Absent/empty -> 'aws'.
    if not account_id:
        return create_error_response(400, 'ValidationError', 'Account ID is required')

    provider_key = _get_account_provider(member_email, account_id) or 'aws'

    validation_error = validate_account_id_for_provider(account_id, provider_key)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate period
    validation_error = validate_period(period)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate service
    validation_error = validate_service(service)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Verify account ownership
    ownership = _verify_account_ownership(member_email, account_id)
    if ownership is not True:
        return ownership

    # Task 7.9: Check DynamoDB cache first for resource-level records
    # For GroundCover/Anthropic, always synthesize fresh from USAGE# items
    # (fast query, avoids stale cached zeros from previous broken logic)
    if provider_key in ('groundcover', 'anthropic'):
        resources = _synthesize_groundcover_resource_breakdown(member_email, account_id, period, service)
        warnings = []
    else:
        cached_records = _read_resource_cache(member_email, account_id, period, service)

        if cached_records:
            resources = cached_records
            warnings = []
        elif provider_key != 'aws':
        # Resource-level breakdown is derived from AWS Cost Explorer, which is
        # AWS-only. Non-AWS providers (azure/gcp/openai) have no equivalent
        # per-resource drill-down source here, so return a graceful empty
        # breakdown instead of attempting a Cost Explorer call (which would
        # fail with a 502).
        resources = []
        warnings = []
    else:
        # Cache miss: fetch resources → enrich metadata → generate AI → store
        try:
            resources, warnings = fetch_resource_breakdown(member_email, account_id, period, service)
        except Exception as e:
            logger.error(f"Failed to fetch resource breakdown for {account_id} period={period} service={service}: {e}")
            return create_error_response(502, 'FetchError', f'Failed to retrieve resource data: {str(e)}')

        # Store fetched records in cache (only if we got data)
        if resources:
            try:
                _write_resource_cache(member_email, account_id, period, service, resources)
            except Exception as e:
                logger.warning(f"Failed to cache resource records: {e}")
                # Non-fatal — still return the data

    # Sort by cost descending
    resources = sorted(resources, key=lambda x: float(x.get('amount', 0)), reverse=True)

    # Calculate total amount
    total_amount = round(sum(float(r.get('amount', 0)) for r in resources), 2)

    # Build response
    response_resources = []
    for r in resources:
        savings_tip = _generate_savings_tip(
            r.get('resourceName', ''),
            r.get('resourceType', ''),
            float(r.get('amount', 0)),
            r.get('usageTypes', []),
        )
        response_resources.append({
            'resourceId': r.get('resourceId', ''),
            'resourceName': r.get('resourceName', ''),
            'resourceType': r.get('resourceType', 'Unknown'),
            'amount': float(r.get('amount', 0)),
            'costExplanation': r.get('costExplanation', ''),
            'aiExplanation': r.get('aiExplanation'),
            'usageTypes': r.get('usageTypes', []),
            'savingsTip': savings_tip,
        })

    return create_response(200, {
        'accountId': account_id,
        'period': period,
        'service': service,
        'totalAmount': total_amount,
        'resources': response_resources,
        'warnings': warnings,
    })


def handle_drilldown_refresh_request(event, member_email):
    """
    Handle POST /members/invoices/refresh.

    Forces a re-sync of all three drill-down levels for the specified
    account and period. Enforces a 5-minute cooldown per account to
    prevent excessive API calls.

    Body params: accountId (required), period (optional — refreshes all if omitted).
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'ValidationError', 'Invalid request body')

    account_id = body.get('accountId')
    period = body.get('period')

    # Validate accountId presence, then resolve the provider so validation can
    # be provider-aware: AWS keeps the strict 12-digit rule; non-AWS providers
    # (azure/gcp/openai) use their own identifier formats. Absent/empty -> 'aws'.
    if not account_id:
        return create_error_response(400, 'ValidationError', 'Account ID is required')

    provider_key = _get_account_provider(member_email, account_id) or 'aws'

    validation_error = validate_account_id_for_provider(account_id, provider_key)
    if validation_error:
        return create_error_response(400, validation_error[0], validation_error[1])

    # Validate period if provided
    if period:
        validation_error = validate_period(period)
        if validation_error:
            return create_error_response(400, validation_error[0], validation_error[1])

    # Verify account ownership
    ownership = _verify_account_ownership(member_email, account_id)
    if ownership is not True:
        return ownership

    # Task 9.1: Check rate limiting (5-minute cooldown per account)
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    cooldown_sk = f'REFRESH_COOLDOWN#{account_id}'
    now_epoch = int(time.time())

    try:
        cooldown_resp = table.get_item(
            Key={'pk': pk, 'sk': cooldown_sk},
        )
        cooldown_item = cooldown_resp.get('Item')

        if cooldown_item:
            last_refresh = int(cooldown_item.get('lastRefreshEpoch', 0))
            elapsed = now_epoch - last_refresh
            if elapsed < REFRESH_COOLDOWN:
                seconds_remaining = REFRESH_COOLDOWN - elapsed
                return create_error_response(429, 'RateLimited',
                    f'Refresh available in {seconds_remaining} seconds',
                    extra={'secondsRemaining': seconds_remaining})
    except ClientError as e:
        logger.warning(f"Failed to check refresh cooldown: {e}")
        # Proceed with refresh if we can't check cooldown

    # Resolve the account's provider so the clear-and-regenerate step below can
    # branch: AWS keeps its existing path; non-AWS routes through the additive
    # generate_provider_invoices generator (resolved above, absent/empty ->
    # 'aws') (Req 9.1).

    # For non-AWS accounts, regenerate the invoice records BEFORE clearing any
    # cached rows so that a regeneration failure leaves the prior cached INV#
    # rows intact (Req 9.3). On failure we return an error indication and never
    # reach the deletion block below. AWS keeps its existing clear-then-refetch
    # behavior unchanged.
    regenerated_invoices = None
    if provider_key == 'groundcover':
        # GroundCover accounts don't use the invoice system — their data is
        # consumed via the AI Cost dashboard (handle_openai_usage). A refresh
        # request is a no-op that succeeds silently.
        # Update cooldown so rapid re-clicks are throttled the same way.
        try:
            table.put_item(Item={
                'pk': pk, 'sk': cooldown_sk,
                'lastRefreshEpoch': now_epoch,
                'ttl': now_epoch + REFRESH_COOLDOWN + 300,
            })
        except Exception:
            pass
        return create_response(200, {
            'message': 'Refresh complete',
            'invoices': [],
            'source': 'groundcover_no_invoices',
        })
    if provider_key != 'aws':
        if generate_provider_invoices is None:
            logger.error(
                "provider_invoices module unavailable; cannot refresh "
                f"{account_id} provider={provider_key}; prior cache retained")
            return create_error_response(
                502, 'FetchError',
                'Failed to refresh invoice data; previously cached invoices retained')
        try:
            # Read existing cached periods to skip closed months that haven't changed
            _cached_periods = set()
            try:
                from boto3.dynamodb.conditions import Key as _DDBKey
                _cached_resp = invoices_table.query(
                    KeyConditionExpression=_DDBKey('pk').eq(f"{member_email}#{account_id}") & _DDBKey('sk').begins_with('INV#'),
                    ProjectionExpression='period'
                )
                for _item in _cached_resp.get('Items', []):
                    _p = _item.get('period', '')
                    if _p:
                        _cached_periods.add(_p)
            except Exception:
                _cached_periods = set()

            regenerated_invoices, regen_unavailable = generate_provider_invoices(
                member_email, account_id, provider_key, cached_periods=_cached_periods)
        except Exception as e:
            logger.error(
                "Provider invoice regeneration raised during refresh for "
                f"{account_id} provider={provider_key}: {type(e).__name__}")
            regenerated_invoices, regen_unavailable = [], True
        # A failed or empty regeneration must not wipe the existing cache: only
        # clear-and-replace after a successful regeneration produced records
        # (Req 9.3).
        if regen_unavailable or not regenerated_invoices:
            logger.warning(
                "Provider invoice regeneration unavailable during refresh for "
                f"{account_id} provider={provider_key}; prior cache retained")
            return create_error_response(
                502, 'FetchError',
                'Failed to refresh invoice data; previously cached invoices retained')

    # Delete all records for account+period (INV#, SVC#, RES# prefixes)
    try:
        # Query all records for this account
        query_kwargs = {
            'KeyConditionExpression': Key('pk').eq(pk),
            'ProjectionExpression': 'pk, sk',
        }

        if period:
            # If period specified, we need to delete records matching that period
            # We'll query all and filter
            pass

        all_items = []
        response = table.query(**query_kwargs)
        all_items.extend(response.get('Items', []))

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            query_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = table.query(**query_kwargs)
            all_items.extend(response.get('Items', []))

        # Filter items to delete based on period (if specified)
        items_to_delete = []
        for item in all_items:
            sk = str(item.get('sk', ''))
            # Skip the cooldown record itself
            if sk.startswith('REFRESH_COOLDOWN#'):
                continue

            if period:
                # Delete INV# records that match the period
                if sk.startswith('INV#'):
                    # We need to check if this invoice is for the given period
                    # For simplicity, delete all INV# records (they'll be re-fetched)
                    items_to_delete.append(item)
                # Delete SVC# records for this period
                elif sk.startswith(f'{period}#'):
                    items_to_delete.append(item)
                # Delete RES# records for this period
                elif sk.startswith(f'RES#{period}#'):
                    items_to_delete.append(item)
            else:
                # Delete all non-cooldown records
                items_to_delete.append(item)

        # Batch delete
        with table.batch_writer() as writer:
            for item in items_to_delete:
                writer.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})

    except ClientError as e:
        logger.error(f"Failed to delete cached records during refresh: {e}")
        return create_error_response(500, 'ServerError', 'Failed to clear cached data for refresh')

    # Re-fetch all three levels
    try:
        # Level 1: Invoice list — provider-aware (Req 9.1). AWS uses its existing
        # fetch path unchanged; non-AWS uses the records already regenerated
        # above (guaranteed non-empty and available at this point).
        if provider_key == 'aws':
            invoice_records = fetch_invoice_list(member_email, account_id)
        else:
            invoice_records = regenerated_invoices
        if invoice_records:
            _write_invoice_cache(member_email, account_id, invoice_records)

        # Level 2/3 service & resource breakdowns are AWS Cost Explorer paths and
        # only apply to AWS accounts (non-AWS providers have no SVC#/RES# cache).
        if provider_key == 'aws' and period:
            service_records = fetch_service_breakdown(member_email, account_id, period)
            if service_records:
                _write_service_cache(member_email, account_id, period, service_records)

                # Level 3: Resource breakdown for each service
                for svc in service_records:
                    svc_name = svc.get('serviceName', '')
                    if svc_name:
                        try:
                            resource_records, _ = fetch_resource_breakdown(
                                member_email, account_id, period, svc_name
                            )
                            if resource_records:
                                _write_resource_cache(
                                    member_email, account_id, period, svc_name, resource_records
                                )
                        except Exception as e:
                            logger.warning(f"Resource refresh failed for service {svc_name}: {e}")
                            # Continue with other services

    except Exception as e:
        logger.error(f"Failed to re-fetch data during refresh: {e}")
        return create_error_response(502, 'FetchError', f'Failed to refresh data: {str(e)}')

    # Update cooldown timestamp
    try:
        table.put_item(Item={
            'pk': pk,
            'sk': cooldown_sk,
            'lastRefreshEpoch': now_epoch,
            'ttl': now_epoch + REFRESH_COOLDOWN,
        })
    except ClientError as e:
        logger.warning(f"Failed to update refresh cooldown: {e}")
        # Non-fatal — refresh still succeeded

    return create_response(200, {
        'refreshed': True,
    })


# ─── Internal data-fetching helpers ───────────────────────────────────────────

def fetch_invoice_list(member_email, account_id):
    """
    Fetch invoice-level metadata for a single account.

    Cost Explorer (LINKED_ACCOUNT-scoped via apply_account_scope) is the
    source of truth for each month's totalAmount and currency, so a
    consolidated-billing PAYER account shows ONLY its own charges. The AWS
    Invoicing API (ListInvoiceSummaries) is queried best-effort to enrich
    records with the real invoiceId, issuer, and paymentStatus, matched by
    period (YYYY-MM). If the Invoicing API is unavailable or errors, pure
    Cost Explorer records are returned.

    Args:
        member_email: Authenticated member's email address.
        account_id: Target AWS account ID (12 digits).

    Returns:
        list[dict]: Normalized invoice records ready for DynamoDB storage.
    """
    creds = _assume_role(member_email, account_id)

    # ── Source of truth: LINKED_ACCOUNT-scoped Cost Explorer aggregation ──
    # The AWS Invoicing API's ListInvoiceSummaries has no LINKED_ACCOUNT filter,
    # so for a consolidated-billing PAYER account it returns the WHOLE org's
    # invoice total (other linked accounts' charges leak in). To guarantee each
    # account shows ONLY its own charges, every month's totalAmount/currency
    # comes from _fetch_invoices_from_cost_explorer (which wraps the CE call in
    # apply_account_scope(..., account_id) and matches the dashboard total).
    # The Invoicing API is used only best-effort to enrich records with the real
    # invoiceId, issuer, and paymentStatus, matched BY PERIOD (YYYY-MM).
    ce_records = _fetch_invoices_from_cost_explorer(creds, account_id)

    # Build per-period enrichment map from the Invoicing API (best-effort).
    invoicing_meta = {}
    try:
        invoicing_client = boto3.client(
            'invoicing',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name='us-east-1',
        )

        response = invoicing_client.list_invoice_summaries(
            Filter={'InvoiceReceivers': [account_id]}
        )
        invoices = response.get('InvoiceSummaries', [])

        for inv in invoices:
            payment_date = inv.get('PaymentDate', inv.get('DueDate', ''))
            if hasattr(payment_date, 'isoformat'):
                payment_date = payment_date.strftime('%Y-%m-%d')
            elif 'T' in str(payment_date):
                payment_date = str(payment_date).split('T')[0]

            period = str(payment_date)[:7] if payment_date else ''
            if not period:
                continue

            payment_status = inv.get('PaymentStatus', 'paid').lower()
            if payment_status not in ('paid', 'pending', 'overdue'):
                payment_status = 'paid'

            # NOTE: TotalAmount/CurrencyCode from the Invoicing API are
            # deliberately ignored — they are org-wide for payer accounts.
            invoicing_meta[period] = {
                'invoiceId': inv.get('InvoiceId', ''),
                'issuer': inv.get('Issuer', 'Amazon Web Services'),
                'paymentDate': str(payment_date),
                'paymentStatus': payment_status,
            }

    except (ClientError, Exception) as e:
        error_code = ''
        if isinstance(e, ClientError):
            error_code = e.response['Error']['Code']
        logger.info(
            f"Invoicing API unavailable for {account_id} ({type(e).__name__}: {error_code or str(e)}), "
            f"using pure Cost Explorer records"
        )
        # Fall back to pure CE records (current fallback behavior).
        return ce_records

    # Enrich the account-scoped CE records with real Invoicing API metadata,
    # matched by period. totalAmount and currency ALWAYS come from CE.
    records = []
    for ce_record in ce_records:
        period = ce_record.get('period', '')
        meta = invoicing_meta.get(period)
        if meta:
            records.append({
                'invoiceId': meta['invoiceId'] or ce_record['invoiceId'],
                'issuer': meta['issuer'],
                'paymentDate': meta['paymentDate'] or ce_record['paymentDate'],
                'paymentStatus': meta['paymentStatus'],
                'totalAmount': ce_record['totalAmount'],
                'currency': ce_record['currency'],
                'period': period,
                'source': 'cost_explorer',
            })
        else:
            # No matching Invoicing API record for this period (e.g. AWS has
            # not yet generated the previous month's invoice). Keep the pure
            # account-scoped CE record.
            records.append(ce_record)

    return records


def fetch_service_breakdown(member_email, account_id, period):
    """
    Fetch service-level cost breakdown for a specific period.

    Calls GetCostAndUsage with SERVICE dimension and USAGE_TYPE grouping
    via cross-account role assumption. Generates cost explanations for
    each service.

    Args:
        member_email: Authenticated member's email address.
        account_id: Target AWS account ID (12 digits).
        period: Billing period in YYYY-MM format.

    Returns:
        list[dict]: Normalized service records with cost explanations,
                    sorted by cost descending.
    """
    creds = _assume_role(member_email, account_id)

    ce_client = boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',
    )

    year, month_num = period.split('-')
    start_date = f'{year}-{month_num}-01'
    end_date = _get_next_month_first_day(int(year), int(month_num))
    # Current (in-progress) month: clamp the future end date to tomorrow so the
    # Forecast invoice drill-down returns MTD service data instead of erroring.
    end_date = _clamp_end_date_to_tomorrow(end_date)

    try:
        response = ce_client.get_cost_and_usage(
            **apply_account_scope({
                'TimePeriod': {'Start': start_date, 'End': end_date},
                'Granularity': 'MONTHLY',
                'Metrics': ['UnblendedCost', 'UsageQuantity'],
                'GroupBy': [
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
                ],
            }, account_id)
        )
    except ClientError as e:
        logger.error(f"Cost Explorer fetch failed for {account_id} period={period}: {e}")
        raise

    # Parse response: group usage types by service
    service_data = {}

    for period_result in response.get('ResultsByTime', []):
        for group in period_result.get('Groups', []):
            keys = group['Keys']
            service_name = keys[0]
            usage_type = keys[1] if len(keys) > 1 else 'Unknown'
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
            unit = group['Metrics'].get('UsageQuantity', {}).get('Unit', '')

            if service_name not in service_data:
                service_data[service_name] = {'total_cost': 0.0, 'usage_types': []}

            service_data[service_name]['total_cost'] += cost

            if abs(cost) >= 0.005:
                service_data[service_name]['usage_types'].append({
                    'type': usage_type,
                    'cost': round(cost, 2),
                    'unit': unit,
                    'quantity': round(quantity, 4),
                })

    # Filter out services with cost < $0.01
    filtered_services = {
        name: data for name, data in service_data.items()
        if data['total_cost'] >= 0.01
    }

    # Calculate total for percentage computation
    total_cost = sum(data['total_cost'] for data in filtered_services.values())

    # Build service records
    records = []
    for service_name, data in filtered_services.items():
        amount = round(data['total_cost'], 2)
        percentage = round((amount / total_cost) * 100, 1) if total_cost > 0 else 0.0
        cost_explanation = generate_cost_explanation(data['usage_types'])

        usage_types = []
        for ut in data['usage_types']:
            usage_types.append({
                'type': ut['type'],
                'cost': ut['cost'],
                'unit': ut['unit'],
                'quantity': ut['quantity'],
            })

        records.append({
            'serviceName': service_name,
            'amount': amount,
            'percentage': percentage,
            'costExplanation': cost_explanation,
            'usageTypes': usage_types,
        })

    records.sort(key=lambda x: x['amount'], reverse=True)
    return records


def fetch_resource_breakdown(member_email, account_id, period, service):
    """
    Fetch resource-level costs for a specific service and period.

    Calls GetCostAndUsageWithResources via cross-account role assumption,
    enriches resource IDs with metadata from Describe APIs, and generates
    AI explanations via Bedrock for resources above the cost threshold.

    Args:
        member_email: Authenticated member's email address.
        account_id: Target AWS account ID (12 digits).
        period: Billing period in YYYY-MM format.
        service: AWS service name (e.g., "Amazon EC2").

    Returns:
        tuple: (list[dict], list[str]) — normalized resource records and
               a list of warning messages for partial failures.
    """
    warnings = []
    creds = _assume_role(member_email, account_id)

    ce_client = boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',
    )

    year, month_num = period.split('-')
    start_date = f'{year}-{month_num}-01'
    end_date = _get_next_month_first_day(int(year), int(month_num))
    # Current (in-progress) month: clamp the future end date to tomorrow so the
    # Forecast invoice drill-down returns MTD resource data instead of erroring.
    end_date = _clamp_end_date_to_tomorrow(end_date)

    # Call GetCostAndUsageWithResources with service filter
    # Note: This API only supports the last 14 days. For older periods, fall back
    # to GetCostAndUsage with USAGE_TYPE grouping.
    try:
        response = ce_client.get_cost_and_usage_with_resources(
            **apply_account_scope({
                'TimePeriod': {'Start': start_date, 'End': end_date},
                'Granularity': 'MONTHLY',
                'Metrics': ['UnblendedCost', 'UsageQuantity'],
                'Filter': {
                    'Dimensions': {
                        'Key': 'SERVICE',
                        'Values': [service],
                    }
                },
                'GroupBy': [
                    {'Type': 'DIMENSION', 'Key': 'RESOURCE_ID'},
                ],
            }, account_id)
        )
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error'].get('Message', '')
        # Handle "start date is too old" — fall back to usage-type breakdown
        if 'ValidationException' in error_code and 'too old' in error_msg.lower():
            logger.info(f"Resource-level data unavailable for {period} (>14 days), falling back to usage-type breakdown")
            return _fetch_usage_type_breakdown(ce_client, creds, service, start_date, end_date, period, account_id)
        # Handle "resource data not available" gracefully
        if 'ResourceNotAvailable' in error_code or 'not available' in error_msg.lower():
            logger.info(f"Resource-level data not available for {account_id}, falling back to usage-type breakdown")
            return _fetch_usage_type_breakdown(ce_client, creds, service, start_date, end_date, period, account_id)
        logger.error(f"GetCostAndUsageWithResources failed for {account_id}: {e}")
        raise

    # Normalize into resource records
    resource_data = {}
    for period_result in response.get('ResultsByTime', []):
        for group in period_result.get('Groups', []):
            resource_id = group['Keys'][0] if group['Keys'] else 'Unknown'
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
            unit = group['Metrics'].get('UsageQuantity', {}).get('Unit', '')

            if resource_id not in resource_data:
                resource_data[resource_id] = {'total_cost': 0.0, 'usage_types': []}

            resource_data[resource_id]['total_cost'] += cost

            if abs(cost) >= 0.005:
                # Derive usage type from resource context
                usage_type = f"{service}:{resource_id}"
                resource_data[resource_id]['usage_types'].append({
                    'type': usage_type,
                    'cost': round(cost, 2),
                    'unit': unit,
                    'quantity': round(quantity, 4),
                })

    # Filter out resources with negligible cost
    filtered_resources = {
        rid: data for rid, data in resource_data.items()
        if data['total_cost'] >= 0.005
    }

    if not filtered_resources:
        return [], warnings

    resource_ids = list(filtered_resources.keys())

    # Enrich resource metadata (names and types)
    try:
        metadata = enrich_resource_metadata(creds, service, resource_ids)
    except Exception as e:
        logger.warning(f"Resource metadata enrichment failed: {e}")
        metadata = {}
        warnings.append('Resource names unavailable (missing permissions)')

    # Build resource records with cost explanations
    records = []
    for resource_id, data in filtered_resources.items():
        meta = metadata.get(resource_id, {'name': resource_id, 'type': 'Unknown'})
        amount = round(data['total_cost'], 2)
        cost_explanation = generate_cost_explanation(data['usage_types'])

        records.append({
            'resourceId': resource_id,
            'resourceName': meta.get('name', resource_id),
            'resourceType': meta.get('type', 'Unknown'),
            'amount': amount,
            'costExplanation': cost_explanation,
            'aiExplanation': None,
            'usageTypes': data['usage_types'],
        })

    # Sort by cost descending
    records.sort(key=lambda x: x['amount'], reverse=True)

    # Generate AI explanations for resources above threshold
    ai_eligible = [r for r in records if r['amount'] > AI_COST_THRESHOLD]
    if ai_eligible:
        try:
            ai_explanations = generate_ai_explanations(service, ai_eligible)
            for record in records:
                if record['resourceId'] in ai_explanations:
                    record['aiExplanation'] = ai_explanations[record['resourceId']]
        except Exception as e:
            logger.warning(f"AI explanation generation failed: {e}")
            # Fall back silently — aiExplanation stays None

    return records, warnings


def enrich_resource_metadata(credentials, service, resource_ids):
    """
    Call service-specific Describe APIs to get resource names and types.

    Maps service names to appropriate AWS API calls:
      - Amazon EC2 → DescribeInstances
      - Amazon RDS → DescribeDBInstances
      - Amazon S3 → ListBuckets
      - AWS Lambda → ListFunctions
      - Amazon EBS → DescribeVolumes
      - Amazon ElastiCache → DescribeCacheClusters
      - Amazon DynamoDB → parse table name from ARN

    On failure or timeout (10s), returns raw resource ID as name and
    "Unknown" as type.

    Args:
        credentials: Cross-account STS credentials dict.
        service: AWS service name.
        resource_ids: List of resource IDs to enrich.

    Returns:
        dict: {resource_id: {"name": str, "type": str}} mapping.
    """
    from botocore.config import Config

    result = {}
    if not resource_ids:
        return result

    # Default fallback for all resource IDs
    for rid in resource_ids:
        result[rid] = {'name': rid, 'type': 'Unknown'}

    # Configure timeout
    timeout_config = Config(
        read_timeout=RESOURCE_TIMEOUT,
        connect_timeout=RESOURCE_TIMEOUT,
        retries={'max_attempts': 1},
    )

    client_kwargs = {
        'aws_access_key_id': credentials['AccessKeyId'],
        'aws_secret_access_key': credentials['SecretAccessKey'],
        'aws_session_token': credentials['SessionToken'],
        'region_name': 'us-east-1',
        'config': timeout_config,
    }

    try:
        service_lower = service.lower()

        if 'elastic compute' in service_lower or service_lower == 'amazon ec2':
            # Amazon Elastic Compute Cloud - Compute or Amazon EC2 → ec2:DescribeInstances
            ec2_client = boto3.client('ec2', **client_kwargs)
            # Filter to only instance IDs (i-xxx)
            instance_ids = [rid for rid in resource_ids if rid.startswith('i-')]
            if instance_ids:
                resp = ec2_client.describe_instances(InstanceIds=instance_ids)
                for reservation in resp.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        iid = instance['InstanceId']
                        name = iid  # default
                        for tag in instance.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                                break
                        result[iid] = {
                            'name': name,
                            'type': instance.get('InstanceType', 'Unknown'),
                        }

        elif 'rds' in service_lower or 'relational database' in service_lower:
            # Amazon RDS → rds:DescribeDBInstances
            rds_client = boto3.client('rds', **client_kwargs)
            resp = rds_client.describe_db_instances()
            db_instances = {
                db['DBInstanceIdentifier']: db
                for db in resp.get('DBInstances', [])
            }
            for rid in resource_ids:
                # Resource ID might be the ARN or the identifier
                db_id = rid.split(':')[-1] if ':' in rid else rid
                if db_id in db_instances:
                    db = db_instances[db_id]
                    result[rid] = {
                        'name': db['DBInstanceIdentifier'],
                        'type': db.get('DBInstanceClass', 'Unknown'),
                    }

        elif 's3' in service_lower or 'simple storage' in service_lower:
            # Amazon S3 → s3:ListBuckets
            s3_client = boto3.client('s3', **client_kwargs)
            resp = s3_client.list_buckets()
            bucket_names = {b['Name'] for b in resp.get('Buckets', [])}
            for rid in resource_ids:
                bucket_name = rid.split('/')[-1] if '/' in rid else rid
                if bucket_name in bucket_names:
                    result[rid] = {
                        'name': bucket_name,
                        'type': 'Standard',
                    }

        elif 'lambda' in service_lower:
            # AWS Lambda → lambda:ListFunctions
            lambda_client = boto3.client('lambda', **client_kwargs)
            resp = lambda_client.list_functions()
            functions = {
                f['FunctionName']: f
                for f in resp.get('Functions', [])
            }
            for rid in resource_ids:
                # Resource ID might be ARN or function name
                func_name = rid.split(':')[-1] if ':' in rid else rid
                if func_name in functions:
                    func = functions[func_name]
                    result[rid] = {
                        'name': func['FunctionName'],
                        'type': func.get('Runtime', 'Unknown'),
                    }

        elif 'ebs' in service_lower or 'elastic block' in service_lower:
            # Amazon EBS → ec2:DescribeVolumes
            ec2_client = boto3.client('ec2', **client_kwargs)
            volume_ids = [rid for rid in resource_ids if rid.startswith('vol-')]
            if volume_ids:
                resp = ec2_client.describe_volumes(VolumeIds=volume_ids)
                for vol in resp.get('Volumes', []):
                    vid = vol['VolumeId']
                    name = vid  # default
                    for tag in vol.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break
                    vol_type = vol.get('VolumeType', 'Unknown')
                    vol_size = vol.get('Size', 0)
                    result[vid] = {
                        'name': name,
                        'type': f"{vol_type} {vol_size}GB",
                    }

        elif 'elasticache' in service_lower:
            # Amazon ElastiCache → elasticache:DescribeCacheClusters
            ec_client = boto3.client('elasticache', **client_kwargs)
            resp = ec_client.describe_cache_clusters()
            clusters = {
                c['CacheClusterId']: c
                for c in resp.get('CacheClusters', [])
            }
            for rid in resource_ids:
                cluster_id = rid.split('/')[-1] if '/' in rid else rid
                if cluster_id in clusters:
                    cluster = clusters[cluster_id]
                    result[rid] = {
                        'name': cluster['CacheClusterId'],
                        'type': cluster.get('CacheNodeType', 'Unknown'),
                    }

        elif 'dynamodb' in service_lower:
            # Amazon DynamoDB → parse table name from ARN
            for rid in resource_ids:
                if 'table/' in rid:
                    table_name = rid.split('table/')[-1].split('/')[0]
                    result[rid] = {
                        'name': table_name,
                        'type': 'Table',
                    }
                else:
                    result[rid] = {
                        'name': rid,
                        'type': 'Table',
                    }

    except Exception as e:
        logger.warning(f"Resource metadata enrichment failed for service={service}: {e}")
        # Fallback already set — raw IDs with "Unknown" type

    return result


def generate_ai_explanations(service, resources):
    """
    Batch call to Amazon Bedrock (Nova Lite) for AI-powered cost explanations.

    Builds a prompt with service context and resource details, sends to
    Bedrock, and parses per-resource explanations from the response.
    Only called for resources with cost > AI_COST_THRESHOLD ($1.00).

    Times out after AI_TIMEOUT (15s); on failure returns empty dict
    (callers fall back to formula-based explanations).

    Args:
        service: AWS service name (e.g., "Amazon EC2").
        resources: List of resource dicts containing name, type, cost,
                   and usage data.

    Returns:
        dict: {resource_id: explanation_text} for successfully explained
              resources. Missing keys indicate AI was not generated.
    """
    from botocore.config import Config

    if not resources:
        return {}

    # Filter to only resources above threshold
    eligible = [r for r in resources if float(r.get('amount', 0)) > AI_COST_THRESHOLD]
    if not eligible:
        return {}

    # Build prompt
    resource_lines = []
    for r in eligible:
        name = r.get('resourceName', r.get('resourceId', 'Unknown'))
        rtype = r.get('resourceType', 'Unknown')
        amount = float(r.get('amount', 0))

        # Extract usage details for the prompt
        usage_types = r.get('usageTypes', [])
        if usage_types:
            ut = usage_types[0]
            quantity = float(ut.get('quantity', 0))
            unit = ut.get('unit', '')
            cost = float(ut.get('cost', 0))
            rate = cost / quantity if quantity > 0 else 0
            resource_lines.append(
                f"- Resource: {name} ({rtype}), Cost: ${amount:.2f}, "
                f"Usage: {quantity:.2f} {unit} at ${rate:.4f}/{unit}"
            )
        else:
            resource_lines.append(
                f"- Resource: {name} ({rtype}), Cost: ${amount:.2f}, Usage: N/A"
            )

    prompt_text = (
        "You are a cloud cost analyst explaining AWS charges to a non-technical business owner.\n"
        "For each resource below, write a 1-2 sentence explanation of what was charged and why,\n"
        "in plain language. Include the resource name, what it does, and how the cost was calculated.\n\n"
        f"Service: {service}\n"
        "Resources:\n"
        + "\n".join(resource_lines) + "\n\n"
        "Respond with one explanation per resource, formatted as:\n"
        "RESOURCE_ID: explanation text"
    )

    # Call Bedrock Nova Lite
    timeout_config = Config(
        read_timeout=AI_TIMEOUT,
        connect_timeout=AI_TIMEOUT,
        retries={'max_attempts': 1},
    )

    try:
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name='us-east-1',
            config=timeout_config,
        )

        request_body = json.dumps({
            'messages': [
                {
                    'role': 'user',
                    'content': [{'text': prompt_text}],
                }
            ],
            'inferenceConfig': {
                'maxTokens': 2048,
                'temperature': 0.3,
            },
        })

        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=request_body,
        )

        response_body = json.loads(response['body'].read())

        # Extract text from response
        output_text = ''
        if 'output' in response_body and 'message' in response_body['output']:
            content_blocks = response_body['output']['message'].get('content', [])
            for block in content_blocks:
                if 'text' in block:
                    output_text += block['text']
        elif 'content' in response_body:
            for block in response_body['content']:
                if 'text' in block:
                    output_text += block['text']

        # Parse per-resource explanations
        explanations = {}
        # Map resource names/IDs for matching
        resource_id_map = {}
        for r in eligible:
            rid = r.get('resourceId', '')
            resource_id_map[rid] = rid
            resource_id_map[r.get('resourceName', '')] = rid

        # Split by lines and look for "RESOURCE_ID:" or resource name patterns
        lines = output_text.strip().split('\n')
        current_id = None
        current_text = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this line starts a new resource explanation
            matched_id = None
            for rid in eligible:
                resource_id = rid.get('resourceId', '')
                resource_name = rid.get('resourceName', '')
                if line.startswith(f"{resource_id}:"):
                    matched_id = resource_id
                    line = line[len(resource_id) + 1:].strip()
                    break
                elif line.startswith(f"{resource_name}:"):
                    matched_id = resource_id
                    line = line[len(resource_name) + 1:].strip()
                    break

            if matched_id:
                # Save previous
                if current_id and current_text:
                    explanations[current_id] = ' '.join(current_text)
                current_id = matched_id
                current_text = [line] if line else []
            elif current_id:
                current_text.append(line)

        # Save last
        if current_id and current_text:
            explanations[current_id] = ' '.join(current_text)

        return explanations

    except Exception as e:
        logger.warning(f"Bedrock AI explanation generation failed: {e}")
        return {}


def generate_cost_explanation(usage_types):
    """
    Generate a formula-based cost explanation from usage type data.

    Combines quantity, unit, and effective rate into a human-readable
    formula string. Annotates with "(full month)" when hours ≈ 730 (±10).

    Format: "{quantity} {unit} × ${rate}/{unit_abbrev}"
    Multiple usage types produce separate lines.
    Falls back to "Monthly charge: ${amount}" for blended costs without
    clear rates, or "See resource breakdown for details" when data is
    insufficient.

    Args:
        usage_types: List of dicts with keys: type, cost, unit, quantity.

    Returns:
        str: Human-readable cost explanation string.
    """
    if not usage_types:
        return "See resource breakdown for details"

    lines = []
    for ut in usage_types:
        quantity = float(ut.get('quantity', 0))
        unit = str(ut.get('unit', ''))
        cost = float(ut.get('cost', 0))

        # Fallback for blended/amortized costs (quantity is 0 or unit is empty)
        if quantity == 0 or not unit.strip():
            lines.append(f"Monthly charge: ${cost:.2f}")
            continue

        # Calculate rate
        rate = cost / quantity

        # Round rate to 4 significant digits
        rate_str = _format_significant(rate, 4)

        # Format quantity for display
        quantity_str = _format_quantity(quantity)

        # Get unit abbreviation
        unit_abbrev = _get_unit_abbreviation(unit)

        # Build formula line
        line = f"{quantity_str} {unit} \u00d7 ${rate_str}/{unit_abbrev}"

        # Annotate with "(full month)" when hours ≈ 730 (±10)
        if unit.lower() in ('hrs', 'hours', 'hr') and 720 <= quantity <= 740:
            line += " (full month)"

        lines.append(line)

    return "\n".join(lines)


# ─── Cost explanation helper functions ────────────────────────────────────────

def _format_significant(value, sig_figs):
    """Format a number to the specified number of significant digits.

    Args:
        value: The numeric value to format.
        sig_figs: Number of significant digits.

    Returns:
        str: Formatted number string.
    """
    if value == 0:
        return "0"

    magnitude = math.floor(math.log10(abs(value)))
    decimal_places = sig_figs - 1 - magnitude

    if decimal_places < 0:
        rounded = round(value, decimal_places)
        return f"{rounded:.0f}"
    else:
        rounded = round(value, decimal_places)
        return f"{rounded:.{decimal_places}f}"


def _format_quantity(quantity):
    """Format quantity for display — remove trailing zeros.

    Args:
        quantity: Numeric quantity value.

    Returns:
        str: Formatted quantity string.
    """
    if quantity == int(quantity):
        return str(int(quantity))
    formatted = f"{quantity:.2f}".rstrip('0').rstrip('.')
    return formatted


def _get_unit_abbreviation(unit):
    """Map usage unit to display abbreviation.

    Mappings:
        "Hrs" → "hr"
        "GB" → "GB"
        "GB-Mo" → "GB-month"
        "Requests" → "req"
        default → use unit as-is

    Args:
        unit: The raw unit string from Cost Explorer.

    Returns:
        str: Abbreviated unit string.
    """
    unit_map = {
        'Hrs': 'hr',
        'Hours': 'hr',
        'Hr': 'hr',
        'GB': 'GB',
        'GB-Mo': 'GB-month',
        'Requests': 'req',
    }
    return unit_map.get(unit, unit)


def _generate_savings_tip(resource_name, resource_type, amount, usage_types):
    """Generate a brief savings recommendation for a resource.

    Based on the resource type and cost, provides a short actionable tip
    that the user can explore further in the Chat tab.

    Args:
        resource_name: Display name of the resource.
        resource_type: Type classification (e.g., 'EC2 Instance', 'EBS Volume').
        amount: Monthly cost in USD.
        usage_types: List of usage type dicts.

    Returns:
        str: A brief savings tip, or empty string if no tip applies.
    """
    rtype_lower = (resource_type or '').lower()
    usage_str = ' '.join(ut.get('type', '') for ut in (usage_types or []))

    # EC2 instances
    if 'ec2 instance' in rtype_lower or 'boxusage' in usage_str.lower():
        if amount > 500:
            return "Consider Reserved Instances or Savings Plans for up to 72% savings"
        elif amount > 100:
            return "Check if rightsizing or Spot instances could reduce costs"
        else:
            return "Review if this instance can be scheduled off-hours"

    # EBS volumes
    if 'ebs' in rtype_lower or 'volume' in rtype_lower:
        if 'gp2' in usage_str.lower():
            return "Migrate from gp2 to gp3 for ~20% savings with better performance"
        elif 'io1' in usage_str.lower() or 'io2' in usage_str.lower():
            return "Review provisioned IOPS — consider gp3 if IOPS needs are under 16K"
        return "Check for unattached or oversized volumes"

    # Data transfer
    if 'data transfer' in rtype_lower:
        if amount > 50:
            return "Use CloudFront or VPC endpoints to reduce transfer costs"
        return "Review cross-region/cross-AZ data transfer patterns"

    # NAT Gateway
    if 'nat' in rtype_lower or 'natgateway' in usage_str.lower():
        return "Consider VPC endpoints for S3/DynamoDB to bypass NAT charges"

    # RDS
    if 'rds' in rtype_lower:
        if amount > 200:
            return "Consider Reserved Instances or Aurora Serverless for variable workloads"
        return "Review if Multi-AZ is needed or if instance can be rightsized"

    # S3
    if 's3' in rtype_lower:
        return "Set up lifecycle policies to move infrequent data to cheaper tiers"

    # Lambda
    if 'lambda' in rtype_lower:
        return "Optimize memory allocation and reduce cold starts"

    # Load Balancer
    if 'load balancer' in rtype_lower or 'elb' in rtype_lower:
        return "Consolidate load balancers or switch to ALB for cost efficiency"

    # ElastiCache
    if 'elasticache' in rtype_lower or 'cache' in rtype_lower:
        return "Consider Reserved Nodes or serverless ElastiCache"

    # Generic high-cost
    if amount > 100:
        return "Review usage patterns for potential optimization"

    return ""


# ─── Cross-account role assumption ───────────────────────────────────────────

def _assume_role(member_email, account_id):
    """Assume the cross-account SlashMyBill role.

    Uses the same pattern as invoice_sync.py:
    - Role ARN: arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}
    - ExternalId: SHA-256 hash of member email
    - Session name: SlashMyBillDrilldown

    Args:
        member_email: Member's email address (used for ExternalId).
        account_id: Target AWS account ID.

    Returns:
        dict with AccessKeyId, SecretAccessKey, SessionToken.
    """
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts')
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SlashMyBillDrilldown',
        ExternalId=external_id,
    )
    return resp['Credentials']


# ─── DynamoDB cache helpers ───────────────────────────────────────────────────

def _read_invoice_cache(member_email, account_id):
    """Read cached invoice-level records from DynamoDB.

    Task 4.1: Query MemberPortal-Invoices table with pk = {email}#{accountId}
    and sk begins_with "INV#". Check TTL validity.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.

    Returns:
        list[dict]: Cached invoice records, or empty list if cache miss.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_epoch = int(time.time())

    try:
        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with('INV#'),
        )
    except ClientError as e:
        logger.error(f"DynamoDB cache read failed for invoices: {e}")
        return []

    # Filter by TTL validity
    valid_records = []
    for item in response.get('Items', []):
        ttl_val = int(item.get('ttl', 0))
        if ttl_val > now_epoch:
            valid_records.append(_dynamo_item_to_dict(item))

    return valid_records


def _write_invoice_cache(member_email, account_id, records):
    """Write invoice-level records to DynamoDB cache.

    Task 4.3: Write with sk = INV#{invoiceId}, recordType = "invoice",
    lastSyncedAt = current ISO timestamp, ttl = epoch + 90 days.
    Uses batch_writer for efficiency. Atomic: all or nothing.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.
        records: List of normalized invoice record dicts.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_iso = datetime.now(timezone.utc).isoformat()
    ttl_epoch = int(time.time()) + TTL_SECONDS

    try:
        with table.batch_writer() as writer:
            for record in records:
                # Resolve account ID at sync time using parser-first/metadata-fallback
                resolved_account_id = resolve_account_id(
                    record.get('accountId', record.get('parsed_account_id')),
                    account_id,
                    provider_key=record.get('provider_key', 'aws'),
                )
                item = {
                    'pk': pk,
                    'sk': f"INV#{record['invoiceId']}",
                    'recordType': 'real',
                    'invoiceId': record['invoiceId'],
                    'issuer': record.get('issuer', 'Amazon Web Services'),
                    'paymentDate': record.get('paymentDate', ''),
                    'paymentStatus': record.get('paymentStatus', ''),
                    'totalAmount': Decimal(str(record.get('totalAmount', 0))),
                    'currency': record.get('currency', 'USD'),
                    'period': record.get('period', ''),
                    'source': record.get('source', ''),
                    'accountId': resolved_account_id,
                    'lastSyncedAt': now_iso,
                    'ttl': ttl_epoch,
                }
                writer.put_item(Item=item)
    except (ClientError, Exception) as e:
        logger.error(f"DynamoDB cache write failed for invoices: {e}")
        raise


# ─── Forecast cache helpers ───────────────────────────────────────────────────

def _read_forecast_record(member_email, account_id, current_month=None):
    """Read the cached Forecast_Invoice record (sk begins_with FCST#).

    If current_month is given, returns that specific FCST#{month} record;
    otherwise returns the single most recent forecast record. Returns None
    when absent or expired by TTL. (Req 12.2)
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_epoch = int(time.time())

    try:
        if current_month:
            resp = table.get_item(
                Key={'pk': pk, 'sk': f'{invoice_forecast.FORECAST_SK_PREFIX}{current_month}'}
            )
            item = resp.get('Item')
            items = [item] if item else []
        else:
            resp = table.query(
                KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(
                    invoice_forecast.FORECAST_SK_PREFIX),
            )
            items = resp.get('Items', [])
    except ClientError as e:
        logger.error(f"DynamoDB forecast cache read failed: {e}")
        return None

    valid = [it for it in items if it and int(it.get('ttl', 0)) > now_epoch]
    if not valid:
        return None
    # Most recent forecast month wins if multiple are present
    valid.sort(key=lambda it: str(it.get('forecastMonth', '')), reverse=True)
    return _forecast_item_to_dict(valid[0])


def _write_forecast_record(member_email, account_id, record):
    """Persist the forecast record with sk=FCST#{forecastMonth},
    recordType='forecast', ttl = epoch + 90 days. (Req 12.1)"""
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_iso = datetime.now(timezone.utc).isoformat()
    ttl_epoch = int(time.time()) + TTL_SECONDS
    month = record.get('forecastMonth') or record.get('period', '')

    item = {
        'pk': pk,
        'sk': f"{invoice_forecast.FORECAST_SK_PREFIX}{month}",
        'recordType': invoice_forecast.RECORD_TYPE_FORECAST,
        'invoiceId': record.get('invoiceId', ''),
        'issuer': record.get('issuer', 'Amazon Web Services'),
        'paymentDate': record.get('paymentDate', ''),
        'paymentStatus': record.get('paymentStatus', 'Forecast'),
        'totalAmount': Decimal(str(record.get('totalAmount', 0))),
        'currency': record.get('currency', 'USD'),
        'period': record.get('period', month),
        'forecastMonth': month,
        'monthToDateCost': Decimal(str(record.get('monthToDateCost', 0))),
        'medianDailyCost': Decimal(str(record.get('medianDailyCost', 0))),
        'variableCostForecast': Decimal(str(record.get('variableCostForecast', 0))),
        'fixedCostForecast': Decimal(str(record.get('fixedCostForecast', 0))),
        'elapsedDays': int(record.get('elapsedDays', 0)),
        'remainingDays': int(record.get('remainingDays', 0)),
        'source': record.get('source', 'forecast_engine'),
        'lastSyncedAt': now_iso,
        'ttl': ttl_epoch,
    }
    try:
        table.put_item(Item=item)
    except (ClientError, Exception) as e:
        logger.error(f"DynamoDB forecast cache write failed: {e}")
        raise


def _delete_forecast_record(member_email, account_id, month):
    """Delete a stale/superseded forecast record (sk=FCST#{month})."""
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    try:
        table.delete_item(Key={'pk': pk, 'sk': f'{invoice_forecast.FORECAST_SK_PREFIX}{month}'})
    except ClientError as e:
        logger.warning(f"DynamoDB forecast cache delete failed for {month}: {e}")


def _forecast_item_to_dict(item):
    """Convert a stored DynamoDB forecast item to a plain dict."""
    return {
        'invoiceId': str(item.get('invoiceId', '')),
        'issuer': str(item.get('issuer', 'Amazon Web Services')),
        'paymentDate': str(item.get('paymentDate', '')),
        'paymentStatus': str(item.get('paymentStatus', 'Forecast')),
        'totalAmount': float(item.get('totalAmount', 0)),
        'currency': str(item.get('currency', 'USD')),
        'period': str(item.get('period', '')),
        'forecastMonth': str(item.get('forecastMonth', '')),
        'recordType': str(item.get('recordType', invoice_forecast.RECORD_TYPE_FORECAST)),
    }


def _get_account_provider(member_email, account_id):
    """Return the account's cloudProvider (Provider_Key).

    Legacy/AWS accounts are frequently stored with a missing or empty
    cloudProvider; consistent with _backfill_cloud_provider and the rest of
    the portal, an absent value defaults to 'aws' so AWS accounts still get a
    forecast. Returns '' only when the account cannot be found at all.
    """
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=Key('memberEmail').eq(member_email),
            ProjectionExpression='accountId, cloudProvider',
        )
        for item in result.get('Items', []):
            if item.get('accountId') == account_id:
                return str(item.get('cloudProvider', '') or 'aws')
    except ClientError as e:
        logger.warning(f"Failed to read provider for {account_id}: {e}")
    return ''


def _latest_real_issuer(items):
    """Derive the issuer from the most recent Real_Invoice (by period desc),
    or None when there is no prior real invoice. (Req 9.3, 9.4)"""
    real = [i for i in items if i.get('period')]
    if not real:
        return None
    real_sorted = sorted(real, key=lambda x: str(x.get('period', '')), reverse=True)
    return real_sorted[0].get('issuer') or None


def _get_or_refresh_forecast(member_email, account_id, provider_key, items, now=None):
    """Merge/supersede/staleness logic for the Current_Month forecast.

    Returns a tuple (forecast_dict_or_None, forecast_unavailable_bool).

    - Drops/deletes the forecast when a Real_Invoice for the same period exists
      (Req 10.2, 10.4).
    - Returns the cached forecast when its month matches the current UTC month
      (Req 12.2).
    - Recomputes when stale/missing; deletes stale on None; on compute failure
      deletes the stale record and signals forecastUnavailable (Req 12.3, 12.4, 8.11).
    """
    now = now or datetime.now(timezone.utc)
    current_month = now.strftime('%Y-%m')
    real_periods = {str(i.get('period', '')) for i in items if i.get('period')}

    # Forecast module not packaged -> silently disable forecasting (best-effort).
    if invoice_forecast is None:
        return None, False

    cached = _read_forecast_record(member_email, account_id)

    # Supersession: a real invoice already exists for the current month.
    if current_month in real_periods:
        if cached and cached.get('forecastMonth'):
            _delete_forecast_record(member_email, account_id, cached['forecastMonth'])
        return None, False

    # Only AWS accounts get a forecast (Req 11).
    if not invoice_forecast.is_aws_provider(provider_key):
        if cached and cached.get('forecastMonth'):
            _delete_forecast_record(member_email, account_id, cached['forecastMonth'])
        return None, False

    # Outside the forecast window: no forecast, drop any stale record.
    if not invoice_forecast.is_in_forecast_window(now):
        if cached and cached.get('forecastMonth') and cached['forecastMonth'] != current_month:
            _delete_forecast_record(member_email, account_id, cached['forecastMonth'])
        return None, False

    # Fresh cache hit (Req 12.2).
    if cached and cached.get('forecastMonth') == current_month:
        return cached, False

    # Stale record present for a different month — drop before recompute (Req 12.3).
    if cached and cached.get('forecastMonth') and cached['forecastMonth'] != current_month:
        _delete_forecast_record(member_email, account_id, cached['forecastMonth'])

    # Recompute.
    try:
        record = invoice_forecast.compute_forecast(
            member_email, account_id, provider_key, now=now,
            latest_real_issuer=_latest_real_issuer(items),
        )
    except Exception as e:
        logger.warning(f"Forecast recompute failed for {account_id}: {e}")
        return None, True  # forecastUnavailable (Req 8.11, 12.4)

    if record is None:
        return None, False

    try:
        _write_forecast_record(member_email, account_id, record)
    except Exception as e:
        logger.warning(f"Forecast write failed for {account_id}: {e}")
    return record, False


def _synthesize_groundcover_service_breakdown(member_email, account_id, period):
    """Synthesize per-model service breakdown from USAGE# items in Cost_Cache_Table.

    Args:
        member_email: Member email (part of pk).
        account_id: GroundCover/Anthropic account ID.
        period: YYYY-MM period string.

    Returns:
        list of service dicts matching the canonical service-breakdown shape.
    """
    try:
        cache_table = dynamodb.Table(
            os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')
        )
        pk = f"{member_email}#{account_id}"
        start_sk = f"USAGE#{period}-01"
        end_sk = f"USAGE#{period}-31~"

        resp = cache_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('pk').eq(pk)
            & boto3.dynamodb.conditions.Key('sk').between(start_sk, end_sk)
        )
        usage_items = resp.get('Items', [])

        if not usage_items:
            return []

        # Aggregate by model
        model_costs = {}
        for u in usage_items:
            model = u.get('service', '') or 'Unknown Model'
            cost = float(u.get('cost_amount', 0) or 0)
            model_costs[model] = model_costs.get(model, 0) + cost

        total = sum(model_costs.values())
        services = []
        for model, cost in sorted(model_costs.items(), key=lambda x: -x[1]):
            if cost >= 0.001:
                services.append({
                    'serviceName': model,
                    'amount': round(cost, 4),
                    'percentage': round((cost / total) * 100, 1) if total > 0 else 0,
                    'region': 'global',
                })

        return services
    except Exception as e:
        logger.warning(f"GroundCover service breakdown synthesis failed for {account_id} period={period}: {e}")
        return []


def _synthesize_groundcover_resource_breakdown(member_email, account_id, period, service):
    """Synthesize per-user resource breakdown from USAGE# items for a specific model.

    Calculates per-user cost using model pricing rates ($/MTok) applied to token
    counts. GroundCover stores per-user token counts in USAGE# items but cost is
    only tracked at model-level aggregate. We compute: tokens × rate = cost.

    Args:
        member_email: Member email (part of pk).
        account_id: GroundCover/Anthropic account ID.
        period: YYYY-MM period string.
        service: Model name (e.g., 'claude-opus-4-8').

    Returns:
        list of resource dicts with per-user cost breakdown.
    """
    # Anthropic model pricing (USD per 1M tokens) - must stay in sync with
    # groundcover_connector.py MODEL_PRICING
    MODEL_PRICING = {
        'claude-opus-4': {'input': 5.0, 'output': 25.0},
        'claude-sonnet-4': {'input': 3.0, 'output': 15.0},
        'claude-sonnet-5': {'input': 3.0, 'output': 15.0},
        'claude-haiku-4': {'input': 1.0, 'output': 5.0},
        'claude-fable-5': {'input': 10.0, 'output': 50.0},
        'gemini-2.5-pro': {'input': 1.25, 'output': 10.0},
        'gemini-2.5-flash': {'input': 0.15, 'output': 0.60},
    }
    DEFAULT_PRICING = {'input': 3.0, 'output': 15.0}

    def _get_model_pricing(model_name):
        """Match model name to pricing using prefix matching."""
        model_lower = (model_name or '').lower()
        for prefix, pricing in MODEL_PRICING.items():
            if prefix in model_lower:
                return pricing
        return DEFAULT_PRICING

    def _estimate_cost(pricing, input_tok, output_tok, total_tok):
        """Estimate cost from tokens. If no input/output split, use blended rate."""
        if input_tok > 0 or output_tok > 0:
            return (input_tok * pricing['input'] + output_tok * pricing['output']) / 1_000_000
        # No input/output split available — use blended average rate
        blended_rate = (pricing['input'] + pricing['output']) / 2
        return (total_tok * blended_rate) / 1_000_000

    try:
        cache_table = dynamodb.Table(
            os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')
        )
        pk = f"{member_email}#{account_id}"
        start_sk = f"USAGE#{period}-01"
        end_sk = f"USAGE#{period}-31~"

        resp = cache_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('pk').eq(pk)
            & boto3.dynamodb.conditions.Key('sk').between(start_sk, end_sk)
        )
        usage_items = resp.get('Items', [])

        if not usage_items:
            return []

        # Get model pricing
        pricing = _get_model_pricing(service)

        # Filter for the specific model and aggregate by user (actor)
        user_data = {}  # {user: {tokens, input_tokens, output_tokens}}
        for u in usage_items:
            item_model = u.get('service', '') or ''
            if item_model != service:
                continue
            actor = u.get('actor', '') or 'unknown'
            tokens = int(float(u.get('usage_quantity', 0) or 0))
            input_tokens = int(float(u.get('input_tokens', 0) or 0))
            output_tokens = int(float(u.get('output_tokens', 0) or 0))

            if actor not in user_data:
                user_data[actor] = {'tokens': 0, 'input_tokens': 0, 'output_tokens': 0}
            user_data[actor]['tokens'] += tokens
            user_data[actor]['input_tokens'] += input_tokens
            user_data[actor]['output_tokens'] += output_tokens

        if not user_data:
            return []

        # Remove "unknown" placeholder if real users exist
        if 'unknown' in user_data and len(user_data) > 1 and user_data['unknown']['tokens'] == 0:
            del user_data['unknown']

        # Calculate cost per user using token × rate
        user_costs = {}
        for actor, data in user_data.items():
            cost = _estimate_cost(pricing, data['input_tokens'], data['output_tokens'], data['tokens'])
            user_costs[actor] = {
                'cost': round(cost, 4),
                'tokens': data['tokens'],
                'input_tokens': data['input_tokens'],
                'output_tokens': data['output_tokens'],
            }

        total_cost = sum(v['cost'] for v in user_costs.values())

        # Build resource records
        resources = []
        for actor, data in sorted(user_costs.items(), key=lambda x: -x[1]['cost']):
            cost = data['cost']
            if cost < 0.0001 and data['tokens'] == 0:
                continue

            pct = round((cost / total_cost) * 100, 1) if total_cost > 0 else 0

            # Build cost explanation showing the calculation
            if data['input_tokens'] > 0 or data['output_tokens'] > 0:
                explanation = (
                    f"Input: {data['input_tokens']:,} tok × ${pricing['input']}/MTok + "
                    f"Output: {data['output_tokens']:,} tok × ${pricing['output']}/MTok = ${cost:.2f}"
                )
            elif data['tokens'] > 0:
                blended = (pricing['input'] + pricing['output']) / 2
                explanation = (
                    f"{data['tokens']:,} tokens × ${blended:.1f}/MTok (blended) = ${cost:.2f}"
                )
            else:
                explanation = f"${cost:.2f}"

            resources.append({
                'resourceId': actor,
                'resourceName': actor,
                'resourceType': 'User',
                'amount': cost,
                'percentage': pct,
                'usageTypes': [
                    {
                        'type': 'Input Tokens',
                        'quantity': data['input_tokens'],
                        'unit': 'tokens',
                        'cost': round(data['input_tokens'] * pricing['input'] / 1_000_000, 4),
                    },
                    {
                        'type': 'Output Tokens',
                        'quantity': data['output_tokens'],
                        'unit': 'tokens',
                        'cost': round(data['output_tokens'] * pricing['output'] / 1_000_000, 4),
                    },
                ] if (data['input_tokens'] > 0 or data['output_tokens'] > 0) else [
                    {
                        'type': 'Tokens',
                        'quantity': data['tokens'],
                        'unit': 'tokens',
                        'cost': cost,
                    }
                ] if data['tokens'] > 0 else [],
                'explanation': explanation,
            })

        return resources
    except Exception as e:
        logger.warning(f"GroundCover resource breakdown synthesis failed for {account_id} period={period} service={service}: {e}")
        return []


def _read_service_cache(member_email, account_id, period):
    """Read cached service-level records from DynamoDB.

    Task 5.1: Query with pk = {email}#{accountId} and
    sk begins_with "{YYYY-MM}#". Check TTL validity.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.
        period: Billing period in YYYY-MM format.

    Returns:
        list[dict]: Cached service records sorted by cost desc, or empty list.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_epoch = int(time.time())

    try:
        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(f'{period}#'),
        )
    except ClientError as e:
        logger.error(f"DynamoDB cache read failed for services: {e}")
        return []

    # Filter by TTL validity
    valid_records = []
    for item in response.get('Items', []):
        ttl_val = int(item.get('ttl', 0))
        if ttl_val > now_epoch:
            record = _dynamo_item_to_service_dict(item)
            valid_records.append(record)

    if not valid_records:
        return []

    # Sort by cost descending
    valid_records.sort(key=lambda x: float(x.get('amount', 0)), reverse=True)
    return valid_records


def _write_service_cache(member_email, account_id, period, records):
    """Write service-level records to DynamoDB cache.

    Task 5.5: Write with sk = {YYYY-MM}#{serviceName}, include
    costExplanation, percentage, recordType="service", usageTypes.
    TTL = epoch + 90 days. Atomic write.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.
        period: Billing period in YYYY-MM format.
        records: List of normalized service record dicts.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_iso = datetime.now(timezone.utc).isoformat()
    ttl_epoch = int(time.time()) + TTL_SECONDS

    try:
        with table.batch_writer() as writer:
            for record in records:
                usage_types = _convert_to_decimal(record.get('usageTypes', []))

                item = {
                    'pk': pk,
                    'sk': f"{period}#{record['serviceName']}",
                    'recordType': 'service',
                    'service': record['serviceName'],
                    'month': period,
                    'cost': Decimal(str(record.get('amount', 0))),
                    'amount': Decimal(str(record.get('amount', 0))),
                    'currency': 'USD',
                    'percentage': Decimal(str(record.get('percentage', 0))),
                    'costExplanation': record.get('costExplanation', ''),
                    'usageTypes': usage_types,
                    'lastSyncedAt': now_iso,
                    'ttl': ttl_epoch,
                }
                writer.put_item(Item=item)
    except (ClientError, Exception) as e:
        logger.error(f"DynamoDB cache write failed for services: {e}")
        raise


def _read_resource_cache(member_email, account_id, period, service):
    """Read cached resource-level records from DynamoDB.

    Task 7.1: Query with pk = {email}#{accountId} and
    sk begins_with "RES#{YYYY-MM}#{serviceName}#". Check TTL validity.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.
        period: Billing period in YYYY-MM format.
        service: AWS service name.

    Returns:
        list[dict]: Cached resource records sorted by cost desc, or empty list.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    sk_prefix = f'RES#{period}#{service}#'
    now_epoch = int(time.time())

    try:
        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with(sk_prefix),
        )
    except ClientError as e:
        logger.error(f"DynamoDB cache read failed for resources: {e}")
        return []

    # Filter by TTL validity
    valid_records = []
    for item in response.get('Items', []):
        ttl_val = int(item.get('ttl', 0))
        if ttl_val > now_epoch:
            record = _dynamo_item_to_resource_dict(item)
            valid_records.append(record)

    if not valid_records:
        return []

    # Invalidate cache for EC2 services if records still have raw usage-type IDs
    # (indicates they were cached before the instance resolution feature)
    service_lower = (service or '').lower()
    is_ec2_service = 'elastic compute' in service_lower or 'ec2' in service_lower
    if is_ec2_service:
        has_unresolved = any(
            'BoxUsage:' in r.get('resourceId', '') or 'SpotUsage:' in r.get('resourceId', '')
            for r in valid_records
        )
        if has_unresolved:
            logger.info(f"Cache invalidated for {service} — contains unresolved usage-type IDs, re-fetching with instance resolution")
            return []

    # Sort by cost descending
    valid_records.sort(key=lambda x: float(x.get('amount', 0)), reverse=True)
    return valid_records
    """Write resource-level records to DynamoDB cache.

    Task 7.8: Write with sk = RES#{YYYY-MM}#{serviceName}#{resourceId}.
    Include all fields: resourceName, resourceType, costExplanation,
    aiExplanation, usageTypes. TTL = epoch + 90 days. Atomic write.

    Args:
        member_email: Member's email address.
        account_id: AWS account ID.
        period: Billing period in YYYY-MM format.
        service: AWS service name.
        records: List of normalized resource record dicts.
    """
    table = dynamodb.Table(INVOICES_TABLE_NAME)
    pk = f'{member_email}#{account_id}'
    now_iso = datetime.now(timezone.utc).isoformat()
    ttl_epoch = int(time.time()) + TTL_SECONDS

    try:
        with table.batch_writer() as writer:
            for record in records:
                usage_types = _convert_to_decimal(record.get('usageTypes', []))

                item = {
                    'pk': pk,
                    'sk': f"RES#{period}#{service}#{record['resourceId']}",
                    'recordType': 'resource',
                    'resourceId': record['resourceId'],
                    'resourceName': record.get('resourceName', record['resourceId']),
                    'resourceType': record.get('resourceType', 'Unknown'),
                    'service': service,
                    'period': period,
                    'amount': Decimal(str(record.get('amount', 0))),
                    'currency': 'USD',
                    'costExplanation': record.get('costExplanation', ''),
                    'aiExplanation': record.get('aiExplanation') or '',
                    'usageTypes': usage_types,
                    'lastSyncedAt': now_iso,
                    'ttl': ttl_epoch,
                }
                writer.put_item(Item=item)
    except (ClientError, Exception) as e:
        logger.error(f"DynamoDB cache write failed for resources: {e}")
        raise


# ─── Utility helpers ──────────────────────────────────────────────────────────

def _get_next_month_first_day(year, month):
    """Get the first day of the next month as YYYY-MM-DD string."""
    if month == 12:
        return f'{year + 1}-01-01'
    return f'{year}-{month + 1:02d}-01'


def _clamp_end_date_to_tomorrow(end_date, now=None):
    """Clamp a Cost Explorer end date so it is never in the future.

    Cost Explorer's GetCostAndUsage rejects a TimePeriod whose End is in the
    future. For a closed month the first-of-next-month end date is in the past
    and is returned unchanged. For the current (in-progress) month that end
    date is in the future, so it is clamped to tomorrow (UTC) — the same bound
    the dashboard monthly-trend fetch uses — which yields month-to-date (MTD)
    data instead of an error. This lets the Forecast invoice's drill-down show
    the current month's service breakdown, cost explanations, and savings tips.

    Args:
        end_date: Exclusive end date as 'YYYY-MM-DD'.
        now: Optional reference datetime (defaults to current UTC time).

    Returns:
        The original end_date, or tomorrow's date when end_date is later.
    """
    now = now or datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    return tomorrow if end_date > tomorrow else end_date


def _parse_usage_type(usage_type, service):
    """Parse an AWS usage type string into a human-readable name and type.

    Examples:
        "USW2-BoxUsage:t3.medium" → ("t3.medium instance", "EC2 Instance")
        "USW2-EBS:VolumeUsage.gp3" → ("gp3 volume", "EBS Volume")
        "USW2-DataTransfer-Out-Bytes" → ("Data Transfer Out", "Data Transfer")
        "USW2-NatGateway-Hours" → ("NAT Gateway", "Networking")
        "Requests-Tier1" → ("Standard Requests", "API Requests")

    Args:
        usage_type: Raw usage type string from Cost Explorer.
        service: AWS service name for context.

    Returns:
        tuple: (friendly_name, friendly_type)
    """
    ut = usage_type

    # Strip region prefix (e.g., "USW2-", "USE1-", "EUW1-")
    if '-' in ut and len(ut.split('-')[0]) <= 5 and ut.split('-')[0].isupper():
        ut = ut.split('-', 1)[1]

    # EC2 instance types
    if 'BoxUsage:' in ut:
        instance_type = ut.split('BoxUsage:')[-1]
        return (f'{instance_type} instance', 'EC2 Instance')
    if 'SpotUsage:' in ut:
        instance_type = ut.split('SpotUsage:')[-1]
        return (f'{instance_type} spot instance', 'EC2 Spot')

    # EBS volumes
    if 'EBS:VolumeUsage' in ut:
        vol_type = ut.split('.')[-1] if '.' in ut else 'gp2'
        return (f'{vol_type} volume storage', 'EBS Volume')
    if 'EBS:SnapshotUsage' in ut:
        return ('EBS Snapshots', 'EBS Snapshot')

    # Data transfer
    if 'DataTransfer' in ut:
        if 'Out' in ut:
            return ('Data Transfer Out', 'Data Transfer')
        elif 'In' in ut:
            return ('Data Transfer In', 'Data Transfer')
        return ('Data Transfer', 'Data Transfer')

    # NAT Gateway
    if 'NatGateway' in ut:
        if 'Hours' in ut:
            return ('NAT Gateway hours', 'Networking')
        if 'Bytes' in ut:
            return ('NAT Gateway data processed', 'Networking')
        return ('NAT Gateway', 'Networking')

    # Load Balancer
    if 'LoadBalancer' in ut or 'LCU' in ut:
        return ('Load Balancer', 'Networking')

    # RDS
    if 'RDS:' in ut or 'Aurora:' in ut:
        if 'InstanceUsage:' in ut:
            db_type = ut.split('InstanceUsage:')[-1]
            return (f'{db_type} database', 'RDS Instance')
        if 'StorageUsage' in ut:
            return ('RDS Storage', 'RDS Storage')
        if 'BackupUsage' in ut:
            return ('RDS Backups', 'RDS Backup')

    # S3
    if 'TimedStorage' in ut:
        return ('S3 Storage', 'S3 Storage')
    if 'Requests-Tier1' in ut or 'Requests-Tier2' in ut:
        tier = '1' if 'Tier1' in ut else '2'
        return (f'S3 Tier {tier} Requests', 'S3 Requests')

    # Lambda
    if 'Lambda-GB-Second' in ut:
        return ('Lambda compute (GB-seconds)', 'Lambda')
    if 'Lambda-Provisioned' in ut:
        return ('Lambda provisioned', 'Lambda')
    if 'Request' in ut and 'lambda' in service.lower():
        return ('Lambda invocations', 'Lambda')

    # CloudWatch
    if 'CW:' in ut or 'CloudWatch' in ut:
        return ('CloudWatch metrics/logs', 'Monitoring')

    # ElastiCache
    if 'NodeUsage:' in ut:
        node_type = ut.split('NodeUsage:')[-1]
        return (f'{node_type} cache node', 'ElastiCache')

    # DynamoDB
    if 'WriteCapacityUnit' in ut:
        return ('DynamoDB Write Capacity', 'DynamoDB')
    if 'ReadCapacityUnit' in ut:
        return ('DynamoDB Read Capacity', 'DynamoDB')
    if 'PayPerRequest' in ut:
        return ('DynamoDB On-Demand', 'DynamoDB')

    # Generic fallback: clean up the string
    # Remove common prefixes and make readable
    clean = ut.replace('-', ' ').replace('_', ' ').replace(':', ' - ')
    return (clean, 'Usage Type')


def _fetch_usage_type_breakdown(ce_client, creds, service, start_date, end_date, period, account_id=None):
    """Fallback: fetch usage-type-level breakdown when resource-level data is unavailable.

    Uses GetCostAndUsage with USAGE_TYPE grouping filtered by service.
    For EC2 BoxUsage types, resolves individual instance names by calling
    DescribeInstances and splits the aggregated cost across them.

    Args:
        ce_client: Cost Explorer boto3 client with cross-account credentials.
        creds: STS credentials dict (for metadata enrichment if needed).
        service: AWS service name.
        start_date: Period start (YYYY-MM-DD).
        end_date: Period end (YYYY-MM-DD).
        period: Billing period (YYYY-MM).

    Returns:
        tuple: (list[dict], list[str]) — resource records and warnings.
    """
    warnings = []

    try:
        response = ce_client.get_cost_and_usage(
            **apply_account_scope({
                'TimePeriod': {'Start': start_date, 'End': end_date},
                'Granularity': 'MONTHLY',
                'Metrics': ['UnblendedCost', 'UsageQuantity'],
                'Filter': {
                    'Dimensions': {
                        'Key': 'SERVICE',
                        'Values': [service],
                    }
                },
                'GroupBy': [
                    {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
                ],
            }, account_id)
        )
    except ClientError as e:
        logger.error(f"Usage-type fallback failed for {service}: {e}")
        raise

    # Collect raw usage-type data
    raw_items = []
    for period_result in response.get('ResultsByTime', []):
        for group in period_result.get('Groups', []):
            usage_type = group['Keys'][0] if group['Keys'] else 'Unknown'
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
            unit = group['Metrics'].get('UsageQuantity', {}).get('Unit', '')

            if abs(cost) < 0.01:
                continue

            raw_items.append({
                'usage_type': usage_type,
                'cost': cost,
                'quantity': quantity,
                'unit': unit,
            })

    # For EC2 services, resolve individual instance names
    is_ec2 = 'elastic compute' in service.lower() or 'ec2' in service.lower()
    instance_map = {}  # {instance_type: [{id, name, region}]}

    if is_ec2 and raw_items:
        instance_map = _resolve_ec2_instances(creds, raw_items)

    records = []
    for item in raw_items:
        usage_type = item['usage_type']
        cost = item['cost']
        quantity = item['quantity']
        unit = item['unit']

        # Check if this is a BoxUsage/SpotUsage type that we can split into individual instances
        instance_type_key = _extract_instance_type_from_usage(usage_type)

        if is_ec2 and instance_type_key and instance_type_key in instance_map:
            instances = instance_map[instance_type_key]
            if len(instances) > 0:
                # Split cost proportionally across instances (equal split)
                per_instance_cost = round(cost / len(instances), 2)
                per_instance_qty = round(quantity / len(instances), 4)

                for inst in instances:
                    inst_name = inst.get('name', inst.get('id', 'Unknown'))
                    inst_id = inst.get('id', usage_type)
                    inst_type = inst.get('type', instance_type_key)

                    usage_types_list = [{
                        'type': usage_type,
                        'cost': per_instance_cost,
                        'unit': unit,
                        'quantity': per_instance_qty,
                    }]

                    hourly_rate = round(cost / quantity, 4) if quantity > 0 else 0
                    hours = round(per_instance_qty, 1)
                    cost_explanation = f"{hours} Hrs × ${hourly_rate:.4f}/hr"

                    records.append({
                        'resourceId': inst_id,
                        'resourceName': inst_name,
                        'resourceType': f'EC2 Instance ({inst_type})',
                        'amount': per_instance_cost,
                        'costExplanation': cost_explanation,
                        'aiExplanation': None,
                        'usageTypes': usage_types_list,
                    })
                continue  # Skip the default record creation

        # Default: use usage type as a pseudo-resource (non-EC2 or unresolved)
        usage_types_list = [{
            'type': usage_type,
            'cost': round(cost, 2),
            'unit': unit,
            'quantity': round(quantity, 4),
        }]

        cost_explanation = generate_cost_explanation(usage_types_list)

        # Parse usage type into a friendly name and type
        friendly_name, friendly_type = _parse_usage_type(usage_type, service)

        records.append({
            'resourceId': usage_type,
            'resourceName': friendly_name,
            'resourceType': friendly_type,
            'amount': round(cost, 2),
            'costExplanation': cost_explanation,
            'aiExplanation': None,
            'usageTypes': usage_types_list,
        })

    records.sort(key=lambda x: x['amount'], reverse=True)
    return records, warnings


def _extract_instance_type_from_usage(usage_type):
    """Extract the EC2 instance type from a BoxUsage or SpotUsage usage type string.

    Examples:
        "EUC1-BoxUsage:r5.xlarge" → "r5.xlarge"
        "USW2-SpotUsage:c5.large" → "c5.large"
        "BoxUsage:t3.medium" → "t3.medium"
        "EUC1-EBS:VolumeUsage.gp3" → None (not an instance type)

    Returns:
        str or None: The instance type if found, else None.
    """
    if 'BoxUsage:' in usage_type:
        return usage_type.split('BoxUsage:')[-1]
    if 'SpotUsage:' in usage_type:
        return usage_type.split('SpotUsage:')[-1]
    return None


def _extract_region_from_usage(usage_type):
    """Extract the AWS region from a usage type prefix.

    Examples:
        "EUC1-BoxUsage:r5.xlarge" → "eu-central-1"
        "USW2-SpotUsage:c5.large" → "us-west-2"
        "BoxUsage:t3.medium" → None (no region prefix)

    Returns:
        str or None: The AWS region if a known prefix is found, else None.
    """
    PREFIX_TO_REGION = {
        'USE1': 'us-east-1', 'USE2': 'us-east-2', 'USW1': 'us-west-1', 'USW2': 'us-west-2',
        'EUC1': 'eu-central-1', 'EUW1': 'eu-west-1', 'EUW2': 'eu-west-2', 'EUW3': 'eu-west-3',
        'EUN1': 'eu-north-1', 'APS1': 'ap-southeast-1', 'APS2': 'ap-southeast-2',
        'APN1': 'ap-northeast-1', 'APN2': 'ap-northeast-2', 'APN3': 'ap-northeast-3',
        'SAE1': 'sa-east-1', 'CAN1': 'ca-central-1', 'MES1': 'me-south-1', 'MEC1': 'me-central-1',
        'AFS1': 'af-south-1', 'APS3': 'ap-south-1',
    }
    if '-' in usage_type:
        prefix = usage_type.split('-')[0]
        if prefix in PREFIX_TO_REGION:
            return PREFIX_TO_REGION[prefix]
    return None


def _resolve_ec2_instances(creds, raw_items):
    """Resolve EC2 instance names for BoxUsage/SpotUsage usage types.

    Calls DescribeInstances in the appropriate region(s) to find instances
    matching each instance type, then returns a map of instance_type → instances.

    Args:
        creds: STS credentials dict for cross-account access.
        raw_items: List of raw usage-type dicts with 'usage_type' key.

    Returns:
        dict: {instance_type: [{'id': str, 'name': str, 'type': str}]}
    """
    from botocore.config import Config

    # Collect all instance types and their regions
    type_regions = {}  # {instance_type: set(regions)}
    for item in raw_items:
        ut = item['usage_type']
        inst_type = _extract_instance_type_from_usage(ut)
        if inst_type:
            region = _extract_region_from_usage(ut) or 'eu-central-1'
            if inst_type not in type_regions:
                type_regions[inst_type] = set()
            type_regions[inst_type].add(region)

    if not type_regions:
        return {}

    timeout_config = Config(
        read_timeout=RESOURCE_TIMEOUT,
        connect_timeout=RESOURCE_TIMEOUT,
        retries={'max_attempts': 1},
    )

    result = {}  # {instance_type: [{id, name, type}]}

    # Group by region to minimize API calls
    region_types = {}  # {region: [instance_types]}
    for inst_type, regions in type_regions.items():
        for region in regions:
            if region not in region_types:
                region_types[region] = []
            region_types[region].append(inst_type)

    for region, instance_types in region_types.items():
        try:
            ec2_client = boto3.client(
                'ec2',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name=region,
                config=timeout_config,
            )

            # Query all instances of these types (running + stopped — they still incur costs if reserved)
            resp = ec2_client.describe_instances(
                Filters=[
                    {'Name': 'instance-type', 'Values': instance_types},
                    {'Name': 'instance-state-name', 'Values': ['running', 'stopped']},
                ],
            )

            found_count = 0
            for reservation in resp.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    iid = instance['InstanceId']
                    itype = instance.get('InstanceType', '')
                    name = iid  # default to instance ID
                    for tag in instance.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break

                    if itype not in result:
                        result[itype] = []
                    result[itype].append({
                        'id': iid,
                        'name': name,
                        'type': itype,
                    })
                    found_count += 1

            logger.info(f"EC2 instance resolution: region={region}, types={instance_types}, found={found_count} instances")

        except Exception as e:
            logger.warning(f"EC2 instance resolution failed for region {region}: {e}")
            # Continue with other regions — partial data is better than none

    return result


def _fetch_invoices_from_cost_explorer(creds, account_id):
    """Generate synthetic invoice records from Cost Explorer monthly aggregation.

    Args:
        creds: STS credentials dict.
        account_id: AWS account ID.

    Returns:
        list[dict]: Synthetic invoice records with source='cost_explorer_fallback'.
    """
    ce_client = boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',
    )

    now = datetime.now(timezone.utc)
    end_date = f'{now.year}-{now.month:02d}-01'
    start_year = now.year - 1
    start_month = now.month
    start_date = f'{start_year}-{start_month:02d}-01'

    logger.info(f"Cost Explorer fallback for {account_id}: {start_date} to {end_date}")

    try:
        # The invoice monthly total MUST match the dashboard "Monthly Cost by
        # Service" total, which is the source of truth. The dashboard sums
        # UnblendedCost across ALL services (with Tax appearing as its own
        # service line) using no RECORD_TYPE filter — see merged_monthly /
        # monthly_trend in lambda_function.handle_dashboard_data. Previously
        # this query excluded Tax (RECORD_TYPE != 'Tax'), which made invoice
        # monthly totals lower than the dashboard (e.g. Apr 2026 $99.85 vs the
        # dashboard's ~$117). Removing the filter includes all record types
        # (Usage, Tax, etc.) on the same UnblendedCost basis, so the per-month
        # invoice totalAmount is consistent with the dashboard monthly total.
        response = ce_client.get_cost_and_usage(
            **apply_account_scope({
                'TimePeriod': {'Start': start_date, 'End': end_date},
                'Granularity': 'MONTHLY',
                'Metrics': ['UnblendedCost'],
            }, account_id)
        )
    except ClientError as e:
        logger.error(f"Cost Explorer fallback failed for {account_id}: {e}")
        raise

    # Extract monthly totals (all services + Tax, matching the dashboard)
    monthly_totals = {}
    results_count = len(response.get('ResultsByTime', []))
    logger.info(f"Cost Explorer returned {results_count} periods for {account_id}")

    for period_result in response.get('ResultsByTime', []):
        period_start = period_result['TimePeriod']['Start']
        period_str = period_start[:7]

        # Ungrouped response has Total at the period level
        total = float(period_result.get('Total', {}).get('UnblendedCost', {}).get('Amount', 0))

        if period_str not in monthly_totals:
            monthly_totals[period_str] = 0.0
        monthly_totals[period_str] += total

    records = []
    for period_str, total in monthly_totals.items():

        if abs(total) < 0.01:
            continue

        invoice_id = f'{period_str}-monthly'

        year_val, month_val = int(period_str[:4]), int(period_str[5:7])
        if month_val == 12:
            pay_year, pay_month = year_val + 1, 1
        else:
            pay_year, pay_month = year_val, month_val + 1
        payment_date = f'{pay_year}-{pay_month:02d}-15'

        records.append({
            'invoiceId': invoice_id,
            'issuer': 'Amazon Web Services',
            'paymentDate': payment_date,
            'paymentStatus': 'paid',
            'totalAmount': round(total, 2),
            'currency': 'USD',
            'period': period_str,
            'source': 'cost_explorer_fallback',
        })

    return records


def _dynamo_item_to_dict(item):
    """Convert a DynamoDB invoice item to a plain dict with native types."""
    return {
        'invoiceId': str(item.get('invoiceId', '')),
        'issuer': str(item.get('issuer', 'Amazon Web Services')),
        'paymentDate': str(item.get('paymentDate', '')),
        'paymentStatus': str(item.get('paymentStatus', '')),
        'totalAmount': float(item.get('totalAmount', item.get('cost', 0))),
        'currency': str(item.get('currency', 'USD')),
        'period': str(item.get('period', '')),
        'source': str(item.get('source', '')),
        'accountId': str(item.get('accountId', 'N/A') or 'N/A'),
    }


def _dynamo_item_to_service_dict(item):
    """Convert a DynamoDB service item to a plain dict with native types."""
    service_name = str(item.get('service', ''))
    if not service_name:
        sk = str(item.get('sk', ''))
        parts = sk.split('#', 1)
        service_name = parts[1] if len(parts) > 1 else sk

    usage_types_raw = item.get('usageTypes', [])
    usage_types = []
    for ut in usage_types_raw:
        usage_types.append({
            'type': str(ut.get('type', '')),
            'cost': float(ut.get('cost', 0)),
            'unit': str(ut.get('unit', '')),
            'quantity': float(ut.get('quantity', 0)),
        })

    return {
        'serviceName': service_name,
        'amount': float(item.get('amount', item.get('cost', 0))),
        'percentage': float(item.get('percentage', 0)),
        'costExplanation': str(item.get('costExplanation', '')),
        'usageTypes': usage_types,
    }


def _dynamo_item_to_resource_dict(item):
    """Convert a DynamoDB resource item to a plain dict with native types."""
    usage_types_raw = item.get('usageTypes', [])
    usage_types = []
    for ut in usage_types_raw:
        usage_types.append({
            'type': str(ut.get('type', '')),
            'cost': float(ut.get('cost', 0)),
            'unit': str(ut.get('unit', '')),
            'quantity': float(ut.get('quantity', 0)),
        })

    ai_explanation = item.get('aiExplanation', '')
    if not ai_explanation:
        ai_explanation = None

    return {
        'resourceId': str(item.get('resourceId', '')),
        'resourceName': str(item.get('resourceName', '')),
        'resourceType': str(item.get('resourceType', 'Unknown')),
        'amount': float(item.get('amount', 0)),
        'costExplanation': str(item.get('costExplanation', '')),
        'aiExplanation': ai_explanation,
        'usageTypes': usage_types,
    }


def _convert_to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(round(obj, 4)))
    if isinstance(obj, list):
        return [_convert_to_decimal(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _convert_to_decimal(v) for k, v in obj.items()}
    return obj


# ─── Formatting utilities ─────────────────────────────────────────────────────

def format_currency(amount):
    """Format a numeric amount as a currency string.

    Returns a string with dollar sign, comma thousands separator, and
    2 decimal places. Negative amounts show minus before the dollar sign.

    Examples:
        format_currency(1234.56)   -> "$1,234.56"
        format_currency(-1234.56)  -> "-$1,234.56"
        format_currency(0)         -> "$0.00"
        format_currency(0.5)       -> "$0.50"
    """
    amount = float(amount)
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def format_date_display(iso_date):
    """Convert an ISO date string (YYYY-MM-DD) to human-readable format.

    Returns a string in "Mon DD, YYYY" format (e.g., "Jan 15, 2025").
    If parsing fails, returns the input unchanged.

    Examples:
        format_date_display("2025-01-15") -> "Jan 15, 2025"
        format_date_display("2024-12-03") -> "Dec 3, 2025"
        format_date_display("invalid")    -> "invalid"
    """
    try:
        dt = datetime.strptime(str(iso_date), '%Y-%m-%d')
        # Use %-d on Unix or %#d on Windows for day without leading zero;
        # for portability, use %d and strip the leading zero manually.
        day = dt.day
        return f"{dt.strftime('%b')} {day}, {dt.strftime('%Y')}"
    except (ValueError, TypeError):
        return iso_date
