"""
Phase 4 Integration Tests
=========================

End-to-end tests for the four Phase 4 deliverables:

  1. RetryStats tracks retry metrics across a flaky async function
  2. PlaywrightPool hard cap (≤5) is enforced without raising
  3. SREOrchestratorAgent.shutdown() method exists and completes cleanly
  4. TryAgain forces retry without polluting RetryStats.last_exception

No real Azure connections or browser instances are used.
All external dependencies are stubbed/mocked.

Markers: @pytest.mark.integration  (registered in pytest.ini)
"""
import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# Ensure app path is importable when running from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retry import retry_async, RetryStats, TryAgain


# ---------------------------------------------------------------------------
# Test 1: RetryStats tracks metrics over a flaky async function
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_retry_stats_integration():
    """RetryStats.attempts, .success, and .total_delay are populated correctly."""
    stats = RetryStats()
    call_count = 0

    @retry_async(retries=3, initial_delay=0.01, max_delay=0.05, stats=stats)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "ok"

    result = await flaky()

    assert result == "ok", f"Expected 'ok', got {result!r}"
    assert stats.attempts == 3, f"Expected 3 attempts, got {stats.attempts}"
    assert stats.success is True, "Expected stats.success to be True"
    assert stats.total_delay > 0, "Expected some delay to have accumulated"
    assert stats.last_exception is not None, "Expected last_exception to record transient ValueError"
    assert isinstance(stats.last_exception, ValueError)


# ---------------------------------------------------------------------------
# Test 2: PlaywrightPool hard cap is enforced (no raise; value clamped to 5)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_playwright_pool_cap_enforced():
    """PlaywrightPool.setup() clamps max_concurrency to _MAX_POOL_SIZE=5."""
    from utils.playwright_pool import PlaywrightPool

    pool = PlaywrightPool()

    # Patch PLAYWRIGHT_AVAILABLE=False so setup() bails before launching a browser,
    # but we can still verify the cap logic fires via the warning log.
    with patch("utils.playwright_pool.PLAYWRIGHT_AVAILABLE", False):
        # Should not raise even though concurrency=10 > cap
        await pool.setup(max_concurrency=10)

    # Pool is not initialised (playwright not available), but no exception was raised.
    assert pool._initialized is False, "Pool should not be initialised without playwright"

    # Verify cap logic directly: create a fresh pool and patch playwright to be available,
    # then intercept the semaphore creation to observe the clamped value.
    pool2 = PlaywrightPool()
    semaphore_values = []

    original_semaphore = asyncio.Semaphore

    def capturing_semaphore(n):
        semaphore_values.append(n)
        return original_semaphore(n)

    mock_playwright_ctx = MagicMock()
    mock_browser = AsyncMock()
    mock_playwright_instance = AsyncMock()
    mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright_ctx.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_playwright_ctx.__aexit__ = AsyncMock(return_value=None)

    async def mock_start():
        return mock_playwright_instance

    mock_ap = MagicMock()
    mock_ap.return_value.start = mock_start

    with patch("utils.playwright_pool.PLAYWRIGHT_AVAILABLE", True), \
         patch("utils.playwright_pool.async_playwright", mock_ap), \
         patch("asyncio.Semaphore", side_effect=capturing_semaphore):
        await pool2.setup(max_concurrency=10)

    assert semaphore_values, "Semaphore should have been created"
    assert semaphore_values[0] <= 5, (
        f"Semaphore was created with {semaphore_values[0]} — cap enforcement failed"
    )


# ---------------------------------------------------------------------------
# Test 3: SREOrchestratorAgent.shutdown() exists and completes without error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_sre_orchestrator_shutdown_noop():
    """SREOrchestratorAgent.shutdown() is a no-op stub that completes cleanly."""
    # SREOrchestratorAgent imports utils/sre_mcp_client which requires the `mcp`
    # package.  When `mcp` is not installed (local dev without full deps) we skip
    # rather than fail — consistent with existing SRE orchestrator test behaviour.
    mcp_mod = pytest.importorskip("mcp", reason="mcp package not installed; skipping SRE shutdown test")
    from agents.sre_orchestrator import SREOrchestratorAgent

    # Verify the method exists at the class level (contract check)
    assert hasattr(SREOrchestratorAgent, "shutdown"), (
        "SREOrchestratorAgent must have a shutdown() method (CQ-07 contract)"
    )
    assert asyncio.iscoroutinefunction(SREOrchestratorAgent.shutdown), (
        "shutdown() must be an async method"
    )

    # Call it on a minimal mock instance — does not need full SRE startup
    mock_instance = MagicMock(spec=SREOrchestratorAgent)
    # Bind the real shutdown coroutine to the mock instance
    await SREOrchestratorAgent.shutdown(mock_instance)


# ---------------------------------------------------------------------------
# Test 4: TryAgain forces retry without setting last_exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_try_again_forces_retry():
    """TryAgain is a control-flow sentinel — it must NOT set RetryStats.last_exception."""
    stats = RetryStats()
    count = [0]

    @retry_async(retries=3, initial_delay=0.01, max_delay=0.05, stats=stats)
    async def fn():
        count[0] += 1
        if count[0] < 3:
            raise TryAgain()
        return "done"

    result = await fn()

    assert result == "done", f"Expected 'done', got {result!r}"
    assert count[0] == 3, f"Expected 3 total calls, got {count[0]}"
    assert stats.last_exception is None, (
        "TryAgain must NOT set stats.last_exception — it is a control-flow signal, not an error"
    )
    assert stats.attempts == 3, f"Expected stats.attempts=3, got {stats.attempts}"
    assert stats.total_delay > 0, "Expected some delay to have accumulated during TryAgain retries"
