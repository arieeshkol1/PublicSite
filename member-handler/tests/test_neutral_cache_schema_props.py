"""Property-based tests for the vendor-neutral AI cache schema.

Feature: vendor-agnostic-ai-usage, Property 3

Property 3: Cached items conform to the neutral schema and key format.
For any write input, the produced cache items use sort keys of the form
``COST#{date}`` / ``USAGE#{date}#{actor}#{service}`` and carry the full set of
required neutral fields (absent fields present as null, not omitted).

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 6.3
"""
from __future__ import annotations

import os
import re
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import (
    build_cost_rollup_sort_key,
    build_usage_detail_sort_key,
    build_neutral_partition_key,
    shape_cost_rollup_item,
    shape_usage_detail_item,
    NEUTRAL_USAGE_UNIT,
)
from incremental_fetch_engine import IncrementalFetchEngine


# ---------------------------------------------------------------------------
# Key-format expectations
# ---------------------------------------------------------------------------

COST_SK_RE = re.compile(r'^COST#\d{4}-\d{2}-\d{2}$')
USAGE_SK_RE = re.compile(r'^USAGE#\d{4}-\d{2}-\d{2}#[^#]+#[^#]+$')

COST_ROLLUP_REQUIRED = {'pk', 'sk', 'cost_amount', 'currency', 'cached_at'}
USAGE_DETAIL_REQUIRED = {
    'pk', 'sk', 'usage_quantity', 'unit', 'cost_amount', 'actor', 'service', 'cached_at',
}


# ---------------------------------------------------------------------------
# Generators (constrained to the valid input space)
# ---------------------------------------------------------------------------

# Actor/service tokens must not contain '#' so the sort key remains parseable.
identifier_text = st.text(
    alphabet=st.characters(blacklist_characters='#', min_codepoint=32, max_codepoint=0x017f),
    min_size=1,
    max_size=24,
)

# Lightweight email generator (st.emails() is too slow for input generation).
emails = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789.', min_size=1, max_size=16),
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=12),
)
account_ids = st.text(alphabet='0123456789', min_size=6, max_size=14)
iso_dates = st.dates().map(lambda d: d.isoformat())
amounts = st.one_of(
    st.none(),
    st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=1_000_000),
)
quantities = st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000))
currencies = st.one_of(st.none(), st.sampled_from(['USD', 'EUR', 'GBP', 'usd']))


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    member_email=emails,
    account_id=account_ids,
    date=iso_dates,
    cost_amount=amounts,
    currency=currencies,
)
def test_cost_rollup_item_schema(member_email, account_id, date, cost_amount, currency):
    """Cost_Rollup_Item uses COST#{date} and carries all required fields."""
    item = shape_cost_rollup_item(
        member_email=member_email,
        account_id=account_id,
        date=date,
        cost_amount=cost_amount,
        currency=currency,
    )

    # Sort key format (Req 2.1).
    assert COST_SK_RE.match(item['sk']), item['sk']
    assert item['sk'] == build_cost_rollup_sort_key(date)

    # Partition key shape (Req 2.3).
    assert item['pk'] == build_neutral_partition_key(member_email, account_id)
    assert item['pk'] == f"{member_email}#{account_id}"

    # All required fields present, none omitted (Req 2.3, 2.6).
    assert COST_ROLLUP_REQUIRED.issubset(item.keys())

    # cached_at is always populated.
    assert item['cached_at']

    # Absent numeric source -> null, present -> string.
    if cost_amount is None:
        assert item['cost_amount'] is None
    else:
        assert item['cost_amount'] == str(cost_amount)


@settings(max_examples=200)
@given(
    member_email=emails,
    account_id=account_ids,
    date=iso_dates,
    actor=identifier_text,
    service=identifier_text,
    usage_quantity=quantities,
    cost_amount=amounts,
)
def test_usage_detail_item_schema(
    member_email, account_id, date, actor, service, usage_quantity, cost_amount
):
    """Usage_Detail_Item uses USAGE#{date}#{actor}#{service} with all fields."""
    item = shape_usage_detail_item(
        member_email=member_email,
        account_id=account_id,
        date=date,
        actor=actor,
        service=service,
        usage_quantity=usage_quantity,
        unit=NEUTRAL_USAGE_UNIT,
        cost_amount=cost_amount,
    )

    # Sort key format (Req 2.2).
    assert USAGE_SK_RE.match(item['sk']), item['sk']
    assert item['sk'] == build_usage_detail_sort_key(date, actor, service)
    # The date/actor/service are recoverable from the key.
    assert item['sk'] == f"USAGE#{date}#{actor}#{service}"

    # All required fields present, none omitted (Req 2.4, 2.6).
    assert USAGE_DETAIL_REQUIRED.issubset(item.keys())
    assert item['actor'] == actor
    assert item['service'] == service
    assert item['unit'] == NEUTRAL_USAGE_UNIT
    assert item['cached_at']

    # Absent numeric source -> null, present -> string.
    if usage_quantity is None:
        assert item['usage_quantity'] is None
    else:
        assert item['usage_quantity'] == str(usage_quantity)
    if cost_amount is None:
        assert item['cost_amount'] is None
    else:
        assert item['cost_amount'] == str(cost_amount)


@settings(max_examples=100)
@given(
    member_email=emails,
    account_id=account_ids,
    records=st.lists(
        st.fixed_dictionaries({
            'date': iso_dates,
            'service_name': identifier_text,
            'cost_amount': st.floats(
                min_value=0, max_value=10_000, allow_nan=False, allow_infinity=False
            ),
            'currency': st.sampled_from(['USD', 'EUR']),
            'input_tokens': st.integers(min_value=0, max_value=1_000_000),
            'output_tokens': st.integers(min_value=0, max_value=1_000_000),
            'project_id': st.one_of(st.none(), identifier_text),
        }),
        min_size=0,
        max_size=20,
    ),
)
def test_neutral_items_from_normalized_conform_and_write_to_cache(
    member_email, account_id, records
):
    """cost_normalizer output projects onto conforming neutral items, and the
    write-back path persists exactly those items to the (mocked) cache table."""
    engine = IncrementalFetchEngine()
    items = engine.neutral_items_from_normalized(member_email, account_id, records)

    expected_pk = f"{member_email}#{account_id}"
    for item in items:
        assert item['pk'] == expected_pk
        if item['sk'].startswith('COST#'):
            assert COST_SK_RE.match(item['sk']), item['sk']
            assert COST_ROLLUP_REQUIRED.issubset(item.keys())
        else:
            assert USAGE_SK_RE.match(item['sk']), item['sk']
            assert USAGE_DETAIL_REQUIRED.issubset(item.keys())

    # One rollup per distinct date.
    distinct_dates = {r['date'] for r in records}
    rollups = [i for i in items if i['sk'].startswith('COST#')]
    assert len(rollups) == len(distinct_dates)

    # Write-back persists every neutral item via batch_writer.
    batch = MagicMock()
    table = MagicMock()
    table.batch_writer.return_value.__enter__.return_value = batch
    table.batch_writer.return_value.__exit__.return_value = False

    assert engine.write_neutral_items(table, items) is True
    assert batch.put_item.call_count == len(items)
    written = [call.kwargs['Item'] for call in batch.put_item.call_args_list]
    assert written == items


def test_write_neutral_items_empty_is_noop():
    """Empty write input is a no-op that does not touch the table."""
    engine = IncrementalFetchEngine()
    table = MagicMock()
    assert engine.write_neutral_items(table, []) is True
    table.batch_writer.assert_not_called()
