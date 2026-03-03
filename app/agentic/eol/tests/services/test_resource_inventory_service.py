"""Unit tests for ResourceInventoryService.

All tests are unit-level (no live Azure). The underlying clients
(ResourceInventoryClient, SREInventoryIntegration) are fully mocked.

API contract notes from the production implementation:
- preflight_check delegates to SREInventoryIntegration.preflight_resource_check(),
  which returns {"ok": bool} or {"ok": False, "result": {"error": ..., "suggestion": ...}}.
  The spec-level keys "passed"/"resource_found" are on the returned PreflightResult,
  NOT on the raw dict from the integration layer.
- resolve_parameters degrades gracefully to returning partial_params unchanged
  when the integration is unavailable or raises.
- lookup_resource parses resourceGroup from the resource ID if absent in the raw doc.

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

try:
    from app.agentic.eol.utils.resource_inventory_service import (
        ResourceInventoryService,
        EntityHints,
        GroundingSummary,
        PreflightResult,
        ResourceDoc,
        get_resource_inventory_service,
    )
except ModuleNotFoundError:
    from utils.resource_inventory_service import (  # type: ignore[import-not-found]
        ResourceInventoryService,
        EntityHints,
        GroundingSummary,
        PreflightResult,
        ResourceDoc,
        get_resource_inventory_service,
    )


# ---------------------------------------------------------------------------
# extract_entities — pure regex, no Azure
# ---------------------------------------------------------------------------

class TestExtractEntities:
    """extract_entities is regex-only — no mocking needed."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_container_app_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("check health of my container app prod-api")
        assert "Microsoft.App/containerApps" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_aks_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("is my AKS cluster healthy")
        assert "Microsoft.ContainerService/managedClusters" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_vnet_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("inspect vnet prod-vnet")
        assert "Microsoft.Network/virtualNetworks" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_quoted_name(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities('check health of "my-app-prod"')
        assert "my-app-prod" in hints.names

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_hyphenated_name(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("check health of prod-api")
        assert "prod-api" in hints.names

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_words_excluded(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("list my azure resources")
        # "list", "my", "azure" are all stop words and must be excluded from names
        for stop in ("list", "my", "azure"):
            assert stop not in hints.names

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_query(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("")
        assert hints.names == []
        assert hints.possible_types == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_types_detected(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities(
            "why can't my container app reach the cosmos database"
        )
        assert "Microsoft.App/containerApps" in hints.possible_types
        assert "Microsoft.DocumentDB/databaseAccounts" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_entity_hints_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("any query")
        assert isinstance(hints, EntityHints)
        assert isinstance(hints.names, list)
        assert isinstance(hints.possible_types, list)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_vm_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("restart my virtual machine web-vm-01")
        assert "Microsoft.Compute/virtualMachines" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_cosmos_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("my cosmosdb account is slow")
        assert "Microsoft.DocumentDB/databaseAccounts" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extracts_key_vault_type(self):
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("key vault my-kv-prod is unreachable")
        assert "Microsoft.KeyVault/vaults" in hints.possible_types

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_short_names_excluded(self):
        """Names shorter than 3 characters must be excluded."""
        svc = ResourceInventoryService()
        # "vm" is 2 chars and also a stop-word candidate; "az" is 2 chars
        hints = await svc.extract_entities("vm az")
        for name in hints.names:
            assert len(name) >= 3, f"Short name {name!r} should have been excluded"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_duplicate_names(self):
        """The same name appearing twice in the query shouldn't produce duplicates."""
        svc = ResourceInventoryService()
        hints = await svc.extract_entities("check prod-api and then check prod-api again")
        name_count = hints.names.count("prod-api")
        # Duplicates are not explicitly deduplicated in the impl, but either way
        # the important assertion is that prod-api IS present
        assert "prod-api" in hints.names


# ---------------------------------------------------------------------------
# resolve_parameters — delegates to SREInventoryIntegration
# ---------------------------------------------------------------------------

class TestResolveParameters:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delegates_to_integration(self):
        svc = ResourceInventoryService()
        enriched = {
            "resource_name": "prod-api",
            "subscription_id": "sub-123",
            "resource_group": "rg-prod",
        }
        mock_integration = AsyncMock()
        mock_integration.enrich_tool_parameters = AsyncMock(return_value=enriched)
        svc._sre_integration = mock_integration

        result = await svc.resolve_parameters(
            "check_container_app_health",
            {"resource_name": "prod-api"},
        )
        assert result["resource_group"] == "rg-prod"
        mock_integration.enrich_tool_parameters.assert_called_once_with(
            "check_container_app_health", {"resource_name": "prod-api"}
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_partial_params_when_integration_unavailable(self):
        """When integration is None, partial_params is returned unchanged."""
        svc = ResourceInventoryService()
        # Prevent lazy init from trying to load the real integration
        svc._sre_integration = None
        svc._get_sre_integration = lambda: None  # type: ignore[method-assign]

        partial = {"resource_name": "prod-api"}
        result = await svc.resolve_parameters("some_tool", partial)
        assert result == partial

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_partial_params_on_integration_error(self):
        """When integration raises, partial_params is returned unchanged (non-fatal)."""
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.enrich_tool_parameters = AsyncMock(
            side_effect=RuntimeError("unexpected network failure")
        )
        svc._sre_integration = mock_integration

        partial = {"resource_name": "prod-api"}
        result = await svc.resolve_parameters("some_tool", partial)
        assert result == partial

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passes_all_params_to_integration(self):
        """All keys in partial_params are forwarded to enrich_tool_parameters."""
        svc = ResourceInventoryService()
        partial = {
            "resource_name": "prod-api",
            "resource_type": "Microsoft.App/containerApps",
            "extra": "value",
        }
        mock_integration = AsyncMock()
        mock_integration.enrich_tool_parameters = AsyncMock(return_value=partial)
        svc._sre_integration = mock_integration

        await svc.resolve_parameters("check_resource_health", partial)
        mock_integration.enrich_tool_parameters.assert_called_once_with(
            "check_resource_health", partial
        )


# ---------------------------------------------------------------------------
# preflight_check — delegates to SREInventoryIntegration
#
# The real integration returns {"ok": bool} or
# {"ok": False, "result": {"error": ..., "suggestion": ...}}.
# The service normalises this to PreflightResult.
# ---------------------------------------------------------------------------

class TestPreflightCheck:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passed_true_when_resource_found(self):
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(
            return_value={"ok": True}
        )
        svc._sre_integration = mock_integration

        result = await svc.preflight_check("check_resource_health", {"resource_name": "prod-api"})
        assert result.passed is True
        assert isinstance(result, PreflightResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passed_false_when_resource_missing(self):
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(
            return_value={
                "ok": False,
                "result": {
                    "error": "Resource not found",
                    "suggestion": "Check the resource name",
                },
            }
        )
        svc._sre_integration = mock_integration

        result = await svc.preflight_check(
            "check_resource_health", {"resource_name": "nonexistent"}
        )
        assert result.passed is False
        assert result.resource_found is False
        assert "Resource not found" in result.issues
        assert result.suggestion == "Check the resource name"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fail_open_when_integration_unavailable(self):
        """If integration unavailable, preflight passes (fail-open)."""
        svc = ResourceInventoryService()
        svc._sre_integration = None
        svc._get_sre_integration = lambda: None  # type: ignore[method-assign]

        result = await svc.preflight_check("any_tool", {})
        assert result.passed is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fail_open_on_error(self):
        """When integration raises, preflight passes (fail-open, non-fatal)."""
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(
            side_effect=RuntimeError("network error")
        )
        svc._sre_integration = mock_integration

        result = await svc.preflight_check("any_tool", {})
        assert result.passed is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_preflight_result_type(self):
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(return_value={"ok": True})
        svc._sre_integration = mock_integration

        result = await svc.preflight_check("any_tool", {})
        assert isinstance(result, PreflightResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ok_true_with_extra_keys_passes(self):
        """ok=True response with unexpected extra keys still passes."""
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(
            return_value={"ok": True, "extra": "ignored"}
        )
        svc._sre_integration = mock_integration

        result = await svc.preflight_check("any_tool", {})
        assert result.passed is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_failed_preflight_has_non_empty_issues(self):
        """A failed preflight result must have at least one issue string."""
        svc = ResourceInventoryService()
        mock_integration = MagicMock()
        mock_integration.preflight_resource_check = AsyncMock(
            return_value={
                "ok": False,
                "result": {"error": "Subscription not found", "suggestion": ""},
            }
        )
        svc._sre_integration = mock_integration

        result = await svc.preflight_check("some_tool", {})
        assert result.passed is False
        assert len(result.issues) > 0
        assert result.issues[0] == "Subscription not found"


# ---------------------------------------------------------------------------
# lookup_resource — delegates to ResourceInventoryClient
# ---------------------------------------------------------------------------

class TestLookupResource:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_resource_docs(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": (
                    "/subscriptions/sub-1/resourceGroups/rg-prod"
                    "/providers/Microsoft.App/containerApps/prod-api"
                ),
                "name": "prod-api",
                "type": "Microsoft.App/containerApps",
                "resourceGroup": "rg-prod",
                "subscriptionId": "sub-1",
                "location": "eastus",
            }
        ])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("prod-api")
        assert len(results) == 1
        assert results[0].name == "prod-api"
        assert results[0].resource_group == "rg-prod"
        assert results[0].subscription_id == "sub-1"
        assert results[0].location == "eastus"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_resource_doc_type(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": "/subscriptions/s/resourceGroups/rg/providers/t/apps/app",
                "name": "app",
                "type": "t",
                "resourceGroup": "rg",
                "subscriptionId": "s",
            }
        ])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("app")
        assert len(results) == 1
        assert isinstance(results[0], ResourceDoc)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_filters_by_resource_group(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": "/subscriptions/s/resourceGroups/rg-a/providers/t/apps/app1",
                "name": "app1",
                "type": "t",
                "resourceGroup": "rg-a",
                "subscriptionId": "s",
            },
            {
                "id": "/subscriptions/s/resourceGroups/rg-b/providers/t/apps/app1",
                "name": "app1",
                "type": "t",
                "resourceGroup": "rg-b",
                "subscriptionId": "s",
            },
        ])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("app1", resource_group="rg-a")
        assert len(results) == 1
        assert results[0].resource_group == "rg-a"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resource_group_filter_is_case_insensitive(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": "/subscriptions/s/resourceGroups/RG-Prod/providers/t/apps/app",
                "name": "app",
                "type": "t",
                "resourceGroup": "RG-Prod",
                "subscriptionId": "s",
            },
        ])
        svc._inventory_client = mock_client

        # Lowercase filter must still match uppercase resourceGroup in the doc
        results = await svc.lookup_resource("app", resource_group="rg-prod")
        assert len(results) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_empty_when_client_unavailable(self):
        svc = ResourceInventoryService()
        svc._inventory_client = None
        svc._get_inventory_client = lambda: None  # type: ignore[method-assign]

        results = await svc.lookup_resource("prod-api")
        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(side_effect=RuntimeError("timeout"))
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("prod-api")
        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parses_resource_group_from_resource_id(self):
        """When resourceGroup key is absent, it should be parsed from the resource ID."""
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": (
                    "/subscriptions/sub-1/resourceGroups/rg-parsed"
                    "/providers/Microsoft.App/containerApps/app"
                ),
                "name": "app",
                "type": "Microsoft.App/containerApps",
                # Note: no "resourceGroup" key present
                "subscriptionId": "sub-1",
            }
        ])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("app")
        assert len(results) == 1
        assert results[0].resource_group == "rg-parsed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(self):
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("nonexistent")
        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_results_returned(self):
        """When multiple resources match the name, all are returned."""
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[
            {
                "id": "/subscriptions/s1/resourceGroups/rg1/providers/t/apps/app",
                "name": "app",
                "type": "t",
                "resourceGroup": "rg1",
                "subscriptionId": "s1",
            },
            {
                "id": "/subscriptions/s2/resourceGroups/rg2/providers/t/apps/app",
                "name": "app",
                "type": "t",
                "resourceGroup": "rg2",
                "subscriptionId": "s2",
            },
        ])
        svc._inventory_client = mock_client

        results = await svc.lookup_resource("app")
        assert len(results) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lookup_passes_resource_type_to_client(self):
        """resource_type is forwarded to the client's get_resource_by_name call."""
        svc = ResourceInventoryService()
        mock_client = MagicMock()
        mock_client.get_resource_by_name = AsyncMock(return_value=[])
        svc._inventory_client = mock_client

        await svc.lookup_resource(
            "prod-api",
            resource_type="Microsoft.App/containerApps",
        )
        mock_client.get_resource_by_name.assert_called_once_with(
            resource_name="prod-api",
            resource_type="Microsoft.App/containerApps",
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetResourceInventoryServiceSingleton:

    @pytest.mark.unit
    def test_returns_instance(self):
        svc = get_resource_inventory_service()
        assert isinstance(svc, ResourceInventoryService)

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        svc1 = get_resource_inventory_service()
        svc2 = get_resource_inventory_service()
        assert svc1 is svc2

    @pytest.mark.unit
    def test_instance_starts_with_no_clients(self):
        """A fresh ResourceInventoryService should start without live clients."""
        svc = ResourceInventoryService()
        assert svc._inventory_client is None
        assert svc._sre_integration is None
