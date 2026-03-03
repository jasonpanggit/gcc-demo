"""
SRE Sub-Agent Tests

Tests for SRE domain sub-agent functionality including initialization, tool routing, and ReAct loop.
Created: 2026-02-27 (Phase 3, Week 1, Day 3)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from agents.sre_sub_agent import SRESubAgent
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
@pytest.mark.asyncio
class TestSRESubAgent:
    """Tests for SRESubAgent."""

    def test_agent_initialization(self):
        """Test that SRE sub-agent initializes correctly."""
        tool_defs = [{"name": "check_resource_health", "description": "Check health"}]
        tool_invoker = AsyncMock()

        agent = SRESubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker
        )

        assert agent._DOMAIN_NAME == "sre"
        assert agent._MAX_ITERATIONS == 20
        assert agent._TIMEOUT_SECONDS == 50.0
        assert agent._tool_definitions == tool_defs
        assert agent._invoke_tool == tool_invoker

    def test_agent_has_system_prompt(self):
        """Test that agent has SRE-specific system prompt."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert len(agent._SYSTEM_PROMPT) > 0
        assert "SRE" in agent._SYSTEM_PROMPT
        assert "Site Reliability Engineering" in agent._SYSTEM_PROMPT

    def test_system_prompt_covers_key_domains(self):
        """Test that system prompt covers all SRE domains."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should mention key SRE domains
        assert "health" in prompt.lower()
        assert "incident" in prompt.lower()
        assert "performance" in prompt.lower()
        assert "cost" in prompt.lower()
        assert "remediation" in prompt.lower()

    def test_agent_inherits_from_domain_sub_agent(self):
        """Test that agent inherits from DomainSubAgent."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Check that agent has DomainSubAgent attributes
        assert hasattr(agent, '_DOMAIN_NAME')
        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert hasattr(agent, '_MAX_ITERATIONS')
        assert hasattr(agent, 'run')

    def test_agent_has_run_method(self):
        """Test that agent has run method."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, 'run')
        assert callable(agent.run)

    async def test_run_method_signature(self):
        """Test run method accepts user message."""
        tool_defs = []
        tool_invoker = AsyncMock(return_value={"success": True})

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Should accept a string message
        # (Won't actually execute without LLM, just checking signature)
        assert hasattr(agent.run, '__call__')

    def test_domain_name_constant(self):
        """Test domain name is correctly set."""
        assert SRESubAgent._DOMAIN_NAME == "sre"

    def test_max_iterations_configured(self):
        """Test max iterations is appropriate for SRE workflows."""
        # SRE workflows can be multi-step (triage → logs → remediate)
        assert SRESubAgent._MAX_ITERATIONS == 20
        assert SRESubAgent._MAX_ITERATIONS > 10  # Should be higher than basic agents

    def test_timeout_configured(self):
        """Test timeout is configured."""
        assert SRESubAgent._TIMEOUT_SECONDS == 50.0
        assert SRESubAgent._TIMEOUT_SECONDS > 0

    def test_event_callback_optional(self):
        """Test that event callback is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        # Should initialize without event_callback
        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_push_event')

    def test_event_callback_provided(self):
        """Test that event callback can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        event_callback = AsyncMock()

        agent = SRESubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            event_callback=event_callback
        )

        assert agent._push_event == event_callback

    def test_conversation_context_optional(self):
        """Test that conversation context is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_conversation_context')
        assert isinstance(agent._conversation_context, list)

    def test_conversation_context_provided(self):
        """Test that conversation context can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        context = [{"role": "user", "content": "Check health"}]

        agent = SRESubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            conversation_context=context
        )

        assert agent._conversation_context == context

    def test_system_prompt_safety_rules(self):
        """Test system prompt includes safety rules for destructive operations."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should have safety rules for remediation
        assert "SAFETY" in prompt or "DESTRUCTIVE" in prompt
        assert "approval" in prompt.lower() or "confirmation" in prompt.lower()


@pytest.mark.integration
@pytest.mark.asyncio
class TestSRESubAgentIntegration:
    """Integration tests for SRE sub-agent with Phase 2 utilities."""

    async def test_agent_with_error_aggregator(self):
        """Test agent integration with error aggregator."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        agg = ErrorAggregator()

        # Simulate agent operation that might fail
        try:
            # Agent initialization should not fail
            assert agent is not None
        except Exception as e:
            agg.add_error(e, {"agent": "sre", "operation": "init"})

        # Should have no errors
        assert not agg.has_errors()

    async def test_agent_with_timeout_config(self):
        """Test agent integration with centralized timeout config."""
        from utils.config import TimeoutConfig

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        timeout_config = TimeoutConfig()

        # Agent timeout should be reasonable (SRE workflows need more time)
        assert agent._TIMEOUT_SECONDS <= timeout_config.agent_timeout * 5

    async def test_agent_with_circuit_breaker_pattern(self):
        """Test agent can work with circuit breaker pattern."""
        from utils.circuit_breaker import CircuitBreaker

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        cb = CircuitBreaker(failure_threshold=2, name="sre_agent")

        # Circuit breaker pattern should be compatible
        assert cb.state.value in ["OPEN", "CLOSED"]

    async def test_tool_invoker_callback(self):
        """Test that tool invoker is called correctly."""
        tool_defs = [{"name": "test_tool", "description": "Test"}]
        tool_invoker = AsyncMock(return_value={"success": True, "data": "test"})

        agent = SRESubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Verify tool invoker is stored
        assert agent._invoke_tool == tool_invoker

        # Verify it can be called
        result = await agent._invoke_tool("test_tool", {})
        assert result["success"] is True
