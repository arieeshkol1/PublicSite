"""
AWS Bill Analyzer - PDF Bill Parser Module

Uses pdfplumber to extract text and tables from AWS invoice PDFs.
Parses service names, costs, billing dates, and other billing information.
Returns a ParsedBill dict with line items, totals, and metadata.
"""

import io
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

import pdfplumber

# Type alias for the parsed bill structure
ParsedBill = Dict[str, Any]

# Regex patterns for AWS invoice metadata
INVOICE_NUMBER_PATTERNS = [
    re.compile(r"Invoice\s+Number[:\s]*([A-Z0-9]+-\d+)", re.IGNORECASE),
    re.compile(r"Invoice\s*#?\s*[:\s]*([A-Z0-9]+-\d+)", re.IGNORECASE),
    re.compile(r"([A-Z]{2,}[A-Z0-9]*-\d{4,})"),
]

ACCOUNT_ID_PATTERNS = [
    re.compile(r"Account\s+(?:number|ID|id)[:\s]*(\d{12})", re.IGNORECASE),
    re.compile(r"Account[:\s]*(\d{12})", re.IGNORECASE),
    re.compile(r"\b(\d{12})\b"),
]

# Date patterns: "Month DD, YYYY" or "YYYY-MM-DD" or "DD/MM/YYYY" or "MM/DD/YYYY"
DATE_PATTERNS = [
    re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}",
        re.IGNORECASE,
    ),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
]

BILLING_PERIOD_PATTERNS = [
    re.compile(
        r"(?:Billing\s+Period|Statement\s+Date|Invoice\s+Date|Period)[:\s]*"
        r"(.+?)(?:\n|$)",
        re.IGNORECASE,
    ),
]

# Month name to number mapping
MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Cost pattern: matches dollar amounts like $1,234.56 or 1234.56
COST_PATTERN = re.compile(r"\$?\s*([\d,]+\.\d{2})")


def parse_bill(pdf_bytes: bytes) -> ParsedBill:
    """
    Parse an AWS invoice PDF and extract billing information.

    Uses pdfplumber to extract text and tables from the PDF, then parses
    the content to identify services, costs, dates, and other metadata.

    Args:
        pdf_bytes: Raw bytes of the uploaded AWS invoice PDF.

    Returns:
        ParsedBill dict with the following structure:
            {
                "line_items": [{"service": str, "cost": Decimal, "description": str}],
                "total_cost": Decimal,
                "currency": str,
                "period_start": str,
                "period_end": str,
                "invoice_number": str,
                "account_id": str,
                "service_totals": {"service_name": Decimal}
            }

    Raises:
        ValueError: If the PDF cannot be parsed or contains no billing data.
    """
    if not pdf_bytes:
        raise ValueError("Empty file provided. Please upload a valid AWS invoice PDF.")

    extracted = _extract_text_and_tables(pdf_bytes)
    text = extracted["text"]
    tables = extracted["tables"]

    if not text.strip():
        raise ValueError(
            "The PDF contains no readable text. "
            "Please upload a valid AWS invoice PDF."
        )

    metadata = _extract_metadata(text)
    line_items = _parse_line_items(text, tables)

    if not line_items:
        raise ValueError(
            "No billing line items found in the PDF. "
            "Please ensure this is a valid AWS invoice."
        )

    total_cost = sum(item["cost"] for item in line_items)
    service_totals = _aggregate_service_totals(line_items)

    return {
        "line_items": line_items,
        "total_cost": total_cost,
        "currency": metadata.get("currency", "USD"),
        "period_start": metadata.get("period_start", "N/A"),
        "period_end": metadata.get("period_end", "N/A"),
        "invoice_number": metadata.get("invoice_number", "N/A"),
        "account_id": metadata.get("account_id", "N/A"),
        "service_totals": service_totals,
    }


