---
phase: 06-index-query-optimization-design
plan: "04"
subsystem: database
tags: [postgres, materialized-views, cte, aggregation, query-optimization, index-design]

requires:
  - phase: 05-unified-schema-design
    provides: 7 retained MVs, unified schema DDL, MV source tables, latest_completed_scan_id() function
  - phase: 06-index-query-optimization-design (P6.1-P6.3)
    provides: search indexes, filter indexes, join indexes referenced by MV refresh dependencies

provides:
  - MV-vs-CTE-vs-Live decision framework for all UI endpoints
  - MV read query patterns for all 7 retained MVs with expected index usage
  - MV refresh index dependency table mapping MVs to critical indexes
  - GAP-05 resolution (latest scan access pattern via Option A)
  - BH-001 PDF export query design (same MV path as page load)
  - BH-004 aggregate_inventory_os_counts replacement query
  - CTE patterns for 4 complex query types

affects: [06-05-pagination-strategy, 06-06-target-sql-all-endpoints, 07-schema-implementation, 08-repository-layer-update, 09-ui-integration-update, 10-validation-cleanup]

tech-stack:
  added: []
  patterns:
    - "Aggregates in MVs, details from live tables, CTEs for complex readability"
    - "PDF export shares same MV read path as page load (no separate analytics)"
    - "Single MV GROUP BY replaces multi-query dual-path aggregation"
    - "latest_completed_scan_id() function for scan-scoped MV access"

key-files:
  created:
    - .planning/phases/06-index-query-optimization-design/queries/AGGREGATION-STRATEGY.md
  modified: []

key-decisions:
  - "GAP-05 resolved with Option A: rely on existing idx_vmcvematch_scan_severity composite index, no partial index lifecycle needed at demo scale"
  - "BH-001 fix: PDF export uses exact same MV read queries as page load, eliminating 5-call Python analytics path"
  - "BH-004 fix: single mv_vm_vulnerability_posture GROUP BY os_name replaces 3-query dual-path with O(N^2) JSONB cross-join fallback"
  - "MV refresh order: 3 tiers (independent, scan-scoped, detail) for dependency-aware refresh"
  - "Phase 10 revisit threshold: 100,000 vm_cve_match_rows or >5s MV refresh triggers re-evaluation of GAP-05"

patterns-established:
  - "MV-vs-CTE-vs-Live: 5-pattern decision framework for aggregation strategy"
  - "MV read queries documented with expected index scan type per MV"
  - "CTE for readability: latest_scan, bulk EOL, time-range, alert evaluation patterns"

requirements-completed: [QRY-01, QRY-03]

duration: 4min
completed: 2026-03-17
---

# Phase 6 Plan 4: Aggregation Strategy Summary

**MV-vs-CTE-vs-Live decision framework with 7 MV read queries, GAP-05 resolution, BH-001/BH-004 fix designs, and 4 CTE patterns for complex queries**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T04:55:54Z
- **Completed:** 2026-03-17T04:59:38Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

- Created comprehensive AGGREGATION-STRATEGY.md covering all aggregation concerns for the EOL platform
- Documented MV read query patterns for all 7 retained MVs with expected index usage and access patterns
- Resolved GAP-05 (latest scan access pattern) with Option A decision and Phase 10 revisit criteria
- Designed BH-001 fix: PDF export uses same 5 MV queries as page load (eliminates Python analytics path)
- Designed BH-004 fix: single `mv_vm_vulnerability_posture GROUP BY os_name` replaces 3-query O(N^2) dual-path
- Documented MV refresh index dependencies for all 8 MVs with critical indexes needed for refresh performance
- Defined 4 CTE patterns for complex queries (latest_scan, bulk EOL, time-range, alert evaluation)
- Added MV refresh ordering (3 tiers) for dependency-aware concurrent refresh

## Task Commits

Each task was committed atomically:

1. **Task 6.4.1: Design MV read queries, refresh optimization, CTE patterns, and GAP-05 strategy** - `6ad9d37` (docs)

## Files Created/Modified

- `.planning/phases/06-index-query-optimization-design/queries/AGGREGATION-STRATEGY.md` - Complete aggregation strategy: decision framework, 7 MV read queries, refresh index deps, GAP-05, BH-001/004 fixes, 4 CTE patterns

## Decisions Made

1. **GAP-05 Option A** - Rely on existing `idx_vmcvematch_scan_severity` composite index for latest scan access. No partial index lifecycle needed at current demo scale (~22,589 rows, ~525 per scan). Phase 10 revisits if >100k rows or >5s refresh.
2. **BH-001 PDF fix** - PDF export must call same repository methods as page load. No separate `_generate_pdf_analytics()` code path. 5 queries use `mv_cve_dashboard_summary`, `mv_cve_trending`, `mv_cve_top_by_score`, `mv_vm_vulnerability_posture`, and `cves` with `idx_cves_high_severity`.
3. **BH-004 OS counts fix** - Replace `aggregate_inventory_os_counts()` with single `mv_vm_vulnerability_posture GROUP BY os_name`. Sequential scan of 100-500 row MV replaces JSONB cross-join of 30 profiles x 10k CVEs.
4. **MV refresh tiers** - Tier 1 (independent MVs) → Tier 2 (scan-scoped MVs) → Tier 3 (detail MV). Allows parallel refresh within tiers while respecting data dependencies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added MV refresh ordering (3 tiers)**
- **Found during:** Task 6.4.1 (MV Refresh Index Dependencies section)
- **Issue:** Plan didn't specify refresh ordering, but dependency-aware ordering is critical for data consistency between dependent MVs
- **Fix:** Added 3-tier refresh order (independent, scan-scoped, detail) after the dependency table
- **Files modified:** AGGREGATION-STRATEGY.md
- **Verification:** Tier ordering matches MV source dependency graph from P5.6
- **Committed in:** 6ad9d37

**2. [Rule 2 - Missing Critical] Added 4th CTE pattern for alert evaluation**
- **Found during:** Task 6.4.1 (CTE Patterns section)
- **Issue:** Plan specified 3 CTE patterns but P5.5 alerting redesign introduces a natural CTE candidate (rule evaluation with dedup check)
- **Fix:** Added Section 7d: Alert Evaluation CTE pattern using active_rules + new_cves CTEs
- **Files modified:** AGGREGATION-STRATEGY.md
- **Verification:** CTE references idx_alert_rules_enabled partial index and idx_alerthistory_rule_cve unique index from P5.5
- **Committed in:** 6ad9d37

---

**Total deviations:** 2 auto-fixed (2 missing critical)
**Impact on plan:** Both additions strengthen the document without scope creep. MV refresh ordering is essential for Phase 7 implementation; alert CTE pattern integrates P5.5 alerting redesign.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- AGGREGATION-STRATEGY.md ready for reference by P6.5 (pagination strategy) and P6.6 (target SQL for all endpoints)
- All MV read queries documented with expected index usage — directly feeds into P6.6 target SQL compilation
- BH-001 and BH-004 fix designs ready for Phase 8 repository implementation
- GAP-05 resolution eliminates partial index design work — simplifies Phase 7 migration scope

---
*Phase: 06-index-query-optimization-design*
*Completed: 2026-03-17*
