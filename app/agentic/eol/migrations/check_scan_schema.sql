-- Check cve_scans table schema
SELECT column_name FROM information_schema.columns WHERE table_name = 'cve_scans' ORDER BY ordinal_position;

-- Check latest scans
SELECT scan_id, status, started_at, completed_at, subscription_id
FROM cve_scans
ORDER BY started_at DESC
LIMIT 3;

-- Check if any CVE detections exist
SELECT COUNT(*) as total_detections FROM cve_vm_detections;

-- Check VMs table
SELECT COUNT(*) as total_vms FROM vms;
