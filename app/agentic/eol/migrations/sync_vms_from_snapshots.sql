-- Sync OS data from os_inventory_snapshots to vms table
UPDATE vms
SET
    os_name = COALESCE(osi.os_name, vms.os_name),
    os_type = COALESCE(osi.os_type, vms.os_type)
FROM os_inventory_snapshots osi
WHERE vms.resource_id = osi.resource_id;

-- Verify the Arc VMs now have correct OS data
SELECT resource_id, vm_name, os_name, os_type
FROM vms
WHERE resource_id LIKE '%HybridCompute%'
ORDER BY vm_name;
