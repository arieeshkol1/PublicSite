"""
Sync Engine.

Handles merging tips from multiple sources, computing deltas
(inserts, updates, unchanged), and applying batch writes to DynamoDB.
"""

import json
import logging
import time
from typing import Any, Dict, List, Tuple

from botocore.exceptions import ClientError

from models import compute_content_hash

logger = logging.getLogger(__name__)


def merge_sources(
    baseline: List[Dict[str, Any]],
    coh: List[Dict[str, Any]],
    ta: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge tips from all sources with baseline file taking priority for duplicate IDs.

    The baseline (Tips_Source_File) takes precedence over AWS sources when the same
    tip ID exists in multiple sources. This preserves manually curated operational
    metadata from the baseline file.

    Args:
        baseline: Tips from the bundled aws-cost-optimization-tips.json file.
        coh: Tips from Cost Optimization Hub.
        ta: Tips from Trusted Advisor.

    Returns:
        Deduplicated list of tips to sync.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    # Add Trusted Advisor tips first (lowest priority)
    for tip in ta:
        tip_id = tip.get("id", "")
        if tip_id:
            merged[tip_id] = tip

    # Add Cost Optimization Hub tips (medium priority, overwrites TA)
    for tip in coh:
        tip_id = tip.get("id", "")
        if tip_id:
            merged[tip_id] = tip

    # Add baseline tips last (highest priority, overwrites COH and TA)
    for tip in baseline:
        tip_id = tip.get("id", "")
        if tip_id:
            merged[tip_id] = tip

    logger.info(
        json.dumps(
            {
                "action": "merge_sources",
                "baseline_count": len(baseline),
                "coh_count": len(coh),
                "ta_count": len(ta),
                "merged_count": len(merged),
            }
        )
    )

    return list(merged.values())


def compute_deltas(
    merged_tips: List[Dict[str, Any]],
    existing_tips: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """Compare merged tips against existing table records using content hash.

    Classifies each tip as:
    - Insert: tip ID does not exist in existing_tips
    - Update: tip ID exists but content hash differs
    - Unchanged: tip ID exists and content hash matches

    Never deletes existing tips (Req 3.5).

    For updates, only content fields change; operational fields are preserved (Req 3.3).

    Args:
        merged_tips: Deduplicated list of tips from merge_sources.
        existing_tips: Dict keyed by tip ID with existing DynamoDB records.

    Returns:
        Tuple of (tips_to_insert, tips_to_update, unchanged_count).
    """
    tips_to_insert: List[Dict[str, Any]] = []
    tips_to_update: List[Dict[str, Any]] = []
    unchanged_count = 0

    for tip in merged_tips:
        tip_id = tip.get("id", "")
        if not tip_id:
            continue

        # Compute content hash for this tip
        content_hash = compute_content_hash(
            title=tip.get("title", ""),
            description=tip.get("description", ""),
            estimated_savings=tip.get("estimatedSavings", ""),
            automated_check=tip.get("automatedCheck", ""),
        )

        if tip_id not in existing_tips:
            # New tip — classify as insert
            tip["contentHash"] = content_hash
            tips_to_insert.append(tip)
            logger.info(
                json.dumps(
                    {
                        "action": "classify_tip",
                        "tipId": tip_id,
                        "classification": "insert",
                    }
                )
            )
        else:
            existing = existing_tips[tip_id]
            existing_hash = existing.get("contentHash", "")

            if content_hash != existing_hash:
                # Content changed — classify as update
                # Preserve operational fields from existing record
                updated_tip = dict(existing)
                # Update content fields only
                updated_tip["title"] = tip.get("title", "")
                updated_tip["description"] = tip.get("description", "")
                updated_tip["estimatedSavings"] = tip.get("estimatedSavings", "")
                updated_tip["automatedCheck"] = tip.get("automatedCheck", "")
                updated_tip["contentHash"] = content_hash
                # Update sync metadata
                updated_tip["syncSource"] = tip.get("syncSource", "")
                updated_tip["lastSyncedAt"] = tip.get("lastSyncedAt", "")
                # Preserve category/service/difficulty from new tip if provided
                if tip.get("category"):
                    updated_tip["category"] = tip["category"]
                if tip.get("difficulty"):
                    updated_tip["difficulty"] = tip["difficulty"]

                tips_to_update.append(updated_tip)
                logger.info(
                    json.dumps(
                        {
                            "action": "classify_tip",
                            "tipId": tip_id,
                            "classification": "update",
                        }
                    )
                )
            else:
                # Hash matches — unchanged, skip
                unchanged_count += 1
                logger.info(
                    json.dumps(
                        {
                            "action": "classify_tip",
                            "tipId": tip_id,
                            "classification": "unchanged",
                        }
                    )
                )

    logger.info(
        json.dumps(
            {
                "action": "compute_deltas_summary",
                "inserts": len(tips_to_insert),
                "updates": len(tips_to_update),
                "unchanged": unchanged_count,
            }
        )
    )

    return tips_to_insert, tips_to_update, unchanged_count


def create_batches(
    items: List[Any], batch_size: int = 25
) -> List[List[Any]]:
    """Split items into batches of max batch_size.

    Args:
        items: List of items to batch.
        batch_size: Maximum number of items per batch (default 25).

    Returns:
        List of batches, each containing at most batch_size items.
    """
    if not items:
        return []
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def apply_deltas(
    table,
    inserts: List[Dict[str, Any]],
    updates: List[Dict[str, Any]],
) -> Tuple[int, int, List[str]]:
    """Write inserts and updates to DynamoDB with conditional writes.

    - Inserts use conditional puts with attribute_not_exists to prevent overwriting.
    - Updates use conditional expression on version attribute for optimistic locking.
    - On version conflict (ConditionalCheckFailedException): log, skip, continue.
    - Process in batches of max 25 items.
    - Exponential backoff retry for throttling errors (3 attempts, base 100ms, max 2000ms).

    Args:
        table: boto3 DynamoDB Table resource.
        inserts: List of tip dicts to insert as new items.
        updates: List of tip dicts to update (with preserved operational fields).

    Returns:
        Tuple of (inserted_count, updated_count, conflict_ids).
    """
    inserted_count = 0
    updated_count = 0
    conflict_ids: List[str] = []

    retryable_errors = {
        "ProvisionedThroughputExceededException",
        "ThrottlingException",
        "InternalServerError",
        "ServiceUnavailable",
    }

    def _execute_with_retry(operation, tip_id: str) -> bool:
        """Execute a DynamoDB operation with exponential backoff retry.

        Args:
            operation: Callable that performs the DynamoDB write.
            tip_id: Tip ID for logging.

        Returns:
            True if operation succeeded, False if it failed after retries.

        Raises:
            ClientError: If a ConditionalCheckFailedException occurs (handled by caller).
        """
        max_attempts = 3
        base_delay_ms = 100
        max_delay_ms = 2000

        for attempt in range(max_attempts):
            try:
                operation()
                return True
            except ClientError as e:
                error_code = e.response["Error"]["Code"]

                if error_code == "ConditionalCheckFailedException":
                    # Version conflict — don't retry, propagate to caller
                    raise

                if error_code in retryable_errors:
                    if attempt < max_attempts - 1:
                        delay_ms = min(
                            base_delay_ms * (2 ** attempt), max_delay_ms
                        )
                        logger.info(
                            json.dumps(
                                {
                                    "action": "retry_throttle",
                                    "tipId": tip_id,
                                    "attempt": attempt + 1,
                                    "delay_ms": delay_ms,
                                    "error_code": error_code,
                                }
                            )
                        )
                        time.sleep(delay_ms / 1000.0)
                    else:
                        logger.error(
                            json.dumps(
                                {
                                    "action": "retry_exhausted",
                                    "tipId": tip_id,
                                    "error_code": error_code,
                                }
                            )
                        )
                        return False
                else:
                    # Non-retryable error
                    logger.error(
                        json.dumps(
                            {
                                "action": "write_error",
                                "tipId": tip_id,
                                "error_code": error_code,
                                "error_message": str(e),
                            }
                        )
                    )
                    return False
        return False

    # Process inserts in batches
    insert_batches = create_batches(inserts, batch_size=25)
    for batch in insert_batches:
        for tip in batch:
            tip_id = tip.get("id", "")
            service = tip.get("service", "")

            def _do_insert(t=tip, s=service, tid=tip_id):
                item = dict(t)
                # Set DynamoDB keys
                item["service"] = s
                item["tipId"] = tid
                # Initialize version for new items
                item["version"] = 1
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(tipId)",
                )

            try:
                success = _execute_with_retry(_do_insert, tip_id)
                if success:
                    inserted_count += 1
                    logger.info(
                        json.dumps(
                            {
                                "action": "insert_tip",
                                "tipId": tip_id,
                                "service": service,
                            }
                        )
                    )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    # Item already exists — treat as conflict
                    conflict_ids.append(tip_id)
                    logger.info(
                        json.dumps(
                            {
                                "action": "insert_conflict",
                                "tipId": tip_id,
                                "reason": "item_already_exists",
                            }
                        )
                    )

    # Process updates in batches
    update_batches = create_batches(updates, batch_size=25)
    for batch in update_batches:
        for tip in batch:
            tip_id = tip.get("id", tip.get("tipId", ""))
            service = tip.get("service", "")
            current_version = tip.get("version", 1)

            def _do_update(t=tip, s=service, tid=tip_id, ver=current_version):
                item = dict(t)
                item["service"] = s
                item["tipId"] = tid
                # Increment version
                item["version"] = ver + 1
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_exists(tipId) AND version = :v",
                    ExpressionAttributeValues={":v": ver},
                )

            try:
                success = _execute_with_retry(_do_update, tip_id)
                if success:
                    updated_count += 1
                    logger.info(
                        json.dumps(
                            {
                                "action": "update_tip",
                                "tipId": tip_id,
                                "service": service,
                                "new_version": current_version + 1,
                            }
                        )
                    )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    # Version conflict — skip and continue
                    conflict_ids.append(tip_id)
                    logger.info(
                        json.dumps(
                            {
                                "action": "update_conflict",
                                "tipId": tip_id,
                                "reason": "version_mismatch",
                                "expected_version": current_version,
                            }
                        )
                    )

    logger.info(
        json.dumps(
            {
                "action": "apply_deltas_summary",
                "inserted": inserted_count,
                "updated": updated_count,
                "conflicts": len(conflict_ids),
            }
        )
    )

    return inserted_count, updated_count, conflict_ids
