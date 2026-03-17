---
phase: 06-index-query-optimization-design
plan: 01
subsystem: database
tags: [postgresql, gin, tsvector, full-text-search, expression-index, btree, jsonb]

requires:
  - phase: 05-unified-schema-design
    provides: Target schema DDL (UNIFIED-SCHEMA-SPEC.md) with table definitions for vms, cves, eol_records
  - phase: 02-schema-repository-audit
    provides: INDEX-AUDIT.md with 71 indexes catalogued and 6 gaps identified
provides:
  - SEARCH-INDEX-STRATEGY.md cataloging all 10 search-related indexes with DDL, purpose, and Phase 7 actions
  - Bootstrap gap analysis for idx_cves_fts, search_vector column, and trg_cves_search_vector_update trigger
  - 2 NEW expression indexes designed for BH-005 fuzzy EOL JOIN (idx_vms_os_name_lower, idx_eol_software_key_lower)
affects: [06-index-query-optimization-design, 07-schema-implementation, 08-repository-layer-update]

tech-stack:
  added: []
  patterns:
    - "Expression indexes on LOWER() for case-insensitive JOINs"
    - "GIN index type selection: tsvector for FTS, jsonb for containment, array for element membership"
    - "B-tree vs GIN decision framework for text search patterns"

key-files:
  created:
    - .planning/phases/06-index-query-optimization-design/queries/SEARCH-INDEX-STRATEGY.md
  modified: []

key-decisions:
  - "idx_vms_os_name_lower and idx_eol_software_key_lower are both required for BH-005 fuzzy JOIN to use index scans"
  - "search_vector column, trigger, and idx_cves_fts are all bootstrap gaps that Phase 7 must resolve"
  - "Always prefer search_vector @@ to_tsquery() over ILIKE for user-facing CVE search"

patterns-established:
  - "Search index documentation pattern: DDL + purpose + query pattern + origin + Phase 7 action"

requirements-completed: [QRY-01, QRY-03]

duration: 2min
completed: 2026-03-17
---

# Phase 6 Plan 1: Search Index Strategy Summary

**Complete catalog of 10 search-related indexes (GIN tsvector/JSONB/array, expression, B-tree) with DDL, query patterns, and 5 bootstrap gaps for Phase 7**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-17T04:55:27Z
- **Completed:** 2026-03-17T04:58:23Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- Created SEARCH-INDEX-STRATEGY.md covering all 5 search index types (FTS, GIN JSONB, GIN array, expression, B-tree text)
- Documented 10 search-related indexes with complete DDL and query patterns
- Identified 5 bootstrap gaps requiring Phase 7 resolution (search_vector column, trigger, idx_cves_fts, 2 new expression indexes)
- Designed BH-005 bulk EOL lookup JOIN pattern with both-side expression indexes

## Task Commits

Each task was committed atomically:

1. **Task 6.1.1: Catalog existing search indexes and validate coverage** - `7321c0a` (docs)

## Files Created/Modified
- `.planning/phases/06-index-query-optimization-design/queries/SEARCH-INDEX-STRATEGY.md` - Complete search index strategy covering FTS, GIN, expression, and B-tree indexes

## Decisions Made
- Both `idx_vms_os_name_lower` and `idx_eol_software_key_lower` required for BH-005 fuzzy JOIN — without both, PostgreSQL falls back to nested-loop with sequential scan
- `search_vector` column + `trg_cves_search_vector_update` trigger + `idx_cves_fts` index are all bootstrap gaps (migration 006 only) — Phase 7 must add all three to bootstrap DDL
- B-tree preferred over GIN for equality/range/prefix text operations; GIN required only for tsvector, JSONB containment, and array membership

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Ready for P6.2 (composite index strategy for filtering)
- SEARCH-INDEX-STRATEGY.md provides the search index foundation that P6.2-P6.6 build upon
- Phase 7 forward references documented for 3 NEW indexes and 3 bootstrap gap items

---
*Phase: 06-index-query-optimization-design*
*Completed: 2026-03-17*
