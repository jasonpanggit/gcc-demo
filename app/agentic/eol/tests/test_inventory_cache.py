"""
Inventory Cache Tests

Tests for unified inventory cache with memory + Cosmos DB persistence.
Created: 2026-02-27 (Phase 3, Week 3, Day 1)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


class TestInventoryCacheInitialization:
    """Tests for InventoryRawCache initialization."""

    def test_inventory_cache_imports(self):
        """Test inventory cache can be imported."""
        from utils.inventory_cache import InventoryRawCache

        assert InventoryRawCache is not None

    def test_inventory_cache_initialization(self):
        """Test inventory cache initializes correctly."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos, cache_duration_hours=4)

        assert cache.cosmos_client == mock_cosmos
        assert cache.cache_duration == timedelta(hours=4)
        assert isinstance(cache._memory_cache, dict)
        assert len(cache._memory_cache) == 0

    def test_inventory_cache_default_duration(self):
        """Test inventory cache uses default 4-hour duration."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        assert cache.cache_duration == timedelta(hours=4)

    def test_inventory_cache_custom_duration(self):
        """Test inventory cache accepts custom duration."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos, cache_duration_hours=8)

        assert cache.cache_duration == timedelta(hours=8)

    def test_container_mapping_exists(self):
        """Test inventory cache has container mappings."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        assert "software" in cache.container_mapping
        assert "os" in cache.container_mapping
        assert cache.container_mapping["software"] == "inventory_software"
        assert cache.container_mapping["os"] == "inventory_os"


class TestInventoryCacheHelperMethods:
    """Tests for inventory cache helper methods."""

    def test_get_container_name_software(self):
        """Test _get_container_name returns correct container for software."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        container_name = cache._get_container_name("software")
        assert container_name == "inventory_software"

    def test_get_container_name_os(self):
        """Test _get_container_name returns correct container for os."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        container_name = cache._get_container_name("os")
        assert container_name == "inventory_os"

    def test_get_container_name_unknown(self):
        """Test _get_container_name handles unknown cache type."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        container_name = cache._get_container_name("custom")
        assert container_name == "inventory_custom"

    def test_get_memory_key(self):
        """Test _get_memory_key generates correct composite key."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        key = cache._get_memory_key("software", "cache-123")
        assert key == "software:cache-123"

    def test_is_cache_valid_fresh(self):
        """Test _is_cache_valid returns True for fresh cache."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos, cache_duration_hours=4)

        # Create fresh timestamp (1 hour ago)
        fresh_time = datetime.now() - timedelta(hours=1)
        timestamp_str = fresh_time.isoformat()

        assert cache._is_cache_valid(timestamp_str) is True

    def test_is_cache_valid_expired(self):
        """Test _is_cache_valid returns False for expired cache."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos, cache_duration_hours=4)

        # Create expired timestamp (5 hours ago)
        expired_time = datetime.now() - timedelta(hours=5)
        timestamp_str = expired_time.isoformat()

        assert cache._is_cache_valid(timestamp_str) is False

    def test_is_cache_valid_invalid_timestamp(self):
        """Test _is_cache_valid handles invalid timestamp."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        assert cache._is_cache_valid("invalid-timestamp") is False


@pytest.mark.asyncio
class TestInventoryCacheOperations:
    """Tests for inventory cache operations."""

    async def test_initialize_with_cosmos_available(self):
        """Test initialize when Cosmos DB is available."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        mock_cosmos.initialized = False
        mock_cosmos._initialize_async = AsyncMock()

        cache = InventoryRawCache(mock_cosmos)
        await cache.initialize()

        mock_cosmos._initialize_async.assert_called_once()

    async def test_initialize_with_cosmos_already_initialized(self):
        """Test initialize when Cosmos DB already initialized."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        mock_cosmos.initialized = True
        mock_cosmos._initialize_async = AsyncMock()

        cache = InventoryRawCache(mock_cosmos)
        await cache.initialize()

        # Should not call initialize again
        mock_cosmos._initialize_async.assert_not_called()

    def test_get_cached_data_memory_hit(self):
        """Test get_cached_data returns data from memory cache."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        # Populate memory cache
        memory_key = cache._get_memory_key("software", "test-key")
        cache._memory_cache[memory_key] = {
            "data": [{"software": "Test Software"}],
            "timestamp": datetime.now().isoformat()
        }

        # Get cached data
        result = cache.get_cached_data("test-key", "software")

        assert result is not None
        assert len(result) == 1
        assert result[0]["software"] == "Test Software"

    def test_get_cached_data_memory_miss(self):
        """Test get_cached_data returns None on memory miss."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos)

        # Don't populate cache
        result = cache.get_cached_data("missing-key", "software")

        # Should return None when not found
        assert result is None

    def test_get_cached_data_expired(self):
        """Test get_cached_data returns None for expired cache."""
        from utils.inventory_cache import InventoryRawCache

        mock_cosmos = MagicMock()
        cache = InventoryRawCache(mock_cosmos, cache_duration_hours=4)

        # Populate with expired data
        memory_key = cache._get_memory_key("software", "test-key")
        expired_time = datetime.now() - timedelta(hours=5)
        cache._memory_cache[memory_key] = {
            "data": [{"software": "Old Software"}],
            "timestamp": expired_time.isoformat()
        }

        result = cache.get_cached_data("test-key", "software")

        # Should return None for expired cache
        assert result is None


class TestInventoryCacheModule:
    """Tests for inventory cache module structure."""

    def test_module_imports(self):
        """Test inventory cache module imports."""
        from utils import inventory_cache

        assert hasattr(inventory_cache, 'InventoryRawCache')
        assert hasattr(inventory_cache, 'datetime')
        assert hasattr(inventory_cache, 'timedelta')

    def test_cosmos_exceptions_handling(self):
        """Test module handles missing Cosmos SDK."""
        from utils import inventory_cache

        # Module should have exception handling
        assert hasattr(inventory_cache, 'COSMOS_EXCEPTIONS_AVAILABLE')
        assert isinstance(inventory_cache.COSMOS_EXCEPTIONS_AVAILABLE, bool)
