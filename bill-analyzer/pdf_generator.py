"""
AWS Bill Analyzer - PDF Report Generator Module

Uses PyPDF2 to read the original invoice PDF and ReportLab to generate
analysis pages. Merges analysis pages first, then appends the original
invoice as an appendix.
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
    PageBreak,
)
from reportlab.pdfgen import canvas

# eshkolai.com theme colors (matching website CSS variables)
PRIMARY_BLUE = colors.HexColor("#0066FF")
DARK_BLUE = colors.HexColor("#0052CC")
SECONDARY_BLUE = colors.HexColor("#00D4FF")
DARK_BG = colors.HexColor("#0A0E27")
LIGHT_BG = colors.HexColor("#F0F4FF")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
MEDIUM_GRAY = colors.HexColor("#DDDDDD")
TEXT_COLOR = colors.HexColor("#333333")
WHITE = colors.white
ACCENT_ORANGE = colors.HexColor("#FF6B35")


def _format_cost(value: Any) -> str:
    """Format a cost value as a string with 2 decimal places."""
    try:
        return f"{Decimal(str(value)):.2f}"
    except Exception:
        return str(value)


def _page_header_footer(canvas_obj, doc):
    """Draw header and footer on every page with eshkolai.com branding."""
    canvas_obj.saveState()
    width, height = letter

    # --- Header bar ---
    bar_height = 28
    canvas_obj.setFillColor(DARK_BG)
    canvas_obj.rect(0, height - bar_height, width, bar_height, fill=1, stroke=0)
    # Accent line under header
    canvas_obj.setStrokeColor(PRIMARY_BLUE)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(0, height - bar_height, width, height - bar_height)
    # Logo text
    canvas_obj.setFillColor(WHITE)
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(doc.leftMargin, height - 19, "eshkolai.com")
    # Right side text
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#AABBDD"))
    canvas_obj.drawRightString(width - doc.rightMargin, height - 19, "Bill Analysis Report")

    # --- Footer bar ---
    footer_y = 30
    canvas_obj.setStrokeColor(MEDIUM_GRAY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(doc.leftMargin, footer_y, width - doc.rightMargin, footer_y)
    # Footer text
    canvas_obj.setFillColor(colors.HexColor("#999999"))
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawString(doc.leftMargin, footer_y - 12, "eshkolai.com \u2022 Cloud and AI")
    canvas_obj.drawRightString(
        width - doc.rightMargin, footer_y - 12,
        "Confidential \u2022 Generated for authorized use only"
    )

    canvas_obj.restoreState()


def _build_styles() -> Dict[str, ParagraphStyle]:
    """Build custom paragraph styles for the analysis pages."""
    base = getSampleStyleSheet()
    return {
        "banner": ParagraphStyle(
            "Banner",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=WHITE,
            alignment=1,
            spaceAfter=0,
        ),
        "banner_sub": ParagraphStyle(
            "BannerSub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#AABBDD"),
            alignment=1,
            spaceAfter=0,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=DARK_BLUE,
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
            textColor=DARK_BLUE,
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
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=WHITE,
            leading=14,
            spaceAfter=0,
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
    Generate a merged PDF report: analysis pages first, then original invoice as appendix.

    Args:
        original_pdf_bytes: Raw bytes of the uploaded AWS invoice PDF.
        parsed_bill: ParsedBill dict from bill_parser.parse_bill().
        ai_analysis: AIAnalysis dict from bedrock_client.analyze_bill().
        session_id: Unique session identifier.
        email: User's email address.

    Returns:
        Merged PDF as bytes (analysis pages + original invoice appendix).

    Raises:
        ValueError: If the original PDF cannot be read.
        RuntimeError: If PDF generation or merging fails.
    """
    _read_original_pdf(original_pdf_bytes)

    analysis_pdf_bytes = _generate_analysis_pages(
        parsed_bill, ai_analysis, session_id, email
    )

    # Analysis first, original as appendix
    return _merge_pdfs(analysis_pdf_bytes, original_pdf_bytes)


def _read_original_pdf(pdf_bytes: bytes):
    """Read and validate the original invoice PDF."""
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
    """Generate the analysis pages as a PDF using ReportLab."""
    buf = io.BytesIO()
    styles = _build_styles()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.75 * inch,  # room for header bar
        bottomMargin=0.75 * inch,  # room for footer
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    elements: List[Any] = []

    # --- Title Banner ---
    elements.extend(_build_header(parsed_bill, timestamp, styles))

    # --- Bill Summary ---
    elements.extend(_build_summary_section(parsed_bill, ai_analysis, styles))

    # --- Service Analysis (explanations + recommendations) ---
    elements.extend(_build_explanations_section(parsed_bill, ai_analysis, styles))

    # --- Savings Plans & Reserved Instances Analysis ---
    elements.extend(_build_savings_plan_section(ai_analysis, styles))

    # --- Footer disclaimer ---
    elements.append(Spacer(1, 20))
    elements.extend(_build_footer(timestamp, styles))

    doc.build(elements, onFirstPage=_page_header_footer, onLaterPages=_page_header_footer)
    return buf.getvalue()


