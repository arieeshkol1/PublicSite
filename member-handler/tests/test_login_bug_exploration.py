"""
Bug Condition Exploration Tests for Login 500 Error.

These tests encode the EXPECTED (correct) behavior after the fix.
They are expected to FAIL on unfixed code - failure confirms the bug exists.

**Validates: Requirements 1.1, 1.2, 1.3**

Test Cases:
A) Import with missing optional module - Lambda should load without ModuleNotFoundError
B) Cognito InvalidParameterException - should return structured AuthConfigError response
C) Generic ClientError - should log full traceback (not just exception string)
"""

import sys
import os
import json
import importlib.abc
import importlib.machinery
import importlib.util
import logging
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Helper: Custom module loader to handle encoding issues in lambda_function.py
# The file contains non-UTF-8 bytes (emoji surrogates) that prevent normal import.
# ---------------------------------------------------------------------------

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


class TestImportFailureResilience:
    """Test Case A: Lambda loads successfully even when optional modules are missing.

    **Validates: Requirements 1.1**

    Bug condition: When provider_registry (or any optional module) is missing,
    the Lambda crashes with ModuleNotFoundError before any handler executes.

    Expected behavior (after fix): Lambda loads successfully, login endpoint
    functions independently of optional modules.
    """

    def test_lambda_loads_without_provider_registry(self):
        """Import lambda_function with provider_registry unavailable.

        EXPECTED: Lambda loads WITHOUT raising ModuleNotFoundError.
        ON UNFIXED CODE: This will FAIL because the bare import crashes.
        """
        # Remove the optional modules from sys.modules so they appear missing
        modules_to_block = [
            'provider_registry',
            'cost_cache',
            'intent_classifier',
            'provider_router',
            'parallel_executor',
        ]

        # Save original state
        saved_modules = {}
        for mod_name in modules_to_block:
            if mod_name in sys.modules:
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        # Also remove lambda_function so it will be re-imported
        if 'lambda_function' in sys.modules:
            del sys.modules['lambda_function']

        # Patch the import mechanism to block optional modules
        real_import = __builtins__['__import__'] if isinstance(__builtins__, dict) else __builtins__.__import__

        def blocking_import(name, *args, **kwargs):
            if name in modules_to_block:
                raise ModuleNotFoundError(f"No module named '{name}'")
            if any(name.startswith(m + '.') for m in modules_to_block):
                raise ModuleNotFoundError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        try:
            # Use the custom loader but with blocked modules
            # Read source, replace bad bytes, compile, and exec with blocked imports
            with open(LAMBDA_PATH, 'rb') as f:
                raw = f.read()
            source = raw.decode('utf-8', errors='replace')
            code = compile(source, LAMBDA_PATH, 'exec')

            import types
            mod = types.ModuleType('lambda_function')
            mod.__file__ = LAMBDA_PATH
            sys.modules['lambda_function'] = mod

            with patch('builtins.__import__', side_effect=blocking_import):
                # On UNFIXED code: this will raise ModuleNotFoundError because
                # the bare "import provider_registry" at top level fails
                # On FIXED code: try/except wraps will catch the ImportError
                exec(code, mod.__dict__)

            # If we get here, the Lambda loaded without crashing
            assert hasattr(mod, 'handle_login'), \
                "Lambda loaded but handle_login function is missing"

        except ModuleNotFoundError as e:
            # This is the EXPECTED failure on unfixed code
            pytest.fail(
                f"Lambda failed to load due to missing optional module: {e}. "
                f"Bug confirmed: unconditional top-level imports crash the Lambda."
            )
        finally:
            # Restore original modules
            if 'lambda_function' in sys.modules:
                del sys.modules['lambda_function']
            for mod_name, module_obj in saved_modules.items():
                sys.modules[mod_name] = module_obj


