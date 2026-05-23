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
from botocore.exceptions import ClientError
import jwt
import bcrypt

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '')
JWT_SECRET = os.environ.get('JWT_SECRET', '')
LEADS_TABLE_NAME = os.environ.get('LEADS_TABLE_NAME', 'ViewMyBill-Leads')
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
FEEDBACK_TABLE_NAME = os.environ.get('FEEDBACK_TABLE_NAME', 'MemberPortal-AgentFeedback')

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
    }

    handler = routes.get(route_key)
    if handler is None:
        return create_error_response(404, 'NotFound', 'Route not found')

    return handler(event)


def handle_login(event):
    """Authenticate admin user and return JWT token."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    username = body.get('username', '')
    password = body.get('password', '')

    if not username or not password:
        return create_error_response(400, 'InvalidRequest', 'Username and password are required')

    # Verify credentials
    if username != ADMIN_USERNAME:
        return create_error_response(401, 'AuthError', 'Invalid credentials')

    try:
        password_valid = bcrypt.checkpw(
            password.encode('utf-8'),
            ADMIN_PASSWORD_HASH.encode('utf-8')
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


def handle_get_tips(event):
    """Return all tips from the Tips table, sorted by service then tipId."""
    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        response = table.scan()
        tips = _decimal_to_native(response.get('Items', []))
        tips.sort(key=lambda x: (x.get('service', ''), x.get('tipId', '')))
        return create_response(200, {'tips': tips})
    except ClientError as e:
        logger.error(f"DynamoDB error scanning tips: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve tips')


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

    # Optional field: automatedCheck (script/command)
    if body.get('automatedCheck', '').strip():
        tip['automatedCheck'] = body['automatedCheck'].strip()

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


def handle_update_tip(event):
    """Update an existing tip in the Tips table."""
    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, 'InvalidRequest', 'Invalid request body')

    required_fields = ['service', 'tipId', 'category', 'title', 'description', 'estimatedSavings', 'difficulty']
    for field in required_fields:
        if not body.get(field, '').strip():
            return create_error_response(400, 'InvalidRequest', f'Field "{field}" is required and cannot be empty')

    tip = {field: body[field].strip() for field in required_fields}

    # Optional field: automatedCheck (script/command)
    if body.get('automatedCheck', '').strip():
        tip['automatedCheck'] = body['automatedCheck'].strip()

    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        table.put_item(Item=tip)
        return create_response(200, {'tip': tip, 'message': 'Tip updated successfully'})
    except ClientError as e:
        logger.error(f"DynamoDB error updating tip: {e}")
        return create_error_response(500, 'ServerError', 'Failed to update tip')


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


def handle_get_sync_logs(event):
    """Return sync log history and current metadata."""
    try:
        from boto3.dynamodb.conditions import Key
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
