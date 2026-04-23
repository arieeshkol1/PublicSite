#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate all SlashMyBill DynamoDB tables from one region to another.
Uses scan + batch_write for simplicity. For large tables, consider DynamoDB Export/Import.

Usage:
    python migrate-dynamodb.py --source-region us-east-1 --target-region me-south-1
    python migrate-dynamodb.py --source-region us-east-1 --target-region me-south-1 --tables MemberPortal-Members
"""

import argparse
import boto3
import sys
import time

TABLES = [
    'MemberPortal-Members',
    'MemberPortal-Accounts',
    'ViewMyBill-CostOptimizationTips',
    'ViewMyBill-Leads',
    'ViewMyBill-OTP',
    'MemberPortal-AgentFeedback',
    'MemberPortal-BusinessMetrics',
    'SpotSavingsLedger',
]


def migrate_table(source_region, target_region, table_name):
    """Scan all items from source and batch-write to target."""
    source = boto3.resource('dynamodb', region_name=source_region)
    target = boto3.resource('dynamodb', region_name=target_region)

    source_table = source.Table(table_name)
    target_table = target.Table(table_name)

    # Verify target table exists
    try:
        target_table.load()
    except Exception as e:
        print(f"  ERROR: Target table {table_name} does not exist in {target_region}. Deploy the CF stack first.")
        print(f"  {e}")
        return 0

    # Scan source
    print(f"  Scanning {table_name} in {source_region}...")
    items = []
    scan_kwargs = {}
    while True:
        resp = source_table.scan(**scan_kwargs)
        items.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']

    print(f"  Found {len(items)} items")

    if not items:
        print(f"  Nothing to migrate")
        return 0

    # Batch write to target
    written = 0
    with target_table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
            if written % 100 == 0:
                print(f"  Written {written}/{len(items)}...")

    print(f"  Migrated {written} items to {target_region}")
    return written


def main():
    parser = argparse.ArgumentParser(description='Migrate SlashMyBill DynamoDB tables between regions')
    parser.add_argument('--source-region', default='us-east-1', help='Source AWS region')
    parser.add_argument('--target-region', default='me-south-1', help='Target AWS region')
    parser.add_argument('--tables', nargs='*', help='Specific tables to migrate (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Only scan, do not write')
    args = parser.parse_args()

    tables = args.tables if args.tables else TABLES
    print(f"Migrating {len(tables)} tables: {args.source_region} -> {args.target_region}")
    if args.dry_run:
        print("DRY RUN - no data will be written")
    print()

    total = 0
    for table_name in tables:
        print(f"[{table_name}]")
        if args.dry_run:
            source = boto3.resource('dynamodb', region_name=args.source_region)
            source_table = source.Table(table_name)
            try:
                count = source_table.item_count
                print(f"  ~{count} items (approximate)")
            except Exception as e:
                print(f"  Error: {e}")
        else:
            count = migrate_table(args.source_region, args.target_region, table_name)
            total += count
        print()

    if not args.dry_run:
        print(f"Migration complete: {total} total items migrated")
    else:
        print("Dry run complete. Run without --dry-run to migrate.")


if __name__ == '__main__':
    main()
