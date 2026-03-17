# Target SQL -- Inventory & EOL Domain

**Phase:** 06-index-query-optimization-design / P6.6
**Scope:** inventory.html, resource-inventory.html, patch-management.html, eol.html, eol-inventory.html, eol-management.html, eol-searches.html, os-normalization-rules.html, inventory-asst.html
**Generated:** 2026-03-17
**Requirements:** QRY-01, QRY-03

---

## Overview

This document contains the complete target SQL for all 9 Inventory & EOL domain UI views. Each query uses asyncpg `$1/$2` parameter syntax, documents expected index usage, pagination approach, bad-hack elimination, and maps to Phase 8 repository methods and Phase 9 routers.

---

## View 9: inventory.html (GET /inventory)

**Route:** `GET /inventory`
**API Endpoint:** `GET /api/inventory/raw/os`

### Query 9a -- VM inventory with bulk EOL lookup (BH-005 fix)

```sql
WITH vm_data AS (
    SELECT v.resource_id, v.vm_name, v.os_name, v.os_type,
           v.location, v.resource_group, v.subscription_id
    FROM vms v
    WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
      AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%')
)
SELECT d.resource_id, d.vm_name, d.os_name, d.os_type,
       d.location, d.resource_group, d.subscription_id,
       e.is_eol, e.eol_date, e.software_name AS eol_software_name
FROM vm_data d
LEFT JOIN eol_records e ON LOWER(d.os_name) = LOWER(e.software_key)
ORDER BY d.vm_name ASC
LIMIT $3 OFFSET $4;
```

**Index:** `idx_vms_subscription_os` (P6.2), `idx_vms_os_name_lower` (P6.1), `idx_eol_software_key_lower` (P6.1)
**Pagination:** Offset/limit (default 50)
**Eliminates:** BH-005 (N+1 POST /api/search/eol per OS row replaced with single bulk JOIN)
**Repository:** `PostgresInventoryVMRepository.get_vm_inventory_with_eol(subscription_id, os_search, limit, offset)`
**Router:** `api/inventory.py`

### Query 9b -- VM inventory count

```sql
SELECT COUNT(*) AS total
FROM vms v
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
  AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%');
```

**Cache:** L1 in-memory for 60s
**Repository:** `PostgresInventoryVMRepository.count_vm_inventory(subscription_id, os_search)`
**Router:** `api/inventory.py`

### Query 9c -- Software inventory per VM

```sql
SELECT software_name, software_type, software_version, publisher, cached_at
FROM arc_software_inventory
WHERE resource_id = $1
ORDER BY software_name;
```

**Index:** `idx_arc_sw_inventory_resource_id`
**Pagination:** None (typically < 200 software entries per VM)
**Repository:** `PostgresInventoryVMRepository.get_software_for_vm(resource_id)`
**Router:** `api/inventory.py`

---

## View 10: resource-inventory.html (GET /resource-inventory)

**Route:** `GET /resource-inventory`
**API Endpoint:** `GET /api/resource-inventory`

### Query 10a -- Resource list with filters

```sql
SELECT resource_id, name, resource_type, subscription_id, resource_group,
       location, os_type, os_name, tags, last_synced_at,
       eol_status, eol_date, eol_confidence
FROM resource_inventory
WHERE ($1::text IS NULL OR subscription_id = $1)
  AND ($2::text IS NULL OR LOWER(resource_type) = LOWER($2))
  AND ($3::text IS NULL OR name ILIKE '%' || $3 || '%')
ORDER BY name ASC
LIMIT $4 OFFSET $5;
```

**Index:** `idx_inventory_sub_lower_type` (exists)
**Pagination:** Offset/limit (default 100)
**Repository:** `ResourceInventoryPostgresStore.list_resources(subscription_id, resource_type, name_search, limit, offset)`
**Router:** `api/resource_inventory.py`

### Query 10b -- Cache freshness

```sql
SELECT subscription_id, resource_type, cached_at, expires_at, row_count
FROM resource_inventory_cache_state
WHERE expires_at > NOW()
ORDER BY cached_at DESC;
```

