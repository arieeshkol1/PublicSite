"""Unit tests for invoice sorting and pagination logic (tasks 5.2 and 5.3)."""

import math
import sys
import os
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the functions - we need to mock heavy deps first
with patch.dict('sys.modules', {
    'boto3': MagicMock(),
    'botocore': MagicMock(),
    'botocore.exceptions': MagicMock(),
    'jwt': MagicMock(),
    'bcrypt': MagicMock(),
    'yaml': MagicMock(),
}):
    os.environ.setdefault('JWT_SECRET', 'test-secret')
    from lambda_function import _sort_invoice_items, _paginate_items


def _make_item(service='Amazon EC2', cost=10.50, month='2024-01', region='us-east-1'):
    """Helper to create a mock invoice item."""
    return {
        'pk': 'test@example.com#123456789012',
        'sk': f'{month}#{service}',
        'memberEmail': 'test@example.com',
        'accountId': '123456789012',
        'month': month,
        'service': service,
        'cost': Decimal(str(cost)),
        'currency': 'USD',
        'usageTypes': [],
        'dailyCosts': {},
        'region': region,
    }


# ============================================================
# Tests for _sort_invoice_items
# ============================================================

class TestSortInvoiceItems:
    """Tests for _sort_invoice_items function."""

    def test_sort_by_cost_desc(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=20.00),
            _make_item(cost=10.00),
        ]
        result = _sort_invoice_items(items, 'cost', 'desc')
        costs = [float(item['cost']) for item in result]
        assert costs == [20.00, 10.00, 5.00]

    def test_sort_by_cost_asc(self):
        items = [
            _make_item(cost=20.00),
            _make_item(cost=5.00),
            _make_item(cost=10.00),
        ]
        result = _sort_invoice_items(items, 'cost', 'asc')
        costs = [float(item['cost']) for item in result]
        assert costs == [5.00, 10.00, 20.00]

    def test_sort_by_service_asc(self):
        items = [
            _make_item(service='AWS Lambda'),
            _make_item(service='Amazon EC2'),
            _make_item(service='Amazon S3'),
        ]
        result = _sort_invoice_items(items, 'service', 'asc')
        services = [item['service'] for item in result]
        assert services == ['Amazon EC2', 'Amazon S3', 'AWS Lambda']

    def test_sort_by_service_desc(self):
        items = [
            _make_item(service='Amazon EC2'),
            _make_item(service='AWS Lambda'),
            _make_item(service='Amazon S3'),
        ]
        result = _sort_invoice_items(items, 'service', 'desc')
        services = [item['service'] for item in result]
        assert services == ['AWS Lambda', 'Amazon S3', 'Amazon EC2']

    def test_sort_by_service_case_insensitive(self):
        items = [
            _make_item(service='amazon ec2', cost=5.00),
            _make_item(service='Amazon EC2', cost=10.00),
            _make_item(service='AWS Lambda', cost=3.00),
        ]
        result = _sort_invoice_items(items, 'service', 'asc')
        # Both 'amazon ec2' and 'Amazon EC2' should be grouped together
        # Secondary sort by cost desc means 10.00 comes before 5.00
        assert result[0]['service'] == 'Amazon EC2'
        assert float(result[0]['cost']) == 10.00
        assert result[1]['service'] == 'amazon ec2'
        assert float(result[1]['cost']) == 5.00

    def test_sort_by_date_desc(self):
        items = [
            _make_item(month='2024-01'),
            _make_item(month='2024-03'),
            _make_item(month='2024-02'),
        ]
        result = _sort_invoice_items(items, 'date', 'desc')
        months = [item['month'] for item in result]
        assert months == ['2024-03', '2024-02', '2024-01']

    def test_sort_by_date_asc(self):
        items = [
            _make_item(month='2024-03'),
            _make_item(month='2024-01'),
            _make_item(month='2024-02'),
        ]
        result = _sort_invoice_items(items, 'date', 'asc')
        months = [item['month'] for item in result]
        assert months == ['2024-01', '2024-02', '2024-03']

    def test_default_sort_cost_desc_when_sort_by_none(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=20.00),
            _make_item(cost=10.00),
        ]
        result = _sort_invoice_items(items, None, None)
        costs = [float(item['cost']) for item in result]
        assert costs == [20.00, 10.00, 5.00]

    def test_secondary_sort_by_cost_desc_for_equal_service(self):
        items = [
            _make_item(service='Amazon EC2', cost=5.00),
            _make_item(service='Amazon EC2', cost=20.00),
            _make_item(service='Amazon EC2', cost=10.00),
        ]
        result = _sort_invoice_items(items, 'service', 'asc')
        costs = [float(item['cost']) for item in result]
        # All same service, secondary sort by cost desc
        assert costs == [20.00, 10.00, 5.00]

    def test_secondary_sort_by_cost_desc_for_equal_date(self):
        items = [
            _make_item(month='2024-01', cost=5.00),
            _make_item(month='2024-01', cost=20.00),
            _make_item(month='2024-01', cost=10.00),
        ]
        result = _sort_invoice_items(items, 'date', 'desc')
        costs = [float(item['cost']) for item in result]
        # All same month, secondary sort by cost desc
        assert costs == [20.00, 10.00, 5.00]

    def test_empty_list_returns_empty(self):
        result = _sort_invoice_items([], 'cost', 'desc')
        assert result == []

    def test_single_item_returns_same(self):
        items = [_make_item(cost=42.00)]
        result = _sort_invoice_items(items, 'cost', 'desc')
        assert len(result) == 1
        assert float(result[0]['cost']) == 42.00

    def test_sort_does_not_mutate_original(self):
        items = [
            _make_item(cost=5.00),
            _make_item(cost=20.00),
            _make_item(cost=10.00),
        ]
        original_order = [float(item['cost']) for item in items]
        _sort_invoice_items(items, 'cost', 'desc')
        current_order = [float(item['cost']) for item in items]
        assert current_order == original_order


