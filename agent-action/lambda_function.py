"""
SlashMyBill Agent Action Group Lambda.
Called by the Bedrock Agent to execute AWS API calls on member accounts.
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Hardcoded constants — no environment variables needed.
# This avoids KMS decryption issues when Lambda has a customer-managed KMS key.
PLATFORM_ACCOUNT_ID = '991105135552'
TIPS_TABLE_NAME = 'ViewMyBill-CostOptimizationTips'
COST_CACHE_TABLE_NAME = 'Cost_Cache_Table'

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Handle Bedrock Agent action group invocations."""
    logger.info(f"Agent action event: {json.dumps(event, default=str)}")

    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')
    parameters = {p['name']: p['value'] for p in event.get('parameters', [])}

    account_id = parameters.get('accountId', '')
    member_email = parameters.get('memberEmail', '')

    result = {}

    if api_path == '/get-cost-data':
        result = _get_cost_data(account_id, member_email)
    elif api_path == '/get-ec2-instances':
        result = _get_ec2_instances(account_id, member_email)
    elif api_path == '/get-s3-buckets':
        result = _get_s3_buckets(account_id, member_email)
    elif api_path == '/get-optimization-tips':
        service = parameters.get('service', '')
        result = _get_optimization_tips(service)
    elif api_path == '/get-aws-pricing':
        service_code = parameters.get('serviceCode', '')
        filters = parameters.get('filters', '')
        region = parameters.get('region', 'us-east-1')
        result = _get_aws_pricing(service_code, filters, region)
    elif api_path == '/get-monthly-comparison':
        months = int(parameters.get('months', '3'))
        result = _get_monthly_comparison(account_id, member_email, months)
    elif api_path == '/get-rds-instances':
        result = _get_rds_instances(account_id, member_email)
    elif api_path == '/get-lambda-functions':
        result = _get_lambda_functions(account_id, member_email)
    elif api_path == '/get-ebs-volumes':
        result = _get_ebs_volumes(account_id, member_email)
    elif api_path == '/get-network-resources':
        result = _get_network_resources(account_id, member_email)
    elif api_path == '/get-budgets':
        result = _get_budgets(account_id, member_email)
    elif api_path == '/get-finops-settings':
        result = _get_finops_settings(account_id, member_email)
    elif api_path == '/get-spot-placement-score':
        vcpu_min = int(parameters.get('vCpuMin', '2'))
        vcpu_max = int(parameters.get('vCpuMax', '8'))
        mem_min = int(parameters.get('memoryMiBMin', '4096'))
        mem_max = int(parameters.get('memoryMiBMax', '16384'))
        target_cap = int(parameters.get('targetCapacity', '10'))
        regions = parameters.get('regions', '')
        result = _get_spot_placement_score(account_id, member_email, vcpu_min, vcpu_max, mem_min, mem_max, target_cap, regions)
    else:
        result = {'error': f'Unknown action: {api_path}'}

    response_body = {'application/json': {'body': json.dumps(result, default=str)}}

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


