# Phase 6: Migration, Testing & Documentation — Research

**Researched:** 2026-03-02
**Domain:** Python project migration, pytest testing strategy, technical documentation authoring
**Confidence:** HIGH

---

## Summary

Phase 6 is the capstone of a 5-phase orchestrator architecture refactor. All foundational work is complete: `MCPToolRegistry`, `MCPHost`, `BaseOrchestrator`, `UnifiedRouter`, `DomainClassifier`, enhanced retry, resource caps, graceful shutdown, and declarative `mcp_servers.yaml` + `MCPConfigLoader` + `MCPHost.from_config()`. Phase 6 must now document what changed, update the two orchestrators that haven't yet adopted the new architecture (`EOLOrchestratorAgent` and `InventoryAssistantOrchestrator`), build comprehensive tests, and produce the migration and documentation deliverables described in the roadmap.

The key insight is that this phase is **primarily a documentation and integration-wiring phase, not a major code authoring phase**. The architecture is stable and working. The migration guide already has partial content (the `utils/legacy/README.md` covers `ToolRouter` → `UnifiedRouter`). The test infrastructure is rich and established. The work is: (1) wire the two remaining orchestrators to new components where appropriate, (2) add targeted tests for Phase 5 and Phase 6 integration, and (3) write authoritative documentation covering the complete architecture.

**Primary recommendation:** Scope the orchestrator updates carefully. `EOLOrchestratorAgent` and `InventoryAssistantOrchestrator` are independent multi-agent systems that do NOT need the `UnifiedRouter` or `MCPToolRegistry` — they use their own specialist agents and patterns. The update goal is `MCPHost.from_config()` adoption in `main.py` startup, plus confirming documentation accurately describes what each orchestrator does and when to use each.

---

## Project Context

### Current Architecture State (as of Phase 5 completion)

```
MCPToolRegistry (Singleton)
      |
  MCPHost ←──── MCPHost.from_config(config/mcp_servers.yaml)
      |
MCPOrchestratorAgent (BaseOrchestrator)    ← uses UnifiedRouter
SREOrchestratorAgent (BaseSREAgent)        ← uses UnifiedRouter
EOLOrchestratorAgent                       ← standalone (doesn't use MCPHost/UnifiedRouter)
InventoryAssistantOrchestrator             ← standalone (agent_framework-backed)

UnifiedRouter (Singleton)
  ├── DomainClassifier (keyword, <5ms)
  └── fast/quality/comprehensive strategies

utils/mcp_config_loader.py  ← MCPConfigLoader, MCPServerConfig, MCPServersFile
config/mcp_servers.yaml     ← 10 server definitions, env-var-toggled
```

### What Each Orchestrator Does (and Whether It Needs Migration)

| Orchestrator | Class Hierarchy | Uses MCPHost? | Uses UnifiedRouter? | Migration Needed? |
|---|---|---|---|---|
| `MCPOrchestratorAgent` | `BaseOrchestrator` | Yes (manually wired) | Yes (`process_with_routing()`) | Wire `from_config()` in startup |
| `SREOrchestratorAgent` | `BaseSREAgent` | Via SREMCPClient | Yes (`process_with_routing()`) | Document gap (ARC-04 rec) |
| `EOLOrchestratorAgent` | Standalone | No (specialist agents) | No (own routing logic) | No code change needed |
| `InventoryAssistantOrchestrator` | Standalone (agent_framework) | No | No | No code change needed |

### Test Infrastructure

- **Framework:** pytest + pytest-asyncio (already in requirements.txt)
- **Config:** `tests/ui/pytest.ini` (UI tests); main tests use `conftest.py` at `tests/` root
- **Test count:** 100+ local tests (not committed per `.gitignore`), 1018+ passing
- **Test categories:** unit, integration, api, ui, slow, cache, eol, inventory, alerts
- **Known baseline:** 56 pre-existing failures (documented); 1018 passing
- **CRITICAL constraint:** Tests are NOT committed to git per `.gitignore` — only exception is explicit plan deliverables committed with `git add -f`

### Git/Commit Conventions

