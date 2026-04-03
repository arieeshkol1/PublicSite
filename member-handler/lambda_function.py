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
SES_SENDER_EMAIL = os.environ.get('SES_SENDER_EMAIL', 'noreply@eshkolai.com')
PLATFORM_ACCOUNT_ID = os.environ.get('PLATFORM_ACCOUNT_ID', '991105135552')
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-2-lite-v1:0')
BEDROCK_AGENT_ID = os.environ.get('BEDROCK_AGENT_ID', '')
BEDROCK_AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')
FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')

# AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

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
        'DELETE /members/accounts': handle_delete_account,
        'POST /members/accounts/template': handle_generate_template,
        'POST /members/accounts/test': handle_test_connection,
        'POST /members/accounts/execute': handle_execute_command,
        'POST /members/accounts/ai-query': handle_ai_query,
        'POST /members/accounts/ai-feedback': handle_ai_feedback,
        'GET /members/dashboard': handle_get_dashboard,
        'POST /members/dashboard': handle_add_dashboard_item,
        'DELETE /members/dashboard': handle_delete_dashboard_item,
    }

    handler = routes.get(route_key)
    if handler is None:
        return create_error_response(404, 'NotFound', 'Route not found')

    return handler(event)


# ============================================================
# Token validation
# ============================================================

def validate_token(event):
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

    return decoded


# ============================================================
# Registration handler (3-step OTP flow)
# ============================================================

