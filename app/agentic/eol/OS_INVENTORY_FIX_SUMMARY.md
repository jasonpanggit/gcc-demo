# OS Inventory PostgreSQL Persistence Fix

## Problem Summary
Arc-enabled servers (WIN-JBC7MM2NO8J and WIN-P3OD2Q85TKG) don't have OS data for CVE scanning because:
1. The `os_inventory_snapshots` table had the wrong schema (wrong PK)
2. The cache logic prevented storing data when `force_refresh=True`
3. The `last_heartbeat` datetime wasn't being parsed correctly

## Root Causes

### 1. Schema Mismatch
**Deployed schema:** PK was `(workspace_id, lookback_days, computer_name)` with 26 columns
**Expected schema:** PK should be `(resource_id, snapshot_version, workspace_id)` per migration 030
**Impact:** The JOIN in `sync_vms_os_data_from_snapshots()` failed because it needs `resource_id`

### 2. Cache Logic Bug
**Location:** `agents/os_inventory_agent.py` line 553
**Issue:** `if use_cache and results:` prevented caching when `force_refresh=True` (which sets `use_cache=False`)
**Fix:** Changed to `if results:` to always cache fresh data

### 3. Datetime Parsing Issue
**Location:** `utils/inventory_cache.py`
**Issue:** `last_heartbeat` from LAW is a string but PostgreSQL expects datetime
**Fix:** Added `datetime.fromisoformat()` parsing

## Files Changed

### 1. migrations/fix_os_inventory_snapshots_schema.sql (NEW)
- Drops existing table with CASCADE
- Recreates with correct schema from migration 030
- Restores FK to vms table
- Recreates indexes
- Includes verification queries

### 2. agents/os_inventory_agent.py
**Line 553:** Changed from `if use_cache and results:` to `if results:`
**Reason:** Always cache fresh data, regardless of `use_cache` flag

### 3. utils/inventory_cache.py
**Lines 210-217:** Added datetime parsing for `last_heartbeat`
**Lines 220-245:** Fixed INSERT statement to match migration 030 schema
- Removed `lookback_days` and `payload` columns
- Fixed PK columns in ON CONFLICT clause
- Added comprehensive debug logging

### 4. utils/pg_database.py
**Lines 568-580:** Removed ALTER TABLE workarounds
**Reason:** Proper schema fix makes these unnecessary

## Deployment Steps

1. **Run schema fix SQL:**
   ```bash
   cd app/agentic/eol/deploy
   ./connect-postgres.sh ../migrations/fix_os_inventory_snapshots_schema.sql
   ```

2. **Deploy updated code:**
   ```bash
   ./deploy-container.sh
   ```

3. **Trigger OS inventory refresh:**
   ```bash
   curl "https://agentic-aiops-demo.jollymushroom-e4a001e7.southeastasia.azurecontainerapps.io/api/inventory/raw/os?force_refresh=true"
   ```

4. **Verify data in PostgreSQL:**
   ```sql
   SELECT COUNT(*) FROM os_inventory_snapshots;
   SELECT resource_id, computer_name, os_name, os_version FROM os_inventory_snapshots;
   ```

5. **Sync vms table with snapshot data:**
   ```sql
   -- This will populate os_name and os_type for Arc VMs
   UPDATE vms
   SET
       os_name = COALESCE(osi.os_name, vms.os_name),
       os_type = COALESCE(osi.os_type, vms.os_type)
   FROM os_inventory_snapshots osi
   WHERE vms.resource_id = osi.resource_id
     AND (vms.os_name IS NULL OR vms.os_name = 'Unknown'
          OR vms.os_type IS NULL OR vms.os_type = 'Unknown');
   ```

## Expected Results

After deployment:
- `os_inventory_snapshots` should have 2 rows (the Arc servers)
- `vms` table should have os_name and os_type populated for Arc servers via JOIN
- CVE scanning should work for all 8 VMs (6 Azure + 2 Arc)

## Testing
```bash
# Check snapshot data
SELECT * FROM os_inventory_snapshots;

# Check vms table Arc servers
SELECT resource_id, vm_name, os_name, os_type
FROM vms
WHERE resource_id LIKE '%HybridCompute%';

# Run CVE scan
curl -X POST "https://.../api/cve/scan"
```
