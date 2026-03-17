# Search Index Strategy (Full-Text, B-tree, GIN)

**Phase:** 06-index-query-optimization-design (Plan 06-01)
**Requirements:** QRY-01, QRY-03
**Generated:** 2026-03-17
**Sources:** INDEX-AUDIT.md (P2.6), 06-RESEARCH.md, UNIFIED-SCHEMA-SPEC.md (P5.7), pg_database.py bootstrap DDL, migrations 006/015

---

## Full-Text Search (GIN on tsvector)

### `idx_cves_fts`

- **DDL:**
  ```sql
  CREATE INDEX IF NOT EXISTS idx_cves_fts ON cves USING GIN (search_vector);
  ```
- **Type:** GIN on `tsvector`
- **Table:** `cves`
- **Column:** `search_vector` (tsvector, auto-populated by trigger)
- **Purpose:** Supports `search_vector @@ to_tsquery($1)` keyword search in `PostgresCVERepository._build_filters()`
- **Origin:** Migration 006 (`006_optimized_schema.sql` line 191) — NOT in bootstrap DDL
- **Query pattern:**
  ```sql
  SELECT cve_id, description, cvss_v3_score, cvss_v3_severity
  FROM cves
  WHERE search_vector @@ to_tsquery('english', $1)
  ORDER BY cvss_v3_score DESC
  LIMIT $2 OFFSET $3
  ```
- **Bootstrap gap:** Phase 7 must add this index AND the `search_vector` column AND trigger `trg_cves_search_vector_update` to bootstrap DDL. Currently these exist only on deployments that ran migration 006.
- **Trigger DDL (migration 006, needed in bootstrap):**
  ```sql
  CREATE OR REPLACE FUNCTION cves_search_vector_update() RETURNS trigger AS $$
  BEGIN
    NEW.search_vector := to_tsvector('english',
      COALESCE(NEW.cve_id, '') || ' ' ||
      COALESCE(NEW.description, '')
    );
    RETURN NEW;
  END $$ LANGUAGE plpgsql;

  CREATE TRIGGER trg_cves_search_vector_update
    BEFORE INSERT OR UPDATE ON cves
    FOR EACH ROW EXECUTE FUNCTION cves_search_vector_update();
  ```
- **Recommendation:** Phase 8 must replace all `ILIKE '%keyword%'` patterns with `search_vector @@ to_tsquery()` for user-facing keyword search. `ILIKE '%..%'` prevents index usage and forces sequential scans on 8,600+ CVE rows.

---

## GIN Indexes on JSONB Columns

GIN (Generalized Inverted Index) indexes on JSONB columns support containment operators (`@>`, `?`, `?|`, `?&`) and path queries. These enable efficient filtering without sequential scan of the JSONB blob.

| # | Index Name | Table | Column | DDL | Purpose |
|---|-----------|-------|--------|-----|---------|
| 1 | `idx_cves_products` | `cves` | `affected_products JSONB` | `CREATE INDEX IF NOT EXISTS idx_cves_products ON cves USING GIN (affected_products);` | JSONB containment for vendor/product filter: `affected_products @> '{"vendor": "microsoft"}'::jsonb`. Used by `mv_inventory_os_cve_counts` EXISTS cross-join and `_build_filters()` vendor/product predicates. |
| 2 | `idx_vms_tags` | `vms` | `tags JSONB` | `CREATE INDEX IF NOT EXISTS idx_vms_tags ON vms USING GIN (tags);` | Tag-based filtering: `tags @> '{"env": "prod"}'::jsonb`. Supports resource-group and environment-based VM filtering in inventory views. |

### Design Notes

- **`idx_cves_products`** is an existing bootstrap index (`pg_database.py` line 113). The `affected_products` column stores vendor/product associations as a JSONB array of objects. GIN supports both `@>` containment and `jsonb_path_exists()` queries.
- **`idx_vms_tags`** is a NEW index on the P5.1 `vms` table (`UNIFIED-SCHEMA-SPEC.md` migration 028). The `tags` column stores Azure resource tags as a flat JSONB object. GIN enables efficient tag-based VM filtering without sequential scan.

