"""Unit tests for provider_router.py — Cloud Provider Router."""
import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from provider_router import _route_to_connector, _extract_credentials, DEFAULT_PROVIDER


class TestRouteToConnector:
    """Tests for _route_to_connector function."""

    @patch('provider_router.boto3')
    def test_aws_account_returns_aws_provider(self, mock_boto3):
        """WHEN cloudProvider is 'aws', THEN returns ('aws', aws_credentials)."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': '123456789012',
                'cloudProvider': 'aws',
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('123456789012', 'user@example.com')

        assert provider == 'aws'
        assert creds['account_id'] == '123456789012'
        assert creds['member_email'] == 'user@example.com'

    @patch('provider_router.boto3')
    def test_azure_account_returns_azure_provider(self, mock_boto3):
        """WHEN cloudProvider is 'azure', THEN returns ('azure', azure_credentials)."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': 'aaaabbbb-cccc-dddd-eeee-ffffffffffff',
                'cloudProvider': 'azure',
                'credentials': {
                    'tenantId': 'tenant-123',
                    'clientId': 'client-456',
                    'encryptedClientSecret': 'enc-secret-789',
                },
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('aaaabbbb-cccc-dddd-eeee-ffffffffffff', 'user@example.com')

        assert provider == 'azure'
        assert creds['tenant_id'] == 'tenant-123'
        assert creds['client_id'] == 'client-456'
        assert creds['encrypted_client_secret'] == 'enc-secret-789'

    @patch('provider_router.boto3')
    def test_gcp_account_returns_gcp_provider(self, mock_boto3):
        """WHEN cloudProvider is 'gcp', THEN returns ('gcp', gcp_credentials)."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': 'my-gcp-project',
                'cloudProvider': 'gcp',
                'credentials': {
                    'clientEmail': 'sa@project.iam.gserviceaccount.com',
                    'projectId': 'my-gcp-project',
                    'privateKeyId': 'key-id-123',
                    'encryptedPrivateKey': 'enc-private-key',
                },
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('my-gcp-project', 'user@example.com')

        assert provider == 'gcp'
        assert creds['client_email'] == 'sa@project.iam.gserviceaccount.com'
        assert creds['project_id'] == 'my-gcp-project'
        assert creds['private_key_id'] == 'key-id-123'
        assert creds['encrypted_private_key'] == 'enc-private-key'

    @patch('provider_router.boto3')
    def test_missing_cloud_provider_defaults_to_aws(self, mock_boto3):
        """IF cloudProvider is missing, THEN defaults to 'aws'."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': '123456789012',
                # No cloudProvider field
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('123456789012', 'user@example.com')

        assert provider == 'aws'
        assert creds['account_id'] == '123456789012'

    @patch('provider_router.boto3')
    def test_empty_cloud_provider_defaults_to_aws(self, mock_boto3):
        """IF cloudProvider is empty string, THEN defaults to 'aws'."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': '123456789012',
                'cloudProvider': '',
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('123456789012', 'user@example.com')

        assert provider == 'aws'

    @patch('provider_router.boto3')
    def test_none_cloud_provider_defaults_to_aws(self, mock_boto3):
        """IF cloudProvider is None, THEN defaults to 'aws'."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': '123456789012',
                'cloudProvider': None,
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('123456789012', 'user@example.com')

        assert provider == 'aws'

    @patch('provider_router.boto3')
    def test_account_not_found_raises_value_error(self, mock_boto3):
        """WHEN account does not exist, THEN raises ValueError."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No 'Item' key
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with pytest.raises(ValueError, match="not found"):
            _route_to_connector('123456789012', 'user@example.com')

    @patch('provider_router.boto3')
    def test_dynamodb_error_raises_runtime_error(self, mock_boto3):
        """WHEN DynamoDB read fails, THEN raises RuntimeError."""
        from botocore.exceptions import ClientError
        mock_table = MagicMock()
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DDB failure'}},
            'GetItem'
        )
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with pytest.raises(RuntimeError, match="Failed to read account record"):
            _route_to_connector('123456789012', 'user@example.com')

    @patch('provider_router.boto3')
    def test_unsupported_provider_defaults_to_aws(self, mock_boto3):
        """IF cloudProvider is an unsupported value, THEN defaults to 'aws'."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': '123456789012',
                'cloudProvider': 'oracle',
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('123456789012', 'user@example.com')

        assert provider == 'aws'

    @patch('provider_router.boto3')
    def test_openai_account_returns_openai_provider(self, mock_boto3):
        """WHEN cloudProvider is 'openai', THEN returns ('openai', openai_credentials)."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'memberEmail': 'user@example.com',
                'accountId': 'openai-org-abc123',
                'cloudProvider': 'openai',
                'credentials': {
                    'encryptedApiKey': 'enc-api-key-ciphertext',
                },
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        provider, creds = _route_to_connector('openai-org-abc123', 'user@example.com')

        assert provider == 'openai'
        assert creds['encrypted_api_key'] == 'enc-api-key-ciphertext'


class TestExtractCredentials:
    """Tests for _extract_credentials helper."""

    def test_aws_credentials_include_account_and_email(self):
        """AWS credentials include account_id, member_email, session_name."""
        account = {'accountId': '111222333444'}
        creds = _extract_credentials('aws', account, 'user@test.com')

        assert creds == {
            'account_id': '111222333444',
            'member_email': 'user@test.com',
            'session_name': 'SlashMyBillAIChat',
        }

    def test_azure_credentials_from_stored_credentials(self):
        """Azure credentials extracted from 'credentials' map in account item."""
        account = {
            'accountId': 'sub-uuid',
            'credentials': {
                'tenantId': 't-1',
                'clientId': 'c-2',
                'encryptedClientSecret': 'secret-3',
            }
        }
        creds = _extract_credentials('azure', account, 'user@test.com')

        assert creds == {
            'tenant_id': 't-1',
            'client_id': 'c-2',
            'encrypted_client_secret': 'secret-3',
        }

    def test_azure_missing_credentials_returns_empty_strings(self):
        """Azure with no credentials map returns empty string defaults."""
        account = {'accountId': 'sub-uuid'}
        creds = _extract_credentials('azure', account, 'user@test.com')

        assert creds == {
            'tenant_id': '',
            'client_id': '',
            'encrypted_client_secret': '',
        }

    def test_gcp_credentials_from_stored_credentials(self):
        """GCP credentials extracted from 'credentials' map in account item."""
        account = {
            'accountId': 'my-project',
            'credentials': {
                'clientEmail': 'sa@proj.iam.gserviceaccount.com',
                'projectId': 'my-project',
                'privateKeyId': 'pk-id',
                'encryptedPrivateKey': 'enc-pk',
            }
        }
        creds = _extract_credentials('gcp', account, 'user@test.com')

        assert creds == {
            'client_email': 'sa@proj.iam.gserviceaccount.com',
            'project_id': 'my-project',
            'private_key_id': 'pk-id',
            'encrypted_private_key': 'enc-pk',
        }

    def test_gcp_missing_credentials_returns_empty_strings(self):
        """GCP with no credentials map returns empty string defaults."""
        account = {'accountId': 'my-project'}
        creds = _extract_credentials('gcp', account, 'user@test.com')

        assert creds == {
            'client_email': '',
            'project_id': '',
            'private_key_id': '',
            'encrypted_private_key': '',
        }

    def test_openai_credentials_from_stored_credentials(self):
        """OpenAI credentials extracted from 'credentials' map in account item."""
        account = {
            'accountId': 'openai-org-abc123',
            'credentials': {
                'encryptedApiKey': 'enc-api-key-ciphertext',
            }
        }
        creds = _extract_credentials('openai', account, 'user@test.com')

        assert creds == {
            'encrypted_api_key': 'enc-api-key-ciphertext',
        }

    def test_openai_missing_credentials_returns_empty_string(self):
        """OpenAI with no credentials map returns empty string default."""
        account = {'accountId': 'openai-org-abc123'}
        creds = _extract_credentials('openai', account, 'user@test.com')

        assert creds == {
            'encrypted_api_key': '',
        }
