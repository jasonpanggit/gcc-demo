-- ============================================================
-- Migration 031: Redesign alert tables (P5.5 — I-06 resolution)
-- Pre-condition: cves table exists (bootstrap)
-- Post-condition: cve_alert_rules and cve_alert_history tables
--                 recreated with new schema + 9 indexes
-- Note: Fresh schema start — no data to preserve. Current
--       alert data is in-memory only (I-06).
-- Idempotency: DROP IF EXISTS + CREATE IF NOT EXISTS
-- ============================================================

-- Drop old alert tables (child first due to FK, then parent)
DROP TABLE IF EXISTS cve_alert_history;
DROP TABLE IF EXISTS cve_alert_rules;

-- ============================================================
-- Recreate cve_alert_rules with explicit filter columns
-- ============================================================

CREATE TABLE IF NOT EXISTS cve_alert_rules (
    rule_id             UUID            NOT NULL DEFAULT gen_random_uuid(),
    rule_name           VARCHAR(200)    NOT NULL,
    severity_threshold  VARCHAR(20)     NOT NULL,
    cvss_min_score      NUMERIC(3, 1)  NOT NULL DEFAULT 0.0,
    vendor_filter       VARCHAR(100),
    product_filter      VARCHAR(100),
    enabled             BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_cve_alert_rules PRIMARY KEY (rule_id),
    CONSTRAINT uq_cve_alert_rules_name UNIQUE (rule_name)
);

-- Base index (UNIFIED-SCHEMA-SPEC)
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled
    ON cve_alert_rules (enabled);

-- Phase 6 partial index: active rules only (FILTER-INDEX-STRATEGY)
CREATE INDEX IF NOT EXISTS idx_alert_rules_active
    ON cve_alert_rules (rule_id, severity_threshold) WHERE enabled = true;

-- ============================================================
-- Recreate cve_alert_history with per-CVE firing model
-- ============================================================

CREATE TABLE IF NOT EXISTS cve_alert_history (
    alert_id             UUID            NOT NULL DEFAULT gen_random_uuid(),
    rule_id              UUID            NOT NULL,
    cve_id               VARCHAR(20)     NOT NULL,
    fired_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    severity             VARCHAR(20)     NOT NULL,
    cvss_score           NUMERIC(3, 1),
    notification_sent    BOOLEAN         NOT NULL DEFAULT FALSE,
    notification_channel VARCHAR(50),
    CONSTRAINT pk_cve_alert_history PRIMARY KEY (alert_id),
    CONSTRAINT fk_alerthistory_rule FOREIGN KEY (rule_id)
        REFERENCES cve_alert_rules(rule_id) ON DELETE CASCADE,
    CONSTRAINT fk_alerthistory_cve FOREIGN KEY (cve_id)
        REFERENCES cves(cve_id) ON DELETE CASCADE
);

-- Base indexes (UNIFIED-SCHEMA-SPEC)
CREATE INDEX IF NOT EXISTS idx_alerthistory_rule
    ON cve_alert_history (rule_id);

CREATE INDEX IF NOT EXISTS idx_alerthistory_cve
    ON cve_alert_history (cve_id);

CREATE INDEX IF NOT EXISTS idx_alerthistory_fired
    ON cve_alert_history (fired_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alerthistory_rule_cve
    ON cve_alert_history (rule_id, cve_id);

-- Phase 6 composite index: severity+fired_at for filtered timeline queries (FILTER-INDEX-STRATEGY)
CREATE INDEX IF NOT EXISTS idx_alerthistory_severity_fired
    ON cve_alert_history (severity, fired_at DESC);

-- Phase 6 partial index: unsent notifications (FILTER-INDEX-STRATEGY)
CREATE INDEX IF NOT EXISTS idx_alerthistory_unsent
    ON cve_alert_history (alert_id, rule_id) WHERE notification_sent = false;

-- Phase 6 covering index: rule-scoped queries with INCLUDE for index-only scan (JOIN-INDEX-STRATEGY)
CREATE INDEX IF NOT EXISTS idx_alerthistory_rule_covering
    ON cve_alert_history (rule_id) INCLUDE (cve_id, severity, fired_at);
