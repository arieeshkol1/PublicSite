#!/usr/bin/env python3
"""
Tips Table Maintenance Script
=============================
Handles 4 maintenance tasks for the DynamoDB tips table:
  1. Delete SYNC_LOG garbage records
  2. Deduplicate tips (remove known duplicates)
  3. Add missing decision framework + Support/Tax tips
  4. Fix providerRouting by scanning table and matching tipIds

Run via CI/CD: python scripts/tips_table_maintenance.py
"""

import sys
import os
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_tips_provider_routing import PROVIDER_ROUTING_MAP

TABLE_NAME = "ViewMyBill-CostOptimizationTips"
REGION = "us-east-1"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# Task 1: Delete SYNC_LOG garbage records
# ============================================================

def task_delete_sync_log_records(table):
    """Delete all items where tipId starts with 'SYNC_LOG#' or equals 'SYNC_METADATA'."""
    logger.info("=" * 60)
    logger.info("Task 1: Delete SYNC_LOG garbage records")
    logger.info("=" * 60)

    deleted = 0
    errors = 0

    # Scan for SYSTEM service items that are sync garbage
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq('SYSTEM')
        )
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq('SYSTEM'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        logger.info("  Found %d items under service='SYSTEM'", len(items))

        for item in items:
            tip_id = item.get('tipId', '')
            if tip_id.startswith('SYNC_LOG#') or tip_id == 'SYNC_METADATA':
                try:
                    table.delete_item(Key={'service': 'SYSTEM', 'tipId': tip_id})
                    deleted += 1
                    logger.info("  Deleted: SYSTEM / %s", tip_id)
                except ClientError as e:
                    errors += 1
                    logger.error("  Failed to delete SYSTEM / %s: %s", tip_id, e.response['Error']['Message'])

    except ClientError as e:
        logger.error("  Failed to query SYSTEM items: %s", e.response['Error']['Message'])
        errors += 1

    logger.info("  Task 1 complete: deleted=%d, errors=%d", deleted, errors)
    return deleted, errors


# ============================================================
# Task 2: Deduplicate tips
# ============================================================

# Known duplicates to delete: (service, tipId)
DUPLICATES_TO_DELETE = [
    # azure-storage-001 duplicate (keep one under Storage)
    ("Storage", "azure-storage-001"),  # extra copy - if 2 exist, one will fail gracefully

    # general-002 duplicate (keep finops-settings-009 which has same content)
    ("General", "general-002"),

    # Lambda scheduling duplicates: keep lambda-003, delete lambda-004 and lambda-005
    ("Lambda", "lambda-004"),
    ("Lambda", "lambda-005"),

    # Azure Key Vault duplicates: keep azure-keyvault-001, delete 002 and 003
    ("Key Vault", "azure-keyvault-002"),
    ("Key Vault", "azure-keyvault-003"),

    # Azure AD licensing duplicates: keep azure-ad-001, delete 002 and 003
    ("Azure AD", "azure-ad-002"),
    ("Azure AD", "azure-ad-003"),
]


def task_deduplicate_tips(table):
    """Delete known duplicate tip entries."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Task 2: Deduplicate tips")
    logger.info("=" * 60)

    deleted = 0
    skipped = 0
    errors = 0

    for service, tip_id in DUPLICATES_TO_DELETE:
        try:
            table.delete_item(
                Key={'service': service, 'tipId': tip_id},
                ConditionExpression='attribute_exists(tipId)'
            )
            deleted += 1
            logger.info("  Deleted duplicate: %s / %s", service, tip_id)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                skipped += 1
                logger.info("  Already gone: %s / %s (skipped)", service, tip_id)
            else:
                errors += 1
                logger.error("  Failed to delete %s / %s: %s", service, tip_id, e.response['Error']['Message'])

    logger.info("  Task 2 complete: deleted=%d, skipped=%d, errors=%d", deleted, skipped, errors)
    return deleted, errors


# ============================================================
# Task 3: Add missing decision framework + Support/Tax tips
# ============================================================

MISSING_TIPS = [
    {
        'service': 'General',
        'tipId': 'general-decision-ri-vs-spot',
        'cloud': 'AWS',
        'category': 'commitment',
        'level': 1,
        'difficulty': 'medium',
        'title': 'When to choose Reserved Instances vs Spot vs Serverless',
        'description': 'Decision framework: Use RIs/Savings Plans for workloads with >70% steady-state utilization and predictable patterns. Use Spot for fault-tolerant, stateless workloads that can handle 2-minute interruption notices (batch processing, CI/CD, rendering). Use Serverless (Lambda/Fargate) for event-driven workloads with <30% average utilization or highly variable traffic. Never buy commitments before right-sizing \u2014 always rightsize first, then commit.',
        'estimatedSavings': '30-90%',
        'implementedInAct': False,
        'checkImplemented': False,
        'actionType': 'pending',
        'actionLabel': 'Ask AI about commitment strategy',
        'serviceKey': 'General',
    },
    {
        'service': 'General',
        'tipId': 'general-support-plan',
        'cloud': 'AWS',
        'category': 'support',
        'level': 2,
        'difficulty': 'easy',
        'title': 'Review AWS Support plan tier',
        'description': 'AWS Support plans (Business at $100+/mo or 3-10% of monthly usage, Enterprise at $15K+/mo) are monthly fixed charges that appear on the 1st of each month. Evaluate if your plan level matches actual usage: Business plan includes 24/7 phone support and Trusted Advisor \u2014 if you rarely open tickets, Developer plan ($29/mo) may suffice. Enterprise plan includes a TAM and concierge \u2014 only justified for $500K+/yr spend. Downgrading from Business to Developer saves $100-500+/mo for most accounts.',
        'estimatedSavings': '$100-500/month',
        'implementedInAct': False,
        'checkImplemented': False,
        'actionType': 'pending',
        'actionLabel': 'Contact AWS',
        'serviceKey': 'General',
    },
    {
        'service': 'General',
        'tipId': 'general-tax-explanation',
        'cloud': 'AWS',
        'category': 'explanation',
        'level': 1,
        'difficulty': 'easy',
        'title': 'Understanding Tax charges in AWS bills',
        'description': 'Tax charges (typically 10-20% of total) are government-imposed and cannot be reduced through optimization. They appear as a lump sum on the 1st of each month. When forecasting: separate tax from daily usage costs. Tax is proportional to total spend \u2014 reducing other services reduces tax proportionally. Some organizations can apply for tax exemption (non-profits, government entities) via the AWS Tax Settings page.',
        'estimatedSavings': 'Non-actionable (informational)',
        'implementedInAct': False,
        'checkImplemented': False,
        'actionType': 'pending',
        'actionLabel': 'View Details',
        'serviceKey': 'General',
    },
    {
        'service': 'General',
        'tipId': 'general-forecast-methodology',
        'cloud': 'AWS',
        'category': 'finops-settings',
        'level': 1,
        'difficulty': 'easy',
        'title': 'How to accurately forecast monthly cloud bills',
        'description': 'Correct forecasting methodology: 1) Use ONLY current month days (not previous month) for daily average. 2) Exclude the 1st-of-month spike (contains monthly fixed charges like Support, Tax, Reserved Instance fees). 3) Formula: forecast = (avg daily cost of recent non-spike days) \u00d7 days_in_month + first_of_month_fixed_charges. 4) The fixed charges from day-1 include: AWS Support plan, Tax, RI upfront amortization, Savings Plan fees. 5) Use getCostForecast API for AWS-native ML-based projection that accounts for seasonality.',
        'estimatedSavings': 'Accuracy improvement (informational)',
        'implementedInAct': False,
        'checkImplemented': False,
        'actionType': 'View Details',
        'serviceKey': 'General',
    },
]


def task_add_missing_tips(table):
    """Add missing decision framework and Support/Tax tips."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Task 3: Add missing decision framework + Support/Tax tips")
    logger.info("=" * 60)

    added = 0
    skipped = 0
    errors = 0

    for tip in MISSING_TIPS:
        # Convert int values to Decimal for DynamoDB
        item = {}
        for k, v in tip.items():
            if isinstance(v, int):
                item[k] = Decimal(str(v))
            else:
                item[k] = v

        try:
            table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(tipId)'
            )
            added += 1
            logger.info("  Added: %s / %s - %s", item['service'], item['tipId'], item['title'])
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                skipped += 1
                logger.info("  Already exists: %s / %s (skipped)", item['service'], item['tipId'])
            else:
                errors += 1
                logger.error("  Failed to add %s / %s: %s", item['service'], item['tipId'], e.response['Error']['Message'])

    logger.info("  Task 3 complete: added=%d, skipped=%d, errors=%d", added, skipped, errors)
    return added, errors


