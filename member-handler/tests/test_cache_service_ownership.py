"""Unit tests for CacheService account ownership verification (Task 3.1).

Tests the _verify_account_ownership method and its integration into
get_cost_data and write_cost_data methods.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cache_service import CacheService
from cache_types import CostDataItem


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock_resource = MagicMock()
    return mock_resource


@pytest.fixture
def cache_service(mock_dynamodb):
    """Create a CacheService instance with mocked DynamoDB."""
    return CacheService(table_name='Cost_Cache_Table', dynamodb_resource=mock_dynamodb)


class TestVerifyAccountOwnership:
    """Tests for _verify_account_ownership method."""

    def test_empty_account_ids_returns_true(self, cache_service):
        """Empty account_ids list should return True without querying."""
        result = cache_service._verify_account_ownership('user@example.com', [])
        assert result is True

    def test_owned_account_returns_true(self, cache_service, mock_dynamodb):
        """Account that belongs to member should return True."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [
                {'accountId': '123456789012'},
                {'accountId': '987654321098'},
            ]
        }
        mock_dynamodb.Table.return_value = mock_table

        result = cache_service._verify_account_ownership(
            'user@example.com', ['123456789012']
        )
        assert result is True

    def test_multiple_owned_accounts_returns_true(self, cache_service, mock_dynamodb):
        """Multiple accounts that all belong to member should return True."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [
                {'accountId': '123456789012'},
                {'accountId': '987654321098'},
                {'accountId': '111222333444'},
            ]
        }
        mock_dynamodb.Table.return_value = mock_table

        result = cache_service._verify_account_ownership(
            'user@example.com', ['123456789012', '987654321098']
        )
        assert result is True

    def test_unowned_account_raises_permission_error(self, cache_service, mock_dynamodb):
        """Account not belonging to member should raise PermissionError."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [
                {'accountId': '123456789012'},
            ]
        }
        mock_dynamodb.Table.return_value = mock_table

        with pytest.raises(PermissionError) as exc_info:
            cache_service._verify_account_ownership(
                'user@example.com', ['999999999999']
            )
        assert '999999999999' in str(exc_info.value)
        assert 'user@example.com' in str(exc_info.value)

    def test_partial_ownership_raises_permission_error(self, cache_service, mock_dynamodb):
        """If one of multiple accounts is not owned, should raise PermissionError."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [
                {'accountId': '123456789012'},
            ]
        }
        mock_dynamodb.Table.return_value = mock_table

        with pytest.raises(PermissionError) as exc_info:
            cache_service._verify_account_ownership(
                'user@example.com', ['123456789012', '999999999999']
            )
        assert '999999999999' in str(exc_info.value)

    def test_dynamodb_error_raises_runtime_error(self, cache_service, mock_dynamodb):
        """DynamoDB ClientError should raise RuntimeError."""
        mock_table = MagicMock()
        mock_table.query.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DDB error'}},
            'Query'
        )
        mock_dynamodb.Table.return_value = mock_table

        with pytest.raises(RuntimeError) as exc_info:
            cache_service._verify_account_ownership(
                'user@example.com', ['123456789012']
            )
        assert 'Failed to verify account ownership' in str(exc_info.value)

    def test_member_with_no_accounts_raises_permission_error(self, cache_service, mock_dynamodb):
        """Member with no accounts should raise PermissionError for any account."""
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        mock_dynamodb.Table.return_value = mock_table

        with pytest.raises(PermissionError):
            cache_service._verify_account_ownership(
                'newuser@example.com', ['123456789012']
            )

    def test_queries_correct_table(self, cache_service, mock_dynamodb):
        """Should query the MemberPortal-Accounts table."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [{'accountId': '123456789012'}]
        }
        mock_dynamodb.Table.return_value = mock_table

        cache_service._verify_account_ownership('user@example.com', ['123456789012'])

        mock_dynamodb.Table.assert_called_with('MemberPortal-Accounts')


class TestGetCostDataOwnershipIntegration:
    """Tests that get_cost_data enforces ownership verification."""

    def test_get_cost_data_rejects_unowned_account(self, cache_service, mock_dynamodb):
        """get_cost_data should raise PermissionError for unowned account."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [{'accountId': '111111111111'}]
        }
        mock_dynamodb.Table.return_value = mock_table

        with pytest.raises(PermissionError):
            cache_service.get_cost_data(
                member_id='user@example.com',
                account_id='999999999999',
                start_date='2024-01-01',
                end_date='2024-01-31',
            )

    def test_get_cost_data_allows_owned_account(self, cache_service, mock_dynamodb):
        """get_cost_data should proceed for owned account."""
        # First call: ownership check (accounts table)
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.return_value = {
            'Items': [{'accountId': '123456789012'}]
        }

        # Second call: cache table query
        mock_cache_table = MagicMock()
        mock_cache_table.query.return_value = {'Items': []}

        def table_side_effect(name):
            if name == 'MemberPortal-Accounts':
                return mock_accounts_table
            return mock_cache_table

        mock_dynamodb.Table.side_effect = table_side_effect

        result = cache_service.get_cost_data(
            member_id='user@example.com',
            account_id='123456789012',
            start_date='2024-01-01',
            end_date='2024-01-31',
        )
        assert result.cache_status == 'miss'


class TestWriteCostDataOwnershipIntegration:
    """Tests that write_cost_data enforces ownership verification."""

    def test_write_cost_data_rejects_unowned_account(self, cache_service, mock_dynamodb):
        """write_cost_data should raise PermissionError for unowned account."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            'Items': [{'accountId': '111111111111'}]
        }
        mock_dynamodb.Table.return_value = mock_table

        items = [
            CostDataItem(
                date='2024-01-15',
                cost_amount=42.57,
                currency='USD',
                service_breakdown={'Amazon EC2': 25.30},
                fetched_at='2024-01-16T08:30:00Z',
            )
        ]

        with pytest.raises(PermissionError):
            cache_service.write_cost_data(
                member_id='user@example.com',
                account_id='999999999999',
                items=items,
            )

    def test_write_cost_data_allows_owned_account(self, cache_service, mock_dynamodb):
        """write_cost_data should proceed for owned account."""
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.return_value = {
            'Items': [{'accountId': '123456789012'}]
        }

        mock_cache_table = MagicMock()

        def table_side_effect(name):
            if name == 'MemberPortal-Accounts':
                return mock_accounts_table
            return mock_cache_table

        mock_dynamodb.Table.side_effect = table_side_effect

        # Mock the batch_write_item on the client
        mock_client = MagicMock()
        mock_client.batch_write_item.return_value = {'UnprocessedItems': {}}
        mock_dynamodb.meta.client = mock_client

        items = [
            CostDataItem(
                date='2024-01-15',
                cost_amount=42.57,
                currency='USD',
                service_breakdown={'Amazon EC2': 25.30},
                fetched_at='2024-01-16T08:30:00Z',
            )
        ]

        result = cache_service.write_cost_data(
            member_id='user@example.com',
            account_id='123456789012',
            items=items,
        )
        assert result is True

    def test_write_cost_data_empty_items_skips_ownership_check(self, cache_service, mock_dynamodb):
        """write_cost_data with empty items should still verify ownership."""
        mock_accounts_table = MagicMock()
        mock_accounts_table.query.return_value = {
            'Items': [{'accountId': '123456789012'}]
        }
        mock_dynamodb.Table.return_value = mock_accounts_table

        result = cache_service.write_cost_data(
            member_id='user@example.com',
            account_id='123456789012',
            items=[],
        )
        assert result is True
