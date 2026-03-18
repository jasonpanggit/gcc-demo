"""
EOL Cache Tests

Tests for EOL-specific memory cache layer.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


class TestCachedEOLResponse:
    """Tests for CachedEOLResponse dataclass."""

    def test_cached_eol_response_imports(self):
        """Test CachedEOLResponse can be imported."""
        from utils.eol_cache import CachedEOLResponse

        assert CachedEOLResponse is not None

    def test_cached_eol_response_creation(self):
        """Test CachedEOLResponse creates correctly."""
        from utils.eol_cache import CachedEOLResponse

        response = CachedEOLResponse(
            id="test-123",
            software_name="Windows Server",
            version="2025",
            agent_name="microsoft",
            response_data={"eol_date": "2034-10-10"},
            confidence_level=95.0,
            created_at="2026-01-01T00:00:00Z",
            expires_at="2026-02-01T00:00:00Z",
            cache_key="windows-server-2025",
            verified=True
        )

        assert response.id == "test-123"
        assert response.software_name == "Windows Server"
        assert response.version == "2025"
        assert response.agent_name == "microsoft"
        assert response.confidence_level == 95.0
        assert response.verified is True

    def test_cached_eol_response_defaults(self):
        """Test CachedEOLResponse uses correct defaults."""
        from utils.eol_cache import CachedEOLResponse

        response = CachedEOLResponse(
            id="test",
            software_name="Test",
            version="1.0",
            agent_name="test",
            response_data={},
            confidence_level=80.0,
            created_at="2026-01-01T00:00:00Z",
            expires_at="2026-02-01T00:00:00Z",
            cache_key="test-key"
        )

        assert response.verified is False
        assert response.source_url is None
        assert response.verification_status is None
        assert response.marked_as_failed is False

    def test_to_dict_conversion(self):
        """Test to_dict converts to dictionary."""
        from utils.eol_cache import CachedEOLResponse

        response = CachedEOLResponse(
            id="test",
            software_name="Test",
            version="1.0",
            agent_name="test",
            response_data={"key": "value"},
            confidence_level=80.0,
            created_at="2026-01-01T00:00:00Z",
            expires_at="2026-02-01T00:00:00Z",
            cache_key="test-key"
        )

        result = response.to_dict()

        assert isinstance(result, dict)
        assert result["id"] == "test"
        assert result["software_name"] == "Test"
        assert result["response_data"]["key"] == "value"

    def test_from_dict_conversion(self):
        """Test from_dict creates from dictionary."""
        from utils.eol_cache import CachedEOLResponse

        data = {
            "id": "test",
            "software_name": "Test",
            "version": "1.0",
            "agent_name": "test",
            "response_data": {"key": "value"},
            "confidence_level": 80.0,
            "created_at": "2026-01-01T00:00:00Z",
            "expires_at": "2026-02-01T00:00:00Z",
            "cache_key": "test-key",
            "_etag": "should-be-filtered",  # Should be filtered out
            "ttl": 3600  # Should be filtered out
        }

        response = CachedEOLResponse.from_dict(data)

        assert response.id == "test"
        assert response.software_name == "Test"
        # _etag and ttl should not cause errors
        assert not hasattr(response, '_etag')
        assert not hasattr(response, 'ttl')


class TestEolMemoryCacheInitialization:
    """Tests for EolMemoryCache initialization."""

    def test_eol_memory_cache_imports(self):
        """Test EolMemoryCache can be imported."""
        from utils.eol_cache import EolMemoryCache

        assert EolMemoryCache is not None

    def test_eol_memory_cache_initialization(self):
        """Test EolMemoryCache initializes correctly."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        assert cache.container_id == 'eol_cache'
        assert cache.cache_duration_days == 30
        assert cache.min_confidence_threshold == 80.0
        assert isinstance(cache.memory_cache, dict)
        assert len(cache.memory_cache) == 0
        assert cache.initialized is False

    def test_eol_memory_cache_custom_container(self):
        """Test EolMemoryCache accepts custom container ID."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache(container_id='custom_cache')

        assert cache.container_id == 'custom_cache'

    def test_memory_lock_exists(self):
        """Test EolMemoryCache has async lock."""
        from utils.eol_cache import EolMemoryCache
        import asyncio

        cache = EolMemoryCache()

        assert hasattr(cache, 'memory_lock')
        assert isinstance(cache.memory_lock, asyncio.Lock)


@pytest.mark.asyncio
class TestEolMemoryCacheOperations:
    """Tests for EolMemoryCache operations."""

    async def test_initialize_sets_flag(self):
        """Test initialize sets initialized flag."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        await cache.initialize()

        # Should mark as initialized
        assert cache.initialized is True

    async def test_initialize_idempotent(self):
        """Test initialize can be called multiple times safely."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        await cache.initialize()
        first_init = cache.initialized

        await cache.initialize()  # Second call

        # Should remain in same state
        assert cache.initialized == first_init


class TestEolCacheModule:
    """Tests for eol_cache module structure."""

    def test_module_imports(self):
        """Test eol_cache module imports."""
        from utils import eol_cache

        assert hasattr(eol_cache, 'EolMemoryCache')
        assert hasattr(eol_cache, 'CachedEOLResponse')
        assert hasattr(eol_cache, 'logger')
        assert hasattr(eol_cache, 'hashlib')
        assert hasattr(eol_cache, 'asyncio')

    def test_cache_stats_manager_import(self):
        """Test cache_stats_manager is imported."""
        from utils import eol_cache

        # May be None if import failed, but should exist
        assert hasattr(eol_cache, 'cache_stats_manager')

    def test_dataclass_decorator(self):
        """Test CachedEOLResponse is a dataclass."""
        from utils.eol_cache import CachedEOLResponse
        from dataclasses import is_dataclass

        assert is_dataclass(CachedEOLResponse)


class TestEolCacheConsolidationNote:
    """Tests for consolidation note and memory-only behavior."""

    def test_memory_only_cache(self):
        """Test cache is memory-only as per consolidation note."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        # Should have memory cache
        assert hasattr(cache, 'memory_cache')
        assert isinstance(cache.memory_cache, dict)

    def test_cache_duration_configuration(self):
        """Test cache duration is configurable."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        # Default 30 days as per module design
        assert cache.cache_duration_days == 30
        assert cache.cache_duration_days > 0

    def test_confidence_threshold(self):
        """Test confidence threshold is set."""
        from utils.eol_cache import EolMemoryCache

        cache = EolMemoryCache()

        # Default 80% confidence threshold
        assert cache.min_confidence_threshold == 80.0
        assert 0 <= cache.min_confidence_threshold <= 100
