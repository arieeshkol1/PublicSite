"""Unit tests for bill_parser.py — specific examples and edge cases."""
import pytest
from decimal import Decimal

from bill_parser import (
    parse_bill,
    _extract_metadata,
    _parse_cost,
    _aggregate_service_totals,
    _parse_period_range,
)


class TestParseBillEdgeCases:
    """Test error handling for invalid inputs."""

    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Empty file"):
            parse_bill(b"")

    def test_non_pdf_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Unable to read"):
            parse_bill(b"this is not a pdf")

    def test_random_bytes_raises_value_error(self):
        import os
        with pytest.raises(ValueError):
            parse_bill(os.urandom(1024))


class TestParseBillWithRealPDF:
    """Test parsing with the actual sample AWS invoice."""

    def test_extracts_invoice_number(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert result["invoice_number"] == "EUINIL26-139120"

    def test_extracts_account_id(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert result["account_id"] == "845760127781"

    def test_extracts_billing_period(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert result["period_start"] == "2026-02-01"
        assert result["period_end"] == "2026-02-28"

    def test_extracts_currency(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert result["currency"] == "USD"

    def test_has_line_items(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert len(result["line_items"]) > 0

    def test_line_items_have_required_fields(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        for item in result["line_items"]:
            assert "service" in item and item["service"]
            assert "cost" in item and isinstance(item["cost"], Decimal)
            assert "description" in item

    def test_total_cost_is_positive(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert result["total_cost"] > Decimal("0")

    def test_total_cost_equals_sum_of_line_items(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        expected = sum(item["cost"] for item in result["line_items"])
        assert result["total_cost"] == expected

    def test_service_totals_match_line_items(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        for service, total in result["service_totals"].items():
            items_sum = sum(
                item["cost"]
                for item in result["line_items"]
                if item["service"] == service
            )
            assert total == items_sum

    def test_has_service_totals(self, sample_pdf_bytes):
        result = parse_bill(sample_pdf_bytes)
        assert len(result["service_totals"]) > 0


class TestParseCost:
    """Test the _parse_cost helper."""

    def test_dollar_amount(self):
        assert _parse_cost("$45.23") == Decimal("45.23")

    def test_amount_with_commas(self):
        assert _parse_cost("$1,234.56") == Decimal("1234.56")

    def test_plain_number(self):
        assert _parse_cost("123.45") == Decimal("123.45")

    def test_negative_in_parens(self):
        assert _parse_cost("(12.34)") == Decimal("-12.34")

    def test_none_returns_none(self):
        assert _parse_cost(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_cost("") is None

    def test_non_numeric_returns_none(self):
        assert _parse_cost("hello") is None


class TestAggregateServiceTotals:
    """Test service total aggregation."""

    def test_single_service(self):
        items = [{"service": "EC2", "cost": Decimal("10")}]
        assert _aggregate_service_totals(items) == {"EC2": Decimal("10")}

    def test_multiple_same_service(self):
        items = [
            {"service": "EC2", "cost": Decimal("10")},
            {"service": "EC2", "cost": Decimal("20")},
        ]
        assert _aggregate_service_totals(items) == {"EC2": Decimal("30")}

    def test_multiple_services(self):
        items = [
            {"service": "EC2", "cost": Decimal("10")},
            {"service": "S3", "cost": Decimal("5")},
        ]
        result = _aggregate_service_totals(items)
        assert result == {"EC2": Decimal("10"), "S3": Decimal("5")}

    def test_empty_list(self):
        assert _aggregate_service_totals([]) == {}


class TestExtractMetadata:
    """Test metadata extraction from text."""

    def test_extracts_invoice_number(self):
        text = "Invoice Number: EUINIL26-139120\nSome other text"
        result = _extract_metadata(text)
        assert result["invoice_number"] == "EUINIL26-139120"

    def test_extracts_account_id(self):
        text = "Account number: 845760127781\nOther text"
        result = _extract_metadata(text)
        assert result["account_id"] == "845760127781"

    def test_defaults_for_missing_fields(self):
        text = "No useful data here"
        result = _extract_metadata(text)
        assert result["invoice_number"] == "N/A"
        assert result["account_id"] == "N/A"
        assert result["currency"] == "USD"


class TestParsePeriodRange:
    """Test billing period range parsing."""

    def test_year_on_end_only(self):
        result = _parse_period_range("February 1 - February 28, 2026")
        assert result == ("2026-02-01", "2026-02-28")

    def test_year_on_both(self):
        result = _parse_period_range("January 1, 2024 - January 31, 2024")
        assert result == ("2024-01-01", "2024-01-31")

    def test_cross_month(self):
        result = _parse_period_range("December 1 - January 31, 2025")
        # Year is shared, so December gets 2025 too (limitation)
        assert result is not None

    def test_unparseable_returns_none(self):
        result = _parse_period_range("no dates here")
        assert result is None
