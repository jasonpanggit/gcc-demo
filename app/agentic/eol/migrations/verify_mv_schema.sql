-- Verify the materialized view schemas
SELECT
    'mv_cve_dashboard_summary' as mv_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'mv_cve_dashboard_summary'
ORDER BY ordinal_position;

SELECT
    'mv_cve_trending' as mv_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'mv_cve_trending'
ORDER BY ordinal_position;

SELECT
    'mv_cve_exposure' as mv_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'mv_cve_exposure'
ORDER BY ordinal_position;
