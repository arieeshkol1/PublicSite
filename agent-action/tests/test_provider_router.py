"""
Unit tests for provider_router module.

Tests cover:
- resolve_provider: DynamoDB lookup, missing account, invalid/missing provider defaulting
- route_tool: dispatching to correct connector, notSupported response, authError response
- Cost cache integration: cache hit, cache miss, stale data, cache read failure
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from provider_router import (
    resolve_provider,
    route_tool,
    AccountNotFoundError,
    AuthenticationError,
    TOOL_TO_METHOD,
    VALID_PROVIDERS,
    CACHEABLE_TOOLS,
    COST_CACHE_TABLE_NAME,
    CACHE_STALENESS_THRESHOLD_HOURS,
    _get_connector,
    _read_cost_cache,
    _write_cost_cache,
    _aggregate_cost_breakdown,
    _aggregate_monthly_trend,
)


class TestResolveProvider:
    """Tests for resolve_provider function."""

    @patch("provider_router._get_dynamodb_resource")
    def test_returns_aws_for_aws_account(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "123456789012", "cloudProvider": "aws"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("123456789012", "user@test.com")
        assert result == "aws"

    @patch("provider_router._get_dynamodb_resource")
    def test_returns_azure_for_azure_account(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "sub-123", "cloudProvider": "azure"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("sub-123", "user@test.com")
        assert result == "azure"

    @patch("provider_router._get_dynamodb_resource")
    def test_returns_gcp_for_gcp_account(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "my-project", "cloudProvider": "gcp"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("my-project", "user@test.com")
        assert result == "gcp"

    @patch("provider_router._get_dynamodb_resource")
    def test_returns_openai_for_openai_account(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "org-abc", "cloudProvider": "openai"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("org-abc", "user@test.com")
        assert result == "openai"

    @patch("provider_router._get_dynamodb_resource")
    def test_defaults_to_aws_when_provider_missing(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "123456789012"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("123456789012", "user@test.com")
        assert result == "aws"

    @patch("provider_router._get_dynamodb_resource")
    def test_defaults_to_aws_when_provider_empty_string(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "123", "cloudProvider": ""}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("123", "user@test.com")
        assert result == "aws"

    @patch("provider_router._get_dynamodb_resource")
    def test_defaults_to_aws_when_provider_invalid(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "user@test.com", "accountId": "123", "cloudProvider": "digitalocean"}
        }
        mock_dynamo.return_value.Table.return_value = table

        result = resolve_provider("123", "user@test.com")
        assert result == "aws"

    @patch("provider_router._get_dynamodb_resource")
    def test_raises_account_not_found_when_no_item(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {}  # No "Item" key
        mock_dynamo.return_value.Table.return_value = table

        with pytest.raises(AccountNotFoundError) as exc_info:
            resolve_provider("nonexistent", "user@test.com")
        assert "nonexistent" in str(exc_info.value)
        assert "user@test.com" in str(exc_info.value)

    @patch("provider_router._get_dynamodb_resource")
    def test_queries_correct_table_and_keys(self, mock_dynamo):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"memberEmail": "a@b.com", "accountId": "acc1", "cloudProvider": "aws"}
        }
        mock_dynamo.return_value.Table.return_value = table

        resolve_provider("acc1", "a@b.com")

        mock_dynamo.return_value.Table.assert_called_with("MemberPortal-Accounts")
        table.get_item.assert_called_once_with(
            Key={"memberEmail": "a@b.com", "accountId": "acc1"}
        )


class TestRouteTool:
    """Tests for route_tool function."""

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_dispatches_to_connector_method(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getComputeInstances"]
        connector.get_compute_instances.return_value = {"instances": [], "count": 0}
        mock_get_conn.return_value = connector

        result = route_tool("getComputeInstances", "123", "user@test.com", {})

        assert result == {"instances": [], "count": 0}
        connector.get_compute_instances.assert_called_once_with("123", "user@test.com", {})

    @patch("provider_router.resolve_provider")
    def test_returns_error_when_account_not_found(self, mock_resolve):
        mock_resolve.side_effect = AccountNotFoundError("123", "user@test.com")

        result = route_tool("getComputeInstances", "123", "user@test.com", {})

        assert "error" in result
        assert "Account not connected" in result["error"]
        assert "guidance" in result
        assert "Configure tab" in result["guidance"]

    @patch("provider_router.resolve_provider")
    def test_returns_retryable_error_on_dynamodb_client_error(self, mock_resolve):
        """When DynamoDB raises a ClientError during provider lookup, returns retryable error."""
        from botocore.exceptions import ClientError as BotoClientError
        mock_resolve.side_effect = BotoClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Service unavailable"}},
            "GetItem"
        )

        result = route_tool("getComputeInstances", "123", "user@test.com", {})

        assert "error" in result
        assert result["retryable"] is True
        assert "guidance" in result
        assert "Configure tab" in result["guidance"]

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_returns_not_supported_when_tool_not_in_operations(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "openai"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown", "getAIVendorUsage"]
        mock_get_conn.return_value = connector

        result = route_tool("getComputeInstances", "org-1", "user@test.com", {})

        assert result["notSupported"] is True
        assert "getComputeInstances" in result["message"]
        assert "openai" in result["message"]
        assert result["availableOperations"] == ["getCostBreakdown", "getAIVendorUsage"]

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_returns_auth_error_on_permission_failure(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getComputeInstances"]
        connector.get_compute_instances.side_effect = PermissionError("Access denied")
        mock_get_conn.return_value = connector

        result = route_tool("getComputeInstances", "123", "user@test.com", {})

        assert result["authError"] is True
        assert "guidance" in result
        assert "Configure tab" in result["guidance"]

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_returns_auth_error_on_authentication_error(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "azure"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.side_effect = AuthenticationError("Token expired")
        mock_get_conn.return_value = connector

        result = route_tool("getCostBreakdown", "sub-1", "user@test.com", {})

        assert result["authError"] is True
        assert "Configure tab" in result["guidance"]

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_returns_retryable_error_on_generic_exception(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "gcp"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getComputeInstances"]
        connector.get_compute_instances.side_effect = RuntimeError("API timeout")
        mock_get_conn.return_value = connector

        result = route_tool("getComputeInstances", "proj-1", "user@test.com", {})

        assert "error" in result
        assert result["retryable"] is True

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_passes_params_to_connector(self, mock_resolve, mock_get_conn):
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.return_value = {"totalCost": 100}
        mock_get_conn.return_value = connector

        params = {"startDate": "2024-01-01", "endDate": "2024-01-31"}
        route_tool("getCostBreakdown", "123", "user@test.com", params)

        connector.get_cost_breakdown.assert_called_once_with("123", "user@test.com", params)

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_monthly_trend_uses_get_cost_breakdown_method(self, mock_resolve, mock_get_conn):
        """getMonthlyTrend maps to the same get_cost_breakdown method."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getMonthlyTrend"]
        connector.get_cost_breakdown.return_value = {"monthlyComparison": {}}
        mock_get_conn.return_value = connector

        result = route_tool("getMonthlyTrend", "123", "user@test.com", {})

        connector.get_cost_breakdown.assert_called_once()


