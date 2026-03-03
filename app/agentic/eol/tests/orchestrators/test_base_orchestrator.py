"""
Unit tests for BaseOrchestrator.

Tests cover:
- Lifecycle management (initialize, cleanup, shutdown)
- Tool invocation through registry
- Error handling and recovery
- Inventory context grounding
- Response formatting
- SSE streaming
- Background task management
- Abstract method enforcement

Created: 2026-03-02 (Phase 2, Task 6)
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any

from agents.base_orchestrator import (
    BaseOrchestrator,
    OrchestratorError,
    OrchestratorInitializationError,
    OrchestratorExecutionError,
)
from agents.orchestrator_models import (
    ExecutionPlan,
    OrchestratorResult,
    ErrorResult,
    SSEEventType,
    ToolEntry,
    PlanStep,
    InventoryContext,
)


# =============================================================================
# Concrete Test Implementation
# =============================================================================

class TestOrchestrator(BaseOrchestrator):
    """Concrete implementation for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.route_called = False
        self.execute_called = False
        self.mock_plan = None
        self.mock_result = None

    async def route_query(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> ExecutionPlan:
        """Test implementation of route_query."""
        self.route_called = True

        if self.mock_plan:
            return self.mock_plan

        return ExecutionPlan(
            strategy="test",
            domains=["test_domain"],
            tools=[
                ToolEntry(
                    name="test_tool",
                    description="Test tool",
                    server="test_server"
                )
            ],
            steps=[
                PlanStep(
                    step_number=1,
                    action="invoke_tool",
                    target="test_tool",
                    parameters={"param": "value"},
                    description="Test step"
                )
            ],
            context=context,
        )

    async def execute_plan(
        self,
        plan: ExecutionPlan,
    ) -> OrchestratorResult:
        """Test implementation of execute_plan."""
        self.execute_called = True

        if self.mock_result:
            return self.mock_result

        return OrchestratorResult(
            success=True,
            content="Test result",
            formatted_response="<p>Test result</p>",
            metadata={"test": "data"},
            tools_called=["test_tool"],
            duration_ms=100.0,
        )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_tool_registry():
    """Mock tool registry."""
    registry = MagicMock()
    registry.invoke_tool = AsyncMock(return_value={
        "success": True,
        "result": "Tool executed successfully"
    })
    registry.refresh = AsyncMock()
    return registry


@pytest.fixture
def mock_mcp_host():
    """Mock MCP host."""
    host = MagicMock()
    host.get_tools = MagicMock(return_value=[])
    return host


@pytest.fixture
def mock_response_formatter():
    """Mock response formatter."""
    formatter = MagicMock()
    formatter.format = MagicMock(return_value="<p>Formatted response</p>")
    return formatter


@pytest_asyncio.fixture
async def test_orchestrator():
    """Create a test orchestrator instance."""
    orch = TestOrchestrator(
        orchestrator_id="test-orch-123",
        enable_streaming=True,
        max_retries=3,
        timeout_seconds=60.0,
    )
    yield orch
    await orch.cleanup()


# =============================================================================
# Lifecycle Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorLifecycle:
    """Test orchestrator lifecycle management."""

    async def test_initialization(self, test_orchestrator):
        """Test orchestrator initializes successfully."""
        # Arrange
        orch = test_orchestrator

        # Act
        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            mock_fmt.return_value = MagicMock()

            await orch.initialize()

        # Assert
        assert orch._initialized is True
        assert orch._tool_registry is not None
        assert orch._response_formatter is not None

    async def test_initialization_idempotent(self, test_orchestrator):
        """Test that initialize can be called multiple times safely."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act - call initialize twice
            await orch.initialize()
            await orch.initialize()

        # Assert - should only initialize once
        assert orch._initialized is True
        assert mock_reg.call_count == 1

    async def test_initialization_failure(self):
        """Test handling of initialization failure."""
        # Arrange
        orch = TestOrchestrator()

        # Act & Assert
        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg:
            mock_reg.side_effect = Exception("Registry unavailable")

            with pytest.raises(OrchestratorInitializationError):
                await orch.initialize()

        assert orch._initialized is False

    async def test_cleanup(self, test_orchestrator):
        """Test cleanup cancels background tasks and resets state."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            await orch.initialize()

            # Spawn a background task
            async def dummy_task():
                await asyncio.sleep(10)

            orch._spawn_background("test-task", dummy_task())

        # Act
        await orch.cleanup()

        # Assert
        assert orch._initialized is False
        assert len(orch._background_tasks) == 0
        assert orch._inventory_context is None

    async def test_shutdown_alias(self, test_orchestrator):
        """Test that shutdown is an alias for cleanup."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            await orch.initialize()

        # Act
        await orch.shutdown()

        # Assert
        assert orch._initialized is False

    async def test_async_context_manager(self):
        """Test orchestrator works as async context manager."""
        # Act & Assert
        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            async with TestOrchestrator() as orch:
                await orch.initialize()
                assert orch._initialized is True

            # After context exit, should be cleaned up
            assert orch._initialized is False


# =============================================================================
# Tool Management Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorToolManagement:
    """Test tool management functionality."""

    async def test_invoke_tool_success(self, test_orchestrator, mock_tool_registry):
        """Test successful tool invocation."""
        # Arrange
        orch = test_orchestrator
        orch._tool_registry = mock_tool_registry

        # Act
        result = await orch.invoke_tool("test_tool", {"param": "value"})

        # Assert
        assert result["success"] is True
        mock_tool_registry.invoke_tool.assert_called_once_with(
            "test_tool",
            {"param": "value"}
        )

    async def test_invoke_tool_not_initialized(self, test_orchestrator):
        """Test tool invocation fails if registry not initialized."""
        # Arrange
        orch = test_orchestrator
        orch._tool_registry = None

        # Act & Assert
        with pytest.raises(OrchestratorExecutionError, match="Tool registry not initialized"):
            await orch.invoke_tool("test_tool", {})

    async def test_invoke_tool_failure(self, test_orchestrator, mock_tool_registry):
        """Test handling of tool invocation failure."""
        # Arrange
        orch = test_orchestrator
        orch._tool_registry = mock_tool_registry
        mock_tool_registry.invoke_tool.side_effect = Exception("Tool failed")

        # Act & Assert
        with pytest.raises(OrchestratorExecutionError, match="Tool test_tool failed"):
            await orch.invoke_tool("test_tool", {})

    async def test_refresh_tool_catalog(self, test_orchestrator, mock_tool_registry):
        """Test tool catalog refresh."""
        # Arrange
        orch = test_orchestrator
        orch._tool_registry = mock_tool_registry

        # Act
        await orch._refresh_tool_catalog()

        # Assert
        mock_tool_registry.refresh.assert_called_once()

    async def test_refresh_tool_catalog_no_registry(self, test_orchestrator):
        """Test refresh does nothing if registry not initialized."""
        # Arrange
        orch = test_orchestrator
        orch._tool_registry = None

        # Act - should not raise
        await orch._refresh_tool_catalog()


# =============================================================================
# Request Handling Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorRequestHandling:
    """Test request handling flow."""

    async def test_handle_request_initializes_if_needed(self, test_orchestrator):
        """Test handle_request initializes orchestrator if needed."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act
            result = await orch.handle_request("test query", stream=False)

        # Assert
        assert orch._initialized is True
        assert result.success is True

    async def test_handle_request_calls_route_and_execute(self, test_orchestrator):
        """Test handle_request calls route_query and execute_plan."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act
            result = await orch.handle_request(
                "test query",
                context={"key": "value"},
                stream=False
            )

        # Assert
        assert orch.route_called is True
        assert orch.execute_called is True
        assert isinstance(result, OrchestratorResult)
        assert result.success is True

    async def test_handle_request_with_context(self, test_orchestrator):
        """Test handle_request passes context correctly."""
        # Arrange
        orch = test_orchestrator
        context = {"subscription_id": "test-sub-123"}

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act
            result = await orch.handle_request(
                "test query",
                context=context,
                stream=False
            )

        # Assert
        assert result.success is True

    async def test_handle_request_error_handling(self, test_orchestrator):
        """Test handle_request handles errors gracefully."""
        # Arrange
        orch = test_orchestrator

        # Make execute_plan raise an error
        async def failing_execute(plan):
            raise Exception("Execution failed")

        orch.execute_plan = failing_execute

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act
            result = await orch.handle_request("test query", stream=False)

        # Assert
        assert result.success is False
        assert "Error:" in result.content
        assert result.error is not None


# =============================================================================
# Context Grounding Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorContextGrounding:
    """Test inventory context grounding."""

    async def test_ground_context_adds_inventory(self, test_orchestrator):
        """Test ground_context enriches context with inventory."""
        # Arrange
        import time
        orch = test_orchestrator
        orch._inventory_context = InventoryContext(
            tenant_id="test-tenant",
            subscription_ids=["sub-123"],
            resource_groups=["rg-test"],
            resource_count=10,
            summary="Test inventory"
        )
        orch._last_inventory_refresh = time.time()  # Set to now so it doesn't refresh

        # Act
        enriched = await orch.ground_context(
            "test query",
            {"existing": "value"}
        )

        # Assert
        assert "existing" in enriched
        assert "inventory_context" in enriched
        assert isinstance(enriched["inventory_context"], InventoryContext)
        assert enriched["inventory_context"].tenant_id == "test-tenant"

    async def test_ground_context_refreshes_expired(self, test_orchestrator):
        """Test ground_context refreshes expired inventory."""
        # Arrange
        orch = test_orchestrator
        orch._inventory_ttl_seconds = 0.1  # Very short TTL
        orch._last_inventory_refresh = 0.0  # Force refresh

        # Act
        enriched = await orch.ground_context("test query", {})

        # Assert
        assert orch._inventory_context is not None

    async def test_refresh_inventory_context(self, test_orchestrator):
        """Test inventory context refresh."""
        # Arrange
        orch = test_orchestrator

        # Act
        await orch._refresh_inventory_context()

        # Assert
        assert orch._inventory_context is not None
        assert orch._last_inventory_refresh > 0


# =============================================================================
# Response Formatting Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorResponseFormatting:
    """Test response formatting."""

    async def test_format_response_html(self, test_orchestrator, mock_response_formatter):
        """Test HTML response formatting."""
        # Arrange
        orch = test_orchestrator
        orch._response_formatter = mock_response_formatter

        # Act
        result = orch.format_response({"data": "test"}, format="formatted_html")

        # Assert
        assert result == "<p>Formatted response</p>"
        mock_response_formatter.format.assert_called_once()

    async def test_format_response_json(self, test_orchestrator):
        """Test JSON response formatting."""
        # Arrange
        orch = test_orchestrator

        # Act
        result = orch.format_response({"data": "test"}, format="raw_json")

        # Assert
        assert '"data"' in result
        assert '"test"' in result

    async def test_format_response_fallback(self, test_orchestrator):
        """Test response formatting fallback."""
        # Arrange
        orch = test_orchestrator

        # Act
        result = orch.format_response({"data": "test"}, format="unknown")

        # Assert
        assert "data" in result

    async def test_format_error_response(self, test_orchestrator):
        """Test error response formatting."""
        # Arrange
        orch = test_orchestrator
        error = ErrorResult(
            error_type="TestError",
            message="Test error message",
            details={"key": "value"}
        )

        # Act
        result = orch._format_error_response(error)

        # Assert
        assert "TestError" in result
        assert "Test error message" in result
        assert "<div class=\"error-container\">" in result


# =============================================================================
# Streaming Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorStreaming:
    """Test SSE streaming functionality."""

    async def test_handle_request_streaming(self, test_orchestrator):
        """Test handle_request returns streaming generator."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            # Act
            result = await orch.handle_request("test query", stream=True)

        # Assert
        assert hasattr(result, '__aiter__')

    async def test_stream_execution_emits_events(self, test_orchestrator):
        """Test streaming emits correct SSE events."""
        # Arrange
        orch = test_orchestrator

        with patch('agents.base_orchestrator.get_tool_registry') as mock_reg, \
             \
             patch('agents.base_orchestrator.ResponseFormatter') as mock_fmt:

            mock_reg.return_value = MagicMock()
            
            mock_fmt.return_value = MagicMock()

            await orch.initialize()

            plan = await orch.route_query("test", {})

            # Act
            events = []
            async for event in orch._stream_execution(plan, 0.0):
                events.append(event)

        # Assert
        assert len(events) >= 3  # status, result, done
        assert "event: status" in events[0]
        assert "event: result" in events[-2]
        assert "event: done" in events[-1]

    async def test_emit_event_format(self, test_orchestrator):
        """Test SSE event formatting."""
        # Arrange
        orch = test_orchestrator

        # Act
        event = orch._emit_event(SSEEventType.STATUS, {"status": "running"})

        # Assert
        assert "event: status\n" in event
        assert "data: " in event
        assert '"status"' in event
        assert '"running"' in event


# =============================================================================
# Background Task Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorBackgroundTasks:
    """Test background task management."""

    async def test_spawn_background_task(self, test_orchestrator):
        """Test spawning background task."""
        # Arrange
        orch = test_orchestrator
        task_executed = False

        async def background_task():
            nonlocal task_executed
            task_executed = True
            await asyncio.sleep(0.01)

        # Act
        task = orch._spawn_background("test-task", background_task())
        await asyncio.sleep(0.02)  # Let task execute

        # Assert
        assert len(orch._background_tasks) == 1
        assert task_executed is True

    async def test_cancel_background_tasks(self, test_orchestrator):
        """Test cancelling all background tasks."""
        # Arrange
        orch = test_orchestrator

        async def long_task():
            await asyncio.sleep(10)

        # Spawn multiple tasks
        orch._spawn_background("task-1", long_task())
        orch._spawn_background("task-2", long_task())

        # Act
        await orch._cancel_background_tasks()

        # Assert
        assert len(orch._background_tasks) == 0


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestBaseOrchestratorErrorHandling:
    """Test error handling."""

    async def test_handle_error_creates_error_result(self, test_orchestrator):
        """Test error handling creates ErrorResult."""
        # Arrange
        orch = test_orchestrator
        error = ValueError("Test error")
        context = {"key": "value"}

        # Act
        result = await orch._handle_error(error, context)

        # Assert
        assert isinstance(result, ErrorResult)
        assert result.error_type == "ValueError"
        assert "Test error" in result.message
        assert result.details["context"] == context

    async def test_handle_error_logs_error(self, test_orchestrator):
        """Test error handling logs errors."""
        # Arrange
        orch = test_orchestrator
        error = Exception("Test error")

        with patch('agents.base_orchestrator.logger') as mock_logger:
            # Act
            await orch._handle_error(error, {})

            # Assert
            mock_logger.error.assert_called_once()


# =============================================================================
# Abstract Method Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.orchestrator
class TestBaseOrchestratorAbstractMethods:
    """Test abstract method enforcement."""

    def test_cannot_instantiate_base_class(self):
        """Test BaseOrchestrator cannot be instantiated directly."""
        # Act & Assert
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseOrchestrator()

    def test_subclass_must_implement_route_query(self):
        """Test subclass must implement route_query."""
        # Arrange
        class IncompleteOrchestrator(BaseOrchestrator):
            async def execute_plan(self, plan):
                pass

        # Act & Assert
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteOrchestrator()

    def test_subclass_must_implement_execute_plan(self):
        """Test subclass must implement execute_plan."""
        # Arrange
        class IncompleteOrchestrator(BaseOrchestrator):
            async def route_query(self, query, context):
                pass

        # Act & Assert
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteOrchestrator()
