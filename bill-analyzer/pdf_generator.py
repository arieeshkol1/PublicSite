"""
AWS Bill Analyzer - PDF Report Generator Module

Uses PyPDF2 to read the original invoice PDF and ReportLab to generate
analysis pages. Merges analysis pages first, then appends the original
invoice as an appendix.
"""

import io
import os
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
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF

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

# Logo image path (bundled with Lambda package)
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "SlashMyBill.png")


def _format_cost(value: Any) -> str:
    """Format a cost value as a string with 2 decimal places and comma separators."""
    try:
        return f"{Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)


def _parse_savings_percent(savings_str: str):
    """Parse an estimated_savings string like '20-40%' or 'up to 30%' into (min%, max%) floats.

    Returns None if unparseable.
    """
    import re
    s = str(savings_str).strip().lower().replace(",", "")
    # Pattern: "20-40%" or "20% - 40%"
    m = re.search(r'(\d+(?:\.\d+)?)\s*[%]?\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*%', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Pattern: "up to 30%" or "~30%"
    m = re.search(r'(?:up\s+to|~)\s*(\d+(?:\.\d+)?)\s*%', s)
    if m:
        val = float(m.group(1))
        return 0.0, val
    # Pattern: plain "30%"
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', s)
    if m:
        val = float(m.group(1))
        return val, val
    return None


def _compute_service_savings(service_cost: float, recommendations: list):
    """Compute min/max/avg dollar savings for a service from its recommendations.

    Returns (min_dollars, max_dollars, avg_dollars) or None if no parseable savings.
    """
    if service_cost <= 0 or not recommendations:
        return None
    total_min_pct = 0.0
    total_max_pct = 0.0
    count = 0
    for rec in recommendations:
        parsed = _parse_savings_percent(str(rec.get("estimated_savings", "")))
        if parsed:
            total_min_pct += parsed[0]
            total_max_pct += parsed[1]
            count += 1
    if count == 0:
        return None
    # Use the highest recommendation range (not sum — recommendations overlap)
    best_min = 0.0
    best_max = 0.0
    for rec in recommendations:
        parsed = _parse_savings_percent(str(rec.get("estimated_savings", "")))
        if parsed:
            if parsed[1] > best_max:
                best_min, best_max = parsed
    min_dollars = service_cost * best_min / 100.0
    max_dollars = service_cost * best_max / 100.0
    avg_dollars = (min_dollars + max_dollars) / 2.0
    return min_dollars, max_dollars, avg_dollars


def _compute_total_savings(service_items: list):
    """Compute aggregate min/max/avg dollar savings across all services.

    Returns (total_min, total_max, total_avg) or None.
    """
    total_min = 0.0
    total_max = 0.0
    has_any = False
    for item in service_items:
        cost_str = str(item.get("cost", "0")).replace("$", "").replace(",", "").strip()
        try:
            cost_val = float(cost_str)
        except ValueError:
            continue
        result = _compute_service_savings(cost_val, item.get("recommendations", []))
        if result:
            total_min += result[0]
            total_max += result[1]
            has_any = True
    if not has_any:
        return None
    return total_min, total_max, (total_min + total_max) / 2.0


def _page_header_footer(canvas_obj, doc):
    """Draw header and footer on every page with eshkolai.com branding."""
    canvas_obj.saveState()
    width, height = letter

    # --- Header bar (white background) ---
    bar_height = 48
    canvas_obj.setFillColor(WHITE)
    canvas_obj.rect(0, height - bar_height, width, bar_height, fill=1, stroke=0)
    # Accent line under header
    canvas_obj.setStrokeColor(PRIMARY_BLUE)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(0, height - bar_height, width, height - bar_height)
    # Logo image (2x size for better visibility)
    logo_h = 40
    logo_w = logo_h * 3.5  # approximate aspect ratio
    if os.path.exists(_LOGO_PATH):
        try:
            canvas_obj.drawImage(
                _LOGO_PATH,
                doc.leftMargin,
                height - bar_height + (bar_height - logo_h) / 2,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            # Fallback to text if image fails
            canvas_obj.setFillColor(DARK_BG)
            canvas_obj.setFont("Helvetica-Bold", 10)
            canvas_obj.drawString(doc.leftMargin, height - 19, "eshkolai.com")
    else:
        canvas_obj.setFillColor(DARK_BG)
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.drawString(doc.leftMargin, height - 19, "eshkolai.com")
    # Right side text — report name + generated timestamp (shifted up)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#666666"))
    canvas_obj.drawRightString(width - doc.rightMargin, height - 20, "Slash My Bill Report")
    # Generated timestamp on second line
    if hasattr(doc, '_report_timestamp') and doc._report_timestamp:
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.drawRightString(width - doc.rightMargin, height - 32, f"Generated: {doc._report_timestamp}")

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
        topMargin=1.0 * inch,  # room for taller header bar
        bottomMargin=0.75 * inch,  # room for footer
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    # Attach timestamp so _page_header_footer can display it
    doc._report_timestamp = timestamp

    elements: List[Any] = []

    # --- Title Banner ---
    elements.extend(_build_header(parsed_bill, timestamp, styles))

    # --- Bill Summary ---
    elements.extend(_build_summary_section(parsed_bill, ai_analysis, styles))

    # --- Service Analysis (explanations + recommendations) ---
    elements.extend(_build_explanations_section(parsed_bill, ai_analysis, styles))

    # --- Savings Plans & Reserved Instances Analysis ---
    elements.extend(_build_savings_plan_section(ai_analysis, parsed_bill, styles))

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

    # Title + date combined in one table, blue line at the bottom
    title_para = Paragraph("Slash My Bill Report", ParagraphStyle(
        "BannerTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=DARK_BLUE,
        alignment=1,
        spaceAfter=0,
    ))
    header_data = [[title_para]]
    header_table = Table(header_data, colWidths=[7 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("TOPPADDING", (0, 0), (0, 0), 14),
        ("BOTTOMPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(header_table)
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
    tax_amount = parsed_bill.get("tax_amount")
    total_with_tax = parsed_bill.get("total_with_tax")

    # Total cost highlight box — include tax if present
    if tax_amount and total_with_tax:
        tax_str = _format_cost(tax_amount)
        total_with_tax_str = _format_cost(total_with_tax)
        total_text = (
            f"<b>Charges:</b> {currency} {total_cost} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Tax:</b> {currency} {tax_str} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total (incl. tax):</b> {currency} {total_with_tax_str}"
        )
    else:
        total_text = f"<b>Total Cost:</b> {currency} {total_cost}"

    total_data = [[
        Paragraph(total_text, styles["body_bold"]),
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

    # AI summary text + savings findings
    summary_text = ai_analysis.get("summary", "No summary available.")

    # Compute total savings range from all service recommendations
    service_items = ai_analysis.get("service_analysis", [])
    if not service_items:
        service_items = ai_analysis.get("explanations", [])
    savings_totals = _compute_total_savings(service_items) if service_items else None

    if savings_totals:
        s_min, s_max, s_avg = savings_totals
        savings_line = (
            f" Based on our analysis, estimated potential savings range from "
            f"<b>{currency} {s_min:,.2f}</b> (min) to <b>{currency} {s_max:,.2f}</b> (max), "
            f"with an average of <b>{currency} {s_avg:,.2f}</b> per billing period."
        )
        summary_text = summary_text.rstrip(".") + "." + savings_line

    elements.append(Paragraph(summary_text, styles["body"]))
    elements.append(Spacer(1, 8))

    # Savings highlight box (if we have numbers)
    if savings_totals:
        s_min, s_max, s_avg = savings_totals
        savings_box_text = (
            f'<b>Estimated Savings:</b> &nbsp; '
            f'Min: <font color="#067D62"><b>{currency} {s_min:,.2f}</b></font> &nbsp;&nbsp;|&nbsp;&nbsp; '
            f'Max: <font color="#067D62"><b>{currency} {s_max:,.2f}</b></font> &nbsp;&nbsp;|&nbsp;&nbsp; '
            f'Avg: <font color="#067D62"><b>{currency} {s_avg:,.2f}</b></font>'
        )
        savings_data = [[Paragraph(savings_box_text, styles["body_bold"])]]
        savings_table = Table(savings_data, colWidths=[7 * inch])
        savings_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F5E9")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#067D62")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        elements.append(savings_table)
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

        # Totals row(s) — include tax if present
        if tax_amount and total_with_tax:
            svc_rows.append([
                Paragraph("<b>Subtotal</b>", styles["body_bold"]),
                Paragraph(f"<b>{total_cost}</b>", styles["body_bold"]),
            ])
            svc_rows.append([
                Paragraph("<b>Tax</b>", styles["body_bold"]),
                Paragraph(f"<b>{_format_cost(tax_amount)}</b>", styles["body_bold"]),
            ])
            svc_rows.append([
                Paragraph("<b>Total (incl. tax)</b>", styles["body_bold"]),
                Paragraph(f"<b>{_format_cost(total_with_tax)}</b>", styles["body_bold"]),
            ])
        else:
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

    # Pie chart of service consumption
    elements.extend(_build_service_pie_chart(parsed_bill, styles))

    return elements


def _build_service_pie_chart(
    parsed_bill: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build a pie chart showing service consumption percentages."""
    elements: List[Any] = []
    service_totals = parsed_bill.get("service_totals", {})
    if not service_totals:
        return elements

    total = sum(float(v) for v in service_totals.values())
    if total <= 0:
        return elements

    # Build slices: services >= 1% shown individually, rest grouped as "Other"
    slices = []
    other_total = 0.0
    for svc, cost in sorted(service_totals.items(), key=lambda x: float(x[1]), reverse=True):
        pct = float(cost) / total * 100
        if pct >= 1.0:
            slices.append((svc, float(cost), pct))
        else:
            other_total += float(cost)

    if other_total > 0:
        other_pct = other_total / total * 100
        slices.append(("Other", other_total, other_pct))

    if not slices:
        return elements

    # Color palette for pie slices
    pie_colors = [
        colors.HexColor("#0066FF"),  # primary blue
        colors.HexColor("#00D4FF"),  # secondary blue
        colors.HexColor("#FF6B35"),  # accent orange
        colors.HexColor("#067D62"),  # green
        colors.HexColor("#8B5CF6"),  # purple
        colors.HexColor("#EC4899"),  # pink
        colors.HexColor("#F59E0B"),  # amber
        colors.HexColor("#10B981"),  # emerald
        colors.HexColor("#6366F1"),  # indigo
        colors.HexColor("#EF4444"),  # red
        colors.HexColor("#14B8A6"),  # teal
        colors.HexColor("#A855F7"),  # violet
        colors.HexColor("#F97316"),  # orange
        colors.HexColor("#3B82F6"),  # blue
        colors.HexColor("#84CC16"),  # lime
        colors.HexColor("#E11D48"),  # rose
        colors.HexColor("#0EA5E9"),  # sky
        colors.HexColor("#D946EF"),  # fuchsia
        colors.HexColor("#78716C"),  # stone (for "Other")
    ]

    # Create the drawing
    chart_width = 500
    chart_height = 220
    d = Drawing(chart_width, chart_height)

    pie = Pie()
    pie.x = 30
    pie.y = 20
    pie.width = 180
    pie.height = 180
    pie.data = [s[2] for s in slices]
    pie.labels = None  # We'll draw a legend instead

    for i in range(len(slices)):
        color_idx = i % len(pie_colors)
        pie.slices[i].fillColor = pie_colors[color_idx]
        pie.slices[i].strokeColor = colors.white
        pie.slices[i].strokeWidth = 1.5
        # Show percentage inside each slice
        pie.slices[i].label_visible = 1
        pie.slices[i].fontName = "Helvetica-Bold"
        pie.slices[i].fontSize = 7
        pie.slices[i].fontColor = colors.white
        pie.slices[i].labelRadius = 0.65

    # Set labels to show % inside slices (only for slices >= 3% to avoid clutter)
    pie.labels = [f"{s[2]:.0f}%" if s[2] >= 3.0 else "" for s in slices]

    d.add(pie)

    # Legend on the right side — show service name + amount
    legend_x = 240
    legend_y = chart_height - 20
    line_height = 14
    max_legend_items = min(len(slices), 15)
    currency = parsed_bill.get("currency", "USD")

    for i in range(max_legend_items):
        svc_name, cost_val, pct = slices[i]
        color_idx = i % len(pie_colors)
        y_pos = legend_y - (i * line_height)

        # Color swatch
        from reportlab.graphics.shapes import Rect
        swatch = Rect(legend_x, y_pos - 3, 10, 10, fillColor=pie_colors[color_idx], strokeColor=None)
        d.add(swatch)

        # Label: service name + cost amount
        label_text = f"{svc_name} ({currency} {cost_val:,.2f})"
        if len(label_text) > 45:
            label_text = label_text[:42] + "..."
        label = String(legend_x + 14, y_pos - 1, label_text, fontSize=8, fontName="Helvetica")
        d.add(label)

    elements.append(d)
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

        # --- Two-column body: left = explanation + billing + regions, right = recommendations ---
        left_parts: List[Any] = []
        left_parts.append(Paragraph(explanation, styles["body"]))
        if billing_details:
            left_parts.append(Spacer(1, 4))
            left_parts.append(Paragraph(
                f'<b>How you are charged:</b> {billing_details}',
                styles["body"],
            ))

        # Embed region breakdown inline (filter out regions < $0.10)
        region_breakdown = parsed_bill.get("region_breakdown", {})
        regions = region_breakdown.get(service, [])
        if regions:
            currency = parsed_bill.get("currency", "USD")
            significant_regions = [
                r for r in regions
                if float(r.get("cost", 0)) >= 0.10
            ]
            if significant_regions:
                left_parts.append(Spacer(1, 4))
                left_parts.append(Paragraph("<b>Region breakdown:</b>", styles["body_bold"]))
                for region_entry in significant_regions:
                    rname = region_entry.get("region", "Unknown")
                    rcost = _format_cost(region_entry.get("cost", 0))
                    details = region_entry.get("details", [])
                    # Build region line with optional details
                    region_line = f"\u2022 {rname}: {currency} {rcost}"
                    left_parts.append(Paragraph(region_line, styles["small"]))
                    # Show up to 3 detail lines per region
                    for d in details[:3]:
                        desc = d.get("description", "")
                        if len(desc) > 70:
                            desc = desc[:67] + "..."
                        left_parts.append(Paragraph(
                            f"&nbsp;&nbsp;&nbsp;{desc}",
                            styles["small"],
                        ))

        right_parts: List[Any] = []
        if recommendations:
            right_parts.append(Paragraph("<b>How to save:</b>", styles["body_bold"]))
            right_parts.append(Spacer(1, 2))

            # Compute per-service savings range
            svc_savings = _compute_service_savings(_extract_cost(item), recommendations)
            if svc_savings:
                s_min, s_max, s_avg = svc_savings
                currency = parsed_bill.get("currency", "USD")
                savings_line = (
                    f'<font color="#067D62"><b>Potential savings: '
                    f'{currency} {s_min:,.2f} – {currency} {s_max:,.2f} '
                    f'(avg {currency} {s_avg:,.2f})</b></font>'
                )
                right_parts.append(Paragraph(savings_line, styles["rec_savings"]))
                right_parts.append(Spacer(1, 4))

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
    parsed_bill: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Build the Savings Plans & Reserved Instances recommendation section."""
    elements: List[Any] = []

    sp_analysis = ai_analysis.get("savings_plan_analysis", {})
    if not sp_analysis:
        # Fallback: build section from parsed bill commitment_discounts data
        sp_analysis = _build_fallback_savings_analysis(parsed_bill)
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

def _build_fallback_savings_analysis(parsed_bill: Dict[str, Any]) -> Dict[str, Any]:
    """Build a fallback savings_plan_analysis dict from parsed bill commitment_discounts."""
    discounts = parsed_bill.get("commitment_discounts", {})
    has_sp = discounts.get("has_savings_plans", False)
    has_ri = discounts.get("has_reserved_instances", False)

    # Always show this section — it's valuable even when no SP/RI detected
    recommendation = ""
    how_to_purchase = ""
    potential_savings = ""

    if not has_sp and not has_ri:
        recommendation = (
            "No Savings Plans or Reserved Instances were detected in this bill. "
            "You are likely paying On-Demand rates for all services. "
            "AWS offers Compute Savings Plans (up to 66% off EC2/Lambda/Fargate), "
            "EC2 Instance Savings Plans (up to 72% off), "
            "and Database Savings Plans (up to 35% off RDS/DynamoDB/ElastiCache). "
            "For steady-state EC2 workloads, Standard Reserved Instances offer up to 72% savings, "
            "while Convertible RIs offer up to 66% with more flexibility."
        )
        how_to_purchase = (
            "Go to AWS Cost Explorer console > Savings Plans > Purchase Savings Plans. "
            "Choose your hourly commitment ($/hr), term (1 or 3 years), and payment option "
            "(All Upfront for maximum discount, Partial Upfront, or No Upfront). "
            "For Reserved Instances: EC2 Console > Reserved Instances > Purchase."
        )
        potential_savings = "30-72% on committed usage"
    elif has_sp and not has_ri:
        recommendation = (
            "Savings Plans are active on this account. "
            "Review your coverage in Cost Explorer to ensure optimal utilization. "
            "Consider Reserved Instances for steady-state EC2/RDS workloads for deeper discounts."
        )
    elif has_ri and not has_sp:
        recommendation = (
            "Reserved Instances are active on this account. "
            "Consider Savings Plans for additional flexibility across services and regions."
        )
    else:
        recommendation = (
            "Both Savings Plans and Reserved Instances are active. "
            "Review utilization in Cost Explorer to ensure you are maximizing coverage."
        )

    return {
        "has_savings_plans": has_sp,
        "has_reserved_instances": has_ri,
        "recommendation": recommendation,
        "potential_savings_percent": potential_savings,
        "how_to_purchase": how_to_purchase,
    }



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
