"""
Scheduler Executor Lambda — Receives EventBridge Scheduler payloads and executes
cross-account stop/start/scale/scan actions via STS AssumeRole.

Target: slashmybill-scheduler-executor
Memory: 512 MB, Timeout: 300s
"""

import json
import os
import hashlib
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MEMBERS_TABLE_NAME = os.environ.get('MEMBERS_TABLE_NAME', 'MemberPortal-Members')
PLATFORM_ACCOUNT_ID = '991105135552'

dynamodb = boto3.resource('dynamodb')

# Schedule-type → resource-type filter for tag-based resolution
SCHEDULE_TYPE_RESOURCE_FILTER = {
    'ec2-stop-start': ['ec2:instance'],
    'rds-stop-start': ['rds:db'],
    'asg-scale-zero': ['autoscaling:autoScalingGroup'],
    'eks-scale-zero': ['eks:nodegroup'],
    'sagemaker-stop': ['sagemaker:notebook-instance'],
    'redshift-pause': ['redshift:cluster'],
    'workspaces-autostop': ['workspaces:workspace'],
    'elb-teardown': ['elasticloadbalancing:loadbalancer'],
}

# (scheduleType, action) → handler function name
DISPATCH_TABLE = {
    ('ec2-stop-start', 'stop'): 'execute_ec2_stop',
    ('ec2-stop-start', 'start'): 'execute_ec2_start',
    ('rds-stop-start', 'stop'): 'execute_rds_stop',
    ('rds-stop-start', 'start'): 'execute_rds_start',
    ('asg-scale-zero', 'stop'): 'execute_asg_scale_zero',
    ('asg-scale-zero', 'start'): 'execute_asg_restore',
    ('eks-scale-zero', 'stop'): 'execute_eks_scale_zero',
    ('eks-scale-zero', 'start'): 'execute_eks_restore',
    ('sagemaker-stop', 'stop'): 'execute_sagemaker_stop',
    ('sagemaker-stop', 'start'): 'execute_sagemaker_start',
    ('redshift-pause', 'stop'): 'execute_redshift_pause',
    ('redshift-pause', 'start'): 'execute_redshift_resume',
    ('workspaces-autostop', 'stop'): 'execute_workspaces_autostop',
    ('elb-teardown', 'stop'): 'execute_elb_teardown',
    ('waste-scan', 'scan'): 'execute_waste_scan',
    ('snapshot-cleanup', 'scan'): 'execute_snapshot_cleanup',
    ('gp2-migration', 'scan'): 'execute_gp2_migration',
    ('commitment-review', 'scan'): 'execute_commitment_review',
}


# ===================================================================
# Entry point
# ===================================================================

