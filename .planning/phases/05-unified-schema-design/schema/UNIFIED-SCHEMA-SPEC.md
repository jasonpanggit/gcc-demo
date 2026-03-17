# Unified Schema Specification — Target State

**Phase:** 05-unified-schema-design (Plan 05-07)
**Status:** Complete
**Generated:** 2026-03-17
**Requirements addressed:** DB-01, DB-02, DB-03
**Sources:** VM-IDENTITY-SPINE.md (P5.1), CVE-TABLES.md (P5.2), INVENTORY-TABLES.md (P5.3), EOL-TABLES.md (P5.4), ALERTING-TABLES.md (P5.5), MATERIALIZED-VIEWS-TARGET.md (P5.6), TTL-TIERS-SPEC.md (P4.4), CACHE-GAPS-SUMMARY.md (P4.6)

---

## Executive Summary

This document is the complete target PostgreSQL schema for the gcc-demo EOL platform. It consolidates designs from P5.1 (VM spine), P5.2 (CVE tables), P5.3 (Inventory), P5.4 (EOL), P5.5 (Alerting), and P5.6 (Materialized Views). Phase 7 executes this spec directly as migrations 027-032.

Key metrics:
- **4 NEW tables:** `vms`, `subscriptions`, `eol_agent_responses`, `cache_ttl_config`
- **2 REDESIGNED tables:** `cve_alert_rules`, `cve_alert_history`
- **7 MODIFIED tables:** `kb_cve_edges`, `vm_cve_match_rows`, `cve_vm_detections`, `patch_assessments_cache`, `available_patches`, `os_inventory_snapshots`, `arc_software_inventory`
- **20+ ACTIVE tables:** unchanged
- **4 DEPRECATED tables:** `inventory_vm_metadata`, `arg_cache`, `law_cache`, `patch_assessments`
- **3 tables to DROP:** `arc_os_inventory`, `patch_assessment_history`, `kb_cve_edge` (singular)
- **3 MVs to DROP:** `vm_vulnerability_overview`, `cve_dashboard_stats`, `os_cve_inventory_counts`
- **1 MV MODIFIED:** `mv_vm_vulnerability_posture` (source: `vms` instead of `inventory_vm_metadata`)
- **1 view DEPRECATED:** `v_unified_vm_inventory`

---

## Table Fate Summary

