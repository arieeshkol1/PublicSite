"""Property-based tests for the OPENAI_DAILY# -> neutral migration.

Feature: vendor-agnostic-ai-usage, Property 13

Property 13: Migration preserves data and is idempotent.
Running the migration twice over a generated set of legacy ``OPENAI_DAILY#``
items leaves the cache table in an identical state, and the produced
``COST#``/``USAGE#`` records preserve cost amount, currency, and date and carry
per-actor/per-service detail sufficient to render the AI dashboard widgets.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.8
"""
from __future__ import annotations

import os
import re
import sys
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# member-handler (cache_service) and infrastructure (migrate_openai_daily).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'infrastructure'))

import migrate_openai_daily as mig  # noqa: E402


COST_SK_RE = re.compile(r'^COST#\d{4}-\d{2}-\d{2}$')
USAGE_SK_RE = re.compile(r'^USAGE#\d{4}-\d{2}-\d{2}#[^#]+#[^#]+$')


# ---------------------------------------------------------------------------
# In-memory DynamoDB stand-in (mock).
# ---------------------------------------------------------------------------

class FakeTable:
    """Minimal DynamoDB Table stand-in keyed by (pk, sk).

    ``scan`` honors the legacy prefix filter the same way ``begins_with`` would
    so neutral records written by a prior run are never re-scanned — exactly the
    property that makes re-runs idempotent.
    """

    def __init__(self):
        self.store: dict = {}

    def put_item(self, Item):  # noqa: N803 (boto3 kwarg name)
        self.store[(Item['pk'], Item['sk'])] = dict(Item)

    def scan(self, FilterExpression=None, ExclusiveStartKey=None):  # noqa: N803
        items = [
            dict(v) for (pk, sk), v in self.store.items()
            if str(sk).startswith(mig.LEGACY_SK_PREFIX)
        ]
        return {'Items': items}

    def snapshot(self):
        return {k: dict(v) for k, v in self.store.items()}


# ---------------------------------------------------------------------------
# Generators — build a legacy item from a ground-truth (actor, service) grid so
# the per-service and per-actor margins are internally consistent (both sum to
# the daily total, as in real OpenAI sync data).
# ---------------------------------------------------------------------------

token_text = st.text(
    alphabet=st.characters(blacklist_characters='#', min_codepoint=97, max_codepoint=122),
    min_size=1, max_size=8,
)
services = st.sampled_from(['gpt-4o', 'gpt-3.5', 'gpt-4', 'o1', 'text-embedding'])
actors = st.sampled_from(['projA', 'projB', 'projC', 'projD'])
iso_dates = st.dates(min_value=__import__('datetime').date(2024, 1, 1),
                     max_value=__import__('datetime').date(2025, 12, 31)).map(lambda d: d.isoformat())


@st.composite
def legacy_item(draw, pk):
    """Generate one legacy OPENAI_DAILY# item with consistent breakdowns."""
    date = draw(iso_dates)
    has_projects = draw(st.booleans())

    svc_set = draw(st.lists(services, min_size=1, max_size=4, unique=True))
    actor_set = draw(st.lists(actors, min_size=1, max_size=3, unique=True)) if has_projects else []

    service_breakdown = {}
    token_breakdown = {}
    project_cost = {}
    total_cost = 0.0

    for svc in svc_set:
        svc_cost = 0.0
        in_tok = 0
        out_tok = 0
        if actor_set:
            for actor in actor_set:
                cell_cost = draw(st.floats(min_value=0.5, max_value=500,
                                           allow_nan=False, allow_infinity=False))
                cell_in = draw(st.integers(min_value=0, max_value=100_000))
                cell_out = draw(st.integers(min_value=0, max_value=100_000))
                svc_cost += cell_cost
                in_tok += cell_in
                out_tok += cell_out
                project_cost[actor] = project_cost.get(actor, 0.0) + cell_cost
        else:
            svc_cost = draw(st.floats(min_value=0.5, max_value=500,
                                      allow_nan=False, allow_infinity=False))
            in_tok = draw(st.integers(min_value=0, max_value=100_000))
            out_tok = draw(st.integers(min_value=0, max_value=100_000))

        service_breakdown[svc] = Decimal(str(round(svc_cost, 4)))
        token_breakdown[svc] = {'input_tokens': in_tok, 'output_tokens': out_tok}
        total_cost += svc_cost

    item = {
        'pk': pk,
        'sk': f"{mig.LEGACY_SK_PREFIX}{date}",
        'cost_amount': Decimal(str(round(total_cost, 4))),
        'currency': 'USD',
        'service_breakdown': service_breakdown,
        'token_breakdown': token_breakdown,
        'fetched_at': '2025-06-02T03:00:00+00:00',
    }
    if project_cost:
        item['project_breakdown'] = {
            a: {'cost': Decimal(str(round(c, 4))), 'name': a}
            for a, c in project_cost.items()
        }
    return item