- Conventional commits: `feat(scope):`, `docs(scope):`, `test(scope):`, `refactor(scope):`
- Feature branches: `feature/XX-YY-description`
- Tests committed with `-f` override only when they are explicit plan deliverables
- Tests file: `tests/test_integration_phase{N}.py` pattern established (see Phase 4-03)

---

## Standard Stack

### Core (already installed — no new dependencies needed)

| Library | Version | Purpose | Already in requirements.txt |
|---------|---------|---------|--------------------------|
| `pytest` | ≥7.0 | Test runner | Yes |
| `pytest-asyncio` | ≥0.21 | Async test support | Yes |
| `httpx` | ≥0.24 | ASGI test client | Yes |
| `PyYAML` | 6.0.2 | YAML config parsing | Yes |
| `pydantic` | 2.12.4 | Config validation | Yes |

### Supporting (optional additions)

| Library | Purpose | When to Add |
|---------|---------|-------------|
| `pytest-cov` | Coverage reports | If 80% coverage measurement required |

**Installation:** No new packages needed. All dependencies exist.

---

## Architecture Patterns

### Pattern 1: MCPHost.from_config() — Startup Wiring

`main.py` currently initialises `MCPHost` manually (in `mcp_orchestrator.py` at agent init time). Phase 6 should wire `MCPHost.from_config()` into the startup sequence so the host is built from YAML declaratively.

**Current pattern (mcp_orchestrator.py):**
```python
# In _setup_mcp_client():
from utils.mcp_host import MCPHost
self._mcp_client = MCPHost(client_entries)
```

**Target pattern (main.py startup, or mcp_orchestrator.py lazy init):**
```python
from utils.mcp_host import MCPHost
host = await MCPHost.from_config()  # reads config/mcp_servers.yaml
```

**Decision:** Whether `from_config()` replaces the existing manual wiring in `MCPOrchestratorAgent._setup_mcp_client()` OR is added as an alternative startup path in `main.py`'s `_run_startup_tasks()` is a key planning decision. The ORCHESTRATOR-ROADMAP says "Update all orchestrators to use new architecture" — but practically, `MCPOrchestratorAgent` already works; adopting `from_config()` is an additive simplification.

### Pattern 2: Migration Guide Structure

The `utils/legacy/README.md` already documents ToolRouter → UnifiedRouter migration. The Phase 6 migration guide at `.planning/MIGRATION_GUIDE.md` should be a **single authoritative source** covering all 5 phases in one document.

**Recommended sections:**
1. Overview of all changes (what changed, why)
2. Breaking changes by component
3. Before/after code examples for each component
4. How to add a new MCP server (key productivity metric: <30 min)
5. How to add a new orchestrator
6. Troubleshooting (known issues, pre-existing failures, skip patterns)
7. Rollback procedure

### Pattern 3: Test Integration File Pattern

Established in Phase 4-03: `tests/test_integration_phase{N}.py` — 4-10 integration tests per phase that verify cross-component contracts. Phase 6's integration test file should cover:
- `MCPHost.from_config()` returns a valid host with tools
- `UnifiedRouter` + `MCPHost` round-trip produces valid plan
- `MCPConfigLoader` + `MCPHost.from_config()` smoke test
- Config yaml env-var toggle disables a server

### Pattern 4: Document Locations

**Committed docs:** Only `README*.md` pattern + explicit plan deliverables via `git add -f`
- `.planning/MIGRATION_GUIDE.md` → committed (explicit roadmap deliverable)
- `.claude/docs/ORCHESTRATOR_GUIDE.md` → local only (per `.gitignore`), committed with `-f`
- `docs/ADDING_MCP_SERVERS.md` → local only, committed with `-f`

**NOT committed:**
- `tests/test_integration_phase6.py` — local only
- `tests/test_e2e_phase6.py` — local only

### Anti-Patterns to Avoid

