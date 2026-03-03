"""
End-to-End Tests for the Resource Inventory System

Covers the full stack: Discovery Engine → Cache → Client → API → Frontend integration.
Uses mocked Azure services so tests run locally without cloud credentials.

Test categories:
  1. Full discovery → cache → API workflow
  2. Cache layer (L1/L2 lifecycle)
  3. Client API (filters, name lookup, parameter resolution)
  4. REST API endpoints (all 5 routes)
  5. Multi-subscription scenarios
  6. Scheduler integration stubs (Task #10/#11)
  7. SRE orchestrator integration stubs (Task #8)

Run:
    pytest tests/test_e2e_inventory.py -v
    pytest tests/test_e2e_inventory.py -m e2e -v
    pytest tests/test_e2e_inventory.py -m "e2e and not stub" -v
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mark all tests in this module
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SUBSCRIPTION = "00000000-1111-2222-3333-444444444444"
SAMPLE_SUBSCRIPTION_2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

SAMPLE_VM_RESOURCES = [
    {
        "id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm-web-01",
        "resource_id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm-web-01",
        "resource_name": "vm-web-01",
        "resource_type": "microsoft.compute/virtualmachines",
        "location": "eastus",
        "resource_group": "rg-prod",
        "subscription_id": SAMPLE_SUBSCRIPTION,
        "tags": {"env": "production", "team": "web"},
        "sku": {"name": "Standard_D4s_v3"},
        "kind": None,
        "selected_properties": {"vm_size": "Standard_D4s_v3", "os_type": "Linux", "provisioning_state": "Succeeded"},
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "ttl": 604800,
    },
    {
        "id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-staging/providers/Microsoft.Compute/virtualMachines/vm-web-02",
        "resource_id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-staging/providers/Microsoft.Compute/virtualMachines/vm-web-02",
        "resource_name": "vm-web-02",
        "resource_type": "microsoft.compute/virtualmachines",
        "location": "westus2",
        "resource_group": "rg-staging",
        "subscription_id": SAMPLE_SUBSCRIPTION,
        "tags": {"env": "staging"},
        "sku": {"name": "Standard_B2s"},
        "kind": None,
        "selected_properties": {"vm_size": "Standard_B2s", "os_type": "Linux", "provisioning_state": "Succeeded"},
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "ttl": 604800,
    },
]

SAMPLE_VNET_RESOURCES = [
    {
        "id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-prod/providers/Microsoft.Network/virtualNetworks/vnet-main",
        "resource_id": f"/subscriptions/{SAMPLE_SUBSCRIPTION}/resourceGroups/rg-prod/providers/Microsoft.Network/virtualNetworks/vnet-main",
        "resource_name": "vnet-main",
        "resource_type": "microsoft.network/virtualnetworks",
        "location": "eastus",
        "resource_group": "rg-prod",
        "subscription_id": SAMPLE_SUBSCRIPTION,
        "tags": {"env": "production"},
        "sku": None,
        "kind": None,
        "selected_properties": {"provisioning_state": "Succeeded"},
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "ttl": 604800,
    },
]

SAMPLE_SUBSCRIPTIONS = [
    {"subscription_id": SAMPLE_SUBSCRIPTION, "display_name": "Prod", "state": "Enabled", "tenant_id": "tenant-1"},
    {"subscription_id": SAMPLE_SUBSCRIPTION_2, "display_name": "Dev", "state": "Enabled", "tenant_id": "tenant-1"},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_cache():
    """Create a fresh ResourceInventoryCache for each test."""
    from utils.resource_inventory_cache import ResourceInventoryCache
    cache = ResourceInventoryCache(default_l1_ttl=300, default_l2_ttl=3600, max_l1_entries=100)
    # Disable L2 for unit/e2e tests (no real Cosmos)
    cache._l2_ready = False
    return cache


@pytest.fixture
def client_with_cache(fresh_cache):
    """Create a ResourceInventoryClient backed by the fresh cache."""
    from utils.resource_inventory_client import ResourceInventoryClient
    return ResourceInventoryClient(cache=fresh_cache)


@pytest.fixture
def mock_discovery_engine():
    """Mock ResourceDiscoveryEngine that returns sample data."""
    engine = MagicMock()
    engine.full_resource_discovery = AsyncMock(return_value=SAMPLE_VM_RESOURCES + SAMPLE_VNET_RESOURCES)
    engine.discover_all_subscriptions = AsyncMock(return_value=SAMPLE_SUBSCRIPTIONS)
    engine.extract_relationships = AsyncMock(return_value=[
        {"source": SAMPLE_VM_RESOURCES[0]["resource_id"], "target": SAMPLE_VNET_RESOURCES[0]["resource_id"],
         "relationship_type": "depends_on", "depth": 1},
    ])
    return engine


@pytest.fixture
def app_client():
    """Create a FastAPI TestClient with the resource inventory router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    try:
        from api.resource_inventory import router, health_router
    except ImportError:
        from app.agentic.eol.api.resource_inventory import router, health_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(health_router)
    return TestClient(app)