@st.composite
def legacy_item_sets(draw):
    """Generate a set of legacy items on distinct dates for one account."""
    pk = 'user@example.com#acct-123'
    n = draw(st.integers(min_value=1, max_value=6))
    items = {}
    while len(items) < n:
        it = draw(legacy_item(pk))
        items[it['sk']] = it  # de-dupe by date
    return list(items.values())


def _seed(table, legacy_items):
    for it in legacy_items:
        table.store[(it['pk'], it['sk'])] = dict(it)


# ---------------------------------------------------------------------------
# Property 13 — idempotency.
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(legacy_items=legacy_item_sets())
def test_property13_migration_is_idempotent(legacy_items):
    """Running the migration twice yields an identical cache state (Req 9.4)."""
    table = FakeTable()
    _seed(table, legacy_items)

    assert mig.migrate(table) == 0
    after_first = table.snapshot()

    assert mig.migrate(table) == 0
    after_second = table.snapshot()

    assert after_first == after_second


# ---------------------------------------------------------------------------
# Property 13 — data preservation (cost amount, currency, date) + Req 9.1/9.3.
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(legacy_items=legacy_item_sets())
def test_property13_rollups_preserve_cost_currency_date(legacy_items):
    """Every legacy day yields a COST#{date} rollup preserving cost/currency/date."""
    table = FakeTable()
    _seed(table, legacy_items)
    assert mig.migrate(table) == 0

    for legacy in legacy_items:
        date = legacy['sk'].replace(mig.LEGACY_SK_PREFIX, '')
        key = (legacy['pk'], f"COST#{date}")
        assert key in table.store, f"missing rollup for {date}"
        rollup = table.store[key]
        assert COST_SK_RE.match(rollup['sk'])
        # Cost amount and currency preserved exactly (Req 9.3).
        assert rollup['cost_amount'] == str(legacy['cost_amount'])
        assert rollup['currency'] == legacy['currency']


# ---------------------------------------------------------------------------
# Property 13 — per-service / per-actor detail margins preserved (Req 9.2, 9.8).
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(legacy_items=legacy_item_sets())
def test_property13_detail_sufficient_for_widgets(legacy_items):
    """USAGE# detail preserves per-model and per-actor margins so the per-model
    cost breakdown and per-user token graph widgets can be rendered (Req 9.8)."""
    table = FakeTable()
    _seed(table, legacy_items)
    assert mig.migrate(table) == 0

    for legacy in legacy_items:
        date = legacy['sk'].replace(mig.LEGACY_SK_PREFIX, '')
        usage = [
            v for (pk, sk), v in table.store.items()
            if pk == legacy['pk'] and str(sk).startswith(f"USAGE#{date}#")
        ]
        for u in usage:
            assert USAGE_SK_RE.match(u['sk'])

        # Per-service (per-model) cost margin preserved — backs the per-model
        # cost breakdown widget.
        svc_cost = {}
        svc_tokens = {}
        for u in usage:
            svc = u['service']
            svc_cost[svc] = svc_cost.get(svc, 0.0) + float(u['cost_amount'])
            svc_tokens[svc] = svc_tokens.get(svc, 0.0) + float(u['usage_quantity'])

        for svc, legacy_cost in legacy['service_breakdown'].items():
            assert svc in svc_cost, f"service {svc} missing from migrated detail"
            assert svc_cost[svc] == pytest.approx(float(legacy_cost), abs=1e-2)
            tok = legacy['token_breakdown'].get(svc, {})
            expected_tokens = int(tok.get('input_tokens', 0)) + int(tok.get('output_tokens', 0))
            assert svc_tokens[svc] == pytest.approx(expected_tokens, abs=1.0)

        # Per-actor cost margin preserved — backs the per-user token graph.
        proj = legacy.get('project_breakdown') or {}
        if proj:
            actor_cost = {}
            for u in usage:
                actor_cost[u['actor']] = actor_cost.get(u['actor'], 0.0) + float(u['cost_amount'])
            for actor, pval in proj.items():
                label = pval['name']
                assert label in actor_cost, f"actor {label} missing from migrated detail"
                assert actor_cost[label] == pytest.approx(float(pval['cost']), abs=1e-2)
