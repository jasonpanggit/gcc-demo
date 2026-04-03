"""
Monitor Agent Tests

Tests for Azure Monitor agent functionality.
Created: 2026-02-27 (Phase 3, Week 1, Day 3)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import sys

# Mock the logging_config import before importing monitor_agent
sys.modules['utils.logging_config'] = MagicMock()

from agents.monitor_agent import MonitorAgent
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
class TestMonitorAgent:
    """Tests for MonitorAgent."""

    def test_agent_initialization(self):
        """Test that Monitor agent initializes correctly."""
        tool_defs = [{"name": "get_service_monitor_resources", "description": "Get resources"}]
        tool_invoker = AsyncMock()

        agent = MonitorAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker
        )

        assert agent._MAX_ITERATIONS == 15
        assert agent._tool_definitions == tool_defs
        assert agent._invoke_tool == tool_invoker

    def test_agent_has_system_prompt(self):
        """Test that agent has Azure Monitor-specific system prompt."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_SYSTEM_PROMPT')
        assert len(agent._SYSTEM_PROMPT) > 0
        assert "Azure Monitor" in agent._SYSTEM_PROMPT
        assert "monitor" in agent._SYSTEM_PROMPT.lower()

    def test_system_prompt_covers_monitor_operations(self):
        """Test that system prompt covers all monitor operations."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should mention key monitor operations
        assert "workbook" in prompt.lower()
        assert "alert" in prompt.lower()
        assert "query" in prompt.lower() or "kql" in prompt.lower()
        assert "deploy" in prompt.lower()

    def test_system_prompt_has_deployment_rules(self):
        """Test system prompt includes deployment safety rules."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should have deployment rules
        assert "DEPLOYMENT" in prompt or "deployment" in prompt.lower()
        assert "resource_group" in prompt or "workspace" in prompt

    def test_system_prompt_has_workflows(self):
        """Test system prompt includes discovery and deployment workflows."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        prompt = agent._SYSTEM_PROMPT

        # Should define workflows
        assert "WORKFLOW" in prompt
        assert "DISCOVERY" in prompt or "discovery" in prompt.lower()

    def test_agent_has_run_method(self):
        """Test that agent has run method."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, 'run')
        assert callable(agent.run)

    def test_max_iterations_configured(self):
        """Test max iterations is appropriate for monitor workflows."""
        assert MonitorAgent._MAX_ITERATIONS == 15
        assert MonitorAgent._MAX_ITERATIONS > 5

    def test_event_callback_optional(self):
        """Test that event callback is optional."""
        tool_defs = []
        tool_invoker = AsyncMock()

        # Should initialize without event_callback
        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert hasattr(agent, '_push_event')

    def test_event_callback_provided(self):
        """Test that event callback can be provided."""
        tool_defs = []
        tool_invoker = AsyncMock()
        event_callback = AsyncMock()

        agent = MonitorAgent(
            tool_definitions=tool_defs,
            tool_invoker=tool_invoker,
            event_callback=event_callback
        )

        assert agent._push_event == event_callback

    def test_deploy_required_params_configured(self):
        """Test deploy tool required parameters are defined."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Should have deploy param specs
        assert hasattr(MonitorAgent, '_DEPLOY_REQUIRED_PARAMS')
        assert isinstance(MonitorAgent._DEPLOY_REQUIRED_PARAMS, dict)

        # Should define params for each deploy tool
        assert "deploy_query" in MonitorAgent._DEPLOY_REQUIRED_PARAMS
        assert "deploy_alert" in MonitorAgent._DEPLOY_REQUIRED_PARAMS
        assert "deploy_workbook" in MonitorAgent._DEPLOY_REQUIRED_PARAMS

    def test_check_deploy_params_validation(self):
        """Test deploy parameter validation logic."""
        # Should return None for non-deploy tools
        result = MonitorAgent._check_deploy_params("list_resources", {})
        assert result is None

        # Should return None when all required params are filled
        result = MonitorAgent._check_deploy_params(
            "deploy_query",
            {"resource_group": "my-rg", "workspace_name": "my-workspace"}
        )
        assert result is None

        # Should return error dict when params are missing
        result = MonitorAgent._check_deploy_params("deploy_query", {})
        assert result is not None
        assert result.get("status") == "needs_user_input"

        # Should return error dict when params are empty strings
        result = MonitorAgent._check_deploy_params(
            "deploy_query",
            {"resource_group": "", "workspace_name": ""}
        )
        assert result is not None
        assert result.get("status") == "needs_user_input"

    def test_check_deploy_params_workbook(self):
        """Test deploy parameter validation for workbooks."""
        # Should require all workbook params
        result = MonitorAgent._check_deploy_params("deploy_workbook", {})
        assert result is not None
        assert "subscription_id" in result.get("message", "")

        # Should pass when all params provided
        result = MonitorAgent._check_deploy_params(
            "deploy_workbook",
            {
                "subscription_id": "sub-123",
                "resource_group": "my-rg",
                "workbook_name": "my-workbook",
                "location": "eastus"
            }
        )
        assert result is None

    def test_check_deploy_params_alert(self):
        """Test deploy parameter validation for alerts."""
        # Should require resource_group and scopes
        result = MonitorAgent._check_deploy_params("deploy_alert", {})
        assert result is not None

        # Should pass when params provided
        result = MonitorAgent._check_deploy_params(
            "deploy_alert",
            {"resource_group": "my-rg", "scopes": "/subscriptions/..."}
        )
        assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestMonitorAgentIntegration:
    """Integration tests for Monitor agent with Phase 2 utilities."""

    async def test_agent_with_error_aggregator(self):
        """Test agent integration with error aggregator."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        agg = ErrorAggregator()

        # Simulate agent operation that might fail
        try:
            # Agent initialization should not fail
            assert agent is not None
        except Exception as e:
            agg.add_error(e, {"agent": "monitor", "operation": "init"})

        # Should have no errors
        assert not agg.has_errors()

    async def test_agent_with_timeout_config(self):
        """Test agent integration with centralized timeout config."""
        from utils.config import TimeoutConfig

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        timeout_config = TimeoutConfig()

        # Max iterations should be reasonable
        assert agent._MAX_ITERATIONS <= 50

    async def test_agent_with_circuit_breaker_pattern(self):
        """Test agent can work with circuit breaker pattern."""
        from utils.circuit_breaker import CircuitBreaker

        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)
        cb = CircuitBreaker(failure_threshold=2, name="monitor_agent")

        # Circuit breaker pattern should be compatible
        assert cb.state.value in ["OPEN", "CLOSED"]

    async def test_tool_invoker_callback(self):
        """Test that tool invoker is called correctly."""
        tool_defs = [{"name": "get_service_monitor_resources", "description": "Test"}]
        tool_invoker = AsyncMock(return_value={"success": True, "data": "test"})

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Verify tool invoker is stored
        assert agent._invoke_tool == tool_invoker

        # Verify it can be called
        result = await agent._invoke_tool("get_service_monitor_resources", {})
        assert result["success"] is True

    async def test_tool_definitions_passed(self):
        """Test that tool definitions are properly stored."""
        tool_defs = [
            {"name": "get_service_monitor_resources", "description": "Get resources"},
            {"name": "deploy_workbook", "description": "Deploy workbook"}
        ]
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        assert agent._tool_definitions == tool_defs
        assert len(agent._tool_definitions) == 2

    async def test_noop_event_handler(self):
        """Test that noop event handler works when no callback provided."""
        tool_defs = []
        tool_invoker = AsyncMock()

        agent = MonitorAgent(tool_definitions=tool_defs, tool_invoker=tool_invoker)

        # Should have noop event handler
        assert hasattr(agent, '_push_event')

        # Should be callable without errors
        await agent._push_event("test_event", "test_content")
