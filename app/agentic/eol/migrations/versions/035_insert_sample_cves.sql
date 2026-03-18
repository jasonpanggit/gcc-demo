-- Insert sample CVE data for testing the UI

-- Insert a few sample CVEs
INSERT INTO cves (cve_id, description, published_at, modified_at, cvss_v3_score, cvss_v3_severity)
VALUES
('CVE-2024-1234', 'Critical security vulnerability in web framework', NOW() - INTERVAL '5 days', NOW(), 9.8, 'CRITICAL'),
('CVE-2024-5678', 'High severity authentication bypass', NOW() - INTERVAL '10 days', NOW(), 8.5, 'HIGH'),
('CVE-2024-9012', 'Medium severity information disclosure', NOW() - INTERVAL '30 days', NOW(), 5.3, 'MEDIUM'),
('CVE-2024-3456', 'Low severity denial of service', NOW() - INTERVAL '60 days', NOW(), 3.1, 'LOW'),
('CVE-2023-7890', 'Critical remote code execution', NOW() - INTERVAL '120 days', NOW(), 10.0, 'CRITICAL')
ON CONFLICT (cve_id) DO NOTHING;

-- Refresh all materialized views to populate them with data
REFRESH MATERIALIZED VIEW mv_cve_dashboard_summary;
REFRESH MATERIALIZED VIEW mv_cve_trending;
REFRESH MATERIALIZED VIEW mv_cve_top_by_score;
REFRESH MATERIALIZED VIEW mv_cve_exposure;

-- Verify the data was inserted
SELECT 'cves' as table_name, COUNT(*) as row_count FROM cves
UNION ALL
SELECT 'mv_cve_dashboard_summary', COUNT(*) FROM mv_cve_dashboard_summary
UNION ALL
SELECT 'mv_cve_trending', COUNT(*) FROM mv_cve_trending;
