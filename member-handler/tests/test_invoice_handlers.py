"""Unit tests for invoice summary, services, and refresh handlers (tasks 6.1, 6.4, 6.6)."""

import json
import sys
import os
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required env vars before import
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('INVOICES_TABLE_NAME', 'MemberPortal-Invoices')

import lambda_function


def _make_event(route_key, qs=None, body=None, token='valid-token'):
    """Create a mock API Gateway event."""
    event = {
        'routeKey': route_key,
        'headers': {'authorization': f'Bearer {token}'},
        'queryStringParameters': qs or {},
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


def _make_invoice_item(service='Amazon EC2', cost=10.50, month='2025-01'):
    """Create a mock DynamoDB invoice item."""
    return {
        'pk': 'test@example.com#123456789012',
        'sk': f'{month}#{service}',
        'memberEmail': 'test@example.com',
        'accountId': '123456789012',
        'month': month,
        'service': service,
        'cost': Decimal(str(cost)),
        'currency': 'USD',
        'usageTypes': [],
        'dailyCosts': {},
        'region': 'us-east-1',
        'lastSyncedAt': '2025-01-15T10:00:00+00:00',
        'ttl': 1713000000,
    }


class TestGetInvoicesSummary:
    """Tests for handle_get_invoices_summary."""

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_returns_zeros_when_no_data(self, mock_validate, mock_dynamodb):
        """When no invoice items exist, returns zero totals and empty lists."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        # Mock _verify_account_ownership to return True
        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['totalCost'] == 0
        assert body['monthOverMonthChange'] == 0
        assert body['topServices'] == []
        assert body['topService'] is None

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_calculates_total_cost_for_current_month(self, mock_validate, mock_dynamodb):
        """totalCost is the sum of all item costs for the current month."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        now = datetime.now(timezone.utc)
        current_month = now.strftime('%Y-%m')

        items = [
            _make_invoice_item(service='Amazon EC2', cost=100.50, month=current_month),
            _make_invoice_item(service='Amazon S3', cost=25.75, month=current_month),
            _make_invoice_item(service='Amazon RDS', cost=50.00, month=current_month),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['totalCost'] == 176.25
        assert body['serviceCount'] == 3

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_month_over_month_change_calculation(self, mock_validate, mock_dynamodb):
        """MoM change is ((current - previous) / previous * 100) rounded to 1 decimal."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        now = datetime.now(timezone.utc)
        current_month = now.strftime('%Y-%m')
        if now.month == 1:
            prev_month = f'{now.year - 1}-12'
        else:
            prev_month = f'{now.year}-{now.month - 1:02d}'

        items = [
            _make_invoice_item(service='Amazon EC2', cost=150.00, month=current_month),
            _make_invoice_item(service='Amazon EC2', cost=100.00, month=prev_month),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        # ((150 - 100) / 100) * 100 = 50.0%
        assert body['monthOverMonthChange'] == 50.0

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_mom_returns_zero_when_previous_month_has_no_data(self, mock_validate, mock_dynamodb):
        """MoM returns 0 when previous month has no data."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        now = datetime.now(timezone.utc)
        current_month = now.strftime('%Y-%m')

        items = [
            _make_invoice_item(service='Amazon EC2', cost=150.00, month=current_month),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        assert body['monthOverMonthChange'] == 0

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_mom_returns_zero_when_previous_month_total_is_zero(self, mock_validate, mock_dynamodb):
        """MoM returns 0 when previous month total is zero."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        now = datetime.now(timezone.utc)
        current_month = now.strftime('%Y-%m')
        if now.month == 1:
            prev_month = f'{now.year - 1}-12'
        else:
            prev_month = f'{now.year}-{now.month - 1:02d}'

        items = [
            _make_invoice_item(service='Amazon EC2', cost=150.00, month=current_month),
            _make_invoice_item(service='Amazon EC2', cost=0.00, month=prev_month),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        assert body['monthOverMonthChange'] == 0

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_top_5_services_by_spend(self, mock_validate, mock_dynamodb):
        """Returns top 5 services ranked by cost with percentage of total."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        now = datetime.now(timezone.utc)
        current_month = now.strftime('%Y-%m')

        items = [
            _make_invoice_item(service='Amazon EC2', cost=200.00, month=current_month),
            _make_invoice_item(service='Amazon S3', cost=100.00, month=current_month),
            _make_invoice_item(service='Amazon RDS', cost=80.00, month=current_month),
            _make_invoice_item(service='AWS Lambda', cost=50.00, month=current_month),
            _make_invoice_item(service='Amazon DynamoDB', cost=40.00, month=current_month),
            _make_invoice_item(service='Amazon CloudFront', cost=30.00, month=current_month),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/summary',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_summary(event)
            body = json.loads(result['body'])

        assert len(body['topServices']) == 5
        assert body['topServices'][0]['name'] == 'Amazon EC2'
        assert body['topServices'][0]['cost'] == 200.00
        # Total is 500, EC2 is 200 => 40.0%
        assert body['topServices'][0]['percentage'] == 40.0
        assert body['topServices'][4]['name'] == 'Amazon DynamoDB'

    @patch('lambda_function.validate_token')
    def test_missing_account_id_returns_400(self, mock_validate):
        """Returns 400 when accountId is missing."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        event = _make_event('GET /members/invoices/summary', qs={})
        result = lambda_function.handle_get_invoices_summary(event)

        assert result['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_invalid_account_id_returns_400(self, mock_validate):
        """Returns 400 when accountId is not 12 digits."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        event = _make_event(
            'GET /members/invoices/summary',
            qs={'accountId': 'invalid'}
        )
        result = lambda_function.handle_get_invoices_summary(event)

        assert result['statusCode'] == 400


class TestGetInvoicesServices:
    """Tests for handle_get_invoices_services."""

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_returns_empty_list_when_no_records(self, mock_validate, mock_dynamodb):
        """Returns empty list with 200 when no records exist."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/services',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_services(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['services'] == []

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_returns_distinct_services_sorted_alphabetically(self, mock_validate, mock_dynamodb):
        """Returns distinct service names sorted in ascending alphabetical order."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        items = [
            {'service': 'Amazon S3'},
            {'service': 'Amazon EC2'},
            {'service': 'Amazon EC2'},  # duplicate
            {'service': 'AWS Lambda'},
            {'service': 'Amazon DynamoDB'},
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': items}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'GET /members/invoices/services',
                qs={'accountId': '123456789012'}
            )
            result = lambda_function.handle_get_invoices_services(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['services'] == [
            'AWS Lambda',
            'Amazon DynamoDB',
            'Amazon EC2',
            'Amazon S3',
        ]

    @patch('lambda_function.validate_token')
    def test_missing_account_id_returns_400(self, mock_validate):
        """Returns 400 when accountId is missing."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        event = _make_event('GET /members/invoices/services', qs={})
        result = lambda_function.handle_get_invoices_services(event)

        assert result['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_invalid_account_id_returns_400(self, mock_validate):
        """Returns 400 when accountId is not 12 digits."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        event = _make_event(
            'GET /members/invoices/services',
            qs={'accountId': 'abc'}
        )
        result = lambda_function.handle_get_invoices_services(event)

        assert result['statusCode'] == 400

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_ownership_check_returns_403(self, mock_validate, mock_dynamodb):
        """Returns 403 when account doesn't belong to member."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        # Mock DynamoDB to return no accounts for this member (ownership check fails)
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        event = _make_event(
            'GET /members/invoices/services',
            qs={'accountId': '999999999999'}
        )
        result = lambda_function.handle_get_invoices_services(event)

        assert result['statusCode'] == 403


class TestRefreshInvoices:
    """Tests for handle_refresh_invoices."""

    @patch('invoice_sync.sync_invoice_data')
    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_successful_refresh(self, mock_validate, mock_dynamodb, mock_sync):
        """Successful refresh returns 200 with synced months and record count."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}
        mock_sync.return_value = {
            'synced_months': ['2025-01'],
            'record_count': 5,
            'total_cost': 150.00,
        }

        mock_table = MagicMock()
        # No rate limit record
        mock_table.get_item.return_value = {}
        # No existing records to delete
        mock_table.query.return_value = {'Items': []}
        mock_table.batch_writer.return_value.__enter__ = MagicMock()
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_table.put_item.return_value = {}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': ['2025-01']}
            )
            result = lambda_function.handle_refresh_invoices(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['refreshed'] is True
        assert body['months'] == ['2025-01']
        assert body['recordCount'] == 5

    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_rate_limited_returns_429(self, mock_validate, mock_dynamodb):
        """Returns 429 with cooldown seconds when rate limited."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        # Rate limit record exists — refreshed 60 seconds ago
        now_epoch = int(time.time())
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'lastRefreshAt': now_epoch - 60}
        }
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': ['2025-01']}
            )
            result = lambda_function.handle_refresh_invoices(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 429
        assert 'cooldownRemaining' in body
        # Should be approximately 240 seconds remaining (300 - 60)
        assert 230 <= body['cooldownRemaining'] <= 250

    @patch('lambda_function.validate_token')
    def test_max_6_months_validation(self, mock_validate):
        """Returns 400 when more than 6 months are requested."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={
                    'accountId': '123456789012',
                    'months': ['2025-01', '2025-02', '2025-03', '2025-04',
                               '2025-05', '2025-06', '2025-07']
                }
            )
            result = lambda_function.handle_refresh_invoices(event)

        assert result['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_empty_months_returns_400(self, mock_validate):
        """Returns 400 when months array is empty."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': []}
            )
            result = lambda_function.handle_refresh_invoices(event)

        assert result['statusCode'] == 400

    @patch('lambda_function.validate_token')
    def test_missing_account_id_returns_400(self, mock_validate):
        """Returns 400 when accountId is missing."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        event = _make_event(
            'POST /members/invoices/refresh',
            body={'months': ['2025-01']}
        )
        result = lambda_function.handle_refresh_invoices(event)

        assert result['statusCode'] == 400

    @patch('invoice_sync.sync_invoice_data')
    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_sync_error_returns_error_response(self, mock_validate, mock_dynamodb, mock_sync):
        """On sync failure, returns error response."""
        from invoice_sync import InvoiceSyncError
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}
        mock_sync.side_effect = InvoiceSyncError(
            'Cost Explorer not enabled', status_code=400, error_type='CostExplorerNotEnabled'
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.query.return_value = {'Items': []}
        mock_table.batch_writer.return_value.__enter__ = MagicMock()
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': ['2025-01']}
            )
            result = lambda_function.handle_refresh_invoices(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Cost Explorer' in body['message']

    @patch('lambda_function.validate_token')
    def test_invalid_month_format_returns_400(self, mock_validate):
        """Returns 400 when month format is invalid."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': ['invalid-month']}
            )
            result = lambda_function.handle_refresh_invoices(event)

        assert result['statusCode'] == 400

    @patch('invoice_sync.sync_invoice_data')
    @patch('lambda_function.dynamodb')
    @patch('lambda_function.validate_token')
    def test_refresh_after_cooldown_succeeds(self, mock_validate, mock_dynamodb, mock_sync):
        """Refresh succeeds when cooldown period has elapsed."""
        mock_validate.return_value = {'sub': 'test@example.com', 'role': 'member'}
        mock_sync.return_value = {
            'synced_months': ['2025-01'],
            'record_count': 3,
            'total_cost': 75.00,
        }

        # Rate limit record exists but expired (refreshed 6 minutes ago)
        now_epoch = int(time.time())
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'lastRefreshAt': now_epoch - 360}
        }
        mock_table.query.return_value = {'Items': []}
        mock_table.batch_writer.return_value.__enter__ = MagicMock()
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        mock_table.put_item.return_value = {}
        mock_dynamodb.Table.return_value = mock_table

        with patch('lambda_function._verify_account_ownership', return_value=True):
            event = _make_event(
                'POST /members/invoices/refresh',
                body={'accountId': '123456789012', 'months': ['2025-01']}
            )
            result = lambda_function.handle_refresh_invoices(event)
            body = json.loads(result['body'])

        assert result['statusCode'] == 200
        assert body['refreshed'] is True
