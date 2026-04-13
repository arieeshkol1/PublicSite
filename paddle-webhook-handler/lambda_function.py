"""
Paddle Webhook Handler for SlashMyCloudBill.

Receives webhook events from Paddle and updates member tier/tokens in DynamoDB.
Verifies webhook signatures using Paddle's webhook secret.

Events handled:
- subscription.activated  → Set member tier to growth/scale
- subscription.canceled   → Set member tier to free
- subscription.updated    → Update tier if plan changed
- transaction.completed   → Add bonus tokens for one-time top-ups
"""

import json
import os
import hashlib
import hmac
import logging
import boto3
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
MEMBERS_TABLE_NAME = os.environ.get('MEMBERS_TABLE_NAME', 'MemberPortal-Members')
PADDLE_WEBHOOK_SECRET = os.environ.get('PADDLE_WEBHOOK_SECRET', '')

# Map Paddle price IDs to tiers and token amounts
PRICE_TO_TIER = {
    'pri_01kp2zns5ph1vpmh71f98wqzcq': 'growth',
    'pri_01kp2zs05ft013aezpprne5wvd': 'scale',
}

PRICE_TO_TOKENS = {
    'pri_01kp2zv7h558s5289qvaw59whr': 50,    # $5 top-up
    'pri_01kp2zyxwhppmx3ddqax5qmbcn': 200,   # $15 top-up
    'pri_01kp30738d2d23fqpfyy2nj7aj': 500,   # $30 top-up
}


def lambda_handler(event, context):
    """Main handler for Paddle webhook events."""
    # Handle CORS preflight
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return _response(200, {'message': 'OK'})

    try:
        body_str = event.get('body', '')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')

        # Verify webhook signature
        if PADDLE_WEBHOOK_SECRET:
            signature = _get_header(event, 'paddle-signature')
            if not signature:
                logger.warning('Missing Paddle-Signature header')
                return _response(401, {'error': 'Missing signature'})
            if not _verify_signature(body_str, signature):
                logger.warning('Invalid Paddle webhook signature')
                return _response(401, {'error': 'Invalid signature'})

        payload = json.loads(body_str)
        event_type = payload.get('event_type', '')
        data = payload.get('data', {})

        logger.info(f'Paddle webhook: {event_type}')

        if event_type == 'subscription.activated':
            _handle_subscription_activated(data)
        elif event_type == 'subscription.canceled':
            _handle_subscription_canceled(data)
        elif event_type == 'subscription.updated':
            _handle_subscription_updated(data)
        elif event_type == 'transaction.completed':
            _handle_transaction_completed(data)
        else:
            logger.info(f'Unhandled event type: {event_type}')

        return _response(200, {'message': 'OK'})

    except Exception as e:
        logger.error(f'Webhook error: {str(e)}', exc_info=True)
        # Always return 200 to Paddle to prevent retries on our errors
        return _response(200, {'message': 'Processed with errors'})


def _handle_subscription_activated(data):
    """Member subscribed — set their tier."""
    email = _extract_email(data)
    if not email:
        logger.warning('subscription.activated: no email found')
        return

    price_id = _extract_price_id(data)
    tier = PRICE_TO_TIER.get(price_id, None)
    if not tier:
        logger.warning(f'subscription.activated: unknown price {price_id}')
        return

    _update_member_tier(email, tier, {
        'paddleSubscriptionId': data.get('id', ''),
        'paddleCustomerId': data.get('customer_id', ''),
        'subscriptionStatus': 'active',
    })
    logger.info(f'Activated {tier} for {email}')


def _handle_subscription_canceled(data):
    """Member canceled — revert to free tier."""
    email = _extract_email(data)
    if not email:
        logger.warning('subscription.canceled: no email found')
        return

    _update_member_tier(email, 'free', {
        'subscriptionStatus': 'canceled',
        'canceledAt': datetime.now(timezone.utc).isoformat(),
    })
    logger.info(f'Canceled subscription for {email}, reverted to free')


