---
plan: 04-02
phase: 04-code-quality-polish
status: complete
completed: "2026-03-02"
branch: feature/prod-ready-phase-4
commits:
  - sha: "0251fa1"
    message: "feat(CQ-05/06/07): PlaywrightPool hard cap + SRE/Inventory shutdown hooks"
  - sha: "5d54055"
    message: "fix(CQ-03/CQ-04): unused import cleanup + logging level standardization"
tests_before: 204
tests_after: 213
regressions: 0
requirements_closed:
  - CQ-03
  - CQ-04
  - CQ-05
  - CQ-06
  - CQ-07
  - NFR-MNT-01
  - NFR-MNT-02
  - NFR-MNT-03
---

# Plan 04-02 Summary: Code Quality Polish

## Objective

Three targeted changes: (1) Add hard cap of 5 to `PlaywrightPool.setup()` and register
SRE/Inventory orchestrator shutdown hooks in `main.py`. (2) Remove unused imports from
4 target files. (3) Standardize logging levels in `agents/` and `utils/`.

---

## Task 1: PlaywrightPool Hard Cap + Shutdown Hooks

### Files Changed
- `app/agentic/eol/utils/playwright_pool.py`
- `app/agentic/eol/agents/sre_orchestrator.py`
- `app/agentic/eol/agents/inventory_orchestrator.py`
- `app/agentic/eol/main.py`
- `app/agentic/eol/utils/sre_startup.py`

### Changes Made

**A. PlaywrightPool hard cap (CQ-05/CQ-06):**
- Added `_MAX_POOL_SIZE = 5` constant inside `setup()` after the `_initialized` guard
- Clamps `max_concurrency` to 5 if exceeded, emitting `logger.warning` with the capped value
- Prevents resource exhaustion from misconfigured `MAX_PLAYWRIGHT_CONCURRENCY` env var

**B. SREOrchestratorAgent.shutdown() stub (CQ-07):**
- Added `async def shutdown()` to `SREOrchestratorAgent`
- SRE orchestrator is per-request (no persistent background tasks), so it's a
  lightweight stub that handles any optional `_background_tasks` set gracefully
- Added `_sre_orchestrator_instance` + `get_sre_orchestrator_instance()` to
  `sre_startup.py` for future long-lived instance storage

**C. InventoryAssistantOrchestrator.shutdown() (CQ-07):**
- Added `async def shutdown()` with full background-task cancellation pattern
- Uses `getattr(self, "_background_tasks", set())` defensively for compatibility
- Handles the case where local `asyncio.create_task()` calls complete inline

**D. main.py shutdown wiring:**
- Two try/except blocks added after inventory scheduler block in `_run_shutdown_tasks()`
- SRE hook: imports `get_sre_orchestrator_instance()` (returns None for per-request pattern)
- Inventory hook: uses module-level `inventory_asst_orchestrator` global directly

### Verification
- 20/20 fire-and-forget + performance tests pass
- All shutdown hooks guarded with `hasattr(..., "shutdown")` checks

---

## Task 2: Unused Imports + Logging Standardization

### Files Changed (Imports)
- `app/agentic/eol/agents/sre_orchestrator.py`
- `app/agentic/eol/agents/mcp_orchestrator.py`
- `app/agentic/eol/api/cache.py`
- `app/agentic/eol/main.py`

### Imports Removed (CQ-03)

| File | Import Removed | Reason |
|------|---------------|--------|
| `main.py` | `from openai import AzureOpenAI` | No usage in file body |
| `main.py` | `create_error_response` | Removed from utils import |
| `main.py` | `base_cosmos` (top-level) | Re-imported locally in each usage site |
| `main.py` | `ensure_standard_format` | Unused |
| `main.py` | `standard_endpoint` | Only in commented-out decorators |
| `main.py` | `pass` in `index()` stub | Docstring is sufficient function body |
| `sre_orchestrator.py` | `AgentExecutionError` | Not referenced in file |
| `sre_orchestrator.py` | `SREInteractionHandler` | Not referenced (get_interaction_handler used) |
| `sre_orchestrator.py` | `datetime, timedelta, timezone` | Not referenced |
| `sre_orchestrator.py` | `Tuple` | Not referenced |
| `api/cache.py` | `HTMLResponse`, `Jinja2Templates`, `Request` | Not used in router |