| # | Table | Domain | Status | Key Change | Phase 7 Action |
|---|-------|--------|--------|-----------|---------------|
| 1 | subscriptions | Identity | NEW | New table | CREATE |
| 2 | vms | Identity | NEW | VM identity spine | CREATE |
| 3 | cves | CVE | ACTIVE | No change | None |
| 4 | kb_cve_edges | CVE | MODIFIED | Add cached_at column, FK to cves already exists | ALTER ADD COLUMN |
| 5 | cve_scans | CVE | ACTIVE | No change | None |
| 6 | vm_cve_match_rows | CVE | MODIFIED | Add FK to vms + FK to cves | ADD CONSTRAINT |
| 7 | cve_vm_detections | CVE | MODIFIED | Add FK to vms + FK to cves | ADD CONSTRAINT |
| 8 | resource_inventory | Inventory | ACTIVE | No change | None |
| 9 | resource_inventory_meta | Inventory | ACTIVE | No change | None |
| 10 | resource_inventory_cache_state | Inventory | ACTIVE | No change | None |
| 11 | os_inventory_snapshots | Inventory | MODIFIED | Add FK to vms | ADD CONSTRAINT |
| 12 | os_inventory_cache_state | Inventory | ACTIVE | No change (metadata table) | None |
| 13 | patch_assessments_cache | Inventory | MODIFIED | resource_id VARCHAR(512)->TEXT, add FK to vms | ALTER TYPE + ADD CONSTRAINT |
| 14 | available_patches | Inventory | MODIFIED | FK target changed to vms (was patch_assessments_cache) | DROP old FK + ADD new FK |
| 15 | arc_software_inventory | Inventory | MODIFIED | Add FK to vms | ADD CONSTRAINT |
| 16 | inventory_software_cache | Inventory | ACTIVE | TTL change 4h->1h in Phase 8 | None (code change) |
| 17 | inventory_os_cache | Inventory | ACTIVE | TTL change 4h->1h in Phase 8 | None (code change) |
| 18 | inventory_os_profiles | CVE | ACTIVE | No change | None |
| 19 | eol_records | EOL | ACTIVE | No change | None |
| 20 | eol_agent_responses | EOL | NEW | Session-scoped chat history | CREATE |
| 21 | os_extraction_rules | EOL | ACTIVE | No change | None |
| 22 | normalization_failures | EOL | ACTIVE | No change | None |
| 23 | cve_alert_rules | Alerting | REDESIGNED | id TEXT->rule_id UUID, JSONB config->explicit columns | DROP + CREATE |
| 24 | cve_alert_history | Alerting | REDESIGNED | 22 cols->8 cols, aggregated->per-CVE model | DROP + CREATE |
| 25 | alert_config | Alerting | ACTIVE | No change | None |
| 26 | notification_history | Alerting | ACTIVE | No change | None |
| 27 | cache_ttl_config | Admin | NEW | TTL admin overrides | CREATE + SEED |
| 28 | workflow_contexts | Operational | ACTIVE | No change | None |
| 29 | audit_trail | Operational | ACTIVE | No change | None |
| 30 | custom_runbooks | SRE | ACTIVE | No change | None |
| 31 | slo_definitions | SRE | ACTIVE | No change | None |
| 32 | slo_measurements | SRE | ACTIVE | No change | None |
| 33 | sre_incidents | SRE | ACTIVE | No change | None |
| 34 | vendor_urls | Reference | ACTIVE | No change | None |
| 35 | patch_assessments | Inventory | DEPRECATED | Superseded by patch_assessments_cache | Phase 10 DROP |
| 36 | patch_installs | Patch | ACTIVE | No change | None |
| 37 | inventory_vm_metadata | Identity | DEPRECATED | Replaced by vms | Phase 10 DROP |
| 38 | arg_cache | Inventory | DEPRECATED | Zero callers | Phase 10 DROP |
| 39 | law_cache | Inventory | DEPRECATED | No confirmed callers | Phase 10 DROP |
| — | arc_os_inventory | — | DROP | INACTIVE, no write path | DROP TABLE |
| — | patch_assessment_history | — | DROP | INACTIVE, no readers | DROP TABLE |
| — | kb_cve_edge (singular) | — | DROP | I-01: kb_cve_edges is canonical | DROP TABLE (after data migration) |

---

## Full Entity-Relationship Diagram

```mermaid
erDiagram
    subscriptions ||--o{ vms : "subscription has VMs"
    vms ||--o{ vm_cve_match_rows : "VM has CVE matches"
    vms ||--o{ patch_assessments_cache : "VM has assessments"
    vms ||--o{ available_patches : "VM has patches"
    vms ||--o{ os_inventory_snapshots : "VM has OS snapshots"
    vms ||--o{ cve_vm_detections : "VM has detections"
    vms ||--o{ arc_software_inventory : "VM has software"
    cve_scans ||--o{ vm_cve_match_rows : "scan contains"
    cves ||--o{ vm_cve_match_rows : "CVE matched"
    cves ||--o{ kb_cve_edges : "CVE has KB patches"
    cves ||--o{ cve_vm_detections : "CVE detected"
    cves ||--o{ cve_alert_history : "CVE triggered alert"
    cve_alert_rules ||--o{ cve_alert_history : "rule fires"

    subscriptions {
        UUID subscription_id PK
        VARCHAR subscription_name
        UUID tenant_id
        VARCHAR state
        JSONB tags
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    vms {
        TEXT resource_id PK
        UUID subscription_id FK
        TEXT resource_group
        TEXT vm_name
        TEXT os_name
        VARCHAR os_type
        VARCHAR vm_type
        TEXT location
        JSONB tags
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ last_synced_at
    }

    cves {
        TEXT cve_id PK
        TEXT description
        NUMERIC cvss_v3_score
        TEXT cvss_v3_severity
        JSONB affected_products
        TIMESTAMPTZ synced_at
    }

    cve_scans {
        TEXT scan_id PK
        TEXT status
        TIMESTAMPTZ completed_at
    }

    vm_cve_match_rows {
        TEXT scan_id PK_FK
        TEXT vm_id PK_FK
        TEXT cve_id PK_FK
        TEXT severity
        NUMERIC cvss_score
    }

    kb_cve_edges {
        TEXT kb_number PK
        TEXT cve_id PK_FK
        TEXT source PK
        TIMESTAMPTZ cached_at
    }

    cve_vm_detections {
        BIGSERIAL id PK
        TEXT resource_id FK
        TEXT cve_id FK
        TEXT severity
        TIMESTAMPTZ detected_at
    }

    patch_assessments_cache {
        TEXT resource_id PK_FK
        TEXT machine_name
        INTEGER total_patches
        TIMESTAMPTZ cached_at
    }

    available_patches {
        BIGSERIAL id PK
        TEXT resource_id FK
        TEXT kb_number
        TIMESTAMPTZ cached_at
    }

    os_inventory_snapshots {
        TEXT resource_id PK_FK
        INTEGER snapshot_version PK
        TEXT workspace_id PK
        TEXT os_name
        TIMESTAMPTZ cached_at
    }

    arc_software_inventory {
        BIGSERIAL id PK
        TEXT resource_id FK
        TEXT software_name
        TIMESTAMPTZ cached_at
    }

    cve_alert_rules {
        UUID rule_id PK
        VARCHAR rule_name
        VARCHAR severity_threshold
        NUMERIC cvss_min_score
        BOOLEAN enabled
    }

    cve_alert_history {
        UUID alert_id PK
        UUID rule_id FK
        VARCHAR cve_id FK
        TIMESTAMPTZ fired_at
        BOOLEAN notification_sent
    }

    eol_records {
        TEXT software_key PK
        TEXT software_name
        BOOLEAN is_eol
        DATE eol_date
    }

    eol_agent_responses {
        UUID response_id PK
        UUID session_id
        TEXT user_query
        TEXT agent_response
        JSONB sources
    }

    cache_ttl_config {
        VARCHAR source_name PK
        VARCHAR ttl_tier
        INTEGER ttl_seconds
    }
```

