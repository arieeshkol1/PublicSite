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


def seed_table(tips, table):
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

    print(f"Loading tips from {TIPS_FILE}")
    print(f"Target region: {REGION}")
    try:
        tips = load_tips(TIPS_FILE)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Error reading tips file: {e}")
        sys.exit(1)

    print(f"Found {len(tips)} tips")

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table exists
    try:
        table.load()
    except ClientError as e:
        print(f"Error accessing table '{TABLE_NAME}': {e.response['Error']['Message']}")
        print("Make sure the CloudFormation stack is deployed first.")
        sys.exit(1)

    print(f"Writing tips to {TABLE_NAME}...")
    loaded, failed = seed_table(tips, table)

    print(f"\nDone! {loaded} tips loaded, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