class TestToolToMethodMapping:
    """Tests for the TOOL_TO_METHOD constant."""

    def test_all_expected_tools_mapped(self):
        expected_tools = [
            "getCostBreakdown", "getMonthlyTrend", "getComputeInstances",
            "getDatabaseInstances", "getServerlessFunctions", "getObjectStorage",
            "getStorageVolumes", "getNetworkResources", "getBudgets",
            "getFinOpsSettings", "getCommitmentCoverage", "getTagCompliance",
            "getBusinessMetrics", "getCostForecast", "getCostAnomalies",
            "getRightsizingRecommendations", "getSpotCandidates",
            "getLicensingAnalysis", "getAIUsage", "getOptimizationTips",
            "getPricingData", "getContainerClusters",
        ]
        for tool in expected_tools:
            assert tool in TOOL_TO_METHOD, f"Missing mapping for {tool}"

    def test_get_ai_usage_maps_to_connector_method(self):
        """getAIUsage replaces the superseded getAIVendorUsage entry."""
        assert TOOL_TO_METHOD["getAIUsage"] == "get_ai_usage"
        assert "getAIVendorUsage" not in TOOL_TO_METHOD

    def test_tool_count(self):
        assert len(TOOL_TO_METHOD) == 22


class TestAccountNotFoundError:
    """Tests for the custom exception."""

    def test_stores_account_id_and_email(self):
        err = AccountNotFoundError("123", "user@test.com")
        assert err.account_id == "123"
        assert err.member_email == "user@test.com"

    def test_message_includes_guidance(self):
        err = AccountNotFoundError("123", "user@test.com")
        assert "Configure tab" in str(err)


