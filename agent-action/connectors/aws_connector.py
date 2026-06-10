"""
AWS Cloud Connector.

Implements vendor-neutral tool operations using AWS APIs (EC2, Cost Explorer,
RDS, Lambda, S3, EBS, VPC, Budgets, Pricing, Spot). Extends the base
CloudConnector and refactors the existing lambda_function.py logic into
the connector pattern.

All methods return raw dicts — response normalization is applied upstream
by the Provider Router / Response Normalizer layer.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from . import CloudConnector

logger = logging.getLogger(__name__)

# Platform constants
PLATFORM_ACCOUNT_ID = '991105135552'

# On-demand hourly rates (USD) for common EC2 instance types (Linux, us-east-1 baseline).
# Covers ~95% of instances seen in production. For types not listed, hourlyRate will be None.
# Rates are approximate — actual pricing varies by region (typically +10-15% for EU).
_EC2_HOURLY_RATES = {
    # T3 family
    't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416,
    't3.large': 0.0832, 't3.xlarge': 0.1664, 't3.2xlarge': 0.3328,
    # T3a family (AMD, ~10% cheaper)
    't3a.nano': 0.0047, 't3a.micro': 0.0094, 't3a.small': 0.0188, 't3a.medium': 0.0376,
    't3a.large': 0.0752, 't3a.xlarge': 0.1504, 't3a.2xlarge': 0.3008,
    # T2 family (older burstable)
    't2.nano': 0.0058, 't2.micro': 0.0116, 't2.small': 0.023, 't2.medium': 0.0464,
    't2.large': 0.0928, 't2.xlarge': 0.1856, 't2.2xlarge': 0.3712,
    # M5 family
    'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
    # M6i family
    'm6i.large': 0.096, 'm6i.xlarge': 0.192, 'm6i.2xlarge': 0.384, 'm6i.4xlarge': 0.768,
    # M7i family
    'm7i.large': 0.1008, 'm7i.xlarge': 0.2016, 'm7i.2xlarge': 0.4032,
    # C5 family
    'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34, 'c5.4xlarge': 0.68,
    # C6i family
    'c6i.large': 0.085, 'c6i.xlarge': 0.17, 'c6i.2xlarge': 0.34,
    # R5 family
    'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504, 'r5.4xlarge': 1.008,
    # R6i family
    'r6i.large': 0.126, 'r6i.xlarge': 0.252, 'r6i.2xlarge': 0.504,
    # Graviton (ARM)
    't4g.nano': 0.0042, 't4g.micro': 0.0084, 't4g.small': 0.0168, 't4g.medium': 0.0336,
    't4g.large': 0.0672, 't4g.xlarge': 0.1344,
    'm6g.large': 0.077, 'm6g.xlarge': 0.154, 'm6g.2xlarge': 0.308,
    'm7g.large': 0.0816, 'm7g.xlarge': 0.1632, 'm7g.2xlarge': 0.3264,
    'c6g.large': 0.068, 'c6g.xlarge': 0.136, 'c6g.2xlarge': 0.272,
    'r6g.large': 0.1008, 'r6g.xlarge': 0.2016, 'r6g.2xlarge': 0.4032,
}


class AWSConnector(CloudConnector):
    """
    AWS-specific implementation of the CloudConnector interface.

    Uses STS AssumeRole for cross-account access. Each tool method maps
    directly to one or more AWS API calls and returns raw response data.
    """

    SUPPORTED_OPERATIONS: list[str] = [
        "getComputeInstances",
        "getCostBreakdown",
        "getMonthlyTrend",
        "getDatabaseInstances",
        "getServerlessFunctions",
        "getObjectStorage",
        "getStorageVolumes",
        "getNetworkResources",
        "getBudgets",
        "getFinOpsSettings",
        "getSpotCandidates",
        "getPricingData",
        "getCostForecast",
    ]

    # ─── Auth Helpers ─────────────────────────────────────────────────────

    def _assume_role(self, account_id: str, member_email: str) -> dict:
        """Assume the cross-account role for the given member account."""
        role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
        external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

        sts = boto3.client('sts')
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SlashMyBillAgent',
            ExternalId=external_id,
        )
        return response['Credentials']

    def _make_client(self, service: str, credentials: dict, region: str = 'us-east-1'):
        """Create a boto3 client using assumed-role credentials."""
        return boto3.client(
            service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region,
        )

    def _detect_active_regions(self, credentials: dict) -> list[str]:
        """Return likely active regions (fast, no API call)."""
        return ['eu-central-1', 'us-east-1']

    def _region_to_location(self, region: str) -> str:
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

    # ─── Cost Analysis ────────────────────────────────────────────────────

    def get_cost_breakdown(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cost breakdown by service (full previous month) and daily trend (last 7 days).
        Calls AWS Cost Explorer GetCostAndUsage API directly.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            ce = self._make_client('ce', creds)

            now = datetime.now(timezone.utc)
            # End = 1st of current month (exclusive in Cost Explorer)
            end_date = now.replace(day=1).strftime('%Y-%m-%d')
            # Start = 1st of previous month
            first_of_this_month = now.replace(day=1)
            first_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
            start_date = first_of_last_month.strftime('%Y-%m-%d')
            # Daily trend: last 7 days
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

            # Daily trend (last 7 days) — includes current month days
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

            # Current month-to-date spend (from 1st of current month to today)
            mtd_services = []
            mtd_total = 0.0
            if now.day > 1:
                try:
                    mtd_resp = ce.get_cost_and_usage(
                        TimePeriod={'Start': first_of_this_month.strftime('%Y-%m-%d'), 'End': today},
                        Granularity='MONTHLY',
                        Metrics=['UnblendedCost'],
                        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
                    )
                    for period in mtd_resp.get('ResultsByTime', []):
                        for group in period.get('Groups', []):
                            svc = group['Keys'][0]
                            cost = float(group['Metrics']['UnblendedCost']['Amount'])
                            if cost > 0.01:
                                mtd_services.append({'service': svc, 'cost': round(cost, 2)})
                    mtd_services.sort(key=lambda x: x['cost'], reverse=True)
                    mtd_total = sum(s['cost'] for s in mtd_services)
                except Exception:
                    pass  # MTD is supplemental, don't fail if it errors

            total = sum(s['cost'] for s in services)

            result = {
                'totalCost30Days': round(total, 2),
                'topServices': services[:7],
                'dailyCosts': daily_costs,
                'period': f'{start_date} to {end_date} (full previous month)',
            }

            # Include MTD data if available
            if mtd_total > 0:
                result['currentMonthMTD'] = round(mtd_total, 2)
                result['currentMonthServices'] = mtd_services[:7]
                result['currentMonthPeriod'] = f"{first_of_this_month.strftime('%Y-%m-%d')} to {today} (month-to-date)"
                # Calculate daily average for forecast context
                if daily_costs:
                    recent_avg = sum(d['cost'] for d in daily_costs) / len(daily_costs)
                    result['dailyAverage7d'] = round(recent_avg, 2)

            # Usage-type breakdown for specific service questions
            # When usageTypeBreakdown=true and serviceFilter is provided,
            # fetch granular usage type data (e.g., FaceSearchImageCount, LabelDetection)
            usage_type_breakdown = params.get('usageTypeBreakdown', '')
            service_filter = params.get('serviceFilter', '')
            if usage_type_breakdown in ('true', 'True', '1', True) and service_filter:
                try:
                    time_period = {'Start': start_date, 'End': end_date}
                    # If we have MTD data requested and the service is in current month
                    if mtd_total > 0:
                        time_period = {'Start': first_of_this_month.strftime('%Y-%m-%d'), 'End': today}

                    usage_resp = ce.get_cost_and_usage(
                        TimePeriod=time_period,
                        Granularity='MONTHLY',
                        Metrics=['UnblendedCost', 'UsageQuantity'],
                        GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
                        Filter={
                            'Dimensions': {
                                'Key': 'SERVICE',
                                'Values': [service_filter],
                            }
                        },
                    )
                    usage_types = []
                    for period in usage_resp.get('ResultsByTime', []):
                        for group in period.get('Groups', []):
                            usage_type = group['Keys'][0]
                            cost = float(group['Metrics']['UnblendedCost']['Amount'])
                            quantity = float(group['Metrics'].get('UsageQuantity', {}).get('Amount', 0))
                            if cost > 0.001:
                                usage_types.append({
                                    'usageType': usage_type,
                                    'cost': round(cost, 4),
                                    'quantity': round(quantity, 2),
                                })
                    usage_types.sort(key=lambda x: x['cost'], reverse=True)
                    if usage_types:
                        # Limit to top 5 usage types to prevent response truncation
                        # (large payloads cause Bedrock EventStreamError)
                        result['usageTypeBreakdown'] = usage_types[:5]
                        result['serviceFilter'] = service_filter
                except Exception as e:
                    logger.warning(f"Usage type breakdown failed for {service_filter}: {e}")

            return result
        except Exception as e:
            return {'error': str(e)}

    def get_monthly_trend(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get monthly cost comparison by service over the specified number of months.
        Calls AWS Cost Explorer GetCostAndUsage API with MONTHLY granularity.
        """
        months = int(params.get('months', 3))
        try:
            creds = self._assume_role(account_id, member_email)
            ce = self._make_client('ce', creds)

            end_date = datetime.now(timezone.utc).replace(day=1).strftime('%Y-%m-%d')
            start_date = (
                datetime.now(timezone.utc).replace(day=1) - timedelta(days=months * 31)
            ).replace(day=1).strftime('%Y-%m-%d')

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

            return {
                'monthlyComparison': monthly_data,
                'months': sorted(monthly_data.keys()),
            }
        except Exception as e:
            return {'error': str(e)}

    # ─── Compute & Optimize ───────────────────────────────────────────────

    def get_compute_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List EC2 instances across active regions with details and estimated per-instance cost.
        Includes hourly rate and estimated monthly cost so the agent doesn't hallucinate costs.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            regions = self._detect_active_regions(creds)

            instances = []
            for region in regions:
                try:
                    ec2 = self._make_client('ec2', creds, region)
                    response = ec2.describe_instances(
                        Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}]
                    )
                    for res in response.get('Reservations', []):
                        for inst in res.get('Instances', []):
                            name = ''
                            for tag in inst.get('Tags', []):
                                if tag['Key'] == 'Name':
                                    name = tag['Value']
                            instance_type = inst['InstanceType']
                            state = inst['State']['Name']
                            hourly_rate = _EC2_HOURLY_RATES.get(instance_type)
                            monthly_cost = None
                            if hourly_rate and state == 'running':
                                monthly_cost = round(hourly_rate * 730, 2)
                            instances.append({
                                'instanceId': inst['InstanceId'],
                                'type': instance_type,
                                'state': state,
                                'name': name,
                                'region': region,
                                'az': inst.get('Placement', {}).get('AvailabilityZone', ''),
                                'launchTime': str(inst.get('LaunchTime', '')),
                                'hourlyRate_USD': hourly_rate,
                                'estimatedMonthlyCost_USD': monthly_cost,
                            })
                except Exception:
                    continue  # Skip regions with access issues

            return {
                'instances': instances,
                'count': len(instances),
                'note': 'Cost shown is per-instance on-demand rate (compute only, excludes EBS/network). Use getCostBreakdown for total account costs.',
            }
        except Exception as e:
            return {'error': str(e)}

    def get_spot_candidates(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Query AWS Spot Placement Score API for capacity availability.
        """
        vcpu_min = int(params.get('vCpuMin', 2))
        vcpu_max = int(params.get('vCpuMax', 8))
        mem_min = int(params.get('memoryMiBMin', 4096))
        mem_max = int(params.get('memoryMiBMax', 16384))
        target_capacity = int(params.get('targetCapacity', 10))
        regions_str = params.get('regions', '')

        if not account_id or not member_email:
            return {'error': 'accountId and memberEmail are required'}

        try:
            credentials = self._assume_role(account_id, member_email)
        except Exception as e:
            return {'error': f'Cannot assume role: {str(e)}'}

        region_list = (
            [r.strip() for r in regions_str.split(',') if r.strip()]
            if regions_str
            else ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
        )

        all_scores = []
        for region in region_list:
            try:
                ec2 = self._make_client('ec2', credentials, region)
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

        # Sort by score descending, deduplicate
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

    # ─── Database & Storage ───────────────────────────────────────────────

    def get_database_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List RDS instances with CPU metrics.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            rds = self._make_client('rds', creds)
            cw = self._make_client('cloudwatch', creds)

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
                        Namespace='AWS/RDS',
                        MetricName='CPUUtilization',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=86400,
                        Statistics=['Average'],
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

    def get_object_storage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List S3 buckets with lifecycle policy status and storage class info.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            s3 = self._make_client('s3', creds)

            response = s3.list_buckets()
            buckets = []
            for b in response.get('Buckets', []):
                bucket_info = {
                    'name': b['Name'],
                    'created': str(b['CreationDate']),
                    'hasLifecyclePolicy': False,
                    'lifecycleRules': 0,
                    'storageClass': 'STANDARD',
                }
                # Check lifecycle policy
                try:
                    lc_resp = s3.get_bucket_lifecycle_configuration(Bucket=b['Name'])
                    rules = lc_resp.get('Rules', [])
                    bucket_info['hasLifecyclePolicy'] = len(rules) > 0
                    bucket_info['lifecycleRules'] = len(rules)
                except s3.exceptions.ClientError as lc_err:
                    # NoSuchLifecycleConfiguration means no policy
                    if 'NoSuchLifecycleConfiguration' in str(lc_err):
                        bucket_info['hasLifecyclePolicy'] = False
                    else:
                        pass  # Access denied or other error — skip
                except Exception:
                    pass
                buckets.append(bucket_info)

            # Summary stats
            no_lifecycle = [b for b in buckets if not b['hasLifecyclePolicy']]
            return {
                'buckets': buckets,
                'count': len(buckets),
                'withoutLifecycle': len(no_lifecycle),
                'withLifecycle': len(buckets) - len(no_lifecycle),
            }
        except Exception as e:
            return {'error': str(e)}

    def get_storage_volumes(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List EBS volumes across active regions.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            regions = self._detect_active_regions(creds)

            volumes = []
            unattached_count = 0
            gp2_count = 0
            total_gb = 0

            for region in regions:
                try:
                    ec2 = self._make_client('ec2', creds, region)
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
                'gp2ToGp3SavingsUSD': round(
                    gp2_count * 0.02 * (total_gb / max(len(volumes), 1)), 2
                ),
            }
        except Exception as e:
            return {'error': str(e)}

    # ─── Network & Serverless ─────────────────────────────────────────────

    def get_network_resources(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List NAT Gateways, VPC Endpoints, and Elastic IPs.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            ec2 = self._make_client('ec2', creds)

            # NAT Gateways
            nat_resp = ec2.describe_nat_gateways(
                Filter=[{'Name': 'state', 'Values': ['available']}]
            )
            nat_gateways = [
                {
                    'id': n['NatGatewayId'],
                    'vpcId': n.get('VpcId', ''),
                    'subnetId': n.get('SubnetId', ''),
                }
                for n in nat_resp.get('NatGateways', [])
            ]

            # VPC Endpoints
            vpce_resp = ec2.describe_vpc_endpoints()
            endpoints = [
                {
                    'id': e['VpcEndpointId'],
                    'type': e['VpcEndpointType'],
                    'serviceName': e['ServiceName'],
                    'state': e['State'],
                }
                for e in vpce_resp.get('VpcEndpoints', [])
            ]

            # Elastic IPs
            eip_resp = ec2.describe_addresses()
            eips = []
            unassociated = 0
            for addr in eip_resp.get('Addresses', []):
                associated = bool(addr.get('AssociationId'))
                if not associated:
                    unassociated += 1
                eips.append({
                    'publicIp': addr.get('PublicIp', ''),
                    'associated': associated,
                    'instanceId': addr.get('InstanceId', ''),
                })

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

    def get_serverless_functions(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List Lambda functions with invocation metrics and estimated cost.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            lam = self._make_client('lambda', creds)
            cw = self._make_client('cloudwatch', creds)

            resp = lam.list_functions(MaxItems=50)
            functions = []
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=30)
            total_invocations = 0

            for fn in resp.get('Functions', []):
                fn_name = fn['FunctionName']
                invocations = 0
                errors = 0
                avg_duration_ms = 0

                try:
                    inv_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Invocations',
                        Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=2592000,
                        Statistics=['Sum'],
                    )
                    points = inv_resp.get('Datapoints', [])
                    if points:
                        invocations = int(sum(p.get('Sum', 0) for p in points))
                except Exception:
                    pass

                try:
                    err_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Errors',
                        Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=2592000,
                        Statistics=['Sum'],
                    )
                    points = err_resp.get('Datapoints', [])
                    if points:
                        errors = int(sum(p.get('Sum', 0) for p in points))
                except Exception:
                    pass

                # Get average duration for cost estimation
                try:
                    dur_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda',
                        MetricName='Duration',
                        Dimensions=[{'Name': 'FunctionName', 'Value': fn_name}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=2592000,
                        Statistics=['Average'],
                    )
                    points = dur_resp.get('Datapoints', [])
                    if points:
                        avg_duration_ms = points[0].get('Average', 0)
                except Exception:
                    pass

                # Calculate estimated monthly cost
                memory_gb = fn.get('MemorySize', 128) / 1024.0
                duration_sec = avg_duration_ms / 1000.0 if avg_duration_ms else 0.1  # default 100ms
                gb_seconds = invocations * memory_gb * duration_sec
                compute_cost = gb_seconds * 0.0000166667
                request_cost = invocations * 0.0000002  # $0.20 per 1M requests
                estimated_cost = round(compute_cost + request_cost, 4)

                total_invocations += invocations
                functions.append({
                    'name': fn_name,
                    'runtime': fn.get('Runtime', 'unknown'),
                    'memoryMB': fn.get('MemorySize', 128),
                    'architecture': fn.get('Architectures', ['x86_64'])[0],
                    'invocations30d': invocations,
                    'errors30d': errors,
                    'avgDurationMs': round(avg_duration_ms, 1),
                    'estimatedMonthlyCost': estimated_cost,
                })

            # Sort by invocations descending (most active first)
            functions.sort(key=lambda f: f['invocations30d'], reverse=True)

            total_cost = sum(f['estimatedMonthlyCost'] for f in functions)
            return {
                'functions': functions,
                'count': len(functions),
                'totalInvocations30d': total_invocations,
                'estimatedTotalCost': round(total_cost, 2),
                'note': 'Cost estimated from CloudWatch metrics. Free tier (1M requests + 400K GB-sec) not deducted.' if total_invocations > 0 else 'All functions show 0 invocations in the last 30 days. Lambda cost is $0 (functions are idle). Consider deleting unused functions.',
            }
        except Exception as e:
            return {'error': str(e)}

    # ─── FinOps Platform ──────────────────────────────────────────────────

    def get_budgets(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List AWS Budgets with spend data.
        """
        try:
            creds = self._assume_role(account_id, member_email)
            budgets_client = self._make_client('budgets', creds)

            resp = budgets_client.describe_budgets(AccountId=account_id)
            budgets = []
            for b in resp.get('Budgets', []):
                limit = float(b.get('BudgetLimit', {}).get('Amount', 0))
                actual = float(
                    b.get('CalculatedSpend', {}).get('ActualSpend', {}).get('Amount', 0)
                )
                forecast = float(
                    b.get('CalculatedSpend', {}).get('ForecastedSpend', {}).get('Amount', 0)
                )
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

    def get_finops_settings(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cached FinOps settings healthcheck results from DynamoDB.
        """
        try:
            import decimal

            dynamodb = boto3.resource('dynamodb')
            members_table = dynamodb.Table('MemberPortal-Members')
            resp = members_table.get_item(
                Key={'email': member_email},
                ProjectionExpression='healthcheckResults',
            )
            results = resp.get('Item', {}).get('healthcheckResults', {})
            account_results = results.get(account_id, {})

            if not account_results:
                return {
                    'message': (
                        'No FinOps settings scan has been run for this account. '
                        'Recommend: Go to Configure > FinOps Settings to run a scan.'
                    )
                }

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

    # ─── Knowledge ────────────────────────────────────────────────────────

    def get_pricing_data(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Query the AWS Pricing API for real-time pricing data.
        """
        service_code = params.get('serviceCode', '') or params.get('service', '')
        filters_str = params.get('filters', '')
        region = params.get('region', 'us-east-1')

        try:
            pricing = boto3.client('pricing', region_name='us-east-1')

            if not service_code:
                # Return available service codes if none specified
                response = pricing.describe_services(MaxResults=100)
                services = [s['ServiceCode'] for s in response.get('Services', [])]
                return {'availableServices': services}

            # Build filters from the comma-separated string
            price_filters = [
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': self._region_to_location(region)}
            ]
            if filters_str:
                for pair in filters_str.split(','):
                    if '=' in pair:
                        key, value = pair.strip().split('=', 1)
                        price_filters.append({
                            'Type': 'TERM_MATCH',
                            'Field': key.strip(),
                            'Value': value.strip(),
                        })

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
                        'attributes': {
                            k: v
                            for k, v in attributes.items()
                            if k in [
                                'instanceType', 'vcpu', 'memory', 'operatingSystem',
                                'storageClass', 'volumeType', 'group', 'groupDescription',
                            ]
                        },
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

    # ─── Stub Implementations (new tools, not yet fully implemented) ──────

    def get_cost_forecast(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get projected cost forecast using AWS Cost Explorer GetCostForecast API.
        Also fetches recent daily costs to provide context for the projection.
        """
        forecast_days = int(params.get('forecastDays', 30))
        try:
            creds = self._assume_role(account_id, member_email)
            ce = self._make_client('ce', creds)

            now = datetime.now(timezone.utc)
            today = now.strftime('%Y-%m-%d')

            # Get recent daily costs (last 7 days) for trend context
            start_7d = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            recent_daily = ce.get_cost_and_usage(
                TimePeriod={'Start': start_7d, 'End': today},
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
            )
            recent_costs = []
            for period in recent_daily.get('ResultsByTime', []):
                date = period['TimePeriod']['Start']
                cost = float(period['Total']['UnblendedCost']['Amount'])
                recent_costs.append({'date': date, 'cost': round(cost, 2)})

            # Calculate daily average from recent data
            total_recent = sum(d['cost'] for d in recent_costs)
            days_with_data = len(recent_costs) if recent_costs else 1
            daily_avg = round(total_recent / days_with_data, 2)

            # Get AWS Cost Explorer forecast for the rest of the month
            # GetCostForecast requires start date >= today
            forecast_end = (now + timedelta(days=forecast_days)).strftime('%Y-%m-%d')

            try:
                forecast_resp = ce.get_cost_forecast(
                    TimePeriod={'Start': today, 'End': forecast_end},
                    Metric='UNBLENDED_COST',
                    Granularity='MONTHLY',
                )
                forecast_total = float(forecast_resp.get('Total', {}).get('Amount', 0))
                forecast_mean = float(forecast_resp.get('Total', {}).get('Amount', 0))

                # Get daily forecast breakdown
                daily_forecast = []
                for item in forecast_resp.get('ForecastResultsByTime', []):
                    period_start = item['TimePeriod']['Start']
                    mean_val = float(item.get('MeanValue', 0))
                    daily_forecast.append({
                        'date': period_start,
                        'forecastedCost': round(mean_val, 2),
                    })
            except Exception as forecast_err:
                # If GetCostForecast fails (e.g., not enough history), fall back to
                # linear projection from recent daily average
                logger.warning(f"GetCostForecast failed, using linear projection: {forecast_err}")
                forecast_total = round(daily_avg * forecast_days, 2)
                daily_forecast = []

            # Calculate current-month projection
            # Days elapsed this month
            day_of_month = now.day
            # Days remaining in month
            if now.month == 12:
                days_in_month = 31
            else:
                next_month = now.replace(day=1, month=now.month + 1)
                days_in_month = (next_month - now.replace(day=1)).days

            # MTD spend (sum of recent days that fall in current month)
            current_month_str = now.strftime('%Y-%m')
            mtd_costs = [d['cost'] for d in recent_costs if d['date'].startswith(current_month_str)]
            mtd_total = sum(mtd_costs) if mtd_costs else daily_avg * day_of_month

            # Project end-of-month
            days_remaining = days_in_month - day_of_month
            projected_month_total = round(mtd_total + (daily_avg * days_remaining), 2)

            return {
                'forecastPeriod': f'{today} to {forecast_end}',
                'forecastTotalUSD': round(forecast_total, 2) if forecast_total > 0 else projected_month_total,
                'projectedMonthEndUSD': projected_month_total,
                'dailyAverage': daily_avg,
                'daysAnalyzed': days_with_data,
                'recentDailyCosts': recent_costs,
                'dailyForecast': daily_forecast[:14],  # Cap at 14 days for readability
                'currentMonthMTD': round(mtd_total, 2),
                'daysRemainingInMonth': days_remaining,
                'method': 'aws_cost_explorer_forecast' if daily_forecast else 'linear_projection',
            }
        except Exception as e:
            return {'error': str(e)}

    def get_cost_anomalies(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Detect cost anomalies.
        TODO: Implement using Cost Explorer GetAnomalies API.
        """
        return {
            'stub': True,
            'message': 'get_cost_anomalies is not yet fully implemented for AWS',
            'tool': 'getCostAnomalies',
        }

    def get_rightsizing_recommendations(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get rightsizing recommendations.
        TODO: Implement using Cost Explorer GetRightsizingRecommendation API.
        """
        return {
            'stub': True,
            'message': 'get_rightsizing_recommendations is not yet fully implemented for AWS',
            'tool': 'getRightsizingRecommendations',
        }

    def get_licensing_analysis(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Analyze software licensing costs.
        TODO: Implement using License Manager and EC2 instance metadata.
        """
        return {
            'stub': True,
            'message': 'get_licensing_analysis is not yet fully implemented for AWS',
            'tool': 'getLicensingAnalysis',
        }

    def get_commitment_coverage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get reserved instance / savings plan coverage.
        TODO: Implement using Cost Explorer GetReservationCoverage and GetSavingsPlansCoverage.
        """
        return {
            'stub': True,
            'message': 'get_commitment_coverage is not yet fully implemented for AWS',
            'tool': 'getCommitmentCoverage',
        }

    def get_tag_compliance(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get tag compliance status.
        TODO: Implement using Resource Groups Tagging API.
        """
        return {
            'stub': True,
            'message': 'get_tag_compliance is not yet fully implemented for AWS',
            'tool': 'getTagCompliance',
        }

    def get_business_metrics(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get business metrics (unit economics, cost per customer).
        TODO: Implement using custom metrics from DynamoDB or CloudWatch.
        """
        return {
            'stub': True,
            'message': 'get_business_metrics is not yet fully implemented for AWS',
            'tool': 'getBusinessMetrics',
        }

    def get_container_clusters(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List container orchestration clusters.
        TODO: Implement using EKS ListClusters and ECS ListClusters APIs.
        """
        return {
            'stub': True,
            'message': 'get_container_clusters is not yet fully implemented for AWS',
            'tool': 'getContainerClusters',
        }
