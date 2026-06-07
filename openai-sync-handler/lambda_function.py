"""OpenAI Nightly Sync Lambda — incremental usage data fetch for all connected accounts.

Triggered daily at 02:00 UTC via EventBridge. Scans the Accounts table for
OpenAI connections with connectionStatus='connected', fetches incremental usage
data from the OpenAI Usage API, normalizes and caches it in Cost_Cache_Table.

Execution constraints:
- Lambda timeout: 900 seconds
- Memory: 256 MB
- Retry policy: 3 attempts with 2s base exponential backoff per account
- Invalid key (401): mark connectionStatus='failed', skip account
- Transient error (429/5xx): retry, then skip on exhaustion
"""
import os
import json
import time
import logging
import base64
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
COST_CACHE_TABLE_NAME = os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')
CREDENTIAL_KMS_KEY_ARN = os.environ.get('CREDENTIAL_KMS_KEY_ARN', '')

# Constants
OPENAI_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT = 30  # seconds per HTTP request
MAX_RETRIES = 3
NIGHTLY_SYNC_BACKOFF_BASE = 2.0  # seconds — base for exponential backoff
DEFAULT_FIRST_SYNC_DAYS = 90  # days to backfill on first sync
SK_PREFIX = 'OPENAI_DAILY#'

# Minimum remaining Lambda time to start processing another account (ms)
MIN_REMAINING_TIME_MS = 30_000  # 30 seconds safety margin

