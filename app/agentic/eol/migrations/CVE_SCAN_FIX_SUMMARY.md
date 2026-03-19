# CVE Scan Fix Summary

## Root Causes Identified

### 1. CVE Search Query Issues (FIXED)

**Problem 1: tsquery format**
- Line 171 in `cve_repository.py` used `to_tsquery('english', $1)`
- Scanner passes plain text like `"windows server 2016"`
- `to_tsquery` expects formatted operators like `'windows & server & 2016'`
- This causes the query to **fail silently** returning 0 results

**Fix**: Changed to `plainto_tsquery('english', $1)` which auto-converts plain text

**Problem 2: JSONB vendor/product matching**
- Line 174-175 used `affected_products @> jsonb_build_object('vendor', $4)`
- This expects exact key-value match in a single JSONB object
- But `affected_products` is a JSONB **array** of product objects
- Need to iterate through array elements

**Fix**: Changed to:
```sql
EXISTS (
  SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
  WHERE product->>'vendor' ILIKE $4
)
```

### 2. Overview Showing 0 VMs (DEPENDENCY ISSUE)

**Problem**:
- Overview reads from `mv_vm_vulnerability_posture` materialized view
- This view is populated from scan results stored in `vm_cve_matches`
- Since scan returns 0 matches, the view is empty → overview shows 0 VMs

**Status**: Will be fixed automatically once scan works

## Files Changed

1. `/Users/jasonmba/workspace/gcc-demo/app/agentic/eol/utils/repositories/cve_repository.py`
   - Modified `QUERY_SEARCH_CVES` (lines 164-181)
   - Modified `QUERY_COUNT_CVES` (lines 184-195)

## Testing Required

1. **Restart container app** to load new query code
2. **Run CVE scan** via cve-inventory.html "Scan VMs" button
3. **Verify**:
   - Scan should find CVE matches for Windows Server 2016 and 2025 VMs
   - Logs should show actual CVE counts
   - Overview should populate with VM data

## Expected Behavior After Fix

Before:
```
✅ 8 VMs collected
🔍 Scanning 8 VMs for CVE matches...
   0 VMs matched 0 CVEs
```

After:
```
✅ 8 VMs collected
🔍 Scanning 8 VMs for CVE matches...
   8 VMs matched ~50+ CVEs
```

## Deployment Command

```bash
cd /Users/jasonmba/workspace/gcc-demo/app/agentic/eol
./deploy/deploy-container.sh
```

## SQL Query Comparison

### Before (BROKEN):
```sql
WHERE c.search_vector @@ to_tsquery('english', 'windows server 2016')
  -- FAILS: expects 'windows & server & 2016' format

  AND c.affected_products @> jsonb_build_object('vendor', 'microsoft')
  -- FAILS: expects single object, not array
```

### After (FIXED):
```sql
WHERE c.search_vector @@ plainto_tsquery('english', 'windows server 2016')
  -- WORKS: auto-converts plain text to proper tsquery

  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(c.affected_products) AS product
    WHERE product->>'vendor' ILIKE 'microsoft'
  )
  -- WORKS: iterates through array, case-insensitive match
```

## Related Issues Fixed

- ✅ Fixed tsquery syntax error
- ✅ Fixed JSONB array matching for vendor/product filters
- ⏳ Overview 0 VMs (will auto-fix once scan populates data)

## Verification Steps

1. Deploy container app
2. Wait for healthy status
3. Navigate to cve-inventory.html
4. Click "Scan VMs"
5. Check logs for match count > 0
6. Navigate to overview page
7. Verify VMs appear in vulnerability posture table
