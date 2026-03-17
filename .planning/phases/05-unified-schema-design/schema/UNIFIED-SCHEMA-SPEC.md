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

*Phase: 05-unified-schema-design / P5.7*
*Generated: 2026-03-17*
