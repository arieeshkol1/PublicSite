"""
provider_registry.py — Centralized provider configuration cache.

Loaded once per Lambda cold start. All lookups served from in-memory cache.
"""

import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = 'ProviderRegistry'
_cache: dict = {}  # {provider_id: {category: config_map}}


def _load_provider(provider_id: str) -> None:
    """Query all config categories for a provider and populate cache."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(_TABLE_NAME)
    response = table.query(
        KeyConditionExpression=Key('providerId').eq(provider_id)
    )
    _cache[provider_id] = {
        item['configCategory']: item['config']
        for item in response.get('Items', [])
    }


def get_config(provider_id: str, category: str) -> dict:
    """Return config map for (provider_id, category). Lazy-loads if cache empty."""
    if provider_id not in _cache:
        _load_provider(provider_id)
    return _cache.get(provider_id, {}).get(category, {})


def get_all_categories(provider_id: str) -> dict:
    """Return all categories for a provider as {category: config_map}."""
    if provider_id not in _cache:
        _load_provider(provider_id)
    return _cache.get(provider_id, {})


def invalidate_cache() -> None:
    """Clear the cache (used in testing or forced refresh)."""
    _cache.clear()
