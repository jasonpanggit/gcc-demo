-- Migration 042: Add gen_random_uuid()::text default to eol_records.id
-- The id column has no default, causing INSERT failures when callers omit it.
-- Adding a default auto-generates a UUID so all upsert paths work without
-- explicitly providing an id.

ALTER TABLE eol_records
    ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;

-- Verify
SELECT column_name, column_default
FROM information_schema.columns
WHERE table_name = 'eol_records' AND column_name = 'id';
