#!/usr/bin/env python3
"""
CLI tool to create a connector in the ConnectorConfig DynamoDB table.

Usage:
  python scripts/create_connector.py --interactive
  python scripts/create_connector.py --provider-key datadog --display-name "Datadog" --cloud monitoring --auth-type api_key
  python scripts/create_connector.py --from-json connector.json
  python scripts/create_connector.py --list
  python scripts/create_connector.py --delete aws

Examples:
  # Interactive mode (guided prompts):
  python scripts/create_connector.py --interactive

  # Quick create with minimal fields (rest auto-generated):
  python scripts/create_connector.py --provider-key newrelic --display-name "New Relic" --cloud monitoring --auth-type api_key

  # Create from JSON file:
  python scripts/create_connector.py --from-json my_connector.json

  # List all connectors:
  python scripts/create_connector.py --list

  # Delete a connector:
  python scripts/create_connector.py --delete openai

  # Overwrite existing connector:
  python scripts/create_connector.py --provider-key aws --display-name "AWS Updated" --cloud aws --auth-type iam_role --force
"""

import argparse
import boto3
import json
import sys
import time
from botocore.exceptions import ClientError

TABLE_NAME = 'ConnectorConfig'
REGION = 'us-east-1'

# Valid options
VALID_CLOUDS = ['aws', 'azure', 'gcp', 'ai_vendor', 'monitoring', 'other']
VALID_AUTH_TYPES = ['iam_role', 'service_principal', 'service_account', 'api_key', 'oauth2']

