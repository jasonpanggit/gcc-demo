"""
Test suite for ResourceDiscoveryEngine.

Tests discovery, incremental detection, relationship extraction,
property enrichment, tag security filtering, and error handling
with mocked Azure SDK responses.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_SUB_ID = "12345678-1234-1234-1234-123456789012"
MOCK_TENANT_ID = "abcdef00-1234-5678-9abc-def012345678"
MOCK_RG = "rg-test"


@pytest.fixture
def mock_subscription():
    """Mock Azure subscription object."""
    sub = MagicMock()
    sub.subscription_id = MOCK_SUB_ID
    sub.display_name = "Test Subscription"
    sub.state = "Enabled"
    sub.tenant_id = MOCK_TENANT_ID
    return sub


@pytest.fixture
def mock_resource_graph_row():
    """Single raw resource row as returned by Resource Graph."""
    return {
        "id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-test",
        "name": "vm-test",
        "type": "Microsoft.Compute/virtualMachines",
        "location": "eastus",
        "resourceGroup": MOCK_RG,
        "subscriptionId": MOCK_SUB_ID,
        "tags": {"env": "dev", "secretKey": "should-be-redacted"},
        "sku": None,
        "kind": None,
        "identity": None,
        "managedBy": None,
        "plan": None,
        "zones": None,
        "extendedLocation": None,
        "properties": {
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "storageProfile": {"osDisk": {"osType": "Linux"}},
            "provisioningState": "Succeeded",
        },
    }


@pytest.fixture
def mock_app_service_row():
    """App Service resource row."""
    return {
        "id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Web/sites/app-test",
        "name": "app-test",
        "type": "Microsoft.Web/sites",
        "location": "westus",
        "resourceGroup": MOCK_RG,
        "subscriptionId": MOCK_SUB_ID,
        "tags": {"team": "platform"},
        "sku": None,
        "kind": "app,linux",
        "identity": None,
        "managedBy": None,
        "plan": None,
        "zones": None,
        "extendedLocation": None,
        "properties": {
            "kind": "app,linux",
            "state": "Running",
            "defaultHostName": "app-test.azurewebsites.net",
            "httpsOnly": True,
        },
    }


@pytest.fixture
def engine():
    """Create a ResourceDiscoveryEngine with a mocked credential."""
    from utils.resource_discovery_engine import ResourceDiscoveryEngine
    return ResourceDiscoveryEngine(credential=MagicMock())


# ---------------------------------------------------------------------------
# discover_all_subscriptions
# ---------------------------------------------------------------------------

class TestDiscoverAllSubscriptions:
    """Tests for discover_all_subscriptions()."""

    async def test_returns_subscription_list(self, engine, mock_subscription):
        """Should list all tenant subscriptions with correct fields."""
        with patch("utils.resource_discovery_engine.SubscriptionClient") as MockSubClient:
            mock_client = MockSubClient.return_value
            mock_client.subscriptions.list.return_value = [mock_subscription]

            result = await engine.discover_all_subscriptions()

            assert len(result) == 1
            sub = result[0]
            assert sub["subscription_id"] == MOCK_SUB_ID
            assert sub["display_name"] == "Test Subscription"
            assert sub["state"] == "Enabled"
            assert sub["tenant_id"] == MOCK_TENANT_ID
            assert "discovered_at" in sub

    async def test_handles_multiple_subscriptions(self, engine):
        """Should return all subscriptions when tenant has multiple."""
        subs = []
        for i in range(3):
            s = MagicMock()
            s.subscription_id = f"sub-{i}"
            s.display_name = f"Sub {i}"
            s.state = "Enabled"
            s.tenant_id = MOCK_TENANT_ID
            subs.append(s)

        with patch("utils.resource_discovery_engine.SubscriptionClient") as MockSubClient:
            MockSubClient.return_value.subscriptions.list.return_value = subs
            result = await engine.discover_all_subscriptions()

        assert len(result) == 3

    async def test_empty_tenant(self, engine):
        """Should return empty list when no subscriptions are accessible."""
        with patch("utils.resource_discovery_engine.SubscriptionClient") as MockSubClient:
            MockSubClient.return_value.subscriptions.list.return_value = []
            result = await engine.discover_all_subscriptions()

        assert result == []


# ---------------------------------------------------------------------------
# full_resource_discovery
# ---------------------------------------------------------------------------

class TestFullResourceDiscovery:
    """Tests for full_resource_discovery()."""

    async def test_returns_cosmos_ready_documents(self, engine, mock_resource_graph_row):
        """Should return documents with Cosmos DB fields."""
        with patch.object(engine, "_execute_graph_query", return_value=[mock_resource_graph_row]):
            docs = await engine.full_resource_discovery(MOCK_SUB_ID)

        assert len(docs) == 1
        doc = docs[0]
        # Cosmos DB fields
        assert "id" in doc
        assert "partition_key" in doc
        assert doc["partition_key"] == MOCK_SUB_ID
        # Resource identity
        assert doc["resource_name"] == "vm-test"
        assert doc["resource_type"] == "microsoft.compute/virtualmachines"
        assert doc["location"] == "eastus"
        assert doc["resource_group"] == MOCK_RG
        # Timestamps
        assert "discovered_at" in doc
        assert "last_seen" in doc
        # TTL
        assert doc["ttl"] == 604800

    async def test_tag_security_filtering(self, engine, mock_resource_graph_row):
        """Should redact tag values containing sensitive keywords."""
        with patch.object(engine, "_execute_graph_query", return_value=[mock_resource_graph_row]):
            docs = await engine.full_resource_discovery(MOCK_SUB_ID)

        tags = docs[0]["tags"]
        assert tags["env"] == "dev"
        assert tags["secretKey"] == "***REDACTED***"

    async def test_selective_property_storage_vm(self, engine, mock_resource_graph_row):
        """Should extract VM-specific selected properties."""
        with patch.object(engine, "_execute_graph_query", return_value=[mock_resource_graph_row]):
            docs = await engine.full_resource_discovery(MOCK_SUB_ID)

        props = docs[0]["selected_properties"]
        assert props["vm_size"] == "Standard_D2s_v3"
        assert props["os_type"] == "Linux"
        assert props["provisioning_state"] == "Succeeded"

    async def test_selective_property_storage_app_service(self, engine, mock_app_service_row):
        """Should extract App Service-specific selected properties."""
        with patch.object(engine, "_execute_graph_query", return_value=[mock_app_service_row]):
            docs = await engine.full_resource_discovery(MOCK_SUB_ID)

        props = docs[0]["selected_properties"]
        assert props["state"] == "Running"
        assert props["default_host_name"] == "app-test.azurewebsites.net"
        assert props["https_only"] is True

    async def test_resource_type_filter(self, engine, mock_resource_graph_row):
        """Should pass resource type filter into KQL query."""
        with patch.object(engine, "_execute_graph_query", return_value=[]) as mock_exec:
            await engine.full_resource_discovery(
                MOCK_SUB_ID,
                resource_types=["Microsoft.Compute/virtualMachines"],
            )

        query = mock_exec.call_args[0][0]
        assert "type in~" in query
        assert "microsoft.compute/virtualmachines" in query.lower()

    async def test_error_handling_reraises(self, engine):
        """Should log and re-raise errors from Resource Graph."""
        with patch.object(engine, "_execute_graph_query", side_effect=RuntimeError("API error")):
            with pytest.raises(RuntimeError, match="API error"):
                await engine.full_resource_discovery(MOCK_SUB_ID)


# ---------------------------------------------------------------------------
# incremental_discovery
# ---------------------------------------------------------------------------

class TestIncrementalDiscovery:
    """Tests for incremental_discovery()."""

    async def test_detects_created_resources(self, engine, mock_resource_graph_row):
        """Resources not in cached set should be classified as created."""
        id_row = {"id": mock_resource_graph_row["id"]}

        with patch.object(engine, "_execute_graph_query") as mock_exec:
            # First call returns changed resources, second returns current IDs
            mock_exec.side_effect = [[mock_resource_graph_row], [id_row]]

            result = await engine.incremental_discovery(
                MOCK_SUB_ID,
                last_scan_time="2026-01-01T00:00:00Z",
                cached_resource_ids=set(),
            )

        assert len(result["created"]) == 1
        assert len(result["modified"]) == 0
        assert len(result["deleted"]) == 0
        assert result["created"][0]["change_type"] == "created"

    async def test_detects_modified_resources(self, engine, mock_resource_graph_row):
        """Resources already in cached set should be classified as modified."""
        rid = mock_resource_graph_row["id"]
        id_row = {"id": rid}

        with patch.object(engine, "_execute_graph_query") as mock_exec:
            mock_exec.side_effect = [[mock_resource_graph_row], [id_row]]

            result = await engine.incremental_discovery(
                MOCK_SUB_ID,
                last_scan_time="2026-01-01T00:00:00Z",
                cached_resource_ids={rid},
            )

        assert len(result["created"]) == 0
        assert len(result["modified"]) == 1
        assert len(result["deleted"]) == 0
        assert result["modified"][0]["change_type"] == "modified"

    async def test_detects_deleted_resources(self, engine):
        """Resources in cached set but not in current IDs should be classified as deleted."""
        deleted_id = "/subscriptions/sub/resourceGroups/rg/providers/M/type/gone"

        with patch.object(engine, "_execute_graph_query") as mock_exec:
            # No changed resources, no current IDs
            mock_exec.side_effect = [[], []]

            result = await engine.incremental_discovery(
                MOCK_SUB_ID,
                last_scan_time="2026-01-01T00:00:00Z",
                cached_resource_ids={deleted_id},
            )

        assert len(result["deleted"]) == 1
        assert result["deleted"][0]["resource_id"] == deleted_id
        assert result["deleted"][0]["change_type"] == "deleted"

    async def test_no_cached_ids_skips_deletion_detection(self, engine):
        """When no cached IDs are provided, should not report deletions."""
        with patch.object(engine, "_execute_graph_query") as mock_exec:
            mock_exec.side_effect = [[], []]

            result = await engine.incremental_discovery(
                MOCK_SUB_ID,
                last_scan_time="2026-01-01T00:00:00Z",
                cached_resource_ids=None,
            )

        assert result["deleted"] == []


# ---------------------------------------------------------------------------
# extract_relationships
# ---------------------------------------------------------------------------

class TestExtractRelationships:
    """Tests for extract_relationships()."""

    async def test_vm_typed_relationship_extraction(self, engine):
        """Should use typed KQL for VMs to extract NIC references."""
        vm_resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-test",
            "resource_type": "microsoft.compute/virtualmachines",
            "subscription_id": MOCK_SUB_ID,
        }
        nic_id = f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Network/networkInterfaces/nic-test"

        with patch.object(engine, "_execute_graph_query", return_value=[{"rel_id": nic_id}]):
            rels = await engine.extract_relationships(vm_resource, depth=1)

        assert len(rels) == 1
        assert rels[0]["source"] == vm_resource["resource_id"]
        assert rels[0]["target"] == nic_id
        assert rels[0]["relationship_type"] == "depends_on"
        assert rels[0]["depth"] == 1

    async def test_depth_capped_at_two(self, engine):
        """Depth should never exceed 2 even if higher is requested."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-test",
            "resource_type": "microsoft.compute/virtualmachines",
            "subscription_id": MOCK_SUB_ID,
        }

        with patch.object(engine, "_execute_graph_query", return_value=[]):
            rels = await engine.extract_relationships(resource, depth=10)

        # Should not error – depth is capped internally
        assert rels == []

    async def test_generic_fallback_for_unknown_types(self, engine):
        """Unknown resource types should use generic 'contains' fallback."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.CustomRP/resources/custom-1",
            "resource_type": "microsoft.customrp/resources",
            "subscription_id": MOCK_SUB_ID,
        }
        related_id = f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Network/virtualNetworks/vnet-1"

        with patch.object(engine, "_execute_graph_query", return_value=[{"id": related_id, "type": "Microsoft.Network/virtualNetworks"}]):
            rels = await engine.extract_relationships(resource, depth=1)

        assert len(rels) == 1
        assert rels[0]["target"] == related_id

    async def test_no_duplicate_visits(self, engine):
        """Should not revisit already-visited resource IDs."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-test",
            "resource_type": "microsoft.compute/virtualmachines",
            "subscription_id": MOCK_SUB_ID,
        }
        nic_id = f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Network/networkInterfaces/nic-test"

        call_count = 0

        async def mock_query(query, subs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"rel_id": nic_id}]
            # NIC's second-level lookup returns the original VM (should be skipped)
            return [{"rel_id": resource["resource_id"].lower()}]

        with patch.object(engine, "_execute_graph_query", side_effect=mock_query):
            rels = await engine.extract_relationships(resource, depth=2)

        # Only the NIC relationship should appear, not the circular reference
        assert len(rels) == 1

    async def test_missing_resource_id_returns_empty(self, engine):
        """Should return empty list when resource has no ID."""
        resource = {"resource_type": "some/type", "subscription_id": MOCK_SUB_ID}
        rels = await engine.extract_relationships(resource, depth=1)
        assert rels == []

    async def test_query_failure_handled_gracefully(self, engine):
        """Should handle query failures without raising."""
        resource = {
            "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/T/t/r",
            "resource_type": "t/t",
            "subscription_id": MOCK_SUB_ID,
        }

        with patch.object(engine, "_execute_graph_query", side_effect=Exception("graph error")):
            rels = await engine.extract_relationships(resource, depth=1)

        assert rels == []