- **Don't refactor EOLOrchestratorAgent or InventoryAssistantOrchestrator to use MCPToolRegistry** — they are independent multi-agent systems with own tool routing. Forcing them onto the registry would be over-engineering and risks breaking 1843/2211 lines of working code.
- **Don't write integration tests that require live Azure connections** — mock mode (`USE_MOCK_DATA=true`) is the test default; real services only in `--remote` mode.
- **Don't commit tests without explicit `-f` override** — `.gitignore` excludes `tests/` at all levels; follow the established convention.
- **Don't add new dependencies** — all needed libraries already installed.
- **Don't change the SREOrchestratorAgent class hierarchy** — it inherits `BaseSREAgent` not `BaseOrchestrator`; this is an ARC-04 recommendation for Q2 2026, not Phase 6.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing with env interpolation | Custom `${VAR}` parser | `MCPConfigLoader._interpolate_env()` | Already built in Phase 5 |
| MCP server initialization | Manual client list | `MCPHost.from_config()` | Already built in Phase 5 |
| Domain routing | Custom classifier | `UnifiedRouter` + `DomainClassifier` | Built in Phase 3 |
| Retry with stats | Custom backoff | `retry_async()` + `RetryStats` | Built in Phase 4 |
| Before/after examples in migration docs | Invent content | Use existing `legacy/README.md` content | Already written, verified |

**Key insight:** The hardest parts of this phase (routing, config, registry, retry) are already built. Phase 6 is integration + documentation of completed work.

---

## Common Pitfalls

### Pitfall 1: Over-scoping Orchestrator Updates

**What goes wrong:** Attempting to make `EOLOrchestratorAgent` and `InventoryAssistantOrchestrator` extend `BaseOrchestrator` or use `MCPToolRegistry`. These orchestrators use completely different internal patterns (specialist EOL agents, Microsoft agent_framework) and don't call MCP tools directly.

**Why it happens:** The roadmap says "Update all orchestrators to use new architecture" — this can be misread as "migrate all 4 orchestrators to BaseOrchestrator."

**How to avoid:** Interpret "update" as "ensure compatible with new architecture" — meaning they work alongside the new components, not necessarily extend them. The only real update needed is confirming `shutdown()` methods exist (done in Phase 4) and ensuring `main.py` startup correctly initializes the new components.

**Warning signs:** If you're changing class hierarchies of `EOLOrchestratorAgent` or `InventoryAssistantOrchestrator`, stop and re-scope.

### Pitfall 2: Tests Not Committed

**What goes wrong:** Writing extensive test files and forgetting they won't persist to git. Verification steps appear to pass locally but the "test deliverable" doesn't exist in the repo.

**Why it happens:** `.gitignore` excludes `tests/` at all levels. Easy to forget.

**How to avoid:** For Phase 6 test deliverables that are REQUIRED (per roadmap acceptance criteria), use `git add -f tests/test_integration_phase6.py` — matching Phase 4-03's precedent.

**Warning signs:** `git status` shows tests as untracked but not staged.

### Pitfall 3: Migration Guide vs. Existing Content Duplication

**What goes wrong:** Writing a migration guide that duplicates content already in `utils/legacy/README.md`, `AGENT-HIERARCHY.md`, and phase summaries.

**Why it happens:** The migration guide is written from scratch without checking existing docs.

**How to avoid:** Start migration guide by referencing existing content: legacy README has ToolRouter/ToolEmbedder migration. AGENT-HIERARCHY.md has the 5-layer stack. Phase summaries have before/after context. The migration guide should synthesize and link, not duplicate.

### Pitfall 4: E2E Tests Require Live Azure

**What goes wrong:** E2E tests that call `/api/sre/execute` or `/api/azure-mcp/chat` require a live Azure connection to pass, making them unusable in CI.

**Why it happens:** The distinction between local mock mode and remote integration mode is subtle.

**How to avoid:** E2E tests for Phase 6 should use `USE_MOCK_DATA=true` (the default in conftest.py). Behavioral tests, not Azure call tests. The `--remote` flag exists for real integration runs.

### Pitfall 5: MCPHost.from_config() in Production Startup

**What goes wrong:** Wiring `MCPHost.from_config()` into `main.py`'s `_run_startup_tasks()` without understanding that `MCPOrchestratorAgent` also lazy-initializes its own client. Double initialization or registry conflicts can occur.

**Why it happens:** Two init paths competing for the `MCPToolRegistry` singleton.

