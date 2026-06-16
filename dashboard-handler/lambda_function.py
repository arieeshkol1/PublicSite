"""
Dashboard Handler Lambda - Widget Builder Dashboard backend.
Routes: POST /dashboard/query, GET /dashboard/layouts,
        PUT /dashboard/layouts, DELETE /dashboard/layouts/{id},
        GET /dashboard/accounts,
        POST /dashboard/datasources/query, PUT /dashboard/datasources,
        GET /dashboard/datasources, DELETE /dashboard/datasources/{id}

Provides a generic query engine for widget data, CRUD for layout persistence,
and custom data source query/management endpoints.
Authentication uses Cognito JWT tokens validated on every request.
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

from auth import extract_token, verify_jwt
from validators import validate_widget_config
from query_engine import QueryEngine
from layout_store import LayoutStore, LayoutStoreError
from datasource_store import DataSourceStore, DataSourceStoreError
from datasource_query import DataSourceQueryEngine

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize components
query_engine = QueryEngine()
layout_store = LayoutStore()
datasource_store = DataSourceStore()
datasource_query_engine = DataSourceQueryEngine()

# DynamoDB resource for accounts queries
_dynamodb = boto3.resource("dynamodb")
ACCOUNTS_TABLE = os.environ.get("ACCOUNTS_TABLE", "MemberPortal-Accounts")


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

        # --- Data source routes ---
        elif path == '/dashboard/accounts' and method == 'GET':
            return _handle_list_accounts(member_email)

        elif path == '/dashboard/datasources/query' and method == 'POST':
            return _handle_datasource_query(event, member_email)

        elif path == '/dashboard/datasources' and method == 'PUT':
            return _handle_save_datasource(event, member_email)

        elif path == '/dashboard/datasources' and method == 'GET':
            return _handle_list_datasources(member_email)

        elif path.startswith('/dashboard/datasources/') and method == 'DELETE':
            datasource_id = path.split('/')[-1]
            return _handle_delete_datasource(member_email, datasource_id)

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


# --- Data Source Route Handlers ---


def _handle_list_accounts(member_email):
    """Handle GET /dashboard/accounts - list connected accounts for the member.

    Queries MemberPortal-Accounts table for accounts with
    connectionStatus="connected" belonging to the authenticated member.
    Returns account_id, account_name (displayName), and cloud_provider.
    """
    try:
        table = _dynamodb.Table(ACCOUNTS_TABLE)
        response = table.query(
            KeyConditionExpression=Key("memberEmail").eq(member_email),
        )
        items = response.get("Items", [])

        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=Key("memberEmail").eq(member_email),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        # Filter to connected accounts only
        accounts = []
        for item in items:
            if item.get("connectionStatus") == "connected":
                accounts.append({
                    "account_id": item.get("accountId", ""),
                    "account_name": item.get("displayName", item.get("accountId", "")),
                    "cloud_provider": item.get("cloudProvider", ""),
                })

        return _response(200, {"accounts": accounts})

    except Exception as e:
        logger.error(f"Error listing accounts: {type(e).__name__}: {e}", exc_info=True)
        return _response(503, {"error": "Failed to retrieve accounts"})


def _handle_datasource_query(event, member_email):
    """Handle POST /dashboard/datasources/query - execute a data source query.

    Parses the request body for query configuration (account_ids, timeframe,
    filters, attributes, page), validates the config, then delegates to
    DataSourceQueryEngine.execute().
    """
    body = _parse_body(event)
    if body is None:
        return _response(400, {"error": "Invalid request body"})

    query_config = body.get("query_config")
    if not query_config or not isinstance(query_config, dict):
        return _response(400, {"error": "query_config is required and must be an object"})

    # Validate required fields
    if not query_config.get("account_ids"):
        return _response(400, {"error": "query_config.account_ids is required"})

    if not query_config.get("timeframe"):
        return _response(400, {"error": "query_config.timeframe is required"})

    # Execute query via data source query engine
    result = datasource_query_engine.execute(member_email, query_config)

    # Check if the engine returned an error
    if "error" in result:
        status_code = result.get("status_code", 400)
        return _response(status_code, {"error": result["error"]})

    return _response(200, result)


def _handle_save_datasource(event, member_email):
    """Handle PUT /dashboard/datasources - create or update a saved data source config.

    Parses the request body and delegates to DataSourceStore.save().
    """
    body = _parse_body(event)
    if body is None:
        return _response(400, {"error": "Invalid request body"})

    try:
        result = datasource_store.save(member_email, body)
    except DataSourceStoreError as e:
        return _response(e.status_code, {"error": e.message})

    return _response(200, result)


def _handle_list_datasources(member_email):
    """Handle GET /dashboard/datasources - list all saved data sources for the member."""
    try:
        datasources = datasource_store.list_all(member_email)
    except DataSourceStoreError as e:
        return _response(e.status_code, {"error": e.message})

    return _response(200, {"datasources": datasources})


def _handle_delete_datasource(member_email, datasource_id):
    """Handle DELETE /dashboard/datasources/{id} - delete a saved data source.

    Returns 404 if the datasource_id does not exist under the member's
    partition, ensuring no information leakage (Requirement 10.3).
    """
    if not datasource_id:
        return _response(400, {"error": "Data source ID is required"})

    deleted = datasource_store.delete(member_email, datasource_id)
    if not deleted:
        return _response(404, {"error": "Data source not found"})

    return _response(200, {"deleted": True})


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
