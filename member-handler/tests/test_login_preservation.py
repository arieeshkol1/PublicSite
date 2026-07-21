"""
Preservation Tests for Login 500 Error Bugfix.

These tests capture the EXISTING correct behavior that must NOT regress.
They test paths NOT affected by the bug, so they PASS on both unfixed and fixed code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Includes both unit tests (one per case) and property-based tests using hypothesis
that generate random email/password combinations and verify response patterns.
"""

import sys
import os
import json
import importlib.abc
import importlib.machinery
import importlib.util
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAMBDA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'lambda_function.py'
)


class _FixedEncodingLoader(importlib.abc.Loader):
    """Loader that handles non-UTF-8 bytes in source files."""

    def __init__(self, path):
        self.path = path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        with open(self.path, 'rb') as f:
            raw = f.read()
        source = raw.decode('utf-8', errors='replace')
        code = compile(source, self.path, 'exec')
        exec(code, module.__dict__)


def _load_lambda_module():
    """Load lambda_function.py with encoding error handling."""
    if 'lambda_function' in sys.modules:
        del sys.modules['lambda_function']
    spec = importlib.machinery.ModuleSpec(
        'lambda_function', _FixedEncodingLoader(LAMBDA_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules['lambda_function'] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_cognito_mock():
    """Create a mock cognito client with proper exception classes."""
    mock_exceptions = MagicMock()
    mock_exceptions.NotAuthorizedException = type(
        'NotAuthorizedException', (ClientError,), {}
    )
    mock_exceptions.UserNotFoundException = type(
        'UserNotFoundException', (ClientError,), {}
    )
    mock_exceptions.UserNotConfirmedException = type(
        'UserNotConfirmedException', (ClientError,), {}
    )
    mock_exceptions.InvalidParameterException = type(
        'InvalidParameterException', (ClientError,), {}
    )
    mock_cognito = MagicMock()
    mock_cognito.exceptions = mock_exceptions
    return mock_cognito


@pytest.fixture
def mod():
    """Load the lambda module fresh for each test."""
    m = _load_lambda_module()
    yield m
    if 'lambda_function' in sys.modules:
        del sys.modules['lambda_function']


# ---------------------------------------------------------------------------
# Test Case 1: Wrong password -> 401 "Invalid email or password"
# Validates: Requirement 3.1
# ---------------------------------------------------------------------------

def test_wrong_password_returns_401(mod):
    """**Validates: Requirements 3.1**"""
    mock_cognito = _make_cognito_mock()
    error_response = {'Error': {'Code': 'NotAuthorizedException', 'Message': 'Incorrect username or password.'}}
    mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.NotAuthorizedException(
        error_response, 'InitiateAuth'
    )
    mod.cognito_client = mock_cognito
    mod.COGNITO_CLIENT_ID = 'test-client-id'

    event = {'body': json.dumps({'email': 'user@example.com', 'password': 'WrongPass123!'})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert body['error'] == 'AuthError'
    assert body['message'] == 'Invalid email or password'


# ---------------------------------------------------------------------------
# Test Case 2: Empty email/password -> 400 "Email and password are required"
# Validates: Requirement 3.2
# ---------------------------------------------------------------------------

def test_empty_email_returns_400(mod):
    """**Validates: Requirements 3.2**"""
    event = {'body': json.dumps({'email': '', 'password': 'SomePass123!'})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert body['error'] == 'InvalidRequest'
    assert body['message'] == 'Email and password are required'


# ---------------------------------------------------------------------------
# Test Case 3: UserNotConfirmedException -> 401 "Please verify your email..."
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

def test_unconfirmed_user_returns_401(mod):
    """**Validates: Requirements 3.3**"""
    mock_cognito = _make_cognito_mock()
    error_response = {'Error': {'Code': 'UserNotConfirmedException', 'Message': 'User is not confirmed.'}}
    mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.UserNotConfirmedException(
        error_response, 'InitiateAuth'
    )
    mod.cognito_client = mock_cognito
    mod.COGNITO_CLIENT_ID = 'test-client-id'

    event = {'body': json.dumps({'email': 'unconfirmed@example.com', 'password': 'ValidPass123!'})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert body['error'] == 'AuthError'
    assert body['message'] == 'Please verify your email before logging in'


# ---------------------------------------------------------------------------
# Test Case 4: No COGNITO_CLIENT_ID, valid DynamoDB creds -> 200 with token
# Validates: Requirements 3.4, 3.5
# ---------------------------------------------------------------------------

def test_legacy_login_success_returns_200(mod):
    """**Validates: Requirements 3.4, 3.5**"""
    import bcrypt as bcrypt_lib

    email = "member@example.com"
    password = "CorrectPassword123!"
    password_hash = bcrypt_lib.hashpw(password.encode('utf-8'), bcrypt_lib.gensalt()).decode('utf-8')

    mod.COGNITO_CLIENT_ID = ''

    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        'Item': {'email': email, 'passwordHash': password_hash, 'displayName': 'John'}
    }
    mock_table.update_item.return_value = {}
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mod.dynamodb = mock_dynamodb

    event = {'body': json.dumps({'email': email, 'password': password})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'token' in body
    assert body['email'] == email
    assert body['displayName'] == 'John'


# ---------------------------------------------------------------------------
# Test Case 5: Valid Cognito login -> 200 with token
# Validates: Requirement 3.5
# ---------------------------------------------------------------------------

def test_cognito_login_success_returns_200(mod):
    """**Validates: Requirements 3.5**"""
    mock_cognito = _make_cognito_mock()
    mock_cognito.initiate_auth.return_value = {
        'AuthenticationResult': {
            'AccessToken': 'test-access-token',
            'RefreshToken': 'test-refresh-token',
        }
    }
    mod.cognito_client = mock_cognito
    mod.COGNITO_CLIENT_ID = 'test-client-id'

    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        'Item': {'email': 'user@example.com', 'displayName': 'TestUser', 'tier': 'pro'}
    }
    mock_table.update_item.return_value = {}
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mod.dynamodb = mock_dynamodb

    event = {'body': json.dumps({'email': 'user@example.com', 'password': 'ValidPass123!'})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['token'] == 'test-access-token'
    assert body['email'] == 'user@example.com'
    assert body['displayName'] == 'TestUser'


# ===========================================================================
# Property-Based Tests using Hypothesis
# ===========================================================================
# These tests generate random email/password combinations and verify that
# the response patterns match the observed behavior on UNFIXED code.
# ===========================================================================

# Strategies for generating inputs
_empty_or_whitespace = st.sampled_from(['', ' ', '  ', '\t', '\n', '   \t\n'])
_valid_email_local = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789._+-'),
    min_size=1, max_size=20
)
_valid_email_domain = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789.-'),
    min_size=3, max_size=15
)
_valid_email = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    _valid_email_local, _valid_email_domain
)
_non_empty_password = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != '')
_special_chars_password = st.text(
    alphabet=st.sampled_from('!@#$%^&*()_+-=[]{}|;:,.<>?/~`'),
    min_size=1, max_size=30
)


class TestPreservationProperties:
    """Property-based tests verifying login behavior is preserved across all input types.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    def _get_module(self):
        """Load a fresh lambda module for testing."""
        return _load_lambda_module()

    # -----------------------------------------------------------------------
    # Property: Missing fields always return 400 with InvalidRequest
    # Validates: Requirement 3.2
    # -----------------------------------------------------------------------

    @given(password=st.text(max_size=50))
    @settings(max_examples=10, deadline=10000)
    def test_empty_email_always_returns_400(self, password):
        """**Validates: Requirements 3.2**

        For any password value, an empty email must return 400 InvalidRequest.
        """
        mod = self._get_module()
        event = {'body': json.dumps({'email': '', 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'InvalidRequest'
        assert body['message'] == 'Email and password are required'

    @given(email=st.text(min_size=0, max_size=50))
    @settings(max_examples=10, deadline=10000)
    def test_empty_password_always_returns_400(self, email):
        """**Validates: Requirements 3.2**

        For any email value, an empty password must return 400 InvalidRequest.
        """
        mod = self._get_module()
        event = {'body': json.dumps({'email': email, 'password': ''})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'InvalidRequest'
        assert body['message'] == 'Email and password are required'

    @given(
        email=_empty_or_whitespace,
        password=_empty_or_whitespace
    )
    @settings(max_examples=10, deadline=10000)
    def test_whitespace_only_fields_return_400(self, email, password):
        """**Validates: Requirements 3.2**

        Whitespace-only values for both email and password should return 400.
        """
        mod = self._get_module()
        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'InvalidRequest'
        assert body['message'] == 'Email and password are required'

    # -----------------------------------------------------------------------
    # Property: Wrong credentials (NotAuthorizedException) always return 401
    # Validates: Requirement 3.1
    # -----------------------------------------------------------------------

    @given(
        email=_valid_email,
        password=_non_empty_password
    )
    @settings(max_examples=10, deadline=10000)
    def test_wrong_password_always_returns_401(self, email, password):
        """**Validates: Requirements 3.1**

        For any valid email format and non-empty password, when Cognito raises
        NotAuthorizedException, the response must be 401 with AuthError.
        """
        mod = self._get_module()

        mock_cognito = _make_cognito_mock()
        error_response = {
            'Error': {'Code': 'NotAuthorizedException', 'Message': 'Incorrect username or password.'}
        }
        mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.NotAuthorizedException(
            error_response, 'InitiateAuth'
        )
        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'AuthError'
        assert body['message'] == 'Invalid email or password'

    @given(
        email=_valid_email,
        password=_special_chars_password
    )
    @settings(max_examples=10, deadline=10000)
    def test_special_char_password_wrong_creds_returns_401(self, email, password):
        """**Validates: Requirements 3.1**

        Passwords with special characters still get proper 401 when wrong.
        """
        mod = self._get_module()

        mock_cognito = _make_cognito_mock()
        error_response = {
            'Error': {'Code': 'NotAuthorizedException', 'Message': 'Incorrect username or password.'}
        }
        mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.NotAuthorizedException(
            error_response, 'InitiateAuth'
        )
        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'AuthError'
        assert body['message'] == 'Invalid email or password'

    # -----------------------------------------------------------------------
    # Property: Unconfirmed user always returns 401 with verify message
    # Validates: Requirement 3.3
    # -----------------------------------------------------------------------

    @given(
        email=_valid_email,
        password=_non_empty_password
    )
    @settings(max_examples=10, deadline=10000)
    def test_unconfirmed_user_always_returns_401(self, email, password):
        """**Validates: Requirements 3.3**

        For any valid credentials where Cognito raises UserNotConfirmedException,
        the response must be 401 with the verify email message.
        """
        mod = self._get_module()

        mock_cognito = _make_cognito_mock()
        error_response = {
            'Error': {'Code': 'UserNotConfirmedException', 'Message': 'User is not confirmed.'}
        }
        mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.UserNotConfirmedException(
            error_response, 'InitiateAuth'
        )
        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'AuthError'
        assert body['message'] == 'Please verify your email before logging in'

    # -----------------------------------------------------------------------
    # Property: Successful Cognito login returns 200 with token structure
    # Validates: Requirement 3.5
    # -----------------------------------------------------------------------

    @given(
        email=_valid_email,
        password=_non_empty_password,
        display_name=st.text(min_size=1, max_size=20, alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz')),
        tier=st.sampled_from(['free', 'pro', 'enterprise'])
    )
    @settings(max_examples=10, deadline=10000)
    def test_successful_cognito_login_returns_200_with_structure(self, email, password, display_name, tier):
        """**Validates: Requirements 3.5**

        For any valid credentials where Cognito succeeds, the response must be 200
        with token, refreshToken, email, displayName, tier, and tierLimit.
        """
        mod = self._get_module()

        mock_cognito = _make_cognito_mock()
        mock_cognito.initiate_auth.return_value = {
            'AuthenticationResult': {
                'AccessToken': 'test-access-token-xyz',
                'RefreshToken': 'test-refresh-token-xyz',
            }
        }
        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'email': email, 'displayName': display_name, 'tier': tier}
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mod.dynamodb = mock_dynamodb

        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'token' in body
        assert 'refreshToken' in body
        assert body['email'] == email.strip().lower()
        assert body['displayName'] == display_name
        assert body['tier'] == tier
        assert 'tierLimit' in body

    # -----------------------------------------------------------------------
    # Property: Legacy DynamoDB login returns 200 with token when no Cognito
    # Validates: Requirements 3.4, 3.5
    # -----------------------------------------------------------------------

    @given(
        email=_valid_email,
        display_name=st.text(min_size=1, max_size=20, alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz'))
    )
    @settings(max_examples=10, deadline=10000)
    def test_legacy_login_returns_200_with_token(self, email, display_name):
        """**Validates: Requirements 3.4, 3.5**

        When COGNITO_CLIENT_ID is empty, valid DynamoDB credentials must return
        200 with token, email, and displayName.
        """
        import bcrypt as bcrypt_lib

        mod = self._get_module()
        password = "TestPassword123!"
        password_hash = bcrypt_lib.hashpw(password.encode('utf-8'), bcrypt_lib.gensalt()).decode('utf-8')

        mod.COGNITO_CLIENT_ID = ''

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'email': email, 'passwordHash': password_hash, 'displayName': display_name}
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mod.dynamodb = mock_dynamodb

        event = {'body': json.dumps({'email': email, 'password': password})}
        response = mod.handle_login(event)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'token' in body
        assert body['email'] == email.strip().lower()
        assert body['displayName'] == display_name
