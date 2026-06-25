"""Property + example tests for the AI dashboard data path on the neutral cache.

Feature: vendor-agnostic-ai-usage

Covers:
  Property 17 — Dashboard data path reads only neutral keys (COST#/USAGE#),
                never OPENAI_DAILY#; the per-user token graph reads
                Usage_Detail_Item records by actor/service.
                (Validates Requirements 9.7, 13.1, 13.2, 13.5)
  Property 18 — Dashboard refresh (_refresh_cost_cache_for_account) writes the
                neutral schema and stays customer-scoped / single-account.
                (Validates Requirements 13.3, 13.6, 11.4, 11.5)
  Example     — handle_openai_usage exposes the neutral cost-summary, per-model,
                and per-user token-graph fields consumed by members.js.
                (Validates Requirement 13.7)

DynamoDB / KMS / HTTP are all mocked — no live calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import lambda_function
import incremental_fetch_engine
from cache_service import (
    shape_cost_rollup_item,
    shape_usage_detail_item,
    build_neutral_partition_key,
    NEUTRAL_USAGE_UNIT,
)


# ---------------------------------------------------------------------------
# Fake cache table (mocks DynamoDB). Logs the sort-key BETWEEN bounds of every
# query so we can assert which key families the dashboard touches.
# ---------------------------------------------------------------------------

class LoggingCacheTable:
    def __init__(self, items=None, query_log=None):
        self.items = list(items or [])
        self.written = []
        self.query_log = query_log if query_log is not None else []

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
        pk, low, high = self._extract(KeyConditionExpression)
        self.query_log.append({'pk': pk, 'low': low, 'high': high})
        matched = [
            it for it in self.items
            if it.get('pk') == pk and low is not None
            and low <= str(it.get('sk', '')) <= high
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


class FakeAccountsTable:
    def __init__(self, account):
        self._account = account

    def get_item(self, Key=None, **kwargs):
        return {'Item': self._account}


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

emails = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=8),
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=6),
)
account_ids = st.builds(lambda n: f"openai-{n}",
                        st.text(alphabet='abcdef0123456789', min_size=4, max_size=10))
actors = st.text(alphabet='abcdefghijklmnopqrstuvwxyz_-0123456789', min_size=1, max_size=8)
services = st.sampled_from(['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'o1', 'text-embedding-3'])
costs = st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False)
token_counts = st.integers(min_value=0, max_value=5_000_000)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _window_dates(date_range):
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    end = now.strftime('%Y-%m-%d')
    start = (now - timedelta(days=date_range)).strftime('%Y-%m-%d')
    return start, end


# ---------------------------------------------------------------------------
# Property 17 — dashboard reads only neutral keys (COST#/USAGE#)
# Feature: vendor-agnostic-ai-usage, Property 17
# ---------------------------------------------------------------------------

@settings(max_examples=120, deadline=None)
@given(
    member_email=emails,
    account_id=account_ids,
    actor=actors,
    service=services,
    cost=costs,
    tokens=token_counts,
    legacy_count=st.integers(min_value=0, max_value=4),
)
def test_property17_dashboard_reads_only_neutral_keys(
    member_email, account_id, actor, service, cost, tokens, legacy_count
):
    """For any neutral/legacy cache mix, the AI dashboard data path queries the
    Cost_Cache_Table using only COST#/USAGE# sort-key prefixes (the per-user
    graph reading Usage_Detail_Item by actor/service) and never OPENAI_DAILY#.
    """
    date_range = 30
    start, end = _window_dates(date_range)
    pk = build_neutral_partition_key(member_email, account_id)
    fresh = _now_iso()

    # A neutral/legacy mix: a fresh COST# rollup (prevents a resolver refresh so
    # only Tier-1 neutral reads run), a USAGE# detail record, and OPENAI_DAILY#
    # legacy noise that must never be read.
    items = [
        shape_cost_rollup_item(member_email, account_id, end, cost, 'USD', fresh),
        shape_usage_detail_item(member_email, account_id, end, actor, service,
                                usage_quantity=tokens, unit=NEUTRAL_USAGE_UNIT,
                                cost_amount=cost, cached_at=fresh),
    ]
    for i in range(legacy_count):
        items.append({
            'pk': pk, 'sk': f'OPENAI_DAILY#{end}',
            'cost_amount': str(cost), 'cached_at': fresh,
        })

    query_log = []
    cache_table = LoggingCacheTable(items=items, query_log=query_log)
    account = {'cloudProvider': 'openai', 'credentials': {'encryptedApiKey': 'x'}}
    accounts_table = FakeAccountsTable(account)

    def _table_dispatch(name):
        if name == lambda_function.COST_CACHE_TABLE_NAME:
            return cache_table
        return accounts_table

    event = {'body': json.dumps({'accountId': account_id, 'dateRange': date_range})}

    with patch.object(lambda_function, 'validate_token', return_value={'sub': member_email}), \
         patch.object(lambda_function, '_verify_account_ownership', return_value=True), \
         patch.object(lambda_function.dynamodb, 'Table', side_effect=_table_dispatch), \
         patch.object(lambda_function, '_get_ai_usage_connector', return_value=None):
        resp = lambda_function.handle_openai_usage(event)

    assert resp['statusCode'] == 200

    # Every cache query must target COST# or USAGE# bounds — never OPENAI_DAILY#.
    assert query_log, "dashboard issued no cache reads"
    prefixes = set()
    for q in query_log:
        low, high = str(q['low']), str(q['high'])
        assert 'OPENAI_DAILY#' not in low and 'OPENAI_DAILY#' not in high, \
            f"dashboard read an OPENAI_DAILY# key: {q}"
        assert low.startswith(('COST#', 'USAGE#')), f"non-neutral read bound: {q}"
        prefixes.add(low.split('#', 1)[0] + '#')

    # Both the cost rollup family and the per-user/per-service usage family read.
    assert 'COST#' in prefixes
    assert 'USAGE#' in prefixes


# ---------------------------------------------------------------------------
# Property 18 — dashboard refresh writes neutral schema, customer-scoped single
# account.  Feature: vendor-agnostic-ai-usage, Property 18
# ---------------------------------------------------------------------------

_COST_SK = re.compile(r'^COST#\d{4}-\d{2}-\d{2}$')
_USAGE_SK = re.compile(r'^USAGE#\d{4}-\d{2}-\d{2}#.*#.*$')


@settings(max_examples=120, deadline=None)
@given(
    member_email=emails,
    account_id=account_ids,
    rollup_specs=st.lists(
        st.tuples(st.dates(), costs), min_size=0, max_size=6
    ),
    usage_specs=st.lists(
        st.tuples(st.dates(), actors, services, token_counts, costs),
        min_size=0, max_size=8,
    ),
)
def test_property18_refresh_writes_neutral_single_account(
    member_email, account_id, rollup_specs, usage_specs
):
    """Every item written by _refresh_cost_cache_for_account matches the neutral
    COST#/USAGE# schema, the partition key is the single (memberEmail,
    accountId) pair, and retrieval resolves exactly one account."""
    pk = build_neutral_partition_key(member_email, account_id)
    cached_at = _now_iso()

    resolved_rollups = [
        shape_cost_rollup_item(member_email, account_id, d.strftime('%Y-%m-%d'),
                               c, 'USD', cached_at)
        for d, c in rollup_specs
    ]
    resolved_usage = [
        shape_usage_detail_item(member_email, account_id, d.strftime('%Y-%m-%d'),
                                actor, svc, usage_quantity=tok,
                                unit=NEUTRAL_USAGE_UNIT, cost_amount=c,
                                cached_at=cached_at)
        for d, actor, svc, tok, c in usage_specs
    ]
    resolved = {'rollups': resolved_rollups, 'usage': resolved_usage}

    cache_table = LoggingCacheTable()
    captured = {}

    def _fake_resolve(me, aid, dim, **kwargs):
        captured['args'] = (me, aid, dim)
        captured['kwargs'] = kwargs
        return resolved

    with patch.object(lambda_function, '_get_account_provider', return_value='openai'), \
         patch.object(lambda_function, '_get_ai_usage_connector', return_value=None), \
         patch.object(incremental_fetch_engine, 'resolve_ai_usage', side_effect=_fake_resolve), \
         patch.object(lambda_function.dynamodb, 'Table', return_value=cache_table):
        lambda_function._refresh_cost_cache_for_account(member_email, account_id)

    # Customer-scoped, single account: the resolver was asked for exactly this
    # (memberEmail, accountId) pair and nothing else.
    assert captured['args'][0] == member_email
    assert captured['args'][1] == account_id

    # Every written item is neutral schema, scoped to the single pk, never legacy.
    for item in cache_table.written:
        assert item['pk'] == pk, "write escaped the single-account partition"
        sk = str(item['sk'])
        assert 'OPENAI_DAILY#' not in sk
        assert _COST_SK.match(sk) or _USAGE_SK.match(sk), f"non-neutral sk written: {sk}"

    # All resolved items were persisted.
    assert len(cache_table.written) == len(resolved_rollups) + len(resolved_usage)


# ---------------------------------------------------------------------------
# Example — handle_openai_usage exposes the members.js neutral payload contract.
# Feature: vendor-agnostic-ai-usage, Task 9.7  (Req 13.7)
# ---------------------------------------------------------------------------

def test_dashboard_payload_exposes_neutral_members_js_fields():
    """The handle_openai_usage payload exposes the neutral cost-summary,
    per-model, and per-user token-graph fields consumed by members.js."""
    member_email = 'user@example.com'
    account_id = 'openai-acct-1'
    date_range = 30
    start, end = _window_dates(date_range)
    fresh = _now_iso()

    items = [
        shape_cost_rollup_item(member_email, account_id, end, 12.50, 'USD', fresh),
        shape_usage_detail_item(member_email, account_id, end, 'alice', 'gpt-4o',
                                usage_quantity=1000, unit=NEUTRAL_USAGE_UNIT,
                                cost_amount=8.00, cached_at=fresh),
        shape_usage_detail_item(member_email, account_id, end, 'bob', 'gpt-4o-mini',
                                usage_quantity=500, unit=NEUTRAL_USAGE_UNIT,
                                cost_amount=4.50, cached_at=fresh),
    ]
    cache_table = LoggingCacheTable(items=items)
    account = {'cloudProvider': 'openai', 'credentials': {'encryptedApiKey': 'x'}}
    accounts_table = FakeAccountsTable(account)

    def _table_dispatch(name):
        if name == lambda_function.COST_CACHE_TABLE_NAME:
            return cache_table
        return accounts_table

    event = {'body': json.dumps({'accountId': account_id, 'dateRange': date_range})}

    with patch.object(lambda_function, 'validate_token', return_value={'sub': member_email}), \
         patch.object(lambda_function, '_verify_account_ownership', return_value=True), \
         patch.object(lambda_function.dynamodb, 'Table', side_effect=_table_dispatch), \
         patch.object(lambda_function, '_get_ai_usage_connector', return_value=None):
        resp = lambda_function.handle_openai_usage(event)

    assert resp['statusCode'] == 200
    payload = json.loads(resp['body'])

    # Neutral payload arrays present.
    assert isinstance(payload.get('rollups'), list)
    assert isinstance(payload.get('usage'), list)

    # Cost summary.
    assert payload['total_spend'] == 12.5

    # Spend trends derived from COST# rollups.
    assert any(t.get('date') == end and abs(t.get('cost', 0) - 12.5) < 1e-6
               for t in payload['spend_trends'])

    # Per-model breakdown derived from USAGE# detail.
    models = {m['model']: m['cost'] for m in payload['cost_by_model']}
    assert models.get('gpt-4o') == 8.0
    assert models.get('gpt-4o-mini') == 4.5

    # Per-user token graph source (grouped by actor) consumed by members.js.
    by_actor = {r['user_id']: r for r in payload['per_user_daily']}
    assert by_actor['alice']['input_tokens'] == 1000
    assert by_actor['bob']['input_tokens'] == 500
    # token_usage mirrors the per-user records for the token chart.
    assert isinstance(payload.get('token_usage'), list) and payload['token_usage']
