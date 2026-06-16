"""
Shared configuration constants for the Widget Builder Dashboard.

Defines supported widget types, aggregation methods, data sources,
filter operators, and grid/layout limits used across the query engine,
layout store, and validators.
"""

# Supported widget visualization types (Requirement 1.3, 11.1)
SUPPORTED_WIDGET_TYPES = frozenset([
    "bar",
    "line",
    "pie",
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

# --- Custom Data Source Wizard Constants ---

# Data source name length limit (Requirement 7.4)
MAX_DATASOURCE_NAME_LENGTH = 100

# Maximum saved data sources per member (Requirement 8.1)
MAX_DATASOURCES_PER_MEMBER = 50

# Pagination: records per page (Requirement 9.6)
DATASOURCE_PAGE_SIZE = 500

# Pagination: maximum total records returned (Requirement 9.6)
DATASOURCE_MAX_TOTAL_ROWS = 10000

# Available attributes for data source queries (Requirement 3.1)
DATASOURCE_AVAILABLE_ATTRIBUTES = [
    "date",
    "account_id",
    "service",
    "cost_amount",
    "currency",
    "cloud_provider",
]

# Filter operators by attribute type (Requirement 5.4)
DATASOURCE_FILTER_OPERATORS = {
    "text": ["equals", "not_equals"],
    "numeric": ["equals", "not_equals", "greater_than", "less_than"],
}

# Attribute-to-type mapping (Requirement 5.4)
DATASOURCE_ATTRIBUTE_TYPES = {
    "date": "text",
    "account_id": "text",
    "service": "text",
    "cost_amount": "numeric",
    "currency": "text",
    "cloud_provider": "text",
}

# Timeframe preset definitions (Requirement 4.1)
DATASOURCE_TIMEFRAME_PRESETS = {
    "last_7d": 7,
    "last_30d": 30,
    "last_90d": 90,
    "current_month": "current_month",
    "previous_month": "previous_month",
}
