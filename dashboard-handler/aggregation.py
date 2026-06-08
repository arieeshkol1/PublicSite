"""
Aggregation and dimension grouping for the Widget Builder Dashboard.

Provides group_by_dimensions() for grouping data by up to 3 dimensions,
aggregate() for computing sum/avg/max/min/count within groups, and
format_for_chart() for producing Chart.js-compatible output structures.

Requirements: 3.1, 3.3, 3.4, 3.7
"""

from constants import MAX_DIMENSIONS


def group_by_dimensions(data: list[dict], dimensions: list[str]) -> dict:
    """
    Group data items by the specified dimension fields.

    Args:
        data: A list of data dictionaries to group.
        dimensions: A list of dimension field names to group by (max 3).

    Returns:
        A dict mapping dimension value tuples (as strings) to lists of items.
        For a single dimension, the key is the dimension value string.
        For multiple dimensions, the key is a tuple string like "val1|val2".

    Raises:
        ValueError: If more than MAX_DIMENSIONS (3) dimensions are provided.
    """
    if len(dimensions) > MAX_DIMENSIONS:
        raise ValueError(
            f"Too many dimensions: {len(dimensions)} exceeds maximum of {MAX_DIMENSIONS}"
        )

    if not dimensions:
        return {"_all": list(data)}

    if not data:
        return {}

    groups: dict[str, list[dict]] = {}

    for item in data:
        # Build the group key from dimension values
        key_parts = []
        for dim in dimensions:
            value = item.get(dim, "_unknown")
            if value is None:
                value = "_unknown"
            key_parts.append(str(value))

        key = "|".join(key_parts) if len(key_parts) > 1 else key_parts[0]

        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    return groups


def aggregate(items: list[dict], aggregation_type: str) -> float:
    """
    Compute an aggregation over a list of data items.

    Extracts numeric values from the 'cost_amount' field of each item
    and applies the specified aggregation function.

    Args:
        items: A list of data dictionaries, each optionally containing
               a 'cost_amount' field with a numeric value.
        aggregation_type: One of 'sum', 'avg', 'max', 'min', 'count'.

    Returns:
        The aggregated numeric result. Returns 0 for empty item lists
        (except count which returns 0 for empty lists).
        For avg, returns 0 if no numeric values are found.
    """
    if not items:
        return 0.0

    if aggregation_type == "count":
        return float(len(items))

    # Extract numeric values from cost_amount field
    values = []
    for item in items:
        raw = item.get("cost_amount")
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue

    if not values:
        return 0.0

    if aggregation_type == "sum":
        return sum(values)
    elif aggregation_type == "avg":
        return sum(values) / len(values)
    elif aggregation_type == "max":
        return max(values)
    elif aggregation_type == "min":
        return min(values)

    return 0.0


def format_for_chart(aggregated: dict, widget_type: str) -> dict:
    """
    Transform aggregated data into a Chart.js-compatible structure.

    Args:
        aggregated: A dict mapping group keys (strings) to aggregated
                    numeric values (floats).
        widget_type: The widget visualization type (bar, line, pie, etc.).

    Returns:
        A dict with:
            - labels: list of group key strings
            - datasets: list containing one dataset object with:
                - label: descriptive dataset label
                - data: list of numeric values corresponding to labels
    """
    if not aggregated:
        return {
            "labels": [],
            "datasets": [{"label": "Value", "data": []}],
        }

    labels = list(aggregated.keys())
    data_values = [aggregated[k] for k in labels]

    dataset_label = "Value"
    if widget_type in ("bar", "line"):
        dataset_label = "Cost (USD)"
    elif widget_type == "pie":
        dataset_label = "Distribution"
    elif widget_type == "kpi":
        dataset_label = "KPI"
    elif widget_type == "gauge":
        dataset_label = "Gauge"
    elif widget_type == "table":
        dataset_label = "Value"

    return {
        "labels": labels,
        "datasets": [
            {
                "label": dataset_label,
                "data": data_values,
            }
        ],
    }
