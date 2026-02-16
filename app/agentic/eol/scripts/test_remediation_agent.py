#!/usr/bin/env python3
"""Test script for Remediation Agent.

Tests the specialized remediation agent with various scenarios.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.remediation_agent import RemediationAgent
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
    """Test remediation agent initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Agent Initialization")
    logger.info("=" * 60)

    try:
        agent = RemediationAgent()
        success = await agent.initialize()

        if success:
            logger.info("✓ Remediation Agent initialized")
            logger.info(f"  Agent ID: {agent.agent_id}")
            logger.info(f"  Agent Type: {agent.agent_type}")
            logger.info(f"  Strategies: {len(agent.strategies)} issue types")
            return agent
        else:
            logger.error("❌ Initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_diagnose_resource(agent):
    """Test resource diagnostics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Diagnose Resource")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "diagnose",
            "resource_type": "app_service",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "symptoms": ["high_cpu", "slow_response"]
        })

        if result.get("status") == "success":
            diagnosis = result.get("diagnosis", {})
            logger.info("✓ Diagnosis completed")
            logger.info(f"  Issues found: {diagnosis.get('issues_found')}")
            logger.info(f"  Primary symptom: {diagnosis.get('primary_symptom')}")
            logger.info(f"  Workflow ID: {result.get('workflow_id')}")
            return True
        else:
            logger.error(f"❌ Diagnosis failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Diagnosis failed: {exc}", exc_info=True)
        return False


async def test_recommend_remediation(agent):
    """Test remediation recommendations."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Recommend Remediation")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "recommend",
            "issue_type": "high_cpu",
            "resource_type": "app_service",
            "context": {
                "current_instances": 2,
                "cpu_percent": 95
            }
        })

        if result.get("status") == "success":
            recommendations = result.get("recommendations", {})
            logger.info("✓ Recommendations generated")
            logger.info(f"  Total actions: {recommendations.get('total_actions')}")
            logger.info(f"  Recommended action: {recommendations.get('recommended_action')}")
            return True
        else:
            logger.error(f"❌ Recommendations failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Recommendations failed: {exc}", exc_info=True)
        return False


async def test_execute_remediation(agent):
    """Test remediation execution."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Execute Remediation")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "execute",
            "remediation_type": "restart",
            "resource_type": "app_service",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "approved": True
        })

        if result.get("status") == "success":
            execution = result.get("execution", {})
            logger.info("✓ Remediation executed")
            logger.info(f"  Status: {execution.get('execution_status')}")
            logger.info(f"  Backup created: {execution.get('backup_created')}")
            return True
        else:
            logger.error(f"❌ Execution failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Execution failed: {exc}", exc_info=True)
        return False


async def test_rollback_remediation(agent):
    """Test remediation rollback."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Rollback Remediation")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "rollback",
            "backup_id": "backup-12345",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app"
        })

        if result.get("status") == "success":
            rollback = result.get("rollback", {})
            logger.info("✓ Rollback completed")
            logger.info(f"  Status: {rollback.get('rollback_status')}")
            logger.info(f"  State restored: {rollback.get('state_restored')}")
            return True
        else:
            logger.error(f"❌ Rollback failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Rollback failed: {exc}", exc_info=True)
        return False


async def test_verify_remediation(agent):
    """Test remediation verification."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Verify Remediation")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "verify",
            "resource_id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/my-app",
            "expected_state": "healthy"
        })

        if result.get("status") == "success":
            verification = result.get("verification", {})
            logger.info("✓ Verification completed")
            logger.info(f"  Success: {verification.get('verification_success')}")
            logger.info(f"  Health status: {verification.get('health_status')}")
            return True
        else:
            logger.error(f"❌ Verification failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Verification failed: {exc}", exc_info=True)
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
    logger.info("Remediation Agent Test Suite")
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

    # Test 2: Diagnose Resource
    result = await test_diagnose_resource(agent)
    all_passed = all_passed and result

    # Test 3: Recommend Remediation
    result = await test_recommend_remediation(agent)
    all_passed = all_passed and result

    # Test 4: Execute Remediation
    result = await test_execute_remediation(agent)
    all_passed = all_passed and result

    # Test 5: Rollback Remediation
    result = await test_rollback_remediation(agent)
    all_passed = all_passed and result

    # Test 6: Verify Remediation
    result = await test_verify_remediation(agent)
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
        logger.info("\nRemediation Agent is fully operational!")
        logger.info("\nCapabilities demonstrated:")
        logger.info("  ✓ Resource diagnostics")
        logger.info("  ✓ Remediation recommendations")
        logger.info("  ✓ Remediation execution")
        logger.info("  ✓ Rollback capability")
        logger.info("  ✓ Verification")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