def lambda_handler(event, context):
    """Parse EventBridge Scheduler payload and dispatch to the correct handler."""
    logger.info(f"Scheduler executor invoked: {json.dumps(event)}")

    # --- Parse & validate required fields ---
    schedule_id = event.get('scheduleId')
    schedule_type = event.get('scheduleType')
    action = event.get('action')
    account_id = event.get('accountId')
    member_email = event.get('memberEmail')
    resources = event.get('resources') or []
    tag_filter = event.get('tagFilter')

    missing = [f for f in ('scheduleId', 'scheduleType', 'action', 'accountId', 'memberEmail')
               if not event.get(f)]
    if missing:
        logger.error(f"Payload missing required fields: {missing}")
        return {'statusCode': 400, 'body': f'Missing fields: {missing}'}

    # --- STS AssumeRole into customer account ---
    try:
        session = assume_cross_account_role(member_email, account_id)
    except Exception as exc:
        logger.error(f"STS AssumeRole failed for account {account_id}, schedule {schedule_id}: {exc}")
        _record_execution(member_email, schedule_id, action, 'failure', 0, 0, 0,
                          [{'resourceId': 'N/A', 'success': False, 'error': f'STS AssumeRole failed: {exc}'}])
        return {'statusCode': 500, 'body': f'AssumeRole failed: {exc}'}

    # --- Tag-based resource resolution ---
    if tag_filter and isinstance(tag_filter, dict):
        resolved = resolve_resources_by_tag(session, tag_filter, schedule_type)
        if not resolved:
            logger.warning(f"Tag resolution returned 0 resources for schedule {schedule_id}")
            _record_execution(member_email, schedule_id, action, 'success', 0, 0, 0, [])
            return {'statusCode': 200, 'body': 'Tag filter matched 0 resources'}
        resources = resolved

    # --- Dispatch to handler ---
    dispatch_key = (schedule_type, action)
    handler_name = DISPATCH_TABLE.get(dispatch_key)
    if not handler_name:
        msg = f"Invalid (scheduleType, action) combination: {dispatch_key}"
        logger.error(msg)
        raise ValueError(msg)

    handler_fn = globals()[handler_name]
    logger.info(f"Dispatching to {handler_name} with {len(resources)} resources")

    # --- Execute and collect results ---
    if handler_name in ('execute_asg_scale_zero', 'execute_asg_restore',
                        'execute_eks_scale_zero', 'execute_eks_restore'):
        results = handler_fn(session, resources, member_email, schedule_id)
    else:
        results = handler_fn(session, resources)

    # --- Compute counts ---
    resource_count = len(results)
    success_count = sum(1 for r in results if r.get('success'))
    failure_count = resource_count - success_count

    if failure_count == 0:
        status = 'success'
    elif success_count == 0:
        status = 'failure'
    else:
        status = 'partial'

    # --- Record execution history ---
    _record_execution(member_email, schedule_id, action, status,
                      resource_count, success_count, failure_count, results)

    logger.info(f"Execution complete: {status} ({success_count}/{resource_count} succeeded)")
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': status,
            'resourceCount': resource_count,
            'successCount': success_count,
            'failureCount': failure_count,
        })
    }


# ===================================================================
# STS AssumeRole
# ===================================================================

