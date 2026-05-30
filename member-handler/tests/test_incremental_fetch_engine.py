"""Unit tests for IncrementalFetchEngine.compute_gaps (Task 5.1).

Tests gap detection logic that identifies missing date ranges from cached dates
and returns minimal contiguous DateRange objects.
"""

import sys
import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from incremental_fetch_engine import IncrementalFetchEngine
from cache_types import CostDataItem, DateRange


@pytest.fixture
def engine():
    """Create an IncrementalFetchEngine instance."""
    return IncrementalFetchEngine()


class TestComputeGapsBasic:
    """Basic gap detection tests."""

    def test_no_cached_dates_returns_single_range(self, engine):
        """When nothing is cached, return one range covering the full request."""
        gaps = engine.compute_gaps('2024-01-01', '2024-01-05', set(), include_today=False)
        assert gaps == [DateRange(start='2024-01-01', end='2024-01-05')]

    def test_all_dates_cached_returns_empty(self, engine):
        """When all dates are cached, return empty list."""
        cached = {'2024-01-01', '2024-01-02', '2024-01-03'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-04', cached, include_today=False)
        assert gaps == []

    def test_single_day_range_not_cached(self, engine):
        """Single day range that is not cached returns one gap."""
        gaps = engine.compute_gaps('2024-01-15', '2024-01-16', set(), include_today=False)
        assert gaps == [DateRange(start='2024-01-15', end='2024-01-16')]

    def test_single_day_range_cached(self, engine):
        """Single day range that is cached returns empty."""
        cached = {'2024-01-15'}
        gaps = engine.compute_gaps('2024-01-15', '2024-01-16', cached, include_today=False)
        assert gaps == []

    def test_empty_range_start_equals_end(self, engine):
        """When start == end, return empty (no dates in range)."""
        gaps = engine.compute_gaps('2024-01-01', '2024-01-01', set(), include_today=False)
        assert gaps == []

    def test_empty_range_start_after_end(self, engine):
        """When start > end, return empty (invalid range)."""
        gaps = engine.compute_gaps('2024-01-05', '2024-01-01', set(), include_today=False)
        assert gaps == []


class TestComputeGapsContiguous:
    """Tests for minimal contiguous range grouping."""

    def test_gap_at_beginning(self, engine):
        """Missing dates at the start form one gap."""
        cached = {'2024-01-03', '2024-01-04'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-05', cached, include_today=False)
        assert gaps == [DateRange(start='2024-01-01', end='2024-01-03')]

    def test_gap_at_end(self, engine):
        """Missing dates at the end form one gap."""
        cached = {'2024-01-01', '2024-01-02'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-05', cached, include_today=False)
        assert gaps == [DateRange(start='2024-01-03', end='2024-01-05')]

    def test_gap_in_middle(self, engine):
        """Missing dates in the middle form one gap."""
        cached = {'2024-01-01', '2024-01-04'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-05', cached, include_today=False)
        assert gaps == [DateRange(start='2024-01-02', end='2024-01-04')]

    def test_multiple_gaps(self, engine):
        """Multiple non-contiguous missing ranges produce multiple gaps."""
        cached = {'2024-01-02', '2024-01-05'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-07', cached, include_today=False)
        assert gaps == [
            DateRange(start='2024-01-01', end='2024-01-02'),
            DateRange(start='2024-01-03', end='2024-01-05'),
            DateRange(start='2024-01-06', end='2024-01-07'),
        ]

    def test_alternating_cached_and_missing(self, engine):
        """Alternating cached/missing dates produce maximum number of gaps."""
        # Cached: 1, 3, 5 -> Missing: 2, 4, 6
        cached = {'2024-01-01', '2024-01-03', '2024-01-05'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-07', cached, include_today=False)
        assert gaps == [
            DateRange(start='2024-01-02', end='2024-01-03'),
            DateRange(start='2024-01-04', end='2024-01-05'),
            DateRange(start='2024-01-06', end='2024-01-07'),
        ]

    def test_contiguous_missing_dates_merged(self, engine):
        """Contiguous missing dates are merged into a single gap."""
        cached = {'2024-01-01', '2024-01-06'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-07', cached, include_today=False)
        # Days 2, 3, 4, 5 are missing and contiguous
        assert gaps == [DateRange(start='2024-01-02', end='2024-01-06')]


class TestComputeGapsToday:
    """Tests for today's date handling."""

    def test_today_included_even_if_cached(self, engine):
        """Today's date is always included in gaps when include_today=True."""
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Cache includes today
        cached = {today}
        gaps = engine.compute_gaps(yesterday, tomorrow, cached, include_today=True)

        # Today should still appear in gaps
        all_gap_dates = set()
        for gap in gaps:
            d = date.fromisoformat(gap.start)
            end_d = date.fromisoformat(gap.end)
            while d < end_d:
                all_gap_dates.add(d.isoformat())
                d += timedelta(days=1)

        assert today in all_gap_dates

    def test_today_not_forced_when_include_today_false(self, engine):
        """Today's date is NOT forced into gaps when include_today=False."""
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Cache includes today
        cached = {today}
        gaps = engine.compute_gaps(yesterday, tomorrow, cached, include_today=False)

        # Today should NOT appear in gaps since it's cached
        all_gap_dates = set()
        for gap in gaps:
            d = date.fromisoformat(gap.start)
            end_d = date.fromisoformat(gap.end)
            while d < end_d:
                all_gap_dates.add(d.isoformat())
                d += timedelta(days=1)

        assert today not in all_gap_dates

    def test_today_outside_range_not_included(self, engine):
        """Today is not included if it's outside the requested range."""
        # Use a date range far in the past
        gaps = engine.compute_gaps('2020-01-01', '2020-01-05', set(), include_today=True)
        today = date.today().isoformat()

        all_gap_dates = set()
        for gap in gaps:
            d = date.fromisoformat(gap.start)
            end_d = date.fromisoformat(gap.end)
            while d < end_d:
                all_gap_dates.add(d.isoformat())
                d += timedelta(days=1)

        assert today not in all_gap_dates

    def test_today_already_missing_still_in_gaps(self, engine):
        """Today is in gaps regardless — whether cached or not — when include_today=True."""
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Today is NOT cached — should be in gaps naturally
        cached = set()
        gaps = engine.compute_gaps(yesterday, tomorrow, cached, include_today=True)

        all_gap_dates = set()
        for gap in gaps:
            d = date.fromisoformat(gap.start)
            end_d = date.fromisoformat(gap.end)
            while d < end_d:
                all_gap_dates.add(d.isoformat())
                d += timedelta(days=1)

        assert today in all_gap_dates


class TestComputeGapsEdgeCases:
    """Edge case tests."""

    def test_month_boundary(self, engine):
        """Handles date ranges spanning month boundaries."""
        cached = {'2024-01-31'}
        gaps = engine.compute_gaps('2024-01-30', '2024-02-02', cached, include_today=False)
        assert gaps == [
            DateRange(start='2024-01-30', end='2024-01-31'),
            DateRange(start='2024-02-01', end='2024-02-02'),
        ]

    def test_year_boundary(self, engine):
        """Handles date ranges spanning year boundaries."""
        gaps = engine.compute_gaps('2023-12-30', '2024-01-03', set(), include_today=False)
        assert gaps == [DateRange(start='2023-12-30', end='2024-01-03')]

    def test_leap_year_feb_29(self, engine):
        """Handles Feb 29 in leap years."""
        gaps = engine.compute_gaps('2024-02-28', '2024-03-01', set(), include_today=False)
        assert gaps == [DateRange(start='2024-02-28', end='2024-03-01')]

    def test_large_range_30_days(self, engine):
        """Handles a typical 30-day dashboard range."""
        start = '2024-01-01'
        end = '2024-01-31'
        # Cache every other day
        cached = {f'2024-01-{d:02d}' for d in range(1, 31, 2)}
        gaps = engine.compute_gaps(start, end, cached, include_today=False)

        # Verify all gap dates are not in cached
        for gap in gaps:
            d = date.fromisoformat(gap.start)
            end_d = date.fromisoformat(gap.end)
            while d < end_d:
                assert d.isoformat() not in cached
                d += timedelta(days=1)

    def test_cached_dates_outside_range_ignored(self, engine):
        """Cached dates outside the requested range don't affect results."""
        cached = {'2023-12-31', '2024-01-05', '2024-02-01'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-05', cached, include_today=False)
        # Only 2024-01-05 is outside range (end is exclusive), so all 4 days are missing
        assert gaps == [DateRange(start='2024-01-01', end='2024-01-05')]


class TestComputeGapsDateRangeConvention:
    """Tests verifying the CE API convention (start inclusive, end exclusive)."""

    def test_end_date_is_exclusive(self, engine):
        """The end date itself should NOT be included in gaps."""
        # Range [Jan 1, Jan 4) means Jan 1, 2, 3 only
        gaps = engine.compute_gaps('2024-01-01', '2024-01-04', set(), include_today=False)
        assert gaps == [DateRange(start='2024-01-01', end='2024-01-04')]

        # Verify the gap covers exactly 3 days
        d = date.fromisoformat(gaps[0].start)
        end_d = date.fromisoformat(gaps[0].end)
        days_count = (end_d - d).days
        assert days_count == 3

    def test_returned_gaps_follow_exclusive_end(self, engine):
        """Each returned DateRange has exclusive end date."""
        cached = {'2024-01-02'}
        gaps = engine.compute_gaps('2024-01-01', '2024-01-04', cached, include_today=False)
        # Missing: Jan 1, Jan 3
        assert gaps == [
            DateRange(start='2024-01-01', end='2024-01-02'),
            DateRange(start='2024-01-03', end='2024-01-04'),
        ]
        # Each gap's end is exclusive — gap 1 covers only Jan 1, gap 2 covers only Jan 3


class TestPlaceholderMethods:
    """Tests for placeholder methods that will be implemented later."""

    def test_fetch_cost_data_returns_empty_for_no_ranges(self, engine):
        """fetch_cost_data returns empty list when given no date ranges."""
        result = engine.fetch_cost_data([], {})
        assert result == []


class TestMergeResults:
    """Tests for merge_results (Task 5.5)."""

    def test_empty_both_returns_empty(self, engine):
        """Merging two empty lists returns empty list."""
        result = engine.merge_results([], [])
        assert result == []

    def test_cached_only_returns_sorted(self, engine):
        """When only cached items exist, return them sorted by date."""
        cached = [
            CostDataItem(date='2024-01-03', cost_amount=30.0, currency='USD', fetched_at='2024-01-04T00:00:00Z'),
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD', fetched_at='2024-01-02T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=20.0, currency='USD', fetched_at='2024-01-03T00:00:00Z'),
        ]
        result = engine.merge_results(cached, [])
        assert [item.date for item in result] == ['2024-01-01', '2024-01-02', '2024-01-03']

    def test_fetched_only_returns_sorted(self, engine):
        """When only fetched items exist, return them sorted by date."""
        fetched = [
            CostDataItem(date='2024-01-05', cost_amount=50.0, currency='USD', fetched_at='2024-01-06T00:00:00Z'),
            CostDataItem(date='2024-01-04', cost_amount=40.0, currency='USD', fetched_at='2024-01-06T00:00:00Z'),
        ]
        result = engine.merge_results([], fetched)
        assert [item.date for item in result] == ['2024-01-04', '2024-01-05']

    def test_no_overlap_combines_all(self, engine):
        """Non-overlapping items are all included in the result."""
        cached = [
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD', fetched_at='2024-01-02T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=20.0, currency='USD', fetched_at='2024-01-03T00:00:00Z'),
        ]
        fetched = [
            CostDataItem(date='2024-01-03', cost_amount=30.0, currency='USD', fetched_at='2024-01-04T00:00:00Z'),
            CostDataItem(date='2024-01-04', cost_amount=40.0, currency='USD', fetched_at='2024-01-05T00:00:00Z'),
        ]
        result = engine.merge_results(cached, fetched)
        assert len(result) == 4
        assert [item.date for item in result] == ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04']

    def test_overlap_prefers_fetched(self, engine):
        """For overlapping dates, fetched (fresh) data wins over cached."""
        cached = [
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD', fetched_at='2024-01-02T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=20.0, currency='USD', fetched_at='2024-01-03T00:00:00Z'),
        ]
        fetched = [
            CostDataItem(date='2024-01-02', cost_amount=25.0, currency='USD', fetched_at='2024-01-04T00:00:00Z'),
        ]
        result = engine.merge_results(cached, fetched)
        assert len(result) == 2
        # Jan 2 should have the fetched value (25.0), not cached (20.0)
        jan2 = next(item for item in result if item.date == '2024-01-02')
        assert jan2.cost_amount == 25.0
        assert jan2.fetched_at == '2024-01-04T00:00:00Z'

    def test_all_overlapping_prefers_fetched(self, engine):
        """When all dates overlap, all items come from fetched."""
        cached = [
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD',
                         service_breakdown={'EC2': 10.0}, fetched_at='2024-01-02T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=20.0, currency='USD',
                         service_breakdown={'EC2': 20.0}, fetched_at='2024-01-03T00:00:00Z'),
        ]
        fetched = [
            CostDataItem(date='2024-01-01', cost_amount=15.0, currency='USD',
                         service_breakdown={'EC2': 12.0, 'S3': 3.0}, fetched_at='2024-01-05T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=22.0, currency='USD',
                         service_breakdown={'EC2': 22.0}, fetched_at='2024-01-05T00:00:00Z'),
        ]
        result = engine.merge_results(cached, fetched)
        assert len(result) == 2
        assert result[0].cost_amount == 15.0
        assert result[0].service_breakdown == {'EC2': 12.0, 'S3': 3.0}
        assert result[1].cost_amount == 22.0

    def test_result_sorted_ascending(self, engine):
        """Result is always sorted by date ascending regardless of input order."""
        cached = [
            CostDataItem(date='2024-01-05', cost_amount=50.0, currency='USD', fetched_at='2024-01-06T00:00:00Z'),
        ]
        fetched = [
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD', fetched_at='2024-01-06T00:00:00Z'),
            CostDataItem(date='2024-01-10', cost_amount=100.0, currency='USD', fetched_at='2024-01-11T00:00:00Z'),
            CostDataItem(date='2024-01-03', cost_amount=30.0, currency='USD', fetched_at='2024-01-06T00:00:00Z'),
        ]
        result = engine.merge_results(cached, fetched)
        dates = [item.date for item in result]
        assert dates == sorted(dates)

    def test_service_breakdown_preserved(self, engine):
        """Service breakdown dict is preserved correctly in merged results."""
        cached = [
            CostDataItem(date='2024-01-01', cost_amount=42.57, currency='USD',
                         service_breakdown={'Amazon EC2': 25.30, 'Amazon S3': 8.12, 'AWS Lambda': 5.15, 'Amazon RDS': 4.00},
                         fetched_at='2024-01-02T08:30:00Z'),
        ]
        result = engine.merge_results(cached, [])
        assert result[0].service_breakdown == {'Amazon EC2': 25.30, 'Amazon S3': 8.12, 'AWS Lambda': 5.15, 'Amazon RDS': 4.00}

    def test_partial_overlap_mixed(self, engine):
        """Mix of overlapping and non-overlapping dates handled correctly."""
        cached = [
            CostDataItem(date='2024-01-01', cost_amount=10.0, currency='USD', fetched_at='2024-01-02T00:00:00Z'),
            CostDataItem(date='2024-01-02', cost_amount=20.0, currency='USD', fetched_at='2024-01-03T00:00:00Z'),
            CostDataItem(date='2024-01-03', cost_amount=30.0, currency='USD', fetched_at='2024-01-04T00:00:00Z'),
        ]
        fetched = [
            CostDataItem(date='2024-01-02', cost_amount=25.0, currency='USD', fetched_at='2024-01-05T00:00:00Z'),
            CostDataItem(date='2024-01-04', cost_amount=40.0, currency='USD', fetched_at='2024-01-05T00:00:00Z'),
        ]
        result = engine.merge_results(cached, fetched)
        assert len(result) == 4
        assert [item.date for item in result] == ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04']
        # Jan 1 and Jan 3 from cache, Jan 2 and Jan 4 from fetched
        assert result[0].cost_amount == 10.0  # cached
        assert result[1].cost_amount == 25.0  # fetched (overwrites 20.0)
        assert result[2].cost_amount == 30.0  # cached
        assert result[3].cost_amount == 40.0  # fetched (new)
