"""
Bedrock AI Tips Generator.

Uses Claude via Bedrock to generate new cost optimization tips
by analyzing coverage gaps in the existing tips catalog.
Groups existing tips by service, identifies underrepresented areas,
and generates new actionable tips across AWS, Azure, and GCP.
"""

import json
import logging

logger = logging.getLogger(__name__)

# AWS services that should have tips but might be underrepresented
TARGET_SERVICES = [
    "EC2", "S3", "RDS", "Lambda", "ECS", "EKS", "DynamoDB",
    "ElastiCache", "Redshift", "CloudFront", "EBS", "NAT Gateway",
    "ELB", "SageMaker", "Bedrock", "OpenSearch", "MSK",
    "Glue", "Athena", "EMR", "Kinesis", "SNS", "SQS",
    "API Gateway", "Step Functions", "EventBridge", "CloudWatch",
    "Secrets Manager", "Systems Manager", "Transfer Family",
    "AppSync", "Cognito", "WAF", "Shield", "GuardDuty",
]

# Azure services that should have tips
AZURE_TARGET_SERVICES = [
    "Virtual Machines", "VM Scale Sets", "Azure Functions", "App Service",
    "Container Instances", "Azure Kubernetes Service",
    "Azure SQL", "Cosmos DB", "Azure Database for PostgreSQL", "Azure Database for MySQL",
    "Blob Storage", "Managed Disks", "Azure Files", "Data Lake Storage",
    "Azure Monitor", "Log Analytics", "Application Insights",
    "Networking", "Application Gateway", "ExpressRoute", "VPN Gateway",
    "Azure DevOps", "Azure AD", "Key Vault",
    "Azure Cache for Redis", "Event Hubs", "Service Bus",
    "Azure Synapse", "Data Factory", "Azure Databricks",
    "Azure Firewall", "DDoS Protection", "Web Application Firewall",
    "Azure Backup", "Site Recovery", "Azure Policy",
]

# GCP services that should have tips
GCP_TARGET_SERVICES = [
    "Compute Engine", "Cloud Functions", "Cloud Run", "App Engine",
    "Google Kubernetes Engine",
    "Cloud SQL", "Cloud Spanner", "Firestore", "Bigtable", "Memorystore",
    "Cloud Storage", "Persistent Disks", "Filestore",
    "BigQuery", "Dataflow", "Dataproc", "Pub/Sub",
    "Networking", "Cloud NAT", "Load Balancing", "Cloud CDN",
    "Cloud Interconnect", "Cloud Armor",
    "Cloud Logging", "Cloud Monitoring", "Cloud Trace",
    "Artifact Registry", "Cloud Build", "Secret Manager",
    "Vertex AI", "Vision AI", "Speech-to-Text",
    "Cloud DNS", "Apigee",
]

PROMPT_TEMPLATE = """You are a multi-cloud FinOps expert covering AWS, Azure, and GCP. Analyze the following existing cost optimization tips catalog and generate NEW tips for services/categories that are underrepresented across all three cloud providers.

EXISTING TIPS BY CLOUD PROVIDER AND SERVICE (count):
{service_summary}

SERVICES WITH NO TIPS YET:
- AWS: {missing_aws_services}
- Azure: {missing_azure_services}
- GCP: {missing_gcp_services}

Generate exactly {num_tips} NEW cost optimization tips distributed across all 3 providers. Aim for approximately:
- {aws_count} AWS tips
- {azure_count} Azure tips
- {gcp_count} GCP tips

Focus on:
1. Services with 0 tips (highest priority)
2. Services with only 1-2 tips (add more depth)
3. New categories for well-covered services (e.g., new pricing models, new features)

For each tip, output ONLY a JSON array with objects containing:
- "cloud": cloud provider in UPPERCASE ("AWS", "AZURE", or "GCP")
- "service": service name (e.g., "Glue", "Virtual Machines", "BigQuery")
- "category": tip category (e.g., "right-sizing", "scheduling", "pricing-model", "cleanup", "architecture", "storage-tiering", "idle-resources", "data-management", "tagging", "networking", "licensing")
- "title": short actionable title (max 80 chars)
- "description": detailed description with specific actions (2-3 sentences)
- "estimatedSavings": savings estimate (e.g., "20-40%", "$50/month", "varies")
- "difficulty": "easy", "medium", or "hard"
- "automatedCheck": CLI or API call to verify this optimization opportunity (use aws cli for AWS, az cli for Azure, gcloud for GCP)

Output ONLY the JSON array, no markdown, no explanation."""


