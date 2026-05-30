"""Unit tests for IncrementalFetchEngine.fetch_cost_data (Task 5.3).

Tests CE API fetch logic including:
- Calling GetCostAndUsage with correct parameters
- Batching contiguous ranges into minimum API calls
- Exponential backoff with max 3 retries for transient errors
- Parsing CE API response into CostDataItem objects
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from incremental_fetch_engine import IncrementalFetchEngine, RETRYABLE_ERROR_CODES
from cache_types import CostDataItem, DateRange


@pytest.fixture
def engine():
    """Create an IncrementalFetchEngine instance."""
    return IncrementalFetchEngine()


@pytest.fixture
def mock_credentials():
    """Sample AWS credentials dict."""
    return {
        'AccessKeyId': 'AKIAIOSFODNN7EXAMPLE',
        'SecretAccessKey': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        'SessionToken': 'FwoGZXIvYXdzEBYaDHqa0AP',
    }


def _make_ce_response(periods: list[dict]) -> dict:
    """Helper to build a CE GetCostAndUsage response.

    Args:
        periods: List of dicts with 'date', 'services' keys.
            services is a dict of {service_name: cost_amount}.
    """
    results_by_time = []
    for period in periods:
        groups = []
        for service_name, cost in period['services'].items():
            groups.append({
                'Keys': [service_name],
                'Metrics': {
                    'UnblendedCost': {
                        'Amount': str(cost),
                        'Unit': 'USD',
                    }
                },
            })
        results_by_time.append({
            'TimePeriod': {
                'Start': period['date'],
                'End': period.get('end_date', period['date']),
            },
            'Groups': groups,
        })

    return {'ResultsByTime': results_by_time}


def _make_client_error(error_code: str, message: str = 'Error') -> ClientError:
    """Helper to create a ClientError with the given error code."""
    return ClientError(
        error_response={
            'Error': {
                'Code': error_code,
                'Message': message,
            }
        },
        operation_name='GetCostAndUsage',
    )


class TestFetchCostDataBasic:
    """Basic fetch_cost_data tests."""

    @patch('incremental_fetch_engine.boto3.client')
    def test_empty_date_ranges_returns_empty(self, mock_boto_client, engine, mock_credentials):
        """Empty date_ranges list returns empty result without API calls."""
        result = engine.fetch_cost_data([], mock_credentials)
        assert result == []
        mock_boto_client.assert_not_called()

    @patch('incremental_fetch_engine.boto3.client')
    def test_single_range_single_api_call(self, mock_boto_client, engine, mock_credentials):
        """Single date range makes exactly one API call."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([
            {'date': '2024-01-01', 'services': {'Amazon EC2': 25.30, 'Amazon S3': 8.12}},
        ])

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert mock_ce.get_cost_and_usage.call_count == 1
        assert len(result) == 1
        assert result[0].date == '2024-01-01'

    @patch('incremental_fetch_engine.boto3.client')
    def test_credentials_passed_to_client(self, mock_boto_client, engine, mock_credentials):
        """Credentials are correctly passed to boto3 client creation."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        engine.fetch_cost_data(ranges, mock_credentials)

        mock_boto_client.assert_called_once_with(
            'ce',
            aws_access_key_id='AKIAIOSFODNN7EXAMPLE',
            aws_secret_access_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            aws_session_token='FwoGZXIvYXdzEBYaDHqa0AP',
        )

    @patch('incremental_fetch_engine.boto3.client')
    def test_api_called_with_correct_params(self, mock_boto_client, engine, mock_credentials):
        """GetCostAndUsage is called with DAILY granularity, UnblendedCost, and SERVICE grouping."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        ranges = [DateRange(start='2024-01-01', end='2024-01-05')]
        engine.fetch_cost_data(ranges, mock_credentials)

        mock_ce.get_cost_and_usage.assert_called_once_with(
            TimePeriod={'Start': '2024-01-01', 'End': '2024-01-05'},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )


