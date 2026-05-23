"""Unit tests for invoice_validation module."""

import json
import sys
import os
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_validation import (
    validate_month,
    validate_account_id,
    validate_page_size,
    validate_page,
    validate_sort_by,
    validate_sort_order,
    validate_invoice_query_params,
)


class TestValidateMonth:
    """Tests for month format validation."""

    def test_valid_month_current_year(self):
        current_year = datetime.now(timezone.utc).year
        assert validate_month(f'{current_year}-01') is None

    def test_valid_month_2015(self):
        assert validate_month('2015-01') is None

    def test_valid_month_december(self):
        assert validate_month('2023-12') is None

    def test_valid_month_june(self):
        assert validate_month('2020-06') is None

    def test_none_month_is_optional(self):
        assert validate_month(None) is None

    def test_invalid_format_no_dash(self):
        error = validate_month('202301')
        assert error is not None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert body['message'] == 'Month must be in YYYY-MM format'

    def test_invalid_format_extra_chars(self):
        error = validate_month('2023-01-01')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_year_before_2015(self):
        error = validate_month('2014-06')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_year_far_future(self):
        error = validate_month('2099-06')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_month_00(self):
        error = validate_month('2023-00')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_month_13(self):
        error = validate_month('2023-13')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_non_numeric(self):
        error = validate_month('abcd-ef')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_empty_string(self):
        error = validate_month('')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_type_integer(self):
        error = validate_month(202301)
        assert error is not None
        assert error['statusCode'] == 400


class TestValidateAccountId:
    """Tests for accountId validation."""

    def test_valid_12_digits(self):
        assert validate_account_id('123456789012') is None

    def test_valid_all_zeros(self):
        assert validate_account_id('000000000000') is None

    def test_invalid_none(self):
        error = validate_account_id(None)
        assert error is not None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert 'accountId is required' in body['message']

    def test_invalid_11_digits(self):
        error = validate_account_id('12345678901')
        assert error is not None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert '12-digit' in body['message']

    def test_invalid_13_digits(self):
        error = validate_account_id('1234567890123')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_with_letters(self):
        error = validate_account_id('12345678901a')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_with_dashes(self):
        error = validate_account_id('1234-5678-9012')
        assert error is not None
        assert error['statusCode'] == 400

    def test_invalid_empty_string(self):
        error = validate_account_id('')
        assert error is not None
        assert error['statusCode'] == 400


class TestValidatePageSize:
    """Tests for pageSize validation."""

    def test_valid_50(self):
        value, error = validate_page_size('50')
        assert error is None
        assert value == 50

    def test_valid_1(self):
        value, error = validate_page_size('1')
        assert error is None
        assert value == 1

    def test_valid_200(self):
        value, error = validate_page_size('200')
        assert error is None
        assert value == 200

    def test_default_when_none(self):
        value, error = validate_page_size(None)
        assert error is None
        assert value == 50

    def test_default_when_empty(self):
        value, error = validate_page_size('')
        assert error is None
        assert value == 50

    def test_invalid_zero(self):
        value, error = validate_page_size('0')
        assert value is None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert 'pageSize' in body['message']

    def test_invalid_201(self):
        value, error = validate_page_size('201')
        assert value is None
        assert error['statusCode'] == 400

    def test_invalid_negative(self):
        value, error = validate_page_size('-1')
        assert value is None
        assert error['statusCode'] == 400

    def test_invalid_non_integer(self):
        value, error = validate_page_size('abc')
        assert value is None
        assert error['statusCode'] == 400

    def test_invalid_float(self):
        value, error = validate_page_size('50.5')
        assert value is None
        assert error['statusCode'] == 400


class TestValidatePage:
    """Tests for page validation."""

    def test_valid_1(self):
        value, error = validate_page('1')
        assert error is None
        assert value == 1

    def test_valid_100(self):
        value, error = validate_page('100')
        assert error is None
        assert value == 100

    def test_default_when_none(self):
        value, error = validate_page(None)
        assert error is None
        assert value == 1

    def test_default_when_empty(self):
        value, error = validate_page('')
        assert error is None
        assert value == 1

    def test_invalid_zero(self):
        value, error = validate_page('0')
        assert value is None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert 'page' in body['message']

    def test_invalid_negative(self):
        value, error = validate_page('-5')
        assert value is None
        assert error['statusCode'] == 400

    def test_invalid_non_integer(self):
        value, error = validate_page('xyz')
        assert value is None
        assert error['statusCode'] == 400


