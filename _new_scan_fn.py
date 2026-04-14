
def handle_actions_scan(event):
    """Tips-driven scan engine v2.
    
    Loads tips from DynamoDB, gates checks by services actually present
    in the account (from CE cost data), evaluates each tip via a registry
    of check functions, and returns findings sorted by savings impact.
    """
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_ids = body.get('accountIds') or []
    if not account_ids:
        accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
        try:
            result = accounts_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
            )
            account_ids = [a['accountId'] for a in result.get('Items', []) if a.get('connectionStatus') == 'connected']
        except ClientError:
            return create_error_response(500, 'ServerError', 'Failed to load accounts')

    if not account_ids:
        return create_response(200, {'cards': [], 'totalSavings': 0, 'findings': []})

    ownership = _verify_account_ownership(member_email, account_ids)
    if isinstance(ownership, dict):
        return ownership

    # ── Step 1: Load tips from DynamoDB (ground truth) ────────────────────
    tips = _load_tips_from_db()

    all_cards = []
    all_findings = []
    total_savings = 0.0

    for account_id in account_ids[:5]:
        try:
            creds = _assume_role_for_account(member_email, account_id)
        except Exception as e:
            logger.warning(f"Cannot assume role for {account_id}: {e}")
            continue

        acct_label = f'Account {account_id[-4:]}'

        # ── Step 2: Collect service data ──────────────────────────────────
        svc_data = _collect_service_data(account_id, creds)

        # ── Step 3: Determine active services from CE cost data ───────────
        active_services = _get_active_services(svc_data.get('cost_by_service', []))

        # ── Step 4: Evaluate each tip against collected data ──────────────
        for tip in tips:
            svc_key = tip.get('serviceKey', tip.get('service', 'General'))
            # Gate: only evaluate if service is present (General always runs)
            if svc_key != 'General' and svc_key not in active_services:
                continue

            tip_id = tip.get('tipId', '')
            check_fn = _SCAN_REGISTRY.get(tip_id)

            if check_fn and tip.get('checkImplemented', False):
                try:
                    finding = check_fn(tip, svc_data, account_id, acct_label, creds)
                    if finding:
                        finding['tipId'] = tip_id
                        finding['level'] = tip.get('level', 2)
                        finding['actionType'] = tip.get('actionType', 'advisory')
                        finding['actionLabel'] = tip.get('actionLabel', 'View')
                        finding['tipTitle'] = tip.get('title', '')
                        finding['service'] = tip.get('service', '')
                        all_findings.append(finding)
                        if finding.get('cardData'):
                            card = finding['cardData']
                            card['accountId'] = account_id
                            card['accountLabel'] = acct_label
                            all_cards.append(card)
                            total_savings += card.get('monthlySavings') or 0
                except Exception as e:
                    logger.warning(f"Check {tip_id} failed for {account_id}: {e}")
            elif not tip.get('checkImplemented', False):
                # Placeholder finding for tips not yet implemented
                all_findings.append({
                    'tipId': tip_id,
                    'level': tip.get('level', 2),
                    'actionType': 'pending',
                    'actionLabel': 'Coming Soon',
                    'tipTitle': tip.get('title', ''),
                    'service': tip.get('service', ''),
                    'status': 'pending',
                    'accountId': account_id,
                    'note': 'Check not yet implemented — will be added in a future update',
                })

    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)

    return create_response(200, {
        'cards': all_cards,
        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': datetime.now(timezone.utc).isoformat(),
    })


