---
phase: 03-performance-optimizations-days-8-10
plan: "04"
subsystem: caching
tags: [cache, ttl, asyncio, cosmos, timeout, centralization]

# Dependency graph
requires:
  - phase: 03-performance-optimizations-days-8-10
    provides: TimeoutConfig (db_query_timeout) and fire-and-forget pattern from plans 03-01 through 03-03
provides:
  - utils/cache_config.py: CacheTTLProfile enum, get_ttl(), TTL_PROFILE_MAP — single TTL source of truth
  - sre_cache.py: TTL_PROFILES now references TTL_PROFILE_MAP (no hardcoded seconds)
  - eol_orchestrator.py: Cosmos reads guarded by asyncio.wait_for(db_query_timeout)
affects: [03-05, cache-related modules, any future code needing TTL constants]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Centralized TTL constants: all cache durations import from utils/cache_config.py"
    - "IntEnum with os.getenv defaults: env-overridable enum values"
    - "asyncio.wait_for pattern for Cosmos reads with fallback to cache miss on timeout"

key-files:
  created:
    - app/agentic/eol/utils/cache_config.py
    - app/agentic/eol/tests/unit/test_cache_config.py
  modified:
    - app/agentic/eol/utils/sre_cache.py
    - app/agentic/eol/agents/eol_orchestrator.py
    - app/agentic/eol/tests/test_sre_cache.py

key-decisions:
  - "TTL_PROFILE_MAP covers both canonical CacheTTLProfile names and legacy SreCache profile names for backward-compatible incremental migration"
  - "real_time TTL changed from 60s to 300s (EPHEMERAL tier) — 60s was too aggressive for cache round-trips per PRF-06"
  - "medium TTL changed from 1800s to 900s (SHORT_LIVED_TTL = 15 min) — aligns SreCache medium tier with standard SHORT_LIVED profile"
  - "_app_config imported via try/except with None fallback so eol_orchestrator functions in environments without config module"
  - "asyncio.wait_for fallback timeout is 10.0s when config unavailable (matches db_query_timeout default)"

patterns-established:
  - "TTL centralization: import CacheTTLProfile or EPHEMERAL_TTL/SHORT_LIVED_TTL etc from utils.cache_config"
  - "Cosmos read guard: wrap await cosmos_client.get() in asyncio.wait_for(timeout=_app_config.timeouts.db_query_timeout)"

requirements-completed:
  - PRF-06
  - PRF-07
  - PRF-08
  - NFR-SCL-04

# Metrics
duration: 16min
completed: 2026-03-01
---

# Phase 3 Plan 04: Cache TTL Centralization + Async Timeout Guards Summary

**Centralized all cache TTL magic numbers into `utils/cache_config.py` (CacheTTLProfile enum + TTL_PROFILE_MAP), updated SreCache to reference it, and added asyncio.wait_for() timeout guard to Cosmos DB reads in eol_orchestrator**

## Performance

- **Duration:** 16 min
- **Started:** 2026-03-01T08:51:28Z
- **Completed:** 2026-03-01T09:07:19Z
- **Tasks:** 2 (Task 1 TDD: 3 commits; Task 2: 1 commit)
- **Files modified:** 5

## Accomplishments

- Created `utils/cache_config.py` as single source of truth for all cache TTL values — eliminates scattered magic numbers (300, 900, 3600 seconds) across 6+ cache files
- Updated `SRECacheManager.TTL_PROFILES` to reference `TTL_PROFILE_MAP` from cache_config — one-line TTL tuning per tier via env vars
- Added `asyncio.wait_for()` timeout guard to `eol_inventory.get()` Cosmos read in `eol_orchestrator.py` — prevents indefinite blocking on DB reads
- 13 new unit tests for `cache_config.py` (all passing), 0 regressions in existing test suite

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for CacheTTLProfile** - `9e4bba2` (test)
2. **Task 1 GREEN: Implement cache_config.py** - `e6b8d08` (feat)
3. **Task 2: Centralize SreCache TTL + Cosmos timeout guard** - `2bf8a81` (feat)

