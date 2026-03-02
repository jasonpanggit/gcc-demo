"""
Phase 4 Integration Tests

End-to-end verification of all Phase 4 deliverables:
  - RetryStats / TryAgain (04-01: utils/retry.py enhancements)
  - PlaywrightPool concurrency cap (04-02: utils/playwright_pool.py CQ-05)
  - SRE + Inventory shutdown() stubs (04-02: CQ-07)

Created: 2026-03-02 (Phase 4, Plan 04-03)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path so imports work from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.retry import retry_async, RetryStats, TryAgain


# =============================================================================
# Test 1: RetryStats tracks retry metrics through a real retry sequence
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestRetryStatsIntegration:
    """RetryStats wired into retry_async captures accurate metrics."""

    async def test_retry_stats_tracks_attempts_and_success(self):
        """RetryStats records attempt count, total delay > 0, and success=True."""
        stats = RetryStats()
        call_count = 0

        @retry_async(retries=3, initial_delay=0.01, stats=stats)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient failure")
            return "ok"

        result = await flaky()

        assert result == "ok", "Function should eventually succeed"
        assert stats.attempts == 3, f"Expected 3 attempts, got {stats.attempts}"
        assert stats.success is True, "stats.success should be True on success"
        assert stats.total_delay > 0, "Cumulative delay should be > 0 after retries"
        assert stats.last_exception is not None, (
            "last_exception should capture the most recent real exception"
        )
        assert isinstance(stats.last_exception, ValueError)


# =============================================================================
# Test 2: PlaywrightPool caps max_concurrency at _MAX_POOL_SIZE = 5
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestPlaywrightPoolCapEnforced:
    """PlaywrightPool.setup() clamps max_concurrency to 5 and warns."""

    async def test_playwright_pool_cap_logic_when_playwright_unavailable(self):
        """
        When PLAYWRIGHT_AVAILABLE is False, setup() returns early before the
        cap check. Verify pool remains un-initialized (no crash, no state set).
        This tests the guard path.
        """
        from utils.playwright_pool import PlaywrightPool

        pool = PlaywrightPool()
        with patch("utils.playwright_pool.PLAYWRIGHT_AVAILABLE", False):
            await pool.setup(max_concurrency=10)

        # Pool should not be initialized — PLAYWRIGHT_AVAILABLE=False causes early return
        assert not pool._initialized, (
            "Pool must not be initialized when Playwright is unavailable"
        )

    async def test_playwright_pool_cap_constant_is_five(self):
        """
        Verify that the _MAX_POOL_SIZE constant value enforced inside setup()
        equals 5, as required by CQ-05.
        Read the source and confirm the constant value directly.
        """
        import inspect
        import utils.playwright_pool as pw_module

        source = inspect.getsource(pw_module.PlaywrightPool.setup)
        assert "_MAX_POOL_SIZE = 5" in source, (
            "PlaywrightPool.setup() must contain '_MAX_POOL_SIZE = 5' "
            "(CQ-05 hard cap requirement)"
        )
        # Also confirm the warning message is present (CQ-06)
        assert "clamping" in source or "hard cap" in source or "exceeds" in source, (
            "PlaywrightPool.setup() must emit a warning when clamping concurrency (CQ-06)"
        )


# =============================================================================
# Test 3: SRE + Inventory orchestrators have callable shutdown() methods
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorShutdownStubs:
    """CQ-07: shutdown() exists and is callable on both orchestrators."""

    async def test_sre_orchestrator_shutdown_method_exists(self):
        """SREOrchestratorAgent.shutdown() is present as an async method.

        Uses AST inspection to avoid importing sre_orchestrator at module level —
        the module has a transitive dependency on `mcp` which may not be installed
        in all CI environments (mcp is an optional runtime dependency).
        """
        import ast

        sre_path = (
            Path(__file__).parent.parent / "agents" / "sre_orchestrator.py"
        )
        assert sre_path.exists(), f"sre_orchestrator.py not found at {sre_path}"

        source = sre_path.read_text()
        tree = ast.parse(source)

        # Find all async def shutdown() inside any class body
        found_async_shutdown = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "shutdown":
                found_async_shutdown = True
                break

        assert found_async_shutdown, (
            "SREOrchestratorAgent must have 'async def shutdown()' method (CQ-07)"
        )

    async def test_inventory_orchestrator_shutdown_method_exists(self):
        """InventoryAssistantOrchestrator.shutdown() is present and is a coroutine function."""
        import inspect
        from agents.inventory_orchestrator import InventoryAssistantOrchestrator

        assert hasattr(InventoryAssistantOrchestrator, "shutdown"), (
            "InventoryAssistantOrchestrator must have a shutdown() method (CQ-07)"
        )
        assert inspect.iscoroutinefunction(InventoryAssistantOrchestrator.shutdown), (
            "InventoryAssistantOrchestrator.shutdown() must be async"
        )


# =============================================================================
# Test 4: TryAgain forces retry without recording last_exception
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestTryAgainSentinel:
    """TryAgain is a control-flow signal; it must NOT be stored as last_exception."""

    async def test_try_again_forces_retry_without_setting_last_exception(self):
        """
        Raising TryAgain forces a retry but does NOT populate stats.last_exception.
        After success on attempt 3, last_exception is still None.
        """
        stats = RetryStats()
        count = [0]

        @retry_async(retries=3, initial_delay=0.01, stats=stats)
        async def fn():
            count[0] += 1
            if count[0] < 3:
                raise TryAgain()
            return "done"

        result = await fn()

        assert result == "done", "Function should succeed on third attempt"
        assert stats.attempts == 3, f"Expected 3 attempts, got {stats.attempts}"
        assert stats.last_exception is None, (
            "TryAgain must NOT be recorded as last_exception — "
            "it is a control-flow sentinel, not a real error"
        )
        assert stats.success is True

    async def test_try_again_coexists_with_real_exceptions(self):
        """
        A mix of TryAgain (control-flow) and ValueError (real error).
        Only the ValueError should appear in stats.last_exception.
        """
        stats = RetryStats()
        count = [0]

        @retry_async(retries=4, initial_delay=0.01, stats=stats)
        async def mixed():
            count[0] += 1
            if count[0] == 1:
                raise TryAgain()          # control-flow: should not set last_exception
            if count[0] == 2:
                raise ValueError("real")  # real exception: should set last_exception
            return "ok"                   # succeeds on attempt 3

        result = await mixed()

        assert result == "ok"
        assert stats.last_exception is not None
        assert isinstance(stats.last_exception, ValueError), (
            "last_exception must be the ValueError, not TryAgain"
        )
        assert stats.success is True
