"""Unit tests for OpenAI connector retry logic with exponential backoff.

Tests cover Requirements 14.3, 14.4, 14.5, 14.6, 14.7.
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from http.client import HTTPResponse
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from connectors.openai_connector import (
    OpenAIConnector, MAX_RETRIES, DEFAULT_BACKOFF_BASE, NIGHTLY_SYNC_BACKOFF_BASE
)
from connectors.base_connector import CostRetrievalError


def _make_http_error(code, headers=None, msg='error'):
    """Create a urllib.error.HTTPError with optional headers."""
    import urllib.error
    resp_headers = MagicMock()
    if headers:
        resp_headers.get = lambda key, default=None: headers.get(key, default)
    else:
        resp_headers.get = lambda key, default=None: default
    err = urllib.error.HTTPError(
        url='https://api.openai.com/v1/usage',
        code=code,
        msg=msg,
        hdrs=resp_headers,
        fp=BytesIO(b'{}')
    )
    err.headers = resp_headers
    return err


class TestRetryOn429WithRetryAfter:
    """HTTP 429 with Retry-After header: wait specified duration, retry up to 3 times (Req 14.3)."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_429_with_retry_after_header_waits_and_retries(self, mock_urlopen, mock_sleep):
        """WHEN 429 with Retry-After=5, THEN wait 5s and retry."""
        # First call: 429 with Retry-After, second call: success
        mock_urlopen.side_effect = [
            _make_http_error(429, headers={'Retry-After': '5'}),
            MagicMock(read=lambda: b'{"data": [{"model": "gpt-4"}]}')
        ]
        connector = OpenAIConnector()
        result = connector.get_cost_data(
            {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
        )
        assert result == [{'model': 'gpt-4'}]
        mock_sleep.assert_called_once_with(5)

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_429_with_retry_after_exhausts_retries(self, mock_urlopen, mock_sleep):
        """WHEN 429 with Retry-After on all 3 attempts, THEN raise with mark_connection_failed."""
        mock_urlopen.side_effect = [
            _make_http_error(429, headers={'Retry-After': '2'}),
            _make_http_error(429, headers={'Retry-After': '2'}),
            _make_http_error(429, headers={'Retry-After': '2'}),
        ]
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert 'temporarily unavailable' in exc_info.value.message.lower()
        assert exc_info.value.mark_connection_failed is True
        # Should have slept twice (before attempt 2 and 3)
        assert mock_sleep.call_count == 2


class TestRetryOn429WithoutRetryAfter:
    """HTTP 429 without Retry-After: exponential backoff starting at 1s (Req 14.4)."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_429_no_header_uses_exponential_backoff(self, mock_urlopen, mock_sleep):
        """WHEN 429 without Retry-After, THEN use exponential backoff (1s, 2s)."""
        mock_urlopen.side_effect = [
            _make_http_error(429),
            _make_http_error(429),
            MagicMock(read=lambda: b'{"data": []}')
        ]
        connector = OpenAIConnector()
        result = connector.get_cost_data(
            {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
        )
        assert result == []
        # backoff: attempt 0 → 1*2^0=1s, attempt 1 → 1*2^1=2s
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_429_no_header_with_nightly_sync_base(self, mock_urlopen, mock_sleep):
        """WHEN 429 without Retry-After and base=2s, THEN backoff is 2s, 4s."""
        mock_urlopen.side_effect = [
            _make_http_error(429),
            _make_http_error(429),
            MagicMock(read=lambda: b'{"data": []}')
        ]
        connector = OpenAIConnector()
        result = connector.get_cost_data(
            {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31',
            retry_base_delay=NIGHTLY_SYNC_BACKOFF_BASE
        )
        assert result == []
        # backoff: attempt 0 → 2*2^0=2s, attempt 1 → 2*2^1=4s
        assert mock_sleep.call_args_list[0][0][0] == 2.0
        assert mock_sleep.call_args_list[1][0][0] == 4.0


class TestRetryOn5xx:
    """HTTP 5xx: retry up to 3 times with backoff (Req 14.5 partially)."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_500_retries_and_succeeds(self, mock_urlopen, mock_sleep):
        """WHEN 500 on first attempt then success, THEN returns data."""
        mock_urlopen.side_effect = [
            _make_http_error(500),
            MagicMock(read=lambda: b'{"data": [{"cost": 1.5}]}')
        ]
        connector = OpenAIConnector()
        result = connector.get_cost_data(
            {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
        )
        assert result == [{'cost': 1.5}]
        mock_sleep.assert_called_once_with(1.0)

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_502_exhausts_retries_marks_failed(self, mock_urlopen, mock_sleep):
        """WHEN 502 on all attempts, THEN raise with mark_connection_failed=True."""
        mock_urlopen.side_effect = [
            _make_http_error(502),
            _make_http_error(502),
            _make_http_error(502),
        ]
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert '502' in exc_info.value.message
        assert exc_info.value.mark_connection_failed is True

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_503_uses_exponential_backoff(self, mock_urlopen, mock_sleep):
        """WHEN 503 repeatedly, THEN delays follow exponential backoff."""
        mock_urlopen.side_effect = [
            _make_http_error(503),
            _make_http_error(503),
            _make_http_error(503),
        ]
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError):
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        # attempt 0 → 1s, attempt 1 → 2s (only 2 sleeps before final attempt)
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0


class TestNoRetryOn401:
    """HTTP 401: do NOT retry, raise key-revoked error (Req 14.6)."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_401_raises_immediately_no_retry(self, mock_urlopen, mock_sleep):
        """WHEN 401, THEN raise immediately without retrying."""
        mock_urlopen.side_effect = _make_http_error(401)
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert 'revoked' in exc_info.value.message.lower()
        assert exc_info.value.mark_connection_failed is True
        mock_sleep.assert_not_called()
        # Only one call to urlopen (no retries)
        assert mock_urlopen.call_count == 1


class TestNoRetryOnOtherErrors:
    """Other HTTP errors: return error with status code, don't change status (Req 14.7)."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_403_raises_immediately_status_unchanged(self, mock_urlopen, mock_sleep):
        """WHEN 403, THEN raise without retry and mark_connection_failed=False."""
        mock_urlopen.side_effect = _make_http_error(403)
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert '403' in exc_info.value.message
        assert exc_info.value.mark_connection_failed is False
        mock_sleep.assert_not_called()
        assert mock_urlopen.call_count == 1

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_400_raises_immediately_status_unchanged(self, mock_urlopen, mock_sleep):
        """WHEN 400, THEN raise without retry and mark_connection_failed=False."""
        mock_urlopen.side_effect = _make_http_error(400)
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert '400' in exc_info.value.message
        assert exc_info.value.mark_connection_failed is False
        mock_sleep.assert_not_called()

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_404_raises_immediately_status_unchanged(self, mock_urlopen, mock_sleep):
        """WHEN 404, THEN raise without retry and mark_connection_failed=False."""
        mock_urlopen.side_effect = _make_http_error(404)
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert '404' in exc_info.value.message
        assert exc_info.value.mark_connection_failed is False


class TestNetworkErrorRetry:
    """Network errors (URLError/OSError): retry with backoff, then mark failed."""

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_network_error_retries_then_marks_failed(self, mock_urlopen, mock_sleep):
        """WHEN network error on all attempts, THEN mark connection failed."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')
        connector = OpenAIConnector()
        with pytest.raises(CostRetrievalError) as exc_info:
            connector.get_cost_data(
                {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
            )
        assert 'temporarily unavailable' in exc_info.value.message.lower()
        assert exc_info.value.mark_connection_failed is True
        assert mock_urlopen.call_count == MAX_RETRIES

    @patch('connectors.openai_connector.time.sleep')
    @patch('connectors.openai_connector.urllib.request.urlopen')
    def test_network_error_then_success(self, mock_urlopen, mock_sleep):
        """WHEN network error then success, THEN returns data."""
        import urllib.error
        mock_urlopen.side_effect = [
            urllib.error.URLError('timeout'),
            MagicMock(read=lambda: b'{"results": [{"x": 1}]}')
        ]
        connector = OpenAIConnector()
        result = connector.get_cost_data(
            {'api_key': 'sk-org-' + 'x' * 40}, 'acc1', '2025-01-01', '2025-01-31'
        )
        assert result == [{'x': 1}]


class TestBackoffDelay:
    """Verify _backoff_delay calculation."""

    def test_default_base_backoff(self):
        """WHEN base=1.0, THEN delays are 1, 2, 4, 8..."""
        assert OpenAIConnector._backoff_delay(0) == 1.0
        assert OpenAIConnector._backoff_delay(1) == 2.0
        assert OpenAIConnector._backoff_delay(2) == 4.0

    def test_nightly_sync_base_backoff(self):
        """WHEN base=2.0, THEN delays are 2, 4, 8..."""
        assert OpenAIConnector._backoff_delay(0, base=2.0) == 2.0
        assert OpenAIConnector._backoff_delay(1, base=2.0) == 4.0
        assert OpenAIConnector._backoff_delay(2, base=2.0) == 8.0

    def test_custom_base_backoff(self):
        """WHEN base=0.5, THEN delays are 0.5, 1.0, 2.0..."""
        assert OpenAIConnector._backoff_delay(0, base=0.5) == 0.5
        assert OpenAIConnector._backoff_delay(1, base=0.5) == 1.0
        assert OpenAIConnector._backoff_delay(2, base=0.5) == 2.0


class TestConstants:
    """Verify module-level constants match requirements."""

    def test_max_retries_is_3(self):
        assert MAX_RETRIES == 3

    def test_default_backoff_base_is_1(self):
        assert DEFAULT_BACKOFF_BASE == 1.0

    def test_nightly_sync_backoff_base_is_2(self):
        assert NIGHTLY_SYNC_BACKOFF_BASE == 2.0
