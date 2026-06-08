"""Forecast engine - cost projections with seasonal detection and what-if scenarios."""
from __future__ import annotations

import logging
import math
from typing import Any

from .models import ForecastResult
from .constants import FORECAST_MIN_DAYS, FORECAST_MAX_MONTHS, FORECAST_SEASONAL_MIN_DAYS, ANOMALY_STD_THRESHOLD

logger = logging.getLogger(__name__)


def generate_forecast(
    historical_data: list[dict[str, Any]],
    projection_months: int,
    scenario: dict[str, Any] | None = None,
) -> ForecastResult:
    """Generate cost forecast using linear extrapolation.

    Requires minimum 30 days of historical data.
    Supports projection periods of 1-12 months.
    """
    # Validate inputs
    if not historical_data or len(historical_data) < FORECAST_MIN_DAYS:
        raise ValueError(
            f"Need at least {FORECAST_MIN_DAYS} days of historical data. "
            f"Got: {len(historical_data) if historical_data else 0} days."
        )

    if projection_months < 1 or projection_months > FORECAST_MAX_MONTHS:
        raise ValueError(
            f"Projection period must be 1-{FORECAST_MAX_MONTHS} months. "
            f"Requested: {projection_months} months."
        )

    # Extract daily costs
    daily_costs = _extract_daily_costs(historical_data)

    # Detect and exclude anomalies
    anomalies = detect_anomalies(daily_costs)
    anomaly_dates = {a["date"] for a in anomalies}
    clean_costs = [d for d in daily_costs if d["date"] not in anomaly_dates]

    # If too many anomalies removed, use original
    if len(clean_costs) < FORECAST_MIN_DAYS:
        clean_costs = daily_costs

    # Calculate linear trend
    slope, intercept = _linear_regression(clean_costs)

    # Detect seasonal patterns (if 90+ days)
    seasonal_patterns = None
    if len(daily_costs) >= FORECAST_SEASONAL_MIN_DAYS:
        seasonal_patterns = _detect_seasonal_patterns(daily_costs)

    # Generate projections
    projections = _generate_projections(
        clean_costs, slope, intercept, projection_months, seasonal_patterns
    )

    # Apply what-if scenario if provided
    scenario_impact = None
    if scenario:
        scenario_result = apply_what_if_scenario(
            ForecastResult(projections=projections, seasonal_patterns=seasonal_patterns, anomalies_excluded=anomalies),
            scenario,
            {},
        )
        return scenario_result

    return ForecastResult(
        projections=projections,
        seasonal_patterns=seasonal_patterns,
        anomalies_excluded=anomalies,
        scenario_impact=scenario_impact,
    )


