-- ============================================================
-- Migration 027: Drop inactive tables, migration-011 MVs, and
--                migrate kb_cve_edge data to kb_cve_edges (I-01)
-- Pre-condition: kb_cve_edges table exists (bootstrap)
-- Post-condition: arc_os_inventory, patch_assessment_history,
--                 kb_cve_edge tables removed; 3 migration-011
--                 MVs removed; kb_cve_edge data preserved in
--                 kb_cve_edges
-- Idempotency: All DROP/CREATE use IF EXISTS/IF NOT EXISTS
-- ============================================================

-- 1. Drop inactive tables (confirmed INACTIVE in P2.2)
DROP TABLE IF EXISTS arc_os_inventory;
DROP TABLE IF EXISTS patch_assessment_history;

-- 2. Drop migration-011 MVs (no active callers — superseded by bootstrap MVs)
-- Pre-verified: grep -r "vm_vulnerability_overview" yields 0 Python callers
-- Pre-verified: grep -r "cve_dashboard_stats" yields 0 Python callers
-- Pre-verified: grep -r "os_cve_inventory_counts" yields 0 Python callers
DROP MATERIALIZED VIEW IF EXISTS vm_vulnerability_overview;
DROP MATERIALIZED VIEW IF EXISTS cve_dashboard_stats;
DROP MATERIALIZED VIEW IF EXISTS os_cve_inventory_counts;

-- 3. Add cached_at column to kb_cve_edges before data migration
--    (Normally in migration 029, but needed here to keep data migration self-contained)
ALTER TABLE kb_cve_edges ADD COLUMN IF NOT EXISTS cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 4. Migrate kb_cve_edge (singular) data to kb_cve_edges (plural)
--    Column mapping: kb_id -> kb_number; source defaults to 'msrc' if NULL
--    Skip rows that already exist in destination (WHERE NOT EXISTS)
INSERT INTO kb_cve_edges (kb_number, cve_id, source, severity, last_seen, cached_at)
SELECT kb_id, cve_id, COALESCE(source, 'msrc'), severity, cached_at, cached_at
FROM kb_cve_edge
WHERE NOT EXISTS (
    SELECT 1 FROM kb_cve_edges
    WHERE kb_cve_edges.kb_number = kb_cve_edge.kb_id
      AND kb_cve_edges.cve_id = kb_cve_edge.cve_id
      AND kb_cve_edges.source = COALESCE(kb_cve_edge.source, 'msrc')
);

-- 5. Drop the inactive singular table after data migration
DROP TABLE IF EXISTS kb_cve_edge;
