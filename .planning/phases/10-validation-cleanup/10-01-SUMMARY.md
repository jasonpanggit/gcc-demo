---
phase: 10-validation-cleanup
plan: "01"
subsystem: testing
tags: [postgres, asyncpg, explain-analyze, performance, pytest]

requires:
  - phase: 07-pg-migration-execution
    provides: PostgreSQL schema with tables, indexes, and materialized views
  - phase: 08-repository-wiring
    provides: pg_client singleton and PostgresDatabaseManager
provides:
  - Performance test package with shared fixtures (pg_pool, seed_performance_data, explain)
  - EXPLAIN ANALYZE output parser with regex extraction
  - Performance threshold constants for query timing validation
  - Seed data generator covering all 7 MV source tables
affects: [10-02, 10-03, 10-04, 10-05, 10-06, 10-07]

tech-stack:
  added: [asyncpg (test fixture), pytest-asyncio (test fixture)]
  patterns: [session-scoped pool fixture, idempotent seed data with ON CONFLICT DO NOTHING, regex-based plan parsing]

key-files:
  created:
    - app/agentic/eol/tests/performance/__init__.py
    - app/agentic/eol/tests/performance/helpers.py
    - app/agentic/eol/tests/performance/conftest.py
  modified: []

key-decisions:
  - "Used deterministic UUIDs for subscription/alert-rule IDs to ensure seed data idempotency across repeated runs"
  - "MV refresh list aligned with pg_database.py (7 MVs including mv_vm_cve_detail instead of mv_cve_top_by_affected_vms)"
  - "Error-tolerant MV refresh (log warning and continue) to handle schema evolution gracefully"

patterns-established:
  - "Performance tests use session-scoped pg_pool + seed_performance_data fixtures"
  - "EXPLAIN results parsed via parse_explain_output() returning dict with timing + scan type flags"
  - "Threshold constants (THRESHOLD_*_MS) used for assertion boundaries in performance tests"

requirements-completed: [QRY-03]

duration: 7min
completed: 2026-03-17
---

# Phase 10 Plan 1: Performance Test Infrastructure Summary

**asyncpg pool fixtures, EXPLAIN ANALYZE parser, and deterministic seed data generator for PostgreSQL query performance validation**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-17T14:56:43Z
- **Completed:** 2026-03-17T15:04:14Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments
- Created `tests/performance/` package with shared infrastructure for all P10.2+ performance tests
- Built EXPLAIN ANALYZE output parser with regex extraction for execution/planning time and scan type detection
- Defined 4 performance threshold constants (50ms detail, 100ms dashboard, 200ms list, 500ms aggregation)
- Created session-scoped seed data fixture inserting 2 subscriptions, 30 VMs, 100 CVEs, 300 match rows, 50 KB edges, 10 EOL records, 3 alert rules, and 10 alert history entries with idempotent ON CONFLICT DO NOTHING

## Task Commits

Each task was committed atomically:

1. **Task 1: Create performance test package and EXPLAIN ANALYZE helper** - `4ab0ced` (feat)
2. **Task 2: Create performance conftest.py with pool fixture and seed data** - `82b540f` (feat)

## Files Created/Modified
- `app/agentic/eol/tests/performance/__init__.py` - Empty package marker
- `app/agentic/eol/tests/performance/helpers.py` - EXPLAIN parser, threshold constants, SMALL_MV_NAMES
- `app/agentic/eol/tests/performance/conftest.py` - pg_pool, seed_performance_data, explain fixtures

## Decisions Made
- Used deterministic UUIDs for seed data IDs to enable idempotent re-runs without conflicts
- Aligned MV refresh list with actual pg_database.py definitions (mv_vm_cve_detail not mv_cve_top_by_affected_vms)
- Error-tolerant MV refresh that logs warnings instead of failing, handling schema evolution

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Performance test infrastructure complete and ready for P10.2 test files
- All fixtures session-scoped for efficient reuse across test modules
- Seed data covers all 7 MV source tables ensuring comprehensive performance coverage

---
*Phase: 10-validation-cleanup*
*Completed: 2026-03-17*
