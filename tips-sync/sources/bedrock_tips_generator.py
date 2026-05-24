"""
Bedrock AI Tips Generator.

Uses Claude via Bedrock to generate new cost optimization tips
by analyzing coverage gaps in the existing tips catalog.
Groups existing tips by service, identifies underrepresented areas,
and generates new actionable tips.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Services that should have tips but might be underrepresented
TARGET_SERVICES = [
    "EC2", "S3", "RDS", "Lambda", "ECS", "EKS", "DynamoDB",
    "ElastiCache", "Redshift", "CloudFront", "EBS", "NAT Gateway",
    "ELB", "SageMaker", "Bedrock", "OpenSearch", "MSK",
    "Glue", "Athena", "EMR", "Kinesis", "SNS", "SQS",
    "API Gateway", "Step Functions", "EventBridge", "CloudWatch",
    "Secrets Manager", "Systems Manager", "Transfer Family",
    "AppSync", "Cognito", "WAF", "Shield", "GuardDuty",
]

PROMPT_TEMPLATE = """You are an AWS FinOps expert. Analyze the following existing cost optimization tips catalog and generate NEW tips for services/categories that are underrepresented.

EXISTING TIPS BY SERVICE (count):
{service_summary}

SERVICES WITH NO TIPS YET: {missing_services}

Generate exactly {num_tips} NEW cost optimization tips that DON'T duplicate existing ones. Focus on:
1. Services with 0 tips (highest priority)
2. Services with only 1-2 tips (add more depth)
3. New categories for well-covered services (e.g., new pricing models, new features)

For each tip, output ONLY a JSON array with objects containing:
- "service": AWS service name (e.g., "Glue", "Athena")
- "category": tip category (e.g., "right-sizing", "scheduling", "pricing-model", "cleanup", "architecture")
- "title": short actionable title (max 80 chars)
- "description": detailed description with specific actions (2-3 sentences)
- "estimatedSavings": savings estimate (e.g., "20-40%", "$50/month", "varies")
- "difficulty": "easy", "medium", or "hard"
- "automatedCheck": AWS CLI or API call to verify this optimization opportunity

Output ONLY the JSON array, no markdown, no explanation."""


def generate_tips_with_bedrock(bedrock_client, existing_tips: list, num_tips: int = 5) -> list:
    """Use Bedrock Claude to generate new cost optimization tips.

    Analyzes the existing tips catalog to find coverage gaps and
    generates new tips for underrepresented services/categories.

    Args:
        bedrock_client: boto3 client for bedrock-runtime service.
        existing_tips: List of existing tip dicts from all sources.
        num_tips: Number of new tips to generate (default 5).

    Returns:
        List of new tip dicts ready for delta comparison, or empty list on error.
    """
    try:
        # Build service summary from existing tips
        service_counts = {}
        existing_titles = set()
        for tip in existing_tips:
            svc = tip.get("service", "General")
            service_counts[svc] = service_counts.get(svc, 0) + 1
            existing_titles.add(tip.get("title", "").lower().strip())

        service_summary = "\n".join(
            f"  - {svc}: {count} tips"
            for svc, count in sorted(service_counts.items(), key=lambda x: -x[1])
        )

        # Find services with no tips
        covered_services = set(service_counts.keys())
        missing_services = [s for s in TARGET_SERVICES if s not in covered_services]

        prompt = PROMPT_TEMPLATE.format(
            service_summary=service_summary,
            missing_services=", ".join(missing_services) if missing_services else "None (all covered)",
            num_tips=num_tips,
        )

        logger.info(json.dumps({
            "event": "bedrock_tips_generation_started",
            "existing_tips_count": len(existing_tips),
            "services_covered": len(covered_services),
            "services_missing": len(missing_services),
            "num_tips_requested": num_tips,
        }))

        # Call Bedrock Claude
        response = bedrock_client.invoke_model(
            modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.7,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            }),
        )

        response_body = json.loads(response["body"].read())
        content = response_body.get("content", [{}])[0].get("text", "")

        # Parse the JSON response
        # Handle potential markdown wrapping
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        new_tips_raw = json.loads(content.strip())

        if not isinstance(new_tips_raw, list):
            logger.warning(json.dumps({
                "event": "bedrock_tips_invalid_format",
                "content_type": type(new_tips_raw).__name__,
            }))
            return []

        # Normalize and deduplicate against existing tips
        new_tips = []
        for tip in new_tips_raw:
            title = tip.get("title", "").strip()
            if not title:
                continue

            # Skip if title is too similar to existing
            if title.lower() in existing_titles:
                logger.info(json.dumps({
                    "event": "bedrock_tip_skipped_duplicate",
                    "title": title,
                }))
                continue

            # Normalize to standard schema
            normalized = {
                "id": "",  # Will be assigned by generate_tip_id later
                "service": tip.get("service", "General"),
                "category": tip.get("category", "optimization"),
                "title": title,
                "description": tip.get("description", ""),
                "estimatedSavings": tip.get("estimatedSavings", "varies"),
                "difficulty": tip.get("difficulty", "medium"),
                "automatedCheck": tip.get("automatedCheck", ""),
                "checkImplemented": False,
                "actionType": "advisory",
                "actionLabel": "View Details",
                "level": 3,
                "syncSource": "bedrock-ai",
            }
            new_tips.append(normalized)

        logger.info(json.dumps({
            "event": "bedrock_tips_generation_complete",
            "tips_generated": len(new_tips),
            "tips_raw": len(new_tips_raw),
        }))

        return new_tips

    except Exception as e:
        logger.error(json.dumps({
            "event": "bedrock_tips_generation_error",
            "error": str(e),
            "error_type": type(e).__name__,
        }))
        return []
