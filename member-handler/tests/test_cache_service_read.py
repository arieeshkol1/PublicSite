"""Unit tests for CacheService.get_cost_data cache read path (Task 2.3).

Tests the enhanced get_cost_data method that properly computes cache_status
based on date coverage and populates missing_dates.

Requirements validated: 3.1, 3.2, 4.1, 4.5
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService
from cache_types import CacheResult, CostDataItem


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock = MagicMock()
    return mock


@pytest.fixture
def cache_service(mock_dynamodb):
    """Create a CacheService instance with mocked DynamoDB."""
    return CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)


def _make_dynamo_item(date_str, cost=10.0, currency='USD'):
    """Helper to create a DynamoDB item dict."""
    return {
        'pk': 'user@example.com#123456789012',
        'sk': f'DAILY#{date_str}',
        'cost_amount': str(cost),
        'currency': currency,
        'service_breakdown': {'Amazon EC2': str(cost)},
        'fetched_at': '2024-01-16T08:30:00Z',
        'ttl': 1713169800,
    }


def _mock_ownership_pass(cache_service, mock_dynamodb):
    """Set up mock to pass ownership verification."""
    mock_accounts_table = MagicMock()
    mock_accounts_table.query.return_value = {
        'Items': [{'accountId': '123456789012'}]
    }
    mock_dynamodb.Table.side_effect = lambda name: (
        mock_accounts_table if name == 'MemberPortal-Accounts'
        else cache_service._table
    )


class TestCacheStatusHit:
    """Tests for cache_status='hit' when all dates are found."""

    def test_full_hit_single_day(self, cache_service, mock_dynamodb):
        """Single day range fully cached returns 'hit'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [_make_dynamo_item('2024-01-15')]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-16'
        )

        assert result.cache_status == 'hit'
        assert result.missing_dates == []
        assert len(result.data) == 1
        assert result.partial_data is False

    def test_full_hit_multi_day(self, cache_service, mock_dynamodb):
        """Multi-day range fully cached returns 'hit'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [
                _make_dynamo_item('2024-01-15'),
                _make_dynamo_item('2024-01-16'),
                _make_dynamo_item('2024-01-17'),
            ]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'hit'
        assert result.missing_dates == []
        assert len(result.data) == 3

    def test_empty_date_range_returns_hit(self, cache_service, mock_dynamodb):
        """Empty date range (start == end) returns 'hit'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-15'
        )

        assert result.cache_status == 'hit'
        assert result.missing_dates == []


class TestCacheStatusMiss:
    """Tests for cache_status='miss' when no dates are found."""

    def test_full_miss_no_items(self, cache_service, mock_dynamodb):
        """No cached items for the range returns 'miss'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'miss'
        assert sorted(result.missing_dates) == ['2024-01-15', '2024-01-16', '2024-01-17']
        assert len(result.data) == 0

    def test_miss_single_day(self, cache_service, mock_dynamodb):
        """Single day not in cache returns 'miss'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-16'
        )

        assert result.cache_status == 'miss'
        assert result.missing_dates == ['2024-01-15']


class TestCacheStatusPartial:
    """Tests for cache_status='partial' when some dates are missing."""

    def test_partial_first_day_missing(self, cache_service, mock_dynamodb):
        """First day missing from 3-day range returns 'partial'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [
                _make_dynamo_item('2024-01-16'),
                _make_dynamo_item('2024-01-17'),
            ]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'partial'
        assert result.missing_dates == ['2024-01-15']
        assert len(result.data) == 2

    def test_partial_middle_day_missing(self, cache_service, mock_dynamodb):
        """Middle day missing from 3-day range returns 'partial'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [
                _make_dynamo_item('2024-01-15'),
                _make_dynamo_item('2024-01-17'),
            ]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'partial'
        assert result.missing_dates == ['2024-01-16']
        assert len(result.data) == 2

    def test_partial_last_day_missing(self, cache_service, mock_dynamodb):
        """Last day missing from 3-day range returns 'partial'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [
                _make_dynamo_item('2024-01-15'),
                _make_dynamo_item('2024-01-16'),
            ]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'partial'
        assert result.missing_dates == ['2024-01-17']
        assert len(result.data) == 2

    def test_partial_multiple_gaps(self, cache_service, mock_dynamodb):
        """Multiple non-contiguous gaps returns 'partial'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [
                _make_dynamo_item('2024-01-15'),
                _make_dynamo_item('2024-01-17'),
                _make_dynamo_item('2024-01-19'),
            ]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-20'
        )

        assert result.cache_status == 'partial'
        assert result.missing_dates == ['2024-01-16', '2024-01-18']
        assert len(result.data) == 3


