"""
Admin Handler Lambda - Authentication and admin API for the Slash My Bill tool.
Routes: POST /admin/login, GET /admin/leads, GET /admin/tips,
        POST /admin/tips, PUT /admin/tips, DELETE /admin/tips,
        GET /admin/feedback, GET /admin/subscribers,
        PUT /admin/subscribers/tier, POST /admin/subscribers/tokens
"""

import json
import os
import time
import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import jwt
import bcrypt

from transaction_logger import transaction_log
from connector_validator import validate_connector_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '')
JWT_SECRET = os.environ.get('JWT_SECRET', '')

# Multiple admin users: JSON env var or hardcoded fallback
# Format: [{"email": "...", "hash": "$2b$..."}]
_EXTRA_ADMINS_JSON = os.environ.get('ADMIN_USERS', '')
ADMIN_USERS = {}
try:
    if _EXTRA_ADMINS_JSON:
        for entry in json.loads(_EXTRA_ADMINS_JSON):
            ADMIN_USERS[entry['email']] = entry['hash']
except (json.JSONDecodeError, KeyError, TypeError):
    pass
# Hardcoded second admin (lavy@aniscoit.com / Anisco2026!)
ADMIN_USERS.setdefault(
    'lavy@aniscoit.com',
    '$2b$12$3QFIJNCA9Y.uZkbPUK1G3OntwY.RAKRhfBdC1lPJM1vB.I4fynF/m'
)
LEADS_TABLE_NAME = os.environ.get('LEADS_TABLE_NAME', 'ViewMyBill-Leads')
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')
TRANSACTION_LOG_TABLE_NAME = os.environ.get('TRANSACTION_LOG_TABLE_NAME', 'Audit_Transaction_Log')
DISCOUNT_CONFIG_TABLE_NAME = os.environ.get('DISCOUNT_CONFIG_TABLE_NAME', 'CustomPlan-DiscountConfig')
CONNECTOR_CONFIG_TABLE_NAME = os.environ.get('CONNECTOR_CONFIG_TABLE_NAME', 'ConnectorConfig')

dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
STORAGE_BUCKET = os.environ.get('STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552')


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


def lambda_handler(event, context):
    """Main entry point — dispatches to handler based on routeKey."""
    route_key = event.get('routeKey', '')
    logger.info(f"Admin API request: {route_key}")

    if route_key == 'OPTIONS /admin/login' or route_key.startswith('OPTIONS '):
        return create_response(200, {'message': 'OK'})

    routes = {
        'POST /admin/login': handle_login,
        'GET /admin/leads': handle_get_leads,
        'PUT /admin/leads': handle_update_lead,
        'DELETE /admin/leads': handle_delete_lead,
        'POST /admin/leads/bulk-delete': handle_bulk_delete_leads,
        'POST /admin/leads/sync-billing': handle_sync_billing,
        'GET /admin/tips': handle_get_tips,
        'POST /admin/tips': handle_create_tip,
        'PUT /admin/tips': handle_update_tip,
        'DELETE /admin/tips': handle_delete_tip,
        'GET /admin/feedback': handle_get_feedback,
        'GET /admin/subscribers': handle_get_subscribers,
        'PUT /admin/subscribers/tier': handle_update_subscriber_tier,
        'POST /admin/subscribers/tokens': handle_add_subscriber_tokens,
        'GET /admin/schedules': handle_get_schedules,
        'GET /admin/tips-sync/status': handle_get_sync_status,
        'GET /admin/tips-sync/logs': handle_get_sync_logs,
        'POST /admin/tips-sync/trigger': handle_trigger_sync,
        'GET /admin/transactions': handle_get_transactions,
        'GET /admin/transactions/detail': handle_get_transaction_detail,
        'GET /admin/custom-plans': handle_get_custom_plans,
        'GET /admin/custom-plans/config': handle_get_discount_config,
        'PUT /admin/custom-plans/config': handle_put_discount_config,
        'GET /admin/connectors': handle_get_connectors,
        'GET /admin/connectors/{provider_key}': handle_get_connector,
        'POST /admin/connectors': handle_create_connector,
        'PUT /admin/connectors/{provider_key}': handle_update_connector,
        'DELETE /admin/connectors/{provider_key}': handle_delete_connector,
    }

    handler = routes.get(route_key)
    if handler is None:
        return create_error_response(404, 'NotFound', 'Route not found')

    return handler(event)


