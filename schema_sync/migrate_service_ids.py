"""
Migration Script — Populates serviceId from legacy serviceKey values.

Idempotent: running multiple times produces the same result.
Does NOT remove legacy serviceKey field.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

from .service_id import validate_service_id

logger = logging.getLogger(__name__)

TIPS_TABLE_NAME = os.environ.get("TIPS_TABLE_NAME", "ViewMyBill-CostOptimizationTips")

# Legacy serviceKey → canonical Service_ID mapping
LEGACY_SERVICE_KEY_MAP: dict[str, str] = {
    "Amazon EC2": "aws:ec2",
    "EC2": "aws:ec2",
    "Amazon S3": "aws:s3",
    "S3": "aws:s3",
    "Amazon Simple Storage Service": "aws:s3",
    "Amazon RDS": "aws:rds",
    "RDS": "aws:rds",
    "Amazon Relational Database Service": "aws:rds",
    "AWS Lambda": "aws:lambda",
    "Lambda": "aws:lambda",
    "EC2 - Other": "aws:ebs",
    "Amazon EBS": "aws:ebs",
    "EBS": "aws:ebs",
    "Elastic Block Store": "aws:ebs",
    "Amazon Virtual Private Cloud": "aws:vpc",
    "VPC": "aws:vpc",
    "Amazon VPC": "aws:vpc",
    "Amazon CloudFront": "aws:cloudfront",
    "CloudFront": "aws:cloudfront",
}


def migrate_tips_table(records: list[dict] | None = None) -> dict:
    """
    Scan all tip records and populate serviceId from serviceKey.

    If records is provided, operates on the in-memory list (for testing).
    Otherwise, scans and updates DynamoDB directly.

    Args:
        records: Optional list of records for in-memory migration (testing).

    Returns:
        Summary dict: {migrated: int, skipped: int, total: int}
    """
    if records is not None:
        return _migrate_in_memory(records)
    return _migrate_dynamodb()


def _migrate_in_memory(records: list[dict]) -> dict:
    """Migrate records in memory (for testing / pure function usage)."""
    migrated = 0
    skipped = 0
    total = len(records)

    for record in records:
        # Already has a valid serviceId — skip (idempotent)
        if record.get("serviceId") and validate_service_id(record["serviceId"]):
            skipped += 1
            continue

        service_key = record.get("serviceKey")
        if not service_key:
            skipped += 1
            continue

        canonical_id = LEGACY_SERVICE_KEY_MAP.get(service_key)
        if canonical_id:
            record["serviceId"] = canonical_id
            migrated += 1
        else:
            logger.warning(
                "Unknown serviceKey '%s' for record '%s', skipping",
                service_key,
                record.get("id", "unknown"),
            )
            skipped += 1

    return {"migrated": migrated, "skipped": skipped, "total": total}


def _migrate_dynamodb() -> dict:
    """Scan DynamoDB and update records with serviceId."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE_NAME)

    migrated = 0
    skipped = 0
    total = 0

    # Scan all records
    response = table.scan()
    items = response.get("Items", [])

    while True:
        for item in items:
            total += 1

            # Skip metadata records
            if item.get("service") == "SCHEMA_META":
                skipped += 1
                continue

            # Already has a valid serviceId
            if item.get("serviceId") and validate_service_id(item["serviceId"]):
                skipped += 1
                continue

            service_key = item.get("serviceKey")
            if not service_key:
                skipped += 1
                continue

            canonical_id = LEGACY_SERVICE_KEY_MAP.get(service_key)
            if not canonical_id:
                logger.warning(
                    "Unknown serviceKey '%s' for record '%s', skipping",
                    service_key,
                    item.get("id", "unknown"),
                )
                skipped += 1
                continue

            # Update the record
            try:
                table.update_item(
                    Key={"service": item["service"], "id": item["id"]},
                    UpdateExpression="SET serviceId = :sid",
                    ExpressionAttributeValues={":sid": canonical_id},
                )
                migrated += 1
            except ClientError as e:
                logger.error(
                    "Failed to update record '%s': %s", item.get("id"), e
                )
                skipped += 1

        # Paginate
        if "LastEvaluatedKey" not in response:
            break
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items = response.get("Items", [])

    summary = {"migrated": migrated, "skipped": skipped, "total": total}
    logger.info("Migration complete: %s", summary)
    return summary
