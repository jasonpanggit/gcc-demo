"""
Tests for utils/retry.py — retry_async, retry_sync, RetryStats, TryAgain.

Split into two sections:
  1. Original 10 tests (unchanged) — backward-compat and core behaviour
  2. 6 new tests covering: RetryStats tracking, on_retry callback,
     retry_on_result predicate, TryAgain sentinel, and backward-compat guard.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

# Ensure the app root is on the path when running from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retry import retry_async, retry_sync, RetryStats, TryAgain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine in a new event loop (compatible with older pytest)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# SECTION 1 — Original 10 tests (must remain unchanged and passing)
# ===========================================================================


class TestRetryAsyncOriginal:
    """Original tests for retry_async (backward-compat guard)."""

    def test_succeeds_on_first_attempt(self):
        call_count = 0

        @retry_async(retries=3, initial_delay=0)
        async def always_ok():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = run(always_ok())
        assert result == "ok"
        assert call_count == 1

    def test_retries_on_exception_then_succeeds(self):
        call_count = 0

        @retry_async(retries=3, initial_delay=0, exceptions=(ValueError,))
        async def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("nope")
            return "done"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(fails_twice())

        assert result == "done"
        assert call_count == 3

    def test_raises_after_all_retries_exhausted(self):
        @retry_async(retries=3, initial_delay=0, exceptions=(RuntimeError,))
        async def always_fails():
            raise RuntimeError("boom")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="boom"):
                run(always_fails())

    def test_only_catches_specified_exceptions(self):
        @retry_async(retries=3, initial_delay=0, exceptions=(ValueError,))
        async def raises_type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            run(raises_type_error())

    def test_default_exceptions_catches_generic_exception(self):
        call_count = 0

        @retry_async(retries=3, initial_delay=0)
        async def generic_fail():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("generic")
            return "recovered"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(generic_fail())

        assert result == "recovered"
        assert call_count == 2

    def test_backoff_increases_delay(self):
        sleep_calls = []

        @retry_async(
            retries=4,
            initial_delay=1.0,
            max_delay=100.0,
            backoff_factor=2.0,
            jitter=0.0,
            exceptions=(Exception,),
        )
        async def always_fails():
            raise Exception("fail")

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(Exception):
                run(always_fails())

        assert len(sleep_calls) == 3  # 4 retries → 3 sleeps
        assert sleep_calls[0] < sleep_calls[1] < sleep_calls[2]

    def test_max_delay_is_respected(self):
        sleep_calls = []

        @retry_async(
            retries=5,
            initial_delay=10.0,
            max_delay=15.0,
            backoff_factor=3.0,
            jitter=0.0,
            exceptions=(Exception,),
        )
        async def always_fails():
            raise Exception("fail")

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(Exception):
                run(always_fails())

        assert all(s <= 15.0 for s in sleep_calls)


class TestRetrySyncOriginal:
    """Original tests for retry_sync (backward-compat guard)."""

    def test_sync_succeeds_on_first_attempt(self):
        @retry_sync(retries=3, initial_delay=0)
        def always_ok():
            return "ok"

        assert always_ok() == "ok"

    def test_sync_retries_then_succeeds(self):
        call_count = 0

        @retry_sync(retries=3, initial_delay=0, exceptions=(ValueError,))
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("nope")
            return "done"

        with patch("time.sleep"):
            result = fail_twice()

        assert result == "done"
        assert call_count == 3

    def test_sync_raises_after_all_retries(self):
        @retry_sync(retries=3, initial_delay=0, exceptions=(RuntimeError,))
        def always_fails():
            raise RuntimeError("boom")

        with patch("time.sleep"):
            with pytest.raises(RuntimeError, match="boom"):
                always_fails()


# ===========================================================================
# SECTION 2 — 6 new tests covering enhanced features
# ===========================================================================


class TestRetryStats:
    """Tests for RetryStats tracking via stats= parameter."""

    def test_retry_stats_tracks_attempts(self):
        """RetryStats.attempts increments on each attempt; success=True on final pass."""
        stats = RetryStats()
        call_count = 0

        @retry_async(
            retries=3,
            initial_delay=0,
            exceptions=(ValueError,),
            stats=stats,
        )
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(fail_twice())

        assert result == "ok"
        assert stats.attempts == 3
        assert stats.success is True

    def test_retry_stats_tracks_delay(self):
        """RetryStats.total_delay accumulates sleep durations across retries."""
        stats = RetryStats()
        accumulated_sleep = []

        @retry_async(
            retries=3,
            initial_delay=1.0,
            backoff_factor=2.0,
            jitter=0.0,
            exceptions=(ValueError,),
            stats=stats,
        )
        async def always_fails():
            raise ValueError("fail")

        async def fake_sleep(seconds):
            accumulated_sleep.append(seconds)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(ValueError):
                run(always_fails())

        # total_delay should match sum of actual sleeps
        assert stats.total_delay == pytest.approx(sum(accumulated_sleep), abs=1e-9)
        assert stats.total_delay > 0.0

    def test_retry_stats_records_last_exception(self):
        """RetryStats.last_exception holds the most recent caught exception."""
        stats = RetryStats()

        @retry_async(
            retries=2,
            initial_delay=0,
            exceptions=(ValueError,),
            stats=stats,
        )
        async def always_fails():
            raise ValueError("specific error")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError):
                run(always_fails())

        assert stats.last_exception is not None
        assert isinstance(stats.last_exception, ValueError)
        assert str(stats.last_exception) == "specific error"


class TestOnRetryCallback:
    """Tests for on_retry callback invocation."""

    def test_on_retry_callback_called(self):
        """on_retry called with (attempt: int, exc: Exception, delay: float) on each retry."""
        callback_calls = []

        def on_retry(attempt, exc, delay):
            callback_calls.append((attempt, exc, delay))

        @retry_async(
            retries=3,
            initial_delay=0.5,
            jitter=0.0,
            exceptions=(ValueError,),
            on_retry=on_retry,
        )
        async def fail_twice():
            if len(callback_calls) < 2:
                raise ValueError("retry me")
            return "ok"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(fail_twice())

        assert result == "ok"
        assert len(callback_calls) == 2

        # Each call: (attempt_number, the exception, delay_float)
        for attempt_num, (cb_attempt, cb_exc, cb_delay) in enumerate(
            callback_calls, start=1
        ):
            assert cb_attempt == attempt_num
            assert isinstance(cb_exc, ValueError)
            assert isinstance(cb_delay, float)


class TestRetryOnResult:
    """Tests for retry_on_result result-predicate."""

    def test_retry_on_result_retries_bad_result(self):
        """When predicate returns True, retry continues; when False, returns immediately."""
        call_count = 0

        @retry_async(
            retries=4,
            initial_delay=0,
            retry_on_result=lambda r: r is None,
        )
        async def returns_none_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return None
            return "real_value"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(returns_none_twice())

        assert result == "real_value"
        assert call_count == 3

    def test_retry_on_result_exhausts_gracefully(self):
        """Exhausted result-predicate retries return the last result (no raise)."""
        stats = RetryStats()

        @retry_async(
            retries=3,
            initial_delay=0,
            retry_on_result=lambda r: r is None,
            stats=stats,
        )
        async def always_none():
            return None

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(always_none())

        # Result returned as-is after exhaustion
        assert result is None
        assert stats.success is False


class TestTryAgain:
    """Tests for TryAgain sentinel exception."""

    def test_try_again_forces_retry(self):
        """Raising TryAgain inside decorated function triggers retry regardless of exceptions filter."""
        call_count = 0

        @retry_async(
            retries=4,
            initial_delay=0,
            exceptions=(ValueError,),  # TryAgain is NOT in this filter
        )
        async def raises_try_again_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TryAgain()
            return "success"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(raises_try_again_twice())

        assert result == "success"
        assert call_count == 3

    def test_try_again_does_not_set_last_exception(self):
        """TryAgain is not recorded as last_exception in RetryStats."""
        stats = RetryStats()
        call_count = 0

        @retry_async(
            retries=3,
            initial_delay=0,
            stats=stats,
        )
        async def try_again_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TryAgain()
            return "done"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(try_again_then_succeed())

        assert result == "done"
        assert stats.last_exception is None  # TryAgain must NOT pollute last_exception
        assert stats.success is True


class TestBackwardCompat:
    """Ensures existing call sites work without any new params."""

    def test_backward_compat_no_new_params(self):
        """Existing @retry_async(retries=3) call with no new params still works identically."""
        call_count = 0

        @retry_async(retries=3, initial_delay=0, exceptions=(ConnectionError,))
        async def fragile():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "connected"

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = run(fragile())

        assert result == "connected"
        assert call_count == 2

    def test_retry_sync_try_again_symmetry(self):
        """retry_sync also handles TryAgain for symmetry with retry_async."""
        call_count = 0

        @retry_sync(retries=4, initial_delay=0, exceptions=(ValueError,))
        def sync_with_try_again():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TryAgain()
            return "sync_ok"

        with patch("time.sleep"):
            result = sync_with_try_again()

        assert result == "sync_ok"
        assert call_count == 3
