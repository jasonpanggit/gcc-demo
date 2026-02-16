#!/usr/bin/env python3
"""Test script for SLO Management Agent.

Tests the specialized SLO management agent with various scenarios.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.slo_management_agent import SLOManagementAgent
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
    """Test SLO management agent initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Agent Initialization")
    logger.info("=" * 60)

    try:
        agent = SLOManagementAgent()
        success = await agent.initialize()

        if success:
            logger.info("✓ SLO Management Agent initialized")
            logger.info(f"  Agent ID: {agent.agent_id}")
            logger.info(f"  Agent Type: {agent.agent_type}")
            logger.info(f"  SLO Targets: {agent.slo_targets}")
            return agent
        else:
            logger.error("❌ Initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_track_slo_metrics(agent):
    """Test SLO metrics tracking."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Track SLO Metrics")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "track",
            "service": "api-gateway",
            "slo_type": "availability",
            "time_window": "7d"
        })

        if result.get("status") == "success":
            tracking = result.get("tracking", {})
            logger.info("✓ SLO tracking completed")
            logger.info(f"  Service: {tracking.get('service')}")
            logger.info(f"  SLO type: {tracking.get('slo_type')}")
            logger.info(f"  Current value: {tracking.get('current_value')}")
            logger.info(f"  Status: {tracking.get('slo_status')}")
            return True
        else:
            logger.error(f"❌ Tracking failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Tracking failed: {exc}", exc_info=True)
        return False


async def test_calculate_error_budget(agent):
    """Test error budget calculation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Calculate Error Budget")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "budget",
            "service": "api-gateway",
            "slo_target": 99.9,
            "time_window": "28d"
        })

        if result.get("status") == "success":
            budget = result.get("budget", {})
            logger.info("✓ Error budget calculation completed")
            logger.info(f"  Budget remaining: {budget.get('budget_remaining_percent')}%")
            logger.info(f"  Budget health: {budget.get('budget_health')}")
            logger.info(f"  Time to exhaustion: {budget.get('time_to_exhaustion')}")
            return True
        else:
            logger.error(f"❌ Budget calculation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Budget calculation failed: {exc}", exc_info=True)
        return False


async def test_configure_alerts(agent):
    """Test SLO alert configuration."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Configure SLO Alerts")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "alert",
            "service": "api-gateway",
            "slo_target": 99.9,
            "alert_windows": ["1h", "6h", "24h"]
        })

        if result.get("status") == "success":
            alerts = result.get("alerts", {})
            logger.info("✓ Alert configuration completed")
            logger.info(f"  Total policies: {alerts.get('total_policies')}")
            logger.info(f"  Fast burn: {alerts.get('fast_burn', {}).get('configured')}")
            logger.info(f"  Slow burn: {alerts.get('slow_burn', {}).get('configured')}")
            return True
        else:
            logger.error(f"❌ Alert configuration failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Alert configuration failed: {exc}", exc_info=True)
        return False


async def test_generate_report(agent):
    """Test SLO compliance report generation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Generate SLO Report")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "report",
            "service": "api-gateway",
            "time_range": "30d"
        })

        if result.get("status") == "success":
            report = result.get("report", {})
            logger.info("✓ Report generation completed")
            logger.info(f"  Overall health: {report.get('overall_health')}")
            logger.info(f"  SLOs tracked: {report.get('slos_tracked')}")
            logger.info(f"  Key findings: {len(report.get('key_findings', []))}")
            return True
        else:
            logger.error(f"❌ Report generation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Report generation failed: {exc}", exc_info=True)
        return False


async def test_forecast_burn_rate(agent):
    """Test error budget burn rate forecasting."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Forecast Burn Rate")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "forecast",
            "service": "api-gateway",
            "forecast_days": 7
        })

        if result.get("status") == "success":
            forecast = result.get("forecast", {})
            logger.info("✓ Burn rate forecast completed")
            logger.info(f"  Current burn rate: {forecast.get('current_burn_rate')}")
            logger.info(f"  Risk level: {forecast.get('risk_level')}")
            logger.info(f"  Recommendations: {len(forecast.get('recommendations', []))}")
            return True
        else:
            logger.error(f"❌ Forecast failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Forecast failed: {exc}", exc_info=True)
        return False


async def test_agent_metrics(agent):
    """Test agent metrics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Agent Metrics")
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
    logger.info("SLO Management Agent Test Suite")
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

    # Test 2: Track SLO Metrics
    result = await test_track_slo_metrics(agent)
    all_passed = all_passed and result

    # Test 3: Calculate Error Budget
    result = await test_calculate_error_budget(agent)
    all_passed = all_passed and result

    # Test 4: Configure Alerts
    result = await test_configure_alerts(agent)
    all_passed = all_passed and result

    # Test 5: Generate Report
    result = await test_generate_report(agent)
    all_passed = all_passed and result

    # Test 6: Forecast Burn Rate
    result = await test_forecast_burn_rate(agent)
    all_passed = all_passed and result

    # Test 7: Metrics
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
        logger.info("\nSLO Management Agent is fully operational!")
        logger.info("\nCapabilities demonstrated:")
        logger.info("  ✓ SLO metrics tracking")
        logger.info("  ✓ Error budget calculation")
        logger.info("  ✓ Alert configuration")
        logger.info("  ✓ Compliance reporting")
        logger.info("  ✓ Burn rate forecasting")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
