from unittest.mock import AsyncMock, patch

import pytest

from api import cve_scan


@pytest.mark.asyncio
async def test_get_scan_status_uses_lightweight_summary_path():
    repository = AsyncMock()
    repository.get_status_summary = AsyncMock(return_value={
        "scan_id": "scan-123",
        "status": "completed",
        "total_vms": 8,
        "scanned_vms": 8,
        "total_matches": 3000,
        "started_at": "2026-03-10T00:00:00+00:00",
        "completed_at": "2026-03-10T00:01:00+00:00",
        "error": None,
    })

    with patch("api.cve_scan._get_scan_repository", AsyncMock(return_value=repository)):
        response = await cve_scan.get_scan_status("scan-123")

    assert response.success is True
    assert response.data["scan_id"] == "scan-123"
    assert response.data["progress"] == 100
    assert response.data["matches_found"] == 3000
    repository.get_status_summary.assert_awaited_once_with("scan-123")


@pytest.mark.asyncio
async def test_get_scan_status_returns_404_when_missing():
    repository = AsyncMock()
    repository.get_status_summary = AsyncMock(return_value=None)

    with patch("api.cve_scan._get_scan_repository", AsyncMock(return_value=repository)):
        with pytest.raises(cve_scan.HTTPException) as exc_info:
            await cve_scan.get_scan_status("missing-scan")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_recent_scans_omits_heavy_match_payloads():
    repository = AsyncMock()
    repository.list_status_summaries = AsyncMock(return_value=[])

    with patch("api.cve_scan._get_scan_repository", AsyncMock(return_value=repository)):
        response = await cve_scan.list_recent_scans(limit=10)

    assert response.success is True
    assert response.data["scans"] == []
    assert response.data["count"] == 0
    repository.list_status_summaries.assert_awaited_once_with(limit=10)