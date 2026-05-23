"""Unit tests for invoice list endpoint filtering logic (task 5.1)."""

import json
import sys
import os
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We need to import the filter function directly
# Since _apply_invoice_filters is in lambda_function.py which has heavy dependencies,
# we test it by importing from the module after mocking external deps.


def _make_item(service='Amazon EC2', cost=10.50, month='2024-01',
               usage_types=None, region='us-east-1'):
    """Helper to create a mock invoice item as returned from DynamoDB."""
    if usage_types is None:
        usage_types = [{'type': 'BoxUsage:t3.micro', 'cost': Decimal('10.50'),
                        'unit': 'Hrs', 'quantity': Decimal('720')}]
    return {
        'pk': 'test@example.com#123456789012',
        'sk': f'{month}#{service}',
        'memberEmail': 'test@example.com',
        'accountId': '123456789012',
        'month': month,
        'service': service,
        'cost': Decimal(str(cost)),
        'currency': 'USD',
        'usageTypes': usage_types,
        'dailyCosts': {'01': Decimal('0.35'), '02': Decimal('0.35')},
        'region': region,
        'lastSyncedAt': '2024-01-15T10:00:00+00:00',
        'ttl': 1713000000,
    }


# Import the filter function - we need to mock heavy deps first
with patch.dict('sys.modules', {
    'boto3': MagicMock(),
    'botocore': MagicMock(),
    'botocore.exceptions': MagicMock(),
    'jwt': MagicMock(),
    'bcrypt': MagicMock(),
    'yaml': MagicMock(),
}):
    # Set required env vars before import
    os.environ.setdefault('JWT_SECRET', 'test-secret')
    from lambda_function import _apply_invoice_filters


