"""
Daily Cost Cache Refresh & Invoice Sync Lambda.

Triggered daily at 03:00 UTC via EventBridge. Scans all connected accounts
in MemberPortal-Accounts table and for each:
1. Refreshes cost cache (last 30 days daily data + service breakdown)
2. Syncs the latest invoice if not already cached

Execution constraints:
- Memory: 512 MB
- Timeout: 300s (5 min)
- Concurrency: 1 (avoid parallel CE calls hitting rate limits)
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment / Constants
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
COST_CACHE_TABLE_NAME = os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')
INVOICES_TABLE_NAME = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
PLATFORM_ACCOUNT_ID = '991105135552'

# Rate limiting: 5 CE API calls/sec max
CE_CALL_DELAY = 0.25

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Entry point — scan accounts and refresh cost cache + invoices."""
    logger.info(f"Daily refresh triggered: {json.dumps(event)}")

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    cache_table = dynamodb.Table(COST_CACHE_TABLE_NAME)
    invoices_table = dynamodb.Table(INVOICES_TABLE_NAME)

    # 1. Scan all connected AWS accounts
    accounts = _get_all_connected_accounts(accounts_table)
    logger.info(f"Found {len(accounts)} connected accounts to refresh")

    results = {
        'accounts_processed': 0,
        'cache_refreshed': 0,
        'cache_failed': 0,
        'invoices_synced': 0,
        'invoices_failed': 0,
    }

    for account in accounts:
        member_email = account['memberEmail']
        account_id = account['accountId']
        cloud_provider = account.get('cloudProvider', 'aws')

        # Only refresh AWS accounts (Azure/GCP/OpenAI have their own sync)
        if cloud_provider != 'aws':
            logger.info(f"Skipping {account_id} ({cloud_provider}) — not AWS")
            continue

        logger.info(f"Refreshing account {account_id} for {member_email}")
        results['accounts_processed'] += 1

        # 2. Refresh cost cache
        try:
            _refresh_cost_cache(member_email, account_id, cache_table)
            results['cache_refreshed'] += 1
        except Exception as e:
            logger.error(f"Cache refresh failed for {account_id}: {e}")
            results['cache_failed'] += 1

        # 3. Sync latest invoice
        try:
            _sync_latest_invoice(member_email, account_id, invoices_table)
            results['invoices_synced'] += 1
        except Exception as e:
            logger.error(f"Invoice sync failed for {account_id}: {e}")
            results['invoices_failed'] += 1

        # Brief pause between accounts to stay within CE rate limits
        time.sleep(1)

    logger.info(f"Daily refresh complete: {json.dumps(results)}")
    return {
        'statusCode': 200,
        'body': json.dumps(results),
    }


def _get_all_connected_accounts(accounts_table):
    """Scan MemberPortal-Accounts for all accounts with connectionStatus='connected'."""
    accounts = []
    scan_kwargs = {
        'FilterExpression': '#status = :connected',
        'ExpressionAttributeNames': {'#status': 'connectionStatus'},
        'ExpressionAttributeValues': {':connected': 'connected'},
        'ProjectionExpression': 'memberEmail, accountId, cloudProvider',
    }

    try:
        response = accounts_table.scan(**scan_kwargs)
        accounts.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = accounts_table.scan(**scan_kwargs)
            accounts.extend(response.get('Items', []))
    except ClientError as e:
        logger.error(f"Failed to scan accounts: {e}")

    return accounts


def _assume_role(account_id, member_email):
    """Assume cross-account role for Cost Explorer access."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts')
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='DailyRefresh',
        ExternalId=external_id,
    )
    return response['Credentials']


def _refresh_cost_cache(member_email, account_id, cache_table):
    """Fetch last 30 days of daily cost data and write to Cost_Cache_Table."""
    credentials = _assume_role(account_id, member_email)

    ce = boto3.client(
        'ce',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name='us-east-1',
    )

    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')

    # Fetch daily costs with service breakdown
    time.sleep(CE_CALL_DELAY)
    response = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': today},
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    pk = f"{member_email}#{account_id}"
    now_iso = now.isoformat()
    ttl_value = int(now.timestamp()) + (90 * 24 * 3600)  # 90 days TTL
    items_written = 0

    for period in response.get('ResultsByTime', []):
        date = period['TimePeriod']['Start']
        service_breakdown = {}
        total_cost = 0.0

        for group in period.get('Groups', []):
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            if cost > 0.001:
                service_breakdown[service_name] = str(round(cost, 4))
                total_cost += cost

        # Write to cache
        cache_table.put_item(
            Item={
                'pk': pk,
                'sk': f'DAILY#{date}',
                'cost_amount': str(round(total_cost, 4)),
                'service_breakdown': service_breakdown,
                'fetched_at': now_iso,
                'cached_at': now_iso,
                'ttl': ttl_value,
            }
        )
        items_written += 1

    logger.info(f"Cache refreshed for {account_id}: {items_written} daily records written")


def _sync_latest_invoice(member_email, account_id, invoices_table):
    """Sync the most recent month's invoice if not already cached."""
    now = datetime.now(timezone.utc)

    # Determine the latest closed month (previous month)
    first_of_this_month = now.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    invoice_month = last_month_end.strftime('%Y-%m')

    # Check if this invoice is already cached
    pk = f"{member_email}#{account_id}"
    sk = f"{invoice_month}-monthly"

    try:
        existing = invoices_table.get_item(
            Key={'pk': pk, 'sk': sk},
            ProjectionExpression='pk',
        )
        if existing.get('Item'):
            logger.info(f"Invoice {invoice_month} already synced for {account_id}")
            return
    except ClientError:
        pass  # If we can't check, try to sync anyway

    # Fetch invoice data from Cost Explorer
    credentials = _assume_role(account_id, member_email)
    ce = boto3.client(
        'ce',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name='us-east-1',
    )

    start_date = last_month_end.replace(day=1).strftime('%Y-%m-%d')
    end_date = first_of_this_month.strftime('%Y-%m-%d')

    time.sleep(CE_CALL_DELAY)
    response = ce.get_cost_and_usage(
        TimePeriod={'Start': start_date, 'End': end_date},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
    )

    # Calculate total and service breakdown
    services = []
    total_cost = 0.0
    for period in response.get('ResultsByTime', []):
        for group in period.get('Groups', []):
            service_name = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            if cost > 0.01:
                services.append({'service': service_name, 'cost': round(cost, 2)})
                total_cost += cost

    services.sort(key=lambda x: x['cost'], reverse=True)

    # Write invoice record
    ttl_value = int(now.timestamp()) + (365 * 24 * 3600)  # 1 year TTL
    payment_date = f"{last_month_end.replace(day=15).strftime('%Y-%m-%d')}"

    invoices_table.put_item(
        Item={
            'pk': pk,
            'sk': sk,
            'month': invoice_month,
            'invoiceId': sk,
            'issuedBy': 'Amazon Web Services',
            'paymentDate': payment_date,
            'status': 'Paid',
            'totalAmount': Decimal(str(round(total_cost, 2))),
            'currency': 'USD',
            'services': json.dumps(services[:20]),
            'synced_at': now.isoformat(),
            'ttl': ttl_value,
        }
    )

    logger.info(f"Invoice {invoice_month} synced for {account_id}: ${total_cost:.2f}")
