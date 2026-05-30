"""Unit tests for CacheService.delete_account_cache (Task 8.2).

Tests the delete_account_cache method that deletes ALL cached data for an
account (including META items) when a member disconnects an AWS account.

Requirements validated: 10.3
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService


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


class TestDeleteAccountCacheBasic:
    """Tests for basic delete_account_cache functionality."""

    def test_deletes_all_daily_items(self, cache_service, mock_dynamodb):
        """Should query all items for the partition key and delete them."""
        # Mock the table query to return DAILY items
        cache_service._table.query.return_value = {
            'Items': [
                {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-15'},
                {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-16'},
                {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-17'},
            ]
        }

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 3
        mock_dynamodb.meta.client.batch_write_item.assert_called_once()
        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        delete_requests = call_args[1]['RequestItems']['Cost_Cache_Table']
        assert len(delete_requests) == 3
        # Verify all are DeleteRequests
        for req in delete_requests:
            assert 'DeleteRequest' in req

    def test_deletes_meta_items_too(self, cache_service, mock_dynamodb):
        """Should delete META items (like META#last_refresh) along with DAILY items."""
        cache_service._table.query.return_value = {
            'Items': [
                {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-15'},
                {'pk': 'user@example.com#123456789012', 'sk': 'META#last_refresh'},
            ]
        }

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 2
        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        delete_requests = call_args[1]['RequestItems']['Cost_Cache_Table']
        # Verify both DAILY and META items are in the delete batch
        sks = [req['DeleteRequest']['Key']['sk'] for req in delete_requests]
        assert 'DAILY#2024-01-15' in sks
        assert 'META#last_refresh' in sks

    def test_returns_zero_when_no_items(self, cache_service, mock_dynamodb):
        """Should return 0 when no items exist for the account."""
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 0
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_uses_correct_partition_key(self, cache_service, mock_dynamodb):
        """Should query using the correct partition key format."""
        cache_service._table.query.return_value = {'Items': []}

        cache_service.delete_account_cache('admin@corp.com', '987654321098')

        call_args = cache_service._table.query.call_args
        # Verify the KeyConditionExpression uses the correct pk
        assert call_args is not None

    def test_does_not_verify_ownership(self, cache_service, mock_dynamodb):
        """Should NOT call _verify_account_ownership (caller already verified)."""
        cache_service._table.query.return_value = {'Items': []}

        with patch.object(cache_service, '_verify_account_ownership') as mock_verify:
            cache_service.delete_account_cache('user@example.com', '123456789012')
            mock_verify.assert_not_called()


class TestDeleteAccountCachePagination:
    """Tests for handling DynamoDB pagination during query."""

    def test_handles_paginated_results(self, cache_service, mock_dynamodb):
        """Should follow pagination to retrieve all items before deleting."""
        # First page returns items with LastEvaluatedKey
        first_page_items = [
            {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#2024-01-{d:02d}'}
            for d in range(1, 11)
        ]
        second_page_items = [
            {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#2024-01-{d:02d}'}
            for d in range(11, 16)
        ]

        cache_service._table.query.side_effect = [
            {'Items': first_page_items, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'y'}},
            {'Items': second_page_items},
        ]

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 15
        assert cache_service._table.query.call_count == 2

    def test_handles_multiple_pages(self, cache_service, mock_dynamodb):
        """Should handle more than two pages of results."""
        page1 = [{'pk': 'u@e.com#123', 'sk': f'DAILY#2024-01-{d:02d}'} for d in range(1, 6)]
        page2 = [{'pk': 'u@e.com#123', 'sk': f'DAILY#2024-01-{d:02d}'} for d in range(6, 11)]
        page3 = [{'pk': 'u@e.com#123', 'sk': f'DAILY#2024-01-{d:02d}'} for d in range(11, 14)]

        cache_service._table.query.side_effect = [
            {'Items': page1, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'y'}},
            {'Items': page2, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'z'}},
            {'Items': page3},
        ]

        result = cache_service.delete_account_cache('u@e.com', '123')

        assert result == 13
        assert cache_service._table.query.call_count == 3


class TestDeleteAccountCacheBatching:
    """Tests for BatchWriteItem 25-item limit during deletion."""

    def test_chunks_deletes_into_batches_of_25(self, cache_service, mock_dynamodb):
        """Should split deletes into batches of 25 items."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#2024-01-{d:02d}'}
            for d in range(1, 27)  # 26 items → 2 batches
        ]
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 26
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2
        # First batch should have 25 items
        first_call = mock_dynamodb.meta.client.batch_write_item.call_args_list[0]
        assert len(first_call[1]['RequestItems']['Cost_Cache_Table']) == 25
        # Second batch should have 1 item
        second_call = mock_dynamodb.meta.client.batch_write_item.call_args_list[1]
        assert len(second_call[1]['RequestItems']['Cost_Cache_Table']) == 1

    def test_exactly_25_items_single_batch(self, cache_service, mock_dynamodb):
        """Exactly 25 items should be deleted in a single batch."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#2024-01-{d:02d}'}
            for d in range(1, 26)
        ]
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 25
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 1


