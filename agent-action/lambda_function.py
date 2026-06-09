"""
SlashMyBill Agent Action Group Lambda.
Called by the Bedrock Agent to execute tool operations on member accounts.

Uses the vendor-neutral routing architecture:
1. Resolve legacy paths to vendor-neutral tool names (legacy_mapper)
2. Route tool invocations to the correct cloud connector (provider_router)
3. Handle Knowledge tools (getOptimizationTips, getPricingData) directly (no account needed)
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import legacy_mapper
import provider_router

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Hardcoded constants — no environment variables needed.
# This avoids KMS decryption issues when Lambda has a customer-managed KMS key.
TIPS_TABLE_NAME = 'ViewMyBill-CostOptimizationTips'
COST_CACHE_TABLE_NAME = 'Cost_Cache_Table'

# Knowledge group tools that do NOT require an accountId (platform-wide data)
KNOWLEDGE_TOOLS_NO_ACCOUNT = {'getOptimizationTips', 'getPricingData'}

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Handle Bedrock Agent action group invocations."""
    logger.info(f"Agent action event: {json.dumps(event, default=str)}")

    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')

    try:
        parameters = {p['name']: p['value'] for p in event.get('parameters', [])}

        account_id = parameters.get('accountId', '')
        member_email = parameters.get('memberEmail', '')

        # Step 1: Resolve legacy path to vendor-neutral tool name
        tool_name = legacy_mapper.resolve_path(api_path)

        # Step 2: Route and execute
        result = _execute_tool(tool_name, account_id, member_email, parameters)
    except Exception as e:
        # Top-level catch: ensure the Bedrock Agent envelope is never broken.
        # Never expose sensitive provider error details to the user.
        logger.error(f"Unhandled error processing {api_path}: {e}", exc_info=True)
        result = {
            'error': 'An unexpected error occurred while processing your request.',
            'retryable': True,
            'guidance': 'Try again in a moment. If the issue persists, contact support.',
        }

    # Step 3: Return Bedrock Agent response envelope (always HTTP 200)
    # Cap response size to prevent Bedrock EventStreamError on oversized tool responses
    result_json = json.dumps(result, default=str)
    if len(result_json) > 12000:
        # Trim large responses: remove daily costs and limit services to keep under limit
        logger.warning(f"Tool response too large ({len(result_json)} chars), trimming...")
        if 'dailyCosts' in result:
            result['dailyCosts'] = result['dailyCosts'][-7:]  # Keep only last 7 days
        if 'topServices' in result:
            result['topServices'] = result['topServices'][:5]
        if 'currentMonthServices' in result:
            result['currentMonthServices'] = result['currentMonthServices'][:5]
        result_json = json.dumps(result, default=str)

    response_body = {'application/json': {'body': result_json}}

    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': event.get('httpMethod', 'POST'),
            'httpStatusCode': 200,
            'responseBody': response_body,
        }
    }


def _execute_tool(tool_name: str, account_id: str, member_email: str, parameters: dict) -> dict:
    """
    Execute a tool by name — handles Knowledge tools directly, routes
    all other tools through the provider_router.

    Knowledge tools (getOptimizationTips, getPricingData) do not require
    an accountId per Requirement 10.5. They query platform-wide data.
    """
    # Knowledge group tools — handled directly, no account needed
    if tool_name in KNOWLEDGE_TOOLS_NO_ACCOUNT:
        return _handle_knowledge_tool(tool_name, parameters)

    # All other tools require accountId and memberEmail for provider routing
    if not account_id or not member_email:
        # If this is a Knowledge tool invoked without accountId, handle gracefully
        return {
            'error': 'Missing required parameters: accountId and memberEmail',
            'guidance': 'Please provide accountId and memberEmail for this operation.',
        }

    # Route through provider_router (resolves provider, dispatches to connector)
    return provider_router.route_tool(tool_name, account_id, member_email, parameters)


