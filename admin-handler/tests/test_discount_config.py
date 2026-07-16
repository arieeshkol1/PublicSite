"""Unit tests for GET/PUT /admin/custom-plans/config endpoints."""
import json
import sys
import os
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory and project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_event(method, route, body=None, token_payload=None):
    """Create a mock API Gateway v2 event."""
    event = {
        'routeKey': f'{method} {route}',
        'headers': {},
    }
    if body is not None:
        event['body'] = json.dumps(body)
    if token_payload:
        event['headers']['authorization'] = 'Bearer valid-token'
    return event


VALID_CONFIG = {
    'baseMonthlyPrice': 275,
    'baseTokenCount': 2500,
    'discountTiers': [
        {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
        {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
        {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
        {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
    ]
}


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set required env vars for imports."""
    monkeypatch.setenv('ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('ADMIN_PASSWORD_HASH', '$2b$12$fake')
    monkeypatch.setenv('JWT_SECRET', 'test-secret')


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB table for discount config."""
    with patch('lambda_function.dynamodb') as mock_db:
        mock_table = MagicMock()
        mock_db.Table.return_value = mock_table
        yield mock_table


@pytest.fixture
def mock_validate_token():
    """Mock validate_token to return admin payload."""
    with patch('lambda_function.validate_token') as mock_vt:
        mock_vt.return_value = {'sub': 'admin@example.com', 'iat': 1000, 'exp': 2000}
        yield mock_vt


class TestGetDiscountConfig:
    """Tests for GET /admin/custom-plans/config."""

    def test_returns_existing_config(self, mock_dynamodb):
        """Should return the ACTIVE config item."""
        from lambda_function import handle_get_discount_config

        mock_dynamodb.get_item.return_value = {
            'Item': {
                'configId': 'ACTIVE',
                'baseMonthlyPrice': Decimal('250'),
                'baseTokenCount': 2000,
                'discountTiers': [
                    {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
                ],
                'updatedAt': '2026-07-01T00:00:00Z',
                'updatedBy': 'admin@example.com',
            }
        }

        event = _make_event('GET', '/admin/custom-plans/config')
        result = handle_get_discount_config(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['config']['baseMonthlyPrice'] == 250
        assert body['config']['baseTokenCount'] == 2000
        assert body['config']['updatedBy'] == 'admin@example.com'

    def test_returns_null_config_when_not_found(self, mock_dynamodb):
        """Should return config: null with message when no config exists."""
        from lambda_function import handle_get_discount_config

        mock_dynamodb.get_item.return_value = {}

        event = _make_event('GET', '/admin/custom-plans/config')
        result = handle_get_discount_config(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['config'] is None
        assert 'message' in body


class TestPutDiscountConfig:
    """Tests for PUT /admin/custom-plans/config."""

    def test_valid_config_update(self, mock_dynamodb, mock_validate_token):
        """Should accept a valid config and store it."""
        from lambda_function import handle_put_discount_config

        mock_dynamodb.put_item.return_value = {}

        event = _make_event('PUT', '/admin/custom-plans/config', body=VALID_CONFIG, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['message'] == 'Discount configuration updated'
        assert 'updatedAt' in body

        # Verify DynamoDB put_item was called with correct data
        call_args = mock_dynamodb.put_item.call_args
        item = call_args[1]['Item'] if 'Item' in (call_args[1] or {}) else call_args[0][0] if call_args[0] else call_args[1]['Item']
        assert item['configId'] == 'ACTIVE'
        assert item['updatedBy'] == 'admin@example.com'

    def test_rejects_base_price_at_200(self, mock_dynamodb, mock_validate_token):
        """Should reject base price that equals 200 (must be greater than)."""
        from lambda_function import handle_put_discount_config

        config = {**VALID_CONFIG, 'baseMonthlyPrice': 200}
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'
        assert 'greater than $200' in body['message']

    def test_rejects_base_price_below_200(self, mock_dynamodb, mock_validate_token):
        """Should reject base price below 200."""
        from lambda_function import handle_put_discount_config

        config = {**VALID_CONFIG, 'baseMonthlyPrice': 150}
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'

    def test_rejects_discount_above_50(self, mock_dynamodb, mock_validate_token):
        """Should reject discount percentages above 50."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 55},
                {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
                {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'
        assert 'between 1 and 50' in body['message']

    def test_rejects_discount_below_1(self, mock_dynamodb, mock_validate_token):
        """Should reject discount percentages below 1."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 0},
                {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
                {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'
        assert 'between 1 and 50' in body['message']

    def test_rejects_gap_in_tier_ranges(self, mock_dynamodb, mock_validate_token):
        """Should reject tier ranges with gaps (e.g., 3-6, 8-12 skips 7)."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
                {'minMonths': 8, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
                {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'
        assert 'without gaps or overlaps' in body['message']

    def test_rejects_overlap_in_tier_ranges(self, mock_dynamodb, mock_validate_token):
        """Should reject tier ranges with overlaps (e.g., 3-6, 6-12)."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
                {'minMonths': 6, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
                {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'
        assert 'without gaps or overlaps' in body['message']

    def test_rejects_tiers_not_starting_at_3(self, mock_dynamodb, mock_validate_token):
        """Should reject tiers that don't start at month 3."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 1, 'maxMonths': 6, 'discountPercent': 5},
                {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
                {'minMonths': 19, 'maxMonths': 24, 'discountPercent': 40},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'

    def test_rejects_tiers_not_ending_at_24(self, mock_dynamodb, mock_validate_token):
        """Should reject tiers that don't end at month 24."""
        from lambda_function import handle_put_discount_config

        config = {
            'baseMonthlyPrice': 275,
            'baseTokenCount': 2500,
            'discountTiers': [
                {'minMonths': 3, 'maxMonths': 6, 'discountPercent': 5},
                {'minMonths': 7, 'maxMonths': 12, 'discountPercent': 15},
                {'minMonths': 13, 'maxMonths': 18, 'discountPercent': 25},
            ]
        }
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'

    def test_rejects_negative_base_token_count(self, mock_dynamodb, mock_validate_token):
        """Should reject negative or zero base token count."""
        from lambda_function import handle_put_discount_config

        config = {**VALID_CONFIG, 'baseTokenCount': 0}
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'

    def test_rejects_empty_discount_tiers(self, mock_dynamodb, mock_validate_token):
        """Should reject empty discount tiers array."""
        from lambda_function import handle_put_discount_config

        config = {**VALID_CONFIG, 'discountTiers': []}
        event = _make_event('PUT', '/admin/custom-plans/config', body=config, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidConfig'

    def test_stores_updated_by_from_jwt(self, mock_dynamodb, mock_validate_token):
        """Should store the admin email from JWT as updatedBy."""
        from lambda_function import handle_put_discount_config

        mock_dynamodb.put_item.return_value = {}
        mock_validate_token.return_value = {'sub': 'boss@company.com', 'iat': 1000, 'exp': 2000}

        event = _make_event('PUT', '/admin/custom-plans/config', body=VALID_CONFIG, token_payload=True)
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 200
        call_kwargs = mock_dynamodb.put_item.call_args[1]
        assert call_kwargs['Item']['updatedBy'] == 'boss@company.com'

    def test_rejects_invalid_json_body(self, mock_dynamodb, mock_validate_token):
        """Should reject invalid JSON in request body."""
        from lambda_function import handle_put_discount_config

        event = {
            'routeKey': 'PUT /admin/custom-plans/config',
            'headers': {'authorization': 'Bearer valid-token'},
            'body': 'not json {{{',
        }
        result = handle_put_discount_config(event)

        assert result['statusCode'] == 400
