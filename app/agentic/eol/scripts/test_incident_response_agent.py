#!/usr/bin/env python3
"""Test script for Incident Response Agent.

Tests the specialized incident response agent with various scenarios.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.incident_response_agent import IncidentResponseAgent
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
    """Test incident response agent initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Agent Initialization")
    logger.info("=" * 60)

    try:
        agent = IncidentResponseAgent()
        success = await agent.initialize()

        if success:
            logger.info("✓ Incident Response Agent initialized")
            logger.info(f"  Agent ID: {agent.agent_id}")
            logger.info(f"  Agent Type: {agent.agent_type}")
            return agent
        else:
            logger.error("❌ Initialization failed")
            return None

    except Exception as exc:
        logger.error(f"❌ Initialization failed: {exc}", exc_info=True)
        return None


async def test_triage(agent):
    """Test incident triage."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Incident Triage")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "triage",
            "incident_id": "INC-001",
            "description": "API gateway returning 500 errors for /users endpoint",
            "severity": "high"
        })

        if result.get("status") == "success":
            triage = result.get("triage", {})
            logger.info("✓ Triage completed successfully")
            logger.info(f"  Severity: {triage.get('severity')}")
            logger.info(f"  Priority: {triage.get('priority')}")
            logger.info(f"  Response time: {triage.get('response_time_mins')} minutes")
            logger.info(f"  Workflow ID: {result.get('workflow_id')}")
            return True
        else:
            logger.error(f"❌ Triage failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Triage failed: {exc}", exc_info=True)
        return False


async def test_correlation(agent):
    """Test alert correlation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Alert Correlation")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "correlate",
            "incident_id": "INC-001",
            "time_window": "1h",
            "severity": "high"
        })

        if result.get("status") == "success":
            correlation = result.get("correlation", {})
            logger.info("✓ Correlation completed successfully")
            logger.info(f"  Total alerts: {correlation.get('total_alerts')}")
            logger.info(f"  Time window: {correlation.get('time_window')}")
            logger.info(f"  Patterns detected: {len(correlation.get('patterns_detected', []))}")
            return True
        else:
            logger.error(f"❌ Correlation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Correlation failed: {exc}", exc_info=True)
        return False


async def test_impact_assessment(agent):
    """Test impact assessment."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Impact Assessment")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "impact",
            "incident_id": "INC-001",
            "resource_ids": [
                "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Web/sites/api-gateway"
            ]
        })

        if result.get("status") == "success":
            impact = result.get("impact", {})
            logger.info("✓ Impact assessment completed")
            logger.info(f"  Directly affected: {impact.get('directly_affected')}")
            logger.info(f"  Downstream affected: {impact.get('downstream_affected')}")
            logger.info(f"  Blast radius: {impact.get('blast_radius')}")
            return True
        else:
            logger.error(f"❌ Impact assessment failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Impact assessment failed: {exc}", exc_info=True)
        return False


async def test_rca(agent):
    """Test root cause analysis."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Root Cause Analysis")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "rca",
            "incident_id": "INC-001",
            "error_pattern": "500|internal server error|exception",
            "resource_group": "my-rg"
        })

        if result.get("status") == "success":
            rca = result.get("rca", {})
            logger.info("✓ RCA completed successfully")
            logger.info(f"  Likely causes: {len(rca.get('likely_causes', []))}")
            logger.info(f"  Confidence: {rca.get('confidence')}")
            logger.info(f"  Log errors found: {rca.get('evidence', {}).get('log_errors_found', 0)}")
            return True
        else:
            logger.error(f"❌ RCA failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ RCA failed: {exc}", exc_info=True)
        return False


async def test_remediation(agent):
    """Test remediation recommendations."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Remediation Recommendations")
    logger.info("=" * 60)

    try:
        result = await agent.handle_request({
            "action": "remediate",
            "incident_id": "INC-001",
            "issue_type": "performance_degradation",
            "affected_resources": ["api-gateway"]
        })

        if result.get("status") == "success":
            remediation = result.get("remediation", {})
            logger.info("✓ Remediation recommendations generated")
            logger.info(f"  Actions: {len(remediation.get('recommended_actions', []))}")
            logger.info(f"  Estimated time: {remediation.get('estimated_time')}")
            logger.info(f"  Risk level: {remediation.get('risk_level')}")
            logger.info(f"  Requires approval: {remediation.get('requires_approval')}")
            return True
        else:
            logger.error(f"❌ Remediation failed: {result.get('error')}")
            return False

    except Exception as exc:
        logger.error(f"❌ Remediation failed: {exc}", exc_info=True)
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
    logger.info("Incident Response Agent Test Suite")
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

    # Test 2: Triage
    result = await test_triage(agent)
    all_passed = all_passed and result

    # Test 3: Correlation
    result = await test_correlation(agent)
    all_passed = all_passed and result

    # Test 4: Impact Assessment
    result = await test_impact_assessment(agent)
    all_passed = all_passed and result

    # Test 5: RCA
    result = await test_rca(agent)
    all_passed = all_passed and result

    # Test 6: Remediation
    result = await test_remediation(agent)
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
        logger.info("\nIncident Response Agent is fully operational!")
        logger.info("\nCapabilities demonstrated:")
        logger.info("  ✓ Automated incident triage")
        logger.info("  ✓ Alert correlation and pattern detection")
        logger.info("  ✓ Impact assessment")
        logger.info("  ✓ Root cause analysis")
        logger.info("  ✓ Remediation recommendations")
        logger.info("  ✓ Workflow context persistence")
        logger.info("\nNext steps:")
        logger.info("  1. Test postmortem generation")
        logger.info("  2. Test full incident response workflow")
        logger.info("  3. Build additional specialist agents")
        logger.info("  4. Create FastAPI endpoints")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