def generate_tips_with_bedrock(bedrock_client, existing_tips: list, num_tips: int = 5) -> list:
    """Use Bedrock Claude to generate new cost optimization tips.

    Analyzes the existing tips catalog to find coverage gaps and
    generates new tips for underrepresented services/categories
    across AWS, Azure, and GCP.

    Args:
        bedrock_client: boto3 client for bedrock-runtime service.
        existing_tips: List of existing tip dicts from all sources.
        num_tips: Number of new tips to generate (default 5).

    Returns:
        List of new tip dicts ready for delta comparison, or empty list on error.
    """
    try:
        # Build service summary from existing tips, grouped by cloud provider
        service_counts_by_cloud = {"AWS": {}, "AZURE": {}, "GCP": {}}
        existing_titles = set()
        for tip in existing_tips:
            cloud = tip.get("cloud", tip.get("cloudProvider", "AWS")).upper()
            if cloud not in service_counts_by_cloud:
                cloud = "AWS"  # Default to AWS for legacy tips without cloud field
            svc = tip.get("service", "General")
            service_counts_by_cloud[cloud][svc] = service_counts_by_cloud[cloud].get(svc, 0) + 1
            existing_titles.add(tip.get("title", "").lower().strip())

        # Build combined service summary
        summary_lines = []
        for cloud in ["AWS", "AZURE", "GCP"]:
            counts = service_counts_by_cloud[cloud]
            if counts:
                summary_lines.append(f"\n  {cloud}:")
                for svc, count in sorted(counts.items(), key=lambda x: -x[1]):
                    summary_lines.append(f"    - {svc}: {count} tips")
            else:
                summary_lines.append(f"\n  {cloud}: (no tips yet)")
        service_summary = "\n".join(summary_lines)

        # Find services with no tips per cloud
        covered_aws = set(service_counts_by_cloud["AWS"].keys())
        covered_azure = set(service_counts_by_cloud["AZURE"].keys())
        covered_gcp = set(service_counts_by_cloud["GCP"].keys())

        missing_aws = [s for s in TARGET_SERVICES if s not in covered_aws]
        missing_azure = [s for s in AZURE_TARGET_SERVICES if s not in covered_azure]
        missing_gcp = [s for s in GCP_TARGET_SERVICES if s not in covered_gcp]

        # Distribute tips across providers (roughly: 2 AWS, 2 Azure, 1 GCP for 5 tips)
        aws_count = max(1, round(num_tips * 0.4))
        azure_count = max(1, round(num_tips * 0.4))
        gcp_count = max(1, num_tips - aws_count - azure_count)

        prompt = PROMPT_TEMPLATE.format(
            service_summary=service_summary,
            missing_aws_services=", ".join(missing_aws) if missing_aws else "None (all covered)",
            missing_azure_services=", ".join(missing_azure) if missing_azure else "None (all covered)",
            missing_gcp_services=", ".join(missing_gcp) if missing_gcp else "None (all covered)",
            num_tips=num_tips,
            aws_count=aws_count,
            azure_count=azure_count,
            gcp_count=gcp_count,
        )

        logger.info(json.dumps({
            "event": "bedrock_tips_generation_started",
            "existing_tips_count": len(existing_tips),
            "aws_services_covered": len(covered_aws),
            "azure_services_covered": len(covered_azure),
            "gcp_services_covered": len(covered_gcp),
            "aws_services_missing": len(missing_aws),
            "azure_services_missing": len(missing_azure),
            "gcp_services_missing": len(missing_gcp),
            "num_tips_requested": num_tips,
        }))

        # Call Bedrock - use Amazon Nova Lite (available in this account)
        response = bedrock_client.invoke_model(
            modelId="us.amazon.nova-2-lite-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inferenceConfig": {
                    "max_new_tokens": 4096,
                    "temperature": 0.7,
                },
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ],
            }),
        )

        response_body = json.loads(response["body"].read())
        content = response_body.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

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

            # Determine cloud provider (UPPERCASE for DynamoDB)
            cloud = tip.get("cloud", "AWS").upper()
            if cloud not in ("AWS", "AZURE", "GCP"):
                cloud = "AWS"

            # Normalize to standard schema
            normalized = {
                "id": "",  # Will be assigned by generate_tip_id later
                "cloud": cloud,
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

            # Validate service name — reject placeholder/meta values
            svc = normalized["service"]
            invalid_services = {"AI-GENERATED", "ai-generated", "Unknown", "UNKNOWN", "General", "general", "N/A", ""}
            if svc in invalid_services or not svc.strip():
                logger.warning(json.dumps({
                    "event": "bedrock_tip_skipped_invalid_service",
                    "service": svc,
                    "title": title,
                }))
                continue

            new_tips.append(normalized)

        logger.info(json.dumps({
            "event": "bedrock_tips_generation_complete",
            "tips_generated": len(new_tips),
            "tips_raw": len(new_tips_raw),
            "tips_by_cloud": {
                "AWS": sum(1 for t in new_tips if t.get("cloud") == "AWS"),
                "AZURE": sum(1 for t in new_tips if t.get("cloud") == "AZURE"),
                "GCP": sum(1 for t in new_tips if t.get("cloud") == "GCP"),
            },
        }))

        return new_tips

    except Exception as e:
        logger.error(json.dumps({
            "event": "bedrock_tips_generation_error",
            "error": str(e),
            "error_type": type(e).__name__,
        }))
        return []
