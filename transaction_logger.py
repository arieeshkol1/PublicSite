"""
Transaction Logger Module — Shared decorator for audit transaction logging.

Captures request/response data, timing, and metadata for every handler invocation
in member-handler and admin-handler. Persists entries to the Audit_Transaction_Log
DynamoDB table without affecting handler behavior.

Usage:
    from transaction_logger import transaction_log

    @transaction_log('member-handler')
    def handle_login(event):
        ...
"""

import functools
import uuid
import time
import json
import copy
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)

# DynamoDB resource (initialized once per Lambda cold start)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
TRANSACTION_LOG_TABLE_NAME = 'Audit_Transaction_Log'

# Maximum payload size in bytes before truncation (10 KB for audit — keeps DynamoDB items small)
MAX_PAYLOAD_BYTES = 10 * 1024

# Fields that must be stripped from request/response payloads at any nesting depth
SENSITIVE_FIELDS = {
    'password', 'token', 'jwt', 'secret', 'authorization',
    'jwt_secret', 'password_hash', 'new_password', 'old_password'
}


def _sanitize(payload):
    """Deep-copy payload and recursively remove keys matching SENSITIVE_FIELDS at any nesting depth."""
    if not isinstance(payload, dict):
        try:
            sanitized = copy.deepcopy(payload)
        except Exception:
            sanitized = payload
        return sanitized

    result = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_FIELDS:
            continue
        if isinstance(value, dict):
            result[key] = _sanitize(value)
        elif isinstance(value, list):
            result[key] = [_sanitize(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    return result


def _extract_user_email(event):
    """Extract email from JWT claims in headers or from request body.

    For Cognito access tokens (which don't contain an 'email' claim),
    calls Cognito GetUser to resolve the sub UUID to an actual email.
    Defaults to 'unknown' only if all resolution methods fail.
    """
    try:
        # Try to get email from JWT token in Authorization header
        headers = event.get('headers') or {}
        auth_header = headers.get('authorization') or headers.get('Authorization') or ''

        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            # Decode without verification — we only need to read claims, not validate
            import jwt as pyjwt
            try:
                claims = pyjwt.decode(token, options={"verify_signature": False})
                # Prefer 'email' over 'sub' — Cognito access tokens have UUID in 'sub'
                email = claims.get('email') or claims.get('cognito:username') or ''

                # If we got a real email (contains @), return it immediately
                if email and '@' in email:
                    return email.lower()

                # For Cognito access tokens: resolve UUID to email via GetUser API
                # Access tokens have 'token_use': 'access' and 'sub' but no 'email'
                token_use = claims.get('token_use', '')
                cognito_sub = claims.get('sub') or claims.get('username') or ''

                if token_use == 'access' and cognito_sub:
                    try:
                        import boto3 as _boto3
                        cognito_client = _boto3.client('cognito-idp', region_name='us-east-1')
                        user_resp = cognito_client.get_user(AccessToken=token)
                        resolved_email = next(
                            (a['Value'] for a in user_resp.get('UserAttributes', []) if a['Name'] == 'email'),
                            ''
                        )
                        if resolved_email and '@' in resolved_email:
                            return resolved_email.lower()
                    except Exception:
                        pass  # GetUser failed — fall through to other methods

                # If still no email, check request body for memberEmail/email fields
                body_str = event.get('body') or ''
                if body_str:
                    try:
                        body = json.loads(body_str) if isinstance(body_str, str) else body_str
                        body_email = body.get('memberEmail') or body.get('email') or body.get('username') or ''
                        if body_email and '@' in body_email:
                            return body_email.lower()
                    except (json.JSONDecodeError, AttributeError):
                        pass

                # Last resort: return the UUID sub (better than 'unknown' for traceability)
                if cognito_sub:
                    return cognito_sub

            except Exception:
                pass

        # Try to get email from the request body (for unauthenticated endpoints like login)
        body_str = event.get('body') or ''
        if body_str:
            try:
                body = json.loads(body_str) if isinstance(body_str, str) else body_str
                email = body.get('email') or body.get('username') or body.get('memberEmail') or ''
                if email:
                    return email.lower() if '@' in email else email
            except (json.JSONDecodeError, AttributeError):
                pass

    except Exception:
        pass

    return 'unknown'


def _extract_function_name(event):
    """Extract function/route name from routeKey field of the event."""
    try:
        route_key = event.get('routeKey', '')
        if route_key:
            return route_key
    except Exception:
        pass
    return 'unknown'


def _truncate_payload(payload):
    """If serialized payload exceeds MAX_PAYLOAD_BYTES, truncate and add metadata."""
    try:
        serialized = json.dumps(payload, default=str)
        byte_size = len(serialized.encode('utf-8'))
        if byte_size > MAX_PAYLOAD_BYTES:
            # Include first portion of data plus metadata about full size
            truncated_str = serialized[:MAX_PAYLOAD_BYTES]
            return {
                '_truncated': True,
                '_original_size_bytes': byte_size,
                '_partial_data': truncated_str
            }
    except (TypeError, ValueError):
        return {'_truncated': True, '_error': 'payload_not_serializable'}
    return payload


def _persist_async(entry):
    """Write entry to DynamoDB Audit_Transaction_Log table.

    Swallows all exceptions and logs failures to CloudWatch so that
    the original handler response is never affected.
    """
    try:
        table = dynamodb.Table(TRANSACTION_LOG_TABLE_NAME)

        # Truncate payloads if they exceed 100KB
        entry['request_payload'] = _truncate_payload(entry.get('request_payload', {}))
        entry['response_payload'] = _truncate_payload(entry.get('response_payload', {}))

        # Convert payload dicts to JSON strings for DynamoDB storage
        if isinstance(entry.get('request_payload'), dict):
            entry['request_payload'] = json.dumps(entry['request_payload'], default=str)
        if isinstance(entry.get('response_payload'), dict):
            entry['response_payload'] = json.dumps(entry['response_payload'], default=str)

        # Remove any empty string values (DynamoDB doesn't allow empty strings in some contexts)
        clean_entry = {k: v for k, v in entry.items() if v != '' and v is not None}
        # Ensure required keys are present even if empty
        if 'user_email' not in clean_entry:
            clean_entry['user_email'] = 'unknown'
        if 'function_name' not in clean_entry:
            clean_entry['function_name'] = 'unknown'

        # Convert any float values to Decimal (DynamoDB doesn't accept Python floats)
        from decimal import Decimal as _Decimal
        for k, v in list(clean_entry.items()):
            if isinstance(v, float):
                clean_entry[k] = _Decimal(str(v))

        table.put_item(Item=clean_entry)
        logger.info(f"Transaction logged: {clean_entry.get('transaction_id', 'N/A')} - {clean_entry.get('function_name', 'N/A')}")
    except Exception as e:
        logger.error(f"Failed to persist transaction log entry: {type(e).__name__}: {e}")
        # Fallback: try to persist a minimal entry without payload fields
        try:
            minimal = {
                'transaction_id': entry.get('transaction_id', str(uuid.uuid4())),
                'start_timestamp': entry.get('start_timestamp', datetime.now(timezone.utc).isoformat()),
                'user_email': entry.get('user_email', 'unknown'),
                'function_name': entry.get('function_name', 'unknown'),
                'duration_ms': int(entry.get('duration_ms', 0)),
                'source_handler': entry.get('source_handler', 'unknown'),
                'status': entry.get('status', 'unknown'),
                'expiry_ttl': int(entry.get('expiry_ttl', 0)),
                'audit_status': 'pending',
                'request_payload': '{"_error": "payload_persist_failed"}',
                'response_payload': '{"_error": "payload_persist_failed"}',
                '_persist_error': f"{type(e).__name__}: {str(e)[:200]}",
            }
            table.put_item(Item=minimal)
            logger.info(f"Minimal transaction logged after error: {minimal['transaction_id']}")
        except Exception as e2:
            logger.error(f"Even minimal persist failed: {type(e2).__name__}: {e2}")


def transaction_log(source_handler):
    """Decorator factory for transaction logging.

    Args:
        source_handler: Identifier string ('member-handler' or 'admin-handler').

    Returns:
        A decorator that wraps handler functions to capture transaction data.
    """
    def decorator(handler_fn):
        @functools.wraps(handler_fn)
        def wrapper(event):
            # Use API Gateway requestId as transaction_id for idempotency.
            # If the same request is processed twice (Lambda retry, client retry),
            # the second PutItem overwrites the first (same PK).
            request_id = (event.get('requestContext') or {}).get('requestId', '')
            transaction_id = request_id if request_id else str(uuid.uuid4())
            start_time = time.time()
            # Use API Gateway request time for deterministic sort key (prevents duplicates
            # when both member-handler and admin-handler process the same request).
            # Format from API GW: "04/Jun/2026:18:15:08 +0000"
            apigw_time = (event.get('requestContext') or {}).get('time', '')
            if apigw_time:
                try:
                    from email.utils import parsedate_to_datetime
                    # API Gateway format: DD/Mon/YYYY:HH:MM:SS +0000
                    # Convert to ISO format for consistent storage
                    parsed = datetime.strptime(apigw_time, '%d/%b/%Y:%H:%M:%S %z')
                    start_iso = parsed.isoformat()
                except (ValueError, TypeError):
                    start_iso = datetime.now(timezone.utc).isoformat()
            else:
                start_iso = datetime.now(timezone.utc).isoformat()

            user_email = _extract_user_email(event)
            function_name = _extract_function_name(event)

            try:
                response = handler_fn(event)
                status = 'success'
            except Exception as e:
                # Build an error response matching the handler pattern
                response = {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'ServerError',
                        'message': str(e),
                        'code': 500,
                    }),
                }
                status = 'error'

            # Extract inference_trace from response if present (set by _invoke_bedrock_agent)
            # Pop it so it's not returned to the caller via API Gateway
            inference_trace = None
            if isinstance(response, dict) and '_inference_trace' in response:
                inference_trace = response.pop('_inference_trace')

            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            entry = {
                'transaction_id': transaction_id,
                'start_timestamp': start_iso,
                'end_timestamp': datetime.now(timezone.utc).isoformat(),
                'user_email': user_email,
                'function_name': function_name,
                'request_payload': _sanitize(event),
                'response_payload': _sanitize(response) if isinstance(response, dict) else response,
                'duration_ms': duration_ms,
                'source_handler': source_handler,
                'status': status,
                'expiry_ttl': int(start_time) + (90 * 24 * 60 * 60),
                'audit_status': 'pending',
            }

            # Add inference_trace to entry only when present (non-None)
            # This keeps the field absent for non-agent paths
            if inference_trace is not None:
                entry['inference_trace'] = inference_trace

            try:
                _persist_async(entry)
            except Exception as persist_err:
                logger.error(f"Transaction log persist raised unexpectedly: {type(persist_err).__name__}: {persist_err}")
            return response

        return wrapper
    return decorator
