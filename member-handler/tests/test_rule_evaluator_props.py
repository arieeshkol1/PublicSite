"""Property-based tests for rule evaluator (Property 16).

Property 16: Optimization rule evaluation
Metrics breaching thresholds always flagged (no false negatives).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.tips_enrichment import evaluate_rules


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def metric_values():
    """Generate metric values."""
    return st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)


def threshold_values():
    """Generate threshold values."""
    return st.floats(min_value=1, max_value=99, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    metric_value=st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=10, max_value=100, allow_nan=False, allow_infinity=False),
)
def test_property16_value_below_threshold_flagged_for_less_than(metric_value, threshold):
    """Property 16: Metric clearly below threshold flagged for < rule (no false negatives)."""
    assume(metric_value < threshold - 1)  # Clearly below

    metrics = {"avg_cpu": metric_value}
    rules = [{"condition": f"avg_cpu < {threshold}", "action": "recommend_downsize", "priority": 1}]

    triggered = evaluate_rules(metrics, rules)

    assert len(triggered) > 0, (
        f"Expected rule to trigger for avg_cpu={metric_value} < {threshold}"
    )
    assert triggered[0]["action"] == "recommend_downsize"


@settings(max_examples=100)
@given(
    metric_value=st.floats(min_value=50, max_value=100, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=1, max_value=45, allow_nan=False, allow_infinity=False),
)
def test_property16_value_above_threshold_flagged_for_greater_than(metric_value, threshold):
    """Property 16: Metric clearly above threshold flagged for > rule (no false negatives)."""
    assume(metric_value > threshold + 1)  # Clearly above

    metrics = {"avg_cpu": metric_value}
    rules = [{"condition": f"avg_cpu > {threshold}", "action": "recommend_upsize", "priority": 2}]

    triggered = evaluate_rules(metrics, rules)

    assert len(triggered) > 0, (
        f"Expected rule to trigger for avg_cpu={metric_value} > {threshold}"
    )
    assert triggered[0]["action"] == "recommend_upsize"


@settings(max_examples=100)
@given(
    cpu_value=st.floats(min_value=0, max_value=5, allow_nan=False, allow_infinity=False),
    max_cpu_value=st.floats(min_value=0, max_value=25, allow_nan=False, allow_infinity=False),
)
def test_property16_compound_condition_both_breach(cpu_value, max_cpu_value):
    """Property 16: Compound AND conditions trigger when all parts breach."""
    assume(cpu_value < 10)
    assume(max_cpu_value < 30)

    metrics = {"avg_cpu": cpu_value, "max_cpu": max_cpu_value}
    rules = [{"condition": "avg_cpu < 10 AND max_cpu < 30", "action": "recommend_downsize", "priority": 1}]

    triggered = evaluate_rules(metrics, rules)

    assert len(triggered) > 0, (
        f"Expected compound rule to trigger for avg_cpu={cpu_value}, max_cpu={max_cpu_value}"
    )


@settings(max_examples=100)
@given(
    cpu_value=st.floats(min_value=15, max_value=100, allow_nan=False, allow_infinity=False),
    threshold=st.floats(min_value=1, max_value=10, allow_nan=False, allow_infinity=False),
)
def test_property16_value_not_breaching_not_flagged(cpu_value, threshold):
    """Property 16: Values not breaching threshold are not flagged (no false positives)."""
    assume(cpu_value > threshold + 2)  # Clearly above threshold for a < rule

    metrics = {"avg_cpu": cpu_value}
    rules = [{"condition": f"avg_cpu < {threshold}", "action": "recommend_downsize", "priority": 1}]

    triggered = evaluate_rules(metrics, rules)

    assert len(triggered) == 0, (
        f"Expected no trigger for avg_cpu={cpu_value} (not < {threshold})"
    )


@settings(max_examples=100)
@given(
    metric_value=metric_values(),
)
def test_property16_missing_metric_no_crash(metric_value):
    """Property 16: Rules referencing missing metrics don't crash."""
    metrics = {"some_other_metric": metric_value}
    rules = [{"condition": "avg_cpu < 10", "action": "recommend_downsize", "priority": 1}]

    # Should not raise
    triggered = evaluate_rules(metrics, rules)
    assert isinstance(triggered, list)
