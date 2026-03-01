---
phase: 03-performance-optimizations-days-8-10
plan: 03
subsystem: agents
tags: [asyncio, fire-and-forget, background-tasks, cosmos-db, gc-prevention, performance]

# Dependency graph
requires: []
provides:
  - _spawn_background() method in EOLOrchestratorAgent and MCPOrchestratorAgent
  - _background_tasks Set for GC prevention in both orchestrators
  - shutdown() method for clean cancellation of background tasks
  - Non-blocking Cosmos DB upsert in eol_orchestrator (fire-and-forget)
  - Non-blocking embedding index build in mcp_orchestrator (fire-and-forget)
affects: [03-04, 03-05, sre_orchestrator, inventory_orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fire-and-forget task-set: asyncio.Task tracked in Set, discard callback removes on completion, exceptions logged at DEBUG"
    - "Shutdown protocol: cancel all background tasks, gather with return_exceptions, clear set"

key-files:
  created:
    - app/agentic/eol/tests/unit/test_fire_and_forget.py
  modified:
    - app/agentic/eol/agents/eol_orchestrator.py
    - app/agentic/eol/agents/mcp_orchestrator.py

key-decisions:
  - "Used Set[asyncio.Task] for O(1) add/discard; discard callback fires immediately on task completion"
  - "Cosmos upsert closure uses default-argument binding to safely capture loop variables"
  - "Kept _spawn_background() duplicated in each orchestrator (not shared base class) per plan constraint — avoids larger refactor out of scope"
  - "shutdown() called at start of aclose() — background tasks cancel before owned agent cleanup"

patterns-established:
  - "Fire-and-forget pattern: _spawn_background(coro, name=...) for any async write that must not block the main request path"
  - "Closure variable capture: use default-argument binding (_var=var) for async closures inside methods"

requirements-completed:
  - TECH-TST-01
  - TECH-TST-02
  - TECH-TST-03
  - TECH-TST-04
  - PRF-01
  - PRF-02
  - NFR-PRF-02
  - NFR-SCL-02

# Metrics
duration: 11min
completed: 2026-03-01
---

# Phase 3 Plan 03: Fire-and-Forget Task Set Pattern Summary

**`_spawn_background()` + `Set[asyncio.Task]` GC-safe pattern added to both orchestrators; Cosmos upsert and embedding index build converted to non-blocking fire-and-forget tasks.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-01T08:34:04Z
- **Completed:** 2026-03-01T08:45:40Z
- **Tasks:** 2 (TDD: RED→GREEN→verify, then Task 2)
- **Files modified:** 3

## Accomplishments

- Implemented fire-and-forget task-set pattern with GC prevention in `EOLOrchestratorAgent`
- Converted blocking `await eol_inventory.upsert(...)` to non-blocking `_spawn_background(_do_upsert())` — Cosmos writes no longer add latency to EOL query responses
- Applied same pattern to `MCPOrchestratorAgent`, replacing bare `asyncio.create_task(self._build_embedding_index_bg())` with tracked `_spawn_background()`
- Added `shutdown()` method to both orchestrators for clean background task cancellation on lifecycle close
- 6 unit tests covering full task lifecycle: create → track → complete → discard, exception handling, shutdown cancellation, and 100-task scale test (GC prevention)

## Task Commits

TDD RED→GREEN cycle for Task 1, then Task 2 implementation:

1. **Task 1 RED: Failing unit tests** - `f50e357` (test)
2. **Task 1 GREEN: EOLOrchestratorAgent implementation** - `5c79b5a` (feat)
3. **Task 2: MCPOrchestratorAgent implementation** - `aec70fa` (feat)

_Note: No REFACTOR commit needed — implementation was already clean after GREEN._

## Files Created/Modified

- `app/agentic/eol/tests/unit/test_fire_and_forget.py` — 6 unit tests for fire-and-forget lifecycle
- `app/agentic/eol/agents/eol_orchestrator.py` — `_background_tasks` field, `_spawn_background()`, `shutdown()`, `aclose()` update, Cosmos upsert converted to fire-and-forget
- `app/agentic/eol/agents/mcp_orchestrator.py` — `Set` import added, `_background_tasks` field, `_spawn_background()`, `shutdown()`, `aclose()` update, embedding index build converted from bare `create_task`

## Decisions Made

- **Closure variable capture with default args**: The `_do_upsert()` async function captures loop variables using default argument binding (`_nn=normalized_name`) to avoid late-binding bugs common with closures in Python loops.
- **Duplicated `_spawn_background()` in both orchestrators**: The plan explicitly required no shared base class refactor. Each orchestrator gets a verbatim copy — safer scope, preserves independent evolution.
- **`shutdown()` called before `_close_lock` in `aclose()`**: Background tasks are cancelled first, then owned agents are cleaned up. This is the correct order — background tasks may reference agents, so cancel first.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's interface block described non-existent bare `asyncio.create_task` at ~line 741**
- **Found during:** Task 1 implementation inspection
- **Issue:** Plan's `<interfaces>` block stated "Bare asyncio.create_task (~line 741) — risky, no GC protection: `asyncio.create_task(self._analyze_os_item_eol(os_item))`". Actual code at line 741 is `tasks = [asyncio.create_task(...) for agent_name in agent_names ...]` — a list comprehension where all tasks are stored in `tasks` and then `await`ed via `asyncio.as_completed()`. This is NOT fire-and-forget.
- **Fix:** Correctly identified only the Cosmos upsert as the true blocking/fire-and-forget candidate. The list comprehension tasks don't need `_spawn_background()` since they're tracked in `tasks` and awaited.
- **Files modified:** None — no incorrect change made
- **Verification:** `grep -n "asyncio.create_task" eol_orchestrator.py` confirms list comprehension create_tasks remain (they await their results), only `_spawn_background()` calls replace true fire-and-forget patterns
- **Committed in:** Handled in `5c79b5a` (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug — plan's interface block inaccuracy caught and corrected)
**Impact on plan:** Positive — avoided incorrectly wrapping awaited agent tasks in fire-and-forget, which would have broken agent result collection.

## Issues Encountered

None — pre-existing test failures in `test_orchestrator_error_handling.py` (4 tests) are unrelated to this plan; they fail due to `utils` module path resolution issues when running from the project root. These failures existed before this plan and were verified by reverting changes to confirm.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Fire-and-forget pattern established and tested — ready for reuse in SRE orchestrator, inventory orchestrator (Phase 3 Plan 4+)
- Both orchestrators now have `shutdown()` and `_background_tasks` available
- Zero regressions in EOL orchestrator and integration test suites

---
*Phase: 03-performance-optimizations-days-8-10*
*Completed: 2026-03-01*

## Self-Check: PASSED

- [x] `test_fire_and_forget.py` exists on disk
- [x] All 6 unit tests pass (6 passed in 0.89s)
- [x] 4 commits tagged `03-03` exist in git log (`f50e357`, `5c79b5a`, `aec70fa`, `2e63b93`)
- [x] `03-03-SUMMARY.md` exists on disk
- [x] `_background_tasks` field present in `eol_orchestrator.py` (7 occurrences)
- [x] `_background_tasks` field present in `mcp_orchestrator.py` (7 occurrences)
- [x] `_spawn_background` used in `mcp_orchestrator.py` (2 occurrences: method def + call site)