def _extract_text_and_tables(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Extract raw text and table data from a PDF using pdfplumber.

    Args:
        pdf_bytes: Raw bytes of the PDF file.

    Returns:
        Dict with 'text' (full extracted text) and 'tables' (list of tables).

    Raises:
        ValueError: If the file is not a valid PDF or cannot be read.
    """
    try:
        pdf_stream = io.BytesIO(pdf_bytes)
        with pdfplumber.open(pdf_stream) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError(
                    "The PDF file has no pages. "
                    "Please upload a valid AWS invoice PDF."
                )

            all_text_parts: List[str] = []
            all_tables: List[List[List[str]]] = []

            for page in pdf.pages:
                page_text = page.extract_text() or ""
                all_text_parts.append(page_text)

                page_tables = page.extract_tables() or []
                for table in page_tables:
                    # Normalize None cells to empty strings
                    cleaned_table = [
                        [cell if cell is not None else "" for cell in row]
                        for row in table
                        if row is not None
                    ]
                    if cleaned_table:
                        all_tables.append(cleaned_table)

            return {
                "text": "\n".join(all_text_parts),
                "tables": all_tables,
            }
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(
            f"Unable to read the PDF file: {str(e)}. "
            "Please ensure the file is a valid, uncorrupted PDF."
        )


def _parse_line_items(
    text: str, tables: List[List[List[str]]]
) -> List[Dict[str, Any]]:
    """
    Parse individual line items (service, cost, description) from extracted content.

    Tries table-based extraction first (more reliable for structured invoices),
    then falls back to text-based regex extraction.

    Args:
        text: Full extracted text from the PDF.
        tables: List of tables extracted from the PDF.

    Returns:
        List of line item dicts with 'service', 'cost', and 'description' keys.
    """
    items = _parse_line_items_from_tables(tables)
    if not items:
        items = _parse_line_items_from_text(text)
    return items


def _parse_line_items_from_tables(
    tables: List[List[List[str]]],
) -> List[Dict[str, Any]]:
    """
    Extract line items from table data.

    Looks for tables that contain cost-like columns (dollar amounts)
    and service name columns.
    """
    items: List[Dict[str, Any]] = []

    for table in tables:
        if len(table) < 2:
            continue

        # Try to identify header row and cost/service columns
        header = table[0]
        cost_col = _find_column_index(header, ["amount", "cost", "total", "charges", "price"])
        service_col = _find_column_index(header, ["service", "description", "product", "name", "item"])

        if cost_col is not None:
            # If no explicit service column, use the first text column
            if service_col is None:
                for i, cell in enumerate(header):
                    if i != cost_col and cell and cell.strip():
                        service_col = i
                        break
                if service_col is None:
                    service_col = 0

            for row in table[1:]:
                if len(row) <= max(cost_col, service_col):
                    continue

                cost_val = _parse_cost(row[cost_col])
                service_name = (row[service_col] or "").strip()

                if cost_val is not None and service_name:
                    # Build description from other columns
                    desc_parts = []
                    for i, cell in enumerate(row):
                        if i not in (cost_col, service_col) and cell and cell.strip():
                            desc_parts.append(cell.strip())
                    description = " - ".join(desc_parts) if desc_parts else service_name

                    items.append({
                        "service": service_name,
                        "cost": cost_val,
                        "description": description,
                    })
        else:
            # No header match — scan rows for cost patterns
            items.extend(_scan_table_rows_for_costs(table))

    return items


def _scan_table_rows_for_costs(
    table: List[List[str]],
) -> List[Dict[str, Any]]:
    """Scan table rows for any cells containing cost values."""
    items: List[Dict[str, Any]] = []
    for row in table:
        if not row:
            continue
        # Find the last cell with a cost value (usually the amount column)
        cost_val = None
        cost_idx = -1
        for i in range(len(row) - 1, -1, -1):
            parsed = _parse_cost(row[i])
            if parsed is not None:
                cost_val = parsed
                cost_idx = i
                break

        if cost_val is not None and cost_idx > 0:
            # Use the first non-empty cell as service name
            service_name = ""
            for i, cell in enumerate(row):
                if i != cost_idx and cell and cell.strip():
                    service_name = cell.strip()
                    break

            if service_name:
                items.append({
                    "service": service_name,
                    "cost": cost_val,
                    "description": service_name,
                })
    return items


def _parse_line_items_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract line items from raw text using regex patterns.

    Looks for lines that contain both a service-like name and a dollar amount.
    Common AWS invoice patterns:
        - "Amazon EC2  $45.23"
        - "AWS Lambda    $1.50"
        - "Amazon Simple Storage Service  $12.34"
    """
    items: List[Dict[str, Any]] = []
    # Pattern: service name followed by a cost
    line_pattern = re.compile(
        r"^(.*?(?:Amazon|AWS|Elastic|Cloud)\s*\S+.*?)\s+"
        r"\$?\s*([\d,]+\.\d{2})\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    for match in line_pattern.finditer(text):
        service_name = match.group(1).strip()
        cost_str = match.group(2).replace(",", "")
        try:
            cost_val = Decimal(cost_str)
            if cost_val > Decimal("0"):
                items.append({
                    "service": service_name,
                    "cost": cost_val,
                    "description": service_name,
                })
        except InvalidOperation:
            continue

    # Fallback: look for any line with a dollar amount preceded by text
    if not items:
        fallback_pattern = re.compile(
            r"^(.{3,}?)\s+\$\s*([\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for match in fallback_pattern.finditer(text):
            service_name = match.group(1).strip()
            cost_str = match.group(2).replace(",", "")
            try:
                cost_val = Decimal(cost_str)
                if cost_val > Decimal("0"):
                    items.append({
                        "service": service_name,
                        "cost": cost_val,
                        "description": service_name,
                    })
            except InvalidOperation:
                continue

    return items


def _extract_metadata(text: str) -> Dict[str, str]:
    """
    Extract invoice metadata: invoice number, account ID, billing period, currency.

    Args:
        text: Full extracted text from the PDF.

    Returns:
        Dict with 'invoice_number', 'account_id', 'period_start',
        'period_end', and 'currency' keys.
    """
    metadata: Dict[str, str] = {
        "invoice_number": "N/A",
        "account_id": "N/A",
        "period_start": "N/A",
        "period_end": "N/A",
        "currency": "USD",
    }

    # Extract invoice number
    for pattern in INVOICE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["invoice_number"] = match.group(1) if match.lastindex else match.group(0)
            break

    # Extract account ID (12-digit number)
    for pattern in ACCOUNT_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["account_id"] = match.group(1)
            break

    # Extract billing period dates
    period_start, period_end = _extract_billing_period(text)
    metadata["period_start"] = period_start
    metadata["period_end"] = period_end

    # Detect currency
    if "EUR" in text or "€" in text:
        metadata["currency"] = "EUR"
    elif "GBP" in text or "£" in text:
        metadata["currency"] = "GBP"
    # Default is USD

    return metadata


def _extract_billing_period(text: str) -> tuple:
    """
    Extract billing period start and end dates from the text.

    Returns:
        Tuple of (period_start, period_end) as ISO date strings (YYYY-MM-DD),
        or ("N/A", "N/A") if not found.
    """
    # Try explicit "billing period" line first
    # AWS invoices use: "billing period February 1 - February 28, 2026"
    period_line_pattern = re.compile(
        r"billing\s+period\s+(.+?)(?:\n|$)", re.IGNORECASE
    )
    match = period_line_pattern.search(text)
    if match:
        period_text = match.group(1).strip()
        dates = _parse_period_range(period_text)
        if dates:
            return dates

    # Try other billing period patterns
    for pattern in BILLING_PERIOD_PATTERNS:
        match = pattern.search(text)
        if match:
            period_text = match.group(1).strip()
            dates = _extract_dates_from_text(period_text)
            if len(dates) >= 2:
                return dates[0], dates[1]
            elif len(dates) == 1:
                return dates[0], dates[0]

    # Fallback: find all dates in the document and use the range
    all_dates = _extract_dates_from_text(text)
    if len(all_dates) >= 2:
        sorted_dates = sorted(all_dates)
        return sorted_dates[0], sorted_dates[-1]
    elif len(all_dates) == 1:
        return all_dates[0], all_dates[0]

    return "N/A", "N/A"


def _parse_period_range(period_text: str) -> tuple | None:
    """
    Parse a billing period range string like "February 1 - February 28, 2026".

    Handles cases where the year only appears on the end date.

    Returns:
        Tuple of (start_iso, end_iso) or None if unparseable.
    """
    # Pattern: "Month Day - Month Day, Year" (year only on end)
    range_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2})\s*[-\u2013\u2014]\s*"
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    )
    match = range_pattern.search(period_text)
    if match:
        start_month = MONTH_MAP[match.group(1).lower()]
        start_day = match.group(2).zfill(2)
        end_month = MONTH_MAP[match.group(3).lower()]
        end_day = match.group(4).zfill(2)
        year = match.group(5)
        start_iso = f"{year}-{start_month}-{start_day}"
        end_iso = f"{year}-{end_month}-{end_day}"
        return start_iso, end_iso

    # Pattern: "Month Day, Year - Month Day, Year" (year on both)
    full_range_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\s*[-\u2013\u2014]\s*"
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    )
    match = full_range_pattern.search(period_text)
    if match:
        start_month = MONTH_MAP[match.group(1).lower()]
        start_day = match.group(2).zfill(2)
        start_year = match.group(3)
        end_month = MONTH_MAP[match.group(4).lower()]
        end_day = match.group(5).zfill(2)
        end_year = match.group(6)
        start_iso = f"{start_year}-{start_month}-{start_day}"
        end_iso = f"{end_year}-{end_month}-{end_day}"
        return start_iso, end_iso

    # Fallback to generic date extraction
    dates = _extract_dates_from_text(period_text)
    if len(dates) >= 2:
        return dates[0], dates[1]
    return None


