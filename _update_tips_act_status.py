#!/usr/bin/env python3
"""Update DynamoDB tips with implementedInAct flag based on _SCAN_REGISTRY."""

# These tip IDs have automated checks implemented in the Act tab scan engine
IMPLEMENTED_IN_ACT = {
    'ebs-004', 'ebs-002', 'ebs-003',
    'vpc-001',
    's3-002', 's3-003',
    'elb-001',
    'kms-001',
    'general-002', 'general-004',
    'ec2-001', 'ec2-003', 'ec2-009', 'ec2-006',
    'rds-001', 'rds-006',
    'general-014',
}

# Update the knowledge base JSON
import json

with open('knowledge-base/aws-cost-optimization-tips.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

updated = 0
for tip in data.get('tips', []):
    tip_id = tip.get('id', '')
    was = tip.get('implementedInAct', False)
    should_be = tip_id in IMPLEMENTED_IN_ACT
    tip['implementedInAct'] = should_be
    if was != should_be:
        updated += 1
        print(f"  {'✅' if should_be else '❌'} {tip_id}: {tip.get('title', '')}")

with open('knowledge-base/aws-cost-optimization-tips.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nUpdated {updated} tips. Total tips: {len(data.get('tips', []))}")
print(f"Implemented in Act: {len(IMPLEMENTED_IN_ACT)}")
print(f"\nNow run 'python knowledge-base/seed-dynamodb.py' to push to DynamoDB")
