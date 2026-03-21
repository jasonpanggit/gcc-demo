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
    from app.agentic.eol.models.cve_models import UnifiedCVE
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]
    from models.cve_models import UnifiedCVE  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL Constants -- Dashboard MV reads (Phase 6 TARGET-SQL-CVE-DOMAIN.md)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 1a
QUERY_DASHBOARD_SUMMARY = """
SELECT total_cves, critical, high, medium, low,
       age_0_7, age_8_30, age_31_90, age_90_plus AS age_over_90,
       NULL::numeric AS avg_cvss,
       NULL::numeric AS max_cvss,
       last_updated
FROM mv_cve_dashboard_summary;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1b
QUERY_TRENDING = """
SELECT bucket_date,
       cve_count AS total_count,
       critical_count,
       high_count,
       0::bigint AS medium_count,
       0::bigint AS low_count
FROM mv_cve_trending
WHERE bucket_date >= $1
ORDER BY bucket_date ASC;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1c
QUERY_TOP_BY_SCORE = """
SELECT score.cve_id,
       score.description,
       score.cvss_v3_score,
       score.severity,
       COALESCE(exposure.affected_vms, 0) AS affected_vms,
       score.published_at
FROM mv_cve_top_by_score score
LEFT JOIN mv_cve_exposure exposure ON exposure.cve_id = score.cve_id
ORDER BY score.cvss_v3_score DESC
LIMIT $1;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 1d
QUERY_VM_POSTURE = """
SELECT vm_id, vm_name, vm_type, os_name, os_version, os_type,
       location, resource_group, subscription_id, last_synced_at,
       risk_level, total_cves, critical, high, medium, low,
       unpatched, unpatched_critical, unpatched_high, eol_status
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
    kb_number, cve_id, source, os_family, advisory_id,
    affected_pkgs, fixed_pkgs, update_id, document_title, cvrf_url,
    published_date, severity, last_seen, cached_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
ON CONFLICT (kb_number, cve_id, source) DO UPDATE SET
    os_family = COALESCE(EXCLUDED.os_family, kb_cve_edges.os_family),
    advisory_id = COALESCE(EXCLUDED.advisory_id, kb_cve_edges.advisory_id),
    affected_pkgs = COALESCE(EXCLUDED.affected_pkgs, kb_cve_edges.affected_pkgs),
    fixed_pkgs = COALESCE(EXCLUDED.fixed_pkgs, kb_cve_edges.fixed_pkgs),
    update_id = COALESCE(EXCLUDED.update_id, kb_cve_edges.update_id),
    document_title = COALESCE(EXCLUDED.document_title, kb_cve_edges.document_title),
    cvrf_url = COALESCE(EXCLUDED.cvrf_url, kb_cve_edges.cvrf_url),
    published_date = COALESCE(EXCLUDED.published_date, kb_cve_edges.published_date),
    severity = COALESCE(EXCLUDED.severity, kb_cve_edges.severity),
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
SELECT c.cve_id, c.description,
       c.cvss_v2_score, c.cvss_v2_severity, c.cvss_v2_vector,
       c.cvss_v2_exploitability AS cvss_v2_exploitability_score,
       c.cvss_v2_impact AS cvss_v2_impact_score,
       c.cvss_v3_score, c.cvss_v3_severity, c.cvss_v3_vector,
       c.cvss_v3_exploitability AS cvss_v3_exploitability_score,
       c.cvss_v3_impact AS cvss_v3_impact_score,
       c.published_at, c.modified_at, c.synced_at,
       c.cwe_ids, c.affected_products, c.references,
       c.vendor_metadata, c.sources,
       COALESCE(e.affected_vms, 0) AS affected_vms
