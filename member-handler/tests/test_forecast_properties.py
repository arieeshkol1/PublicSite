"""Property-based tests for invoice_forecast (Forecast Engine).

Covers design Properties 4, 5, 6, 7, 8, 9, 10, 16 — pure-math and
predicate correctness. AWS access is not exercised here.
"""

import calendar
import os
import re
import sys
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import invoice_forecast as fe  # noqa: E402

RUNS = 100
ID_RE = re.compile(r'^Forecast-\d{4}-(0[1-9]|1[0-2])$')


# ─── Property 4: Forecast window predicate ────────────────────────────────────

@given(
    year=st.integers(min_value=2000, max_value=2100),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=31),
)
@settings(max_examples=RUNS)
def test_property4_forecast_window(year, month, day):
    days_in_month = calendar.monthrange(year, month)[1]
    if day > days_in_month:
        return
    now = datetime(year, month, day, 12, 0, tzinfo=timezone.utc)
    expected = (fe.FORECAST_START_DAY <= day <= days_in_month)
    assert fe.is_in_forecast_window(now) is expected


# ─── Property 5: Forecast identifier format and validation ────────────────────

@given(
    year=st.integers(min_value=1000, max_value=9999),
    month=st.integers(min_value=1, max_value=12),
)
@settings(max_examples=RUNS)
def test_property5_id_format_valid(year, month):
    fid = fe.forecast_invoice_id(year, month)
    assert ID_RE.match(fid)
    ym = fid[len('Forecast-'):]
    py, pm = ym.split('-')
    assert int(py) == year and int(pm) == month


@given(month=st.integers().filter(lambda m: m < 1 or m > 12))
@settings(max_examples=RUNS)
def test_property5_id_invalid_month_raises(month):
    with pytest.raises(fe.ForecastError):
        fe.forecast_invoice_id(2026, month)


# ─── Property 6: Median definition ────────────────────────────────────────────

@given(values=st.lists(st.floats(min_value=0, max_value=1e6,
                                  allow_nan=False, allow_infinity=False),
                        min_size=1, max_size=40))
@settings(max_examples=RUNS)
def test_property6_median(values):
    result = fe.median(values)
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        expected = ordered[mid]
    else:
        expected = (ordered[mid - 1] + ordered[mid]) / 2.0
    assert result == pytest.approx(expected)


def test_property6_median_empty():
    assert fe.median([]) == 0.0


# ─── Property 7: Variable forecast formula ────────────────────────────────────

@given(
    mtd=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    daily=st.lists(st.floats(min_value=0, max_value=1e5, allow_nan=False,
                             allow_infinity=False), min_size=1, max_size=28),
    days_in_month=st.integers(min_value=28, max_value=31),
)
@settings(max_examples=RUNS)
def test_property7_variable_forecast(mtd, daily, days_in_month):
    elapsed = len(daily)
    if elapsed > days_in_month:
        daily = daily[:days_in_month]
        elapsed = len(daily)
    remaining = days_in_month - elapsed
    result = fe.compute_variable_forecast(mtd, fe.median(daily), remaining)
    expected = mtd + fe.median(daily) * remaining
    assert result == pytest.approx(expected)


# ─── Property 8: Forecast total composition and rounding ──────────────────────

@given(
    variable=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    amounts=st.lists(st.floats(min_value=0, max_value=1e4, allow_nan=False,
                               allow_infinity=False), max_size=10),
)
@settings(max_examples=RUNS)
def test_property8_total_composition(variable, amounts):
    components = [{'model': 'fixed', 'amount': a} for a in amounts]
    fixed = fe.compute_fixed_forecast(components, variable)
    total = fe.round_half_up_2dp(variable + fixed)
    # at most 2 decimal places
    assert total == total.quantize(total)
    assert -total.as_tuple().exponent <= 2
    expected = fe.round_half_up_2dp(variable + sum(amounts))
    assert total == expected


@given(variable=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=RUNS)
def test_property8_empty_fixed_equals_variable(variable):
    fixed = fe.compute_fixed_forecast([], variable)
    assert fixed == 0.0
    assert fe.round_half_up_2dp(variable + fixed) == fe.round_half_up_2dp(variable)


# ─── Property 9: Fixed-cost detection records amount and percentage ───────────

@given(
    amount=st.floats(min_value=1, max_value=1e4, allow_nan=False, allow_infinity=False),
    total=st.floats(min_value=1, max_value=1e5, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=RUNS)
def test_property9_percentage_application(amount, total):
    share = amount / total
    comp = [{'model': 'percentage', 'amount': amount, 'share': share}]
    projected = 5000.0
    result = fe.compute_fixed_forecast(comp, projected)
    assert result == pytest.approx(share * projected)


# ─── Property 16: Provider scope of forecasting ───────────────────────────────

@given(provider=st.sampled_from(['aws', 'AWS', ' aws ', 'Aws']))
@settings(max_examples=RUNS)
def test_property16_aws_is_aws(provider):
    assert fe.is_aws_provider(provider) is True


@given(provider=st.sampled_from(['openai', 'azure', 'gcp', 'AWSX', 'amazon', '']))
@settings(max_examples=RUNS)
def test_property16_non_aws(provider):
    assert fe.is_aws_provider(provider) is False


def test_property16_none_is_non_aws():
    assert fe.is_aws_provider(None) is False


# ─── Property 10: Forecast omission conditions (provider/window gates) ─────────

def test_property10_non_aws_returns_none():
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    assert fe.compute_forecast('m@e.com', '123456789012', 'openai', now=now,
                               creds={}) is None


def test_property10_before_window_returns_none():
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)  # day 2 < 4
    assert fe.compute_forecast('m@e.com', '123456789012', 'aws', now=now,
                               creds={}) is None
