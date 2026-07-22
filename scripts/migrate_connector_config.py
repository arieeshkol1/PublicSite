"""
Migration Script: Seed ConnectorConfig DynamoDB table from vendor_registry.json.

Reads the existing vendor_registry.json and creates full Connector_Config records
in the ConnectorConfig DynamoDB table. Uses conditional writes (skip-if-exists)
to ensure idempotency.

Usage:
    python scripts/migrate_connector_config.py [--table-name ConnectorConfig] [--region us-east-1]

Requirements:
    - boto3
    - AWS credentials configured (IAM role or env vars)
    - ConnectorConfig DynamoDB table must exist
"""

import json
import os
import sys
import argparse
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Known issuer labels for invoice generation (from existing codebase)
ISSUER_LABELS = {
    'aws': 'Amazon Web Services, Inc.',
    'azure': 'Microsoft Corporation',
    'gcp': 'Google Cloud Platform',
    'openai': 'OpenAI, LLC',
    'anthropic': 'Anthropic, PBC',
    'groundcover': 'GroundCover Ltd.',
}

# Known account ID patterns for each provider
PROVIDER_ACCOUNT_ID_PATTERNS = {
    'aws': r'^\d{12}$',
    'azure': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    'gcp': r'^[a-z][a-z0-9\-]{4,28}[a-z0-9]$',
    'openai': r'^org-[A-Za-z0-9]+$',
    'anthropic': r'^org-[A-Za-z0-9]+$',
    'groundcover': r'^[A-Za-z0-9_\-]+$',
}

# Default icon URLs (can be updated via admin UI later)
ICON_URLS = {
    'aws': '/icons/aws.svg',
    'azure': '/icons/azure.svg',
    'gcp': '/icons/gcp.svg',
    'openai': '/icons/openai.svg',
    'anthropic': '/icons/anthropic.svg',
    'groundcover': '/icons/groundcover.svg',
}

# Default sync fields per provider
SYNC_FIELDS = {
    'aws': ['costBreakdown', 'monthlyTrend', 'ec2Instances', 'rdsInstances', 'lambdaFunctions', 's3Buckets', 'ebsVolumes'],
    'azure': ['costBreakdown', 'monthlyTrend', 'computeInstances', 'databaseInstances', 'objectStorage'],
    'gcp': ['costBreakdown', 'monthlyTrend', 'computeInstances', 'objectStorage', 'serverlessFunctions'],
    'openai': ['costBreakdown', 'monthlyTrend', 'aiUsage'],
    'anthropic': ['costBreakdown', 'monthlyTrend', 'aiUsage'],
    'groundcover': ['costBreakdown', 'monthlyTrend', 'aiUsage'],
}

# Tips repository locations
TIPS_REPOSITORIES = {
    'aws': 'ViewMyBill-CostOptimizationTips',
    'azure': 'ViewMyBill-CostOptimizationTips',
    'gcp': 'ViewMyBill-CostOptimizationTips',
    'openai': 'ViewMyBill-CostOptimizationTips',
    'anthropic': 'ViewMyBill-CostOptimizationTips',
    'groundcover': 'ViewMyBill-CostOptimizationTips',
}

# Cache schema SK format and field names
CACHE_SK_FORMATS = {
    'aws': 'COST#{month}',
    'azure': 'COST#{month}',
    'gcp': 'COST#{month}',
    'openai': 'COST#{month}',
    'anthropic': 'COST#{month}',
    'groundcover': 'COST#{month}',
}

CACHE_FIELD_NAMES = {
    'aws': ['totalCost', 'services', 'dailyCosts', 'currency'],
    'azure': ['totalCost', 'services', 'dailyCosts', 'currency'],
    'gcp': ['totalCost', 'services', 'dailyCosts', 'currency'],
    'openai': ['totalCost', 'models', 'dailyCosts', 'currency'],
    'anthropic': ['totalCost', 'models', 'dailyCosts', 'currency'],
    'groundcover': ['totalCost', 'services', 'dailyCosts', 'currency'],
}

# Cost estimation rates (defaults)
COST_ESTIMATION_RATES = {
    'aws': {},
    'azure': {},
    'gcp': {},
    'openai': {
        'gpt-4': 0.03,
        'gpt-4-turbo': 0.01,
        'gpt-3.5-turbo': 0.0015,
    },
    'anthropic': {
        'claude-3-opus': 0.015,
        'claude-3-sonnet': 0.003,
        'claude-3-haiku': 0.00025,
    },
    'groundcover': {},
}


