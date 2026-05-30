"""Unit tests for CacheService.invalidate method (Task 8.1).

Tests the invalidate method that deletes cached items for a specified date
range or all items for an account using Query + BatchWriteItem (delete).

Requirements validated: 10.1, 10.4
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


def _make_cache_items(dates):
    """Helper to create mock DynamoDB items for given dates."""
    return [
        {'pk': 'user@example.com#123456789012', 'sk': f'DAILY#{d}'}
        for d in dates
    ]


class TestInvalidateWithDateRange:
    """Tests for invalidating cached items within a specified date range."""

    def test_delete_items_in_date_range(self, cache_service, mock_dynamodb):
        """Should query and delete items within the specified date range."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15', '2024-01-16', '2024-01-17'])
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-18'
        )

        assert result == 3
        mock_dynamodb.meta.client.batch_write_item.assert_called_once()
        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        request_items = call_args[1]['RequestItems']['Cost_Cache_Table']
        assert len(request_items) == 3
        # Verify all are DeleteRequests
        for req in request_items:
            assert 'DeleteRequest' in req
            assert 'Key' in req['DeleteRequest']

    def test_delete_single_day(self, cache_service, mock_dynamodb):
        """Should handle single-day date range."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15'])
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-16'
        )

        assert result == 1

    def test_empty_date_range_returns_zero(self, cache_service, mock_dynamodb):
        """Should return 0 when no items found in the date range."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-18'
        )

        assert result == 0
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_uses_between_condition_for_date_range(self, cache_service, mock_dynamodb):
        """Should use sk between condition when date range is specified."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-20'
        )

        cache_service._table.query.assert_called_once()
        call_kwargs = cache_service._table.query.call_args[1]
        assert 'KeyConditionExpression' in call_kwargs


class TestInvalidateAllItems:
    """Tests for invalidating all items when no date range is specified."""

    def test_delete_all_items_for_account(self, cache_service, mock_dynamodb):
        """Should delete all items when no date range is provided."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-10', '2024-01-11', '2024-01-12',
                                   '2024-01-13', '2024-01-14'])
        # Also include META item
        items.append({'pk': 'user@example.com#123456789012', 'sk': 'META#last_refresh'})
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate('user@example.com', '123456789012')

        assert result == 6
        mock_dynamodb.meta.client.batch_write_item.assert_called_once()

    def test_no_items_returns_zero(self, cache_service, mock_dynamodb):
        """Should return 0 when account has no cached items."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        result = cache_service.invalidate('user@example.com', '123456789012')

        assert result == 0
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_queries_by_partition_key_only(self, cache_service, mock_dynamodb):
        """Should query using only pk when no date range specified."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.return_value = {'Items': []}

        cache_service.invalidate('user@example.com', '123456789012')

        cache_service._table.query.assert_called_once()


