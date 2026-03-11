"""
L1 in-memory cache for CVE data.

Provides TTL-based caching with thread safety for recently accessed CVEs.
"""
from __future__ import annotations

from threading import RLock
from typing import Optional
from cachetools import TTLCache

try:
    from models.cve_models import UnifiedCVE
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


class CVECache:
    """L1 in-memory cache for CVE data.

    Uses TTLCache for automatic expiration and LRU eviction.
    Thread-safe with RLock for concurrent access.

    Default: 1000 CVEs, 1 hour TTL
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        """Initialize CVE cache.

        Args:
            maxsize: Maximum number of CVEs to cache
            ttl: Time-to-live in seconds (default 1 hour)
        """
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = RLock()
        self.maxsize = maxsize
        self.ttl = ttl
        logger.info(f"Initialized CVE L1 cache (size={maxsize}, ttl={ttl}s)")

    def get(self, cve_id: str) -> Optional[UnifiedCVE]:
        """Get CVE from cache.

        Args:
            cve_id: CVE identifier

        Returns:
            UnifiedCVE model or None if not cached/expired
        """
        cve_id = cve_id.upper()
        with self._lock:
            cve = self._cache.get(cve_id)
            if cve:
                logger.debug(f"L1 cache hit: {cve_id}")
            return cve

    def set(self, cve_id: str, cve: UnifiedCVE) -> None:
        """Add CVE to cache.

        Args:
            cve_id: CVE identifier
            cve: UnifiedCVE model to cache
        """
        cve_id = cve_id.upper()
        with self._lock:
            self._cache[cve_id] = cve
            logger.debug(f"L1 cache set: {cve_id}")

    def invalidate(self, cve_id: str) -> None:
        """Remove CVE from cache.

        Args:
            cve_id: CVE identifier to invalidate
        """
        cve_id = cve_id.upper()
        with self._lock:
            removed = self._cache.pop(cve_id, None)
            if removed:
                logger.debug(f"L1 cache invalidated: {cve_id}")

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"L1 cache cleared ({count} CVEs)")

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with current size, maxsize, TTL, hit rate (if tracked)
        """
        with self._lock:
            return {
                "current_size": len(self._cache),
                "maxsize": self.maxsize,
                "ttl_seconds": self.ttl,
                "cache_type": "TTLCache with LRU eviction"
            }