**How to avoid:** Check how `MCPOrchestratorAgent.ensure_mcp_ready()` works. If `from_config()` is wired in startup, the agent's own `_setup_mcp_client()` should detect the registry is already populated (`_ensure_unified_router` pattern). Alternatively, wire `from_config()` ONLY inside `MCPOrchestratorAgent.__init__()` as a replacement for manual client construction.

---

## Code Examples

### Example 1: MCPHost.from_config() integration in startup

```python
# In main.py _run_startup_tasks(), or in MCPOrchestratorAgent initialization:
# Source: app/agentic/eol/utils/mcp_host.py (Phase 5 implementation)

from utils.mcp_host import MCPHost

async def initialize_mcp():
    host = await MCPHost.from_config()  # reads config/mcp_servers.yaml
    # host.ensure_registered() already called inside from_config()
    return host
```

### Example 2: Integration test pattern (following Phase 4-03 precedent)

```python
# Source: test_integration_phase4.py pattern
import pytest
from utils.mcp_config_loader import MCPConfigLoader
from utils.mcp_host import MCPHost

@pytest.mark.asyncio
async def test_mcp_host_from_config_smoke():
    """MCPHost.from_config() with all servers disabled returns valid host."""
    import os
    env_backup = {}
    disabled_keys = [
        "SRE_ENABLED", "AZURE_MCP_ENABLED", "NETWORK_ENABLED",
        "COMPUTE_ENABLED", "STORAGE_ENABLED", "MONITOR_ENABLED",
        "PATCH_ENABLED", "OS_EOL_ENABLED", "INVENTORY_ENABLED",
        "LABEL_MCP_ENABLED",
    ]
    for k in disabled_keys:
        env_backup[k] = os.environ.get(k)
        os.environ[k] = "false"
    try:
        host = await MCPHost.from_config()
        tools = host.get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) == 0  # All disabled
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
```

### Example 3: Migration guide before/after example (config approach)

```python
# BEFORE (Phase 0 — manual client construction):
from utils.sre_mcp_client import SREMCPClient
from utils.network_mcp_client import NetworkMCPClient
from utils.mcp_host import MCPHost

clients = [
    ("sre", await SREMCPClient.create()),
    ("network", await NetworkMCPClient.create()),
]
host = MCPHost(clients)

# AFTER (Phase 5+ — declarative config):
from utils.mcp_host import MCPHost

host = await MCPHost.from_config()  # reads config/mcp_servers.yaml
# Enable/disable servers via environment variables:
# SRE_ENABLED=false python main.py  → SRE server not initialized
```

### Example 4: Rollback procedure

```bash
# Rollback trigger: critical error post-deployment
# Rollback method: feature flag (env var) — fastest option
SRE_ENABLED=false NETWORK_ENABLED=false python main.py   # Disable problematic servers

# Full rollback: revert commit
git revert <phase6-commit-sha>   # Creates a new revert commit (non-destructive)
git push origin main

# Verify rollback
cd app/agentic/eol && python -c "from utils.mcp_host import MCPHost; print('OK')"
```

---

## State of the Art

| Old Approach | Current Approach (Phase 5+) | When Changed | Impact |
|---|---|---|---|
| Manual client list in `MCPOrchestratorAgent._setup_mcp_client()` | `MCPHost.from_config(config/mcp_servers.yaml)` | Phase 5 | Add MCP server by editing YAML, not Python |
| 3 parallel routing systems (`ToolRouter`, `ToolEmbedder`, custom logic) | Single `UnifiedRouter` with strategies | Phase 3 | One entry point for all routing |
| No orchestrator base class | `BaseOrchestrator` ABC with `process_message()`, `route_query()` | Phase 2 | Shared grounding, formatting, error handling |
| No tool registry | `MCPToolRegistry` singleton, 52 tools, zero duplication | Phase 1 | Single catalog for all MCP tools |
| No retry observability | `RetryStats`, `TryAgain`, `on_retry` callback | Phase 4-01 | Per-call attempt/delay/exception tracking |

**Deprecated/outdated:**
- `ToolRouter` in `utils/tool_router.py`: deprecated (still functional for legacy ReAct path in `MCPOrchestratorAgent`), replaced by `UnifiedRouter`
- `ToolEmbedder` in `utils/tool_embedder.py`: deprecated, replaced by `UnifiedRouter` quality strategy
- `mcp_composite_client.py`: backward compat re-export of `MCPHost` only — do not use directly

