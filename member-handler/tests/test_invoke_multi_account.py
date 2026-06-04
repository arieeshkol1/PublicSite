"""
Unit tests for the _invoke_multi_account provider routing integration and
_normalize_connector_cost_data helper.

Validates:
- Provider routing via _route_to_connector for each account
- Concurrent processing via _gather_multi_account_parallel for non-AWS accounts
- Mixed-provider queries routing each account independently
- failedAccounts metadata in response for partial failures
- Error response when all accounts fail

Requirements: 1.6, 12.1, 12.2, 12.3, 12.4
"""
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestNormalizeConnectorCostData:
    """Tests for _normalize_connector_cost_data helper function."""

    def _import_fn(self):
        """Import the function under test."""
        # The function is defined in lambda_function.py at module level
        from lambda_function import _normalize_connector_cost_data
        return _normalize_connector_cost_data

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
    })
    def test_dict_with_cost_by_service_and_daily_trend(self):
        """Dict input with both fields returns them directly."""
        fn = self._import_fn()
        cost_data = {
            'cost_by_service': [
                {'service': 'Virtual Machines', 'cost_usd': 89.50},
                {'service': 'Storage', 'cost_usd': 12.30},
            ],
            'daily_cost_trend': [
                {'date': '2024-01-25', 'cost_usd': 12.34},
                {'date': '2024-01-26', 'cost_usd': 11.89},
            ],
            'provider': 'azure',
        }
        result = fn(cost_data)
        assert result['cost_by_service'] == cost_data['cost_by_service']
        assert result['daily_cost_trend'] == cost_data['daily_cost_trend']
        assert result['provider'] == 'azure'

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
    })
    def test_dict_missing_fields_defaults_to_empty_lists(self):
        """Dict without cost_by_service or daily_cost_trend gets empty lists."""
        fn = self._import_fn()
        result = fn({'provider': 'gcp'})
        assert result['cost_by_service'] == []
        assert result['daily_cost_trend'] == []
        assert result['provider'] == 'gcp'

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
    })
    def test_list_format_parses_results_by_time(self):
        """List input (raw Cost Explorer format) is parsed into normalized format."""
        fn = self._import_fn()
        cost_data = [
            {
                'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                'Groups': [
                    {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '50.0'}}},
                    {'Keys': ['Amazon S3'], 'Metrics': {'UnblendedCost': {'Amount': '10.0'}}},
                ],
            },
            {
                'TimePeriod': {'Start': '2024-01-02', 'End': '2024-01-03'},
                'Groups': [
                    {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '45.0'}}},
                ],
            },
        ]
        result = fn(cost_data)
        assert len(result['cost_by_service']) == 2
        # EC2 total should be 95.0
        ec2 = next(s for s in result['cost_by_service'] if s['service'] == 'Amazon EC2')
        assert ec2['cost_usd'] == 95.0
        # S3 total should be 10.0
        s3 = next(s for s in result['cost_by_service'] if s['service'] == 'Amazon S3')
        assert s3['cost_usd'] == 10.0
        # Daily trend
        assert len(result['daily_cost_trend']) == 2
        assert result['daily_cost_trend'][0]['date'] == '2024-01-01'
        assert result['daily_cost_trend'][0]['cost_usd'] == 60.0

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
    })
    def test_non_dict_non_list_returns_empty(self):
        """Non-dict, non-list input returns empty structure."""
        fn = self._import_fn()
        result = fn(None)
        assert result == {'cost_by_service': [], 'daily_cost_trend': []}

        result = fn("unexpected")
        assert result == {'cost_by_service': [], 'daily_cost_trend': []}


