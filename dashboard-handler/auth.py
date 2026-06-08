"""JWT authentication module for the Dashboard Handler.

Validates Cognito JWT tokens by verifying signature, expiration, and issuer.
Returns member email on success, or None/error response on failure.
"""

import os
import time
import logging
import requests
from jose import jwt, JWTError, ExpiredSignatureError

logger = logging.getLogger()

COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_REGION = os.environ.get('COGNITO_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
COGNITO_ISSUER = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}'
JWKS_URL = f'{COGNITO_ISSUER}/.well-known/jwks.json'

# Cache JWKS keys in memory (Lambda warm start optimization)
_jwks_cache = None
_jwks_cache_time = 0
JWKS_CACHE_TTL = 3600  # 1 hour


def _get_jwks():
    """Fetch and cache Cognito JWKS keys."""
    global _jwks_cache, _jwks_cache_time
    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache
    try:
        response = requests.get(JWKS_URL, timeout=5)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = now
        return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        return None


def extract_token(event):
    """Extract Bearer token from the Authorization header.

    Args:
        event: API Gateway event dict.

    Returns:
        The token string, or None if not present/invalid format.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''
    if not auth_header.startswith('Bearer '):
        return None
    return auth_header[7:]


def verify_jwt(token):
    """Validate a Cognito JWT token.

    Verifies signature, expiration, and issuer against the configured User Pool.

    Args:
        token: The JWT token string.

    Returns:
        A dict with 'email' key on success, or a dict with 'error' and 'status_code' on failure.
        Returns None if token is None.
    """
    if not token:
        return {'error': 'Authentication required', 'status_code': 401}

    if not COGNITO_USER_POOL_ID:
        return {'error': 'Authentication service not configured', 'status_code': 503}

    try:
        jwks = _get_jwks()
        if jwks is None:
            return {'error': 'Authentication service unavailable', 'status_code': 503}

        # Decode token header to get the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')

        # Find the matching key
        rsa_key = None
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                rsa_key = key
                break

        if not rsa_key:
            return {'error': 'Invalid token signature', 'status_code': 401}

        # Verify and decode the token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=['RS256'],
            issuer=COGNITO_ISSUER,
            options={'verify_aud': False}  # Access tokens don't have aud claim
        )

        # Extract email from token claims
        email = payload.get('email') or payload.get('username') or payload.get('sub', '')
        if not email:
            return {'error': 'Token missing email claim', 'status_code': 401}

        return {'email': email.lower()}

    except ExpiredSignatureError:
        return {'error': 'Token has expired', 'status_code': 401}
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        return {'error': 'Invalid token', 'status_code': 401}
    except Exception as e:
        logger.error(f"Unexpected auth error: {e}")
        return {'error': 'Authentication service unavailable', 'status_code': 503}
