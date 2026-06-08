"""Property-based tests for cache strategy (Property 15).

Property 15: Cache freshness determines retrieval path
Fresh cache → use cached, no API call. Stale/missing → API call + write-back.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock, call

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.behavioral_router import execute_cost_analysis_general, _is_stale
from agent.models import AccountContext, SessionState
from agent.constants import CACHE_STALENESS_THRESHOLD_SECONDS


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def fresh_timestamps():
    """Generate timestamps within the staleness threshold (fresh)."""
    now = datetime.now(timezone.utc)
    return st.builds(
        lambda seconds: (now - timedelta(seconds=seconds)).isoformat(),
        seconds=st.integers(min_value=0, max_value=CACHE_STALENESS_THRESHOLD_SECONDS - 1),
    )


def stale_timestamps():
    """Generate timestamps beyond the staleness threshold (stale)."""
    now = datetime.now(timezone.utc)
    return st.builds(
        lambda seconds: (now - timedelta(seconds=seconds)).isoformat(),
        seconds=st.integers(
            min_value=CACHE_STALENESS_THRESHOLD_SECONDS + 1,
            max_value=CACHE_STALENESS_THRESHOLD_SECONDS * 10,
        ),
    )


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(ts=fresh_timestamps())
def test_property15_fresh_cache_not_stale(ts):
    """Property 15: Fresh cache timestamps are not stale."""
    assert not _is_stale(ts), f"Expected fresh for timestamp {ts}"


@settings(max_examples=100)
@given(ts=stale_timestamps())
def test_property15_stale_cache_is_stale(ts):
    """Property 15: Stale timestamps beyond threshold are detected."""
    assert _is_stale(ts), f"Expected stale for timestamp {ts}"


def test_property15_missing_timestamp_is_stale():
    """Property 15: Missing/empty timestamp is always stale."""
    assert _is_stale("")
    assert _is_stale(None)


@settings(max_examples=100)
@given(
    account_id=st.from_regex(r"\d{12}", fullmatch=True),
    timeframe=st.sampled_from(["last-7d", "last-30d", "last-90d"]),
)
def test_property15_fresh_cache_skips_api(account_id, timeframe):
    """Property 15: Fresh cache → use cached data, no API call."""
    account_context = AccountContext(
        account_id=account_id,
        account_name="Test",
        cloud_provider="aws",
        member_email="test@example.com",
    )
    session = SessionState(active_timeframe=timeframe)

    fresh_time = datetime.now(timezone.utc).isoformat()

    with patch("agent.behavioral_router.boto3") as mock_boto3, \
         patch("agent.behavioral_router.get_connector") as mock_connector:

        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_boto3.resource.return_value = mock_resource
        mock_resource.Table.return_value = mock_table

        # Return fresh cached data
        mock_table.get_item.return_value = {
            "Item": {
                "cacheKey": f"{account_id}#{timeframe}",
                "data": {"cost_by_service": [{"service": "EC2", "cost": 100}]},
                "cachedAt": fresh_time,
            }
        }

        result = execute_cost_analysis_general(account_context, session)

    # Should use cache, not call connector
    mock_connector.assert_not_called()
    assert result.get("retrieval_path") == "cache_hit"


@settings(max_examples=100)
@given(
    account_id=st.from_regex(r"\d{12}", fullmatch=True),
    timeframe=st.sampled_from(["last-7d", "last-30d", "last-90d"]),
)
def test_property15_stale_cache_calls_api_and_writes_back(account_id, timeframe):
    """Property 15: Stale/missing cache → API call + write-back."""
    account_context = AccountContext(
        account_id=account_id,
        account_name="Test",
        cloud_provider="aws",
        member_email="test@example.com",
    )
    session = SessionState(active_timeframe=timeframe)

    stale_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    with patch("agent.behavioral_router.boto3") as mock_boto3, \
         patch("agent.behavioral_router.get_connector") as mock_connector:

        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_boto3.resource.return_value = mock_resource
        mock_resource.Table.return_value = mock_table

        # Return stale cached data
        mock_table.get_item.return_value = {
            "Item": {
                "cacheKey": f"{account_id}#{timeframe}",
                "data": {"cost_by_service": []},
                "cachedAt": stale_time,
            }
        }

        # API returns fresh data
        mock_conn = MagicMock()
        mock_conn.get_cost_data.return_value = {"cost_by_service": [{"service": "RDS", "cost": 200}]}
        mock_connector.return_value = mock_conn

        result = execute_cost_analysis_general(account_context, session)

    # Should have called the API
    mock_conn.get_cost_data.assert_called_once()
    # Should have written back to cache
    mock_table.put_item.assert_called_once()
    assert result.get("retrieval_path") == "cache_miss_api_fallback"
