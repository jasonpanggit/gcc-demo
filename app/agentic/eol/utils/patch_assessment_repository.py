"""Patch Assessment Repository

Cosmos DB repository for caching Azure Resource Graph patch assessment data.
Eliminates repeated ARG queries and prevents throttling.

Cache strategy:
- TTL: 1 hour (3600s) for assessment data
- Key: {subscription_id}:{machine_name}:{vm_type}
- Automatic expiration via Cosmos TTL
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from utils.logging_config import get_logger
    from utils.config import config
    from utils.cosmos_cache import base_cosmos
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.cosmos_cache import base_cosmos

logger = get_logger(__name__)

_CONTAINER_NAME = "patch_assessments"
_CONTAINER_PARTITION_PATH = "/partitionKey"
_CONTAINER_TTL = 3600  # 1 hour


def _is_cosmos_available() -> bool:
    """Return True only when Cosmos is configured and the base client initialised."""
    return bool(getattr(config.azure, "cosmos_endpoint", None)) and base_cosmos.initialized


def _get_container():
    """Return the patch_assessments container (or None when unavailable)."""
    return base_cosmos.get_container(
        _CONTAINER_NAME,
        partition_path=_CONTAINER_PARTITION_PATH,
        default_ttl=_CONTAINER_TTL,
    )


def _make_cache_key(subscription_id: str, machine_name: str, vm_type: str) -> str:
    """Generate a short, consistent document ID for the cache entry."""
    normalized = f"{subscription_id}:{machine_name.lower()}:{vm_type}".lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class PatchAssessmentRepository:
    """Repository for patch assessment data backed by the shared Cosmos base_cosmos client."""

    async def get_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str = "arc",
    ) -> Optional[Dict[str, Any]]:
        """Return cached assessment data, or None on miss / unavailable."""
        if not _is_cosmos_available():
            return None

        container = _get_container()
        if container is None:
            return None

        cache_key = _make_cache_key(subscription_id, machine_name, vm_type)
        try:
            item = await asyncio.to_thread(
                container.read_item,
                item=cache_key,
                partition_key=subscription_id,
            )
            if item:
                logger.info("Returning cached patch assessment for %s", machine_name)
                return item.get("assessment_data")
        except Exception as exc:
            logger.debug("Cache MISS for patch assessment %s: %s", machine_name, exc)

        return None

    async def store_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str,
        assessment_data: Dict[str, Any],
    ) -> bool:
        """Persist assessment data to Cosmos. Returns True on success."""
        if not _is_cosmos_available():
            return False

        container = _get_container()
        if container is None:
            return False

        cache_key = _make_cache_key(subscription_id, machine_name, vm_type)
        document = {
            "id": cache_key,
            "partitionKey": subscription_id,
            "subscription_id": subscription_id,
            "machine_name": machine_name.lower(),
            "vm_type": vm_type,
            "assessment_data": assessment_data,
            "cached_at": datetime.utcnow().isoformat(),
        }

        try:
            await asyncio.to_thread(container.upsert_item, document)
            logger.debug("Cached patch assessment for %s", machine_name)
            return True
        except Exception as exc:
            logger.warning("Failed to cache patch assessment for %s: %s", machine_name, exc)
            return False

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
        if not _is_cosmos_available():
            return {}

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
    """Return the singleton PatchAssessmentRepository, initialising Cosmos if needed."""
    global _patch_assessment_repo

    if _patch_assessment_repo is not None:
        return _patch_assessment_repo

    if not getattr(config.azure, "cosmos_endpoint", None):
        raise RuntimeError("Cosmos DB is not configured - patch assessment caching unavailable")

    # Ensure the base client is initialised (idempotent)
    if not base_cosmos.initialized:
        await base_cosmos._initialize_async()

    if not base_cosmos.initialized:
        raise RuntimeError("Cosmos DB base client failed to initialise")

    _patch_assessment_repo = PatchAssessmentRepository()
    return _patch_assessment_repo