class TestFetchCostDataBatching:
    """Tests for batching contiguous ranges into minimum API calls."""

    @patch('incremental_fetch_engine.boto3.client')
    def test_contiguous_ranges_merged_into_one_call(self, mock_boto_client, engine, mock_credentials):
        """Two contiguous ranges are merged into a single API call."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        # Jan 1-3 and Jan 3-5 are contiguous (end of first == start of second)
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
        ]
        engine.fetch_cost_data(ranges, mock_credentials)

        # Should be merged into one call: Jan 1-5
        assert mock_ce.get_cost_and_usage.call_count == 1
        call_args = mock_ce.get_cost_and_usage.call_args
        assert call_args[1]['TimePeriod'] == {'Start': '2024-01-01', 'End': '2024-01-05'}

    @patch('incremental_fetch_engine.boto3.client')
    def test_non_contiguous_ranges_separate_calls(self, mock_boto_client, engine, mock_credentials):
        """Non-contiguous ranges result in separate API calls."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        # Jan 1-3 and Jan 5-7 are NOT contiguous
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-05', end='2024-01-07'),
        ]
        engine.fetch_cost_data(ranges, mock_credentials)

        assert mock_ce.get_cost_and_usage.call_count == 2

    @patch('incremental_fetch_engine.boto3.client')
    def test_three_contiguous_ranges_merged(self, mock_boto_client, engine, mock_credentials):
        """Three contiguous ranges are merged into one API call."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
            DateRange(start='2024-01-05', end='2024-01-07'),
        ]
        engine.fetch_cost_data(ranges, mock_credentials)

        assert mock_ce.get_cost_and_usage.call_count == 1
        call_args = mock_ce.get_cost_and_usage.call_args
        assert call_args[1]['TimePeriod'] == {'Start': '2024-01-01', 'End': '2024-01-07'}

    @patch('incremental_fetch_engine.boto3.client')
    def test_unsorted_ranges_still_merged(self, mock_boto_client, engine, mock_credentials):
        """Unsorted contiguous ranges are still properly merged."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([])

        # Out of order but contiguous
        ranges = [
            DateRange(start='2024-01-05', end='2024-01-07'),
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
        ]
        engine.fetch_cost_data(ranges, mock_credentials)

        assert mock_ce.get_cost_and_usage.call_count == 1
        call_args = mock_ce.get_cost_and_usage.call_args
        assert call_args[1]['TimePeriod'] == {'Start': '2024-01-01', 'End': '2024-01-07'}