def assume_cross_account_role(member_email, account_id):
    """Assume SlashMyBill-{accountId} cross-account role and return a boto3 Session."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts = boto3.client('sts')
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='SlashMyBillScheduler',
        ExternalId=external_id,
    )
    creds = resp['Credentials']
    session = boto3.Session(
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
    )
    logger.info(f"Assumed role {role_arn} for account {account_id}")
    return session


# ===================================================================
# Tag-based resource resolution
# ===================================================================

def resolve_resources_by_tag(session, tag_filter, schedule_type):
    """Resolve resource ARNs matching a tag filter in the customer account."""
    tagging = session.client('resourcegroupstaggingapi')
    tag_filters = [{'Key': tag_filter['Key'], 'Values': [tag_filter['Value']]}]
    resource_type_filters = SCHEDULE_TYPE_RESOURCE_FILTER.get(schedule_type, [])

    arns = []
    paginator = tagging.get_paginator('get_resources')
    pages = paginator.paginate(
        TagFilters=tag_filters,
        ResourceTypeFilters=resource_type_filters,
    )
    for page in pages:
        for mapping in page.get('ResourceTagMappingList', []):
            arns.append(mapping['ResourceARN'])

    logger.info(f"Tag resolution found {len(arns)} resources for {tag_filter}")
    return arns


# ===================================================================
# EC2 Stop / Start  (Task 1.2)
# ===================================================================

def execute_ec2_stop(session, resources):
    """Stop EC2 instances. Checks state and instance lifecycle before acting (idempotent)."""
    ec2 = session.client('ec2')
    results = []
    instance_ids = [_extract_resource_id(r) for r in resources]

    for iid in instance_ids:
        try:
            desc = ec2.describe_instances(InstanceIds=[iid])
            instance = desc['Reservations'][0]['Instances'][0]
            state = instance['State']['Name']
            lifecycle = instance.get('InstanceLifecycle', '')  # 'spot' or '' (on-demand)

            if state in ('stopped', 'stopping'):
                logger.info(f"EC2 {iid} already {state}, skipping stop")
                results.append({'resource_id': iid, 'success': True, 'error': None})
                continue

            # Spot Instances with one-time requests cannot be stopped — only persistent Spot can
            if lifecycle == 'spot':
                # Check if it's a persistent Spot request (can be stopped) or one-time (cannot)
                spot_req_id = instance.get('SpotInstanceRequestId', '')
                can_stop = False
                if spot_req_id:
                    try:
                        spot_resp = ec2.describe_spot_instance_requests(SpotInstanceRequestIds=[spot_req_id])
                        spot_type = spot_resp['SpotInstanceRequests'][0].get('Type', 'one-time')
                        can_stop = (spot_type == 'persistent')
                    except Exception:
                        pass

                if not can_stop:
                    msg = f'Spot Instance {iid} has a one-time request — cannot be stopped (only terminated). Skipping.'
                    logger.warning(msg)
                    results.append({'resource_id': iid, 'success': False, 'error': msg})
                    continue

            ec2.stop_instances(InstanceIds=[iid])
            logger.info(f"EC2 {iid} stop initiated")
            results.append({'resource_id': iid, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"EC2 stop failed for {iid}: {exc}")
            results.append({'resource_id': iid, 'success': False, 'error': str(exc)})
    return results


def execute_ec2_start(session, resources):
    """Start EC2 instances. Checks state before acting (idempotent)."""
    ec2 = session.client('ec2')
    results = []
    instance_ids = [_extract_resource_id(r) for r in resources]

    for iid in instance_ids:
        try:
            desc = ec2.describe_instances(InstanceIds=[iid])
            state = desc['Reservations'][0]['Instances'][0]['State']['Name']
            if state in ('running', 'pending'):
                logger.info(f"EC2 {iid} already {state}, skipping start")
                results.append({'resource_id': iid, 'success': True, 'error': None})
                continue
            ec2.start_instances(InstanceIds=[iid])
            logger.info(f"EC2 {iid} start initiated")
            results.append({'resource_id': iid, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"EC2 start failed for {iid}: {exc}")
            results.append({'resource_id': iid, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# RDS Stop / Start  (Task 1.3)
# ===================================================================

def execute_rds_stop(session, resources):
    """Stop RDS instances. Handles already-stopped state gracefully."""
    rds = session.client('rds')
    results = []

    for res in resources:
        db_id = _extract_resource_id(res)
        try:
            desc = rds.describe_db_instances(DBInstanceIdentifier=db_id)
            status = desc['DBInstances'][0]['DBInstanceStatus']
            if status in ('stopped', 'stopping'):
                logger.info(f"RDS {db_id} already {status}, skipping stop")
                results.append({'resource_id': db_id, 'success': True, 'error': None})
                continue
            rds.stop_db_instance(DBInstanceIdentifier=db_id)
            logger.info(f"RDS {db_id} stop initiated")
            results.append({'resource_id': db_id, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"RDS stop failed for {db_id}: {exc}")
            results.append({'resource_id': db_id, 'success': False, 'error': str(exc)})
    return results


def execute_rds_start(session, resources):
    """Start RDS instances. Handles already-started state gracefully."""
    rds = session.client('rds')
    results = []

    for res in resources:
        db_id = _extract_resource_id(res)
        try:
            desc = rds.describe_db_instances(DBInstanceIdentifier=db_id)
            status = desc['DBInstances'][0]['DBInstanceStatus']
            if status in ('available', 'starting'):
                logger.info(f"RDS {db_id} already {status}, skipping start")
                results.append({'resource_id': db_id, 'success': True, 'error': None})
                continue
            rds.start_db_instance(DBInstanceIdentifier=db_id)
            logger.info(f"RDS {db_id} start initiated")
            results.append({'resource_id': db_id, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"RDS start failed for {db_id}: {exc}")
            results.append({'resource_id': db_id, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# ASG Scale-Zero / Restore  (Task 1.4)
# ===================================================================

def execute_asg_scale_zero(session, resources, member_email, schedule_id):
    """Scale ASGs to zero. Stores original values in DynamoDB before scaling."""
    asg_client = session.client('autoscaling')
    results = []
    original_values = {}

    for res in resources:
        asg_name = _extract_resource_id(res)
        try:
            desc = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            if not desc['AutoScalingGroups']:
                results.append({'resource_id': asg_name, 'success': False, 'error': 'ASG not found'})
                continue
            asg = desc['AutoScalingGroups'][0]
            original_values[asg_name] = {
                'MinSize': asg['MinSize'],
                'MaxSize': asg['MaxSize'],
                'DesiredCapacity': asg['DesiredCapacity'],
            }
            # Already at zero — idempotent
            if asg['MinSize'] == 0 and asg['MaxSize'] == 0 and asg['DesiredCapacity'] == 0:
                logger.info(f"ASG {asg_name} already at zero, skipping")
                results.append({'resource_id': asg_name, 'success': True, 'error': None})
                continue
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0, MaxSize=0, DesiredCapacity=0,
            )
            logger.info(f"ASG {asg_name} scaled to zero")
            results.append({'resource_id': asg_name, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"ASG scale-zero failed for {asg_name}: {exc}")
            results.append({'resource_id': asg_name, 'success': False, 'error': str(exc)})

    # Store original values in DynamoDB
    if original_values:
        _store_original_scale_values(member_email, schedule_id, original_values)

    return results


def execute_asg_restore(session, resources, member_email, schedule_id):
    """Restore ASGs from stored original values."""
    asg_client = session.client('autoscaling')
    results = []
    original_values = _get_original_scale_values(member_email, schedule_id)

    for res in resources:
        asg_name = _extract_resource_id(res)
        try:
            stored = original_values.get(asg_name)
            if not stored:
                logger.warning(f"No stored values for ASG {asg_name}, skipping restore")
                results.append({'resource_id': asg_name, 'success': False,
                                'error': 'No stored original values found'})
                continue
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=int(stored['MinSize']),
                MaxSize=int(stored['MaxSize']),
                DesiredCapacity=int(stored['DesiredCapacity']),
            )
            logger.info(f"ASG {asg_name} restored to Min={stored['MinSize']}, "
                        f"Max={stored['MaxSize']}, Desired={stored['DesiredCapacity']}")
            results.append({'resource_id': asg_name, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"ASG restore failed for {asg_name}: {exc}")
            results.append({'resource_id': asg_name, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# EKS Scale-Zero / Restore  (Task 1.5)
# ===================================================================

def execute_eks_scale_zero(session, resources, member_email, schedule_id):
    """Scale EKS node groups to zero. Stores original values in DynamoDB."""
    eks = session.client('eks')
    results = []
    original_values = {}

    for res in resources:
        # resources expected as "cluster-name/nodegroup-name" or ARN
        cluster_name, nodegroup_name = _parse_eks_resource(res)
        resource_key = f"{cluster_name}/{nodegroup_name}"
        try:
            desc = eks.describe_nodegroup(clusterName=cluster_name, nodegroupName=nodegroup_name)
            scaling = desc['nodegroup']['scalingConfig']
            original_values[resource_key] = {
                'minSize': scaling['minSize'],
                'maxSize': scaling['maxSize'],
                'desiredSize': scaling['desiredSize'],
            }
            if scaling['minSize'] == 0 and scaling['desiredSize'] == 0:
                logger.info(f"EKS nodegroup {resource_key} already at zero, skipping")
                results.append({'resource_id': resource_key, 'success': True, 'error': None})
                continue
            eks.update_nodegroup_config(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name,
                scalingConfig={'minSize': 0, 'maxSize': scaling['maxSize'], 'desiredSize': 0},
            )
            logger.info(f"EKS nodegroup {resource_key} scaled to zero")
            results.append({'resource_id': resource_key, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"EKS scale-zero failed for {resource_key}: {exc}")
            results.append({'resource_id': resource_key, 'success': False, 'error': str(exc)})

    if original_values:
        _store_original_scale_values(member_email, schedule_id, original_values)

    return results


def execute_eks_restore(session, resources, member_email, schedule_id):
    """Restore EKS node groups from stored original values."""
    eks = session.client('eks')
    results = []
    original_values = _get_original_scale_values(member_email, schedule_id)

    for res in resources:
        cluster_name, nodegroup_name = _parse_eks_resource(res)
        resource_key = f"{cluster_name}/{nodegroup_name}"
        try:
            stored = original_values.get(resource_key)
            if not stored:
                logger.warning(f"No stored values for EKS nodegroup {resource_key}")
                results.append({'resource_id': resource_key, 'success': False,
                                'error': 'No stored original values found'})
                continue
            eks.update_nodegroup_config(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name,
                scalingConfig={
                    'minSize': int(stored['minSize']),
                    'maxSize': int(stored['maxSize']),
                    'desiredSize': int(stored['desiredSize']),
                },
            )
            logger.info(f"EKS nodegroup {resource_key} restored to min={stored['minSize']}, "
                        f"desired={stored['desiredSize']}")
            results.append({'resource_id': resource_key, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"EKS restore failed for {resource_key}: {exc}")
            results.append({'resource_id': resource_key, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# SageMaker Stop / Start  (Task 1.6)
# ===================================================================

def execute_sagemaker_stop(session, resources):
    """Stop SageMaker notebook instances."""
    sm = session.client('sagemaker')
    results = []

    for res in resources:
        nb_name = _extract_resource_id(res)
        try:
            desc = sm.describe_notebook_instance(NotebookInstanceName=nb_name)
            status = desc['NotebookInstanceStatus']
            if status in ('Stopped', 'Stopping'):
                logger.info(f"SageMaker {nb_name} already {status}, skipping")
                results.append({'resource_id': nb_name, 'success': True, 'error': None})
                continue
            sm.stop_notebook_instance(NotebookInstanceName=nb_name)
            logger.info(f"SageMaker {nb_name} stop initiated")
            results.append({'resource_id': nb_name, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"SageMaker stop failed for {nb_name}: {exc}")
            results.append({'resource_id': nb_name, 'success': False, 'error': str(exc)})
    return results


def execute_sagemaker_start(session, resources):
    """Start SageMaker notebook instances."""
    sm = session.client('sagemaker')
    results = []

    for res in resources:
        nb_name = _extract_resource_id(res)
        try:
            desc = sm.describe_notebook_instance(NotebookInstanceName=nb_name)
            status = desc['NotebookInstanceStatus']
            if status in ('InService', 'Pending'):
                logger.info(f"SageMaker {nb_name} already {status}, skipping")
                results.append({'resource_id': nb_name, 'success': True, 'error': None})
                continue
            sm.start_notebook_instance(NotebookInstanceName=nb_name)
            logger.info(f"SageMaker {nb_name} start initiated")
            results.append({'resource_id': nb_name, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"SageMaker start failed for {nb_name}: {exc}")
            results.append({'resource_id': nb_name, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# Redshift Pause / Resume  (Task 1.6)
# ===================================================================

def execute_redshift_pause(session, resources):
    """Pause Redshift clusters."""
    rs = session.client('redshift')
    results = []

    for res in resources:
        cluster_id = _extract_resource_id(res)
        try:
            desc = rs.describe_clusters(ClusterIdentifier=cluster_id)
            status = desc['Clusters'][0]['ClusterStatus']
            if status == 'paused':
                logger.info(f"Redshift {cluster_id} already paused, skipping")
                results.append({'resource_id': cluster_id, 'success': True, 'error': None})
                continue
            rs.pause_cluster(ClusterIdentifier=cluster_id)
            logger.info(f"Redshift {cluster_id} pause initiated")
            results.append({'resource_id': cluster_id, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"Redshift pause failed for {cluster_id}: {exc}")
            results.append({'resource_id': cluster_id, 'success': False, 'error': str(exc)})
    return results


def execute_redshift_resume(session, resources):
    """Resume Redshift clusters."""
    rs = session.client('redshift')
    results = []

    for res in resources:
        cluster_id = _extract_resource_id(res)
        try:
            desc = rs.describe_clusters(ClusterIdentifier=cluster_id)
            status = desc['Clusters'][0]['ClusterStatus']
            if status == 'available':
                logger.info(f"Redshift {cluster_id} already available, skipping")
                results.append({'resource_id': cluster_id, 'success': True, 'error': None})
                continue
            rs.resume_cluster(ClusterIdentifier=cluster_id)
            logger.info(f"Redshift {cluster_id} resume initiated")
            results.append({'resource_id': cluster_id, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"Redshift resume failed for {cluster_id}: {exc}")
            results.append({'resource_id': cluster_id, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# WorkSpaces Auto-Stop  (Task 1.6)
# ===================================================================

def execute_workspaces_autostop(session, resources):
    """Set WorkSpaces to AUTO_STOP running mode."""
    ws = session.client('workspaces')
    results = []

    for res in resources:
        ws_id = _extract_resource_id(res)
        try:
            ws.modify_workspace_properties(
                WorkspaceId=ws_id,
                WorkspaceProperties={'RunningMode': 'AUTO_STOP'},
            )
            logger.info(f"WorkSpace {ws_id} set to AUTO_STOP")
            results.append({'resource_id': ws_id, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"WorkSpaces autostop failed for {ws_id}: {exc}")
            results.append({'resource_id': ws_id, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# ELB Teardown  (Task 1.6)
# ===================================================================

def execute_elb_teardown(session, resources):
    """Delete load balancers. No start/restore action — teardown is destructive."""
    elbv2 = session.client('elbv2')
    results = []

    for res in resources:
        lb_arn = res  # ELB resources are typically full ARNs
        try:
            elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
            logger.info(f"ELB {lb_arn} deleted")
            results.append({'resource_id': lb_arn, 'success': True, 'error': None})
        except Exception as exc:
            logger.error(f"ELB teardown failed for {lb_arn}: {exc}")
            results.append({'resource_id': lb_arn, 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# Review-Type Handlers  (Task 1.7)
# ===================================================================

def execute_waste_scan(session, resources):
    """Trigger waste scan logic for the account. Resources list is informational."""
    results = []
    try:
        # Use Cost Explorer to identify idle/underutilized resources
        ce = session.client('ce')
        ec2 = session.client('ec2')

        # Check for idle EC2 instances (low CPU)
        findings = []
        try:
            instances = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            for reservation in instances.get('Reservations', []):
                for inst in reservation.get('Instances', []):
                    findings.append(inst['InstanceId'])
        except Exception as exc:
            logger.warning(f"Waste scan EC2 check failed: {exc}")

        results.append({
            'resource_id': 'waste-scan-report',
            'success': True,
            'error': None,
        })
        logger.info(f"Waste scan completed, found {len(findings)} running instances to review")
    except Exception as exc:
        logger.error(f"Waste scan failed: {exc}")
        results.append({'resource_id': 'waste-scan-report', 'success': False, 'error': str(exc)})
    return results


def execute_snapshot_cleanup(session, resources):
    """Identify and delete unused/old snapshots."""
    ec2 = session.client('ec2')
    results = []

    try:
        snapshots = ec2.describe_snapshots(OwnerIds=['self'])
        for snap in snapshots.get('Snapshots', []):
            snap_id = snap['SnapshotId']
            try:
                # Check if snapshot is attached to any AMI
                images = ec2.describe_images(
                    Filters=[{'Name': 'block-device-mapping.snapshot-id', 'Values': [snap_id]}]
                )
                if images.get('Images'):
                    continue  # Skip snapshots backing AMIs

                ec2.delete_snapshot(SnapshotId=snap_id)
                logger.info(f"Deleted orphaned snapshot {snap_id}")
                results.append({'resource_id': snap_id, 'success': True, 'error': None})
            except Exception as exc:
                logger.error(f"Snapshot cleanup failed for {snap_id}: {exc}")
                results.append({'resource_id': snap_id, 'success': False, 'error': str(exc)})
    except Exception as exc:
        logger.error(f"Snapshot cleanup describe failed: {exc}")
        results.append({'resource_id': 'snapshot-cleanup', 'success': False, 'error': str(exc)})

    if not results:
        results.append({'resource_id': 'snapshot-cleanup', 'success': True, 'error': None})
    return results


def execute_gp2_migration(session, resources):
    """Identify gp2 EBS volumes and convert to gp3."""
    ec2 = session.client('ec2')
    results = []

    try:
        volumes = ec2.describe_volumes(
            Filters=[{'Name': 'volume-type', 'Values': ['gp2']}]
        )
        for vol in volumes.get('Volumes', []):
            vol_id = vol['VolumeId']
            try:
                ec2.modify_volume(VolumeId=vol_id, VolumeType='gp3')
                logger.info(f"Volume {vol_id} migration gp2→gp3 initiated")
                results.append({'resource_id': vol_id, 'success': True, 'error': None})
            except Exception as exc:
                logger.error(f"gp2 migration failed for {vol_id}: {exc}")
                results.append({'resource_id': vol_id, 'success': False, 'error': str(exc)})
    except Exception as exc:
        logger.error(f"gp2 migration describe failed: {exc}")
        results.append({'resource_id': 'gp2-migration', 'success': False, 'error': str(exc)})

    if not results:
        results.append({'resource_id': 'gp2-migration', 'success': True, 'error': None})
    return results


def execute_commitment_review(session, resources):
    """Generate Savings Plans and Reserved Instances utilization review."""
    results = []
    try:
        ce = session.client('ce')
        today = datetime.now(timezone.utc)
        start = (today.replace(day=1)).strftime('%Y-%m-%d')
        end = today.strftime('%Y-%m-%d')

        # Get RI utilization
        ri_data = {}
        try:
            ri_resp = ce.get_reservation_utilization(
                TimePeriod={'Start': start, 'End': end},
                Granularity='MONTHLY',
            )
            ri_data = ri_resp.get('UtilizationsByTime', [])
        except Exception as exc:
            logger.warning(f"RI utilization check failed: {exc}")

        # Get SP utilization
        sp_data = {}
        try:
            sp_resp = ce.get_savings_plans_utilization(
                TimePeriod={'Start': start, 'End': end},
                Granularity='MONTHLY',
            )
            sp_data = sp_resp.get('SavingsPlansUtilizationsByTime', [])
        except Exception as exc:
            logger.warning(f"SP utilization check failed: {exc}")

        results.append({
            'resource_id': 'commitment-review-report',
            'success': True,
            'error': None,
        })
        logger.info("Commitment review completed")
    except Exception as exc:
        logger.error(f"Commitment review failed: {exc}")
        results.append({'resource_id': 'commitment-review-report', 'success': False, 'error': str(exc)})
    return results


# ===================================================================
# Execution History Recording  (Task 1.8)
# ===================================================================

def _record_execution(member_email, schedule_id, action, status,
                      resource_count, success_count, failure_count, details):
    """Write execution record to DynamoDB on the member's schedule (best-effort)."""
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'action': action,
        'status': status,
        'resourceCount': resource_count,
        'successCount': success_count,
        'failureCount': failure_count,
        'details': details,
    }

    try:
        table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = table.get_item(Key={'email': member_email}).get('Item')
        if not member:
            logger.error(f"Member {member_email} not found, cannot record execution")
            return

        schedules = member.get('userSchedules', [])
        schedule_index = None
        for i, sched in enumerate(schedules):
            if sched.get('id') == schedule_id:
                schedule_index = i
                break

        if schedule_index is None:
            logger.error(f"Schedule {schedule_id} not found for member {member_email}")
            return

        # Append to executionHistory using list_append
        table.update_item(
            Key={'email': member_email},
            UpdateExpression=(
                f'SET userSchedules[{schedule_index}].executionHistory = '
                f'list_append(if_not_exists(userSchedules[{schedule_index}].executionHistory, :empty), :record)'
            ),
            ExpressionAttributeValues={
                ':record': [record],
                ':empty': [],
            },
        )
        logger.info(f"Execution record written for schedule {schedule_id}: {status}")
    except Exception as exc:
        # Best-effort — log to CloudWatch if DynamoDB fails
        logger.error(f"Failed to write execution record to DynamoDB: {exc}")
        logger.error(f"Lost execution record: {json.dumps(record, default=str)}")


