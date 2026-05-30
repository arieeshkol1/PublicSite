"""Cache Service module for the Cost Data Cache feature.

This module provides the CacheService class that orchestrates cache reads,
writes, background refresh, and tenant isolation for cost data stored in
DynamoDB. It enforces strict tenant isolation by verifying account ownership
before any cache operation.

Only DAILY granularity is supported — monthly summaries are computed by
aggregating daily items at query time.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from cache_types import CacheResult, CostDataItem

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')

# TTL duration: 90 days in seconds
TTL_DURATION_SECONDS = 90 * 24 * 60 * 60  # 7,776,000 seconds


class ServiceUnavailableError(Exception):
    """Raised when both cache and Cost Explorer API are unavailable."""
    pass


class CacheService:
    """Manages cost data caching with tenant isolation.

    The CacheService enforces that all cache operations are scoped to the
    authenticated member's accounts. It verifies account ownership against
    the MemberPortal-Accounts table before reading from or writing to the
    Cost_Cache_Table.
    """

    def __init__(self, table_name: str, dynamodb_resource=None):
        """Initialize with DynamoDB table reference.

        Args:
            table_name: Name of the Cost_Cache_Table DynamoDB table.
            dynamodb_resource: Optional boto3 DynamoDB resource. If not
                provided, a default resource is created.
        """
        self._dynamodb = dynamodb_resource or boto3.resource('dynamodb')
        self._table = self._dynamodb.Table(table_name)
        self._table_name = table_name

    @staticmethod
    def _build_partition_key(member_id: str, account_id: str) -> str:
        """Construct the partition key for the Cost_Cache_Table.

        Args:
            member_id: The authenticated member's email address.
            account_id: The AWS account ID.

        Returns:
            Partition key in the format '{member_id}#{account_id}'.
        """
        return f"{member_id}#{account_id}"

    @staticmethod
    def _build_sort_key(date: str) -> str:
        """Construct the sort key for the Cost_Cache_Table.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            Sort key in the format 'DAILY#{date}'.
        """
        return f"DAILY#{date}"

    @staticmethod
    def _calculate_ttl(fetched_at: str) -> int:
        """Calculate the TTL expiry timestamp (90 days from fetched_at).

        Args:
            fetched_at: ISO 8601 timestamp string of when data was fetched.

        Returns:
            Unix epoch integer representing 90 days after fetched_at.
        """
        dt = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
        epoch = int(dt.timestamp())
        return epoch + TTL_DURATION_SECONDS

    def _verify_account_ownership(self, member_id: str, account_ids: list[str]) -> bool:
        """Verify that all given account IDs belong to the authenticated member.

        Queries the MemberPortal-Accounts table to retrieve the list of
        accounts owned by the member, then checks that every requested
        account_id is in that list.

        Args:
            member_id: The authenticated member's email address.
            account_ids: List of AWS account IDs to verify ownership for.

        Returns:
            True if all account_ids belong to the member.

        Raises:
            PermissionError: If any account_id does not belong to the member.
            RuntimeError: If the ownership check fails due to a DynamoDB error.
        """
        if not account_ids:
            return True

        accounts_table = self._dynamodb.Table(ACCOUNTS_TABLE_NAME)
        try:
            result = accounts_table.query(
                KeyConditionExpression=Key('memberEmail').eq(member_id),
                ProjectionExpression='accountId',
            )
            owned_ids = {item['accountId'] for item in result.get('Items', [])}
        except ClientError as e:
            logger.error(f"Failed to verify account ownership for {member_id}: {e}")
            raise RuntimeError('Failed to verify account ownership') from e

        for aid in account_ids:
            if aid not in owned_ids:
                logger.warning(
                    f"Cache lateral access attempt: {member_id} tried to access account {aid}"
                )
                raise PermissionError(
                    f'Account {aid} does not belong to member {member_id}'
                )

        return True

    @staticmethod
    def _generate_date_range(start_date: str, end_date: str) -> list[str]:
        """Generate all dates in the range [start_date, end_date).

        Args:
            start_date: Start date in YYYY-MM-DD format (inclusive).
            end_date: End date in YYYY-MM-DD format (exclusive).

        Returns:
            List of date strings in YYYY-MM-DD format.
        """
        from datetime import timedelta

        dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        while current < end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        return dates

    def get_cost_data(
        self,
        member_id: str,
        account_id: str,
        start_date: str,
        end_date: str,
        credentials: dict = None,
    ) -> CacheResult:
        """Read cost data from cache, fetch missing ranges if needed.

        Verifies account ownership before accessing the cache. Queries
        the Cost_Cache_Table for the requested date range using a between
        condition on the sort key. Handles DynamoDB pagination if results
        exceed 1MB. Computes cache_status by comparing requested dates
        against cached dates and populates missing_dates accordingly.

        Fallback logic (Requirement 9.1, 9.2, 9.3):
        - If DynamoDB read fails, falls back to direct CE API call.
        - If CE API times out, returns available cached data with partial_data=True.
        - If both are unavailable, raises a ServiceUnavailableError.

        Cache status logic:
        - "hit": All requested dates found in cache (no gaps).
        - "partial": Some dates found, some missing.
        - "miss": No dates found in cache.

        Args:
            member_id: The authenticated member's email address.
            account_id: The AWS account ID to retrieve cost data for.
            start_date: Start date in YYYY-MM-DD format (inclusive).
            end_date: End date in YYYY-MM-DD format (exclusive).
            credentials: Optional STS credentials for CE API calls.

        Returns:
            CacheResult with cached data and status information.

        Raises:
            PermissionError: If account_id does not belong to member_id.
            RuntimeError: If ownership verification fails.
            ServiceUnavailableError: If both cache and CE API are unavailable.
        """
        # Verify account ownership before any cache access
        self._verify_account_ownership(member_id, [account_id])

        logger.info(f"Cache read: member_id={member_id}, account_id={account_id}, range={start_date} to {end_date}")

        # Build the expected set of dates for the requested range
        requested_dates = set(self._generate_date_range(start_date, end_date))

        # Query cache for the requested date range
        pk = self._build_partition_key(member_id, account_id)
        start_sk = self._build_sort_key(start_date)
        end_sk = self._build_sort_key(end_date)

        dynamo_failed = False
        items = []

        try:
            # Initial query
            response = self._table.query(
                KeyConditionExpression=(
                    Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
                )
            )
            items = response.get('Items', [])

            # Handle DynamoDB pagination (results exceeding 1MB)
            while 'LastEvaluatedKey' in response:
                response = self._table.query(
                    KeyConditionExpression=(
                        Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
                    ),
                    ExclusiveStartKey=response['LastEvaluatedKey'],
                )
                items.extend(response.get('Items', []))

        except ClientError as e:
            logger.error(f"DynamoDB query failed for {pk}: {e}")
            dynamo_failed = True

        # If DynamoDB failed, fall back to direct CE API call
        if dynamo_failed:
            logger.info(f"Cache fallback: DynamoDB unavailable for {member_id}#{account_id}, attempting direct CE API call")
            if credentials:
                try:
                    from incremental_fetch_engine import IncrementalFetchEngine
                    from cache_types import DateRange

                    engine = IncrementalFetchEngine()
                    fetched_items = engine.fetch_cost_data(
                        [DateRange(start=start_date, end=end_date)],
                        credentials,
                    )
                    logger.info(f"Cache fallback: CE API returned {len(fetched_items)} items for {member_id}#{account_id}")
                    return CacheResult(
                        data=fetched_items,
                        cache_status='miss',
                        missing_dates=[],
                        partial_data=False,
                    )
                except Exception as ce_error:
                    logger.error(f"Cache fallback: CE API also failed for {member_id}#{account_id}: {ce_error}")
                    # Both DynamoDB and CE API unavailable
                    raise ServiceUnavailableError(
                        'Both cache and Cost Explorer API are temporarily unavailable'
                    ) from ce_error
            else:
                # No credentials provided and DynamoDB failed
                raise ServiceUnavailableError(
                    'Cache is temporarily unavailable and no credentials provided for fallback'
                )

        # Convert DynamoDB items to CostDataItem objects
        cached_items = []
        cached_dates = set()
        for item in items:
            date_str = item['sk'].replace('DAILY#', '')
            cached_dates.add(date_str)
            cached_items.append(CostDataItem(
                date=date_str,
                cost_amount=float(item.get('cost_amount', 0)),
                currency=item.get('currency', 'USD'),
                service_breakdown=item.get('service_breakdown', {}),
                fetched_at=item.get('fetched_at', ''),
            ))

        # Compute missing dates by comparing requested vs cached
        missing_dates = sorted(requested_dates - cached_dates)

        # Determine cache status based on date coverage
        if not requested_dates:
            cache_status = 'hit'
        elif not missing_dates:
            cache_status = 'hit'
            logger.info(f"Cache hit: member_id={member_id}, account_id={account_id}")
        elif len(missing_dates) == len(requested_dates):
            cache_status = 'miss'
            logger.info(f"Cache miss: member_id={member_id}, account_id={account_id}")
        else:
            cache_status = 'partial'
            logger.info(f"Cache partial: member_id={member_id}, account_id={account_id}, missing={len(missing_dates)} dates")

        # If there are missing dates and credentials are available, fetch them
        if missing_dates and credentials:
            try:
                from incremental_fetch_engine import IncrementalFetchEngine
                from cache_types import DateRange

                engine = IncrementalFetchEngine()
                gaps = engine.compute_gaps(start_date, end_date, cached_dates)
                if gaps:
                    fetched_items = engine.fetch_cost_data(gaps, credentials)
                    if fetched_items:
                        # Write fetched data to cache (non-blocking on failure)
                        self.write_cost_data(member_id, account_id, fetched_items)
                        # Merge results
                        cached_items = engine.merge_results(cached_items, fetched_items)
                        missing_dates = []
                        cache_status = 'hit' if not missing_dates else 'partial'
                        logger.info(f"Cache write: member_id={member_id}, account_id={account_id}, items={len(fetched_items)}")
            except Exception as ce_error:
                # CE API timeout/failure — return available cached data with partial_data=True
                logger.warning(
                    f"CE API failed during incremental fetch for {member_id}#{account_id}: {ce_error}"
                )
                return CacheResult(
                    data=cached_items,
                    cache_status='partial' if cached_items else 'miss',
                    missing_dates=missing_dates,
                    partial_data=True,
                )

        return CacheResult(
            data=cached_items,
            cache_status=cache_status,
            missing_dates=missing_dates,
            partial_data=False,
        )

    def write_cost_data(
        self,
        member_id: str,
        account_id: str,
        items: list[CostDataItem],
    ) -> bool:
        """Write fetched cost data items to cache using DynamoDB BatchWriteItem.

        Verifies account ownership before writing to the cache. Each day's
        cost data is written as a separate item with all required fields
        (pk, sk, cost_amount, currency, service_breakdown, fetched_at, ttl).

        Uses chunking to respect the DynamoDB BatchWriteItem 25-item limit.
        Retries unprocessed items with exponential backoff (max 3 retries).
        On failure, logs the error and returns False without raising — the
        caller can still return fetched data to the member.

        Args:
            member_id: The authenticated member's email address.
            account_id: The AWS account ID the cost data belongs to.
            items: List of CostDataItem objects to write to the cache.

        Returns:
            True if all items were written successfully, False if write failed.

        Raises:
            PermissionError: If account_id does not belong to member_id.
            RuntimeError: If ownership verification fails.
        """
        # Verify account ownership before any cache write
        self._verify_account_ownership(member_id, [account_id])

        if not items:
            return True

        logger.info(f"Cache write: member_id={member_id}, account_id={account_id}, items_count={len(items)}")
        pk = self._build_partition_key(member_id, account_id)

        # Chunk items into batches of 25 (DynamoDB BatchWriteItem limit)
        batch_size = 25
        all_success = True

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            put_requests = []

            for item in batch:
                fetched_at = item.fetched_at or datetime.now(timezone.utc).isoformat()
                ttl_value = self._calculate_ttl(fetched_at)

                put_requests.append({
                    'PutRequest': {
                        'Item': {
                            'pk': pk,
                            'sk': self._build_sort_key(item.date),
                            'cost_amount': str(item.cost_amount),
                            'currency': item.currency,
                            'service_breakdown': item.service_breakdown,
                            'fetched_at': fetched_at,
                            'ttl': ttl_value,
                        }
                    }
                })

            try:
                response = self._dynamodb.meta.client.batch_write_item(
                    RequestItems={self._table_name: put_requests}
                )
                # Handle unprocessed items with retry (up to 3 attempts)
                unprocessed = response.get('UnprocessedItems', {})
                retry_count = 0
                max_retries = 3
                while unprocessed.get(self._table_name) and retry_count < max_retries:
                    retry_count += 1
                    delay = 0.1 * (2 ** (retry_count - 1))  # Exponential backoff
                    time.sleep(delay)
                    logger.info(
                        f"Retrying {len(unprocessed[self._table_name])} unprocessed "
                        f"items for {pk} (attempt {retry_count}/{max_retries})"
                    )
                    response = self._dynamodb.meta.client.batch_write_item(
                        RequestItems=unprocessed
                    )
                    unprocessed = response.get('UnprocessedItems', {})

                if unprocessed.get(self._table_name):
                    logger.warning(
                        f"Unprocessed items remain after {max_retries} retries for {pk}: "
                        f"{len(unprocessed[self._table_name])} items"
                    )
                    all_success = False
            except ClientError as e:
                logger.error(
                    f"BatchWriteItem failed for {pk}: {e}"
                )
                all_success = False

        return all_success

    def invalidate(
        self,
        member_id: str,
        account_id: str,
        start_date: str = None,
        end_date: str = None,
    ) -> int:
        """Delete cached items for the given range.

        If start_date and end_date are provided, queries items in that date
        range and batch-deletes them. If no date range is specified, queries
        ALL items for the account (pk) and batch-deletes them.

        Verifies account ownership before performing any deletion. Uses
        Query to find items, then BatchWriteItem with DeleteRequest to
        remove them. Handles pagination in the query and respects the
        25-item BatchWriteItem limit.

        Args:
            member_id: The authenticated member's identifier.
            account_id: The AWS account ID.
            start_date: Optional start date for range deletion (YYYY-MM-DD, inclusive).
            end_date: Optional end date for range deletion (YYYY-MM-DD, exclusive).

        Returns:
            Count of deleted items.

        Raises:
            PermissionError: If account_id does not belong to member_id.
            RuntimeError: If ownership verification fails.
        """
        # Verify account ownership before any cache deletion
        self._verify_account_ownership(member_id, [account_id])

        logger.info(f"Cache invalidation: member_id={member_id}, account_id={account_id}, range={start_date} to {end_date}")
        pk = self._build_partition_key(member_id, account_id)

        # Query items to delete
        items_to_delete = []
        try:
            if start_date and end_date:
                # Delete items within the specified date range
                start_sk = self._build_sort_key(start_date)
                end_sk = self._build_sort_key(end_date)
                response = self._table.query(
                    KeyConditionExpression=(
                        Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
                    ),
                    ProjectionExpression='pk, sk',
                )
                items_to_delete.extend(response.get('Items', []))

                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = self._table.query(
                        KeyConditionExpression=(
                            Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
                        ),
                        ProjectionExpression='pk, sk',
                        ExclusiveStartKey=response['LastEvaluatedKey'],
                    )
                    items_to_delete.extend(response.get('Items', []))
            else:
                # Delete ALL items for this account (no date range filter)
                response = self._table.query(
                    KeyConditionExpression=Key('pk').eq(pk),
                    ProjectionExpression='pk, sk',
                )
                items_to_delete.extend(response.get('Items', []))

                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = self._table.query(
                        KeyConditionExpression=Key('pk').eq(pk),
                        ProjectionExpression='pk, sk',
                        ExclusiveStartKey=response['LastEvaluatedKey'],
                    )
                    items_to_delete.extend(response.get('Items', []))

        except ClientError as e:
            logger.error(f"Failed to query items for invalidation ({pk}): {e}")
            return 0

        if not items_to_delete:
            return 0

        # Batch delete items (respecting 25-item limit)
        deleted_count = 0
        batch_size = 25

        for i in range(0, len(items_to_delete), batch_size):
            batch = items_to_delete[i:i + batch_size]
            delete_requests = [
                {
                    'DeleteRequest': {
                        'Key': {'pk': item['pk'], 'sk': item['sk']}
                    }
                }
                for item in batch
            ]

            try:
                response = self._dynamodb.meta.client.batch_write_item(
                    RequestItems={self._table_name: delete_requests}
                )

                # Handle unprocessed items with retry
                unprocessed = response.get('UnprocessedItems', {})
                retry_count = 0
                max_retries = 3
                while unprocessed.get(self._table_name) and retry_count < max_retries:
                    retry_count += 1
                    delay = 0.1 * (2 ** (retry_count - 1))
                    time.sleep(delay)
                    logger.info(
                        f"Retrying {len(unprocessed[self._table_name])} unprocessed "
                        f"deletes for {pk} (attempt {retry_count}/{max_retries})"
                    )
                    response = self._dynamodb.meta.client.batch_write_item(
                        RequestItems=unprocessed
                    )
                    unprocessed = response.get('UnprocessedItems', {})

                # Count successfully deleted items
                remaining = len(unprocessed.get(self._table_name, []))
                deleted_count += len(batch) - remaining

                if remaining:
                    logger.warning(
                        f"Unprocessed deletes remain after {max_retries} retries for {pk}: "
                        f"{remaining} items"
                    )
            except ClientError as e:
                logger.error(f"BatchWriteItem (delete) failed for {pk}: {e}")
                # Continue with remaining batches

        logger.info(
            f"Cache invalidated for {pk}: {deleted_count} items deleted"
        )
        return deleted_count

    def delete_account_cache(
        self,
        member_id: str,
        account_id: str,
    ) -> int:
        """Delete ALL cached data for an account (used on disconnect).

        Queries all items with the partition key (no sort key filter) to
        retrieve both DAILY# cost items and META# metadata items. Then
        batch-deletes all found items using BatchWriteItem with DeleteRequest.

        This method does NOT verify ownership — it is called from
        handle_delete_account which already verified the member owns the
        account.

        Handles DynamoDB pagination for large result sets and respects the
        25-item BatchWriteItem limit by chunking delete requests.

        Args:
            member_id: The authenticated member's identifier.
            account_id: The AWS account ID to remove from cache.

        Returns:
            Count of deleted items.
        """
        pk = self._build_partition_key(member_id, account_id)
        logger.info(f"Cache delete_account_cache: member_id={member_id}, account_id={account_id}")
        deleted_count = 0

        try:
            # Query ALL items for this partition key (no sk filter)
            response = self._table.query(
                KeyConditionExpression=Key('pk').eq(pk),
                ProjectionExpression='pk, sk',
            )
            items = response.get('Items', [])

            # Handle pagination — keep querying until all items retrieved
            while 'LastEvaluatedKey' in response:
                response = self._table.query(
                    KeyConditionExpression=Key('pk').eq(pk),
                    ProjectionExpression='pk, sk',
                    ExclusiveStartKey=response['LastEvaluatedKey'],
                )
                items.extend(response.get('Items', []))

        except ClientError as e:
            logger.error(
                f"Failed to query items for deletion ({pk}): {e}"
            )
            return 0

        if not items:
            return 0

        # Batch delete in chunks of 25 (DynamoDB BatchWriteItem limit)
        batch_size = 25
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            delete_requests = [
                {
                    'DeleteRequest': {
                        'Key': {
                            'pk': item['pk'],
                            'sk': item['sk'],
                        }
                    }
                }
                for item in batch
            ]

            try:
                response = self._dynamodb.meta.client.batch_write_item(
                    RequestItems={self._table_name: delete_requests}
                )

                # Handle unprocessed items with exponential backoff
                unprocessed = response.get('UnprocessedItems', {})
                retry_count = 0
                max_retries = 3
                while unprocessed.get(self._table_name) and retry_count < max_retries:
                    retry_count += 1
                    delay = 0.1 * (2 ** (retry_count - 1))
                    time.sleep(delay)
                    logger.info(
                        f"Retrying {len(unprocessed[self._table_name])} unprocessed "
                        f"deletes for {pk} (attempt {retry_count}/{max_retries})"
                    )
                    response = self._dynamodb.meta.client.batch_write_item(
                        RequestItems=unprocessed
                    )
                    unprocessed = response.get('UnprocessedItems', {})

                # Count successfully deleted items
                unprocessed_count = len(unprocessed.get(self._table_name, []))
                deleted_count += len(batch) - unprocessed_count

                if unprocessed_count > 0:
                    logger.warning(
                        f"Unprocessed deletes remain after {max_retries} retries "
                        f"for {pk}: {unprocessed_count} items"
                    )

            except ClientError as e:
                logger.error(
                    f"BatchWriteItem (delete) failed for {pk}: {e}"
                )
                # Continue with remaining batches even if one fails

        logger.info(
            f"Deleted {deleted_count} cache items for account "
            f"{account_id} (member: {member_id})"
        )
        return deleted_count

    def should_background_refresh(
        self,
        member_id: str,
        account_id: str,
    ) -> bool:
        """Check if recent data is stale (>6h) and refresh not throttled.

        Returns True if the most recent 3 days' cached data has a
        fetched_at older than 6 hours AND no refresh has been triggered
        for this account in the last hour.

        Logic:
        1. Query the cache for the most recent 3 days' items.
        2. If no items exist for recent 3 days, data is considered stale.
        3. Find the oldest fetched_at among those items.
        4. If oldest fetched_at is more than 6 hours ago → stale.
        5. Check META#last_refresh item for rate limiting.
        6. If last_refresh_at is less than 1 hour ago → throttled.
        7. Return True only if stale AND not throttled.

        Args:
            member_id: The authenticated member's identifier.
            account_id: The AWS account ID.

        Returns:
            True if background refresh should be triggered.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        pk = self._build_partition_key(member_id, account_id)

        # Step 1: Query cache for the most recent 3 days
        today = now.strftime('%Y-%m-%d')
        three_days_ago = (now - timedelta(days=2)).strftime('%Y-%m-%d')

        start_sk = self._build_sort_key(three_days_ago)
        end_sk = self._build_sort_key(today)

        try:
            response = self._table.query(
                KeyConditionExpression=(
                    Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
                )
            )
            items = response.get('Items', [])
        except ClientError as e:
            logger.error(
                f"Failed to check staleness for {pk}: {e}"
            )
            # On error, don't trigger refresh to avoid cascading failures
            return False

        # Step 2: If no items exist for recent 3 days, data is stale
        if not items:
            is_stale = True
        else:
            # Step 3: Find the oldest fetched_at among recent items
            oldest_fetched_at = None
            for item in items:
                fetched_at_str = item.get('fetched_at', '')
                if not fetched_at_str:
                    # Item without fetched_at is considered infinitely stale
                    is_stale = True
                    break
                try:
                    fetched_at_dt = datetime.fromisoformat(
                        fetched_at_str.replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    # Unparseable timestamp — treat as stale
                    is_stale = True
                    break
                if oldest_fetched_at is None or fetched_at_dt < oldest_fetched_at:
                    oldest_fetched_at = fetched_at_dt
            else:
                # Step 4: Check if oldest fetched_at is more than 6 hours ago
                staleness_threshold = now - timedelta(hours=6)
                is_stale = oldest_fetched_at < staleness_threshold

        if not is_stale:
            return False

        # Step 5: Check META#last_refresh for rate limiting
        meta_sk = 'META#last_refresh'
        try:
            meta_response = self._table.get_item(
                Key={'pk': pk, 'sk': meta_sk}
            )
            meta_item = meta_response.get('Item')
        except ClientError as e:
            logger.error(
                f"Failed to check refresh throttle for {pk}: {e}"
            )
            # On error reading meta, don't trigger refresh
            return False

        # Step 6: If last_refresh_at is less than 1 hour ago → throttled
        if meta_item:
            last_refresh_str = meta_item.get('last_refresh_at', '')
            if last_refresh_str:
                try:
                    last_refresh_dt = datetime.fromisoformat(
                        last_refresh_str.replace('Z', '+00:00')
                    )
                    throttle_threshold = now - timedelta(hours=1)
                    if last_refresh_dt > throttle_threshold:
                        # Throttled — refresh was triggered less than 1 hour ago
                        return False
                except (ValueError, TypeError):
                    # Unparseable timestamp — allow refresh
                    pass

        # Step 7: Stale AND not throttled → trigger refresh
        return True

    def trigger_background_refresh(
        self,
        member_id: str,
        account_id: str,
        credentials: dict,
    ) -> None:
        """Non-blocking refresh of recent 3 days' data.

        Immediately updates the META#last_refresh item to enforce rate
        limiting, then spawns a daemon background thread that:
        1. Creates an IncrementalFetchEngine
        2. Computes the date range for the most recent 3 days
        3. Calls fetch_cost_data for those dates
        4. Calls write_cost_data to update the cache
        5. Logs any errors without raising

        The method returns immediately (non-blocking) so the member's
        current request is not delayed.

        Args:
            member_id: The authenticated member's identifier.
            account_id: The AWS account ID.
            credentials: STS credentials for CE API calls.
        """
        # Step 1: Update META#last_refresh item immediately
        pk = self._build_partition_key(member_id, account_id)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        ttl_value = int(now.timestamp()) + TTL_DURATION_SECONDS

        try:
            self._table.put_item(
                Item={
                    'pk': pk,
                    'sk': 'META#last_refresh',
                    'last_refresh_at': now_iso,
                    'ttl': ttl_value,
                }
            )
        except ClientError as e:
            logger.error(
                f"Failed to update META#last_refresh for {pk}: {e}"
            )
            # Continue anyway — the refresh itself may still succeed

        # Step 2: Spawn a daemon background thread for the actual refresh
        thread = threading.Thread(
            target=self._background_refresh_worker,
            args=(member_id, account_id, credentials),
            daemon=True,
        )
        thread.start()

    def _background_refresh_worker(
        self,
        member_id: str,
        account_id: str,
        credentials: dict,
    ) -> None:
        """Worker function that runs in a background thread to refresh cache.

        Fetches the most recent 3 days of cost data from the Cost Explorer
        API and writes it to the cache. Logs any errors without raising.

        Args:
            member_id: The authenticated member's identifier.
            account_id: The AWS account ID.
            credentials: STS credentials for CE API calls.
        """
        try:
            from incremental_fetch_engine import IncrementalFetchEngine

            engine = IncrementalFetchEngine()

            # Compute date range for the most recent 3 days
            today = datetime.now(timezone.utc).date()
            start_date = (today - timedelta(days=2)).isoformat()
            # End date is exclusive (CE API convention), so today + 1
            end_date = (today + timedelta(days=1)).isoformat()

            # Fetch cost data for the 3-day range
            from cache_types import DateRange
            date_ranges = [DateRange(start=start_date, end=end_date)]
            fetched_items = engine.fetch_cost_data(date_ranges, credentials)

            # Write fetched data to cache
            if fetched_items:
                self.write_cost_data(member_id, account_id, fetched_items)

            logger.info(
                f"Background refresh completed for {member_id}#{account_id}: "
                f"{len(fetched_items)} items refreshed"
            )
        except Exception as e:
            logger.error(
                f"Background refresh failed for {member_id}#{account_id}: {e}"
            )
