"""
Member Handler Lambda v2 - Registration, login, account management, Console, AI Agent.
Routes: POST /members/register, POST /members/login, GET /members/accounts,
        POST /members/accounts, PUT /members/accounts, DELETE /members/accounts,
        POST /members/accounts/template, POST /members/accounts/test
"""

import json
import os
import re
import time
import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
import jwt
import bcrypt
import yaml

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
JWT_SECRET = os.environ.get('JWT_SECRET', '')
MEMBERS_TABLE_NAME = os.environ.get('MEMBERS_TABLE_NAME', 'MemberPortal-Members')
ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
OTP_TABLE_NAME = os.environ.get('OTP_TABLE_NAME', 'ViewMyBill-OTP')
SES_SENDER_EMAIL = os.environ.get('SES_SENDER_EMAIL', 'noreply@slashmycloudbill.com')
PLATFORM_ACCOUNT_ID = os.environ.get('PLATFORM_ACCOUNT_ID', '991105135552')
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')
BEDROCK_AGENT_ID = os.environ.get('BEDROCK_AGENT_ID', '')
BEDROCK_AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')
FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID', '')

# AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')
cognito_client = boto3.client('cognito-idp', region_name='us-east-1')

# Constants
OTP_TTL_SECONDS = 300  # 5 minutes
RATE_LIMIT_SECONDS = 60
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _decimal_to_native(obj):
    """Recursively convert Decimal values to int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_decimal_to_native(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj


# ============================================================
# Main entry point and route dispatch
# ============================================================

def lambda_handler(event, context):
    """Main entry point — dispatches to handler based on routeKey."""
    route_key = event.get('routeKey', '')
    logger.info(f"Member API request: {route_key}")

    if route_key.startswith('OPTIONS '):
        return create_response(200, {'message': 'OK'})

    routes = {
        'POST /members/register': handle_register,
        'POST /members/login': handle_login,
        'POST /members/reset-password': handle_reset_password,
        'GET /members/accounts': handle_get_accounts,
        'POST /members/accounts': handle_add_account,
        'PUT /members/accounts': handle_edit_account,
        'POST /members/accounts/reorder': handle_reorder_accounts,
        'DELETE /members/accounts': handle_delete_account,
        'POST /members/accounts/template': handle_generate_template,
        'POST /members/accounts/test': handle_test_connection,
        'POST /members/accounts/execute': handle_execute_command,
        'POST /members/accounts/ai-query': handle_ai_query,
        'POST /members/accounts/ai-feedback': handle_ai_feedback,
        'GET /members/dashboard': handle_get_dashboard,
        'GET /members/dashboard-data': handle_dashboard_data,
        'POST /members/dashboard': handle_add_dashboard_item,
        'DELETE /members/dashboard': handle_delete_dashboard_item,
        'GET /members/allocation-rules': handle_get_allocation_rules,
        'POST /members/allocation-rules': handle_save_allocation_rules,
        'GET /members/business-metrics': handle_get_business_metrics,
        'POST /members/business-metrics': handle_save_business_metrics,
        'POST /members/actions/scan': handle_actions_scan,
        'GET /members/actions/last-scan': handle_get_last_scan,
        'POST /members/actions/execute': handle_actions_execute,
        'POST /members/actions/browse-bucket': handle_browse_bucket,
        'POST /member/add-tokens': handle_add_tokens,
        'POST /member/update-tier': handle_update_tier,
        'POST /members/tags/scan': handle_tag_scan,
        'POST /members/tags/apply': handle_tag_apply,
        'POST /members/schedules/analyze': handle_schedule_analyze,
        'GET /members/schedules': handle_get_schedules,
        'PUT /members/schedules/status': handle_update_schedule_status,
    }

    handler = routes.get(route_key)
    if handler is None:
        return create_error_response(404, 'NotFound', 'Route not found')

    return handler(event)


# ============================================================
# Token validation
# ============================================================

def validate_token(event):
    """Validate token from Authorization header.
    
    If Cognito is configured (COGNITO_USER_POOL_ID set), validates via Cognito GetUser.
    Falls back to legacy JWT validation for backward compatibility during migration.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    # ── Cognito path (new) ────────────────────────────────────────────────
    if COGNITO_USER_POOL_ID:
        try:
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
            # Could be a legacy JWT token — try fallback
            pass
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(401, 'AuthError', 'Authentication required')
        except Exception as e:
            logger.warning(f"Cognito token validation error: {e}")
            # Fall through to legacy JWT validation

    # ── Legacy JWT path (fallback / migration period) ─────────────────────
    if JWT_SECRET:
        try:
            decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            if decoded.get('role') == 'member':
                return decoded
        except jwt.ExpiredSignatureError:
            return create_error_response(401, 'AuthError', 'Session expired, please log in again')
        except jwt.InvalidTokenError:
            pass

    return create_error_response(401, 'AuthError', 'Authentication required')


def _verify_account_ownership(member_email, account_ids):
    """Verify that all given account IDs belong to the authenticated member.
    Returns True if all accounts are owned, or an error response dict if not.
    """
    if not account_ids:
        return True
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email),
            ProjectionExpression='accountId',
        )
        owned_ids = {item['accountId'] for item in result.get('Items', [])}
    except ClientError:
        return create_error_response(500, 'ServerError', 'Failed to verify account ownership')

    for aid in account_ids:
        if aid not in owned_ids:
            logger.warning(f"Lateral access attempt: {member_email} tried to access account {aid}")
            return create_error_response(403, 'Forbidden', f'Account {aid} does not belong to you')
    return True


# ============================================================
# Registration handler (3-step OTP flow)
# ============================================================


def handle_register(event):
    """Register a new member via Cognito User Pool."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    action = body.get("action", "")

    if action == "send-otp":
        # Step 1: Initiate Cognito sign-up (sends verification email automatically)
        email = (body.get("email") or "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            return create_error_response(400, "InvalidEmail", "Please provide a valid email address")
        password = body.get("password") or ""
        if not password:
            # Temporary password for sign-up initiation — will be set properly in create-account
            # For the 3-step flow, we use AdminCreateUser with SUPPRESS message first
            # then send verification code
            try:
                # Check if user already exists
                try:
                    cognito_client.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=email)
                    return create_error_response(409, "ConflictError", "An account with this email already exists")
                except cognito_client.exceptions.UserNotFoundException:
                    pass
                # Initiate sign-up with a placeholder — we will use AdminCreateUser flow
                # Send OTP via Cognito ResendConfirmationCode after AdminCreateUser
                return create_response(200, {"message": "OTP sent successfully", "email": email})
            except ClientError as e:
                logger.error(f"Cognito check error: {e}")
                return create_error_response(500, "ServerError", "An unexpected error occurred.")

        # Full sign-up with email + password in one step
        pre_verified = body.get("preVerified", False)
        try:
            try:
                cognito_client.admin_get_user(UserPoolId=COGNITO_USER_POOL_ID, Username=email)
                return create_error_response(409, "ConflictError", "An account with this email already exists")
            except cognito_client.exceptions.UserNotFoundException:
                pass

            if pre_verified:
                # Email already verified via OTP on bill upload — skip Cognito verification
                cognito_client.admin_create_user(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=email,
                    UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
                    MessageAction="SUPPRESS",
                )
                cognito_client.admin_set_user_password(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=email,
                    Password=password,
                    Permanent=True,
                )
                # Create profile in DynamoDB
                members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
                now_iso = datetime.now(timezone.utc).isoformat()
                try:
                    members_table.put_item(
                        Item={"email": email, "displayName": email.split("@")[0], "createdAt": now_iso, "lastLoginAt": None, "favoriteQueries": [], "tier": "free"},
                        ConditionExpression="attribute_not_exists(email)",
                    )
                except ClientError:
                    pass
                return create_response(201, {"message": "Registration successful", "email": email, "preVerified": True})
            else:
                cognito_client.sign_up(
                    ClientId=COGNITO_CLIENT_ID,
                    Username=email,
                    Password=password,
                    UserAttributes=[
                        {"Name": "email", "Value": email},
                    ],
                )
                return create_response(200, {"message": "OTP sent successfully", "email": email})
        except cognito_client.exceptions.UsernameExistsException:
            return create_error_response(409, "ConflictError", "An account with this email already exists")
        except cognito_client.exceptions.InvalidPasswordException as e:
            return create_error_response(400, "InvalidPassword", str(e))
        except ClientError as e:
            logger.error(f"Cognito sign_up error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "verify-otp":
        # Step 2: Confirm sign-up with the verification code
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp") or "").strip()
        if not email or not otp_code:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        try:
            cognito_client.confirm_sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=otp_code,
            )
            # Generate a short-lived otpToken for the final step (backward compat)
            now = int(time.time())
            otp_token = jwt.encode(
                {"sub": email, "purpose": "registration", "iat": now, "exp": now + 600},
                JWT_SECRET, algorithm="HS256"
            )
            return create_response(200, {"verified": True, "otpToken": otp_token})
        except cognito_client.exceptions.CodeMismatchException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        except cognito_client.exceptions.ExpiredCodeException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired OTP code")
        except ClientError as e:
            logger.error(f"Cognito confirm_sign_up error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "create-account":
        # Step 3: Account already created in step 1 — just create the profile record
        otp_token = (body.get("otpToken") or "").strip()
        if not otp_token:
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        try:
            decoded = jwt.decode(otp_token, JWT_SECRET, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        if decoded.get("purpose") != "registration":
            return create_error_response(400, "InvalidToken", "Email verification token is invalid or expired")
        email = decoded.get("sub", "").lower()

        # Create profile record in DynamoDB (no password stored)
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            existing = members_table.get_item(Key={"email": email}).get("Item")
            if not existing:
                members_table.put_item(Item={
                    "email": email,
                    "displayName": email.split("@")[0],
                    "createdAt": now_iso,
                    "lastLoginAt": None,
                    "favoriteQueries": [],
                    "tier": "free",
                })
        except ClientError as e:
            logger.warning(f"Profile create error (non-critical): {e}")

        return create_response(201, {"message": "Registration successful", "email": email})

    elif action == "resend-otp":
        # Resend verification code
        email = (body.get("email") or "").strip().lower()
        if not email:
            return create_error_response(400, "InvalidEmail", "Email is required")
        try:
            cognito_client.resend_confirmation_code(ClientId=COGNITO_CLIENT_ID, Username=email)
            return create_response(200, {"message": "Code resent", "email": email})
        except ClientError as e:
            logger.error(f"Cognito resend error: {e}")
            return create_error_response(500, "ServerError", "Failed to resend code")

    else:
        return create_error_response(400, "InvalidRequest", "Field 'action' is required")


def handle_login(event):
    """Authenticate member via Cognito and return access token."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    email = (body.get("email") or "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        return create_error_response(400, "InvalidRequest", "Email and password are required")

    # ── Cognito login (new) ──────────────────────────────────────────────────
    if COGNITO_CLIENT_ID:
        try:
            auth_resp = cognito_client.initiate_auth(
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
                ClientId=COGNITO_CLIENT_ID,
            )
            auth_result = auth_resp.get("AuthenticationResult", {})
            access_token = auth_result.get("AccessToken", "")
            refresh_token = auth_result.get("RefreshToken", "")

            display_name = email.split("@")[0]
            members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
            try:
                member = members_table.get_item(Key={"email": email}).get("Item")
                if member:
                    display_name = member.get("displayName", display_name)
                else:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    members_table.put_item(Item={"email": email, "displayName": display_name, "createdAt": now_iso, "lastLoginAt": now_iso, "favoriteQueries": []})
            except ClientError:
                pass
            try:
                members_table.update_item(Key={"email": email}, UpdateExpression="SET lastLoginAt = :ts", ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()})
            except ClientError:
                pass

            logger.info(f"Member Cognito login successful for: {email}")
            member_tier = 'free'
            try:
                m = members_table.get_item(Key={"email": email}).get("Item", {})
                member_tier = m.get('tier', 'free')
            except Exception:
                pass
            return create_response(200, {"token": access_token, "refreshToken": refresh_token, "email": email, "displayName": display_name, "tier": member_tier, "tierLimit": _get_tier_limit(member_tier)})

        except cognito_client.exceptions.NotAuthorizedException:
            return create_error_response(401, "AuthError", "Invalid email or password")
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(401, "AuthError", "Invalid email or password")
        except cognito_client.exceptions.UserNotConfirmedException:
            return create_error_response(401, "AuthError", "Please verify your email before logging in")
        except ClientError as e:
            logger.error(f"Cognito login error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    # ── Legacy DynamoDB login (fallback during migration) ─────────────────
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        result = members_table.get_item(Key={"email": email})
        member = result.get("Item")
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, "ServerError", "An unexpected error occurred.")

    if not member:
        return create_error_response(401, "AuthError", "Invalid email or password")

    try:
        password_valid = bcrypt.checkpw(password.encode("utf-8"), member["passwordHash"].encode("utf-8"))
    except Exception:
        return create_error_response(401, "AuthError", "Invalid email or password")

    if not password_valid:
        return create_error_response(401, "AuthError", "Invalid email or password")

    now = int(time.time())
    token = jwt.encode({"sub": email, "role": "member", "iat": now, "exp": now + 86400}, JWT_SECRET, algorithm="HS256")

    try:
        members_table.update_item(Key={"email": email}, UpdateExpression="SET lastLoginAt = :ts", ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()})
    except ClientError:
        pass

    display_name = member.get("displayName", email.split("@")[0])
    logger.info(f"Member legacy login successful for: {email}")
    return create_response(200, {"token": token, "email": email, "displayName": display_name})


def handle_reset_password(event):
    """Handle password reset via Cognito ForgotPassword flow."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "InvalidRequest", "Invalid request body")

    action = body.get("action", "")

    if action == "send-otp":
        email = (body.get("email") or "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            return create_error_response(400, "InvalidEmail", "Please provide a valid email address")
        try:
            cognito_client.forgot_password(ClientId=COGNITO_CLIENT_ID, Username=email)
            return create_response(200, {"message": "Reset code sent", "email": email})
        except cognito_client.exceptions.UserNotFoundException:
            return create_error_response(404, "NotFound", "No account found with this email")
        except cognito_client.exceptions.LimitExceededException:
            return create_error_response(429, "RateLimited", "Please wait before requesting a new code")
        except ClientError as e:
            logger.error(f"Cognito forgot_password error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    elif action == "verify-otp":
        email = (body.get("email") or "").strip().lower()
        otp_code = (body.get("otp") or "").strip()
        if not email or not otp_code:
            return create_error_response(400, "InvalidOTP", "Invalid or expired code")
        # We can't verify the code without the new password in Cognito
        # So we store it in a short-lived JWT for the next step
        now = int(time.time())
        reset_token = jwt.encode(
            {"sub": email, "otp": otp_code, "purpose": "reset", "iat": now, "exp": now + 600},
            JWT_SECRET, algorithm="HS256"
        )
        return create_response(200, {"verified": True, "resetToken": reset_token})

    elif action == "set-password":
        reset_token = (body.get("resetToken") or "").strip()
        password = body.get("password", "")
        confirm_password = body.get("confirmPassword", "")
        if not reset_token:
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        try:
            decoded = jwt.decode(reset_token, JWT_SECRET, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        if decoded.get("purpose") != "reset":
            return create_error_response(400, "InvalidToken", "Reset token is invalid or expired")
        email = decoded.get("sub", "").lower()
        otp_code = decoded.get("otp", "")
        if len(password) < 8:
            return create_error_response(400, "InvalidPassword", "Password must be at least 8 characters")
        if password != confirm_password:
            return create_error_response(400, "InvalidPassword", "Passwords do not match")
        try:
            cognito_client.confirm_forgot_password(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=otp_code,
                Password=password,
            )
            return create_response(200, {"message": "Password reset successful. Please log in with your new password."})
        except cognito_client.exceptions.CodeMismatchException:
            return create_error_response(400, "InvalidOTP", "Invalid or expired reset code")
        except cognito_client.exceptions.ExpiredCodeException:
            return create_error_response(400, "InvalidOTP", "Reset code has expired. Please request a new one.")
        except cognito_client.exceptions.InvalidPasswordException as e:
            return create_error_response(400, "InvalidPassword", str(e))
        except ClientError as e:
            logger.error(f"Cognito confirm_forgot_password error: {e}")
            return create_error_response(500, "ServerError", "An unexpected error occurred.")

    else:
        return create_error_response(400, "InvalidRequest", "Field 'action' is required")


def handle_get_accounts(event):
    """List member's accounts."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)

    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
        )
        accounts = result.get('Items', [])
    except ClientError as e:
        logger.error(f"DynamoDB query error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Sort by sortOrder (priority), then addedAt
    accounts.sort(key=lambda a: (a.get('sortOrder', 999), a.get('addedAt', '')))

    # Convert Decimal values for JSON serialization
    accounts = _decimal_to_native(accounts)

    # Include tier and token info for frontend
    tier = _get_member_tier(member_email)
    limit = _get_tier_limit(tier)
    max_tokens = AI_CREDITS.get(tier, 100)
    try:
        m = dynamodb.Table(MEMBERS_TABLE_NAME).get_item(Key={'email': member_email}).get('Item', {})
        current_month = datetime.now(timezone.utc).strftime('%Y-%m')
        tokens_used = int(m.get('aiCreditsUsed', 0)) if m.get('aiCreditsMonth', '') == current_month else 0
        bonus = int(m.get('bonusTokens', 0))
    except Exception:
        tokens_used = 0
        bonus = 0

    return create_response(200, {
        'accounts': accounts,
        'tier': tier,
        'tierLimit': limit,
        'tokens': {'used': tokens_used, 'total': max_tokens + bonus, 'remaining': max(0, max_tokens + bonus - tokens_used), 'bonus': bonus},
    })


def _get_tier_limit(tier: str) -> int:
    """Return max AWS accounts allowed per tier."""
    return TIER_ACCOUNT_LIMITS.get(tier, 1)


TIER_FEATURES = {
    'free': {'dashboard', 'accounts', 'waste_detection', 'ai_agent'},
    'growth': {'dashboard', 'accounts', 'waste_detection', 'actions', 'ai_agent', 'office_hours', 'virtual_tagging', 'unit_economics'},
}

AI_CREDITS = {'free': 100, 'growth': 300, 'scale': 1500}  # tokens per month
SCAN_CREDIT_COST = 10  # Each scan costs 10 tokens
AI_QUERY_CREDIT_COST = 2  # Each AI question costs 2 tokens
ACTIVITY_CREDIT_COST = 50  # Each cleanup action costs 50 tokens

TIER_ACCOUNT_LIMITS = {'free': 1, 'growth': 5, 'scale': 20}


def _check_and_consume_credits(member_email: str, tier: str, cost: int) -> dict:
    """Check if member has enough tokens and consume them. Returns None if OK, or error response."""
    max_tokens = AI_CREDITS.get(tier, 100)

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    current_month = datetime.now(timezone.utc).strftime('%Y-%m')
    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item', {})
        tokens_used = int(member.get('aiCreditsUsed', 0))
        tokens_month = member.get('aiCreditsMonth', '')
        bonus_tokens = int(member.get('bonusTokens', 0))

        # Monthly reset: if stored month differs from current, reset used count
        if tokens_month != current_month:
            tokens_used = 0
            members_table.update_item(
                Key={'email': member_email},
                UpdateExpression='SET aiCreditsUsed = :zero, aiCreditsMonth = :month',
                ExpressionAttributeValues={':zero': 0, ':month': current_month}
            )

        tokens_remaining = max(0, (max_tokens + bonus_tokens) - tokens_used)
    except Exception:
        tokens_used = 0
        bonus_tokens = 0
        tokens_remaining = max_tokens

    if tokens_remaining < cost:
        return create_error_response(403, 'TokensExhausted',
            f'Not enough tokens. This costs {cost} tokens but you have {tokens_remaining} remaining. '
            f'Top up tokens or upgrade your plan.',
            extra={'tokensUsed': tokens_used, 'tokensTotal': max_tokens + bonus_tokens,
                   'tokensRemaining': tokens_remaining, 'tokenCost': cost,
                   'currentTier': tier, 'bonusTokens': bonus_tokens})

    # Consume tokens
    try:
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET aiCreditsUsed = if_not_exists(aiCreditsUsed, :zero) + :cost, aiCreditsMonth = :month',
            ExpressionAttributeValues={':zero': 0, ':cost': cost, ':month': current_month}
        )
    except Exception:
        pass

    return None


def _check_feature_access(tier: str, feature: str) -> bool:
    """Check if a tier has access to a specific feature."""
    return feature in TIER_FEATURES.get(tier, TIER_FEATURES['free'])


def _get_member_tier(email: str) -> str:
    """Get the member's current tier from DynamoDB."""
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        item = members_table.get_item(Key={'email': email}).get('Item', {})
        return item.get('tier', 'free')
    except Exception:
        return 'free'


def handle_add_account(event):
    """Add a new AWS account."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    account_name = (body.get('accountName') or '').strip()

    # Validate 12-digit Account ID
    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)

    # Check for duplicate
    try:
        existing = accounts_table.get_item(Key={'memberEmail': member_email, 'accountId': account_id}).get('Item')
        if existing:
            return create_error_response(409, 'ConflictError', 'This AWS account is already connected')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Enforce tier account limit
    try:
        all_accounts = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email),
            Select='COUNT'
        )
        current_count = all_accounts.get('Count', 0)
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = members_table.get_item(Key={'email': member_email}).get('Item', {})
        tier = member.get('tier', 'free')
        limit = _get_tier_limit(tier)
        if current_count >= limit:
            if tier == 'free':
                return create_error_response(403, 'TierLimitReached',
                    f'Your Free plan allows 1 AWS account. Upgrade to Growth ($50/mo) to connect up to 5 accounts.',
                    extra={'currentTier': tier, 'limit': limit, 'currentCount': current_count}
                )
            else:
                return create_error_response(403, 'TierLimitReached',
                    f'You have reached the maximum of {limit} accounts for your {tier.title()} plan.',
                    extra={'currentTier': tier, 'limit': limit, 'currentCount': current_count}
                )
    except ClientError as e:
        logger.error(f"Tier limit check error: {e}")
        # Non-blocking — allow the add if check fails

    now_iso = datetime.now(timezone.utc).isoformat()
    role_name = f'SlashMyBill-{account_id}'

    account_record = {
        'memberEmail': member_email,
        'accountId': account_id,
        'accountName': account_name or f'Account {account_id[-4:]}',
        'roleName': role_name,
        'connectionStatus': 'pending',
        'addedAt': now_iso,
        'lastTestedAt': None,
    }

    try:
        accounts_table.put_item(Item=account_record)
    except ClientError as e:
        logger.error(f"DynamoDB write error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    logger.info(f"Account {account_id} added for member {member_email}")
    return create_response(201, {'message': 'Account added', 'account': account_record})


def handle_edit_account(event):
    """Edit an existing AWS account (change Account ID)."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    old_account_id = (body.get('oldAccountId') or '').strip()
    new_account_id = (body.get('newAccountId') or '').strip()
    account_name = (body.get('accountName') or '').strip()

    if not old_account_id or not new_account_id:
        return create_error_response(400, 'InvalidRequest', "Fields 'oldAccountId' and 'newAccountId' are required")

    # Validate new Account ID is 12 digits
    if not re.fullmatch(r'\d{12}', new_account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)

    # Fetch old record
    try:
        old_result = accounts_table.get_item(Key={'memberEmail': member_email, 'accountId': old_account_id})
        old_record = old_result.get('Item')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    if not old_record:
        return create_error_response(404, 'NotFound', 'Account not found')

    # If same ID, nothing to change
    if old_account_id == new_account_id:
        try:
            accounts_table.update_item(
                Key={'memberEmail': member_email, 'accountId': old_account_id},
                UpdateExpression='SET accountName = :n',
                ExpressionAttributeValues={':n': account_name or old_record.get('accountName', f'Account {old_account_id[-4:]}')},
            )
            old_record['accountName'] = account_name or old_record.get('accountName', f'Account {old_account_id[-4:]}')
        except ClientError as e:
            logger.error(f"DynamoDB update error: {e}")
            return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')
        return create_response(200, {'message': 'Account updated', 'account': _decimal_to_native(old_record)})

    # Check for duplicate with new ID
    try:
        dup = accounts_table.get_item(Key={'memberEmail': member_email, 'accountId': new_account_id}).get('Item')
        if dup:
            return create_error_response(409, 'ConflictError', 'This AWS account is already connected')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Preserve original addedAt
    original_added_at = old_record.get('addedAt', datetime.now(timezone.utc).isoformat())

    new_record = {
        'memberEmail': member_email,
        'accountId': new_account_id,
        'accountName': account_name or old_record.get('accountName', f'Account {new_account_id[-4:]}'),
        'roleName': f'SlashMyBill-{new_account_id}',
        'connectionStatus': 'pending',
        'addedAt': original_added_at,
        'lastTestedAt': None,
    }

    # Delete old, create new
    try:
        accounts_table.delete_item(Key={'memberEmail': member_email, 'accountId': old_account_id})
        accounts_table.put_item(Item=new_record)
    except ClientError as e:
        logger.error(f"DynamoDB write error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    logger.info(f"Account edited for {member_email}: {old_account_id} -> {new_account_id}")
    return create_response(200, {'message': 'Account updated', 'account': new_record})


def handle_reorder_accounts(event):
    """Reorder accounts by setting sortOrder on each."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    order = body.get('order', [])  # list of accountId strings in desired order
    if not order or not isinstance(order, list):
        return create_error_response(400, 'InvalidRequest', '"order" must be a non-empty array of accountIds')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    for idx, acct_id in enumerate(order):
        try:
            accounts_table.update_item(
                Key={'memberEmail': member_email, 'accountId': str(acct_id)},
                UpdateExpression='SET sortOrder = :s',
                ExpressionAttributeValues={':s': idx},
            )
        except ClientError:
            pass
    return create_response(200, {'message': 'Accounts reordered'})


def handle_delete_account(event):
    """Delete an AWS account."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    if not account_id:
        return create_error_response(400, 'InvalidRequest', "Field 'accountId' is required")

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)

    # Try deleting the member stack in the target AWS account first
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    stack_name = f'SlashMyBill-Access-{account_id}'
    stack_delete_requested = False
    stack_delete_warning = None
    try:
        sts_client = boto3.client('sts')
        assume = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SlashMyBillDeleteStack',
            ExternalId=external_id,
        )
        creds = assume['Credentials']

        # First, clean up the IAM role (detach policies, delete inline policies, delete role)
        # This is needed because CloudFormation can't delete a role with policies attached
        iam = boto3.client(
            'iam',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name='us-east-1',
        )
        role_name = f'SlashMyBill-{account_id}'
        try:
            # Detach all managed policies
            attached = iam.list_attached_role_policies(RoleName=role_name).get('AttachedPolicies', [])
            for pol in attached:
                try:
                    iam.detach_role_policy(RoleName=role_name, PolicyArn=pol['PolicyArn'])
                except Exception:
                    pass

            # Delete all inline policies
            inline = iam.list_role_policies(RoleName=role_name).get('PolicyNames', [])
            for pol_name in inline:
                try:
                    iam.delete_role_policy(RoleName=role_name, PolicyName=pol_name)
                except Exception:
                    pass

            # Delete the role itself
            try:
                iam.delete_role(RoleName=role_name)
                logger.info(f"Deleted IAM role {role_name} in account {account_id}")
            except Exception as e:
                logger.warning(f"Could not delete role {role_name}: {e}")
        except Exception as e:
            logger.warning(f"IAM cleanup failed for {role_name}: {e}")

        # Now delete the CloudFormation stack
        cf = boto3.client(
            'cloudformation',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name='us-east-1',
        )
        cf.delete_stack(StackName=stack_name)
        stack_delete_requested = True
    except ClientError as e:
        code = (e.response or {}).get('Error', {}).get('Code', '')
        msg = (e.response or {}).get('Error', {}).get('Message', '')
        if code == 'ValidationError' and 'does not exist' in msg:
            logger.info(f"Stack {stack_name} not found in account {account_id}, continuing with account delete")
        elif 'not authorized' in msg.lower() or code == 'AccessDenied':
            # Old role template — missing cloudformation:DeleteStack permission.
            # Don't block the disconnect; warn the user to clean up manually.
            stack_delete_warning = (
                f'The connection has been removed from SlashMyBill. '
                f'However, the IAM role stack "{stack_name}" could not be automatically deleted '
                f'because the role was deployed with an older template that lacks cloudformation:DeleteStack. '
                f'To fully clean up, please delete the stack manually in your AWS CloudFormation console, '
                f'or redeploy the latest template first and then disconnect again.'
            )
            logger.warning(f"Stack delete permission denied for {stack_name}: {msg}")
        else:
            logger.error(f"Failed to delete stack {stack_name} for account {account_id}: {e}")
            return create_error_response(400, 'StackDeleteFailed', f'Failed to delete stack {stack_name}: {msg or code}')

    try:
        accounts_table.delete_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            ConditionExpression='attribute_exists(memberEmail)',
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Account not found')
        logger.error(f"DynamoDB delete error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    logger.info(f"Account {account_id} deleted for member {member_email}")
    return create_response(200, {
        'message': 'Account deleted',
        'stackDeleteRequested': stack_delete_requested,
        'stackName': stack_name,
        'warning': stack_delete_warning,
    })


def handle_generate_template(event):
    """Generate CloudFormation template for an account."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')

    # Compute ExternalId as SHA-256 hash of member email
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    template = {
        'AWSTemplateFormatVersion': '2010-09-09',
        'Description': f'SlashMyBill cross-account access role for {account_id}',
        'Resources': {
            'SlashMyBillRole': {
                'Type': 'AWS::IAM::Role',
                'DeletionPolicy': 'Delete',
                'UpdateReplacePolicy': 'Delete',
                'Properties': {
                    'RoleName': f'SlashMyBill-{account_id}',
                    'AssumeRolePolicyDocument': {
                        'Version': '2012-10-17',
                        'Statement': [
                            {
                                'Effect': 'Allow',
                                'Principal': {
                                    'AWS': f'arn:aws:iam::{PLATFORM_ACCOUNT_ID}:root'
                                },
                                'Action': 'sts:AssumeRole',
                                'Condition': {
                                    'StringEquals': {
                                        'sts:ExternalId': external_id
                                    }
                                }
                            }
                        ]
                    },
                    # AWS managed ReadOnlyAccess covers all ~200 services automatically
                    # and is maintained by AWS. Billing/CE APIs are not included so
                    # we add those as a separate inline policy below.
                    'ManagedPolicyArns': [
                        'arn:aws:iam::aws:policy/ReadOnlyAccess',
                    ],
                    'Policies': [
                        {
                            'PolicyName': 'SlashMyBillBillingAccess',
                            'PolicyDocument': {
                                'Version': '2012-10-17',
                                'Statement': [
                                    {
                                        'Effect': 'Allow',
                                        'Action': [
                                            # Cost Explorer — core FinOps data
                                            'ce:GetCostAndUsage',
                                            'ce:GetCostForecast',
                                            'ce:GetReservationUtilization',
                                            'ce:GetReservationCoverage',
                                            'ce:GetSavingsPlansUtilization',
                                            'ce:GetSavingsPlansCoverage',
                                            'ce:GetRightsizingRecommendation',
                                            'ce:GetCostCategories',
                                            'ce:GetDimensionValues',
                                            'ce:GetTags',
                                            'ce:ListCostAllocationTags',
                                            'ce:GetApproximateUsageRecords',
                                            'ce:UpdatePreferences',
                                            'ce:GetPreferences',
                                            # Budgets
                                            'budgets:ViewBudget',
                                            'budgets:DescribeBudgets',
                                            'budgets:DescribeBudgetActionsForAccount',
                                            # Cost Optimization Hub
                                            'cost-optimization-hub:ListRecommendations',
                                            'cost-optimization-hub:GetRecommendation',
                                            # Billing / CUR
                                            'cur:DescribeReportDefinitions',
                                            'cur:GetClassicReport',
                                            'cur:GetUsageReport',
                                            'billing:GetBillingData',
                                            'billing:GetBillingDetails',
                                            # Trusted Advisor (cost checks)
                                            'support:DescribeTrustedAdvisorChecks',
                                            'support:DescribeTrustedAdvisorCheckResult',
                                            # Stack self-management (for template update/delete)
                                            'cloudformation:DeleteStack',
                                            'cloudformation:UpdateStack',
                                            'cloudformation:CreateStack',
                                            'cloudformation:DescribeStacks',
                                            'cloudformation:DescribeStackResources',
                                            'cloudformation:GetTemplate',
                                            'iam:GetRole',
                                            'iam:ListRolePolicies',
                                            'iam:ListAttachedRolePolicies',
                                            'iam:DeleteRolePolicy',
                                            'iam:DetachRolePolicy',
                                            'iam:DeleteRole',
                                            'iam:CreateRole',
                                            'iam:PutRolePolicy',
                                            'iam:AttachRolePolicy',
                                            'iam:TagRole',
                                            'iam:PassRole',
                                            # Level 1 cleanup actions
                                            'ec2:ReleaseAddress',
                                            'ec2:DeleteVolume',
                                            'elasticloadbalancing:DeleteLoadBalancer',
                                            's3:PutBucketLifecycleConfiguration',
                                            's3:GetBucketLifecycleConfiguration',
                                            's3:GetBucketLocation',
                                            's3:ListBucketMultipartUploads',
                                            's3:AbortMultipartUpload',
                                            's3:ListBucket',
                                            's3:GetObject',
                                            's3:HeadObject',
                                            's3:DeleteObject',
                                            's3:DeleteObjects',
                                            # Idle EC2 / RDS / Snapshot cleanup
                                            'ec2:StopInstances',
                                            'ec2:TerminateInstances',
                                            'ec2:DescribeInstanceAttribute',
                                            'autoscaling:DescribeAutoScalingInstances',
                                            'autoscaling:DetachInstances',
                                            'autoscaling:UpdateAutoScalingGroup',
                                            'ec2:DeleteSnapshot',
                                            'rds:DeleteDBInstance',
                                            'rds:DescribeDBInstances',
                                            # Resource tagging (bulk tag management)
                                            'tag:GetResources',
                                            'tag:GetTagKeys',
                                            'tag:GetTagValues',
                                            'tag:TagResources',
                                            'tag:UntagResources',
                                            # Per-service tagging permissions
                                            'ec2:CreateTags',
                                            'ec2:DeleteTags',
                                            'rds:AddTagsToResource',
                                            'rds:RemoveTagsFromResource',
                                            's3:PutBucketTagging',
                                            's3:GetBucketTagging',
                                            'lambda:TagResource',
                                            'lambda:UntagResource',
                                            'elasticloadbalancing:AddTags',
                                            'elasticloadbalancing:RemoveTags',
                                        ],
                                        'Resource': '*'
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        },
        'Outputs': {
            'RoleArn': {
                'Description': 'ARN of the SlashMyBill cross-account role',
                'Value': {'Fn::GetAtt': ['SlashMyBillRole', 'Arn']}
            }
        }
    }

    template_yaml = yaml.dump(template, default_flow_style=False, sort_keys=False)
    filename = f'SlashMyBill-{account_id}.yaml'
    stack_name = f'SlashMyBill-Access-{account_id}'
    role_name = f'SlashMyBill-{account_id}'

    # Upload template to S3 for CloudFormation quick-create link
    s3_key = f'cf-templates/{member_email}/{filename}'
    try:
        s3_client = boto3.client('s3')
        bucket = os.environ.get('STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552')
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=template_yaml,
            ContentType='application/x-yaml',
        )
        # Use a pre-signed URL so CloudFormation in the member account can fetch
        # the template even when the platform bucket is private.
        template_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=86400,  # 24 hours
        )
    except Exception as e:
        logger.warning(f"Failed to upload CF template to S3: {e}")
        template_url = None

    # Detect whether the stack already exists in the customer account
    # so the frontend can show Create vs Update automatically
    stack_exists = False
    stack_status = None
    try:
        role_arn_check = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
        sts_check = boto3.client('sts')
        assume_check = sts_check.assume_role(
            RoleArn=role_arn_check,
            RoleSessionName='SlashMyBillTemplateCheck',
            ExternalId=external_id,
        )
        cf_check = boto3.client(
            'cloudformation',
            aws_access_key_id=assume_check['Credentials']['AccessKeyId'],
            aws_secret_access_key=assume_check['Credentials']['SecretAccessKey'],
            aws_session_token=assume_check['Credentials']['SessionToken'],
            region_name='us-east-1',
        )
        stacks = cf_check.describe_stacks(StackName=stack_name)
        if stacks.get('Stacks'):
            stack_exists = True
            stack_status = stacks['Stacks'][0].get('StackStatus', '')
    except ClientError as e:
        # Stack doesn't exist or role not yet deployed — that's fine
        pass
    except Exception as e:
        logger.warning(f"Stack existence check failed: {e}")

    # Build CloudFormation URLs
    cf_console_url = None
    cf_update_url = None
    if template_url:
        import urllib.parse
        create_params = urllib.parse.urlencode({
            'templateURL': template_url,
            'stackName': stack_name,
        })
        cf_console_url = f'https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?{create_params}'
        update_params = urllib.parse.urlencode({'templateURL': template_url})
        cf_update_url = (
            f'https://console.aws.amazon.com/cloudformation/home#/stacks/update/template'
            f'?stackId={urllib.parse.quote(f"arn:aws:cloudformation:us-east-1:{account_id}:stack/{stack_name}/", safe="")}'
            f'&{update_params}'
        )

    return create_response(200, {
        'template': template_yaml,
        'filename': filename,
        'templateUrl': template_url,
        'cfConsoleUrl': cf_console_url,
        'cfUpdateUrl': cf_update_url,
        'stackName': stack_name,
        'roleName': role_name,
        'stackExists': stack_exists,
        'stackStatus': stack_status,
        'instructions': (
            f'If you see "role already exists" when deploying, the stack needs to be UPDATED not created. '
            f'Go to CloudFormation → Stacks → {stack_name} → Update, and use the template URL above.'
        ),
    })


def handle_test_connection(event):
    """Test cross-account connection via STS AssumeRole + Cost Explorer."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')

    # Verify account ownership
    ownership = _verify_account_ownership(member_email, [account_id])
    if isinstance(ownership, dict):
        return ownership

    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: STS AssumeRole
    sts_client = boto3.client('sts')
    try:
        assume_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SlashMyBillConnectionTest',
            ExternalId=external_id,
        )
        credentials = assume_response['Credentials']
    except ClientError as e:
        logger.error(f"STS AssumeRole failed for {role_arn}: {e}")
        # Update status to failed
        _update_connection_status(accounts_table, member_email, account_id, 'failed', now_iso)
        return create_error_response(
            400, 'ConnectionFailed',
            f'The IAM role SlashMyBill-{account_id} was not found in account {account_id}. '
            'Please deploy the CloudFormation template first.'
        )

    # Step 2: Test Cost Explorer call with assumed credentials
    try:
        ce_client = boto3.client(
            'ce',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
        )

        # Query last 7 days
        end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        start_str = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')

        ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_str, 'End': end_date},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
        )
    except ClientError as e:
        logger.error(f"Cost Explorer call failed for {account_id}: {e}")
        _update_connection_status(accounts_table, member_email, account_id, 'partial', now_iso)
        return create_error_response(
            400, 'PartialConnection',
            'The role was assumed successfully, but Cost Explorer access was denied. '
            'Please verify the role policy includes ce:GetCostAndUsage permission.'
        )

    # Step 3: Probe hourly granularity availability
    hourly_enabled = False
    try:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=2)
        hourly_resp = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_dt.strftime('%Y-%m-%d'),
                'End': end_dt.strftime('%Y-%m-%d'),
            },
            Granularity='HOURLY',
            Metrics=['UnblendedCost'],
        )
        # If we get results with hourly data, it's enabled
        results = hourly_resp.get('ResultsByTime', [])
        hourly_enabled = len(results) > 2  # Daily would give <=2, hourly gives 24+
    except ClientError as e:
        err_code = (e.response or {}).get('Error', {}).get('Code', '')
        err_msg = (e.response or {}).get('Error', {}).get('Message', '')
        if 'BillNotEnabled' in err_code or 'hourly' in err_msg.lower() or 'granularity' in err_msg.lower():
            hourly_enabled = False
        else:
            logger.warning(f"Hourly probe failed for {account_id}: {e}")
            hourly_enabled = False

    # Full success
    _update_connection_status(accounts_table, member_email, account_id, 'connected', now_iso)

    # Store hourly status on the account record
    try:
        accounts_table.update_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            UpdateExpression='SET hourlyEnabled = :h',
            ExpressionAttributeValues={':h': hourly_enabled},
        )
    except ClientError:
        pass  # Non-critical

    logger.info(f"Connection test successful for account {account_id}, member {member_email}, hourly={hourly_enabled}")
    msg = 'Connection verified. Cost data is accessible.'
    if hourly_enabled:
        msg += ' Hourly granularity is enabled ✓'
    else:
        msg += ' Hourly granularity is NOT enabled — enable it in Cost Explorer Settings for real-time tracking.'
    return create_response(200, {'status': 'connected', 'hourlyEnabled': hourly_enabled, 'message': msg})


