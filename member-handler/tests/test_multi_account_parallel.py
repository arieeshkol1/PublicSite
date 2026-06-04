"""
Unit tests for _gather_multi_account_parallel and _process_single_account.

Validates concurrent multi-account processing with partial failure handling,
logging per-account failures with account ID, provider, and error details.

Requirements: 8.5, 12.1, 12.2, 12.3, 12.4
"""
import sys
import os
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from parallel_executor import (
    _gather_multi_account_parallel,
    _process_single_account,
    MAX_ACCOUNT_WORKERS,
)


FAKE_AWS_CREDS = {
    'account_id': '123456789012',
    'member_email': 'test@example.com',
    'session_name': 'SlashMyBillAI',
}

FAKE_AZURE_CREDS = {
    'tenant_id': 'tenant-123',
    'client_id': 'client-456',
    'encrypted_client_secret': 'enc-secret',
}

FAKE_GCP_CREDS = {
    'client_email': 'svc@proj.iam.gserviceaccount.com',
    'project_id': 'my-gcp-project',
    'private_key_id': 'key-789',
    'encrypted_private_key': 'enc-key',
}


class TestMaxAccountWorkers:
    """Test that the multi-account worker constant matches spec."""

    def test_max_account_workers_is_3(self):
        """Requirement 8.5: max_workers=3 for account-level parallelism."""
        assert MAX_ACCOUNT_WORKERS == 3


class TestProcessSingleAccount:
    """Tests for _process_single_account helper function."""

    @patch('parallel_executor.get_connector')
    def test_success_returns_data(self, mock_get_connector):
        """Successful account processing returns data dict."""
        mock_connector = MagicMock()
        mock_connector.authenticate.return_value = {'access_token': 'tok'}
        mock_connector.get_cost_data.return_value = {
            'cost_by_service': [{'service': 'EC2', 'cost_usd': 100.0}],
            'daily_cost_trend': [{'date': '2024-01-01', 'cost_usd': 10.0}],
            'provider': 'aws',
            'error': None,
        }
        mock_get_connector.return_value = mock_connector

        result = _process_single_account(
            ('123456789012', 'aws', FAKE_AWS_CREDS),
            'What is my total spend?'
        )

        assert result['accountId'] == '123456789012'
        assert result['provider'] == 'aws'
        assert 'data' in result
        assert 'error' not in result
        assert result['data']['cost_by_service'][0]['service'] == 'EC2'

    @patch('parallel_executor.get_connector')
    def test_no_connector_returns_error(self, mock_get_connector):
        """Missing connector returns error."""
        mock_get_connector.return_value = None

        result = _process_single_account(
            ('sub-uuid-123', 'azure', FAKE_AZURE_CREDS),
            'How much am I spending?'
        )

        assert result['accountId'] == 'sub-uuid-123'
        assert result['provider'] == 'azure'
        assert 'error' in result
        assert 'No connector available' in result['error']

    @patch('parallel_executor.get_connector')
    def test_auth_failure_returns_error(self, mock_get_connector):
        """Authentication failure returns error with details."""
        from connectors.base_connector import AuthenticationError as AuthErr
        mock_connector = MagicMock()
        mock_connector.authenticate.side_effect = AuthErr(
            'Invalid credentials', provider='azure'
        )
        mock_get_connector.return_value = mock_connector

        result = _process_single_account(
            ('sub-uuid-123', 'azure', FAKE_AZURE_CREDS),
            'Cost breakdown?'
        )

        assert result['accountId'] == 'sub-uuid-123'
        assert result['provider'] == 'azure'
        assert 'error' in result
        assert 'Authentication failed' in result['error']

    @patch('parallel_executor.get_connector')
    def test_generic_exception_returns_error(self, mock_get_connector):
        """Unhandled exceptions are caught and returned as errors."""
        mock_connector = MagicMock()
        mock_connector.authenticate.return_value = {'access_token': 'tok'}
        mock_connector.get_cost_data.side_effect = RuntimeError('Network timeout')
        mock_get_connector.return_value = mock_connector

        result = _process_single_account(
            ('my-gcp-proj', 'gcp', FAKE_GCP_CREDS),
            'GCP costs?'
        )

        assert result['accountId'] == 'my-gcp-proj'
        assert result['provider'] == 'gcp'
        assert 'error' in result
        assert 'RuntimeError' in result['error']
        assert 'Network timeout' in result['error']


