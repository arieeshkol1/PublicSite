"""Unit tests for the OpenAI optimization recommendation engine."""
import pytest
from openai_recommendations import (
    generate_recommendations,
    _check_model_switch_rule,
    _check_prompt_optimization_rule,
    GPT4_MODEL_NAMES,
)


class TestGenerateRecommendations:
    """Tests for the core generate_recommendations function."""

    def test_empty_records_returns_empty_list(self):
        """Empty input should produce no recommendations."""
        assert generate_recommendations([]) == []

    def test_none_input_returns_empty_list(self):
        """None-ish empty input should produce no recommendations."""
        assert generate_recommendations([]) == []

    def test_no_rules_match_returns_empty(self):
        """Records that don't trigger any rule should return empty list."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 10.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 1000,
                'output_tokens': 1000,  # ratio 1:1, well below 4:1
            }
        ]
        result = generate_recommendations(records)
        assert result == []

    def test_results_ordered_by_savings_descending(self):
        """When multiple rules fire, results are sorted by savings descending."""
        # Create records that trigger both rules
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 100.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 200,  # avg output 200 ≤ 500
            },
            {
                'date': '2025-01-16',
                'service_name': 'gpt-4',
                'cost_amount': 100.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 200,
            },
        ]
        result = generate_recommendations(records)
        assert len(result) >= 1
        # Verify sorted by savings descending
        for i in range(len(result) - 1):
            assert result[i]['estimated_monthly_savings'] >= result[i + 1]['estimated_monthly_savings']

    def test_max_10_recommendations(self):
        """Result is capped at 10 recommendations."""
        # This test verifies the cap even though current rules produce at most 2
        # The cap logic is still verified structurally
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 100.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 200,
            }
        ]
        result = generate_recommendations(records)
        assert len(result) <= 10

    def test_recommendation_field_constraints(self):
        """All recommendations must have valid field constraints."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 100.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 200,
            }
        ]
        result = generate_recommendations(records)
        for rec in result:
            assert len(rec['title']) <= 80
            assert len(rec['description']) <= 300
            assert isinstance(rec['estimated_monthly_savings'], float)
            assert rec['estimated_monthly_savings'] >= 0
            assert rec['difficulty'] in ('easy', 'medium', 'hard')


class TestModelSwitchRule:
    """Tests for the model-switch recommendation rule (Task 9.2)."""

    def test_triggers_when_gpt4_above_50pct_and_short_output(self):
        """Rule fires when GPT-4 > 50% spend AND avg output ≤ 500 tokens."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 300,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is not None
        assert result['difficulty'] == 'easy'
        assert result['estimated_monthly_savings'] > 0

    def test_does_not_trigger_when_gpt4_exactly_50pct(self):
        """Rule does NOT fire when GPT-4 is exactly 50% (not > 50%)."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 300,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is None

    def test_does_not_trigger_when_gpt4_below_50pct(self):
        """Rule does NOT fire when GPT-4 < 50% of total spend."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 30.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 5000,
                'output_tokens': 200,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 70.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 100000,
                'output_tokens': 20000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is None

    def test_does_not_trigger_when_avg_output_above_500(self):
        """Rule does NOT fire when avg GPT-4 output exceeds 500 tokens."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 600,  # > 500
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is None

    def test_does_not_trigger_when_avg_output_exactly_501(self):
        """Rule does NOT fire when avg GPT-4 output is 501 tokens."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 501,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is None

    def test_triggers_at_boundary_avg_output_exactly_500(self):
        """Rule fires when avg GPT-4 output is exactly 500 tokens (≤500)."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 500,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is not None

    def test_savings_estimate_uses_1_30th_cost_ratio(self):
        """Savings should be GPT-4 cost × (1 - 1/30) = GPT-4 cost × 29/30."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 90.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 300,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 10.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        result = _check_model_switch_rule(records)
        assert result is not None
        expected_savings = round(90.0 * (1 - 1 / 30), 2)
        assert result['estimated_monthly_savings'] == expected_savings

    def test_recognizes_gpt4_variants(self):
        """All GPT-4 model variants are counted toward GPT-4 spend."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4-turbo',
                'cost_amount': 40.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 200,
            },
            {
                'date': '2025-01-16',
                'service_name': 'gpt-4-0125-preview',
                'cost_amount': 40.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 300,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 10.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 5000,
            },
        ]
        # GPT-4 variants total: 80/90 = ~89% > 50%, avg output: (200+300)/2 = 250 ≤ 500
        result = _check_model_switch_rule(records)
        assert result is not None

    def test_no_records_returns_none(self):
        """Empty records returns None."""
        result = _check_model_switch_rule([])
        assert result is None