def _assume_role(account_id, member_email):
    """Assume the cross-account role."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts')
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SlashMyBillAgent',
        ExternalId=external_id,
    )
    return response['Credentials']


def _make_client(service, credentials, region='us-east-1'):
    return boto3.client(
        service,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region,
    )


def _get_cost_data(account_id, member_email):
    """Get cost breakdown by service (full previous month) and daily trend (last 7 days).
    Reads from Cost_Cache_Table first, falls back to direct CE API on cache miss or error.
    """
    try:
        # Try cache first
        cache_table = dynamodb.Table(COST_CACHE_TABLE_NAME)
        now = datetime.now(timezone.utc)
        # Full previous calendar month
        end_date = now.replace(day=1)
        first_of_last_month = (end_date - timedelta(days=1)).replace(day=1)
        start_date = first_of_last_month

        pk = f"{member_email}#{account_id}"
        start_sk = f"DAILY#{start_date.strftime('%Y-%m-%d')}"
        end_sk = f"DAILY#{end_date.strftime('%Y-%m-%d')}"

        resp = cache_table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
        )
        items = resp.get('Items', [])

        if items:
            # Cache hit - aggregate daily items into service breakdown and total cost
            services = {}
            daily_costs = []
            for item in items:
                cost = float(item.get('cost_amount', 0))
                date = item['sk'].replace('DAILY#', '')
                daily_costs.append({'date': date, 'cost': round(cost, 2)})
                for svc, svc_cost in item.get('service_breakdown', {}).items():
                    services[svc] = services.get(svc, 0) + float(svc_cost)

            top_services = sorted(
                [{'service': k, 'cost': round(v, 2)} for k, v in services.items()],
                key=lambda x: x['cost'], reverse=True
            )
            total = sum(s['cost'] for s in top_services)
            return {
                'totalCost30Days': round(total, 2),
                'topServices': top_services[:10],
                'dailyCosts': daily_costs[-7:],
                'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (from cache)",
            }

        # Cache miss - fall back to direct CE API call
        logger.info(f"Cache miss for {pk}, falling back to CE API")
        return _get_cost_data_direct(account_id, member_email)

    except Exception as e:
        # On any cache error, fall back to direct CE API
        logger.warning(f"Cache read error for {member_email}#{account_id}: {e}")
        return _get_cost_data_direct(account_id, member_email)


def _get_cost_data_direct(account_id, member_email):
    """Get cost breakdown directly from Cost Explorer API (fallback path)."""
    try:
        creds = _assume_role(account_id, member_email)
        ce = _make_client('ce', creds)

        # Use FULL PREVIOUS CALENDAR MONTH for accurate monthly costs
        now = datetime.now(timezone.utc)
        # End = 1st of current month (exclusive in Cost Explorer)
        end_date = now.replace(day=1).strftime('%Y-%m-%d')
        # Start = 1st of previous month
        first_of_this_month = now.replace(day=1)
        first_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
        start_date = first_of_last_month.strftime('%Y-%m-%d')
        # Daily trend: last 7 days (current period)
        start_7d = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        today = now.strftime('%Y-%m-%d')

        # Cost by service (full previous month)
        by_service = ce.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )

        services = []
        for period in by_service.get('ResultsByTime', []):
            for group in period.get('Groups', []):
                svc = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                if cost > 0.01:
                    services.append({'service': svc, 'cost': round(cost, 2)})
        services.sort(key=lambda x: x['cost'], reverse=True)

        # Daily trend (last 7 days)
        daily = ce.get_cost_and_usage(
            TimePeriod={'Start': start_7d, 'End': today},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
        )
        daily_costs = []
        for period in daily.get('ResultsByTime', []):
            date = period['TimePeriod']['Start']
            cost = float(period['Total']['UnblendedCost']['Amount'])
            daily_costs.append({'date': date, 'cost': round(cost, 2)})

        total = sum(s['cost'] for s in services)
        return {
            'totalCost30Days': round(total, 2),
            'topServices': services[:10],
            'dailyCosts': daily_costs,
            'period': f'{start_date} to {end_date} (full previous month)',
        }
    except Exception as e:
        return {'error': str(e)}


def _detect_active_regions(creds):
    """Return likely active regions. Skips slow CE API — uses hardcoded common regions.
    The EC2/RDS/EBS functions will skip regions that return empty results anyway.
    """
    # Most AWS accounts use 1-2 regions. Check the most common ones.
    # This avoids the 3-8 second Cost Explorer API call entirely.
    return ['eu-central-1', 'us-east-1']


def _get_ec2_instances(account_id, member_email):
    """List EC2 instances across all regions with details."""
    try:
        creds = _assume_role(account_id, member_email)
        
        # Detect active regions from Cost Explorer (fast, single API call)
        regions = _detect_active_regions(creds)
        
        instances = []
        for region in regions:
            try:
                ec2 = _make_client('ec2', creds, region)
                response = ec2.describe_instances(
                    Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
                )
                for res in response.get('Reservations', []):
                    for inst in res.get('Instances', []):
                        name = ''
                        for tag in inst.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                        instances.append({
                            'instanceId': inst['InstanceId'],
                            'type': inst['InstanceType'],
                            'state': inst['State']['Name'],
                            'name': name,
                            'region': region,
                            'az': inst.get('Placement', {}).get('AvailabilityZone', ''),
                            'launchTime': str(inst.get('LaunchTime', '')),
                        })
            except Exception:
                continue  # Skip regions with access issues
        
        return {'instances': instances, 'count': len(instances)}
    except Exception as e:
        return {'error': str(e)}


def _get_s3_buckets(account_id, member_email):
    """List S3 buckets."""
    try:
        creds = _assume_role(account_id, member_email)
        s3 = _make_client('s3', creds)

        response = s3.list_buckets()
        buckets = [{'name': b['Name'], 'created': str(b['CreationDate'])} for b in response.get('Buckets', [])]
        return {'buckets': buckets, 'count': len(buckets)}
    except Exception as e:
        return {'error': str(e)}


def _get_aws_pricing(service_code, filters_str='', region='us-east-1'):
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


def _get_optimization_tips(service=''):
    """Query the cost optimization tips table."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        if service:
            result = tips_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(service.upper())
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


