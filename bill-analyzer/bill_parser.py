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

# Month name to number mapping (full names)
MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Abbreviated month name to number mapping
MONTH_ABBREV_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Cost pattern: matches dollar amounts like $1,234.56 or 1234.56
COST_PATTERN = re.compile(r"\$?\s*([\d,]+\.\d{2})")

# Currency codes to strip from service names
CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "INR", "BRL"}


def _clean_service_name(name: str) -> str:
    """Remove trailing currency codes and clean up service names."""
    cleaned = name.strip()
    # Remove trailing currency code (e.g., "Amazon EC2 USD" -> "Amazon EC2")
    for code in CURRENCY_CODES:
        if cleaned.upper().endswith(f" {code}"):
            cleaned = cleaned[: -(len(code) + 1)].strip()
            break
    # Remove leading/trailing dashes and whitespace
    cleaned = cleaned.strip(" -")
    return cleaned


def parse_bill(pdf_bytes: bytes) -> ParsedBill:
    """
    Parse an AWS invoice PDF and extract billing information.

    Supports two formats:
        1. Traditional AWS Tax Invoice (EMEA SARL style)
        2. AWS Billing Console export ("Charges by service" style)

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

    # First pass: extract text only (fast — skips expensive table extraction)
    text_only = _extract_text_and_tables(pdf_bytes, text_only=True)
    text = text_only["text"]

    if not text.strip():
        raise ValueError(
            "The PDF contains no readable text. "
            "Please upload a valid AWS invoice PDF."
        )

    # Strip previously-generated analysis report pages from the text
    # (in case user re-uploads an analyzed PDF that has report + original appended)
    for report_marker in ["Slash My Bill Report", "Bill Analysis Report"]:
        idx = text.find(report_marker)
        if idx >= 0 and idx < 200:
            # Find where the original invoice starts
            for invoice_marker in ["Invoice Number", "Tax Invoice", "Charges by service",
                                   "AWS bill summary", "billing period"]:
                inv_idx = text.find(invoice_marker)
                if inv_idx > idx:
                    text = text[inv_idx:]
                    break

    # Detect format: billing console export vs traditional invoice
    if _is_billing_console_format(text):
        # Billing console format only needs text, no tables
        return _parse_billing_console(text, [])

    # Traditional invoice format — need tables too (second pass)
    extracted = _extract_text_and_tables(pdf_bytes)
    tables = extracted["tables"]

    metadata = _extract_metadata(text)
    line_items = _parse_line_items(text, tables)

    if not line_items:
        raise ValueError(
            "No billing line items found in the PDF. "
            "Please ensure this is a valid AWS invoice."
        )

    total_cost = sum(item["cost"] for item in line_items)
    service_totals = _aggregate_service_totals(line_items)
    commitment_discounts = _detect_commitment_discounts(text)

    # Extract tax amount
    tax_amount = _extract_tax_amount(text)

    result = {
        "line_items": line_items,
        "total_cost": total_cost,
        "currency": metadata.get("currency", "USD"),
        "period_start": metadata.get("period_start", "N/A"),
        "period_end": metadata.get("period_end", "N/A"),
        "invoice_number": metadata.get("invoice_number", "N/A"),
        "account_id": metadata.get("account_id", "N/A"),
        "service_totals": service_totals,
        "commitment_discounts": commitment_discounts,
    }
    if tax_amount and tax_amount > Decimal("0"):
        result["tax_amount"] = tax_amount
        result["total_with_tax"] = total_cost + tax_amount
    return result


def _detect_commitment_discounts(text: str) -> Dict[str, Any]:
    """
    Detect whether Savings Plans or Reserved Instances are used in the bill.

    Only matches actual billing indicators (charges, fees, applied discounts),
    NOT recommendation text like "Implement Savings Plans" or "consider Reserved Instances".

    Returns:
        Dict with:
            "has_savings_plans": bool,
            "has_reserved_instances": bool,
            "savings_plan_details": list of detected SP references,
            "reserved_instance_details": list of detected RI references,
            "savings_amount": Decimal or None (total savings shown in bill),
    """
    result: Dict[str, Any] = {
        "has_savings_plans": False,
        "has_reserved_instances": False,
        "savings_plan_details": [],
        "reserved_instance_details": [],
        "savings_amount": None,
    }

    # Strip any analysis report pages from the text to avoid false positives
    # from our own recommendations text
    clean_text = text
    for marker in ["Slash My Bill Report", "Bill Analysis Report"]:
        idx = clean_text.find(marker)
        if idx >= 0 and idx < 200:
            # Find where the original invoice starts
            invoice_start = clean_text.find("Invoice Number")
            if invoice_start < 0:
                invoice_start = clean_text.find("Tax Invoice")
            if invoice_start < 0:
                invoice_start = clean_text.find("Charges by service")
            if invoice_start > idx:
                clean_text = clean_text[invoice_start:]

    # --- Savings Plans detection ---
    # Only match actual billing line items, NOT recommendation text
    sp_indicators = [
        re.compile(r"Savings\s+Plans?\s+for\s+compute", re.IGNORECASE),
        re.compile(r"Savings\s+Plans?\s+negation", re.IGNORECASE),
        re.compile(r"SavingsPlan\s+(?:Covered|Negation|Recurring)", re.IGNORECASE),
        re.compile(r"Savings\s+Plans?\s+\$[\d,]+\.\d{2}", re.IGNORECASE),
        re.compile(r"Compute\s+Savings\s+Plan\s+\$", re.IGNORECASE),
    ]
    # Negative patterns — skip if context contains recommendation language
    skip_phrases = [
        "implement", "consider", "commit to", "how to", "save up to",
        "recommend", "purchase", "get started", "potential savings",
        "savings plans: not detected", "savings plans: active",
    ]

    sp_details = []
    for pattern in sp_indicators:
        for match in pattern.finditer(clean_text):
            start = match.start()
            end = min(match.end() + 120, len(clean_text))
            context = clean_text[start:end].replace("\n", " ").strip()
            # Skip if context looks like recommendation text
            context_lower = context.lower()
            if any(phrase in context_lower for phrase in skip_phrases):
                continue
            sp_details.append(context)

    if sp_details:
        result["has_savings_plans"] = True
        seen = set()
        unique = []
        for d in sp_details:
            key = d[:60]
            if key not in seen:
                seen.add(key)
                unique.append(d)
        result["savings_plan_details"] = unique[:10]

    # --- Reserved Instances detection ---
    # Only match actual billing indicators
    ri_indicators = [
        re.compile(r"Reserved\s+Instance\s+(?:fee|charge|applied)", re.IGNORECASE),
        re.compile(r"\bRI\s+(?:fee|charge|discount|applied)", re.IGNORECASE),
        re.compile(r"Reserved\s+(?:capacity|pricing)\s+\$", re.IGNORECASE),
        re.compile(r"Reservation\s+applied", re.IGNORECASE),
        re.compile(r"Reserved\s+Instance.*USD\s+[\d,]+\.\d{2}", re.IGNORECASE),
    ]
    ri_details = []
    for pattern in ri_indicators:
        for match in pattern.finditer(clean_text):
            start = match.start()
            end = min(match.end() + 120, len(clean_text))
            context = clean_text[start:end].replace("\n", " ").strip()
            context_lower = context.lower()
            if any(phrase in context_lower for phrase in skip_phrases):
                continue
            ri_details.append(context)

    if ri_details:
        result["has_reserved_instances"] = True
        seen = set()
        unique = []
        for d in ri_details:
            key = d[:60]
            if key not in seen:
                seen.add(key)
                unique.append(d)
        result["reserved_instance_details"] = unique[:10]

    # --- Savings amount detection ---
    savings_pattern = re.compile(
        r"(?:Savings|Total\s+savings|You\s+saved)[:\s]*\$?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    )
    savings_match = savings_pattern.search(clean_text)
    if savings_match:
        try:
            result["savings_amount"] = Decimal(savings_match.group(1).replace(",", ""))
        except InvalidOperation:
            pass

    return result


def _is_billing_console_format(text: str) -> bool:
    """Detect if the PDF is an AWS Billing Console export."""
    indicators = [
        "Charges by service",
        "AWS bill summary",
        "Grand total:",
        "Billing period Account ID Bill status",
    ]
    score = sum(1 for ind in indicators if ind in text)
    return score >= 2


def _parse_billing_console(text: str, tables: List[List[List[str]]]) -> ParsedBill:
    """
    Parse an AWS Billing Console export PDF.

    This format has:
        - Header: "Billing period Account ID Bill status ..."
        - "Charges by service" section with per-service totals and line items
        - "Taxes by service" section at the end
    """
    metadata = _extract_billing_console_metadata(text)
    line_items = _extract_billing_console_services(text)

    if not line_items:
        raise ValueError(
            "No billing line items found in the PDF. "
            "Please ensure this is a valid AWS bill."
        )

    # Enrich line items with detailed pricing sub-items for Bedrock
    detail_items = _extract_billing_console_details(text, line_items)

    # Extract region-level breakdown per service
    region_breakdown = _extract_region_breakdown(text, line_items)

    total_cost = sum(item["cost"] for item in line_items)
    service_totals = _aggregate_service_totals(line_items)
    commitment_discounts = _detect_commitment_discounts(text)

    # Extract tax amount from "Taxes by service" or "Total tax" lines
    tax_amount = _extract_tax_amount(text)

    result = {
        "line_items": line_items + detail_items,
        "total_cost": total_cost,
        "currency": metadata.get("currency", "USD"),
        "period_start": metadata.get("period_start", "N/A"),
        "period_end": metadata.get("period_end", "N/A"),
        "invoice_number": metadata.get("invoice_number", "N/A"),
        "account_id": metadata.get("account_id", "N/A"),
        "service_totals": service_totals,
        "commitment_discounts": commitment_discounts,
        "region_breakdown": region_breakdown,
    }
    if tax_amount and tax_amount > Decimal("0"):
        result["tax_amount"] = tax_amount
        result["total_with_tax"] = total_cost + tax_amount
    return result


def _extract_billing_console_metadata(text: str) -> Dict[str, str]:
    """Extract metadata from billing console format."""
    metadata: Dict[str, str] = {
        "invoice_number": "N/A",
        "account_id": "N/A",
        "period_start": "N/A",
        "period_end": "N/A",
        "currency": "USD",
    }

    # Account ID: 12-digit number on first page near header
    acct_match = re.search(r"\b(\d{12})\b", text)
    if acct_match:
        metadata["account_id"] = acct_match.group(1)

    # Invoice IDs from payment section (e.g., "EUINIL26-167895" or "2544926965")
    invoice_match = re.search(r"Invoice\s+(?:ID\s+)?([A-Z]{2,}[A-Z0-9]*-\d+)", text)
    if invoice_match:
        metadata["invoice_number"] = invoice_match.group(1)
    else:
        # Try numeric invoice ID
        inv_num_match = re.search(r"Invoice\s+(\d{7,})", text)
        if inv_num_match:
            metadata["invoice_number"] = inv_num_match.group(1)

    # Billing period: "Feb 1 - Feb 28, 2026" (abbreviated months)
    abbrev_range = re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s*"
        r"[-\u2013\u2014]\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    )
    period_match = abbrev_range.search(text)
    if period_match:
        sm = MONTH_ABBREV_MAP[period_match.group(1).lower()]
        sd = period_match.group(2).zfill(2)
        em = MONTH_ABBREV_MAP[period_match.group(3).lower()]
        ed = period_match.group(4).zfill(2)
        year = period_match.group(5)
        metadata["period_start"] = f"{year}-{sm}-{sd}"
        metadata["period_end"] = f"{year}-{em}-{ed}"
    else:
        # Fallback to full month name extraction
        period_start, period_end = _extract_billing_period(text)
        metadata["period_start"] = period_start
        metadata["period_end"] = period_end

    # Currency detection
    if "EUR" in text and "USD" not in text:
        metadata["currency"] = "EUR"
    elif "GBP" in text and "USD" not in text:
        metadata["currency"] = "GBP"

    return metadata


def _extract_billing_console_services(text: str) -> List[Dict[str, Any]]:
    """
    Extract top-level service charges from the 'Charges by service' section.

    Looks for lines like:
        "Elastic Compute Cloud USD 300.26"
        "Virtual Private Cloud USD 132.05"

    Only captures the top-level service totals (not sub-items or regions).
    Stops at "Total tax" or "Charges by account" or "Invoices" sections.
    """
    items: List[Dict[str, Any]] = []

    # Find the "Charges by service" section
    charges_match = re.search(r"Charges by service\b", text)
    if not charges_match:
        return items

    charges_text = text[charges_match.end():]

    # Cut off at known section boundaries
    for boundary in [
        "Charges by account",
        "Invoices\n",
        "Tax Invoices and Additional Documents",
        "Savings \\(",
    ]:
        boundary_match = re.search(boundary, charges_text)
        if boundary_match:
            charges_text = charges_text[:boundary_match.start()]

    # Match all lines ending with "USD amount"
    line_pattern = re.compile(
        r"^(.+?)\s+USD\s+([\d,]+\.\d{2})\s*$",
        re.MULTILINE,
    )

    # Region prefixes and sub-item indicators to skip
    skip_prefixes = (
        "EU (", "US ", "Israel", "Asia", "Africa", "Canada", "South America",
        "Middle East", "Global", "Any", "Bandwidth", "EBS",
    )
    sub_item_indicators = (
        "EUC1-", "USE1-", "EU-", "ILC1-", "APN1-", "EUN1-", "USW2-",
        "NatGateway", "running Linux", "T3CPUCredits", "Provisioned Storage",
        "Public IPv4", "TimedStorage", "Requests-Tier", "ByteHrs",
        "Fargate-", "Fargate -", "vCPU-Hours", "GB-Hours", "DashboardHour",
        "Outbound", "MessageFees", "MessageCount", "DNS-Queries",
        "HostedZone", "Automation-", "Lambda-GB",
        "KMS-Requests", "ApiGateway", "Invalidations",
        "for MySQL", "for PostgreSQL", "for Aurora",
        "- Application", "- Network",
        "ScriptDuration", "StepCount",
        "AWS Fargate", "AmazonCloudWatch ", "Amazon CloudWatch",
        "Amazon Elastic Compute Cloud ",
        "Amazon Virtual Private Cloud ",
        "Amazon Relational Database Service ",
        "Amazon Simple Storage Service ",
        "Amazon EC2 Container Registry ",
        "Amazon Simple Queue Service ",
        "Amazon Simple Email Service ",
        "AWS End User Messaging ",
        "AWS Systems Manager ",
        "AWS Secrets Manager ",
        "AWS Data Transfer ",
        "Amazon Route 53 ",
        "AWS Certificate Manager ",
        "Amazon CloudFront ",
        "AWS Key Management Service ",
        "AWS Lambda ",
        "Amazon Elastic Container Service ",
        "Elastic Load Balancing -",
        "AWS Glue ",
    )

    seen_services: Dict[str, bool] = {}

    for match in line_pattern.finditer(charges_text):
        service_name = match.group(1).strip()
        cost_str = match.group(2).replace(",", "")

        # Skip pricing descriptions, regions, sub-items, totals, headers
        if service_name.startswith(("$", "USD")):
            continue
        if service_name.startswith(skip_prefixes):
            continue
        if any(ind in service_name for ind in sub_item_indicators):
            continue
        if "Total" in service_name:
            continue
        if "Amazon Web Services" in service_name:
            continue
        if "Description" in service_name:
            continue
        # Skip lines with pipe chars (usage descriptions)
        if "|" in service_name:
            continue
        # Skip pricing/usage description lines
        if "per " in service_name.lower() and "Count" in service_name:
            continue
        if service_name.startswith("Cost per"):
            continue
        # Must start with a letter
        if not service_name[0].isalpha():
            continue

        try:
            cost_val = Decimal(cost_str)
        except InvalidOperation:
            continue

        if cost_val <= Decimal("0"):
            continue

        cleaned_name = _clean_service_name(service_name)

        # Deduplicate: keep only the first (highest-level) occurrence
        if cleaned_name in seen_services:
            continue
        seen_services[cleaned_name] = True

        items.append({
            "service": cleaned_name,
            "cost": cost_val,
            "description": cleaned_name,
        })

    return items


def _extract_region_breakdown(
    text: str, line_items: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract region-level cost breakdown and instance/resource details per service.

    Parses the billing console text to find region lines like:
        "US East (N. Virginia) USD 250.00"
        "EU (Ireland) USD 50.00"
    and detail lines like:
        "$0.097 per db.t3.medium Single-AZ instance hour ... 672 Hrs USD 65.18"

    Groups them under their parent service.

    Returns:
        Dict mapping service name -> list of region/detail dicts:
        {
            "Elastic Compute Cloud": [
                {"region": "US East (N. Virginia)", "cost": Decimal("250.00"), "details": [
                    {"description": "2x t3.xlarge running Linux, 672 Hrs at $0.1664/Hr", "cost": Decimal("223.66")}
                ]}
            ]
        }
    """
    breakdown: Dict[str, List[Dict[str, Any]]] = {}

    charges_match = re.search(r"Charges by service\b", text)
    if not charges_match:
        return breakdown

    charges_text = text[charges_match.end():]

    # Cut off at known boundaries
    for boundary in ["Charges by account", "Invoices\n", "Tax Invoices"]:
        idx = charges_text.find(boundary)
        if idx > 0:
            charges_text = charges_text[:idx]

    service_names = [item["service"] for item in line_items]

    # Region name patterns
    region_prefixes = (
        "US East", "US West", "EU (", "Europe (", "Asia Pacific",
        "Canada", "South America", "Middle East", "Africa",
        "Israel", "Global", "Any",
    )

    # USD amount pattern at end of line
    usd_pattern = re.compile(r"^(.+?)\s+USD\s+([\d,]+\.\d{2})\s*$", re.MULTILINE)

    # Detail pricing pattern: $rate per <description> <qty> <unit> USD <amount>
    detail_pattern = re.compile(
        r"\$([\d,.]+)\s+per\s+(.+?)\s+([\d,.]+)\s+(Hrs?|GB|Requests?|Count|Queries|Keys?|Secrets?|Hrs:HrsUsage)\s+USD\s+([\d,.]+)",
        re.IGNORECASE,
    )

    current_service = ""
    current_region_name = ""
    current_region_entry: Dict[str, Any] | None = None

    for line in charges_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line is a top-level service header
        is_service_header = False
        for svc in service_names:
            if stripped.startswith(svc) and "USD" in stripped:
                current_service = svc
                is_service_header = True
                if current_service not in breakdown:
                    breakdown[current_service] = []
                current_region_name = ""
                current_region_entry = None
                break

        if is_service_header:
            continue

        if not current_service:
            continue

        # Check if this is a region line (e.g., "US East (N. Virginia) USD 132.05")
        is_region = False
        for prefix in region_prefixes:
            if stripped.startswith(prefix):
                is_region = True
                break

        if is_region:
            region_match = usd_pattern.match(stripped)
            if region_match:
                region_name = region_match.group(1).strip()
                region_cost_str = region_match.group(2).replace(",", "")
                try:
                    region_cost = Decimal(region_cost_str)
                except InvalidOperation:
                    continue
                current_region_name = region_name
                current_region_entry = {
                    "region": region_name,
                    "cost": region_cost,
                    "details": [],
                }
                breakdown[current_service].append(current_region_entry)
            continue

        # Check if this is a detail pricing line
        for match in detail_pattern.finditer(stripped):
            rate = match.group(1).replace(",", "")
            desc_text = match.group(2).strip()
            quantity = match.group(3).replace(",", "")
            unit = match.group(4)
            amount = match.group(5).replace(",", "")

            try:
                cost_val = Decimal(amount)
            except InvalidOperation:
                continue

            if cost_val <= Decimal("0"):
                continue

            detail_desc = f"{desc_text}: {quantity} {unit} at ${rate}/{unit.rstrip('s')} = ${amount}"

            if current_region_entry is not None:
                current_region_entry["details"].append({
                    "description": detail_desc,
                    "cost": cost_val,
                })
            elif current_service in breakdown:
                # Detail without a region header — add to a "General" region
                general_entry = None
                for entry in breakdown[current_service]:
                    if entry["region"] == "General":
                        general_entry = entry
                        break
                if general_entry is None:
                    general_entry = {"region": "General", "cost": Decimal("0"), "details": []}
                    breakdown[current_service].append(general_entry)
                general_entry["details"].append({
                    "description": detail_desc,
                    "cost": cost_val,
                })

    return breakdown