def handle_register(event):
    """Handle member registration with 3-step OTP flow."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    action = body.get('action', '')

    if action == 'send-otp':
        return _register_send_otp(body)
    elif action == 'verify-otp':
        return _register_verify_otp(body)
    elif action == 'create-account':
        return _register_create_account(body)
    else:
        return create_error_response(400, 'InvalidRequest', "Field 'action' is required")


def _register_send_otp(body):
    """Step 1: Validate email, check for existing member, send OTP."""
    email = (body.get('email') or '').strip().lower()
    if not email or not EMAIL_REGEX.match(email):
        return create_error_response(400, 'InvalidEmail', 'Please provide a valid email address')

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    otp_table = dynamodb.Table(OTP_TABLE_NAME)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_epoch = int(now.timestamp())

    # Check if member already exists
    try:
        existing_member = members_table.get_item(Key={'email': email}).get('Item')
        if existing_member:
            return create_error_response(409, 'ConflictError', 'An account with this email already exists')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Rate limiting: check if OTP was sent within last 60 seconds
    try:
        existing_otp = otp_table.get_item(Key={'email': email}).get('Item')
        if existing_otp and existing_otp.get('createdAt'):
            created = datetime.fromisoformat(existing_otp['createdAt'])
            elapsed = (now - created).total_seconds()
            if elapsed < RATE_LIMIT_SECONDS:
                retry_after = int(RATE_LIMIT_SECONDS - elapsed)
                return create_error_response(429, 'RateLimited', 'Please wait before requesting a new code')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Generate 6-digit OTP
    otp_code = str(secrets.randbelow(900000) + 100000)

    # Store in OTP table
    try:
        otp_table.put_item(Item={
            'email': email,
            'otp': otp_code,
            'createdAt': now_iso,
            'ttl': now_epoch + OTP_TTL_SECONDS,
        })
    except ClientError as e:
        logger.error(f"DynamoDB write error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Send email via SES
    try:
        ses_client.send_email(
            Source=f'SlashMyBill <{SES_SENDER_EMAIL}>',
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'Your SlashMyBill verification code', 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {
                        'Data': _build_otp_email(otp_code),
                        'Charset': 'UTF-8',
                    }
                },
            },
        )
    except ClientError as e:
        logger.error(f"SES send error: {e}")
        return create_error_response(500, 'SendFailed', 'Failed to send verification email')

    return create_response(200, {'message': 'OTP sent successfully', 'email': email})


def _register_verify_otp(body):
    """Step 2: Verify OTP code, return short-lived otpToken."""
    email = (body.get('email') or '').strip().lower()
    otp_code = (body.get('otp') or '').strip()

    if not email or not otp_code:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired OTP code')

    otp_table = dynamodb.Table(OTP_TABLE_NAME)

    try:
        result = otp_table.get_item(Key={'email': email})
        item = result.get('Item')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    if not item:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired OTP code')

    # Check expiry
    now_epoch = int(time.time())
    if item.get('ttl') and int(item['ttl']) < now_epoch:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired OTP code')

    # Compare codes
    if item.get('otp') != otp_code:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired OTP code')

    # Delete OTP record on success
    try:
        otp_table.delete_item(Key={'email': email})
    except ClientError:
        pass  # Non-critical

    # Generate short-lived otpToken (10-min expiry)
    now = int(time.time())
    otp_token_payload = {
        'sub': email,
        'purpose': 'registration',
        'iat': now,
        'exp': now + 600,  # 10 minutes
    }
    otp_token = jwt.encode(otp_token_payload, JWT_SECRET, algorithm='HS256')

    return create_response(200, {'verified': True, 'otpToken': otp_token})


def _register_create_account(body):
    """Step 3: Validate otpToken, create member record with hashed password."""
    otp_token = (body.get('otpToken') or '').strip()
    password = body.get('password', '')
    confirm_password = body.get('confirmPassword', '')

    if not otp_token:
        return create_error_response(400, 'InvalidToken', 'Email verification token is invalid or expired')

    # Validate otpToken
    try:
        decoded = jwt.decode(otp_token, JWT_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return create_error_response(400, 'InvalidToken', 'Email verification token is invalid or expired')
    except jwt.InvalidTokenError:
        return create_error_response(400, 'InvalidToken', 'Email verification token is invalid or expired')

    if decoded.get('purpose') != 'registration':
        return create_error_response(400, 'InvalidToken', 'Email verification token is invalid or expired')

    email = decoded.get('sub', '').lower()

    # Validate password
    if len(password) < 8:
        return create_error_response(400, 'InvalidPassword', 'Password must be at least 8 characters')

    if password != confirm_password:
        return create_error_response(400, 'InvalidPassword', 'Passwords do not match')

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)

    # Check if member already exists (race condition guard)
    try:
        existing = members_table.get_item(Key={'email': email}).get('Item')
        if existing:
            return create_error_response(409, 'ConflictError', 'An account with this email already exists')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Hash password with bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Derive displayName from email
    display_name = email.split('@')[0]

    now_iso = datetime.now(timezone.utc).isoformat()

    # Store member record
    try:
        members_table.put_item(Item={
            'email': email,
            'passwordHash': password_hash,
            'displayName': display_name,
            'createdAt': now_iso,
            'lastLoginAt': None,
            'favoriteQueries': [],
        })
    except ClientError as e:
        logger.error(f"DynamoDB write error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    return create_response(201, {'message': 'Registration successful', 'email': email})


# ============================================================
# Login handler
# ============================================================

def handle_login(event):
    """Authenticate member and return JWT token."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = (body.get('email') or '').strip().lower()
    password = body.get('password', '')

    if not email or not password:
        return create_error_response(400, 'InvalidRequest', "Field 'email' is required")

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)

    # Look up member
    try:
        result = members_table.get_item(Key={'email': email})
        member = result.get('Item')
    except ClientError as e:
        logger.error(f"DynamoDB read error: {e}")
        return create_error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    if not member:
        return create_error_response(401, 'AuthError', 'Invalid email or password')

    # Verify password with bcrypt
    try:
        password_valid = bcrypt.checkpw(
            password.encode('utf-8'),
            member['passwordHash'].encode('utf-8'),
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return create_error_response(401, 'AuthError', 'Invalid email or password')

    if not password_valid:
        return create_error_response(401, 'AuthError', 'Invalid email or password')

    # Generate JWT with 24h expiry
    now = int(time.time())
    payload = {
        'sub': email,
        'role': 'member',
        'iat': now,
        'exp': now + 86400,  # 24 hours
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

    # Update lastLoginAt
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        members_table.update_item(
            Key={'email': email},
            UpdateExpression='SET lastLoginAt = :ts',
            ExpressionAttributeValues={':ts': now_iso},
        )
    except ClientError as e:
        logger.warning(f"Failed to update lastLoginAt: {e}")
        # Non-critical — don't fail the login

    display_name = member.get('displayName', email.split('@')[0])

    logger.info(f"Member login successful for: {email}")
    return create_response(200, {'token': token, 'email': email, 'displayName': display_name})


def handle_reset_password(event):
    """Handle password reset with 3-step OTP flow (same pattern as registration)."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    action = body.get('action', '')

    if action == 'send-otp':
        return _reset_send_otp(body)
    elif action == 'verify-otp':
        return _reset_verify_otp(body)
    elif action == 'set-password':
        return _reset_set_password(body)
    else:
        return create_error_response(400, 'InvalidRequest', "Field 'action' is required")


def _reset_send_otp(body):
    """Step 1: Validate email exists, send OTP."""
    email = (body.get('email') or '').strip().lower()
    if not email or not EMAIL_REGEX.match(email):
        return create_error_response(400, 'InvalidEmail', 'Please provide a valid email address')

    members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
    otp_table = dynamodb.Table(OTP_TABLE_NAME)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_epoch = int(now.timestamp())

    # Check if member exists
    try:
        existing = members_table.get_item(Key={'email': email}).get('Item')
        if not existing:
            return create_error_response(404, 'NotFound', 'No account found with this email')
    except ClientError:
        return create_error_response(500, 'ServerError', 'An unexpected error occurred.')

    # Rate limiting
    try:
        existing_otp = otp_table.get_item(Key={'email': email}).get('Item')
        if existing_otp and existing_otp.get('createdAt'):
            created = datetime.fromisoformat(existing_otp['createdAt'])
            if (now - created).total_seconds() < RATE_LIMIT_SECONDS:
                return create_error_response(429, 'RateLimited', 'Please wait before requesting a new code')
    except ClientError:
        pass

    otp_code = str(secrets.randbelow(900000) + 100000)
    try:
        otp_table.put_item(Item={'email': email, 'otp': otp_code, 'createdAt': now_iso, 'ttl': now_epoch + OTP_TTL_SECONDS})
    except ClientError:
        return create_error_response(500, 'ServerError', 'An unexpected error occurred.')

    try:
        ses_client.send_email(
            Source=f'SlashMyBill <{SES_SENDER_EMAIL}>',
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'SlashMyBill Password Reset Code', 'Charset': 'UTF-8'},
                'Body': {'Html': {'Data': _build_otp_email(otp_code), 'Charset': 'UTF-8'}},
            },
        )
    except ClientError:
        return create_error_response(500, 'SendFailed', 'Failed to send verification email')

    return create_response(200, {'message': 'Reset code sent', 'email': email})


def _reset_verify_otp(body):
    """Step 2: Verify OTP, return resetToken."""
    email = (body.get('email') or '').strip().lower()
    otp_code = (body.get('otp') or '').strip()
    if not email or not otp_code:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired code')

    otp_table = dynamodb.Table(OTP_TABLE_NAME)
    try:
        item = otp_table.get_item(Key={'email': email}).get('Item')
    except ClientError:
        return create_error_response(500, 'ServerError', 'An unexpected error occurred.')

    if not item:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired code')
    if item.get('ttl') and int(item['ttl']) < int(time.time()):
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired code')
    if item.get('otp') != otp_code:
        return create_error_response(400, 'InvalidOTP', 'Invalid or expired code')

    try:
        otp_table.delete_item(Key={'email': email})
    except ClientError:
        pass

    now = int(time.time())
    reset_token = jwt.encode({'sub': email, 'purpose': 'reset', 'iat': now, 'exp': now + 600}, JWT_SECRET, algorithm='HS256')
    return create_response(200, {'verified': True, 'resetToken': reset_token})


def _reset_set_password(body):
    """Step 3: Validate resetToken, set new password."""
    reset_token = (body.get('resetToken') or '').strip()
    password = body.get('password', '')
    confirm_password = body.get('confirmPassword', '')

    if not reset_token:
        return create_error_response(400, 'InvalidToken', 'Reset token is invalid or expired')

    try:
        decoded = jwt.decode(reset_token, JWT_SECRET, algorithms=['HS256'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return create_error_response(400, 'InvalidToken', 'Reset token is invalid or expired')

    if decoded.get('purpose') != 'reset':
        return create_error_response(400, 'InvalidToken', 'Reset token is invalid or expired')

    email = decoded.get('sub', '').lower()
    if len(password) < 8:
        return create_error_response(400, 'InvalidPassword', 'Password must be at least 8 characters')
    if password != confirm_password:
        return create_error_response(400, 'InvalidPassword', 'Passwords do not match')

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        members_table.update_item(
            Key={'email': email},
            UpdateExpression='SET passwordHash = :ph',
            ExpressionAttributeValues={':ph': password_hash},
        )
    except ClientError:
        return create_error_response(500, 'ServerError', 'An unexpected error occurred.')

    return create_response(200, {'message': 'Password reset successful. Please log in with your new password.'})


# ============================================================
# Account CRUD handlers
# ============================================================

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

    # Sort by addedAt
    accounts.sort(key=lambda a: a.get('addedAt', ''))

    # Convert Decimal values for JSON serialization
    accounts = _decimal_to_native(accounts)

    return create_response(200, {'accounts': accounts})


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
                                            'iam:DeleteRolePolicy',
                                            'iam:DeleteRole',
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

    # Full success
    _update_connection_status(accounts_table, member_email, account_id, 'connected', now_iso)
    logger.info(f"Connection test successful for account {account_id}, member {member_email}")
    return create_response(200, {'status': 'connected', 'message': 'Connection verified. Cost data is accessible.'})


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
    if not account_id:
        missing.append('accountId')
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
            'accountId': account_id,
            'createdAt': now_iso,
        }
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
                    'createdAt': now_iso,
                },
                ConditionExpression='attribute_not_exists(tipId)',
            )
        except ClientError as e:
            # Duplicate or error — non-critical, feedback was already saved
            if e.response.get('Error', {}).get('Code') != 'ConditionalCheckFailedException':
                logger.warning(f"Failed to save feedback tip: {e}")

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

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    question = (body.get('question') or '').strip()
    account_id = (body.get('accountId') or '').strip()

    if not question:
        return create_error_response(400, 'InvalidRequest', 'Question is required')
    if not re.fullmatch(r'\d{12}', account_id):
        return create_error_response(400, 'InvalidAccountId', 'Account ID must be exactly 12 digits')

    # Generate unique interactionId for feedback tracking
    interaction_id = datetime.now(timezone.utc).isoformat() + '-' + secrets.token_hex(4)

    # Use Bedrock Agent if configured, otherwise fall back to direct API
    if BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID:
        return _invoke_bedrock_agent(question, account_id, member_email, interaction_id)
    else:
        return _invoke_direct_model(question, account_id, member_email, interaction_id)


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

    return create_response(200, {
        'answer': answer,
        'interactionId': interaction_id,
        'commands': executed_actions,
        'results': [],
        'tipFound': bool(tips_context),
        'agentUsed': False,
        'chartData': _build_chart_data(account_data),
    })


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
        # Total cost per month
        month_totals = []
        for m in trend_months:
            total = sum(monthly_trend[m].values())
            month_totals.append(round(total, 2))
        charts.append({
            'id': 'monthly-total-trend',
            'title': f'Monthly Total Cost ({trend_months[0]} to {trend_months[-1]})',
            'type': 'line',
            'labels': trend_months,
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
            # Build per-month data for each service
            month_columns = {}
            for m in trend_months:
                month_columns[m] = [round(monthly_trend.get(m, {}).get(s[0], 0), 2) for s in top_svcs]
            charts.append({
                'id': 'monthly-service-trend',
                'title': f'Top Services by Month ({trend_months[0]} to {trend_months[-1]})',
                'type': 'bar',
                'labels': svc_names,
                'monthColumns': month_columns,
                'months': trend_months,
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

    service_keywords = [
        'ec2', 's3', 'rds', 'lambda', 'cloudfront', 'dynamodb', 'ebs',
        'elb', 'ecs', 'eks', 'redshift', 'elasticache', 'route53',
        'cloudwatch', 'iam', 'vpc', 'nat', 'general', 'cost', 'billing',
    ]
    matched_services = [s for s in service_keywords if s in question_lower]

    tips = []
    try:
        if matched_services:
            for svc in matched_services[:3]:
                result = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(svc.upper())
                )
                tips.extend(result.get('Items', []))
        else:
            result = tips_table.scan(Limit=20)
            tips = result.get('Items', [])
    except ClientError as e:
        logger.warning(f"Tips table query error: {e}")

    # Sort so high-confidence tips appear first (stable sort)
    tips = sorted(tips, key=lambda t: (0 if t.get('confidenceTag') == 'high-confidence' else 1))

    return _decimal_to_native(tips[:10])


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

        # If comparing two specific months, fetch both explicitly
        if is_comparison and len(mentioned_months) >= 2:
            now = datetime.now(timezone.utc)
            # Determine year — assume current year, or previous year if month is in the future
            year_hint = now.year
            # Check if user mentioned a year
            import re as _re
            year_match = _re.search(r'20\d{2}', question)
            if year_match:
                year_hint = int(year_match.group())

            m1 = mentioned_months[0][1]
            m2 = mentioned_months[1][1]

            # Build date ranges for both months
            from calendar import monthrange
            m1_start = f'{year_hint}-{m1:02d}-01'
            m1_end_day = monthrange(year_hint, m1)[1]
            m1_end = f'{year_hint}-{m1:02d}-{m1_end_day:02d}'
            # Use first of next month as end for CE (exclusive end)
            if m1 == 12:
                m1_ce_end = f'{year_hint + 1}-01-01'
            else:
                m1_ce_end = f'{year_hint}-{m1 + 1:02d}-01'

            m2_start = f'{year_hint}-{m2:02d}-01'
            if m2 == 12:
                m2_ce_end = f'{year_hint + 1}-01-01'
            else:
                m2_ce_end = f'{year_hint}-{m2 + 1:02d}-01'

            # Fetch month 1
            m1_data = ce.get_cost_and_usage(
                TimePeriod={'Start': m1_start, 'End': m1_ce_end},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
            m1_costs = []
            for period in m1_data.get('ResultsByTime', []):
                for group in period.get('Groups', []):
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0:
                        m1_costs.append({'service': group['Keys'][0], 'cost_usd': round(cost, 4)})
            m1_costs.sort(key=lambda x: x['cost_usd'], reverse=True)

            # Fetch month 2
            m2_data = ce.get_cost_and_usage(
                TimePeriod={'Start': m2_start, 'End': m2_ce_end},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
            )
            m2_costs = []
            for period in m2_data.get('ResultsByTime', []):
                for group in period.get('Groups', []):
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    if cost > 0:
                        m2_costs.append({'service': group['Keys'][0], 'cost_usd': round(cost, 4)})
            m2_costs.sort(key=lambda x: x['cost_usd'], reverse=True)

            m1_label = f'{mentioned_months[0][0].capitalize()} {year_hint}'
            m2_label = f'{mentioned_months[1][0].capitalize()} {year_hint}'

            data['month_comparison'] = {
                'month1': {'label': m1_label, 'period': f'{m1_start} to {m1_ce_end}', 'costs': m1_costs},
                'month2': {'label': m2_label, 'period': f'{m2_start} to {m2_ce_end}', 'costs': m2_costs},
            }
            actions.append(f'ce:GetCostAndUsage ({m1_label} vs {m2_label})')

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

    # EC2 instances if question mentions EC2, instances, servers
    if any(kw in question_lower for kw in ['ec2', 'instance', 'server', 'compute', 'running']):
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
                    })
            data['ec2_instances'] = instance_list
            actions.append('ec2:DescribeInstances')
        except Exception as e:
            data['ec2_error'] = str(e)

    # NAT Gateways — always fetch when EC2-Other or VPC are top costs (they drive those bills)
    top_service_names = [s['service'] for s in data.get('cost_by_service', [])[:6]]
    if any(s in top_service_names for s in ['EC2 - Other', 'Amazon Virtual Private Cloud']) or \
       any(kw in question_lower for kw in ['nat', 'vpc', 'network', 'data transfer']):
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

    # CloudWatch metrics — fetch when question asks about usage, invocations, utilization, transactions
    if any(kw in question_lower for kw in ['lambda', 'invocation', 'transaction', 'execution', 'utilization',
                                            'cpu', 'usage', 'metric', 'cloudwatch', 'how many', 'how much',
                                            'כמה', 'שימוש']):
        try:
            cw = _make_client('cloudwatch')
            now = datetime.now(timezone.utc)
            start_30d_dt = now - timedelta(days=30)

            # Lambda invocation metrics per function
            if data.get('lambda_functions'):
                lambda_metrics = []
                for func in data['lambda_functions'][:10]:  # Top 10 functions
                    try:
                        inv_resp = cw.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Invocations',
                            Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                            StartTime=start_30d_dt,
                            EndTime=now,
                            Period=2592000,  # 30 days in one datapoint
                            Statistics=['Sum'],
                        )
                        dur_resp = cw.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Duration',
                            Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                            StartTime=start_30d_dt,
                            EndTime=now,
                            Period=2592000,
                            Statistics=['Average', 'Maximum'],
                        )
                        err_resp = cw.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Errors',
                            Dimensions=[{'Name': 'FunctionName', 'Value': func['name']}],
                            StartTime=start_30d_dt,
                            EndTime=now,
                            Period=2592000,
                            Statistics=['Sum'],
                        )
                        invocations = sum(dp['Sum'] for dp in inv_resp.get('Datapoints', []))
                        avg_duration = next((dp['Average'] for dp in dur_resp.get('Datapoints', [])), 0)
                        max_duration = next((dp['Maximum'] for dp in dur_resp.get('Datapoints', [])), 0)
                        errors = sum(dp['Sum'] for dp in err_resp.get('Datapoints', []))
                        lambda_metrics.append({
                            'functionName': func['name'],
                            'invocations_30d': int(invocations),
                            'avg_duration_ms': round(avg_duration, 1),
                            'max_duration_ms': round(max_duration, 1),
                            'errors_30d': int(errors),
                            'memory_mb': func.get('memory', 0),
                        })
                    except Exception:
                        pass
                lambda_metrics.sort(key=lambda x: x['invocations_30d'], reverse=True)
                data['lambda_metrics'] = lambda_metrics
                actions.append('cloudwatch:GetMetricStatistics (Lambda invocations, duration, errors)')

            # EC2 CPU utilization if instances exist
            if data.get('ec2_instances'):
                ec2_metrics = []
                for inst in data['ec2_instances'][:10]:
                    if inst.get('state') != 'running':
                        continue
                    try:
                        cpu_resp = cw.get_metric_statistics(
                            Namespace='AWS/EC2',
                            MetricName='CPUUtilization',
                            Dimensions=[{'Name': 'InstanceId', 'Value': inst['id']}],
                            StartTime=start_30d_dt,
                            EndTime=now,
                            Period=2592000,
                            Statistics=['Average', 'Maximum'],
                        )
                        avg_cpu = next((dp['Average'] for dp in cpu_resp.get('Datapoints', [])), 0)
                        max_cpu = next((dp['Maximum'] for dp in cpu_resp.get('Datapoints', [])), 0)
                        ec2_metrics.append({
                            'instanceId': inst['id'],
                            'type': inst.get('type', ''),
                            'name': inst.get('name', ''),
                            'avg_cpu_pct': round(avg_cpu, 1),
                            'max_cpu_pct': round(max_cpu, 1),
                            'rightsizing_note': 'Consider downsizing' if avg_cpu < 10 else '',
                        })
                    except Exception:
                        pass
                if ec2_metrics:
                    data['ec2_cpu_metrics'] = ec2_metrics
                    actions.append('cloudwatch:GetMetricStatistics (EC2 CPU utilization)')
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
    total_spend = sum(s['cost_usd'] for s in data.get('cost_by_service', []))
    potential_savings = 0.0

    # Unattached EBS volumes
    ebs = data.get('ebs_summary', {})
    potential_savings += ebs.get('unattached_monthly_cost_usd', 0)
    potential_savings += ebs.get('gp2_to_gp3_savings_usd', 0)

    # Idle Elastic IPs
    eips = data.get('elastic_ips', {})
    potential_savings += eips.get('unattached_monthly_cost_usd', 0)

    # VPC endpoints (if deleted mid-month, charges will stop)
    vpc_eps = data.get('vpc_endpoints', {})
    if vpc_eps.get('total', 0) == 0:
        # Charges from deleted endpoints — will stop next month
        vpc_breakdown = data.get('amazon_virtual_private_cloud_usage_breakdown', [])
        for u in vpc_breakdown:
            if 'VpcEndpoint' in u.get('usage_type', ''):
                potential_savings += u['cost_usd']

    # KMS customer-managed keys
    kms = data.get('kms_summary', {})
    potential_savings += kms.get('monthly_cost_usd', 0)

    if total_spend > 0:
        efficiency_score = round((1 - (potential_savings / total_spend)) * 100, 1)
        savings_breakdown = {}
        if ebs.get('unattached_monthly_cost_usd', 0) > 0:
            savings_breakdown['Unattached EBS volumes'] = ebs['unattached_monthly_cost_usd']
        if ebs.get('gp2_to_gp3_savings_usd', 0) > 0:
            savings_breakdown['gp2 to gp3 migration'] = ebs['gp2_to_gp3_savings_usd']
        if eips.get('unattached_monthly_cost_usd', 0) > 0:
            savings_breakdown['Idle Elastic IPs'] = eips['unattached_monthly_cost_usd']
        if kms.get('monthly_cost_usd', 0) > 0:
            savings_breakdown['KMS customer-managed keys'] = kms['monthly_cost_usd']
        # VPC endpoint charges from deleted resources
        vpc_ep_savings = 0
        if vpc_eps.get('total', 0) == 0:
            vpc_breakdown = data.get('amazon_virtual_private_cloud_usage_breakdown', [])
            for u in vpc_breakdown:
                if 'VpcEndpoint' in u.get('usage_type', ''):
                    vpc_ep_savings += u['cost_usd']
        if vpc_ep_savings > 0:
            savings_breakdown['Deleted VPC endpoints (charges stop next month)'] = round(vpc_ep_savings, 2)

        # Compute Optimizer savings
        co_summary = data.get('compute_optimizer_summary', {})
        if co_summary.get('total_monthly_savings', 0) > 0:
            potential_savings += co_summary['total_monthly_savings']
            savings_breakdown['Compute Optimizer rightsizing'] = co_summary['total_monthly_savings']

        # Recalculate score with all savings
        if total_spend > 0:
            efficiency_score = round((1 - (potential_savings / total_spend)) * 100, 1)

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
        pricing_context = _fetch_pricing_context(data['cost_by_service'])
        if pricing_context:
            data['pricing_context'] = pricing_context
            actions.append('pricing:GetProducts (on-demand + RI rates for top services)')

    return data, actions


def _fetch_pricing_context(service_costs):
    """
    Fetch pricing intelligence for top spending services.
    Modern FinOps approach: Savings Plans > RIs, capacity mix, rightsize-first.
    """
    PRICEABLE_SERVICES = {
        'Amazon Elastic Compute Cloud - Compute': {
            'serviceCode': 'AmazonEC2',
            'instance_types': ['t3.medium', 't3.large', 'm5.large', 'm5.xlarge', 'c5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
            ],
            'supports_spot': True,
            'supports_savings_plan': True,
        },
        'Amazon Relational Database Service': {
            'serviceCode': 'AmazonRDS',
            'instance_types': ['db.t3.medium', 'db.t3.large', 'db.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': 'MySQL'},
                {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'},
            ],
            'supports_spot': False,
            'supports_savings_plan': True,
        },
        'Amazon ElastiCache': {
            'serviceCode': 'AmazonElastiCache',
            'instance_types': ['cache.t3.medium', 'cache.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'cacheEngine', 'Value': 'Redis'},
            ],
            'supports_spot': False,
            'supports_savings_plan': False,
        },
    }

    pricing_client = boto3.client('pricing', region_name='us-east-1')
    results = {}
    top_services = [s['service'] for s in service_costs[:5]]

    for svc_name in top_services:
        if svc_name not in PRICEABLE_SERVICES:
            continue
        cfg = PRICEABLE_SERVICES[svc_name]

        pricing_samples = []
        for instance_type in cfg['instance_types'][:3]:
            try:
                filters = cfg['filters'] + [
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'},
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
- When eks_clusters or ecs_clusters is present, show cluster count, status, and running tasks. Flag clusters with 0 running tasks as candidates for deletion. For ECS, flag clusters with low task counts relative to registered instances as over-provisioned.
- When s3_optimization_summary is present, list buckets without lifecycle policies and without Intelligent-Tiering. Recommend enabling S3 Intelligent-Tiering for buckets without it, and adding lifecycle policies to move infrequently accessed data to S3-IA or Glacier.
- When compute_optimizer_ec2 is present, show the rightsizing recommendations: current instance type, recommended type, finding (OVER_PROVISIONED/UNDER_PROVISIONED/OPTIMIZED), and estimated monthly savings. This is the most authoritative source for rightsizing — prefer it over manual CPU analysis.
- The data already contains the resource details. Do NOT tell the customer to "use CloudWatch" or "check Trusted Advisor" to find resources that are already listed in the data.
- When usage_breakdown shows charges (e.g. VpcEndpoint-Hours: $11.20) but the resource inventory shows 0 resources (e.g. vpc_endpoints.total: 0), you MUST explain: "These charges are from resources that were active earlier in the billing period but have since been deleted. The charges will stop in the next billing cycle." Do NOT say "no cost savings opportunity" and do NOT suggest reviewing resources that no longer exist.
- IMPORTANT: Only apply the "deleted mid-month" explanation when the SPECIFIC resource inventory for that service shows 0 AND the usage_breakdown shows charges. Do NOT apply it to services like Amazon Registrar, EC2-Other (EBS), or RDS just because April data is low — that's simply because April just started.
- Tax is NEVER actionable and NEVER minor. Exclude Tax from the ranked analysis entirely — do not list it as a numbered item or in the minor costs section. Only mention it as a footnote if the user specifically asks about tax.
- ALWAYS rank services strictly by cost_usd descending. A service costing $1.03 MUST appear above a service costing $0.93.
- Services costing less than $0.50 MUST be in the "Minor costs" bullet list, not individually numbered. Do NOT give them their own numbered section.
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


def create_error_response(status_code, error_type, message):
    """Return an error response following the existing Lambda pattern."""
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps({
            'error': error_type,
            'message': message,
            'code': status_code,
        }),
    }
