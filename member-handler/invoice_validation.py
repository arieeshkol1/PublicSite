"""
Invoice Explorer — Input validation module.

Validates query parameters for invoice API endpoints and returns
structured 400 error responses for invalid inputs.
"""

import re
from datetime import datetime, timezone


# Pre-compiled patterns
_MONTH_PATTERN = re.compile(r'^\d{4}-\d{2}$')
_ACCOUNT_ID_PATTERN = re.compile(r'^\d{12}$')

# Valid enum values
VALID_SORT_BY = ('cost', 'service', 'date')
VALID_SORT_ORDER = ('asc', 'desc')

# Defaults
DEFAULT_PAGE_SIZE = 50
DEFAULT_PAGE = 1


def validate_month(month_str):
    """Validate month parameter format YYYY-MM.

    Accepts months where:
    - Format is exactly YYYY-MM
    - Year is between 2015 and the current year (inclusive)
    - Month is between 01 and 12

    Returns:
        None if valid, or an error dict with statusCode/body if invalid.
    """
    if month_str is None:
        return None  # Month is optional

    if not isinstance(month_str, str) or not _MONTH_PATTERN.match(month_str):
        return _validation_error('Month must be in YYYY-MM format')

    year_str, month_part = month_str.split('-')
    year = int(year_str)
    month = int(month_part)

    current_year = datetime.now(timezone.utc).year

    if year < 2015 or year > current_year:
        return _validation_error('Month must be in YYYY-MM format')

    if month < 1 or month > 12:
        return _validation_error('Month must be in YYYY-MM format')

    return None


def validate_account_id(account_id):
    """Validate accountId parameter (exactly 12 digits).

    Returns:
        None if valid, or an error dict with statusCode/body if invalid.
    """
    if account_id is None:
        return _validation_error('accountId is required')

    if not isinstance(account_id, str) or not _ACCOUNT_ID_PATTERN.match(account_id):
        return _validation_error('Account ID must be a 12-digit number')

    return None


def validate_page_size(page_size_raw):
    """Validate and parse pageSize parameter.

    Must be an integer between 1 and 200 inclusive.
    Defaults to 50 if not provided.

    Returns:
        (int, None) if valid — the parsed pageSize value.
        (None, error_dict) if invalid.
    """
    if page_size_raw is None or page_size_raw == '':
        return DEFAULT_PAGE_SIZE, None

    try:
        page_size = int(page_size_raw)
    except (ValueError, TypeError):
        return None, _validation_error(
            'pageSize must be an integer between 1 and 200'
        )

    if page_size < 1 or page_size > 200:
        return None, _validation_error(
            'pageSize must be an integer between 1 and 200'
        )

    return page_size, None


def validate_page(page_raw):
    """Validate and parse page parameter.

    Must be an integer greater than or equal to 1.
    Defaults to 1 if not provided.

    Returns:
        (int, None) if valid — the parsed page value.
        (None, error_dict) if invalid.
    """
    if page_raw is None or page_raw == '':
        return DEFAULT_PAGE, None

    try:
        page = int(page_raw)
    except (ValueError, TypeError):
        return None, _validation_error(
            'page must be an integer greater than or equal to 1'
        )

    if page < 1:
        return None, _validation_error(
            'page must be an integer greater than or equal to 1'
        )

    return page, None


def validate_sort_by(sort_by):
    """Validate sortBy parameter.

    Must be one of: cost, service, date.
    Defaults to 'cost' if not provided.

    Returns:
        (str, None) if valid — the validated sortBy value.
        (None, error_dict) if invalid.
    """
    if sort_by is None or sort_by == '':
        return 'cost', None

    if sort_by not in VALID_SORT_BY:
        return None, _validation_error(
            'sortBy must be one of: cost, service, date'
        )

    return sort_by, None


def validate_sort_order(sort_order):
    """Validate sortOrder parameter.

    Must be one of: asc, desc.
    Defaults to 'desc' if not provided.

    Returns:
        (str, None) if valid — the validated sortOrder value.
        (None, error_dict) if invalid.
    """
    if sort_order is None or sort_order == '':
        return 'desc', None

    if sort_order not in VALID_SORT_ORDER:
        return None, _validation_error(
            'sortOrder must be one of: asc, desc'
        )

    return sort_order, None


def validate_invoice_query_params(params):
    """Validate all query parameters for the invoice list endpoint.

    Args:
        params: dict of query string parameters from the API request.

    Returns:
        (validated_params, None) if all valid — a dict with parsed/defaulted values.
        (None, error_response) if any parameter is invalid.
    """
    # accountId is required
    account_id = params.get('accountId')
    error = validate_account_id(account_id)
    if error:
        return None, error

    # month is optional
    month = params.get('month')
    if month is not None and month != '':
        error = validate_month(month)
        if error:
            return None, error
    else:
        month = None

    # pageSize
    page_size, error = validate_page_size(params.get('pageSize'))
    if error:
        return None, error

    # page
    page, error = validate_page(params.get('page'))
    if error:
        return None, error

    # sortBy
    sort_by, error = validate_sort_by(params.get('sortBy'))
    if error:
        return None, error

    # sortOrder
    sort_order, error = validate_sort_order(params.get('sortOrder'))
    if error:
        return None, error

    validated = {
        'accountId': account_id,
        'month': month,
        'service': params.get('service') or None,
        'minCost': params.get('minCost') or None,
        'maxCost': params.get('maxCost') or None,
        'search': params.get('search') or None,
        'page': page,
        'pageSize': page_size,
        'sortBy': sort_by,
        'sortOrder': sort_order,
    }

    return validated, None


def _validation_error(message):
    """Create a 400 validation error response matching the Lambda response format."""
    import json
    return {
        'statusCode': 400,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        },
        'body': json.dumps({
            'error': 'ValidationError',
            'message': message,
            'code': 400,
        }),
    }