def handle_dashboard_data(event):
    """Return comprehensive FinOps dashboard data for selected accounts."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    # Get accountIds from query string (optional — if not provided, use all connected)
    qs = event.get('queryStringParameters') or {}
    requested_ids = (qs.get('accountIds') or '').split(',')
    requested_ids = [a.strip() for a in requested_ids if a.strip()]

    # Get all connected accounts
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
        )
        accounts = [a for a in result.get('Items', []) if a.get('connectionStatus') == 'connected']
    except ClientError:
        accounts = []

    # Filter to requested accounts if specified
    if requested_ids:
        accounts = [a for a in accounts if a['accountId'] in requested_ids]

    if not accounts:
        return create_response(200, {'summary': {'totalSpend': 0, 'totalAccounts': 0}})

    accounts.sort(key=lambda a: (a.get('sortOrder', 999), a.get('addedAt', '')))
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts_client = boto3.client('sts')

    merged_costs = {}
    merged_daily = {}
    merged_hourly = {}
    merged_monthly = {}
    merged_regional = {}
    drill_down_data = {}
    all_waste = []
    all_rightsizing = []
    per_account = []
    total_savings = 0
    savings_breakdown = {}
    containers = {'ecsClusters': [], 'eksClusters': []}
    all_discovered_metrics = []

    for acct in accounts[:5]:
        acct_id = acct['accountId']
        acct_name = acct.get('accountName', f'Account {acct_id[-4:]}')
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillDash', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']
            # Gather data with a broad question to trigger all checks
            acct_data, _ = _gather_account_data('how efficient is my account? rightsizing savings compare last 3 months', creds)

            acct_total = sum(s['cost_usd'] for s in acct_data.get('cost_by_service', []) if s.get('service') != 'Tax')
            for svc in acct_data.get('cost_by_service', []):
                if svc['service'] != 'Tax':
                    merged_costs[svc['service']] = merged_costs.get(svc['service'], 0) + svc['cost_usd']
            for d in acct_data.get('daily_cost_trend', []):
                merged_daily[d['date']] = merged_daily.get(d['date'], 0) + d['cost_usd']

            # Fetch 30-day daily trend for dashboard (the standard gather only does 7 days)
            try:
                ce_30d = boto3.client('ce',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'])
                end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                start_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
                daily_30d = ce_30d.get_cost_and_usage(
                    TimePeriod={'Start': start_30d, 'End': end_date},
                    Granularity='DAILY', Metrics=['UnblendedCost'],
                )
                for period in daily_30d.get('ResultsByTime', []):
                    d_date = period['TimePeriod']['Start']
                    d_cost = float(period['Total']['UnblendedCost']['Amount'])
                    merged_daily[d_date] = merged_daily.get(d_date, 0) + d_cost
            except Exception:
                pass  # Fall back to 7-day data from _gather_account_data

            # Fetch cost by region (last 30 days)
            try:
                region_resp = ce_30d.get_cost_and_usage(
                    TimePeriod={'Start': start_30d, 'End': end_date},
                    Granularity='MONTHLY', Metrics=['UnblendedCost'],
                    GroupBy=[{'Type': 'DIMENSION', 'Key': 'REGION'}],
                )
                for period in region_resp.get('ResultsByTime', []):
                    for group in period.get('Groups', []):
                        region_name = group['Keys'][0]
                        region_cost = float(group['Metrics']['UnblendedCost']['Amount'])
                        if region_cost > 0.01 and region_name:
                            merged_regional[region_name] = merged_regional.get(region_name, 0) + region_cost
            except Exception:
                pass

            # Fetch hourly usage metrics (last 24h) via CloudWatch for real-time waste detection
            try:
                cw_hourly = boto3.client('cloudwatch',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name='us-east-1')
                h_start = datetime.now(timezone.utc) - timedelta(hours=24)
                h_end = datetime.now(timezone.utc)

                # Try CE HOURLY first (most accurate if enabled)
                try:
                    hourly_resp = ce_30d.get_cost_and_usage(
                        TimePeriod={'Start': (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%d'),
                                    'End': datetime.now(timezone.utc).strftime('%Y-%m-%d')},
                        Granularity='HOURLY', Metrics=['UnblendedCost'],
                    )
                    for period in hourly_resp.get('ResultsByTime', []):
                        h_ts = period['TimePeriod']['Start'][:16]
                        h_cost = float(period['Total']['UnblendedCost']['Amount'])
                        if h_cost > 0:
                            merged_hourly[h_ts] = h_cost
                except Exception:
                    pass

                # If CE hourly didn't work, estimate from daily cost split into 24 hours
                if not merged_hourly:
                    # Use the last 3 days of daily data, split each day into 24 equal hours
                    for d in acct_data.get('daily_cost_trend', []):
                        daily_cost = d.get('cost_usd', 0)
                        if daily_cost > 0:
                            hourly_est = daily_cost / 24
                            for h in range(24):
                                ts = f"{d['date']}T{h:02d}:00"
                                merged_hourly[ts] = merged_hourly.get(ts, 0) + hourly_est

                    # Now overlay CloudWatch spikes on top of the flat estimate
                    # This shows WHERE the spikes happen even if we can't get exact hourly costs
                    metrics_to_check = [
                        ('AWS/EC2', 'NetworkIn', 0.09 / (1024**3)),  # $/byte
                        ('AWS/NATGateway', 'BytesOutToDestination', 0.045 / (1024**3)),
                        ('AWS/Lambda', 'Invocations', 0.0000002),
                    ]
                    for ns, metric, rate in metrics_to_check:
                        try:
                            resp = cw_hourly.get_metric_statistics(
                                Namespace=ns, MetricName=metric,
                                StartTime=h_start, EndTime=h_end, Period=3600, Statistics=['Sum'],
                            )
                            for dp in sorted(resp.get('Datapoints', []), key=lambda x: x['Timestamp']):
                                ts = dp['Timestamp'].strftime('%Y-%m-%dT%H:00')
                                est = dp['Sum'] * rate
                                if est > 0.001:
                                    merged_hourly[ts] = merged_hourly.get(ts, 0) + est
                        except Exception:
                            pass
            except Exception:
                pass

            # Fetch usage type breakdown for drill-down (top services)
            try:
                for svc in acct_data.get('cost_by_service', [])[:6]:
                    svc_name = svc.get('service', '')
                    if svc_name in ('Tax',) or svc.get('cost_usd', 0) < 1:
                        continue
                    try:
                        ut_resp = ce_30d.get_cost_and_usage(
                            TimePeriod={'Start': start_30d, 'End': end_date},
                            Granularity='MONTHLY', Metrics=['UnblendedCost'],
                            GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
                            Filter={'Dimensions': {'Key': 'SERVICE', 'Values': [svc_name]}},
                        )
                        usage_items = []
                        for p in ut_resp.get('ResultsByTime', []):
                            for g in p.get('Groups', []):
                                cost = float(g['Metrics']['UnblendedCost']['Amount'])
                                if cost > 0.01:
                                    usage_items.append({'usageType': g['Keys'][0], 'cost': round(cost, 4)})
                        if usage_items:
                            usage_items.sort(key=lambda x: x['cost'], reverse=True)
                            svc_key = svc_name.replace(' ', '_').replace('-', '_')
                            drill_down_data[svc_key] = {'service': svc_name, 'usageTypes': usage_items[:10]}
                    except Exception:
                        pass
            except Exception:
                pass

            for m, svcs in acct_data.get('monthly_trend', {}).items():
                if m not in merged_monthly:
                    merged_monthly[m] = {}
                for s, c in svcs.items():
                    merged_monthly[m][s] = merged_monthly[m].get(s, 0) + c

            # Waste items
            ebs = acct_data.get('ebs_summary', {})
            if ebs.get('unattached_count', 0) > 0:
                for v in ebs.get('unattached_volumes', []):
                    all_waste.append({'type': 'Unattached EBS', 'resource': v.get('volumeId', ''),
                                      'monthlyCost': v.get('monthly_cost_usd', 0), 'account': acct_id})
            eips = acct_data.get('elastic_ips', {})
            if eips.get('unattached', 0) > 0:
                all_waste.append({'type': 'Idle Elastic IPs', 'resource': f'{eips["unattached"]} EIPs',
                                  'monthlyCost': eips.get('unattached_monthly_cost_usd', 0), 'account': acct_id})
            kms = acct_data.get('kms_summary', {})
            if kms.get('monthly_cost_usd', 0) > 0:
                all_waste.append({'type': 'KMS Keys', 'resource': f'{kms.get("customer_managed_keys", 0)} keys',
                                  'monthlyCost': kms['monthly_cost_usd'], 'account': acct_id})

            # Rightsizing from Compute Optimizer
            for rec in acct_data.get('compute_optimizer_ec2', []):
                if rec.get('finding') == 'OVER_PROVISIONED':
                    all_rightsizing.append({
                        'resource': rec.get('instanceId', ''), 'currentType': rec.get('currentType', ''),
                        'recommendedType': rec.get('recommendedType', ''), 'finding': rec['finding'],
                        'monthlySavings': rec.get('estimatedMonthlySavings', 0), 'account': acct_id,
                    })

            # Efficiency
            eff = acct_data.get('cost_efficiency', {})
            acct_savings = eff.get('potential_savings_usd', 0)
            total_savings += acct_savings
            for k, v in eff.get('savings_breakdown', {}).items():
                savings_breakdown[k] = savings_breakdown.get(k, 0) + v

            # Containers
            for c in acct_data.get('ecs_clusters', []):
                containers['ecsClusters'].append({**c, 'account': acct_id})
            for c in acct_data.get('eks_clusters', []):
                containers['eksClusters'].append({**c, 'account': acct_id})
            # ECS service metrics
            for sm in acct_data.get('ecs_service_metrics', []):
                containers['ecsClusters'].append({**sm, 'account': acct_id, 'hasMetrics': True})

            # Auto-discover IT metrics for unit economics
            try:
                discovered = _auto_discover_it_metrics(creds)
                for d in discovered:
                    d['account'] = acct_id
                all_discovered_metrics.extend(discovered)
            except Exception:
                pass

            per_account.append({
                'accountId': acct_id, 'accountName': acct_name,
                'totalSpend': round(acct_total, 2),
                'efficiencyScore': eff.get('score', 0),
                'topServices': acct_data.get('cost_by_service', [])[:5],
            })
        except Exception as e:
            logger.warning(f"Dashboard data failed for {acct_id}: {e}")
            per_account.append({'accountId': acct_id, 'accountName': acct_name, 'error': str(e)})

    # Build response
    total_spend = round(sum(merged_costs.values()), 2)
    # MoM from monthly_trend: compare last two calendar months
    sorted_months = sorted(merged_monthly.keys())
    current_month_spend = 0
    prev_month_spend = 0
    if len(sorted_months) >= 1:
        current_month_spend = round(sum(merged_monthly[sorted_months[-1]].values()), 2)
    if len(sorted_months) >= 2:
        prev_month_spend = round(sum(merged_monthly[sorted_months[-2]].values()), 2)
    # Use total_spend from cost_by_service as the primary number, but MoM from trend
    if prev_month_spend > 0 and current_month_spend > 0:
        mom_change = round(((current_month_spend - prev_month_spend) / prev_month_spend * 100), 1)
    elif prev_month_spend > 0:
        mom_change = round(((total_spend - prev_month_spend) / prev_month_spend * 100), 1)
    else:
        mom_change = 0
    eff_score = round((1 - total_savings / total_spend) * 100, 1) if total_spend > 0 else 100

    # Daily trend with anomaly detection
    daily_list = sorted(merged_daily.items())
    daily_costs = [c for _, c in daily_list]
    avg_daily = sum(daily_costs) / len(daily_costs) if daily_costs else 0
    daily_trend = []
    for date, cost in daily_list:
        is_anomaly = cost > avg_daily * 2 and avg_daily > 0
        daily_trend.append({
            'date': date, 'cost': round(cost, 4),
            'isAnomaly': is_anomaly,
            'spikePct': round((cost / avg_daily - 1) * 100, 1) if is_anomaly else 0,
        })

    cost_by_service = sorted(
        [{'service': s, 'cost': round(c, 2), 'pct': round(c / total_spend * 100, 1) if total_spend > 0 else 0}
         for s, c in merged_costs.items() if c > 0.01],
        key=lambda x: x['cost'], reverse=True
    )

    over_count = sum(1 for r in all_rightsizing if r['finding'] == 'OVER_PROVISIONED')
    all_rightsizing.sort(key=lambda x: x.get('monthlySavings', 0), reverse=True)

    # Load and apply allocation rules (Virtual Tagging)
    allocation_data = None
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = members_table.get_item(Key={'email': member_email}).get('Item') or {}
        alloc_rules = member.get('allocationRules') or []
        if alloc_rules:
            allocation_data = _apply_allocation_rules(cost_by_service, per_account, alloc_rules)
    except Exception as e:
        logger.warning(f"Allocation rules error: {e}")

    return create_response(200, {
        'summary': {
            'totalSpend': total_spend,
            'previousMonthSpend': prev_month_spend,
            'monthOverMonthChange': mom_change,
            'efficiencyScore': max(0, eff_score),
            'efficiencyRating': 'Excellent' if eff_score >= 90 else 'Good' if eff_score >= 75 else 'Needs Improvement' if eff_score >= 50 else 'Critical',
            'potentialSavings': round(total_savings, 2),
            'savingsBreakdown': {k: round(v, 2) for k, v in savings_breakdown.items()},
            'totalAccounts': len(accounts),
            'accountsAnalyzed': len([a for a in per_account if 'error' not in a]),
        },
        'costByService': cost_by_service,
        'dailyTrend': daily_trend,
        'monthlyTrend': {m: {s: round(c, 2) for s, c in svcs.items()} for m, svcs in merged_monthly.items()},
        'rightsizing': {
            'overProvisioned': over_count,
            'topOpportunities': all_rightsizing[:5],
        },
        'waste': {
            'totalWaste': round(sum(w['monthlyCost'] for w in all_waste), 2),
            'items': all_waste,
        },
        'perAccount': per_account,
        'containers': containers,
        'costAllocation': allocation_data,
        'hourlyTrend': sorted([{'hour': h, 'cost': round(c, 4)} for h, c in merged_hourly.items()], key=lambda x: x['hour']) if merged_hourly else [],
        'drillDown': drill_down_data,
        'unitEconomics': _get_unit_economics(member_email, merged_monthly) if merged_monthly else None,
        'discoveredMetrics': all_discovered_metrics,
        'costByRegion': sorted(
            [{'region': r, 'cost': round(c, 2), 'pct': round(c / total_spend * 100, 1) if total_spend > 0 else 0}
             for r, c in merged_regional.items() if c > 0.01],
            key=lambda x: x['cost'], reverse=True
        ),
        'commitments': _get_commitments_data(accounts, external_id),
        'costByTag': _get_cost_by_tag(accounts, external_id),
    })


def _get_commitments_data(accounts, external_id):
    """Fetch Savings Plans and Reserved Instances across all connected accounts."""
    sts_client = boto3.client('sts')
    all_sp = []
    all_ri_ec2 = []
    all_ri_rds = []
    sp_coverage = {}
    ri_coverage = {}

    for acct in accounts[:5]:
        acct_id = acct['accountId']
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillCommit', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']

            # Savings Plans
            try:
                sp_client = boto3.client('savingsplans',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name='us-east-1')
                sp_resp = sp_client.describe_savings_plans(
                    States=['active', 'queued', 'queued-deleted']
                )
                for sp in sp_resp.get('savingsPlans', []):
                    all_sp.append({
                        'id': sp.get('savingsPlanId', ''),
                        'type': sp.get('savingsPlanType', ''),
                        'paymentOption': sp.get('paymentOption', ''),
                        'commitment': float(sp.get('commitment', '0')),
                        'currency': sp.get('currency', 'USD'),
                        'term': sp.get('termDurationInSeconds', 0) // (365 * 86400),
                        'state': sp.get('state', ''),
                        'start': sp.get('start', ''),
                        'end': sp.get('end', ''),
                        'account': acct_id,
                    })
            except Exception as e:
                logger.warning(f"SP fetch failed for {acct_id}: {e}")

            # EC2 Reserved Instances
            try:
                ec2 = boto3.client('ec2',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name='us-east-1')
                ri_resp = ec2.describe_reserved_instances(
                    Filters=[{'Name': 'state', 'Values': ['active']}]
                )
                for ri in ri_resp.get('ReservedInstances', []):
                    all_ri_ec2.append({
                        'id': ri.get('ReservedInstancesId', ''),
                        'instanceType': ri.get('InstanceType', ''),
                        'count': ri.get('InstanceCount', 0),
                        'offeringClass': ri.get('OfferingClass', ''),
                        'offeringType': ri.get('OfferingType', ''),
                        'fixedPrice': float(ri.get('FixedPrice', 0)),
                        'usagePrice': float(ri.get('UsagePrice', 0)),
                        'duration': ri.get('Duration', 0) // (365 * 86400),
                        'start': ri.get('Start', '').isoformat() if hasattr(ri.get('Start', ''), 'isoformat') else str(ri.get('Start', '')),
                        'end': ri.get('End', '').isoformat() if hasattr(ri.get('End', ''), 'isoformat') else str(ri.get('End', '')),
                        'state': ri.get('State', ''),
                        'account': acct_id,
                    })
            except Exception as e:
                logger.warning(f"EC2 RI fetch failed for {acct_id}: {e}")

            # RDS Reserved Instances
            try:
                rds = boto3.client('rds',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name='us-east-1')
                rds_ri_resp = rds.describe_reserved_db_instances()
                for ri in rds_ri_resp.get('ReservedDBInstances', []):
                    if ri.get('State') == 'active':
                        all_ri_rds.append({
                            'id': ri.get('ReservedDBInstanceId', ''),
                            'dbInstanceClass': ri.get('DBInstanceClass', ''),
                            'count': ri.get('DBInstanceCount', 0),
                            'engine': ri.get('ProductDescription', ''),
                            'offeringType': ri.get('OfferingType', ''),
                            'fixedPrice': float(ri.get('FixedPrice', 0)),
                            'duration': ri.get('Duration', 0) // (365 * 86400),
                            'start': ri.get('StartTime', '').isoformat() if hasattr(ri.get('StartTime', ''), 'isoformat') else str(ri.get('StartTime', '')),
                            'state': ri.get('State', ''),
                            'account': acct_id,
                        })
            except Exception as e:
                logger.warning(f"RDS RI fetch failed for {acct_id}: {e}")

            # SP Coverage (last 30 days)
            try:
                ce = boto3.client('ce',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'])
                end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')

                sp_cov = ce.get_savings_plans_coverage(
                    TimePeriod={'Start': start_date, 'End': end_date},
                    Granularity='MONTHLY',
                )
                for period in sp_cov.get('SavingsPlansCoverages', []):
                    cov = period.get('Coverage', {})
                    sp_coverage[acct_id] = {
                        'coveragePct': float(cov.get('CoveragePercentage', '0')),
                        'spendCovered': float(cov.get('SpendCoveredBySavingsPlans', '0')),
                        'onDemandCost': float(cov.get('OnDemandCost', '0')),
                        'totalCost': float(cov.get('TotalCost', '0')),
                    }
            except Exception:
                pass

            # RI Coverage (last 30 days)
            try:
                ri_cov = ce.get_reservation_coverage(
                    TimePeriod={'Start': start_date, 'End': end_date},
                    Granularity='MONTHLY',
                )
                for period in ri_cov.get('CoveragesByTime', []):
                    total = period.get('Total', {}).get('CoverageHours', {})
                    ri_coverage[acct_id] = {
                        'coveragePct': float(total.get('CoverageHoursPercentage', '0')),
                        'reservedHours': float(total.get('ReservedHours', '0')),
                        'totalRunningHours': float(total.get('TotalRunningHours', '0')),
                        'onDemandHours': float(total.get('OnDemandHours', '0')),
                    }
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Commitments fetch failed for {acct_id}: {e}")

    return {
        'savingsPlans': all_sp,
        'ec2ReservedInstances': all_ri_ec2,
        'rdsReservedInstances': all_ri_rds,
        'spCoverage': sp_coverage,
        'riCoverage': ri_coverage,
        'totalSP': len(all_sp),
        'totalEC2RI': sum(r['count'] for r in all_ri_ec2),
        'totalRDSRI': sum(r['count'] for r in all_ri_rds),
    }


def _get_cost_by_tag(accounts, external_id):
    """Query Cost Explorer grouped by tag keys to show cost allocation by tags."""
    sts_client = boto3.client('sts')
    end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')

    # Collect available tag keys and cost-by-tag data across accounts
    all_tag_keys = set()
    tag_costs = {}  # {tag_key: {tag_value: cost}}

    for acct in accounts[:5]:
        acct_id = acct['accountId']
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillTags', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']
            ce = boto3.client('ce',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'])

            # Get available tag keys
            try:
                tags_resp = ce.get_tags(
                    TimePeriod={'Start': start_date, 'End': end_date},
                )
                for tag in tags_resp.get('Tags', []):
                    if tag and not tag.startswith('aws:'):
                        all_tag_keys.add(tag)
            except Exception as e:
                logger.warning(f"get_tags failed for {acct_id}: {e}")

            # Query cost by the most common FinOps tag keys
            priority_keys = ['Environment', 'environment', 'Env', 'env',
                             'CostCenter', 'costCenter', 'cost-center',
                             'Owner', 'owner', 'Team', 'team',
                             'Application', 'application', 'app', 'App',
                             'Project', 'project', 'Department', 'department']

            # Use discovered keys that match priority, or first 5 discovered
            query_keys = [k for k in priority_keys if k in all_tag_keys]
            remaining = [k for k in all_tag_keys if k not in query_keys]
            query_keys = query_keys[:5]
            if len(query_keys) < 5:
                query_keys.extend(remaining[:5 - len(query_keys)])

            for tag_key in query_keys[:5]:
                try:
                    resp = ce.get_cost_and_usage(
                        TimePeriod={'Start': start_date, 'End': end_date},
                        Granularity='MONTHLY',
                        Metrics=['UnblendedCost'],
                        GroupBy=[{'Type': 'TAG', 'Key': tag_key}],
                    )
                    if tag_key not in tag_costs:
                        tag_costs[tag_key] = {}
                    for period in resp.get('ResultsByTime', []):
                        for group in period.get('Groups', []):
                            raw_key = group['Keys'][0]
                            # CE returns "tagKey$tagValue" format
                            tag_val = raw_key.split('$', 1)[1] if '$' in raw_key else raw_key
                            if not tag_val:
                                tag_val = '(untagged)'
                            cost = float(group['Metrics']['UnblendedCost']['Amount'])
                            if cost > 0.01:
                                tag_costs[tag_key][tag_val] = tag_costs[tag_key].get(tag_val, 0) + cost
                except Exception as e:
                    logger.warning(f"Cost by tag '{tag_key}' failed for {acct_id}: {e}")

        except Exception as e:
            logger.warning(f"Tag data failed for {acct_id}: {e}")

    # Build response
    result = {}
    for tag_key, values in tag_costs.items():
        if not values:
            continue
        total = sum(values.values())
        untagged = values.pop('(untagged)', 0)
        tagged_total = total - untagged
        coverage = round(tagged_total / total * 100, 1) if total > 0 else 0

        sorted_vals = sorted(
            [{'tag': v, 'cost': round(c, 2), 'pct': round(c / total * 100, 1) if total > 0 else 0}
             for v, c in values.items()],
            key=lambda x: x['cost'], reverse=True
        )
        if untagged > 0.01:
            sorted_vals.append({'tag': '(untagged)', 'cost': round(untagged, 2),
                                'pct': round(untagged / total * 100, 1) if total > 0 else 0})

        result[tag_key] = {
            'values': sorted_vals[:15],
            'total': round(total, 2),
            'coverage': coverage,
        }

    return {
        'tagKeys': sorted(list(all_tag_keys)),
        'data': result,
    } if all_tag_keys else {}


def handle_get_dashboard(event):
    """Return saved dashboard/favorite query items for the authenticated member."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)

    try:
        item = members_table.get_item(Key={'email': member_email}).get('Item') or {}
    except ClientError as e:
        logger.error(f"DynamoDB read error (dashboard): {e}")
        return create_error_response(500, 'ServerError', 'Failed to load dashboard items')

    favorites = item.get('favoriteQueries') or []
    if not isinstance(favorites, list):
        favorites = []
    return create_response(200, {'items': _decimal_to_native(favorites)})


