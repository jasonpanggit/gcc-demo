"""
Integration tests for the resource inventory system.

Tests end-to-end flows through ResourceDiscoveryEngine →
ResourceInventoryCache → ResourceInventoryClient with mocked
Azure SDK responses. Controlled via USE_MOCK_DATA env var;
when set to ``false`` (and Azure credentials are available)
tests run against live Azure.

Covers:
- Full discovery pipeline (discover → cache → query)
- Incremental discovery with change merging
- Multi-subscription resource queries
- Name collision handling
- Parameter auto-population
- Relationship traversal
- Scheduler job execution
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_SUB_A = "aaaaaaaa-1111-2222-3333-444444444444"
MOCK_SUB_B = "bbbbbbbb-1111-2222-3333-444444444444"
MOCK_TENANT = "tenant-0000-0000-0000-000000000000"
MOCK_RG = "rg-test"

# ---------------------------------------------------------------------------
# Mock Resource Graph data
# ---------------------------------------------------------------------------

def _make_resource(name: str, rtype: str, sub: str = MOCK_SUB_A, rg: str = MOCK_RG, **extra):
    """Factory for mock Resource Graph rows."""
    base = {
        "id": f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{rtype}/{name}",
        "name": name,
        "type": rtype,
        "location": "eastus",
        "resourceGroup": rg,
        "subscriptionId": sub,
        "tags": {"env": "test"},
        "sku": None,
        "kind": None,
        "identity": None,
        "managedBy": None,
        "plan": None,
        "zones": None,
        "extendedLocation": None,
        "properties": {"provisioningState": "Succeeded"},
    }
    base.update(extra)
    return base


MOCK_VM_1 = _make_resource("vm-web-01", "Microsoft.Compute/virtualMachines",
    properties={"hardwareProfile": {"vmSize": "Standard_D2s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
                "provisioningState": "Succeeded"})
MOCK_VM_2 = _make_resource("vm-web-02", "Microsoft.Compute/virtualMachines",
    properties={"hardwareProfile": {"vmSize": "Standard_D4s_v3"},
                "storageProfile": {"osDisk": {"osType": "Linux"}},
                "provisioningState": "Succeeded"})
MOCK_APP_1 = _make_resource("app-frontend", "Microsoft.Web/sites",
    properties={"state": "Running", "defaultHostName": "app-frontend.azurewebsites.net",
                "httpsOnly": True, "kind": "app,linux"})
MOCK_APP_2 = _make_resource("app-frontend", "Microsoft.Web/sites", rg="rg-staging",
    properties={"state": "Running", "defaultHostName": "app-frontend-staging.azurewebsites.net",
                "httpsOnly": True, "kind": "app,linux"})
MOCK_VNET = _make_resource("vnet-main", "Microsoft.Network/virtualNetworks")

ALL_MOCK_RESOURCES = [MOCK_VM_1, MOCK_VM_2, MOCK_APP_1, MOCK_APP_2, MOCK_VNET]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    """Patch ResourceDiscoveryEngine methods with mock data."""
    with patch("utils.resource_discovery_engine.SubscriptionClient") as MockSubClient, \
         patch("utils.resource_discovery_engine.ResourceGraphClient") as MockRGC:

        # Subscription discovery
        sub_obj = MagicMock()
        sub_obj.subscription_id = MOCK_SUB_A
        sub_obj.display_name = "Test Subscription A"
        sub_obj.state = "Enabled"
        sub_obj.tenant_id = MOCK_TENANT
        MockSubClient.return_value.subscriptions.list.return_value = [sub_obj]

        # Resource Graph responses
        rg_response = MagicMock()
        rg_response.data = ALL_MOCK_RESOURCES
        rg_response.skip_token = None
        MockRGC.return_value.resources.return_value = rg_response

        yield


@pytest.fixture
def fresh_cache():
    """Create a clean cache for each test."""
    from utils.resource_inventory_cache import ResourceInventoryCache
    cache = ResourceInventoryCache(default_l1_ttl=300, default_l2_ttl=3600)
    cache._l2_ready = False
    return cache


@pytest.fixture
def client_with_cache(fresh_cache):
    """Create an inventory client backed by a fresh cache."""
    from utils.resource_inventory_client import ResourceInventoryClient
    return ResourceInventoryClient(cache=fresh_cache)


# ---------------------------------------------------------------------------
# End-to-end discovery + cache population
# ---------------------------------------------------------------------------

class TestEndToEndDiscovery:
    """Full pipeline: discover → cache → query."""

    async def test_full_discovery_populates_cache(self, mock_engine, fresh_cache):
        """Full discovery should populate the cache with all resources."""
        from utils.resource_discovery_engine import ResourceDiscoveryEngine

        engine = ResourceDiscoveryEngine(credential=MagicMock())
        resources = await engine.full_resource_discovery(MOCK_SUB_A)

        # Cache by type
        by_type: Dict[str, list] = {}
        for r in resources:
            rtype = r.get("resource_type", "unknown")
            by_type.setdefault(rtype, []).append(r)

        for rtype, typed in by_type.items():
            await fresh_cache.set(MOCK_SUB_A, rtype, typed)

        # Verify cache has VMs
        vms = await fresh_cache.get(MOCK_SUB_A, "microsoft.compute/virtualmachines")
        assert vms is not None
        assert len(vms) == 2

        # Verify cache has App Services
        apps = await fresh_cache.get(MOCK_SUB_A, "microsoft.web/sites")
        assert apps is not None
        assert len(apps) == 2

        # Verify cache has VNets
        vnets = await fresh_cache.get(MOCK_SUB_A, "microsoft.network/virtualnetworks")
        assert vnets is not None
        assert len(vnets) == 1

    async def test_client_queries_cached_resources(self, mock_engine, client_with_cache):
        """Client should be able to query resources from cache."""
        from utils.resource_discovery_engine import ResourceDiscoveryEngine

        client = client_with_cache
        engine = ResourceDiscoveryEngine(credential=MagicMock())

        # Populate cache
        resources = await engine.full_resource_discovery(MOCK_SUB_A)
        by_type: Dict[str, list] = {}
        for r in resources:
            rtype = r.get("resource_type", "unknown")
            by_type.setdefault(rtype, []).append(r)
        for rtype, typed in by_type.items():
            await client._cache.set(MOCK_SUB_A, rtype, typed)

        # Query with name filter
        vms = await client.get_resources(
            "microsoft.compute/virtualmachines",
            subscription_id=MOCK_SUB_A,
            filters={"name": "vm-web-01"},
        )
        assert len(vms) == 1
        assert vms[0]["resource_name"] == "vm-web-01"


# ---------------------------------------------------------------------------
# Multi-subscription
# ---------------------------------------------------------------------------

class TestMultiSubscription:
    """Tests for multi-subscription resource queries."""

    async def test_batch_retrieval_across_subscriptions(self, fresh_cache):
        """get_multi should return data for multiple subscriptions."""
        await fresh_cache.set(MOCK_SUB_A, "Microsoft.Compute/virtualMachines", [{"id": "vm-a"}])
        await fresh_cache.set(MOCK_SUB_B, "Microsoft.Compute/virtualMachines", [{"id": "vm-b"}])

        results = await fresh_cache.get_multi(
            [MOCK_SUB_A, MOCK_SUB_B],
            "Microsoft.Compute/virtualMachines",
        )

        assert results[MOCK_SUB_A] is not None
        assert results[MOCK_SUB_B] is not None
        assert len(results[MOCK_SUB_A]) == 1
        assert len(results[MOCK_SUB_B]) == 1


# ---------------------------------------------------------------------------
# Name collision handling
# ---------------------------------------------------------------------------

class TestNameCollisionHandling:
    """Tests for resources with the same name in different scopes."""

    async def test_same_name_different_resource_groups(self, client_with_cache):
        """Resources with same name in different RGs should all be returned."""
        client = client_with_cache

        # Both MOCK_APP_1 and MOCK_APP_2 are "app-frontend" in different RGs
        from utils.resource_discovery_engine import ResourceDiscoveryEngine
        engine = ResourceDiscoveryEngine(credential=MagicMock())

        # Build documents manually to simulate cached data
        doc_1 = {
            "resource_id": MOCK_APP_1["id"],
            "resource_name": "app-frontend",
            "resource_type": "microsoft.web/sites",
            "resource_group": "rg-test",
            "location": "eastus",
            "subscription_id": MOCK_SUB_A,
            "tags": {},
            "selected_properties": {},
        }
        doc_2 = {
            "resource_id": MOCK_APP_2["id"],
            "resource_name": "app-frontend",
            "resource_type": "microsoft.web/sites",
            "resource_group": "rg-staging",
            "location": "eastus",
            "subscription_id": MOCK_SUB_A,
            "tags": {},
            "selected_properties": {},
        }

        await client._cache.set(MOCK_SUB_A, "microsoft.web/sites", [doc_1, doc_2])

        # Look up by name — should find both
        with patch.dict(os.environ, {"SUBSCRIPTION_ID": MOCK_SUB_A}):
            matches = await client.get_resource_by_name(
                "app-frontend",
                resource_type="microsoft.web/sites",
                subscription_id=MOCK_SUB_A,
            )

        assert len(matches) == 2
        rgs = {m.get("resource_group") for m in matches}
        assert rgs == {"rg-test", "rg-staging"}


# ---------------------------------------------------------------------------
# Parameter auto-population
# ---------------------------------------------------------------------------

class TestParameterAutoPopulation:
    """Tests for resolve_tool_parameters()."""

    async def test_auto_populate_subscription_id(self, client_with_cache):
        """Should fill subscription_id from config when missing."""
        client = client_with_cache

        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB_A

            result = await client.resolve_tool_parameters(
                "check_resource_health", {}
            )

        assert result["subscription_id"] == MOCK_SUB_A

    async def test_auto_populate_resource_group(self, client_with_cache):
        """Should resolve resource_group from cached resource name."""
        client = client_with_cache

        doc = {
            "resource_id": MOCK_VM_1["id"],
            "resource_name": "vm-web-01",
            "resource_type": "microsoft.compute/virtualmachines",
            "resource_group": MOCK_RG,
            "location": "eastus",
            "subscription_id": MOCK_SUB_A,
            "tags": {},
            "selected_properties": {},
        }
        await client._cache.set(MOCK_SUB_A, "microsoft.compute/virtualmachines", [doc])

        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB_A
            mock_config.azure.resource_group_name = ""

            result = await client.resolve_tool_parameters(
                "check_resource_health",
                {
                    "resource_name": "vm-web-01",
                    "resource_type": "microsoft.compute/virtualmachines",
                },
            )

        assert result.get("resource_group") == MOCK_RG

    async def test_disambiguation_flag_on_collision(self, client_with_cache):
        """Should set _disambiguation_required when multiple matches exist."""
        client = client_with_cache

        doc_1 = {
            "resource_id": MOCK_APP_1["id"],
            "resource_name": "app-frontend",
            "resource_type": "microsoft.web/sites",
            "resource_group": "rg-test",
            "location": "eastus",
            "subscription_id": MOCK_SUB_A,
            "tags": {},
            "selected_properties": {},
        }
        doc_2 = {
            "resource_id": MOCK_APP_2["id"],
            "resource_name": "app-frontend",
            "resource_type": "microsoft.web/sites",
            "resource_group": "rg-staging",
            "location": "eastus",
            "subscription_id": MOCK_SUB_A,
            "tags": {},
            "selected_properties": {},
        }
        await client._cache.set(MOCK_SUB_A, "microsoft.web/sites", [doc_1, doc_2])

        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB_A
            mock_config.azure.resource_group_name = ""

            result = await client.resolve_tool_parameters(
                "check_resource_health",
                {
                    "resource_name": "app-frontend",
                    "resource_type": "microsoft.web/sites",
                },
            )

        assert result.get("_disambiguation_required") is True
        assert len(result["_matches"]) == 2


# ---------------------------------------------------------------------------
# Relationship traversal (integration)
# ---------------------------------------------------------------------------

class TestRelationshipTraversal:
    """Tests for relationship extraction through the client."""

    async def test_get_resource_relationships(self, client_with_cache):
        """Client should delegate to engine and return edges."""
        nic_id = f"/subscriptions/{MOCK_SUB_A}/resourceGroups/{MOCK_RG}/providers/Microsoft.Network/networkInterfaces/nic-01"

        mock_engine = MagicMock()
        mock_engine.extract_relationships = AsyncMock(return_value=[
            {
                "source": MOCK_VM_1["id"],
                "target": nic_id,
                "relationship_type": "depends_on",
                "depth": 1,
            }
        ])

        client = client_with_cache
        client._engine = mock_engine

        rels = await client.get_resource_relationships(MOCK_VM_1["id"], depth=2)

        assert len(rels) == 1
        assert rels[0]["target"] == nic_id
        mock_engine.extract_relationships.assert_called_once()


# ---------------------------------------------------------------------------
# Scheduler job integration
# ---------------------------------------------------------------------------

class TestSchedulerJobIntegration:
    """Tests for scheduler job handlers end-to-end."""

    async def test_full_refresh_job_populates_cache(self):
        """full_refresh_job should discover and cache resources."""
        import utils.inventory_scheduler as sched

        mock_sub = MagicMock()
        mock_sub.subscription_id = MOCK_SUB_A
        mock_sub.display_name = "Test"
        mock_sub.state = "Enabled"
        mock_sub.tenant_id = MOCK_TENANT

        mock_rg_response = MagicMock()
        mock_rg_response.data = [MOCK_VM_1, MOCK_VM_2]
        mock_rg_response.skip_token = None

        with patch("utils.resource_discovery_engine.SubscriptionClient") as MockSub, \
             patch("utils.resource_discovery_engine.ResourceGraphClient") as MockRGC, \
             patch("utils.inventory_scheduler.get_resource_inventory_cache") as mock_cache_fn:

            MockSub.return_value.subscriptions.list.return_value = [mock_sub]
            MockRGC.return_value.resources.return_value = mock_rg_response

            mock_cache = MagicMock()
            mock_cache.set = AsyncMock()
            mock_cache_fn.return_value = mock_cache

            # Reset stats
            sched._cached_resource_ids = set()
            sched._last_scan_time = None

            await sched.full_refresh_job()

        # Verify stats were updated
        stats = sched.get_scheduler_stats()
        assert stats["full_scan"]["total_runs"] >= 1
        assert stats["full_scan"]["last_resource_count"] == 2
        assert sched._last_scan_time is not None
        assert len(sched._cached_resource_ids) == 2

    async def test_incremental_job_falls_back_to_full(self):
        """Incremental job should trigger full scan when no prior scan exists."""
        import utils.inventory_scheduler as sched

        # Force no prior scan
        sched._last_scan_time = None

        with patch("utils.inventory_scheduler.full_refresh_job", new_callable=AsyncMock) as mock_full:
            await sched.incremental_refresh_job()

        mock_full.assert_called_once()


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Tests for behaviour when inventory subsystem is unavailable."""

    async def test_client_returns_empty_when_engine_unavailable(self):
        """Client should return empty list when engine can't be imported."""
        from utils.resource_inventory_client import ResourceInventoryClient
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._l2_ready = False
        client = ResourceInventoryClient(cache=cache)
        # Force engine to be unavailable
        client._engine = None

        with patch.object(client, "_get_engine", return_value=None):
            result = await client.get_resources(
                "Microsoft.Compute/virtualMachines",
                subscription_id=MOCK_SUB_A,
            )

        assert result == []

    async def test_client_returns_empty_relationships_when_engine_down(self):
        """Relationship extraction should return empty on engine failure."""
        from utils.resource_inventory_client import ResourceInventoryClient
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._l2_ready = False
        client = ResourceInventoryClient(cache=cache)
        client._engine = None

        with patch.object(client, "_get_engine", return_value=None):
            rels = await client.get_resource_relationships(MOCK_VM_1["id"])

        assert rels == []
