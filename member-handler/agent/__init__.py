"""
SlashMyBill Agent Pipeline - Modular AI agent for cloud cost optimization.

Pipeline stages:
  Account Resolver → Session State → Intent Classifier → Payload Assembler →
  Behavioral Router → Output Validator → Response Builder
"""
from __future__ import annotations

from .models import (
    AccountContext,
    SessionState,
    ClassificationResult,
    ContextBudget,
    ExecutionPayload,
    PromptTemplate,
    ModelConfig,
    ForecastResult,
    EnrichedTip,
)
from .pipeline import execute_pipeline

__all__ = [
    "AccountContext",
    "SessionState",
    "ClassificationResult",
    "ContextBudget",
    "ExecutionPayload",
    "PromptTemplate",
    "ModelConfig",
    "ForecastResult",
    "EnrichedTip",
    "execute_pipeline",
]
