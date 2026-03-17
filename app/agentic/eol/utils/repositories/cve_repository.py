"""
CVERepository -- PostgreSQL repository for all CVE-domain queries.

Covers 16 queries from Phase 6 TARGET-SQL-CVE-DOMAIN.md:
  - Dashboard MVs (1a-1f)
  - CVE search, count, stats (2a-2c)
  - CVE detail, affected VMs, patches (3a-3c)
  - VM vulnerability overview, detail, MV refresh (4a-4b)
  - Write paths: upsert_cve, upsert_kb_cve_edges

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
# SQL Constants -- CVE Search (Phase 6 TARGET-SQL-CVE-DOMAIN.md)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 2a (BH-002+BH-003 fix)
QUERY_CVE_SEARCH = """
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
LIMIT $9;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 2b
QUERY_CVE_COUNT = """
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

# From: TARGET-SQL-CVE-DOMAIN.md Query 2c
QUERY_CVE_STATS = """
SELECT total_cves, critical, high, medium, low FROM mv_cve_dashboard_summary;
"""

# ---------------------------------------------------------------------------
# SQL Constants -- CVE Detail + Affected VMs + Patches
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 3a
QUERY_CVE_DETAIL = """
SELECT cve_id, description, cvss_v3_score, cvss_v3_severity, cvss_v2_score, cvss_v2_severity,
       vector_string_v3, vector_string_v2, cwe_ids, references, affected_products,
       sources, published_at, last_modified_at, synced_at, search_vector,
       exploitability_score, impact_score, attack_vector, attack_complexity
FROM cves
WHERE cve_id = $1;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 3b (BH-006+BH-007 fix)
QUERY_AFFECTED_VMS = """
SELECT d.vm_id, d.vm_name, d.severity, d.cvss_score, d.patch_status, d.kb_ids,
       v.resource_group, v.subscription_id, v.os_type, v.location
FROM mv_vm_cve_detail d
LEFT JOIN vms v ON d.vm_id = v.resource_id
WHERE d.cve_id = $1
  AND d.scan_id = latest_completed_scan_id()
  AND ($2::text IS NULL OR v.subscription_id::text = $2)
  AND ($3::text IS NULL OR v.resource_group = $3)
ORDER BY CASE d.severity
    WHEN 'CRITICAL' THEN 1
    WHEN 'HIGH' THEN 2
    WHEN 'MEDIUM' THEN 3
    WHEN 'LOW' THEN 4
    ELSE 5
END, d.cvss_score DESC
LIMIT $4 OFFSET $5;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 3c
QUERY_PATCHES_FOR_CVE = """
SELECT kb_number, cve_id, source, severity, title, fixed_version, last_seen, cached_at
FROM kb_cve_edges
WHERE cve_id = $1
ORDER BY source, kb_number;
"""

# ---------------------------------------------------------------------------
# SQL Constants -- VM Vulnerability Overview + Detail
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 4a (BH-008 fix)
QUERY_VULNERABILITY_OVERVIEW = """
SELECT vm_id, vm_name, vm_type, os_name, os_type, location, resource_group, subscription_id,
       total_cves, critical, high, medium, low,
       unpatched, unpatched_critical, unpatched_high,
       risk_level, eol_status, eol_date
FROM mv_vm_vulnerability_posture
WHERE ($1::text IS NULL OR risk_level = $1)
  AND ($2::text IS NULL OR os_type = $2)
ORDER BY total_cves DESC;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 4b
QUERY_VM_CVE_DETAIL = """
SELECT scan_id, vm_id, vm_name, cve_id, severity, cvss_score,
       patch_status, kb_ids, description, published_date
FROM mv_vm_cve_detail
WHERE vm_id = $1 AND scan_id = latest_completed_scan_id()
  AND ($2::text IS NULL OR severity = $2)
ORDER BY cvss_score DESC
LIMIT $3 OFFSET $4;
"""

# ---------------------------------------------------------------------------
# SQL Constants -- Write paths (sync jobs)
# ---------------------------------------------------------------------------