---

## Complete DDL — Phase 7 Migration Blueprint

### Migration 027 — Drop Obsolete Tables and MVs

```sql
-- ============================================================
-- Migration 027: Drop inactive tables and migration-011 MVs
-- Pre-condition: Verify no active callers before executing
-- ============================================================

-- Drop inactive tables (confirmed INACTIVE in P2.2)
DROP TABLE IF EXISTS arc_os_inventory;
DROP TABLE IF EXISTS patch_assessment_history;

-- Drop migration-011 MVs (no active callers — superseded by bootstrap MVs)
-- Verify with grep before executing:
--   grep -r "vm_vulnerability_overview" app/agentic/eol/ --include="*.py"
--   grep -r "cve_dashboard_stats" app/agentic/eol/ --include="*.py"
--   grep -r "os_cve_inventory_counts" app/agentic/eol/ --include="*.py"
DROP MATERIALIZED VIEW IF EXISTS vm_vulnerability_overview;
DROP MATERIALIZED VIEW IF EXISTS cve_dashboard_stats;
DROP MATERIALIZED VIEW IF EXISTS os_cve_inventory_counts;

-- Migrate kb_cve_edge data to kb_cve_edges before DROP (I-01 resolution)
INSERT INTO kb_cve_edges (kb_number, cve_id, source, severity, last_seen, cached_at)
SELECT kb_id, cve_id, COALESCE(source, 'msrc'), severity, cached_at, cached_at
FROM kb_cve_edge
WHERE NOT EXISTS (
    SELECT 1 FROM kb_cve_edges
    WHERE kb_cve_edges.kb_number = kb_cve_edge.kb_id
      AND kb_cve_edges.cve_id = kb_cve_edge.cve_id
      AND kb_cve_edges.source = COALESCE(kb_cve_edge.source, 'msrc')
);
DROP TABLE IF EXISTS kb_cve_edge;
```

### Migration 028 — Create VM Identity Spine

