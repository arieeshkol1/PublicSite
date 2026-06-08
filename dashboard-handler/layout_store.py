"""Layout Store for the Widget Builder Dashboard.

CRUD operations for dashboard layouts stored per user in DynamoDB.
Uses member_email as partition key for data isolation (Requirement 9.1).
"""

import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from constants import (
    LAYOUT_NAME_MAX_LENGTH,
    LAYOUT_NAME_MIN_LENGTH,
    MAX_LAYOUTS,
    MAX_WIDGETS,
)
from grid_validator import validate_grid_positions


class LayoutStoreError(Exception):
    """Base exception for LayoutStore errors."""

    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LayoutStore:
    """Manages dashboard layout persistence in DynamoDB.

    All operations are scoped to the authenticated member's partition key,
    ensuring data isolation between users (Requirement 9.1, 9.3, 9.4).
    """

    def __init__(self, dynamodb_resource=None, table_name="DashboardLayouts"):
        """Initialize LayoutStore with optional DynamoDB resource.

        Args:
            dynamodb_resource: A boto3 DynamoDB resource. If None, creates default.
            table_name: Name of the DashboardLayouts DynamoDB table.
        """
        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource("dynamodb")
        self.table = dynamodb_resource.Table(table_name)

    def save_layout(self, member_email, layout):
        """Create or update a dashboard layout.

        Validates layout name length, widget count limits, and layout count limits.
        If a layout with the same name already exists for this member, it is
        overwritten with an updated timestamp (Requirement 7.10).

        Args:
            member_email: The authenticated member's email (partition key).
            layout: Dict with layout_name, widgets, and optional layout_id.

        Returns:
            Dict with layout_id and updated_at on success.

        Raises:
            LayoutStoreError: On validation failure or limit exceeded.
        """
        layout_name = layout.get("layout_name", "")
        widgets = layout.get("widgets", [])

        # Validate layout name length (Requirement 7.9)
        if not isinstance(layout_name, str) or not (
            LAYOUT_NAME_MIN_LENGTH <= len(layout_name) <= LAYOUT_NAME_MAX_LENGTH
        ):
            raise LayoutStoreError(
                f"Layout name must be between {LAYOUT_NAME_MIN_LENGTH} and "
                f"{LAYOUT_NAME_MAX_LENGTH} characters",
                status_code=400,
            )

        # Validate widget count (Requirement 7.5, 7.8)
        if len(widgets) > MAX_WIDGETS:
            raise LayoutStoreError(
                f"Layout cannot contain more than {MAX_WIDGETS} widgets",
                status_code=400,
            )

        # Validate grid positions (Requirements 6.3, 6.4, 6.5)
        if widgets:
            grid_valid, grid_error = validate_grid_positions(widgets)
            if not grid_valid:
                raise LayoutStoreError(
                    f"Invalid grid position: {grid_error}",
                    status_code=400,
                )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check for existing layout with same name (Requirement 7.10)
        existing_layout_id = self._find_layout_by_name(member_email, layout_name)

        if existing_layout_id:
            # Overwrite existing layout with same name, update timestamp
            layout_id = existing_layout_id
        elif layout.get("layout_id"):
            # Updating existing layout by ID
            layout_id = layout["layout_id"]
        else:
            # Creating new layout - check limit (Requirement 7.6, 7.7)
            existing_count = self._count_layouts(member_email)
            if existing_count >= MAX_LAYOUTS:
                raise LayoutStoreError(
                    f"Layout limit reached. Maximum {MAX_LAYOUTS} layouts per member",
                    status_code=409,
                )
            layout_id = str(uuid.uuid4())

        # Build DynamoDB item
        item = {
            "pk": member_email,
            "sk": f"LAYOUT#{layout_id}",
            "layout_name": layout_name,
            "widgets": widgets,
            "updated_at": now,
        }

        # Preserve created_at if updating, set it if creating
        existing_item = self._get_item(member_email, layout_id)
        if existing_item and existing_item.get("created_at"):
            item["created_at"] = existing_item["created_at"]
        else:
            item["created_at"] = now

        self.table.put_item(Item=item)

        return {"layout_id": layout_id, "updated_at": now}

    def get_layout(self, member_email, layout_id):
        """Retrieve a specific layout by ID, scoped to the member.

        Returns 404 if not found, without revealing existence under other
        members (Requirement 9.4).

        Args:
            member_email: The authenticated member's email.
            layout_id: The layout identifier.

        Returns:
            Layout dict if found.

        Raises:
            LayoutStoreError: With 404 status if not found.
        """
        item = self._get_item(member_email, layout_id)

        if item is None:
            raise LayoutStoreError("Layout not found", status_code=404)

        return self._format_layout(item)

    def list_layouts(self, member_email):
        """List all layouts for a member, ordered by updated_at descending.

        Only returns layouts belonging to the specified member (Requirement 9.3).

        Args:
            member_email: The authenticated member's email.

        Returns:
            List of layout dicts belonging to the member, sorted by
            updated_at descending.
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email) & Key("sk").begins_with("LAYOUT#")
            )
        )

        items = response.get("Items", [])

        # Sort by updated_at descending (Requirement 7.2)
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return [self._format_layout(item) for item in items]

    def delete_layout(self, member_email, layout_id):
        """Delete a layout scoped to the member's partition key.

        Only deletes if the layout belongs to the specified member.

        Args:
            member_email: The authenticated member's email.
            layout_id: The layout identifier to delete.

        Returns:
            True if deleted successfully.

        Raises:
            LayoutStoreError: With 404 status if not found.
        """
        # Verify the layout exists for this member before deleting
        item = self._get_item(member_email, layout_id)
        if item is None:
            raise LayoutStoreError("Layout not found", status_code=404)

        self.table.delete_item(
            Key={"pk": member_email, "sk": f"LAYOUT#{layout_id}"}
        )

        return True

    def _get_item(self, member_email, layout_id):
        """Get a single item from DynamoDB by pk and sk.

        Args:
            member_email: Partition key value.
            layout_id: Layout ID (without LAYOUT# prefix).

        Returns:
            The DynamoDB item dict, or None if not found.
        """
        response = self.table.get_item(
            Key={"pk": member_email, "sk": f"LAYOUT#{layout_id}"}
        )
        return response.get("Item")

    def _find_layout_by_name(self, member_email, layout_name):
        """Find a layout by name for the given member.

        Args:
            member_email: The member's email.
            layout_name: The layout name to search for.

        Returns:
            The layout_id if found, None otherwise.
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email) & Key("sk").begins_with("LAYOUT#")
            )
        )

        for item in response.get("Items", []):
            if item.get("layout_name") == layout_name:
                return item["sk"].replace("LAYOUT#", "")

        return None

    def _count_layouts(self, member_email):
        """Count existing layouts for a member.

        Args:
            member_email: The member's email.

        Returns:
            Integer count of existing layouts.
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email) & Key("sk").begins_with("LAYOUT#")
            ),
            Select="COUNT",
        )
        return response.get("Count", 0)

    def _format_layout(self, item):
        """Format a DynamoDB item as a layout response dict.

        Args:
            item: Raw DynamoDB item.

        Returns:
            Formatted layout dict suitable for API responses.
        """
        layout_id = item.get("sk", "").replace("LAYOUT#", "")
        return {
            "layout_id": layout_id,
            "layout_name": item.get("layout_name", ""),
            "widgets": item.get("widgets", []),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }
