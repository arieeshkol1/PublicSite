"""Tips enrichment module - populates runtime metadata and evaluates rules."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import boto3

from .models import EnrichedTip
from .constants import TIPS_TABLE

logger = logging.getLogger(__name__)

# Default API configurations when enrichment fields are missing
_DEFAULT_API_CONFIGS: dict[str, dict] = {
    "EC2": {
        "api_endpoint": "compute-optimizer:GetEC2InstanceRecommendations",
        "parameter_schema": {"instanceArns": {"type": "array"}, "maxResults": {"type": "integer", "default": 10}},
        "response_format": {"recommendations": []},
    },
    "RDS": {
        "api_endpoint": "ce:GetCostAndUsage",
        "parameter_schema": {"service": {"type": "string", "default": "Amazon RDS"}},
        "response_format": {"costs": []},
    },
    "S3": {
        "api_endpoint": "s3:ListBuckets",
        "parameter_schema": {},
        "response_format": {"buckets": []},
    },
    "Lambda": {
        "api_endpoint": "lambda:ListFunctions",
        "parameter_schema": {"maxItems": {"type": "integer", "default": 50}},
        "response_format": {"functions": []},
    },
}


def enrich_tips_table() -> dict[str, Any]:
    """Periodic enrichment process: populate API mappings, schemas, rules.

    Returns summary of enrichment results.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE)

    enriched_count = 0
    failed_count = 0
    now = datetime.now(timezone.utc).isoformat()

    try:
        response = table.scan()
        items = response.get("Items", [])

        for item in items:
            try:
                service = item.get("service", "")
                tip_id = item.get("tipId", "")

                if not service or not tip_id:
                    continue

                # Build enrichment data
                enrichment = _build_enrichment(service, item)
                enrichment["lastEnriched"] = now

                # Update the record
                table.update_item(
                    Key={"service": service, "tipId": tip_id},
                    UpdateExpression=(
                        "SET apiEndpoint = :ep, parameterSchema = :ps, "
                        "responseFormat = :rf, costThresholds = :ct, "
                        "optimizationRules = :rules, lastEnriched = :le"
                    ),
                    ExpressionAttributeValues={
                        ":ep": enrichment.get("apiEndpoint", ""),
                        ":ps": enrichment.get("parameterSchema", {}),
                        ":rf": enrichment.get("responseFormat", {}),
                        ":ct": enrichment.get("costThresholds", {}),
                        ":rules": enrichment.get("optimizationRules", []),
                        ":le": now,
                    },
                )
                enriched_count += 1
            except Exception as e:
                logger.warning(f"Failed to enrich tip {item.get('tipId')}: {e}")
                failed_count += 1

    except Exception as e:
        logger.error(f"Tips enrichment scan failed: {e}")
        return {"status": "error", "error": str(e)}

    return {
        "status": "completed",
        "enriched": enriched_count,
        "failed": failed_count,
        "timestamp": now,
    }


def get_enriched_tip(service: str, tip_id: str) -> EnrichedTip | None:
    """Query pre-enriched tip with runtime metadata.

    Falls back to default config when enrichment fields missing.
    """
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(TIPS_TABLE)

        response = table.get_item(Key={"service": service.upper(), "tipId": tip_id})
        item = response.get("Item")

        if not item:
            return None

        # Get defaults for this service
        defaults = _DEFAULT_API_CONFIGS.get(service.upper(), {})

        return EnrichedTip(
            tip_id=tip_id,
            service=service,
            api_endpoint=item.get("apiEndpoint", defaults.get("api_endpoint", "")),
            parameter_schema=item.get("parameterSchema", defaults.get("parameter_schema", {})),
            response_format=item.get("responseFormat", defaults.get("response_format", {})),
            cost_thresholds=item.get("costThresholds", {}),
            optimization_rules=item.get("optimizationRules", []),
            last_enriched=item.get("lastEnriched", ""),
        )

    except Exception as e:
        logger.warning(f"Failed to get enriched tip {service}/{tip_id}: {e}")
        return None


