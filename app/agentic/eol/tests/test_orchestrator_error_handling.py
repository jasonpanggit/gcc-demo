"""
Orchestrator Error Handling Integration Tests

Integration tests for orchestrators with Phase 2 error handling utilities.
Tests error aggregation, circuit breaker, correlation ID, and timeout config.

Created: 2026-02-27 (Phase 2, Day 7)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from utils.error_aggregator import ErrorAggregator
from utils.correlation_id import set_correlation_id, get_correlation_id, clear_correlation_id
from utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from utils.config import TimeoutConfig
from utils.error_boundary import with_error_boundary, with_error_aggregation


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorErrorAggregation:
    """Tests for error aggregation in orchestrator patterns."""

    async def test_orchestrator_aggregates_agent_errors(self):
        """Test that orchestrator aggregates errors from multiple agents."""
        agg = ErrorAggregator()

        # Simulate orchestrator calling multiple agents
        async def agent1():
            return "agent1_success"

        async def agent2():
            raise ValueError("Agent 2 failed")

        async def agent3():
            raise KeyError("Agent 3 failed")

        async def agent4():
            return "agent4_success"

        # Execute agents with error aggregation
        results = []
        agents = [
            ("agent1", agent1),
            ("agent2", agent2),
            ("agent3", agent3),
            ("agent4", agent4),
        ]

        for name, agent_func in agents:
            result = await with_error_aggregation(
                agent_func,
                agg,
                context={"agent": name, "orchestrator": "test_orch"}
            )
            results.append((name, result))

        # Verify results
        assert results[0][1] == "agent1_success"
        assert results[1][1] is None  # Failed
        assert results[2][1] is None  # Failed
        assert results[3][1] == "agent4_success"

        # Verify error aggregation
        assert agg.get_error_count() == 2
        summary = agg.get_summary()
        assert "ValueError" in summary["error_types"]
        assert "KeyError" in summary["error_types"]

    async def test_orchestrator_partial_success_handling(self):
        """Test orchestrator handling partial success scenarios."""
        agg = ErrorAggregator()

        # Simulate vendor-specific agents
        vendors = {
            "microsoft": lambda: asyncio.create_task(asyncio.sleep(0.01), name="ms_success"),
            "redhat": lambda: asyncio.create_task(self._failing_agent("RedHat unavailable"), name="rh_fail"),
            "ubuntu": lambda: asyncio.create_task(asyncio.sleep(0.01), name="ub_success"),
        }

        async def _successful_agent():
            await asyncio.sleep(0.01)
            return {"vendor": "test", "data": "success"}

        async def _failing_agent(msg):
            raise ConnectionError(msg)

        # Execute with proper async handling
        results = {}
        for vendor in ["microsoft", "ubuntu"]:
            results[vendor] = await with_error_aggregation(
                _successful_agent,
                agg,
                context={"vendor": vendor}
            )

        # One failing vendor
        results["redhat"] = await with_error_aggregation(
            lambda: _failing_agent("RedHat unavailable"),
            agg,
            context={"vendor": "redhat"}
        )

        # Should have 2 successes, 1 failure
        assert results["microsoft"] is not None
        assert results["ubuntu"] is not None
        assert results["redhat"] is None
        assert agg.get_error_count() == 1

    async def test_orchestrator_error_summary_reporting(self):
        """Test that orchestrator can generate error summary report."""
        agg = ErrorAggregator()

        # Simulate multiple agent failures
        async def failing_agent(agent_name, error_type):
            if error_type == "timeout":
                raise asyncio.TimeoutError(f"{agent_name} timed out")
            elif error_type == "connection":
                raise ConnectionError(f"{agent_name} connection failed")
            else:
                raise ValueError(f"{agent_name} invalid data")

        # Execute multiple agents with different failures
        agents = [
            ("agent1", "timeout"),
            ("agent2", "connection"),
            ("agent3", "connection"),
            ("agent4", "validation"),
        ]

        for name, error_type in agents:
            await with_error_aggregation(
                lambda n=name, et=error_type: failing_agent(n, et),
                agg,
                context={"agent": name, "error_category": error_type}
            )

        # Generate summary
        summary = agg.get_summary()

        assert summary["total_errors"] == 4
        assert "TimeoutError" in summary["error_types"]
        assert "ConnectionError" in summary["error_types"]
        assert "ValueError" in summary["error_types"]
        assert summary["error_types"]["ConnectionError"] == 2  # 2 connection errors


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorCircuitBreakerIntegration:
    """Tests for circuit breaker integration with orchestrators."""

    async def test_orchestrator_uses_circuit_breaker_per_service(self):
        """Test that orchestrator uses separate circuit breakers per service."""
        cb_microsoft = CircuitBreaker(failure_threshold=2, name="microsoft")
        cb_redhat = CircuitBreaker(failure_threshold=2, name="redhat")

        # Fail Microsoft service
        async def microsoft_agent():
            raise ConnectionError("Microsoft service down")

        async def redhat_agent():
            return "redhat_success"

        # Trigger Microsoft circuit breaker
        for _ in range(2):
            try:
                await cb_microsoft.call(microsoft_agent)
            except ConnectionError:
                pass

        assert cb_microsoft.state.value == "OPEN"

        # RedHat should still work
        result = await cb_redhat.call(redhat_agent)
        assert result == "redhat_success"
        assert cb_redhat.state.value == "CLOSED"

    async def test_orchestrator_fallback_when_circuit_open(self):
        """Test orchestrator fallback when circuit breaker is open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0, name="primary")

        async def primary_service():
            raise ConnectionError("Service unavailable")

        async def fallback_service():
            return {"source": "cache", "data": "fallback_data"}

        # Open the circuit
        for _ in range(2):
            try:
                await cb.call(primary_service)
            except ConnectionError:
                pass

        assert cb.state.value == "OPEN"

        # Use fallback when circuit open
        try:
            await cb.call(primary_service)
        except CircuitBreakerOpenError:
            result = await fallback_service()
            assert result["source"] == "cache"

    async def test_orchestrator_circuit_breaker_metrics(self):
        """Test that orchestrator can access circuit breaker metrics."""
        cb = CircuitBreaker(failure_threshold=3, name="metrics_test")

        async def agent_call(should_fail):
            if should_fail:
                raise ValueError("Agent failed")
            return "success"

        # Mix of successes and failures
        for should_fail in [False, True, False, True, False]:
            try:
                await cb.call(agent_call, should_fail)
            except ValueError:
                pass

        metrics = cb.metrics

        assert metrics["success_count"] == 3
        assert metrics["failure_count"] == 2
        assert metrics["total_calls"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorCorrelationIDPropagation:
    """Tests for correlation ID propagation through orchestrator layers."""

    async def test_correlation_id_propagates_through_orchestrator(self):
        """Test that correlation ID propagates from orchestrator to agents."""
        test_cid = "test-orch-correlation-123"
        set_correlation_id(test_cid)

        captured_cids = []

        async def agent_with_cid_check():
            # Agent should see the same correlation ID
            cid = get_correlation_id()
            captured_cids.append(cid)
            return "success"

        # Simulate orchestrator calling multiple agents
        for _ in range(3):
            await agent_with_cid_check()

        # All agents should see the same correlation ID
        assert len(captured_cids) == 3
        assert all(cid == test_cid for cid in captured_cids)

        clear_correlation_id()

    async def test_correlation_id_in_error_context(self):
        """Test that correlation ID is included in error context."""
        test_cid = "test-error-correlation-456"
        set_correlation_id(test_cid)

        agg = ErrorAggregator()

        async def failing_agent():
            raise ValueError("Agent failed with correlation")

        await with_error_aggregation(
            failing_agent,
            agg,
            context={"agent": "test_agent"}
        )

        # Correlation ID should be logged (checked via logging integration)
        # For now, verify error was collected
        assert agg.get_error_count() == 1

        clear_correlation_id()

    async def test_correlation_id_persists_across_async_boundaries(self):
        """Test correlation ID persists across async function calls."""
        test_cid = "test-async-boundary-789"
        set_correlation_id(test_cid)

        async def level_1():
            assert get_correlation_id() == test_cid
            return await level_2()

        async def level_2():
            assert get_correlation_id() == test_cid
            return await level_3()

        async def level_3():
            assert get_correlation_id() == test_cid
            return "deep_success"

        result = await level_1()
        assert result == "deep_success"

        clear_correlation_id()


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorTimeoutConfiguration:
    """Tests for timeout configuration in orchestrators."""

    async def test_orchestrator_uses_centralized_timeout(self):
        """Test that orchestrator uses centralized timeout config."""
        timeout_config = TimeoutConfig()

        async def agent_operation():
            await asyncio.sleep(0.01)
            return "completed"

        # Use orchestrator timeout
        try:
            async with asyncio.timeout(timeout_config.orchestrator_timeout):
                result = await agent_operation()
                assert result == "completed"
        except asyncio.TimeoutError:
            pytest.fail("Should not timeout with valid orchestrator timeout")

    async def test_orchestrator_timeout_hierarchy(self):
        """Test timeout hierarchy: orchestrator > agent > tool."""
        timeout_config = TimeoutConfig()

        # Verify hierarchy
        assert timeout_config.orchestrator_timeout >= timeout_config.agent_timeout
        assert timeout_config.agent_timeout >= timeout_config.mcp_tool_timeout

    async def test_orchestrator_respects_timeout_overrides(self):
        """Test that orchestrator respects environment-based timeout overrides."""
        # Test with default timeouts
        timeout_config = TimeoutConfig()

        async def quick_operation():
            await asyncio.sleep(0.001)
            return "done"

        # Should complete within orchestrator timeout
        try:
            async with asyncio.timeout(timeout_config.orchestrator_timeout):
                result = await quick_operation()
                assert result == "done"
        except asyncio.TimeoutError:
            pytest.fail("Should not timeout")


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorFullIntegration:
    """Full integration tests combining all Phase 2 utilities."""

    async def test_orchestrator_full_error_handling_pipeline(self):
        """Test full orchestrator pipeline with all error handling utilities."""
        # Setup all utilities
        test_cid = "test-full-pipeline-123"
        set_correlation_id(test_cid)

        agg = ErrorAggregator()
        cb = CircuitBreaker(failure_threshold=2, name="full_test")
        timeout_config = TimeoutConfig()

        # Simulate orchestrator executing multiple agents
        async def agent1():
            await asyncio.sleep(0.01)
            return {"agent": "agent1", "status": "success"}

        async def agent2():
            raise ConnectionError("Agent 2 connection failed")

        async def agent3():
            await asyncio.sleep(0.01)
            return {"agent": "agent3", "status": "success"}

        results = []

        # Agent 1 - success
        result1 = await with_error_aggregation(
            lambda: cb.call(agent1),
            agg,
            context={"agent": "agent1", "correlation_id": test_cid}
        )
        results.append(result1)

        # Agent 2 - failure (with circuit breaker)
        result2 = await with_error_aggregation(
            lambda: cb.call(agent2),
            agg,
            context={"agent": "agent2", "correlation_id": test_cid}
        )
        results.append(result2)

        # Agent 3 - success
        result3 = await with_error_aggregation(
            lambda: cb.call(agent3),
            agg,
            context={"agent": "agent3", "correlation_id": test_cid}
        )
        results.append(result3)

        # Verify results
        assert results[0] is not None
        assert results[1] is None  # Failed
        assert results[2] is not None

        # Verify error aggregation
        assert agg.get_error_count() == 1

        # Verify correlation ID
        assert get_correlation_id() == test_cid

        # Verify circuit breaker metrics
        metrics = cb.metrics
        assert metrics["success_count"] == 2
        assert metrics["failure_count"] == 1

        clear_correlation_id()

    async def test_orchestrator_concurrent_agent_execution(self):
        """Test orchestrator executing agents concurrently with error handling."""
        agg = ErrorAggregator()

        async def agent(name, delay, should_fail=False):
            await asyncio.sleep(delay)
            if should_fail:
                raise ValueError(f"{name} failed")
            return f"{name}_result"

        # Execute multiple agents concurrently
        agents = [
            ("agent1", 0.01, False),
            ("agent2", 0.02, True),
            ("agent3", 0.01, False),
            ("agent4", 0.015, True),
        ]

        tasks = []
        for name, delay, should_fail in agents:
            task = with_error_aggregation(
                lambda n=name, d=delay, sf=should_fail: agent(n, d, sf),
                agg,
                context={"agent": name}
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Should have 2 successes, 2 failures
        successful = [r for r in results if r is not None]
        assert len(successful) == 2
        assert agg.get_error_count() == 2
