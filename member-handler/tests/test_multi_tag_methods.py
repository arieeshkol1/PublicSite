"""Unit tests for multi-tag discovery and querying methods (Tasks 2.1, 2.2, 2.3).

Tests the _discover_active_tag_keys, _call_ce_for_single_tag, and
_parse_single_tag_response methods of IncrementalFetchEngine.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from incremental_fetch_engine import IncrementalFetchEngine, RETRYABLE_ERROR_CODES
from cache_types import DateRange


@pytest.fixture
def engine():
    """Create an IncrementalFetchEngine instance."""
    return IncrementalFetchEngine()


@pytest.fixture
def date_range():
    """Create a sample date range."""
    return DateRange(start='2024-01-01', end='2024-01-08')


@pytest.fixture
def mock_ce_client():
    """Create a mock CE client."""
    return MagicMock()


# ============================================================
# Tests for _discover_active_tag_keys (Task 2.1)
# ============================================================

class TestDiscoverActiveTagKeys:
    """Tests for _discover_active_tag_keys method."""

    def test_returns_all_tag_keys_on_success(self, engine, mock_ce_client, date_range):
        """Returns all tag key strings when get_tags succeeds."""
        mock_ce_client.get_tags.return_value = {
            'Tags': ['Environment', 'Team', 'Project'],
            'ReturnSize': 3,
        }
        result = engine._discover_active_tag_keys(mock_ce_client, date_range)
        assert result == ['Environment', 'Team', 'Project']
        mock_ce_client.get_tags.assert_called_once_with(
            TimePeriod={'Start': '2024-01-01', 'End': '2024-01-08'}
        )

    def test_returns_empty_list_on_api_failure(self, engine, mock_ce_client, date_range):
        """Returns empty list and logs warning on API failure."""
        mock_ce_client.get_tags.side_effect = Exception("Access denied")
        result = engine._discover_active_tag_keys(mock_ce_client, date_range)
        assert result == []

    def test_returns_empty_list_when_no_tags_found(self, engine, mock_ce_client, date_range):
        """Returns empty list and logs info when no tags exist."""
        mock_ce_client.get_tags.return_value = {'Tags': [], 'ReturnSize': 0}
        result = engine._discover_active_tag_keys(mock_ce_client, date_range)
        assert result == []

    def test_returns_single_tag_key(self, engine, mock_ce_client, date_range):
        """Returns a single tag key when only one is active."""
        mock_ce_client.get_tags.return_value = {'Tags': ['Environment']}
        result = engine._discover_active_tag_keys(mock_ce_client, date_range)
        assert result == ['Environment']

    def test_handles_client_error_gracefully(self, engine, mock_ce_client, date_range):
        """Handles ClientError without raising."""
        mock_ce_client.get_tags.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'Not allowed'}},
            'GetTags'
        )
        result = engine._discover_active_tag_keys(mock_ce_client, date_range)
        assert result == []


# ============================================================
# Tests for _call_ce_for_single_tag (Task 2.2)
# ============================================================

class TestCallCeForSingleTag:
    """Tests for _call_ce_for_single_tag method."""

    def test_successful_call_returns_response(self, engine, mock_ce_client, date_range):
        """Returns CE response on successful call."""
        expected_response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Environment$Production'], 'Metrics': {'UnblendedCost': {'Amount': '45.20', 'Unit': 'USD'}}}
                    ],
                }
            ]
        }
        mock_ce_client.get_cost_and_usage.return_value = expected_response

        result = engine._call_ce_for_single_tag(mock_ce_client, date_range, 'Environment')
        assert result == expected_response
        mock_ce_client.get_cost_and_usage.assert_called_once_with(
            TimePeriod={'Start': '2024-01-01', 'End': '2024-01-08'},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'TAG', 'Key': 'Environment'}],
        )

    def test_returns_none_on_non_retryable_error(self, engine, mock_ce_client, date_range):
        """Returns None on non-retryable error without retrying."""
        mock_ce_client.get_cost_and_usage.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException', 'Message': 'Invalid tag'}},
            'GetCostAndUsage'
        )
        result = engine._call_ce_for_single_tag(mock_ce_client, date_range, 'BadTag')
        assert result is None
        # Should only be called once (no retries for non-retryable errors)
        assert mock_ce_client.get_cost_and_usage.call_count == 1

    @patch('incremental_fetch_engine.time.sleep')
    def test_retries_on_throttling_then_succeeds(self, mock_sleep, engine, mock_ce_client, date_range):
        """Retries on ThrottlingException and succeeds on second attempt."""
        expected_response = {'ResultsByTime': []}
        mock_ce_client.get_cost_and_usage.side_effect = [
            ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'GetCostAndUsage'
            ),
            expected_response,
        ]
        result = engine._call_ce_for_single_tag(mock_ce_client, date_range, 'Environment')
        assert result == expected_response
        assert mock_ce_client.get_cost_and_usage.call_count == 2
        mock_sleep.assert_called_once_with(0.1)  # base_delay * 2^0

    @patch('incremental_fetch_engine.time.sleep')
    def test_returns_none_after_retry_exhaustion(self, mock_sleep, engine, mock_ce_client, date_range):
        """Returns None after all retries are exhausted."""
        mock_ce_client.get_cost_and_usage.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'GetCostAndUsage'
        )
        result = engine._call_ce_for_single_tag(
            mock_ce_client, date_range, 'Environment', max_retries=2
        )
        assert result is None
        # Initial attempt + 2 retries = 3 calls
        assert mock_ce_client.get_cost_and_usage.call_count == 3

    @patch('incremental_fetch_engine.time.sleep')
    def test_exponential_backoff_delays(self, mock_sleep, engine, mock_ce_client, date_range):
        """Verifies exponential backoff delay pattern."""
        mock_ce_client.get_cost_and_usage.side_effect = ClientError(
            {'Error': {'Code': 'RequestLimitExceeded', 'Message': 'Limit'}},
            'GetCostAndUsage'
        )
        engine._call_ce_for_single_tag(
            mock_ce_client, date_range, 'Team', max_retries=3, base_delay=0.1
        )
        # Delays: 0.1*2^0=0.1, 0.1*2^1=0.2, 0.1*2^2=0.4
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)
        mock_sleep.assert_any_call(0.4)

    @patch('incremental_fetch_engine.time.sleep')
    def test_retries_on_internal_error(self, mock_sleep, engine, mock_ce_client, date_range):
        """Retries on InternalError (a retryable code)."""
        expected_response = {'ResultsByTime': []}
        mock_ce_client.get_cost_and_usage.side_effect = [
            ClientError(
                {'Error': {'Code': 'InternalError', 'Message': 'Internal'}},
                'GetCostAndUsage'
            ),
            expected_response,
        ]
        result = engine._call_ce_for_single_tag(mock_ce_client, date_range, 'Project')
        assert result == expected_response


# ============================================================
# Tests for _parse_single_tag_response (Task 2.3)
# ============================================================

class TestParseSingleTagResponse:
    """Tests for _parse_single_tag_response method."""

    def test_basic_parsing(self, engine):
        """Parses a basic CE response into {date: {value: cost}} structure."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Environment$Production'], 'Metrics': {'UnblendedCost': {'Amount': '45.20', 'Unit': 'USD'}}},
                        {'Keys': ['Environment$Staging'], 'Metrics': {'UnblendedCost': {'Amount': '12.50', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {
            '2024-01-01': {'Production': 45.20, 'Staging': 12.50}
        }

    def test_excludes_zero_cost_entries(self, engine):
        """Zero-cost entries are excluded from the result."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Environment$Production'], 'Metrics': {'UnblendedCost': {'Amount': '45.20', 'Unit': 'USD'}}},
                        {'Keys': ['Environment$Dev'], 'Metrics': {'UnblendedCost': {'Amount': '0.0', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert '2024-01-01' in result
        assert 'Dev' not in result['2024-01-01']
        assert result['2024-01-01'] == {'Production': 45.20}

    def test_empty_key_becomes_untagged(self, engine):
        """Empty string key is stored as '(untagged)'."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': [''], 'Metrics': {'UnblendedCost': {'Amount': '10.00', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {'2024-01-01': {'(untagged)': 10.00}}

    def test_dollar_sign_only_becomes_untagged(self, engine):
        """A bare '$' key is stored as '(untagged)'."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['$'], 'Metrics': {'UnblendedCost': {'Amount': '5.00', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {'2024-01-01': {'(untagged)': 5.00}}

    def test_tag_key_dollar_becomes_untagged(self, engine):
        """'tagKey$' (no value after $) is stored as '(untagged)'."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Environment$'], 'Metrics': {'UnblendedCost': {'Amount': '8.50', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {'2024-01-01': {'(untagged)': 8.50}}

    def test_key_without_dollar_used_as_value(self, engine):
        """Key without '$' is used directly as the tag value."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Production'], 'Metrics': {'UnblendedCost': {'Amount': '30.00', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {'2024-01-01': {'Production': 30.00}}

    def test_multiple_days(self, engine):
        """Parses multiple days correctly."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Team$Backend'], 'Metrics': {'UnblendedCost': {'Amount': '20.00', 'Unit': 'USD'}}},
                    ],
                },
                {
                    'TimePeriod': {'Start': '2024-01-02', 'End': '2024-01-03'},
                    'Groups': [
                        {'Keys': ['Team$Backend'], 'Metrics': {'UnblendedCost': {'Amount': '25.00', 'Unit': 'USD'}}},
                        {'Keys': ['Team$Frontend'], 'Metrics': {'UnblendedCost': {'Amount': '15.00', 'Unit': 'USD'}}},
                    ],
                },
            ]
        }
        result = engine._parse_single_tag_response(response, 'Team')
        assert result == {
            '2024-01-01': {'Backend': 20.00},
            '2024-01-02': {'Backend': 25.00, 'Frontend': 15.00},
        }

    def test_empty_response(self, engine):
        """Returns empty dict for empty response."""
        response = {'ResultsByTime': []}
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {}

    def test_day_with_only_zero_costs_excluded(self, engine):
        """A day where all entries have zero cost is excluded from result."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['Environment$Dev'], 'Metrics': {'UnblendedCost': {'Amount': '0.0', 'Unit': 'USD'}}},
                        {'Keys': ['Environment$Test'], 'Metrics': {'UnblendedCost': {'Amount': '0.0', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {}

    def test_aggregates_duplicate_untagged_values(self, engine):
        """Multiple untagged entries for same day are aggregated."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': [''], 'Metrics': {'UnblendedCost': {'Amount': '5.00', 'Unit': 'USD'}}},
                        {'Keys': ['Environment$'], 'Metrics': {'UnblendedCost': {'Amount': '3.00', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'Environment')
        assert result == {'2024-01-01': {'(untagged)': 8.00}}

    def test_value_with_dollar_in_name(self, engine):
        """Tag value containing '$' is handled correctly (split on first $ only)."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [
                        {'Keys': ['CostCenter$dept$finance'], 'Metrics': {'UnblendedCost': {'Amount': '100.00', 'Unit': 'USD'}}},
                    ],
                }
            ]
        }
        result = engine._parse_single_tag_response(response, 'CostCenter')
        # Split on first $ only: "CostCenter$dept$finance" -> value is "dept$finance"
        assert result == {'2024-01-01': {'dept$finance': 100.00}}
