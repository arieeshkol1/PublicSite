"""Unit tests for aggregate_cost_by_project() function.

Tests cover:
- Basic grouping by project_id
- Sorting by cost descending
- Top 50 project limit (cap)
- Truncation indicator when >50 projects exist
- Percentage calculation
- Formatting: costs to 2 decimal places, percentages to 1 decimal place
- Edge cases: empty input, single project, records without project_id, all zero costs
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cost_normalizer import aggregate_cost_by_project


class TestAggregateCostByProject:
    """Tests for aggregate_cost_by_project()."""

    def test_basic_grouping(self):
        """Records with the same project_id are grouped together."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 5.00},
            {'project_id': 'proj_abc', 'cost_amount': 2.50},
            {'project_id': 'proj_def', 'cost_amount': 3.00},
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 2
        assert result['projects'][0]['project_id'] == 'proj_abc'
        assert result['projects'][0]['cost'] == 7.50
        assert result['projects'][1]['project_id'] == 'proj_def'
        assert result['projects'][1]['cost'] == 3.00

    def test_sorted_by_cost_descending(self):
        """Projects are sorted by cost descending."""
        records = [
            {'project_id': 'proj_low', 'cost_amount': 1.00},
            {'project_id': 'proj_high', 'cost_amount': 10.00},
            {'project_id': 'proj_mid', 'cost_amount': 5.00},
        ]
        result = aggregate_cost_by_project(records)

        assert result['projects'][0]['project_id'] == 'proj_high'
        assert result['projects'][1]['project_id'] == 'proj_mid'
        assert result['projects'][2]['project_id'] == 'proj_low'

    def test_top_50_limit(self):
        """Only top 50 projects by cost are returned."""
        records = [
            {'project_id': f'proj_{i:03d}', 'cost_amount': float(i)}
            for i in range(1, 61)  # 60 projects
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 50
        # Top project should be proj_060 (cost=60.0)
        assert result['projects'][0]['project_id'] == 'proj_060'
        assert result['truncated'] is True
        assert result['total_projects'] == 60

    def test_not_truncated_when_50_or_fewer(self):
        """truncated is False when 50 or fewer projects exist."""
        records = [
            {'project_id': f'proj_{i:03d}', 'cost_amount': float(i)}
            for i in range(1, 51)  # exactly 50 projects
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 50
        assert result['truncated'] is False
        assert result['total_projects'] == 50

    def test_truncated_indicator_at_51_projects(self):
        """truncated is True when exactly 51 projects exist."""
        records = [
            {'project_id': f'proj_{i:03d}', 'cost_amount': float(i)}
            for i in range(1, 52)  # 51 projects
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 50
        assert result['truncated'] is True
        assert result['total_projects'] == 51

    def test_percentage_calculation(self):
        """Percentages are correctly calculated as cost/total * 100."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 75.00},
            {'project_id': 'proj_def', 'cost_amount': 25.00},
        ]
        result = aggregate_cost_by_project(records)

        assert result['projects'][0]['percentage'] == 75.0
        assert result['projects'][1]['percentage'] == 25.0

    def test_cost_formatted_2_decimal_places(self):
        """Costs are rounded to 2 decimal places."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 1.23456},
            {'project_id': 'proj_def', 'cost_amount': 2.789},
        ]
        result = aggregate_cost_by_project(records)

        assert result['projects'][0]['cost'] == 2.79
        assert result['projects'][1]['cost'] == 1.23

    def test_percentage_formatted_1_decimal_place(self):
        """Percentages are rounded to 1 decimal place."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 1.0},
            {'project_id': 'proj_def', 'cost_amount': 2.0},
        ]
        result = aggregate_cost_by_project(records)

        # proj_def: 2/3 * 100 = 66.666... -> 66.7
        # proj_abc: 1/3 * 100 = 33.333... -> 33.3
        assert result['projects'][0]['percentage'] == 66.7
        assert result['projects'][1]['percentage'] == 33.3

    def test_empty_input(self):
        """Empty input returns empty projects list."""
        result = aggregate_cost_by_project([])

        assert result['projects'] == []
        assert result['truncated'] is False
        assert result['total_projects'] == 0

    def test_single_project(self):
        """Single project gets 100% of spend."""
        records = [
            {'project_id': 'proj_only', 'cost_amount': 10.00},
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 1
        assert result['projects'][0]['project_id'] == 'proj_only'
        assert result['projects'][0]['cost'] == 10.00
        assert result['projects'][0]['percentage'] == 100.0
        assert result['truncated'] is False
        assert result['total_projects'] == 1

    def test_records_without_project_id_are_skipped(self):
        """Records without a project_id field are ignored."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 5.00},
            {'cost_amount': 3.00},  # no project_id
            {'project_id': None, 'cost_amount': 2.00},  # project_id is None
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 1
        assert result['projects'][0]['project_id'] == 'proj_abc'
        assert result['total_projects'] == 1

    def test_all_zero_costs(self):
        """All zero cost records produce 0% for each project."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 0.0},
            {'project_id': 'proj_def', 'cost_amount': 0.0},
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 2
        for p in result['projects']:
            assert p['cost'] == 0.0
            assert p['percentage'] == 0.0

    def test_output_structure(self):
        """Result dict has exactly projects, truncated, and total_projects keys."""
        records = [
            {'project_id': 'proj_abc', 'cost_amount': 5.00},
        ]
        result = aggregate_cost_by_project(records)

        assert set(result.keys()) == {'projects', 'truncated', 'total_projects'}
        assert set(result['projects'][0].keys()) == {'project_id', 'cost', 'percentage'}

    def test_with_full_normalized_records(self):
        """Works correctly with full normalized records (extra fields ignored)."""
        records = [
            {
                'date': '2024-01-01',
                'service_name': 'gpt-4',
                'cost_amount': 7.50,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-abc123',
                'input_tokens': 150000,
                'output_tokens': 45000,
                'project_id': 'proj_abc',
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
                'project_id': 'proj_def',
            },
            {
                'date': '2024-01-02',
                'service_name': 'gpt-4',
                'cost_amount': 2.80,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-abc123',
                'input_tokens': 130000,
                'output_tokens': 40000,
                'project_id': 'proj_def',
            },
        ]
        result = aggregate_cost_by_project(records)

        assert len(result['projects']) == 2
        assert result['projects'][0]['project_id'] == 'proj_abc'
        assert result['projects'][0]['cost'] == 7.50
        assert result['projects'][1]['project_id'] == 'proj_def'
        assert result['projects'][1]['cost'] == 4.95
        assert result['total_projects'] == 2
        assert result['truncated'] is False
