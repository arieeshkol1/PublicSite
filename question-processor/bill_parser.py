"""
AWS Bill Analyzer - Bill Parser Module

This module provides parsers for AWS billing documents in CSV and PDF formats.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any
from datetime import datetime
import pdfplumber

class BillParser:
    """Base class for bill parsing"""
    
    def parse(self, file_content: bytes) -> Dict[str, Any]:
        """
        Parse bill file into structured data.
        
        Args:
            file_content: Raw file content as bytes
            
        Returns:
            Structured bill data dictionary
            
        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement parse()")


class CSVBillParser(BillParser):
    """Parser for AWS Cost and Usage Report CSV format"""
    
    # Column name mappings for different CSV formats
    COLUMN_MAPPINGS = {
        'service': ['lineItem/ProductCode', 'Service', 'ProductCode', 'product/ProductName'],
        'usage_type': ['lineItem/UsageType', 'Usage Type', 'UsageType'],
        'cost': ['lineItem/UnblendedCost', 'Cost', 'UnblendedCost', 'lineItem/BlendedCost'],
        'date': ['lineItem/UsageStartDate', 'Date', 'UsageStartDate', 'UsageDate'],
        'usage_amount': ['lineItem/UsageAmount', 'Usage Amount', 'UsageAmount']
    }
    
    def parse(self, file_content: bytes) -> Dict[str, Any]:
        """
        Parse CSV bill into structured data.
        
        Args:
            file_content: CSV file content as bytes
            
        Returns:
            {
                'line_items': [
                    {
                        'service': str,
                        'usage_type': str,
                        'cost': Decimal,
                        'date': str,
                        'usage_amount': float
                    }
                ],
                'total_cost': Decimal,
                'currency': str,
                'period_start': str,
                'period_end': str,
                'service_totals': {
                    'service_name': Decimal
                }
            }
        """
        try:
            # Decode bytes to string
            csv_text = file_content.decode('utf-8-sig')  # utf-8-sig handles BOM
            csv_file = io.StringIO(csv_text)
            
            # Read CSV
            reader = csv.DictReader(csv_file)
            
            # Get column mappings
            headers = reader.fieldnames
            if not headers:
                raise ValueError("CSV file has no headers")
            
            column_map = self._map_columns(headers)
            
            # Parse rows
            line_items = []
            service_totals = {}
            dates = []
            
            for row in reader:
                try:
                    # Extract fields using mapped column names
                    service = self._get_field(row, column_map.get('service', []))
                    usage_type = self._get_field(row, column_map.get('usage_type', []))
                    cost_str = self._get_field(row, column_map.get('cost', []))
                    date_str = self._get_field(row, column_map.get('date', []))
                    usage_amount_str = self._get_field(row, column_map.get('usage_amount', []))
                    
                    # Skip rows with no cost or invalid data
                    if not cost_str or not service:
                        continue
                    
                    # Parse cost with 2 decimal precision
                    try:
                        cost = Decimal(cost_str).quantize(Decimal('0.01'))
                    except (InvalidOperation, ValueError):
                        continue
                    
                    # Skip zero-cost items
                    if cost == 0:
                        continue
                    
                    # Parse usage amount
                    usage_amount = 0.0
                    if usage_amount_str:
                        try:
                            usage_amount = float(usage_amount_str)
                        except ValueError:
                            pass
                    
                    # Parse date
                    if date_str:
                        dates.append(date_str)
                    
                    # Add line item
                    line_items.append({
                        'service': service,
                        'usage_type': usage_type or 'N/A',
                        'cost': cost,
                        'date': date_str or 'N/A',
                        'usage_amount': usage_amount
                    })
                    
                    # Aggregate service totals
                    if service in service_totals:
                        service_totals[service] += cost
                    else:
                        service_totals[service] = cost
                        
                except Exception as e:
                    # Skip malformed rows
                    print(f"Skipping malformed row: {e}")
                    continue
            
            if not line_items:
                raise ValueError("No valid line items found in CSV file")
            
            # Calculate total cost
            total_cost = sum(item['cost'] for item in line_items)
            
            # Determine period start and end
            period_start, period_end = self._determine_period(dates)
            
            return {
                'line_items': line_items,
                'total_cost': total_cost,
                'currency': 'USD',  # AWS bills are typically in USD
                'period_start': period_start,
                'period_end': period_end,
                'service_totals': {k: v for k, v in service_totals.items()}
            }
            
        except UnicodeDecodeError:
            raise ValueError("CSV file encoding is not supported. Please ensure the file is UTF-8 encoded.")
        except csv.Error as e:
            raise ValueError(f"CSV file is malformed: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")
    
    def _map_columns(self, headers: List[str]) -> Dict[str, List[str]]:
        """
        Map CSV headers to standard field names.
        
        Args:
            headers: List of column headers from CSV
            
        Returns:
            Dictionary mapping field names to possible column names
        """
        column_map = {}
        
        for field, possible_names in self.COLUMN_MAPPINGS.items():
            for header in headers:
                if header in possible_names:
                    column_map[field] = [header]
                    break
            else:
                # If no exact match, try case-insensitive partial match
                for header in headers:
                    for possible_name in possible_names:
                        if possible_name.lower() in header.lower():
                            column_map[field] = [header]
                            break
                    if field in column_map:
                        break
        
        return column_map
    
    def _get_field(self, row: Dict[str, str], column_names: List[str]) -> str:
        """
        Get field value from row using possible column names.
        
        Args:
            row: CSV row as dictionary
            column_names: List of possible column names
            
        Returns:
            Field value or empty string
        """
        for col_name in column_names:
            if col_name in row and row[col_name]:
                return row[col_name].strip()
        return ''
    
    def _determine_period(self, dates: List[str]) -> tuple:
        """
        Determine billing period from dates.
        
        Args:
            dates: List of date strings
            
        Returns:
            Tuple of (period_start, period_end) as ISO 8601 strings
        """
        if not dates:
            return 'N/A', 'N/A'
        
        try:
            # Try to parse dates
            parsed_dates = []
            for date_str in dates:
                try:
                    # Try common date formats
                    for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d']:
                        try:
                            dt = datetime.strptime(date_str[:10], fmt[:10])
                            parsed_dates.append(dt)
                            break
                        except ValueError:
                            continue
                except:
                    continue
            
            if parsed_dates:
                period_start = min(parsed_dates).strftime('%Y-%m-%d')
                period_end = max(parsed_dates).strftime('%Y-%m-%d')
                return period_start, period_end
        except:
            pass
        
        return dates[0] if dates else 'N/A', dates[-1] if dates else 'N/A'


