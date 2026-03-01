---
phase: 03-performance-optimizations-days-8-10
plan: 02
subsystem: agents
tags: [azure-identity, credential-sharing, singleton, performance, azure-sdk-manager]

# Dependency graph
requires:
  - phase: 03-performance-optimizations-days-8-10
    plan: 01
    provides: AzureSDKManager singleton with get_credential() and get_async_credential()
provides:
  - All 6 agents now source credentials from AzureSDKManager singleton instead of constructing independently
  - Credential warm-up happens once at startup; agents share the pre-warmed token
  - 2 new integration tests verifying credential sharing (Tests 10-11)
affects:
  - 03-03
  - 03-04
  - 03-05

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Local import pattern: `from utils.azure_client_manager import get_azure_sdk_manager` inside __init__ or method body to avoid circular imports"
    - "Mock-mode guard preserved: `if DefaultAzureCredential is None` guards still protect os_inventory and software_inventory agents"
    - "Async credential via manager: monitor_agent and domain_sub_agent use get_async_credential() for async code paths"

key-files:
  created: []
  modified:
    - app/agentic/eol/agents/azure_ai_agent.py
    - app/agentic/eol/agents/os_inventory_agent.py
    - app/agentic/eol/agents/software_inventory_agent.py
    - app/agentic/eol/agents/openai_agent.py
    - app/agentic/eol/agents/monitor_agent.py
    - app/agentic/eol/agents/domain_sub_agent.py
    - app/agentic/eol/tests/unit/test_azure_client_manager.py

key-decisions:
  - "openai_agent.py: replaced top-level `from azure.identity import DefaultAzureCredential` with `from utils.azure_client_manager import get_azure_sdk_manager` — cleanest change since no mock-mode guard exists in that file"
  - "monitor_agent.py and domain_sub_agent.py: local import inside method body preserved (not moved to module level) to minimize diff scope and avoid any import-order issues"
  - "Tests 10-11 went directly GREEN: AzureSDKManager.get_credential() caching was already implemented in Plan 03-01 — tests verify existing singleton contract"

patterns-established:
  - "Agent credential pattern: always source from get_azure_sdk_manager().get_credential() (sync) or .get_async_credential() (async)"
  - "Mock-mode guard preserved: agents that check `if DefaultAzureCredential is None` retain that guard — mock mode still works"

requirements-completed:
  - PRF-03
  - NFR-PRF-03
  - NFR-PRF-04
  - NFR-SCL-01

# Metrics
duration: 5min
completed: 2026-03-01
---

# Phase 3 Plan 02: Agent Credential Migration Summary

**All 6 agents migrated to share credentials via AzureSDKManager singleton, eliminating 6 independent MSAL auth flows; 17 unit tests pass including 2 new credential-sharing integration tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-01T08:51:08Z
- **Completed:** 2026-03-01T08:56:55Z
- **Tasks:** 2 completed
- **Files modified:** 7

## Accomplishments

- All 6 agents (4 sync + 2 async) now use `AzureSDKManager` for credentials instead of constructing `DefaultAzureCredential`/`AsyncDefaultAzureCredential` independently
- Mock-mode guards preserved in `os_inventory_agent.py` and `software_inventory_agent.py` — backward compatibility maintained
- 2 new integration tests (`TestCredentialSharing`) verify credential sharing contract — 17 total tests in `test_azure_client_manager.py`, all passing
- Zero new test failures introduced (1203 unit tests pass)

## Task Commits

Each task was committed atomically:

1. **Task 1: Update all 6 agents to use AzureSDKManager credential** - `de8cd86` (feat)
2. **Task 2: Add integration tests verifying credential sharing** - `abfe85f` (test)

**Plan metadata:** _(docs commit to follow)_

## Files Created/Modified

- `app/agentic/eol/agents/azure_ai_agent.py` — replaced `DefaultAzureCredential()` with `get_azure_sdk_manager().get_credential()`
- `app/agentic/eol/agents/os_inventory_agent.py` — replaced `DefaultAzureCredential()` with shared manager (mock guard preserved)
- `app/agentic/eol/agents/software_inventory_agent.py` — replaced `DefaultAzureCredential()` with shared manager (mock guard preserved)
- `app/agentic/eol/agents/openai_agent.py` — replaced top-level import + `DefaultAzureCredential(...)` instantiation with `get_azure_sdk_manager().get_credential()`
- `app/agentic/eol/agents/monitor_agent.py` — replaced local `AsyncDefaultAzureCredential()` with `get_azure_sdk_manager().get_async_credential()`
- `app/agentic/eol/agents/domain_sub_agent.py` — replaced local `AsyncDefaultAzureCredential()` with `get_azure_sdk_manager().get_async_credential()`
- `app/agentic/eol/tests/unit/test_azure_client_manager.py` — added `TestCredentialSharing` class with Tests 10-11

## Decisions Made

- **openai_agent.py import approach:** Replaced the top-level `from azure.identity import DefaultAzureCredential` with `from utils.azure_client_manager import get_azure_sdk_manager` at module level — cleanest migration since no mock-mode guard exists in this file.
- **monitor_agent.py / domain_sub_agent.py:** Local import inside the method body preserved (not elevated to module level) to minimize diff scope. The manager's `get_async_credential()` returns the shared `AsyncDefaultAzureCredential` instance — `.get_token()` works identically.
- **Tests go GREEN immediately:** `AzureSDKManager.get_credential()` caching was implemented in Plan 03-01. Tests 10-11 verify the existing singleton contract rather than driving new implementation — this is consistent with integration-style TDD for pre-built components.

## Deviations from Plan

None - plan executed exactly as written.

The plan noted `monitor_agent.py` used `AsyncDefaultAzureCredential` at "~line 479" — confirmed at line 479. `domain_sub_agent.py` at "~line 254" — confirmed at line 253-254. Both matched plan spec precisely.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Agent credential migration complete. All 6 agents now share a single credential instance.
- PRF-03, NFR-PRF-03, NFR-PRF-04, NFR-SCL-01 requirements fulfilled.
- Ready for **03-04-PLAN.md** — Cache TTL standardization + async timeout guards.
- Ready for **03-05-PLAN.md** — Phase 3 validation: regression tests, integration tests.

---

## Self-Check: PASSED

- ✅ `git log --oneline --grep="03-02"` returns 2 commits (`de8cd86`, `abfe85f`)
- ✅ All 6 agents contain `get_azure_sdk_manager` — verified by grep
- ✅ No `AsyncDefaultAzureCredential()` instantiations remain in monitor_agent.py or domain_sub_agent.py
- ✅ 17 tests pass in `test_azure_client_manager.py`
- ✅ 1203 unit tests pass (zero new regressions)

---
*Phase: 03-performance-optimizations-days-8-10*
*Completed: 2026-03-01*
