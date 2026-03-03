"""
Resource Inventory Cache Tests

Tests for dual-layer (L1 memory + L2 Cosmos) Azure resource inventory cache.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import time


class TestL1Entry:
    """Tests for _L1Entry helper class."""

    def test_l1_entry_imports(self):
        """Test _L1Entry can be imported."""
        from utils.resource_inventory_cache import _L1Entry

        assert _L1Entry is not None

    def test_l1_entry_creation(self):
        """Test _L1Entry creates with data and TTL."""
        from utils.resource_inventory_cache import _L1Entry

        data = [{"id": "resource-1", "type": "VM"}]
        entry = _L1Entry(data, ttl=300)

        assert entry.data == data
        assert hasattr(entry, 'created_at')
        assert hasattr(entry, 'expires_at')
        assert isinstance(entry.created_at, float)
        assert isinstance(entry.expires_at, float)

    def test_l1_entry_is_valid_fresh(self):
        """Test is_valid returns True for fresh entry."""
        from utils.resource_inventory_cache import _L1Entry

        entry = _L1Entry([{"id": "test"}], ttl=300)

        assert entry.is_valid is True

    def test_l1_entry_is_valid_expired(self):
        """Test is_valid returns False for expired entry."""
        from utils.resource_inventory_cache import _L1Entry

        # Create entry with very short TTL
        entry = _L1Entry([{"id": "test"}], ttl=0)

        # Wait a moment
        time.sleep(0.01)

        assert entry.is_valid is False

    def test_l1_entry_slots(self):
        """Test _L1Entry uses __slots__ for memory efficiency."""
        from utils.resource_inventory_cache import _L1Entry

        assert hasattr(_L1Entry, '__slots__')
        assert 'data' in _L1Entry.__slots__
        assert 'created_at' in _L1Entry.__slots__
        assert 'expires_at' in _L1Entry.__slots__


class TestResourceInventoryCacheInitialization:
    """Tests for ResourceInventoryCache initialization."""

    def test_resource_inventory_cache_imports(self):
        """Test ResourceInventoryCache can be imported."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        assert ResourceInventoryCache is not None

    def test_resource_inventory_cache_default_initialization(self):
        """Test ResourceInventoryCache initializes with defaults."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        assert cache._default_l1_ttl == 300  # 5 minutes
        assert cache._default_l2_ttl == 3600  # 1 hour
        assert cache._max_l1_entries == 500
        assert len(cache._l1) == 0
        assert cache._l2_ready is False
        assert cache._hits_l1 == 0
        assert cache._hits_l2 == 0
        assert cache._misses == 0
        assert cache._writes == 0

    def test_resource_inventory_cache_custom_initialization(self):
        """Test ResourceInventoryCache accepts custom parameters."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache(
            default_l1_ttl=600,
            default_l2_ttl=7200,
            max_l1_entries=1000
        )

        assert cache._default_l1_ttl == 600
        assert cache._default_l2_ttl == 7200
        assert cache._max_l1_entries == 1000

    def test_resource_inventory_cache_has_locks(self):
        """Test ResourceInventoryCache has threading lock."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        assert hasattr(cache, '_l1_lock')
        # Lock exists - type check is sufficient
        assert cache._l1_lock is not None


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_cache_key_basic(self):
        """Test _cache_key generates correct format."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        key = ResourceInventoryCache._cache_key(
            "sub-123",
            "Microsoft.Compute/virtualMachines"
        )

        assert key.startswith("resource_inv:")
        assert "sub-123" in key
        assert "Microsoft.Compute/virtualMachines" in key

    def test_cache_key_with_filters(self):
        """Test _cache_key includes filter hash when provided."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        key = ResourceInventoryCache._cache_key(
            "sub-123",
            "Microsoft.Compute/virtualMachines",
            filters={"location": "eastus"}
        )

        assert key.startswith("resource_inv:")
        # Should have filter hash appended
        assert key.count(":") == 3

    def test_cache_key_filter_order_independent(self):
        """Test _cache_key is order-independent for filters."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        key1 = ResourceInventoryCache._cache_key(
            "sub-123",
            "Microsoft.Compute/virtualMachines",
            filters={"location": "eastus", "tags": {"env": "prod"}}
        )

        key2 = ResourceInventoryCache._cache_key(
            "sub-123",
            "Microsoft.Compute/virtualMachines",
            filters={"tags": {"env": "prod"}, "location": "eastus"}
        )

        assert key1 == key2