def handle_add_dashboard_item(event):
    """Add a new dashboard item (table/graph) to the member profile."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    view_type = (body.get('viewType') or '').strip().lower()
    prompt = (body.get('prompt') or '').strip()
    title = (body.get('title') or '').strip()
    answer = (body.get('answer') or '').strip()
    account_id = (body.get('accountId') or '').strip()
    chart_config = body.get('chartConfig')

    if view_type not in ('graph', 'table'):
        return create_error_response(400, 'InvalidRequest', "viewType must be 'graph' or 'table'")
    if not prompt:
        return create_error_response(400, 'InvalidRequest', 'Prompt is required')

    now_iso = datetime.now(timezone.utc).isoformat()
    item_id = hashlib.sha256(f'{member_email}|{prompt}|{now_iso}'.encode('utf-8')).hexdigest()[:16]
    item = {
        'id': item_id,
        'title': title or prompt[:80],
        'prompt': prompt,
        'answer': answer,
        'viewType': view_type,
        'accountId': account_id,
        'chartConfig': chart_config if isinstance(chart_config, dict) else None,
        'createdAt': now_iso,
    }

    try:
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET favoriteQueries = list_append(if_not_exists(favoriteQueries, :empty), :item)',
            ExpressionAttributeValues={
                ':empty': [],
                ':item': [item],
            },
        )
    except ClientError as e:
        logger.error(f"DynamoDB update error (dashboard add): {e}")
        return create_error_response(500, 'ServerError', 'Failed to save dashboard item')

    return create_response(201, {'message': 'Dashboard item saved', 'item': item})


def handle_delete_dashboard_item(event):
    """Delete a dashboard item from the member profile by item id."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    item_id = (body.get('id') or '').strip()
    if not item_id:
        return create_error_response(400, 'InvalidRequest', 'Item id is required')

    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item') or {}
        current = member.get('favoriteQueries') or []
        filtered = [it for it in current if str(it.get('id', '')) != item_id]
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET favoriteQueries = :items',
            ExpressionAttributeValues={':items': filtered},
        )
    except ClientError as e:
        logger.error(f"DynamoDB update error (dashboard delete): {e}")
        return create_error_response(500, 'ServerError', 'Failed to delete dashboard item')

    return create_response(200, {'message': 'Dashboard item deleted', 'id': item_id})


# ============================================================
# Cost Allocation Rules (Virtual Tagging)
# ============================================================

def handle_get_allocation_rules(event):
    """Get the member's cost allocation rules."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item') or {}
        rules = member.get('allocationRules') or []
    except ClientError:
        rules = []
    return create_response(200, {'rules': _decimal_to_native(rules)})


def handle_save_allocation_rules(event):
    """Save the member's virtual tagging business units and rules."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    business_units = body.get('businessUnits', [])
    shared_cost_mode = body.get('sharedCostMode', 'proportional')  # even, proportional, custom
    custom_splits = body.get('customSplits', {})  # {buName: percentage}

    if not isinstance(business_units, list):
        return create_error_response(400, 'InvalidRequest', '"businessUnits" must be an array')

    # Validate and normalize business units
    valid_units = []
    for bu in business_units[:20]:  # max 20 business units
        unit = {
            'name': str(bu.get('name', '')).strip()[:100],
            'ruleLogic': bu.get('ruleLogic', 'or') if bu.get('ruleLogic') in ('or', 'and') else 'or',
            'rules': [],
        }
        for r in (bu.get('rules') or [])[:10]:  # max 10 rules per BU
            rule = {
                'dimension': r.get('dimension', 'account'),  # account, service, tag
                'operator': r.get('operator', 'equals'),  # equals, contains, startsWith
                'value': str(r.get('value', '')).strip()[:200],
            }
            if rule['value']:
                unit['rules'].append(rule)
        if unit['name'] and unit['rules']:
            valid_units.append(unit)

    now_iso = datetime.now(timezone.utc).isoformat()
    allocation_config = {
        'businessUnits': valid_units,
        'sharedCostMode': shared_cost_mode if shared_cost_mode in ('even', 'proportional', 'custom') else 'proportional',
        'customSplits': {k: min(100, max(0, float(v))) for k, v in (custom_splits or {}).items()} if shared_cost_mode == 'custom' else {},
        'status': 'processing',
        'updatedAt': now_iso,
    }

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET allocationRules = :rules',
            ExpressionAttributeValues={':rules': allocation_config},
        )
    except ClientError as e:
        logger.error(f"Failed to save allocation rules: {e}")
        return create_error_response(500, 'ServerError', 'Failed to save rules')

    return create_response(200, {
        'message': 'Business units saved! Your Dashboard will reflect these allocations within 24 hours.',
        'count': len(valid_units),
        'status': 'processing',
    })


BUSINESS_METRICS_TABLE = os.environ.get('BUSINESS_METRICS_TABLE', 'MemberPortal-BusinessMetrics')


def handle_get_business_metrics(event):
    """Get business metrics for the member."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        table = dynamodb.Table(BUSINESS_METRICS_TABLE)
        result = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email),
            ScanIndexForward=False,
            Limit=24,  # last 24 months
        )
        metrics = _decimal_to_native(result.get('Items', []))
    except ClientError:
        metrics = []
    return create_response(200, {'metrics': metrics})


def handle_save_business_metrics(event):
    """Save or update a business metric for a specific month."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    metric_month = (body.get('metricMonth') or '').strip()  # e.g. "2026-03"
    metric_name = (body.get('metricName') or '').strip()[:100]
    metric_volume = body.get('metricVolume', 0)

    if not metric_month or not metric_name:
        return create_error_response(400, 'InvalidRequest', 'metricMonth and metricName are required')

    try:
        metric_volume = float(metric_volume)
    except (ValueError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'metricVolume must be a number')

    table = dynamodb.Table(BUSINESS_METRICS_TABLE)
    try:
        table.put_item(Item={
            'memberEmail': member_email,
            'metricMonth': metric_month,
            'metricName': metric_name,
            'metricVolume': Decimal(str(metric_volume)),
            'businessUnitLink': (body.get('businessUnitLink') or '').strip()[:100] or None,
            'updatedAt': datetime.now(timezone.utc).isoformat(),
        })
    except ClientError as e:
        logger.error(f"Failed to save business metric: {e}")
        return create_error_response(500, 'ServerError', 'Failed to save metric')

    return create_response(200, {'message': 'Business metric saved'})


# ============================================================
# Act Tab — Level 1 Resource Hygiene Scan & Execute
# ============================================================

def _assume_role_for_account(member_email, account_id):
    """Assume cross-account role and return boto3 credentials dict, or raise."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts = boto3.client('sts')
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName='SlashMyBillAct', ExternalId=external_id)
    return resp['Credentials']


def _make_client_from_creds(service, creds, region='us-east-1'):
    return boto3.client(
        service,
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name=region,
    )



def handle_actions_scan(event):
    """Tips-driven scan engine v2."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    # Credits check: scan costs 10 credits for Free tier
    tier = _get_member_tier(member_email)
    credit_err = _check_and_consume_credits(member_email, tier, SCAN_CREDIT_COST)
    if credit_err:
        return credit_err

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_ids = body.get('accountIds') or []
    if not account_ids:
        accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
        try:
            result = accounts_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
            )
            account_ids = [a['accountId'] for a in result.get('Items', []) if a.get('connectionStatus') == 'connected']
        except ClientError:
            return create_error_response(500, 'ServerError', 'Failed to load accounts')

    if not account_ids:
        return create_response(200, {'cards': [], 'totalSavings': 0, 'findings': []})

    ownership = _verify_account_ownership(member_email, account_ids)
    if isinstance(ownership, dict):
        return ownership

    # ── Step 1: Load tips from DynamoDB (ground truth) ────────────────────
    tips = _load_tips_from_db()

    all_cards = []
    all_findings = []
    total_savings = 0.0

    for account_id in account_ids[:5]:
        try:
            creds = _assume_role_for_account(member_email, account_id)
        except Exception as e:
            logger.warning(f"Cannot assume role for {account_id}: {e}")
            continue

        acct_label = f'Account {account_id[-4:]}'

        # ── Step 2: Collect service data ──────────────────────────────────
        svc_data = _collect_service_data(account_id, creds)

        # ── Step 3: Determine active services from CE cost data ───────────
        active_services = _get_active_services(svc_data.get('cost_by_service', []))

        # ── Step 4: Evaluate each tip against collected data ──────────────
        for tip in tips:
            svc_key = tip.get('serviceKey', tip.get('service', 'General'))
            # Gate: only evaluate if service is present (General always runs)
            if svc_key != 'General' and svc_key not in active_services:
                continue

            tip_id = tip.get('tipId', '')
            check_fn = _SCAN_REGISTRY.get(tip_id)

            if check_fn and tip.get('checkImplemented', False):
                try:
                    finding = check_fn(tip, svc_data, account_id, acct_label, creds)
                    if finding:
                        finding['tipId'] = tip_id
                        finding['level'] = tip.get('level', 2)
                        finding['actionType'] = tip.get('actionType', 'advisory')
                        finding['actionLabel'] = tip.get('actionLabel', 'View')
                        finding['tipTitle'] = tip.get('title', '')
                        finding['service'] = tip.get('service', '')
                        all_findings.append(finding)
                        if finding.get('cardData'):
                            card = finding['cardData']
                            card['accountId'] = account_id
                            card['accountLabel'] = acct_label
                            all_cards.append(card)
                            total_savings += card.get('monthlySavings') or 0
                except Exception as e:
                    logger.warning(f"Check {tip_id} failed for {account_id}: {e}")
            elif not tip.get('checkImplemented', False):
                # Placeholder finding for tips not yet implemented
                all_findings.append({
                    'tipId': tip_id,
                    'level': tip.get('level', 2),
                    'actionType': 'pending',
                    'actionLabel': 'Coming Soon',
                    'tipTitle': tip.get('title', ''),
                    'service': tip.get('service', ''),
                    'status': 'pending',
                    'accountId': account_id,
                    'note': 'Check not yet implemented — will be added in a future update',
                })

    # Deduplicate cards: merge multiple cards of the same type+account into one
    # (happens when multiple tips map to the same check function, e.g. s3-002 and s3-003)
    seen_card_ids = {}
    deduped_cards = []
    for card in all_cards:
        cid = card.get('cardId', '')
        if cid not in seen_card_ids:
            seen_card_ids[cid] = card
            deduped_cards.append(card)
        else:
            # Merge resources from duplicate into existing card
            existing = seen_card_ids[cid]
            existing_res = existing.get('resources') or []
            new_res = card.get('resources') or []
            # Add resources not already present (by id/name)
            existing_ids = {r.get('id') or r.get('name') for r in existing_res}
            for r in new_res:
                rid = r.get('id') or r.get('name')
                if rid not in existing_ids:
                    existing_res.append(r)
                    existing_ids.add(rid)
            existing['resources'] = existing_res
            existing['count'] = len(existing_res)
    all_cards = deduped_cards

    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)

    scanned_at = datetime.now(timezone.utc).isoformat()
    result = create_response(200, {
        'cards': all_cards,
        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': scanned_at,
    })

    # Cache top findings for the Chat widget
    _save_last_scan(member_email, account_ids, all_findings[:10], round(total_savings, 2), scanned_at)

    return result


def _load_tips_from_db():
    """Load all tips from DynamoDB tips table."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        result = tips_table.scan()
        return _decimal_to_native(result.get('Items', []))
    except Exception as e:
        logger.warning(f"Failed to load tips from DynamoDB: {e}")
        return []


def _get_active_services(cost_by_service):
    """Return set of service names that have actual spend (> $0.01)."""
    active = set()
    for svc in cost_by_service:
        cost = svc.get('cost_usd', 0)
        if cost > 0.01:
            name = svc.get('service', '')
            active.add(name)
            # Also add normalized aliases
            if 'EC2' in name and 'Other' not in name:
                active.add('Amazon EC2')
            if 'EC2 - Other' in name:
                active.add('EC2 - Other')
            if 'S3' in name or 'Simple Storage' in name:
                active.add('Amazon Simple Storage Service')
            if 'RDS' in name or 'Relational Database' in name:
                active.add('Amazon Relational Database Service')
            if 'Lambda' in name:
                active.add('AWS Lambda')
            if 'VPC' in name or 'Virtual Private Cloud' in name:
                active.add('Amazon Virtual Private Cloud')
            if 'Load Balancing' in name or 'ELB' in name:
                active.add('Amazon Elastic Load Balancing')
            if 'KMS' in name or 'Key Management' in name:
                active.add('AWS Key Management Service')
            if 'Container Service' in name or 'ECS' in name:
                active.add('Amazon Elastic Container Service')
            if 'Kubernetes' in name or 'EKS' in name:
                active.add('Amazon Elastic Kubernetes Service')
            if 'ElastiCache' in name:
                active.add('Amazon ElastiCache')
            if 'DynamoDB' in name:
                active.add('Amazon DynamoDB')
            if 'CloudFront' in name:
                active.add('Amazon CloudFront')
            if 'Elastic File' in name or 'EFS' in name:
                active.add('Amazon Elastic File System')
    return active


def _collect_service_data(account_id, creds):
    """Collect all service data needed for tip evaluation. Fast, parallel-friendly."""
    data = {}
    now_dt = datetime.now(timezone.utc)

    try:
        ec2 = _make_client_from_creds('ec2', creds)
        cw = _make_client_from_creds('cloudwatch', creds)

        # CE: cost by service (last 30 days) — determines active services
        try:
            ce = _make_client_from_creds('ce', creds)
            end_date = now_dt.strftime('%Y-%m-%d')
            start_date = (now_dt - timedelta(days=30)).strftime('%Y-%m-%d')
            ce_resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY', Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
            data['cost_by_service'] = [
                {'service': g['Keys'][0], 'cost_usd': float(g['Metrics']['UnblendedCost']['Amount'])}
                for period in ce_resp.get('ResultsByTime', [])
                for g in period.get('Groups', [])
                if float(g['Metrics']['UnblendedCost']['Amount']) > 0.01
            ]
        except Exception as e:
            logger.warning(f"CE cost_by_service failed for {account_id}: {e}")
            data['cost_by_service'] = []

        # EIPs
        try:
            eips = ec2.describe_addresses()
            data['elastic_ips'] = eips.get('Addresses', [])
        except Exception:
            data['elastic_ips'] = []

        # EBS volumes (unattached)
        try:
            vols = ec2.describe_volumes(Filters=[{'Name': 'status', 'Values': ['available']}])
            data['unattached_volumes'] = vols.get('Volumes', [])
        except Exception:
            data['unattached_volumes'] = []

        # EBS snapshots (own account, capped at 200)
        try:
            snaps = ec2.describe_snapshots(OwnerIds=['self'], MaxResults=200)
            data['snapshots'] = snaps.get('Snapshots', [])
        except Exception:
            data['snapshots'] = []

        # EC2 running instances
        try:
            inst_resp = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            data['ec2_instances'] = [
                inst
                for r in inst_resp.get('Reservations', [])
                for inst in r.get('Instances', [])
            ]
        except Exception:
            data['ec2_instances'] = []

        # S3 buckets + lifecycle check
        try:
            s3 = _make_client_from_creds('s3', creds)
            buckets = s3.list_buckets().get('Buckets', [])
            bucket_data = []
            for b in buckets[:20]:
                bname = b['Name']
                has_lc = False
                try:
                    lc = s3.get_bucket_lifecycle_configuration(Bucket=bname)
                    has_lc = bool(lc.get('Rules', []))
                except ClientError as ce_err:
                    if ce_err.response['Error']['Code'] != 'NoSuchLifecycleConfiguration':
                        pass
                except Exception:
                    pass
                # Quick activity check
                last_modified_days = None
                try:
                    sample = s3.list_objects_v2(Bucket=bname, MaxKeys=5)
                    contents = sample.get('Contents', [])
                    if contents:
                        latest = max(contents, key=lambda o: o['LastModified'])
                        last_modified_days = (now_dt - latest['LastModified'].replace(tzinfo=timezone.utc)).days
                except Exception:
                    pass
                bucket_data.append({
                    'name': bname,
                    'created': str(b.get('CreationDate', '')),
                    'hasLifecycle': has_lc,
                    'lastModifiedDays': last_modified_days,
                })
            data['s3_buckets'] = bucket_data
        except Exception:
            data['s3_buckets'] = []

        # RDS instances
        try:
            rds = _make_client_from_creds('rds', creds)
            data['rds_instances'] = [
                d for d in rds.describe_db_instances().get('DBInstances', [])
                if d.get('DBInstanceStatus') == 'available'
            ]
        except Exception:
            data['rds_instances'] = []

        # Lambda functions
        try:
            lam = _make_client_from_creds('lambda', creds)
            data['lambda_functions'] = lam.list_functions().get('Functions', [])
        except Exception:
            data['lambda_functions'] = []

        # Load balancers
        try:
            elbv2 = _make_client_from_creds('elbv2', creds)
            data['load_balancers'] = elbv2.describe_load_balancers().get('LoadBalancers', [])
        except Exception:
            data['load_balancers'] = []

        # KMS customer-managed keys
        try:
            kms = _make_client_from_creds('kms', creds)
            keys = kms.list_keys().get('Keys', [])
            aliases = kms.list_aliases().get('Aliases', [])
            alias_map = {a.get('TargetKeyId'): a.get('AliasName', '') for a in aliases}
            cmks = [k for k in keys if not alias_map.get(k['KeyId'], '').startswith('alias/aws/')]
            data['kms_customer_keys'] = cmks
        except Exception:
            data['kms_customer_keys'] = []

        # Budgets
        try:
            budgets_client = _make_client_from_creds('budgets', creds)
            blist = budgets_client.describe_budgets(AccountId=account_id).get('Budgets', [])
            data['budgets'] = blist
        except Exception:
            data['budgets'] = []

        # Batch CloudWatch: EC2 CPU (14d avg) for idle detection
        if data.get('ec2_instances'):
            try:
                queries = []
                for i, inst in enumerate(data['ec2_instances'][:15]):
                    queries.append({
                        'Id': f'cpu{i}',
                        'MetricStat': {
                            'Metric': {'Namespace': 'AWS/EC2', 'MetricName': 'CPUUtilization',
                                       'Dimensions': [{'Name': 'InstanceId', 'Value': inst['InstanceId']}]},
                            'Period': 1209600, 'Stat': 'Average',
                        }, 'ReturnData': True,
                    })
                cw_resp = cw.get_metric_data(
                    MetricDataQueries=queries,
                    StartTime=now_dt - timedelta(days=14), EndTime=now_dt,
                )
                data['ec2_cpu_14d'] = {
                    data['ec2_instances'][int(r['Id'].replace('cpu', ''))]['InstanceId']: r['Values'][0]
                    for r in cw_resp.get('MetricDataResults', [])
                    if r.get('Values')
                }
            except Exception:
                data['ec2_cpu_14d'] = {}

        # Batch CloudWatch: RDS CPU + connections (14d)
        if data.get('rds_instances'):
            try:
                queries = []
                for i, db in enumerate(data['rds_instances'][:8]):
                    db_id = db['DBInstanceIdentifier']
                    queries.append({'Id': f'cpu{i}', 'MetricStat': {'Metric': {'Namespace': 'AWS/RDS', 'MetricName': 'CPUUtilization', 'Dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': db_id}]}, 'Period': 1209600, 'Stat': 'Average'}, 'ReturnData': True})
                    queries.append({'Id': f'conn{i}', 'MetricStat': {'Metric': {'Namespace': 'AWS/RDS', 'MetricName': 'DatabaseConnections', 'Dimensions': [{'Name': 'DBInstanceIdentifier', 'Value': db_id}]}, 'Period': 1209600, 'Stat': 'Maximum'}, 'ReturnData': True})
                cw_resp = cw.get_metric_data(MetricDataQueries=queries, StartTime=now_dt - timedelta(days=14), EndTime=now_dt)
                cpu_map, conn_map = {}, {}
                for r in cw_resp.get('MetricDataResults', []):
                    idx = int(r['Id'][3:])
                    db_id = data['rds_instances'][idx]['DBInstanceIdentifier']
                    if r['Id'].startswith('cpu') and r.get('Values'):
                        cpu_map[db_id] = r['Values'][0]
                    elif r['Id'].startswith('conn') and r.get('Values'):
                        conn_map[db_id] = r['Values'][0]
                data['rds_cpu_14d'] = cpu_map
                data['rds_conn_14d'] = conn_map
            except Exception:
                data['rds_cpu_14d'] = {}
                data['rds_conn_14d'] = {}

    except Exception as e:
        logger.warning(f"Service data collection error for {account_id}: {e}")

    return data


# ============================================================
# Scan Check Registry — maps tip.id → check function
# Each function returns a finding dict or None (no issue found)
# finding dict: {status, savingsUsd, cardData (optional), evidence}
# ============================================================

def _check_ebs_unattached(tip, data, account_id, acct_label, creds):
    vols = data.get('unattached_volumes', [])
    if not vols:
        return None
    total_gb = sum(v.get('Size', 0) for v in vols)
    savings = total_gb * 0.10
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(vols)} unattached volumes, {total_gb} GB',
        'cardData': {
            'cardId': f'ebs-{account_id}', 'type': 'ebs-volume',
            'title': 'Unattached EBS Volumes', 'icon': '💾',
            'count': len(vols), 'risk': 'low',
            'description': f'{len(vols)} volume(s) totalling {total_gb} GB not attached to any instance',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': v['VolumeId'], 'size': v.get('Size', 0), 'type': v.get('VolumeType', ''), 'az': v.get('AvailabilityZone', '')} for v in vols],
        }
    }


def _check_ebs_snapshots(tip, data, account_id, acct_label, creds):
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    stale = []
    total_gb = 0
    for snap in data.get('snapshots', []):
        st = snap.get('StartTime')
        if st and st.replace(tzinfo=timezone.utc) < cutoff:
            age = (datetime.now(timezone.utc) - st.replace(tzinfo=timezone.utc)).days
            gb = snap.get('VolumeSize', 0)
            total_gb += gb
            stale.append({'id': snap['SnapshotId'], 'size': gb, 'ageDays': age, 'description': snap.get('Description', '')[:60]})
    if not stale:
        return None
    savings = total_gb * 0.05
    stale.sort(key=lambda s: s['ageDays'], reverse=True)
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(stale)} snapshots >180d, {total_gb} GB',
        'cardData': {
            'cardId': f'snap-{account_id}', 'type': 'ebs-snapshot',
            'title': 'Stale EBS Snapshots', 'icon': '📸',
            'count': len(stale), 'risk': 'low',
            'description': f'{len(stale)} snapshot(s) older than 180 days — {total_gb} GB total',
            'monthlySavings': round(savings, 2),
            'resources': stale[:20],
        }
    }


def _check_eip_unattached(tip, data, account_id, acct_label, creds):
    unattached = [a for a in data.get('elastic_ips', []) if not a.get('AssociationId')]
    if not unattached:
        return None
    savings = len(unattached) * 3.65
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(unattached)} unassociated EIPs',
        'cardData': {
            'cardId': f'eip-{account_id}', 'type': 'elastic-ip',
            'title': 'Unassociated Elastic IPs', 'icon': '🌐',
            'count': len(unattached), 'risk': 'low',
            'description': f'{len(unattached)} Elastic IP(s) not attached to any instance',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': a['AllocationId'], 'ip': a.get('PublicIp', '')} for a in unattached],
        }
    }


def _check_s3_lifecycle(tip, data, account_id, acct_label, creds):
    now_dt = datetime.now(timezone.utc)
    flagged = []
    for b in data.get('s3_buckets', []):
        reasons = []
        if not b.get('hasLifecycle'):
            reasons.append('no_lifecycle')
        lmd = b.get('lastModifiedDays')
        if lmd is not None and lmd >= 90:
            reasons.append(f'inactive_{lmd}d')
        elif lmd is None:
            reasons.append('empty')
        if reasons:
            flagged.append({**b, 'reasons': reasons})
    if not flagged:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(flagged)} S3 buckets flagged',
        'cardData': {
            'cardId': f's3-{account_id}', 'type': 's3-lifecycle',
            'title': 'S3 Buckets Needing Attention', 'icon': '🪣',
            'count': len(flagged), 'risk': 'low',
            'description': f'{len(flagged)} bucket(s) flagged — no lifecycle policy or inactive 90+ days',
            'monthlySavings': None,
            'resources': [{'name': b['name'], 'created': b['created'], 'sizeGb': 0, 'objectCount': 0, 'estimatedMonthlyCost': 0, 'lastModifiedDays': b.get('lastModifiedDays'), 'reasons': b['reasons'], 'reasonLabel': ' · '.join(b['reasons'])} for b in flagged[:15]],
        }
    }


def _check_elb_idle(tip, data, account_id, acct_label, creds):
    idle = []
    try:
        elbv2 = _make_client_from_creds('elbv2', creds)
        for lb in data.get('load_balancers', [])[:10]:
            try:
                tgs = elbv2.describe_target_groups(LoadBalancerArn=lb['LoadBalancerArn']).get('TargetGroups', [])
                if not tgs:
                    continue
                healthy = sum(
                    1 for tg in tgs[:3]
                    for t in elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn']).get('TargetHealthDescriptions', [])
                    if t.get('TargetHealth', {}).get('State') == 'healthy'
                )
                if healthy == 0:
                    idle.append({'arn': lb['LoadBalancerArn'], 'name': lb['LoadBalancerName'], 'type': lb.get('Type', '')})
            except Exception:
                pass
    except Exception:
        pass
    if not idle:
        return None
    savings = len(idle) * 16.43
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} idle load balancers',
        'cardData': {
            'cardId': f'lb-{account_id}', 'type': 'load-balancer',
            'title': 'Idle Load Balancers', 'icon': '⚖️',
            'count': len(idle), 'risk': 'medium',
            'description': f'{len(idle)} load balancer(s) with 0 healthy targets',
            'monthlySavings': round(savings, 2),
            'resources': idle,
        }
    }


def _check_ec2_idle(tip, data, account_id, acct_label, creds):
    cpu_map = data.get('ec2_cpu_14d', {})
    idle = []
    for inst in data.get('ec2_instances', []):
        iid = inst['InstanceId']
        avg_cpu = cpu_map.get(iid)
        if avg_cpu is not None and avg_cpu < 5.0:
            tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
            idle.append({'id': iid, 'name': tags.get('Name', iid), 'type': inst.get('InstanceType', ''), 'avgCpu': round(avg_cpu, 2), 'inAsg': 'aws:autoscaling:groupName' in tags, 'asgName': tags.get('aws:autoscaling:groupName', '')})
    if not idle:
        return None
    savings = len(idle) * 0.05 * 730
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} EC2 instances with avg CPU < 5% over 14 days',
        'cardData': {
            'cardId': f'ec2-idle-{account_id}', 'type': 'ec2-idle',
            'title': 'Idle EC2 Instances', 'icon': '🖥️',
            'count': len(idle), 'risk': 'high',
            'description': f'{len(idle)} running instance(s) with avg CPU < 5% over 14 days',
            'monthlySavings': round(savings, 2),
            'resources': idle,
            'note': 'Instances in Auto Scaling Groups will be detached before stopping.',
        }
    }


def _check_rds_idle(tip, data, account_id, acct_label, creds):
    cpu_map = data.get('rds_cpu_14d', {})
    conn_map = data.get('rds_conn_14d', {})
    idle = []
    for db in data.get('rds_instances', []):
        db_id = db['DBInstanceIdentifier']
        avg_cpu = cpu_map.get(db_id)
        max_conn = conn_map.get(db_id, 0)
        if avg_cpu is not None and avg_cpu < 5.0 and max_conn < 2:
            idle.append({'id': db_id, 'class': db.get('DBInstanceClass', ''), 'engine': db.get('Engine', ''), 'avgCpu': round(avg_cpu, 2), 'maxConnections': int(max_conn)})
    if not idle:
        return None
    savings = len(idle) * 50
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(idle)} RDS instances with avg CPU < 5% and < 2 connections',
        'cardData': {
            'cardId': f'rds-idle-{account_id}', 'type': 'rds-idle',
            'title': 'Idle RDS Instances', 'icon': '🗄️',
            'count': len(idle), 'risk': 'high',
            'description': f'{len(idle)} RDS instance(s) with avg CPU < 5% and < 2 connections over 14 days',
            'monthlySavings': round(savings, 2),
            'resources': idle,
            'note': 'A final snapshot will be taken automatically before deletion.',
        }
    }


def _check_kms_unused(tip, data, account_id, acct_label, creds):
    cmks = data.get('kms_customer_keys', [])
    if not cmks:
        return None
    savings = len(cmks) * 1.0
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(cmks)} customer-managed KMS keys at $1/month each',
        'cardData': {
            'cardId': f'kms-{account_id}', 'type': 'advisory',
            'title': 'Customer-Managed KMS Keys', 'icon': '🔑',
            'count': len(cmks), 'risk': 'low',
            'description': f'{len(cmks)} customer-managed KMS key(s) at $1/month each — audit for unused keys',
            'monthlySavings': round(savings, 2),
            'resources': [{'id': k['KeyId']} for k in cmks[:10]],
        }
    }


def _check_budgets(tip, data, account_id, acct_label, creds):
    if data.get('budgets'):
        return None  # budgets exist, no issue
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': 'No AWS Budgets configured',
        'cardData': {
            'cardId': f'budgets-{account_id}', 'type': 'advisory',
            'title': 'No AWS Budgets Configured', 'icon': '💰',
            'count': 0, 'risk': 'medium',
            'description': 'No budgets found — set up cost alerts to catch unexpected spend early',
            'monthlySavings': None,
            'resources': [],
        }
    }


def _check_spot_candidates(tip, data, account_id, acct_label, creds):
    """Identify EC2 instances that could use Spot (non-prod, low CPU, not already Spot)."""
    candidates = []
    cpu_map = data.get('ec2_cpu_14d', {})
    for inst in data.get('ec2_instances', []):
        if inst.get('InstanceLifecycle') == 'spot':
            continue  # already Spot
        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
        env = tags.get('Environment', tags.get('Env', '')).lower()
        is_nonprod = any(e in env for e in ['dev', 'test', 'staging', 'qa', 'sandbox'])
        avg_cpu = cpu_map.get(inst['InstanceId'])
        if is_nonprod or (avg_cpu is not None and avg_cpu < 30.0):
            candidates.append({'id': inst['InstanceId'], 'name': tags.get('Name', inst['InstanceId']), 'type': inst.get('InstanceType', ''), 'avgCpu': round(avg_cpu, 2) if avg_cpu is not None else None, 'env': env or 'unknown'})
    if not candidates:
        return None
    savings = len(candidates) * 0.05 * 730 * 0.7  # ~70% Spot discount
    return {
        'status': 'found', 'savingsUsd': round(savings, 2),
        'evidence': f'{len(candidates)} EC2 instances are Spot candidates',
        'cardData': {
            'cardId': f'spot-{account_id}', 'type': 'advisory',
            'title': 'Spot Instance Candidates', 'icon': '⚡',
            'count': len(candidates), 'risk': 'medium',
            'description': f'{len(candidates)} instance(s) could use Spot pricing — save up to 70%',
            'monthlySavings': round(savings, 2),
            'resources': candidates[:10],
            'actionUrl': 'https://console.aws.amazon.com/ec2/v2/home#SpotInstances',
        }
    }


def _check_ri_marketplace(tip, data, account_id, acct_label, creds):
    """Check for underutilized Reserved Instances via CE."""
    try:
        ce = _make_client_from_creds('ce', creds)
        now_dt = datetime.now(timezone.utc)
        ri_resp = ce.get_reservation_utilization(
            TimePeriod={'Start': (now_dt - timedelta(days=30)).strftime('%Y-%m-%d'), 'End': now_dt.strftime('%Y-%m-%d')},
        )
        total = ri_resp.get('Total', {})
        util_pct = float(total.get('UtilizationPercentage', '100') or '100')
        if util_pct >= 70:
            return None
        unused_cost = float(total.get('UnusedAmortizedUpfrontCostForRI', '0') or '0') + float(total.get('UnusedRecurringFeeForRI', '0') or '0')
        if unused_cost < 5:
            return None
        return {
            'status': 'found', 'savingsUsd': round(unused_cost, 2),
            'evidence': f'RI utilization {util_pct:.0f}% — ${unused_cost:.2f}/mo wasted',
            'cardData': {
                'cardId': f'ri-{account_id}', 'type': 'advisory',
                'title': 'Underutilized Reserved Instances', 'icon': '🏪',
                'count': 1, 'risk': 'medium',
                'description': f'RI utilization is {util_pct:.0f}% — ${unused_cost:.2f}/month in unused commitments. Consider selling on RI Marketplace.',
                'monthlySavings': round(unused_cost, 2),
                'resources': [],
                'actionUrl': 'https://console.aws.amazon.com/ec2/v2/home#ReservedInstances',
            }
        }
    except Exception:
        return None


def _check_rds_commercial_engine(tip, data, account_id, acct_label, creds):
    """Flag Oracle/SQL Server RDS instances as migration candidates."""
    commercial = [db for db in data.get('rds_instances', []) if db.get('Engine', '') in ('oracle-ee', 'oracle-se2', 'sqlserver-ee', 'sqlserver-se', 'sqlserver-ex', 'sqlserver-web')]
    if not commercial:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(commercial)} commercial-engine RDS instances',
        'cardData': {
            'cardId': f'rds-commercial-{account_id}', 'type': 'advisory',
            'title': 'Commercial DB Engine Migration', 'icon': '🗄️',
            'count': len(commercial), 'risk': 'low',
            'description': f'{len(commercial)} Oracle/SQL Server instance(s) — migrating to PostgreSQL/MySQL could save 30-60%',
            'monthlySavings': None,
            'resources': [{'id': db['DBInstanceIdentifier'], 'engine': db.get('Engine', ''), 'class': db.get('DBInstanceClass', '')} for db in commercial],
        }
    }


def _check_graviton_candidates(tip, data, account_id, acct_label, creds):
    """Flag x86 EC2 instances that have Graviton equivalents."""
    x86_families = {'t3', 't3a', 'm5', 'm5a', 'm6i', 'c5', 'c5a', 'c6i', 'r5', 'r5a', 'r6i'}
    graviton_map = {'t3': 't4g', 't3a': 't4g', 'm5': 'm7g', 'm5a': 'm7g', 'm6i': 'm7g', 'c5': 'c7g', 'c5a': 'c7g', 'c6i': 'c7g', 'r5': 'r7g', 'r5a': 'r7g', 'r6i': 'r7g'}
    candidates = []
    for inst in data.get('ec2_instances', []):
        itype = inst.get('InstanceType', '')
        family = itype.split('.')[0] if '.' in itype else ''
        if family in x86_families:
            tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
            candidates.append({'id': inst['InstanceId'], 'name': tags.get('Name', inst['InstanceId']), 'type': itype, 'gravitonEquiv': graviton_map.get(family, family + 'g')})
    if not candidates:
        return None
    return {
        'status': 'found', 'savingsUsd': 0,
        'evidence': f'{len(candidates)} x86 instances with Graviton equivalents',
        'cardData': {
            'cardId': f'graviton-{account_id}', 'type': 'advisory',
            'title': 'Graviton Migration Candidates', 'icon': '⚡',
            'count': len(candidates), 'risk': 'low',
            'description': f'{len(candidates)} x86 instance(s) have Graviton equivalents — save 20-40% with better performance',
            'monthlySavings': None,
            'resources': candidates[:10],
        }
    }


# ── Registry: tip.id → check function ────────────────────────────────────────
_SCAN_REGISTRY = {
    # Level 1 — Resource Hygiene
    'ebs-004':     _check_ebs_unattached,
    'ebs-002':     _check_ebs_snapshots,
    'ebs-003':     _check_ebs_snapshots,   # archive = same detection as delete
    'vpc-001':     _check_eip_unattached,
    's3-002':      _check_s3_lifecycle,
    's3-003':      _check_s3_lifecycle,
    'elb-001':     _check_elb_idle,
    'kms-001':     _check_kms_unused,
    'general-002': _check_budgets,
    'general-004': _check_ebs_unattached,  # general audit → EBS check
    # Level 2 — Optimization
    'ec2-001':     _check_ec2_idle,        # rightsizing uses idle detection
    'ec2-003':     _check_spot_candidates,
    'ec2-009':     _check_spot_candidates,
    'ec2-006':     _check_graviton_candidates,
    'rds-001':     _check_rds_idle,
    'rds-006':     _check_rds_commercial_engine,
    # Level 3 — Architecture / Commitment
    'general-014': _check_ri_marketplace,
}



def _save_last_scan(member_email, account_ids, findings, total_savings, scanned_at):
    """Persist top findings to Members table for the Chat widget."""
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET lastScan = :s',
            ExpressionAttributeValues={':s': {
                'accountIds': account_ids,
                'findings': findings[:10],
                'totalSavings': str(round(total_savings, 2)),
                'scannedAt': scanned_at,
            }},
        )
    except Exception as e:
        logger.warning(f"Failed to save last scan: {e}")


def handle_get_last_scan(event):
    """Return the cached last scan result for the Chat widget."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = members_table.get_item(Key={'email': member_email}).get('Item') or {}
        last_scan = _decimal_to_native(member.get('lastScan') or {})
        return create_response(200, {'lastScan': last_scan})
    except ClientError as e:
        return create_error_response(500, 'ServerError', 'Failed to load last scan')