---

## Open Questions

1. **Should `MCPOrchestratorAgent._setup_mcp_client()` call `MCPHost.from_config()` or remain manual?**
   - What we know: `from_config()` works, gracefully degrades, is already smoke-tested
   - What's unclear: Whether replacing the manual path risks breaking the existing ReAct loop (which still uses `ToolRouter`/`ToolEmbedder`)
   - Recommendation: Wire `from_config()` as the ONLY startup path, remove manual client construction. The legacy ReAct tools still get their client via `self._mcp_client` — same host, different path.

2. **Does main.py need explicit `MCPHost.from_config()` in startup, or is lazy-init in MCPOrchestratorAgent sufficient?**
   - What we know: `MCPOrchestratorAgent` lazy-initializes via `ensure_mcp_ready()` on first request
   - What's unclear: Whether there's a warm-up benefit to eager init at startup
   - Recommendation: Add eager startup init in `_run_startup_tasks()` as a non-blocking warm-up (like `_startup_inventory_discovery()`), with graceful failure handling.

3. **What is the rollout plan given this is a demo app (no production traffic)?**
   - What we know: This is the GCC demo platform, not a production app with real user traffic
   - What's unclear: Whether "10% traffic rollout" applies or if this is simply merge-to-main + smoke test
   - Recommendation: Simplify rollout to: merge to main → run full test suite → smoke test locally → done. Skip staged traffic rollout.

---

## Phase 6 Deliverables — Scoping Analysis

### 6.1 Migration Guide (`.planning/MIGRATION_GUIDE.md`)

**Scope:** Synthesize all 5 phases. Reference `utils/legacy/README.md` for ToolRouter/ToolEmbedder migration. Add `MCPHost.from_config()` usage guide. Document before/after for each new component.

**Effort estimate:** MEDIUM — most content exists in phase summaries and legacy README.

### 6.2 Update Orchestrators

**Actual scope (not all 4 orchestrators):**
- `mcp_orchestrator.py`: Replace manual `MCPHost(clients)` construction with `MCPHost.from_config()` — LOW RISK
- `main.py`: Add eager `MCPHost.from_config()` warm-up in `_run_startup_tasks()` — LOW RISK
- `eol_orchestrator.py`: No code change needed — verify `shutdown()` exists ✅ (line 324)
- `inventory_orchestrator.py`: No code change needed — `shutdown()` already wired ✅ (Phase 4-02)
- `sre_orchestrator.py`: No code change needed — `shutdown()` and `process_with_routing()` already present ✅

**Effort estimate:** LOW — one focused change in `mcp_orchestrator.py` + `main.py`.

### 6.3 Comprehensive Testing

**Recommended test file:** `tests/test_integration_phase6.py` (commit with `git add -f`)

**Tests to write:**
- `test_mcp_host_from_config_smoke` — all servers disabled → valid empty host
- `test_mcp_config_loader_env_toggle` — env var disables server
- `test_unified_router_with_mcp_host` — router produces plan, host has matching tools
- `test_migration_guide_examples_work` — execute code from migration guide directly

**Existing tests to verify (not write new):**
- `tests/orchestrators/test_orchestrator_tool_access.py` — MCPHost tool access
- `tests/routing/test_unified_router.py` — UnifiedRouter behavior
- `tests/routing/test_domain_classifier.py` — DomainClassifier

**Effort estimate:** MEDIUM — ~30-40 lines per test, 4-6 tests total.

### 6.4 Documentation Updates

**Files to create/update (commit with `git add -f` per project convention):**
- `.claude/docs/ORCHESTRATOR_GUIDE.md` — NEW: when to use which orchestrator, adding new servers
- `docs/ADDING_MCP_SERVERS.md` — NEW: step-by-step guide for new server addition (<30 min goal)
- `.planning/research/orchestrator-patterns.md` — UPDATE: add Phase 1-5 completed patterns
- `agents/CLAUDE.md` — UPDATE: add BaseOrchestrator usage, new architecture notes

