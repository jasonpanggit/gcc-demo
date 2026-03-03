"""Tests for MCPToolRegistry."""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from utils.tool_registry import (
    MCPToolRegistry,
    ToolEntry,
    ServerEntry,
    get_tool_registry,
)


class MockMCPClient:
    """Mock MCP client for testing."""

    def __init__(self, tools, label="mock"):
        self._tools = tools
        self._label = label

    def get_available_tools(self):
        """Return mock tool definitions."""
        return self._tools

    async def call_tool(self, name, args):
        """Simulate tool invocation."""
        await asyncio.sleep(0.01)  # Simulate network latency
        return {
            "success": True,
            "result": f"Called {name} with {args}",
            "tool_name": name,
            "mock_client": self._label,
        }


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    # Clear singleton
    MCPToolRegistry._instance = None
    reg = MCPToolRegistry()
    yield reg
    # Cleanup
    reg.clear()


@pytest.fixture
def mock_sre_client():
    """Create mock SRE MCP client."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_resource_health",
                "description": "Check health status of Azure resources",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_id": {"type": "string"}
                    },
                    "required": ["resource_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_incidents",
                "description": "List active incidents",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]
    return MockMCPClient(tools, label="sre")


@pytest.fixture
def mock_network_client():
    """Create mock Network MCP client."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "audit_nsg_rules",
                "description": "Audit NSG security rules",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nsg_id": {"type": "string"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_routing",
                "description": "Check routing configuration",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]
    return MockMCPClient(tools, label="network")


class TestToolEntry:
    """Tests for ToolEntry dataclass."""

    def test_tool_entry_creation(self):
        """Test creating a ToolEntry."""
        entry = ToolEntry(
            name="test_tool",
            original_name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
            source_label="sre",
            domain="sre",
            priority=1
        )

        assert entry.name == "test_tool"
        assert entry.source_label == "sre"
        assert entry.domain == "sre"
        assert entry.priority == 1

    def test_tool_entry_to_openai_format(self):
        """Test converting ToolEntry to OpenAI format."""
        entry = ToolEntry(
            name="test_tool",
            original_name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
            source_label="sre",
            domain="sre",
            priority=1
        )

        openai_format = entry.to_openai_format()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "test_tool"
        assert openai_format["function"]["description"] == "A test tool"
        assert openai_format["metadata"]["source"] == "sre"
        assert openai_format["metadata"]["domain"] == "sre"


class TestServerEntry:
    """Tests for ServerEntry dataclass."""

    def test_server_entry_creation(self):
        """Test creating a ServerEntry."""
        client = MockMCPClient([], label="test")
        entry = ServerEntry(
            label="test",
            client=client,
            domain="test_domain",
            priority=1
        )

        assert entry.label == "test"
        assert entry.domain == "test_domain"
        assert entry.priority == 1
        assert entry.enabled is True
        assert entry.tool_count == 0


