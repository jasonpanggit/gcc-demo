"""Patch Assessment Repository

In-memory repository for caching Azure Resource Graph patch assessment data.
Eliminates repeated ARG queries and prevents throttling.

Cache strategy:
- TTL: 1 hour (3600s) for assessment data
- Key: {subscription_id}:{machine_name}:{vm_type}
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)

_CACHE_TTL = 3600  # 1 hour


def _make_cache_key(subscription_id: str, machine_name: str, vm_type: str) -> str:
    """Generate a short, consistent document ID for the cache entry."""
    normalized = f"{subscription_id}:{machine_name.lower()}:{vm_type}".lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class PatchAssessmentRepository:
    """In-memory repository for patch assessment data with TTL-based expiration."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _is_valid(self, entry: Dict[str, Any]) -> bool:
        """Check if a cache entry is still valid based on TTL."""
        cached_at = entry.get("_cached_at", 0)
        return (time.time() - cached_at) < _CACHE_TTL

    async def get_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str = "arc",
    ) -> Optional[Dict[str, Any]]:
        """Return cached assessment data, or None on miss."""
        cache_key = _make_cache_key(subscription_id, machine_name, vm_type)
        entry = self._cache.get(cache_key)
        if entry and self._is_valid(entry):
            logger.info("Returning cached patch assessment for %s", machine_name)
            return entry.get("assessment_data")

        # Remove expired entry
        if entry:
            self._cache.pop(cache_key, None)

        logger.debug("Cache MISS for patch assessment %s", machine_name)
        return None

    async def store_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str,
        assessment_data: Dict[str, Any],
    ) -> bool:
        """Persist assessment data to cache. Returns True on success."""
        cache_key = _make_cache_key(subscription_id, machine_name, vm_type)
        self._cache[cache_key] = {
            "id": cache_key,
            "subscription_id": subscription_id,
            "machine_name": machine_name.lower(),
            "vm_type": vm_type,
            "assessment_data": assessment_data,
            "cached_at": datetime.utcnow().isoformat(),
            "_cached_at": time.time(),
        }
        logger.debug("Cached patch assessment for %s", machine_name)
        return True

    async def batch_get_assessments(
        self,
        machines: List[Dict[str, str]],
    ) -> Dict[str, Dict[str, Any]]:
        """Parallel cache lookup for a list of machines.

        Args:
            machines: list of dicts with keys subscription_id, machine_name, vm_type

        Returns:
            Dict mapping machine_name (lower) -> assessment_data for cache hits only
        """
        results: Dict[str, Dict[str, Any]] = {}

        async def fetch_one(m: Dict[str, str]) -> None:
            data = await self.get_assessment(
                m["subscription_id"],
                m["machine_name"],
                m.get("vm_type", "arc"),
            )
            if data:
                results[m["machine_name"].lower()] = data

        await asyncio.gather(*[fetch_one(m) for m in machines], return_exceptions=True)
        logger.info("Batch fetch: %d/%d cache hits", len(results), len(machines))
        return results


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_patch_assessment_repo: Optional[PatchAssessmentRepository] = None


async def get_patch_assessment_repository() -> PatchAssessmentRepository:
    """Return the singleton PatchAssessmentRepository."""
    global _patch_assessment_repo

    if _patch_assessment_repo is not None:
        return _patch_assessment_repo

    _patch_assessment_repo = PatchAssessmentRepository()
    return _patch_assessment_repo
