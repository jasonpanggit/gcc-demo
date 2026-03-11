"""Patch Assessment Repository

Cosmos DB repository for caching Azure Resource Graph patch assessment data.
Eliminates repeated ARG queries and prevents throttling.

Cache strategy:
- TTL: 1 hour (3600s) for assessment data
- Key: {subscription_id}:{machine_name}:{vm_type}
- Automatic expiration via Cosmos TTL
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import hashlib

try:
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)


class PatchAssessmentRepository:
    """Repository for patch assessment data with Cosmos DB caching."""

    def __init__(self, cosmos_client, database_name: str, container_name: str = "patch_assessments"):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self._container = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazy initialization of Cosmos resources."""
        if self._initialized:
            return

        try:
            database = self.cosmos_client.get_database_client(self.database_name)

            # Create container with TTL enabled
            try:
                self._container = await database.create_container_if_not_exists(
                    id=self.container_name,
                    partition_key={"paths": ["/partitionKey"], "kind": "Hash"},
                    default_ttl=3600,  # 1 hour TTL for all documents
                )
                logger.info(f"Patch assessment container '{self.container_name}' ready with TTL=3600s")
            except Exception as e:
                logger.warning(f"Failed to create container: {e}, attempting to get existing")
                self._container = database.get_container_client(self.container_name)

            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize patch assessment repository: {e}")
            raise

    def _make_cache_key(self, subscription_id: str, machine_name: str, vm_type: str) -> str:
        """Generate consistent cache key for assessment data."""
        normalized = f"{subscription_id}:{machine_name.lower()}:{vm_type}".lower()
        # Use hash to keep key length reasonable
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    async def get_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str = "arc"
    ) -> Optional[Dict[str, Any]]:
        """Get cached patch assessment data.

        Args:
            subscription_id: Azure subscription ID
            machine_name: VM/machine name
            vm_type: 'arc' or 'azure-vm'

        Returns:
            Cached assessment data or None if not found/expired
        """
        if not config.cosmos.enabled:
            return None

        try:
            await self._ensure_initialized()

            cache_key = self._make_cache_key(subscription_id, machine_name, vm_type)

            item = await self._container.read_item(
                item=cache_key,
                partition_key=subscription_id
            )

            if item:
                logger.debug(f"Cache HIT for patch assessment: {machine_name}")
                return item.get("assessment_data")

        except Exception as e:
            # Cache miss or error - return None to trigger fresh fetch
            logger.debug(f"Cache MISS for patch assessment {machine_name}: {e}")
            return None

    async def store_assessment(
        self,
        subscription_id: str,
        machine_name: str,
        vm_type: str,
        assessment_data: Dict[str, Any]
    ) -> bool:
        """Store patch assessment data in cache.

        Args:
            subscription_id: Azure subscription ID
            machine_name: VM/machine name
            vm_type: 'arc' or 'azure-vm'
            assessment_data: Assessment result to cache

        Returns:
            True if stored successfully, False otherwise
        """
        if not config.cosmos.enabled:
            return False

        try:
            await self._ensure_initialized()

            cache_key = self._make_cache_key(subscription_id, machine_name, vm_type)

            document = {
                "id": cache_key,
                "partitionKey": subscription_id,
                "subscription_id": subscription_id,
                "machine_name": machine_name.lower(),
                "vm_type": vm_type,
                "assessment_data": assessment_data,
                "cached_at": datetime.utcnow().isoformat(),
                # TTL is set at container level (3600s)
            }

            await self._container.upsert_item(document)
            logger.debug(f"Cached patch assessment for {machine_name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to cache patch assessment for {machine_name}: {e}")
            return False

    async def batch_get_assessments(
        self,
        machines: List[Dict[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """Get cached assessments for multiple machines in parallel.

        Args:
            machines: List of dicts with keys: subscription_id, machine_name, vm_type

        Returns:
            Dict mapping machine_name -> assessment_data for cache hits only
        """
        if not config.cosmos.enabled:
            return {}

        import asyncio

        results = {}

        async def fetch_one(machine_dict):
            assessment = await self.get_assessment(
                machine_dict["subscription_id"],
                machine_dict["machine_name"],
                machine_dict.get("vm_type", "arc")
            )
            if assessment:
                results[machine_dict["machine_name"].lower()] = assessment

        await asyncio.gather(*[fetch_one(m) for m in machines], return_exceptions=True)

        logger.info(f"Batch fetch: {len(results)}/{len(machines)} cache hits")
        return results


# Singleton instance
_patch_assessment_repo: Optional[PatchAssessmentRepository] = None


async def get_patch_assessment_repository() -> PatchAssessmentRepository:
    """Get or create the patch assessment repository singleton."""
    global _patch_assessment_repo

    if _patch_assessment_repo is not None:
        return _patch_assessment_repo

    if not config.cosmos.enabled:
        raise RuntimeError("Cosmos DB is not enabled - cannot use patch assessment caching")

    try:
        from utils.cosmos_client_factory import get_cosmos_client
    except ModuleNotFoundError:
        from app.agentic.eol.utils.cosmos_client_factory import get_cosmos_client

    cosmos_client = await get_cosmos_client()
    _patch_assessment_repo = PatchAssessmentRepository(
        cosmos_client,
        config.cosmos.database_name
    )

    return _patch_assessment_repo
