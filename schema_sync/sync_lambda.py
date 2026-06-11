"""
Sync Lambda — Orchestrates schema generation and Bedrock Agent update.

Triggered by DynamoDB Streams or direct admin invocation.
Handles: generation → validation → backward compat check → backup → push.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from .schema_generator import (
    generate_schema,
    validate_schema,
    check_backward_compatibility,
    SchemaValidationError,
    REQUIRED_OPERATION_IDS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
TIPS_TABLE_NAME = os.environ.get("TIPS_TABLE_NAME", "ViewMyBill-CostOptimizationTips")
SCHEMA_BUCKET = os.environ.get("SCHEMA_BUCKET", "slashmybill-schema-versions")
AGENT_ID = os.environ.get("AGENT_ID", "")
ACTION_GROUP_NAME = os.environ.get("ACTION_GROUP_NAME", "FinOpsActions")
ACTION_GROUP_ID = os.environ.get("ACTION_GROUP_ID", "")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")

# Retry configuration
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1


def lambda_handler(event, context) -> dict:
    """
    Entry point. Handles both DynamoDB Stream events and direct invocations.

    Direct invocation payloads:
        {"action": "sync", "dryRun": false}
        {"action": "rollback", "version": 5}
    """
    logger.info("Sync Lambda invoked with event: %s", json.dumps(event)[:500])

    # Determine if this is a direct invocation or stream event
    if "action" in event:
        action = event["action"]
        if action == "rollback":
            return _handle_rollback(event.get("version"))
        dry_run = event.get("dryRun", False)
        return _handle_sync(dry_run=dry_run)

    # DynamoDB Stream event
    if "Records" in event:
        # Check if any records involve toolDefinition changes
        relevant = any(_is_tool_relevant_event(r) for r in event.get("Records", []))
        if not relevant:
            logger.info("No tool-relevant changes detected, skipping")
            return {"statusCode": 200, "body": "No relevant changes"}
        return _handle_sync(dry_run=False)

    # Default: treat as manual sync
    return _handle_sync(dry_run=False)


def _handle_sync(dry_run: bool = False) -> dict:
    """Full sync: scan tips → generate → validate → backup → push."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE_NAME)

    # Scan all tip records
    tip_records = _scan_all_tips(table)
    logger.info("Scanned %d tip records", len(tip_records))

    # Generate schema
    try:
        schema = generate_schema(tip_records)
    except SchemaValidationError as e:
        _publish_alert("SCHEMA_VALIDATION_FAILURE", str(e.errors))
        return {
            "statusCode": 400,
            "body": f"Schema validation failed: {e.errors}",
        }

    # Validate (double-check)
    errors = validate_schema(schema)
    if errors:
        _publish_alert("SCHEMA_VALIDATION_FAILURE", str(errors))
        return {"statusCode": 400, "body": f"Validation errors: {errors}"}

    # Backward compatibility check
    missing_ops = check_backward_compatibility(schema)
    if missing_ops:
        _publish_alert(
            "BACKWARD_COMPAT_FAILURE",
            f"Missing operationIds: {missing_ops}",
        )
        return {
            "statusCode": 400,
            "body": f"Backward compatibility failed. Missing: {missing_ops}",
        }

    # Get current metadata
    metadata = _get_metadata()
    current_version = metadata.get("currentVersion", 0)
    new_version = current_version + 1

    # Compute operation count and providers
    operation_count = len(schema.get("paths", {}))
    providers = _extract_providers_from_tips(tip_records)

    if dry_run:
        # Return diff summary without pushing
        diff = _compute_diff(metadata, schema)
        return {
            "statusCode": 200,
            "dryRun": True,
            "schema": schema,
            "diff": diff,
            "operationCount": operation_count,
            "providers": providers,
            "warnings": [],
        }

    # Backup current schema to S3
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s3_key = f"v{new_version}/{timestamp}.json"
    _backup_current_schema(schema, s3_key)

    # Push to Bedrock Agent
    push_result = _push_to_bedrock(schema)
    if not push_result.get("success"):
        return {
            "statusCode": 500,
            "body": f"Bedrock push failed: {push_result.get('error')}",
        }

    # Update metadata
    _update_metadata(new_version, timestamp, operation_count, providers, s3_key)

    logger.info(
        "Schema sync complete. Version: %d, Operations: %d, Providers: %s",
        new_version,
        operation_count,
        providers,
    )

    return {
        "statusCode": 200,
        "version": new_version,
        "operationCount": operation_count,
        "providers": providers,
    }


def _handle_rollback(version: int | None) -> dict:
    """Rollback to a previous schema version from S3."""
    if not version:
        return {"statusCode": 400, "body": "Missing 'version' parameter"}

    s3 = boto3.client("s3")

    # List objects with the version prefix
    prefix = f"v{version}/"
    try:
        response = s3.list_objects_v2(Bucket=SCHEMA_BUCKET, Prefix=prefix, MaxKeys=1)
    except ClientError as e:
        return {"statusCode": 500, "body": f"S3 list failed: {e}"}

    contents = response.get("Contents", [])
    if not contents:
        return {"statusCode": 404, "body": f"No schema found for version {version}"}

    # Get the schema
    s3_key = contents[0]["Key"]
    try:
        obj = s3.get_object(Bucket=SCHEMA_BUCKET, Key=s3_key)
        schema = json.loads(obj["Body"].read().decode("utf-8"))
    except (ClientError, json.JSONDecodeError) as e:
        return {"statusCode": 500, "body": f"Failed to read schema: {e}"}

    # Push to Bedrock
    push_result = _push_to_bedrock(schema)
    if not push_result.get("success"):
        return {"statusCode": 500, "body": f"Rollback push failed: {push_result.get('error')}"}

    # Update metadata
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    operation_count = len(schema.get("paths", {}))
    _update_metadata(version, timestamp, operation_count, [], s3_key)

    return {"statusCode": 200, "rolledBackToVersion": version}


