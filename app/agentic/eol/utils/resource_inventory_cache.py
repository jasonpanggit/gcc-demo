"""
Resource Inventory Cache - Dual-layer caching for Azure resource inventory data.

Provides L1 (in-memory) + L2 (Cosmos DB) caching with per-resource-type TTL
overrides to minimise redundant Azure Resource Graph / ARM API calls.

Cache key format: resource_inv:{subscription_id}:{resource_type}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .cosmos_cache import base_cosmos

try:
    from azure.cosmos.exceptions import CosmosResourceNotFoundError
    COSMOS_EXCEPTIONS_OK = True
except ImportError:
    CosmosResourceNotFoundError = None  # type: ignore[misc]
    COSMOS_EXCEPTIONS_OK = False

try:
    from .cache_stats_manager import cache_stats_manager
except ImportError:
    cache_stats_manager = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-resource-type TTL overrides (seconds)
# ---------------------------------------------------------------------------
TTL_OVERRIDES: Dict[str, int] = {
    # Compute – changes frequently (scaling, restarts)
    "Microsoft.Compute/virtualMachines": 1800,          # 30 min
    "Microsoft.Compute/virtualMachineScaleSets": 1800,  # 30 min
    # Networking – relatively stable
    "Microsoft.Network/virtualNetworks": 86400,         # 24 hr
    "Microsoft.Network/networkSecurityGroups": 86400,   # 24 hr
    "Microsoft.Network/loadBalancers": 3600,            # 1 hr
    "Microsoft.Network/publicIPAddresses": 3600,        # 1 hr
    "Microsoft.Network/applicationGateways": 3600,      # 1 hr
    # Storage
    "Microsoft.Storage/storageAccounts": 3600,          # 1 hr
    # Web / App Service
    "Microsoft.Web/sites": 1800,                        # 30 min
    "Microsoft.Web/serverFarms": 3600,                  # 1 hr
    # Containers
    "Microsoft.ContainerService/managedClusters": 1800, # 30 min
    "Microsoft.App/containerApps": 1800,                # 30 min
    # Databases
    "Microsoft.Sql/servers": 3600,                      # 1 hr
    "Microsoft.DocumentDB/databaseAccounts": 3600,      # 1 hr
    # Key Vault
    "Microsoft.KeyVault/vaults": 3600,                  # 1 hr
}

# Default TTLs when no override is specified
DEFAULT_L1_TTL = 300      # 5 minutes
DEFAULT_L2_TTL = 3600     # 1 hour

# Cosmos DB container for L2 persistence
COSMOS_CONTAINER_ID = "resource_inventory"


# ---------------------------------------------------------------------------
# L1 entry helper
# ---------------------------------------------------------------------------
class _L1Entry:
    """Lightweight in-memory cache entry with expiry tracking."""

    __slots__ = ("data", "created_at", "expires_at")

    def __init__(self, data: List[Dict[str, Any]], ttl: int) -> None:
        now = time.time()
        self.data = data
        self.created_at = now
        self.expires_at = now + ttl

    @property
    def is_valid(self) -> bool:
        return time.time() < self.expires_at


# ---------------------------------------------------------------------------
# ResourceInventoryCache
# ---------------------------------------------------------------------------
class ResourceInventoryCache:
    """Dual-layer cache (L1 in-memory, L2 Cosmos DB) for Azure resource inventory.

    Features:
        - Per-resource-type TTL overrides
        - Automatic L1 → L2 fallback on miss
        - Batch retrieval across subscriptions
        - Statistics tracking (hit rate, miss rate)
    """

    def __init__(
        self,
        default_l1_ttl: int = DEFAULT_L1_TTL,
        default_l2_ttl: int = DEFAULT_L2_TTL,
        max_l1_entries: int = 500,
    ) -> None:
        self._default_l1_ttl = default_l1_ttl
        self._default_l2_ttl = default_l2_ttl
        self._max_l1_entries = max_l1_entries

        # L1 – in-memory store
        self._l1: Dict[str, _L1Entry] = {}
        self._l1_lock = threading.RLock()

        # L2 – Cosmos DB (lazy initialised)
        self._l2_container: Any = None
        self._l2_ready = False

        # Statistics
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0
        self._writes = 0

    # ---- key helpers -------------------------------------------------------

    @staticmethod
    def _cache_key(subscription_id: str, resource_type: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """Build a deterministic cache key.

        Format: ``resource_inv:{subscription_id}:{resource_type}[:filter_hash]``
        """
        base = f"resource_inv:{subscription_id}:{resource_type}"
        if filters:
            sorted_filters = json.dumps(filters, sort_keys=True, default=str)
            fhash = hashlib.md5(sorted_filters.encode()).hexdigest()[:10]
            return f"{base}:{fhash}"
        return base

    def _ttl_for(self, resource_type: str, layer: str = "l1") -> int:
        """Return TTL in seconds for a resource type and cache layer."""
        override = TTL_OVERRIDES.get(resource_type)
        if override is not None:
            # L1 gets a shorter slice of the override to keep memory fresh
            return min(override, self._default_l1_ttl) if layer == "l1" else override
        return self._default_l1_ttl if layer == "l1" else self._default_l2_ttl

    # ---- L2 (Cosmos) helpers -----------------------------------------------

    def _ensure_l2(self) -> bool:
        """Lazily initialise the L2 Cosmos DB container."""
        if self._l2_ready and self._l2_container is not None:
            return True
        if not base_cosmos.initialized:
            try:
                base_cosmos._ensure_initialized()
            except Exception:
                pass
        if not base_cosmos.initialized:
            return False
        try:
            self._l2_container = base_cosmos.get_container(
                container_id=COSMOS_CONTAINER_ID,
                partition_path="/cache_key",
                default_ttl=self._default_l2_ttl,
            )
            self._l2_ready = True
            logger.info("L2 Cosmos container '%s' ready", COSMOS_CONTAINER_ID)
            return True
        except Exception as exc:
            logger.warning("Failed to initialise L2 container: %s", exc)
            return False

    # ---- L1 eviction -------------------------------------------------------

    def _evict_l1_expired(self) -> int:
        """Remove expired L1 entries. Must be called under ``_l1_lock``."""
        expired = [k for k, v in self._l1.items() if not v.is_valid]
        for k in expired:
            del self._l1[k]
        return len(expired)

    def _evict_l1_oldest(self, count: int = 50) -> None:
        """Remove oldest L1 entries by creation time. Must be called under ``_l1_lock``."""
        sorted_keys = sorted(self._l1, key=lambda k: self._l1[k].created_at)
        for k in sorted_keys[:count]:
            del self._l1[k]

    # ---- public API --------------------------------------------------------

    async def get(
        self,
        subscription_id: str,
        resource_type: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached resources.  Checks L1 first, falls back to L2.

        Returns ``None`` on a full miss (both layers).
        """
        key = self._cache_key(subscription_id, resource_type, filters)
        start = time.time()

        # -- L1 lookup -------------------------------------------------------
        with self._l1_lock:
            entry = self._l1.get(key)
            if entry is not None:
                if entry.is_valid:
                    self._hits_l1 += 1
                    self._record_stats(time.time() - start, hit_layer="l1")
                    logger.debug("L1 HIT  key=%s (%d resources)", key[:60], len(entry.data))
                    return entry.data
                else:
                    del self._l1[key]

        # -- L2 lookup -------------------------------------------------------
        if not self._ensure_l2():
            self._misses += 1
            self._record_stats(time.time() - start, hit_layer=None)
            return None

        try:
            query = "SELECT * FROM c WHERE c.cache_key = @key"
            params = [{"name": "@key", "value": key}]
            items = list(
                self._l2_container.query_items(
                    query=query, parameters=params, enable_cross_partition_query=True
                )
            )
            if items:
                doc = items[0]
                resources: List[Dict[str, Any]] = doc.get("resources", [])
                # Promote to L1
                l1_ttl = self._ttl_for(resource_type, "l1")
                with self._l1_lock:
                    self._l1[key] = _L1Entry(resources, l1_ttl)
                self._hits_l2 += 1
                self._record_stats(time.time() - start, hit_layer="l2")
                logger.debug("L2 HIT  key=%s (%d resources)", key[:60], len(resources))
                return resources
        except Exception as exc:
            logger.warning("L2 read error for key=%s: %s", key[:60], exc)

        self._misses += 1
        self._record_stats(time.time() - start, hit_layer=None)
        return None

    async def set(
        self,
        subscription_id: str,
        resource_type: str,
        resources: List[Dict[str, Any]],
        filters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write resources to both L1 and L2.

        Returns ``True`` if at least L1 succeeded.
        """
        key = self._cache_key(subscription_id, resource_type, filters)
        l1_ttl = self._ttl_for(resource_type, "l1")
        l2_ttl = self._ttl_for(resource_type, "l2")

        # -- L1 write --------------------------------------------------------
        with self._l1_lock:
            # Evict if capacity reached
            if len(self._l1) >= self._max_l1_entries:
                self._evict_l1_expired()
                if len(self._l1) >= self._max_l1_entries:
                    self._evict_l1_oldest(self._max_l1_entries // 10)
            self._l1[key] = _L1Entry(resources, l1_ttl)

        self._writes += 1

        # -- L2 write --------------------------------------------------------
        if self._ensure_l2():
            now_iso = datetime.now(timezone.utc).isoformat()
            doc = {
                "id": hashlib.md5(key.encode()).hexdigest(),
                "cache_key": key,
                "subscription_id": subscription_id,
                "resource_type": resource_type,
                "resources": resources,
                "resource_count": len(resources),
                "created_at": now_iso,
                "ttl": l2_ttl,
            }
            try:
                self._l2_container.upsert_item(doc)
                logger.debug("L2 WRITE key=%s (%d resources, ttl=%ds)", key[:60], len(resources), l2_ttl)
            except Exception as exc:
                logger.warning("L2 write error for key=%s: %s", key[:60], exc)

        return True

    async def get_multi(
        self,
        subscription_ids: List[str],
        resource_type: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[List[Dict[str, Any]]]]:
        """Batch retrieval across multiple subscriptions.

        Returns a dict mapping each subscription_id to its cached resources
        (``None`` for misses).
        """
        results: Dict[str, Optional[List[Dict[str, Any]]]] = {}
        # Fire all lookups concurrently
        tasks = {
            sid: asyncio.ensure_future(self.get(sid, resource_type, filters))
            for sid in subscription_ids
        }
        for sid, task in tasks.items():
            try:
                results[sid] = await task
            except Exception:
                results[sid] = None
        return results

    async def invalidate(
        self,
        subscription_id: str,
        resource_type: Optional[str] = None,
    ) -> int:
        """Clear cache entries for a subscription (optionally scoped to a resource type).

        Returns the number of L1 entries removed.
        """
        prefix = f"resource_inv:{subscription_id}"
        if resource_type:
            prefix = f"{prefix}:{resource_type}"

        removed = 0

        # -- L1 invalidation -------------------------------------------------
        with self._l1_lock:
            keys_to_remove = [k for k in self._l1 if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._l1[k]
            removed = len(keys_to_remove)

        # -- L2 invalidation -------------------------------------------------
        if self._ensure_l2():
            try:
                query = "SELECT c.id, c.cache_key FROM c WHERE STARTSWITH(c.cache_key, @prefix)"
                params = [{"name": "@prefix", "value": prefix}]
                items = list(
                    self._l2_container.query_items(
                        query=query, parameters=params, enable_cross_partition_query=True
                    )
                )
                for item in items:
                    try:
                        self._l2_container.delete_item(item=item["id"], partition_key=item["cache_key"])
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("L2 invalidation error for prefix=%s: %s", prefix, exc)

        logger.debug("Invalidated %d L1 entries for prefix=%s", removed, prefix)
        return removed

    # ---- statistics --------------------------------------------------------

    def _record_stats(self, elapsed: float, hit_layer: Optional[str]) -> None:
        """Push lightweight stats to the global CacheStatsManager if available."""
        if cache_stats_manager is None:
            return
        try:
            cache_stats_manager.record_inventory_request(
                response_time_ms=elapsed * 1000,
                was_cache_hit=hit_layer is not None,
            )
        except Exception:
            pass

    def get_statistics(self) -> Dict[str, Any]:
        """Return cache hit/miss statistics."""
        total = self._hits_l1 + self._hits_l2 + self._misses
        with self._l1_lock:
            l1_entries = len(self._l1)
            l1_valid = sum(1 for e in self._l1.values() if e.is_valid)

        return {
            "l1_entries": l1_entries,
            "l1_valid_entries": l1_valid,
            "l1_max_entries": self._max_l1_entries,
            "l2_ready": self._l2_ready,
            "hits_l1": self._hits_l1,
            "hits_l2": self._hits_l2,
            "misses": self._misses,
            "total_requests": total,
            "writes": self._writes,
            "hit_rate_percent": round((self._hits_l1 + self._hits_l2) / total * 100, 1) if total else 0.0,
            "l1_hit_rate_percent": round(self._hits_l1 / total * 100, 1) if total else 0.0,
            "l2_hit_rate_percent": round(self._hits_l2 / total * 100, 1) if total else 0.0,
            "miss_rate_percent": round(self._misses / total * 100, 1) if total else 0.0,
            "ttl_overrides": dict(TTL_OVERRIDES),
            "default_l1_ttl": self._default_l1_ttl,
            "default_l2_ttl": self._default_l2_ttl,
        }

    def clear_all(self) -> int:
        """Clear all L1 entries and return the count removed."""
        with self._l1_lock:
            count = len(self._l1)
            self._l1.clear()
        self._hits_l1 = 0
        self._hits_l2 = 0
        self._misses = 0
        self._writes = 0
        logger.info("ResourceInventoryCache cleared (%d L1 entries removed)", count)
        return count


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_instance: Optional[ResourceInventoryCache] = None
_instance_lock = threading.Lock()


def get_resource_inventory_cache() -> ResourceInventoryCache:
    """Get or create the ResourceInventoryCache singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResourceInventoryCache()
    return _instance