def _handle_subscription_updated(data):
    """Subscription changed (upgrade/downgrade)."""
    email = _extract_email(data)
    if not email:
        return

    price_id = _extract_price_id(data)
    tier = PRICE_TO_TIER.get(price_id, None)
    if tier:
        _update_member_tier(email, tier, {
            'paddleSubscriptionId': data.get('id', ''),
            'subscriptionStatus': data.get('status', 'active'),
        })
        logger.info(f'Updated subscription to {tier} for {email}')


def _handle_transaction_completed(data):
    """One-time purchase completed — add bonus tokens."""
    # Only process one-time transactions (not subscription renewals)
    if data.get('subscription_id'):
        # This is a subscription payment, not a top-up
        logger.info('transaction.completed: subscription payment, skipping token add')
        return

    email = _extract_email(data)
    if not email:
        logger.warning('transaction.completed: no email found')
        return

    items = data.get('items', [])
    total_tokens = 0
    for item in items:
        price = item.get('price', {})
        price_id = price.get('id', '')
        tokens = PRICE_TO_TOKENS.get(price_id, 0)
        quantity = item.get('quantity', 1)
        total_tokens += tokens * quantity

    if total_tokens <= 0:
        logger.info('transaction.completed: no token top-up items found')
        return

    _add_bonus_tokens(email, total_tokens, data.get('id', ''))
    logger.info(f'Added {total_tokens} bonus tokens for {email}')


# ============================================================
# DynamoDB helpers
# ============================================================

def _update_member_tier(email, tier, extra_attrs=None):
    """Update member's tier and optional extra attributes in DynamoDB."""
    table = dynamodb.Table(MEMBERS_TABLE_NAME)
    update_expr = 'SET tier = :tier, updatedAt = :ts'
    expr_values = {
        ':tier': tier,
        ':ts': datetime.now(timezone.utc).isoformat(),
    }

    if extra_attrs:
        for key, value in extra_attrs.items():
            update_expr += f', {key} = :{key}'
            expr_values[f':{key}'] = value

    table.update_item(
        Key={'email': email},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


def _add_bonus_tokens(email, tokens, transaction_id=''):
    """Add bonus tokens to member's account."""
    table = dynamodb.Table(MEMBERS_TABLE_NAME)
    now = datetime.now(timezone.utc).isoformat()

    # Atomically increment bonusTokens
    table.update_item(
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


# ============================================================
# Paddle helpers
# ============================================================

def _extract_email(data):
    """Extract customer email from Paddle webhook data."""
    # Try custom_data first (we pass memberEmail from frontend)
    custom_data = data.get('custom_data', {}) or {}
    if isinstance(custom_data, str):
        try:
            custom_data = json.loads(custom_data)
        except (json.JSONDecodeError, TypeError):
            custom_data = {}
    email = custom_data.get('memberEmail', '')
    if email:
        return email.lower().strip()

    # Try customer.email
    customer = data.get('customer', {}) or {}
    email = customer.get('email', '')
    if email:
        return email.lower().strip()

    # Try billing_details
    billing = data.get('billing_details', {}) or {}
    email = billing.get('email', '')
    if email:
        return email.lower().strip()

    return ''


def _extract_price_id(data):
    """Extract the first price ID from subscription/transaction items."""
    items = data.get('items', [])
    if items:
        price = items[0].get('price', {})
        return price.get('id', '')
    return ''


def _verify_signature(body, signature_header):
    """Verify Paddle webhook signature (Paddle Billing v2 format).

    Paddle-Signature header format: ts=TIMESTAMP;h1=HASH
    Signed payload: TIMESTAMP:BODY
    """
    try:
        parts = {}
        for part in signature_header.split(';'):
            key, _, value = part.partition('=')
            parts[key.strip()] = value.strip()

        ts = parts.get('ts', '')
        h1 = parts.get('h1', '')
        if not ts or not h1:
            return False

        signed_payload = f'{ts}:{body}'
        expected = hmac.new(
            PADDLE_WEBHOOK_SECRET.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, h1)
    except Exception as e:
        logger.error(f'Signature verification error: {e}')
        return False


def _get_header(event, header_name):
    """Get a header value from API Gateway v2 event (case-insensitive)."""
    headers = event.get('headers', {}) or {}
    # API Gateway v2 lowercases all headers
    return headers.get(header_name.lower(), '')


def _response(status_code, body):
    """Create API Gateway v2 response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps(body),
    }
