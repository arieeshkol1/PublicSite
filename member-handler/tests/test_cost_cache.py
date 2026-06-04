"""Unit tests for the cost_cache module (cache-first cost data retrieval).

Tests the _get_cost_data_cached function which queries Cost_Cache_Table first
and falls back to live Cost Explorer API on cache miss.
"""

import sys
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pytest

# Ensure the member-handler directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cost_cache import (
    _get_cost_data_cached,
    _read_from_cache,
    _fetch_from_cost_explorer,
    _count_days,
)


class TestCountDays:
    """Tests for the _count_days helper."""

    def test_same_day(self):
        assert _count_days('2024-01-01', '2024-01-01') == 0

    def test_one_day(self):
        assert _count_days('2024-01-01', '2024-01-02') == 1

    def test_thirty_days(self):
        assert _count_days('2024-01-01', '2024-01-31') == 30

    def test_cross_month(self):
        assert _count_days('2024-01-25', '2024-02-05') == 11


class TestReadFromCache:
    """Tests for _read_from_cache function."""

    @patch('cost_cache.boto3.resource')
    def test_cache_hit_full_coverage(self, mock_resource):
        """When cache has enough items, returns aggregated cost data."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # Simulate 28 cache items (for a 30-day range, 28 >= 30-2)
        items = []
        for i in range(28):
            day = f'2024-01-{i+1:02d}'
            items.append({
                'pk': 'user@test.com#123456789012',
                'sk': f'DAILY#{day}',
                'cost_amount': Decimal('10.50'),
                'service_breakdown': {
                    'Amazon EC2': Decimal('7.00'),
                    'Amazon S3': Decimal('3.50'),
                },
            })

        mock_table.query.return_value = {'Items': items}

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is not None
        assert len(result) == 2
        # Sorted descending by cost
        assert result[0]['service'] == 'Amazon EC2'
        assert result[0]['cost_usd'] == round(7.00 * 28, 4)
        assert result[1]['service'] == 'Amazon S3'
        assert result[1]['cost_usd'] == round(3.50 * 28, 4)
        assert result[0]['period'] == '2024-01-01 to 2024-01-31'

    @patch('cost_cache.boto3.resource')
    def test_cache_miss_no_items(self, mock_resource):
        """When cache has no items, returns None."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {'Items': []}

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is None

    @patch('cost_cache.boto3.resource')
    def test_cache_incomplete_coverage(self, mock_resource):
        """When cache has too few items, returns None (incomplete)."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # Only 10 items for a 30-day range (need at least 28)
        items = [
            {
                'pk': 'user@test.com#123456789012',
                'sk': f'DAILY#2024-01-{i+1:02d}',
                'cost_amount': Decimal('5.00'),
                'service_breakdown': {'Amazon EC2': Decimal('5.00')},
            }
            for i in range(10)
        ]
        mock_table.query.return_value = {'Items': items}

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is None

    @patch('cost_cache.boto3.resource')
    def test_cache_read_dynamo_error(self, mock_resource):
        """When DynamoDB read fails, returns None."""
        from botocore.exceptions import ClientError

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'Service unavailable'}},
            'Query'
        )

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is None

    @patch('cost_cache.boto3.resource')
    def test_cache_handles_pagination(self, mock_resource):
        """When query returns paginated results, all items are collected."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        # First page returns 15 items + LastEvaluatedKey
        items_page1 = [
            {
                'pk': 'user@test.com#123456789012',
                'sk': f'DAILY#2024-01-{i+1:02d}',
                'cost_amount': Decimal('10.00'),
                'service_breakdown': {'Amazon EC2': Decimal('10.00')},
            }
            for i in range(15)
        ]
        # Second page returns 15 items (no LastEvaluatedKey)
        items_page2 = [
            {
                'pk': 'user@test.com#123456789012',
                'sk': f'DAILY#2024-01-{i+16:02d}',
                'cost_amount': Decimal('10.00'),
                'service_breakdown': {'Amazon EC2': Decimal('10.00')},
            }
            for i in range(15)
        ]

        mock_table.query.side_effect = [
            {'Items': items_page1, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'y'}},
            {'Items': items_page2},
        ]

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is not None
        assert result[0]['service'] == 'Amazon EC2'
        assert result[0]['cost_usd'] == round(10.00 * 30, 4)

    @patch('cost_cache.boto3.resource')
    def test_cache_filters_zero_cost_services(self, mock_resource):
        """Services with zero total cost are excluded from results."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        items = [
            {
                'pk': 'user@test.com#123456789012',
                'sk': f'DAILY#2024-01-{i+1:02d}',
                'cost_amount': Decimal('5.00'),
                'service_breakdown': {
                    'Amazon EC2': Decimal('5.00'),
                    'AWS Config': Decimal('0'),
                },
            }
            for i in range(28)
        ]
        mock_table.query.return_value = {'Items': items}

        result = _read_from_cache(
            'user@test.com', '123456789012',
            '2024-01-01', '2024-01-31'
        )

        assert result is not None
        assert len(result) == 1
        assert result[0]['service'] == 'Amazon EC2'


class TestFetchFromCostExplorer:
    """Tests for _fetch_from_cost_explorer function."""

    @patch('cost_cache.boto3.client')
    def test_successful_fetch(self, mock_client_ctor):
        """Returns cost_by_service list from live Cost Explorer."""
        mock_ce = MagicMock()
        mock_client_ctor.return_value = mock_ce

        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'},
                    'Groups': [
                        {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '145.67'}}},
                        {'Keys': ['Amazon S3'], 'Metrics': {'UnblendedCost': {'Amount': '23.50'}}},
                        {'Keys': ['Tax'], 'Metrics': {'UnblendedCost': {'Amount': '0.00'}}},
                    ],
                }
            ]
        }

        creds = {
            'AccessKeyId': 'AKIA...',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }
        result = _fetch_from_cost_explorer(creds, '2024-01-01', '2024-02-01')

        assert result is not None
        assert len(result) == 2  # Tax with $0 excluded
        assert result[0]['service'] == 'Amazon EC2'
        assert result[0]['cost_usd'] == 145.67
        assert result[1]['service'] == 'Amazon S3'
        assert result[1]['cost_usd'] == 23.5

    @patch('cost_cache.boto3.client')
    def test_api_failure_returns_none(self, mock_client_ctor):
        """When Cost Explorer API call fails, returns None."""
        from botocore.exceptions import ClientError

        mock_ce = MagicMock()
        mock_client_ctor.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = ClientError(
            {'Error': {'Code': 'LimitExceededException', 'Message': 'Rate exceeded'}},
            'GetCostAndUsage'
        )

        creds = {
            'AccessKeyId': 'AKIA...',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }
        result = _fetch_from_cost_explorer(creds, '2024-01-01', '2024-02-01')

        assert result is None


class TestGetCostDataCached:
    """Integration tests for the main _get_cost_data_cached function."""

    @patch('cost_cache._fetch_from_cost_explorer')
    @patch('cost_cache._read_from_cache')
    def test_returns_cache_data_on_hit(self, mock_cache, mock_ce):
        """When cache has data, returns it and skips CE API."""
        cache_result = [
            {'service': 'Amazon EC2', 'cost_usd': 196.0, 'period': '2024-01-01 to 2024-01-31'},
        ]
        mock_cache.return_value = cache_result

        result, from_cache = _get_cost_data_cached(
            'user@test.com', '123456789012',
            {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'},
            '2024-01-01', '2024-01-31'
        )

        assert from_cache is True
        assert result == cache_result
        mock_ce.assert_not_called()

    @patch('cost_cache._fetch_from_cost_explorer')
    @patch('cost_cache._read_from_cache')
    def test_falls_back_to_live_api_on_cache_miss(self, mock_cache, mock_ce):
        """When cache returns None, falls back to live CE API."""
        mock_cache.return_value = None
        live_result = [
            {'service': 'Amazon EC2', 'cost_usd': 145.67, 'period': '2024-01-01 to 2024-02-01'},
        ]
        mock_ce.return_value = live_result

        result, from_cache = _get_cost_data_cached(
            'user@test.com', '123456789012',
            {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'},
            '2024-01-01', '2024-02-01'
        )

        assert from_cache is False
        assert result == live_result
        mock_ce.assert_called_once()

    @patch('cost_cache._fetch_from_cost_explorer')
    @patch('cost_cache._read_from_cache')
    def test_both_fail_returns_error_indicator(self, mock_cache, mock_ce):
        """When both cache and CE fail, returns partial response with error."""
        mock_cache.return_value = None
        mock_ce.return_value = None

        result, from_cache = _get_cost_data_cached(
            'user@test.com', '123456789012',
            {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'},
            '2024-01-01', '2024-02-01'
        )

        assert from_cache is False
        assert len(result) == 1
        assert result[0]['service'] == '_error'
        assert 'error' in result[0]
        assert 'unavailable' in result[0]['error'].lower()
