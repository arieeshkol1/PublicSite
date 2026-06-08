"""Behavioral router - executes data-gathering strategies by intent type."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import boto3

from .models import AccountContext, SessionState, ClassificationResult
from .provider_connectors import get_connector
from .constants import (
    COST_CACHE_TABLE,
    TIPS_TABLE,
    CACHE_STALENESS_THRESHOLD_SECONDS,
    FORECAST_MAX_MONTHS,
)

logger = logging.getLogger(__name__)


def execute_by_intent(
    intent: ClassificationResult,
    account_context: AccountContext,
    session: SessionState,
) -> dict[str, Any]:
    """Route to the appropriate behavioral routine based on intent type."""
    intent_type = intent.intent_type

    if intent_type == "Cost_Analysis_General":
        return execute_cost_analysis_general(account_context, session)
    elif intent_type == "Cost_Analysis_Specific":
        return execute_cost_analysis_specific(account_context, intent.target_scope)
    elif intent_type == "Optimization_Tips":
        return execute_optimization_tips(account_context, intent.target_scope)
    elif intent_type == "Forecasting":
        return execute_forecasting(account_context, intent.timeframe, scenario=None)
    else:
        return execute_cost_analysis_general(account_context, session)


def execute_cost_analysis_general(
    account_context: AccountContext,
    session: SessionState,
) -> dict[str, Any]:
    """General cost analysis - query cache first, fallback to API.

    Strategy: Cost_Cache_Table → Cost Explorer API
    """
    timeframe = session.active_timeframe or "last-30d"
    results: dict[str, Any] = {"sources": [], "data": {}}

    # Try cache first
    cache_data = _query_cache(account_context.account_id, timeframe)
    if cache_data:
        logger.info(f"Cache HIT for {account_context.account_id}/{timeframe}")
        results["data"] = cache_data
        results["sources"].append("cache")
        results["retrieval_path"] = "cache_hit"
        return results

    # Cache miss - query API
    logger.info(f"Cache MISS for {account_context.account_id}/{timeframe}, querying API")
    try:
        connector = get_connector(account_context.cloud_provider)
        api_data = connector.get_cost_data(account_context, timeframe)
        results["data"] = api_data
        results["sources"].append("api")
        results["retrieval_path"] = "cache_miss_api_fallback"

        # Write back to cache
        _write_cache(account_context.account_id, timeframe, api_data)
    except Exception as e:
        logger.error(f"API fallback failed: {e}")
        results["retrieval_path"] = "all_sources_failed"
        results["error"] = "Cost data temporarily unavailable"

    return results


def execute_cost_analysis_specific(
    account_context: AccountContext,
    target_service: str,
) -> dict[str, Any]:
    """Specific service cost analysis - Tips_Table cross-reference + granular calls.

    Fault-tolerant: skip failed sources, continue with available.
    """
    results: dict[str, Any] = {"sources": [], "data": {}, "errors": []}

    # Source 1: Tips_Table for service context
    try:
        tips = _query_tips_for_service(target_service)
        if tips:
            results["data"]["tips"] = tips
            results["sources"].append("tips_table")
    except Exception as e:
        logger.warning(f"Tips lookup failed for {target_service}: {e}")
        results["errors"].append(f"tips_table: {e}")

    # Source 2: Cost data from cache/API
    try:
        connector = get_connector(account_context.cloud_provider)
        cost_data = connector.get_cost_data(account_context, "last-30d")
        results["data"]["cost_data"] = cost_data
        results["sources"].append("cost_explorer")
    except Exception as e:
        logger.warning(f"Cost data query failed: {e}")
        results["errors"].append(f"cost_explorer: {e}")

    # Source 3: Resource recommendations
    try:
        connector = get_connector(account_context.cloud_provider)
        recommendations = connector.get_resource_recommendations(account_context, target_service)
        if recommendations.get("recommendations"):
            results["data"]["recommendations"] = recommendations
            results["sources"].append("compute_optimizer")
    except Exception as e:
        logger.warning(f"Recommendations query failed: {e}")
        results["errors"].append(f"compute_optimizer: {e}")

    # If all sources failed
    if not results["sources"]:
        results["retrieval_path"] = "all_sources_failed"
        results["error"] = "Service data temporarily unavailable"
    else:
        results["retrieval_path"] = f"partial_success ({len(results['sources'])} sources)"

    return results


def execute_optimization_tips(
    account_context: AccountContext,
    target_service: str,
) -> dict[str, Any]:
    """Sequential tip scan with fault-tolerant aggregation.

    Continues processing remaining tips if an individual lookup fails.
    """
    results: dict[str, Any] = {"sources": [], "data": {"tips": []}, "errors": []}

    try:
        # Get all tip IDs for the service
        tip_ids = _get_tip_ids_for_service(target_service)

        successful_tips = []
        failed_tips = []

        for tip_id in tip_ids:
            try:
                tip_data = _get_tip_detail(target_service, tip_id)
                if tip_data:
                    successful_tips.append(tip_data)
            except Exception as e:
                logger.warning(f"Tip {tip_id} lookup failed: {e}")
                failed_tips.append(tip_id)

        results["data"]["tips"] = successful_tips
        results["sources"].append("tips_table")

        if failed_tips:
            results["errors"].append(f"Failed tips: {failed_tips}")

        results["retrieval_path"] = f"tips_scan ({len(successful_tips)}/{len(tip_ids)} succeeded)"

    except Exception as e:
        logger.error(f"Tips scan completely failed: {e}")
        results["errors"].append(str(e))
        results["retrieval_path"] = "all_sources_failed"
        results["error"] = "Optimization tips temporarily unavailable"

    return results


def execute_forecasting(
    account_context: AccountContext,
    timeframe: str,
    scenario: dict | None = None,
) -> dict[str, Any]:
    """Forecasting - validate bounds, pull history, generate projection.

    Validates projection period is within 1-12 months.
    """
    results: dict[str, Any] = {"sources": [], "data": {}}

    # Parse projection months from timeframe
    projection_months = _parse_projection_months(timeframe)

    # Validate projection bounds
    if projection_months is not None and projection_months > FORECAST_MAX_MONTHS:
        return {
            "sources": [],
            "data": {},
            "error": f"Projection period must be 1-12 months. Requested: {projection_months} months.",
            "retrieval_path": "validation_rejected",
        }

    if projection_months is not None and projection_months < 1:
        return {
            "sources": [],
            "data": {},
            "error": "Projection period must be at least 1 month.",
            "retrieval_path": "validation_rejected",
        }

    # Get historical data
    try:
        connector = get_connector(account_context.cloud_provider)
        historical = connector.get_historical_costs(account_context, days=90)
        results["data"]["historical_costs"] = historical
        results["sources"].append("historical_api")
        results["data"]["projection_months"] = projection_months or 3
        results["data"]["scenario"] = scenario
        results["retrieval_path"] = "historical_data_retrieved"
    except Exception as e:
        logger.error(f"Historical data retrieval failed: {e}")
        results["error"] = "Historical cost data unavailable for forecasting"
        results["retrieval_path"] = "all_sources_failed"

    return results


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _query_cache(account_id: str, timeframe: str) -> dict | None:
    """Query Cost_Cache_Table for fresh cached data."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(COST_CACHE_TABLE)

        cache_key = f"{account_id}#{timeframe}"
        response = table.get_item(Key={"cacheKey": cache_key})
        item = response.get("Item")

        if not item:
            return None

        # Check freshness
        cached_at = item.get("cachedAt", "")
        if _is_stale(cached_at):
            return None

        return item.get("data")
    except Exception as e:
        logger.warning(f"Cache query failed: {e}")
        return None


