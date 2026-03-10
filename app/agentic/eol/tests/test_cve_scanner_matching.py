from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cve_models import CVEAffectedProduct, CVEScanRequest, CVSSScore, ScanResult, UnifiedCVE, VMScanTarget
from utils.cve_scanner import CVEScanner


def _build_scanner() -> CVEScanner:
    return CVEScanner(
        cve_service=AsyncMock(),
        resource_graph_client=MagicMock(),
        scan_repository=AsyncMock(),
        subscription_id="sub-123",
    )


def _build_cve(product: str, version: str = "") -> UnifiedCVE:
    return UnifiedCVE(
        cve_id="CVE-2026-9999",
        description="Windows Server test CVE",
        published_date="2026-01-01T00:00:00Z",
        last_modified_date="2026-01-02T00:00:00Z",
        cvss_v3=CVSSScore(
            version="3.1",
            base_score=9.8,
            base_severity="CRITICAL",
            vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        ),
        affected_products=[
            CVEAffectedProduct(vendor="microsoft", product=product, version=version)
        ],
        sources=["nvd"],
    )


def test_build_cve_search_filters_uses_keyword_for_windows_server():
    scanner = _build_scanner()
    vm = VMScanTarget(
        vm_id="vm-1",
        name="vm-1",
        resource_group="rg",
        subscription_id="sub-123",
        os_type="Windows",
        os_name="WindowsServer",
        os_version="2022-datacenter-g2",
        installed_packages=[],
        tags={},
        location="eastus",
        vm_type="azure",
    )

    filters = scanner._build_cve_search_filters(vm)

    assert filters["vendor"] == "microsoft"
    assert filters["keyword"] == "windows server 2022"


def test_product_matches_vm_normalizes_windows_server_variants():
    scanner = _build_scanner()
    vm = VMScanTarget(
        vm_id="vm-1",
        name="vm-1",
        resource_group="rg",
        subscription_id="sub-123",
        os_type="Windows",
        os_name="WindowsServer",
        os_version="2022-datacenter-g2",
        installed_packages=[],
        tags={},
        location="eastus",
        vm_type="azure",
    )

    assert scanner._product_matches_vm(vm, "windows_server_2022", "")
    assert scanner._product_matches_vm(vm, "Microsoft Windows Server", "2022")
    assert not scanner._product_matches_vm(vm, "windows_server_2019", "")


def test_is_vm_affected_handles_normalized_windows_products():
    scanner = _build_scanner()
    vm = VMScanTarget(
        vm_id="vm-1",
        name="vm-1",
        resource_group="rg",
        subscription_id="sub-123",
        os_type="Windows",
        os_name="WindowsServer",
        os_version="2022-datacenter-g2",
        installed_packages=[],
        tags={},
        location="eastus",
        vm_type="azure",
    )

    matching_cve = _build_cve("windows_server_2022")
    non_matching_cve = _build_cve("windows_server_2019")

    assert scanner._is_vm_affected(vm, matching_cve) is True
    assert scanner._is_vm_affected(vm, non_matching_cve) is False


@pytest.mark.asyncio
async def test_match_cves_to_vm_paginates_beyond_first_page():
    scanner = _build_scanner()
    vm = VMScanTarget(
        vm_id="vm-1",
        name="vm-1",
        resource_group="rg",
        subscription_id="sub-123",
        os_type="Windows",
        os_name="WindowsServer",
        os_version="2025-datacenter-g2",
        installed_packages=[],
        tags={},
        location="eastus",
        vm_type="azure",
    )

    first_page = [_build_cve("windows_server_2025") for _ in range(1000)]
    second_page = [_build_cve("windows_server_2025") for _ in range(37)]
    scanner.cve_service.search_cves = AsyncMock(side_effect=[first_page, second_page])

    matches = await scanner._match_cves_to_vm(vm)

    assert len(matches) == 1037
    assert scanner.cve_service.search_cves.await_count == 2
    assert scanner.cve_service.search_cves.await_args_list[0].kwargs["offset"] == 0
    assert scanner.cve_service.search_cves.await_args_list[0].kwargs["limit"] == 1000
    assert scanner.cve_service.search_cves.await_args_list[0].kwargs["allow_live_fallback"] is False
    assert scanner.cve_service.search_cves.await_args_list[1].kwargs["offset"] == 1000


