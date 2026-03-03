"""Integration tests for router integration with orchestrators — Task 3.

Tests:
- BaseOrchestrator exposes process_with_routing() and self.router
- process_with_routing() raises ValueError when router is None
- process_with_routing() works when router is set
- MCPOrchestratorAgent has _ensure_unified_router()
- MCPOrchestratorAgent wires router lazily via _ensure_unified_router()
- SREOrchestratorAgent has process_with_routing()
- SREOrchestratorAgent has _ensure_unified_router()
- SREOrchestratorAgent wires router lazily via _ensure_unified_router()
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.agents.base_orchestrator import BaseOrchestrator
    from app.agentic.eol.agents.orchestrator_models import ExecutionPlan, OrchestratorResult
    from app.agentic.eol.utils.unified_router import UnifiedRouter, RoutingPlan
    from app.agentic.eol.utils.domain_classifier import DomainClassifier, DomainLabel
    _AGENTS_PREFIX = "app.agentic.eol.agents"
except ModuleNotFoundError:
    from agents.base_orchestrator import BaseOrchestrator  # type: ignore[import-not-found]
    from agents.orchestrator_models import ExecutionPlan, OrchestratorResult  # type: ignore[import-not-found]
    from utils.unified_router import UnifiedRouter, RoutingPlan  # type: ignore[import-not-found]
    from utils.domain_classifier import DomainClassifier, DomainLabel  # type: ignore[import-not-found]
    _AGENTS_PREFIX = "agents"


# ============================================================================
# Concrete TestOrchestrator for BaseOrchestrator tests
# ============================================================================

class ConcreteOrchestrator(BaseOrchestrator):
    """Minimal concrete implementation for testing."""

    async def route_query(self, query: str, context: Dict) -> ExecutionPlan:
        return ExecutionPlan(
            strategy="react",
            domains=["general"],
            tools=[],
            steps=[],
        )

    async def execute_plan(self, plan: ExecutionPlan) -> OrchestratorResult:
        return OrchestratorResult(
            success=True,
            content="ok",
            formatted_response="<p>ok</p>",
        )


def _make_mock_router() -> MagicMock:
    """Build a mock UnifiedRouter that returns a basic RoutingPlan."""
    mock = MagicMock(spec=UnifiedRouter)
    mock.route = AsyncMock(return_value=RoutingPlan(
        orchestrator="mcp",
        domain=DomainLabel.COMPUTE,
        tools=["restart_vm"],
        confidence=0.8,
        strategy_used="fast",
        classification_time_ms=2.5,
    ))
    return mock


# ============================================================================
# BaseOrchestrator router integration
# ============================================================================

def test_base_orchestrator_has_router_attribute():
    """BaseOrchestrator must expose self.router as None by default."""
    orch = ConcreteOrchestrator()
    assert hasattr(orch, "router")
    assert orch.router is None


def test_base_orchestrator_has_process_with_routing():
    """BaseOrchestrator must have process_with_routing() method."""
    assert hasattr(BaseOrchestrator, "process_with_routing")
    assert callable(getattr(BaseOrchestrator, "process_with_routing"))


@pytest.mark.asyncio
async def test_process_with_routing_raises_when_router_none():
    """process_with_routing() must raise ValueError when router is not set."""
    orch = ConcreteOrchestrator()
    with pytest.raises(ValueError, match="UnifiedRouter not configured"):
        await orch.process_with_routing("check VM health")


@pytest.mark.asyncio
async def test_process_with_routing_works_when_router_set():
    """process_with_routing() must return RoutingPlan when router is set."""
    orch = ConcreteOrchestrator()
    orch.router = _make_mock_router()

    plan = await orch.process_with_routing("restart the VM", strategy="fast")
    assert isinstance(plan, RoutingPlan)
    assert plan.domain == DomainLabel.COMPUTE


@pytest.mark.asyncio
async def test_process_with_routing_passes_strategy():
    """process_with_routing() must forward the strategy argument to the router."""
    orch = ConcreteOrchestrator()
    orch.router = _make_mock_router()

    await orch.process_with_routing("check storage", strategy="quality")
    orch.router.route.assert_called_once()
    _, kwargs = orch.router.route.call_args
    assert kwargs.get("strategy") == "quality"


@pytest.mark.asyncio
async def test_process_with_routing_passes_context():
    """process_with_routing() must forward context dict to the router."""
    orch = ConcreteOrchestrator()
    orch.router = _make_mock_router()

    ctx = {"subscription_id": "sub-123"}
    await orch.process_with_routing("list VMs", context=ctx)
    orch.router.route.assert_called_once()
    _, kwargs = orch.router.route.call_args
    assert kwargs.get("context") == ctx


# ============================================================================
# MCPOrchestratorAgent router integration
# ============================================================================

def test_mcp_orchestrator_has_ensure_unified_router():
    """MCPOrchestratorAgent must have _ensure_unified_router() method."""
    try:
        from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
    except ModuleNotFoundError:
        from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore
    assert hasattr(MCPOrchestratorAgent, "_ensure_unified_router")


def test_mcp_orchestrator_has_unified_router_flag():
    """MCPOrchestratorAgent must track router initialization state."""
    try:
        from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
    except ModuleNotFoundError:
        from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore

    agent = MCPOrchestratorAgent()
    assert hasattr(agent, "_unified_router_initialized")
    assert agent._unified_router_initialized is False


def test_mcp_orchestrator_ensure_unified_router_wires_router():
    """_ensure_unified_router() must set self.router on the agent."""
    try:
        from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
    except ModuleNotFoundError:
        from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore

    agent = MCPOrchestratorAgent()
    mock_router = _make_mock_router()

    with patch("utils.unified_router.get_unified_router", return_value=mock_router):
        agent._ensure_unified_router()

    assert agent.router is not None
    assert agent._unified_router_initialized is True


def test_mcp_orchestrator_ensure_unified_router_idempotent():
    """_ensure_unified_router() must be safe to call multiple times."""
    try:
        from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
    except ModuleNotFoundError:
        from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore

    agent = MCPOrchestratorAgent()
    mock_router = _make_mock_router()

    # Directly set router and flag to simulate already-initialized state
    agent.router = mock_router
    agent._unified_router_initialized = True

    # Second call must be a no-op — router should remain the same object
    agent._ensure_unified_router()
    assert agent.router is mock_router


# ============================================================================
# SREOrchestratorAgent router integration (import-guarded)
# ============================================================================

def _import_sre_agent():
    """Try to import SREOrchestratorAgent — skip if mcp module unavailable."""
    try:
        try:
            from app.agentic.eol.agents.sre_orchestrator import SREOrchestratorAgent
        except ModuleNotFoundError:
            from agents.sre_orchestrator import SREOrchestratorAgent  # type: ignore
        return SREOrchestratorAgent
    except (ModuleNotFoundError, ImportError):
        return None


def test_sre_orchestrator_has_process_with_routing():
    """SREOrchestratorAgent must expose process_with_routing()."""
    SREOrchestratorAgent = _import_sre_agent()
    if SREOrchestratorAgent is None:
        pytest.skip("SREOrchestratorAgent requires mcp module (not installed in test env)")
    assert hasattr(SREOrchestratorAgent, "process_with_routing")


def test_sre_orchestrator_has_ensure_unified_router():
    """SREOrchestratorAgent must expose _ensure_unified_router()."""
    SREOrchestratorAgent = _import_sre_agent()
    if SREOrchestratorAgent is None:
        pytest.skip("SREOrchestratorAgent requires mcp module")
    assert hasattr(SREOrchestratorAgent, "_ensure_unified_router")
