"""
Filter pipeline for the Widget Builder Dashboard.

Provides apply_filter() for individual item evaluation and apply_filters()
for conjunctive (AND) filtering of data sets. Supports operators: eq, neq,
gt, lt, contains (case-insensitive substring).

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from constants import MAX_FILTERS


def apply_filter(item: dict, filter_config: dict) -> bool:
    """
    Evaluate whether a single item passes a filter condition.

    Args:
        item: A data dictionary to evaluate.
        filter_config: A dict with keys 'field', 'operator', 'value'.

    Returns:
        True if the item satisfies the filter condition, False otherwise.

    Rules:
        - Returns False if the referenced field is not present in the item.
        - Returns False for gt/lt when the field value is not numeric.
        - Returns False for eq when comparing non-comparable types that would
          raise exceptions.
        - 'contains' performs case-insensitive substring matching.
    """
    field_name = filter_config.get("field")
    operator = filter_config.get("operator")
    target_value = filter_config.get("value")

    # Field not present in item -> exclude
    if field_name not in item:
        return False

    field_value = item[field_name]

    # Field value is None -> exclude
    if field_value is None:
        return False

    if operator == "eq":
        try:
            return field_value == target_value
        except (TypeError, ValueError):
            return False

    elif operator == "neq":
        try:
            return field_value != target_value
        except (TypeError, ValueError):
            return True

    elif operator == "gt":
        try:
            return float(field_value) > float(target_value)
        except (TypeError, ValueError):
            return False

    elif operator == "lt":
        try:
            return float(field_value) < float(target_value)
        except (TypeError, ValueError):
            return False

    elif operator == "contains":
        return str(target_value).lower() in str(field_value).lower()

    # Unknown operator -> exclude
    return False


def apply_filters(data: list[dict], filters: list[dict]) -> list[dict]:
    """
    Apply all filters conjunctively (AND logic) to a data set.

    Args:
        data: A list of data dictionaries to filter.
        filters: A list of filter configurations, each with 'field',
                 'operator', and 'value' keys.

    Returns:
        A new list containing only items that satisfy ALL filter conditions.

    Raises:
        ValueError: If more than MAX_FILTERS (20) filters are provided.

    Rules:
        - If filters list is empty, all items are returned.
        - If data list is empty, an empty list is returned.
        - Maximum 20 filters per query enforced.
    """
    if len(filters) > MAX_FILTERS:
        raise ValueError(
            f"Too many filters: {len(filters)} exceeds maximum of {MAX_FILTERS}"
        )

    if not filters:
        return list(data)

    if not data:
        return []

    result = []
    for item in data:
        if all(apply_filter(item, f) for f in filters):
            result.append(item)

    return result
