"""
CloudWatch metrics publisher.

Publishes sync success/failure metrics and duration
to the SlashMyBill/TipsSync namespace.
"""

import json
import logging

import boto3

logger = logging.getLogger(__name__)

NAMESPACE = "SlashMyBill/TipsSync"


def _get_cloudwatch_client():
    """Create and return a CloudWatch client."""
    return boto3.client("cloudwatch", region_name="us-east-1")


def _publish_metric(client, metric_name: str, value: float, unit: str) -> None:
    """Publish a single metric to the SlashMyBill/TipsSync CloudWatch namespace.

    Handles errors gracefully — metric publishing failure should not
    break the sync process.

    Args:
        client: boto3 CloudWatch client.
        metric_name: Name of the metric (e.g., "TipsSyncSuccess").
        value: Metric value.
        unit: CloudWatch unit (e.g., "Count", "Milliseconds").
    """
    try:
        client.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": unit,
                }
            ],
        )
        logger.info(
            json.dumps(
                {
                    "event": "metric_published",
                    "metric_name": metric_name,
                    "value": value,
                    "unit": unit,
                    "namespace": NAMESPACE,
                }
            )
        )
    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "event": "metric_publish_failed",
                    "metric_name": metric_name,
                    "error": str(e),
                    "namespace": NAMESPACE,
                }
            )
        )


def publish_success_metrics(duration_ms: int) -> None:
    """Publish success metrics after a completed sync run.

    Publishes two metrics:
    - TipsSyncSuccess (Count=1): Indicates a successful sync execution.
    - TipsSyncDuration (Milliseconds): Total execution duration.

    Args:
        duration_ms: Sync execution duration in milliseconds.
    """
    client = _get_cloudwatch_client()
    _publish_metric(client, "TipsSyncSuccess", 1, "Count")
    _publish_metric(client, "TipsSyncDuration", duration_ms, "Milliseconds")


def publish_failure_metric() -> None:
    """Publish failure metric when an unrecoverable error prevents sync completion.

    Publishes TipsSyncFailure (Count=1) to signal that the sync run failed
    and operator attention may be needed.
    """
    client = _get_cloudwatch_client()
    _publish_metric(client, "TipsSyncFailure", 1, "Count")