def detect_anomalies(
    daily_costs: list[dict[str, Any]],
    std_threshold: float = ANOMALY_STD_THRESHOLD,
) -> list[dict[str, Any]]:
    """Identify one-time spikes exceeding threshold from rolling mean.

    Returns list of anomalies with date, actual cost, and expected cost.
    """
    if len(daily_costs) < 7:
        return []

    costs = [d["cost"] for d in daily_costs]
    anomalies: list[dict[str, Any]] = []

    # Calculate rolling mean and std (window=7)
    window = min(7, len(costs) // 2)
    if window < 2:
        return []

    for i in range(window, len(costs)):
        window_costs = costs[i - window:i]
        mean = sum(window_costs) / len(window_costs)
        variance = sum((c - mean) ** 2 for c in window_costs) / len(window_costs)
        std = math.sqrt(variance) if variance > 0 else 0

        if std > 0 and abs(costs[i] - mean) > std_threshold * std:
            anomalies.append({
                "date": daily_costs[i]["date"],
                "cost": costs[i],
                "expected": round(mean, 2),
                "reason": f"spike > {std_threshold} std dev",
            })
        elif std == 0 and mean > 0 and abs(costs[i] - mean) > mean * std_threshold:
            # When std is 0 (constant data), treat deviation > threshold*mean as anomaly
            anomalies.append({
                "date": daily_costs[i]["date"],
                "cost": costs[i],
                "expected": round(mean, 2),
                "reason": f"spike > {std_threshold}x mean (zero variance window)",
            })

    return anomalies


def apply_what_if_scenario(
    baseline: ForecastResult,
    scenario: dict[str, Any],
    pricing_data: dict[str, Any],
) -> ForecastResult:
    """Calculate incremental cost from what-if scenario parameters.

    scenario_impact = unit_price × quantity × projection_period_months
    """
    unit_price = float(scenario.get("unit_price", 0))
    quantity = float(scenario.get("quantity", 0))
    projection_months = len(baseline.projections) if baseline.projections else 1

    # Calculate per-month impact
    monthly_impact = unit_price * quantity
    total_impact = monthly_impact * projection_months

    # Adjust each projection
    adjusted_projections = []
    for proj in baseline.projections:
        adjusted = proj.copy()
        adjusted["projected_cost"] = proj["projected_cost"] + monthly_impact
        adjusted["ci_80_low"] = proj["ci_80_low"] + monthly_impact
        adjusted["ci_80_high"] = proj["ci_80_high"] + monthly_impact
        adjusted["ci_95_low"] = proj["ci_95_low"] + monthly_impact
        adjusted["ci_95_high"] = proj["ci_95_high"] + monthly_impact
        adjusted["scenario_addition"] = monthly_impact
        adjusted_projections.append(adjusted)

    return ForecastResult(
        projections=adjusted_projections,
        seasonal_patterns=baseline.seasonal_patterns,
        anomalies_excluded=baseline.anomalies_excluded,
        scenario_impact=total_impact,
    )


def _extract_daily_costs(historical_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract and normalize daily costs from historical data."""
    daily = []
    for entry in historical_data:
        date = entry.get("date", "")
        cost = float(entry.get("cost", 0))
        daily.append({"date": date, "cost": cost})
    # Sort by date
    daily.sort(key=lambda x: x["date"])
    return daily


def _linear_regression(daily_costs: list[dict[str, Any]]) -> tuple[float, float]:
    """Calculate linear regression (slope, intercept) for daily cost data."""
    n = len(daily_costs)
    if n < 2:
        avg = daily_costs[0]["cost"] if daily_costs else 0
        return 0.0, avg

    # x = day index (0, 1, 2, ...), y = cost
    x_values = list(range(n))
    y_values = [d["cost"] for d in daily_costs]

    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)

    if denominator == 0:
        return 0.0, y_mean

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    return slope, intercept


def _detect_seasonal_patterns(daily_costs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Detect weekly and monthly seasonal patterns from 90+ days of data."""
    if len(daily_costs) < FORECAST_SEASONAL_MIN_DAYS:
        return None

    costs = [d["cost"] for d in daily_costs]
    overall_mean = sum(costs) / len(costs) if costs else 1

    # Weekly pattern detection (7-day cycle)
    weekly_factors = {}
    for i, entry in enumerate(daily_costs):
        day_of_week = i % 7
        if day_of_week not in weekly_factors:
            weekly_factors[day_of_week] = []
        weekly_factors[day_of_week].append(entry["cost"])

    weekly = {}
    has_weekly_pattern = False
    for day, values in weekly_factors.items():
        factor = (sum(values) / len(values)) / overall_mean if overall_mean > 0 else 1.0
        weekly[f"day_{day}"] = round(factor, 3)
        if abs(factor - 1.0) > 0.1:
            has_weekly_pattern = True

    # Monthly pattern detection (approximate 30-day cycle)
    monthly_factors = {}
    for i, entry in enumerate(daily_costs):
        day_of_month = i % 30
        bucket = day_of_month // 10  # 0=start, 1=mid, 2=end
        if bucket not in monthly_factors:
            monthly_factors[bucket] = []
        monthly_factors[bucket].append(entry["cost"])

    monthly = {}
    has_monthly_pattern = False
    labels = {0: "start_of_month", 1: "mid_month", 2: "end_of_month"}
    for bucket, values in monthly_factors.items():
        factor = (sum(values) / len(values)) / overall_mean if overall_mean > 0 else 1.0
        monthly[labels.get(bucket, f"period_{bucket}")] = round(factor, 3)
        if abs(factor - 1.0) > 0.1:
            has_monthly_pattern = True

    if not has_weekly_pattern and not has_monthly_pattern:
        return None

    result = {}
    if has_weekly_pattern:
        result["weekly"] = weekly
    if has_monthly_pattern:
        result["monthly"] = monthly

    return result if result else None


def _generate_projections(
    clean_costs: list[dict[str, Any]],
    slope: float,
    intercept: float,
    projection_months: int,
    seasonal_patterns: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Generate monthly projections with confidence intervals."""
    n = len(clean_costs)
    costs = [d["cost"] for d in clean_costs]

    # Calculate residual standard deviation for confidence intervals
    residuals = []
    for i, c in enumerate(costs):
        predicted = intercept + slope * i
        residuals.append(c - predicted)

    residual_std = math.sqrt(sum(r ** 2 for r in residuals) / max(1, len(residuals) - 2)) if len(residuals) > 2 else 0

    projections = []

    for month_idx in range(1, projection_months + 1):
        # Project daily cost at future point
        future_day = n + (month_idx * 30)
        daily_projected = intercept + slope * future_day

        # Monthly cost (30 days)
        monthly_projected = max(0, daily_projected * 30)

        # Apply seasonal adjustment if available
        if seasonal_patterns and "monthly" in seasonal_patterns:
            # Apply end-of-month factor as an average boost
            monthly_avg_factor = sum(seasonal_patterns["monthly"].values()) / len(seasonal_patterns["monthly"])
            monthly_projected *= monthly_avg_factor

        # Ensure non-negative
        monthly_projected = max(0, monthly_projected)

        # Confidence intervals (widen with projection distance)
        distance_factor = math.sqrt(month_idx)
        monthly_std = residual_std * 30 * distance_factor  # Scale to monthly

        # 80% CI: ~1.28 std deviations
        ci_80_low = max(0, monthly_projected - 1.28 * monthly_std)
        ci_80_high = monthly_projected + 1.28 * monthly_std

        # 95% CI: ~1.96 std deviations
        ci_95_low = max(0, monthly_projected - 1.96 * monthly_std)
        ci_95_high = monthly_projected + 1.96 * monthly_std

        # Enforce ordering: ci_95_low ≤ ci_80_low ≤ projected ≤ ci_80_high ≤ ci_95_high
        ci_95_low = min(ci_95_low, ci_80_low)
        ci_80_low = min(ci_80_low, monthly_projected)
        ci_80_high = max(ci_80_high, monthly_projected)
        ci_95_high = max(ci_95_high, ci_80_high)

        projections.append({
            "month": month_idx,
            "projected_cost": round(monthly_projected, 2),
            "ci_80_low": round(ci_80_low, 2),
            "ci_80_high": round(ci_80_high, 2),
            "ci_95_low": round(ci_95_low, 2),
            "ci_95_high": round(ci_95_high, 2),
        })

    return projections
