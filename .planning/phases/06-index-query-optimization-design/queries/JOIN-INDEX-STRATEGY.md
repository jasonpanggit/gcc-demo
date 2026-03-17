# Cross-Table JOIN Index Strategy (Covering, FK, Expression, Redundancy)

**Phase:** 06-index-query-optimization-design (Plan 06-03)
**Requirements:** QRY-01, QRY-03
**Generated:** 2026-03-17
**Sources:** INDEX-AUDIT.md (P2.6), UNIFIED-SCHEMA-SPEC.md (P5.7), CVE-TABLES.md (P5.2), VM-IDENTITY-SPINE.md (P5.1), ALERTING-TABLES.md (P5.5), 06-RESEARCH.md, SEARCH-INDEX-STRATEGY.md (P6.1)

---

## Section 1: GAP-03 + GAP-04 Resolution -- kb_cve_edges Composite

### Index Definition

```sql
CREATE INDEX IF NOT EXISTS idx_edges_cve_source ON kb_cve_edges (cve_id, source);
```

**Type:** Composite B-tree (2 columns)
**Priority:** MEDIUM
**Status:** NEW -- Phase 7 migration 032 + bootstrap DDL

### Query Patterns Served

This single composite index resolves both GAP-03 (`kb_cve_edges.source` no standalone index) and GAP-04 (`kb_cve_edges.cve_id` no standalone index) from INDEX-AUDIT.md (P2.6). Three documented query patterns are served:

1. **get_advisories_for_cve** -- Advisory lookup by CVE + source:
   ```sql
   SELECT * FROM kb_cve_edges WHERE cve_id = $1 AND source = $2 ORDER BY kb_number
   ```

2. **get_kbs_for_cve** -- Microsoft KB articles for a CVE:
   ```sql
   SELECT * FROM kb_cve_edges WHERE cve_id = $1 AND source = 'microsoft'
   ```

3. **get_fixed_packages_for_cve** -- Linux fixed packages for a CVE:
   ```sql
   SELECT * FROM kb_cve_edges WHERE cve_id = $1 AND source IN ('ubuntu','redhat','debian')
   ```

### Column Ordering Rationale

`cve_id` is the leading key because all documented query patterns filter by `cve_id` first. PostgreSQL B-tree descends to `cve_id` leaf pages, then scans `source` values within that `cve_id` bucket. This ordering is optimal for the equality-on-cve_id + equality/IN-on-source pattern.

### GAP-03 Note

A standalone `idx_edges_source ON kb_cve_edges (source)` is NOT created. The composite covers the dominant `(cve_id, source)` pattern. Standalone source-only queries (bulk source statistics) are rare; if needed, revisit in Phase 10.

---

## Section 2: Covering Indexes (INCLUDE Columns for Index-Only Scans)

### Existing RETAINED Covering Indexes (No Changes)

| # | Index Name | Table | Key Columns | INCLUDE Columns | Purpose | Status |
|---|-----------|-------|-------------|-----------------|---------|--------|
| 1 | `idx_vmcvematch_cve_scan` | `vm_cve_match_rows` | `(cve_id, scan_id)` | `(vm_id, vm_name, patch_status)` | CVE-to-VM lookup: returns VM identity + patch status without heap access | RETAINED |
| 2 | `idx_vmcvematch_vm_scan` | `vm_cve_match_rows` | `(vm_id, scan_id)` | `(cve_id, severity, cvss_score, patch_status)` | VM-to-CVE detail: returns CVE severity data without heap access | RETAINED |

### New Covering Indexes

| # | Index Name | Table | Key Columns | INCLUDE Columns | DDL | Purpose | Phase 7 Action |
|---|-----------|-------|-------------|-----------------|-----|---------|---------------|
| 3 | `idx_cves_severity_covering` | `cves` | `(cvss_v3_severity)` | `(cve_id, cvss_v3_score, published_at)` | `CREATE INDEX IF NOT EXISTS idx_cves_severity_covering ON cves (cvss_v3_severity) INCLUDE (cve_id, cvss_v3_score, published_at);` | cve-database severity filter returns display columns without heap access; serves `SELECT cve_id, cvss_v3_score, published_at FROM cves WHERE cvss_v3_severity = $1` as index-only scan | Migration 032 + bootstrap |
| 4 | `idx_alerthistory_rule_covering` | `cve_alert_history` | `(rule_id)` | `(cve_id, severity, fired_at)` | `CREATE INDEX IF NOT EXISTS idx_alerthistory_rule_covering ON cve_alert_history (rule_id) INCLUDE (cve_id, severity, fired_at);` | Alert history per-rule query: `SELECT cve_id, severity, fired_at FROM cve_alert_history WHERE rule_id = $1` as index-only scan | Migration 031 + bootstrap |

