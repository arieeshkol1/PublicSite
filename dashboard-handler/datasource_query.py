"""Data Source Query Engine for the Custom Data Source Wizard.

Provides read-only querying against Cost_Cache_Table in DynamoDB.
Orchestrates ownership verification, DynamoDB query execution,
server-side filtering, attribute projection, and pagination.

The sole data source is DynamoDB with pk="{email}#{accountId}" and
sk="DAILY#{date}". Cost_Cache_Table items have service_breakdown
(dict of service_name→cost) that is flattened into individual records
with fields: date, account_id, service, cost_amount, currency, cloud_provider.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

import logging
import os
from datetime import date, datetime, timedelta

import boto3
from boto3.dynamodb.conditions import Key

from constants import (
    DATASOURCE_ATTRIBUTE_TYPES,
    DATASOURCE_AVAILABLE_ATTRIBUTES,
    DATASOURCE_FILTER_OPERATORS,
    DATASOURCE_MAX_TOTAL_ROWS,
    DATASOURCE_PAGE_SIZE,
    DATASOURCE_TIMEFRAME_PRESETS,
)

logger = logging.getLogger(__name__)

# Table names from environment or defaults
COST_CACHE_TABLE = os.environ.get("COST_CACHE_TABLE", "Cost_Cache_Table")
ACCOUNTS_TABLE = os.environ.get("ACCOUNTS_TABLE", "MemberPortal-Accounts")


class DataSourceQueryEngine:
    """Executes data source queries against Cost_Cache_Table.

    Provides read-only access to cost data with ownership verification,
    server-side filtering, attribute projection, and pagination.
    Uses DynamoDB query operations (not scan) with partition key and
    sort key range conditions.
    """

    def __init__(self, dynamodb_resource=None):
        """Initialize DataSourceQueryEngine with optional DynamoDB resource.

        Args:
            dynamodb_resource: A boto3 DynamoDB resource. If None,
                creates a default resource from the environment.
        """
        self.dynamodb = dynamodb_resource or boto3.resource("dynamodb")

    def execute(self, member_email: str, query_config: dict) -> dict:
        """Execute a data source query and return paginated results.

        Orchestrates: verify ownership → resolve timeframe → query DynamoDB
        → flatten service_breakdown → filter → project → paginate.

        Args:
            member_email: The authenticated member's email.
            query_config: Dict with keys:
                - account_ids: list of account IDs to query
                - timeframe: dict with 'preset' or 'start_date'/'end_date'
                - filters: list of filter dicts (optional)
                - attributes: list of attribute names to return (optional)
                - page: page number (1-indexed, optional, default 1)

        Returns:
            Dict with 'rows', 'total_count', 'page', 'page_size',
            'total_pages', and 'has_more' keys.
            On error, returns dict with 'error' and 'status_code' keys.
        """
        # Extract query parameters
        account_ids = query_config.get("account_ids", [])
        timeframe = query_config.get("timeframe", {})
        filters = query_config.get("filters", [])
        attributes = query_config.get("attributes", DATASOURCE_AVAILABLE_ATTRIBUTES[:])
        page = query_config.get("page", 1)

        # Validate account_ids
        if not account_ids:
            return {"error": "At least one account_id is required", "status_code": 400}

        # Step 1: Verify account ownership
        try:
            self._verify_ownership(member_email, account_ids)
        except PermissionError as e:
            return {"error": str(e), "status_code": 403}

        # Step 2: Resolve timeframe to concrete date range
        try:
            start_date, end_date = self._resolve_timeframe(timeframe)
        except ValueError as e:
            return {"error": str(e), "status_code": 400}

        # Step 3: Query DynamoDB for each account
        raw_records = []
        for account_id in account_ids:
            query_params = self._build_query_params(
                member_email, account_id, start_date, end_date
            )
            items = self._execute_query(query_params)
            # Flatten service_breakdown into individual records
            raw_records.extend(
                self._flatten_cost_items(items, account_id)
            )

        # Step 4: Apply server-side filters
        filtered_records = self._apply_filters(raw_records, filters)

        # Step 5: Project attributes
        projected_records = self._project_attributes(filtered_records, attributes)

        # Step 6: Paginate results
        result = self._paginate(projected_records, page)

        return result

    def _verify_ownership(self, member_email: str, account_ids: list) -> None:
        """Verify all requested accounts are owned by the member.

        Queries MemberPortal-Accounts table to confirm each account_id
        belongs to the authenticated member. Rejects the entire query
        if any account is not owned.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of account IDs to verify.

        Raises:
            PermissionError: If any account is not owned by the member.
        """
        if not account_ids:
            return

        table = self.dynamodb.Table(ACCOUNTS_TABLE)

        for account_id in account_ids:
            response = table.query(
                KeyConditionExpression=(
                    Key("memberEmail").eq(member_email)
                    & Key("accountId").eq(account_id)
                ),
            )

            items = response.get("Items", [])
            if not items:
                raise PermissionError(
                    f"Account {account_id} not owned by authenticated user"
                )

    def _resolve_timeframe(self, timeframe: dict) -> tuple[str, str]:
        """Resolve a timeframe configuration to concrete start/end dates.

        Supports preset timeframes (last_7d, last_30d, last_90d,
        current_month, previous_month) and custom date ranges.

        Args:
            timeframe: Dict with either:
                - 'preset': one of the supported preset keys
                - 'start_date' and 'end_date': YYYY-MM-DD strings

        Returns:
            Tuple of (start_date, end_date) strings in YYYY-MM-DD format.

        Raises:
            ValueError: If timeframe is invalid or dates are malformed.
        """
        if not isinstance(timeframe, dict):
            raise ValueError("Timeframe must be an object")

        preset = timeframe.get("preset")
        start_date_str = timeframe.get("start_date")
        end_date_str = timeframe.get("end_date")

        if preset:
            return self._resolve_preset(preset)
        elif start_date_str and end_date_str:
            return self._resolve_custom_range(start_date_str, end_date_str)
        else:
            raise ValueError(
                "Timeframe must specify either 'preset' or both "
                "'start_date' and 'end_date'"
            )

    def _resolve_preset(self, preset: str) -> tuple[str, str]:
        """Resolve a timeframe preset to concrete date range.

        Args:
            preset: One of last_7d, last_30d, last_90d, current_month,
                previous_month.

        Returns:
            Tuple of (start_date, end_date) strings in YYYY-MM-DD format.

        Raises:
            ValueError: If preset is not supported.
        """
        if preset not in DATASOURCE_TIMEFRAME_PRESETS:
            raise ValueError(
                f"Unsupported timeframe preset: {preset}. "
                f"Supported: {sorted(DATASOURCE_TIMEFRAME_PRESETS.keys())}"
            )

        today = date.today()
        preset_value = DATASOURCE_TIMEFRAME_PRESETS[preset]

        if isinstance(preset_value, int):
            # last_7d, last_30d, last_90d: go back N days
            start_date = today - timedelta(days=preset_value)
            end_date = today
        elif preset_value == "current_month":
            start_date = today.replace(day=1)
            end_date = today
        elif preset_value == "previous_month":
            # First day of current month minus 1 day = last day of previous month
            first_of_current = today.replace(day=1)
            end_date = first_of_current - timedelta(days=1)
            start_date = end_date.replace(day=1)
        else:
            raise ValueError(f"Unsupported timeframe preset value: {preset_value}")

        return (start_date.isoformat(), end_date.isoformat())

    def _resolve_custom_range(
        self, start_date_str: str, end_date_str: str
    ) -> tuple[str, str]:
        """Validate and return custom date range.

        Args:
            start_date_str: Start date in YYYY-MM-DD format.
            end_date_str: End date in YYYY-MM-DD format.

        Returns:
            Tuple of (start_date, end_date) strings in YYYY-MM-DD format.

        Raises:
            ValueError: If dates are invalid or start >= end.
        """
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid start_date format: {start_date_str}. Expected YYYY-MM-DD"
            )

        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid end_date format: {end_date_str}. Expected YYYY-MM-DD"
            )

        if start_date > end_date:
            raise ValueError(
                f"start_date ({start_date_str}) must be before or equal to "
                f"end_date ({end_date_str})"
            )

        # Cap range at 365 days
        span_days = (end_date - start_date).days
        if span_days > 365:
            raise ValueError(
                f"Date range span ({span_days} days) exceeds maximum "
                f"allowed (365 days)"
            )

        return (start_date_str, end_date_str)

    def _build_query_params(
        self,
        member_email: str,
        account_id: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """Construct DynamoDB query parameters.

        Builds a query with pk="{email}#{accountId}" and sk range
        "DAILY#{start_date}" to "DAILY#{end_date}".

        Args:
            member_email: The authenticated member's email.
            account_id: The account ID to query.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            Dict with 'table_name', 'key_condition', 'pk', 'sk_start',
            'sk_end' keys for the DynamoDB query.
        """
        pk = f"{member_email}#{account_id}"
        sk_start = f"DAILY#{start_date}"
        sk_end = f"DAILY#{end_date}"

        return {
            "table_name": COST_CACHE_TABLE,
            "pk": pk,
            "sk_start": sk_start,
            "sk_end": sk_end,
        }

    def _execute_query(self, query_params: dict) -> list[dict]:
        """Execute a DynamoDB query and handle pagination.

        Args:
            query_params: Dict from _build_query_params with table_name,
                pk, sk_start, sk_end.

        Returns:
            List of raw DynamoDB items.
        """
        table = self.dynamodb.Table(query_params["table_name"])
        pk = query_params["pk"]
        sk_start = query_params["sk_start"]
        sk_end = query_params["sk_end"]

        response = table.query(
            KeyConditionExpression=(
                Key("pk").eq(pk)
                & Key("sk").between(sk_start, sk_end)
            ),
        )

        items = response.get("Items", [])

        # Handle DynamoDB pagination (LastEvaluatedKey)
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=(
                    Key("pk").eq(pk)
                    & Key("sk").between(sk_start, sk_end)
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        return items

    def _flatten_cost_items(
        self, items: list[dict], account_id: str
    ) -> list[dict]:
        """Flatten Cost_Cache_Table items into normalized records.

        Each item's service_breakdown is expanded into individual records
        with fields: date, account_id, service, cost_amount, currency,
        cloud_provider.

        Args:
            items: Raw DynamoDB items from Cost_Cache_Table.
            account_id: The account ID for these items.

        Returns:
            List of flattened records with standard attribute fields.
        """
        records = []
        for item in items:
            sk = item.get("sk", "")
            # Extract date from sort key "DAILY#YYYY-MM-DD"
            date_str = sk.replace("DAILY#", "") if sk.startswith("DAILY#") else ""
            currency = item.get("currency", "USD")
            cloud_provider = item.get("cloud_provider", "custom")

            service_breakdown = item.get("service_breakdown", {})
            if service_breakdown and isinstance(service_breakdown, dict):
                for service_name, cost_value in service_breakdown.items():
                    try:
                        cost_amount = float(cost_value) if cost_value is not None else 0.0
                    except (TypeError, ValueError):
                        cost_amount = 0.0

                    records.append({
                        "date": date_str,
                        "account_id": account_id,
                        "service": service_name,
                        "cost_amount": cost_amount,
                        "currency": currency,
                        "cloud_provider": cloud_provider,
                    })
            else:
                # If no service breakdown, use cost_amount as total
                total_cost = item.get("cost_amount", 0)
                try:
                    cost_amount = float(total_cost) if total_cost is not None else 0.0
                except (TypeError, ValueError):
                    cost_amount = 0.0

                records.append({
                    "date": date_str,
                    "account_id": account_id,
                    "service": "_total",
                    "cost_amount": cost_amount,
                    "currency": currency,
                    "cloud_provider": cloud_provider,
                })

        return records

    def _apply_filters(
        self, records: list[dict], filters: list[dict]
    ) -> list[dict]:
        """Apply server-side filter conditions to records.

        Supports operators: equals, not_equals, greater_than, less_than.
        All filters are applied conjunctively (AND logic).

        Args:
            records: List of flattened record dicts.
            filters: List of filter dicts, each with 'attribute',
                'operator', and 'value' keys.

        Returns:
            Filtered list of records satisfying all conditions.
        """
        if not filters:
            return records

        result = []
        for record in records:
            if self._record_passes_filters(record, filters):
                result.append(record)

        return result

    def _record_passes_filters(
        self, record: dict, filters: list[dict]
    ) -> bool:
        """Check if a single record passes all filter conditions.

        Args:
            record: A single flattened record dict.
            filters: List of filter configurations.

        Returns:
            True if the record satisfies all filters, False otherwise.
        """
        for f in filters:
            attribute = f.get("attribute", "")
            operator = f.get("operator", "")
            value = f.get("value")

            # Skip invalid filter definitions
            if not attribute or not operator:
                continue

            # Get field value from record
            field_value = record.get(attribute)
            if field_value is None:
                return False

            # Determine attribute type for comparison
            attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute, "text")

            if not self._evaluate_condition(
                field_value, operator, value, attr_type
            ):
                return False

        return True

    def _evaluate_condition(
        self, field_value, operator: str, target_value, attr_type: str
    ) -> bool:
        """Evaluate a single filter condition.

        Args:
            field_value: The actual value from the record.
            operator: The filter operator (equals, not_equals, greater_than,
                less_than).
            target_value: The target value to compare against.
            attr_type: The attribute type ('text' or 'numeric').

        Returns:
            True if the condition is satisfied, False otherwise.
        """
        if operator == "equals":
            if attr_type == "numeric":
                try:
                    return float(field_value) == float(target_value)
                except (TypeError, ValueError):
                    return False
            else:
                return str(field_value) == str(target_value)

        elif operator == "not_equals":
            if attr_type == "numeric":
                try:
                    return float(field_value) != float(target_value)
                except (TypeError, ValueError):
                    return True
            else:
                return str(field_value) != str(target_value)

        elif operator == "greater_than":
            try:
                return float(field_value) > float(target_value)
            except (TypeError, ValueError):
                return False

        elif operator == "less_than":
            try:
                return float(field_value) < float(target_value)
            except (TypeError, ValueError):
                return False

        # Unknown operator - exclude record
        return False

    def _project_attributes(
        self, records: list[dict], attributes: list[str]
    ) -> list[dict]:
        """Return only selected attribute columns from records.

        Args:
            records: List of flattened record dicts.
            attributes: List of attribute names to include in output.
                If empty or None, returns all available attributes.

        Returns:
            List of records containing only the specified attributes.
        """
        if not attributes:
            attributes = DATASOURCE_AVAILABLE_ATTRIBUTES[:]

        # Filter to only valid attributes
        valid_attributes = [
            attr for attr in attributes
            if attr in DATASOURCE_AVAILABLE_ATTRIBUTES
        ]

        if not valid_attributes:
            valid_attributes = DATASOURCE_AVAILABLE_ATTRIBUTES[:]

        projected = []
        for record in records:
            projected_record = {}
            for attr in valid_attributes:
                if attr in record:
                    projected_record[attr] = record[attr]
            projected.append(projected_record)

        return projected

    def _paginate(self, records: list[dict], page: int) -> dict:
        """Paginate results with max 500 per page, capped at 10,000 total.

        Args:
            records: Full list of records after filtering and projection.
            page: Page number (1-indexed). Defaults to 1 if invalid.

        Returns:
            Dict with 'rows', 'total_count', 'page', 'page_size',
            'total_pages', and 'has_more' keys.
        """
        # Ensure page is valid
        if not isinstance(page, int) or page < 1:
            page = 1

        # Cap total records at DATASOURCE_MAX_TOTAL_ROWS (10,000)
        total_count = len(records)
        capped_count = min(total_count, DATASOURCE_MAX_TOTAL_ROWS)

        # Calculate pagination
        page_size = DATASOURCE_PAGE_SIZE
        total_pages = max(1, (capped_count + page_size - 1) // page_size)

        # Clamp page to valid range
        if page > total_pages:
            page = total_pages

        # Calculate slice indices
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, capped_count)

        # Extract page of records
        page_records = records[start_idx:end_idx]

        return {
            "rows": page_records,
            "total_count": capped_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_more": page < total_pages,
        }

    def get_operators_for_attribute(self, attribute: str) -> list[str]:
        """Get the valid filter operators for a given attribute.

        Returns the operator list based on the attribute's type from
        DATASOURCE_ATTRIBUTE_TYPES and DATASOURCE_FILTER_OPERATORS.

        Args:
            attribute: The attribute name to get operators for.

        Returns:
            List of operator strings for this attribute's type.

        Raises:
            KeyError: If the attribute is not in DATASOURCE_ATTRIBUTE_TYPES.
            TypeError: If attribute is not a string.
        """
        if not isinstance(attribute, str):
            raise TypeError(
                f"Attribute must be a string, got {type(attribute).__name__}"
            )

        if not attribute:
            raise ValueError("Attribute name cannot be empty")

        if attribute not in DATASOURCE_ATTRIBUTE_TYPES:
            raise KeyError(
                f"Unknown attribute: '{attribute}'. "
                f"Available attributes: {DATASOURCE_AVAILABLE_ATTRIBUTES}"
            )

        # Get the attribute type
        attr_type = DATASOURCE_ATTRIBUTE_TYPES[attribute]

        # Get operators for this type
        if attr_type not in DATASOURCE_FILTER_OPERATORS:
            raise KeyError(
                f"No operators defined for type '{attr_type}' "
                f"used by attribute '{attribute}'"
            )

        return DATASOURCE_FILTER_OPERATORS[attr_type]
