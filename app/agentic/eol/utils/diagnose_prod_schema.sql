-- Diagnostic script to check production schema state
-- Run with: psql -h <host> -U <user> -d eol_app -f diagnose_prod_schema.sql

-- Check if MVs exist
SELECT
    schemaname,
    matviewname,
    definition
FROM pg_matviews
WHERE matviewname IN (
    'mv_cve_dashboard_summary',
    'mv_cve_trending',
    'mv_cve_top_by_score',
    'mv_cve_exposure'
)
ORDER BY matviewname;

-- Check column names for mv_cve_dashboard_summary
\d+ mv_cve_dashboard_summary

-- Check column names for mv_cve_trending
\d+ mv_cve_trending

-- Check column names for mv_cve_exposure
\d+ mv_cve_exposure
