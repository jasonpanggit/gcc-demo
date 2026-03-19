-- Emergency fix for production materialized views
-- Run these commands in sequence using your PostgreSQL client

-- Fix mv_cve_dashboard_summary
DROP MATERIALIZED VIEW IF EXISTS mv_cve_dashboard_summary CASCADE;

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

CREATE UNIQUE INDEX mv_cve_dashboard_summary_unique_idx ON mv_cve_dashboard_summary (last_updated);

-- Fix mv_cve_trending
DROP MATERIALIZED VIEW IF EXISTS mv_cve_trending CASCADE;

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

CREATE UNIQUE INDEX mv_cve_trending_bucket_date_unique_idx ON mv_cve_trending (bucket_date);
CREATE INDEX mv_cve_trending_bucket_date_idx ON mv_cve_trending (bucket_date DESC);

-- Fix mv_cve_exposure
DROP MATERIALIZED VIEW IF EXISTS mv_cve_exposure CASCADE;

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

CREATE UNIQUE INDEX mv_cve_exposure_cve_id_unique_idx ON mv_cve_exposure (cve_id);
CREATE INDEX mv_cve_exposure_severity_idx ON mv_cve_exposure (severity);
CREATE INDEX mv_cve_exposure_affected_vms_idx ON mv_cve_exposure (affected_vms DESC);

-- Refresh all MVs to populate data
REFRESH MATERIALIZED VIEW mv_cve_dashboard_summary;
REFRESH MATERIALIZED VIEW mv_cve_trending;
REFRESH MATERIALIZED VIEW mv_cve_exposure;

-- Verify the fix
SELECT 'mv_cve_dashboard_summary' as view_name, COUNT(*) as rows FROM mv_cve_dashboard_summary
UNION ALL
SELECT 'mv_cve_trending', COUNT(*) FROM mv_cve_trending
UNION ALL
SELECT 'mv_cve_exposure', COUNT(*) FROM mv_cve_exposure;