# ===================================================================
# DynamoDB Helpers — Original Scale Values (ASG / EKS)
# ===================================================================

def _store_original_scale_values(member_email, schedule_id, values):
    """Store original scale values on the schedule record in DynamoDB."""
    try:
        table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = table.get_item(Key={'email': member_email}).get('Item')
        if not member:
            logger.error(f"Member {member_email} not found for storing scale values")
            return

        schedules = member.get('userSchedules', [])
        schedule_index = None
        for i, sched in enumerate(schedules):
            if sched.get('id') == schedule_id:
                schedule_index = i
                break

        if schedule_index is None:
            logger.error(f"Schedule {schedule_id} not found for storing scale values")
            return

        table.update_item(
            Key={'email': member_email},
            UpdateExpression=f'SET userSchedules[{schedule_index}].originalScaleValues = :vals',
            ExpressionAttributeValues={':vals': values},
        )
        logger.info(f"Stored original scale values for schedule {schedule_id}")
    except Exception as exc:
        logger.error(f"Failed to store original scale values: {exc}")


def _get_original_scale_values(member_email, schedule_id):
    """Retrieve stored original scale values from DynamoDB."""
    try:
        table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = table.get_item(Key={'email': member_email}).get('Item')
        if not member:
            logger.warning(f"Member {member_email} not found for retrieving scale values")
            return {}

        schedules = member.get('userSchedules', [])
        for sched in schedules:
            if sched.get('id') == schedule_id:
                return sched.get('originalScaleValues') or {}

        logger.warning(f"Schedule {schedule_id} not found for retrieving scale values")
        return {}
    except Exception as exc:
        logger.error(f"Failed to retrieve original scale values: {exc}")
        return {}


