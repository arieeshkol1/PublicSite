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
    """AWS cloud provider connector - Cost Explorer and Compute Optimizer.

    IMPORTANT (cost-safety): all cost/recommendation API calls MUST run against
    the *customer's* account using their cross-account role credentials — never
    the platform's own credentials. We therefore assume the customer role here
    and pass the temporary credentials to every client. If credentials cannot be
    resolved we return empty data rather than silently falling back to the
    platform account (which would bill the platform's Cost Explorer).
    """

    def __init__(self):
        self._creds_cache = {}

    def _customer_credentials(self, account_context):
        """Resolve cross-account (customer) STS credentials, cached per account.

        Returns a credentials dict (AccessKeyId/SecretAccessKey/SessionToken) or
        None if the role could not be assumed. Never returns platform creds.
        """
        acct = account_context.account_id
        if acct in self._creds_cache:
            return self._creds_cache[acct]
        try:
            import sts_assume_role
            creds = sts_assume_role.assume_role(
                acct, account_context.member_email, session_name='SlashMyBillAgentCost'
            )
            self._creds_cache[acct] = creds
            return creds
        except Exception as e:
            logger.error(
                f"Could not assume customer role for account {acct}; "
                f"skipping live cost API to avoid billing the platform. Error: {e}"
            )
            self._creds_cache[acct] = None
            return None

    @staticmethod
    def _client(service, creds, region="us-east-1"):
        return boto3.client(
            service,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=region,
        )

    def get_cost_data(
        self,
        account_context: AccountContext,
        timeframe: str,
        granularity: str = "MONTHLY",
    ) -> dict[str, Any]:
        """Query the CUSTOMER's AWS Cost Explorer for cost data (cache is checked
        upstream by the behavioral router; this is the priority-2 fallback)."""
        creds = self._customer_credentials(account_context)
        if not creds:
            return {"cost_by_service": [], "source": "unavailable", "timeframe": timeframe,
                    "note": "Customer connection unavailable; no cost data retrieved."}
        try:
            ce_client = self._client("ce", creds)

            start_date, end_date = _parse_timeframe(timeframe)

            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity=granularity,
                Metrics=["UnblendedCost", "UsageQuantity"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            return {
                "cost_by_service": _parse_cost_results(response),
                "source": "cost_explorer",
                "timeframe": timeframe,
            }
        except Exception as e:
            logger.error(f"Customer Cost Explorer query failed: {e}")
            return {"cost_by_service": [], "source": "error", "timeframe": timeframe,
                    "note": "Cost data temporarily unavailable from the customer connection."}

    def get_resource_recommendations(
        self,
        account_context: AccountContext,
        service: str,
    ) -> dict[str, Any]:
        """Query the CUSTOMER's AWS Compute Optimizer for rightsizing recommendations."""
        creds = self._customer_credentials(account_context)
        if not creds:
            return {"recommendations": [], "source": "unavailable"}
        try:
            co_client = self._client("compute-optimizer", creds)

            if service == "ec2":
                response = co_client.get_ec2_instance_recommendations(maxResults=10)
                return {
                    "recommendations": response.get("instanceRecommendations", []),
                    "source": "compute_optimizer",
                }
            return {"recommendations": [], "source": "compute_optimizer"}
        except Exception as e:
            logger.error(f"Customer Compute Optimizer query failed: {e}")
            return {"recommendations": [], "source": "error"}

    def get_historical_costs(
        self,
        account_context: AccountContext,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Get daily cost history from the CUSTOMER's account for forecasting."""
        creds = self._customer_credentials(account_context)
        if not creds:
            return []
        try:
            from datetime import datetime, timedelta, timezone

            ce_client = self._client("ce", creds)
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )

            daily_costs = []
            for result in response.get("ResultsByTime", []):
                daily_costs.append({
                    "date": result["TimePeriod"]["Start"],
                    "cost": float(result["Total"]["UnblendedCost"]["Amount"]),
                })
            return daily_costs
        except Exception as e:
            logger.error(f"Customer historical costs query failed: {e}")
            return []


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
