# Summary: PostgreSQL-Backed Persistent Vendor EOL Cache

**ID:** 260323-hgs
**Status:** COMPLETE
**Branch:** `quick/260323-hgs-pg-eol-inventory`
**Commits:** 4

---

## What Changed

`EolInventory` was an in-memory-only store (`self._store` dict). All EOL data was lost on app restart despite the `eol_records` table already existing in PostgreSQL with the correct schema. This task added L2 PostgreSQL read-through/write-through to bridge the gap.

## Files Modified

| File | Change |
|------|--------|
| `app/agentic/eol/utils/eol_inventory.py` | L2 PG read-through in `get()`, fire-and-forget write in `upsert()`, `list_by_vendor()`, `_extract_vendor()`, `_pg_get()`, `_pg_upsert()`, `_pg_row_to_doc()`, pool injection |
| `app/agentic/eol/main.py` | Inject `postgres_client.pool` into `eol_inventory._pool` before `initialize()` |
| `app/agentic/eol/api/eol.py` | New `GET /api/eol-inventory/vendor/{vendor}` endpoint; fixed route ordering |
| `app/agentic/eol/utils/pg_database.py` | Added `idx_eol_vendor` to bootstrap DDL |
| `app/agentic/eol/migrations/038_eol_vendor_index.sql` | New migration for vendor index + backfill |

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 173126f | Add L2 PostgreSQL read-through/write-through to EolInventory |
| 2 | 6e2abb4 | Wire PG pool injection and add vendor-scoped EOL query endpoint |
| 3 | 070837d | Add vendor column index for vendor-scoped EOL queries |
| 4 | fbf91b0 | Fix vendor route ordering to prevent path parameter conflict |

## Architecture

```
                        L1 dict (fast)         L2 PostgreSQL (persistent)
                       +-----------+           +------------------+
get(name, ver) ------->| _store    |--miss---->| eol_records      |--hit--> promote to L1
                       | hit: O(1) |           | SELECT ... LIMIT |
                       +-----------+           +------------------+

upsert(name, ver) --> write L1 synchronously --> fire-and-forget async L2 write
                       confidence gate in L1      ON CONFLICT confidence gate in PG
```

## Key Design Decisions

1. **Fire-and-forget L2 writes**: `asyncio.ensure_future()` so L1 upsert is never blocked by PG latency
2. **Confidence-gated ON CONFLICT**: PG upsert only overwrites if incoming `confidence >= existing`
3. **3s timeout on L2 reads**: `asyncio.wait_for(timeout=3.0)` prevents slow PG from degrading `get()` latency
4. **Vendor extraction heuristic**: `_extract_vendor()` maps agent_used/source/software_name to vendor for the `vendor` column
5. **Route ordering fix**: `/api/eol-inventory/vendor/{vendor}` placed before `/{software_key}` to prevent FastAPI path parameter conflict

## Verification Checklist

- [x] All 4 files pass syntax check (`ast.parse()`)
- [x] External API surface unchanged (`get`, `upsert`, `list_recent`, `get_stats`, etc. all preserved)
- [x] `list_by_vendor()` added as new public method
- [x] Pool not available at import time -- lazy initialization in `initialize()` or explicit injection
- [x] L2 failures logged and swallowed -- never break L1 behavior
- [x] Confidence-gated upsert in PG via `WHERE ... EXCLUDED.confidence >= eol_records.confidence`
- [x] Route ordering: vendor route precedes catch-all `{software_key}` route
- [x] Migration file 038 created for existing deployments
- [x] Bootstrap DDL updated for fresh deployments

## Risks Mitigated

| Risk | Mitigation |
|------|------------|
| Pool not ready at first `get()`/`upsert()` | `_has_pool()` guard on every L2 call; lazy acquisition in `initialize()` |
| Slow PG queries blocking orchestrator | 3s timeout on L2 reads; fire-and-forget on writes |
| Schema mismatch | Explicit column mapping in `_pg_upsert()`; cast eol_date to `::date` |
| Route parameter conflict | Vendor route defined before `{software_key}` catch-all |
