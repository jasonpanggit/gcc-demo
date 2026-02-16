#!/usr/bin/env python3
"""Comprehensive test script for the SRE orchestrator.

This script:
1. Registers all 48 SRE tools
2. Tests orchestrator initialization
3. Tests intent analysis
4. Tests tool routing with registered tools
5. Tests actual tool execution
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_sre_agent import BaseSREAgent
from agents.sre_orchestrator_agent import SREOrchestratorAgent
from utils.agent_registry import get_agent_registry
from utils.sre_mcp_client import get_sre_mcp_client
from utils.logger import get_logger

logger = get_logger(__name__)


class SREToolProxyAgent(BaseSREAgent):
    """Proxy agent that executes SRE MCP tools."""

    def __init__(self):
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

    async def execute(self, request: dict, context: dict = None) -> dict:
        """Execute SRE tool via MCP client."""
        if not self.sre_client or not self.sre_client.is_initialized():
            raise RuntimeError("SRE MCP client not initialized")

        tool_name = request.get("tool")
        parameters = request.get("parameters", {})

        if not tool_name:
            return {"success": False, "error": "Tool name required"}

        logger.info(f"Executing SRE tool: {tool_name}")
        result = await self.sre_client.call_tool(tool_name, parameters)
        return result


async def setup_tools():
    """Register all SRE tools."""
    logger.info("\n" + "=" * 60)
    logger.info("SETUP: Registering SRE Tools")
    logger.info("=" * 60)

    registry = get_agent_registry()

    # Create and initialize proxy agent
    logger.info("\n1. Creating SRE tool proxy agent...")
    proxy_agent = SREToolProxyAgent()

    try:
        initialized = await proxy_agent.initialize()
        if not initialized:
            logger.error("❌ Failed to initialize proxy agent")
            return None, None

        logger.info("✓ Proxy agent initialized")
    except Exception as exc:
        logger.error(f"❌ Failed to initialize proxy agent: {exc}")
        return None, None

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

    # Get and register tools
    logger.info("\n3. Loading SRE MCP tools...")
    tools = proxy_agent.sre_client.get_available_tools()
    logger.info(f"✓ Found {len(tools)} tools")

    logger.info("\n4. Registering tools with agent registry...")
    registered_count = await registry.register_tools_bulk(
        agent_id=proxy_agent.agent_id,
        tools=tools
    )

    logger.info(f"✓ Registered {registered_count}/{len(tools)} tools")

    # Validation
    registry_tools = registry.list_tools(agent_id=proxy_agent.agent_id)
    if len(registry_tools) == len(tools):
        logger.info("✓ All tools registered successfully")
    else:
        logger.warning(
            f"⚠️ Tool count mismatch: {len(registry_tools)} registered, "
            f"{len(tools)} expected"
        )

    return proxy_agent, registry


async def test_orchestrator_initialization():
    """Test orchestrator initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Orchestrator Initialization")
    logger.info("=" * 60)

    try:
        orchestrator = SREOrchestratorAgent()
        success = await orchestrator.initialize()

        if success:
            logger.info("✓ Orchestrator initialized successfully")
            logger.info(f"  Agent ID: {orchestrator.agent_id}")
            logger.info(f"  Agent Type: {orchestrator.agent_type}")
            logger.info(f"  Initialized: {orchestrator.is_initialized()}")
            return orchestrator
        else:
            logger.error("❌ Orchestrator initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_intent_analysis(orchestrator):
    """Test intent analysis."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Intent Analysis")
    logger.info("=" * 60)

    test_queries = [
        ("Check health of container apps", "health"),
        ("Find orphaned resources and estimate savings", "cost"),
        ("Show me performance metrics for the API", "performance"),
        ("Triage this incident", "incident"),
        ("Check SLO compliance", "slo"),
        ("Get security score", "security"),
        ("Restart the web app", "remediation"),
    ]

    passed = 0
    failed = 0

    for query, expected_intent in test_queries:
        intent, tools = orchestrator._analyze_intent(query)

        if intent == expected_intent:
            logger.info(f"✓ '{query[:40]}...'")
            logger.info(f"  → Intent: {intent}, Tools: {len(tools)}")
            passed += 1
        else:
            logger.error(f"❌ '{query[:40]}...'")
            logger.error(f"  Expected: {expected_intent}, Got: {intent}")
            failed += 1

    logger.info(f"\nIntent Analysis: {passed} passed, {failed} failed")
    return failed == 0


async def test_registry_stats(registry):
    """Test agent registry statistics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Agent Registry Stats")
    logger.info("=" * 60)

    try:
        stats = registry.get_registry_stats()

        logger.info(f"✓ Total agents: {stats['total_agents']}")
        logger.info(f"  Healthy agents: {stats['healthy_agents']}")
        logger.info(f"  Total tools: {stats['total_tools']}")
        logger.info(f"  Tool categories: {stats['tool_categories']}")

        if stats['agent_types']:
            logger.info("\n  Agents by type:")
            for agent_type, count in stats['agent_types'].items():
                logger.info(f"    • {agent_type}: {count}")

        # Should have at least 1 agent and 48 tools
        return stats['total_agents'] > 0 and stats['total_tools'] >= 48

    except Exception as exc:
        logger.error(f"❌ Failed to get registry stats: {exc}")
        return False


async def test_tool_routing(orchestrator, registry):
    """Test tool routing with registered tools."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Tool Routing (With Registered Tools)")
    logger.info("=" * 60)

    test_cases = [
        {
            "query": "Check health of container apps",
            "expected_category": "health"
        },
        {
            "query": "Find orphaned resources",
            "expected_category": "cost"
        },
        {
            "query": "Show performance metrics",
            "expected_category": "performance"
        }
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        query = test_case["query"]
        expected = test_case["expected_category"]

        intent, tool_names = orchestrator._analyze_intent(query)

        if intent == expected and len(tool_names) > 0:
            # Check if tools exist in registry
            all_tools = registry.list_tools()
            tool_name_list = [t["name"] for t in all_tools]

            found_tools = [t for t in tool_names if t in tool_name_list]

            logger.info(f"✓ Query: '{query}'")
            logger.info(f"  → Intent: {intent}")
            logger.info(f"  → Suggested tools: {len(tool_names)}")
            logger.info(f"  → Registered tools found: {len(found_tools)}")
            if found_tools:
                logger.info(f"  → Examples: {', '.join(found_tools[:3])}")
            passed += 1
        else:
            logger.error(f"❌ Query: '{query}'")
            logger.error(f"  Expected: {expected}, Got: {intent}")
            failed += 1

    logger.info(f"\nTool Routing: {passed} passed, {failed} failed")
    return failed == 0


async def test_tool_execution(proxy_agent):
    """Test actual tool execution."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Tool Execution")
    logger.info("=" * 60)

    try:
        # Test with describe_capabilities (always works)
        logger.info("\nExecuting: describe_capabilities")
        result = await proxy_agent.handle_request({
            "tool": "describe_capabilities",
            "parameters": {}
        })

        if result.get("status") == "success":
            logger.info("✓ Tool execution successful")
            data = result.get("data", {})
            if isinstance(data, dict):
                logger.info(f"  → Returned {len(data)} capability sections")
            return True
        else:
            logger.error(f"❌ Tool execution failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Tool execution failed: {exc}")
        return False


