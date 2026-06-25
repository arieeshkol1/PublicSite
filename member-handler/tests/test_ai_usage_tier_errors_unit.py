"""Unit tests for Tier-2 credential and Tier-3 admin-key error handling.

Feature: vendor-agnostic-ai-usage, Task 3.13

  - Missing customer credentials at Tier 2 → structured Configure-tab error (Req 6.4)
  - Admin-key gap at Tier 3 → structured "admin-level key" message (Req 12.1)

DynamoDB / KMS / HTTP are mocked — no live calls.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import provider_invoices
from incremental_fetch_engine import (
    resolve_ai_usage,
    _default_tier3_call,
    build_admin_key_required_error,
    build_connection_required_error,
    DrilldownResult,
    LiveResult,
)

REF_NOW = datetime(2025, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _tips_table_with_plan():
    table = MagicMock()
    table.query.return_value = {
        'Items': [{
            'service': 'openai', 'tipId': 'drill-1',
            'drilldownApis': '["/v1/organization/usage/completions"]',
        }]
    }
    return table


# ---------------------------------------------------------------------------
# Tier 2 — missing customer credentials → Configure-tab error (Req 6.4)
# ---------------------------------------------------------------------------

def test_tier2_missing_credentials_returns_configure_tab_error():
    """When the customer connection is not configured, Tier 2 returns the
    structured Configure-tab error and never reaches the connector."""
    def failing_loader(me, aid, provider_key):
        raise RuntimeError("OpenAI credentials are not available for this account.")

    connector = MagicMock()

    result = provider_invoices.tips_drilldown(
        'user@example.com', '123456789012', None,
        {'start': '2025-06-01', 'end': '2025-06-02'},
        provider_key='openai',
        tips_table=_tips_table_with_plan(),
        connector=connector,
        credentials_loader=failing_loader,
    )

    assert isinstance(result, DrilldownResult)
    assert result.satisfied is False
    assert result.error == build_connection_required_error()
    assert result.error['error'] == 'connection_required'
    assert result.error['configureTab'] is True
    assert 'Configure tab' in result.error['message']
    # The customer connection is never invoked when credentials are missing.
    connector.authenticate.assert_not_called()
    connector.fetch_per_user_daily_usage.assert_not_called()


def test_resolver_surfaces_tier2_configure_tab_error():
    """The resolver surfaces the Tier-2 Configure-tab error in the response."""
    # Empty Tier 1 → Tier 2 runs; Tier 2 returns the credential error.
    table = MagicMock()
    table.query.return_value = {'Items': []}

    def tier2(me, aid, svc, period):
        return DrilldownResult(satisfied=False, error=build_connection_required_error())

    def tier3(*a, **k):  # must not be reached on a Tier-2 hard error
        raise AssertionError("Tier 3 should not run after a Tier-2 credential error")

    resp = resolve_ai_usage(
        'user@example.com', '123456789012', 'cost', service=None,
        period={'start': '2025-06-01', 'end': '2025-06-02'},
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert resp['error'] == 'connection_required'
    assert resp['configureTab'] is True
    assert 'Configure tab' in resp['message']


# ---------------------------------------------------------------------------
# Tier 3 — admin-key gap → structured "admin-level key" message (Req 12.1)
# ---------------------------------------------------------------------------

def test_tier3_permission_error_admin_key_message():
    """A live call that fails because the key lacks org-wide (admin) access
    returns the structured admin-key-required message."""
    connector = MagicMock()
    connector.get_ai_usage.side_effect = PermissionError(
        "Account-wide usage requires an admin-level key"
    )

    result = _default_tier3_call(
        'user@example.com', '123456789012', 'cost', None,
        {'start': '2025-06-01', 'end': '2025-06-02'},
        connector=connector, now=REF_NOW, timeout=5,
    )

    assert isinstance(result, LiveResult)
    assert result.items == []
    assert result.error == build_admin_key_required_error()
    assert result.error['error'] == 'admin_key_required'
    assert 'admin-level' in result.error['message']


def test_tier3_error_result_admin_key_message():
    """A live result carrying an admin-key error code maps to the structured
    admin-key-required message."""
    connector = MagicMock()
    connector.get_ai_usage.return_value = {'error': 'admin_key_required', 'message': 'x'}

    result = _default_tier3_call(
        'user@example.com', '123456789012', 'cost', None,
        {'start': '2025-06-01', 'end': '2025-06-02'},
        connector=connector, now=REF_NOW, timeout=5,
    )
    assert result.error == build_admin_key_required_error()


def test_resolver_surfaces_tier3_admin_key_message():
    """The resolver surfaces the Tier-3 admin-key message in the response."""
    table = MagicMock()
    table.query.return_value = {'Items': []}  # empty Tier 1 → deeper tiers run

    def tier2(*a, **k):
        return DrilldownResult(satisfied=False)

    def tier3(*a, **k):
        return LiveResult(items=[], error=build_admin_key_required_error())

    resp = resolve_ai_usage(
        'user@example.com', '123456789012', 'cost', service=None,
        period={'start': '2025-06-01', 'end': '2025-06-02'},
        table=table, now=REF_NOW, tier2_fn=tier2, tier3_fn=tier3,
    )

    assert resp['error'] == 'admin_key_required'
    assert 'admin-level' in resp['message']