def _extract_dates_from_text(text: str) -> List[str]:
    """
    Find all dates in text and return them as ISO format strings (YYYY-MM-DD).
    """
    dates: List[str] = []

    # "Month DD, YYYY" format
    month_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    )
    for match in month_pattern.finditer(text):
        month = MONTH_MAP[match.group(1).lower()]
        day = match.group(2).zfill(2)
        year = match.group(3)
        dates.append(f"{year}-{month}-{day}")

    # "YYYY-MM-DD" format
    iso_pattern = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
    for match in iso_pattern.finditer(text):
        year, month, day = match.group(1), match.group(2), match.group(3)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            dates.append(f"{year}-{month}-{day}")

    return dates


def _aggregate_service_totals(
    line_items: List[Dict[str, Any]],
) -> Dict[str, Decimal]:
    """
    Aggregate line item costs by service name.

    Args:
        line_items: List of parsed line item dicts.

    Returns:
        Dict mapping service names to their total cost as Decimal.
    """
    totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in line_items:
        totals[item["service"]] += item["cost"]
    return dict(totals)


def _find_column_index(
    header: List[str], keywords: List[str]
) -> int | None:
    """
    Find the index of a column in a table header that matches any of the keywords.
    """
    for i, cell in enumerate(header):
        if cell is None:
            continue
        cell_lower = cell.strip().lower()
        for keyword in keywords:
            if keyword in cell_lower:
                return i
    return None


def _parse_cost(value: str | None) -> Decimal | None:
    """
    Parse a cost string into a Decimal.

    Handles formats like "$1,234.56", "1234.56", "$45.23", "(12.34)" for credits.
    Returns None if the value cannot be parsed as a cost.
    """
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    # Check for credit/negative amounts in parentheses
    is_negative = False
    if value.startswith("(") and value.endswith(")"):
        is_negative = True
        value = value[1:-1]

    # Remove currency symbols and whitespace
    value = value.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()

    if not value:
        return None

    try:
        result = Decimal(value)
        if is_negative:
            result = -result
        return result
    except InvalidOperation:
        return None
