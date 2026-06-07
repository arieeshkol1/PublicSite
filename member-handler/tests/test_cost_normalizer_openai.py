"""Unit tests for normalize_openai() and format_normalized_to_openai() functions.

Tests cover:
- Basic normalization of OpenAI Usage API bucket responses
- Unix timestamp to ISO date parsing
- Model name extraction as service_name (lowercased)
- Per-project breakdowns
- Round-trip integrity: normalize → format_back → re-normalize produces equivalent records
- Edge cases: missing fields, zero costs, empty results
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cost_normalizer import normalize_openai, format_normalized_to_openai, calculate_period_change


class TestNormalizeOpenai:
    """Tests for normalize_openai()."""

    def test_basic_single_bucket_single_result(self):
        """Normalize a single bucket with one result."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,  # 2024-01-01 00:00:00 UTC
            'end_time': 1704153600,
            'results': [{
                'object': 'organization.costs.result',
                'amount': {'value': 0.45, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_abc123',
                'input_tokens': 150000,
                'output_tokens': 45000,
            }]
        }]
        result = normalize_openai(raw, 'openai-org-abc123')

        assert len(result) == 1
        record = result[0]
        assert record['date'] == '2024-01-01'
        assert record['service_name'] == 'gpt-4'
        assert record['cost_amount'] == 0.45
        assert record['currency'] == 'USD'
        assert record['cloud_provider'] == 'openai'
        assert record['account_id'] == 'openai-org-abc123'
        assert record['input_tokens'] == 150000
        assert record['output_tokens'] == 45000
        assert record['project_id'] == 'proj_abc123'

    def test_multiple_results_in_bucket(self):
        """Normalize a bucket with multiple results (multiple models)."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [
                {
                    'object': 'organization.costs.result',
                    'amount': {'value': 8.20, 'currency': 'usd'},
                    'line_item': 'GPT-4',
                    'input_tokens': 150000,
                    'output_tokens': 45000,
                },
                {
                    'object': 'organization.costs.result',
                    'amount': {'value': 2.15, 'currency': 'usd'},
                    'line_item': 'GPT-4o-mini',
                    'input_tokens': 500000,
                    'output_tokens': 120000,
                },
            ]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert len(result) == 2
        assert result[0]['service_name'] == 'gpt-4'
        assert result[0]['cost_amount'] == 8.20
        assert result[1]['service_name'] == 'gpt-4o-mini'
        assert result[1]['cost_amount'] == 2.15

    def test_multiple_buckets(self):
        """Normalize multiple buckets (multiple days)."""
        raw = [
            {
                'object': 'bucket',
                'start_time': 1704067200,  # 2024-01-01
                'end_time': 1704153600,
                'results': [{
                    'amount': {'value': 5.00, 'currency': 'usd'},
                    'line_item': 'GPT-4',
                }]
            },
            {
                'object': 'bucket',
                'start_time': 1704153600,  # 2024-01-02
                'end_time': 1704240000,
                'results': [{
                    'amount': {'value': 3.00, 'currency': 'usd'},
                    'line_item': 'GPT-3.5-Turbo',
                }]
            },
        ]
        result = normalize_openai(raw, 'openai-org-test')

        assert len(result) == 2
        assert result[0]['date'] == '2024-01-01'
        assert result[1]['date'] == '2024-01-02'

    def test_unix_timestamp_parsing(self):
        """Verify Unix timestamp is correctly converted to ISO date."""
        # 2025-06-16 00:00:00 UTC = 1750032000
        raw = [{
            'object': 'bucket',
            'start_time': 1750032000,
            'end_time': 1750118400,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'DALL-E-3',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result[0]['date'] == '2025-06-16'

    def test_model_name_lowercased(self):
        """Verify line_item is lowercased as service_name."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.50, 'currency': 'usd'},
                'line_item': 'GPT-3.5-Turbo',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result[0]['service_name'] == 'gpt-3.5-turbo'

    def test_currency_uppercased(self):
        """Verify currency is uppercased in output."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'GPT-4',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result[0]['currency'] == 'USD'

    def test_project_id_included_when_present(self):
        """Project ID is included in output when present in result."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_xyz789',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result[0]['project_id'] == 'proj_xyz789'

    def test_project_id_absent_when_not_in_response(self):
        """Project ID is not included when not in the original result."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'GPT-4',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert 'project_id' not in result[0]

    def test_missing_token_counts_default_to_zero(self):
        """Token counts default to 0 when not present."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'GPT-4',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result[0]['input_tokens'] == 0
        assert result[0]['output_tokens'] == 0

    def test_empty_results_in_bucket(self):
        """Bucket with no results produces no records."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': []
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result == []

    def test_empty_input(self):
        """Empty input list produces empty output."""
        result = normalize_openai([], 'openai-org-test')
        assert result == []

    def test_missing_start_time_skipped(self):
        """Bucket with missing start_time is skipped."""
        raw = [{
            'object': 'bucket',
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 1.00, 'currency': 'usd'},
                'line_item': 'GPT-4',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert result == []

    def test_zero_cost_still_included(self):
        """Records with zero cost are still included (unlike AWS which filters them)."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 0.0, 'currency': 'usd'},
                'line_item': 'GPT-4',
            }]
        }]
        result = normalize_openai(raw, 'openai-org-test')

        assert len(result) == 1
        assert result[0]['cost_amount'] == 0.0