**Effort estimate:** MEDIUM — structured docs, can reference AGENT-HIERARCHY.md heavily.

### 6.5 Rollout Plan

For this demo app context, simplified rollout:

```
Phase 6A: Merge feature branch to main
  → Run: cd tests && ./run_tests.sh
  → Verify: 1018+ passing, 56 pre-existing failures (baseline maintained)
  → Smoke test: uvicorn main:app --port 8000 → curl /health

Phase 6B: Smoke Test Critical Paths
  → MCPHost.from_config() initializes successfully
  → UnifiedRouter routes a test query correctly
  → MCPConfigLoader reads mcp_servers.yaml without error

Phase 6C: Cleanup (no separate step needed)
  → utils/legacy/ already in place
  → feature flags (env vars) already in mcp_servers.yaml
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `tests/ui/pytest.ini` (UI tests); conftest.py at `tests/` root |
| Quick run command | `pytest tests/test_integration_phase6.py -v` |
| Full suite command | `cd tests && ./run_tests.sh` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Command | File Exists? |
|-----|----------|-----------|---------|-------------|
| MIG-01 | Migration guide complete | Manual review | — | ❌ Wave 0 |
| MIG-02 | MCPHost.from_config() used in main orchestration path | Unit/integration | `pytest tests/test_integration_phase6.py::test_mcp_host_from_config_smoke -x` | ❌ Wave 0 |
| MIG-03 | Config env-var toggle works end-to-end | Unit | `pytest tests/test_integration_phase6.py::test_mcp_config_loader_env_toggle -x` | ❌ Wave 0 |
| MIG-04 | Full test suite passes (baseline maintained) | Suite | `cd tests && ./run_tests.sh` | ✅ exists |
| MIG-05 | Orchestrator docs complete | Manual review | — | ❌ Wave 0 |
| MIG-06 | Adding new MCP server guide complete | Manual review | — | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_integration_phase6.py -v`
- **Per wave merge:** `cd tests && ./run_tests.sh`
- **Phase gate:** Full suite green (1018+ passing, 56 pre-existing failures) before done

### Wave 0 Gaps
- [ ] `tests/test_integration_phase6.py` — covers MIG-02, MIG-03 (commit with `git add -f`)
- [ ] `.planning/MIGRATION_GUIDE.md` — MIG-01
- [ ] `.claude/docs/ORCHESTRATOR_GUIDE.md` — MIG-05 (commit with `git add -f`)
- [ ] `docs/ADDING_MCP_SERVERS.md` — MIG-06 (commit with `git add -f`)

---

## Sources

### Primary (HIGH confidence)

- **Project source code** — `app/agentic/eol/agents/*.py`, `utils/mcp_host.py`, `utils/mcp_config_loader.py` — verified current state
- **Phase summaries** — `.planning/phases/03-*/03-01-SUMMARY.md`, `04-*/04-01/02/03-SUMMARY.md`, `05-*/05-01/02-SUMMARY.md` — authoritative completed-work records
- **STATE.md** — `.planning/STATE.md` — current architecture diagram, key decisions, active issues
- **ORCHESTRATOR-ROADMAP.md** — `.planning/ORCHESTRATOR-ROADMAP.md` — Phase 6 objectives and acceptance criteria
- **EOL CLAUDE.md** — `app/agentic/eol/CLAUDE.md` — git/test commit rules, what IS and IS NOT committed
- **legacy README** — `utils/legacy/README.md` — existing migration guide content for ToolRouter/ToolEmbedder

### Secondary (MEDIUM confidence)

- **conftest.py** — `tests/conftest.py` — test infrastructure, USE_MOCK_DATA pattern, fixture conventions
- **test_integration_phase4.py** — Pattern for integration test deliverables committed with `git add -f`
- **AGENT-HIERARCHY.md** — `.claude/docs/AGENT-HIERARCHY.md` — 5-layer stack, ARC-04 simplification recs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all tools already in use
- Architecture: HIGH — verified from current source code, not assumptions
- Pitfalls: HIGH — drawn from real decisions documented in phase summaries
- Test patterns: HIGH — conftest.py and existing test files examined directly

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable architecture; 30-day validity)
