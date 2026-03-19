-- Test the fixed query that handles JSONB string vs array
SELECT cve_id, LEFT(description, 80) as desc_preview
FROM cves
WHERE search_vector @@ plainto_tsquery('english', 'windows server 2016')
  AND (
    CASE
      WHEN jsonb_typeof(affected_products) = 'string'
      THEN affected_products#>>'{}' ILIKE '%microsoft%'
      ELSE EXISTS (
        SELECT 1 FROM jsonb_array_elements(affected_products) AS product
        WHERE product->>'vendor' ILIKE 'microsoft'
      )
    END
  )
LIMIT 10;
