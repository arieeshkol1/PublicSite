"""Unit tests for POST /members/custom-plan/webhook endpoint (PayPal webhook handler).

Tests cover:
- Returns 401 when PayPal signature verification fails
- Returns 400 for invalid JSON body
- PAYMENT.SALE.COMPLETED clears grace period and sets status to active
- PAYMENT.SALE.DENIED sets grace_period status and 7-day deadline
- BILLING.SUBSCRIPTION.EXPIRED transitions member to Scale tier
- BILLING.SUBSCRIPTION.CANCELLED logs warning and returns 200
- Returns 200 when subscription_id not found in resource
- Returns 200 when member not found for subscription_id
- Unhandled event types return 200
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_webhook_event(event_type, resource, headers=None):
    """Create a mock API Gateway event for POST /members/custom-plan/webhook."""
    default_headers = {
        "paypal-transmission-id": "abc123",
        "paypal-transmission-time": "2026-07-15T10:00:00Z",
        "paypal-cert-url": "https://api.paypal.com/cert.pem",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "sig123",
    }
    if headers:
        default_headers.update(headers)

    body = json.dumps({
        "event_type": event_type,
        "resource": resource,
    })

    return {
        "routeKey": "POST /members/custom-plan/webhook",
        "headers": default_headers,
        "body": body,
    }


class TestPaypalWebhookSignatureVerification:
    """Test that webhook signature verification works correctly."""

    @patch("lambda_function.PAYPAL_WEBHOOK_ID", "")
    def test_returns_401_when_webhook_id_not_configured(self):
        from lambda_function import handle_paypal_webhook

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {"billing_agreement_id": "I-123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "Unauthorized"

    @patch("lambda_function.PAYPAL_WEBHOOK_ID", "WH-123")
    def test_returns_401_when_signature_headers_missing(self):
        from lambda_function import handle_paypal_webhook

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {"billing_agreement_id": "I-123"})
        # Remove required headers
        event["headers"] = {}

        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 401

    @patch("lambda_function._get_paypal_access_token", return_value="mock-token")
    @patch("lambda_function.PAYPAL_WEBHOOK_ID", "WH-123")
    def test_returns_401_when_paypal_verification_fails(self, mock_token):
        """When PayPal returns FAILURE verification status, webhook should be rejected."""
        from lambda_function import handle_paypal_webhook
        import urllib.request

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {"billing_agreement_id": "I-123"})

        # Mock urlopen to return FAILURE verification
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"verification_status": "FAILURE"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = handle_paypal_webhook(event)

        assert result["statusCode"] == 401


class TestPaypalWebhookPaymentCompleted:
    """Test PAYMENT.SALE.COMPLETED handling."""

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.dynamodb")
    def test_clears_grace_period_and_sets_active(self, mock_dynamodb, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom", "commitmentStatus": "grace_period"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {"billing_agreement_id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "PAYMENT.SALE.COMPLETED" in body["message"]

        # Verify DynamoDB update was called correctly
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args
        assert update_call[1]["Key"] == {"email": "user@example.com"}
        assert ":status" in update_call[1]["ExpressionAttributeValues"]
        assert update_call[1]["ExpressionAttributeValues"][":status"] == "active"
        assert "REMOVE commitmentGraceDeadline" in update_call[1]["UpdateExpression"]


class TestPaypalWebhookPaymentDenied:
    """Test PAYMENT.SALE.DENIED handling."""

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.ses_client")
    @patch("lambda_function.dynamodb")
    def test_sets_grace_period_with_7_day_deadline(self, mock_dynamodb, mock_ses, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom", "commitmentStatus": "active"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("PAYMENT.SALE.DENIED", {"billing_agreement_id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200

        # Verify DynamoDB update was called with grace_period status
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args
        assert update_call[1]["ExpressionAttributeValues"][":status"] == "grace_period"

        # Verify the grace deadline is approximately 7 days from now
        deadline_str = update_call[1]["ExpressionAttributeValues"][":deadline"]
        deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (deadline - now).total_seconds()
        # Should be approximately 7 days (604800 seconds), allow 60s tolerance
        assert 604700 < diff < 604900

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.ses_client")
    @patch("lambda_function.dynamodb")
    def test_sends_grace_period_email(self, mock_dynamodb, mock_ses, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom", "commitmentStatus": "active"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("PAYMENT.SALE.DENIED", {"billing_agreement_id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        # Verify SES email was sent
        mock_ses.send_email.assert_called_once()
        email_call = mock_ses.send_email.call_args
        assert email_call[1]["Destination"]["ToAddresses"] == ["user@example.com"]
        assert "Payment Failed" in email_call[1]["Message"]["Subject"]["Data"]


class TestPaypalWebhookSubscriptionExpired:
    """Test BILLING.SUBSCRIPTION.EXPIRED handling."""

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.dynamodb")
    def test_transitions_to_scale_tier(self, mock_dynamodb, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom", "commitmentStatus": "active"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("BILLING.SUBSCRIPTION.EXPIRED", {"id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200

        # Verify DynamoDB update transitions to scale
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args
        assert update_call[1]["ExpressionAttributeValues"][":tier"] == "scale"
        assert update_call[1]["ExpressionAttributeValues"][":status"] == "expired"
        # Verify commitment fields are removed
        assert "REMOVE customTokenAllocation" in update_call[1]["UpdateExpression"]
        assert "commitmentEndDate" in update_call[1]["UpdateExpression"]
        assert "paypalCustomPlanSubId" in update_call[1]["UpdateExpression"]


class TestPaypalWebhookSubscriptionCancelled:
    """Test BILLING.SUBSCRIPTION.CANCELLED handling."""

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.dynamodb")
    def test_logs_warning_and_returns_200(self, mock_dynamodb, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("BILLING.SUBSCRIPTION.CANCELLED", {"id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200
        # update_item should NOT be called for cancellation (just logged)
        mock_table.update_item.assert_not_called()


class TestPaypalWebhookEdgeCases:
    """Test edge cases for the webhook handler."""

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    def test_returns_400_for_invalid_json(self, mock_verify):
        from lambda_function import handle_paypal_webhook

        event = {
            "routeKey": "POST /members/custom-plan/webhook",
            "headers": {},
            "body": "not valid json {{{",
        }
        result = handle_paypal_webhook(event)
        assert result["statusCode"] == 400

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    def test_returns_200_when_no_subscription_id(self, mock_verify):
        from lambda_function import handle_paypal_webhook

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "no subscription_id found" in body["message"]

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.dynamodb")
    def test_returns_200_when_member_not_found(self, mock_dynamodb, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("PAYMENT.SALE.COMPLETED", {"billing_agreement_id": "I-UNKNOWN"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "member not found" in body["message"]

    @patch("lambda_function._verify_paypal_webhook_signature", return_value=True)
    @patch("lambda_function.dynamodb")
    def test_unhandled_event_type_returns_200(self, mock_dynamodb, mock_verify):
        from lambda_function import handle_paypal_webhook

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [{"email": "user@example.com", "tier": "custom"}]
        }
        mock_dynamodb.Table.return_value = mock_table

        event = _make_webhook_event("BILLING.SUBSCRIPTION.ACTIVATED", {"id": "I-SUB123"})
        result = handle_paypal_webhook(event)

        assert result["statusCode"] == 200
        # No update should be called for unrecognized events
        mock_table.update_item.assert_not_called()
