"""
Circuit Breaker Tests

Tests for circuit_breaker.py with state machine validation.
Created: 2026-02-27 (Phase 1, Task 3.2)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerOpenError,
    CircuitBreakerManager,
    circuit_breaker_manager
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestCircuitBreaker:
    """Tests for CircuitBreaker state machine."""

    async def test_circuit_breaker_closed_state_success(self):
        """Test that successful calls in CLOSED state work normally."""
        cb = CircuitBreaker(failure_threshold=3, name="test")
        mock_func = AsyncMock(return_value="success")

        result = await cb.call(mock_func, "arg1")

        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert mock_func.call_count == 1

    async def test_circuit_breaker_opens_after_threshold(self):
        """Test that circuit opens after failure_threshold is reached."""
        cb = CircuitBreaker(failure_threshold=3, name="test")
        mock_func = AsyncMock(side_effect=ValueError("Failure"))

        # First 3 failures should open circuit
        for i in range(3):
            with pytest.raises(ValueError):
                await cb.call(mock_func)

        assert cb.state == CircuitBreakerState.OPEN
        assert mock_func.call_count == 3

    async def test_circuit_breaker_rejects_calls_when_open(self):
        """Test that calls are rejected immediately when circuit is OPEN."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, name="test")
        mock_func = AsyncMock(side_effect=ValueError("Failure"))

        # Open the circuit
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(mock_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Next call should be rejected immediately without calling func
        call_count_before = mock_func.call_count
        with pytest.raises(CircuitBreakerOpenError, match="is OPEN"):
            await cb.call(mock_func)

        assert mock_func.call_count == call_count_before  # Not called

    async def test_circuit_breaker_half_open_transition(self):
        """Test transition from OPEN to HALF_OPEN after recovery timeout."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,  # Short timeout for testing
            half_open_max_calls=3,
            name="test"
        )
        mock_func = AsyncMock(side_effect=ValueError("Failure"))

        # Open the circuit
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(mock_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Next call should transition to HALF_OPEN (and fail)
        with pytest.raises(ValueError):
            await cb.call(mock_func)

        assert cb.state == CircuitBreakerState.OPEN  # Failed in HALF_OPEN, back to OPEN

    async def test_circuit_breaker_half_open_success_closes(self):
        """Test that success in HALF_OPEN closes the circuit."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.1,
            name="test"
        )

        # Open the circuit
        failing_func = AsyncMock(side_effect=ValueError("Failure"))
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Successful call in HALF_OPEN should close circuit
        success_func = AsyncMock(return_value="success")
        result = await cb.call(success_func)

        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_circuit_breaker_metrics(self):
        """Test that circuit breaker tracks metrics correctly."""
        cb = CircuitBreaker(failure_threshold=3, name="test")

        # Successful call
        success_func = AsyncMock(return_value="ok")
        await cb.call(success_func)

        metrics = cb.metrics
        assert metrics["state"] == "CLOSED"
        assert metrics["success_count"] == 1
        assert metrics["failure_count"] == 0
        assert metrics["total_calls"] == 1

        # Failed call
        failing_func = AsyncMock(side_effect=ValueError("Fail"))
        with pytest.raises(ValueError):
            await cb.call(failing_func)

        metrics = cb.metrics
        assert metrics["failure_count"] == 1
        assert metrics["total_calls"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestCircuitBreakerManager:
    """Tests for CircuitBreakerManager registry."""

    async def test_manager_creates_named_breakers(self):
        """Test that manager creates and caches named circuit breakers."""
        manager = CircuitBreakerManager()

        breaker1 = manager.get_breaker("service1")
        breaker2 = manager.get_breaker("service1")
        breaker3 = manager.get_breaker("service2")

        assert breaker1 is breaker2  # Same instance
        assert breaker1 is not breaker3  # Different service

    async def test_manager_call_wrapper(self):
        """Test that manager.call() wraps function with named breaker."""
        manager = CircuitBreakerManager()
        mock_func = AsyncMock(return_value="success")

        result = await manager.call("test-service", mock_func, "arg1")

        assert result == "success"
        assert mock_func.call_count == 1

    async def test_manager_is_open_check(self):
        """Test that manager can check if named circuit is open."""
        manager = CircuitBreakerManager()

        # Initially closed
        assert not manager.is_open("test-service")

        # Open the circuit
        failing_func = AsyncMock(side_effect=ValueError("Fail"))
        for i in range(5):  # Default threshold is 5
            try:
                await manager.call("test-service", failing_func)
            except ValueError:
                pass

        assert manager.is_open("test-service")


@pytest.mark.unit
def test_module_singleton_exists():
    """Test that module-level singleton manager exists."""
    assert circuit_breaker_manager is not None
    assert isinstance(circuit_breaker_manager, CircuitBreakerManager)