def evaluate_rules(
    metrics: dict[str, float],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate optimization rules against gathered metric data.

    Each rule has a 'condition' (expression) and 'action'.
    Returns list of triggered rules (no false negatives for values beyond thresholds).
    """
    triggered: list[dict[str, Any]] = []

    for rule in rules:
        condition = rule.get("condition", "")
        if not condition:
            continue

        try:
            if _evaluate_condition(condition, metrics):
                triggered.append({
                    "rule": condition,
                    "action": rule.get("action", "review"),
                    "priority": rule.get("priority", 99),
                    "metrics_snapshot": {k: v for k, v in metrics.items() if k in condition},
                })
        except Exception as e:
            logger.warning(f"Rule evaluation failed for '{condition}': {e}")
            # On evaluation error for a rule, check if any metric clearly breaches
            # a numeric threshold mentioned in the rule to avoid false negatives
            breach = _check_obvious_breach(condition, metrics)
            if breach:
                triggered.append({
                    "rule": condition,
                    "action": rule.get("action", "review"),
                    "priority": rule.get("priority", 99),
                    "metrics_snapshot": breach,
                    "note": "Evaluated via fallback threshold check",
                })

    return triggered


def _evaluate_condition(condition: str, metrics: dict[str, float]) -> bool:
    """Safely evaluate a rule condition against metrics.

    Supports conditions like:
    - 'avg_cpu < 10'
    - 'avg_cpu < 10 AND max_cpu < 30'
    - 'memory_utilization > 80'
    """
    import re

    # Split on AND/OR
    parts = re.split(r"\s+AND\s+", condition, flags=re.IGNORECASE)

    for part in parts:
        part = part.strip()
        # Parse comparison: metric_name operator value
        match = re.match(r"(\w+)\s*([<>=!]+)\s*([\d.]+)", part)
        if not match:
            continue

        metric_name = match.group(1)
        operator = match.group(2)
        threshold = float(match.group(3))

        metric_value = metrics.get(metric_name)
        if metric_value is None:
            # Metric not available - can't evaluate, skip this part
            continue

        if not _compare(metric_value, operator, threshold):
            return False

    return True


def _compare(value: float, operator: str, threshold: float) -> bool:
    """Compare a value against a threshold using the specified operator."""
    if operator == "<":
        return value < threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == ">":
        return value > threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "==" or operator == "=":
        return abs(value - threshold) < 0.001
    elif operator == "!=":
        return abs(value - threshold) >= 0.001
    return False


def _check_obvious_breach(condition: str, metrics: dict[str, float]) -> dict | None:
    """Fallback check for obvious threshold breaches to avoid false negatives."""
    import re

    breaches = {}
    comparisons = re.findall(r"(\w+)\s*([<>=!]+)\s*([\d.]+)", condition)

    for metric_name, operator, threshold_str in comparisons:
        threshold = float(threshold_str)
        metric_value = metrics.get(metric_name)
        if metric_value is not None:
            if _compare(metric_value, operator, threshold):
                breaches[metric_name] = metric_value

    return breaches if breaches else None


def _build_enrichment(service: str, item: dict) -> dict:
    """Build enrichment data for a tip based on its service."""
    defaults = _DEFAULT_API_CONFIGS.get(service.upper(), {})

    # Use existing values or fall back to defaults
    return {
        "apiEndpoint": item.get("apiEndpoint", defaults.get("api_endpoint", "")),
        "parameterSchema": item.get("parameterSchema", defaults.get("parameter_schema", {})),
        "responseFormat": item.get("responseFormat", defaults.get("response_format", {})),
        "costThresholds": item.get("costThresholds", _default_thresholds(service)),
        "optimizationRules": item.get("optimizationRules", _default_rules(service)),
    }


def _default_thresholds(service: str) -> dict:
    """Default cost thresholds by service."""
    thresholds = {
        "EC2": {"cpuUtilizationLow": 10, "cpuUtilizationHigh": 80, "memoryUtilizationLow": 20},
        "RDS": {"cpuUtilizationLow": 10, "connectionCountLow": 5, "storageUtilizationHigh": 85},
        "S3": {"objectCountHigh": 1000000, "bucketSizeHighGB": 500},
        "Lambda": {"invocationErrorRateHigh": 5, "durationP99HighMs": 10000},
    }
    return thresholds.get(service.upper(), {})


def _default_rules(service: str) -> list[dict]:
    """Default optimization rules by service."""
    rules = {
        "EC2": [
            {"condition": "avg_cpu < 10 AND max_cpu < 30", "action": "recommend_downsize", "priority": 1},
            {"condition": "avg_cpu > 80", "action": "recommend_upsize", "priority": 2},
        ],
        "RDS": [
            {"condition": "avg_cpu < 10", "action": "recommend_downsize", "priority": 1},
            {"condition": "connections < 5", "action": "recommend_stop_or_terminate", "priority": 1},
        ],
        "S3": [
            {"condition": "access_frequency < 1", "action": "recommend_glacier", "priority": 2},
        ],
        "Lambda": [
            {"condition": "error_rate > 5", "action": "investigate_errors", "priority": 1},
            {"condition": "avg_duration > 10000", "action": "recommend_optimize", "priority": 2},
        ],
    }
    return rules.get(service.upper(), [])