class TestFormatNormalizedToOpenai:
    """Tests for format_normalized_to_openai()."""

    def test_basic_format_back(self):
        """Convert normalized records back to OpenAI bucket format."""
        normalized = [{
            'date': '2024-01-01',
            'service_name': 'gpt-4',
            'cost_amount': 0.45,
            'currency': 'USD',
            'cloud_provider': 'openai',
            'account_id': 'openai-org-abc123',
            'input_tokens': 150000,
            'output_tokens': 45000,
            'project_id': 'proj_abc123',
        }]
        buckets = format_normalized_to_openai(normalized)

        assert len(buckets) == 1
        bucket = buckets[0]
        assert bucket['object'] == 'bucket'
        assert bucket['start_time'] == 1704067200
        assert bucket['end_time'] == 1704067200 + 86400
        assert len(bucket['results']) == 1

        result = bucket['results'][0]
        assert result['object'] == 'organization.costs.result'
        assert result['amount']['value'] == 0.45
        assert result['amount']['currency'] == 'usd'
        assert result['line_item'] == 'gpt-4'
        assert result['input_tokens'] == 150000
        assert result['output_tokens'] == 45000
        assert result['project_id'] == 'proj_abc123'

    def test_groups_by_date(self):
        """Records with the same date are grouped into one bucket."""
        normalized = [
            {
                'date': '2024-01-01',
                'service_name': 'gpt-4',
                'cost_amount': 5.00,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-test',
                'input_tokens': 100000,
                'output_tokens': 30000,
            },
            {
                'date': '2024-01-01',
                'service_name': 'gpt-3.5-turbo',
                'cost_amount': 1.00,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-test',
                'input_tokens': 200000,
                'output_tokens': 50000,
            },
        ]
        buckets = format_normalized_to_openai(normalized)

        assert len(buckets) == 1
        assert len(buckets[0]['results']) == 2

    def test_multiple_dates_produce_multiple_buckets(self):
        """Records from different dates produce separate buckets."""
        normalized = [
            {
                'date': '2024-01-01',
                'service_name': 'gpt-4',
                'cost_amount': 5.00,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-test',
                'input_tokens': 0,
                'output_tokens': 0,
            },
            {
                'date': '2024-01-02',
                'service_name': 'gpt-4',
                'cost_amount': 3.00,
                'currency': 'USD',
                'cloud_provider': 'openai',
                'account_id': 'openai-org-test',
                'input_tokens': 0,
                'output_tokens': 0,
            },
        ]
        buckets = format_normalized_to_openai(normalized)

        assert len(buckets) == 2
        assert buckets[0]['start_time'] < buckets[1]['start_time']

    def test_empty_input(self):
        """Empty input produces empty output."""
        assert format_normalized_to_openai([]) == []


