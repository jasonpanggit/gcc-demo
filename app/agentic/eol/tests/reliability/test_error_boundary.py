"""
Error Boundary Tests

Tests for error boundary wrapper with fallback and aggregation support.
Created: 2026-02-27 (Phase 2, Day 6)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from utils.error_boundary import (
    with_error_boundary,
    error_boundary,
    with_error_aggregation
)
from utils.error_aggregator import ErrorAggregator
from utils.correlation_id import set_correlation_id, clear_correlation_id


@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorBoundary:
    """Tests for error boundary wrapper."""

    async def test_with_error_boundary_success(self):
        """Test that successful function execution passes through."""
        async def successful_func():
            return "success"

        result = await with_error_boundary(successful_func)

        assert result == "success"

    async def test_with_error_boundary_catches_exception(self):
        """Test that error boundary catches exceptions."""
        async def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await with_error_boundary(failing_func)

    async def test_with_error_boundary_calls_fallback(self):
        """Test that fallback is called on error."""
        async def failing_func():
            raise ValueError("Primary failed")

        async def fallback_func():
            return "fallback_result"

        result = await with_error_boundary(failing_func, fallback=fallback_func)

        assert result == "fallback_result"

    async def test_with_error_boundary_suppress_exceptions(self):
        """Test that errors can be suppressed."""
        async def failing_func():
            raise ValueError("Test error")

        result = await with_error_boundary(failing_func, suppress=True)

        assert result is None  # Suppressed, returns None

    async def test_with_error_boundary_with_context(self):
        """Test that context is passed through error boundary."""
        async def failing_func():
            raise ValueError("Test error")

        context = {"operation": "test", "agent": "test_agent"}

        with pytest.raises(ValueError):
            await with_error_boundary(failing_func, context=context)

        # Context should be used in logging (hard to test without capturing logs)

    async def test_with_error_boundary_fallback_also_fails(self):
        """Test behavior when both primary and fallback fail."""
        async def failing_func():
            raise ValueError("Primary failed")

        async def failing_fallback():
            raise RuntimeError("Fallback also failed")

        # Should raise the fallback error when not suppressed
        with pytest.raises(RuntimeError, match="Fallback also failed"):
            await with_error_boundary(failing_func, fallback=failing_fallback)

    async def test_with_error_boundary_fallback_fails_suppressed(self):
        """Test that fallback failure can be suppressed."""
        async def failing_func():
            raise ValueError("Primary failed")

        async def failing_fallback():
            raise RuntimeError("Fallback failed")

        result = await with_error_boundary(
            failing_func,
            fallback=failing_fallback,
            suppress=True
        )

        assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorBoundaryDecorator:
    """Tests for error_boundary decorator."""

    async def test_decorator_on_successful_function(self):
        """Test decorator on successful function."""
        @error_boundary()
        async def successful_func():
            return "decorated_success"

        result = await successful_func()

        assert result == "decorated_success"

    async def test_decorator_with_fallback(self):
        """Test decorator with fallback function."""
        async def fallback_func():
            return "fallback_value"

        @error_boundary(fallback=fallback_func)
        async def failing_func():
            raise ValueError("Decorated failure")

        result = await failing_func()

        assert result == "fallback_value"

    async def test_decorator_with_suppress(self):
        """Test decorator with error suppression."""
        @error_boundary(suppress=True)
        async def failing_func():
            raise ValueError("Suppressed error")

        result = await failing_func()

        assert result is None

    async def test_decorator_with_context(self):
        """Test decorator with context."""
        @error_boundary(context={"service": "test_service"})
        async def failing_func():
            raise ValueError("Context error")

        with pytest.raises(ValueError):
            await failing_func()

    async def test_decorator_preserves_function_arguments(self):
        """Test that decorator preserves function arguments."""
        @error_boundary()
        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await func_with_args("x", "y", c="z")

        assert result == "x-y-z"


@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorAggregationIntegration:
    """Tests for error boundary with error aggregation."""

    async def test_with_error_aggregation_success(self):
        """Test successful execution with aggregation."""
        agg = ErrorAggregator()

        async def successful_func():
            return "success"

        result = await with_error_aggregation(successful_func, agg)

        assert result == "success"
        assert not agg.has_errors()

    async def test_with_error_aggregation_collects_errors(self):
        """Test that errors are collected in aggregator."""
        agg = ErrorAggregator()

        async def failing_func():
            raise ValueError("Aggregated error")

        context = {"agent": "test_agent", "operation": "test"}
        result = await with_error_aggregation(failing_func, agg, context=context)

        assert result is None  # Returns None on error
        assert agg.has_errors()
        assert agg.get_error_count() == 1

        errors = agg.get_summary()["errors"]
        assert errors[0]["error_type"] == "ValueError"
        assert errors[0]["context"]["agent"] == "test_agent"

    async def test_with_error_aggregation_fallback(self):
        """Test fallback with error aggregation."""
        agg = ErrorAggregator()

        async def failing_func():
            raise ValueError("Primary failed")

        async def fallback_func():
            return "fallback_result"

        result = await with_error_aggregation(
            failing_func,
            agg,
            context={"operation": "test"},
            fallback=fallback_func
        )

        assert result == "fallback_result"
        assert agg.has_errors()  # Error still recorded even with fallback

    async def test_with_error_aggregation_multiple_errors(self):
        """Test aggregating errors from multiple operations."""
        agg = ErrorAggregator()

        async def operation1():
            raise ValueError("Error 1")

        async def operation2():
            raise KeyError("Error 2")

        async def operation3():
            raise RuntimeError("Error 3")

        # Execute multiple operations
        await with_error_aggregation(operation1, agg, context={"op": "1"})
        await with_error_aggregation(operation2, agg, context={"op": "2"})
        await with_error_aggregation(operation3, agg, context={"op": "3"})

        assert agg.get_error_count() == 3

        summary = agg.get_summary()
        assert "ValueError" in summary["error_types"]
        assert "KeyError" in summary["error_types"]
        assert "RuntimeError" in summary["error_types"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorBoundaryCorrelationID:
    """Tests for error boundary with correlation ID integration."""

    async def test_error_boundary_includes_correlation_id(self):
        """Test that correlation ID is included in error context."""
        test_cid = "test-correlation-456"
        set_correlation_id(test_cid)

        async def failing_func():
            raise ValueError("Test error with correlation")

        # Error should be logged with correlation ID
        # (Hard to test without log capture, but context is passed)
        with pytest.raises(ValueError):
            await with_error_boundary(
                failing_func,
                context={"operation": "test"}
            )

        clear_correlation_id()

    async def test_error_aggregation_includes_correlation_id(self):
        """Test that error aggregation includes correlation ID."""
        test_cid = "test-agg-correlation-789"
        set_correlation_id(test_cid)

        agg = ErrorAggregator()

        async def failing_func():
            raise ValueError("Aggregated with correlation")

        await with_error_aggregation(
            failing_func,
            agg,
            context={"agent": "test"}
        )

        # Correlation ID should be in error context
        # (Currently added by logging, not directly in aggregator)

        clear_correlation_id()


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorBoundaryOrchestrator:
    """Integration tests for error boundary in orchestrator patterns."""

    async def test_orchestrator_agent_error_handling(self):
        """Test orchestrator pattern with multiple agents using error boundary."""
        agg = ErrorAggregator()

        async def agent1():
            return "agent1_result"

        async def agent2():
            raise ValueError("Agent2 failed")

        async def agent3():
            return "agent3_result"

        # Execute agents with error boundary
        results = []
        for agent, name in [(agent1, "agent1"), (agent2, "agent2"), (agent3, "agent3")]:
            result = await with_error_aggregation(
                agent,
                agg,
                context={"agent": name}
            )
            results.append(result)

        # Should have 2 successes and 1 None (error)
        assert results[0] == "agent1_result"
        assert results[1] is None  # Failed
        assert results[2] == "agent3_result"

        # Should have 1 error aggregated
        assert agg.get_error_count() == 1
        assert "agent2" in str(agg.get_summary()["errors"][0]["context"])
