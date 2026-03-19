-- Full diagnostic check for database state

-- 1. Check if we're in the right database
SELECT current_database();

-- 2. Check if the cves table exists (base table)
SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name = 'cves'
) as cves_table_exists;

-- 3. List all materialized views in the database
SELECT schemaname, matviewname
FROM pg_matviews
WHERE schemaname = 'public'
ORDER BY matviewname;

-- 4. List all tables in the database (first 20)
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_type = 'BASE TABLE'
ORDER BY table_name
LIMIT 20;

-- 5. Check if any of the expected MVs exist
SELECT
    EXISTS (SELECT FROM pg_matviews WHERE matviewname = 'mv_cve_dashboard_summary') as has_dashboard_summary,
    EXISTS (SELECT FROM pg_matviews WHERE matviewname = 'mv_cve_trending') as has_trending,
    EXISTS (SELECT FROM pg_matviews WHERE matviewname = 'mv_cve_exposure') as has_exposure;