def _build_header(
    parsed_bill: Dict[str, Any], timestamp: str, styles: Dict[str, ParagraphStyle]
) -> List[Any]:
    """Build the title banner with branding and billing period summary."""
    elements: List[Any] = []

    # Title banner - white background with blue text
    title_data = [[Paragraph("Bill Analysis Report", ParagraphStyle(
        "BannerTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=DARK_BLUE,
        alignment=1,
        spaceAfter=0,
    ))]]
    title_table = Table(title_data, colWidths=[7 * inch])
    title_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, -1), 3, PRIMARY_BLUE),
    ]))
    elements.append(title_table)

    # Date line - separate row below the title
    date_data = [[Paragraph(f"Generated: {timestamp}", ParagraphStyle(
        "BannerDate",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        alignment=1,
    ))]]
    date_table = Table(date_data, colWidths=[7 * inch])
    date_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(date_table)
    elements.append(Spacer(1, 14))

    # Billing period info row
    period_start = parsed_bill.get("period_start", "N/A")
    period_end = parsed_bill.get("period_end", "N/A")
    invoice_num = parsed_bill.get("invoice_number", "N/A")
    account_id = parsed_bill.get("account_id", "N/A")

    info_data = [[
        Paragraph(f"<b>Invoice:</b> {invoice_num}", styles["body"]),
        Paragraph(f"<b>Account:</b> {account_id}", styles["body"]),
        Paragraph(f"<b>Period:</b> {period_start} to {period_end}", styles["body"]),
    ]]
    info_table = Table(info_data, colWidths=[2.3 * inch, 2.3 * inch, 2.4 * inch])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 16))

    return elements


