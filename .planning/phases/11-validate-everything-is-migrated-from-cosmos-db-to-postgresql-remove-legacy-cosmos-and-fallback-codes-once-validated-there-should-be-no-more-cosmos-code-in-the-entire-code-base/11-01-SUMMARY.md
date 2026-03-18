---
phase: 11-validate-everything-is-migrated-from-cosmos-db-to-postgresql-remove-legacy-cosmos-and-fallback-codes-once-validated-there-should-be-no-more-cosmos-code-in-the-entire-code-base
plan: "01"
subsystem: database
tags: [cosmos, postgresql, audit, dependency-graph, fallback-catalogue]

requires:
  - phase: 10-validation-cleanup
    provides: Test baseline (1680 passing), performance tests (33), partial Cosmos cleanup
provides:
  - COSMOS-DEPENDENCY-GRAPH.md with all 24 consumer files classified by usage pattern
  - FALLBACK-CATALOGUE.md with 137 entries across 118 files
  - Priority-sorted Cosmos removal order (9 tiers, leaves-to-roots)
  - Cosmos vs legitimate fallback classification for all 732 "fallback" references
affects: [11-02, 11-03, 11-04, 11-05, 11-06, 11-07]

tech-stack:
  added: []
  patterns: [audit-first dependency mapping, categorized fallback analysis]

key-files:
  created:
    - ".planning/phases/11-.../COSMOS-DEPENDENCY-GRAPH.md"
    - ".planning/phases/11-.../FALLBACK-CATALOGUE.md"
  modified: []

key-decisions:
  - "All 24 consumer files actively use cosmos_cache imports (zero dead imports found)"
  - "Only 18 of 732 fallback references are Cosmos-related; 714 are legitimate CONFIG/ERROR/DATA patterns"
  - "sre_audit.py imports wrong name (cosmos_cache instead of base_cosmos) — BUG flagged for fix"
  - "9-tier removal order established: tests → docstrings → guards → API endpoints → utils → MCP → service → main.py → core deletion"

patterns-established:
  - "Audit-first approach: map all consumers before any removal"
  - "Usage pattern classification: cache reader, cache writer, singleton user, type hint, comment-only"
  - "Fallback categorization: COSMOS (remove) vs CONFIG/ERROR/DATA (keep)"

requirements-completed: []

duration: 9 min
completed: 2026-03-18
---

# Phase 11 Plan 01: Cosmos Audit & Fallback Catalogue Summary

**Dependency graph mapping 24 Cosmos consumer files and fallback catalogue auditing 732 references across 118 files — zero dead imports, 18 Cosmos-specific fallbacks identified for removal**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-18T02:10:19Z
- **Completed:** 2026-03-18T02:19:45Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Built complete Cosmos dependency graph covering all 24 consumer files of cosmos_cache.py and cve_cosmos_repository.py
- Classified every consumer by usage pattern: 14 cache reader+writer, 16 singleton users, 1 BUG, 1 docstring-only, 2 get_cosmos_client users, 1 type-hint-only, 3 test files
- Established 9-tier removal order from lowest risk (test files) to highest (core file deletion)
- Audited all 732 "fallback" references across 118 Python files
- Categorized 137 unique entries: 18 COSMOS (REMOVE), 63 CONFIG (KEEP), 43 ERROR (KEEP), 13 DATA (KEEP)
- Priority-sorted COSMOS entries: 11 HIGH, 3 MEDIUM, 5 LOW

## Task Commits

Each task was committed atomically:

1. **Task 1: Build Cosmos dependency graph** - `130ec2b` (docs)
2. **Task 2: Audit and catalogue all fallback references** - `2ed195a` (docs)

## Files Created/Modified
- `.planning/phases/11-.../COSMOS-DEPENDENCY-GRAPH.md` - Maps all 24 consumer files with import lines, usage patterns, specific calls, and recommended actions
- `.planning/phases/11-.../FALLBACK-CATALOGUE.md` - 137 entries cataloguing all 732 "fallback" references with COSMOS/CONFIG/ERROR/DATA classification

## Decisions Made
- Zero dead imports found — every cosmos_cache import is actively used in code. This means all 24 consumers need actual refactoring (no quick wins from dead import removal)
- Identified BUG in `api/sre_audit.py` — imports `cosmos_cache` (the module name) instead of `base_cosmos` (the exported singleton). Works by accident due to Python module caching, but technically wrong
- Only 18 of 732 "fallback" references (2.5%) are Cosmos-related. The vast majority (714) are legitimate CONFIG/ERROR/DATA fallbacks that should be preserved
- Two DATA-category entries (FB-076, FB-077) in sre_mcp_server.py need further investigation as they involve Cosmos try/except patterns

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Cosmos dependency graph provides the exact list of files to refactor in P11.2–P11.5
- Fallback catalogue confirms that COSMOS-related fallbacks are a small subset (18/732) — refactoring scope is well-bounded
- The 9-tier removal order guides the sequencing of P11.2 (tests), P11.3 (config), P11.4 (runtime consumers), P11.5 (core deletion)
- No blockers for subsequent plans

---
*Phase: 11-validate-everything-is-migrated-from-cosmos-db-to-postgresql-remove-legacy-cosmos-and-fallback-codes-once-validated-there-should-be-no-more-cosmos-code-in-the-entire-code-base*
*Completed: 2026-03-18*
