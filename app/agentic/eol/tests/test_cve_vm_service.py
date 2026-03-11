from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cve_models import CVEAffectedProduct, CVEMatch, CVEReference, CVSSScore, ScanResult, UnifiedCVE, VMCVEDetail, VMPatchInventoryItem, VMScanTarget
from utils.cve_vm_service import CVEVMService


class _PatchMapping:
    def __init__(self, patches=None):
        self.patches = patches or []


def _build_cve(cve_id: str = "CVE-2018-8626") -> UnifiedCVE:
    return UnifiedCVE(
        cve_id=cve_id,
        description="Test CVE",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_modified_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
        cvss_v3=CVSSScore(
            version="3.1",
            base_score=7.8,
            base_severity="HIGH",
            vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        ),
        affected_products=[
            CVEAffectedProduct(vendor="microsoft", product="windows_server_2019", version="")
        ],
        references=[
            CVEReference(
                url="https://support.microsoft.com/help/KB4534273",
                source="microsoft",
            )
        ],
        sources=["nvd"],
    )


@pytest.fixture
def mock_scanner():
    scanner = AsyncMock()
    scanner.get_latest_scan_result = AsyncMock()
    scanner.get_vm_targets_by_ids = AsyncMock(return_value={})
    scanner.get_vm_targets = AsyncMock(return_value=[])
    scanner.is_vm_affected_by_cve = MagicMock(return_value=False)
    return scanner


@pytest.fixture
def mock_cve_service():
    service = AsyncMock()
    service.get_cve = AsyncMock(return_value=_build_cve())
    return service


@pytest.fixture
def mock_patch_mapper():
    mapper = AsyncMock()
    mapper.get_patches_for_cve = AsyncMock(return_value=_PatchMapping())
    mapper.get_cve_ids_for_patch = AsyncMock(return_value=[])
    mapper.extract_cve_kb_numbers = MagicMock(return_value={"KB4534273"})
    mapper.extract_cve_package_names = MagicMock(return_value=set())
    return mapper


@pytest.fixture
def vm_service(mock_cve_service, mock_patch_mapper, mock_scanner):
    return CVEVMService(mock_cve_service, mock_patch_mapper, mock_scanner)


@pytest.mark.asyncio
async def test_get_cve_affected_vms_enriches_inventory_metadata(vm_service, mock_scanner):
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-1",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=1,
        matches=[
            CVEMatch(
                cve_id="CVE-2018-8626",
                vm_id=vm_id,
                vm_name="testvm1",
                match_reason="OS Windows Server 2019 affected",
                cvss_score=7.8,
                severity="HIGH",
                published_date="2018-11-14T01:29:01+00:00",
            )
        ],
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id.lower(): VMScanTarget(
            vm_id=vm_id,
            name="testvm1",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2019-datacenter-gensecond",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="azure",
        )
    }

    result = await vm_service.get_cve_affected_vms("CVE-2018-8626")

    assert result is not None
    assert result.total_vms == 1
    assert result.affected_vms[0].resource_group == "rg-prod"
    assert result.affected_vms[0].subscription_id == "sub-123"
    assert result.affected_vms[0].os_type == "Windows"
    assert result.affected_vms[0].os_name == "Windows Server"
    assert result.affected_vms[0].os_version == "2019"
    assert result.affected_vms[0].location == "eastus"
    assert result.affected_vms[0].patch_status == "unknown"


@pytest.mark.asyncio
async def test_get_cve_affected_vms_queries_patch_mapping_once_per_cve(
    vm_service,
    mock_scanner,
    mock_patch_mapper,
):
    vm_ids = [
        "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm2",
    ]
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-3",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=2,
        scanned_vms=2,
        total_matches=2,
        matches=[
            CVEMatch(
                cve_id="CVE-2018-8626",
                vm_id=vm_ids[0],
                vm_name="testvm1",
                match_reason="OS Windows Server 2019 affected",
            ),
            CVEMatch(
                cve_id="CVE-2018-8626",
                vm_id=vm_ids[1],
                vm_name="testvm2",
                match_reason="OS Windows Server 2019 affected",
            ),
        ],
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[{"id": "KB1"}])

    result = await vm_service.get_cve_affected_vms("CVE-2018-8626")

    assert result is not None
    assert result.total_vms == 2
    mock_patch_mapper.get_patches_for_cve.assert_awaited_once_with("CVE-2018-8626")


