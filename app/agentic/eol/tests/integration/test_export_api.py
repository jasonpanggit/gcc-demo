"""
Integration Tests for CVE Export API

Tests export endpoints with FastAPI test client.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    """Create test client."""
    # Import app after patching dependencies
    with patch('main.get_cve_analytics'):
        from main import app
        return TestClient(app)


def test_csv_export_endpoint(client):
    """Test CSV export endpoint returns file."""
    with patch('utils.cve_export.CVEScanner') as mock_scanner:
        mock_scanner.return_value.get_latest_scan_results = AsyncMock(return_value=[])

        response = client.get("/api/cve/export?format=csv&time_range=30")

        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/csv'
        assert 'CVE-Dashboard-' in response.headers['content-disposition']


def test_pdf_export_endpoint(client):
    """Test PDF export endpoint with chart images."""
    with patch('main.get_cve_analytics') as mock_analytics:
        # Mock analytics service
        mock_service = AsyncMock()
        mock_service.get_summary_stats = AsyncMock(return_value={
            'total_cves': 10,
            'critical': 2,
            'high': 3,
            'medium': 3,
            'low': 2
        })
        mock_service.get_top_cves_by_exposure = AsyncMock(return_value=[])
        mock_service.get_vm_vulnerability_posture = AsyncMock(return_value=[])
        mock_service.get_aging_distribution = AsyncMock(return_value={})
        mock_service.calculate_mttp = AsyncMock(return_value=12.5)
        mock_analytics.return_value = mock_service

        with patch('utils.cve_export.WEASYPRINT_AVAILABLE', True):
            with patch('utils.cve_export.HTML') as mock_html:
                mock_html.return_value.write_pdf.return_value = b'%PDF-1.4\n%content'

                payload = {
                    'format': 'pdf',
                    'time_range': 30,
                    'severity': 'CRITICAL',
                    'chart_images': {
                        'donut': 'data:image/png;base64,iVBORw0KGgo...',
                        'line': 'data:image/png;base64,iVBORw0KGgo...',
                        'aging': 'data:image/png;base64,iVBORw0KGgo...'
                    }
                }

                response = client.post("/api/cve/export", json=payload)

                assert response.status_code == 200
                assert response.headers['content-type'] == 'application/pdf'
                assert 'CVE-Dashboard-' in response.headers['content-disposition']


def test_export_invalid_format(client):
    """Test export endpoint rejects invalid format."""
    response = client.get("/api/cve/export?format=invalid")

    assert response.status_code == 400
    assert "only supports format=csv" in response.json()['detail']


def test_pdf_export_invalid_format(client):
    """Test PDF endpoint rejects non-pdf format."""
    payload = {
        'format': 'csv',
        'time_range': 30
    }

    response = client.post("/api/cve/export", json=payload)

    assert response.status_code == 400
    assert "only supports format=pdf" in response.json()['detail']
