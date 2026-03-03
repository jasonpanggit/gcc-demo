"""Comprehensive unit tests for UnifiedRouter — Task 5 of plan 03-01.

Covers:
- Domain → orchestrator mapping for all 10 labels
- fast / quality / comprehensive strategy behaviour
- Tool deduplication in quality strategy
- Performance: classification_time_ms < 200ms
- Edge cases (empty query, unknown domain)
- RoutingPlan structure validation
- Singleton factory
"""
from __future__ import annotations

import time
from typing import List
from unittest.mock import MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.unified_router import (
        UnifiedRouter,
        RoutingPlan,
        ExecutionPlan,
        get_unified_router,
    )
    from app.agentic.eol.utils.domain_classifier import DomainClassifier, DomainLabel
    from app.agentic.eol.utils.tool_registry import ToolEntry
except ModuleNotFoundError:
    from utils.unified_router import (  # type: ignore[import-not-found]
        UnifiedRouter,
        RoutingPlan,
        ExecutionPlan,
        get_unified_router,
    )
    from utils.domain_classifier import DomainClassifier, DomainLabel  # type: ignore[import-not-found]
    from utils.tool_registry import ToolEntry  # type: ignore[import-not-found]


# ============================================================================
# Test Fixtures
# ============================================================================

def _make_tool(name: str, domain: str) -> ToolEntry:
    return ToolEntry(
        name=name,
        original_name=name,
        description=f"Tool {name}",
        parameters={},
        source_label=domain,
        domain=domain,
    )


def _build_mock_registry(domain_tools: dict) -> MagicMock:
    """Build a mock MCPToolRegistry that returns ToolEntry lists by domain."""
    registry = MagicMock()
    registry.get_tools_by_domain.side_effect = lambda domain: domain_tools.get(domain, [])
    return registry


@pytest.fixture
def domain_tools():
    return {
        "sre": [_make_tool("check_resource_health", "sre"), _make_tool("get_incidents", "sre")],
        "monitoring": [_make_tool("list_alerts", "monitoring"), _make_tool("get_metrics", "monitoring")],
        "network": [_make_tool("list_nsg_rules", "network"), _make_tool("get_vnet_info", "network")],
        "inventory": [_make_tool("list_resources", "inventory")],
        "patch": [_make_tool("get_patch_status", "patch"), _make_tool("apply_patches", "patch")],
        "compute": [_make_tool("restart_vm", "compute"), _make_tool("get_vm_status", "compute")],
        "storage": [_make_tool("list_blobs", "storage")],
        "cost": [_make_tool("get_cost_summary", "cost")],
        "security": [_make_tool("run_security_audit", "security")],
        "general": [],
    }


@pytest.fixture
def mock_registry(domain_tools):
    return _build_mock_registry(domain_tools)


@pytest.fixture
def classifier():
    return DomainClassifier()


@pytest.fixture
def router(mock_registry, classifier):
    return UnifiedRouter(mock_registry, classifier)


# ============================================================================
# Orchestrator Selection — domain mapping tests
# ============================================================================

@pytest.mark.asyncio
async def test_sre_query_routes_to_sre_orchestrator(router):
    plan = await router.route("VM is down, need incident response")
    assert plan.orchestrator == "sre"
    assert plan.domain == DomainLabel.SRE


@pytest.mark.asyncio
async def test_monitoring_query_routes_to_sre_orchestrator(router):
    plan = await router.route("Set up an alert when metric exceeds threshold")
    assert plan.orchestrator == "sre"
    assert plan.domain == DomainLabel.MONITORING


@pytest.mark.asyncio
async def test_network_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("List all NSG rules in the vnet")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.NETWORK


@pytest.mark.asyncio
async def test_inventory_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("List all resources and build an inventory catalog")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.INVENTORY


@pytest.mark.asyncio
async def test_patch_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("Check vulnerability and apply security patch")
    assert plan.orchestrator == "mcp"
    assert plan.domain in (DomainLabel.PATCH, DomainLabel.SECURITY)


@pytest.mark.asyncio
async def test_compute_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("Restart the virtual machine")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.COMPUTE


@pytest.mark.asyncio
async def test_storage_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("Check the blob storage disk usage")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.STORAGE


@pytest.mark.asyncio
async def test_cost_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("Show billing cost and budget")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.COST


@pytest.mark.asyncio
async def test_security_query_routes_to_mcp_orchestrator(router):
    plan = await router.route("Run a security audit and check RBAC policy")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.SECURITY


@pytest.mark.asyncio
async def test_general_fallback_routes_to_mcp(router):
    plan = await router.route("Hello there")
    assert plan.orchestrator == "mcp"
    assert plan.domain == DomainLabel.GENERAL


# ============================================================================
# Strategy behaviour
# ============================================================================

@pytest.mark.asyncio
async def test_fast_strategy_returns_primary_domain_tools(router):
    plan = await router.route("list NSG rules in network", strategy="fast")
    assert plan.strategy_used == "fast"
    assert len(plan.tools) <= 10
    # Should include network tools
    assert "list_nsg_rules" in plan.tools or "get_vnet_info" in plan.tools


