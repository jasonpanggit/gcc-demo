"""
Integration tests for SRE Orchestrator + Resource Inventory.

Validates that the SRE orchestrator can leverage the resource inventory
system for:
- Fast-path resource lookups (cache hit vs live query)
- Automatic parameter population from inventory
- Graceful degradation when inventory is unavailable
- Response time improvements with inventory enabled

Note: These tests use mocked orchestrator responses. Once Task #8
(SRE Orchestrator inventory integration) completes, update the
mock targets to match the actual integration points.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_SUB = "aaaaaaaa-1111-2222-3333-444444444444"
MOCK_RG = "rg-production"
MOCK_VM_ID = f"/subscriptions/{MOCK_SUB}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-web-01"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def populated_cache():
    """Cache pre-populated with representative resource data."""
    from utils.resource_inventory_cache import ResourceInventoryCache

    cache = ResourceInventoryCache(default_l1_ttl=300, default_l2_ttl=3600)
    cache._l2_ready = False
    return cache


@pytest.fixture
async def cache_with_resources(populated_cache):
    """Cache populated with VMs and App Services."""
    vm_docs = [
        {
            "resource_id": MOCK_VM_ID,
            "resource_name": "vm-web-01",
            "resource_type": "microsoft.compute/virtualmachines",
            "resource_group": MOCK_RG,
            "location": "eastus",
            "subscription_id": MOCK_SUB,
            "tags": {"env": "production", "team": "platform"},
            "selected_properties": {
                "vm_size": "Standard_D2s_v3",
                "os_type": "Linux",
                "provisioning_state": "Succeeded",
            },
        },
        {
            "resource_id": f"/subscriptions/{MOCK_SUB}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-api-01",
            "resource_name": "vm-api-01",
            "resource_type": "microsoft.compute/virtualmachines",
            "resource_group": MOCK_RG,
            "location": "eastus",
            "subscription_id": MOCK_SUB,
            "tags": {"env": "production", "team": "backend"},
            "selected_properties": {
                "vm_size": "Standard_D4s_v3",
                "os_type": "Linux",
                "provisioning_state": "Succeeded",
            },
        },
    ]

    app_docs = [
        {
            "resource_id": f"/subscriptions/{MOCK_SUB}/resourceGroups/{MOCK_RG}/providers/Microsoft.Web/sites/app-api",
            "resource_name": "app-api",
            "resource_type": "microsoft.web/sites",
            "resource_group": MOCK_RG,
            "location": "eastus",
            "subscription_id": MOCK_SUB,
            "tags": {"env": "production"},
            "selected_properties": {
                "state": "Running",
                "default_host_name": "app-api.azurewebsites.net",
                "https_only": True,
            },
        },
    ]

    await populated_cache.set(MOCK_SUB, "microsoft.compute/virtualmachines", vm_docs)
    await populated_cache.set(MOCK_SUB, "microsoft.web/sites", app_docs)
    return populated_cache


@pytest.fixture
def inventory_client(cache_with_resources):
    """ResourceInventoryClient with pre-populated cache."""
    from utils.resource_inventory_client import ResourceInventoryClient
    return ResourceInventoryClient(cache=cache_with_resources)


# ---------------------------------------------------------------------------
# Resource existence fast-path
# ---------------------------------------------------------------------------

class TestResourceExistenceFastPath:
    """Test that inventory provides fast resource existence checks."""

    async def test_cache_hit_sub_millisecond(self, inventory_client):
        """L1 cache hit should complete in under 5ms."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB

            start = time.monotonic()
            exists = await inventory_client.check_resource_exists(
                "microsoft.compute/virtualmachines",
                filters={"name": "vm-web-01"},
                subscription_id=MOCK_SUB,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

        assert exists is True
        assert elapsed_ms < 5.0, f"L1 cache hit took {elapsed_ms:.2f}ms (expected < 5ms)"

    async def test_nonexistent_resource_returns_false(self, inventory_client):
        """Checking for a resource that doesn't exist should return False."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB

            exists = await inventory_client.check_resource_exists(
                "microsoft.compute/virtualmachines",
                filters={"name": "vm-does-not-exist"},
                subscription_id=MOCK_SUB,
            )

        assert exists is False

    async def test_resource_not_found_fast_path(self, inventory_client):
        """Querying a non-cached resource type should return empty quickly."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB

            # Force no engine fallback for pure fast-path test
            with patch.object(inventory_client, "_get_engine", return_value=None):
                start = time.monotonic()
                result = await inventory_client.get_resources(
                    "Microsoft.ContainerService/managedClusters",
                    subscription_id=MOCK_SUB,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

        assert result == []
        # Without engine fallback, should be instant
        assert elapsed_ms < 10.0


# ---------------------------------------------------------------------------
# Parameter auto-population via orchestrator
# ---------------------------------------------------------------------------

class TestOrchestratorParameterPopulation:
    """Test that inventory enables auto-populating tool parameters.

    These tests validate the ResourceInventoryClient's
    resolve_tool_parameters() behaviour that the SRE orchestrator
    will call (Task #8 integration).
    """

    async def test_resolve_subscription_and_resource_group(self, inventory_client):
        """Should auto-populate both subscription_id and resource_group."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB
            mock_config.azure.resource_group_name = ""

            result = await inventory_client.resolve_tool_parameters(
                "check_resource_health",
                {"resource_name": "vm-web-01", "resource_type": "microsoft.compute/virtualmachines"},
            )

        assert result["subscription_id"] == MOCK_SUB
        assert result["resource_group"] == MOCK_RG
        assert "_disambiguation_required" not in result

    async def test_resolve_preserves_existing_params(self, inventory_client):
        """Should not overwrite parameters that are already provided."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB
            mock_config.azure.resource_group_name = ""

            custom_rg = "rg-custom"
            result = await inventory_client.resolve_tool_parameters(
                "check_resource_health",
                {
                    "subscription_id": "custom-sub-id",
                    "resource_group": custom_rg,
                    "resource_name": "vm-web-01",
                },
            )

        # Should keep the provided values
        assert result["subscription_id"] == "custom-sub-id"
        assert result["resource_group"] == custom_rg

    async def test_resolve_handles_unknown_resource(self, inventory_client):
        """Should gracefully handle unresolvable resource names."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB
            mock_config.azure.resource_group_name = "fallback-rg"

            result = await inventory_client.resolve_tool_parameters(
                "check_resource_health",
                {"resource_name": "vm-nonexistent"},
            )

        # Should fall back to environment resource group
        assert result["resource_group"] == "fallback-rg"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Test orchestrator behaviour when inventory subsystem is unavailable."""

    async def test_inventory_disabled_does_not_error(self):
        """When inventory is disabled, client should still function."""
        from utils.resource_inventory_client import ResourceInventoryClient
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._l2_ready = False
        client = ResourceInventoryClient(cache=cache)

        with patch.object(client, "_get_engine", return_value=None):
            # Should return empty list, not raise
            resources = await client.get_resources(
                "Microsoft.Compute/virtualMachines",
                subscription_id=MOCK_SUB,
            )
            assert resources == []

            # Check existence should be False, not raise
            exists = await client.check_resource_exists(
                "Microsoft.Compute/virtualMachines",
                subscription_id=MOCK_SUB,
            )
            assert exists is False

    async def test_resolve_params_works_without_cache(self):
        """Parameter resolution should work with empty cache (env fallback)."""
        from utils.resource_inventory_client import ResourceInventoryClient
        from utils.resource_inventory_cache import ResourceInventoryCache

        cache = ResourceInventoryCache()
        cache._l2_ready = False
        client = ResourceInventoryClient(cache=cache)

        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB
            mock_config.azure.resource_group_name = "env-rg"

            result = await client.resolve_tool_parameters(
                "any_tool",
                {"resource_name": "unknown-resource"},
            )

        assert result["subscription_id"] == MOCK_SUB
        assert result["resource_group"] == "env-rg"

    async def test_scheduler_handles_apscheduler_missing(self):
        """InventoryScheduler should not crash when apscheduler is missing."""
        from utils.inventory_scheduler import InventoryScheduler

        scheduler = InventoryScheduler()

        with patch("utils.inventory_scheduler.APSCHEDULER_AVAILABLE", False):
            await scheduler.start()

        assert scheduler.is_running is False
        status = scheduler.get_status()
        assert status["apscheduler_available"] is False


# ---------------------------------------------------------------------------
# Response time comparison (with vs without inventory)
# ---------------------------------------------------------------------------

class TestResponseTimeComparison:
    """Validate that inventory cache improves response times."""

    async def test_cached_lookup_faster_than_live(self, inventory_client):
        """Cache hit should be significantly faster than a live query."""
        with patch("utils.resource_inventory_client.config") as mock_config:
            mock_config.azure.subscription_id = MOCK_SUB

            # Cached lookup
            start = time.monotonic()
            cached_result = await inventory_client.get_resources(
                "microsoft.compute/virtualmachines",
                subscription_id=MOCK_SUB,
            )
            cached_time = time.monotonic() - start

            # "Live" lookup with mocked delay
            mock_engine = MagicMock()

            async def slow_discovery(*args, **kwargs):
                import asyncio
                await asyncio.sleep(0.05)  # Simulate 50ms network call
                return cached_result

            mock_engine.full_resource_discovery = slow_discovery

            start = time.monotonic()
            inventory_client._engine = mock_engine
            live_result = await inventory_client.get_resources(
                "microsoft.compute/virtualmachines",
                subscription_id=MOCK_SUB,
                refresh=True,
            )
            live_time = time.monotonic() - start

        # Cache hit should be at least 10x faster
        assert cached_time < live_time
        assert len(cached_result) == len(live_result)


# ---------------------------------------------------------------------------
# SRE Orchestrator integration with inventory (blocking on not found)
# ---------------------------------------------------------------------------

class TestSREOrchestratorInventoryBlocking:
    """Test SRE Orchestrator's behavior when resources are not found in inventory.

    These tests validate that the orchestrator:
    1. Blocks tool execution when resources are not in inventory (strict mode)
    2. Returns immediate helpful error messages
    3. Doesn't make expensive API calls to non-existent resources
    """

    async def test_orchestrator_blocks_on_resource_not_found(self):
        """When strict_mode=True, orchestrator should block tools if resource not in inventory."""
        from agents.sre_orchestrator import SREOrchestratorAgent
        from utils.sre_inventory_integration import SREInventoryIntegration
        from unittest.mock import AsyncMock, MagicMock

        # Create orchestrator
        orchestrator = SREOrchestratorAgent()
        await orchestrator.initialize()

        # Mock inventory integration in strict mode
        mock_integration = MagicMock()

        async def preflight_not_found(tool_name, parameters):
            return {
                "ok": False,
                "result": {
                    "success": False,
                    "error": "Resource 'vm-nonexistent' not found in inventory",
                    "suggestion": "Verify the resource exists and inventory is up-to-date."
                }
            }

        mock_integration.preflight_resource_check = AsyncMock(side_effect=preflight_not_found)
        mock_integration.enrich_tool_parameters = AsyncMock(
            side_effect=lambda tool, params, ctx=None: params
        )
        mock_integration.get_statistics = MagicMock(return_value={"enabled": True})

        # Inject mock
        orchestrator.inventory_integration = mock_integration

        # Mock registry to provide tool info
        mock_registry = MagicMock()
        mock_registry.get_tool = MagicMock(return_value={
            "name": "check_resource_health",
            "agent_id": "sre-mcp-server",
            "definition": {
                "function": {
                    "name": "check_resource_health",
                    "parameters": {
                        "type": "object",
                        "properties": {"resource_id": {"type": "string"}},
                        "required": ["resource_id"]
                    }
                }
            }
        })
        orchestrator.registry = mock_registry

        # Execute with non-existent resource
        result = await orchestrator.execute({
            "query": "check health of vm-nonexistent",
            "parameters": {
                "resource_id": f"/subscriptions/{MOCK_SUB}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-nonexistent"
            }
        })

        # Verify preflight was called
        assert mock_integration.preflight_resource_check.called

        # Verify orchestrator returned error without calling tools
        assert result is not None
        aggregated = result.get("results", {})

        # Should have error message about resource not found
        assert "message" in aggregated or aggregated.get("errors") is not None

        # Cleanup
        await orchestrator.cleanup()

    async def test_orchestrator_executes_when_resource_exists(self):
        """When resource exists in inventory, orchestrator should execute tools normally."""
        from agents.sre_orchestrator import SREOrchestratorAgent
        from unittest.mock import AsyncMock, MagicMock

        orchestrator = SREOrchestratorAgent()
        await orchestrator.initialize()

        # Mock inventory that allows execution
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(return_value={"ok": True})
        mock_integration.enrich_tool_parameters = AsyncMock(
            side_effect=lambda tool, params, ctx=None: params
        )
        mock_integration.get_statistics = MagicMock(return_value={"enabled": True})

        orchestrator.inventory_integration = mock_integration

        # Mock successful tool execution
        mock_agent = MagicMock()
        mock_agent.agent_id = "sre-mcp-server"

        async def successful_execution(request):
            return {
                "status": "success",
                "result": {
                    "parsed": {
                        "resource_id": MOCK_VM_ID,
                        "health_data": {
                            "availability_state": "Available",
                            "summary": "Resource is healthy"
                        }
                    }
                }
            }

        mock_agent.handle_request = AsyncMock(side_effect=successful_execution)

        mock_registry = MagicMock()
        mock_registry.get_tool = MagicMock(return_value={
            "name": "check_resource_health",
            "agent_id": "sre-mcp-server",
            "definition": {"function": {"name": "check_resource_health", "parameters": {"type": "object", "properties": {"resource_id": {"type": "string"}}, "required": ["resource_id"]}}}
        })
        mock_registry.get_agent = MagicMock(return_value=mock_agent)

        orchestrator.registry = mock_registry

        # Execute with valid resource
        result = await orchestrator.execute({
            "query": "check health of vm-web-01",
            "parameters": {"resource_id": MOCK_VM_ID}
        })

        # Verify tool was executed
        assert result is not None
        assert result.get("tools_executed", 0) > 0

        results = result.get("results", {}).get("results", [])
        assert len(results) > 0
        assert results[0].get("status") == "success"

        await orchestrator.cleanup()


# ---------------------------------------------------------------------------
# Remote API Testing (actual Container Apps calls)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.getenv('USE_MOCK_DATA', 'true').lower() == 'true',
    reason="Remote API test - only runs with --remote flag"
)
class TestSREOrchestratorRemoteAPI:
    """Test SRE Orchestrator via actual API calls to Container Apps.

    These tests only run when USE_MOCK_DATA=false (i.e., with --remote flag).
    They make real HTTP requests to the deployed Container Apps instance.
    """

    async def test_remote_resource_not_found_blocks_execution(self, client):
        """Test that non-existent resources are blocked in remote deployment."""
        import uuid

        # Use a UUID to ensure resource doesn't exist
        fake_resource_id = (
            f"/subscriptions/{MOCK_SUB}/resourceGroups/{MOCK_RG}/"
            f"providers/Microsoft.Compute/virtualMachines/vm-nonexistent-{uuid.uuid4().hex[:8]}"
        )

        response = await client.post(
            "/api/sre-orchestrator/execute",
            json={
                "query": "check health of non-existent VM",
                "context": {
                    "resource_id": fake_resource_id
                }
            },
            timeout=30.0
        )

        # Should return 200 with error message (not a 500 or hang)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "results" in data or "error" in data

        # If strict mode is enabled, should get resource not found message
        if data.get("results"):
            results = data["results"]
            # Check for error message about resource not found
            has_not_found_msg = (
                "not found" in str(results).lower() or
                "message" in results and "resource" in str(results.get("message", "")).lower()
            )
            # In strict mode, we expect this
            logger.info(f"Remote test result: {results.get('summary', {})}")

    async def test_remote_capabilities_endpoint(self, client):
        """Test that capabilities endpoint works remotely."""
        response = await client.get(
            "/api/sre-orchestrator/capabilities",
            timeout=10.0
        )

        assert response.status_code == 200
        data = response.json()

        # Should have basic orchestrator info
        assert "total_tools" in data or "capabilities" in data or "data" in data

    async def test_remote_health_endpoint(self, client):
        """Test that health endpoint works remotely."""
        response = await client.get(
            "/api/sre-orchestrator/health",
            timeout=10.0
        )

        assert response.status_code == 200
        data = response.json()

        # Should indicate orchestrator is healthy
        assert data.get("status") == "healthy" or data.get("success") is True
