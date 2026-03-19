-- Check Arc VMs in vms table
SELECT resource_id, vm_name, os_name, os_type
FROM vms
WHERE resource_id LIKE '%HybridCompute%'
ORDER BY vm_name;

-- Check all VMs count
SELECT COUNT(*) as total_vms FROM vms;
