-- ============================================================
-- Migration 030: Inventory FK additions + EOL + cache tables
-- Pre-condition: vms table exists (migration 028)
-- Post-condition: Inventory tables FK'd to vms; eol_agent_responses
--                 and cache_ttl_config created and seeded
-- WARNING: Orphan cleanup will DELETE all rows from inventory
--          child tables because vms is empty. Phase 8 repopulates.
-- Idempotency: DO blocks for ADD CONSTRAINT; IF NOT EXISTS for
--              CREATE TABLE/INDEX; ON CONFLICT DO NOTHING for seed
-- ============================================================

-- ============================================================
-- Ensure inventory tables exist (bootstrap gap: these are created
-- by the runtime bootstrap DDL but not by any prior migration).
-- Using IF NOT EXISTS so this is safe on already-migrated DBs.
-- ============================================================

CREATE TABLE IF NOT EXISTS patch_assessments_cache (
    resource_id     TEXT        NOT NULL,
    machine_name    TEXT,
    os_name         TEXT,
    os_version      TEXT,
    vm_type         TEXT,
    total_patches   INTEGER     NOT NULL DEFAULT 0,
    critical_count  INTEGER     NOT NULL DEFAULT 0,
    security_count  INTEGER     NOT NULL DEFAULT 0,
    other_count     INTEGER     NOT NULL DEFAULT 0,
    last_modified   TIMESTAMPTZ,
    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_id)
);

CREATE TABLE IF NOT EXISTS available_patches (
    id              BIGSERIAL   PRIMARY KEY,
    resource_id     TEXT        NOT NULL,
    kb_number       TEXT,
    title           TEXT,
    classification  TEXT,
    severity        TEXT,
    reboot_required BOOLEAN     DEFAULT FALSE,
    installed       BOOLEAN     DEFAULT FALSE,
    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS os_inventory_snapshots (
    resource_id      TEXT        NOT NULL,
    snapshot_version INTEGER     NOT NULL DEFAULT 1,
    workspace_id     TEXT        NOT NULL,
    computer_name    TEXT,
    os_name          TEXT,
    os_version       TEXT,
    os_type          TEXT,
    last_heartbeat   TIMESTAMPTZ,
    cached_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl_seconds      INTEGER     NOT NULL DEFAULT 3600,
    PRIMARY KEY (resource_id, snapshot_version, workspace_id)
);

CREATE TABLE IF NOT EXISTS arc_software_inventory (
    id              BIGSERIAL   PRIMARY KEY,
    resource_id     TEXT        NOT NULL,
    software_name   TEXT,
    software_version TEXT,
    publisher       TEXT,
    install_date    TEXT,
    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Type alignment
-- ============================================================

-- patch_assessments_cache.resource_id: VARCHAR(512) -> TEXT
-- Metadata-only operation in PostgreSQL (no table rewrite)
-- (On a fresh schema the column is already TEXT; this is a no-op.)
ALTER TABLE patch_assessments_cache ALTER COLUMN resource_id TYPE TEXT;

-- ============================================================
-- Orphan cleanup for inventory tables
-- ============================================================

DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM patch_assessments_cache WHERE resource_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from patch_assessments_cache', _count;
    END IF;
END $$;

DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM available_patches WHERE resource_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from available_patches', _count;
    END IF;
END $$;

DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM os_inventory_snapshots WHERE resource_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from os_inventory_snapshots', _count;
    END IF;
END $$;

DO $$ DECLARE _count BIGINT; BEGIN
    DELETE FROM arc_software_inventory WHERE resource_id NOT IN (SELECT resource_id FROM vms);
    GET DIAGNOSTICS _count = ROW_COUNT;
    IF _count > 0 THEN
        RAISE NOTICE 'Deleted % orphan rows from arc_software_inventory', _count;
    END IF;
END $$;

-- ============================================================
-- FK additions: inventory tables -> vms
-- ============================================================

-- patch_assessments_cache -> vms
DO $$ BEGIN
    ALTER TABLE patch_assessments_cache
        ADD CONSTRAINT fk_patchcache_vm
        FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_patchcache_vm already exists, skipping';
END $$;

-- available_patches -> vms (drop old FK to patch_assessments_cache first)
ALTER TABLE available_patches DROP CONSTRAINT IF EXISTS available_patches_resource_id_fkey;

DO $$ BEGIN
    ALTER TABLE available_patches
        ADD CONSTRAINT fk_availpatches_vm
        FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_availpatches_vm already exists, skipping';
END $$;

-- os_inventory_snapshots -> vms
DO $$ BEGIN
    ALTER TABLE os_inventory_snapshots
        ADD CONSTRAINT fk_osinvsnap_vm
        FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_osinvsnap_vm already exists, skipping';
END $$;

-- arc_software_inventory -> vms
DO $$ BEGIN
    ALTER TABLE arc_software_inventory
        ADD CONSTRAINT fk_arcswinv_vm
        FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Constraint fk_arcswinv_vm already exists, skipping';
END $$;

-- ============================================================
-- NEW: eol_agent_responses (P5.4 — eol-searches.html persistence)
-- ============================================================

CREATE TABLE IF NOT EXISTS eol_agent_responses (
    response_id      UUID            NOT NULL DEFAULT gen_random_uuid(),
    session_id       UUID            NOT NULL,
    user_query       TEXT            NOT NULL,
    agent_response   TEXT            NOT NULL,
    sources          JSONB           NOT NULL DEFAULT '[]'::jsonb,
    timestamp        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    response_time_ms INTEGER,
    CONSTRAINT pk_eol_agent_responses PRIMARY KEY (response_id)
);

CREATE INDEX IF NOT EXISTS idx_eol_responses_session
    ON eol_agent_responses (session_id);

CREATE INDEX IF NOT EXISTS idx_eol_responses_timestamp
    ON eol_agent_responses (timestamp DESC);

-- ============================================================
-- NEW: cache_ttl_config (P4.4 — TTL admin overrides)
-- ============================================================

CREATE TABLE IF NOT EXISTS cache_ttl_config (
    source_name  VARCHAR(50)  PRIMARY KEY,
    ttl_tier     VARCHAR(30)  NOT NULL DEFAULT 'medium_lived',
    ttl_seconds  INTEGER      NOT NULL DEFAULT 3600,
    updated_at   TIMESTAMP    DEFAULT NOW(),
    updated_by   VARCHAR(100) DEFAULT 'system'
);

-- Seed with initial TTL values (ON CONFLICT DO NOTHING for idempotency)
INSERT INTO cache_ttl_config (source_name, ttl_tier, ttl_seconds) VALUES
    ('arg', 'medium_lived', 3600),
    ('law', 'medium_lived', 3600),
    ('msrc', 'long_lived', 86400)
ON CONFLICT (source_name) DO NOTHING;
