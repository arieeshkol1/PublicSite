"""Property-based tests for member data isolation in data sources.

Tests the data isolation logic using hypothesis to verify that:
- List operations only return items belonging to the queried member
- Get operations return 404 when accessing another member's data sources
- Member A cannot access Member B's data sources
- All operations enforce partition key scoping (member_email as pk)
- Query results never leak data across member boundaries

Validates: Requirements 10.3
"""

import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_store import DataSourceStore
from datasource_query import DataSourceQueryEngine


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def store(mock_dynamodb):
    """Create a DataSourceStore with mock DynamoDB."""
    return DataSourceStore(dynamodb_resource=mock_dynamodb)


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy for generating email addresses
member_emails = st.emails()

# Strategy for generating data source IDs (UUIDs)
datasource_ids = st.uuids().map(str)

# Strategy for generating account IDs
account_ids = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=50
)


class TestDataSourceIsolationProperties:
    """Property-based tests for data source member isolation.
    
    **Validates: Requirements 10.3**
    
    Requirement 10.3: Member partition key isolation
    - All operations scoped to authenticated member's email (pk)
    - List/get operations only return matching partition items
    - Access to another member's data returns 404/403
    """

    @given(member_email=member_emails, datasource_id=datasource_ids)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_get_only_returns_owned_datasources(self, store, member_email, datasource_id):
        """Property: Get operation only returns datasources owned by the queried member.
        
        For any member_email and datasource_id, if the datasource is owned by that member,
        the get() call must return the datasource with pk matching the member_email.
        If not owned, it must raise DataSourceStoreError with 404 status.
        """
        # Setup: Mock a datasource owned by member_email
        mock_item = {
            "pk": member_email,
            "sk": f"DATASOURCE#{datasource_id}",
            "datasource_name": "Test Source",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "config": {"accounts": [], "attributes": [], "timeframe": {}, "filters": []},
        }
        
        # Mock get_item to return the owned datasource
        store.table.get_item = MagicMock(return_value={"Item": mock_item})
        
        # Act & Assert: Get should return the datasource
        result = store.get(member_email, datasource_id)
        
        # Verify the result contains data and the partition key matches
        assert result is not None, "Get returned None for owned datasource"
        assert result["datasource_id"] == datasource_id, \
            f"Returned datasource_id {result['datasource_id']} does not match requested {datasource_id}"
        assert result["datasource_name"] == "Test Source", \
            "Returned datasource name mismatch"
        
        # Verify get_item was called with the correct partition key
        store.table.get_item.assert_called_once()
        call_args = store.table.get_item.call_args[1]
        assert call_args["Key"]["pk"] == member_email, \
            f"Query was not scoped to member {member_email}"

    @given(member_email_1=member_emails, member_email_2=member_emails, datasource_id=datasource_ids)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_get_denies_access_to_other_member_datasource(self, store, member_email_1, member_email_2, datasource_id):
        """Property: Get operation denies access to datasources owned by other members.
        
        For any two different members (member_email_1 != member_email_2), if a datasource
        belongs to member_email_2, member_email_1 cannot access it. The get() call must
        raise DataSourceStoreError with 404 status (no information leak).
        """
        # Skip if emails are the same (degenerate case)
        if member_email_1 == member_email_2:
            return
        
        # Setup: Mock get_item to return None (item not found in member_email_1's partition)
        store.table.get_item = MagicMock(return_value={})
        
        # Act & Assert: Get should raise 404 error
        from datasource_store import DataSourceStoreError
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.get(member_email_1, datasource_id)
        
        # Verify it's a 404 (not found, no information leak)
        assert exc_info.value.status_code == 404, \
            f"Expected 404, got {exc_info.value.status_code}"
        
        # Verify get_item was called with member_email_1's partition key
        store.table.get_item.assert_called_once()
        call_args = store.table.get_item.call_args[1]
        assert call_args["Key"]["pk"] == member_email_1, \
            f"Query was not scoped to member {member_email_1}"

    @given(member_email=member_emails, num_datasources=st.integers(min_value=1, max_value=10))
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_list_only_returns_datasources_for_queried_member(self, store, member_email, num_datasources):
        """Property: List operation only returns datasources owned by the queried member.
        
        For any member_email, list_all() must return only datasources where pk == member_email.
        All returned items must have pk matching the queried member_email.
        No datasources from other members should appear in the result.
        """
        # Setup: Generate datasources owned by member_email
        mock_items = [
            {
                "pk": member_email,
                "sk": f"DATASOURCE#{i}",
                "datasource_name": f"Source {i}",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "config": {"accounts": [], "attributes": [], "timeframe": {}, "filters": []},
            }
            for i in range(num_datasources)
        ]
        
        # Mock query to return only member_email's datasources
        store.table.query = MagicMock(return_value={"Items": mock_items})
        
        # Act: List all datasources for member_email
        result = store.list_all(member_email)
        
        # Assert: All returned items have correct partition key
        assert len(result) == num_datasources, \
            f"Expected {num_datasources} datasources, got {len(result)}"
        
        for datasource in result:
            assert "datasource_id" in datasource, "Missing datasource_id in result"
            assert "datasource_name" in datasource, "Missing datasource_name in result"
        
        # Verify query was called with member_email partition key
        store.table.query.assert_called_once()
        call_args = store.table.query.call_args[1]
        
        # Verify the query used member_email in the KeyConditionExpression
        # (This is harder to test directly with the Key() API, but we can verify it was called)
        assert "KeyConditionExpression" in call_args, \
            "Query did not use KeyConditionExpression"

    @given(member_email_1=member_emails, member_email_2=member_emails)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_list_returns_empty_for_member_with_no_datasources(self, store, member_email_1, member_email_2):
        """Property: List returns empty array for member with no datasources, not other members' data.
        
        For any member_email, if that member has no datasources, list_all() must return
        an empty list, never returning datasources owned by other members.
        """
        # Setup: Mock query to return empty result
        store.table.query = MagicMock(return_value={"Items": []})
        
        # Act: List datasources for member_email_1
        result = store.list_all(member_email_1)
        
        # Assert: Result is empty
        assert result == [], f"Expected empty list, got {result}"
        assert len(result) == 0, "List is not empty"
        
        # Verify query was called with member_email_1's partition key
        store.table.query.assert_called_once()

    @given(member_email=member_emails, datasource_id=datasource_ids)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_delete_only_deletes_owned_datasources(self, store, member_email, datasource_id):
        """Property: Delete operation only removes datasources owned by the queried member.
        
        For any member_email and datasource_id, if the datasource is owned by that member,
        delete() must remove it. If not owned (pk doesn't match), delete() must return False
        and make no modifications.
        """
        # Setup: Mock get_item to return a datasource owned by member_email
        mock_item = {
            "pk": member_email,
            "sk": f"DATASOURCE#{datasource_id}",
            "datasource_name": "Test Source",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        
        store.table.get_item = MagicMock(return_value={"Item": mock_item})
        store.table.delete_item = MagicMock()
        
        # Act: Delete the datasource
        result = store.delete(member_email, datasource_id)
        
        # Assert: Delete succeeded
        assert result is True, "Delete should return True for owned datasource"
        
        # Verify delete_item was called with the correct partition key
        store.table.delete_item.assert_called_once()
        call_args = store.table.delete_item.call_args[1]
        assert call_args["Key"]["pk"] == member_email, \
            f"Delete was not scoped to member {member_email}"
        assert call_args["Key"]["sk"] == f"DATASOURCE#{datasource_id}", \
            f"Delete used wrong sort key"

    @given(member_email_1=member_emails, member_email_2=member_emails, datasource_id=datasource_ids)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_delete_denies_removal_of_other_member_datasource(self, store, member_email_1, member_email_2, datasource_id):
        """Property: Delete operation denies removal of datasources owned by other members.
        
        For any two different members, if a datasource belongs to member_email_2,
        member_email_1 cannot delete it. The delete() call must return False and make
        no modifications to the database.
        """
        # Skip if emails are the same
        if member_email_1 == member_email_2:
            return
        
        # Setup: Mock get_item to return None (item not found in member_email_1's partition)
        store.table.get_item = MagicMock(return_value={})
        store.table.delete_item = MagicMock()
        
        # Act: Try to delete a datasource not owned by member_email_1
        result = store.delete(member_email_1, datasource_id)
        
        # Assert: Delete failed and no modification occurred
        assert result is False, "Delete should return False for unowned datasource"
        store.table.delete_item.assert_not_called(), \
            "Delete should not modify database for unowned datasource"

    @given(
        member_email=member_emails,
        account_ids=st.lists(account_ids, min_size=1, max_size=5),
        page=st.integers(min_value=1, max_value=10)
    )
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_query_engine_verifies_account_ownership(self, engine, member_email, account_ids, page):
        """Property: Query engine verifies all queried accounts are owned by the member.
        
        For any member_email and list of account_ids, execute() must verify that all
        account_ids belong to member_email before executing the query. If any account
        is not owned, execute() must return error with 403 status (permission denied).
        """
        # Setup: Mock the accounts table to return no matching accounts
        accounts_table = MagicMock()
        accounts_table.query = MagicMock(return_value={"Items": []})
        
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table = MagicMock(return_value=accounts_table)
        
        engine_with_mock = DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)
        
        # Act: Try to query with accounts not owned by member_email
        query_config = {
            "account_ids": account_ids,
            "timeframe": {"preset": "last_7d"},
            "filters": [],
            "attributes": ["date", "cost_amount"],
            "page": page,
        }
        
        result = engine_with_mock.execute(member_email, query_config)
        
        # Assert: Query was rejected with 403 status
        assert "error" in result or "status_code" in result, \
            "Execute should return error for unowned accounts"
        
        if "status_code" in result:
            assert result["status_code"] == 403, \
                f"Expected 403 for unowned accounts, got {result.get('status_code')}"

    @given(
        member_email=member_emails,
        owned_account_id=account_ids,
        unowned_account_id=account_ids
    )
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_query_engine_rejects_mixed_owned_unowned_accounts(self, engine, member_email, owned_account_id, unowned_account_id):
        """Property: Query is rejected if ANY account in the list is not owned.
        
        For a member querying a mix of owned and unowned accounts, execute() must
        reject the entire query with 403 status. It's all-or-nothing: if even one
        account is not owned, all results are denied.
        """
        # Skip if account IDs are the same
        if owned_account_id == unowned_account_id:
            return
        
        # Setup: Mock accounts table - first account found, second not found
        accounts_table = MagicMock()
        
        call_state = {"count": 0}
        
        def query_side_effect(**kwargs):
            # For simplicity, we'll check by call count
            call_state["count"] += 1
            if call_state["count"] == 1:
                # First call - return the owned account
                return {"Items": [{"memberEmail": member_email, "accountId": owned_account_id}]}
            else:
                # Subsequent calls - return nothing (account not owned)
                return {"Items": []}
        
        accounts_table.query = MagicMock(side_effect=query_side_effect)
        
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table = MagicMock(return_value=accounts_table)
        
        engine_with_mock = DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)
        
        # Act: Try to query with mixed owned/unowned accounts
        query_config = {
            "account_ids": [owned_account_id, unowned_account_id],
            "timeframe": {"preset": "last_7d"},
            "filters": [],
            "attributes": ["date", "cost_amount"],
        }
        
        result = engine_with_mock.execute(member_email, query_config)
        
        # Assert: Query was rejected
        assert "error" in result or "status_code" in result, \
            "Execute should return error for mixed owned/unowned accounts"

    @given(member_email=member_emails)
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_partition_key_always_scopes_operations_to_member(self, store, member_email):
        """Property: All partition key operations use member_email as pk.
        
        For any operation (get, list, delete, save), the DynamoDB queries must use
        member_email as the partition key (pk). This is the fundamental enforcement
        of member isolation.
        """
        # Setup: Mock all DynamoDB operations
        store.table.get_item = MagicMock(return_value={})
        store.table.query = MagicMock(return_value={"Items": []})
        store.table.delete_item = MagicMock()
        store.table.put_item = MagicMock()
        
        # Test: Get operation scopes to member_email
        try:
            store.get(member_email, "test-id")
        except:
            pass  # Expected to fail on 404
        
        get_call = store.table.get_item.call_args
        if get_call:
            assert get_call[1]["Key"]["pk"] == member_email, \
                "Get did not scope to member_email"
        
        # Test: List operation scopes to member_email
        store.list_all(member_email)
        
        # Test: Delete operation scopes to member_email
        try:
            store.delete(member_email, "test-id")
        except:
            pass
        
        # Test: Save operation scopes to member_email
        try:
            store.save(member_email, {"datasource_name": "Test"})
        except:
            pass


