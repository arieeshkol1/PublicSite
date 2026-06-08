"""
Dashboard Handler Lambda - Widget Builder Dashboard backend.
Routes: POST /dashboard/query, GET /dashboard/layouts,
        PUT /dashboard/layouts, DELETE /dashboard/layouts/{id}

Provides a generic query engine for widget data and CRUD for layout persistence.
Authentication uses Cognito JWT tokens validated on every request.
"""

import json
import logging

from auth import extract_token, verify_jwt
from validators import validate_widget_config
from query_engine import QueryEngine
from layout_store import LayoutStore, LayoutStoreError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize components
query_engine = QueryEngine()
layout_store = LayoutStore()


def lambda_handler(event, context):
    """Main entry point - routes /dashboard/* requests.

    Extracts JWT from Authorization header, validates authentication,
    then dispatches to the appropriate handler based on path and method.
    """
    path = event.get('rawPath', '') or event.get('path', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')

    # Also support routeKey format (API Gateway V2)
    if not method:
        route_key = event.get('routeKey', '')
        if route_key:
            parts = route_key.split(' ', 1)
            if len(parts) == 2:
                method = parts[0]
                path = parts[1]

    logger.info(f"Dashboard API request: {method} {path}")

    # Handle CORS preflight
    if method == 'OPTIONS':
        return _response(200, {'message': 'OK'})

    # Extract and validate JWT token
    token = extract_token(event)
    auth_result = verify_jwt(token)

    if 'error' in auth_result:
        status_code = auth_result.get('status_code', 401)
        return _response(status_code, {'error': auth_result['error']})

    member_email = auth_result['email']

    # Route to appropriate handler
    try:
        if path == '/dashboard/query' and method == 'POST':
            return _handle_query(event, member_email)

        elif path == '/dashboard/layouts' and method == 'GET':
            return _handle_list_layouts(member_email)

        elif path == '/dashboard/layouts' and method == 'PUT':
            return _handle_save_layout(event, member_email)

        elif path.startswith('/dashboard/layouts/') and method == 'GET':
            layout_id = path.split('/')[-1]
            return _handle_get_layout(member_email, layout_id)

        elif path.startswith('/dashboard/layouts/') and method == 'DELETE':
            layout_id = path.split('/')[-1]
            return _handle_delete_layout(member_email, layout_id)

        else:
            return _response(404, {'error': 'Not found'})

    except Exception as e:
        logger.error(f"Unhandled error in dashboard handler: {type(e).__name__}: {e}", exc_info=True)
        return _response(500, {'error': f'Internal server error: {type(e).__name__}'})


def _handle_query(event, member_email):
    """Handle POST /dashboard/query - execute a widget data query.

    Validates the widget configuration, then delegates to the query engine.
    """
    body = _parse_body(event)
    if body is None:
        return _response(400, {'error': 'Invalid request body'})

    widget_config = body.get('widget_config')

    # Validate widget configuration
    valid, error_msg = validate_widget_config(widget_config)
    if not valid:
        return _response(400, {'error': error_msg})

    # Execute query via query engine
    result = query_engine.execute(member_email, widget_config)
    return _response(200, result)


def _handle_list_layouts(member_email):
    """Handle GET /dashboard/layouts - list all layouts for the member."""
    layouts = layout_store.list_layouts(member_email)
    return _response(200, {'layouts': layouts})


def _handle_get_layout(member_email, layout_id):
    """Handle GET /dashboard/layouts/{id} - retrieve a specific layout.

    Returns 404 (not 403) if the layout_id does not exist under the
    member's partition, ensuring no information leakage about other
    members' layouts (Requirement 9.4).
    """
    if not layout_id:
        return _response(400, {'error': 'Layout ID is required'})

    try:
        layout = layout_store.get_layout(member_email, layout_id)
    except LayoutStoreError as e:
        return _response(e.status_code, {'error': e.message})

    return _response(200, layout)


def _handle_save_layout(event, member_email):
    """Handle PUT /dashboard/layouts - create or update a layout."""
    body = _parse_body(event)
    if body is None:
        return _response(400, {'error': 'Invalid request body'})

    try:
        result = layout_store.save_layout(member_email, body)
    except LayoutStoreError as e:
        return _response(e.status_code, {'error': e.message})

    return _response(200, result)


def _handle_delete_layout(member_email, layout_id):
    """Handle DELETE /dashboard/layouts/{id} - delete a specific layout.

    Returns 404 (not 403) if the layout_id does not exist under the
    member's partition, ensuring no information leakage about other
    members' layouts (Requirement 9.4).
    """
    if not layout_id:
        return _response(400, {'error': 'Layout ID is required'})

    try:
        layout_store.delete_layout(member_email, layout_id)
    except LayoutStoreError as e:
        return _response(e.status_code, {'error': e.message})

    return _response(200, {'deleted': True})


def _parse_body(event):
    """Parse JSON body from the event, returning None on failure."""
    try:
        body_str = event.get('body', '{}')
        if body_str is None:
            return {}
        return json.loads(body_str)
    except (json.JSONDecodeError, TypeError):
        return None


def _response(status_code, body):
    """Create an API Gateway response with CORS headers.

    Args:
        status_code: HTTP status code.
        body: Dict to serialize as JSON response body.

    Returns:
        API Gateway response dict.
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body)
    }
