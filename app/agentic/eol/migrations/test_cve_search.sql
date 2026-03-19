-- Test the CVE search query with Windows Server 2016 filters

-- First check if search_vector exists and is populated
SELECT cve_id, LEFT(description, 100) as desc_preview
FROM cves
WHERE description ILIKE '%windows server 2016%'
LIMIT 3;

-- Test plainto_tsquery
SELECT cve_id, LEFT(description, 100) as desc_preview
FROM cves
WHERE search_vector @@ plainto_tsquery('english', 'windows server 2016')
LIMIT 5;

-- Test vendor filter with EXISTS
SELECT cve_id, affected_products::text
FROM cves
WHERE EXISTS (
    SELECT 1 FROM jsonb_array_elements(affected_products) AS product
    WHERE product->>'vendor' ILIKE 'microsoft'
)
LIMIT 3;

-- Combined test - exactly what the scanner would use
SELECT cve_id, LEFT(description, 80) as desc_preview
FROM cves
WHERE search_vector @@ plainto_tsquery('english', 'windows server 2016')
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(affected_products) AS product
    WHERE product->>'vendor' ILIKE 'microsoft'
  )
LIMIT 10;
