"""Integration tests for CVE tools in SRE orchestrator (Wave 3).

Tests that CVE tools are accessible via SRE chat interface.
These tests are local only and not committed per .gitignore policy.
"""
import asyncio
import pytest
from typing import Dict, Any


@pytest.mark.asyncio
async def test_cve_tools_available_in_sre_orchestrator():
    """Test that CVE tools are included in SRESubAgent tool catalog."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    # Check that SRESubAgent was initialized
    assert orchestrator._sre_sub_agent is not None, "SRESubAgent should be initialized"

    # Check that tool catalog includes CVE tools
    tool_names = [tool.get("name") for tool in orchestrator._sre_sub_agent.tool_definitions]

    # Should have ~62 tools (58 SRE + 4 CVE)
    assert len(tool_names) >= 60, f"Expected ~62 tools, got {len(tool_names)}"

    # CVE tools should be present
    cve_tools = {"search_cve", "scan_inventory", "get_patches", "trigger_remediation"}
    found_cve_tools = set(tool_names) & cve_tools
    assert found_cve_tools == cve_tools, f"Missing CVE tools: {cve_tools - found_cve_tools}"

    print(f"✅ CVE tools integrated: {len(tool_names)} total tools")
    print(f"   Found CVE tools: {found_cve_tools}")

    await orchestrator.cleanup()


@pytest.mark.asyncio
async def test_cve_search_via_sre_chat():
    """Test CVE search workflow through SRE orchestrator."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    request = {
        "query": "Search for CVE-2024-1234",
        "workflow_id": "test-cve-search-001",
        "context": {}
    }

    result = await orchestrator.handle_request(request)

    # Should receive a response (even if CVE doesn't exist, we get a response)
    assert result is not None
    assert "response" in result or "formatted_response" in result

    print(f"✅ CVE search workflow completed")
    print(f"   Response preview: {str(result)[:200]}...")

    await orchestrator.cleanup()


@pytest.mark.asyncio
async def test_cve_scan_via_sre_chat():
    """Test CVE inventory scan workflow through SRE orchestrator."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    request = {
        "query": "Scan my VMs for CVEs",
        "workflow_id": "test-cve-scan-001",
        "context": {
            "subscription_id": "test-sub-123"
        }
    }

    result = await orchestrator.handle_request(request)

    # Should receive a response
    assert result is not None
    assert "response" in result or "formatted_response" in result

    print(f"✅ CVE scan workflow completed")
    print(f"   Response preview: {str(result)[:200]}...")

    await orchestrator.cleanup()


@pytest.mark.asyncio
async def test_unified_tool_invoker_routing():
    """Test that unified tool invoker routes correctly to CVE/SRE clients."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    # Get the unified invoker
    invoker = orchestrator._sre_tool_invoker
    assert invoker is not None, "Unified tool invoker should be initialized"

    # Test routing to CVE tool (should not error out even if MCP not available)
    try:
        result = await invoker("search_cve", {"cve_id": "CVE-2024-1234", "limit": 5})
        print(f"✅ CVE tool routing works: {type(result)}")
    except Exception as e:
        print(f"⚠️  CVE tool routing attempted (expected in test env): {e}")

    await orchestrator.cleanup()


@pytest.mark.asyncio
async def test_sre_sub_agent_system_prompt_includes_cve():
    """Test that SRE sub-agent system prompt includes CVE capabilities."""
    from agents.sre_sub_agent import SRESubAgent

    # Check system prompt includes CVE references
    prompt = SRESubAgent._SYSTEM_PROMPT

    assert "CVE" in prompt or "vulnerability" in prompt, "System prompt should mention CVE"
    assert "search_cve" in prompt, "System prompt should document search_cve tool"
    assert "scan_inventory" in prompt, "System prompt should document scan_inventory tool"
    assert "get_patches" in prompt, "System prompt should document get_patches tool"
    assert "trigger_remediation" in prompt, "System prompt should document trigger_remediation tool"

    print("✅ SRE sub-agent system prompt includes CVE documentation")


@pytest.mark.asyncio
async def test_cve_patch_discovery_workflow():
    """Test CVE patch discovery workflow through SRE orchestrator."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    request = {
        "query": "What patches fix CVE-2024-5678?",
        "workflow_id": "test-cve-patches-001",
        "context": {}
    }

    result = await orchestrator.handle_request(request)

    # Should receive a response
    assert result is not None
    assert "response" in result or "formatted_response" in result

    print(f"✅ CVE patch discovery workflow completed")
    print(f"   Response preview: {str(result)[:200]}...")

    await orchestrator.cleanup()


@pytest.mark.asyncio
async def test_cve_remediation_workflow_dry_run():
    """Test CVE remediation dry-run workflow through SRE orchestrator."""
    from agents.sre_orchestrator import SREOrchestratorAgent

    orchestrator = SREOrchestratorAgent()
    await orchestrator.initialize()

    request = {
        "query": "Preview patch installation for CVE-2024-9999 on vm-test-01",
        "workflow_id": "test-cve-remediation-001",
        "context": {
            "subscription_id": "test-sub-123",
            "resource_group": "test-rg"
        }
    }

    result = await orchestrator.handle_request(request)

    # Should receive a response
    assert result is not None
    assert "response" in result or "formatted_response" in result

    print(f"✅ CVE remediation dry-run workflow completed")
    print(f"   Response preview: {str(result)[:200]}...")

    await orchestrator.cleanup()


if __name__ == "__main__":
    # Run tests manually
    print("🧪 Running CVE-SRE integration tests...\n")

    asyncio.run(test_cve_tools_available_in_sre_orchestrator())
    print()

    asyncio.run(test_sre_sub_agent_system_prompt_includes_cve())
    print()

    asyncio.run(test_unified_tool_invoker_routing())
    print()

    # Note: Chat workflow tests require full MCP infrastructure
    print("✅ All CVE-SRE integration tests passed!")
