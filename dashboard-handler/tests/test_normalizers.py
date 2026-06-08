"""Unit tests for cross-provider data normalization.

Tests normalize_aws_data, normalize_azure_data, normalize_gcp_data,
normalize_openai_data, and multi_provider_query functions.

Requirements: 10.1, 10.2, 10.3, 10.4, 11.3
"""

import sys
import os
from decimal import Decimal

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalizers import (
    normalize_aws_data,
    normalize_azure_data,
    normalize_gcp_data,
    normalize_openai_data,
    multi_provider_query,
    is_normalized,
    NORMALIZED_FIELDS,
)


class TestNormalizeAwsData:
    """Tests for normalize_aws_data function."""

    def test_normalizes_service_breakdown(self):
        """AWS items with service_breakdown are expanded into records."""
        raw_items = [
            {
                "sk": "DAILY#2024-01-15",
                "service_breakdown": {
                    "Amazon EC2": Decimal("23.45"),
                    "Amazon S3": Decimal("12.22"),
                },
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]

        result = normalize_aws_data(raw_items, "123456789012")

        assert len(result) == 2
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["service_name"] == "Amazon EC2"
        assert result[0]["cost_amount"] == 23.45
        assert result[0]["currency"] == "USD"
        assert result[0]["cloud_provider"] == "aws"
        assert result[0]["account_id"] == "123456789012"

    def test_normalizes_total_cost_fallback(self):
        """AWS items without service_breakdown use total_cost."""
        raw_items = [
            {
                "sk": "DAILY#2024-01-15",
                "total_cost": Decimal("50.00"),
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]

        result = normalize_aws_data(raw_items, "acc1")

        assert len(result) == 1
        assert result[0]["service_name"] == "_total"
        assert result[0]["cost_amount"] == 50.0

    def test_all_records_pass_is_normalized(self):
        """All returned records have the normalized schema."""
        raw_items = [
            {
                "sk": "DAILY#2024-01-15",
                "service_breakdown": {"EC2": 10, "S3": 5},
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]

        result = normalize_aws_data(raw_items, "acc1")
        for record in result:
            assert is_normalized(record)

    def test_handles_none_cost_values(self):
        """None cost values default to 0.0."""
        raw_items = [
            {
                "sk": "DAILY#2024-01-15",
                "service_breakdown": {"EC2": None},
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]

        result = normalize_aws_data(raw_items, "acc1")
        assert result[0]["cost_amount"] == 0.0

    def test_empty_input_returns_empty_list(self):
        """Empty input list returns empty result."""
        assert normalize_aws_data([], "acc1") == []

    def test_uses_item_account_id_if_present(self):
        """Uses account_id from item if available."""
        raw_items = [
            {
                "sk": "DAILY#2024-01-15",
                "total_cost": 10,
                "currency": "USD",
                "cloud_provider": "aws",
                "account_id": "item_account",
            }
        ]

        result = normalize_aws_data(raw_items, "fallback_account")
        assert result[0]["account_id"] == "item_account"


class TestNormalizeAzureData:
    """Tests for normalize_azure_data function."""

    def test_normalizes_standard_azure_fields(self):
        """Azure data with standard fields is normalized correctly."""
        raw_items = [
            {
                "usageDate": "20240115",
                "serviceName": "Virtual Machines",
                "cost": 45.67,
                "currency": "EUR",
                "subscriptionId": "sub-123",
            }
        ]

        result = normalize_azure_data(raw_items, "sub-123")

        assert len(result) == 1
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["service_name"] == "Virtual Machines"
        assert result[0]["cost_amount"] == 45.67
        assert result[0]["currency"] == "EUR"
        assert result[0]["cloud_provider"] == "azure"
        assert result[0]["account_id"] == "sub-123"

    def test_normalizes_meter_category_field(self):
        """Azure data with meterCategory field is handled."""
        raw_items = [
            {
                "date": "2024-01-15",
                "meterCategory": "Storage",
                "pretaxCost": 12.50,
                "billingCurrency": "USD",
                "subscriptionId": "sub-456",
            }
        ]

        result = normalize_azure_data(raw_items)

        assert result[0]["service_name"] == "Storage"
        assert result[0]["cost_amount"] == 12.50
        assert result[0]["currency"] == "USD"

    def test_all_records_pass_is_normalized(self):
        """All returned records have the normalized schema."""
        raw_items = [
            {
                "date": "2024-01-15",
                "serviceName": "SQL Database",
                "cost": 30.00,
                "currency": "USD",
                "subscriptionId": "sub-1",
            }
        ]

        result = normalize_azure_data(raw_items)
        for record in result:
            assert is_normalized(record)

    def test_handles_costInBillingCurrency_field(self):
        """Azure costInBillingCurrency field is used as fallback."""
        raw_items = [
            {
                "date": "2024-01-15",
                "serviceName": "App Service",
                "costInBillingCurrency": 22.00,
                "billingCurrency": "GBP",
            }
        ]

        result = normalize_azure_data(raw_items, "sub-1")
        assert result[0]["cost_amount"] == 22.00
        assert result[0]["currency"] == "GBP"

    def test_empty_input_returns_empty_list(self):
        """Empty input list returns empty result."""
        assert normalize_azure_data([], "sub-1") == []


class TestNormalizeGcpData:
    """Tests for normalize_gcp_data function."""

    def test_normalizes_standard_gcp_fields(self):
        """GCP data with nested service/project fields is normalized."""
        raw_items = [
            {
                "usage_start_time": "2024-01-15T10:00:00Z",
                "service": {"description": "Compute Engine"},
                "cost": 33.50,
                "currency": "USD",
                "project": {"id": "my-project"},
            }
        ]

        result = normalize_gcp_data(raw_items)

        assert len(result) == 1
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["service_name"] == "Compute Engine"
        assert result[0]["cost_amount"] == 33.50
        assert result[0]["currency"] == "USD"
        assert result[0]["cloud_provider"] == "gcp"
        assert result[0]["account_id"] == "my-project"

    def test_normalizes_flat_gcp_fields(self):
        """GCP data with flat field names is handled."""
        raw_items = [
            {
                "date": "2024-01-15",
                "service_description": "Cloud Storage",
                "cost": 5.00,
                "currency_code": "USD",
                "project_id": "proj-456",
            }
        ]

        result = normalize_gcp_data(raw_items, "proj-456")

        assert result[0]["service_name"] == "Cloud Storage"
        assert result[0]["account_id"] == "proj-456"

    def test_all_records_pass_is_normalized(self):
        """All returned records have the normalized schema."""
        raw_items = [
            {
                "date": "2024-01-15",
                "service": {"description": "BigQuery"},
                "cost": 10.00,
                "currency": "USD",
                "project": {"id": "proj-1"},
            }
        ]

        result = normalize_gcp_data(raw_items)
        for record in result:
            assert is_normalized(record)

    def test_handles_camelcase_usage_start_time(self):
        """GCP usageStartTime camelCase field is handled."""
        raw_items = [
            {
                "usageStartTime": "2024-03-20T14:30:00Z",
                "service": {"description": "Cloud Run"},
                "cost": 2.50,
                "currency": "USD",
                "project": {"id": "proj-1"},
            }
        ]

        result = normalize_gcp_data(raw_items)
        assert result[0]["date"] == "2024-03-20"

    def test_empty_input_returns_empty_list(self):
        """Empty input list returns empty result."""
        assert normalize_gcp_data([], "proj-1") == []


class TestNormalizeOpenaiData:
    """Tests for normalize_openai_data function."""

    def test_normalizes_standard_openai_fields(self):
        """OpenAI usage data with model/cost fields is normalized."""
        raw_items = [
            {
                "date": "2024-01-15",
                "model": "gpt-4",
                "cost": 5.50,
                "organization_id": "org-123",
            }
        ]

        result = normalize_openai_data(raw_items)

        assert len(result) == 1
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["service_name"] == "gpt-4"
        assert result[0]["cost_amount"] == 5.50
        assert result[0]["currency"] == "USD"
        assert result[0]["cloud_provider"] == "openai"
        assert result[0]["account_id"] == "org-123"

    def test_uses_amount_field_as_fallback(self):
        """OpenAI data with 'amount' instead of 'cost' is handled."""
        raw_items = [
            {
                "date": "2024-01-15",
                "model": "gpt-3.5-turbo",
                "amount": 1.20,
                "organization_id": "org-456",
            }
        ]

        result = normalize_openai_data(raw_items)
        assert result[0]["cost_amount"] == 1.20

    def test_all_records_pass_is_normalized(self):
        """All returned records have the normalized schema."""
        raw_items = [
            {
                "date": "2024-01-15",
                "model": "gpt-4",
                "cost": 5.0,
                "organization_id": "org-1",
            }
        ]

        result = normalize_openai_data(raw_items)
        for record in result:
            assert is_normalized(record)

    def test_always_uses_usd_currency(self):
        """OpenAI normalization always returns USD currency."""
        raw_items = [
            {
                "date": "2024-01-15",
                "model": "gpt-4",
                "cost": 5.0,
            }
        ]

        result = normalize_openai_data(raw_items, "org-1")
        assert result[0]["currency"] == "USD"

    def test_empty_input_returns_empty_list(self):
        """Empty input list returns empty result."""
        assert normalize_openai_data([], "org-1") == []


class TestMultiProviderQuery:
    """Tests for multi_provider_query function."""

    def test_all_providers_succeed(self):
        """All providers returning data produces combined result."""
        fetchers = {
            "aws": lambda: [
                {"date": "2024-01-15", "service_name": "EC2", "cost_amount": 10.0,
                 "currency": "USD", "cloud_provider": "aws", "account_id": "acc1"}
            ],
            "azure": lambda: [
                {"date": "2024-01-15", "service_name": "VM", "cost_amount": 20.0,
                 "currency": "USD", "cloud_provider": "azure", "account_id": "sub1"}
            ],
        }

        result = multi_provider_query(fetchers)

        assert len(result["data"]) == 2
        assert result["successful_providers"] == ["aws", "azure"]
        assert result["failed_providers"] == []
        assert result["partial"] is False

    def test_one_provider_fails_returns_partial(self):
        """One provider failing returns partial data with error indicator."""
        fetchers = {
            "aws": lambda: [
                {"date": "2024-01-15", "service_name": "EC2", "cost_amount": 10.0,
                 "currency": "USD", "cloud_provider": "aws", "account_id": "acc1"}
            ],
            "azure": _raise_exception("Azure API connection refused"),
        }

        result = multi_provider_query(fetchers)

        assert len(result["data"]) == 1
        assert result["data"][0]["cloud_provider"] == "aws"
        assert result["successful_providers"] == ["aws"]
        assert len(result["failed_providers"]) == 1
        assert result["failed_providers"][0]["provider"] == "azure"
        assert "Azure API connection refused" in result["failed_providers"][0]["error"]
        assert result["partial"] is True

    def test_timeout_error_is_captured(self):
        """TimeoutError from a provider is captured as failure."""
        fetchers = {
            "openai": _raise_timeout("OpenAI API timed out after 30s"),
        }

        result = multi_provider_query(fetchers)

        assert result["data"] == []
        assert len(result["failed_providers"]) == 1
        assert "Timeout" in result["failed_providers"][0]["error"]
        assert result["partial"] is True

    def test_all_providers_fail(self):
        """All providers failing returns empty data with all errors."""
        fetchers = {
            "aws": _raise_exception("AWS error"),
            "azure": _raise_exception("Azure error"),
            "gcp": _raise_exception("GCP error"),
        }

        result = multi_provider_query(fetchers)

        assert result["data"] == []
        assert len(result["failed_providers"]) == 3
        assert result["successful_providers"] == []
        assert result["partial"] is True

    def test_empty_provider_dict(self):
        """Empty provider dict returns empty results, not partial."""
        result = multi_provider_query({})

        assert result["data"] == []
        assert result["failed_providers"] == []
        assert result["successful_providers"] == []
        assert result["partial"] is False

    def test_provider_returning_none_counts_as_success(self):
        """Provider returning None is treated as success (empty data)."""
        fetchers = {
            "aws": lambda: None,
        }

        result = multi_provider_query(fetchers)

        assert result["data"] == []
        assert result["successful_providers"] == ["aws"]
        assert result["failed_providers"] == []
        assert result["partial"] is False

    def test_mixed_success_and_failure_preserves_all_data(self):
        """Mixed results preserve all data from successful providers."""
        fetchers = {
            "aws": lambda: [
                {"date": "2024-01-15", "service_name": "EC2", "cost_amount": 10.0,
                 "currency": "USD", "cloud_provider": "aws", "account_id": "acc1"},
                {"date": "2024-01-16", "service_name": "S3", "cost_amount": 5.0,
                 "currency": "USD", "cloud_provider": "aws", "account_id": "acc1"},
            ],
            "gcp": lambda: [
                {"date": "2024-01-15", "service_name": "Compute", "cost_amount": 15.0,
                 "currency": "USD", "cloud_provider": "gcp", "account_id": "proj1"},
            ],
            "azure": _raise_exception("Service unavailable"),
            "openai": _raise_timeout("Timed out"),
        }

        result = multi_provider_query(fetchers)

        assert len(result["data"]) == 3
        assert set(result["successful_providers"]) == {"aws", "gcp"}
        assert len(result["failed_providers"]) == 2
        failed_names = {fp["provider"] for fp in result["failed_providers"]}
        assert failed_names == {"azure", "openai"}
        assert result["partial"] is True


class TestIsNormalized:
    """Tests for the is_normalized validation function."""

    def test_valid_record_passes(self):
        """A record with all required fields passes validation."""
        record = {
            "date": "2024-01-15",
            "service_name": "EC2",
            "cost_amount": 10.0,
            "currency": "USD",
            "cloud_provider": "aws",
            "account_id": "acc1",
        }
        assert is_normalized(record) is True

    def test_missing_field_fails(self):
        """A record missing a required field fails validation."""
        record = {
            "date": "2024-01-15",
            "service_name": "EC2",
            "cost_amount": 10.0,
            "currency": "USD",
            # missing cloud_provider and account_id
        }
        assert is_normalized(record) is False

    def test_wrong_type_cost_amount_fails(self):
        """A record with non-numeric cost_amount fails validation."""
        record = {
            "date": "2024-01-15",
            "service_name": "EC2",
            "cost_amount": "not_a_number",
            "currency": "USD",
            "cloud_provider": "aws",
            "account_id": "acc1",
        }
        assert is_normalized(record) is False

    def test_non_dict_fails(self):
        """Non-dict input fails validation."""
        assert is_normalized("not a dict") is False
        assert is_normalized(None) is False
        assert is_normalized([]) is False


# --- Helper functions for tests ---


def _raise_exception(msg: str):
    """Create a callable that raises an Exception."""
    def raiser():
        raise Exception(msg)
    return raiser


def _raise_timeout(msg: str):
    """Create a callable that raises a TimeoutError."""
    def raiser():
        raise TimeoutError(msg)
    return raiser
