"""
CVERepository -- PostgreSQL repository for all CVE-domain queries.

Covers 16 queries from Phase 6 TARGET-SQL-CVE-DOMAIN.md:
  - Dashboard MVs (1a-1f)
  - CVE search, count, stats (2a-2c)
  - CVE detail, affected VMs, patches (3a-3c)
  - VM vulnerability overview, detail, MV refresh (4a-4b)
  - Write paths: upsert_cve, upsert_kb_cve_edges

Phase 8 (P8.6): Added write paths, MV refresh, MSRC cache freshness.

Eliminates: BH-001, BH-002, BH-003, BH-004, BH-006, BH-007, BH-008
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL Constants -- Dashboard MV reads (Phase 6 TARGET-SQL-CVE-DOMAIN.md)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 1a
QUERY_DASHBOARD_SUMMARY = """
SELECT total_cves, critical, high, medium, low,
       age_0_7, age_8_30, age_31_90, age_over_90,
       avg_cvss, max_cvss, last_updated
FROM mv_cve_dashboard_summary;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1b
QUERY_TRENDING = """
SELECT bucket_date, total_count, critical_count, high_count, medium_count, low_count
FROM mv_cve_trending
WHERE bucket_date >= $1
ORDER BY bucket_date ASC;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1c
QUERY_TOP_BY_SCORE = """
SELECT cve_id, description, cvss_v3_score, severity, affected_vms, published_at
FROM mv_cve_top_by_score
ORDER BY cvss_v3_score DESC
LIMIT $1;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1d
QUERY_VM_POSTURE = """
SELECT vm_id, vm_name, os_name, risk_level, total_cves, critical, high, eol_status
FROM mv_vm_vulnerability_posture
ORDER BY total_cves DESC
LIMIT $1;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1e (BH-004 fix)
QUERY_OS_CVE_BREAKDOWN = """
SELECT os_name,
       COUNT(*) AS vm_count,
       SUM(total_cves) AS total_cve_count,
       SUM(critical) AS critical_count,
       SUM(high) AS high_count
FROM mv_vm_vulnerability_posture
GROUP BY os_name
ORDER BY total_cve_count DESC;
"""

# ---------------------------------------------------------------------------
# SQL Constants -- Write paths (sync jobs, Phase 8 P8.6)
# ---------------------------------------------------------------------------

UPSERT_CVE = """
INSERT INTO cves (
    cve_id, description, published_at, modified_at,
    cvss_v2_score, cvss_v2_severity, cvss_v2_vector,
    cvss_v3_score, cvss_v3_severity, cvss_v3_vector,
    cvss_v3_exploitability, cvss_v3_impact,
    cwe_ids, affected_products, "references", vendor_metadata,
    sources, synced_at
) VALUES (
    $1, $2, $3, $4,
    $5, $6, $7,
    $8, $9, $10,
    $11, $12,
    $13, $14, $15, $16,
    $17, NOW()
) ON CONFLICT (cve_id) DO UPDATE SET
    description = EXCLUDED.description,
    published_at = COALESCE(EXCLUDED.published_at, cves.published_at),
    modified_at = COALESCE(EXCLUDED.modified_at, cves.modified_at),
    cvss_v2_score = COALESCE(EXCLUDED.cvss_v2_score, cves.cvss_v2_score),
    cvss_v2_severity = COALESCE(EXCLUDED.cvss_v2_severity, cves.cvss_v2_severity),
    cvss_v2_vector = COALESCE(EXCLUDED.cvss_v2_vector, cves.cvss_v2_vector),
    cvss_v3_score = COALESCE(EXCLUDED.cvss_v3_score, cves.cvss_v3_score),
    cvss_v3_severity = COALESCE(EXCLUDED.cvss_v3_severity, cves.cvss_v3_severity),
    cvss_v3_vector = COALESCE(EXCLUDED.cvss_v3_vector, cves.cvss_v3_vector),
    cvss_v3_exploitability = COALESCE(EXCLUDED.cvss_v3_exploitability, cves.cvss_v3_exploitability),
    cvss_v3_impact = COALESCE(EXCLUDED.cvss_v3_impact, cves.cvss_v3_impact),
    cwe_ids = COALESCE(EXCLUDED.cwe_ids, cves.cwe_ids),
    affected_products = COALESCE(EXCLUDED.affected_products, cves.affected_products),
    "references" = COALESCE(EXCLUDED."references", cves."references"),
    vendor_metadata = COALESCE(EXCLUDED.vendor_metadata, cves.vendor_metadata),
    sources = EXCLUDED.sources,
    synced_at = NOW();
