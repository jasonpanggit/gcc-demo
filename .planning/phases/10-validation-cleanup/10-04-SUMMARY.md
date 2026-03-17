---
phase: 10-validation-cleanup
plan: "04"
subsystem: utils
tags: [dead-code, mcp, feature-flags, cleanup]

requires:
  - phase: 10-validation-cleanup
    provides: Performance validation suite (P10.2), Dead code removal cosmos stubs (P10.3)
provides:
  - mcp_composite_client.py deleted — all callers use MCPHost from mcp_host
  - CompositeMCPClient alias removed from mcp_host.py
  - INVENTORY_USE_UNIFIED_VIEW flag verified absent (removed in Phase 9)
  - cve_dashboard PDF export verified using MV fast-path (consolidated in Phase 9)
  - cve_in_memory_repository.py documented with Phase-11 TODO
affects: [mcp-integration, tool-routing, mock-mode]

tech-stack:
  added: []
  patterns:
    - "MCPHost is the sole MCP coordinator class (no more CompositeMCPClient alias)"

key-files:
  created: []
  modified:
    - "app/agentic/eol/utils/mcp_host.py"
    - "app/agentic/eol/utils/executor.py"
    - "app/agentic/eol/utils/tool_retriever.py"
    - "app/agentic/eol/utils/tool_manifest_index.py"
    - "app/agentic/eol/utils/unified_domain_registry.py"
    - "app/agentic/eol/agents/mcp_orchestrator.py"
    - "app/agentic/eol/utils/manifests/azure_manifests.py"
    - "app/agentic/eol/utils/legacy/tool_router.py"
    - "app/agentic/eol/utils/cve_in_memory_repository.py"

key-decisions:
  - "Legacy tool_router.py and tool_embedder.py retained: active callers in mcp_orchestrator.py and tool_retriever.py require non-trivial refactor to remove"
  - "cve_in_memory_repository.py retained: required for USE_MOCK_DATA=true mode in main.py"

patterns-established:
  - "MCPHost is the canonical MCP coordinator name — no backward compat aliases"

requirements-completed: [QRY-03]

duration: 8 min
completed: 2026-03-17
---

# Phase 10 Plan 4: Dead Code Removal Summary

**Deleted mcp_composite_client.py deprecated shim, removed CompositeMCPClient alias from mcp_host.py, verified BH-045/BH-046 already resolved by Phase 9**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-17T15:46:53Z
- **Completed:** 2026-03-17T15:55:25Z
- **Tasks:** 4
- **Files modified:** 10

## Accomplishments
- Deleted `utils/mcp_composite_client.py` — zero active imports confirmed before deletion
- Removed backward compat `CompositeMCPClient = MCPHost` alias from `mcp_host.py`
- Updated all docstring/comment references from CompositeMCPClient to MCPHost across 8 files
- Verified `INVENTORY_USE_UNIFIED_VIEW` flag has zero references (BH-045 — already cleaned by Phase 9)
- Verified CVE dashboard PDF export uses MV repository methods (BH-046 — already consolidated by Phase 9)
- Documented `cve_in_memory_repository.py` mock-mode dependency with Phase-11 TODO

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify INVENTORY_USE_UNIFIED_VIEW flag (BH-045)** — No commit needed (verified absent, zero references)
2. **Task 2: Verify cve_dashboard PDF path uses MV (BH-046)** — No commit needed (verified MV fast-path already active)
3. **Task 3: Delete mcp_composite_client.py and update callers** — `a0ce601` (feat)
4. **Task 4: Handle cve_in_memory_repository.py** — `5c9cad2` (feat)

## Files Created/Modified
- `app/agentic/eol/utils/mcp_composite_client.py` — DELETED (deprecated re-export shim)
- `app/agentic/eol/utils/mcp_host.py` — Removed CompositeMCPClient alias and updated module docstring
- `app/agentic/eol/utils/executor.py` — Updated docstrings and error messages to reference MCPHost
- `app/agentic/eol/utils/tool_retriever.py` — Updated docstrings to reference MCPHost
- `app/agentic/eol/utils/tool_manifest_index.py` — Updated module docstring
- `app/agentic/eol/utils/unified_domain_registry.py` — Updated type comment
- `app/agentic/eol/agents/mcp_orchestrator.py` — Updated warning messages
- `app/agentic/eol/utils/manifests/azure_manifests.py` — Updated module docstring
- `app/agentic/eol/utils/legacy/tool_router.py` — Updated class docstring
- `app/agentic/eol/utils/cve_in_memory_repository.py` — Added Phase-11 TODO comment

## Decisions Made
- **Legacy files retained:** `legacy/tool_router.py` and `legacy/tool_embedder.py` have active callers in `mcp_orchestrator.py` (ToolEmbedder import for ReAct path) and `tool_retriever.py` (ToolEmbedder for semantic ranking). Deleting these requires non-trivial refactoring beyond dead-code removal scope.
- **cve_in_memory_repository.py retained:** Still required for `USE_MOCK_DATA=true` mode in `main.py` line ~659. Mock mode creates `CVEInMemoryRepository()` as the repository for `CVEService`. Deferred to Phase 11.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Legacy tool_router.py and tool_embedder.py not deleted**
- **Found during:** Task 3 (Delete legacy files)
- **Issue:** Plan expected legacy files could be deleted or callers trivially updated. Active callers found in `mcp_orchestrator.py` (imports ToolEmbedder), `tool_retriever.py` (imports ToolEmbedder), `scripts/selection_reporter.py` (imports ToolRouter), and root-level `utils/tool_embedder.py` + `utils/tool_router.py` re-export shims.
- **Fix:** Retained legacy files. Updated docstring references from CompositeMCPClient to MCPHost. Full migration of callers to use unified_router equivalents requires architectural changes beyond dead-code cleanup scope.
- **Files affected:** `legacy/tool_router.py`, `legacy/tool_embedder.py` (kept)
- **Verification:** All modified files parse cleanly with py_compile
- **Committed in:** a0ce601 (documented in commit message)

---

**Total deviations:** 1 auto-fixed (blocking — legacy files retained due to active callers)
**Impact on plan:** Minimal. Primary goal (delete mcp_composite_client.py) achieved. Legacy file deletion deferred to future plan.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dead code removal (dual-path, duplicates, legacy) complete within safe scope
- Ready for P10.5 (next plan in Phase 10)
- Legacy tool_router.py/tool_embedder.py deletion should be planned as a separate refactoring task

---
*Phase: 10-validation-cleanup*
*Completed: 2026-03-17*
