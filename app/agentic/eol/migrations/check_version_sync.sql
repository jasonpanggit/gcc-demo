-- Check detailed data in snapshots
SELECT computer_name, os_name, os_version, os_type
FROM os_inventory_snapshots
ORDER BY computer_name;

-- Check what's in vms for Arc machines
SELECT vm_name, os_name, os_type
FROM vms
WHERE resource_id LIKE '%HybridCompute%'
ORDER BY vm_name;

-- Check if vms table has os_version column
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'vms' AND column_name LIKE '%version%';