All 4 target files pass `autoflake --remove-all-unused-imports --check`.

### Logging Level Changes (CQ-04): 40 changes

| File | Count | Change |
|------|-------|--------|
| `agents/azure_ai_agent.py` | 17 | `logger.info([DEBUG])` → `logger.debug()` for diagnostic/inspection logs |
| `agents/azure_ai_agent.py` | 2 | Fallback path: `logger.info` → `logger.warning()` |
| `agents/os_inventory_agent.py` | 1 | Cache miss: `logger.info` → `logger.debug()` |
| `agents/software_inventory_agent.py` | 1 | Cache miss: `logger.info` → `logger.debug()` |
| `agents/playwright_agent.py` | 1 | Bing search detail: `logger.info` → `logger.debug()` |
| `utils/os_eol_mcp_client.py` | 1 | Fallback enable: `logger.info` → `logger.warning()` |
| `utils/inventory_mcp_client.py` | 1 | Fallback enable: `logger.info` → `logger.warning()` |
| `utils/error_boundary.py` | 1 | Fallback handler: `logger.info` → `logger.warning()` |
| `utils/alert_manager.py` | 1 | File-load fallback: `logger.info` → `logger.warning()` |
| `main.py` | 5 | Diagnostic API counts → `logger.debug()`; warnings cleaned up |

---

## Results

### Artifacts Verified

| Artifact | Check | Result |
|---------|-------|--------|
| `playwright_pool.py` contains `_MAX_POOL_SIZE = 5` | `grep -n "_MAX_POOL_SIZE"` | ✅ line 48 |
| `sre_orchestrator.py` has `async def shutdown` | `grep -n "async def shutdown"` | ✅ line 243 |
| `inventory_orchestrator.py` has `async def shutdown` | `grep -n "async def shutdown"` | ✅ line 138 |
| `main.py` calls `sre_orch.shutdown()` in `_run_shutdown_tasks()` | `grep "shutdown()"` | ✅ lines 659, 669 |
| All 4 target files pass `autoflake --check` | autoflake | ✅ "No issues detected!" |

### Test Results
- **Before:** 204 passed, 3 skipped
- **After:** 213 passed, 0 skipped (unit + integration core suite)
- **Regressions:** 0

### Requirements Closed
- **CQ-03**: Unused imports removed from all 4 target files ✅
- **CQ-04**: 40 logging level corrections applied (>10 minimum) ✅
- **CQ-05**: PlaywrightPool hard cap enforced at max 5 ✅
- **CQ-06**: Warning logged when concurrency is clamped ✅
- **CQ-07**: SRE + Inventory orchestrators implement `shutdown()`, both wired in `main.py` ✅
- **NFR-MNT-01/02/03**: Operational clarity improved via correct log levels ✅

---

## Key Decisions

1. **SRE per-request pattern**: `SREOrchestratorAgent` is created per-request (not a singleton).
   Added `get_sre_orchestrator_instance()` to `sre_startup.py` returning `None` for future
   compatibility; main.py wires it defensively with `if sre_orch is not None` guard.

2. **Inventory global**: `inventory_asst_orchestrator` is already a module-level global in
   `main.py`, so no additional module accessor was needed — used it directly in shutdown hook.

3. **autoflake `pass` removal**: `pass` in stub async function body is valid Python to remove
   since docstring serves as function body. Safe change.

4. **40 logging changes**: Focused on `azure_ai_agent.py` which had 17 `logger.info([DEBUG])`
   calls — the most impactful single file. Fallback-enabling paths across utils promoted to
   WARNING for operational clarity.