def handle_actions_execute(event):
    """Execute a Level-1 cleanup action with JIT safety checks."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    # Token cost: each cleanup action costs 50 tokens
    tier = _get_member_tier(member_email)
    token_err = _check_and_consume_credits(member_email, tier, ACTIVITY_CREDIT_COST)
    if token_err:
        return token_err

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    action_type = (body.get('actionType') or '').strip()  # elastic-ip | ebs-volume | load-balancer | s3-lifecycle
    resource_ids = body.get('resourceIds') or []  # list of IDs to act on

    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')
    if not action_type:
        return create_error_response(400, 'InvalidRequest', 'actionType is required')
    if not resource_ids:
        return create_error_response(400, 'InvalidRequest', 'resourceIds is required')

    # Verify ownership
    ownership = _verify_account_ownership(member_email, [account_id])
    if isinstance(ownership, dict):
        return ownership

    try:
        creds = _assume_role_for_account(member_email, account_id)
    except Exception as e:
        return create_error_response(400, 'ConnectionFailed', f'Cannot access account {account_id}: {str(e)}')

    results = []
    errors = []

    if action_type == 'elastic-ip':
        ec2 = _make_client_from_creds('ec2', creds)
        for alloc_id in resource_ids:
            try:
                # JIT check: verify still unassociated
                check = ec2.describe_addresses(AllocationIds=[alloc_id])
                addr = check.get('Addresses', [{}])[0]
                if addr.get('AssociationId'):
                    errors.append({'id': alloc_id, 'error': 'EIP is now associated — skipped for safety'})
                    continue
                ec2.release_address(AllocationId=alloc_id)
                results.append({'id': alloc_id, 'status': 'released', 'ip': addr.get('PublicIp', '')})
                logger.info(f"Released EIP {alloc_id} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': alloc_id, 'error': str(e.response['Error']['Message'])})

    elif action_type == 'ebs-volume':
        ec2 = _make_client_from_creds('ec2', creds)
        for vol_id in resource_ids:
            try:
                # JIT check: verify still available (unattached)
                check = ec2.describe_volumes(VolumeIds=[vol_id])
                vol = check.get('Volumes', [{}])[0]
                if vol.get('State') != 'available':
                    errors.append({'id': vol_id, 'error': f'Volume state is now "{vol.get("State")}" — skipped for safety'})
                    continue
                ec2.delete_volume(VolumeId=vol_id)
                results.append({'id': vol_id, 'status': 'deleted', 'size': vol.get('Size', 0)})
                logger.info(f"Deleted EBS volume {vol_id} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': vol_id, 'error': str(e.response['Error']['Message'])})

    elif action_type == 'load-balancer':
        elbv2 = _make_client_from_creds('elbv2', creds)
        for lb_arn in resource_ids:
            try:
                # JIT check: verify still has 0 healthy targets
                tgs = elbv2.describe_target_groups(LoadBalancerArn=lb_arn).get('TargetGroups', [])
                healthy = 0
                for tg in tgs:
                    health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
                    healthy += sum(1 for t in health.get('TargetHealthDescriptions', []) if t.get('TargetHealth', {}).get('State') == 'healthy')
                if healthy > 0:
                    errors.append({'id': lb_arn, 'error': f'Load balancer now has {healthy} healthy target(s) — skipped for safety'})
                    continue
                elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
                results.append({'id': lb_arn, 'status': 'deleted'})
                logger.info(f"Deleted LB {lb_arn} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': lb_arn, 'error': str(e.response['Error']['Message'])})

    elif action_type == 's3-lifecycle':
        s3 = _make_client_from_creds('s3', creds)
        for bucket_name in resource_ids:
            try:
                # Apply Intelligent-Tiering + Glacier transition after 90 days
                s3.put_bucket_lifecycle_configuration(
                    Bucket=bucket_name,
                    LifecycleConfiguration={
                        'Rules': [
                            {
                                'ID': 'SlashMyBill-CostOptimization',
                                'Status': 'Enabled',
                                'Filter': {'Prefix': ''},
                                'Transitions': [
                                    {'Days': 90, 'StorageClass': 'INTELLIGENT_TIERING'},
                                ],
                                'NoncurrentVersionTransitions': [
                                    {'NoncurrentDays': 30, 'StorageClass': 'GLACIER_IR'},
                                ],
                                'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7},
                            }
                        ]
                    }
                )
                results.append({'id': bucket_name, 'status': 'lifecycle-applied', 'rule': 'Intelligent-Tiering after 90 days'})
                logger.info(f"Applied lifecycle to S3 bucket {bucket_name} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': bucket_name, 'error': str(e.response['Error']['Message'])})

    elif action_type == 's3-delete-objects':        # Delete ALL objects in the bucket (paginated batch delete)
        s3 = _make_client_from_creds('s3', creds)
        for bucket_name in resource_ids:
            try:
                total_deleted = 0
                paginator = s3.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket_name):
                    objects = page.get('Contents', [])
                    if not objects:
                        break
                    # Batch delete up to 1000 at a time
                    delete_resp = s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': [{'Key': o['Key']} for o in objects], 'Quiet': True}
                    )
                    total_deleted += len(objects) - len(delete_resp.get('Errors', []))
                    if delete_resp.get('Errors'):
                        for err in delete_resp['Errors'][:3]:
                            errors.append({'id': bucket_name + '/' + err['Key'], 'error': err.get('Message', 'Delete failed')})
                results.append({'id': bucket_name, 'status': 'objects-deleted', 'deleted': total_deleted})
                logger.info(f"Deleted {total_deleted} objects from s3://{bucket_name} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': bucket_name, 'error': str(e.response['Error']['Message'])})

    elif action_type == 'ec2-idle':
        ec2 = _make_client_from_creds('ec2', creds)
        asg_client = _make_client_from_creds('autoscaling', creds)
        for inst_id in resource_ids:
            try:
                # JIT check: verify still running and still low CPU
                check = ec2.describe_instances(InstanceIds=[inst_id])
                reservations = check.get('Reservations', [])
                if not reservations:
                    errors.append({'id': inst_id, 'error': 'Instance not found'})
                    continue
                inst = reservations[0]['Instances'][0]
                if inst.get('State', {}).get('Name') != 'running':
                    errors.append({'id': inst_id, 'error': f'Instance state is now "{inst["State"]["Name"]}" — skipped'})
                    continue

                # ASG check — detach from ASG before stopping
                tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                asg_name = tags.get('aws:autoscaling:groupName', '')
                if asg_name:
                    try:
                        # Decrement desired capacity and detach
                        asg_client.detach_instances(
                            InstanceIds=[inst_id],
                            AutoScalingGroupName=asg_name,
                            ShouldDecrementDesiredCapacity=True,
                        )
                        logger.info(f"Detached {inst_id} from ASG {asg_name}")
                    except Exception as asg_err:
                        errors.append({'id': inst_id, 'error': f'ASG detach failed: {str(asg_err)} — skipped for safety'})
                        continue

                # Stop (not terminate) — safer default, user can terminate manually
                ec2.stop_instances(InstanceIds=[inst_id])
                results.append({'id': inst_id, 'status': 'stopped', 'asgDetached': bool(asg_name)})
                logger.info(f"Stopped EC2 {inst_id} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': inst_id, 'error': str(e.response['Error']['Message'])})

    elif action_type == 'rds-idle':
        rds = _make_client_from_creds('rds', creds)
        for db_id in resource_ids:
            try:
                # JIT check: verify still available and still idle
                check = rds.describe_db_instances(DBInstanceIdentifier=db_id)
                db = check['DBInstances'][0]
                if db.get('DBInstanceStatus') != 'available':
                    errors.append({'id': db_id, 'error': f'RDS status is now "{db["DBInstanceStatus"]}" — skipped'})
                    continue
                # Delete with final snapshot (safety guardrail — always keep a backup)
                snapshot_id = f'slashmybill-final-{db_id}-{int(datetime.now(timezone.utc).timestamp())}'
                rds.delete_db_instance(
                    DBInstanceIdentifier=db_id,
                    SkipFinalSnapshot=False,
                    FinalDBSnapshotIdentifier=snapshot_id,
                )
                results.append({'id': db_id, 'status': 'deleting', 'finalSnapshot': snapshot_id})
                logger.info(f"Deleting RDS {db_id} with snapshot {snapshot_id} in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': db_id, 'error': str(e.response['Error']['Message'])})

    elif action_type == 'ebs-snapshot':
        ec2 = _make_client_from_creds('ec2', creds)
        for snap_id in resource_ids:
            try:
                # JIT check: verify snapshot still exists and is still old
                check = ec2.describe_snapshots(SnapshotIds=[snap_id])
                snaps = check.get('Snapshots', [])
                if not snaps:
                    errors.append({'id': snap_id, 'error': 'Snapshot not found'})
                    continue
                snap = snaps[0]
                age_days = (datetime.now(timezone.utc) - snap['StartTime'].replace(tzinfo=timezone.utc)).days
                if age_days < 180:
                    errors.append({'id': snap_id, 'error': f'Snapshot is now only {age_days} days old — skipped for safety'})
                    continue
                ec2.delete_snapshot(SnapshotId=snap_id)
                results.append({'id': snap_id, 'status': 'deleted', 'ageDays': age_days, 'sizeGb': snap.get('VolumeSize', 0)})
                logger.info(f"Deleted snapshot {snap_id} ({age_days}d old) in account {account_id} by {member_email}")
            except ClientError as e:
                errors.append({'id': snap_id, 'error': str(e.response['Error']['Message'])})

    else:
        return create_error_response(400, 'InvalidRequest', f'Unknown actionType: {action_type}')

    return create_response(200, {
        'actionType': action_type,
        'accountId': account_id,
        'succeeded': results,
        'failed': errors,
        'executedAt': datetime.now(timezone.utc).isoformat(),
    })


def handle_browse_bucket(event):
    """Return top objects in an S3 bucket sorted by LastModified (oldest first for aged data review)."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    bucket_name = (body.get('bucketName') or '').strip()
    sort_by = (body.get('sortBy') or 'oldest').strip()  # 'oldest' | 'largest' | 'newest'

    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')
    if not bucket_name:
        return create_error_response(400, 'InvalidRequest', 'bucketName is required')

    ownership = _verify_account_ownership(member_email, [account_id])
    if isinstance(ownership, dict):
        return ownership

    try:
        creds = _assume_role_for_account(member_email, account_id)
    except Exception as e:
        return create_error_response(400, 'ConnectionFailed', str(e))

    s3 = _make_client_from_creds('s3', creds)
    now_dt = datetime.now(timezone.utc)

    try:
        # Paginate up to 500 objects for analysis
        objects = []
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, PaginationConfig={'MaxItems': 500}):
            for obj in page.get('Contents', []):
                last_mod = obj['LastModified'].replace(tzinfo=timezone.utc)
                age_days = (now_dt - last_mod).days
                objects.append({
                    'key': obj['Key'],
                    'sizeBytes': obj['Size'],
                    'sizeGb': round(obj['Size'] / (1024 ** 3), 6),
                    'lastModified': last_mod.strftime('%Y-%m-%d'),
                    'ageDays': age_days,
                    'storageClass': obj.get('StorageClass', 'STANDARD'),
                    'aged': age_days >= 90,
                })

        total_objects = len(objects)
        total_size_gb = round(sum(o['sizeGb'] for o in objects), 4)
        aged_objects = [o for o in objects if o['aged']]
        aged_size_gb = round(sum(o['sizeGb'] for o in aged_objects), 4)
        estimated_cost = round(total_size_gb * 0.023, 4)  # S3 Standard $0.023/GB
        aged_cost = round(aged_size_gb * 0.023, 4)

        # Sort
        if sort_by == 'oldest':
            objects.sort(key=lambda o: o['ageDays'], reverse=True)
        elif sort_by == 'largest':
            objects.sort(key=lambda o: o['sizeBytes'], reverse=True)
        else:  # newest
            objects.sort(key=lambda o: o['ageDays'])

        return create_response(200, {
            'bucketName': bucket_name,
            'totalObjects': total_objects,
            'totalSizeGb': total_size_gb,
            'estimatedMonthlyCost': estimated_cost,
            'agedObjects': len(aged_objects),
            'agedSizeGb': aged_size_gb,
            'agedMonthlyCost': aged_cost,
            'objects': objects[:100],  # top 100 after sort
            'truncated': total_objects > 500,
        })
    except ClientError as e:
        return create_error_response(400, 'S3Error', str(e.response['Error']['Message']))
    except Exception as e:
        return create_error_response(500, 'ServerError', str(e))


def _get_unit_economics(member_email, monthly_trend):
    """Calculate unit economics from business metrics and monthly cost data."""
    try:
        table = dynamodb.Table(BUSINESS_METRICS_TABLE)
        result = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email),
            ScanIndexForward=False,
            Limit=24,
        )
        metrics = _decimal_to_native(result.get('Items', []))
    except Exception:
        return None

    if not metrics or not monthly_trend:
        return None

    by_month = {}
    for m in metrics:
        month = m.get('metricMonth', '')
        if month not in by_month:
            by_month[month] = []
        by_month[month].append(m)

    unit_costs = []
    for month in sorted(monthly_trend.keys()):
        total_cost = sum(monthly_trend[month].values())
        month_metrics = by_month.get(month, [])
        if month_metrics:
            for bm in month_metrics:
                vol = bm.get('metricVolume', 0)
                if vol > 0:
                    unit_costs.append({
                        'month': month,
                        'metricName': bm.get('metricName', ''),
                        'volume': vol,
                        'totalCost': round(total_cost, 2),
                        'costPerUnit': round(total_cost / vol, 6),
                        'source': bm.get('source', 'manual'),
                    })

    if not unit_costs:
        return None

    primary = metrics[0].get('metricName', '')
    primary_trend = [uc for uc in unit_costs if uc['metricName'] == primary]

    return {
        'metricName': primary,
        'trend': primary_trend,
        'allMetrics': list(set(m.get('metricName', '') for m in metrics)),
    }


def _auto_discover_it_metrics(credentials):
    """Auto-discover real IT metrics from AWS services for unit economics."""
    discovered = []
    try:
        # DynamoDB table item counts (proxy for "users" or "records")
        ddb = boto3.client('dynamodb',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name='us-east-1')
        tables = ddb.list_tables().get('TableNames', [])
        for tname in tables[:10]:
            try:
                desc = ddb.describe_table(TableName=tname)
                count = desc['Table'].get('ItemCount', 0)
                if count > 0:
                    discovered.append({
                        'metricName': f'DynamoDB:{tname} items',
                        'volume': count,
                        'source': 'aws-dynamodb',
                        'description': f'{count:,} items in {tname}',
                    })
            except Exception:
                pass

        # API Gateway request count (last 30 days via CloudWatch)
        cw = boto3.client('cloudwatch',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name='us-east-1')
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)
        try:
            apigw_resp = cw.get_metric_statistics(
                Namespace='AWS/ApiGateway', MetricName='Count',
                StartTime=start, EndTime=now, Period=2592000, Statistics=['Sum'],
            )
            total_requests = sum(dp['Sum'] for dp in apigw_resp.get('Datapoints', []))
            if total_requests > 0:
                discovered.append({
                    'metricName': 'API Gateway Requests (30d)',
                    'volume': int(total_requests),
                    'source': 'aws-cloudwatch',
                    'description': f'{int(total_requests):,} API requests in 30 days',
                })
        except Exception:
            pass

        # Lambda total invocations (last 30 days)
        try:
            lam_resp = cw.get_metric_statistics(
                Namespace='AWS/Lambda', MetricName='Invocations',
                StartTime=start, EndTime=now, Period=2592000, Statistics=['Sum'],
            )
            total_invocations = sum(dp['Sum'] for dp in lam_resp.get('Datapoints', []))
            if total_invocations > 0:
                discovered.append({
                    'metricName': 'Lambda Invocations (30d)',
                    'volume': int(total_invocations),
                    'source': 'aws-cloudwatch',
                    'description': f'{int(total_invocations):,} Lambda invocations in 30 days',
                })
        except Exception:
            pass

        # S3 total objects
        try:
            s3 = boto3.client('s3',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name='us-east-1')
            buckets = s3.list_buckets().get('Buckets', [])
            discovered.append({
                'metricName': 'S3 Buckets',
                'volume': len(buckets),
                'source': 'aws-s3',
                'description': f'{len(buckets)} S3 buckets',
            })
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"IT metrics discovery error: {e}")

    return discovered


def _apply_allocation_rules(cost_by_service, per_account, alloc_config):
    """Apply virtual tagging rules to cost data and return cost-by-business-unit."""
    if not alloc_config:
        return None

    # Support both old format (list of rules) and new format (config object)
    if isinstance(alloc_config, list):
        # Legacy format — convert
        business_units = []
        for r in alloc_config:
            business_units.append({
                'name': r.get('businessUnit', r.get('name', '')),
                'rules': [{'dimension': r.get('matchType', 'account'), 'operator': 'equals', 'value': r.get('matchValue', '')}],
            })
        shared_cost_mode = 'proportional'
        custom_splits = {}
    else:
        business_units = alloc_config.get('businessUnits', [])
        shared_cost_mode = alloc_config.get('sharedCostMode', 'proportional')
        custom_splits = alloc_config.get('customSplits', {})

    if not business_units:
        return None

    bu_costs = {}  # bu_name -> allocated cost
    unmatched_cost = 0
    total_cost = 0

    # Process each account's costs against business unit rules
    for acct in per_account:
        if 'error' in acct:
            continue
        acct_id = str(acct.get('accountId', ''))
        for svc in acct.get('topServices', []):
            svc_name = (svc.get('service') or '').lower()
            svc_cost = svc.get('cost_usd', 0)
            total_cost += svc_cost
            matched = False

            for bu in business_units:
                bu_name = bu.get('name', '')
                rule_logic = bu.get('ruleLogic', 'or')  # 'or' or 'and'
                rules = bu.get('rules', [])
                if not rules:
                    continue

                def _eval_rule(rule):
                    dim = rule.get('dimension', '')
                    op = rule.get('operator', 'equals')
                    val = str(rule.get('value', '')).lower()
                    if dim == 'account':
                        return val == acct_id
                    elif dim == 'service':
                        if op == 'equals':
                            return val == svc_name or val in svc_name
                        elif op == 'contains':
                            return val in svc_name
                        elif op == 'startsWith':
                            return svc_name.startswith(val)
                    elif dim == 'tag':
                        acct_name = (acct.get('accountName') or '').lower()
                        return val in acct_name
                    return False

                if rule_logic == 'and':
                    bu_match = all(_eval_rule(r) for r in rules)
                else:  # 'or' (default)
                    bu_match = any(_eval_rule(r) for r in rules)

                if bu_match:
                    bu_costs[bu_name] = bu_costs.get(bu_name, 0) + svc_cost
                    matched = True
                    break

            if not matched:
                unmatched_cost += svc_cost

    # Split shared/unmatched costs
    if unmatched_cost > 0 and business_units:
        if shared_cost_mode == 'even':
            share = unmatched_cost / len(business_units)
            for bu in business_units:
                bu_costs[bu['name']] = bu_costs.get(bu['name'], 0) + share
        elif shared_cost_mode == 'custom' and custom_splits:
            for bu in business_units:
                pct = custom_splits.get(bu['name'], 0) / 100
                bu_costs[bu['name']] = bu_costs.get(bu['name'], 0) + unmatched_cost * pct
        else:  # proportional (default)
            total_matched = sum(bu_costs.values())
            if total_matched > 0:
                for bu_name in list(bu_costs.keys()):
                    ratio = bu_costs[bu_name] / total_matched
                    bu_costs[bu_name] += unmatched_cost * ratio
            else:
                bu_costs['Unallocated'] = unmatched_cost

    if not bu_costs:
        return None

    total = sum(bu_costs.values())
    result = sorted(
        [{'businessUnit': bu, 'cost': round(c, 2), 'pct': round(c / total * 100, 1) if total > 0 else 0}
         for bu, c in bu_costs.items()],
        key=lambda x: x['cost'], reverse=True
    )
    allocated_pct = round((1 - bu_costs.get('Unallocated', 0) / total) * 100, 1) if total > 0 else 100
    status = alloc_config.get('status', 'active') if isinstance(alloc_config, dict) else 'active'

    return {
        'businessUnits': result,
        'allocatedPct': allocated_pct,
        'totalAllocated': round(total, 2),
        'sharedCostMode': shared_cost_mode,
        'status': status,
    }


def handle_execute_command(event):
    """Execute an AWS CLI command against a member's connected account via cross-account role."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    account_id = (body.get('accountId') or '').strip()
    command = (body.get('command') or '').strip()

    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')
    if not command:
        return create_error_response(400, 'InvalidRequest', 'Command is required')

    # Verify account ownership — prevent lateral access
    ownership = _verify_account_ownership(member_email, [account_id])
    if isinstance(ownership, dict):
        return ownership

    # Parse the AWS CLI command: "aws <service> <action> [--param value ...]"
    parts = command.split()
    if len(parts) < 3 or parts[0] != 'aws':
        return create_error_response(400, 'InvalidCommand', 'Command must start with "aws <service> <action>"')

    service_name = parts[1]
    action_name = parts[2]

    # Whitelist of allowed services (read-only operations)
    allowed_services = {
        'ce', 'costexplorer', 'cost-explorer',
        's3', 's3api',
        'ec2',
        'rds',
        'lambda',
        'iam',
        'cloudwatch', 'logs',
        'sts',
        'dynamodb',
        'elasticache',
        'elbv2', 'elb',
        'route53',
        'cloudfront',
        'budgets',
    }

    # Block write/delete operations
    blocked_actions = [
        'create', 'delete', 'put', 'update', 'modify', 'terminate', 'stop', 'start',
        'reboot', 'run', 'invoke', 'send', 'publish', 'remove', 'attach', 'detach',
        'enable', 'disable', 'tag', 'untag', 'deregister', 'register',
    ]

    if service_name not in allowed_services:
        return create_error_response(400, 'InvalidCommand', f'Service "{service_name}" is not allowed. Allowed: {", ".join(sorted(allowed_services))}')

    action_lower = action_name.lower().replace('-', '')
    for blocked in blocked_actions:
        if action_lower.startswith(blocked):
            return create_error_response(400, 'InvalidCommand', f'Write operation "{action_name}" is not allowed. Only read/describe/list/get operations are permitted.')

    # Assume the cross-account role
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    sts_client = boto3.client('sts')
    try:
        assume_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SlashMyBillLab',
            ExternalId=external_id,
        )
        credentials = assume_response['Credentials']
    except ClientError as e:
        return create_error_response(400, 'ConnectionFailed',
            f'Cannot assume role for account {account_id}. Please ensure the CloudFormation stack is deployed.')

    # Parse CLI arguments into boto3 parameters
    cli_params = {}
    i = 3
    while i < len(parts):
        if parts[i].startswith('--'):
            param_name = parts[i][2:]
            # Convert CLI param name to PascalCase for boto3
            pascal = ''.join(w.capitalize() for w in param_name.split('-'))
            if i + 1 < len(parts) and not parts[i + 1].startswith('--'):
                cli_params[pascal] = parts[i + 1]
                i += 2
            else:
                cli_params[pascal] = True
                i += 1
        else:
            i += 1

    # Convert action name from CLI format to boto3 method name
    # e.g., "describe-instances" -> "describe_instances"
    method_name = action_name.replace('-', '_')

    # Map common CLI shorthand commands to boto3 method names
    cli_to_boto3_actions = {
        's3': {'ls': 'list_buckets'},
        'lambda': {'ls': 'list_functions'},
        'iam': {'ls': 'list_roles'},
    }
    if service_name in cli_to_boto3_actions and action_name in cli_to_boto3_actions[service_name]:
        method_name = cli_to_boto3_actions[service_name][action_name]

    # Map CLI service names to boto3 service names
    service_map = {
        'costexplorer': 'ce', 'cost-explorer': 'ce',
        's3api': 's3', 'logs': 'logs',
        'elbv2': 'elbv2', 'elb': 'elb',
    }
    boto3_service = service_map.get(service_name, service_name)

    try:
        client = boto3.client(
            boto3_service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name='us-east-1',
        )

        if not hasattr(client, method_name):
            return create_error_response(400, 'InvalidCommand',
                f'Unknown action "{action_name}" for service "{service_name}"')

        method = getattr(client, method_name)
        result = method(**cli_params)

        # Remove ResponseMetadata for cleaner output
        if isinstance(result, dict):
            result.pop('ResponseMetadata', None)

        # Convert to JSON-serializable format
        output = json.dumps(result, indent=2, default=str)

        return create_response(200, {
            'output': output,
            'service': service_name,
            'action': action_name,
            'accountId': account_id,
        })

    except ClientError as e:
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        return create_response(200, {
            'output': f'ERROR: {error_msg}',
            'service': service_name,
            'action': action_name,
            'accountId': account_id,
        })
    except Exception as e:
        return create_response(200, {
            'output': f'ERROR: {str(e)}',
            'service': service_name,
            'action': action_name,
            'accountId': account_id,
        })


# ============================================================
# AI Feedback Handler
# ============================================================

SERVICE_KEYWORD_MAP = {
    'EC2': ['ec2', 'instance'],
    'S3': ['s3', 'bucket', 'storage'],
    'RDS': ['rds', 'database', 'aurora'],
    'Lambda': ['lambda', 'function', 'serverless'],
    'EBS': ['ebs', 'volume'],
    'VPC': ['vpc', 'nat', 'endpoint'],
    'CloudFront': ['cloudfront', 'cdn'],
    'DynamoDB': ['dynamodb'],
    'ECS': ['ecs', 'fargate', 'container'],
    'EKS': ['eks', 'kubernetes'],
    'Route53': ['route53', 'dns'],
    'KMS': ['kms', 'key', 'encrypt'],
    'ElastiCache': ['elasticache', 'redis', 'memcached'],
    'Redshift': ['redshift', 'warehouse'],
    'CloudWatch': ['cloudwatch', 'monitor', 'alarm'],
    'IAM': ['iam', 'role', 'policy', 'permission'],
}


def _derive_related_service(question):
    """Match question text against AWS service keywords and return the service name."""
    question_lower = question.lower()
    for service, keywords in SERVICE_KEYWORD_MAP.items():
        for kw in keywords:
            if kw in question_lower:
                return service
    return 'General'


def handle_ai_feedback(event):
    """Handle AI feedback submissions — store feedback and optionally save tip."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    interaction_id = (body.get('interactionId') or '').strip()
    feedback_score = (body.get('feedbackScore') or '').strip()
    user_question = (body.get('userQuestion') or '').strip()
    agent_response = (body.get('agentResponse') or '').strip()
    account_id = (body.get('accountId') or '').strip()
    user_correction = (body.get('userCorrection') or '').strip() or None

    # Validate required fields
    missing = []
    if not interaction_id:
        missing.append('interactionId')
    if not feedback_score:
        missing.append('feedbackScore')
    if not user_question:
        missing.append('userQuestion')
    if not agent_response:
        missing.append('agentResponse')
    if missing:
        return create_error_response(400, 'InvalidRequest', f"Missing required fields: {', '.join(missing)}")

    if feedback_score not in ('yes', 'no'):
        return create_error_response(400, 'InvalidRequest', "feedbackScore must be 'yes' or 'no'")

    related_service = _derive_related_service(user_question)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Write feedback record to DynamoDB
    feedback_table = dynamodb.Table(FEEDBACK_TABLE_NAME)
    try:
        feedback_record = {
            'memberEmail': member_email,
            'interactionId': interaction_id,
            'userQuestion': user_question,
            'agentResponse': agent_response[:2000],
            'feedbackScore': feedback_score,
            'relatedService': related_service,
            'createdAt': now_iso,
        }
        if account_id:
            feedback_record['accountId'] = account_id
        if user_correction:
            feedback_record['userCorrection'] = user_correction
        feedback_table.put_item(Item=feedback_record)
    except ClientError as e:
        logger.error(f"Failed to write feedback: {e}")
        return create_error_response(500, 'InternalError', 'Failed to save feedback')

    # If positive feedback, save tip with high-confidence tag
    if feedback_score == 'yes':
        tip_id = f'ai-fb-{hashlib.md5(user_question.encode()).hexdigest()[:8]}'
        tips_table = dynamodb.Table(TIPS_TABLE_NAME)
        try:
            tips_table.put_item(
                Item={
                    'service': related_service,
                    'tipId': tip_id,
                    'title': user_question[:100],
                    'description': agent_response[:500],
                    'category': 'ai-generated',
                    'estimatedSavings': 'varies',
                    'difficulty': 'medium',
                    'source': 'user-feedback',
                    'confidenceTag': 'high-confidence',
                    'positiveCount': 1,
                    'createdAt': now_iso,
                },
                ConditionExpression='attribute_not_exists(tipId)',
            )
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
                # Tip already exists — increment its positiveCount and ensure high-confidence
                try:
                    tips_table.update_item(
                        Key={'service': related_service, 'tipId': tip_id},
                        UpdateExpression='SET positiveCount = if_not_exists(positiveCount, :zero) + :one, confidenceTag = :hc',
                        ExpressionAttributeValues={':zero': 0, ':one': 1, ':hc': 'high-confidence'},
                    )
                except Exception:
                    pass
            else:
                logger.warning(f"Failed to save feedback tip: {e}")

    # If negative feedback, decrement positiveCount on the matching tip (if it exists)
    if feedback_score == 'no':
        tip_id = f'ai-fb-{hashlib.md5(user_question.encode()).hexdigest()[:8]}'
        tips_table = dynamodb.Table(TIPS_TABLE_NAME)
        try:
            tips_table.update_item(
                Key={'service': related_service, 'tipId': tip_id},
                UpdateExpression='SET positiveCount = if_not_exists(positiveCount, :zero) - :one',
                ExpressionAttributeValues={':zero': 0, ':one': 1},
                ConditionExpression='attribute_exists(tipId)',
            )
            # If positiveCount drops below 0, remove high-confidence tag
            try:
                resp = tips_table.get_item(Key={'service': related_service, 'tipId': tip_id})
                item = resp.get('Item', {})
                if item.get('positiveCount', 0) <= 0:
                    tips_table.update_item(
                        Key={'service': related_service, 'tipId': tip_id},
                        UpdateExpression='REMOVE confidenceTag',
                    )
            except Exception:
                pass
        except ClientError:
            pass  # Tip doesn't exist — nothing to decrement

    return create_response(200, {'success': True})