@pytest.mark.asyncio
async def test_get_vm_vulnerabilities_keeps_patch_coverage_for_known_vm_without_cve_matches(
    vm_service,
    mock_scanner,
):
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.HybridCompute/machines/WIN-JBC7MM2NO8J"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-empty",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=0,
        matches=[],
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id.lower(): VMScanTarget(
            vm_id=vm_id,
            name="WIN-JBC7MM2NO8J",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="Microsoft Windows Server 2016 Standard",
            os_version="10.0",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="arc",
        )
    }
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": {"KB5075999", "KB5075902"},
        "available_patches": [{"kbId": "5075999"}, {"kbId": "5075902"}],
        "installed_patch_entries": [],
        "available_patch_entries": [
            VMPatchInventoryItem(patch_id="KB5075999", patch_name="KB5075999", cve_ids=["CVE-2026-0001"], status="available"),
            VMPatchInventoryItem(patch_id="KB5075902", patch_name="KB5075902", cve_ids=[], status="available"),
        ],
        "installed_patch_index": [],
        "available_patch_index": [],
        "software_inventory_checked": False,
        "patch_assessment_checked": True,
        "patch_derived_cve_ids": ["CVE-2026-0001"],
    })

    result = await vm_service.get_vm_vulnerabilities(vm_id)

    assert result is not None
    assert result.vm_name == "WIN-JBC7MM2NO8J"
    assert result.total_cves == 1
    assert result.patch_coverage.available_patch_assessment_available is True
    assert result.patch_coverage.available_patch_count == 2
    assert result.patch_coverage.patch_derived_cves == 1
    assert result.patch_coverage.patch_derived_missing_cves == 0
    assert result.cve_details[0].cve_id == "CVE-2026-0001"
    assert result.cve_details[0].patch_status == "available"
    assert result.cve_details[0].available_patch_ids == ["KB5075999"]
    vm_service._get_vm_patch_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_vm_vulnerabilities_falls_back_to_inventory_synced_cves_when_scan_has_no_matches(
    vm_service,
    mock_scanner,
    mock_cve_service,
):
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-empty",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=0,
        matches=[],
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id.lower(): VMScanTarget(
            vm_id=vm_id,
            name="testvm1",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2019-datacenter-gensecond",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="azure",
        )
    }
    mock_cve_service.search_cves = AsyncMock(return_value=[_build_cve()])
    mock_scanner.is_vm_affected_by_cve.return_value = True
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": set(),
        "available_patches": [],
        "installed_patch_entries": [],
        "available_patch_entries": [],
        "software_inventory_checked": False,
        "patch_assessment_checked": False,
        "patch_derived_cve_ids": [],
    })

    result = await vm_service.get_vm_vulnerabilities(vm_id)

    assert result is not None
    assert result.total_cves == 1
    assert result.cve_details[0].cve_id == "CVE-2018-8626"
    assert result.cves_by_severity["HIGH"] == 1
    mock_cve_service.search_cves.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_vm_vulnerability_summary_uses_cached_inventory_only(
    vm_service,
    mock_scanner,
    mock_cve_service,
):
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-empty",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=0,
        matches=[],
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id.lower(): VMScanTarget(
            vm_id=vm_id,
            name="testvm1",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2019-datacenter-gensecond",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="azure",
        )
    }
    mock_scanner.is_vm_affected_by_cve.return_value = True
    mock_cve_service.search_cves = AsyncMock(return_value=[_build_cve()])

    result = await vm_service.get_vm_vulnerability_summary(
        vm_id,
        allow_live_cve_fallback=False,
    )

    assert result is not None
    assert result["total_cves"] == 1
    assert result["high"] == 1
    assert result["critical"] == 0
    mock_cve_service.search_cves.assert_awaited_once_with(
        filters={"keyword": "windows server 2019", "vendor": "microsoft"},
        limit=10000,
        offset=0,
        allow_live_fallback=False,
    )


@pytest.mark.asyncio
async def test_get_vm_vulnerability_summaries_batches_inventory_lookup_by_shared_os(
    vm_service,
    mock_scanner,
    mock_cve_service,
):
    vm_id_1 = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1"
    vm_id_2 = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm2"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-empty",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=2,
        scanned_vms=2,
        total_matches=0,
        matches=[],
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id_1.lower(): VMScanTarget(
            vm_id=vm_id_1,
            name="testvm1",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2019-datacenter-gensecond",
            installed_packages=[],
            tags={},
            location="eastus",
            vm_type="azure",
        ),
        vm_id_2.lower(): VMScanTarget(
            vm_id=vm_id_2,
            name="testvm2",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="WindowsServer",
            os_version="2019-datacenter-gensecond",
            installed_packages=[],
            tags={},
            location="eastus2",
            vm_type="azure",
        ),
    }
    mock_scanner.is_vm_affected_by_cve.return_value = True
    mock_cve_service.search_cves = AsyncMock(return_value=[_build_cve()])

    result = await vm_service.get_vm_vulnerability_summaries(
        [vm_id_1, vm_id_2],
        allow_live_cve_fallback=False,
    )

    assert sorted(result.keys()) == [vm_id_1.lower(), vm_id_2.lower()]
    assert result[vm_id_1.lower()]["total_cves"] == 1
    assert result[vm_id_2.lower()]["high"] == 1
    mock_scanner.get_vm_targets_by_ids.assert_awaited_once_with([vm_id_1, vm_id_2])
    mock_cve_service.search_cves.assert_awaited_once_with(
        filters={"keyword": "windows server 2019", "vendor": "microsoft"},
        limit=10000,
        offset=0,
        allow_live_fallback=False,
    )


