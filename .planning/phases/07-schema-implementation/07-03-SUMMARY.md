---
phase: 07-schema-implementation
plan: "03"
subsystem: database
tags: [postgres, migration, fk-constraints, orphan-cleanup, cve, idempotent-ddl]

requires:
  - phase: 07-01
    provides: kb_cve_edges cached_at column (migration 027)
  - phase: 07-02
    provides: vms table with resource_id PK (migration 028)
provides:
  - FK constraints from vm_cve_match_rows to vms and cves
  - FK constraints from cve_vm_detections to vms and cves
  - Unique index idx_cvevmdet_resource_cve on cve_vm_detections
  - Orphan cleanup pattern for CVE domain tables
affects: [07-04, 07-05, 07-06, 08-01, 08-02]

tech-stack:
  added: []
  patterns:
    - "DO $$ BEGIN ... EXCEPTION WHEN duplicate_object pattern for idempotent ADD CONSTRAINT"
    - "Orphan cleanup DELETE with RAISE NOTICE row count logging before FK addition"

key-files:
  created:
    - app/agentic/eol/migrations/versions/029_cve_table_fk_additions.sql
  modified: []

key-decisions:
  - "Migration 029 follows exact DDL from plan — no deviations needed"
  - "cached_at safety net retained as ADD COLUMN IF NOT EXISTS (already in 027)"

patterns-established:
  - "FK ADD CONSTRAINT idempotency: DO block with EXCEPTION WHEN duplicate_object THEN RAISE NOTICE"
  - "Orphan cleanup before FK: DELETE WHERE col NOT IN (SELECT pk FROM parent) with GET DIAGNOSTICS row count"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 1min
completed: 2026-03-17
---

# Phase 7 Plan 3: Migration 029 — CVE Table FK Additions + Orphan Cleanup Summary

**Migration 029 adds 4 FK constraints (vm_cve_match_rows + cve_vm_detections to vms and cves) with inline orphan cleanup and idempotent DO blocks**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-17T07:06:35Z
- **Completed:** 2026-03-17T07:07:42Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- Created migration 029 SQL file with 4 FK constraints linking CVE domain tables to the VM identity spine (vms) and CVE catalogue (cves)
- Implemented orphan cleanup pattern: 4 DELETE statements with RAISE NOTICE logging precede each FK addition
- All ADD CONSTRAINT statements wrapped in DO blocks with EXCEPTION WHEN duplicate_object for idempotency (Risk 2 mitigation)
- fk_vmcvematch_cve uses DEFERRABLE INITIALLY DEFERRED for batch scan inserts
- Added unique index idx_cvevmdet_resource_cve to prevent duplicate detections per resource+CVE
- Safety net: cached_at ADD COLUMN IF NOT EXISTS on kb_cve_edges (already present from migration 027)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write migration 029 SQL file** - `6aae855` (feat)

## Files Created/Modified
- `app/agentic/eol/migrations/versions/029_cve_table_fk_additions.sql` - CVE domain FK constraints + orphan cleanup + unique index

## Decisions Made
None - followed plan as specified. The SQL matched the plan exactly.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Migration 029 complete, ready for P7.4 (Migration 030: Inventory + EOL tables)
- The orphan cleanup pattern established here (DO block + DELETE + RAISE NOTICE + EXCEPTION WHEN duplicate_object) will be reused in migration 030

---
*Phase: 07-schema-implementation*
*Completed: 2026-03-17*
