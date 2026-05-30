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
        tag_breakdown: Mapping of tag values to their cost amounts for
            all active cost allocation tags. Keys are "tagKey=tagValue"
            (e.g., {"Environment=Production": 15.0, "Team=Backend": 10.0}).
        fetched_at: ISO 8601 timestamp indicating when this data was
            retrieved from the Cost Explorer API.
    """

    date: str
    cost_amount: float
    currency: str
    service_breakdown: dict[str, float] = field(default_factory=dict)
    tag_breakdown: dict[str, float] = field(default_factory=dict)
    fetched_at: str = ""


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
