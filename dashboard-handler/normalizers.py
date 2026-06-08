"""Cross-provider data normalization for the Widget Builder Dashboard.

Provides normalization functions that transform raw provider data into a
common schema: date, service_name, cost_amount, currency, cloud_provider,
account_id. Supports AWS (Cost_Cache_Table service_breakdown), Azure
(Azure Cost Mgmt API), GCP (GCP Billing API), and OpenAI (usage API).

Also provides a multi_provider_query function that handles partial failures
gracefully, returning available data from successful providers with error
indicators for failed ones.

Requirements: 10.1, 10.2, 10.3, 10.4, 11.3
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common normalized record fields
NORMALIZED_FIELDS = frozenset([
    "date",
    "service_name",
    "cost_amount",
    "currency",
    "cloud_provider",
    "account_id",
])


def normalize_aws_data(raw_items: list[dict], account_id: str = "") -> list[dict]:
    """Normalize AWS Cost_Cache_Table data into common schema.

    Transforms raw DynamoDB items with service_breakdown dicts into
    flat normalized records. Each service in the breakdown becomes a
    separate record.

    Args:
        raw_items: Raw items from Cost_Cache_Table. Each item may have:
            - sk: Sort key like "DAILY#YYYY-MM-DD"
            - service_breakdown: Dict of {service_name: cost_amount}
            - total_cost: Fallback if no service_breakdown
            - currency: Currency code (defaults to "USD")
            - cloud_provider: Provider identifier (defaults to "aws")
        account_id: The AWS account ID for these items.

    Returns:
        List of normalized dicts with fields: date, service_name,
        cost_amount, currency, cloud_provider, account_id.
    """
    normalized = []

    for item in raw_items:
        sk = item.get("sk", "")
        date_str = sk.replace("DAILY#", "") if sk.startswith("DAILY#") else item.get("date", "")
        currency = item.get("currency", "USD")
        cloud_provider = item.get("cloud_provider", "aws")
        item_account_id = item.get("account_id", account_id)

        service_breakdown = item.get("service_breakdown", {})

        if service_breakdown and isinstance(service_breakdown, dict):
            for service_name, cost_value in service_breakdown.items():
                normalized.append({
                    "date": date_str,
                    "service_name": service_name,
                    "cost_amount": _safe_float(cost_value),
                    "currency": currency,
                    "cloud_provider": cloud_provider,
                    "account_id": item_account_id,
                })
        else:
            # Fallback: use total_cost as a single record
            total_cost = item.get("total_cost", item.get("cost_amount", 0))
            service_name = item.get("service_name", item.get("service", "_total"))
            normalized.append({
                "date": date_str,
                "service_name": service_name,
                "cost_amount": _safe_float(total_cost),
                "currency": currency,
                "cloud_provider": cloud_provider,
                "account_id": item_account_id,
            })

    return normalized


def normalize_azure_data(raw_items: list[dict], account_id: str = "") -> list[dict]:
    """Normalize Azure Cost Management API data into common schema.

    Transforms Azure cost data (from Azure Cost Management API responses)
    into the common normalized schema. Azure data typically includes fields
    like usageDate, serviceName/meterCategory, cost/pretaxCost, and
    subscriptionId.

    Args:
        raw_items: Raw items from Azure Cost Management API. Expected fields:
            - usageDate or date: Usage date (YYYY-MM-DD or YYYYMMDD format)
            - serviceName or meterCategory or service_name: Service identifier
            - cost or pretaxCost or costInBillingCurrency: Cost amount
            - currency or billingCurrency: Currency code
            - subscriptionId or account_id: Azure subscription ID
        account_id: Default account/subscription ID if not in item.

    Returns:
        List of normalized dicts with fields: date, service_name,
        cost_amount, currency, cloud_provider, account_id.
    """
    normalized = []

    for item in raw_items:
        # Extract date - Azure may use various date field names/formats
        date_str = _extract_azure_date(item)

        # Extract service name - Azure uses various field names
        service_name = (
            item.get("serviceName")
            or item.get("meterCategory")
            or item.get("service_name")
            or item.get("service")
            or "azure_service"
        )

        # Extract cost - Azure uses various cost field names
        cost_value = (
            item.get("cost")
            if item.get("cost") is not None
            else item.get("pretaxCost")
            if item.get("pretaxCost") is not None
            else item.get("costInBillingCurrency")
            if item.get("costInBillingCurrency") is not None
            else item.get("cost_amount", 0)
        )

        # Extract currency
        currency = (
            item.get("currency")
            or item.get("billingCurrency")
            or "USD"
        )

        # Extract account/subscription ID
        item_account_id = (
            item.get("subscriptionId")
            or item.get("account_id")
            or account_id
        )

        normalized.append({
            "date": date_str,
            "service_name": service_name,
            "cost_amount": _safe_float(cost_value),
            "currency": currency,
            "cloud_provider": "azure",
            "account_id": item_account_id,
        })

    return normalized


def normalize_gcp_data(raw_items: list[dict], account_id: str = "") -> list[dict]:
    """Normalize GCP Billing API data into common schema.

    Transforms GCP billing data (from BigQuery billing export or GCP
    Billing API) into the common normalized schema. GCP data typically
    includes fields like usage_start_time, service.description, cost,
    and project.id.

    Args:
        raw_items: Raw items from GCP Billing API. Expected fields:
            - usage_start_time or usageStartTime or date: Usage date
            - service.description or service_description or service_name: Service
            - cost or cost_amount: Cost amount
            - currency or currency_code: Currency code
            - project.id or project_id or account_id: GCP project ID
        account_id: Default project/account ID if not in item.

    Returns:
        List of normalized dicts with fields: date, service_name,
        cost_amount, currency, cloud_provider, account_id.
    """
    normalized = []

    for item in raw_items:
        # Extract date - GCP may use timestamps or date strings
        date_str = _extract_gcp_date(item)

        # Extract service name - GCP uses nested or flat fields
        service_obj = item.get("service")
        if isinstance(service_obj, dict):
            service_name = service_obj.get("description", "gcp_service")
        elif isinstance(service_obj, str) and service_obj:
            service_name = service_obj
        else:
            service_name = (
                item.get("service_description")
                or item.get("service_name")
                or "gcp_service"
            )

        # Extract cost
        cost_value = item.get("cost", item.get("cost_amount", 0))

        # Extract currency
        currency = (
            item.get("currency")
            or item.get("currency_code")
            or "USD"
        )

        # Extract project/account ID - GCP uses nested or flat fields
        project_obj = item.get("project", {})
        if isinstance(project_obj, dict):
            item_account_id = project_obj.get("id", account_id)
        else:
            item_account_id = (
                item.get("project_id")
                or item.get("account_id")
                or account_id
            )

        normalized.append({
            "date": date_str,
            "service_name": service_name,
            "cost_amount": _safe_float(cost_value),
            "currency": currency,
            "cloud_provider": "gcp",
            "account_id": item_account_id,
        })

    return normalized


def normalize_openai_data(raw_items: list[dict], account_id: str = "") -> list[dict]:
    """Normalize OpenAI usage API data into common schema.

    Transforms OpenAI usage data into the common normalized schema.
    OpenAI data typically includes fields like date, model (as service),
    cost/amount, and organization_id.

    Args:
        raw_items: Raw items from OpenAI usage API. Expected fields:
            - date: Usage date (YYYY-MM-DD format)
            - model or service or service_name: Model/service identifier
            - cost or amount or cost_amount: Cost amount
            - organization_id or account_id: OpenAI organization ID
        account_id: Default organization ID if not in item.

    Returns:
        List of normalized dicts with fields: date, service_name,
        cost_amount, currency, cloud_provider, account_id.
    """
    normalized = []

    for item in raw_items:
        # Extract date
        date_str = item.get("date", "")

        # Extract service/model name
        service_name = (
            item.get("model")
            or item.get("service")
            or item.get("service_name")
            or "openai"
        )

        # Extract cost
        cost_value = (
            item.get("cost")
            if item.get("cost") is not None
            else item.get("amount")
            if item.get("amount") is not None
            else item.get("cost_amount", 0)
        )

        # Extract account/org ID
        item_account_id = (
            item.get("organization_id")
            or item.get("account_id")
            or account_id
        )

        normalized.append({
            "date": date_str,
            "service_name": service_name,
            "cost_amount": _safe_float(cost_value),
            "currency": "USD",  # OpenAI bills in USD
            "cloud_provider": "openai",
            "account_id": item_account_id,
        })

    return normalized


def multi_provider_query(
    provider_fetchers: dict[str, callable],
) -> dict:
    """Execute queries across multiple providers with graceful partial failure.

    Calls each provider's fetch function and collects results. If a provider
    fails, its error is captured and data from successful providers is still
    returned. This enables cross-provider queries to degrade gracefully.

    Args:
        provider_fetchers: Dict mapping provider names to callables that
            return list[dict] of normalized data. Each callable takes no args
            (use functools.partial or lambdas to bind parameters).

            Example:
                {
                    "aws": lambda: normalize_aws_data(fetch_aws_data(...), "acc1"),
                    "azure": lambda: normalize_azure_data(fetch_azure_data(...), "acc2"),
                    "gcp": lambda: normalize_gcp_data(fetch_gcp_data(...), "proj1"),
                    "openai": lambda: normalize_openai_data(fetch_openai_data(...), "org1"),
                }

    Returns:
        Dict with:
            - data: list[dict] - Combined normalized data from all successful providers
            - failed_providers: list[dict] - List of {provider, error} for failed providers
            - successful_providers: list[str] - Names of providers that returned data
            - partial: bool - True if any provider failed (indicates partial results)
    """
    combined_data: list[dict] = []
    failed_providers: list[dict] = []
    successful_providers: list[str] = []

    for provider_name, fetcher in provider_fetchers.items():
        try:
            provider_data = fetcher()
            if provider_data is not None:
                combined_data.extend(provider_data)
                successful_providers.append(provider_name)
            else:
                successful_providers.append(provider_name)
        except TimeoutError as e:
            logger.warning(
                f"Provider {provider_name} timed out: {e}"
            )
            failed_providers.append({
                "provider": provider_name,
                "error": f"Timeout: {str(e)}",
            })
        except Exception as e:
            logger.warning(
                f"Provider {provider_name} failed: {e}"
            )
            failed_providers.append({
                "provider": provider_name,
                "error": str(e),
            })

    return {
        "data": combined_data,
        "failed_providers": failed_providers,
        "successful_providers": successful_providers,
        "partial": len(failed_providers) > 0,
    }


def is_normalized(record: dict) -> bool:
    """Check if a record conforms to the common normalized schema.

    Validates that the record has all required fields with appropriate types.

    Args:
        record: A data record to validate.

    Returns:
        True if the record has all required normalized fields.
    """
    if not isinstance(record, dict):
        return False

    for field in NORMALIZED_FIELDS:
        if field not in record:
            return False

    # Validate types
    if not isinstance(record.get("date"), str):
        return False
    if not isinstance(record.get("service_name"), str):
        return False
    if not isinstance(record.get("cost_amount"), (int, float)):
        return False
    if not isinstance(record.get("currency"), str):
        return False
    if not isinstance(record.get("cloud_provider"), str):
        return False
    if not isinstance(record.get("account_id"), str):
        return False

    return True


# --- Private helper functions ---


def _safe_float(value: Any) -> float:
    """Safely convert a value to float.

    Handles Decimal, string, int, float, and None values.

    Args:
        value: The value to convert.

    Returns:
        Float representation of the value, or 0.0 if conversion fails.
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_azure_date(item: dict) -> str:
    """Extract and normalize date from Azure cost data.

    Azure may provide dates in various formats:
    - usageDate: YYYYMMDD integer or string
    - date: YYYY-MM-DD string
    - properties.date: Nested date field

    Args:
        item: Raw Azure cost item.

    Returns:
        Date string in YYYY-MM-DD format, or empty string if not found.
    """
    # Try usageDate (Azure format may be YYYYMMDD)
    usage_date = item.get("usageDate") or item.get("usage_date")
    if usage_date:
        date_str = str(usage_date)
        # Convert YYYYMMDD to YYYY-MM-DD
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    # Try standard date field
    date_val = item.get("date", "")
    if date_val:
        return str(date_val)

    # Try nested properties
    properties = item.get("properties", {})
    if isinstance(properties, dict) and "date" in properties:
        return str(properties["date"])

    return ""


def _extract_gcp_date(item: dict) -> str:
    """Extract and normalize date from GCP billing data.

    GCP may provide dates as:
    - usage_start_time: ISO timestamp (YYYY-MM-DDTHH:MM:SSZ)
    - usageStartTime: Camel case variant
    - date: Simple date string
    - export_time: BigQuery export timestamp

    Args:
        item: Raw GCP billing item.

    Returns:
        Date string in YYYY-MM-DD format, or empty string if not found.
    """
    # Try usage_start_time (may be ISO timestamp)
    usage_time = (
        item.get("usage_start_time")
        or item.get("usageStartTime")
        or item.get("usage_start_date")
    )
    if usage_time:
        date_str = str(usage_time)
        # Extract YYYY-MM-DD from ISO timestamp
        if "T" in date_str:
            return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str

    # Try standard date field
    date_val = item.get("date", "")
    if date_val:
        return str(date_val)[:10]

    # Try export_time
    export_time = item.get("export_time", "")
    if export_time:
        date_str = str(export_time)
        if "T" in date_str:
            return date_str.split("T")[0]
        return date_str[:10] if len(date_str) >= 10 else date_str

    return ""
