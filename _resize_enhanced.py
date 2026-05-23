#!/usr/bin/env python3
"""Enhance resize: full instance specs + sortable alternatives table."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Enhance _get_instance_specs to return ALL parameters
old_specs_fn = '''def _get_instance_specs(ec2_client, instance_type):
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
    return {'vcpu': 0, 'mem': 0, 'archs': []}'''

new_specs_fn = '''def _get_instance_specs(ec2_client, instance_type):
    """Get full specs for an instance type via ec2:DescribeInstanceTypes."""
    try:
        resp = ec2_client.describe_instance_types(InstanceTypes=[instance_type])
        types = resp.get('InstanceTypes', [])
        if types:
            t = types[0]
            vcpu_info = t.get('VCpuInfo', {})
            mem_info = t.get('MemoryInfo', {})
            proc_info = t.get('ProcessorInfo', {})
            net_info = t.get('NetworkInfo', {})
            storage_info = t.get('InstanceStorageInfo', {})
            ebs_info = t.get('EbsInfo', {})
            gpu_info = t.get('GpuInfo', {})

            vcpu = vcpu_info.get('DefaultVCpus', 0)
            mem_mb = mem_info.get('SizeInMiB', 0)
            mem_gb = round(mem_mb / 1024, 1)
            archs = proc_info.get('SupportedArchitectures', [])

            return {
                'vcpu': vcpu,
                'mem': mem_gb,
                'archs': archs,
                'processor': proc_info.get('SustainedClockSpeedInGhz', 0),
                'processorManufacturer': proc_info.get('Manufacturer', ''),
                'networkPerformance': net_info.get('NetworkPerformance', ''),
                'maxNetworkInterfaces': net_info.get('MaximumNetworkInterfaces', 0),
                'ebsOptimized': ebs_info.get('EbsOptimizedSupport', 'unsupported'),
                'ebsMaxBandwidthMbps': ebs_info.get('EbsOptimizedInfo', {}).get('MaximumBandwidthInMbps', 0),
                'ebsMaxIops': ebs_info.get('EbsOptimizedInfo', {}).get('MaximumIops', 0),
                'ebsMaxThroughputMBs': ebs_info.get('EbsOptimizedInfo', {}).get('MaximumThroughputInMBps', 0),
                'instanceStorageSupported': t.get('InstanceStorageSupported', False),
                'instanceStorageGB': round(storage_info.get('TotalSizeInGB', 0), 0) if storage_info else 0,
                'instanceStorageType': storage_info.get('Disks', [{}])[0].get('Type', '') if storage_info.get('Disks') else '',
                'gpuCount': sum(g.get('Count', 0) for g in gpu_info.get('Gpus', [])) if gpu_info.get('Gpus') else 0,
                'gpuMemoryGB': sum(g.get('MemoryInfo', {}).get('SizeInMiB', 0) for g in gpu_info.get('Gpus', [])) / 1024 if gpu_info.get('Gpus') else 0,
                'hypervisor': t.get('Hypervisor', ''),
                'burstable': t.get('BurstablePerformanceSupported', False),
                'currentGeneration': t.get('CurrentGeneration', False),
                'freeTierEligible': t.get('FreeTierEligible', False),
            }
    except Exception as e:
        logger.warning(f"DescribeInstanceTypes failed for {instance_type}: {e}")
    return {'vcpu': 0, 'mem': 0, 'archs': []}'''

if old_specs_fn in content:
    content = content.replace(old_specs_fn, new_specs_fn)
    print("1. _get_instance_specs enhanced with full parameters")
else:
    print("1. WARNING: Could not find old _get_instance_specs")

# 2. Enhance _get_rightsizing_candidates to return full specs for each candidate
old_candidate_append = """                candidates.append({
                    'instanceType': itype,
                    'vcpu': vcpu,
                    'memory': mem_gb,
                    'isGraviton': is_graviton,
                    'archs': archs,
                })"""

new_candidate_append = """                net_perf = t.get('NetworkInfo', {}).get('NetworkPerformance', '')
                ebs_opt = t.get('EbsInfo', {}).get('EbsOptimizedSupport', '')
                ebs_iops = t.get('EbsInfo', {}).get('EbsOptimizedInfo', {}).get('MaximumIops', 0)
                ebs_bw = t.get('EbsInfo', {}).get('EbsOptimizedInfo', {}).get('MaximumBandwidthInMbps', 0)
                burstable = t.get('BurstablePerformanceSupported', False)
                proc_mfr = t.get('ProcessorInfo', {}).get('Manufacturer', '')
                clock = t.get('ProcessorInfo', {}).get('SustainedClockSpeedInGhz', 0)
                candidates.append({
                    'instanceType': itype,
                    'vcpu': vcpu,
                    'memory': mem_gb,
                    'isGraviton': is_graviton,
                    'archs': archs,
                    'networkPerformance': net_perf,
                    'ebsOptimized': ebs_opt,
                    'ebsMaxIops': ebs_iops,
                    'ebsMaxBandwidthMbps': ebs_bw,
                    'burstable': burstable,
                    'processorManufacturer': proc_mfr,
                    'clockSpeed': clock,
                })"""

if old_candidate_append in content:
    content = content.replace(old_candidate_append, new_candidate_append)
    print("2. Candidates now include full specs")
else:
    print("2. WARNING: Could not find old candidate append")

# 3. Pass extra fields through to the recommendation results
old_rec_build = """        rec = {
            'instanceType': c['instanceType'],
            'vcpu': c['vcpu'],
            'memory': c['memory'],
            'hourlyRate': price,
            'monthlyRate': monthly,
            'monthlySavings': savings,
            'savingsPercent': pct,
            'isGraviton': c['isGraviton'],
        }"""

new_rec_build = """        rec = {
            'instanceType': c['instanceType'],
            'vcpu': c['vcpu'],
            'memory': c['memory'],
            'hourlyRate': price,
            'monthlyRate': monthly,
            'monthlySavings': savings,
            'savingsPercent': pct,
            'isGraviton': c['isGraviton'],
            'networkPerformance': c.get('networkPerformance', ''),
            'ebsOptimized': c.get('ebsOptimized', ''),
            'ebsMaxIops': c.get('ebsMaxIops', 0),
            'ebsMaxBandwidthMbps': c.get('ebsMaxBandwidthMbps', 0),
            'burstable': c.get('burstable', False),
            'processorManufacturer': c.get('processorManufacturer', ''),
            'clockSpeed': c.get('clockSpeed', 0),
        }"""

if old_rec_build in content:
    content = content.replace(old_rec_build, new_rec_build)
    print("3. Recommendations now include full specs")
else:
    print("3. WARNING: Could not find old rec build")

# 4. Update the analyze response to include full currentSpecs
old_current_specs = """        'currentSpecs': {
            'vcpu': current_vcpu,
            'memory': current_mem,
            'hourlyRate': current_hourly,
            'monthlyRate': current_monthly,
        },"""

new_current_specs = """        'currentSpecs': {
            'vcpu': current_vcpu,
            'memory': current_mem,
            'hourlyRate': current_hourly,
            'monthlyRate': current_monthly,
            'processor': current_specs_raw.get('processor', 0),
            'processorManufacturer': current_specs_raw.get('processorManufacturer', ''),
            'networkPerformance': current_specs_raw.get('networkPerformance', ''),
            'ebsOptimized': current_specs_raw.get('ebsOptimized', ''),
            'ebsMaxIops': current_specs_raw.get('ebsMaxIops', 0),
            'ebsMaxBandwidthMbps': current_specs_raw.get('ebsMaxBandwidthMbps', 0),
            'instanceStorageSupported': current_specs_raw.get('instanceStorageSupported', False),
            'instanceStorageGB': current_specs_raw.get('instanceStorageGB', 0),
            'instanceStorageType': current_specs_raw.get('instanceStorageType', ''),
            'burstable': current_specs_raw.get('burstable', False),
            'freeTierEligible': current_specs_raw.get('freeTierEligible', False),
            'hypervisor': current_specs_raw.get('hypervisor', ''),
            'currentGeneration': current_specs_raw.get('currentGeneration', False),
        },"""

if old_current_specs in content:
    content = content.replace(old_current_specs, new_current_specs)
    print("4. Current specs now include full parameters")
else:
    print("4. WARNING: Could not find old current specs")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Backend enhanced - all done")