@pytest.mark.asyncio
async def test_get_vm_vulnerability_summary_uses_scan_vm_summary_when_raw_matches_not_persisted(
    vm_service,
    mock_scanner,
    mock_cve_service,
):
    vm_id = "/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.HybridCompute/machines/WIN-P30D2Q85TKG"
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-summary",
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
    )
    mock_scanner.get_vm_targets_by_ids.return_value = {
        vm_id.lower(): VMScanTarget(
            vm_id=vm_id,
            name="WIN-P30D2Q85TKG",
            resource_group="rg-prod",
            subscription_id="sub-123",
            os_type="Windows",
            os_name="Windows Server 2025",
            os_version="10.0",
            installed_packages=[],
            tags={},
            location="southeastasia",
            vm_type="arc",
        )
    }

    result = await vm_service.get_vm_vulnerability_summary(vm_id, allow_live_cve_fallback=False)

    assert result is not None
    assert result["total_cves"] == 973
    assert result["critical"] == 11
    assert result["high"] == 660
    mock_cve_service.search_cves.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_cve_affected_vms_falls_back_to_inventory_matching(vm_service, mock_scanner):
    mock_scanner.get_latest_scan_result.return_value = ScanResult(
        scan_id="scan-2",
        started_at="2026-03-08T00:00:00+00:00",
        completed_at="2026-03-08T00:05:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=0,
        matches=[],
    )

    inventory_vm = VMScanTarget(
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm2",
        name="testvm2",
        resource_group="rg-prod",
        subscription_id="sub-123",
        os_type="Windows",
        os_name="Windows Server 2019 Datacenter",
        os_version="10.0",
        installed_packages=[],
        tags={},
        location="westus2",
        vm_type="azure",
    )
    mock_scanner.get_vm_targets.return_value = [inventory_vm]
    mock_scanner.is_vm_affected_by_cve.return_value = True

    result = await vm_service.get_cve_affected_vms("CVE-2018-8626")

    assert result is not None
    assert result.total_vms == 1
    assert result.affected_vms[0].vm_name == "testvm2"
    assert result.affected_vms[0].os_name == "Windows Server"
    assert result.affected_vms[0].os_version == "2019"
    assert result.affected_vms[0].match_reason == "OS Windows Server 2019 affected"
    assert result.affected_vms[0].patch_status == "unknown"


@pytest.mark.asyncio
async def test_get_patch_status_for_cve_returns_unknown_without_matching_patches(vm_service, mock_patch_mapper):
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[])

    status = await vm_service._get_patch_status_for_cve("CVE-2018-8626")

    assert status == "unknown"


@pytest.mark.asyncio
async def test_get_patch_status_for_cve_returns_unknown_when_patch_lookup_errors(vm_service, mock_patch_mapper):
    mock_patch_mapper.get_patches_for_cve.side_effect = RuntimeError("patch lookup failed")

    status = await vm_service._get_patch_status_for_cve("CVE-2018-8626")

    assert status == "unknown"


@pytest.mark.asyncio
async def test_enrich_cve_match_marks_cve_as_installed(vm_service, mock_patch_mapper):
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[{"id": "KB1"}])
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": {"KB4534273"},
        "available_identifiers": set(),
        "installed_patch_index": [{"entry": MagicMock(patch_id="KB4534273"), "identifiers": {"KB4534273"}}],
        "available_patch_index": [],
        "software_inventory_checked": True,
        "patch_assessment_checked": True,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "installed"
    assert detail.installed_patches == 1
    assert detail.patches_available == 0
    assert detail.installed_patch_ids == ["KB4534273"]


