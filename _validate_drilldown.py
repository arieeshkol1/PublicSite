#!/usr/bin/env python3
"""Validate per-tip drilldown ("check") capability through the connection.

The system can only execute the OpenAPI operations defined in
agent-action/openapi-schema.json. Those 11 operations are ALL AWS-only:
  getCostData, getMonthlyComparison, getAWSPricing, getBudgets, getFinOpsSettings
  getEC2Instances, getRDSInstances, getLambdaFunctions, getS3Buckets,
  getEBSVolumes, getNetworkResources

Classification per tip:
  FULL       - AWS, and a resource-level operation exists for the service
               (so a real "check" can run and return resource data)
  COST_ONLY  - AWS, no resource operation, but getCostData(serviceFilter)
               can still return spend for the service
  NONE       - non-AWS (Azure/GCP/OpenAI): no OpenAPI operation exists,
               so no drilldown through the connection returns data
"""
import csv
import json
from collections import Counter, defaultdict

with open('_tips_export.csv', encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))

def v(r, k): return (r.get(k) or '').strip()

# AWS services that have a dedicated resource-level OpenAPI operation.
RESOURCE_OP = {
    'EC2': 'getEC2Instances',
    'RDS': 'getRDSInstances',
    'Lambda': 'getLambdaFunctions',
    'S3': 'getS3Buckets',
    'EBS': 'getEBSVolumes',
    'NAT Gateway': 'getNetworkResources',
    'Elastic IP': 'getNetworkResources',
    'VPC': 'getNetworkResources',
    'Data Transfer': 'getNetworkResources',
    'Budgets': 'getBudgets',
    'General': 'getFinOpsSettings',  # FinOps healthcheck / budgets
}

results = []
counts = Counter()
gap_by_cloud = Counter()
aws_costonly_services = Counter()

for r in rows:
    cloud = v(r, 'cloud').upper()
    svc = v(r, 'service')
    has_check = bool(v(r, 'drilldownApis') or v(r, 'automatedCheck'))

    if cloud == 'AWS':
        if svc in RESOURCE_OP:
            cls = 'FULL'
            op = RESOURCE_OP[svc]
        else:
            cls = 'COST_ONLY'
            op = 'getCostData(usageTypeBreakdown,serviceFilter)'
            aws_costonly_services[svc] += 1
    else:
        cls = 'NONE'
        op = '(no OpenAPI operation for ' + cloud + ')'
        gap_by_cloud[cloud] += 1

    counts[cls] += 1
    results.append({
        'cloud': cloud, 'service': svc, 'tipId': v(r, 'tipId'),
        'title': v(r, 'title'),
        'drilldown_class': cls,
        'openapi_operation': op,
        'has_check_content': has_check,
    })

total = len(rows)
print(f"Total tips: {total}\n")
print("=== Drilldown capability through the connection (OpenAPI) ===")
for cls in ('FULL', 'COST_ONLY', 'NONE'):
    print(f"  {cls:10s}: {counts[cls]:4d}  ({100*counts[cls]/total:.0f}%)")

print("\n=== NONE (no OpenAPI drilldown exists) by provider ===")
for cl, c in gap_by_cloud.most_common():
    print(f"  {cl:8s}: {c}")

print("\n=== AWS COST_ONLY services (resource-level check NOT available) ===")
for svc, c in aws_costonly_services.most_common():
    print(f"  {c:4d}  {svc}")

# Tips that have NO check content at all (no automatedCheck and no drilldownApis)
no_check = [r for r in rows if not (v(r,'drilldownApis') or v(r,'automatedCheck'))]
print(f"\n=== Tips with NO 'check' content at all: {len(no_check)} ===")
for cl, c in Counter(v(r,'cloud') for r in no_check).most_common():
    print(f"  {cl:8s}: {c}")

# Write full per-tip report
with open('tips-drilldown-validation.json', 'w', encoding='utf-8') as f:
    json.dump({
        'summary': {
            'total': total,
            'FULL': counts['FULL'],
            'COST_ONLY': counts['COST_ONLY'],
            'NONE': counts['NONE'],
            'no_check_content': len(no_check),
            'openapi_operations_available': [
                'getCostData', 'getMonthlyComparison', 'getAWSPricing', 'getBudgets',
                'getFinOpsSettings', 'getEC2Instances', 'getRDSInstances',
                'getLambdaFunctions', 'getS3Buckets', 'getEBSVolumes', 'getNetworkResources',
            ],
            'note': 'All OpenAPI operations are AWS-only; non-AWS tips have no drilldown path that returns live data through the connection.',
        },
        'tips': results,
    }, f, indent=2, ensure_ascii=False)

print("\nWrote tips-drilldown-validation.json")
