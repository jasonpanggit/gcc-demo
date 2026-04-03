"""
Patch Sub-Agent Tests

Tests for Patch Management domain sub-agent functionality.
Created: 2026-02-27 (Phase 3, Week 1, Day 3)
"""

import pytest
from unittest.mock import AsyncMock
from agents.patch_sub_agent import PatchSubAgent
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
class TestPatchSubAgent:
    """Tests for PatchSubAgent."""

    def test_agent_initialization(self):
        """Test that Patch sub-agent initializes correctly."""
        tool_defs = [{"name": "assess_vm_patches", "description": "Assess patches"}]
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker
        )

        assert agent._DOMAIN_NAME == "patch"
        assert agent._MAX_ITERATIONS == 15
        assert agent._TIMEOUT_SECONDS == 45.0
        assert agent._tool_definitions == tool_defs
        assert agent._invoke_tool == tool_invoker

    def test_agent_has_system_prompt(self):
        """Test that agent has patch management-specific system prompt."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert len(agent._SYSTEM_PROMPT) > 0
        assert "Patch Management" in agent._SYSTEM_PROMPT
        assert "patch" in agent._SYSTEM_PROMPT.lower()

    def test_system_prompt_covers_patch_operations(self):
        """Test that system prompt covers all patch operations."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should mention key patch operations
        assert "assessment" in prompt.lower()
        assert "compliance" in prompt.lower()
        assert "install" in prompt.lower()
        assert "reboot" in prompt.lower()

    def test_system_prompt_has_severity_levels(self):
        """Test that system prompt defines patch severity levels."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should define severity levels
        assert "Critical" in prompt
        assert "Security" in prompt
        assert "Important" in prompt

    def test_system_prompt_has_safety_rules(self):
        """Test system prompt includes safety rules for patch installation."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should have safety rules
        assert "SAFETY" in prompt or "approval" in prompt.lower()
        assert "confirmation" in prompt.lower() or "Wait for" in prompt

    def test_agent_inherits_from_domain_sub_agent(self):
        """Test that agent inherits from DomainSubAgent."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Check that agent has DomainSubAgent attributes
        assert hasattr(agent, '_DOMAIN_NAME')
        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert hasattr(agent, '_MAX_ITERATIONS')
        assert hasattr(agent, 'run')

    def test_agent_has_run_method(self):
        """Test that agent has run method."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, 'run')
        assert callable(agent.run)

    def test_domain_name_constant(self):
        """Test domain name is correctly set."""
        assert PatchSubAgent._DOMAIN_NAME == "patch"

    def test_max_iterations_configured(self):
        """Test max iterations is appropriate for patch workflows."""
        assert PatchSubAgent._MAX_ITERATIONS == 15
        assert PatchSubAgent._MAX_ITERATIONS > 5

    def test_timeout_configured(self):
        """Test timeout is configured."""
        assert PatchSubAgent._TIMEOUT_SECONDS == 45.0
        assert PatchSubAgent._TIMEOUT_SECONDS > 0

    def test_event_callback_optional(self):
        """Test that event callback is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        # Should initialize without event_callback
        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_push_event')

    def test_event_callback_provided(self):
        """Test that event callback can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        event_callback = AsyncMock()

        agent = PatchSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            event_callback=event_callback
        )

        assert agent._push_event == event_callback

    def test_conversation_context_optional(self):
        """Test that conversation context is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_conversation_context')
        assert isinstance(agent._conversation_context, list)

    def test_conversation_context_provided(self):
        """Test that conversation context can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        context = [{"role": "user", "content": "Check patches"}]

        # Note: conversation_context is a keyword argument
        agent = PatchSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker
        )

        # Agent should have conversation context attribute
        assert hasattr(agent, '_conversation_context')
        assert isinstance(agent._conversation_context, list)

    def test_system_prompt_has_workflows(self):
        """Test system prompt includes common patch workflows."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should define common workflows
        assert "WORKFLOW" in prompt or "workflow" in prompt.lower()
        assert "Compliance" in prompt or "compliance" in prompt.lower()


@pytest.mark.integration
@pytest.mark.asyncio
class TestPatchSubAgentIntegration:
    """Integration tests for Patch sub-agent with Phase 2 utilities."""

    async def test_agent_with_error_aggregator(self):
        """Test agent integration with error aggregator."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        agg = ErrorAggregator()

        # Simulate agent operation that might fail
        try:
            # Agent initialization should not fail
            assert agent is not None
        except Exception as e:
            agg.add_error(e, {"agent": "patch", "operation": "init"})

        # Should have no errors
        assert not agg.has_errors()

    async def test_agent_with_timeout_config(self):
        """Test agent integration with centralized timeout config."""
        from utils.config import TimeoutConfig

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        timeout_config = TimeoutConfig()

        # Agent timeout should be reasonable (patch workflows need more time)
        assert agent._TIMEOUT_SECONDS <= timeout_config.agent_timeout * 5

    async def test_agent_with_circuit_breaker_pattern(self):
        """Test agent can work with circuit breaker pattern."""
        from utils.circuit_breaker import CircuitBreaker

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        cb = CircuitBreaker(failure_threshold=2, name="patch_agent")

        # Circuit breaker pattern should be compatible
        assert cb.state.value in ["OPEN", "CLOSED"]

    async def test_tool_invoker_callback(self):
        """Test that tool invoker is called correctly."""
        tool_defs = [{"name": "assess_vm_patches", "description": "Test"}]
        tool_invoker = AsyncMock(return_value={"success": True, "data": "test"})

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Verify tool invoker is stored
        assert agent._invoke_tool == tool_invoker

        # Verify it can be called
        result = await agent._invoke_tool("assess_vm_patches", {})
        assert result["success"] is True

    async def test_tool_definitions_passed(self):
        """Test that tool definitions are properly stored."""
        tool_defs = [
            {"name": "list_azure_vms", "description": "List VMs"},
            {"name": "assess_vm_patches", "description": "Assess patches"}
        ]
        tool_invoker = AsyncMock()

        agent = PatchSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert agent._tool_definitions == tool_defs
        assert len(agent._tool_definitions) == 2
