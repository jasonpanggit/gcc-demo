---
phase: 06-index-query-optimization-design
plan: "02"
subsystem: database
tags: [postgresql, indexes, b-tree, composite, partial, filter, performance]

requires:
  - phase: 05-unified-schema-design
    provides: Target schema DDL (UNIFIED-SCHEMA-SPEC.md) with table definitions and column types
  - phase: 02-schema-repository-audit
    provides: INDEX-AUDIT.md with 6 gaps (GAP-01 through GAP-06) and redundancy findings
  - phase: 01-ui-view-audit
    provides: UI filter patterns from all 24 auditable views
provides:
  - Complete filter index specification: 11 new indexes (2 GAP resolutions, 4 composites, 5 partials)
  - Validation of 15 existing filter indexes with RETAINED/RETAIN-BUT-REVIEW status
  - Column ordering rationale for all composite indexes
  - Phase 7 migration distribution (migration 031 and 032)
affects: [06-index-query-optimization-design, 07-schema-implementation]

tech-stack:
  added: []
  patterns:
    - "Equality column first, range/sort column second in composite B-tree indexes"
    - "Partial indexes for common WHERE clause predicates (enabled=true, status=completed, severity IN)"
    - "Phase 7 migration distribution: alerting indexes in 031, optimization indexes in 032"

key-files:
  created:
    - .planning/phases/06-index-query-optimization-design/queries/FILTER-INDEX-STRATEGY.md
  modified: []

key-decisions:
  - "GAP-01 resolved: standalone idx_cves_severity retained alongside composite idx_cves_severity_published for equality-only efficiency"
  - "GAP-02 resolved: composite (cvss_v3_severity, published_at) with equality-first ordering for dashboard time-range + severity queries"
  - "GAP-06 resolved: idx_wfctx_expires partial index added to bootstrap DDL for parity with migration 006"
  - "GAP-05 mitigated: idx_scans_completed partial index on cve_scans for O(1) latest_completed_scan_id() access"
  - "Alerting indexes (3) assigned to migration 031; optimization indexes (8) assigned to migration 032"
  - "idx_alert_rules_enabled marked RETAIN-BUT-REVIEW for Phase 10 evaluation"
  - "R-01 (resource_inventory normalized OS index redundancy) deferred to Phase 10"

patterns-established:
  - "Filter Index Registry pattern: every filter index documented with DDL, query patterns, column ordering rationale, and Phase 7 action"
  - "Composite index ordering: equality column first, range/sort column second"
  - "Partial index design: smaller index for dominant WHERE predicate, coexists with full index for other access patterns"

requirements-completed:
  - QRY-01
  - QRY-03

duration: 5 min
completed: 2026-03-17
---

# Phase 6 Plan 2: Filter Index Strategy Summary

**Designed 11 new filter indexes (2 GAP resolutions, 4 composites, 5 partials) resolving GAP-01/02/06 and covering all Phase 1 UI filter patterns, with complete DDL and Phase 7 migration distribution**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T04:55:35Z
- **Completed:** 2026-03-17T05:00:51Z
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

- Resolved GAP-01 (cves severity B-tree), GAP-02 (cves severity+published_at composite), and GAP-06 (workflow_contexts expires_at bootstrap parity)
- Mitigated GAP-05 with idx_scans_completed partial index for O(1) latest scan access
- Designed 4 new composite indexes driven by Phase 1 UI filter patterns (severity+score, subscription+os, alert severity+fired_at, patch resource+last_modified)
- Designed 5 new partial indexes for common WHERE clause patterns (active rules, high severity CVEs, completed scans, workflow expires, unsent alerts)
- Validated 15 existing filter indexes with RETAINED/RETAIN-BUT-REVIEW status
- Documented column ordering rationale for every composite index
- Created Complete Filter Index Registry with 25 total indexes and Phase 7 migration distribution

## Task Commits

Each task was committed atomically:

1. **Task 6.2.1: Design composite, partial, and single-column filter indexes** - `dd16097` (docs)

## Files Created/Modified

- `.planning/phases/06-index-query-optimization-design/queries/FILTER-INDEX-STRATEGY.md` - Complete filter index specification with 6 sections: GAP-01 resolution, GAP-02 resolution, composite indexes, partial indexes, existing index validation, complete registry

## Decisions Made

1. **GAP-01 standalone retained alongside GAP-02 composite** - Standalone severity index is more efficient for equality-only filters without published_at. Both indexes serve different query patterns: standalone for simple severity equals, composite for severity+date range.

2. **GAP-05 mitigated via partial index, not resolved** - True GAP-05 resolution (partial index on dynamic scan_id) is impossible in PostgreSQL. The idx_scans_completed partial index provides O(1) access to latest_completed_scan_id() function, which is the practical bottleneck.

3. **Alerting indexes in migration 031, optimization indexes in migration 032** - Alerting indexes are created inline with the redesigned cve_alert_rules and cve_alert_history tables (migration 031). All other new filter indexes go in the dedicated optimization migration (032).

4. **idx_alert_rules_enabled kept as RETAIN-BUT-REVIEW** - Partially subsumed by partial idx_alert_rules_active, but needed if any query filters disabled rules. Phase 10 should verify and potentially drop.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FILTER-INDEX-STRATEGY.md ready for Phase 6 plans P6.3 (join indexes) and P6.6 (target SQL) to reference
- Phase 7 migration 031 and 032 have complete DDL for all 11 new filter indexes
- GAP-01, GAP-02, GAP-06 fully resolved; GAP-05 mitigated
- Ready for P6.3: Design index strategy for cross-table joins (covering indexes, INCLUDE columns)

---
*Phase: 06-index-query-optimization-design*
*Completed: 2026-03-17*
