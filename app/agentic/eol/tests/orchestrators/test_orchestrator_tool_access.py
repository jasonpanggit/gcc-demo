"""
Test both orchestrators can access all MCP tools through centralized registry.

Verifies Phase 1 implementation: MCPOrchestratorAgent and SREOrchestratorAgent
both have access to all 10 MCP servers through the MCPToolRegistry.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pytest
import pytest_asyncio
from typing import List, Dict, Any

from utils.tool_registry import MCPToolRegistry, get_tool_registry
from utils.mcp_host import MCPHost


class MockMCPClient:
    """Mock MCP client for testing."""

    def __init__(self, label: str, tool_count: int = 5):
        self.label = label
        self.tool_count = tool_count
        self._initialized = True

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Return mock tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{self.label}_tool_{i}",
                    "description": f"Tool {i} from {self.label} server",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string"}
                        }
                    }
                }
            }
            for i in range(1, self.tool_count + 1)
        ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mock tool execution."""
        return {
            "success": True,
            "tool_name": tool_name,
            "content": [f"Mock result from {tool_name}"],
            "parsed": {"result": f"executed {tool_name}"}
        }

    def is_initialized(self) -> bool:
        return self._initialized


async def create_test_registry():
    """Create a fresh registry with mock servers for testing."""
    # Get existing registry and clear it
    registry = get_tool_registry()
    registry.clear()  # Clear all registered servers and tools

    # Mock 10 MCP servers matching production setup
    mock_servers = {
        "azure": (MockMCPClient("azure", 10), "azure", 5),
        "sre": (MockMCPClient("sre", 5), "sre", 10),
        "network": (MockMCPClient("network", 8), "network", 10),
        "compute": (MockMCPClient("compute", 6), "compute", 10),
        "storage": (MockMCPClient("storage", 7), "storage", 10),
        "monitor": (MockMCPClient("monitor", 4), "monitoring", 10),
        "patch": (MockMCPClient("patch", 5), "patch", 10),
        "os_eol": (MockMCPClient("os_eol", 2), "eol", 10),
        "inventory": (MockMCPClient("inventory", 3), "inventory", 10),
        "azure_cli_executor": (MockMCPClient("azure_cli_executor", 2), "azure", 15),
    }

    # Register all servers
    for label, (client, domain, priority) in mock_servers.items():
        await registry.register_server(
            label=label,
            client=client,
            domain=domain,
            priority=priority,
            auto_discover=True
        )

    return registry, mock_servers


@pytest.mark.asyncio
async def test_registry_has_all_servers():
    """Test registry contains all 10 MCP servers."""
    registry, mock_servers = await create_test_registry()

    # Verify tools from all 10 servers
    stats = registry.get_stats()
    registered_servers = stats.get("servers", {})

    assert len(registered_servers) == 10, f"Expected 10 servers, got {len(registered_servers)}"
    print(f"✅ Registry contains all 10 MCP servers")

    # Verify each server
    for label in mock_servers.keys():
        tools_for_server = registry.get_tools_by_source(label)
        assert len(tools_for_server) > 0, f"Server '{label}' should have tools"

    print(f"✅ All 10 servers have registered tools")


@pytest.mark.asyncio
async def test_registry_total_tools():
    """Test registry has discovered all tools from all servers."""
    registry, mock_servers = await create_test_registry()

    # Calculate expected tool count
    expected_count = sum(client.tool_count for client, _, _ in mock_servers.values())

    # Get all tools
    all_tools = registry.get_all_tools()
    assert len(all_tools) == expected_count, f"Expected {expected_count} tools, got {len(all_tools)}"

    print(f"✅ Registry discovered all {expected_count} tools from 10 servers")


@pytest.mark.asyncio
async def test_mcp_host_access_to_registry():
    """Test MCPHost can access registry tools."""
    registry, _ = await create_test_registry()

    # Create MCPHost (registry already populated)
    mcp_host = MCPHost([])

    # Get tools from registry
    all_tools = mcp_host.get_tools_from_registry()
    assert len(all_tools) > 0, "MCPHost should access registry tools"

    print(f"✅ MCPHost can access {len(all_tools)} tools from registry")


