"""Property-based tests for DataSourceQueryEngine timeframe validation.

Tests the timeframe validation logic using hypothesis to verify that:
- Invalid date ranges (start_date > end_date, span > 365 days) are rejected
- Valid date ranges (start_date <= end_date and span <= 365 days) are accepted

Validates: Requirements 4.4, 4.5, 4.6
"""

import sys
import os
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_query import DataSourceQueryEngine
from constants import MAX_DATE_RANGE_DAYS


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy for generating valid dates (between 2023-01-01 and 2025-12-31)
valid_dates = st.dates(
    min_value=date(2023, 1, 1),
    max_value=date(2025, 12, 31)
)


class TestTimeframeValidationProperties:
    """Property-based tests for timeframe validation.
    
    **Validates: Requirements 4.4, 4.5, 4.6**
    
    Requirement 4.4: Invalid timeframe (start > end) must be rejected
    Requirement 4.5: Date range span > 365 days must be rejected
    Requirement 4.6: Valid date ranges (start <= end and span <= 365) must be accepted
    """

    @given(start_date=valid_dates, end_date=valid_dates)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture]
    )
    def test_reject_invalid_date_ranges_start_after_end(
        self, engine, start_date, end_date
    ):
        """Property: start_date > end_date is always rejected.
        
        For any pair of dates where start_date > end_date,
        the validation must raise ValueError.
        """
        # Only test when start_date > end_date
        if start_date <= end_date:
            return
        
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        with pytest.raises(ValueError) as exc_info:
            engine._resolve_custom_range(start_str, end_str)
        
        error_msg = str(exc_info.value).lower()
        assert "start" in error_msg or "date" in error_msg, \
            f"Expected error about start_date, got: {exc_info.value}"

    @given(start_date=valid_dates)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_reject_date_range_exceeding_365_days(self, engine, start_date):
        """Property: Date range span > 365 days is always rejected.
        
        For any start_date, if end_date is more than 365 days away,
        the validation must raise ValueError.
        """
        # Create an end date that is exactly 366 days after start_date
        end_date = start_date + timedelta(days=366)
        
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        with pytest.raises(ValueError) as exc_info:
            engine._resolve_custom_range(start_str, end_str)
        
        error_msg = str(exc_info.value).lower()
        assert "365" in error_msg or "span" in error_msg or "exceeds" in error_msg, \
            f"Expected error about 365 day limit, got: {exc_info.value}"

    @given(start_date=valid_dates, offset_days=st.integers(min_value=0, max_value=365))
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_accept_valid_date_ranges(self, engine, start_date, offset_days):
        """Property: All date ranges where start_date <= end_date and span <= 365 are accepted.
        
        For any pair of dates where start_date <= end_date and the span is
        at most 365 days, the validation must succeed and return the dates.
        """
        end_date = start_date + timedelta(days=offset_days)
        
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        # Should not raise an exception
        result_start, result_end = engine._resolve_custom_range(start_str, end_str)
        
        # Verify the returned values are correct
        assert result_start == start_str
        assert result_end == end_str
        
        # Verify the dates are valid
        result_start_date = datetime.strptime(result_start, "%Y-%m-%d").date()
        result_end_date = datetime.strptime(result_end, "%Y-%m-%d").date()
        
        assert result_start_date <= result_end_date
        assert (result_end_date - result_start_date).days <= MAX_DATE_RANGE_DAYS

    @given(start_date=valid_dates)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_accept_same_date_range(self, engine, start_date):
        """Property: Date range with same start and end date is accepted.
        
        Edge case: A one-day range (start_date == end_date) should always be valid.
        """
        date_str = start_date.isoformat()
        
        result_start, result_end = engine._resolve_custom_range(date_str, date_str)
        
        assert result_start == date_str
        assert result_end == date_str

    @given(start_date=valid_dates)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_accept_exactly_365_day_range(self, engine, start_date):
        """Property: Date range with exactly 365 day span is accepted.
        
        Edge case: Maximum allowed span (365 days) should be valid.
        """
        end_date = start_date + timedelta(days=365)
        
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        result_start, result_end = engine._resolve_custom_range(start_str, end_str)
        
        assert result_start == start_str
        assert result_end == end_str
        
        span = (datetime.strptime(result_end, "%Y-%m-%d").date() - 
                datetime.strptime(result_start, "%Y-%m-%d").date()).days
        assert span == 365


class TestTimeframeValidationEdgeCases:
    """Edge case unit tests for timeframe validation."""

    def test_reject_malformed_start_date(self, engine):
        """Invalid start_date format is rejected."""
        with pytest.raises(ValueError) as exc_info:
            engine._resolve_custom_range("2024/01/01", "2024-01-31")
        
        error_msg = str(exc_info.value).lower()
        assert "start" in error_msg or "format" in error_msg

    def test_reject_malformed_end_date(self, engine):
        """Invalid end_date format is rejected."""
        with pytest.raises(ValueError) as exc_info:
            engine._resolve_custom_range("2024-01-01", "2024/01/31")
        
        error_msg = str(exc_info.value).lower()
        assert "end" in error_msg or "format" in error_msg

    def test_reject_none_start_date(self, engine):
        """None as start_date is rejected."""
        with pytest.raises((ValueError, TypeError)):
            engine._resolve_custom_range(None, "2024-01-31")

    def test_reject_none_end_date(self, engine):
        """None as end_date is rejected."""
        with pytest.raises((ValueError, TypeError)):
            engine._resolve_custom_range("2024-01-01", None)

    def test_accept_leap_year_date(self, engine):
        """Valid date on leap year (Feb 29) is accepted."""
        result_start, result_end = engine._resolve_custom_range("2024-02-29", "2024-02-29")
        
        assert result_start == "2024-02-29"
        assert result_end == "2024-02-29"

    def test_accept_year_boundary_range(self, engine):
        """Date range crossing year boundary is accepted."""
        result_start, result_end = engine._resolve_custom_range("2023-12-01", "2024-01-31")
        
        assert result_start == "2023-12-01"
        assert result_end == "2024-01-31"


class TestTimeframeValidationDocumentation:
    """Tests that verify documented behavior of timeframe validation."""

    def test_valid_7_day_range(self, engine):
        """Documentation example: 7-day range is valid."""
        result_start, result_end = engine._resolve_custom_range(
            "2024-01-01", "2024-01-07"
        )
        assert result_start == "2024-01-01"
        assert result_end == "2024-01-07"

    def test_valid_30_day_range(self, engine):
        """Documentation example: 30-day range is valid."""
        result_start, result_end = engine._resolve_custom_range(
            "2024-01-01", "2024-01-31"
        )
        assert result_start == "2024-01-01"
        assert result_end == "2024-01-31"

    def test_invalid_exceeds_365_days_by_one(self, engine):
        """Date range 366 days is rejected."""
        with pytest.raises(ValueError):
            engine._resolve_custom_range("2024-01-01", "2025-01-01")

    def test_valid_max_allowed_range(self, engine):
        """Maximum allowed range (365 days) is accepted."""
        # 2024 is a leap year, so 2024-01-01 to 2025-01-01 is 366 days.
        # Use 2024-01-01 to 2024-12-31 (364 days) as the max range example.
        result_start, result_end = engine._resolve_custom_range(
            "2024-01-01", "2024-12-31"
        )
        assert result_start == "2024-01-01"
        assert result_end == "2024-12-31"