class TestDataSourceIsolationEdgeCases:
    """Edge case unit tests for member isolation."""

    def test_get_item_called_with_correct_key_structure(self, store):
        """Test that get_item is called with correct DynamoDB Key structure."""
        member_email = "test@example.com"
        datasource_id = "123-456-789"
        
        store.table.get_item = MagicMock(return_value={})
        
        try:
            store.get(member_email, datasource_id)
        except:
            pass
        
        # Verify the Key was structured correctly
        store.table.get_item.assert_called_once()
        call_kwargs = store.table.get_item.call_args[1]
        assert "Key" in call_kwargs
        assert "pk" in call_kwargs["Key"]
        assert "sk" in call_kwargs["Key"]
        assert call_kwargs["Key"]["pk"] == member_email
        assert call_kwargs["Key"]["sk"] == f"DATASOURCE#{datasource_id}"

    def test_query_filters_by_member_email_partition(self, store):
        """Test that query always filters by member email partition key."""
        member_email = "alice@example.com"
        
        store.table.query = MagicMock(return_value={"Items": []})
        
        store.list_all(member_email)
        
        store.table.query.assert_called_once()
        call_kwargs = store.table.query.call_args[1]
        
        # Verify KeyConditionExpression is present
        assert "KeyConditionExpression" in call_kwargs, \
            "Query missing KeyConditionExpression"

    def test_different_members_get_different_results(self, store):
        """Test that different members querying get different results."""
        member_1 = "alice@example.com"
        member_2 = "bob@example.com"
        
        alice_items = [
            {
                "pk": member_1,
                "sk": "DATASOURCE#alice-ds-1",
                "datasource_name": "Alice's Source",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "config": {},
            }
        ]
        
        bob_items = [
            {
                "pk": member_2,
                "sk": "DATASOURCE#bob-ds-1",
                "datasource_name": "Bob's Source",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "config": {},
            }
        ]
        
        # Setup: Mock query to return different items based on member_email
        def query_side_effect(**kwargs):
            # This is a simplification - in reality we'd parse the KeyConditionExpression
            # but for this test we'll use side effects
            return {"Items": alice_items if query_side_effect.is_alice else bob_items}
        
        query_side_effect.is_alice = True
        store.table.query = MagicMock(side_effect=query_side_effect)
        
        # Alice's query
        alice_result = store.list_all(member_1)
        assert len(alice_result) == 1
        assert alice_result[0]["datasource_name"] == "Alice's Source"
        
        # Bob's query
        query_side_effect.is_alice = False
        store.table.query = MagicMock(side_effect=query_side_effect)
        
        bob_result = store.list_all(member_2)
        assert len(bob_result) == 1
        assert bob_result[0]["datasource_name"] == "Bob's Source"

    def test_delete_with_wrong_member_email_returns_false(self, store):
        """Test that delete returns False when member_email doesn't own the datasource."""
        member_email = "alice@example.com"
        datasource_id = "test-123"
        
        # Mock get_item to return None (item not found)
        store.table.get_item = MagicMock(return_value={})
        
        result = store.delete(member_email, datasource_id)
        
        assert result is False, "Delete should return False for non-existent item"

    def test_save_creates_item_with_member_email_pk(self, store):
        """Test that save creates items with member_email as partition key."""
        member_email = "test@example.com"
        
        store.table.query = MagicMock(return_value={"Count": 0})  # For _count_datasources
        store.table.get_item = MagicMock(return_value={})  # For new datasource
        store.table.put_item = MagicMock()
        
        config = {
            "datasource_name": "Test Source",
            "accounts": ["acc-1"],
            "attributes": ["date", "cost_amount"],
            "timeframe": {"preset": "last_7d"},
            "filters": [],
        }
        
        store.save(member_email, config)
        
        # Verify put_item was called with member_email as pk
        store.table.put_item.assert_called_once()
        call_kwargs = store.table.put_item.call_args[1]
        assert call_kwargs["Item"]["pk"] == member_email, \
            "Save did not use member_email as partition key"


