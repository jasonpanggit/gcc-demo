-- ============================================================
-- Migration 034: Consolidated hosted PostgreSQL schema repair
-- Date: 2026-03-18
--
-- Purpose:
--   Bring existing hosted PostgreSQL databases into alignment with the
--   runtime schema expected by utils/pg_database.py without relying on
--   Container Apps startup bootstrap/repair logic.
--
-- Consolidates the earlier targeted Container Apps repair into a single,
-- authoritative migration for hosted environments.
--
-- Use this with a privileged PostgreSQL client.
-- Safe to run multiple times.
--
-- Notes:
--   - Orphaned child rows are deleted before each FK is added.
--   - Each FK is created only if it does not already exist.
--   - Optional function ownership handoff is included at the end for
--     older app images that still perform ownership-sensitive startup DDL.
-- ============================================================

-- ============================================================
-- 1. kb_cve_edges.cve_id -> cves.cve_id
-- ============================================================

DELETE FROM kb_cve_edges AS child
WHERE child.cve_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cves AS parent WHERE parent.cve_id = child.cve_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_kb_cve_edges_cve'
    ) THEN
        ALTER TABLE kb_cve_edges
        ADD CONSTRAINT fk_kb_cve_edges_cve
        FOREIGN KEY (cve_id)
        REFERENCES cves (cve_id)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$repair$;

-- ============================================================
-- 2. vms.subscription_id -> subscriptions.subscription_id
-- ============================================================

DELETE FROM vms AS child
WHERE child.subscription_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM subscriptions AS parent WHERE parent.subscription_id = child.subscription_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_vms_subscription'
    ) THEN
        ALTER TABLE vms
        ADD CONSTRAINT fk_vms_subscription
        FOREIGN KEY (subscription_id)
        REFERENCES subscriptions (subscription_id)
        ON DELETE RESTRICT;
    END IF;
END
$repair$;

-- ============================================================
-- 3. vm_cve_match_rows.scan_id -> cve_scans.scan_id
-- ============================================================

DELETE FROM vm_cve_match_rows AS child
WHERE child.scan_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cve_scans AS parent WHERE parent.scan_id = child.scan_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_vmcvematch_scan'
    ) THEN
        ALTER TABLE vm_cve_match_rows
        ADD CONSTRAINT fk_vmcvematch_scan
        FOREIGN KEY (scan_id)
        REFERENCES cve_scans (scan_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 4. vm_cve_match_rows.vm_id -> vms.resource_id
-- ============================================================

DELETE FROM vm_cve_match_rows AS child
WHERE child.vm_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.vm_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_vmcvematch_vm'
    ) THEN
        ALTER TABLE vm_cve_match_rows
        ADD CONSTRAINT fk_vmcvematch_vm
        FOREIGN KEY (vm_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 5. vm_cve_match_rows.cve_id -> cves.cve_id
-- ============================================================

DELETE FROM vm_cve_match_rows AS child
WHERE child.cve_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cves AS parent WHERE parent.cve_id = child.cve_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_vmcvematch_cve'
    ) THEN
        ALTER TABLE vm_cve_match_rows
        ADD CONSTRAINT fk_vmcvematch_cve
        FOREIGN KEY (cve_id)
        REFERENCES cves (cve_id)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$repair$;

-- ============================================================
-- 6. patch_assessments_cache.resource_id -> vms.resource_id
-- ============================================================

DELETE FROM patch_assessments_cache AS child
WHERE child.resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.resource_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_patchcache_vm'
    ) THEN
        ALTER TABLE patch_assessments_cache
        ADD CONSTRAINT fk_patchcache_vm
        FOREIGN KEY (resource_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 7. available_patches.resource_id -> vms.resource_id
-- ============================================================

DELETE FROM available_patches AS child
WHERE child.resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.resource_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_availpatches_vm'
    ) THEN
        ALTER TABLE available_patches
        ADD CONSTRAINT fk_availpatches_vm
        FOREIGN KEY (resource_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 8. os_inventory_snapshots.resource_id -> vms.resource_id
-- ============================================================

DELETE FROM os_inventory_snapshots AS child
WHERE child.resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.resource_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_osinvsnap_vm'
    ) THEN
        ALTER TABLE os_inventory_snapshots
        ADD CONSTRAINT fk_osinvsnap_vm
        FOREIGN KEY (resource_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 9. cve_vm_detections.resource_id -> vms.resource_id
-- ============================================================

DELETE FROM cve_vm_detections AS child
WHERE child.resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.resource_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_cvevmdet_vm'
    ) THEN
        ALTER TABLE cve_vm_detections
        ADD CONSTRAINT fk_cvevmdet_vm
        FOREIGN KEY (resource_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 10. cve_vm_detections.cve_id -> cves.cve_id
-- ============================================================

DELETE FROM cve_vm_detections AS child
WHERE child.cve_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cves AS parent WHERE parent.cve_id = child.cve_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_cvevmdet_cve'
    ) THEN
        ALTER TABLE cve_vm_detections
        ADD CONSTRAINT fk_cvevmdet_cve
        FOREIGN KEY (cve_id)
        REFERENCES cves (cve_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 11. arc_software_inventory.resource_id -> vms.resource_id
-- ============================================================

DELETE FROM arc_software_inventory AS child
WHERE child.resource_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM vms AS parent WHERE parent.resource_id = child.resource_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_arcswinv_vm'
    ) THEN
        ALTER TABLE arc_software_inventory
        ADD CONSTRAINT fk_arcswinv_vm
        FOREIGN KEY (resource_id)
        REFERENCES vms (resource_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 12. cve_alert_history.rule_id -> cve_alert_rules.rule_id
-- ============================================================

DELETE FROM cve_alert_history AS child
WHERE child.rule_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cve_alert_rules AS parent WHERE parent.rule_id = child.rule_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerthistory_rule'
    ) THEN
        ALTER TABLE cve_alert_history
        ADD CONSTRAINT fk_alerthistory_rule
        FOREIGN KEY (rule_id)
        REFERENCES cve_alert_rules (rule_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 13. cve_alert_history.cve_id -> cves.cve_id
-- ============================================================

DELETE FROM cve_alert_history AS child
WHERE child.cve_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM cves AS parent WHERE parent.cve_id = child.cve_id
  );