# ============================================================
# AI Agent Query Handler
# ============================================================

def handle_ai_query(event):
    """Handle natural language questions — uses Bedrock Agent or falls back to direct model API."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    member_email = auth['sub']

    # Check AI credits
    tier = _get_member_tier(member_email)
    credit_err = _check_and_consume_credits(member_email, tier, AI_QUERY_CREDIT_COST)
    if credit_err:
        return credit_err

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    question = (body.get('question') or '').strip()
    account_id = (body.get('accountId') or '').strip()
    account_ids = body.get('accountIds', [])

    if not question:
        return create_error_response(400, 'InvalidRequest', 'Question is required')

    # Support multi-account: accountIds array takes priority over single accountId
    if account_ids and isinstance(account_ids, list):
        account_ids = [a.strip() for a in account_ids if re.fullmatch(r'\d{12}', a.strip())]
    elif account_id and re.fullmatch(r'\d{12}', account_id):
        account_ids = [account_id]
    else:
        return create_error_response(400, 'InvalidAccountId', 'At least one valid 12-digit Account ID is required')

    # Generate unique interactionId for feedback tracking
    interaction_id = datetime.now(timezone.utc).isoformat() + '-' + secrets.token_hex(4)

    # Verify account ownership — prevent lateral access
    ownership = _verify_account_ownership(member_email, account_ids)
    if isinstance(ownership, dict):
        return ownership

    # Multi-account query: gather data from all accounts, then analyze together
    if len(account_ids) > 1:
        result = _invoke_multi_account(question, account_ids, member_email, interaction_id)
    elif BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID:
        result = _invoke_bedrock_agent(question, account_ids[0], member_email, interaction_id)
    else:
        result = _invoke_direct_model(question, account_ids[0], member_email, interaction_id)

    # Inject credits info into the response body
    max_credits = AI_CREDITS.get(tier, 100)
    if max_credits > 0 and result.get('statusCode') == 200:
        try:
            members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
            member = members_table.get_item(Key={'email': member_email}).get('Item', {})
            used = int(member.get('aiCreditsUsed', 0))
            resp_body = json.loads(result.get('body', '{}'))
            resp_body['aiCredits'] = {'used': used, 'total': max_credits, 'remaining': max(0, max_credits - used)}
            result['body'] = json.dumps(resp_body)
        except Exception:
            pass

    return result


def _invoke_bedrock_agent(question, account_id, member_email, interaction_id):
    """Invoke the Bedrock Agent for a conversational FinOps query."""
    agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

    # Include account context in the prompt
    enriched_prompt = f"[Account: {account_id}, Member: {member_email}] {question}"

    try:
        response = agent_runtime.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS_ID,
            sessionId=f'{member_email}-{account_id}'[:100],
            inputText=enriched_prompt,
        )

        # Stream the response
        answer_parts = []
        for event_stream in response.get('completion', []):
            if 'chunk' in event_stream:
                chunk = event_stream['chunk']
                if 'bytes' in chunk:
                    answer_parts.append(chunk['bytes'].decode('utf-8'))

        answer = ''.join(answer_parts)
        if not answer:
            answer = 'The agent did not return a response. Please try rephrasing your question.'

        return create_response(200, {
            'answer': answer,
            'interactionId': interaction_id,
            'commands': ['Bedrock Agent orchestrated the analysis'],
            'results': [],
            'tipFound': False,
            'agentUsed': True,
        })
    except Exception as e:
        logger.error(f"Bedrock Agent invocation failed: {e}")
        # Fall back to direct model
        return _invoke_direct_model(question, account_id, member_email, interaction_id)


def _invoke_direct_model(question, account_id, member_email, interaction_id):
    """Fallback: use direct Bedrock model API with boto3 data gathering."""
    # Step 1: Search tips
    tips_context = _search_tips(question)

    # Step 2: Assume role and gather data
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    credentials = None
    try:
        sts_client = boto3.client('sts')
        assume_response = sts_client.assume_role(
            RoleArn=role_arn, RoleSessionName='SlashMyBillAI', ExternalId=external_id,
        )
        credentials = assume_response['Credentials']
    except ClientError as e:
        logger.error(f"STS AssumeRole failed: {e}")

    account_data = {}
    executed_actions = []
    if credentials:
        account_data, executed_actions = _gather_account_data(question, credentials)

    # Step 3: Ask Bedrock to analyze
    answer = _ask_bedrock_analyze(question, tips_context, account_data, account_id)

    # Step 4: Save tip
    _maybe_save_tip(question, answer, tips_context)

    # Build service-based follow-up topics from the bill
    top_services = []
    for svc in account_data.get('cost_by_service', [])[:10]:
        svc_name = svc.get('service', '')
        cost = svc.get('cost_usd', 0)
        if cost > 0.5 and svc_name not in ('Tax',):
            top_services.append({'service': svc_name, 'cost': round(cost, 2)})

    return create_response(200, {
        'answer': answer,
        'interactionId': interaction_id,
        'commands': executed_actions,
        'results': [],
        'tipFound': bool(tips_context),
        'agentUsed': False,
        'chartData': _build_chart_data(account_data),
        'topServices': top_services,
    })


def _invoke_multi_account(question, account_ids, member_email, interaction_id):
    """Gather data from multiple accounts, merge, and analyze together."""
    tips_context = _search_tips(question)
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts_client = boto3.client('sts')

    all_account_data = {}
    all_actions = []
    merged_costs = {}
    merged_monthly = {}  # month -> service -> total cost

    for acct_id in account_ids[:5]:
        role_arn = f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}'
        try:
            assume_response = sts_client.assume_role(
                RoleArn=role_arn, RoleSessionName='SlashMyBillAI', ExternalId=external_id,
            )
            credentials = assume_response['Credentials']
            acct_data, acct_actions = _gather_account_data(question, credentials)
            all_account_data[acct_id] = acct_data
            all_actions.extend([f'[{acct_id}] {a}' for a in acct_actions])

            for svc in acct_data.get('cost_by_service', []):
                key = svc['service']
                merged_costs[key] = merged_costs.get(key, 0) + svc['cost_usd']

            # Merge monthly trend data across accounts
            for month, svc_costs in acct_data.get('monthly_trend', {}).items():
                if month not in merged_monthly:
                    merged_monthly[month] = {}
                for svc, cost in svc_costs.items():
                    merged_monthly[month][svc] = merged_monthly[month].get(svc, 0) + cost
        except Exception as e:
            logger.warning(f"Failed to gather data for account {acct_id}: {e}")
            all_account_data[acct_id] = {'error': str(e)}

    # Build aggregate
    aggregate = {
        'total_accounts': len(account_ids),
        'accounts_analyzed': len([a for a in all_account_data.values() if 'error' not in a]),
        'aggregate_cost_by_service': sorted(
            [{'service': s, 'cost_usd': round(c, 4)} for s, c in merged_costs.items()],
            key=lambda x: x['cost_usd'], reverse=True
        ),
        'aggregate_total_spend': round(sum(merged_costs.values()), 2),
        'per_account_data': {},
    }

    # Include monthly trend in aggregate if available
    if merged_monthly:
        aggregate['monthly_trend'] = {m: {s: round(c, 4) for s, c in svcs.items()} for m, svcs in merged_monthly.items()}
        aggregate['monthly_trend_months'] = sorted(merged_monthly.keys())

    for acct_id, acct_data in all_account_data.items():
        if 'error' not in acct_data:
            acct_total = sum(s['cost_usd'] for s in acct_data.get('cost_by_service', []))

            # Pass through ALL gathered data so the AI can answer any specific question.
            # Exclude only keys that are redundant or too large for the prompt.
            _exclude_keys = {'daily_cost_trend', 'cost_error', 'cloudwatch_error',
                             'ec2_error', 'rds_error', 's3_error', 'lambda_error',
                             'nat_gateway_error', 'kms_error'}
            per_acct = {k: v for k, v in acct_data.items() if k not in _exclude_keys}
            per_acct['total_spend'] = round(acct_total, 2)

            aggregate['per_account_data'][acct_id] = per_acct

    answer = _ask_bedrock_multi_account(question, tips_context, aggregate, all_account_data, account_ids)
    _maybe_save_tip(question, answer, tips_context)

    # Build chart data from aggregate including monthly trend
    chart_source = {
        'cost_by_service': aggregate['aggregate_cost_by_service'],
    }
    if merged_monthly:
        chart_source['monthly_trend'] = {m: {s: round(c, 4) for s, c in svcs.items()} for m, svcs in merged_monthly.items()}
        chart_source['monthly_trend_months'] = sorted(merged_monthly.keys())
    # Merge daily trends
    merged_daily = {}
    for acct_data in all_account_data.values():
        if isinstance(acct_data, dict) and 'error' not in acct_data:
            for d in acct_data.get('daily_cost_trend', []):
                date = d['date']
                merged_daily[date] = merged_daily.get(date, 0) + d['cost_usd']
    if merged_daily:
        chart_source['daily_cost_trend'] = [{'date': d, 'cost_usd': round(c, 4)} for d, c in sorted(merged_daily.items())]
    # Merge efficiency
    total_savings = sum(a.get('cost_efficiency', {}).get('potential_savings_usd', 0) for a in all_account_data.values() if isinstance(a, dict) and 'error' not in a)
    total_spend = aggregate['aggregate_total_spend']
    if total_spend > 0:
        eff_score = round((1 - total_savings / total_spend) * 100, 1)
        chart_source['cost_efficiency'] = {
            'score': max(0, eff_score),
            'rating': 'Excellent' if eff_score >= 90 else 'Good' if eff_score >= 75 else 'Needs Improvement' if eff_score >= 50 else 'Critical',
        }

    agg_chart_data = _build_chart_data(chart_source)

    top_services = [{'service': s['service'], 'cost': round(s['cost_usd'], 2)}
                    for s in aggregate['aggregate_cost_by_service'][:10]
                    if s['cost_usd'] > 0.5 and s['service'] != 'Tax']

    return create_response(200, {
        'answer': answer,
        'interactionId': interaction_id,
        'commands': all_actions,
        'results': [],
        'tipFound': bool(tips_context),
        'agentUsed': False,
        'chartData': agg_chart_data,
        'topServices': top_services,
        'multiAccount': True,
        'accountIds': account_ids,
    })


def _ask_bedrock_multi_account(question, tips_context, aggregate, all_account_data, account_ids):
    """Call Bedrock to analyze multi-account data."""
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    tips_text = ""
    if tips_context:
        tips_text = "\n\nRelevant optimization tips from our knowledge base:\n"
        for tip in tips_context[:5]:
            label = "[Validated] " if tip.get('confidenceTag') == 'high-confidence' else ""
            tips_text += f"- {label}{tip.get('title', '')}: {tip.get('description', '')} (Savings: {tip.get('estimatedSavings', 'N/A')})\n"

    # Trim per-account data to keep prompt manageable while preserving all key metrics
    trimmed_aggregate = dict(aggregate)
    trimmed_per_account = {}
    for acct_id, acct_data in aggregate.get('per_account_data', {}).items():
        trimmed = dict(acct_data)
        # Cap list fields to avoid blowing the prompt
        if trimmed.get('cost_by_service'):
            trimmed['cost_by_service'] = trimmed['cost_by_service'][:12]
        if trimmed.get('ec2_instances'):
            trimmed['ec2_instances'] = trimmed['ec2_instances'][:8]
        if trimmed.get('lambda_functions'):
            trimmed['lambda_functions'] = trimmed['lambda_functions'][:10]
        if trimmed.get('lambda_metrics'):
            trimmed['lambda_metrics'] = trimmed['lambda_metrics'][:10]
        if trimmed.get('rds_instances'):
            trimmed['rds_instances'] = trimmed['rds_instances'][:8]
        if trimmed.get('nat_gateways'):
            trimmed['nat_gateways'] = trimmed['nat_gateways'][:5]
        if trimmed.get('vpc_endpoints', {}).get('endpoints'):
            trimmed['vpc_endpoints']['endpoints'] = trimmed['vpc_endpoints']['endpoints'][:5]
        if trimmed.get('route53_hosted_zones'):
            trimmed['route53_hosted_zones'] = trimmed['route53_hosted_zones'][:10]
        trimmed_per_account[acct_id] = trimmed
    trimmed_aggregate['per_account_data'] = trimmed_per_account

    data_text = json.dumps(trimmed_aggregate, indent=2, default=str)
    if len(data_text) > 10000:
        data_text = data_text[:10000] + '\n... (truncated)'

    prompt = f"""You are SlashMyBill AI, an AWS FinOps assistant analyzing MULTIPLE AWS accounts.

CRITICAL RULE: Read the user's question carefully. If it is a SPECIFIC question (e.g. "list Lambda transactions", "show EC2 usage", "compare costs for Jan Feb March"), answer THAT question DIRECTLY and completely using the data provided. Do NOT default to a generic cost summary. The specific answer must come FIRST.

SPECIFIC QUESTION HANDLING:
- If the user asks about Lambda invocations/transactions: use lambda_metrics (invocations_30d per function) and monthly_trend (Lambda cost per month). Show per-function breakdown per account.
- If the user asks about EC2: use ec2_instances and ec2_cpu_metrics. Show instance IDs, types, CPU utilization.
- If the user asks about RDS: use rds_instances and rds_cpu_metrics. Show DB identifiers, instance class, CPU, connections.
- If the user asks about S3: use s3_buckets (per account). Show bucket names and count **per account separately** — never merge accounts or report only one. List ALL buckets without lifecycle policies from ALL accounts. Count must match the list length exactly.
- If the user asks about NAT Gateway: use nat_gateways and nat_gateway_metrics. Show gateway IDs, state, bytes transferred.
- If the user asks about EBS: use ebs_summary. Show total volumes, unattached count, gp2 vs gp3 breakdown.
- If the user asks about VPC/endpoints: use vpc_endpoints and elastic_ips. Show endpoint types, unattached EIPs.
- If the user asks about KMS: use kms_summary. Show total keys, customer-managed key count.
- If the user asks about Route 53: use route53_hosted_zones. Show zone names and record counts.
- If the user asks for a monthly comparison (Jan/Feb/March): use monthly_trend data — each key is YYYY-MM with service→cost dict. Show a table per account.
- If the user asks about a specific service: show ONLY that service's data across all accounts with exact numbers.
- Only after answering the specific question, add a brief cross-account summary if relevant.

GENERAL QUESTION RULES (only apply when the question is broad/general):
1. Start with AGGREGATE view: total spend across all {len(account_ids)} accounts, top services by combined cost.
2. Then break down PER ACCOUNT: each account's total spend and top services.
3. Identify cross-account patterns.
4. Savings recommendations ranked by total dollar impact.
5. NON-ACTIONABLE SERVICES (never list as savings): Tax, Amazon Registrar, AWS Cost Explorer, AWS CloudTrail.
6. Services < $0.50 across all accounts = Minor costs (do not list individually).
7. Do NOT give generic advice for services with $0 spend.
8. ALWAYS rank services by cost descending.

User question: {question}
{tips_text}

Multi-account data ({len(account_ids)} accounts):
{data_text}

Answer the user's question directly using the actual data above. Quote specific numbers, function names, and account IDs."""

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'maxTokens': 3000, 'temperature': 0.3},
            }),
        )
        response_body = json.loads(response['body'].read())
        return response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', 'No response from AI.')
    except Exception as e:
        logger.error(f"Bedrock multi-account call failed: {e}")
        return f'AI analysis error: {str(e)}'


