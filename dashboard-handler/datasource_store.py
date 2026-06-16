"""Data Source Store for the Custom Data Source Wizard.

CRUD operations for saved data source configurations stored per user in DynamoDB.
Uses member_email as partition key for data isolation (Requirement 10.3).
All items use DATASOURCE#{uuid} sort key prefix in the DashboardLayouts table.
"""

import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from constants import (
    MAX_DATASOURCE_NAME_LENGTH,
    MAX_DATASOURCES_PER_MEMBER,
)


class DataSourceStoreError(Exception):
    """Base exception for DataSourceStore errors."""

    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DataSourceStore:
    """Manages data source configuration persistence in DynamoDB.

    All operations are scoped to the authenticated member's partition key,
    ensuring data isolation between users (Requirement 10.3).
    """

    def __init__(self, dynamodb_resource=None, table_name="DashboardLayouts"):
        """Initialize DataSourceStore with optional DynamoDB resource.

        Args:
            dynamodb_resource: A boto3 DynamoDB resource. If None, creates default.
            table_name: Name of the DashboardLayouts DynamoDB table.
        """
        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource("dynamodb")
        self.table = dynamodb_resource.Table(table_name)

    def save(self, member_email, config):
        """Create or update a saved data source configuration.

        Validates name length (1-100 chars) and enforces per-member limit.

        Args:
            member_email: The authenticated member's email (partition key).
            config: Dict with datasource_name and configuration fields
                (accounts, attributes, timeframe, filters, etc.).

        Returns:
            Dict with datasource_id and updated_at on success.

        Raises:
            DataSourceStoreError: On validation failure or limit exceeded.
        """
        datasource_name = config.get("datasource_name", "")

        # Validate name length (Requirement 7.3, 7.4)
        if not isinstance(datasource_name, str) or not (
            1 <= len(datasource_name) <= MAX_DATASOURCE_NAME_LENGTH
        ):
            raise DataSourceStoreError(
                f"Data source name must be between 1 and "
                f"{MAX_DATASOURCE_NAME_LENGTH} characters",
                status_code=400,
            )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check if updating existing datasource by ID
        datasource_id = config.get("datasource_id")

        if datasource_id:
            # Verify the datasource exists for this member before updating
            existing = self._get_item(member_email, datasource_id)
            if existing is None:
                raise DataSourceStoreError(
                    "Data source not found", status_code=404
                )
        else:
            # Creating new datasource - check limit (Requirement 8.1)
            existing_count = self._count_datasources(member_email)
            if existing_count >= MAX_DATASOURCES_PER_MEMBER:
                raise DataSourceStoreError(
                    f"Data source limit reached. Maximum "
                    f"{MAX_DATASOURCES_PER_MEMBER} data sources per member",
                    status_code=409,
                )
            datasource_id = str(uuid.uuid4())

        # Build DynamoDB item
        item = {
            "pk": member_email,
            "sk": f"DATASOURCE#{datasource_id}",
            "datasource_name": datasource_name,
            "config": {
                "accounts": config.get("accounts", []),
                "attributes": config.get("attributes", []),
                "timeframe": config.get("timeframe", {}),
                "filters": config.get("filters", []),
            },
            "updated_at": now,
        }

        # Preserve created_at if updating, set it if creating
        existing_item = self._get_item(member_email, datasource_id)
        if existing_item and existing_item.get("created_at"):
            item["created_at"] = existing_item["created_at"]
        else:
            item["created_at"] = now

        self.table.put_item(Item=item)

        return {"datasource_id": datasource_id, "updated_at": now}

    def get(self, member_email, datasource_id):
        """Retrieve a specific data source by ID, scoped to the member.

        Returns 404 if not found or belongs to a different partition,
        without revealing existence under other members (Requirement 10.3).

        Args:
            member_email: The authenticated member's email.
            datasource_id: The data source identifier.

        Returns:
            Data source dict if found.

        Raises:
            DataSourceStoreError: With 404 status if not found.
        """
        item = self._get_item(member_email, datasource_id)

        if item is None:
            raise DataSourceStoreError(
                "Data source not found", status_code=404
            )

        return self._format_datasource(item)

    def list_all(self, member_email):
        """List all data sources for a member, ordered by created_at descending.

        Only returns data sources belonging to the specified member
        (Requirement 10.3, 8.3).

        Args:
            member_email: The authenticated member's email.

        Returns:
            List of data source dicts belonging to the member, sorted by
            created_at descending.
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email)
                & Key("sk").begins_with("DATASOURCE#")
            )
        )

        items = response.get("Items", [])

        # Sort by created_at descending (Requirement 8.3)
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return [self._format_datasource(item) for item in items]

    def delete(self, member_email, datasource_id):
        """Delete a data source scoped to the member's partition key.

        Verifies ownership via pk match before deleting (Requirement 8.5).

        Args:
            member_email: The authenticated member's email.
            datasource_id: The data source identifier to delete.

        Returns:
            True if deleted successfully, False if not found.
        """
        # Verify the datasource exists for this member before deleting
        item = self._get_item(member_email, datasource_id)
        if item is None:
            return False

        self.table.delete_item(
            Key={"pk": member_email, "sk": f"DATASOURCE#{datasource_id}"}
        )

        return True

    def _get_item(self, member_email, datasource_id):
        """Get a single item from DynamoDB by pk and sk.

        Args:
            member_email: Partition key value.
            datasource_id: Data source ID (without DATASOURCE# prefix).

        Returns:
            The DynamoDB item dict, or None if not found.
        """
        response = self.table.get_item(
            Key={
                "pk": member_email,
                "sk": f"DATASOURCE#{datasource_id}",
            }
        )
        return response.get("Item")

    def _count_datasources(self, member_email):
        """Count existing data sources for a member.

        Args:
            member_email: The member's email.

        Returns:
            Integer count of existing data sources.
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email)
                & Key("sk").begins_with("DATASOURCE#")
            ),
            Select="COUNT",
        )
        return response.get("Count", 0)

    def _format_datasource(self, item):
        """Format a DynamoDB item as a data source response dict.

        Args:
            item: Raw DynamoDB item.

        Returns:
            Formatted data source dict suitable for API responses.
        """
        datasource_id = item.get("sk", "").replace("DATASOURCE#", "")
        return {
            "datasource_id": datasource_id,
            "datasource_name": item.get("datasource_name", ""),
            "config": item.get("config", {}),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }
