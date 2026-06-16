"""JWT authentication module for the Dashboard Handler.

Validates tokens by:
1. Trying Cognito GetUser API (access token validation - same as member-handler)
2. Falling back to legacy HS256 JWT signed with JWT_SECRET

Returns member email on success, or error response on failure.
"""

import os
import logging
import boto3

logger = logging.getLogger()

COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_REGION = os.environ.get('COGNITO_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
JWT_SECRET = os.environ.get('JWT_SECRET', '')

# Cognito client for GetUser API
cognito_client = boto3.client('cognito-idp', region_name=COGNITO_REGION)


def extract_token(event):
    """Extract Bearer token from the Authorization header."""
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''
    if not auth_header.startswith('Bearer '):
        return None
    return auth_header[7:]


def verify_jwt(token):
    """Validate a JWT token (Cognito access token or legacy HS256).

    Returns:
        A dict with 'email' key on success, or a dict with 'error' and 'status_code' on failure.
    """
    if not token:
        return {'error': 'Authentication required', 'status_code': 401}

    # --- Try Cognito GetUser API first (validates access tokens properly) ---
    if COGNITO_USER_POOL_ID:
        try:
            user_resp = cognito_client.get_user(AccessToken=token)
            email = next(
                (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'email'),
                user_resp.get('Username', '')
            ).lower()
            if email:
                return {'email': email}
            return {'error': 'Token missing email claim', 'status_code': 401}
        except cognito_client.exceptions.NotAuthorizedException:
            # Could be a legacy JWT token — try fallback
            pass
        except cognito_client.exceptions.UserNotFoundException:
            return {'error': 'Authentication required', 'status_code': 401}
        except Exception as e:
            logger.warning(f"Cognito token validation error: {e}")
            # Fall through to legacy JWT validation

    # --- Try legacy HS256 JWT ---
    if JWT_SECRET:
        try:
            from jose import jwt as jose_jwt, JWTError, ExpiredSignatureError
            decoded = jose_jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            if decoded.get('role') == 'member':
                email = decoded.get('sub', '')
                if email:
                    return {'email': email.lower()}
        except Exception as e:
            logger.warning(f"Legacy JWT validation error: {e}")
            pass

    return {'error': 'Authentication required', 'status_code': 401}
