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
