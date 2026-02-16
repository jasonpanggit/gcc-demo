#!/usr/bin/env python3
"""Test script for Performance Analysis Agent.

Tests the specialized performance analysis agent with various scenarios.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.performance_analysis_agent import PerformanceAnalysisAgent
from agents.base_sre_agent import BaseSREAgent
from utils.agent_registry import get_agent_registry
from utils.sre_mcp_client import get_sre_mcp_client
from utils.logger import get_logger

logger = get_logger(__name__)


class SREToolProxyAgent(BaseSREAgent):
    """Proxy agent for SRE MCP tools."""

    def __init__(self):
        super().__init__(
            agent_type="sre-tool-proxy",
            agent_id="sre-mcp-server",
            max_retries=2,
            timeout=120
        )
        self.sre_client = None

    async def _initialize_impl(self) -> None:
        try:
            self.sre_client = await get_sre_mcp_client()
            logger.info("✓ SRE MCP client initialized")
        except Exception as exc:
            logger.error(f"Failed to initialize SRE MCP client: {exc}")
            raise

    async def _cleanup_impl(self) -> None:
        if self.sre_client:
            await self.sre_client.cleanup()

    async def execute(self, request: dict, context: dict = None) -> dict:
        if not self.sre_client or not self.sre_client.is_initialized():
            raise RuntimeError("SRE MCP client not initialized")

        tool_name = request.get("tool")
        parameters = request.get("parameters", {})

        if not tool_name:
            return {"success": False, "error": "Tool name required"}

        result = await self.sre_client.call_tool(tool_name, parameters)
        return result


async def setup_tools():
    """Register SRE tools."""
    logger.info("\n" + "=" * 60)
    logger.info("SETUP: Registering SRE Tools")
    logger.info("=" * 60)

    registry = get_agent_registry()

    # Create and initialize proxy agent
    proxy_agent = SREToolProxyAgent()

    try:
        initialized = await proxy_agent.initialize()
        if not initialized:
            logger.error("❌ Failed to initialize proxy agent")
            return None

        logger.info("✓ Proxy agent initialized")
    except Exception as exc:
        logger.error(f"❌ Failed to initialize proxy agent: {exc}")
        return None

    # Register agent
    await registry.register_agent(
        proxy_agent,
        metadata={"description": "Proxy agent for SRE MCP server tools"}
    )

    # Register tools
    tools = proxy_agent.sre_client.get_available_tools()
    registered_count = await registry.register_tools_bulk(
        agent_id=proxy_agent.agent_id,
        tools=tools
    )

    logger.info(f"✓ Registered {registered_count}/{len(tools)} tools")

    return proxy_agent


async def test_agent_initialization():
    """Test performance analysis agent initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Agent Initialization")
    logger.info("=" * 60)

    try:
        agent = PerformanceAnalysisAgent()
        success = await agent.initialize()

        if success:
            logger.info("✓ Performance Analysis Agent initialized")
            logger.info(f"  Agent ID: {agent.agent_id}")
            logger.info(f"  Agent Type: {agent.agent_type}")
            return agent
        else:
            logger.error("❌ Initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_analyze_performance(agent):
    """Test performance analysis."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Analyze Performance")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "analyze",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "metrics": ["cpu", "memory", "network"],
            "time_range": "1h"
        })

        if result.get("status") == "success":
            analysis = result.get("analysis", {})
            logger.info("✓ Performance analysis completed")
            logger.info(f"  Time range: {analysis.get('time_range')}")
            logger.info(f"  Metrics collected: {analysis.get('metrics_collected')}")
            logger.info(f"  Workflow ID: {result.get('workflow_id')}")
            return True
        else:
            logger.error(f"❌ Analysis failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Analysis failed: {exc}", exc_info=True)
        return False


async def test_identify_bottlenecks(agent):
    """Test bottleneck identification."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Identify Bottlenecks")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "bottlenecks",
            "resource_group": "prod-rg",
            "time_range": "24h"
        })

        if result.get("status") == "success":
            bottlenecks = result.get("bottlenecks", {})
            logger.info("✓ Bottleneck analysis completed")
            logger.info(f"  Total found: {bottlenecks.get('total_found')}")
            logger.info(f"  Recommendations: {len(bottlenecks.get('recommendations', []))}")
            return True
        else:
            logger.error(f"❌ Bottleneck analysis failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Bottleneck analysis failed: {exc}", exc_info=True)
        return False


