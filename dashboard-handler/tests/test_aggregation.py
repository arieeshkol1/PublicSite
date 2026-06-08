"""Unit tests for aggregation, dimension grouping, and chart formatting functions."""

import sys
import os

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from aggregation import group_by_dimensions, aggregate, format_for_chart


# ====================================================
# Tests for aggregate - sum
# ====================================================


class TestAggregateSum:
    """Tests for the 'sum' aggregation type."""

    def test_sum_basic(self):
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": 20.0},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "sum") == 60.0

    def test_sum_single_item(self):
        items = [{"cost_amount": 42.5}]
        assert aggregate(items, "sum") == 42.5

    def test_sum_with_string_numeric_values(self):
        items = [{"cost_amount": "15.5"}, {"cost_amount": "4.5"}]
        assert aggregate(items, "sum") == 20.0

    def test_sum_empty_list(self):
        assert aggregate([], "sum") == 0.0


# ====================================================
# Tests for aggregate - avg
# ====================================================


class TestAggregateAvg:
    """Tests for the 'avg' aggregation type."""

    def test_avg_basic(self):
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": 20.0},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "avg") == 20.0

    def test_avg_single_item(self):
        items = [{"cost_amount": 50.0}]
        assert aggregate(items, "avg") == 50.0

    def test_avg_no_numeric_values_returns_zero(self):
        """avg returns 0 for groups with no numeric values."""
        items = [
            {"cost_amount": "not_a_number"},
            {"cost_amount": "also_not_numeric"},
        ]
        assert aggregate(items, "avg") == 0.0

    def test_avg_missing_cost_amount_returns_zero(self):
        """avg returns 0 when no items have cost_amount field."""
        items = [{"service": "EC2"}, {"service": "S3"}]
        assert aggregate(items, "avg") == 0.0

    def test_avg_empty_list(self):
        assert aggregate([], "avg") == 0.0

    def test_avg_none_values_excluded(self):
        """Items with None cost_amount are excluded from avg calculation."""
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": None},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "avg") == 20.0


# ====================================================
# Tests for aggregate - max
# ====================================================


class TestAggregateMax:
    """Tests for the 'max' aggregation type."""

    def test_max_basic(self):
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": 50.0},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "max") == 50.0

    def test_max_single_item(self):
        items = [{"cost_amount": 99.0}]
        assert aggregate(items, "max") == 99.0

    def test_max_with_negative_values(self):
        items = [{"cost_amount": -5.0}, {"cost_amount": -1.0}]
        assert aggregate(items, "max") == -1.0

    def test_max_empty_list(self):
        assert aggregate([], "max") == 0.0


# ====================================================
# Tests for aggregate - min
# ====================================================


class TestAggregateMin:
    """Tests for the 'min' aggregation type."""

    def test_min_basic(self):
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": 50.0},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "min") == 10.0

    def test_min_single_item(self):
        items = [{"cost_amount": 7.0}]
        assert aggregate(items, "min") == 7.0

    def test_min_with_negative_values(self):
        items = [{"cost_amount": -5.0}, {"cost_amount": -1.0}]
        assert aggregate(items, "min") == -5.0

    def test_min_empty_list(self):
        assert aggregate([], "min") == 0.0


# ====================================================
# Tests for aggregate - count
# ====================================================


class TestAggregateCount:
    """Tests for the 'count' aggregation type."""

    def test_count_basic(self):
        items = [
            {"cost_amount": 10.0},
            {"cost_amount": 20.0},
            {"cost_amount": 30.0},
        ]
        assert aggregate(items, "count") == 3.0

    def test_count_includes_items_without_cost_amount(self):
        """Count counts all items regardless of cost_amount presence."""
        items = [{"service": "EC2"}, {"service": "S3"}, {"cost_amount": 5.0}]
        assert aggregate(items, "count") == 3.0

    def test_count_single_item(self):
        items = [{"cost_amount": 100.0}]
        assert aggregate(items, "count") == 1.0

    def test_count_empty_list(self):
        assert aggregate([], "count") == 0.0


# ====================================================
# Tests for group_by_dimensions - single dimension
# ====================================================


