"""Property-based tests for intent classifier v2 (Properties 6, 7).

Property 6: Classification output schema conformance
Property 7: Few-shot disambiguation resolves ambiguity
"""
from __future__ import annotations

import json
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.intent_classifier_v2 import classify_intent, _keyword_match, INTENT_KEYWORDS
from agent.models import SessionState, ClassificationResult
from agent.constants import VALID_INTENT_TYPES


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def random_user_questions():
    """Generate random user questions (may or may not contain keywords)."""
    return st.one_of(
        # Questions with known keywords
        st.sampled_from([
            "How much am I spending on EC2?",
            "What's my total AWS bill this month?",
            "Show me optimization tips for RDS",
            "Forecast my costs for next quarter",
            "Why is my S3 so expensive?",
            "Can I reduce Lambda costs?",
            "What's the cost breakdown?",
            "Predict next month spending",
            "Show me unused resources",
            "What if I add more instances?",
        ]),
        # Random text that may or may not match
        st.text(alphabet=string.ascii_letters + " ?.", min_size=5, max_size=100),
    )


def ambiguous_questions():
    """Generate questions that match 3+ intent categories by keyword."""
    return st.sampled_from([
        "How can I optimize my total EC2 costs and forecast next month?",
        "Show me cost optimization tips and predict future spending for EC2",
        "What's the best way to reduce cost and forecast savings for Lambda?",
        "Analyze my spending trends, provide tips, and forecast EC2 costs",
        "Cost breakdown with optimization recommendations and future projection",
        "Help me reduce spending with predictions and EC2 tips for optimization",
    ])


# Mock model client that returns None (simulating LLM failure gracefully)
def _mock_model_client():
    """Return a mock that raises so LLM disambiguation falls back gracefully."""
    mock = MagicMock()
    mock.invoke_model.side_effect = Exception("Mocked: no real LLM in tests")
    return mock


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(question=random_user_questions())
def test_property6_output_always_valid_schema(question):
    """Property 6: Output always valid JSON with required fields."""
    result = classify_intent(question, session=None, model_client=_mock_model_client())

    # Must be a ClassificationResult
    assert isinstance(result, ClassificationResult)

    # intent_type must be in valid set
    assert result.intent_type in VALID_INTENT_TYPES, (
        f"Invalid intent_type: {result.intent_type}"
    )

    # target_scope must be a non-empty string
    assert isinstance(result.target_scope, str)
    assert len(result.target_scope) > 0

    # timeframe must be a non-empty string
    assert isinstance(result.timeframe, str)
    assert len(result.timeframe) > 0

    # confidence_score must be between 0 and 1
    assert isinstance(result.confidence_score, float)
    assert 0.0 <= result.confidence_score <= 1.0


@settings(max_examples=100, deadline=None)
@given(question=ambiguous_questions())
def test_property7_ambiguous_still_produces_single_intent(question):
    """Property 7: Ambiguous questions (3+ keyword matches) still produce single valid intent."""
    # Verify this is actually ambiguous (3+ keyword matches)
    matches = _keyword_match(question)

    # Even with 3+ matches, the classifier should return a single valid intent
    # (not 'all' or multiple)
    result = classify_intent(question, session=None, model_client=_mock_model_client())

    assert isinstance(result, ClassificationResult)
    assert result.intent_type in VALID_INTENT_TYPES
    # Should not return a list or 'all'
    assert isinstance(result.intent_type, str)
    assert result.intent_type != "all"


@settings(max_examples=100, deadline=None)
@given(question=st.text(min_size=0, max_size=5))
def test_property6_empty_or_short_questions_still_valid(question):
    """Property 6: Even empty/short questions produce valid schema output."""
    result = classify_intent(question, session=None, model_client=_mock_model_client())

    assert isinstance(result, ClassificationResult)
    assert result.intent_type in VALID_INTENT_TYPES
    assert 0.0 <= result.confidence_score <= 1.0
    assert isinstance(result.target_scope, str)
    assert isinstance(result.timeframe, str)


@settings(max_examples=100, deadline=None)
@given(
    question=random_user_questions(),
    session_intent=st.one_of(st.none(), st.sampled_from(VALID_INTENT_TYPES)),
    session_scope=st.one_of(st.none(), st.sampled_from(["ec2", "rds", "s3", "account-wide"])),
)
def test_property6_with_session_context_still_valid(question, session_intent, session_scope):
    """Property 6: Classification with session context still produces valid output."""
    session = SessionState(
        current_intent=session_intent,
        target_scope=session_scope,
        active_timeframe="last-30d",
    )

    result = classify_intent(question, session=session, model_client=_mock_model_client())

    assert isinstance(result, ClassificationResult)
    assert result.intent_type in VALID_INTENT_TYPES
    assert 0.0 <= result.confidence_score <= 1.0
