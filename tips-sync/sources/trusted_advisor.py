"""
Trusted Advisor source fetcher.

Fetches and normalizes cost_optimizing checks from AWS Trusted Advisor
using the support:DescribeTrustedAdvisorChecks API.
"""

import json
import logging

logger = logging.getLogger(__name__)


def fetch_cost_checks(support_client) -> list[dict]:
    """Fetch cost optimization checks from AWS Trusted Advisor.

    Calls support:DescribeTrustedAdvisorChecks filtered to the
    cost_optimizing category, then fetches detailed results for each
    check via support:DescribeTrustedAdvisorCheckResult.

    Normalizes each check into a tip dict with default operational fields.

    Args:
        support_client: A boto3 client for the AWS Support service.

    Returns:
        List of normalized tip dicts, or empty list on API error.
    """
    try:
        # Fetch all checks filtered to cost_optimizing category
        response = support_client.describe_trusted_advisor_checks(language="en")
        all_checks = response.get("checks", [])

        # Filter to cost_optimizing category only
        cost_checks = [
            check for check in all_checks if check.get("category") == "cost_optimizing"
        ]

        logger.info(
            json.dumps(
                {
                    "event": "trusted_advisor_checks_fetched",
                    "total_checks": len(all_checks),
                    "cost_checks": len(cost_checks),
                }
            )
        )

        tips = []
        for check in cost_checks:
            tip = _fetch_and_normalize_check(support_client, check)
            if tip is not None:
                tips.append(tip)

        logger.info(
            json.dumps(
                {
                    "event": "trusted_advisor_normalization_complete",
                    "tips_produced": len(tips),
                }
            )
        )

        return tips

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "event": "trusted_advisor_fetch_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
        )
        return []


def _fetch_and_normalize_check(support_client, check: dict) -> dict | None:
    """Fetch result details for a single check and normalize to a tip dict.

    Args:
        support_client: A boto3 client for the AWS Support service.
        check: A check dict from DescribeTrustedAdvisorChecks response.

    Returns:
        Normalized tip dict, or None if the check result cannot be fetched.
    """
    check_id = check.get("id", "")
    check_name = check.get("name", "")

    try:
        result_response = support_client.describe_trusted_advisor_check_result(
            checkId=check_id, language="en"
        )
        result = result_response.get("result", {})
    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "event": "trusted_advisor_check_result_error",
                    "check_id": check_id,
                    "check_name": check_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
        )
        return None

    # Extract estimated monthly savings from result
    estimated_savings = _extract_estimated_savings(result)

    # Map TA category to a more specific category
    category = _map_category(check)

    # Determine service from check metadata
    service = _extract_service(check)

    # Build normalized tip dict
    tip = {
        # Content fields
        "title": check_name,
        "description": check.get("description", ""),
        "estimatedSavings": estimated_savings,
        "category": category,
        "service": service,
        "difficulty": "medium",
        "automatedCheck": f"Trusted Advisor check: {check_name}",
        # Default operational fields
        "checkImplemented": False,
        "actionType": "advisory",
        "actionLabel": "View Details",
        "level": 3,
        # Sync metadata
        "syncSource": "trusted-advisor",
        "_sourceId": check_id,
    }

    logger.info(
        json.dumps(
            {
                "event": "trusted_advisor_check_normalized",
                "check_id": check_id,
                "title": check_name,
                "service": service,
                "category": category,
            }
        )
    )

    return tip


def _extract_estimated_savings(result: dict) -> str:
    """Extract estimated monthly savings from a Trusted Advisor check result.

    The savings information can appear in the categorySpecificSummary
    or in the flaggedResources cost estimates.

    Args:
        result: The result dict from DescribeTrustedAdvisorCheckResult.

    Returns:
        Formatted savings string (e.g., "$150/month") or "Variable" if unavailable.
    """
    # Try categorySpecificSummary first
    category_summary = result.get("categorySpecificSummary", {})
    cost_optimizing = category_summary.get("costOptimizing", {})
    estimated_monthly = cost_optimizing.get("estimatedMonthlySavings", 0)

    if estimated_monthly and float(estimated_monthly) > 0:
        return f"${float(estimated_monthly):,.0f}/month"

    # Try flaggedResources for aggregate savings
    flagged_resources = result.get("flaggedResources", [])
    if flagged_resources:
        total_savings = 0
        for resource in flagged_resources:
            metadata = resource.get("metadata", [])
            # The last metadata field often contains the estimated savings
            if metadata:
                try:
                    # Try to parse the last field as a dollar amount
                    savings_str = metadata[-1]
                    if savings_str and savings_str.replace(".", "").replace(",", "").isdigit():
                        total_savings += float(savings_str.replace(",", ""))
                except (ValueError, IndexError):
                    continue

        if total_savings > 0:
            return f"${total_savings:,.0f}/month"

    return "Variable"


def _map_category(check: dict) -> str:
    """Map a Trusted Advisor cost_optimizing check to a specific tip category.

    Uses the check name and metadata to determine the most appropriate
    category for the tip.

    Args:
        check: A check dict from DescribeTrustedAdvisorChecks response.

    Returns:
        A category string (e.g., "right-sizing", "idle-resources").
    """
    name_lower = check.get("name", "").lower()

    if any(term in name_lower for term in ["idle", "unused", "underutilized", "low utilization"]):
        return "idle-resources"
    elif any(term in name_lower for term in ["reserved", "reservation", "savings plan"]):
        return "commitment-discounts"
    elif any(term in name_lower for term in ["right-siz", "oversized", "overprovisioned"]):
        return "right-sizing"
    elif any(term in name_lower for term in ["generation", "previous generation", "outdated"]):
        return "modernization"
    elif any(term in name_lower for term in ["transfer", "network", "nat"]):
        return "network-optimization"
    elif any(term in name_lower for term in ["storage", "snapshot", "volume"]):
        return "storage-optimization"
    else:
        return "cost-optimizing"


def _extract_service(check: dict) -> str:
    """Extract the AWS service name from a Trusted Advisor check.

    Uses the check name and metadata to determine which AWS service
    the check relates to.

    Args:
        check: A check dict from DescribeTrustedAdvisorChecks response.

    Returns:
        An AWS service name (e.g., "EC2", "RDS", "S3").
    """
    name_lower = check.get("name", "").lower()

    # Map common service keywords to service names
    # Order matters: more specific services checked first to avoid
    # generic terms like "instance" matching before specific service names
    service_keywords = {
        "RDS": ["rds", "database instance", "aurora"],
        "ElastiCache": ["elasticache", "cache"],
        "Redshift": ["redshift"],
        "DynamoDB": ["dynamodb"],
        "EBS": ["ebs", "volume", "snapshot"],
        "S3": ["s3", "bucket", "storage class"],
        "ELB": ["load balancer", "elb", "alb", "nlb"],
        "Lambda": ["lambda"],
        "CloudFront": ["cloudfront", "distribution"],
        "Route53": ["route 53", "route53", "hosted zone"],
        "NAT": ["nat gateway"],
        "VPC": ["vpc", "elastic ip"],
        "EC2": ["ec2", "instance", "elastic compute"],
    }

    for service, keywords in service_keywords.items():
        if any(keyword in name_lower for keyword in keywords):
            return service

    return "General"
