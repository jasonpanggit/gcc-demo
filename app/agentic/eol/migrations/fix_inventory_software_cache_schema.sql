-- Migration: Add missing ttl_seconds column to inventory_software_cache
-- Symptom: WARNING: Failed to persist software inventory to postgres:
--          column "ttl_seconds" of relation "inventory_software_cache" does not exist
--
-- Root cause: The table was created before the ttl_seconds column was added to the
--             CREATE TABLE DDL in pg_database.py (bootstrap path). The bootstrap
--             DDL uses CREATE TABLE IF NOT EXISTS, so once the table exists it
--             never re-runs, leaving the column absent in already-deployed DBs.
--
-- Fix: Add the column with IF NOT EXISTS guard so this migration is safe to run
--      multiple times and on DBs that already have the column.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_name  = 'inventory_software_cache'
          AND  column_name = 'ttl_seconds'
    ) THEN
        ALTER TABLE inventory_software_cache
            ADD COLUMN ttl_seconds INTEGER NOT NULL DEFAULT 3600;
        RAISE NOTICE 'Added ttl_seconds column to inventory_software_cache';
    ELSE
        RAISE NOTICE 'Column ttl_seconds already exists on inventory_software_cache — no-op';
    END IF;
END $$;
