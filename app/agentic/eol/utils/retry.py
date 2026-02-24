"""
Lightweight retry utilities for synchronous and asynchronous call wrappers.

This module intentionally avoids external dependencies so it can be used
in environments where installing new packages is not desirable.

Provides:
- retry_async: decorator for async functions with exponential backoff + jitter
- retry_sync: decorator for sync functions with exponential backoff + jitter

Usage:
from utils.retry import retry_async, retry_sync

@retry_async(retries=5, initial_delay=1, max_delay=30)
async def call_external(...):
    ...

@retry_sync(retries=3)
def call_db(...):
    ...

"""
import asyncio
import random
import time
import functools
from typing import Callable, Iterable, Tuple, Type, Any

ExceptionTypes = Tuple[Type[BaseException], ...]


def _default_exceptions() -> ExceptionTypes:
    return (Exception,)


def retry_async(
    retries: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: ExceptionTypes = None,
    jitter: float = 0.1,
):
    """Decorator for retrying async functions on exceptions.

    Args:
        retries: total attempts (including the first)
        initial_delay: starting delay in seconds
        max_delay: maximum delay in seconds
        backoff_factor: multiplier applied to the delay on each retry
        exceptions: tuple of exception classes to catch and retry on
        jitter: fraction of delay to add as random jitter (0.0-1.0)
    """
    if exceptions is None:
        exceptions = _default_exceptions()

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:  # type: ignore
                    last_exc = exc
                    if attempt == retries:
                        # Exhausted retries
                        raise
                    # add jitter to avoid thundering herd
                    jitter_amount = random.uniform(0, jitter * delay)
                    sleep_for = min(delay + jitter_amount, max_delay)
                    await asyncio.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)
            # If somehow we exit loop without returning, raise last exception
            if last_exc:
                raise last_exc

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
    """Decorator for retrying synchronous functions on exceptions."""
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
