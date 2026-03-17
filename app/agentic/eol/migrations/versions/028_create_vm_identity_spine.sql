-- ============================================================
-- Migration 028: Create subscriptions + vms tables (P5.1)
-- Pre-condition: None (new tables)
-- Post-condition: subscriptions and vms tables exist with all
--                 indexes. Tables will be empty — Phase 8 sync
--                 jobs populate them.
-- Idempotency: IF NOT EXISTS on all CREATE statements
-- ============================================================

-- 1. Create subscriptions table (must exist before vms due to FK)
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id   UUID            NOT NULL,
    subscription_name VARCHAR(200)    NOT NULL,
    tenant_id         UUID,
    state             VARCHAR(20)     DEFAULT 'Enabled',
    tags              JSONB           NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_subscriptions PRIMARY KEY (subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_name
    ON subscriptions (subscription_name);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant
    ON subscriptions (tenant_id);

-- 2. Create vms table (canonical VM identity spine)
CREATE TABLE IF NOT EXISTS vms (
    resource_id     TEXT            NOT NULL,
    subscription_id UUID            NOT NULL,
    resource_group  TEXT            NOT NULL,
    vm_name         TEXT            NOT NULL,
    os_name         TEXT,
    os_type         VARCHAR(10),
    vm_type         VARCHAR(20),
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
