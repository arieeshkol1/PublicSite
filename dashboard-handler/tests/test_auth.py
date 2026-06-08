"""Unit tests for dashboard-handler/auth.py.

Tests JWT validation, token extraction, JWKS caching, and error handling
for the authentication middleware.
"""

import time
from unittest.mock import patch, MagicMock

import pytest
from jose import jwt

# We need to patch env vars before importing auth
import os

os.environ['COGNITO_USER_POOL_ID'] = 'us-east-1_TestPool123'
os.environ['COGNITO_REGION'] = 'us-east-1'

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from auth import (
    extract_token,
    verify_jwt,
    _get_jwks,
    COGNITO_ISSUER,
    JWKS_CACHE_TTL,
)
import auth


# --- Fixtures and helpers ---

FAKE_KID = 'test-key-id-1'
FAKE_RSA_KEY = {
    'kid': FAKE_KID,
    'kty': 'RSA',
    'alg': 'RS256',
    'use': 'sig',
    'n': 'test-n-value',
    'e': 'AQAB',
}

FAKE_JWKS = {'keys': [FAKE_RSA_KEY]}


def make_event(token=None, header_key='Authorization'):
    """Create a mock API Gateway event with optional auth header."""
    headers = {}
    if token is not None:
        headers[header_key] = f'Bearer {token}'
    return {'headers': headers}


# --- Tests for extract_token ---

class TestExtractToken:
    def test_valid_bearer_token(self):
        event = make_event('my-jwt-token')
        assert extract_token(event) == 'my-jwt-token'

    def test_lowercase_authorization_header(self):
        event = {'headers': {'authorization': 'Bearer lowercase-token'}}
        assert extract_token(event) == 'lowercase-token'

    def test_missing_authorization_header(self):
        event = {'headers': {}}
        assert extract_token(event) is None

    def test_no_headers_key(self):
        event = {}
        assert extract_token(event) is None

    def test_null_headers(self):
        event = {'headers': None}
        assert extract_token(event) is None

    def test_no_bearer_prefix(self):
        event = {'headers': {'Authorization': 'Basic abc123'}}
        assert extract_token(event) is None

    def test_empty_authorization_header(self):
        event = {'headers': {'Authorization': ''}}
        assert extract_token(event) is None

    def test_bearer_with_empty_token(self):
        event = {'headers': {'Authorization': 'Bearer '}}
        # "Bearer " with trailing space, token is empty string
        result = extract_token(event)
        assert result == ''


# --- Tests for verify_jwt ---

class TestVerifyJwt:
    def test_none_token_returns_401(self):
        result = verify_jwt(None)
        assert result['error'] == 'Authentication required'
        assert result['status_code'] == 401

    def test_empty_string_token_returns_401(self):
        # Empty string is falsy, so treated same as None
        result = verify_jwt('')
        assert result['error'] == 'Authentication required'
        assert result['status_code'] == 401

    @patch.dict(os.environ, {'COGNITO_USER_POOL_ID': ''})
    def test_unconfigured_user_pool_returns_503(self):
        """When COGNITO_USER_POOL_ID is empty, returns 503."""
        # Need to reload module to pick up empty env var
        import importlib
        original_pool_id = auth.COGNITO_USER_POOL_ID
        auth.COGNITO_USER_POOL_ID = ''
        try:
            result = verify_jwt('some-token')
            assert result['error'] == 'Authentication service not configured'
            assert result['status_code'] == 503
        finally:
            auth.COGNITO_USER_POOL_ID = original_pool_id

    @patch('auth._get_jwks')
    def test_jwks_unavailable_returns_503(self, mock_get_jwks):
        """When JWKS cannot be fetched, returns 503."""
        mock_get_jwks.return_value = None
        result = verify_jwt('some-token')
        assert result['error'] == 'Authentication service unavailable'
        assert result['status_code'] == 503

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    def test_no_matching_kid_returns_401(self, mock_header, mock_get_jwks):
        """When token kid doesn't match any JWKS key, returns 401."""
        mock_get_jwks.return_value = {'keys': [{'kid': 'other-key'}]}
        mock_header.return_value = {'kid': 'unknown-kid'}

        result = verify_jwt('some-token')
        assert result['error'] == 'Invalid token signature'
        assert result['status_code'] == 401

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_valid_token_returns_email(self, mock_decode, mock_header, mock_get_jwks):
        """A valid token with email claim returns the email."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'email': 'user@example.com', 'sub': 'sub-123'}

        result = verify_jwt('valid-token')
        assert result == {'email': 'user@example.com'}

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_valid_token_email_lowercased(self, mock_decode, mock_header, mock_get_jwks):
        """Email is normalized to lowercase."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'email': 'User@Example.COM'}

        result = verify_jwt('valid-token')
        assert result == {'email': 'user@example.com'}

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_fallback_to_username_claim(self, mock_decode, mock_header, mock_get_jwks):
        """When email claim missing, falls back to username."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'username': 'testuser', 'sub': 'sub-123'}

        result = verify_jwt('valid-token')
        assert result == {'email': 'testuser'}

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_fallback_to_sub_claim(self, mock_decode, mock_header, mock_get_jwks):
        """When email and username missing, falls back to sub."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'sub': 'sub-12345'}

        result = verify_jwt('valid-token')
        assert result == {'email': 'sub-12345'}

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_no_email_claims_returns_401(self, mock_decode, mock_header, mock_get_jwks):
        """When no identifiable claims exist, returns 401."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'sub': '', 'iss': 'some-issuer'}

        result = verify_jwt('valid-token')
        assert result['error'] == 'Token missing email claim'
        assert result['status_code'] == 401

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_expired_token_returns_specific_error(self, mock_decode, mock_header, mock_get_jwks):
        """Expired tokens get a specific error message distinguishing from other failures."""
        from jose import ExpiredSignatureError
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.side_effect = ExpiredSignatureError('Token expired')

        result = verify_jwt('expired-token')
        assert result['error'] == 'Token has expired'
        assert result['status_code'] == 401

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_jwt_error_returns_invalid_token(self, mock_decode, mock_header, mock_get_jwks):
        """General JWT errors return 'Invalid token'."""
        from jose import JWTError
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.side_effect = JWTError('Bad signature')

        result = verify_jwt('bad-token')
        assert result['error'] == 'Invalid token'
        assert result['status_code'] == 401

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    def test_unexpected_exception_returns_503(self, mock_header, mock_get_jwks):
        """Unexpected exceptions (network, etc.) return 503."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.side_effect = Exception('Network failure')

        result = verify_jwt('some-token')
        assert result['error'] == 'Authentication service unavailable'
        assert result['status_code'] == 503

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_decode_called_with_correct_params(self, mock_decode, mock_header, mock_get_jwks):
        """Verify jwt.decode is called with RS256 algorithm and correct issuer."""
        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}
        mock_decode.return_value = {'email': 'test@test.com'}

        verify_jwt('test-token')

        mock_decode.assert_called_once_with(
            'test-token',
            FAKE_RSA_KEY,
            algorithms=['RS256'],
            issuer=COGNITO_ISSUER,
            options={'verify_aud': False}
        )


