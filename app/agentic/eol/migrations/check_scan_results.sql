-- Check latest CVE scan results
SELECT scan_id, status, started_at, completed_at, total_vms_scanned, total_cve_matches
FROM cve_scans
ORDER BY started_at DESC
LIMIT 3;

-- Check VM matches from latest scan
SELECT COUNT(DISTINCT vm_resource_id) as vms_with_matches
FROM cve_vm_detections
WHERE scan_id = (SELECT scan_id FROM cve_scans ORDER BY started_at DESC LIMIT 1);

-- Check all VMs that have been scanned
SELECT COUNT(DISTINCT resource_id) as total_scanned_vms
FROM vm_cve_matches;