class TestMCPToolRegistry:
    """Tests for MCPToolRegistry class."""

    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        reg1 = MCPToolRegistry()
        reg2 = MCPToolRegistry()

        assert reg1 is reg2

    def test_get_tool_registry(self):
        """Test get_tool_registry() function."""
        reg1 = get_tool_registry()
        reg2 = get_tool_registry()

        assert reg1 is reg2
        assert isinstance(reg1, MCPToolRegistry)

    @pytest.mark.asyncio
    async def test_register_server(self, registry, mock_sre_client):
        """Test registering an MCP server."""
        server = await registry.register_server(
            label="sre",
            client=mock_sre_client,
            domain="sre",
            priority=1,
            auto_discover=False
        )

        assert server.label == "sre"
        assert server.domain == "sre"
        assert server.priority == 1
        assert server.enabled is True

        # Verify server is in registry
        stats = registry.get_stats()
        assert stats["total_servers"] == 1

    @pytest.mark.asyncio
    async def test_register_duplicate_server(self, registry, mock_sre_client):
        """Test that registering duplicate server raises error."""
        await registry.register_server("sre", mock_sre_client)

        with pytest.raises(ValueError, match="already registered"):
            await registry.register_server("sre", mock_sre_client)

    @pytest.mark.asyncio
    async def test_register_invalid_client(self, registry):
        """Test that registering invalid client raises error."""
        invalid_client = object()  # No get_available_tools() method

        with pytest.raises(ValueError, match="must implement get_available_tools"):
            await registry.register_server("test", invalid_client)

    @pytest.mark.asyncio
    async def test_discover_tools(self, registry, mock_sre_client):
        """Test discovering tools from a server."""
        await registry.register_server(
            "sre",
            mock_sre_client,
            domain="sre",
            auto_discover=False
        )

        tools = await registry.discover_tools("sre")

        assert len(tools) == 2
        assert tools[0].source_label == "sre"
        assert tools[0].domain == "sre"
        assert tools[0].name in ["check_resource_health", "list_incidents"]

    @pytest.mark.asyncio
    async def test_auto_discover_on_registration(self, registry, mock_sre_client):
        """Test that auto_discover works during registration."""
        await registry.register_server(
            "sre",
            mock_sre_client,
            domain="sre",
            auto_discover=True  # Default
        )

        stats = registry.get_stats()
        assert stats["total_tools"] == 2
        assert stats["tools_by_source"]["sre"] == 2

    @pytest.mark.asyncio
    async def test_tool_name_collision_resolution(self, registry):
        """Test that tool name collisions are resolved."""
        # Create two clients with same tool name
        client1_tools = [{
            "type": "function",
            "function": {
                "name": "read_resource",
                "description": "Read resource from SRE",
                "parameters": {"type": "object"}
            }
        }]
        client1 = MockMCPClient(client1_tools, "sre")

        client2_tools = [{
            "type": "function",
            "function": {
                "name": "read_resource",
                "description": "Read resource from Azure",
                "parameters": {"type": "object"}
            }
        }]
        client2 = MockMCPClient(client2_tools, "azure")

        # Register both (second should get suffix)
        await registry.register_server("sre", client1, priority=1)
        await registry.register_server("azure", client2, priority=5)

        # Check collision was resolved
        tool1 = registry.get_tool_by_name("read_resource")
        tool2 = registry.get_tool_by_name("read_resource_azure")

        assert tool1 is not None
        assert tool1.source_label == "sre"  # Higher priority keeps clean name

        assert tool2 is not None
        assert tool2.source_label == "azure"
        assert tool2.original_name == "read_resource"

    @pytest.mark.asyncio
    async def test_priority_based_collision_resolution(self, registry):
        """Test that priority determines collision resolution."""
        # Lower priority number = higher priority

        client_low_priority_tools = [{
            "type": "function",
            "function": {
                "name": "shared_tool",
                "description": "Low priority version",
                "parameters": {"type": "object"}
            }
        }]
        client_low = MockMCPClient(client_low_priority_tools, "low")

        client_high_priority_tools = [{
            "type": "function",
            "function": {
                "name": "shared_tool",
                "description": "High priority version",
                "parameters": {"type": "object"}
            }
        }]
        client_high = MockMCPClient(client_high_priority_tools, "high")

        # Register low priority first
        await registry.register_server("low", client_low, priority=10)

        # Then register high priority
        await registry.register_server("high", client_high, priority=1)

        # High priority should get clean name
        tool_clean = registry.get_tool_by_name("shared_tool")
        assert tool_clean.source_label == "high"
        assert tool_clean.description == "High priority version"

        # Low priority should get suffix
        tool_suffixed = registry.get_tool_by_name("shared_tool_low")
        assert tool_suffixed.source_label == "low"

    @pytest.mark.asyncio
    async def test_get_tools_by_domain(self, registry, mock_sre_client, mock_network_client):
        """Test getting tools by domain."""
        await registry.register_server("sre", mock_sre_client, domain="sre")
        await registry.register_server("network", mock_network_client, domain="network")

        sre_tools = registry.get_tools_by_domain("sre")
        network_tools = registry.get_tools_by_domain("network")

        assert len(sre_tools) == 2
        assert all(tool.domain == "sre" for tool in sre_tools)

        assert len(network_tools) == 2
        assert all(tool.domain == "network" for tool in network_tools)

    @pytest.mark.asyncio
    async def test_get_tools_by_source(self, registry, mock_sre_client, mock_network_client):
        """Test getting tools by source."""
        await registry.register_server("sre", mock_sre_client, domain="sre")
        await registry.register_server("network", mock_network_client, domain="network")

        sre_tools = registry.get_tools_by_source("sre")
        network_tools = registry.get_tools_by_source("network")

        assert len(sre_tools) == 2
        assert all(tool.source_label == "sre" for tool in sre_tools)

        assert len(network_tools) == 2
        assert all(tool.source_label == "network" for tool in network_tools)

    @pytest.mark.asyncio
    async def test_get_tools_by_sources(self, registry, mock_sre_client, mock_network_client):
        """Test getting tools from multiple sources."""
        await registry.register_server("sre", mock_sre_client, domain="sre")
        await registry.register_server("network", mock_network_client, domain="network")

        tools = registry.get_tools_by_sources(["sre", "network"])

        assert len(tools) == 4  # 2 from each source

    @pytest.mark.asyncio
    async def test_get_all_tools(self, registry, mock_sre_client, mock_network_client):
        """Test getting all tools."""
        await registry.register_server("sre", mock_sre_client)
        await registry.register_server("network", mock_network_client)

        all_tools = registry.get_all_tools()

        assert len(all_tools) == 4

    @pytest.mark.asyncio
    async def test_get_all_tools_openai_format(self, registry, mock_sre_client):
        """Test getting all tools in OpenAI format."""
        await registry.register_server("sre", mock_sre_client)

        tools = registry.get_all_tools_openai_format()

        assert len(tools) == 2
        assert all(tool["type"] == "function" for tool in tools)
        assert all("function" in tool for tool in tools)
        assert all("metadata" in tool for tool in tools)

    @pytest.mark.asyncio
    async def test_invoke_tool(self, registry, mock_sre_client):
        """Test invoking a tool."""
        await registry.register_server("sre", mock_sre_client)

        result = await registry.invoke_tool(
            "check_resource_health",
            {"resource_id": "vm-123"}
        )

        assert result["success"] is True
        assert "Called check_resource_health" in result["result"]

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_tool(self, registry):
        """Test that invoking nonexistent tool raises error."""
        with pytest.raises(ValueError, match="not found in registry"):
            await registry.invoke_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_refresh_tool_catalog(self, registry, mock_sre_client):
        """Test refreshing tool catalog."""
        await registry.register_server("sre", mock_sre_client, auto_discover=False)

        # Initially no tools
        assert len(registry.get_all_tools()) == 0

        # Refresh catalog
        count = await registry.refresh_tool_catalog("sre")

        assert count == 2
        assert len(registry.get_all_tools()) == 2

    @pytest.mark.asyncio
    async def test_refresh_all_servers(self, registry, mock_sre_client, mock_network_client):
        """Test refreshing all servers."""
        await registry.register_server("sre", mock_sre_client, auto_discover=False)
        await registry.register_server("network", mock_network_client, auto_discover=False)

        # Refresh all
        total = await registry.refresh_tool_catalog()

        assert total == 4
        assert len(registry.get_all_tools()) == 4

    def test_subscribe_notification(self, registry):
        """Test subscribing to notifications."""
        events = []

        def handler(server_label, tool_count):
            events.append((server_label, tool_count))

        registry.subscribe_notification("tools_changed", handler)

        # Trigger notification
        registry._notify("tools_changed", "sre", 5)

        assert len(events) == 1
        assert events[0] == ("sre", 5)

    def test_get_stats(self, registry, mock_sre_client):
        """Test getting registry statistics."""
        asyncio.run(registry.register_server("sre", mock_sre_client, domain="sre"))

        stats = registry.get_stats()

        assert stats["total_servers"] == 1
        assert stats["total_tools"] == 2
        assert stats["tools_by_source"]["sre"] == 2
        assert stats["tools_by_domain"]["sre"] == 2
        assert "sre" in stats["servers"]

    def test_clear_registry(self, registry, mock_sre_client):
        """Test clearing the registry."""
        asyncio.run(registry.register_server("sre", mock_sre_client))

        assert len(registry.get_all_tools()) > 0

        registry.clear()

        assert len(registry.get_all_tools()) == 0
        assert registry.get_stats()["total_servers"] == 0