# ---------------------------------------------------------------------------
# enrich_properties
# ---------------------------------------------------------------------------

class TestEnrichProperties:
    """Tests for enrich_properties()."""

    async def test_vm_enrichment(self, engine):
        """Should enrich VM with power state from instance view."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-test",
            "resource_type": "microsoft.compute/virtualmachines",
        }

        mock_status = MagicMock()
        mock_status.code = "PowerState/running"
        mock_status.display_status = "VM running"

        mock_iv = MagicMock()
        mock_iv.statuses = [mock_status]
        mock_iv.vm_agent = MagicMock()
        mock_iv.vm_agent.vm_agent_version = "2.7.41491.1"
        mock_iv.os_name = "Ubuntu"
        mock_iv.os_version = "22.04"

        with patch("utils.resource_discovery_engine.ComputeManagementClient") as MockCompute:
            mock_client = MockCompute.return_value
            mock_client.virtual_machines.instance_view.return_value = mock_iv

            result = await engine.enrich_properties(resource)

        enriched = result["enriched_properties"]
        assert enriched["power_state"] == "VM running"
        assert enriched["vm_agent_status"] == "2.7.41491.1"
        assert "enriched_at" in enriched

    async def test_app_service_enrichment(self, engine):
        """Should enrich App Service with state and host name."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Web/sites/app-test",
            "resource_type": "microsoft.web/sites",
        }

        mock_site = MagicMock()
        mock_site.state = "Running"
        mock_site.availability_state = "Normal"
        mock_site.default_host_name = "app-test.azurewebsites.net"
        mock_site.https_only = True
        mock_site.site_config = MagicMock()
        mock_site.site_config.linux_fx_version = "PYTHON|3.11"

        with patch("utils.resource_discovery_engine.WebSiteManagementClient") as MockWeb:
            mock_client = MockWeb.return_value
            mock_client.web_apps.get.return_value = mock_site

            result = await engine.enrich_properties(resource)

        enriched = result["enriched_properties"]
        assert enriched["state"] == "Running"
        assert enriched["default_host_name"] == "app-test.azurewebsites.net"
        assert enriched["https_only"] is True
        assert enriched["runtime_stack"] == "PYTHON|3.11"

    async def test_unsupported_type_returns_message(self, engine):
        """Should return 'not implemented' for unsupported resource types."""
        resource = {
            "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/kv-1",
            "resource_type": "microsoft.keyvault/vaults",
        }

        result = await engine.enrich_properties(resource)

        enriched = result["enriched_properties"]
        assert enriched["supported"] is False
        assert "not yet implemented" in enriched["message"]

    async def test_enrichment_error_handled_gracefully(self, engine):
        """Should capture enrichment errors without raising."""
        resource = {
            "resource_id": f"/subscriptions/{MOCK_SUB_ID}/resourceGroups/{MOCK_RG}/providers/Microsoft.Compute/virtualMachines/vm-fail",
            "resource_type": "microsoft.compute/virtualmachines",
        }

        with patch("utils.resource_discovery_engine.ComputeManagementClient") as MockCompute:
            MockCompute.return_value.virtual_machines.instance_view.side_effect = Exception("API timeout")

            result = await engine.enrich_properties(resource)

        enriched = result["enriched_properties"]
        assert "error" in enriched
        assert "API timeout" in enriched["error"]


