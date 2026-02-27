"""
Shared test fixtures for GCC Demo Platform tests.

This module provides reusable pytest fixtures for:
- Azure SDK mocks (Cosmos, OpenAI, Compute, Network, Storage)
- MCP client mocks (Patch, Network, SRE)
- Orchestrator factories (EOL, SRE, Inventory)

Created: 2026-02-27 (Phase 1, Task 1.2)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List


# =============================================================================
# Azure SDK Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_cosmos_client():
    """Mock Cosmos DB client with common operations.

    Provides mocked methods:
    - read_item: Returns test document
    - upsert_item: Returns success status
    - query_items: Returns iterable of test documents

    Usage:
        def test_cosmos_read(mock_cosmos_client):
            result = await mock_cosmos_client.read_item(item="123", partition_key="test")
            assert result["id"] == "123"
    """
    from azure.cosmos.aio import CosmosClient

    client = AsyncMock(spec=CosmosClient)

    # Mock database and container
    database = AsyncMock()
    container = AsyncMock()

    # Mock read_item
    container.read_item = AsyncMock(return_value={
        "id": "test-id-123",
        "data": {"key": "value"},
        "cached": True,
        "timestamp": "2026-02-27T00:00:00Z"
    })

    # Mock upsert_item
    container.upsert_item = AsyncMock(return_value={
        "id": "test-id-123",
        "status": "ok"
    })

    # Mock query_items (returns async iterable)
    async def mock_query():
        yield {"id": "1", "data": "test1"}
        yield {"id": "2", "data": "test2"}

    container.query_items = MagicMock(return_value=mock_query())

    # Wire up the hierarchy
    database.get_container_client = MagicMock(return_value=container)
    client.get_database_client = MagicMock(return_value=database)

    return client


@pytest.fixture
def mock_openai_client():
    """Mock Azure OpenAI client for LLM calls.

    Provides mocked methods:
    - chat.completions.create: Returns test completion

    Usage:
        async def test_llm_call(mock_openai_client):
            response = await mock_openai_client.chat.completions.create(...)
            assert response.choices[0].message.content
    """
    from openai import AsyncAzureOpenAI

    client = AsyncMock(spec=AsyncAzureOpenAI)

    # Mock completion response
    mock_choice = MagicMock()
    mock_choice.message.content = "Test response from LLM"
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.total_tokens = 100

    client.chat.completions.create = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture
def mock_compute_client():
    """Mock Azure Compute Management client.

    Provides mocked methods:
    - virtual_machines.list: Returns list of VMs
    - virtual_machines.get: Returns specific VM
    - virtual_machines.begin_restart: Returns async operation

    Usage:
        async def test_vm_list(mock_compute_client):
            vms = mock_compute_client.virtual_machines.list(resource_group="test-rg")
            vm_list = [vm async for vm in vms]
            assert len(vm_list) > 0
    """
    from azure.mgmt.compute.aio import ComputeManagementClient

    client = AsyncMock(spec=ComputeManagementClient)

    # Mock VM object
    mock_vm = MagicMock()
    mock_vm.name = "test-vm-01"
    mock_vm.id = "/subscriptions/.../test-vm-01"
    mock_vm.location = "eastus"
    mock_vm.provisioning_state = "Succeeded"

    # Mock list operation (async iterable)
    async def mock_vm_list(*args, **kwargs):
        yield mock_vm

    client.virtual_machines.list = MagicMock(return_value=mock_vm_list())
    client.virtual_machines.list_all = MagicMock(return_value=mock_vm_list())
    client.virtual_machines.get = AsyncMock(return_value=mock_vm)

    # Mock long-running operation
    mock_operation = AsyncMock()
    mock_operation.result = AsyncMock(return_value=mock_vm)
    client.virtual_machines.begin_restart = AsyncMock(return_value=mock_operation)

    return client


@pytest.fixture
def mock_network_client():
    """Mock Azure Network Management client.

    Provides mocked methods:
    - network_security_groups.list: Returns NSGs
    - virtual_networks.list: Returns VNets
    - network_watchers.get_flow_log_status: Returns flow log status

    Usage:
        async def test_nsg_list(mock_network_client):
            nsgs = mock_network_client.network_security_groups.list(resource_group="test")
            nsg_list = [nsg async for nsg in nsgs]
            assert len(nsg_list) > 0
    """
    from azure.mgmt.network.aio import NetworkManagementClient

    client = AsyncMock(spec=NetworkManagementClient)

    # Mock NSG
    mock_nsg = MagicMock()
    mock_nsg.name = "test-nsg-01"
    mock_nsg.id = "/subscriptions/.../test-nsg-01"
    mock_nsg.location = "eastus"

    # Mock VNet
    mock_vnet = MagicMock()
    mock_vnet.name = "test-vnet-01"
    mock_vnet.address_space.address_prefixes = ["10.0.0.0/16"]

    # Mock async iterables
    async def mock_nsg_list(*args, **kwargs):
        yield mock_nsg

    async def mock_vnet_list(*args, **kwargs):
        yield mock_vnet

    client.network_security_groups.list = MagicMock(return_value=mock_nsg_list())
    client.virtual_networks.list = MagicMock(return_value=mock_vnet_list())

    # Mock flow log status
    mock_flow_log = MagicMock()
    mock_flow_log.enabled = True
    client.network_watchers.begin_get_flow_log_status = AsyncMock(return_value=AsyncMock(
        result=AsyncMock(return_value=mock_flow_log)
    ))

    return client


@pytest.fixture
def mock_storage_client():
    """Mock Azure Storage Management client.

    Provides mocked methods:
    - storage_accounts.list: Returns storage accounts
    - storage_accounts.get_properties: Returns account properties

    Usage:
        async def test_storage_list(mock_storage_client):
            accounts = mock_storage_client.storage_accounts.list()
            account_list = [acc async for acc in accounts]
            assert len(account_list) > 0
    """
    from azure.mgmt.storage.aio import StorageManagementClient

    client = AsyncMock(spec=StorageManagementClient)

    # Mock storage account
    mock_account = MagicMock()
    mock_account.name = "teststorage01"
    mock_account.id = "/subscriptions/.../teststorage01"
    mock_account.location = "eastus"
    mock_account.sku.name = "Standard_LRS"
    mock_account.kind = "StorageV2"

    # Mock async iterable
    async def mock_storage_list(*args, **kwargs):
        yield mock_account

    client.storage_accounts.list = MagicMock(return_value=mock_storage_list())
    client.storage_accounts.get_properties = AsyncMock(return_value=mock_account)

    return client


# =============================================================================
# MCP Client Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_patch_mcp_client():
    """Mock Patch MCP client.

    Provides mocked methods:
    - call_tool: Returns patch operation results
    - list_tools: Returns available patch tools

    Usage:
        async def test_patch_assessment(mock_patch_mcp_client):
            result = await mock_patch_mcp_client.call_tool("assess_patches", {})
            assert result["success"] is True
    """
    client = AsyncMock()

    client.call_tool = AsyncMock(return_value={
        "success": True,
        "data": {
            "total_patches": 10,
            "critical": 2,
            "important": 5,
            "moderate": 3
        }
    })

    client.list_tools = AsyncMock(return_value=[
        {"name": "assess_patches", "description": "Assess available patches"},
        {"name": "install_patches", "description": "Install patches"},
        {"name": "get_patch_status", "description": "Get patch status"},
    ])

    return client


@pytest.fixture
def mock_network_mcp_client():
    """Mock Network MCP client.

    Provides mocked methods:
    - call_tool: Returns network diagnostic results
    - list_tools: Returns available network tools

    Usage:
        async def test_nsg_flow_logs(mock_network_mcp_client):
            result = await mock_network_mcp_client.call_tool("get_nsg_flow_logs", {})
            assert result["success"] is True
    """
    client = AsyncMock()

    client.call_tool = AsyncMock(return_value={
        "success": True,
        "data": {
            "flow_logs": [
                {"nsg": "test-nsg", "enabled": True, "retention_days": 7}
            ]
        }
    })

    client.list_tools = AsyncMock(return_value=[
        {"name": "get_nsg_flow_logs", "description": "Get NSG flow logs"},
        {"name": "test_connectivity", "description": "Test network connectivity"},
        {"name": "get_effective_routes", "description": "Get effective routes"},
    ])

    return client


@pytest.fixture
def mock_sre_mcp_client():
    """Mock SRE MCP client.

    Provides mocked methods:
    - call_tool: Returns SRE operation results
    - list_tools: Returns available SRE tools

    Usage:
        async def test_incident_create(mock_sre_mcp_client):
            result = await mock_sre_mcp_client.call_tool("create_incident", {})
            assert result["success"] is True
    """
    client = AsyncMock()

    client.call_tool = AsyncMock(return_value={
        "success": True,
        "data": {
            "incident_id": "INC-001",
            "status": "created",
            "severity": "high"
        }
    })

    client.list_tools = AsyncMock(return_value=[
        {"name": "create_incident", "description": "Create incident"},
        {"name": "get_incident_status", "description": "Get incident status"},
        {"name": "resolve_incident", "description": "Resolve incident"},
    ])

    return client


# =============================================================================
# Orchestrator Factory Fixtures
# =============================================================================

@pytest.fixture
def factory_eol_orchestrator(mock_cosmos_client, mock_openai_client):
    """Factory fixture for creating EOL Orchestrator instances.

    Returns a factory function that creates orchestrator with mocked dependencies.

    Usage:
        def test_eol_orchestrator(factory_eol_orchestrator):
            orchestrator = factory_eol_orchestrator()
            result = await orchestrator.process_query("Windows Server 2025")
            assert result["success"] is True
    """
    def _create_orchestrator(**kwargs):
        """Create EOL Orchestrator with optional overrides."""
        from agents.eol_orchestrator import EOLOrchestratorAgent

        # Create orchestrator (may need DI changes in Phase 2 if constructor doesn't support mocks)
        with patch('utils.cosmos_cache.base_cosmos', mock_cosmos_client):
            with patch('openai.AsyncAzureOpenAI', return_value=mock_openai_client):
                orchestrator = EOLOrchestratorAgent(**kwargs)
                return orchestrator

    return _create_orchestrator


@pytest.fixture
def factory_sre_orchestrator(mock_cosmos_client, mock_openai_client, mock_sre_mcp_client):
    """Factory fixture for creating SRE Orchestrator instances.

    Returns a factory function that creates orchestrator with mocked dependencies.

    Usage:
        def test_sre_orchestrator(factory_sre_orchestrator):
            orchestrator = factory_sre_orchestrator()
            result = await orchestrator.handle_request("Check VM health")
            assert result["success"] is True
    """
    def _create_orchestrator(**kwargs):
        """Create SRE Orchestrator with optional overrides."""
        from agents.sre_orchestrator import SREOrchestrator

        with patch('utils.cosmos_cache.base_cosmos', mock_cosmos_client):
            with patch('openai.AsyncAzureOpenAI', return_value=mock_openai_client):
                with patch('utils.sre_mcp_client.sre_mcp_client', mock_sre_mcp_client):
                    orchestrator = SREOrchestrator(**kwargs)
                    return orchestrator

    return _create_orchestrator


@pytest.fixture
def factory_inventory_orchestrator(mock_cosmos_client, mock_openai_client):
    """Factory fixture for creating Inventory Orchestrator instances.

    Returns a factory function that creates orchestrator with mocked dependencies.

    Usage:
        def test_inventory_orchestrator(factory_inventory_orchestrator):
            orchestrator = factory_inventory_orchestrator()
            result = await orchestrator.run_full_scan()
            assert result["success"] is True
    """
    def _create_orchestrator(**kwargs):
        """Create Inventory Orchestrator with optional overrides."""
        from agents.inventory_orchestrator import InventoryOrchestrator

        with patch('utils.cosmos_cache.base_cosmos', mock_cosmos_client):
            with patch('openai.AsyncAzureOpenAI', return_value=mock_openai_client):
                orchestrator = InventoryOrchestrator(**kwargs)
                return orchestrator

    return _create_orchestrator


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def sample_eol_response():
    """Sample EOL response for testing."""
    return {
        "success": True,
        "data": {
            "software": "Windows Server 2025",
            "version": "2025",
            "eol_date": "2034-10-10",
            "extended_support_date": "2036-10-10",
            "confidence": 0.95,
            "source": "microsoft"
        },
        "cached": False,
        "metadata": {
            "query_time_ms": 150,
            "agent": "microsoft"
        }
    }


@pytest.fixture
def sample_sre_response():
    """Sample SRE response for testing."""
    return {
        "success": True,
        "data": {
            "incident_id": "INC-001",
            "status": "resolved",
            "severity": "medium",
            "resolution": "VM restarted successfully"
        },
        "cached": False,
        "metadata": {
            "query_time_ms": 500,
            "tools_used": ["vm_restart", "health_check"]
        }
    }