**Plan metadata:** `8629cd1` (docs: complete plan)

_Note: TDD Task 1 produced 2 commits (test → feat). No REFACTOR needed — implementation was clean._

## Self-Check: PASSED

- ✅ `utils/cache_config.py` exists on disk
- ✅ `tests/unit/test_cache_config.py` exists on disk
- ✅ 4 commits with `03-04` reference found in git log

## Files Created/Modified

- `app/agentic/eol/utils/cache_config.py` — NEW: CacheTTLProfile IntEnum, module constants (EPHEMERAL_TTL etc), get_ttl() helper, TTL_PROFILE_MAP dict
- `app/agentic/eol/tests/unit/test_cache_config.py` — NEW: 13 unit tests (enum values, constants, get_ttl, env var override)
- `app/agentic/eol/utils/sre_cache.py` — Updated: replaced hardcoded TTL_PROFILES dict with `TTL_PROFILE_MAP` import from cache_config; updated TOOL_TTL_MAP comments to reflect new tier names
- `app/agentic/eol/agents/eol_orchestrator.py` — Updated: added `_app_config` import; wrapped `await eol_inventory.get()` in `asyncio.wait_for()` with `db_query_timeout`
- `app/agentic/eol/tests/test_sre_cache.py` — Updated: TTL value assertions updated to use `EPHEMERAL_TTL`/`SHORT_LIVED_TTL` constants; `test_ttl_profiles_ascending_order` replaced with `test_ttl_profiles_tiered_order` (real_time and short share EPHEMERAL tier at 300s)

## Decisions Made

1. **TTL_PROFILE_MAP covers both canonical and legacy names** — The plan showed TTL_PROFILE_MAP as a dict covering legacy SreCache profile names (real_time, short, medium, long). Added `daily` key (86400s = LONG_LIVED) since sre_cache had a 5th `"daily"` profile not in the plan's template. This ensures drop-in replacement with no lookup failures.

2. **real_time changed 60s → 300s, medium changed 1800s → 900s** — Per plan: 60s is too aggressive for cache round-trips. The SHORT_LIVED tier (15 min) better fits "config analysis, costs" than 30 min (old medium). Test updated with explanatory comment documenting this intentional change.

3. **`_app_config` imported via try/except with `None` fallback** — eol_orchestrator uses a bare `try/except ImportError` pattern for all its utils imports. Adding config as `_app_config` with a `None` fallback keeps the pattern consistent and allows mock-data mode (no Azure/config) to work.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `daily` key to TTL_PROFILE_MAP**
- **Found during:** Task 2 (updating sre_cache.py)
- **Issue:** Plan's TTL_PROFILE_MAP template had 4 legacy keys (real_time, short, medium, long) but existing sre_cache.py TTL_PROFILES had a 5th key `"daily": 86400`. Replacing TTL_PROFILES with a map missing `"daily"` would cause `set()` to silently skip caching for all daily-mapped tools (security_score, check_compliance_status, etc.)
- **Fix:** Added `"daily": LONG_LIVED_TTL` to TTL_PROFILE_MAP in cache_config.py
- **Files modified:** app/agentic/eol/utils/cache_config.py
- **Verification:** All 36 sre_cache tests pass including daily-TTL tool mapping tests
- **Committed in:** `e6b8d08` (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Auto-fix necessary for correctness — without `daily` key, 5 daily-TTL tools would silently lose caching. No scope creep.

## Issues Encountered

- Pre-existing test failures (not caused by this plan): `test_cli_executor_safety.py` (FastMCP API version), `test_sre_orchestrator.py` (mcp module not installed), `test_alerts_api.py` (pymsteams not installed), `test_cosmos_cache.py` (2 async tests missing asyncio mark). All confirmed pre-existing via `git stash` verification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 5 plan success criteria met
- `cache_config.py` exports are available for any cache module needing standardized TTLs
- Zero regressions introduced
- Ready for **03-05-PLAN.md** — Phase 3 validation: regression tests, integration tests

---
*Phase: 03-performance-optimizations-days-8-10*
*Completed: 2026-03-01*
