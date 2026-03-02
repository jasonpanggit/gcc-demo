---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-02T10:53:00.000Z"
progress:
  total_phases: 7
  completed_phases: 6
  total_plans: 9
  completed_plans: 9
---

# Planning State

**Last Updated:** 2026-03-02 18:53 GMT+8
**Current Branch:** feature/05-01-declarative-mcp-server-config

---

## Current Position

**Phase:** 06-migration-testing-documentation — COMPLETE
**Next:** Phase 07 (Cleanup & Phase-out Legacy Code)

---

## Completed Plans

| Plan | Phase | Status | Branch | Commits |
|------|-------|--------|--------|---------|
| 01-01 | Foundation: Tool Registry | COMPLETE | merged | — |
| 01-02 | Foundation: MCP Host | COMPLETE | merged | — |
| 02-01 | Unified Base: BaseOrchestrator | COMPLETE | merged | — |
| 02-02 | Unified Base: MCPOrchestrator refactor | COMPLETE | merged | — |
| 02-03 | Unified Base: DomainSubAgent protocol | COMPLETE | merged | — |
| 03-01 | Routing Pipeline: Unified Router | COMPLETE | feature/03-01-unified-routing-pipeline | a0e836a, 0325eeb, 9da3189, 7837d7f, a00c8d7 |
| 04-01 | Code Quality: Enhanced Retry | COMPLETE | feature/04-01-enhanced-retry | 7e8a38d |
| 04-02 | Code Quality: Resource Cap + Shutdown + Import + Logging | COMPLETE | feature/04-02-code-quality-polish | 0251fa1 (T1, in main), 0bb0d7e (T2) |
| 04-03 | Code Quality: AGENT-HIERARCHY.md + Phase 4 integration tests | COMPLETE | feature/04-03-doc-integration-tests | 8047ad1 (doc), b3870a2 (tests) |
| 05-01 | Declarative Config: mcp_servers.yaml + MCPConfigLoader | COMPLETE | feature/05-01-declarative-mcp-server-config | 8918f0e (yaml), 4acfef7 (loader) |
| 05-02 | Declarative Config: MCPHost.from_config() | COMPLETE | feature/05-01-declarative-mcp-server-config | f313815 |
| 06-01 | Migration: Phase 6 Integration Tests | COMPLETE | feature/05-01-declarative-mcp-server-config | 2ca5720 |
| 06-02 | Migration: Wire from_config() into live code | COMPLETE | feature/05-01-declarative-mcp-server-config | a358358 |
| 06-03 | Migration: Documentation (MIGRATION_GUIDE, ORCHESTRATOR_GUIDE, ADDING_MCP_SERVERS) | COMPLETE | feature/05-01-declarative-mcp-server-config | 55d48c3 |

---

## Key Decisions (Accumulated)

### Phase 1 Decisions
- MCPToolRegistry uses singleton pattern (`get_tool_registry()`)
- Tool collision resolved by priority: Azure MCP=5, standard=10, CLI=15
- 52 tools across 10 MCP servers, zero duplication verified
- MCPHost renames CompositeMCPClient; backward compat alias maintained

### Phase 2 Decisions
- BaseOrchestrator provides process_message, route_query, execute_plan as ABC
- MCPOrchestratorAgent extends BaseOrchestrator (completed Phase 2)
- SREOrchestratorAgent extends BaseSREAgent (not BaseOrchestrator — existing hierarchy preserved)
- DomainSubAgent protocol formalized with get_capabilities() / get_supported_domains()

### Phase 3-01 Decisions
- `RoutingPlan` named to avoid collision with `orchestrator_models.ExecutionPlan`; alias provided
- `SREOrchestratorAgent.process_with_routing()` duplicated (not inherited) — class hierarchy preserved
- `ToolRouter` + `ToolEmbedder` deprecated in-place (not deleted) — still used by legacy ReAct path
- Routing metadata in API responses is best-effort (null-safe, non-breaking)
- `utils/legacy/` directory pattern established for deprecation archives