def _build_chart_data(account_data):
    """Build chart data structures from gathered account data for frontend rendering."""
    charts = []

    # Chart 1: Top costs by service (horizontal bar)
    cost_by_service = account_data.get('cost_by_service', [])
    if cost_by_service:
        # Filter to services with cost > $0.01 and take top 8
        top = [s for s in cost_by_service if s['cost_usd'] > 0.01][:8]
        if top:
            charts.append({
                'id': 'service-costs',
                'title': 'Cost by Service (Last 30 Days)',
                'type': 'bar',
                'indexAxis': 'y',
                'labels': [s['service'].replace('Amazon ', '').replace('AWS ', '')[:25] for s in top],
                'data': [s['cost_usd'] for s in top],
                'color': '#6366f1',
            })

    # Chart 2: Daily cost trend (line)
    daily = account_data.get('daily_cost_trend', [])
    if daily and len(daily) > 1:
        charts.append({
            'id': 'daily-trend',
            'title': 'Daily Cost Trend (Last 7 Days)',
            'type': 'line',
            'labels': [d['date'][5:] for d in daily],  # MM-DD format
            'data': [d['cost_usd'] for d in daily],
            'color': '#10b981',
        })

    # Chart 3: VPC usage breakdown (doughnut) if available
    vpc_breakdown = account_data.get('amazon_virtual_private_cloud_usage_breakdown', [])
    if vpc_breakdown:
        items = [u for u in vpc_breakdown if u['cost_usd'] > 0.001][:6]
        if items:
            charts.append({
                'id': 'vpc-breakdown',
                'title': 'VPC Cost Breakdown',
                'type': 'doughnut',
                'labels': [u['usage_type'].split('-', 1)[-1] if '-' in u['usage_type'] else u['usage_type'] for u in items],
                'data': [u['cost_usd'] for u in items],
                'color': '#8b5cf6',
            })

    # Chart 4: EC2-Other usage breakdown (doughnut) if available
    ec2_breakdown = account_data.get('ec2___other_usage_breakdown', [])
    if ec2_breakdown:
        items = [u for u in ec2_breakdown if u['cost_usd'] > 0.001][:6]
        if items:
            charts.append({
                'id': 'ec2other-breakdown',
                'title': 'EC2-Other Cost Breakdown',
                'type': 'doughnut',
                'labels': [u['usage_type'].split(':')[-1] if ':' in u['usage_type'] else u['usage_type'] for u in items],
                'data': [u['cost_usd'] for u in items],
                'color': '#f59e0b',
            })

    # Chart 5: Month comparison (grouped bar) if available
    comparison = account_data.get('month_comparison')
    if comparison:
        m1 = comparison['month1']
        m2 = comparison['month2']
        all_services = {}
        for s in m1.get('costs', []):
            all_services[s['service']] = {'m1': s['cost_usd'], 'm2': 0}
        for s in m2.get('costs', []):
            if s['service'] in all_services:
                all_services[s['service']]['m2'] = s['cost_usd']
            else:
                all_services[s['service']] = {'m1': 0, 'm2': s['cost_usd']}
        sorted_svcs = sorted(all_services.items(), key=lambda x: max(x[1]['m1'], x[1]['m2']), reverse=True)[:8]
        if sorted_svcs:
            charts.append({
                'id': 'month-comparison',
                'title': f"{m1['label']} vs {m2['label']}",
                'type': 'bar',
                'labels': [s[0].replace('Amazon ', '').replace('AWS ', '')[:25] for s in sorted_svcs],
                'data': [s[1]['m1'] for s in sorted_svcs],
                'data2': [s[1]['m2'] for s in sorted_svcs],
                'data2Label': m2['label'],
                'dataLabel': m1['label'],
                'color': '#6366f1',
                'color2': '#10b981',
            })

    # Chart 6: Monthly trend (multi-month line) if available
    monthly_trend = account_data.get('monthly_trend', {})
    trend_months = account_data.get('monthly_trend_months', [])
    if len(trend_months) >= 2:
        # Convert YYYY-MM to readable month names
        _month_labels_map = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                             '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
        def _fmt_month(ym):
            parts = ym.split('-')
            return f"{_month_labels_map.get(parts[1], parts[1])} {parts[0]}" if len(parts) == 2 else ym
        readable_months = [_fmt_month(m) for m in trend_months]
        month_range_label = ' vs '.join(readable_months) if len(trend_months) <= 4 else f'{readable_months[0]} to {readable_months[-1]}'

        # Total cost per month
        month_totals = []
        for m in trend_months:
            total = sum(monthly_trend[m].values())
            month_totals.append(round(total, 2))
        charts.append({
            'id': 'monthly-total-trend',
            'title': f'Monthly Total Cost ({month_range_label})',
            'type': 'line',
            'labels': readable_months,
            'data': month_totals,
            'color': '#6366f1',
        })

        # Top services across all months — pass full monthly data for multi-column table
        all_svcs = {}
        for m in trend_months:
            for svc, cost in monthly_trend[m].items():
                all_svcs[svc] = all_svcs.get(svc, 0) + cost
        top_svcs = sorted(all_svcs.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_svcs:
            svc_names = [s[0].replace('Amazon ', '').replace('AWS ', '')[:30] for s in top_svcs]
            month_columns = {}
            for i, m in enumerate(trend_months):
                month_columns[readable_months[i]] = [round(monthly_trend.get(m, {}).get(s[0], 0), 2) for s in top_svcs]
            charts.append({
                'id': 'monthly-service-trend',
                'title': f'Cost by Service Comparison ({month_range_label})',
                'type': 'bar',
                'labels': svc_names,
                'monthColumns': month_columns,
                'months': readable_months,
                'data': [round(all_svcs[s[0]], 2) for s in top_svcs],
                'color': '#6366f1',
            })

    # Chart 7: Lambda invocations (bar) if available
    lambda_metrics = account_data.get('lambda_metrics', [])
    if lambda_metrics:
        active = [m for m in lambda_metrics if m['invocations_30d'] > 0]
        if active:
            charts.append({
                'id': 'lambda-invocations',
                'title': 'Lambda Invocations (Last 30 Days)',
                'type': 'bar',
                'indexAxis': 'y',
                'labels': [m['functionName'].replace('aws-bill-analyzer-', '')[:25] for m in active],
                'data': [m['invocations_30d'] for m in active],
                'color': '#f59e0b',
                'isCurrency': False,
            })

    # Chart 8: Cost Efficiency Score (gauge-like doughnut) if available
    efficiency = account_data.get('cost_efficiency')
    if efficiency:
        score = efficiency['score']
        charts.append({
            'id': 'efficiency-score',
            'title': f"Cost Efficiency Score: {score}% ({efficiency['rating']})",
            'type': 'doughnut',
            'labels': ['Efficient Spend', 'Potential Savings'],
            'data': [round(score, 1), round(100 - score, 1)],
            'color': '#10b981',
            'isCurrency': False,
        })

    return charts if charts else None


def _search_tips(question):
    """Search ViewMyBill-CostOptimizationTips for relevant tips matching the question."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    question_lower = question.lower()

    # Map keywords to the EXACT service names used in DynamoDB (case-sensitive)
    keyword_to_service = {
        'ec2': 'EC2', 's3': 'S3', 'rds': 'RDS', 'lambda': 'Lambda',
        'cloudfront': 'CloudFront', 'dynamodb': 'DynamoDB', 'ebs': 'EBS',
        'elb': 'ELB', 'ecs': 'ECS', 'eks': 'EKS', 'redshift': 'Redshift',
        'elasticache': 'ElastiCache', 'route53': 'Route53', 'route 53': 'Route53',
        'cloudwatch': 'CloudWatch', 'iam': 'IAM', 'vpc': 'VPC', 'nat': 'NAT Gateway',
        'kms': 'KMS', 'general': 'General', 'cost': 'General', 'billing': 'General',
        'save': 'General', 'efficient': 'General', 'optimize': 'General',
        'data transfer': 'Data Transfer', 'efs': 'EFS',
    }
    matched_services = set()
    for kw, svc in keyword_to_service.items():
        if kw in question_lower:
            matched_services.add(svc)

    tips = []
    try:
        if matched_services:
            for svc in list(matched_services)[:4]:
                result = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(svc)
                )
                tips.extend(result.get('Items', []))
            # Also check AI-GENERATED tips (from auto-save)
            try:
                ai_tips = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq('AI-GENERATED')
                )
                tips.extend(ai_tips.get('Items', []))
            except Exception:
                pass
        else:
            result = tips_table.scan(Limit=20)
            tips = result.get('Items', [])
    except ClientError as e:
        logger.warning(f"Tips table query error: {e}")

    # Deduplicate by tipId
    seen = set()
    unique_tips = []
    for t in tips:
        tid = t.get('tipId', '')
        if tid not in seen:
            seen.add(tid)
            unique_tips.append(t)

    # Sort: high-confidence first, then by feedbackScore (positive count), then curated
    def _tip_sort_key(t):
        if t.get('confidenceTag') == 'high-confidence':
            return (0, -(t.get('positiveCount', 0)))
        if t.get('source') == 'user-feedback':
            return (1, -(t.get('positiveCount', 0)))
        if t.get('source') == 'ai-agent':
            return (2, 0)
        return (3, 0)  # curated tips last
    unique_tips.sort(key=_tip_sort_key)

    return _decimal_to_native(unique_tips[:10])


def _gather_account_data(question, credentials):
    """Gather relevant AWS account data based on the question using direct boto3 calls."""
    question_lower = question.lower()
    data = {}
    actions = []

    def _make_client(service, region='us-east-1'):
        return boto3.client(
            service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region,
        )

    # Always get cost data — it's the most common question
    try:
        ce = _make_client('ce')
        end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        start_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')

        # Detect month comparison questions (e.g. "compare Feb and March", "Jan vs Feb")
        month_names = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
            'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
        }
        is_comparison = any(kw in question_lower for kw in ['compare', 'vs', 'versus', 'between', 'difference']) or \
                       any(kw in question for kw in ['השווה', 'תשווה', 'השוואה', 'לעומת'])
        mentioned_months = []
        for name, num in month_names.items():
            if name in question_lower:
                if num not in [m[1] for m in mentioned_months]:
                    mentioned_months.append((name, num))
        mentioned_months.sort(key=lambda x: x[1])

        # Detect "this month" / "last month" / "previous month" patterns
        now_dt = datetime.now(timezone.utc)
        if is_comparison and len(mentioned_months) < 2:
            has_this = any(kw in question_lower for kw in ['this month', 'current month', 'החודש הזה'])
            has_last = any(kw in question_lower for kw in ['last month', 'previous month', 'prior month', 'החודש שעבר', 'החודש הקודם'])
            if has_this and has_last:
                cur_m = now_dt.month
                prev_m = cur_m - 1 if cur_m > 1 else 12
                cur_name = list(month_names.keys())[list(month_names.values()).index(cur_m)]
                prev_name = list(month_names.keys())[list(month_names.values()).index(prev_m)]
                mentioned_months = [(prev_name, prev_m), (cur_name, cur_m)]
            elif has_last and not has_this:
                # "compare last month" alone — compare last month vs this month
                cur_m = now_dt.month
                prev_m = cur_m - 1 if cur_m > 1 else 12
                cur_name = list(month_names.keys())[list(month_names.values()).index(cur_m)]
                prev_name = list(month_names.keys())[list(month_names.values()).index(prev_m)]
                mentioned_months = [(prev_name, prev_m), (cur_name, cur_m)]

        # If comparing two specific months, fetch both explicitly
        # If 3+ months mentioned, use the monthly_trend path instead
        if is_comparison and len(mentioned_months) >= 2:
            # Unified approach: fetch the full range from first to last mentioned month
            now = datetime.now(timezone.utc)
            year_hint = now.year
            import re as _re
            year_match = _re.search(r'20\d{2}', question)
            if year_match:
                year_hint = int(year_match.group())
            from calendar import monthrange

            first_m = mentioned_months[0][1]
            last_m = mentioned_months[-1][1]
            range_start = f'{year_hint}-{first_m:02d}-01'
            if last_m == 12:
                range_end = f'{year_hint + 1}-01-01'
            else:
                range_end = f'{year_hint}-{last_m + 1:02d}-01'

            multi_month = ce.get_cost_and_usage(
                TimePeriod={'Start': range_start, 'End': range_end},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
            monthly_data = {}
            for period in multi_month.get('ResultsByTime', []):
                period_start = period['TimePeriod']['Start']
                month_label = period_start[:7]
                month_costs = {}
                for group in period.get('Groups', []):
                    svc = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0:
                        month_costs[svc] = round(cost, 4)
                monthly_data[month_label] = month_costs

            data['monthly_trend'] = monthly_data
            data['monthly_trend_months'] = sorted(monthly_data.keys())
            month_labels = [f'{mentioned_months[i][0].capitalize()} {year_hint}' for i in range(len(mentioned_months))]
            actions.append(f'ce:GetCostAndUsage (monthly trend, {" vs ".join(month_labels)})')

            # For exactly 2 months, also populate month_comparison for backward compatibility
            if len(mentioned_months) == 2:
                m1_key = f'{year_hint}-{first_m:02d}'
                m2_key = f'{year_hint}-{last_m:02d}'
                m1_costs = [{'service': s, 'cost_usd': c} for s, c in sorted(monthly_data.get(m1_key, {}).items(), key=lambda x: x[1], reverse=True)]
                m2_costs = [{'service': s, 'cost_usd': c} for s, c in sorted(monthly_data.get(m2_key, {}).items(), key=lambda x: x[1], reverse=True)]
                data['month_comparison'] = {
                    'month1': {'label': month_labels[0], 'period': f'{range_start} to {m2_key}-01', 'costs': m1_costs},
                    'month2': {'label': month_labels[1], 'period': f'{m2_key}-01 to {range_end}', 'costs': m2_costs},
                }

        # Detect relative time comparisons: "last 3 months", "past 6 months", "last quarter"
        # Also support Hebrew: "3 חודשים", "חודשים אחרונים"
        import re as _re2
        relative_match = _re2.search(r'last\s+(\d+)\s+month', question_lower) or \
                         _re2.search(r'past\s+(\d+)\s+month', question_lower) or \
                         _re2.search(r'(\d+)\s+month', question_lower)
        # Hebrew: "3 חודשים" or "חודשים"
        if not relative_match:
            hebrew_match = _re2.search(r'(\d+)\s*חודש', question)
            if hebrew_match:
                relative_match = hebrew_match
        if not relative_match and ('last quarter' in question_lower or 'past quarter' in question_lower or 'רבעון' in question):
            class _FakeMatch:
                def group(self, n): return '3'
            relative_match = _FakeMatch()
            # Treat "last quarter" as 3 months
            class _FakeMatch:
                def group(self, n): return '3'
            relative_match = _FakeMatch()

        if relative_match and 'month_comparison' not in data:
            num_months = min(int(relative_match.group(1)), 12)
            now = datetime.now(timezone.utc)

            # Fetch monthly data for the requested range
            # Start from num_months ago, first of that month
            start_month = now.month - num_months
            start_year = now.year
            while start_month <= 0:
                start_month += 12
                start_year -= 1
            range_start = f'{start_year}-{start_month:02d}-01'
            # End is first of current month + 1 (to include current partial month)
            if now.month == 12:
                range_end = f'{now.year + 1}-01-01'
            else:
                range_end = f'{now.year}-{now.month + 1:02d}-01'

            multi_month = ce.get_cost_and_usage(
                TimePeriod={'Start': range_start, 'End': range_end},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )

            # Organize by month
            monthly_data = {}
            for period in multi_month.get('ResultsByTime', []):
                period_start = period['TimePeriod']['Start']
                month_label = period_start[:7]  # YYYY-MM
                month_costs = {}
                for group in period.get('Groups', []):
                    svc = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0:
                        month_costs[svc] = round(cost, 4)
                monthly_data[month_label] = month_costs

            data['monthly_trend'] = monthly_data
            data['monthly_trend_months'] = sorted(monthly_data.keys())
            actions.append(f'ce:GetCostAndUsage (monthly trend, {range_start} to {range_end})')

        # Monthly cost by service — cost only (no UsageQuantity to avoid unit confusion)
        cost_by_service = ce.get_cost_and_usage(
            TimePeriod={'Start': start_30d, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )
        # Flatten to a clean list so the AI gets unambiguous numbers
        service_costs = []
        for period in cost_by_service.get('ResultsByTime', []):
            for group in period.get('Groups', []):
                svc = group['Keys'][0]
                cost_usd = float(group['Metrics']['UnblendedCost']['Amount'])
                if cost_usd > 0:
                    service_costs.append({
                        'service': svc,
                        'cost_usd': round(cost_usd, 4),
                        'period': f"{period['TimePeriod']['Start']} to {period['TimePeriod']['End']}",
                    })
        service_costs.sort(key=lambda x: x['cost_usd'], reverse=True)
        data['cost_by_service'] = service_costs
        actions.append('ce:GetCostAndUsage (monthly by service, last 30 days)')

        # Daily cost trend — cost only
        start_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
        daily_cost = ce.get_cost_and_usage(
            TimePeriod={'Start': start_7d, 'End': end_date},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
        )
        daily_costs = []
        for period in daily_cost.get('ResultsByTime', []):
            daily_costs.append({
                'date': period['TimePeriod']['Start'],
                'cost_usd': round(float(period['Total']['UnblendedCost']['Amount']), 4),
            })
        data['daily_cost_trend'] = daily_costs
        actions.append('ce:GetCostAndUsage (daily, last 7 days)')

        # For top-cost services that are hard to explain (VPC, EC2-Other),
        # fetch a USAGE_TYPE breakdown so the AI can identify the exact driver
        top_svc_names = [s['service'] for s in service_costs[:6]]
        breakdown_services = []
        if 'Amazon Virtual Private Cloud' in top_svc_names:
            breakdown_services.append('Amazon Virtual Private Cloud')
        if 'EC2 - Other' in top_svc_names:
            breakdown_services.append('EC2 - Other')

        for svc_name in breakdown_services:
            try:
                usage_breakdown = ce.get_cost_and_usage(
                    TimePeriod={'Start': start_30d, 'End': end_date},
                    Granularity='MONTHLY',
                    Metrics=['UnblendedCost'],
                    GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}],
                    Filter={'Dimensions': {'Key': 'SERVICE', 'Values': [svc_name]}},
                )
                usage_items = []
                for period in usage_breakdown.get('ResultsByTime', []):
                    for group in period.get('Groups', []):
                        usage_type = group['Keys'][0]
                        cost = float(group['Metrics']['UnblendedCost']['Amount'])
                        if cost > 0.001:
                            usage_items.append({
                                'usage_type': usage_type,
                                'cost_usd': round(cost, 4),
                            })
                usage_items.sort(key=lambda x: x['cost_usd'], reverse=True)
                safe_key = svc_name.replace(' ', '_').replace('-', '_').lower()
                data[f'{safe_key}_usage_breakdown'] = usage_items
                actions.append(f'ce:GetCostAndUsage (usage type breakdown for {svc_name})')
            except Exception as e:
                logger.warning(f"Usage type breakdown failed for {svc_name}: {e}")
    except Exception as e:
        data['cost_error'] = str(e)
        logger.warning(f"Cost Explorer error: {e}")

    # EC2 instances — fetch when question mentions EC2 OR when EC2 Compute is a top cost
    # (needed for pricing engine to use actual instance types)
    top_service_names_ec2 = [s['service'] for s in data.get('cost_by_service', [])[:8]]
    if 'Amazon Elastic Compute Cloud - Compute' in top_service_names_ec2 or \
       any(kw in question_lower for kw in ['ec2', 'instance', 'server', 'compute', 'running', 'saving', 'save', 'efficient', 'optimize', 'ri', 'reserved']):
        try:
            ec2 = _make_client('ec2')
            instances = ec2.describe_instances()
            instance_list = []
            for res in instances.get('Reservations', []):
                for inst in res.get('Instances', []):
                    name_tag = ''
                    for tag in inst.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name_tag = tag['Value']
                    instance_list.append({
                        'id': inst['InstanceId'],
                        'type': inst['InstanceType'],
                        'state': inst['State']['Name'],
                        'name': name_tag,
                        'az': inst.get('Placement', {}).get('AvailabilityZone', ''),
                        'tags_raw': inst.get('Tags', []),
                    })
            data['ec2_instances'] = instance_list
            actions.append('ec2:DescribeInstances')
        except Exception as e:
            data['ec2_error'] = str(e)

    # NAT Gateways — always fetch when EC2-Other or VPC are top costs (they drive those bills)
    # SKIP if question is specifically about a single service — irrelevant data wastes tokens
    _specific_service_question = any(kw in question_lower for kw in [
        'lifecycle', 'bucket', 's3 bucket', 'intelligent-tier', 'glacier', 'storage class',  # S3
        'kms', 'key management', 'encryption key', 'customer-managed key',                    # KMS
        'lambda function', 'invocation', 'serverless function',                               # Lambda
        'rds instance', 'database instance', 'db instance',                                   # RDS specific
        'snapshot', 'ebs snapshot',                                                            # Snapshots
        'budget', 'cost alert', 'billing alarm', 'spend limit',                               # Budgets
    ])
    top_service_names = [s['service'] for s in data.get('cost_by_service', [])[:6]]
    if not _specific_service_question and (
        any(s in top_service_names for s in ['EC2 - Other', 'Amazon Virtual Private Cloud']) or
        any(kw in question_lower for kw in ['nat', 'vpc', 'network', 'data transfer'])
    ):
        try:
            ec2 = _make_client('ec2')
            nat_gws = ec2.describe_nat_gateways(
                Filter=[{'Name': 'state', 'Values': ['available', 'pending']}]
            )
            nat_list = []
            for gw in nat_gws.get('NatGateways', []):
                name_tag = next((t['Value'] for t in gw.get('Tags', []) if t['Key'] == 'Name'), '')
                nat_list.append({
                    'natGatewayId': gw['NatGatewayId'],
                    'state': gw['State'],
                    'subnetId': gw['SubnetId'],
                    'vpcId': gw['VpcId'],
                    'name': name_tag,
                    'createTime': str(gw.get('CreateTime', '')),
                })
            data['nat_gateways'] = nat_list
            data['nat_gateway_count'] = len(nat_list)
            actions.append('ec2:DescribeNatGateways')

            # Elastic IPs — unattached ones cost $0.005/hr (~$3.65/month each)
            eips = ec2.describe_addresses()
            unattached_eips = [
                {'allocationId': e.get('AllocationId', ''), 'publicIp': e.get('PublicIp', '')}
                for e in eips.get('Addresses', [])
                if not e.get('AssociationId')
            ]
            data['elastic_ips'] = {
                'total': len(eips.get('Addresses', [])),
                'unattached': len(unattached_eips),
                'unattached_monthly_cost_usd': round(len(unattached_eips) * 3.65, 2),
                'unattached_list': unattached_eips[:10],
            }
            actions.append('ec2:DescribeAddresses')

            # VPC Endpoints — each interface endpoint costs ~$7.20/month
            endpoints = ec2.describe_vpc_endpoints(
                Filters=[{'Name': 'vpc-endpoint-state', 'Values': ['available', 'pending']}]
            )
            ep_list = []
            for ep in endpoints.get('VpcEndpoints', []):
                ep_list.append({
                    'endpointId': ep.get('VpcEndpointId', ''),
                    'type': ep.get('VpcEndpointType', ''),
                    'serviceName': ep.get('ServiceName', ''),
                    'state': ep.get('State', ''),
                })
            interface_ep_count = sum(1 for e in ep_list if e['type'] == 'Interface')
            data['vpc_endpoints'] = {
                'total': len(ep_list),
                'interface_count': interface_ep_count,
                'interface_monthly_cost_usd': round(interface_ep_count * 7.20, 2),
                'endpoints': ep_list[:10],
            }
            actions.append('ec2:DescribeVpcEndpoints')

            # Also fetch EBS volumes to explain EC2-Other storage costs
            vols = ec2.describe_volumes()
            vol_summary = {'total_gb': 0, 'gp2_count': 0, 'gp2_gb': 0, 'gp3_count': 0, 'io1_count': 0,
                           'unattached_count': 0, 'unattached_gb': 0, 'unattached_volumes': []}
            for v in vols.get('Volumes', []):
                size = v.get('Size', 0)
                vol_summary['total_gb'] += size
                vtype = v.get('VolumeType', '')
                if vtype == 'gp2':
                    vol_summary['gp2_count'] += 1
                    vol_summary['gp2_gb'] += size
                elif vtype == 'gp3':
                    vol_summary['gp3_count'] += 1
                elif vtype == 'io1':
                    vol_summary['io1_count'] += 1
                if not v.get('Attachments'):
                    vol_summary['unattached_count'] += 1
                    vol_summary['unattached_gb'] += size
                    vol_summary['unattached_volumes'].append({
                        'volumeId': v['VolumeId'],
                        'size_gb': size,
                        'type': vtype,
                        'monthly_cost_usd': round(size * 0.10, 2) if vtype in ('gp2', 'gp3') else round(size * 0.125, 2),
                    })
            # gp2 costs $0.10/GB/month, gp3 costs $0.08/GB/month
            vol_summary['unattached_monthly_cost_usd'] = round(vol_summary['unattached_gb'] * 0.10, 2)
            vol_summary['gp2_to_gp3_savings_usd'] = round(vol_summary['gp2_gb'] * 0.02, 2)  # $0.02/GB saving
            data['ebs_summary'] = vol_summary
            actions.append('ec2:DescribeVolumes')
        except Exception as e:
            data['nat_gateway_error'] = str(e)

    # S3 if question mentions S3, storage, buckets
    if any(kw in question_lower for kw in ['s3', 'storage', 'bucket']):
        try:
            s3 = _make_client('s3')
            buckets = s3.list_buckets()
            data['s3_buckets'] = [{'name': b['Name'], 'created': str(b['CreationDate'])} for b in buckets.get('Buckets', [])]
            actions.append('s3:ListBuckets')
        except Exception as e:
            data['s3_error'] = str(e)

    # RDS — fetch when it's a top cost or question mentions database
    top_service_names_rds = [s['service'] for s in data.get('cost_by_service', [])[:8]]
    if 'Amazon Relational Database Service' in top_service_names_rds or \
       any(kw in question_lower for kw in ['rds', 'database', 'db']):
        try:
            rds = _make_client('rds')
            dbs = rds.describe_db_instances()
            data['rds_instances'] = [{'id': d['DBInstanceIdentifier'], 'class': d['DBInstanceClass'],
                                       'engine': d['Engine'], 'status': d['DBInstanceStatus'],
                                       'multiAz': d.get('MultiAZ', False),
                                       'storage_gb': d.get('AllocatedStorage', 0)} for d in dbs.get('DBInstances', [])]
            actions.append('rds:DescribeDBInstances')
        except Exception as e:
            data['rds_error'] = str(e)

    # KMS — fetch key count when KMS is a top cost
    top_service_names_kms = [s['service'] for s in data.get('cost_by_service', [])[:8]]
    if 'AWS Key Management Service' in top_service_names_kms or \
       any(kw in question_lower for kw in ['kms', 'key management', 'encryption key']):
        try:
            kms = _make_client('kms')
            keys = kms.list_keys()
            aliases = kms.list_aliases()
            # Customer-managed keys cost $1/month each; AWS-managed are free
            cmk_count = sum(1 for k in keys.get('Keys', [])
                            if not any(a.get('AliasName', '').startswith('alias/aws/')
                                       for a in aliases.get('Aliases', [])
                                       if a.get('TargetKeyId') == k['KeyId']))
            data['kms_summary'] = {
                'total_keys': len(keys.get('Keys', [])),
                'customer_managed_keys': cmk_count,
                'monthly_cost_usd': round(cmk_count * 1.0, 2),
                'note': 'Customer-managed KMS keys cost $1/month each. AWS-managed keys are free.',
            }
            actions.append('kms:ListKeys')
        except Exception as e:
            data['kms_error'] = str(e)

    # Lambda if question mentions Lambda, functions
    if any(kw in question_lower for kw in ['lambda', 'function', 'serverless']):
        try:
            lam = _make_client('lambda')
            funcs = lam.list_functions()
            data['lambda_functions'] = [{'name': f['FunctionName'], 'runtime': f.get('Runtime', ''), 'memory': f.get('MemorySize', 0), 'timeout': f.get('Timeout', 0)} for f in funcs.get('Functions', [])]
            actions.append('lambda:ListFunctions')
        except Exception as e:
            data['lambda_error'] = str(e)

    # Budgets — fetch when question mentions budgets/alerts/cost alerts
    if any(kw in question_lower for kw in ['budget', 'alert', 'cost alert', 'billing alarm', 'spend limit']):
        try:
            budgets_client = _make_client('budgets')
            # Need account_id for describe_budgets — derive from STS
            sts = boto3.client('sts',
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
            )
            acct_id = sts.get_caller_identity()['Account']
            blist = budgets_client.describe_budgets(AccountId=acct_id).get('Budgets', [])
            data['budgets'] = [
                {
                    'name': b.get('BudgetName', ''),
                    'type': b.get('BudgetType', ''),
                    'limit': float(b.get('BudgetLimit', {}).get('Amount', 0)),
                    'currency': b.get('BudgetLimit', {}).get('Unit', 'USD'),
                    'timeUnit': b.get('TimeUnit', ''),
                    'actualSpend': float(b.get('CalculatedSpend', {}).get('ActualSpend', {}).get('Amount', 0)),
                    'forecastedSpend': float(b.get('CalculatedSpend', {}).get('ForecastedSpend', {}).get('Amount', 0)),
                }
                for b in blist
            ]
            data['budget_count'] = len(blist)
            actions.append('budgets:DescribeBudgets')
        except Exception as e:
            data['budgets'] = []
            data['budget_count'] = 0
            logger.warning(f"Budgets fetch failed: {e}")

    # ============================================================
    # CloudWatch Rightsizing Metrics — auto-fetch for ALL top-cost services
    # For each paid service, get peak + average usage over 30 days
    # ============================================================
    top_svc_names_cw = [s['service'] for s in data.get('cost_by_service', [])[:8]]
    try:
        cw = _make_client('cloudwatch')
        now = datetime.now(timezone.utc)
        start_30d_dt = now - timedelta(days=30)

        # Lambda invocation metrics per function
        if data.get('lambda_functions'):
            lambda_metrics = []
            for func in data['lambda_functions'][:10]:
                try:
                    inv_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda', MetricName='Invocations',
                        Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                    )
                    dur_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda', MetricName='Duration',
                        Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    err_resp = cw.get_metric_statistics(
                        Namespace='AWS/Lambda', MetricName='Errors',
                        Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                    )
                    invocations = sum(dp['Sum'] for dp in inv_resp.get('Datapoints', []))
                    avg_duration = next((dp['Average'] for dp in dur_resp.get('Datapoints', [])), 0)
                    max_duration = next((dp['Maximum'] for dp in dur_resp.get('Datapoints', [])), 0)
                    errors = sum(dp['Sum'] for dp in err_resp.get('Datapoints', []))
                    lambda_metrics.append({
                        'functionName': func['name'], 'invocations_30d': int(invocations),
                        'avg_duration_ms': round(avg_duration, 1), 'max_duration_ms': round(max_duration, 1),
                        'errors_30d': int(errors), 'memory_mb': func.get('memory', 0),
                    })
                except Exception:
                    pass
            lambda_metrics.sort(key=lambda x: x['invocations_30d'], reverse=True)
            data['lambda_metrics'] = lambda_metrics
            actions.append('cloudwatch:GetMetricStatistics (Lambda invocations, duration, errors)')

        # EC2 CPU + Network utilization
        if data.get('ec2_instances'):
            ec2_metrics = []
            for inst in data['ec2_instances'][:10]:
                if inst.get('state') != 'running':
                    continue
                try:
                    cpu_resp = cw.get_metric_statistics(
                        Namespace='AWS/EC2', MetricName='CPUUtilization',
                        Dimensions=[{'Name': 'InstanceId', 'Value': inst['id']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    net_in = cw.get_metric_statistics(
                        Namespace='AWS/EC2', MetricName='NetworkIn',
                        Dimensions=[{'Name': 'InstanceId', 'Value': inst['id']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    net_out = cw.get_metric_statistics(
                        Namespace='AWS/EC2', MetricName='NetworkOut',
                        Dimensions=[{'Name': 'InstanceId', 'Value': inst['id']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    # Try CWAgent memory metrics (requires CloudWatch agent installed)
                    mem_resp = cw.get_metric_statistics(
                        Namespace='CWAgent', MetricName='mem_used_percent',
                        Dimensions=[{'Name': 'InstanceId', 'Value': inst['id']}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    avg_cpu = next((dp['Average'] for dp in cpu_resp.get('Datapoints', [])), 0)
                    max_cpu = next((dp['Maximum'] for dp in cpu_resp.get('Datapoints', [])), 0)
                    avg_net_in = next((dp['Average'] for dp in net_in.get('Datapoints', [])), 0)
                    avg_net_out = next((dp['Average'] for dp in net_out.get('Datapoints', [])), 0)
                    avg_mem = next((dp['Average'] for dp in mem_resp.get('Datapoints', [])), None)
                    max_mem = next((dp['Maximum'] for dp in mem_resp.get('Datapoints', [])), None)

                    # Detect environment from tags for scheduling recommendation
                    env_tag = ''
                    for tag in inst.get('tags_raw', []):
                        if tag.get('Key', '').lower() in ('environment', 'env', 'stage'):
                            env_tag = tag.get('Value', '').lower()

                    note = ''
                    is_non_prod = env_tag in ('dev', 'development', 'test', 'testing', 'staging', 'qa', 'sandbox')
                    if avg_cpu < 10 and max_cpu < 30:
                        if is_non_prod:
                            note = 'NON-PROD + LOW CPU — consider Instance Scheduler (stop nights/weekends for ~65% savings)'
                        else:
                            note = 'OVER-PROVISIONED — avg CPU very low, consider downsizing'
                    elif avg_cpu < 20:
                        note = 'Potentially over-provisioned — monitor before committing'
                    # Check if Graviton migration candidate (x86 instance families)
                    itype = inst.get('type', '')
                    is_x86 = any(itype.startswith(f) for f in ['t3.', 'm5.', 'c5.', 'r5.', 'm6i.', 'c6i.', 'r6i.'])
                    graviton_note = 'Graviton migration candidate (20-40% better price-performance)' if is_x86 else ''

                    metric = {
                        'instanceId': inst['id'], 'type': inst.get('type', ''),
                        'name': inst.get('name', ''),
                        'avg_cpu_pct': round(avg_cpu, 1), 'max_cpu_pct': round(max_cpu, 1),
                        'avg_network_in_mb': round(avg_net_in / (1024*1024), 2),
                        'avg_network_out_mb': round(avg_net_out / (1024*1024), 2),
                        'rightsizing_note': note,
                    }
                    if avg_mem is not None:
                        metric['avg_memory_pct'] = round(avg_mem, 1)
                        metric['max_memory_pct'] = round(max_mem, 1) if max_mem else None
                        metric['memory_agent_installed'] = True
                    else:
                        metric['memory_agent_installed'] = False
                    if env_tag:
                        metric['environment_tag'] = env_tag
                    if graviton_note:
                        metric['graviton_note'] = graviton_note
                    ec2_metrics.append(metric)
                except Exception:
                    pass
            if ec2_metrics:
                data['ec2_cpu_metrics'] = ec2_metrics
                actions.append('cloudwatch:GetMetricStatistics (EC2 CPU, memory, network)')

        # RDS CPU, connections, memory, read/write IOPS
        if data.get('rds_instances'):
            rds_metrics = []
            for db in data['rds_instances'][:10]:
                db_id = db.get('id', '')
                if not db_id or db.get('status') != 'available':
                    continue
                try:
                    cpu_resp = cw.get_metric_statistics(
                        Namespace='AWS/RDS', MetricName='CPUUtilization',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    conn_resp = cw.get_metric_statistics(
                        Namespace='AWS/RDS', MetricName='DatabaseConnections',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    mem_resp = cw.get_metric_statistics(
                        Namespace='AWS/RDS', MetricName='FreeableMemory',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Minimum'],
                    )
                    riops = cw.get_metric_statistics(
                        Namespace='AWS/RDS', MetricName='ReadIOPS',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    wiops = cw.get_metric_statistics(
                        Namespace='AWS/RDS', MetricName='WriteIOPS',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                    )
                    avg_cpu = next((dp['Average'] for dp in cpu_resp.get('Datapoints', [])), 0)
                    max_cpu = next((dp['Maximum'] for dp in cpu_resp.get('Datapoints', [])), 0)
                    avg_conn = next((dp['Average'] for dp in conn_resp.get('Datapoints', [])), 0)
                    max_conn = next((dp['Maximum'] for dp in conn_resp.get('Datapoints', [])), 0)
                    avg_mem = next((dp['Average'] for dp in mem_resp.get('Datapoints', [])), 0)
                    min_mem = next((dp['Minimum'] for dp in mem_resp.get('Datapoints', [])), 0)
                    avg_riops = next((dp['Average'] for dp in riops.get('Datapoints', [])), 0)
                    max_riops = next((dp['Maximum'] for dp in riops.get('Datapoints', [])), 0)
                    avg_wiops = next((dp['Average'] for dp in wiops.get('Datapoints', [])), 0)
                    max_wiops = next((dp['Maximum'] for dp in wiops.get('Datapoints', [])), 0)

                    note = ''
                    if avg_cpu < 10 and max_cpu < 30:
                        note = 'OVER-PROVISIONED — avg CPU very low, downsize instance class'
                    elif avg_cpu > 80:
                        note = 'HIGH CPU — consider upsizing or read replicas'

                    rds_metrics.append({
                        'dbInstanceId': db_id, 'instanceClass': db.get('class', ''),
                        'engine': db.get('engine', ''), 'multiAz': db.get('multiAz', False),
                        'storage_gb': db.get('storage_gb', 0),
                        'avg_cpu_pct': round(avg_cpu, 1), 'max_cpu_pct': round(max_cpu, 1),
                        'avg_connections': round(avg_conn, 1), 'max_connections': int(max_conn),
                        'avg_freeable_memory_gb': round(avg_mem / (1024**3), 2) if avg_mem else 0,
                        'min_freeable_memory_gb': round(min_mem / (1024**3), 2) if min_mem else 0,
                        'avg_read_iops': round(avg_riops, 1), 'max_read_iops': round(max_riops, 1),
                        'avg_write_iops': round(avg_wiops, 1), 'max_write_iops': round(max_wiops, 1),
                        'rightsizing_note': note,
                    })
                except Exception:
                    pass
            if rds_metrics:
                data['rds_cpu_metrics'] = rds_metrics
                actions.append('cloudwatch:GetMetricStatistics (RDS CPU, connections, memory, IOPS)')

        # ELB metrics — request count, active connections
        if 'Amazon Elastic Load Balancing' in top_svc_names_cw:
            try:
                elbv2 = _make_client('elbv2')
                lbs = elbv2.describe_load_balancers()
                elb_metrics = []
                for lb in lbs.get('LoadBalancers', [])[:10]:
                    lb_name = lb.get('LoadBalancerName', '')
                    lb_arn = lb.get('LoadBalancerArn', '')
                    lb_type = lb.get('Type', '')
                    arn_suffix = lb_arn.split(':loadbalancer/')[-1] if ':loadbalancer/' in lb_arn else ''
                    if not arn_suffix:
                        continue
                    try:
                        ns = 'AWS/ApplicationELB' if lb_type == 'application' else 'AWS/NetworkELB'
                        metric_name = 'RequestCount' if lb_type == 'application' else 'ActiveFlowCount'
                        req_resp = cw.get_metric_statistics(
                            Namespace=ns, MetricName=metric_name,
                            Dimensions=[{'Name': 'LoadBalancer', 'Value': arn_suffix}],
                            StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                        )
                        total_requests = sum(dp['Sum'] for dp in req_resp.get('Datapoints', []))
                        note = ''
                        if total_requests == 0:
                            note = 'ZERO TRAFFIC — candidate for deletion'
                        elif total_requests < 1000:
                            note = 'Very low traffic — consider consolidating'
                        elb_metrics.append({
                            'name': lb_name, 'type': lb_type,
                            'total_requests_30d': int(total_requests),
                            'rightsizing_note': note,
                        })
                    except Exception:
                        pass
                if elb_metrics:
                    data['elb_metrics'] = elb_metrics
                    actions.append('cloudwatch:GetMetricStatistics (ELB requests)')
            except Exception as e:
                logger.warning(f"ELB metrics error: {e}")

        # NAT Gateway metrics — bytes processed, active connections
        if data.get('nat_gateways'):
            try:
                nat_metrics = []
                for gw in data['nat_gateways'][:5]:
                    gw_id = gw.get('natGatewayId', '')
                    if not gw_id:
                        continue
                    try:
                        bytes_out = cw.get_metric_statistics(
                            Namespace='AWS/NATGateway', MetricName='BytesOutToDestination',
                            Dimensions=[{'Name': 'NatGatewayId', 'Value': gw_id}],
                            StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                        )
                        active_conn = cw.get_metric_statistics(
                            Namespace='AWS/NATGateway', MetricName='ActiveConnectionCount',
                            Dimensions=[{'Name': 'NatGatewayId', 'Value': gw_id}],
                            StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Average', 'Maximum'],
                        )
                        total_bytes = sum(dp['Sum'] for dp in bytes_out.get('Datapoints', []))
                        avg_conn = next((dp['Average'] for dp in active_conn.get('Datapoints', [])), 0)
                        max_conn = next((dp['Maximum'] for dp in active_conn.get('Datapoints', [])), 0)
                        note = ''
                        if total_bytes < 1024 * 1024:
                            note = 'VERY LOW TRAFFIC — candidate for deletion'
                        nat_metrics.append({
                            'natGatewayId': gw_id, 'vpcId': gw.get('vpcId', ''),
                            'name': gw.get('name', ''),
                            'total_bytes_out_30d_gb': round(total_bytes / (1024**3), 2),
                            'avg_active_connections': round(avg_conn, 1),
                            'max_active_connections': int(max_conn),
                            'rightsizing_note': note,
                        })
                    except Exception:
                        pass
                if nat_metrics:
                    data['nat_gateway_metrics'] = nat_metrics
                    actions.append('cloudwatch:GetMetricStatistics (NAT Gateway bytes, connections)')
            except Exception as e:
                logger.warning(f"NAT Gateway metrics error: {e}")

        # EBS Volume IOPS — identify over-provisioned io1/io2 or underused volumes
        ebs_data = data.get('ebs_summary', {})
        if ebs_data.get('total_gb', 0) > 0:
            try:
                ec2_vol = _make_client('ec2')
                vols = ec2_vol.describe_volumes()
                ebs_metrics = []
                for v in vols.get('Volumes', [])[:15]:
                    vid = v['VolumeId']
                    vtype = v.get('VolumeType', '')
                    if not v.get('Attachments'):
                        continue
                    try:
                        r_iops = cw.get_metric_statistics(
                            Namespace='AWS/EBS', MetricName='VolumeReadOps',
                            Dimensions=[{'Name': 'VolumeId', 'Value': vid}],
                            StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                        )
                        w_iops = cw.get_metric_statistics(
                            Namespace='AWS/EBS', MetricName='VolumeWriteOps',
                            Dimensions=[{'Name': 'VolumeId', 'Value': vid}],
                            StartTime=start_30d_dt, EndTime=now, Period=2592000, Statistics=['Sum'],
                        )
                        total_reads = sum(dp['Sum'] for dp in r_iops.get('Datapoints', []))
                        total_writes = sum(dp['Sum'] for dp in w_iops.get('Datapoints', []))
                        avg_read_iops = round(total_reads / (30 * 86400), 1) if total_reads else 0
                        avg_write_iops = round(total_writes / (30 * 86400), 1) if total_writes else 0
                        note = ''
                        if vtype in ('io1', 'io2') and avg_read_iops + avg_write_iops < 100:
                            note = 'LOW IOPS on provisioned volume — consider switching to gp3'
                        ebs_metrics.append({
                            'volumeId': vid, 'type': vtype, 'size_gb': v.get('Size', 0),
                            'provisioned_iops': v.get('Iops', 0),
                            'avg_read_iops': avg_read_iops, 'avg_write_iops': avg_write_iops,
                            'rightsizing_note': note,
                        })
                    except Exception:
                        pass
                if ebs_metrics:
                    data['ebs_iops_metrics'] = ebs_metrics
                    actions.append('cloudwatch:GetMetricStatistics (EBS read/write IOPS)')
            except Exception as e:
                logger.warning(f"EBS metrics error: {e}")

    except Exception as e:
        data['cloudwatch_error'] = str(e)
        logger.warning(f"CloudWatch metrics error: {e}")

        # Route 53 — fetch when it's a top cost or question mentions DNS/Route53
    top_service_names_r53 = [s['service'] for s in data.get('cost_by_service', [])[:8]]
    if 'Amazon Route 53' in top_service_names_r53 or \
       any(kw in question_lower for kw in ['route53', 'route 53', 'dns', 'hosted zone']):
        try:
            r53 = _make_client('route53')
            zones = r53.list_hosted_zones()
            zone_list = []
            for z in zones.get('HostedZones', []):
                zone_list.append({
                    'name': z['Name'],
                    'id': z['Id'],
                    'recordCount': z['ResourceRecordSetCount'],
                    'private': z['Config'].get('PrivateZone', False),
                })
            data['route53_hosted_zones'] = zone_list
            data['route53_zone_count'] = len(zone_list)
            # Route 53 pricing: $0.50/month per hosted zone (first 25), $0.10 per million queries
            data['route53_pricing_note'] = '$0.50/month per hosted zone (first 25 zones). Delete unused zones to reduce costs.'
            actions.append('route53:ListHostedZones')
        except Exception as e:
            data['route53_error'] = str(e)

    # ============================================================
    # EKS/ECS Kubernetes & Container Clusters
    # ============================================================
    top_svc_names_k8s = [s['service'] for s in data.get('cost_by_service', [])[:10]]
    if any(s in top_svc_names_k8s for s in ['Amazon Elastic Container Service', 'Amazon Elastic Kubernetes Service',
                                              'Amazon Elastic Container Service for Kubernetes']) or \
       any(kw in question_lower for kw in ['eks', 'ecs', 'kubernetes', 'k8s', 'container', 'cluster', 'pod', 'node']):
        try:
            # EKS clusters
            eks = _make_client('eks')
            eks_clusters = eks.list_clusters().get('clusters', [])
            eks_details = []
            for cluster_name in eks_clusters[:5]:
                try:
                    detail = eks.describe_cluster(name=cluster_name)['cluster']
                    eks_details.append({
                        'name': cluster_name,
                        'status': detail.get('status', ''),
                        'version': detail.get('version', ''),
                        'platformVersion': detail.get('platformVersion', ''),
                    })
                except Exception:
                    eks_details.append({'name': cluster_name, 'status': 'unknown'})
            data['eks_clusters'] = eks_details
            data['eks_cluster_count'] = len(eks_clusters)
            actions.append('eks:ListClusters + eks:DescribeCluster')
        except Exception as e:
            data['eks_error'] = str(e)

        try:
            # ECS clusters
            ecs = _make_client('ecs')
            ecs_arns = ecs.list_clusters().get('clusterArns', [])
            if ecs_arns:
                ecs_details_resp = ecs.describe_clusters(clusters=ecs_arns[:10])
                ecs_details = []
                for c in ecs_details_resp.get('clusters', []):
                    ecs_details.append({
                        'name': c.get('clusterName', ''),
                        'status': c.get('status', ''),
                        'runningTasks': c.get('runningTasksCount', 0),
                        'pendingTasks': c.get('pendingTasksCount', 0),
                        'registeredInstances': c.get('registeredContainerInstancesCount', 0),
                        'activeServices': c.get('activeServicesCount', 0),
                    })
                data['ecs_clusters'] = ecs_details
            else:
                data['ecs_clusters'] = []
            data['ecs_cluster_count'] = len(ecs_arns)
            actions.append('ecs:ListClusters + ecs:DescribeClusters')

            # ECS service-level CloudWatch metrics for rightsizing
            if data.get('ecs_clusters'):
                try:
                    ecs_svc_metrics = []
                    for cluster in data['ecs_clusters'][:5]:
                        cname = cluster.get('name', '')
                        if not cname or cluster.get('activeServices', 0) == 0:
                            continue
                        try:
                            svcs = ecs.list_services(cluster=cname, maxResults=10)
                            svc_arns = svcs.get('serviceArns', [])
                            if svc_arns:
                                svc_details = ecs.describe_services(cluster=cname, services=svc_arns)
                                for svc in svc_details.get('services', []):
                                    svc_name = svc.get('serviceName', '')
                                    try:
                                        cpu_resp = cw.get_metric_statistics(
                                            Namespace='AWS/ECS', MetricName='CPUUtilization',
                                            Dimensions=[{'Name': 'ClusterName', 'Value': cname},
                                                        {'Name': 'ServiceName', 'Value': svc_name}],
                                            StartTime=start_30d_dt, EndTime=now, Period=2592000,
                                            Statistics=['Average', 'Maximum'],
                                        )
                                        mem_resp = cw.get_metric_statistics(
                                            Namespace='AWS/ECS', MetricName='MemoryUtilization',
                                            Dimensions=[{'Name': 'ClusterName', 'Value': cname},
                                                        {'Name': 'ServiceName', 'Value': svc_name}],
                                            StartTime=start_30d_dt, EndTime=now, Period=2592000,
                                            Statistics=['Average', 'Maximum'],
                                        )
                                        avg_cpu = next((dp['Average'] for dp in cpu_resp.get('Datapoints', [])), 0)
                                        max_cpu = next((dp['Maximum'] for dp in cpu_resp.get('Datapoints', [])), 0)
                                        avg_mem = next((dp['Average'] for dp in mem_resp.get('Datapoints', [])), 0)
                                        max_mem = next((dp['Maximum'] for dp in mem_resp.get('Datapoints', [])), 0)
                                        note = ''
                                        if avg_cpu < 10 and avg_mem < 20:
                                            note = 'OVER-PROVISIONED — low CPU and memory, reduce task size or count'
                                        ecs_svc_metrics.append({
                                            'cluster': cname, 'service': svc_name,
                                            'desiredCount': svc.get('desiredCount', 0),
                                            'runningCount': svc.get('runningCount', 0),
                                            'avg_cpu_pct': round(avg_cpu, 1), 'max_cpu_pct': round(max_cpu, 1),
                                            'avg_memory_pct': round(avg_mem, 1), 'max_memory_pct': round(max_mem, 1),
                                            'rightsizing_note': note,
                                        })
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    if ecs_svc_metrics:
                        data['ecs_service_metrics'] = ecs_svc_metrics
                        actions.append('cloudwatch:GetMetricStatistics (ECS CPU, memory per service)')
                except Exception as e:
                    logger.warning(f"ECS service metrics error: {e}")
        except Exception as e:
            data['ecs_error'] = str(e)

    # ============================================================
    # S3 Storage Optimization — check for lifecycle policies and Intelligent-Tiering
    # ============================================================
    if any(kw in question_lower for kw in ['s3', 'storage', 'bucket', 'lifecycle', 'tiering', 'glacier', 'archive']) or \
       'Amazon Simple Storage Service' in [s['service'] for s in data.get('cost_by_service', [])[:8]]:
        try:
            s3 = _make_client('s3')
            buckets_resp = s3.list_buckets()
            bucket_analysis = []
            for b in buckets_resp.get('Buckets', [])[:15]:
                bucket_info = {
                    'name': b['Name'],
                    'created': str(b['CreationDate']),
                    'hasLifecyclePolicy': False,
                    'hasIntelligentTiering': False,
                }
                try:
                    lc = s3.get_bucket_lifecycle_configuration(Bucket=b['Name'])
                    bucket_info['hasLifecyclePolicy'] = bool(lc.get('Rules', []))
                    bucket_info['lifecycleRuleCount'] = len(lc.get('Rules', []))
                except ClientError as lce:
                    if lce.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
                        bucket_info['hasLifecyclePolicy'] = False
                    else:
                        bucket_info['lifecycleError'] = str(lce)
                try:
                    it_configs = s3.list_bucket_intelligent_tiering_configurations(Bucket=b['Name'])
                    bucket_info['hasIntelligentTiering'] = bool(it_configs.get('IntelligentTieringConfigurationList', []))
                except Exception:
                    pass
                bucket_analysis.append(bucket_info)

            no_lifecycle = [b for b in bucket_analysis if not b['hasLifecyclePolicy']]
            no_tiering = [b for b in bucket_analysis if not b['hasIntelligentTiering']]
            data['s3_bucket_analysis'] = bucket_analysis
            data['s3_optimization_summary'] = {
                'total_buckets': len(bucket_analysis),
                'without_lifecycle_policy': len(no_lifecycle),
                'without_intelligent_tiering': len(no_tiering),
                'buckets_needing_lifecycle': [b['name'] for b in no_lifecycle[:5]],
                'buckets_needing_tiering': [b['name'] for b in no_tiering[:5]],
            }
            actions.append('s3:ListBuckets + s3:GetBucketLifecycleConfiguration + s3:ListBucketIntelligentTieringConfigurations')
        except Exception as e:
            data['s3_analysis_error'] = str(e)

    # ============================================================
    # AWS Compute Optimizer — rightsizing recommendations
    # ============================================================
    if any(kw in question_lower for kw in ['rightsize', 'rightsizing', 'optimize', 'oversized', 'underutilized',
                                            'compute optimizer', 'instance type', 'downsize']) or \
       any(s in [svc['service'] for svc in data.get('cost_by_service', [])[:5]]
           for s in ['Amazon Elastic Compute Cloud - Compute', 'Amazon Relational Database Service']):
        try:
            co = _make_client('compute-optimizer')
            # EC2 rightsizing recommendations
            ec2_recs = co.get_ec2_instance_recommendations(maxResults=10)
            recommendations = []
            for rec in ec2_recs.get('instanceRecommendations', []):
                current = rec.get('currentInstanceType', '')
                finding = rec.get('finding', '')
                options = rec.get('recommendationOptions', [])
                top_option = options[0] if options else {}
                recommendations.append({
                    'instanceId': rec.get('instanceArn', '').split('/')[-1],
                    'instanceName': rec.get('instanceName', ''),
                    'currentType': current,
                    'finding': finding,
                    'recommendedType': top_option.get('instanceType', ''),
                    'estimatedMonthlySavings': top_option.get('estimatedMonthlySavings', {}).get('value', 0),
                    'savingsCurrency': top_option.get('estimatedMonthlySavings', {}).get('currency', 'USD'),
                    'performanceRisk': top_option.get('performanceRisk', 0),
                })
            if recommendations:
                data['compute_optimizer_ec2'] = recommendations
                data['compute_optimizer_summary'] = {
                    'total_recommendations': len(recommendations),
                    'over_provisioned': sum(1 for r in recommendations if r['finding'] == 'OVER_PROVISIONED'),
                    'under_provisioned': sum(1 for r in recommendations if r['finding'] == 'UNDER_PROVISIONED'),
                    'optimized': sum(1 for r in recommendations if r['finding'] == 'OPTIMIZED'),
                    'total_monthly_savings': round(sum(r['estimatedMonthlySavings'] for r in recommendations), 2),
                }
            actions.append('compute-optimizer:GetEC2InstanceRecommendations')
        except Exception as e:
            data['compute_optimizer_error'] = str(e)

    # ============================================================
    # Cost Anomaly Detection — flag daily spikes > 2x the 7-day average
    # ============================================================
    daily_trend = data.get('daily_cost_trend', [])
    if len(daily_trend) >= 3:
        costs = [d['cost_usd'] for d in daily_trend]
        avg_cost = sum(costs) / len(costs) if costs else 0
        anomalies = []
        for d in daily_trend:
            if avg_cost > 0 and d['cost_usd'] > avg_cost * 2:
                anomalies.append({
                    'date': d['date'],
                    'cost_usd': d['cost_usd'],
                    'avg_usd': round(avg_cost, 4),
                    'spike_pct': round((d['cost_usd'] / avg_cost - 1) * 100, 1),
                })
        if anomalies:
            data['cost_anomalies'] = anomalies
            data['cost_anomaly_count'] = len(anomalies)

    # ============================================================
    # Cost Efficiency Score — based on identified savings opportunities
    # Formula: [1 - (Potential Savings / Total Optimizable Spend)] × 100%
    # ============================================================
    total_spend = sum(s['cost_usd'] for s in data.get('cost_by_service', [])
                      if s.get('service', '') != 'Tax')
    potential_savings = 0.0
    savings_breakdown = {}

    # Unattached EBS volumes
    ebs = data.get('ebs_summary', {})
    if ebs.get('unattached_monthly_cost_usd', 0) > 0:
        potential_savings += ebs['unattached_monthly_cost_usd']
        savings_breakdown['Unattached EBS volumes'] = ebs['unattached_monthly_cost_usd']
    if ebs.get('gp2_to_gp3_savings_usd', 0) > 0:
        potential_savings += ebs['gp2_to_gp3_savings_usd']
        savings_breakdown['gp2 to gp3 migration'] = ebs['gp2_to_gp3_savings_usd']

    # Idle Elastic IPs — from ec2:DescribeAddresses AND from VPC usage breakdown
    eips = data.get('elastic_ips', {})
    idle_eip_savings = eips.get('unattached_monthly_cost_usd', 0)
    # Also check VPC usage breakdown for IdleAddress charges (may not show in DescribeAddresses)
    vpc_breakdown = data.get('amazon_virtual_private_cloud_usage_breakdown', [])
    for u in vpc_breakdown:
        if 'IdleAddress' in u.get('usage_type', '') and u.get('cost_usd', 0) > idle_eip_savings:
            idle_eip_savings = u['cost_usd']
    if idle_eip_savings > 0:
        potential_savings += idle_eip_savings
        savings_breakdown['Idle Elastic IPs'] = round(idle_eip_savings, 2)

    # VPC endpoints (if deleted mid-month, charges will stop)
    vpc_eps = data.get('vpc_endpoints', {})
    vpc_ep_savings = 0
    if vpc_eps.get('total', 0) == 0:
        vpc_breakdown = data.get('amazon_virtual_private_cloud_usage_breakdown', [])
        for u in vpc_breakdown:
            if 'VpcEndpoint' in u.get('usage_type', ''):
                vpc_ep_savings += u['cost_usd']
    if vpc_ep_savings > 0:
        potential_savings += vpc_ep_savings
        savings_breakdown['Deleted VPC endpoints (charges stop next month)'] = round(vpc_ep_savings, 2)

    # KMS customer-managed keys
    kms = data.get('kms_summary', {})
    if kms.get('monthly_cost_usd', 0) > 0:
        potential_savings += kms['monthly_cost_usd']
        savings_breakdown['KMS customer-managed keys'] = kms['monthly_cost_usd']

    # Compute Optimizer savings
    co_summary = data.get('compute_optimizer_summary', {})
    if co_summary.get('total_monthly_savings', 0) > 0:
        potential_savings += co_summary['total_monthly_savings']
        savings_breakdown['Compute Optimizer rightsizing'] = co_summary['total_monthly_savings']

    # Commitment savings estimate (Savings Plans ~30% on top compute/RDS services)
    for svc in data.get('cost_by_service', [])[:5]:
        svc_name = svc.get('service', '')
        svc_cost = svc.get('cost_usd', 0)
        if svc_name == 'Amazon Relational Database Service' and svc_cost > 10:
            sp_saving = round(svc_cost * 0.30, 2)
            potential_savings += sp_saving
            savings_breakdown['RDS Savings Plans / Reserved Instances (~30%)'] = sp_saving
        elif svc_name == 'Amazon Elastic Compute Cloud - Compute' and svc_cost > 10:
            sp_saving = round(svc_cost * 0.30, 2)
            potential_savings += sp_saving
            savings_breakdown['EC2 Savings Plans / Spot Instances (~30-70%)'] = sp_saving

    if total_spend > 0:
        efficiency_score = round((1 - (potential_savings / total_spend)) * 100, 1)
        efficiency_score = max(0, efficiency_score)  # floor at 0

        data['cost_efficiency'] = {
            'score': efficiency_score,
            'total_spend_usd': round(total_spend, 2),
            'potential_savings_usd': round(potential_savings, 2),
            'savings_pct': round((potential_savings / total_spend) * 100, 1),
            'savings_breakdown': savings_breakdown,
            'rating': 'Excellent' if efficiency_score >= 90 else 'Good' if efficiency_score >= 75 else 'Needs Improvement' if efficiency_score >= 50 else 'Critical',
        }

    # Fetch real pricing for top spending services to ground recommendations
    if data.get('cost_by_service'):
        pricing_context = _fetch_pricing_context(data['cost_by_service'], data)
        if pricing_context:
            data['pricing_context'] = pricing_context
            actions.append('pricing:GetProducts (on-demand + RI rates for top services)')

    return data, actions


def _fetch_pricing_context(service_costs, account_data=None):
    """
    Fetch pricing intelligence for top spending services.
    Uses ACTUAL instance types from the account (rds_instances, ec2_instances)
    instead of hardcoded examples. Falls back to common types if no inventory.
    """
    if account_data is None:
        account_data = {}

    # Build actual instance type lists from account inventory
    actual_ec2_types = []
    for inst in account_data.get('ec2_instances', []):
        itype = inst.get('type', '')
        if itype and itype not in actual_ec2_types and inst.get('state') == 'running':
            actual_ec2_types.append(itype)

    actual_rds_instances = account_data.get('rds_instances', [])
    actual_rds_types = []
    for db in actual_rds_instances:
        db_class = db.get('class', '')
        if db_class and db_class not in actual_rds_types:
            actual_rds_types.append(db_class)

    # Detect RDS engine and deployment option from actual instances
    rds_engine = 'MySQL'  # default fallback
    rds_deployment = 'Single-AZ'
    if actual_rds_instances:
        # Use the engine of the most expensive (first) instance
        engine_map = {
            'mysql': 'MySQL', 'postgres': 'PostgreSQL', 'mariadb': 'MariaDB',
            'oracle-ee': 'Oracle', 'oracle-se2': 'Oracle', 'sqlserver-ee': 'SQL Server',
            'sqlserver-se': 'SQL Server', 'sqlserver-ex': 'SQL Server',
            'aurora-mysql': 'Aurora MySQL', 'aurora-postgresql': 'Aurora PostgreSQL',
        }
        raw_engine = actual_rds_instances[0].get('engine', 'mysql').lower()
        rds_engine = engine_map.get(raw_engine, 'MySQL')
        if any(db.get('multiAz') for db in actual_rds_instances):
            rds_deployment = 'Multi-AZ'

    PRICEABLE_SERVICES = {
        'Amazon Elastic Compute Cloud - Compute': {
            'serviceCode': 'AmazonEC2',
            'instance_types': actual_ec2_types[:5] if actual_ec2_types else ['t3.medium', 't3.large', 'm5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
            ],
            'supports_spot': True,
            'supports_savings_plan': True,
            'source': 'actual' if actual_ec2_types else 'example',
        },
        'Amazon Relational Database Service': {
            'serviceCode': 'AmazonRDS',
            'instance_types': actual_rds_types[:5] if actual_rds_types else ['db.t3.medium', 'db.t3.large', 'db.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': rds_engine},
                {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': rds_deployment},
            ],
            'supports_spot': False,
            'supports_savings_plan': True,
            'source': 'actual' if actual_rds_types else 'example',
        },
        'Amazon ElastiCache': {
            'serviceCode': 'AmazonElastiCache',
            'instance_types': ['cache.t3.medium', 'cache.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'cacheEngine', 'Value': 'Redis'},
            ],
            'supports_spot': False,
            'supports_savings_plan': False,
            'source': 'example',
        },
    }

    pricing_client = boto3.client('pricing', region_name='us-east-1')
    results = {}
    top_services = [s['service'] for s in service_costs[:5]]

    # Detect region from usage type prefixes in cost data
    # EU- = eu-west-1, USE1- = us-east-1, USW2- = us-west-2, APN1- = ap-northeast-1, etc.
    region_location_map = {
        'EU': 'EU (Ireland)',
        'EUC1': 'EU (Frankfurt)',
        'EUW2': 'EU (London)',
        'EUW3': 'EU (Paris)',
        'EUS1': 'EU (Stockholm)',
        'USE1': 'US East (N. Virginia)',
        'USE2': 'US East (Ohio)',
        'USW1': 'US West (N. California)',
        'USW2': 'US West (Oregon)',
        'APN1': 'Asia Pacific (Tokyo)',
        'APN2': 'Asia Pacific (Seoul)',
        'APS1': 'Asia Pacific (Singapore)',
        'APS2': 'Asia Pacific (Sydney)',
        'SAE1': 'South America (Sao Paulo)',
        'CAN1': 'Canada (Central)',
    }
    pricing_location = 'US East (N. Virginia)'  # default
    # Check usage breakdowns for region prefix
    for key in ['amazon_virtual_private_cloud_usage_breakdown', 'ec2___other_usage_breakdown']:
        for item in account_data.get(key, []):
            ut = item.get('usage_type', '')
            for prefix, location in region_location_map.items():
                if ut.startswith(prefix + '-') or ut.startswith(prefix + ':'):
                    pricing_location = location
                    break
            if pricing_location != 'US East (N. Virginia)':
                break
        if pricing_location != 'US East (N. Virginia)':
            break

    for svc_name in top_services:
        if svc_name not in PRICEABLE_SERVICES:
            continue
        cfg = PRICEABLE_SERVICES[svc_name]

        pricing_samples = []
        for instance_type in cfg['instance_types'][:5]:
            try:
                filters = cfg['filters'] + [
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': pricing_location},
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                ]
                response = pricing_client.get_products(
                    ServiceCode=cfg['serviceCode'], Filters=filters, MaxResults=1,
                )

                for price_str in response.get('PriceList', []):
                    item = json.loads(price_str)
                    terms = item.get('terms', {})
                    sample = {'instanceType': instance_type}

                    # On-demand price
                    for _, term in terms.get('OnDemand', {}).items():
                        for _, dim in term.get('priceDimensions', {}).items():
                            usd = float(dim.get('pricePerUnit', {}).get('USD', 0))
                            if usd > 0:
                                sample['onDemand_per_hr'] = round(usd, 4)
                                sample['onDemand_per_month'] = round(usd * 730, 2)
                                break
                        break

                    # Savings Plan estimate (~30% discount on compute)
                    od_hr = sample.get('onDemand_per_hr', 0)
                    if od_hr > 0 and cfg.get('supports_savings_plan'):
                        sp_discount = 0.30  # Typical 1yr Compute Savings Plan discount
                        sample['savings_plan_per_hr'] = round(od_hr * (1 - sp_discount), 4)
                        sample['savings_plan_per_month'] = round(od_hr * (1 - sp_discount) * 730, 2)
                        sample['savings_plan_monthly_saving'] = round(od_hr * sp_discount * 730, 2)
                        sample['savings_plan_discount_pct'] = round(sp_discount * 100, 0)

                    # Spot estimate (~60-90% discount, use 70% as conservative)
                    if od_hr > 0 and cfg.get('supports_spot'):
                        spot_discount = 0.70
                        sample['spot_per_hr'] = round(od_hr * (1 - spot_discount), 4)
                        sample['spot_per_month'] = round(od_hr * (1 - spot_discount) * 730, 2)
                        sample['spot_monthly_saving'] = round(od_hr * spot_discount * 730, 2)
                        sample['spot_discount_pct'] = round(spot_discount * 100, 0)

                    # RI price (kept as fallback for rigid workloads only)
                    for _, term in terms.get('Reserved', {}).items():
                        term_attrs = term.get('termAttributes', {})
                        if (term_attrs.get('LeaseContractLength') == '1yr' and
                                term_attrs.get('PurchaseOption') == 'No Upfront'):
                            for _, dim in term.get('priceDimensions', {}).items():
                                usd = float(dim.get('pricePerUnit', {}).get('USD', 0))
                                if usd > 0:
                                    sample['ri_1yr_per_hr'] = round(usd, 4)
                                    sample['ri_1yr_per_month'] = round(usd * 730, 2)
                                    break
                            break

                    # Capacity mix recommendation (for EC2 compute)
                    od_month = sample.get('onDemand_per_month', 0)
                    if od_month > 0 and cfg.get('supports_spot'):
                        sp_month = sample.get('savings_plan_per_month', od_month)
                        spot_month = sample.get('spot_per_month', od_month)
                        # Recommended mix: 30% Savings Plan (baseline) + 70% Spot (fault-tolerant)
                        sample['capacity_mix'] = {
                            'baseline_pct': 30,
                            'baseline_cost_per_instance': round(sp_month, 2),
                            'spot_pct': 70,
                            'spot_cost_per_instance': round(spot_month, 2),
                            'blended_cost_per_instance': round(sp_month * 0.3 + spot_month * 0.7, 2),
                            'vs_ondemand_saving_pct': round((1 - (sp_month * 0.3 + spot_month * 0.7) / od_month) * 100, 1),
                        }

                    if 'onDemand_per_month' in sample:
                        pricing_samples.append(sample)

            except Exception as e:
                logger.warning(f"Pricing fetch failed for {svc_name} {instance_type}: {e}")

        if pricing_samples:
            results[svc_name] = {
                'sample_pricing': pricing_samples,
                'commitment_strategy': 'Compute Savings Plans (recommended)' if cfg.get('supports_savings_plan') else 'Reserved Instances',
                'spot_eligible': cfg.get('supports_spot', False),
                'pricing_source': cfg.get('source', 'example'),
                'note': (
                    'RIGHTSIZE FIRST: Always rightsize via Compute Optimizer before purchasing commitments. '
                    'Buying Savings Plans on oversized instances locks in waste for 1-3 years. '
                    'Recommended workflow: Analyze utilization → Rightsize → Then commit.'
                ),
            }

    return results if results else None


def _ask_bedrock_analyze(question, tips_context, account_data, account_id):
    """Call Bedrock to analyze gathered data and answer the question."""
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    tips_text = ""
    if tips_context:
        tips_text = "\n\nRelevant optimization tips from our knowledge base:\n"
        for tip in tips_context[:5]:
            label = "[Validated] " if tip.get('confidenceTag') == 'high-confidence' else ""
            tips_text += f"- {label}{tip.get('title', '')}: {tip.get('description', '')} (Savings: {tip.get('estimatedSavings', 'N/A')})\n"

    data_text = json.dumps(account_data, indent=2, default=str)
    if len(data_text) > 8000:
        data_text = data_text[:8000] + '\n... (truncated)'

    prompt = f"""You are SlashMyBill AI, an AWS FinOps assistant. Analyze the following real data from AWS account {account_id} and answer the user's question.

RESPONSE FOCUS:
- If the user asks a specific question (e.g. "find unattached EBS volumes", "show my NAT Gateways"), answer ONLY that question with full detail. Do NOT include a full cost breakdown or "Minor costs" section.
- If the user asks a general question (e.g. "how can I reduce costs", "analyze my spending"), provide the full ranked cost analysis.
- Prioritize strategies from Knowledge Base tips that have historically positive user feedback.
- If a user corrects you in the chat, acknowledge the correction and adjust recommendations accordingly.
- When citing a Knowledge Base tip, if the tip has an automatedCheck field, verify the recommendation against the ACTUAL gathered data described in that check. For example, if tip rds-001 says to check RDS CPU and the rds_cpu_metrics show avg_cpu_pct=45%, state "Your RDS instance averages 45% CPU (peak 72%) — it is RIGHT-SIZED, no downsizing needed." Do NOT recommend downsizing when the data shows healthy utilization.
- ALWAYS ground tip recommendations in the actual metrics data. Never recommend rightsizing without showing the actual avg and peak usage numbers from the 30-day CloudWatch data.

IMPORTANT RULES:
- Only reference real AWS services and products. Do NOT invent product names.
- cost_by_service contains ONLY USD amounts. Do NOT infer usage units unless explicitly in the data.
- "EC2 - Other" = NAT Gateway hours/data, EBS volumes, data transfer, Elastic IPs, load balancers. NOT EC2 instances. Do NOT recommend Reserved Instances for this line item.
- "Amazon Virtual Private Cloud" costs = NAT Gateway data processing, VPC endpoints (Interface type cost ~$7.20/month each), Elastic IPs. Use elastic_ips and vpc_endpoints data to identify the exact driver.
- When amazon_virtual_private_cloud_usage_breakdown is present, use it to show the EXACT cost drivers (e.g. NatGateway-Hours, VpcEndpoint-Hours, ElasticIP:IdleAddress, DataTransfer-Out-Bytes). List each usage type with its cost.
- When ec2___other_usage_breakdown is present, use it to show the EXACT cost drivers for EC2-Other (e.g. EBS:VolumeUsage.gp2, NatGateway-Hours, DataTransfer-Out-Bytes). List each usage type with its cost.
- Reserved Instances ONLY apply to "Amazon Elastic Compute Cloud - Compute" and RDS instances, never to EC2-Other or VPC.
- PRICING STRATEGY (CRITICAL — follow this exact sequence):
  1. RIGHTSIZE FIRST: If compute_optimizer_ec2 data is present showing OVER_PROVISIONED instances, ALWAYS recommend rightsizing BEFORE any commitment purchase. Say: "Do NOT buy Savings Plans on oversized instances — rightsize first to avoid locking in waste for 1-3 years."
  2. SAVINGS PLANS over RIs: When recommending commitments, default to Compute Savings Plans (more flexible, adapts to architecture changes). Only mention Reserved Instances as a fallback for rigid, high-commitment scenarios. Never recommend RIs as the primary option.
  3. CAPACITY MIX: For EC2 compute workloads, recommend a capacity mix: 20-40% Savings Plan (baseline stability) + 60-80% Spot Instances (for fault-tolerant, stateless, batch workloads — up to 70-90% savings). Show the blended cost from capacity_mix data.
  4. When pricing_context is present, show: On-Demand cost → Savings Plan cost (30% savings) → Spot cost (70% savings) → Blended capacity mix cost. Use the actual numbers from the data.
  5. For RDS: recommend Savings Plans. Spot is not available for RDS.
  6. CRITICAL: When pricing_context.pricing_source is "actual", the instance types shown are the REAL instances running in this account. Present them as "Your db.r5.large instance" not "For example, a db.t3.medium". When pricing_source is "example", clarify these are example types.
  7. For RDS RI recommendations: ALWAYS use the actual RDS instance classes from rds_instances data. Show the actual engine (PostgreSQL, MySQL, etc.) and deployment option (Single-AZ/Multi-AZ). Never show generic examples when real instance data is available.
  8. For EC2 Savings Plan recommendations: ALWAYS use the actual EC2 instance types from ec2_instances data. Show pricing for the real running instances, not generic examples.
- When unattached_volumes list is present, ALWAYS list each volume by its volumeId, size_gb, type, and monthly_cost_usd. Do NOT just say "6 volumes" — list them individually.
- When elastic_ips.unattached_list is present, list each by allocationId and publicIp.
- When vpc_endpoints.endpoints is present, list each by endpointId, type, and serviceName.
- For EBS: unattached_monthly_cost_usd is the exact saving from deleting unattached volumes. gp2_to_gp3_savings_usd is the saving from migrating gp2 to gp3.
- For Elastic IPs: unattached ones cost $3.65/month each. Quote unattached_monthly_cost_usd as the exact saving.
- For VPC endpoints: interface_monthly_cost_usd is the cost. Recommend reviewing if each endpoint is actively used.
- For KMS: customer_managed_keys × $1/month = monthly_cost_usd. Flag keys that may be unused.
- For RDS: show instance class, engine, Multi-AZ status. If Multi-AZ is enabled for dev/test, suggest disabling it.
- When lambda_metrics is present, use it to show invocation counts, average/max duration, and error counts per function. Identify functions with 0 invocations as candidates for deletion. Identify functions with high avg duration relative to their timeout as optimization candidates.
- CRITICAL: If a Lambda function's max_duration_ms equals its timeout (timeout × 1000), flag it as "hitting timeout limit — investigate for performance issues or increase timeout."
- CRITICAL: If a Lambda function has errors_30d > 0 AND errors_30d equals invocations_30d (100% error rate), flag it as "100% error rate — this function is broken and needs immediate attention."
- When ec2_cpu_metrics is present, use it to show CPU utilization. Instances with avg CPU < 10% are rightsizing candidates. Quote the actual avg/max CPU percentages.
- When rds_cpu_metrics is present, use it for RDS rightsizing analysis. Show each instance's avg/max CPU, avg/max connections, and freeable memory. Instances with avg CPU < 10% and max CPU < 30% are OVER-PROVISIONED — recommend downsizing to a smaller instance class. Instances with avg CPU > 80% may need upsizing or read replicas. Quote the actual metrics. If an RDS instance has low CPU AND high freeable memory, it is clearly oversized — recommend a specific smaller instance class (e.g. db.r5.large → db.r5.medium, db.t3.large → db.t3.medium).
- CRITICAL RIGHTSIZING RULE: When both rds_cpu_metrics AND pricing_context are present, combine them: first show the utilization data proving the instance is over/under-provisioned, then show the pricing for the recommended right-sized instance class. This is the "Analyze → Rightsize → Commit" workflow in action.
- When elb_metrics is present, show each load balancer's total requests over 30 days. ELBs with 0 requests are deletion candidates. ELBs with < 1000 requests may be consolidation candidates. Each ALB costs ~$16/month minimum.
- When nat_gateway_metrics is present, show each NAT Gateway's total bytes processed and active connections. NAT Gateways with very low traffic (< 1MB/30d) are deletion candidates. Each NAT Gateway costs ~$32/month in hourly charges alone plus data processing fees.
- When ebs_iops_metrics is present, show volumes with provisioned IOPS (io1/io2) that have low actual IOPS usage — recommend switching to gp3 which includes 3000 IOPS free. For gp3 volumes, show the actual read/write IOPS from the metrics to help the user understand if the volume size can be reduced. NEVER say "you would need to check the actual usage metrics" — the metrics ARE in the data.
- For EBS gp3 cost questions: gp3 costs $0.08/GB/month. Show the actual volume sizes from ebs_summary. If ebs_iops_metrics shows low IOPS, the volume may be oversized for its workload. Recommend reducing volume size if IOPS are consistently low. Do NOT recommend switching FROM gp3 to gp2 — gp3 is already cheaper than gp2.
- RIGHTSIZING SUMMARY RULE: For every paid service with metrics data, always present a rightsizing verdict: "RIGHT-SIZED" (usage matches capacity), "OVER-PROVISIONED" (low avg + low peak = downsize), or "UNDER-PROVISIONED" (high peak = upsize). Base this on the avg and max (peak) values from the 30-day CloudWatch data.
- COMPUTE OPTIMIZER PRIORITY: When compute_optimizer_ec2 data is present, it is the MOST AUTHORITATIVE source for rightsizing — it uses ML on 14+ days of data. Prefer Compute Optimizer recommendations over static CPU threshold rules. If CO says OPTIMIZED but CPU is low, trust CO.
- GRAVITON RECOMMENDATION: When ec2_cpu_metrics contains graviton_note for x86 instances (t3, m5, c5, r5, m6i, c6i, r6i families), recommend migrating to Graviton equivalents (t4g, m7g, c7g, r7g) for 20-40% better price-performance. This applies AFTER rightsizing.
- MEMORY METRICS: When ec2_cpu_metrics contains avg_memory_pct/max_memory_pct (CloudWatch agent installed), use BOTH CPU and memory for rightsizing. An instance with low CPU but high memory (>70%) is NOT over-provisioned — it is memory-bound. Only recommend downsizing when BOTH CPU and memory are low. When memory_agent_installed=false, warn: "Memory metrics unavailable — install CloudWatch agent for accurate rightsizing. CPU-only analysis may miss memory-bound workloads."
- SCHEDULING RECOMMENDATION: When ec2_cpu_metrics contains environment_tag=dev/test/staging/qa/sandbox AND the instance has low CPU, recommend AWS Instance Scheduler to stop instances during nights and weekends (~65% savings) INSTEAD of just downsizing. Non-production instances running 24/7 are the most common waste pattern.
- ECS/EKS CONTAINER RIGHTSIZING: When ecs_service_metrics is present, show each service's avg/max CPU and memory utilization. Services with avg CPU < 10% AND avg memory < 20% are over-provisioned — recommend reducing task CPU/memory limits or task count. Kubernetes/container waste from over-provisioned resource requests is one of the most common and least monitored sources of cloud waste.
- BUDGETS: When budgets or budget_count is present in the data, ALWAYS check it first. If budget_count == 0: state "No budgets are configured for this account" and recommend setting one up using the actual current monthly spend as the budget limit (e.g., "Your last 30-day spend was $46.31 — suggest setting a monthly budget at $50 with alerts at 80% ($40) and 100% ($50)"). If budgets exist: list them by name, type, limit, and current spend vs limit. Do NOT invent budget amounts — use the actual cost_by_service total. Do NOT give generic AWS console steps — give specific recommended values based on the real spend data.
- S3 STORAGE OPTIMIZATION: When s3_optimization_summary or s3_bucket_analysis is present, list ALL buckets without lifecycle policies with their exact names. The count in the summary MUST match the number of buckets listed — never say "12 out of 15" if you list 16. For each bucket, state whether it has a lifecycle policy. Do NOT give generic AWS console instructions — instead tell the user they can apply lifecycle policies directly from the SlashMyBill Act tab (🪣 S3 Buckets card) with one click. Recommend: (1) S3 Intelligent-Tiering for unknown access patterns, (2) Standard-IA after 30 days + Glacier after 90 days for logs/archives, (3) Abort incomplete multipart uploads after 7 days.
- BUSINESS UNIT / VIRTUAL TAGGING: If the user mentions a team name or business unit (e.g., "Data Science team", "Production", "Dev team"), check if the account data contains cost_allocation with businessUnits. If a matching business unit exists, focus the analysis on the services and accounts mapped to that business unit. Show the business unit's total cost, its percentage of total spend, and the services driving its costs.
- UNIT ECONOMICS: If the account data contains business_metrics, cross-reference cost changes with business volume changes. If costs increased by 20% but business volume increased by 40%, the cost per unit DECREASED — frame this as "efficient scaling" not "cost overrun". Always show: total cost, business volume, and cost per unit when business metrics are available.
- When eks_clusters or ecs_clusters is present, show cluster count, status, and running tasks. Flag clusters with 0 running tasks as candidates for deletion. For ECS, flag clusters with low task counts relative to registered instances as over-provisioned.
- When s3_optimization_summary is present, list ALL buckets without lifecycle policies (exact names, exact count). Recommend enabling S3 Intelligent-Tiering and adding lifecycle policies. Direct the user to the Act tab to apply policies with one click — do NOT give manual AWS console steps.
- When compute_optimizer_ec2 is present, show the rightsizing recommendations: current instance type, recommended type, finding (OVER_PROVISIONED/UNDER_PROVISIONED/OPTIMIZED), and estimated monthly savings. This is the most authoritative source for rightsizing — prefer it over manual CPU analysis.
- The data already contains the resource details. Do NOT tell the customer to "use CloudWatch" or "check Trusted Advisor" or "monitor usage" to find resources that are already listed in the data. The system has ALREADY gathered CloudWatch metrics — use them directly. If ebs_iops_metrics is present, show the actual IOPS numbers. If rds_cpu_metrics is present, show the actual CPU/memory numbers. NEVER say "you would need to check" when the data is already in front of you.
- When usage_breakdown shows charges (e.g. VpcEndpoint-Hours: $11.20) but the resource inventory shows 0 resources (e.g. vpc_endpoints.total: 0), you MUST explain: "These charges are from resources that were active earlier in the billing period but have since been deleted. The charges will stop in the next billing cycle." Do NOT say "no cost savings opportunity" and do NOT suggest reviewing resources that no longer exist.
- IMPORTANT: Only apply the "deleted mid-month" explanation when the SPECIFIC resource inventory for that service shows 0 AND the usage_breakdown shows charges. Do NOT apply it to services like Amazon Registrar, EC2-Other (EBS), or RDS just because April data is low — that's simply because April just started.
- Tax is NEVER actionable and NEVER minor. Exclude Tax from the ranked analysis entirely — do not list it as a numbered item or in the minor costs section. Only mention it as a footnote if the user specifically asks about tax.
- NON-ACTIONABLE SERVICES: The following services must NEVER appear as "savings opportunities" or numbered recommendations because they are not optimizable:
  * Tax — proportional to spend, never actionable
  * Amazon Registrar — annual domain registration fee, not a recurring optimization target
  * AWS Cost Explorer — monitoring tool, costs $0.01 per API request, essential for visibility
  * AWS CloudTrail — audit/compliance tool, should not be disabled for cost savings
  These services should only be mentioned in a cost breakdown if the user asks "what am I spending on?" but NEVER in a "how to save" or "savings opportunities" response.
- ALWAYS rank services strictly by cost_usd descending. A service costing $1.03 MUST appear above a service costing $0.93.
- SAVINGS RECOMMENDATIONS SORTING (CRITICAL): When listing savings opportunities or recommendations, ALWAYS sort them by estimated dollar savings descending (highest savings first). A recommendation saving $147/month MUST appear before one saving $37/month. Never list savings in random order.
- Services costing less than $0.50 MUST be in the "Minor costs" bullet list, not individually numbered. Do NOT give them their own numbered section. This applies to ALL response types including "any savings?" questions.
- For general cost analysis: collapse ALL services under $0.50 into a single "Minor costs" bullet list at the end. Do NOT give each one its own numbered section.
- ALWAYS rank services strictly by cost_usd descending. Never rank a cheaper service above a more expensive one.
- When month_comparison is present, use ONLY that data for the comparison — do NOT use cost_by_service (which is last 30 days). Show a side-by-side comparison with the difference (+ or -) and percentage change for each service. Highlight services with the biggest absolute dollar change.
- When monthly_trend is present, use it to show month-over-month costs. Each key in monthly_trend is a YYYY-MM label with a dict of service→cost. Show a table with months as columns and services as rows. Highlight the trend direction. Do NOT fabricate data for months not in the monthly_trend dict.
- CRITICAL for monthly comparisons: If the last month in the trend is the CURRENT month and its costs are very low compared to previous months, explain "the current month (April) only has 1-2 days of data so far — costs will accumulate throughout the month." Do NOT say services "dropped to $0" or were "terminated."
- For comparison recommendations, be SPECIFIC using the usage_breakdown data: instead of "investigate the VPC spike", say "the VPC increase was caused by VpcEndpoint-Hours ($11.20)". Instead of "review EBS usage", say "EC2-Other increased due to gp3 EBS volumes ($13.01)".
- Domain registration (Amazon Registrar) is typically an annual charge. Do NOT call it a "spike to investigate" — explain it's a standard annual domain registration fee.
- Tax increases are proportional to spend increases. Do NOT recommend "reviewing tax costs" — Tax is never actionable.
- Do NOT use generic percentages. Use real dollar amounts from the data fields.
- Do NOT list IAM permissions unless a specific fetch failed with an error in the data.
- When the user asks about "services I don't need", "waste", "unused", or "unnecessary costs", do NOT list every service. ONLY list resources with concrete evidence of being unused or wasteful:
  * Unattached EBS volumes (unattached_count > 0)
  * Idle Elastic IPs (elastic_ips.unattached > 0)
  * Lambda functions with 0 invocations
  * VPC endpoints/NAT Gateways with charges but 0 current resources (deleted mid-month)
  * KMS customer-managed keys
  * Route 53 hosted zones with very few records
  If no evidence of waste exists for a service, do NOT include it — say "appears actively used."
- CRITICAL: When cost_by_service shows charges for a service (e.g. RDS: $0.63) but the resource inventory is empty (rds_instances: []), do NOT say "there are no RDS instances." Instead explain: "RDS charges of $0.63 exist but no running instances were found in this region — the instances may be in a different region, or these are residual charges from recently deleted resources." Same logic applies to EC2, ElastiCache, etc.
- When the user asks "can I rightsize?" or "any savings?", ONLY list services where you have ACTIONABLE data. Do NOT list services with "no instances found" as rightsizing candidates — that's not helpful. Focus on services where you have actual metrics or concrete waste evidence.
- Do NOT repeat "review X usage to ensure it is necessary" for every service. That is generic filler. Only give specific, actionable advice based on the data.
- When cost_anomalies is present, highlight the anomalous days with their spike percentage. Explain what might have caused the spike and suggest investigating.
- When cost_efficiency is present, ALWAYS show the Cost Efficiency Score prominently at the top of general cost analyses. Format: "Cost Efficiency Score: XX% (Rating)". Then show a savings breakdown listing EACH component that contributes to potential_savings_usd (e.g. "Unattached EBS: $X, Idle EIPs: $Y, Deleted VPC endpoints: $Z, KMS keys: $W"). Do NOT just show the total — break it down so the user understands where the savings come from.
- When the user asks a yes/no efficiency question like "is this account efficient?", lead with the score and savings breakdown, then list ONLY the actionable items. Do NOT list every service with "Potential Savings: N/A" — that's noise. Only show services where savings exist.
- NEVER write "Potential Savings: N/A" — if there are no savings for a service, simply don't mention savings for it.

User question: {question}
{tips_text}

Real account data (costs in USD, gathered via AWS APIs):
{data_text}

For general questions: answer ranked by cost impact (highest first), with exact dollar savings and specific resource IDs. Group only truly minor services (< $0.50) at the end.
For specific questions: answer the question directly with full resource-level detail from the data."""

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'maxTokens': 2000, 'temperature': 0.3},
            }),
        )
        response_body = json.loads(response['body'].read())
        return response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', 'No response from AI.')
    except Exception as e:
        logger.error(f"Bedrock call failed: {e}")
        return f'AI analysis error: {str(e)}. The account data was gathered successfully — please try again.'


def _maybe_save_tip(question, answer, existing_tips):
    """Save a new tip to the knowledge base if the answer contains useful optimization advice."""
    # Only save if we don't already have many tips for this topic
    if len(existing_tips) >= 5:
        return
    # Simple heuristic: if the answer mentions savings, save it
    if 'sav' not in answer.lower() and 'reduc' not in answer.lower() and 'optim' not in answer.lower():
        return

    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    tip_id = f'ai-{hashlib.md5(question.encode()).hexdigest()[:8]}'
    try:
        tips_table.put_item(
            Item={
                'service': 'AI-GENERATED',
                'tipId': tip_id,
                'title': question[:100],
                'description': answer[:500],
                'category': 'ai-generated',
                'estimatedSavings': 'varies',
                'difficulty': 'medium',
                'source': 'ai-agent',
                'createdAt': datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression='attribute_not_exists(tipId)',
        )
    except ClientError:
        pass  # Already exists or error — non-critical


# ============================================================
# Connection status helper
# ============================================================

def _update_connection_status(accounts_table, member_email, account_id, status, last_tested_at):
    """Update connectionStatus and lastTestedAt for an account record."""
    try:
        accounts_table.update_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            UpdateExpression='SET connectionStatus = :s, lastTestedAt = :t',
            ExpressionAttributeValues={':s': status, ':t': last_tested_at},
        )
    except ClientError as e:
        logger.error(f"Failed to update connection status for {account_id}: {e}")


# ============================================================
# OTP email template
# ============================================================

def _build_otp_email(otp_code):
    """Build HTML email body for OTP verification with SlashMyBill branding."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:20px;background:#ffffff;">
  <div style="text-align:center;padding:20px 0;border-bottom:2px solid #0066ff;">
    <img src="https://www.eshkolai.com/SlashMyBill.png" alt="SlashMyBill" style="height:48px;margin-bottom:8px;" />
    <h2 style="color:#0a0e27;margin:0;">SlashMyBill</h2>
    <p style="color:#666;margin:4px 0 0;">AI-Powered AWS Bill Analysis</p>
  </div>
  <div style="padding:30px 0;text-align:center;">
    <p style="color:#333;font-size:16px;">Your verification code is:</p>
    <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#0066ff;
                padding:20px;background:#f0f7ff;border-radius:8px;margin:16px 0;">
      {otp_code}
    </div>
    <p style="color:#666;font-size:14px;">This code is valid for 5 minutes.</p>
    <p style="color:#999;font-size:12px;margin-top:24px;">
      If you did not request this code, please ignore this email.
    </p>
  </div>
  <div style="text-align:center;padding-top:16px;border-top:1px solid #eee;">
    <p style="color:#999;font-size:11px;">eshkolai.com &bull; Cloud and AI Services</p>
  </div>
</body></html>"""


# ============================================================
# Helper functions
# ============================================================

def cors_headers():
    """Return CORS headers for member API responses."""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    }


def create_response(status_code, body):
    """Return an API Gateway v2 response dict with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body),
    }