```sql
-- ============================================================
-- Migration 028: Create subscriptions + vms tables (P5.1)
-- Pre-condition: None (new tables)
-- ============================================================

-- Create subscriptions table (must exist before vms due to FK)
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id UUID            NOT NULL,
    subscription_name VARCHAR(200)  NOT NULL,
    tenant_id       UUID,
    state           VARCHAR(20)     DEFAULT 'Enabled',
    tags            JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_subscriptions PRIMARY KEY (subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_name
    ON subscriptions (subscription_name);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant
    ON subscriptions (tenant_id);

-- Create vms table (canonical VM identity spine)
CREATE TABLE IF NOT EXISTS vms (
    resource_id     TEXT            NOT NULL,
    subscription_id UUID            NOT NULL,
    resource_group  TEXT            NOT NULL,
    vm_name         TEXT            NOT NULL,
    os_name         TEXT,
    os_type         VARCHAR(10),    -- 'Linux' or 'Windows'
    vm_type         VARCHAR(20),    -- 'arc' or 'azure-vm'
    location        TEXT,
    tags            JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_synced_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_vms PRIMARY KEY (resource_id),
    CONSTRAINT fk_vms_subscription FOREIGN KEY (subscription_id)
        REFERENCES subscriptions(subscription_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_vms_subscription
    ON vms (subscription_id);

CREATE INDEX IF NOT EXISTS idx_vms_os_name
    ON vms (os_name);

CREATE INDEX IF NOT EXISTS idx_vms_os_type
    ON vms (os_type);

CREATE INDEX IF NOT EXISTS idx_vms_location
    ON vms (location);

CREATE INDEX IF NOT EXISTS idx_vms_resource_group
    ON vms (resource_group);

CREATE INDEX IF NOT EXISTS idx_vms_tags
    ON vms USING GIN (tags);

CREATE INDEX IF NOT EXISTS idx_vms_last_synced
    ON vms (last_synced_at);
```

### Migration 029 — CVE Table Modifications

```sql
-- ============================================================
-- Migration 029: CVE domain FK additions and column changes (P5.2)
-- Pre-condition: vms table exists (migration 028)
-- ============================================================

-- Add cached_at to kb_cve_edges (P4.4 LONG_LIVED TTL tracking)
ALTER TABLE kb_cve_edges ADD COLUMN IF NOT EXISTS cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Clean up orphan rows before adding FK constraints
DELETE FROM vm_cve_match_rows
WHERE vm_id NOT IN (SELECT resource_id FROM vms);

DELETE FROM vm_cve_match_rows
WHERE cve_id NOT IN (SELECT cve_id FROM cves);

-- Add FK from vm_cve_match_rows to vms
ALTER TABLE vm_cve_match_rows
    ADD CONSTRAINT fk_vmcvematch_vm FOREIGN KEY (vm_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

-- Add FK from vm_cve_match_rows to cves
ALTER TABLE vm_cve_match_rows
    ADD CONSTRAINT fk_vmcvematch_cve FOREIGN KEY (cve_id)
    REFERENCES cves(cve_id) ON DELETE CASCADE
    DEFERRABLE INITIALLY DEFERRED;

-- Clean up orphan rows in cve_vm_detections
DELETE FROM cve_vm_detections
WHERE resource_id NOT IN (SELECT resource_id FROM vms);

DELETE FROM cve_vm_detections
WHERE cve_id NOT IN (SELECT cve_id FROM cves);

-- Add FKs to cve_vm_detections
ALTER TABLE cve_vm_detections
    ADD CONSTRAINT fk_cvevmdet_vm FOREIGN KEY (resource_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

ALTER TABLE cve_vm_detections
    ADD CONSTRAINT fk_cvevmdet_cve FOREIGN KEY (cve_id)
    REFERENCES cves(cve_id) ON DELETE CASCADE;

-- Add unique index to prevent duplicate detections
CREATE UNIQUE INDEX IF NOT EXISTS idx_cvevmdet_resource_cve
    ON cve_vm_detections (resource_id, cve_id);
```

### Migration 030 — Inventory + EOL Tables

