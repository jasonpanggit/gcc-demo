-- Fix affected_products data - convert JSON strings to proper JSONB arrays
-- This is a one-time migration to fix the data format issue

-- Check current state
SELECT
    COUNT(*) as total_cves,
    COUNT(*) FILTER (WHERE jsonb_typeof(affected_products) = 'string') as string_type,
    COUNT(*) FILTER (WHERE jsonb_typeof(affected_products) = 'array') as array_type
FROM cves;

-- Convert string-formatted JSON to proper JSONB arrays
UPDATE cves
SET affected_products = (affected_products#>>'{}')::jsonb
WHERE jsonb_typeof(affected_products) = 'string';

-- Verify conversion
SELECT
    COUNT(*) as total_cves,
    COUNT(*) FILTER (WHERE jsonb_typeof(affected_products) = 'string') as string_type,
    COUNT(*) FILTER (WHERE jsonb_typeof(affected_products) = 'array') as array_type
FROM cves;

-- Test query after conversion
SELECT cve_id, LEFT(description, 80) as desc_preview
FROM cves
WHERE search_vector @@ plainto_tsquery('english', 'windows server 2016')
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(affected_products) AS product
    WHERE product->>'vendor' ILIKE 'microsoft'
  )
LIMIT 10;
