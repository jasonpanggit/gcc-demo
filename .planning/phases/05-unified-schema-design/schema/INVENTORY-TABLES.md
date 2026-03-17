# Inventory Domain Schema Design

**Phase:** P5.3 -- Inventory Tables Design
**Status:** Complete
**Generated:** 2026-03-17

---

## Overview

The inventory domain covers Azure resource metadata, OS snapshots, patch assessments, and software inventory. This document specifies the target schema for all inventory-domain tables, their FK relationships to the `vms` identity spine (P5.1), TTL tier assignments, tables to DROP and DEPRECATE, and the domain ERD.

Tables in this domain fall into three categories:
1. **Active data tables** -- store typed, normalized inventory data with FK to `vms`
2. **State/cache metadata tables** -- track TTL and cache freshness (no FK to `vms`)
3. **Legacy/inactive tables** -- scheduled for DROP or DEPRECATION

---

## 1. `resource_inventory` -- Status: ACTIVE (no structural changes)

### Purpose

Stores ALL Azure resource types discovered via Azure Resource Graph (ARG) -- VMs, storage accounts, networking resources, databases, etc. This is a mixed-type resource catalogue, not a VM-only table.

### DDL

```sql
CREATE TABLE IF NOT EXISTS resource_inventory (
    id              TEXT            NOT NULL,
    name            TEXT,
    type            TEXT,
    location        TEXT,
    resource_group  TEXT,
    subscription_id TEXT,
    properties      JSONB           NOT NULL DEFAULT '{}',
    tags            JSONB           NOT NULL DEFAULT '{}',
    synced_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_resource_inventory PRIMARY KEY (id)
);
```

### NO FK to `vms`

The `resource_inventory` table intentionally has **NO FK to `vms`** for the following reasons:

- `resource_inventory` stores ALL Azure resource types (VMs, storage accounts, networking, etc.) -- not just VMs
- The `id` column is a generic Azure ARM resource ID, not always a VM path
- Only VM-type rows would conceptually FK to `vms`, but the mixed-type nature of this table makes FK impractical
- Phase 8 queries that need VM enrichment should JOIN explicitly:
  ```sql
  SELECT ri.*, v.os_name, v.vm_type
  FROM resource_inventory ri
  JOIN vms v ON ri.id = v.resource_id
  WHERE ri.type LIKE '%virtualMachines%';
  ```

### Indexes

| Index Name | Columns | Type | Purpose |
|------------|---------|------|---------|
| pk_resource_inventory | id | PRIMARY KEY | PK lookup |
| idx_resource_inventory_type | type | B-tree | Type-based filtering |
| idx_resource_inventory_sub | subscription_id | B-tree | Subscription filter |

### Index DDL

```sql
CREATE INDEX IF NOT EXISTS idx_resource_inventory_type
    ON resource_inventory (type);

CREATE INDEX IF NOT EXISTS idx_resource_inventory_sub
    ON resource_inventory (subscription_id);
```

---

## 2. `os_inventory_snapshots` -- Status: MODIFIED (adding FK to vms)

### Purpose

Stores point-in-time OS inventory snapshots from Log Analytics Workspace (LAW) Heartbeat data. Each row represents one VM's OS state at a specific snapshot version and workspace. The `resource_id` column links to the `vms` identity spine.

### DDL

```sql
CREATE TABLE IF NOT EXISTS os_inventory_snapshots (
    resource_id         TEXT            NOT NULL,
    snapshot_version    INTEGER         NOT NULL DEFAULT 1,
    workspace_id        TEXT            NOT NULL,
    computer_name       TEXT,
    os_name             TEXT,
    os_version          TEXT,
    os_type             TEXT,
    kernel_version      TEXT,
    last_heartbeat      TIMESTAMPTZ,
    cached_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_os_inventory_snapshots PRIMARY KEY (resource_id, snapshot_version, workspace_id),
    CONSTRAINT fk_osinvsnap_vm FOREIGN KEY (resource_id)
        REFERENCES vms(resource_id) ON DELETE CASCADE          -- NEW
);
```

### Modifications

- **NEW FK:** `fk_osinvsnap_vm` -- `resource_id` -> `vms(resource_id)` ON DELETE CASCADE
  - When a VM is removed from the `vms` spine, all its OS snapshots are automatically cleaned up
- **TYPE ALIGNMENT:** `resource_id` is already TEXT -- matches `vms.resource_id TEXT`. No type change required.
- **TTL Tier:** MEDIUM_LIVED (3600s / 1h) per TTL-TIERS-SPEC row #7 -- Pattern C (metadata-controlled via `os_inventory_cache_state`)
  - Staleness is delegated to companion table `os_inventory_cache_state.expires_at`
  - Phase 8 should standardize to `get_ttl(CacheTTLProfile.MEDIUM_LIVED)` instead of caller-specified `ttl_seconds`

### `os_name` in this table vs `vms.os_name`

- **`os_inventory_snapshots.os_name`:** Stores the raw LAW-reported OS name at snapshot time. This is the unprocessed value from the KQL Heartbeat query (e.g., `"Ubuntu 20.04.6 LTS"`, `"Microsoft Windows Server 2022 Datacenter"`)
- **`vms.os_name`:** Stores the normalized canonical OS name used for query-time filtering and EOL lookup (e.g., `"Ubuntu 20.04"`, `"Windows Server 2022"`)
- Both are needed -- this table for raw historical data, `vms` for canonical identity

### Indexes

| Index Name | Columns | Type | Purpose |
|------------|---------|------|---------|
| pk_os_inventory_snapshots | (resource_id, snapshot_version, workspace_id) | PRIMARY KEY | Composite PK |
| idx_osinvsnap_resource | resource_id | B-tree | VM lookup |
| idx_osinvsnap_cached | cached_at | B-tree | Staleness queries |

### Index DDL

```sql
CREATE INDEX IF NOT EXISTS idx_osinvsnap_resource
    ON os_inventory_snapshots (resource_id);

CREATE INDEX IF NOT EXISTS idx_osinvsnap_cached
    ON os_inventory_snapshots (cached_at);
```

### Phase 7 Migration

```sql
-- Add FK constraint (table already exists)
ALTER TABLE os_inventory_snapshots
    ADD CONSTRAINT fk_osinvsnap_vm
    FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
```

> **Pre-condition:** `vms` table must exist and be populated before adding this FK. Orphan rows in `os_inventory_snapshots` with `resource_id` values not in `vms` must be cleaned up first:
> ```sql
> DELETE FROM os_inventory_snapshots
> WHERE resource_id NOT IN (SELECT resource_id FROM vms);
> ```

---