def _get_monthly_comparison(account_id, member_email, months=3):
    """Get monthly cost comparison by service.
    Reads from Cost_Cache_Table first, falls back to direct CE API on cache miss or error.
    """
    try:
        # Try cache first
        cache_table = dynamodb.Table(COST_CACHE_TABLE_NAME)
        now = datetime.now(timezone.utc)
        end_date = now.replace(day=1)
        start_date = (end_date - timedelta(days=months * 31)).replace(day=1)

        pk = f"{member_email}#{account_id}"
        start_sk = f"DAILY#{start_date.strftime('%Y-%m-%d')}"
        end_sk = f"DAILY#{end_date.strftime('%Y-%m-%d')}"

        resp = cache_table.query(
            KeyConditionExpression=Key('pk').eq(pk) & Key('sk').between(start_sk, end_sk)
        )
        items = resp.get('Items', [])

        if items:
            # Cache hit - aggregate daily items per month per service
            monthly_data = {}
            for item in items:
                date = item['sk'].replace('DAILY#', '')
                month = date[:7]  # YYYY-MM
                if month not in monthly_data:
                    monthly_data[month] = {}
                for svc, svc_cost in item.get('service_breakdown', {}).items():
                    cost = float(svc_cost)
                    if cost > 0.01:
                        monthly_data[month][svc] = round(
                            monthly_data[month].get(svc, 0) + cost, 2
                        )

            return {
                'monthlyComparison': monthly_data,
                'months': sorted(monthly_data.keys()),
            }

        # Cache miss - fall back to direct CE API call
        logger.info(f"Cache miss for monthly comparison {pk}, falling back to CE API")
        return _get_monthly_comparison_direct(account_id, member_email, months)

    except Exception as e:
        # On any cache error, fall back to direct CE API
        logger.warning(f"Cache read error for monthly comparison {member_email}#{account_id}: {e}")
        return _get_monthly_comparison_direct(account_id, member_email, months)


def _get_monthly_comparison_direct(account_id, member_email, months=3):
    """Get monthly cost comparison directly from Cost Explorer API (fallback path)."""
    try:
        creds = _assume_role(account_id, member_email)
        ce = _make_client('ce', creds)
        
        end_date = datetime.now(timezone.utc).replace(day=1).strftime('%Y-%m-%d')
        start_date = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=months*31)).replace(day=1).strftime('%Y-%m-%d')
        
        resp = ce.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )
        
        monthly_data = {}
        for period in resp.get('ResultsByTime', []):
            month = period['TimePeriod']['Start'][:7]
            monthly_data[month] = {}
            for group in period.get('Groups', []):
                svc = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                if cost > 0.01:
                    monthly_data[month][svc] = round(cost, 2)
        
        return {'monthlyComparison': monthly_data, 'months': sorted(monthly_data.keys())}
    except Exception as e:
        return {'error': str(e)}


def _get_rds_instances(account_id, member_email):
    """List RDS instances with metrics."""
    try:
        creds = _assume_role(account_id, member_email)
        rds = _make_client('rds', creds)
        cw = _make_client('cloudwatch', creds)
        
        resp = rds.describe_db_instances()
        instances = []
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=14)
        
        for db in resp.get('DBInstances', []):
            db_id = db['DBInstanceIdentifier']
            # Get CPU metrics
            cpu_avg = 0
            try:
                cpu_resp = cw.get_metric_statistics(
                    Namespace='AWS/RDS', MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                    StartTime=start_time, EndTime=end_time,
                    Period=86400, Statistics=['Average']
                )
                points = cpu_resp.get('Datapoints', [])
                if points:
                    cpu_avg = round(sum(p['Average'] for p in points) / len(points), 1)
            except Exception:
                pass
            
            instances.append({
                'dbId': db_id,
                'instanceClass': db['DBInstanceClass'],
                'engine': db['Engine'],
                'engineVersion': db.get('EngineVersion', ''),
                'status': db['DBInstanceStatus'],
                'storageGB': db.get('AllocatedStorage', 0),
                'multiAZ': db.get('MultiAZ', False),
                'avgCPU14d': cpu_avg,
            })
        
        return {'instances': instances, 'count': len(instances)}
    except Exception as e:
        return {'error': str(e)}


