"""Unit tests for fire-and-forget task-set pattern in orchestrators.

Tests cover:
- Task lifecycle (create → track → complete → remove)
- GC prevention via set membership
- Exception handling (logged, not raised)
- shutdown() cancellation behavior
- Scale test (100 tasks without GC)

Phase 03, Plan 03 — fire-and-forget pattern.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _noop():
    """Coroutine that completes immediately."""
    pass


async def _slow(delay: float = 0.05):
    """Coroutine that sleeps briefly."""
    await asyncio.sleep(delay)


async def _raises(exc: Exception):
    """Coroutine that raises an exception."""
    raise exc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator():
    """Return a real EOLOrchestratorAgent with mock agents (no network I/O)."""
    from agents.eol_orchestrator import EOLOrchestratorAgent

    # Provide empty agents dict so we own no real resources
    orch = EOLOrchestratorAgent(agents={}, close_provided_agents=False)
    return orch


# ---------------------------------------------------------------------------
# Test 1: _spawn_background creates a task and adds it to _background_tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_spawn_background_adds_task_to_set(orchestrator):
    """_spawn_background(coro) must add the returned task to _background_tasks."""
    # Use a slow coroutine so the task is still running when we check the set
    task = orchestrator._spawn_background(_slow(0.1), name="test_task")

    assert task in orchestrator._background_tasks, (
        "_spawn_background should add the task to _background_tasks immediately"
    )

    # Clean up — cancel before the test exits
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Test 2: Task is removed from set when it completes normally
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_completed_task_removed_from_set(orchestrator):
    """After a task completes, the discard callback must remove it from _background_tasks."""
    task = orchestrator._spawn_background(_noop(), name="noop_task")

    # Wait for the task to finish (yield control a few times)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert task not in orchestrator._background_tasks, (
        "Completed task should be discarded from _background_tasks"
    )


# ---------------------------------------------------------------------------
# Test 3: Exception is logged, not re-raised; task removed from set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_exception_logged_not_raised(orchestrator):
    """When background task raises, exception is logged at DEBUG and task is removed."""
    with patch("agents.eol_orchestrator.logger") as mock_logger:
        task = orchestrator._spawn_background(
            _raises(ValueError("boom")), name="failing_task"
        )

        # Let the task run and the callback fire
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Task must be removed from set despite exception
        assert task not in orchestrator._background_tasks, (
            "Failed task should be removed from _background_tasks"
        )

        # Exception should be logged at DEBUG level (not ERROR/WARNING)
        mock_logger.debug.assert_called()
        debug_calls = str(mock_logger.debug.call_args_list)
        assert "boom" in debug_calls or "ValueError" in debug_calls, (
            "Exception details should be logged at DEBUG"
        )


# ---------------------------------------------------------------------------
# Test 4: shutdown() cancels all pending background tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_shutdown_cancels_pending_tasks(orchestrator):
    """shutdown() must cancel all tasks currently in _background_tasks."""
    # Spawn tasks that block long enough to still be pending at shutdown
    tasks = [
        orchestrator._spawn_background(_slow(10.0), name=f"long_task_{i}")
        for i in range(3)
    ]

    assert len(orchestrator._background_tasks) == 3

    await orchestrator.shutdown()

    # All tasks must have been cancelled
    for task in tasks:
        assert task.cancelled() or task.done(), (
            "shutdown() must cancel all pending background tasks"
        )


# ---------------------------------------------------------------------------
# Test 5: After shutdown(), _background_tasks is empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_shutdown_empties_background_tasks(orchestrator):
    """After shutdown(), the _background_tasks set must be empty."""
    for i in range(5):
        orchestrator._spawn_background(_slow(10.0), name=f"task_{i}")

    assert len(orchestrator._background_tasks) == 5

    await orchestrator.shutdown()

    assert len(orchestrator._background_tasks) == 0, (
        "_background_tasks must be empty after shutdown()"
    )


# ---------------------------------------------------------------------------
# Test 6: 100 tasks tracked without GC (set prevents garbage collection)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_100_tasks_tracked_without_gc(orchestrator):
    """Spawning 100 tasks — all must be in _background_tasks until completion.

    This verifies the GC-prevention guarantee: without the set, asyncio tasks
    are weakly referenced and can be garbage-collected before completion.
    """
    N = 100
    # Use a small delay so tasks are still running when we check
    tasks = [
        orchestrator._spawn_background(_slow(0.5), name=f"scale_task_{i}")
        for i in range(N)
    ]

    # All N tasks must be tracked (not GC'd)
    assert len(orchestrator._background_tasks) == N, (
        f"Expected {N} tasks in _background_tasks, got {len(orchestrator._background_tasks)}"
    )
    assert all(t in orchestrator._background_tasks for t in tasks), (
        "Every spawned task must be in _background_tasks"
    )

    # Clean up — cancel all before test exits
    await orchestrator.shutdown()
