"""Unit tests for the PDF report generator module."""

import io
from decimal import Decimal

import pytest
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf_generator import (
    _generate_analysis_pages,
    _merge_pdfs,
    _read_original_pdf,
    generate_report,
)


def _make_minimal_pdf(num_pages: int = 1) -> bytes:
    """Create a minimal valid PDF with the given number of pages."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(num_pages):
        c.drawString(100, 700, f"Page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _sample_parsed_bill() -> dict:
    return {
        "line_items": [
            {"service": "Amazon EC2", "cost": Decimal("45.23"), "description": "Running instances"},
            {"service": "Amazon S3", "cost": Decimal("12.50"), "description": "Storage"},
        ],
        "total_cost": Decimal("57.73"),
        "currency": "USD",
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "invoice_number": "INV-12345",
        "account_id": "123456789012",
        "service_totals": {
            "Amazon EC2": Decimal("45.23"),
            "Amazon S3": Decimal("12.50"),
        },
    }


def _sample_ai_analysis() -> dict:
    return {
        "summary": "Your total bill is $57.73. EC2 is the top spender.",
        "service_analysis": [
            {
                "service": "Amazon EC2",
                "cost": "$45.23",
                "explanation": "Compute instances running in us-east-1.",
                "billing_details": "720 hours of t3.medium at $0.0416/hr",
                "recommendations": [
                    {
                        "title": "Use Reserved Instances",
                        "description": "Switch to reserved instances for steady-state workloads.",
                        "estimated_savings": "20-40%",
                    },
                ],
            },
            {
                "service": "Amazon S3",
                "cost": "$12.50",
                "explanation": "Object storage for your files.",
                "billing_details": "500 GB stored at $0.023/GB",
                "recommendations": [
                    {
                        "title": "Enable S3 Intelligent Tiering",
                        "description": "Automatically move objects to cheaper storage tiers.",
                        "estimated_savings": "10-20%",
                    },
                ],
            },
        ],
        "explanations": [
            {"service": "Amazon EC2", "cost": "$45.23", "explanation": "Compute instances running in us-east-1."},
            {"service": "Amazon S3", "cost": "$12.50", "explanation": "Object storage for your files."},
        ],
        "recommendations": [
            {
                "title": "Use Reserved Instances",
                "description": "Switch to reserved instances for steady-state workloads.",
                "estimated_savings": "20-40%",
            },
            {
                "title": "Enable S3 Intelligent Tiering",
                "description": "Automatically move objects to cheaper storage tiers.",
                "estimated_savings": "10-20%",
            },
        ],
    }


# --- _read_original_pdf tests ---

class TestReadOriginalPdf:
    def test_valid_pdf(self):
        pdf_bytes = _make_minimal_pdf()
        reader = _read_original_pdf(pdf_bytes)
        assert len(reader.pages) == 1

    def test_multi_page_pdf(self):
        pdf_bytes = _make_minimal_pdf(3)
        reader = _read_original_pdf(pdf_bytes)
        assert len(reader.pages) == 3

    def test_empty_bytes_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _read_original_pdf(b"")

    def test_invalid_bytes_raises(self):
        with pytest.raises(ValueError):
            _read_original_pdf(b"not a pdf at all")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            _read_original_pdf(b"")


# --- _generate_analysis_pages tests ---

class TestGenerateAnalysisPages:
    def test_returns_valid_pdf_bytes(self):
        result = _generate_analysis_pages(
            _sample_parsed_bill(), _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"

    def test_contains_branding(self):
        result = _generate_analysis_pages(
            _sample_parsed_bill(), _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        reader = PdfReader(io.BytesIO(result))
        all_text = ""
        for page in reader.pages:
            all_text += (page.extract_text() or "")
        assert "eshkolai" in all_text.lower()

    def test_contains_total_cost(self):
        result = _generate_analysis_pages(
            _sample_parsed_bill(), _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        reader = PdfReader(io.BytesIO(result))
        all_text = ""
        for page in reader.pages:
            all_text += (page.extract_text() or "")
        assert "57.73" in all_text

    def test_contains_service_names(self):
        result = _generate_analysis_pages(
            _sample_parsed_bill(), _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        reader = PdfReader(io.BytesIO(result))
        all_text = ""
        for page in reader.pages:
            all_text += (page.extract_text() or "")
        assert "Amazon EC2" in all_text
        assert "Amazon S3" in all_text

    def test_contains_recommendations(self):
        result = _generate_analysis_pages(
            _sample_parsed_bill(), _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        reader = PdfReader(io.BytesIO(result))
        all_text = ""
        for page in reader.pages:
            all_text += (page.extract_text() or "")
        assert "Reserved Instances" in all_text
        assert "Intelligent Tiering" in all_text

    def test_empty_analysis_still_generates(self):
        empty_analysis = {"summary": "", "explanations": [], "recommendations": []}
        result = _generate_analysis_pages(
            _sample_parsed_bill(), empty_analysis, "sess-123", "test@example.com"
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"

    def test_empty_bill_still_generates(self):
        empty_bill = {
            "line_items": [],
            "total_cost": Decimal("0"),
            "currency": "USD",
            "period_start": "N/A",
            "period_end": "N/A",
            "invoice_number": "N/A",
            "account_id": "N/A",
            "service_totals": {},
        }
        result = _generate_analysis_pages(
            empty_bill, _sample_ai_analysis(), "sess-123", "test@example.com"
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"


# --- _merge_pdfs tests ---

class TestMergePdfs:
    def test_merge_preserves_page_count(self):
        original = _make_minimal_pdf(2)
        analysis = _make_minimal_pdf(1)
        merged = _merge_pdfs(original, analysis)
        reader = PdfReader(io.BytesIO(merged))
        assert len(reader.pages) == 3

    def test_merge_single_pages(self):
        original = _make_minimal_pdf(1)
        analysis = _make_minimal_pdf(1)
        merged = _merge_pdfs(original, analysis)
        reader = PdfReader(io.BytesIO(merged))
        assert len(reader.pages) == 2


# --- generate_report (integration) tests ---

class TestGenerateReport:
    def test_full_report_is_valid_pdf(self):
        original = _make_minimal_pdf(2)
        result = generate_report(
            original, _sample_parsed_bill(), _sample_ai_analysis(), "sess-1", "a@b.com"
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"

    def test_full_report_has_original_plus_analysis_pages(self):
        original = _make_minimal_pdf(3)
        result = generate_report(
            original, _sample_parsed_bill(), _sample_ai_analysis(), "sess-1", "a@b.com"
        )
        reader = PdfReader(io.BytesIO(result))
        # Original 3 pages + at least 1 analysis page
        assert len(reader.pages) >= 4

    def test_invalid_original_pdf_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_report(
                b"garbage", _sample_parsed_bill(), _sample_ai_analysis(), "s", "a@b.com"
            )

    def test_empty_original_pdf_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_report(
                b"", _sample_parsed_bill(), _sample_ai_analysis(), "s", "a@b.com"
            )

    def test_report_text_contains_key_content(self):
        original = _make_minimal_pdf(1)
        result = generate_report(
            original, _sample_parsed_bill(), _sample_ai_analysis(), "sess-1", "a@b.com"
        )
        reader = PdfReader(io.BytesIO(result))
        all_text = ""
        for page in reader.pages:
            all_text += (page.extract_text() or "")
        # Check key content is present
        assert "eshkolai" in all_text.lower()
        assert "57.73" in all_text
        assert "Amazon EC2" in all_text
        assert "Reserved Instances" in all_text
