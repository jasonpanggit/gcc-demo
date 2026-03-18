"""
Emergency MV fix endpoint - adds a temporary API route to fix production MVs.

This endpoint can be called from the deployed Container App to fix the MVs
using the app's own managed identity credentials.

Usage:
    1. Add this router to main.py temporarily
    2. Deploy to Container App
    3. Call POST /api/emergency/fix-mvs
    4. Remove this router and redeploy
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/emergency", tags=["Emergency Fixes"])


@router.post("/fix-mvs")
async def fix_production_mvs():
    """Emergency fix for materialized views in production."""
    try:
        from utils.pg_client import postgres_client

        results = []

        # Get connection pool
        pool = postgres_client.pool
        if not pool:
            raise HTTPException(status_code=503, detail="Database pool not initialized")

        async with pool.acquire() as conn:
            # Fix mv_cve_dashboard_summary
            results.append("Fixing mv_cve_dashboard_summary...")
            await conn.execute("DROP MATERIALIZED VIEW IF EXISTS mv_cve_dashboard_summary CASCADE;")
            await conn.execute("""
                CREATE MATERIALIZED VIEW mv_cve_dashboard_summary AS
                SELECT
                    COUNT(*)                                                                     AS total_cves,
                    COUNT(CASE WHEN cvss_v3_severity = 'CRITICAL' THEN 1 END)                   AS critical,
                    COUNT(CASE WHEN cvss_v3_severity = 'HIGH'     THEN 1 END)                   AS high,
                    COUNT(CASE WHEN cvss_v3_severity = 'MEDIUM'   THEN 1 END)                   AS medium,
                    COUNT(CASE WHEN cvss_v3_severity = 'LOW'      THEN 1 END)                   AS low,
                    COUNT(CASE WHEN published_at >= NOW() - INTERVAL '7 days'                   THEN 1 END) AS age_0_7,
                    COUNT(CASE WHEN published_at >= NOW() - INTERVAL '30 days'
                                AND published_at <  NOW() - INTERVAL '7 days'                   THEN 1 END) AS age_8_30,
                    COUNT(CASE WHEN published_at >= NOW() - INTERVAL '90 days'
                                AND published_at <  NOW() - INTERVAL '30 days'                  THEN 1 END) AS age_31_90,
                    COUNT(CASE WHEN published_at <  NOW() - INTERVAL '90 days'
                                OR  published_at IS NULL                                         THEN 1 END) AS age_90_plus,
                    NOW() AS last_updated
                FROM cves;
            """)
            await conn.execute("CREATE UNIQUE INDEX mv_cve_dashboard_summary_unique_idx ON mv_cve_dashboard_summary (last_updated);")
            results.append("✅ mv_cve_dashboard_summary fixed")

            # Fix mv_cve_trending
            results.append("Fixing mv_cve_trending...")
            await conn.execute("DROP MATERIALIZED VIEW IF EXISTS mv_cve_trending CASCADE;")
            await conn.execute("""
                CREATE MATERIALIZED VIEW mv_cve_trending AS
                SELECT
                    date_trunc('day', published_at)::date        AS bucket_date,
                    COUNT(*)                                      AS cve_count,
                    COUNT(CASE WHEN cvss_v3_severity = 'CRITICAL' THEN 1 END) AS critical_count,
                    COUNT(CASE WHEN cvss_v3_severity = 'HIGH'     THEN 1 END) AS high_count
                FROM cves
                WHERE published_at IS NOT NULL
                GROUP BY 1
                ORDER BY 1;
            """)
            await conn.execute("CREATE UNIQUE INDEX mv_cve_trending_bucket_date_unique_idx ON mv_cve_trending (bucket_date);")
            await conn.execute("CREATE INDEX mv_cve_trending_bucket_date_idx ON mv_cve_trending (bucket_date DESC);")
            results.append("✅ mv_cve_trending fixed")

            # Fix mv_cve_exposure
            results.append("Fixing mv_cve_exposure...")
            await conn.execute("DROP MATERIALIZED VIEW IF EXISTS mv_cve_exposure CASCADE;")
            await conn.execute("""
                CREATE MATERIALIZED VIEW mv_cve_exposure AS
                SELECT
                    m.cve_id,
                    c.cvss_v3_severity                                                                AS severity,
                    c.cvss_v3_score                                                                   AS cvss_score,
                    c.published_at                                                                    AS published_date,
                    COUNT(DISTINCT m.vm_id)                                                           AS affected_vms,
                    COUNT(DISTINCT CASE WHEN m.patch_status IN ('installed')
                                        THEN m.vm_id END)                                             AS patched_vms,
                    COUNT(DISTINCT CASE WHEN m.patch_status NOT IN ('installed')
                                        THEN m.vm_id END)                                             AS unpatched_vms
                FROM vm_cve_match_rows m
                JOIN cves c ON c.cve_id = m.cve_id
                WHERE m.scan_id = latest_completed_scan_id()
                GROUP BY m.cve_id, c.cvss_v3_severity, c.cvss_v3_score, c.published_at
                ORDER BY affected_vms DESC;
            """)
            await conn.execute("CREATE UNIQUE INDEX mv_cve_exposure_cve_id_unique_idx ON mv_cve_exposure (cve_id);")
            await conn.execute("CREATE INDEX mv_cve_exposure_severity_idx ON mv_cve_exposure (severity);")
            await conn.execute("CREATE INDEX mv_cve_exposure_affected_vms_idx ON mv_cve_exposure (affected_vms DESC);")
            results.append("✅ mv_cve_exposure fixed")

            # Refresh all MVs
            results.append("Refreshing materialized views...")
            await conn.execute("REFRESH MATERIALIZED VIEW mv_cve_dashboard_summary;")
            await conn.execute("REFRESH MATERIALIZED VIEW mv_cve_trending;")
            await conn.execute("REFRESH MATERIALIZED VIEW mv_cve_exposure;")
            results.append("✅ All MVs refreshed")

        return JSONResponse(content={
            "success": True,
            "message": "Materialized views fixed successfully",
            "details": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fix MVs: {str(e)}")
