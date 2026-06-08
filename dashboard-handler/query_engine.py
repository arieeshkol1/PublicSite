"""Generic Query Engine for the Widget Builder Dashboard.

Accepts a widget config, resolves the data source, applies
filters/dimensions/aggregations, and returns chart-ready data.

Orchestrates the full pipeline: validate → resolve date range →
verify account ownership → fetch data → filter → dimension →
aggregate → format.

Requirements: 3.1, 3.6, 10.1, 10.2, 12.1, 12.5
"""

import logging
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

from validators import validate_widget_config, resolve_date_range
from filters import apply_filters
from aggregation import group_by_dimensions, aggregate, format_for_chart

logger = logging.getLogger(__name__)

# Table names from environment or defaults
COST_CACHE_TABLE = os.environ.get("COST_CACHE_TABLE", "Cost_Cache_Table")
INVOICES_TABLE = os.environ.get("INVOICES_TABLE", "MemberPortal-Invoices")
ACCOUNTS_TABLE = os.environ.get("ACCOUNTS_TABLE", "MemberPortal-Accounts")

# Timeout for external provider API calls (seconds)
PROVIDER_API_TIMEOUT = 30


class QueryEngine:
    """Executes widget data queries against appropriate data sources.

    Supports data sources: cost_cache, invoices, openai_usage,
    commitments, business_metrics. Uses DynamoDB query operations
    (not scan) with partition key and sort key range conditions.
    """

    def __init__(self, dynamodb_resource=None):
        """Initialize QueryEngine with optional DynamoDB resource.

        Args:
            dynamodb_resource: A boto3 DynamoDB resource. If None,
                creates a default resource from the environment.
        """
        self.dynamodb = dynamodb_resource or boto3.resource("dynamodb")

    def execute(self, member_email: str, widget_config: dict) -> dict:
        """Execute a widget query and return chart-ready data.

        Orchestrates: validate → resolve date range → verify account
        ownership → fetch data → filter → dimension → aggregate → format.

        Args:
            member_email: The authenticated member's email.
            widget_config: The widget configuration dict.

        Returns:
            Dict with 'labels', 'datasets', and 'metadata' keys.
            On error, returns empty labels/datasets with error in metadata.
        """
        # Step 1: Validate widget configuration
        valid, error_msg = validate_widget_config(widget_config)
        if not valid:
            return self._error_response(error_msg)

        # Step 2: Resolve date range
        try:
            date_range = widget_config["dataSource"]["dateRange"]
            start_date, end_date = resolve_date_range(date_range)
        except (ValueError, KeyError) as e:
            return self._error_response(f"Invalid date range: {e}")

        # Step 3: Verify account ownership
        account_ids = widget_config["dataSource"].get("accountIds", [])
        try:
            owned_account_ids = self._verify_account_ownership(
                member_email, account_ids
            )
        except PermissionError as e:
            return {
                "labels": [],
                "datasets": [],
                "metadata": {"error": str(e), "status_code": 403},
            }

        # Step 4: Fetch raw data from the appropriate source
        source = widget_config["dataSource"]["source"]
        try:
            raw_data = self._resolve_data_source(
                member_email, source, account_ids, start_date, end_date
            )
        except Exception as e:
            logger.error(f"Data source error ({source}): {e}", exc_info=True)
            return self._error_response(
                f"Data source unavailable: {source}",
                period=f"{start_date} to {end_date}",
            )

        # Step 4b: Server-side filter to include only owned account data
        # Defense-in-depth: even after ownership check, ensure results contain
        # only data from verified owned accounts (Requirements 8.5, 9.5)
        if owned_account_ids is not None:
            raw_data = self._filter_by_owned_accounts(
                raw_data, owned_account_ids, member_email
            )

        # Step 5: Apply filters
        filters = widget_config.get("filters", [])
        try:
            filtered_data = apply_filters(raw_data, filters)
        except ValueError as e:
            return self._error_response(str(e))

        # Step 6: Group by dimensions
        dimensions = widget_config.get("dimensions", [])
        try:
            grouped = group_by_dimensions(filtered_data, dimensions)
        except ValueError as e:
            return self._error_response(str(e))

        # Step 7: Aggregate
        aggregation_type = widget_config.get("aggregation", "sum")
        aggregated = {}
        for key, items in grouped.items():
            aggregated[key] = aggregate(items, aggregation_type)

        # Step 8: Format for Chart.js
        widget_type = widget_config.get("type", "bar")
        chart_data = format_for_chart(aggregated, widget_type)

        # Add metadata
        total = (
            sum(chart_data["datasets"][0]["data"])
            if chart_data["datasets"] and chart_data["datasets"][0]["data"]
            else 0
        )
        chart_data["metadata"] = {
            "total": total,
            "currency": "USD",
            "period": f"{start_date} to {end_date}",
            "from_cache": source == "cost_cache",
        }

        return chart_data

    def _resolve_data_source(
        self,
        member_email: str,
        source: str,
        account_ids: list,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Fetch raw data from the appropriate DynamoDB table or provider API.

        Routes to the correct data retrieval method based on source type.
        Uses DynamoDB query operations (not scan) with partition key and
        sort key range conditions.

        Args:
            member_email: The authenticated member's email.
            source: Data source identifier (cost_cache, invoices, etc.).
            account_ids: List of account IDs to query.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of data dictionaries in normalized format.

        Raises:
            ValueError: If the source type is not supported.
            Exception: If the data source query fails.
        """
        if source == "cost_cache":
            return self._query_cost_cache(
                member_email, account_ids, start_date, end_date
            )
        elif source == "invoices":
            return self._query_invoices(
                member_email, account_ids, start_date, end_date
            )
        elif source == "openai_usage":
            return self._query_openai_usage(
                member_email, account_ids, start_date, end_date
            )
        elif source == "commitments":
            return self._query_commitments(member_email, account_ids)
        elif source == "business_metrics":
            return self._query_business_metrics(
                member_email, start_date, end_date
            )
        else:
            raise ValueError(f"Unsupported data source: {source}")

    def _query_cost_cache(
        self,
        member_email: str,
        account_ids: list,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Query DynamoDB Cost_Cache_Table for cost data.

        Uses pk="{email}#{account_id}", sk begins_with "DAILY#" with
        date range filtering via sort key conditions.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of account IDs to query.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of normalized cost data items with flattened service breakdown.
        """
        table = self.dynamodb.Table(COST_CACHE_TABLE)
        raw_data = []

        for account_id in account_ids:
            pk = f"{member_email}#{account_id}"
            sk_start = f"DAILY#{start_date}"
            sk_end = f"DAILY#{end_date}"

            # DynamoDB query with partition key and sort key range
            response = table.query(
                KeyConditionExpression=(
                    Key("pk").eq(pk)
                    & Key("sk").between(sk_start, sk_end)
                ),
            )

            items = response.get("Items", [])

            # Handle pagination
            while "LastEvaluatedKey" in response:
                response = table.query(
                    KeyConditionExpression=(
                        Key("pk").eq(pk)
                        & Key("sk").between(sk_start, sk_end)
                    ),
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            # Flatten service breakdown into individual records
            raw_data.extend(self._flatten_cost_cache_items(items, account_id))

        return raw_data

    def _flatten_cost_cache_items(
        self, items: list[dict], account_id: str
    ) -> list[dict]:
        """Flatten Cost_Cache_Table items into normalized records.

        Each item's service_breakdown is expanded into individual records
        with fields: date, service, cost_amount, currency, cloud_provider,
        account_id.

        Args:
            items: Raw DynamoDB items from Cost_Cache_Table.
            account_id: The account ID for these items.

        Returns:
            List of flattened, normalized data dicts.
        """
        normalized = []
        for item in items:
            sk = item.get("sk", "")
            # Extract date from sort key "DAILY#YYYY-MM-DD"
            date_str = sk.replace("DAILY#", "") if sk.startswith("DAILY#") else ""
            currency = item.get("currency", "USD")
            cloud_provider = item.get("cloud_provider", "aws")

            service_breakdown = item.get("service_breakdown", {})
            if service_breakdown and isinstance(service_breakdown, dict):
                for service_name, cost_value in service_breakdown.items():
                    normalized.append(
                        {
                            "date": date_str,
                            "service": service_name,
                            "cost_amount": float(cost_value)
                            if cost_value is not None
                            else 0.0,
                            "currency": currency,
                            "cloud_provider": cloud_provider,
                            "account_id": account_id,
                        }
                    )
            else:
                # If no service breakdown, use total_cost
                total_cost = item.get("total_cost", 0)
                normalized.append(
                    {
                        "date": date_str,
                        "service": "_total",
                        "cost_amount": float(total_cost)
                        if total_cost is not None
                        else 0.0,
                        "currency": currency,
                        "cloud_provider": cloud_provider,
                        "account_id": account_id,
                    }
                )

        return normalized

    def _query_invoices(
        self,
        member_email: str,
        account_ids: list,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Query MemberPortal-Invoices table for invoice data.

        Uses DynamoDB query with member email as partition key.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of account IDs to filter by.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of normalized invoice data items.
        """
        table = self.dynamodb.Table(INVOICES_TABLE)

        # Query invoices for the member
        response = table.query(
            KeyConditionExpression=(
                Key("pk").eq(member_email)
                & Key("sk").between(f"INV#{start_date}", f"INV#{end_date}")
            ),
        )

        items = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=(
                    Key("pk").eq(member_email)
                    & Key("sk").between(f"INV#{start_date}", f"INV#{end_date}")
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        # Normalize and filter by account_ids
        normalized = []
        for item in items:
            item_account = item.get("account_id", "")
            if account_ids and item_account not in account_ids:
                continue

            sk = item.get("sk", "")
            date_str = sk.replace("INV#", "") if sk.startswith("INV#") else ""

            normalized.append(
                {
                    "date": date_str,
                    "service": item.get("service", item.get("description", "_invoice")),
                    "cost_amount": float(item.get("amount", item.get("total", 0))),
                    "currency": item.get("currency", "USD"),
                    "cloud_provider": item.get("provider", "aws"),
                    "account_id": item_account,
                }
            )

        return normalized

    def _query_openai_usage(
        self,
        member_email: str,
        account_ids: list,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Fetch OpenAI usage data from the provider API.

        Calls the OpenAI provider endpoint with a 30-second timeout.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of OpenAI account/org IDs to query.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of normalized OpenAI usage data items.

        Raises:
            TimeoutError: If the API call exceeds 30 seconds.
            Exception: If the API call fails.
        """
        import requests

        openai_api_url = os.environ.get(
            "OPENAI_USAGE_API_URL",
            "https://api.openai.com/v1/usage",
        )
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        normalized = []

        for account_id in account_ids:
            try:
                response = requests.get(
                    openai_api_url,
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "OpenAI-Organization": account_id,
                    },
                    params={
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    timeout=PROVIDER_API_TIMEOUT,
                )
                response.raise_for_status()
                usage_data = response.json()

                # Normalize the OpenAI usage response
                for entry in usage_data.get("data", []):
                    normalized.append(
                        {
                            "date": entry.get("date", ""),
                            "service": entry.get(
                                "model", entry.get("service", "openai")
                            ),
                            "cost_amount": float(
                                entry.get("cost", entry.get("amount", 0))
                            ),
                            "currency": "USD",
                            "cloud_provider": "openai",
                            "account_id": account_id,
                        }
                    )

            except requests.exceptions.Timeout:
                raise TimeoutError(
                    f"OpenAI API call timed out after {PROVIDER_API_TIMEOUT}s "
                    f"for account {account_id}"
                )
            except requests.exceptions.RequestException as e:
                raise Exception(
                    f"OpenAI API error for account {account_id}: {e}"
                )

        return normalized

    def _query_commitments(
        self, member_email: str, account_ids: list
    ) -> list[dict]:
        """Query commitment/reservation data from Cost_Cache_Table.

        Looks up commitment records (Reserved Instances, Savings Plans)
        using the COMMITMENT# sort key prefix.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of account IDs to query.

        Returns:
            List of normalized commitment data items.
        """
        table = self.dynamodb.Table(COST_CACHE_TABLE)
        normalized = []

        for account_id in account_ids:
            pk = f"{member_email}#{account_id}"

            response = table.query(
                KeyConditionExpression=(
                    Key("pk").eq(pk)
                    & Key("sk").begins_with("COMMITMENT#")
                ),
            )

            items = response.get("Items", [])

            # Handle pagination
            while "LastEvaluatedKey" in response:
                response = table.query(
                    KeyConditionExpression=(
                        Key("pk").eq(pk)
                        & Key("sk").begins_with("COMMITMENT#")
                    ),
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            for item in items:
                sk = item.get("sk", "")
                commitment_id = (
                    sk.replace("COMMITMENT#", "")
                    if sk.startswith("COMMITMENT#")
                    else sk
                )

                normalized.append(
                    {
                        "date": item.get("start_date", ""),
                        "service": item.get("service", item.get("type", "commitment")),
                        "cost_amount": float(
                            item.get(
                                "monthly_cost",
                                item.get("cost_amount", item.get("amount", 0)),
                            )
                        ),
                        "currency": item.get("currency", "USD"),
                        "cloud_provider": item.get("cloud_provider", "aws"),
                        "account_id": account_id,
                        "commitment_id": commitment_id,
                        "end_date": item.get("end_date", ""),
                        "status": item.get("status", "active"),
                    }
                )

        return normalized

    def _query_business_metrics(
        self, member_email: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Query business metrics data from Cost_Cache_Table.

        Fetches METRIC# sort key prefixed records for the member.

        Args:
            member_email: The authenticated member's email.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            List of normalized business metrics data items.
        """
        table = self.dynamodb.Table(COST_CACHE_TABLE)

        # Business metrics are stored per member (no account_id)
        pk = member_email

        response = table.query(
            KeyConditionExpression=(
                Key("pk").eq(pk)
                & Key("sk").between(
                    f"METRIC#{start_date}", f"METRIC#{end_date}"
                )
            ),
        )

        items = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=(
                    Key("pk").eq(pk)
                    & Key("sk").between(
                        f"METRIC#{start_date}", f"METRIC#{end_date}"
                    )
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        normalized = []
        for item in items:
            sk = item.get("sk", "")
            date_str = (
                sk.replace("METRIC#", "") if sk.startswith("METRIC#") else ""
            )

            normalized.append(
                {
                    "date": date_str,
                    "service": item.get("metric_name", "business_metric"),
                    "cost_amount": float(item.get("value", item.get("amount", 0))),
                    "currency": item.get("currency", "USD"),
                    "cloud_provider": "internal",
                    "account_id": member_email,
                }
            )

        return normalized

    def _verify_account_ownership(
        self, member_email: str, account_ids: list
    ) -> set:
        """Verify that all requested accounts are owned by the member.

        Queries the MemberPortal-Accounts table to confirm each account_id
        has a memberEmail matching the authenticated member.

        Args:
            member_email: The authenticated member's email.
            account_ids: List of account IDs to verify.

        Returns:
            A set of verified owned account IDs.

        Raises:
            PermissionError: If any account is not owned by the member.
                Rejects entire query with no partial results (Requirement 8.4).
        """
        if not account_ids:
            return set()

        table = self.dynamodb.Table(ACCOUNTS_TABLE)
        owned = set()

        for account_id in account_ids:
            response = table.query(
                KeyConditionExpression=Key("pk").eq(member_email),
                FilterExpression="account_id = :aid",
                ExpressionAttributeValues={":aid": account_id},
            )

            items = response.get("Items", [])
            if not items:
                raise PermissionError(
                    f"Account {account_id} not owned by {member_email}"
                )
            owned.add(account_id)

        return owned

    def _filter_by_owned_accounts(
        self, data: list[dict], owned_account_ids: set, member_email: str = ""
    ) -> list[dict]:
        """Filter query results to include only data from owned accounts.

        Server-side defense-in-depth filter ensuring that query results
        never contain data from accounts not owned by the requesting member.

        Args:
            data: Raw data items from the data source query.
            owned_account_ids: Set of verified owned account IDs.
            member_email: The authenticated member's email (for business
                metrics that use email as account_id).

        Returns:
            List of data items filtered to only include owned account data.
            Items without an account_id field are included (e.g., business_metrics).

        Requirements: 8.5, 9.5
        """
        if not owned_account_ids and not member_email:
            return data

        filtered = []
        for item in data:
            item_account = item.get("account_id")
            # Include items that either:
            # 1. Have an account_id in the owned set
            # 2. Have no account_id field
            # 3. Have account_id matching the member email (business_metrics)
            if item_account is None:
                filtered.append(item)
            elif item_account in owned_account_ids:
                filtered.append(item)
            elif member_email and item_account == member_email:
                filtered.append(item)

        return filtered

    def _error_response(self, error_message: str, period: str = "") -> dict:
        """Create a standard error response with empty data.

        Args:
            error_message: Description of the error.
            period: Optional date period string.

        Returns:
            Dict with empty labels/datasets and error in metadata.
        """
        metadata = {"error": error_message}
        if period:
            metadata["period"] = period
        return {
            "labels": [],
            "datasets": [],
            "metadata": metadata,
        }
