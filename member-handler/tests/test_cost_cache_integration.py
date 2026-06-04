"""Unit tests for cache-first cost lookup integration in _gather_account_data.

Tests that the AI chat flow correctly uses _get_cost_data_cached before
falling back to the live Cost Explorer API, and handles error cases gracefully.
"""

import sys
import os
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pytest

# Ensure the member-handler directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCacheFirstCostIntegration:
    """Tests for cache-first cost lookup wired into _gather_account_data."""

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_cache_hit_skips_live_ce_call(self, mock_boto_client, mock_cached):
        """When cache returns data (from_cache=True), live CE call is skipped."""
        from lambda_function import _gather_account_data

        # Setup cache to return hit
        cached_data = [
            {'service': 'Amazon EC2', 'cost_usd': 150.0, 'period': '2024-01-01 to 2024-02-01'},
            {'service': 'Amazon S3', 'cost_usd': 25.0, 'period': '2024-01-01 to 2024-02-01'},
        ]
        mock_cached.return_value = (cached_data, True)

        # Mock boto3 client to track if CE is called
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
            member_email='user@test.com',
            account_id='123456789012',
        )

        # Verify cache was called
        mock_cached.assert_called_once()

        # Verify cost_by_service comes from cache
        assert data['cost_by_service'] == cached_data
        assert any('cache hit' in a.lower() for a in actions)

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_cache_miss_uses_live_api_fallback(self, mock_boto_client, mock_cached):
        """When cache misses (from_cache=False), live API result is used."""
        from lambda_function import _gather_account_data

        # Setup cache to return live API fallback
        live_data = [
            {'service': 'Amazon EC2', 'cost_usd': 145.67, 'period': '2024-01-01 to 2024-02-01'},
        ]
        mock_cached.return_value = (live_data, False)

        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
            member_email='user@test.com',
            account_id='123456789012',
        )

        # Verify cost_by_service comes from live fallback
        assert data['cost_by_service'] == live_data
        assert any('cache miss' in a.lower() or 'live api fallback' in a.lower() for a in actions)

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_both_fail_sets_error_and_continues(self, mock_boto_client, mock_cached):
        """When both cache and live API fail, sets cost_error and empty list."""
        from lambda_function import _gather_account_data

        # Setup cache to return error indicator
        error_data = [
            {'service': '_error', 'cost_usd': 0, 'period': '2024-01-01 to 2024-02-01',
             'error': 'Cost data unavailable from both cache and live API'}
        ]
        mock_cached.return_value = (error_data, False)

        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
            member_email='user@test.com',
            account_id='123456789012',
        )

        # Verify error handling
        assert data['cost_by_service'] == []
        assert 'cost_error' in data
        assert 'unavailable' in data['cost_error'].lower()

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_cache_exception_falls_through_to_direct_ce(self, mock_boto_client, mock_cached):
        """When cache lookup raises exception, falls through to direct CE call."""
        from lambda_function import _gather_account_data

        # Setup cache to raise an exception
        mock_cached.side_effect = Exception("Connection timeout")

        # Mock CE client to return valid data
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'},
                    'Groups': [
                        {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '100.00'}}},
                    ],
                }
            ]
        }

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
            member_email='user@test.com',
            account_id='123456789012',
        )

        # Verify it fell through to the standard CE call
        assert len(data.get('cost_by_service', [])) > 0
        assert any('monthly by service' in a.lower() for a in actions)

    @patch('lambda_function.boto3.client')
    def test_no_cache_params_uses_direct_ce(self, mock_boto_client):
        """When member_email/account_id not provided, uses direct CE (no cache)."""
        from lambda_function import _gather_account_data

        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'},
                    'Groups': [
                        {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '100.00'}}},
                    ],
                }
            ]
        }

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        # No member_email or account_id — should skip cache
        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
        )

        assert any('monthly by service' in a.lower() for a in actions)
        # Cache should NOT have been used
        assert not any('cache' in a.lower() for a in actions)

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_tag_filter_bypasses_cache(self, mock_boto_client, mock_cached):
        """When tag_key and tag_value are set, cache is bypassed."""
        from lambda_function import _gather_account_data

        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'},
                    'Groups': [
                        {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '50.00'}}},
                    ],
                }
            ]
        }

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much does team-alpha spend?',
            credentials,
            tag_key='Team',
            tag_value='alpha',
            member_email='user@test.com',
            account_id='123456789012',
        )

        # Cache should NOT have been called
        mock_cached.assert_not_called()
        # Standard CE call should have been used
        assert any('monthly by service' in a.lower() for a in actions)

    @patch('lambda_function._get_cost_data_cached')
    @patch('lambda_function.boto3.client')
    def test_error_service_filtered_from_cache_hit(self, mock_boto_client, mock_cached):
        """Error indicator items are filtered out from cache hit results."""
        from lambda_function import _gather_account_data

        # Simulate a cache hit that somehow contains an error marker (edge case)
        cached_data = [
            {'service': 'Amazon EC2', 'cost_usd': 100.0, 'period': '2024-01-01 to 2024-02-01'},
            {'service': '_error', 'cost_usd': 0, 'period': '2024-01-01 to 2024-02-01'},
        ]
        mock_cached.return_value = (cached_data, True)

        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        credentials = {
            'AccessKeyId': 'AKIA_TEST',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        data, actions = _gather_account_data(
            'how much am I spending?',
            credentials,
            member_email='user@test.com',
            account_id='123456789012',
        )

        # _error service should be filtered out
        services = [s['service'] for s in data['cost_by_service']]
        assert '_error' not in services
        assert 'Amazon EC2' in services