---

## GIN Indexes on Array Columns

GIN indexes on PostgreSQL array (`TEXT[]`) columns support the `@>` (contains), `<@` (is contained by), and `&&` (overlap) operators. The `= ANY()` operator can also benefit from GIN via the `@>` rewrite.

| # | Index Name | Table | Column | DDL | Purpose |
|---|-----------|-------|--------|-----|---------|
| 1 | `idx_cves_sources` | `cves` | `sources TEXT[]` | `CREATE INDEX IF NOT EXISTS idx_cves_sources ON cves USING GIN (sources);` | Array containment: `sources @> ARRAY[$1]` or `$1 = ANY(sources)`. Used by `_build_filters()` source predicate to filter CVEs by data source (nvd, msrc, etc.). |
| 2 | `idx_vmcvematch_kb_ids` | `vm_cve_match_rows` | `kb_ids TEXT[]` | `CREATE INDEX IF NOT EXISTS idx_vmcvematch_kb_ids ON vm_cve_match_rows USING GIN (kb_ids);` | KB-ID containment: `kb_ids @> ARRAY[$1]` to find all CVEs patched by a given KB. Used by patch remediation views to trace KB->CVE relationships within scan results. |

### Design Notes

- **`idx_cves_sources`** is an existing bootstrap index (`pg_database.py` line 112). The `sources` column is populated by NVD/MSRC sync jobs with values like `['nvd']`, `['msrc']`, `['nvd', 'msrc']`.
- **`idx_vmcvematch_kb_ids`** is an existing bootstrap index (`pg_database.py` line 499). The `kb_ids` column stores KB patch identifiers associated with each VM-CVE match row, enabling reverse lookups from KB to affected CVEs.

---

## Expression Indexes for Case-Insensitive Search

Expression indexes (also called functional indexes) pre-compute and index the result of an expression. For case-insensitive matching, `LOWER(column)` expression indexes allow the query planner to use an index scan for `WHERE LOWER(a) = LOWER(b)` JOINs instead of full table scans.

| # | Index Name | Table | Expression | DDL | Purpose |
|---|-----------|-------|-----------|-----|---------|
| 1 | `idx_vms_os_name_lower` | `vms` | `LOWER(os_name)` | `CREATE INDEX IF NOT EXISTS idx_vms_os_name_lower ON vms (LOWER(os_name));` | BH-005 fuzzy EOL JOIN: `LOWER(vms.os_name) = LOWER(eol_records.software_key)`. Enables bulk EOL lookup replacing N+1 HTTP calls with a single SQL query. Used by `mv_vm_vulnerability_posture` (migration 032). |
| 2 | `idx_eol_software_key_lower` | `eol_records` | `LOWER(software_key)` | `CREATE INDEX IF NOT EXISTS idx_eol_software_key_lower ON eol_records (LOWER(software_key));` | BH-005 inner side of fuzzy EOL JOIN. Both sides of the JOIN need expression indexes for the planner to use merge/hash join on the indexed expression. |
| 3 | `idx_inventory_sub_lower_type` | `resource_inventory` | `(subscription_id, LOWER(resource_type))` | `CREATE INDEX IF NOT EXISTS idx_inventory_sub_lower_type ON resource_inventory (subscription_id, LOWER(resource_type));` | Existing — case-insensitive `resource_type` filter: `WHERE subscription_id = $1 AND LOWER(resource_type) = $2`. Origin: migration 004 + bootstrap. |
| 4 | `idx_resource_inventory_name_lower` | `resource_inventory` | `LOWER(name)` | `CREATE INDEX IF NOT EXISTS idx_resource_inventory_name_lower ON resource_inventory (LOWER(name));` | Existing — case-insensitive name JOIN for `v_unified_vm_inventory`: `LOWER(ri.name) = LOWER(los.computer_name)`. Origin: migration 015. |
| 5 | `idx_os_inventory_computer_name_lower` | `os_inventory_snapshots` | `LOWER(computer_name)` | `CREATE INDEX IF NOT EXISTS idx_os_inventory_computer_name_lower ON os_inventory_snapshots (LOWER(computer_name));` | Existing — case-insensitive name JOIN for `v_unified_vm_inventory` CTE `latest_os`. Origin: migration 015. |

