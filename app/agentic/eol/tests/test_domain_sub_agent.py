"""
Domain Sub-Agent Base Class Tests

Tests for DomainSubAgent base class functionality.
Created: 2026-02-27 (Phase 3, Week 1, Day 5)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import sys

# Mock dependencies before import
sys.modules['utils.logging_config'] = MagicMock()

from agents.domain_sub_agent import DomainSubAgent


@pytest.mark.unit
class TestDomainSubAgent:
    """Tests for DomainSubAgent base class."""

    def test_agent_initialization(self):
        """Test domain sub-agent initialization."""
        tool_defs = [{"name": "test_tool", "description": "Test"}]
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker
        )

        assert agent._tool_definitions == tool_defs
        assert agent._invoke_tool == tool_invoker
        assert agent._DOMAIN_NAME == "generic"
        assert agent._MAX_ITERATIONS == 15
        assert agent._TIMEOUT_SECONDS == 45.0

    def test_agent_has_system_prompt(self):
        """Test agent has default system prompt."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert len(agent._SYSTEM_PROMPT) > 0
        assert "helpful assistant" in agent._SYSTEM_PROMPT

    def test_agent_has_run_method(self):
        """Test agent has run method."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, 'run')
        assert callable(agent.run)

    def test_domain_name_default(self):
        """Test default domain name."""
        assert DomainSubAgent._DOMAIN_NAME == "generic"

    def test_max_iterations_default(self):
        """Test default max iterations."""
        assert DomainSubAgent._MAX_ITERATIONS == 15
        assert DomainSubAgent._MAX_ITERATIONS > 0

    def test_timeout_default(self):
        """Test default timeout."""
        assert DomainSubAgent._TIMEOUT_SECONDS == 45.0
        assert DomainSubAgent._TIMEOUT_SECONDS > 0

    def test_event_callback_optional(self):
        """Test event callback is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_push_event')

    def test_event_callback_provided(self):
        """Test event callback can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        event_callback = AsyncMock()

        agent = DomainSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            event_callback=event_callback
        )

        assert agent._push_event == event_callback

    def test_conversation_context_default(self):
        """Test conversation context defaults to empty list."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_conversation_context')
        assert isinstance(agent._conversation_context, list)
        assert len(agent._conversation_context) == 0

    def test_conversation_context_provided(self):
        """Test conversation context can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        context = [{"role": "user", "content": "Hello"}]

        agent = DomainSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            conversation_context=context
        )

        assert agent._conversation_context == context

    def test_tool_definitions_stored(self):
        """Test tool definitions are stored correctly."""
        tool_defs = [
            {"name": "tool1", "description": "First"},
            {"name": "tool2", "description": "Second"}
        ]
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert agent._tool_definitions == tool_defs
        assert len(agent._tool_definitions) == 2

    def test_tool_invoker_stored(self):
        """Test tool invoker is stored correctly."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert agent._invoke_tool == tool_invoker


@pytest.mark.integration
@pytest.mark.asyncio
class TestDomainSubAgentIntegration:
    """Integration tests for DomainSubAgent."""

    async def test_tool_invoker_can_be_called(self):
        """Test that tool invoker can be called."""
        tool_defs = []
        tool_invoker = AsyncMock(return_value={"success": True, "data": "test"})

        agent = DomainSubAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Should be able to call the tool invoker
        result = await agent._invoke_tool("test_tool", {})

        assert result["success"] is True
        assert result["data"] == "test"
        tool_invoker.assert_called_once_with("test_tool", {})

    async def test_event_callback_can_be_called(self):
        """Test that event callback can be called."""
        tool_defs = []
        tool_invoker = AsyncMock()
        event_callback = AsyncMock()

        agent = DomainSubAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            event_callback=event_callback
        )

        # Should be able to call the event callback
        await agent._push_event("test_event", "test_content")

        event_callback.assert_called_once()
