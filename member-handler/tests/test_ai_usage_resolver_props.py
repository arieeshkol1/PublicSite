"""Property-based tests for the three-tier AI usage resolver.

Feature: vendor-agnostic-ai-usage

Covers:
  Property 6  — Resolution is cache-first and tiers run in strict order.
                (Validates Requirements 4.1, 4.3, 4.4, 11.1)
  Property 7  — Fresh full-coverage cache short-circuits deeper tiers.
                (Validates Requirements 4.2)
  Property 8  — Staleness is an exact age comparison.
                (Validates Requirements 4.5)
  Property 9  — Tier-2 trigger predicate is exactly the union of five conditions.
                (Validates Requirements 5.1, 5.2, 5.3, 5.4, 5.5)
  Property 10 — Tier-2/Tier-3 results are written back under neutral keys.
                (Validates Requirements 4.6)
  Property 15 — Responses are capped to the highest-cost entries.
                (Validates Requirements 12.2)
  Property 16 — Tier 3 is bounded and degrades to the best lower-tier result.
                (Validates Requirements 12.3, 12.4)

DynamoDB / KMS / HTTP are all mocked — no live calls.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st
from boto3.dynamodb.conditions import Key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cache_service
from cache_service import (
    build_cost_rollup_sort_key,
    build_usage_detail_sort_key,
    build_neutral_partition_key,
    shape_cost_rollup_item,
    shape_usage_detail_item,
    is_stale,
    within_staleness,
    tier2_trigger_reasons,
    should_trigger_tier2,
    window_dates_inclusive,
    NEUTRAL_USAGE_UNIT,
)
import incremental_fetch_engine
from incremental_fetch_engine import (
    resolve_ai_usage,
    build_ai_usage_response,
    _default_tier3_call,
    DrilldownResult,
    LiveResult,
)


# ---------------------------------------------------------------------------
# Fake cache table (mocks DynamoDB) — introspects the Key condition to filter
# by partition key and sort-key BETWEEN range, so both COST# and USAGE# reads
# work without a real DynamoDB.
# ---------------------------------------------------------------------------

class FakeCacheTable:
    def __init__(self, items=None, read_log=None, read_tag='tier1'):
        self.items = list(items or [])
        self.written = []
        self._read_log = read_log
        self._read_tag = read_tag

    @staticmethod
    def _extract(cond):
        expr = cond.get_expression()
        pk = low = high = None
        for v in expr['values']:
            sub = v.get_expression()
            if sub['operator'] == '=':
                pk = sub['values'][1]
            elif sub['operator'] == 'BETWEEN':
                low = sub['values'][1]
                high = sub['values'][2]
        return pk, low, high

    def query(self, KeyConditionExpression=None, ExclusiveStartKey=None, **kwargs):
        if self._read_log is not None:
            self._read_log.append(self._read_tag)
        pk, low, high = self._extract(KeyConditionExpression)
        matched = [
            it for it in self.items
            if it.get('pk') == pk and low <= str(it.get('sk', '')) <= high
        ]
        return {'Items': matched}

    def batch_writer(self):
        outer = self

        class _BW:
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                return False

            def put_item(self_, Item=None):
                outer.written.append(Item)
                outer.items.append(Item)

        return _BW()


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

emails = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=10),
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8),
)
account_ids = st.text(alphabet='0123456789', min_size=6, max_size=12)
dimensions = st.sampled_from(['cost', 'units', 'actor'])

REF_NOW = datetime(2025, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


@st.composite
def _windows(draw):
    """Generate a small inclusive {start, end} window ending near REF_NOW."""
    start = draw(st.integers(min_value=0, max_value=10))
    length = draw(st.integers(min_value=0, max_value=5))
    end_dt = REF_NOW - timedelta(days=start)
    start_dt = end_dt - timedelta(days=length)
    return {'start': start_dt.strftime('%Y-%m-%d'), 'end': end_dt.strftime('%Y-%m-%d')}


windows = _windows()


# ---------------------------------------------------------------------------
# Property 6 — cache-first, strict tier ordering
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(member_email=emails, account_id=account_ids, dimension=dimensions, window=windows)
def test_property6_cache_first_strict_ordering(member_email, account_id, dimension, window):
    """Tier 1 read precedes Tier 2 / Tier 3; Tier 2 precedes Tier 3; no live
    call before a cache read (Property 6)."""
    log = []
    table = FakeCacheTable(items=[], read_log=log, read_tag='tier1')  # empty → triggers Tier 2

    def tier2(me, aid, svc, period):
        log.append('tier2')
        return DrilldownResult(satisfied=False)

    def tier3(me, aid, dim, svc, period, connector=None, now=None):
        log.append('tier3')
        return LiveResult(items=[], partial=False)

    resolve_ai_usage(
        member_email, account_id, dimension, service=None, period=window,
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert 'tier1' in log
    first_tier1 = log.index('tier1')
    # No tier2/tier3 before the first tier1 read (cache-first).
    for marker in ('tier2', 'tier3'):
        if marker in log:
            assert log.index(marker) > first_tier1
    # Tier 2 before Tier 3.
    if 'tier2' in log and 'tier3' in log:
        assert log.index('tier2') < log.index('tier3')


# ---------------------------------------------------------------------------
# Property 7 — fresh full-coverage short-circuit
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(member_email=emails, account_id=account_ids, dimension=dimensions, window=windows)
def test_property7_fresh_full_coverage_short_circuits(member_email, account_id, dimension, window):
    """A fresh, fully covered window with no service scope is answered from the
    cache alone — neither Tier 2 nor Tier 3 is invoked (Property 7)."""
    dates = window_dates_inclusive(window['start'], window['end'])
    fresh = REF_NOW.isoformat()
    rollups = [
        shape_cost_rollup_item(member_email, account_id, d, 10.0, 'USD', cached_at=fresh)
        for d in dates
    ]
    table = FakeCacheTable(items=rollups)

    called = {'t2': False, 't3': False}

    def tier2(*a, **k):
        called['t2'] = True
        return DrilldownResult(satisfied=False)

    def tier3(*a, **k):
        called['t3'] = True
        return LiveResult(items=[])

    resp = resolve_ai_usage(
        member_email, account_id, dimension, service=None, period=window,
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert called['t2'] is False
    assert called['t3'] is False
    assert resp['providerMetadata']['source'] == 'cache'
    assert table.written == []


# ---------------------------------------------------------------------------
# Property 8 — staleness exact age comparison
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    threshold_hours=st.floats(min_value=1, max_value=240, allow_nan=False, allow_infinity=False),
    delta_seconds=st.integers(min_value=-5000, max_value=5000),
)
def test_property8_staleness_exact_comparison(threshold_hours, delta_seconds):
    """A record is stale iff (now - cached_at) strictly exceeds the threshold.
    The exact-edge case (age == threshold) is NOT stale (Property 8)."""
    now = REF_NOW
    age = timedelta(hours=threshold_hours) + timedelta(seconds=delta_seconds)
    cached_at = (now - age).isoformat()

    expected_stale = age > timedelta(hours=threshold_hours)
    assert is_stale(cached_at, now=now, threshold_hours=threshold_hours) == expected_stale
    assert within_staleness(cached_at, now=now, threshold_hours=threshold_hours) == (not expected_stale)


@settings(max_examples=1, deadline=None)
@given(threshold_hours=st.just(48.0))
def test_property8_exact_edge_is_fresh(threshold_hours):
    """Age exactly equal to the threshold is on the fresh side."""
    now = REF_NOW
    cached_at = (now - timedelta(hours=threshold_hours)).isoformat()
    assert is_stale(cached_at, now=now, threshold_hours=threshold_hours) is False
    assert within_staleness(cached_at, now=now, threshold_hours=threshold_hours) is True


# ---------------------------------------------------------------------------
# Property 9 — Tier-2 trigger predicate = union of five conditions
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    member_email=emails,
    account_id=account_ids,
    window=windows,
    present_mask=st.lists(st.booleans(), min_size=0, max_size=8),
    service=st.one_of(st.none(), st.sampled_from(['gpt-4o', 'gpt-3.5'])),
    stale=st.booleans(),
)
def test_property9_trigger_predicate_union(member_email, account_id, window, present_mask, service, stale):
    """should_trigger_tier2 == (T1 ∨ T2 ∨ T3 ∨ T4 ∨ T5), each computed
    independently (Property 9)."""
    dates = window_dates_inclusive(window['start'], window['end'])
    cached_at = (REF_NOW - timedelta(hours=1000 if stale else 1)).isoformat()

    # Include a rollup for a date iff its mask bit is True.
    rollups = []
    for i, d in enumerate(dates):
        present = present_mask[i] if i < len(present_mask) else False
        if present:
            rollups.append(
                shape_cost_rollup_item(member_email, account_id, d, 1.0, 'USD', cached_at=cached_at)
            )

    covered = {r['sk'].replace('COST#', '') for r in rollups}

    # Independent recomputation of the five conditions.
    t4 = len(rollups) == 0
    t1 = bool(dates) and max(dates) not in covered
    t2 = any(d not in covered for d in dates) if dates else False
    t3 = bool(service)
    t5 = (not t4) and stale  # stale only matters when records exist
    expected = t1 or t2 or t3 or t4 or t5

    reasons = tier2_trigger_reasons(
        rollups, dates, service, now=REF_NOW, threshold_hours=48.0
    )
    assert should_trigger_tier2(rollups, dates, service, now=REF_NOW, threshold_hours=48.0) == expected
    # Each fired reason corresponds to an independently-true condition.
    assert ('T4' in reasons) == t4
    assert ('T1' in reasons) == t1
    assert ('T2' in reasons) == t2
    assert ('T3' in reasons) == t3
    assert ('T5' in reasons) == t5


# ---------------------------------------------------------------------------
# Property 10 — Tier-2 / Tier-3 write-back uses neutral keys
# ---------------------------------------------------------------------------

neutral_usage_items = st.lists(
    st.builds(
        lambda me, aid, day, actor, svc, qty: shape_usage_detail_item(
            'm@x.com', '123456', f'2025-06-{day:02d}', actor, svc,
            usage_quantity=qty, unit=NEUTRAL_USAGE_UNIT, cost_amount=qty / 10.0,
        ),
        st.just('m@x.com'), st.just('123456'),
        st.integers(min_value=1, max_value=28),
        st.sampled_from(['user_a', 'user_b', 'user_c']),
        st.sampled_from(['gpt-4o', 'gpt-3.5']),
        st.integers(min_value=0, max_value=100000),
    ),
    min_size=1, max_size=15,
)


@settings(max_examples=120, deadline=None)
@given(items=neutral_usage_items, via_tier3=st.booleans())
def test_property10_tier2_tier3_writeback_neutral_keys(items, via_tier3):
    """Items retrieved at Tier 2 or Tier 3 are written back under COST#/USAGE#
    keys equivalent to the returned result (Property 10)."""
    table = FakeCacheTable(items=[])  # empty Tier 1 → deeper tiers run

    if via_tier3:
        def tier2(*a, **k):
            return DrilldownResult(satisfied=False)

        def tier3(me, aid, dim, svc, period, connector=None, now=None):
            return LiveResult(items=items, partial=False)
    else:
        def tier2(me, aid, svc, period):
            return DrilldownResult(satisfied=True, items=items)

        tier3 = None

    resolve_ai_usage(
        'm@x.com', '123456', 'actor', service=None,
        period={'start': '2025-06-01', 'end': '2025-06-28'},
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert table.written, "expected write-back of retrieved items"
    for w in table.written:
        assert str(w['sk']).startswith(('COST#', 'USAGE#'))
    # Every produced item was written.
    assert table.written == items


# ---------------------------------------------------------------------------
# Property 15 — response capped to highest-cost entries
# ---------------------------------------------------------------------------

@settings(max_examples=200, deadline=None)
@given(
    costs=st.lists(
        st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
        min_size=0, max_size=60,
    ),
    max_entries=st.integers(min_value=1, max_value=25),
)
def test_property15_response_capped_to_highest_cost(costs, max_entries):
    """The built response keeps at most ``max_entries`` usage rows, the
    highest-cost ones in descending order, with truncated set iff dropped
    (Property 15)."""
    usage = [
        shape_usage_detail_item(
            'm@x.com', '123456', '2025-06-01', f'user_{i}', 'gpt-4o',
            usage_quantity=1, unit=NEUTRAL_USAGE_UNIT, cost_amount=c,
        )
        for i, c in enumerate(costs)
    ]
    resp = build_ai_usage_response(
        'cost', {'start': '2025-06-01', 'end': '2025-06-01'},
        [], usage, source='cache', max_entries=max_entries,
    )

    out = resp['usage']
    assert len(out) <= max_entries
    assert resp['truncated'] == (len(usage) > max_entries)

    out_costs = [float(u['cost_amount']) for u in out]
    # Descending cost order.
    assert out_costs == sorted(out_costs, reverse=True)
    # The kept entries are the top-N by cost.
    assert sorted(out_costs, reverse=True) == sorted(costs, reverse=True)[:max_entries]


# ---------------------------------------------------------------------------
# Property 16 — Tier 3 bounded; degrades to best lower-tier result
# ---------------------------------------------------------------------------

class _SlowConnector:
    def __init__(self, sleep_seconds):
        self.sleep_seconds = sleep_seconds

    def get_ai_usage(self, account_id, member_email, params):
        time.sleep(self.sleep_seconds)
        return {'rollups': [], 'usage': []}


@settings(max_examples=60, deadline=None)
@given(timeout=st.floats(min_value=0.02, max_value=0.1))
def test_property16_tier3_bounded_degrades(timeout):
    """A Tier-3 call that overruns the latency bound returns within the bound
    with no new items and partial=True (Property 16)."""
    connector = _SlowConnector(sleep_seconds=timeout + 0.5)
    start = time.monotonic()
    result = _default_tier3_call(
        'm@x.com', '123456', 'cost', None,
        {'start': '2025-06-01', 'end': '2025-06-02'},
        connector=connector, now=REF_NOW, timeout=timeout,
    )
    elapsed = time.monotonic() - start

    assert result.partial is True
    assert result.items == []
    # Returned within a small multiple of the bound (not the full sleep).
    assert elapsed < timeout + 0.4


@settings(max_examples=50, deadline=None)
@given(member_email=emails, account_id=account_ids)
def test_property16_resolver_marks_live_partial(member_email, account_id):
    """When Tier 3 degrades (partial), the resolver returns the best lower-tier
    result and marks the response live_partial (Property 16, Req 12.4)."""
    # Tier-1 has one stale day so Tier 2/3 are triggered but lower-tier data
    # is still surfaced.
    stale_at = (REF_NOW - timedelta(hours=1000)).isoformat()
    rollup = shape_cost_rollup_item(member_email, account_id, '2025-06-01', 5.0, 'USD', cached_at=stale_at)
    table = FakeCacheTable(items=[rollup])

    def tier2(*a, **k):
        return DrilldownResult(satisfied=False)

    def tier3(*a, **k):
        return LiveResult(items=[], partial=True)

    resp = resolve_ai_usage(
        member_email, account_id, 'cost', service=None,
        period={'start': '2025-06-01', 'end': '2025-06-01'},
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )
    assert resp['providerMetadata']['live_partial'] is True
    assert resp['providerMetadata']['source'] == 'live'
    # Best lower-tier rollup is still present.
    assert any(r['sk'] == 'COST#2025-06-01' for r in resp['rollups'])
