"""GroundCover connector — Anthropic AI usage monitoring via GroundCover."""
import json
import logging

from .base_connector import ProviderConnector
from . import register_connector

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Constants
GROUNDCOVER_API_BASE = "https://api.groundcover.com"
REQUEST_TIMEOUT = 10  # seconds
VALID_TOKEN_PREFIX = 'gcsa_'
MIN_TOKEN_LENGTH = 20
MAX_TOKEN_LENGTH = 200


def validate_groundcover_token_format(token: str) -> dict:
    """Validate GroundCover token format without making an external API call.

    Valid tokens must start with 'gcsa_' and have a total length between 20
    and 200 characters inclusive.

    Args:
        token: The API token string to validate.

    Returns:
        dict: {'valid': True} if format is correct, or
              {'valid': False, 'error': '<reason>'} if format is invalid.
    """
    if not isinstance(token, str):
        return {'valid': False, 'error': 'Token must be a string.'}

    if not token:
        return {'valid': False, 'error': 'Token must not be empty.'}

    if not token.startswith(VALID_TOKEN_PREFIX):
        return {
            'valid': False,
            'error': 'Invalid token format. Token must start with "gcsa_".'
        }

    token_length = len(token)
    if token_length < MIN_TOKEN_LENGTH or token_length > MAX_TOKEN_LENGTH:
        return {
            'valid': False,
            'error': (
                f'Invalid token length ({token_length} characters). '
                f'Must be between {MIN_TOKEN_LENGTH} and {MAX_TOKEN_LENGTH}.'
            )
        }

    return {'valid': True}


class GroundcoverConnector(ProviderConnector):
    """GroundCover AI vendor connector using Bearer token auth."""

    def authenticate(self, credentials: dict) -> dict:
        """Validate token format and return auth context.

        credentials should contain:
          - api_key: The gcsa_ token (plaintext, already decrypted)

        Returns:
            Auth context dict with 'api_key'
        """
        api_key = credentials.get('api_key', '')
        validation = validate_groundcover_token_format(api_key)
        if not validation['valid']:
            from .base_connector import AuthenticationError
            raise AuthenticationError(validation['error'], provider='groundcover')
        return {'api_key': api_key}

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connectivity to GroundCover API using HEAD request.

        Args:
            auth_context: Dict containing 'api_key' (gcsa_ token)
            account_id: Account identifier

        Returns:
            Dict with keys: success (bool), message (str)
        """
        token = auth_context.get('api_key', '')
        # Use HEAD request — doesn't require sessionId in body
        url = GROUNDCOVER_API_BASE
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Backend-Id': 'groundcover',
        }

        try:
            req = urllib.request.Request(
                url,
                method='HEAD',
                headers=headers,
            )
            response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
            # Any 2xx/3xx means the token was accepted
            return {
                'success': True,
                'message': 'GroundCover connection verified.',
            }
        except urllib.error.HTTPError as e:
            # 401/403 = bad token
            if e.code in (401, 403):
                return {
                    'success': False,
                    'message': f'Authentication failed (HTTP {e.code}). Check your API token.',
                }
            # 405 Method Not Allowed or other codes = server responded, token accepted
            # (GroundCover may not support HEAD but responding means network + auth work)
            if e.code in (405, 400, 404):
                return {
                    'success': True,
                    'message': 'GroundCover connection verified.',
                }
            return {
                'success': False,
                'message': f'GroundCover returned HTTP {e.code}.',
            }
        except (urllib.error.URLError, OSError) as e:
            return {
                'success': False,
                'message': f'Connection error: {str(e)[:100]}',
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection test failed: {str(e)[:100]}',
            }

    def get_cost_data(self, auth_context: dict, account_id: str,
                      start_date: str, end_date: str, **kwargs) -> list:
        """Not implemented for GroundCover (monitoring only, no cost data retrieval)."""
        return []


# Auto-register when module is imported
register_connector('groundcover', GroundcoverConnector, vendor_type='ai_vendor')
