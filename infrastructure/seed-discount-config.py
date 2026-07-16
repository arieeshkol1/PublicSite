"""
seed-discount-config.py — Populate CustomPlan-DiscountConfig table with default data.

Seeds the single-item discount configuration used by the Custom Subscription Plan
feature. The table stores base pricing, token counts, and tiered discount percentages
that the Discount Engine reads on every custom plan price calculation.

Run standalone: python infrastructure/seed-discount-config.py
"""

import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('CustomPlan-DiscountConfig')

DEFAULT_CONFIG = {
    'configId': 'ACTIVE',
    'baseMonthlyPrice': 250,
    'baseTokenCount': 2000,
    'discountTiers': [
        {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
        {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
        {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
        {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 35},
    ],
    'updatedAt': None,  # set at seed time
    'updatedBy': 'system-seed',
}


def seed():
    """Write the default discount configuration to the CustomPlan-DiscountConfig table."""
    now = datetime.now(timezone.utc).isoformat()
    item = {**DEFAULT_CONFIG, 'updatedAt': now}

    table.put_item(Item=item)

    print(f"Seeded CustomPlan-DiscountConfig table with default configuration:")
    print(f"  configId: {item['configId']}")
    print(f"  baseMonthlyPrice: ${item['baseMonthlyPrice']}")
    print(f"  baseTokenCount: {item['baseTokenCount']}")
    print(f"  discountTiers:")
    for tier in item['discountTiers']:
        print(f"    {tier['minMonths']}-{tier['maxMonths']} months: {tier['discountPercent']}% off")
    print(f"  updatedAt: {now}")
    print(f"  updatedBy: {item['updatedBy']}")


if __name__ == '__main__':
    seed()