"""

UPSERT_KB_CVE_EDGE = """
INSERT INTO kb_cve_edges (
    kb_number, cve_id, source, severity, title, fixed_version, last_seen, cached_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
ON CONFLICT (kb_number, cve_id, source) DO UPDATE SET
    severity = COALESCE(EXCLUDED.severity, kb_cve_edges.severity),
    title = COALESCE(EXCLUDED.title, kb_cve_edges.title),
    fixed_version = COALESCE(EXCLUDED.fixed_version, kb_cve_edges.fixed_version),
    last_seen = EXCLUDED.last_seen,
    cached_at = NOW();
"""

# From: TARGET-SQL-ADMIN-DOMAIN.md MSRC freshness
QUERY_MSRC_FRESHNESS = """
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM kb_cve_edges;
"""

# ---------------------------------------------------------------------------
# SQL Constants -- CVE search + count (Phase 6 Queries 2a-2b)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 2a (BH-002 fix, offset/limit pagination)
QUERY_SEARCH_CVES = """
SELECT c.cve_id, c.description, c.cvss_v3_score, c.cvss_v3_severity,
       c.published_at, c.affected_products, c.sources,
       COALESCE(e.affected_vms, 0) AS affected_vms
FROM cves c
LEFT JOIN mv_cve_exposure e ON e.cve_id = c.cve_id
WHERE 1=1
  AND ($1::text IS NULL OR c.search_vector @@ to_tsquery('english', $1))
  AND ($2::text IS NULL OR c.cvss_v3_severity = $2)
  AND ($3::numeric IS NULL OR c.cvss_v3_score >= $3)
  AND ($4::text IS NULL OR c.affected_products @> jsonb_build_object('vendor', $4))
  AND ($5::text IS NULL OR c.affected_products @> jsonb_build_object('product', $5))
  AND ($6::timestamptz IS NULL OR c.published_at >= $6)
  AND ($7::timestamptz IS NULL OR c.published_at <= $7)
  AND ($8::text IS NULL OR $8 = ANY(c.sources))
ORDER BY c.published_at DESC, c.cve_id DESC
LIMIT $9 OFFSET $10;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 2b
QUERY_COUNT_CVES = """
SELECT COUNT(*) AS total
FROM cves c
WHERE 1=1
  AND ($1::text IS NULL OR c.search_vector @@ to_tsquery('english', $1))
  AND ($2::text IS NULL OR c.cvss_v3_severity = $2)
  AND ($3::numeric IS NULL OR c.cvss_v3_score >= $3)
  AND ($4::text IS NULL OR c.affected_products @> jsonb_build_object('vendor', $4))
  AND ($5::text IS NULL OR c.affected_products @> jsonb_build_object('product', $5))
  AND ($6::timestamptz IS NULL OR c.published_at >= $6)
  AND ($7::timestamptz IS NULL OR c.published_at <= $7)
  AND ($8::text IS NULL OR $8 = ANY(c.sources));
"""

# ---------------------------------------------------------------------------
# MV refresh tiers (P6.4 AGGREGATION-STRATEGY.md, bootstrap MVs only)
# ---------------------------------------------------------------------------

_MV_TIER_1 = ["mv_cve_dashboard_summary", "mv_cve_trending", "mv_cve_top_by_score"]
_MV_TIER_2 = [
    "mv_cve_top_by_affected_vms",
    "mv_cve_exposure",
    "mv_vm_vulnerability_posture",
    "mv_inventory_os_cve_counts",
]
_MV_TIER_3 = ["mv_vm_cve_detail"]


class CVERepository:
    """PostgreSQL repository for all CVE-domain data access.

    All methods are async and return Dict/List[Dict].
    Each method has its own try/except for graceful error handling.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Dashboard MV reads (Queries 1a-1e)
    # ------------------------------------------------------------------

    async def get_dashboard_summary(self) -> Dict:
        """Dashboard summary from mv_cve_dashboard_summary. Eliminates BH-001."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_DASHBOARD_SUMMARY)
                return dict(row) if row else {}
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch dashboard summary", exc_info=True)
            return {}

    async def get_trending_data(self, days_back: int = 90) -> List[Dict]:
        """Trending chart data from mv_cve_trending. Query 1b."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_TRENDING, cutoff)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch trending data", exc_info=True)
            return []

    async def get_top_cves_by_score(self, limit: int = 10) -> List[Dict]:
        """Top CVEs by CVSS score from mv_cve_top_by_score. Query 1c."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_TOP_BY_SCORE, limit)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch top CVEs by score", exc_info=True)
            return []

    async def get_vm_posture_summary(self, limit: int = 20) -> List[Dict]:
        """VM posture summary from mv_vm_vulnerability_posture. Query 1d."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_VM_POSTURE, limit)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch VM posture summary", exc_info=True)
            return []

    async def get_os_cve_breakdown(self) -> List[Dict]:
        """OS CVE breakdown from mv_vm_vulnerability_posture. Eliminates BH-004."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_OS_CVE_BREAKDOWN)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch OS CVE breakdown", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Write paths -- sync jobs (Phase 8 P8.6)
    # ------------------------------------------------------------------

    async def upsert_cve(self, cve_data: Dict) -> None:
        """Upsert a CVE record from NVD/vendor sync. Re-raises on error."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                UPSERT_CVE,
                cve_data.get("cve_id"),
                cve_data.get("description"),
                cve_data.get("published_at"),
                cve_data.get("modified_at"),
                cve_data.get("cvss_v2_score"),
                cve_data.get("cvss_v2_severity"),
                cve_data.get("cvss_v2_vector"),
                cve_data.get("cvss_v3_score"),
                cve_data.get("cvss_v3_severity"),
                cve_data.get("cvss_v3_vector"),
                cve_data.get("cvss_v3_exploitability"),
                cve_data.get("cvss_v3_impact"),
                cve_data.get("cwe_ids"),
                cve_data.get("affected_products"),
                cve_data.get("references"),
                cve_data.get("vendor_metadata"),
                cve_data.get("sources"),
            )

    async def upsert_kb_cve_edges(self, edges: List[Dict]) -> int:
        """Bulk upsert KB-CVE edges from MSRC sync. Returns count upserted."""
        count = 0
        async with self.pool.acquire() as conn:
            for edge in edges:
                await conn.execute(
                    UPSERT_KB_CVE_EDGE,
                    edge.get("kb_number"),
                    edge.get("cve_id"),
                    edge.get("source", "microsoft"),
                    edge.get("severity"),
                    edge.get("title"),
                    edge.get("fixed_version"),
                    edge.get("last_seen"),
                )
                count += 1
        return count

    # ------------------------------------------------------------------
    # MV refresh (3-tier per P6.4 AGGREGATION-STRATEGY.md)
    # ------------------------------------------------------------------

    async def refresh_materialized_views(self) -> Dict:
        """Refresh all bootstrap MVs in 3 tiers.

        Uses bootstrap MV list only -- the 3 dropped migration-011 MVs
        are NOT included.

        Returns dict with refreshed/failed lists and duration.
        """
        start = time.monotonic()
        refreshed: List[str] = []
        failed: List[str] = []

        for tier_name, mv_list in [
            ("tier1", _MV_TIER_1),
            ("tier2", _MV_TIER_2),
            ("tier3", _MV_TIER_3),
        ]:
            for mv_name in mv_list:
                try:
                    async with self.pool.acquire() as conn:
                        await conn.execute(
                            f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name}"
                        )
                    refreshed.append(mv_name)
                    logger.info("Refreshed MV %s (%s)", mv_name, tier_name)
                except asyncpg.PostgresError:
                    failed.append(mv_name)
                    logger.error(
                        "Failed to refresh MV %s (%s)",
                        mv_name,
                        tier_name,
                        exc_info=True,
                    )

        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        result = {
            "refreshed": refreshed,
            "failed": failed,
            "duration_ms": elapsed_ms,
        }
        logger.info(
            "MV refresh complete: %d refreshed, %d failed in %.1fms",
            len(refreshed),
            len(failed),
            elapsed_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Cache freshness (Phase 8 P8.6, TARGET-SQL-ADMIN-DOMAIN.md)
    # ------------------------------------------------------------------

    async def get_msrc_freshness(self) -> Dict:
        """MSRC cache freshness aggregate for /api/cache/status."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_MSRC_FRESHNESS)
                return dict(row) if row else {"row_count": 0}
        except asyncpg.PostgresError:
            logger.error("Failed to fetch MSRC freshness", exc_info=True)
            return {"row_count": 0}

    # ------------------------------------------------------------------
    # CVE search + count (Queries 2a-2b)
    # ------------------------------------------------------------------

    async def search_cves(
        self,
        keyword: Optional[str] = None,
        severity: Optional[str] = None,
        min_score: Optional[float] = None,
        vendor: Optional[str] = None,
        product: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """CVE search with full filters. Phase 6 Query 2a. Eliminates BH-002."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    QUERY_SEARCH_CVES,
                    keyword, severity, min_score,
                    vendor, product,
                    date_from, date_to,
                    source,
                    limit, offset,
                )
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to search CVEs", exc_info=True)
            return []

    async def count_cves(
        self,
        keyword: Optional[str] = None,
        severity: Optional[str] = None,
        min_score: Optional[float] = None,
        vendor: Optional[str] = None,
        product: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        source: Optional[str] = None,
    ) -> int:
        """CVE count for pagination. Phase 6 Query 2b."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    QUERY_COUNT_CVES,
                    keyword, severity, min_score,
                    vendor, product,
                    date_from, date_to,
                    source,
                )
                return row["total"] if row else 0
        except asyncpg.PostgresError as e:
            logger.error("Failed to count CVEs", exc_info=True)
            return 0
