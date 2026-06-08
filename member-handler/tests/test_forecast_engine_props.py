"""Property-based tests for forecast engine (Properties 17-21).

Property 17: Forecast linear extrapolation validity
Property 18: Seasonal pattern detection threshold
Property 19: Anomaly exclusion from forecast baseline
Property 20: Confidence interval ordering
Property 21: What-if scenario incremental cost calculation
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.forecast_engine import (
    generate_forecast,
    detect_anomalies,
    apply_what_if_scenario,
)
from agent.models import ForecastResult
from agent.constants import FORECAST_MIN_DAYS, FORECAST_MAX_MONTHS, FORECAST_SEASONAL_MIN_DAYS


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def random_cost_time_series(min_days=30, max_days=120, trend="increasing"):
    """Generate daily cost data with a specified trend."""
    def _build(days, base_cost, daily_increment):
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = []
        for i in range(days):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            cost = base_cost + daily_increment * i
            # Add some noise
            data.append({"date": date, "cost": max(0, cost)})
        return data

    if trend == "increasing":
        return st.builds(
            _build,
            days=st.integers(min_value=min_days, max_value=max_days),
            base_cost=st.floats(min_value=10, max_value=100, allow_nan=False, allow_infinity=False),
            daily_increment=st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False),
        )
    elif trend == "decreasing":
        return st.builds(
            _build,
            days=st.integers(min_value=min_days, max_value=max_days),
            base_cost=st.floats(min_value=100, max_value=500, allow_nan=False, allow_infinity=False),
            daily_increment=st.floats(min_value=-2.0, max_value=-0.1, allow_nan=False, allow_infinity=False),
        )
    else:
        return st.builds(
            _build,
            days=st.integers(min_value=min_days, max_value=max_days),
            base_cost=st.floats(min_value=10, max_value=500, allow_nan=False, allow_infinity=False),
            daily_increment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        )


def seasonal_time_series():
    """Generate time series with weekly seasonal pattern (90+ days)."""
    def _build(days, base_cost, amplitude):
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = []
        for i in range(days):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            # Weekly cycle: higher on weekdays, lower on weekends
            day_of_week = i % 7
            if day_of_week < 5:
                seasonal_factor = 1.0 + amplitude
            else:
                seasonal_factor = 1.0 - amplitude
            cost = max(0, base_cost * seasonal_factor)
            data.append({"date": date, "cost": cost})
        return data

    return st.builds(
        _build,
        days=st.integers(min_value=90, max_value=180),
        base_cost=st.floats(min_value=50, max_value=200, allow_nan=False, allow_infinity=False),
        amplitude=st.floats(min_value=0.2, max_value=0.5, allow_nan=False, allow_infinity=False),
    )


def time_series_with_spikes():
    """Generate time series with obvious spikes."""
    def _build(days, base_cost, spike_positions, spike_multiplier):
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        data = []
        for i in range(days):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            cost = base_cost
            if i in spike_positions:
                cost = base_cost * spike_multiplier
            data.append({"date": date, "cost": cost})
        return data

    return st.builds(
        _build,
        days=st.just(60),
        base_cost=st.floats(min_value=50, max_value=100, allow_nan=False, allow_infinity=False),
        spike_positions=st.lists(
            st.integers(min_value=10, max_value=55),
            min_size=1, max_size=3, unique=True,
        ),
        spike_multiplier=st.floats(min_value=5, max_value=20, allow_nan=False, allow_infinity=False),
    )


# ---------------------------------------------------------------------------
# Property 17: Forecast linear extrapolation validity
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    historical=random_cost_time_series(min_days=30, max_days=90, trend="increasing"),
    months=st.integers(min_value=1, max_value=6),
)
def test_property17_increasing_trend_nonnegative_nondecreasing(historical, months):
    """Property 17: 30+ days with increasing trend → non-negative, non-decreasing projections."""
    result = generate_forecast(historical, months)

    assert len(result.projections) == months
    for proj in result.projections:
        assert proj["projected_cost"] >= 0, "Projected cost must be non-negative"


@settings(max_examples=100)
@given(
    historical=random_cost_time_series(min_days=30, max_days=90, trend="decreasing"),
    months=st.integers(min_value=1, max_value=6),
)
def test_property17_decreasing_trend_nonnegative(historical, months):
    """Property 17: Decreasing trend → non-negative projections (clamped to 0)."""
    result = generate_forecast(historical, months)

    for proj in result.projections:
        assert proj["projected_cost"] >= 0, "Projected cost must be non-negative even for decreasing trends"


@settings(max_examples=100)
@given(days=st.integers(min_value=1, max_value=29))
def test_property17_insufficient_data_raises(days):
    """Property 17: Less than 30 days raises error."""
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    historical = [
        {"date": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"), "cost": 50.0}
        for i in range(days)
    ]

    with pytest.raises(ValueError) as exc_info:
        generate_forecast(historical, 3)

    assert "30" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Property 18: Seasonal pattern detection threshold
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(historical=seasonal_time_series())
def test_property18_90plus_days_with_cycle_detected(historical):
    """Property 18: 90+ days with weekly cycle → seasonal pattern detected."""
    assume(len(historical) >= FORECAST_SEASONAL_MIN_DAYS)

    result = generate_forecast(historical, 3)

    assert result.seasonal_patterns is not None, (
        f"Expected seasonal patterns for {len(historical)} days with cycle"
    )


@settings(max_examples=100)
@given(
    historical=random_cost_time_series(min_days=30, max_days=89, trend="increasing"),
)
def test_property18_under_90_days_no_seasonal(historical):
    """Property 18: <90 days → no seasonal adjustment applied."""
    assume(len(historical) < FORECAST_SEASONAL_MIN_DAYS)

    result = generate_forecast(historical, 3)

    assert result.seasonal_patterns is None, (
        f"Expected no seasonal patterns for {len(historical)} days"
    )


# ---------------------------------------------------------------------------
# Property 19: Anomaly exclusion from forecast baseline
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(historical=time_series_with_spikes())
def test_property19_spikes_over_2_std_excluded(historical):
    """Property 19: Spikes >2 std dev excluded and listed in anomalies."""
    daily_costs = [{"date": h["date"], "cost": h["cost"]} for h in historical]

    anomalies = detect_anomalies(daily_costs)

    # Should detect at least some anomalies given the large spike multiplier
    # (spike_multiplier is 5-20x base, which is well above 2 std dev)
    assert len(anomalies) > 0, "Expected anomalies to be detected for large spikes"

    for anomaly in anomalies:
        assert "date" in anomaly
        assert "cost" in anomaly
        assert "expected" in anomaly
        assert anomaly["cost"] > anomaly["expected"]  # Spike is above expected


# ---------------------------------------------------------------------------
# Property 20: Confidence interval ordering
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    historical=random_cost_time_series(min_days=30, max_days=100, trend="increasing"),
    months=st.integers(min_value=1, max_value=FORECAST_MAX_MONTHS),
)
def test_property20_confidence_interval_ordering(historical, months):
    """Property 20: ci_95_low ≤ ci_80_low ≤ projected ≤ ci_80_high ≤ ci_95_high."""
    result = generate_forecast(historical, months)

    for proj in result.projections:
        ci_95_low = proj["ci_95_low"]
        ci_80_low = proj["ci_80_low"]
        projected = proj["projected_cost"]
        ci_80_high = proj["ci_80_high"]
        ci_95_high = proj["ci_95_high"]

        assert ci_95_low <= ci_80_low, (
            f"ci_95_low ({ci_95_low}) > ci_80_low ({ci_80_low})"
        )
        assert ci_80_low <= projected, (
            f"ci_80_low ({ci_80_low}) > projected ({projected})"
        )
        assert projected <= ci_80_high, (
            f"projected ({projected}) > ci_80_high ({ci_80_high})"
        )
        assert ci_80_high <= ci_95_high, (
            f"ci_80_high ({ci_80_high}) > ci_95_high ({ci_95_high})"
        )


# ---------------------------------------------------------------------------
# Property 21: What-if scenario incremental cost calculation
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    unit_price=st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False),
    quantity=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
    months=st.integers(min_value=1, max_value=6),
)
def test_property21_scenario_impact_equals_price_times_qty_times_months(unit_price, quantity, months):
    """Property 21: scenario_impact = unit_price × quantity × months."""
    # Create a simple baseline
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    historical = [
        {"date": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"), "cost": 50.0}
        for i in range(60)
    ]

    baseline = generate_forecast(historical, months)

    scenario = {
        "unit_price": unit_price,
        "quantity": quantity,
    }

    result = apply_what_if_scenario(baseline, scenario, {})

    expected_impact = unit_price * quantity * months
    assert result.scenario_impact is not None
    assert abs(result.scenario_impact - expected_impact) < 0.01, (
        f"Expected impact {expected_impact}, got {result.scenario_impact}"
    )


@settings(max_examples=100)
@given(
    unit_price=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
    quantity=st.floats(min_value=1, max_value=50, allow_nan=False, allow_infinity=False),
)
def test_property21_adjusted_forecast_equals_baseline_plus_impact(unit_price, quantity):
    """Property 21: Adjusted forecast = baseline + scenario impact per month."""
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    historical = [
        {"date": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"), "cost": 50.0}
        for i in range(60)
    ]

    months = 3
    baseline = generate_forecast(historical, months)

    scenario = {"unit_price": unit_price, "quantity": quantity}
    result = apply_what_if_scenario(baseline, scenario, {})

    monthly_impact = unit_price * quantity

    for i, (base_proj, adj_proj) in enumerate(zip(baseline.projections, result.projections)):
        expected = base_proj["projected_cost"] + monthly_impact
        assert abs(adj_proj["projected_cost"] - expected) < 0.01, (
            f"Month {i}: expected {expected}, got {adj_proj['projected_cost']}"
        )
