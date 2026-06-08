"""
Vendor-neutral cloud connector interfaces.

The CloudConnector base class defines the contract that all provider-specific
connectors (AWS, Azure, GCP, AI vendor) must implement. Each method corresponds
to a vendor-neutral tool operation and raises NotImplementedError by default.
Provider connectors override the methods they support and list them in
SUPPORTED_OPERATIONS.
"""

from abc import ABC


class CloudConnector(ABC):
    """
    Base class for all cloud provider connectors.

    Each connector implements the tool methods it supports and declares them
    in SUPPORTED_OPERATIONS. The Provider Router uses SUPPORTED_OPERATIONS to
    determine if a tool call is valid for a given provider before dispatching.
    """

    # Subclasses MUST override this with the list of operation names they support.
    # Operation names use the camelCase tool names from the OpenAPI schema, e.g.:
    # ["getComputeInstances", "getCostBreakdown", "getDatabaseInstances", ...]
    SUPPORTED_OPERATIONS: list[str] = []

    # ─── Cost Analysis ────────────────────────────────────────────────────

    def get_cost_breakdown(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cost breakdown by service for a given time period.

        Returns raw provider-specific data (normalization applied upstream).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_cost_breakdown"
        )

    def get_cost_forecast(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get projected cost forecast for the specified number of days.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_cost_forecast"
        )

    def get_cost_anomalies(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Detect unusual cost spikes or drops for the account.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_cost_anomalies"
        )

    # ─── Compute & Optimize ───────────────────────────────────────────────

    def get_compute_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List compute instances (VMs) across all regions/zones.

        Returns raw provider-specific data (normalization applied upstream).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_compute_instances"
        )

    def get_rightsizing_recommendations(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get rightsizing recommendations for underutilized compute resources.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_rightsizing_recommendations"
        )

    def get_spot_candidates(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Identify workloads that are candidates for spot/preemptible instances.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_spot_candidates"
        )

    def get_licensing_analysis(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Analyze software licensing costs and optimization opportunities.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_licensing_analysis"
        )

    # ─── Database & Storage ───────────────────────────────────────────────

    def get_database_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List managed database instances.

        Returns raw provider-specific data (normalization applied upstream).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_database_instances"
        )

    def get_storage_volumes(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List block storage volumes (EBS, Azure Disks, Persistent Disks).

        Returns raw provider-specific data (normalization applied upstream).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_storage_volumes"
        )

    def get_object_storage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List object storage buckets/containers (S3, Blob Storage, GCS).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_object_storage"
        )

    # ─── Network & Serverless ─────────────────────────────────────────────

    def get_network_resources(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List network resources (NAT gateways, load balancers, elastic IPs, etc.).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_network_resources"
        )

    def get_serverless_functions(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List serverless functions (Lambda, Azure Functions, Cloud Functions).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_serverless_functions"
        )

    def get_container_clusters(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List container orchestration clusters (EKS, AKS, GKE).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_container_clusters"
        )

    # ─── FinOps Platform ──────────────────────────────────────────────────

    def get_budgets(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List budgets and budget utilization for the account.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_budgets"
        )

    def get_finops_settings(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get FinOps settings and healthcheck results for the account.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_finops_settings"
        )

    def get_commitment_coverage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get reserved instance / savings plan commitment coverage analysis.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_commitment_coverage"
        )

    def get_tag_compliance(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get tag compliance status for resources in the account.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_tag_compliance"
        )

    def get_business_metrics(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get business metrics (unit economics, cost per customer, etc.).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_business_metrics"
        )

    # ─── Knowledge ────────────────────────────────────────────────────────

    def get_optimization_tips(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get optimization tips from the knowledge base, optionally filtered by service.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_optimization_tips"
        )

    def get_pricing_data(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Query real-time pricing data for the provider's services.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_pricing_data"
        )

    def get_ai_vendor_usage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get AI vendor usage data (tokens, model costs, total spend).
        Only applicable for AI vendor accounts (OpenAI, Anthropic, etc.).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_ai_vendor_usage"
        )
