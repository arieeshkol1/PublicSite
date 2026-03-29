"""
Member Handler Lambda - Registration, login, and account management for the Member Portal.
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
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')

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
    return create_response(200, {'message': 'Account deleted'})


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
                                            'cur:DescribeReportDefinitions',
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
        template_url = f'https://{bucket}.s3.amazonaws.com/{s3_key}'
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
    """Handle natural language questions — uses tips DB + Bedrock + cross-account execution."""
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

    # Step 1: Search tips table for relevant knowledge
    tips_context = _search_tips(question)

    # Step 2: Ask Bedrock to interpret the question and generate CLI commands
    bedrock_response = _ask_bedrock(question, tips_context, account_id)

    # Step 3: If Bedrock suggested CLI commands, execute them on the account
    cli_results = []
    if bedrock_response.get('commands'):
        cli_results = _execute_ai_commands(
            bedrock_response['commands'], account_id, member_email
        )

    # Step 4: Ask Bedrock to summarize the results in natural language
    final_answer = _summarize_results(question, bedrock_response, cli_results)

    # Step 5: Save new tip if Bedrock generated useful knowledge
    if bedrock_response.get('newTip'):
        _save_tip(bedrock_response['newTip'])

    return create_response(200, {
        'answer': final_answer,
        'commands': bedrock_response.get('commands', []),
        'results': cli_results,
        'tipFound': bool(tips_context),
    })


def _search_tips(question):
    """Search ViewMyBill-CostOptimizationTips for relevant tips matching the question."""
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    question_lower = question.lower()

    # Extract service keywords from the question
    service_keywords = [
        'ec2', 's3', 'rds', 'lambda', 'cloudfront', 'dynamodb', 'ebs',
        'elb', 'ecs', 'eks', 'redshift', 'elasticache', 'route53',
        'cloudwatch', 'iam', 'vpc', 'nat', 'general', 'cost', 'billing',
    ]
    matched_services = [s for s in service_keywords if s in question_lower]

    tips = []
    try:
        if matched_services:
            for svc in matched_services[:3]:  # Limit to 3 services
                result = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(svc.upper())
                )
                tips.extend(result.get('Items', []))
        else:
            # Scan for general tips if no service matched
            result = tips_table.scan(Limit=20)
            tips = result.get('Items', [])
    except ClientError as e:
        logger.warning(f"Tips table query error: {e}")

    # Convert Decimal values
    tips = _decimal_to_native(tips)
    return tips[:10]  # Return top 10 relevant tips


def _ask_bedrock(question, tips_context, account_id):
    """Call Bedrock to interpret the question and generate CLI commands."""
    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    tips_text = ""
    if tips_context:
        tips_text = "Relevant knowledge from our tips database:\n"
        for tip in tips_context:
            tips_text += f"- {tip.get('title', '')}: {tip.get('description', '')} (Service: {tip.get('service', '')}, Savings: {tip.get('estimatedSavings', 'N/A')})\n"

    prompt = f"""You are an AWS FinOps AI assistant for SlashMyBill. A member is asking about their AWS account {account_id}.

{tips_text}

User question: {question}

Respond with a JSON object containing:
1. "answer": A brief natural language explanation of what you'll check
2. "commands": An array of AWS CLI commands (read-only) to run on the account to answer the question. Use only describe/list/get operations. Each command should be a string like "aws ec2 describe-instances --region us-east-1". Maximum 3 commands.
3. "newTip": If this question reveals a useful optimization tip not in the existing tips, provide an object with "service" (uppercase), "tipId" (like "ec2-auto-001"), "title", "description", "category", "estimatedSavings", "difficulty" (easy/medium/hard), and "automatedCheck" (the CLI command to verify). Set to null if no new tip.

IMPORTANT: Only suggest read-only commands (describe, list, get). Never suggest create, delete, modify, update, put, terminate, stop, start commands.
Respond ONLY with valid JSON, no markdown formatting."""

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
        ai_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '{}')

        # Parse JSON from the response
        # Strip markdown code fences if present
        ai_text = ai_text.strip()
        if ai_text.startswith('```'):
            ai_text = ai_text.split('\n', 1)[1] if '\n' in ai_text else ai_text[3:]
            if ai_text.endswith('```'):
                ai_text = ai_text[:-3]
            ai_text = ai_text.strip()

        parsed = json.loads(ai_text)
        return parsed
    except Exception as e:
        logger.error(f"Bedrock call failed: {e}")
        return {'answer': 'I encountered an error processing your question. Please try again.', 'commands': [], 'newTip': None}


def _execute_ai_commands(commands, account_id, member_email):
    """Execute AI-suggested CLI commands on the member's account."""
    role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'
    external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()

    # Assume role
    sts_client = boto3.client('sts')
    try:
        assume_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName='SlashMyBillAI',
            ExternalId=external_id,
        )
        credentials = assume_response['Credentials']
    except ClientError as e:
        return [{'command': cmd, 'output': f'ERROR: Cannot assume role - {str(e)}'} for cmd in commands]

    results = []
    for cmd in commands[:3]:  # Max 3 commands
        result = _run_single_command(cmd, credentials)
        results.append(result)

    return results


