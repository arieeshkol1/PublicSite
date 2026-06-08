"""Widget configuration validation module.

Validates widget configs against the defined schema before query execution.
Ensures no side effects or mutations to input configuration.
"""

from datetime import date, datetime, timedelta

from constants import (
    MAX_DATE_RANGE_DAYS,
    SUPPORTED_AGGREGATIONS,
    SUPPORTED_DATA_SOURCES,
    SUPPORTED_RELATIVE_RANGES,
    SUPPORTED_WIDGET_TYPES,
)


def validate_widget_config(config: dict) -> tuple[bool, str | None]:
    """Validate a widget configuration object against the schema.

    Args:
        config: The widget configuration dict to validate.

    Returns:
        Tuple of (is_valid: bool, error_message: str | None).
        Returns (True, None) if valid, (False, error_message) if invalid.
        No side effects, no mutations to input.

    Validates:
        - Input is a non-null dict
        - Required top-level fields: type, dataSource, aggregation
        - Widget type is in supported set
        - Aggregation is in supported set
        - dataSource has required sub-fields: source, accountIds, dateRange
    """
    # Handle null/non-object/unparseable inputs (Requirement 5.6)
    if config is None or not isinstance(config, dict):
        return (False, "A valid configuration object is required")

    # Validate required top-level fields (Requirement 5.2)
    required_fields = ["type", "dataSource", "aggregation"]
    for field in required_fields:
        if field not in config:
            return (False, f"Missing required field: {field}")

    # Validate widget type (Requirement 5.3)
    if config["type"] not in SUPPORTED_WIDGET_TYPES:
        return (False, f"Invalid widget type: {config['type']}")

    # Validate aggregation type (Requirement 5.4)
    if config["aggregation"] not in SUPPORTED_AGGREGATIONS:
        return (False, f"Invalid aggregation type: {config['aggregation']}")

    # Validate dataSource is an object (Requirement 5.5)
    data_source = config["dataSource"]
    if not isinstance(data_source, dict):
        return (False, "dataSource must be an object")

    # Validate dataSource sub-fields (Requirement 5.5)
    required_ds_fields = ["source", "accountIds", "dateRange"]
    for field in required_ds_fields:
        if field not in data_source:
            return (False, f"Missing required dataSource field: {field}")

    return (True, None)


def resolve_date_range(date_range: dict) -> tuple[str, str]:
    """Convert relative or absolute date range to (start_date, end_date) strings.

    Args:
        date_range: Dict with 'type' key ('relative' or 'absolute').
            - If relative: must have 'relative' key with value in SUPPORTED_RELATIVE_RANGES.
            - If absolute: must have 'start' and 'end' keys in YYYY-MM-DD format.

    Returns:
        Tuple of (start_date, end_date) both in YYYY-MM-DD format.
        start_date < end_date, span never exceeds MAX_DATE_RANGE_DAYS.

    Raises:
        ValueError: If date range is invalid (missing fields, unsupported range,
            start >= end, or span exceeds MAX_DATE_RANGE_DAYS).
    """
    if not isinstance(date_range, dict):
        raise ValueError("dateRange must be an object")

    range_type = date_range.get("type")
    if range_type not in ("relative", "absolute"):
        raise ValueError("dateRange.type must be 'relative' or 'absolute'")

    if range_type == "relative":
        relative_value = date_range.get("relative")
        if relative_value not in SUPPORTED_RELATIVE_RANGES:
            raise ValueError(
                f"Unsupported relative range: {relative_value}. "
                f"Supported: {sorted(SUPPORTED_RELATIVE_RANGES)}"
            )

        today = date.today()
        end_date = today

        if relative_value.endswith("d"):
            days = int(relative_value[:-1])
            start_date = today - timedelta(days=days)
        elif relative_value.endswith("m"):
            months = int(relative_value[:-1])
            # Approximate months as 30 days each
            start_date = today - timedelta(days=months * 30)
        else:
            raise ValueError(f"Unsupported relative range format: {relative_value}")

    else:  # absolute
        start_str = date_range.get("start")
        end_str = date_range.get("end")

        if not start_str or not end_str:
            raise ValueError(
                "Absolute date range requires both 'start' and 'end' fields"
            )

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid start date format: {start_str}. Expected YYYY-MM-DD"
            )

        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid end date format: {end_str}. Expected YYYY-MM-DD"
            )

    # Validate start < end
    if start_date >= end_date:
        raise ValueError(
            f"Start date ({start_date.isoformat()}) must be before "
            f"end date ({end_date.isoformat()})"
        )

    # Validate span does not exceed MAX_DATE_RANGE_DAYS
    span_days = (end_date - start_date).days
    if span_days > MAX_DATE_RANGE_DAYS:
        raise ValueError(
            f"Date range span ({span_days} days) exceeds maximum "
            f"allowed ({MAX_DATE_RANGE_DAYS} days)"
        )

    return (start_date.isoformat(), end_date.isoformat())
