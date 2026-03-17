"""
AWS Bill Analyzer - PDF Report Generator Module

Uses PyPDF2 to read the original invoice PDF and ReportLab to generate
analysis pages. Merges original invoice pages with analysis pages into
a single PDF output.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# AWS-inspired color palette
AWS_ORANGE = colors.HexColor("#FF9900")
AWS_DARK = colors.HexColor("#232F3E")
HEADER_BG = colors.HexColor("#232F3E")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
MEDIUM_GRAY = colors.HexColor("#DDDDDD")
TEXT_COLOR = colors.HexColor("#333333")
WHITE = colors.white


def _format_cost(value: Any) -> str:
    """Format a cost value as a string with 2 decimal places."""
    try:
        return f"{Decimal(str(value)):.2f}"
    except Exception:
        return str(value)


def _build_styles() -> Dict[str, ParagraphStyle]:
    """Build custom paragraph styles for the analysis pages."""
    base = getSampleStyleSheet()
    return {
        "banner": ParagraphStyle(
            "Banner",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=WHITE,
            alignment=1,  # center
            spaceAfter=0,
        ),
        "banner_sub": ParagraphStyle(
            "BannerSub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#CCCCCC"),
            alignment=1,
            spaceAfter=0,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=AWS_DARK,
            spaceBefore=16,
            spaceAfter=8,
            borderPadding=(0, 0, 4, 0),
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_COLOR,
            leading=14,
            spaceAfter=4,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=TEXT_COLOR,
            leading=14,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#666666"),
            leading=10,
        ),
        "rec_title": ParagraphStyle(
            "RecTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=AWS_DARK,
            spaceAfter=2,
        ),
        "rec_body": ParagraphStyle(
            "RecBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_COLOR,
            leading=13,
            spaceAfter=2,
        ),
        "rec_savings": ParagraphStyle(
            "RecSavings",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.HexColor("#067D62"),
            spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=colors.HexColor("#999999"),
            alignment=1,
        ),
    }


def generate_report(
    original_pdf_bytes: bytes,
    parsed_bill: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    session_id: str,
    email: str,
) -> bytes:
    """
    Generate a merged PDF report: original invoice pages + analysis pages.

    Args:
        original_pdf_bytes: Raw bytes of the uploaded AWS invoice PDF.
        parsed_bill: ParsedBill dict from bill_parser.parse_bill().
        ai_analysis: AIAnalysis dict from bedrock_client.analyze_bill().
        session_id: Unique session identifier.
        email: User's email address.

    Returns:
        Merged PDF as bytes (original invoice + analysis pages).

    Raises:
        ValueError: If the original PDF cannot be read.
        RuntimeError: If PDF generation or merging fails.
    """
    # Validate original PDF
    _read_original_pdf(original_pdf_bytes)

    # Generate analysis pages
    analysis_pdf_bytes = _generate_analysis_pages(
        parsed_bill, ai_analysis, session_id, email
    )

    # Merge original + analysis
    return _merge_pdfs(original_pdf_bytes, analysis_pdf_bytes)


def _read_original_pdf(pdf_bytes: bytes):
    """
    Read the original invoice PDF using PyPDF2.

    Args:
        pdf_bytes: Raw bytes of the original PDF.

    Returns:
        PyPDF2 PdfReader instance.

    Raises:
        ValueError: If the bytes are not a valid PDF.
    """
    if not pdf_bytes:
        raise ValueError("Original PDF is empty")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) == 0:
            raise ValueError("Original PDF has no pages")
        return reader
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid PDF file: {e}")


def _generate_analysis_pages(
    parsed_bill: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    session_id: str,
    email: str,
) -> bytes:
    """
    Generate the analysis pages as a PDF using ReportLab.

    Args:
        parsed_bill: ParsedBill dict.
        ai_analysis: AIAnalysis dict.
        session_id: Unique session identifier.
        email: User's email address.

    Returns:
        Analysis pages PDF as bytes.
    """
    buf = io.BytesIO()
    styles = _build_styles()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    elements: List[Any] = []

    # --- Header / Banner ---
    elements.extend(_build_header(parsed_bill, timestamp, styles))

    # --- Bill Summary ---
    elements.extend(_build_summary_section(parsed_bill, ai_analysis, styles))

    # --- Service Breakdown & Explanations ---
    elements.extend(_build_explanations_section(parsed_bill, ai_analysis, styles))

    # --- Recommendations ---
    elements.extend(_build_recommendations_section(ai_analysis, styles))

    # --- Footer disclaimer ---
    elements.append(Spacer(1, 20))
    elements.extend(_build_footer(timestamp, styles))

    doc.build(elements)
    return buf.getvalue()


def _build_header(
    parsed_bill: Dict[str, Any], timestamp: str, styles: Dict[str, ParagraphStyle]
) -> List[Any]:
    """Build the header banner with branding and billing period summary."""
    elements: List[Any] = []

    # Orange + dark banner table
    banner_data = [
        [Paragraph("eshkolai.com Bill Analysis", styles["banner"])],
        [Paragraph(f"Generated: {timestamp}", styles["banner_sub"])],
    ]
    banner_table = Table(banner_data, colWidths=[7 * inch])
    banner_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AWS_DARK),
                ("TOPPADDING", (0, 0), (-1, 0), 18),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("LINEBELOW", (0, 0), (-1, 0), 3, AWS_ORANGE),
            ]
        )
    )
    elements.append(banner_table)
    elements.append(Spacer(1, 12))

    # Billing period summary row
    period_start = parsed_bill.get("period_start", "N/A")
    period_end = parsed_bill.get("period_end", "N/A")
    invoice_num = parsed_bill.get("invoice_number", "N/A")
    account_id = parsed_bill.get("account_id", "N/A")

    info_data = [
        [
            Paragraph(f"<b>Invoice:</b> {invoice_num}", styles["body"]),
            Paragraph(f"<b>Account:</b> {account_id}", styles["body"]),
            Paragraph(
                f"<b>Period:</b> {period_start} to {period_end}", styles["body"]
            ),
        ]
    ]
    info_table = Table(info_data, colWidths=[2.3 * inch, 2.3 * inch, 2.4 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(info_table)
    elements.append(Spacer(1, 16))

    return elements


def _build_summary_section(
    parsed_bill: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build the bill summary section."""
    elements: List[Any] = []

    # Section heading with orange left border
    elements.append(_section_heading("Bill Summary", styles))

    total_cost = _format_cost(parsed_bill.get("total_cost", 0))
    currency = parsed_bill.get("currency", "USD")

    # Total cost highlight
    total_data = [
        [
            Paragraph(f"<b>Total Cost:</b> {currency} {total_cost}", styles["body_bold"]),
        ]
    ]
    total_table = Table(total_data, colWidths=[7 * inch])
    total_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("LINEBELOW", (0, 0), (-1, -1), 2, AWS_ORANGE),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elements.append(total_table)
    elements.append(Spacer(1, 8))

    # AI summary text
    summary_text = ai_analysis.get("summary", "No summary available.")
    elements.append(Paragraph(summary_text, styles["body"]))
    elements.append(Spacer(1, 8))

    # Service totals mini-table
    service_totals = parsed_bill.get("service_totals", {})
    if service_totals:
        svc_header = [
            Paragraph("<b>Service</b>", styles["body_bold"]),
            Paragraph(f"<b>Cost ({currency})</b>", styles["body_bold"]),
        ]
        svc_rows = [svc_header]
        for svc, cost in sorted(
            service_totals.items(), key=lambda x: float(x[1]), reverse=True
        ):
            svc_rows.append(
                [
                    Paragraph(str(svc), styles["body"]),
                    Paragraph(_format_cost(cost), styles["body"]),
                ]
            )

        svc_table = Table(svc_rows, colWidths=[5 * inch, 2 * inch])
        svc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), AWS_DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                    ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(svc_table)
    else:
        elements.append(Paragraph("No service breakdown available.", styles["body"]))

    elements.append(Spacer(1, 12))
    return elements


