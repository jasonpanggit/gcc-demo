-- Direct approach: Select from the MVs to see their columns

-- Check mv_cve_dashboard_summary structure
SELECT * FROM mv_cve_dashboard_summary LIMIT 0;

-- Check mv_cve_trending structure
SELECT * FROM mv_cve_trending LIMIT 0;

-- Check mv_cve_exposure structure
SELECT * FROM mv_cve_exposure LIMIT 0;

-- Alternative: Use pg_attribute to see columns
SELECT
    a.attname as column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
    a.attnum as position
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
WHERE c.relname = 'mv_cve_dashboard_summary'
  AND n.nspname = 'public'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;

SELECT
    a.attname as column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
    a.attnum as position
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
WHERE c.relname = 'mv_cve_trending'
  AND n.nspname = 'public'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;

SELECT
    a.attname as column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
    a.attnum as position
FROM pg_catalog.pg_attribute a
JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
WHERE c.relname = 'mv_cve_exposure'
  AND n.nspname = 'public'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