# DynamoDB resource (initialized once per Lambda container)
dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Sync OpenAI usage data for all connected accounts.

    Args:
        event: EventBridge scheduled event payload (not used).
        context: Lambda context object (provides get_remaining_time_in_millis()).

    Returns:
        Dict with sync results summary.
    """
    logger.info("OpenAI nightly sync started")
    start_time = time.time()

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    cache_table = dynamodb.Table(COST_CACHE_TABLE_NAME)

    # 1. Scan for all OpenAI accounts with connectionStatus='connected'
    openai_accounts = _scan_connected_openai_accounts(accounts_table)
    logger.info("Found %d connected OpenAI accounts to sync", len(openai_accounts))

    results = {
        'total_accounts': len(openai_accounts),
        'synced': 0,
        'failed': 0,
        'skipped_timeout': 0,
        'errors': [],
    }

    # 2. Process each account
    for account in openai_accounts:
        # Check remaining Lambda execution time
        remaining_ms = context.get_remaining_time_in_millis()
        if remaining_ms < MIN_REMAINING_TIME_MS:
            skipped_count = len(openai_accounts) - results['synced'] - results['failed']
            results['skipped_timeout'] = skipped_count
            logger.warning(
                "Lambda approaching timeout (%dms remaining). Skipping %d remaining accounts.",
                remaining_ms, skipped_count
            )
            break

        member_email = account.get('memberEmail', '')
        account_id = account.get('accountId', '')
        logger.info("Syncing account %s for %s", account_id, member_email)

        try:
            _sync_single_account(
                account=account,
                accounts_table=accounts_table,
                cache_table=cache_table,
            )
            results['synced'] += 1
            logger.info("Successfully synced account %s", account_id)
        except InvalidKeyError as e:
            # 401 — mark connection as failed, skip this account
            results['failed'] += 1
            results['errors'].append({
                'account_id': account_id,
                'member_email': member_email,
                'error': str(e),
                'type': 'invalid_key',
            })
            _update_connection_status(accounts_table, member_email, account_id, 'failed')
            logger.warning("Invalid API key for account %s: %s", account_id, e)
        except SyncTransientError as e:
            # Retries exhausted — mark sync failed, continue others
            results['failed'] += 1
            results['errors'].append({
                'account_id': account_id,
                'member_email': member_email,
                'error': str(e),
                'type': 'transient_exhausted',
            })
            logger.error("Sync failed for account %s after retries: %s", account_id, e)
        except Exception as e:
            # Unexpected error — log and continue to next account
            results['failed'] += 1
            results['errors'].append({
                'account_id': account_id,
                'member_email': member_email,
                'error': str(e)[:200],
                'type': 'unexpected',
            })
            logger.error("Unexpected error syncing account %s: %s", account_id, e)

    elapsed = time.time() - start_time
    logger.info(
        "OpenAI nightly sync complete: %d synced, %d failed, %d skipped (%.1fs elapsed)",
        results['synced'], results['failed'], results['skipped_timeout'], elapsed
    )
    return results


# ─── Custom Exceptions ────────────────────────────────────────────────────────


class InvalidKeyError(Exception):
    """Raised when OpenAI returns 401 indicating the API key is invalid/revoked."""
    pass


class SyncTransientError(Exception):
    """Raised when transient errors exhaust all retry attempts."""
    pass


# ─── Core Sync Logic ──────────────────────────────────────────────────────────


def _sync_single_account(account: dict, accounts_table, cache_table):
    """Sync usage data for a single OpenAI account.

    Steps:
    1. Determine date range (lastSyncedAt or 90 days back)
    2. Decrypt API key
    3. Fetch usage data from OpenAI with retries
    4. Normalize response
    5. Batch write to Cost_Cache_Table
    6. Update lastSyncedAt

    Raises:
        InvalidKeyError: If the API key is invalid (401).
        SyncTransientError: If retries are exhausted for transient errors.
    """
    member_email = account['memberEmail']
    account_id = account['accountId']

    # 1. Determine sync date range
    start_date, end_date = _compute_sync_date_range(account)
    logger.info(
        "Sync date range for %s: %s to %s", account_id, start_date, end_date
    )

    if start_date >= end_date:
        logger.info("Account %s already synced up to today, skipping.", account_id)
        return

    # 2. Decrypt API key
    encrypted_key = account.get('credentials', {}).get('encryptedApiKey', '')
    if not encrypted_key:
        raise InvalidKeyError("No encrypted API key found for account.")

    api_key = _decrypt_api_key(encrypted_key, member_email, account_id)

    # 3. Fetch usage data from OpenAI with retry
    raw_data = _fetch_openai_usage_with_retry(api_key, start_date, end_date)

    # 4. Normalize response
    normalized_records = _normalize_openai(raw_data, account_id)
    logger.info("Normalized %d records for account %s", len(normalized_records), account_id)

    # 5. Batch write to Cost_Cache_Table
    if normalized_records:
        _batch_write_cache(cache_table, member_email, account_id, normalized_records)

    # 6. Update lastSyncedAt
    now_iso = datetime.now(timezone.utc).isoformat()
    _update_last_synced(accounts_table, member_email, account_id, now_iso)


def _compute_sync_date_range(account: dict) -> tuple:
    """Compute start_date and end_date for the incremental sync.

    If lastSyncedAt is present, start from that date.
    Otherwise, backfill 90 days (first sync).

    Args:
        account: The account record from DynamoDB.

    Returns:
        Tuple of (start_date, end_date) as YYYY-MM-DD strings.
    """
    now = datetime.now(timezone.utc)
    end_date = now.strftime('%Y-%m-%d')

    last_synced_at = account.get('lastSyncedAt')
    if last_synced_at:
        # Parse ISO 8601 timestamp and extract date
        try:
            if 'T' in str(last_synced_at):
                synced_dt = datetime.fromisoformat(str(last_synced_at).replace('Z', '+00:00'))
            else:
                synced_dt = datetime.strptime(str(last_synced_at)[:10], '%Y-%m-%d').replace(
                    tzinfo=timezone.utc
                )
            start_date = synced_dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            # Fallback to 90 days if parsing fails
            start_date = (now - timedelta(days=DEFAULT_FIRST_SYNC_DAYS)).strftime('%Y-%m-%d')
    else:
        # First sync — backfill 90 days
        start_date = (now - timedelta(days=DEFAULT_FIRST_SYNC_DAYS)).strftime('%Y-%m-%d')

    return start_date, end_date


def _fetch_openai_usage_with_retry(api_key: str, start_date: str, end_date: str) -> list:
    """Fetch usage data from OpenAI Usage API with exponential backoff retry.

    Retries up to MAX_RETRIES times for transient errors (429, 5xx).
    Uses NIGHTLY_SYNC_BACKOFF_BASE (2s) for exponential backoff: 2s, 4s, 8s.

    Args:
        api_key: Decrypted OpenAI API key.
        start_date: ISO date string (YYYY-MM-DD).
        end_date: ISO date string (YYYY-MM-DD).

    Returns:
        List of raw usage records from OpenAI API.

    Raises:
        InvalidKeyError: If OpenAI returns 401 (invalid/revoked key).
        SyncTransientError: If all retries are exhausted.
    """
    url = f"{OPENAI_BASE_URL}/usage?start_date={start_date}&end_date={end_date}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                method='GET',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                }
            )
            response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
            data = json.loads(response.read().decode('utf-8'))
            # The usage API returns data in 'data' or 'results' key
            return data.get('data', data.get('results', [data] if 'object' in data else []))

        except urllib.error.HTTPError as e:
            status_code = e.code
            last_error = e

            if status_code == 401:
                # Invalid/revoked key — do NOT retry
                raise InvalidKeyError(
                    f"OpenAI API returned 401: API key is invalid or revoked."
                )

            if status_code == 429 or (500 <= status_code < 600):
                # Transient error — retry with exponential backoff
                if attempt < MAX_RETRIES - 1:
                    # Check Retry-After header for 429
                    wait_time = _compute_backoff_delay(attempt, e if status_code == 429 else None)
                    logger.info(
                        "OpenAI %d on attempt %d/%d for sync, waiting %.1fs",
                        status_code, attempt + 1, MAX_RETRIES, wait_time
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise SyncTransientError(
                        f"OpenAI API returned {status_code} after {MAX_RETRIES} attempts."
                    )

            # Other HTTP errors — non-retryable
            raise SyncTransientError(
                f"OpenAI API returned HTTP {status_code}."
            )

        except (urllib.error.URLError, OSError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait_time = _compute_backoff_delay(attempt)
                logger.info(
                    "Network error on attempt %d/%d for sync, waiting %.1fs: %s",
                    attempt + 1, MAX_RETRIES, wait_time, str(e)[:100]
                )
                time.sleep(wait_time)
                continue

    # All retries exhausted
    raise SyncTransientError(
        f"OpenAI Usage API unreachable after {MAX_RETRIES} attempts: {str(last_error)[:150]}"
    )


def _compute_backoff_delay(attempt: int, http_error=None) -> float:
    """Compute exponential backoff delay for retry.

    Uses NIGHTLY_SYNC_BACKOFF_BASE (2s): delays are 2s, 4s, 8s.
    If a Retry-After header is present, uses that instead.

    Args:
        attempt: Zero-based attempt number.
        http_error: Optional HTTPError to check for Retry-After header.

    Returns:
        Delay in seconds.
    """
    if http_error and hasattr(http_error, 'headers'):
        retry_after = http_error.headers.get('Retry-After')
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass

    return NIGHTLY_SYNC_BACKOFF_BASE * (2 ** attempt)


# ─── Data Normalization ───────────────────────────────────────────────────────


def _normalize_openai(raw_records: list, account_id: str) -> list:
    """Transform OpenAI Usage API response into common cost schema.

    OpenAI format (per bucket):
    {
        'object': 'bucket',
        'start_time': 1704067200,
        'end_time': 1704153600,
        'results': [
            {
                'object': 'organization.costs.result',
                'amount': {'value': 0.45, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_abc123',
                'input_tokens': 150000,
                'output_tokens': 45000
            }
        ]
    }

    Returns: list of dicts matching common schema.
    """
    normalized = []
    for bucket in raw_records:
        try:
            start_time = bucket.get('start_time')
            if start_time is None:
                logger.warning("Skipping OpenAI bucket with missing start_time")
                continue
            date = datetime.fromtimestamp(int(start_time), tz=timezone.utc).strftime('%Y-%m-%d')

            results = bucket.get('results', [])
            for result in results:
                try:
                    amount_obj = result.get('amount', {})
                    cost_value = float(amount_obj.get('value', 0))
                    currency = amount_obj.get('currency', 'usd').upper()

                    line_item = result.get('line_item', 'Unknown')
                    service_name = line_item.lower() if line_item else 'unknown'

                    input_tokens = result.get('input_tokens', 0)
                    output_tokens = result.get('output_tokens', 0)
                    project_id = result.get('project_id', None)

                    record = {
                        'date': date,
                        'service_name': service_name,
                        'cost_amount': round(cost_value, 4),
                        'currency': currency,
                        'cloud_provider': 'openai',
                        'account_id': account_id,
                        'input_tokens': int(input_tokens) if input_tokens else 0,
                        'output_tokens': int(output_tokens) if output_tokens else 0,
                    }
                    if project_id:
                        record['project_id'] = project_id

                    normalized.append(record)
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning("Skipping malformed OpenAI result: %s", e)
                    continue
        except (ValueError, TypeError, OSError) as e:
            logger.warning("Skipping malformed OpenAI bucket: %s", e)
            continue
    return normalized


# ─── Cache Writing ────────────────────────────────────────────────────────────


def _batch_write_cache(cache_table, member_email: str, account_id: str, normalized_records: list):
    """Batch write normalized records to Cost_Cache_Table.

    Groups records by date and writes one cache item per day with:
    - PK: {memberEmail}#{accountId}
    - SK: OPENAI_DAILY#YYYY-MM-DD
    - cost_amount: total daily cost
    - currency: USD
    - service_breakdown: {model: cost}
    - token_breakdown: {model: {input_tokens, output_tokens}}
    - project_breakdown: {project_id: {cost, name}}
    - fetched_at: ISO timestamp

    Args:
        cache_table: DynamoDB Table resource for Cost_Cache_Table.
        member_email: Member's email address.
        account_id: OpenAI account identifier.
        normalized_records: List of normalized cost records.
    """
    pk = f"{member_email}#{account_id}"
    fetched_at = datetime.now(timezone.utc).isoformat()

    # Group records by date
    daily_data = defaultdict(lambda: {
        'cost_amount': 0.0,
        'service_breakdown': defaultdict(float),
        'token_breakdown': defaultdict(lambda: {'input_tokens': 0, 'output_tokens': 0}),
        'project_breakdown': defaultdict(lambda: {'cost': 0.0, 'name': ''}),
    })

    for record in normalized_records:
        date_str = record.get('date', '')
        if not date_str:
            continue

        day = daily_data[date_str]
        cost = float(record.get('cost_amount', 0))
        model = record.get('service_name', 'unknown')

        day['cost_amount'] += cost
        day['service_breakdown'][model] += cost
        day['token_breakdown'][model]['input_tokens'] += int(record.get('input_tokens', 0))
        day['token_breakdown'][model]['output_tokens'] += int(record.get('output_tokens', 0))

        project_id = record.get('project_id')
        if project_id:
            day['project_breakdown'][project_id]['cost'] += cost

    # Batch write items
    try:
        with cache_table.batch_writer() as batch:
            for date_str, day in daily_data.items():
                # Convert floats to Decimal for DynamoDB
                service_breakdown = {
                    k: Decimal(str(round(v, 4)))
                    for k, v in day['service_breakdown'].items()
                }
                token_breakdown = {
                    k: {
                        'input_tokens': v['input_tokens'],
                        'output_tokens': v['output_tokens'],
                    }
                    for k, v in day['token_breakdown'].items()
                }
                project_breakdown = {
                    k: {
                        'cost': Decimal(str(round(v['cost'], 4))),
                        'name': v.get('name', ''),
                    }
                    for k, v in day['project_breakdown'].items()
                }

                item = {
                    'pk': pk,
                    'sk': f"{SK_PREFIX}{date_str}",
                    'cost_amount': Decimal(str(round(day['cost_amount'], 4))),
                    'currency': 'USD',
                    'service_breakdown': service_breakdown,
                    'token_breakdown': token_breakdown,
                    'fetched_at': fetched_at,
                }

                # Only include project_breakdown if there's data
                if project_breakdown:
                    item['project_breakdown'] = project_breakdown

                batch.put_item(Item=item)

        logger.info(
            "Wrote %d cache items for account %s", len(daily_data), account_id
        )
    except ClientError as e:
        logger.error("DynamoDB batch write failed for account %s: %s", account_id, e)
        raise


# ─── DynamoDB Helpers ─────────────────────────────────────────────────────────


def _scan_connected_openai_accounts(accounts_table) -> list:
    """Scan the Accounts table for OpenAI accounts with connectionStatus='connected'.

    Uses a filter expression to find all records where:
    - cloudProvider = 'openai'
    - connectionStatus = 'connected'

    Returns:
        List of account records (dicts).
    """
    accounts = []
    try:
        scan_kwargs = {
            'FilterExpression': (
                Attr('cloudProvider').eq('openai') &
                Attr('connectionStatus').eq('connected')
            ),
        }
        response = accounts_table.scan(**scan_kwargs)
        accounts.extend(response.get('Items', []))

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = accounts_table.scan(**scan_kwargs)
            accounts.extend(response.get('Items', []))

    except ClientError as e:
        logger.error("Failed to scan Accounts table: %s", e)
        raise

    return accounts


def _update_connection_status(accounts_table, member_email: str, account_id: str, status: str):
    """Update the connectionStatus field for an account.

    Args:
        accounts_table: DynamoDB Table resource.
        member_email: Member's email (PK).
        account_id: Account ID (SK).
        status: New connection status ('connected', 'failed', 'pending').
    """
    try:
        accounts_table.update_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            UpdateExpression='SET connectionStatus = :s',
            ExpressionAttributeValues={':s': status},
        )
        logger.info("Updated connectionStatus to '%s' for account %s", status, account_id)
    except ClientError as e:
        logger.error(
            "Failed to update connectionStatus for %s/%s: %s",
            member_email, account_id, e
        )


def _update_last_synced(accounts_table, member_email: str, account_id: str, timestamp: str):
    """Update the lastSyncedAt timestamp for an account after successful sync.

    Args:
        accounts_table: DynamoDB Table resource.
        member_email: Member's email (PK).
        account_id: Account ID (SK).
        timestamp: ISO 8601 timestamp string.
    """
    try:
        accounts_table.update_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            UpdateExpression='SET lastSyncedAt = :t',
            ExpressionAttributeValues={':t': timestamp},
        )
    except ClientError as e:
        logger.error(
            "Failed to update lastSyncedAt for %s/%s: %s",
            member_email, account_id, e
        )


# ─── KMS Decryption ──────────────────────────────────────────────────────────


def _decrypt_api_key(encrypted_key: str, member_email: str, account_id: str) -> str:
    """Decrypt an OpenAI API key using KMS with encryption context.

    Uses the same encryption context (memberEmail + accountId) that was used
    during encryption. Falls back to base64 decode if KMS key ARN is not set
    (dev mode only).

    Args:
        encrypted_key: Base64-encoded KMS ciphertext.
        member_email: Member's email (encryption context).
        account_id: Account identifier (encryption context).

    Returns:
        Decrypted plaintext API key.

    Raises:
        InvalidKeyError: If decryption fails (credentials inaccessible).
    """
    encryption_context = {
        'memberEmail': member_email,
        'accountId': account_id,
    }

    if not CREDENTIAL_KMS_KEY_ARN:
        # Dev mode fallback — decode base64
        try:
            return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
        except Exception:
            raise InvalidKeyError("Credentials inaccessible (dev mode decode failed).")

    try:
        kms_client = boto3.client('kms')
        ciphertext_blob = base64.b64decode(encrypted_key.encode('utf-8'))
        response = kms_client.decrypt(
            CiphertextBlob=ciphertext_blob,
            KeyId=CREDENTIAL_KMS_KEY_ARN,
            EncryptionContext=encryption_context,
        )
        plaintext = response['Plaintext'].decode('utf-8')
        logger.info("Successfully decrypted API key for account %s", account_id)
        return plaintext
    except Exception as e:
        logger.error("KMS decryption failed for account %s: %s", account_id, type(e).__name__)
        raise InvalidKeyError(
            "Credentials inaccessible. Please re-add your OpenAI connection."
        )