class TestNormalizationRoundTrip:
    """Tests for round-trip integrity: normalize → format_back → re-normalize."""

    def test_round_trip_basic(self):
        """Basic round-trip: normalize → format → re-normalize produces equivalent records."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'object': 'organization.costs.result',
                'amount': {'value': 0.45, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_abc123',
                'input_tokens': 150000,
                'output_tokens': 45000,
            }]
        }]
        account_id = 'openai-org-abc123'

        # First normalization
        normalized1 = normalize_openai(raw, account_id)

        # Format back to OpenAI structure
        formatted_back = format_normalized_to_openai(normalized1)

        # Re-normalize
        normalized2 = normalize_openai(formatted_back, account_id)

        # Compare
        assert len(normalized1) == len(normalized2)
        for r1, r2 in zip(normalized1, normalized2):
            assert r1 == r2

    def test_round_trip_multiple_models(self):
        """Round-trip with multiple models in one bucket."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [
                {
                    'amount': {'value': 8.20, 'currency': 'usd'},
                    'line_item': 'GPT-4',
                    'input_tokens': 150000,
                    'output_tokens': 45000,
                },
                {
                    'amount': {'value': 2.15, 'currency': 'usd'},
                    'line_item': 'GPT-4o-mini',
                    'input_tokens': 500000,
                    'output_tokens': 120000,
                },
            ]
        }]
        account_id = 'openai-org-test'

        normalized1 = normalize_openai(raw, account_id)
        formatted_back = format_normalized_to_openai(normalized1)
        normalized2 = normalize_openai(formatted_back, account_id)

        assert len(normalized1) == len(normalized2)
        for r1, r2 in zip(normalized1, normalized2):
            assert r1 == r2

    def test_round_trip_multiple_days(self):
        """Round-trip with multiple days."""
        raw = [
            {
                'object': 'bucket',
                'start_time': 1704067200,
                'end_time': 1704153600,
                'results': [{
                    'amount': {'value': 5.00, 'currency': 'usd'},
                    'line_item': 'GPT-4',
                    'input_tokens': 100000,
                    'output_tokens': 30000,
                }]
            },
            {
                'object': 'bucket',
                'start_time': 1704153600,
                'end_time': 1704240000,
                'results': [{
                    'amount': {'value': 3.00, 'currency': 'usd'},
                    'line_item': 'GPT-3.5-Turbo',
                    'input_tokens': 200000,
                    'output_tokens': 60000,
                }]
            },
        ]
        account_id = 'openai-org-test'

        normalized1 = normalize_openai(raw, account_id)
        formatted_back = format_normalized_to_openai(normalized1)
        normalized2 = normalize_openai(formatted_back, account_id)

        assert len(normalized1) == len(normalized2)
        for r1, r2 in zip(normalized1, normalized2):
            assert r1 == r2

    def test_round_trip_with_project_id(self):
        """Round-trip preserves project_id."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 7.50, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_production',
                'input_tokens': 250000,
                'output_tokens': 75000,
            }]
        }]
        account_id = 'openai-org-test'

        normalized1 = normalize_openai(raw, account_id)
        formatted_back = format_normalized_to_openai(normalized1)
        normalized2 = normalize_openai(formatted_back, account_id)

        assert normalized1[0]['project_id'] == normalized2[0]['project_id']
        assert normalized1 == normalized2

    def test_round_trip_zero_tokens(self):
        """Round-trip with zero token counts."""
        raw = [{
            'object': 'bucket',
            'start_time': 1704067200,
            'end_time': 1704153600,
            'results': [{
                'amount': {'value': 0.60, 'currency': 'usd'},
                'line_item': 'DALL-E-3',
                'input_tokens': 0,
                'output_tokens': 0,
            }]
        }]
        account_id = 'openai-org-test'

        normalized1 = normalize_openai(raw, account_id)
        formatted_back = format_normalized_to_openai(normalized1)
        normalized2 = normalize_openai(formatted_back, account_id)

        assert normalized1 == normalized2


class TestCalculatePeriodChange:
    """Tests for calculate_period_change()."""

    def test_positive_increase(self):
        """50% increase: (150 - 100) / 100 * 100 = 50.0%."""
        result = calculate_period_change(150.0, 100.0)
        assert result == 50.0

    def test_positive_decrease(self):
        """50% decrease: (50 - 100) / 100 * 100 = -50.0%."""
        result = calculate_period_change(50.0, 100.0)
        assert result == -50.0

    def test_no_change(self):
        """Same totals: (100 - 100) / 100 * 100 = 0.0%."""
        result = calculate_period_change(100.0, 100.0)
        assert result == 0.0

    def test_zero_previous_positive_current(self):
        """Previous is zero with positive current returns infinity (new spend)."""
        result = calculate_period_change(50.0, 0.0)
        assert result == float('inf')
        assert math.isinf(result)

    def test_zero_previous_zero_current(self):
        """Both previous and current are zero returns 0.0."""
        result = calculate_period_change(0.0, 0.0)
        assert result == 0.0

    def test_rounds_to_one_decimal_place(self):
        """Result is rounded to 1 decimal place: (200 - 300) / 300 * 100 = -33.333... -> -33.3."""
        result = calculate_period_change(200.0, 300.0)
        assert result == -33.3

    def test_small_fractional_change(self):
        """Small fractional change: (101.5 - 100) / 100 * 100 = 1.5%."""
        result = calculate_period_change(101.5, 100.0)
        assert result == 1.5

    def test_large_increase(self):
        """Large increase: (1000 - 10) / 10 * 100 = 9900.0%."""
        result = calculate_period_change(1000.0, 10.0)
        assert result == 9900.0

    def test_current_is_zero_previous_positive(self):
        """100% decrease: (0 - 100) / 100 * 100 = -100.0%."""
        result = calculate_period_change(0.0, 100.0)
        assert result == -100.0