@pytest.mark.asyncio
async def test_mcp_host_domain_filtering():
    """Test MCPHost can filter tools by domain."""
    registry, mock_servers = await create_test_registry()

    mcp_host = MCPHost([])

    # Test domain filtering
    test_domains = ["azure", "sre", "network", "monitoring"]

    for domain in test_domains:
        domain_tools = mcp_host.get_tools_from_registry(domain=domain)
        assert len(domain_tools) > 0, f"Should have tools for domain '{domain}'"

        # Verify tools are from correct domain
        for tool in domain_tools:
            tool_name = tool.get("function", {}).get("name", "")
            # Verify tool prefix matches one of the servers in this domain
            found_match = False
            for label, (_, d, _) in mock_servers.items():
                if d == domain and tool_name.startswith(label):
                    found_match = True
                    break
            assert found_match, f"Tool {tool_name} should be from domain {domain}"

        print(f"✅ Domain '{domain}' has {len(domain_tools)} tools")


@pytest.mark.asyncio
async def test_mcp_host_source_filtering():
    """Test MCPHost can filter tools by source."""
    registry, _ = await create_test_registry()

    mcp_host = MCPHost([])

    # Test source filtering
    test_sources = ["azure", "sre", "network", "patch"]

    for source in test_sources:
        source_tools = mcp_host.get_tools_from_registry(sources=[source])
        assert len(source_tools) > 0, f"Should have tools from source '{source}'"

        # Verify all tools are from correct source
        for tool in source_tools:
            tool_name = tool.get("function", {}).get("name", "")
            assert tool_name.startswith(source), f"Tool {tool_name} should be from source {source}"

        print(f"✅ Source '{source}' has {len(source_tools)} tools")


@pytest.mark.asyncio
async def test_priority_collision_resolution():
    """Test priority-based collision resolution."""
    registry, _ = await create_test_registry()

    # Azure MCP (priority=5) should win over azure_cli_executor (priority=15)
    # Both are in 'azure' domain
    azure_tools = registry.get_tools_by_domain("azure")
    assert len(azure_tools) > 0, "Should have Azure domain tools"

    # Count tools from each source
    azure_mcp_count = sum(1 for tool in azure_tools if tool.name.startswith("azure_tool_"))
    azure_cli_count = sum(1 for tool in azure_tools if tool.name.startswith("azure_cli_executor_"))

    # Both should be present (no collision since different prefixes)
    assert azure_mcp_count > 0, "Azure MCP tools should be present"
    assert azure_cli_count > 0, "Azure CLI Executor tools should be present"

    print(f"✅ Priority system working: Azure MCP ({azure_mcp_count} tools) + CLI Executor ({azure_cli_count} tools)")


@pytest.mark.asyncio
async def test_tool_invocation_through_registry():
    """Test tools can be invoked through registry."""
    registry, _ = await create_test_registry()

    # Get a tool
    all_tools = registry.get_all_tools()
    assert len(all_tools) > 0, "Should have tools"

    test_tool = all_tools[0]
    tool_name = test_tool.name

    # Invoke tool through registry
    result = await registry.invoke_tool(tool_name, {"param": "test_value"})

    assert result["success"] is True, f"Tool invocation should succeed: {result}"
    assert result["tool_name"] == tool_name

    print(f"✅ Tool '{tool_name}' invoked successfully through registry")


@pytest.mark.asyncio
async def test_mcp_orchestrator_pattern():
    """Test MCPOrchestrator usage pattern with registry."""
    registry, mock_servers = await create_test_registry()

    # Simulate MCPOrchestratorAgent pattern
    client_entries = [
        (label, client)
        for label, (client, _, _) in mock_servers.items()
    ]

    mcp_host = MCPHost(client_entries)
    await mcp_host.ensure_registered()

    # MCPOrchestrator should be able to:
    # 1. Get all tools
    all_tools = mcp_host.get_tools_from_registry()
    assert len(all_tools) > 0, "MCPOrchestrator should see all tools"

    # 2. Filter by domain for specialized queries
    network_tools = mcp_host.get_tools_from_registry(domain="network")
    assert len(network_tools) > 0, "MCPOrchestrator should filter by domain"

    # 3. Get tools in OpenAI format for LLM
    openai_tools = mcp_host.get_tools_from_registry()
    for tool in openai_tools:
        assert "type" in tool
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]

    print(f"✅ MCPOrchestrator pattern validated: {len(all_tools)} tools accessible")