@pytest.mark.asyncio
async def test_enrich_cve_match_marks_cve_as_available(vm_service, mock_patch_mapper):
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[{"id": "KB1"}])
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": {"KB4534273"},
        "installed_patch_index": [],
        "available_patch_index": [{"entry": MagicMock(patch_id="KB4534273"), "identifiers": {"KB4534273"}}],
        "software_inventory_checked": True,
        "patch_assessment_checked": True,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "available"
    assert detail.installed_patches == 0
    assert detail.patches_available == 1
    assert detail.available_patch_ids == ["KB4534273"]


@pytest.mark.asyncio
async def test_enrich_cve_match_marks_cve_as_none_when_patch_checks_complete_without_evidence(vm_service, mock_patch_mapper):
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[])
    mock_patch_mapper.extract_cve_kb_numbers.return_value = set()
    mock_patch_mapper.extract_cve_package_names.return_value = set()
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": set(),
        "installed_patch_index": [],
        "available_patch_index": [],
        "software_inventory_checked": True,
        "patch_assessment_checked": True,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "none"
    assert detail.installed_patches == 0
    assert detail.patches_available == 0


@pytest.mark.asyncio
async def test_enrich_cve_match_includes_fix_kb_ids_when_patch_status_is_none(vm_service, mock_patch_mapper):
    """When a CVE has known KB numbers but none are installed/available, fix_kb_ids
    should carry those KB IDs so the UI can show 'install these to fix'."""
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[])
    mock_patch_mapper.extract_cve_kb_numbers.return_value = {"KB4534273", "KB4534271"}
    mock_patch_mapper.extract_cve_package_names.return_value = set()
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": set(),
        "installed_patch_index": [],
        "available_patch_index": [],
        "software_inventory_checked": True,
        "patch_assessment_checked": True,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "none"
    assert set(detail.fix_kb_ids) == {"KB4534273", "KB4534271"}


@pytest.mark.asyncio
async def test_enrich_cve_match_fix_kb_ids_empty_when_no_known_kbs(vm_service, mock_patch_mapper):
    """When a CVE has no known KB numbers, fix_kb_ids should be empty."""
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[])
    mock_patch_mapper.extract_cve_kb_numbers.return_value = set()
    mock_patch_mapper.extract_cve_package_names.return_value = set()
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": set(),
        "installed_patch_index": [],
        "available_patch_index": [],
        "software_inventory_checked": True,
        "patch_assessment_checked": True,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "none"
    assert detail.fix_kb_ids == []


@pytest.mark.asyncio
async def test_enrich_cve_match_keeps_unknown_when_patch_checks_fail(vm_service, mock_patch_mapper):
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/testvm1",
        vm_name="testvm1",
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.8,
        severity="HIGH",
        published_date="2018-11-14T01:29:01+00:00",
    )
    mock_patch_mapper.get_patches_for_cve.return_value = _PatchMapping(patches=[])
    mock_patch_mapper.extract_cve_kb_numbers.return_value = set()
    mock_patch_mapper.extract_cve_package_names.return_value = set()
    vm_service._get_vm_patch_context = AsyncMock(return_value={
        "installed_identifiers": set(),
        "available_identifiers": set(),
        "installed_patch_index": [],
        "available_patch_index": [],
        "software_inventory_checked": False,
        "patch_assessment_checked": False,
    })

    detail = await vm_service._enrich_cve_match(match)

    assert detail.patch_status == "unknown"


def test_build_patch_coverage_summary_identifies_unpatched_cves(vm_service):
    summary = vm_service._build_patch_coverage_summary(
        [
            VMCVEDetail(
                cve_id="CVE-1",
                severity="HIGH",
                description="Installed fix",
                match_reason="reason",
                patch_status="installed",
                installed_patches=1,
            ),
            VMCVEDetail(
                cve_id="CVE-2",
                severity="HIGH",
                description="Fix available",
                match_reason="reason",
                patch_status="available",
                patches_available=1,
            ),
            VMCVEDetail(
                cve_id="CVE-3",
                severity="MEDIUM",
                description="No evidence",
                match_reason="reason",
                patch_status="none",
            ),
            VMCVEDetail(
                cve_id="CVE-4",
                severity="LOW",
                description="Unknown",
                match_reason="reason",
                patch_status="unknown",
            ),
        ],
        {
            "installed_identifiers": {"KB1", "KB2"},
            "available_identifiers": {"KB3"},
            "installed_patch_entries": [VMPatchInventoryItem(patch_id="KB1", patch_name="KB1", cve_ids=["CVE-1"], status="installed")],
            "available_patch_entries": [VMPatchInventoryItem(patch_id="KB3", patch_name="KB3", cve_ids=["CVE-2"], status="available")],
            "software_inventory_checked": True,
            "patch_assessment_checked": True,
        },
    )

    assert summary.installed_patch_inventory_available is True
    assert summary.available_patch_assessment_available is True
    assert summary.installed_patch_count == 1
    assert summary.installed_patch_identifier_count == 2
    assert summary.available_patch_identifier_count == 1
    assert summary.covered_cves == 1
    assert summary.not_patched_cves == 3
    assert summary.patchable_unpatched_cves == 1
    assert summary.no_patch_evidence_cves == 1
    assert summary.unknown_patch_status_cves == 1
    assert summary.covered_cve_ids == ["CVE-1"]
    assert summary.not_patched_cve_ids == ["CVE-2", "CVE-3", "CVE-4"]


