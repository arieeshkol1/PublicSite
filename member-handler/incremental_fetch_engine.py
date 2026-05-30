"""Incremental Fetch Engine for the Cost Data Cache feature.

This module handles gap detection (identifying missing date ranges from cached data)
and fetching only the missing ranges from the AWS Cost Explorer API.

Only DAILY granularity is supported — no MONTHLY or HOURLY.
"""

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

        for batch_range in batched_ranges:
            response = self._call_ce_with_retry(ce_client, batch_range)
            items = self._parse_ce_response(response)
            all_items.extend(items)

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
