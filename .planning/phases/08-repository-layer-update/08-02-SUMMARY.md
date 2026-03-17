---
phase: 08-repository-layer-update
plan: "02"
subsystem: database
tags: [asyncpg, postgresql, cve, repository, materialized-views]

requires:
  - phase: 07-schema-implementation
    provides: Target schema DDL (migrations 027-032, pg_database.py bootstrap)
  - phase: 06-index-query-optimization-design
    provides: TARGET-SQL-CVE-DOMAIN.md with 16 queries
provides:
  - CVERepository class with 16+ methods for all CVE-domain queries
  - MV refresh with 3-tier ordering (independent, scan-scoped, detail)
  - CVE upsert and KB-CVE edge upsert write paths
  - MSRC cache freshness query
affects: [08-repository-layer-update, 09-ui-integration-update]

tech-stack:
  added: []
  patterns: [repository-per-domain, mv-first-reads, tiered-mv-refresh, asyncpg-parameterized-queries]

key-files:
  created:
    - app/agentic/eol/utils/repositories/cve_repository.py
  modified: []

key-decisions:
  - "All 16 CVE-domain queries implemented verbatim from Phase 6 TARGET-SQL-CVE-DOMAIN.md"
  - "MV refresh uses 3-tier ordering per P6.4 AGGREGATION-STRATEGY.md"
  - "Write paths (upsert_cve, upsert_kb_cve_edges) use ON CONFLICT DO UPDATE for idempotency"
  - "Every read method has per-method except asyncpg.PostgresError error handling"

patterns-established:
  - "Repository pattern: class with asyncpg.Pool constructor, Dict/List[Dict] returns"
  - "SQL constants as module-level strings with asyncpg $1/$2 parameterized syntax"
  - "Per-method try/except with logger.error and safe fallback return"

requirements-completed: [DB-04, QRY-02]

duration: 11min
completed: 2026-03-17
---

# Phase 8 Plan 2: CVERepository -- Dashboard MVs, Search, Detail, VM Posture Summary

**CVERepository with 16+ methods covering all Phase 6 CVE-domain queries, 3-tier MV refresh, and write paths for NVD/MSRC sync**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-17T08:43:57Z
- **Completed:** 2026-03-17T08:55:05Z
- **Tasks:** 4
- **Files modified:** 1

## Accomplishments
- Created CVERepository class with complete coverage of all 16 CVE-domain queries from Phase 6
- Implemented 3-tier MV refresh (tier1: dashboard, tier2: scan-scoped, tier3: detail)
- Eliminated 7 bad hacks: BH-001 (dashboard MV reads), BH-002 (full-filter search with FTS), BH-003 (inline LEFT JOIN to mv_cve_exposure), BH-004 (single GROUP BY for OS breakdown), BH-006 (uses vms not inventory_vm_metadata), BH-007 (SQL WHERE for subscription/RG), BH-008 (server-side multi-filter on MV)
- All SQL uses asyncpg parameterized $1/$2 syntax -- zero string interpolation

## Task Commits

Each task was committed atomically:

1. **Task P8.2.1: Dashboard MV read methods** - `1de4e63` (feat) - 5 methods: get_dashboard_summary, get_trending_data, get_top_cves_by_score, get_vm_posture_summary, get_os_cve_breakdown
2. **Tasks P8.2.2-P8.2.4: Search + Detail + VM Posture + MV refresh + Write paths** - `35a50b4` (feat) - 11 additional methods completing the full 16-query coverage

## Files Created/Modified
- `app/agentic/eol/utils/repositories/cve_repository.py` - CVERepository class with 16+ methods, all SQL constants, MV tier definitions, write paths

## Decisions Made
- All SQL constants copied verbatim from Phase 6 TARGET-SQL-CVE-DOMAIN.md
- UPSERT_CVE uses ON CONFLICT (cve_id) DO UPDATE with COALESCE for non-destructive merges
- UPSERT_KB_CVE_EDGE uses ON CONFLICT (kb_number, cve_id, source) composite PK
- MV refresh iterates tiers sequentially, MVs within tiers sequentially (parallel deferred to Phase 10)
- REFRESH MATERIALIZED VIEW CONCURRENTLY used for all MVs (requires unique indexes, already created in Phase 7)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Consolidated P8.2.2-P8.2.4 into single commit**
- **Found during:** Task P8.2.2 (search methods)
- **Issue:** External linter process kept reverting file changes between atomic commits, making task-per-commit impossible
- **Fix:** Combined tasks P8.2.2, P8.2.3, and P8.2.4 into a single write+commit cycle
- **Files modified:** app/agentic/eol/utils/repositories/cve_repository.py
- **Verification:** All 27 acceptance criteria checks pass
- **Committed in:** 35a50b4

**2. [Rule 1 - Bug] UPSERT_CVE column names aligned to bootstrap schema**
- **Found during:** Task P8.2.4 (write paths)
- **Issue:** Linter-generated UPSERT_CVE used migration 011 column names (modified_at, cvss_v2_vector, etc.) instead of bootstrap schema names (last_modified_at, vector_string_v2, etc.)
- **Fix:** Aligned all column names to bootstrap cves schema from P5.2 CVE-TABLES.md
- **Files modified:** app/agentic/eol/utils/repositories/cve_repository.py
- **Verification:** Column names match bootstrap DDL in pg_database.py
- **Committed in:** 35a50b4

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** No scope change. All 16 methods implemented with correct SQL.

## Issues Encountered
- Environment branch-switching during commit operations required cherry-pick to land commits on correct branch

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CVERepository complete, ready for Phase 8 Plan 3 (Patch repositories)
- Phase 9 can wire cve_dashboard.py, cve.py, cve_inventory.py, vm_inventory.py to CVERepository methods

---
*Phase: 08-repository-layer-update*
*Completed: 2026-03-17*