class TestFetchCostDataRetry:
    """Tests for exponential backoff retry logic."""

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_throttling_retried_and_succeeds(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """ThrottlingException triggers retry and succeeds on second attempt."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        # First call fails with throttling, second succeeds
        mock_ce.get_cost_and_usage.side_effect = [
            _make_client_error('ThrottlingException'),
            _make_ce_response([{'date': '2024-01-01', 'services': {'EC2': 10.0}}]),
        ]

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        assert mock_ce.get_cost_and_usage.call_count == 2
        mock_sleep.assert_called_once_with(0.1)  # base_delay * 2^0

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_request_limit_exceeded_retried(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """RequestLimitExceeded triggers retry."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        mock_ce.get_cost_and_usage.side_effect = [
            _make_client_error('RequestLimitExceeded'),
            _make_ce_response([{'date': '2024-01-01', 'services': {'S3': 5.0}}]),
        ]

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        assert mock_ce.get_cost_and_usage.call_count == 2

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_internal_error_retried(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """InternalError triggers retry."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        mock_ce.get_cost_and_usage.side_effect = [
            _make_client_error('InternalError'),
            _make_ce_response([{'date': '2024-01-01', 'services': {'Lambda': 2.0}}]),
        ]

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        assert mock_ce.get_cost_and_usage.call_count == 2

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_exponential_backoff_delays(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """Retry delays follow exponential backoff: 0.1, 0.2, 0.4."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        # Fail 3 times, succeed on 4th (attempt index 3)
        mock_ce.get_cost_and_usage.side_effect = [
            _make_client_error('ThrottlingException'),
            _make_client_error('ThrottlingException'),
            _make_client_error('ThrottlingException'),
            _make_ce_response([{'date': '2024-01-01', 'services': {'EC2': 10.0}}]),
        ]

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(0.1)   # 0.1 * 2^0
        mock_sleep.assert_any_call(0.2)   # 0.1 * 2^1
        mock_sleep.assert_any_call(0.4)   # 0.1 * 2^2

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_max_retries_exhausted_raises(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """After 3 retries (4 total attempts), the error is raised."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        # Fail all 4 attempts
        mock_ce.get_cost_and_usage.side_effect = [
            _make_client_error('ThrottlingException'),
            _make_client_error('ThrottlingException'),
            _make_client_error('ThrottlingException'),
            _make_client_error('ThrottlingException'),
        ]

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        with pytest.raises(ClientError) as exc_info:
            engine.fetch_cost_data(ranges, mock_credentials)

        assert exc_info.value.response['Error']['Code'] == 'ThrottlingException'
        assert mock_ce.get_cost_and_usage.call_count == 4  # 1 initial + 3 retries

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_non_retryable_error_raises_immediately(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """Non-retryable errors (e.g., ValidationException) raise immediately."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        mock_ce.get_cost_and_usage.side_effect = _make_client_error('ValidationException')

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        with pytest.raises(ClientError) as exc_info:
            engine.fetch_cost_data(ranges, mock_credentials)

        assert exc_info.value.response['Error']['Code'] == 'ValidationException'
        assert mock_ce.get_cost_and_usage.call_count == 1
        mock_sleep.assert_not_called()

    @patch('incremental_fetch_engine.time.sleep')
    @patch('incremental_fetch_engine.boto3.client')
    def test_access_denied_not_retried(self, mock_boto_client, mock_sleep, engine, mock_credentials):
        """AccessDeniedException is not retried."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce

        mock_ce.get_cost_and_usage.side_effect = _make_client_error('AccessDeniedException')

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        with pytest.raises(ClientError):
            engine.fetch_cost_data(ranges, mock_credentials)

        assert mock_ce.get_cost_and_usage.call_count == 1
        mock_sleep.assert_not_called()


class TestFetchCostDataParsing:
    """Tests for parsing CE API response into CostDataItem objects."""

    @patch('incremental_fetch_engine.boto3.client')
    def test_single_day_single_service(self, mock_boto_client, engine, mock_credentials):
        """Parse response with one day and one service."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([
            {'date': '2024-01-15', 'services': {'Amazon EC2': 25.30}},
        ])

        ranges = [DateRange(start='2024-01-15', end='2024-01-16')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        item = result[0]
        assert item.date == '2024-01-15'
        assert abs(item.cost_amount - 25.30) < 0.001
        assert item.currency == 'USD'
        assert item.service_breakdown == {'Amazon EC2': 25.30}
        assert item.fetched_at != ''

    @patch('incremental_fetch_engine.boto3.client')
    def test_single_day_multiple_services(self, mock_boto_client, engine, mock_credentials):
        """Parse response with one day and multiple services."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([
            {
                'date': '2024-01-15',
                'services': {
                    'Amazon EC2': 25.30,
                    'Amazon S3': 8.12,
                    'AWS Lambda': 5.15,
                    'Amazon RDS': 4.00,
                },
            },
        ])

        ranges = [DateRange(start='2024-01-15', end='2024-01-16')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        item = result[0]
        assert abs(item.cost_amount - 42.57) < 0.001
        assert item.service_breakdown == {
            'Amazon EC2': 25.30,
            'Amazon S3': 8.12,
            'AWS Lambda': 5.15,
            'Amazon RDS': 4.00,
        }

    @patch('incremental_fetch_engine.boto3.client')
    def test_multiple_days(self, mock_boto_client, engine, mock_credentials):
        """Parse response with multiple days."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([
            {'date': '2024-01-01', 'services': {'EC2': 10.0}},
            {'date': '2024-01-02', 'services': {'EC2': 12.0, 'S3': 3.0}},
            {'date': '2024-01-03', 'services': {'Lambda': 1.5}},
        ])

        ranges = [DateRange(start='2024-01-01', end='2024-01-04')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 3
        assert result[0].date == '2024-01-01'
        assert abs(result[0].cost_amount - 10.0) < 0.001
        assert result[1].date == '2024-01-02'
        assert abs(result[1].cost_amount - 15.0) < 0.001
        assert result[2].date == '2024-01-03'
        assert abs(result[2].cost_amount - 1.5) < 0.001

    @patch('incremental_fetch_engine.boto3.client')
    def test_empty_response(self, mock_boto_client, engine, mock_credentials):
        """Empty ResultsByTime returns empty list."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = {'ResultsByTime': []}

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert result == []

    @patch('incremental_fetch_engine.boto3.client')
    def test_day_with_no_groups(self, mock_boto_client, engine, mock_credentials):
        """A day with no service groups produces zero cost item."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [],
                }
            ]
        }

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert len(result) == 1
        assert result[0].cost_amount == 0.0
        assert result[0].service_breakdown == {}
        assert result[0].currency == 'USD'

    @patch('incremental_fetch_engine.boto3.client')
    def test_fetched_at_is_set(self, mock_boto_client, engine, mock_credentials):
        """Each CostDataItem has a non-empty fetched_at timestamp."""
        mock_ce = MagicMock()
        mock_boto_client.return_value = mock_ce
        mock_ce.get_cost_and_usage.return_value = _make_ce_response([
            {'date': '2024-01-01', 'services': {'EC2': 10.0}},
        ])

        ranges = [DateRange(start='2024-01-01', end='2024-01-02')]
        result = engine.fetch_cost_data(ranges, mock_credentials)

        assert result[0].fetched_at != ''
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(result[0].fetched_at)


