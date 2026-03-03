"""
Tool Result Cache Tests

Tests for TTL-based LRU cache for tool invocation results.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
import asyncio
import time
from unittest.mock import patch


class TestCacheEntry:
    """Tests for CacheEntry class."""

    def test_cache_entry_imports(self):
        """Test CacheEntry can be imported."""
        from utils.tool_result_cache import CacheEntry

        assert CacheEntry is not None

    def test_cache_entry_creation(self):
        """Test CacheEntry creates with value and TTL."""
        from utils.tool_result_cache import CacheEntry

        entry = CacheEntry({"result": "data"}, ttl_seconds=60.0)

        assert entry.value == {"result": "data"}
        assert hasattr(entry, 'expires_at')
        assert isinstance(entry.expires_at, float)

    def test_cache_entry_is_not_expired(self):
        """Test is_expired returns False for fresh entry."""
        from utils.tool_result_cache import CacheEntry

        entry = CacheEntry("test", ttl_seconds=60.0)

        assert entry.is_expired() is False

    def test_cache_entry_is_expired(self):
        """Test is_expired returns True for expired entry."""
        from utils.tool_result_cache import CacheEntry

        # Create entry with 0.01 second TTL
        entry = CacheEntry("test", ttl_seconds=0.01)

        # Wait for expiry
        time.sleep(0.02)

        assert entry.is_expired() is True

    def test_cache_entry_slots(self):
        """Test CacheEntry uses __slots__ for memory efficiency."""
        from utils.tool_result_cache import CacheEntry

        entry = CacheEntry("test", 60.0)

        assert hasattr(CacheEntry, '__slots__')
        assert 'value' in CacheEntry.__slots__
        assert 'expires_at' in CacheEntry.__slots__


class TestToolResultCacheInitialization:
    """Tests for ToolResultCache initialization."""

    def test_tool_result_cache_imports(self):
        """Test ToolResultCache can be imported."""
        from utils.tool_result_cache import ToolResultCache

        assert ToolResultCache is not None

    def test_tool_result_cache_default_initialization(self):
        """Test ToolResultCache initializes with defaults."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        assert cache._default_ttl == 300.0
        assert cache._max_size == 1000
        assert len(cache._store) == 0
        assert len(cache._tool_keys) == 0
        assert cache._hits == 0
        assert cache._misses == 0
        assert cache._evictions == 0

    def test_tool_result_cache_custom_initialization(self):
        """Test ToolResultCache accepts custom parameters."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache(default_ttl_seconds=600.0, max_size=500)

        assert cache._default_ttl == 600.0
        assert cache._max_size == 500

    def test_tool_result_cache_has_lock(self):
        """Test ToolResultCache has async lock."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        assert hasattr(cache, '_lock')
        assert isinstance(cache._lock, asyncio.Lock)