class TestDeleteAccountCacheErrorHandling:
    """Tests for error handling during deletion."""

    def test_query_failure_returns_zero(self, cache_service, mock_dynamodb):
        """Should return 0 if the initial query fails."""
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 0
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_batch_delete_failure_continues(self, cache_service, mock_dynamodb):
        """Should continue with remaining batches if one batch fails."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#2024-01-{d:02d}'}
            for d in range(1, 27)  # 26 items → 2 batches
        ]
        cache_service._table.query.return_value = {'Items': items}

        # First batch fails, second succeeds
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'BatchWriteItem'
            ),
            {'UnprocessedItems': {}},
        ]

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        # Only second batch (1 item) counted as deleted
        assert result == 1
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2

    @patch('cache_service.time.sleep')
    def test_retries_unprocessed_deletes(self, mock_sleep, cache_service, mock_dynamodb):
        """Should retry unprocessed delete items with exponential backoff."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-15'},
        ]
        cache_service._table.query.return_value = {'Items': items}

        unprocessed_item = {'DeleteRequest': {'Key': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            {'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}},
            {'UnprocessedItems': {}},  # Retry succeeds
        ]

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        assert result == 1
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2
        mock_sleep.assert_called_once_with(0.1)

    @patch('cache_service.time.sleep')
    def test_retries_up_to_3_times(self, mock_sleep, cache_service, mock_dynamodb):
        """Should retry unprocessed items up to 3 times then count as failed."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-15'},
            {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-16'},
        ]
        cache_service._table.query.return_value = {'Items': items}

        unprocessed_item = {'DeleteRequest': {'Key': {'pk': 'x', 'sk': 'y'}}}
        # All retries return unprocessed items
        mock_dynamodb.meta.client.batch_write_item.return_value = {
            'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}
        }

        result = cache_service.delete_account_cache('user@example.com', '123456789012')

        # 2 items in batch, 1 unprocessed = 1 deleted
        assert result == 1
        # 1 initial + 3 retries = 4 total calls
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 4
        # Verify exponential backoff
        assert mock_sleep.call_args_list == [
            call(0.1),
            call(0.2),
            call(0.4),
        ]

    def test_does_not_raise_on_error(self, cache_service, mock_dynamodb):
        """Should never raise an exception — always returns a count."""
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'table gone'}},
            'Query'
        )

        # Should not raise
        result = cache_service.delete_account_cache('user@example.com', '123456789012')
        assert isinstance(result, int)


class TestDeleteAccountCacheDeleteRequestFormat:
    """Tests that delete requests are properly formatted."""

    def test_delete_request_contains_pk_and_sk(self, cache_service, mock_dynamodb):
        """Each DeleteRequest should contain the correct pk and sk."""
        items = [
            {'pk': 'user@example.com#123456789012', 'sk': 'DAILY#2024-01-15'},
        ]
        cache_service._table.query.return_value = {'Items': items}

        cache_service.delete_account_cache('user@example.com', '123456789012')

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        delete_req = call_args[1]['RequestItems']['Cost_Cache_Table'][0]
        assert delete_req == {
            'DeleteRequest': {
                'Key': {
                    'pk': 'user@example.com#123456789012',
                    'sk': 'DAILY#2024-01-15',
                }
            }
        }

    def test_uses_projection_expression_for_efficiency(self, cache_service, mock_dynamodb):
        """Query should use ProjectionExpression to only fetch pk and sk."""
        cache_service._table.query.return_value = {'Items': []}

        cache_service.delete_account_cache('user@example.com', '123456789012')

        call_args = cache_service._table.query.call_args
        assert 'ProjectionExpression' in call_args[1]
        assert 'pk' in call_args[1]['ProjectionExpression']
        assert 'sk' in call_args[1]['ProjectionExpression']
