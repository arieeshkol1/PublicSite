"""
Tips Sync Lambda - Entry point.

Orchestrates the sync process: fetches tips from AWS sources,
computes deltas, and writes changes to DynamoDB.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from metrics import publish_failure_metric, publish_success_metrics
from models import generate_tip_id
from sources.baseline_file import load_baseline_tips
from sources.cost_optimization_hub import fetch_recommendations
from sources.trusted_advisor import fetch_cost_checks
from sync_engine import apply_deltas, compute_deltas, merge_sources

# Configure structured JSON logging at INFO level
logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = "ViewMyBill-CostOptimizationTips"
REGION = "us-east-1"
LOCK_TTL_SECONDS = 900  # 15 minutes


def lambda_handler(event, context):
    """Entry point for the Tips Sync Lambda.

    Handles both scheduled (EventBridge) and manual triggers.
    Orchestrates: lock acquisition, source fetching, merge, delta
    detection, apply, metadata write, lock release, and metrics.

    Args:
        event: Lambda event. Contains {"manual": true} for manual triggers.
        context: Lambda context object.

    Returns:
        dict with statusCode and body containing sync results.
    """
    start_time = time.time()

    # (1) Detect trigger type
    trigger_type = "manual" if event.get("manual", False) else "scheduled"
    logger.info(json.dumps({
        "action": "sync_started",
        "triggerType": trigger_type,
    }))

    # Initialize AWS resources
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # (2) Acquire SYNC_LOCK via DynamoDB conditional put with 15-min TTL
    lock_acquired = _acquire_lock(table)

    # (3) On lock failure, log and exit gracefully
    if not lock_acquired:
        logger.info(json.dumps({
            "action": "sync_skipped",
            "reason": "concurrent_execution",
            "message": "Another sync is already in progress",
        }))
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Sync skipped — concurrent execution detected",
                "triggerType": trigger_type,
            }),
        }

    try:
        # (4) Fetch from all sources with graceful degradation
        sources_queried = ["cost-optimization-hub", "trusted-advisor", "baseline"]
        sources_succeeded = []
        sources_failed = []

        # Fetch from Cost Optimization Hub
        coh_tips = _fetch_coh_tips(sources_succeeded, sources_failed)

        # Fetch from Trusted Advisor
        ta_tips = _fetch_ta_tips(sources_succeeded, sources_failed)

        # Fetch from baseline file
        baseline_tips = _fetch_baseline_tips(sources_succeeded, sources_failed)

        # If ALL sources fail, publish failure metric and return error
        if not sources_succeeded:
            logger.info(json.dumps({
                "action": "sync_failed",
                "reason": "all_sources_failed",
                "sourcesFailed": sources_failed,
            }))
            publish_failure_metric()
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "message": "All sources failed",
                    "sourcesFailed": sources_failed,
                }),
            }

        # (5) Merge and compute deltas
        merged_tips = merge_sources(baseline_tips, coh_tips, ta_tips)

        logger.info(json.dumps({
            "action": "sources_merged",
            "mergedCount": len(merged_tips),
            "sourcesSucceeded": sources_succeeded,
            "sourcesFailed": sources_failed,
        }))

        # Scan existing tips from DynamoDB to get current state
        existing_tips = _scan_existing_tips(table)

        # Assign IDs to new tips that don't have them (from COH/TA)
        existing_ids = set(existing_tips.keys())
        for tip in merged_tips:
            if not tip.get("id"):
                service = tip.get("service", "General")
                new_id = generate_tip_id(service, existing_ids)
                tip["id"] = new_id
                existing_ids.add(new_id)

        # Compute deltas
        inserts, updates, unchanged_count = compute_deltas(merged_tips, existing_tips)

        logger.info(json.dumps({
            "action": "deltas_computed",
            "inserts": len(inserts),
            "updates": len(updates),
            "unchanged": unchanged_count,
        }))

        # (6) Apply deltas
        inserted_count, updated_count, conflict_ids = apply_deltas(table, inserts, updates)

        logger.info(json.dumps({
            "action": "deltas_applied",
            "inserted": inserted_count,
            "updated": updated_count,
            "conflicts": len(conflict_ids),
        }))

        # (7) Write SYNC_METADATA record with all stats
        duration_ms = int((time.time() - start_time) * 1000)
        _write_sync_metadata(
            table=table,
            trigger_type=trigger_type,
            sources_queried=sources_queried,
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
            tips_inserted=inserted_count,
            tips_updated=updated_count,
            tips_unchanged=unchanged_count,
            duration_ms=duration_ms,
        )

        # (9) Publish CloudWatch success metrics
        publish_success_metrics(duration_ms)

        _write_sync_log(table=table, trigger_type=trigger_type, sources_queried=sources_queried, sources_succeeded=sources_succeeded, sources_failed=sources_failed, tips_inserted=inserted_count, tips_updated=updated_count, tips_unchanged=unchanged_count, duration_ms=duration_ms, status="success")

        logger.info(json.dumps({
            "action": "sync_completed",
            "triggerType": trigger_type,
            "tipsInserted": inserted_count,
            "tipsUpdated": updated_count,
            "tipsUnchanged": unchanged_count,
            "durationMs": duration_ms,
        }))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Sync completed successfully",
                "triggerType": trigger_type,
                "tipsInserted": inserted_count,
                "tipsUpdated": updated_count,
                "tipsUnchanged": unchanged_count,
                "durationMs": duration_ms,
            }),
        }

    except Exception as e:
        logger.error(json.dumps({
            "action": "sync_error",
            "error": str(e),
            "errorType": type(e).__name__,
        }))
        publish_failure_metric()
        try:
            duration_ms = int((time.time() - start_time) * 1000)
            _write_sync_log(table=table, trigger_type=trigger_type, sources_queried=sources_queried if 'sources_queried' in dir() else [], sources_succeeded=sources_succeeded if 'sources_succeeded' in dir() else [], sources_failed=sources_failed if 'sources_failed' in dir() else [], tips_inserted=0, tips_updated=0, tips_unchanged=0, duration_ms=duration_ms, status="failed", error_message=str(e))
        except Exception:
            pass
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Sync failed with unrecoverable error",
                "error": str(e),
            }),
        }

    finally:
        # (8) Release lock
        _release_lock(table)


def _acquire_lock(table) -> bool:
    """Acquire the SYNC_LOCK via DynamoDB conditional put with 15-min TTL.

    Args:
        table: boto3 DynamoDB Table resource.

    Returns:
        True if lock was acquired, False if another execution holds it.
    """
    now = datetime.now(timezone.utc)
    ttl_epoch = int(now.timestamp()) + LOCK_TTL_SECONDS

    try:
        table.put_item(
            Item={
                "service": "SYSTEM",
                "tipId": "SYNC_LOCK",
                "lockedAt": now.isoformat(),
                "ttl": ttl_epoch,
            },
            ConditionExpression="attribute_not_exists(tipId)",
        )
        logger.info(json.dumps({
            "action": "lock_acquired",
            "lockedAt": now.isoformat(),
            "ttlEpoch": ttl_epoch,
        }))
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning(json.dumps({
                "action": "lock_acquisition_failed",
                "reason": "lock_already_held",
            }))
            return False
        # Unexpected error — re-raise
        raise


def _release_lock(table) -> None:
    """Release the SYNC_LOCK by deleting the lock record.

    Args:
        table: boto3 DynamoDB Table resource.
    """
    try:
        table.delete_item(
            Key={"service": "SYSTEM", "tipId": "SYNC_LOCK"}
        )
        logger.info(json.dumps({
            "action": "lock_released",
        }))
    except Exception as e:
        # Lock release failure is non-fatal — TTL will clean it up
        logger.warning(json.dumps({
            "action": "lock_release_failed",
            "error": str(e),
        }))


def _fetch_coh_tips(sources_succeeded, sources_failed) -> list:
    """Fetch tips from Cost Optimization Hub with graceful degradation.

    Args:
        sources_succeeded: List to append source name on success.
        sources_failed: List to append source name on failure.

    Returns:
        List of tip dicts from COH, or empty list on error.
    """
    try:
        coh_client = boto3.client("cost-optimization-hub", region_name=REGION)
        tips = fetch_recommendations(coh_client)
        if tips is not None:
            sources_succeeded.append("cost-optimization-hub")
            logger.info(json.dumps({
                "action": "source_fetch_complete",
                "source": "cost-optimization-hub",
                "tipsCount": len(tips),
            }))
            return tips
        else:
            sources_failed.append("cost-optimization-hub")
            return []
    except Exception as e:
        logger.error(json.dumps({
            "action": "source_fetch_error",
            "source": "cost-optimization-hub",
            "error": str(e),
            "errorType": type(e).__name__,
        }))
        sources_failed.append("cost-optimization-hub")
        return []


def _fetch_ta_tips(sources_succeeded, sources_failed) -> list:
    """Fetch tips from Trusted Advisor with graceful degradation.

    Args:
        sources_succeeded: List to append source name on success.
        sources_failed: List to append source name on failure.

    Returns:
        List of tip dicts from TA, or empty list on error.
    """
    try:
        support_client = boto3.client("support", region_name=REGION)
        tips = fetch_cost_checks(support_client)
        if tips is not None:
            sources_succeeded.append("trusted-advisor")
            logger.info(json.dumps({
                "action": "source_fetch_complete",
                "source": "trusted-advisor",
                "tipsCount": len(tips),
            }))
            return tips
        else:
            sources_failed.append("trusted-advisor")
            return []
    except Exception as e:
        logger.error(json.dumps({
            "action": "source_fetch_error",
            "source": "trusted-advisor",
            "error": str(e),
            "errorType": type(e).__name__,
        }))
        sources_failed.append("trusted-advisor")
        return []


def _fetch_baseline_tips(sources_succeeded, sources_failed) -> list:
    """Fetch tips from the baseline file with graceful degradation.

    Args:
        sources_succeeded: List to append source name on success.
        sources_failed: List to append source name on failure.

    Returns:
        List of tip dicts from baseline file, or empty list on error.
    """
    try:
        baseline_path = os.path.join(
            os.path.dirname(__file__), "knowledge-base", "aws-cost-optimization-tips.json"
        )
        tips = load_baseline_tips(baseline_path)
        if tips:
            sources_succeeded.append("baseline")
            logger.info(json.dumps({
                "action": "source_fetch_complete",
                "source": "baseline",
                "tipsCount": len(tips),
            }))
        else:
            sources_failed.append("baseline")
            logger.warning(json.dumps({
                "action": "source_fetch_empty",
                "source": "baseline",
                "tipsCount": 0,
                "path": baseline_path,
            }))
        return tips
    except Exception as e:
        logger.error(json.dumps({
            "action": "source_fetch_error",
            "source": "baseline",
            "error": str(e),
            "errorType": type(e).__name__,
        }))
        sources_failed.append("baseline")
        return []


def _scan_existing_tips(table) -> dict:
    """Scan the DynamoDB table to get all existing tips.

    Returns a dict keyed by tip ID with the full item as value.
    Excludes SYSTEM records (SYNC_LOCK, SYNC_METADATA).

    Args:
        table: boto3 DynamoDB Table resource.

    Returns:
        Dict mapping tipId -> item dict for all existing tips.
    """
    existing = {}

    try:
        response = table.scan()
        items = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

        for item in items:
            # Skip SYSTEM records
            if item.get("service") == "SYSTEM":
                continue
            tip_id = item.get("tipId", item.get("id", ""))
            if tip_id:
                existing[tip_id] = item

        logger.info(json.dumps({
            "action": "existing_tips_scanned",
            "count": len(existing),
        }))

    except Exception as e:
        logger.error(json.dumps({
            "action": "scan_existing_tips_error",
            "error": str(e),
            "errorType": type(e).__name__,
        }))

    return existing


def _write_sync_metadata(
    table,
    trigger_type: str,
    sources_queried: list,
    sources_succeeded: list,
    sources_failed: list,
    tips_inserted: int,
    tips_updated: int,
    tips_unchanged: int,
    duration_ms: int,
) -> None:
    """Write the SYNC_METADATA record to the Tips_Table.

    Args:
        table: boto3 DynamoDB Table resource.
        trigger_type: "scheduled" or "manual".
        sources_queried: List of all source names queried.
        sources_succeeded: List of sources that returned data.
        sources_failed: List of sources that errored.
        tips_inserted: Count of new tips added.
        tips_updated: Count of tips updated.
        tips_unchanged: Count of tips skipped (unchanged).
        duration_ms: Total execution time in milliseconds.
    """
    now = datetime.now(timezone.utc).isoformat()

    metadata_item = {
        "service": "SYSTEM",
        "tipId": "SYNC_METADATA",
        "lastSyncTimestamp": now,
        "triggerType": trigger_type,
        "sourcesQueried": sources_queried,
        "sourcesSucceeded": sources_succeeded,
        "sourcesFailed": sources_failed,
        "tipsInserted": tips_inserted,
        "tipsUpdated": tips_updated,
        "tipsUnchanged": tips_unchanged,
        "durationMs": duration_ms,
    }

    try:
        table.put_item(Item=metadata_item)
        logger.info(json.dumps({
            "action": "sync_metadata_written",
            "lastSyncTimestamp": now,
            "triggerType": trigger_type,
            "tipsInserted": tips_inserted,
            "tipsUpdated": tips_updated,
            "tipsUnchanged": tips_unchanged,
            "durationMs": duration_ms,
        }))
    except Exception as e:
        logger.error(json.dumps({
            "action": "sync_metadata_write_error",
            "error": str(e),
            "errorType": type(e).__name__,
        }))


def _write_sync_log(table, trigger_type, sources_queried, sources_succeeded, sources_failed, tips_inserted, tips_updated, tips_unchanged, duration_ms, status, error_message=None):
    now = datetime.now(timezone.utc).isoformat()
    log_item = {
        "service": "SYSTEM",
        "tipId": f"SYNC_LOG#{now}",
        "timestamp": now,
        "triggerType": trigger_type,
        "sourcesQueried": sources_queried,
        "sourcesSucceeded": sources_succeeded,
        "sourcesFailed": sources_failed,
        "tipsInserted": tips_inserted,
        "tipsUpdated": tips_updated,
        "tipsUnchanged": tips_unchanged,
        "durationMs": duration_ms,
        "status": status,
    }
    if error_message:
        log_item["errorMessage"] = error_message
    try:
        table.put_item(Item=log_item)
        logger.info(json.dumps({"action": "sync_log_written", "status": status, "timestamp": now}))
    except Exception as e:
        logger.error(json.dumps({"action": "sync_log_write_error", "error": str(e)}))
