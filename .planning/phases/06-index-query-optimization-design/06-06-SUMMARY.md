---
phase: 06-index-query-optimization-design
plan: "06"
subsystem: database
tags: [postgres, sql, index, query-optimization, asyncpg, materialized-views]

requires:
  - phase: 05-unified-schema-design
    provides: Target schema DDL (UNIFIED-SCHEMA-SPEC.md) with all table/MV definitions
  - phase: 06-index-query-optimization-design (P6.1-P6.5)
    provides: Search, filter, join, aggregation, and pagination strategy documents
provides:
  - TARGET-SQL-CVE-DOMAIN.md with 16 queries covering 8 CVE views
  - TARGET-SQL-INVENTORY-DOMAIN.md with 13 queries covering 9 Inventory/EOL views
  - TARGET-SQL-ADMIN-DOMAIN.md covering 7 Admin views (2 with DB queries, 5 no-DB)
  - Complete 24-view target SQL reference for Phase 8 repository rewrites
  - Cross-reference tables mapping views to Phase 8 repositories and Phase 9 routers
affects: [phase-07-schema-implementation, phase-08-repository-update, phase-09-ui-integration]

tech-stack:
  added: []
  patterns:
    - "asyncpg $1/$2 parameterized SQL for all queries"
    - "MV-first read path for dashboard/trending/posture views"
    - "Keyset pagination for large result sets (cve-database)"
    - "CTE pattern for bulk VM+EOL JOIN (BH-005)"
    - "Single-query patch management view replacing dual-query load (BH-010)"
    - "Server-side sort with ALLOWED_SORT_COLUMNS whitelist (BH-009)"

key-files:
  created:
    - .planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-CVE-DOMAIN.md
    - .planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-INVENTORY-DOMAIN.md
    - .planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-ADMIN-DOMAIN.md
  modified: []

key-decisions:
  - "All 24 views fully documented with target SQL, index usage, pagination, and Phase 8/9 mapping"
  - "10 bad hacks (BH-001 through BH-010) have target SQL fixes across the 3 domain files"
  - "18 views have DB queries; 6 views are no-DB (in-memory, JSONL, or chat/streaming)"
  - "35+ distinct SQL queries documented across all 3 domain files"

patterns-established:
  - "Domain file structure: View header -> Query blocks -> Index usage -> Pagination -> BH reference -> Repository -> Router"
  - "Cross-reference table at end of each domain file linking views to Phase 8/9 artifacts"
  - "No-DB views explicitly documented with explanation of data source"

requirements-completed: [QRY-01, QRY-03]

duration: 5min
completed: 2026-03-17
---

# Phase 6 Plan 6: Target SQL for All High-Traffic Endpoints Summary

**Complete target SQL reference for all 24 UI views across 3 domain files (CVE, Inventory/EOL, Admin) with asyncpg parameterized queries, index usage documentation, and Phase 8/9 forward references**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T04:56:00Z
- **Completed:** 2026-03-17T05:01:19Z
- **Tasks:** 3
- **Files created:** 3

## Accomplishments

- Created TARGET-SQL-CVE-DOMAIN.md with 16 distinct SQL queries covering all 8 CVE views (cve-dashboard, cve-database, cve-detail, vm-vulnerability, cve_alert_config, cve_alert_history, visualizations, alerts)
- Created TARGET-SQL-INVENTORY-DOMAIN.md with 13 distinct SQL queries covering all 9 Inventory/EOL views (inventory, resource-inventory, patch-management, eol, eol-inventory, eol-management, eol-searches, os-normalization-rules, inventory-asst)
- Created TARGET-SQL-ADMIN-DOMAIN.md covering all 7 Admin/Operational views with 4 cache freshness queries, 1 audit trail write, and 5 no-DB view explanations
- Documented target SQL fixes for all 10 query-pattern bad hacks: BH-001 through BH-010
- Cross-reference tables in all 3 files map each view to Phase 8 repository methods and Phase 9 routers

## Task Commits

Each task was committed atomically:

1. **Task 6.6.1: CVE domain target SQL (8 views)** - `f92054d` (docs)
2. **Task 6.6.2: Inventory & EOL domain target SQL (9 views)** - `e80656b` (docs)
3. **Task 6.6.3: Admin & Operational domain target SQL (7 views)** - `34dff96` (docs)

**Plan metadata:** (pending)

## Files Created/Modified

- `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-CVE-DOMAIN.md` - 16 queries for 8 CVE domain views
- `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-INVENTORY-DOMAIN.md` - 13 queries for 9 Inventory/EOL views
- `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-ADMIN-DOMAIN.md` - 7 Admin views (2 DB, 5 no-DB)

## Decisions Made

- All 24 UI views documented with target SQL across 3 domain-organized files following the plan specification exactly
- Every SQL query uses asyncpg `$1/$2` parameterized syntax with no string interpolation
- All 10 bad hacks (BH-001 through BH-010) have corresponding target SQL fixes
- No-DB views (6 total) explicitly documented with data source explanation (in-memory, JSONL, chat/streaming, external MCP)
- I-07 (hardcoded 35% DB load) documented with pg_stat_activity replacement query for Phase 9

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Git branch topology: commits initially landed on wrong branches (feat/06-04-aggregation-strategy, feat/06-05-pagination-strategy, feat/06-02-filter-index-strategy) due to branch checkout resolution. Resolved by cherry-picking all 3 commits onto feat/06-06-target-sql-all-endpoints.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Phase 6 complete** -- All 6/6 plans done (P6.1 Search, P6.2 Filter, P6.3 Join, P6.4 Aggregation, P6.5 Pagination, P6.6 Target SQL)
- **Ready for Phase 7:** Schema Implementation -- migrations 027-032 can be written using UNIFIED-SCHEMA-SPEC.md (Phase 5) + all index/query strategy documents (Phase 6)
- Phase 8 repository rewrites have target SQL for every query method
- Phase 9 router updates have exact API endpoint mappings

---
*Phase: 06-index-query-optimization-design*
*Completed: 2026-03-17*
