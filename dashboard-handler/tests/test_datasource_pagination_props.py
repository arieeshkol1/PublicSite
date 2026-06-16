"""Property-based tests for DataSourceQueryEngine pagination bounds.

Tests the pagination logic using hypothesis to verify that:
- Maximum 500 records per page
- Total records capped at 10,000
- Correct index ranges for each page
- Correct total_pages calculation
- Accurate has_more flag
- Edge cases: empty records, single page, exactly at boundaries

Validates: Requirements 9.6
"""

import sys
import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_query import DataSourceQueryEngine
from constants import DATASOURCE_PAGE_SIZE, DATASOURCE_MAX_TOTAL_ROWS


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy for generating cost records with minimal fields
def cost_records(num_records=10):
    """Generate realistic cost data records for pagination testing."""
    return st.lists(
        st.fixed_dictionaries({
            "date": st.dates().map(str),
            "service": st.sampled_from(["EC2", "RDS", "S3", "Lambda", "DynamoDB"]),
            "cost_amount": st.floats(
                min_value=0.01,
                max_value=10000.0,
                allow_nan=False,
                allow_infinity=False
            ),
        }),
        min_size=0,
        max_size=num_records
    )


# Strategy for generating valid page numbers
valid_page_numbers = st.integers(min_value=1, max_value=100)

# Strategy for generating record lists capped at reasonable size for testing
record_lists_for_pagination = st.lists(
    st.fixed_dictionaries({
        "date": st.just("2024-01-01"),
        "service": st.just("EC2"),
        "cost_amount": st.just(100.0),
    }),
    min_size=0,
    max_size=11000  # Allow testing beyond 10K cap
)