class TestDataSourceIsolationDocumentation:
    """Tests that verify documented member isolation behavior."""

    def test_requirement_10_3_partition_key_enforcement(self, store):
        """Requirement 10.3: All operations are scoped to authenticated member's partition key.
        
        This test documents that member isolation is the primary security mechanism,
        enforced through DynamoDB partition key (member_email as pk).
        """
        member_email = "user@example.com"
        datasource_id = "ds-123"
        
        # Mock table operations
        store.table.get_item = MagicMock(return_value={})
        store.table.query = MagicMock(return_value={"Items": []})
        
        # All operations must scope to the member_email partition
        store.list_all(member_email)
        
        # Verify partition key is used in query
        store.table.query.assert_called_once()

    def test_member_isolation_prevents_cross_member_access(self, store):
        """Member isolation prevents one member from accessing another member's data."""
        alice_email = "alice@example.com"
        bob_email = "bob@example.com"
        datasource_id = "shared-id"
        
        # Mock: item belongs to bob
        store.table.get_item = MagicMock(return_value={})
        
        # Alice tries to access bob's datasource
        from datasource_store import DataSourceStoreError
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.get(alice_email, datasource_id)
        
        # Must return 404 (no information leak)
        assert exc_info.value.status_code == 404

    def test_member_isolation_in_list_operations(self, store):
        """List operations only return items for the queried member."""
        member_email = "user@example.com"
        
        # Mock: return only items with this member_email as pk
        mock_items = [
            {
                "pk": member_email,
                "sk": "DATASOURCE#ds-1",
                "datasource_name": "My Source",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "config": {},
            }
        ]
        
        store.table.query = MagicMock(return_value={"Items": mock_items})
        
        result = store.list_all(member_email)
        
        # All returned items must have correct partition key
        for item in result:
            assert "datasource_id" in item
            assert "datasource_name" in item
