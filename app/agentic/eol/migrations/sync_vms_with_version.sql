-- Sync OS data from os_inventory_snapshots to vms table
-- Concatenate os_name + os_version for proper CVE matching
UPDATE vms
SET
    os_name = CASE
        WHEN osi.os_version IS NOT NULL AND osi.os_version != ''
        THEN osi.os_name || ' ' || osi.os_version
        ELSE COALESCE(osi.os_name, vms.os_name)
    END,
    os_type = COALESCE(osi.os_type, vms.os_type)
FROM os_inventory_snapshots osi
WHERE vms.resource_id = osi.resource_id;

-- Verify the Arc VMs now have correct OS data with versions
SELECT resource_id, vm_name, os_name, os_type
FROM vms
WHERE resource_id LIKE '%HybridCompute%'
ORDER BY vm_name;

-- Check all VMs
SELECT vm_name, os_name, os_type
FROM vms
ORDER BY vm_name;