def test_build_patch_coverage_summary_identifies_patch_derived_cache_gaps(vm_service):
    summary = vm_service._build_patch_coverage_summary(
        [
            VMCVEDetail(
                cve_id="CVE-1",
                severity="HIGH",
                description="Installed fix",
                match_reason="reason",
                patch_status="installed",
                installed_patches=1,
            ),
            VMCVEDetail(
                cve_id="CVE-2",
                severity="HIGH",
                description="Fix available",
                match_reason="reason",
                patch_status="available",
                patches_available=1,
            ),
        ],
        {
            "installed_identifiers": {"KB1"},
            "available_identifiers": {"KB2", "KB3"},
            "available_patches": [{"kbId": "KB2"}, {"kbId": "KB3"}],
            "installed_patch_entries": [VMPatchInventoryItem(patch_id="KB1", patch_name="KB1", cve_ids=["CVE-1"], status="installed")],
            "available_patch_entries": [
                VMPatchInventoryItem(patch_id="KB2", patch_name="KB2", cve_ids=["CVE-2"], status="available"),
                VMPatchInventoryItem(patch_id="KB3", patch_name="KB3", cve_ids=["CVE-9"], status="available"),
            ],
            "software_inventory_checked": True,
            "patch_assessment_checked": True,
            "patch_derived_cve_ids": ["CVE-2", "CVE-9"],
        },
    )

    assert summary.available_patch_count == 2
    assert summary.patch_derived_cves == 2
    assert summary.patch_derived_cve_ids == ["CVE-2", "CVE-9"]
    assert summary.patch_derived_missing_cves == 1
    assert summary.patch_derived_missing_cve_ids == ["CVE-9"]


@pytest.mark.asyncio
async def test_get_available_patch_identifiers_falls_back_to_patch_management_api(vm_service, mock_patch_mapper):
    match = CVEMatch(
        cve_id="CVE-2018-8626",
        vm_id="/subscriptions/sub-123/resourceGroups/rg-prod/providers/Microsoft.HybridCompute/machines/WIN-JBC7MM2NO8J",
        vm_name="WIN-JBC7MM2NO8J",
        match_reason="OS Windows Server 2016 affected",
    )
    mock_patch_mapper.patch_mcp_client.get_assessment_result = AsyncMock(side_effect=RuntimeError("mcp unavailable"))
    vm_service._get_available_patch_assessment_via_api = AsyncMock(return_value={
        "success": True,
        "found": True,
        "patches": {
            "available_patches": [
                {"patchName": "2026-02 Cumulative Update (KB5075999)", "kbId": "5075999"},
                {"patchName": "2026-02 Servicing Stack Update (KB5075902)", "kbId": "5075902"},
            ]
        },
    })

    identifiers, checked, available_patches = await vm_service._get_available_patch_identifiers(match)

    assert checked is True
    assert len(available_patches) == 2
    assert "5075999" in identifiers
    assert "KB5075999" in identifiers
    assert any(p["kbId"] == "5075902" for p in available_patches)


@pytest.mark.asyncio
async def test_build_patch_derived_cve_details_uses_patch_inventory_evidence(vm_service, mock_cve_service):
    mock_cve_service.get_cve.return_value = _build_cve("CVE-2026-1000")

    details = await vm_service._build_patch_derived_cve_details(
        set(),
        {
            "installed_patch_entries": [MagicMock(patch_id="KB4534273", cve_ids=["CVE-2026-1000"])],
            "available_patch_entries": [MagicMock(patch_id="KB9999999", cve_ids=["CVE-2026-2000"])],
        },
    )

    assert len(details) == 2
    by_id = {detail.cve_id: detail for detail in details}
    assert by_id["CVE-2026-1000"].patch_status == "installed"
    assert by_id["CVE-2026-1000"].installed_patch_ids == ["KB4534273"]
    assert by_id["CVE-2026-2000"].patch_status == "available"
    assert by_id["CVE-2026-2000"].available_patch_ids == ["KB9999999"]