def create_error_response(status_code, error_type, message, extra=None):
    """Return an error response following the existing Lambda pattern."""
    body = {
        'error': error_type,
        'message': message,
        'code': status_code,
    }
    if extra:
        body.update(extra)
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body),
    }


# ============================================================
# Tag Management Handlers
# ============================================================

def handle_tag_scan(event):
    """Scan resources for missing tags using Resource Groups Tagging API."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        body = {}

    account_ids = body.get('accountIds', [])
    required_tags = body.get('requiredTags', ['Environment', 'Owner', 'CostCenter', 'Application'])

    # Consume tokens
    tier = _get_member_tier(member_email)
    credit_check = _check_and_consume_credits(member_email, tier, SCAN_CREDIT_COST)
    if credit_check:
        return credit_check

    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts_client = boto3.client('sts')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
        )
        accounts = [a for a in result.get('Items', []) if a.get('connectionStatus') == 'connected']
    except ClientError:
        accounts = []

    if account_ids:
        accounts = [a for a in accounts if a['accountId'] in account_ids]

    all_resources = []
    all_tag_keys = set()
    summary = {'total': 0, 'fullyTagged': 0, 'partiallyTagged': 0, 'untagged': 0}

    for acct in accounts[:5]:
        acct_id = acct['accountId']
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillTagScan', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']
            tagging = boto3.client('resourcegroupstaggingapi',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name='us-east-1')

            # Get all tag keys in use
            try:
                tk_resp = tagging.get_tag_keys()
                for k in tk_resp.get('TagKeys', []):
                    if not k.startswith('aws:'):
                        all_tag_keys.add(k)
            except Exception:
                pass

            # Scan resources — focus on costly resource types
            resource_types = [
                'ec2:instance', 'ec2:volume', 'rds:db', 'lambda:function',
                's3', 'elasticloadbalancing:loadbalancer',
                'elasticloadbalancing:loadbalancer/app',
                'elasticloadbalancing:loadbalancer/net',
            ]

            paginator = tagging.get_paginator('get_resources')
            for rt in resource_types:
                try:
                    for page in paginator.paginate(ResourceTypeFilters=[rt], ResourcesPerPage=100):
                        for res in page.get('ResourceTagMappingList', []):
                            arn = res.get('ResourceARN', '')
                            tags = {t['Key']: t['Value'] for t in res.get('Tags', []) if not t['Key'].startswith('aws:')}
                            missing = [k for k in required_tags if k not in tags]

                            summary['total'] += 1
                            if not missing:
                                summary['fullyTagged'] += 1
                            elif len(missing) < len(required_tags):
                                summary['partiallyTagged'] += 1
                            else:
                                summary['untagged'] += 1

                            # Only return resources with missing tags (limit to 200)
                            if missing and len(all_resources) < 200:
                                # Extract friendly name
                                parts = arn.split(':')
                                res_type = rt.split(':')[0].upper() if ':' in rt else rt.upper()
                                res_id = arn.split('/')[-1] if '/' in arn else arn.split(':')[-1]
                                name = tags.get('Name', res_id)

                                all_resources.append({
                                    'arn': arn,
                                    'resourceType': res_type,
                                    'resourceId': res_id,
                                    'name': name,
                                    'account': acct_id,
                                    'existingTags': tags,
                                    'missingTags': missing,
                                })
                except Exception as e:
                    logger.warning(f"Tag scan for {rt} in {acct_id}: {e}")

        except Exception as e:
            logger.warning(f"Tag scan failed for {acct_id}: {e}")

    coverage = round(summary['fullyTagged'] / summary['total'] * 100, 1) if summary['total'] > 0 else 0

    return create_response(200, {
        'resources': all_resources,
        'summary': summary,
        'coverage': coverage,
        'requiredTags': required_tags,
        'discoveredTagKeys': sorted(list(all_tag_keys)),
    })


def handle_tag_apply(event):
    """Apply tags to selected resources in bulk."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    arns = body.get('arns', [])
    tags = body.get('tags', {})  # {key: value}

    if not arns or not tags:
        return create_error_response(400, 'InvalidRequest', 'arns and tags are required')
    if len(arns) > 100:
        return create_error_response(400, 'InvalidRequest', 'Maximum 100 resources per batch')
    if len(tags) > 10:
        return create_error_response(400, 'InvalidRequest', 'Maximum 10 tags per batch')

    # Validate tag keys/values
    for k, v in tags.items():
        if not k or len(k) > 128 or len(str(v)) > 256:
            return create_error_response(400, 'InvalidRequest', f'Invalid tag key/value: {k}')
        if k.startswith('aws:'):
            return create_error_response(400, 'InvalidRequest', 'Cannot set aws: prefixed tags')

    # Consume tokens
    tier = _get_member_tier(member_email)
    credit_check = _check_and_consume_credits(member_email, tier, ACTIVITY_CREDIT_COST)
    if credit_check:
        return credit_check

    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts_client = boto3.client('sts')

    # Group ARNs by account
    arns_by_account = {}
    for arn in arns:
        parts = arn.split(':')
        if len(parts) >= 5:
            acct_id = parts[4]
            arns_by_account.setdefault(acct_id, []).append(arn)

    results = {'tagged': 0, 'failed': 0, 'errors': []}

    for acct_id, acct_arns in arns_by_account.items():
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillTagApply', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']
            tagging = boto3.client('resourcegroupstaggingapi',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name='us-east-1')

            # Tag in batches of 20 (API limit)
            for i in range(0, len(acct_arns), 20):
                batch = acct_arns[i:i+20]
                try:
                    resp = tagging.tag_resources(
                        ResourceARNList=batch,
                        Tags=tags,
                    )
                    failed = resp.get('FailedResourcesMap', {})
                    results['tagged'] += len(batch) - len(failed)
                    results['failed'] += len(failed)
                    for arn, err in failed.items():
                        err_msg = err.get('ErrorMessage', '') or err.get('ErrorCode', '') or str(err)
                        logger.warning(f"Tag failed for {arn}: {err_msg} (full: {err})")
                        results['errors'].append(f"{arn}: {err_msg}")
                except Exception as e:
                    logger.error(f"tag_resources exception for {acct_id}: {e}", exc_info=True)
                    results['failed'] += len(batch)
                    results['errors'].append(f"Batch failed for {acct_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Cannot access {acct_id} for tagging: {e}", exc_info=True)
            results['failed'] += len(acct_arns)
            results['errors'].append(f"Cannot access {acct_id}: {str(e)}")

    logger.info(f"Tag apply by {member_email}: {results['tagged']} tagged, {results['failed']} failed, errors: {results['errors'][:5]}")

    return create_response(200, {
        'message': f"{results['tagged']} resources tagged successfully",
        'tagged': results['tagged'],
        'failed': results['failed'],
        'errors': results['errors'][:10],
    })


