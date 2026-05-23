"""Unit tests for SQL Platform Comparator."""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('AWS_REGION', 'us-east-1')
os.environ.setdefault('MEMBERS_TABLE', 'MemberPortal-Members')
os.environ.setdefault('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')

import importlib.util
spec = importlib.util.spec_from_file_location('lf', os.path.join(os.path.dirname(__file__), '..', 'lambda_function.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_constants():
    assert mod.PLATFORM_EC2_WIN_SQL_LI == 'ec2_windows_sql_li'
    assert mod.PLATFORM_EC2_WIN_BYOL == 'ec2_windows_byol'
    assert mod.PLATFORM_RDS_SQL_STANDARD == 'rds_sql_standard'
    assert mod.PLATFORM_RDS_SQL_ENTERPRISE == 'rds_sql_enterprise'
    assert len(mod.VALID_PLATFORMS) == 4
    print("  PASS: constants")


def test_migration_templates():
    assert len(mod.SQL_MIGRATION_TEMPLATES) == 7
    for key, tmpl in mod.SQL_MIGRATION_TEMPLATES.items():
        assert 'steps' in tmpl
        assert 'risks' in tmpl
        assert 'complexity' in tmpl
        assert 'duration' in tmpl
        assert len(tmpl['steps']) > 0
        has_backup = any(s['type'] == 'backup' for s in tmpl['steps'])
        assert has_backup, f'Template {key} has no backup step'
    print("  PASS: migration templates (7 paths, all have backup steps)")


def test_comparison_matrix():
    pricing = {
        'r5.2xlarge': {
            'instanceType': 'r5.2xlarge',
            'ec2WindowsSqlStdHourly': 1.5,
            'ec2WindowsSqlEntHourly': 3.0,
            'ec2WindowsByolHourly': 0.8,
            'rdsSqlStandardHourly': 1.8,
            'rdsSqlEnterpriseHourly': 4.0,
            'rdsInstanceClass': 'db.r5.2xlarge',
        }
    }
    workloads = [{
        'instanceId': 'i-test123',
        'accountId': '123456789012',
        'source': 'ec2',
        'instanceType': 'r5.2xlarge',
        'ec2EquivalentType': 'r5.2xlarge',
        'region': 'us-east-1',
        'platform': 'Windows with SQL Enterprise',
        'sqlEdition': 'Enterprise',
        'currentPlatformKey': 'ec2_windows_sql_li',
        'tags': {},
        'name': 'test',
        'vcpus': 8,
        'memoryGb': 64.0,
    }]

    result = mod._build_sql_comparison_matrix(workloads, pricing)
    assert len(result) == 1
    assert len(result[0]['options']) == 4

    current_count = sum(1 for o in result[0]['options'] if o['isCurrent'])
    assert current_count == 1

    cheapest_count = sum(1 for o in result[0]['options'] if o['isCheapest'])
    assert cheapest_count == 1

    for o in result[0]['options']:
        if o['isCurrent']:
            assert o['savingsVsCurrent'] == 0
        if o['isCheapest']:
            assert o['platform'] == 'ec2_windows_byol'

    # Verify monthly costs
    assert result[0]['currentMonthlyCost'] == 3.0 * 730  # Enterprise hourly * 730
    print("  PASS: comparison matrix (4 options, 1 current, 1 cheapest, savings correct)")


def test_migration_plan_generation():
    plan = mod._generate_sql_migration_plan(
        'i-test123', 'ec2_windows_sql_li', 'ec2_windows_byol',
        {'instance_type': 'r5.2xlarge', 'region': 'us-east-1',
         'ec2_equivalent_type': 'r5.2xlarge', 'savings_vs_current': 356.0}
    )
    assert plan is not None
    assert plan['complexity'] == 'high'
    assert plan['estimatedSavings']['monthly'] == 356.0
    assert plan['estimatedSavings']['annual'] == 4272.0
    assert len(plan['steps']) == 8
    assert plan['steps'][0]['stepNumber'] == 1
    assert plan['steps'][-1]['stepNumber'] == 8
    assert plan['steps'][-1]['isReversible'] is False  # cleanup step
    print("  PASS: migration plan generation (8 steps, correct savings)")


def test_invalid_migration_pair():
    plan = mod._generate_sql_migration_plan(
        'i-test', 'ec2_windows_byol', 'ec2_windows_sql_li',
        {'instance_type': 'r5.2xlarge', 'region': 'us-east-1',
         'ec2_equivalent_type': 'r5.2xlarge', 'savings_vs_current': 0}
    )
    assert plan is None
    print("  PASS: invalid migration pair returns None")


def test_route_exists():
    event = {'routeKey': 'POST /members/sql/compare', 'headers': {}, 'body': '{}'}
    resp = mod.lambda_handler(event, None)
    assert resp['statusCode'] == 401  # Auth required = route exists
    print("  PASS: POST /members/sql/compare route exists (returns 401 without auth)")

    event2 = {'routeKey': 'POST /members/sql/migration-plan', 'headers': {}, 'body': '{}'}
    resp2 = mod.lambda_handler(event2, None)
    assert resp2['statusCode'] == 401
    print("  PASS: POST /members/sql/migration-plan route exists (returns 401 without auth)")


if __name__ == '__main__':
    print("Running SQL Platform Comparator unit tests...")
    test_constants()
    test_migration_templates()
    test_comparison_matrix()
    test_migration_plan_generation()
    test_invalid_migration_pair()
    test_route_exists()
    print("\nALL TESTS PASSED ✓")