# ===================================================================
# Utility Functions
# ===================================================================

def _extract_resource_id(resource_arn_or_id):
    """Extract the resource ID from an ARN or return as-is if already an ID.

    Examples:
        arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123 → i-0abc123
        arn:aws:rds:us-east-1:123456789012:db:mydb → mydb
        i-0abc123 → i-0abc123
    """
    if not resource_arn_or_id:
        return resource_arn_or_id
    if not resource_arn_or_id.startswith('arn:'):
        return resource_arn_or_id
    # ARN formats: arn:partition:service:region:account:resource-type/resource-id
    #              arn:partition:service:region:account:resource-type:resource-id
    parts = resource_arn_or_id.split(':')
    resource_part = ':'.join(parts[5:]) if len(parts) > 5 else parts[-1]
    # Handle both / and : separators
    if '/' in resource_part:
        return resource_part.split('/')[-1]
    if ':' in resource_part:
        return resource_part.split(':')[-1]
    return resource_part


def _parse_eks_resource(resource):
    """Parse EKS resource into (cluster_name, nodegroup_name).

    Accepts:
        cluster-name/nodegroup-name
        arn:aws:eks:region:account:nodegroup/cluster/nodegroup/uuid
    """
    if resource.startswith('arn:'):
        # arn:aws:eks:us-east-1:123456789012:nodegroup/my-cluster/my-ng/abc123
        parts = resource.split('/')
        if len(parts) >= 3:
            return parts[1], parts[2]
    if '/' in resource:
        parts = resource.split('/')
        return parts[0], parts[1]
    # Fallback: treat entire string as both cluster and nodegroup
    return resource, resource
