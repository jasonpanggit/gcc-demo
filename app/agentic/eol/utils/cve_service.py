"""
CVE service - orchestrates cache, repository, and aggregator.

Provides high-level CVE operations with L1/L2 caching.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

try:
    from models.cve_models import UnifiedCVE
    from utils.cve_cache import CVECache
    from utils.cve_cosmos_repository import CVECosmosRepository
    from utils.cve_data_aggregator import CVEDataAggregator
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.cve_cache import CVECache
    from app.agentic.eol.utils.cve_cosmos_repository import CVECosmosRepository
    from app.agentic.eol.utils.cve_data_aggregator import CVEDataAggregator
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


def _iso_to_datetime(value: Any) -> Optional[datetime]:
    """Best-effort ISO datetime parser used for filter checks."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


class CVEService:
    """High-level CVE service with L1/L2 caching.

    Cache hierarchy:
    - L1: In-memory TTLCache (1000 CVEs, 1 hour TTL)
    - L2: Cosmos DB (persistent)
    - Source: External APIs (CVE.org, NVD, vendor feeds)

    Read path: L1 → L2 → APIs
    Write path: APIs → L2 → L1
    """

    def __init__(
        self,
        cache: CVECache,
        repository: CVECosmosRepository,
        aggregator: CVEDataAggregator
    ):
        self.cache = cache
        self.repository = repository
        self.aggregator = aggregator
        logger.info("CVEService initialized with L1/L2 caching")

    async def get_cve(
        self,
        cve_id: str,
        force_refresh: bool = False
    ) -> Optional[UnifiedCVE]:
        """Get CVE with L1/L2 cache-aside pattern.

        Args:
            cve_id: CVE identifier
            force_refresh: Skip cache and fetch from APIs

        Returns:
            UnifiedCVE model or None if not found

        Cache flow:
        1. Check L1 cache (memory)
        2. If miss, check L2 cache (Cosmos DB)
        3. If miss, fetch from external APIs
        4. Populate L2 and L1 on miss
        """
        cve_id = cve_id.upper()

        if not force_refresh:
            # L1 cache check (in-memory)
            cached = self.cache.get(cve_id)
            if cached:
                logger.debug(f"CVE {cve_id} served from L1 cache")
                return cached

            # L2 cache check (Cosmos DB)
            cached = await self.repository.get_cve(cve_id)
            if cached:
                logger.debug(f"CVE {cve_id} served from L2 cache (Cosmos DB)")
                # Populate L1 for subsequent reads
                self.cache.set(cve_id, cached)
                return cached

        # Cache miss or force refresh: fetch from external APIs
        logger.info(f"Fetching CVE {cve_id} from external sources...")
        cve = await self.aggregator.fetch_and_merge_cve(cve_id)

        if cve:
            # Write to L2 (Cosmos DB) for durability
            await self.repository.upsert_cve(cve)

            # Write to L1 (memory) for fast subsequent reads
            self.cache.set(cve_id, cve)

            logger.info(f"CVE {cve_id} fetched and cached")

        return cve

    async def search_cves(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0
    ) -> List[UnifiedCVE]:
        """Search CVEs with filters.

        Note: Search always hits L2 (Cosmos DB), not L1.
        L1 cache is for single CVE lookups only.

        Args:
            filters: Query filters (severity, CVSS range, dates, keyword, source)
            limit: Max results
            offset: Pagination offset

        Returns:
            List of UnifiedCVE models
        """
        logger.debug(f"Searching CVEs with filters: {filters}")
        try:
            cached_results = await self.repository.query_cves(filters, limit, offset)
        except Exception as e:
            logger.debug("CVE repository query unavailable, continuing with live fallback: %s", e)
            cached_results = []

        if cached_results:
            return cached_results

        # Live fallback path for mock mode and cold-start environments.
        keyword = (filters.get("keyword") or "").strip()
        if not keyword:
            return cached_results

        logger.info("CVE search cache miss; fetching live results for keyword '%s'", keyword)
        live_results = await self.aggregator.search_and_merge_cves(
            query=keyword,
            limit=limit,
            source=filters.get("source")
        )

        # Apply local filter checks to keep behavior close to repository query semantics.
        filtered_live_results = [
            cve for cve in live_results
            if self._matches_filters(cve, filters)
        ]

        # Persist to L2 when available and always populate L1 cache.
        for cve in filtered_live_results:
            try:
                await self.repository.upsert_cve(cve)
            except Exception as e:
                # In mock mode Cosmos may be unavailable; still return live data.
                logger.debug("CVE live fallback upsert skipped for %s: %s", cve.cve_id, e)

            self.cache.set(cve.cve_id, cve)

        return filtered_live_results[:limit]

    async def count_cves(self, filters: Dict[str, Any]) -> int:
        """Count cached CVEs matching the supplied filters."""
        try:
            return await self.repository.count_cves(filters)
        except Exception as e:
            logger.debug("CVE repository count unavailable: %s", e)
            return 0

    def _matches_filters(self, cve: UnifiedCVE, filters: Dict[str, Any]) -> bool:
        """Apply repository-like filtering checks to live-fetched CVEs."""
        severity = filters.get("severity")
        if severity:
            cve_severity = (cve.cvss_v3.base_severity if cve.cvss_v3 else "") or ""
            if cve_severity.upper() != str(severity).upper():
                return False

        min_score = filters.get("min_score")
        if min_score is not None:
            score = cve.cvss_v3.base_score if cve.cvss_v3 else None
            if score is None or score < float(min_score):
                return False

        max_score = filters.get("max_score")
        if max_score is not None:
            score = cve.cvss_v3.base_score if cve.cvss_v3 else None
            if score is None or score > float(max_score):
                return False

        published_after = _iso_to_datetime(filters.get("published_after"))
        if published_after and cve.published_date < published_after:
            return False

        published_before = _iso_to_datetime(filters.get("published_before"))
        if published_before and cve.published_date > published_before:
            return False

        source = filters.get("source")
        if source and source not in cve.sources:
            return False

        vendor_filter = (filters.get("vendor") or "").strip().lower()
        if vendor_filter:
            if not any((p.vendor or "").lower().find(vendor_filter) != -1 for p in cve.affected_products):
                return False

        product_filter = (filters.get("product") or "").strip().lower()
        if product_filter:
            if not any((p.product or "").lower().find(product_filter) != -1 for p in cve.affected_products):
                return False

        keyword = (filters.get("keyword") or "").strip().lower()
        if keyword:
            haystack = f"{cve.cve_id} {cve.description}".lower()
            if keyword not in haystack:
                return False

        return True

    async def sync_cve(self, cve_id: str) -> Optional[UnifiedCVE]:
        """Force sync CVE from external sources.

        Bypasses cache, fetches from APIs, updates L2 and L1.

        Args:
            cve_id: CVE identifier to sync

        Returns:
            Updated UnifiedCVE model or None if not found
        """
        return await self.get_cve(cve_id, force_refresh=True)

    async def sync_recent_cves(
        self,
        since_date: datetime,
        limit: Optional[int] = None
    ) -> int:
        """Sync CVEs modified since date.

        Fetches from external sources and updates L2 cache.
        Does not populate L1 (too many CVEs for memory cache).

        Args:
            since_date: Fetch CVEs modified after this date
            limit: Max CVEs to sync

        Returns:
            Number of CVEs synced
        """
        logger.info(f"Syncing CVEs modified since {since_date.isoformat()}")

        cves = await self.aggregator.fetch_cves_since(since_date, limit)

        # Upsert to Cosmos DB
        synced_count = 0
        for cve in cves:
            try:
                await self.repository.upsert_cve(cve)
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to upsert CVE {cve.cve_id}: {e}")

        logger.info(f"Synced {synced_count}/{len(cves)} CVEs to Cosmos DB")
        return synced_count

    def invalidate_cache(self, cve_id: str) -> None:
        """Invalidate L1 cache for a CVE.

        Use when CVE is updated in L2 (Cosmos DB).

        Args:
            cve_id: CVE identifier to invalidate
        """
        self.cache.invalidate(cve_id)

    def clear_cache(self) -> None:
        """Clear entire L1 cache.

        Use when making bulk updates to Cosmos DB.
        """
        self.cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get L1 cache statistics.

        Returns:
            Cache size, maxsize, TTL, etc.
        """
        return self.cache.stats()

    async def close(self):
        """Close aggregator clients."""
        await self.aggregator.close()
