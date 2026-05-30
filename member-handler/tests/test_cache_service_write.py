"""Unit tests for CacheService.write_cost_data cache write path (Task 2.5).

Tests the write_cost_data method that writes cost data items to DynamoDB
using BatchWriteItem with chunking, TTL calculation, and error handling.

Requirements validated: 5.1, 5.2, 5.3, 5.4, 5.5
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService, TTL_DURATION_SECONDS
from cache_types import CostDataItem


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock = MagicMock()
    mock.meta.client.batch_write_item.return_value = {'UnprocessedItems': {}}
    return mock


@pytest.fixture
def cache_service(mock_dynamodb):
    """Create a CacheService instance with mocked DynamoDB."""
    return CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)


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


def _make_cost_item(date_str, cost=10.0, currency='USD', fetched_at='2024-01-16T08:30:00Z'):
    """Helper to create a CostDataItem."""
    return CostDataItem(
        date=date_str,
        cost_amount=cost,
        currency=currency,
        service_breakdown={'Amazon EC2': cost * 0.6, 'Amazon S3': cost * 0.4},
        fetched_at=fetched_at,
    )


class TestWriteBasicFunctionality:
    """Tests for basic write_cost_data functionality."""

    def test_write_single_item(self, cache_service, mock_dynamodb):
        """Should write a single cost item successfully."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        mock_dynamodb.meta.client.batch_write_item.assert_called_once()

    def test_write_empty_list(self, cache_service, mock_dynamodb):
        """Should return True immediately for empty item list."""
        _mock_ownership_pass(cache_service, mock_dynamodb)

        result = cache_service.write_cost_data('user@example.com', '123456789012', [])

        assert result is True
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_write_multiple_items(self, cache_service, mock_dynamodb):
        """Should write multiple items in a single batch."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item(f'2024-01-{d:02d}') for d in range(15, 20)]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        mock_dynamodb.meta.client.batch_write_item.assert_called_once()
        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        request_items = call_args[1]['RequestItems']['Cost_Cache_Table']
        assert len(request_items) == 5


class TestItemFields:
    """Tests that all required fields are present in written items (Req 5.1)."""

    def test_item_contains_all_required_fields(self, cache_service, mock_dynamodb):
        """Each written item must have pk, sk, cost_amount, currency, service_breakdown, fetched_at, ttl."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15', cost=42.57, fetched_at='2024-01-16T08:30:00Z')]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']

        assert put_item['pk'] == 'user@example.com#123456789012'
        assert put_item['sk'] == 'DAILY#2024-01-15'
        assert put_item['cost_amount'] == '42.57'
        assert put_item['currency'] == 'USD'
        assert 'service_breakdown' in put_item
        assert put_item['fetched_at'] == '2024-01-16T08:30:00Z'
        assert 'ttl' in put_item

    def test_partition_key_format(self, cache_service, mock_dynamodb):
        """Partition key should be {member_id}#{account_id}."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        cache_service.write_cost_data('admin@corp.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        assert put_item['pk'] == 'admin@corp.com#123456789012'

    def test_sort_key_format(self, cache_service, mock_dynamodb):
        """Sort key should be DAILY#{date}."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-03-22')]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        assert put_item['sk'] == 'DAILY#2024-03-22'

    def test_service_breakdown_preserved(self, cache_service, mock_dynamodb):
        """Service breakdown dict should be written as-is."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        breakdown = {'Amazon EC2': 25.30, 'Amazon S3': 8.12, 'AWS Lambda': 5.15}
        items = [CostDataItem(
            date='2024-01-15',
            cost_amount=38.57,
            currency='USD',
            service_breakdown=breakdown,
            fetched_at='2024-01-16T08:30:00Z',
        )]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        assert put_item['service_breakdown'] == breakdown


class TestTTLCalculation:
    """Tests for TTL calculation (Req 5.4)."""

    def test_ttl_is_90_days_from_fetched_at(self, cache_service, mock_dynamodb):
        """TTL should be fetched_at + 90 days (7,776,000 seconds)."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        # 2024-01-16T08:30:00Z = epoch 1705393800
        fetched_at = '2024-01-16T08:30:00Z'
        items = [_make_cost_item('2024-01-15', fetched_at=fetched_at)]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        expected_ttl = 1705393800 + TTL_DURATION_SECONDS
        assert put_item['ttl'] == expected_ttl

    def test_ttl_is_integer(self, cache_service, mock_dynamodb):
        """TTL should be an integer (Unix epoch)."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        assert isinstance(put_item['ttl'], int)

    def test_missing_fetched_at_uses_current_time(self, cache_service, mock_dynamodb):
        """If fetched_at is empty, should use current time for TTL."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [CostDataItem(
            date='2024-01-15',
            cost_amount=10.0,
            currency='USD',
            service_breakdown={},
            fetched_at='',  # Empty fetched_at
        )]

        cache_service.write_cost_data('user@example.com', '123456789012', items)

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        put_item = call_args[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        # TTL should be approximately now + 90 days
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        expected_min = now_epoch + TTL_DURATION_SECONDS - 60  # Allow 60s tolerance
        expected_max = now_epoch + TTL_DURATION_SECONDS + 60
        assert expected_min <= put_item['ttl'] <= expected_max


class TestBatchChunking:
    """Tests for BatchWriteItem 25-item limit chunking (Req 5.2)."""

    def test_25_items_single_batch(self, cache_service, mock_dynamodb):
        """Exactly 25 items should be written in a single batch."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item(f'2024-01-{d:02d}') for d in range(1, 26)]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 1
        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        request_items = call_args[1]['RequestItems']['Cost_Cache_Table']
        assert len(request_items) == 25

    def test_26_items_two_batches(self, cache_service, mock_dynamodb):
        """26 items should be split into two batches (25 + 1)."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item(f'2024-01-{d:02d}') for d in range(1, 27)]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2

    def test_50_items_two_batches(self, cache_service, mock_dynamodb):
        """50 items should be split into two batches (25 + 25)."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        # Generate 50 items across Jan and Feb
        items = []
        for d in range(1, 32):
            items.append(_make_cost_item(f'2024-01-{d:02d}'))
        for d in range(1, 20):
            items.append(_make_cost_item(f'2024-02-{d:02d}'))

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2

    def test_75_items_three_batches(self, cache_service, mock_dynamodb):
        """75 items should be split into three batches (25 + 25 + 25)."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = []
        for month in range(1, 4):
            for d in range(1, 26):
                items.append(_make_cost_item(f'2024-{month:02d}-{d:02d}'))

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 3


class TestErrorHandling:
    """Tests for error handling on write failure (Req 5.3)."""

    def test_client_error_returns_false(self, cache_service, mock_dynamodb):
        """BatchWriteItem ClientError should return False, not raise."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        mock_dynamodb.meta.client.batch_write_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'BatchWriteItem'
        )
        items = [_make_cost_item('2024-01-15')]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is False

    def test_partial_batch_failure(self, cache_service, mock_dynamodb):
        """If first batch succeeds but second fails, returns False."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item(f'2024-01-{d:02d}') for d in range(1, 27)]

        # First batch succeeds, second fails
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            {'UnprocessedItems': {}},
            ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'BatchWriteItem'
            ),
        ]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is False

    def test_write_failure_does_not_raise(self, cache_service, mock_dynamodb):
        """Write failure should never raise an exception to the caller."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        mock_dynamodb.meta.client.batch_write_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'throttled'}},
            'BatchWriteItem'
        )
        items = [_make_cost_item('2024-01-15')]

        # Should not raise
        result = cache_service.write_cost_data('user@example.com', '123456789012', items)
        assert result is False


class TestUnprocessedItems:
    """Tests for handling UnprocessedItems in BatchWriteItem response."""

    @patch('cache_service.time.sleep')
    def test_retries_unprocessed_items(self, mock_sleep, cache_service, mock_dynamodb):
        """Should retry unprocessed items with exponential backoff."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        unprocessed_item = {'PutRequest': {'Item': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            {'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}},
            {'UnprocessedItems': {}},  # Retry succeeds
        ]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2
        mock_sleep.assert_called_once_with(0.1)  # First retry: 0.1 * 2^0

    @patch('cache_service.time.sleep')
    def test_retries_up_to_3_times(self, mock_sleep, cache_service, mock_dynamodb):
        """Should retry unprocessed items up to 3 times then give up."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        unprocessed_item = {'PutRequest': {'Item': {'pk': 'x', 'sk': 'y'}}}
        # All retries return unprocessed items
        mock_dynamodb.meta.client.batch_write_item.return_value = {
            'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}
        }

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is False
        # 1 initial + 3 retries = 4 total calls
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 4
        # Verify exponential backoff delays
        assert mock_sleep.call_args_list == [
            call(0.1),   # 0.1 * 2^0
            call(0.2),   # 0.1 * 2^1
            call(0.4),   # 0.1 * 2^2
        ]

    @patch('cache_service.time.sleep')
    def test_succeeds_on_second_retry(self, mock_sleep, cache_service, mock_dynamodb):
        """Should succeed if unprocessed items clear on second retry."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = [_make_cost_item('2024-01-15')]

        unprocessed_item = {'PutRequest': {'Item': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            {'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}},
            {'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}},
            {'UnprocessedItems': {}},  # Third attempt succeeds
        ]

        result = cache_service.write_cost_data('user@example.com', '123456789012', items)

        assert result is True
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 3


class TestOverwriteBehavior:
    """Tests for overwrite/last-write-wins behavior (Req 5.5)."""

    def test_same_date_uses_put_request(self, cache_service, mock_dynamodb):
        """Writing same date twice uses PutRequest which naturally overwrites."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        # Write first version
        items1 = [CostDataItem(
            date='2024-01-15',
            cost_amount=10.0,
            currency='USD',
            service_breakdown={'EC2': 10.0},
            fetched_at='2024-01-16T08:00:00Z',
        )]
        cache_service.write_cost_data('user@example.com', '123456789012', items1)

        # Write second version (same date, different cost)
        items2 = [CostDataItem(
            date='2024-01-15',
            cost_amount=15.0,
            currency='USD',
            service_breakdown={'EC2': 15.0},
            fetched_at='2024-01-16T10:00:00Z',
        )]
        cache_service.write_cost_data('user@example.com', '123456789012', items2)

        # Both writes should use PutRequest (which overwrites in DynamoDB)
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2
        # Verify second write has updated values
        second_call = mock_dynamodb.meta.client.batch_write_item.call_args_list[1]
        put_item = second_call[1]['RequestItems']['Cost_Cache_Table'][0]['PutRequest']['Item']
        assert put_item['cost_amount'] == '15.0'
        assert put_item['fetched_at'] == '2024-01-16T10:00:00Z'


class TestOwnershipVerification:
    """Tests that ownership is verified before writing."""

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
        items = [_make_cost_item('2024-01-15')]

        with pytest.raises(PermissionError):
            cache_service.write_cost_data('user@example.com', '123456789012', items)

        # Should not attempt to write
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_ownership_check_before_write(self, cache_service, mock_dynamodb):
        """Ownership verification should happen before any write attempt."""
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )
        mock_dynamodb.Table.side_effect = lambda name: (
            mock_accounts_table if name == 'MemberPortal-Accounts'
            else cache_service._table
        )
        items = [_make_cost_item('2024-01-15')]

        with pytest.raises(RuntimeError):
            cache_service.write_cost_data('user@example.com', '123456789012', items)

        mock_dynamodb.meta.client.batch_write_item.assert_not_called()
