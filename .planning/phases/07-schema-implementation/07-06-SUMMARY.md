---
phase: 07-schema-implementation
plan: "06"
subsystem: database
tags: [postgres, sql, migration, materialized-view, indexes, full-text-search, gin, btree, covering-index, partial-index]

# Dependency graph
requires:
  - phase: 07-02
    provides: vms table (source for MV re-creation)
  - phase: 07-03
    provides: CVE FK constraints (vm_cve_match_rows FKs)
  - phase: 07-04
    provides: inventory FK + eol_agent_responses + cache_ttl_config
provides:
  - Migration 032 SQL file with MV re-creation, 13 optimization indexes, FTS infrastructure, 1 index DROP
  - mv_vm_vulnerability_posture sourced from vms (not inventory_vm_metadata) with eol_records JOIN
  - FTS trigger function + trigger + GIN index for cves.search_vector
  - All Phase 6 search, filter, JOIN, and covering indexes
affects: [07-07-bootstrap-rewrite, 08-repository-layer, 09-ui-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DO block for idempotent trigger creation (no IF NOT EXISTS for CREATE TRIGGER)"
    - "CREATE OR REPLACE FUNCTION for natively idempotent function creation"
    - "OWNER TO CURRENT_ROLE for MV ownership fix (I-03)"
    - "Expression indexes LOWER() for case-insensitive JOIN optimization"

key-files:
  created:
    - app/agentic/eol/migrations/versions/032_mv_and_optimization_indexes.sql
  modified: []

key-decisions:
  - "Migration 032 follows exact DDL from plan — no deviations needed"

patterns-established:
  - "FTS bootstrap gap pattern: CREATE OR REPLACE FUNCTION + DO block trigger + GIN index"
  - "MV ownership pattern: OWNER TO CURRENT_ROLE after CREATE for CONCURRENT refresh"
  - "Partial index pattern: WHERE clause for high-selectivity subset access"
  - "Covering index pattern: INCLUDE columns for index-only scans"

requirements-completed: [DB-01, DB-02, DB-03]

# Metrics
duration: 2min
completed: 2026-03-17
---

# Phase 7 Plan 06: Migration 032 Summary

**Migration 032 creates mv_vm_vulnerability_posture (vms source), 13 Phase 6 optimization indexes, FTS trigger infrastructure, and drops redundant idx_edges_kb**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T07:13:05Z
- **Completed:** 2026-03-17T07:15:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Created migration 032 with 5 sections: FTS infrastructure, expression indexes, filter indexes, JOIN/covering indexes, MV re-creation
- FTS trigger function + trigger + GIN index fills bootstrap gap from migration 006
- 13 new optimization indexes: 2 expression (BH-005), 3 severity (GAP-01/02), 2 composite, 3 partial (GAP-05/06), 2 JOIN/covering (GAP-03/04)
- 1 index DROP (idx_edges_kb — R-02 redundancy resolution)
- mv_vm_vulnerability_posture re-created with vms as source + eol_records LEFT JOIN + 4 MV indexes
- I-03 ownership fix applied with OWNER TO CURRENT_ROLE

## Task Commits

Each task was committed atomically:

1. **Task 07-06-01: Write migration 032 SQL file** - `5c04cc2` (feat)

## Files Created/Modified
- `app/agentic/eol/migrations/versions/032_mv_and_optimization_indexes.sql` - Migration 032: MV re-creation + 13 optimization indexes + FTS infrastructure + 1 DROP

## Decisions Made
None - followed plan as specified. The plan provided exact DDL for all sections.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Migration 032 complete — all 6 migration files (027-032) now exist
- Ready for P7.7: Bootstrap DDL rewrite (`pg_database.py` _bootstrap_runtime_schema update)
- Phase 7 is 6/7 plans done after this plan

---
*Phase: 07-schema-implementation*
*Completed: 2026-03-17*
