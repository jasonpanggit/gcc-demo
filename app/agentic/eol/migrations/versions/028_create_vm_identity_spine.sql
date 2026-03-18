-- ============================================================
-- Migration 028: Create VM Identity Spine tables (P5.1)
-- Pre-condition: bootstrap tables exist (001-027 applied)
-- Post-condition: subscriptions, vms, and cve_vm_detections
--                 tables exist with indexes
-- Idempotency: All CREATE use IF NOT EXISTS
-- ============================================================

-- ==========================================================
-- subscriptions
-- ==========================================================

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

CREATE INDEX IF NOT EXISTS idx_subscriptions_name ON subscriptions (subscription_name);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON subscriptions (tenant_id);

-- ==========================================================
-- vms
-- ==========================================================

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

CREATE INDEX IF NOT EXISTS idx_vms_subscription ON vms (subscription_id);
CREATE INDEX IF NOT EXISTS idx_vms_os_name ON vms (os_name);
CREATE INDEX IF NOT EXISTS idx_vms_os_type ON vms (os_type);
CREATE INDEX IF NOT EXISTS idx_vms_location ON vms (location);
CREATE INDEX IF NOT EXISTS idx_vms_resource_group ON vms (resource_group);
CREATE INDEX IF NOT EXISTS idx_vms_tags ON vms USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_vms_last_synced ON vms (last_synced_at);
CREATE INDEX IF NOT EXISTS idx_vms_os_name_lower ON vms (LOWER(os_name));
CREATE INDEX IF NOT EXISTS idx_vms_subscription_os ON vms (subscription_id, os_name);

-- ==========================================================
-- cve_vm_detections
-- ==========================================================

CREATE TABLE IF NOT EXISTS cve_vm_detections (
    id              BIGSERIAL   PRIMARY KEY,
    resource_id     TEXT        NOT NULL,
    cve_id          TEXT        NOT NULL,
    severity        TEXT,
    detection_source TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cve_vm_resource_id ON cve_vm_detections (resource_id);
CREATE INDEX IF NOT EXISTS idx_cve_vm_cve_id ON cve_vm_detections (cve_id);
