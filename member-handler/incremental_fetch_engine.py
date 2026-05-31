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

        for batch_range in batched_ranges:
            response = self._call_ce_with_retry(ce_client, batch_range)
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
    ) -> dict:
        """Call Cost Explorer GetCostAndUsage with exponential backoff.

        Args:
            ce_client: boto3 Cost Explorer client.
            date_range: DateRange to query.
            max_retries: Maximum number of retry attempts (default 3).
            base_delay: Base delay in seconds for backoff (default 0.1).

        Returns:
            The CE API response dict.

        Raises:
            ClientError: If a non-retryable error occurs, or if retries
                are exhausted.
        """
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
                            'Type': 'DIMENSION',
                            'Key': 'SERVICE',
                        }
                    ],
                )
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
            try:
                rg_tag_data = self._resource_groups_tag_fallback(
                    ce_client, date_range, credentials, untagged_only_keys
                )
                all_tag_data.update(rg_tag_data)
            except Exception as e:
                logger.warning(f"Resource Groups tag fallback failed: {e}")

        return all_tag_data

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

        For each tag key, finds tagged resources across all charged regions,
        groups them by service, then estimates costs proportionally based on
        the number of tagged resources per service vs total service cost.

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

        # For each tag key, find all resources with that tag and their values
        tag_key_resources: dict[str, dict[str, list[str]]] = {}
        # Structure: {tag_key: {tag_value: [service_codes...]}}

        for tag_key in tag_keys:
            value_services: dict[str, list[str]] = {}
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
                            # Extract tag value for this key
                            tag_val = None
                            for t in res.get('Tags', []):
                                if t['Key'] == tag_key:
                                    tag_val = t['Value']
                                    break
                            if not tag_val:
                                continue
                            # Extract service from ARN (arn:aws:SERVICE:region:account:...)
                            parts = arn.split(':')
                            if len(parts) >= 3:
                                svc_code = parts[2]
                                value_services.setdefault(tag_val, []).append(svc_code)
                except Exception as e:
                    logger.debug(f"Resource Groups scan failed for tag '{tag_key}' in {region}: {e}")
                    continue

            if value_services:
                tag_key_resources[tag_key] = value_services
                logger.info(
                    f"Tag '{tag_key}': found {sum(len(v) for v in value_services.values())} "
                    f"resources across {len(value_services)} values"
                )

        if not tag_key_resources:
            return {}

        # Now fetch daily service costs for the date range (we need this to estimate)
        # We already have service breakdown from the main fetch, but we need per-day data
        # Fetch service costs for the date range
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

        # Map AWS service codes to CE service names
        SVC_CODE_TO_CE_NAME = {
            'ec2': 'Amazon Elastic Compute Cloud - Compute',
            'rds': 'Amazon Relational Database Service',
            's3': 'Amazon Simple Storage Service',
            'lambda': 'AWS Lambda',
            'dynamodb': 'Amazon DynamoDB',
            'elasticache': 'Amazon ElastiCache',
            'ecs': 'Amazon Elastic Container Service',
            'eks': 'Amazon Elastic Kubernetes Service',
            'sqs': 'Amazon Simple Queue Service',
            'sns': 'Amazon Simple Notification Service',
            'kms': 'AWS Key Management Service',
            'elasticloadbalancing': 'Elastic Load Balancing',
            'cloudwatch': 'AmazonCloudWatch',
            'logs': 'AmazonCloudWatch',
            'apigateway': 'Amazon API Gateway',
            'cloudfront': 'Amazon CloudFront',
            'route53': 'Amazon Route 53',
            'ses': 'Amazon Simple Email Service',
            'glue': 'AWS Glue',
            'rekognition': 'Amazon Rekognition',
            'amplify': 'AWS Amplify',
            'ecr': 'Amazon EC2 Container Registry (ECR)',
            'events': 'CloudWatch Events',
        }

        # Parse daily service costs
        daily_service_costs: dict[str, dict[str, float]] = {}
        # {date: {ce_service_name: cost}}
        for period in svc_response.get('ResultsByTime', []):
            period_date = period['TimePeriod']['Start']
            svc_costs: dict[str, float] = {}
            for group in period.get('Groups', []):
                svc_name = group['Keys'][0]
                amount = float(group['Metrics']['UnblendedCost']['Amount'])
                if amount > 0:
                    svc_costs[svc_name] = amount
            daily_service_costs[period_date] = svc_costs

        # For each tag key, estimate per-value costs proportionally
        result: dict[str, dict[str, dict[str, float]]] = {}

        for tag_key, value_services in tag_key_resources.items():
            # Count resources per service per tag value
            # {tag_value: {ce_service_name: resource_count}}
            value_svc_counts: dict[str, dict[str, int]] = {}
            for tag_val, svc_codes in value_services.items():
                svc_counts: dict[str, int] = {}
                for code in svc_codes:
                    ce_name = SVC_CODE_TO_CE_NAME.get(code)
                    if ce_name:
                        svc_counts[ce_name] = svc_counts.get(ce_name, 0) + 1
                    else:
                        # Try partial match for unmapped services
                        for mapped_code, mapped_name in SVC_CODE_TO_CE_NAME.items():
                            if mapped_code in code:
                                svc_counts[mapped_name] = svc_counts.get(mapped_name, 0) + 1
                                break
                if svc_counts:
                    value_svc_counts[tag_val] = svc_counts

            if not value_svc_counts:
                continue

            # Total resource count per service across all tag values
            total_svc_counts: dict[str, int] = {}
            for svc_counts in value_svc_counts.values():
                for svc_name, count in svc_counts.items():
                    total_svc_counts[svc_name] = total_svc_counts.get(svc_name, 0) + count

            # Estimate daily costs per tag value
            date_data: dict[str, dict[str, float]] = {}
            for period_date, svc_costs in daily_service_costs.items():
                value_costs: dict[str, float] = {}
                total_day_cost = sum(svc_costs.values())
                tagged_cost = 0.0

                for tag_val, svc_counts in value_svc_counts.items():
                    val_cost = 0.0
                    for svc_name, res_count in svc_counts.items():
                        svc_total_cost = svc_costs.get(svc_name, 0.0)
                        total_res_for_svc = total_svc_counts.get(svc_name, 1)
                        # Proportional allocation: (resources with this tag value / total tagged resources) * service cost
                        proportion = res_count / total_res_for_svc
                        val_cost += svc_total_cost * proportion
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
