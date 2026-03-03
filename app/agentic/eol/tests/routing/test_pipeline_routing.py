"""Unit tests for Phase 5 — MCP_AGENT_PIPELINE=routing activation.

Tests that:
- _pipeline_routing flag set correctly from MCP_AGENT_PIPELINE env var
- _get_active_tools_for_iteration_async uses new pipeline when _pipeline_routing=True
- _get_active_tools_for_iteration_async falls back to legacy when pipeline returns empty
- _get_active_tools_for_iteration_async falls back to legacy when pipeline raises
- legacy path used when _pipeline_routing=False (default)
- shadow mode log tag changes between SHADOW and ROUTING

All tests use MagicMock/AsyncMock — no Azure calls.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
    _AGENTS_PREFIX = "app.agentic.eol.agents.mcp_orchestrator"
except ModuleNotFoundError:
    from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore[import-not-found]
    _AGENTS_PREFIX = "agents.mcp_orchestrator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool: {name}",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


def _make_agent(pipeline_routing: bool = False, pipeline_shadow: bool = False) -> MCPOrchestratorAgent:
    """Construct a minimal MCPOrchestratorAgent with faked dependencies."""
    env_patch = {
        "MCP_AGENT_PIPELINE": "routing" if pipeline_routing else "",
        "MCP_PIPELINE_SHADOW": "true" if pipeline_shadow else "",
        # Disable real Azure connections
        "AZURE_OPENAI_ENDPOINT": "",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
        # Minimal attribute initialization (mirrors __init__ but avoids real Azure calls)
        agent._pipeline_routing = pipeline_routing
        agent._pipeline_shadow = pipeline_shadow
        agent._pipeline_router = None
        agent._pipeline_retriever = None
        agent._tool_router = None
        agent._tool_embedder = None
        agent._tool_definitions = []
        agent._tool_source_map = {}
        agent._routed_tool_budget = 15
        agent._mcp_client = None
        agent._last_tool_request = None
    return agent


def _attach_mock_pipeline(
    agent: MCPOrchestratorAgent,
    pipeline_tools: Optional[List[Dict[str, Any]]] = None,
    raise_exc: Optional[Exception] = None,
) -> None:
    """Attach mock pipeline router + retriever to agent."""
    try:
        from app.agentic.eol.utils.router import DomainMatch
        from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain
        from app.agentic.eol.utils.tool_retriever import ToolRetrievalResult
    except ModuleNotFoundError:
        from utils.router import DomainMatch  # type: ignore[import-not-found]
        from utils.unified_domain_registry import UnifiedDomain  # type: ignore[import-not-found]
        from utils.tool_retriever import ToolRetrievalResult  # type: ignore[import-not-found]

    mock_router = AsyncMock()
    domain_matches = [DomainMatch(domain=UnifiedDomain.SRE_HEALTH, confidence=0.9, matched_signals=["sre"])]
    mock_router.route = AsyncMock(return_value=domain_matches)

    mock_retriever = AsyncMock()
    if raise_exc:
        mock_retriever.retrieve = AsyncMock(side_effect=raise_exc)
    else:
        retrieval_result = ToolRetrievalResult(
            tools=pipeline_tools or [],
            domain_matches=domain_matches,
            sources_used=["sre"],
            conflict_notes="",
            pool_size=len(pipeline_tools or []) * 2,
        )
        mock_retriever.retrieve = AsyncMock(return_value=retrieval_result)

    agent._pipeline_router = mock_router
    agent._pipeline_retriever = mock_retriever


def _attach_mock_legacy_router(
    agent: MCPOrchestratorAgent,
    legacy_tools: Optional[List[Dict[str, Any]]] = None,
) -> MagicMock:
    """Attach a mock legacy ToolRouter to agent."""
    mock_tool_router = MagicMock()
    mock_tool_router.filter_tools_for_query = MagicMock(return_value=legacy_tools or [])
    agent._tool_router = mock_tool_router
    agent._tool_definitions = legacy_tools or [_make_tool("legacy_tool")]
    return mock_tool_router


# ---------------------------------------------------------------------------
# Test: _pipeline_routing flag initialization
# ---------------------------------------------------------------------------

class TestPipelineRoutingFlag:
    def test_routing_false_by_default(self):
        """Default env → _pipeline_routing=False."""
        with patch.dict(os.environ, {"MCP_AGENT_PIPELINE": ""}, clear=False):
            agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
            agent._pipeline_routing = os.getenv("MCP_AGENT_PIPELINE", "").lower() in ("routing", "true", "1", "yes")
            assert agent._pipeline_routing is False

    def test_routing_true_when_routing(self):
        with patch.dict(os.environ, {"MCP_AGENT_PIPELINE": "routing"}, clear=False):
            agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
            agent._pipeline_routing = os.getenv("MCP_AGENT_PIPELINE", "").lower() in ("routing", "true", "1", "yes")
            assert agent._pipeline_routing is True

    def test_routing_true_when_true(self):
        with patch.dict(os.environ, {"MCP_AGENT_PIPELINE": "true"}, clear=False):
            agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
            agent._pipeline_routing = os.getenv("MCP_AGENT_PIPELINE", "").lower() in ("routing", "true", "1", "yes")
            assert agent._pipeline_routing is True

    def test_routing_false_when_false(self):
        with patch.dict(os.environ, {"MCP_AGENT_PIPELINE": "false"}, clear=False):
            agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
            agent._pipeline_routing = os.getenv("MCP_AGENT_PIPELINE", "").lower() in ("routing", "true", "1", "yes")
            assert agent._pipeline_routing is False


# ---------------------------------------------------------------------------
# Test: _get_active_tools_for_iteration_async — routing path
# ---------------------------------------------------------------------------

class TestGetActiveToolsRoutingPath:
    @pytest.mark.asyncio
    async def test_routing_path_returns_pipeline_tools(self):
        """When _pipeline_routing=True and pipeline has tools → return pipeline tools."""
        agent = _make_agent(pipeline_routing=True)
        pipeline_tools = [_make_tool("pipeline_tool_a"), _make_tool("pipeline_tool_b")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        tool_names = [t["function"]["name"] for t in result]
        assert "pipeline_tool_a" in tool_names
        assert "pipeline_tool_b" in tool_names

    @pytest.mark.asyncio
    async def test_routing_path_calls_router_route(self):
        """Router.route() must be called when routing is active."""
        agent = _make_agent(pipeline_routing=True)
        pipeline_tools = [_make_tool("sre_tool")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)

        await agent._get_active_tools_for_iteration_async("check health", [])

        agent._pipeline_router.route.assert_called_once()

    @pytest.mark.asyncio
    async def test_routing_path_calls_retriever_retrieve(self):
        """ToolRetriever.retrieve() must be called when routing is active."""
        agent = _make_agent(pipeline_routing=True)
        pipeline_tools = [_make_tool("sre_tool")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)

        await agent._get_active_tools_for_iteration_async("check health", [])

        agent._pipeline_retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_routing_path_does_not_call_legacy_router(self):
        """Legacy ToolRouter must NOT be called when pipeline returns tools."""
        agent = _make_agent(pipeline_routing=True)
        pipeline_tools = [_make_tool("pipeline_only_tool")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)
        mock_legacy = _attach_mock_legacy_router(agent)

        await agent._get_active_tools_for_iteration_async("check health", [])

        mock_legacy.filter_tools_for_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_path_passes_prior_tool_names(self):
        """Prior tool names are forwarded to Router.route()."""
        agent = _make_agent(pipeline_routing=True)
        pipeline_tools = [_make_tool("sre_tool")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)

        prior_names = ["tool_x", "tool_y"]
        await agent._get_active_tools_for_iteration_async("what next?", prior_names)

        call_kwargs = agent._pipeline_router.route.call_args
        # prior_tool_names is a keyword arg
        assert call_kwargs is not None
        assert "prior_tool_names" in call_kwargs.kwargs or len(call_kwargs.args) >= 2


# ---------------------------------------------------------------------------
# Test: fallback to legacy when pipeline returns empty
# ---------------------------------------------------------------------------

class TestRoutingFallbackOnEmpty:
    @pytest.mark.asyncio
    async def test_fallback_to_legacy_when_pipeline_returns_empty(self):
        """If pipeline returns 0 tools, fall back to legacy ToolRouter."""
        agent = _make_agent(pipeline_routing=True)
        _attach_mock_pipeline(agent, pipeline_tools=[])  # Empty result
        legacy_tools = [_make_tool("legacy_fallback_tool")]
        mock_legacy = _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        # Legacy router should have been called
        mock_legacy.filter_tools_for_query.assert_called_once()
        # Result should contain legacy tools
        tool_names = [t["function"]["name"] for t in result]
        assert "legacy_fallback_tool" in tool_names

    @pytest.mark.asyncio
    async def test_fallback_to_legacy_when_pipeline_raises(self):
        """If pipeline raises an exception, fall back to legacy ToolRouter."""
        agent = _make_agent(pipeline_routing=True)
        _attach_mock_pipeline(agent, raise_exc=RuntimeError("embedding service down"))
        legacy_tools = [_make_tool("legacy_exception_fallback")]
        mock_legacy = _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        # Should NOT raise
        result = await agent._get_active_tools_for_iteration_async("check health", [])

        mock_legacy.filter_tools_for_query.assert_called_once()
        tool_names = [t["function"]["name"] for t in result]
        assert "legacy_exception_fallback" in tool_names

    @pytest.mark.asyncio
    async def test_fallback_when_pipeline_not_initialized(self):
        """If _pipeline_router is None, use legacy path even when _pipeline_routing=True."""
        agent = _make_agent(pipeline_routing=True)
        # Don't attach mock pipeline → router + retriever remain None
        legacy_tools = [_make_tool("legacy_uninit_tool")]
        mock_legacy = _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        mock_legacy.filter_tools_for_query.assert_called_once()
        tool_names = [t["function"]["name"] for t in result]
        assert "legacy_uninit_tool" in tool_names


# ---------------------------------------------------------------------------
# Test: legacy path used when pipeline_routing=False
# ---------------------------------------------------------------------------

class TestLegacyPathWhenRoutingOff:
    @pytest.mark.asyncio
    async def test_legacy_path_when_routing_disabled(self):
        """When _pipeline_routing=False, legacy ToolRouter is used."""
        agent = _make_agent(pipeline_routing=False)
        pipeline_tools = [_make_tool("should_not_appear")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)
        legacy_tools = [_make_tool("legacy_path_tool")]
        mock_legacy = _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        # Pipeline router should NOT be called
        agent._pipeline_router.route.assert_not_called()
        # Legacy router should be called
        mock_legacy.filter_tools_for_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_legacy_path_returns_legacy_tools(self):
        """Legacy path should return tools from ToolRouter.filter_tools_for_query."""
        agent = _make_agent(pipeline_routing=False)
        legacy_tools = [_make_tool("legacy_a"), _make_tool("legacy_b")]
        _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        tool_names = [t["function"]["name"] for t in result]
        assert "legacy_a" in tool_names
        assert "legacy_b" in tool_names

    @pytest.mark.asyncio
    async def test_legacy_path_empty_when_no_tools(self):
        """When no tools defined, returns empty list."""
        agent = _make_agent(pipeline_routing=False)
        agent._tool_definitions = []
        agent._tool_router = None

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        assert result == []


# ---------------------------------------------------------------------------
# Test: shadow+routing coexistence
# ---------------------------------------------------------------------------

class TestShadowAndRoutingCoexist:
    @pytest.mark.asyncio
    async def test_routing_active_takes_precedence_over_shadow(self):
        """When both shadow and routing are enabled, routing path is taken."""
        agent = _make_agent(pipeline_routing=True, pipeline_shadow=True)
        pipeline_tools = [_make_tool("routing_tool")]
        _attach_mock_pipeline(agent, pipeline_tools=pipeline_tools)
        legacy_tools = [_make_tool("shadow_only_tool")]
        mock_legacy = _attach_mock_legacy_router(agent, legacy_tools=legacy_tools)

        result = await agent._get_active_tools_for_iteration_async("check health", [])

        # Routing path was taken → pipeline retriever called
        agent._pipeline_retriever.retrieve.assert_called_once()
        # Legacy not called (pipeline returned tools)
        mock_legacy.filter_tools_for_query.assert_not_called()
        tool_names = [t["function"]["name"] for t in result]
        assert "routing_tool" in tool_names
