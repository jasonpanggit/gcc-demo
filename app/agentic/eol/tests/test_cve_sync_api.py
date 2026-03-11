from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api import cve_sync


@pytest.mark.asyncio
async def test_trigger_full_sync_only_bootstraps_new_inventory_os():
    cve_service = AsyncMock()
    cve_scanner = AsyncMock()
    eol_orchestrator = SimpleNamespace()
    inventory_sync_result = {
        "discovered_os_count": 3,
        "new_os_count": 1,
        "processed_os_count": 1,
        "os_entries": [{"key": "windows server::2022", "query_mode": "cpe"}],
    }
    delta_sync_result = {
        "cve_count": 42,
        "since_date": datetime(2026, 3, 10, tzinfo=timezone.utc),
        "used_fallback_window": False,
    }

    with patch("main.get_cve_service", AsyncMock(return_value=cve_service)), \
         patch("main.get_cve_scanner", AsyncMock(return_value=cve_scanner)), \
         patch("main.get_eol_orchestrator", return_value=eol_orchestrator), \
         patch("api.cve_sync.run_inventory_bootstrap_sync", AsyncMock(return_value=inventory_sync_result)) as mock_inventory_sync, \
         patch("api.cve_sync.run_delta_sync", AsyncMock(return_value=delta_sync_result)) as mock_delta_sync:
        response = await cve_sync.trigger_full_sync(
            lookback_days=7,
            force_inventory_resync=True,
        )

    mock_inventory_sync.assert_awaited_once_with(
        cve_service=cve_service,
        cve_scanner=cve_scanner,
        eol_orchestrator=eol_orchestrator,
        limit_per_os=None,
        force_resync=False,
    )
    mock_delta_sync.assert_awaited_once()
    assert response.success is True
    assert response.data["cve_count"] == 42
    assert response.data["inventory_os_processed"] == 1
    assert response.data["force_inventory_resync"] is False
    assert response.data["inventory_sync_mode"] == "new-only"


@pytest.mark.asyncio
async def test_trigger_incremental_sync_runs_delta_without_full_fallback():
    cve_service = AsyncMock()
    cve_scanner = AsyncMock()
    eol_orchestrator = SimpleNamespace()
    inventory_sync_result = {
        "discovered_os_count": 4,
        "new_os_count": 2,
        "processed_os_count": 2,
        "os_entries": [{"key": "windows server::2025", "query_mode": "cpe"}],
    }
    delta_sync_result = {
        "cve_count": 11,
        "since_date": datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        "used_fallback_window": True,
    }

    with patch("main.get_cve_service", AsyncMock(return_value=cve_service)), \
         patch("main.get_cve_scanner", AsyncMock(return_value=cve_scanner)), \
         patch("main.get_eol_orchestrator", return_value=eol_orchestrator), \
         patch("api.cve_sync.run_inventory_bootstrap_sync", AsyncMock(return_value=inventory_sync_result)) as mock_inventory_sync, \
         patch("api.cve_sync.run_delta_sync", AsyncMock(return_value=delta_sync_result)) as mock_delta_sync:
        response = await cve_sync.trigger_incremental_sync()

    mock_inventory_sync.assert_awaited_once_with(
        cve_service=cve_service,
        cve_scanner=cve_scanner,
        eol_orchestrator=eol_orchestrator,
        limit_per_os=None,
        force_resync=False,
    )
    mock_delta_sync.assert_awaited_once_with(
        cve_service=cve_service,
        lookback_days=cve_sync.config.cve_sync.sync_lookback_days,
        limit=cve_sync.config.cve_sync.max_cves_per_sync,
    )
    assert response.success is True
    assert response.message == "Delta sync completed: 11 CVEs synced"
    assert response.data["inventory_os_processed"] == 2
    assert response.data["used_fallback_window"] is True
    assert response.data["inventory_sync_mode"] == "new-only"