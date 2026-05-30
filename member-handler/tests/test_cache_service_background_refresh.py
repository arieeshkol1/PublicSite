"""Unit tests for CacheService.trigger_background_refresh (Task 6.3).

Tests the trigger_background_refresh method that performs a non-blocking
background refresh of the most recent 3 days' cost data using a daemon
thread, updates the META#last_refresh item, and logs failures without
blocking the member's current request.

Requirements validated: 6.2, 6.3
"""

import sys
import os
import time
import threading
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService, TTL_DURATION_SECONDS
from cache_types import CostDataItem, DateRange


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock = MagicMock()
    mock.meta.client.batch_write_item.return_value = {'UnprocessedItems': {}}
    return mock


@pytest.fixture
def mock_table(mock_dynamodb):
    """Create a mock DynamoDB table."""
    table = MagicMock()
    mock_dynamodb.Table.return_value = table
    return table


@pytest.fixture
def cache_service(mock_dynamodb, mock_table):
    """Create a CacheService instance with mocked DynamoDB."""
    service = CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)
    return service


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


class TestMetaLastRefreshUpdate:
    """Tests that META#last_refresh item is updated immediately on trigger."""

    def test_updates_meta_last_refresh_item(self, cache_service, mock_dynamodb, mock_table):
        """Should write META#last_refresh item to DynamoDB immediately."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {
            'AccessKeyId': 'AKIA...',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
        }

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        # Verify put_item was called for META#last_refresh
        cache_service._table.put_item.assert_called_once()
        call_kwargs = cache_service._table.put_item.call_args[1]
        item = call_kwargs['Item']
        assert item['pk'] == 'user@example.com#123456789012'
        assert item['sk'] == 'META#last_refresh'
        assert 'last_refresh_at' in item
        assert 'ttl' in item

    def test_meta_item_has_correct_ttl(self, cache_service, mock_dynamodb, mock_table):
        """META#last_refresh TTL should be 90 days from now."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()

            before = datetime.now(timezone.utc)
            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )
            after = datetime.now(timezone.utc)

        call_kwargs = cache_service._table.put_item.call_args[1]
        item = call_kwargs['Item']
        ttl = item['ttl']

        # TTL should be approximately now + 90 days
        expected_min = int(before.timestamp()) + TTL_DURATION_SECONDS
        expected_max = int(after.timestamp()) + TTL_DURATION_SECONDS
        assert expected_min <= ttl <= expected_max

    def test_meta_item_last_refresh_at_is_iso_format(self, cache_service, mock_dynamodb, mock_table):
        """last_refresh_at should be a valid ISO 8601 timestamp."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()

            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        call_kwargs = cache_service._table.put_item.call_args[1]
        last_refresh_at = call_kwargs['Item']['last_refresh_at']
        # Should parse without error
        parsed = datetime.fromisoformat(last_refresh_at)
        assert parsed.tzinfo is not None  # Should be timezone-aware

    def test_continues_if_meta_update_fails(self, cache_service, mock_dynamodb, mock_table):
        """Should still spawn background thread even if META update fails."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'PutItem'
        )
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            # Should not raise
            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        # Thread should still be started
        mock_thread.start.assert_called_once()


class TestNonBlockingBehavior:
    """Tests that trigger_background_refresh returns immediately (non-blocking)."""

    def test_returns_immediately(self, cache_service, mock_dynamodb, mock_table):
        """Method should return None immediately without waiting for thread."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            result = cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        assert result is None

    def test_spawns_daemon_thread(self, cache_service, mock_dynamodb, mock_table):
        """Should create a daemon thread so it doesn't block Lambda shutdown."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        mock_thread_cls.assert_called_once()
        call_kwargs = mock_thread_cls.call_args[1]
        assert call_kwargs['daemon'] is True

    def test_thread_is_started(self, cache_service, mock_dynamodb, mock_table):
        """Should call thread.start() to begin background execution."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        mock_thread.start.assert_called_once()

    def test_thread_target_is_worker(self, cache_service, mock_dynamodb, mock_table):
        """Thread target should be _background_refresh_worker with correct args."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )

        call_kwargs = mock_thread_cls.call_args[1]
        assert call_kwargs['target'] == cache_service._background_refresh_worker
        assert call_kwargs['args'] == ('user@example.com', '123456789012', credentials)


