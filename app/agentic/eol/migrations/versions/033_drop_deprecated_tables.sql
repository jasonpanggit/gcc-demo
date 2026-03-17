-- Migration 033: Drop deprecated tables and views (Phase 10 cleanup)
-- Date: 2026-03-18
--
-- These objects were replaced in Phases 5-8:
--   inventory_vm_metadata -> vms (Phase 5.1 / migration 028)
--   patch_assessments     -> patch_assessments_cache (Phase 5.3 / migration 030)
--   v_unified_vm_inventory -> direct vms queries (Phase 8-9)
--   arg_cache             -> typed domain repositories (Phase 8)
--   law_cache             -> typed domain repositories (Phase 8)

-- Drop deprecated view first (may reference deprecated tables)
DROP VIEW IF EXISTS v_unified_vm_inventory;

-- Drop deprecated tables
DROP TABLE IF EXISTS inventory_vm_metadata;
DROP TABLE IF EXISTS patch_assessments;
DROP TABLE IF EXISTS arg_cache;
DROP TABLE IF EXISTS law_cache;
