---
phase: 05-unified-schema-design
plan: "05"
subsystem: database
tags: [postgresql, alerting, cve-alerts, schema-design, i-06]

requires:
  - phase: 02-schema-repository-audit
    provides: BASE-TABLES.md with current cve_alert_rules/cve_alert_history DDL
  - phase: 03-bad-hack-catalogue
    provides: BH-025/026/027 alert in-memory patterns
  - phase: 05-unified-schema-design
    provides: 05-CONTEXT.md with target cve_alert_rules/history schemas
provides:
  - ALERTING-TABLES.md with target DDL for 4 alerting domain tables
  - cve_alert_rules REDESIGNED DDL (UUID PK, explicit filter columns)
  - cve_alert_history REDESIGNED DDL (per-CVE firing model, 8 columns)
  - alert_config and notification_history documented as ACTIVE
  - I-06 resolution documentation
  - Old-to-new column mappings for Phase 8 repository rewrite
  - Mermaid ERD for alerting domain
  - Query patterns for cve-alert-config.html and cve-alert-history.html
affects: [phase-07-schema-implementation, phase-08-repository-layer-update, phase-09-ui-integration]

tech-stack:
  added: []
  patterns:
    - "Per-CVE firing model: one row per rule+CVE instead of aggregated arrays"
    - "Explicit filter columns instead of JSONB config blobs"
    - "UNIQUE constraint on (rule_id, cve_id) prevents duplicate firings"

key-files:
  created:
    - ".planning/phases/05-unified-schema-design/schema/ALERTING-TABLES.md"
  modified: []

key-decisions:
  - "cve_alert_rules uses explicit filter columns (severity_threshold, cvss_min_score, vendor_filter, product_filter) instead of JSONB config blob"
  - "cve_alert_history uses per-CVE firing model (8 columns) replacing aggregated event model (22 columns)"
  - "UNIQUE constraint on (rule_id, cve_id) prevents duplicate firings for same rule+CVE pair"
  - "alert_config and notification_history retained as ACTIVE (unchanged)"

patterns-established:
  - "REDESIGNED table pattern: document old DDL, new DDL, old-to-new column mapping, in-memory manager mapping, Phase 7 migration strategy"
  - "ACTIVE table pattern: document current DDL with note that Phase 7 retains as-is"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 4 min
completed: 2026-03-17
---

# Phase 5 Plan 5: Alerting Tables Design Summary

**Redesigned cve_alert_rules (UUID PK + explicit filter columns) and cve_alert_history (per-CVE firing model, 22->8 columns) with I-06 resolution, plus alert_config and notification_history documented as ACTIVE**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-17T02:27:28Z
- **Completed:** 2026-03-17T02:31:28Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments
- Designed `cve_alert_rules` REDESIGNED table with UUID PK and 4 explicit filter columns replacing JSONB config blob
- Designed `cve_alert_history` REDESIGNED table with per-CVE firing model (8 columns) replacing aggregated event model (22 columns)
- Documented I-06 resolution path: Phase 7 DDL + Phase 8 repository rewrite + BH-025/026/027 resolution
- Created Mermaid ERD and query patterns for Phase 8/9 implementation

## Task Commits

Each task was committed atomically:

1. **Task 05-05.1: Design cve_alert_rules REDESIGNED table** - `5e09775` (docs)
2. **Task 05-05.2: Design cve_alert_history REDESIGNED table** - `e0c8684` (docs)
3. **Task 05-05.3: Document alert_config, notification_history, and ERD** - `7af5f1a` (docs)

## Files Created/Modified
- `.planning/phases/05-unified-schema-design/schema/ALERTING-TABLES.md` - Complete alerting domain schema design (4 tables, ERD, query patterns)

## Decisions Made
- cve_alert_rules uses explicit filter columns instead of JSONB blob (per 05-CONTEXT decision)
- cve_alert_history uses per-CVE firing model: one row per rule+CVE, not one row per alert event covering N CVEs
- UNIQUE constraint on (rule_id, cve_id) prevents duplicate firings
- alert_config and notification_history retained as ACTIVE (no redesign needed)
- Phase 7 migration is DROP+CREATE for both redesigned tables (no data migration — current data is in-memory only)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ALERTING-TABLES.md ready for P5.7 consolidation into UNIFIED-SCHEMA-SPEC.md
- Phase 7 can execute DROP+CREATE migrations for both redesigned tables
- Phase 8 has complete old-to-new column mappings for AlertPostgresRepository rewrite
- I-06 resolution path fully documented across Phase 7/8

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
