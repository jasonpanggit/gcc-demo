"""
Async circuit breaker for protecting external dependency calls.

Implements the canonical three-state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
with asyncio-native locking so it is safe for concurrent coroutines.

States
------
CLOSED    Normal operation.  Failures are counted; once the failure_threshold is
          reached the circuit trips to OPEN.
OPEN      All calls are rejected immediately with CircuitBreakerOpenError.
          After recovery_timeout seconds the circuit transitions to HALF_OPEN.
HALF_OPEN A probe window: up to half_open_max_calls are allowed through.
          A single success closes the circuit; a single failure re-opens it.

Usage
-----
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0, name="database")

    try:
        result = await cb.call(my_async_func, arg1, kwarg=value)
    except CircuitBreakerOpenError:
        # fast-fail path
        ...

Module-level singleton manager
-------------------------------
    from utils.circuit_breaker import circuit_breaker_manager

    result = await circuit_breaker_manager.call("openai", my_coro, *args)
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Async-safe circuit breaker.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive/cumulative failures required to open the circuit
        while in CLOSED state.
    recovery_timeout:
        Seconds to wait in OPEN state before transitioning to HALF_OPEN.
    half_open_max_calls:
        Maximum probe calls allowed while in HALF_OPEN state.  The first
        success closes the circuit; the first failure re-opens it.
    name:
        Human-readable label used in log messages and metrics.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.name = name

        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._total_calls: int = 0
        self._rejected_calls: int = 0
        self._half_open_calls: int = 0
        self._last_failure_time: Optional[float] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *func* while honouring the circuit breaker state.

        Parameters
        ----------
        func:
            Async (or sync) callable to execute.
        *args / **kwargs:
            Forwarded verbatim to *func*.

        Raises
        ------
        CircuitBreakerOpenError
            When the circuit is OPEN and the recovery window has not elapsed.
        """
        async with self._lock:
            current_state = self._state

            if current_state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    logger.info(
                        "CircuitBreaker[%s]: recovery timeout elapsed, transitioning "
                        "OPEN → HALF_OPEN",
                        self.name,
                    )
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 0
                else:
                    self._rejected_calls += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is OPEN; call rejected"
                    )

            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    # Probe window exhausted without resolution — stay OPEN
                    self._state = CircuitBreakerState.OPEN
                    self._last_failure_time = time.monotonic()
                    self._rejected_calls += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' probe window exhausted; re-opening"
                    )
                self._half_open_calls += 1

            self._total_calls += 1

        # Execute the callable *outside* the lock so other coroutines are not
        # blocked while waiting for the I/O result.
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def record_success(self) -> None:
        """Update the state machine after a successful call."""
        prev_state = self._state
        self._failure_count = 0
        self._success_count += 1

        if prev_state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.CLOSED
            self._half_open_calls = 0
            self._last_failure_time = None
            logger.info(
                "CircuitBreaker[%s]: success in HALF_OPEN → CLOSED", self.name
            )
        # In CLOSED state a success simply resets the failure counter (already done).

    def record_failure(self) -> None:
        """Update the state machine after a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            logger.warning(
                "CircuitBreaker[%s]: failure in HALF_OPEN → OPEN", self.name
            )
        elif self._state == CircuitBreakerState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: failure_threshold=%d reached → OPEN",
                    self.name,
                    self.failure_threshold,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_attempt_reset(self) -> bool:
        """Return True if enough time has passed since the last failure."""
        if self._last_failure_time is None:
            return True
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        return self._state

    @property
    def metrics(self) -> Dict[str, Any]:
        """Snapshot of runtime counters.

        Returns
        -------
        dict with keys:
            state            – current state name (str)
            failure_count    – failures since last reset
            success_count    – cumulative successes
            total_calls      – calls that were attempted (not rejected)
            rejected_calls   – calls rejected while OPEN
            last_failure_time – monotonic timestamp of last failure, or None
        """
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "rejected_calls": self._rejected_calls,
            "last_failure_time": self._last_failure_time,
        }


# ---------------------------------------------------------------------------
# Backward-compatible shims (preserves callers that use the old API)
# ---------------------------------------------------------------------------

class CircuitOpenException(CircuitBreakerOpenError):
    """Alias kept for backward compatibility with existing callers."""


# ---------------------------------------------------------------------------
# Manager — per-name registry of CircuitBreaker instances
# ---------------------------------------------------------------------------

class CircuitBreakerManager:
    """Registry that provides named CircuitBreaker instances.

    Existing callers that use ``circuit_breaker_manager.call(name, coro, ...)``
    continue to work unchanged.
    """

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    def get_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ) -> CircuitBreaker:
        """Return (and lazily create) a named CircuitBreaker.

        The first call with a given *name* creates the breaker with the
        supplied parameters; subsequent calls return the cached instance.
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
                name=name,
            )
        return self._breakers[name]

    def is_open(self, name: str) -> bool:
        """Return True if the named circuit is currently OPEN."""
        return self.get_breaker(name).state == CircuitBreakerState.OPEN

    async def call(self, name: str, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *func* via the named circuit breaker.

        Raises CircuitBreakerOpenError (subclass of CircuitOpenException) when
        the circuit is open.
        """
        breaker = self.get_breaker(name)
        return await breaker.call(func, *args, **kwargs)


# Module-level singleton — drop-in replacement for the old singleton.
circuit_breaker_manager = CircuitBreakerManager()
