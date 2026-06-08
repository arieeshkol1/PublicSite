"""Temporary test script for intent_classifier."""
import sys
import time
sys.path.insert(0, r'c:\Users\Michal\Desktop\PublicSite\member-handler')

from intent_classifier import _classify_intent, get_apis_for_intent, CATEGORY_API_MAPPING

tests = [
    ('How much does EC2 cost?', {'ec2', 'cost-general'}),
    ('What is my total monthly bill?', {'cost-general'}),
    ('Show me RDS instances', {'rds'}),
    ('Tell me about S3 buckets', {'s3'}),
    ('How can I reduce Lambda costs?', {'lambda', 'cost-general'}),
    ('What is the NAT gateway charge?', {'network', 'cost-general'}),
    ('Show my EBS volumes', {'storage'}),
    ('', {'all'}),
    ('Hello, how are you?', {'all'}),
    ('rightsizing my EC2 fleet', {'compute'}),
    ('What is costing me the most?', {'cost-general'}),
    ('Show me compute and storage and network usage', {'all'}),
    ('My database is slow', {'rds'}),
    ('cost-general only question about spending', {'cost-general'}),
    ('How much am I spending on EC2 and RDS and S3 and Lambda and EBS?', {'all'}),
    ('What are my EC2 instance types?', {'ec2'}),
]

passed = 0
failed = 0
for q, expected in tests:
    result = _classify_intent(q)
    if result == expected:
        print(f'  PASS: {q!r} -> {result}')
        passed += 1
    else:
        print(f'  FAIL: {q!r} -> got {result}, expected {expected}')
        failed += 1

print(f'\nResults: {passed}/{passed+failed} passed')

# Performance test
start = time.perf_counter()
for _ in range(10000):
    _classify_intent('How much does my EC2 instances cost this month?')
elapsed = (time.perf_counter() - start) / 10000 * 1000
print(f'Avg execution time: {elapsed:.4f}ms (limit: 50ms)')

# Test get_apis_for_intent
print('\n--- API mapping tests ---')
print(f"  ec2 intent APIs: {get_apis_for_intent({'ec2'})}")
print(f"  cost-general APIs: {get_apis_for_intent({'cost-general'})}")
print(f"  all intent APIs: {get_apis_for_intent({'all'})}")
print(f"  ec2+cost-general APIs: {get_apis_for_intent({'ec2', 'cost-general'})}")