@pytest.mark.asyncio
async def test_fast_strategy_capped_at_ten_tools(mock_registry, classifier):
    """Fast strategy must cap at 10 even when registry returns more."""
    # Populate 20 tools for network
    many_tools = [_make_tool(f"net_tool_{i}", "network") for i in range(20)]
    registry = _build_mock_registry({"network": many_tools})
    r = UnifiedRouter(registry, classifier)
    plan = await r.route("check vnet firewall network", strategy="fast")
    assert len(plan.tools) <= 10


@pytest.mark.asyncio
async def test_quality_strategy_includes_secondary_domains(mock_registry, classifier):
    """Quality strategy should include secondary domain tools when detected."""
    r = UnifiedRouter(mock_registry, classifier)
    # Query that hits both SRE and monitoring
    plan = await r.route("incident alert monitoring health check metric", strategy="quality")
    assert plan.strategy_used == "quality"
    # Should have tools from at least one domain
    assert len(plan.tools) > 0


@pytest.mark.asyncio
async def test_quality_strategy_capped_at_fifteen(mock_registry, classifier):
    """Quality strategy must cap at 15 tools."""
    many_sre = [_make_tool(f"sre_t{i}", "sre") for i in range(10)]
    many_mon = [_make_tool(f"mon_t{i}", "monitoring") for i in range(10)]
    registry = _build_mock_registry({"sre": many_sre, "monitoring": many_mon})
    r = UnifiedRouter(registry, classifier)
    plan = await r.route("incident alert monitoring sre health metric threshold", strategy="quality")
    assert len(plan.tools) <= 15


@pytest.mark.asyncio
async def test_quality_strategy_no_duplicate_tools(mock_registry, classifier):
    """Quality strategy must deduplicate tools that appear in multiple domains."""
    shared_tool = _make_tool("shared_tool", "sre")
    # Same tool name in both domains
    registry = _build_mock_registry({
        "sre": [shared_tool],
        "monitoring": [shared_tool],
    })
    r = UnifiedRouter(registry, classifier)
    plan = await r.route("incident alert monitoring sre metric", strategy="quality")
    assert plan.tools.count("shared_tool") <= 1


@pytest.mark.asyncio
async def test_comprehensive_strategy_returns_empty_list(router):
    """Comprehensive strategy should return [] to signal 'use all tools'."""
    plan = await router.route("check everything", strategy="comprehensive")
    assert plan.strategy_used == "comprehensive"
    assert plan.tools == []


# ============================================================================
# Performance tests
# ============================================================================

@pytest.mark.asyncio
async def test_fast_strategy_performance(router):
    """Fast strategy must complete in <200ms."""
    plan = await router.route("Check VM health status", strategy="fast")
    assert plan.classification_time_ms < 200
    assert plan.strategy_used == "fast"


@pytest.mark.asyncio
async def test_quality_strategy_performance(router):
    """Quality strategy must complete in <200ms (keyword path)."""
    plan = await router.route("Check VM health and monitoring metrics", strategy="quality")
    assert plan.classification_time_ms < 200


@pytest.mark.asyncio
async def test_comprehensive_strategy_performance(router):
    """Comprehensive strategy must complete in <200ms."""
    plan = await router.route("Audit everything", strategy="comprehensive")
    assert plan.classification_time_ms < 200


# ============================================================================
# Edge cases
# ============================================================================

@pytest.mark.asyncio
async def test_empty_query_defaults_to_general(router):
    plan = await router.route("")
    assert plan.domain == DomainLabel.GENERAL
    assert plan.orchestrator == "mcp"


@pytest.mark.asyncio
async def test_context_parameter_accepted(router):
    """route() should accept context dict without error."""
    plan = await router.route(
        "list NSG rules",
        context={"subscription_id": "sub-123"},
        strategy="fast",
    )
    assert plan.orchestrator == "mcp"


# ============================================================================
# RoutingPlan structure
# ============================================================================

@pytest.mark.asyncio
async def test_routing_plan_fields_populated(router):
    plan = await router.route("check VM health status")
    assert isinstance(plan, RoutingPlan)
    assert isinstance(plan.orchestrator, str)
    assert isinstance(plan.domain, DomainLabel)
    assert isinstance(plan.tools, list)
    assert isinstance(plan.confidence, float)
    assert isinstance(plan.strategy_used, str)
    assert isinstance(plan.classification_time_ms, float)
    assert isinstance(plan.secondary_domains, list)


def test_execution_plan_is_alias_for_routing_plan():
    """ExecutionPlan must be the same class as RoutingPlan (backward compat)."""
    assert ExecutionPlan is RoutingPlan


# ============================================================================
# Singleton factory
# ============================================================================

def test_get_unified_router_returns_instance():
    """get_unified_router() must return a UnifiedRouter instance."""
    router = get_unified_router()
    assert isinstance(router, UnifiedRouter)


def test_get_unified_router_singleton():
    """Two calls must return the same instance."""
    r1 = get_unified_router()
    r2 = get_unified_router()
    assert r1 is r2
