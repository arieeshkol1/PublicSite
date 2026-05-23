#!/usr/bin/env python3
"""Replace static _INSTANCE_SPECS with live AWS API calls."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the _INSTANCE_SPECS dict with a dynamic lookup function
old_specs_start = "# Instance type specs for rightsizing recommendations\n_INSTANCE_SPECS = {"
old_specs_end = "}\n\n\ndef handle_server_analyze"

# Find the full block
start_idx = content.find(old_specs_start)
end_idx = content.find("\n\n\ndef handle_server_analyze")
if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find _INSTANCE_SPECS block")
    exit(1)

old_block = content[start_idx:end_idx]

new_block = '''# Instance type specs -- fetched dynamically from AWS APIs
def _get_instance_specs(ec2_client, instance_type):
    """Get vCPU, memory, arch for an instance type via ec2:DescribeInstanceTypes."""
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        types = resp.get('InstanceTypes', [])
        if types:
            t = types[0]
            vcpu = t.get('VCpuInfo', {}).get('DefaultVCpus', 0)
            mem_mb = t.get('MemoryInfo', {}).get('SizeInMiB', 0)
            mem_gb = round(mem_mb / 1024, 1)
            archs = t.get('ProcessorInfo', {}).get('SupportedArchitectures', [])
            return {'vcpu': vcpu, 'mem': mem_gb, 'archs': archs}
    except Exception as e:
        logger.warning(f"DescribeInstanceTypes failed for {instance_type}: {e}")
    return {'vcpu': 0, 'mem': 0, 'archs': []}


def _get_instance_price(instance_type, region='us-east-1'):
    """Get on-demand hourly price via AWS Pricing API."""
    region_names = {
        'us-east-1': 'US East (N. Virginia)', 'us-east-2': 'US East (Ohio)',
        'us-west-1': 'US West (N. California)', 'us-west-2': 'US West (Oregon)',
        'eu-west-1': 'EU (Ireland)', 'eu-central-1': 'EU (Frankfurt)',
        'ap-southeast-1': 'Asia Pacific (Singapore)', 'ap-northeast-1': 'Asia Pacific (Tokyo)',
        'me-south-1': 'Middle East (Bahrain)', 'me-central-1': 'Middle East (UAE)',
    }
    location = region_names.get(region, 'US East (N. Virginia)')
    try:
        pricing = boto3.client('pricing', region_name='us-east-1')
        resp = pricing.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
            ],
            MaxResults=5,
        )
        for pl in resp.get('PriceList', []):
            data = json.loads(pl) if isinstance(pl, str) else pl
            terms = data.get('terms', {}).get('OnDemand', {})
            for term in terms.values():
                for dim in term.get('priceDimensions', {}).values():
                    price = float(dim.get('pricePerUnit', {}).get('USD', '0'))
                    if price > 0:
                        return price
    except Exception as e:
        logger.warning(f"Pricing API failed for {instance_type}: {e}")
    return 0.0


def _get_rightsizing_candidates(ec2_client, current_type, needed_vcpu, needed_mem, current_hourly, arch='x86_64'):
    """Find cheaper instance types that meet the workload needs using ec2:DescribeInstanceTypes."""
    candidates = []
    # Query instance types in the same family and nearby families
    family = current_type.split('.')[0] if '.' in current_type else ''
    # Search families: same family, t3, m5, m6i, c5, c6g, m6g, r5
    families_to_check = set()
    if family:
        families_to_check.add(family)
    families_to_check.update(['t3', 't3a', 'm5', 'm5a', 'm6i', 'c5', 'c5a', 'c6i', 'r5', 'r5a'])
    # Add Graviton families
    families_to_check.update(['t4g', 'm6g', 'm7g', 'c6g', 'c7g', 'r6g', 'r7g'])

    for fam in families_to_check:
        try:
            resp = ec2_client.describe_instance_types(
                Filters=[
                    {'Name': 'instance-type', 'Values': [f'{fam}.*']},
                    {'Name': 'vcpu-info.default-vcpus', 'Values': [str(v) for v in range(max(1, needed_vcpu), needed_vcpu * 4 + 1)]},
                    {'Name': 'current-generation', 'Values': ['true']},
                ],
                MaxResults=20,
            )
            for t in resp.get('InstanceTypes', []):
                itype = t['InstanceType']
                if itype == current_type:
                    continue
                vcpu = t.get('VCpuInfo', {}).get('DefaultVCpus', 0)
                mem_mb = t.get('MemoryInfo', {}).get('SizeInMiB', 0)
                mem_gb = round(mem_mb / 1024, 1)
                archs = t.get('ProcessorInfo', {}).get('SupportedArchitectures', [])
                if vcpu < needed_vcpu or mem_gb < needed_mem:
                    continue
                is_graviton = 'arm64' in archs and 'x86_64' not in archs
                candidates.append({
                    'instanceType': itype,
                    'vcpu': vcpu,
                    'memory': mem_gb,
                    'isGraviton': is_graviton,
                    'archs': archs,
                })
        except Exception:
            pass

    # Get prices for candidates (batch -- limit to top 15 by vcpu to avoid too many API calls)
    candidates.sort(key=lambda c: (c['vcpu'], c['memory']))
    candidates = candidates[:15]

    result = []
    for c in candidates:
        price = _get_instance_price(c['instanceType'])
        if price <= 0 or price >= current_hourly:
            continue
        monthly = round(price * 730, 2)
        current_monthly = round(current_hourly * 730, 2)
        savings = round(current_monthly - monthly, 2)
        pct = round(savings / current_monthly * 100) if current_monthly > 0 else 0
        rec = {
            'instanceType': c['instanceType'],
            'vcpu': c['vcpu'],
            'memory': c['memory'],
            'hourlyRate': price,
            'monthlyRate': monthly,
            'monthlySavings': savings,
            'savingsPercent': pct,
            'isGraviton': c['isGraviton'],
        }
        if c['isGraviton'] and arch == 'x86_64':
            rec['warning'] = 'Graviton (ARM) -- verify your AMI supports ARM architecture'
        result.append(rec)

    result.sort(key=lambda r: r['monthlySavings'], reverse=True)
    return result[:5]'''

content = content[:start_idx] + new_block + content[end_idx:]

# 2. Update handle_server_analyze to use the new functions
# Replace the old specs lookup and recommendation logic
old_analyze_specs = """    # Current instance specs
    current_specs = _INSTANCE_SPECS.get(current_type, {})
    current_vcpu = current_specs.get('vcpu', 0)
    current_mem = current_specs.get('mem', 0)
    current_hourly = current_specs.get('hourly', 0)
    current_monthly = round(current_hourly * 730, 2)

    # Generate recommendations
    recommendations = []
    cpu_avg = metrics.get('cpu_avg', 0)
    cpu_max = metrics.get('cpu_max', 0)
    mem_avg = metrics.get('mem_avg')

    # Determine needed vCPU and memory
    if cpu_max < 30 and current_vcpu > 1:
        needed_vcpu = max(1, current_vcpu // 2)
    elif cpu_max < 60:
        needed_vcpu = current_vcpu
    else:
        needed_vcpu = current_vcpu

    needed_mem = current_mem
    if mem_avg is not None and mem_avg < 40 and current_mem > 2:
        needed_mem = max(2, current_mem // 2)

    # Find cheaper instance types that meet the needs
    is_arm = arch == 'arm64'
    for itype, specs in _INSTANCE_SPECS.items():
        if specs['vcpu'] < needed_vcpu:
            continue
        if specs['mem'] < needed_mem:
            continue
        if specs['hourly'] >= current_hourly:
            continue
        if itype == current_type:
            continue
        # ARM filter
        is_graviton = any(g in itype for g in ['6g.', '7g.', 't4g.'])
        if is_graviton and not is_arm and arch != 'x86_64':
            continue

        monthly = round(specs['hourly'] * 730, 2)
        savings = round(current_monthly - monthly, 2)
        pct = round(savings / current_monthly * 100) if current_monthly > 0 else 0

        rec = {
            'instanceType': itype,
            'vcpu': specs['vcpu'],
            'memory': specs['mem'],
            'hourlyRate': specs['hourly'],
            'monthlyRate': monthly,
            'monthlySavings': savings,
            'savingsPercent': pct,
            'isGraviton': is_graviton,
        }
        if is_graviton and not is_arm:
            rec['warning'] = 'Graviton (ARM) -- verify your AMI supports ARM architecture'
        recommendations.append(rec)

    # Sort by savings descending
    recommendations.sort(key=lambda r: r['monthlySavings'], reverse=True)
    # Limit to top 5
    recommendations = recommendations[:5]"""

new_analyze_specs = """    # Current instance specs (live from AWS APIs)
    current_specs_raw = _get_instance_specs(ec2, current_type)
    current_vcpu = current_specs_raw.get('vcpu', 0)
    current_mem = current_specs_raw.get('mem', 0)
    current_hourly = _get_instance_price(current_type)
    current_monthly = round(current_hourly * 730, 2)

    # Generate recommendations
    cpu_avg = metrics.get('cpu_avg', 0)
    cpu_max = metrics.get('cpu_max', 0)
    mem_avg = metrics.get('mem_avg')

    # Determine needed vCPU and memory based on actual usage
    if cpu_max < 30 and current_vcpu > 1:
        needed_vcpu = max(1, current_vcpu // 2)
    elif cpu_max < 60:
        needed_vcpu = current_vcpu
    else:
        needed_vcpu = current_vcpu

    needed_mem = current_mem
    if mem_avg is not None and mem_avg < 40 and current_mem > 2:
        needed_mem = max(2, current_mem // 2)

    recommendations = _get_rightsizing_candidates(ec2, current_type, needed_vcpu, needed_mem, current_hourly, arch)"""

if old_analyze_specs in content:
    content = content.replace(old_analyze_specs, new_analyze_specs)
    print("Analyze function updated to use live APIs")
else:
    print("WARNING: Could not find old analyze specs block")

# 3. Also update the resize handler to use live pricing instead of _INSTANCE_SPECS
old_resize_savings = """        # Calculate savings
        old_specs = _INSTANCE_SPECS.get(current_type, {})
        new_specs = _INSTANCE_SPECS.get(new_type, {})
        old_monthly = round(old_specs.get('hourly', 0) * 730, 2)
        new_monthly = round(new_specs.get('hourly', 0) * 730, 2)
        savings = round(old_monthly - new_monthly, 2)"""

new_resize_savings = """        # Calculate savings (live pricing)
        old_hourly = _get_instance_price(current_type)
        new_hourly = _get_instance_price(new_type)
        old_monthly = round(old_hourly * 730, 2)
        new_monthly = round(new_hourly * 730, 2)
        savings = round(old_monthly - new_monthly, 2)"""

if old_resize_savings in content:
    content = content.replace(old_resize_savings, new_resize_savings)
    print("Resize handler updated to use live pricing")
else:
    print("WARNING: Could not find old resize savings block")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done - all static specs replaced with live AWS API calls")
