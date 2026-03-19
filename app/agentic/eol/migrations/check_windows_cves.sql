-- Check what Windows CVEs exist
SELECT DISTINCT c.cve_id, c.base_score
FROM cves c
INNER JOIN kb_cve_edges ke ON c.cve_id = ke.cve_id
WHERE ke.kb_number LIKE 'KB%'
ORDER BY c.base_score DESC NULLS LAST
LIMIT 10;

-- Check if there are any CVEs for Windows Server specifically
SELECT COUNT(*) as count
FROM cves
WHERE LOWER(description) LIKE '%windows server%'
   OR LOWER(affected_products) LIKE '%windows server%';

-- Sample CVE descriptions to see matching patterns
SELECT cve_id, LEFT(description, 100) as desc_sample
FROM cves
WHERE LOWER(description) LIKE '%windows%'
LIMIT 5;
