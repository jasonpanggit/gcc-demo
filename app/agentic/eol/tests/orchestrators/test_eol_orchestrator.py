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


class DummyAgent:
    """Minimal lifecycle-safe test double for orchestrator-managed agents."""

    async def aclose(self):
        return None

    async def health_check(self):
        return {"status": "healthy"}


@pytest.fixture
def sample_eol_response():
    return {
        "success": True,
        "data": {
            "software": "Windows Server 2025",
            "version": "2025",
            "eol_date": "2030-10-14",
        },
        "confidence": 0.95,
        "agent_used": "endoflife",
        "source": "endoflife",
        "source_url": "https://endoflife.date/windows-server-2025",
        "search_mode": "agents_plus_internet",
        "sources": [],
        "discrepancies": [],
        "communications": [],
        "elapsed_seconds": 0.01,
    }


@pytest.fixture
def factory_eol_orchestrator():
    """Create orchestrators with lightweight stub agents for focused unit tests."""

    def _factory() -> EOLOrchestratorAgent:
        agents = {
            "endoflife": DummyAgent(),
            "eolstatus": DummyAgent(),
            "microsoft": DummyAgent(),
            "redhat": DummyAgent(),
            "ubuntu": DummyAgent(),
            "playwright": DummyAgent(),
        }
        return EOLOrchestratorAgent(agents=agents, close_provided_agents=False)

    return _factory


@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestEOLOrchestrator:
    """Test suite for EOL Orchestrator."""

    async def test_get_eol_data_happy_path(self, factory_eol_orchestrator, sample_eol_response):
        """Test successful EOL data retrieval with all agents succeeding.

        Scenario: User queries "Windows Server 2025"
        Expected: Orchestrator returns success with EOL data
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()
        software_name = "Windows Server 2025"

        # Mock the underlying get_autonomous_eol_data method
        with patch.object(orchestrator, 'get_autonomous_eol_data', new_callable=AsyncMock) as mock_get_autonomous:
            mock_get_autonomous.return_value = sample_eol_response

            # Act
            result = await orchestrator.get_eol_data(software_name)

            # Assert
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["software"] == "Windows Server 2025"
            mock_get_autonomous.assert_called_once_with(software_name, None)


    async def test_get_eol_data_agent_failure(self, factory_eol_orchestrator):
        """Test orchestrator handles agent failure gracefully.

        Scenario: Agent raises an exception
        Expected: Orchestrator propagates exception (or returns error response)
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()
        software_name = "Unknown Software"

        # Mock agent to raise exception
        with patch.object(orchestrator, 'get_autonomous_eol_data', new_callable=AsyncMock) as mock_get_autonomous:
            mock_get_autonomous.side_effect = Exception("Agent failed")

            # Act & Assert
            with pytest.raises(Exception, match="Agent failed"):
                await orchestrator.get_eol_data(software_name)


    async def test_get_eol_data_with_version(self, factory_eol_orchestrator, sample_eol_response):
        """Test EOL data retrieval with version parameter.

        Scenario: Multiple agents called with version parameter
        Expected: Returns success with data from successful agents
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()
        software_name = "Windows Server"
        version = "2025"

        # Mock successful response
        with patch.object(orchestrator, 'get_autonomous_eol_data', new_callable=AsyncMock) as mock_get_autonomous:
            mock_get_autonomous.return_value = sample_eol_response

            # Act
            result = await orchestrator.get_eol_data(software_name, version)

            # Assert
            assert result["success"] is True
            assert "data" in result
            mock_get_autonomous.assert_called_once_with(software_name, version)


    async def test_get_eol_data_timeout(self, factory_eol_orchestrator):
        """Test orchestrator handles timeout correctly.

        Scenario: Agent takes too long to respond
        Expected: asyncio.TimeoutError propagates
        """
        import asyncio

        # Arrange
        orchestrator = factory_eol_orchestrator()
        software_name = "Slow Software"

        # Mock agent to take too long
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow operation
            return {"success": True}

        with patch.object(orchestrator, 'get_autonomous_eol_data', new_callable=AsyncMock) as mock_get_autonomous:
            mock_get_autonomous.side_effect = slow_operation

            # Act & Assert
            with pytest.raises(asyncio.TimeoutError):
                # Wrap orchestrator call with timeout
                await asyncio.wait_for(orchestrator.get_eol_data(software_name), timeout=0.1)


    @pytest.mark.placeholder
    async def test_get_eol_data_circuit_breaker(self, factory_eol_orchestrator):
        """Test circuit breaker prevents cascading failures.

        Scenario: Multiple failures trigger circuit breaker
        Expected: Circuit opens, subsequent calls fail fast

        NOTE: Placeholder for Phase 2 (circuit breaker implementation)
        """
        pytest.skip("Circuit breaker not yet implemented (Phase 2)")


    async def test_get_autonomous_eol_data_error_handling(self, factory_eol_orchestrator):
        """Test get_autonomous_eol_data handles exceptions from agents gracefully.

        Scenario: All agents fail during autonomous query
        Expected: Returns failure response instead of raising exception
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()
        software_name = "NonexistentSoftware"

        # Mock the pipeline itself to fail during fetch
        with patch.object(orchestrator._pipeline, 'fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Agent invocation failed")

            # Act
            result = await orchestrator.get_autonomous_eol_data(software_name)

            # Assert - orchestrator handles error gracefully
            assert result is not None
            assert result.get("success") is False
            assert "error" in result
            assert "Agent invocation failed" in result.get("error", "")


    @pytest.mark.placeholder
    async def test_get_eol_data_fallback(self, factory_eol_orchestrator):
        """Test orchestrator uses fallback mechanism when primary agent fails.

        Scenario: Primary agent fails, fallback agent succeeds
        Expected: Returns success with fallback data

        NOTE: Placeholder for Phase 2 (fallback mechanism)
        """
        pytest.skip("Fallback mechanism not yet implemented (Phase 2)")


    @pytest.mark.placeholder
    async def test_get_eol_data_context_propagation(self, factory_eol_orchestrator):
        """Test correlation ID propagates through orchestrator calls.

        Scenario: Request with correlation ID
        Expected: Correlation ID present in all agent calls and response

        NOTE: Placeholder for Phase 2 (correlation ID implementation)
        """
        pytest.skip("Correlation ID not yet implemented (Phase 2)")


    async def test_orchestrator_lifecycle_aclose(self, factory_eol_orchestrator):
        """Test orchestrator properly closes resources.

        Scenario: Orchestrator is closed
        Expected: All agent resources are cleaned up
        """
        # Arrange
        orchestrator = factory_eol_orchestrator()

        # Act
        await orchestrator.aclose()

        # Assert
        assert orchestrator._closed is True


    async def test_orchestrator_context_manager(self, factory_eol_orchestrator):
        """Test orchestrator works as async context manager.

        Scenario: Use orchestrator in async with statement
        Expected: Orchestrator is properly initialized and cleaned up
        """
        # Arrange & Act
        async with factory_eol_orchestrator() as orchestrator:
            # Assert - orchestrator is usable
            assert orchestrator is not None
            assert hasattr(orchestrator, 'get_eol_data')

        # After context - orchestrator should be closed
        assert orchestrator._closed is True
