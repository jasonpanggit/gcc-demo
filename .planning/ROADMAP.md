# PostgreSQL Schema & Data Architecture Optimization

**Project**: gcc-demo EOL Platform — Schema & Performance Overhaul
**Created**: 2026-03-16
**Status**: In Progress

---

## Vision

> Every UI view is served by a single, fast PostgreSQL query. No multiple queries, no in-memory joins, no hardcoded fallbacks, no denormalized duplicates.

---

## Phases

### Phase 1: UI View Audit

**Goal**: Produce a complete, grounded map of every UI view and the exact data it needs from the database — columns, filters, sorts, aggregations, pagination.

**Requirements**: UI-01, UI-02, UI-03, UI-04

**Depends on**: Phase 0

**Plans**: 7 plans

Plans:
- [x] P1.1: Enumerate all UI routes from `api/ui.py` and link each to its HTML template
- [x] P1.2: Audit CVE views: `cve-dashboard.html`, `cve-database.html`, `cve-detail.html` — document every data field displayed
- [x] P1.3: Audit Inventory views: `inventory.html`, `resource-inventory.html`, `vm-vulnerability.html`, `inventory-asst.html`
- [x] P1.4: Audit EOL views: `eol.html`, `eol-searches.html`, `eol-inventory.html`, `eol-management.html`, `os-normalization-rules.html`
- [x] P1.5: Audit Patch views: `patch-management.html`
- [x] P1.6: Audit Alert/Admin/Observability views (11 views total)
- [x] P1.7: Cross-view interaction patterns summary

---

### Phase 2: Schema & Repository Audit

**Goal**: Produce a complete, accurate picture of the current PostgreSQL schema — every table, view, index, relationship, and the repository classes that own them.

**Requirements**: DB-01, DB-02, DB-03, DB-04

**Depends on**: Phase 1

**Plans**: 7 plans

Plans:
- [x] P2.1: Document all base tables with columns, types, constraints, PKs, FKs
- [x] P2.2: Document migration 011 tables
- [x] P2.3: Document all materialized views
- [x] P2.4: Document all regular views
- [x] P2.5: Audit all 14+ repository classes
- [x] P2.6: Document existing indexes — identify overlapping, missing, or redundant
- [x] P2.7: Map each UI view to tables/views/repositories that serve it

---

### Phase 3: Bad-Hack Catalogue

**Goal**: Enumerate every instance of "bad hacking" — multiple queries, in-memory joins, hardcoded fallbacks, denormalized data — with specific file, function, and line range for each.

**Requirements**: QRY-02, QRY-03, QRY-04

**Depends on**: Phase 2

**Plans**: 5 plans

Plans:
- [x] P3.1: Grep all routers for N+1 patterns (multiple `pool.acquire()` calls per endpoint)
- [x] P3.2: Identify in-memory join/filter patterns
- [x] P3.3: Identify hardcoded fallback values
- [x] P3.4: Identify denormalization and schema duplication
- [x] P3.5: Prioritize hacks by impact and create priority matrix

---

### Phase 4: Cache Layer Specification

**Goal**: Design the caching strategy for all three remote Azure data sources — LAW, ARG, MSRC — so that UI queries always hit PostgreSQL, never the remote API.

**Requirements**: CACHE-01, CACHE-02, CACHE-03, CACHE-04

**Depends on**: Phase 2

**Plans**: 6 plans

Plans:
- [x] P4.1: Audit current ARG cache — document what's cached, TTLs, refresh triggers
- [x] P4.2: Audit current LAW cache — document gaps vs. what LAW actually provides
- [x] P4.3: Audit current MSRC cache — document what's stored and what's missing
- [x] P4.4: Define TTL tiers for each cache table aligned with `cache_config.py`
- [x] P4.5: Design cache invalidation strategy (event-based vs time-based vs manual)
- [x] P4.6: Identify missing cache tables needed by Phase 7 schema design

---

### Phase 5: Unified Schema Design

**Goal**: Design the target schema — the final, clean table structure that all UI views will be served from. Fresh start allowed; no migration-of-existing-data required.

**Requirements**: DB-01, DB-02, DB-03

**Depends on**: Phase 1, Phase 2, Phase 3, Phase 4

**Plans**: 7 plans

Plans:
- [x] P5.1: Design the VM identity spine — single source-of-truth VM table ✅ (2026-03-17)
- [x] P5.2: Design CVE data tables with finalized column set and constraints ✅ (2026-03-17)
- [x] P5.3: Design Inventory tables — normalize or consolidate redundant OS data ✅ (2026-03-17)
- [x] P5.4: Design EOL tables — ensure fast EOL lookup by OS key ✅ (2026-03-17)
- [x] P5.5: Design Alerting tables with foreign keys and query patterns ✅ (2026-03-17)
- [x] P5.6: Design Materialized View set with refresh schedule ✅ (2026-03-17)
- [x] P5.7: Write complete target schema DDL in single spec document ✅ (2026-03-17)

---

### Phase 6: Index & Query Optimization Design

**Goal**: For every UI endpoint, write the exact target SQL query and the indexes that make it fast. Prove the design on paper before implementing.

**Requirements**: QRY-01, QRY-03

**Depends on**: Phase 5

**Plans**: 6 plans