class TestValidateSortBy:
    """Tests for sortBy validation."""

    def test_valid_cost(self):
        value, error = validate_sort_by('cost')
        assert error is None
        assert value == 'cost'

    def test_valid_service(self):
        value, error = validate_sort_by('service')
        assert error is None
        assert value == 'service'

    def test_valid_date(self):
        value, error = validate_sort_by('date')
        assert error is None
        assert value == 'date'

    def test_default_when_none(self):
        value, error = validate_sort_by(None)
        assert error is None
        assert value == 'cost'

    def test_default_when_empty(self):
        value, error = validate_sort_by('')
        assert error is None
        assert value == 'cost'

    def test_invalid_value(self):
        value, error = validate_sort_by('name')
        assert value is None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert 'cost, service, date' in body['message']

    def test_invalid_uppercase(self):
        value, error = validate_sort_by('Cost')
        assert value is None
        assert error['statusCode'] == 400


class TestValidateSortOrder:
    """Tests for sortOrder validation."""

    def test_valid_asc(self):
        value, error = validate_sort_order('asc')
        assert error is None
        assert value == 'asc'

    def test_valid_desc(self):
        value, error = validate_sort_order('desc')
        assert error is None
        assert value == 'desc'

    def test_default_when_none(self):
        value, error = validate_sort_order(None)
        assert error is None
        assert value == 'desc'

    def test_default_when_empty(self):
        value, error = validate_sort_order('')
        assert error is None
        assert value == 'desc'

    def test_invalid_value(self):
        value, error = validate_sort_order('ascending')
        assert value is None
        assert error['statusCode'] == 400
        body = json.loads(error['body'])
        assert 'asc, desc' in body['message']

    def test_invalid_uppercase(self):
        value, error = validate_sort_order('ASC')
        assert value is None
        assert error['statusCode'] == 400


class TestValidateInvoiceQueryParams:
    """Tests for the combined query parameter validation."""

    def test_valid_minimal_params(self):
        params = {'accountId': '123456789012'}
        validated, error = validate_invoice_query_params(params)
        assert error is None
        assert validated['accountId'] == '123456789012'
        assert validated['month'] is None
        assert validated['page'] == 1
        assert validated['pageSize'] == 50
        assert validated['sortBy'] == 'cost'
        assert validated['sortOrder'] == 'desc'

    def test_valid_all_params(self):
        params = {
            'accountId': '123456789012',
            'month': '2023-06',
            'pageSize': '25',
            'page': '2',
            'sortBy': 'service',
            'sortOrder': 'asc',
            'service': 'Amazon EC2',
            'search': 'compute',
        }
        validated, error = validate_invoice_query_params(params)
        assert error is None
        assert validated['accountId'] == '123456789012'
        assert validated['month'] == '2023-06'
        assert validated['pageSize'] == 25
        assert validated['page'] == 2
        assert validated['sortBy'] == 'service'
        assert validated['sortOrder'] == 'asc'
        assert validated['service'] == 'Amazon EC2'
        assert validated['search'] == 'compute'

    def test_missing_account_id(self):
        params = {'month': '2023-06'}
        validated, error = validate_invoice_query_params(params)
        assert validated is None
        assert error['statusCode'] == 400

    def test_invalid_month_stops_early(self):
        params = {'accountId': '123456789012', 'month': 'bad'}
        validated, error = validate_invoice_query_params(params)
        assert validated is None
        assert error['statusCode'] == 400

    def test_invalid_page_size_stops_early(self):
        params = {'accountId': '123456789012', 'pageSize': '999'}
        validated, error = validate_invoice_query_params(params)
        assert validated is None
        assert error['statusCode'] == 400

    def test_invalid_sort_by_stops_early(self):
        params = {'accountId': '123456789012', 'sortBy': 'invalid'}
        validated, error = validate_invoice_query_params(params)
        assert validated is None
        assert error['statusCode'] == 400
