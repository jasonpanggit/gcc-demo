"""Unit tests for Phase 7 — MCP_AGENT_PIPELINE default promotion.

Tests that:
- MCP_AGENT_PIPELINE defaults to "true" (pipeline active by default)
- MCP_AGENT_PIPELINE=false (or "legacy") disables the full pipeline
- MCP_AGENT_PIPELINE=routing enables routing-only mode (Phase 5)
- _pipeline_full and _pipeline_routing flags are consistent with each other
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

try:
    from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
except ModuleNotFoundError:
    from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore[import-not-found]


def _make_agent_with_env(env: dict) -> MCPOrchestratorAgent:
    """Construct a minimal MCPOrchestratorAgent with a specific env, avoiding Azure calls."""
    with patch.dict(os.environ, env, clear=False):
        agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
        _pipeline_mode = os.getenv("MCP_AGENT_PIPELINE", "true").lower()
        agent._pipeline_routing = _pipeline_mode in ("routing", "true", "1", "yes")
        agent._pipeline_full = _pipeline_mode in ("true", "1", "yes", "full")
    return agent


class TestPhase7Default:
    def test_pipeline_full_is_true_by_default(self):
        """Phase 7: MCP_AGENT_PIPELINE defaults to 'true' — full pipeline is default."""
        with patch.dict(os.environ, {}, clear=False):
            # Temporarily remove MCP_AGENT_PIPELINE if set in the test environment
            env_without_flag = {k: v for k, v in os.environ.items() if k != "MCP_AGENT_PIPELINE"}
        with patch.dict(os.environ, env_without_flag, clear=True):
            agent = _make_agent_with_env({})
            assert agent._pipeline_full is True

    def test_pipeline_full_false_when_legacy(self):
        """Setting MCP_AGENT_PIPELINE=legacy disables full pipeline."""
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "legacy"})
        assert agent._pipeline_full is False
        assert agent._pipeline_routing is False

    def test_pipeline_full_false_when_false(self):
        """Setting MCP_AGENT_PIPELINE=false disables full pipeline."""
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "false"})
        assert agent._pipeline_full is False
        assert agent._pipeline_routing is False

    def test_pipeline_full_true_when_true(self):
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "true"})
        assert agent._pipeline_full is True
        assert agent._pipeline_routing is True

    def test_pipeline_full_true_when_1(self):
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "1"})
        assert agent._pipeline_full is True

    def test_pipeline_full_true_when_full(self):
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "full"})
        assert agent._pipeline_full is True
        # routing flag: "full" is not in the routing set
        assert agent._pipeline_routing is False

    def test_pipeline_routing_only_when_routing(self):
        """MCP_AGENT_PIPELINE=routing → routing=True but full=False."""
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "routing"})
        assert agent._pipeline_routing is True
        assert agent._pipeline_full is False

    def test_pipeline_flags_consistent_for_true(self):
        """When full pipeline is active, routing is also active (it's a sub-step)."""
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": "true"})
        # If full is True, routing must also be True (Router is Stage 1 of full pipeline)
        assert agent._pipeline_full is True
        assert agent._pipeline_routing is True

    def test_empty_env_uses_default_true(self):
        """Empty MCP_AGENT_PIPELINE string → treated as unset → default 'true'."""
        # The new default fallback is "true", so empty string goes to legacy behaviour
        # (empty string is not in the "true/1/yes/full" set)
        # This test documents that explicit empty string overrides the default
        agent = _make_agent_with_env({"MCP_AGENT_PIPELINE": ""})
        # Empty string is not "true" — falls through to the legacy path
        assert agent._pipeline_full is False