### BH-005 Fuzzy JOIN Pattern

The BH-005 bad hack (N+1 EOL lookups per unique OS in `inventory.html`) is resolved by a bulk SQL JOIN:

```sql
-- BH-005 bulk EOL lookup: replaces N+1 POST /api/search/eol calls
SELECT
  vm.resource_id,
  vm.vm_name,
  vm.os_name,
  e.is_eol,
  e.eol_date,
  e.software_name
FROM vms vm
LEFT JOIN eol_records e
  ON LOWER(vm.os_name) = LOWER(e.software_key)
WHERE vm.subscription_id = $1;
```

Both `idx_vms_os_name_lower` and `idx_eol_software_key_lower` are required for this JOIN to use index scans. Without both indexes, PostgreSQL falls back to nested-loop with sequential scan on the inner table.

### Design Notes

- **`idx_vms_os_name_lower`** is NEW — must be created in Phase 7 (migration 032 or dedicated index migration). The `vms` table is created in migration 028 (P5.1) but this expression index is not included in UNIFIED-SCHEMA-SPEC.md migration 028.
- **`idx_eol_software_key_lower`** is NEW — must be created in Phase 7. The `eol_records` table has 4 existing B-tree indexes but none on `LOWER(software_key)`.
- Expression indexes #3-5 are existing (migration 004/015 or bootstrap) and require no Phase 7 action.

---

## B-tree Text Search Patterns

B-tree indexes are the default PostgreSQL index type and are optimal for equality (`=`), range (`<`, `>`, `BETWEEN`), and left-anchored `LIKE` (`LIKE 'prefix%'`) operations on text columns.

### When B-tree is Preferred Over GIN for Text

| Pattern | Index Type | Example | Rationale |
|---------|-----------|---------|-----------|
| PK equality lookup | B-tree (PK) | `WHERE cve_id = $1` | O(log n) B-tree lookup; PK index is automatically created; GIN not needed |
| Left-anchored prefix match | B-tree | `WHERE cve_id LIKE 'CVE-2024-%'` | B-tree supports left-anchored LIKE natively; GIN not needed for prefix |
| Range queries | B-tree | `WHERE cvss_v3_score >= 7.0` | B-tree supports range scans; GIN does not support ordering |
| Exact text equality | B-tree | `WHERE status = 'completed'` | B-tree equality lookup is faster than GIN for single-value predicates |
| ILIKE short infrequent | B-tree (expression) | `WHERE LOWER(name) = LOWER($1)` | Expression index on LOWER() for case-insensitive exact match |

### When GIN is Required

| Pattern | Index Type | Example | Rationale |
|---------|-----------|---------|-----------|
| Full-text keyword search | GIN (tsvector) | `search_vector @@ to_tsquery('english', $1)` | B-tree cannot index tsvector; GIN is the only option |
| JSONB containment | GIN (jsonb) | `affected_products @> '{"vendor": "microsoft"}'::jsonb` | B-tree cannot index JSONB paths; GIN supports `@>` operator |
| Array containment | GIN (array) | `sources @> ARRAY['nvd']` | B-tree cannot index array elements; GIN inverts the array |
| Middle-of-string search | None efficient | `WHERE description ILIKE '%buffer overflow%'` | Neither B-tree nor GIN helps; use `search_vector @@ to_tsquery()` instead |

### Recommendation

**Always prefer `search_vector @@ to_tsquery()` over `ILIKE '%..%'` for user-facing CVE search.** The FTS approach uses the GIN index (`idx_cves_fts`) for O(1) lookup per term, while `ILIKE '%keyword%'` forces a sequential scan on every row in the `cves` table (8,600+ rows and growing).

