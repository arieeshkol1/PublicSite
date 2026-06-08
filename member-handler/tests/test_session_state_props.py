"""Property-based tests for session state (Property 5).

Property 5: Session state carry-forward
For any existing session state and follow-up question, if the question does not
explicitly override a session parameter, that parameter SHALL be preserved.
"""
from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.models import SessionState, AccountContext
from agent.session_state import update_session


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def random_session_state():
    """Generate random session states with various parameter combinations."""
    return st.builds(
        SessionState,
        account_context=st.just(None),
        current_intent=st.one_of(
            st.none(),
            st.sampled_from(["Cost_Analysis_General", "Cost_Analysis_Specific", "Optimization_Tips", "Forecasting"]),
        ),
        target_scope=st.one_of(
            st.none(),
            st.sampled_from(["ec2", "rds", "s3", "lambda", "account-wide"]),
        ),
        active_timeframe=st.one_of(
            st.none(),
            st.sampled_from(["last-7d", "last-30d", "last-90d", "next-1m", "next-3m"]),
        ),
        conversation_history=st.just([]),
        last_updated=st.just("2024-01-01T00:00:00Z"),
    )


def intent_result_missing_fields():
    """Generate intent results with some fields missing (simulating follow-up)."""
    return st.fixed_dictionaries({}, optional={
        "intent_type": st.sampled_from(["Cost_Analysis_General", "Cost_Analysis_Specific", "Optimization_Tips", "Forecasting"]),
        "target_scope": st.sampled_from(["ec2", "rds", "s3", "lambda", "account-wide"]),
        "timeframe": st.sampled_from(["last-7d", "last-30d", "last-90d", "next-1m"]),
    })


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    session=random_session_state(),
    intent_result=intent_result_missing_fields(),
)
def test_property5_unchanged_params_preserved(session, intent_result):
    """Property 5: Unchanged params are preserved from prior session."""
    original_intent = session.current_intent
    original_scope = session.target_scope
    original_timeframe = session.active_timeframe

    updated = update_session(session, intent_result)

    # If intent_result provides a field, updated should use it
    # If intent_result doesn't provide a field, updated should keep original
    if "intent_type" in intent_result:
        assert updated.current_intent == intent_result["intent_type"]
    else:
        assert updated.current_intent == original_intent

    if "target_scope" in intent_result:
        assert updated.target_scope == intent_result["target_scope"]
    else:
        assert updated.target_scope == original_scope

    if "timeframe" in intent_result:
        assert updated.active_timeframe == intent_result["timeframe"]
    else:
        assert updated.active_timeframe == original_timeframe


@settings(max_examples=100)
@given(session=random_session_state())
def test_property5_empty_intent_result_preserves_all(session):
    """Property 5: Empty intent result preserves all session parameters."""
    original_intent = session.current_intent
    original_scope = session.target_scope
    original_timeframe = session.active_timeframe

    updated = update_session(session, {})

    assert updated.current_intent == original_intent
    assert updated.target_scope == original_scope
    assert updated.active_timeframe == original_timeframe


@settings(max_examples=100)
@given(
    session=random_session_state(),
    intent_result=st.fixed_dictionaries({
        "intent_type": st.sampled_from(["Cost_Analysis_General", "Cost_Analysis_Specific", "Optimization_Tips", "Forecasting"]),
        "target_scope": st.sampled_from(["ec2", "rds", "s3", "lambda", "account-wide"]),
        "timeframe": st.sampled_from(["last-7d", "last-30d", "last-90d", "next-1m"]),
    }),
)
def test_property5_full_override_uses_new_values(session, intent_result):
    """Property 5: Full intent result overrides all session parameters."""
    updated = update_session(session, intent_result)

    assert updated.current_intent == intent_result["intent_type"]
    assert updated.target_scope == intent_result["target_scope"]
    assert updated.active_timeframe == intent_result["timeframe"]
