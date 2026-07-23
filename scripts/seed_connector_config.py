"""Seed ConnectorConfig DynamoDB table with default providers."""
import boto3
import time
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('ConnectorConfig')
now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

providers = [
    {
        'providerKey': 'aws',
        'displayName': 'Amazon Web Services',
        'cloud': 'aws',
        'authType': 'iam_role',
        'connectorClass': 'aws_connector.AWSConnector',
        'iconUrl': '/icons/aws.svg',
        'stalenessThresholdHours': 24,
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations', 'get_resource_inventory'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'ec2Instances', 'rdsInstances', 'lambdaFunctions'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'Amazon Web Services, Inc.', 'accountIdPattern': r'^\d{12}$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'AWS', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
        'costEstimationRates': {},
    },
    {
        'providerKey': 'azure',
        'displayName': 'Microsoft Azure',
        'cloud': 'azure',
        'authType': 'service_principal',
        'connectorClass': 'azure_connector.AzureConnector',
        'iconUrl': '/icons/azure.svg',
        'stalenessThresholdHours': 48,
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'Microsoft Corporation', 'accountIdPattern': r'^[0-9a-f-]{36}$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'AZURE', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
        'costEstimationRates': {},
    },
    {
        'providerKey': 'gcp',
        'displayName': 'Google Cloud Platform',
        'cloud': 'gcp',
        'authType': 'service_account',
        'connectorClass': 'gcp_connector.GCPConnector',
        'iconUrl': '/icons/gcp.svg',
        'stalenessThresholdHours': 48,
        'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'Google Cloud', 'accountIdPattern': r'^[a-z][a-z0-9\-]{4,28}[a-z0-9]$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'GCP', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
        'costEstimationRates': {},
    },
    {
        'providerKey': 'openai',
        'displayName': 'OpenAI',
        'cloud': 'ai_vendor',
        'authType': 'api_key',
        'connectorClass': 'ai_vendor_connector.OpenAIConnector',
        'iconUrl': '/icons/openai.svg',
        'stalenessThresholdHours': 24,
        'supportedOperations': ['get_usage', 'get_cost_breakdown', 'get_model_pricing'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'aiUsage', 'modelBreakdown'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'OpenAI, LLC', 'accountIdPattern': r'^org-[A-Za-z0-9]+$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'OPENAI', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'models', 'dailyCosts', 'currency']},
        'costEstimationRates': {'gpt-4o': '0.005', 'gpt-4-turbo': '0.01', 'gpt-3.5-turbo': '0.0015'},
    },
    {
        'providerKey': 'anthropic',
        'displayName': 'Anthropic',
        'cloud': 'ai_vendor',
        'authType': 'api_key',
        'connectorClass': 'ai_vendor_connector.AnthropicConnector',
        'iconUrl': '/icons/anthropic.svg',
        'stalenessThresholdHours': 24,
        'supportedOperations': ['get_usage', 'get_cost_breakdown', 'get_model_pricing'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'aiUsage', 'modelBreakdown'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'Anthropic, PBC', 'accountIdPattern': r'^org-[A-Za-z0-9]+$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'ANTHROPIC', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'models', 'dailyCosts', 'currency']},
        'costEstimationRates': {'claude-3-opus': '0.015', 'claude-3-sonnet': '0.003', 'claude-3-haiku': '0.00025'},
    },
    {
        'providerKey': 'groundcover',
        'displayName': 'Groundcover',
        'cloud': 'monitoring',
        'authType': 'api_key',
        'connectorClass': 'ai_vendor_connector.GroundcoverConnector',
        'iconUrl': '/icons/groundcover.svg',
        'stalenessThresholdHours': 24,
        'supportedOperations': ['get_usage', 'get_cost_breakdown'],
        'syncFields': ['costBreakdown', 'monthlyTrend', 'clusterUsage'],
        'tipsRepository': 'ViewMyBill-CostOptimizationTips',
        'invoiceFields': {'issuerLabel': 'GroundCover Ltd.', 'accountIdPattern': r'^[A-Za-z0-9_\-]+$', 'currencyDefault': 'USD'},
        'cacheSchema': {'pkPrefix': 'GROUNDCOVER', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
        'costEstimationRates': {},
    },
]

for p in providers:
    p['createdAt'] = now
    p['updatedAt'] = now
    try:
        table.put_item(Item=p, ConditionExpression='attribute_not_exists(providerKey)')
        print(f'  + {p["providerKey"]} created')
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f'  - {p["providerKey"]} already exists')
        else:
            print(f'  ! {p["providerKey"]} failed: {e}')

print('Done: ConnectorConfig seeded')
