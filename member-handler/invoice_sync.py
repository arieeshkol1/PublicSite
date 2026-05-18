"""
Invoice Explorer — Invoice Data Sync Service.

Fetches invoice data from customer AWS accounts via cross-account role
assumption and normalizes it into DynamoDB records for caching.

Uses the existing SlashMyBill-{AccountID} role pattern with ExternalId
derived from the member's email (SHA-256 hash).
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cost Explorer rate limit: 5 requests/second — we add a small delay
# between sequential calls to stay well within limits.
_CE_CALL_DELAY_SECONDS = 0.25

# Maximum retries for throttling errors with exponential backoff
_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0

# TTL: 90 days in seconds
_TTL_SECONDS = 90 * 24 * 60 * 60


def sync_invoice_data(member_email, account_id, months):
    """
    Fetch and cache invoice data for specified months.

    Uses STS AssumeRole to access the customer's AWS account via the
    existing SlashMyBill-{AccountID} role, then calls Cost Explorer
    GetCostAndUsage with SERVICE and DAILY granularity.

    Args:
        member_email: Authenticated member's email address.
        account_id: Target AWS account ID (12 digits).
        months: List of months to sync (YYYY-MM format), max 6.

    Returns:
        dict with keys:
            - synced_months: list of months successfully synced
            - record_count: total number of DynamoDB records written
            - total_cost: sum of all costs across synced months (float)

    Raises:
        InvoiceSyncError: When the sync fails entirely (STS failure,
            Cost Explorer not enabled, etc.)
    """
    if not months:
        return {'synced_months': [], 'record_count': 0, 'total_cost': 0.0}

    # Limit to 6 months per request (Requirement 7.1)
    months = months[:6]

    # Step 1: Assume cross-account role
    try:
        creds = _assume_role(member_email, account_id)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error'].get('Message', str(e))
        if error_code in ('AccessDenied', 'AccessDeniedException'):
            raise InvoiceSyncError(
                'STS AssumeRole failed — please re-deploy the CloudFormation template',
                status_code=403,
                error_type='AccessDenied'
            )
        raise InvoiceSyncError(
            f'Failed to access account {account_id}: {error_msg}',
            status_code=500,
            error_type='STSError'
        )

    # Step 2: Create Cost Explorer client with assumed credentials
    ce_client = boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',  # Cost Explorer is global, endpoint in us-east-1
    )

    # Step 3: Fetch data for each month sequentially (respecting rate limits)
    synced_months = []
    all_records = []
    total_cost = 0.0
    errors = []

    for month in months:
        try:
            records = _fetch_month_data(ce_client, member_email, account_id, month)
            all_records.extend(records)
            month_cost = sum(float(r['cost']) for r in records)
            total_cost += month_cost
            synced_months.append(month)
        except InvoiceSyncError:
            # Re-raise critical errors (Cost Explorer not enabled, etc.)
            raise
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error'].get('Message', str(e))

            # Cost Explorer not enabled — critical, abort all
            if 'not subscribed' in error_msg.lower() or 'not enabled' in error_msg.lower():
                raise InvoiceSyncError(
                    'Cost Explorer is not enabled for this account. '
                    'Please enable it in the AWS Billing Console.',
                    status_code=400,
                    error_type='CostExplorerNotEnabled'
                )

            # Throttling after retries exhausted — return 429 (Requirement 10.6)
            if error_code in ('LimitExceededException', 'ThrottlingException',
                              'RequestThrottled', 'TooManyRequestsException'):
                raise InvoiceSyncError(
                    'AWS rate limit reached after retries exhausted. Please try again shortly.',
                    status_code=429,
                    error_type='Throttled'
                )

            # For other errors, record the failure for this month
            logger.warning(
                f"Failed to fetch invoice data for {account_id} month={month}: "
                f"{error_code} - {error_msg}"
            )
            errors.append({'month': month, 'error': error_msg})
        except Exception as e:
            logger.warning(
                f"Unexpected error fetching invoice data for {account_id} month={month}: {e}"
            )
            errors.append({'month': month, 'error': str(e)})

        # Rate limit delay between months
        if month != months[-1]:
            time.sleep(_CE_CALL_DELAY_SECONDS)

    # Step 4: If no months succeeded, return error without storing anything
    if not synced_months:
        error_detail = errors[0]['error'] if errors else 'Unknown error'
        raise InvoiceSyncError(
            f'Failed to retrieve invoice data: {error_detail}',
            status_code=502,
            error_type='SyncFailed'
        )

    # Step 5: Write records to DynamoDB (only if we have data)
    if all_records:
        _write_records_to_dynamodb(all_records)

    result = {
        'synced_months': synced_months,
        'record_count': len(all_records),
        'total_cost': round(total_cost, 2),
    }

    # Include partial failure info if some months failed
    if errors:
        result['failed_months'] = errors

    return result


def _assume_role(member_email, account_id):
    """Assume the cross-account SlashMyBill role.

    Uses the same pattern as _assume_role_for_account in lambda_function.py:
    - Role ARN: arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}
    - ExternalId: SHA-256 hash of member email
    - Session name: SlashMyBillInvoiceSync

    Returns:
        dict with AccessKeyId, SecretAccessKey, SessionToken
    """
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts')
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SlashMyBillInvoiceSync',
        ExternalId=external_id,
    )
    return resp['Credentials']


def _fetch_month_data(ce_client, member_email, account_id, month):
    """Fetch Cost Explorer data for a single month.

    Makes two API calls:
    1. SERVICE granularity — service-level cost breakdown
    2. DAILY granularity — daily cost breakdown per service

    Args:
        ce_client: boto3 Cost Explorer client with assumed credentials
        member_email: Member's email for record keys
        account_id: AWS account ID
        month: Month string in YYYY-MM format

    Returns:
        List of normalized record dicts ready for DynamoDB storage
    """
    year, month_num = month.split('-')
    start_date = f'{year}-{month_num}-01'

    # Calculate end date (first day of next month)
    end_date = _get_next_month_first_day(int(year), int(month_num))

    # Call 1: Service-level costs (SERVICE granularity grouped by SERVICE)
    service_data = _call_cost_explorer_with_retry(
        ce_client,
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost', 'UsageQuantity'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    # Rate limit delay between calls
    time.sleep(_CE_CALL_DELAY_SECONDS)

    # Call 2: Daily costs grouped by service
    daily_data = _call_cost_explorer_with_retry(
        ce_client,
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    # Rate limit delay
    time.sleep(_CE_CALL_DELAY_SECONDS)

    # Call 3: Usage type breakdown per service (for usageTypes field)
    usage_type_data = _call_cost_explorer_with_retry(
        ce_client,
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost', 'UsageQuantity'],
        GroupBy=[
            {'Type': 'DIMENSION', 'Key': 'SERVICE'},
            {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
        ],
    )

    # Normalize into DynamoDB records
    now_iso = datetime.now(timezone.utc).isoformat()
    ttl_epoch = int(time.time()) + _TTL_SECONDS

    records = _normalize_records(
        service_data=service_data,
        daily_data=daily_data,
        usage_type_data=usage_type_data,
        member_email=member_email,
        account_id=account_id,
        month=month,
        synced_at=now_iso,
        ttl=ttl_epoch,
    )

    return records


def _call_cost_explorer_with_retry(ce_client, **kwargs):
    """Call GetCostAndUsage with exponential backoff on throttling.

    Retries up to 3 times with exponential backoff (1s, 2s, 4s)
    as specified in Requirement 10.6.

    Returns:
        The API response dict.

    Raises:
        ClientError: If all retries are exhausted or a non-throttling error occurs.
    """
    backoff = _INITIAL_BACKOFF_SECONDS

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = ce_client.get_cost_and_usage(**kwargs)
            return response
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ('LimitExceededException', 'ThrottlingException',
                              'RequestThrottled', 'TooManyRequestsException'):
                if attempt < _MAX_RETRIES:
                    logger.info(
                        f"Cost Explorer throttled (attempt {attempt + 1}/{_MAX_RETRIES + 1}), "
                        f"retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(
                        f"Cost Explorer throttled after {_MAX_RETRIES + 1} attempts, giving up"
                    )
            raise


def _normalize_records(service_data, daily_data, usage_type_data,
                       member_email, account_id, month, synced_at, ttl):
    """Normalize Cost Explorer responses into flat DynamoDB records.

    Creates one record per service with:
    - pk: {memberEmail}#{accountId}
    - sk: {YYYY-MM}#{serviceName}
    - cost: total cost for the service in this month
    - dailyCosts: {day: cost} map
    - usageTypes: [{type, cost, unit, quantity}] list
    """
    pk = f'{member_email}#{account_id}'

    # Parse service-level costs
    service_costs = {}
    for period in service_data.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            # Skip services with zero or negligible cost
            if abs(cost) < 0.005:
                continue
            service_costs[service_name] = round(cost, 2)

    # Parse daily costs per service
    daily_costs_by_service = {}
    for period in daily_data.get('ResultsByTime', []):
        day_str = period['TimePeriod']['Start']  # YYYY-MM-DD
        day_num = day_str.split('-')[2]  # Just the day part (e.g., "01")
        for group in period.get('Groups', []):
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            if service_name not in daily_costs_by_service:
                daily_costs_by_service[service_name] = {}
            if abs(cost) >= 0.005:
                daily_costs_by_service[service_name][day_num] = round(cost, 2)

    # Parse usage type breakdown per service
    usage_types_by_service = {}
    for period in usage_type_data.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            keys = group['Keys']
            service_name = keys[0]
            usage_type = keys[1] if len(keys) > 1 else 'Unknown'
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
            unit = group['Metrics'].get('UsageQuantity', {}).get('Unit', 'N/A')

            if abs(cost) < 0.005:
                continue

            if service_name not in usage_types_by_service:
                usage_types_by_service[service_name] = []
            usage_types_by_service[service_name].append({
                'type': usage_type,
                'cost': round(cost, 2),
                'unit': unit,
                'quantity': round(quantity, 4),
            })

    # Build final records — one per service that has non-zero cost
    records = []
    for service_name, cost in service_costs.items():
        record = {
            'pk': pk,
            'sk': f'{month}#{service_name}',
            'memberEmail': member_email,
            'accountId': account_id,
            'month': month,
            'service': service_name,
            'cost': Decimal(str(cost)),
            'currency': 'USD',
            'usageTypes': usage_types_by_service.get(service_name, []),
            'dailyCosts': daily_costs_by_service.get(service_name, {}),
            'region': 'global',  # CE doesn't provide region in this grouping
            'lastSyncedAt': synced_at,
            'ttl': ttl,
        }
        records.append(record)

    return records


def _write_records_to_dynamodb(records):
    """Write normalized invoice records to DynamoDB using BatchWriteItem.

    Handles batches of 25 items (DynamoDB limit) and retries on
    throttling errors.
    """
    import os
    table_name = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    # Convert any remaining float values in nested structures to Decimal
    def _convert_to_decimal(obj):
        if isinstance(obj, float):
            return Decimal(str(round(obj, 4)))
        if isinstance(obj, list):
            return [_convert_to_decimal(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _convert_to_decimal(v) for k, v in obj.items()}
        return obj

    # BatchWriteItem in chunks of 25
    batch_size = 25
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        with table.batch_writer() as writer:
            for record in batch:
                # Deep-convert nested structures
                item = {}
                for key, value in record.items():
                    item[key] = _convert_to_decimal(value)
                writer.put_item(Item=item)

        # Small delay between batches to avoid DynamoDB throttling
        if i + batch_size < len(records):
            time.sleep(0.1)


def _get_next_month_first_day(year, month):
    """Get the first day of the next month as YYYY-MM-DD string.

    Used to calculate the end date for Cost Explorer time periods.
    """
    if month == 12:
        return f'{year + 1}-01-01'
    return f'{year}-{month + 1:02d}-01'


class InvoiceSyncError(Exception):
    """Custom exception for invoice sync failures.

    Carries HTTP status code and error type for API response formatting.
    """

    def __init__(self, message, status_code=500, error_type='SyncError'):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
