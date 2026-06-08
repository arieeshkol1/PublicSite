"""
Shared configuration constants for the Widget Builder Dashboard.

Defines supported widget types, aggregation methods, data sources,
filter operators, and grid/layout limits used across the query engine,
layout store, and validators.
"""

# Supported widget visualization types (Requirement 1.3)
SUPPORTED_WIDGET_TYPES = frozenset([
    "bar",
    "line",
    "pie",
    "table",
    "kpi",
    "gauge",
])

# Supported aggregation methods (Requirement 5.1)
SUPPORTED_AGGREGATIONS = frozenset([
    "sum",
    "avg",
    "max",
    "min",
    "count",
])

# Supported data source identifiers (Requirement 5.1)
SUPPORTED_DATA_SOURCES = frozenset([
    "cost_cache",
    "invoices",
    "openai_usage",
    "commitments",
    "business_metrics",
])

# Supported filter operators (Requirement 5.1)
SUPPORTED_OPERATORS = frozenset([
    "eq",
    "neq",
    "gt",
    "lt",
    "contains",
])

# Grid layout constraints (Requirements 6.1, 6.5)
GRID_COLS = 12
MAX_ROWS = 48

# Layout limits (Requirements 7.5, 7.6)
MAX_WIDGETS = 20
MAX_LAYOUTS = 10

# Filter limit (Requirement 6.5)
MAX_FILTERS = 20

# Supported relative date ranges
SUPPORTED_RELATIVE_RANGES = frozenset([
    "7d",
    "30d",
    "90d",
    "12m",
])

# Maximum date range span in days
MAX_DATE_RANGE_DAYS = 365

# Maximum dimensions per query
MAX_DIMENSIONS = 3

# Layout name length constraints
LAYOUT_NAME_MIN_LENGTH = 1
LAYOUT_NAME_MAX_LENGTH = 64
