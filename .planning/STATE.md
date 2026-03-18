---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-03-18T02:38:38Z"
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 73
  completed_plans: 57
---

# STATE: PostgreSQL Schema & Data Architecture Optimization

**Project:** gcc-demo EOL Platform — Schema & Performance Overhaul
**Last Updated:** 2026-03-18
**Status:** In progress — Phase 11

---

## Current Phase

**Phase 11: Cosmos DB Removal & PostgreSQL Migration Validation** 🔄 **In Progress — 3 / 7 plans done**

**Completed:** P11.1 (Cosmos Audit & Fallback Catalogue), P11.2 (Cosmos Test File Cleanup), P11.3 (Comment, Docstring & Template Cleanup)
**In Progress:** P11.4 (next)
**Next:** Phase 11 continuation

---

### Previous Phase

**Phase 10: Validation & Cleanup** ✅ **Complete -- 7 / 7 plans done**

**Completed:** P10.1 (Performance Test Infrastructure), P10.2 (Performance Validation Suite), P10.3 (Dead Code Removal — Cosmos Stubs), P10.4 (Dead Code Removal — Dual-Path, Duplicates, Legacy), P10.5 (Deprecated Table/View Cleanup), P10.6 (Fresh DB Bootstrap Verification), P10.7 (Final Test Suite Execution + Phase Sign-Off)
**Next:** Phase 11 (if planned)

---

## Phase Status

| Phase | Name | Status | Completed Plans | Notes |
|-------|------|--------|-----------------|-------|
| 1 | UI View Audit | ✅ Complete | 7 / 7 | P1.1–P1.7 done — VIEW-REGISTRY + all domain views + VIEW-INTERACTIONS |
| 2 | Schema & Repository Audit | ✅ Complete | 7 / 7 | P2.1–P2.7 done — BASE-TABLES, MIGRATION-011, MATERIALIZED-VIEWS, VIEWS, REPOSITORY-MAP, INDEX-AUDIT (P2.6), UI-TO-SCHEMA-MAP (P2.7) |
| 3 | Bad-Hack Catalogue | ✅ Complete | 5 / 5 | P3.1–P3.5 done — 49 bad hacks catalogued, Priority Matrix sorted CRITICAL→LOW, cross-validated against Phase 1-2 |
| 4 | Cache Layer Specification | ✅ Complete | 6 / 6 | P4.1 ARG-CACHE-SPEC, P4.2 LAW-CACHE-SPEC, P4.3 MSRC-CACHE-SPEC, P4.4 TTL-TIERS-SPEC, P4.5 INVALIDATION-SPEC, P4.6 CACHE-GAPS-SUMMARY |
| 5 | Unified Schema Design | ✅ Complete | 7 / 7 | P5.1 VM-IDENTITY-SPINE.md, P5.2 CVE-TABLES.md, P5.3 INVENTORY-TABLES.md, P5.4 EOL-TABLES.md, P5.5 ALERTING-TABLES.md, P5.6 MATERIALIZED-VIEWS-TARGET.md, P5.7 UNIFIED-SCHEMA-SPEC.md |
| 6 | Index & Query Optimization Design | ✅ Complete | 6 / 6 | P6.1 SEARCH-INDEX-STRATEGY.md, P6.2 FILTER-INDEX-STRATEGY.md, P6.3 JOIN-INDEX-STRATEGY.md, P6.4 AGGREGATION-STRATEGY.md, P6.5 PAGINATION-STRATEGY.md, P6.6 TARGET-SQL (3 domain files) done |
| 7 | Schema Implementation | ✅ Complete | 7 / 7 | P7.1–P7.6 done (migrations 027-032), P7.7 done (pg_database.py bootstrap DDL rewrite) |
| 8 | Repository Layer Update | ✅ Complete | 7 / 7 | P8.1–P8.7 done — pg_client, 5 domain repos, aliases, consumer rewiring |
| 9 | UI Integration Update | ✅ Complete | 7 / 7 | P9.1-P9.7 done — all 10 affected files use app.state repos; BH-001 through BH-005 eliminated; PG pool fatal at startup |
| 10 | Validation & Cleanup | ✅ Complete | 7 / 7 | P10.1–P10.7 done — perf test infra, validation suite, Cosmos stub removal, dual-path/duplicate cleanup, deprecated table cleanup, bootstrap verification, final test suite execution + phase sign-off |
| 11 | Cosmos DB Removal | 🔄 In Progress | 1 / 7 | P11.1 done — Cosmos dependency graph (24 consumers) + Fallback catalogue (137 entries, 18 COSMOS-related) |

**Legend:** ⬜ Not started | 🔄 In progress | ✅ Complete | ⚠️ Blocked

---

## Completed Work (Before This Roadmap)

The following migrations are already complete and represent the baseline for this project:

- **Migration 001–010**: Initial schema, inventory, OS profiles, optimization passes, data purges
- **Migration 011**: Dual-source KB-CVE architecture — `patch_assessments_cache`, `available_patches`, `arc_os_inventory`, `arc_software_inventory`, `kb_cve_edge`, `cve_vm_detections`, plus 3 materialized views (`vm_vulnerability_overview`, `cve_dashboard_stats`, `os_cve_inventory_counts`)
- **Migration 012–026**: Permissions grants, MV fixes, unified VM inventory, view ownership corrections, LEFT JOIN fixes

---

## Known Issues / Blockers

