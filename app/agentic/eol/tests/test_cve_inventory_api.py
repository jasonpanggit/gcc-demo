from api import cve_inventory

from unittest.mock import AsyncMock, patch

import pytest

from models.cve_models import ScanResult


def test_cve_search_request_sort_fields_are_supported():
    from models.cve_models import CVESearchRequest

    request = CVESearchRequest(sort_by="severity", sort_order="asc")

    assert request.sort_by == "severity"
    assert request.sort_order == "asc"


def test_vm_inventory_query_route_exists_for_resource_ids_with_slashes():
    route = next(
        route for route in cve_inventory.router.routes
        if getattr(route, "path", None) == "/vm-vulnerability-detail"
    )

    assert route is not None


def test_vm_inventory_path_route_still_captures_resource_ids_with_slashes():
    route = next(
        route for route in cve_inventory.router.routes
        if getattr(route, "path", None) == "/cve/inventory/{vm_id:path}"
    )

    match = route.path_regex.match(
        "/cve/inventory//subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/test-vm"
    )

    assert match is not None
    assert match.group("vm_id") == "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/test-vm"


@pytest.mark.asyncio
async def test_vm_inventory_overview_uses_inventory_backed_fallback_for_zero_match_rows():
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1"
    service = AsyncMock()
    service.get_latest_scan = AsyncMock(return_value=ScanResult(
        scan_id="scan-1",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=0,
        matches=[],
    ))
    service.get_vm_vulnerability_summaries = AsyncMock(return_value={
        vm_id.lower(): {
            "total_cves": 78,
            "critical": 2,
            "high": 47,
            "medium": 10,
            "low": 19,
        }
    })
    service.get_vm_vulnerabilities = AsyncMock()

    with patch("api.cve_inventory._get_cve_vm_service", AsyncMock(return_value=service)), \
         patch(
             "api.patch_management._list_machines_inventory",
             AsyncMock(return_value={
                 "data": [{
                     "resource_id": vm_id,
                     "computer": "testvm1",
                     "resource_group": "contosoresourcegroup",
                     "subscription_id": "sub-123",
                     "location": "eastus",
                     "os_type": "Windows",
                     "os_name": "Windows Server",
                     "os_version": "2019",
                     "vm_type": "azure-vm",
                 }]
             }),
         ) as mock_list_machines:
        response = await cve_inventory.get_vm_vulnerability_overview(days=90)

    row = response.data[0]
    assert row["total_cves"] == 78
    assert row["critical"] == 2
    assert row["high"] == 47
    assert row["risk_level"] == "Critical"
    assert response.metadata["vulnerable_vms"] == 1
    assert response.metadata["healthy_vms"] == 0
    service.get_vm_vulnerability_summaries.assert_awaited_once_with([vm_id], allow_live_cve_fallback=False)
    service.get_vm_vulnerabilities.assert_not_called()
    mock_list_machines.assert_awaited_once_with(days=90, include_eol=False)


@pytest.mark.asyncio
async def test_vm_inventory_overview_prefers_scan_vm_summaries_when_raw_matches_are_truncated():
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.HybridCompute/machines/WIN-P30D2Q85TKG"
    service = AsyncMock()
    service.get_latest_scan = AsyncMock(return_value=ScanResult(
        scan_id="scan-2",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=973,
        matches=[],
        vm_match_summaries={
            vm_id.lower(): {
                "vm_id": vm_id,
                "vm_name": "WIN-P30D2Q85TKG",
                "total_cves": 973,
                "critical": 11,
                "high": 660,
                "medium": 200,
                "low": 102,
            }
        },
    ))
    service.get_vm_vulnerability_summaries = AsyncMock(return_value={})

    with patch("api.cve_inventory._get_cve_vm_service", AsyncMock(return_value=service)), \
         patch(
             "api.patch_management._list_machines_inventory",
             AsyncMock(return_value={
                 "data": [{
                     "resource_id": vm_id,
                     "computer": "WIN-P30D2Q85TKG",
                     "resource_group": "agentic-aiops-demo-rg",
                     "subscription_id": "sub-123",
                     "location": "southeastasia",
                     "os_type": "Windows",
                     "os_name": "Windows Server",
                     "os_version": "2025",
                     "vm_type": "arc",
                 }]
             }),
         ):
        response = await cve_inventory.get_vm_vulnerability_overview(days=90)

    row = response.data[0]
    assert row["total_cves"] == 973
    assert row["critical"] == 11
    assert row["high"] == 660
    assert row["risk_level"] == "Critical"
    service.get_vm_vulnerability_summaries.assert_not_awaited()