# ============================================================
# Scheduler — Recommendation Engine
# ============================================================

def handle_schedule_analyze(event):
    """Analyze environment and generate scheduling recommendations."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    tier = _get_member_tier(member_email)
    credit_check = _check_and_consume_credits(member_email, tier, SCAN_CREDIT_COST)
    if credit_check:
        return credit_check

    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    sts_client = boto3.client('sts')

    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)
    try:
        result = accounts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('memberEmail').eq(member_email)
        )
        accounts = [a for a in result.get('Items', []) if a.get('connectionStatus') == 'connected']
    except ClientError:
        accounts = []

    recommendations = []

    for acct in accounts[:5]:
        acct_id = acct['accountId']
        acct_name = acct.get('accountName', f'Account {acct_id[-4:]}')
        try:
            assume_resp = sts_client.assume_role(
                RoleArn=f'arn:aws:iam::{acct_id}:role/SlashMyBill-{acct_id}',
                RoleSessionName='SlashMyBillScheduler', ExternalId=external_id,
            )
            creds = assume_resp['Credentials']

            ec2 = boto3.client('ec2',
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name='us-east-1')

            # 1. Office Hours — find non-prod instances running 24/7
            try:
                instances = ec2.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
                nonprod = []
                for res in instances.get('Reservations', []):
                    for inst in res.get('Instances', []):
                        tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                        env = (tags.get('Environment', '') or tags.get('Env', '') or tags.get('environment', '')).lower()
                        if any(e in env for e in ['dev', 'test', 'staging', 'qa', 'sandbox']):
                            itype = inst.get('InstanceType', '')
                            nonprod.append({'id': inst['InstanceId'], 'name': tags.get('Name', inst['InstanceId']), 'type': itype, 'env': env})
                if nonprod:
                    # Estimate savings: ~65% of on-demand for 16hrs/day off
                    est_monthly = len(nonprod) * 50  # rough $50/instance/mo savings
                    recommendations.append({
                        'id': f'office-hours-{acct_id}',
                        'type': 'office-hours',
                        'priority': 'high',
                        'title': f'Schedule {len(nonprod)} non-prod instances to stop outside business hours',
                        'reason': f'{len(nonprod)} instances tagged as dev/test/staging are running 24/7 in {acct_name}',
                        'estimatedSavings': est_monthly,
                        'difficulty': 'easy',
                        'accountId': acct_id,
                        'accountName': acct_name,
                        'resources': nonprod[:10],
                        'guide': {
                            'steps': [
                                'Go to AWS Instance Scheduler in the AWS Solutions Library',
                                'Deploy the CloudFormation template in your account',
                                'Create a schedule: Mon-Fri 8am-6pm in your timezone',
                                'Tag your instances with Schedule=office-hours',
                                'The scheduler will auto-stop instances at 6pm and start at 8am',
                            ],
                            'consoleUrl': f'https://console.aws.amazon.com/ec2/home?region=us-east-1#Instances:instanceState=running',
                            'solutionUrl': 'https://aws.amazon.com/solutions/implementations/instance-scheduler-on-aws/',
                            'cliCommand': None,
                        },
                    })
            except Exception as e:
                logger.warning(f"Office hours check failed for {acct_id}: {e}")

            # 2. gp2 → gp3 migration
            try:
                vols = ec2.describe_volumes(Filters=[{'Name': 'volume-type', 'Values': ['gp2']}])
                gp2_vols = vols.get('Volumes', [])
                if gp2_vols:
                    total_gb = sum(v.get('Size', 0) for v in gp2_vols)
                    savings = round(total_gb * 0.02, 2)  # $0.02/GB/mo savings
                    recommendations.append({
                        'id': f'gp2-migration-{acct_id}',
                        'type': 'gp2-migration',
                        'priority': 'medium',
                        'title': f'Migrate {len(gp2_vols)} gp2 volumes to gp3',
                        'reason': f'{len(gp2_vols)} EBS volumes ({total_gb} GB) still using gp2 in {acct_name}. gp3 is 20% cheaper with better performance.',
                        'estimatedSavings': savings,
                        'difficulty': 'easy',
                        'accountId': acct_id,
                        'accountName': acct_name,
                        'resources': [{'id': v['VolumeId'], 'size': v['Size'], 'state': v['State']} for v in gp2_vols[:10]],
                        'guide': {
                            'steps': [
                                'Go to EC2 → Volumes in the AWS Console',
                                'Select a gp2 volume → Actions → Modify Volume',
                                'Change Volume Type to gp3 → Modify',
                                'No downtime required — modification happens live',
                                'Repeat for each gp2 volume, or use the CLI command below',
                            ],
                            'consoleUrl': f'https://console.aws.amazon.com/ec2/home?region=us-east-1#Volumes:volumeType=gp2',
                            'cliCommand': 'aws ec2 modify-volume --volume-id VOL_ID --volume-type gp3',
                        },
                    })
            except Exception as e:
                logger.warning(f"gp2 check failed for {acct_id}: {e}")

            # 3. Old snapshots cleanup
            try:
                snaps = ec2.describe_snapshots(OwnerIds=[acct_id])
                cutoff = datetime.now(timezone.utc) - timedelta(days=180)
                old_snaps = [s for s in snaps.get('Snapshots', []) if s.get('StartTime') and s['StartTime'].replace(tzinfo=None) < cutoff.replace(tzinfo=None)]
                if len(old_snaps) > 3:
                    total_gb = sum(s.get('VolumeSize', 0) for s in old_snaps)
                    savings = round(total_gb * 0.05, 2)
                    recommendations.append({
                        'id': f'snapshot-cleanup-{acct_id}',
                        'type': 'snapshot-cleanup',
                        'priority': 'medium',
                        'title': f'Clean up {len(old_snaps)} snapshots older than 6 months',
                        'reason': f'{len(old_snaps)} EBS snapshots ({total_gb} GB) are over 180 days old in {acct_name}',
                        'estimatedSavings': savings,
                        'difficulty': 'easy',
                        'accountId': acct_id,
                        'accountName': acct_name,
                        'resources': [{'id': s['SnapshotId'], 'size': s.get('VolumeSize', 0), 'age': (datetime.now(timezone.utc) - s['StartTime'].replace(tzinfo=timezone.utc)).days} for s in old_snaps[:10]],
                        'guide': {
                            'steps': [
                                'Go to EC2 → Snapshots in the AWS Console',
                                'Sort by Start Time to find oldest snapshots',
                                'Verify the snapshot is not needed (check if source volume exists)',
                                'Select snapshot → Actions → Delete Snapshot',
                                'Or set up a Data Lifecycle Manager policy for automatic cleanup',
                            ],
                            'consoleUrl': f'https://console.aws.amazon.com/ec2/home?region=us-east-1#Snapshots:',
                            'cliCommand': 'aws ec2 delete-snapshot --snapshot-id SNAP_ID',
                        },
                    })
            except Exception as e:
                logger.warning(f"Snapshot check failed for {acct_id}: {e}")

            # 4. Budget setup recommendation
            try:
                budgets_client = boto3.client('budgets',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'])
                budgets_resp = budgets_client.describe_budgets(AccountId=acct_id)
                if not budgets_resp.get('Budgets'):
                    recommendations.append({
                        'id': f'budget-setup-{acct_id}',
                        'type': 'budget-setup',
                        'priority': 'medium',
                        'title': 'Set up AWS Budgets with cost alerts',
                        'reason': f'No budgets configured in {acct_name}. Budgets alert you before costs exceed thresholds.',
                        'estimatedSavings': 0,
                        'difficulty': 'easy',
                        'accountId': acct_id,
                        'accountName': acct_name,
                        'resources': [],
                        'guide': {
                            'steps': [
                                'Go to AWS Budgets in the Billing Console',
                                'Click "Create budget" → "Cost budget"',
                                'Set monthly budget amount (e.g., your average monthly spend + 10%)',
                                'Add alert thresholds at 50%, 75%, and 100%',
                                'Enter email addresses for notifications',
                                'Click "Create budget"',
                            ],
                            'consoleUrl': 'https://console.aws.amazon.com/billing/home#/budgets/create',
                            'cliCommand': None,
                        },
                    })
            except Exception as e:
                logger.warning(f"Budget check failed for {acct_id}: {e}")

            # 5. Tag compliance recommendation
            try:
                tagging = boto3.client('resourcegroupstaggingapi',
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name='us-east-1')
                tag_resp = tagging.get_resources(ResourcesPerPage=100)
                total = len(tag_resp.get('ResourceTagMappingList', []))
                required = ['Environment', 'Owner', 'CostCenter', 'Application']
                untagged = 0
                for res in tag_resp.get('ResourceTagMappingList', []):
                    tags = {t['Key'] for t in res.get('Tags', [])}
                    if not all(r in tags for r in required):
                        untagged += 1
                coverage = round((1 - untagged / total) * 100, 1) if total > 0 else 100
                if coverage < 80:
                    recommendations.append({
                        'id': f'tag-compliance-{acct_id}',
                        'type': 'tag-compliance',
                        'priority': 'medium',
                        'title': f'Improve tag coverage from {coverage}% to 80%+',
                        'reason': f'{untagged} of {total} resources missing required tags in {acct_name}',
                        'estimatedSavings': 0,
                        'difficulty': 'easy',
                        'accountId': acct_id,
                        'accountName': acct_name,
                        'resources': [],
                        'guide': {
                            'steps': [
                                'Go to the Act → Tag Resources section in SlashMyBill',
                                'Click "Scan for Untagged" to see all resources missing tags',
                                'Select resources and apply tags in bulk',
                                'Or use AWS Tag Editor in the AWS Console for bulk tagging',
                                'Enable AWS Config rule "required-tags" to enforce going forward',
                            ],
                            'consoleUrl': 'https://console.aws.amazon.com/resource-groups/tag-editor',
                            'cliCommand': None,
                        },
                    })
            except Exception as e:
                logger.warning(f"Tag compliance check failed for {acct_id}: {e}")

        except Exception as e:
            logger.warning(f"Scheduler analysis failed for {acct_id}: {e}")

    # Sort by priority then savings
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    recommendations.sort(key=lambda r: (priority_order.get(r['priority'], 2), -r.get('estimatedSavings', 0)))

    # Load existing statuses
    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item', {})
        sched_data = member.get('schedulerData', {})
        completed = {c['id'] for c in sched_data.get('completed', [])}
        dismissed = set(sched_data.get('dismissed', []))
    except Exception:
        completed = set()
        dismissed = set()

    # Mark statuses
    for rec in recommendations:
        if rec['id'] in completed:
            rec['status'] = 'completed'
        elif rec['id'] in dismissed:
            rec['status'] = 'dismissed'
        else:
            rec['status'] = 'pending'

    # Save recommendations
    now = datetime.now(timezone.utc).isoformat()
    try:
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET schedulerData.recommendations = :recs, schedulerData.lastAnalyzedAt = :ts',
            ExpressionAttributeValues={':recs': recommendations, ':ts': now},
        )
    except ClientError:
        # schedulerData might not exist yet
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET schedulerData = :sd',
            ExpressionAttributeValues={':sd': {'recommendations': recommendations, 'lastAnalyzedAt': now, 'completed': [], 'dismissed': []}},
        )

    total_savings = sum(r.get('estimatedSavings', 0) for r in recommendations if r['status'] == 'pending')
    completed_count = len([r for r in recommendations if r['status'] == 'completed'])

    return create_response(200, {
        'recommendations': _decimal_to_native(recommendations),
        'totalSavings': round(total_savings, 2),
        'completedCount': completed_count,
        'totalCount': len(recommendations),
        'analyzedAt': now,
    })


def handle_get_schedules(event):
    """Get saved scheduler recommendations and statuses."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item', {})
        sched_data = _decimal_to_native(member.get('schedulerData', {}))
        return create_response(200, {
            'recommendations': sched_data.get('recommendations', []),
            'completed': sched_data.get('completed', []),
            'dismissed': sched_data.get('dismissed', []),
            'lastAnalyzedAt': sched_data.get('lastAnalyzedAt', ''),
        })
    except Exception as e:
        logger.error(f"Get schedules error: {e}")
        return create_response(200, {'recommendations': [], 'completed': [], 'dismissed': [], 'lastAnalyzedAt': ''})


def handle_update_schedule_status(event):
    """Update a recommendation's status (completed/dismissed/pending)."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    rec_id = body.get('id', '')
    new_status = body.get('status', '')  # completed, dismissed, pending

    if not rec_id or new_status not in ('completed', 'dismissed', 'pending'):
        return create_error_response(400, 'InvalidRequest', 'id and status (completed/dismissed/pending) required')

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    now = datetime.now(timezone.utc).isoformat()

    try:
        member = members_table.get_item(Key={'email': member_email}).get('Item', {})
        sched_data = member.get('schedulerData', {})
        completed = sched_data.get('completed', [])
        dismissed = sched_data.get('dismissed', [])
        recommendations = sched_data.get('recommendations', [])

        # Remove from completed/dismissed first
        completed = [c for c in completed if c.get('id') != rec_id]
        dismissed = [d for d in dismissed if d != rec_id]

        if new_status == 'completed':
            completed.append({'id': rec_id, 'completedAt': now})
        elif new_status == 'dismissed':
            dismissed.append(rec_id)

        # Update status in recommendations
        for rec in recommendations:
            if rec.get('id') == rec_id:
                rec['status'] = new_status

        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET schedulerData.completed = :c, schedulerData.dismissed = :d, schedulerData.recommendations = :r',
            ExpressionAttributeValues={':c': completed, ':d': dismissed, ':r': recommendations},
        )

        return create_response(200, {'message': f'Recommendation {rec_id} marked as {new_status}'})
    except Exception as e:
        logger.error(f"Update schedule status error: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update status')


# ============================================================
# Paddle Payment Handlers
# ============================================================

def handle_add_tokens(event):
    """Add bonus tokens to a member's account (called from frontend after Paddle checkout)."""
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').lower().strip()
        tokens = int(body.get('tokens', 0))
        transaction_id = body.get('paddleTransactionId', '')

        if not email or tokens <= 0:
            return create_error_response(400, 'BadRequest', 'email and tokens required')

        # Validate token amounts (only allow known top-up values)
        if tokens not in (50, 200, 500):
            return create_error_response(400, 'BadRequest', 'Invalid token amount')

        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        now = datetime.now(timezone.utc).isoformat()

        members_table.update_item(
            Key={'email': email},
            UpdateExpression='SET bonusTokens = if_not_exists(bonusTokens, :zero) + :tokens, '
                             'lastTopUpAt = :ts, lastTopUpTransactionId = :txn',
            ExpressionAttributeValues={
                ':tokens': tokens,
                ':zero': 0,
                ':ts': now,
                ':txn': transaction_id,
            },
        )

        # Fetch updated token info
        member = members_table.get_item(Key={'email': email}).get('Item', {})
        tier = member.get('tier', 'free')
        max_tokens = AI_CREDITS.get(tier, 100)
        current_month = datetime.now(timezone.utc).strftime('%Y-%m')
        tokens_used = int(member.get('aiCreditsUsed', 0)) if member.get('aiCreditsMonth', '') == current_month else 0
        bonus = int(member.get('bonusTokens', 0))

        return create_response(200, {
            'message': f'{tokens} tokens added',
            'tokens': {
                'used': tokens_used,
                'total': max_tokens + bonus,
                'remaining': max(0, max_tokens + bonus - tokens_used),
                'bonus': bonus,
            },
        })

    except Exception as e:
        logger.error(f'handle_add_tokens error: {e}', exc_info=True)
        return create_error_response(500, 'InternalError', 'Failed to add tokens')


def handle_update_tier(event):
    """Update a member's tier (called from frontend after Paddle subscription checkout)."""
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').lower().strip()
        tier = body.get('tier', '').lower().strip()
        paddle_sub_id = body.get('paddleSubscriptionId', '')
        paddle_customer_id = body.get('paddleCustomerId', '')

        if not email or tier not in ('free', 'growth', 'scale'):
            return create_error_response(400, 'BadRequest', 'email and valid tier required')

        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        now = datetime.now(timezone.utc).isoformat()

        update_expr = 'SET tier = :tier, updatedAt = :ts'
        expr_values = {':tier': tier, ':ts': now}

        if paddle_sub_id:
            update_expr += ', paddleSubscriptionId = :psid'
            expr_values[':psid'] = paddle_sub_id
        if paddle_customer_id:
            update_expr += ', paddleCustomerId = :pcid'
            expr_values[':pcid'] = paddle_customer_id

        members_table.update_item(
            Key={'email': email},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )

        limit = _get_tier_limit(tier)
        max_tokens = AI_CREDITS.get(tier, 100)

        return create_response(200, {
            'message': f'Tier updated to {tier}',
            'tier': tier,
            'tierLimit': limit,
            'maxTokens': max_tokens,
        })

    except Exception as e:
        logger.error(f'handle_update_tier error: {e}', exc_info=True)
        return create_error_response(500, 'InternalError', 'Failed to update tier')
