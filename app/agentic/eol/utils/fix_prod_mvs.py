#!/usr/bin/env python3
"""
Fix production materialized views to match bootstrap schema.

This script connects to the production PostgreSQL database and recreates
the materialized views that are causing column mismatch errors.

IMPORTANT: This will drop and recreate the MVs, which will cause brief
read failures during recreation. Run during maintenance window.

Usage:
    python fix_prod_mvs.py

Required environment variables:
    - POSTGRES_HOST (from appsettings.json)
    - POSTGRES_USER (from appsettings.json)
    - POSTGRES_PASSWORD (from managed identity or connection string)
    - POSTGRES_DB (default: eol_app)
"""

import asyncio
import os
import sys

import asyncpg


# MV definitions from pg_database.py bootstrap code
MV_DEFINITIONS = {
    "mv_cve_dashboard_summary": """
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
    """,

    "mv_cve_trending": """
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
    """,

    "mv_cve_exposure": """
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
    """,
}

MV_INDEXES = {
    "mv_cve_dashboard_summary": [
        "CREATE UNIQUE INDEX mv_cve_dashboard_summary_unique_idx ON mv_cve_dashboard_summary (last_updated);"
    ],
    "mv_cve_trending": [
        "CREATE UNIQUE INDEX mv_cve_trending_bucket_date_unique_idx ON mv_cve_trending (bucket_date);",
        "CREATE INDEX mv_cve_trending_bucket_date_idx ON mv_cve_trending (bucket_date DESC);"
    ],
    "mv_cve_exposure": [
        "CREATE UNIQUE INDEX mv_cve_exposure_cve_id_unique_idx ON mv_cve_exposure (cve_id);",
        "CREATE INDEX mv_cve_exposure_severity_idx ON mv_cve_exposure (severity);",
        "CREATE INDEX mv_cve_exposure_affected_vms_idx ON mv_cve_exposure (affected_vms DESC);"
    ],
}


async def recreate_mv(conn: asyncpg.Connection, mv_name: str):
    """Drop and recreate a single materialized view."""
    print(f"🔄 Recreating {mv_name}...")

    # Drop MV (CASCADE to drop dependent indexes)
    await conn.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv_name} CASCADE;")
    print(f"  ✅ Dropped {mv_name}")

    # Create MV
    await conn.execute(MV_DEFINITIONS[mv_name])
    print(f"  ✅ Created {mv_name}")

    # Create indexes
    for idx_sql in MV_INDEXES.get(mv_name, []):
        await conn.execute(idx_sql)
    print(f"  ✅ Created {len(MV_INDEXES.get(mv_name, []))} indexes")


async def main():
    # Get connection details
    host = os.getenv("POSTGRES_HOST", "agentic-aiops-demo-pg.postgres.database.azure.com")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "aad_postgres_flexible_eol")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB", "eol_app")

    if not password:
        print("❌ ERROR: POSTGRES_PASSWORD environment variable not set")
        sys.exit(1)

    print(f"🔌 Connecting to {host}:{port}/{database} as {user}...")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            ssl="require"
        )
        print("  ✅ Connected")

        # Recreate each problematic MV
        for mv_name in ["mv_cve_dashboard_summary", "mv_cve_trending", "mv_cve_exposure"]:
            await recreate_mv(conn, mv_name)

        print("\n✅ All materialized views recreated successfully")
        print("⚠️  NOTE: MVs are empty until first refresh. Run REFRESH MATERIALIZED VIEW or wait for scheduled refresh.")

        await conn.close()

    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