FROM cves c
LEFT JOIN mv_cve_exposure e ON e.cve_id = c.cve_id
WHERE 1=1
  -- When CPE is provided, it's the primary filter - keyword/vendor become optional hints
  AND ($1::text IS NULL OR $9::text IS NOT NULL OR c.search_vector @@ plainto_tsquery('english', $1))
  AND ($2::text IS NULL OR c.cvss_v3_severity = $2)
  AND ($3::numeric IS NULL OR c.cvss_v3_score >= $3)
  AND ($4::text IS NULL OR $9::text IS NOT NULL OR (
    CASE
      WHEN jsonb_typeof(c.affected_products) = 'string'
      THEN c.affected_products#>>'{}' ILIKE '%' || $4 || '%'
      ELSE EXISTS (
        SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
        WHERE product->>'vendor' ILIKE $4
      )
    END
  ))
  AND ($5::text IS NULL OR (
    CASE
      WHEN jsonb_typeof(c.affected_products) = 'string'
      THEN c.affected_products#>>'{}' ILIKE '%' || $5 || '%'
      ELSE EXISTS (
        SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
        WHERE product->>'product' ILIKE $5
      )
    END
  ))
  AND ($6::timestamptz IS NULL OR c.published_at >= $6)
  AND ($7::timestamptz IS NULL OR c.published_at <= $7)
  AND ($8::text IS NULL OR $8 = ANY(c.sources))
  AND ($9::text IS NULL OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
    WHERE product->>'cpe_uri' LIKE
      -- Extract CPE prefix (vendor:product) and match any version wildcard (* or -)
      substring($9 from '^(cpe:2.3:[^:]+:[^:]+:[^:]+):') || ':%'
  ))
ORDER BY c.published_at DESC, c.cve_id DESC
LIMIT $10 OFFSET $11;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 2b
QUERY_COUNT_CVES = """
SELECT COUNT(*) AS total
FROM cves c
WHERE 1=1
  AND ($1::text IS NULL OR c.search_vector @@ plainto_tsquery('english', $1))
  AND ($2::text IS NULL OR c.cvss_v3_severity = $2)
  AND ($3::numeric IS NULL OR c.cvss_v3_score >= $3)
  AND ($4::text IS NULL OR (
    CASE
      WHEN jsonb_typeof(c.affected_products) = 'string'
      THEN c.affected_products#>>'{}' ILIKE '%' || $4 || '%'
      ELSE EXISTS (
        SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
        WHERE product->>'vendor' ILIKE $4
      )
    END
  ))
  AND ($5::text IS NULL OR (
    CASE
      WHEN jsonb_typeof(c.affected_products) = 'string'
      THEN c.affected_products#>>'{}' ILIKE '%' || $5 || '%'
      ELSE EXISTS (
        SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
        WHERE product->>'product' ILIKE $5
      )
    END
  ))
  AND ($6::timestamptz IS NULL OR c.published_at >= $6)
  AND ($7::timestamptz IS NULL OR c.published_at <= $7)
  AND ($8::text IS NULL OR $8 = ANY(c.sources));
"""

# ---------------------------------------------------------------------------
# SQL Constants -- CVE detail + affected VMs (Phase 6 Queries 3a-3b)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 3a (PK lookup)
QUERY_CVE_DETAIL = """
SELECT cve_id, description, cvss_v3_score, cvss_v3_severity, cvss_v2_score, cvss_v2_severity,
       cvss_v3_vector, cvss_v2_vector, cwe_ids, "references", affected_products,
       sources, published_at, modified_at, synced_at,
       cvss_v3_exploitability, cvss_v3_impact
FROM cves
WHERE cve_id = $1;
"""

# From: TARGET-SQL-CVE-DOMAIN.md Query 3b (BH-006 fix)
QUERY_CVE_AFFECTED_VMS = """
SELECT d.vm_id, d.vm_name, d.severity, d.cvss_score, d.patch_status, d.kb_ids,
       v.resource_group, v.subscription_id, v.os_type, v.location
FROM mv_vm_cve_detail d
LEFT JOIN vms v ON d.vm_id = v.resource_id
WHERE d.cve_id = $1
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

# ---------------------------------------------------------------------------
# SQL Constants -- VM CVE detail (Phase 6 Queries 4a-4b)
# ---------------------------------------------------------------------------

# From: TARGET-SQL-CVE-DOMAIN.md Query 4b
QUERY_VM_CVE_MATCHES = """
SELECT scan_id, vm_id, vm_name, cve_id, severity, cvss_score,
       patch_status, kb_ids, description, published_date