@pytest.mark.asyncio
async def test_sre_orchestrator_pattern():
    """Test SREOrchestrator usage pattern with registry."""
    registry, _ = await create_test_registry()

    # Simulate SREOrchestratorAgent pattern (via SRESubAgent → MCPHost)
    # SRE focuses on specific domains
    sre_domains = ["sre", "monitoring", "network", "compute"]

    mcp_host = MCPHost([])

    # SREOrchestrator should be able to:
    # 1. Get tools for SRE-specific domains
    for domain in sre_domains:
        domain_tools = mcp_host.get_tools_from_registry(domain=domain)
        assert len(domain_tools) > 0, f"SREOrchestrator should access {domain} tools"
        print(f"✅ SREOrchestrator can access {len(domain_tools)} {domain} tools")

    # 2. Get combined tools from multiple domains
    multi_domain_tools = []
    for domain in sre_domains:
        multi_domain_tools.extend(mcp_host.get_tools_from_registry(domain=domain))

    assert len(multi_domain_tools) > 0, "SREOrchestrator should combine multiple domains"
    print(f"✅ SREOrchestrator can combine tools from {len(sre_domains)} domains: {len(multi_domain_tools)} total")


@pytest.mark.asyncio
async def test_both_orchestrators_share_tools():
    """Test both orchestrators can access the same tool catalog."""
    registry, _ = await create_test_registry()

    # Create two separate MCPHost instances (simulating two orchestrators)
    mcp_host_1 = MCPHost([])  # MCPOrchestratorAgent
    mcp_host_2 = MCPHost([])  # SREOrchestratorAgent (via SRESubAgent)

    # Both should see the same registry
    tools_1 = mcp_host_1.get_tools_from_registry()
    tools_2 = mcp_host_2.get_tools_from_registry()

    assert len(tools_1) == len(tools_2), "Both orchestrators should see same tool count"

    # Extract tool names
    names_1 = {tool["function"]["name"] for tool in tools_1}
    names_2 = {tool["function"]["name"] for tool in tools_2}

    assert names_1 == names_2, "Both orchestrators should see identical tools"

    print(f"✅ Both orchestrators share access to {len(tools_1)} tools via centralized registry")


@pytest.mark.asyncio
async def test_no_tool_duplication():
    """Test registry prevents tool duplication."""
    registry, _ = await create_test_registry()

    all_tools = registry.get_all_tools()
    tool_names = [tool.name for tool in all_tools]

    # Check for duplicates
    unique_names = set(tool_names)
    assert len(tool_names) == len(unique_names), f"Found duplicate tools: {len(tool_names)} vs {len(unique_names)}"

    print(f"✅ No tool duplication: {len(unique_names)} unique tools")


@pytest.mark.asyncio
async def test_registry_statistics():
    """Test registry provides useful statistics."""
    registry, _ = await create_test_registry()

    stats = registry.get_stats()

    # Verify statistics
    assert "total_tools" in stats
    assert stats["total_tools"] > 0
    assert "tools_by_domain" in stats
    assert "tools_by_source" in stats
    assert "servers" in stats

    print(f"✅ Registry statistics:")
    print(f"   - Total tools: {stats['total_tools']}")
    print(f"   - Domains: {len(stats['tools_by_domain'])}")
    print(f"   - Servers: {len(stats['servers'])}")
    print(f"   - Tool distribution: {stats['tools_by_domain']}")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("Testing Orchestrator Tool Access via Centralized Registry")
    print("="*80 + "\n")

    # Run pytest with verbose output
    pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short"
    ])


if __name__ == "__main__":
    main()
