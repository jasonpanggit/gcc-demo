-- ============================================================
-- Migration 029: CVE domain FK additions and orphan cleanup (P5.2)
-- Pre-condition: vms table exists (migration 028), cves table
--                exists (bootstrap)
-- Post-condition: vm_cve_match_rows and cve_vm_detections have
--                 FK constraints to vms and cves
-- WARNING: Orphan cleanup will DELETE all rows from
--          vm_cve_match_rows and cve_vm_detections because the
--          vms table is empty at this point. This is expected
--          per "fresh schema start" project decision. Phase 8
--          sync jobs will repopulate data.
-- Idempotency: DO blocks with EXCEPTION WHEN duplicate_object
-- ============================================================

-- Safety net: ensure cached_at exists on kb_cve_edges
-- (Should already exist from migration 027, but ADD COLUMN IF NOT EXISTS is safe)
ALTER TABLE kb_cve_edges ADD COLUMN IF NOT EXISTS cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- ============================================================
-- vm_cve_match_rows FK additions
-- ============================================================

-- Clean orphan rows before adding FK to vms
DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM vm_cve_match_rows WHERE vm_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from vm_cve_match_rows (vm_id not in vms)', _count;
    END IF;
END $$;

-- Clean orphan rows before adding FK to cves
DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM vm_cve_match_rows WHERE cve_id NOT IN (SELECT cve_id FROM cves);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from vm_cve_match_rows (cve_id not in cves)', _count;
    END IF;
END $$;

-- Add FK from vm_cve_match_rows.vm_id to vms.resource_id
DO $$ BEGIN
    ALTER TABLE vm_cve_match_rows
        ADD CONSTRAINT fk_vmcvematch_vm
        FOREIGN KEY (vm_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_vmcvematch_vm already exists, skipping';
END $$;

-- Add FK from vm_cve_match_rows.cve_id to cves.cve_id (DEFERRABLE for batch inserts)
DO $$ BEGIN
    ALTER TABLE vm_cve_match_rows
        ADD CONSTRAINT fk_vmcvematch_cve
        FOREIGN KEY (cve_id) REFERENCES cves(cve_id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_vmcvematch_cve already exists, skipping';
END $$;

-- ============================================================
-- cve_vm_detections FK additions
-- ============================================================

-- Clean orphan rows before adding FK to vms
DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM cve_vm_detections WHERE resource_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from cve_vm_detections (resource_id not in vms)', _count;
    END IF;
END $$;

-- Clean orphan rows before adding FK to cves
DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM cve_vm_detections WHERE cve_id NOT IN (SELECT cve_id FROM cves);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from cve_vm_detections (cve_id not in cves)', _count;
    END IF;
END $$;

-- Add FK from cve_vm_detections.resource_id to vms.resource_id
DO $$ BEGIN
    ALTER TABLE cve_vm_detections
        ADD CONSTRAINT fk_cvevmdet_vm
        FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_cvevmdet_vm already exists, skipping';
END $$;

-- Add FK from cve_vm_detections.cve_id to cves.cve_id
DO $$ BEGIN
    ALTER TABLE cve_vm_detections
        ADD CONSTRAINT fk_cvevmdet_cve
        FOREIGN KEY (cve_id) REFERENCES cves(cve_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_cvevmdet_cve already exists, skipping';
END $$;

-- Unique index to prevent duplicate detections per resource+CVE
CREATE UNIQUE INDEX IF NOT EXISTS idx_cvevmdet_resource_cve
    ON cve_vm_detections (resource_id, cve_id);
