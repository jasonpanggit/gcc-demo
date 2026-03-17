---
phase: 06-index-query-optimization-design
plan: 05
subsystem: database
tags: [postgresql, pagination, keyset, offset-limit, cursor, sql, indexing]

requires:
  - phase: 06-index-query-optimization-design (P6.1, P6.2)
    provides: Search index strategy, filter index strategy
provides:
  - Per-view pagination mode assignment for all 24 views
  - Keyset pagination SQL patterns for cve-database.html
  - Offset/limit SQL template with count queries
  - Server-side sorting design for eol-inventory (BH-009 fix)
  - Pagination index requirements summary
affects: [phase-7-schema-implementation, phase-8-repository-update, phase-9-ui-integration]

tech-stack:
  added: []
  patterns: [keyset-pagination, cursor-token-base64, sort-column-whitelist, count-caching-l1]

key-files:
  created:
    - .planning/phases/06-index-query-optimization-design/queries/PAGINATION-STRATEGY.md
  modified: []

key-decisions:
  - "Only cve-database.html uses keyset pagination (8,608+ growing CVEs); all other paginated views use offset/limit"
  - "Cursor token format: base64url(JSON) with compound key (published_at, cve_id) for uniqueness"
  - "Count queries cached in L1 for 60s to avoid per-page re-counting"
  - "BH-009 server-side sorting uses ALLOWED_SORT_COLUMNS whitelist to prevent SQL injection"
  - "15 of 24 views need no pagination (dashboards, chat UIs, config pages, small datasets)"

patterns-established:
  - "Keyset pagination: ROW value comparison (a, b) < (cursor_a, cursor_b) with compound sort key"
  - "Sort column whitelist: map user-facing names to DB column names, reject unknown"
  - "Pagination response format: has_next/has_prev/next_cursor/prev_cursor for keyset; page/total_pages for offset"

requirements-completed: [QRY-01, QRY-03]

duration: 3 min
completed: 2026-03-17
---

# Phase 6 Plan 5: Pagination Strategy Summary

**Designed keyset and offset/limit pagination strategies for all 24 UI views with SQL patterns, cursor token format, and BH-009 server-side sorting fix**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-17T04:55:42Z
- **Completed:** 2026-03-17T04:58:54Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

- Assigned pagination mode (keyset, offset/limit, or none) to all 24 UI views based on dataset size and access patterns
- Fully specified keyset pagination for cve-database.html: first/next/prev page SQL, cursor token format, API response schema
- Documented offset/limit SQL patterns for 8 views with per-view ORDER BY and index coverage
- Designed server-side sorting for eol-inventory.html (BH-009 fix) with sort column whitelist preventing SQL injection
- Mapped 11 indexes to their supported pagination patterns across all paginated views

## Task Commits

Each task was committed atomically:

1. **Task 6.5.1: Design per-view pagination strategy with SQL patterns and index requirements** - `0bb4e79` (docs)

## Files Created/Modified

- `.planning/phases/06-index-query-optimization-design/queries/PAGINATION-STRATEGY.md` - Complete pagination specification: strategy overview, per-view assignment table (24 rows), keyset implementation (cursor format, first/next/prev SQL), offset/limit template, BH-009 sorting fix, index requirements summary (11 indexes)

## Decisions Made

1. **Keyset only for cve-database.html** -- Only one view (cve-database) has enough rows (8,608+ and growing) to justify keyset pagination complexity. All other paginated views have <1,000 rows per query.
2. **Compound cursor key (published_at, cve_id)** -- Multiple CVEs can share the same published_at timestamp, so cve_id is the tiebreaker ensuring unique, stable ordering.
3. **60-second L1 count cache** -- COUNT(*) queries are expensive with filters; caching for 60s avoids re-counting on every page turn while keeping counts reasonably fresh.
4. **Sort whitelist pattern** -- ALLOWED_SORT_COLUMNS maps user input to DB columns, preventing SQL injection while supporting all 10 sortable columns in eol-inventory.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- P6.5 complete; one more plan remaining (P6.6: target SQL for every high-traffic endpoint)
- PAGINATION-STRATEGY.md ready for Phase 7 migration DDL (index creation) and Phase 8 repository implementation
- BH-009 sorting fix documented for Phase 8 implementation

---
*Phase: 06-index-query-optimization-design*
*Completed: 2026-03-17*
