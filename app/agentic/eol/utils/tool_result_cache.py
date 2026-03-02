"""
TTL-based LRU cache for tool invocation results.

Provides an async-safe, in-memory cache suitable for eliminating duplicate tool
calls within a single agent turn or across short-lived request windows.

Design decisions:
  - ``OrderedDict`` supplies O(1) LRU promotion without a separate linked list.
  - ``asyncio.Lock`` (not ``threading.Lock``) matches the async-first codebase
    convention; all I/O paths in this app are async.
  - A secondary ``_tool_keys`` index maps tool_name → set[key] to make
    ``invalidate_pattern`` O(k) instead of O(n) where k is the number of keys
    cached for that specific tool.
  - ``time.monotonic()`` is used throughout for expiry checks — it is immune to
    wall-clock adjustments (DST, NTP), which matters for correctness in tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

class CacheEntry:
    """A single cached value with an expiry timestamp."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_seconds: float) -> None:
        self.value = value
        self.expires_at: float = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        """Return True when the entry has passed its TTL."""
        return time.monotonic() > self.expires_at


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class ToolResultCache:
    """
    Async-safe TTL-LRU cache for tool invocation results.

    Args:
        default_ttl_seconds: TTL applied when ``set()`` is called without an
            explicit override.  Defaults to 300 s (5 min).
        max_size: Maximum number of entries before LRU eviction kicks in.
    """

    def __init__(
        self,
        default_ttl_seconds: float = 300.0,
        max_size: int = 1000,
    ) -> None:
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size

        # Ordered dict preserves insertion / access order for LRU semantics.
        # Most-recently used entries live at the *end* of the dict.
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()

        # Secondary index: tool_name → set of keys stored for that tool.
        # Kept in sync with _store to enable O(k) pattern invalidation.
        self._tool_keys: Dict[str, Set[str]] = {}

        self._lock = asyncio.Lock()

        # Stats counters
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ------------------------------------------------------------------
    # Key construction
    # ------------------------------------------------------------------

    def make_key(self, tool_name: str, args: dict) -> str:
        """
        Build a stable, deterministic cache key from tool name and arguments.

        Argument dict order is normalised via ``sort_keys=True`` before hashing
        so that ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}`` produce the same
        key.  Non-JSON-serialisable values are coerced to strings via
        ``default=str``.
        """
        payload = json.dumps(
            {"tool": tool_name, "args": args},
            sort_keys=True,
            default=str,
        )
        return hashlib.md5(payload.encode()).hexdigest()  # noqa: S324

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        """
        Return the cached value for *key*, or ``None`` on miss / expiry.

        An expired entry is evicted on read (lazy expiry) so the cache does not
        accumulate stale data between explicit ``clear()`` calls.
        """
        async with self._lock:
            entry = self._store.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                # Lazy eviction — remove the stale entry
                self._remove_entry(key)
                self._misses += 1
                logger.debug("tool_result_cache: expired eviction for key=%s", key[:16])
                return None

            # LRU promotion: move to the end (most-recently-used position)
            self._store.move_to_end(key)
            self._hits += 1
            logger.debug("tool_result_cache: HIT key=%s", key[:16])
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        *,
        tool_name: Optional[str] = None,
    ) -> None:
        """
        Store *value* under *key* with a TTL.

        Args:
            key: Cache key (typically produced by :meth:`make_key`).
            value: Serialisable result to cache.
            ttl_seconds: Per-entry TTL override; uses ``default_ttl_seconds``
                when omitted.
            tool_name: Optional tool name stored in the secondary index to
                enable :meth:`invalidate_pattern`.  If callers use
                :meth:`make_key` they can pass ``tool_name`` here so the index
                stays accurate.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        async with self._lock:
            # If the key already exists, update in-place and re-promote.
            if key in self._store:
                self._store[key] = CacheEntry(value, ttl)
                self._store.move_to_end(key)
                return

            # Evict LRU entries when we are at capacity.
            while len(self._store) >= self._max_size:
                self._evict_lru()

            entry = CacheEntry(value, ttl)
            self._store[key] = entry

            # Keep the secondary tool-name index up to date.
            if tool_name is not None:
                self._tool_keys.setdefault(tool_name, set()).add(key)

            logger.debug(
                "tool_result_cache: SET key=%s ttl=%.0fs",
                key[:16],
                ttl,
            )

    async def invalidate(self, key: str) -> None:
        """Remove the entry for *key*, if present."""
        async with self._lock:
            if key in self._store:
                self._remove_entry(key)
                logger.debug("tool_result_cache: invalidated key=%s", key[:16])

    async def invalidate_pattern(self, tool_name: str) -> int:
        """
        Remove all cached entries associated with *tool_name*.

        Uses the secondary ``_tool_keys`` index for O(k) removal rather than
        scanning the entire store.

        Returns:
            Number of entries removed.
        """
        async with self._lock:
            keys = self._tool_keys.pop(tool_name, set())
            for key in keys:
                if key in self._store:
                    del self._store[key]
            count = len(keys)
            if count:
                logger.debug(
                    "tool_result_cache: pattern-invalidated %d entries for tool=%s",
                    count,
                    tool_name,
                )
            return count

    async def clear(self) -> None:
        """Remove all entries and reset statistics."""
        async with self._lock:
            self._store.clear()
            self._tool_keys.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            logger.debug("tool_result_cache: cleared")

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """
        Return a snapshot of cache statistics.

        Keys: ``hits``, ``misses``, ``size``, ``evictions``, ``hit_rate``.
        ``hit_rate`` is a float in [0.0, 1.0]; returns 0.0 when no requests
        have been made.
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "evictions": self._evictions,
            "hit_rate": round(hit_rate, 4),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_lru(self) -> None:
        """
        Evict the least-recently-used entry (the *first* item in the
        OrderedDict).  Must be called while the lock is held.
        """
        if not self._store:
            return
        lru_key, _ = next(iter(self._store.items()))
        self._remove_entry(lru_key)
        self._evictions += 1
        logger.debug("tool_result_cache: LRU eviction key=%s", lru_key[:16])

    def _remove_entry(self, key: str) -> None:
        """
        Remove *key* from both ``_store`` and the tool-key index.
        Must be called while the lock is held.
        """
        del self._store[key]
        # Clean up secondary index (scan is O(t) where t = distinct tool names,
        # which is small in practice).
        for keys_set in self._tool_keys.values():
            keys_set.discard(key)
