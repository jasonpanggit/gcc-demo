"""
Resource Inventory Monitoring Metrics

Provides comprehensive monitoring instrumentation for the inventory system:
- Cache performance tracking (L1/L2 hits, misses, hit rates)
- Discovery operation metrics (duration, resource counts, errors)
- API call savings tracking
- Structured logging with metric context
- Dashboard-ready metrics export

Usage:
    from utils.inventory_metrics import get_inventory_metrics
    metrics = get_inventory_metrics()

    # Record cache operations
    metrics.record_cache_hit("l1")
    metrics.record_cache_miss("l2")

    # Record discovery operations
    with metrics.track_discovery("sub-123"):
        # ... discovery logic ...
        pass

    # Get dashboard metrics
    dashboard = metrics.get_dashboard_metrics()
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager, contextmanager
from collections import defaultdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_inventory_metrics_instance: Optional["InventoryMetrics"] = None


def get_inventory_metrics() -> "InventoryMetrics":
    """Get or create the singleton InventoryMetrics instance."""
    global _inventory_metrics_instance
    if _inventory_metrics_instance is None:
        _inventory_metrics_instance = InventoryMetrics()
    return _inventory_metrics_instance


def reset_inventory_metrics() -> None:
    """Reset the singleton (for testing)."""
    global _inventory_metrics_instance
    _inventory_metrics_instance = None


# ---------------------------------------------------------------------------
# InventoryMetrics
# ---------------------------------------------------------------------------
class InventoryMetrics:
    """
    Centralized monitoring metrics collector for the Resource Inventory system.

    Tracks:
    - Cache hit/miss rates per layer (L1 in-memory, L2 Cosmos DB)
    - Discovery operation durations and resource counts
    - API calls saved through caching
    - Query performance by operation type
    - Error counts and types
    - Per-subscription resource counts
    """

    def __init__(self):
        # --- Cache Metrics ---
        self._cache_hits: dict[str, int] = defaultdict(int)         # layer -> count
        self._cache_misses: dict[str, int] = defaultdict(int)       # layer -> count
        self._cache_evictions: dict[str, int] = defaultdict(int)    # layer -> count
        self._cache_sets: dict[str, int] = defaultdict(int)         # layer -> count

        # --- API Savings ---
        self._api_calls_saved: int = 0

        # --- Discovery Metrics ---
        self._discovery_count: int = 0
        self._discovery_errors: int = 0
        self._discovery_durations: list[float] = []  # seconds
        self._discovery_resource_counts: dict[str, int] = defaultdict(int)  # sub_id -> count
        self._last_discovery_time: Optional[datetime] = None
        self._last_discovery_duration: Optional[float] = None
        self._last_discovery_status: Optional[str] = None

        # --- Query Metrics ---
        self._query_count: dict[str, int] = defaultdict(int)        # operation -> count
        self._query_durations: dict[str, list[float]] = defaultdict(list)  # operation -> [durations]
        self._query_errors: dict[str, int] = defaultdict(int)       # operation -> error count

        # --- Resource Metrics ---
        self._total_resources: int = 0
        self._resource_counts_by_type: dict[str, int] = defaultdict(int)  # type -> count
        self._subscription_count: int = 0
        self._subscriptions: set[str] = set()

        # --- Error Tracking ---
        self._errors: list[dict] = []  # recent errors (capped at 100)
        self._error_count: int = 0

        # --- Timestamps ---
        self._created_at: datetime = datetime.now(timezone.utc)
        self._last_reset: datetime = datetime.now(timezone.utc)

        logger.info("inventory_metrics_initialized", extra={
            "component": "inventory_metrics",
            "event": "initialized",
            "timestamp": self._created_at.isoformat()
        })

    # -----------------------------------------------------------------------
    # Cache Metrics
    # -----------------------------------------------------------------------

    def record_cache_hit(self, layer: str = "l1") -> None:
        """Record a cache hit for the specified layer (l1 or l2)."""
        self._cache_hits[layer] += 1
        self._api_calls_saved += 1
        logger.debug("inventory_cache_hit", extra={
            "component": "inventory_metrics",
            "event": "cache_hit",
            "layer": layer,
            "total_hits": self._cache_hits[layer],
            "api_calls_saved": self._api_calls_saved
        })

    def record_cache_miss(self, layer: str = "l1") -> None:
        """Record a cache miss for the specified layer."""
        self._cache_misses[layer] += 1
        logger.debug("inventory_cache_miss", extra={
            "component": "inventory_metrics",
            "event": "cache_miss",
            "layer": layer,
            "total_misses": self._cache_misses[layer]
        })

    def record_cache_set(self, layer: str = "l1") -> None:
        """Record a cache write/set for the specified layer."""
        self._cache_sets[layer] += 1

    def record_cache_eviction(self, layer: str = "l1") -> None:
        """Record a cache eviction for the specified layer."""
        self._cache_evictions[layer] += 1

    def get_cache_hit_rate(self, layer: Optional[str] = None) -> float:
        """Calculate cache hit rate for a specific layer or overall."""
        if layer:
            hits = self._cache_hits.get(layer, 0)
            misses = self._cache_misses.get(layer, 0)
        else:
            hits = sum(self._cache_hits.values())
            misses = sum(self._cache_misses.values())

        total = hits + misses
        return hits / total if total > 0 else 0.0

    # -----------------------------------------------------------------------
    # Discovery Metrics
    # -----------------------------------------------------------------------

    @contextmanager
    def track_discovery(self, subscription_id: str = "all"):
        """
        Context manager to track discovery operation timing and status.

        Usage:
            with metrics.track_discovery("sub-123"):
                resources = await engine.discover_all()
        """
        start_time = time.monotonic()
        self._discovery_count += 1

        logger.info("inventory_discovery_started", extra={
            "component": "inventory_metrics",
            "event": "discovery_started",
            "subscription_id": subscription_id,
            "discovery_number": self._discovery_count
        })

        try:
            yield
            duration = time.monotonic() - start_time
            self._discovery_durations.append(duration)
            self._last_discovery_time = datetime.now(timezone.utc)
            self._last_discovery_duration = duration
            self._last_discovery_status = "success"

            if subscription_id != "all":
                self._subscriptions.add(subscription_id)
                self._subscription_count = len(self._subscriptions)

            logger.info("inventory_discovery_completed", extra={
                "component": "inventory_metrics",
                "event": "discovery_completed",
                "subscription_id": subscription_id,
                "duration_seconds": round(duration, 3),
                "status": "success"
            })

        except Exception as e:
            duration = time.monotonic() - start_time
            self._discovery_errors += 1
            self._last_discovery_status = "error"
            self._last_discovery_duration = duration
            self._record_error("discovery", str(e), subscription_id=subscription_id)

            logger.error("inventory_discovery_failed", extra={
                "component": "inventory_metrics",
                "event": "discovery_failed",
                "subscription_id": subscription_id,
                "duration_seconds": round(duration, 3),
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    @asynccontextmanager
    async def track_discovery_async(self, subscription_id: str = "all"):
        """Async version of track_discovery."""
        start_time = time.monotonic()
        self._discovery_count += 1

        logger.info("inventory_discovery_started", extra={
            "component": "inventory_metrics",
            "event": "discovery_started",
            "subscription_id": subscription_id,
            "discovery_number": self._discovery_count
        })

        try:
            yield
            duration = time.monotonic() - start_time
            self._discovery_durations.append(duration)
            self._last_discovery_time = datetime.now(timezone.utc)
            self._last_discovery_duration = duration
            self._last_discovery_status = "success"

            if subscription_id != "all":
                self._subscriptions.add(subscription_id)
                self._subscription_count = len(self._subscriptions)

            logger.info("inventory_discovery_completed", extra={
                "component": "inventory_metrics",
                "event": "discovery_completed",
                "subscription_id": subscription_id,
                "duration_seconds": round(duration, 3),
                "status": "success"
            })

        except Exception as e:
            duration = time.monotonic() - start_time
            self._discovery_errors += 1
            self._last_discovery_status = "error"
            self._last_discovery_duration = duration
            self._record_error("discovery", str(e), subscription_id=subscription_id)

            logger.error("inventory_discovery_failed", extra={
                "component": "inventory_metrics",
                "event": "discovery_failed",
                "subscription_id": subscription_id,
                "duration_seconds": round(duration, 3),
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    def record_discovery_resources(
        self,
        subscription_id: str,
        resource_count: int,
        resource_type_counts: Optional[dict[str, int]] = None
    ) -> None:
        """Record discovered resource counts after a discovery operation."""
        self._discovery_resource_counts[subscription_id] = resource_count
        self._total_resources = sum(self._discovery_resource_counts.values())
        self._subscriptions.add(subscription_id)
        self._subscription_count = len(self._subscriptions)

        if resource_type_counts:
            for rtype, count in resource_type_counts.items():
                self._resource_counts_by_type[rtype] = count

        logger.info("inventory_resources_recorded", extra={
            "component": "inventory_metrics",
            "event": "resources_recorded",
            "subscription_id": subscription_id,
            "resource_count": resource_count,
            "total_resources": self._total_resources,
            "subscription_count": self._subscription_count
        })

    # -----------------------------------------------------------------------
    # Query Metrics
    # -----------------------------------------------------------------------

    @contextmanager
    def track_query(self, operation: str):
        """
        Context manager to track query/operation timing.

        Usage:
            with metrics.track_query("get_by_type"):
                result = cache.get_resources_by_type("vm")
        """
        start_time = time.monotonic()
        self._query_count[operation] += 1

        try:
            yield
            duration = time.monotonic() - start_time
            self._query_durations[operation].append(duration)

            # Keep only last 1000 durations per operation to prevent unbounded growth
            if len(self._query_durations[operation]) > 1000:
                self._query_durations[operation] = self._query_durations[operation][-500:]

            logger.debug("inventory_query_completed", extra={
                "component": "inventory_metrics",
                "event": "query_completed",
                "operation": operation,
                "duration_seconds": round(duration, 4),
            })

        except Exception as e:
            duration = time.monotonic() - start_time
            self._query_errors[operation] += 1
            self._record_error("query", str(e), operation=operation)

            logger.warning("inventory_query_failed", extra={
                "component": "inventory_metrics",
                "event": "query_failed",
                "operation": operation,
                "duration_seconds": round(duration, 4),
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    @asynccontextmanager
    async def track_query_async(self, operation: str):
        """Async version of track_query."""
        start_time = time.monotonic()
        self._query_count[operation] += 1

        try:
            yield
            duration = time.monotonic() - start_time
            self._query_durations[operation].append(duration)

            if len(self._query_durations[operation]) > 1000:
                self._query_durations[operation] = self._query_durations[operation][-500:]

            logger.debug("inventory_query_completed", extra={
                "component": "inventory_metrics",
                "event": "query_completed",
                "operation": operation,
                "duration_seconds": round(duration, 4),
            })

        except Exception as e:
            duration = time.monotonic() - start_time
            self._query_errors[operation] += 1
            self._record_error("query", str(e), operation=operation)

            logger.warning("inventory_query_failed", extra={
                "component": "inventory_metrics",
                "event": "query_failed",
                "operation": operation,
                "duration_seconds": round(duration, 4),
                "error": str(e),
                "error_type": type(e).__name__
            })
            raise

    # -----------------------------------------------------------------------
    # Error Tracking
    # -----------------------------------------------------------------------

    def _record_error(self, category: str, message: str, **kwargs) -> None:
        """Record an error with context for diagnostics."""
        self._error_count += 1
        error_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "message": message,
            "count": self._error_count,
            **kwargs
        }
        self._errors.append(error_entry)
        # Cap at 100 recent errors
        if len(self._errors) > 100:
            self._errors = self._errors[-50:]

    # -----------------------------------------------------------------------
    # Dashboard / Export
    # -----------------------------------------------------------------------

    def get_dashboard_metrics(self) -> dict:
        """
        Get comprehensive metrics for monitoring dashboard.

        Returns a structured dict suitable for the /api/resource-inventory/metrics endpoint.
        """
        now = datetime.now(timezone.utc)
        uptime_seconds = (now - self._created_at).total_seconds()

        # Compute average discovery duration
        avg_discovery_duration = (
            sum(self._discovery_durations) / len(self._discovery_durations)
            if self._discovery_durations else 0.0
        )

        # Compute per-operation query stats
        query_stats = {}
        for op, durations in self._query_durations.items():
            if durations:
                query_stats[op] = {
                    "count": self._query_count.get(op, 0),
                    "avg_duration_seconds": round(sum(durations) / len(durations), 4),
                    "min_duration_seconds": round(min(durations), 4),
                    "max_duration_seconds": round(max(durations), 4),
                    "p95_duration_seconds": round(
                        sorted(durations)[int(len(durations) * 0.95)] if durations else 0, 4
                    ),
                    "errors": self._query_errors.get(op, 0)
                }

        return {
            # Overall
            "status": "healthy" if self._discovery_errors == 0 else "degraded",
            "uptime_seconds": round(uptime_seconds, 1),
            "timestamp": now.isoformat(),

            # Cache Performance
            "cache": {
                "overall_hit_rate": round(self.get_cache_hit_rate(), 4),
                "l1_hit_rate": round(self.get_cache_hit_rate("l1"), 4),
                "l2_hit_rate": round(self.get_cache_hit_rate("l2"), 4),
                "l1_hits": self._cache_hits.get("l1", 0),
                "l1_misses": self._cache_misses.get("l1", 0),
                "l2_hits": self._cache_hits.get("l2", 0),
                "l2_misses": self._cache_misses.get("l2", 0),
                "total_sets": sum(self._cache_sets.values()),
                "total_evictions": sum(self._cache_evictions.values()),
                "api_calls_saved": self._api_calls_saved
            },

            # Discovery Performance
            "discovery": {
                "total_discoveries": self._discovery_count,
                "successful_discoveries": self._discovery_count - self._discovery_errors,
                "failed_discoveries": self._discovery_errors,
                "success_rate": round(
                    (self._discovery_count - self._discovery_errors) / self._discovery_count, 4
                ) if self._discovery_count > 0 else 0.0,
                "avg_duration_seconds": round(avg_discovery_duration, 3),
                "last_discovery": self._last_discovery_time.isoformat() if self._last_discovery_time else None,
                "last_duration_seconds": round(self._last_discovery_duration, 3) if self._last_discovery_duration else None,
                "last_status": self._last_discovery_status
            },

            # Resource Inventory
            "resources": {
                "total_resources": self._total_resources,
                "subscriptions": self._subscription_count,
                "subscription_ids": sorted(self._subscriptions),
                "by_subscription": dict(self._discovery_resource_counts),
                "by_type": dict(self._resource_counts_by_type)
            },

            # Query Performance
            "queries": {
                "total_queries": sum(self._query_count.values()),
                "total_errors": sum(self._query_errors.values()),
                "by_operation": query_stats
            },

            # Errors
            "errors": {
                "total_errors": self._error_count,
                "recent_errors": self._errors[-10:]  # last 10 errors
            }
        }

    def get_summary_metrics(self) -> dict:
        """
        Get a compact summary suitable for health checks and quick status.

        This is the simplified format requested in the task spec:
        GET /api/resource-inventory/metrics
        """
        return {
            "cache_hit_rate": round(self.get_cache_hit_rate(), 4),
            "l1_hit_rate": round(self.get_cache_hit_rate("l1"), 4),
            "l2_hit_rate": round(self.get_cache_hit_rate("l2"), 4),
            "total_resources": self._total_resources,
            "subscriptions": self._subscription_count,
            "last_discovery": (
                self._last_discovery_time.isoformat()
                if self._last_discovery_time else None
            ),
            "api_calls_saved": self._api_calls_saved,
            "discovery_count": self._discovery_count,
            "error_count": self._error_count
        }

    # -----------------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all metrics counters (e.g., for testing or periodic reset)."""
        self.__init__()  # type: ignore[misc]
        self._last_reset = datetime.now(timezone.utc)
        logger.info("inventory_metrics_reset", extra={
            "component": "inventory_metrics",
            "event": "metrics_reset",
            "timestamp": self._last_reset.isoformat()
        })