def _handle_knowledge_tool(tool_name: str, parameters: dict) -> dict:
    """
    Handle Knowledge group tools that don't require account context.
    These query platform-wide data (tips table, pricing API).
    """
    if tool_name == 'getOptimizationTips':
        service = parameters.get('service', '')
        return _get_optimization_tips(service)
    elif tool_name == 'getPricingData':
        service_code = parameters.get('serviceCode', '') or parameters.get('service', '')
        filters = parameters.get('filters', '')
        region = parameters.get('region', 'us-east-1')
        return _get_pricing_data(service_code, filters, region)
    else:
        return {'error': f'Unknown knowledge tool: {tool_name}'}


def _get_optimization_tips(service=''):
    """Query the cost optimization tips table."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        if service:
            result = tips_table.query(
                KeyConditionExpression=Key('service').eq(service.upper())
            )
        else:
            result = tips_table.scan(Limit=20)

        tips = []
        for item in result.get('Items', []):
            tips.append({
                'service': str(item.get('service', '')),
                'title': str(item.get('title', '')),
                'description': str(item.get('description', '')),
                'estimatedSavings': str(item.get('estimatedSavings', '')),
                'difficulty': str(item.get('difficulty', '')),
            })
        return {'tips': tips, 'count': len(tips)}
    except Exception as e:
        return {'error': str(e)}


def _get_pricing_data(service_code, filters_str='', region='us-east-1'):
    """
    Query the AWS Pricing API for real-time pricing data.
    The Pricing API endpoint is always us-east-1 regardless of target region.
    filters_str: comma-separated key=value pairs, e.g. "instanceType=m5.large,operatingSystem=Linux"
    """
    try:
        pricing = boto3.client('pricing', region_name='us-east-1')

        if not service_code:
            # Return available service codes if none specified
            response = pricing.describe_services(MaxResults=100)
            services = [s['ServiceCode'] for s in response.get('Services', [])]
            return {'availableServices': services}

        # Build filters from the comma-separated string
        price_filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': _region_to_location(region)}
        ]
        if filters_str:
            for pair in filters_str.split(','):
                if '=' in pair:
                    key, value = pair.strip().split('=', 1)
                    price_filters.append({'Type': 'TERM_MATCH', 'Field': key.strip(), 'Value': value.strip()})

        response = pricing.get_products(
            ServiceCode=service_code,
            Filters=price_filters,
            MaxResults=10,
        )

        results = []
        for price_str in response.get('PriceList', []):
            price_item = json.loads(price_str)
            product = price_item.get('product', {})
            attributes = product.get('attributes', {})
            terms = price_item.get('terms', {})

            # Extract on-demand price
            on_demand = terms.get('OnDemand', {})
            price_dimensions = []
            for term_key, term_val in on_demand.items():
                for dim_key, dim in term_val.get('priceDimensions', {}).items():
                    usd = dim.get('pricePerUnit', {}).get('USD', '0')
                    if float(usd) > 0:
                        price_dimensions.append({
                            'description': dim.get('description', ''),
                            'unit': dim.get('unit', ''),
                            'pricePerUnit_USD': usd,
                        })

            if price_dimensions:
                results.append({
                    'serviceCode': service_code,
                    'attributes': {k: v for k, v in attributes.items()
                                   if k in ['instanceType', 'vcpu', 'memory', 'operatingSystem',
                                            'storageClass', 'volumeType', 'group', 'groupDescription']},
                    'pricing': price_dimensions,
                })

        return {
            'serviceCode': service_code,
            'region': region,
            'results': results,
            'count': len(results),
        }
    except Exception as e:
        return {'error': str(e)}


def _region_to_location(region):
    """Map AWS region code to the location name used by the Pricing API."""
    mapping = {
        'us-east-1': 'US East (N. Virginia)',
        'us-east-2': 'US East (Ohio)',
        'us-west-1': 'US West (N. California)',
        'us-west-2': 'US West (Oregon)',
        'eu-west-1': 'Europe (Ireland)',
        'eu-central-1': 'Europe (Frankfurt)',
        'ap-southeast-1': 'Asia Pacific (Singapore)',
        'ap-northeast-1': 'Asia Pacific (Tokyo)',
    }
    return mapping.get(region, 'US East (N. Virginia)')