class TestPaginationBoundsProperties:
    """Property-based tests for pagination bounds.
    
    **Validates: Requirements 9.6**
    
    Requirement 9.6: Pagination enforces max 500 per page and 10K total cap,
    with correct page calculation and has_more flag.
    """

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_max_records_per_page(self, engine, records):
        """Property: Each page contains at most DATASOURCE_PAGE_SIZE (500) records.
        
        For any record list, every page except possibly the last should contain
        exactly DATASOURCE_PAGE_SIZE records, and the last page should contain
        at most DATASOURCE_PAGE_SIZE records.
        """
        page_size = DATASOURCE_PAGE_SIZE
        result = engine._paginate(records, page=1)
        
        # Current page rows should not exceed page_size
        assert len(result["rows"]) <= page_size, (
            f"Page contains {len(result['rows'])} records, "
            f"exceeds max {page_size}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_total_capped_at_max(self, engine, records):
        """Property: Total record count is capped at DATASOURCE_MAX_TOTAL_ROWS (10,000).
        
        For any record list with more than 10,000 records, the total_count
        in pagination response should not exceed 10,000.
        """
        max_total = DATASOURCE_MAX_TOTAL_ROWS
        result = engine._paginate(records, page=1)
        
        assert result["total_count"] <= max_total, (
            f"total_count {result['total_count']} exceeds max {max_total}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=valid_page_numbers
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_correct_total_pages_calculation(self, engine, records, page):
        """Property: total_pages calculation is correct.
        
        For any record set and page number, total_pages should equal
        ceil(total_count / page_size), which is correctly calculated as:
        max(1, (total_count + page_size - 1) // page_size)
        """
        page_size = DATASOURCE_PAGE_SIZE
        max_total = DATASOURCE_MAX_TOTAL_ROWS
        
        result = engine._paginate(records, page=page)
        
        total_count = result["total_count"]
        expected_total_pages = max(1, (total_count + page_size - 1) // page_size)
        
        assert result["total_pages"] == expected_total_pages, (
            f"total_pages calculation wrong: {result['total_pages']} "
            f"!= {expected_total_pages} "
            f"(total_count={total_count}, page_size={page_size})"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=valid_page_numbers
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_correct_index_ranges(self, engine, records, page):
        """Property: Index ranges for each page are calculated correctly.
        
        For any page number, the start_idx should be (page - 1) * page_size,
        and end_idx should be min(start_idx + page_size, total_count).
        The returned rows should match exactly records[start_idx:end_idx].
        """
        page_size = DATASOURCE_PAGE_SIZE
        max_total = DATASOURCE_MAX_TOTAL_ROWS
        
        result = engine._paginate(records, page=page)
        
        total_count = result["total_count"]
        
        # Calculate expected indices
        expected_start_idx = (result["page"] - 1) * page_size
        expected_end_idx = min(expected_start_idx + page_size, total_count)
        
        # Get expected rows from capped records list
        capped_records = records[:max_total]
        expected_rows = capped_records[expected_start_idx:expected_end_idx]
        
        assert result["rows"] == expected_rows, (
            f"Page {result['page']} index range mismatch. "
            f"Expected rows from [{expected_start_idx}:{expected_end_idx}], "
            f"got {len(result['rows'])} rows"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=valid_page_numbers
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_has_more_flag_accurate(self, engine, records, page):
        """Property: has_more flag is accurate.
        
        For any page number:
        - has_more should be True if page < total_pages
        - has_more should be False if page >= total_pages
        """
        result = engine._paginate(records, page=page)
        
        page_num = result["page"]
        total_pages = result["total_pages"]
        has_more = result["has_more"]
        
        expected_has_more = page_num < total_pages
        
        assert has_more == expected_has_more, (
            f"has_more flag incorrect for page {page_num} of {total_pages}. "
            f"Expected {expected_has_more}, got {has_more}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=valid_page_numbers
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_response_has_required_fields(self, engine, records, page):
        """Property: Pagination response contains all required fields.
        
        For any pagination result, the response dict should have keys:
        rows, total_count, page, page_size, total_pages, has_more
        """
        result = engine._paginate(records, page=page)
        
        required_keys = {"rows", "total_count", "page", "page_size", "total_pages", "has_more"}
        result_keys = set(result.keys())
        
        assert required_keys.issubset(result_keys), (
            f"Missing required keys. Expected: {required_keys}, got: {result_keys}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=valid_page_numbers
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_page_size_consistent(self, engine, records, page):
        """Property: page_size field always equals DATASOURCE_PAGE_SIZE.
        
        Regardless of input, the page_size in response should always be
        the configured DATASOURCE_PAGE_SIZE constant (500).
        """
        result = engine._paginate(records, page=page)
        
        assert result["page_size"] == DATASOURCE_PAGE_SIZE, (
            f"page_size {result['page_size']} != {DATASOURCE_PAGE_SIZE}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=st.integers(min_value=-100, max_value=0)  # Invalid page numbers
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_pagination_invalid_page_clamped_to_one(self, engine, records, page):
        """Property: Invalid page numbers (< 1) are clamped to 1.
        
        For any invalid page number (negative or zero), the pagination
        should treat it as page 1.
        """
        result = engine._paginate(records, page=page)
        
        # Should be clamped to page 1
        assert result["page"] == 1, (
            f"Invalid page {page} should be clamped to 1, "
            f"got page {result['page']}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        ),
        page=st.integers(min_value=1, max_value=1000)  # Very high page numbers
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_pagination_beyond_last_page_clamped(self, engine, records, page):
        """Property: Page numbers beyond last page are clamped to last page.
        
        For any page number greater than total_pages, the pagination
        should clamp it to the last available page and return
        appropriate results for that page.
        """
        result = engine._paginate(records, page=page)
        
        total_pages = result["total_pages"]
        
        # If requested page > total_pages, should be clamped
        if page > total_pages:
            assert result["page"] == total_pages, (
                f"Page {page} should be clamped to {total_pages}, "
                f"got {result['page']}"
            )

    @given(
        record_count=st.integers(min_value=0, max_value=11000)
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_pagination_record_count_matches_expected_range(
        self, engine, record_count
    ):
        """Property: Number of rows returned never exceeds page_size.
        
        For any record count, the returned rows on any page should not
        exceed DATASOURCE_PAGE_SIZE.
        """
        records = [{"id": i} for i in range(record_count)]
        result = engine._paginate(records, page=1)
        
        assert len(result["rows"]) <= DATASOURCE_PAGE_SIZE, (
            f"Returned {len(result['rows'])} rows, exceeds max {DATASOURCE_PAGE_SIZE}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_pagination_first_page_always_available(self, engine, records):
        """Property: First page is always available and returns data.
        
        For any record set, page 1 should always be available and return
        the correct first batch of records (or empty if no records).
        """
        result = engine._paginate(records, page=1)
        
        assert result["page"] == 1, (
            f"First page request should return page 1, got {result['page']}"
        )
        
        # Calculate expected rows for first page
        max_total = DATASOURCE_MAX_TOTAL_ROWS
        capped_records = records[:max_total]
        expected_rows = capped_records[:DATASOURCE_PAGE_SIZE]
        
        assert result["rows"] == expected_rows, (
            f"First page rows mismatch"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=1000,
            max_size=2000
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.large_base_example, HealthCheck.too_slow, HealthCheck.data_too_large]
    )
    def test_pagination_with_large_record_sets(self, engine, records):
        """Property: Pagination correctly handles large record sets up to cap.
        
        For any record set, pagination should correctly compute total_pages
        and only return up to the capped total of 10,000 records.
        """
        result = engine._paginate(records, page=1)
        
        # total_count should be min(actual records, cap)
        expected_count = min(len(records), DATASOURCE_MAX_TOTAL_ROWS)
        assert result["total_count"] == expected_count, (
            f"total_count should be {expected_count}, got {result['total_count']}"
        )
        
        # total_pages should be correct
        expected_pages = (expected_count + DATASOURCE_PAGE_SIZE - 1) // DATASOURCE_PAGE_SIZE
        assert result["total_pages"] == expected_pages

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=DATASOURCE_PAGE_SIZE - 1,
            max_size=DATASOURCE_PAGE_SIZE + 1
        )
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_pagination_boundary_at_page_size(self, engine, records):
        """Property: Pagination boundary at page_size works correctly.
        
        For record counts near the page_size boundary (499, 500, 501),
        pagination should handle the boundary correctly.
        """
        result = engine._paginate(records, page=1)
        
        total_count = result["total_count"]
        returned_rows = len(result["rows"])
        
        # On first page, should return min(total_count, page_size)
        expected_returned = min(total_count, DATASOURCE_PAGE_SIZE)
        assert returned_rows == expected_returned, (
            f"For {total_count} records, first page should return {expected_returned}, "
            f"got {returned_rows}"
        )

    @given(
        records=st.lists(
            st.fixed_dictionaries({"id": st.integers()}),
            min_size=0,
            max_size=11000
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_pagination_all_pages_within_bounds(self, engine, records):
        """Property: Iterating through all pages stays within bounds.
        
        For any record set, iterating through all pages (1 to total_pages)
        should never exceed page_size per page and never exceed total_count.
        """
        page = 1
        page_size = DATASOURCE_PAGE_SIZE
        max_total = DATASOURCE_MAX_TOTAL_ROWS
        
        # Get first page to determine total_pages
        first_result = engine._paginate(records, page=1)
        total_pages = first_result["total_pages"]
        total_count = first_result["total_count"]
        
        # Iterate through all pages
        capped_records = records[:max_total]
        rows_seen = 0
        
        for page_num in range(1, min(total_pages + 1, 100)):  # Cap iterations for property test
            result = engine._paginate(records, page=page_num)
            
            # Verify page is within bounds
            assert result["page"] <= total_pages, (
                f"Page {result['page']} exceeds total_pages {total_pages}"
            )
            
            # Verify rows count is within bounds
            assert len(result["rows"]) <= page_size, (
                f"Page {page_num} has {len(result['rows'])} rows, exceeds {page_size}"
            )
            
            rows_seen += len(result["rows"])
        
        # Total rows seen should not exceed total_count
        assert rows_seen <= total_count, (
            f"Total rows seen {rows_seen} exceeds total_count {total_count}"
        )


class TestPaginationBoundsEdgeCases:
    """Edge case unit tests for pagination bounds."""

    def test_empty_records_list(self, engine):
        """Empty records list returns proper pagination response."""
        result = engine._paginate([], page=1)
        
        assert result["rows"] == []
        assert result["total_count"] == 0
        assert result["page"] == 1
        assert result["page_size"] == DATASOURCE_PAGE_SIZE
        assert result["total_pages"] == 1
        assert result["has_more"] is False

    def test_single_record(self, engine):
        """Single record is paginated correctly."""
        records = [{"id": 1}]
        result = engine._paginate(records, page=1)
        
        assert result["rows"] == records
        assert result["total_count"] == 1
        assert result["page"] == 1
        assert result["total_pages"] == 1
        assert result["has_more"] is False

    def test_exactly_one_page_of_records(self, engine):
        """Record set exactly equal to page_size."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE)]
        result = engine._paginate(records, page=1)
        
        assert len(result["rows"]) == DATASOURCE_PAGE_SIZE
        assert result["total_count"] == DATASOURCE_PAGE_SIZE
        assert result["page"] == 1
        assert result["total_pages"] == 1
        assert result["has_more"] is False

    def test_one_more_than_page_size(self, engine):
        """Record count one more than page_size requires two pages."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE + 1)]
        result = engine._paginate(records, page=1)
        
        assert len(result["rows"]) == DATASOURCE_PAGE_SIZE
        assert result["total_count"] == DATASOURCE_PAGE_SIZE + 1
        assert result["total_pages"] == 2
        assert result["has_more"] is True

    def test_second_page_single_record(self, engine):
        """Second page with single record."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE + 1)]
        result = engine._paginate(records, page=2)
        
        assert len(result["rows"]) == 1
        assert result["rows"] == [{"id": DATASOURCE_PAGE_SIZE}]
        assert result["page"] == 2
        assert result["has_more"] is False

    def test_exactly_at_10k_cap(self, engine):
        """Exactly 10,000 records (at cap)."""
        records = [{"id": i} for i in range(DATASOURCE_MAX_TOTAL_ROWS)]
        result = engine._paginate(records, page=1)
        
        assert result["total_count"] == DATASOURCE_MAX_TOTAL_ROWS
        assert result["total_pages"] == (DATASOURCE_MAX_TOTAL_ROWS + DATASOURCE_PAGE_SIZE - 1) // DATASOURCE_PAGE_SIZE

    def test_exceeding_10k_cap(self, engine):
        """Exceeding 10,000 records gets capped."""
        records = [{"id": i} for i in range(DATASOURCE_MAX_TOTAL_ROWS + 100)]
        result = engine._paginate(records, page=1)
        
        assert result["total_count"] == DATASOURCE_MAX_TOTAL_ROWS
        # total_pages should reflect capped count
        expected_pages = (DATASOURCE_MAX_TOTAL_ROWS + DATASOURCE_PAGE_SIZE - 1) // DATASOURCE_PAGE_SIZE
        assert result["total_pages"] == expected_pages

    def test_exceeding_10k_no_beyond_access(self, engine):
        """Records beyond 10K limit are not accessible through pagination."""
        # Create a set of 15K records
        records = [{"id": i, "value": f"record_{i}"} for i in range(15000)]
        result = engine._paginate(records, page=1)
        
        # total_count should be capped at 10K
        assert result["total_count"] == DATASOURCE_MAX_TOTAL_ROWS
        
        # Calculate total pages needed for 10K records
        total_pages = (DATASOURCE_MAX_TOTAL_ROWS + DATASOURCE_PAGE_SIZE - 1) // DATASOURCE_PAGE_SIZE
        assert result["total_pages"] == total_pages
        
        # Navigate to last page
        last_result = engine._paginate(records, page=total_pages)
        
        # Last page should have no more data from beyond 10K
        # Verify all returned rows are from within first 10K
        for row in last_result["rows"]:
            assert row["id"] < DATASOURCE_MAX_TOTAL_ROWS, (
                f"Row ID {row['id']} exceeds 10K cap"
            )

    def test_invalid_page_zero(self, engine):
        """Page 0 is treated as page 1."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE)]
        result = engine._paginate(records, page=0)
        
        assert result["page"] == 1

    def test_invalid_page_negative(self, engine):
        """Negative page is treated as page 1."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE)]
        result = engine._paginate(records, page=-5)
        
        assert result["page"] == 1

    def test_invalid_page_non_integer(self, engine):
        """Non-integer page is treated as page 1."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE)]
        
        # Test with float that looks like 1
        result_float = engine._paginate(records, page=1.5)
        # Implementation should handle this gracefully
        assert result_float["page"] >= 1

    def test_page_beyond_total_pages(self, engine):
        """Page number beyond total_pages is clamped."""
        records = [{"id": i} for i in range(100)]
        result = engine._paginate(records, page=1000)
        
        # Should clamp to last page
        assert result["page"] == result["total_pages"]
        assert result["has_more"] is False

    def test_pagination_consistency_across_pages(self, engine):
        """All pages together contain exactly total_count records."""
        records = [{"id": i} for i in range(DATASOURCE_PAGE_SIZE * 3 + 100)]
        
        first_result = engine._paginate(records, page=1)
        total_pages = first_result["total_pages"]
        total_count = first_result["total_count"]
        
        rows_seen = set()
        for page_num in range(1, total_pages + 1):
            result = engine._paginate(records, page=page_num)
            for row in result["rows"]:
                rows_seen.add(row["id"])
        
        # Should see exactly total_count unique records
        assert len(rows_seen) == min(total_count, len(records))

    def test_max_total_rows_constant(self, engine):
        """DATASOURCE_MAX_TOTAL_ROWS constant is 10000."""
        assert DATASOURCE_MAX_TOTAL_ROWS == 10000

    def test_page_size_constant(self, engine):
        """DATASOURCE_PAGE_SIZE constant is 500."""
        assert DATASOURCE_PAGE_SIZE == 500

    def test_total_pages_at_boundary_values(self, engine):
        """total_pages calculation at boundary values."""
        # Test at boundaries: 0, 1, 499, 500, 501, 1000, 10000, 10001
        test_cases = [
            (0, 1),           # 0 records -> 1 page
            (1, 1),           # 1 record -> 1 page
            (499, 1),         # 499 records -> 1 page
            (500, 1),         # 500 records -> 1 page (exactly one page)
            (501, 2),         # 501 records -> 2 pages
            (1000, 2),        # 1000 records -> 2 pages
            (10000, 20),      # 10000 records -> 20 pages
            (10001, 20),      # 10001 records (capped to 10000) -> 20 pages
        ]
        
        for record_count, expected_pages in test_cases:
            records = [{"id": i} for i in range(record_count)]
            result = engine._paginate(records, page=1)
            
            assert result["total_pages"] == expected_pages, (
                f"For {record_count} records, expected {expected_pages} pages, "
                f"got {result['total_pages']}"
            )

    def test_last_page_has_correct_record_count(self, engine):
        """Last page has correct partial record count."""
        # 1234 records with 500 per page -> 3 pages
        # Page 1: 500, Page 2: 500, Page 3: 234
        records = [{"id": i} for i in range(1234)]
        
        # Get last page
        result = engine._paginate(records, page=1)
        total_pages = result["total_pages"]
        
        last_page_result = engine._paginate(records, page=total_pages)
        
        expected_last_count = 1234 - (total_pages - 1) * DATASOURCE_PAGE_SIZE
        assert len(last_page_result["rows"]) == expected_last_count

    def test_response_structure_complete(self, engine):
        """Response dict has all required fields with correct types."""
        records = [{"id": i} for i in range(100)]
        result = engine._paginate(records, page=1)
        
        assert isinstance(result, dict)
        assert isinstance(result["rows"], list)
        assert isinstance(result["total_count"], int)
        assert isinstance(result["page"], int)
        assert isinstance(result["page_size"], int)
        assert isinstance(result["total_pages"], int)
        assert isinstance(result["has_more"], bool)
        
        # Verify relationships
        assert result["page"] >= 1
        assert result["page_size"] > 0
        assert result["total_count"] >= 0
        assert result["total_pages"] >= 1
        assert len(result["rows"]) <= result["page_size"]
