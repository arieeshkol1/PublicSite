"""
Preservation Tests for Login 500 Error Bugfix.

These tests capture the EXISTING correct behavior that must NOT regress.
They test paths NOT affected by the bug, so they PASS on both unfixed and fixed code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Simple unit tests - one per case, no parameterization.
"""

import sys
import os
import json
import importlib.abc
import importlib.machinery
import importlib.util
from unittest.mock import MagicMock

import pytest
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