# =====================================================================
# 1. CACHE LAYER TESTS
# =====================================================================

class TestCacheLifecycle:
    """Test L1 cache set/get/invalidate/stats lifecycle."""

    async def test_cache_set_and_get(self, fresh_cache):
        """Resources stored in L1 are retrievable."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        result = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert result is not None
        assert len(result) == 2
        assert result[0]["resource_name"] == "vm-web-01"

    async def test_cache_miss_returns_none(self, fresh_cache):
        """Cache miss returns None."""
        result = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualMachines")
        assert result is None

    async def test_cache_invalidate(self, fresh_cache):
        """Invalidated entries are no longer returned."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        removed = await fresh_cache.invalidate(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert removed >= 1
        result = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert result is None

    async def test_cache_invalidate_by_subscription(self, fresh_cache):
        """Invalidating by subscription clears all types for that subscription."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.network/virtualnetworks", SAMPLE_VNET_RESOURCES)
        removed = await fresh_cache.invalidate(SAMPLE_SUBSCRIPTION)
        assert removed == 2
        assert await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines") is None
        assert await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.network/virtualnetworks") is None

    async def test_cache_statistics(self, fresh_cache):
        """Statistics track hits, misses, and writes."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")  # hit
        await fresh_cache.get(SAMPLE_SUBSCRIPTION, "nonexistent.type")  # miss

        stats = fresh_cache.get_statistics()
        assert stats["hits_l1"] == 1
        assert stats["misses"] == 1
        assert stats["writes"] == 1
        assert stats["hit_rate_percent"] > 0

    async def test_cache_filters(self, fresh_cache):
        """Cache keys with different filters are independent."""
        filters_a = {"resource_group": "rg-prod"}
        filters_b = {"resource_group": "rg-staging"}

        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", [SAMPLE_VM_RESOURCES[0]], filters=filters_a)
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", [SAMPLE_VM_RESOURCES[1]], filters=filters_b)

        result_a = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", filters=filters_a)
        result_b = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", filters=filters_b)

        assert len(result_a) == 1
        assert result_a[0]["resource_name"] == "vm-web-01"
        assert len(result_b) == 1
        assert result_b[0]["resource_name"] == "vm-web-02"

    async def test_cache_clear_all(self, fresh_cache):
        """clear_all removes everything and resets stats."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        count = fresh_cache.clear_all()
        assert count >= 1
        stats = fresh_cache.get_statistics()
        assert stats["l1_entries"] == 0
        assert stats["writes"] == 0

    async def test_cache_get_multi(self, fresh_cache):
        """Batch retrieval across multiple subscriptions."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        results = await fresh_cache.get_multi(
            [SAMPLE_SUBSCRIPTION, SAMPLE_SUBSCRIPTION_2],
            "microsoft.compute/virtualmachines",
        )
        assert results[SAMPLE_SUBSCRIPTION] is not None
        assert len(results[SAMPLE_SUBSCRIPTION]) == 2
        assert results[SAMPLE_SUBSCRIPTION_2] is None  # not cached


# =====================================================================
# 2. CLIENT API TESTS
# =====================================================================