class TestRegistryErrorHandling:
    """Tests for error handling in registry."""

    @pytest.mark.asyncio
    async def test_discover_tools_from_unregistered_server(self, registry):
        """Test discovering tools from unregistered server raises error."""
        with pytest.raises(ValueError, match="not registered"):
            await registry.discover_tools("nonexistent")

    @pytest.mark.asyncio
    async def test_discover_tools_handles_client_errors(self, registry):
        """Test that tool discovery handles client errors gracefully."""
        # Create client that raises error
        bad_client = MagicMock()
        bad_client.get_available_tools.side_effect = Exception("Client error")

        await registry.register_server("bad", bad_client, auto_discover=False)

        # Should not raise, just return empty list
        tools = await registry.discover_tools("bad")

        assert tools == []

    @pytest.mark.asyncio
    async def test_invoke_tool_handles_connection_error(self, registry):
        """Test that tool invocation handles connection errors."""
        # Create client that raises ConnectionError
        client = MagicMock()
        client.get_available_tools.return_value = [{
            "type": "function",
            "function": {
                "name": "failing_tool",
                "description": "A tool that fails",
                "parameters": {"type": "object"}
            }
        }]
        client.call_tool.side_effect = ConnectionError("Network error")

        await registry.register_server("failing", client)

        result = await registry.invoke_tool("failing_tool", {})

        assert result["success"] is False
        assert result["is_error"] is True
        assert "Connection error" in result["error"]
        assert result["retry_suggested"] is True
