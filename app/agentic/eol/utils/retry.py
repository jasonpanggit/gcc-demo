"""
Lightweight retry utilities for synchronous and asynchronous call wrappers.

This module intentionally avoids external dependencies so it can be used
in environments where installing new packages is not desirable.

Provides:
- retry_async: decorator for async functions with exponential backoff + jitter
- retry_sync:  decorator for sync functions with exponential backoff + jitter
- RetryStats:  mutable dataclass for per-call retry metrics (pass as ``stats=``)
- TryAgain:    sentinel exception; raise inside a retried function to force retry

Usage:
from utils.retry import retry_async, retry_sync, RetryStats, TryAgain

@retry_async(retries=5, initial_delay=1, max_delay=30)
async def call_external(...):
    ...

@retry_sync(retries=3)
def call_db(...):
    ...

# With observability hooks:
stats = RetryStats()

@retry_async(retries=5, stats=stats, on_retry=lambda a, e, d: log(a, e, d))
async def call_azure(...):
    ...

# Result-based retry (e.g. retry until Azure returns a non-None response):
@retry_async(retries=5, retry_on_result=lambda r: r is None)
async def poll_resource(...):
    ...

"""
import asyncio
import random
import time
import functools
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, Type, Any

ExceptionTypes = Tuple[Type[BaseException], ...]


def _default_exceptions() -> ExceptionTypes:
    return (Exception,)


@dataclass
class RetryStats:
    """Mutable stats object; pass to retry_async(stats=...) to track per-call metrics.

    Attributes:
        attempts:       Total number of call attempts made (including successful one).
        total_delay:    Cumulative sleep time (seconds) across all retries.
        last_exception: Most recent exception caught by the retry loop (None if no exception).
        success:        True when the decorated call ultimately succeeded; False otherwise.
    """
    attempts: int = 0
    total_delay: float = 0.0
    last_exception: Optional[Exception] = None
    success: bool = False


class TryAgain(Exception):
    """Raise inside a retried function to force another retry attempt.

    Unlike normal exceptions, TryAgain is NOT recorded as ``last_exception``
    in RetryStats — it is treated purely as a control-flow signal.
    """
    pass


def retry_async(
    retries: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: ExceptionTypes = None,
    jitter: float = 0.1,
    retry_on_result: Optional[Callable[[Any], bool]] = None,
    on_retry: Optional[Callable[[int, Optional[Exception], float], None]] = None,
    stats: Optional[RetryStats] = None,
):
    """Decorator for retrying async functions on exceptions.

    Args:
        retries:          Total attempts (including the first).
        initial_delay:    Starting delay in seconds.
        max_delay:        Maximum delay in seconds.
        backoff_factor:   Multiplier applied to the delay on each retry.
        exceptions:       Tuple of exception classes to catch and retry on.
        jitter:           Fraction of delay to add as random jitter (0.0–1.0).
        retry_on_result:  Optional predicate; when ``predicate(result)`` is True
                          the call is retried even if no exception was raised.
                          Retries are exhausted gracefully (result returned as-is).
        on_retry:         Optional callback invoked on each retry with
                          ``(attempt: int, exc_or_none: Optional[Exception], delay: float)``.
        stats:            Optional :class:`RetryStats` instance; updated in place with
                          attempt count, cumulative delay, last exception, and success flag.
    """
    if exceptions is None:
        exceptions = _default_exceptions()

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(1, retries + 1):
                try:
                    result = await func(*args, **kwargs)

                    # Update stats for this attempt regardless of result-predicate
                    if stats is not None:
                        stats.attempts = attempt

                    # Result-based retry
                    if retry_on_result is not None and retry_on_result(result):
                        if attempt < retries:
                            jitter_amount = random.uniform(0, jitter * delay)
                            sleep_for = min(delay + jitter_amount, max_delay)
                            if stats is not None:
                                stats.total_delay += sleep_for
                            if on_retry is not None:
                                on_retry(attempt, None, sleep_for)
                            await asyncio.sleep(sleep_for)
                            delay = min(delay * backoff_factor, max_delay)
                            continue
                        # Retries exhausted — return whatever we have
                        if stats is not None:
                            stats.success = False
                        return result

                    # Successful result
                    if stats is not None:
                        stats.success = True
                    return result

                except TryAgain:
                    # TryAgain is a control-flow sentinel — not a real error;
                    # do NOT record it as last_exception.
                    if stats is not None:
                        stats.attempts = attempt
                    if attempt == retries:
                        # Exhausted retries via TryAgain — nothing to raise, fall through
                        break
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)
                    if stats is not None:
                        stats.total_delay += sleep_for
                    if on_retry is not None:
                        on_retry(attempt, None, sleep_for)
                    await asyncio.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)

                except exceptions as exc:  # type: ignore
                    if stats is not None:
                        stats.last_exception = exc
                        stats.attempts = attempt
                    if attempt == retries:
                        # Exhausted retries — re-raise
                        raise
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)
                    if stats is not None:
                        stats.total_delay += sleep_for
                    if on_retry is not None:
                        on_retry(attempt, exc, sleep_for)
                    await asyncio.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)

        return wrapper

    return decorator


def retry_sync(
    retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    exceptions: ExceptionTypes = None,
    jitter: float = 0.1,
):
    """Decorator for retrying synchronous functions on exceptions.

    Also honours :class:`TryAgain` — raising it inside a decorated sync
    function forces a retry regardless of the ``exceptions`` filter.
    """
    if exceptions is None:
        exceptions = _default_exceptions()

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except TryAgain:
                    if attempt == retries:
                        break
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)
                    time.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)
                except exceptions as exc:  # type: ignore
                    last_exc = exc
                    if attempt == retries:
                        raise
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)
                    time.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)
            if last_exc:
                raise last_exc

        return wrapper

    return decorator
