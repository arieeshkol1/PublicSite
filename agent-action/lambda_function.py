"""
SlashMyBill Agent Action Group Lambda.
Called by the Bedrock Agent to execute AWS API calls on member accounts.
"""

import json
import os
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PLATFORM_ACCOUNT_ID = os.environ.get('PLATFORM_ACCOUNT_ID', '991105135552')
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')

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
    """Get cost breakdown by service and daily trend."""
    try:
        creds = _assume_role(account_id, member_email)
        ce = _make_client('ce', creds)

        end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        start_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
        start_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')

        # Cost by service (last 30 days)
        by_service = ce.get_cost_and_usage(
            TimePeriod={'Start': start_30d, 'End': end_date},
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
            TimePeriod={'Start': start_7d, 'End': end_date},
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
            'period': f'{start_30d} to {end_date}',
        }
    except Exception as e:
        return {'error': str(e)}


def _get_ec2_instances(account_id, member_email):
    """List EC2 instances with details."""
    try:
        creds = _assume_role(account_id, member_email)
        ec2 = _make_client('ec2', creds)

        response = ec2.describe_instances()
        instances = []
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
                    'az': inst.get('Placement', {}).get('AvailabilityZone', ''),
                    'launchTime': str(inst.get('LaunchTime', '')),
                })
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
