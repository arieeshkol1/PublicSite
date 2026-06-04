"""Cache-first cost data retrieval for AI chat queries.

This module provides the _get_cost_data_cached function that attempts to read
cost data from the Cost_Cache_Table (DynamoDB) before falling back to the live
AWS Cost Explorer API. This reduces latency for AI chat queries when cached data
is available.

Only applies to AWS accounts — Azure and GCP connectors manage their own caching.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

COST_CACHE_TABLE_NAME = os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')


def _get_cost_data_cached(
    member_email: str,
    account_id: str,
    credentials: dict,
    start_date: str,
    end_date: str,
) -> tuple[list, bool]:
    """Attempt to read cost data from Cost_Cache_Table first, fall back to live API.

    Queries the Cost_Cache_Table for cached daily cost items covering the
    requested date range. If the cache has full coverage (items for all dates
    in the range), the cached data is used and the live Cost Explorer API call
    is skipped. If the cache has no data or incomplete coverage, falls back to
    the live Cost Explorer API.

    If both the cache read and the live API fail, returns a partial response
    with an error indicator rather than failing the entire query.

    Only applies to AWS accounts.

    Args:
        member_email: The authenticated member's email address.
        account_id: The AWS account ID (12 digits).
        credentials: STS credentials dict with AccessKeyId, SecretAccessKey,
            SessionToken for the cross-account role.
        start_date: Start date in YYYY-MM-DD format (inclusive).
        end_date: End date in YYYY-MM-DD format (exclusive).

    Returns:
        Tuple of (cost_data_list, from_cache).
        - cost_data_list: List of dicts with keys 'service', 'cost_usd', 'period'
          representing cost breakdown by service, sorted descending by cost.
        - from_cache: True if data was served from cache, False if from live API.

        If both sources fail, returns a list with a single error indicator item
        and from_cache=False.
    """
    # Try cache first
    cache_data = _read_from_cache(member_email, account_id, start_date, end_date)
    if cache_data is not None:
        return cache_data, True

    # Cache miss or incomplete — fall back to live Cost Explorer API
    live_data = _fetch_from_cost_explorer(credentials, start_date, end_date)
    if live_data is not None:
        return live_data, False

    # Both failed — return partial response with error indicator
    logger.error(
        f"Both cache and live CE API failed for {account_id}, "
        f"range {start_date} to {end_date}"
    )
    return [{'service': '_error', 'cost_usd': 0, 'period': f'{start_date} to {end_date}',
             'error': 'Cost data unavailable from both cache and live API'}], False


def _read_from_cache(
    member_email: str,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list | None:
    """Query Cost_Cache_Table for cached daily cost items.

    Returns a cost_by_service list if cache has full coverage for the date range,
    or None if the cache is empty, incomplete, or read fails.

    Full coverage is defined as having at least (expected_days - 2) items,
    allowing for today and yesterday which may not yet be finalized.
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(COST_CACHE_TABLE_NAME)

        pk = f"{member_email}#{account_id}"
        start_sk = f"DAILY#{start_date}"
        end_sk = f"DAILY#{end_date}"

        response = table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
        )
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))

        if not items:
            logger.info(f"Cache miss: no items for {account_id} in range {start_date} to {end_date}")
            return None

        # Check coverage: compute expected days in the range
        expected_days = _count_days(start_date, end_date)
        # Allow 2-day grace (today + yesterday may not be finalized)
        min_required = max(1, expected_days - 2)

        if len(items) < min_required:
            logger.info(
                f"Cache incomplete for {account_id}: got {len(items)} items, "
                f"need at least {min_required} (expected {expected_days} days)"
            )
            return None

        # Cache has sufficient coverage — aggregate service costs
        service_totals: dict[str, float] = {}
        for item in items:
            service_breakdown = item.get('service_breakdown') or {}
            for svc, svc_cost in service_breakdown.items():
                service_totals[svc] = service_totals.get(svc, 0) + float(svc_cost)

        # Build cost_by_service list in the same format as _gather_account_data
        cost_by_service = sorted(
            [
                {
                    'service': svc,
                    'cost_usd': round(cost, 4),
                    'period': f"{start_date} to {end_date}",
                }
                for svc, cost in service_totals.items()
                if cost > 0
            ],
            key=lambda x: x['cost_usd'],
            reverse=True,
        )

        logger.info(
            f"Cache hit for {account_id}: {len(items)} items, "
            f"{len(cost_by_service)} services, range {start_date} to {end_date}"
        )
        return cost_by_service

    except ClientError as e:
        logger.warning(f"Cache read failed for {account_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected cache read error for {account_id}: {e}")
        return None


def _fetch_from_cost_explorer(
    credentials: dict,
    start_date: str,
    end_date: str,
) -> list | None:
    """Fetch cost data from the live AWS Cost Explorer API.

    Returns a cost_by_service list, or None if the API call fails.
    """
    try:
        ce = boto3.client(
            'ce',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name='us-east-1',
        )

        response = ce.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )

        service_costs = []
        for period in response.get('ResultsByTime', []):
            for group in period.get('Groups', []):
                svc = group['Keys'][0]
                cost_usd = float(group['Metrics']['UnblendedCost']['Amount'])
                if cost_usd > 0:
                    service_costs.append({
                        'service': svc,
                        'cost_usd': round(cost_usd, 4),
                        'period': f"{period['TimePeriod']['Start']} to {period['TimePeriod']['End']}",
                    })

        service_costs.sort(key=lambda x: x['cost_usd'], reverse=True)
        logger.info(f"Live CE API returned {len(service_costs)} services for range {start_date} to {end_date}")
        return service_costs

    except ClientError as e:
        logger.warning(f"Cost Explorer API call failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected Cost Explorer error: {e}")
        return None


def _count_days(start_date: str, end_date: str) -> int:
    """Count the number of days between start_date (inclusive) and end_date (exclusive)."""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    return max(0, (end - start).days)