# ---------------------------------------------------------------------------
# Tag security filtering (unit-level)
# ---------------------------------------------------------------------------

class TestTagSanitization:
    """Tests for _sanitize_tags helper."""

    def test_redacts_password_keys(self):
        from utils.resource_discovery_engine import _sanitize_tags

        tags = {"dbPassword": "s3cret", "environment": "prod"}
        result = _sanitize_tags(tags)
        assert result["dbPassword"] == "***REDACTED***"
        assert result["environment"] == "prod"

    def test_redacts_multiple_sensitive_keywords(self):
        from utils.resource_discovery_engine import _sanitize_tags

        tags = {
            "api-token": "abc",
            "accessKey": "def",
            "myCredential": "ghi",
            "secretValue": "jkl",
            "normal-tag": "safe",
        }
        result = _sanitize_tags(tags)
        for key in ["api-token", "accessKey", "myCredential", "secretValue"]:
            assert result[key] == "***REDACTED***"
        assert result["normal-tag"] == "safe"

    def test_empty_tags_returns_empty_dict(self):
        from utils.resource_discovery_engine import _sanitize_tags

        assert _sanitize_tags(None) == {}
        assert _sanitize_tags({}) == {}


# ---------------------------------------------------------------------------
# _execute_graph_query (pagination)
# ---------------------------------------------------------------------------