UPSERT_CVE = """
INSERT INTO cves (
    cve_id, description, published_at, last_modified_at,
    cvss_v2_score, cvss_v2_severity, vector_string_v2,
    cvss_v3_score, cvss_v3_severity, vector_string_v3,
    exploitability_score, impact_score,
    cwe_ids, affected_products, references, attack_vector, attack_complexity,
    sources, synced_at
) VALUES (
    $1, $2, $3, $4,
    $5, $6, $7,
    $8, $9, $10,
    $11, $12,
    $13, $14, $15, $16, $17,
    $18, NOW()
) ON CONFLICT (cve_id) DO UPDATE SET
    description = EXCLUDED.description,
    published_at = COALESCE(EXCLUDED.published_at, cves.published_at),
    last_modified_at = COALESCE(EXCLUDED.last_modified_at, cves.last_modified_at),
    cvss_v2_score = COALESCE(EXCLUDED.cvss_v2_score, cves.cvss_v2_score),
    cvss_v2_severity = COALESCE(EXCLUDED.cvss_v2_severity, cves.cvss_v2_severity),
    vector_string_v2 = COALESCE(EXCLUDED.vector_string_v2, cves.vector_string_v2),
    cvss_v3_score = COALESCE(EXCLUDED.cvss_v3_score, cves.cvss_v3_score),
    cvss_v3_severity = COALESCE(EXCLUDED.cvss_v3_severity, cves.cvss_v3_severity),
    vector_string_v3 = COALESCE(EXCLUDED.vector_string_v3, cves.vector_string_v3),
    exploitability_score = COALESCE(EXCLUDED.exploitability_score, cves.exploitability_score),
    impact_score = COALESCE(EXCLUDED.impact_score, cves.impact_score),
    cwe_ids = COALESCE(EXCLUDED.cwe_ids, cves.cwe_ids),
    affected_products = COALESCE(EXCLUDED.affected_products, cves.affected_products),
    references = COALESCE(EXCLUDED.references, cves.references),
    attack_vector = COALESCE(EXCLUDED.attack_vector, cves.attack_vector),
    attack_complexity = COALESCE(EXCLUDED.attack_complexity, cves.attack_complexity),
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

# ---------------------------------------------------------------------------
# SQL Constants -- Cache freshness (Phase 8 P8.6, TARGET-SQL-ADMIN-DOMAIN.md)
# ---------------------------------------------------------------------------

QUERY_MSRC_FRESHNESS = """
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM kb_cve_edges;
"""

# ---------------------------------------------------------------------------
# MV refresh tiers (P6.4 AGGREGATION-STRATEGY.md)
# ---------------------------------------------------------------------------

_MV_TIER_1 = ["mv_cve_dashboard_summary", "mv_cve_trending", "mv_cve_top_by_score"]
_MV_TIER_2 = ["mv_cve_top_by_affected_vms", "mv_cve_exposure", "mv_vm_vulnerability_posture", "mv_inventory_os_cve_counts"]
_MV_TIER_3 = ["mv_vm_cve_detail"]


class CVERepository:
    """PostgreSQL repository for all CVE-domain data access.

    Reads from 7 bootstrap materialized views + base tables.
    Writes for NVD sync (upsert_cve) and MSRC sync (upsert_kb_cve_edges).
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
    # CVE search, count, stats (Queries 2a-2c)
    # ------------------------------------------------------------------

    async def search_cves(self, keyword=None, severity=None, min_score=None, vendor=None, product=None, date_from=None, date_to=None, source=None, limit=50) -> List[Dict]:
        """Full-filter CVE search with FTS. Eliminates BH-002 + BH-003."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_CVE_SEARCH, keyword, severity, min_score, vendor, product, date_from, date_to, source, limit)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to search CVEs", exc_info=True)
            return []

    async def count_cves(self, keyword=None, severity=None, min_score=None, vendor=None, product=None, date_from=None, date_to=None, source=None) -> int:
        """Count CVEs matching filter criteria. Query 2b."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_CVE_COUNT, keyword, severity, min_score, vendor, product, date_from, date_to, source)
                return row["total"] if row else 0
        except asyncpg.PostgresError as e:
            logger.error("Failed to count CVEs", exc_info=True)
            return 0

    async def get_cve_stats(self) -> Dict:
        """Quick CVE stats from mv_cve_dashboard_summary. Query 2c."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_CVE_STATS)
                return dict(row) if row else {}
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch CVE stats", exc_info=True)
            return {}

    # ------------------------------------------------------------------
    # CVE detail + affected VMs + patches (Queries 3a-3c)
    # ------------------------------------------------------------------

    async def get_cve(self, cve_id: str) -> Dict:
        """Single CVE detail by PK. Query 3a."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_CVE_DETAIL, cve_id)
                return dict(row) if row else {}
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch CVE %s", cve_id, exc_info=True)
            return {}

    async def get_affected_vms_for_cve(self, cve_id: str, subscription_id: str = None, resource_group: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """VMs affected by a CVE from mv_vm_cve_detail. Eliminates BH-006 + BH-007."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_AFFECTED_VMS, cve_id, subscription_id, resource_group, limit, offset)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch affected VMs for %s", cve_id, exc_info=True)
            return []

    async def get_patches_for_cve(self, cve_id: str) -> List[Dict]:
        """Patches/KB edges for a CVE from kb_cve_edges. Query 3c."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_PATCHES_FOR_CVE, cve_id)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch patches for %s", cve_id, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # VM vulnerability overview + detail (Queries 4a-4b)
    # ------------------------------------------------------------------

    async def get_vulnerability_overview(self, risk_level: str = None, os_type: str = None) -> List[Dict]:
        """VM vulnerability overview from mv_vm_vulnerability_posture. Eliminates BH-008."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_VULNERABILITY_OVERVIEW, risk_level, os_type)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch vulnerability overview", exc_info=True)
            return []

    async def get_vm_cve_detail(self, vm_id: str, severity: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """CVE details for a specific VM from mv_vm_cve_detail. Query 4b."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(QUERY_VM_CVE_DETAIL, vm_id, severity, limit, offset)
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch VM CVE detail for %s", vm_id, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # MV refresh (3-tier per P6.4 AGGREGATION-STRATEGY.md)
    # ------------------------------------------------------------------

    async def refresh_materialized_views(self) -> Dict:
        """Refresh all bootstrap MVs in 3 tiers (independent, scan-scoped, detail).

        Returns dict with refreshed/failed lists and duration_ms.
        """
        start = time.monotonic()
        refreshed: List[str] = []
        failed: List[str] = []

        for tier_name, mv_list in [("tier1", _MV_TIER_1), ("tier2", _MV_TIER_2), ("tier3", _MV_TIER_3)]:
            for mv_name in mv_list:
                try:
                    async with self.pool.acquire() as conn:
                        await conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name}")
                    refreshed.append(mv_name)
                    logger.info("Refreshed MV %s (%s)", mv_name, tier_name)
                except asyncpg.PostgresError as e:
                    failed.append(mv_name)
                    logger.error("Failed to refresh MV %s (%s)", mv_name, tier_name, exc_info=True)

        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        result = {"refreshed": refreshed, "failed": failed, "duration_ms": elapsed_ms}
        logger.info("MV refresh complete: %d refreshed, %d failed in %.1fms", len(refreshed), len(failed), elapsed_ms)
        return result

    # ------------------------------------------------------------------
    # Write paths -- sync jobs
    # ------------------------------------------------------------------

    async def upsert_cve(self, cve_data: Dict) -> None:
        """Upsert a CVE record from NVD/vendor sync. Re-raises on write error."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                UPSERT_CVE,
                cve_data.get("cve_id"), cve_data.get("description"),
                cve_data.get("published_at"), cve_data.get("last_modified_at"),
                cve_data.get("cvss_v2_score"), cve_data.get("cvss_v2_severity"), cve_data.get("vector_string_v2"),
                cve_data.get("cvss_v3_score"), cve_data.get("cvss_v3_severity"), cve_data.get("vector_string_v3"),
                cve_data.get("exploitability_score"), cve_data.get("impact_score"),
                cve_data.get("cwe_ids"), cve_data.get("affected_products"), cve_data.get("references"),
                cve_data.get("attack_vector"), cve_data.get("attack_complexity"),
                cve_data.get("sources"),
            )

    async def upsert_kb_cve_edges(self, edges: List[Dict]) -> int:
        """Bulk upsert KB-CVE edges from MSRC sync. Returns count of upserted rows."""
        count = 0
        async with self.pool.acquire() as conn:
            for edge in edges:
                await conn.execute(
                    UPSERT_KB_CVE_EDGE,
                    edge.get("kb_number"), edge.get("cve_id"),
                    edge.get("source", "microsoft"), edge.get("severity"),
                    edge.get("title"), edge.get("fixed_version"), edge.get("last_seen"),
                )
                count += 1
        return count

    # ------------------------------------------------------------------
    # Cache freshness (Phase 8 P8.6, TARGET-SQL-ADMIN-DOMAIN.md)
    # ------------------------------------------------------------------

    async def get_msrc_freshness(self) -> Dict:
        """MSRC cache freshness aggregate for /api/cache/status."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_MSRC_FRESHNESS)
                return dict(row) if row else {"row_count": 0}
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch MSRC freshness", exc_info=True)
            return {"row_count": 0}
