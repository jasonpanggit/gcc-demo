---
phase: 07-schema-implementation
plan: "05"
subsystem: database
tags: [postgresql, migration, alerting, ddl, indexes, schema-redesign]

requires:
  - phase: 05-unified-schema-design
    provides: ALERTING-TABLES.md target DDL for cve_alert_rules and cve_alert_history
  - phase: 06-index-query-optimization-design
    provides: FILTER-INDEX-STRATEGY.md and JOIN-INDEX-STRATEGY.md alerting indexes
  - phase: 07-schema-implementation (07-03)
    provides: Migration 029 CVE table FK additions (cves table must exist for FK target)
provides:
  - Migration 031 SQL file with redesigned cve_alert_rules (9 columns) and cve_alert_history (8 columns)
  - 9 indexes on alerting tables (5 base + 4 Phase 6 optimization)
  - I-06 schema foundation (Phase 8 completes resolution with repository rewrite)
affects: [phase-08-repository-layer, AlertPostgresRepository, cve_alert_rule_manager, cve_alert_history_manager]

tech-stack:
  added: []
  patterns: [drop-recreate-migration, per-cve-firing-model, partial-indexes, covering-indexes]

key-files:
  created:
    - app/agentic/eol/migrations/versions/031_alerting_tables.sql
  modified: []

key-decisions:
  - "Migration 031 uses DROP IF EXISTS + CREATE IF NOT EXISTS for idempotent alerting table redesign"
  - "9 indexes total: 2 on cve_alert_rules (enabled, active partial), 7 on cve_alert_history (rule, cve, fired, rule_cve unique, severity_fired, unsent partial, rule covering)"

patterns-established:
  - "Pattern: DROP child table before parent when FK exists (cve_alert_history before cve_alert_rules)"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 1min
completed: 2026-03-17
---

# Phase 7 Plan 5: Migration 031 — Alerting Tables DROP + CREATE Summary

**Redesigned cve_alert_rules (9 explicit columns replacing JSONB blob) and cve_alert_history (8-column per-CVE firing model replacing 22-column aggregated model) with 9 indexes including partial and covering indexes from Phase 6**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-17T07:13:05Z
- **Completed:** 2026-03-17T07:14:34Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- Created migration 031 SQL file that drops and recreates both alerting tables with Phase 5.5 target schema
- Included all 9 indexes (5 base from UNIFIED-SCHEMA-SPEC + 4 optimization from Phase 6 FILTER-INDEX-STRATEGY and JOIN-INDEX-STRATEGY)
- Both FK constraints defined with CASCADE DELETE (rule_id -> cve_alert_rules, cve_id -> cves)
- I-06 schema foundation complete (Phase 8 will rewrite AlertPostgresRepository and replace in-memory managers)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write migration 031 SQL file** - `357c2ff` (feat)

## Files Created/Modified
- `app/agentic/eol/migrations/versions/031_alerting_tables.sql` - Migration 031: DROP old alerting tables, CREATE redesigned cve_alert_rules (9 cols) + cve_alert_history (8 cols) + 9 indexes

## Decisions Made
None - followed plan as specified. All DDL matched UNIFIED-SCHEMA-SPEC.md, ALERTING-TABLES.md, FILTER-INDEX-STRATEGY.md, and JOIN-INDEX-STRATEGY.md exactly.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Migration 031 complete, ready for P7.6 (Migration 032: optimization indexes + modified MV)
- Phase 7 now 5/7 plans done
- Phase 8 AlertPostgresRepository rewrite can reference the new column names from this migration

---
*Phase: 07-schema-implementation*
*Completed: 2026-03-17*
