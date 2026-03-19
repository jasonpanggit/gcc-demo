-- Check the actual structure of affected_products
SELECT cve_id,
       jsonb_typeof(affected_products) as type,
       affected_products
FROM cves
WHERE description ILIKE '%windows server 2016%'
LIMIT 3;