class TestTTLOverrides:
    """Tests for per-resource-type TTL overrides."""

    def test_ttl_overrides_exist(self):
        """Test TTL_OVERRIDES constant exists."""
        from utils.resource_inventory_cache import TTL_OVERRIDES

        assert isinstance(TTL_OVERRIDES, dict)
        assert len(TTL_OVERRIDES) > 0

    def test_ttl_for_vm_override(self):
        """Test _ttl_for returns VM-specific TTL."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        ttl = cache._ttl_for("Microsoft.Compute/virtualMachines", layer="l2")

        # VMs have 1800 second TTL override
        assert ttl == 1800

    def test_ttl_for_vnet_override(self):
        """Test _ttl_for returns VNet-specific TTL."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        ttl = cache._ttl_for("Microsoft.Network/virtualNetworks", layer="l2")

        # VNets have 86400 second (24 hr) TTL
        assert ttl == 86400

    def test_ttl_for_unknown_resource_type(self):
        """Test _ttl_for returns default for unknown types."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        ttl_l1 = cache._ttl_for("Microsoft.Unknown/resources", layer="l1")
        ttl_l2 = cache._ttl_for("Microsoft.Unknown/resources", layer="l2")

        assert ttl_l1 == 300  # default L1
        assert ttl_l2 == 3600  # default L2

    def test_ttl_for_l1_shorter_than_l2(self):
        """Test L1 TTL is shorter or equal to L2 TTL."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        for resource_type in ["Microsoft.Compute/virtualMachines",
                             "Microsoft.Network/virtualNetworks",
                             "Microsoft.Storage/storageAccounts"]:
            ttl_l1 = cache._ttl_for(resource_type, layer="l1")
            ttl_l2 = cache._ttl_for(resource_type, layer="l2")

            assert ttl_l1 <= ttl_l2


class TestL1Eviction:
    """Tests for L1 cache eviction."""

    def test_evict_l1_expired(self):
        """Test _evict_l1_expired removes expired entries."""
        from utils.resource_inventory_cache import ResourceInventoryCache, _L1Entry

        cache = ResourceInventoryCache()

        # Add expired entry
        cache._l1["expired-key"] = _L1Entry([{"id": "test"}], ttl=0)
        time.sleep(0.01)

        # Add fresh entry
        cache._l1["fresh-key"] = _L1Entry([{"id": "test"}], ttl=300)

        count = cache._evict_l1_expired()

        assert count == 1
        assert "expired-key" not in cache._l1
        assert "fresh-key" in cache._l1

    def test_evict_l1_oldest(self):
        """Test _evict_l1_oldest removes oldest entries."""
        from utils.resource_inventory_cache import ResourceInventoryCache, _L1Entry

        cache = ResourceInventoryCache()

        # Add entries with small delays
        cache._l1["old-key"] = _L1Entry([{"id": "old"}], ttl=300)
        time.sleep(0.01)
        cache._l1["new-key"] = _L1Entry([{"id": "new"}], ttl=300)

        cache._evict_l1_oldest(count=1)

        # Oldest should be removed
        assert "old-key" not in cache._l1
        assert "new-key" in cache._l1


