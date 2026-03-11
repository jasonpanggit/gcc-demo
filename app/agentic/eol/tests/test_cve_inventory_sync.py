from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.cve_inventory_sync import discover_inventory_os_identities, sync_inventory_os_cves


@pytest.mark.asyncio
async def test_discover_inventory_os_identities_merges_os_and_vm_sources():
    os_agent = AsyncMock()
    os_agent.get_os_inventory.return_value = {
        "success": True,
        "data": [
            {"os_name": "Microsoft Windows Server 2022 Datacenter", "os_version": "10.0"},
            {"os_name": "Ubuntu", "os_version": "22.04"},
        ],
    }
    orchestrator = SimpleNamespace(agents={"os_inventory": os_agent})
    scanner = AsyncMock()
    scanner.get_vm_targets.return_value = [
        SimpleNamespace(os_name="WindowsServer", os_version="2022-datacenter-g2", os_type="Windows"),
        SimpleNamespace(os_name="Ubuntu", os_version="22.04-LTS", os_type="Linux"),
    ]

    identities = await discover_inventory_os_identities(
        eol_orchestrator=orchestrator,
        cve_scanner=scanner,
    )

    by_key = {item["key"]: item for item in identities}
    assert "windows server::2022" in by_key
    assert "ubuntu::22.04" in by_key
    assert sorted(by_key["windows server::2022"]["sources"]) == ["os_inventory", "vm_inventory"]


@pytest.mark.asyncio
async def test_sync_inventory_os_cves_only_processes_new_identities():
    cve_service = AsyncMock()
    cve_service.sync_live_cves.side_effect = [[SimpleNamespace(cve_id="CVE-1")], [SimpleNamespace(cve_id="CVE-2")]]
    os_agent = AsyncMock()
    os_agent.get_os_inventory.return_value = {
        "success": True,
        "data": [
            {"os_name": "Windows Server 2022", "os_version": "2022"},
            {"os_name": "Ubuntu", "os_version": "22.04"},
        ],
    }
    orchestrator = SimpleNamespace(agents={"os_inventory": os_agent})
    scanner = AsyncMock()
    scanner.get_vm_targets.return_value = []

    class _Store:
        def __init__(self):
            self.state = {
                "synced_os_keys": ["windows server::2022"],
                "os_entries": [],
                "last_synced_at": None,
            }

        async def load(self):
            return self.state

        async def save(self, state):
            self.state = state

    store = _Store()

    result = await sync_inventory_os_cves(
        cve_service=cve_service,
        cve_scanner=scanner,
        eol_orchestrator=orchestrator,
        state_store=store,
        limit_per_os=100,
    )

    assert result["discovered_os_count"] == 2
    assert result["new_os_count"] == 1
    assert result["processed_os_count"] == 1
    assert result["synced_cve_count"] == 1
    cve_service.sync_live_cves.assert_awaited_once()
    assert "ubuntu::22.04" in store.state["synced_os_keys"]


@pytest.mark.asyncio
async def test_sync_inventory_os_cves_uses_nvd_cpe_queries_for_supported_os():
    cve_service = AsyncMock()
    cve_service.sync_live_cves.return_value = [SimpleNamespace(cve_id="CVE-1")]
    os_agent = AsyncMock()
    os_agent.get_os_inventory.return_value = {
        "success": True,
        "data": [
            {"os_name": "Windows Server 2022", "os_version": "2022"},
        ],
    }
    orchestrator = SimpleNamespace(agents={"os_inventory": os_agent})
    scanner = AsyncMock()
    scanner.get_vm_targets.return_value = []

    class _Store:
        def __init__(self):
            self.state = {
                "synced_os_keys": [],
                "os_entries": [],
                "last_synced_at": None,
            }

        async def load(self):
            return self.state

        async def save(self, state):
            self.state = state

    store = _Store()

    result = await sync_inventory_os_cves(
        cve_service=cve_service,
        cve_scanner=scanner,
        eol_orchestrator=orchestrator,
        state_store=store,
        limit_per_os=None,
    )

    cve_service.sync_live_cves.assert_awaited_once_with(
        query=None,
        limit=None,
        source="nvd",
        nvd_filters={"cpeName": "cpe:2.3:o:microsoft:windows_server_2022:-:*:*:*:*:*:*:*"},
    )
    assert result["synced_cve_count"] == 1
    assert result["os_entries"][0]["query_mode"] == "cpe"