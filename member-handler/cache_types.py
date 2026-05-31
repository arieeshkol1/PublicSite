"""Data type definitions for the Cost Data Cache feature.

This module defines the core dataclasses used throughout the cache service,
incremental fetch engine, and dashboard integration for cost data caching.

Only DAILY granularity is supported — monthly summaries are computed by
aggregating daily items at query time.
"""

from dataclasses import dataclass, field


@dataclass
class DateRange:
    """Represents a contiguous date range for cost data queries.

    Attributes:
        start: Start date in YYYY-MM-DD format (inclusive).
        end: End date in YYYY-MM-DD format (exclusive, matching
            AWS Cost Explorer API convention).
    """

    start: str
    end: str


@dataclass
class CostDataItem:
    """Represents a single day's cost data for one account.

    Only DAILY granularity is stored; monthly summaries are computed
    by aggregating daily items at query time.

    Attributes:
        date: The date this cost data applies to, in YYYY-MM-DD format.
        cost_amount: Total cost amount for this date.
        currency: Currency code (e.g., "USD").
        service_breakdown: Mapping of service names to their individual
            cost amounts (e.g., {"Amazon EC2": 25.30, "Amazon S3": 8.12}).
        tag_breakdown: Nested mapping of tag keys to their value-cost
            dictionaries. Format: {tag_key: {tag_value: cost_amount}}
            (e.g., {"Environment": {"Production": 15.0, "Staging": 3.2},
                    "Team": {"Backend": 10.0}}).
        fetched_at: ISO 8601 timestamp indicating when this data was
            retrieved from the Cost Explorer API.
    """

    date: str
    cost_amount: float
    currency: str
    service_breakdown: dict[str, float] = field(default_factory=dict)
    tag_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    fetched_at: str = ""


def normalize_tag_breakdown(
    raw_breakdown: dict,
) -> dict[str, dict[str, float]]:
    """Normalize tag_breakdown to nested format regardless of stored format.

    Detection logic:
    - If empty dict → return empty
    - If first value is a dict → Nested_Format (pass through with float conversion)
    - If first value is a number/string-number → Flat_Format (convert)

    Flat format conversion:
    - "tagKey=tagValue" keys are split and grouped under the tag key
    - Keys without "=" separator are placed under "unknown" tag key

    Args:
        raw_breakdown: Tag breakdown dict in either flat or nested format.

    Returns:
        Nested format: {tag_key: {tag_value: cost_float}}
    """
    if not raw_breakdown:
        return {}

    # Detect format by inspecting first value
    first_value = next(iter(raw_breakdown.values()))

    if isinstance(first_value, dict):
        # Already nested format — convert string costs to float
        return {
            tag_key: {
                tag_val: float(cost) for tag_val, cost in values.items()
            }
            for tag_key, values in raw_breakdown.items()
        }

    # Flat format: keys are "tagKey=tagValue", values are cost strings/numbers
    nested: dict[str, dict[str, float]] = {}
    for key, cost in raw_breakdown.items():
        cost_float = float(cost)
        if '=' in key:
            tag_key, tag_value = key.split('=', 1)
            nested.setdefault(tag_key, {})[tag_value] = cost_float
        else:
            nested.setdefault('unknown', {})[key] = cost_float

    return nested


@dataclass
class CacheResult:
    """Result returned by the cache service for a cost data query.

    Attributes:
        data: List of cost data items retrieved (from cache, API, or both).
        cache_status: Indicates the cache outcome for this query.
            One of "hit" (all data from cache), "partial" (some from cache,
            some fetched or unavailable), or "miss" (no data from cache).
        missing_dates: List of date strings (YYYY-MM-DD) that could not
            be retrieved from either cache or the Cost Explorer API.
        partial_data: True if some data is unavailable due to errors
            (e.g., API timeout or failure for certain dates).
    """

    data: list[CostDataItem] = field(default_factory=list)
    cache_status: str = "miss"
    missing_dates: list[str] = field(default_factory=list)
    partial_data: bool = False
