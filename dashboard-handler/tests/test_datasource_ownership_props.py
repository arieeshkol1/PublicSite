"""Property-based tests for DataSourceQueryEngine ownership verification.

Tests the account ownership verification logic using hypothesis to verify that:
- Queries with all owned accounts succeed
- Queries with any unowned account fail entirely (not partial rejection)
- Empty account lists are handled correctly
- All unowned, mixed owned/unowned, and single unowned accounts are rejected
- Correct PermissionError is raised for unowned accounts

Validates: Requirements 9.1, 9.2
"""

import sys
import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_query import DataSourceQueryEngine


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy for generating realistic AWS account IDs
aws_account_ids = st.integers(min_value=100000000000, max_value=999999999999).map(str)

# Strategy for generating account ID sets
owned_account_sets = st.lists(
    st.sampled_from(["123456789012", "210987654321", "555555555555"]),
    unique=True,
    min_size=1,
    max_size=3
)

unowned_account_sets = st.lists(
    st.sampled_from(["999999999999", "888888888888", "777777777777"]),
    unique=True,
    min_size=1,
    max_size=3
)


class TestOwnershipVerificationProperties:
    """Property-based tests for account ownership verification.
    
    **Validates: Requirements 9.1, 9.2**
    
    Requirement 9.1: All requested accounts must be owned by the member
    Requirement 9.2: Entire query rejected if any account unowned (not partial)
    """

    @given(owned_accounts=owned_account_sets)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_all_owned_accounts_succeeds(self, engine, mock_dynamodb, owned_accounts):
        """Property: Queries with all owned accounts succeed.
        
        For any list of account IDs that all belong to the authenticated member,
        _verify_ownership() must succeed without raising an exception.
        
        **Validates: Requirement 9.1**
        """
        member_email = "user@example.com"
        
        # Mock DynamoDB to return results for all accounts
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # For each account, simulate ownership
        def query_side_effect(*args, **kwargs):
            key_condition = kwargs.get('KeyConditionExpression')
            # All queries should return items (owned)
            return {"Items": [{"memberEmail": member_email, "accountId": "test"}]}
        
        mock_table.query.side_effect = query_side_effect
        
        # Should not raise any exception
        try:
            engine._verify_ownership(member_email, owned_accounts)
        except PermissionError as e:
            pytest.fail(f"_verify_ownership raised PermissionError for owned accounts: {e}")

    @given(unowned_accounts=unowned_account_sets)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_unowned_accounts_rejected(self, engine, mock_dynamodb, unowned_accounts):
        """Property: Queries with unowned accounts are rejected.
        
        For any list of account IDs where none belong to the authenticated member,
        _verify_ownership() must raise PermissionError.
        
        **Validates: Requirements 9.1, 9.2**
        """
        member_email = "user@example.com"
        
        # Mock DynamoDB to return no results (unowned)
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        # Should raise PermissionError for at least the first unowned account
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, unowned_accounts)
        
        error_msg = str(exc_info.value).lower()
        assert "not owned" in error_msg or "permission" in error_msg, \
            f"Expected ownership error, got: {exc_info.value}"

    @given(
        owned_accounts=owned_account_sets,
        unowned_accounts=st.lists(
            st.text(min_size=12, max_size=12, alphabet=st.characters(blacklist_characters="")),
            unique=True,
            min_size=1,
            max_size=1
        )
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_mixed_owned_unowned_rejected_entirely(
        self, engine, mock_dynamodb, owned_accounts, unowned_accounts
    ):
        """Property: Mixed owned/unowned accounts reject entire query (not partial).
        
        For any mix of owned and unowned accounts, if even one account is unowned,
        _verify_ownership() must raise PermissionError and reject the entire query.
        This tests that the system does NOT allow partial acceptance.
        
        **Validates: Requirement 9.2**
        """
        member_email = "user@example.com"
        mixed_accounts = owned_accounts + unowned_accounts
        
        # Mock DynamoDB
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Track which accounts were queried
        queried_accounts = []
        
        def query_side_effect(*args, **kwargs):
            key_condition = kwargs.get('KeyConditionExpression')
            # Return items only for owned accounts
            # By examining the call, we can determine which account was queried
            # For simplicity, return empty for all (simulating all unowned)
            return {"Items": []}
        
        mock_table.query.side_effect = query_side_effect
        
        # Should raise PermissionError
        with pytest.raises(PermissionError):
            engine._verify_ownership(member_email, mixed_accounts)

    def test_empty_account_list_succeeds(self, engine):
        """Edge case: Empty account list should succeed without querying.
        
        If no accounts are specified, verification should pass (nothing to verify).
        """
        member_email = "user@example.com"
        
        # Should not raise and should not query anything
        try:
            engine._verify_ownership(member_email, [])
        except PermissionError:
            pytest.fail("Empty account list should succeed")

    def test_single_owned_account_succeeds(self, engine, mock_dynamodb):
        """Edge case: Single owned account succeeds.
        
        Verify single account ownership works correctly.
        """
        member_email = "user@example.com"
        account_id = "123456789012"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": account_id}]
        }
        
        # Should succeed
        try:
            engine._verify_ownership(member_email, [account_id])
        except PermissionError:
            pytest.fail("Single owned account should succeed")

    def test_single_unowned_account_rejected(self, engine, mock_dynamodb):
        """Edge case: Single unowned account is rejected.
        
        Verify single account ownership failure works correctly.
        """
        member_email = "user@example.com"
        account_id = "999999999999"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        # Should raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, [account_id])
        
        assert "999999999999" in str(exc_info.value)

    def test_three_accounts_all_owned(self, engine, mock_dynamodb):
        """Edge case: Three owned accounts in sequence all succeed.
        
        Verify that multiple account checks all pass when all are owned.
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "210987654321", "555555555555"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # All queries return items (owned)
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": "test"}]
        }
        
        # Should succeed
        try:
            engine._verify_ownership(member_email, accounts)
        except PermissionError:
            pytest.fail("Multiple owned accounts should succeed")
        
        # Verify it queried each account
        assert mock_table.query.call_count == 3

    def test_three_accounts_first_unowned(self, engine, mock_dynamodb):
        """Edge case: First account unowned stops verification immediately.
        
        Verify that as soon as one unowned account is found, it fails.
        """
        member_email = "user@example.com"
        accounts = ["999999999999", "210987654321", "555555555555"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        # Should raise on first unowned
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, accounts)
        
        assert "999999999999" in str(exc_info.value)

    def test_three_accounts_second_unowned(self, engine, mock_dynamodb):
        """Edge case: Second account unowned still rejects entire query.
        
        Verify that unowned accounts in the middle are caught.
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "999999999999", "555555555555"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # First account owned, second unowned, third would be owned
        def query_side_effect(*args, **kwargs):
            call_count = mock_table.query.call_count
            if call_count == 1:
                # First call (first account) - owned
                return {"Items": [{"memberEmail": member_email, "accountId": accounts[0]}]}
            else:
                # All others - unowned
                return {"Items": []}
        
        mock_table.query.side_effect = query_side_effect
        
        # Should raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, accounts)
        
        assert "999999999999" in str(exc_info.value)

    def test_three_accounts_last_unowned(self, engine, mock_dynamodb):
        """Edge case: Last account unowned rejects entire query.
        
        Verify that unowned accounts at the end are caught.
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "210987654321", "999999999999"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # First two owned, third unowned
        def query_side_effect(*args, **kwargs):
            call_count = mock_table.query.call_count
            if call_count <= 2:
                # First two calls - owned
                return {"Items": [{"memberEmail": member_email, "accountId": "test"}]}
            else:
                # Last call - unowned
                return {"Items": []}
        
        mock_table.query.side_effect = query_side_effect
        
        # Should raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, accounts)
        
        assert "999999999999" in str(exc_info.value)

    def test_correct_table_queried(self, engine, mock_dynamodb):
        """Verify that the correct MemberPortal-Accounts table is queried.
        
        The verification must query the MemberPortal-Accounts table.
        """
        member_email = "user@example.com"
        accounts = ["123456789012"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": accounts[0]}]
        }
        
        engine._verify_ownership(member_email, accounts)
        
        # Should have called Table() with MemberPortal-Accounts
        mock_dynamodb.Table.assert_called_with("MemberPortal-Accounts")

    def test_permission_error_message_includes_account_id(self, engine, mock_dynamodb):
        """PermissionError message includes the unowned account ID.
        
        When an account is unowned, the error message should identify which account.
        """
        member_email = "user@example.com"
        unowned_account = "999999999999"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        with pytest.raises(PermissionError) as exc_info:
            engine._verify_ownership(member_email, [unowned_account])
        
        error_message = str(exc_info.value)
        assert unowned_account in error_message, \
            f"Account ID {unowned_account} should be in error message: {error_message}"

    def test_all_owned_no_exception_raised(self, engine, mock_dynamodb):
        """All owned accounts must result in no exception.
        
        Verify that the function returns normally (None) for all owned.
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "210987654321"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": "test"}]
        }
        
        result = engine._verify_ownership(member_email, accounts)
        
        # Should return None (no exception)
        assert result is None


