"""Unit tests for validate_widget_config and resolve_date_range functions."""

import sys
import os
import copy
from datetime import date, timedelta

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from validators import validate_widget_config, resolve_date_range


def _valid_config():
    """Return a minimal valid widget configuration."""
    return {
        "type": "bar",
        "dataSource": {
            "source": "cost_cache",
            "accountIds": ["123456789012"],
            "dateRange": {"type": "relative", "relative": "30d"},
        },
        "aggregation": "sum",
    }


class TestValidWidgets:
    """Tests that valid configs pass validation."""

    def test_minimal_valid_config(self):
        valid, error = validate_widget_config(_valid_config())
        assert valid is True
        assert error is None

    def test_all_widget_types(self):
        for wtype in ("bar", "line", "pie", "table", "kpi", "gauge"):
            config = _valid_config()
            config["type"] = wtype
            valid, error = validate_widget_config(config)
            assert valid is True, f"Widget type '{wtype}' should be valid"

    def test_all_aggregation_types(self):
        for agg in ("sum", "avg", "max", "min", "count"):
            config = _valid_config()
            config["aggregation"] = agg
            valid, error = validate_widget_config(config)
            assert valid is True, f"Aggregation '{agg}' should be valid"

    def test_config_with_extra_fields(self):
        """Extra fields should not cause rejection."""
        config = _valid_config()
        config["title"] = "My Widget"
        config["dimensions"] = ["service"]
        config["filters"] = []
        config["display"] = {"colorScheme": "default"}
        valid, error = validate_widget_config(config)
        assert valid is True


class TestNullNonObjectInputs:
    """Tests for null/non-object/unparseable inputs (Requirement 5.6)."""

    def test_none_input(self):
        valid, error = validate_widget_config(None)
        assert valid is False
        assert "valid configuration object is required" in error.lower()

    def test_string_input(self):
        valid, error = validate_widget_config("not a dict")
        assert valid is False
        assert "valid configuration object is required" in error.lower()

    def test_list_input(self):
        valid, error = validate_widget_config([1, 2, 3])
        assert valid is False
        assert "valid configuration object is required" in error.lower()

    def test_integer_input(self):
        valid, error = validate_widget_config(42)
        assert valid is False
        assert "valid configuration object is required" in error.lower()

    def test_boolean_input(self):
        valid, error = validate_widget_config(True)
        assert valid is False
        assert "valid configuration object is required" in error.lower()