| ID | Issue | Affects | Priority |
|----|-------|---------|----------|
| I-01 | Dual KB-CVE table conflict: `kb_cve_edges` (original, snake_plural) vs `kb_cve_edge` (migration 011, singular) — both exist | Phase 2, 5, 7 | High |
| I-02 | ~~`INVENTORY_USE_UNIFIED_VIEW` feature flag still in place~~ — **Resolved P10.4**: verified zero references, removed by Phase 9 | Phase 3, 9 | ~~Medium~~ |
| I-03 | `mv_vm_cve_detail` ownership issues causing refresh failures (migrations 025–026 patched but startup-time only) | Phase 7 | Medium |
| I-04 | ~~`cve_dashboard.py` has both PG fast-path and Python analytics fallback~~ — **Resolved P10.4**: verified MV fast-path only | Phase 3, 9 | ~~High~~ |
| I-05 | Cosmos stubs (`cve_cosmos_repository`, `resource_inventory_cosmos`, `cosmos_cache`) still present — not yet removed | Phase 10 | Low |
| I-06 | CVE alert rules and history stored in-memory only (`cve_alert_rule_manager`, `cve_alert_history_manager`) — lost on restart | Phase 5, 7 | High |
| I-07 | `index.html` "Database Load" metric is hardcoded at 35% — not a real measurement | Phase 3, 9 | Medium |
| I-08 | `cache.html` JS calls deprecated Cosmos endpoints (`/api/cache/cosmos/*`) that return 410 Gone — dead code in JS | Phase 10 | Low |
| I-09 | `cve_metadata_sync_job.py` uses migration 011 `cves` column names (`severity`, `cvss_score`, `vendor`, `product`, `cached_at`) against bootstrap `cves` schema — will fail at runtime when NVD sync runs | Phase 7, 8 | High |

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-16 | Fresh schema start allowed | Dev/demo environment; maximum optimization freedom |
| 2026-03-16 | API response shapes frozen | Cannot change JSON key names; can change queries |
| 2026-03-16 | Migration 011 is the baseline | Don't redo dual-source KB-CVE work |
| 2026-03-16 | asyncpg parameterized syntax throughout | $1/$2 style; no string interpolation |
| 2026-03-16 | Route count is 25 (not 27) — research doc had stale data | api/ui.py has 25 @router.get() decorators: 24 TemplateResponse + 1 redirect |
| 2026-03-16 | Auditable template count is 24 (not 25) | 25 routes - 1 redirect = 24 auditable template routes |
| 2026-03-16 | base.html is only orphaned root-level template | Layout base extended by all pages; all 24 route-bound templates verified present |
| 2026-03-16 | P1.5: Two-query page load pattern is high-severity bad hack | /machines + /arg-patch-data merge requires periodic assessments to fix; no PostgreSQL caching for ARG data |
| 2026-03-16 | P1.5: patch_install_history_repository is only PostgreSQL write in patch domain | Not surfaced in UI; relevant for Phase 2 schema audit |
| 2026-03-17 | P8.7: AlertRepository created as missing dependency from prior plans | alert_repository.py was referenced in __init__.py but never created; Rule 3 blocking deviation |
| 2026-03-17 | P8.7: Consumer repo access via request.app.state pattern | Clean DI for routers; pg_client singleton for MCP servers |
| 2026-03-16 | P1.2: cve-database.html does NOT use DataTables — custom Bootstrap 5 pagination (pre-audit doc was wrong) | Actual template inspection revealed custom JS rendering, not jQuery DataTables |
| 2026-03-16 | P1.2: PG fast path for /cve/search only handles keyword+severity+min_score | vendor/product/date/source filters fall to service fallback — significant coverage gap |
| 2026-03-16 | P1.2: PDF export in cve-dashboard always uses slow Python analytics path (5 calls) | PG materialized views fast path not used for PDF export — P9.7 target |
| 2026-03-16 | P1.2: OS CVE breakdown in dashboard is scan-scoped, not catalogue-scoped | mv_vm_vulnerability_posture GROUP BY os_name; inconsistent with trend chart semantics |
| 2026-03-16 | P1.3: resource-inventory.html L2 is PostgreSQL (resource_inventory_postgres_store) not Cosmos | Cosmos stubs present but inactive; UI label "L2 (Cosmos DB)" is stale — confirms I-05 scope |
| 2026-03-16 | P1.3: vm-vulnerability.html actual endpoint is /api/vm-vulnerability-detail (not /api/cve/inventory/{vm_id}) | JS buildCveApiUrl() → /api/vm-vulnerability-detail with offset/limit server-side pagination |
| 2026-03-16 | P1.3: inventory-asst.html comm polling is global shared state — not session-scoped | GET /api/communications/inventory-assistant returns in-memory log; multi-user concurrency risk |
| 2026-03-16 | P1.3: inventory.html still uses LAW KQL — N+1 EOL queries per unique OS unchanged | checkEOLInPlace() POSTs /api/search/eol per OS row; no PG consolidation yet |
| 2026-03-16 | P1.4: eol-inventory.html data source is PostgreSQL (eol_records) — Cosmos fallback only when PG unavailable | EolInventory._is_postgres_available() guards all CRUD; stale Cosmos copy in UI is tech debt |
| 2026-03-16 | P1.4: eol-searches data source is in-memory orchestrator lists — no PG table for agent response history | eol_agent_responses not persisted; lost on restart; Phase 5 must design eol_agent_responses table |
| 2026-03-16 | P1.4: os-normalization-rules data is os_extraction_rules PG table with seeded DEFAULT_OS_EXTRACTION_RULES | Custom rules override defaults by ID; "Apply to Cosmos" button label is stale (should say DB) |
| 2026-03-16 | P1.6: routing-analytics.html data source confirmed as JSONL flat files — no PostgreSQL involvement | routing_analytics.py reads ./routing_logs/*.jsonl; no Phase 5 schema work needed for this view |
| 2026-03-16 | P1.6: CVE alert rules and history are in-memory only | cve_alert_rule_manager + cve_alert_history_manager use Python dicts; lost on restart; Phase 5 must design tables |
| 2026-03-16 | P1.6: cache.html server-side context is passed but stat widgets use JS fetch | Hybrid pattern confirmed; redundant server-side computation; no DB queries at all in cache view |
| 2026-03-16 | P1.6: sre.html and azure-mcp.html have zero DB queries on page load | Pure chat/streaming UIs; DB touched only by downstream tool calls |
| 2026-03-16 | P1.6: index.html "Database Load" metric is hardcoded at 35% | Not a real measurement; I-07 documented for Phase 3 bad-hack catalogue |
| 2026-03-16 | P2.2: kb_cve_edge is INACTIVE — kb_cve_edges (bootstrap) is canonical | PostgresKBCVEEdgeRepository exclusively writes to kb_cve_edges; msrc_kb_cve_sync_job.py writes raw SQL to kb_cve_edge but no repo class reads from it |
| 2026-03-16 | P2.2: Migration 011 cves CREATE is a silent no-op — bootstrap schema wins | pg_database.py creates cves first; IF NOT EXISTS in migration 011 silently skips; production uses bootstrap schema (10 CVSS columns, affected_products JSONB, search_vector) |
| 2026-03-16 | P2.2: arc_os_inventory is INACTIVE — no write path in current codebase | law_software_inventory_sync_job.py writes to arc_software_inventory only; arc_os_inventory has no corresponding sync job |
| 2026-03-16 | P2.2: patch_assessment_history is INACTIVE — no Python code reads or writes it | Table exists but no sync job populates it; no query path reads from it |
| 2026-03-16 | P2.2: cve_metadata_sync_job.py has latent column mismatch against bootstrap cves (I-09) | Uses migration 011 column names (severity, cvss_score, vendor, product, cached_at) — these don't exist in bootstrap cves schema; will fail at runtime |
| 2026-03-16 | P2.2: Migration 011 MVs ARE refreshed by cve_inference_job.py (corrects research note) | KBCVEInferenceJob._refresh_materialized_views() refreshes vm_vulnerability_overview, cve_dashboard_stats, os_cve_inventory_counts after each inference run |
| 2026-03-16 | P2.5: Total repository class count is 22 (not 20) | 16 canonical + 4 alias modules + 2 shim wrappers; plan estimated 14+6; PostgresInventoryVMRepository and 2 others not in plan estimate |
| 2026-03-16 | P2.5: VMCVEMatchRepository in vm_cve_match_repository.py is Cosmos DB, not PostgreSQL | Uses azure.cosmos SDK; legacy class superseded by PostgresVMCVEMatchRepository; documented as non-PostgreSQL |
| 2026-03-16 | P2.5: AlertPostgresRepository is broken at runtime — column mismatch confirmed (I-06) | rule_id/fired_at/severity/data columns don't exist in cve_alert_history; active path uses in-memory managers |
| 2026-03-16 | P2.5: InventoryPostgresRepository lacks staleness gate; PostgresInventoryVMRepository has one | Two classes write to inventory_vm_metadata; only PostgresInventoryVMRepository has WHERE last_synced_at < NOW() - 1 hour guard |
| 2026-03-16 | P2.5: 13 anti-patterns identified — 4 HIGH, 6 MEDIUM, 3 LOW severity | count_cves N+1, aggregate_inventory_os_counts dual-path, get_vm_matches empty-MV fallback, AlertPostgresRepository broken columns (all HIGH) |
| 2026-03-16 | P2.4: INVENTORY_USE_UNIFIED_VIEW default is "false" — not in ConfigManager | 5 separate callers each read os.getenv("INVENTORY_USE_UNIFIED_VIEW", "false") directly; no central config property |
| 2026-03-16 | P2.4: Only 1 regular view exists — v_unified_vm_inventory | Confirmed via search of pg_database.py and all 26 migration files; no other CREATE VIEW statements found |
| 2026-03-16 | P2.4: v_unified_vm_inventory output column count is 20 (bootstrap) | Migration 016/017 had 21 columns including vm_size; bootstrap dropped it; 20 is the authoritative count |
| 2026-03-16 | P2.3: mv_cve_dashboard_summary canonical DDL is migration 023 (sourced from cves, not vm_cve_match_rows) | Migration 023 rebuilt the MV to show full 8608+ CVE catalogue instead of scan-scoped 525 CVEs |
| 2026-03-16 | P2.3: mv_vm_cve_detail canonical DDL is migration 025 (LEFT JOIN) — INNER JOIN was root cause of 503 errors | 22,589 match rows but only ~8,600 cves rows; INNER JOIN produced empty view; migration 025 fixed with LEFT JOIN |
| 2026-03-16 | P2.3: I-03 root cause is circular: pg_database.py startup recreates mv_vm_cve_detail as superuser defeating runtime ownership | migrations 024/026 fix at migration time; startup DROP+CREATE reverts ownership; ALTER requires superuser — circular |
| 2026-03-16 | P2.3: mv_cve_dashboard_summary unique index on constant (1) is invalid for CONCURRENT refresh | Migration 023 used (1); migration 024 replaced with last_updated column index — actual row data required |
| 2026-03-16 | P2.3: Migration 011 MVs refreshed by KBCVEInferenceJob but no API reads them | Corrects research.md note; inference job has its own 3-MV refresh list; bootstrap 7-MV list in PostgresVMCVEMatchRepository is separate |
| 2026-03-16 | P2.1: pg_database.py bootstrap DDL is runtime-authoritative — migration file DDL is historical context only | IF NOT EXISTS semantics; bootstrap creates tables first so migration re-creates are no-ops |
| 2026-03-16 | P2.1: workflow_contexts has 3 indexes in migration 006 but only 1 in bootstrap DDL | idx_wfctx_workflow_created and idx_wfctx_expires are migration-only; bootstrap deployments only have idx_wfctx_session_agent |
| 2026-03-16 | P2.1: vm_cve_match_rows FK to cves absent in bootstrap | Migration 006 has CONSTRAINT fk_vmcvematch_cve to cves DEFERRABLE; bootstrap does not — no FK enforcement on bootstrap deployments |
| 2026-03-16 | P2.1: eol_confidence type inconsistency on resource_inventory | Bootstrap DDL: NUMERIC(5,2); migration 018 + _apply_column_migrations: TEXT — column type depends on deployment path |
| 2026-03-16 | P2.1: law_cache and arg_cache NOT in _REQUIRED_TABLES — not bootstrap-guaranteed | Actively used by LAWCachePostgresRepository and ARGCachePostgresRepository; will fail at runtime if tables absent |
| 2026-03-17 | P3.5: Phase 3 complete — 49 bad hacks catalogued with Priority Matrix | All Phase 1-2 findings cross-validated; Priority Matrix sorted CRITICAL→LOW ready for Phase 9-10 execution |
| 2026-03-17 | P3.4: os_name denormalized across 4 tables (HIGH priority) | resource_inventory, os_inventory_snapshots, patch_assessments, inventory_vm_metadata — no single source of truth; Phase 5 must design canonical vm_identity table |
| 2026-03-17 | P3.4: subscription_id denormalized across 8+ tables (HIGH priority) | No foreign key relationship; no subscription metadata table — Phase 5 must design subscriptions table with canonical subscription_id |
| 2026-03-17 | P3.4: vm_id/resource_id identity confusion (HIGH priority) | Inconsistent naming; no FK relationship; Phase 5 must standardize on resource_id |
| 2026-03-17 | P3.4: kb_cve_edges vs kb_cve_edge dual table conflict (I-01 catalogued) | Migration 011 table is inactive (no production reads); msrc_kb_cve_sync_job.py writes to inactive table — Phase 7 should drop kb_cve_edge |
| 2026-03-17 | P3.4: cves migration 011 CREATE is silent no-op (I-09 catalogued) | Bootstrap schema wins; cve_metadata_sync_job.py will fail at runtime — Phase 8 must fix column references |
| 2026-03-17 | P3.4: Cosmos stubs still present (I-05 catalogued) | Zero production callers, test-only imports — Phase 10 cleanup target |
| 2026-03-17 | P3.4: cache.html deprecated Cosmos endpoints (I-08 catalogued) | JavaScript calls /api/cache/cosmos/* endpoints that return 410 Gone — Phase 9 must remove dead UI code |
| 2026-03-17 | P3.4: INVENTORY_USE_UNIFIED_VIEW flag (I-02 catalogued) | 5 separate callers, feature flag never promoted — Phase 9 should promote unified view to default or remove flag |
| 2026-03-17 | P9.7: PG pool failure is fatal at startup — RuntimeError raised, no silent skip | All routers trust app.state repos exist; no defensive hasattr checks needed |
| 2026-03-17 | P9.7: CSV export uses dual-path (cve_repo fast-path + scanner fallback) | Backward compat preserved for mock mode/tests; repo path used in production |
| 2026-03-17 | P3.4: cve_dashboard dual-path (I-04 catalogued) | PDF export uses slow Python analytics path (200-500ms) instead of PG fast-path (50ms) — Phase 9 must wire PDF to PG MVs |
| 2026-03-17 | P3.4: Dual inventory write classes with conflicting staleness policies | InventoryPostgresRepository (no staleness check) vs PostgresInventoryVMRepository (1-hour guard) — Phase 8 must consolidate |
| 2026-03-17 | P4.1: /arg-patch-data should read from patch_assessments_cache + available_patches | 4 live ARG queries (5-30s) on every page load; sync job already populates same data every 15 min |
| 2026-03-17 | P4.1: arg_cache (generic JSONB) should be DEPRECATED | Zero active callers; typed tables provide superior query support |
| 2026-03-17 | P4.1: patch_assessment_history should be DROPPED | INACTIVE — no Python code reads or writes it |
| 2026-03-17 | P4.1: All ARG cache tables assigned MEDIUM_LIVED (1h) TTL | Per 04-CONTEXT decision; sync job cadence (15 min) always fresher than TTL |
| 2026-03-17 | P4.1: Manual refresh endpoint POST /api/cache/refresh/arg | Clears L1 + triggers ARGPatchSyncJob.run() + returns stats; no event-based triggers |
| 2026-03-17 | P4.3: kb_cve_edges (bootstrap, plural) is CANONICAL winner over kb_cve_edge (I-01 resolved) | Used by repository layer, all UI queries, mv_vm_cve_detail MV; richer schema with composite natural PK |
| 2026-03-17 | P4.3: MSRCKBCVESyncJob must be rewired to write to kb_cve_edges (Phase 8) | Currently writes to wrong table (kb_cve_edge); column mapping: kb_id → kb_number |
| 2026-03-17 | P4.3: KBCVEInferenceJob must be rewired to read from kb_cve_edges (Phase 8) | Currently reads from wrong table; column mapping: kb_id → kb_number |
| 2026-03-17 | P4.3: All MSRC cache data assigned LONG_LIVED (24h) TTL | Stable reference data; MSRC publishes on Patch Tuesday monthly; 24h TTL is appropriate |
| 2026-03-17 | P4.3: Manual refresh endpoint POST /api/cache/refresh/msrc with cascade | Clears L1 + triggers sync job → optionally cascades to inference job → MV refresh |
| 2026-03-17 | P4.2: arc_os_inventory SHOULD be DROPPED (INACTIVE, no write path) | Redundant with os_inventory_snapshots; no sync job; Phase 7 should DROP |
| 2026-03-17 | P4.2: law_cache generic JSONB cache SHOULD be DEPRECATED | No active callers found; typed tables (os_inventory_snapshots, arc_software_inventory) are the active path |
| 2026-03-17 | P4.2: inventory_software_cache/inventory_os_cache TTL: 4h to 1h (MEDIUM_LIVED alignment) | Current 14400s default doesn't align with any standard tier; Phase 8 must update to 3600s |
| 2026-03-17 | P4.2: os_inventory_snapshots TTL should standardize to MEDIUM_LIVED | Replace caller-controlled ttl_seconds with cache_config.MEDIUM_LIVED_TTL |
| 2026-03-17 | P4.2: cve_inventory.py LAW fallback should be replaced with arc_software_inventory query | Eliminate last uncached LAW KQL call site; Phase 8 must wire to PG |
| 2026-03-17 | P4.4: Complete TTL tier matrix assigns all 15 cache tables | 9 MEDIUM_LIVED (1h), 1 LONG_LIVED (24h), 2 DEPRECATED, 3 DROPPED, 1 metadata (N/A) |
| 2026-03-17 | P4.4: Three staleness enforcement patterns (A/B/C) | Pattern A: expires_at for blob caches; Pattern B: cached_at+TTL for sync tables; Pattern C: metadata-controlled for snapshots |
| 2026-03-17 | P4.4: cache_ttl_config admin table designed with seed data | source_name PK for arg/law/msrc; UI-configurable TTL overrides without code changes |
| 2026-03-17 | P4.4: TTL resolution precedence: DB row > env var > CacheTTLProfile default | resolve_ttl() async function reads cache_ttl_config first, falls back to cache_config.py |
| 2026-03-17 | P4.4: kb_cve_edges needs cached_at column added in Phase 7 | Only LONG_LIVED table; created_at/updated_at exist but no cached_at for freshness tracking |
| 2026-03-17 | P4.5: Two-mechanism invalidation strategy (TTL + manual refresh, no event-based) | Predictable and debuggable; 15-min sync cadence provides automatic freshness; manual button handles urgent needs |
| 2026-03-17 | P4.5: MSRC refresh MUST always cascade to inference job | New KB-CVE edges directly change vulnerability detection; skipping cascade leaves stale cve_vm_detections |
| 2026-03-17 | P4.5: ARG/LAW refresh cascade to inference is optional | Fresh patches/inventory don't always require full inference re-run |
| 2026-03-17 | P4.5: Freshness thresholds: fresh 0-74%, expiring 75-99%, stale >=100%, empty 0 rows | Clear visual progression from green through yellow to red in cache.html |
| 2026-03-17 | P4.5: 6 admin API endpoints specified for Phase 8 implementation | 3 refresh (POST /api/cache/refresh/{arg,law,msrc}), 1 status (GET /api/cache/status), 2 TTL config (GET/PUT /api/cache/config/ttl) |
| 2026-03-17 | P4.6: Phase 4 complete — CACHE-GAPS-SUMMARY.md consolidates all findings | 15 tables audited, 11 active post-Phase 7, 3 to DROP, 2 to DEPRECATE, 1 new (cache_ttl_config), all CACHE-01–04 requirements met |
| 2026-03-17 | P5.5: cve_alert_rules REDESIGNED — explicit filter columns replace JSONB config blob | rule_id UUID PK, severity_threshold, cvss_min_score, vendor_filter, product_filter; matches in-memory AlertRule structure |
| 2026-03-17 | P5.5: cve_alert_history REDESIGNED — per-CVE firing model (22->8 columns) | One row per rule+CVE firing; FK to cve_alert_rules(rule_id) + cves(cve_id) CASCADE; UNIQUE (rule_id, cve_id) prevents duplicates |
| 2026-03-17 | P5.5: alert_config and notification_history retained as ACTIVE (unchanged) | No redesign needed; Phase 7 keeps existing DDL |
| 2026-03-17 | P5.5: I-06 resolution path documented across Phase 7/8 | Phase 7: DROP+CREATE new DDL; Phase 8: rewrite AlertPostgresRepository + replace in-memory managers |
| 2026-03-17 | P5.1: resource_id uses TEXT not VARCHAR(500) for vms PK | PostgreSQL stores TEXT/VARCHAR identically; TEXT eliminates truncation risk for long ARM paths |
| 2026-03-17 | P5.1: vm_type included in vms table (12th column) | Stable identity attribute needed by mv_vm_vulnerability_posture; avoids JOIN to deprecated inventory_vm_metadata |
| 2026-03-17 | P5.1: subscription FK uses ON DELETE RESTRICT (not CASCADE) | Prevents catastrophic cascade-delete of entire VM spine when a subscription is removed |
| 2026-03-17 | P5.1: inventory_vm_metadata DEPRECATED — replaced by vms table | 6 consumers mapped to Phase 7/8/9 migration paths; Phase 10 DROP candidate |
| 2026-03-17 | P5.1: patch_assessments_cache.resource_id needs VARCHAR(512)->TEXT alignment | Only child table with type mismatch; metadata-only ALTER in Phase 7 |
| 2026-03-17 | P5.1: 6 child tables FK to vms.resource_id with CASCADE DELETE | vm_cve_match_rows, patch_assessments_cache, available_patches, os_inventory_snapshots, cve_vm_detections, arc_software_inventory |
| 2026-03-17 | P5.2: cves table retains 21-column bootstrap schema (ACTIVE, no changes) | Migration 011 cves CREATE is silent no-op; bootstrap DDL is authoritative; I-09 documents column mapping |
| 2026-03-17 | P5.2: kb_cve_edges gets cached_at TIMESTAMPTZ for LONG_LIVED TTL tracking | Required by P4.4 Pattern B staleness enforcement; Phase 7 ALTER TABLE migration |
| 2026-03-17 | P5.2: vm_cve_match_rows gets 2 new FKs (vm_id->vms, cve_id->cves) | Fixes P2.1 bootstrap gap; DEFERRABLE on cve FK for batch scan inserts |
| 2026-03-17 | P5.2: cve_vm_detections gets 2 new FKs (resource_id->vms, cve_id->cves) | Per strict FK policy; CASCADE DELETE removes detections when VM/CVE deleted |
| 2026-03-17 | P5.2: I-09 resolved with 5-column mapping (migration 011 -> canonical) | severity->cvss_v3_severity, cvss_score->cvss_v3_score, vendor/product->affected_products JSONB, cached_at->synced_at |
| 2026-03-17 | P5.2: I-01 confirmed — kb_cve_edges canonical, kb_cve_edge DROP in Phase 7 | Data migration SQL documented; Phase 8 rewiring for MSRCKBCVESyncJob and KBCVEInferenceJob |

| 2026-03-17 | P5.6: mv_vm_vulnerability_posture source changed from inventory_vm_metadata to vms | vms is canonical VM table (P5.1); eol_status/eol_date now via LEFT JOIN eol_records |
| 2026-03-17 | P5.6: 3 migration-011 MVs on DROP list (vm_vulnerability_overview, cve_dashboard_stats, os_cve_inventory_counts) | No active callers; superseded by bootstrap MVs; Phase 7 must verify with grep before DROP |
| 2026-03-17 | P5.6: I-03 ownership fix -- idempotent bootstrap (check pg_matviews before CREATE) | Option 3 recommended: preserves migration ownership, no hardcoded roles, skip CREATE if MV exists |
| 2026-03-17 | P5.6: v_unified_vm_inventory DEPRECATED -- Phase 7 keep, Phase 9 rewire, Phase 10 DROP | Replaced by vms table + domain JOINs; INVENTORY_USE_UNIFIED_VIEW flag removed in Phase 9 |
| 2026-03-17 | P5.6: eol_status column type change (TEXT to BOOLEAN via e.is_eol) in mv_vm_vulnerability_posture | Phase 8/9 must verify API response shape; CASE map needed if API returns string |
| 2026-03-17 | P5.6: KBCVEInferenceJob refresh list must be updated in Phase 8 | Currently refreshes 3 MVs being dropped; must remove or rewire to bootstrap MV names |

| 2026-03-17 | P5.3: resource_inventory has NO FK to vms -- stores all Azure resource types | Mixed-type table makes FK impractical; Phase 8 queries use explicit JOIN with WHERE type filter |
| 2026-03-17 | P5.3: os_inventory_snapshots retains os_name alongside vms.os_name | Raw LAW-reported vs normalized canonical; both needed for raw historical data vs query-time filtering |
| 2026-03-17 | P5.3: patch_assessments_cache.resource_id VARCHAR(512)->TEXT alignment | Metadata-only ALTER in Phase 7; ensures FK compatibility with vms.resource_id TEXT |
| 2026-03-17 | P5.3: available_patches FK target changed from patch_assessments_cache to vms directly | Cleaner relationship; avoids transitive dependency; patches are associated with VMs not cache entries |
| 2026-03-17 | P5.3: arc_software_inventory gets new FK fk_arcswinv_vm to vms ON DELETE CASCADE | LAW software inventory linked to VM spine for lifecycle cleanup |
| 2026-03-17 | P5.3: 2 tables DROP (arc_os_inventory, patch_assessment_history) | Both confirmed INACTIVE in P2.2; safe to drop in Phase 7 |
| 2026-03-17 | P5.3: 4 tables DEPRECATE (inventory_vm_metadata, arg_cache, law_cache, patch_assessments) | All superseded by typed tables; kept Phases 7-9, dropped Phase 10 |
| 2026-03-17 | P5.4: eol_records documented as ACTIVE reference table -- no structural changes | software_key PK; reference table pattern; no FK to vms; logical many-to-many via computed JOIN |
| 2026-03-17 | P5.4: eol_agent_responses NEW table with 7 columns for eol-searches.html persistence | response_id UUID PK, session_id, user_query, agent_response, sources JSONB, timestamp, response_time_ms |
| 2026-03-17 | P5.4: BH-005 bulk EOL lookup JOIN pattern documented | LEFT JOIN vms to eol_records via LOWER(os_name) fuzzy matching; replaces N+1 HTTP calls with single SQL query |
| 2026-03-17 | P5.4: os_extraction_rules and normalization_failures ACTIVE -- unchanged | Seeded with DEFAULT_OS_EXTRACTION_RULES; normalization pipeline supporting tables |

| 2026-03-17 | P5.7: UNIFIED-SCHEMA-SPEC.md is the single authoritative Phase 7 migration blueprint | Consolidates all P5.1-P5.6 outputs; migrations 027-032; complete DDL + ERD + bootstrap updates + forward refs |
| 2026-03-17 | P5.7: Migrations ordered by dependency (027 drops, 028 spine, 029 CVE, 030 inventory+EOL, 031 alerting, 032 MV) | Ensures parent tables exist before FK constraints are added; orphan cleanup before every ADD CONSTRAINT |
| 2026-03-17 | P5.7: 8 tables added to _REQUIRED_TABLES (4 NEW + 4 promoted from migration 011) | subscriptions, vms, eol_agent_responses, cache_ttl_config, plus patch_assessments_cache, available_patches, arc_software_inventory, cve_vm_detections |
| 2026-03-17 | P5.7: Phase 5 complete -- all 7 plans done, ready for Phase 6 | UNIFIED-SCHEMA-SPEC.md ready for direct Phase 7 execution; Phase 6 index design can begin |

| 2026-03-17 | P6.1: Both idx_vms_os_name_lower and idx_eol_software_key_lower required for BH-005 fuzzy JOIN | Without both expression indexes, PostgreSQL falls back to nested-loop with sequential scan on inner table |
| 2026-03-17 | P6.1: search_vector + trigger + idx_cves_fts are all bootstrap gaps for Phase 7 | Migration 006 only; bootstrap deployments lack FTS capability entirely |
| 2026-03-17 | P6.1: Always prefer search_vector @@ to_tsquery() over ILIKE for user-facing CVE search | GIN index enables O(1) lookup per term; ILIKE forces sequential scan on 8,600+ rows |

| 2026-03-17 | P6.2: GAP-01 resolved with standalone idx_cves_severity retained alongside GAP-02 composite | Equality-only severity filter more efficient with single-column index; composite idx_cves_severity_published adds unnecessary published_at overhead for severity-only queries |
| 2026-03-17 | P6.2: GAP-02 resolved with composite (cvss_v3_severity, published_at) equality-first ordering | Equality prefix on severity allows B-tree descent, then range scan on published_at; reverse order would force full date range scan before severity filter |
| 2026-03-17 | P6.2: GAP-06 resolved with idx_wfctx_expires partial index added to bootstrap DDL | Bootstrap-migration parity restored; migration 006 index now also in bootstrap + migration 032 |
| 2026-03-17 | P6.2: GAP-05 mitigated with idx_scans_completed partial index (WHERE status = 'completed') | O(1) access for latest_completed_scan_id() function; true dynamic partial index impossible in PostgreSQL |
| 2026-03-17 | P6.2: 11 new filter indexes designed (2 GAP resolutions, 4 composites, 5 partials) | Alerting indexes in migration 031; optimization indexes in migration 032; all added to bootstrap DDL |
| 2026-03-17 | P6.2: idx_alert_rules_enabled marked RETAIN-BUT-REVIEW for Phase 10 | Partially subsumed by partial idx_alert_rules_active; Phase 10 should verify if disabled-rule queries exist |

| 2026-03-17 | P6.4: GAP-05 resolved with Option A -- rely on existing idx_vmcvematch_scan_severity composite index | No partial index lifecycle needed at demo scale (~22,589 rows); Phase 10 revisits if >100k rows or >5s MV refresh |
| 2026-03-17 | P6.4: BH-001 fix -- PDF export uses same MV read queries as page load | Eliminates 5-call Python analytics path; same data as rendered page; Phase 8 implementation |
| 2026-03-17 | P6.4: BH-004 fix -- single mv_vm_vulnerability_posture GROUP BY os_name | Replaces 3-query dual-path with O(N^2) JSONB cross-join fallback; Phase 8 implementation |
| 2026-03-17 | P6.4: MV refresh order defined as 3 tiers (independent, scan-scoped, detail) | Tier 1: dashboard/trending/top. Tier 2: exposure/posture. Tier 3: vm_cve_detail. Parallel within tiers. |

| 2026-03-17 | P6.5: Only cve-database.html uses keyset pagination (8,608+ growing CVEs) | All other paginated views use offset/limit; 15 views need no pagination |
| 2026-03-17 | P6.5: Cursor token format is base64url(JSON) with compound key (published_at, cve_id) | Compound key guarantees uniqueness since multiple CVEs can share same published_at |
| 2026-03-17 | P6.5: COUNT(*) queries cached in L1 for 60s for both keyset and offset/limit views | Avoids per-page re-counting; keyed by filter combination hash |
| 2026-03-17 | P6.5: BH-009 server-side sorting uses ALLOWED_SORT_COLUMNS whitelist (10 columns) | Maps user-facing column names to DB column names; rejects unknown columns with 400 |

| 2026-03-17 | P6.3: GAP-03/04 resolved with single composite idx_edges_cve_source ON kb_cve_edges (cve_id, source) | No standalone idx_edges_source created; composite covers dominant (cve_id, source) pattern; standalone source-only queries are rare |
| 2026-03-17 | P6.3: R-01 RETAIN BOTH indexes on resource_inventory -- deferred to Phase 10 | v_unified_vm_inventory still in transition; partial index preferred by queries with IS NOT NULL; Phase 10 drops full index after view dropped |
| 2026-03-17 | P6.3: R-02 DROP idx_edges_kb -- fully redundant with PK prefix on kb_cve_edges | PK (kb_number, cve_id, source) leading key serves WHERE kb_number = $1; saves write amplification on UPSERT-heavy table |
| 2026-03-17 | P6.3: 2 new covering indexes designed for high-traffic JOIN queries | idx_cves_severity_covering INCLUDE (cve_id, cvss_v3_score, published_at); idx_alerthistory_rule_covering INCLUDE (cve_id, severity, fired_at) |
| 2026-03-17 | P6.3: All 11 FK child columns verified to have supporting indexes | No new FK indexes needed; covering indexes on vm_cve_match_rows serve double duty as FK support |
| 2026-03-17 | P6.3: idx_vms_subscription_covering deferred -- 100-500 VMs too small to benefit | Write amplification on upsert-heavy vms table outweighs index-only scan benefit at current scale |

| 2026-03-17 | P7.1: cached_at column added to kb_cve_edges in migration 027 (moved from 029) | Keeps kb_cve_edge data migration self-contained; INSERT references cached_at in both source and destination (07-RESEARCH Risk 3 resolution) |
| 2026-03-17 | P7.1: WHERE NOT EXISTS used for kb_cve_edge data migration (not ON CONFLICT) | PK is 3-column composite (kb_number, cve_id, source); WHERE NOT EXISTS is more explicit for multi-column duplicate check |
| 2026-03-17 | P7.1: Migration 029 should skip ALTER TABLE kb_cve_edges ADD COLUMN cached_at | Already added in migration 027; IF NOT EXISTS makes it safe but redundant |

| 2026-03-17 | P10.4: legacy/tool_router.py and legacy/tool_embedder.py retained — active callers | mcp_orchestrator.py and tool_retriever.py import ToolEmbedder; non-trivial refactor needed for deletion |
| 2026-03-17 | P10.4: cve_in_memory_repository.py retained — required for mock mode | main.py creates CVEInMemoryRepository() when USE_MOCK_DATA=true; deferred to Phase 11 |

---

## File Index

| File | Purpose |
|------|---------|
| `.planning/ROADMAP.md` | Phase/plan roadmap |
| `.planning/STATE.md` | This file — current status, decisions, blockers |
| `.planning/PROJECT.md` | Project context and requirements |
| `.planning/REQUIREMENTS.md` | Discovery-phase requirements checklist |
| `.planning/phases/01-ui-view-audit/views/VIEW-REGISTRY.md` | Master route→template map (P1.1 output) |
| `.planning/phases/01-ui-view-audit/views/cve-dashboard.html.md` | CVE analytics dashboard view audit (P1.2 output) |
| `.planning/phases/01-ui-view-audit/views/cve-database.html.md` | CVE catalogue browser view audit (P1.2 output) |
| `.planning/phases/01-ui-view-audit/views/cve-detail.html.md` | CVE detail + affected VMs + patches view audit (P1.2 output) |
| `.planning/phases/01-ui-view-audit/views/patch-management.html.md` | Patch domain view audit (P1.5 output) |
| `.planning/phases/01-ui-view-audit/views/inventory.html.md` | OS/software inventory view audit (P1.3 output) |
| `.planning/phases/01-ui-view-audit/views/resource-inventory.html.md` | Azure resource inventory view audit (P1.3 output) |
| `.planning/phases/01-ui-view-audit/views/vm-vulnerability.html.md` | VM vulnerability dual-mode view audit (P1.3 output) |
| `.planning/phases/01-ui-view-audit/views/inventory-asst.html.md` | Inventory AI assistant view audit (P1.3 output) |
| `.planning/phases/01-ui-view-audit/views/admin-views.md` | Admin/alert/observability view audit — 7 views (P1.6 output) |
| `.planning/phases/01-ui-view-audit/views/eol-views.md` | EOL domain view audit — 5 views (P1.4 output) |
| `.planning/phases/01-ui-view-audit/views/sre-agent-views.md` | SRE/agent view audit — 4 views (P1.6 output) |
| `.planning/ui-discovery/` | Pre-audited views: cve-dashboard, cve-database, inventory, patch-management, vm-vulnerability |
| `.planning/schema/` | Schema audit and design artifacts |
| `.planning/phases/02-schema-repository-audit/schema/BASE-TABLES.md` | All 29 _REQUIRED_TABLES with exact DDL, 5 dropped/non-guaranteed tables, schema evolution notes (cve_scans, vm_cve_matches), I-06 column mismatch callout, 2 Mermaid ERDs (P2.1 output) |
| `.planning/phases/02-schema-repository-audit/schema/VIEWS.md` | Regular views reference — v_unified_vm_inventory DDL, CTEs, output columns, feature flag, I-02 (P2.4 output) |
| `.planning/phases/02-schema-repository-audit/schema/MATERIALIZED-VIEWS.md` | All 10 MVs documented — 7 bootstrap + 3 migration 011; DDL, refresh mechanism, I-03 ownership, dual-system conflict, Mermaid diagram (P2.3 output) |
| `.planning/phases/02-schema-repository-audit/schema/REPOSITORY-MAP.md` | All 22 repository classes mapped — methods, SQL patterns, tables, anti-patterns, cache layer, alias delegation (P2.5 output) |
| `.planning/phases/02-schema-repository-audit/schema/INDEX-AUDIT.md` | 71 indexes catalogued (54 base-table + 17 MV), 6 gaps (GAP-01–06), 2 redundancy findings (R-01/R-02), Phase 6 forward references (P2.6 output) |
| `.planning/phases/02-schema-repository-audit/schema/UI-TO-SCHEMA-MAP.md` | All 24 UI views traced: UI → API endpoint → router → repository → table/view/MV; Schema Coverage Analysis; Phase 5 Design Inputs with 7 critical gaps (P2.7 output) |
| `.planning/phases/03-bad-hack-catalogue/schema/BAD-HACKS.md` | Bad-hack anti-pattern catalogue: 49 entries across 8 categories, Priority Matrix, Known Issues Coverage, cross-validated (P3.1–P3.5 complete) |
| `.planning/phases/04-cache-layer-specification/cache/LAW-CACHE-SPEC.md` | LAW cache audit: 3 KQL call sites, 7 cache tables, gap analysis, MEDIUM_LIVED TTL alignment, refresh triggers (P4.2 output) |
| `.planning/phases/04-cache-layer-specification/cache/ARG-CACHE-SPEC.md` | ARG cache specification: 5 call sites, 5 cache tables, gap analysis, MEDIUM_LIVED 1h TTL, refresh triggers, Phase 7 forward refs (P4.1 output) |
| `.planning/phases/04-cache-layer-specification/cache/MSRC-CACHE-SPEC.md` | MSRC cache specification: 5 call sites, I-01 dual table conflict resolved, 5 storage mechanisms, 3 cache gaps, LONG_LIVED 24h TTL, refresh triggers, Phase 7 forward refs (P4.3 output) |
| `.planning/phases/04-cache-layer-specification/cache/TTL-TIERS-SPEC.md` | TTL tier assignment: all 15 cache tables assigned to tiers, 3 staleness patterns, cache_ttl_config admin table DDL, resolve_ttl() precedence chain, Phase 7/8 forward refs (P4.4 output) |
| `.planning/phases/04-cache-layer-specification/cache/INVALIDATION-SPEC.md` | Cache invalidation strategy: 2 mechanisms (TTL + manual), 3 TTL enforcement patterns, 6 admin API endpoints, 3 cascade chains, cache.html integration plan, Phase 8-9 forward refs (P4.5 output) |
| `.planning/phases/04-cache-layer-specification/cache/CACHE-GAPS-SUMMARY.md` | Consolidated Phase 7 migration blueprint: 15 tables audited, 11 active, 2 deprecated, 3 dropped, 1 new (cache_ttl_config), DDL, bootstrap changes, TTL adjustments, 6 admin API endpoints, requirements coverage (P4.6 output) |
| `.planning/phases/05-unified-schema-design/schema/ALERTING-TABLES.md` | Alerting domain: 4 tables (cve_alert_rules REDESIGNED, cve_alert_history REDESIGNED, alert_config ACTIVE, notification_history ACTIVE), I-06 resolution, ERD, query patterns (P5.5 output) |
| `.planning/phases/05-unified-schema-design/schema/VM-IDENTITY-SPINE.md` | VM identity spine: vms (12 columns, TEXT PK, 8 indexes) + subscriptions (7 columns, UUID PK, 3 indexes) + 6 FK relationships + inventory_vm_metadata deprecation + ERD (P5.1 output) |
| `.planning/phases/05-unified-schema-design/schema/CVE-TABLES.md` | CVE domain: 5 tables (cves ACTIVE, kb_cve_edges MODIFIED +cached_at, vm_cve_match_rows MODIFIED +2 FKs, cve_vm_detections MODIFIED +2 FKs, cve_scans ACTIVE) + latest_completed_scan_id() + I-09/I-01 resolution + ERD (P5.2 output) |
| `.planning/phases/05-unified-schema-design/schema/INVENTORY-TABLES.md` | Inventory domain: 5 active/modified tables (resource_inventory, os_inventory_snapshots, patch_assessments_cache, available_patches, arc_software_inventory), 5 state/cache tables, 2 DROP, 4 DEPRECATE, ERD (P5.3 output) |
| `.planning/phases/05-unified-schema-design/schema/MATERIALIZED-VIEWS-TARGET.md` | MV target design: 7 retained MVs, updated mv_vm_vulnerability_posture DDL, 3 DROP list, refresh schedule, manual API, I-03 fix, v_unified_vm_inventory deprecation, dependency diagram (P5.6 output) |
| `.planning/phases/05-unified-schema-design/schema/EOL-TABLES.md` | EOL domain: 4 tables (eol_records ACTIVE, eol_agent_responses NEW 7-column, os_extraction_rules ACTIVE, normalization_failures ACTIVE) + BH-005 bulk lookup pattern + ERD (P5.4 output) |
| `.planning/phases/05-unified-schema-design/schema/UNIFIED-SCHEMA-SPEC.md` | Authoritative target schema DDL: 39+ tables, migrations 027-032, full Mermaid ERD, bootstrap _REQUIRED_TABLES/RELATIONS updates, Phase 6-10 forward references (P5.7 output) |
| `.planning/phases/06-index-query-optimization-design/queries/AGGREGATION-STRATEGY.md` | Aggregation strategy: MV-vs-CTE-vs-Live decision framework, 7 MV read queries, 8 MV refresh index deps, GAP-05 resolution (Option A), BH-001/BH-004 fix designs, 4 CTE patterns (P6.4 output) |
| `.planning/phases/06-index-query-optimization-design/queries/PAGINATION-STRATEGY.md` | Pagination strategy: 1 keyset (cve-database), 8 offset/limit, 15 none; cursor token format, SQL patterns, BH-009 sorting fix, 11 pagination indexes (P6.5 output) |
| `.planning/phases/06-index-query-optimization-design/queries/FILTER-INDEX-STRATEGY.md` | Filter index strategy: 11 new indexes (2 GAP resolutions + 4 composites + 5 partials), GAP-01/02/06 resolved, GAP-05 mitigated, 15 existing indexes validated, 25-entry complete registry (P6.2 output) |
| `.planning/phases/06-index-query-optimization-design/queries/JOIN-INDEX-STRATEGY.md` | Cross-table JOIN index strategy: GAP-03/04 resolved (idx_edges_cve_source), 2 new covering indexes, 11 FK indexes verified, R-01/R-02 redundancy resolved, BH-005 expression indexes cross-referenced, 19-entry registry (P6.3 output) |
| `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-CVE-DOMAIN.md` | Target SQL for 8 CVE views: 16 queries, BH-001/002/003/004/006/007/008 fixes, MV-first read path, keyset pagination for search (P6.6 output) |
| `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-INVENTORY-DOMAIN.md` | Target SQL for 9 Inventory/EOL views: 13 queries, BH-005/009/010 fixes, CTE bulk JOIN, server-side sort (P6.6 output) |
| `.planning/phases/06-index-query-optimization-design/queries/TARGET-SQL-ADMIN-DOMAIN.md` | Target SQL for 7 Admin views: 2 DB-query + 5 no-DB, cache freshness queries, I-07 fix, 24-view coverage summary (P6.6 output) |

---

## Next Actions

1. **P8.1 COMPLETE** -- asyncpg pool singleton + repositories package init
2. **P8.3 COMPLETE** -- InventoryRepository with BH-005 bulk EOL lookup
3. **P8.4 COMPLETE** -- PatchRepository (BH-010 fix) + AlertRepository (I-06 resolution)
4. **P8.5 COMPLETE** -- EOLRepository with BH-009 sort fix
5. **Next:** P8.2 -- CVE repository (uses TARGET-SQL-CVE-DOMAIN.md)
6. Phase 8 uses TARGET-SQL-*.md files as the definitive query reference for repository rewrites
7. Phase 8 must implement pagination patterns from P6.5: keyset for cve-database, offset/limit for 8 other views
8. Phase 8 rewiring: cve_metadata_sync_job.py (I-09), MSRCKBCVESyncJob, KBCVEInferenceJob
9. Phase 9 must remove `INVENTORY_USE_UNIFIED_VIEW` feature flag (I-02)
10. Phase 9 must rewire 5+ callers of cve_alert_rule_manager.py and cve_alert_history_manager.py to use AlertRepository

---

| 2026-03-16 | P2.7: visualizations.html exact API calls require JS file inspection | visualizations.js static file not read; documented with 'likely' sourcing from dashboard MVs |
| 2026-03-16 | P2.7: arg_cache table not wired to /arg-patch-data endpoint | ARGCachePostgresRepository and arg_cache table exist (migration 011) but get_arg_patch_data() runs live ARG queries; documented as Phase 5 Gap 6 |
| 2026-03-16 | P2.7: Schema Coverage: 7 fully covered, 8 partial, 5 in-memory-only, 1 flat-file, 3 no-DB-on-load | Complete picture of all 24 views vs schema coverage |
| 2026-03-16 | P3.2: No nested comprehensions or double loops in codebase | Modern dict-based lookup patterns instead; 7 in-memory join entries documented (0 CRITICAL, 3 HIGH, 3 MEDIUM, 1 LOW) |
| 2026-03-16 | P3.2: aggregate_inventory_os_counts() is most complex in-memory pattern | 3-query dual-path with O(N²) JSONB cross-join fallback; 30 profiles × 10k CVEs = 300k row evaluations when MV stale |
| 2026-03-16 | P3.2: Dict-based joins are common in-memory pattern | 3 of 7 entries use dict comprehension to build lookup tables then loop with .get(); easier to read than nested loops but same perf |

| 2026-03-17 | P6.6: All 24 UI views have target SQL across 3 domain files (CVE, Inventory/EOL, Admin) | 35+ queries documented with asyncpg params, index usage, pagination, BH-001 through BH-010 fixes, Phase 8/9 forward refs |
| 2026-03-17 | P6.3 gap closure: JOIN-INDEX-STRATEGY.md restored (was 0 bytes) | File write failed during original P6.3 execution; all decisions were already recorded in STATE.md and 06-03-SUMMARY.md; gap closure re-executed the write |

| 2026-03-17 | P7.2: Migration 028 created — subscriptions + vms tables (VM identity spine) | Exact DDL from UNIFIED-SCHEMA-SPEC.md and VM-IDENTITY-SPINE.md; subscriptions 7 cols + 2 idx, vms 12 cols + 7 idx, FK ON DELETE RESTRICT; migrations/versions/ directory created |

| 2026-03-17 | P7.3: Migration 029 created — CVE table FK additions + orphan cleanup | 4 FK constraints (fk_vmcvematch_vm, fk_vmcvematch_cve DEFERRABLE, fk_cvevmdet_vm, fk_cvevmdet_cve); orphan cleanup DELETEs precede each FK; DO blocks for idempotency; idx_cvevmdet_resource_cve unique index |

| 2026-03-17 | P7.4: Migration 030 created — inventory FK additions + EOL + cache tables | Type alignment VARCHAR(512)->TEXT; 4 FK constraints (fk_patchcache_vm, fk_availpatches_vm, fk_osinvsnap_vm, fk_arcswinv_vm); eol_agent_responses (7 cols, UUID PK); cache_ttl_config (5 cols, 3 seed rows); all orphan cleanup + DO block idempotency |

| 2026-03-17 | P7.5: Migration 031 created — alerting tables DROP + CREATE with 9 indexes | DROP cve_alert_history (child) then cve_alert_rules (parent); recreated cve_alert_rules (9 explicit cols, UUID PK) + cve_alert_history (8 cols, per-CVE firing model); 5 base + 4 Phase 6 optimization indexes; FKs to cve_alert_rules and cves with CASCADE DELETE; I-06 schema foundation complete |

| 2026-03-17 | P7.6: Migration 032 created — MV re-creation + 13 optimization indexes + FTS | mv_vm_vulnerability_posture recreated with vms source + eol_records LEFT JOIN; FTS trigger function + trigger + GIN index (bootstrap gap); 13 optimization indexes (2 expression, 3 severity, 2 composite, 3 partial, 2 JOIN/covering); DROP idx_edges_kb (R-02); 4 MV indexes; I-03 OWNER TO CURRENT_ROLE fix |

| 2026-03-17 | P7.7: pg_database.py created with full target schema bootstrap DDL | 39 _REQUIRED_TABLES (29 existing + 8 new + 2 deprecated caches), 14 _REQUIRED_RELATIONS, I-03 MV fix, all Phase 6 indexes, FTS infrastructure; Phase 7 complete |

| 2026-03-17 | P8.1: PostgresClient receives DSN externally (no config.py dependency) | Enables independent testing; 3-tier DSN resolution: param > DATABASE_URL > PG* env vars |
| 2026-03-17 | P8.1: repositories/__init__.py forward-declares __all__ without imports | Prevents ImportError before P8.2-P8.6 create actual repo files |

| 2026-03-17 | P8.3: InventoryRepository created with 7 methods covering queries 9a-9c, 10a-10b | BH-005 eliminated (CTE + LEFT JOIN); BH-013/BH-015 inherently fixed via vms table |
| 2026-03-17 | P8.3: upsert_vm uses ON CONFLICT (never DELETE + INSERT) | Preserves CASCADE FK integrity with 6 child tables |

| 2026-03-17 | P8.5: EOLRepository created with 8 methods covering queries 12a-16a | BH-009 eliminated (server-side ORDER BY with ALLOWED_SORT_COLUMNS whitelist); eol_agent_responses write path implemented |
| 2026-03-17 | P8.5: Sort whitelist has 9 entries mapping user-facing names to DB columns | Prevents SQL injection; invalid sort_column defaults to "updated_at", invalid direction defaults to "DESC" |

| 2026-03-17 | P8.4: PatchRepository created with 5 methods covering queries 11a-11b, 4c | BH-010 eliminated: single LEFT JOIN + correlated subquery replaces /machines + /arg-patch-data two-query pattern |
| 2026-03-17 | P8.4: AlertRepository created with 9 methods covering queries 5a-5b, 6a, 8a-8b + full CRUD | I-06 resolved: replaces cve_alert_rule_manager.py and cve_alert_history_manager.py (Cosmos/in-memory) |
| 2026-03-17 | P8.4: Per-CVE firing model uses ON CONFLICT (rule_id, cve_id) DO NOTHING | Prevents duplicate alert firings; matches redesigned cve_alert_history schema from P5.5 |
| 2026-03-17 | P8.4: update_rule uses COALESCE for partial updates | Only non-NULL kwargs modify the row; enables single-field updates without overwriting other fields |

| 2026-03-17 | P8.2: CVERepository created with 16+ methods covering all Phase 6 CVE-domain queries | BH-001/002/003/004/006/007/008 eliminated; MV-first reads + full-filter search + 3-tier refresh |
| 2026-03-17 | P8.2: 3-tier MV refresh: tier1 (dashboard), tier2 (scan-scoped), tier3 (detail) | Per-MV error handling; failed MVs don't block remaining refreshes; returns refreshed/failed/duration_ms |
| 2026-03-17 | P8.2: UPSERT_CVE aligned to bootstrap cves schema column names | Uses last_modified_at/vector_string_v3/exploitability_score (not migration 011 names); 18 parameters |

| 2026-03-17 | P9.1: Omitted scan_id filter from QUERY_CVE_AFFECTED_VMS | MV already contains only latest scan data; filter would require latest_completed_scan_id() function call |
| 2026-03-17 | P9.1: Used offset/limit pagination for all new queries | Per 09-CONTEXT pagination decision; consistent with existing repo pattern |

| 2026-03-17 | P9.3: Renamed search_cves body param from 'request' to 'search_request' | Avoids naming collision with FastAPI Request dependency injection parameter |
| 2026-03-17 | P9.3: Removed _build_inventory_cached_filters() and 3 unused model imports | Dead code after stats endpoint rewrite; CVESearchResponse/CVEDetailResponse/UnifiedCVE no longer used |
| 2026-03-17 | P9.3: CVE detail endpoint returns 404 HTTPException instead of success=False | Cleaner API contract; 404 is more RESTful for missing resources |
| 2026-03-17 | P9.4: Keep _merge_azure_vm_os_inventory for raw endpoint | get_raw_os_inventory still calls it; only remove functions with zero callers |
| 2026-03-17 | P9.4: Keep get_inventory() on orchestrator path with TODO(P10) | Live Azure Log Analytics software data has no PG sync job yet |

| 2026-03-17 | P9.2: Kept _calculate_risk_level as fallback when MV risk_level is NULL | Defensive fallback is cheap; MV may not always have risk_level populated |
| 2026-03-17 | P9.2: Used Query alias for subscription_id/resource_group params | Maintains backward-compatible query string names in affected-vms endpoint |

---

*State version: 9.5*
*Updated: 2026-03-17 (P9.2 complete -- cve_inventory.py rewired, BH-002 + BH-003 eliminated; Phase 9 in progress 4/7 plans done)*

## Accumulated Context

### Roadmap Evolution
- Phase 11 added: validate everything is migrated from cosmos db to postgresql. remove legacy cosmos and fallback codes once validated. there should be no more cosmos code in the entire code base.
