"""
Tips Cache Module - In-memory cache for cost optimization tips.

Uses Lambda execution context persistence (module-level globals survive across
warm invocations) to cache tips per cloud provider with a 5-minute TTL.
No external dependencies (no Redis, no ElastiCache).
"""

import time

# Module-level globals (Lambda execution context)
_tips_cache: dict[str, dict] = {}  # {provider: {'tips': [...], 'timestamp': float}}
TIPS_CACHE_TTL = 300  # 5 minutes in seconds


def _get_cached_tips(provider: str) -> list | None:
    """Return cached tips if fresh, None if stale or missing.

    Args:
        provider: Cloud provider key ("aws", "azure", "gcp").

    Returns:
        List of tips if cache entry exists and is less than TIPS_CACHE_TTL seconds old,
        otherwise None.
    """
    entry = _tips_cache.get(provider)
    if entry is None:
        return None
    if time.time() - entry['timestamp'] < TIPS_CACHE_TTL:
        return entry['tips']
    # Stale entry - discard it
    del _tips_cache[provider]
    return None


def _set_cached_tips(provider: str, tips: list) -> None:
    """Store tips in cache with current timestamp.

    Args:
        provider: Cloud provider key ("aws", "azure", "gcp").
        tips: List of tip items to cache.
    """
    _tips_cache[provider] = {
        'tips': tips,
        'timestamp': time.time(),
    }


def _clear_cache() -> None:
    """Clear the entire tips cache. Useful for testing."""
    _tips_cache.clear()