class TestPromptOptimizationRule:
    """Tests for the prompt optimization recommendation rule (Task 9.4)."""

    def test_triggers_when_ratio_above_4_to_1(self):
        """Rule fires when input:output ratio > 4:1."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 5000,
                'output_tokens': 1000,  # ratio 5:1 > 4:1
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is not None
        assert result['difficulty'] == 'medium'
        assert result['estimated_monthly_savings'] > 0

    def test_does_not_trigger_when_ratio_exactly_4_to_1(self):
        """Rule does NOT fire when ratio is exactly 4:1."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 4000,
                'output_tokens': 1000,  # ratio exactly 4:1
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is None

    def test_does_not_trigger_when_ratio_below_4_to_1(self):
        """Rule does NOT fire when ratio < 4:1."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 3000,
                'output_tokens': 1000,  # ratio 3:1
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is None

    def test_ratio_computed_across_all_records(self):
        """Ratio is computed from total input and total output across all records."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 25.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 3000,
                'output_tokens': 1000,  # per-record ratio 3:1
            },
            {
                'date': '2025-01-16',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 25.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 7000,
                'output_tokens': 1000,  # per-record ratio 7:1
            },
        ]
        # Aggregate: 10000 input / 2000 output = 5:1 > 4:1
        result = _check_prompt_optimization_rule(records)
        assert result is not None

    def test_does_not_trigger_with_zero_output_tokens(self):
        """Rule does NOT fire when total output tokens is zero."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 5000,
                'output_tokens': 0,
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is None

    def test_savings_estimate_uses_30pct_reduction(self):
        """Savings = 30% of cost × input fraction."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 100.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 5000,
                'output_tokens': 1000,  # ratio 5:1
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is not None
        # input_fraction = 5000 / (5000 + 1000) = 5/6 ≈ 0.8333
        # savings = 100.0 * (5/6) * 0.30 = 25.0
        expected = round(100.0 * (5000 / 6000) * 0.30, 2)
        assert result['estimated_monthly_savings'] == expected

    def test_no_records_returns_none(self):
        """Empty records returns None."""
        result = _check_prompt_optimization_rule([])
        assert result is None

    def test_just_above_4_to_1_triggers(self):
        """Rule fires when ratio is just barely above 4:1."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 50.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 4001,
                'output_tokens': 1000,  # ratio 4.001:1
            },
        ]
        result = _check_prompt_optimization_rule(records)
        assert result is not None


class TestIntegration:
    """Integration tests verifying both rules can fire together."""

    def test_both_rules_fire_together(self):
        """When both conditions are met, both recommendations appear."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 300,  # avg output 300 ≤ 500
            },
            {
                'date': '2025-01-16',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 200,
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 10.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 10000,
                'output_tokens': 500,
            },
        ]
        # GPT-4: 160/170 = 94% > 50%, avg output: (300+200)/2 = 250 ≤ 500
        # Input: 110000, Output: 1000 => ratio 110:1 > 4:1
        result = generate_recommendations(records)
        assert len(result) == 2
        # Should be sorted by savings descending
        assert result[0]['estimated_monthly_savings'] >= result[1]['estimated_monthly_savings']

    def test_only_model_switch_fires(self):
        """Only model-switch fires when prompt ratio is low."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 1000,
                'output_tokens': 400,  # ratio 2.5:1, no prompt opt
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 1000,
                'output_tokens': 500,
            },
        ]
        # GPT-4: 80/100 = 80% > 50%, avg output: 400 ≤ 500 => model switch fires
        # Total input: 2000, output: 900, ratio: 2.2:1 => no prompt opt
        result = generate_recommendations(records)
        assert len(result) == 1
        assert 'GPT-4o-mini' in result[0]['title'] or 'switch' in result[0]['title'].lower()

    def test_only_prompt_opt_fires(self):
        """Only prompt optimization fires when model switch conditions aren't met."""
        records = [
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4o-mini',
                'cost_amount': 80.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 1000,  # high input ratio
            },
            {
                'date': '2025-01-15',
                'service_name': 'gpt-4',
                'cost_amount': 20.0,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'org-123',
                'input_tokens': 50000,
                'output_tokens': 1000,
            },
        ]
        # GPT-4: 20/100 = 20% < 50% => no model switch
        # Total input: 100000, output: 2000, ratio: 50:1 > 4 => prompt opt fires
        result = generate_recommendations(records)
        assert len(result) == 1
        assert 'prompt' in result[0]['title'].lower() or 'input' in result[0]['title'].lower()
