"""Unit tests for handle_add_openai route handler."""
import json
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

# Add parent directory to path so we can import lambda_function
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_event(body=None, token='Bearer valid-token'):
    """Helper to build a mock API Gateway event."""
    event = {
        'routeKey': 'POST /members/accounts/add-openai',
        'headers': {'authorization': token},
        'body': json.dumps(body) if body else '{}',
    }
    return event


def _mock_validate_token_success(event):
    """Mock validate_token returning a valid member."""
    return {'sub': 'user@example.com', 'role': 'member'}


def _mock_validate_token_failure(event):
    """Mock validate_token returning an auth error."""
    return {'statusCode': 401, 'headers': {}, 'body': json.dumps({'error': 'AuthError'})}


class TestHandleAddOpenaiValidation:
    """Test input validation in handle_add_openai."""

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    def test_missing_api_key_returns_400(self, mock_token):
        from lambda_function import handle_add_openai
        event = _make_event(body={'connectionName': 'My OpenAI'})
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidKeyFormat'

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    def test_empty_api_key_returns_400(self, mock_token):
        from lambda_function import handle_add_openai
        event = _make_event(body={'apiKey': '', 'connectionName': 'Test'})
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidKeyFormat'

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    def test_invalid_format_api_key_returns_400(self, mock_token):
        from lambda_function import handle_add_openai
        event = _make_event(body={'apiKey': 'invalid-key-format'})
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidKeyFormat'

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    def test_connection_name_too_long_returns_400(self, mock_token):
        from lambda_function import handle_add_openai
        event = _make_event(body={
            'apiKey': 'sk-org-' + 'a' * 50,
            'connectionName': 'x' * 65
        })
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert '64' in body['message']

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_failure)
    def test_unauthenticated_returns_401(self, mock_token):
        from lambda_function import handle_add_openai
        event = _make_event(body={'apiKey': 'sk-org-' + 'a' * 50})
        result = handle_add_openai(event)
        assert result['statusCode'] == 401

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    def test_invalid_json_body_returns_400(self, mock_token):
        from lambda_function import handle_add_openai
        event = {
            'routeKey': 'POST /members/accounts/add-openai',
            'headers': {'authorization': 'Bearer valid-token'},
            'body': 'not-json{{{',
        }
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'


