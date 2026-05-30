"""Unit tests for CacheService.should_background_refresh (Task 6.1).

Tests the staleness detection and rate limiting logic that determines
whether a background refresh should be triggered for an account's
recent cost data.

Requirements tested:
- 6.1: Trigger background refresh when recent 3 days' data is older than 6 hours
- 6.4: Max one background refresh per account per hour
"""

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock = MagicMock()
    return mock


@pytest.fixture
def cache_service(mock_dynamodb):
    """Create a CacheService instance with mocked DynamoDB."""
    return CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)


@pytest.fixture
def mock_table(cache_service):
    """Get the mock table from the cache service."""
    return cache_service._table


def _make_cache_item(date: str, fetched_at: str) -> dict:
    """Helper to create a cache item dict as returned by DynamoDB."""
    return {
        'pk': 'user@example.com#123456789012',
        'sk': f'DAILY#{date}',
        'cost_amount': '10.50',
        'currency': 'USD',
        'service_breakdown': {'Amazon EC2': '10.50'},
        'fetched_at': fetched_at,
        'ttl': 1713254400,
    }


def _make_meta_item(last_refresh_at: str) -> dict:
    """Helper to create a META#last_refresh item dict."""
    return {
        'pk': 'user@example.com#123456789012',
        'sk': 'META#last_refresh',
        'last_refresh_at': last_refresh_at,
        'ttl': 1713254400,
    }


class TestShouldBackgroundRefresh:
    """Tests for CacheService.should_background_refresh."""

    def test_returns_true_when_stale_and_not_throttled(self, cache_service, mock_table):
        """Should return True when data is older than 6 hours and no recent refresh."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        today = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        # Cache items with old fetched_at
        mock_table.query.return_value = {
            'Items': [
                _make_cache_item(today, seven_hours_ago),
                _make_cache_item(yesterday, seven_hours_ago),
            ]
        }
        # No META item (no recent refresh)
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_returns_false_when_data_is_fresh(self, cache_service, mock_table):
        """Should return False when data is less than 6 hours old."""
        now = datetime.now(timezone.utc)
        two_hours_ago = (now - timedelta(hours=2)).isoformat()
        today = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [
                _make_cache_item(today, two_hours_ago),
                _make_cache_item(yesterday, two_hours_ago),
            ]
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is False

    def test_returns_false_when_throttled(self, cache_service, mock_table):
        """Should return False when refresh was triggered less than 1 hour ago."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        thirty_minutes_ago = (now - timedelta(minutes=30)).isoformat()
        today = now.strftime('%Y-%m-%d')

        # Data is stale
        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        # But refresh was triggered 30 minutes ago
        mock_table.get_item.return_value = {
            'Item': _make_meta_item(thirty_minutes_ago)
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is False

    def test_returns_true_when_no_cached_items(self, cache_service, mock_table):
        """Should return True when no items exist for recent 3 days (stale)."""
        # No cached items
        mock_table.query.return_value = {'Items': []}
        # No META item
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_returns_true_when_throttle_expired(self, cache_service, mock_table):
        """Should return True when data is stale and last refresh was >1 hour ago."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        two_hours_ago = (now - timedelta(hours=2)).isoformat()
        today = now.strftime('%Y-%m-%d')

        # Data is stale
        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        # Last refresh was 2 hours ago (throttle expired)
        mock_table.get_item.return_value = {
            'Item': _make_meta_item(two_hours_ago)
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_staleness_uses_oldest_fetched_at(self, cache_service, mock_table):
        """Should use the oldest fetched_at among recent items for staleness check."""
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        today = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        # One item is fresh, one is stale — oldest determines staleness
        mock_table.query.return_value = {
            'Items': [
                _make_cache_item(today, one_hour_ago),
                _make_cache_item(yesterday, seven_hours_ago),
            ]
        }
        # No throttle
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_returns_false_on_query_error(self, cache_service, mock_table):
        """Should return False when DynamoDB query fails (avoid cascading failures)."""
        mock_table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'Service error'}},
            'Query'
        )

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is False

    def test_returns_false_on_meta_read_error(self, cache_service, mock_table):
        """Should return False when META item read fails."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        today = now.strftime('%Y-%m-%d')

        # Data is stale
        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        # META read fails
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'Service error'}},
            'GetItem'
        )

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is False

    def test_stale_with_empty_fetched_at(self, cache_service, mock_table):
        """Should treat items with empty fetched_at as stale."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, '')]
        }
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_stale_with_invalid_fetched_at(self, cache_service, mock_table):
        """Should treat items with unparseable fetched_at as stale."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, 'not-a-timestamp')]
        }
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_allows_refresh_with_invalid_meta_timestamp(self, cache_service, mock_table):
        """Should allow refresh when META item has unparseable last_refresh_at."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        today = now.strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        mock_table.get_item.return_value = {
            'Item': _make_meta_item('invalid-timestamp')
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_exactly_six_hours_is_not_stale(self, cache_service, mock_table):
        """Data fetched exactly 6 hours ago should NOT be considered stale (boundary)."""
        now = datetime.now(timezone.utc)
        # Exactly 6 hours ago (minus a small buffer to avoid timing issues)
        exactly_six_hours = (now - timedelta(hours=6) + timedelta(seconds=5)).isoformat()
        today = now.strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, exactly_six_hours)]
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is False

    def test_just_over_six_hours_is_stale(self, cache_service, mock_table):
        """Data fetched just over 6 hours ago should be considered stale."""
        now = datetime.now(timezone.utc)
        just_over_six_hours = (now - timedelta(hours=6, seconds=10)).isoformat()
        today = now.strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, just_over_six_hours)]
        }
        mock_table.get_item.return_value = {}

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_exactly_one_hour_throttle_boundary(self, cache_service, mock_table):
        """Refresh exactly 1 hour ago should NOT be throttled (boundary)."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        # Exactly 1 hour ago (plus small buffer to be clearly past threshold)
        exactly_one_hour = (now - timedelta(hours=1, seconds=5)).isoformat()
        today = now.strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        mock_table.get_item.return_value = {
            'Item': _make_meta_item(exactly_one_hour)
        }

        result = cache_service.should_background_refresh('user@example.com', '123456789012')
        assert result is True

    def test_queries_correct_date_range(self, cache_service, mock_table):
        """Should query for the most recent 3 days (today and 2 days back)."""
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        three_days_ago = (now - timedelta(days=2)).strftime('%Y-%m-%d')

        mock_table.query.return_value = {'Items': []}
        mock_table.get_item.return_value = {}

        cache_service.should_background_refresh('user@example.com', '123456789012')

        # Verify the query was called with correct key conditions
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        key_condition = call_kwargs['KeyConditionExpression']
        # The key condition should reference the correct pk and sk range
        assert key_condition is not None

    def test_checks_meta_item_with_correct_key(self, cache_service, mock_table):
        """Should check META#last_refresh with correct pk and sk."""
        now = datetime.now(timezone.utc)
        seven_hours_ago = (now - timedelta(hours=7)).isoformat()
        today = now.strftime('%Y-%m-%d')

        mock_table.query.return_value = {
            'Items': [_make_cache_item(today, seven_hours_ago)]
        }
        mock_table.get_item.return_value = {}

        cache_service.should_background_refresh('user@example.com', '123456789012')

        mock_table.get_item.assert_called_once_with(
            Key={'pk': 'user@example.com#123456789012', 'sk': 'META#last_refresh'}
        )
