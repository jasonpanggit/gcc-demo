"""
Unified Inventory Cache - Handles both software and OS inventory with memory-only persistence
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


class InventoryRawCache:
    """
    Unified cache for inventory data (software and OS) with memory-only persistence.
    Supports separate namespaces for different cache types with 4-hour cache duration.
    """

    def __init__(self, cache_duration_hours: int = 4):
        """
        Initialize the unified inventory cache.

        Args:
            cache_duration_hours: Cache duration in hours (default: 4 hours)
        """
        self.cache_duration = timedelta(hours=cache_duration_hours)

        # Memory cache for frequently accessed data
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

        # Container mappings for different cache types
        self.container_mapping = {
            "software": "inventory_software",
            "os": "inventory_os"
        }

    async def initialize(self):
        """
        Initialize the inventory cache. No-op for memory-only cache.
        """
        pass

    def _get_container_name(self, cache_type: str) -> str:
        """Get the appropriate container name for the cache type."""
        return self.container_mapping.get(cache_type, f"inventory_{cache_type}")

    def _get_memory_key(self, cache_type: str, cache_key: str) -> str:
        """Generate memory cache key combining cache type and key."""
        return f"{cache_type}:{cache_key}"

    def _is_cache_valid(self, timestamp_str: str) -> bool:
        """Check if cache entry is still valid based on timestamp."""
        try:
            cache_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            current_time = datetime.now(cache_time.tzinfo) if cache_time.tzinfo else datetime.now()
            return current_time - cache_time < self.cache_duration
        except Exception as e:
            return False

    def get_cached_data(self, cache_key: str, cache_type: str = "software") -> Optional[List[Dict]]:
        """
        Retrieve cached inventory data from memory.

        Args:
            cache_key: Unique identifier for the cached data
            cache_type: Type of cache ("software" or "os")

        Returns:
            Cached data if valid, None otherwise
        """
        result = self.get_cached_data_with_metadata(cache_key, cache_type)
        return result['data'] if result else None

    def get_cached_data_with_metadata(self, cache_key: str, cache_type: str = "software") -> Optional[Dict]:
        """
        Retrieve cached inventory data with metadata including timestamp.

        Args:
            cache_key: Unique identifier for the cached data
            cache_type: Type of cache ("software" or "os")

        Returns:
            Dict with 'data' and 'timestamp' if valid, None otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)

        # Check memory cache
        if memory_key in self._memory_cache:
            memory_entry = self._memory_cache[memory_key]
            if self._is_cache_valid(memory_entry['timestamp']):
                return {
                    'data': memory_entry['data'],
                    'timestamp': memory_entry['timestamp'],
                    'metadata': memory_entry.get('metadata')
                }
            else:
                del self._memory_cache[memory_key]

        return None

    def store_cached_data(self, cache_key: str, data: List[Dict], cache_type: str = "software", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store inventory data in memory cache.

        Args:
            cache_key: Unique identifier for the cached data
            data: Inventory data to cache
            cache_type: Type of cache ("software" or "os")
            metadata: Optional metadata to store with the cache entry

        Returns:
            True if successfully stored, False otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)
        timestamp = datetime.now().isoformat()

        # Store in memory cache
        self._memory_cache[memory_key] = {
            'data': data,
            'timestamp': timestamp,
            'metadata': metadata
        }

        return True

    def clear_cache(self, cache_key: str, cache_type: str = "software") -> bool:
        """
        Clear cached data from memory.

        Args:
            cache_key: Unique identifier for the cached data to clear
            cache_type: Type of cache ("software" or "os")

        Returns:
            True if successfully cleared, False otherwise
        """
        memory_key = self._get_memory_key(cache_type, cache_key)

        # Clear from memory cache
        if memory_key in self._memory_cache:
            del self._memory_cache[memory_key]

        return True

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring and debugging.

        Returns:
            Dictionary with cache statistics
        """
        memory_stats = {}
        for cache_type in self.container_mapping.keys():
            type_entries = [k for k in self._memory_cache.keys() if k.startswith(f"{cache_type}:")]
            memory_stats[cache_type] = len(type_entries)

        return {
            'memory_cache_entries': memory_stats,
            'total_memory_entries': len(self._memory_cache),
            'cache_duration_hours': self.cache_duration.total_seconds() / 3600,
            'supported_cache_types': list(self.container_mapping.keys()),
            'storage': 'memory_only'
        }

    async def clear_all_cache(self, cache_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear cache entries for specified type or all types.

        Args:
            cache_type: "software", "os", or None for all

        Returns:
            Dictionary with operation results
        """
        if cache_type:
            types_to_clear = [cache_type]
        else:
            types_to_clear = list(self.container_mapping.keys())

        cleared_count = 0

        # Clear memory cache
        keys_to_remove = []
        for key in list(self._memory_cache.keys()):
            for ct in types_to_clear:
                if key.startswith(f"{ct}:"):
                    keys_to_remove.append(key)
                    break

        for key in keys_to_remove:
            del self._memory_cache[key]
            cleared_count += 1

        return {
            "success": True,
            "cleared_count": cleared_count,
            "cache_types": types_to_clear,
            "message": f"Cleared {cleared_count} cache entries"
        }


# Create module-level instance
inventory_cache = InventoryRawCache()