class TestBatchDeletion:
    """Tests for batch deletion respecting 25-item limit."""

    def test_chunks_deletes_into_batches_of_25(self, cache_service, mock_dynamodb):
        """Should split deletes into batches of 25."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items([f'2024-01-{d:02d}' for d in range(1, 31)])
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate('user@example.com', '123456789012')

        assert result == 30
        # 30 items = 2 batches (25 + 5)
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2

    def test_exactly_25_items_single_batch(self, cache_service, mock_dynamodb):
        """Exactly 25 items should be deleted in a single batch."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items([f'2024-01-{d:02d}' for d in range(1, 26)])
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate('user@example.com', '123456789012')

        assert result == 25
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 1

    def test_delete_request_format(self, cache_service, mock_dynamodb):
        """Each delete request should have correct key structure."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15'])
        cache_service._table.query.return_value = {'Items': items}

        cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-16'
        )

        call_args = mock_dynamodb.meta.client.batch_write_item.call_args
        delete_req = call_args[1]['RequestItems']['Cost_Cache_Table'][0]
        assert delete_req == {
            'DeleteRequest': {
                'Key': {
                    'pk': 'user@example.com#123456789012',
                    'sk': 'DAILY#2024-01-15'
                }
            }
        }


class TestPagination:
    """Tests for handling DynamoDB query pagination."""

    def test_handles_paginated_query_results(self, cache_service, mock_dynamodb):
        """Should follow pagination to get all items before deleting."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        page1_items = _make_cache_items(['2024-01-15', '2024-01-16'])
        page2_items = _make_cache_items(['2024-01-17', '2024-01-18'])

        cache_service._table.query.side_effect = [
            {'Items': page1_items, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'y'}},
            {'Items': page2_items},
        ]

        result = cache_service.invalidate('user@example.com', '123456789012')

        assert result == 4
        assert cache_service._table.query.call_count == 2

    def test_handles_paginated_query_with_date_range(self, cache_service, mock_dynamodb):
        """Should handle pagination when querying with date range."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        page1_items = _make_cache_items(['2024-01-15'])
        page2_items = _make_cache_items(['2024-01-16'])

        cache_service._table.query.side_effect = [
            {'Items': page1_items, 'LastEvaluatedKey': {'pk': 'x', 'sk': 'y'}},
            {'Items': page2_items},
        ]

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-17'
        )

        assert result == 2


class TestRetryBehavior:
    """Tests for retry logic on unprocessed items."""

    @patch('cache_service.time.sleep')
    def test_retries_unprocessed_deletes(self, mock_sleep, cache_service, mock_dynamodb):
        """Should retry unprocessed delete items with exponential backoff."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15'])
        cache_service._table.query.return_value = {'Items': items}

        unprocessed_item = {'DeleteRequest': {'Key': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            {'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}},
            {'UnprocessedItems': {}},
        ]

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-16'
        )

        assert result == 1
        mock_sleep.assert_called_once_with(0.1)

    @patch('cache_service.time.sleep')
    def test_max_3_retries_for_unprocessed(self, mock_sleep, cache_service, mock_dynamodb):
        """Should stop retrying after 3 attempts."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15'])
        cache_service._table.query.return_value = {'Items': items}

        unprocessed_item = {'DeleteRequest': {'Key': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.return_value = {
            'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}
        }

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-16'
        )

        # 1 item attempted - 1 unprocessed = 0 deleted
        assert result == 0
        # 1 initial + 3 retries = 4 total calls
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 4
        assert mock_sleep.call_args_list == [
            call(0.1),
            call(0.2),
            call(0.4),
        ]


class TestErrorHandling:
    """Tests for error handling during invalidation."""

    def test_query_failure_returns_zero(self, cache_service, mock_dynamodb):
        """Should return 0 if the query to find items fails."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        cache_service._table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-18'
        )

        assert result == 0
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_batch_delete_failure_continues(self, cache_service, mock_dynamodb):
        """Should continue with remaining batches if one batch fails."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        # 30 items = 2 batches
        items = _make_cache_items([f'2024-01-{d:02d}' for d in range(1, 31)])
        cache_service._table.query.return_value = {'Items': items}

        # First batch fails, second succeeds
        mock_dynamodb.meta.client.batch_write_item.side_effect = [
            ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'BatchWriteItem'
            ),
            {'UnprocessedItems': {}},
        ]

        result = cache_service.invalidate('user@example.com', '123456789012')

        # Only second batch (5 items) succeeded
        assert result == 5
        assert mock_dynamodb.meta.client.batch_write_item.call_count == 2


class TestOwnershipVerification:
    """Tests that ownership is verified before invalidation."""

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
            cache_service.invalidate(
                'user@example.com', '123456789012',
                start_date='2024-01-15', end_date='2024-01-18'
            )

        # Should not attempt to query or delete
        cache_service._table.query.assert_not_called()
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()

    def test_ownership_verified_before_deletion(self, cache_service, mock_dynamodb):
        """Ownership check should happen before any query or delete."""
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
            'Query'
        )
        mock_dynamodb.Table.side_effect = lambda name: (
            mock_accounts_table if name == 'MemberPortal-Accounts'
            else cache_service._table
        )

        with pytest.raises(RuntimeError):
            cache_service.invalidate('user@example.com', '123456789012')

        cache_service._table.query.assert_not_called()
        mock_dynamodb.meta.client.batch_write_item.assert_not_called()


class TestReturnCount:
    """Tests that the correct count of deleted items is returned."""

    def test_returns_exact_count_of_deleted_items(self, cache_service, mock_dynamodb):
        """Should return the exact number of successfully deleted items."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15', '2024-01-16', '2024-01-17'])
        cache_service._table.query.return_value = {'Items': items}

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-18'
        )

        assert result == 3

    @patch('cache_service.time.sleep')
    def test_count_excludes_unprocessed_items(self, mock_sleep, cache_service, mock_dynamodb):
        """Count should not include items that remained unprocessed."""
        _mock_ownership_pass(cache_service, mock_dynamodb)
        items = _make_cache_items(['2024-01-15', '2024-01-16'])
        cache_service._table.query.return_value = {'Items': items}

        # 1 of 2 items remains unprocessed after all retries
        unprocessed_item = {'DeleteRequest': {'Key': {'pk': 'x', 'sk': 'y'}}}
        mock_dynamodb.meta.client.batch_write_item.return_value = {
            'UnprocessedItems': {'Cost_Cache_Table': [unprocessed_item]}
        }

        result = cache_service.invalidate(
            'user@example.com', '123456789012',
            start_date='2024-01-15', end_date='2024-01-17'
        )

        # 2 attempted - 1 unprocessed = 1 deleted
        assert result == 1
