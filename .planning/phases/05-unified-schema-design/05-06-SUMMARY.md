---
phase: 05-unified-schema-design
plan: "06"
subsystem: database
tags: [postgres, materialized-views, schema-design, refresh-schedule, ownership]

requires:
  - phase: 05-unified-schema-design/05-01
    provides: vms table DDL (source for updated mv_vm_vulnerability_posture)
  - phase: 02-schema-repository-audit/02-03
    provides: All 10 MV DDLs, refresh mechanisms, ownership audit
provides:
  - MATERIALIZED-VIEWS-TARGET.md with 7 retained MVs and updated posture DDL
  - DROP list for 3 migration-011 MVs with verification checklist
  - 15-minute APScheduler refresh schedule for all 7 MVs
  - Manual refresh API endpoint spec (3 endpoints)
  - I-03 ownership fix strategy (idempotent bootstrap)
  - v_unified_vm_inventory deprecation timeline
  - MV source dependency Mermaid diagram
affects: [phase-06-index-optimization, phase-07-schema-implementation, phase-08-repository-update]

tech-stack:
  added: []
  patterns: [idempotent-mv-bootstrap, eol-records-join-pattern, concurrent-refresh-ownership]

key-files:
  created:
    - .planning/phases/05-unified-schema-design/schema/MATERIALIZED-VIEWS-TARGET.md
  modified: []

key-decisions:
  - "mv_vm_vulnerability_posture updated to source from vms instead of inventory_vm_metadata, with LEFT JOIN eol_records for EOL data"
  - "3 migration-011 MVs (vm_vulnerability_overview, cve_dashboard_stats, os_cve_inventory_counts) on DROP list with Phase 7 verification checklist"
  - "I-03 ownership fix: idempotent bootstrap (check pg_matviews before CREATE, skip if exists)"
  - "v_unified_vm_inventory DEPRECATED -- Phase 7 keep, Phase 9 rewire, Phase 10 DROP"
  - "eol_status column changes from TEXT to BOOLEAN (e.is_eol) -- Phase 8/9 must verify API response shape"

patterns-established:
  - "MV idempotent bootstrap: query pg_matviews before CREATE to preserve ownership"
  - "EOL data via JOIN to eol_records (not denormalized in source tables)"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 5min
completed: 2026-03-17
---

# Plan 05-06: Materialized View Set Design Summary

**Target MV set consolidated from 10 to 7 bootstrap MVs with updated mv_vm_vulnerability_posture DDL sourcing from vms table, 15-minute APScheduler refresh, I-03 ownership fix, and 3 migration-011 MVs on DROP list**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T02:37:54Z
- **Completed:** 2026-03-17T02:43:37Z
- **Tasks:** 2
- **Files created:** 1

## Accomplishments

- Documented all 7 retained bootstrap MVs with status, source tables, unique indexes, and CONCURRENT refresh support
- Rewrote `mv_vm_vulnerability_posture` DDL to source from `vms` (P5.1) instead of `inventory_vm_metadata`, with `LEFT JOIN eol_records` for EOL data
- Created DROP list for 3 migration-011 MVs with Phase 7 verification checklist and DROP DDL
- Specified 15-minute APScheduler refresh schedule for all 7 MVs plus existing post-scan trigger
- Designed 3 manual refresh API endpoints (`/api/admin/mv/refresh/{dashboard,inventory,all}`) with success/error response formats
- Documented I-03 ownership fix strategy: idempotent bootstrap checking `pg_matviews` before CREATE
- Documented `v_unified_vm_inventory` deprecation timeline across Phase 7/9/10
- Created Mermaid MV source dependency diagram showing all table-to-MV relationships

## Task Commits

Each task was committed atomically:

1. **Task 05-06.1: Document retained bootstrap MVs and update mv_vm_vulnerability_posture** - `c575d9f` (docs)
2. **Task 05-06.2: Document DROP list, refresh schedule, manual API, and I-03 fix** - `d4f2c99` (docs)

## Files Created/Modified

- `.planning/phases/05-unified-schema-design/schema/MATERIALIZED-VIEWS-TARGET.md` - Complete MV target design: 7 retained MVs, updated posture DDL, DROP list, refresh schedule, API spec, I-03 fix, deprecation timeline, dependency diagram

## Decisions Made

1. **mv_vm_vulnerability_posture source migration:** Changed from `inventory_vm_metadata` to `vms` table with LEFT JOIN to `eol_records` for EOL data. Removes denormalized `eol_status`/`eol_date` columns, adds computed JOIN.
2. **eol_status type change:** From `TEXT` (string 'EOL'/'Supported') to `BOOLEAN` (`e.is_eol`). Phase 8/9 must verify API response shape and add CASE mapping if needed.
3. **os_version removed from MV:** `os_version` not in `vms` (lives in `os_inventory_snapshots`). Removed from posture MV output columns.
4. **LATERAL JOIN removed:** `COALESCE(m.vm_name, vm.vm_name)` pattern eliminated since `vms.vm_name` is canonical.
5. **I-03 fix: Option 3 (idempotent bootstrap):** Check `pg_matviews` before CREATE; skip if MV exists to preserve migration ownership. No hardcoded role names.
6. **KBCVEInferenceJob refresh list:** Must be updated in Phase 8 after Phase 7 drops the 3 migration-011 MVs.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- P5.6 complete -- MV target design feeds into P5.7 (Unified DDL Spec) as the MV section
- Phase 6 can reference MV indexes for query optimization design
- Phase 7 has complete MV DDL for migration implementation
- Phase 8 has forward references for KBCVEInferenceJob refresh list update and eol_status API shape verification
- **Remaining Phase 5 plans:** P5.3 (Inventory), P5.4 (EOL), P5.7 (Unified DDL Spec)

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
