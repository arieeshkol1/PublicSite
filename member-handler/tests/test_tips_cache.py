"""Unit tests for tips_cache module."""

import time
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tips_cache import (
    _get_cached_tips,
    _set_cached_tips,
    _clear_cache,
    _tips_cache,
    TIPS_CACHE_TTL,
)


class TestTipsCacheTTL:
    """Tests for cache TTL behavior."""

    def setup_method(self):
        """Clear cache before each test."""
        _clear_cache()

    def test_cache_ttl_is_300_seconds(self):
        """TIPS_CACHE_TTL should be 300 seconds (5 minutes)."""
        assert TIPS_CACHE_TTL == 300

    def test_get_cached_tips_returns_none_when_empty(self):
        """Should return None when no cache entry exists for the provider."""
        result = _get_cached_tips("aws")
        assert result is None

    def test_set_and_get_cached_tips(self):
        """Should store and retrieve tips within TTL."""
        tips = [{"tipId": "t1", "service": "EC2", "title": "Use spot instances"}]
        _set_cached_tips("aws", tips)
        result = _get_cached_tips("aws")
        assert result == tips

    def test_cache_keyed_by_provider(self):
        """Each provider should have its own independent cache entry."""
        aws_tips = [{"tipId": "t1", "service": "EC2", "title": "AWS tip"}]
        azure_tips = [{"tipId": "t2", "service": "Virtual Machines", "title": "Azure tip"}]
        gcp_tips = [{"tipId": "t3", "service": "Compute Engine", "title": "GCP tip"}]

        _set_cached_tips("aws", aws_tips)
        _set_cached_tips("azure", azure_tips)
        _set_cached_tips("gcp", gcp_tips)

        assert _get_cached_tips("aws") == aws_tips
        assert _get_cached_tips("azure") == azure_tips
        assert _get_cached_tips("gcp") == gcp_tips

    def test_stale_cache_returns_none(self):
        """Should return None and discard entry when older than TTL."""
        tips = [{"tipId": "t1", "service": "EC2", "title": "Old tip"}]
        _set_cached_tips("aws", tips)

        # Simulate time passing beyond TTL
        _tips_cache["aws"]["timestamp"] = time.time() - 301
        result = _get_cached_tips("aws")
        assert result is None
        # Entry should be removed
        assert "aws" not in _tips_cache

    def test_fresh_cache_at_boundary(self):
        """Should return tips when exactly at TTL - 1 second (still fresh)."""
        tips = [{"tipId": "t1", "service": "S3", "title": "Fresh tip"}]
        _set_cached_tips("aws", tips)

        # Set timestamp to just under 300 seconds ago
        _tips_cache["aws"]["timestamp"] = time.time() - 299
        result = _get_cached_tips("aws")
        assert result == tips

    def test_stale_at_exact_boundary(self):
        """Should return None when exactly at TTL boundary (300 seconds)."""
        tips = [{"tipId": "t1", "service": "RDS", "title": "Boundary tip"}]
        _set_cached_tips("aws", tips)

        # Set timestamp to exactly 300 seconds ago - time.time() - timestamp == 300 is NOT < 300
        _tips_cache["aws"]["timestamp"] = time.time() - 300
        result = _get_cached_tips("aws")
        assert result is None

    def test_set_overwrites_existing_entry(self):
        """Setting cache should overwrite any existing entry."""
        old_tips = [{"tipId": "t1", "title": "Old"}]
        new_tips = [{"tipId": "t2", "title": "New"}]

        _set_cached_tips("aws", old_tips)
        _set_cached_tips("aws", new_tips)

        result = _get_cached_tips("aws")
        assert result == new_tips

    def test_empty_tips_list_is_cached(self):
        """Should cache empty lists (valid DynamoDB result with no tips)."""
        _set_cached_tips("gcp", [])
        result = _get_cached_tips("gcp")
        assert result == []

    def test_clear_cache_removes_all_entries(self):
        """_clear_cache should remove all provider entries."""
        _set_cached_tips("aws", [{"tipId": "t1"}])
        _set_cached_tips("azure", [{"tipId": "t2"}])
        _clear_cache()

        assert _get_cached_tips("aws") is None
        assert _get_cached_tips("azure") is None

    def test_no_external_dependencies(self):
        """Verify the module uses only stdlib (time module)."""
        import tips_cache
        import inspect
        source = inspect.getsource(tips_cache)
        # Should not import redis, memcache, or boto3
        assert "import redis" not in source
        assert "import memcache" not in source
        assert "import boto3" not in source
