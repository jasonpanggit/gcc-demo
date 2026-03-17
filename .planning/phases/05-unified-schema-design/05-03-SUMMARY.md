---
phase: 05-unified-schema-design
plan: "03"
subsystem: database
tags: [postgresql, inventory, schema-design, foreign-keys, ttl, cascade-delete]

requires:
  - phase: 05-unified-schema-design/P5.1
    provides: vms identity spine (resource_id PK, FK target for all inventory tables)
provides:
  - INVENTORY-TABLES.md with DDL for 5 active/modified tables
  - FK relationships for 4 inventory tables to vms.resource_id
  - DROP list (2 inactive tables) with migration SQL
  - DEPRECATE list (4 legacy tables) with timeline
  - Mermaid ERD for inventory domain
affects: [phase-06-index-optimization, phase-07-schema-implementation, phase-08-repository-update, phase-10-cleanup]

tech-stack:
  added: []
  patterns:
    - "Pattern B staleness enforcement (cached_at + TTL comparison) for sync-job tables"
    - "Pattern C metadata-controlled TTL for snapshot tables"
    - "FK TARGET CHANGE pattern: available_patches FK moved from transitive (patch_assessments_cache) to direct (vms)"

key-files:
  created:
    - .planning/phases/05-unified-schema-design/schema/INVENTORY-TABLES.md
  modified: []

key-decisions:
  - "resource_inventory has NO FK to vms -- stores all Azure resource types, not just VMs"
  - "os_inventory_snapshots retains os_name alongside vms.os_name (raw LAW vs normalized canonical)"
  - "patch_assessments_cache.resource_id type changed VARCHAR(512)->TEXT for alignment with vms"
  - "available_patches FK target changed from patch_assessments_cache to vms directly (cleaner, avoids transitive dependency)"
  - "arc_software_inventory gets new FK fk_arcswinv_vm to vms"
  - "2 tables DROP (arc_os_inventory, patch_assessment_history) -- both INACTIVE"
  - "4 tables DEPRECATE (inventory_vm_metadata, arg_cache, law_cache, patch_assessments) -- Phase 10 cleanup"

patterns-established:
  - "All inventory domain FK constraints use ON DELETE CASCADE to vms.resource_id"
  - "TTL tier: MEDIUM_LIVED (3600s) for all active inventory cache tables"
  - "Phase 7 migration pattern: orphan cleanup DELETE before ADD CONSTRAINT FK"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 7min
completed: 2026-03-17
---

# Phase 5 Plan 3: Inventory Tables Design Summary

**DDL design for 5 active inventory tables with FK to vms spine, 5 state/cache tables, 2 tables to DROP, 4 tables to DEPRECATE, and Mermaid ERD**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-17T02:37:41Z
- **Completed:** 2026-03-17T02:44:58Z
- **Tasks:** 3
- **Files created:** 1

## Accomplishments

- Designed target DDL for all 5 active/modified inventory domain tables with FK relationships to `vms.resource_id`
- Documented `resource_inventory` as ACTIVE with no FK to `vms` (mixed resource types rationale)
- Specified 4 new FK constraints (`fk_osinvsnap_vm`, `fk_patchcache_vm`, `fk_availpatches_vm`, `fk_arcswinv_vm`) all with ON DELETE CASCADE
- Documented `patch_assessments_cache.resource_id` type change from VARCHAR(512) to TEXT
- Changed `available_patches` FK target from `patch_assessments_cache` to `vms` directly (cleaner, no transitive dependency)
- Documented TTL tier assignments: all MEDIUM_LIVED (3600s) with Pattern B or Pattern C enforcement
- Documented 5 unchanged state/cache metadata tables
- Specified 2 tables for DROP in Phase 7 with SQL
- Specified 4 tables for DEPRECATE in Phase 10 with deprecation timeline
- Created Mermaid ERD for the complete inventory domain

## Task Commits

Each task was committed atomically:

1. **Task 1: Document resource_inventory and os_inventory_snapshots** - `fbbb91d` (docs)
2. **Task 2: Document patch_assessments_cache and available_patches with FK changes** - `61d9a1d` (docs)
3. **Task 3: Document arc_software_inventory, DROP list, DEPRECATE list, and ERD** - content committed via prior session restoration

**Plan metadata:** (this commit)

## Files Created/Modified

- `.planning/phases/05-unified-schema-design/schema/INVENTORY-TABLES.md` - Complete inventory domain schema design with DDL for 10 tables, DROP/DEPRECATE lists, and ERD

## Decisions Made

1. **resource_inventory NO FK to vms** - Stores ALL Azure resource types (VMs, storage, networking). Mixed-type table makes FK impractical. Phase 8 queries use explicit JOIN with WHERE type LIKE '%virtualMachines%'.
2. **os_name dual storage** - `os_inventory_snapshots.os_name` keeps raw LAW-reported value; `vms.os_name` stores normalized canonical. Both needed for raw historical data vs query-time filtering.
3. **patch_assessments_cache type alignment** - VARCHAR(512) -> TEXT. PostgreSQL metadata-only operation, no table rewrite. Ensures FK compatibility with `vms.resource_id TEXT`.
4. **available_patches FK target change** - Direct FK to `vms` instead of transitive through `patch_assessments_cache`. Cleaner relationship; patches are associated with VMs, not with cache entries.
5. **Phase 7 migration pattern** - All FK additions require: (1) orphan row cleanup via DELETE, (2) then ADD CONSTRAINT. Pre-condition: `vms` table populated first.
6. **4 DEPRECATED tables** - `inventory_vm_metadata`, `arg_cache`, `law_cache`, `patch_assessments` kept through Phases 7-9 for backward compatibility, dropped in Phase 10.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Inventory domain schema design complete, ready for P5.4 (EOL Tables Design)
- All 4 FK relationships documented with migration SQL for Phase 7
- Phase 6 has forward references for index design on new FK columns
- Remaining Phase 5 plans: P5.4 (EOL), P5.6 (MVs), P5.7 (Unified DDL spec)

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