async def test_detect_anomalies(agent):
    """Test anomaly detection."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Detect Anomalies")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "anomalies",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "metric_name": "cpu_percent",
            "time_range": "24h",
            "sensitivity": "medium"
        })

        if result.get("status") == "success":
            anomalies = result.get("anomalies", {})
            logger.info("✓ Anomaly detection completed")
            logger.info(f"  Total detected: {anomalies.get('total_detected')}")
            logger.info(f"  Severity: {anomalies.get('severity')}")
            return True
        else:
            logger.error(f"❌ Anomaly detection failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Anomaly detection failed: {exc}", exc_info=True)
        return False


async def test_plan_capacity(agent):
    """Test capacity planning."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Plan Capacity")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "capacity",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "forecast_days": 30
        })

        if result.get("status") == "success":
            capacity = result.get("capacity", {})
            logger.info("✓ Capacity planning completed")
            logger.info(f"  Recommendations: {len(capacity.get('recommendations', []))}")
            logger.info(f"  Action required: {capacity.get('action_required')}")
            return True
        else:
            logger.error(f"❌ Capacity planning failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Capacity planning failed: {exc}", exc_info=True)
        return False


async def test_recommend_optimizations(agent):
    """Test optimization recommendations."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Recommend Optimizations")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "optimize"
        })

        if result.get("status") == "success":
            optimizations = result.get("optimizations", {})
            logger.info("✓ Optimization recommendations generated")
            logger.info(f"  Immediate actions: {len(optimizations.get('immediate_actions', []))}")
            logger.info(f"  Short-term actions: {len(optimizations.get('short_term_actions', []))}")
            logger.info(f"  Long-term actions: {len(optimizations.get('long_term_actions', []))}")
            return True
        else:
            logger.error(f"❌ Optimization failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Optimization failed: {exc}", exc_info=True)
        return False


async def test_compare_baseline(agent):
    """Test baseline comparison."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Compare Baseline")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "compare",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "baseline_period": "7d",
            "comparison_period": "1d"
        })

        if result.get("status") == "success":
            comparison = result.get("comparison", {})
            logger.info("✓ Baseline comparison completed")
            logger.info(f"  Deviations: {len(comparison.get('deviations', []))}")
            logger.info(f"  Overall trend: {comparison.get('overall_trend')}")
            return True
        else:
            logger.error(f"❌ Baseline comparison failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Baseline comparison failed: {exc}", exc_info=True)
        return False


async def test_agent_metrics(agent):
    """Test agent metrics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 8: Agent Metrics")
    logger.info("=" * 60)

    try:
        metrics = agent.get_metrics()

        logger.info("✓ Agent metrics:")
        logger.info(f"  Requests handled: {metrics['requests_handled']}")
        logger.info(f"  Requests succeeded: {metrics['requests_succeeded']}")
        logger.info(f"  Requests failed: {metrics['requests_failed']}")
        logger.info(f"  Success rate: {metrics['success_rate']:.2%}")
        logger.info(f"  Avg execution time: {metrics['avg_execution_time']:.2f}s")

        return True

    except Exception as exc:
        logger.error(f"❌ Failed to get metrics: {exc}")
        return False


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Performance Analysis Agent Test Suite")
    logger.info("=" * 60)

    all_passed = True

    # Setup: Register tools
    proxy_agent = await setup_tools()
    if not proxy_agent:
        logger.error("\n❌ Setup failed - cannot proceed")
        sys.exit(1)

    # Test 1: Initialization
    agent = await test_agent_initialization()
    if not agent:
        logger.error("\n❌ Cannot proceed - agent initialization failed")
        await proxy_agent.cleanup()
        sys.exit(1)

    # Test 2: Analyze Performance
    result = await test_analyze_performance(agent)
    all_passed = all_passed and result

    # Test 3: Identify Bottlenecks
    result = await test_identify_bottlenecks(agent)
    all_passed = all_passed and result

    # Test 4: Detect Anomalies
    result = await test_detect_anomalies(agent)
    all_passed = all_passed and result

    # Test 5: Plan Capacity
    result = await test_plan_capacity(agent)
    all_passed = all_passed and result

    # Test 6: Recommend Optimizations
    result = await test_recommend_optimizations(agent)
    all_passed = all_passed and result

    # Test 7: Compare Baseline
    result = await test_compare_baseline(agent)
    all_passed = all_passed and result

    # Test 8: Metrics
    result = await test_agent_metrics(agent)
    all_passed = all_passed and result

    # Cleanup
    await agent.cleanup()
    await proxy_agent.cleanup()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    if all_passed:
        logger.info("✅ All tests passed!")
        logger.info("\nPerformance Analysis Agent is fully operational!")
        logger.info("\nCapabilities demonstrated:")
        logger.info("  ✓ Performance metrics analysis")
        logger.info("  ✓ Bottleneck identification")
        logger.info("  ✓ Anomaly detection")
        logger.info("  ✓ Capacity planning")
        logger.info("  ✓ Optimization recommendations")
        logger.info("  ✓ Baseline comparison")
        logger.info("\nNext: Build more specialist agents (Cost, Security, Health, Config, SLO, Remediation)")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