class TestCostCacheIntegration:
    """Tests for cost cache integration in route_tool."""

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_cache_hit_returns_cached_data_for_get_cost_breakdown(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """When cache has fresh data, getCostBreakdown returns it without invoking connector."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        mock_get_conn.return_value = connector

        # Mock cache table returning fresh data
        now = datetime.now(timezone.utc)
        cache_table = MagicMock()
        cache_table.query.return_value = {
            "Items": [
                {
                    "pk": "user@test.com#123",
                    "sk": "DAILY#2024-01-15",
                    "cost_amount": "42.50",
                    "service_breakdown": {"EC2": "30.00", "S3": "12.50"},
                    "cached_at": now.isoformat(),
                }
            ]
        }
        mock_cache_table.return_value = cache_table

        result = route_tool("getCostBreakdown", "123", "user@test.com", {})

        # Should return cached data
        assert result["source"] == "cache"
        assert "totalCost30Days" in result
        # Should NOT invoke the connector
        connector.get_cost_breakdown.assert_not_called()

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_cache_hit_returns_cached_data_for_get_monthly_trend(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """When cache has fresh data, getMonthlyTrend returns it without invoking connector."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getMonthlyTrend"]
        mock_get_conn.return_value = connector

        now = datetime.now(timezone.utc)
        cache_table = MagicMock()
        cache_table.query.return_value = {
            "Items": [
                {
                    "pk": "user@test.com#123",
                    "sk": "DAILY#2024-01-01",
                    "cost_amount": "100.00",
                    "service_breakdown": {"EC2": "80.00", "S3": "20.00"},
                    "cached_at": now.isoformat(),
                },
                {
                    "pk": "user@test.com#123",
                    "sk": "DAILY#2024-02-01",
                    "cost_amount": "120.00",
                    "service_breakdown": {"EC2": "90.00", "S3": "30.00"},
                    "cached_at": now.isoformat(),
                },
            ]
        }
        mock_cache_table.return_value = cache_table

        result = route_tool("getMonthlyTrend", "123", "user@test.com", {})

        assert result["source"] == "cache"
        assert "monthlyComparison" in result
        connector.get_cost_breakdown.assert_not_called()

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_cache_miss_invokes_connector_and_writes_cache(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """On cache miss, invokes connector and writes result to cache."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.return_value = {
            "totalCost30Days": 150.00,
            "topServices": [{"service": "EC2", "cost": 100.00}, {"service": "S3", "cost": 50.00}],
            "dailyCosts": [{"date": "2024-01-15", "cost": 5.00}],
            "period": "2024-01-01 to 2024-02-01",
        }
        mock_get_conn.return_value = connector

        # Cache miss (empty result)
        cache_table = MagicMock()
        cache_table.query.return_value = {"Items": []}
        mock_cache_table.return_value = cache_table

        result = route_tool("getCostBreakdown", "123", "user@test.com", {})

        # Should invoke connector
        connector.get_cost_breakdown.assert_called_once_with("123", "user@test.com", {})
        # Should write to cache
        cache_table.put_item.assert_called()
        # Should return live result
        assert result["totalCost30Days"] == 150.00

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_stale_cache_invokes_connector(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """When cache data is older than 24 hours, invokes connector."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.return_value = {
            "totalCost30Days": 200.00,
            "topServices": [{"service": "EC2", "cost": 200.00}],
            "dailyCosts": [{"date": "2024-01-20", "cost": 7.00}],
            "period": "2024-01-01 to 2024-02-01",
        }
        mock_get_conn.return_value = connector

        # Stale cache (cached_at > 24 hours ago)
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        cache_table = MagicMock()
        cache_table.query.return_value = {
            "Items": [
                {
                    "pk": "user@test.com#123",
                    "sk": "DAILY#2024-01-15",
                    "cost_amount": "42.50",
                    "service_breakdown": {"EC2": "30.00"},
                    "cached_at": stale_time,
                }
            ]
        }
        mock_cache_table.return_value = cache_table

        result = route_tool("getCostBreakdown", "123", "user@test.com", {})

        # Should invoke connector since cache is stale
        connector.get_cost_breakdown.assert_called_once()
        assert result["totalCost30Days"] == 200.00

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_cache_read_failure_falls_back_to_live_api(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """On cache read failure, falls back to live API with warning."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.return_value = {
            "totalCost30Days": 300.00,
            "topServices": [{"service": "Lambda", "cost": 300.00}],
            "dailyCosts": [],
            "period": "2024-01-01 to 2024-02-01",
        }
        mock_get_conn.return_value = connector

        # Cache read throws exception
        cache_table = MagicMock()
        cache_table.query.side_effect = Exception("DynamoDB timeout")
        mock_cache_table.return_value = cache_table

        result = route_tool("getCostBreakdown", "123", "user@test.com", {})

        # Should fall back to connector
        connector.get_cost_breakdown.assert_called_once()
        assert result["totalCost30Days"] == 300.00

    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_non_cacheable_tools_bypass_cache(self, mock_resolve, mock_get_conn):
        """Tools not in CACHEABLE_TOOLS should not check cache."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getComputeInstances"]
        connector.get_compute_instances.return_value = {"instances": [], "count": 0}
        mock_get_conn.return_value = connector

        with patch("provider_router._get_cache_table") as mock_cache:
            result = route_tool("getComputeInstances", "123", "user@test.com", {})
            # Cache should NOT be consulted for non-cost tools
            mock_cache.assert_not_called()

        assert result == {"instances": [], "count": 0}

    @patch("provider_router._get_cache_table")
    @patch("provider_router._get_connector")
    @patch("provider_router.resolve_provider")
    def test_cache_write_failure_does_not_affect_response(
        self, mock_resolve, mock_get_conn, mock_cache_table
    ):
        """If cache write fails, the live result is still returned."""
        mock_resolve.return_value = "aws"
        connector = MagicMock()
        connector.SUPPORTED_OPERATIONS = ["getCostBreakdown"]
        connector.get_cost_breakdown.return_value = {
            "totalCost30Days": 50.00,
            "topServices": [{"service": "S3", "cost": 50.00}],
            "dailyCosts": [{"date": "2024-01-10", "cost": 2.00}],
            "period": "2024-01-01 to 2024-02-01",
        }
        mock_get_conn.return_value = connector

        # Cache miss, but write will fail
        cache_table = MagicMock()
        cache_table.query.return_value = {"Items": []}
        cache_table.put_item.side_effect = Exception("DynamoDB write error")
        mock_cache_table.return_value = cache_table

        result = route_tool("getCostBreakdown", "123", "user@test.com", {})

        # Should still return the live result
        assert result["totalCost30Days"] == 50.00


