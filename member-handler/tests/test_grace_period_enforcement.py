"""Unit tests for grace period enforcement logic in _check_and_consume_credits.

Tests cover:
- Grace period within 7 days allows continued custom tier access
- Grace period past deadline reverts member to free tier
- Grace period without deadline set allows continued access (defensive)
- _enter_grace_period sets correct fields and sends email
- _send_grace_period_email calls SES with correct parameters
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGracePeriodEnforcementWithinDeadline:
    """Test that members within the 7-day grace window retain custom tier access."""

    @patch("lambda_function.dynamodb")
    def test_within_grace_period_uses_custom_allocation(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        # Grace deadline is 3 days in the future
        grace_deadline = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentGraceDeadline": grace_deadline,
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        # Should allow access (return None = no error)
        result = _check_and_consume_credits("user@example.com", "custom", 10)
        assert result is None

    @patch("lambda_function.dynamodb")
    def test_within_grace_period_does_not_revert_tier(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        grace_deadline = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentGraceDeadline": grace_deadline,
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        _check_and_consume_credits("user@example.com", "custom", 10)

        # Should NOT have called update_item to change tier
        update_calls = mock_table.update_item.call_args_list
        for c in update_calls:
            expr = c[1].get("UpdateExpression", "") if c[1] else ""
            assert "tier = :free" not in expr
            assert "tier = :scale" not in expr


class TestGracePeriodEnforcementPastDeadline:
    """Test that members past the grace deadline revert to free tier."""

    @patch("lambda_function.dynamodb")
    def test_past_grace_deadline_reverts_to_free_tier(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        # Grace deadline was 2 days ago
        grace_deadline = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentGraceDeadline": grace_deadline,
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        # Should now use free tier allocation (100 tokens)
        # Cost of 200 exceeds free tier, so should get TokensExhausted error
        result = _check_and_consume_credits("user@example.com", "custom", 200)
        assert result is not None
        body = json.loads(result["body"])
        assert body["error"] == "TokensExhausted"

    @patch("lambda_function.dynamodb")
    def test_past_grace_deadline_updates_member_record(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        grace_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentGraceDeadline": grace_deadline,
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        _check_and_consume_credits("user@example.com", "custom", 2)

        # Should have updated the member to free tier
        update_calls = mock_table.update_item.call_args_list
        # First update should be the grace period expiry
        first_update = update_calls[0]
        expr = first_update[1].get("UpdateExpression", "")
        values = first_update[1].get("ExpressionAttributeValues", {})
        assert "tier = :free" in expr
        assert "commitmentStatus = :expired" in expr
        assert values[":free"] == "free"
        assert values[":expired"] == "expired"

    @patch("lambda_function.dynamodb")
    def test_past_grace_deadline_clears_all_commitment_fields(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        grace_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                "commitmentGraceDeadline": grace_deadline,
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        _check_and_consume_credits("user@example.com", "custom", 2)

        # Verify REMOVE clause includes all commitment fields
        update_calls = mock_table.update_item.call_args_list
        first_update = update_calls[0]
        expr = first_update[1].get("UpdateExpression", "")
        assert "REMOVE" in expr
        assert "customTokenAllocation" in expr
        assert "customMonthlyPrice" in expr
        assert "commitmentStartDate" in expr
        assert "commitmentEndDate" in expr
        assert "commitmentMonths" in expr
        assert "commitmentDiscountPercent" in expr
        assert "paypalCustomPlanSubId" in expr
        assert "commitmentGraceDeadline" in expr


class TestGracePeriodNoDeadlineSet:
    """Test defensive behavior when grace period status set but no deadline."""

    @patch("lambda_function.dynamodb")
    def test_no_grace_deadline_allows_custom_access(self, mock_dynamodb):
        from lambda_function import _check_and_consume_credits

        # Grace period status but no commitmentGraceDeadline field
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "email": "user@example.com",
                "tier": "custom",
                "commitmentStatus": "grace_period",
                # No commitmentGraceDeadline
                "customTokenAllocation": 2300,
                "aiCreditsUsed": 0,
                "aiCreditsMonth": "",
            }
        }
        mock_dynamodb.Table.return_value = mock_table

        # Should allow access with custom allocation (no deadline means within grace)
        result = _check_and_consume_credits("user@example.com", "custom", 10)
        assert result is None


class TestEnterGracePeriod:
    """Test the _enter_grace_period helper function."""

    @patch("lambda_function.ses_client")
    @patch("lambda_function.dynamodb")
    def test_enter_grace_period_sets_fields(self, mock_dynamodb, mock_ses):
        from lambda_function import _enter_grace_period

        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        _enter_grace_period("user@example.com")

        # Should have called update_item with grace_period status and deadline
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        expr = call_kwargs["UpdateExpression"]
        values = call_kwargs["ExpressionAttributeValues"]

        assert "commitmentStatus = :grace" in expr
        assert "commitmentGraceDeadline = :deadline" in expr
        assert values[":grace"] == "grace_period"
        # Deadline should be approximately 7 days from now
        deadline = datetime.fromisoformat(values[":deadline"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (deadline - now).total_seconds()
        # Should be ~7 days (604800 seconds), allow 60 seconds tolerance
        assert 604700 < diff < 604900

    @patch("lambda_function.ses_client")
    @patch("lambda_function.dynamodb")
    def test_enter_grace_period_sends_email(self, mock_dynamodb, mock_ses):
        from lambda_function import _enter_grace_period

        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        _enter_grace_period("user@example.com")

        # Should have called ses send_email
        mock_ses.send_email.assert_called_once()
        call_kwargs = mock_ses.send_email.call_args[1]
        assert call_kwargs["Destination"]["ToAddresses"] == ["user@example.com"]
        assert "Payment Failed" in call_kwargs["Message"]["Subject"]["Data"]


class TestSendGracePeriodEmail:
    """Test the _send_grace_period_email helper."""

    @patch("lambda_function.ses_client")
    def test_email_contains_deadline_date(self, mock_ses):
        from lambda_function import _send_grace_period_email

        deadline = "2026-07-22T10:00:00+00:00"
        _send_grace_period_email("user@example.com", deadline)

        mock_ses.send_email.assert_called_once()
        call_kwargs = mock_ses.send_email.call_args[1]
        body_html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "July 22, 2026" in body_html

    @patch("lambda_function.ses_client")
    def test_email_mentions_free_tier_reversion(self, mock_ses):
        from lambda_function import _send_grace_period_email

        deadline = "2026-07-22T10:00:00+00:00"
        _send_grace_period_email("user@example.com", deadline)

        call_kwargs = mock_ses.send_email.call_args[1]
        body_html = call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert "Free tier" in body_html or "Free" in body_html
        assert "100 tokens" in body_html

    @patch("lambda_function.ses_client")
    def test_email_handles_ses_failure_gracefully(self, mock_ses):
        from lambda_function import _send_grace_period_email

        mock_ses.send_email.side_effect = Exception("SES quota exceeded")

        # Should not raise — function handles exceptions internally
        _send_grace_period_email("user@example.com", "2026-07-22T10:00:00+00:00")

    @patch("lambda_function.ses_client")
    def test_email_subject_mentions_payment_failed(self, mock_ses):
        from lambda_function import _send_grace_period_email

        deadline = "2026-07-22T10:00:00+00:00"
        _send_grace_period_email("user@example.com", deadline)

        call_kwargs = mock_ses.send_email.call_args[1]
        subject = call_kwargs["Message"]["Subject"]["Data"]
        assert "Payment Failed" in subject