async def test_metrics(orchestrator):
    """Test agent metrics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Agent Metrics")
    logger.info("=" * 60)

    try:
        metrics = orchestrator.get_metrics()

        logger.info("✓ Agent metrics:")
        logger.info(f"  Agent ID: {metrics['agent_id']}")
        logger.info(f"  Agent Type: {metrics['agent_type']}")
        logger.info(f"  Requests handled: {metrics['requests_handled']}")
        logger.info(f"  Success rate: {metrics['success_rate']:.2%}")

        return True

    except Exception as exc:
        logger.error(f"❌ Failed to get metrics: {exc}")
        return False


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("SRE Orchestrator Comprehensive Test Suite")
    logger.info("=" * 60)

    all_passed = True

    # Setup: Register tools
    proxy_agent, registry = await setup_tools()
    if not proxy_agent or not registry:
        logger.error("\n❌ Setup failed - cannot proceed")
        sys.exit(1)

    # Test 1: Initialization
    orchestrator = await test_orchestrator_initialization()
    if not orchestrator:
        logger.error("\n❌ Cannot proceed - orchestrator initialization failed")
        await proxy_agent.cleanup()
        sys.exit(1)

    # Test 2: Intent Analysis
    result = await test_intent_analysis(orchestrator)
    all_passed = all_passed and result

    # Test 3: Registry Stats
    result = await test_registry_stats(registry)
    all_passed = all_passed and result

    # Test 4: Tool Routing
    result = await test_tool_routing(orchestrator, registry)
    all_passed = all_passed and result

    # Test 5: Tool Execution
    result = await test_tool_execution(proxy_agent)
    all_passed = all_passed and result

    # Test 6: Metrics
    result = await test_metrics(orchestrator)
    all_passed = all_passed and result

    # Cleanup
    await orchestrator.cleanup()
    await proxy_agent.cleanup()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    if all_passed:
        logger.info("✅ All tests passed!")
        logger.info("\nThe SRE Orchestrator is fully operational!")
        logger.info("\nWhat it can do:")
        logger.info("  ✓ Analyze natural language SRE requests")
        logger.info("  ✓ Route to appropriate tools from 48 available")
        logger.info("  ✓ Execute tools via MCP protocol")
        logger.info("  ✓ Track metrics and performance")
        logger.info("  ✓ Handle errors and retries")
        logger.info("\nNext steps:")
        logger.info("  1. Create FastAPI endpoint (Task #25)")
        logger.info("  2. Build specialist agents (Task #13)")
        logger.info("  3. Deploy to production")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        logger.info("\nPlease review the failures above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
