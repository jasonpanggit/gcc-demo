"""
CVE Export Service

Generates CSV and PDF exports of CVE dashboard data with filtering support.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi.responses import StreamingResponse
from jinja2 import Environment, FileSystemLoader
from utils.cve_scanner import CVEScanner
from utils.logger import get_logger

logger = get_logger(__name__)

# WeasyPrint import with fallback
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not available - PDF export will fail. Install system dependencies and weasyprint.")


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


async def generate_pdf_export(
    dashboard_data: dict,
    chart_images: dict,
    time_range_days: int,
    severity_filter: Optional[str] = None
) -> StreamingResponse:
    """
    Generate PDF report with charts and summary tables.

    Content includes:
    - Cover page with summary metrics
    - Severity breakdown chart (as PNG image)
    - Trending chart (as PNG image)
    - Aging distribution chart (as PNG image)
    - Top 10 CVEs table
    - VM posture table
    - Footer with timestamp and filters

    Args:
        dashboard_data: Dashboard metrics from API
        chart_images: Dict of chart base64 images {'donut': 'data:image/png;base64,...', ...}
        time_range_days: Days to look back
        severity_filter: Optional severity filter

    Returns:
        StreamingResponse with PDF content
    """
    try:
        logger.info(f"Generating PDF export: time_range={time_range_days}, severity={severity_filter}")

        # Check WeasyPrint availability
        if not WEASYPRINT_AVAILABLE:
            raise RuntimeError(
                "PDF export unavailable - WeasyPrint not installed. "
                "Install system dependencies (cairo, pango) and weasyprint package."
            )

        # Load Jinja2 template
        env = Environment(loader=FileSystemLoader('templates/pdf'))
        template = env.get_template('cve-dashboard-report.html')

        # Render HTML with data
        html_content = template.render(
            summary=dashboard_data['summary'],
            top_cves=dashboard_data['top_cves'],
            vm_posture=dashboard_data['vm_posture'],
            aging=dashboard_data['aging'],
            chart_donut=chart_images.get('donut', ''),
            chart_line=chart_images.get('line', ''),
            chart_aging=chart_images.get('aging', ''),
            timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            time_range_days=time_range_days,
            severity_filter=severity_filter or 'All'
        )

        # Generate PDF with WeasyPrint
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        severity_suffix = f"-{severity_filter}" if severity_filter else ""
        filename = f"CVE-Dashboard-{timestamp}-Last{time_range_days}Days{severity_suffix}.pdf"

        # Return streaming response
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"PDF export failed: {e}", exc_info=True)
        raise