```sql
-- ============================================================
-- Migration 030: Inventory FK additions + EOL + cache tables (P5.3, P5.4, P4.4)
-- Pre-condition: vms table exists (migration 028)
-- ============================================================

-- Type alignment for patch_assessments_cache (metadata-only operation)
ALTER TABLE patch_assessments_cache ALTER COLUMN resource_id TYPE TEXT;

-- Clean up orphan rows in inventory tables
DELETE FROM patch_assessments_cache
WHERE resource_id NOT IN (SELECT resource_id FROM vms);

DELETE FROM available_patches
WHERE resource_id NOT IN (SELECT resource_id FROM vms);

DELETE FROM os_inventory_snapshots
WHERE resource_id NOT IN (SELECT resource_id FROM vms);

DELETE FROM arc_software_inventory
WHERE resource_id NOT IN (SELECT resource_id FROM vms);

-- Add FK from inventory tables to vms
ALTER TABLE patch_assessments_cache
    ADD CONSTRAINT fk_patchcache_vm FOREIGN KEY (resource_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

ALTER TABLE available_patches
    DROP CONSTRAINT IF EXISTS available_patches_resource_id_fkey,
    ADD CONSTRAINT fk_availpatches_vm FOREIGN KEY (resource_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

ALTER TABLE os_inventory_snapshots
    ADD CONSTRAINT fk_osinvsnap_vm FOREIGN KEY (resource_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

ALTER TABLE arc_software_inventory
    ADD CONSTRAINT fk_arcswinv_vm FOREIGN KEY (resource_id)
    REFERENCES vms(resource_id) ON DELETE CASCADE;

-- Create eol_agent_responses (P5.4 — NEW table for eol-searches.html persistence)
CREATE TABLE IF NOT EXISTS eol_agent_responses (
    response_id     UUID            NOT NULL DEFAULT gen_random_uuid(),
    session_id      UUID            NOT NULL,
    user_query      TEXT            NOT NULL,
    agent_response  TEXT            NOT NULL,
    sources         JSONB           NOT NULL DEFAULT '[]'::jsonb,
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    response_time_ms INTEGER,
    CONSTRAINT pk_eol_agent_responses PRIMARY KEY (response_id)
);
CREATE INDEX IF NOT EXISTS idx_eol_responses_session ON eol_agent_responses (session_id);
CREATE INDEX IF NOT EXISTS idx_eol_responses_timestamp ON eol_agent_responses (timestamp DESC);

-- Create cache_ttl_config (P4.4 — TTL admin overrides)
CREATE TABLE IF NOT EXISTS cache_ttl_config (
    source_name     VARCHAR(50)     PRIMARY KEY,
    ttl_tier        VARCHAR(30)     NOT NULL DEFAULT 'medium_lived',
    ttl_seconds     INTEGER         NOT NULL DEFAULT 3600,
    updated_at      TIMESTAMP       DEFAULT NOW(),
    updated_by      VARCHAR(100)    DEFAULT 'system'
);

-- Seed cache_ttl_config with initial values
INSERT INTO cache_ttl_config (source_name, ttl_tier, ttl_seconds) VALUES
    ('arg', 'medium_lived', 3600),
    ('law', 'medium_lived', 3600),
    ('msrc', 'long_lived', 86400)
ON CONFLICT (source_name) DO NOTHING;
```

### Migration 031 — Alerting Tables (DROP + CREATE)

```sql
-- ============================================================
-- Migration 031: Redesign alert tables (P5.5 — I-06 resolution)
-- Pre-condition: cves table exists
-- Note: Fresh schema start — no data to preserve (current data is in-memory only)
-- ============================================================

-- Drop old alert tables (fresh schema start — no data to preserve)
DROP TABLE IF EXISTS cve_alert_history;
DROP TABLE IF EXISTS cve_alert_rules;

-- Recreate cve_alert_rules with new schema
CREATE TABLE IF NOT EXISTS cve_alert_rules (
    rule_id             UUID            NOT NULL DEFAULT gen_random_uuid(),
    rule_name           VARCHAR(200)    NOT NULL,
    severity_threshold  VARCHAR(20)     NOT NULL,
    cvss_min_score      NUMERIC(3, 1)   NOT NULL DEFAULT 0.0,
    vendor_filter       VARCHAR(100),
    product_filter      VARCHAR(100),
    enabled             BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_cve_alert_rules PRIMARY KEY (rule_id),
    CONSTRAINT uq_cve_alert_rules_name UNIQUE (rule_name)
);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON cve_alert_rules (enabled);

-- Recreate cve_alert_history with per-CVE firing model
CREATE TABLE IF NOT EXISTS cve_alert_history (
    alert_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    rule_id             UUID            NOT NULL,
    cve_id              VARCHAR(20)     NOT NULL,
    fired_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    severity            VARCHAR(20)     NOT NULL,
    cvss_score          NUMERIC(3, 1),
    notification_sent   BOOLEAN         NOT NULL DEFAULT FALSE,
    notification_channel VARCHAR(50),
    CONSTRAINT pk_cve_alert_history PRIMARY KEY (alert_id),
    CONSTRAINT fk_alerthistory_rule FOREIGN KEY (rule_id)
        REFERENCES cve_alert_rules(rule_id) ON DELETE CASCADE,
    CONSTRAINT fk_alerthistory_cve FOREIGN KEY (cve_id)
        REFERENCES cves(cve_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_alerthistory_rule ON cve_alert_history (rule_id);
CREATE INDEX IF NOT EXISTS idx_alerthistory_cve ON cve_alert_history (cve_id);
CREATE INDEX IF NOT EXISTS idx_alerthistory_fired ON cve_alert_history (fired_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerthistory_rule_cve ON cve_alert_history (rule_id, cve_id);
```

