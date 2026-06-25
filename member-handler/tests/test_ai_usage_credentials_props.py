"""Property-based test for customer-credential, single-account AI retrieval.

Feature: vendor-agnostic-ai-usage, Property 11

Property 11: All AI usage retrieval uses customer credentials for exactly one
account. Every data-retrieval path loads credentials scoped to the single
requested (memberEmail, accountId) pair, never reads platform-owned AI spend,
and resolves exactly one account per invocation.

Validates: Requirements 6.1, 6.2, 11.2, 11.3, 8.4

DynamoDB / KMS / HTTP are mocked — no live calls.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import provider_invoices


emails = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=10),
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8),
)
account_ids = st.text(alphabet='0123456789', min_size=6, max_size=12)
services = st.one_of(st.none(), st.sampled_from(['gpt-4o', 'gpt-3.5']))


def _make_tips_table():
    table = MagicMock()
    table.query.return_value = {
        'Items': [{
            'service': 'openai',
            'tipId': 'drill-1',
            'drilldownApis': '["/v1/organization/usage/completions"]',
            'checkConnection': '/v1/models',
        }]
    }
    return table


@settings(max_examples=150, deadline=None)
@given(member_email=emails, account_id=account_ids, service=services)
def test_property11_customer_credentials_single_account(member_email, account_id, service):
    """Tier-2 retrieval loads credentials for exactly the requested
    (memberEmail, accountId) pair and executes through the customer's
    connection (Property 11)."""
    loader_calls = []

    def fake_loader(me, aid, provider_key):
        loader_calls.append((me, aid, provider_key))
        return {'encrypted_api_key': 'enc', 'member_email': me, 'account_id': aid}

    fetch_calls = []
    connector = MagicMock()
    connector.authenticate.return_value = {'api_key': 'sk-test', 'org_name': 'org_1'}

    def fake_fetch(api_key, organization_id, start_date, end_date):
        fetch_calls.append((api_key, organization_id))
        return [
            {'date': '2025-06-01', 'user_id': 'user_a', 'model': service or 'gpt-4o',
             'input_tokens': 100, 'output_tokens': 50, 'api_key_id': 'k1'},
        ]

    connector.fetch_per_user_daily_usage.side_effect = fake_fetch

    result = provider_invoices.tips_drilldown(
        member_email, account_id, service,
        {'start': '2025-06-01', 'end': '2025-06-02'},
        provider_key='openai',
        tips_table=_make_tips_table(),
        connector=connector,
        credentials_loader=fake_loader,
    )

    # Credentials loaded exactly once for exactly the requested single pair.
    assert loader_calls == [(member_email, account_id, 'openai')]
    # Retrieval executed through the customer's connection.
    assert len(fetch_calls) == 1
    # Every produced item belongs to the single (memberEmail, accountId) pk.
    expected_pk = f"{member_email}#{account_id}"
    for item in result.items:
        assert item['pk'] == expected_pk
    # When a service scope is set, only matching-service detail is produced.
    if service:
        assert all(i['service'] == service for i in result.items)