# Auto-generation defaults by cloud type
CLOUD_DEFAULTS = {
    'aws': {
        'connectorClass': 'aws_connector.AWSConnector',
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations', 'get_resource_inventory'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'ec2Instances', 'rdsInstances', 'lambdaFunctions'],
        'cacheSchema': {'pkPrefix': 'AWS', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
    },
    'azure': {
        'connectorClass': 'azure_connector.AzureConnector',
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
        'cacheSchema': {'pkPrefix': 'AZURE', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
    },
    'gcp': {
        'connectorClass': 'gcp_connector.GCPConnector',
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
        'cacheSchema': {'pkPrefix': 'GCP', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
    },
    'ai_vendor': {
        'connectorClass': 'ai_vendor_connector.GenericAIConnector',
        'supportedOperations': ['get_usage', 'get_cost_breakdown', 'get_model_pricing'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'aiUsage', 'modelBreakdown'],
        'cacheSchema': {'pkPrefix': '', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'models', 'dailyCosts', 'currency']},
    },
    'monitoring': {
        'connectorClass': 'monitoring_connector.GenericMonitoringConnector',
        'supportedOperations': ['get_usage', 'get_cost_breakdown'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'clusterUsage'],
        'cacheSchema': {'pkPrefix': '', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
    },
    'other': {
        'connectorClass': 'generic_connector.GenericConnector',
        'supportedOperations': ['get_cost_breakdown'],
        'syncFields': ['costBreakdown', 'monthlyTrend'],
        'cacheSchema': {'pkPrefix': '', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
    },
}


def get_table():
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    return dynamodb.Table(TABLE_NAME)


def autofill_defaults(provider_key, cloud):
    """Auto-generate technical fields based on providerKey and cloud type."""
    defaults = CLOUD_DEFAULTS.get(cloud, CLOUD_DEFAULTS['other'])
    pk_upper = provider_key.upper().replace('-', '_')

    result = {
        'connectorClass': defaults['connectorClass'],
        'iconUrl': f'/icons/{provider_key}.svg',
        'supportedOperations': defaults['supportedOperations'],
        'syncFields': defaults['syncFields'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'cacheSchema': {
            'pkPrefix': defaults['cacheSchema']['pkPrefix'] or pk_upper,
            'skFormat': defaults['cacheSchema']['skFormat'],
            'fieldNames': defaults['cacheSchema']['fieldNames'],
        },
        'costEstimationRates': {},
        'invoiceFields': {
            'issuerLabel': '',
            'accountIdPattern': '.*',
            'currencyDefault': 'USD',
        },
    }
    return result


def build_connector(provider_key, display_name, cloud, auth_type, staleness_hours=24,
                    issuer_label='', tips_sync_url='', extra_fields=None):
    """Build a full connector record with auto-generated defaults."""
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    defaults = autofill_defaults(provider_key, cloud)

    connector = {
        'providerKey': provider_key,
        'displayName': display_name,
        'cloud': cloud,
        'authType': auth_type,
        'stalenessThresholdHours': staleness_hours,
        **defaults,
        'createdAt': now,
        'updatedAt': now,
    }

    if issuer_label:
        connector['invoiceFields']['issuerLabel'] = issuer_label
    if tips_sync_url:
        connector['tipsSyncUrl'] = tips_sync_url

    # Override with any extra fields from JSON
    if extra_fields:
        for k, v in extra_fields.items():
            if k not in ('providerKey', 'createdAt', 'updatedAt'):
                connector[k] = v

    return connector


def interactive_create():
    """Guided interactive connector creation."""
    print('\n=== Create New Connector (Interactive) ===\n')

    # Provider Key
    while True:
        pk = input('Provider Key (lowercase, e.g. "datadog"): ').strip()
        if pk and all(c.isalnum() or c == '_' for c in pk) and pk[0].isalpha():
            break
        print('  Invalid! Use lowercase letters, digits, underscores. Must start with a letter.')

    # Display Name
    display_name = input(f'Display Name (e.g. "Datadog"): ').strip()
    if not display_name:
        display_name = pk.replace('_', ' ').title()
        print(f'  Using: {display_name}')

    # Cloud
    print(f'\nCloud/Category options: {", ".join(VALID_CLOUDS)}')
    while True:
        cloud = input('Cloud/Category: ').strip().lower()
        if cloud in VALID_CLOUDS:
            break
        print(f'  Invalid! Choose from: {", ".join(VALID_CLOUDS)}')

    # Auth Type
    print(f'\nAuth Type options: {", ".join(VALID_AUTH_TYPES)}')
    while True:
        auth_type = input('Auth Type: ').strip().lower()
        if auth_type in VALID_AUTH_TYPES:
            break
        print(f'  Invalid! Choose from: {", ".join(VALID_AUTH_TYPES)}')

    # Staleness
    staleness_input = input('\nStaleness Threshold Hours [24]: ').strip()
    staleness_hours = int(staleness_input) if staleness_input.isdigit() else 24

    # Invoice Issuer Label
    issuer_label = input('Invoice Issuer Label (optional): ').strip()

    # Tips Sync URL
    tips_sync_url = input('Tips Sync Source URL (optional): ').strip()

    connector = build_connector(pk, display_name, cloud, auth_type, staleness_hours,
                                issuer_label, tips_sync_url)

    print(f'\n--- Preview ---')
    print(json.dumps(connector, indent=2, default=str))

    confirm = input('\nSave to DynamoDB? [Y/n]: ').strip().lower()
    if confirm in ('', 'y', 'yes'):
        return connector
    else:
        print('Cancelled.')
        sys.exit(0)


def list_connectors():
    """List all connectors in the table."""
    table = get_table()
    try:
        resp = table.scan()
        items = resp.get('Items', [])
        if not items:
            print('No connectors found in table.')
            return
        print(f'\n{"Provider Key":<20} {"Display Name":<30} {"Cloud":<12} {"Auth Type":<18} {"Staleness (hrs)"}')
        print('-' * 95)
        for item in sorted(items, key=lambda x: x.get('providerKey', '')):
            print(f'{item["providerKey"]:<20} {item.get("displayName",""):<30} {item.get("cloud",""):<12} {item.get("authType",""):<18} {item.get("stalenessThresholdHours","")}')
        print(f'\nTotal: {len(items)} connectors')
    except ClientError as e:
        print(f'Error: {e}')
        sys.exit(1)


def delete_connector(provider_key):
    """Delete a connector by providerKey."""
    table = get_table()
    try:
        resp = table.get_item(Key={'providerKey': provider_key})
        if 'Item' not in resp:
            print(f'Connector "{provider_key}" not found.')
            sys.exit(1)
        confirm = input(f'Delete connector "{provider_key}" ({resp["Item"].get("displayName","")})? [y/N]: ').strip().lower()
        if confirm in ('y', 'yes'):
            table.delete_item(Key={'providerKey': provider_key})
            print(f'Deleted: {provider_key}')
        else:
            print('Cancelled.')
    except ClientError as e:
        print(f'Error: {e}')
        sys.exit(1)


def save_connector(connector, force=False):
    """Save connector to DynamoDB."""
    table = get_table()
    pk = connector['providerKey']

    try:
        if force:
            table.put_item(Item=connector)
            print(f'  + {pk} saved (force overwrite)')
        else:
            table.put_item(
                Item=connector,
                ConditionExpression='attribute_not_exists(providerKey)'
            )
            print(f'  + {pk} created successfully')
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f'  ! {pk} already exists. Use --force to overwrite.')
            sys.exit(1)
        else:
            print(f'  ! Error saving {pk}: {e}')
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='CLI tool to manage ConnectorConfig DynamoDB table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --interactive
  %(prog)s --provider-key datadog --display-name "Datadog" --cloud monitoring --auth-type api_key
  %(prog)s --from-json connector.json
  %(prog)s --list
  %(prog)s --delete openai
        """
    )

    # Modes
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive guided creation')
    parser.add_argument('--list', '-l', action='store_true', help='List all connectors')
    parser.add_argument('--delete', '-d', metavar='PROVIDER_KEY', help='Delete a connector by providerKey')
    parser.add_argument('--from-json', '-j', metavar='FILE', help='Create connector from JSON file')

    # Direct creation fields
    parser.add_argument('--provider-key', '-pk', help='Provider key (lowercase, e.g. "datadog")')
    parser.add_argument('--display-name', '-dn', help='Display name (e.g. "Datadog")')
    parser.add_argument('--cloud', '-c', choices=VALID_CLOUDS, help='Cloud/Category')
    parser.add_argument('--auth-type', '-at', choices=VALID_AUTH_TYPES, help='Authentication type')
    parser.add_argument('--staleness-hours', '-sh', type=int, default=24, help='Staleness threshold in hours (default: 24)')
    parser.add_argument('--issuer-label', help='Invoice issuer label')
    parser.add_argument('--tips-sync-url', help='Tips sync source URL')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite if connector already exists')

    args = parser.parse_args()

    # List mode
    if args.list:
        list_connectors()
        return

    # Delete mode
    if args.delete:
        delete_connector(args.delete)
        return

    # Interactive mode
    if args.interactive:
        connector = interactive_create()
        save_connector(connector, force=False)
        return

    # From JSON file
    if args.from_json:
        try:
            with open(args.from_json, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f'Error reading JSON file: {e}')
            sys.exit(1)

        # Validate minimum fields
        if 'providerKey' not in data:
            print('Error: JSON must contain "providerKey"')
            sys.exit(1)

        pk = data['providerKey']
        display_name = data.get('displayName', pk.replace('_', ' ').title())
        cloud = data.get('cloud', 'other')
        auth_type = data.get('authType', 'api_key')
        staleness = data.get('stalenessThresholdHours', 24)

        connector = build_connector(pk, display_name, cloud, auth_type, staleness,
                                    data.get('invoiceFields', {}).get('issuerLabel', ''),
                                    data.get('tipsSyncUrl', ''),
                                    extra_fields=data)
        print(f'Creating connector from JSON: {pk}')
        save_connector(connector, force=args.force)
        return

    # Direct creation from CLI args
    if args.provider_key:
        if not args.display_name:
            args.display_name = args.provider_key.replace('_', ' ').title()
        if not args.cloud:
            print('Error: --cloud is required for direct creation')
            sys.exit(1)
        if not args.auth_type:
            print('Error: --auth-type is required for direct creation')
            sys.exit(1)

        connector = build_connector(
            args.provider_key, args.display_name, args.cloud, args.auth_type,
            args.staleness_hours, args.issuer_label or '', args.tips_sync_url or ''
        )
        print(f'Creating connector: {args.provider_key}')
        save_connector(connector, force=args.force)
        return

    # No mode specified
    parser.print_help()


if __name__ == '__main__':
    main()
