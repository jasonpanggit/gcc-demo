-- Check the actual columns in each MV

-- Check mv_cve_dashboard_summary columns
SELECT 'mv_cve_dashboard_summary' as view_name, column_name, ordinal_position
FROM information_schema.columns
WHERE table_name = 'mv_cve_dashboard_summary'
ORDER BY ordinal_position;

-- Check mv_cve_trending columns
SELECT 'mv_cve_trending' as view_name, column_name, ordinal_position
FROM information_schema.columns
WHERE table_name = 'mv_cve_trending'
ORDER BY ordinal_position;

-- Check mv_cve_exposure columns
SELECT 'mv_cve_exposure' as view_name, column_name, ordinal_position
FROM information_schema.columns
WHERE table_name = 'mv_cve_exposure'
ORDER BY ordinal_position;
