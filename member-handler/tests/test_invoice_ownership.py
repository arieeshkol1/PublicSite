"""Unit tests for invoice route account ownership verification.

Tests that all four invoice endpoints enforce account ownership before
returning any data, returning 403 when the account doesn't belong to the
authenticated member.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import json
import re
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add parent directory to path so we can import lambda_function
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Helper to build API Gateway v2 events ────────────────────────────────────

def _make_get_event(route_key, query_params=None, token='Bearer valid-token'):
    """Build a minimal API Gateway v2 GET event."""
    return {
        'routeKey': route_key,
        'headers': {'authorization': token},
        'queryStringParameters': query_params or {},
        'body': None,
    }


def _make_post_event(route_key, body=None, token='Bearer valid-token'):
    """Build a minimal API Gateway v2 POST event."""
    return {
        'routeKey': route_key,
        'headers': {'authorization': token},
        'queryStringParameters': {},
        'body': json.dumps(body or {}),
    }


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestInvoiceOwnershipEnforcement:
    """All four invoice endpoints must verify account ownership."""

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_get_invoices_returns_403_when_not_owner(self, mock_validate, mock_dynamodb):
        """GET /members/invoices returns 403 when account not owned by member."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        # Mock DynamoDB to return no accounts for this member
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_get_event('GET /members/invoices', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices(event)

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'
        assert '123456789012' in body['message']

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_refresh_invoices_returns_403_when_not_owner(self, mock_validate, mock_dynamodb):
        """POST /members/invoices/refresh returns 403 when account not owned."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_post_event('POST /members/invoices/refresh', body={'accountId': '123456789012', 'months': ['2024-01']})
        response = lambda_function.handle_refresh_invoices(event)

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'
        assert '123456789012' in body['message']

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_get_summary_returns_403_when_not_owner(self, mock_validate, mock_dynamodb):
        """GET /members/invoices/summary returns 403 when account not owned."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_get_event('GET /members/invoices/summary', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices_summary(event)

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'
        assert '123456789012' in body['message']

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_get_services_returns_403_when_not_owner(self, mock_validate, mock_dynamodb):
        """GET /members/invoices/services returns 403 when account not owned."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_get_event('GET /members/invoices/services', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices_services(event)

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'
        assert '123456789012' in body['message']

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_get_invoices_succeeds_when_owner(self, mock_validate, mock_dynamodb):
        """GET /members/invoices returns 200 when account is owned by member."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        # Mock DynamoDB to return the account as owned
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': [{'accountId': '123456789012'}]}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_get_event('GET /members/invoices', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices(event)

        assert response['statusCode'] == 200

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_get_services_succeeds_when_owner(self, mock_validate, mock_dynamodb):
        """GET /members/invoices/services returns 200 when account is owned."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': [{'accountId': '123456789012'}]}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_get_event('GET /members/invoices/services', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices_services(event)

        assert response['statusCode'] == 200


class TestInvoiceMissingAccountId:
    """Invoice endpoints return 400 when accountId is missing."""

    @patch('lambda_function.validate_token')
    def test_get_invoices_missing_account_id(self, mock_validate):
        """GET /members/invoices without accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_get_event('GET /members/invoices', query_params={})
        response = lambda_function.handle_get_invoices(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'accountId' in body['message'].lower() or 'accountid' in body['message'].lower()

    @patch('lambda_function.validate_token')
    def test_refresh_invoices_missing_account_id(self, mock_validate):
        """POST /members/invoices/refresh without accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_post_event('POST /members/invoices/refresh', body={})
        response = lambda_function.handle_refresh_invoices(event)

        assert response['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_get_summary_missing_account_id(self, mock_validate):
        """GET /members/invoices/summary without accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_get_event('GET /members/invoices/summary', query_params={})
        response = lambda_function.handle_get_invoices_summary(event)

        assert response['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_get_services_missing_account_id(self, mock_validate):
        """GET /members/invoices/services without accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_get_event('GET /members/invoices/services', query_params={})
        response = lambda_function.handle_get_invoices_services(event)

        assert response['statusCode'] == 400


class TestInvoiceInvalidAccountIdFormat:
    """Invoice endpoints return 400 for invalid accountId format."""

    @patch('lambda_function.validate_token')
    def test_get_invoices_invalid_account_id(self, mock_validate):
        """GET /members/invoices with non-12-digit accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_get_event('GET /members/invoices', query_params={'accountId': '12345'})
        response = lambda_function.handle_get_invoices(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert '12-digit' in body['message'] or '12 digit' in body['message']

    @patch('lambda_function.validate_token')
    def test_refresh_invoices_invalid_account_id(self, mock_validate):
        """POST /members/invoices/refresh with non-12-digit accountId returns 400."""
        import lambda_function

        mock_validate.return_value = {'sub': 'member@example.com', 'role': 'member'}

        event = _make_post_event('POST /members/invoices/refresh', body={'accountId': 'abc'})
        response = lambda_function.handle_refresh_invoices(event)

        assert response['statusCode'] == 400


class TestInvoiceAuthRequired:
    """Invoice endpoints require valid authentication."""

    @patch('lambda_function.validate_token')
    def test_get_invoices_returns_401_without_auth(self, mock_validate):
        """GET /members/invoices returns 401 when token is invalid."""
        import lambda_function

        mock_validate.return_value = {
            'statusCode': 401,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'AuthError', 'message': 'Authentication required', 'code': 401}),
        }

        event = _make_get_event('GET /members/invoices', query_params={'accountId': '123456789012'})
        response = lambda_function.handle_get_invoices(event)

        assert response['statusCode'] == 401
