"""Unit tests for CacheService initialization and key construction (Task 2.1).

Tests the __init__, _build_partition_key, _build_sort_key, and _calculate_ttl
methods of the CacheService class.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService, TTL_DURATION_SECONDS


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def cache_service(mock_dynamodb):
    """Create a CacheService instance with mocked DynamoDB."""
    return CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)


class TestInit:
    """Tests for CacheService.__init__."""

    def test_init_stores_table_name(self, mock_dynamodb):
        """Should store the provided table_name."""
        cs = CacheService('MyTable', dynamodb_resource=mock_dynamodb)
        assert cs._table_name == 'MyTable'

    def test_init_uses_provided_dynamodb_resource(self, mock_dynamodb):
        """Should use the provided dynamodb_resource."""
        cs = CacheService('T', dynamodb_resource=mock_dynamodb)
        assert cs._dynamodb is mock_dynamodb

    def test_init_creates_table_reference(self, mock_dynamodb):
        """Should create a Table reference from the resource."""
        cs = CacheService('Cost_Cache_Table', dynamodb_resource=mock_dynamodb)
        mock_dynamodb.Table.assert_called_once_with('Cost_Cache_Table')
        assert cs._table == mock_dynamodb.Table.return_value


class TestBuildPartitionKey:
    """Tests for CacheService._build_partition_key."""

    def test_basic_format(self):
        """Should return member_id#account_id."""
        result = CacheService._build_partition_key('user@example.com', '123456789012')
        assert result == 'user@example.com#123456789012'

    def test_preserves_special_characters_in_email(self):
        """Should preserve special characters in member_id."""
        result = CacheService._build_partition_key('user+tag@sub.example.com', '111222333444')
        assert result == 'user+tag@sub.example.com#111222333444'

    def test_empty_strings(self):
        """Should handle empty strings (edge case)."""
        result = CacheService._build_partition_key('', '')
        assert result == '#'

    def test_hash_in_member_id(self):
        """Should handle # character in member_id (unlikely but valid)."""
        result = CacheService._build_partition_key('user#1@example.com', '123456789012')
        assert result == 'user#1@example.com#123456789012'


class TestBuildSortKey:
    """Tests for CacheService._build_sort_key."""

    def test_basic_format(self):
        """Should return DAILY#date."""
        result = CacheService._build_sort_key('2024-01-15')
        assert result == 'DAILY#2024-01-15'

    def test_different_dates(self):
        """Should work with various date formats."""
        assert CacheService._build_sort_key('2024-12-31') == 'DAILY#2024-12-31'
        assert CacheService._build_sort_key('2023-01-01') == 'DAILY#2023-01-01'

    def test_only_daily_granularity(self):
        """Sort key always uses DAILY prefix — no MONTHLY or HOURLY."""
        result = CacheService._build_sort_key('2024-06-15')
        assert result.startswith('DAILY#')
        assert 'MONTHLY' not in result
        assert 'HOURLY' not in result


class TestCalculateTtl:
    """Tests for CacheService._calculate_ttl."""

    def test_basic_ttl_calculation(self):
        """Should return Unix epoch 90 days from fetched_at."""
        # 2024-01-16T08:30:00Z + 90 days = 2024-04-15T08:30:00Z
        result = CacheService._calculate_ttl('2024-01-16T08:30:00Z')
        assert result == 1713169800

    def test_ttl_is_integer(self):
        """TTL should be an integer (Unix epoch)."""
        result = CacheService._calculate_ttl('2024-01-01T00:00:00Z')
        assert isinstance(result, int)

    def test_ttl_with_timezone_offset(self):
        """Should handle ISO 8601 with explicit timezone offset."""
        # Same moment in time, different representation
        result_z = CacheService._calculate_ttl('2024-01-16T08:30:00Z')
        result_offset = CacheService._calculate_ttl('2024-01-16T08:30:00+00:00')
        assert result_z == result_offset

    def test_ttl_90_days_difference(self):
        """The difference between fetched_at epoch and TTL should be 7,776,000 seconds."""
        from datetime import datetime, timezone
        fetched_at = '2024-06-01T12:00:00Z'
        fetched_epoch = int(
            datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        )
        ttl = CacheService._calculate_ttl(fetched_at)
        assert ttl - fetched_epoch == TTL_DURATION_SECONDS

    def test_ttl_duration_constant(self):
        """TTL_DURATION_SECONDS should be exactly 90 days."""
        assert TTL_DURATION_SECONDS == 7_776_000
