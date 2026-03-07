"""
Tests for CVE Export Service

Tests CSV and PDF export functionality with filtering and formatting.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from utils.cve_export import generate_csv_export, generate_pdf_export


@pytest.mark.asyncio
async def test_csv_export_generates_valid_csv():
    """Test CSV export creates valid CSV content."""
    with patch('utils.cve_export.CVEScanner') as mock_scanner:
        # Mock scan results
        mock_scan_results = [
            MagicMock(
                vm_id='vm-001',
                vm_name='web-server-01',
                matches=[
                    MagicMock(
                        cve_id='CVE-2024-0001',
                        severity='CRITICAL',
                        cvss_score=9.8,
                        published_date='2024-01-15',
                        description='Remote code execution vulnerability'
                    )
                ]
            )
        ]

        mock_scanner.return_value.get_latest_scan_results = AsyncMock(return_value=mock_scan_results)

        response = await generate_csv_export(time_range_days=30)

        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/csv'
        assert 'attachment' in response.headers['content-disposition']

        # Read CSV content
        content = b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8')

        # Verify header row
        assert 'CVE ID' in content
        assert 'Severity' in content
        assert 'Affected VMs' in content


@pytest.mark.asyncio
async def test_csv_export_filename_format():
    """Test CSV filename includes timestamp and filters."""
    with patch('utils.cve_export.CVEScanner') as mock_scanner:
        mock_scanner.return_value.get_latest_scan_results = AsyncMock(return_value=[])

        response = await generate_csv_export(
            time_range_days=90,
            severity_filter='CRITICAL'
        )

        filename = response.headers['content-disposition']
        assert 'CVE-Dashboard-' in filename
        assert 'Last90Days' in filename
        assert 'CRITICAL' in filename
        assert '.csv' in filename


@pytest.mark.asyncio
async def test_csv_export_applies_severity_filter():
    """Test CSV export respects severity filter."""
    with patch('utils.cve_export.CVEScanner') as mock_scanner:
        # Mock scan results with mixed severities
        mock_scan_results = [
            MagicMock(
                vm_id='vm-001',
                vm_name='web-server-01',
                matches=[
                    MagicMock(
                        cve_id='CVE-2024-0001',
                        severity='HIGH',
                        cvss_score=7.5,
                        published_date='2024-01-15',
                        description='High severity issue'
                    ),
                    MagicMock(
                        cve_id='CVE-2024-0002',
                        severity='CRITICAL',
                        cvss_score=9.8,
                        published_date='2024-01-20',
                        description='Critical severity issue'
                    )
                ]
            )
        ]

        mock_scanner.return_value.get_latest_scan_results = AsyncMock(return_value=mock_scan_results)

        response = await generate_csv_export(
            time_range_days=30,
            severity_filter='HIGH'
        )

        content = b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8')
        lines = content.split('\n')

        # Should only include HIGH severity CVEs
        assert 'CVE-2024-0001' in content
        assert 'HIGH' in content
        # Should NOT include CRITICAL CVE
        assert 'CVE-2024-0002' not in content


@pytest.mark.asyncio
async def test_pdf_export_generates_valid_pdf():
    """Test PDF export creates valid PDF document."""
    mock_data = {
        'summary': {
            'total_cves': 100,
            'critical': 10,
            'high': 30,
            'medium': 40,
            'low': 20,
            'mttp_days': 12.5
        },
        'top_cves': [
            {
                'cve_id': 'CVE-2024-0001',
                'severity': 'CRITICAL',
                'cvss_score': 9.8,
                'affected_vms': 5
            }
        ],
        'vm_posture': [
            {
                'vm_name': 'web-server-01',
                'vm_id': 'vm-001',
                'cve_count': 15,
                'highest_severity': 'CRITICAL'
            }
        ],
        'aging': {'0-7_days': 10, '8-30_days': 20, '31-90_days': 30, '90+_days': 40}
    }

    mock_charts = {
        'donut': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        'line': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        'aging': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    }

    with patch('utils.cve_export.WEASYPRINT_AVAILABLE', True):
        with patch('utils.cve_export.HTML') as mock_html:
            # Mock WeasyPrint HTML object
            mock_html.return_value.write_pdf.return_value = b'%PDF-1.4\n%fake-pdf-content'

            response = await generate_pdf_export(
                dashboard_data=mock_data,
                chart_images=mock_charts,
                time_range_days=30
            )

            assert response.status_code == 200
            assert response.headers['content-type'] == 'application/pdf'
            assert 'attachment' in response.headers['content-disposition']

            # Verify PDF magic number
            content = b''.join([chunk async for chunk in response.body_iterator])
            assert content.startswith(b'%PDF')


@pytest.mark.asyncio
async def test_pdf_export_filename_format():
    """Test PDF filename includes timestamp and filters."""
    mock_data = {'summary': {}, 'top_cves': [], 'vm_posture': [], 'aging': {}}
    mock_charts = {}

    with patch('utils.cve_export.WEASYPRINT_AVAILABLE', True):
        with patch('utils.cve_export.HTML') as mock_html:
            mock_html.return_value.write_pdf.return_value = b'%PDF-1.4\n%fake-pdf-content'

            response = await generate_pdf_export(
                dashboard_data=mock_data,
                chart_images=mock_charts,
                time_range_days=365,
                severity_filter='CRITICAL'
            )

            filename = response.headers['content-disposition']
            assert 'CVE-Dashboard-' in filename
            assert 'Last365Days' in filename
            assert 'CRITICAL' in filename
            assert '.pdf' in filename


@pytest.mark.asyncio
async def test_pdf_export_fails_without_weasyprint():
    """Test PDF export returns error when WeasyPrint unavailable."""
    mock_data = {'summary': {}, 'top_cves': [], 'vm_posture': [], 'aging': {}}
    mock_charts = {}

    with patch('utils.cve_export.WEASYPRINT_AVAILABLE', False):
        with pytest.raises(RuntimeError, match="PDF export unavailable"):
            await generate_pdf_export(
                dashboard_data=mock_data,
                chart_images=mock_charts,
                time_range_days=30
            )
