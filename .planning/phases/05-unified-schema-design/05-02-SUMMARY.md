---
phase: 05-unified-schema-design
plan: "02"
subsystem: database
tags: [postgresql, cve, schema-design, ddl, foreign-keys, materialized-views]

requires:
  - phase: 02-schema-repository-audit
    provides: BASE-TABLES.md with runtime-authoritative DDL for cves, kb_cve_edges, vm_cve_match_rows, cve_scans
  - phase: 04-cache-layer-specification
    provides: MSRC-CACHE-SPEC.md (I-01 resolution), TTL-TIERS-SPEC.md (cached_at requirement), CACHE-GAPS-SUMMARY.md (migration blueprint)
provides:
  - CVE-TABLES.md with finalized DDL for 5 CVE domain tables
  - I-09 resolution documentation (canonical vs wrong column mapping)
  - I-01 resolution confirmation (kb_cve_edges canonical, kb_cve_edge DROP)
  - 4 new FK constraints across vm_cve_match_rows and cve_vm_detections
  - latest_completed_scan_id() function DDL
  - Mermaid ERD for full CVE domain relationships
affects: [05-03, 05-06, 05-07, 06-index-optimization, 07-schema-implementation, 08-repository-update]

tech-stack:
  added: []
  patterns:
    - "DEFERRABLE INITIALLY DEFERRED FK for batch insert scenarios"
    - "Pattern B (cached_at + TTL) for LONG_LIVED staleness enforcement"
    - "Mermaid ERD for domain relationship documentation"

key-files:
  created:
    - ".planning/phases/05-unified-schema-design/schema/CVE-TABLES.md"
  modified: []

key-decisions:
  - "cves table retains 21-column bootstrap schema unchanged (ACTIVE status)"
  - "kb_cve_edges gets cached_at TIMESTAMPTZ column for LONG_LIVED TTL tracking"
  - "vm_cve_match_rows gets 2 new FKs: vm_id->vms.resource_id and cve_id->cves.cve_id"
  - "cve_vm_detections gets 2 new FKs: resource_id->vms.resource_id and cve_id->cves.cve_id"
  - "cve_scans unchanged (ACTIVE) with latest_completed_scan_id() function retained"
  - "I-09 resolved: 5 migration 011 column names mapped to canonical equivalents"
  - "I-01 confirmed: kb_cve_edges (plural) CANONICAL, kb_cve_edge (singular) DROP in Phase 7"

patterns-established:
  - "CVE domain FK strategy: CASCADE DELETE everywhere, DEFERRABLE on batch-insert paths"
  - "Table status tagging: ACTIVE (no change), MODIFIED (new columns/constraints)"
  - "Cross-phase action documentation: Phase 7 migration DDL + Phase 8 rewiring actions"

requirements-completed: [DB-01, DB-02, DB-03]

duration: 5min
completed: 2026-03-17
---

# Plan 05-02: CVE Data Tables Design Summary

**Finalized target DDL for 5 CVE domain tables with I-09/I-01 resolution, 4 new FK constraints, and Mermaid ERD**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-17T02:27:37Z
- **Completed:** 2026-03-17T02:33:09Z
- **Tasks:** 4
- **Files created:** 1

## Accomplishments

- Documented canonical 21-column `cves` table DDL with search vector trigger and 6 indexes
- Added `cached_at` column to `kb_cve_edges` for LONG_LIVED (24h) TTL staleness enforcement
- Added 2 FK constraints to `vm_cve_match_rows` (vm_id->vms, cve_id->cves) fixing P2.1 bootstrap gap
- Added 2 FK constraints to `cve_vm_detections` (resource_id->vms, cve_id->cves) per strict FK policy
- Documented `cve_scans` and `latest_completed_scan_id()` function used by 4 materialized views
- Resolved I-09: mapped 5 migration 011 wrong column names to canonical equivalents
- Confirmed I-01: `kb_cve_edges` is CANONICAL, `kb_cve_edge` is DROP target with data migration SQL
- Created Mermaid ERD showing all 8 CVE domain FK relationships

## Task Commits

Each task was committed atomically:

1. **Task 05-02.1: Document cves table DDL and I-09 resolution** - `f36dcde` (docs)
2. **Task 05-02.2: Document kb_cve_edges with cached_at and I-01 resolution** - `848406f` (docs)
3. **Task 05-02.3: Document vm_cve_match_rows with new FK constraints** - `c63c32e` (docs)
4. **Task 05-02.4: Document cve_vm_detections, cve_scans, function, ERD** - `3b1c631` (docs)

## Files Created/Modified

- `.planning/phases/05-unified-schema-design/schema/CVE-TABLES.md` - Complete CVE domain schema spec with 5 table DDLs, function DDL, I-09/I-01 resolutions, and Mermaid ERD

## Decisions Made

- Retained `cves` table with 21-column bootstrap schema unchanged (migration 011 is a silent no-op)
- Added `cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` to `kb_cve_edges` per P4.4 TTL-TIERS-SPEC Pattern B
- Used `DEFERRABLE INITIALLY DEFERRED` on `fk_vmcvematch_cve` for batch scan insert compatibility
- Documented `idx_cvevmdet_resource_cve` UNIQUE index on `(resource_id, cve_id)` for detection dedup
- Included `detection_source` and `matched_criteria` columns in `vm_cve_match_rows` target DDL
- Simplified `cve_scans` to plan-specified 7 columns (dropped bootstrap's `error` and `created_at` for clean spec)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CVE domain schema design complete -- ready for P5.3 (Inventory tables)
- `vms` table FK references in vm_cve_match_rows and cve_vm_detections depend on P5.1 completion
- Phase 6 index optimization has 4 forward references from this plan (GAP-01, GAP-02, GAP-05, GAP-03/04)
- Phase 7 migration has clear DDL targets: `ALTER TABLE kb_cve_edges ADD COLUMN cached_at`, data migration from `kb_cve_edge`, new FK constraints
- Phase 8 repository rewiring has 3 documented actions: cve_metadata_sync_job.py, MSRCKBCVESyncJob, KBCVEInferenceJob

---
*Phase: 05-unified-schema-design*
*Completed: 2026-03-17*