class TestGraphQueryPagination:
    """Tests for paginated Resource Graph query execution."""

    async def test_single_page(self, engine):
        """Should return all rows from a single-page response."""
        mock_response = MagicMock()
        mock_response.data = [{"id": "r1"}, {"id": "r2"}]
        mock_response.skip_token = None

        with patch("utils.resource_discovery_engine.ResourceGraphClient") as MockRGC:
            engine._graph_client = MockRGC.return_value
            engine._graph_client.resources.return_value = mock_response

            rows = await engine._execute_graph_query("Resources", [MOCK_SUB_ID])

        assert len(rows) == 2

    async def test_multi_page(self, engine):
        """Should follow skip_token to fetch all pages."""
        page1 = MagicMock()
        page1.data = [{"id": "r1"}]
        page1.skip_token = "token-page2"

        page2 = MagicMock()
        page2.data = [{"id": "r2"}]
        page2.skip_token = None

        with patch("utils.resource_discovery_engine.ResourceGraphClient") as MockRGC:
            engine._graph_client = MockRGC.return_value
            engine._graph_client.resources.side_effect = [page1, page2]

            rows = await engine._execute_graph_query("Resources", [MOCK_SUB_ID])

        assert len(rows) == 2
        assert rows[0]["id"] == "r1"
        assert rows[1]["id"] == "r2"


