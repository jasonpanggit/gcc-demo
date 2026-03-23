-- ============================================================
-- Migration 035: Repair kb_cve_edges conflict key for hosted DBs
-- Date: 2026-03-22
--
-- Purpose:
--   Bring older kb_cve_edges tables into line with the canonical runtime
--   contract used by CVERepository and KBCVEEdgeRepository upserts:
--     (kb_number, cve_id, source)
--
--   Older hosted databases may be missing the unique/primary key required
--   for ON CONFLICT inference, and may still contain placeholder rows with
--   NULL cve_id values from legacy negative-cache logic.
--
-- Safe to run multiple times.
-- ============================================================

-- 1. Remove legacy placeholder rows that cannot satisfy the canonical key.
DELETE FROM kb_cve_edges
WHERE kb_number IS NULL
   OR cve_id IS NULL
   OR source IS NULL;

-- 2. Deduplicate surviving rows before adding the unique conflict key.
WITH ranked AS (
    SELECT
        ctid,
        ROW_NUMBER() OVER (
            PARTITION BY kb_number, cve_id, source
            ORDER BY
                COALESCE(last_seen, cached_at, NOW()) DESC,
                COALESCE(cached_at, last_seen, NOW()) DESC,
                ctid DESC
        ) AS row_num
    FROM kb_cve_edges
)
DELETE FROM kb_cve_edges AS edge
USING ranked
WHERE edge.ctid = ranked.ctid
  AND ranked.row_num > 1;

-- 3. Enforce the canonical key columns as non-null.
ALTER TABLE kb_cve_edges ALTER COLUMN kb_number SET NOT NULL;
ALTER TABLE kb_cve_edges ALTER COLUMN cve_id SET NOT NULL;
ALTER TABLE kb_cve_edges ALTER COLUMN source SET NOT NULL;

-- 4. Ensure ON CONFLICT (kb_number, cve_id, source) can be inferred.
CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_cve_edges_conflict_key
    ON kb_cve_edges (kb_number, cve_id, source);