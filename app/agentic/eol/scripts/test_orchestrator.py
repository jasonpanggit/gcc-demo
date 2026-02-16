#!/usr/bin/env python3
"""Simple test script for the SRE orchestrator.

Tests:
1. Orchestrator initialization
2. Intent analysis
3. Tool routing
4. Basic execution
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.sre_orchestrator_agent import SREOrchestratorAgent
from utils.agent_registry import get_agent_registry
from utils.logger import get_logger

logger = get_logger(__name__)


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


async def test_capabilities(orchestrator):
    """Test getting orchestrator capabilities."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Orchestrator Capabilities")
    logger.info("=" * 60)

    try:
        capabilities = orchestrator.get_capabilities()

        logger.info(f"✓ Orchestrator version: {capabilities['orchestrator_version']}")
        logger.info(f"  Total tools: {capabilities['total_tools']}")
        logger.info(f"  Total agents: {capabilities['total_agents']}")
        logger.info(f"  Categories: {', '.join(capabilities['categories'])}")

        logger.info("\n  Tools by category:")
        for category, tools in capabilities['tools_by_category'].items():
            logger.info(f"    • {category}: {len(tools)} tools")

        return True

    except Exception as exc:
        logger.error(f"❌ Failed to get capabilities: {exc}")
        return False


async def test_registry_stats():
    """Test agent registry statistics."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Agent Registry Stats")
    logger.info("=" * 60)

    try:
        registry = get_agent_registry()
        stats = registry.get_registry_stats()

        logger.info(f"✓ Total agents: {stats['total_agents']}")
        logger.info(f"  Healthy agents: {stats['healthy_agents']}")
        logger.info(f"  Total tools: {stats['total_tools']}")
        logger.info(f"  Tool categories: {stats['tool_categories']}")

        if stats['agent_types']:
            logger.info("\n  Agents by type:")
            for agent_type, count in stats['agent_types'].items():
                logger.info(f"    • {agent_type}: {count}")

        return stats['total_agents'] > 0

    except Exception as exc:
        logger.error(f"❌ Failed to get registry stats: {exc}")
        return False


async def test_tool_routing(orchestrator):
    """Test tool routing without actual execution."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Tool Routing (Dry Run)")
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

        intent, tools = orchestrator._analyze_intent(query)

        if intent == expected and len(tools) > 0:
            logger.info(f"✓ Query: '{query}'")
            logger.info(f"  → Intent: {intent}")
            logger.info(f"  → Tools: {', '.join(t[:30] for t in tools[:3])}")
            passed += 1
        else:
            logger.error(f"❌ Query: '{query}'")
            logger.error(f"  Expected: {expected}, Got: {intent}")
            failed += 1

    logger.info(f"\nTool Routing: {passed} passed, {failed} failed")
    return failed == 0


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
    logger.info("SRE Orchestrator Test Suite")
    logger.info("=" * 60)

    all_passed = True

    # Test 1: Initialization
    orchestrator = await test_orchestrator_initialization()
    if not orchestrator:
        logger.error("\n❌ Cannot proceed - orchestrator initialization failed")
        sys.exit(1)

    # Test 2: Intent Analysis
    result = await test_intent_analysis(orchestrator)
    all_passed = all_passed and result

    # Test 3: Capabilities
    result = await test_capabilities(orchestrator)
    all_passed = all_passed and result

    # Test 4: Registry Stats
    result = await test_registry_stats()
    all_passed = all_passed and result

    # Test 5: Tool Routing
    result = await test_tool_routing(orchestrator)
    all_passed = all_passed and result

    # Test 6: Metrics
    result = await test_metrics(orchestrator)
    all_passed = all_passed and result

    # Cleanup
    await orchestrator.cleanup()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    if all_passed:
        logger.info("✅ All tests passed!")
        logger.info("\nNext steps:")
        logger.info("1. Register SRE tools: python scripts/register_sre_tools.py")
        logger.info("2. Test with real tools")
        logger.info("3. Create FastAPI endpoint")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        logger.info("\nPlease fix the issues before proceeding")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
