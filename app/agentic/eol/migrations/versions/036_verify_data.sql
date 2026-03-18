-- Verify CVE data exists

SELECT 'Step 1: Check cves table' as step, COUNT(*) as count FROM cves;

SELECT 'Step 2: Check mv_cve_dashboard_summary' as step, COUNT(*) as count FROM mv_cve_dashboard_summary;

SELECT 'Step 3: Sample CVEs' as step;
SELECT cve_id, cvss_v3_severity, published_at FROM cves ORDER BY published_at DESC LIMIT 5;

SELECT 'Step 4: Dashboard summary data' as step;
SELECT * FROM mv_cve_dashboard_summary;