@transaction_log('admin-handler')
def handle_login(event):
    """Authenticate admin user and return JWT token.
    Checks ADMIN_USERS dict (env var + hardcoded), then legacy env var."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    username = body.get('username', '')
    password = body.get('password', '')

    if not username or not password:
        return create_error_response(400, 'InvalidRequest', 'Username and password are required')

    # Look up password hash: check multi-admin dict first, then legacy env var
    password_hash = ADMIN_USERS.get(username)
    if not password_hash:
        if username == ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
            password_hash = ADMIN_PASSWORD_HASH
        else:
            return create_error_response(401, 'AuthError', 'Invalid credentials')

    try:
        password_valid = bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return create_error_response(401, 'AuthError', 'Invalid credentials')

    if not password_valid:
        return create_error_response(401, 'AuthError', 'Invalid credentials')

    # Generate JWT
    now = int(time.time())
    payload = {
        'sub': username,
        'iat': now,
        'exp': now + 86400,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

    logger.info(f"Admin login successful for user: {username}")
    return create_response(200, {'token': token, 'username': username})


def validate_token(event):
    """Extract and validate JWT from Authorization header.

    Returns decoded payload on success.
    Returns an error response dict on failure.
    """
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization') or ''

    if not auth_header.startswith('Bearer '):
        return create_error_response(401, 'AuthError', 'Authentication required')

    token = auth_header[7:]

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return decoded
    except jwt.ExpiredSignatureError:
        return create_error_response(401, 'AuthError', 'Invalid or expired token')
    except jwt.InvalidTokenError:
        return create_error_response(401, 'AuthError', 'Invalid or expired token')


@transaction_log('admin-handler')
def handle_get_leads(event):
    """Return all leads from the Leads table, sorted by timestamp descending."""
    try:
        table = dynamodb.Table(LEADS_TABLE_NAME)
        response = table.scan()
        leads = _decimal_to_native(response.get('Items', []))
        leads.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return create_response(200, {'leads': leads})
    except ClientError as e:
        logger.error(f"DynamoDB error scanning leads: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve leads')


@transaction_log('admin-handler')
def handle_get_tips(event):
    """Return tips from the Tips table, sorted by service then tipId.
    Supports optional pagination via query params: limit, offset, cloud, service.
    Excludes SYSTEM records (SYNC_LOCK, SYNC_METADATA, SYNC_LOG#*).
    Backfills cloud='AWS' for tips missing the field."""
    try:
        params = event.get('queryStringParameters') or {}
        limit = int(params.get('limit', '0'))  # 0 = return all (backward compat)
        offset = int(params.get('offset', '0'))
        cloud_filter = params.get('cloud', '').upper()
        service_filter = params.get('service', '').lower()

        table = dynamodb.Table(TIPS_TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        # Handle DynamoDB pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
        # Filter out SYSTEM records (sync metadata, locks, logs)
        tips = [t for t in items if t.get('service') != 'SYSTEM']
        # Backfill cloud provider for tips that don't have it yet
        for t in tips:
            if not t.get('cloud'):
                t['cloud'] = 'AWS'
        # Apply optional filters
        if cloud_filter:
            tips = [t for t in tips if (t.get('cloud') or '').upper() == cloud_filter]
        if service_filter:
            tips = [t for t in tips if (t.get('service') or '').lower() == service_filter]

        tips = _decimal_to_native(tips)
        tips.sort(key=lambda x: (x.get('service', ''), x.get('tipId', '')))

        total = len(tips)
        # Apply pagination if limit is specified
        if limit > 0:
            tips = tips[offset:offset + limit]

        return create_response(200, {
            'tips': tips,
            'total': total,
            'offset': offset,
            'limit': limit if limit > 0 else total,
        })
    except ClientError as e:
        logger.error(f"DynamoDB error scanning tips: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve tips')


@transaction_log('admin-handler')
def handle_get_feedback(event):
    """Return all feedback from the AgentFeedback table, sorted by createdAt descending."""
    try:
        table = dynamodb.Table(FEEDBACK_TABLE_NAME)
        response = table.scan()
        feedback = _decimal_to_native(response.get('Items', []))
        feedback.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        return create_response(200, {'feedback': feedback})
    except ClientError as e:
        logger.error(f"DynamoDB error scanning feedback: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve feedback')


@transaction_log('admin-handler')
def handle_update_lead(event):
    """Update an existing lead's editable fields."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = body.get('email', '').strip()
    timestamp = body.get('timestamp', '').strip()
    if not email or not timestamp:
        return create_error_response(400, 'InvalidRequest', 'Fields "email" and "timestamp" are required')

    # Only allow updating non-key, non-system fields
    editable = ['name', 'company', 'phone', 'notes']
    updates = {f: body[f].strip() for f in editable if f in body}
    if not updates:
        return create_error_response(400, 'InvalidRequest', 'No editable fields provided')

    expr = 'SET ' + ', '.join(f'#{k} = :{k}' for k in updates)
    names = {f'#{k}': k for k in updates}
    values = {f':{k}': v for k, v in updates.items()}

    try:
        table = dynamodb.Table(LEADS_TABLE_NAME)
        table.update_item(
            Key={'email': email, 'timestamp': timestamp},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression='attribute_exists(email)',
        )
        return create_response(200, {'message': 'Lead updated successfully'})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Lead not found')
        logger.error(f"DynamoDB error updating lead: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update lead')


@transaction_log('admin-handler')
def handle_delete_lead(event):
    """Delete a lead from the Leads table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = body.get('email', '').strip()
    timestamp = body.get('timestamp', '').strip()
    if not email or not timestamp:
        return create_error_response(400, 'InvalidRequest', 'Fields "email" and "timestamp" are required')

    try:
        table = dynamodb.Table(LEADS_TABLE_NAME)
        table.delete_item(
            Key={'email': email, 'timestamp': timestamp},
            ConditionExpression='attribute_exists(email)',
        )
        return create_response(200, {'message': 'Lead deleted successfully'})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Lead not found')
        logger.error(f"DynamoDB error deleting lead: {e}")
        return create_error_response(500, 'ServerError', 'Failed to delete lead')


@transaction_log('admin-handler')
def handle_bulk_delete_leads(event):
    """Delete multiple leads from the Leads table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    items = body.get('items', [])
    if not items or not isinstance(items, list):
        return create_error_response(400, 'InvalidRequest', 'Field "items" must be a non-empty array')

    table = dynamodb.Table(LEADS_TABLE_NAME)
    deleted = 0
    failed = 0
    for item in items:
        email = (item.get('email') or '').strip()
        timestamp = (item.get('timestamp') or '').strip()
        if not email or not timestamp:
            failed += 1
            continue
        try:
            table.delete_item(Key={'email': email, 'timestamp': timestamp})
            deleted += 1
        except ClientError:
            failed += 1

    return create_response(200, {'message': f'{deleted} leads deleted, {failed} failed', 'deleted': deleted, 'failed': failed})


@transaction_log('admin-handler')
def handle_sync_billing(event):
    """Sync billing data from S3 result.json to the lead record in DynamoDB."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = body.get('email', '').strip()
    session_id = body.get('sessionId', '').strip()
    timestamp = body.get('timestamp', '').strip()
    if not email or not session_id or not timestamp:
        return create_error_response(400, 'InvalidRequest', 'email, sessionId, and timestamp are required')

    # Read result.json from S3
    try:
        result_key = f'reports/{session_id}/result.json'
        obj = s3_client.get_object(Bucket=STORAGE_BUCKET, Key=result_key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        return create_error_response(404, 'NotFound', f'Result not found for session {session_id}')

    bill_total = data.get('billTotalCost')
    if not bill_total:
        return create_error_response(404, 'NotFound', 'No billing data in result')

    # Update the lead
    try:
        table = dynamodb.Table(LEADS_TABLE_NAME)
        table.update_item(
            Key={'email': email, 'timestamp': timestamp},
            UpdateExpression='SET billTotalCost = :bt, billCurrency = :bc, monthlySavingsMin = :smin, monthlySavingsMax = :smax, numServices = :ns',
            ExpressionAttributeValues={
                ':bt': Decimal(str(bill_total)),
                ':bc': data.get('billCurrency', 'USD'),
                ':smin': Decimal(str(data.get('monthlySavingsMin', 0))),
                ':smax': Decimal(str(data.get('monthlySavingsMax', 0))),
                ':ns': data.get('numServices', 0),
            },
        )
        return create_response(200, {'message': 'Billing data synced', 'billTotalCost': bill_total, 'monthlySavingsMax': data.get('monthlySavingsMax', 0)})
    except ClientError as e:
        logger.error(f"DynamoDB error syncing billing: {e}")
        return create_error_response(500, 'ServerError', f'Failed to sync: {str(e)}')


def _collect_optional_tip_fields(body):
    """Return a dict of optional tip fields present in the request body.
    drilldownApis may be a list (one API per line from the UI) or a string."""
    out = {}
    str_fields = ['automatedCheck', 'cloud', 'provider', 'level', 'actionType',
                  'actionLabel', 'drilldownInstructions', 'checkConnection']
    for f in str_fields:
        v = body.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = v.strip()
    # drilldownApis: stored as a JSON-array string to match the existing table
    # rows (the enriched dataset uses json.dumps). Accept list or string input.
    da = body.get('drilldownApis')
    items = None
    if isinstance(da, list):
        items = [str(x).strip() for x in da if str(x).strip()]
    elif isinstance(da, str) and da.strip():
        s = da.strip()
        if s[:1] == '[':
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    items = [str(x).strip() for x in parsed if str(x).strip()]
            except (ValueError, TypeError):
                items = None
        if items is None:
            items = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if items:
        out['drilldownApis'] = json.dumps(items, ensure_ascii=False)
    return out


def handle_create_tip(event):
    """Create a new tip in the Tips table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    required_fields = ['service', 'tipId', 'category', 'title', 'description', 'estimatedSavings', 'difficulty']
    for field in required_fields:
        if not body.get(field, '').strip():
            return create_error_response(400, 'InvalidRequest', f'Field "{field}" is required and cannot be empty')

    tip = {field: body[field].strip() for field in required_fields}
    tip.update(_collect_optional_tip_fields(body))

    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        table.put_item(
            Item=tip,
            ConditionExpression='attribute_not_exists(service) AND attribute_not_exists(tipId)'
        )
        return create_response(201, {'tip': tip, 'message': 'Tip created successfully'})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(409, 'ConflictError', 'A tip with this service and tipId already exists')
        logger.error(f"DynamoDB error creating tip: {e}")
        return create_error_response(500, 'ServerError', 'Failed to create tip')


@transaction_log('admin-handler')
def handle_update_tip(event):
    """Update an existing tip in the Tips table.

    Uses update_item (SET) so that fields NOT present in the request (e.g.
    metadata like version, createdAt, contentHash, positiveCount) are
    preserved rather than wiped by a full put_item replace.
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    required_fields = ['service', 'tipId', 'category', 'title', 'description', 'estimatedSavings', 'difficulty']
    for field in required_fields:
        if not body.get(field, '').strip():
            return create_error_response(400, 'InvalidRequest', f'Field "{field}" is required and cannot be empty')

    service = body['service'].strip()
    tip_id = body['tipId'].strip()

    # Build the attribute set: required (minus the keys) + provided optional fields.
    updates = {f: body[f].strip() for f in required_fields if f not in ('service', 'tipId')}
    updates.update(_collect_optional_tip_fields(body))

    names, values, sets = {}, {}, []
    for i, (k, v) in enumerate(updates.items()):
        names[f'#f{i}'] = k
        values[f':v{i}'] = v
        sets.append(f'#f{i} = :v{i}')

    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        table.update_item(
            Key={'service': service, 'tipId': tip_id},
            UpdateExpression='SET ' + ', '.join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        tip = {'service': service, 'tipId': tip_id}
        tip.update(updates)
        return create_response(200, {'tip': tip, 'message': 'Tip updated successfully'})
    except ClientError as e:
        logger.error(f"DynamoDB error updating tip: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update tip')


@transaction_log('admin-handler')
def handle_delete_tip(event):
    """Delete a tip from the Tips table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    service = body.get('service', '').strip()
    tip_id = body.get('tipId', '').strip()

    if not service or not tip_id:
        return create_error_response(400, 'InvalidRequest', 'Fields "service" and "tipId" are required')

    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        table.delete_item(
            Key={'service': service, 'tipId': tip_id},
            ConditionExpression='attribute_exists(service)'
        )
        return create_response(200, {'message': 'Tip deleted successfully'})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Tip not found')
        logger.error(f"DynamoDB error deleting tip: {e}")
        return create_error_response(500, 'ServerError', 'Failed to delete tip')


@transaction_log('admin-handler')
def handle_get_subscribers(event):
    """Return all subscribers from the Members table, sorted by createdAt descending."""
    try:
        table = dynamodb.Table('MemberPortal-Members')
        response = table.scan()
        items = response.get('Items', [])

        fields = [
            'email', 'tier', 'bonusTokens', 'aiCreditsUsed', 'aiCreditsMonth',
            'paddleSubscriptionId', 'paddleCustomerId', 'subscriptionStatus',
            'createdAt', 'lastLoginAt', 'lastTopUpAt', 'updatedAt',
        ]
        subscribers = []
        for item in items:
            subscriber = {f: item.get(f) for f in fields if item.get(f) is not None}
            # Include active schedule count
            user_schedules = item.get('userSchedules', [])
            if user_schedules:
                active_count = sum(1 for s in user_schedules if s.get('status', 'active') == 'active')
                subscriber['scheduleCount'] = active_count
            else:
                subscriber['scheduleCount'] = 0
            subscribers.append(subscriber)

        subscribers = _decimal_to_native(subscribers)
        subscribers.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        return create_response(200, {'subscribers': subscribers})
    except ClientError as e:
        logger.error(f"DynamoDB error scanning subscribers: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve subscribers')


@transaction_log('admin-handler')
def handle_update_subscriber_tier(event):
    """Update a subscriber's tier in the Members table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = (body.get('email') or '').strip()
    tier = (body.get('tier') or '').strip()

    if not email:
        return create_error_response(400, 'InvalidRequest', 'Field "email" is required')
    if tier not in ('free', 'growth', 'scale'):
        return create_error_response(400, 'InvalidRequest', 'Field "tier" must be one of: free, growth, scale')

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    try:
        table = dynamodb.Table('MemberPortal-Members')
        table.update_item(
            Key={'email': email},
            UpdateExpression='SET tier = :tier, updatedAt = :now',
            ExpressionAttributeValues={
                ':tier': tier,
                ':now': now,
            },
            ConditionExpression='attribute_exists(email)',
        )
        logger.info(f"Admin updated tier for {email} to {tier}")
        return create_response(200, {'message': 'Subscriber tier updated', 'email': email, 'tier': tier})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Subscriber not found')
        logger.error(f"DynamoDB error updating subscriber tier: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update subscriber tier')


@transaction_log('admin-handler')
def handle_add_subscriber_tokens(event):
    """Atomically add bonus tokens to a subscriber in the Members table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    email = (body.get('email') or '').strip()
    tokens = body.get('tokens')
    reason = (body.get('reason') or '').strip()

    if not email:
        return create_error_response(400, 'InvalidRequest', 'Field "email" is required')
    if not isinstance(tokens, int) or tokens <= 0:
        return create_error_response(400, 'InvalidRequest', 'Field "tokens" must be a positive integer')

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    try:
        table = dynamodb.Table('MemberPortal-Members')
        update_expr = 'SET bonusTokens = if_not_exists(bonusTokens, :zero) + :tokens, lastAdminTopUpAt = :now, updatedAt = :now'
        expr_values = {
            ':zero': 0,
            ':tokens': tokens,
            ':now': now,
        }

        if reason:
            update_expr += ', lastAdminTopUpReason = :reason'
            expr_values[':reason'] = reason

        result = table.update_item(
            Key={'email': email},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ConditionExpression='attribute_exists(email)',
            ReturnValues='UPDATED_NEW',
        )
        new_bonus = _decimal_to_native(result['Attributes'].get('bonusTokens', 0))
        logger.info(f"Admin added {tokens} bonus tokens to {email} (reason: {reason or 'none'})")
        return create_response(200, {'message': 'Tokens added successfully', 'email': email, 'bonusTokens': new_bonus})
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return create_error_response(404, 'NotFound', 'Subscriber not found')
        logger.error(f"DynamoDB error adding tokens: {e}")
        return create_error_response(500, 'ServerError', 'Failed to add tokens')


@transaction_log('admin-handler')
def handle_get_schedules(event):
    """Return all schedules across all members with aggregated stats."""
    try:
        from datetime import datetime, timedelta, timezone
        table = dynamodb.Table('MemberPortal-Members')
        response = table.scan()
        items = response.get('Items', [])

        schedules = []
        total = 0
        active = 0
        paused = 0
        executions_24h = 0
        failures_24h = 0
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        cutoff_iso = cutoff.isoformat()

        for item in items:
            user_schedules = item.get('userSchedules', [])
            if not user_schedules:
                continue
            email = item.get('email', '')
            for sched in user_schedules:
                total += 1
                status = sched.get('status', 'active')
                if status == 'active':
                    active += 1
                elif status == 'paused':
                    paused += 1

                last_exec = None
                history = sched.get('executionHistory', [])
                if history:
                    last_exec = history[-1] if isinstance(history, list) else None
                    for ex in history:
                        ts = ex.get('timestamp', '')
                        if ts >= cutoff_iso:
                            executions_24h += 1
                            if ex.get('status') == 'failure':
                                failures_24h += 1

                schedules.append({
                    'memberEmail': email,
                    'scheduleId': sched.get('id', ''),
                    'name': sched.get('name', ''),
                    'type': sched.get('type', ''),
                    'status': status,
                    'accountId': sched.get('config', {}).get('accountId', ''),
                    'createdAt': sched.get('createdAt', ''),
                    'lastExecution': _decimal_to_native(last_exec) if last_exec else None,
                })

        schedules = _decimal_to_native(schedules)
        return create_response(200, {
            'schedules': schedules,
            'stats': {
                'totalSchedules': total,
                'activeSchedules': active,
                'pausedSchedules': paused,
                'executionsLast24h': executions_24h,
                'failuresLast24h': failures_24h,
            }
        })
    except ClientError as e:
        logger.error(f"DynamoDB error scanning schedules: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve schedules')


@transaction_log('admin-handler')
def handle_get_custom_plans(event):
    """Return all members with custom plans and a revenue summary.

    Scans MemberPortal-Members for members where tier='custom' OR commitmentStatus exists.
    Returns per-member details and aggregate summary (active count, MRR, grace period count).
    Requirements: 6.1, 6.2, 6.3, 6.4
    """
    from datetime import datetime, timezone

    try:
        table = dynamodb.Table('MemberPortal-Members')

        # Scan with filter: tier = "custom" OR commitmentStatus attribute exists
        filter_expr = Attr('tier').eq('custom') | Attr('commitmentStatus').exists()
        response = table.scan(FilterExpression=filter_expr)
        items = response.get('Items', [])
        # Handle DynamoDB pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=filter_expr,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        now = datetime.now(timezone.utc)
        custom_plans = []
        total_active = 0
        total_monthly_revenue = Decimal('0')
        grace_period_count = 0

        for item in items:
            email = item.get('email', '')
            monthly_price = item.get('customMonthlyPrice', 0)
            token_allocation = item.get('customTokenAllocation', 0)
            start_date = item.get('commitmentStartDate', '')
            end_date = item.get('commitmentEndDate', '')
            status = item.get('commitmentStatus', '')
            paypal_sub_id = item.get('paypalCustomPlanSubId', '')

            # Calculate remaining months
            remaining_months = 0
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if end_dt > now:
                        months = (end_dt.year - now.year) * 12 + (end_dt.month - now.month)
                        if now.day > end_dt.day:
                            months -= 1
                        remaining_months = max(0, months)
                except (ValueError, AttributeError):
                    remaining_months = 0

            # Build plan entry
            plan_entry = {
                'email': email,
                'monthlyPrice': float(Decimal(str(monthly_price))) if monthly_price else 0,
                'tokenAllocation': int(token_allocation) if token_allocation else 0,
                'commitmentStartDate': start_date,
                'commitmentEndDate': end_date,
                'remainingMonths': remaining_months,
                'status': status,
                'paypalSubscriptionId': paypal_sub_id,
            }
            custom_plans.append(plan_entry)

            # Aggregate summary
            if status == 'active':
                total_active += 1
                total_monthly_revenue += Decimal(str(monthly_price)) if monthly_price else Decimal('0')
            elif status == 'grace_period':
                grace_period_count += 1

        # Sort by status (grace_period first for visibility), then by email
        status_order = {'grace_period': 0, 'active': 1, 'expired': 2}
        custom_plans.sort(key=lambda x: (status_order.get(x['status'], 99), x['email']))

        result = {
            'customPlans': custom_plans,
            'summary': {
                'totalActiveCommitments': total_active,
                'totalMonthlyRevenue': float(total_monthly_revenue),
                'gracePeriodCount': grace_period_count,
            }
        }

        return create_response(200, result)

    except ClientError as e:
        logger.error(f"DynamoDB error scanning custom plans: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve custom plans')


@transaction_log('admin-handler')
def handle_get_sync_status(event):
    """Return the current SYNC_METADATA record."""
    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        response = table.get_item(Key={'service': 'SYSTEM', 'tipId': 'SYNC_METADATA'})
        item = response.get('Item')
        if not item:
            return create_response(200, {'status': None, 'message': 'No sync has been executed yet'})
        item.pop('service', None)
        item.pop('tipId', None)
        return create_response(200, {'status': _decimal_to_native(item)})
    except Exception as e:
        logger.error(f"DynamoDB error getting sync status: {e}")
        return create_error_response(500, 'ServerError', f'Failed to retrieve sync status: {str(e)}')


@transaction_log('admin-handler')
def handle_get_sync_logs(event):
    """Return sync log history and current metadata."""
    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        response = table.query(
            KeyConditionExpression=Key('service').eq('SYSTEM') & Key('tipId').begins_with('SYNC_LOG#'),
            ScanIndexForward=False,
        )
        logs = _decimal_to_native(response.get('Items', []))
        for log in logs:
            log.pop('service', None)
            log.pop('tipId', None)
        meta_response = table.get_item(Key={'service': 'SYSTEM', 'tipId': 'SYNC_METADATA'})
        metadata = meta_response.get('Item')
        if metadata:
            metadata.pop('service', None)
            metadata.pop('tipId', None)
            metadata = _decimal_to_native(metadata)
        return create_response(200, {'logs': logs, 'metadata': metadata})
    except Exception as e:
        logger.error(f"DynamoDB error getting sync logs: {e}")
        return create_error_response(500, 'ServerError', f'Failed to retrieve sync logs: {str(e)}')


@transaction_log('admin-handler')
def handle_trigger_sync(event):
    """Invoke the tips-sync Lambda asynchronously."""
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        lambda_client.invoke(
            FunctionName='slashmybill-tips-sync',
            InvocationType='Event',
            Payload=json.dumps({'manual': True}),
        )
        return create_response(202, {'message': 'Sync triggered successfully. It will run in the background.'})
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        return create_error_response(500, 'ServerError', f'Failed to trigger sync: {str(e)}')


# ============================================================
# Transaction Log Routes (NOT decorated to avoid recursive logging)
# ============================================================

def handle_get_transactions(event):
    """Return paginated, filterable transaction log entries. NOT decorated with @transaction_log to avoid recursive logging."""
    # Note: Admin panel uses frontend password gate, not JWT tokens for API calls.
    # Matches existing admin handler pattern (handle_get_leads, handle_get_tips, etc.)

    # Parse query parameters
    params = event.get('queryStringParameters', {}) or {}
    try:
        page = max(1, int(params.get('page', '1')))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = min(100, max(1, int(params.get('page_size', '50'))))
    except (ValueError, TypeError):
        page_size = 50

    user_email = params.get('user_email', '').strip()
    function_name = params.get('function_name', '').strip()
    status_filter = params.get('status', '').strip()
    source_handler_filter = params.get('source_handler', '').strip()
    score_min = params.get('score_min', '').strip()
    score_max = params.get('score_max', '').strip()
    date_from = params.get('date_from', '').strip()
    date_to = params.get('date_to', '').strip()
    search = params.get('search', '').strip().lower()

    try:
        table = dynamodb.Table(TRANSACTION_LOG_TABLE_NAME)

        # Choose query strategy based on filters
        if user_email:
            # Query user-email-index GSI
            query_kwargs = {
                'IndexName': 'user-email-index',
                'KeyConditionExpression': Key('user_email').eq(user_email),
                'ScanIndexForward': False,
            }
            # Add date range to key condition if provided
            if date_from and date_to:
                query_kwargs['KeyConditionExpression'] = (
                    Key('user_email').eq(user_email) &
                    Key('start_timestamp').between(date_from, date_to)
                )
            elif date_from:
                query_kwargs['KeyConditionExpression'] = (
                    Key('user_email').eq(user_email) &
                    Key('start_timestamp').gte(date_from)
                )
            elif date_to:
                query_kwargs['KeyConditionExpression'] = (
                    Key('user_email').eq(user_email) &
                    Key('start_timestamp').lte(date_to)
                )

            items = _query_all_pages(table, query_kwargs)

        elif function_name:
            # Query function-name-index GSI
            query_kwargs = {
                'IndexName': 'function-name-index',
                'KeyConditionExpression': Key('function_name').eq(function_name),
                'ScanIndexForward': False,
            }
            # Add date range to key condition if provided
            if date_from and date_to:
                query_kwargs['KeyConditionExpression'] = (
                    Key('function_name').eq(function_name) &
                    Key('start_timestamp').between(date_from, date_to)
                )
            elif date_from:
                query_kwargs['KeyConditionExpression'] = (
                    Key('function_name').eq(function_name) &
                    Key('start_timestamp').gte(date_from)
                )
            elif date_to:
                query_kwargs['KeyConditionExpression'] = (
                    Key('function_name').eq(function_name) &
                    Key('start_timestamp').lte(date_to)
                )

            items = _query_all_pages(table, query_kwargs)

        else:
            # Full table scan — include payloads when search is active so text
            # search can match account IDs and other request content.
            # Default to last 7 days when no date filter is specified to ensure
            # recent entries are always visible (avoids arbitrary scan ordering).
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            effective_date_from = date_from or None
            if not date_from and not date_to and not search:
                effective_date_from = (_dt.now(_tz.utc) - _td(days=7)).isoformat()
            items = _scan_all_pages(
                table,
                max_items=5000,
                include_payloads=bool(search),
                source_handler_filter=source_handler_filter or None,
                date_from=effective_date_from,
            )

        # Apply server-side filtering
        filtered = _apply_filters(items, status_filter, score_min, score_max, date_from, date_to, search, user_email, function_name, source_handler_filter=source_handler_filter or None)

        # Sort by start_timestamp descending
        filtered.sort(key=lambda x: x.get('start_timestamp', ''), reverse=True)

        # Deduplicate by transaction_id (same API Gateway request logged by multiple Lambdas)
        seen_ids = set()
        deduped = []
        for item in filtered:
            tid = item.get('transaction_id', '')
            if tid and tid in seen_ids:
                continue
            if tid:
                seen_ids.add(tid)
            deduped.append(item)
        filtered = deduped

        # Paginate
        total_count = len(filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        # Strip large payload fields from list response to stay under Lambda 6MB limit.
        # Payloads are only returned in the detail endpoint (GET /admin/transactions/detail).
        slim_items = []
        for item in page_items:
            slim = {k: v for k, v in item.items() if k not in ('request_payload', 'response_payload')}
            slim_items.append(slim)

        # Convert Decimals for JSON serialization
        transactions = _decimal_to_native(slim_items)

        return create_response(200, {
            'transactions': transactions,
            'pagination': {
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
            }
        })

    except ClientError as e:
        logger.error(f"DynamoDB error querying transactions: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve transactions')


def _query_all_pages(table, query_kwargs):
    """Execute a DynamoDB query and handle pagination."""
    items = []
    response = table.query(**query_kwargs)
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        query_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.query(**query_kwargs)
        items.extend(response.get('Items', []))
    return items


def _scan_all_pages(table, max_items=2000, include_payloads=False, source_handler_filter=None, date_from=None):
    """Execute a DynamoDB scan with a cap to prevent Lambda timeout.
    Excludes large payload fields to keep memory under control unless search requires them.
    When date_from is provided, only returns items with start_timestamp >= date_from."""
    items = []
    if include_payloads:
        # Include request_payload for text search (but still exclude response_payload to save memory)
        scan_kwargs = {
            'ProjectionExpression': 'transaction_id, start_timestamp, end_timestamp, function_name, #s, user_email, source_handler, duration_ms, audit_status, audit_score, audit_accuracy_assessment, audit_timing_assessment, audit_improvement_suggestions, request_payload',
            'ExpressionAttributeNames': {'#s': 'status'},
        }
    else:
        # Project only summary fields — payloads excluded to avoid 6MB response limit
        scan_kwargs = {
            'ProjectionExpression': 'transaction_id, start_timestamp, end_timestamp, function_name, #s, user_email, source_handler, duration_ms, audit_status, audit_score, audit_accuracy_assessment, audit_timing_assessment, audit_improvement_suggestions',
            'ExpressionAttributeNames': {'#s': 'status'},
        }

    # Build FilterExpression combining all applicable filters
    filter_conditions = []
    if source_handler_filter:
        filter_conditions.append(Attr('source_handler').eq(source_handler_filter))
    if date_from:
        filter_conditions.append(Attr('start_timestamp').gte(date_from))

    if filter_conditions:
        combined = filter_conditions[0]
        for cond in filter_conditions[1:]:
            combined = combined & cond
        scan_kwargs['FilterExpression'] = combined

    response = table.scan(**scan_kwargs)
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response and len(items) < max_items:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))
    return items


def _apply_filters(items, status_filter, score_min, score_max, date_from, date_to, search, user_email_used, function_name_used, source_handler_filter=None):
    """Apply server-side filtering for status, score range, date range, source handler, and text search."""
    filtered = []

    # Parse score range
    score_min_val = None
    score_max_val = None
    if score_min:
        try:
            score_min_val = int(score_min)
        except (ValueError, TypeError):
            pass
    if score_max:
        try:
            score_max_val = int(score_max)
        except (ValueError, TypeError):
            pass

    for item in items:
        # Source handler filter (when querying via GSI, DynamoDB filter isn't applied)
        if source_handler_filter and item.get('source_handler', '') != source_handler_filter:
            continue

        # Status filter
        if status_filter and item.get('status', '') != status_filter:
            continue

        # Score range filter (treat None/pending scores as passing when min is 0)
        item_score = item.get('audit_score')
        if score_min_val is not None:
            if item_score is not None and int(item_score) < score_min_val:
                continue
            # If item_score is None (not yet scored), only exclude if min > 0
            if item_score is None and score_min_val > 0:
                continue
        if score_max_val is not None:
            if item_score is not None and int(item_score) > score_max_val:
                continue

        # Date range filter (only if not already applied via key condition)
        if not user_email_used and not function_name_used:
            item_timestamp = item.get('start_timestamp', '')
            if date_from and item_timestamp < date_from:
                continue
            if date_to and item_timestamp > date_to:
                continue

        # Text search filter
        if search:
            searchable = ' '.join([
                str(item.get('user_email', '')),
                str(item.get('function_name', '')),
                json.dumps(item.get('request_payload', {})) if isinstance(item.get('request_payload'), dict) else str(item.get('request_payload', '')),
            ]).lower()
            if search not in searchable:
                continue

        filtered.append(item)

    return filtered


def handle_get_transaction_detail(event):
    """Return a single transaction log entry with full payloads and audit evaluation."""
    # Note: Admin panel uses frontend password gate, not JWT tokens for API calls.

    params = event.get('queryStringParameters', {}) or {}
    transaction_id = params.get('transaction_id', '').strip()
    start_timestamp = params.get('start_timestamp', '').strip()

    if not transaction_id or not start_timestamp:
        return create_error_response(400, 'InvalidRequest', 'Query parameters "transaction_id" and "start_timestamp" are required')

    try:
        table = dynamodb.Table(TRANSACTION_LOG_TABLE_NAME)
        response = table.get_item(
            Key={
                'transaction_id': transaction_id,
                'start_timestamp': start_timestamp,
            }
        )
        item = response.get('Item')
        if not item:
            return create_error_response(404, 'NotFound', 'Transaction not found')

        return create_response(200, {'transaction': _decimal_to_native(item)})
    except ClientError as e:
        logger.error(f"DynamoDB error getting transaction detail: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve transaction detail')


# ============================================================
# Custom Plans Config Routes
# ============================================================

@transaction_log('admin-handler')
def handle_get_discount_config(event):
    """Return the current discount configuration from CustomPlan-DiscountConfig table."""
    try:
        table = dynamodb.Table(DISCOUNT_CONFIG_TABLE_NAME)
        response = table.get_item(Key={'configId': 'ACTIVE'})
        item = response.get('Item')
        if not item:
            return create_response(200, {
                'config': None,
                'message': 'No discount configuration found. Please create one.',
            })
        return create_response(200, {'config': _decimal_to_native(item)})
    except ClientError as e:
        logger.error(f"DynamoDB error getting discount config: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve discount configuration')


@transaction_log('admin-handler')
def handle_put_discount_config(event):
    """Validate and update the discount configuration."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    # Extract fields
    base_monthly_price = body.get('baseMonthlyPrice')
    base_token_count = body.get('baseTokenCount')
    discount_tiers = body.get('discountTiers')

    # Validate baseMonthlyPrice
    if base_monthly_price is None or not isinstance(base_monthly_price, (int, float)):
        return create_error_response(400, 'InvalidConfig', 'Base monthly price must be greater than $200')
    if base_monthly_price <= 200:
        return create_error_response(400, 'InvalidConfig', 'Base monthly price must be greater than $200')

    # Validate baseTokenCount
    if base_token_count is None or not isinstance(base_token_count, int) or base_token_count <= 0:
        return create_error_response(400, 'InvalidConfig', 'Base token count must be a positive integer')

    # Validate discountTiers is a non-empty array
    if not discount_tiers or not isinstance(discount_tiers, list) or len(discount_tiers) == 0:
        return create_error_response(400, 'InvalidConfig', 'Discount tiers must be a non-empty array')

    # Validate each tier and discount percentages
    for tier in discount_tiers:
        if not isinstance(tier, dict):
            return create_error_response(400, 'InvalidConfig', 'Each discount tier must be an object')
        min_months = tier.get('minMonths')
        max_months = tier.get('maxMonths')
        discount_percent = tier.get('discountPercent')

        if not isinstance(min_months, int) or not isinstance(max_months, int):
            return create_error_response(400, 'InvalidConfig', 'Discount tier ranges must cover months 3-24 without gaps or overlaps')
        if not isinstance(discount_percent, (int, float)):
            return create_error_response(400, 'InvalidConfig', 'Discount percentages must be between 1 and 50')
        if discount_percent < 1 or discount_percent > 50:
            return create_error_response(400, 'InvalidConfig', 'Discount percentages must be between 1 and 50')
        if min_months > max_months:
            return create_error_response(400, 'InvalidConfig', 'Discount tier ranges must cover months 3-24 without gaps or overlaps')

    # Sort tiers by minMonths ascending
    sorted_tiers = sorted(discount_tiers, key=lambda t: t['minMonths'])

    # Validate tier ranges cover 3-24 without gaps or overlaps
    if sorted_tiers[0]['minMonths'] != 3:
        return create_error_response(400, 'InvalidConfig', 'Discount tier ranges must cover months 3-24 without gaps or overlaps')
    if sorted_tiers[-1]['maxMonths'] != 24:
        return create_error_response(400, 'InvalidConfig', 'Discount tier ranges must cover months 3-24 without gaps or overlaps')

    for i in range(len(sorted_tiers) - 1):
        current_max = sorted_tiers[i]['maxMonths']
        next_min = sorted_tiers[i + 1]['minMonths']
        # Next tier should start exactly 1 after current ends (no gap, no overlap)
        if next_min != current_max + 1:
            return create_error_response(400, 'InvalidConfig', 'Discount tier ranges must cover months 3-24 without gaps or overlaps')

    # Validate monotonicity: discount percent must increase (or stay same) as months increase
    for i in range(len(sorted_tiers) - 1):
        if sorted_tiers[i + 1]['discountPercent'] < sorted_tiers[i]['discountPercent']:
            return create_error_response(400, 'InvalidConfig', 'Discount percentages must be between 1 and 50')

    # Get admin email from JWT token (optional — admin panel may not send token)
    admin_email = ADMIN_USERNAME or 'admin'
    try:
        auth_result = validate_token(event)
        if isinstance(auth_result, dict) and 'statusCode' not in auth_result:
            admin_email = auth_result.get('sub', admin_email)
    except Exception:
        pass

    # Write to DynamoDB
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    try:
        table = dynamodb.Table(DISCOUNT_CONFIG_TABLE_NAME)
        table.put_item(Item={
            'configId': 'ACTIVE',
            'baseMonthlyPrice': Decimal(str(base_monthly_price)),
            'baseTokenCount': base_token_count,
            'discountTiers': sorted_tiers,
            'updatedAt': now,
            'updatedBy': admin_email,
        })
        return create_response(200, {
            'message': 'Discount configuration updated',
            'updatedAt': now,
        })
    except ClientError as e:
        logger.error(f"DynamoDB error updating discount config: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update discount configuration')


# ============================================================
# Connector Configuration CRUD Routes
# ============================================================

@transaction_log('admin-handler')
def handle_get_connectors(event):
    """Return all connector configurations from the ConnectorConfig table.
    Auto-seeds default providers if table exists but is empty."""
    try:
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        # Auto-seed if table is empty
        if not items:
            logger.info("ConnectorConfig table is empty — auto-seeding default providers")
            items = _seed_default_connectors(table)

        connectors = _decimal_to_native(items)
        connectors.sort(key=lambda x: x.get('providerKey', ''))
        return create_response(200, {'connectors': connectors})
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code in ('ResourceNotFoundException', 'AccessDeniedException'):
            logger.warning(f"ConnectorConfig table '{CONNECTOR_CONFIG_TABLE_NAME}' not accessible ({error_code}). Returning empty list.")
            return create_response(200, {'connectors': []})
        logger.error(f"DynamoDB error scanning connectors: {error_code} - {e}")
        return create_error_response(500, 'ServerError', f'DynamoDB error: {error_code}')
    except Exception as e:
        logger.error(f"Unexpected error in handle_get_connectors: {type(e).__name__}: {e}")
        return create_error_response(500, 'ServerError', f'Unexpected error: {type(e).__name__}: {str(e)}')


def _autofill_connector_defaults(body):
    """Auto-fill technical fields that the simplified form doesn't send."""
    pk = body.get('providerKey', '')
    cloud = body.get('cloud', '')
    display = body.get('displayName', pk)

    if not body.get('connectorClass') and pk:
        body['connectorClass'] = f"{pk}_connector.{pk.title().replace('_', '')}Connector"
    if not body.get('iconUrl') and pk:
        body['iconUrl'] = f"/icons/{pk}.svg"
    if not body.get('tipsRepository'):
        body['tipsRepository'] = 'ViewMyBill-CostOptimizationTips'
    if not body.get('supportedOperations'):
        if cloud == 'ai_vendor':
            body['supportedOperations'] = ['get_usage', 'get_cost_breakdown']
        else:
            body['supportedOperations'] = ['get_cost_breakdown', 'get_recommendations', 'get_resource_inventory']
    if not body.get('syncFields'):
        body['syncFields'] = ['costBreakdown', 'monthlyTrend']
    if not body.get('cacheSchema') and pk:
        body['cacheSchema'] = {'pkPrefix': pk.upper(), 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']}
    if not body.get('costEstimationRates'):
        body['costEstimationRates'] = {}
    if not body.get('invoiceFields'):
        body['invoiceFields'] = {'issuerLabel': display, 'accountIdPattern': '.*', 'currencyDefault': 'USD'}
    return body


def _seed_default_connectors(table):
    """Seed the ConnectorConfig table with default providers. Returns the seeded items."""
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    defaults = [
        {'providerKey': 'aws', 'displayName': 'Amazon Web Services', 'cloud': 'aws', 'authType': 'iam_role',
         'connectorClass': 'aws_connector.AWSConnector', 'iconUrl': '/icons/aws.svg', 'stalenessThresholdHours': 24,
         'supportedOperations': ['get_cost_breakdown', 'get_recommendations', 'get_resource_inventory'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'ec2Instances', 'rdsInstances', 'lambdaFunctions'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'Amazon Web Services, Inc.', 'accountIdPattern': '^\\d{12}$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'AWS', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
         'costEstimationRates': {}},
        {'providerKey': 'azure', 'displayName': 'Microsoft Azure', 'cloud': 'azure', 'authType': 'service_principal',
         'connectorClass': 'azure_connector.AzureConnector', 'iconUrl': '/icons/azure.svg', 'stalenessThresholdHours': 48,
         'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'Microsoft Corporation', 'accountIdPattern': '^[0-9a-f-]{36}$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'AZURE', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
         'costEstimationRates': {}},
        {'providerKey': 'gcp', 'displayName': 'Google Cloud Platform', 'cloud': 'gcp', 'authType': 'service_account',
         'connectorClass': 'gcp_connector.GCPConnector', 'iconUrl': '/icons/gcp.svg', 'stalenessThresholdHours': 48,
         'supportedOperations': ['get_cost_breakdown', 'get_recommendations'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'computeInstances'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'Google Cloud', 'accountIdPattern': '^[a-z][a-z0-9-]{4,28}[a-z0-9]$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'GCP', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
         'costEstimationRates': {}},
        {'providerKey': 'openai', 'displayName': 'OpenAI', 'cloud': 'ai_vendor', 'authType': 'api_key',
         'connectorClass': 'ai_vendor_connector.OpenAIConnector', 'iconUrl': '/icons/openai.svg', 'stalenessThresholdHours': 24,
         'supportedOperations': ['get_usage', 'get_cost_breakdown', 'get_model_pricing'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'aiUsage', 'modelBreakdown'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'OpenAI, LLC', 'accountIdPattern': '^org-[A-Za-z0-9]+$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'OPENAI', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'models', 'dailyCosts', 'currency']},
         'costEstimationRates': {'gpt-4o': '0.005', 'gpt-4-turbo': '0.01', 'gpt-3.5-turbo': '0.0015'}},
        {'providerKey': 'anthropic', 'displayName': 'Anthropic', 'cloud': 'ai_vendor', 'authType': 'api_key',
         'connectorClass': 'ai_vendor_connector.AnthropicConnector', 'iconUrl': '/icons/anthropic.svg', 'stalenessThresholdHours': 24,
         'supportedOperations': ['get_usage', 'get_cost_breakdown', 'get_model_pricing'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'aiUsage', 'modelBreakdown'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'Anthropic, PBC', 'accountIdPattern': '^org-[A-Za-z0-9]+$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'ANTHROPIC', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'models', 'dailyCosts', 'currency']},
         'costEstimationRates': {'claude-3-opus': '0.015', 'claude-3-sonnet': '0.003', 'claude-3-haiku': '0.00025'}},
        {'providerKey': 'groundcover', 'displayName': 'Groundcover', 'cloud': 'monitoring', 'authType': 'api_key',
         'connectorClass': 'ai_vendor_connector.GroundcoverConnector', 'iconUrl': '/icons/groundcover.svg', 'stalenessThresholdHours': 24,
         'supportedOperations': ['get_usage', 'get_cost_breakdown'],
         'syncFields': ['costBreakdown', 'monthlyTrend', 'clusterUsage'],
         'tipsRepository': 'ViewMyBill-CostOptimizationTips',
         'invoiceFields': {'issuerLabel': 'GroundCover Ltd.', 'accountIdPattern': '^[A-Za-z0-9_-]+$', 'currencyDefault': 'USD'},
         'cacheSchema': {'pkPrefix': 'GROUNDCOVER', 'skFormat': 'COST#{month}', 'fieldNames': ['totalCost', 'services', 'dailyCosts', 'currency']},
         'costEstimationRates': {}},
    ]
    seeded = []
    for p in defaults:
        p['createdAt'] = now
        p['updatedAt'] = now
        try:
            table.put_item(Item=p, ConditionExpression='attribute_not_exists(providerKey)')
            seeded.append(p)
            logger.info(f"  Seeded connector: {p['providerKey']}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                seeded.append(p)  # already exists
            else:
                logger.error(f"  Failed to seed {p['providerKey']}: {e}")
    return seeded


@transaction_log('admin-handler')
def handle_get_connector(event):
    """Return a single connector configuration by providerKey."""
    path_params = event.get('pathParameters', {}) or {}
    provider_key = path_params.get('provider_key', '')
    if not provider_key:
        return create_error_response(400, 'InvalidRequest', 'Provider key is required')

    try:
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        response = table.get_item(Key={'providerKey': provider_key})
        item = response.get('Item')
        if not item:
            return create_error_response(404, 'NotFound', 'Connector not found')
        return create_response(200, {'connector': _decimal_to_native(item)})
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ResourceNotFoundException':
            return create_error_response(404, 'NotFound', 'Connector not found')
        logger.error(f"DynamoDB error getting connector: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')


@transaction_log('admin-handler')
def handle_create_connector(event):
    """Create a new connector configuration."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    # Auto-fill technical fields if not provided (simplified form sends minimal data)
    body = _autofill_connector_defaults(body)

    # Validate
    errors = validate_connector_config(body, is_update=False)
    if errors:
        return create_response(400, {
            'error': 'ValidationError',
            'message': 'Validation failed',
            'errors': errors,
            'code': 400,
        })

    provider_key = body['providerKey']

    # Check if already exists
    try:
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        existing = table.get_item(Key={'providerKey': provider_key}).get('Item')
        if existing:
            return create_error_response(409, 'ConflictError', 'Connector with this providerKey already exists')
    except ClientError as e:
        logger.error(f"DynamoDB error checking connector existence: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')

    # Set timestamps
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    body['createdAt'] = now
    body['updatedAt'] = now

    try:
        table.put_item(Item=body)
        return create_response(201, {'connector': body, 'message': 'Connector created successfully'})
    except ClientError as e:
        logger.error(f"DynamoDB error creating connector: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')


@transaction_log('admin-handler')
def handle_update_connector(event):
    """Update an existing connector configuration."""
    path_params = event.get('pathParameters', {}) or {}
    provider_key = path_params.get('provider_key', '')
    if not provider_key:
        return create_error_response(400, 'InvalidRequest', 'Provider key is required')

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    # Ensure providerKey in body matches path
    body['providerKey'] = provider_key

    # Validate
    errors = validate_connector_config(body, is_update=False)
    if errors:
        return create_response(400, {
            'error': 'ValidationError',
            'message': 'Validation failed',
            'errors': errors,
            'code': 400,
        })

    # Check record exists
    try:
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        existing = table.get_item(Key={'providerKey': provider_key}).get('Item')
        if not existing:
            return create_error_response(404, 'NotFound', 'Connector not found')
    except ClientError as e:
        logger.error(f"DynamoDB error checking connector: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')

    # Preserve createdAt, update updatedAt
    body['createdAt'] = existing.get('createdAt', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    body['updatedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    try:
        table.put_item(Item=body)
        return create_response(200, {'connector': body, 'message': 'Connector updated successfully'})
    except ClientError as e:
        logger.error(f"DynamoDB error updating connector: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')


@transaction_log('admin-handler')
def handle_delete_connector(event):
    """Delete a connector configuration."""
    path_params = event.get('pathParameters', {}) or {}
    provider_key = path_params.get('provider_key', '')
    if not provider_key:
        return create_error_response(400, 'InvalidRequest', 'Provider key is required')

    try:
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        existing = table.get_item(Key={'providerKey': provider_key}).get('Item')
        if not existing:
            return create_error_response(404, 'NotFound', 'Connector not found')

        table.delete_item(Key={'providerKey': provider_key})
        return create_response(200, {'message': 'Connector deleted successfully'})
    except ClientError as e:
        logger.error(f"DynamoDB error deleting connector: {e}")
        return create_error_response(500, 'ServerError', 'Internal server error')


# ============================================================
# Helper functions
# ============================================================

def cors_headers():
    """Return CORS headers for admin API responses."""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': 'https://slashmycloudbill.com',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Filename',
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
