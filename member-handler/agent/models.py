"""Shared data models for the agent pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AccountContext:
    """Resolved cloud account context."""
    account_id: str
    account_name: str
    cloud_provider: str  # 'aws' | 'azure' | 'gcp'
    member_email: str
    supported_services: list[str] = field(default_factory=list)
    provider_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionState:
    """Multi-turn conversation session state."""
    account_context: AccountContext | None = None
    current_intent: str | None = None
    target_scope: str | None = None
    active_timeframe: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    last_updated: str = ""


@dataclass
class ClassificationResult:
    """Output of intent classification."""
    intent_type: str  # 'Cost_Analysis_General' | 'Cost_Analysis_Specific' | 'Optimization_Tips' | 'Forecasting'
    target_scope: str  # service name or 'account-wide'
    timeframe: str  # 'last-30d' | 'last-7d' | 'last-90d' | 'next-3m' etc.
    confidence_score: float  # 0.0 - 1.0


@dataclass
class ContextBudget:
    """Token budget allocation for the execution payload."""
    system_prefix_tokens: int  # fixed, cacheable
    dynamic_data_tokens: int  # variable, truncatable
    user_query_tokens: int  # preserved in full
    total_ceiling: int  # max tokens for entire payload


@dataclass
class ExecutionPayload:
    """Assembled payload ready for model invocation."""
    system_prefix: str  # [CONTEXT] section - static
    available_metadata: str  # [AVAILABLE META-DATA] section - dynamic
    user_query: str  # [USER QUERY] section - preserved
    template_version: str = ""
    token_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class PromptTemplate:
    """Versioned prompt template from the repository."""
    template_id: str
    version: str
    content: str
    last_modified: str = ""


@dataclass
class ModelConfig:
    """AI model provider configuration."""
    provider: str  # 'bedrock' | 'openai' | 'azure-openai'
    model_id: str
    region: str | None = None
    api_key_secret_arn: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.1


@dataclass
class ForecastResult:
    """Output of the forecast engine."""
    projections: list[dict[str, Any]] = field(default_factory=list)
    seasonal_patterns: dict[str, Any] | None = None
    anomalies_excluded: list[dict[str, Any]] = field(default_factory=list)
    scenario_impact: float | None = None


@dataclass
class EnrichedTip:
    """Pre-enriched optimization tip with runtime metadata."""
    tip_id: str
    service: str
    api_endpoint: str = ""
    parameter_schema: dict[str, Any] = field(default_factory=dict)
    response_format: dict[str, Any] = field(default_factory=dict)
    cost_thresholds: dict[str, Any] = field(default_factory=dict)
    optimization_rules: list[dict[str, Any]] = field(default_factory=list)
    last_enriched: str = ""