### Migration 032 — Recreate Modified MV

```sql
-- ============================================================
-- Migration 032: Recreate mv_vm_vulnerability_posture with vms as source (P5.6)
-- Pre-condition: vms table exists and is populated; eol_records exists
-- ============================================================

-- Recreate mv_vm_vulnerability_posture with vms as source
DROP MATERIALIZED VIEW IF EXISTS mv_vm_vulnerability_posture;

CREATE MATERIALIZED VIEW mv_vm_vulnerability_posture AS
SELECT
  vm.resource_id                                                          AS vm_id,
  vm.vm_name,
  vm.vm_type,
  vm.os_name,
  vm.os_type,
  vm.location,
  vm.resource_group,
  vm.subscription_id,
  vm.last_synced_at,
  COALESCE(agg.total_cves, 0)         AS total_cves,
  COALESCE(agg.critical, 0)           AS critical,
  COALESCE(agg.high, 0)               AS high,
  COALESCE(agg.medium, 0)             AS medium,
  COALESCE(agg.low, 0)                AS low,
  COALESCE(agg.unpatched, 0)          AS unpatched,
  COALESCE(agg.unpatched_critical, 0) AS unpatched_critical,
  COALESCE(agg.unpatched_high, 0)     AS unpatched_high,
  CASE
    WHEN COALESCE(agg.critical, 0) > 0
     AND COALESCE(agg.unpatched_critical, 0) > 0 THEN 'Critical'
    WHEN COALESCE(agg.high, 0) > 0
     AND COALESCE(agg.unpatched_high, 0) > 0     THEN 'High'
    WHEN COALESCE(agg.total_cves, 0) > 0         THEN 'Medium'
    ELSE 'Healthy'
  END AS risk_level,
  e.is_eol                            AS eol_status,
  e.eol_date                          AS eol_date,
  NOW() AS last_updated
FROM vms vm
LEFT JOIN (
  SELECT
    vm_id,
    COUNT(DISTINCT cve_id)                                                              AS total_cves,
    COUNT(DISTINCT CASE WHEN severity = 'CRITICAL' THEN cve_id END)                    AS critical,
    COUNT(DISTINCT CASE WHEN severity = 'HIGH'     THEN cve_id END)                    AS high,
    COUNT(DISTINCT CASE WHEN severity = 'MEDIUM'   THEN cve_id END)                    AS medium,
    COUNT(DISTINCT CASE WHEN severity = 'LOW'      THEN cve_id END)                    AS low,
    COUNT(DISTINCT CASE WHEN patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched,
    COUNT(DISTINCT CASE WHEN severity = 'CRITICAL'
                         AND patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched_critical,
    COUNT(DISTINCT CASE WHEN severity = 'HIGH'
                         AND patch_status NOT IN ('installed') THEN cve_id END)        AS unpatched_high
  FROM vm_cve_match_rows
  WHERE scan_id = latest_completed_scan_id()
  GROUP BY vm_id
) agg ON agg.vm_id = vm.resource_id
LEFT JOIN eol_records e ON LOWER(vm.os_name) = LOWER(e.software_key);

-- Indexes for CONCURRENT refresh and query performance
CREATE UNIQUE INDEX mv_vm_vulnerability_posture_vm_id_idx
    ON mv_vm_vulnerability_posture (vm_id);
CREATE INDEX mv_vm_vulnerability_posture_risk_total_idx
    ON mv_vm_vulnerability_posture (risk_level, total_cves DESC);
CREATE INDEX mv_vm_vulnerability_posture_sub_rg_idx
    ON mv_vm_vulnerability_posture (subscription_id, resource_group);
CREATE INDEX mv_vm_vulnerability_posture_vm_type_idx
    ON mv_vm_vulnerability_posture (vm_type);

-- Fix I-03: Set MV ownership to current role for CONCURRENT refresh
ALTER MATERIALIZED VIEW mv_vm_vulnerability_posture OWNER TO CURRENT_ROLE;
```

