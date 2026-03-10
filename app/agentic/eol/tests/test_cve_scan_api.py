from unittest.mock import AsyncMock, patch

import pytest

from api import cve_scan


@pytest.mark.asyncio
async def test_get_scan_status_uses_lightweight_summary_path():
    scanner = AsyncMock()
    scanner.get_scan_status_summary = AsyncMock(return_value={
        "scan_id": "scan-123",
        "status": "completed",
        "total_vms": 8,
        "scanned_vms": 8,
        "total_matches": 3000,
        "started_at": "2026-03-10T00:00:00+00:00",
        "completed_at": "2026-03-10T00:01:00+00:00",
        "error": None,
    })
    scanner.get_scan_status = AsyncMock(side_effect=AssertionError("heavy status path should not be used"))

    with patch("api.cve_scan._get_cve_scanner", AsyncMock(return_value=scanner)):
        response = await cve_scan.get_scan_status("scan-123")

    assert response.success is True
    assert response.data["scan_id"] == "scan-123"
    assert response.data["progress"] == 100
    assert response.data["matches_found"] == 3000
    scanner.get_scan_status_summary.assert_awaited_once_with("scan-123")
    scanner.get_scan_status.assert_not_called()


@pytest.mark.asyncio
async def test_get_scan_status_returns_404_when_missing():
    scanner = AsyncMock()
    scanner.get_scan_status_summary = AsyncMock(return_value=None)

    with patch("api.cve_scan._get_cve_scanner", AsyncMock(return_value=scanner)):
        with pytest.raises(cve_scan.HTTPException) as exc_info:
            await cve_scan.get_scan_status("missing-scan")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_recent_scans_omits_heavy_match_payloads():
    scanner = AsyncMock()
    scanner.list_recent_scans = AsyncMock(return_value=[])

    with patch("api.cve_scan._get_cve_scanner", AsyncMock(return_value=scanner)):
        response = await cve_scan.list_recent_scans(limit=10)

    assert response.success is True
    assert response.data["scans"] == []
    assert response.data["count"] == 0
    scanner.list_recent_scans.assert_awaited_once_with(limit=10)