class PDFBillParser(BillParser):
    """Parser for AWS PDF bills"""
    
    # Regex patterns for extracting data
    SERVICE_PATTERNS = [
        r'Amazon\s+\w+',
        r'AWS\s+\w+',
        r'Amazon\s+\w+\s+\w+',
    ]
    
    COST_PATTERNS = [
        r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'USD\s+(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD',
    ]
    
    DATE_PATTERNS = [
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}',
    ]
    
    TOTAL_KEYWORDS = ['Total', 'Amount Due', 'Total Cost', 'Total Charges', 'Balance Due']
    
    def parse(self, file_content: bytes) -> Dict[str, Any]:
        """
        Parse PDF bill into structured data.
        
        Args:
            file_content: PDF file content as bytes
            
        Returns:
            Same structure as CSVBillParser
        """
        try:
            # Extract text from PDF
            text = self._extract_text_from_pdf(file_content)
            
            if not text or len(text.strip()) < 10:
                raise ValueError("PDF file appears to be empty or contains no extractable text")
            
            # Extract structured data
            services = self._extract_services(text)
            costs = self._extract_costs(text)
            dates = self._extract_dates(text)
            total_cost = self._extract_total_cost(text, costs)
            
            # Build line items
            line_items = []
            service_totals = {}
            
            # Match services with costs
            for i, service in enumerate(services):
                if i < len(costs):
                    cost = costs[i]
                    line_items.append({
                        'service': service,
                        'usage_type': 'N/A',
                        'cost': cost,
                        'date': dates[0] if dates else 'N/A',
                        'usage_amount': 0.0
                    })
                    
                    if service in service_totals:
                        service_totals[service] += cost
                    else:
                        service_totals[service] = cost
            
            # If no line items found, create a summary item
            if not line_items and total_cost:
                line_items.append({
                    'service': 'AWS Services',
                    'usage_type': 'N/A',
                    'cost': total_cost,
                    'date': dates[0] if dates else 'N/A',
                    'usage_amount': 0.0
                })
                service_totals['AWS Services'] = total_cost
            
            if not line_items:
                raise ValueError("Could not extract billing information from PDF")
            
            # Determine period
            period_start, period_end = self._determine_period_from_dates(dates)
            
            return {
                'line_items': line_items,
                'total_cost': total_cost or sum(item['cost'] for item in line_items),
                'currency': 'USD',
                'period_start': period_start,
                'period_end': period_end,
                'service_totals': service_totals,
                'raw_text': text[:1000]  # Include first 1000 chars for AI context
            }
            
        except Exception as e:
            raise ValueError(f"Failed to parse PDF file: {str(e)}")
    
    def _extract_text_from_pdf(self, file_content: bytes) -> str:
        """
        Extract text from all pages of PDF.
        
        Args:
            file_content: PDF file content as bytes
            
        Returns:
            Extracted text
        """
        try:
            text_parts = []
            
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            
            return '\n'.join(text_parts)
            
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    def _extract_services(self, text: str) -> List[str]:
        """Extract AWS service names from text."""
        services = []
        
        for pattern in self.SERVICE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            services.extend(matches)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_services = []
        for service in services:
            service_clean = service.strip()
            if service_clean and service_clean not in seen:
                seen.add(service_clean)
                unique_services.append(service_clean)
        
        return unique_services[:20]  # Limit to 20 services
    
    def _extract_costs(self, text: str) -> List[Decimal]:
        """Extract cost values from text."""
        costs = []
        
        for pattern in self.COST_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # Remove commas and convert to Decimal
                    cost_str = match.replace(',', '')
                    cost = Decimal(cost_str).quantize(Decimal('0.01'))
                    if cost > 0:
                        costs.append(cost)
                except:
                    continue
        
        return costs
    
    def _extract_dates(self, text: str) -> List[str]:
        """Extract dates from text."""
        dates = []
        
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, text)
            dates.extend(matches)
        
        return dates[:10]  # Limit to 10 dates
    
    def _extract_total_cost(self, text: str, costs: List[Decimal]) -> Decimal:
        """Extract total cost from text."""
        # Look for total keywords followed by cost
        for keyword in self.TOTAL_KEYWORDS:
            pattern = rf'{keyword}\s*:?\s*\$?\s*(\d+(?:,\d{{3}})*(?:\.\d{{2}})?)'
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    cost_str = matches[0].replace(',', '')
                    return Decimal(cost_str).quantize(Decimal('0.01'))
                except:
                    continue
        
        # If no total found, return the largest cost
        return max(costs) if costs else Decimal('0.00')
    
    def _determine_period_from_dates(self, dates: List[str]) -> tuple:
        """Determine billing period from extracted dates."""
        if not dates:
            return 'N/A', 'N/A'
        
        # Return first and last date as period
        return dates[0], dates[-1] if len(dates) > 1 else dates[0]


def get_parser(file_extension: str) -> BillParser:
    """
    Factory function to get appropriate parser based on file extension.
    
    Args:
        file_extension: File extension (e.g., '.csv', '.pdf')
        
    Returns:
        Appropriate BillParser instance
        
    Raises:
        ValueError: If file extension is not supported
    """
    file_extension = file_extension.lower()
    
    if file_extension == '.csv':
        return CSVBillParser()
    elif file_extension == '.pdf':
        return PDFBillParser()
    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")
