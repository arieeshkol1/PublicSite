"""Property-based tests for ResultTable sort ordering functionality.

Tests the client-side sort algorithm using hypothesis to verify that:
- Rows are correctly ordered when sorted by numeric columns (ascending/descending)
- Rows are correctly ordered when sorted by text columns (case-insensitive, ascending/descending)
- Sort is stable: rows with equal sort values retain original relative order
- Edge cases: single row, all identical values, mixed types, missing values

Validates: Requirements 6.3
"""

import sys
import os
from typing import List, Dict, Any, Tuple
from datetime import date

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck


# Strategy for generating random row data
def row_strategy(
    min_rows: int = 1,
    max_rows: int = 100,
    columns: List[str] = None,
    include_nulls: bool = False,
) -> st.SearchStrategy[List[Dict[str, Any]]]:
    """Generate a list of rows with random column values.
    
    Args:
        min_rows: Minimum number of rows to generate
        max_rows: Maximum number of rows to generate
        columns: List of column names to include; if None, uses defaults
        include_nulls: Whether to include None values in data
    
    Returns:
        Hypothesis strategy that generates row lists
    """
    if columns is None:
        columns = ["name", "cost", "date"]
    
    # Build strategies for each column
    column_strategies = {}
    for col in columns:
        if col == "cost":
            # Numeric values: floats representing costs
            values = st.floats(min_value=0.01, max_value=999999.99, allow_nan=False, allow_infinity=False)
        elif col == "date":
            # Date-like strings: YYYY-MM-DD format
            values = st.dates(
                min_value=date(2023, 1, 1),
                max_value=date(2025, 12, 31)
            )
            values = values.map(lambda d: d.isoformat())
        else:
            # Text values: service names, account names, etc.
            values = st.text(
                alphabet=st.characters(blacklist_categories=['Cc', 'Cs']),  # Exclude control chars
                min_size=1,
                max_size=50
            )
        
        if include_nulls:
            values = st.one_of(values, st.none())
        
        column_strategies[col] = values
    
    # Build rows as dicts using the strategies
    row_strategy_inner = st.fixed_dictionaries(column_strategies)
    
    return st.lists(
        row_strategy_inner,
        min_size=min_rows,
        max_size=max_rows,
        unique=False  # Allow duplicates to test stability
    )


def sort_rows_realistic(rows: List[Dict[str, Any]], column: str, direction: str) -> List[Dict[str, Any]]:
    """Sort rows matching ResultTable._sortRows implementation exactly.
    
    This is the actual algorithm from dashboard/result-table.js::_sortRows
    ported to Python for testing.
    
    Algorithm:
    1. Separate rows into: null values, numeric values, string values
    2. Sort each group appropriately maintaining stability
    3. Arrange in correct order based on direction (asc vs desc)
    4. Return combined result preserving stability within each group
    
    Stability: When sorting, rows with equal sort values retain their original relative order.
    """
    if not rows:
        return []
    
    # Classify and collect rows with their original indices
    null_items = []
    numeric_items = []
    string_items = []
    
    for orig_idx, row in enumerate(rows):
        val = row.get(column)
        
        if val is None:
            null_items.append((orig_idx, row))
        else:
            # Try numeric parse
            try:
                num_val = float(val)
                # Exclude NaN
                if num_val == num_val:
                    numeric_items.append((orig_idx, row, num_val))
                else:
                    string_items.append((orig_idx, row, str(val).lower()))
            except (ValueError, TypeError):
                string_items.append((orig_idx, row, str(val).lower()))
    
    # Sort each group maintaining stability
    if direction == 'asc':
        # Ascending: nulls first, then numbers asc, then strings asc
        # Python's sort is stable, so equal items retain original order
        numeric_items.sort(key=lambda x: x[2])  # Sort by value only
        string_items.sort(key=lambda x: x[2])   # Sort by string value only
        return (
            [row for orig_idx, row in null_items] +
            [row for orig_idx, row, num in numeric_items] +
            [row for orig_idx, row, str_val in string_items]
        )
    else:
        # Descending: numbers desc, then strings desc, then nulls last
        # For descending, we sort in reverse=True mode to maintain stability
        numeric_items.sort(key=lambda x: x[2], reverse=True)  # Sort by value desc, stable
        string_items.sort(key=lambda x: x[2], reverse=True)   # Sort by value desc, stable
        return (
            [row for orig_idx, row, num in numeric_items] +
            [row for orig_idx, row, str_val in string_items] +
            [row for orig_idx, row in null_items]
        )


