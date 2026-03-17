---
phase: 05-unified-schema-design
plan: "01"
subsystem: database
tags: [postgresql, schema-design, vm-identity, foreign-keys, erd]

requires:
  - phase: 02-schema-repository-audit
    provides: BASE-TABLES.md (inventory_vm_metadata DDL), REPOSITORY-MAP.md (consumers), UI-TO-SCHEMA-MAP.md (UI dependencies)
  - phase: 03-bad-hack-catalogue
    provides: BH-013 (os_name denormalization), BH-014 (subscription_id), BH-015 (vm_id/resource_id confusion)
  - phase: 04-cache-layer-specification
    provides: TTL-TIERS-SPEC (cached_at columns), CACHE-GAPS-SUMMARY (tables to DROP/modify)
provides:
  - vms table DDL (12 columns, TEXT PK, 8 indexes, upsert pattern)
  - subscriptions table DDL (7 columns, UUID PK, 3 indexes, upsert pattern)
  - FK relationship graph (6 child tables with CASCADE DELETE)
  - TYPE ALIGNMENT audit (patch_assessments_cache VARCHAR(512)->TEXT)
  - inventory_vm_metadata deprecation plan (6 consumers mapped)
  - Mermaid ERD (subscriptions->vms spine with all FK radiating outward)
  - CASCADE DELETE safety pattern (4-step sync)
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, 06-01, 07-02, 08-01]

tech-stack:
  added: []
  patterns:
    - "TEXT PK for Azure ARM resource IDs (not VARCHAR)"
    - "ON DELETE RESTRICT for parent refs, ON DELETE CASCADE for child data"
    - "UPSERT-only sync pattern (never DELETE+INSERT)"
    - "Staleness monitoring via last_synced_at < NOW() - INTERVAL"

key-files:
  created:
    - .planning/phases/05-unified-schema-design/schema/VM-IDENTITY-SPINE.md
  modified: []

key-decisions:
  - "PK resource_id uses TEXT not VARCHAR(500) -- PostgreSQL stores identically; TEXT eliminates truncation risk"
  - "vm_type included in vms table -- stable identity attribute needed by mv_vm_vulnerability_posture MV"
  - "subscription FK uses ON DELETE RESTRICT -- prevents catastrophic cascade-delete of entire VM spine"
  - "eol_status/eol_date excluded from vms -- derived at query time via JOIN to eol_records"
  - "inventory_vm_metadata DEPRECATED -- all 6 consumers mapped to Phase 8/9 migration paths"
  - "patch_assessments_cache.resource_id needs VARCHAR(512)->TEXT alignment in Phase 7"

patterns-established:
  - "VM identity spine pattern: vms as canonical FK target for all VM-referencing tables"
  - "UPSERT-only sync: never DELETE+INSERT from vms to protect CASCADE child data"
  - "Subscriptions-first population order due to FK dependency"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 4min
completed: 2026-03-17
---

# Phase 5 Plan 1: VM Identity Spine Design Summary

**Designed `vms` (12-column TEXT PK) and `subscriptions` (UUID PK) tables as the canonical VM identity spine with 6 FK relationships, type alignment audit, and full `inventory_vm_metadata` deprecation plan**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T02:27:28Z
- **Completed:** 2026-03-17T02:32:18Z
- **Tasks:** 3
- **Files created:** 1

## Accomplishments

- Designed `vms` table with 12 columns (resource_id TEXT PK, subscription_id UUID FK, vm_type added per research S7.1 recommendation) and 8 indexes including GIN for JSONB tags
- Designed `subscriptions` table with 7 columns (subscription_id UUID PK) and 3 indexes, plus upsert pattern for sync job
- Documented 6 FK relationships from child tables to `vms.resource_id` (all ON DELETE CASCADE) with ALTER TABLE DDL
- TYPE ALIGNMENT audit: only `patch_assessments_cache.resource_id` needs VARCHAR(512)->TEXT change in Phase 7
- Complete `inventory_vm_metadata` deprecation plan mapping all 6 consumers to Phase 7/8/9 migration paths
- Mermaid ERD showing subscriptions->vms spine with all FK relationships radiating outward
- CASCADE DELETE safety documentation with 4-step sync pattern and staleness monitoring query

## Task Commits

Each task was committed atomically:

1. **Task 05-01.1: Design vms table DDL** - `6867c3b` (docs)
2. **Task 05-01.2: Design subscriptions table DDL** - `4866aa9` (docs)
3. **Task 05-01.3: Document FK relationship graph and inventory_vm_metadata deprecation** - `55e22cc` (docs)

## Files Created/Modified

- `.planning/phases/05-unified-schema-design/schema/VM-IDENTITY-SPINE.md` - Complete VM identity spine design: vms DDL, subscriptions DDL, FK graph, type alignment, deprecation plan, Mermaid ERD, CASCADE safety

## Decisions Made

1. **TEXT over VARCHAR(500) for resource_id** - PostgreSQL stores TEXT and VARCHAR identically; TEXT eliminates truncation risk for long ARM paths (per research S7.2)
2. **vm_type included in vms** - Stable identity attribute ('arc'/'azure-vm' never changes). Needed by mv_vm_vulnerability_posture MV to avoid JOIN to deprecated table (per research S7.1 Option A)
3. **ON DELETE RESTRICT for subscription FK** - Prevents catastrophic cascade-delete of entire VM spine when a subscription is removed
4. **eol_status/eol_date excluded** - Derived values computed from eol_records via JOIN; storing in vms creates stale denormalized copies
5. **UPSERT-only sync pattern** - CASCADE DELETE from vms propagates to 6 child tables; DELETE+INSERT would wipe all dependent data
6. **tenant_id not updated on conflict** - Once set, tenant_id should not change for a subscription

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- VM identity spine design is complete and ready for P5.2 (CVE data tables) to reference `vms.resource_id` FK
- All remaining P5.x plans can now use the FK relationship graph as the foundation
- P5.6 (MVs) will need to update `mv_vm_vulnerability_posture` source from `inventory_vm_metadata` to `vms`
- P5.7 (Unified DDL spec) will consolidate this design with P5.2-P5.6 outputs

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
