"""Property + unit tests for the vendor-agnostic AI usage intent gate.

Feature: vendor-agnostic-ai-usage

Covers:
  Property 12 — Intent gate routes AI-cost questions to the neutral path and
                others unchanged.
                (Validates Requirements 8.1, 8.3)
  Property 14 — Post-cutover reads use only neutral keys (never OPENAI_DAILY#).
                (Validates Requirements 9.6)
  Unit (7.4)  — _answer_openai_query is not invoked on the neutral ai_vendor
                path.
                (Validates Requirements 8.2)

DynamoDB / KMS / HTTP are all mocked — no live calls.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import lambda_function
from lambda_function import (
    is_ai_cost_or_usage_question,
    should_route_to_neutral_ai_usage,
    _ai_usage_dimension_from_question,
    resolve_ai_usage_response,
)
import incremental_fetch_engine
from incremental_fetch_engine import (
    resolve_ai_usage,
    DrilldownResult,
    LiveResult,
)
from cache_service import (
    shape_cost_rollup_item,
    window_dates_inclusive,
)
from cache_service import COST_ROLLUP_SK_PREFIX, USAGE_DETAIL_SK_PREFIX


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Phrases that always contain an AI cost/usage keyword (classifier -> True).
_COST_KEYWORD_TEMPLATES = [
    "What is my {kw} this month?",
    "Show me the {kw} for last month",
    "Give me a {kw} report",
    "How is my {kw} trending?",
]
_COST_KEYWORDS = [
    'cost', 'spend', 'spending', 'tokens', 'token usage', 'usage',
    'per-user', 'per user', 'by model', 'breakdown', 'budget', 'forecast',
    'how much', 'billing',
]

# Phrases that contain NO AI cost/usage keyword (classifier -> False).
_NON_COST_QUESTIONS = [
    "hello there",
    "what region am I in",
    "show me the dashboard layout",
    "rename this account please",
    "is my connection healthy",
    "good morning",
    "open the configure tab",
    "what time is it",
]

vendor_types = st.sampled_from(['ai_vendor', 'cloud_provider'])


@st.composite
def _cost_questions(draw):
    tmpl = draw(st.sampled_from(_COST_KEYWORD_TEMPLATES))
    kw = draw(st.sampled_from(_COST_KEYWORDS))
    return tmpl.format(kw=kw)


cost_questions = _cost_questions()
non_cost_questions = st.sampled_from(_NON_COST_QUESTIONS)


# ---------------------------------------------------------------------------
# Property 12 — intent gate routes AI-cost questions to neutral path; others
# unchanged.  Feature: vendor-agnostic-ai-usage, Property 12.
# ---------------------------------------------------------------------------

@settings(max_examples=150, deadline=None)
@given(question=cost_questions, vendor_type=vendor_types)
def test_property12_cost_question_routes_neutral_only_for_ai_vendor(question, vendor_type):
    """A question on an ai_vendor connection routes to the neutral path; a
    cloud_provider account routes unchanged (Property 12).

    Routing is keyword-free and depends only on the data-driven vendorType, so
    AI-vendor questions are never bounced to the static redirect (no hardcoded
    model/vendor strings gate the decision).

    **Validates: Requirements 8.1, 8.3**
    """
    routed = should_route_to_neutral_ai_usage(question, vendor_type)
    assert routed is (vendor_type == 'ai_vendor')


@settings(max_examples=150, deadline=None)
@given(question=non_cost_questions, vendor_type=vendor_types)
def test_property12_routing_independent_of_keywords(question, vendor_type):
    """Questions with NO AI-cost keyword still route to the neutral path when
    the account is an ai_vendor (the dedicated single-vendor connection answers
    every question via the AI-in-the-loop resolver), and route unchanged for
    cloud_provider accounts (Property 12).

    This is the regression guard for the prior bug where model-specific phrasings
    fell through to a generic redirect with no answer and no audit.

    **Validates: Requirements 8.1, 8.3**
    """
    assert should_route_to_neutral_ai_usage(question, vendor_type) is (vendor_type == 'ai_vendor')


@settings(max_examples=200, deadline=None)
@given(
    question=st.one_of(cost_questions, non_cost_questions),
    vendor_type=vendor_types,
)
def test_property12_routing_is_exactly_ai_vendor(question, vendor_type):
    """For any question/vendor, routing to the neutral path holds iff the account
    is an ai_vendor — independent of question wording (Property 12).

    **Validates: Requirements 8.1, 8.3**
    """
    assert should_route_to_neutral_ai_usage(question, vendor_type) is (vendor_type == 'ai_vendor')


# ---------------------------------------------------------------------------
# Property 14 — post-cutover reads use only neutral keys.
# Feature: vendor-agnostic-ai-usage, Property 14.
# ---------------------------------------------------------------------------

class _SortKeyLoggingTable:
    """Fake DynamoDB table that records the sort-key prefixes it is queried
    with so we can assert reads never use OPENAI_DAILY#."""

    def __init__(self, items=None, sk_log=None):
        self.items = list(items or [])
        self.sk_log = sk_log if sk_log is not None else []

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
        # Record the sort-key bounds for the post-cutover key assertion.
        self.sk_log.append(str(low))
        self.sk_log.append(str(high))
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
                outer.items.append(Item)

        return _BW()


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
    start = draw(st.integers(min_value=0, max_value=10))
    length = draw(st.integers(min_value=0, max_value=5))
    end_dt = REF_NOW - timedelta(days=start)
    start_dt = end_dt - timedelta(days=length)
    return {'start': start_dt.strftime('%Y-%m-%d'), 'end': end_dt.strftime('%Y-%m-%d')}


