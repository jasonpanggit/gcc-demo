-- Fix os_inventory_snapshots schema to match migration 030
-- This table exists with wrong PK - need to drop and recreate

-- Drop the existing table (CASCADE to handle any FKs)
DROP TABLE IF EXISTS os_inventory_snapshots CASCADE;

-- Recreate with correct schema from migration 030
CREATE TABLE os_inventory_snapshots (
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

-- Add FK back to vms table
ALTER TABLE os_inventory_snapshots
    ADD CONSTRAINT fk_osinvsnap_vm
    FOREIGN KEY (resource_id) REFERENCES vms(resource_id) ON DELETE CASCADE;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_os_inventory_snapshots_resource_id
    ON os_inventory_snapshots (resource_id);

CREATE INDEX IF NOT EXISTS idx_os_inventory_computer_name_lower
    ON os_inventory_snapshots (LOWER(computer_name));

-- Verify the new schema
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'os_inventory_snapshots'
ORDER BY ordinal_position;

-- Verify constraints
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'os_inventory_snapshots'
ORDER BY constraint_type, constraint_name;
