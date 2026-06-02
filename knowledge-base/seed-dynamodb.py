#!/usr/bin/env python3
"""
Seed script for ViewMyBill DynamoDB cost optimization tips table.

Reads tips from aws-cost-optimization-tips.json and batch writes them
to the ViewMyBill-CostOptimizationTips DynamoDB table.

Usage:
    python knowledge-base/seed-dynamodb.py
    python knowledge-base/seed-dynamodb.py --region me-central-1
"""

import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "ViewMyBill-CostOptimizationTips"
REGION = os.environ.get("AWS_REGION", "us-east-1")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TIPS_FILE = os.path.join(SCRIPT_DIR, "aws-cost-optimization-tips.json")


def load_tips(filepath):
    """Load tips from the JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["tips"]


def seed_table(tips, table, cloud_label="AWS"):
    """Batch write tips to DynamoDB. Overwrites existing items."""
    loaded = 0
    failed = 0

    with table.batch_writer(overwrite_by_pkeys=["service", "tipId"]) as batch:
        for tip in tips:
            item = {
                "service": tip["service"],
                "tipId": tip["id"],
                "category": tip["category"],
                "title": tip["title"],
                "description": tip["description"],
                "estimatedSavings": tip["estimatedSavings"],
                "difficulty": tip["difficulty"],
                "cloud": cloud_label,
                # Phase 1 scan engine fields
                "checkImplemented": tip.get("checkImplemented", False),
                "actionType": tip.get("actionType", "pending"),
                "actionLabel": tip.get("actionLabel", "Coming Soon"),
                "level": tip.get("level", 2),
                "serviceKey": tip.get("serviceKey", tip["service"]),
                "implementedInAct": tip.get("implementedInAct", False),
            }
            if "automatedCheck" in tip and tip["automatedCheck"]:
                item["automatedCheck"] = tip["automatedCheck"]
            try:
                batch.put_item(Item=item)
                loaded += 1
            except ClientError as e:
                print(f"  Failed to write {tip['id']}: {e.response['Error']['Message']}")
                failed += 1

    return loaded, failed


def main():
    global REGION
    # Support --region argument
    if '--region' in sys.argv:
        idx = sys.argv.index('--region')
        if idx + 1 < len(sys.argv):
            REGION = sys.argv[idx + 1]

    print(f"Target region: {REGION}")

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table exists
    try:
        table.load()
    except ClientError as e:
        print(f"Error accessing table '{TABLE_NAME}': {e.response['Error']['Message']}")
        print("Make sure the CloudFormation stack is deployed first.")
        sys.exit(1)

    # Seed all provider tips files
    tips_files = [
        ("aws-cost-optimization-tips.json", "AWS"),
        ("azure-cost-optimization-tips.json", "AZURE"),
        ("gcp-cost-optimization-tips.json", "GCP"),
    ]

    total_loaded = 0
    total_failed = 0

    for filename, cloud_label in tips_files:
        filepath = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP: {filename} not found")
            continue

        print(f"\nLoading {filename} (cloud={cloud_label})...")
        try:
            tips = load_tips(filepath)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"  Error reading {filename}: {e}")
            continue

        print(f"  Found {len(tips)} tips")
        print(f"  Writing to {TABLE_NAME}...")
        loaded, failed = seed_table(tips, table, cloud_label)
        total_loaded += loaded
        total_failed += failed
        print(f"  {loaded} loaded, {failed} failed")

    print(f"\nDone! Total: {total_loaded} tips loaded, {total_failed} failed.")
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