---

## Bootstrap _REQUIRED_TABLES Update

Document exact changes to `pg_database.py` `_REQUIRED_TABLES` list:

### Tables to ADD to _REQUIRED_TABLES

| # | Table | Reason |
|---|-------|--------|
| 1 | `subscriptions` | NEW — VM identity spine parent table |
| 2 | `vms` | NEW — canonical VM identity spine |
| 3 | `eol_agent_responses` | NEW — session-scoped chat history for eol-searches.html |
| 4 | `cache_ttl_config` | NEW — TTL admin overrides for cache management |
| 5 | `patch_assessments_cache` | Migration 011, now promoted to bootstrap — actively used by ARG sync job |
| 6 | `available_patches` | Migration 011, now promoted to bootstrap — actively used by ARG sync job |
| 7 | `arc_software_inventory` | Migration 011, now promoted to bootstrap — actively used by LAW sync job |
| 8 | `cve_vm_detections` | Migration 011, now promoted to bootstrap — actively used by KB-CVE inference job |

### Tables to REMOVE from _REQUIRED_TABLES (after Phase 7 DROP)

None immediately — deprecated tables (`inventory_vm_metadata`, `arg_cache`, `law_cache`, `patch_assessments`) remain in `_REQUIRED_TABLES` until Phase 10 consumer migration is complete. Premature removal would break the bootstrap check.

### _REQUIRED_RELATIONS to ADD

| # | FK Name | Child Table | Child Column | Parent Table | Parent Column | On Delete |
|---|---------|-------------|--------------|-------------|---------------|-----------|
| 1 | `fk_vms_subscription` | vms | subscription_id | subscriptions | subscription_id | RESTRICT |
| 2 | `fk_vmcvematch_vm` | vm_cve_match_rows | vm_id | vms | resource_id | CASCADE |
| 3 | `fk_vmcvematch_cve` | vm_cve_match_rows | cve_id | cves | cve_id | CASCADE DEFERRABLE |
| 4 | `fk_patchcache_vm` | patch_assessments_cache | resource_id | vms | resource_id | CASCADE |
| 5 | `fk_availpatches_vm` | available_patches | resource_id | vms | resource_id | CASCADE |
| 6 | `fk_osinvsnap_vm` | os_inventory_snapshots | resource_id | vms | resource_id | CASCADE |
| 7 | `fk_cvevmdet_vm` | cve_vm_detections | resource_id | vms | resource_id | CASCADE |
| 8 | `fk_cvevmdet_cve` | cve_vm_detections | cve_id | cves | cve_id | CASCADE |
| 9 | `fk_arcswinv_vm` | arc_software_inventory | resource_id | vms | resource_id | CASCADE |
| 10 | `fk_alerthistory_rule` | cve_alert_history | rule_id | cve_alert_rules | rule_id | CASCADE |
| 11 | `fk_alerthistory_cve` | cve_alert_history | cve_id | cves | cve_id | CASCADE |

---

## Phase 6-10 Forward References

### Phase 6 — Index & Query Optimization Design

- Design optimal index for `vms.os_name` -> `eol_records.software_key` fuzzy JOIN (BH-005 bulk lookup)
- Design missing `idx_cves_severity` on `cvss_v3_severity` (INDEX-AUDIT GAP-01)
- Design composite indexes for common filter combinations on `vms` (subscription_id + os_type + location)
- Design composite `idx_cves_severity_published` for severity + date range queries (GAP-02)
- Benchmark whether `idx_edges_kb` is redundant with PK prefix on `kb_cve_edges` (R-02)
- Design partial index strategy for `vm_cve_match_rows WHERE scan_id = latest_completed_scan_id()` (GAP-05)
- Write target SQL for all 24 high-traffic endpoints

### Phase 7 — Schema Implementation

