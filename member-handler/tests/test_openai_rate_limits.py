"""Unit tests for openai_rate_limits module.

Tests rate limit data retrieval, utilization calculation, and warning logic.
"""
import json
import sys
import os
from unittest.mock import patch, MagicMock
from http.client import HTTPMessage
from io import BytesIO

import pytest

# Ensure module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_rate_limits import (
    get_rate_limit_utilization,
    _calculate_utilization,
    _should_warn,
    _parse_rate_limit_headers,
    _build_model_utilization,
    WARNING_THRESHOLD,
)


class TestCalculateUtilization:
    """Tests for _calculate_utilization."""

    def test_zero_limit_returns_zero(self):
        assert _calculate_utilization(0, 0) == 0.0

    def test_full_utilization(self):
        # limit=100, remaining=0 → 100% used
        assert _calculate_utilization(100, 0) == 100.0

    def test_no_utilization(self):
        # limit=100, remaining=100 → 0% used
        assert _calculate_utilization(100, 100) == 0.0

    def test_partial_utilization(self):
        # limit=500, remaining=100 → 400/500 = 80%
        assert _calculate_utilization(500, 100) == 80.0

    def test_high_utilization(self):
        # limit=1000, remaining=50 → 950/1000 = 95%
        assert _calculate_utilization(1000, 50) == 95.0

    def test_rounding(self):
        # limit=3, remaining=1 → 2/3 = 66.666... → 66.7
        assert _calculate_utilization(3, 1) == 66.7


class TestShouldWarn:
    """Tests for _should_warn — warning if utilization > 80%."""

    def test_below_threshold_no_warning(self):
        assert _should_warn(79.9) is False

    def test_exactly_at_threshold_no_warning(self):
        # 80% exactly should NOT trigger warning (> 80%, not >=)
        assert _should_warn(80.0) is False

    def test_above_threshold_warning(self):
        assert _should_warn(80.1) is True

    def test_zero_no_warning(self):
        assert _should_warn(0.0) is False

    def test_100_percent_warning(self):
        assert _should_warn(100.0) is True

    def test_just_above_threshold(self):
        assert _should_warn(80.01) is True


class TestParseRateLimitHeaders:
    """Tests for _parse_rate_limit_headers."""

    def test_all_headers_present(self):
        headers = {
            'x-ratelimit-limit-requests': '500',
            'x-ratelimit-remaining-requests': '450',
            'x-ratelimit-limit-tokens': '40000',
            'x-ratelimit-remaining-tokens': '35000',
        }
        result = _parse_rate_limit_headers(headers)
        assert result == {
            'rpm_limit': 500,
            'rpm_remaining': 450,
            'tpm_limit': 40000,
            'tpm_remaining': 35000,
        }

    def test_only_rpm_headers(self):
        headers = {
            'x-ratelimit-limit-requests': '100',
            'x-ratelimit-remaining-requests': '80',
        }
        result = _parse_rate_limit_headers(headers)
        assert result == {
            'rpm_limit': 100,
            'rpm_remaining': 80,
        }

    def test_only_tpm_headers(self):
        headers = {
            'x-ratelimit-limit-tokens': '10000',
            'x-ratelimit-remaining-tokens': '5000',
        }
        result = _parse_rate_limit_headers(headers)
        assert result == {
            'tpm_limit': 10000,
            'tpm_remaining': 5000,
        }

    def test_no_headers_returns_empty(self):
        headers = {'content-type': 'application/json'}
        result = _parse_rate_limit_headers(headers)
        assert result == {}

    def test_invalid_values_returns_empty(self):
        headers = {
            'x-ratelimit-limit-requests': 'abc',
            'x-ratelimit-remaining-requests': '50',
        }
        result = _parse_rate_limit_headers(headers)
        assert result == {}

    def test_missing_remaining_defaults_to_zero(self):
        headers = {
            'x-ratelimit-limit-requests': '500',
            # remaining not provided
            'x-ratelimit-limit-tokens': '40000',
        }
        result = _parse_rate_limit_headers(headers)
        assert result['rpm_limit'] == 500
        assert result['rpm_remaining'] == 0
        assert result['tpm_limit'] == 40000
        assert result['tpm_remaining'] == 0