def load_vendor_registry(registry_path: str) -> dict:
    """Load vendor_registry.json and return the vendors dict."""
    if not os.path.exists(registry_path):
        logger.error(f"vendor_registry.json not found at: {registry_path}")
        sys.exit(1)

    try:
        with open(registry_path, 'r') as f:
            data = json.load(f)
        return data.get('vendors', {})
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to read vendor_registry.json: {e}")
        sys.exit(1)


def compose_connector_config(provider_key: str, vendor: dict) -> dict:
    """Compose a full Connector_Config record from vendor registry entry and known constants."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        'providerKey': provider_key,
        'displayName': vendor.get('displayName', provider_key.title()),
        'iconUrl': ICON_URLS.get(provider_key, f'/icons/{provider_key}.svg'),
        'authType': vendor.get('authType', 'api_key'),
        'syncFields': SYNC_FIELDS.get(provider_key, []),
        'tipsRepository': TIPS_REPOSITORIES.get(provider_key, 'ViewMyBill-CostOptimizationTips'),
        'invoiceFields': {
            'issuerLabel': ISSUER_LABELS.get(provider_key, provider_key.title()),
            'accountIdPattern': PROVIDER_ACCOUNT_ID_PATTERNS.get(provider_key, r'^.+$'),
            'currencyDefault': 'USD',
        },
        'cacheSchema': {
            'pkPrefix': vendor.get('cachePrefix', provider_key.upper()),
            'skFormat': CACHE_SK_FORMATS.get(provider_key, 'COST#{month}'),
            'fieldNames': CACHE_FIELD_NAMES.get(provider_key, ['totalCost', 'services', 'dailyCosts']),
        },
        'supportedOperations': vendor.get('supportedTools', []),
        'stalenessThresholdHours': vendor.get('staleness_hours', 48),
        'costEstimationRates': COST_ESTIMATION_RATES.get(provider_key, {}),
        'cloud': vendor.get('cloud', 'unknown'),
        'connectorClass': vendor.get('connector', f'{provider_key}_connector.{provider_key.title()}Connector'),
        'createdAt': now,
        'updatedAt': now,
    }


def migrate(table_name: str, region: str, registry_path: str):
    """Run the migration: read vendor_registry.json and seed ConnectorConfig table."""
    logger.info(f"Starting migration to {table_name} in {region}")
    logger.info(f"Reading vendor registry from: {registry_path}")

    vendors = load_vendor_registry(registry_path)
    if not vendors:
        logger.error("No vendors found in vendor_registry.json")
        sys.exit(1)

    logger.info(f"Found {len(vendors)} vendors to migrate: {list(vendors.keys())}")

    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)
        # Verify table exists
        table.load()
    except ClientError as e:
        logger.error(f"Cannot connect to DynamoDB table '{table_name}': {e}")
        sys.exit(1)

    success_count = 0
    skip_count = 0
    fail_count = 0

    for provider_key, vendor in vendors.items():
        config = compose_connector_config(provider_key, vendor)

        try:
            table.put_item(
                Item=config,
                ConditionExpression='attribute_not_exists(providerKey)',
            )
            logger.info(f"  ✓ Created: {provider_key} ({config['displayName']})")
            success_count += 1
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"  ⚠ Skipped: {provider_key} (already exists)")
                skip_count += 1
            else:
                logger.error(f"  ✗ Failed: {provider_key} — {e}")
                fail_count += 1

    logger.info(f"\nMigration complete: {success_count} created, {skip_count} skipped, {fail_count} failed")

    if fail_count > 0:
        logger.error("Some providers failed to migrate. Check logs above.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Migrate vendor_registry.json to ConnectorConfig DynamoDB table')
    parser.add_argument('--table-name', default='ConnectorConfig', help='DynamoDB table name (default: ConnectorConfig)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--registry-path', default=None, help='Path to vendor_registry.json')
    args = parser.parse_args()

    # Determine registry path
    if args.registry_path:
        registry_path = args.registry_path
    else:
        # Default: look relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        registry_path = os.path.join(script_dir, '..', 'agent-action', 'connectors', 'vendor_registry.json')

    migrate(args.table_name, args.region, registry_path)


if __name__ == '__main__':
    main()