class TestBackgroundRefreshWorker:
    """Tests for the _background_refresh_worker method."""

    @patch('cache_service.CacheService.write_cost_data')
    def test_worker_fetches_recent_3_days(self, mock_write, cache_service, mock_dynamodb, mock_table):
        """Worker should fetch cost data for the most recent 3 days."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        mock_items = [
            CostDataItem(date='2024-01-14', cost_amount=10.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
            CostDataItem(date='2024-01-15', cost_amount=12.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
            CostDataItem(date='2024-01-16', cost_amount=8.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
        ]

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   return_value=mock_items) as mock_fetch:
            cache_service._background_refresh_worker(
                'user@example.com', '123456789012', credentials
            )

        # Verify fetch_cost_data was called with a 3-day range
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[0]
        date_ranges = call_args[0]
        assert len(date_ranges) == 1

        # Verify the range covers 3 days (today - 2 to today + 1 exclusive)
        today = datetime.now(timezone.utc).date()
        expected_start = (today - timedelta(days=2)).isoformat()
        expected_end = (today + timedelta(days=1)).isoformat()
        assert date_ranges[0].start == expected_start
        assert date_ranges[0].end == expected_end

    @patch('cache_service.CacheService.write_cost_data')
    def test_worker_writes_fetched_data_to_cache(self, mock_write, cache_service, mock_dynamodb, mock_table):
        """Worker should call write_cost_data with fetched items."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        mock_write.return_value = True
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        mock_items = [
            CostDataItem(date='2024-01-15', cost_amount=10.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
        ]

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   return_value=mock_items):
            cache_service._background_refresh_worker(
                'user@example.com', '123456789012', credentials
            )

        mock_write.assert_called_once_with(
            'user@example.com', '123456789012', mock_items
        )

    @patch('cache_service.CacheService.write_cost_data')
    def test_worker_skips_write_if_no_items_fetched(self, mock_write, cache_service, mock_dynamodb, mock_table):
        """Worker should not call write_cost_data if fetch returns empty list."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   return_value=[]):
            cache_service._background_refresh_worker(
                'user@example.com', '123456789012', credentials
            )

        mock_write.assert_not_called()

    def test_worker_logs_error_on_fetch_failure(self, cache_service, mock_dynamodb, mock_table):
        """Worker should log errors without raising when fetch fails."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   side_effect=Exception("CE API timeout")):
            with patch('cache_service.logger') as mock_logger:
                # Should not raise
                cache_service._background_refresh_worker(
                    'user@example.com', '123456789012', credentials
                )

            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert 'user@example.com#123456789012' in error_msg

    @patch('cache_service.CacheService.write_cost_data')
    def test_worker_logs_error_on_write_failure(self, mock_write, cache_service, mock_dynamodb, mock_table):
        """Worker should log errors without raising when write fails."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        mock_write.side_effect = Exception("DynamoDB write error")
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        mock_items = [
            CostDataItem(date='2024-01-15', cost_amount=10.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
        ]

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   return_value=mock_items):
            with patch('cache_service.logger') as mock_logger:
                # Should not raise
                cache_service._background_refresh_worker(
                    'user@example.com', '123456789012', credentials
                )

            mock_logger.error.assert_called_once()

    @patch('cache_service.CacheService.write_cost_data')
    def test_worker_logs_success(self, mock_write, cache_service, mock_dynamodb, mock_table):
        """Worker should log success message with item count on completion."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        mock_write.return_value = True
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        mock_items = [
            CostDataItem(date='2024-01-14', cost_amount=10.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
            CostDataItem(date='2024-01-15', cost_amount=12.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
            CostDataItem(date='2024-01-16', cost_amount=8.0, currency='USD',
                         service_breakdown={}, fetched_at='2024-01-16T08:00:00Z'),
        ]

        with patch('incremental_fetch_engine.IncrementalFetchEngine.fetch_cost_data',
                   return_value=mock_items):
            with patch('cache_service.logger') as mock_logger:
                cache_service._background_refresh_worker(
                    'user@example.com', '123456789012', credentials
                )

            mock_logger.info.assert_called_once()
            info_msg = mock_logger.info.call_args[0][0]
            assert '3 items refreshed' in info_msg


class TestEndToEndNonBlocking:
    """Integration-style tests verifying the full non-blocking flow."""

    def test_full_flow_does_not_block(self, cache_service, mock_dynamodb, mock_table):
        """The full trigger_background_refresh call should complete quickly."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            start_time = time.time()
            cache_service.trigger_background_refresh(
                'user@example.com', '123456789012', credentials
            )
            elapsed = time.time() - start_time

        # Should complete in well under 1 second (non-blocking)
        assert elapsed < 1.0

    def test_partition_key_format_in_meta_item(self, cache_service, mock_dynamodb, mock_table):
        """META item pk should follow {member_id}#{account_id} format."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        credentials = {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}

        with patch('cache_service.threading.Thread') as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()

            cache_service.trigger_background_refresh(
                'admin@corp.com', '987654321098', credentials
            )

        call_kwargs = cache_service._table.put_item.call_args[1]
        assert call_kwargs['Item']['pk'] == 'admin@corp.com#987654321098'
