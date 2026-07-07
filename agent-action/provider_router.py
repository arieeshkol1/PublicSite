"""
Provider Router — resolves the cloud provider for an account and dispatches
tool invocations to the appropriate connector.

The routing flow:
1. Look up the account's `cloudProvider` in MemberPortal-Accounts DynamoDB table
2. Load vendor metadata from vendor_registry.json (no hardcoded provider lists)
3. For cost tools (getCostBreakdown, getMonthlyTrend): check Cost_Cache_Table first
   Cache SK prefix = <VENDOR>#<account_id>#<date>  (e.g. AWS#123456789012#2026-07-05)
4. Check if the requested tool is in the connector's SUPPORTED_OPERATIONS
5. Dispatch to the connector method and return the result
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Cost Cache configuration
COST_CACHE_TABLE_NAME = "Cost_Cache_Table"

# Tips table for drilldown plan lookup
TIPS_TABLE_NAME = "ViewMyBill-CostOptimizationTips"

# Tools that benefit from cost cache lookup
CACHEABLE_TOOLS = {"getCostBreakdown", "getMonthlyTrend"}

# Load vendor registry once at cold-start
_REGISTRY_PATH = Path(__file__).parent / "connectors" / "vendor_registry.json"
try:
    with open(_REGISTRY_PATH) as _f:
        _VENDOR_REGISTRY = json.load(_f)["vendors"]
except Exception:
    # Fallback: try relative path (Lambda zip may flatten structure)
    try:
        import os as _os
        _alt_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "connectors", "vendor_registry.json")
        with open(_alt_path) as _f2:
            _VENDOR_REGISTRY = json.load(_f2)["vendors"]
    except Exception as _e2:
        logger.warning(f"vendor_registry.json not found: {_e2} — using empty registry")
        _VENDOR_REGISTRY = {}

VALID_PROVIDERS = set(_VENDOR_REGISTRY.keys()) or {"aws", "azure", "gcp", "openai", "anthropic", "groundcover"}


def _vendor_meta(provider: str) -> dict:
    """Return registry entry for provider, falling back to aws defaults."""
    return _VENDOR_REGISTRY.get(provider, _VENDOR_REGISTRY.get("aws", {}))

# Maps camelCase tool names (from OpenAPI schema) to snake_case connector methods
TOOL_TO_METHOD = {
    "getCostBreakdown": "get_cost_breakdown",
    "getMonthlyTrend": "get_cost_breakdown",
    "getComputeInstances": "get_compute_instances",
    "getDatabaseInstances": "get_database_instances",
    "getServerlessFunctions": "get_serverless_functions",
    "getObjectStorage": "get_object_storage",
    "getStorageVolumes": "get_storage_volumes",
    "getNetworkResources": "get_network_resources",
    "getBudgets": "get_budgets",
    "getFinOpsSettings": "get_finops_settings",
    "getCommitmentCoverage": "get_commitment_coverage",
    "getTagCompliance": "get_tag_compliance",
    "getBusinessMetrics": "get_business_metrics",
    "getCostForecast": "get_cost_forecast",
    "getCostAnomalies": "get_cost_anomalies",
    "getRightsizingRecommendations": "get_rightsizing_recommendations",
    "getSpotCandidates": "get_spot_candidates",
    "getLicensingAnalysis": "get_licensing_analysis",
    "getAIUsage": "get_ai_usage",
    "getOptimizationTips": "get_optimization_tips",
    "getPricingData": "get_pricing_data",
    "getContainerClusters": "get_container_clusters",
}


class AccountNotFoundError(Exception):
    """Raised when the account is not found in MemberPortal-Accounts table."""

    def __init__(self, account_id: str, member_email: str):
        self.account_id = account_id
        self.member_email = member_email
        super().__init__(
            f"Account {account_id} not found for {member_email}. "
            "Add this account via the Configure tab."
        )


class AuthenticationError(Exception):
    """Raised when a Cloud Connector encounters an auth/permissions error."""

    def __init__(self, message: str):
        super().__init__(message)


def _get_dynamodb_resource():
    """Get a DynamoDB resource. Extracted for testability."""
    return boto3.resource("dynamodb")


def resolve_provider(account_id: str, member_email: str) -> str:
    """
    Look up the cloudProvider for an account from the MemberPortal-Accounts table.

    Args:
        account_id: The connected account identifier.
        member_email: The member's email (partition key).

    Returns:
        One of: "aws", "azure", "gcp", "openai". Defaults to "aws" if the value
        is missing or not in the supported set.

    Raises:
        AccountNotFoundError: If no account record exists for the given keys.
    """
    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table("MemberPortal-Accounts")

    try:
        response = table.get_item(
            Key={"memberEmail": member_email, "accountId": account_id}
        )
    except ClientError as e:
        logger.error(f"DynamoDB error looking up account {account_id}: {e}")
        raise

    item = response.get("Item")
    if not item:
        raise AccountNotFoundError(account_id, member_email)

    cloud_provider = item.get("cloudProvider", "")

    if cloud_provider not in VALID_PROVIDERS:
        logger.info(
            f"Account {account_id} has invalid/missing cloudProvider "
            f"'{cloud_provider}', defaulting to 'aws'"
        )
        return "aws"

    return cloud_provider


def _get_connector(provider: str):
    """
    Instantiate and return the connector for the given provider.
    The connector class is resolved from vendor_registry.json so no
    hardcoded provider names live in routing code.
    """
    meta = _vendor_meta(provider)
    connector_path = meta.get("connector", "aws_connector.AWSConnector")
    module_name, class_name = connector_path.rsplit(".", 1)
    try:
        import importlib
        mod = importlib.import_module(f"connectors.{module_name}")
        return getattr(mod, class_name)()
    except Exception as e:
        logger.warning(f"Connector load failed for {provider} ({connector_path}): {e} — falling back to AWSConnector")
        from connectors.aws_connector import AWSConnector
        return AWSConnector()


def _get_cache_table():
    """Get the Cost_Cache_Table DynamoDB Table resource. Extracted for testability."""
    dynamodb = _get_dynamodb_resource()
    return dynamodb.Table(COST_CACHE_TABLE_NAME)


def _cache_sk(provider: str, account_id: str, date_str: str) -> str:
    """Build the cache sort key: <VENDOR>#<account_id>#<YYYY-MM-DD>.
    E.g.  AWS#123456789012#2026-07-05
          OPENAI#openai-org-xxx#2026-07-05
    """
    vendor = _vendor_meta(provider).get("cachePrefix", provider.upper())
    return f"{vendor}#{account_id}#{date_str}"


def _parse_cache_date(sk: str) -> str:
    """Extract the date part from any SK format, new or legacy."""
    # New: VENDOR#accountId#YYYY-MM-DD
    parts = sk.split("#")
    if len(parts) >= 3:
        return parts[-1]
    # Legacy: DAILY#YYYY-MM-DD or COST#YYYY-MM-DD or OPENAI_DAILY#YYYY-MM-DD
    return sk.replace("OPENAI_DAILY#", "").replace("COST#", "").replace("DAILY#", "")


def _read_cost_cache(member_email: str, account_id: str, tool_name: str, params: dict):
    """
    Attempt to read cached cost data from Cost_Cache_Table.

    Cache key format:
      PK = {memberEmail}#{accountId}
      SK = <VENDOR>#<account_id>#<YYYY-MM-DD>   (e.g. AWS#123456789012#2026-07-05)

    Returns:
        tuple: (cached_data, is_fresh)
    """
    try:
        cache_table = _get_cache_table()
        now = datetime.now(timezone.utc)

        try:
            provider = resolve_provider(account_id, member_email)
        except Exception:
            provider = "aws"

        staleness_hours = _vendor_meta(provider).get("staleness_hours", 48)

        if tool_name == "getCostBreakdown":
            first_of_current_month = now.replace(day=1)
            first_of_last_month = (first_of_current_month - timedelta(days=1)).replace(day=1)
            start_date = first_of_last_month
            end_date = now
        else:  # getMonthlyTrend
            months = int(params.get("months", 3))
            end_date = now.replace(day=1)
            start_date = (end_date - timedelta(days=months * 31)).replace(day=1)

        pk = f"{member_email}#{account_id}"
        start_sk = _cache_sk(provider, account_id, start_date.strftime('%Y-%m-%d'))
        end_sk   = _cache_sk(provider, account_id, end_date.strftime('%Y-%m-%d'))

        resp = cache_table.query(
            KeyConditionExpression=Key("pk").eq(pk) & Key("sk").between(start_sk, end_sk)
        )
        items = resp.get("Items", [])

        if not items:
            # Backward compat: try legacy SK prefixes (DAILY#, COST#)
            # Old cache entries predate the VENDOR#accountId#date scheme.
            # Legacy SK prefixes: openai historically used OPENAI_DAILY#, then COST#; cloud uses DAILY#
            _legacy_pfx = "OPENAI_DAILY#" if provider == "openai" else ("COST#" if provider in ("anthropic", "groundcover") else "DAILY#")
            _leg_start = f"{_legacy_pfx}{start_date.strftime('%Y-%m-%d')}"
            _leg_end   = f"{_legacy_pfx}{end_date.strftime('%Y-%m-%d')}"
            try:
                _leg_resp = cache_table.query(
                    KeyConditionExpression=Key("pk").eq(pk) & Key("sk").between(_leg_start, _leg_end)
                )
                items = _leg_resp.get("Items", [])
            except Exception:
                pass
            # Second legacy attempt: if openai OPENAI_DAILY# was empty, try COST#
            if not items and provider == "openai":
                try:
                    _alt_resp = cache_table.query(
                        KeyConditionExpression=Key("pk").eq(pk) & Key("sk").between(
                            f"COST#{start_date.strftime('%Y-%m-%d')}",
                            f"COST#{end_date.strftime('%Y-%m-%d')}"
                        )
                    )
                    items = _alt_resp.get("Items", [])
                except Exception:
                    pass
            if not items:
                return None, False

        staleness_threshold = now - timedelta(hours=staleness_hours)
        most_recent_cached_at = None
        for item in items:
            cached_at_str = item.get("cached_at")
            if cached_at_str:
                try:
                    cached_at = datetime.fromisoformat(cached_at_str)
                    if most_recent_cached_at is None or cached_at > most_recent_cached_at:
                        most_recent_cached_at = cached_at
                except (ValueError, TypeError):
                    pass

        is_fresh = True if most_recent_cached_at is None else (most_recent_cached_at >= staleness_threshold)
        if not is_fresh:
            return None, False

        if tool_name == "getCostBreakdown":
            return _aggregate_cost_breakdown(items, start_date, end_date), True
        else:
            return _aggregate_monthly_trend(items), True

    except Exception as e:
        logger.warning(f"Cost cache read failure for {member_email}#{account_id} ({tool_name}): {e}")
        return None, False


def _aggregate_cost_breakdown(items, start_date, end_date):
    """Aggregate daily cache items into a cost breakdown response.
    
    Returns last 14 days of daily costs and identifies first-of-month fixed charges
    (support, tax, etc.) so forecasting can separate recurring monthly fees from daily usage.
    """
    services = {}
    daily_costs = []
    for item in items:
        cost = float(item.get("cost_amount", 0))
        sk = item["sk"]
        date = _parse_cache_date(sk)
        daily_costs.append({"date": date, "cost": round(cost, 2)})
        for svc, svc_cost in item.get("service_breakdown", {}).items():
            services[svc] = services.get(svc, 0) + float(svc_cost)

    # Sort by date to ensure correct ordering
    daily_costs.sort(key=lambda x: x["date"])

    top_services = sorted(
        [{"service": k, "cost": round(v, 2)} for k, v in services.items()],
        key=lambda x: x["cost"],
        reverse=True,
    )
    total = sum(s["cost"] for s in top_services)

    # Return up to 21 days — enough for week-over-week comparison
    # while keeping response within Bedrock's token limits
    recent_daily = daily_costs[-21:]

    # Identify first-of-month spike: if any day ending in "-01" has cost > 2x median,
    # flag it as containing monthly fixed charges
    costs_values = [d["cost"] for d in recent_daily if d["cost"] > 0]
    median_cost = sorted(costs_values)[len(costs_values) // 2] if costs_values else 0
    first_of_month_charges = 0
    for d in recent_daily:
        if d["date"].endswith("-01") and d["cost"] > median_cost * 2:
            first_of_month_charges = round(d["cost"] - median_cost, 2)
            d["_note"] = f"includes ~${first_of_month_charges} monthly fixed charges (support, tax, etc.)"

    return {
        "totalCost30Days": round(total, 2),
        "topServices": top_services[:7],
        "dailyCosts": recent_daily,
        "period": (
            f"{start_date.strftime('%Y-%m-%d')} to "
            f"{end_date.strftime('%Y-%m-%d')} (from cache)"
        ),
        "source": "cache",
        "forecastHint": {
            "firstOfMonthFixedCharges": first_of_month_charges,
            "medianDailyCost": round(median_cost, 2),
            "taxAndSupportPercent": round((first_of_month_charges / (median_cost * 30 + first_of_month_charges)) * 100, 1) if median_cost > 0 else 0,
            "note": "For forecasting: daily costs on non-1st days EXCLUDE tax/support (billed as lump sum on 1st). To estimate total month: (avg_daily × 30) / (1 - taxSupportPercent/100). Tax and Support are percentages of total spend, not fixed amounts."
        },
    }


def _aggregate_monthly_trend(items):
    """Aggregate daily cache items into a monthly trend response."""
    monthly_data = {}
    for item in items:
        sk = item["sk"]
        date = _parse_cache_date(sk)
        month = date[:7]  # YYYY-MM
        if month not in monthly_data:
            monthly_data[month] = {}
        for svc, svc_cost in item.get("service_breakdown", {}).items():
            cost = float(svc_cost)
            if cost > 0.01:
                monthly_data[month][svc] = round(
                    monthly_data[month].get(svc, 0) + cost, 2
                )

    return {
        "monthlyComparison": monthly_data,
        "months": sorted(monthly_data.keys()),
        "source": "cache",
    }


def _write_cost_cache(member_email: str, account_id: str, tool_name: str, result: dict):
    """
    Write cost data to Cost_Cache_Table after a cache miss.
    SK format: <VENDOR>#<account_id>#<YYYY-MM-DD>  (from vendor_registry cachePrefix)
    """
    try:
        cache_table = _get_cache_table()
        now = datetime.now(timezone.utc)
        pk = f"{member_email}#{account_id}"
        cached_at = now.isoformat()

        try:
            provider = resolve_provider(account_id, member_email)
        except Exception:
            provider = "aws"

        if tool_name == "getCostBreakdown":
            daily_costs = result.get("dailyCosts", [])
            service_breakdown = {}
            for svc in result.get("topServices", result.get("serviceBreakdown", [])):
                svc_name = svc.get("service", svc.get("serviceName", ""))
                svc_cost = svc.get("cost", 0)
                if svc_name:
                    service_breakdown[svc_name] = str(svc_cost)

            for day_entry in daily_costs:
                date = day_entry.get("date", "")
                cost = day_entry.get("cost", 0)
                if date:
                    cache_table.put_item(Item={
                        "pk": pk,
                        "sk": _cache_sk(provider, account_id, date),
                        "cost_amount": str(cost),
                        "service_breakdown": service_breakdown,
                        "cached_at": cached_at,
                    })
        elif tool_name == "getMonthlyTrend":
            monthly_data = result.get("monthlyComparison", {})
            for month, services in monthly_data.items():
                total_cost = sum(float(v) for v in services.values())
                service_breakdown = {k: str(v) for k, v in services.items()}
                cache_table.put_item(Item={
                    "pk": pk,
                    "sk": _cache_sk(provider, account_id, f"{month}-01"),
                    "cost_amount": str(round(total_cost, 2)),
                    "service_breakdown": service_breakdown,
                    "cached_at": cached_at,
                })

        logger.info(f"Cost cache updated for {pk} ({tool_name})")
    except Exception as e:
        logger.warning(f"Cost cache write failure for {member_email}#{account_id} ({tool_name}): {e}")


def _substitute_placeholders(call_params: dict, previous_result: dict) -> dict:
    """
    Replace <each> placeholders in params with values from previous result.

    Example:
      params: {"InstanceIds": "<each>"}
      previous_result: {"Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]}

    The connector extracts the iterable from previous_result and substitutes.
    """
    substituted = {}
    for key, value in call_params.items():
        if value == '<each>':
            substituted[key] = _extract_iterable(previous_result)
        else:
            substituted[key] = value
    return substituted


def _extract_iterable(result: dict) -> list:
    """Extract the primary list from an API response for <each> substitution."""
    for key in result:
        if isinstance(result[key], list) and result[key]:
            return result[key]
    return []


def _resolve_drilldown_plan(service: str, tip_id: str) -> dict:
    """
    Query Tips_Table for the drilldown plan associated with a tip.

    Always queries fresh — no in-memory caching.

    Returns:
        dict with keys:
          - 'plan': list of structured objects or legacy strings
          - 'format': 'structured' or 'legacy'
        OR error dict with 'error' key on failure.
    """
    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(TIPS_TABLE_NAME)

    try:
        response = table.get_item(
            Key={'service': service, 'tipId': tip_id}
        )
    except ClientError as e:
        logger.error(f"DynamoDB error fetching drilldown plan for {service}/{tip_id}: {e}")
        return {'error': 'Unable to fetch drilldown plan', 'retryable': True}

    item = response.get('Item')
    if not item:
        return {
            'error': 'Drilldown plan not found',
            'guidance': f'No drilldown configuration exists for tip {tip_id} in service {service}.'
        }

    drilldown_apis = item.get('drilldownApis', [])
    if not drilldown_apis:
        return {
            'error': 'Drilldown plan not found',
            'guidance': f'Tip {tip_id} exists but has no drilldownApis defined.'
        }

    # Detect format by inspecting first element
    fmt = 'structured' if isinstance(drilldown_apis[0], dict) else 'legacy'

    return {'plan': drilldown_apis, 'format': fmt}


def route_tool(tool_name: str, account_id: str, member_email: str, params: dict) -> dict:
    """
    Resolve the provider for the account, instantiate the correct connector,
    and dispatch the tool invocation.

    For cost tools (getCostBreakdown, getMonthlyTrend), checks Cost_Cache_Table first.
    On cache hit within 24-hour staleness threshold, returns cached data directly.
    On cache miss/stale, invokes the connector and writes result to cache.
    On cache read failure, falls back to live API with a warning log.

    Args:
        tool_name: The camelCase tool name (e.g., "getComputeInstances").
        account_id: The connected account identifier.
        member_email: The member's email.
        params: Additional parameters for the tool call.

    Returns:
        dict: The tool result, or a structured error response.
    """
    # Resolve provider
    try:
        provider = resolve_provider(account_id, member_email)
    except AccountNotFoundError:
        return {
            "error": "Account not connected",
            "guidance": "Add this account via the Configure tab.",
        }
    except ClientError as e:
        logger.error(f"DynamoDB error resolving provider for account {account_id}: {e}")
        return {
            "error": "Unable to look up account information",
            "retryable": True,
            "guidance": "Try again in a moment. If the issue persists, check your account connection in the Configure tab.",
        }

    # Get connector instance
    connector = _get_connector(provider)

    # === Drilldown plan path (triggered by tipId presence) ===
    tip_id = params.get('tipId')
    if tip_id:
        service = params.get('service', '')
        plan_result = _resolve_drilldown_plan(service, tip_id)

        if 'error' in plan_result:
            return plan_result

        plan = plan_result['plan']
        fmt = plan_result['format']

        if fmt == 'structured':
            # Validate and filter malformed entries
            valid_steps = [s for s in plan if s.get('service') and s.get('operation')]
            skipped = len(plan) - len(valid_steps)
            if skipped > 0:
                logger.warning(f"Skipped {skipped} malformed entries in plan for {tip_id}")

            if not valid_steps:
                return {
                    'error': 'All drilldown plan entries are malformed',
                    'healingRequired': True,
                    'tipId': tip_id,
                    'service': service,
                }

            return connector.execute_drilldown_plan(
                account_id, member_email, valid_steps, params
            )
        else:
            # Legacy string-array format — pass to existing connector logic
            return connector.execute_legacy_drilldown(
                account_id, member_email, plan, params
            )

    # Check if tool is supported by this connector
    if tool_name not in connector.SUPPORTED_OPERATIONS:
        return {
            "notSupported": True,
            "message": (
                f"{tool_name} is not applicable for {provider} accounts. "
                f"Available operations: {', '.join(connector.SUPPORTED_OPERATIONS)}"
            ),
            "availableOperations": connector.SUPPORTED_OPERATIONS,
        }

    # For cacheable cost tools, check Cost_Cache_Table first
    # Skip cache when usageTypeBreakdown is requested — cache doesn't have this granularity
    usage_breakdown_requested = params.get('usageTypeBreakdown', '') in ('true', 'True', '1', True)
    if tool_name in CACHEABLE_TOOLS and not usage_breakdown_requested:
        cached_data, is_fresh = _read_cost_cache(member_email, account_id, tool_name, params)
        if cached_data and is_fresh:
            logger.info(
                f"Cost cache hit for {member_email}#{account_id} ({tool_name})"
            )
            return cached_data

    # Resolve the method name
    method_name = TOOL_TO_METHOD.get(tool_name)
    if not method_name:
        return {
            "error": f"Unknown tool: {tool_name}",
            "guidance": "Check available tools in the Chat tab.",
        }

    # Dispatch to the connector method
    method = getattr(connector, method_name, None)
    if not method:
        return {
            "error": f"Connector {provider} does not implement {method_name}",
            "guidance": "This operation may not be fully implemented yet.",
        }

    try:
        result = method(account_id, member_email, params)

        # On successful live invocation for cacheable tools, write to cache
        if tool_name in CACHEABLE_TOOLS and "error" not in result:
            _write_cost_cache(member_email, account_id, tool_name, result)

        return result
    except (ClientError, PermissionError, AuthenticationError) as e:
        error_msg = str(e)
        # Log full details server-side but don't expose to user
        logger.error(
            f"Auth/permission error for {tool_name} on {provider} "
            f"account {account_id}: {error_msg}"
        )
        # For accounts with no live cache yet, provide generic guidance
        return {
            "authError": True,
            "error": "Authentication or permissions error",
            "guidance": "Check your account connection in the Configure tab.",
        }
    except NotImplementedError:
        return {
            "notSupported": True,
            "message": (
                f"{tool_name} is not yet implemented for {provider} accounts."
            ),
            "availableOperations": connector.SUPPORTED_OPERATIONS,
        }
    except Exception as e:
        logger.error(
            f"Provider API error for {tool_name} on {provider} "
            f"account {account_id}: {e}"
        )
        return {
            "error": "Provider API error",
            "retryable": True,
            "guidance": "Try again in a moment. If the issue persists, check your account connection in the Configure tab.",
        }
# Deploy trigger


