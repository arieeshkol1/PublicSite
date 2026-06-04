"""
Unit tests for the Parallel Executor module.

Tests concurrent AWS API call execution with ThreadPoolExecutor,
10-second per-call timeout, and partial failure handling.
Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""
import sys
import os
import time
from unittest.mock import patch, MagicMock
from concurrent.futures import TimeoutError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from parallel_executor import (
    _gather_aws_data_parallel,
    _fetch_ec2_instances,
    _fetch_cloudwatch_metrics,
    _fetch_rds_instances,
    _fetch_s3_buckets,
    _fetch_ebs_volumes,
    _fetch_nat_gateways,
    _fetch_lambda_functions,
    API_FETCH_MAP,
    MAX_WORKERS,
    PER_CALL_TIMEOUT,
)


FAKE_CREDENTIALS = {
    'AccessKeyId': 'AKIAIOSFODNN7EXAMPLE',
    'SecretAccessKey': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
    'SessionToken': 'FwoGZXIvYXdzEBAaDExample',
}


class TestConstants:
    """Test that module constants match the spec requirements."""

    def test_max_workers_is_5(self):
        """Requirement 8.2: max_workers=5 per account."""
        assert MAX_WORKERS == 5

    def test_per_call_timeout_is_10(self):
        """Requirement 8.4: 10-second per-call timeout."""
        assert PER_CALL_TIMEOUT == 10


class TestApiMapping:
    """Test the API identifier to function mapping."""

    def test_all_expected_apis_mapped(self):
        """All APIs from intent_classifier are present in the fetch map."""
        expected = [
            'ec2_describe_instances', 'cloudwatch', 'rds_describe_instances',
            's3_list_buckets', 'ebs_volumes', 'nat_gateways', 'eips',
            'vpc_endpoints', 'lambda_list_functions',
        ]
        for api_id in expected:
            assert api_id in API_FETCH_MAP, f"{api_id} missing from API_FETCH_MAP"

    def test_network_apis_share_function(self):
        """nat_gateways, eips, vpc_endpoints all use the same fetch function."""
        assert API_FETCH_MAP['nat_gateways'] is API_FETCH_MAP['eips']
        assert API_FETCH_MAP['nat_gateways'] is API_FETCH_MAP['vpc_endpoints']


class TestGatherAwsDataParallel:
    """Tests for _gather_aws_data_parallel function."""

    @patch('parallel_executor._fetch_ec2_instances')
    @patch('parallel_executor._fetch_cloudwatch_metrics')
    def test_ec2_intent_calls_ec2_and_cloudwatch(self, mock_cw, mock_ec2):
        """EC2 intent should call ec2_describe_instances and cloudwatch."""
        mock_ec2.return_value = ('ec2_instances', [{'id': 'i-123'}], 'ec2:DescribeInstances')
        mock_cw.return_value = ('cloudwatch_metrics', {'account_avg_cpu_pct': 15.0}, 'cloudwatch:GetMetricStatistics (EC2 CPU)')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'What EC2 instances?', {'ec2'})

        assert 'ec2_instances' in data
        assert 'cloudwatch_metrics' in data
        assert len(actions) == 2

    @patch('parallel_executor._fetch_rds_instances')
    def test_rds_intent_calls_rds(self, mock_rds):
        """RDS intent should call rds_describe_instances."""
        mock_rds.return_value = ('rds_instances', [{'id': 'mydb'}], 'rds:DescribeDBInstances')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'RDS instances?', {'rds'})

        assert 'rds_instances' in data
        assert 'rds:DescribeDBInstances' in actions

    @patch('parallel_executor._fetch_s3_buckets')
    def test_s3_intent_calls_s3(self, mock_s3):
        """S3 intent should call s3_list_buckets."""
        mock_s3.return_value = ('s3_buckets', [{'name': 'my-bucket'}], 's3:ListBuckets')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'S3 buckets?', {'s3'})

        assert 's3_buckets' in data
        assert 's3:ListBuckets' in actions

    def test_cost_general_intent_calls_nothing(self):
        """cost-general intent only needs cost_explorer which is handled externally."""
        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'Total cost?', {'cost-general'})

        assert data == {}
        assert actions == []

    @patch('parallel_executor._fetch_ec2_instances')
    @patch('parallel_executor._fetch_cloudwatch_metrics')
    def test_partial_failure_skips_failed_call(self, mock_cw, mock_ec2):
        """Requirement 8.3: failed calls are skipped, successful results returned."""
        mock_ec2.return_value = ('ec2_instances', [{'id': 'i-123'}], 'ec2:DescribeInstances')
        mock_cw.side_effect = Exception('CloudWatch API throttled')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'EC2 instances?', {'ec2'})

        # EC2 should succeed
        assert 'ec2_instances' in data
        assert 'ec2:DescribeInstances' in actions
        # CloudWatch should be skipped
        assert 'cloudwatch_metrics' not in data

    @patch('parallel_executor._fetch_ec2_instances')
    @patch('parallel_executor._fetch_cloudwatch_metrics')
    def test_timeout_skips_slow_call(self, mock_cw, mock_ec2):
        """Requirement 8.4: per-call timeout is enforced via future.result(timeout=10).
        
        When a function takes longer than PER_CALL_TIMEOUT, the first call
        to future.result() will raise TimeoutError. This test verifies that
        timeout causes the call to be skipped (at least 1 timeout occurs).
        """
        import parallel_executor
        original_timeout = parallel_executor.PER_CALL_TIMEOUT
        parallel_executor.PER_CALL_TIMEOUT = 1  # Temporarily reduce for fast test

        try:
            def slow_call(creds):
                time.sleep(5)  # Exceeds the 1-second timeout
                return ('ec2_instances', [], 'ec2:DescribeInstances')

            mock_ec2.side_effect = slow_call
            mock_cw.side_effect = slow_call

            data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'What EC2 instances?', {'ec2'})

            # With 1-second timeout and 5-second sleep, the first future waited on
            # will timeout. The second may or may not have completed by then.
            # Key assertion: at least one was skipped due to timeout
            assert len(actions) < 2
        finally:
            parallel_executor.PER_CALL_TIMEOUT = original_timeout

    @patch('parallel_executor._fetch_nat_gateways')
    def test_network_data_flattened(self, mock_nat):
        """Network data dict should be flattened into top-level data."""
        mock_nat.return_value = ('network_data', {
            'nat_gateways': [{'natGatewayId': 'nat-123'}],
            'nat_gateway_count': 1,
            'elastic_ips': {'total': 2, 'unattached': 1},
            'vpc_endpoints': {'total': 3},
        }, 'ec2:DescribeNatGateways+DescribeAddresses+DescribeVpcEndpoints')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'NAT gateways?', {'network'})

        # Network data should be flattened
        assert 'nat_gateways' in data
        assert 'elastic_ips' in data
        assert 'vpc_endpoints' in data
        assert 'network_data' not in data

    @patch('parallel_executor._fetch_ec2_instances')
    @patch('parallel_executor._fetch_cloudwatch_metrics')
    @patch('parallel_executor._fetch_rds_instances')
    @patch('parallel_executor._fetch_s3_buckets')
    @patch('parallel_executor._fetch_ebs_volumes')
    @patch('parallel_executor._fetch_nat_gateways')
    @patch('parallel_executor._fetch_lambda_functions')
    def test_all_intent_calls_all_apis(
        self, mock_lambda, mock_nat, mock_ebs, mock_s3, mock_rds, mock_cw, mock_ec2
    ):
        """'all' intent should call all available API functions."""
        mock_ec2.return_value = ('ec2_instances', [], 'ec2:DescribeInstances')
        mock_cw.return_value = ('cloudwatch_metrics', {}, 'cloudwatch:GetMetricStatistics')
        mock_rds.return_value = ('rds_instances', [], 'rds:DescribeDBInstances')
        mock_s3.return_value = ('s3_buckets', [], 's3:ListBuckets')
        mock_ebs.return_value = ('ebs_summary', {}, 'ec2:DescribeVolumes')
        mock_nat.return_value = ('network_data', {}, 'ec2:DescribeNatGateways')
        mock_lambda.return_value = ('lambda_functions', [], 'lambda:ListFunctions')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'Show me everything', {'all'})

        # All 7 unique fetch functions should be called
        assert len(actions) == 7

    @patch('parallel_executor._fetch_ec2_instances')
    @patch('parallel_executor._fetch_cloudwatch_metrics')
    @patch('parallel_executor._fetch_rds_instances')
    def test_all_calls_fail_returns_empty(self, mock_rds, mock_cw, mock_ec2):
        """When all calls fail, return empty data and empty actions."""
        mock_ec2.side_effect = Exception('EC2 error')
        mock_cw.side_effect = Exception('CW error')
        mock_rds.side_effect = Exception('RDS error')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'Compute info?', {'compute'})

        assert data == {}
        assert actions == []

    def test_empty_intent_after_discarding_cost_explorer(self):
        """When only cost_explorer is needed, no parallel calls are submitted."""
        data, actions = _gather_aws_data_parallel(
            FAKE_CREDENTIALS, 'Total spend this month?', {'cost-general'}
        )
        assert data == {}
        assert actions == []

    @patch('parallel_executor._fetch_nat_gateways')
    @patch('parallel_executor._fetch_ebs_volumes')
    def test_storage_intent_fetches_ebs(self, mock_ebs, mock_nat):
        """Storage intent should fetch EBS volumes."""
        mock_ebs.return_value = ('ebs_summary', {'total_gb': 100}, 'ec2:DescribeVolumes')
        # nat_gateways should not be called for storage intent
        mock_nat.return_value = ('network_data', {}, 'nat')

        data, actions = _gather_aws_data_parallel(FAKE_CREDENTIALS, 'EBS volumes?', {'storage'})

        assert 'ebs_summary' in data
        assert data['ebs_summary']['total_gb'] == 100