**Index:** `idx_resource_inventory_cache_state_expiry`
**Pagination:** None (small metadata table)
**Repository:** `ResourceInventoryPostgresStore.get_cache_status()`
**Router:** `api/resource_inventory.py`

---

## View 11: patch-management.html (GET /patch-management)

**Route:** `GET /patch-management`
**API Endpoint:** `GET /api/patch-management/machines`

### Query 11a -- Single-query patch management view (BH-010 fix)

```sql
SELECT v.resource_id, v.vm_name, v.os_name, v.os_type, v.location, v.resource_group,
       pac.machine_name, pac.total_patches, pac.critical_count, pac.security_count,
       pac.last_modified, pac.os_version, pac.vm_type AS pac_vm_type,
       (SELECT COUNT(*) FROM available_patches ap WHERE ap.resource_id = v.resource_id) AS available_patch_count
FROM vms v
LEFT JOIN patch_assessments_cache pac ON pac.resource_id = v.resource_id
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
ORDER BY COALESCE(pac.critical_count, 0) DESC, v.vm_name ASC
LIMIT $2 OFFSET $3;
```

**Index:** `idx_vms_subscription` (filter), `idx_patch_cache_resource_id` (JOIN), `idx_patches_resource_id` (subquery)
**Pagination:** Offset/limit (default 50)
**Eliminates:** BH-010 (two-query load: /machines + /arg-patch-data merged into single query)
**Repository:** `PostgresPatchRepository.get_patch_management_view(subscription_id, limit, offset)`
**Router:** `api/patch_management.py`

### Query 11b -- Patch detail for VM

```sql
SELECT ap.id, ap.resource_id, ap.kb_id, ap.software_name, ap.software_version,
       ap.classifications, ap.assessment_state, ap.assessment_timestamp
FROM available_patches ap
WHERE ap.resource_id = $1
ORDER BY ap.classifications, ap.software_name;
```

**Index:** `idx_patches_resource_id`
**Pagination:** None (typically < 100 patches per VM)
**Repository:** `PostgresPatchRepository.get_patches_for_vm(resource_id)`
**Router:** `api/patch_management.py`

---

## View 12: eol.html (GET /eol-search)

**Route:** `GET /eol-search`
**API Endpoint:** `GET /api/eol/search`

### Query 12a -- EOL lookup (PK)

```sql
SELECT software_key, software_name, version_key, status, risk_level,
       eol_date, extended_end_date, is_eol, last_verified,
       item_type, lifecycle_url, updated_at
FROM eol_records
WHERE software_key = $1;
```

**Index:** PK `eol_records_pkey` (O(1) lookup)
**Pagination:** None (single row)
**Repository:** `EolPostgresRepository.get_by_key(software_key)`
**Router:** `api/eol.py`

---

## View 13: eol-inventory.html (GET /eol-inventory)

**Route:** `GET /eol-inventory`
**API Endpoint:** `GET /api/eol/inventory`

### Query 13a -- EOL records with search + server-side sort (BH-009 fix)

```sql
SELECT software_key, software_name, version_key, status, risk_level,
       eol_date, is_eol, item_type, updated_at
FROM eol_records
WHERE ($1::text IS NULL OR normalized_software_name ILIKE '%' || $1 || '%')
ORDER BY updated_at DESC NULLS LAST
LIMIT $2 OFFSET $3;
```

**Index:** `idx_eol_normalized` for search, `idx_eol_item_type` for ORDER BY updated_at
**Pagination:** Offset/limit (default 25)
**Eliminates:** BH-009 (sorting is page-local only; now server-side ORDER BY)
**Note:** Sort column is configurable per PAGINATION-STRATEGY.md Section 5; validated against ALLOWED_SORT_COLUMNS whitelist
**Repository:** `EolPostgresRepository.list_records(search, sort_column, sort_direction, limit, offset)`
**Router:** `api/eol.py`

---

## View 14: eol-management.html (GET /eol-management)

**Route:** `GET /eol-management`
**API Endpoint:** `GET /api/eol/management`

### Query 14a -- VMs with EOL status (same pattern as inventory BH-005)