class TestDynamoDBPagination:
    """Tests for DynamoDB pagination handling."""

    def test_handles_paginated_results(self, cache_service, mock_dynamodb):
        """Should follow LastEvaluatedKey for paginated results."""
        _mock_ownership_pass(cache_service, mock_dynamodb)

        # First page returns 2 items with pagination token
        first_response = {
            'Items': [
                _make_dynamo_item('2024-01-15'),
                _make_dynamo_item('2024-01-16'),
            ],
            'LastEvaluatedKey': {'pk': 'x', 'sk': 'DAILY#2024-01-16'},
        }
        # Second page returns 1 item, no more pages
        second_response = {
            'Items': [_make_dynamo_item('2024-01-17')],
        }
        cache_service._table.query.side_effect = [first_response, second_response]

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'hit'
        assert len(result.data) == 3
        assert result.missing_dates == []
        # Verify query was called twice (pagination)
        assert cache_service._table.query.call_count == 2

    def test_paginated_with_missing_dates(self, cache_service, mock_dynamodb):
        """Paginated results that still have gaps return 'partial'."""
        _mock_ownership_pass(cache_service, mock_dynamodb)

        first_response = {
            'Items': [_make_dynamo_item('2024-01-15')],
            'LastEvaluatedKey': {'pk': 'x', 'sk': 'DAILY#2024-01-15'},
        }
        second_response = {
            'Items': [_make_dynamo_item('2024-01-17')],
        }
        cache_service._table.query.side_effect = [first_response, second_response]

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
        )

        assert result.cache_status == 'partial'
        assert result.missing_dates == ['2024-01-16']
        assert len(result.data) == 2