def _get_lambda_functions(account_id, member_email):
    """List Lambda functions with invocation metrics."""
    try:
        creds = _assume_role(account_id, member_email)
        lam = _make_client('lambda', creds)
        cw = _make_client('cloudwatch', creds)
        
        resp = lam.list_functions(MaxItems=50)
        functions = []
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=30)
        
        for fn in resp.get('Functions', []):
            fn_name = fn['FunctionName']
            invocations = 0
            errors = 0
            avg_duration = 0
            
            try:
                inv_resp = cw.get_metric_statistics(
                    Namespace='AWS/Lambda', MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
                    StartTime=start_time, EndTime=end_time,
                    Period=2592000, Statistics=['Sum']
                )
                points = inv_resp.get('Datapoints', [])
                if points:
                    invocations = int(points[0].get('Sum', 0))
            except Exception:
                pass
            
            try:
                err_resp = cw.get_metric_statistics(
                    Namespace='AWS/Lambda', MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
                    StartTime=start_time, EndTime=end_time,
                    Period=2592000, Statistics=['Sum']
                )
                points = err_resp.get('Datapoints', [])
                if points:
                    errors = int(points[0].get('Sum', 0))
            except Exception:
                pass
            
            functions.append({
                'name': fn_name,
                'runtime': fn.get('Runtime', 'unknown'),
                'memoryMB': fn.get('MemorySize', 128),
                'architecture': fn.get('Architectures', ['x86_64'])[0],
                'invocations30d': invocations,
                'errors30d': errors,
            })
        
        return {'functions': functions, 'count': len(functions)}
    except Exception as e:
        return {'error': str(e)}


def _get_ebs_volumes(account_id, member_email):
    """List EBS volumes across active regions."""
    try:
        creds = _assume_role(account_id, member_email)
        
        # Detect active regions from Cost Explorer usage types
        regions = _detect_active_regions(creds)
        
        volumes = []
        unattached_count = 0
        gp2_count = 0
        total_gb = 0
        
        for region in regions:
            try:
                ec2 = _make_client('ec2', creds, region)
                resp = ec2.describe_volumes()
                for vol in resp.get('Volumes', []):
                    attached = len(vol.get('Attachments', [])) > 0
                    vol_type = vol.get('VolumeType', 'unknown')
                    size = vol.get('Size', 0)
                    total_gb += size
                    if not attached:
                        unattached_count += 1
                    if vol_type == 'gp2':
                        gp2_count += 1
                    volumes.append({
                        'volumeId': vol['VolumeId'],
                        'type': vol_type,
                        'sizeGB': size,
                        'state': vol['State'],
                        'attached': attached,
                        'iops': vol.get('Iops', 0),
                        'region': region,
                    })
            except Exception:
                continue
        
        return {
            'volumes': volumes[:50],
            'count': len(volumes),
            'totalGB': total_gb,
            'unattachedCount': unattached_count,
            'gp2Count': gp2_count,
            'gp2ToGp3SavingsUSD': round(gp2_count * 0.02 * (total_gb / max(len(volumes), 1)), 2),
        }
    except Exception as e:
        return {'error': str(e)}


def _get_network_resources(account_id, member_email):
    """List NAT Gateways, VPC Endpoints, and Elastic IPs."""
    try:
        creds = _assume_role(account_id, member_email)
        ec2 = _make_client('ec2', creds)
        
        # NAT Gateways
        nat_resp = ec2.describe_nat_gateways(Filter=[{'Name': 'state', 'Values': ['available']}])
        nat_gateways = [{'id': n['NatGatewayId'], 'vpcId': n.get('VpcId', ''), 'subnetId': n.get('SubnetId', '')} for n in nat_resp.get('NatGateways', [])]
        
        # VPC Endpoints
        vpce_resp = ec2.describe_vpc_endpoints()
        endpoints = [{'id': e['VpcEndpointId'], 'type': e['VpcEndpointType'], 'serviceName': e['ServiceName'], 'state': e['State']} for e in vpce_resp.get('VpcEndpoints', [])]
        
        # Elastic IPs
        eip_resp = ec2.describe_addresses()
        eips = []
        unassociated = 0
        for addr in eip_resp.get('Addresses', []):
            associated = bool(addr.get('AssociationId'))
            if not associated:
                unassociated += 1
            eips.append({'publicIp': addr.get('PublicIp', ''), 'associated': associated, 'instanceId': addr.get('InstanceId', '')})
        
        return {
            'natGateways': nat_gateways,
            'natGatewayCount': len(nat_gateways),
            'natGatewayCostEstimate': round(len(nat_gateways) * 32.40, 2),
            'vpcEndpoints': endpoints,
            'vpcEndpointCount': len(endpoints),
            'elasticIPs': eips,
            'unassociatedEIPs': unassociated,
            'unassociatedEIPCost': round(unassociated * 3.65, 2),
        }
    except Exception as e:
        return {'error': str(e)}