# --- Tests for _get_jwks ---

class TestGetJwks:
    def setup_method(self):
        """Reset JWKS cache before each test."""
        auth._jwks_cache = None
        auth._jwks_cache_time = 0

    @patch('auth.requests.get')
    def test_fetches_jwks_on_first_call(self, mock_get):
        """First call fetches from network."""
        mock_response = MagicMock()
        mock_response.json.return_value = FAKE_JWKS
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _get_jwks()
        assert result == FAKE_JWKS
        mock_get.assert_called_once()

    @patch('auth.requests.get')
    def test_returns_cached_jwks_within_ttl(self, mock_get):
        """Subsequent calls within TTL use cache."""
        auth._jwks_cache = FAKE_JWKS
        auth._jwks_cache_time = time.time()

        result = _get_jwks()
        assert result == FAKE_JWKS
        mock_get.assert_not_called()

    @patch('auth.requests.get')
    def test_refetches_after_ttl_expires(self, mock_get):
        """After TTL, cache is refreshed."""
        auth._jwks_cache = FAKE_JWKS
        auth._jwks_cache_time = time.time() - JWKS_CACHE_TTL - 1

        new_jwks = {'keys': [{'kid': 'new-key'}]}
        mock_response = MagicMock()
        mock_response.json.return_value = new_jwks
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = _get_jwks()
        assert result == new_jwks
        mock_get.assert_called_once()

    @patch('auth.requests.get')
    def test_network_error_returns_none(self, mock_get):
        """Network failures return None (triggers 503 in verify_jwt)."""
        mock_get.side_effect = Exception('Connection timeout')

        result = _get_jwks()
        assert result is None

    @patch('auth.requests.get')
    def test_timeout_set_to_5_seconds(self, mock_get):
        """JWKS fetch uses 5 second timeout (Requirement 8.6)."""
        mock_response = MagicMock()
        mock_response.json.return_value = FAKE_JWKS
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        _get_jwks()
        mock_get.assert_called_once_with(auth.JWKS_URL, timeout=5)

    @patch('auth.requests.get')
    def test_http_error_returns_none(self, mock_get):
        """HTTP errors (4xx/5xx) from Cognito return None."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception('HTTP 500')
        mock_get.return_value = mock_response

        result = _get_jwks()
        assert result is None


# --- Integration-style tests with lambda_function patterns ---

class TestAuthIntegration:
    """Tests verifying auth behavior in the context of the lambda handler flow."""

    def test_missing_auth_header_returns_401(self):
        """No Authorization header → 401."""
        event = {'headers': {}}
        token = extract_token(event)
        result = verify_jwt(token)
        assert result['status_code'] == 401
        assert 'Authentication required' in result['error']

    def test_invalid_bearer_format_returns_401(self):
        """Non-Bearer token format → returns None token → 401."""
        event = {'headers': {'Authorization': 'Token abc123'}}
        token = extract_token(event)
        assert token is None
        result = verify_jwt(token)
        assert result['status_code'] == 401

    @patch('auth._get_jwks')
    @patch('auth.jwt.get_unverified_header')
    @patch('auth.jwt.decode')
    def test_expired_vs_invalid_distinction(self, mock_decode, mock_header, mock_get_jwks):
        """Requirement 11.1: Frontend can distinguish expiry from other failures."""
        from jose import ExpiredSignatureError, JWTError

        mock_get_jwks.return_value = FAKE_JWKS
        mock_header.return_value = {'kid': FAKE_KID}

        # Expired token
        mock_decode.side_effect = ExpiredSignatureError('expired')
        expired_result = verify_jwt('expired-token')

        # Invalid token
        mock_decode.side_effect = JWTError('bad signature')
        invalid_result = verify_jwt('invalid-token')

        # The error messages must be distinguishable
        assert expired_result['error'] != invalid_result['error']
        assert 'expired' in expired_result['error'].lower()
        assert expired_result['status_code'] == 401
        assert invalid_result['status_code'] == 401