Plans:
- [x] P6.1: Design index strategy for search (full-text, B-tree, GIN) ✅ (2026-03-17)
- [x] P6.2: Design index strategy for filtering (composite indexes) ✅ (2026-03-17)
- [x] P6.3: Design index strategy for cross-table joins (covering indexes, INCLUDE columns) ✅ (2026-03-17)
- [x] P6.4: Design aggregation strategy (MVs vs inline CTEs vs partial indexes) ✅ (2026-03-17)
- [x] P6.5: Design pagination strategy (keyset vs offset/limit) ✅ (2026-03-17)
- [x] P6.6: Write target SQL for every high-traffic endpoint ✅ (2026-03-17)

---

### Phase 7: Schema Implementation

**Goal**: Apply the target schema from Phase 5 and indexes from Phase 6 to the database. Write a single idempotent migration that can be applied to any environment.

**Requirements**: DB-01, DB-02, DB-03

**Depends on**: Phase 5, Phase 6

**Plans**: 7 plans

Plans:
- [x] P7.1: Write migration 027 — drop obsolete tables identified in Phase 3
- [x] P7.2: Write migration 028 — create/alter VM identity spine table
- [x] P7.3: Write migration 029 — finalize CVE tables with constraints and indexes ✅ (2026-03-17)
- [x] P7.4: Write migration 030 — finalize Inventory + EOL tables ✅ (2026-03-17)
- [x] P7.5: Write migration 031 — create/replace all Materialized Views
- [x] P7.6: Write migration 032 — create all optimization indexes ✅ (2026-03-17)
- [x] P7.7: Update `pg_database.py` bootstrap with new tables ✅ (2026-03-17)

---

### Phase 8: Repository Layer Update

**Goal**: Update all 14+ repository classes to use the optimized schema — eliminating N+1 patterns, in-memory joins, and multi-query workarounds at the repository level.

**Requirements**: DB-04, QRY-02

**Depends on**: Phase 7

**Plans**: 7 plans

Plans:
- [x] P8.1: Foundation -- asyncpg pool singleton + repository package init
- [x] P8.2: CVERepository -- Dashboard MVs, Search, Detail, VM Posture
- [x] P8.3: InventoryRepository -- VM Inventory, Resources, Software
- [x] P8.4: PatchRepository + AlertRepository -- Patch Management + Alert CRUD
- [x] P8.5: EOLRepository -- EOL Records, Agent Responses, Extraction Rules
- [x] P8.6: Sync Job Rewiring + Cache Freshness Queries
- [x] P8.7: Consumer Rewiring -- Import Paths + main.py Integration

---

### Phase 9: UI Integration Update

**Goal**: Update API routers and service layers to use single-query patterns, remove all Python-level aggregation workarounds, and eliminate hardcoded fallbacks.

**Requirements**: QRY-01, QRY-02, QRY-04

**Depends on**: Phase 8

**Plans**: 7 plans

Plans:
- [x] P9.1: Add Missing CVERepository + InventoryRepository Methods ✅ (2026-03-17)
- [x] P9.2: Rewire `api/cve_inventory.py` -- Eliminate BH-002, BH-003 ✅ (2026-03-17)
- [x] P9.3: Rewire `api/cve.py` -- Eliminate BH-001 N+1 Pattern ✅ (2026-03-17)
- [x] P9.4: Rewire `api/inventory.py` -- Eliminate BH-005 N+1 EOL Lookups ✅ (2026-03-17)
- [x] P9.5: Rewire `api/patch_management.py` Read Endpoints ✅ (2026-03-17)
- [x] P9.6: Update `api/eol.py` — consolidate multi-query lookups ✅ (2026-03-17)
- [x] P9.7: Update PDF export path — use PG fast-path instead of Python analytics ✅ (2026-03-17)

---

### Phase 10: Validation & Cleanup

**Goal**: Prove performance improvements are real, remove all dead code identified in earlier phases, and leave the codebase in a clean state.

**Requirements**: QRY-03

**Depends on**: Phase 9

**Status**: 🔄 In Progress (1 / 7 plans)

**Plans**: 7 plans

Plans:
- [x] P10.1: Baseline + post-optimization query timing with EXPLAIN ANALYZE
- [ ] P10.2: Validate index usage — confirm index scans on all large tables
- [ ] P10.3: Remove `cve_in_memory_repository.py` callers
- [ ] P10.4: Remove dead Cosmos stubs
- [ ] P10.5: Remove workaround code from Phase 3 catalogue
- [ ] P10.6: Run full test suite and fix failures
- [ ] P10.7: Update `pg_database.py` final verification

---

## Key Constraints

- **Migration 011 is done** — dual-source KB-CVE architecture is the baseline; don't redo it
- **API response shapes are frozen** — queries can change, JSON key names cannot
- **Fresh schema start allowed** — dev/demo environment; prioritize correctness over compatibility hacks
- **asyncpg throughout** — all SQL must be compatible with asyncpg parameterized query syntax (`$1`, `$2`)
- **No Cosmos, no Elasticsearch** — PostgreSQL only

### Phase 11: Cosmos DB Removal & PostgreSQL Migration Validation

**Goal:** Audit the entire codebase for any remaining Cosmos DB references, legacy fallback code, or dual-path logic. Validate all data flows now use PostgreSQL exclusively, then delete all Cosmos-related code so no Cosmos dependency remains in the repository.
**Requirements**: TBD
**Depends on:** Phase 10
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 11 to break down)

---

*Roadmap created: 2026-03-16*
*Last updated: 2026-03-17T14:17Z*
*Total phases: 11*
*Total plans: 64*
