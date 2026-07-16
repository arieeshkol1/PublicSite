"""Unit tests for GET /members/custom-plan/status endpoint.

Tests cover:
- Returns hasCommitment: false when member has no active commitment
- Returns full status when member has an active commitment
- Calculates canRenew correctly (true when 30 days or fewer remain)
- Handles expired commitment status
- Returns 401 when not authenticated
- Returns 404 when member not found
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_event(token="Bearer valid-token"):
    """Create a mock API Gateway event for GET /members/custom-plan/status."""
    return {
        "routeKey": "GET /members/custom-plan/status",
        "headers": {"authorization": token},
        "body": None,
    }


def _mock_validate_token_ok(event):
    """Mock valid token returning member email."""
    return {"sub": "user@example.com", "role": "member"}


def _mock_validate_token_fail(event):
    """Mock invalid token returning error response."""
    return {"statusCode": 401, "body": json.dumps({"error": "AuthError"})}


class TestCustomPlanStatusNoCommitment:
    """Test that members without an active commitment get hasCommitment: false."""

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_no_commitment_fields(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # Member record with no commitment fields
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"email": "user@example.com", "tier": "scale"}}
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["hasCommitment"] is False
        assert body["status"] is None

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_expired_commitment_status(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # Member has commitment fields but status is expired
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "scale",
                "commitmentEndDate": "2024-01-15T00:00:00Z",
                "commitmentStatus": "expired",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["hasCommitment"] is False
        assert body["status"] is None

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_no_commitment_end_date(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # Member has commitmentStatus but no commitmentEndDate
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"email": "user@example.com", "tier": "custom", "commitmentStatus": "active"}
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["hasCommitment"] is False


class TestCustomPlanStatusActiveCommitment:
    """Test that active commitments return full status information."""

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_active_commitment_returns_full_status(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # Set end date far in the future
        end_date = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        start_date = "2026-07-15T00:00:00Z"

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "active",
                "commitmentStartDate": start_date,
                "commitmentEndDate": end_date,
                "customMonthlyPrice": Decimal("212.50"),
                "customTokenAllocation": 2300,
                "commitmentDiscountPercent": 15,
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["hasCommitment"] is True
        assert body["status"] == "active"
        assert body["startDate"] == start_date
        assert body["endDate"] == end_date
        assert body["monthlyPrice"] == 212.50
        assert body["tokenAllocation"] == 2300
        assert body["discountPercent"] == 15
        assert body["canRenew"] is False  # Far in the future
        assert body["remainingMonths"] > 0


class TestCustomPlanStatusCanRenew:
    """Test canRenew flag logic (true when 30 days or fewer remain)."""

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_can_renew_true_when_within_30_days(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # End date is 20 days from now
        end_date = (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "active",
                "commitmentStartDate": "2026-01-15T00:00:00Z",
                "commitmentEndDate": end_date,
                "customMonthlyPrice": Decimal("212.50"),
                "customTokenAllocation": 2300,
                "commitmentDiscountPercent": 15,
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert body["canRenew"] is True

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_can_renew_true_at_exactly_30_days(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # End date is exactly 30 days from now
        end_date = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "active",
                "commitmentStartDate": "2026-01-15T00:00:00Z",
                "commitmentEndDate": end_date,
                "customMonthlyPrice": Decimal("200.00"),
                "customTokenAllocation": 2000,
                "commitmentDiscountPercent": 10,
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert body["canRenew"] is True

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_can_renew_false_when_more_than_30_days(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        # End date is 60 days from now
        end_date = (datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "active",
                "commitmentStartDate": "2026-01-15T00:00:00Z",
                "commitmentEndDate": end_date,
                "customMonthlyPrice": Decimal("212.50"),
                "customTokenAllocation": 2300,
                "commitmentDiscountPercent": 15,
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert body["canRenew"] is False


class TestCustomPlanStatusAuth:
    """Test authentication handling."""

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_fail)
    def test_returns_401_without_auth(self, mock_auth):
        from lambda_function import handle_custom_plan_status

        result = handle_custom_plan_status(_make_event(token=""))
        assert result["statusCode"] == 401

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_returns_404_when_member_not_found(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        assert result["statusCode"] == 404


class TestCustomPlanStatusGracePeriod:
    """Test grace period status is correctly returned."""

    @patch("lambda_function.validate_token", side_effect=_mock_validate_token_ok)
    @patch("lambda_function.dynamodb")
    def test_grace_period_status_returns_commitment(self, mock_dynamodb, mock_auth):
        from lambda_function import handle_custom_plan_status

        end_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentStartDate": "2026-01-15T00:00:00Z",
                "commitmentEndDate": end_date,
                "customMonthlyPrice": Decimal("212.50"),
                "customTokenAllocation": 2300,
                "commitmentDiscountPercent": 15,
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        result = handle_custom_plan_status(_make_event())
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["hasCommitment"] is True
        assert body["status"] == "grace_period"
