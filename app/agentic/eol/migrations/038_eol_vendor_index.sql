-- Migration 038: Add index on vendor column for vendor-scoped queries
-- Supports the new GET /api/eol-inventory/vendor/{vendor} endpoint

-- Index for vendor-scoped queries (ILIKE on LOWER(vendor))
CREATE INDEX IF NOT EXISTS idx_eol_vendor ON eol_records (LOWER(vendor));

-- Backfill vendor from source where vendor is NULL and source is available
UPDATE eol_records SET vendor = source WHERE vendor IS NULL AND source IS NOT NULL;