class TestDynamoDBErrors:
    """Tests for DynamoDB error handling."""

    def test_dynamodb_error_without_credentials_raises_service_unavailable(self, cache_service, mock_dynamodb):
        """DynamoDB ClientError without credentials raises ServiceUnavailableError."""
        from cache_service import ServiceUnavailableError
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )

        with pytest.raises(ServiceUnavailableError):
            cache_service.get_cost_data(
                'user@example.com', '123456789012', '2024-01-15', '2024-01-18'
            )

    def test_dynamodb_error_with_credentials_falls_back_to_ce_api(self, cache_service, mock_dynamodb):
        """DynamoDB ClientError with credentials falls back to CE API."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )

        mock_creds = {
            'AccessKeyId': 'AKID',
            'SecretAccessKey': 'SECRET',
            'SessionToken': 'TOKEN',
        }

        with patch('incremental_fetch_engine.IncrementalFetchEngine') as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine_cls.return_value = mock_engine
            mock_engine.fetch_cost_data.return_value = [
                CostDataItem(date='2024-01-15', cost_amount=10.0, currency='USD',
                             service_breakdown={'EC2': 10.0}, fetched_at='2024-01-16T00:00:00Z'),
            ]

            result = cache_service.get_cost_data(
                'user@example.com', '123456789012', '2024-01-15', '2024-01-18',
                credentials=mock_creds,
            )

            assert result.cache_status == 'miss'
            assert result.partial_data is False
            assert len(result.data) == 1

    def test_dynamodb_and_ce_both_fail_raises_service_unavailable(self, cache_service, mock_dynamodb):
        """Both DynamoDB and CE API failing raises ServiceUnavailableError."""
        from cache_service import ServiceUnavailableError
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )

        mock_creds = {
            'AccessKeyId': 'AKID',
            'SecretAccessKey': 'SECRET',
            'SessionToken': 'TOKEN',
        }

        with patch('incremental_fetch_engine.IncrementalFetchEngine') as mock_engine_cls:
            mock_engine = MagicMock()
            mock_engine_cls.return_value = mock_engine
            mock_engine.fetch_cost_data.side_effect = Exception('CE API timeout')

            with pytest.raises(ServiceUnavailableError):
                cache_service.get_cost_data(
                    'user@example.com', '123456789012', '2024-01-15', '2024-01-18',
                    credentials=mock_creds,
                )


class TestDataConversion:
    """Tests for DynamoDB item to CostDataItem conversion."""

    def test_converts_items_correctly(self, cache_service, mock_dynamodb):
        """Should correctly convert DynamoDB items to CostDataItem objects."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [{
                'pk': 'user@example.com#123456789012',
                'sk': 'DAILY#2024-01-15',
                'cost_amount': '42.57',
                'currency': 'EUR',
                'service_breakdown': {'Amazon EC2': '25.30', 'Amazon S3': '17.27'},
                'fetched_at': '2024-01-16T08:30:00Z',
                'ttl': 1713169800,
            }]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-16'
        )

        assert len(result.data) == 1
        item = result.data[0]
        assert item.date == '2024-01-15'
        assert item.cost_amount == 42.57
        assert item.currency == 'EUR'
        assert item.service_breakdown == {'Amazon EC2': '25.30', 'Amazon S3': '17.27'}
        assert item.fetched_at == '2024-01-16T08:30:00Z'

    def test_handles_missing_optional_fields(self, cache_service, mock_dynamodb):
        """Should handle items with missing optional fields gracefully."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {
            'Items': [{
                'pk': 'user@example.com#123456789012',
                'sk': 'DAILY#2024-01-15',
            }]
        }

        result = cache_service.get_cost_data(
            'user@example.com', '123456789012', '2024-01-15', '2024-01-16'
        )

        assert len(result.data) == 1
        item = result.data[0]
        assert item.date == '2024-01-15'
        assert item.cost_amount == 0.0
        assert item.currency == 'USD'
        assert item.service_breakdown == {}
        assert item.fetched_at == ''


class TestOwnershipEnforcement:
    """Tests that ownership verification is enforced."""

    def test_rejects_unowned_account(self, cache_service, mock_dynamodb):
        """Should raise PermissionError for unowned account."""
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.return_value = {
            'Items': [{'accountId': '999999999999'}]
        }
        mock_dynamodb.Table.side_effect = lambda name: (
            mock_accounts_table if name == 'MemberPortal-Accounts'
            else cache_service._table
        )

        with pytest.raises(PermissionError):
            cache_service.get_cost_data(
                'user@example.com', '123456789012', '2024-01-15', '2024-01-16'
            )


class TestGenerateDateRange:
    """Tests for the _generate_date_range helper method."""

    def test_single_day(self):
        """Single day range returns one date."""
        result = CacheService._generate_date_range('2024-01-15', '2024-01-16')
        assert result == ['2024-01-15']

    def test_multi_day(self):
        """Multi-day range returns all dates."""
        result = CacheService._generate_date_range('2024-01-15', '2024-01-18')
        assert result == ['2024-01-15', '2024-01-16', '2024-01-17']

    def test_empty_range(self):
        """Same start and end returns empty list."""
        result = CacheService._generate_date_range('2024-01-15', '2024-01-15')
        assert result == []

    def test_month_boundary(self):
        """Handles month boundary correctly."""
        result = CacheService._generate_date_range('2024-01-30', '2024-02-02')
        assert result == ['2024-01-30', '2024-01-31', '2024-02-01']

    def test_year_boundary(self):
        """Handles year boundary correctly."""
        result = CacheService._generate_date_range('2023-12-30', '2024-01-02')
        assert result == ['2023-12-30', '2023-12-31', '2024-01-01']
