"""Unit tests for the Trusted Advisor source fetcher."""

from unittest.mock import MagicMock, patch
import pytest

from sources.trusted_advisor import (
    fetch_cost_checks,
    _extract_estimated_savings,
    _map_category,
    _extract_service,
)


class TestFetchCostChecks:
    """Tests for the main fetch_cost_checks function."""

    def test_returns_empty_list_on_api_error(self):
        """API errors should be handled gracefully, returning empty list."""
        client = MagicMock()
        client.describe_trusted_advisor_checks.side_effect = Exception("API Error")

        result = fetch_cost_checks(client)

        assert result == []

    def test_filters_to_cost_optimizing_category(self):
        """Only checks with category 'cost_optimizing' should be processed."""
        client = MagicMock()
        client.describe_trusted_advisor_checks.return_value = {
            "checks": [
                {"id": "check1", "name": "Cost Check", "category": "cost_optimizing", "description": "desc1"},
                {"id": "check2", "name": "Security Check", "category": "security", "description": "desc2"},
                {"id": "check3", "name": "Another Cost", "category": "cost_optimizing", "description": "desc3"},
            ]
        }
        client.describe_trusted_advisor_check_result.return_value = {
            "result": {"categorySpecificSummary": {}, "flaggedResources": []}
        }

        result = fetch_cost_checks(client)

        # Should only process the 2 cost_optimizing checks
        assert len(result) == 2
        assert result[0]["title"] == "Cost Check"
        assert result[1]["title"] == "Another Cost"

    def test_normalizes_check_to_tip_dict(self):
        """Each check should be normalized with all required fields and defaults."""
        client = MagicMock()
        client.describe_trusted_advisor_checks.return_value = {
            "checks": [
                {
                    "id": "abc123",
                    "name": "Low Utilization Amazon EC2 Instances",
                    "category": "cost_optimizing",
                    "description": "Checks for EC2 instances with low utilization.",
                }
            ]
        }
        client.describe_trusted_advisor_check_result.return_value = {
            "result": {
                "categorySpecificSummary": {
                    "costOptimizing": {"estimatedMonthlySavings": 150.0}
                },
                "flaggedResources": [],
            }
        }

        result = fetch_cost_checks(client)

        assert len(result) == 1
        tip = result[0]

        # Content fields
        assert tip["title"] == "Low Utilization Amazon EC2 Instances"
        assert tip["description"] == "Checks for EC2 instances with low utilization."
        assert tip["estimatedSavings"] == "$150/month"
        assert tip["service"] == "EC2"
        assert tip["category"] == "idle-resources"
        assert tip["difficulty"] == "medium"
        assert tip["automatedCheck"] == "Trusted Advisor check: Low Utilization Amazon EC2 Instances"

        # Default operational fields
        assert tip["checkImplemented"] is False
        assert tip["actionType"] == "advisory"
        assert tip["actionLabel"] == "View Details"
        assert tip["level"] == 3

        # Sync metadata
        assert tip["syncSource"] == "trusted-advisor"
        assert tip["_sourceId"] == "abc123"

    def test_continues_on_individual_check_result_error(self):
        """If fetching a single check result fails, skip it and continue."""
        client = MagicMock()
        client.describe_trusted_advisor_checks.return_value = {
            "checks": [
                {"id": "check1", "name": "Check 1", "category": "cost_optimizing", "description": "d1"},
                {"id": "check2", "name": "Check 2", "category": "cost_optimizing", "description": "d2"},
            ]
        }
        # First check result fails, second succeeds
        client.describe_trusted_advisor_check_result.side_effect = [
            Exception("Throttled"),
            {"result": {"categorySpecificSummary": {}, "flaggedResources": []}},
        ]

        result = fetch_cost_checks(client)

        # Should still return the second check
        assert len(result) == 1
        assert result[0]["title"] == "Check 2"

    def test_returns_empty_list_when_no_cost_checks(self):
        """If no cost_optimizing checks exist, return empty list."""
        client = MagicMock()
        client.describe_trusted_advisor_checks.return_value = {
            "checks": [
                {"id": "check1", "name": "Security Check", "category": "security", "description": "d"},
            ]
        }

        result = fetch_cost_checks(client)

        assert result == []


class TestExtractEstimatedSavings:
    """Tests for savings extraction from check results."""

    def test_extracts_from_category_specific_summary(self):
        """Should extract savings from categorySpecificSummary.costOptimizing."""
        result = {
            "categorySpecificSummary": {
                "costOptimizing": {"estimatedMonthlySavings": 250.50}
            },
            "flaggedResources": [],
        }

        savings = _extract_estimated_savings(result)

        assert savings == "$250/month"

    def test_returns_variable_when_no_savings_data(self):
        """Should return 'Variable' when no savings information is available."""
        result = {"categorySpecificSummary": {}, "flaggedResources": []}

        savings = _extract_estimated_savings(result)

        assert savings == "Variable"

    def test_returns_variable_for_zero_savings(self):
        """Should return 'Variable' when savings is zero."""
        result = {
            "categorySpecificSummary": {
                "costOptimizing": {"estimatedMonthlySavings": 0}
            },
            "flaggedResources": [],
        }

        savings = _extract_estimated_savings(result)

        assert savings == "Variable"


class TestMapCategory:
    """Tests for category mapping from check names."""

    def test_maps_idle_resources(self):
        assert _map_category({"name": "Idle Load Balancers"}) == "idle-resources"
        assert _map_category({"name": "Unused EBS Volumes"}) == "idle-resources"
        assert _map_category({"name": "Underutilized EC2"}) == "idle-resources"

    def test_maps_commitment_discounts(self):
        assert _map_category({"name": "Reserved Instance Optimization"}) == "commitment-discounts"

    def test_maps_right_sizing(self):
        assert _map_category({"name": "Right-Sizing Recommendations"}) == "right-sizing"
        assert _map_category({"name": "Oversized EC2 Instances"}) == "right-sizing"

    def test_maps_modernization(self):
        assert _map_category({"name": "Previous Generation Instances"}) == "modernization"

    def test_defaults_to_cost_optimizing(self):
        assert _map_category({"name": "Some Unknown Check"}) == "cost-optimizing"


class TestExtractService:
    """Tests for service extraction from check names."""

    def test_extracts_ec2(self):
        assert _extract_service({"name": "Low Utilization Amazon EC2 Instances"}) == "EC2"

    def test_extracts_rds(self):
        assert _extract_service({"name": "Idle RDS DB Instances"}) == "RDS"

    def test_extracts_s3(self):
        assert _extract_service({"name": "Amazon S3 Bucket Versioning"}) == "S3"

    def test_extracts_ebs(self):
        assert _extract_service({"name": "Underutilized EBS Volumes"}) == "EBS"

    def test_defaults_to_general(self):
        assert _extract_service({"name": "Some Generic Check"}) == "General"
