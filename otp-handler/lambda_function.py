"""
OTP Handler Lambda - Send and verify OTP codes for email verification.
Routes: POST /send-otp, POST /verify-otp
"""

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

OTP_TABLE_NAME = os.environ.get('OTP_TABLE_NAME', 'ViewMyBill-OTP')
SES_SENDER_EMAIL = os.environ.get('SES_SENDER_EMAIL', 'noreply@eshkolai.com')
OTP_TTL_SECONDS = 300  # 5 minutes
RATE_LIMIT_SECONDS = 60
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def lambda_handler(event, context):
    route_key = event.get('routeKey', '')
    if route_key == 'POST /send-otp':
        return handle_send_otp(event)
    elif route_key == 'POST /verify-otp':
        return handle_verify_otp(event)
    else:
        return error_response(404, 'NotFound', 'Route not found')


def handle_send_otp(event):
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return error_response(400, 'InvalidRequest', 'Invalid request body')

    email = (body.get('email') or '').strip().lower()
    if not email or not EMAIL_REGEX.match(email):
        return error_response(400, 'InvalidEmail', 'Please provide a valid email address')

    table = dynamodb.Table(OTP_TABLE_NAME)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_epoch = int(now.timestamp())

    # Rate limiting: check if OTP was sent within last 60 seconds
    try:
        existing = table.get_item(Key={'email': email}).get('Item')
        if existing and existing.get('createdAt'):
            created = datetime.fromisoformat(existing['createdAt'])
            elapsed = (now - created).total_seconds()
            if elapsed < RATE_LIMIT_SECONDS:
                retry_after = int(RATE_LIMIT_SECONDS - elapsed)
                return error_response(429, 'RateLimited',
                    'Please wait before requesting a new code', retry_after=retry_after)
    except ClientError as e:
        print(f"DynamoDB read error: {e}")
        return error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Generate OTP
    otp_code = str(secrets.randbelow(900000) + 100000)

    # Store in DynamoDB
    try:
        table.put_item(Item={
            'email': email,
            'otp': otp_code,
            'createdAt': now_iso,
            'ttl': now_epoch + OTP_TTL_SECONDS
        })
    except ClientError as e:
        print(f"DynamoDB write error: {e}")
        return error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    # Send email via SES
    try:
        ses_client.send_email(
            Source=SES_SENDER_EMAIL,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'Your Slash My Bill verification code', 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {
                        'Data': build_email_body(otp_code),
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
    except ClientError as e:
        print(f"SES send error: {e}")
        return error_response(500, 'SendFailed', 'Failed to send verification email. Please try again.')

    return success_response({'message': 'OTP sent successfully', 'email': email})


def handle_verify_otp(event):
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return error_response(400, 'InvalidRequest', 'Invalid request body')

    email = (body.get('email') or '').strip().lower()
    otp_code = (body.get('otp') or '').strip()

    if not email or not otp_code:
        return error_response(400, 'InvalidOTP', 'Invalid OTP code')

    table = dynamodb.Table(OTP_TABLE_NAME)

    try:
        result = table.get_item(Key={'email': email})
        item = result.get('Item')
    except ClientError as e:
        print(f"DynamoDB read error: {e}")
        return error_response(500, 'ServerError', 'An unexpected error occurred. Please try again.')

    if not item:
        return error_response(400, 'ExpiredOTP', 'OTP has expired or was not requested')

    # Check expiry
    now_epoch = int(time.time())
    if item.get('ttl') and int(item['ttl']) < now_epoch:
        return error_response(400, 'ExpiredOTP', 'OTP has expired or was not requested')

    # Compare codes
    if item.get('otp') != otp_code:
        return error_response(400, 'InvalidOTP', 'Invalid OTP code')

    # Delete record on success
    try:
        table.delete_item(Key={'email': email})
    except ClientError:
        pass  # Non-critical

    return success_response({'verified': True, 'message': 'Email verified successfully'})


def build_email_body(otp_code):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:20px;">
  <div style="text-align:center;padding:20px 0;border-bottom:2px solid #0066ff;">
    <h2 style="color:#0a0e27;margin:0;">Eshkol AI</h2>
    <p style="color:#666;margin:4px 0 0;">Cloud and AI Services</p>
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
</body></html>"""


def cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }


def success_response(data):
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps(data)
    }


def error_response(status_code, error_type, message, retry_after=None):
    body = {
        'error': error_type,
        'message': message,
        'code': status_code,
        'retryable': status_code >= 500
    }
    if retry_after is not None:
        body['retryAfter'] = retry_after
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body)
    }