class TestBuildModelUtilization:
    """Tests for _build_model_utilization."""

    def test_full_rate_data(self):
        rate_data = {
            'rpm_limit': 500,
            'rpm_remaining': 100,
            'tpm_limit': 40000,
            'tpm_remaining': 5000,
        }
        result = _build_model_utilization(rate_data, model_name='gpt-4')

        assert result['model'] == 'gpt-4'
        assert result['rpm_limit'] == 500
        assert result['rpm_current'] == 400
        assert result['rpm_utilization'] == 80.0
        assert result['tpm_limit'] == 40000
        assert result['tpm_current'] == 35000
        assert result['tpm_utilization'] == 87.5
        # TPM is 87.5% > 80% → warning
        assert result['warning'] is True

    def test_low_utilization_no_warning(self):
        rate_data = {
            'rpm_limit': 500,
            'rpm_remaining': 400,
            'tpm_limit': 40000,
            'tpm_remaining': 35000,
        }
        result = _build_model_utilization(rate_data, model_name='gpt-3.5-turbo')

        assert result['rpm_utilization'] == 20.0
        assert result['tpm_utilization'] == 12.5
        assert result['warning'] is False

    def test_rpm_only_with_warning(self):
        rate_data = {
            'rpm_limit': 100,
            'rpm_remaining': 10,
        }
        result = _build_model_utilization(rate_data, model_name='default')

        assert result['rpm_utilization'] == 90.0
        assert result['tpm_limit'] == 0
        assert result['tpm_utilization'] == 0.0
        assert result['warning'] is True

    def test_default_model_name(self):
        rate_data = {'rpm_limit': 100, 'rpm_remaining': 50}
        result = _build_model_utilization(rate_data)
        assert result['model'] == 'default'


