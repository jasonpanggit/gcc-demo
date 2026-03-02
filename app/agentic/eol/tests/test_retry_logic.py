"""
Retry Logic Tests

Tests for retry.py utility functions with exponential backoff and jitter.
Created: 2026-02-27 (Phase 1, Task 3.2)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.retry import retry_async, retry_sync, RetryStats, TryAgain


@pytest.mark.unit
@pytest.mark.asyncio
class TestRetryAsync:
    """Tests for retry_async decorator."""

    async def test_retry_async_success_first_try(self):
        """Test that successful call on first attempt returns immediately."""
        mock_func = AsyncMock(return_value="success")
        decorated = retry_async(retries=3)(mock_func)

        result = await decorated("arg1", kwarg="value")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with("arg1", kwarg="value")

    async def test_retry_async_success_after_failures(self):
        """Test that function retries and succeeds on second attempt."""
        mock_func = AsyncMock(side_effect=[
            Exception("First failure"),
            "success"
        ])
        decorated = retry_async(retries=3, initial_delay=0.01)(mock_func)

        result = await decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    async def test_retry_async_exhausted_retries(self):
        """Test that function raises exception after exhausting retries."""
        mock_func = AsyncMock(side_effect=ValueError("Always fails"))
        decorated = retry_async(retries=3, initial_delay=0.01)(mock_func)

        with pytest.raises(ValueError, match="Always fails"):
            await decorated()

        assert mock_func.call_count == 3

    async def test_retry_async_exponential_backoff(self):
        """Test that retry delays increase exponentially."""
        mock_func = AsyncMock(side_effect=[
            Exception("Fail 1"),
            Exception("Fail 2"),
            "success"
        ])
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            backoff_factor=2.0,
            jitter=0.0  # Disable jitter for predictable timing
        )(mock_func)

        start_time = asyncio.get_event_loop().time()
        result = await decorated()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # Should wait ~0.01s then ~0.02s (total ~0.03s minimum)
        assert elapsed >= 0.03

    async def test_retry_async_specific_exceptions(self):
        """Test that retry only catches specified exceptions."""
        mock_func = AsyncMock(side_effect=TypeError("Not retryable"))
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            exceptions=(ValueError,)  # Only retry ValueError
        )(mock_func)

        with pytest.raises(TypeError, match="Not retryable"):
            await decorated()

        # Should fail immediately, not retry
        assert mock_func.call_count == 1

    async def test_retry_async_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        mock_func = AsyncMock(side_effect=[
            Exception("Fail 1"),
            Exception("Fail 2"),
            "success"
        ])
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            max_delay=0.015,  # Cap delay
            backoff_factor=10.0,  # Would exceed max without cap
            jitter=0.0
        )(mock_func)

        start_time = asyncio.get_event_loop().time()
        result = await decorated()
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # Should wait ~0.01s then capped at ~0.015s (total ~0.025s)
        assert elapsed < 0.05  # Much less than uncapped would be


@pytest.mark.unit
class TestRetrySync:
    """Tests for retry_sync decorator."""

    def test_retry_sync_success_first_try(self):
        """Test that successful call on first attempt returns immediately."""
        mock_func = MagicMock(return_value="success")
        decorated = retry_sync(retries=3)(mock_func)

        result = decorated("arg1", kwarg="value")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with("arg1", kwarg="value")

    def test_retry_sync_success_after_failures(self):
        """Test that function retries and succeeds on second attempt."""
        mock_func = MagicMock(side_effect=[
            Exception("First failure"),
            "success"
        ])
        decorated = retry_sync(retries=3, initial_delay=0.01)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_retry_sync_exhausted_retries(self):
        """Test that function raises exception after exhausting retries."""
        mock_func = MagicMock(side_effect=ValueError("Always fails"))
        decorated = retry_sync(retries=3, initial_delay=0.01)(mock_func)

        with pytest.raises(ValueError, match="Always fails"):
            decorated()

        assert mock_func.call_count == 3

    def test_retry_sync_specific_exceptions(self):
        """Test that retry only catches specified exceptions."""
        mock_func = MagicMock(side_effect=TypeError("Not retryable"))
        decorated = retry_sync(
            retries=3,
            initial_delay=0.01,
            exceptions=(ValueError,)  # Only retry ValueError
        )(mock_func)

        with pytest.raises(TypeError, match="Not retryable"):
            decorated()

        # Should fail immediately, not retry
        assert mock_func.call_count == 1


# ---------------------------------------------------------------------------
# Phase 4 — Plan 04-01: New tests covering RetryStats, on_retry, TryAgain,
# retry_on_result, and backward-compat verification.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestRetryStats:
    """Tests for RetryStats tracking object."""

    async def test_retry_stats_tracks_attempts(self):
        """RetryStats.attempts increments on each attempt; success=True on final pass."""
        stats = RetryStats()
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        decorated = retry_async(retries=5, initial_delay=0.01, stats=stats)(flaky)
        result = await decorated()

        assert result == "ok"
        assert stats.attempts == 3
        assert stats.success is True

    async def test_retry_stats_tracks_delay(self):
        """RetryStats.total_delay accumulates sleep durations across retries."""
        stats = RetryStats()

        mock_func = AsyncMock(side_effect=[
            ValueError("fail 1"),
            ValueError("fail 2"),
            "done",
        ])
        decorated = retry_async(
            retries=5,
            initial_delay=0.01,
            jitter=0.0,
            stats=stats,
        )(mock_func)

        await decorated()

        # Two sleeps happened: after attempt 1 and after attempt 2
        # With jitter=0.0 the sleep_for = min(delay, max_delay)
        # delay starts at 0.01, grows to 0.02 → total ~ 0.03
        assert stats.total_delay > 0.0
        assert stats.attempts == 3
        assert stats.success is True

    async def test_retry_stats_last_exception(self):
        """RetryStats.last_exception is set to the most recent exception caught."""
        stats = RetryStats()

        exc_to_raise = ValueError("captured")
        mock_func = AsyncMock(side_effect=[exc_to_raise, "ok"])
        decorated = retry_async(retries=3, initial_delay=0.01, stats=stats)(mock_func)

        await decorated()

        assert stats.last_exception is exc_to_raise


@pytest.mark.unit
@pytest.mark.asyncio
class TestOnRetryCallback:
    """Tests for on_retry observability callback."""

    async def test_on_retry_callback_called(self):
        """on_retry called with (attempt, exc, delay) on each retry."""
        calls = []

        def record_retry(attempt, exc, delay):
            calls.append((attempt, exc, delay))

        exc1 = ValueError("boom")
        mock_func = AsyncMock(side_effect=[exc1, "ok"])
        decorated = retry_async(
            retries=3,
            initial_delay=0.01,
            jitter=0.0,
            on_retry=record_retry,
        )(mock_func)

        await decorated()

        assert len(calls) == 1
        attempt, exc, delay = calls[0]
        assert attempt == 1
        assert exc is exc1
        assert delay > 0.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestRetryOnResult:
    """Tests for retry_on_result predicate."""

    async def test_retry_on_result_retries_bad_result(self):
        """When predicate returns True, retry continues; False → immediate return."""
        responses = [None, None, "ready"]
        idx = 0

        async def poll():
            nonlocal idx
            value = responses[idx]
            idx += 1
            return value

        decorated = retry_async(
            retries=5,
            initial_delay=0.01,
            jitter=0.0,
            retry_on_result=lambda r: r is None,
        )(poll)

        result = await decorated()

        assert result == "ready"
        assert idx == 3  # polled 3 times


@pytest.mark.unit
@pytest.mark.asyncio
class TestTryAgain:
    """Tests for TryAgain sentinel exception."""

    async def test_try_again_forces_retry(self):
        """Raising TryAgain inside decorated function triggers retry without setting last_exception."""
        stats = RetryStats()
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TryAgain()
            return "done"

        decorated = retry_async(
            retries=5,
            initial_delay=0.01,
            exceptions=(ValueError,),  # TryAgain is NOT in exceptions list
            stats=stats,
        )(flaky)

        result = await decorated()

        assert result == "done"
        assert call_count == 3
        # TryAgain must NOT be recorded as last_exception
        assert stats.last_exception is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestBackwardCompat:
    """Ensure existing call sites with no new params work identically."""

    async def test_backward_compat_no_new_params(self):
        """Existing @retry_async(retries=3) call with no new params still works."""
        mock_func = AsyncMock(side_effect=[Exception("transient"), "ok"])
        decorated = retry_async(retries=3, initial_delay=0.01)(mock_func)

        result = await decorated()

        assert result == "ok"
        assert mock_func.call_count == 2