class TestCognitoInvalidParameterException:
    """Test Case B: InvalidParameterException returns structured AuthConfigError.

    **Validates: Requirements 1.2**

    Bug condition: When Cognito raises InvalidParameterException (auth flow not
    enabled), the generic ClientError handler catches it and returns an opaque 500
    with no structured error code.

    Expected behavior (after fix): Returns statusCode=500 with body containing
    errorCode "AuthConfigError" and a descriptive message.
    """

    def test_invalid_parameter_exception_returns_auth_config_error(self):
        """Mock cognito_client.initiate_auth to raise InvalidParameterException.

        EXPECTED: Response has statusCode=500 AND body contains "AuthConfigError".
        ON UNFIXED CODE: This will FAIL because the generic handler returns
        "ServerError" without the specific AuthConfigError code.
        """
        # Load lambda_function with encoding fix (modules ARE present in dev)
        mod = _load_lambda_module()

        # Create mock exception classes matching boto3 client exception patterns
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

        error_response = {
            'Error': {
                'Code': 'InvalidParameterException',
                'Message': 'USER_PASSWORD_AUTH flow not enabled for this client'
            }
        }

        mock_cognito = MagicMock()
        mock_cognito.exceptions = mock_exceptions
        mock_cognito.initiate_auth.side_effect = (
            mock_exceptions.InvalidParameterException(error_response, 'InitiateAuth')
        )

        # Patch cognito_client and COGNITO_CLIENT_ID so the Cognito path executes
        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        # Mock event with valid email/password
        event = {
            'body': json.dumps({
                'email': 'testuser@example.com',
                'password': 'ValidPassword123!'
            })
        }

        response = mod.handle_login(event)

        # Verify structured error response
        assert response['statusCode'] == 500, \
            f"Expected statusCode 500, got {response['statusCode']}"

        body = json.loads(response['body'])
        assert body.get('error') == 'AuthConfigError', (
            f"Expected error code 'AuthConfigError' but got '{body.get('error')}'. "
            f"Full body: {body}. "
            f"Bug confirmed: InvalidParameterException is caught by generic "
            f"ClientError handler which returns 'ServerError' instead of "
            f"'AuthConfigError'."
        )


class TestGenericClientErrorTraceback:
    """Test Case C: Generic ClientError includes traceback in logs.

    **Validates: Requirements 1.3**

    Bug condition: When a generic ClientError occurs, the current code logs only
    f"Cognito login error: {e}" - no traceback, making debugging impossible.

    Expected behavior (after fix): The logged output includes a full traceback
    (traceback.format_exc() content), not just the exception string.
    """

    def test_generic_client_error_logs_traceback(self, caplog):
        """Mock cognito_client.initiate_auth to raise a generic ClientError.

        EXPECTED: Logged output includes traceback information.
        ON UNFIXED CODE: This will FAIL because only the exception string is logged.
        """
        # Load lambda_function with encoding fix
        mod = _load_lambda_module()

        # Create a generic ClientError (e.g., network/service issue)
        error_response = {
            'Error': {
                'Code': 'ServiceUnavailableException',
                'Message': 'Service is temporarily unavailable'
            }
        }
        generic_error = ClientError(error_response, 'InitiateAuth')

        # Set up mock exceptions so specific handlers don't match
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
        mock_cognito.initiate_auth.side_effect = generic_error

        mod.cognito_client = mock_cognito
        mod.COGNITO_CLIENT_ID = 'test-client-id'

        event = {
            'body': json.dumps({
                'email': 'testuser@example.com',
                'password': 'ValidPassword123!'
            })
        }

        with caplog.at_level(logging.ERROR):
            response = mod.handle_login(event)

        # The response should be 500
        assert response['statusCode'] == 500

        # Verify that the log contains traceback info (not just the exception string)
        # After the fix, logs should include "Traceback" from traceback.format_exc()
        log_output = caplog.text
        has_traceback = (
            'Traceback' in log_output
            or 'File "' in log_output
            or 'format_exc' in log_output
        )
        assert has_traceback, (
            f"Expected traceback in log output, but got only: "
            f"'{log_output.strip()}'. "
            f"Bug confirmed: the current code logs only the exception string "
            f"without a full traceback, making post-mortem debugging impossible."
        )