class TestGetRateLimitUtilization:
    """Tests for the main get_rate_limit_utilization function."""

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_successful_retrieval_with_headers(self, mock_urlopen):
        """Rate limit data available in response headers."""
        mock_response = MagicMock()
        mock_response.headers = {
            'x-ratelimit-limit-requests': '500',
            'x-ratelimit-remaining-requests': '50',
            'x-ratelimit-limit-tokens': '40000',
            'x-ratelimit-remaining-tokens': '5000',
            'x-ratelimit-limit-requests-model': 'gpt-4',
        }
        mock_response.read.return_value = json.dumps({
            'data': [{'id': 'gpt-4'}, {'id': 'gpt-3.5-turbo'}]
        }).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        assert 'models' in result
        assert len(result['models']) >= 1
        model = result['models'][0]
        assert model['model'] == 'gpt-4'
        assert model['rpm_limit'] == 500
        assert model['rpm_current'] == 450
        assert model['rpm_utilization'] == 90.0
        assert model['tpm_limit'] == 40000
        assert model['tpm_current'] == 35000
        assert model['tpm_utilization'] == 87.5
        assert model['warning'] is True

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_no_rate_limit_headers_returns_unavailable(self, mock_urlopen):
        """No rate limit headers → unavailable message."""
        mock_response = MagicMock()
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.read.return_value = json.dumps({
            'data': [{'id': 'gpt-4'}]
        }).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is False
        assert 'unavailable' in result['message'].lower()

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_http_401_returns_unavailable(self, mock_urlopen):
        """401 error → unavailable with key error message."""
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.openai.com/v1/models',
            code=401,
            msg='Unauthorized',
            hdrs=MagicMock(get=lambda x: None),
            fp=BytesIO(b'')
        )
        mock_urlopen.side_effect = error

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is False
        assert 'invalid' in result['message'].lower() or 'revoked' in result['message'].lower()

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_http_429_returns_unavailable(self, mock_urlopen):
        """429 error without rate limit headers → unavailable."""
        import urllib.error
        mock_headers = MagicMock()
        mock_headers.get.return_value = None
        error = urllib.error.HTTPError(
            url='https://api.openai.com/v1/models',
            code=429,
            msg='Too Many Requests',
            hdrs=mock_headers,
            fp=BytesIO(b'')
        )
        mock_urlopen.side_effect = error

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is False
        assert 'rate limit' in result['message'].lower() or 'unavailable' in result['message'].lower()

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_network_error_returns_unavailable(self, mock_urlopen):
        """Network error → unavailable message."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError('Network unreachable')

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is False
        assert 'unavailable' in result['message'].lower()

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_warning_flag_at_exactly_80_no_warning(self, mock_urlopen):
        """Exactly 80% utilization should NOT trigger warning."""
        mock_response = MagicMock()
        mock_response.headers = {
            'x-ratelimit-limit-requests': '100',
            'x-ratelimit-remaining-requests': '20',  # 80% used — exactly at threshold
            'x-ratelimit-limit-tokens': '10000',
            'x-ratelimit-remaining-tokens': '5000',  # 50% used
        }
        mock_response.read.return_value = json.dumps({'data': []}).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        model = result['models'][0]
        assert model['rpm_utilization'] == 80.0
        assert model['warning'] is False  # 80% exactly is NOT > 80%

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_warning_flag_above_80(self, mock_urlopen):
        """Above 80% utilization SHOULD trigger warning."""
        mock_response = MagicMock()
        mock_response.headers = {
            'x-ratelimit-limit-requests': '100',
            'x-ratelimit-remaining-requests': '19',  # 81% used
            'x-ratelimit-limit-tokens': '10000',
            'x-ratelimit-remaining-tokens': '5000',  # 50% used
        }
        mock_response.read.return_value = json.dumps({'data': []}).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        model = result['models'][0]
        assert model['rpm_utilization'] == 81.0
        assert model['warning'] is True

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_http_error_with_rate_limit_headers_returns_data(self, mock_urlopen):
        """HTTP error but rate limit headers present → still return data."""
        import urllib.error

        # Create mock headers that return rate limit values
        class MockHeaders:
            _data = {
                'x-ratelimit-limit-requests': '200',
                'x-ratelimit-remaining-requests': '30',
                'x-ratelimit-limit-tokens': '20000',
                'x-ratelimit-remaining-tokens': '2000',
            }
            def get(self, key, default=None):
                return self._data.get(key, default)

        error = urllib.error.HTTPError(
            url='https://api.openai.com/v1/models',
            code=500,
            msg='Server Error',
            hdrs=MockHeaders(),
            fp=BytesIO(b'')
        )
        error.headers = MockHeaders()
        mock_urlopen.side_effect = error

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        model = result['models'][0]
        assert model['rpm_limit'] == 200
        assert model['rpm_current'] == 170
        assert model['tpm_limit'] == 20000
        assert model['tpm_current'] == 18000
        assert model['warning'] is True  # 85% RPM and 90% TPM

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_model_tier_from_header(self, mock_urlopen):
        """Model tier name comes from x-ratelimit-limit-requests-model header."""
        mock_response = MagicMock()
        mock_response.headers = {
            'x-ratelimit-limit-requests': '500',
            'x-ratelimit-remaining-requests': '400',
            'x-ratelimit-limit-tokens': '40000',
            'x-ratelimit-remaining-tokens': '35000',
            'x-ratelimit-limit-requests-model': 'gpt-4o',
        }
        mock_response.read.return_value = json.dumps({'data': []}).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        assert result['models'][0]['model'] == 'gpt-4o'

    @patch('openai_rate_limits.urllib.request.urlopen')
    def test_no_model_header_defaults_to_account_level(self, mock_urlopen):
        """Without model header, default to 'account-level' label."""
        mock_response = MagicMock()
        mock_response.headers = {
            'x-ratelimit-limit-requests': '500',
            'x-ratelimit-remaining-requests': '400',
            'x-ratelimit-limit-tokens': '40000',
            'x-ratelimit-remaining-tokens': '35000',
        }
        mock_response.read.return_value = json.dumps({'data': []}).encode('utf-8')
        mock_urlopen.return_value = mock_response

        result = get_rate_limit_utilization('sk-org-test1234567890abcdefghijklmnopqrst')

        assert result['available'] is True
        assert result['models'][0]['model'] == 'account-level'