DO $repair$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerthistory_cve'
    ) THEN
        ALTER TABLE cve_alert_history
        ADD CONSTRAINT fk_alerthistory_cve
        FOREIGN KEY (cve_id)
        REFERENCES cves (cve_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- 14. slo_measurements.slo_id -> slo_definitions.slo_id
-- ============================================================

-- Legacy hosted DBs may have slo_definitions.id as the identifier column,
-- or may have a partially-populated slo_id from an interrupted repair.
-- Normalize that shape in one atomic block before adding the FK.
DO $repair$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'slo_definitions'
          AND column_name = 'id'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'slo_definitions'
          AND column_name = 'slo_id'
    ) THEN
        ALTER TABLE slo_definitions ADD COLUMN slo_id TEXT;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'slo_definitions'
          AND column_name = 'id'
    ) AND EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'slo_definitions'
          AND column_name = 'slo_id'
    ) THEN
        EXECUTE 'UPDATE slo_definitions SET slo_id = id::text WHERE slo_id IS NULL AND id IS NOT NULL';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'slo_definitions'
          AND column_name = 'slo_id'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
        WHERE n.nspname = 'public'
          AND t.relname = 'slo_definitions'
          AND c.contype IN ('p', 'u')
          AND a.attname = 'slo_id'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM slo_definitions
            WHERE slo_id IS NULL
        ) THEN
            RAISE EXCEPTION 'Cannot repair slo_definitions: slo_id contains NULL values';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM slo_definitions
            GROUP BY slo_id
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION 'Cannot repair slo_definitions: slo_id contains duplicate values';
        END IF;

        ALTER TABLE slo_definitions
        ADD CONSTRAINT uq_slo_definitions_slo_id UNIQUE (slo_id);
    END IF;

    DELETE FROM slo_measurements AS child
    WHERE child.slo_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM slo_definitions AS parent WHERE parent.slo_id = child.slo_id
      );

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'slo_measurements_slo_id_fkey'
    ) THEN
        ALTER TABLE slo_measurements
        ADD CONSTRAINT slo_measurements_slo_id_fkey
        FOREIGN KEY (slo_id)
        REFERENCES slo_definitions (slo_id)
        ON DELETE CASCADE;
    END IF;
END
$repair$;

-- ============================================================
-- Verification queries
-- ============================================================

SELECT conname
FROM pg_constraint
WHERE conname IN (
    'fk_kb_cve_edges_cve',
    'fk_vmcvematch_scan',
    'slo_measurements_slo_id_fkey',
    'fk_vms_subscription',
    'fk_vmcvematch_vm',
    'fk_vmcvematch_cve',
    'fk_patchcache_vm',
    'fk_availpatches_vm',
    'fk_osinvsnap_vm',
    'fk_cvevmdet_vm',
    'fk_cvevmdet_cve',
    'fk_arcswinv_vm',
    'fk_alerthistory_rule',
    'fk_alerthistory_cve'
)
ORDER BY conname;

-- ============================================================
-- Optional emergency mitigation for older app images
--
-- Only use this if Container Apps is still running an image that tries to
-- recreate/replace PostgreSQL functions at startup before the updated
-- pg_database.py code is deployed. Run the SET statement immediately before
-- this block when you need the ownership handoff.
--
-- Replace the sample role with the actual database role used by the container app.
-- Example for the current environment:
--   SET app.repair_owner_role = 'aad_postgres_flexible_eol';
-- ============================================================

-- SET app.repair_owner_role = 'APP_DB_ROLE';
DO $repair$
DECLARE
    target_owner TEXT := NULLIF(current_setting('app.repair_owner_role', true), '');
BEGIN
    IF target_owner IS NULL THEN
        RAISE NOTICE 'Skipping function ownership handoff; app.repair_owner_role is not set';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'latest_completed_scan_id'
          AND pg_get_function_identity_arguments(p.oid) = ''
    ) THEN
        EXECUTE format(
            'ALTER FUNCTION public.latest_completed_scan_id() OWNER TO %I',
            target_owner
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proname = 'cves_search_vector_update'
          AND pg_get_function_identity_arguments(p.oid) = ''
    ) THEN
        EXECUTE format(
            'ALTER FUNCTION public.cves_search_vector_update() OWNER TO %I',
            target_owner
        );
    END IF;
END
$repair$;

SELECT
    p.proname,
    pg_get_function_identity_arguments(p.oid) AS identity_args,
    pg_get_userbyid(p.proowner) AS owner_name
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname IN ('latest_completed_scan_id', 'cves_search_vector_update')
ORDER BY p.proname;