class TestGroupByDimensionsSingle:
    """Tests for grouping by a single dimension."""

    def test_group_by_service(self):
        data = [
            {"service": "EC2", "cost_amount": 10.0},
            {"service": "S3", "cost_amount": 20.0},
            {"service": "EC2", "cost_amount": 30.0},
        ]
        groups = group_by_dimensions(data, ["service"])
        assert "EC2" in groups
        assert "S3" in groups
        assert len(groups["EC2"]) == 2
        assert len(groups["S3"]) == 1

    def test_group_by_single_unique_values(self):
        data = [
            {"region": "us-east-1", "cost_amount": 5.0},
            {"region": "eu-west-1", "cost_amount": 15.0},
            {"region": "ap-south-1", "cost_amount": 25.0},
        ]
        groups = group_by_dimensions(data, ["region"])
        assert len(groups) == 3
        for key in groups:
            assert len(groups[key]) == 1

    def test_group_by_missing_dimension_field(self):
        """Items missing the dimension field are grouped under '_unknown'."""
        data = [
            {"service": "EC2", "cost_amount": 10.0},
            {"cost_amount": 20.0},  # missing 'service'
        ]
        groups = group_by_dimensions(data, ["service"])
        assert "EC2" in groups
        assert "_unknown" in groups
        assert len(groups["_unknown"]) == 1


# ====================================================
# Tests for group_by_dimensions - two dimensions
# ====================================================


class TestGroupByDimensionsTwo:
    """Tests for grouping by two dimensions."""

    def test_group_by_two_dimensions(self):
        data = [
            {"service": "EC2", "region": "us-east-1", "cost_amount": 10.0},
            {"service": "EC2", "region": "eu-west-1", "cost_amount": 20.0},
            {"service": "S3", "region": "us-east-1", "cost_amount": 30.0},
        ]
        groups = group_by_dimensions(data, ["service", "region"])
        assert "EC2|us-east-1" in groups
        assert "EC2|eu-west-1" in groups
        assert "S3|us-east-1" in groups
        assert len(groups) == 3

    def test_group_by_two_dimensions_same_combo(self):
        data = [
            {"service": "EC2", "region": "us-east-1", "cost_amount": 10.0},
            {"service": "EC2", "region": "us-east-1", "cost_amount": 20.0},
        ]
        groups = group_by_dimensions(data, ["service", "region"])
        assert len(groups) == 1
        assert len(groups["EC2|us-east-1"]) == 2


# ====================================================
# Tests for group_by_dimensions - three dimensions
# ====================================================


class TestGroupByDimensionsThree:
    """Tests for grouping by three dimensions."""

    def test_group_by_three_dimensions(self):
        data = [
            {"service": "EC2", "region": "us-east-1", "account": "111", "cost_amount": 10.0},
            {"service": "EC2", "region": "us-east-1", "account": "222", "cost_amount": 20.0},
            {"service": "EC2", "region": "eu-west-1", "account": "111", "cost_amount": 30.0},
        ]
        groups = group_by_dimensions(data, ["service", "region", "account"])
        assert "EC2|us-east-1|111" in groups
        assert "EC2|us-east-1|222" in groups
        assert "EC2|eu-west-1|111" in groups
        assert len(groups) == 3


# ====================================================
# Tests for group_by_dimensions - max dimensions enforcement
# ====================================================


class TestGroupByDimensionsMaxLimit:
    """Tests for maximum 3 dimensions enforcement."""

    def test_exactly_3_dimensions_allowed(self):
        data = [{"a": "1", "b": "2", "c": "3", "cost_amount": 10.0}]
        groups = group_by_dimensions(data, ["a", "b", "c"])
        assert isinstance(groups, dict)
        assert len(groups) == 1

    def test_4_dimensions_raises_error(self):
        data = [{"a": "1", "b": "2", "c": "3", "d": "4"}]
        with pytest.raises(ValueError, match="Too many dimensions"):
            group_by_dimensions(data, ["a", "b", "c", "d"])

    def test_5_dimensions_raises_error(self):
        data = [{"a": "1"}]
        with pytest.raises(ValueError, match="Too many dimensions"):
            group_by_dimensions(data, ["a", "b", "c", "d", "e"])


# ====================================================
# Tests for group_by_dimensions - empty data
# ====================================================


class TestGroupByDimensionsEmpty:
    """Tests for empty data handling in group_by_dimensions."""

    def test_empty_data_returns_empty_groups(self):
        groups = group_by_dimensions([], ["service"])
        assert groups == {}

    def test_empty_dimensions_returns_all_group(self):
        data = [{"service": "EC2", "cost_amount": 10.0}]
        groups = group_by_dimensions(data, [])
        assert "_all" in groups
        assert len(groups["_all"]) == 1


# ====================================================
# Tests for format_for_chart - output structure
# ====================================================


