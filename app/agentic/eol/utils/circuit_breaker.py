"""
Simple in-memory circuit breaker manager.

Provides per-resource circuit breakers with basic failure counting and
an automatic cooldown (open -> half-open -> closed) behavior.

This is intentionally lightweight and meant as a pragmatic safety layer
for external dependency calls (OpenAI, Cosmos, Playwright, etc.). For
production-grade usage consider using a robust library or Redis-backed
state for distributed deployments.
"""
import time
import threading
from typing import Dict, Optional


class CircuitOpenException(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self._state == "OPEN":
                # If recovery timeout elapsed, transition to HALF_OPEN
                if self._opened_at and (time.time() - self._opened_at) >= self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    return False
                return True
            return False

    def on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"
            self._opened_at = None

    def on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                self._opened_at = time.time()

    def force_open(self) -> None:
        with self._lock:
            self._state = "OPEN"
            self._opened_at = time.time()

    def force_close(self) -> None:
        with self._lock:
            self._state = "CLOSED"
            self._failure_count = 0
            self._opened_at = None


class CircuitBreakerManager:
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(failure_threshold=failure_threshold, recovery_timeout=recovery_timeout)
            return self._breakers[name]

    def is_open(self, name: str) -> bool:
        breaker = self.get_breaker(name)
        return breaker.is_open()

    async def call(self, name: str, coro, *args, **kwargs):
        """
        Execute the coroutine `coro` while honoring the circuit breaker state.

        Args:
            name: logical resource name for the breaker (e.g., 'openai', 'cosmos')
            coro: async callable to execute
        Raises:
            CircuitOpenException if the circuit is open and call is not allowed
        """
        breaker = self.get_breaker(name)
        if breaker.is_open():
            raise CircuitOpenException(f"Circuit '{name}' is open; rejecting call")

        try:
            result = await coro(*args, **kwargs)
            breaker.on_success()
            return result
        except Exception:
            # Record failure and re-raise
            breaker.on_failure()
            raise


# Module-level singleton
circuit_breaker_manager = CircuitBreakerManager()