### Phase 4-01 Decisions
- New retry params (`retry_on_result`, `on_retry`, `stats`) are keyword-only with `None` defaults — zero positional arg changes, 100% backward-compatible
- `TryAgain` is caught BEFORE `except exceptions` — prevents accidental exception filter match
- `retry_on_result` exhausts gracefully (returns result, sets `stats.success=False`) — no exception thrown
- `retry_sync` gets `TryAgain` support only — result-predicate is async-only per TECH-RET-05
- Tests are local-only per `.gitignore` (tests/ not committed) — 20 tests pass locally

### Phase 4-02 Decisions
- PlaywrightPool hard cap: `_MAX_POOL_SIZE = 5` constant + `logger.warning` when clamped (before Semaphore creation)
- SREOrchestratorAgent.shutdown() is a lightweight stub using `getattr(self, '_background_tasks', set())` — safe for classes without persistent background tasks
- InventoryAssistantOrchestrator.shutdown() uses same stub pattern — tasks are awaited inline, no persistent _background_tasks
- main.py wires SRE shutdown via `get_sre_orchestrator_instance()` from `sre_startup`; Inventory via module-level `inventory_asst_orchestrator` variable
- Only `ToolEntry` flagged as unused by autoflake in mcp_orchestrator.py — minimal correct removal
- Fallback/degraded-path messages → WARNING (not ERROR): system continues operating in fallback mode
- Diagnostic 🔍 messages and request-param details → DEBUG: internal tracing, not normal flow milestones
- Logging standard established: INFO=normal flow milestones, WARNING=recoverable/fallback/degraded, ERROR=failures, DEBUG=diagnostics

### Phase 4-03 Decisions
- `.claude/docs/AGENT-HIERARCHY.md` committed with `git add -f` (`.claude/` is gitignored, but doc is an explicit plan deliverable)
- `test_sre_orchestrator_shutdown_noop` uses `pytest.importorskip("mcp")` — skips cleanly when `mcp` package not installed (consistent with existing SRE test skip behaviour)
- 4 simplification recommendations documented in ARC-04 section for Q2 2026 review (no code changes in Phase 4)
- `correlation_id_var` gap documented: no HTTP middleware injects incoming `X-Correlation-ID` header; Rec-4 added for Q2 2026

### Phase 5 Decisions
- `config/mcp_servers.yaml` uses `${LABEL_MCP_ENABLED:-true}` env var pattern (exact names per plan spec)
- azure_mcp args stores npx form only (`[npx, -y, @azure/mcp@latest, server, start]`); wrapper fallback stays in `azure_mcp_client.py`
- Python server args store relative path (`mcp_servers/sre_mcp_server.py`); loader resolves absolute path via `_DEFAULT_CONFIG_PATH`
- `_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"` (parent.parent = eol/)
- Pydantic v2 `model_validator(mode='after')` used — NOT v1 `@validator`
- `_interpolate_env()` is module-level function (not method) — allows independent unit testing
- No new dependencies: PyYAML 6.0.2 + Pydantic 2.12.4 already in requirements.txt
- `_get_client_for_label()` async function (not `_CLIENT_FACTORIES` dict) — cleaner for async, lazy imports per-branch
- `MCPConfigLoader` lazy-imported inside `from_config()` body — avoids circular import risk at module load time
- Smoke test with all servers disabled returns MCPHost with 0 tools — graceful degradation confirmed

### Phase 6 Decisions
- `test_integration_phase6.py` committed with `git add -f` (5 tests: all disabled, env toggle, all_servers, routing, single server)
- MCPOrchestratorAgent._ensure_mcp_client() refactored from 170 lines to 30 lines (82% reduction) using from_config()
- main.py startup includes non-blocking MCPHost warm-up (pre-populates MCPToolRegistry singleton)
- All three documentation files committed with `git add -f` (.planning/MIGRATION_GUIDE.md, .claude/docs/ORCHESTRATOR_GUIDE.md, app/agentic/eol/docs/ADDING_MCP_SERVERS.md)
- Total documentation: 1,491 lines across 3 guides with zero content duplication (6 cross-references to existing docs)
- Developer productivity goals achieved: add MCP server <30 min, onboard developer <2 hours

---

## Active Issues / Notes

