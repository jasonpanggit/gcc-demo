-- Fix os_inventory_snapshots schema to match migration 030
-- Add missing columns: snapshot_version and ttl_seconds

-- Add snapshot_version if missing
DO $$ BEGIN
    ALTER TABLE os_inventory_snapshots ADD COLUMN IF NOT EXISTS snapshot_version INTEGER NOT NULL DEFAULT 1;
EXCEPTION WHEN duplicate_column THEN
    RAISE NOTICE 'Column snapshot_version already exists';
END $$;

-- Add ttl_seconds if missing
DO $$ BEGIN
    ALTER TABLE os_inventory_snapshots ADD COLUMN IF NOT EXISTS ttl_seconds INTEGER NOT NULL DEFAULT 3600;
EXCEPTION WHEN duplicate_column THEN
    RAISE NOTICE 'Column ttl_seconds already exists';
END $$;

-- Verify schema
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'os_inventory_snapshots'
ORDER BY ordinal_position;