# ---------------------------------------------------------------------------
# Credential initialisation
# ---------------------------------------------------------------------------

class TestCredentialInit:
    """Tests for credential initialisation logic."""

    def test_service_principal_when_configured(self):
        """Should use ClientSecretCredential when env vars are set."""
        from utils.resource_discovery_engine import ResourceDiscoveryEngine

        env = {
            "USE_SERVICE_PRINCIPAL": "true",
            "AZURE_SP_CLIENT_ID": "client-id",
            "AZURE_SP_CLIENT_SECRET": "client-secret",
            "AZURE_TENANT_ID": MOCK_TENANT_ID,
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("utils.resource_discovery_engine.ClientSecretCredential") as MockCSC:
                eng = ResourceDiscoveryEngine()
                cred = eng._get_credential()

        MockCSC.assert_called_once_with(
            tenant_id=MOCK_TENANT_ID,
            client_id="client-id",
            client_secret="client-secret",
        )

    def test_default_credential_fallback(self):
        """Should use DefaultAzureCredential when SP env vars are absent."""
        from utils.resource_discovery_engine import ResourceDiscoveryEngine

        env = {"USE_SERVICE_PRINCIPAL": "false"}
        with patch.dict("os.environ", env, clear=False):
            with patch("utils.resource_discovery_engine.DefaultAzureCredential") as MockDAC:
                eng = ResourceDiscoveryEngine()
                cred = eng._get_credential()

        MockDAC.assert_called_once()

    def test_injected_credential_used_directly(self):
        """Should use injected credential without creating a new one."""
        from utils.resource_discovery_engine import ResourceDiscoveryEngine

        fake_cred = MagicMock()
        eng = ResourceDiscoveryEngine(credential=fake_cred)
        assert eng._get_credential() is fake_cred