class TestMissingRequiredFields:
    """Tests for missing required top-level fields (Requirement 5.2)."""

    def test_missing_type(self):
        config = _valid_config()
        del config["type"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "type" in error

    def test_missing_data_source(self):
        config = _valid_config()
        del config["dataSource"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "dataSource" in error

    def test_missing_aggregation(self):
        config = _valid_config()
        del config["aggregation"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "aggregation" in error

    def test_empty_dict(self):
        valid, error = validate_widget_config({})
        assert valid is False
        assert "type" in error  # Should identify first missing field


class TestInvalidWidgetType:
    """Tests for unsupported widget types (Requirement 5.3)."""

    def test_invalid_type(self):
        config = _valid_config()
        config["type"] = "scatter"
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "scatter" in error

    def test_empty_string_type(self):
        config = _valid_config()
        config["type"] = ""
        valid, error = validate_widget_config(config)
        assert valid is False

    def test_numeric_type(self):
        config = _valid_config()
        config["type"] = 123
        valid, error = validate_widget_config(config)
        assert valid is False


class TestInvalidAggregation:
    """Tests for unsupported aggregation types (Requirement 5.4)."""

    def test_invalid_aggregation(self):
        config = _valid_config()
        config["aggregation"] = "median"
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "median" in error

    def test_empty_string_aggregation(self):
        config = _valid_config()
        config["aggregation"] = ""
        valid, error = validate_widget_config(config)
        assert valid is False


class TestDataSourceSubFields:
    """Tests for dataSource sub-field validation (Requirement 5.5)."""

    def test_missing_source(self):
        config = _valid_config()
        del config["dataSource"]["source"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "source" in error

    def test_missing_account_ids(self):
        config = _valid_config()
        del config["dataSource"]["accountIds"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "accountIds" in error

    def test_missing_date_range(self):
        config = _valid_config()
        del config["dataSource"]["dateRange"]
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "dateRange" in error

    def test_data_source_not_a_dict(self):
        config = _valid_config()
        config["dataSource"] = "not_a_dict"
        valid, error = validate_widget_config(config)
        assert valid is False
        assert "object" in error.lower()


class TestNoMutations:
    """Tests that validation does not mutate the input (Requirement 5.7)."""

    def test_valid_config_not_mutated(self):
        config = _valid_config()
        original = copy.deepcopy(config)
        validate_widget_config(config)
        assert config == original

    def test_invalid_config_not_mutated(self):
        config = {"type": "invalid_type", "aggregation": "sum"}
        original = copy.deepcopy(config)
        validate_widget_config(config)
        assert config == original

    def test_none_input_no_side_effects(self):
        # Just verify it doesn't raise
        validate_widget_config(None)


# ====================================================
# Tests for resolve_date_range (Requirements 2.4, 2.5, 2.6)
# ====================================================


class TestResolveDateRangeRelative:
    """Tests for relative date range resolution."""

    def test_7d_relative_range(self):
        start, end = resolve_date_range({"type": "relative", "relative": "7d"})
        today = date.today()
        expected_start = (today - timedelta(days=7)).isoformat()
        expected_end = today.isoformat()
        assert start == expected_start
        assert end == expected_end

    def test_30d_relative_range(self):
        start, end = resolve_date_range({"type": "relative", "relative": "30d"})
        today = date.today()
        expected_start = (today - timedelta(days=30)).isoformat()
        expected_end = today.isoformat()
        assert start == expected_start
        assert end == expected_end

    def test_90d_relative_range(self):
        start, end = resolve_date_range({"type": "relative", "relative": "90d"})
        today = date.today()
        expected_start = (today - timedelta(days=90)).isoformat()
        expected_end = today.isoformat()
        assert start == expected_start
        assert end == expected_end

    def test_12m_relative_range(self):
        start, end = resolve_date_range({"type": "relative", "relative": "12m"})
        today = date.today()
        # 12 months approximated as 360 days
        expected_start = (today - timedelta(days=360)).isoformat()
        expected_end = today.isoformat()
        assert start == expected_start
        assert end == expected_end

    def test_relative_range_start_before_end(self):
        """All relative ranges produce start < end."""
        for rel in ("7d", "30d", "90d", "12m"):
            start, end = resolve_date_range({"type": "relative", "relative": rel})
            assert start < end, f"Relative range '{rel}' should have start < end"

    def test_relative_range_within_365_days(self):
        """All relative ranges produce span <= 365 days."""
        for rel in ("7d", "30d", "90d", "12m"):
            start, end = resolve_date_range({"type": "relative", "relative": rel})
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            assert (end_date - start_date).days <= 365


class TestResolveDateRangeAbsolute:
    """Tests for absolute date range resolution."""

    def test_valid_absolute_range(self):
        start, end = resolve_date_range({
            "type": "absolute",
            "start": "2024-01-01",
            "end": "2024-01-31",
        })
        assert start == "2024-01-01"
        assert end == "2024-01-31"

    def test_absolute_range_one_day(self):
        start, end = resolve_date_range({
            "type": "absolute",
            "start": "2024-06-01",
            "end": "2024-06-02",
        })
        assert start == "2024-06-01"
        assert end == "2024-06-02"

    def test_absolute_range_exactly_365_days(self):
        start, end = resolve_date_range({
            "type": "absolute",
            "start": "2024-01-01",
            "end": "2024-12-31",
        })
        assert start == "2024-01-01"
        assert end == "2024-12-31"


class TestResolveDateRangeErrors:
    """Tests for invalid date range rejection."""

    def test_non_dict_input(self):
        with pytest.raises(ValueError, match="must be an object"):
            resolve_date_range("not a dict")

    def test_none_input(self):
        with pytest.raises(ValueError, match="must be an object"):
            resolve_date_range(None)

    def test_missing_type(self):
        with pytest.raises(ValueError, match="type"):
            resolve_date_range({"relative": "30d"})

    def test_invalid_type_value(self):
        with pytest.raises(ValueError, match="type"):
            resolve_date_range({"type": "invalid"})

    def test_unsupported_relative_range(self):
        with pytest.raises(ValueError, match="Unsupported relative range"):
            resolve_date_range({"type": "relative", "relative": "5d"})

    def test_missing_relative_value(self):
        with pytest.raises(ValueError, match="Unsupported relative range"):
            resolve_date_range({"type": "relative"})

    def test_absolute_missing_start(self):
        with pytest.raises(ValueError, match="both 'start' and 'end'"):
            resolve_date_range({"type": "absolute", "end": "2024-01-31"})

    def test_absolute_missing_end(self):
        with pytest.raises(ValueError, match="both 'start' and 'end'"):
            resolve_date_range({"type": "absolute", "start": "2024-01-01"})

    def test_absolute_invalid_start_format(self):
        with pytest.raises(ValueError, match="Invalid start date format"):
            resolve_date_range({
                "type": "absolute",
                "start": "01-01-2024",
                "end": "2024-01-31",
            })

    def test_absolute_invalid_end_format(self):
        with pytest.raises(ValueError, match="Invalid end date format"):
            resolve_date_range({
                "type": "absolute",
                "start": "2024-01-01",
                "end": "not-a-date",
            })

    def test_start_equals_end(self):
        with pytest.raises(ValueError, match="must be before"):
            resolve_date_range({
                "type": "absolute",
                "start": "2024-01-15",
                "end": "2024-01-15",
            })

    def test_start_after_end(self):
        with pytest.raises(ValueError, match="must be before"):
            resolve_date_range({
                "type": "absolute",
                "start": "2024-06-01",
                "end": "2024-01-01",
            })

    def test_range_exceeds_365_days(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            resolve_date_range({
                "type": "absolute",
                "start": "2023-01-01",
                "end": "2024-01-02",
            })
