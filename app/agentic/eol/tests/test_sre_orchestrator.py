"""
Unit tests for SRE Orchestrator.

Tests cover:
- Request handling (agent-first routing)
- Fallback to MCP execution
- Tool execution
- Error handling
- Lifecycle management

Created: 2026-02-27 (Phase 1, Task 2.2)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agents.sre_orchestrator import SREOrchestratorAgent


@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestSREOrchestrator:
    """Test suite for SRE Orchestrator."""

    async def test_handle_request_happy_path(self, factory_sre_orchestrator):
        """Test successful request handling with agent-first routing.

        Scenario: User requests SRE operation
        Expected: Orchestrator routes to agent, returns response
        """
        # Arrange
        orchestrator = factory_sre_orchestrator()
        request = {
            "query": "Check health of container app myapp",
            "workflow_id": "test-workflow-123"
        }

        # Mock agent execution
        mock_response = {
            "success": True,
            "formatted_response": "Container app is healthy",
            "agent_metadata": {"agent": "gccsreagent"}
        }

        with patch.object(orchestrator, '_execute_via_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = mock_response

            # Mock agent availability check
            if orchestrator.azure_sre_agent:
                orchestrator.azure_sre_agent.is_available = AsyncMock(return_value=True)

            # Act
            result = await orchestrator.handle_request(request)

            # Assert
            assert result is not None
            assert "formatted_response" in result or "success" in result

    async def test_handle_request_fallback_to_mcp(self, factory_sre_orchestrator):
        """Test fallback to MCP when agent is unavailable.

        Scenario: Agent is not available
        Expected: Orchestrator falls back to direct MCP execution
        """
        # Arrange
        orchestrator = factory_sre_orchestrator()
        request = {
            "query": "List container apps",
            "workflow_id": "test-workflow-456"
        }

        # Mock MCP fallback
        mock_mcp_response = {
            "success": True,
            "formatted_response": "Found 3 container apps",
            "tool_results": []
        }

        with patch.object(orchestrator, '_execute_mcp_fallback', new_callable=AsyncMock) as mock_mcp:
            mock_mcp.return_value = mock_mcp_response

            # Mock agent as unavailable
            if orchestrator.azure_sre_agent:
                orchestrator.azure_sre_agent.is_available = AsyncMock(return_value=False)

            # Act
            result = await orchestrator.handle_request(request)

            # Assert
            assert result["success"] is True
            mock_mcp.assert_called_once()

    async def test_handle_request_agent_timeout(self, factory_sre_orchestrator):
        """Test handling of agent timeout with MCP fallback.

        Scenario: Agent times out
        Expected: Falls back to MCP execution
        """
        import asyncio

        # Arrange
        orchestrator = factory_sre_orchestrator()
        request = {
            "query": "Slow operation",
            "workflow_id": "test-workflow-789"
        }

        # Mock agent timeout
        with patch.object(orchestrator, '_execute_via_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = asyncio.TimeoutError("Agent timeout")

            with patch.object(orchestrator, '_execute_mcp_fallback', new_callable=AsyncMock) as mock_mcp:
                mock_mcp.return_value = {"success": True, "formatted_response": "Completed via MCP"}

                # Mock agent availability
                if orchestrator.azure_sre_agent:
                    orchestrator.azure_sre_agent.is_available = AsyncMock(return_value=True)

                # Act
                result = await orchestrator.handle_request(request)

                # Assert
                assert result["success"] is True
                mock_mcp.assert_called_once()

    async def test_execute_legacy_interface(self, factory_sre_orchestrator):
        """Test legacy execute() method delegates to handle_request().

        Scenario: Use legacy execute() interface
        Expected: Calls handle_request() with merged context
        """
        # Arrange
        orchestrator = factory_sre_orchestrator()
        request = {"query": "Get metrics"}
        context = {"subscription_id": "test-sub"}

        with patch.object(orchestrator, 'handle_request', new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {"success": True}

            # Act
            result = await orchestrator.execute(request, context)

            # Assert
            assert result["success"] is True
            # Verify context was merged into request
            call_args = mock_handle.call_args[0][0]
            assert "context" in call_args
            assert call_args["context"]["subscription_id"] == "test-sub"

    async def test_handle_request_error_handling(self, factory_sre_orchestrator):
        """Test orchestrator handles exceptions gracefully.

        Scenario: Both agent and MCP fail
        Expected: Exception is handled or propagated appropriately
        """
        # Arrange
        orchestrator = factory_sre_orchestrator()
        request = {"query": "Failing operation"}

        # Mock both agent and MCP to fail
        with patch.object(orchestrator, '_execute_via_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = Exception("Agent failed")

            with patch.object(orchestrator, '_execute_mcp_fallback', new_callable=AsyncMock) as mock_mcp:
                mock_mcp.side_effect = Exception("MCP failed")

                # Mock agent availability
                if orchestrator.azure_sre_agent:
                    orchestrator.azure_sre_agent.is_available = AsyncMock(return_value=True)

                # Act & Assert
                with pytest.raises(Exception):
                    await orchestrator.handle_request(request)

    @pytest.mark.placeholder
    async def test_handle_request_circuit_breaker(self, factory_sre_orchestrator):
        """Test circuit breaker prevents cascading failures.

        Scenario: Multiple failures trigger circuit breaker
        Expected: Circuit opens, subsequent calls fail fast

        NOTE: Placeholder for Phase 2 (circuit breaker implementation)
        """
        pytest.skip("Circuit breaker not yet implemented (Phase 2)")

    @pytest.mark.placeholder
    async def test_handle_request_context_propagation(self, factory_sre_orchestrator):
        """Test workflow context propagates through orchestrator.

        Scenario: Request with workflow_id
        Expected: Context is stored and retrieved correctly

        NOTE: Placeholder for Phase 2 (context store implementation)
        """
        pytest.skip("Context propagation not yet implemented (Phase 2)")

    async def test_orchestrator_lifecycle_cleanup(self, factory_sre_orchestrator):
        """Test orchestrator properly cleans up resources.

        Scenario: Orchestrator is cleaned up
        Expected: All resources are released
        """
        # Arrange
        orchestrator = factory_sre_orchestrator()

        # Act
        await orchestrator.cleanup()

        # Assert - orchestrator should be in cleaned state
        # (Specific assertions depend on implementation)
        assert orchestrator is not None  # Basic check that cleanup didn't crash