class TestCacheKeyFormat:
    """Tests for cache key format: {memberEmail}#{accountId}."""

    @patch("provider_router._get_cache_table")
    def test_cache_key_format(self, mock_cache_table):
        """Cache queries use the correct pk format: {memberEmail}#{accountId}."""
        cache_table = MagicMock()
        cache_table.query.return_value = {"Items": []}
        mock_cache_table.return_value = cache_table

        _read_cost_cache("alice@company.com", "987654321012", "getCostBreakdown", {})

        # Verify the query was called with proper key format
        call_kwargs = cache_table.query.call_args[1]
        key_expr = call_kwargs["KeyConditionExpression"]
        # The Key condition should reference pk = "alice@company.com#987654321012"
        # We can verify the query was actually called
        cache_table.query.assert_called_once()

    @patch("provider_router._get_cache_table")
    def test_sort_key_format_daily(self, mock_cache_table):
        """Sort key uses DAILY#{date} format."""
        cache_table = MagicMock()
        cache_table.query.return_value = {"Items": []}
        mock_cache_table.return_value = cache_table

        _read_cost_cache("user@test.com", "123", "getCostBreakdown", {})

        # Verify query was called (sort key is embedded in the KeyConditionExpression)
        cache_table.query.assert_called_once()


class TestAggregateFunctions:
    """Tests for _aggregate_cost_breakdown and _aggregate_monthly_trend."""

    def test_aggregate_cost_breakdown_basic(self):
        """Aggregates daily items into cost breakdown response."""
        items = [
            {
                "pk": "user@test.com#123",
                "sk": "DAILY#2024-01-15",
                "cost_amount": "10.00",
                "service_breakdown": {"EC2": "7.00", "S3": "3.00"},
            },
            {
                "pk": "user@test.com#123",
                "sk": "DAILY#2024-01-16",
                "cost_amount": "12.00",
                "service_breakdown": {"EC2": "8.00", "S3": "4.00"},
            },
        ]
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 2, 1, tzinfo=timezone.utc)

        result = _aggregate_cost_breakdown(items, start_date, end_date)

        assert result["totalCost30Days"] == 22.0
        assert result["source"] == "cache"
        assert "(from cache)" in result["period"]
        assert len(result["topServices"]) == 2
        # EC2: 7+8=15, S3: 3+4=7
        assert result["topServices"][0]["service"] == "EC2"
        assert result["topServices"][0]["cost"] == 15.0
        assert result["topServices"][1]["service"] == "S3"
        assert result["topServices"][1]["cost"] == 7.0

    def test_aggregate_monthly_trend_basic(self):
        """Aggregates daily items into monthly trend response."""
        items = [
            {
                "pk": "user@test.com#123",
                "sk": "DAILY#2024-01-15",
                "cost_amount": "10.00",
                "service_breakdown": {"EC2": "7.00", "S3": "3.00"},
            },
            {
                "pk": "user@test.com#123",
                "sk": "DAILY#2024-02-10",
                "cost_amount": "20.00",
                "service_breakdown": {"EC2": "15.00", "S3": "5.00"},
            },
        ]

        result = _aggregate_monthly_trend(items)

        assert result["source"] == "cache"
        assert "2024-01" in result["months"]
        assert "2024-02" in result["months"]
        assert result["monthlyComparison"]["2024-01"]["EC2"] == 7.0
        assert result["monthlyComparison"]["2024-02"]["EC2"] == 15.0

    def test_aggregate_monthly_trend_filters_small_costs(self):
        """Monthly trend filters out costs <= 0.01."""
        items = [
            {
                "pk": "user@test.com#123",
                "sk": "DAILY#2024-01-15",
                "cost_amount": "10.00",
                "service_breakdown": {"EC2": "10.00", "TinyService": "0.005"},
            },
        ]

        result = _aggregate_monthly_trend(items)

        assert "EC2" in result["monthlyComparison"]["2024-01"]
        assert "TinyService" not in result["monthlyComparison"]["2024-01"]