class TestFormatForChart:
    """Tests for format_for_chart output structure."""

    def test_basic_bar_chart_structure(self):
        aggregated = {"EC2": 100.0, "S3": 50.0, "Lambda": 25.0}
        result = format_for_chart(aggregated, "bar")
        assert "labels" in result
        assert "datasets" in result
        assert result["labels"] == ["EC2", "S3", "Lambda"]
        assert len(result["datasets"]) == 1
        assert result["datasets"][0]["data"] == [100.0, 50.0, 25.0]
        assert "label" in result["datasets"][0]

    def test_pie_chart_structure(self):
        aggregated = {"EC2": 60.0, "S3": 40.0}
        result = format_for_chart(aggregated, "pie")
        assert result["labels"] == ["EC2", "S3"]
        assert result["datasets"][0]["data"] == [60.0, 40.0]
        assert result["datasets"][0]["label"] == "Distribution"

    def test_line_chart_structure(self):
        aggregated = {"2024-01-01": 10.0, "2024-01-02": 20.0}
        result = format_for_chart(aggregated, "line")
        assert result["labels"] == ["2024-01-01", "2024-01-02"]
        assert result["datasets"][0]["data"] == [10.0, 20.0]
        assert result["datasets"][0]["label"] == "Cost (USD)"

    def test_empty_aggregated_returns_empty_structure(self):
        result = format_for_chart({}, "bar")
        assert result["labels"] == []
        assert len(result["datasets"]) == 1
        assert result["datasets"][0]["data"] == []

    def test_kpi_widget_type(self):
        aggregated = {"total": 1234.56}
        result = format_for_chart(aggregated, "kpi")
        assert result["labels"] == ["total"]
        assert result["datasets"][0]["data"] == [1234.56]
        assert result["datasets"][0]["label"] == "KPI"

    def test_table_widget_type(self):
        aggregated = {"row1": 10.0, "row2": 20.0}
        result = format_for_chart(aggregated, "table")
        assert result["labels"] == ["row1", "row2"]
        assert result["datasets"][0]["data"] == [10.0, 20.0]

    def test_gauge_widget_type(self):
        aggregated = {"current": 75.0}
        result = format_for_chart(aggregated, "gauge")
        assert result["datasets"][0]["label"] == "Gauge"

    def test_labels_and_data_positional_correspondence(self):
        """Labels and data arrays must correspond positionally."""
        aggregated = {"A": 1.0, "B": 2.0, "C": 3.0}
        result = format_for_chart(aggregated, "bar")
        for i, label in enumerate(result["labels"]):
            assert result["datasets"][0]["data"][i] == aggregated[label]


# ====================================================
# Tests for partition consistency
# ====================================================


class TestPartitionConsistency:
    """Tests that sum across groups equals sum of unpartitioned data."""

    def test_sum_partition_consistency_by_service(self):
        """Sum of aggregated groups equals total sum of unpartitioned data."""
        data = [
            {"service": "EC2", "cost_amount": 10.0},
            {"service": "S3", "cost_amount": 20.0},
            {"service": "EC2", "cost_amount": 30.0},
            {"service": "Lambda", "cost_amount": 15.0},
        ]
        groups = group_by_dimensions(data, ["service"])
        group_sum = sum(aggregate(items, "sum") for items in groups.values())
        total_sum = aggregate(data, "sum")
        assert abs(group_sum - total_sum) < 1e-9

    def test_sum_partition_consistency_by_region(self):
        data = [
            {"region": "us-east-1", "cost_amount": 100.0},
            {"region": "eu-west-1", "cost_amount": 200.0},
            {"region": "us-east-1", "cost_amount": 50.0},
        ]
        groups = group_by_dimensions(data, ["region"])
        group_sum = sum(aggregate(items, "sum") for items in groups.values())
        total_sum = aggregate(data, "sum")
        assert abs(group_sum - total_sum) < 1e-9

    def test_sum_partition_consistency_two_dimensions(self):
        data = [
            {"service": "EC2", "region": "us-east-1", "cost_amount": 10.0},
            {"service": "EC2", "region": "eu-west-1", "cost_amount": 20.0},
            {"service": "S3", "region": "us-east-1", "cost_amount": 30.0},
        ]
        groups = group_by_dimensions(data, ["service", "region"])
        group_sum = sum(aggregate(items, "sum") for items in groups.values())
        total_sum = aggregate(data, "sum")
        assert abs(group_sum - total_sum) < 1e-9
