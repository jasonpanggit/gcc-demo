-- Debug: Check affected_products structure for Windows Server CVEs
SELECT cve_id, affected_products
FROM cves
WHERE LOWER(description) LIKE '%windows server 2016%'
LIMIT 5;
