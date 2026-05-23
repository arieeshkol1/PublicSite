"""
Cost Optimization Hub source fetcher.

Fetches and normalizes recommendations from AWS Cost Optimization Hub
using the cost-optimization-hub:ListRecommendations API.
"""

import json
import logging

logger = logging.getLogger(__name__)


def fetch_recommendations(client) -> list[dict]:
    """Fetch recommendations from AWS Cost Optimization Hub with pagination.

    Calls cost-optimization-hub:ListRecommendations, handling pagination via
    NextToken. Each recommendation is normalized into a tip dict compatible
    with the Tips_Table schema.

    Args:
        client: A boto3 client for the 'cost-optimization-hub' service.

    Returns:
        A list of normalized tip dicts ready for delta comparison.
        Returns an empty list if an API error occurs.
    """
    tips = []

    try:
        next_token = None

        while True:
            params = {}
            if next_token:
                params["nextToken"] = next_token

            response = client.list_recommendations(**params)

            items = response.get("items", [])
            for rec in items:
                tip = _normalize_recommendation(rec)
                if tip:
                    tips.append(tip)

            next_token = response.get("nextToken")
            if not next_token:
                break

        logger.info(
            json.dumps({
                "event": "cost_optimization_hub_fetch_complete",
                "recommendations_fetched": len(tips),
            })
        )

    except Exception as e:
        logger.error(
            json.dumps({
                "event": "cost_optimization_hub_fetch_error",
                "error": str(e),
                "error_type": type(e).__name__,
            })
        )
        return []

    return tips


def _normalize_recommendation(rec: dict) -> dict | None:
    """Normalize a Cost Optimization Hub recommendation into a tip dict.

    Maps COH fields to the Tips_Table schema:
      - source → service
      - recommendationType → category
      - estimatedMonthlySavings → estimatedSavings (formatted)
      - currentResourceSummary → contributes to description

    Sets default operational fields for new AWS-sourced tips.

    Args:
        rec: A single recommendation dict from the ListRecommendations response.

    Returns:
        A normalized tip dict, or None if the recommendation cannot be normalized.
    """
    try:
        # Extract service from the 'source' field (e.g., "Ec2Instance" -> "EC2")
        service = _extract_service(rec.get("source", ""))

        # Map recommendationType to category
        category = rec.get("recommendationType", "general").lower().replace("_", "-")

        # Build title from recommendation type and resource info
        title = _build_title(rec)

        # Build description from currentResourceSummary and other fields
        description = _build_description(rec)

        # Format estimated savings
        estimated_savings = _format_savings(rec.get("estimatedMonthlySavings", {}))

        # Build the normalized tip dict
        tip = {
            "id": "",  # Temporary, will be assigned by generate_tip_id later
            "service": service,
            "category": category,
            "title": title,
            "description": description,
            "estimatedSavings": estimated_savings,
            "difficulty": "medium",
            "automatedCheck": rec.get("recommendationId", ""),
            "checkImplemented": False,
            "actionType": "advisory",
            "actionLabel": "View Details",
            "level": 3,
            "syncSource": "cost-optimization-hub",
            "recommendationId": rec.get("recommendationId", ""),
        }

        return tip

    except Exception as e:
        logger.warning(
            json.dumps({
                "event": "cost_optimization_hub_normalize_error",
                "error": str(e),
                "recommendation_id": rec.get("recommendationId", "unknown"),
            })
        )
        return None


def _extract_service(source: str) -> str:
    """Extract a normalized service name from the COH source field.

    Args:
        source: The source field from COH (e.g., "Ec2Instance", "RdsDbInstance").

    Returns:
        Normalized service name (e.g., "EC2", "RDS").
    """
    if not source:
        return "General"

    # Common mappings from COH source values to service names
    service_map = {
        "ec2instance": "EC2",
        "ec2autoscalinggroup": "EC2",
        "ec2reservedinstances": "EC2",
        "ebsvolume": "EBS",
        "rdsdbinstance": "RDS",
        "rdsreservedinstances": "RDS",
        "lambdafunction": "Lambda",
        "ecsservice": "ECS",
        "elasticachenode": "ElastiCache",
        "opensearchdomain": "OpenSearch",
        "redshiftreservedinstances": "Redshift",
        "sagemakernotebookinstance": "SageMaker",
        "s3storagelens": "S3",
        "computesavingsplans": "Savings Plans",
        "ec2instancesavingsplans": "Savings Plans",
        "sagemakersavingsplans": "Savings Plans",
    }

    source_lower = source.lower()
    if source_lower in service_map:
        return service_map[source_lower]

    # Fallback: extract the service prefix from camelCase
    # e.g., "Ec2Instance" -> "EC2"
    for key, value in service_map.items():
        if source_lower.startswith(key[:3]):
            return value

    return source


def _build_title(rec: dict) -> str:
    """Build a human-readable title from the recommendation.

    Args:
        rec: A single recommendation dict from COH.

    Returns:
        A descriptive title string.
    """
    rec_type = rec.get("recommendationType", "")
    source = rec.get("source", "")

    if rec_type and source:
        # Format: "Right-size EC2 Instance" or "Delete Unused EBS Volume"
        action = rec_type.replace("_", " ").title()
        return f"{action} - {source}"

    return rec_type.replace("_", " ").title() if rec_type else "Cost Optimization Recommendation"


def _build_description(rec: dict) -> str:
    """Build a description from the recommendation's resource summary.

    Args:
        rec: A single recommendation dict from COH.

    Returns:
        A description string incorporating resource summary details.
    """
    parts = []

    current_summary = rec.get("currentResourceSummary", "")
    if current_summary:
        parts.append(f"Current resource: {current_summary}")

    recommended_summary = rec.get("recommendedResourceSummary", "")
    if recommended_summary:
        parts.append(f"Recommended: {recommended_summary}")

    if not parts:
        rec_type = rec.get("recommendationType", "optimization")
        source = rec.get("source", "resource")
        parts.append(
            f"AWS Cost Optimization Hub recommends {rec_type.replace('_', ' ')} "
            f"for {source} to reduce costs."
        )

    return " | ".join(parts)


def _format_savings(savings: dict | float | str) -> str:
    """Format estimated monthly savings into a display string.

    Args:
        savings: The estimatedMonthlySavings value from COH.
            Can be a dict with 'value' and 'currency', a float, or a string.

    Returns:
        Formatted savings string (e.g., "$25.50/month").
    """
    if isinstance(savings, dict):
        value = savings.get("value", 0)
        currency = savings.get("currency", "USD")
        if value and float(value) > 0:
            return f"${float(value):.2f}/month"
        return "Potential savings available"

    if isinstance(savings, (int, float)):
        if savings > 0:
            return f"${float(savings):.2f}/month"
        return "Potential savings available"

    if isinstance(savings, str) and savings:
        return savings

    return "Potential savings available"
