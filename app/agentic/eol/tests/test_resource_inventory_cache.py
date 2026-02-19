"""
Test suite for ResourceInventoryCache.

Tests L1 (in-memory) cache, L2 (Cosmos DB) fallback, per-resource-type
TTL overrides, batch operations, invalidation, and statistics tracking.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

MOCK_SUB_ID = "12345678-1234-1234-1234-123456789012"
MOCK_RESOURCE_TYPE = "Microsoft.Compute/virtualMachines"
MOCK_RESOURCES = [
    {"id": "r1", "name": "vm-1", "type": MOCK_RESOURCE_TYPE},
    {"id": "r2", "name": "vm-2", "type": MOCK_RESOURCE_TYPE},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache():
    """Create a fresh ResourceInventoryCache with L2 disabled."""
    from utils.resource_inventory_cache import ResourceInventoryCache
    c = ResourceInventoryCache(default_l1_ttl=300, default_l2_ttl=3600, max_l1_entries=100)
    # Disable L2 so tests stay pure unit tests
    c._l2_ready = False
    return c


@pytest.fixture
def cache_with_l2():
    """Create a ResourceInventoryCache with a mocked L2 Cosmos container."""
    from utils.resource_inventory_cache import ResourceInventoryCache
    c = ResourceInventoryCache(default_l1_ttl=300, default_l2_ttl=3600, max_l1_entries=100)
    c._l2_container = MagicMock()
    c._l2_ready = True
    return c


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------

class TestCacheKey:
    """Tests for deterministic cache key construction."""

    def test_basic_key_format(self):
        from utils.resource_inventory_cache import ResourceInventoryCache
        key = ResourceInventoryCache._cache_key(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert key == f"resource_inv:{MOCK_SUB_ID}:{MOCK_RESOURCE_TYPE}"

    def test_key_with_filters(self):
        from utils.resource_inventory_cache import ResourceInventoryCache
        filters = {"location": "eastus", "env": "prod"}
        key = ResourceInventoryCache._cache_key(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, filters)
        # Should end with a hash suffix
        assert key.startswith(f"resource_inv:{MOCK_SUB_ID}:{MOCK_RESOURCE_TYPE}:")
        assert len(key.split(":")[-1]) == 10  # md5[:10]

    def test_filter_order_independent(self):
        from utils.resource_inventory_cache import ResourceInventoryCache
        key1 = ResourceInventoryCache._cache_key(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, {"a": "1", "b": "2"})
        key2 = ResourceInventoryCache._cache_key(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, {"b": "2", "a": "1"})
        assert key1 == key2


# ---------------------------------------------------------------------------
# L1 cache hit / miss
# ---------------------------------------------------------------------------

class TestL1CacheHitMiss:
    """Tests for L1 (in-memory) cache layer."""

    async def test_miss_returns_none(self, cache):
        """A get on empty cache should return None."""
        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result is None

    async def test_set_then_get_returns_data(self, cache):
        """A set followed by get should return the cached data."""
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)
        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result == MOCK_RESOURCES

    async def test_expired_entry_returns_none(self, cache):
        """An expired L1 entry should be evicted and return None."""
        # Set with very short TTL
        cache._default_l1_ttl = 0  # immediate expiry
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)

        # Wait a tiny bit so the entry expires
        time.sleep(0.01)
        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result is None

    async def test_different_resource_types_independent(self, cache):
        """Different resource types should not interfere with each other."""
        type_a = "Microsoft.Compute/virtualMachines"
        type_b = "Microsoft.Web/sites"
        data_a = [{"id": "vm-1"}]
        data_b = [{"id": "app-1"}]

        await cache.set(MOCK_SUB_ID, type_a, data_a)
        await cache.set(MOCK_SUB_ID, type_b, data_b)

        assert await cache.get(MOCK_SUB_ID, type_a) == data_a
        assert await cache.get(MOCK_SUB_ID, type_b) == data_b


# ---------------------------------------------------------------------------
# L2 fallback
# ---------------------------------------------------------------------------

class TestL2Fallback:
    """Tests for L2 (Cosmos DB) cache fallback."""

    async def test_l2_hit_promotes_to_l1(self, cache_with_l2):
        """A L2 hit should populate L1 for future requests."""
        cache = cache_with_l2
        # Mock L2 returning data
        cache._l2_container.query_items.return_value = [
            {"resources": MOCK_RESOURCES, "cache_key": "whatever"}
        ]

        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)

        assert result == MOCK_RESOURCES
        assert cache._hits_l2 == 1

        # Second call should hit L1 (no more L2 queries)
        cache._l2_container.query_items.reset_mock()
        result2 = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result2 == MOCK_RESOURCES
        assert cache._hits_l1 == 1
        cache._l2_container.query_items.assert_not_called()

    async def test_l2_miss_returns_none(self, cache_with_l2):
        """When L2 has no data, should return None."""
        cache = cache_with_l2
        cache._l2_container.query_items.return_value = []

        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result is None
        assert cache._misses == 1

    async def test_l2_error_handled_gracefully(self, cache_with_l2):
        """L2 query errors should be caught and return None."""
        cache = cache_with_l2
        cache._l2_container.query_items.side_effect = Exception("Cosmos unavailable")

        result = await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        assert result is None
        assert cache._misses == 1

    async def test_set_writes_to_l2(self, cache_with_l2):
        """set() should upsert a document to the L2 container."""
        cache = cache_with_l2
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)

        cache._l2_container.upsert_item.assert_called_once()
        doc = cache._l2_container.upsert_item.call_args[0][0]
        assert doc["subscription_id"] == MOCK_SUB_ID
        assert doc["resource_type"] == MOCK_RESOURCE_TYPE
        assert doc["resources"] == MOCK_RESOURCES
        assert doc["resource_count"] == 2


# ---------------------------------------------------------------------------
# TTL overrides per resource type
# ---------------------------------------------------------------------------

class TestTTLOverrides:
    """Tests for per-resource-type TTL configuration."""

    def test_vm_ttl_override(self, cache):
        """VMs should have a 30-minute TTL override."""
        ttl = cache._ttl_for("Microsoft.Compute/virtualMachines", "l2")
        assert ttl == 1800  # 30 min

    def test_vnet_ttl_override(self, cache):
        """VNets should have a 24-hour TTL override."""
        ttl = cache._ttl_for("Microsoft.Network/virtualNetworks", "l2")
        assert ttl == 86400  # 24 hr

    def test_unknown_type_uses_default(self, cache):
        """Unknown resource types should get the default TTL."""
        ttl_l1 = cache._ttl_for("Microsoft.CustomRP/resources", "l1")
        ttl_l2 = cache._ttl_for("Microsoft.CustomRP/resources", "l2")
        assert ttl_l1 == 300   # default L1
        assert ttl_l2 == 3600  # default L2

    def test_l1_ttl_capped(self, cache):
        """L1 TTL should not exceed default L1 TTL even with override."""
        # VM override is 1800 but L1 default is 300
        ttl_l1 = cache._ttl_for("Microsoft.Compute/virtualMachines", "l1")
        assert ttl_l1 <= cache._default_l1_ttl


# ---------------------------------------------------------------------------
# Batch operations (get_multi)
# ---------------------------------------------------------------------------

class TestBatchOperations:
    """Tests for get_multi() batch retrieval."""

    async def test_batch_retrieval_all_hits(self, cache):
        """Should return data for all subscriptions that are cached."""
        sub_a = "sub-a"
        sub_b = "sub-b"
        data_a = [{"id": "r1"}]
        data_b = [{"id": "r2"}]

        await cache.set(sub_a, MOCK_RESOURCE_TYPE, data_a)
        await cache.set(sub_b, MOCK_RESOURCE_TYPE, data_b)

        results = await cache.get_multi([sub_a, sub_b], MOCK_RESOURCE_TYPE)

        assert results[sub_a] == data_a
        assert results[sub_b] == data_b

    async def test_batch_retrieval_partial_misses(self, cache):
        """Uncached subscriptions should return None."""
        sub_a = "sub-a"
        sub_b = "sub-b"
        data_a = [{"id": "r1"}]

        await cache.set(sub_a, MOCK_RESOURCE_TYPE, data_a)

        results = await cache.get_multi([sub_a, sub_b], MOCK_RESOURCE_TYPE)

        assert results[sub_a] == data_a
        assert results[sub_b] is None

    async def test_batch_empty_list(self, cache):
        """Empty subscription list should return empty dict."""
        results = await cache.get_multi([], MOCK_RESOURCE_TYPE)
        assert results == {}


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

class TestInvalidation:
    """Tests for cache invalidation."""

    async def test_invalidate_by_subscription(self, cache):
        """Should remove all entries for a subscription."""
        type_a = "Microsoft.Compute/virtualMachines"
        type_b = "Microsoft.Web/sites"

        await cache.set(MOCK_SUB_ID, type_a, [{"id": "r1"}])
        await cache.set(MOCK_SUB_ID, type_b, [{"id": "r2"}])

        removed = await cache.invalidate(MOCK_SUB_ID)

        assert removed == 2
        assert await cache.get(MOCK_SUB_ID, type_a) is None
        assert await cache.get(MOCK_SUB_ID, type_b) is None

    async def test_invalidate_by_resource_type(self, cache):
        """Should only remove entries matching the resource type."""
        type_a = "Microsoft.Compute/virtualMachines"
        type_b = "Microsoft.Web/sites"

        await cache.set(MOCK_SUB_ID, type_a, [{"id": "r1"}])
        await cache.set(MOCK_SUB_ID, type_b, [{"id": "r2"}])

        removed = await cache.invalidate(MOCK_SUB_ID, resource_type=type_a)

        assert removed == 1
        assert await cache.get(MOCK_SUB_ID, type_a) is None
        assert await cache.get(MOCK_SUB_ID, type_b) is not None

    async def test_clear_all(self, cache):
        """clear_all() should empty the L1 cache and reset stats."""
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)
        await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)

        count = cache.clear_all()

        assert count == 1
        assert await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE) is None
        stats = cache.get_statistics()
        assert stats["hits_l1"] == 0
        assert stats["misses"] == 0


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    """Tests for cache statistics tracking."""

    async def test_hit_rate_calculation(self, cache):
        """Hit rate should reflect actual hits vs misses."""
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)

        # 1 hit
        await cache.get(MOCK_SUB_ID, MOCK_RESOURCE_TYPE)
        # 1 miss
        await cache.get("nonexistent-sub", MOCK_RESOURCE_TYPE)

        stats = cache.get_statistics()
        assert stats["hits_l1"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate_percent"] == 50.0

    async def test_initial_stats_are_zero(self, cache):
        """Fresh cache should have all-zero statistics."""
        stats = cache.get_statistics()
        assert stats["total_requests"] == 0
        assert stats["hits_l1"] == 0
        assert stats["hits_l2"] == 0
        assert stats["misses"] == 0
        assert stats["writes"] == 0
        assert stats["hit_rate_percent"] == 0.0

    async def test_write_counter(self, cache):
        """Writes should be tracked."""
        await cache.set(MOCK_SUB_ID, MOCK_RESOURCE_TYPE, MOCK_RESOURCES)
        await cache.set("sub-2", MOCK_RESOURCE_TYPE, MOCK_RESOURCES)

        stats = cache.get_statistics()
        assert stats["writes"] == 2

    async def test_stats_include_ttl_overrides(self, cache):
        """Statistics should expose TTL override map."""
        stats = cache.get_statistics()
        assert "ttl_overrides" in stats
        assert "Microsoft.Compute/virtualMachines" in stats["ttl_overrides"]


# ---------------------------------------------------------------------------
# L1 eviction
# ---------------------------------------------------------------------------

class TestL1Eviction:
    """Tests for L1 capacity management."""

    async def test_evicts_when_at_capacity(self):
        """Should evict entries when L1 reaches max capacity."""
        from utils.resource_inventory_cache import ResourceInventoryCache
        cache = ResourceInventoryCache(max_l1_entries=3)
        cache._l2_ready = False

        for i in range(5):
            await cache.set(f"sub-{i}", MOCK_RESOURCE_TYPE, [{"id": f"r{i}"}])

        # Should not exceed max entries after eviction
        stats = cache.get_statistics()
        assert stats["l1_entries"] <= 3