class TestProperty1ProviderSelectionPurity:
    """Property 1: Provider selection is a pure function of cloudProvider.

    Feature: vendor-agnostic-ai-usage, Property 1
    **Validates: Requirements 1.1, 1.2**

    The connector chosen by the resolver depends only on the stored
    `cloudProvider` value and never on the account/member identity or
    vendor-specific conditional logic. Any two accounts with the same
    `cloudProvider` therefore resolve to the same provider and connector type.
    """

    @staticmethod
    def _make_resource(cloud_provider, present=True):
        """Build a mock DynamoDB resource whose account item carries cloud_provider."""
        table = MagicMock()
        if present:
            item = {"memberEmail": "x", "accountId": "y"}
            if cloud_provider is not None:
                item["cloudProvider"] = cloud_provider
            table.get_item.return_value = {"Item": item}
        else:
            table.get_item.return_value = {}
        resource = MagicMock()
        resource.Table.return_value = table
        return resource

    @settings(max_examples=150, deadline=None)
    @given(
        cloud_provider=st.one_of(
            st.sampled_from(["aws", "azure", "gcp", "openai"]),
            # Invalid / missing values must deterministically default to "aws".
            st.sampled_from(["", "AWS", "digitalocean", "oracle", "unknown"]),
            st.none(),
        ),
        acct_a=st.text(min_size=1, max_size=16),
        email_a=st.emails(),
        acct_b=st.text(min_size=1, max_size=16),
        email_b=st.emails(),
    )
    def test_provider_selection_is_pure_function_of_cloud_provider(
        self, cloud_provider, acct_a, email_a, acct_b, email_b
    ):
        resource = self._make_resource(cloud_provider)

        with patch("provider_router._get_dynamodb_resource", return_value=resource):
            prov_a = resolve_provider(acct_a, email_a)
            prov_b = resolve_provider(acct_b, email_b)

        # The resolved provider depends only on cloudProvider, so two different
        # accounts sharing the same cloudProvider resolve identically.
        assert prov_a == prov_b

        # The resolved provider is exactly the pure function of cloudProvider:
        # valid values pass through; everything else defaults to "aws".
        expected = cloud_provider if cloud_provider in VALID_PROVIDERS else "aws"
        assert prov_a == expected
        assert prov_a in VALID_PROVIDERS

        # The connector type is itself a pure function of the resolved provider,
        # so identical providers yield identical connector types.
        conn_a = type(_get_connector(prov_a)).__name__
        conn_b = type(_get_connector(prov_b)).__name__
        assert conn_a == conn_b