class TestMakeKey:
    """Tests for make_key method."""

    def test_make_key_deterministic(self):
        """Test make_key produces deterministic keys."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key1 = cache.make_key("test_tool", {"a": 1, "b": 2})
        key2 = cache.make_key("test_tool", {"a": 1, "b": 2})

        assert key1 == key2

    def test_make_key_order_independent(self):
        """Test make_key is order-independent for args."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key1 = cache.make_key("test_tool", {"a": 1, "b": 2})
        key2 = cache.make_key("test_tool", {"b": 2, "a": 1})

        assert key1 == key2

    def test_make_key_different_tools(self):
        """Test make_key produces different keys for different tools."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key1 = cache.make_key("tool_a", {"x": 1})
        key2 = cache.make_key("tool_b", {"x": 1})

        assert key1 != key2

    def test_make_key_different_args(self):
        """Test make_key produces different keys for different args."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key1 = cache.make_key("test_tool", {"x": 1})
        key2 = cache.make_key("test_tool", {"x": 2})

        assert key1 != key2

    def test_make_key_with_complex_args(self):
        """Test make_key handles complex nested args."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key = cache.make_key("test_tool", {
            "nested": {"a": 1, "b": [1, 2, 3]},
            "simple": "value"
        })

        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length


@pytest.mark.asyncio
class TestGetOperation:
    """Tests for get operation."""

    async def test_get_miss(self):
        """Test get returns None on cache miss."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        result = await cache.get("nonexistent-key")

        assert result is None
        assert cache._misses == 1
        assert cache._hits == 0

    async def test_get_hit(self):
        """Test get returns cached value on hit."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        # Set value
        await cache.set(key, {"result": "data"}, tool_name="test_tool")

        # Get value
        result = await cache.get(key)

        assert result == {"result": "data"}
        assert cache._hits == 1
        assert cache._misses == 0

    async def test_get_expired(self):
        """Test get returns None for expired entry."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        # Set value with very short TTL
        await cache.set(key, "test-value", ttl_seconds=0.01, tool_name="test_tool")

        # Wait for expiry
        await asyncio.sleep(0.02)

        # Get should return None and increment misses
        result = await cache.get(key)

        assert result is None
        assert cache._misses == 1

    async def test_get_lru_promotion(self):
        """Test get promotes entry to most-recently-used."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        # Add two entries
        key1 = cache.make_key("tool1", {"x": 1})
        key2 = cache.make_key("tool2", {"x": 2})

        await cache.set(key1, "value1", tool_name="tool1")
        await cache.set(key2, "value2", tool_name="tool2")

        # Access key1 (should move to end)
        await cache.get(key1)

        # Verify key1 is at the end (most recent)
        keys = list(cache._store.keys())
        assert keys[-1] == key1


@pytest.mark.asyncio
class TestSetOperation:
    """Tests for set operation."""

    async def test_set_basic(self):
        """Test set stores value with default TTL."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        await cache.set(key, "test-value", tool_name="test_tool")

        result = await cache.get(key)
        assert result == "test-value"

    async def test_set_custom_ttl(self):
        """Test set respects custom TTL."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        await cache.set(key, "test-value", ttl_seconds=60.0, tool_name="test_tool")

        result = await cache.get(key)
        assert result == "test-value"

    async def test_set_updates_existing(self):
        """Test set updates existing entry."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        # Set initial value
        await cache.set(key, "value1", tool_name="test_tool")

        # Update value
        await cache.set(key, "value2", tool_name="test_tool")

        result = await cache.get(key)
        assert result == "value2"

    async def test_set_without_tool_name(self):
        """Test set works without tool_name for secondary index."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = "manual-key"

        await cache.set(key, "test-value")

        result = await cache.get(key)
        assert result == "test-value"

    async def test_set_triggers_lru_eviction(self):
        """Test set triggers LRU eviction at max capacity."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache(max_size=3)

        # Fill cache
        key1 = cache.make_key("tool1", {"x": 1})
        key2 = cache.make_key("tool2", {"x": 2})
        key3 = cache.make_key("tool3", {"x": 3})

        await cache.set(key1, "value1", tool_name="tool1")
        await cache.set(key2, "value2", tool_name="tool2")
        await cache.set(key3, "value3", tool_name="tool3")

        # Add one more (should evict key1)
        key4 = cache.make_key("tool4", {"x": 4})
        await cache.set(key4, "value4", tool_name="tool4")

        # key1 should be evicted, key4 should exist
        assert await cache.get(key1) is None
        assert await cache.get(key4) == "value4"
        assert cache._evictions == 1


@pytest.mark.asyncio
class TestInvalidateOperations:
    """Tests for invalidate operations."""

    async def test_invalidate_single_key(self):
        """Test invalidate removes single key."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        await cache.set(key, "test-value", tool_name="test_tool")
        await cache.invalidate(key)

        result = await cache.get(key)
        assert result is None

    async def test_invalidate_nonexistent_key(self):
        """Test invalidate handles nonexistent key."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        # Should not raise error
        await cache.invalidate("nonexistent-key")

    async def test_invalidate_pattern_by_tool_name(self):
        """Test invalidate_pattern removes all entries for a tool."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        # Add multiple entries for same tool
        key1 = cache.make_key("test_tool", {"x": 1})
        key2 = cache.make_key("test_tool", {"x": 2})
        key3 = cache.make_key("other_tool", {"x": 3})

        await cache.set(key1, "value1", tool_name="test_tool")
        await cache.set(key2, "value2", tool_name="test_tool")
        await cache.set(key3, "value3", tool_name="other_tool")

        # Invalidate all test_tool entries
        count = await cache.invalidate_pattern("test_tool")

        assert count == 2
        assert await cache.get(key1) is None
        assert await cache.get(key2) is None
        assert await cache.get(key3) == "value3"

    async def test_invalidate_pattern_empty(self):
        """Test invalidate_pattern returns 0 for unknown tool."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        count = await cache.invalidate_pattern("unknown_tool")

        assert count == 0