def _build_summary_section(
    parsed_bill: Dict[str, Any],
    ai_analysis: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build the bill summary section with total cost and service breakdown table."""
    elements: List[Any] = []

    elements.append(_section_heading("Bill Summary", styles))

    total_cost = _format_cost(parsed_bill.get("total_cost", 0))
    currency = parsed_bill.get("currency", "USD")

    # Total cost highlight box
    total_data = [[
        Paragraph(f"<b>Total Cost:</b> {currency} {total_cost}", styles["body_bold"]),
    ]]
    total_table = Table(total_data, colWidths=[7 * inch])
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 8))

    # AI summary text
    summary_text = ai_analysis.get("summary", "No summary available.")
    elements.append(Paragraph(summary_text, styles["body"]))
    elements.append(Spacer(1, 8))

    # Service totals table
    service_totals = parsed_bill.get("service_totals", {})
    if service_totals:
        svc_header = [
            Paragraph("<b>Service</b>", styles["table_header"]),
            Paragraph(f"<b>Cost ({currency})</b>", styles["table_header"]),
        ]
        svc_rows = [svc_header]
        for svc, cost in sorted(
            service_totals.items(), key=lambda x: float(x[1]), reverse=True
        ):
            svc_rows.append([
                Paragraph(str(svc), styles["body"]),
                Paragraph(_format_cost(cost), styles["body"]),
            ])

        # Totals row
        svc_rows.append([
            Paragraph("<b>Total</b>", styles["body_bold"]),
            Paragraph(f"<b>{total_cost}</b>", styles["body_bold"]),
        ])

        svc_table = Table(svc_rows, colWidths=[5 * inch, 2 * inch])
        svc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT_BG]),
            ("BACKGROUND", (0, -1), (-1, -1), LIGHT_BG),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, DARK_BLUE),
            ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
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
    """Build unified per-service cards sorted by cost descending (most expensive first)."""
    elements: List[Any] = []

    elements.append(_section_heading("Service Analysis", styles))

    # Prefer new service_analysis format, fall back to legacy explanations
    service_items = ai_analysis.get("service_analysis", [])
    if not service_items:
        service_items = ai_analysis.get("explanations", [])
    if not service_items:
        elements.append(Paragraph("No charge explanations available.", styles["body"]))
        elements.append(Spacer(1, 12))
        return elements

    # Sort by cost descending (most expensive first)
    def _extract_cost(item):
        cost_str = str(item.get("cost", "0"))
        # Strip $ and commas
        cleaned = cost_str.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    sorted_items = sorted(service_items, key=_extract_cost, reverse=True)

    for item in sorted_items:
        service = str(item.get("service", "Unknown"))
        cost = str(item.get("cost", "N/A"))
        explanation = str(item.get("explanation", ""))
        billing_details = str(item.get("billing_details", ""))
        recommendations = item.get("recommendations", [])

        # --- Service header bar (dark blue) ---
        header_data = [[
            Paragraph(f"<b>{service}</b>", styles["table_header"]),
            Paragraph(f"<b>{cost}</b>", styles["table_header"]),
        ]]
        header_table = Table(header_data, colWidths=[5.5 * inch, 1.5 * inch])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 2, PRIMARY_BLUE),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]))
        elements.append(header_table)

        # --- Two-column body: left = explanation + billing, right = recommendations ---
        left_parts: List[Any] = []
        left_parts.append(Paragraph(explanation, styles["body"]))
        if billing_details:
            left_parts.append(Spacer(1, 4))
            left_parts.append(Paragraph(
                f'<b>How you are charged:</b> {billing_details}',
                styles["body"],
            ))

        right_parts: List[Any] = []
        if recommendations:
            right_parts.append(Paragraph("<b>How to save:</b>", styles["body_bold"]))
            right_parts.append(Spacer(1, 2))
            for rec in recommendations:
                title = str(rec.get("title", ""))
                desc = str(rec.get("description", ""))
                savings = str(rec.get("estimated_savings", ""))
                right_parts.append(Paragraph(f"\u2022 <b>{title}</b>", styles["body_bold"]))
                if desc:
                    right_parts.append(Paragraph(f"  {desc}", styles["small"]))
                if savings:
                    right_parts.append(Paragraph(f"  Savings: {savings}", styles["rec_savings"]))
        else:
            right_parts.append(Paragraph("<i>No specific recommendations.</i>", styles["small"]))

        body_data = [[left_parts, right_parts]]
        body_table = Table(body_data, colWidths=[3.5 * inch, 3.5 * inch])
        body_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBEFORE", (1, 0), (1, -1), 0.5, MEDIUM_GRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
        ]))
        elements.append(body_table)
        elements.append(Spacer(1, 10))

    return elements


def _build_savings_plan_section(
    ai_analysis: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build the Savings Plans & Reserved Instances recommendation section."""
    elements: List[Any] = []

    sp_analysis = ai_analysis.get("savings_plan_analysis", {})
    if not sp_analysis:
        return elements

    elements.append(_section_heading("Savings Plans & Reserved Instances", styles))

    recommendation = sp_analysis.get("recommendation", "")
    potential_savings = sp_analysis.get("potential_savings_percent", "")
    how_to_purchase = sp_analysis.get("how_to_purchase", "")
    has_sp = sp_analysis.get("has_savings_plans", False)
    has_ri = sp_analysis.get("has_reserved_instances", False)

    # Status indicators
    sp_status = "Active" if has_sp else "Not detected"
    ri_status = "Active" if has_ri else "Not detected"
    sp_color = "#067D62" if has_sp else "#CC5500"
    ri_color = "#067D62" if has_ri else "#CC5500"

    status_data = [[
        Paragraph(
            f'<b>Savings Plans:</b> <font color="{sp_color}">{sp_status}</font>',
            styles["body"],
        ),
        Paragraph(
            f'<b>Reserved Instances:</b> <font color="{ri_color}">{ri_status}</font>',
            styles["body"],
        ),
    ]]
    if potential_savings:
        status_data[0].append(
            Paragraph(
                f'<b>Potential Savings:</b> <font color="#067D62">{potential_savings}</font>',
                styles["body"],
            )
        )
    else:
        status_data[0].append(Paragraph("", styles["body"]))

    status_table = Table(status_data, colWidths=[2.3 * inch, 2.3 * inch, 2.4 * inch])
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 8))

    # Recommendation text
    if recommendation:
        elements.append(Paragraph(recommendation, styles["body"]))
        elements.append(Spacer(1, 6))

    # How to purchase
    if how_to_purchase:
        elements.append(Paragraph("<b>How to get started:</b>", styles["body_bold"]))
        elements.append(Paragraph(how_to_purchase, styles["body"]))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 8))
    return elements


def _build_footer(timestamp: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    """Build the footer with branding and disclaimer."""
    elements: List[Any] = []

    sep_data = [[""]]
    sep_table = Table(sep_data, colWidths=[7 * inch])
    sep_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 1, MEDIUM_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(sep_table)

    elements.append(Paragraph(
        "Generated by eshkolai.com Bill Analysis Service",
        styles["footer"],
    ))
    elements.append(Paragraph(
        f"Report generated at {timestamp}",
        styles["footer"],
    ))
    elements.append(Paragraph(
        "Disclaimer: This analysis is provided for informational purposes only. "
        "Actual savings may vary. Please verify recommendations with your AWS account team.",
        styles["footer"],
    ))
    return elements


def _section_heading(text: str, styles: Dict[str, ParagraphStyle]) -> Table:
    """Create a section heading with a blue left border accent."""
    data = [[Paragraph(text, styles["section_heading"])]]
    table = Table(data, colWidths=[7 * inch])
    table.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 3, PRIMARY_BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _merge_pdfs(first_pdf_bytes: bytes, second_pdf_bytes: bytes) -> bytes:
    """
    Merge two PDFs: first PDF pages followed by second PDF pages.

    In our case: analysis pages first, then original invoice as appendix.
    """
    try:
        writer = PdfWriter()

        first_reader = PdfReader(io.BytesIO(first_pdf_bytes))
        for page in first_reader.pages:
            writer.add_page(page)

        second_reader = PdfReader(io.BytesIO(second_pdf_bytes))
        for page in second_reader.pages:
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception as e:
        raise RuntimeError(f"Failed to merge PDFs: {e}")
