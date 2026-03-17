# Pagination Strategy Specification

**Phase:** 06-index-query-optimization-design
**Plan:** P6.5
**Created:** 2026-03-17
**Requirements:** QRY-01, QRY-03
**Depends on:** P6.1 (SEARCH-INDEX-STRATEGY), P6.2 (FILTER-INDEX-STRATEGY)

---

## Table of Contents

1. [Strategy Overview](#1-strategy-overview)
2. [Per-View Pagination Assignment](#2-per-view-pagination-assignment)
3. [Keyset Pagination Implementation -- cve-database.html](#3-keyset-pagination-implementation----cve-databasehtml)
4. [Offset/Limit Implementation Pattern](#4-offsetlimit-implementation-pattern)
5. [Server-Side Sorting (BH-009 Fix)](#5-server-side-sorting-bh-009-fix)
6. [Pagination Index Requirements Summary](#6-pagination-index-requirements-summary)

---

## 1. Strategy Overview

Two pagination modes serve the platform's UI views, selected per-view based on dataset size, growth trajectory, and access pattern.

### Mode 1: Offset/Limit (Default)

- **Use for:** Datasets < 1,000 rows or bounded-growth tables
- **Supports:** Random page access (jump to page 5, page 12, etc.)
- **Implementation:** Standard SQL `LIMIT $N OFFSET $M`
- **Performance:** O(offset) -- degrades at deep offsets (page 100+ on 10k+ rows) because PostgreSQL must scan and discard `offset` rows before returning results
- **Trade-off:** Simple implementation, familiar UX with page numbers; acceptable for small/medium datasets

### Mode 2: Keyset (Cursor-Based)

- **Use for:** Datasets > 1,000 rows or growing unbounded
- **Requires:** Stable, unique sort key (compound key if primary sort has duplicates)
- **Implementation:** `WHERE (sort_key) < ($cursor_value)` with `LIMIT $N`
- **Performance:** Consistent O(1) at any depth -- always uses index seek, never scans discarded rows
- **Trade-off:** No random page access (no "jump to page 5"); forward/backward navigation only; requires cursor token management
- **Returns:** Opaque cursor token encoding the last row's sort key values

### Page Size Defaults

| Category | Default Page Size | Override Param | Max | Examples |
|----------|------------------|----------------|-----|---------|
| List views | 50 | `?page_size=50` | 500 | inventory, patch-management |
| Table views | 100 | `?page_size=100` | 500 | cve-database, resource-inventory |
| Dashboard widgets | 10-20 | N/A (fixed) | N/A | top CVEs by score, recent scans |
| Chat/response history | 10 | `?page_size=10` | 500 | eol-searches |

All page sizes are UI-configurable via `?page_size=N` query parameter (max 500, default per category above). Validation: `page_size = min(max(page_size, 1), 500)`.

---

## 2. Per-View Pagination Assignment

| # | View | Mode | Default Page Size | Sort Key | Expected Rows | Index Supporting Pagination | Rationale |
|---|------|------|------------------|----------|---------------|---------------------------|-----------|
| 1 | cve-database.html | **Keyset** | 100 | `(published_at DESC, cve_id DESC)` | 8,608+ (growing) | `idx_cves_published ON cves (published_at)` + PK `cve_id` | Growing dataset; deep pagination common for CVE research |
| 2 | vm-vulnerability.html (detail) | Offset/Limit | 50 | `cvss_score DESC` | 0-500 per VM | MV index `mv_vm_cve_detail_vm_severity_score_idx` | Moderate per-VM count; users navigate few pages |
| 3 | vm-vulnerability.html (overview) | None | N/A | `total_cves DESC` | 100-500 | MV index `mv_vm_vulnerability_posture_risk_total_idx` | Full list displayed; client-side filtering |
| 4 | inventory.html | Offset/Limit | 50 | `vm_name ASC` | 100-500 | `idx_vms_subscription_os ON vms (subscription_id, os_name)` | Small dataset; random page access useful |
| 5 | patch-management.html | Offset/Limit | 50 | `machine_name ASC` | 50-200 | `idx_patch_cache_resource_id` | Small dataset |
| 6 | resource-inventory.html | Offset/Limit | 100 | `name ASC` | 200-1,000 | `idx_inventory_sub_lower_type` | Moderate; random page access useful |
| 7 | eol-inventory.html | Offset/Limit | 25 | `updated_at DESC NULLS LAST` | 100-500 | `idx_eol_item_type ON eol_records (item_type, updated_at)` | Small dataset; current UI uses server-side offset/limit |
| 8 | eol-searches.html | Offset/Limit | 10 | `timestamp DESC` | 0-1,000 | `idx_eol_responses_timestamp ON eol_agent_responses (timestamp DESC)` | Moderate growth; recent results most relevant |
| 9 | cve-detail.html (affected VMs) | Offset/Limit | 100 | severity priority then `cvss_score DESC` | 0-500 | MV index `mv_vm_cve_detail_scan_cve_idx` | Moderate; users view top severity first |
| 10 | cve_alert_history.html | Offset/Limit | 100 | `fired_at DESC` | 0-10,000 | `idx_alerthistory_fired ON cve_alert_history (fired_at DESC)` | Growing but date-filtered; offset acceptable for filtered views |
| 11 | cve_alert_config.html | None | N/A | `created_at DESC` | <50 | PK sufficient | Tiny dataset; full list |
| 12 | os-normalization-rules.html | None | N/A | `priority ASC` | <100 | `idx_os_rules_type` | Tiny dataset; full list |
| 13 | cve-dashboard.html | None (MV) | N/A | N/A | Aggregate | MV pre-computed | Dashboard aggregates from MVs; no row-level pagination |
| 14 | eol.html | None | N/A | N/A | Single result | N/A | Single search result per query |
| 15 | eol-management.html | None | N/A | N/A | 100-500 | N/A | Full list from LAW; client-side filtering. Future: server-side pagination from os_inventory_snapshots |
| 16 | cache.html | None | N/A | N/A | N/A | N/A | No DB queries; in-memory cache stats |
| 17 | routing-analytics.html | None | N/A | N/A | N/A | N/A | JSONL flat files; no DB involvement |
| 18 | agent-cache-details.html | None | N/A | N/A | N/A | N/A | In-memory cache stats; no DB |
| 19 | alerts.html | None | N/A | N/A | N/A | N/A | Config CRUD; single config object |
| 20 | visualizations.html | None | N/A | N/A | N/A | N/A | Chart aggregates from MVs; no row-level pagination |
| 21 | sre.html | None | N/A | N/A | N/A | N/A | Chat UI; no DB on page load |
| 22 | azure-mcp.html | None | N/A | N/A | N/A | N/A | Chat UI; no DB on page load |
| 23 | inventory-asst.html | None | N/A | N/A | N/A | N/A | Chat UI; no DB on page load |
| 24 | index.html | None | N/A | N/A | N/A | N/A | Dashboard landing; hardcoded metrics (I-07) |

**Summary:** 1 keyset, 8 offset/limit, 15 no pagination needed.

---

## 3. Keyset Pagination Implementation -- cve-database.html

### Cursor Token Format

Cursor tokens use Base64-encoded JSON containing the sort key values of the last row on the current page. This creates an opaque, tamper-evident token that the API can decode to resume pagination.

**Cursor token structure:**

```json
{
  "published_at": "2026-03-17T10:30:00Z",
  "cve_id": "CVE-2026-12345"
}
```

**Encoding:** `base64url(JSON.stringify({published_at, cve_id}))`

**Why compound key `(published_at, cve_id)`:** Multiple CVEs can share the same `published_at` timestamp. Adding `cve_id` as a tiebreaker guarantees uniqueness and stable ordering. The `cve_id` column is the PK, so the pair `(published_at, cve_id)` is guaranteed unique.

### API Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `cursor` | string (base64) | Cursor for next/prev page (mutually exclusive with `page`) | None (first page) |
| `page_size` | integer | Override default page size | 100 |
| `direction` | `next` or `prev` | Forward or backward navigation | `next` |
| `severity` | string | Optional severity filter | None |
| `min_score` | numeric | Optional minimum CVSS score filter | None |
| `keyword` | string | Optional full-text search keyword | None |

### First Page (No Cursor)

```sql
SELECT cve_id, description, cvss_v3_score, cvss_v3_severity, published_at,
       affected_products, sources
FROM cves
WHERE 1=1
  AND ($1::text IS NULL OR cvss_v3_severity = $1)             -- severity filter
  AND ($2::numeric IS NULL OR cvss_v3_score >= $2)            -- min_score filter
  AND ($3::text IS NULL OR search_vector @@ to_tsquery('english', $3))  -- keyword filter
ORDER BY published_at DESC, cve_id DESC
LIMIT $4;  -- page_size (default 100)
-- Index: idx_cves_published (published_at) or idx_cves_severity_published when severity filtered
```

### Next Page (With Cursor, direction=next)

```sql
SELECT cve_id, description, cvss_v3_score, cvss_v3_severity, published_at,
       affected_products, sources
FROM cves
WHERE 1=1
  AND ($1::text IS NULL OR cvss_v3_severity = $1)
  AND ($2::numeric IS NULL OR cvss_v3_score >= $2)
  AND ($3::text IS NULL OR search_vector @@ to_tsquery('english', $3))
  AND (published_at, cve_id) < ($cursor_published_at, $cursor_cve_id)  -- keyset condition
ORDER BY published_at DESC, cve_id DESC
LIMIT $4;
-- Index: idx_cves_severity_published for filtered keyset; idx_cves_published for unfiltered
-- The (published_at, cve_id) < comparison uses ROW value comparison: PostgreSQL evaluates
-- published_at first, then cve_id as tiebreaker. Efficient with B-tree on published_at.
```

**ROW value comparison semantics:** `(a, b) < (x, y)` is equivalent to `a < x OR (a = x AND b < y)`. PostgreSQL's B-tree index on `published_at` handles the first condition efficiently; the PK index resolves the tiebreaker for rows with equal `published_at`.

### Previous Page (direction=prev)

```sql
SELECT * FROM (
  SELECT cve_id, description, cvss_v3_score, cvss_v3_severity, published_at,
         affected_products, sources
  FROM cves
  WHERE 1=1
    AND ($1::text IS NULL OR cvss_v3_severity = $1)
    AND ($2::numeric IS NULL OR cvss_v3_score >= $2)
    AND ($3::text IS NULL OR search_vector @@ to_tsquery('english', $3))
    AND (published_at, cve_id) > ($cursor_published_at, $cursor_cve_id)  -- reverse direction
  ORDER BY published_at ASC, cve_id ASC  -- reverse order
  LIMIT $4
) sub
ORDER BY published_at DESC, cve_id DESC;  -- re-reverse to correct display order
```

**Why subquery:** Backward navigation requires fetching rows "before" the cursor in reverse order, then re-sorting them into display order. The subquery pattern ensures exactly `page_size` rows are returned in the correct display order.

### Total Count (Separate Query)

```sql
SELECT COUNT(*) AS total
FROM cves
WHERE 1=1
  AND ($1::text IS NULL OR cvss_v3_severity = $1)
  AND ($2::numeric IS NULL OR cvss_v3_score >= $2)
  AND ($3::text IS NULL OR search_vector @@ to_tsquery('english', $3));
-- Index: idx_cves_severity (for severity filter), idx_cves_cvss3 (for score filter)
-- Note: COUNT(*) with filters still requires index scan; cached in L1 for 60s to avoid per-page re-count
```

**Caching strategy:** The total count is expensive for filtered queries. Cache the count result in L1 memory with a 60-second TTL, keyed by the filter combination hash. This avoids re-counting on every page turn while keeping the count reasonably fresh.

### API Response Format (Keyset)

```json
{
  "data": [
    {
      "cve_id": "CVE-2026-12345",
      "description": "Buffer overflow in...",
      "cvss_v3_score": 9.8,
      "cvss_v3_severity": "CRITICAL",
      "published_at": "2026-03-17T10:30:00Z",
      "affected_products": [...],
      "sources": [...]
    }
  ],
  "pagination": {
    "page_size": 100,
    "total": 8608,
    "has_next": true,
    "has_prev": false,
    "next_cursor": "eyJwdWJsaXNoZWRfYXQiOiIyMDI2LTAzLTE3VDEwOjMwOjAwWiIsImN2ZV9pZCI6IkNWRS0yMDI2LTEyMzQ1In0=",
    "prev_cursor": null
  }
}
```

**Cursor generation rule:** After fetching the page results, extract `published_at` and `cve_id` from the **last row** for `next_cursor`, and from the **first row** for `prev_cursor`. If the result set has fewer rows than `page_size`, set `has_next = false`.

---

## 4. Offset/Limit Implementation Pattern

### Standard SQL Template

```sql
-- Example: inventory.html
SELECT v.resource_id, v.vm_name, v.os_name, v.os_type, v.location, v.resource_group,
       e.is_eol, e.eol_date
FROM vms v
LEFT JOIN eol_records e ON LOWER(v.os_name) = LOWER(e.software_key)
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)  -- optional subscription filter
  AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%')  -- optional OS search
ORDER BY v.vm_name ASC
LIMIT $3 OFFSET $4;
-- $3 = page_size (default 50), $4 = (page_number - 1) * page_size
-- Index: idx_vms_subscription_os for subscription + OS filter
-- Index: idx_vms_os_name_lower + idx_eol_software_key_lower for EOL JOIN
```

### Count Query Template

```sql
SELECT COUNT(*) AS total
FROM vms v
WHERE ($1::uuid IS NULL OR v.subscription_id = $1)
  AND ($2::text IS NULL OR v.os_name ILIKE '%' || $2 || '%');
-- Separate count query; cached in L1 for 60s
```

**Count caching:** Like the keyset pattern, offset/limit count queries are cached in L1 for 60 seconds to avoid redundant counting on page navigation. The cache key is the filter combination hash.

### Offset/Limit API Response Format

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 342,
    "total_pages": 7,
    "has_next": true,
    "has_prev": false
  }
}
```

**`total_pages` computation:** `CEIL(total / page_size)` -- computed in Python, not SQL.

**`has_next` computation:** `page < total_pages`

**`has_prev` computation:** `page > 1`

### Per-View Offset/Limit SQL Patterns

#### vm-vulnerability.html (Detail Mode)

```sql
-- CVE list for a specific VM, from materialized view
SELECT cve_id, severity, cvss_score, published_date, description,
       patch_status, kb_ids
FROM mv_vm_cve_detail
WHERE resource_id = $1
  AND ($2::text IS NULL OR severity = $2)           -- optional severity filter
  AND ($3::text IS NULL OR cve_id ILIKE '%' || $3 || '%')  -- optional search
ORDER BY
  CASE severity
    WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
    WHEN 'MEDIUM' THEN 3  WHEN 'LOW' THEN 4
    ELSE 5
  END ASC,
  cvss_score DESC
LIMIT $4 OFFSET $5;
-- Index: mv_vm_cve_detail_vm_severity_score_idx ON mv_vm_cve_detail (resource_id, severity, cvss_score DESC)
```

#### resource-inventory.html

```sql
SELECT resource_id, name, type, location, resource_group, subscription_id,
       tags, provisioning_state
FROM resource_inventory
WHERE ($1::uuid IS NULL OR subscription_id = $1)
  AND ($2::text IS NULL OR LOWER(type) = LOWER($2))
  AND ($3::text IS NULL OR name ILIKE '%' || $3 || '%')
ORDER BY name ASC
LIMIT $4 OFFSET $5;
-- Index: idx_inventory_sub_lower_type ON resource_inventory (subscription_id, LOWER(type))
```

#### eol-inventory.html

```sql
SELECT software_key, software_name, normalized_software_name, version_key,
       normalized_version, eol_date, support_end_date, release_date,
       risk_level, confidence, source, agent_used, created_at, updated_at
FROM eol_records
WHERE ($1::text IS NULL OR normalized_software_name ILIKE '%' || $1 || '%')
  AND ($2::text IS NULL OR normalized_version ILIKE '%' || $2 || '%')
ORDER BY updated_at DESC NULLS LAST
LIMIT $3 OFFSET $4;
-- Index: idx_eol_item_type ON eol_records (item_type, updated_at)
-- Index: idx_eol_normalized ON eol_records (LOWER(normalized_software_name))
```

#### eol-searches.html

```sql
SELECT response_id, session_id, user_query, agent_response, sources,
       timestamp, response_time_ms
FROM eol_agent_responses
ORDER BY timestamp DESC
LIMIT $1 OFFSET $2;
-- Index: idx_eol_responses_timestamp ON eol_agent_responses (timestamp DESC)
```

#### cve-detail.html (Affected VMs)

```sql
SELECT m.resource_id, v.vm_name, v.os_name, m.severity, m.cvss_score,
       m.detected_at, m.patch_status
FROM mv_vm_cve_detail m
JOIN vms v ON m.resource_id = v.resource_id
WHERE m.cve_id = $1
ORDER BY
  CASE m.severity
    WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
    WHEN 'MEDIUM' THEN 3  WHEN 'LOW' THEN 4
    ELSE 5
  END ASC,
  m.cvss_score DESC
LIMIT $2 OFFSET $3;
-- Index: mv_vm_cve_detail_scan_cve_idx ON mv_vm_cve_detail (cve_id)
```

#### cve_alert_history.html

```sql
SELECT history_id, rule_id, cve_id, fired_at, severity_at_fire,
       cvss_score_at_fire, acknowledged, acknowledged_by, acknowledged_at
FROM cve_alert_history
WHERE ($1::text IS NULL OR severity_at_fire = $1)       -- alert_type filter
  AND ($2::boolean IS NULL OR acknowledged = $2)         -- acknowledged filter
  AND ($3::timestamptz IS NULL OR fired_at >= $3)        -- start_date
  AND ($4::timestamptz IS NULL OR fired_at <= $4)        -- end_date
ORDER BY fired_at DESC
LIMIT $5 OFFSET $6;
-- Index: idx_alerthistory_fired ON cve_alert_history (fired_at DESC)
```

#### patch-management.html

```sql
SELECT pac.resource_id, pac.machine_name, pac.os_type, pac.os_name,
       pac.location, pac.resource_group, pac.subscription_id,
       pac.critical_count, pac.other_count, pac.total_count,
       pac.last_assessed_at, pac.reboot_pending
FROM patch_assessments_cache pac
JOIN vms v ON pac.resource_id = v.resource_id
ORDER BY pac.machine_name ASC
LIMIT $1 OFFSET $2;
-- Index: idx_patch_cache_resource_id ON patch_assessments_cache (resource_id)
```

---

## 5. Server-Side Sorting (BH-009 Fix)

### Problem Statement

**BH-009:** eol-inventory.html sorting is page-local only. Clicking a column header sorts only the 25 visible rows on the current page, not the full dataset. Users see a falsely sorted view that doesn't reflect the actual data ordering across all pages.

### Solution Design

Add server-side `sort` and `order` query parameters to the EOL inventory API endpoint. Validate against a column whitelist to prevent SQL injection.

### Sortable Columns Whitelist

```python
ALLOWED_SORT_COLUMNS = {
    'software_name': 'normalized_software_name',
    'version': 'version_key',
    'status': 'status',
    'risk_level': 'risk_level',
    'updated_at': 'updated_at',
    'eol_date': 'eol_date',
    'confidence': 'confidence',
    'source': 'source',
    'agent_used': 'agent_used',
    'created_at': 'created_at',
}
```

**Key mapping:** The dictionary maps user-facing column names (from the `?sort=` parameter) to actual database column names. This prevents SQL injection by only allowing known column names.

### API Parameters

| Parameter | Type | Default | Validation |
|-----------|------|---------|------------|
| `sort` | string | `updated_at` | Must be key in `ALLOWED_SORT_COLUMNS` |
| `order` | `asc` or `desc` | `desc` | Whitelist: `{'asc', 'desc'}` |

### SQL Pattern

```sql
-- eol-inventory with server-side sort
SELECT software_key, software_name, normalized_software_name, version_key,
       normalized_version, status, risk_level, eol_date, support_end_date,
       confidence, source, agent_used, updated_at, created_at
FROM eol_records
WHERE ($1::text IS NULL OR normalized_software_name ILIKE '%' || $1 || '%')  -- search filter
ORDER BY {validated_sort_column} {validated_sort_direction} NULLS LAST
LIMIT $2 OFFSET $3;
-- Note: {validated_sort_column} is selected from ALLOWED_SORT_COLUMNS whitelist
-- Note: {validated_sort_direction} is 'ASC' or 'DESC' from whitelist validation
-- Index: idx_eol_normalized for software_name search; idx_eol_item_type for updated_at sort
```

### Implementation Notes (Phase 8)

1. Add `sort` and `order` query parameters to `GET /api/eol-inventory` endpoint
2. Validate `sort` against `ALLOWED_SORT_COLUMNS` keys; reject unknown columns with 400
3. Validate `order` against `{'asc', 'desc'}`; default to `'desc'`
4. Build `ORDER BY` clause dynamically using the mapped column name (NOT user input)
5. Add `NULLS LAST` for all sort directions to ensure NULL values don't appear at top
6. Update the eol-inventory.html JavaScript to send `sort` and `order` params on column header click, and to remove client-side sorting logic

### Sort Column Index Coverage

| Sort Column | Existing Index | Index Scan? |
|-------------|---------------|-------------|
| `updated_at` | `idx_eol_item_type (item_type, updated_at)` | Partial -- only when `item_type` filter is also applied; standalone `updated_at` sort may seq scan |
| `eol_date` | None | Seq scan -- consider adding `idx_eol_records_eol_date` if sort-by-eol-date is frequent |
| `created_at` | None | Seq scan -- acceptable for 100-500 rows |
| `risk_level` | None | Seq scan -- acceptable for 100-500 rows |
| `confidence` | None | Seq scan -- acceptable for 100-500 rows |
| `normalized_software_name` | `idx_eol_normalized` | Yes (if expression index matches LOWER()) |

**Note:** For the current dataset size (100-500 rows), sequential scans on sort columns are acceptable. Index creation for sort-only columns is deferred unless dataset exceeds 1,000 rows.

---

## 6. Pagination Index Requirements Summary

| Index | Table | Column(s) | Pagination Pattern It Supports | View(s) |
|-------|-------|-----------|-------------------------------|---------|
| `idx_cves_published` | `cves` | `published_at` | Keyset on `(published_at DESC, cve_id DESC)` | cve-database.html |
| `idx_cves_severity_published` | `cves` | `(cvss_v3_severity, published_at DESC)` | Filtered keyset on `(severity, published_at DESC)` | cve-database.html with severity filter |
| `idx_vms_subscription_os` | `vms` | `(subscription_id, os_name)` | Offset/limit with subscription + OS filter | inventory.html |
| `idx_eol_item_type` | `eol_records` | `(item_type, updated_at)` | Offset/limit with `ORDER BY updated_at DESC` | eol-inventory.html |
| `idx_eol_normalized` | `eol_records` | `LOWER(normalized_software_name)` | Offset/limit with ILIKE software_name search | eol-inventory.html |
| `idx_eol_responses_timestamp` | `eol_agent_responses` | `timestamp DESC` | Offset/limit with `ORDER BY timestamp DESC` | eol-searches.html |
| `idx_alerthistory_fired` | `cve_alert_history` | `fired_at DESC` | Offset/limit with `ORDER BY fired_at DESC` | cve_alert_history.html |
| `mv_vm_cve_detail_vm_severity_score_idx` | `mv_vm_cve_detail` | `(resource_id, severity, cvss_score DESC)` | Offset/limit with `ORDER BY cvss_score DESC` per VM | vm-vulnerability.html detail |
| `mv_vm_cve_detail_scan_cve_idx` | `mv_vm_cve_detail` | `cve_id` | Offset/limit per-CVE affected VMs | cve-detail.html |
| `idx_inventory_sub_lower_type` | `resource_inventory` | `(subscription_id, LOWER(type))` | Offset/limit with subscription + type filter | resource-inventory.html |
| `idx_patch_cache_resource_id` | `patch_assessments_cache` | `resource_id` | Offset/limit with resource_id join | patch-management.html |

### Index Design Notes

1. **Keyset indexes must cover the sort key columns.** The `idx_cves_published` B-tree on `published_at` enables the `(published_at, cve_id) < ($cursor)` condition because PostgreSQL can seek directly to the cursor position. The PK `cve_id` handles the tiebreaker.

2. **Offset/limit indexes should cover the ORDER BY column as a leading or sole column.** This enables PostgreSQL to avoid a sort operation and return rows in index order.

3. **Filtered pagination benefits from composite indexes.** When filters are applied alongside pagination (e.g., severity + pagination on cve-database), the composite index `idx_cves_severity_published` allows both the filter and the sort to use the same index.

4. **MV indexes are re-created on refresh.** All `mv_vm_cve_detail_*` indexes must be defined with `CREATE UNIQUE INDEX` on the MV so they persist across `REFRESH MATERIALIZED VIEW CONCURRENTLY` operations.

5. **Count query performance.** Total count queries (`SELECT COUNT(*)`) cannot use keyset optimization. For the keyset view (cve-database), the count is cached in L1 for 60s. For offset/limit views with small datasets, the count is fast enough to run per-request.

---

## Cross-References

- **Phase 1 view audits:** Pagination requirements per view from P1.2-P1.6
- **Phase 5 schema:** Table definitions in UNIFIED-SCHEMA-SPEC.md
- **Phase 6 P6.1:** Search index strategy (full-text, B-tree) -- idx_cves_published, search_vector
- **Phase 6 P6.2:** Filter index strategy (composite indexes) -- idx_cves_severity_published, idx_vms_subscription_os
- **Phase 6 P6.3:** Cross-table join indexes (covering, INCLUDE) -- mv_vm_cve_detail indexes
- **Phase 3 BH-009:** eol-inventory.html page-local sorting -- resolved by Section 5
- **Phase 8:** Repository implementation of pagination patterns
- **Phase 9:** UI integration of pagination API responses

---

*Phase: 06-index-query-optimization-design*
*Plan: P6.5 -- Pagination Strategy*
*Created: 2026-03-17*
