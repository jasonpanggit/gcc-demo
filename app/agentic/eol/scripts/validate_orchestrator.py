#!/usr/bin/env python3
"""Quick validation test for SRE orchestrator components.

Tests core functionality without external dependencies.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all components can be imported."""
    print("=" * 60)
    print("TEST: Component Imports")
    print("=" * 60)

    components = [
        ("Base SRE Agent", "agents.base_sre_agent", "BaseSREAgent"),
        ("Agent Registry", "utils.agent_registry", "AgentRegistry"),
        ("Context Store", "utils.agent_context_store", "AgentContextStore"),
        ("Message Bus", "utils.agent_message_bus", "AgentMessageBus"),
        ("Orchestrator", "agents.sre_orchestrator_agent", "SREOrchestratorAgent"),
    ]

    passed = 0
    failed = 0

    for name, module, cls in components:
        try:
            mod = __import__(module, fromlist=[cls])
            getattr(mod, cls)
            print(f"✓ {name}: {module}.{cls}")
            passed += 1
        except Exception as exc:
            print(f"❌ {name}: {exc}")
            failed += 1

    print(f"\nImports: {passed} passed, {failed} failed")
    return failed == 0


async def test_base_agent():
    """Test base agent functionality."""
    print("\n" + "=" * 60)
    print("TEST: Base SRE Agent")
    print("=" * 60)

    try:
        from agents.base_sre_agent import BaseSREAgent

        # Create a simple test agent
        class TestAgent(BaseSREAgent):
            async def execute(self, request, context=None):
                return {"status": "success", "message": "test"}

        agent = TestAgent(agent_type="test", agent_id="test-001")

        # Test initialization
        await agent.initialize()
        print(f"✓ Agent initialized: {agent.agent_id}")

        # Test request handling
        result = await agent.handle_request({"test": "data"})
        print(f"✓ Request handled: status={result['status']}")

        # Test metrics
        metrics = agent.get_metrics()
        print(f"✓ Metrics: {metrics['requests_handled']} requests")

        # Cleanup
        await agent.cleanup()
        print("✓ Agent cleaned up")

        return True

    except Exception as exc:
        print(f"❌ Base agent test failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


async def test_registry():
    """Test agent registry."""
    print("\n" + "=" * 60)
    print("TEST: Agent Registry")
    print("=" * 60)

    try:
        from utils.agent_registry import get_agent_registry, AgentRegistry
        from agents.base_sre_agent import BaseSREAgent

        # Get registry
        registry = get_agent_registry()
        print("✓ Registry instance created")

        # Create a test agent
        class TestAgent(BaseSREAgent):
            async def execute(self, request, context=None):
                return {"status": "success"}

        agent = TestAgent(agent_type="test", agent_id="test-registry")
        await agent.initialize()

        # Register agent
        await registry.register_agent(agent, metadata={"test": True})
        print(f"✓ Agent registered: {agent.agent_id}")

        # Register a test tool
        await registry.register_tool(
            "test_tool",
            agent.agent_id,
            {
                "function": {
                    "name": "test_tool",
                    "description": "Test tool"
                }
            }
        )
        print("✓ Tool registered")

        # List agents
        agents = registry.list_agents()
        print(f"✓ Agents listed: {len(agents)} agent(s)")

        # List tools
        tools = registry.list_tools()
        print(f"✓ Tools listed: {len(tools)} tool(s)")

        # Get stats
        stats = registry.get_registry_stats()
        print(f"✓ Stats: {stats['total_agents']} agents, {stats['total_tools']} tools")

        await agent.cleanup()
        return True

    except Exception as exc:
        print(f"❌ Registry test failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_basic():
    """Test basic orchestrator functionality."""
    print("\n" + "=" * 60)
    print("TEST: SRE Orchestrator (Basic)")
    print("=" * 60)

    try:
        from agents.sre_orchestrator_agent import SREOrchestratorAgent

        # Create orchestrator
        orchestrator = SREOrchestratorAgent()
        print(f"✓ Orchestrator created: {orchestrator.agent_id}")

        # Test intent analysis
        intent, tools = orchestrator._analyze_intent("check health of container apps")
        print(f"✓ Intent analysis: {intent} → {len(tools)} tools")

        # Test capabilities
        capabilities = orchestrator.get_capabilities()
        print(f"✓ Capabilities: {len(capabilities['categories'])} categories")

        # Test metrics
        metrics = orchestrator.get_metrics()
        print(f"✓ Metrics: {metrics['agent_type']}")

        return True

    except Exception as exc:
        print(f"❌ Orchestrator test failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("SRE Orchestrator Validation Suite")
    print("=" * 60)
    print()

    results = []

    # Test 1: Imports
    results.append(("Imports", test_imports()))

    # Test 2: Base Agent
    results.append(("Base Agent", await test_base_agent()))

    # Test 3: Registry
    results.append(("Registry", await test_registry()))

    # Test 4: Orchestrator
    results.append(("Orchestrator", await test_orchestrator_basic()))

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All validation tests passed!")
        print("\nThe SRE Orchestrator is ready to use!")
        print("\nNext steps:")
        print("1. Activate venv: source .venv/bin/activate")
        print("2. Register tools: python scripts/register_sre_tools.py")
        print("3. Run full tests with real SRE tools")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
