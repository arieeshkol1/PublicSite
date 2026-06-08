"""Constants and schema definitions for the agent pipeline."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Classification JSON schema
# ---------------------------------------------------------------------------
CLASSIFICATION_SCHEMA: dict = {
    "type": "object",
    "required": ["intent_type", "target_scope", "timeframe", "confidence_score"],
    "properties": {
        "intent_type": {
            "type": "string",
            "enum": [
                "Cost_Analysis_General",
                "Cost_Analysis_Specific",
                "Optimization_Tips",
                "Forecasting",
            ],
        },
        "target_scope": {"type": "string"},
        "timeframe": {"type": "string"},
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

# ---------------------------------------------------------------------------
# Delimiter boundaries for prompt injection defense
# ---------------------------------------------------------------------------
DELIMITER_START = "<<<USER_INPUT>>>"
DELIMITER_END = "<<<END_USER_INPUT>>>"

# ---------------------------------------------------------------------------
# Valid intent types
# ---------------------------------------------------------------------------
VALID_INTENT_TYPES = [
    "Cost_Analysis_General",
    "Cost_Analysis_Specific",
    "Optimization_Tips",
    "Forecasting",
]

# ---------------------------------------------------------------------------
# Default context budget configuration
# ---------------------------------------------------------------------------
DEFAULT_BUDGET_CONFIG: dict = {
    "model_context_window": 128000,
    "system_prefix_budget": 4000,
    "dynamic_data_budget": 12000,
    "user_query_budget": 2000,
    "response_budget": 4000,
    "total_ceiling": 22000,
}

# ---------------------------------------------------------------------------
# S3 prompt repository
# ---------------------------------------------------------------------------
PROMPT_REPOSITORY_BUCKET = "slashmybill-prompt-repository"
PROMPT_TEMPLATES_PREFIX = "templates/"

# ---------------------------------------------------------------------------
# DynamoDB table names
# ---------------------------------------------------------------------------
ACCOUNTS_TABLE = "Accounts"
MEMBERS_TABLE = "Members"
COST_CACHE_TABLE = "Cost_Cache_Table"
TIPS_TABLE = "ViewMyBill-CostOptimizationTips"

# ---------------------------------------------------------------------------
# Cache staleness threshold (seconds)
# ---------------------------------------------------------------------------
CACHE_STALENESS_THRESHOLD_SECONDS = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Forecast constraints
# ---------------------------------------------------------------------------
FORECAST_MIN_DAYS = 30
FORECAST_MAX_MONTHS = 12
FORECAST_SEASONAL_MIN_DAYS = 90
ANOMALY_STD_THRESHOLD = 2.0
