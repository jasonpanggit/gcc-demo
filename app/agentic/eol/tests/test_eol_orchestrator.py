"""
Unit tests for EOL Orchestrator.

Tests cover:
- Happy path (all agents succeed)
- Agent failure handling
- Partial success scenarios
- Timeout handling
- Error aggregation

Created: 2026-02-27 (Phase 1, Task 1.3)
"""

import pytest
from unittest.mock import AsyncMock, patch
from agents.eol_orchestrator import EOLOrchestratorAgent


@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestEOLOrchestrator:
    """Test suite for EOL Orchestrator."""

    async def test_process_query_happy_path(self, factory_eol_orchestrator, sample_eol_response):
        """Test successful query processing with all agents succeeding.

        Scenario: User queries "Windows Server 2025"
        Expected: Orchestrator returns success with EOL data
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()
        query = "Windows Server 2025"

        # Mock agent response
        with patch.object(orchestrator, 'get_eol_data', new_callable=AsyncMock) as mock_get_eol:
            mock_get_eol.return_value = sample_eol_response

            # Act
            result = await orchestrator.process_query(query)

            # Assert
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["software"] == "Windows Server 2025"
            mock_get_eol.assert_called_once_with(query)


    # Additional tests to be added in Task 1.4:
    # - test_process_query_agent_failure
    # - test_process_query_partial_success
    # - test_process_query_timeout
    # - test_process_query_circuit_breaker
    # - test_process_query_error_aggregation
    # - test_process_query_fallback
    # - test_process_query_context_propagation