class TestHandleAddOpenaiConnectionTest:
    """Test the OpenAI connection test step."""

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    def test_connection_test_failure_returns_400(self, mock_test, mock_token):
        from lambda_function import handle_add_openai
        mock_test.return_value = {
            'success': False,
            'message': 'API key is invalid or has been revoked.',
            'details': {'status_code': 401}
        }
        event = _make_event(body={'apiKey': 'sk-org-' + 'a' * 50})
        result = handle_add_openai(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'ConnectionFailed'
        assert 'invalid' in body['message'].lower() or 'revoked' in body['message'].lower()


class TestHandleAddOpenaiSuccess:
    """Test successful OpenAI account creation."""

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    @patch('connectors.openai_kms.encrypt_openai_key')
    @patch('lambda_function.dynamodb')
    def test_success_returns_201_with_account(self, mock_dynamo, mock_encrypt,
                                              mock_test, mock_token):
        from lambda_function import handle_add_openai

        mock_test.return_value = {
            'success': True,
            'message': 'OpenAI connection successful',
            'details': {'models': ['gpt-4', 'gpt-3.5-turbo']}
        }
        mock_encrypt.return_value = 'encrypted-ciphertext-base64'
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        event = _make_event(body={
            'apiKey': 'sk-org-' + 'a' * 50,
            'connectionName': 'My Production OpenAI'
        })
        result = handle_add_openai(event)

        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['account']['cloudProvider'] == 'openai'
        assert body['account']['vendorType'] == 'ai_vendor'
        assert body['account']['connectionStatus'] == 'connected'
        assert body['account']['accountName'] == 'My Production OpenAI'
        assert body['account']['accountId'].startswith('openai-')
        assert 'encryptedApiKey' not in json.dumps(body)  # No credentials in response
        assert body['account']['lastTestedAt'] is not None
        assert body['account']['addedAt'] is not None

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    @patch('connectors.openai_kms.encrypt_openai_key')
    @patch('lambda_function.dynamodb')
    def test_success_without_connection_name_uses_default(self, mock_dynamo, mock_encrypt,
                                                          mock_test, mock_token):
        from lambda_function import handle_add_openai

        mock_test.return_value = {'success': True, 'message': 'OK', 'details': {}}
        mock_encrypt.return_value = 'encrypted-value'
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        event = _make_event(body={'apiKey': 'sk-proj-' + 'b' * 50})
        result = handle_add_openai(event)

        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['account']['accountName'] == 'OpenAI Connection'

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    @patch('connectors.openai_kms.encrypt_openai_key')
    @patch('lambda_function.dynamodb')
    def test_dynamo_record_contains_required_fields(self, mock_dynamo, mock_encrypt,
                                                     mock_test, mock_token):
        from lambda_function import handle_add_openai

        mock_test.return_value = {'success': True, 'message': 'OK', 'details': {}}
        mock_encrypt.return_value = 'enc-key-123'
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        event = _make_event(body={
            'apiKey': 'sk-org-' + 'c' * 50,
            'connectionName': 'Test Conn'
        })
        handle_add_openai(event)

        # Verify DynamoDB put_item was called with correct record
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]['Item']
        assert item['memberEmail'] == 'user@example.com'
        assert item['cloudProvider'] == 'openai'
        assert item['vendorType'] == 'ai_vendor'
        assert item['connectionStatus'] == 'connected'
        assert item['credentials']['encryptedApiKey'] == 'enc-key-123'
        assert item['accountName'] == 'Test Conn'
        assert item['accountId'].startswith('openai-')
        assert len(item['accountId']) == len('openai-') + 12
        assert item['addedAt'] is not None
        assert item['lastTestedAt'] is not None


class TestHandleAddOpenaiErrors:
    """Test error handling in handle_add_openai."""

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    @patch('connectors.openai_kms.encrypt_openai_key')
    def test_encryption_failure_returns_500(self, mock_encrypt, mock_test, mock_token):
        from lambda_function import handle_add_openai
        from connectors.openai_kms import EncryptionError

        mock_test.return_value = {'success': True, 'message': 'OK', 'details': {}}
        mock_encrypt.side_effect = EncryptionError('KMS unavailable')

        event = _make_event(body={'apiKey': 'sk-org-' + 'd' * 50})
        result = handle_add_openai(event)

        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['error'] == 'ServerError'
        assert 'credentials' in body['message'].lower() or 'save' in body['message'].lower()

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    @patch('connectors.openai_kms.encrypt_openai_key')
    @patch('lambda_function.dynamodb')
    def test_dynamo_write_failure_returns_500(self, mock_dynamo, mock_encrypt,
                                              mock_test, mock_token):
        from lambda_function import handle_add_openai
        from botocore.exceptions import ClientError

        mock_test.return_value = {'success': True, 'message': 'OK', 'details': {}}
        mock_encrypt.return_value = 'enc-key'
        mock_table = MagicMock()
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DDB unavailable'}},
            'PutItem'
        )
        mock_dynamo.Table.return_value = mock_table

        event = _make_event(body={'apiKey': 'sk-org-' + 'e' * 50})
        result = handle_add_openai(event)

        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['error'] == 'ServerError'

    @patch('lambda_function.validate_token', side_effect=_mock_validate_token_success)
    @patch('connectors.openai_connector.OpenAIConnector.test_connection')
    def test_failure_reason_truncated_to_200_chars(self, mock_test, mock_token):
        from lambda_function import handle_add_openai

        long_message = 'x' * 500
        mock_test.return_value = {
            'success': False,
            'message': long_message,
            'details': {}
        }

        event = _make_event(body={'apiKey': 'sk-org-' + 'f' * 50})
        result = handle_add_openai(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert len(body['message']) <= 200
