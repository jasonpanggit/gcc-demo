-- Show primary key definition
SELECT a.attname AS column_name
FROM pg_index i
JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
WHERE i.indrelid = 'os_inventory_snapshots'::regclass
  AND i.indisprimary
ORDER BY a.attnum;
