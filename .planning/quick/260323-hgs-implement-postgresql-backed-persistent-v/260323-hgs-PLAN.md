# Quick Plan: PostgreSQL-Backed Persistent Vendor EOL Cache

**ID:** 260323-hgs
**Created:** 2026-03-23
**Status:** PLANNED

---

## Problem

`EolInventory` (`utils/eol_inventory.py`) is an **in-memory-only** store. All EOL data is lost on restart. The `eol_records` table in PostgreSQL already exists with the correct schema (via `pg_database.py` bootstrap and `repositories/eol_repository.py`), but `EolInventory` never reads from or writes to it. The result: vendor parsing workflows that populate the cache via `eol_inventory.upsert()` lose all data on app restart, and there's no way to query "all Microsoft products" from persistent storage.

## Current Architecture

```
eol_orchestrator.py ──> eol_inventory.get()  ──> self._store (dict)  ──> miss
                    ──> eol_inventory.upsert() ──> self._store (dict) ──> lost on restart
```

- `EolInventory._store`: `Dict[str, Dict[str, Any]]` — pure in-memory
- `eol_records` table: already has `software_key` PK, `vendor`, `confidence`, `source`, `raw_response` JSONB, etc.
- `EOLRepository` (`repositories/eol_repository.py`): already has `get_by_key()`, `upsert_eol_record()`, `list_records()` — but only used by the admin API routes, NOT by `EolInventory`

## Target Architecture

```
eol_orchestrator.py ──> eol_inventory.get()  ──> L1 dict ──hit──> return
                                              ──miss──> L2 Postgres (eol_records) ──hit──> populate L1, return
                                              ──miss──> None

                    ──> eol_inventory.upsert() ──> L1 dict + L2 Postgres (fire-and-forget write)
```

## Tasks

### Task 1: Add L2 PostgreSQL read/write to EolInventory

**Files changed:**
- `app/agentic/eol/utils/eol_inventory.py` — main changes

**Changes:**

1. **Add Postgres pool injection** to `EolInventory.__init__()`:
   - Accept optional `pool: asyncpg.Pool` parameter
   - Store as `self._pool`
   - In `initialize()`, try to acquire pool from `pg_client.postgres_client` if not injected

2. **Extend `get()` with L2 read-through**:
   - After L1 miss (`self._store.get()` returns None), query `eol_records` by `software_key` + `version_key`
   - Use a private `_pg_get()` method with parameterized query:
     ```sql
     SELECT * FROM eol_records
     WHERE software_key = $1
       AND ($2::text IS NULL OR version_key = $2)
     LIMIT 1;
     ```
   - On L2 hit: convert row to `EolRecord` dict, populate L1, return `to_cached_response()`
   - On L2 miss: return None (existing behavior)
   - Wrap in try/except — L2 failure must not break L1-only behavior

3. **Extend `upsert()` with L2 write-through**:
   - After successful L1 write, fire-and-forget an async write to `eol_records`
   - Use a private `_pg_upsert()` method mapping `EolRecord` fields to `eol_records` columns:
     - `software_key`, `software_name`, `version_key`, `version`, `eol_date`, `status`, `risk_level`, `confidence`, `source`, `item_type`, `normalized_software_name`, `normalized_version`, `vendor` (extract from source/agent_used), `raw_response` (JSONB of full `data` dict)
   - Use `INSERT ... ON CONFLICT (software_key) DO UPDATE` with confidence-gated update (only update if incoming confidence >= existing)
   - Wrap in try/except — L2 failure must not break L1 write

4. **Add vendor-scoped query** `list_by_vendor()`:
   - New async method: `async def list_by_vendor(self, vendor: str, *, limit=100, offset=0) -> tuple[list, int]`
   - Queries `eol_records WHERE vendor ILIKE $1 OR source ILIKE $1`
   - Returns list of record summaries + total count
   - Falls back gracefully if pool not available

5. **Add `_extract_vendor()` helper**:
   - Derive vendor name from `source`, `agent_used`, or `software_name` fields
   - Simple mapping: "endoflife.date" -> extract from product name, "microsoft_agent" -> "Microsoft", etc.
   - Used during upsert to populate the `vendor` column

**Key constraints:**
- `eol_inventory = EolInventory()` singleton at module bottom stays unchanged
- All existing callers (`eol_inventory.get()`, `.upsert()`, `.list_recent()`, etc.) continue working
- Pool not available at import time — lazy initialization in `initialize()` or first use
- L2 failures are logged and swallowed — never break L1 behavior

### Task 2: Wire up initialization and expose vendor query in API

**Files changed:**
- `app/agentic/eol/main.py` — inject pool into eol_inventory during startup
- `app/agentic/eol/api/eol.py` — add vendor-scoped query endpoint

**Changes in `main.py`:**
1. After `postgres_client.initialize()` and before `eol_inventory.initialize()`, inject the pool:
   ```python
   eol_inventory._pool = postgres_client.pool
   await eol_inventory.initialize()
   ```

**Changes in `api/eol.py`:**
1. Add `GET /api/eol-inventory/vendor/{vendor}` endpoint:
   - Calls `eol_inventory.list_by_vendor(vendor, limit=limit, offset=offset)`
   - Returns `StandardResponse.success_response(data={"items": records, "total": total, "vendor": vendor})`
   - Uses `@readonly_endpoint` decorator

### Task 3: Add migration for vendor column index

**Files changed:**
- `app/agentic/eol/migrations/034_eol_vendor_index.sql` (new file)

**SQL:**
```sql
-- Add index on vendor column for vendor-scoped queries
CREATE INDEX IF NOT EXISTS idx_eol_vendor ON eol_records (LOWER(vendor));
-- Backfill vendor from source where possible
UPDATE eol_records SET vendor = source WHERE vendor IS NULL AND source IS NOT NULL;
```

Also update `pg_database.py` bootstrap to include the index creation for fresh deployments.

---

## Verification

- [ ] Existing tests pass (run_tests.sh)
- [ ] `eol_inventory.get("python", "3.9")` reads from Postgres on L1 miss
- [ ] `eol_inventory.upsert(...)` writes to both L1 dict and `eol_records` table
- [ ] `eol_inventory.list_by_vendor("Microsoft")` returns vendor-scoped results
- [ ] App starts correctly with pool injection
- [ ] App starts correctly WITHOUT Postgres (graceful degradation)
- [ ] Confidence-gated upsert: lower confidence does not overwrite higher in Postgres

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Pool not ready at first `get()`/`upsert()` | LOW | Lazy pool acquisition in each method with try/except |
| Slow Postgres queries blocking orchestrator | MEDIUM | Use `asyncio.wait_for()` with timeout on L2 reads; fire-and-forget on writes |
| Schema mismatch between EolRecord fields and eol_records columns | LOW | Explicit column mapping in `_pg_upsert()`; ignore extra fields |