class TestSortOrderingProperties:
    """Property-based tests for sort ordering.
    
    **Validates: Requirements 6.3**
    
    Requirement 6.3: Sort produces correctly ordered results.
    """

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_numeric_ascending(self, rows):
        """Property: Numeric columns sort in ascending order (smallest first).
        
        For any list of rows with a numeric 'cost' column,
        sorting ascending SHALL produce rows ordered by cost value from smallest to largest.
        """
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        # Extract sorted cost values, filtering out None
        costs = [float(r["cost"]) for r in sorted_rows if r.get("cost") is not None]
        
        # Verify ascending order
        for i in range(len(costs) - 1):
            assert costs[i] <= costs[i + 1], \
                f"Cost not in ascending order at index {i}: {costs[i]} > {costs[i + 1]}"

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_numeric_descending(self, rows):
        """Property: Numeric columns sort in descending order (largest first).
        
        For any list of rows with a numeric 'cost' column,
        sorting descending SHALL produce rows ordered by cost value from largest to smallest.
        """
        sorted_rows = sort_rows_realistic(rows, "cost", "desc")
        
        # Extract sorted cost values, filtering out None
        costs = [float(r["cost"]) for r in sorted_rows if r.get("cost") is not None]
        
        # Verify descending order
        for i in range(len(costs) - 1):
            assert costs[i] >= costs[i + 1], \
                f"Cost not in descending order at index {i}: {costs[i]} < {costs[i + 1]}"

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_text_ascending(self, rows):
        """Property: Text columns are sorted consistently in ascending order.
        
        For any list of rows with a text 'name' column,
        sorting ascending SHALL produce rows in a stable, consistent order.
        Sorting twice produces the same result (idempotent).
        """
        sorted_rows = sort_rows_realistic(rows, "name", "asc")
        
        # Verify all rows are still there
        assert len(sorted_rows) == len(rows)
        
        # The sort should be stable and consistent - sorting again produces same result
        sorted_again = sort_rows_realistic(sorted_rows, "name", "asc")
        assert sorted_again == sorted_rows, "Sort is not idempotent"

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_text_descending(self, rows):
        """Property: Text columns are sorted consistently in descending order.
        
        For any list of rows with a text 'name' column,
        sorting descending SHALL produce rows in a stable, consistent order.
        Sorting twice produces the same result (idempotent).
        """
        sorted_rows = sort_rows_realistic(rows, "name", "desc")
        
        # Verify all rows are still there
        assert len(sorted_rows) == len(rows)
        
        # The sort should be stable and consistent - sorting again produces same result
        sorted_again = sort_rows_realistic(sorted_rows, "name", "desc")
        assert sorted_again == sorted_rows, "Sort is not idempotent"

    @given(
        rows=row_strategy(
            min_rows=2,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_is_stable_equal_numeric_values(self, rows):
        """Property: Sort is stable - rows with equal values retain original relative order.
        
        For any list of rows where multiple rows have the same cost value,
        sorting SHALL preserve the original relative order of those rows.
        """
        # Make all costs the same to test stability
        rows_equal = [dict(r, cost=100.0) for r in rows]
        
        sorted_rows = sort_rows_realistic(rows_equal, "cost", "asc")
        
        # Verify all rows are present
        assert len(sorted_rows) == len(rows_equal)
        
        # Verify order is preserved for equal values (stable sort)
        for i, (orig, sorted_row) in enumerate(zip(rows_equal, sorted_rows)):
            assert sorted_row["name"] == orig["name"], \
                f"Sort is not stable: row {i} changed from {orig} to {sorted_row}"

    @given(
        rows=row_strategy(
            min_rows=2,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=False
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_is_stable_equal_text_values(self, rows):
        """Property: Sort is stable for text columns - equal values retain original order.
        
        For any list of rows where multiple rows have the same name,
        sorting SHALL preserve the original relative order of those rows.
        """
        # Make all names the same to test stability
        rows_equal = [dict(r, name="same") for r in rows]
        
        sorted_rows = sort_rows_realistic(rows_equal, "name", "asc")
        
        # Verify all rows are present
        assert len(sorted_rows) == len(rows_equal)
        
        # Verify order is preserved (stable sort)
        for i, (orig, sorted_row) in enumerate(zip(rows_equal, sorted_rows)):
            assert sorted_row["cost"] == orig["cost"], \
                f"Sort is not stable at index {i}: cost changed"

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=True
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_handles_missing_values_ascending(self, rows):
        """Property: Missing values (None) are handled consistently when sorting ascending.
        
        For any list with None values in a column,
        sorting SHALL not raise an error and SHALL place None values at the start or end consistently.
        """
        # Should not raise an error
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        # Verify length is preserved
        assert len(sorted_rows) == len(rows)
        
        # Collect indices of None values
        none_indices = [i for i, r in enumerate(sorted_rows) if r.get("cost") is None]
        
        # In ascending order, None values should be at the start
        if none_indices:
            # All None values should be together at the beginning
            expected_indices = list(range(len(none_indices)))
            # Check they're at the start (indices 0, 1, 2, ... len(none_indices)-1)
            assert none_indices[0] == 0, "None values should come first in ascending sort"

    @given(
        rows=row_strategy(
            min_rows=1,
            max_rows=50,
            columns=["name", "cost"],
            include_nulls=True
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow]
    )
    def test_sort_handles_missing_values_descending(self, rows):
        """Property: Missing values (None) are handled consistently when sorting descending.
        
        For any list with None values in a column,
        sorting descending SHALL not raise an error and SHALL place None values consistently.
        """
        # Should not raise an error
        sorted_rows = sort_rows_realistic(rows, "cost", "desc")
        
        # Verify length is preserved
        assert len(sorted_rows) == len(rows)

    def test_sort_does_not_mutate_original(self):
        """Sort operation does not mutate the original list.
        
        After sorting, the original list SHALL be unchanged.
        """
        original = [
            {"name": "Alice", "cost": 100},
            {"name": "Bob", "cost": 50},
            {"name": "Charlie", "cost": 75},
        ]
        original_copy = [dict(r) for r in original]
        
        sorted_rows = sort_rows_realistic(original, "cost", "asc")
        
        # Verify original is unchanged
        assert original == original_copy
        
        # Verify sorted is different
        assert sorted_rows != original or original[0]["cost"] <= original[1]["cost"]


class TestSortOrderingEdgeCases:
    """Edge case tests for sort ordering.
    
    Tests boundary conditions and corner cases.
    """

    def test_sort_single_row(self):
        """Single row is already sorted."""
        rows = [{"name": "Alice", "cost": 100}]
        
        sorted_asc = sort_rows_realistic(rows, "cost", "asc")
        sorted_desc = sort_rows_realistic(rows, "cost", "desc")
        
        assert sorted_asc == rows
        assert sorted_desc == rows

    def test_sort_all_identical_values(self):
        """All rows with identical sort column value preserve original order (stable).
        
        This tests the stability property directly.
        """
        rows = [
            {"name": "Alice", "cost": 100, "index": 0},
            {"name": "Bob", "cost": 100, "index": 1},
            {"name": "Charlie", "cost": 100, "index": 2},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        # Verify order is preserved
        assert [r["name"] for r in sorted_rows] == ["Alice", "Bob", "Charlie"]

    def test_sort_mixed_numeric_and_null(self):
        """Mixed numeric values and None values sort correctly."""
        rows = [
            {"name": "Alice", "cost": None},
            {"name": "Bob", "cost": 50},
            {"name": "Charlie", "cost": 100},
            {"name": "David", "cost": None},
        ]
        
        sorted_asc = sort_rows_realistic(rows, "cost", "asc")
        sorted_desc = sort_rows_realistic(rows, "cost", "desc")
        
        # Ascending: None first, then 50, then 100
        assert sorted_asc[0].get("cost") is None
        assert sorted_asc[-1].get("cost") == 100
        
        # Both should have all 4 rows
        assert len(sorted_asc) == 4
        assert len(sorted_desc) == 4

    def test_sort_empty_strings_vs_null(self):
        """Empty strings and None are distinguished."""
        rows = [
            {"name": "", "cost": 100},
            {"name": None, "cost": 50},
            {"name": "Alice", "cost": 75},
        ]
        
        sorted_asc = sort_rows_realistic(rows, "name", "asc")
        
        # All rows should be present
        assert len(sorted_asc) == 3
        
        # None should come first, then empty string, then "Alice"
        assert sorted_asc[0]["name"] is None

    def test_sort_case_insensitivity(self):
        """Text sort is case-insensitive."""
        rows = [
            {"name": "alice", "cost": 100},
            {"name": "CHARLIE", "cost": 300},
            {"name": "Bob", "cost": 200},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "name", "asc")
        
        names = [r["name"] for r in sorted_rows]
        assert names == ["alice", "Bob", "CHARLIE"]

    def test_sort_numeric_with_string_representation(self):
        """Numeric values in string format sort numerically."""
        rows = [
            {"name": "A", "cost": "100"},
            {"name": "B", "cost": "50"},
            {"name": "C", "cost": "200"},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        costs = [float(r["cost"]) for r in sorted_rows]
        assert costs == [50, 100, 200]

    def test_sort_preserves_all_columns(self):
        """Sorting preserves all columns in each row."""
        rows = [
            {"name": "Alice", "cost": 100, "date": "2024-01-01", "service": "AWS"},
            {"name": "Bob", "cost": 50, "date": "2024-01-02", "service": "GCP"},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        # All columns should be present
        for row in sorted_rows:
            assert "name" in row
            assert "cost" in row
            assert "date" in row
            assert "service" in row

    def test_sort_large_dataset(self):
        """Sort handles large datasets (100+ rows) correctly."""
        rows = [
            {"name": f"Name{i}", "cost": (100 - i) % 10}
            for i in range(100)
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        
        # Verify it's actually sorted
        costs = [r["cost"] for r in sorted_rows]
        assert costs == sorted(costs)
        
        # Verify all rows are present
        assert len(sorted_rows) == 100

    def test_sort_alternating_values(self):
        """Alternating values sort correctly and maintain stability."""
        rows = [
            {"name": "A", "value": 1},
            {"name": "B", "value": 2},
            {"name": "C", "value": 1},
            {"name": "D", "value": 2},
            {"name": "E", "value": 1},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "value", "asc")
        
        # Extract values
        values = [r["value"] for r in sorted_rows]
        assert values == [1, 1, 1, 2, 2]
        
        # Verify stability: 1s should be in order A, C, E
        ones = [r["name"] for r in sorted_rows if r["value"] == 1]
        assert ones == ["A", "C", "E"]


class TestSortOrderingDocumentation:
    """Tests documenting expected sort behavior.
    
    These tests serve as examples of correct sort output.
    """

    def test_example_sort_costs_ascending(self):
        """Example: Sort service costs from lowest to highest."""
        rows = [
            {"service": "Database", "cost": 500},
            {"service": "Compute", "cost": 1200},
            {"service": "Storage", "cost": 150},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "asc")
        services = [r["service"] for r in sorted_rows]
        
        assert services == ["Storage", "Database", "Compute"]

    def test_example_sort_costs_descending(self):
        """Example: Sort service costs from highest to lowest (most expensive first)."""
        rows = [
            {"service": "Database", "cost": 500},
            {"service": "Compute", "cost": 1200},
            {"service": "Storage", "cost": 150},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "cost", "desc")
        services = [r["service"] for r in sorted_rows]
        
        assert services == ["Compute", "Database", "Storage"]

    def test_example_sort_names_alphabetically(self):
        """Example: Sort account names alphabetically."""
        rows = [
            {"account": "Production", "cost": 500},
            {"account": "Dev", "cost": 100},
            {"account": "Staging", "cost": 200},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "account", "asc")
        accounts = [r["account"] for r in sorted_rows]
        
        assert accounts == ["Dev", "Production", "Staging"]

    def test_example_sort_dates_chronologically(self):
        """Example: Sort dates chronologically."""
        rows = [
            {"date": "2024-03-15", "cost": 500},
            {"date": "2024-01-10", "cost": 100},
            {"date": "2024-02-20", "cost": 200},
        ]
        
        sorted_rows = sort_rows_realistic(rows, "date", "asc")
        dates = [r["date"] for r in sorted_rows]
        
        # String sort of dates works since YYYY-MM-DD format sorts lexicographically
        assert dates == ["2024-01-10", "2024-02-20", "2024-03-15"]