@pytest.mark.asyncio
async def test_extract_vm_details_prefers_arc_os_sku():
    scanner = _build_scanner()

    vm = await scanner._extract_vm_details({
        "id": "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.HybridCompute/machines/WIN-P3OD2Q85TKG",
        "name": "WIN-P3OD2Q85TKG",
        "resourceGroup": "rg",
        "subscriptionId": "sub-123",
        "location": "southeastasia",
        "type": "microsoft.hybridcompute/machines",
        "properties": {
            "osName": "windows",
            "osSku": "Windows Server 2025 Standard",
            "osVersion": "10.0.26100.4946",
            "osType": "windows",
        },
        "tags": {},
    })

    assert vm.vm_type == "arc"
    assert vm.os_name == "Windows Server 2025 Standard"
    assert vm.os_version == "10.0.26100.4946"


@pytest.mark.asyncio
async def test_get_scan_status_summary_prefers_in_memory_cache_for_active_scans():
    repository = AsyncMock()
    repository.get_status_summary = AsyncMock(side_effect=AssertionError("repository fallback should not be used"))
    scanner = CVEScanner(
        cve_service=AsyncMock(),
        resource_graph_client=MagicMock(),
        scan_repository=repository,
        subscription_id="sub-123",
    )

    scanner._scan_status_cache["scan-123"] = {
        "scan_id": "scan-123",
        "started_at": "2026-03-10T00:00:00+00:00",
        "completed_at": None,
        "status": "running",
        "total_vms": 8,
        "scanned_vms": 0,
        "total_matches": 0,
        "error": None,
    }

    summary = await scanner.get_scan_status_summary("scan-123")

    assert summary is not None
    assert summary["status"] == "running"
    assert summary["scan_id"] == "scan-123"
    repository.get_status_summary.assert_not_called()


@pytest.mark.asyncio
async def test_get_scan_status_summary_falls_back_to_repository_when_not_cached():
    repository = AsyncMock()
    repository.get_status_summary = AsyncMock(return_value={
        "scan_id": "scan-456",
        "started_at": "2026-03-10T00:00:00+00:00",
        "completed_at": "2026-03-10T00:05:00+00:00",
        "status": "completed",
        "total_vms": 8,
        "scanned_vms": 8,
        "total_matches": 3000,
        "error": None,
    })
    scanner = CVEScanner(
        cve_service=AsyncMock(),
        resource_graph_client=MagicMock(),
        scan_repository=repository,
        subscription_id="sub-123",
    )

    summary = await scanner.get_scan_status_summary("scan-456")

    assert summary is not None
    assert summary["status"] == "completed"
    repository.get_status_summary.assert_awaited_once_with("scan-456")


@pytest.mark.asyncio
async def test_execute_scan_updates_progress_for_small_scans():
    repository = AsyncMock()
    initial_scan = ScanResult(
        scan_id="scan-small",
        started_at="2026-03-10T00:00:00+00:00",
        status="pending",
        total_vms=0,
        scanned_vms=0,
        total_matches=0,
        matches=[],
    )
    repository.get = AsyncMock(return_value=initial_scan)

    saved_states = []

    async def capture_save(scan_result):
        saved_states.append((scan_result.status, scan_result.scanned_vms, scan_result.total_vms))

    repository.save = AsyncMock(side_effect=capture_save)

    scanner = CVEScanner(
        cve_service=AsyncMock(),
        resource_graph_client=MagicMock(),
        scan_repository=repository,
        subscription_id="sub-123",
    )
    vms = [
        VMScanTarget(
            vm_id=f"vm-{index}",
            name=f"vm-{index}",
            resource_group="rg",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2025-datacenter-g2",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="azure",
        )
        for index in range(8)
    ]
    scanner._discover_vms = AsyncMock(return_value=vms)
    scanner._match_cves_to_vm = AsyncMock(return_value=[])

    await scanner._execute_scan("scan-small", CVEScanRequest(subscription_ids=["sub-123"], include_arc=True))

    progress_states = [state for state in saved_states if state[0] == "running" and state[1] > 0]
    assert progress_states, "expected intermediate running progress saves"
    assert progress_states[0] == ("running", 1, 8)
    assert progress_states[-1] == ("running", 8, 8)