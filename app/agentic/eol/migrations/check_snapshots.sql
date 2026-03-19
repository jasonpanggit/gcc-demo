SELECT COUNT(*) as row_count FROM os_inventory_snapshots;
SELECT workspace_id, computer_name, os_name, os_version, os_type, resource_id, cached_at
FROM os_inventory_snapshots
ORDER BY cached_at DESC
LIMIT 5;
