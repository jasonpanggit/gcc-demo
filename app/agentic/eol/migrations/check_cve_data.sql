-- Check CVE database status
SELECT COUNT(*) as total_cves FROM cves;

-- Check if there are any Windows Server CVEs
SELECT COUNT(*) as windows_cves
FROM cves
WHERE cve_id IN (
    SELECT DISTINCT cve_id
    FROM kb_cve_edges
);

-- Check KB-CVE edges for Windows
SELECT COUNT(*) as kb_edges FROM kb_cve_edges;

-- Sample some CVEs if they exist
SELECT cve_id, description, severity, published_date
FROM cves
LIMIT 5;