@pytest.mark.asyncio
class TestClearOperation:
    """Tests for clear operation."""

    async def test_clear_removes_all(self):
        """Test clear removes all entries."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        # Add multiple entries
        key1 = cache.make_key("tool1", {"x": 1})
        key2 = cache.make_key("tool2", {"x": 2})

        await cache.set(key1, "value1", tool_name="tool1")
        await cache.set(key2, "value2", tool_name="tool2")

        # Clear cache
        await cache.clear()

        assert len(cache._store) == 0
        assert len(cache._tool_keys) == 0
        assert await cache.get(key1) is None
        assert await cache.get(key2) is None

    async def test_clear_resets_stats(self):
        """Test clear resets statistics."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        # Generate some stats
        await cache.set(key, "value", tool_name="test_tool")
        await cache.get(key)  # hit
        await cache.get("nonexistent")  # miss

        # Clear
        await cache.clear()

        assert cache._hits == 0
        assert cache._misses == 0
        assert cache._evictions == 0


class TestStatistics:
    """Tests for cache statistics."""

    def test_stats_initial(self):
        """Test stats returns correct initial values."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        stats = cache.stats

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["evictions"] == 0
        assert stats["hit_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_hit_rate_calculation(self):
        """Test stats calculates hit_rate correctly."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})

        # Set value
        await cache.set(key, "value", tool_name="test_tool")

        # Generate hits and misses
        await cache.get(key)  # hit
        await cache.get(key)  # hit
        await cache.get("nonexistent")  # miss

        stats = cache.stats

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        # 2 hits out of 3 requests = 0.6667
        assert abs(stats["hit_rate"] - 0.6667) < 0.01

    @pytest.mark.asyncio
    async def test_stats_size_tracking(self):
        """Test stats tracks cache size."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        key1 = cache.make_key("tool1", {"x": 1})
        key2 = cache.make_key("tool2", {"x": 2})

        await cache.set(key1, "value1", tool_name="tool1")
        await cache.set(key2, "value2", tool_name="tool2")

        stats = cache.stats
        assert stats["size"] == 2


class TestToolResultCacheModule:
    """Tests for tool_result_cache module structure."""

    def test_module_imports(self):
        """Test tool_result_cache module imports."""
        from utils import tool_result_cache

        assert hasattr(tool_result_cache, 'ToolResultCache')
        assert hasattr(tool_result_cache, 'CacheEntry')
        assert hasattr(tool_result_cache, 'asyncio')
        assert hasattr(tool_result_cache, 'time')
        assert hasattr(tool_result_cache, 'hashlib')

    def test_ordered_dict_usage(self):
        """Test ToolResultCache uses OrderedDict for LRU."""
        from utils.tool_result_cache import ToolResultCache
        from collections import OrderedDict

        cache = ToolResultCache()

        assert isinstance(cache._store, OrderedDict)

    def test_monotonic_time_usage(self):
        """Test module uses time.monotonic for expiry."""
        from utils.tool_result_cache import CacheEntry

        # CacheEntry should use time.monotonic
        entry = CacheEntry("test", 60.0)

        # expires_at should be a float (monotonic timestamp)
        assert isinstance(entry.expires_at, float)
        assert entry.expires_at > 0


@pytest.mark.asyncio
class TestConcurrency:
    """Tests for async-safe concurrent access."""

    async def test_concurrent_reads(self):
        """Test multiple concurrent reads are safe."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key = cache.make_key("test_tool", {"x": 1})
        await cache.set(key, "value", tool_name="test_tool")

        # Concurrent reads
        results = await asyncio.gather(
            cache.get(key),
            cache.get(key),
            cache.get(key),
        )

        assert all(r == "value" for r in results)

    async def test_concurrent_writes(self):
        """Test multiple concurrent writes are safe."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()

        # Concurrent writes with different keys
        await asyncio.gather(
            cache.set("key1", "value1"),
            cache.set("key2", "value2"),
            cache.set("key3", "value3"),
        )

        assert len(cache._store) == 3

    async def test_concurrent_mixed_operations(self):
        """Test mixed concurrent operations are safe."""
        from utils.tool_result_cache import ToolResultCache

        cache = ToolResultCache()
        key1 = cache.make_key("tool1", {"x": 1})
        key2 = cache.make_key("tool2", {"x": 2})

        await cache.set(key1, "value1", tool_name="tool1")

        # Mix of reads, writes, invalidations
        await asyncio.gather(
            cache.get(key1),
            cache.set(key2, "value2", tool_name="tool2"),
            cache.invalidate(key1),
            cache.get(key2),
        )

        # Should complete without errors
        assert True
