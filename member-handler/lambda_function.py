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
    return create_response(200, {'message': 'Account deleted', 'stackDeleteRequested': stack_delete_requested, 'stackName': stack_name})


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
                'DeletionPolicy': 'Retain',
                'UpdateReplacePolicy': 'Retain',
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
                    'Policies': [
                        {
                            'PolicyName': 'SlashMyBillReadOnly',
                            'PolicyDocument': {
                                'Version': '2012-10-17',
                                'Statement': [
                                    {
                                        'Effect': 'Allow',
                                        'Action': [
                                            'ce:GetCostAndUsage',
                                            'ce:GetCostForecast',
                                            'ce:GetReservationUtilization',
                                            'ce:GetSavingsPlansUtilization',
                                            'budgets:ViewBudget',
                                            'billingconductor:GetBillingData',
                                            'billingconductor:GetBillingGroupCostReport',
                                            'billingconductor:GetCustomLineItemVersions',
                                            'cloudformation:DeleteStack',
                                            'cloudformation:DescribeStacks',
                                            'cloudformation:DescribeStackResources',
                                            'iam:GetRole',
                                            'iam:ListRolePolicies',
                                            'iam:DeleteRolePolicy',
                                            'iam:DeleteRole',
                                            'cur:DescribeReportDefinitions',
                                            'cur:GetClassicReport',
                                            'cur:GetUsageReport',
                                        ],
                                        'Resource': '*'
                                    },
                                    {
                                        'Effect': 'Allow',
                                        'Action': [
                                            'athena:GetDataCatalog',
                                            'athena:GetDatabase',
                                            'athena:GetTableMetadata',
                                            'athena:ListDatabases',
                                            'athena:ListTableMetadata',
                                            'athena:ListWorkGroups',
                                            'athena:StartQueryExecution',
                                            'athena:GetQueryExecution',
                                            'athena:GetQueryResults',
                                            'athena:StopQueryExecution',
                                            'glue:GetDatabase',
                                            'glue:GetDatabases',
                                            'glue:GetTable',
                                            'glue:GetTables',
                                            'glue:GetPartition',
                                            'glue:GetPartitions',
                                        ],
                                        'Resource': '*'
                                    },
                                    {
                                        'Effect': 'Allow',
                                        'Action': [
                                            's3:ListAllMyBuckets',
                                            's3:ListBucket',
                                            's3:GetBucketLocation',
                                            's3:GetObject',
                                        ],
                                        'Resource': '*'
                                    },
                                    {
                                        'Effect': 'Allow',
                                        'Action': [
                                            'cloudwatch:GetMetricData',
                                            'cloudwatch:GetMetricStatistics',
                                            'cloudwatch:ListMetrics',
                                            'ec2:DescribeInstances',
                                            'ec2:DescribeInstanceTypes',
                                            'ec2:DescribeVolumes',
                                            'ec2:DescribeTags',
                                            'ec2:DescribeRegions',
                                            'rds:DescribeDBInstances',
                                            'rds:DescribeDBClusters',
                                            'rds:DescribeDBLogFiles',
                                            'ecs:ListClusters',
                                            'ecs:DescribeClusters',
                                            'ecs:ListServices',
                                            'ecs:DescribeServices',
                                            'ecs:ListTasks',
                                            'ecs:DescribeTasks',
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

    # Build CloudFormation quick-create URL
    cf_console_url = None
    if template_url:
        import urllib.parse
        params = urllib.parse.urlencode({
            'templateURL': template_url,
            'stackName': stack_name,
        })
        cf_console_url = f'https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?{params}'

    return create_response(200, {
        'template': template_yaml,
        'filename': filename,
        'templateUrl': template_url,
        'cfConsoleUrl': cf_console_url,
        'stackName': stack_name,
        'roleName': role_name,
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

    # Use Bedrock Agent if configured, otherwise fall back to direct API
    if BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID:
        return _invoke_bedrock_agent(question, account_id, member_email)
    else:
        return _invoke_direct_model(question, account_id, member_email)


def _invoke_bedrock_agent(question, account_id, member_email):
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
            'commands': ['Bedrock Agent orchestrated the analysis'],
            'results': [],
            'tipFound': False,
            'agentUsed': True,
        })
    except Exception as e:
        logger.error(f"Bedrock Agent invocation failed: {e}")
        # Fall back to direct model
        return _invoke_direct_model(question, account_id, member_email)


def _invoke_direct_model(question, account_id, member_email):
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
        'commands': executed_actions,
        'results': [],
        'tipFound': bool(tips_context),
        'agentUsed': False,
    })


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

            # Also fetch EBS volumes to explain EC2-Other storage costs
            vols = ec2.describe_volumes()
            vol_summary = {'total_gb': 0, 'gp2_count': 0, 'gp2_gb': 0, 'gp3_count': 0, 'io1_count': 0, 'unattached_count': 0}
            for v in vols.get('Volumes', []):
                vol_summary['total_gb'] += v.get('Size', 0)
                vtype = v.get('VolumeType', '')
                if vtype == 'gp2':
                    vol_summary['gp2_count'] += 1
                    vol_summary['gp2_gb'] += v.get('Size', 0)
                elif vtype == 'gp3':
                    vol_summary['gp3_count'] += 1
                elif vtype == 'io1':
                    vol_summary['io1_count'] += 1
                if not v.get('Attachments'):
                    vol_summary['unattached_count'] += 1
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

    # RDS if question mentions RDS, database
    if any(kw in question_lower for kw in ['rds', 'database', 'db']):
        try:
            rds = _make_client('rds')
            dbs = rds.describe_db_instances()
            data['rds_instances'] = [{'id': d['DBInstanceIdentifier'], 'class': d['DBInstanceClass'], 'engine': d['Engine'], 'status': d['DBInstanceStatus']} for d in dbs.get('DBInstances', [])]
            actions.append('rds:DescribeDBInstances')
        except Exception as e:
            data['rds_error'] = str(e)

    # Lambda if question mentions Lambda, functions
    if any(kw in question_lower for kw in ['lambda', 'function', 'serverless']):
        try:
            lam = _make_client('lambda')
            funcs = lam.list_functions()
            data['lambda_functions'] = [{'name': f['FunctionName'], 'runtime': f.get('Runtime', ''), 'memory': f.get('MemorySize', 0), 'timeout': f.get('Timeout', 0)} for f in funcs.get('Functions', [])]
            actions.append('lambda:ListFunctions')
        except Exception as e:
            data['lambda_error'] = str(e)

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

    # Fetch real pricing for top spending services to ground recommendations
    if data.get('cost_by_service'):
        pricing_context = _fetch_pricing_context(data['cost_by_service'])
        if pricing_context:
            data['pricing_context'] = pricing_context
            actions.append('pricing:GetProducts (on-demand + RI rates for top services)')

    return data, actions


def _fetch_pricing_context(service_costs):
    """
    For the top spending services that have RI/Savings Plan alternatives,
    fetch current on-demand and 1-year RI pricing so the AI can quote
    real savings numbers instead of generic percentages.
    """
    # Map CE service names to Pricing API service codes + relevant filters
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
            'label': 'EC2 (Linux, shared tenancy) — RI eligible',
        },
        'Amazon Relational Database Service': {
            'serviceCode': 'AmazonRDS',
            'instance_types': ['db.t3.medium', 'db.t3.large', 'db.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': 'MySQL'},
                {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'},
            ],
            'label': 'RDS (MySQL, Single-AZ)',
        },
        'Amazon ElastiCache': {
            'serviceCode': 'AmazonElastiCache',
            'instance_types': ['cache.t3.medium', 'cache.m5.large'],
            'filters': [
                {'Type': 'TERM_MATCH', 'Field': 'cacheEngine', 'Value': 'Redis'},
            ],
            'label': 'ElastiCache (Redis)',
        },
    }

    pricing_client = boto3.client('pricing', region_name='us-east-1')
    results = {}

    # Only price the top 3 services by spend that we know how to price
    top_services = [s['service'] for s in service_costs[:5]]

    for svc_name in top_services:
        if svc_name not in PRICEABLE_SERVICES:
            continue
        cfg = PRICEABLE_SERVICES[svc_name]
        
        # Fetch pricing for common instance types
        pricing_samples = []
        for instance_type in cfg['instance_types'][:3]:  # Top 3 common types
            try:
                filters = cfg['filters'] + [
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'},
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                ]
                response = pricing_client.get_products(
                    ServiceCode=cfg['serviceCode'],
                    Filters=filters,
                    MaxResults=1,
                )

                for price_str in response.get('PriceList', []):
                    item = json.loads(price_str)
                    terms = item.get('terms', {})
                    
                    sample = {'instanceType': instance_type}

                    # On-demand
                    for _, term in terms.get('OnDemand', {}).items():
                        for _, dim in term.get('priceDimensions', {}).items():
                            usd = float(dim.get('pricePerUnit', {}).get('USD', 0))
                            if usd > 0:
                                sample['onDemand_per_hr_usd'] = round(usd, 4)
                                sample['onDemand_per_month_usd'] = round(usd * 730, 2)
                                break
                        break

                    # Reserved (1yr, No Upfront)
                    for _, term in terms.get('Reserved', {}).items():
                        term_attrs = term.get('termAttributes', {})
                        if (term_attrs.get('LeaseContractLength') == '1yr' and
                                term_attrs.get('PurchaseOption') == 'No Upfront'):
                            for _, dim in term.get('priceDimensions', {}).items():
                                usd = float(dim.get('pricePerUnit', {}).get('USD', 0))
                                if usd > 0:
                                    sample['ri_1yr_no_upfront_per_hr_usd'] = round(usd, 4)
                                    sample['ri_1yr_no_upfront_per_month_usd'] = round(usd * 730, 2)
                                    break
                            break

                    # Calculate savings
                    od = sample.get('onDemand_per_month_usd')
                    ri = sample.get('ri_1yr_no_upfront_per_month_usd')
                    if od and ri and od > 0:
                        sample['monthly_savings_usd'] = round(od - ri, 2)
                        sample['savings_pct'] = round((1 - ri / od) * 100, 1)
                    
                    if 'onDemand_per_month_usd' in sample:
                        pricing_samples.append(sample)
                        
            except Exception as e:
                logger.warning(f"Pricing fetch failed for {svc_name} {instance_type}: {e}")

        if pricing_samples:
            results[svc_name] = {
                'label': cfg['label'],
                'sample_pricing': pricing_samples,
                'note': 'us-east-1 pricing. 1yr No Upfront RI vs on-demand. Multiply monthly savings by number of instances.',
            }

    return results if results else None


def _ask_bedrock_analyze(question, tips_context, account_data, account_id):
    """Call Bedrock to analyze gathered data and answer the question."""
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    tips_text = ""
    if tips_context:
        tips_text = "\n\nRelevant optimization tips from our knowledge base:\n"
        for tip in tips_context[:5]:
            tips_text += f"- {tip.get('title', '')}: {tip.get('description', '')} (Savings: {tip.get('estimatedSavings', 'N/A')})\n"

    data_text = json.dumps(account_data, indent=2, default=str)
    if len(data_text) > 8000:
        data_text = data_text[:8000] + '\n... (truncated)'

    prompt = f"""You are SlashMyBill AI, an AWS FinOps assistant. Analyze the following real data from AWS account {account_id} and answer the user's question.

IMPORTANT RULES:
- Only reference real AWS services and products. Do NOT invent product names.
- cost_by_service contains ONLY USD amounts. Do NOT infer usage units unless explicitly in the data.
- "EC2 - Other" = NAT Gateway hours/data, EBS volumes, data transfer, Elastic IPs, load balancers. NOT EC2 instances. Do NOT recommend Reserved Instances for this line item.
- "Amazon Virtual Private Cloud" = NAT Gateway data processing, VPC endpoints, Elastic IPs. Use nat_gateways data to show count and recommend consolidation. Each NAT Gateway costs ~$32/month in hourly charges plus $0.045/GB processed.
- Reserved Instances ONLY apply to "Amazon Elastic Compute Cloud - Compute", never to EC2-Other or VPC.
- If route53_hosted_zones is present and Route 53 is a significant cost, analyze zone count. Each zone costs $0.50/month. Identify zones with low record counts as deletion candidates.
- If ebs_summary is present: highlight gp2_count (recommend migrating to gp3, 20% cheaper at same performance) and unattached_count (immediate savings — delete unused volumes).
- When pricing_context is present for EC2 Compute, show exact on-demand vs 1yr RI monthly cost and saving per instance type.
- Do NOT use generic percentages. Use real numbers from the data.
- Do NOT list IAM permissions unless a specific fetch failed with an error in the data.

User question: {question}
{tips_text}

Real account data (costs in USD, gathered via AWS APIs):
{data_text}

Answer ranked by cost impact (highest first). For each significant cost:
- What the line item actually contains
- Why it is likely high based on the data (nat_gateways count, ebs_summary, zone count, etc.)
- The specific action to take with estimated dollar saving"""

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
