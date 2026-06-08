#!/usr/bin/env python3
"""
Migration script: Enrich existing tips with providerRouting metadata.

Scans the ViewMyBill-CostOptimizationTips DynamoDB table and adds the
`providerRouting` map attribute to existing tips, enabling multi-provider
optimization checks via the vendor-neutral agent tooling architecture.

Each providerRouting entry contains:
  - apiEndpoint: Provider-specific API call(s) for the optimization check
  - parameterSchema: Parameters to pass when invoking the API
  - responseFormat: Expected response structure identifier
  - costThresholds: Minimum thresholds to surface the tip

Usage:
    python scripts/enrich_tips_provider_routing.py
    python scripts/enrich_tips_provider_routing.py --region us-east-1
    python scripts/enrich_tips_provider_routing.py --dry-run
    python scripts/enrich_tips_provider_routing.py --tip-id ec2-001
"""

import logging
import os
import sys

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "ViewMyBill-CostOptimizationTips"
REGION = os.environ.get("AWS_REGION", "us-east-1")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# providerRouting definitions per tip category
# ---------------------------------------------------------------------------

PROVIDER_ROUTING_MAP = {
    # ─── EC2 / Compute Right-Sizing ────────────────────────────────────
    "ec2-001": {
        "aws": {
            "apiEndpoint": "ec2:DescribeInstances + cloudwatch:GetMetricStatistics",
            "parameterSchema": {
                "metricsWindow": "14d",
                "cpuThreshold": 30,
                "memoryThreshold": 30,
            },
            "responseFormat": "ec2_instance_list",
            "costThresholds": {"minSavingsUSD": 10, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Compute/virtualMachines + Microsoft.Monitor/metrics",
            "parameterSchema": {
                "metricsWindow": "14d",
                "cpuThreshold": 30,
                "memoryThreshold": 30,
            },
            "responseFormat": "azure_vm_list",
            "costThresholds": {"minSavingsUSD": 10, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "compute.instances.list + monitoring.timeSeries.list",
            "parameterSchema": {
                "metricsWindow": "14d",
                "cpuThreshold": 30,
                "memoryThreshold": 30,
            },
            "responseFormat": "gce_instance_list",
            "costThresholds": {"minSavingsUSD": 10, "minResourceCount": 1},
        },
    },
    # ─── EC2 / Reserved Instances & Savings Plans ──────────────────────
    "ec2-002": {
        "aws": {
            "apiEndpoint": "pricing:GetProducts + ce:GetSavingsPlansCoverage",
            "parameterSchema": {
                "granularity": "DAILY",
                "lookbackDays": 30,
            },
            "responseFormat": "cost_explorer_results",
            "costThresholds": {"minSavingsUSD": 50},
        },
        "azure": {
            "apiEndpoint": "Microsoft.CostManagement/query + Microsoft.Reservations/reservationOrders",
            "parameterSchema": {
                "granularity": "Daily",
                "lookbackDays": 30,
            },
            "responseFormat": "azure_cost_mgmt",
            "costThresholds": {"minSavingsUSD": 50},
        },
        "gcp": {
            "apiEndpoint": "cloudbilling.billingAccounts.budgets + recommender.projects.locations.recommenders.recommendations",
            "parameterSchema": {
                "granularity": "DAILY",
                "lookbackDays": 30,
            },
            "responseFormat": "bigquery_billing",
            "costThresholds": {"minSavingsUSD": 50},
        },
    },
    # ─── EC2 / Spot Instances ──────────────────────────────────────────
    "ec2-003": {
        "aws": {
            "apiEndpoint": "ec2:DescribeInstances + ec2:GetSpotPlacementScores",
            "parameterSchema": {
                "metricsWindow": "30d",
                "cpuThreshold": 50,
            },
            "responseFormat": "ec2_instance_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Compute/virtualMachines + Microsoft.Compute/spotPriceHistory",
            "parameterSchema": {
                "metricsWindow": "30d",
            },
            "responseFormat": "azure_vm_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "compute.instances.list + compute.machineTypes.list",
            "parameterSchema": {
                "metricsWindow": "30d",
            },
            "responseFormat": "gce_instance_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
    },
    # ─── EC2 / Scheduling Non-Prod ─────────────────────────────────────
    "ec2-004": {
        "aws": {
            "apiEndpoint": "ec2:DescribeInstances + cloudwatch:GetMetricStatistics",
            "parameterSchema": {
                "metricsWindow": "7d",
                "tagFilter": "Environment=dev,test,staging,qa,sandbox",
            },
            "responseFormat": "ec2_instance_list",
            "costThresholds": {"minSavingsUSD": 15, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Compute/virtualMachines + Microsoft.Monitor/metrics",
            "parameterSchema": {
                "metricsWindow": "7d",
                "tagFilter": "Environment=dev,test,staging,qa,sandbox",
            },
            "responseFormat": "azure_vm_list",
            "costThresholds": {"minSavingsUSD": 15, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "compute.instances.list + monitoring.timeSeries.list",
            "parameterSchema": {
                "metricsWindow": "7d",
                "labelFilter": "env=dev,test,staging,qa,sandbox",
            },
            "responseFormat": "gce_instance_list",
            "costThresholds": {"minSavingsUSD": 15, "minResourceCount": 1},
        },
    },
    # ─── S3 / Object Storage Tiering ──────────────────────────────────
    "s3-001": {
        "aws": {
            "apiEndpoint": "s3:ListBuckets + s3:GetBucketIntelligentTieringConfiguration",
            "parameterSchema": {
                "storageClass": "INTELLIGENT_TIERING",
            },
            "responseFormat": "s3_bucket_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Storage/storageAccounts + Microsoft.Storage/blobServices",
            "parameterSchema": {
                "storageClass": "Cool",
            },
            "responseFormat": "azure_blob_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "storage.buckets.list + storage.buckets.get",
            "parameterSchema": {
                "storageClass": "NEARLINE",
            },
            "responseFormat": "gcs_bucket_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
    },
    # ─── S3 / Lifecycle Policies ───────────────────────────────────────
    "s3-002": {
        "aws": {
            "apiEndpoint": "s3:GetBucketLifecycleConfiguration",
            "parameterSchema": {
                "retentionDays": 30,
                "archiveDays": 90,
            },
            "responseFormat": "s3_bucket_list",
            "costThresholds": {"minSavingsUSD": 5},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Storage/storageAccounts/managementPolicies",
            "parameterSchema": {
                "retentionDays": 30,
                "archiveDays": 90,
            },
            "responseFormat": "azure_blob_list",
            "costThresholds": {"minSavingsUSD": 5},
        },
        "gcp": {
            "apiEndpoint": "storage.buckets.get (lifecycle field)",
            "parameterSchema": {
                "retentionDays": 30,
                "archiveDays": 90,
            },
            "responseFormat": "gcs_bucket_list",
            "costThresholds": {"minSavingsUSD": 5},
        },
    },
    # ─── RDS / Database Right-Sizing ──────────────────────────────────
    "rds-001": {
        "aws": {
            "apiEndpoint": "rds:DescribeDBInstances + cloudwatch:GetMetricStatistics",
            "parameterSchema": {
                "metricsWindow": "30d",
                "cpuThreshold": 30,
                "connectionThreshold": 10,
            },
            "responseFormat": "rds_instance_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Sql/servers/databases + Microsoft.Monitor/metrics",
            "parameterSchema": {
                "metricsWindow": "30d",
                "cpuThreshold": 30,
                "dtuThreshold": 20,
            },
            "responseFormat": "azure_sql_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "sqladmin.instances.list + monitoring.timeSeries.list",
            "parameterSchema": {
                "metricsWindow": "30d",
                "cpuThreshold": 30,
            },
            "responseFormat": "cloudsql_instance_list",
            "costThresholds": {"minSavingsUSD": 20, "minResourceCount": 1},
        },
    },
    # ─── Lambda / Serverless Right-Sizing ─────────────────────────────
    "lambda-001": {
        "aws": {
            "apiEndpoint": "lambda:ListFunctions + cloudwatch:GetMetricStatistics",
            "parameterSchema": {
                "metricsWindow": "30d",
                "metrics": ["Duration", "Invocations", "ConcurrentExecutions"],
            },
            "responseFormat": "lambda_function_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Web/sites + Microsoft.Monitor/metrics",
            "parameterSchema": {
                "metricsWindow": "30d",
                "metrics": ["FunctionExecutionCount", "FunctionExecutionUnits"],
            },
            "responseFormat": "azure_functions_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "cloudfunctions.projects.locations.functions.list + monitoring.timeSeries.list",
            "parameterSchema": {
                "metricsWindow": "30d",
                "metrics": ["function/execution_count", "function/execution_times"],
            },
            "responseFormat": "gcf_function_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
    },
    # ─── EBS / Volume Type Optimization ───────────────────────────────
    "ebs-001": {
        "aws": {
            "apiEndpoint": "ec2:DescribeVolumes",
            "parameterSchema": {
                "volumeTypeFilter": "gp2",
            },
            "responseFormat": "ebs_volume_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Compute/disks",
            "parameterSchema": {
                "diskSkuFilter": "Standard_LRS",
            },
            "responseFormat": "azure_disk_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
        "gcp": {
            "apiEndpoint": "compute.disks.list",
            "parameterSchema": {
                "diskTypeFilter": "pd-standard",
            },
            "responseFormat": "gce_disk_list",
            "costThresholds": {"minSavingsUSD": 5, "minResourceCount": 1},
        },
    },
    # ─── General / Budgets ─────────────────────────────────────────────
    "general-002": {
        "aws": {
            "apiEndpoint": "budgets:DescribeBudgets",
            "parameterSchema": {},
            "responseFormat": "aws_budgets_list",
            "costThresholds": {},
        },
        "azure": {
            "apiEndpoint": "Microsoft.CostManagement/budgets",
            "parameterSchema": {},
            "responseFormat": "azure_budgets_list",
            "costThresholds": {},
        },
        "gcp": {
            "apiEndpoint": "cloudbilling.billingAccounts.budgets.list",
            "parameterSchema": {},
            "responseFormat": "gcp_budgets_list",
            "costThresholds": {},
        },
    },
    # ─── General / Cost Allocation Tags ────────────────────────────────
    "general-005": {
        "aws": {
            "apiEndpoint": "ce:GetTags + resourcegroupstaggingapi:GetResources",
            "parameterSchema": {
                "requiredTags": ["Project", "Environment", "Owner"],
            },
            "responseFormat": "tag_compliance_report",
            "costThresholds": {"minResourceCount": 5},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Resources/tags + Microsoft.CostManagement/query",
            "parameterSchema": {
                "requiredTags": ["Project", "Environment", "Owner"],
            },
            "responseFormat": "azure_tag_report",
            "costThresholds": {"minResourceCount": 5},
        },
        "gcp": {
            "apiEndpoint": "cloudresourcemanager.projects.get + cloudbilling.billingAccounts.projects",
            "parameterSchema": {
                "requiredLabels": ["project", "environment", "owner"],
            },
            "responseFormat": "gcp_label_report",
            "costThresholds": {"minResourceCount": 5},
        },
    },
    # ─── NAT Gateway / VPC Endpoints ──────────────────────────────────
    "nat-001": {
        "aws": {
            "apiEndpoint": "ec2:DescribeVpcEndpoints + cloudwatch:GetMetricStatistics",
            "parameterSchema": {
                "metricsWindow": "30d",
                "metric": "BytesOutToDestination",
            },
            "responseFormat": "vpc_endpoint_list",
            "costThresholds": {"minSavingsUSD": 10},
        },
        "azure": {
            "apiEndpoint": "Microsoft.Network/virtualNetworks/subnets + Microsoft.Network/privateEndpoints",
            "parameterSchema": {
                "metricsWindow": "30d",
            },
            "responseFormat": "azure_private_endpoint_list",
            "costThresholds": {"minSavingsUSD": 10},
        },
        "gcp": {
            "apiEndpoint": "compute.routers.list + compute.addresses.list",
            "parameterSchema": {
                "metricsWindow": "30d",
            },
            "responseFormat": "gcp_nat_list",
            "costThresholds": {"minSavingsUSD": 10},
        },
    },
    # ─── OpenAI / Model Selection ──────────────────────────────────────
    "openai-model-selection-001": {
        "openai": {
            "apiEndpoint": "api.openai.com/v1/organization/usage",
            "parameterSchema": {
                "metricsWindow": "30d",
                "modelFilter": ["gpt-4", "gpt-4-turbo"],
            },
            "responseFormat": "openai_usage_report",
            "costThresholds": {"minSavingsUSD": 50},
        },
    },
    "openai-model-selection-002": {
        "openai": {
            "apiEndpoint": "api.openai.com/v1/organization/usage",
            "parameterSchema": {
                "metricsWindow": "30d",
                "modelFilter": ["gpt-4"],
            },
            "responseFormat": "openai_usage_report",
            "costThresholds": {"minSavingsUSD": 100},
        },
    },
    # ─── OpenAI / Batch API ────────────────────────────────────────────
    "openai-batch-001": {
        "openai": {
            "apiEndpoint": "api.openai.com/v1/organization/usage + api.openai.com/v1/batches",
            "parameterSchema": {
                "metricsWindow": "30d",
                "syncCallThreshold": 100,
            },
            "responseFormat": "openai_usage_report",
            "costThresholds": {"minSavingsUSD": 100},
        },
    },
}


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------


def get_tip_key_from_id(tip_id: str) -> dict:
    """
    Map a tipId to its (service, tipId) primary key pair.

    For tips that follow the pattern 'service-NNN', the service is derived
    from the ID prefix. For OpenAI tips, the service is looked up from
    a known mapping.
    """
    # OpenAI tips have varied service values; map them explicitly
    openai_service_map = {
        "openai-model-selection-001": "GPT-4",
        "openai-model-selection-002": "GPT-4o",
        "openai-batch-001": "Batch API",
    }

    if tip_id in openai_service_map:
        return {"service": openai_service_map[tip_id], "tipId": tip_id}

    # Standard tips: prefix maps to service
    prefix_to_service = {
        "ec2": "EC2",
        "s3": "S3",
        "rds": "RDS",
        "lambda": "Lambda",
        "ebs": "EBS",
        "nat": "NAT Gateway",
        "general": "General",
        "cloudfront": "CloudFront",
        "data-transfer": "Data Transfer",
    }

    for prefix, service in prefix_to_service.items():
        if tip_id.startswith(prefix + "-"):
            return {"service": service, "tipId": tip_id}

    # Fallback: use the tip_id prefix before last dash as service
    parts = tip_id.rsplit("-", 1)
    return {"service": parts[0].upper() if len(parts) > 1 else tip_id, "tipId": tip_id}


def enrich_tip(table, tip_id: str, provider_routing: dict, dry_run: bool = False) -> bool:
    """
    Update a single tip item with providerRouting metadata.

    Uses an UpdateExpression to add the providerRouting attribute without
    overwriting other fields. Uses a ConditionExpression to ensure the
    item exists before updating.

    Returns True if successful, False otherwise.
    """
    key = get_tip_key_from_id(tip_id)

    if dry_run:
        logger.info(
            "  [DRY-RUN] Would update %s/%s with %d provider entries",
            key["service"],
            key["tipId"],
            len(provider_routing),
        )
        return True

    try:
        table.update_item(
            Key=key,
            UpdateExpression="SET providerRouting = :pr",
            ExpressionAttributeValues={":pr": provider_routing},
            ConditionExpression="attribute_exists(service) AND attribute_exists(tipId)",
        )
        logger.info(
            "  Updated %s/%s with %d provider entries",
            key["service"],
            key["tipId"],
            len(provider_routing),
        )
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ConditionalCheckFailedException":
            logger.warning(
                "  SKIP: Tip %s/%s not found in table (may not be seeded yet)",
                key["service"],
                key["tipId"],
            )
        else:
            logger.error(
                "  FAILED to update %s/%s: %s",
                key["service"],
                key["tipId"],
                e.response["Error"]["Message"],
            )
        return False


def run_migration(region: str, dry_run: bool = False, single_tip: str = None):
    """
    Run the providerRouting enrichment migration.

    Args:
        region: AWS region where the Tips table lives
        dry_run: If True, log what would be done without writing
        single_tip: If set, only enrich this specific tip ID
    """
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table access
    try:
        table.load()
    except ClientError as e:
        logger.error(
            "Cannot access table '%s' in region '%s': %s",
            TABLE_NAME,
            region,
            e.response["Error"]["Message"],
        )
        sys.exit(1)

    logger.info("Table: %s (region: %s)", TABLE_NAME, region)
    logger.info("Mode: %s", "DRY-RUN" if dry_run else "LIVE")
    logger.info("")

    tips_to_process = PROVIDER_ROUTING_MAP
    if single_tip:
        if single_tip not in PROVIDER_ROUTING_MAP:
            logger.error("Tip ID '%s' not found in PROVIDER_ROUTING_MAP", single_tip)
            sys.exit(1)
        tips_to_process = {single_tip: PROVIDER_ROUTING_MAP[single_tip]}

    updated = 0
    skipped = 0
    failed = 0

    for tip_id, provider_routing in tips_to_process.items():
        success = enrich_tip(table, tip_id, provider_routing, dry_run=dry_run)
        if success:
            updated += 1
        else:
            # Check if it's a skip (item not found) vs actual failure
            skipped += 1

    logger.info("")
    logger.info("─" * 50)
    logger.info("Migration complete.")
    logger.info("  Updated: %d", updated)
    logger.info("  Skipped/Failed: %d", skipped)
    logger.info("  Total tips with providerRouting definitions: %d", len(PROVIDER_ROUTING_MAP))

    if skipped > 0 and not dry_run:
        logger.warning(
            "Some tips were skipped. Run seed-dynamodb.py first to ensure all tips exist."
        )


def main():
    region = REGION
    dry_run = False
    single_tip = None

    # Parse CLI arguments
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--region" and i + 1 < len(args):
            region = args[i + 1]
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--tip-id" and i + 1 < len(args):
            single_tip = args[i + 1]
            i += 2
        elif args[i] in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        else:
            logger.error("Unknown argument: %s", args[i])
            print(__doc__)
            sys.exit(1)

    logger.info("═" * 50)
    logger.info("Tips Table providerRouting Enrichment Migration")
    logger.info("═" * 50)
    logger.info("")

    run_migration(region=region, dry_run=dry_run, single_tip=single_tip)


if __name__ == "__main__":
    main()