def _load_tips_from_db():
    """Load all tips from DynamoDB tips table."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        result = tips_table.scan()
        return _decimal_to_native(result.get('Items', []))
    except Exception as e:
        logger.warning(f"Failed to load tips from DynamoDB: {e}")
        return []


def _get_active_services(cost_by_service):
    """Return set of service names that have actual spend (> $0.01)."""
    active = set()
    for svc in cost_by_service:
        cost = svc.get('cost_usd', 0)
        if cost > 0.01:
            name = svc.get('service', '')
            active.add(name)
            # Also add normalized aliases
            if 'EC2' in name and 'Other' not in name:
                active.add('Amazon EC2')
            if 'EC2 - Other' in name:
                active.add('EC2 - Other')
            if 'S3' in name or 'Simple Storage' in name:
                active.add('Amazon Simple Storage Service')
            if 'RDS' in name or 'Relational Database' in name:
                active.add('Amazon Relational Database Service')
            if 'Lambda' in name:
                active.add('AWS Lambda')
            if 'VPC' in name or 'Virtual Private Cloud' in name:
                active.add('Amazon Virtual Private Cloud')
            if 'Load Balancing' in name or 'ELB' in name:
                active.add('Amazon Elastic Load Balancing')
            if 'KMS' in name or 'Key Management' in name:
                active.add('AWS Key Management Service')
            if 'Container Service' in name or 'ECS' in name:
                active.add('Amazon Elastic Container Service')
            if 'Kubernetes' in name or 'EKS' in name:
                active.add('Amazon Elastic Kubernetes Service')
            if 'ElastiCache' in name:
                active.add('Amazon ElastiCache')
            if 'DynamoDB' in name:
                active.add('Amazon DynamoDB')
            if 'CloudFront' in name:
                active.add('Amazon CloudFront')
            if 'Elastic File' in name or 'EFS' in name:
                active.add('Amazon Elastic File System')
    return active


def _collect_service_data(account_id, creds):
    """Collect all service data needed for tip evaluation. Fast, parallel-friendly."""
    data = {}
    now_dt = datetime.now(timezone.utc)

    try:
        ec2 = _make_client_from_creds('ec2', creds)
        cw = _make_client_from_creds('cloudwatch', creds)

        # CE: cost by service (last 30 days) — determines active services
        try:
            ce = _make_client_from_creds('ce', creds)
            end_date = now_dt.strftime('%Y-%m-%d')
            start_date = (now_dt - timedelta(days=30)).strftime('%Y-%m-%d')
            ce_resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY', Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
            data['cost_by_service'] = [
                {'service': g['Keys'][0], 'cost_usd': float(g['Metrics']['UnblendedCost']['Amount'])}
                for period in ce_resp.get('ResultsByTime', [])
                for g in period.get('Groups', [])
                if float(g['Metrics']['UnblendedCost']['Amount']) > 0.01
            ]
        except Exception as e:
            logger.warning(f"CE cost_by_service failed for {account_id}: {e}")
            data['cost_by_service'] = []

        # EIPs
        try:
            eips = ec2.describe_addresses()
            data['elastic_ips'] = eips.get('Addresses', [])
        except Exception:
            data['elastic_ips'] = []

        # EBS volumes (unattached)
        try:
            vols = ec2.describe_volumes(Filters=[{'Name': 'status', 'Values': ['available']}])
            data['unattached_volumes'] = vols.get('Volumes', [])
        except Exception:
            data['unattached_volumes'] = []

        # EBS snapshots (own account, capped at 200)
        try:
            snaps = ec2.describe_snapshots(OwnerIds=['self'], MaxResults=200)
            data['snapshots'] = snaps.get('Snapshots', [])
        except Exception:
            data['snapshots'] = []

        # EC2 running instances
        try:
            inst_resp = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            data['ec2_instances'] = [
                inst
                for r in inst_resp.get('Reservations', [])
                for inst in r.get('Instances', [])
            ]
        except Exception:
            data['ec2_instances'] = []

        # S3 buckets + lifecycle check
        try:
            s3 = _make_client_from_creds('s3', creds)
            buckets = s3.list_buckets().get('Buckets', [])
            bucket_data = []
            for b in buckets[:20]:
                bname = b['Name']
                has_lc = False
                try:
                    lc = s3.get_bucket_lifecycle_configuration(Bucket=bname)
                    has_lc = bool(lc.get('Rules', []))
                except ClientError as ce_err:
                    if ce_err.response['Error']['Code'] != 'NoSuchLifecycleConfiguration':
                        pass
                except Exception:
                    pass
                # Quick activity check
                last_modified_days = None
                try:
                    sample = s3.list_objects_v2(Bucket=bname, MaxKeys=5)
                    contents = sample.get('Contents', [])
                    if contents:
                        latest = max(contents, key=lambda o: o['LastModified'])
                        last_modified_days = (now_dt - latest['LastModified'].replace(tzinfo=timezone.utc)).days
                except Exception:
                    pass
                bucket_data.append({
                    'name': bname,
                    'created': str(b.get('CreationDate', '')),
                    'hasLifecycle': has_lc,
                    'lastModifiedDays': last_modified_days,
                })
            data['s3_buckets'] = bucket_data
        except Exception:
            data['s3_buckets'] = []

        # RDS instances
        try:
            rds = _make_client_from_creds('rds', creds)
            data['rds_instances'] = [
                d for d in rds.describe_db_instances().get('DBInstances', [])
                if d.get('DBInstanceStatus') == 'available'
            ]
        except Exception:
            data['rds_instances'] = []

        # Lambda functions
        try:
            lam = _make_client_from_creds('lambda', creds)
            data['lambda_functions'] = lam.list_functions().get('Functions', [])
        except Exception:
            data['lambda_functions'] = []

        # Load balancers
        try:
            elbv2 = _make_client_from_creds('elbv2', creds)
            data['load_balancers'] = elbv2.describe_load_balancers().get('LoadBalancers', [])
        except Exception:
            data['load_balancers'] = []

        # KMS customer-managed keys
        try:
            kms = _make_client_from_creds('kms', creds)
            keys = kms.list_keys().get('Keys', [])
            aliases = kms.list_aliases().get('Aliases', [])
            alias_map = {a.get('TargetKeyId'): a.get('AliasName', '') for a in aliases}
            cmks = [k for k in keys if not alias_map.get(k['KeyId'], '').startswith('alias/aws/')]
            data['kms_customer_keys'] = cmks
        except Exception:
            data['kms_customer_keys'] = []

        # Budgets
        try:
            budgets_client = _make_client_from_creds('budgets', creds)
            blist = budgets_client.describe_budgets(AccountId=account_id).get('Budgets', [])
            data['budgets'] = blist
        except Exception:
            data['budgets'] = []

        # Batch CloudWatch: EC2 CPU (14d avg) for idle detection
        if data.get('ec2_instances'):
            try:
                queries = []
                for i, inst in enumerate(data['ec2_instances'][:15]):
                    queries.append({
                        'Id': f'cpu{i}',
                        'MetricStat': {
                            'Metric': {'Namespace': 'AWS/EC2', 'MetricName': 'CPUUtilization',
                                       'Dimensions': [{'Name': 'InstanceId', 'Value': inst['InstanceId']}]},
                            'Period': 1209600, 'Stat': 'Average',
                        }, 'ReturnData': True,
                    })
                cw_resp = cw.get_metric_data(
                    MetricDataQueries=queries,
                    StartTime=now_dt - timedelta(days=14), EndTime=now_dt,
                )
                data['ec2_cpu_14d'] = {
                    data['ec2_instances'][int(r['Id'].replace('cpu', ''))]['InstanceId']: r['Values'][0]
                    for r in cw_resp.get('MetricDataResults', [])
                    if r.get('Values')
                }
            except Exception:
                data['ec2_cpu_14d'] = {}

        # Batch CloudWatch: RDS CPU + connections (14d)
        if data.get('rds_instances'):
            try:
                queries = []
                for i, db in enumerate(data['rds_instances'][:8]):
                    db_id = db['DBInstanceIdentifier']
                    queries.append({'Id': f'cpu{i}', 'MetricStat': {'Metric': {'Namespace': 'AWS/RDS', 'MetricName': 'CPUUtilization', 'Dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': db_id}]}, 'Period': 1209600, 'Stat': 'Average'}, 'ReturnData': True})
                    queries.append({'Id': f'conn{i}', 'MetricStat': {'Metric': {'Namespace': 'AWS/RDS', 'MetricName': 'DatabaseConnections', 'Dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': db_id}]}, 'Period': 1209600, 'Stat': 'Maximum'}, 'ReturnData': True})
                cw_resp = cw.get_metric_data(MetricDataQueries=queries, StartTime=now_dt - timedelta(days=14), EndTime=now_dt)
                cpu_map, conn_map = {}, {}
                for r in cw_resp.get('MetricDataResults', []):
                    idx = int(r['Id'][3:])
                    db_id = data['rds_instances'][idx]['DBInstanceIdentifier']
                    if r['Id'].startswith('cpu') and r.get('Values'):
                        cpu_map[db_id] = r['Values'][0]
                    elif r['Id'].startswith('conn') and r.get('Values'):
                        conn_map[db_id] = r['Values'][0]
                data['rds_cpu_14d'] = cpu_map
                data['rds_conn_14d'] = conn_map
            except Exception:
                data['rds_cpu_14d'] = {}
                data['rds_conn_14d'] = {}

    except Exception as e:
        logger.warning(f"Service data collection error for {account_id}: {e}")

    return data


# ============================================================
# Scan Check Registry — maps tip.id → check function
# Each function returns a finding dict or None (no issue found)
# finding dict: {status, savingsUsd, cardData (optional), evidence}
# ============================================================

def _check_ebs_unattached(tip, data, account_id, acct_label, creds):
    vols = data.get('unattached_volumes', [])
    if not vols:
        return None
    total_gb = sum(v.get('Size', 0) for v in vols)
    savings = total_gb * 0.10
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(vols)} unattached volumes, {total_gb} GB',
        'cardData': {
            'cardId': f'ebs-{account_id}', 'type': 'ebs-volume',
            'title': 'Unattached EBS Volumes', 'icon': '💾',
            'count': len(vols), 'risk': 'low',
            'description': f'{len(vols)} volume(s) totalling {total_gb} GB not attached to any instance',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': v['VolumeId'], 'size': v.get('Size', 0), 'type': v.get('VolumeType', ''), 'az': v.get('AvailabilityZone', '')} for v in vols],
        }
    }


def _check_ebs_snapshots(tip, data, account_id, acct_label, creds):
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    stale = []
    total_gb = 0
    for snap in data.get('snapshots', []):
        st = snap.get('StartTime')
        if st and st.replace(tzinfo=timezone.utc) < cutoff:
            age = (datetime.now(timezone.utc) - st.replace(tzinfo=timezone.utc)).days
            gb = snap.get('VolumeSize', 0)
            total_gb += gb
            stale.append({'id': snap['SnapshotId'], 'size': gb, 'ageDays': age, 'description': snap.get('Description', '')[:60]})
    if not stale:
        return None
    savings = total_gb * 0.05
    stale.sort(key=lambda s: s['ageDays'], reverse=True)
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(stale)} snapshots >180d, {total_gb} GB',
        'cardData': {
            'cardId': f'snap-{account_id}', 'type': 'ebs-snapshot',
            'title': 'Stale EBS Snapshots', 'icon': '📸',
            'count': len(stale), 'risk': 'low',
            'description': f'{len(stale)} snapshot(s) older than 180 days — {total_gb} GB total',
            'monthlySavings': round(savings, 2),
            'resources': stale[:20],
        }
    }


def _check_eip_unattached(tip, data, account_id, acct_label, creds):
    unattached = [a for a in data.get('elastic_ips', []) if not a.get('AssociationId')]
    if not unattached:
        return None
    savings = len(unattached) * 3.65
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(unattached)} unassociated EIPs',
        'cardData': {
            'cardId': f'eip-{account_id}', 'type': 'elastic-ip',
            'title': 'Unassociated Elastic IPs', 'icon': '🌐',
            'count': len(unattached), 'risk': 'low',
            'description': f'{len(unattached)} Elastic IP(s) not attached to any instance',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': a['AllocationId'], 'ip': a.get('PublicIp', '')} for a in unattached],
        }
    }


def _check_s3_lifecycle(tip, data, account_id, acct_label, creds):
    now_dt = datetime.now(timezone.utc)
    flagged = []
    for b in data.get('s3_buckets', []):
        reasons = []
        if not b.get('hasLifecycle'):
            reasons.append('no_lifecycle')
        lmd = b.get('lastModifiedDays')
        if lmd is not None and lmd >= 90:
            reasons.append(f'inactive_{lmd}d')
        elif lmd is None:
            reasons.append('empty')
        if reasons:
            flagged.append({**b, 'reasons': reasons})
    if not flagged:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(flagged)} S3 buckets flagged',
        'cardData': {
            'cardId': f's3-{account_id}', 'type': 's3-lifecycle',
            'title': 'S3 Buckets Needing Attention', 'icon': '🪣',
            'count': len(flagged), 'risk': 'low',
            'description': f'{len(flagged)} bucket(s) flagged — no lifecycle policy or inactive 90+ days',
            'monthlySavings': None,
            'resources': [{'name': b['name'], 'created': b['created'], 'sizeGb': 0, 'objectCount': 0, 'estimatedMonthlyCost': 0, 'lastModifiedDays': b.get('lastModifiedDays'), 'reasons': b['reasons'], 'reasonLabel': ' · '.join(b['reasons'])} for b in flagged[:15]],
        }
    }


def _check_elb_idle(tip, data, account_id, acct_label, creds):
    idle = []
    try:
        elbv2 = _make_client_from_creds('elbv2', creds)
        for lb in data.get('load_balancers', [])[:10]:
            try:
                tgs = elbv2.describe_target_groups(LoadBalancerArn=lb['LoadBalancerArn']).get('TargetGroups', [])
                if not tgs:
                    continue
                healthy = sum(
                    1 for tg in tgs[:3]
                    for t in elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn']).get('TargetHealthDescriptions', [])
                    if t.get('TargetHealth', {}).get('State') == 'healthy'
                )
                if healthy == 0:
                    idle.append({'arn': lb['LoadBalancerArn'], 'name': lb['LoadBalancerName'], 'type': lb.get('Type', '')})
            except Exception:
                pass
    except Exception:
        pass
    if not idle:
        return None
    savings = len(idle) * 16.43
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} idle load balancers',
        'cardData': {
            'cardId': f'lb-{account_id}', 'type': 'load-balancer',
            'title': 'Idle Load Balancers', 'icon': '⚖️',
            'count': len(idle), 'risk': 'medium',
            'description': f'{len(idle)} load balancer(s) with 0 healthy targets',
            'monthlySavings': round(savings, 2),
            'resources': idle,
        }
    }


def _check_ec2_idle(tip, data, account_id, acct_label, creds):
    cpu_map = data.get('ec2_cpu_14d', {})
    idle = []
    for inst in data.get('ec2_instances', []):
        iid = inst['InstanceId']
        avg_cpu = cpu_map.get(iid)
        if avg_cpu is not None and avg_cpu < 5.0:
            tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
            idle.append({'id': iid, 'name': tags.get('Name', iid), 'type': inst.get('InstanceType', ''), 'avgCpu': round(avg_cpu, 2), 'inAsg': 'aws:autoscaling:groupName' in tags, 'asgName': tags.get('aws:autoscaling:groupName', '')})
    if not idle:
        return None
    savings = len(idle) * 0.05 * 730
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} EC2 instances with avg CPU < 5% over 14 days',
        'cardData': {
            'cardId': f'ec2-idle-{account_id}', 'type': 'ec2-idle',
            'title': 'Idle EC2 Instances', 'icon': '🖥️',
            'count': len(idle), 'risk': 'high',
            'description': f'{len(idle)} running instance(s) with avg CPU < 5% over 14 days',
            'monthlySavings': round(savings, 2),
            'resources': idle,
            'note': 'Instances in Auto Scaling Groups will be detached before stopping.',
        }
    }


def _check_rds_idle(tip, data, account_id, acct_label, creds):
    cpu_map = data.get('rds_cpu_14d', {})
    conn_map = data.get('rds_conn_14d', {})
    idle = []
    for db in data.get('rds_instances', []):
        db_id = db['DBInstanceIdentifier']
        avg_cpu = cpu_map.get(db_id)
        max_conn = conn_map.get(db_id, 0)
        if avg_cpu is not None and avg_cpu < 5.0 and max_conn < 2:
            idle.append({'id': db_id, 'class': db.get('DBInstanceClass', ''), 'engine': db.get('Engine', ''), 'avgCpu': round(avg_cpu, 2), 'maxConnections': int(max_conn)})
    if not idle:
        return None
    savings = len(idle) * 50
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} RDS instances with avg CPU < 5% and < 2 connections',
        'cardData': {
            'cardId': f'rds-idle-{account_id}', 'type': 'rds-idle',
            'title': 'Idle RDS Instances', 'icon': '🗄️',
            'count': len(idle), 'risk': 'high',
            'description': f'{len(idle)} RDS instance(s) with avg CPU < 5% and < 2 connections over 14 days',
            'monthlySavings': round(savings, 2),
            'resources': idle,
            'note': 'A final snapshot will be taken automatically before deletion.',
        }
    }


def _check_kms_unused(tip, data, account_id, acct_label, creds):
    cmks = data.get('kms_customer_keys', [])
    if not cmks:
        return None
    savings = len(cmks) * 1.0
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(cmks)} customer-managed KMS keys at $1/month each',
        'cardData': {
            'cardId': f'kms-{account_id}', 'type': 'advisory',
            'title': 'Customer-Managed KMS Keys', 'icon': '🔑',
            'count': len(cmks), 'risk': 'low',
            'description': f'{len(cmks)} customer-managed KMS key(s) at $1/month each — audit for unused keys',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': k['KeyId']} for k in cmks[:10]],
        }
    }


def _check_budgets(tip, data, account_id, acct_label, creds):
    if data.get('budgets'):
        return None  # budgets exist, no issue
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': 'No AWS Budgets configured',
        'cardData': {
            'cardId': f'budgets-{account_id}', 'type': 'advisory',
            'title': 'No AWS Budgets Configured', 'icon': '💰',
            'count': 0, 'risk': 'medium',
            'description': 'No budgets found — set up cost alerts to catch unexpected spend early',
            'monthlySavings': None,
            'resources': [],
        }
    }


def _check_spot_candidates(tip, data, account_id, acct_label, creds):
    """Identify EC2 instances that could use Spot (non-prod, low CPU, not already Spot)."""
    candidates = []
    cpu_map = data.get('ec2_cpu_14d', {})
    for inst in data.get('ec2_instances', []):
        if inst.get('InstanceLifecycle') == 'spot':
            continue  # already Spot
        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
        env = tags.get('Environment', tags.get('Env', '')).lower()
        is_nonprod = any(e in env for e in ['dev', 'test', 'staging', 'qa', 'sandbox'])
        avg_cpu = cpu_map.get(inst['InstanceId'])
        if is_nonprod or (avg_cpu is not None and avg_cpu < 30.0):
            candidates.append({'id': inst['InstanceId'], 'name': tags.get('Name', inst['InstanceId']), 'type': inst.get('InstanceType', ''), 'avgCpu': round(avg_cpu, 2) if avg_cpu is not None else None, 'env': env or 'unknown'})
    if not candidates:
        return None
    savings = len(candidates) * 0.05 * 730 * 0.7  # ~70% Spot discount
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(candidates)} EC2 instances are Spot candidates',
        'cardData': {
            'cardId': f'spot-{account_id}', 'type': 'advisory',
            'title': 'Spot Instance Candidates', 'icon': '⚡',
            'count': len(candidates), 'risk': 'medium',
            'description': f'{len(candidates)} instance(s) could use Spot pricing — save up to 70%',
            'monthlySavings': round(savings, 2),
            'resources': candidates[:10],
            'actionUrl': 'https://console.aws.amazon.com/ec2/v2/home#SpotInstances',
        }
    }


def _check_ri_marketplace(tip, data, account_id, acct_label, creds):
    """Check for underutilized Reserved Instances via CE."""
    try:
        ce = _make_client_from_creds('ce', creds)
        now_dt = datetime.now(timezone.utc)
        ri_resp = ce.get_reservation_utilization(
            TimePeriod={'Start': (now_dt - timedelta(days=30)).strftime('%Y-%m-%d'), 'End': now_dt.strftime('%Y-%m-%d')},
        )
        total = ri_resp.get('Total', {})
        util_pct = float(total.get('UtilizationPercentage', '100') or '100')
        if util_pct >= 70:
            return None
        unused_cost = float(total.get('UnusedAmortizedUpfrontCostForRI', '0') or '0') + float(total.get('UnusedRecurringFeeForRI', '0') or '0')
        if unused_cost < 5:
            return None
        return {
            'status': 'found', 'savingsUsd': round(unused_cost, 2),
            'evidence': f'RI utilization {util_pct:.0f}% — ${unused_cost:.2f}/mo wasted',
            'cardData': {
                'cardId': f'ri-{account_id}', 'type': 'advisory',
                'title': 'Underutilized Reserved Instances', 'icon': '🏪',
                'count': 1, 'risk': 'medium',
                'description': f'RI utilization is {util_pct:.0f}% — ${unused_cost:.2f}/month in unused commitments. Consider selling on RI Marketplace.',
                'monthlySavings': round(unused_cost, 2),
                'resources': [],
                'actionUrl': 'https://console.aws.amazon.com/ec2/v2/home#ReservedInstances',
            }
        }
    except Exception:
        return None


def _check_rds_commercial_engine(tip, data, account_id, acct_label, creds):
    """Flag Oracle/SQL Server RDS instances as migration candidates."""
    commercial = [db for db in data.get('rds_instances', []) if db.get('Engine', '') in ('oracle-ee', 'oracle-se2', 'sqlserver-ee', 'sqlserver-se', 'sqlserver-ex', 'sqlserver-web')]
    if not commercial:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(commercial)} commercial-engine RDS instances',
        'cardData': {
            'cardId': f'rds-commercial-{account_id}', 'type': 'advisory',
            'title': 'Commercial DB Engine Migration', 'icon': '🗄️',
            'count': len(commercial), 'risk': 'low',
            'description': f'{len(commercial)} Oracle/SQL Server instance(s) — migrating to PostgreSQL/MySQL could save 30-60%',
            'monthlySavings': None,
            'resources': [{'id': db['DBInstanceIdentifier'], 'engine': db.get('Engine', ''), 'class': db.get('DBInstanceClass', '')} for db in commercial],
        }
    }


def _check_graviton_candidates(tip, data, account_id, acct_label, creds):
    """Flag x86 EC2 instances that have Graviton equivalents."""
    x86_families = {'t3', 't3a', 'm5', 'm5a', 'm6i', 'c5', 'c5a', 'c6i', 'r5', 'r5a', 'r6i'}
    graviton_map = {'t3': 't4g', 't3a': 't4g', 'm5': 'm7g', 'm5a': 'm7g', 'm6i': 'm7g', 'c5': 'c7g', 'c5a': 'c7g', 'c6i': 'c7g', 'r5': 'r7g', 'r5a': 'r7g', 'r6i': 'r7g'}
    candidates = []
    for inst in data.get('ec2_instances', []):
        itype = inst.get('InstanceType', '')
        family = itype.split('.')[0] if '.' in itype else ''
        if family in x86_families:
            tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
            candidates.append({'id': inst['InstanceId'], 'name': tags.get('Name', inst['InstanceId']), 'type': itype, 'gravitonEquiv': graviton_map.get(family, family + 'g')})
    if not candidates:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(candidates)} x86 instances with Graviton equivalents',
        'cardData': {
            'cardId': f'graviton-{account_id}', 'type': 'advisory',
            'title': 'Graviton Migration Candidates', 'icon': '⚡',
            'count': len(candidates), 'risk': 'low',
            'description': f'{len(candidates)} x86 instance(s) have Graviton equivalents — save 20-40% with better performance',
            'monthlySavings': None,
            'resources': candidates[:10],
        }
    }


# ── Registry: tip.id → check function ────────────────────────────────────────
_SCAN_REGISTRY = {
    # Level 1 — Resource Hygiene
    'ebs-004':     _check_ebs_unattached,
    'ebs-002':     _check_ebs_snapshots,
    'ebs-003':     _check_ebs_snapshots,   # archive = same detection as delete
    'vpc-001':     _check_eip_unattached,
    's3-002':      _check_s3_lifecycle,
    's3-003':      _check_s3_lifecycle,
    'elb-001':     _check_elb_idle,
    'kms-001':     _check_kms_unused,
    'general-002': _check_budgets,
    'general-004': _check_ebs_unattached,  # general audit → EBS check
    # Level 2 — Optimization
    'ec2-001':     _check_ec2_idle,        # rightsizing uses idle detection
    'ec2-003':     _check_spot_candidates,
    'ec2-009':     _check_spot_candidates,
    'ec2-006':     _check_graviton_candidates,
    'rds-001':     _check_rds_idle,
    'rds-006':     _check_rds_commercial_engine,
    # Level 3 — Architecture / Commitment
    'general-014': _check_ri_marketplace,
}