For admin/internal views where the search is short, infrequent, and against a small result set (e.g., filtering a pre-limited 50-row page), `ILIKE` on the application side after an indexed fetch is acceptable as a pragmatic fallback.

---

## Search Index Summary

Complete registry of all search-related indexes with their current status and Phase 7 actions.

| # | Index Name | Table | Type | Columns/Expression | Status | Phase 7 Action |
|---|-----------|-------|------|-------------------|--------|----------------|
| 1 | `idx_cves_fts` | `cves` | GIN (tsvector) | `search_vector` | Bootstrap-gap | Add to bootstrap DDL + create in index migration |
| 2 | `idx_cves_products` | `cves` | GIN (jsonb) | `affected_products` | Existing | None |
| 3 | `idx_cves_sources` | `cves` | GIN (array) | `sources` | Existing | None |
| 4 | `idx_vms_tags` | `vms` | GIN (jsonb) | `tags` | Existing (migration 028) | None (created with table) |
| 5 | `idx_vmcvematch_kb_ids` | `vm_cve_match_rows` | GIN (array) | `kb_ids` | Existing | None |
| 6 | `idx_vms_os_name_lower` | `vms` | Expression (B-tree) | `LOWER(os_name)` | NEW | Create in index migration |
| 7 | `idx_eol_software_key_lower` | `eol_records` | Expression (B-tree) | `LOWER(software_key)` | NEW | Create in index migration |
| 8 | `idx_inventory_sub_lower_type` | `resource_inventory` | Expression (B-tree) | `(subscription_id, LOWER(resource_type))` | Existing | None |
| 9 | `idx_resource_inventory_name_lower` | `resource_inventory` | Expression (B-tree) | `LOWER(name)` | Existing | None |
| 10 | `idx_os_inventory_computer_name_lower` | `os_inventory_snapshots` | Expression (B-tree) | `LOWER(computer_name)` | Existing | None |

### Bootstrap Gaps Requiring Phase 7 Resolution

| # | Gap Item | Type | Current State | Phase 7 Action |
|---|----------|------|--------------|----------------|
| 1 | `search_vector` column on `cves` | Column (tsvector) | Migration 006 only; NOT in bootstrap DDL | Add `search_vector tsvector` column to `cves` CREATE TABLE in `pg_database.py` |
| 2 | `trg_cves_search_vector_update` trigger | Trigger | Migration 006 only; NOT in bootstrap DDL | Add trigger function + CREATE TRIGGER to bootstrap DDL |
| 3 | `idx_cves_fts` index | GIN index | Migration 006 only; NOT in bootstrap DDL | Add `CREATE INDEX IF NOT EXISTS idx_cves_fts ON cves USING GIN (search_vector)` to bootstrap DDL |
| 4 | `idx_vms_os_name_lower` index | Expression index | Does not exist yet | Create in Phase 7 index migration (P7.6) |
| 5 | `idx_eol_software_key_lower` index | Expression index | Does not exist yet | Create in Phase 7 index migration (P7.6) |

### New Indexes (Phase 7 Must Create)

- **`idx_vms_os_name_lower`** — expression index for BH-005 fuzzy EOL JOIN on `vms` table
- **`idx_eol_software_key_lower`** — expression index for BH-005 fuzzy EOL JOIN on `eol_records` table
- **`idx_cves_fts`** — must be added to bootstrap DDL (currently migration-only; exists only on migration 006 deployments)

### Existing Indexes (No Action)

- `idx_cves_products`, `idx_cves_sources`, `idx_vms_tags`, `idx_vmcvematch_kb_ids` — GIN indexes already in bootstrap or table creation DDL
- `idx_inventory_sub_lower_type`, `idx_resource_inventory_name_lower`, `idx_os_inventory_computer_name_lower` — expression indexes already in bootstrap/migration DDL

---

*Document version: 1.0*
*Phase: 06-index-query-optimization-design / P6.1*
*Generated: 2026-03-17*
*Sources: INDEX-AUDIT.md (P2.6), 06-RESEARCH.md, UNIFIED-SCHEMA-SPEC.md (P5.7), pg_database.py bootstrap DDL*
