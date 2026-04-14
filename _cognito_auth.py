import re

content = open("member-handler/lambda_function.py", "r", encoding="utf-8").read()

# ── 1. Add Cognito env vars after existing ones ────────────────────────────
old_env = """FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')"""
new_env = """FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID', '')"""
content = content.replace(old_env, new_env)

# ── 2. Add cognito client after existing AWS clients ──────────────────────
old_clients = """# AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')"""
new_clients = """# AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')
cognito_client = boto3.client('cognito-idp', region_name='us-east-1')"""
content = content.replace(old_clients, new_clients)

# ── 3. Replace validate_token ─────────────────────────────────────────────
old_validate = '''def validate_token(event):
    """Extract and validate JWT from Authorization header.

    Returns decoded payload on success (with role == 'member').
    Returns an error response dict on failure.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return create_error_response(401, 'AuthError', 'Session expired, please log in again')
    except jwt.InvalidTokenError:
        return create_error_response(401, 'AuthError', 'Authentication required')

    if decoded.get('role') != 'member':
        return create_error_response(401, 'AuthError', 'Authentication required')

    return decoded'''

new_validate = '''def validate_token(event):
    """Validate Cognito JWT from Authorization header.
    Returns decoded payload on success, error response dict on failure.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    try:
        # Use Cognito GetUser to validate the access token
        user_resp = cognito_client.get_user(AccessToken=token)
        email = next(
            (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'email'),
            user_resp.get('Username', '')
        ).lower()
        display_name = next(
            (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'custom:displayName'),
            email.split('@')[0]
        )
        return {'sub': email, 'role': 'member', 'displayName': display_name, 'username': user_resp.get('Username', '')}
    except cognito_client.exceptions.NotAuthorizedException:
        return create_error_response(401, 'AuthError', 'Session expired, please log in again')
    except cognito_client.exceptions.UserNotFoundException:
        return create_error_response(401, 'AuthError', 'Authentication required')
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        return create_error_response(401, 'AuthError', 'Authentication required')'''

if old_validate in content:
    content = content.replace(old_validate, new_validate)
    print("validate_token replaced")
else:
    print("ERROR: validate_token not found")

open("member-handler/lambda_function.py", "w", encoding="utf-8").write(content)
print("Step 1 done")
