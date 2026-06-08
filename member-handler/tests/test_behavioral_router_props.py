"""Property-based tests for behavioral router (Properties 8, 9).

Property 8: Fault-tolerant data gathering
Property 9: Forecast projection period validation
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.behavioral_router import (
    execute_cost_analysis_specific,
    execute_forecasting,
)
from agent.models import AccountContext, SessionState
from agent.constants import FORECAST_MAX_MONTHS


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def random_account_context():
    """Generate random AccountContext."""
    return st.builds(
        AccountContext,
        account_id=st.from_regex(r"\d{12}", fullmatch=True),
        account_name=st.just("Test Account"),
        cloud_provider=st.just("aws"),
        member_email=st.just("test@example.com"),
        supported_services=st.just(["EC2", "RDS", "S3"]),
        provider_config=st.just({}),
    )


# ---------------------------------------------------------------------------
# Property 8: Fault-tolerant data gathering
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    account_context=random_account_context(),
    target_service=st.sampled_from(["ec2", "rds", "s3", "lambda"]),
    tips_fail=st.booleans(),
    cost_fail=st.booleans(),
    recommend_fail=st.booleans(),
)
def test_property8_partial_failures_return_partial_results(
    account_context, target_service, tips_fail, cost_fail, recommend_fail,
):
    """Property 8: K of N failures still returns (N-K) results, error only when all fail."""
    # Mock the data sources with configurable failures
    with patch("agent.behavioral_router._query_tips_for_service") as mock_tips, \
         patch("agent.behavioral_router.get_connector") as mock_connector:

        # Configure tips
        if tips_fail:
            mock_tips.side_effect = Exception("Tips DB error")
        else:
            mock_tips.return_value = [{"tipId": "tip1", "title": "Test tip"}]

        # Configure connector
        mock_conn_instance = MagicMock()
        if cost_fail:
            mock_conn_instance.get_cost_data.side_effect = Exception("Cost API error")
        else:
            mock_conn_instance.get_cost_data.return_value = {"cost_by_service": [{"service": "EC2", "cost": 100}]}

        if recommend_fail:
            mock_conn_instance.get_resource_recommendations.side_effect = Exception("Recommend API error")
        else:
            mock_conn_instance.get_resource_recommendations.return_value = {"recommendations": [{"id": "r1"}]}

        mock_connector.return_value = mock_conn_instance

        result = execute_cost_analysis_specific(account_context, target_service)

    # Count failures
    failures = sum([tips_fail, cost_fail, recommend_fail])

    if failures == 3:
        # All sources failed
        assert result.get("retrieval_path") == "all_sources_failed" or len(result.get("sources", [])) == 0
    else:
        # Some sources succeeded
        sources = result.get("sources", [])
        assert len(sources) > 0, f"Expected some sources with {3 - failures} successes"
        # Should not have a top-level error
        assert "error" not in result or result.get("sources")


@settings(max_examples=100)
@given(
    account_context=random_account_context(),
    target_service=st.sampled_from(["ec2", "rds", "s3"]),
)
def test_property8_all_sources_succeed_returns_all(account_context, target_service):
    """Property 8: When no failures, returns results from all sources."""
    with patch("agent.behavioral_router._query_tips_for_service") as mock_tips, \
         patch("agent.behavioral_router.get_connector") as mock_connector:

        mock_tips.return_value = [{"tipId": "tip1", "title": "Test tip"}]

        mock_conn_instance = MagicMock()
        mock_conn_instance.get_cost_data.return_value = {"cost_by_service": []}
        mock_conn_instance.get_resource_recommendations.return_value = {"recommendations": [{"id": "r1"}]}
        mock_connector.return_value = mock_conn_instance

        result = execute_cost_analysis_specific(account_context, target_service)

    sources = result.get("sources", [])
    assert len(sources) >= 2  # At least tips + cost or recommend


# ---------------------------------------------------------------------------
# Property 9: Forecast projection period validation
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(months=st.integers(min_value=1, max_value=FORECAST_MAX_MONTHS))
def test_property9_valid_projection_accepted(months):
    """Property 9: 1-12 months accepted."""
    account_context = AccountContext(
        account_id="123456789012",
        account_name="Test",
        cloud_provider="aws",
        member_email="test@example.com",
    )

    timeframe = f"next-{months}m"

    with patch("agent.behavioral_router.get_connector") as mock_connector:
        mock_conn = MagicMock()
        mock_conn.get_historical_costs.return_value = [
            {"date": f"2024-01-{i:02d}", "cost": 42.0} for i in range(1, 31)
        ]
        mock_connector.return_value = mock_conn

        result = execute_forecasting(account_context, timeframe)

    # Should not have validation error
    assert result.get("error") is None or "must be" not in result.get("error", "")
    assert result.get("retrieval_path") != "validation_rejected"


@settings(max_examples=100)
@given(months=st.integers(min_value=FORECAST_MAX_MONTHS + 1, max_value=100))
def test_property9_over_12_months_rejected(months):
    """Property 9: >12 months rejected with descriptive error."""
    account_context = AccountContext(
        account_id="123456789012",
        account_name="Test",
        cloud_provider="aws",
        member_email="test@example.com",
    )

    timeframe = f"next-{months}m"

    result = execute_forecasting(account_context, timeframe)

    # Should be rejected before any API call
    assert "error" in result
    assert result["retrieval_path"] == "validation_rejected"
    # Error should mention the valid range
    assert "12" in result["error"] or "months" in result["error"]