def _build_explanations_section(
    parsed_bill: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build the charge explanations section."""
    elements: List[Any] = []

    elements.append(_section_heading("Charge Explanations", styles))

    explanations = ai_analysis.get("explanations", [])
    if not explanations:
        elements.append(
            Paragraph("No charge explanations available.", styles["body"])
        )
        elements.append(Spacer(1, 12))
        return elements

    currency = parsed_bill.get("currency", "USD")

    # Table header
    header = [
        Paragraph("<b>Service</b>", styles["body_bold"]),
        Paragraph(f"<b>Cost ({currency})</b>", styles["body_bold"]),
        Paragraph("<b>Explanation</b>", styles["body_bold"]),
    ]
    rows = [header]

    for exp in explanations:
        service = str(exp.get("service", "Unknown"))
        cost = str(exp.get("cost", "N/A"))
        explanation = str(exp.get("explanation", ""))
        rows.append(
            [
                Paragraph(service, styles["body"]),
                Paragraph(cost, styles["body"]),
                Paragraph(explanation, styles["body"]),
            ]
        )

    exp_table = Table(rows, colWidths=[1.5 * inch, 1 * inch, 4.5 * inch])
    exp_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AWS_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(exp_table)
    elements.append(Spacer(1, 12))
    return elements


def _build_recommendations_section(
    ai_analysis: Dict[str, Any], styles: Dict[str, ParagraphStyle]
) -> List[Any]:
    """Build the cost-saving recommendations section."""
    elements: List[Any] = []

    elements.append(_section_heading("Cost-Saving Recommendations", styles))

    recommendations = ai_analysis.get("recommendations", [])
    if not recommendations:
        elements.append(
            Paragraph("No recommendations available.", styles["body"])
        )
        return elements

    for idx, rec in enumerate(recommendations, 1):
        title = str(rec.get("title", "Recommendation"))
        description = str(rec.get("description", ""))
        savings = str(rec.get("estimated_savings", ""))
        difficulty = str(rec.get("difficulty", ""))

        # Numbered title
        elements.append(
            Paragraph(f"{idx}. {title}", styles["rec_title"])
        )
        elements.append(Paragraph(description, styles["rec_body"]))

        # Savings + difficulty badge line
        badge_parts = []
        if savings:
            badge_parts.append(f"Estimated Savings: {savings}")
        if difficulty:
            badge_parts.append(f"Difficulty: {difficulty}")
        if badge_parts:
            elements.append(
                Paragraph(" | ".join(badge_parts), styles["rec_savings"])
            )

        elements.append(Spacer(1, 4))

    return elements


def _build_footer(timestamp: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    """Build the footer with branding and disclaimer."""
    elements: List[Any] = []

    # Separator line
    sep_data = [[""]]
    sep_table = Table(sep_data, colWidths=[7 * inch])
    sep_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, -1), 1, MEDIUM_GRAY),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(sep_table)

    elements.append(
        Paragraph(
            "Generated by eshkolai.com Bill Analysis Service",
            styles["footer"],
        )
    )
    elements.append(
        Paragraph(
            f"Report generated at {timestamp}",
            styles["footer"],
        )
    )
    elements.append(
        Paragraph(
            "Disclaimer: This analysis is provided for informational purposes only. "
            "Actual savings may vary. Please verify recommendations with your AWS account team.",
            styles["footer"],
        )
    )
    return elements


def _section_heading(text: str, styles: Dict[str, ParagraphStyle]) -> Table:
    """Create a section heading with an orange left border accent."""
    data = [[Paragraph(text, styles["section_heading"])]]
    table = Table(data, colWidths=[7 * inch])
    table.setStyle(
        TableStyle(
            [
                ("LINEBEFORE", (0, 0), (0, -1), 3, AWS_ORANGE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _merge_pdfs(original_pdf_bytes: bytes, analysis_pdf_bytes: bytes) -> bytes:
    """
    Merge original invoice PDF with analysis pages PDF.

    Original pages come first, followed by analysis pages.

    Args:
        original_pdf_bytes: Raw bytes of the original invoice PDF.
        analysis_pdf_bytes: Raw bytes of the generated analysis pages.

    Returns:
        Merged PDF as bytes.

    Raises:
        RuntimeError: If merging fails.
    """
    try:
        writer = PdfWriter()

        # Add original pages
        original_reader = PdfReader(io.BytesIO(original_pdf_bytes))
        for page in original_reader.pages:
            writer.add_page(page)

        # Add analysis pages
        analysis_reader = PdfReader(io.BytesIO(analysis_pdf_bytes))
        for page in analysis_reader.pages:
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception as e:
        raise RuntimeError(f"Failed to merge PDFs: {e}")
