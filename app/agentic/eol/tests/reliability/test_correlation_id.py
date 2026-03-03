"""
Correlation ID Tests

Tests for correlation ID propagation utility.
Created: 2026-02-27 (Phase 1, Task 3.2)
Updated: 2026-02-27 (Phase 2, Day 4)
"""

import pytest
import asyncio
from utils.correlation_id import (
    generate_correlation_id,
    set_correlation_id,
    get_correlation_id,
    ensure_correlation_id,
    clear_correlation_id
)


@pytest.mark.unit
class TestCorrelationID:
    """Tests for correlation ID utility."""

    def test_correlation_id_generation(self):
        """Test generating unique correlation IDs."""
        cid1 = generate_correlation_id()
        cid2 = generate_correlation_id()

        # Should generate unique IDs
        assert cid1 != cid2
        # Should be valid UUID format
        assert len(cid1) == 36  # UUID4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert len(cid2) == 36

    @pytest.mark.asyncio
    async def test_correlation_id_context_propagation(self):
        """Test propagating correlation ID through async context."""
        # Clear any existing correlation ID
        clear_correlation_id()

        # Set a correlation ID
        test_cid = "test-correlation-123"
        set_correlation_id(test_cid)

        # Should be retrievable
        assert get_correlation_id() == test_cid

        # Should propagate through async function calls
        async def inner_function():
            return get_correlation_id()

        result = await inner_function()
        assert result == test_cid

        # Clean up
        clear_correlation_id()

    @pytest.mark.asyncio
    async def test_correlation_id_isolation_across_tasks(self):
        """Test that correlation IDs are isolated across different async tasks."""
        clear_correlation_id()

        results = []

        async def task_with_cid(cid: str):
            set_correlation_id(cid)
            await asyncio.sleep(0.01)  # Small delay to test isolation
            retrieved_cid = get_correlation_id()
            results.append((cid, retrieved_cid))

        # Run two tasks with different correlation IDs
        await asyncio.gather(
            task_with_cid("task-1-cid"),
            task_with_cid("task-2-cid")
        )

        # Each task should have its own correlation ID
        assert len(results) == 2
        for original, retrieved in results:
            assert original == retrieved

    def test_correlation_id_ensure_function(self):
        """Test ensure_correlation_id generates if missing, returns existing if present."""
        clear_correlation_id()

        # Should generate a new one if none exists
        cid1 = ensure_correlation_id()
        assert cid1 is not None
        assert len(cid1) == 36

        # Should return the same one on subsequent calls
        cid2 = ensure_correlation_id()
        assert cid1 == cid2

        # Clean up
        clear_correlation_id()

    def test_correlation_id_clear(self):
        """Test clearing correlation ID."""
        # Set a correlation ID
        set_correlation_id("test-cid-clear")
        assert get_correlation_id() == "test-cid-clear"

        # Clear it
        clear_correlation_id()
        assert get_correlation_id() is None

    @pytest.mark.asyncio
    async def test_correlation_id_across_nested_async_calls(self):
        """Test correlation ID flows through nested async function calls."""
        clear_correlation_id()

        test_cid = "nested-test-123"
        set_correlation_id(test_cid)

        async def level_1():
            assert get_correlation_id() == test_cid
            return await level_2()

        async def level_2():
            assert get_correlation_id() == test_cid
            return await level_3()

        async def level_3():
            return get_correlation_id()

        result = await level_1()
        assert result == test_cid

        # Clean up
        clear_correlation_id()
