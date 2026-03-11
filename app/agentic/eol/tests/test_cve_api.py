from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import cve


@pytest.mark.asyncio
async def test_get_cve_stats_includes_inventory_os_counts():
    cve_service = AsyncMock()
    async def count_cves_side_effect(filters):
        if not filters:
            return 1234
        mapping = {
            ("microsoft", "windows server 2016"): 482,
            ("microsoft", "windows server 2019"): 78,
            ("microsoft", "windows server 2022"): 41,
            ("ubuntu", "ubuntu 22.04"): 0,
        }
        return mapping.get((filters.get("vendor"), filters.get("keyword")), 0)

    cve_service.count_cves = AsyncMock(side_effect=count_cves_side_effect)
    cve_service.get_cache_stats = MagicMock(return_value={"entries": 5})
    inventory_state = {
        "last_synced_at": "2026-03-09T00:00:00+00:00",
        "os_entries": [
            {
                "key": "windows server::2016",
                "normalized_name": "windows server",
                "normalized_version": "2016",
                "match_count": 1,
                "query_mode": "cpe",
                "synced_at": "2026-03-09T00:00:00+00:00",
            },
            {
                "key": "windows server::2019",
                "normalized_name": "windows server",
                "normalized_version": "2019",
                "match_count": 3,
                "query_mode": "cpe",
                "synced_at": "2026-03-09T00:00:00+00:00",
            },
            {
                "key": "windows server::2022",
                "normalized_name": "windows server",
                "normalized_version": "2022",
                "match_count": 2,
                "query_mode": "cpe",
                "synced_at": "2026-03-09T00:00:00+00:00",
            },
        ],
    }
    discovered_identities = [
        {
            "key": "windows server::2016",
            "normalized_name": "windows server",
            "normalized_version": "2016",
        },
        {
            "key": "windows server::2019",
            "normalized_name": "windows server",
            "normalized_version": "2019",
        },
        {
            "key": "windows server::2022",
            "normalized_name": "windows server",
            "normalized_version": "2022",
        },
        {
            "key": "ubuntu::22.04",
            "normalized_name": "ubuntu",
            "normalized_version": "22.04",
        },
    ]

    with patch("main.get_cve_service", AsyncMock(return_value=cve_service)), \
         patch("main.get_cve_scanner", AsyncMock(return_value=AsyncMock())), \
         patch("main.get_eol_orchestrator", return_value=MagicMock()), \
         patch("utils.cve_inventory_sync.CVEInventorySyncStateStore.load", AsyncMock(return_value=inventory_state)), \
         patch("utils.cve_inventory_sync.discover_inventory_os_identities", AsyncMock(return_value=discovered_identities)):
        response = await cve.get_cve_stats()

    assert response.success is True
    assert response.data["cached_count"] == 1234
    assert response.data["inventory_os_last_synced_at"] == "2026-03-09T00:00:00+00:00"
    assert response.data["inventory_os_counts"][0]["display_name"] == "Windows Server"
    assert response.data["inventory_os_counts"][0]["version"] == "2016"
    assert response.data["inventory_os_counts"][0]["match_count"] == 482
    assert any(
        entry["display_name"] == "Windows Server" and entry["version"] == "2022" and entry["match_count"] == 41
        for entry in response.data["inventory_os_counts"]
    )
    assert any(
        entry["display_name"] == "Ubuntu" and entry["version"] == "22.04" and entry["match_count"] == 0
        for entry in response.data["inventory_os_counts"]
    )
    assert len(response.data["inventory_os_counts"]) == 4