def _write_cache(account_id: str, timeframe: str, data: dict) -> None:
    """Write data back to Cost_Cache_Table."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(COST_CACHE_TABLE)

        cache_key = f"{account_id}#{timeframe}"
        table.put_item(Item={
            "cacheKey": cache_key,
            "accountId": account_id,
            "timeframe": timeframe,
            "data": data,
            "cachedAt": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Cache write-back: {cache_key}")
    except Exception as e:
        logger.warning(f"Cache write-back failed: {e}")


def _is_stale(cached_at: str) -> bool:
    """Check if a cache entry is stale based on timestamp."""
    if not cached_at:
        return True
    try:
        cached_time = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
        return age_seconds > CACHE_STALENESS_THRESHOLD_SECONDS
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Tips helpers
# ---------------------------------------------------------------------------

def _query_tips_for_service(service: str) -> list[dict]:
    """Query Tips_Table for tips matching a service."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(TIPS_TABLE)

        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("service").eq(service.upper()),
        )
        return response.get("Items", [])
    except Exception as e:
        logger.warning(f"Tips query failed for {service}: {e}")
        return []


def _get_tip_ids_for_service(service: str) -> list[str]:
    """Get all tip IDs for a given service."""
    tips = _query_tips_for_service(service)
    return [tip.get("tipId", "") for tip in tips if tip.get("tipId")]


def _get_tip_detail(service: str, tip_id: str) -> dict | None:
    """Get detailed tip data."""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(TIPS_TABLE)

        response = table.get_item(Key={"service": service.upper(), "tipId": tip_id})
        return response.get("Item")
    except Exception:
        return None


def _parse_projection_months(timeframe: str) -> int | None:
    """Parse projection months from timeframe string."""
    import re

    if not timeframe:
        return 3  # Default

    # Match patterns like 'next-3m', 'next-6m', 'next-12m'
    match = re.match(r"next-(\d+)m", timeframe)
    if match:
        return int(match.group(1))

    # Match 'next X months'
    match = re.match(r"next[\s-](\d+)[\s-]?months?", timeframe, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Historical timeframes don't need projection
    if timeframe.startswith("last-"):
        return 3  # Default projection for historical context

    return None