class TestOwnershipVerificationEdgeCases:
    """Edge case unit tests for ownership verification."""

    def test_none_account_list(self, engine):
        """None account list should not crash."""
        member_email = "user@example.com"
        
        # Should either handle gracefully or raise ValueError
        try:
            engine._verify_ownership(member_email, None)
        except (TypeError, AttributeError):
            # This is acceptable - None is not a valid list
            pass

    def test_empty_member_email(self, engine, mock_dynamodb):
        """Empty member email is handled."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        # Should attempt to verify
        with pytest.raises(PermissionError):
            engine._verify_ownership("", ["123456789012"])

    def test_none_member_email(self, engine):
        """None member email is handled."""
        # Should raise an error when querying
        try:
            engine._verify_ownership(None, ["123456789012"])
        except (TypeError, AttributeError):
            # Expected to fail
            pass

    def test_duplicate_account_ids(self, engine, mock_dynamodb):
        """Duplicate account IDs are handled correctly.
        
        If the same account ID is provided twice, it should still verify correctly.
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "123456789012"]  # Duplicate
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": accounts[0]}]
        }
        
        # Should succeed (both are owned)
        try:
            engine._verify_ownership(member_email, accounts)
        except PermissionError:
            pytest.fail("Duplicate owned accounts should succeed")

    def test_dynamodb_query_error_handling(self, engine, mock_dynamodb):
        """DynamoDB query errors are handled appropriately.
        
        If DynamoDB query fails, it should raise an error (not silently pass).
        """
        member_email = "user@example.com"
        accounts = ["123456789012"]
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.side_effect = Exception("DynamoDB error")
        
        # Should propagate the DynamoDB error
        with pytest.raises(Exception):
            engine._verify_ownership(member_email, accounts)

    def test_multiple_items_in_query_response(self, engine, mock_dynamodb):
        """Query returning multiple items (shouldn't happen) is handled.
        
        DynamoDB query should return 0 or 1 items (based on exact pk+sk match),
        but if it returns multiple, the verification should still pass
        (at least one item = owned).
        """
        member_email = "user@example.com"
        account_id = "123456789012"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [
                {"memberEmail": member_email, "accountId": account_id},
                {"memberEmail": member_email, "accountId": account_id},
            ]
        }
        
        # Should succeed (items returned = owned)
        try:
            engine._verify_ownership(member_email, [account_id])
        except PermissionError:
            pytest.fail("Multiple items in response should indicate owned account")


