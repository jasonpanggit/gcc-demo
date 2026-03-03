"""
Unit tests for the Resource Inventory Monitoring Metrics module.

Tests cover:
- InventoryMetrics singleton lifecycle
- Cache hit/miss recording and hit-rate calculation
- Discovery tracking (sync and async context managers)
- Query tracking (sync and async context managers)
- Error recording and capping
- Dashboard / summary metric export
- Reset functionality
"""

import asyncio
import time
import pytest
from unittest.mock import patch

import sys
import os

# Ensure the app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.inventory_metrics import (
    InventoryMetrics,
    get_inventory_metrics,
    reset_inventory_metrics,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the module-level singleton before and after each test."""
    reset_inventory_metrics()
    yield
    reset_inventory_metrics()


@pytest.fixture
def metrics() -> InventoryMetrics:
    return InventoryMetrics()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSingleton:
    def test_get_returns_same_instance(self):
        a = get_inventory_metrics()
        b = get_inventory_metrics()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_inventory_metrics()
        reset_inventory_metrics()
        b = get_inventory_metrics()
        assert a is not b


# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCacheMetrics:
    def test_cache_hit_increments(self, metrics: InventoryMetrics):
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l2")

        assert metrics._cache_hits["l1"] == 2
        assert metrics._cache_hits["l2"] == 1

    def test_cache_miss_increments(self, metrics: InventoryMetrics):
        metrics.record_cache_miss("l1")
        metrics.record_cache_miss("l2")
        metrics.record_cache_miss("l2")

        assert metrics._cache_misses["l1"] == 1
        assert metrics._cache_misses["l2"] == 2

    def test_cache_hit_rate_overall(self, metrics: InventoryMetrics):
        # 3 hits, 1 miss => 75%
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l2")
        metrics.record_cache_miss("l1")

        assert metrics.get_cache_hit_rate() == pytest.approx(0.75)

    def test_cache_hit_rate_per_layer(self, metrics: InventoryMetrics):
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l1")
        metrics.record_cache_miss("l1")
        metrics.record_cache_hit("l2")
        metrics.record_cache_miss("l2")
        metrics.record_cache_miss("l2")

        assert metrics.get_cache_hit_rate("l1") == pytest.approx(2 / 3)
        assert metrics.get_cache_hit_rate("l2") == pytest.approx(1 / 3)

    def test_cache_hit_rate_no_data(self, metrics: InventoryMetrics):
        assert metrics.get_cache_hit_rate() == 0.0
        assert metrics.get_cache_hit_rate("l1") == 0.0

    def test_api_calls_saved(self, metrics: InventoryMetrics):
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l2")
        assert metrics._api_calls_saved == 2

    def test_cache_set_and_eviction(self, metrics: InventoryMetrics):
        metrics.record_cache_set("l1")
        metrics.record_cache_set("l1")
        metrics.record_cache_eviction("l1")

        assert metrics._cache_sets["l1"] == 2
        assert metrics._cache_evictions["l1"] == 1


# ---------------------------------------------------------------------------
# Discovery tracking
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDiscoveryTracking:
    def test_sync_discovery_success(self, metrics: InventoryMetrics):
        with metrics.track_discovery("sub-123"):
            time.sleep(0.01)

        assert metrics._discovery_count == 1
        assert metrics._discovery_errors == 0
        assert len(metrics._discovery_durations) == 1
        assert metrics._discovery_durations[0] >= 0.01
        assert metrics._last_discovery_status == "success"
        assert metrics._last_discovery_time is not None

    def test_sync_discovery_failure(self, metrics: InventoryMetrics):
        with pytest.raises(ValueError):
            with metrics.track_discovery("sub-fail"):
                raise ValueError("boom")

        assert metrics._discovery_count == 1
        assert metrics._discovery_errors == 1
        assert metrics._last_discovery_status == "error"
        assert metrics._error_count == 1

    @pytest.mark.asyncio
    async def test_async_discovery_success(self, metrics: InventoryMetrics):
        async with metrics.track_discovery_async("sub-456"):
            await asyncio.sleep(0.01)

        assert metrics._discovery_count == 1
        assert metrics._discovery_errors == 0
        assert metrics._last_discovery_status == "success"

    @pytest.mark.asyncio
    async def test_async_discovery_failure(self, metrics: InventoryMetrics):
        with pytest.raises(RuntimeError):
            async with metrics.track_discovery_async("sub-err"):
                raise RuntimeError("async boom")

        assert metrics._discovery_count == 1
        assert metrics._discovery_errors == 1
        assert metrics._last_discovery_status == "error"

    def test_subscription_tracking(self, metrics: InventoryMetrics):
        with metrics.track_discovery("sub-a"):
            pass
        with metrics.track_discovery("sub-b"):
            pass
        with metrics.track_discovery("sub-a"):
            pass

        assert metrics._subscription_count == 2
        assert metrics._subscriptions == {"sub-a", "sub-b"}

    def test_record_discovery_resources(self, metrics: InventoryMetrics):
        type_counts = {
            "Microsoft.Compute/virtualMachines": 10,
            "Microsoft.Network/virtualNetworks": 5,
        }
        metrics.record_discovery_resources("sub-123", 15, type_counts)

        assert metrics._total_resources == 15
        assert metrics._discovery_resource_counts["sub-123"] == 15
        assert metrics._resource_counts_by_type["Microsoft.Compute/virtualMachines"] == 10
        assert metrics._resource_counts_by_type["Microsoft.Network/virtualNetworks"] == 5
        assert "sub-123" in metrics._subscriptions


# ---------------------------------------------------------------------------
# Query tracking
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQueryTracking:
    def test_sync_query_success(self, metrics: InventoryMetrics):
        with metrics.track_query("get_resources"):
            time.sleep(0.005)

        assert metrics._query_count["get_resources"] == 1
        assert len(metrics._query_durations["get_resources"]) == 1
        assert metrics._query_errors.get("get_resources", 0) == 0

    def test_sync_query_failure(self, metrics: InventoryMetrics):
        with pytest.raises(TypeError):
            with metrics.track_query("bad_query"):
                raise TypeError("type error")

        assert metrics._query_count["bad_query"] == 1
        assert metrics._query_errors["bad_query"] == 1

    @pytest.mark.asyncio
    async def test_async_query_success(self, metrics: InventoryMetrics):
        async with metrics.track_query_async("async_get"):
            await asyncio.sleep(0.005)

        assert metrics._query_count["async_get"] == 1
        assert len(metrics._query_durations["async_get"]) == 1

    @pytest.mark.asyncio
    async def test_async_query_failure(self, metrics: InventoryMetrics):
        with pytest.raises(OSError):
            async with metrics.track_query_async("async_fail"):
                raise OSError("os error")

        assert metrics._query_errors["async_fail"] == 1

    def test_query_duration_list_capped(self, metrics: InventoryMetrics):
        """Verify that query duration lists are trimmed to prevent memory leaks."""
        for _ in range(1100):
            with metrics.track_query("flood"):
                pass

        # After 1100 entries, should be trimmed to 500
        assert len(metrics._query_durations["flood"]) <= 1000


# ---------------------------------------------------------------------------
# Error tracking
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorTracking:
    def test_errors_capped_at_100(self, metrics: InventoryMetrics):
        for i in range(120):
            metrics._record_error("test", f"error {i}")

        assert len(metrics._errors) <= 100
        assert metrics._error_count == 120


# ---------------------------------------------------------------------------
# Dashboard / summary export
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDashboardMetrics:
    def test_summary_metrics_structure(self, metrics: InventoryMetrics):
        summary = metrics.get_summary_metrics()

        expected_keys = {
            "cache_hit_rate", "l1_hit_rate", "l2_hit_rate",
            "total_resources", "subscriptions", "last_discovery",
            "api_calls_saved", "discovery_count", "error_count"
        }
        assert set(summary.keys()) == expected_keys

    def test_summary_defaults(self, metrics: InventoryMetrics):
        summary = metrics.get_summary_metrics()
        assert summary["cache_hit_rate"] == 0.0
        assert summary["total_resources"] == 0
        assert summary["subscriptions"] == 0
        assert summary["last_discovery"] is None
        assert summary["api_calls_saved"] == 0

    def test_dashboard_metrics_structure(self, metrics: InventoryMetrics):
        dashboard = metrics.get_dashboard_metrics()

        assert "status" in dashboard
        assert "uptime_seconds" in dashboard
        assert "timestamp" in dashboard
        assert "cache" in dashboard
        assert "discovery" in dashboard
        assert "resources" in dashboard
        assert "queries" in dashboard
        assert "errors" in dashboard

    def test_dashboard_with_data(self, metrics: InventoryMetrics):
        # Simulate some activity
        metrics.record_cache_hit("l1")
        metrics.record_cache_hit("l1")
        metrics.record_cache_miss("l1")
        metrics.record_cache_hit("l2")

        with metrics.track_discovery("sub-test"):
            pass
        metrics.record_discovery_resources("sub-test", 100, {"vm": 60, "vnet": 40})

        with metrics.track_query("get_resources"):
            pass

        dashboard = metrics.get_dashboard_metrics()

        assert dashboard["status"] == "healthy"
        assert dashboard["cache"]["l1_hits"] == 2
        assert dashboard["cache"]["l1_misses"] == 1
        assert dashboard["cache"]["l2_hits"] == 1
        assert dashboard["cache"]["api_calls_saved"] == 3
        assert dashboard["cache"]["overall_hit_rate"] == pytest.approx(0.75)

        assert dashboard["discovery"]["total_discoveries"] == 1
        assert dashboard["discovery"]["failed_discoveries"] == 0
        assert dashboard["discovery"]["last_status"] == "success"

        assert dashboard["resources"]["total_resources"] == 100
        assert dashboard["resources"]["subscriptions"] == 1
        assert dashboard["resources"]["by_type"]["vm"] == 60

        assert dashboard["queries"]["total_queries"] == 1
        assert "get_resources" in dashboard["queries"]["by_operation"]

    def test_dashboard_degraded_on_errors(self, metrics: InventoryMetrics):
        try:
            with metrics.track_discovery("sub-fail"):
                raise RuntimeError("oops")
        except RuntimeError:
            pass

        dashboard = metrics.get_dashboard_metrics()
        assert dashboard["status"] == "degraded"
        assert dashboard["discovery"]["failed_discoveries"] == 1

    def test_query_stats_p95(self, metrics: InventoryMetrics):
        """Verify p95 calculation in query stats."""
        for _ in range(100):
            with metrics.track_query("perf_test"):
                pass

        dashboard = metrics.get_dashboard_metrics()
        op_stats = dashboard["queries"]["by_operation"]["perf_test"]
        assert "p95_duration_seconds" in op_stats
        assert op_stats["count"] == 100
        assert op_stats["min_duration_seconds"] <= op_stats["avg_duration_seconds"]
        assert op_stats["avg_duration_seconds"] <= op_stats["max_duration_seconds"]


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReset:
    def test_reset_clears_all_counters(self, metrics: InventoryMetrics):
        metrics.record_cache_hit("l1")
        metrics.record_cache_miss("l2")
        with metrics.track_discovery("sub-x"):
            pass
        metrics.record_discovery_resources("sub-x", 50)

        metrics.reset()

        assert metrics._cache_hits.get("l1", 0) == 0
        assert metrics._cache_misses.get("l2", 0) == 0
        assert metrics._discovery_count == 0
        assert metrics._total_resources == 0
        assert metrics._api_calls_saved == 0
        assert metrics._error_count == 0
        assert len(metrics._errors) == 0

    def test_reset_updates_timestamp(self, metrics: InventoryMetrics):
        original = metrics._created_at
        time.sleep(0.01)
        metrics.reset()
        assert metrics._last_reset > original