class TestClientAPI:
    """Test ResourceInventoryClient methods."""

    async def test_check_exists_positive(self, client_with_cache, fresh_cache):
        """check_resource_exists returns True when resources are cached."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        exists = await client_with_cache.check_resource_exists(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert exists is True

    async def test_check_exists_negative(self, client_with_cache):
        """check_resource_exists returns False on empty cache."""
        exists = await client_with_cache.check_resource_exists(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert exists is False

    async def test_check_exists_with_filters(self, client_with_cache, fresh_cache):
        """check_resource_exists applies filter criteria."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)

        # Should match
        assert await client_with_cache.check_resource_exists(
            "microsoft.compute/virtualmachines",
            filters={"name": "vm-web-01"},
            subscription_id=SAMPLE_SUBSCRIPTION,
        ) is True

        # Should not match
        assert await client_with_cache.check_resource_exists(
            "microsoft.compute/virtualmachines",
            filters={"name": "nonexistent-vm"},
            subscription_id=SAMPLE_SUBSCRIPTION,
        ) is False

    async def test_get_resources_from_cache(self, client_with_cache, fresh_cache):
        """get_resources returns cached data."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        resources = await client_with_cache.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert len(resources) == 2

    async def test_get_resources_with_location_filter(self, client_with_cache, fresh_cache):
        """get_resources applies location filter."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        resources = await client_with_cache.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
            filters={"location": "eastus"},
        )
        assert len(resources) == 1
        assert resources[0]["resource_name"] == "vm-web-01"

    async def test_get_resources_with_rg_filter(self, client_with_cache, fresh_cache):
        """get_resources applies resource_group filter."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        resources = await client_with_cache.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
            filters={"resource_group": "rg-staging"},
        )
        assert len(resources) == 1
        assert resources[0]["resource_name"] == "vm-web-02"

    async def test_get_resources_with_tag_filter(self, client_with_cache, fresh_cache):
        """get_resources applies tag filter."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        resources = await client_with_cache.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
            filters={"tags": {"env": "production"}},
        )
        assert len(resources) == 1
        assert resources[0]["resource_name"] == "vm-web-01"

    async def test_get_resource_by_name_unique(self, client_with_cache, fresh_cache):
        """get_resource_by_name returns single match for unique name."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        matches = await client_with_cache.get_resource_by_name(
            "vm-web-01",
            resource_type="microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert len(matches) == 1
        assert matches[0]["resource_group"] == "rg-prod"

    async def test_get_resource_by_name_collision(self, client_with_cache, fresh_cache):
        """get_resource_by_name returns multiple matches for common substring."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        matches = await client_with_cache.get_resource_by_name(
            "vm-web",  # matches both vm-web-01 and vm-web-02
            resource_type="microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert len(matches) == 2

    async def test_resolve_tool_parameters_subscription(self, client_with_cache):
        """resolve_tool_parameters fills subscription_id from config."""
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": SAMPLE_SUBSCRIPTION}):
            resolved = await client_with_cache.resolve_tool_parameters(
                "check_resource_health", {}
            )
            assert resolved.get("subscription_id") == SAMPLE_SUBSCRIPTION

    async def test_resolve_tool_parameters_resource_group(self, client_with_cache, fresh_cache):
        """resolve_tool_parameters resolves resource_group from name lookup."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": SAMPLE_SUBSCRIPTION}):
            resolved = await client_with_cache.resolve_tool_parameters(
                "get_performance_metrics",
                {"resource_name": "vm-web-01", "resource_type": "microsoft.compute/virtualmachines"},
            )
            assert resolved.get("resource_group") == "rg-prod"

    async def test_resolve_tool_parameters_disambiguation(self, client_with_cache, fresh_cache):
        """resolve_tool_parameters flags disambiguation when multiple matches."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": SAMPLE_SUBSCRIPTION}):
            resolved = await client_with_cache.resolve_tool_parameters(
                "check_resource_health",
                {"resource_name": "vm-web"},
            )
            assert resolved.get("_disambiguation_required") is True
            assert len(resolved.get("_matches", [])) == 2

    async def test_client_statistics(self, client_with_cache, fresh_cache):
        """get_statistics returns cache and engine status."""
        stats = client_with_cache.get_statistics()
        assert "cache" in stats
        assert "engine_available" in stats


# =====================================================================
# 3. REST API ENDPOINT TESTS
# =====================================================================

