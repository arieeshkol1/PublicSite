"""
Connector Configuration Cache Module.
Provides cached access to ConnectorConfig DynamoDB table with fallback
to vendor_registry.json when the table is empty or unreachable.

Deploy this module alongside member-handler and agent-action Lambda packages.
"""

import json
import os
import time
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Configuration
CONNECTOR_CONFIG_TABLE_NAME = os.environ.get('CONNECTOR_CONFIG_TABLE_NAME', 'ConnectorConfig')
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Module-level cache state
_cache: dict = {}
_cache_loaded_at: float = 0.0
_fallback_active: bool = False

# DynamoDB resource (initialized lazily)
_dynamodb = None


def _get_dynamodb():
    """Lazy initialization of DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    return _dynamodb


def _load_vendor_registry_fallback() -> dict:
    """Load connector configs from the static vendor_registry.json file.

    Searches common paths relative to the Lambda package structure.
    Returns a dict keyed by providerKey.
    """
    search_paths = [
        os.path.join(os.path.dirname(__file__), 'connectors', 'vendor_registry.json'),
        os.path.join(os.path.dirname(__file__), 'vendor_registry.json'),
        os.path.join(os.path.dirname(__file__), '..', 'agent-action', 'connectors', 'vendor_registry.json'),
    ]

    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                vendors = data.get('vendors', {})
                # Convert vendor_registry format to ConnectorConfig format
                result = {}
                for key, vendor in vendors.items():
                    result[key] = {
                        'providerKey': key,
                        'displayName': vendor.get('displayName', key),
                        'cloud': vendor.get('cloud', ''),
                        'authType': vendor.get('authType', ''),
                        'cacheSchema': {'pkPrefix': vendor.get('cachePrefix', key.upper()), 'skFormat': 'COST#{month}', 'fieldNames': []},
                        'stalenessThresholdHours': vendor.get('staleness_hours', 48),
                        'connectorClass': vendor.get('connector', ''),
                        'supportedOperations': vendor.get('supportedTools', []),
                        'iconUrl': '',
                        'syncFields': [],
                        'tipsRepository': '',
                        'invoiceFields': {},
                        'costEstimationRates': {},
                    }
                return result
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to read vendor_registry.json at {path}: {e}")
                continue

    logger.critical("vendor_registry.json not found in any search path")
    return {}


def _refresh_cache():
    """Refresh the cache from DynamoDB. Falls back to vendor_registry.json if empty."""
    global _cache, _cache_loaded_at, _fallback_active

    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(CONNECTOR_CONFIG_TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        if items:
            # DynamoDB has records - use them
            new_cache = {}
            for item in items:
                pk = item.get('providerKey')
                if pk:
                    # Convert Decimal types to native Python types
                    new_cache[pk] = _decimal_to_native(item)
            _cache = new_cache
            _cache_loaded_at = time.time()
            if _fallback_active:
                logger.info("ConnectorConfig loaded from DynamoDB - disabling fallback mode")
            _fallback_active = False
        else:
            # DynamoDB table is empty - fall back to static file
            logger.warning("ConnectorConfig table returned zero records - falling back to vendor_registry.json")
            _cache = _load_vendor_registry_fallback()
            _cache_loaded_at = time.time()
            _fallback_active = True

    except ClientError as e:
        # DynamoDB is unreachable - serve last good cache
        logger.warning(f"ConnectorConfig DynamoDB unreachable: {e}. Serving last good cache.")
        if not _cache:
            # No cached data at all - try fallback
            _cache = _load_vendor_registry_fallback()
            _fallback_active = True
        # Don't update _cache_loaded_at so we retry next request


def _ensure_cache_fresh():
    """Ensure the cache is fresh. Refresh if TTL expired."""
    if time.time() - _cache_loaded_at > _CACHE_TTL_SECONDS:
        _refresh_cache()


def _decimal_to_native(obj):
    """Recursively convert Decimal values to int/float for JSON compatibility."""
    from decimal import Decimal
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
# Public API
# ============================================================

def get_connector(provider_key: str) -> dict | None:
    """Get a single connector config by provider key.

    Returns None if not found.
    """
    _ensure_cache_fresh()
    return _cache.get(provider_key)


def get_all_connectors() -> dict:
    """Get all connector configs as {provider_key: config}."""
    _ensure_cache_fresh()
    return dict(_cache)


def is_fallback_active() -> bool:
    """Returns True if serving from static file fallback."""
    _ensure_cache_fresh()
    return _fallback_active
