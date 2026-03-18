-- Migration: Create cve_sync_os_summary table
-- Purpose: Persist CVE sync metadata per OS identity for dashboard display
-- Date: 2026-03-18

-- Create the table
CREATE TABLE IF NOT EXISTS cve_sync_os_summary (
    id SERIAL PRIMARY KEY,
    os_key VARCHAR(255) NOT NULL UNIQUE,  -- e.g., "windows server::2016"
    normalized_name VARCHAR(255) NOT NULL,
    normalized_version VARCHAR(100),
    display_name VARCHAR(255) NOT NULL,
    query_mode VARCHAR(50),  -- "cpe" or "keyword"
    cached_cve_count INTEGER NOT NULL DEFAULT 0,
    synced_at TIMESTAMPTZ NOT NULL,
    sync_metadata JSONB,  -- Full sync entry details
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_cve_sync_os_summary_name ON cve_sync_os_summary(normalized_name);
CREATE INDEX IF NOT EXISTS idx_cve_sync_os_summary_synced_at ON cve_sync_os_summary(synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_cve_sync_os_summary_cve_count ON cve_sync_os_summary(cached_cve_count DESC);

-- Add comments for documentation
COMMENT ON TABLE cve_sync_os_summary IS 'CVE sync metadata per OS identity for dashboard display';
COMMENT ON COLUMN cve_sync_os_summary.os_key IS 'Unique OS identity key: normalized_name::normalized_version';
COMMENT ON COLUMN cve_sync_os_summary.normalized_name IS 'Normalized OS name (e.g., windows server, ubuntu)';
COMMENT ON COLUMN cve_sync_os_summary.normalized_version IS 'Normalized OS version (e.g., 2016, 20.04)';
COMMENT ON COLUMN cve_sync_os_summary.display_name IS 'Human-readable OS name for UI display';
COMMENT ON COLUMN cve_sync_os_summary.query_mode IS 'Sync query mode: cpe (CPE name query) or keyword (text search)';
COMMENT ON COLUMN cve_sync_os_summary.cached_cve_count IS 'Number of CVEs cached for this OS during last sync';
COMMENT ON COLUMN cve_sync_os_summary.synced_at IS 'Timestamp when this OS was last synced';
COMMENT ON COLUMN cve_sync_os_summary.sync_metadata IS 'Full sync entry: query details, errors, raw examples';

-- Grant permissions to managed identity user (eol-app-identity)
-- Replace 'eol-app-identity' with actual managed identity username if different
DO $$
BEGIN
    -- Check if the role exists and grant permissions
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eol-app-identity') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON cve_sync_os_summary TO "eol-app-identity";
        GRANT USAGE, SELECT ON SEQUENCE cve_sync_os_summary_id_seq TO "eol-app-identity";
        RAISE NOTICE 'Granted permissions to eol-app-identity';
    ELSE
        RAISE NOTICE 'Role eol-app-identity does not exist - skipping grants';
    END IF;
END $$;

-- Migration verification queries
-- SELECT COUNT(*) FROM cve_sync_os_summary;
-- SELECT * FROM cve_sync_os_summary ORDER BY cached_cve_count DESC LIMIT 10;