def _run_single_command(command, credentials):
    """Parse and execute a single AWS CLI command using boto3."""
    parts = command.split()
    if len(parts) < 3 or parts[0] != 'aws':
        return {'command': command, 'output': 'ERROR: Invalid command format'}

    service_name = parts[1]
    action_name = parts[2]

    # Block write operations
    action_lower = action_name.lower().replace('-', '')
    blocked = ['create', 'delete', 'put', 'update', 'modify', 'terminate', 'stop', 'start',
               'reboot', 'run', 'invoke', 'send', 'publish', 'remove', 'attach', 'detach']
    for b in blocked:
        if action_lower.startswith(b):
            return {'command': command, 'output': f'ERROR: Write operation "{action_name}" blocked'}

    # Parse CLI params
    cli_params = {}
    region = 'us-east-1'
    i = 3
    while i < len(parts):
        if parts[i] == '--region' and i + 1 < len(parts):
            region = parts[i + 1]
            i += 2
        elif parts[i].startswith('--'):
            param_name = parts[i][2:]
            pascal = ''.join(w.capitalize() for w in param_name.split('-'))
            if i + 1 < len(parts) and not parts[i + 1].startswith('--'):
                cli_params[pascal] = parts[i + 1]
                i += 2
            else:
                cli_params[pascal] = True
                i += 1
        else:
            i += 1

    method_name = action_name.replace('-', '_')

    # CLI shorthand mappings
    cli_to_boto3 = {'s3': {'ls': 'list_buckets'}, 'lambda': {'ls': 'list_functions'}}
    if service_name in cli_to_boto3 and action_name in cli_to_boto3[service_name]:
        method_name = cli_to_boto3[service_name][action_name]

    service_map = {'costexplorer': 'ce', 'cost-explorer': 'ce', 's3api': 's3', 'logs': 'logs'}
    boto3_service = service_map.get(service_name, service_name)

    try:
        client = boto3.client(
            boto3_service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region,
        )
        if not hasattr(client, method_name):
            return {'command': command, 'output': f'ERROR: Unknown action "{action_name}"'}

        result = getattr(client, method_name)(**cli_params)
        if isinstance(result, dict):
            result.pop('ResponseMetadata', None)
        output = json.dumps(result, indent=2, default=str)
        # Truncate very long outputs
        if len(output) > 5000:
            output = output[:5000] + '\n... (truncated)'
        return {'command': command, 'output': output}
    except Exception as e:
        return {'command': command, 'output': f'ERROR: {str(e)}'}


def _summarize_results(question, bedrock_response, cli_results):
    """Ask Bedrock to summarize the CLI results into a natural language answer."""
    if not cli_results:
        return bedrock_response.get('answer', 'I could not find relevant information.')

    bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

    results_text = ""
    for r in cli_results:
        results_text += f"Command: {r['command']}\nOutput: {r['output']}\n\n"

    prompt = f"""You are an AWS FinOps assistant. The user asked: "{question}"

We ran these commands and got these results:
{results_text}

Please provide a clear, concise natural language summary of the findings. Include specific numbers, costs, and actionable recommendations. Format with bullet points where helpful. Keep it under 500 words."""

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'maxTokens': 1500, 'temperature': 0.3},
            }),
        )
        response_body = json.loads(response['body'].read())
        return response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', bedrock_response.get('answer', ''))
    except Exception as e:
        logger.error(f"Bedrock summarize failed: {e}")
        return bedrock_response.get('answer', 'Analysis complete. See command results below.')


def _save_tip(tip):
    """Save a new tip to the CostOptimizationTips table."""
    if not tip or not tip.get('service') or not tip.get('tipId'):
        return
    tips_table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        item = {
            'service': tip['service'].upper(),
            'tipId': tip['tipId'],
            'title': tip.get('title', ''),
            'description': tip.get('description', ''),
            'category': tip.get('category', 'ai-generated'),
            'estimatedSavings': tip.get('estimatedSavings', 'varies'),
            'difficulty': tip.get('difficulty', 'medium'),
            'automatedCheck': tip.get('automatedCheck', ''),
            'source': 'ai-agent',
            'createdAt': datetime.now(timezone.utc).isoformat(),
        }
        tips_table.put_item(Item=item)
        logger.info(f"Saved new AI-generated tip: {tip['tipId']}")
    except ClientError as e:
        logger.warning(f"Failed to save tip: {e}")


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