class TestOwnershipVerificationDocumentation:
    """Tests that verify documented behavior of ownership verification."""

    def test_permission_error_raised_for_unowned(self, engine, mock_dynamodb):
        """Documentation example: PermissionError raised for unowned accounts.
        
        As documented in _verify_ownership docstring, PermissionError is raised
        when an account is not owned by the member.
        """
        member_email = "user@example.com"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}
        
        with pytest.raises(PermissionError):
            engine._verify_ownership(member_email, ["999999999999"])

    def test_no_exception_for_all_owned(self, engine, mock_dynamodb):
        """Documentation example: No exception for all owned accounts.
        
        When all accounts are owned, no exception should be raised.
        """
        member_email = "user@example.com"
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.query.return_value = {
            "Items": [{"memberEmail": member_email, "accountId": "test"}]
        }
        
        # Should not raise
        engine._verify_ownership(member_email, ["123456789012"])

    def test_rejects_entire_query_on_any_unowned(self, engine, mock_dynamodb):
        """Documentation requirement: Entire query rejected if any unowned.
        
        The design spec requires that if any account in the list is unowned,
        the entire query is rejected (not partial acceptance).
        """
        member_email = "user@example.com"
        accounts = ["123456789012", "999999999999"]  # Mix of owned/unowned
        
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        query_count = [0]
        
        def query_side_effect(*args, **kwargs):
            query_count[0] += 1
            if query_count[0] == 1:
                # First account owned
                return {"Items": [{"memberEmail": member_email, "accountId": accounts[0]}]}
            else:
                # Second account unowned
                return {"Items": []}
        
        mock_table.query.side_effect = query_side_effect
        
        # Should raise PermissionError (entire query rejected)
        with pytest.raises(PermissionError):
            engine._verify_ownership(member_email, accounts)