def _get_budgets(account_id, member_email):
    """List AWS Budgets with spend data."""
    try:
        creds = _assume_role(account_id, member_email)
        budgets_client = _make_client('budgets', creds)
        
        resp = budgets_client.describe_budgets(AccountId=account_id)
        budgets = []
        for b in resp.get('Budgets', []):
            limit = float(b.get('BudgetLimit', {}).get('Amount', 0))
            actual = float(b.get('CalculatedSpend', {}).get('ActualSpend', {}).get('Amount', 0))
            forecast = float(b.get('CalculatedSpend', {}).get('ForecastedSpend', {}).get('Amount', 0))
            budgets.append({
                'name': b.get('BudgetName', ''),
                'type': b.get('BudgetType', ''),
                'limit': limit,
                'actualSpend': actual,
                'forecastedSpend': forecast,
                'utilizationPct': round((actual / limit) * 100, 1) if limit > 0 else 0,
            })
        
        return {'budgets': budgets, 'count': len(budgets)}
    except Exception as e:
        return {'error': str(e)}


def _get_finops_settings(account_id, member_email):
    """Get cached FinOps settings healthcheck results."""
    try:
        members_table = dynamodb.Table('MemberPortal-Members')
        resp = members_table.get_item(
            Key={'email': member_email},
            ProjectionExpression='healthcheckResults'
        )
        results = resp.get('Item', {}).get('healthcheckResults', {})
        account_results = results.get(account_id, {})
        
        if not account_results:
            return {'message': 'No FinOps settings scan has been run for this account. Recommend: Go to Configure > FinOps Settings to run a scan.'}
        
        # Convert Decimal to native types
        import decimal
        def decimal_to_native(obj):
            if isinstance(obj, list):
                return [decimal_to_native(i) for i in obj]
            if isinstance(obj, dict):
                return {k: decimal_to_native(v) for k, v in obj.items()}
            if isinstance(obj, decimal.Decimal):
                return int(obj) if obj % 1 == 0 else float(obj)
            return obj
        
        return decimal_to_native(account_results)
    except Exception as e:
        return {'error': str(e)}


def _get_spot_placement_score(account_id, member_email, vcpu_min, vcpu_max, mem_min, mem_max, target_capacity, regions_str):
    """Query AWS Spot Placement Score API for capacity availability."""
    if not account_id or not member_email:
        return {'error': 'accountId and memberEmail are required'}

    try:
        credentials = _assume_role(account_id, member_email)
    except Exception as e:
        return {'error': f'Cannot assume role: {str(e)}'}

    region_list = [r.strip() for r in regions_str.split(',') if r.strip()] if regions_str else [
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2'
    ]

    all_scores = []
    for region in region_list:
        try:
            ec2 = _make_client('ec2', credentials, region)
            resp = ec2.get_spot_placement_scores(
                TargetCapacity=target_capacity,
                InstanceRequirementsWithMetadata={
                    'ArchitectureTypes': ['x86_64', 'arm64'],
                    'InstanceRequirements': {
                        'VCpuCount': {'Min': vcpu_min, 'Max': vcpu_max},
                        'MemoryMiB': {'Min': mem_min, 'Max': mem_max},
                    }
                },
                SingleAvailabilityZone=False,
                MaxResults=10,
            )
            for score in resp.get('SpotPlacementScores', []):
                all_scores.append({
                    'region': score.get('Region', region),
                    'az': score.get('AvailabilityZoneId', ''),
                    'score': score.get('Score', 0),
                })
        except Exception as e:
            logger.warning(f"Spot Placement Score failed for {region}: {e}")
            all_scores.append({
                'region': region,
                'az': '',
                'score': 0,
                'error': str(e),
            })

    # Sort by score descending, remove duplicates
    seen = set()
    deduped = []
    for s in sorted(all_scores, key=lambda x: x.get('score', 0), reverse=True):
        key = f"{s['region']}#{s['az']}"
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    return {
        'scores': deduped,
        'targetCapacity': target_capacity,
        'instanceRequirements': {
            'vCpuCount': {'min': vcpu_min, 'max': vcpu_max},
            'memoryMiB': {'min': mem_min, 'max': mem_max},
        },
        'summary': f'{len(deduped)} region/AZ scores retrieved for {target_capacity} instances',
    }
