"""
Seed Azure and GCP tips directly into DynamoDB.
Run this script locally or via CI/CD to load multi-cloud tips.

Usage: python infrastructure/seed-multicloud-tips.py
"""
import json
import os
import boto3
from datetime import datetime, timezone

TABLE_NAME = 'ViewMyBill-CostOptimizationTips'
REGION = 'us-east-1'

def load_tips_file(filepath):
    """Load tips from a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('tips', []), data.get('cloudProvider', 'aws')

def seed_tips():
    """Seed Azure and GCP tips into DynamoDB."""
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    
    # Find knowledge-base directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    kb_dir = os.path.join(repo_root, 'knowledge-base')
    
    files_to_load = [
        ('azure-cost-optimization-tips.json', 'AZURE'),
        ('gcp-cost-optimization-tips.json', 'GCP'),
    ]
    
    now_iso = datetime.now(timezone.utc).isoformat()
    total_inserted = 0
    total_skipped = 0
    
    for filename, cloud_label in files_to_load:
        filepath = os.path.join(kb_dir, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP: {filename} not found at {filepath}")
            continue
        
        tips, _ = load_tips_file(filepath)
        print(f"\n  Loading {len(tips)} tips from {filename} (cloud={cloud_label})...")
        
        for tip in tips:
            tip_id = tip.get('id', '')
            service = tip.get('service', '')
            
            if not tip_id or not service:
                print(f"    SKIP: tip missing id or service: {tip}")
                continue
            
            # Build the DynamoDB item
            item = {
                'service': service,
                'tipId': tip_id,
                'title': tip.get('title', ''),
                'description': tip.get('description', ''),
                'category': tip.get('category', ''),
                'estimatedSavings': tip.get('estimatedSavings', ''),
                'difficulty': tip.get('difficulty', 'medium'),
                'cloud': cloud_label,
                'syncSource': 'baseline',
                'createdAt': now_iso,
                'lastSyncedAt': now_iso,
                'version': 1,
            }
            
            try:
                table.put_item(
                    Item=item,
                    ConditionExpression='attribute_not_exists(tipId)'
                )
                total_inserted += 1
                print(f"    INSERT: {service}/{tip_id} ({cloud_label})")
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                # Tip already exists — update cloud field if needed
                try:
                    table.update_item(
                        Key={'service': service, 'tipId': tip_id},
                        UpdateExpression='SET cloud = :c, lastSyncedAt = :ts',
                        ExpressionAttributeValues={':c': cloud_label, ':ts': now_iso}
                    )
                    total_skipped += 1
                    print(f"    UPDATE cloud: {service}/{tip_id} -> {cloud_label}")
                except Exception as e:
                    print(f"    ERROR updating {tip_id}: {e}")
            except Exception as e:
                print(f"    ERROR inserting {tip_id}: {e}")
    
    print(f"\n  Done! Inserted: {total_inserted}, Updated: {total_skipped}")

if __name__ == '__main__':
    print("=== Seeding Multi-Cloud Tips ===")
    seed_tips()
