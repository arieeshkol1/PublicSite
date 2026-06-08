"""Provider connectors abstraction - routes to cloud provider APIs."""
from __future__ import annotations

import logging
from typing import Any

import boto3

from .models import AccountContext

logger = logging.getLogger(__name__)


def get_connector(cloud_provider: str):
    """Get the appropriate connector for the cloud provider."""
    connectors = {
        "aws": AWSConnector,
        "azure": AzureConnector,
        "gcp": GCPConnector,
    }
    connector_class = connectors.get(cloud_provider.lower())
    if not connector_class:
        raise ValueError(f"Unsupported cloud provider: {cloud_provider}")
    return connector_class()


class AWSConnector:
    """AWS cloud provider connector - Cost Explorer and Compute Optimizer."""

    def get_cost_data(
        self,
        account_context: AccountContext,
        timeframe: str,
        granularity: str = "MONTHLY",
    ) -> dict[str, Any]:
        """Query AWS Cost Explorer for cost data."""
        try:
            ce_client = boto3.client("ce", region_name="us-east-1")

            start_date, end_date = _parse_timeframe(timeframe)

            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity=granularity,
                Metrics=["UnblendedCost", "UsageQuantity"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                Filter={
                    "Dimensions": {
                        "Key": "LINKED_ACCOUNT",
                        "Values": [account_context.account_id],
                    }
                },
            )

            return {
                "cost_by_service": _parse_cost_results(response),
                "source": "cost_explorer",
                "timeframe": timeframe,
            }
        except Exception as e:
            logger.error(f"AWS Cost Explorer query failed: {e}")
            raise

    def get_resource_recommendations(
        self,
        account_context: AccountContext,
        service: str,
    ) -> dict[str, Any]:
        """Query AWS Compute Optimizer for rightsizing recommendations."""
        try:
            co_client = boto3.client("compute-optimizer", region_name="us-east-1")

            if service == "ec2":
                response = co_client.get_ec2_instance_recommendations(
                    accountIds=[account_context.account_id],
                    maxResults=10,
                )
                return {
                    "recommendations": response.get("instanceRecommendations", []),
                    "source": "compute_optimizer",
                }
            return {"recommendations": [], "source": "compute_optimizer"}
        except Exception as e:
            logger.error(f"AWS Compute Optimizer query failed: {e}")
            raise

    def get_historical_costs(
        self,
        account_context: AccountContext,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get daily cost history for forecasting."""
        try:
            from datetime import datetime, timedelta, timezone

            ce_client = boto3.client("ce", region_name="us-east-1")
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                Filter={
                    "Dimensions": {
                        "Key": "LINKED_ACCOUNT",
                        "Values": [account_context.account_id],
                    }
                },
            )

            daily_costs = []
            for result in response.get("ResultsByTime", []):
                daily_costs.append({
                    "date": result["TimePeriod"]["Start"],
                    "cost": float(result["Total"]["UnblendedCost"]["Amount"]),
                })
            return daily_costs
        except Exception as e:
            logger.error(f"AWS historical costs query failed: {e}")
            raise


class AzureConnector:
    """Azure cloud provider connector - stub implementation."""

    def get_cost_data(
        self,
        account_context: AccountContext,
        timeframe: str,
        granularity: str = "Monthly",
    ) -> dict[str, Any]:
        """Query Azure Cost Management for cost data (stub)."""
        logger.info(f"Azure cost data query for {account_context.account_id} - stub")
        return {
            "cost_by_service": [],
            "source": "azure_cost_management",
            "timeframe": timeframe,
            "note": "Azure connector not yet implemented",
        }

    def get_resource_recommendations(
        self,
        account_context: AccountContext,
        service: str,
    ) -> dict[str, Any]:
        """Query Azure Advisor for recommendations (stub)."""
        return {
            "recommendations": [],
            "source": "azure_advisor",
            "note": "Azure connector not yet implemented",
        }

    def get_historical_costs(
        self,
        account_context: AccountContext,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get daily cost history (stub)."""
        return []


class GCPConnector:
    """GCP cloud provider connector - stub implementation."""

    def get_cost_data(
        self,
        account_context: AccountContext,
        timeframe: str,
        granularity: str = "MONTHLY",
    ) -> dict[str, Any]:
        """Query GCP BigQuery billing export (stub)."""
        logger.info(f"GCP cost data query for {account_context.account_id} - stub")
        return {
            "cost_by_service": [],
            "source": "bigquery_billing",
            "timeframe": timeframe,
            "note": "GCP connector not yet implemented",
        }

    def get_resource_recommendations(
        self,
        account_context: AccountContext,
        service: str,
    ) -> dict[str, Any]:
        """Query GCP Recommender (stub)."""
        return {
            "recommendations": [],
            "source": "gcp_recommender",
            "note": "GCP connector not yet implemented",
        }

    def get_historical_costs(
        self,
        account_context: AccountContext,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get daily cost history (stub)."""
        return []


def _parse_timeframe(timeframe: str) -> tuple[str, str]:
    """Convert timeframe string to start/end dates."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    if timeframe == "last-7d":
        start = now - timedelta(days=7)
    elif timeframe == "last-90d":
        start = now - timedelta(days=90)
    elif timeframe == "last-30d":
        start = now - timedelta(days=30)
    else:
        # Default to last 30 days
        start = now - timedelta(days=30)

    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def _parse_cost_results(response: dict) -> list[dict[str, Any]]:
    """Parse Cost Explorer response into simplified cost-by-service list."""
    costs = {}
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            costs[service] = costs.get(service, 0) + amount

    return [
        {"service": service, "cost": round(cost, 2)}
        for service, cost in sorted(costs.items(), key=lambda x: x[1], reverse=True)
    ]
