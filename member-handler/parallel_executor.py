"""
Parallel Executor for AI Chat Data Gathering.

Provides:
- _gather_aws_data_parallel(): Executes independent AWS API calls concurrently
  using ThreadPoolExecutor(max_workers=5). Each API call has a 10-second timeout.
  Failed calls are logged and skipped — partial results are returned.
- _gather_multi_account_parallel(): Processes multiple accounts concurrently
  using ThreadPoolExecutor(max_workers=3). Routes each account to its respective
  connector. Failed accounts are logged and tracked in results.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 12.1, 12.2, 12.3, 12.4
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timedelta, timezone

import boto3

from intent_classifier import get_apis_for_intent
from connectors import get_connector
from connectors.base_connector import AuthenticationError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Per-call timeout in seconds
PER_CALL_TIMEOUT = 10

# Maximum concurrent workers per account
MAX_WORKERS = 5

# Maximum concurrent workers for multi-account processing
MAX_ACCOUNT_WORKERS = 3


def _make_client(credentials: dict, service: str, region: str = 'us-east-1'):
    """Create a boto3 client using STS temporary credentials."""
    return boto3.client(
        service,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region,
    )


# ---------------------------------------------------------------------------
# Individual API call functions
# Each returns a tuple of (data_key, data_value, action_description)
# ---------------------------------------------------------------------------


def _fetch_ec2_instances(credentials: dict) -> tuple[str, list, str]:
    """Fetch EC2 instances (running and stopped) from a single region."""
    ec2 = _make_client(credentials, 'ec2')
    instances = ec2.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
    )
    instance_list = []
    for res in instances.get('Reservations', []):
        for inst in res.get('Instances', []):
            name_tag = ''
            for tag in inst.get('Tags', []):
                if tag['Key'] == 'Name':
                    name_tag = tag['Value']
            instance_list.append({
                'id': inst['InstanceId'],
                'type': inst['InstanceType'],
                'state': inst['State']['Name'],
                'name': name_tag,
                'region': 'us-east-1',
                'az': inst.get('Placement', {}).get('AvailabilityZone', ''),
                'platform': inst.get('Platform', 'Linux'),
            })
    return ('ec2_instances', instance_list, 'ec2:DescribeInstances')


def _fetch_cloudwatch_metrics(credentials: dict) -> tuple[str, dict, str]:
    """Fetch CloudWatch EC2 CPU metrics for rightsizing analysis."""
    cw = _make_client(credentials, 'cloudwatch')
    now = datetime.now(timezone.utc)
    start_30d = now - timedelta(days=30)

    # Get aggregate EC2 CPU utilization across the account
    resp = cw.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        StartTime=start_30d,
        EndTime=now,
        Period=2592000,  # 30 days
        Statistics=['Average', 'Maximum'],
    )
    datapoints = resp.get('Datapoints', [])
    avg_cpu = 0.0
    max_cpu = 0.0
    if datapoints:
        avg_cpu = datapoints[0].get('Average', 0.0)
        max_cpu = datapoints[0].get('Maximum', 0.0)

    metrics = {
        'account_avg_cpu_pct': round(avg_cpu, 1),
        'account_max_cpu_pct': round(max_cpu, 1),
        'period_days': 30,
    }
    return ('cloudwatch_metrics', metrics, 'cloudwatch:GetMetricStatistics (EC2 CPU)')


def _fetch_rds_instances(credentials: dict) -> tuple[str, list, str]:
    """Fetch RDS database instances."""
    rds = _make_client(credentials, 'rds')
    dbs = rds.describe_db_instances()
    rds_list = [{
        'id': d['DBInstanceIdentifier'],
        'class': d['DBInstanceClass'],
        'engine': d['Engine'],
        'status': d['DBInstanceStatus'],
        'multiAz': d.get('MultiAZ', False),
        'storage_gb': d.get('AllocatedStorage', 0),
    } for d in dbs.get('DBInstances', [])]
    return ('rds_instances', rds_list, 'rds:DescribeDBInstances')


def _fetch_s3_buckets(credentials: dict) -> tuple[str, list, str]:
    """Fetch S3 bucket list."""
    s3 = _make_client(credentials, 's3')
    buckets = s3.list_buckets()
    bucket_list = [{
        'name': b['Name'],
        'created': str(b['CreationDate']),
    } for b in buckets.get('Buckets', [])]
    return ('s3_buckets', bucket_list, 's3:ListBuckets')


def _fetch_ebs_volumes(credentials: dict) -> tuple[str, dict, str]:
    """Fetch EBS volume summary for storage analysis."""
    ec2 = _make_client(credentials, 'ec2')
    vols = ec2.describe_volumes()
    vol_summary = {
        'total_gb': 0,
        'gp2_count': 0,
        'gp2_gb': 0,
        'gp3_count': 0,
        'io1_count': 0,
        'unattached_count': 0,
        'unattached_gb': 0,
        'unattached_volumes': [],
    }
    for v in vols.get('Volumes', []):
        size = v.get('Size', 0)
        vol_summary['total_gb'] += size
        vtype = v.get('VolumeType', '')
        if vtype == 'gp2':
            vol_summary['gp2_count'] += 1
            vol_summary['gp2_gb'] += size
        elif vtype == 'gp3':
            vol_summary['gp3_count'] += 1
        elif vtype == 'io1':
            vol_summary['io1_count'] += 1
        if not v.get('Attachments'):
            vol_summary['unattached_count'] += 1
            vol_summary['unattached_gb'] += size
            vol_summary['unattached_volumes'].append({
                'volumeId': v['VolumeId'],
                'size_gb': size,
                'type': vtype,
                'monthly_cost_usd': round(
                    size * 0.10 if vtype in ('gp2', 'gp3') else size * 0.125, 2
                ),
            })
    vol_summary['unattached_monthly_cost_usd'] = round(
        vol_summary['unattached_gb'] * 0.10, 2
    )
    vol_summary['gp2_to_gp3_savings_usd'] = round(
        vol_summary['gp2_gb'] * 0.02, 2
    )
    return ('ebs_summary', vol_summary, 'ec2:DescribeVolumes')


def _fetch_nat_gateways(credentials: dict) -> tuple[str, dict, str]:
    """Fetch NAT Gateways, Elastic IPs, and VPC Endpoints for network analysis."""
    ec2 = _make_client(credentials, 'ec2')
    result = {}

    # NAT Gateways
    nat_gws = ec2.describe_nat_gateways(
        Filter=[{'Name': 'state', 'Values': ['available', 'pending']}]
    )
    nat_list = []
    for gw in nat_gws.get('NatGateways', []):
        name_tag = next(
            (t['Value'] for t in gw.get('Tags', []) if t['Key'] == 'Name'), ''
        )
        nat_list.append({
            'natGatewayId': gw['NatGatewayId'],
            'state': gw['State'],
            'subnetId': gw['SubnetId'],
            'vpcId': gw['VpcId'],
            'name': name_tag,
            'createTime': str(gw.get('CreateTime', '')),
        })
    result['nat_gateways'] = nat_list
    result['nat_gateway_count'] = len(nat_list)

    # Elastic IPs
    eips = ec2.describe_addresses()
    unattached_eips = [
        {'allocationId': e.get('AllocationId', ''), 'publicIp': e.get('PublicIp', '')}
        for e in eips.get('Addresses', [])
        if not e.get('AssociationId')
    ]
    result['elastic_ips'] = {
        'total': len(eips.get('Addresses', [])),
        'unattached': len(unattached_eips),
        'unattached_monthly_cost_usd': round(len(unattached_eips) * 3.65, 2),
        'unattached_list': unattached_eips[:10],
    }

    # VPC Endpoints
    endpoints = ec2.describe_vpc_endpoints(
        Filters=[{'Name': 'vpc-endpoint-state', 'Values': ['available', 'pending']}]
    )
    ep_list = []
    for ep in endpoints.get('VpcEndpoints', []):
        ep_list.append({
            'endpointId': ep.get('VpcEndpointId', ''),
            'type': ep.get('VpcEndpointType', ''),
            'serviceName': ep.get('ServiceName', ''),
            'state': ep.get('State', ''),
        })
    interface_ep_count = sum(1 for e in ep_list if e['type'] == 'Interface')
    result['vpc_endpoints'] = {
        'total': len(ep_list),
        'interface_count': interface_ep_count,
        'interface_monthly_cost_usd': round(interface_ep_count * 7.20, 2),
        'endpoints': ep_list[:10],
    }

    return ('network_data', result, 'ec2:DescribeNatGateways+DescribeAddresses+DescribeVpcEndpoints')


def _fetch_lambda_functions(credentials: dict) -> tuple[str, list, str]:
    """Fetch Lambda function list."""
    lam = _make_client(credentials, 'lambda')
    funcs = lam.list_functions()
    func_list = [{
        'name': f['FunctionName'],
        'runtime': f.get('Runtime', ''),
        'memory': f.get('MemorySize', 0),
        'timeout': f.get('Timeout', 0),
    } for f in funcs.get('Functions', [])]
    return ('lambda_functions', func_list, 'lambda:ListFunctions')


# ---------------------------------------------------------------------------
# API identifier to fetch function name mapping
# The mapping uses string names to allow proper mocking in tests. The actual
# function is resolved at runtime via globals().
# ---------------------------------------------------------------------------

API_FETCH_MAP = {
    'ec2_describe_instances': '_fetch_ec2_instances',
    'cloudwatch': '_fetch_cloudwatch_metrics',
    'rds_describe_instances': '_fetch_rds_instances',
    's3_list_buckets': '_fetch_s3_buckets',
    'ebs_volumes': '_fetch_ebs_volumes',
    'nat_gateways': '_fetch_nat_gateways',
    'eips': '_fetch_nat_gateways',        # Covered by nat_gateways call
    'vpc_endpoints': '_fetch_nat_gateways',  # Covered by nat_gateways call
    'lambda_list_functions': '_fetch_lambda_functions',
}


def _resolve_fetch_function(func_name: str):
    """Resolve a fetch function by name from the module globals."""
    import parallel_executor
    return getattr(parallel_executor, func_name)


def _gather_aws_data_parallel(
    credentials: dict,
    question: str,
    intent: set[str],
) -> tuple[dict, list]:
    """
    Execute independent AWS API calls concurrently based on intent classification.

    Uses ThreadPoolExecutor with max_workers=5 per account.
    Enforces 10-second per-call timeout.
    Logs and skips failed individual calls, continues with successful results.

    Args:
        credentials: STS temporary credentials dict with AccessKeyId,
                     SecretAccessKey, SessionToken.
        question: The user's question (passed for context, not used for routing
                  since intent already determined).
        intent: Set of intent categories from _classify_intent().

    Returns:
        Tuple of (account_data_dict, executed_actions_list):
        - account_data_dict: Merged data from all successful API calls
        - executed_actions_list: List of action descriptions for successful calls
    """
    # Determine which APIs to call based on intent
    apis_to_call = get_apis_for_intent(intent)

    # cost_explorer is handled separately (it's always needed and has its own
    # complex logic for date comparisons, tag filtering, etc.). This parallel
    # executor handles the resource-level API calls only.
    apis_to_call.discard('cost_explorer')

    # Deduplicate fetch functions (nat_gateways, eips, vpc_endpoints all use same function)
    fetch_tasks: dict[str, callable] = {}
    for api_id in apis_to_call:
        if api_id in API_FETCH_MAP:
            func_name = API_FETCH_MAP[api_id]
            if func_name not in fetch_tasks:
                fetch_tasks[func_name] = _resolve_fetch_function(func_name)

    if not fetch_tasks:
        return ({}, [])

    data = {}
    actions = []

    logger.info(
        f"Parallel executor: submitting {len(fetch_tasks)} API calls "
        f"for intent={intent}"
    )

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_name = {}
        for func_name, func in fetch_tasks.items():
            future = executor.submit(func, credentials)
            future_to_name[future] = func_name

        # Collect results with per-call timeout
        for future, func_name in future_to_name.items():
            try:
                result = future.result(timeout=PER_CALL_TIMEOUT)
                if result is None:
                    continue

                data_key, data_value, action_desc = result

                # For network_data, flatten into the main data dict
                if data_key == 'network_data' and isinstance(data_value, dict):
                    data.update(data_value)
                else:
                    data[data_key] = data_value

                actions.append(action_desc)
                logger.info(f"Parallel executor: {func_name} completed successfully")

            except TimeoutError:
                logger.warning(
                    f"Parallel executor: {func_name} timed out after "
                    f"{PER_CALL_TIMEOUT}s, skipping"
                )
            except Exception as e:
                logger.warning(
                    f"Parallel executor: {func_name} failed with "
                    f"{type(e).__name__}: {e}, skipping"
                )

    logger.info(
        f"Parallel executor: completed with {len(actions)} successful calls "
        f"out of {len(fetch_tasks)} submitted"
    )

    return (data, actions)


def _process_single_account(account_config: tuple, question: str) -> dict:
    """
    Process a single account by routing to its connector and retrieving cost data.

    Args:
        account_config: Tuple of (account_id, provider, credentials)
        question: The user's question (for context/logging)

    Returns:
        Dict with either successful data or error info:
        - On success: {"accountId": str, "provider": str, "data": dict}
        - On failure: {"accountId": str, "provider": str, "error": str}
    """
    account_id, provider, credentials = account_config

    try:
        connector = get_connector(provider)
        if connector is None:
            return {
                'accountId': account_id,
                'provider': provider,
                'error': f'No connector available for provider: {provider}',
            }

        # Authenticate with the connector
        auth_context = connector.authenticate(credentials)

        # Get cost data (last 30 days)
        now = datetime.now(timezone.utc)
        end_date = now.strftime('%Y-%m-%d')
        start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')

        cost_data = connector.get_cost_data(auth_context, account_id, start_date, end_date)

        return {
            'accountId': account_id,
            'provider': provider,
            'data': cost_data,
        }

    except AuthenticationError as e:
        logger.warning(
            f"Multi-account parallel: authentication failed for "
            f"account={account_id}, provider={provider}: {e}"
        )
        return {
            'accountId': account_id,
            'provider': provider,
            'error': f'Authentication failed: {e}',
        }
    except Exception as e:
        logger.warning(
            f"Multi-account parallel: data gathering failed for "
            f"account={account_id}, provider={provider}: "
            f"{type(e).__name__}: {e}"
        )
        return {
            'accountId': account_id,
            'provider': provider,
            'error': f'{type(e).__name__}: {e}',
        }


def _gather_multi_account_parallel(account_configs: list, question: str) -> dict:
    """
    Process multiple accounts concurrently using ThreadPoolExecutor(max_workers=3).

    Each account is routed to its respective cloud connector. Failed accounts
    are logged with account ID, provider, and error details. Partial results
    from successful accounts are always returned.

    Args:
        account_configs: List of tuples (account_id, provider, credentials)
            - account_id: Cloud account identifier (AWS 12-digit, Azure UUID, GCP project ID)
            - provider: One of "aws", "azure", "gcp"
            - credentials: Provider-specific credentials dict
        question: The user's question

    Returns:
        Dict with:
        - "accounts": dict mapping account_id -> cost data for successful accounts
        - "failedAccounts": list of {"accountId": str, "provider": str, "error": str}
        - "totalAccounts": int total accounts attempted
        - "successfulAccounts": int count of successful accounts

    Requirements: 8.5, 12.1, 12.2, 12.3, 12.4
    """
    if not account_configs:
        return {
            'accounts': {},
            'failedAccounts': [],
            'totalAccounts': 0,
            'successfulAccounts': 0,
        }

    accounts_data = {}
    failed_accounts = []

    logger.info(
        f"Multi-account parallel: processing {len(account_configs)} accounts "
        f"with max_workers={MAX_ACCOUNT_WORKERS}"
    )

    with ThreadPoolExecutor(max_workers=MAX_ACCOUNT_WORKERS) as executor:
        # Submit all account processing tasks
        future_to_account = {}
        for config in account_configs:
            future = executor.submit(_process_single_account, config, question)
            future_to_account[future] = config[0]  # account_id

        # Collect results as they complete
        for future in as_completed(future_to_account):
            account_id = future_to_account[future]
            try:
                result = future.result(timeout=PER_CALL_TIMEOUT)

                if 'error' in result:
                    # Account processing failed
                    failed_accounts.append({
                        'accountId': result['accountId'],
                        'provider': result['provider'],
                        'error': result['error'],
                    })
                    logger.warning(
                        f"Multi-account parallel: account {result['accountId']} "
                        f"(provider={result['provider']}) failed: {result['error']}"
                    )
                else:
                    # Account processing succeeded
                    accounts_data[result['accountId']] = result['data']
                    logger.info(
                        f"Multi-account parallel: account {result['accountId']} "
                        f"(provider={result['provider']}) completed successfully"
                    )

            except TimeoutError:
                # Find the provider from the config
                provider = 'unknown'
                for config in account_configs:
                    if config[0] == account_id:
                        provider = config[1]
                        break

                failed_accounts.append({
                    'accountId': account_id,
                    'provider': provider,
                    'error': f'Account processing timed out after {PER_CALL_TIMEOUT}s',
                })
                logger.warning(
                    f"Multi-account parallel: account {account_id} "
                    f"(provider={provider}) timed out after {PER_CALL_TIMEOUT}s"
                )

            except Exception as e:
                # Find the provider from the config
                provider = 'unknown'
                for config in account_configs:
                    if config[0] == account_id:
                        provider = config[1]
                        break

                failed_accounts.append({
                    'accountId': account_id,
                    'provider': provider,
                    'error': f'{type(e).__name__}: {e}',
                })
                logger.warning(
                    f"Multi-account parallel: account {account_id} "
                    f"(provider={provider}) failed with {type(e).__name__}: {e}"
                )

    successful_count = len(accounts_data)
    total_count = len(account_configs)

    logger.info(
        f"Multi-account parallel: completed {successful_count}/{total_count} "
        f"accounts successfully, {len(failed_accounts)} failed"
    )

    return {
        'accounts': accounts_data,
        'failedAccounts': failed_accounts,
        'totalAccounts': total_count,
        'successfulAccounts': successful_count,
    }
