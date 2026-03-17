---
phase: 05-unified-schema-design
plan: "07"
subsystem: database
tags: [postgresql, schema, ddl, migration, erd, unified-spec]

requires:
  - phase: 05-unified-schema-design (P5.1-P5.6)
    provides: Domain-specific schema designs (VM spine, CVE, Inventory, EOL, Alerting, MVs)
  - phase: 04-cache-layer-specification
    provides: cache_ttl_config DDL, TTL tiers, cached_at column requirements
provides:
  - Complete target PostgreSQL schema DDL specification (UNIFIED-SCHEMA-SPEC.md)
  - Migration-ready SQL for migrations 027-032
  - Bootstrap _REQUIRED_TABLES and _REQUIRED_RELATIONS update lists
  - Phase 6-10 actionable forward references
affects: [phase-6-index-design, phase-7-schema-implementation, phase-8-repository-update, phase-9-ui-integration, phase-10-validation]

tech-stack:
  added: []
  patterns: [migration-numbered-ddl, table-fate-classification, forward-reference-documentation]

key-files:
  created:
    - .planning/phases/05-unified-schema-design/schema/UNIFIED-SCHEMA-SPEC.md
  modified: []

key-decisions:
  - "UNIFIED-SCHEMA-SPEC.md is the single authoritative DDL document for Phase 7 migration execution"
  - "Migrations numbered 027-032 organized by domain dependency order (drops first, spine, CVE, inventory+EOL, alerting, MV)"
  - "8 tables added to _REQUIRED_TABLES (4 NEW + 4 promoted from migration 011)"
  - "11 FK relationships documented in _REQUIRED_RELATIONS with ON DELETE behavior"
  - "Orphan row cleanup DELETEs included before every ADD CONSTRAINT to prevent FK violations"

patterns-established:
  - "Migration dependency ordering: DROP obsolete -> CREATE spine -> ALTER existing -> CREATE new -> DROP+CREATE redesigned -> Recreate MVs"
  - "Orphan cleanup pattern: DELETE WHERE NOT IN (SELECT) before ADD CONSTRAINT FK"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 5 min
completed: 2026-03-17
---

# Phase 5 Plan 7: Unified Schema DDL Specification Summary

**Consolidated all P5.1-P5.6 domain designs into a single authoritative UNIFIED-SCHEMA-SPEC.md with complete migration-ready DDL (027-032), Table Fate Summary (39+ tables), full Mermaid ERD, bootstrap update lists, and Phase 6-10 forward references.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T02:52:42Z
- **Completed:** 2026-03-17T02:57:50Z
- **Tasks:** 3
- **Files created:** 1

## Accomplishments

- Created comprehensive UNIFIED-SCHEMA-SPEC.md (680 lines) that serves as the single Phase 7 migration blueprint
- Table Fate Summary classifies all 39+ tables with status badges (4 NEW, 2 REDESIGNED, 7 MODIFIED, 20+ ACTIVE, 4 DEPRECATED, 3 DROP)
- Complete copy-pasteable DDL for 6 migrations organized by domain dependency order
- Full Mermaid ERD with all FK relationships across Identity, CVE, Inventory, EOL, and Alerting domains
- Bootstrap _REQUIRED_TABLES additions (8 tables) and _REQUIRED_RELATIONS (11 FK constraints)
- Phase 6-10 forward references with specific action items per phase

## Task Commits

Each task was committed atomically:

1. **Task 05-07.1: Create UNIFIED-SCHEMA-SPEC.md with Table Fate Summary and full ERD** - `9f1585f` (docs)
2. **Task 05-07.2: Add complete DDL section with all CREATE/ALTER/DROP statements** - `cb36f01` (docs)
3. **Task 05-07.3: Add bootstrap update list and Phase 6-10 forward references** - `99eae71` (docs)

## Files Created/Modified

- `.planning/phases/05-unified-schema-design/schema/UNIFIED-SCHEMA-SPEC.md` - Complete target schema DDL specification (680 lines)

## Decisions Made

- Organized migrations by dependency order: 027 (drops) -> 028 (spine) -> 029 (CVE) -> 030 (inventory+EOL) -> 031 (alerting) -> 032 (MV)
- Included orphan row DELETE statements before every ADD CONSTRAINT to ensure FK constraints can be applied without violation errors
- Documented all 11 FK relationships with explicit ON DELETE behavior (CASCADE vs RESTRICT)
- Phase 10 deprecated table removal deferred until all consumer migration is confirmed complete

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 5 COMPLETE** - All 7 plans (P5.1-P5.7) are done
- UNIFIED-SCHEMA-SPEC.md is ready for Phase 7 direct execution as migrations 027-032
- Phase 6 (Index & Query Optimization Design) can now begin, with forward references from the spec document
- Phase 7 executor can read UNIFIED-SCHEMA-SPEC.md alone and produce all migration SQL

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