FROM mv_vm_cve_detail
WHERE vm_id = $1
  AND ($2::text IS NULL OR severity = $2)
ORDER BY cvss_score DESC
LIMIT $3 OFFSET $4;
"""

# Count companion for QUERY_VM_CVE_MATCHES (pagination support)
QUERY_COUNT_VM_CVE_MATCHES = """
SELECT COUNT(*) AS total
FROM mv_vm_cve_detail
WHERE vm_id = $1
  AND ($2::text IS NULL OR severity = $2);
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
                fixed_packages = edge.get("fixed_pkgs") or edge.get("fixed_packages")
                fixed_version = edge.get("fixed_version")
                if fixed_packages is None and fixed_version:
                    fixed_packages = [fixed_version]

                await conn.execute(
                    UPSERT_KB_CVE_EDGE,
                    edge.get("kb_number"),
                    edge.get("cve_id"),
                    edge.get("source", "microsoft"),
                    edge.get("os_family", "windows"),
                    edge.get("advisory_id") or edge.get("kb_number"),
                    edge.get("affected_pkgs") or edge.get("affected_packages"),
                    fixed_packages,
                    edge.get("update_id"),
                    edge.get("document_title") or edge.get("title"),
                    edge.get("cvrf_url"),
                    edge.get("published_date"),
                    edge.get("severity"),
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

    async def query_cves(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "published_date",
        sort_order: str = "desc",
    ) -> List[UnifiedCVE]:
        """Adapter method for dict-based filter interface (used by CVEService).

        Maps filters dict to individual search_cves parameters and converts
        dict results to UnifiedCVE objects.
        """
        logger.info(f"query_cves called with {len(filters)} filters, limit={limit}")
        dict_results = await self.search_cves(
            keyword=filters.get("keyword"),
            severity=filters.get("severity"),
            min_score=filters.get("min_score"),
            vendor=filters.get("vendor"),
            product=filters.get("product"),
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            source=filters.get("source"),
            cpe_name=filters.get("cpe_name"),
            limit=limit,
            offset=offset,
        )

        # Convert dict results to UnifiedCVE objects with field name mapping
        unified_cves = []
        for row in dict_results:
            try:
                # Map database field names to UnifiedCVE field names
                mapped_row = dict(row)
                if "published_at" in mapped_row:
                    mapped_row["published_date"] = mapped_row.pop("published_at")
                if "modified_at" in mapped_row:
                    # Handle NULL modified_at by using published_at as fallback
                    modified_at = mapped_row.pop("modified_at")
                    mapped_row["last_modified_date"] = modified_at or mapped_row.get("published_date")
                if "synced_at" in mapped_row:
                    # Map synced_at to last_synced
                    mapped_row["last_synced"] = mapped_row.pop("synced_at")

                # Parse JSON string fields if needed (asyncpg JSONB codec handles most cases)
                import json
                for json_field in ["affected_products", "references", "vendor_metadata"]:
                    if json_field in mapped_row:
                        value = mapped_row[json_field]
                        # Handle string serialization edge cases
                        if isinstance(value, str):
                            try:
                                parsed_value = json.loads(value)
                                mapped_row[json_field] = parsed_value
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.warning(f"JSON parse failed for {json_field} in CVE {mapped_row.get('cve_id')}: {e}")
                                mapped_row[json_field] = []
                        elif value is None:
                            # NULL JSONB should become empty list
                            mapped_row[json_field] = []

                # Construct CVSSScore objects as dicts (not instances) for Pydantic v2 validation
                if mapped_row.get("cvss_v3_score") is not None:
                    mapped_row["cvss_v3"] = {
                        "version": mapped_row.get("cvss_v3_version", "3.1"),
                        "base_score": float(mapped_row["cvss_v3_score"]),
                        "base_severity": mapped_row.get("cvss_v3_severity", "UNKNOWN"),
                        "vector_string": mapped_row.get("cvss_v3_vector", ""),
                        "exploitability_score": mapped_row.get("cvss_v3_exploitability_score"),
                        "impact_score": mapped_row.get("cvss_v3_impact_score"),
                    }
                if mapped_row.get("cvss_v2_score") is not None:
                    mapped_row["cvss_v2"] = {
                        "version": mapped_row.get("cvss_v2_version", "2.0"),
                        "base_score": float(mapped_row["cvss_v2_score"]),
                        "base_severity": mapped_row.get("cvss_v2_severity", "UNKNOWN"),
                        "vector_string": mapped_row.get("cvss_v2_vector", ""),
                        "exploitability_score": mapped_row.get("cvss_v2_exploitability_score"),
                        "impact_score": mapped_row.get("cvss_v2_impact_score"),
                    }

                unified_cves.append(UnifiedCVE.model_validate(mapped_row))
            except Exception as e:
                logger.warning(f"Failed to convert CVE row to UnifiedCVE: {e}")
                continue

        return unified_cves

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
        cpe_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """CVE search with full filters including CPE. Phase 6 Query 2a. Eliminates BH-002."""
        try:
            # Debug log to verify CPE parameter
            if cpe_name:
                logger.info(f"search_cves called with cpe_name={cpe_name}, vendor={vendor}, keyword={keyword}")

            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    QUERY_SEARCH_CVES,
                    keyword, severity, min_score,
                    vendor, product,
                    date_from, date_to,
                    source, cpe_name,
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

    # ------------------------------------------------------------------
    # CVE detail + affected VMs (Queries 3a-3b)
    # ------------------------------------------------------------------

    async def get_cve_detail(self, cve_id: str) -> Optional[Dict]:
        """Single CVE by ID with full columns. Phase 6 Query 3a."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(QUERY_CVE_DETAIL, cve_id)
                return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch CVE detail for %s", cve_id, exc_info=True)
            return None

    async def get_cve_affected_vms(
        self,
        cve_id: str,
        subscription_id: Optional[str] = None,
        resource_group: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """VMs affected by a specific CVE. Phase 6 Query 3b. Eliminates BH-006."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    QUERY_CVE_AFFECTED_VMS,
                    cve_id, subscription_id, resource_group, limit, offset,
                )
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch affected VMs for %s", cve_id, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # VM CVE detail (Queries 4a-4b)
    # ------------------------------------------------------------------

    async def get_vm_cve_matches(
        self,
        vm_id: str,
        severity: Optional[str] = None,
        limit: Optional[int] = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """CVEs affecting a specific VM. Phase 6 Query 4b.

        Args:
            vm_id: VM resource ID
            severity: Optional severity filter
            limit: Max records to return (None = all records)
            offset: Starting offset for pagination
        """
        try:
            async with self.pool.acquire() as conn:
                if limit is None:
                    # Fetch all records without LIMIT
                    query = """
                    SELECT scan_id, vm_id, vm_name, cve_id, severity, cvss_score,
                           patch_status, kb_ids, description, published_date
                    FROM mv_vm_cve_detail
                    WHERE vm_id = $1
                      AND ($2::text IS NULL OR severity = $2)
                    ORDER BY cvss_score DESC
                    OFFSET $3;
                    """
                    rows = await conn.fetch(query, vm_id, severity, offset)
                else:
                    # Use paginated query
                    rows = await conn.fetch(
                        QUERY_VM_CVE_MATCHES, vm_id, severity, limit, offset,
                    )
                return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("Failed to fetch CVE matches for VM %s", vm_id, exc_info=True)
            return []

    async def count_vm_cve_matches(
        self,
        vm_id: str,
        severity: Optional[str] = None,
    ) -> int:
        """Count CVEs affecting a specific VM (pagination support)."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    QUERY_COUNT_VM_CVE_MATCHES, vm_id, severity,
                )
                return row["total"] if row else 0
        except asyncpg.PostgresError as e:
            logger.error("Failed to count CVE matches for VM %s", vm_id, exc_info=True)
            return 0
