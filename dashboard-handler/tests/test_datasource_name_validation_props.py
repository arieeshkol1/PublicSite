"""Property-based tests for DataSourceStore name validation.

Tests the data source name validation logic using hypothesis to verify that:
- Empty strings (0 chars) are rejected
- Names > 100 characters are rejected
- All names with length between 1 and 100 characters are accepted
- Whitespace, special characters, and unicode are handled correctly

Validates: Requirements 7.3, 7.4
"""

import sys
import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_store import DataSourceStore, DataSourceStoreError
from constants import MAX_DATASOURCE_NAME_LENGTH


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    mock = MagicMock()
    # Mock the table and its methods
    mock.Table.return_value = MagicMock()
    return mock


@pytest.fixture
def store(mock_dynamodb):
    """Create a DataSourceStore with mock DynamoDB."""
    return DataSourceStore(dynamodb_resource=mock_dynamodb)


# Strategy for generating strings of varying lengths (0 to 200 chars)
# Include whitespace, special characters, and unicode
test_strings = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs"),  # Exclude control and surrogates
        blacklist_characters="\x00"
    ),
    min_size=0,
    max_size=200
)


class TestDataSourceNameValidationProperties:
    """Property-based tests for data source name validation.
    
    **Validates: Requirements 7.3, 7.4**
    
    Requirement 7.3: Data source names must be 1-100 characters
    Requirement 7.4: Invalid names (empty or > 100 chars) must be rejected
    """

    @given(name=st.text(min_size=0, max_size=0))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture]
    )
    def test_reject_empty_name(self, store, name):
        """Property: Empty string (0 chars) is always rejected.
        
        For any empty string, the save method must raise DataSourceStoreError
        with a 400 status code.
        """
        config = {"datasource_name": name}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400
        error_msg = exc_info.value.message.lower()
        assert "1" in error_msg or "empty" in error_msg or "least" in error_msg, \
            f"Expected error about minimum length, got: {exc_info.value.message}"

    @given(name=st.text(min_size=101, max_size=300))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture]
    )
    def test_reject_name_exceeding_max_length(self, store, name):
        """Property: Name > 100 characters is always rejected.
        
        For any string with length > MAX_DATASOURCE_NAME_LENGTH (100),
        the save method must raise DataSourceStoreError with 400 status.
        """
        config = {"datasource_name": name}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400
        error_msg = exc_info.value.message.lower()
        assert "100" in error_msg or "maximum" in error_msg or "exceeds" in error_msg, \
            f"Expected error about max length, got: {exc_info.value.message}"

    @given(name=st.text(min_size=1, max_size=100))
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture]
    )
    def test_accept_valid_name_length(self, store, name):
        """Property: All names with 1 <= length <= 100 are accepted.
        
        For any string with length between 1 and MAX_DATASOURCE_NAME_LENGTH (100),
        the save method must succeed without raising an exception.
        """
        config = {
            "datasource_name": name,
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        # Mock the table methods to track save calls
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        # Should not raise an exception
        result = store.save("user@example.com", config)
        
        # Verify the result has expected fields
        assert "datasource_id" in result
        assert "updated_at" in result
        assert result["datasource_id"] is not None
        assert result["updated_at"] is not None


class TestDataSourceNameValidationEdgeCases:
    """Edge case unit tests for data source name validation."""

    def test_accept_single_character_name(self, store):
        """Single character name (minimum valid length) is accepted."""
        config = {
            "datasource_name": "A",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_accept_exactly_100_char_name(self, store):
        """Name with exactly 100 characters (maximum valid length) is accepted."""
        name = "A" * 100  # Exactly 100 chars
        config = {
            "datasource_name": name,
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_reject_101_char_name(self, store):
        """Name with 101 characters (exceeds max) is rejected."""
        name = "A" * 101  # 101 chars
        config = {"datasource_name": name}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400

    def test_accept_name_with_whitespace(self, store):
        """Name with leading/trailing/internal whitespace is accepted."""
        config = {
            "datasource_name": "  My Data Source  ",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_accept_name_with_special_characters(self, store):
        """Name with special characters and symbols is accepted."""
        config = {
            "datasource_name": "Data-Source_123.v2!@#$%",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_accept_name_with_unicode_characters(self, store):
        """Name with unicode characters (emoji, non-ASCII) is accepted."""
        config = {
            "datasource_name": "Data源 🎯 Données",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_accept_name_with_newlines_and_tabs(self, store):
        """Name with newlines and tabs is accepted (validation happens, not filtered)."""
        config = {
            "datasource_name": "My\nData\tSource",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_reject_non_string_name(self, store):
        """Non-string name (e.g., integer, None, list) is rejected."""
        config = {"datasource_name": 12345}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400

    def test_reject_none_name(self, store):
        """None as name is rejected."""
        config = {"datasource_name": None}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400

    def test_reject_missing_name_field(self, store):
        """Missing datasource_name field in config is treated as empty string."""
        config = {
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400


class TestDataSourceNameValidationBoundaries:
    """Boundary value tests for data source name validation."""

    def test_boundary_length_99_chars(self, store):
        """Name with 99 characters (just below max) is accepted."""
        name = "A" * 99
        config = {
            "datasource_name": name,
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_boundary_length_2_chars(self, store):
        """Name with 2 characters (just above min) is accepted."""
        config = {
            "datasource_name": "AB",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None

    def test_boundary_only_spaces_name(self, store):
        """Name consisting only of spaces is accepted (not empty string)."""
        config = {
            "datasource_name": "     ",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None


class TestDataSourceNameValidationDocumentation:
    """Tests that verify documented behavior from requirements."""

    def test_requirement_7_3_name_length_constraint(self, store):
        """Requirement 7.3: Data source names must be 1-100 characters."""
        # Valid case
        config = {
            "datasource_name": "My Custom Source",
            "accounts": [],
            "attributes": [],
            "timeframe": {},
            "filters": []
        }
        
        store.table.put_item = MagicMock()
        store.table.query = MagicMock(return_value={"Count": 0, "Items": []})
        store.table.get_item = MagicMock(return_value={})
        
        result = store.save("user@example.com", config)
        assert result["datasource_id"] is not None
        
        # Invalid case - too long
        config["datasource_name"] = "A" * 101
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400

    def test_requirement_7_4_reject_invalid_names(self, store):
        """Requirement 7.4: Invalid names (empty or > 100 chars) must be rejected."""
        # Empty string
        config = {"datasource_name": ""}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400
        
        # Exceeds maximum
        config = {"datasource_name": "X" * 101}
        
        with pytest.raises(DataSourceStoreError) as exc_info:
            store.save("user@example.com", config)
        
        assert exc_info.value.status_code == 400
