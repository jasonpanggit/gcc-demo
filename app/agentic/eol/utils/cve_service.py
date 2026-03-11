"""
CVE service - orchestrates cache, repository, and aggregator.

Provides high-level CVE operations with L1/L2 caching.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Optional, List, Dict, Any

try:
    from models.cve_models import UnifiedCVE
    from utils.cve_cache import CVECache
    from utils.cve_cosmos_repository import CVECosmosRepository
    from utils.cve_data_aggregator import CVEDataAggregator
    from utils.cve_id_utils import is_valid_cve_id
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.cve_cache import CVECache
    from app.agentic.eol.utils.cve_cosmos_repository import CVECosmosRepository
    from app.agentic.eol.utils.cve_data_aggregator import CVEDataAggregator
    from app.agentic.eol.utils.cve_id_utils import is_valid_cve_id
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


def _affected_product_keyword_haystack(cve: UnifiedCVE) -> str:
    parts: List[str] = []
    for product in cve.affected_products:
        parts.append(re.sub(r"[_-]+", " ", str(product.vendor or "")))
        parts.append(re.sub(r"[_-]+", " ", str(product.product or "")))
        parts.append(re.sub(r"[_-]+", " ", str(product.version or "")))
    return " ".join(parts).lower()


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


def _extract_live_nvd_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Map service filters to NVD live-search parameters when supported."""
    nvd_filters: Dict[str, Any] = {}

    cpe_name = (filters.get("cpe_name") or filters.get("cpeName") or "").strip()
    if cpe_name:
        nvd_filters["cpeName"] = cpe_name

    return nvd_filters


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
        aggregator: CVEDataAggregator,
        kb_cve_edge_repository=None,
    ):
        self.cache = cache
        self.repository = repository
        self.aggregator = aggregator
        self.kb_cve_edge_repository = kb_cve_edge_repository
        logger.info("CVEService initialized with L1/L2 caching")

    async def _persist_cve(self, cve: UnifiedCVE) -> None:
        """Persist a CVE and its reverse KB edges when configured."""
        await self.repository.upsert_cve(cve)
        if self.kb_cve_edge_repository is not None:
            await self.kb_cve_edge_repository.sync_cve_edges(cve)

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

        if not is_valid_cve_id(cve_id):
            logger.debug("Skipping external fetch for non-standard CVE identifier %s", cve_id)
            return None

        # Cache miss or force refresh: fetch from external APIs
        logger.info(f"Fetching CVE {cve_id} from external sources...")
        cve = await self.aggregator.fetch_and_merge_cve(cve_id)

        if cve:
            # Write to L2 (Cosmos DB) for durability
            await self._persist_cve(cve)

            # Write to L1 (memory) for fast subsequent reads
            self.cache.set(cve_id, cve)

            logger.info(f"CVE {cve_id} fetched and cached")

        return cve

    async def search_cves(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "published_date",
        sort_order: str = "desc",
        allow_live_fallback: bool = True,
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
            cached_results = await self.repository.query_cves(
                filters,
                limit,
                offset,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        except Exception as e:
            logger.debug("CVE repository query unavailable, continuing with live fallback: %s", e)
            cached_results = []

        if cached_results:
            return cached_results

        # Live fallback path for mock mode and cold-start environments.
        if not allow_live_fallback:
            return cached_results

        keyword = (filters.get("keyword") or "").strip()
        live_nvd_filters = _extract_live_nvd_filters(filters)
        if not keyword and not live_nvd_filters:
            return cached_results

        if keyword:
            logger.info("CVE search cache miss; fetching live results for keyword '%s'", keyword)
        else:
            logger.info("CVE search cache miss; fetching live results for NVD filters %s", live_nvd_filters)

        live_results = await self.sync_live_cves(
            query=keyword or None,
            limit=limit,
            source=filters.get("source"),
            nvd_filters=live_nvd_filters,
            populate_l1=True,
        )

        # Apply local filter checks to keep behavior close to repository query semantics.
        filtered_live_results = [
            cve for cve in live_results
            if self._matches_filters(cve, filters)
        ]

        filtered_live_results = self._sort_cves(filtered_live_results, sort_by, sort_order)

        if offset < 0:
            offset = 0
        if limit < 0:
            limit = 0

        return filtered_live_results[offset:offset + limit]

    async def sync_live_cves(
        self,
        *,
        query: Optional[str] = None,
        limit: Optional[int] = 100,
        source: Optional[str] = None,
        nvd_filters: Optional[Dict[str, Any]] = None,
        populate_l1: bool = False,
    ) -> List[UnifiedCVE]:
        """Fetch live CVEs from upstream sources and persist them to L2 cache."""
        live_results = await self.aggregator.search_and_merge_cves(
            query=query,
            limit=limit,
            source=source,
            nvd_filters=nvd_filters,
        )

        for cve in live_results:
            try:
                await self._persist_cve(cve)
            except Exception as e:
                logger.debug("CVE live sync upsert skipped for %s: %s", cve.cve_id, e)

            if populate_l1:
                self.cache.set(cve.cve_id, cve)

        return live_results

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
            haystack = f"{cve.cve_id} {cve.description} {_affected_product_keyword_haystack(cve)}".lower()
            if keyword not in haystack:
                return False

        return True

    def _sort_cves(
        self,
        cves: List[UnifiedCVE],
        sort_by: str,
        sort_order: str,
    ) -> List[UnifiedCVE]:
        reverse = str(sort_order).lower() != "asc"
        field = (sort_by or "published_date").lower()

        severity_rank = {
            "UNKNOWN": 0,
            "LOW": 1,
            "MEDIUM": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }

        def score_for(cve: UnifiedCVE) -> float:
            if cve.cvss_v3 and cve.cvss_v3.base_score is not None:
                return cve.cvss_v3.base_score
            if cve.cvss_v2 and cve.cvss_v2.base_score is not None:
                return cve.cvss_v2.base_score
            return -1.0

        def severity_for(cve: UnifiedCVE) -> str:
            if cve.cvss_v3 and cve.cvss_v3.base_severity:
                return cve.cvss_v3.base_severity.upper()
            if cve.cvss_v2 and cve.cvss_v2.base_severity:
                return cve.cvss_v2.base_severity.upper()
            return "UNKNOWN"

        if field == "cve_id":
            key_fn = lambda cve: cve.cve_id
        elif field == "severity":
            key_fn = lambda cve: (severity_rank.get(severity_for(cve), 0), score_for(cve), cve.cve_id)
        elif field == "cvss_score":
            key_fn = lambda cve: (score_for(cve), cve.cve_id)
        elif field == "last_modified_date":
            key_fn = lambda cve: (cve.last_modified_date, cve.cve_id)
        else:
            key_fn = lambda cve: (cve.published_date, cve.cve_id)

        return sorted(cves, key=key_fn, reverse=reverse)

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
                await self._persist_cve(cve)
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


# Singleton pattern
_cve_service_instance: Optional[CVEService] = None


async def get_cve_service() -> CVEService:
    """Get the global CVE service instance, initializing if needed.

    Returns:
        Initialized CVEService instance
    """
    global _cve_service_instance

    if _cve_service_instance is None:
        cache = CVECache(maxsize=1000, ttl_seconds=300)
        repository = CVECosmosRepository()
        await repository.ensure_initialized()
        aggregator = CVEDataAggregator()
        _cve_service_instance = CVEService(cache=cache, repository=repository, aggregator=aggregator)
        logger.info("CVE service singleton initialized")

    return _cve_service_instance