def _extract_billing_console_details(
    text: str, line_items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract detailed pricing sub-line-items from a billing console PDF.

    Parses lines like:
        $0.097 per db.t3.medium Single-AZ instance hour ... 672 Hrs USD 65.18

    Matches each detail to its parent service and returns human-readable
    descriptions that Bedrock can use to explain charges.

    Args:
        text: Full extracted text from the PDF.
        line_items: Top-level service line items (used to identify parent services).

    Returns:
        List of detail dicts: {"service": parent, "cost": Decimal, "description": str}
    """
    details: List[Dict[str, Any]] = []

    # Find the "Charges by service" section
    charges_match = re.search(r"Charges by service\b", text)
    if not charges_match:
        return details

    charges_text = text[charges_match.end():]

    # Cut off at known boundaries
    for boundary in ["Charges by account", "Invoices\n", "Tax Invoices"]:
        idx = charges_text.find(boundary)
        if idx > 0:
            charges_text = charges_text[:idx]

    # Build set of known service names for matching
    service_names = [item["service"] for item in line_items]

    # Pattern: $rate per <description> <quantity> <unit> USD <amount>
    detail_pattern = re.compile(
        r"\$([\d,.]+)\s+per\s+(.+?)\s+([\d,.]+)\s+(Hrs?|GB|Requests?|Count|Queries|Keys?|Secrets?|Hrs:HrsUsage)\s+USD\s+([\d,.]+)",
        re.IGNORECASE,
    )

    # Track current service context by scanning lines
    current_service = ""
    for line in charges_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line is a service header (matches a known service)
        for svc in service_names:
            if stripped.startswith(svc) or svc in stripped:
                current_service = svc
                break

        # Try to match detail pricing lines
        for match in detail_pattern.finditer(stripped):
            rate = match.group(1).replace(",", "")
            desc_text = match.group(2).strip()
            quantity = match.group(3).replace(",", "")
            unit = match.group(4)
            amount = match.group(5).replace(",", "")

            try:
                cost_val = Decimal(amount)
            except InvalidOperation:
                continue

            if cost_val <= Decimal("0"):
                continue

            # Build human-readable description
            human_desc = f"{quantity} {unit} at ${rate}/{unit.rstrip('s')} = ${amount} ({desc_text})"

            parent = current_service if current_service else "Unknown"

            details.append({
                "service": parent,
                "cost": cost_val,
                "description": human_desc,
            })

    return details


def _extract_text_and_tables(pdf_bytes: bytes, text_only: bool = False) -> Dict[str, Any]:
    """
    Extract raw text and optionally table data from a PDF using pdfplumber.

    Args:
        pdf_bytes: Raw bytes of the PDF file.
        text_only: If True, skip expensive table extraction.

    Returns:
        Dict with 'text' (full extracted text) and 'tables' (list of tables, empty if text_only).

    Raises:
        ValueError: If the file is not a valid PDF or cannot be read.
    """
    # Markers that identify pages generated by our analysis report
    _REPORT_MARKERS = ("Slash My Bill", "Bill Analysis", "eshkolai.com Bill Analysis")

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

                if not text_only:
                    # Skip tables from our own analysis report pages to avoid
                    # double-counting when a user re-uploads an analyzed PDF
                    if any(marker in page_text[:200] for marker in _REPORT_MARKERS):
                        continue

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
    Deduplicates results to prevent double-counting from repeated sections
    (e.g., when a previously-generated report is appended to the original invoice).

    Args:
        text: Full extracted text from the PDF.
        tables: List of tables extracted from the PDF.

    Returns:
        List of line item dicts with 'service', 'cost', and 'description' keys.
    """
    items = _parse_line_items_from_tables(tables)
    if not items:
        items = _parse_line_items_from_text(text)

    # Deduplicate: same service + same cost = keep only first occurrence.
    # This prevents double-counting when a re-uploaded analyzed PDF contains
    # both the report pages and the original invoice with identical line items.
    seen_pairs: set = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        key = (item["service"], str(item["cost"]))
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped.append(item)

    return deduped


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
                    cleaned_svc = _clean_service_name(service_name)
                    # Skip summary/aggregate lines
                    if cleaned_svc.lower() in (
                        "aws service charges", "total", "net charges",
                        "charges", "vat", "tax", "total amount",
                    ) or cleaned_svc.lower().startswith("total"):
                        continue
                    # Build description from other columns
                    desc_parts = []
                    for i, cell in enumerate(row):
                        if i not in (cost_col, service_col) and cell and cell.strip():
                            desc_parts.append(cell.strip())
                    description = " - ".join(desc_parts) if desc_parts else cleaned_svc

                    items.append({
                        "service": cleaned_svc,
                        "cost": cost_val,
                        "description": _clean_service_name(description),
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
                cleaned = _clean_service_name(service_name)
                # Skip summary/aggregate lines
                if cleaned.lower() in (
                    "aws service charges", "total", "net charges",
                    "charges", "vat", "tax", "total amount",
                    "total vat", "total charges",
                ) or cleaned.lower().startswith("total"):
                    continue
                items.append({
                    "service": cleaned,
                    "cost": cost_val,
                    "description": cleaned,
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

    Stops before "Linked Account" sections to avoid double-counting services
    that appear in both the main Detail and Linked Account Detail sections.
    """
    # Truncate text before linked account sections to avoid double-counting
    truncated = text
    for marker in [
        "Linked Account Allocation",
        "Summary for Linked Account",
        "Detail for Linked Account",
        "Activity By Account",
    ]:
        idx = truncated.find(marker)
        if idx > 0:
            truncated = truncated[:idx]

    # Also strip any previously-generated analysis report pages
    # (in case user re-uploads an analyzed PDF)
    for report_marker in [
        "Slash My Bill Report",
        "Bill Analysis Report",
        "Service Analysis\n",
        "Generated by eshkolai.com",
    ]:
        idx = truncated.find(report_marker)
        if idx >= 0 and idx < 200:
            # Report text at the start — find where the original invoice begins
            # Look for the actual invoice content after the report pages
            invoice_start = truncated.find("Invoice Number")
            if invoice_start < 0:
                invoice_start = truncated.find("Tax Invoice")
            if invoice_start > idx:
                truncated = truncated[invoice_start:]

    # Summary lines that should not be treated as services
    summary_lines = {
        "aws service charges",
        "net charges",
        "charges",
        "total",
        "vat",
        "tax",
        "invoice summary",
        "total amount",
        "total vat",
        "total charges",
    }

    items: List[Dict[str, Any]] = []
    # Pattern: service name followed by a cost
    line_pattern = re.compile(
        r"^(.*?(?:Amazon|AWS|Elastic|Cloud)\s*\S+.*?)\s+"
        r"\$?\s*([\d,]+\.\d{2})\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    for match in line_pattern.finditer(truncated):
        service_name = match.group(1).strip()
        cost_str = match.group(2).replace(",", "")
        cleaned = _clean_service_name(service_name)
        # Skip summary/aggregate lines
        if cleaned.lower() in summary_lines:
            continue
        # Skip lines that are just "Total" with a qualifier
        if cleaned.lower().startswith("total"):
            continue
        try:
            cost_val = Decimal(cost_str)
            if cost_val > Decimal("0"):
                items.append({
                    "service": cleaned,
                    "cost": cost_val,
                    "description": cleaned,
                })
        except InvalidOperation:
            continue

    # Deduplicate: if the same service appears multiple times with the same cost,
    # keep only the first occurrence (prevents double-counting from repeated sections)
    seen_pairs: set = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        key = (item["service"], str(item["cost"]))
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped.append(item)
    items = deduped

    # Fallback: look for any line with a dollar amount preceded by text
    if not items:
        fallback_pattern = re.compile(
            r"^(.{3,}?)\s+\$\s*([\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for match in fallback_pattern.finditer(truncated):
            service_name = match.group(1).strip()
            cost_str = match.group(2).replace(",", "")
            cleaned = _clean_service_name(service_name)
            if cleaned.lower() in summary_lines:
                continue
            try:
                cost_val = Decimal(cost_str)
                if cost_val > Decimal("0"):
                    items.append({
                        "service": cleaned,
                        "cost": cost_val,
                        "description": cleaned,
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


def _extract_tax_amount(text: str) -> Decimal | None:
    """
    Extract total tax/VAT amount from the bill text.

    Looks for patterns like:
        "Total tax USD 132.81"
        "VAT 17% USD 132.81"
        "Tax USD 132.81"
    """
    # Try "Total tax USD amount" pattern (billing console format)
    tax_match = re.search(
        r"Total\s+tax\s+(?:USD\s+)?([\d,]+\.\d{2})",
        text, re.IGNORECASE,
    )
    if tax_match:
        try:
            return Decimal(tax_match.group(1).replace(",", ""))
        except Exception:
            pass

    # Try "VAT nn% USD amount" pattern (EMEA invoice format)
    vat_match = re.search(
        r"VAT\s+\d+%?\s+(?:USD\s+)?([\d,]+\.\d{2})",
        text, re.IGNORECASE,
    )
    if vat_match:
        try:
            return Decimal(vat_match.group(1).replace(",", ""))
        except Exception:
            pass

    # Try "Total VAT USD amount"
    total_vat_match = re.search(
        r"Total\s+VAT\s+(?:USD\s+)?([\d,]+\.\d{2})",
        text, re.IGNORECASE,
    )
    if total_vat_match:
        try:
            return Decimal(total_vat_match.group(1).replace(",", ""))
        except Exception:
            pass

    return None


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
