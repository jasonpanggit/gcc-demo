"""
Unified Inventory Cache - Handles both software and OS inventory with memory + PostgreSQL persistence
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

try:
    from utils.pg_client import postgres_client
except ImportError:
    from app.agentic.eol.utils.pg_client import postgres_client

logger = logging.getLogger(__name__)


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

    async def store_cached_data_async(self, cache_key: str, data: List[Dict], cache_type: str = "software", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Async version: Store inventory data in memory cache and PostgreSQL (for OS data).

        Args:
            cache_key: Unique identifier for the cached data
            data: Inventory data to cache
            cache_type: Type of cache ("software" or "os")
            metadata: Optional metadata to store with the cache entry

        Returns:
            True if successfully stored, False otherwise
        """
        logger.debug("store_cached_data_async: cache_type=%s, data_count=%d", cache_type, len(data) if data else 0)

        # Store in memory first
        self.store_cached_data(cache_key, data, cache_type, metadata)

        # For OS data, also persist to PostgreSQL os_inventory_snapshots table
        if cache_type == "os" and data:
            try:
                logger.debug("store_cached_data_async: persisting %d OS records to PostgreSQL", len(data))
                await self._persist_os_inventory_to_postgres(data, metadata)
            except Exception as e:
                # Log but don't fail - memory cache still works
                logger.warning("Failed to persist OS inventory to PostgreSQL: %s", e)

        return True

    def store_cached_data(self, cache_key: str, data: List[Dict], cache_type: str = "software", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store inventory data in memory cache (sync version for backward compatibility).

        For OS data persistence to PostgreSQL, use store_cached_data_async() instead.

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

    async def _persist_os_inventory_to_postgres(self, os_data: List[Dict], metadata: Optional[Dict[str, Any]]):
        """Persist OS inventory data to os_inventory_snapshots table for database joins."""
        logger.debug("[PERSIST] Entry: os_data count=%d, metadata=%s", len(os_data) if os_data else 0, metadata)

        try:
            pool = postgres_client.pool
            logger.debug("[PERSIST] Pool check: pool=%s", "available" if pool else "None")

            if not pool:
                logger.warning("[PERSIST] PostgreSQL pool not available for OS inventory persistence")
                return

            workspace_id = metadata.get("workspace_id", "default") if metadata else "default"
            logger.debug("[PERSIST] workspace_id=%s", workspace_id)

            persisted_count = 0
            skipped_count = 0
            skipped_details = []

            logger.debug("[PERSIST] Acquiring connection from pool...")
            async with pool.acquire() as conn:
                logger.debug("[PERSIST] Connection acquired, starting transaction")

                # Start transaction
                async with conn.transaction():
                    for idx, item in enumerate(os_data):
                        resource_id = item.get("resource_id")
                        logger.debug("[PERSIST] Processing item %d/%d: resource_id=%s", idx + 1, len(os_data), resource_id)

                        if not resource_id:
                            logger.debug("[PERSIST] Item %d has no resource_id, skipping", idx + 1)
                            skipped_count += 1
                            skipped_details.append(f"Item {idx+1}: no resource_id")
                            continue

                        # Check if VM exists in vms table first
                        logger.debug("[PERSIST] Checking FK: SELECT 1 FROM vms WHERE resource_id=%s", resource_id)
                        vm_exists = await conn.fetchval(
                            "SELECT 1 FROM vms WHERE resource_id = $1 LIMIT 1",
                            resource_id
                        )
                        logger.debug("[PERSIST] VM FK check result: vm_exists=%s", vm_exists)

                        if not vm_exists:
                            # Skip if VM not in vms table (FK constraint would fail)
                            skipped_count += 1
                            skipped_details.append(f"{resource_id}: not in vms table")
                            logger.debug("[PERSIST] Skipping %s: VM not found in vms table", resource_id)
                            continue

                        # Prepare values for upsert
                        computer_name = item.get("computer_name") or item.get("computer")
                        os_name = item.get("os_name") or item.get("name")
                        os_version = item.get("os_version") or item.get("version")
                        os_type = item.get("os_type")
                        last_heartbeat_raw = item.get("last_heartbeat")

                        # Parse last_heartbeat if it's a string
                        last_heartbeat = None
                        if last_heartbeat_raw:
                            if isinstance(last_heartbeat_raw, str):
                                try:
                                    last_heartbeat = datetime.fromisoformat(last_heartbeat_raw.replace('Z', '+00:00'))
                                except Exception as e:
                                    logger.warning("[PERSIST] Failed to parse last_heartbeat '%s': %s", last_heartbeat_raw, e)
                            else:
                                last_heartbeat = last_heartbeat_raw

                        logger.debug("[PERSIST] Upserting: computer=%s, os=%s, version=%s, type=%s", computer_name, os_name, os_version, os_type)

                        # Upsert into os_inventory_snapshots
                        # Schema from migration 030: PK is (resource_id, snapshot_version, workspace_id)
                        await conn.execute("""
                            INSERT INTO os_inventory_snapshots (
                                resource_id,
                                workspace_id,
                                computer_name,
                                os_name,
                                os_version,
                                os_type,
                                last_heartbeat,
                                cached_at,
                                ttl_seconds
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), 14400)
                            ON CONFLICT (resource_id, snapshot_version, workspace_id)
                            DO UPDATE SET
                                computer_name = EXCLUDED.computer_name,
                                os_name = EXCLUDED.os_name,
                                os_version = EXCLUDED.os_version,
                                os_type = EXCLUDED.os_type,
                                last_heartbeat = EXCLUDED.last_heartbeat,
                                cached_at = EXCLUDED.cached_at
                        """,
                            resource_id,
                            workspace_id,
                            computer_name,
                            os_name,
                            os_version,
                            os_type,
                            last_heartbeat
                        )
                        persisted_count += 1
                        logger.debug("[PERSIST] Successfully upserted item %d/%d", idx + 1, len(os_data))

            logger.info("[PERSIST] Transaction committed: %d records persisted, %d skipped", persisted_count, skipped_count)
            if skipped_details:
                logger.debug("[PERSIST] Skip details: %s", skipped_details)

        except Exception as e:
            logger.error("[PERSIST] Error persisting OS inventory to PostgreSQL: %s", e, exc_info=True)

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