class TestBatchContiguousRanges:
    """Tests for the _batch_contiguous_ranges helper method."""

    def test_empty_list(self, engine):
        """Empty input returns empty output."""
        assert engine._batch_contiguous_ranges([]) == []

    def test_single_range(self, engine):
        """Single range returns unchanged."""
        ranges = [DateRange(start='2024-01-01', end='2024-01-05')]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [DateRange(start='2024-01-01', end='2024-01-05')]

    def test_two_contiguous(self, engine):
        """Two contiguous ranges merge into one."""
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
        ]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [DateRange(start='2024-01-01', end='2024-01-05')]

    def test_two_non_contiguous(self, engine):
        """Two non-contiguous ranges stay separate."""
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-05', end='2024-01-07'),
        ]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-05', end='2024-01-07'),
        ]

    def test_overlapping_ranges_merged(self, engine):
        """Overlapping ranges are merged."""
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-05'),
            DateRange(start='2024-01-03', end='2024-01-07'),
        ]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [DateRange(start='2024-01-01', end='2024-01-07')]

    def test_unsorted_input(self, engine):
        """Unsorted input is handled correctly."""
        ranges = [
            DateRange(start='2024-01-05', end='2024-01-07'),
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
        ]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [DateRange(start='2024-01-01', end='2024-01-07')]

    def test_mixed_contiguous_and_separate(self, engine):
        """Mix of contiguous and separate ranges."""
        ranges = [
            DateRange(start='2024-01-01', end='2024-01-03'),
            DateRange(start='2024-01-03', end='2024-01-05'),
            DateRange(start='2024-01-10', end='2024-01-12'),
            DateRange(start='2024-01-12', end='2024-01-14'),
        ]
        result = engine._batch_contiguous_ranges(ranges)
        assert result == [
            DateRange(start='2024-01-01', end='2024-01-05'),
            DateRange(start='2024-01-10', end='2024-01-14'),
        ]