class TestL2CosmosInitialization:
    """Tests for L2 Cosmos DB initialization."""

    @patch('utils.resource_inventory_cache.base_cosmos')
    def test_ensure_l2_already_ready(self, mock_cosmos):
        """Test _ensure_l2 returns True when already initialized."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._l2_ready = True
        cache._l2_container = MagicMock()

        result = cache._ensure_l2()

        assert result is True

    @patch('utils.resource_inventory_cache.base_cosmos')
    def test_ensure_l2_cosmos_not_initialized(self, mock_cosmos):
        """Test _ensure_l2 handles Cosmos not initialized."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        mock_cosmos.initialized = False
        mock_cosmos._ensure_initialized.side_effect = Exception("Not configured")

        result = cache._ensure_l2()

        assert result is False
        assert cache._l2_ready is False

    @patch('utils.resource_inventory_cache.base_cosmos')
    def test_ensure_l2_success(self, mock_cosmos):
        """Test _ensure_l2 successfully initializes container."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        mock_cosmos.initialized = True
        mock_container = MagicMock()
        mock_cosmos.get_container.return_value = mock_container

        result = cache._ensure_l2()

        assert result is True
        assert cache._l2_ready is True
        assert cache._l2_container == mock_container
        mock_cosmos.get_container.assert_called_once()


class TestStatistics:
    """Tests for cache statistics."""

    def test_get_statistics_initial(self):
        """Test get_statistics returns initial values."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        stats = cache.get_statistics()

        assert stats["hits_l1"] == 0
        assert stats["hits_l2"] == 0
        assert stats["misses"] == 0
        assert stats["writes"] == 0
        assert stats["l1_entries"] == 0
        assert stats["hit_rate_percent"] == 0.0

    def test_get_statistics_hit_rate_calculation(self):
        """Test get_statistics calculates hit_rate correctly."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()

        # Simulate hits and misses
        cache._hits_l1 = 2
        cache._hits_l2 = 1
        cache._misses = 1

        stats = cache.get_statistics()

        # 3 hits out of 4 total = 75%
        assert abs(stats["hit_rate_percent"] - 75.0) < 0.1

    def test_get_statistics_l1_tracking(self):
        """Test get_statistics tracks L1 entries."""
        from utils.resource_inventory_cache import ResourceInventoryCache, _L1Entry

        cache = ResourceInventoryCache()

        cache._l1["key1"] = _L1Entry([{"id": "1"}], ttl=300)
        cache._l1["key2"] = _L1Entry([{"id": "2"}], ttl=300)

        stats = cache.get_statistics()

        assert stats["l1_entries"] == 2
        assert stats["l1_valid_entries"] == 2


class TestClearOperations:
    """Tests for cache clearing operations."""

    def test_clear_all(self):
        """Test clear_all removes all L1 entries."""
        from utils.resource_inventory_cache import ResourceInventoryCache, _L1Entry

        cache = ResourceInventoryCache()

        cache._l1["key1"] = _L1Entry([{"id": "1"}], ttl=300)
        cache._l1["key2"] = _L1Entry([{"id": "2"}], ttl=300)

        count = cache.clear_all()

        assert count == 2
        assert len(cache._l1) == 0

    def test_clear_all_resets_stats(self):
        """Test clear_all resets all statistics."""
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._hits_l1 = 10
        cache._hits_l2 = 5
        cache._misses = 3

        cache.clear_all()

        # Should reset all stats
        assert cache._hits_l1 == 0
        assert cache._hits_l2 == 0
        assert cache._misses == 0


class TestResourceInventoryCacheModule:
    """Tests for resource_inventory_cache module structure."""

    def test_module_imports(self):
        """Test resource_inventory_cache module imports."""
        from utils import resource_inventory_cache

        assert hasattr(resource_inventory_cache, 'ResourceInventoryCache')
        assert hasattr(resource_inventory_cache, '_L1Entry')
        assert hasattr(resource_inventory_cache, 'TTL_OVERRIDES')
        assert hasattr(resource_inventory_cache, 'DEFAULT_L1_TTL')
        assert hasattr(resource_inventory_cache, 'DEFAULT_L2_TTL')

    def test_ttl_constants(self):
        """Test TTL constants are defined."""
        from utils.resource_inventory_cache import DEFAULT_L1_TTL, DEFAULT_L2_TTL

        assert DEFAULT_L1_TTL == 300  # 5 minutes
        assert DEFAULT_L2_TTL == 3600  # 1 hour

    def test_cosmos_container_constant(self):
        """Test Cosmos container ID constant."""
        from utils.resource_inventory_cache import COSMOS_CONTAINER_ID

        assert COSMOS_CONTAINER_ID == "resource_inventory"

    def test_cosmos_exceptions_flag(self):
        """Test COSMOS_EXCEPTIONS_OK flag exists."""
        from utils.resource_inventory_cache import COSMOS_EXCEPTIONS_OK

        assert isinstance(COSMOS_EXCEPTIONS_OK, bool)

    def test_specific_resource_type_ttls(self):
        """Test specific Azure resource types have TTL overrides."""
        from utils.resource_inventory_cache import TTL_OVERRIDES

        # Verify key resource types have overrides
        assert "Microsoft.Compute/virtualMachines" in TTL_OVERRIDES
        assert "Microsoft.Network/virtualNetworks" in TTL_OVERRIDES
        assert "Microsoft.Storage/storageAccounts" in TTL_OVERRIDES
        assert "Microsoft.Web/sites" in TTL_OVERRIDES
        assert "Microsoft.KeyVault/vaults" in TTL_OVERRIDES

    def test_ttl_override_values_reasonable(self):
        """Test TTL override values are reasonable."""
        from utils.resource_inventory_cache import TTL_OVERRIDES

        for resource_type, ttl in TTL_OVERRIDES.items():
            # All TTLs should be positive and less than 7 days
            assert ttl > 0
            assert ttl <= 604800  # 7 days in seconds
