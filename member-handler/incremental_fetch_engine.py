"""Incremental Fetch Engine for the Cost Data Cache feature.

This module handles gap detection (identifying missing date ranges from cached data)
and fetching only the missing ranges from the AWS Cost Explorer API.

Only DAILY granularity is supported — no MONTHLY or HOURLY.
"""

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from cache_types import CostDataItem, DateRange

logger = logging.getLogger(__name__)

# Transient error codes that should trigger a retry
RETRYABLE_ERROR_CODES = frozenset({
    'ThrottlingException',
    'RequestLimitExceeded',
    'InternalError',
})

# Maximum number of tag values retained per tag key (by descending cost)
TOP_N_CAP_DEFAULT = 50

# Safe size threshold for DynamoDB item (350 KB out of 400 KB limit)
SIZE_LIMIT_BYTES = 350 * 1024


class IncrementalFetchEngine:
    """Determines missing date ranges and fetches only gaps from Cost Explorer."""

    def compute_gaps(
        self,
        requested_start: str,
        requested_end: str,
        cached_dates: set[str],
        include_today: bool = True,
    ) -> list[DateRange]:
        """Compute contiguous date ranges not present in cached_dates.

        Generates all dates in [requested_start, requested_end) range,
        removes dates that exist in cached_dates, and groups the remaining
        dates into minimal contiguous DateRange objects.

        If include_today is True and today's date falls within the requested
        range, today is always included in the gaps (even if it appears in
        cached_dates) to capture intra-day cost updates.

        Args:
            requested_start: Start date (inclusive) in YYYY-MM-DD format.
            requested_end: End date (exclusive) in YYYY-MM-DD format,
                matching AWS Cost Explorer API convention.
            cached_dates: Set of date strings (YYYY-MM-DD) already cached.
            include_today: If True, always include today's date in gaps
                when it falls within the requested range.

        Returns:
            Minimal list of contiguous DateRange objects covering uncached
            dates. Each DateRange has start (inclusive) and end (exclusive).
            Returns empty list if all dates are cached (and today is not
            in range or include_today is False).
        """
        start = date.fromisoformat(requested_start)
        end = date.fromisoformat(requested_end)

        if start >= end:
            return []

        today_str = date.today().isoformat()

        # Generate all dates in [start, end) that are missing from cache
        missing_dates: list[date] = []
        current = start
        while current < end:
            current_str = current.isoformat()
            is_missing = current_str not in cached_dates
            is_today_forced = (
                include_today and current_str == today_str
            )

            if is_missing or is_today_forced:
                missing_dates.append(current)

            current += timedelta(days=1)

        if not missing_dates:
            return []

        # Group missing dates into minimal contiguous DateRange objects
        gaps: list[DateRange] = []
        gap_start = missing_dates[0]
        prev = missing_dates[0]

        for i in range(1, len(missing_dates)):
            current_date = missing_dates[i]
            if (current_date - prev).days == 1:
                # Contiguous — extend the current gap
                prev = current_date
            else:
                # Non-contiguous — close current gap and start new one
                # End is exclusive, so add 1 day
                gaps.append(DateRange(
                    start=gap_start.isoformat(),
                    end=(prev + timedelta(days=1)).isoformat(),
                ))
                gap_start = current_date
                prev = current_date

        # Close the final gap
        gaps.append(DateRange(
            start=gap_start.isoformat(),
            end=(prev + timedelta(days=1)).isoformat(),
        ))

        return gaps

    def fetch_cost_data(
        self,
        date_ranges: list[DateRange],
        credentials: dict,
    ) -> list[CostDataItem]:
        """Fetch cost data from CE API for the given date ranges.

        Batches contiguous ranges into minimum API calls.
        Uses DAILY granularity only.
        Implements exponential backoff (max 3 retries) for transient errors.

        Args:
            date_ranges: List of DateRange objects to fetch.
            credentials: AWS credentials dict with AccessKeyId,
                SecretAccessKey, and SessionToken.

        Returns:
            List of CostDataItem objects for the fetched dates.

        Raises:
            ClientError: If a non-retryable AWS error occurs, or if
                retries are exhausted for a transient error.
        """
        if not date_ranges:
            return []

        # Batch contiguous ranges into minimum number of API calls
        batched_ranges = self._batch_contiguous_ranges(date_ranges)

        # Create CE client with provided credentials
        ce_client = boto3.client(
            'ce',
            aws_access_key_id=credentials.get('AccessKeyId'),
            aws_secret_access_key=credentials.get('SecretAccessKey'),
            aws_session_token=credentials.get('SessionToken'),
        )

        all_items: list[CostDataItem] = []

        # Extract account_id for size_guard logging (default "unknown" if not available)
        account_id = credentials.get('AccountId', credentials.get('account_id', 'unknown'))
        # Account ID to scope CE queries to (only when it's a real AWS account ID).
        scope_account_id = account_id if account_id and account_id != 'unknown' else None

        for batch_range in batched_ranges:
            response = self._call_ce_with_retry(ce_client, batch_range, account_id=scope_account_id)
            items = self._parse_ce_response(response)

            # Service-breakdown caching completes regardless of tag query outcomes
            all_items.extend(items)

            # Fetch multi-tag breakdowns for the same range
            try:
                all_tag_data = self._fetch_all_tag_breakdowns(ce_client, batch_range, credentials)
                if all_tag_data:
                    all_tag_data = self._apply_top_n_cap(all_tag_data)
                    all_tag_data = self._apply_size_guard(all_tag_data, account_id)
                    # Merge tag data into items by date: for each item, extract per-date dict for each tag key
                    for item in items:
                        item.tag_breakdown = {
                            tag_key: tag_dates.get(item.date, {})
                            for tag_key, tag_dates in all_tag_data.items()
                        }
            except Exception as e:
                logger.warning(f"Tag fetch failed for {batch_range.start}-{batch_range.end}: {e}")
                # Continue without tags — service data is still valid

        return all_items

    def _batch_contiguous_ranges(
        self, date_ranges: list[DateRange]
    ) -> list[DateRange]:
        """Merge contiguous or overlapping DateRange objects into minimal set.

        Two ranges are contiguous if one's end equals the other's start.

        Args:
            date_ranges: List of DateRange objects (may be unsorted).

        Returns:
            Minimal list of merged DateRange objects sorted by start date.
        """
        if not date_ranges:
            return []

        # Sort by start date
        sorted_ranges = sorted(date_ranges, key=lambda r: r.start)

        merged: list[DateRange] = [
            DateRange(start=sorted_ranges[0].start, end=sorted_ranges[0].end)
        ]

        for current in sorted_ranges[1:]:
            last = merged[-1]
            # Contiguous: last.end == current.start, or overlapping: last.end >= current.start
            if last.end >= current.start:
                # Extend the merged range if current extends further
                if current.end > last.end:
                    merged[-1] = DateRange(start=last.start, end=current.end)
            else:
                merged.append(DateRange(start=current.start, end=current.end))

        return merged

    def _call_ce_with_retry(
        self,
        ce_client,
        date_range: DateRange,
        max_retries: int = 3,
        base_delay: float = 0.1,
        account_id: str = None,
    ) -> dict:
        """Call Cost Explorer GetCostAndUsage with exponential backoff.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            max_retries: Maximum number of retry attempts (default 3).
            base_delay: Base delay in seconds for backoff (default 0.1).
            account_id: Connected AWS account ID. When provided, the query is
                scoped to that LINKED_ACCOUNT so a payer/management-account
                connection returns only this account's costs (not the org's).

        Returns:
            The CE API response dict.

        Raises:
            ClientError: If a non-retryable error occurs, or if retries
                are exhausted.
        """
        from ce_account_scope import apply_account_scope
        params = apply_account_scope({
            'TimePeriod': {
                'Start': date_range.start,
                'End': date_range.end,
            },
            'Granularity': 'DAILY',
            'Metrics': ['UnblendedCost'],
            'GroupBy': [
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE',
                }
            ],
        }, account_id)
        for attempt in range(max_retries + 1):
            try:
                response = ce_client.get_cost_and_usage(**params)
                return response
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in RETRYABLE_ERROR_CODES and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Transient CE API error '%s' on attempt %d/%d, "
                        "retrying in %.2fs",
                        error_code,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise

    def _parse_ce_response(self, response: dict) -> list[CostDataItem]:
        """Parse Cost Explorer GetCostAndUsage response into CostDataItem objects.

        Each ResultsByTime period produces one CostDataItem with the total
        cost and a service_breakdown dict.

        Args:
            response: The raw CE API response dict.

        Returns:
            List of CostDataItem objects, one per day in the response.
        """
        items: list[CostDataItem] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        results_by_time = response.get('ResultsByTime', [])

        for period in results_by_time:
            period_start = period['TimePeriod']['Start']
            groups = period.get('Groups', [])

            service_breakdown: dict[str, float] = {}
            total_cost = 0.0

            for group in groups:
                service_name = group['Keys'][0]
                amount_str = group['Metrics']['UnblendedCost']['Amount']
                amount = float(amount_str)
                service_breakdown[service_name] = amount
                total_cost += amount

            # Determine currency from first group, default to USD
            currency = 'USD'
            if groups:
                currency = groups[0]['Metrics']['UnblendedCost'].get('Unit', 'USD')

            items.append(CostDataItem(
                date=period_start,
                cost_amount=round(total_cost, 10),
                currency=currency,
                service_breakdown=service_breakdown,
                fetched_at=now_iso,
            ))

        return items

    def _call_ce_by_tag(
        self,
        ce_client,
        date_range: DateRange,
        max_retries: int = 3,
        base_delay: float = 0.1,
    ) -> dict:
        """Call Cost Explorer GetCostAndUsage grouped by TAG keys.

        Fetches cost data grouped by all active cost allocation tags.
        Uses the same exponential backoff retry logic as the service call.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            max_retries: Maximum number of retry attempts (default 3).
            base_delay: Base delay in seconds for backoff (default 0.1).

        Returns:
            The CE API response dict grouped by TAG.

        Raises:
            ClientError: If a non-retryable error occurs, or if retries
                are exhausted.
        """
        # First, try to get active cost allocation tags
        tag_key = self._get_primary_tag_key(ce_client, date_range)

        for attempt in range(max_retries + 1):
            try:
                response = ce_client.get_cost_and_usage(
                    TimePeriod={
                        'Start': date_range.start,
                        'End': date_range.end,
                    },
                    Granularity='DAILY',
                    Metrics=['UnblendedCost'],
                    GroupBy=[
                        {
                            'Type': 'TAG',
                            'Key': tag_key,
                        }
                    ],
                )
                return response
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in RETRYABLE_ERROR_CODES and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Transient CE API error '%s' on tag fetch attempt %d/%d, "
                        "retrying in %.2fs",
                        error_code,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise

    def _get_primary_tag_key(self, ce_client, date_range: DateRange) -> str:
        """Get the primary cost allocation tag key to group by.

        Attempts to list active cost allocation tags. If multiple are found,
        uses the first one. Falls back to 'Environment' if the API call fails
        or returns no tags.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange for context (used for tag lookup).

        Returns:
            Tag key string to use for GroupBy.
        """
        try:
            # Use get_tags to discover available tag keys in the date range
            response = ce_client.get_tags(
                TimePeriod={
                    'Start': date_range.start,
                    'End': date_range.end,
                },
            )
            tags = response.get('Tags', [])
            if tags:
                # Return the first available tag key
                return tags[0]
        except Exception as e:
            logger.warning(f"Failed to list tag keys, falling back to 'Environment': {e}")

        return 'Environment'

    def _parse_tag_response(self, response: dict) -> dict[str, dict[str, float]]:
        """Parse Cost Explorer tag-grouped response into date-keyed tag breakdown.

        Each ResultsByTime period produces a mapping of tag values to costs.
        The keys in the returned dict are "tagKey=tagValue" format.

        Args:
            response: The raw CE API response dict (grouped by TAG).

        Returns:
            Dict mapping date (YYYY-MM-DD) to {tag_key=tag_value: cost_amount}.
            Empty tag values are stored as "tagKey=(untagged)".
        """
        tag_data: dict[str, dict[str, float]] = {}

        results_by_time = response.get('ResultsByTime', [])

        for period in results_by_time:
            period_start = period['TimePeriod']['Start']
            groups = period.get('Groups', [])

            tag_breakdown: dict[str, float] = {}

            for group in groups:
                # Keys format is ["tagKey$tagValue"] or ["tagValue"]
                raw_key = group['Keys'][0]
                amount_str = group['Metrics']['UnblendedCost']['Amount']
                amount = float(amount_str)

                # Skip zero-cost entries to keep the breakdown clean
                if amount == 0.0:
                    continue

                # The key from CE is in format "tagValue" when grouped by a single tag
                # or empty string for untagged resources
                if raw_key == '' or raw_key == '$':
                    tag_breakdown['(untagged)'] = amount
                else:
                    # Remove the tag key prefix if present (format: "key$value")
                    if '$' in raw_key:
                        tag_breakdown[raw_key.replace('$', '=')] = amount
                    else:
                        tag_breakdown[raw_key] = amount

            if tag_breakdown:
                tag_data[period_start] = tag_breakdown

        return tag_data

    def _discover_active_tag_keys(
        self, ce_client, date_range: DateRange, credentials: dict = None
    ) -> list[str]:
        """Discover tag keys available for cost grouping.

        First tries CE get_tags API (returns cost allocation tags).
        If that returns empty, falls back to Resource Groups Tagging API
        to discover tag keys from actual resources (works even without
        cost allocation tag activation).

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            credentials: Optional STS credentials for Resource Groups API fallback.

        Returns:
            List of tag key strings. Empty list on failure or no tags.
        """
        try:
            response = ce_client.get_tags(
                TimePeriod={'Start': date_range.start, 'End': date_range.end}
            )
            tags = response.get('Tags', [])
            if tags:
                logger.info(f"Discovered {len(tags)} active tag keys via CE: {tags}")
                return tags
        except Exception as e:
            logger.warning(f"CE get_tags failed: {e}")

        # Fallback: discover tag keys from Resource Groups Tagging API
        if credentials:
            try:
                # Detect charged regions dynamically instead of hard-coding
                charged_regions = self._detect_charged_regions(ce_client)
                tag_keys_set: set[str] = set()
                for region in charged_regions:
                    try:
                        tagging = boto3.client(
                            'resourcegroupstaggingapi',
                            aws_access_key_id=credentials.get('AccessKeyId'),
                            aws_secret_access_key=credentials.get('SecretAccessKey'),
                            aws_session_token=credentials.get('SessionToken'),
                            region_name=region,
                        )
                        paginator = tagging.get_paginator('get_tag_keys')
                        for page in paginator.paginate():
                            tag_keys_set.update(page.get('TagKeys', []))
                    except Exception as e:
                        logger.debug(f"get_tag_keys failed for region {region}: {e}")
                        continue
                # Filter out AWS-internal tags to reduce noise
                user_tags = [k for k in tag_keys_set if not k.startswith('aws:') and not k.startswith('aws-cdk:')]
                if user_tags:
                    logger.info(f"Discovered {len(user_tags)} tag keys via Resource Groups API: {user_tags[:10]}...")
                    return user_tags[:20]  # Cap at 20 to avoid excessive CE calls
            except Exception as e:
                logger.warning(f"Resource Groups tag key discovery failed: {e}")

        logger.info("No tag keys found from any source, skipping tag breakdown")
        return []

    def _call_ce_for_single_tag(
        self,
        ce_client,
        date_range: DateRange,
        tag_key: str,
        max_retries: int = 3,
        base_delay: float = 0.1,
    ) -> dict | None:
        """Query CE GetCostAndUsage for a single tag key with retry.

        Uses exponential backoff for transient errors (same codes as
        _call_ce_with_retry). Returns None on failure after retry exhaustion
        to allow caller to continue with remaining tag keys.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            tag_key: The tag key to group by.
            max_retries: Maximum number of retry attempts (default 3).
            base_delay: Base delay in seconds for backoff (default 0.1).

        Returns:
            The CE API response dict, or None on failure.
        """
        for attempt in range(max_retries + 1):
            try:
                response = ce_client.get_cost_and_usage(
                    TimePeriod={'Start': date_range.start, 'End': date_range.end},
                    Granularity='DAILY',
                    Metrics=['UnblendedCost'],
                    GroupBy=[{'Type': 'TAG', 'Key': tag_key}],
                )
                return response
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in RETRYABLE_ERROR_CODES and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Transient CE error '%s' for tag '%s' attempt %d/%d, "
                        "retry in %.2fs",
                        error_code, tag_key, attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "Tag key query failed for '%s': %s (code: %s)",
                    tag_key, e, error_code,
                )
                return None
        return None

    def _parse_single_tag_response(
        self, response: dict, tag_key: str
    ) -> dict[str, dict[str, float]]:
        """Parse CE tag response for a single tag key into {date: {value: cost}}.

        Rules:
        - Zero-cost values are excluded
        - Empty/missing tag values are stored as "(untagged)"
        - The dollar-sign separator in CE keys ("key$value") is handled

        Args:
            response: The raw CE API response dict (grouped by TAG).
            tag_key: The tag key that was queried (used for key prefix detection).

        Returns:
            Dict mapping date (YYYY-MM-DD) to {tag_value: cost_amount}.
        """
        date_data: dict[str, dict[str, float]] = {}

        for period in response.get('ResultsByTime', []):
            period_start = period['TimePeriod']['Start']
            values: dict[str, float] = {}

            for group in period.get('Groups', []):
                raw_key = group['Keys'][0]
                amount = float(group['Metrics']['UnblendedCost']['Amount'])

                if amount == 0.0:
                    continue

                # Extract tag value from CE key format
                if raw_key == '' or raw_key == '$' or raw_key == f'{tag_key}$':
                    tag_value = '(untagged)'
                elif '$' in raw_key:
                    # Format: "tagKey$tagValue" — extract value after $
                    tag_value = raw_key.split('$', 1)[1] or '(untagged)'
                else:
                    tag_value = raw_key

                values[tag_value] = values.get(tag_value, 0.0) + amount

            if values:
                date_data[period_start] = values

        return date_data

    def _fetch_all_tag_breakdowns(
        self,
        ce_client,
        date_range: DateRange,
        credentials: dict = None,
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Fetch tag breakdowns for all active tag keys sequentially.

        Discovers active tag keys via _discover_active_tag_keys, then queries
        Cost Explorer for each tag key one at a time. For tag keys where CE
        returns only '(untagged)' (cost allocation tags not activated), falls
        back to the Resource Groups Tagging API to estimate per-tag-value costs
        proportionally from the service breakdown.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            credentials: Optional STS credentials for Resource Groups API fallback.

        Returns:
            Nested dict: {tag_key: {date: {tag_value: cost}}}
            Only includes successfully queried tag keys.
        """
        tag_keys = self._discover_active_tag_keys(ce_client, date_range, credentials)
        if not tag_keys:
            return {}

        all_tag_data: dict[str, dict[str, dict[str, float]]] = {}
        failed_count = 0
        untagged_only_keys: list[str] = []

        for tag_key in tag_keys:
            response = self._call_ce_for_single_tag(ce_client, date_range, tag_key)
            if response is None:
                failed_count += 1
                continue
            parsed = self._parse_single_tag_response(response, tag_key)
            if parsed:
                # Check if ALL dates have ONLY "(untagged)" — means CE can't break down by this tag
                all_untagged = all(
                    list(day_values.keys()) == ['(untagged)']
                    for day_values in parsed.values()
                )
                if all_untagged:
                    untagged_only_keys.append(tag_key)
                else:
                    all_tag_data[tag_key] = parsed

        if failed_count == len(tag_keys):
            logger.error(f"All {failed_count} tag key queries failed")
        elif failed_count > 0:
            logger.warning(f"{failed_count}/{len(tag_keys)} tag key queries failed")

        # For tag keys where CE returned only (untagged), use Resource Groups API fallback
        if untagged_only_keys and credentials:
            logger.info(
                f"CE returned only (untagged) for {len(untagged_only_keys)} tag keys, "
                f"using Resource Groups API fallback: {untagged_only_keys}"
            )
            # Auto-activate these tags as cost allocation tags so next sync gets real data
            try:
                self._activate_cost_allocation_tags(ce_client, untagged_only_keys)
            except Exception as e:
                logger.warning(f"Cost allocation tag activation failed: {e}")
            try:
                rg_tag_data = self._resource_groups_tag_fallback(
                    ce_client, date_range, credentials, untagged_only_keys
                )
                all_tag_data.update(rg_tag_data)
            except Exception as e:
                logger.warning(f"Resource Groups tag fallback failed: {e}")

        return all_tag_data

    def _activate_cost_allocation_tags(
        self, ce_client, tag_keys: list[str]
    ) -> None:
        """Activate discovered tag keys as cost allocation tags.

        Calls UpdateCostAllocationTagsStatus to activate tags that CE
        doesn't yet track. After activation (takes up to 24h), CE will
        return real per-tag costs instead of all-untagged.

        Args:
            ce_client: boto3 Cost Explorer client.
            tag_keys: List of tag key strings to activate.
        """
        try:
            existing = ce_client.list_cost_allocation_tags(
                Status='Active', MaxResults=100
            )
            active_keys = {t.get('TagKey') for t in existing.get('CostAllocationTags', [])}
            to_activate = [k for k in tag_keys if k not in active_keys]
            if not to_activate:
                return
            for i in range(0, len(to_activate), 20):
                batch = to_activate[i:i+20]
                ce_client.update_cost_allocation_tags_status(
                    CostAllocationTagsStatus=[
                        {'TagKey': k, 'Status': 'Active'} for k in batch
                    ]
                )
                logger.info(f"Activated {len(batch)} cost allocation tags: {batch}")
        except Exception as e:
            logger.warning(f"Cost allocation tag activation failed: {e}")

    def _detect_charged_regions(self, ce_client) -> list[str]:
        """Detect regions with actual charges from Cost Explorer.

        Uses a single CE API call grouped by REGION to find regions with
        non-trivial costs. Falls back to ['us-east-1'] on failure.

        Args:
            ce_client: boto3 Cost Explorer client.

        Returns:
            List of region strings sorted by cost descending.
        """
        try:
            now = date.today()
            first_this = now.replace(day=1)
            first_last = (first_this - timedelta(days=1)).replace(day=1)
            resp = ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': first_last.isoformat(),
                    'End': first_this.isoformat(),
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'REGION'}],
            )
            regions: dict[str, float] = {}
            for period in resp.get('ResultsByTime', []):
                for group in period.get('Groups', []):
                    region_val = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0.01 and region_val and region_val != 'global':
                        regions[region_val] = regions.get(region_val, 0) + cost
            sorted_regions = sorted(regions.keys(), key=lambda r: regions[r], reverse=True)
            return sorted_regions if sorted_regions else ['us-east-1']
        except Exception as e:
            logger.warning(f"Region detection failed: {e}")
            return ['us-east-1']

    def _resource_groups_tag_fallback(
        self,
        ce_client,
        date_range: DateRange,
        credentials: dict,
        tag_keys: list[str],
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Estimate per-tag-value costs using Resource Groups Tagging API.

        For EC2 instances, looks up actual instance types and estimates costs
        based on instance size (not equal proportions). For other services,
        uses resource-count-based proportional allocation.

        This replicates the old dashboard behavior that worked without
        cost allocation tag activation.

        Args:
            ce_client: boto3 Cost Explorer client (for region detection).
            date_range: DateRange to query.
            credentials: AWS credentials dict.
            tag_keys: List of tag keys to estimate costs for.

        Returns:
            Nested dict: {tag_key: {date: {tag_value: cost}}}
        """
        # Detect charged regions dynamically
        charged_regions = self._detect_charged_regions(ce_client)
        logger.info(f"Resource Groups fallback scanning regions: {charged_regions}")

        # Structure: {tag_key: {tag_value: [{arn, service, region, resource}]}}
        tag_key_resources: dict[str, dict[str, list[dict]]] = {}

        for tag_key in tag_keys:
            value_resources: dict[str, list[dict]] = {}
            for region in charged_regions:
                try:
                    tagging = boto3.client(
                        'resourcegroupstaggingapi',
                        aws_access_key_id=credentials.get('AccessKeyId'),
                        aws_secret_access_key=credentials.get('SecretAccessKey'),
                        aws_session_token=credentials.get('SessionToken'),
                        region_name=region,
                    )
                    paginator = tagging.get_paginator('get_resources')
                    for page in paginator.paginate(
                        TagFilters=[{'Key': tag_key}],
                        ResourcesPerPage=100,
                    ):
                        for res in page.get('ResourceTagMappingList', []):
                            arn = res.get('ResourceARN', '')
                            tag_val = None
                            for t in res.get('Tags', []):
                                if t['Key'] == tag_key:
                                    tag_val = t['Value']
                                    break
                            if not tag_val:
                                continue
                            parts = arn.split(':')
                            if len(parts) >= 6:
                                svc_code = parts[2]
                                res_region = parts[3] or region
                                resource_part = ':'.join(parts[5:])
                                value_resources.setdefault(tag_val, []).append({
                                    'arn': arn, 'service': svc_code,
                                    'region': res_region, 'resource': resource_part,
                                })
                except Exception as e:
                    logger.debug(f"Resource Groups scan failed for tag '{tag_key}' in {region}: {e}")
                    continue

            if value_resources:
                tag_key_resources[tag_key] = value_resources
                logger.info(
                    f"Tag '{tag_key}': found {sum(len(v) for v in value_resources.values())} "
                    f"resources across {len(value_resources)} values"
                )

        if not tag_key_resources:
            return {}

        # Get EC2 instance types for cost-weighted estimation
        # Collect all EC2 instance IDs by region
        ec2_instances_by_region: dict[str, list[str]] = {}
        for value_resources in tag_key_resources.values():
            for resources in value_resources.values():
                for r in resources:
                    if r['service'] == 'ec2' and 'instance/' in r['resource']:
                        inst_id = r['resource'].split('/')[-1]
                        ec2_instances_by_region.setdefault(r['region'], []).append(inst_id)

        # Describe instances to get types
        instance_types: dict[str, str] = {}  # instance_id -> instance_type
        for region, inst_ids in ec2_instances_by_region.items():
            try:
                ec2_client = boto3.client(
                    'ec2',
                    aws_access_key_id=credentials.get('AccessKeyId'),
                    aws_secret_access_key=credentials.get('SecretAccessKey'),
                    aws_session_token=credentials.get('SessionToken'),
                    region_name=region,
                )
                # Batch describe (max 200 at a time)
                unique_ids = list(set(inst_ids))
                for i in range(0, len(unique_ids), 200):
                    batch = unique_ids[i:i+200]
                    try:
                        desc = ec2_client.describe_instances(InstanceIds=batch)
                        for reservation in desc.get('Reservations', []):
                            for inst in reservation.get('Instances', []):
                                iid = inst.get('InstanceId', '')
                                itype = inst.get('InstanceType', 't3.medium')
                                instance_types[iid] = itype
                    except Exception as e:
                        logger.debug(f"describe_instances failed for batch in {region}: {e}")
            except Exception as e:
                logger.debug(f"EC2 client creation failed for {region}: {e}")

        # Hourly cost lookup for instance types
        _hourly_costs = {
            't2.nano': 0.0058, 't2.micro': 0.0116, 't2.small': 0.023, 't2.medium': 0.0464,
            't2.large': 0.0928, 't2.xlarge': 0.1856, 't2.2xlarge': 0.3712,
            't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416,
            't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
            't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376,
            't3a.large': 0.0752, 't3a.xlarge': 0.1504, 't3a.2xlarge': 0.3008,
            'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
            'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384,
            'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68,
            'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34,
            'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008,
            'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504,
            'i3.large': 0.156, 'i3.xlarge': 0.312, 'i3.2xlarge': 0.624,
        }

        def _get_hourly_cost(instance_id: str) -> float:
            itype = instance_types.get(instance_id, 't3.medium')
            return _hourly_costs.get(itype, 0.05)

        # Fetch daily service costs
        try:
            svc_response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': date_range.start, 'End': date_range.end},
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
        except Exception as e:
            logger.warning(f"Failed to fetch service costs for RG fallback: {e}")
            return {}

        # Parse daily service costs
        daily_service_costs: dict[str, dict[str, float]] = {}
        for period in svc_response.get('ResultsByTime', []):
            period_date = period['TimePeriod']['Start']
            svc_costs: dict[str, float] = {}
            for group in period.get('Groups', []):
                svc_name = group['Keys'][0]
                amount = float(group['Metrics']['UnblendedCost']['Amount'])
                if amount > 0:
                    svc_costs[svc_name] = amount
            daily_service_costs[period_date] = svc_costs

        EC2_CE_NAME = 'Amazon Elastic Compute Cloud - Compute'

        # Map service codes to CE names for non-EC2 services
        SVC_CODE_TO_CE_NAME = {
            'rds': 'Amazon Relational Database Service',
            's3': 'Amazon Simple Storage Service',
            'lambda': 'AWS Lambda',
            'dynamodb': 'Amazon DynamoDB',
            'elasticache': 'Amazon ElastiCache',
            'sqs': 'Amazon Simple Queue Service',
            'sns': 'Amazon Simple Notification Service',
            'kms': 'AWS Key Management Service',
            'elasticloadbalancing': 'Elastic Load Balancing',
            'cloudwatch': 'AmazonCloudWatch',
            'apigateway': 'Amazon API Gateway',
            'cloudfront': 'Amazon CloudFront',
            'route53': 'Amazon Route 53',
            'glue': 'AWS Glue',
            'rekognition': 'Amazon Rekognition',
            'amplify': 'AWS Amplify',
        }

        # For each tag key, estimate per-value costs using instance-size weighting
        result: dict[str, dict[str, dict[str, float]]] = {}

        for tag_key, value_resources in tag_key_resources.items():
            # Compute per-tag-value hourly cost weight for EC2
            # {tag_value: total_hourly_cost_for_ec2_instances}
            value_ec2_hourly: dict[str, float] = {}
            total_ec2_hourly = 0.0

            # Non-EC2: count resources per service per tag value
            value_other_svc: dict[str, dict[str, int]] = {}
            total_other_svc: dict[str, int] = {}

            for tag_val, resources in value_resources.items():
                ec2_hourly = 0.0
                other_counts: dict[str, int] = {}
                for r in resources:
                    if r['service'] == 'ec2' and 'instance/' in r['resource']:
                        inst_id = r['resource'].split('/')[-1]
                        ec2_hourly += _get_hourly_cost(inst_id)
                    else:
                        svc_code = r['service']
                        ce_name = SVC_CODE_TO_CE_NAME.get(svc_code)
                        if ce_name:
                            other_counts[ce_name] = other_counts.get(ce_name, 0) + 1

                if ec2_hourly > 0:
                    value_ec2_hourly[tag_val] = ec2_hourly
                    total_ec2_hourly += ec2_hourly
                if other_counts:
                    value_other_svc[tag_val] = other_counts
                    for svc, cnt in other_counts.items():
                        total_other_svc[svc] = total_other_svc.get(svc, 0) + cnt

            # Estimate daily costs per tag value
            date_data: dict[str, dict[str, float]] = {}
            for period_date, svc_costs in daily_service_costs.items():
                value_costs: dict[str, float] = {}
                total_day_cost = sum(svc_costs.values())
                tagged_cost = 0.0

                ec2_day_cost = svc_costs.get(EC2_CE_NAME, 0.0)

                for tag_val in set(list(value_ec2_hourly.keys()) + list(value_other_svc.keys())):
                    val_cost = 0.0

                    # EC2: weight by instance hourly cost
                    if tag_val in value_ec2_hourly and total_ec2_hourly > 0 and ec2_day_cost > 0:
                        ec2_proportion = value_ec2_hourly[tag_val] / total_ec2_hourly
                        val_cost += ec2_day_cost * ec2_proportion

                    # Other services: weight by resource count
                    if tag_val in value_other_svc:
                        for svc_name, res_count in value_other_svc[tag_val].items():
                            svc_total_cost = svc_costs.get(svc_name, 0.0)
                            total_res = total_other_svc.get(svc_name, 1)
                            if total_res > 0 and svc_total_cost > 0:
                                val_cost += svc_total_cost * (res_count / total_res)

                    if val_cost > 0:
                        value_costs[tag_val] = round(val_cost, 10)
                        tagged_cost += val_cost

                # Add (untagged) for the remainder
                untagged = total_day_cost - tagged_cost
                if untagged > 0.01:
                    value_costs['(untagged)'] = round(untagged, 10)

                if value_costs:
                    date_data[period_date] = value_costs

            if date_data:
                result[tag_key] = date_data

        return result

    def _apply_top_n_cap(
        self,
        tag_data: dict[str, dict[str, dict[str, float]]],
        top_n: int = TOP_N_CAP_DEFAULT,
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Retain only top N tag values per tag key by total cost across all dates.

        Sums costs per tag value across all dates for each tag key, then retains
        only the top N values (by descending total cost). Discarded values are
        aggregated into a single "(other)" entry per day. The "(untagged)" entry
        is always preserved regardless of ranking.

        Args:
            tag_data: {tag_key: {date: {tag_value: cost}}}
            top_n: Maximum values to retain per tag key (default 50).

        Returns:
            Modified tag_data with capped values per tag key.
        """
        for tag_key, date_values in tag_data.items():
            # Sum costs across all dates per value (excluding special entries)
            value_totals: dict[str, float] = {}
            for date_dict in date_values.values():
                for value, cost in date_dict.items():
                    if value == '(other)':
                        continue
                    if value == '(untagged)':
                        continue
                    value_totals[value] = value_totals.get(value, 0.0) + cost

            if len(value_totals) <= top_n:
                continue

            # Determine top N values by descending total cost
            sorted_values = sorted(
                value_totals.items(), key=lambda x: x[1], reverse=True
            )
            top_values = {v[0] for v in sorted_values[:top_n]}

            # Aggregate discarded values into "(other)" per day
            for date_str, day_values in date_values.items():
                other_sum = 0.0
                keys_to_remove = []
                for value, cost in day_values.items():
                    if value not in top_values and value != '(untagged)' and value != '(other)':
                        other_sum += cost
                        keys_to_remove.append(value)
                for k in keys_to_remove:
                    del day_values[k]
                if other_sum > 0:
                    day_values['(other)'] = day_values.get('(other)', 0.0) + other_sum

        return tag_data

    def _apply_size_guard(
        self,
        tag_data: dict[str, dict[str, dict[str, float]]],
        account_id: str,
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Remove tag keys with fewest values until serialized size <= 350KB.

        Serializes tag_data to JSON and checks UTF-8 byte size against
        SIZE_LIMIT_BYTES (350KB). While over limit, finds the tag key with
        the fewest distinct values across all dates, removes it, and logs
        a warning. Repeats until within limit or no tag keys remain.

        Args:
            tag_data: {tag_key: {date: {tag_value: cost}}} — already Top-N capped.
            account_id: Account identifier for logging context.

        Returns:
            Potentially reduced tag_data within size limit.
        """
        while True:
            serialized = json.dumps(tag_data, default=str)
            if len(serialized.encode('utf-8')) <= SIZE_LIMIT_BYTES:
                break
            if not tag_data:
                break

            # Find tag key with fewest total distinct values across all dates
            key_value_counts = {
                tk: len(set(v for day in dates.values() for v in day.keys()))
                for tk, dates in tag_data.items()
            }
            smallest_key = min(key_value_counts, key=key_value_counts.get)
            logger.warning(
                "Size guard: removing tag key '%s' (account: %s) — "
                "%d values, breakdown exceeds 350KB",
                smallest_key, account_id, key_value_counts[smallest_key],
            )
            del tag_data[smallest_key]

        return tag_data

    def merge_results(
        self,
        cached_items: list[CostDataItem],
        fetched_items: list[CostDataItem],
    ) -> list[CostDataItem]:
        """Merge cached and freshly fetched items, preferring fresh data.

        For overlapping dates, the freshly fetched item takes precedence
        (last-write-wins semantics).

        Args:
            cached_items: Items previously retrieved from the cache.
            fetched_items: Items freshly fetched from the Cost Explorer API.

        Returns:
            Combined sorted list of CostDataItem objects, with fresh data
            preferred for any date that appears in both inputs.
        """
        # Build a dict keyed by date, starting with cached items
        merged: dict[str, CostDataItem] = {}
        for item in cached_items:
            merged[item.date] = item

        # Overwrite with fetched items — fresh data wins for overlapping dates
        for item in fetched_items:
            merged[item.date] = item

        # Return sorted by date ascending
        return sorted(merged.values(), key=lambda item: item.date)

    # -----------------------------------------------------------------------
    # Vendor-neutral AI cost/usage read and write-back
    # (vendor-agnostic-ai-usage feature)
    #
    # These methods operate on the neutral COST#/USAGE# sort-key families only.
    # The AWS DAILY# path above is left completely untouched.
    # -----------------------------------------------------------------------

    def _query_neutral_window(
        self,
        table,
        pk: str,
        start_sk: str,
        end_sk: str,
    ) -> list[dict]:
        """Query a (pk, sk) window from the cache table, handling pagination.

        Args:
            table: A boto3 DynamoDB Table resource for the Cost_Cache_Table.
            pk: The neutral partition key '{memberEmail}#{accountId}'.
            start_sk: Inclusive lower sort-key bound.
            end_sk: Inclusive upper sort-key bound.

        Returns:
            List of raw DynamoDB item dicts within the window.
        """
        from boto3.dynamodb.conditions import Key

        key_condition = Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)

        items: list[dict] = []
        response = table.query(KeyConditionExpression=key_condition)
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=key_condition,
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))
        return items

    def read_cost_rollup_window(
        self,
        table,
        member_email: str,
        account_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Read Cost_Rollup_Item records for a date window.

        Uses ``Key('pk').eq(pk) & Key('sk').between('COST#{start}', 'COST#{end}')``
        over the neutral schema (Req 2.1).

        Args:
            table: A boto3 DynamoDB Table resource for the Cost_Cache_Table.
            member_email: The authenticated member's email address.
            account_id: The connected AI-vendor account identifier.
            start_date: Inclusive ISO 8601 start date (YYYY-MM-DD).
            end_date: Inclusive ISO 8601 end date (YYYY-MM-DD).

        Returns:
            List of Cost_Rollup_Item dicts in the window.
        """
        from cache_service import (
            build_neutral_partition_key,
            build_cost_rollup_sort_key,
        )

        pk = build_neutral_partition_key(member_email, account_id)
        start_sk = build_cost_rollup_sort_key(start_date)
        end_sk = build_cost_rollup_sort_key(end_date)
        return self._query_neutral_window(table, pk, start_sk, end_sk)

    def read_usage_detail_window(
        self,
        table,
        member_email: str,
        account_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Read Usage_Detail_Item records for a date window.

        Uses ``Key('pk').eq(pk) & Key('sk').between('USAGE#{start}', 'USAGE#{end}#\\uffff')``
        so that every actor/service suffix on the inclusive end date is captured
        (Req 2.2).

        Args:
            table: A boto3 DynamoDB Table resource for the Cost_Cache_Table.
            member_email: The authenticated member's email address.
            account_id: The connected AI-vendor account identifier.
            start_date: Inclusive ISO 8601 start date (YYYY-MM-DD).
            end_date: Inclusive ISO 8601 end date (YYYY-MM-DD).

        Returns:
            List of Usage_Detail_Item dicts in the window.
        """
        from cache_service import (
            build_neutral_partition_key,
            USAGE_DETAIL_SK_PREFIX,
        )

        pk = build_neutral_partition_key(member_email, account_id)
        start_sk = f"{USAGE_DETAIL_SK_PREFIX}{start_date}"
        # '\uffff' sorts after every normal character, so the upper bound
        # captures all '#{actor}#{service}' suffixes on the end date.
        end_sk = f"{USAGE_DETAIL_SK_PREFIX}{end_date}#\uffff"
        return self._query_neutral_window(table, pk, start_sk, end_sk)

    def write_neutral_items(self, table, items: list[dict]) -> bool:
        """Persist pre-shaped neutral items (Tier-2/Tier-3 write-back).

        Writes Cost_Rollup_Item / Usage_Detail_Item dicts (as produced by
        ``cache_service.shape_cost_rollup_item`` / ``shape_usage_detail_item``)
        to the Cost_Cache_Table via batched PutItem requests, overwriting by
        primary key (Req 4.6). The AWS DAILY# path is not involved.

        Args:
            table: A boto3 DynamoDB Table resource for the Cost_Cache_Table.
            items: List of pre-shaped neutral item dicts.

        Returns:
            True when all items were submitted for writing.
        """
        if not items:
            return True

        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
        return True

    def neutral_items_from_normalized(
        self,
        member_email: str,
        account_id: str,
        normalized_records: list[dict],
        cached_at: str | None = None,
    ) -> list[dict]:
        """Build neutral cache items from cost_normalizer output.

        Reuses the common-schema records produced by ``cost_normalizer`` (which
        carry ``date``, ``service_name``, ``cost_amount``, ``currency``,
        ``input_tokens``, ``output_tokens`` and optional ``project_id``) and
        projects them onto the neutral schema: one Cost_Rollup_Item per day
        (summing cost across services) plus one Usage_Detail_Item per
        actor/service/day (Req 2.1, 2.2). Token totals become the usage
        quantity (unit 'tokens'); the actor falls back to null when the source
        has no project/user identifier (Req 2.6).

        Args:
            member_email: The authenticated member's email address.
            account_id: The connected AI-vendor account identifier.
            normalized_records: cost_normalizer common-schema records.
            cached_at: ISO 8601 timestamp; defaults to now (UTC) per item shaper.

        Returns:
            List of neutral item dicts (rollups followed by detail records).
        """
        from cache_service import (
            shape_cost_rollup_item,
            shape_usage_detail_item,
            NEUTRAL_USAGE_UNIT,
        )

        rollups: dict[str, dict] = {}
        details: list[dict] = []

        for record in normalized_records:
            date = record.get('date')
            if not date:
                continue
            cost = float(record.get('cost_amount', 0) or 0)
            currency = record.get('currency') or 'USD'

            # Accumulate the daily cost rollup.
            rollup = rollups.get(date)
            if rollup is None:
                rollups[date] = {'cost': cost, 'currency': currency}
            else:
                rollup['cost'] += cost

            # Per-actor/per-service usage detail.
            service = record.get('service_name')
            # Actor falls back to null when no source identifier is present.
            actor = record.get('project_id')
            tokens = (record.get('input_tokens') or 0) + (record.get('output_tokens') or 0)
            details.append(
                shape_usage_detail_item(
                    member_email=member_email,
                    account_id=account_id,
                    date=date,
                    actor=actor,
                    service=service,
                    usage_quantity=tokens if tokens else None,
                    unit=NEUTRAL_USAGE_UNIT,
                    cost_amount=cost,
                    cached_at=cached_at,
                )
            )

        rollup_items = [
            shape_cost_rollup_item(
                member_email=member_email,
                account_id=account_id,
                date=date,
                cost_amount=round(data['cost'], 4),
                currency=data['currency'],
                cached_at=cached_at,
            )
            for date, data in sorted(rollups.items())
        ]

        return rollup_items + details


# ===========================================================================
# Three-tier AI usage resolver (vendor-agnostic-ai-usage feature, Task 3)
#
# The resolver is the AI_Usage_Service orchestrator. It is structurally
# cache-first: Tier 1 (cache read) always executes before any Tier 2 (Tips
# drilldown via the customer connection) or Tier 3 (bounded live vendor call),
# and Tier 2 always runs before Tier 3 (Property 6 / Req 4.1, 4.3, 4.4, 11.1).
# Tier-2/Tier-3 results are written back under the neutral COST#/USAGE# schema
# (Req 4.6). All retrieval targets exactly one (memberEmail, accountId) pair
# using the customer's own credentials (Req 11.2, 11.3).
# ===========================================================================

import os as _os
from concurrent.futures import (
    ThreadPoolExecutor as _ThreadPoolExecutor,
    TimeoutError as _FuturesTimeout,
)
from dataclasses import dataclass, field

# Tier-3 latency bound (reuses the existing 20s ThreadPoolExecutor budget used
# elsewhere for bounded live work, Req 12.3).
TIER3_TIMEOUT_SECONDS = 20

_COST_CACHE_TABLE_NAME = _os.environ.get('COST_CACHE_TABLE_NAME', 'Cost_Cache_Table')


class AdminKeyRequiredError(Exception):
    """Raised when a Tier-3 live call needs an admin-level key the account lacks."""
    pass


@dataclass
class DrilldownResult:
    """Outcome of a Tier-2 Tips drilldown executed via the customer connection."""
    satisfied: bool = False
    items: list = field(default_factory=list)
    error: dict | None = None


@dataclass
class LiveResult:
    """Outcome of a bounded Tier-3 live vendor call."""
    items: list = field(default_factory=list)
    partial: bool = False
    error: dict | None = None


def build_admin_key_required_error() -> dict:
    """Structured message when account-wide usage needs an admin-level key (Req 12.1)."""
    return {
        'error': 'admin_key_required',
        'message': (
            'Account-wide AI usage requires an admin-level API key. The connected '
            'key does not have organization-wide access. Please add an admin-level '
            'key in the Configure tab to see account-wide usage.'
        ),
    }


def build_connection_required_error() -> dict:
    """Structured "configure connection" message for missing credentials (Req 6.4)."""
    return {
        'error': 'connection_required',
        'message': (
            'No AI vendor connection is configured for this account. Please add '
            'your connection in the Configure tab to retrieve usage data.'
        ),
        'configureTab': True,
    }


def _coerce_float(value) -> float:
    """Best-effort numeric coercion; missing/unparseable values sort as 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _field(obj, key, default=None):
    """Read ``key`` from a dict or attribute-style object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _normalize_period(period, now: datetime, window_days: int = 30) -> dict:
    """Resolve the requested window to {start, end} ISO dates.

    Defaults to the most recent ``window_days`` calendar days when no period
    is supplied (Req 3.6).
    """
    default_end = now.strftime('%Y-%m-%d')
    default_start = (now - timedelta(days=window_days - 1)).strftime('%Y-%m-%d')
    if not period:
        return {'start': default_start, 'end': default_end}
    if isinstance(period, dict):
        return {
            'start': period.get('start') or default_start,
            'end': period.get('end') or default_end,
        }
    if isinstance(period, str):
        for sep in ('/', ' to ', ','):
            if sep in period:
                parts = [p.strip() for p in period.split(sep, 1)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    return {'start': parts[0], 'end': parts[1]}
                break
    return {'start': default_start, 'end': default_end}


def _resolve_currency(rollup_items: list, usage_items: list) -> str:
    """Return the first non-null currency seen, defaulting to USD."""
    for item in list(rollup_items or []) + list(usage_items or []):
        currency = _field(item, 'currency')
        if currency:
            return str(currency).upper()
    return 'USD'


def _merge_neutral(*item_lists) -> tuple[list, list]:
    """Merge neutral item lists by (pk, sk), later writes winning.

    Returns ``(rollup_items, usage_items)`` split by sort-key family.
    """
    from cache_service import COST_ROLLUP_SK_PREFIX, USAGE_DETAIL_SK_PREFIX

    merged: dict = {}
    order: list = []
    for lst in item_lists:
        for item in lst or []:
            sk = _field(item, 'sk')
            key = (_field(item, 'pk'), sk) if sk else (id(item),)
            if key not in merged:
                order.append(key)
            merged[key] = item

    rollups, usage = [], []
    for key in order:
        item = merged[key]
        sk = str(_field(item, 'sk') or '')
        if sk.startswith(COST_ROLLUP_SK_PREFIX):
            rollups.append(item)
        elif sk.startswith(USAGE_DETAIL_SK_PREFIX):
            usage.append(item)
        else:
            usage.append(item)
    return rollups, usage


def build_ai_usage_response(
    dimension: str,
    period: dict,
    rollup_items: list,
    usage_items: list,
    *,
    source: str = 'cache',
    live_partial: bool = False,
    currency: str | None = None,
    max_entries: int | None = None,
    error: dict | None = None,
    provider: str | None = None,
) -> dict:
    """Build the capped neutral AIUsageResponse dict.

    The ``usage`` list is sorted by descending cost and capped to the
    configured maximum number of entries; when entries are dropped the
    response sets ``truncated = True`` (Property 15 / Req 12.2). ``rollups``
    are one-per-day and not capped.
    """
    from cache_service import DEFAULT_MAX_RESPONSE_ENTRIES

    if max_entries is None:
        max_entries = DEFAULT_MAX_RESPONSE_ENTRIES

    sorted_usage = sorted(
        list(usage_items or []),
        key=lambda u: _coerce_float(_field(u, 'cost_amount')),
        reverse=True,
    )
    truncated = len(sorted_usage) > max_entries
    capped_usage = sorted_usage[:max_entries]

    response = {
        'dimension': dimension,
        'period': period,
        'currency': currency or _resolve_currency(rollup_items, usage_items),
        'rollups': list(rollup_items or []),
        'usage': capped_usage,
        'truncated': truncated,
        'providerMetadata': {
            'provider': provider,
            'source': source,
            'live_partial': bool(live_partial),
        },
    }
    if error:
        response['error'] = error.get('error')
        response['message'] = error.get('message')
        if error.get('configureTab'):
            response['configureTab'] = True
    return response


def _live_result_to_neutral_items(member_email: str, account_id: str, result: dict,
                                  cached_at: str | None = None) -> list:
    """Convert an ``AIVendorConnector.get_ai_usage`` result to neutral items.

    Only entries carrying a concrete ``date`` (plus actor/service for usage)
    are converted for write-back; dimension-grouped projections (which lack a
    date) are left out of the cache write (Req 4.6).
    """
    from cache_service import (
        shape_cost_rollup_item,
        shape_usage_detail_item,
        NEUTRAL_USAGE_UNIT,
    )

    items: list = []
    if not isinstance(result, dict):
        return items

    for rollup in result.get('rollups', []) or []:
        date = _field(rollup, 'date')
        if not date:
            continue
        items.append(shape_cost_rollup_item(
            member_email=member_email,
            account_id=account_id,
            date=date,
            cost_amount=_field(rollup, 'cost_amount'),
            currency=_field(rollup, 'currency'),
            cached_at=cached_at,
        ))

    for usage in result.get('usage', []) or []:
        date = _field(usage, 'date')
        actor = _field(usage, 'actor')
        service = _field(usage, 'service')
        # Grouped projections (units/actor) omit the date — skip those.
        if not date or service is None and actor is None:
            continue
        items.append(shape_usage_detail_item(
            member_email=member_email,
            account_id=account_id,
            date=date,
            actor=actor,
            service=service,
            usage_quantity=_field(usage, 'usage_quantity'),
            unit=_field(usage, 'unit') or NEUTRAL_USAGE_UNIT,
            cost_amount=_field(usage, 'cost_amount'),
            cached_at=cached_at,
        ))

    return items


def _default_tier3_call(
    member_email: str,
    account_id: str,
    dimension: str,
    service: str | None,
    period: dict,
    *,
    connector=None,
    now: datetime | None = None,
    timeout: int | None = None,
) -> LiveResult:
    """Bounded Tier-3 live vendor call via the customer's connector.

    Reuses a single-worker ThreadPoolExecutor bounded to ``TIER3_TIMEOUT_SECONDS``
    (Req 12.3). On timeout the call degrades to the best lower-tier result by
    returning no new items with ``partial=True`` (Req 12.4). When the live call
    needs an admin-level key the account lacks, a structured admin-key error is
    returned (Req 12.1).
    """
    if connector is None or not hasattr(connector, 'get_ai_usage'):
        # No live connector wired into this context — degrade gracefully.
        return LiveResult(items=[], partial=False)

    timeout = timeout or TIER3_TIMEOUT_SECONDS
    params = {'dimension': dimension, 'service': service, 'period': period}

    def _call():
        return connector.get_ai_usage(account_id, member_email, params)

    # Do NOT use a `with` block here: ThreadPoolExecutor.__exit__ calls
    # shutdown(wait=True), which would block until the (possibly hung) worker
    # finishes and defeat the latency bound. Instead shut down with wait=False
    # on every path so the call always returns within ``timeout`` (Req 12.3).
    executor = _ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_call)
        try:
            result = future.result(timeout=timeout)
        except _FuturesTimeout:
            logger.warning(
                "Tier-3 live call exceeded %ss bound for account %s; returning "
                "best lower-tier result", timeout, account_id
            )
            return LiveResult(items=[], partial=True)
        except AdminKeyRequiredError:
            return LiveResult(items=[], error=build_admin_key_required_error())
        except PermissionError as e:
            if 'admin' in str(e).lower():
                return LiveResult(items=[], error=build_admin_key_required_error())
            return LiveResult(items=[], error=build_connection_required_error())
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Tier-3 live call failed for account %s: %s", account_id, type(e).__name__)
            return LiveResult(items=[], partial=False)
    finally:
        executor.shutdown(wait=False)

    if isinstance(result, dict) and result.get('error'):
        err = str(result.get('error'))
        if 'admin' in err.lower():
            return LiveResult(items=[], error=build_admin_key_required_error())
        return LiveResult(items=[], partial=False)

    items = _live_result_to_neutral_items(member_email, account_id, result)
    partial = bool(isinstance(result, dict) and result.get('live_partial'))
    return LiveResult(items=items, partial=partial)


def _tier1_covers_dimension(dimension, tier1_detail):
    """True when the cached usage detail can satisfy the requested dimension.

    Cost-rollup freshness gates the cache short-circuit elsewhere, but a fresh
    cost cache does NOT mean a per-user/per-unit question can be answered from
    it. This guards the short-circuit so dimension-specific questions fall
    through to the Tips→API drilldown when the cache lacks that breakdown:

      - 'cost'  : always covered by the cost rollups.
      - 'units' : covered only if some usage row carries a token/unit quantity.
      - 'actor' : covered only if the cache holds a real per-actor breakdown
                  (>=2 distinct actors). A single actor (e.g. one project id
                  carried over from a cost fetch) is treated as NOT covering a
                  "break down by user" request, so the per-user drilldown runs.
    """
    dim = (dimension or 'cost').lower()
    if dim == 'cost':
        return True
    items = tier1_detail or []

    def _qty(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    if dim == 'units':
        return any(_qty(it.get('usage_quantity')) > 0 for it in items)
    if dim == 'actor':
        actors = {
            (it.get('actor') or '').strip()
            for it in items
            if (it.get('actor') or '').strip()
        }
        return len(actors) >= 2
    return True


def _provider_key_from_account(account_id):
    """Best-effort AI-vendor provider key from the account id prefix.

    Vendor-agnostic: derives the provider from the ``{provider}-...`` id naming
    used for AI-vendor connections (e.g. 'openai-...', 'groundcover-...').
    Falls back to 'openai' for ids without a recognised AI-vendor prefix.
    """
    aid = (account_id or '').strip().lower()
    for pk in ('openai', 'groundcover'):
        if aid.startswith(pk + '-'):
            return pk
    return 'openai'


def resolve_ai_usage(
    member_email: str,
    account_id: str,
    dimension: str,
    service: str | None = None,
    period=None,
    *,
    table=None,
    now: datetime | None = None,
    tier2_fn=None,
    tier3_fn=None,
    connector=None,
    provider_key: str | None = None,
    max_entries: int | None = None,
    window_days: int = 30,
    staleness_hours: float | None = None,
) -> dict:
    """Resolve AI cost/usage for exactly one account, cache-first.

    Orchestrates the three-tier resolution (Req 4.1-4.4, 11.1):

      Tier 1 — read neutral COST#/USAGE# records from the cache.
      Tier 2 — Tips drilldown via the customer connection (when triggered).
      Tier 3 — bounded live vendor call (last resort).

    Tier 1 always runs first; the fresh full-coverage / no-service case
    short-circuits Tiers 2 and 3 (Req 4.2). Tier-2/Tier-3 results are written
    back under the neutral schema (Req 4.6).

    Args:
        member_email: Authenticated member email (single account scope).
        account_id: The connected AI-vendor account id.
        dimension: 'cost' | 'units' | 'actor'.
        service: Optional service scope (forces Tier 2, T3).
        period: Optional {start, end} window; defaults to last 30 days.
        table: Optional cache table resource (injected for tests).
        now: Reference time (defaults to current UTC time).
        tier2_fn: Optional Tier-2 executor override (injected for tests).
        tier3_fn: Optional Tier-3 executor override (injected for tests).
        connector: Optional connector for the default Tier-3 live call.
        max_entries: Optional response cap override.
        window_days: Default window size when no period is supplied.
        staleness_hours: Optional staleness threshold override.

    Returns:
        A neutral AIUsageResponse dict (capped, with providerMetadata).
    """
    from cache_service import should_trigger_tier2, window_dates_inclusive

    if now is None:
        now = datetime.now(timezone.utc)
    period = _normalize_period(period, now, window_days)
    w_dates = window_dates_inclusive(period['start'], period['end'])

    engine = IncrementalFetchEngine()

    if table is None:
        table = boto3.resource('dynamodb').Table(_COST_CACHE_TABLE_NAME)

    # ---- Tier 1: cache read (ALWAYS first — cache-first guarantee) ----
    tier1_rollups = engine.read_cost_rollup_window(
        table, member_email, account_id, period['start'], period['end']
    )
    tier1_detail = engine.read_usage_detail_window(
        table, member_email, account_id, period['start'], period['end']
    )

    # Fresh full-coverage, no service scope → short-circuit (Req 4.2) — but
    # ONLY when the cached detail actually covers the requested dimension.
    # Cost-rollup freshness alone does not satisfy a per-user ('actor') or
    # per-unit ('units') question: the cached usage detail produced by a cost
    # fetch carries project-level actors, not per-user breakdowns. Without this
    # dimension check, "break it down by users" wrongly short-circuits on the
    # cost cache and never runs the Tips→API per-user drilldown (Req 4.3, 6).
    if not should_trigger_tier2(
        tier1_rollups, w_dates, service, now=now, threshold_hours=staleness_hours
    ) and _tier1_covers_dimension(dimension, tier1_detail):
        return build_ai_usage_response(
            dimension, period, tier1_rollups, tier1_detail,
            source='cache', max_entries=max_entries,
        )

    # ---- Tier 2: Tips drilldown via the customer connection (Req 4.3, 6) ----
    if tier2_fn is None:
        import functools
        from provider_invoices import tips_drilldown
        # Bind the account's OWN provider so the tips drilldown uses the right
        # tips/credentials/connector — never a hardcoded vendor (Req 6, vendor
        # agnostic). Without this it defaulted to 'openai' for every account.
        _pk = provider_key or _provider_key_from_account(account_id)
        tier2_fn = functools.partial(tips_drilldown, provider_key=_pk)
    t2 = tier2_fn(member_email, account_id, service, period)
    t2_error = _field(t2, 'error')
    t2_items = _field(t2, 'items') or []
    if t2_error:
        # Missing customer credentials → Configure-tab error (Req 6.4).
        return build_ai_usage_response(
            dimension, period, tier1_rollups, tier1_detail,
            source='tips', max_entries=max_entries, error=t2_error,
        )
    if _field(t2, 'satisfied'):
        engine.write_neutral_items(table, t2_items)  # neutral write-back (Req 4.6)
        rollups, usage = _merge_neutral(tier1_rollups, tier1_detail, t2_items)
        return build_ai_usage_response(
            dimension, period, rollups, usage,
            source='tips', max_entries=max_entries,
        )

    # ---- Tier 3: bounded live vendor call (last resort, Req 4.4, 12.3) ----
    if tier3_fn is None:
        tier3_fn = _default_tier3_call
    t3 = tier3_fn(
        member_email, account_id, dimension, service, period,
        connector=connector, now=now,
    )
    t3_error = _field(t3, 'error')
    t3_items = _field(t3, 'items') or []
    t3_partial = bool(_field(t3, 'partial'))
    if t3_error:
        # Admin-key gap → structured admin-level-key message (Req 12.1).
        return build_ai_usage_response(
            dimension, period, tier1_rollups, tier1_detail,
            source='live', max_entries=max_entries, error=t3_error,
        )
    if t3_items:
        engine.write_neutral_items(table, t3_items)  # neutral write-back (Req 4.6)
    rollups, usage = _merge_neutral(tier1_rollups, tier1_detail, t2_items, t3_items)
    return build_ai_usage_response(
        dimension, period, rollups, usage,
        source='live', live_partial=t3_partial, max_entries=max_entries,
    )