class TestApplyInvoiceFilters:
    """Tests for _apply_invoice_filters function."""

    def _validated(self, **overrides):
        """Create a validated params dict with defaults."""
        params = {
            'accountId': '123456789012',
            'month': None,
            'service': None,
            'minCost': None,
            'maxCost': None,
            'search': None,
            'page': 1,
            'pageSize': 50,
            'sortBy': 'cost',
            'sortOrder': 'desc',
        }
        params.update(overrides)
        return params

    def test_no_filters_returns_all_items(self):
        items = [_make_item(service='Amazon EC2'), _make_item(service='Amazon S3')]
        result = _apply_invoice_filters(items, self._validated())
        assert len(result) == 2

    def test_service_filter_case_insensitive_exact_match(self):
        items = [
            _make_item(service='Amazon EC2'),
            _make_item(service='Amazon S3'),
            _make_item(service='amazon ec2'),  # different case
        ]
        result = _apply_invoice_filters(items, self._validated(service='amazon ec2'))
        assert len(result) == 2
        for item in result:
            assert item['service'].lower() == 'amazon ec2'

    def test_service_filter_no_match(self):
        items = [_make_item(service='Amazon EC2')]
        result = _apply_invoice_filters(items, self._validated(service='Amazon RDS'))
        assert len(result) == 0

    def test_month_filter_exact_match(self):
        items = [
            _make_item(month='2024-01'),
            _make_item(month='2024-02'),
            _make_item(month='2024-01'),
        ]
        result = _apply_invoice_filters(items, self._validated(month='2024-01'))
        assert len(result) == 2

    def test_min_cost_filter_inclusive(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=10.00),
            _make_item(cost=15.00),
        ]
        result = _apply_invoice_filters(items, self._validated(minCost='10.00'))
        assert len(result) == 2
        for item in result:
            assert float(item['cost']) >= 10.00

    def test_max_cost_filter_inclusive(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=10.00),
            _make_item(cost=15.00),
        ]
        result = _apply_invoice_filters(items, self._validated(maxCost='10.00'))
        assert len(result) == 2
        for item in result:
            assert float(item['cost']) <= 10.00

    def test_cost_range_filter(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=10.00),
            _make_item(cost=15.00),
            _make_item(cost=20.00),
        ]
        result = _apply_invoice_filters(items, self._validated(minCost='10.00', maxCost='15.00'))
        assert len(result) == 2
        for item in result:
            cost = float(item['cost'])
            assert 10.00 <= cost <= 15.00

    def test_cost_filter_two_decimal_precision(self):
        items = [
            _make_item(cost=9.99),
            _make_item(cost=10.00),
            _make_item(cost=10.01),
        ]
        result = _apply_invoice_filters(items, self._validated(minCost='10.00'))
        assert len(result) == 2

    def test_search_on_service_name(self):
        items = [
            _make_item(service='Amazon EC2'),
            _make_item(service='Amazon S3'),
            _make_item(service='AWS Lambda'),
        ]
        result = _apply_invoice_filters(items, self._validated(search='ec2'))
        assert len(result) == 1
        assert result[0]['service'] == 'Amazon EC2'

    def test_search_on_usage_type(self):
        items = [
            _make_item(service='Amazon EC2', usage_types=[
                {'type': 'BoxUsage:t3.micro', 'cost': Decimal('5'), 'unit': 'Hrs', 'quantity': Decimal('100')}
            ]),
            _make_item(service='Amazon S3', usage_types=[
                {'type': 'TimedStorage-ByteHrs', 'cost': Decimal('2'), 'unit': 'GB-Mo', 'quantity': Decimal('50')}
            ]),
        ]
        result = _apply_invoice_filters(items, self._validated(search='BoxUsage'))
        assert len(result) == 1
        assert result[0]['service'] == 'Amazon EC2'

    def test_search_case_insensitive(self):
        items = [
            _make_item(service='Amazon EC2'),
            _make_item(service='Amazon S3'),
        ]
        result = _apply_invoice_filters(items, self._validated(search='AMAZON'))
        assert len(result) == 2

    def test_search_shorter_than_1_char_ignored(self):
        items = [
            _make_item(service='Amazon EC2'),
            _make_item(service='Amazon S3'),
        ]
        # Empty string search should be ignored (return all)
        result = _apply_invoice_filters(items, self._validated(search=''))
        assert len(result) == 2

    def test_search_none_returns_all(self):
        items = [_make_item(), _make_item()]
        result = _apply_invoice_filters(items, self._validated(search=None))
        assert len(result) == 2

    def test_multiple_filters_and_logic(self):
        items = [
            _make_item(service='Amazon EC2', cost=10.00, month='2024-01'),
            _make_item(service='Amazon EC2', cost=5.00, month='2024-01'),
            _make_item(service='Amazon S3', cost=10.00, month='2024-01'),
            _make_item(service='Amazon EC2', cost=10.00, month='2024-02'),
        ]
        result = _apply_invoice_filters(items, self._validated(
            service='Amazon EC2', month='2024-01', minCost='8.00'
        ))
        assert len(result) == 1
        assert result[0]['service'] == 'Amazon EC2'
        assert float(result[0]['cost']) == 10.00
        assert result[0]['month'] == '2024-01'

    def test_empty_items_returns_empty(self):
        result = _apply_invoice_filters([], self._validated())
        assert result == []

    def test_no_matches_returns_empty(self):
        items = [_make_item(service='Amazon EC2')]
        result = _apply_invoice_filters(items, self._validated(service='NonExistent'))
        assert len(result) == 0

    def test_invalid_min_cost_ignored(self):
        items = [_make_item(cost=10.00)]
        # Non-numeric minCost should be ignored (treated as None)
        result = _apply_invoice_filters(items, self._validated(minCost='abc'))
        assert len(result) == 1

    def test_invalid_max_cost_ignored(self):
        items = [_make_item(cost=10.00)]
        result = _apply_invoice_filters(items, self._validated(maxCost='xyz'))
        assert len(result) == 1