```sql
SELECT v.resource_id, v.vm_name, v.os_name, v.os_type,
       v.resource_group, v.location,
       e.is_eol, e.eol_date, e.status AS eol_status, e.risk_level
FROM vms v
LEFT JOIN eol_records e ON LOWER(v.os_name) = LOWER(e.software_key)
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
ORDER BY e.is_eol DESC NULLS LAST, v.vm_name ASC
LIMIT $2 OFFSET $3;
```

**Index:** `idx_vms_subscription` (filter), `idx_vms_os_name_lower` + `idx_eol_software_key_lower` (JOIN)
**Pagination:** Offset/limit (default 50)
**Repository:** `EolPostgresRepository.get_vm_eol_management(subscription_id, limit, offset)`
**Router:** `api/eol.py`

---

## View 15: eol-searches.html (GET /eol-searches)

**Route:** `GET /eol-searches`
**API Endpoint:** `GET /api/eol/searches`

### Query 15a -- Recent EOL agent responses

```sql
SELECT response_id, session_id, user_query, agent_response,
       sources, timestamp, response_time_ms
FROM eol_agent_responses
ORDER BY timestamp DESC
LIMIT $1 OFFSET $2;
```

**Index:** `idx_eol_responses_timestamp`
**Pagination:** Offset/limit (default 10)
**Repository:** `EolAgentResponseRepository.list_recent(limit, offset)`
**Router:** `api/eol.py`

### Query 15b -- Session-scoped responses

```sql
SELECT response_id, session_id, user_query, agent_response,
       sources, timestamp, response_time_ms
FROM eol_agent_responses
WHERE session_id = $1
ORDER BY timestamp ASC;
```

**Index:** `idx_eol_responses_session`
**Pagination:** None (session history, typically < 50 entries)
**Repository:** `EolAgentResponseRepository.get_by_session(session_id)`
**Router:** `api/eol.py`

---

## View 16: os-normalization-rules.html (GET /os-normalization-rules)

**Route:** `GET /os-normalization-rules`
**API Endpoint:** `GET /api/os-normalization-rules`

### Query 16a -- All rules

```sql
SELECT id, rule_type, pattern, replacement, priority, description, created_at
FROM os_extraction_rules
ORDER BY priority ASC, rule_type ASC;
```

**Index:** `idx_os_rules_type`
**Pagination:** None (< 100 rules)
**Repository:** `OsExtractionRulesRepository.list_rules()`
**Router:** `api/eol.py`

---

## View 17: inventory-asst.html (GET /inventory-asst)

**Route:** `GET /inventory-asst`
**API Endpoint:** N/A

No direct DB queries -- pure chat/streaming UI.

DB queries happen only via downstream tool calls (inventory MCP server, CVE lookups, etc.). Those queries use repository methods documented in the CVE and Inventory domain files.

---

## Cross-Reference Table

| View | API Endpoint | Queries | BH Fixed | Phase 8 Repository | Phase 9 Router |
|------|-------------|---------|----------|-------------------|---------------|
| inventory | GET /api/inventory/raw/os | 9a-9c | BH-005 | PostgresInventoryVMRepository | api/inventory.py |
| resource-inventory | GET /api/resource-inventory | 10a-10b | - | ResourceInventoryPostgresStore | api/resource_inventory.py |
| patch-management | GET /api/patch-management/machines | 11a-11b | BH-010 | PostgresPatchRepository | api/patch_management.py |
| eol | GET /api/eol/search | 12a | - | EolPostgresRepository | api/eol.py |
| eol-inventory | GET /api/eol/inventory | 13a | BH-009 | EolPostgresRepository | api/eol.py |
| eol-management | GET /api/eol/management | 14a | - | EolPostgresRepository | api/eol.py |
| eol-searches | GET /api/eol/searches | 15a-15b | - | EolAgentResponseRepository | api/eol.py |
| os-normalization-rules | GET /api/os-normalization-rules | 16a | - | OsExtractionRulesRepository | api/eol.py |
| inventory-asst | N/A | None | - | N/A | api/inventory_assistant.py |

---

*Domain: Inventory & EOL*
*Views: 9*
*Distinct SQL queries: 13 (9a-9c, 10a-10b, 11a-11b, 12a, 13a, 14a, 15a-15b, 16a)*
*Bad hacks eliminated: BH-005, BH-009, BH-010*
