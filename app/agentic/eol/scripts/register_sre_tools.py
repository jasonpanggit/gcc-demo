#!/usr/bin/env python3
"""Register all SRE MCP tools with the orchestrator.

This script:
1. Initializes the SRE MCP server
2. Extracts all tool definitions
3. Registers tools with the agent registry
4. Creates a proxy agent for tool execution
5. Validates registration
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_sre_agent import BaseSREAgent
from utils.agent_registry import get_agent_registry
from utils.sre_mcp_client import get_sre_mcp_client
from utils.logger import get_logger

logger = get_logger(__name__)


class SREToolProxyAgent(BaseSREAgent):
    """Proxy agent that executes SRE MCP tools.

    This agent wraps the SRE MCP client and executes tools
    on behalf of the orchestrator.
    """

    def __init__(self):
        """Initialize SRE tool proxy agent."""
        super().__init__(
            agent_type="sre-tool-proxy",
            agent_id="sre-mcp-server",
            max_retries=2,
            timeout=120
        )
        self.sre_client = None

    async def _initialize_impl(self) -> None:
        """Initialize SRE MCP client."""
        try:
            self.sre_client = await get_sre_mcp_client()
            logger.info("✓ SRE MCP client initialized")
        except Exception as exc:
            logger.error(f"Failed to initialize SRE MCP client: {exc}")
            raise

    async def _cleanup_impl(self) -> None:
        """Cleanup SRE MCP client."""
        if self.sre_client:
            await self.sre_client.cleanup()

    async def execute(
        self,
        request: dict,
        context: dict = None
    ) -> dict:
        """Execute SRE tool via MCP client.

        Args:
            request: Request with 'tool' and 'parameters'
            context: Optional workflow context

        Returns:
            Tool execution result
        """
        if not self.sre_client or not self.sre_client.is_initialized():
            raise RuntimeError("SRE MCP client not initialized")

        tool_name = request.get("tool")
        parameters = request.get("parameters", {})

        if not tool_name:
            return {
                "success": False,
                "error": "Tool name required"
            }

        logger.info(f"Executing SRE tool: {tool_name}")

        # Execute tool via MCP client
        result = await self.sre_client.call_tool(tool_name, parameters)

        return result


async def register_sre_tools():
    """Register all SRE MCP tools with the orchestrator."""
    logger.info("=" * 60)
    logger.info("SRE Tool Registration")
    logger.info("=" * 60)

    # Get registry
    registry = get_agent_registry()

    # Create and initialize proxy agent
    logger.info("\n1. Creating SRE tool proxy agent...")
    proxy_agent = SREToolProxyAgent()

    try:
        initialized = await proxy_agent.initialize()
        if not initialized:
            logger.error("❌ Failed to initialize proxy agent")
            return False

        logger.info("✓ Proxy agent initialized")

    except Exception as exc:
        logger.error(f"❌ Failed to initialize proxy agent: {exc}")
        return False

    # Register agent
    logger.info("\n2. Registering proxy agent...")
    await registry.register_agent(
        proxy_agent,
        metadata={
            "description": "Proxy agent for SRE MCP server tools",
            "source": "sre_mcp_server.py",
            "total_tools": len(proxy_agent.sre_client.get_available_tools())
        }
    )

    # Get tools from SRE MCP client
    logger.info("\n3. Loading SRE MCP tools...")
    tools = proxy_agent.sre_client.get_available_tools()
    logger.info(f"✓ Found {len(tools)} tools")

    # Categorize tools
    tool_categories = categorize_tools(tools)

    logger.info("\n4. Tool breakdown by category:")
    for category, category_tools in tool_categories.items():
        logger.info(f"   • {category}: {len(category_tools)} tools")

    # Register tools
    logger.info("\n5. Registering tools with agent registry...")
    registered_count = await registry.register_tools_bulk(
        agent_id=proxy_agent.agent_id,
        tools=tools
    )

    logger.info(f"✓ Registered {registered_count}/{len(tools)} tools")

    # Validation
    logger.info("\n6. Validating registration...")
    registry_tools = registry.list_tools(agent_id=proxy_agent.agent_id)

    if len(registry_tools) == len(tools):
        logger.info("✓ All tools registered successfully")
    else:
        logger.warning(
            f"⚠️ Tool count mismatch: {len(registry_tools)} registered, "
            f"{len(tools)} expected"
        )

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Registration Summary")
    logger.info("=" * 60)

    stats = registry.get_registry_stats()
    logger.info(f"Total agents: {stats['total_agents']}")
    logger.info(f"Total tools: {stats['total_tools']}")
    logger.info(f"Tool categories: {stats['tool_categories']}")

    logger.info("\n✓ Tool registration complete!")

    return True


def categorize_tools(tools: list) -> dict:
    """Categorize tools by their purpose.

    Args:
        tools: List of tool definitions

    Returns:
        Dictionary mapping categories to tool lists
    """
    categories = {
        "health": [],
        "incident": [],
        "performance": [],
        "cost": [],
        "slo": [],
        "security": [],
        "remediation": [],
        "config": [],
        "observability": [],
        "other": []
    }

    category_keywords = {
        "health": ["health", "diagnose", "diagnostic", "check"],
        "incident": ["incident", "triage", "alert", "correlate", "postmortem"],
        "performance": ["performance", "metrics", "bottleneck", "capacity"],
        "cost": ["cost", "savings", "orphaned", "idle", "budget"],
        "slo": ["slo", "sli", "error_budget"],
        "security": ["security", "compliance", "vulnerability", "policy"],
        "remediation": ["restart", "scale", "clear", "remediation"],
        "config": ["configuration", "query_", "app_service", "container_app", "aks", "apim"],
        "observability": ["traces", "telemetry", "insights", "logs"]
    }

    for tool in tools:
        tool_name = tool.get("function", {}).get("name", "").lower()
        categorized = False

        for category, keywords in category_keywords.items():
            if any(keyword in tool_name for keyword in keywords):
                categories[category].append(tool)
                categorized = True
                break

        if not categorized:
            categories["other"].append(tool)

    return categories


async def print_tool_details():
    """Print detailed information about registered tools."""
    registry = get_agent_registry()

    tools = registry.list_tools()
    categories_map = {}

    # Group tools by category
    for tool in tools:
        tool_def = tool.get("definition", {})
        func_def = tool_def.get("function", {})
        name = func_def.get("name", "unknown")
        description = func_def.get("description", "No description")

        # Determine category
        category = "other"
        for cat in ["health", "incident", "performance", "cost", "slo",
                    "security", "remediation", "config", "observability"]:
            if cat in name.lower():
                category = cat
                break

        if category not in categories_map:
            categories_map[category] = []

        categories_map[category].append({
            "name": name,
            "description": description[:80] + "..." if len(description) > 80 else description
        })

    # Print organized list
    print("\n" + "=" * 80)
    print("Registered SRE Tools")
    print("=" * 80)

    for category, tools_list in sorted(categories_map.items()):
        print(f"\n{category.upper()} ({len(tools_list)} tools)")
        print("-" * 80)
        for tool in tools_list:
            print(f"  • {tool['name']}")
            print(f"    {tool['description']}")


async def test_tool_execution():
    """Test executing a tool through the orchestrator."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Tool Execution")
    logger.info("=" * 60)

    registry = get_agent_registry()

    # Get proxy agent
    agent = registry.get_agent("sre-mcp-server")
    if not agent:
        logger.error("❌ Proxy agent not found")
        return False

    # Test with describe_capabilities (should always work)
    logger.info("\nTesting: describe_capabilities")
    result = await agent.handle_request({
        "tool": "describe_capabilities",
        "parameters": {}
    })

    if result.get("status") == "success":
        logger.info("✓ Tool execution successful")
        return True
    else:
        logger.error(f"❌ Tool execution failed: {result.get('error')}")
        return False


async def main():
    """Main entry point."""
    try:
        # Register tools
        success = await register_sre_tools()

        if not success:
            logger.error("❌ Tool registration failed")
            sys.exit(1)

        # Print tool details
        await print_tool_details()

        # Test tool execution
        test_success = await test_tool_execution()

        if test_success:
            logger.info("\n✅ All tests passed!")
            sys.exit(0)
        else:
            logger.error("\n❌ Tests failed")
            sys.exit(1)

    except Exception as exc:
        logger.error(f"❌ Registration failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