class TestGatherMultiAccountParallel:
    """Tests for _gather_multi_account_parallel function."""

    def test_empty_configs_returns_empty_results(self):
        """Empty account list returns empty results dict."""
        result = _gather_multi_account_parallel([], 'What is my spend?')

        assert result['accounts'] == {}
        assert result['failedAccounts'] == []
        assert result['totalAccounts'] == 0
        assert result['successfulAccounts'] == 0

    @patch('parallel_executor.get_connector')
    def test_single_successful_account(self, mock_get_connector):
        """Single successful account returns its data."""
        mock_connector = MagicMock()
        mock_connector.authenticate.return_value = {'access_token': 'tok'}
        mock_connector.get_cost_data.return_value = {
            'cost_by_service': [{'service': 'S3', 'cost_usd': 50.0}],
            'daily_cost_trend': [],
            'provider': 'aws',
            'error': None,
        }
        mock_get_connector.return_value = mock_connector

        configs = [('123456789012', 'aws', FAKE_AWS_CREDS)]
        result = _gather_multi_account_parallel(configs, 'S3 costs?')

        assert '123456789012' in result['accounts']
        assert result['accounts']['123456789012']['provider'] == 'aws'
        assert result['failedAccounts'] == []
        assert result['totalAccounts'] == 1
        assert result['successfulAccounts'] == 1

    @patch('parallel_executor.get_connector')
    def test_mixed_success_and_failure(self, mock_get_connector):
        """Partial failure: successful accounts returned, failed ones tracked."""
        from connectors.base_connector import AuthenticationError as AuthErr

        def connector_factory(provider):
            connector = MagicMock()
            if provider == 'aws':
                connector.authenticate.return_value = {'AccessKeyId': 'k'}
                connector.get_cost_data.return_value = {
                    'cost_by_service': [{'service': 'EC2', 'cost_usd': 200.0}],
                    'daily_cost_trend': [],
                    'provider': 'aws',
                    'error': None,
                }
            elif provider == 'azure':
                connector.authenticate.side_effect = AuthErr(
                    'Bad credentials', provider='azure'
                )
            return connector

        mock_get_connector.side_effect = connector_factory

        configs = [
            ('123456789012', 'aws', FAKE_AWS_CREDS),
            ('sub-uuid-123', 'azure', FAKE_AZURE_CREDS),
        ]
        result = _gather_multi_account_parallel(configs, 'Total costs?')

        # AWS should succeed
        assert '123456789012' in result['accounts']
        # Azure should fail
        assert len(result['failedAccounts']) == 1
        assert result['failedAccounts'][0]['accountId'] == 'sub-uuid-123'
        assert result['failedAccounts'][0]['provider'] == 'azure'
        assert 'Authentication failed' in result['failedAccounts'][0]['error']
        assert result['totalAccounts'] == 2
        assert result['successfulAccounts'] == 1

    @patch('parallel_executor.get_connector')
    def test_all_accounts_fail(self, mock_get_connector):
        """All accounts failing returns empty accounts with all in failedAccounts."""
        mock_connector = MagicMock()
        mock_connector.authenticate.side_effect = Exception('Connection refused')
        mock_get_connector.return_value = mock_connector

        configs = [
            ('123456789012', 'aws', FAKE_AWS_CREDS),
            ('sub-uuid-123', 'azure', FAKE_AZURE_CREDS),
            ('my-gcp-proj', 'gcp', FAKE_GCP_CREDS),
        ]
        result = _gather_multi_account_parallel(configs, 'All costs?')

        assert result['accounts'] == {}
        assert len(result['failedAccounts']) == 3
        assert result['totalAccounts'] == 3
        assert result['successfulAccounts'] == 0

    @patch('parallel_executor.get_connector')
    def test_multi_provider_concurrent_processing(self, mock_get_connector):
        """Multiple providers processed concurrently, each routed independently."""
        def connector_factory(provider):
            connector = MagicMock()
            connector.authenticate.return_value = {'access_token': f'tok-{provider}'}
            connector.get_cost_data.return_value = {
                'cost_by_service': [{'service': f'{provider}-svc', 'cost_usd': 100.0}],
                'daily_cost_trend': [{'date': '2024-01-01', 'cost_usd': 10.0}],
                'provider': provider,
                'error': None,
            }
            return connector

        mock_get_connector.side_effect = connector_factory

        configs = [
            ('123456789012', 'aws', FAKE_AWS_CREDS),
            ('sub-uuid-123', 'azure', FAKE_AZURE_CREDS),
            ('my-gcp-proj', 'gcp', FAKE_GCP_CREDS),
        ]
        result = _gather_multi_account_parallel(configs, 'All cloud costs?')

        assert result['successfulAccounts'] == 3
        assert result['totalAccounts'] == 3
        assert result['failedAccounts'] == []
        assert '123456789012' in result['accounts']
        assert 'sub-uuid-123' in result['accounts']
        assert 'my-gcp-proj' in result['accounts']

    @patch('parallel_executor.get_connector')
    def test_failed_accounts_have_correct_structure(self, mock_get_connector):
        """Requirement 12.2: failed accounts include accountId, provider, error."""
        mock_connector = MagicMock()
        mock_connector.authenticate.side_effect = RuntimeError('Network error')
        mock_get_connector.return_value = mock_connector

        configs = [('sub-uuid-123', 'azure', FAKE_AZURE_CREDS)]
        result = _gather_multi_account_parallel(configs, 'Costs?')

        assert len(result['failedAccounts']) == 1
        failed = result['failedAccounts'][0]
        assert 'accountId' in failed
        assert 'provider' in failed
        assert 'error' in failed
        assert failed['accountId'] == 'sub-uuid-123'
        assert failed['provider'] == 'azure'
        assert isinstance(failed['error'], str)
        assert len(failed['error']) > 0