# ============================================================
# Task 4: Fix providerRouting by scanning table
# ============================================================

def task_fix_provider_routing(table):
    """
    Scan the full table and apply providerRouting from PROVIDER_ROUTING_MAP
    using the actual (service, tipId) key from each scanned item.
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("Task 4: Fix providerRouting (scan-based)")
    logger.info("=" * 60)

    # Scan all items from the table
    all_items = []
    try:
        response = table.scan(ProjectionExpression='service, tipId, providerRouting')
        all_items.extend(response.get('Items', []))

        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression='service, tipId, providerRouting',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            all_items.extend(response.get('Items', []))

        logger.info("  Scanned %d items from table", len(all_items))
    except ClientError as e:
        logger.error("  Failed to scan table: %s", e.response['Error']['Message'])
        return 0, 1

    updated = 0
    skipped = 0
    errors = 0

    for item in all_items:
        tip_id = item.get('tipId', '')
        service = item.get('service', '')

        # Check if this tipId has a providerRouting definition
        if tip_id not in PROVIDER_ROUTING_MAP:
            continue

        # Skip if providerRouting already set
        if 'providerRouting' in item and item['providerRouting']:
            skipped += 1
            continue

        # Apply providerRouting using the actual key from the scanned item
        try:
            table.update_item(
                Key={'service': service, 'tipId': tip_id},
                UpdateExpression='SET providerRouting = :pr',
                ExpressionAttributeValues={':pr': PROVIDER_ROUTING_MAP[tip_id]},
                ConditionExpression='attribute_exists(service) AND attribute_exists(tipId)'
            )
            updated += 1
            logger.info("  Updated providerRouting: %s / %s", service, tip_id)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                skipped += 1
                logger.info("  Item not found: %s / %s (skipped)", service, tip_id)
            else:
                errors += 1
                logger.error("  Failed to update %s / %s: %s", service, tip_id, e.response['Error']['Message'])

    logger.info("  Task 4 complete: updated=%d, skipped=%d, errors=%d", updated, skipped, errors)
    return updated, errors


# ============================================================
# Main
# ============================================================

def main():
    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║  Tips Table Maintenance Script                          ║")
    logger.info("║  Table: %s            ║", TABLE_NAME)
    logger.info("║  Region: %s                                    ║", REGION)
    logger.info("╚══════════════════════════════════════════════════════════╝")
    logger.info("")

    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table access
    try:
        table.load()
    except ClientError as e:
        logger.error("Cannot access table '%s' in region '%s': %s",
                     TABLE_NAME, REGION, e.response['Error']['Message'])
        sys.exit(1)

    # Run all 4 tasks
    summary = {}

    # Task 1
    try:
        deleted, errs = task_delete_sync_log_records(table)
        summary['Task 1 (SYNC_LOG cleanup)'] = f"deleted={deleted}, errors={errs}"
    except Exception as e:
        logger.error("Task 1 failed: %s", str(e))
        summary['Task 1 (SYNC_LOG cleanup)'] = f"FAILED: {str(e)}"

    # Task 2
    try:
        deleted, errs = task_deduplicate_tips(table)
        summary['Task 2 (Deduplication)'] = f"deleted={deleted}, errors={errs}"
    except Exception as e:
        logger.error("Task 2 failed: %s", str(e))
        summary['Task 2 (Deduplication)'] = f"FAILED: {str(e)}"

    # Task 3
    try:
        added, errs = task_add_missing_tips(table)
        summary['Task 3 (Add missing tips)'] = f"added={added}, errors={errs}"
    except Exception as e:
        logger.error("Task 3 failed: %s", str(e))
        summary['Task 3 (Add missing tips)'] = f"FAILED: {str(e)}"

    # Task 4
    try:
        updated, errs = task_fix_provider_routing(table)
        summary['Task 4 (Fix providerRouting)'] = f"updated={updated}, errors={errs}"
    except Exception as e:
        logger.error("Task 4 failed: %s", str(e))
        summary['Task 4 (Fix providerRouting)'] = f"FAILED: {str(e)}"

    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("MAINTENANCE SUMMARY")
    logger.info("=" * 60)
    for task, result in summary.items():
        logger.info("  %s: %s", task, result)
    logger.info("=" * 60)
    logger.info("Done.")


if __name__ == "__main__":
    main()