### Deferred Covering Index

`idx_vms_subscription_covering ON vms (subscription_id) INCLUDE (vm_name, os_name, os_type, location)` was evaluated but deferred. At 100-500 VMs, heap random I/O is negligible. Write amplification on the upsert-heavy `vms` table outweighs index-only scan benefit at current scale. Phase 10 should profile and add if >1000 VMs or heap random I/O becomes measurable.

---

## Section 3: FK Join Indexes -- New Foreign Key Verification

Phase 5 added 11 FK constraints (UNIFIED-SCHEMA-SPEC.md `_REQUIRED_RELATIONS`). Every FK child column must have a supporting index for efficient JOIN performance and to prevent table locks on parent DELETE/UPDATE. Verification results:

| # | FK Name | Child Table | Child Column | Parent Table | Parent Column | Supporting Index | Index Source | Status |
|---|---------|-------------|--------------|-------------|---------------|-----------------|-------------|--------|
| 1 | `fk_vms_subscription` | `vms` | `subscription_id` | `subscriptions` | `subscription_id` | `idx_vms_subscription ON vms (subscription_id)` | Migration 028 | EXISTS |
| 2 | `fk_vmcvematch_vm` | `vm_cve_match_rows` | `vm_id` | `vms` | `resource_id` | `idx_vmcvematch_vm_scan ON vm_cve_match_rows (vm_id, scan_id) INCLUDE (...)` | Bootstrap | EXISTS (covering index serves as FK index) |
| 3 | `fk_vmcvematch_cve` | `vm_cve_match_rows` | `cve_id` | `cves` | `cve_id` | `idx_vmcvematch_cve_scan ON vm_cve_match_rows (cve_id, scan_id) INCLUDE (...)` | Bootstrap | EXISTS (covering index serves as FK index) |
| 4 | `fk_patchcache_vm` | `patch_assessments_cache` | `resource_id` | `vms` | `resource_id` | `idx_patch_cache_resource_id ON patch_assessments_cache (resource_id)` | Migration 011 | EXISTS |
| 5 | `fk_availpatches_vm` | `available_patches` | `resource_id` | `vms` | `resource_id` | `idx_patches_resource_id ON available_patches (resource_id)` | Migration 011 | EXISTS |
| 6 | `fk_osinvsnap_vm` | `os_inventory_snapshots` | `resource_id` | `vms` | `resource_id` | `idx_os_inventory_snapshots_resource_id ON os_inventory_snapshots (resource_id)` | Bootstrap | EXISTS |
| 7 | `fk_cvevmdet_vm` | `cve_vm_detections` | `resource_id` | `vms` | `resource_id` | `idx_cve_vm_resource_id ON cve_vm_detections (resource_id)` | Migration 011 | EXISTS |
| 8 | `fk_cvevmdet_cve` | `cve_vm_detections` | `cve_id` | `cves` | `cve_id` | `idx_cve_vm_cve_id ON cve_vm_detections (cve_id)` | Migration 011 | EXISTS |
| 9 | `fk_arcswinv_vm` | `arc_software_inventory` | `resource_id` | `vms` | `resource_id` | `idx_arc_sw_inventory_resource_id ON arc_software_inventory (resource_id)` | Migration 011 | EXISTS |
| 10 | `fk_alerthistory_rule` | `cve_alert_history` | `rule_id` | `cve_alert_rules` | `rule_id` | `idx_alerthistory_rule ON cve_alert_history (rule_id)` | Migration 031 | EXISTS |
| 11 | `fk_alerthistory_cve` | `cve_alert_history` | `cve_id` | `cves` | `cve_id` | `idx_alerthistory_cve ON cve_alert_history (cve_id)` | Migration 031 | EXISTS |

**Result: All 11 FK child columns have supporting indexes. No new FK indexes needed.**

### Covering Indexes as FK Support

FK indexes #2 and #3 use covering indexes as their FK support. PostgreSQL uses the leading key of a covering index for FK validation during parent DELETE/UPDATE. Since `vm_id` is the leading key of `idx_vmcvematch_vm_scan` and `cve_id` is the leading key of `idx_vmcvematch_cve_scan`, these serve double duty as both query-optimization and FK-support indexes.

---

## Section 4: Redundancy Resolution

### R-01: `idx_resource_inventory_normalized_os` vs `idx_resource_inventory_normalized`