def _is_tool_relevant_event(record: dict) -> bool:
    """Check if a DynamoDB stream record involves a toolDefinition change."""
    event_name = record.get("eventName", "")

    if event_name == "REMOVE":
        # Check if the old image had a toolDefinition
        old_image = record.get("dynamodb", {}).get("OldImage", {})
        return "toolDefinition" in old_image

    if event_name in ("INSERT", "MODIFY"):
        new_image = record.get("dynamodb", {}).get("NewImage", {})
        old_image = record.get("dynamodb", {}).get("OldImage", {})
        # Relevant if new or old image has toolDefinition
        return "toolDefinition" in new_image or "toolDefinition" in old_image

    return False


def _scan_all_tips(table) -> list[dict]:
    """Scan all records from the Tips table."""
    items = []
    response = table.scan()
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))

    return items


def _backup_current_schema(schema: dict, s3_key: str) -> str:
    """Write schema to S3 and return the S3 key."""
    s3 = boto3.client("s3")
    try:
        s3.put_object(
            Bucket=SCHEMA_BUCKET,
            Key=s3_key,
            Body=json.dumps(schema, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Schema backed up to s3://%s/%s", SCHEMA_BUCKET, s3_key)
    except ClientError as e:
        logger.warning("S3 backup failed (non-fatal): %s", e)
    return s3_key


def _push_to_bedrock(schema: dict) -> dict:
    """
    Call update_agent_action_group with retry logic.

    Returns dict with 'success' bool and optional 'error' or 'response'.
    """
    client = boto3.client("bedrock-agent")

    for attempt in range(MAX_RETRIES):
        try:
            response = client.update_agent_action_group(
                agentId=AGENT_ID,
                agentVersion="DRAFT",
                actionGroupId=ACTION_GROUP_ID,
                actionGroupName=ACTION_GROUP_NAME,
                apiSchema={
                    "payload": json.dumps(schema),
                },
            )
            logger.info(
                "Bedrock Agent updated successfully: %s",
                response.get("agentActionGroup", {}).get("actionGroupId"),
            )
            return {"success": True, "response": response}

        except ClientError as e:
            error_msg = str(e)
            logger.error(
                "Bedrock push attempt %d/%d failed: %s",
                attempt + 1,
                MAX_RETRIES,
                error_msg,
            )
            if attempt < MAX_RETRIES - 1:
                backoff = BASE_BACKOFF_SECONDS * (2**attempt)
                time.sleep(backoff)
            else:
                _publish_alert("BEDROCK_API_FAILURE", error_msg)
                return {"success": False, "error": error_msg}

    return {"success": False, "error": "Max retries exceeded"}


def _get_metadata() -> dict:
    """Get the current schema metadata from DynamoDB."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        response = table.get_item(Key={"service": "SCHEMA_META", "id": "CURRENT"})
        return response.get("Item", {})
    except ClientError:
        return {}


def _update_metadata(
    version: int,
    timestamp: str,
    operation_count: int,
    providers: list[str],
    s3_key: str,
) -> None:
    """Update the schema metadata record."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        table.put_item(
            Item={
                "service": "SCHEMA_META",
                "id": "CURRENT",
                "currentVersion": version,
                "lastSyncTimestamp": timestamp,
                "syncStatus": "SUCCESS",
                "operationCount": operation_count,
                "providersIncluded": providers,
                "s3Key": s3_key,
                "lastError": None,
            }
        )
    except ClientError as e:
        logger.error("Failed to update metadata: %s", e)


def _publish_alert(error_type: str, message: str) -> None:
    """Publish an alert to the SNS topic."""
    if not ALERT_TOPIC_ARN:
        logger.warning("No ALERT_TOPIC_ARN configured, skipping alert")
        return

    sns = boto3.client("sns")
    try:
        sns.publish(
            TopicArn=ALERT_TOPIC_ARN,
            Subject=f"SlashMyBill Schema Sync Alert: {error_type}",
            Message=json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "errorType": error_type,
                    "message": message,
                }
            ),
        )
    except ClientError as e:
        logger.error("Failed to publish SNS alert: %s", e)


def _compute_diff(metadata: dict, new_schema: dict) -> dict:
    """Compute a diff between current active schema and new schema."""
    # Get current schema from S3 if available
    current_s3_key = metadata.get("s3Key")
    current_ops = set()

    if current_s3_key:
        s3 = boto3.client("s3")
        try:
            obj = s3.get_object(Bucket=SCHEMA_BUCKET, Key=current_s3_key)
            current_schema = json.loads(obj["Body"].read().decode("utf-8"))
            for path_item in current_schema.get("paths", {}).values():
                for op in path_item.values():
                    if isinstance(op, dict) and "operationId" in op:
                        current_ops.add(op["operationId"])
        except (ClientError, json.JSONDecodeError):
            pass

    new_ops = set()
    for path_item in new_schema.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict) and "operationId" in op:
                new_ops.add(op["operationId"])

    return {
        "added": sorted(new_ops - current_ops),
        "removed": sorted(current_ops - new_ops),
        "unchanged": sorted(current_ops & new_ops),
    }


def _extract_providers_from_tips(tip_records: list[dict]) -> list[str]:
    """Extract unique providers from tip records with tool definitions."""
    providers = set()
    for record in tip_records:
        tool_def = record.get("toolDefinition")
        if tool_def and tool_def.get("provider"):
            providers.add(tool_def["provider"])
    return sorted(providers)
