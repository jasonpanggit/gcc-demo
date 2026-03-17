# Target SQL -- Admin & Operational Domain

**Phase:** 06-index-query-optimization-design / P6.6
**Scope:** cache.html, agent-cache-details.html, agents.html, routing-analytics.html, sre.html, azure-mcp.html, index.html
**Generated:** 2026-03-17
**Requirements:** QRY-01, QRY-03

---

## Overview

This document covers all 7 Admin & Operational domain UI views (Views 18-24). Most are low-traffic or no-DB views. Only cache.html and sre.html involve database interaction, and those are limited to cache freshness queries and audit trail writes respectively.

---

## View 18: cache.html (GET /cache)

**Route:** `GET /cache`
**API Endpoint:** `GET /api/cache/status`

No direct DB queries on page load. Stats widgets use JavaScript `fetch()` to `/api/cache/status`.

Target query for Phase 8 cache status API:

### Cache freshness status (6 admin API endpoints from P4.5)

```sql
-- GET /api/cache/status -- TTL configuration
SELECT source_name, ttl_tier, ttl_seconds, updated_at
FROM cache_ttl_config
ORDER BY source_name;
```

**Index:** PK lookup on cache_ttl_config (3 rows)
**Repository:** `CacheStatusRepository.get_ttl_config()`
**Router:** `api/cache.py`

### ARG cache freshness

```sql
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM patch_assessments_cache;
```

**Index:** No special indexes needed (COUNT + MAX on small table)
**Repository:** `CacheStatusRepository.get_arg_freshness()`
**Router:** `api/cache.py`

### LAW cache freshness

```sql
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM os_inventory_snapshots;
```

**Index:** No special indexes needed (COUNT + MAX on small table)
**Repository:** `CacheStatusRepository.get_law_freshness()`
**Router:** `api/cache.py`

### MSRC cache freshness

```sql
SELECT COUNT(*) AS row_count,
       MAX(cached_at) AS latest_cached_at,
       MIN(cached_at) AS oldest_cached_at
FROM kb_cve_edges;
```

**Index:** No special indexes needed (COUNT + MAX on small table)
**Repository:** `CacheStatusRepository.get_msrc_freshness()`
**Router:** `api/cache.py`

**Note:** Phase 8 must implement 6 admin API endpoints per INVALIDATION-SPEC.md:
1. `POST /api/cache/refresh/arg` -- trigger ARG sync
2. `POST /api/cache/refresh/law` -- trigger LAW sync
3. `POST /api/cache/refresh/msrc` -- trigger MSRC sync + cascade to inference
4. `GET /api/cache/status` -- freshness report (queries above)
5. `GET /api/cache/config/ttl` -- read TTL config
6. `PUT /api/cache/config/ttl` -- update TTL config

---

## View 19: agent-cache-details.html (GET /agent-cache-details)

**Route:** `GET /agent-cache-details`
**API Endpoint:** N/A

No direct DB queries -- in-memory cache stats only.

Agent cache details are served from in-memory data structures maintained by the MCP composite client and individual agent caches. No PostgreSQL tables are involved.

---

## View 20: agents.html (GET /agents)

**Route:** `GET /agents`
**API Endpoint:** N/A

No direct DB queries -- in-memory agent config only.

Agent configuration is loaded from Python module definitions and environment variables. The agents page displays registered agent names, capabilities, and status from in-memory state.

---

## View 21: routing-analytics.html (GET /routing-analytics)

**Route:** `GET /routing-analytics`
**API Endpoint:** `GET /api/routing-analytics`

No DB queries -- JSONL flat files. No Phase 6/7 schema work needed.

Data source is `./routing_logs/*.jsonl` files read by `routing_analytics.py`. These are append-only JSONL logs of agent routing decisions. No PostgreSQL involvement.

---

## View 22: sre.html (GET /sre)

**Route:** `GET /sre`
**API Endpoint:** N/A (WebSocket streaming)

No DB queries on page load. Pure chat/streaming UI.

Side-effect writes to `audit_trail` happen via downstream SRE tool calls:

### SRE audit trail write (side-effect, not page-load query)

```sql
INSERT INTO audit_trail (id, action, details, user_id, timestamp)
VALUES ($1, $2, $3, $4, NOW());
```

**Index:** `idx_audit_trail_timestamp` (exists)
**Note:** This is a write-only operation triggered by SRE agent actions, not a page-load query.
**Repository:** `AuditTrailRepository.log_action(action, details, user_id)`
**Router:** `api/sre.py`

---

## View 23: azure-mcp.html (GET /azure-mcp)

**Route:** `GET /azure-mcp`
**API Endpoint:** N/A (WebSocket streaming)

No direct DB queries -- external Azure MCP proxy.

The Azure MCP page proxies tool calls to the external `@azure/mcp` server. All data retrieval is from Azure APIs, not PostgreSQL.

---

## View 24: index.html (GET /)

**Route:** `GET /`
**API Endpoint:** N/A (server-side template rendering)

No DB queries on page load. Cache stats are hardcoded or fetched from in-memory.

**Note:** I-07 -- "Database Load" metric is hardcoded at 35% (Phase 9 fix target).

Target query for real DB metric (Phase 9):

### Real database load metric (replace hardcoded 35%)

```sql
SELECT
    (SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections;
-- Compute: active_connections / max_connections * 100 = real DB load %
```

**Note:** This is a pg_catalog query, not an application table query. Phase 9 must replace the hardcoded value.
**Repository:** N/A (Phase 9 inline query in router)
**Router:** `api/ui.py`

---

## Cross-Reference Table

| View | API Endpoint | Queries | DB Involvement | Phase 8 Repository | Phase 9 Router |
|------|-------------|---------|---------------|-------------------|---------------|
| cache | GET /api/cache/status | 4 freshness queries | Phase 8: 6 admin API endpoints | CacheStatusRepository | api/cache.py |
| agent-cache-details | N/A | None | In-memory only | N/A | api/cache.py |
| agents | N/A | None | In-memory only | N/A | api/agents.py |
| routing-analytics | N/A | None | JSONL flat files | N/A | api/routing_analytics.py |
| sre | audit_trail INSERT | 1 side-effect write | Write-only, not page-load | AuditTrailRepository | api/sre.py |
| azure-mcp | N/A | None | External MCP | N/A | api/azure_mcp.py |
| index | pg_stat_activity (Phase 9) | 1 system query | I-07 fix target | N/A | api/ui.py |

---

## All 24 Views Coverage

| Domain | Views | With DB Queries | No-DB Views |
|--------|-------|----------------|-------------|
| CVE | 8 | 8 | 0 |
| Inventory & EOL | 9 | 8 | 1 (inventory-asst) |
| Admin & Operational | 7 | 2 (cache, sre side-effect) | 5 |
| **Total** | **24** | **18** | **6** |

Total target SQL queries documented: 35+ across 3 domain files.

---

*Domain: Admin & Operational*
*Views: 7*
*DB-query views: 2 (cache freshness, sre audit trail)*
*No-DB views: 5 (agent-cache-details, agents, routing-analytics, azure-mcp, index)*
*Known Issues referenced: I-07 (hardcoded DB load metric)*
