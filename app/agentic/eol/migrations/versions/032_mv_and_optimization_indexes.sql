-- ============================================================
-- Migration 032: Recreate mv_vm_vulnerability_posture + all
--                Phase 6 optimization indexes + FTS infrastructure
-- Pre-condition: vms (028), eol_records (bootstrap), cves (bootstrap),
--                kb_cve_edges (bootstrap+027), vm_cve_match_rows (bootstrap),
--                workflow_contexts (bootstrap), cve_scans (bootstrap),
--                patch_assessments_cache (bootstrap+030) all exist
-- Post-condition: Updated MV, 13 new indexes, 1 dropped index,
--                 FTS trigger function + trigger on cves
-- Idempotency: IF NOT EXISTS on CREATE; IF EXISTS on DROP;
--              CREATE OR REPLACE on function
-- ============================================================

-- ============================================================
-- SECTION 0: Schema guard — ensure eol_records has columns used in MV
-- Handles DBs created before these columns were added to the bootstrap DDL
-- ============================================================

ALTER TABLE eol_records
    ADD COLUMN IF NOT EXISTS is_eol   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS eol_date DATE;

-- ============================================================
-- SECTION 1: FTS Infrastructure (bootstrap gap from migration 006)
-- ============================================================

-- Trigger function for auto-updating search_vector on cves
CREATE OR REPLACE FUNCTION cves_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        COALESCE(NEW.cve_id, '') || ' ' ||
        COALESCE(NEW.description, '')
    );
    RETURN NEW;
END $$ LANGUAGE plpgsql;

-- Trigger to auto-populate search_vector on INSERT/UPDATE
-- Use DO block to handle "trigger already exists" gracefully
DO $$ BEGIN
    CREATE TRIGGER trg_cves_search_vector_update
        BEFORE INSERT OR UPDATE ON cves
        FOR EACH ROW EXECUTE FUNCTION cves_search_vector_update();
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Trigger trg_cves_search_vector_update already exists, skipping';
END $$;

-- GIN index on search_vector for full-text search (bootstrap gap)
CREATE INDEX IF NOT EXISTS idx_cves_fts
    ON cves USING GIN (search_vector);

-- ============================================================
-- SECTION 2: Expression Indexes for Case-Insensitive Search
-- ============================================================

-- BH-005 fuzzy EOL JOIN: LOWER(vms.os_name) = LOWER(eol_records.software_key)
CREATE INDEX IF NOT EXISTS idx_vms_os_name_lower
    ON vms (LOWER(os_name));

CREATE INDEX IF NOT EXISTS idx_eol_software_key_lower
    ON eol_records (LOWER(software_key));

-- ============================================================
-- SECTION 3: Filter Indexes (GAP resolutions + composites + partials)
-- ============================================================

-- GAP-01: Single-column severity index (equality-only severity filters)
CREATE INDEX IF NOT EXISTS idx_cves_severity
    ON cves (cvss_v3_severity);

-- GAP-02: Composite severity+published_at (time-range + severity queries)
CREATE INDEX IF NOT EXISTS idx_cves_severity_published
    ON cves (cvss_v3_severity, published_at);

-- Composite severity+score (severity filter with CVSS score ordering)
CREATE INDEX IF NOT EXISTS idx_cves_severity_score
    ON cves (cvss_v3_severity, cvss_v3_score DESC);

-- Composite subscription+os_name for inventory filter combinations
CREATE INDEX IF NOT EXISTS idx_vms_subscription_os
    ON vms (subscription_id, os_name);

-- Composite resource+last_modified for patch assessment timeline
CREATE INDEX IF NOT EXISTS idx_patchcache_resource_lastmod
    ON patch_assessments_cache (resource_id, last_modified DESC);

-- Partial index: high-severity CVEs only (dashboard priority filtering)
CREATE INDEX IF NOT EXISTS idx_cves_high_severity
    ON cves (cve_id, cvss_v3_score DESC)
    WHERE cvss_v3_severity IN ('CRITICAL', 'HIGH');

-- GAP-05: Partial index for completed scans (latest_completed_scan_id() O(1) access)
CREATE INDEX IF NOT EXISTS idx_scans_completed
    ON cve_scans (completed_at DESC, scan_id)
    WHERE status = 'completed';

-- GAP-06: Partial index for workflow context expiration (bootstrap-migration parity)
CREATE INDEX IF NOT EXISTS idx_wfctx_expires
    ON workflow_contexts (expires_at)
    WHERE expires_at IS NOT NULL;