# ============================================================
# Tests for _paginate_items
# ============================================================

class TestPaginateItems:
    """Tests for _paginate_items function."""

    def test_first_page_default(self):
        items = [_make_item(cost=i) for i in range(100)]
        page_items, meta = _paginate_items(items, page=1, page_size=50)
        assert len(page_items) == 50
        assert meta['page'] == 1
        assert meta['pageSize'] == 50
        assert meta['totalItems'] == 100
        assert meta['totalPages'] == 2

    def test_second_page(self):
        items = [_make_item(cost=i) for i in range(100)]
        page_items, meta = _paginate_items(items, page=2, page_size=50)
        assert len(page_items) == 50
        assert meta['page'] == 2

    def test_last_page_partial(self):
        items = [_make_item(cost=i) for i in range(75)]
        page_items, meta = _paginate_items(items, page=2, page_size=50)
        assert len(page_items) == 25
        assert meta['totalItems'] == 75
        assert meta['totalPages'] == 2

    def test_page_exceeds_total_pages_returns_empty(self):
        items = [_make_item(cost=i) for i in range(10)]
        page_items, meta = _paginate_items(items, page=5, page_size=50)
        assert page_items == []
        assert meta['page'] == 5
        assert meta['pageSize'] == 50
        assert meta['totalItems'] == 10
        assert meta['totalPages'] == 1

    def test_empty_items_returns_empty(self):
        page_items, meta = _paginate_items([], page=1, page_size=50)
        assert page_items == []
        assert meta['totalItems'] == 0
        assert meta['totalPages'] == 0

    def test_page_size_1(self):
        items = [_make_item(cost=i) for i in range(5)]
        page_items, meta = _paginate_items(items, page=3, page_size=1)
        assert len(page_items) == 1
        assert meta['totalPages'] == 5

    def test_page_size_200(self):
        items = [_make_item(cost=i) for i in range(150)]
        page_items, meta = _paginate_items(items, page=1, page_size=200)
        assert len(page_items) == 150
        assert meta['totalPages'] == 1

    def test_exact_page_boundary(self):
        items = [_make_item(cost=i) for i in range(100)]
        page_items, meta = _paginate_items(items, page=2, page_size=50)
        assert len(page_items) == 50
        assert meta['totalPages'] == 2

    def test_all_pages_cover_all_items(self):
        """Verify that iterating all pages returns exactly totalItems items."""
        items = [_make_item(cost=i, service=f'Service-{i}') for i in range(123)]
        page_size = 50
        total_pages = math.ceil(123 / page_size)

        all_collected = []
        for p in range(1, total_pages + 1):
            page_items, meta = _paginate_items(items, page=p, page_size=page_size)
            all_collected.extend(page_items)

        assert len(all_collected) == 123
        # No duplicates
        assert len(all_collected) == len(set(id(item) for item in all_collected))

    def test_pagination_metadata_correct_for_single_item(self):
        items = [_make_item(cost=42.00)]
        page_items, meta = _paginate_items(items, page=1, page_size=50)
        assert len(page_items) == 1
        assert meta['totalItems'] == 1
        assert meta['totalPages'] == 1

    def test_page_1_with_zero_items(self):
        page_items, meta = _paginate_items([], page=1, page_size=50)
        assert page_items == []
        assert meta['page'] == 1
        assert meta['totalItems'] == 0
        assert meta['totalPages'] == 0