windows = _windows()


@settings(max_examples=150, deadline=None)
@given(
    member_email=emails,
    account_id=account_ids,
    dimension=dimensions,
    window=windows,
    populate=st.booleans(),
)
def test_property14_reads_use_only_neutral_keys(member_email, account_id, dimension, window, populate):
    """Every cache read issued by the AI usage resolver uses only COST#/USAGE#
    sort-key prefixes and never OPENAI_DAILY# (Property 14).

    **Validates: Requirements 9.6**
    """
    sk_log = []
    items = []
    if populate:
        # Fresh, fully covered cache (short-circuit branch still reads Tier 1).
        for d in window_dates_inclusive(window['start'], window['end']):
            items.append(
                shape_cost_rollup_item(
                    member_email, account_id, d, 5.0, 'USD',
                    cached_at=REF_NOW.isoformat(),
                )
            )
    table = _SortKeyLoggingTable(items=items, sk_log=sk_log)

    # Tier 2 / Tier 3 are stubbed so they do not issue their own reads — we are
    # asserting on the resolver's own Tier-1 read keys.
    def tier2(*a, **k):
        return DrilldownResult(satisfied=False)

    def tier3(*a, **k):
        return LiveResult(items=[], partial=False)

    resolve_ai_usage(
        member_email, account_id, dimension, service=None, period=window,
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert sk_log, "expected at least one Tier-1 cache read"
    for sk in sk_log:
        assert 'OPENAI_DAILY#' not in sk, f"post-cutover read used legacy key: {sk}"
        assert sk.startswith((COST_ROLLUP_SK_PREFIX, USAGE_DETAIL_SK_PREFIX)), (
            f"read used a non-neutral sort key: {sk}"
        )


# ---------------------------------------------------------------------------
# Unit (7.4) — _answer_openai_query is not invoked on the neutral path.
# Validates: Requirements 8.2
# ---------------------------------------------------------------------------

def test_neutral_path_does_not_invoke_answer_openai_query():
    """resolve_ai_usage_response resolves through the neutral resolver and never
    calls the legacy _answer_openai_query short-circuit (Req 8.2)."""
    fake_resolved = {
        'dimension': 'cost',
        'period': {'start': '2025-06-01', 'end': '2025-06-30'},
        'currency': 'USD',
        'rollups': [{'date': '2025-06-01', 'cost_amount': '12.34', 'currency': 'USD'}],
        'usage': [{'date': '2025-06-01', 'actor': None, 'service': 'gpt-4o',
                   'usage_quantity': '1000', 'unit': 'tokens', 'cost_amount': '12.34'}],
        'truncated': False,
        'providerMetadata': {'provider': 'openai', 'source': 'cache', 'live_partial': False},
    }

    with patch.object(incremental_fetch_engine, 'resolve_ai_usage',
                      return_value=fake_resolved) as mock_resolve, \
         patch.object(lambda_function, '_get_account_provider', return_value='openai'), \
         patch.object(lambda_function, '_ai_usage_llm_answer',
                      side_effect=lambda q, r, baseline: baseline), \
         patch.object(lambda_function, '_inline_audit_score',
                      return_value={'score': 100, 'can_improve': False,
                                    'improvement': '', 'guiding_questions': []}), \
         patch.object(lambda_function, '_answer_openai_query') as mock_legacy:
        resp = resolve_ai_usage_response(
            'user@example.com', 'openai-acct-1', 'What is my AI cost this month?', 'iid-1'
        )

    # The neutral resolver was used …
    assert mock_resolve.called
    # … and the legacy OpenAI short-circuit was never invoked (Req 8.2).
    mock_legacy.assert_not_called()
    assert resp['statusCode'] == 200


def test_neutral_path_answers_cost_tokens_and_per_user_questions():
    """The neutral answer addresses cost, token/unit, AND per-user questions —
    not just a per-model cost table (the prior bug)."""
    usage = [
        {'date': '2025-06-01', 'actor': 'user_a', 'service': 'gpt-4o',
         'usage_quantity': '1000', 'unit': 'tokens', 'cost_amount': None},
        {'date': '2025-06-01', 'actor': 'user_b', 'service': 'gpt-4o',
         'usage_quantity': '500', 'unit': 'tokens', 'cost_amount': None},
    ]
    rollups = [{'date': '2025-06-01', 'cost_amount': '9.99', 'currency': 'USD'}]

    def _resolved(dimension):
        return {
            'dimension': dimension,
            'period': {'start': '2025-06-01', 'end': '2025-06-30'},
            'currency': 'USD',
            'rollups': rollups,
            'usage': usage if dimension == 'actor' else [
                {'date': '2025-06-01', 'actor': None, 'service': 'gpt-4o',
                 'usage_quantity': '1500', 'unit': 'tokens', 'cost_amount': '9.99'}
            ],
            'truncated': False,
            'providerMetadata': {'provider': 'openai', 'source': 'cache', 'live_partial': False},
        }

    # Per-user question -> actor dimension -> per-user table.
    with patch.object(incremental_fetch_engine, 'resolve_ai_usage',
                      side_effect=lambda *a, **k: _resolved(a[2])), \
         patch.object(lambda_function, '_get_account_provider', return_value='openai'), \
         patch.object(lambda_function, '_ai_usage_llm_answer',
                      side_effect=lambda q, r, baseline: baseline), \
         patch.object(lambda_function, '_inline_audit_score',
                      return_value={'score': 100, 'can_improve': False,
                                    'improvement': '', 'guiding_questions': []}):
        per_user = resolve_ai_usage_response(
            'u@x.com', 'openai-1', 'Show AI tokens per user', 'iid')
        tokens_q = resolve_ai_usage_response(
            'u@x.com', 'openai-1', 'How many tokens did we use?', 'iid')
        cost_q = resolve_ai_usage_response(
            'u@x.com', 'openai-1', 'What is my AI cost?', 'iid')

    import json
    per_user_ans = json.loads(per_user['body'])['answer']
    tokens_ans = json.loads(tokens_q['body'])['answer']
    cost_ans = json.loads(cost_q['body'])['answer']

    assert 'user_a' in per_user_ans and 'User / actor' in per_user_ans
    assert 'tokens' in tokens_ans.lower()
    assert 'cost' in cost_ans.lower() and '9.99' in cost_ans


def test_dimension_classifier_priority():
    """Per-user > token/units > cost priority for dimension selection."""
    assert _ai_usage_dimension_from_question('tokens per user') == 'actor'
    assert _ai_usage_dimension_from_question('how many tokens') == 'units'
    assert _ai_usage_dimension_from_question('what is my cost') == 'cost'