- **Decision:** RETAIN BOTH -- deferred to Phase 10
- **Table:** `resource_inventory`
- **Full index:** `idx_resource_inventory_normalized_os ON resource_inventory (normalized_os_name, normalized_os_version)` -- no WHERE clause
- **Partial index:** `idx_resource_inventory_normalized ON resource_inventory (normalized_os_name, normalized_os_version) WHERE normalized_os_name IS NOT NULL`
- **Rationale:** `v_unified_vm_inventory` is deprecated (Phase 5.6, Phase 10 DROP target) but still used during Phase 9 transition. The partial index is preferred by queries that include the IS NOT NULL predicate. The full index covers queries without that predicate. After Phase 10 drops the view, reevaluate whether the full index can be removed.
- **Phase 7 action:** None
- **Phase 10 action:** DROP `idx_resource_inventory_normalized_os` if no query needs it without IS NOT NULL predicate
- **Phase 10 validation:** `EXPLAIN ANALYZE SELECT * FROM resource_inventory WHERE normalized_os_name = 'Windows Server 2022'` -- should use partial index if IS NOT NULL is implied

### R-02: `idx_edges_kb` vs PK Prefix on `kb_cve_edges`

- **Decision:** DROP `idx_edges_kb`
- **Table:** `kb_cve_edges`
- **PK:** `(kb_number, cve_id, source)` -- `kb_number` is the leading key
- **Redundant index:** `idx_edges_kb ON kb_cve_edges (kb_number)` -- exact duplicate of PK leading key
- **Rationale:** PostgreSQL uses PK B-tree for `WHERE kb_number = $1` lookups because `kb_number` is the leading column of the composite PK. The standalone `idx_edges_kb` index is fully redundant -- it provides zero additional query paths but incurs write amplification on every INSERT/UPDATE/DELETE (and kb_cve_edges is UPSERT-heavy from MSRCKBCVESyncJob).
- **Phase 7 DDL:**
  ```sql
  DROP INDEX IF EXISTS idx_edges_kb;
  ```
  In migration 032.
- **Phase 10 validation:** `EXPLAIN ANALYZE SELECT * FROM kb_cve_edges WHERE kb_number = 'KB5001234'` should show PK index scan (not sequential scan)

---

## Section 5: Expression Indexes for Fuzzy JOINs

Cross-reference to SEARCH-INDEX-STRATEGY.md Section 4 for the BH-005 fuzzy JOIN indexes:

### Index Definitions (from P6.1)

```sql
-- NEW, Phase 7 migration 032
CREATE INDEX IF NOT EXISTS idx_vms_os_name_lower ON vms (LOWER(os_name));

-- NEW, Phase 7 migration 032
CREATE INDEX IF NOT EXISTS idx_eol_software_key_lower ON eol_records (LOWER(software_key));
```

These expression indexes are the primary mechanism for the bulk `vms LEFT JOIN eol_records ON LOWER(os_name) = LOWER(software_key)` pattern that replaces the N+1 EOL lookups (BH-005).

### JOIN Execution Plan Expectations

1. PostgreSQL recognizes `LOWER(column)` expression matches expression index
2. For nested-loop JOIN (likely given eol_records ~100-500 rows): outer scan on `vms`, inner index lookup on `idx_eol_software_key_lower`
3. For hash JOIN (possible at larger scale): both expression indexes provide pre-computed hash keys
4. Requires `ANALYZE vms; ANALYZE eol_records;` after data population for planner to recognize statistics

### Target SQL (from TARGET-SQL-INVENTORY-DOMAIN.md)

```sql
SELECT
  vm.resource_id, vm.vm_name, vm.os_name,
  e.is_eol, e.eol_date, e.software_name
FROM vms vm
LEFT JOIN eol_records e
  ON LOWER(vm.os_name) = LOWER(e.software_key)
WHERE vm.subscription_id = $1;
```

---

## Section 6: Complete JOIN Index Registry

Full summary table with all JOIN-related indexes:

| # | Index Name | Table | Type | Key Columns | INCLUDE Columns | Status | Phase 7 Action | Gap/Redundancy Resolved |
|---|-----------|-------|------|-------------|-----------------|--------|---------------|------------------------|
| 1 | `idx_edges_cve_source` | `kb_cve_edges` | Composite B-tree | `(cve_id, source)` | -- | NEW | Migration 032 + bootstrap | GAP-03, GAP-04 |
| 2 | `idx_vmcvematch_cve_scan` | `vm_cve_match_rows` | Covering B-tree | `(cve_id, scan_id)` | `(vm_id, vm_name, patch_status)` | RETAINED | None | -- |
| 3 | `idx_vmcvematch_vm_scan` | `vm_cve_match_rows` | Covering B-tree | `(vm_id, scan_id)` | `(cve_id, severity, cvss_score, patch_status)` | RETAINED | None | -- |
| 4 | `idx_cves_severity_covering` | `cves` | Covering B-tree | `(cvss_v3_severity)` | `(cve_id, cvss_v3_score, published_at)` | NEW | Migration 032 + bootstrap | -- |
| 5 | `idx_alerthistory_rule_covering` | `cve_alert_history` | Covering B-tree | `(rule_id)` | `(cve_id, severity, fired_at)` | NEW | Migration 031 + bootstrap | -- |
| 6 | `idx_vms_subscription` | `vms` | B-tree (FK) | `(subscription_id)` | -- | EXISTS | None (migration 028) | FK #1 |
| 7 | `idx_vmcvematch_vm_scan` | `vm_cve_match_rows` | Covering (FK) | `(vm_id, scan_id)` | `(cve_id, severity, ...)` | EXISTS | None (bootstrap) | FK #2 |
| 8 | `idx_vmcvematch_cve_scan` | `vm_cve_match_rows` | Covering (FK) | `(cve_id, scan_id)` | `(vm_id, vm_name, ...)` | EXISTS | None (bootstrap) | FK #3 |
| 9 | `idx_patch_cache_resource_id` | `patch_assessments_cache` | B-tree (FK) | `(resource_id)` | -- | EXISTS | None (migration 011) | FK #4 |
| 10 | `idx_patches_resource_id` | `available_patches` | B-tree (FK) | `(resource_id)` | -- | EXISTS | None (migration 011) | FK #5 |
| 11 | `idx_os_inventory_snapshots_resource_id` | `os_inventory_snapshots` | B-tree (FK) | `(resource_id)` | -- | EXISTS | None (bootstrap) | FK #6 |
| 12 | `idx_cve_vm_resource_id` | `cve_vm_detections` | B-tree (FK) | `(resource_id)` | -- | EXISTS | None (migration 011) | FK #7 |
| 13 | `idx_cve_vm_cve_id` | `cve_vm_detections` | B-tree (FK) | `(cve_id)` | -- | EXISTS | None (migration 011) | FK #8 |
| 14 | `idx_arc_sw_inventory_resource_id` | `arc_software_inventory` | B-tree (FK) | `(resource_id)` | -- | EXISTS | None (migration 011) | FK #9 |
| 15 | `idx_alerthistory_rule` | `cve_alert_history` | B-tree (FK) | `(rule_id)` | -- | EXISTS | None (migration 031) | FK #10 |
| 16 | `idx_alerthistory_cve` | `cve_alert_history` | B-tree (FK) | `(cve_id)` | -- | EXISTS | None (migration 031) | FK #11 |
| 17 | `idx_vms_os_name_lower` | `vms` | Expression B-tree | `LOWER(os_name)` | -- | NEW (from P6.1) | Migration 032 + bootstrap | BH-005 |
| 18 | `idx_eol_software_key_lower` | `eol_records` | Expression B-tree | `LOWER(software_key)` | -- | NEW (from P6.1) | Migration 032 + bootstrap | BH-005 |
| 19 | `idx_edges_kb` | `kb_cve_edges` | B-tree | `(kb_number)` | -- | DROP | Migration 032: `DROP INDEX IF EXISTS idx_edges_kb;` | R-02 |

### Summary Counts

- **New indexes: 3** (`idx_edges_cve_source`, `idx_cves_severity_covering`, `idx_alerthistory_rule_covering`)
- **Dropped indexes: 1** (`idx_edges_kb` -- R-02 redundancy)
- **Retained existing: 13** (2 covering + 11 FK support)
- **Expression indexes: 2** (cross-referenced from P6.1 for BH-005)
- **Net index change: +2** (3 new - 1 dropped)

### Phase 7 Migration Distribution

- **Migration 031** (Alerting tables): `idx_alerthistory_rule_covering` (created inline with redesigned `cve_alert_history` table)
- **Migration 032** (Optimization indexes): `idx_edges_cve_source`, `idx_cves_severity_covering`, `DROP INDEX idx_edges_kb`
- **Bootstrap DDL update:** All 3 new indexes added to `_bootstrap_runtime_schema()`

---

*Phase: 06-index-query-optimization-design*
*Plan: 06-03 (Gap Closure)*
*Generated: 2026-03-17*
