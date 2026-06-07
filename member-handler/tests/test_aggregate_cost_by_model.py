"""Unit tests for aggregate_cost_by_model() function.

Tests cover:
- Basic grouping by model name
- Sorting by cost descending
- Top 20 model limit
- Percentage calculation
- Formatting: costs to 2 decimal places, percentages to 1 decimal place
- Edge cases: empty input, single model, zero cost records
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cost_normalizer import aggregate_cost_by_model


class TestAggregateCostByModel:
    """Tests for aggregate_cost_by_model()."""

    def test_basic_grouping(self):
        """Records with the same model are grouped together."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 5.00},
            {'service_name': 'gpt-4', 'cost_amount': 3.20},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 1.50},
        ]
        result = aggregate_cost_by_model(records)

        assert len(result) == 2
        assert result[0]['model'] == 'gpt-4'
        assert result[0]['cost'] == 8.20
        assert result[1]['model'] == 'gpt-3.5-turbo'
        assert result[1]['cost'] == 1.50

    def test_sorted_by_cost_descending(self):
        """Results are sorted by cost descending."""
        records = [
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 1.00},
            {'service_name': 'gpt-4', 'cost_amount': 10.00},
            {'service_name': 'gpt-4o-mini', 'cost_amount': 5.00},
        ]
        result = aggregate_cost_by_model(records)

        assert result[0]['model'] == 'gpt-4'
        assert result[1]['model'] == 'gpt-4o-mini'
        assert result[2]['model'] == 'gpt-3.5-turbo'

    def test_top_20_limit(self):
        """Only top 20 models by cost are returned."""
        records = [
            {'service_name': f'model-{i:02d}', 'cost_amount': float(i)}
            for i in range(1, 26)  # 25 models
        ]
        result = aggregate_cost_by_model(records)

        assert len(result) == 20
        # Top model should be model-25 (cost=25.0)
        assert result[0]['model'] == 'model-25'

    def test_percentage_calculation(self):
        """Percentages are correctly calculated as cost/total * 100."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 75.00},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 25.00},
        ]
        result = aggregate_cost_by_model(records)

        assert result[0]['percentage'] == 75.0
        assert result[1]['percentage'] == 25.0

    def test_percentages_sum_approximately_100(self):
        """Percentages of all returned models sum close to 100% when all models fit in top 20."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 8.20},
            {'service_name': 'gpt-4o-mini', 'cost_amount': 2.15},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 1.50},
            {'service_name': 'dall-e-3', 'cost_amount': 0.60},
        ]
        result = aggregate_cost_by_model(records)

        total_pct = sum(r['percentage'] for r in result)
        # Within floating-point tolerance (rounding can cause small deviation)
        assert abs(total_pct - 100.0) < 1.0

    def test_cost_formatted_2_decimal_places(self):
        """Costs are rounded to 2 decimal places."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 1.23456},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 2.789},
        ]
        result = aggregate_cost_by_model(records)

        assert result[0]['cost'] == 2.79
        assert result[1]['cost'] == 1.23

    def test_percentage_formatted_1_decimal_place(self):
        """Percentages are rounded to 1 decimal place."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 1.0},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 2.0},
        ]
        result = aggregate_cost_by_model(records)

        # gpt-3.5-turbo: 2/3 * 100 = 66.666... -> 66.7
        # gpt-4: 1/3 * 100 = 33.333... -> 33.3
        assert result[0]['percentage'] == 66.7
        assert result[1]['percentage'] == 33.3

    def test_empty_input(self):
        """Empty input returns empty list."""
        result = aggregate_cost_by_model([])
        assert result == []

    def test_single_model(self):
        """Single model gets 100% of spend."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 10.00},
        ]
        result = aggregate_cost_by_model(records)

        assert len(result) == 1
        assert result[0]['model'] == 'gpt-4'
        assert result[0]['cost'] == 10.00
        assert result[0]['percentage'] == 100.0

    def test_all_zero_costs(self):
        """All zero cost records produce 0% for each model."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 0.0},
            {'service_name': 'gpt-3.5-turbo', 'cost_amount': 0.0},
        ]
        result = aggregate_cost_by_model(records)

        assert len(result) == 2
        for r in result:
            assert r['cost'] == 0.0
            assert r['percentage'] == 0.0

    def test_output_structure(self):
        """Each result dict has exactly model, cost, and percentage keys."""
        records = [
            {'service_name': 'gpt-4', 'cost_amount': 5.00},
        ]
        result = aggregate_cost_by_model(records)

        assert set(result[0].keys()) == {'model', 'cost', 'percentage'}

    def test_with_full_normalized_records(self):
        """Works correctly with full normalized records (extra fields ignored)."""
        records = [
            {
                'date': '2024-01-01',
                'service_name': 'gpt-4',
                'cost_amount': 8.20,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-abc123',
                'input_tokens': 150000,
                'output_tokens': 45000,
            },
            {
                'date': '2024-01-01',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 2.15,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-abc123',
                'input_tokens': 500000,
                'output_tokens': 120000,
            },
            {
                'date': '2024-01-02',
                'service_name': 'gpt-4',
                'cost_amount': 7.10,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-abc123',
                'input_tokens': 130000,
                'output_tokens': 40000,
            },
        ]
        result = aggregate_cost_by_model(records)

        assert len(result) == 2
        assert result[0]['model'] == 'gpt-4'
        assert result[0]['cost'] == 15.30  # 8.20 + 7.10
        assert result[1]['model'] == 'gpt-4o-mini'
        assert result[1]['cost'] == 2.15
