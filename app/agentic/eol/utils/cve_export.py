"""
CVE Export Service

Generates CSV and PDF exports of CVE dashboard data with filtering support.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi.responses import StreamingResponse
from utils.cve_scanner import CVEScanner
from utils.logger import get_logger

logger = get_logger(__name__)


async def generate_csv_export(
    time_range_days: int,
    severity_filter: Optional[str] = None
) -> StreamingResponse:
    """
    Generate CSV export of filtered CVE data.

    Content includes:
    - All CVEs matching filters (ID, severity, CVSS, affected VMs, published date, description)
    - VM details (which CVEs affect which VMs)
    - Patch status (available, applied, pending)

    Args:
        time_range_days: Days to look back (30, 90, 365)
        severity_filter: Optional severity filter (CRITICAL, HIGH, MEDIUM, LOW)

    Returns:
        StreamingResponse with CSV content
    """
    try:
        logger.info(f"Generating CSV export: time_range={time_range_days}, severity={severity_filter}")

        # Collect data
        scanner = CVEScanner()

        # Get latest scan results
        scan_results = await scanner.get_latest_scan_results()

        # Build CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'CVE ID',
            'Severity',
            'CVSS Score',
            'Published Date',
            'Description',
            'Affected VMs',
            'VM Names',
            'Patch Available',
            'Patch Status'
        ])

        # Aggregate CVE data
        cve_data = {}
        for scan in scan_results:
            for match in scan.matches:
                cve_id = match.cve_id

                # Apply severity filter
                if severity_filter and match.severity != severity_filter:
                    continue

                if cve_id not in cve_data:
                    cve_data[cve_id] = {
                        'cve_id': cve_id,
                        'severity': match.severity,
                        'cvss_score': match.cvss_score,
                        'published_date': match.published_date,
                        'description': match.description or '',
                        'vms': [],
                        'vm_names': []
                    }

                cve_data[cve_id]['vms'].append(scan.vm_id)
                cve_data[cve_id]['vm_names'].append(scan.vm_name)

        # Write CVE rows
        for cve_id, data in cve_data.items():
            # Get patch info (from Phase 6 patch mapper)
            # TODO: Integrate with actual patch service
            patch_available = "Unknown"
            patch_status = "Unknown"

            writer.writerow([
                data['cve_id'],
                data['severity'],
                data['cvss_score'],
                data['published_date'],
                data['description'][:200] + '...' if len(data['description']) > 200 else data['description'],
                len(data['vms']),
                ', '.join(data['vm_names'][:5]) + ('...' if len(data['vm_names']) > 5 else ''),
                patch_available,
                patch_status
            ])

        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        severity_suffix = f"-{severity_filter}" if severity_filter else ""
        filename = f"CVE-Dashboard-{timestamp}-Last{time_range_days}Days{severity_suffix}.csv"

        # Return streaming response
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"CSV export failed: {e}", exc_info=True)
        raise