class TestInvokeMultiAccountIntegration:
    """Integration tests for _invoke_multi_account provider routing."""

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
        'BEDROCK_MODEL_ID': 'test-model',
    })
    @patch('lambda_function._ask_bedrock_multi_account')
    @patch('lambda_function._maybe_save_tip')
    @patch('lambda_function._search_tips')
    @patch('lambda_function._classify_intent')
    @patch('lambda_function._route_to_connector')
    @patch('lambda_function._gather_account_data')
    @patch('lambda_function.boto3')
    def test_all_aws_accounts_backward_compatible(
        self, mock_boto3, mock_gather, mock_route, mock_classify,
        mock_tips, mock_save_tip, mock_bedrock
    ):
        """When all accounts are AWS, produces same result as before."""
        from lambda_function import _invoke_multi_account

        mock_classify.return_value = {'all'}
        mock_route.side_effect = [
            ('aws', {'account_id': '111111111111', 'member_email': 'u@test.com', 'session_name': 'SlashMyBillAI'}),
            ('aws', {'account_id': '222222222222', 'member_email': 'u@test.com', 'session_name': 'SlashMyBillAI'}),
        ]
        mock_tips.return_value = []

        # Mock STS assume role
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIA...',
                'SecretAccessKey': 'secret',
                'SessionToken': 'token',
            }
        }
        mock_boto3.client.return_value = mock_sts

        mock_gather.return_value = (
            {
                'cost_by_service': [{'service': 'EC2', 'cost_usd': 100.0}],
                'daily_cost_trend': [{'date': '2024-01-01', 'cost_usd': 10.0}],
            },
            ['ce:GetCostAndUsage']
        )

        mock_bedrock.return_value = 'Analysis complete.'

        # Mock dynamodb for healthcheck
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {}}
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource

        result = _invoke_multi_account(
            'How much am I spending?',
            ['111111111111', '222222222222'],
            'u@test.com',
            'int-123'
        )

        body = json.loads(result['body'])
        assert body['multiAccount'] is True
        assert body['interactionId'] == 'int-123'
        assert 'failedAccounts' not in body  # No failures

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
        'BEDROCK_MODEL_ID': 'test-model',
    })
    @patch('lambda_function._ask_bedrock_multi_account')
    @patch('lambda_function._maybe_save_tip')
    @patch('lambda_function._search_tips')
    @patch('lambda_function._search_tips_multi_provider')
    @patch('lambda_function._classify_intent')
    @patch('lambda_function._route_to_connector')
    @patch('lambda_function._gather_multi_account_parallel')
    @patch('lambda_function._gather_account_data')
    @patch('lambda_function.boto3')
    def test_mixed_provider_with_partial_failure(
        self, mock_boto3, mock_gather, mock_parallel, mock_route,
        mock_classify, mock_tips_multi, mock_tips, mock_save_tip, mock_bedrock
    ):
        """Mixed providers with one failure includes failedAccounts in response."""
        from lambda_function import _invoke_multi_account

        mock_classify.return_value = {'all'}
        mock_route.side_effect = [
            ('aws', {'account_id': '111111111111', 'member_email': 'u@test.com', 'session_name': 'SlashMyBillAI'}),
            ('azure', {'tenant_id': 't', 'client_id': 'c', 'encrypted_client_secret': 's'}),
        ]
        mock_tips_multi.return_value = []

        # AWS account STS
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIA...',
                'SecretAccessKey': 'secret',
                'SessionToken': 'token',
            }
        }
        mock_boto3.client.return_value = mock_sts

        mock_gather.return_value = (
            {
                'cost_by_service': [{'service': 'EC2', 'cost_usd': 100.0}],
                'daily_cost_trend': [],
            },
            ['ce:GetCostAndUsage']
        )

        # Non-AWS parallel executor returns Azure as failed
        mock_parallel.return_value = {
            'accounts': {},
            'failedAccounts': [
                {'accountId': 'sub-uuid-123', 'provider': 'azure', 'error': 'Authentication failed'}
            ],
            'totalAccounts': 1,
            'successfulAccounts': 0,
        }

        mock_bedrock.return_value = 'Partial analysis.'

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {}}
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource

        result = _invoke_multi_account(
            'How much am I spending?',
            ['111111111111', 'sub-uuid-123'],
            'u@test.com',
            'int-456'
        )

        body = json.loads(result['body'])
        assert body['multiAccount'] is True
        # Should have failedAccounts since Azure failed
        assert 'failedAccounts' in body
        assert len(body['failedAccounts']) == 1
        assert body['failedAccounts'][0]['accountId'] == 'sub-uuid-123'
        assert body['failedAccounts'][0]['provider'] == 'azure'

    @patch.dict(os.environ, {
        'JWT_SECRET': 'test',
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_CLIENT_ID': '',
    })
    @patch('lambda_function._search_tips')
    @patch('lambda_function._classify_intent')
    @patch('lambda_function._route_to_connector')
    @patch('lambda_function._gather_account_data')
    @patch('lambda_function.boto3')
    def test_all_accounts_fail_returns_error_response(
        self, mock_boto3, mock_gather, mock_route, mock_classify, mock_tips
    ):
        """When all accounts fail, returns error response with failedAccounts."""
        from lambda_function import _invoke_multi_account

        mock_classify.return_value = {'all'}
        mock_route.side_effect = [
            ('aws', {'account_id': '111111111111', 'member_email': 'u@test.com', 'session_name': 'SlashMyBillAI'}),
        ]
        mock_tips.return_value = []

        # STS assume role fails
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = Exception('Access denied')
        mock_boto3.client.return_value = mock_sts

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {}}
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_resource

        result = _invoke_multi_account(
            'What is my spend?',
            ['111111111111'],
            'u@test.com',
            'int-789'
        )

        body = json.loads(result['body'])
        assert 'unable to retrieve data' in body['answer'].lower()
        assert body['failedAccounts'] is not None
        assert len(body['failedAccounts']) == 1
        assert body['failedAccounts'][0]['provider'] == 'aws'
        assert body['chartData'] == []
        assert body['topServices'] == []