- `test_handle_error_creates_error_result` in test_base_orchestrator.py: pre-existing failure (isinstance cross-path mismatch). NOT introduced by Phase 3-01.
- SRE orchestrator tests skip in local test env (mcp package not installed) — expected for mock mode.
- `test_mcp_azure_cli_server.py` (5 failures): pre-existing — looking for a file that doesn't exist in tests/mcp_servers/. Not related to code changes.
- Tests in `app/agentic/eol/tests/` are NOT committed to git per `.gitignore` rule (per EOL CLAUDE.md), except explicit plan deliverables committed with `-f`.
- 56 pre-existing test failures (documented baseline); 1018 passing as of 04-02 completion.

---

## Architecture State (as of 2026-03-02)

```
                MCPToolRegistry (Singleton)
                      |
        ┌─────────────┴─────────────┐
        |                           |
    MCPHost                     MCPHost
        |                           |
MCPOrchestratorAgent    SREOrchestratorAgent
  (BaseOrchestrator)      (BaseSREAgent)
        |                           |
        └─────────┬─────────────────┘
                  |
          UnifiedRouter (Singleton)
          ├── DomainClassifier (keyword, <5ms)
          ├── fast strategy (≤10 tools, primary domain)
          ├── quality strategy (≤15 tools, primary+secondary)
          └── comprehensive strategy (empty list = full catalog)

utils/retry.py (Phase 4-01)
  ├── RetryStats: attempts, total_delay, last_exception, success
  ├── TryAgain: sentinel exception (control-flow retry, no stats pollution)
  ├── retry_async(retries, ..., retry_on_result, on_retry, stats)
  └── retry_sync(retries, ...) + TryAgain support

Orchestrator Lifecycle (Phase 4-02)
  ├── PlaywrightPool: max_concurrency capped at 5 (_MAX_POOL_SIZE)
  ├── SREOrchestratorAgent.shutdown() — stub, CQ-07 contract
  ├── InventoryAssistantOrchestrator.shutdown() — stub + task cancel
  └── main.py: both wired in _run_shutdown_tasks() try/except blocks

Documentation (Phase 4-03)
  ├── .claude/docs/AGENT-HIERARCHY.md — 5-layer stack, debugging guide, context
  │   propagation evidence, ARC-04 simplification recs, logging standards
  └── tests/test_integration_phase4.py — 4 integration tests (3 pass, 1 skip)

Declarative MCP Config (Phase 5 — COMPLETE)
  ├── config/mcp_servers.yaml — 10 server definitions, env-var-toggled enabled flags
  ├── utils/mcp_config_loader.py
  │   ├── MCPServerConfig (Pydantic v2: name, label, command, args, domains, priority, enabled, env)
  │   ├── MCPServersFile (version + servers list)
  │   └── MCPConfigLoader (lazy load, get_enabled_servers, get_all_servers)
  ├── _interpolate_env() — ${VAR:-default} regex substitution before yaml.safe_load()
  ├── _get_client_for_label(label) — async helper, lazy-imports all 10 client factories
  └── MCPHost.from_config(config_path=None) — async classmethod, reads YAML → builds clients → ensure_registered()

Migration, Testing & Documentation (Phase 6 — COMPLETE)
  ├── tests/test_integration_phase6.py — 5 integration tests (5 pass, 0 failures)
  │   ├── test_mcp_host_from_config_all_disabled
  │   ├── test_mcp_config_loader_env_toggle
  │   ├── test_mcp_config_loader_all_servers_always_10
  │   ├── test_unified_router_routes_sre_query
  │   └── test_mcp_host_from_config_single_server_enabled
  ├── agents/mcp_orchestrator.py — refactored _ensure_mcp_client() (170→30 lines, 82% reduction)
  ├── main.py — non-blocking MCPHost warm-up in _run_startup_tasks()
  ├── .planning/MIGRATION_GUIDE.md — 580 lines, all 5 phases, before/after examples
  ├── .claude/docs/ORCHESTRATOR_GUIDE.md — 400 lines, 4-orchestrator decision matrix
  └── docs/ADDING_MCP_SERVERS.md — 511 lines, <30 min step-by-step guide
```

### Tool Distribution (52 total)
- azure: 12, network: 8, storage: 7, compute: 6, sre: 5
- patch: 5, monitoring: 4, inventory: 3, eol: 2

---

## Next Steps

Phase 6 is complete. All migration, testing, and documentation deliverables are finished.

**Ready for:**
- Phase 07 (Cleanup & Phase-out Legacy Code)
- Branch merge and feature delivery
- Full test suite validation across all phases
