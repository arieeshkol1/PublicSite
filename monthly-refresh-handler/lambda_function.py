"""
Monthly Full Invoice Refresh Lambda.

Triggered by EventBridge on the 7th calendar day of each month at 04:00 UTC.
Performs a full invoice refresh for every member and every account:

  1. Rebuilds Real_Invoice records (including the just-Closed_Month that ended).
  2. Invalidates and rewrites the account's INV# invoice-list cache
     (recordType = "real").
  3. Recomputes the Current_Month Forecast_Invoice for AWS accounts and
     replaces FCST#{currentMonth} (or deletes it if no forecast is produced).

Each account is processed with try/except isolation so one failure does not
abort the run. All writes are deterministic upserts keyed by (pk, sk), so
repeated runs on the 7th converge to the same state (idempotent — Req 13.5).

Reuses invoice_drilldown (fetch + cache helpers) and invoice_forecast
(compute_forecast). These modules are packaged alongside this handler.
"""

import os
import time
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

import invoice_drilldown as idd
import invoice_forecast as fe

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ACCOUNTS_TABLE = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
INVOICES_TABLE = os.environ.get('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')
REGION = os.environ.get('AWS_REGION', 'us-east-1')

dynamodb = boto3.resource('dynamodb', region_name=REGION)


def lambda_handler(event, context):
    """EventBridge entry point. Scan all accounts and refresh each one with
    per-account failure isolation; return a run summary. (Req 13.1, 13.4, 13.5)"""
    logger.info("Monthly full refresh starting...")
    now = datetime.now(timezone.utc)

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE)
    all_accounts = []
    scan_kwargs = {'ProjectionExpression': 'memberEmail, accountId, cloudProvider'}
    while True:
        resp = accounts_table.scan(**scan_kwargs)
        all_accounts.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']

    logger.info(f"Found {len(all_accounts)} account(s) to refresh")

    results = []
    for account in all_accounts:
        member_email = account.get('memberEmail', '')
        account_id = account.get('accountId', '')
        provider_key = str(account.get('cloudProvider', '') or '')
        if not member_email or not account_id:
            continue
        try:
            results.append(_refresh_account_monthly(member_email, account_id, provider_key, now))
        except Exception as e:
            logger.error(f"Monthly refresh failed for {account_id}: {e}")
            results.append({'accountId': account_id, 'status': 'failed', 'error': str(e)})
        time.sleep(0.5)  # rate limit between accounts

    summary = _build_run_summary(results)
    logger.info(f"Monthly refresh complete: {summary}")
    return {'statusCode': 200, 'body': summary}


def _refresh_account_monthly(member_email, account_id, provider_key, now):
    """Rebuild real invoices, invalidate + rewrite INV#, and recompute the
    AWS forecast for a single account. (Req 13.2, 13.3)"""
    logger.info(f"Refreshing {account_id} for {member_email}")

    # 1. Rebuild Real_Invoice records (includes the just-closed month).
    records = idd.fetch_invoice_list(member_email, account_id)

    # 2. Invalidate prior INV# cache, then rewrite (recordType='real').
    _invalidate_invoice_cache(member_email, account_id)
    if records:
        idd._write_invoice_cache(member_email, account_id, records)

    # 3. Recompute the Current_Month forecast for AWS accounts.
    current_month = now.strftime('%Y-%m')
    if fe.is_aws_provider(provider_key):
        try:
            forecast = fe.compute_forecast(
                member_email, account_id, provider_key, now=now,
                latest_real_issuer=idd._latest_real_issuer(records),
            )
        except Exception as e:
            logger.warning(f"Forecast recompute failed for {account_id}: {e}")
            forecast = None

        # If a real invoice already covers the current month, no forecast.
        real_periods = {str(r.get('period', '')) for r in records if r.get('period')}
        if current_month in real_periods:
            forecast = None

        if forecast:
            idd._write_forecast_record(member_email, account_id, forecast)
        else:
            idd._delete_forecast_record(member_email, account_id, current_month)

    return {'accountId': account_id, 'status': 'succeeded'}


def _invalidate_invoice_cache(member_email, account_id):
    """Delete all INV# invoice-list records for an account before rewrite.
    (Req 13.3)"""
    table = dynamodb.Table(INVOICES_TABLE)
    pk = f'{member_email}#{account_id}'
    try:
        resp = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with('INV#'),
            ProjectionExpression='pk, sk',
        )
        items = resp.get('Items', [])
        while 'LastEvaluatedKey' in resp:
            resp = table.query(
                KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with('INV#'),
                ProjectionExpression='pk, sk',
                ExclusiveStartKey=resp['LastEvaluatedKey'],
            )
            items.extend(resp.get('Items', []))
        with table.batch_writer() as writer:
            for item in items:
                writer.delete_item(Key={'pk': item['pk'], 'sk': item['sk']})
    except ClientError as e:
        logger.warning(f"INV# cache invalidation failed for {account_id}: {e}")


def _build_run_summary(results):
    """Build the run summary: processed/succeeded/failed counts + failures.
    Invariant: succeeded + failed == processed. (Req 13.4)"""
    succeeded = sum(1 for r in results if r.get('status') == 'succeeded')
    failed = sum(1 for r in results if r.get('status') == 'failed')
    failures = [
        {'accountId': r.get('accountId', ''), 'error': r.get('error', '')}
        for r in results if r.get('status') == 'failed'
    ]
    return {
        'processed': len(results),
        'succeeded': succeeded,
        'failed': failed,
        'failures': failures,
    }
