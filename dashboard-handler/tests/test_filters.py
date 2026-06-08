"""Unit tests for apply_filter and apply_filters functions."""

import sys
import os

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from filters import apply_filter, apply_filters


# ====================================================
# Tests for apply_filter - eq operator
# ====================================================


class TestApplyFilterEq:
    """Tests for the 'eq' (equals) operator."""

    def test_eq_string_match(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "eq", "value": "Amazon EC2"}
        assert apply_filter(item, f) is True

    def test_eq_string_no_match(self):
        item = {"service": "Amazon S3"}
        f = {"field": "service", "operator": "eq", "value": "Amazon EC2"}
        assert apply_filter(item, f) is False

    def test_eq_numeric_match(self):
        item = {"cost_amount": 42.5}
        f = {"field": "cost_amount", "operator": "eq", "value": 42.5}
        assert apply_filter(item, f) is True

    def test_eq_numeric_no_match(self):
        item = {"cost_amount": 42.5}
        f = {"field": "cost_amount", "operator": "eq", "value": 100.0}
        assert apply_filter(item, f) is False

    def test_eq_boolean_match(self):
        item = {"active": True}
        f = {"field": "active", "operator": "eq", "value": True}
        assert apply_filter(item, f) is True


# ====================================================
# Tests for apply_filter - neq operator
# ====================================================


class TestApplyFilterNeq:
    """Tests for the 'neq' (not equals) operator."""

    def test_neq_string_different(self):
        item = {"service": "Amazon S3"}
        f = {"field": "service", "operator": "neq", "value": "Amazon EC2"}
        assert apply_filter(item, f) is True

    def test_neq_string_same(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "neq", "value": "Amazon EC2"}
        assert apply_filter(item, f) is False

    def test_neq_numeric_different(self):
        item = {"cost_amount": 50.0}
        f = {"field": "cost_amount", "operator": "neq", "value": 42.5}
        assert apply_filter(item, f) is True

    def test_neq_numeric_same(self):
        item = {"cost_amount": 42.5}
        f = {"field": "cost_amount", "operator": "neq", "value": 42.5}
        assert apply_filter(item, f) is False


# ====================================================
# Tests for apply_filter - gt operator
# ====================================================


