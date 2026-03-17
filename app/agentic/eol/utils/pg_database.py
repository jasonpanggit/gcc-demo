"""
PostgreSQL Database Manager — Bootstrap DDL & Schema Validation.

Runtime-authoritative source of table DDL for the gcc-demo EOL platform.
When any table in _REQUIRED_TABLES is missing, _bootstrap_runtime_schema()
creates ALL tables with IF NOT EXISTS, ensuring fresh deployments have
identical schema to migrated deployments.

Phase 10 cleanup: deprecated tables removed, aligned with final schema.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


class PostgresDatabaseManager:
    """Manages PostgreSQL schema bootstrap and validation."""

    # ------------------------------------------------------------------ #
    # Tables checked at every startup.  If ANY is missing, the full
    # bootstrap DDL runs.
    # Phase 10: deprecated tables removed (inventory_vm_metadata,
    # patch_assessments, arg_cache, law_cache) — see migration 033.
    # ------------------------------------------------------------------ #
    _REQUIRED_TABLES: List[str] = [
        # --- Core CVE ---
        "cves",
        "kb_cve_edges",
        "cve_scans",
        "vm_cve_match_rows",
        # --- VM Identity Spine (NEW P5.1) ---
        "subscriptions",
        "vms",
        # --- Inventory ---
        "resource_inventory",
        "resource_inventory_meta",
        "resource_inventory_cache_state",
        "os_inventory_snapshots",
        "os_inventory_cache_state",
        "inventory_os_profiles",
        "inventory_software_cache",
        "inventory_os_cache",
        # --- Inventory (promoted from migration 011) ---
        "patch_assessments_cache",
        "available_patches",
        "arc_software_inventory",
        "cve_vm_detections",
        # --- Patch ---
        "patch_installs",
        # --- EOL ---
        "eol_records",
        "eol_agent_responses",                  # NEW P5.4
        "os_extraction_rules",
        "normalization_failures",
        # --- Alerting ---
        "cve_alert_rules",
        "cve_alert_history",
        "alert_config",
        "notification_history",
        # --- Admin ---
        "cache_ttl_config",                     # NEW P4.4
        # --- Operational ---
        "workflow_contexts",
        "audit_trail",
        # --- SRE ---
        "custom_runbooks",
        "slo_definitions",
        "slo_measurements",
        "sre_incidents",
        # --- Reference ---
        "vendor_urls",
    ]

    # ------------------------------------------------------------------ #
    # Foreign-key relationships validated by ensure_runtime_schema().
    # Tuples: (child_table, child_column, parent_table, parent_column)
    # ------------------------------------------------------------------ #
    _REQUIRED_RELATIONS: List[Tuple[str, str, str, str]] = [
        # Existing relations
        ("kb_cve_edges", "cve_id", "cves", "cve_id"),
        ("vm_cve_match_rows", "scan_id", "cve_scans", "scan_id"),
        ("slo_measurements", "slo_id", "slo_definitions", "slo_id"),
        # NEW Phase 7 FK relations (migrations 028-031)
        ("vms", "subscription_id", "subscriptions", "subscription_id"),
        ("vm_cve_match_rows", "vm_id", "vms", "resource_id"),
        ("vm_cve_match_rows", "cve_id", "cves", "cve_id"),
        ("patch_assessments_cache", "resource_id", "vms", "resource_id"),
        ("available_patches", "resource_id", "vms", "resource_id"),
        ("os_inventory_snapshots", "resource_id", "vms", "resource_id"),
        ("cve_vm_detections", "resource_id", "vms", "resource_id"),
        ("cve_vm_detections", "cve_id", "cves", "cve_id"),
        ("arc_software_inventory", "resource_id", "vms", "resource_id"),
        ("cve_alert_history", "rule_id", "cve_alert_rules", "rule_id"),
        ("cve_alert_history", "cve_id", "cves", "cve_id"),
    ]

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ================================================================== #
    #  Bootstrap DDL — creates the COMPLETE target schema on fresh deploy
    # ================================================================== #

    async def _bootstrap_runtime_schema(self) -> None:
        """Create all tables, indexes, functions, triggers, and MVs.

        Uses IF NOT EXISTS throughout so re-running is safe on an
        already-migrated database.  Aligned with migrations 001-032.
        """
        async with self._pool.acquire() as conn:
            # ----------------------------------------------------------
            # latest_completed_scan_id() function
            # ----------------------------------------------------------
            await conn.execute("""
                CREATE OR REPLACE FUNCTION latest_completed_scan_id()
                RETURNS TEXT LANGUAGE sql STABLE AS $$
                    SELECT scan_id FROM cve_scans
                    WHERE status = 'completed'
                    ORDER BY completed_at DESC
                    LIMIT 1;
                $$;
            """)

            # ==========================================================
            # CORE CVE TABLES
            # ==========================================================

            # --- cves ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cves (
                    cve_id              TEXT PRIMARY KEY,
                    description         TEXT,
                    published_at        TIMESTAMPTZ,
                    modified_at         TIMESTAMPTZ,
                    cvss_v2_score       NUMERIC(4, 2),
                    cvss_v2_severity    TEXT,
                    cvss_v2_vector      TEXT,
                    cvss_v2_exploitability NUMERIC(6, 3),
                    cvss_v2_impact      NUMERIC(6, 3),
                    cvss_v3_score       NUMERIC(4, 2),
                    cvss_v3_severity    TEXT,
                    cvss_v3_vector      TEXT,
                    cvss_v3_exploitability NUMERIC(6, 3),
                    cvss_v3_impact      NUMERIC(6, 3),
                    cwe_ids             TEXT[],
                    affected_products   JSONB,
                    "references"        JSONB,
                    vendor_metadata     JSONB,
                    sources             TEXT[],
                    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    search_vector       tsvector
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_cvss3 ON cves (cvss_v3_score);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_published ON cves (published_at);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_sources ON cves USING GIN (sources);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_products ON cves USING GIN (affected_products);"
            )

            # --- FTS infrastructure (migration 006 bootstrap gap) ---
            await conn.execute("""
                CREATE OR REPLACE FUNCTION cves_search_vector_update() RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := to_tsvector('english',
                        COALESCE(NEW.cve_id, '') || ' ' ||
                        COALESCE(NEW.description, '')
                    );
                    RETURN NEW;
                END $$ LANGUAGE plpgsql;
            """)
            await conn.execute("""
                DO $$ BEGIN
                    CREATE TRIGGER trg_cves_search_vector_update
                        BEFORE INSERT OR UPDATE ON cves
                        FOR EACH ROW EXECUTE FUNCTION cves_search_vector_update();
                EXCEPTION WHEN duplicate_object THEN
                    NULL;
                END $$;
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_fts ON cves USING GIN (search_vector);"
            )

            # Phase 6 optimization indexes on cves
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_severity ON cves (cvss_v3_severity);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_severity_published ON cves (cvss_v3_severity, published_at);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_severity_score ON cves (cvss_v3_severity, cvss_v3_score DESC);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_high_severity ON cves (cve_id, cvss_v3_score DESC) WHERE cvss_v3_severity IN ('CRITICAL', 'HIGH');"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cves_severity_covering ON cves (cvss_v3_severity) INCLUDE (cve_id, cvss_v3_score, published_at);"
            )

            # --- kb_cve_edges ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_cve_edges (
                    kb_number       TEXT NOT NULL,
                    cve_id          TEXT NOT NULL,
                    source          TEXT NOT NULL,
                    os_family       TEXT,
                    advisory_id     TEXT,
                    affected_pkgs   TEXT[],
                    fixed_pkgs      TEXT[],
                    update_id       TEXT,
                    document_title  TEXT,
                    cvrf_url        TEXT,
                    published_date  TEXT,
                    severity        TEXT,
                    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (kb_number, cve_id, source),
                    CONSTRAINT fk_kb_cve_edges_cve
                        FOREIGN KEY (cve_id)
                        REFERENCES cves (cve_id)
                        ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_cve ON kb_cve_edges (cve_id);"
            )
            # Phase 6: GAP-03/04 composite (replaces dropped idx_edges_kb — R-02)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_cve_source ON kb_cve_edges (cve_id, source);"
            )

            # --- cve_scans ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cve_scans (
                    scan_id       TEXT        NOT NULL,
                    status        TEXT        NOT NULL,
                    started_at    TIMESTAMPTZ,
                    completed_at  TIMESTAMPTZ,
                    total_vms     INT         NOT NULL DEFAULT 0,
                    scanned_vms   INT         NOT NULL DEFAULT 0,
                    total_matches INT         NOT NULL DEFAULT 0,
                    error         TEXT,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT pk_cve_scans PRIMARY KEY (scan_id)
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cve_scans_status_completed ON cve_scans (status, completed_at DESC);"
            )
            # Phase 6 GAP-05: Partial index for completed scans
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scans_completed ON cve_scans (completed_at DESC, scan_id) WHERE status = 'completed';"
            )

            # --- vm_cve_match_rows ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vm_cve_match_rows (
                    scan_id        TEXT        NOT NULL,
                    vm_id          TEXT        NOT NULL,
                    vm_name        TEXT,
                    cve_id         TEXT        NOT NULL,
                    severity       TEXT,
                    cvss_score     NUMERIC(4,2),
                    published_date TIMESTAMPTZ,
                    patch_status   TEXT,
                    kb_ids         TEXT[],
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT pk_vm_cve_match_rows PRIMARY KEY (scan_id, vm_id, cve_id),
                    CONSTRAINT fk_vmcvematch_scan FOREIGN KEY (scan_id)
                        REFERENCES cve_scans (scan_id) ON DELETE CASCADE,
                    CONSTRAINT fk_vmcvematch_vm FOREIGN KEY (vm_id)
                        REFERENCES vms (resource_id) ON DELETE CASCADE,
                    CONSTRAINT fk_vmcvematch_cve FOREIGN KEY (cve_id)
                        REFERENCES cves (cve_id) ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vmcvematch_scan_severity ON vm_cve_match_rows (scan_id, severity);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vmcvematch_cve_scan ON vm_cve_match_rows (cve_id, scan_id) INCLUDE (vm_id, vm_name, patch_status);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vmcvematch_vm_scan ON vm_cve_match_rows (vm_id, scan_id) INCLUDE (cve_id, severity, cvss_score, patch_status);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vmcvematch_kb_ids ON vm_cve_match_rows USING GIN (kb_ids);"
            )

            # ==========================================================
            # VM IDENTITY SPINE (NEW — P5.1 / migration 028)
            # ==========================================================

            # --- subscriptions ---
            await conn.execute("""
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
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_subscriptions_name ON subscriptions (subscription_name);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON subscriptions (tenant_id);"
            )

            # --- vms ---
            await conn.execute("""
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
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_subscription ON vms (subscription_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_os_name ON vms (os_name);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_os_type ON vms (os_type);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_location ON vms (location);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_resource_group ON vms (resource_group);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_tags ON vms USING GIN (tags);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_last_synced ON vms (last_synced_at);"
            )
            # Phase 6 expression + composite indexes on vms
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_os_name_lower ON vms (LOWER(os_name));"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vms_subscription_os ON vms (subscription_id, os_name);"
            )

            # ==========================================================
            # INVENTORY TABLES
            # ==========================================================

            # --- resource_inventory ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_inventory (
                    id                  TEXT PRIMARY KEY,
                    subscription_id     TEXT NOT NULL,
                    resource_type       TEXT NOT NULL,
                    name                TEXT,
                    location            TEXT,
                    resource_group      TEXT,
                    properties          JSONB,
                    tags                JSONB,
                    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    normalized_os_name  TEXT,
                    normalized_os_version TEXT,
                    derivation_strategy TEXT,
                    eol_status          TEXT,
                    eol_date            TEXT,
                    risk_level          TEXT,
                    eol_confidence      NUMERIC(5, 2),
                    eol_source          TEXT
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inventory_sub ON resource_inventory (subscription_id, resource_type);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inventory_sub_lower_type ON resource_inventory (subscription_id, LOWER(resource_type));"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_inventory_normalized_os ON resource_inventory (normalized_os_name, normalized_os_version);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_inventory_name_lower ON resource_inventory (LOWER(name));"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_inventory_normalized ON resource_inventory (normalized_os_name, normalized_os_version) WHERE normalized_os_name IS NOT NULL;"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resource_inventory_eol_date ON resource_inventory (eol_date) WHERE eol_date IS NOT NULL;"
            )
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_resource_inventory_type_eol
                    ON resource_inventory (resource_type, eol_date)
                    WHERE resource_type = 'microsoft.compute/virtualmachines' AND eol_date IS NOT NULL;
            """)

            # --- resource_inventory_meta ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_inventory_meta (
                    subscription_id TEXT PRIMARY KEY,
                    last_scanned_at TIMESTAMPTZ,
                    scan_status     TEXT,
                    resource_count  INTEGER NOT NULL DEFAULT 0
                );
            """)

            # --- resource_inventory_cache_state ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_inventory_cache_state (
                    subscription_id TEXT NOT NULL,
                    resource_type   TEXT NOT NULL,
                    last_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at      TIMESTAMPTZ,
                    row_count       INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (subscription_id, resource_type)
                );
            """)

            # --- os_inventory_snapshots ---
            await conn.execute("""
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
                    PRIMARY KEY (resource_id, snapshot_version, workspace_id),
                    CONSTRAINT fk_osinvsnap_vm FOREIGN KEY (resource_id)
                        REFERENCES vms(resource_id) ON DELETE CASCADE
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_os_inventory_snapshots_resource_id ON os_inventory_snapshots (resource_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_os_inventory_computer_name_lower ON os_inventory_snapshots (LOWER(computer_name));"
            )

            # --- os_inventory_cache_state ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS os_inventory_cache_state (
                    workspace_id    TEXT    NOT NULL,
                    snapshot_version INTEGER NOT NULL DEFAULT 1,
                    last_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at      TIMESTAMPTZ,
                    row_count       INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (workspace_id, snapshot_version)
                );
            """)

            # --- inventory_os_profiles ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory_os_profiles (
                    os_key              TEXT PRIMARY KEY,
                    display_name        TEXT NOT NULL,
                    normalized_version  TEXT,
                    vendor              TEXT,
                    keyword             TEXT,
                    cpe_name            TEXT,
                    query_mode          TEXT NOT NULL DEFAULT 'auto',
                    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_bootstrap_synced_at TIMESTAMPTZ
                );
            """)

            # --- inventory_software_cache ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory_software_cache (
                    cache_key   TEXT PRIMARY KEY,
                    data        JSONB NOT NULL,
                    cached_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ttl_seconds INTEGER NOT NULL DEFAULT 3600
                );
            """)

            # --- inventory_os_cache ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory_os_cache (
                    cache_key   TEXT PRIMARY KEY,
                    data        JSONB NOT NULL,
                    cached_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    ttl_seconds INTEGER NOT NULL DEFAULT 3600
                );
            """)

            # --- Promoted migration 011 tables ---

            # --- patch_assessments_cache ---
            await conn.execute("""
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
                    PRIMARY KEY (resource_id),
                    CONSTRAINT fk_patchcache_vm FOREIGN KEY (resource_id)
                        REFERENCES vms(resource_id) ON DELETE CASCADE
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patch_cache_resource_id ON patch_assessments_cache (resource_id);"
            )
            # Phase 6 composite index
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patchcache_resource_lastmod ON patch_assessments_cache (resource_id, last_modified DESC);"
            )

            # --- available_patches ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS available_patches (
                    id              BIGSERIAL   PRIMARY KEY,
                    resource_id     TEXT        NOT NULL,
                    kb_number       TEXT,
                    title           TEXT,
                    classification  TEXT,
                    severity        TEXT,
                    reboot_required BOOLEAN     DEFAULT FALSE,
                    installed       BOOLEAN     DEFAULT FALSE,
                    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT fk_availpatches_vm FOREIGN KEY (resource_id)
                        REFERENCES vms(resource_id) ON DELETE CASCADE
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patches_resource_id ON available_patches (resource_id);"
            )

            # --- arc_software_inventory ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS arc_software_inventory (
                    id              BIGSERIAL   PRIMARY KEY,
                    resource_id     TEXT        NOT NULL,
                    software_name   TEXT,
                    software_version TEXT,
                    publisher       TEXT,
                    install_date    TEXT,
                    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT fk_arcswinv_vm FOREIGN KEY (resource_id)
                        REFERENCES vms(resource_id) ON DELETE CASCADE
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_arc_sw_inventory_resource_id ON arc_software_inventory (resource_id);"
            )

            # --- cve_vm_detections ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cve_vm_detections (
                    id              BIGSERIAL   PRIMARY KEY,
                    resource_id     TEXT        NOT NULL,
                    cve_id          TEXT        NOT NULL,
                    severity        TEXT,
                    detection_source TEXT,
                    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT fk_cvevmdet_vm FOREIGN KEY (resource_id)
                        REFERENCES vms(resource_id) ON DELETE CASCADE,
                    CONSTRAINT fk_cvevmdet_cve FOREIGN KEY (cve_id)
                        REFERENCES cves(cve_id) ON DELETE CASCADE
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cve_vm_resource_id ON cve_vm_detections (resource_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cve_vm_cve_id ON cve_vm_detections (cve_id);"
            )
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_cvevmdet_resource_cve ON cve_vm_detections (resource_id, cve_id);"
            )

            # ==========================================================
            # PATCH TABLES
            # ==========================================================

            # --- patch_installs ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS patch_installs (
                    install_id  TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    kb_number   TEXT,
                    status      TEXT,
                    started_at  TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    error       TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # ==========================================================
            # EOL TABLES
            # ==========================================================

            # --- eol_records ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS eol_records (
                    software_key            TEXT PRIMARY KEY,
                    version_key             TEXT,
                    software_name           TEXT NOT NULL,
                    version                 TEXT,
                    is_eol                  BOOLEAN NOT NULL DEFAULT FALSE,
                    eol_date                DATE,
                    status                  TEXT DEFAULT 'Unknown',
                    risk_level              TEXT DEFAULT 'Unknown',
                    item_type               TEXT DEFAULT 'os',
                    normalized_software_name TEXT,
                    normalized_version      TEXT,
                    vendor                  TEXT,
                    cycle                   TEXT,
                    latest_version          TEXT,
                    release_date            DATE,
                    lts                     BOOLEAN DEFAULT FALSE,
                    support_ended_at        DATE,
                    extended_support_ended_at DATE,
                    link                    TEXT,
                    source                  TEXT DEFAULT 'endoflife.date',
                    confidence              NUMERIC(5, 2) DEFAULT 0.0,
                    raw_response            JSONB,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_software ON eol_records (software_key, version_key);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_status ON eol_records (status, risk_level);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_item_type ON eol_records (item_type, updated_at);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_normalized ON eol_records (normalized_software_name, normalized_version);"
            )
            # Phase 6 expression index for BH-005 fuzzy JOIN
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_software_key_lower ON eol_records (LOWER(software_key));"
            )

            # --- eol_agent_responses (NEW — P5.4 / migration 030) ---
            await conn.execute("""
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
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_responses_session ON eol_agent_responses (session_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_eol_responses_timestamp ON eol_agent_responses (timestamp DESC);"
            )

            # --- os_extraction_rules ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS os_extraction_rules (
                    id          TEXT PRIMARY KEY,
                    pattern     TEXT NOT NULL,
                    os_name     TEXT NOT NULL,
                    os_version  TEXT,
                    os_type     TEXT,
                    priority    INTEGER NOT NULL DEFAULT 0,
                    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
                    source      TEXT DEFAULT 'custom',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # --- normalization_failures ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS normalization_failures (
                    id              BIGSERIAL PRIMARY KEY,
                    raw_os_string   TEXT NOT NULL,
                    source          TEXT,
                    resource_id     TEXT,
                    error_message   TEXT,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_normfail_raw ON normalization_failures (raw_os_string);"
            )

            # ==========================================================
            # ALERTING TABLES (REDESIGNED — P5.5 / migration 031)
            # ==========================================================

            # --- cve_alert_rules ---
            await conn.execute("""
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
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON cve_alert_rules (enabled);"
            )
            # Phase 6 partial index: active rules
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON cve_alert_rules (rule_id, severity_threshold) WHERE enabled = true;"
            )

            # --- cve_alert_history ---
            await conn.execute("""
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
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_rule ON cve_alert_history (rule_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_cve ON cve_alert_history (cve_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_fired ON cve_alert_history (fired_at DESC);"
            )
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_alerthistory_rule_cve ON cve_alert_history (rule_id, cve_id);"
            )
            # Phase 6 alerting optimization indexes
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_severity_fired ON cve_alert_history (severity, fired_at DESC);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_unsent ON cve_alert_history (alert_id, rule_id) WHERE notification_sent = false;"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerthistory_rule_covering ON cve_alert_history (rule_id) INCLUDE (cve_id, severity, fired_at);"
            )

            # --- alert_config ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_config (
                    config_key  TEXT PRIMARY KEY,
                    config_data JSONB NOT NULL,
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # --- notification_history ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_history (
                    id              TEXT PRIMARY KEY,
                    channel         TEXT NOT NULL,
                    recipient       TEXT,
                    subject         TEXT,
                    body            TEXT,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    sent_at         TIMESTAMPTZ,
                    error           TEXT,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # ==========================================================
            # ADMIN TABLES
            # ==========================================================

            # --- cache_ttl_config (NEW — P4.4 / migration 030) ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_ttl_config (
                    source_name  VARCHAR(50)  PRIMARY KEY,
                    ttl_tier     VARCHAR(30)  NOT NULL DEFAULT 'medium_lived',
                    ttl_seconds  INTEGER      NOT NULL DEFAULT 3600,
                    updated_at   TIMESTAMP    DEFAULT NOW(),
                    updated_by   VARCHAR(100) DEFAULT 'system'
                );
            """)
            # Seed with initial TTL values
            await conn.execute("""
                INSERT INTO cache_ttl_config (source_name, ttl_tier, ttl_seconds) VALUES
                    ('arg', 'medium_lived', 3600),
                    ('law', 'medium_lived', 3600),
                    ('msrc', 'long_lived', 86400)
                ON CONFLICT (source_name) DO NOTHING;
            """)

            # ==========================================================
            # OPERATIONAL TABLES
            # ==========================================================

            # --- workflow_contexts ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_contexts (
                    context_id  TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    agent_type  TEXT NOT NULL,
                    state       JSONB NOT NULL DEFAULT '{}',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at  TIMESTAMPTZ
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_wfctx_session_agent ON workflow_contexts (session_id, agent_type);"
            )
            # Phase 6 GAP-06: Partial index for TTL cleanup (bootstrap parity)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_wfctx_expires ON workflow_contexts (expires_at) WHERE expires_at IS NOT NULL;"
            )

            # --- audit_trail ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_trail (
                    id          BIGSERIAL PRIMARY KEY,
                    action      TEXT NOT NULL,
                    entity_type TEXT,
                    entity_id   TEXT,
                    actor       TEXT,
                    details     JSONB,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_trail (entity_type, entity_id);"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_trail (created_at DESC);"
            )

            # ==========================================================
            # SRE TABLES
            # ==========================================================

            # --- custom_runbooks ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_runbooks (
                    runbook_id  TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    description TEXT,
                    steps       JSONB NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # --- slo_definitions ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS slo_definitions (
                    slo_id      TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    description TEXT,
                    target      NUMERIC(6, 3) NOT NULL,
                    metric_type TEXT NOT NULL,
                    resource_id TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # --- slo_measurements ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS slo_measurements (
                    id          BIGSERIAL PRIMARY KEY,
                    slo_id      TEXT NOT NULL REFERENCES slo_definitions(slo_id) ON DELETE CASCADE,
                    value       NUMERIC(10, 4) NOT NULL,
                    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slo_measurements_slo_id ON slo_measurements (slo_id, measured_at DESC);"
            )

            # --- sre_incidents ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sre_incidents (
                    incident_id TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    severity    TEXT,
                    status      TEXT NOT NULL DEFAULT 'open',
                    resource_id TEXT,
                    details     JSONB,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    resolved_at TIMESTAMPTZ
                );
            """)

            # ==========================================================
            # REFERENCE TABLES
            # ==========================================================

            # --- vendor_urls ---
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vendor_urls (
                    vendor_key  TEXT PRIMARY KEY,
                    vendor_name TEXT NOT NULL,
                    eol_url     TEXT,
                    api_url     TEXT,
                    parser_type TEXT DEFAULT 'endoflife.date',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)

            # ==========================================================
            # MATERIALIZED VIEWS (with I-03 fix: check pg_matviews before CREATE)
            # ==========================================================
            await self._bootstrap_materialized_views(conn)

            logger.info("Bootstrap DDL completed successfully")

    # ------------------------------------------------------------------ #
    #  Materialized View Bootstrap — I-03 idempotent pattern
    # ------------------------------------------------------------------ #

    async def _bootstrap_materialized_views(self, conn: asyncpg.Connection) -> None:
        """Create materialized views if they do not already exist.

        Uses I-03 fix pattern: check pg_matviews before CREATE to preserve
        migration ownership.  Only CREATE + OWNER TO CURRENT_ROLE on
        fresh deployments where the MV is missing.
        """

        # ---- mv_inventory_os_cve_counts ----
        await self._create_mv_if_missing(conn, "mv_inventory_os_cve_counts", """
            CREATE MATERIALIZED VIEW mv_inventory_os_cve_counts AS
            WITH profiles AS (
                SELECT
                    os_key AS key,
                    display_name,
                    normalized_version AS version,
                    vendor,
                    keyword,
                    cpe_name,
                    CASE
                        WHEN cpe_name IS NULL THEN NULL
                        WHEN POSITION(':-:' IN cpe_name) > 0 THEN split_part(cpe_name, ':-:', 1)
                        WHEN POSITION(':*:' IN cpe_name) > 0 THEN split_part(cpe_name, ':*:', 1)
                        ELSE cpe_name
                    END AS cpe_filter,
                    query_mode,
                    last_bootstrap_synced_at AS synced_at
                FROM inventory_os_profiles
            )
            SELECT
                profiles.key,
                profiles.display_name,
                profiles.version,
                profiles.cpe_name,
                profiles.cpe_filter,
                profiles.query_mode,
                profiles.synced_at,
                COUNT(DISTINCT cves.cve_id)::int AS match_count,
                COUNT(DISTINCT cves.cve_id) FILTER (
                    WHERE UPPER(COALESCE(cves.cvss_v3_severity, 'UNKNOWN')) = 'CRITICAL'
                )::int AS critical_count,
                COUNT(DISTINCT cves.cve_id) FILTER (
                    WHERE UPPER(COALESCE(cves.cvss_v3_severity, 'UNKNOWN')) = 'HIGH'
                )::int AS high_count,
                COUNT(DISTINCT cves.cve_id) FILTER (
                    WHERE UPPER(COALESCE(cves.cvss_v3_severity, 'UNKNOWN')) = 'MEDIUM'
                )::int AS medium_count,
                COUNT(DISTINCT cves.cve_id) FILTER (
                    WHERE UPPER(COALESCE(cves.cvss_v3_severity, 'UNKNOWN')) = 'LOW'
                )::int AS low_count,
                COUNT(DISTINCT cves.cve_id) FILTER (
                    WHERE UPPER(COALESCE(cves.cvss_v3_severity, 'UNKNOWN')) NOT IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
                )::int AS unknown_count
            FROM profiles
            LEFT JOIN cves ON EXISTS (
                SELECT 1
                FROM jsonb_array_elements(
                    CASE WHEN jsonb_typeof(cves.affected_products) = 'array'
                         THEN cves.affected_products
                         ELSE '[]'::jsonb
                    END
                ) AS product
                WHERE (profiles.vendor IS NULL
                       OR LOWER(COALESCE(product->>'vendor', '')) LIKE '%%' || LOWER(profiles.vendor) || '%%')
                  AND (COALESCE(profiles.keyword, '') = ''
                       OR LOWER(regexp_replace(
                           concat_ws(' ',
                               COALESCE(product->>'vendor', ''),
                               COALESCE(product->>'product', ''),
                               COALESCE(product->>'version', '')
                           ), '[_-]+', ' ', 'g'
                       )) LIKE '%%' || LOWER(profiles.keyword) || '%%')
                  AND (profiles.cpe_filter IS NULL
                       OR LOWER(COALESCE(product->>'cpe_uri', '')) LIKE '%%' || LOWER(profiles.cpe_filter) || '%%')
            )
            GROUP BY
                profiles.key, profiles.display_name, profiles.version, profiles.cpe_name,
                profiles.cpe_filter, profiles.query_mode, profiles.synced_at;
        """, [
            "CREATE UNIQUE INDEX mv_inventory_os_cve_counts_key_idx ON mv_inventory_os_cve_counts (key);",
        ])

        # ---- mv_cve_dashboard_summary ----
        await self._create_mv_if_missing(conn, "mv_cve_dashboard_summary", """
            CREATE MATERIALIZED VIEW mv_cve_dashboard_summary AS
            SELECT
                COUNT(*)                                                                     AS total_cves,
                COUNT(CASE WHEN cvss_v3_severity = 'CRITICAL' THEN 1 END)                   AS critical,
                COUNT(CASE WHEN cvss_v3_severity = 'HIGH'     THEN 1 END)                   AS high,
                COUNT(CASE WHEN cvss_v3_severity = 'MEDIUM'   THEN 1 END)                   AS medium,
                COUNT(CASE WHEN cvss_v3_severity = 'LOW'      THEN 1 END)                   AS low,
                COUNT(CASE WHEN published_at >= NOW() - INTERVAL '7 days'                   THEN 1 END) AS age_0_7,
                COUNT(CASE WHEN published_at >= NOW() - INTERVAL '30 days'
                            AND published_at <  NOW() - INTERVAL '7 days'                   THEN 1 END) AS age_8_30,
                COUNT(CASE WHEN published_at >= NOW() - INTERVAL '90 days'
                            AND published_at <  NOW() - INTERVAL '30 days'                  THEN 1 END) AS age_31_90,
                COUNT(CASE WHEN published_at <  NOW() - INTERVAL '90 days'
                            OR  published_at IS NULL                                         THEN 1 END) AS age_90_plus,
                NOW() AS last_updated
            FROM cves;
        """, [
            "CREATE UNIQUE INDEX mv_cve_dashboard_summary_unique_idx ON mv_cve_dashboard_summary (last_updated);",
        ])

        # ---- mv_cve_top_by_score ----
        await self._create_mv_if_missing(conn, "mv_cve_top_by_score", """
            CREATE MATERIALIZED VIEW mv_cve_top_by_score AS
            SELECT
                cve_id,
                cvss_v3_severity                        AS severity,
                cvss_v3_score,
                description,
                published_at,
                affected_products
            FROM cves
            WHERE cvss_v3_score IS NOT NULL
            ORDER BY cvss_v3_score DESC;
        """, [
            "CREATE UNIQUE INDEX mv_cve_top_by_score_cve_id_idx ON mv_cve_top_by_score (cve_id);",
            "CREATE INDEX mv_cve_top_by_score_score_idx ON mv_cve_top_by_score (cvss_v3_score DESC);",
            "CREATE INDEX mv_cve_top_by_score_severity_score_idx ON mv_cve_top_by_score (severity, cvss_v3_score DESC);",
        ])

        # ---- mv_cve_exposure ----
        await self._create_mv_if_missing(conn, "mv_cve_exposure", """
            CREATE MATERIALIZED VIEW mv_cve_exposure AS
            SELECT
                m.cve_id,
                c.cvss_v3_severity                                                                AS severity,
                c.cvss_v3_score                                                                   AS cvss_score,
                c.published_at                                                                    AS published_date,
                COUNT(DISTINCT m.vm_id)                                                           AS affected_vms,
                COUNT(DISTINCT CASE WHEN m.patch_status IN ('installed')
                                    THEN m.vm_id END)                                             AS patched_vms,
                COUNT(DISTINCT CASE WHEN m.patch_status NOT IN ('installed')
                                    THEN m.vm_id END)                                             AS unpatched_vms
            FROM vm_cve_match_rows m
            JOIN cves c ON c.cve_id = m.cve_id
            WHERE m.scan_id = latest_completed_scan_id()
            GROUP BY m.cve_id, c.cvss_v3_severity, c.cvss_v3_score, c.published_at
            ORDER BY affected_vms DESC;
        """, [
            "CREATE UNIQUE INDEX mv_cve_exposure_cve_id_idx ON mv_cve_exposure (cve_id);",
            "CREATE INDEX mv_cve_exposure_severity_affected_idx ON mv_cve_exposure (severity, affected_vms DESC);",
            "CREATE INDEX mv_cve_exposure_cvss_score_idx ON mv_cve_exposure (cvss_score DESC);",
        ])

        # ---- mv_cve_trending ----
        await self._create_mv_if_missing(conn, "mv_cve_trending", """
            CREATE MATERIALIZED VIEW mv_cve_trending AS
            SELECT
                date_trunc('day', published_at)::date        AS bucket_date,
                COUNT(*)                                      AS cve_count,
                COUNT(CASE WHEN cvss_v3_severity = 'CRITICAL' THEN 1 END) AS critical_count,
                COUNT(CASE WHEN cvss_v3_severity = 'HIGH'     THEN 1 END) AS high_count
            FROM cves
            WHERE published_at IS NOT NULL
            GROUP BY 1
            ORDER BY 1;
        """, [
            "CREATE UNIQUE INDEX mv_cve_trending_bucket_date_unique_idx ON mv_cve_trending (bucket_date);",
            "CREATE INDEX mv_cve_trending_bucket_date_idx ON mv_cve_trending (bucket_date DESC);",
        ])

        # ---- mv_vm_vulnerability_posture (MODIFIED — P5.6, sources from vms) ----
        await self._create_mv_if_missing(conn, "mv_vm_vulnerability_posture", """
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
        """, [
            "CREATE UNIQUE INDEX mv_vm_vulnerability_posture_vm_id_idx ON mv_vm_vulnerability_posture (vm_id);",
            "CREATE INDEX mv_vm_vulnerability_posture_risk_total_idx ON mv_vm_vulnerability_posture (risk_level, total_cves DESC);",
            "CREATE INDEX mv_vm_vulnerability_posture_sub_rg_idx ON mv_vm_vulnerability_posture (subscription_id, resource_group);",
            "CREATE INDEX mv_vm_vulnerability_posture_vm_type_idx ON mv_vm_vulnerability_posture (vm_type);",
        ])

        # ---- mv_vm_cve_detail ----
        await self._create_mv_if_missing(conn, "mv_vm_cve_detail", """
            CREATE MATERIALIZED VIEW mv_vm_cve_detail AS
            SELECT
                m.scan_id,
                m.vm_id,
                m.vm_name,
                m.cve_id,
                m.severity,
                m.cvss_score,
                m.published_date,
                m.patch_status,
                m.kb_ids,
                c.description,
                c.cvss_v3_vector,
                c.cvss_v2_score,
                c.cwe_ids,
                c.affected_products,
                EXISTS(
                    SELECT 1 FROM kb_cve_edges k WHERE k.cve_id = m.cve_id
                ) AS has_kb_patch
            FROM vm_cve_match_rows m
            LEFT JOIN cves c ON c.cve_id = m.cve_id;
        """, [
            "CREATE UNIQUE INDEX mv_vm_cve_detail_scan_vm_cve_idx ON mv_vm_cve_detail (scan_id, vm_id, cve_id);",
            "CREATE INDEX mv_vm_cve_detail_vm_severity_score_idx ON mv_vm_cve_detail (scan_id, vm_id, severity, cvss_score DESC);",
            "CREATE INDEX mv_vm_cve_detail_scan_cve_idx ON mv_vm_cve_detail (scan_id, cve_id);",
        ])

        # NOTE: 3 migration-011 MVs (vm_vulnerability_overview, cve_dashboard_stats,
        # os_cve_inventory_counts) are NOT created in bootstrap — they were dropped
        # in migration 027.

    async def _create_mv_if_missing(
        self,
        conn: asyncpg.Connection,
        mv_name: str,
        create_ddl: str,
        index_ddls: Optional[List[str]] = None,
    ) -> None:
        """Create a materialized view only if it does not already exist.

        I-03 fix: preserves migration ownership by skipping CREATE when
        the MV already exists.  On fresh CREATE, sets OWNER TO CURRENT_ROLE.
        """
        row = await conn.fetchval(
            "SELECT 1 FROM pg_matviews WHERE matviewname = $1", mv_name
        )
        if row is not None:
            logger.debug("MV %s already exists, skipping CREATE (I-03 fix)", mv_name)
            return

        logger.info("Creating materialized view %s", mv_name)
        await conn.execute(create_ddl)

        # Set ownership to the current role for CONCURRENT refresh
        await conn.execute(
            f"ALTER MATERIALIZED VIEW {mv_name} OWNER TO CURRENT_ROLE"
        )

        # Create indexes on the new MV
        if index_ddls:
            for idx_ddl in index_ddls:
                await conn.execute(idx_ddl)

    # ================================================================== #
    #  Schema Validation
    # ================================================================== #

    async def ensure_runtime_schema(self) -> None:
        """Validate that all required tables and relations exist.

        If any table is missing, runs the full bootstrap DDL.
        Then validates FK relationships.
        """
        async with self._pool.acquire() as conn:
            # Check for missing tables
            existing = set()
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            for r in rows:
                existing.add(r["tablename"])

            missing_tables = [
                t for t in self._REQUIRED_TABLES if t not in existing
            ]

            if missing_tables:
                logger.warning(
                    "Missing %d required table(s): %s — running bootstrap DDL",
                    len(missing_tables),
                    ", ".join(missing_tables[:5]),
                )
                await self._bootstrap_runtime_schema()
                logger.info("Bootstrap DDL complete")

            # Validate FK relationships
            for child_tbl, child_col, parent_tbl, parent_col in self._REQUIRED_RELATIONS:
                has_fk = await conn.fetchval("""
                    SELECT 1
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                        ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_name = $1
                      AND kcu.column_name = $2
                      AND ccu.table_name = $3
                      AND ccu.column_name = $4
                """, child_tbl, child_col, parent_tbl, parent_col)

                if has_fk is None:
                    logger.warning(
                        "Missing FK: %s.%s -> %s.%s — re-running bootstrap",
                        child_tbl, child_col, parent_tbl, parent_col,
                    )
                    await self._bootstrap_runtime_schema()
                    break  # Full bootstrap covers all FKs

            logger.info("Schema validation complete")