-- ============================================================
-- SECTION 4: JOIN / Covering Indexes
-- ============================================================

-- GAP-03/04: Composite cve_id+source for kb_cve_edges JOIN queries
CREATE INDEX IF NOT EXISTS idx_edges_cve_source
    ON kb_cve_edges (cve_id, source);

-- Covering index: severity with INCLUDE columns for index-only scans
CREATE INDEX IF NOT EXISTS idx_cves_severity_covering
    ON cves (cvss_v3_severity) INCLUDE (cve_id, cvss_v3_score, published_at);

-- R-02: Drop redundant idx_edges_kb (fully redundant with PK prefix on kb_cve_edges)
DROP INDEX IF EXISTS idx_edges_kb;

-- ============================================================
-- SECTION 5: Recreate mv_vm_vulnerability_posture (P5.6)
-- Source changed from inventory_vm_metadata to vms
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS mv_vm_vulnerability_posture;

CREATE MATERIALIZED VIEW mv_vm_vulnerability_posture AS
SELECT
    vm.resource_id                                                          AS vm_id,
    vm.vm_name,
    vm.vm_type,
    vm.os_name,
    vm.os_type,
    vm.location,
    vm.resource_group,
    vm.subscription_id,
    vm.last_synced_at,
    COALESCE(agg.total_cves, 0)         AS total_cves,
    COALESCE(agg.critical, 0)           AS critical,
    COALESCE(agg.high, 0)               AS high,
    COALESCE(agg.medium, 0)             AS medium,
    COALESCE(agg.low, 0)                AS low,
    COALESCE(agg.unpatched, 0)          AS unpatched,
    COALESCE(agg.unpatched_critical, 0) AS unpatched_critical,
    COALESCE(agg.unpatched_high, 0)     AS unpatched_high,
    CASE
        WHEN COALESCE(agg.critical, 0) > 0
         AND COALESCE(agg.unpatched_critical, 0) > 0 THEN 'Critical'
        WHEN COALESCE(agg.high, 0) > 0
         AND COALESCE(agg.unpatched_high, 0) > 0     THEN 'High'
        WHEN COALESCE(agg.total_cves, 0) > 0         THEN 'Medium'
        ELSE 'Healthy'
    END AS risk_level,
    e.is_eol                            AS eol_status,
    e.eol_date                          AS eol_date,
    NOW() AS last_updated
FROM vms vm
LEFT JOIN (
    SELECT
        vm_id,
        COUNT(DISTINCT cve_id)                                                              AS total_cves,
        COUNT(DISTINCT CASE WHEN severity = 'CRITICAL' THEN cve_id END)                    AS critical,
        COUNT(DISTINCT CASE WHEN severity = 'HIGH'     THEN cve_id END)                    AS high,
        COUNT(DISTINCT CASE WHEN severity = 'MEDIUM'   THEN cve_id END)                    AS medium,
        COUNT(DISTINCT CASE WHEN severity = 'LOW'      THEN cve_id END)                    AS low,
        COUNT(DISTINCT CASE WHEN patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched,
        COUNT(DISTINCT CASE WHEN severity = 'CRITICAL'
                             AND patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched_critical,
        COUNT(DISTINCT CASE WHEN severity = 'HIGH'
                             AND patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched_high
    FROM vm_cve_match_rows
    WHERE scan_id = latest_completed_scan_id()
    GROUP BY vm_id
) agg ON agg.vm_id = vm.resource_id
LEFT JOIN eol_records e ON LOWER(vm.os_name) = LOWER(e.software_key);

-- MV indexes for CONCURRENT refresh and query performance
CREATE UNIQUE INDEX mv_vm_vulnerability_posture_vm_id_idx
    ON mv_vm_vulnerability_posture (vm_id);

CREATE INDEX mv_vm_vulnerability_posture_risk_total_idx
    ON mv_vm_vulnerability_posture (risk_level, total_cves DESC);

CREATE INDEX mv_vm_vulnerability_posture_sub_rg_idx
    ON mv_vm_vulnerability_posture (subscription_id, resource_group);

CREATE INDEX mv_vm_vulnerability_posture_vm_type_idx
    ON mv_vm_vulnerability_posture (vm_type);

-- I-03 fix: Set MV ownership to current role for CONCURRENT refresh
ALTER MATERIALIZED VIEW mv_vm_vulnerability_posture OWNER TO CURRENT_ROLE;