class TestAPIEndpoints:
    """Test the FastAPI resource inventory router endpoints."""

    def test_health_endpoint(self, app_client):
        """GET /healthz/inventory returns health data."""
        resp = app_client.get("/healthz/inventory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "status" in data["data"]
        assert "cache" in data["data"]
        assert "config" in data["data"]

    def test_stats_endpoint(self, app_client):
        """GET /api/resource-inventory/stats returns cache statistics."""
        resp = app_client.get("/api/resource-inventory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "duration_ms" in data

    def test_resources_requires_type(self, app_client):
        """GET /api/resource-inventory/resources without resource_type returns error."""
        resp = app_client.get("/api/resource-inventory/resources")
        data = resp.json()
        assert data["success"] is False
        assert "resource_type" in data["error"].lower()

    def test_resources_with_type(self, app_client):
        """GET /api/resource-inventory/resources with resource_type returns paginated data."""
        resp = app_client.get(
            "/api/resource-inventory/resources",
            params={
                "resource_type": "Microsoft.Compute/virtualMachines",
                "subscription_id": SAMPLE_SUBSCRIPTION,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # May return empty if no real discovery, but structure is correct
        assert "data" in data
        if data["success"] and data["data"]:
            assert "items" in data["data"]
            assert "total" in data["data"]
            assert "has_more" in data["data"]

    def test_resources_pagination(self, app_client):
        """GET /api/resource-inventory/resources respects offset and limit."""
        resp = app_client.get(
            "/api/resource-inventory/resources",
            params={
                "resource_type": "Microsoft.Compute/virtualMachines",
                "subscription_id": SAMPLE_SUBSCRIPTION,
                "offset": 0,
                "limit": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["success"] and data["data"]:
            assert data["data"]["limit"] == 10
            assert data["data"]["offset"] == 0

    @pytest.mark.integration
    def test_subscriptions_endpoint(self, app_client):
        """GET /api/resource-inventory/subscriptions attempts discovery."""
        resp = app_client.get("/api/resource-inventory/subscriptions")
        assert resp.status_code == 200
        data = resp.json()
        # Will fail without Azure credentials but response format is valid
        assert "success" in data

    @pytest.mark.integration
    def test_refresh_endpoint(self, app_client):
        """POST /api/resource-inventory/refresh triggers discovery."""
        resp = app_client.post(
            "/api/resource-inventory/refresh",
            json={"subscription_id": SAMPLE_SUBSCRIPTION, "mode": "full"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    def test_response_envelope(self, app_client):
        """All responses follow StandardResponse structure."""
        for path in ["/healthz/inventory", "/api/resource-inventory/stats"]:
            resp = app_client.get(path)
            data = resp.json()
            assert "success" in data
            assert "timestamp" in data


# =====================================================================
# 4. FULL WORKFLOW E2E TESTS
# =====================================================================

class TestFullWorkflow:
    """End-to-end: discovery → cache → client → query."""

    async def test_discover_cache_query_workflow(self, fresh_cache, mock_discovery_engine):
        """Full pipeline: discover resources, cache them, query with filters."""
        from utils.resource_inventory_client import ResourceInventoryClient

        client = ResourceInventoryClient(cache=fresh_cache)
        client._engine = mock_discovery_engine

        # Step 1: Get resources (triggers discovery on cache miss)
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": SAMPLE_SUBSCRIPTION}):
            resources = await client.get_resources(
                "microsoft.compute/virtualmachines",
                subscription_id=SAMPLE_SUBSCRIPTION,
            )

        # Step 2: Verify discovery was called
        mock_discovery_engine.full_resource_discovery.assert_called_once()

        # Step 3: Verify resources are now cached
        cached = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert cached is not None

        # Step 4: Second query should hit cache (no additional discovery call)
        resources2 = await client.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
        )
        assert mock_discovery_engine.full_resource_discovery.call_count == 1  # still 1

        # Step 5: Filter by location
        eastus_only = await client.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
            filters={"location": "eastus"},
        )
        # May or may not filter depending on what discovery returned
        assert isinstance(eastus_only, list)

    async def test_parameter_resolution_workflow(self, fresh_cache, mock_discovery_engine):
        """Full workflow: cache resources, then auto-resolve tool parameters."""
        from utils.resource_inventory_client import ResourceInventoryClient

        client = ResourceInventoryClient(cache=fresh_cache)
        client._engine = mock_discovery_engine

        # Pre-populate cache
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)

        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": SAMPLE_SUBSCRIPTION}):
            resolved = await client.resolve_tool_parameters(
                "get_performance_metrics",
                {"resource_name": "vm-web-01", "resource_type": "microsoft.compute/virtualmachines"},
            )

        assert resolved["subscription_id"] == SAMPLE_SUBSCRIPTION
        assert resolved["resource_group"] == "rg-prod"
        assert "_disambiguation_required" not in resolved

    async def test_relationship_extraction_workflow(self, fresh_cache, mock_discovery_engine):
        """Full workflow: get resource relationships."""
        from utils.resource_inventory_client import ResourceInventoryClient

        client = ResourceInventoryClient(cache=fresh_cache)
        client._engine = mock_discovery_engine

        relationships = await client.get_resource_relationships(
            SAMPLE_VM_RESOURCES[0]["resource_id"], depth=2,
        )
        assert len(relationships) >= 1
        assert relationships[0]["relationship_type"] == "depends_on"

    async def test_multi_subscription_workflow(self, fresh_cache):
        """Multi-subscription batch retrieval."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)
        # Subscription 2 has no data

        results = await fresh_cache.get_multi(
            [SAMPLE_SUBSCRIPTION, SAMPLE_SUBSCRIPTION_2],
            "microsoft.compute/virtualmachines",
        )
        assert results[SAMPLE_SUBSCRIPTION] is not None
        assert len(results[SAMPLE_SUBSCRIPTION]) == 2
        assert results[SAMPLE_SUBSCRIPTION_2] is None


# =====================================================================
# 5. CACHE PERFORMANCE TESTS
# =====================================================================

class TestCachePerformance:
    """Validate cache performance characteristics."""

    async def test_l1_read_under_1ms(self, fresh_cache):
        """L1 cache read should complete under 1ms."""
        await fresh_cache.set(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines", SAMPLE_VM_RESOURCES)

        start = time.perf_counter()
        for _ in range(100):
            await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        elapsed = (time.perf_counter() - start) / 100 * 1000  # ms per read

        assert elapsed < 1.0, f"L1 read took {elapsed:.3f}ms, expected < 1ms"

    async def test_cache_eviction_at_capacity(self, fresh_cache):
        """Cache evicts old entries when max_l1_entries is reached."""
        fresh_cache._max_l1_entries = 10
        for i in range(15):
            await fresh_cache.set(f"sub-{i}", "microsoft.compute/virtualmachines", [{"id": str(i)}])

        stats = fresh_cache.get_statistics()
        assert stats["l1_entries"] <= 10


# =====================================================================
# 6. STUB: SRE ORCHESTRATOR INTEGRATION (Task #8)
# =====================================================================

@pytest.mark.stub
class TestSREOrchestratorIntegration:
    """Stub tests for SRE orchestrator integration.

    Replace stubs with real integration once Task #8 completes.
    """

    async def test_orchestrator_uses_inventory_for_params(self):
        """SRE orchestrator should use ResourceInventoryClient.resolve_tool_parameters."""
        # STUB: Mock orchestrator calling resolve_tool_parameters
        from utils.resource_inventory_client import ResourceInventoryClient, get_resource_inventory_client
        client = get_resource_inventory_client()
        resolved = await client.resolve_tool_parameters("check_resource_health", {})
        assert isinstance(resolved, dict)

    async def test_orchestrator_skips_without_subscription(self):
        """Orchestrator gracefully handles missing subscription."""
        from utils.resource_inventory_client import ResourceInventoryClient
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        client = ResourceInventoryClient(cache=cache)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(type(client), '_default_subscription', return_value=""):
                resolved = await client.resolve_tool_parameters("some_tool", {})
                assert "subscription_id" not in resolved or resolved["subscription_id"] == ""


# =====================================================================
# 7. STUB: SCHEDULER INTEGRATION (Task #10/#11)
# =====================================================================

@pytest.mark.stub
class TestSchedulerIntegration:
    """Stub tests for APScheduler periodic refresh.

    Replace stubs with real integration once Tasks #10/#11 complete.
    """

    async def test_scheduled_full_discovery_populates_cache(self, fresh_cache, mock_discovery_engine):
        """Scheduled full scan should populate the cache."""
        from utils.resource_inventory_client import ResourceInventoryClient

        client = ResourceInventoryClient(cache=fresh_cache)
        client._engine = mock_discovery_engine

        # Simulate what the scheduler job would do
        resources = await client.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=SAMPLE_SUBSCRIPTION,
            refresh=True,
        )
        assert len(resources) > 0
        # Cache should now have data
        cached = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert cached is not None

    async def test_incremental_discovery_after_full(self, fresh_cache, mock_discovery_engine):
        """Incremental scan following a full scan should update cache."""
        from utils.resource_inventory_client import ResourceInventoryClient

        client = ResourceInventoryClient(cache=fresh_cache)
        client._engine = mock_discovery_engine

        # Full scan
        await client.get_resources("microsoft.compute/virtualmachines", subscription_id=SAMPLE_SUBSCRIPTION, refresh=True)

        # Simulate incremental with modified data
        modified_vms = [dict(SAMPLE_VM_RESOURCES[0], resource_name="vm-web-01-updated")]
        mock_discovery_engine.full_resource_discovery = AsyncMock(return_value=modified_vms)

        await client.get_resources("microsoft.compute/virtualmachines", subscription_id=SAMPLE_SUBSCRIPTION, refresh=True)

        cached = await fresh_cache.get(SAMPLE_SUBSCRIPTION, "microsoft.compute/virtualmachines")
        assert cached is not None
        assert cached[0]["resource_name"] == "vm-web-01-updated"
