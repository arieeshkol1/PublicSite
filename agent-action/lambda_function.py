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

try:
    import connector_config_cache
except ImportError:
    connector_config_cache = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Hardcoded constants — no environment variables needed.
# This avoids KMS decryption issues when Lambda has a customer-managed KMS key.
TIPS_TABLE_NAME = 'ViewMyBill-CostOptimizationTips'
COST_CACHE_TABLE_NAME = 'Cost_Cache_Table'

# Knowledge group tools that do NOT require an accountId (platform-wide data)
KNOWLEDGE_TOOLS_NO_ACCOUNT = {'getOptimizationTips', 'getPricingData', 'updateDrilldownPlan'}

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Handle Bedrock Agent action group invocations."""
    logger.info(f"Agent action event: {json.dumps(event, default=str)}")

    # Log warning if connector config is using fallback mode
    if connector_config_cache and connector_config_cache.is_fallback_active():
        logger.warning("ConnectorConfig: dynamic configuration unavailable, serving from vendor_registry.json fallback")

    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')

    try:
        parameters = {p['name']: p['value'] for p in event.get('parameters', [])}

        # Bedrock Agent sometimes wraps string parameters in literal quotes
        # (e.g. "'991105135552'" instead of "991105135552") or HTML-encoded
        # quotes (&#39; or &quot;). Strip all variants aggressively.
        for key in parameters:
            val = parameters[key]
            if isinstance(val, str):
                # Decode HTML entities first (&#39; -> ', &quot; -> ")
                val = val.replace('&#39;', "'").replace('&quot;', '"').replace('&amp;', '&')
                # Strip wrapping quotes (repeat to handle double-wrapped)
                for _ in range(3):
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                # Final strip of whitespace
                val = val.strip()
                parameters[key] = val.strip()

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
        # Trim large responses progressively to keep under Bedrock limit
        logger.warning(f"Tool response too large ({len(result_json)} chars), trimming...")

        # Pass 1: limit breakdowns and daily data
        if 'dailyCosts' in result:
            result['dailyCosts'] = result['dailyCosts'][-7:]  # Keep only last 7 days
        if 'topServices' in result:
            result['topServices'] = result['topServices'][:5]
        if 'currentMonthServices' in result:
            result['currentMonthServices'] = result['currentMonthServices'][:5]
        if 'modelBreakdown' in result:
            result['modelBreakdown'] = result['modelBreakdown'][:5]
        if 'userBreakdown' in result:
            result['userBreakdown'] = result['userBreakdown'][:5]
        if 'projectBreakdown' in result:
            result['projectBreakdown'] = result['projectBreakdown'][:5]
        # Remove usageTypeBreakdown if present (very verbose)
        result.pop('usageTypeBreakdown', None)

        result_json = json.dumps(result, default=str)

        # Pass 2: if still over limit, drop verbose fields entirely
        if len(result_json) > 12000:
            logger.warning(f"Still too large after pass 1 ({len(result_json)} chars), aggressive trim...")
            result.pop('dailyCosts', None)
            result.pop('forecastHint', None)
            result.pop('projectBreakdown', None)
            # Keep modelBreakdown/userBreakdown/tokenSummary (compact, high value)
            result_json = json.dumps(result, default=str)

        # Pass 3: nuclear — keep only the absolute essentials
        if len(result_json) > 12000:
            logger.warning(f"Still too large after pass 2 ({len(result_json)} chars), nuclear trim...")
            result.pop('userBreakdown', None)
            result.pop('modelBreakdown', None)
            result.pop('tokenSummary', None)
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
    result = provider_router.route_tool(tool_name, account_id, member_email, parameters)

    # Handle notSupported: return a helpful message instead of blindly retrying
    # with an irrelevant tool (e.g. getComputeInstances for an AI vendor account)
    if isinstance(result, dict) and result.get('notSupported') is True:
        available_ops = result.get('availableOperations', [])
        # Only retry with fallback if the alternative is a cost/usage tool
        # (useful fallbacks). Don't retry with unrelated tools.
        cost_tools = {'getCostBreakdown', 'getMonthlyTrend', 'getAIUsage'}
        useful_fallbacks = [op for op in available_ops if op in cost_tools]
        if useful_fallbacks:
            fallback_tool = useful_fallbacks[0]
            logger.warning(f"Tool fallback: {tool_name} -> {fallback_tool} for account {account_id}")
            result = provider_router.route_tool(fallback_tool, account_id, member_email, parameters)
        else:
            # Return clear guidance — don't attempt irrelevant tools
            logger.warning(f"Tool {tool_name} not supported for account {account_id}, no useful alternatives")
            result = {
                'notApplicable': True,
                'message': f'{tool_name} is not applicable for this account type. '
                           f'For AI vendor accounts, use getCostBreakdown or getOptimizationTips to analyze costs and get savings recommendations.',
                'availableOperations': available_ops,
            }

    return result


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
    elif tool_name == 'updateDrilldownPlan':
        service = parameters.get('service', '')
        tip_id = parameters.get('tipId', '')
        drilldown_apis_str = parameters.get('drilldownApis', '[]')
        return _update_drilldown_plan(service, tip_id, drilldown_apis_str)
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


def _update_drilldown_plan(service: str, tip_id: str, drilldown_apis_str: str) -> dict:
    """
    Write or update the drilldownApis field for a tip in the Tips table.
    Used by the self-healing flow when the Agent detects a broken plan.

    Args:
        service: Tips table partition key (e.g., 'EC2')
        tip_id: Tips table sort key (e.g., 'ec2-idle-instances')
        drilldown_apis_str: JSON string of the drilldownApis list

    Returns:
        Success or error dict
    """
    if not service or not tip_id:
        return {'error': 'service and tipId are required'}

    try:
        drilldown_apis = json.loads(drilldown_apis_str)
    except (json.JSONDecodeError, TypeError):
        return {'error': 'drilldownApis must be a valid JSON array'}

    if not isinstance(drilldown_apis, list) or not drilldown_apis:
        return {'error': 'drilldownApis must be a non-empty array'}

    # Validate each entry has at minimum service and operation
    for i, entry in enumerate(drilldown_apis):
        if not isinstance(entry, dict):
            return {'error': f'Entry {i} must be a dict with service and operation fields'}
        if not entry.get('service') or not entry.get('operation'):
            return {'error': f'Entry {i} must have non-empty service and operation fields'}

    tips_table = dynamodb.Table(TIPS_TABLE_NAME)

    try:
        tips_table.update_item(
            Key={'service': service, 'tipId': tip_id},
            UpdateExpression='SET drilldownApis = :apis, healedAt = :ts',
            ExpressionAttributeValues={
                ':apis': drilldown_apis,
                ':ts': datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Self-healing: updated drilldownApis for {service}/{tip_id} ({len(drilldown_apis)} steps)")
        return {
            'success': True,
            'message': f'Drilldown plan updated for {service}/{tip_id}',
            'stepCount': len(drilldown_apis),
        }
    except ClientError as e:
        logger.error(f"Failed to update drilldown plan for {service}/{tip_id}: {e}")
        return {'error': 'Failed to update drilldown plan', 'retryable': True}
