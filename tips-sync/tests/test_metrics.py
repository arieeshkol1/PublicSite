"""Unit tests for tips-sync/metrics.py."""

from unittest.mock import MagicMock, patch

import pytest

from metrics import (
    NAMESPACE,
    _publish_metric,
    publish_failure_metric,
    publish_success_metrics,
)


class TestPublishMetric:
    """Tests for the _publish_metric helper."""

    def test_calls_put_metric_data_with_correct_params(self):
        """Publishes metric with correct namespace, name, value, and unit."""
        client = MagicMock()

        _publish_metric(client, "TestMetric", 42, "Count")

        client.put_metric_data.assert_called_once_with(
            Namespace="SlashMyBill/TipsSync",
            MetricData=[
                {
                    "MetricName": "TestMetric",
                    "Value": 42,
                    "Unit": "Count",
                }
            ],
        )

    def test_does_not_raise_on_client_error(self):
        """Gracefully handles errors without raising."""
        client = MagicMock()
        client.put_metric_data.side_effect = Exception("CloudWatch unavailable")

        # Should not raise
        _publish_metric(client, "TestMetric", 1, "Count")

    def test_uses_correct_namespace(self):
        """Namespace is always SlashMyBill/TipsSync."""
        assert NAMESPACE == "SlashMyBill/TipsSync"


class TestPublishSuccessMetrics:
    """Tests for publish_success_metrics."""

    @patch("metrics._get_cloudwatch_client")
    def test_publishes_success_and_duration_metrics(self, mock_get_client):
        """Publishes both TipsSyncSuccess and TipsSyncDuration."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        publish_success_metrics(1500)

        calls = mock_client.put_metric_data.call_args_list
        assert len(calls) == 2

        # First call: TipsSyncSuccess
        success_call = calls[0]
        assert success_call.kwargs["Namespace"] == "SlashMyBill/TipsSync"
        assert success_call.kwargs["MetricData"][0]["MetricName"] == "TipsSyncSuccess"
        assert success_call.kwargs["MetricData"][0]["Value"] == 1
        assert success_call.kwargs["MetricData"][0]["Unit"] == "Count"

        # Second call: TipsSyncDuration
        duration_call = calls[1]
        assert duration_call.kwargs["Namespace"] == "SlashMyBill/TipsSync"
        assert duration_call.kwargs["MetricData"][0]["MetricName"] == "TipsSyncDuration"
        assert duration_call.kwargs["MetricData"][0]["Value"] == 1500
        assert duration_call.kwargs["MetricData"][0]["Unit"] == "Milliseconds"

    @patch("metrics._get_cloudwatch_client")
    def test_does_not_raise_on_failure(self, mock_get_client):
        """Metric publishing failure does not propagate."""
        mock_client = MagicMock()
        mock_client.put_metric_data.side_effect = Exception("Network error")
        mock_get_client.return_value = mock_client

        # Should not raise
        publish_success_metrics(500)


class TestPublishFailureMetric:
    """Tests for publish_failure_metric."""

    @patch("metrics._get_cloudwatch_client")
    def test_publishes_failure_metric(self, mock_get_client):
        """Publishes TipsSyncFailure with value 1."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        publish_failure_metric()

        mock_client.put_metric_data.assert_called_once_with(
            Namespace="SlashMyBill/TipsSync",
            MetricData=[
                {
                    "MetricName": "TipsSyncFailure",
                    "Value": 1,
                    "Unit": "Count",
                }
            ],
        )

    @patch("metrics._get_cloudwatch_client")
    def test_does_not_raise_on_failure(self, mock_get_client):
        """Metric publishing failure does not propagate."""
        mock_client = MagicMock()
        mock_client.put_metric_data.side_effect = Exception("Service error")
        mock_get_client.return_value = mock_client

        # Should not raise
        publish_failure_metric()
