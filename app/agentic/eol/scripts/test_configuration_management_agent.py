#!/usr/bin/env python3
"""Test script for Configuration Management Agent.

Tests the specialized configuration management agent with various scenarios.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.configuration_management_agent import ConfigurationManagementAgent
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
    """Test configuration management agent initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Agent Initialization")
    logger.info("=" * 60)

    try:
        agent = ConfigurationManagementAgent()
        success = await agent.initialize()

        if success:
            logger.info("✓ Configuration Management Agent initialized")
            logger.info(f"  Agent ID: {agent.agent_id}")
            logger.info(f"  Agent Type: {agent.agent_type}")
            return agent
        else:
            logger.error("❌ Initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_scan_configuration(agent):
    """Test configuration scanning."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Scan Configuration")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "scan",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "include_settings": True
        })

        if result.get("status") == "success":
            scan = result.get("scan", {})
            logger.info("✓ Configuration scan completed")
            logger.info(f"  Total settings: {scan.get('total_settings')}")
            logger.info(f"  Categories: {scan.get('categories_scanned')}")
            logger.info(f"  Workflow ID: {result.get('workflow_id')}")
            return True
        else:
            logger.error(f"❌ Scan failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Scan failed: {exc}", exc_info=True)
        return False


async def test_detect_drift(agent):
    """Test configuration drift detection."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Detect Configuration Drift")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "drift",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "baseline_id": "baseline-prod-2024"
        })

        if result.get("status") == "success":
            drift = result.get("drift", {})
            logger.info("✓ Drift detection completed")
            logger.info(f"  Total drifts: {drift.get('total_drifts')}")
            logger.info(f"  Severity: {drift.get('severity')}")
            return True
        else:
            logger.error(f"❌ Drift detection failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Drift detection failed: {exc}", exc_info=True)
        return False


async def test_check_compliance(agent):
    """Test policy compliance checking."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Check Policy Compliance")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "compliance",
            "resource_group": "prod-rg",
            "policies": ["security", "tagging", "encryption"]
        })

        if result.get("status") == "success":
            compliance = result.get("compliance", {})
            logger.info("✓ Compliance check completed")
            logger.info(f"  Compliance score: {compliance.get('compliance_score')}")
            logger.info(f"  Violations: {compliance.get('total_violations')}")
            return True
        else:
            logger.error(f"❌ Compliance check failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Compliance check failed: {exc}", exc_info=True)
        return False


async def test_remediate_configuration(agent):
    """Test configuration remediation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Remediate Configuration")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "remediate",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "fixes": [
                {"setting": "httpsOnly", "value": True},
                {"setting": "minTlsVersion", "value": "1.2"}
            ]
        })

        if result.get("status") == "success":
            remediation = result.get("remediation", {})
            logger.info("✓ Remediation completed")
            logger.info(f"  Applied fixes: {remediation.get('applied_count')}")
            logger.info(f"  Failed fixes: {remediation.get('failed_count')}")
            return True
        else:
            logger.error(f"❌ Remediation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Remediation failed: {exc}", exc_info=True)
        return False


async def test_create_baseline(agent):
    """Test baseline creation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Create Configuration Baseline")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "baseline",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "baseline_name": "prod-baseline-2024"
        })

        if result.get("status") == "success":
            baseline = result.get("baseline", {})
            logger.info("✓ Baseline creation completed")
            logger.info(f"  Baseline ID: {baseline.get('baseline_id')}")
            logger.info(f"  Settings captured: {baseline.get('settings_count')}")
            return True
        else:
            logger.error(f"❌ Baseline creation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Baseline creation failed: {exc}", exc_info=True)
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
    logger.info("Configuration Management Agent Test Suite")
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

    # Test 2: Scan Configuration
    result = await test_scan_configuration(agent)
    all_passed = all_passed and result

    # Test 3: Detect Drift
    result = await test_detect_drift(agent)
    all_passed = all_passed and result

    # Test 4: Check Compliance
    result = await test_check_compliance(agent)
    all_passed = all_passed and result

    # Test 5: Remediate Configuration
    result = await test_remediate_configuration(agent)
    all_passed = all_passed and result

    # Test 6: Create Baseline
    result = await test_create_baseline(agent)
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
        logger.info("\nConfiguration Management Agent is fully operational!")
        logger.info("\nCapabilities demonstrated:")
        logger.info("  ✓ Configuration scanning")
        logger.info("  ✓ Drift detection")
        logger.info("  ✓ Policy compliance checking")
        logger.info("  ✓ Configuration remediation")
        logger.info("  ✓ Baseline management")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
