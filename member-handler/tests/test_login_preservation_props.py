"""
Property-Based Preservation Tests for Login 500 Error Bugfix.

These tests use hypothesis to generate random email/password combinations
and verify the response matches expected patterns for existing login paths
that are NOT affected by the bug.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Expected Outcome: All tests PASS on unfixed code (these paths are unaffected by the bug).
"""

import sys
import os
import json
import importlib.abc
import importlib.machinery
import importlib.util
from unittest.mock import MagicMock

import pytest
from hypothesis import given, assume, settings, HealthCheck, Verbosity
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


# ---------------------------------------------------------------------------
# Strategies for generating login inputs
# ---------------------------------------------------------------------------

# Emails that are effectively empty after strip().lower()
empty_emails = st.one_of(
    st.just(''),
    st.text(alphabet=' \t\n\r', min_size=1, max_size=10),
)

# Passwords that are empty (falsy)
empty_passwords = st.just('')

# Valid-format email addresses
valid_emails = st.from_regex(
    r'^[a-z][a-z0-9]{0,20}@[a-z]{2,10}\.[a-z]{2,5}$', fullmatch=True
)

# Non-empty passwords (any printable characters, limited to 72 bytes for bcrypt compatibility)
non_empty_passwords = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S'), max_codepoint=127),
    min_size=1,
    max_size=50,
)


# ---------------------------------------------------------------------------
# Module-level fixture (loaded once for all property tests)
# ---------------------------------------------------------------------------

_mod_cache = None


def _get_mod():
    """Get or load the lambda module (cached for performance)."""
    global _mod_cache
    if _mod_cache is None:
        _mod_cache = _load_lambda_module()
    return _mod_cache


# ---------------------------------------------------------------------------
# Property 1: Missing Fields -> 400
# For ALL inputs where email is empty OR password is empty,
# handle_login returns 400 with "Email and password are required"
#
# **Validates: Requirements 3.2**
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=st.one_of(empty_emails, valid_emails),
    password=st.one_of(empty_passwords, non_empty_passwords),
)
def test_missing_fields_returns_400(email, password):
    """**Validates: Requirements 3.2**

    Property: For any email/password combination where at least one is
    empty (after stripping), handle_login returns 400 with InvalidRequest.
    """
    # Only test cases where email or password is effectively empty
    stripped_email = (email or '').strip().lower()
    assume(not stripped_email or not password)

    mod = _get_mod()
    event = {'body': json.dumps({'email': email, 'password': password})}
    response = mod.handle_login(event)

    assert response['statusCode'] == 400, (
        f"Expected 400 for empty fields, got {response['statusCode']}. "
        f"email={repr(email)}, password={repr(password)}"
    )
    body = json.loads(response['body'])
    assert body['error'] == 'InvalidRequest'
    assert body['message'] == 'Email and password are required'


# ---------------------------------------------------------------------------
# Property 2: Wrong Password (Cognito NotAuthorizedException) -> 401
# For ALL non-empty email/password where Cognito rejects credentials,
# handle_login returns 401 with "Invalid email or password"
#
# **Validates: Requirements 3.1**
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=valid_emails,
    password=non_empty_passwords,
)
def test_wrong_password_returns_401(email, password):
    """**Validates: Requirements 3.1**

    Property: For any non-empty email/password combination where Cognito raises
    NotAuthorizedException, handle_login returns 401 with AuthError.
    """
    mod = _get_mod()

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

    assert response['statusCode'] == 401, (
        f"Expected 401 for wrong password, got {response['statusCode']}. "
        f"email={repr(email)}, password={repr(password)}"
    )
    body = json.loads(response['body'])
    assert body['error'] == 'AuthError'
    assert body['message'] == 'Invalid email or password'


# ---------------------------------------------------------------------------
# Property 3: UserNotConfirmedException -> 401 with verify message
# For ALL non-empty email/password where Cognito raises UserNotConfirmedException,
# handle_login returns 401 with "Please verify your email before logging in"
#
# **Validates: Requirements 3.3**
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=valid_emails,
    password=non_empty_passwords,
)
def test_unconfirmed_user_returns_401(email, password):
    """**Validates: Requirements 3.3**

    Property: For any non-empty email/password combination where Cognito raises
    UserNotConfirmedException, handle_login returns 401 with verify message.
    """
    mod = _get_mod()

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

    assert response['statusCode'] == 401, (
        f"Expected 401 for unconfirmed user, got {response['statusCode']}. "
        f"email={repr(email)}, password={repr(password)}"
    )
    body = json.loads(response['body'])
    assert body['error'] == 'AuthError'
    assert body['message'] == 'Please verify your email before logging in'


# ---------------------------------------------------------------------------
# Property 4: Legacy DynamoDB fallback with valid credentials -> 200
# When COGNITO_CLIENT_ID is not set and DynamoDB returns valid member,
# handle_login returns 200 with token, email, displayName
#
# **Validates: Requirements 3.4, 3.5**
# ---------------------------------------------------------------------------

@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=valid_emails,
    password=non_empty_passwords,
    display_name=st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
        min_size=1,
        max_size=30,
    ),
)
def test_legacy_login_success_returns_200(email, password, display_name):
    """**Validates: Requirements 3.4, 3.5**

    Property: For any non-empty email/password where COGNITO_CLIENT_ID is empty
    and DynamoDB has a valid member record with matching bcrypt hash,
    handle_login returns 200 with token, email, and displayName.
    """
    import bcrypt as bcrypt_lib

    mod = _get_mod()

    password_hash = bcrypt_lib.hashpw(
        password.encode('utf-8'), bcrypt_lib.gensalt()
    ).decode('utf-8')

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

    assert response['statusCode'] == 200, (
        f"Expected 200 for legacy login success, got {response['statusCode']}. "
        f"email={repr(email)}"
    )
    body = json.loads(response['body'])
    assert 'token' in body, "Response must contain a token"
    assert body['email'] == email.strip().lower()
    assert body['displayName'] == display_name


# ---------------------------------------------------------------------------
# Property 5: Cognito successful login -> 200 with token details
# When COGNITO_CLIENT_ID is set and Cognito returns AuthenticationResult,
# handle_login returns 200 with token, email, displayName, tier, tierLimit
#
# **Validates: Requirements 3.5**
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    email=valid_emails,
    password=non_empty_passwords,
    display_name=st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'Zs')),
        min_size=1,
        max_size=30,
    ),
    tier=st.sampled_from(['free', 'growth', 'scale']),
)
def test_cognito_success_returns_200(email, password, display_name, tier):
    """**Validates: Requirements 3.5**

    Property: For any non-empty email/password where Cognito authentication
    succeeds, handle_login returns 200 with token, email, displayName, tier.
    """
    mod = _get_mod()

    mock_cognito = _make_cognito_mock()
    mock_cognito.initiate_auth.return_value = {
        'AuthenticationResult': {
            'AccessToken': 'mock-access-token-xyz',
            'RefreshToken': 'mock-refresh-token-abc',
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

    assert response['statusCode'] == 200, (
        f"Expected 200 for Cognito success, got {response['statusCode']}. "
        f"email={repr(email)}"
    )
    body = json.loads(response['body'])
    assert body['token'] == 'mock-access-token-xyz'
    assert body['refreshToken'] == 'mock-refresh-token-abc'
    assert body['email'] == email.strip().lower()
    assert body['displayName'] == display_name
    assert body['tier'] == tier
    assert 'tierLimit' in body