class TestApplyFilterGt:
    """Tests for the 'gt' (greater than) operator."""

    def test_gt_numeric_greater(self):
        item = {"cost_amount": 100.0}
        f = {"field": "cost_amount", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is True

    def test_gt_numeric_equal(self):
        item = {"cost_amount": 50.0}
        f = {"field": "cost_amount", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_gt_numeric_less(self):
        item = {"cost_amount": 10.0}
        f = {"field": "cost_amount", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_gt_string_numeric_value(self):
        """Numeric strings should be convertible for gt comparison."""
        item = {"cost_amount": "100.5"}
        f = {"field": "cost_amount", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is True

    def test_gt_non_numeric_string_excluded(self):
        """Non-numeric strings should be excluded for gt."""
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is False


# ====================================================
# Tests for apply_filter - lt operator
# ====================================================


class TestApplyFilterLt:
    """Tests for the 'lt' (less than) operator."""

    def test_lt_numeric_less(self):
        item = {"cost_amount": 10.0}
        f = {"field": "cost_amount", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is True

    def test_lt_numeric_equal(self):
        item = {"cost_amount": 50.0}
        f = {"field": "cost_amount", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_lt_numeric_greater(self):
        item = {"cost_amount": 100.0}
        f = {"field": "cost_amount", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_lt_string_numeric_value(self):
        """Numeric strings should be convertible for lt comparison."""
        item = {"cost_amount": "10.5"}
        f = {"field": "cost_amount", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is True

    def test_lt_non_numeric_string_excluded(self):
        """Non-numeric strings should be excluded for lt."""
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is False


# ====================================================
# Tests for apply_filter - contains operator
# ====================================================


class TestApplyFilterContains:
    """Tests for the 'contains' (case-insensitive substring) operator."""

    def test_contains_exact_match(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "contains", "value": "Amazon EC2"}
        assert apply_filter(item, f) is True

    def test_contains_substring_match(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "contains", "value": "EC2"}
        assert apply_filter(item, f) is True

    def test_contains_case_insensitive(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "contains", "value": "amazon"}
        assert apply_filter(item, f) is True

    def test_contains_case_insensitive_value_uppercase(self):
        item = {"service": "amazon ec2"}
        f = {"field": "service", "operator": "contains", "value": "AMAZON"}
        assert apply_filter(item, f) is True

    def test_contains_no_match(self):
        item = {"service": "Amazon EC2"}
        f = {"field": "service", "operator": "contains", "value": "Lambda"}
        assert apply_filter(item, f) is False

    def test_contains_numeric_value_converted_to_string(self):
        """Numeric field values are converted to string for contains."""
        item = {"cost_amount": 123.45}
        f = {"field": "cost_amount", "operator": "contains", "value": "123"}
        assert apply_filter(item, f) is True


# ====================================================
# Tests for apply_filter - missing field exclusion
# ====================================================


class TestApplyFilterMissingField:
    """Tests for items where the referenced field is not present."""

    def test_missing_field_eq(self):
        item = {"service": "EC2"}
        f = {"field": "cost_amount", "operator": "eq", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_missing_field_neq(self):
        item = {"service": "EC2"}
        f = {"field": "cost_amount", "operator": "neq", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_missing_field_gt(self):
        item = {"service": "EC2"}
        f = {"field": "cost_amount", "operator": "gt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_missing_field_lt(self):
        item = {"service": "EC2"}
        f = {"field": "cost_amount", "operator": "lt", "value": 50.0}
        assert apply_filter(item, f) is False

    def test_missing_field_contains(self):
        item = {"service": "EC2"}
        f = {"field": "description", "operator": "contains", "value": "test"}
        assert apply_filter(item, f) is False

    def test_none_field_value_excluded(self):
        """A field explicitly set to None should be excluded."""
        item = {"cost_amount": None}
        f = {"field": "cost_amount", "operator": "eq", "value": 50.0}
        assert apply_filter(item, f) is False


# ====================================================
# Tests for apply_filter - non-comparable value exclusion
# ====================================================


class TestApplyFilterNonComparable:
    """Tests for gt/lt on non-numeric values (Requirement 4.5)."""

    def test_gt_on_text_string(self):
        item = {"service": "hello"}
        f = {"field": "service", "operator": "gt", "value": 10}
        assert apply_filter(item, f) is False

    def test_lt_on_text_string(self):
        item = {"service": "hello"}
        f = {"field": "service", "operator": "lt", "value": 10}
        assert apply_filter(item, f) is False

    def test_gt_with_non_numeric_target(self):
        item = {"cost_amount": 50.0}
        f = {"field": "cost_amount", "operator": "gt", "value": "not_a_number"}
        assert apply_filter(item, f) is False

    def test_lt_with_non_numeric_target(self):
        item = {"cost_amount": 50.0}
        f = {"field": "cost_amount", "operator": "lt", "value": "not_a_number"}
        assert apply_filter(item, f) is False

    def test_gt_on_list_value(self):
        item = {"tags": ["tag1", "tag2"]}
        f = {"field": "tags", "operator": "gt", "value": 5}
        assert apply_filter(item, f) is False

    def test_lt_on_dict_value(self):
        item = {"metadata": {"key": "val"}}
        f = {"field": "metadata", "operator": "lt", "value": 5}
        assert apply_filter(item, f) is False


# ====================================================
# Tests for apply_filters - AND logic
# ====================================================


class TestApplyFiltersAndLogic:
    """Tests for conjunctive (AND) filter application."""

    def test_multiple_filters_all_pass(self):
        data = [
            {"service": "EC2", "cost_amount": 100.0},
            {"service": "S3", "cost_amount": 50.0},
            {"service": "EC2", "cost_amount": 30.0},
        ]
        filters = [
            {"field": "service", "operator": "eq", "value": "EC2"},
            {"field": "cost_amount", "operator": "gt", "value": 50.0},
        ]
        result = apply_filters(data, filters)
        assert len(result) == 1
        assert result[0]["cost_amount"] == 100.0

    def test_multiple_filters_none_pass(self):
        data = [
            {"service": "EC2", "cost_amount": 100.0},
            {"service": "S3", "cost_amount": 50.0},
        ]
        filters = [
            {"field": "service", "operator": "eq", "value": "Lambda"},
            {"field": "cost_amount", "operator": "gt", "value": 200.0},
        ]
        result = apply_filters(data, filters)
        assert len(result) == 0

    def test_three_filters_and_logic(self):
        data = [
            {"service": "EC2", "cost_amount": 100.0, "region": "us-east-1"},
            {"service": "EC2", "cost_amount": 200.0, "region": "eu-west-1"},
            {"service": "S3", "cost_amount": 150.0, "region": "us-east-1"},
        ]
        filters = [
            {"field": "service", "operator": "eq", "value": "EC2"},
            {"field": "cost_amount", "operator": "gt", "value": 50.0},
            {"field": "region", "operator": "contains", "value": "us-east"},
        ]
        result = apply_filters(data, filters)
        assert len(result) == 1
        assert result[0]["region"] == "us-east-1"
        assert result[0]["cost_amount"] == 100.0


# ====================================================
# Tests for apply_filters - max filter enforcement
# ====================================================


class TestApplyFiltersMaxLimit:
    """Tests for maximum 20 filters enforcement."""

    def test_exactly_20_filters_allowed(self):
        data = [{"field_0": 1}]
        filters = [
            {"field": f"field_{i}", "operator": "eq", "value": 1}
            for i in range(20)
        ]
        # Should not raise - just returns items that match (or not)
        result = apply_filters(data, filters)
        assert isinstance(result, list)

    def test_21_filters_raises_error(self):
        data = [{"x": 1}]
        filters = [
            {"field": "x", "operator": "eq", "value": 1}
            for _ in range(21)
        ]
        with pytest.raises(ValueError, match="Too many filters"):
            apply_filters(data, filters)

    def test_30_filters_raises_error(self):
        data = [{"x": 1}]
        filters = [
            {"field": "x", "operator": "eq", "value": 1}
            for _ in range(30)
        ]
        with pytest.raises(ValueError, match="Too many filters"):
            apply_filters(data, filters)


# ====================================================
# Tests for apply_filters - empty filter list
# ====================================================


class TestApplyFiltersEmptyFilters:
    """Tests for empty filter list (all items returned)."""

    def test_empty_filters_returns_all(self):
        data = [
            {"service": "EC2", "cost_amount": 100.0},
            {"service": "S3", "cost_amount": 50.0},
        ]
        result = apply_filters(data, [])
        assert len(result) == 2

    def test_empty_filters_preserves_items(self):
        data = [{"a": 1}, {"b": 2}, {"c": 3}]
        result = apply_filters(data, [])
        assert result == data


# ====================================================
# Tests for apply_filters - empty data list
# ====================================================


class TestApplyFiltersEmptyData:
    """Tests for empty data list."""

    def test_empty_data_returns_empty(self):
        filters = [{"field": "x", "operator": "eq", "value": 1}]
        result = apply_filters([], filters)
        assert result == []

    def test_empty_data_empty_filters_returns_empty(self):
        result = apply_filters([], [])
        assert result == []
