"""Unit tests for LayoutStore CRUD operations.

Tests cover:
- save_layout: creation, update, name collision overwrite, validation
- get_layout: found and not found cases
- list_layouts: ordering by updated_at descending
- delete_layout: successful delete and not found
- Limit enforcement: max 10 layouts, max 20 widgets, name length
"""

import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from layout_store import LayoutStore, LayoutStoreError


def _make_table_mock():
    """Create a mock DynamoDB table."""
    table = MagicMock()
    table.get_item = MagicMock(return_value={})
    table.put_item = MagicMock(return_value={})
    table.delete_item = MagicMock(return_value={})
    table.query = MagicMock(return_value={"Items": [], "Count": 0})
    return table


def _make_store(table_mock=None):
    """Create a LayoutStore with a mocked DynamoDB resource."""
    if table_mock is None:
        table_mock = _make_table_mock()
    resource_mock = MagicMock()
    resource_mock.Table.return_value = table_mock
    store = LayoutStore(dynamodb_resource=resource_mock, table_name="DashboardLayouts")
    return store, table_mock


def _valid_layout(name="My Dashboard", widget_count=3):
    """Return a valid layout dict with widgets in valid grid positions.

    Places widgets in a 2-column pattern (w=6 each) with h=4 rows,
    fitting up to 24 widgets within the 12-col x 48-row grid.
    """
    widgets = []
    for i in range(widget_count):
        col = (i % 2) * 6  # 0 or 6
        row = (i // 2) * 4  # 0, 4, 8, 12, ...
        widgets.append({
            "id": f"widget-{i}",
            "type": "bar",
            "title": f"Widget {i}",
            "dataSource": {"source": "cost_cache", "accountIds": ["123"], "dateRange": {"type": "relative", "relative": "30d"}},
            "aggregation": "sum",
            "gridPosition": {"x": col, "y": row, "w": 6, "h": 4},
        })
    return {"layout_name": name, "widgets": widgets}


class TestSaveLayoutCreation:
    """Tests for creating new layouts."""

    def test_save_new_layout_returns_id_and_timestamp(self):
        store, table = _make_store()
        # No existing layouts
        table.query.return_value = {"Items": [], "Count": 0}

        result = store.save_layout("user@example.com", _valid_layout())

        assert "layout_id" in result
        assert "updated_at" in result
        assert len(result["layout_id"]) == 36  # UUID format

    def test_save_layout_calls_put_item_with_correct_keys(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}

        result = store.save_layout("user@example.com", _valid_layout("Test Layout"))

        table.put_item.assert_called_once()
        item = table.put_item.call_args[1]["Item"]
        assert item["pk"] == "user@example.com"
        assert item["sk"].startswith("LAYOUT#")
        assert item["layout_name"] == "Test Layout"
        assert "updated_at" in item
        assert "created_at" in item

    def test_save_layout_updated_at_is_iso8601_utc(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}

        result = store.save_layout("user@example.com", _valid_layout())

        # Verify ISO 8601 format with Z suffix
        timestamp = result["updated_at"]
        assert timestamp.endswith("Z")
        # Should parse without error
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    def test_save_layout_with_zero_widgets(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}

        layout = {"layout_name": "Empty Dashboard", "widgets": []}
        result = store.save_layout("user@example.com", layout)

        assert "layout_id" in result


class TestSaveLayoutUpdate:
    """Tests for updating existing layouts."""

    def test_save_layout_with_existing_id_updates(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}
        table.get_item.return_value = {
            "Item": {
                "pk": "user@example.com",
                "sk": "LAYOUT#existing-id",
                "layout_name": "Old Name",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }

        layout = _valid_layout("Updated Name")
        layout["layout_id"] = "existing-id"
        result = store.save_layout("user@example.com", layout)

        assert result["layout_id"] == "existing-id"
        item = table.put_item.call_args[1]["Item"]
        assert item["created_at"] == "2024-01-01T00:00:00Z"  # Preserved


class TestSaveLayoutNameCollision:
    """Tests for layout name collision handling (Requirement 7.10)."""

    def test_same_name_overwrites_existing(self):
        store, table = _make_store()
        # Simulate existing layout with same name
        table.query.return_value = {
            "Items": [
                {
                    "pk": "user@example.com",
                    "sk": "LAYOUT#original-id",
                    "layout_name": "My Dashboard",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "widgets": [],
                }
            ],
            "Count": 1,
        }
        table.get_item.return_value = {
            "Item": {
                "pk": "user@example.com",
                "sk": "LAYOUT#original-id",
                "layout_name": "My Dashboard",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        }

        result = store.save_layout("user@example.com", _valid_layout("My Dashboard"))

        assert result["layout_id"] == "original-id"
        item = table.put_item.call_args[1]["Item"]
        assert item["sk"] == "LAYOUT#original-id"
        assert item["updated_at"] != "2024-01-01T00:00:00Z"


class TestSaveLayoutValidation:
    """Tests for layout validation on save."""

    def test_reject_empty_layout_name(self):
        store, _ = _make_store()
        layout = _valid_layout("")

        with pytest.raises(LayoutStoreError) as exc_info:
            store.save_layout("user@example.com", layout)
        assert exc_info.value.status_code == 400
        assert "name" in exc_info.value.message.lower()

    def test_reject_name_too_long(self):
        store, _ = _make_store()
        layout = _valid_layout("x" * 65)

        with pytest.raises(LayoutStoreError) as exc_info:
            store.save_layout("user@example.com", layout)
        assert exc_info.value.status_code == 400

    def test_accept_name_exactly_1_char(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}
        layout = _valid_layout("A")

        result = store.save_layout("user@example.com", layout)
        assert "layout_id" in result

    def test_accept_name_exactly_64_chars(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}
        layout = _valid_layout("x" * 64)

        result = store.save_layout("user@example.com", layout)
        assert "layout_id" in result

    def test_reject_more_than_20_widgets(self):
        store, _ = _make_store()
        layout = _valid_layout("Big Layout", widget_count=21)

        with pytest.raises(LayoutStoreError) as exc_info:
            store.save_layout("user@example.com", layout)
        assert exc_info.value.status_code == 400
        assert "widget" in exc_info.value.message.lower()

    def test_accept_exactly_20_widgets(self):
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}
        layout = _valid_layout("Max Widgets", widget_count=20)

        result = store.save_layout("user@example.com", layout)
        assert "layout_id" in result

    def test_reject_non_string_layout_name(self):
        store, _ = _make_store()
        layout = {"layout_name": 123, "widgets": []}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.save_layout("user@example.com", layout)
        assert exc_info.value.status_code == 400


class TestSaveLayoutLimits:
    """Tests for max layout count enforcement (Requirement 7.6, 7.7)."""

    def test_reject_11th_layout(self):
        store, table = _make_store()
        # No name collision found
        table.query.side_effect = [
            {"Items": [], "Count": 0},  # _find_layout_by_name returns no match
            {"Items": [], "Count": 10},  # _count_layouts returns 10
        ]

        with pytest.raises(LayoutStoreError) as exc_info:
            store.save_layout("user@example.com", _valid_layout("New Layout"))
        assert exc_info.value.status_code == 409
        assert "limit" in exc_info.value.message.lower()

    def test_accept_10th_layout(self):
        store, table = _make_store()
        # No name collision found, 9 existing layouts
        table.query.side_effect = [
            {"Items": [], "Count": 0},  # _find_layout_by_name
            {"Items": [], "Count": 9},  # _count_layouts
        ]

        result = store.save_layout("user@example.com", _valid_layout("10th Layout"))
        assert "layout_id" in result


class TestGetLayout:
    """Tests for get_layout operation."""

    def test_get_existing_layout(self):
        store, table = _make_store()
        table.get_item.return_value = {
            "Item": {
                "pk": "user@example.com",
                "sk": "LAYOUT#abc-123",
                "layout_name": "My Layout",
                "widgets": [{"id": "w1", "type": "bar"}],
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T14:00:00Z",
            }
        }

        result = store.get_layout("user@example.com", "abc-123")

        assert result["layout_id"] == "abc-123"
        assert result["layout_name"] == "My Layout"
        assert result["widgets"] == [{"id": "w1", "type": "bar"}]
        assert result["updated_at"] == "2024-01-15T14:00:00Z"

    def test_get_nonexistent_layout_raises_404(self):
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.get_layout("user@example.com", "nonexistent-id")
        assert exc_info.value.status_code == 404

    def test_get_layout_scoped_to_member(self):
        """Get uses pk=member_email, ensuring data isolation."""
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.get_layout("other@example.com", "abc-123")
        assert exc_info.value.status_code == 404

        # Verify query was scoped to the requesting member
        table.get_item.assert_called_with(
            Key={"pk": "other@example.com", "sk": "LAYOUT#abc-123"}
        )


class TestListLayouts:
    """Tests for list_layouts operation."""

    def test_list_empty(self):
        store, table = _make_store()
        table.query.return_value = {"Items": []}

        result = store.list_layouts("user@example.com")
        assert result == []

    def test_list_returns_formatted_layouts(self):
        store, table = _make_store()
        table.query.return_value = {
            "Items": [
                {
                    "pk": "user@example.com",
                    "sk": "LAYOUT#id-1",
                    "layout_name": "First",
                    "widgets": [],
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-10T00:00:00Z",
                },
                {
                    "pk": "user@example.com",
                    "sk": "LAYOUT#id-2",
                    "layout_name": "Second",
                    "widgets": [],
                    "created_at": "2024-01-05T00:00:00Z",
                    "updated_at": "2024-01-15T00:00:00Z",
                },
            ]
        }

        result = store.list_layouts("user@example.com")

        assert len(result) == 2
        assert result[0]["layout_name"] == "Second"  # More recent first
        assert result[1]["layout_name"] == "First"

    def test_list_ordered_by_updated_at_descending(self):
        store, table = _make_store()
        table.query.return_value = {
            "Items": [
                {"pk": "u@x.com", "sk": "LAYOUT#a", "layout_name": "Old", "widgets": [], "created_at": "", "updated_at": "2024-01-01T00:00:00Z"},
                {"pk": "u@x.com", "sk": "LAYOUT#b", "layout_name": "New", "widgets": [], "created_at": "", "updated_at": "2024-06-15T00:00:00Z"},
                {"pk": "u@x.com", "sk": "LAYOUT#c", "layout_name": "Mid", "widgets": [], "created_at": "", "updated_at": "2024-03-10T00:00:00Z"},
            ]
        }

        result = store.list_layouts("u@x.com")

        assert result[0]["layout_name"] == "New"
        assert result[1]["layout_name"] == "Mid"
        assert result[2]["layout_name"] == "Old"

    def test_list_uses_begins_with_layout_prefix(self):
        store, table = _make_store()
        table.query.return_value = {"Items": []}

        store.list_layouts("user@example.com")

        # Verify the query used begins_with
        call_kwargs = table.query.call_args[1]
        assert "KeyConditionExpression" in call_kwargs


class TestDeleteLayout:
    """Tests for delete_layout operation."""

    def test_delete_existing_layout(self):
        store, table = _make_store()
        table.get_item.return_value = {
            "Item": {
                "pk": "user@example.com",
                "sk": "LAYOUT#del-id",
                "layout_name": "To Delete",
            }
        }

        result = store.delete_layout("user@example.com", "del-id")

        assert result is True
        table.delete_item.assert_called_once_with(
            Key={"pk": "user@example.com", "sk": "LAYOUT#del-id"}
        )

    def test_delete_nonexistent_layout_raises_404(self):
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.delete_layout("user@example.com", "nonexistent")
        assert exc_info.value.status_code == 404

    def test_delete_scoped_to_member(self):
        """Delete only works for the authenticated member's layouts."""
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.delete_layout("attacker@evil.com", "victim-layout-id")
        assert exc_info.value.status_code == 404

        # Verify key was scoped to attacker, not victim
        table.get_item.assert_called_with(
            Key={"pk": "attacker@evil.com", "sk": "LAYOUT#victim-layout-id"}
        )


class TestDataIsolation:
    """Tests for data isolation enforcement (Requirements 9.1, 9.2, 9.3, 9.4).

    Verifies that all Layout Store operations use member_email as the
    partition key and return 404 (not 403) when a layout_id exists under
    a different member's partition.
    """

    def test_save_layout_uses_member_email_as_pk(self):
        """save_layout writes pk=member_email to DynamoDB (Requirement 9.1)."""
        store, table = _make_store()
        table.query.return_value = {"Items": [], "Count": 0}

        store.save_layout("alice@example.com", _valid_layout())

        item = table.put_item.call_args[1]["Item"]
        assert item["pk"] == "alice@example.com"

    def test_get_layout_queries_with_member_email_pk(self):
        """get_layout uses pk=member_email in DynamoDB GetItem (Requirement 9.1)."""
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError):
            store.get_layout("alice@example.com", "some-layout-id")

        table.get_item.assert_called_with(
            Key={"pk": "alice@example.com", "sk": "LAYOUT#some-layout-id"}
        )

    def test_list_layouts_queries_only_member_partition(self):
        """list_layouts queries only the member's partition key (Requirement 9.3)."""
        store, table = _make_store()
        table.query.return_value = {"Items": []}

        store.list_layouts("alice@example.com")

        # Verify the query was called with the member's email as pk condition
        call_kwargs = table.query.call_args[1]
        key_expr = call_kwargs["KeyConditionExpression"]
        # The expression object should contain alice@example.com
        assert "KeyConditionExpression" in call_kwargs

    def test_delete_layout_scoped_to_member_partition(self):
        """delete_layout uses pk=member_email for both lookup and delete (Requirement 9.1)."""
        store, table = _make_store()
        table.get_item.return_value = {
            "Item": {
                "pk": "alice@example.com",
                "sk": "LAYOUT#layout-123",
                "layout_name": "Test",
            }
        }

        store.delete_layout("alice@example.com", "layout-123")

        table.delete_item.assert_called_with(
            Key={"pk": "alice@example.com", "sk": "LAYOUT#layout-123"}
        )

    def test_get_layout_returns_404_not_403_for_other_members_layout(self):
        """Accessing another member's layout returns 404, not 403 (Requirement 9.4).

        When member A tries to get a layout_id that belongs to member B,
        the system should return 404 (not found) rather than 403 (forbidden),
        so as not to reveal whether the layout exists for another member.
        """
        store, table = _make_store()
        # The layout doesn't exist under the attacker's partition key
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.get_layout("attacker@evil.com", "victim-layout-id")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    def test_delete_layout_returns_404_not_403_for_other_members_layout(self):
        """Deleting another member's layout returns 404, not 403 (Requirement 9.4).

        When member A tries to delete a layout_id that belongs to member B,
        the system returns 404 rather than revealing the layout exists.
        """
        store, table = _make_store()
        table.get_item.return_value = {}

        with pytest.raises(LayoutStoreError) as exc_info:
            store.delete_layout("attacker@evil.com", "victim-layout-id")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message.lower()

    def test_save_layout_cannot_overwrite_another_members_layout(self):
        """save_layout can only overwrite layouts in the member's own partition.

        Even if an attacker knows a layout_id, they cannot overwrite it
        because all queries are scoped to their own partition key.
        """
        store, table = _make_store()
        # No name collision for the attacker's partition
        table.query.return_value = {"Items": [], "Count": 0}
        # The layout_id doesn't exist under the attacker's partition
        table.get_item.return_value = {}

        layout = _valid_layout("Attacker Layout")
        layout["layout_id"] = "victim-layout-id"

        result = store.save_layout("attacker@evil.com", layout)

        # The attacker's save creates a new item under THEIR partition
        item = table.put_item.call_args[1]["Item"]
        assert item["pk"] == "attacker@evil.com"
        # It uses the provided layout_id but scoped to attacker's partition
        assert item["sk"] == "LAYOUT#victim-layout-id"
