"""
Daily Cost Cache Refresh + Invoice Sync Lambda.

Triggered by EventBridge at 03:00 UTC daily.
Scans all member accounts and refreshes:
1. Cost_Cache_Table — daily cost data with service_breakdown
2. MemberPortal-Invoices — per-service usage-type breakdowns

Uses STS AssumeRole to access each customer's AWS account.
"""

import os
import time
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ACCOUNTS_TABLE = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
CACHE_TABLE = os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')
INVOICES_TABLE = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
REGION = os.environ.get('AWS_REGION', 'us-east-1')

dynamodb = boto3.resource('dynamodb', region_name=REGION)


def lambda_handler(event, context):
    """Main entry point — refresh all accounts."""
    logger.info("Daily refresh starting...")

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE)

    # Scan all accounts
    all_accounts = []
    scan_kwargs = {'ProjectionExpression': 'memberEmail, accountId'}
    while True:
        resp = accounts_table.scan(**scan_kwargs)
        all_accounts.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']

    logger.info(f"Found {len(all_accounts)} account(s) to refresh")

    success_count = 0
    error_count = 0

    for account in all_accounts:
        member_email = account.get('memberEmail', '')
        account_id = account.get('accountId', '')
        if not member_email or not account_id:
            continue

        try:
            _refresh_account(member_email, account_id)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to refresh {account_id}: {e}")
            error_count += 1

        # Rate limit between accounts
        time.sleep(1)

    logger.info(f"Daily refresh complete: {success_count} succeeded, {error_count} failed")
    return {
        'statusCode': 200,
        'body': f'Refreshed {success_count}/{len(all_accounts)} accounts'
    }


def _refresh_account(member_email, account_id):
    """Refresh cost cache and invoice data for one account."""
    logger.info(f"Refreshing {account_id} for {member_email}")

    # AI vendor accounts (OpenAI, GroundCover, etc.) don't use STS AssumeRole.
    # Trigger their cache refresh via the member-handler Lambda asynchronously.
    if not account_id.isdigit():
        try:
            lambda_client = boto3.client('lambda', region_name=REGION)
            lambda_client.invoke(
                FunctionName='aws-bill-analyzer-member-api',
                InvocationType='Event',
                Payload=b'{"_cache_refresh_ai": true, "member_email": "' + member_email.encode() + b'", "account_id": "' + account_id.encode() + b'"}',
            )
            logger.info(f"Triggered async AI vendor refresh for {account_id}")
        except Exception as e:
            logger.warning(f"Failed to trigger AI vendor refresh for {account_id}: {e}")
        return

    # AWS accounts: Assume role
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts', region_name=REGION)
    try:
        assume_resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='DailyRefresh',
            ExternalId=external_id,
        )
        creds = assume_resp['Credentials']
    except ClientError as e:
        logger.warning(f"STS AssumeRole failed for {account_id}: {e}")
        raise

    # Create CE client with assumed credentials
    ce = boto3.client(
        'ce',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name='us-east-1',
    )

    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')

    # Refresh last 7 days of daily costs (to catch any late-arriving data)
    start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')

    try:
        _refresh_daily_cache(ce, member_email, account_id, start_date, today)
    except Exception as e:
        logger.error(f"Daily cache refresh failed for {account_id}: {e}")

    # Refresh current month invoice data
    current_month = now.strftime('%Y-%m')
    try:
        _refresh_invoices(ce, member_email, account_id, current_month)
    except Exception as e:
        logger.error(f"Invoice refresh failed for {account_id}: {e}")


def _refresh_daily_cache(ce, member_email, account_id, start_date, end_date):
    """Refresh Cost_Cache_Table with daily costs + service breakdown."""
    cache_table = dynamodb.Table(CACHE_TABLE)
    pk = f"{member_email}#{account_id}"

    # Get daily costs grouped by service
    resp = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    ttl_epoch = int(time.time()) + (90 * 24 * 60 * 60)  # 90 days

    with cache_table.batch_writer() as batch:
        for period in resp.get('ResultsByTime', []):
            date_str = period['TimePeriod']['Start']
            service_breakdown = {}
            total_cost = 0.0

            for group in period.get('Groups', []):
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                if cost > 0.001:
                    service_breakdown[service] = Decimal(str(round(cost, 4)))
                    total_cost += cost

            if total_cost > 0.001:
                batch.put_item(Item={
                    'pk': pk,
                    'sk': f'DAILY#{date_str}',
                    'cost_amount': Decimal(str(round(total_cost, 4))),
                    'currency': 'USD',
                    'service_breakdown': service_breakdown,
                    'refreshed_at': datetime.now(timezone.utc).isoformat(),
                    'ttl': ttl_epoch,
                })

    logger.info(f"  Cache refreshed: {start_date} to {end_date}")


def _refresh_invoices(ce, member_email, account_id, month):
    """Refresh MemberPortal-Invoices with service-level usage-type breakdowns."""
    invoices_table = dynamodb.Table(INVOICES_TABLE)
    pk = f"{member_email}#{account_id}"

    year, month_num = month.split('-')
    start_date = f'{year}-{month_num}-01'
    # End date = first day of next month
    if int(month_num) == 12:
        end_date = f'{int(year) + 1}-01-01'
    else:
        end_date = f'{year}-{int(month_num) + 1:02d}-01'

    # If end_date is in the future, use today+1
    today_plus_1 = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')
    if end_date > today_plus_1:
        end_date = today_plus_1

    time.sleep(0.3)

    # Get service-level costs
    svc_resp = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    time.sleep(0.3)

    # Get usage-type breakdown per service
    ut_resp = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost', 'UsageQuantity'],
        GroupBy=[
            {'Type': 'DIMENSION', 'Key': 'SERVICE'},
            {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'},
        ],
    )

    # Parse service costs
    service_costs = {}
    for period in svc_resp.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            svc = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            if abs(cost) >= 0.005:
                service_costs[svc] = round(cost, 2)

    # Parse usage types per service
    usage_types_by_svc = {}
    for period in ut_resp.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            keys = group['Keys']
            svc = keys[0]
            usage_type = keys[1] if len(keys) > 1 else 'Unknown'
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
            unit = group['Metrics'].get('UsageQuantity', {}).get('Unit', 'N/A')

            if abs(cost) < 0.005:
                continue

            if svc not in usage_types_by_svc:
                usage_types_by_svc[svc] = []
            usage_types_by_svc[svc].append({
                'type': usage_type,
                'cost': Decimal(str(round(cost, 2))),
                'unit': unit,
                'quantity': Decimal(str(round(quantity, 4))),
            })

    # Write records
    ttl_epoch = int(time.time()) + (90 * 24 * 60 * 60)
    now_iso = datetime.now(timezone.utc).isoformat()

    with invoices_table.batch_writer() as batch:
        for svc, cost in service_costs.items():
            batch.put_item(Item={
                'pk': pk,
                'sk': f'{month}#{svc}',
                'memberEmail': member_email,
                'accountId': account_id,
                'month': month,
                'service': svc,
                'cost': Decimal(str(cost)),
                'currency': 'USD',
                'usageTypes': usage_types_by_svc.get(svc, []),
                'lastSyncedAt': now_iso,
                'ttl': ttl_epoch,
            })

    logger.info(f"  Invoices refreshed: {month} ({len(service_costs)} services)")
