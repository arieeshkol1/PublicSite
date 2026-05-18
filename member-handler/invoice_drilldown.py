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
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Module-level constants ───────────────────────────────────────────────────

INVOICES_TABLE_NAME = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')

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
PERIOD_REGEX = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
VALID_SORT_BY = ['paymentDate', 'amount', 'status']
VALID_SORT_ORDER = ['asc', 'desc']
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


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

    # Validate accountId
    validation_error = validate_account_id(account_id)
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

    # Task 4.1: Check DynamoDB cache first
    cached_records = _read_invoice_cache(member_email, account_id)

    if cached_records:
        items = cached_records
    else:
        # Task 4.2/4.4: Cache miss — fetch from AWS APIs
        try:
            items = fetch_invoice_list(member_email, account_id)
        except Exception as e:
            logger.error(f"Failed to fetch invoice list for {account_id}: {e}")
            return create_error_response(502, 'FetchError', f'Failed to retrieve invoice data: {str(e)}')

        # Task 4.3: Store fetched records in cache
        if items:
            _write_invoice_cache(member_email, account_id, items)

    # Apply sorting (default: paymentDate desc)
    effective_sort_by = sort_by or 'paymentDate'
    effective_sort_order = sort_order or 'desc'

    sort_key_map = {
        'paymentDate': lambda x: x.get('paymentDate', ''),
        'amount': lambda x: float(x.get('totalAmount', 0)),
        'status': lambda x: x.get('paymentStatus', ''),
    }
    sort_fn = sort_key_map.get(effective_sort_by, sort_key_map['paymentDate'])
    items = sorted(items, key=sort_fn, reverse=(effective_sort_order == 'desc'))

    # Apply pagination
    total_items = len(items)
    total_pages = math.ceil(total_items / page_size_int) if total_items > 0 else 0
    start_idx = (page_int - 1) * page_size_int
    end_idx = start_idx + page_size_int
    page_items = items[start_idx:end_idx]

    # Build response items (strip internal DynamoDB fields)
    response_items = []
    for item in page_items:
        response_items.append({
            'invoiceId': item.get('invoiceId', ''),
            'issuer': item.get('issuer', 'Amazon Web Services'),
            'paymentDate': item.get('paymentDate', ''),
            'paymentStatus': item.get('paymentStatus', ''),
            'totalAmount': float(item.get('totalAmount', 0)),
            'currency': item.get('currency', 'USD'),
            'period': item.get('period', ''),
        })

    return create_response(200, {
        'items': response_items,
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

    # Validate accountId
    validation_error = validate_account_id(account_id)
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
        response_services.append({
            'serviceName': svc.get('serviceName', ''),
            'amount': float(svc.get('amount', 0)),
            'percentage': float(svc.get('percentage', 0)),
            'costExplanation': svc.get('costExplanation', ''),
            'usageTypes': svc.get('usageTypes', []),
        })

    return create_response(200, {
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

    # Validate accountId
    validation_error = validate_account_id(account_id)
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
    cached_records = _read_resource_cache(member_email, account_id, period, service)

    if cached_records:
        resources = cached_records
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
        response_resources.append({
            'resourceId': r.get('resourceId', ''),
            'resourceName': r.get('resourceName', ''),
            'resourceType': r.get('resourceType', 'Unknown'),
            'amount': float(r.get('amount', 0)),
            'costExplanation': r.get('costExplanation', ''),
            'aiExplanation': r.get('aiExplanation'),
            'usageTypes': r.get('usageTypes', []),
        })

    return create_response(200, {
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

    # Validate accountId
    validation_error = validate_account_id(account_id)
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
        # Level 1: Invoice list
        invoice_records = fetch_invoice_list(member_email, account_id)
        if invoice_records:
            _write_invoice_cache(member_email, account_id, invoice_records)

        # Level 2: Service breakdown (only if period specified)
        if period:
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
    Fetch invoice-level metadata from AWS Invoicing API.

    Calls ListInvoiceSummaries via cross-account role assumption.
    Falls back to Cost Explorer monthly aggregation if the Invoicing API
    is unavailable or returns AccessDenied.

    Args:
        member_email: Authenticated member's email address.
        account_id: Target AWS account ID (12 digits).

    Returns:
        list[dict]: Normalized invoice records ready for DynamoDB storage.
    """
    creds = _assume_role(member_email, account_id)

    # Try AWS Invoicing API first
    try:
        invoicing_client = boto3.client(
            'invoicing',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name='us-east-1',
        )

        response = invoicing_client.list_invoice_summaries()
        invoices = response.get('InvoiceSummaries', [])

        records = []
        for inv in invoices:
            invoice_id = inv.get('InvoiceId', '')
            payment_date = inv.get('PaymentDate', inv.get('DueDate', ''))
            if hasattr(payment_date, 'isoformat'):
                payment_date = payment_date.strftime('%Y-%m-%d')
            elif 'T' in str(payment_date):
                payment_date = str(payment_date).split('T')[0]

            period = str(payment_date)[:7] if payment_date else ''
            total_amount = float(inv.get('TotalAmount', {}).get('Amount', 0))
            currency = inv.get('TotalAmount', {}).get('CurrencyCode', 'USD')
            payment_status = inv.get('PaymentStatus', 'paid').lower()
            if payment_status not in ('paid', 'pending', 'overdue'):
                payment_status = 'paid'

            records.append({
                'invoiceId': invoice_id,
                'issuer': inv.get('Issuer', 'Amazon Web Services'),
                'paymentDate': str(payment_date),
                'paymentStatus': payment_status,
                'totalAmount': round(total_amount, 2),
                'currency': currency,
                'period': period,
                'source': 'billing_api',
            })

        return records

    except (ClientError, Exception) as e:
        error_code = ''
        if isinstance(e, ClientError):
            error_code = e.response['Error']['Code']
        logger.info(
            f"Invoicing API unavailable for {account_id} ({error_code}), "
            f"falling back to Cost Explorer"
        )
        return _fetch_invoices_from_cost_explorer(creds, account_id)


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

    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
            ],
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

    # Call GetCostAndUsageWithResources with service filter
    try:
        response = ce_client.get_cost_and_usage_with_resources(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': [service],
                }
            },
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'RESOURCE_ID'},
            ],
        )
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error'].get('Message', '')
        # Handle "resource data not available" gracefully
        if 'ResourceNotAvailable' in error_code or 'not available' in error_msg.lower():
            warnings.append(
                'Resource-level data requires Cost Explorer hourly granularity to be enabled'
            )
            return [], warnings
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
                item = {
                    'pk': pk,
                    'sk': f"INV#{record['invoiceId']}",
                    'recordType': 'invoice',
                    'invoiceId': record['invoiceId'],
                    'issuer': record.get('issuer', 'Amazon Web Services'),
                    'paymentDate': record.get('paymentDate', ''),
                    'paymentStatus': record.get('paymentStatus', ''),
                    'totalAmount': Decimal(str(record.get('totalAmount', 0))),
                    'currency': record.get('currency', 'USD'),
                    'period': record.get('period', ''),
                    'source': record.get('source', ''),
                    'lastSyncedAt': now_iso,
                    'ttl': ttl_epoch,
                }
                writer.put_item(Item=item)
    except (ClientError, Exception) as e:
        logger.error(f"DynamoDB cache write failed for invoices: {e}")
        raise


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

    # Sort by cost descending
    valid_records.sort(key=lambda x: float(x.get('amount', 0)), reverse=True)
    return valid_records


def _write_resource_cache(member_email, account_id, period, service, records):
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

    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
        )
    except ClientError as e:
        logger.error(f"Cost Explorer fallback failed for {account_id}: {e}")
        raise

    records = []
    for period_result in response.get('ResultsByTime', []):
        period_start = period_result['TimePeriod']['Start']
        period_str = period_start[:7]
        total = float(period_result.get('Total', {}).get('UnblendedCost', {}).get('Amount', 0))

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
