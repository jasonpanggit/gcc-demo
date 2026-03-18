-- Check if materialized views have any data

SELECT 'mv_cve_dashboard_summary' as view_name, COUNT(*) as row_count
FROM mv_cve_dashboard_summary
UNION ALL
SELECT 'mv_cve_trending', COUNT(*)
FROM mv_cve_trending
UNION ALL
SELECT 'mv_cve_exposure', COUNT(*)
FROM mv_cve_exposure
UNION ALL
SELECT 'cves (base table)', COUNT(*)
FROM cves;

-- Also check the actual data in dashboard summary
SELECT * FROM mv_cve_dashboard_summary;