- Execute migrations 027-032 as specified in the DDL section above
- Update `pg_database.py` bootstrap DDL for new/redesigned tables
- Update `_REQUIRED_TABLES` and `_REQUIRED_RELATIONS` lists per bootstrap section above
- Run `ALTER MATERIALIZED VIEW ... OWNER TO {runtime_role}` for all MVs (I-03 fix)
- Implement idempotent bootstrap: check `pg_matviews` before CREATE (skip if MV exists)
- Verify zero callers for 3 migration-011 MVs before DROP (grep checks documented in migration 027)

### Phase 8 — Repository Layer Update

- Rewrite `AlertPostgresRepository` to use new `cve_alert_rules` / `cve_alert_history` schema (8 columns, UUID PKs, per-CVE firing model)
- Replace `cve_alert_rule_manager.py` / `cve_alert_history_manager.py` in-memory managers with DB-backed calls (resolves BH-025, BH-026, BH-027)
- Rewrite `cve_metadata_sync_job.py` to use canonical `cves` column names (I-09 fix): `severity`->`cvss_v3_severity`, `cvss_score`->`cvss_v3_score`, `vendor`/`product`->`affected_products` JSONB, `cached_at`->`synced_at`
- Rewire `MSRCKBCVESyncJob` to write to `kb_cve_edges` (not `kb_cve_edge`): column mapping `kb_id`->`kb_number`
- Rewire `KBCVEInferenceJob` to read from `kb_cve_edges` (not `kb_cve_edge`): column mapping `kb_id`->`kb_number` in `_process_available_patches()` and `_process_installed_patches()`
- Remove `KBCVEInferenceJob._refresh_materialized_views()` 3-MV refresh list (migration-011 MVs dropped)
- Consolidate `InventoryPostgresRepository` + `PostgresInventoryVMRepository` to write to `vms` (fix dual-write with conflicting staleness policies)
- Create `EolAgentResponseRepository` for `eol_agent_responses` table with `save()`, `get_by_session()`, `list_recent_sessions()`, `delete_session()`
- Reduce `inventory_software_cache` / `inventory_os_cache` TTL from 4h to 1h (MEDIUM_LIVED alignment)
- Replace `cve_inventory.py` LAW fallback with `arc_software_inventory` query (eliminate last uncached LAW KQL call)
- Implement 6 admin API endpoints: 3 refresh (POST /api/cache/refresh/{arg,law,msrc}), 1 status (GET /api/cache/status), 2 TTL config (GET/PUT /api/cache/config/ttl)

### Phase 9 — UI Integration Update

- Wire `cve-alert-config.html` and `cve-alert-history.html` to DB-backed alert repository (replacing in-memory data)
- Wire `eol-searches.html` to `eol_agent_responses` for persistent chat history (replacing in-memory orchestrator lists)
- Remove `INVENTORY_USE_UNIFIED_VIEW` feature flag from all 5 callers (I-02 resolution)
- Wire PDF export to PG fast-path MVs instead of Python analytics fallback (I-04 fix)
- Remove stale "L2 (Cosmos DB)" label in resource-inventory.html
- Replace N+1 EOL lookups in inventory.html with bulk JOIN query using `vms` -> `eol_records` pattern (BH-005)
- Wire `cache.html` to new admin API endpoints (refresh buttons, TTL config, freshness indicators)
- Fix hardcoded "Database Load" 35% metric in index.html (I-07)

### Phase 10 — Validation & Cleanup

- DROP deprecated tables: `inventory_vm_metadata`, `arg_cache`, `law_cache`, `patch_assessments`
- DROP deprecated view: `v_unified_vm_inventory`
- Remove deprecated tables from `_REQUIRED_TABLES` list
- Remove Cosmos stubs: `cve_cosmos_repository`, `resource_inventory_cosmos`, `cosmos_cache` (I-05)
- Remove `cache.html` deprecated Cosmos endpoint calls (`/api/cache/cosmos/*`) that return 410 Gone (I-08)
- Run EXPLAIN ANALYZE on all high-traffic queries to validate index usage
- Confirm zero remaining consumers for each dropped table before DROP
- Final `pg_database.py` bootstrap DDL verification against target schema

---

*Phase: 05-unified-schema-design / P5.7*
*Generated: 2026-03-17*
