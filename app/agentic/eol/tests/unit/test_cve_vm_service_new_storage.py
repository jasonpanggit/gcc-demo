"""Tests for CVEVMService reading from VMCVEMatchRepository."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from models.cve_models import ScanResult, CVEMatch


def make_scan(scan_id="scan-1"):
    return ScanResult(
        scan_id=scan_id,
        started_at="2026-03-11T00:00:00+00:00",
        completed_at="2026-03-11T01:00:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=200,
        matches=[],  # Empty — stored separately
        matches_stored_separately=True,
        vm_match_summaries={
            "/subs/s/rg/r/providers/m/virtualmachines/vm1": {
                "vm_id": "/subs/s/rg/r/providers/m/virtualMachines/VM1",
                "vm_name": "VM1",
                "total_cves": 200,
                "critical": 10, "high": 50, "medium": 100, "low": 40,
            }
        },
    )


@pytest.fixture
def mock_vm_match_repo():
    repo = MagicMock()
    repo.get_vm_matches = AsyncMock(return_value={
        "vm_id": "/subs/s/rg/r/providers/m/virtualMachines/VM1",
        "vm_name": "VM1",
        "total_matches": 200,
        "matches": [
            {"cve_id": f"CVE-2024-{i:04d}", "vm_id": "/subs/s/rg/r/providers/m/virtualMachines/VM1",
             "vm_name": "VM1", "match_reason": "OS match", "cvss_score": 7.0, "severity": "HIGH"}
            for i in range(100)
        ],
        "has_more": True,
    })
    return repo


@pytest.fixture
def service_with_repo(mock_vm_match_repo):
    from utils.cve_vm_service import CVEVMService
    mock_cve_service = MagicMock()
    mock_cve_service.get_cve = AsyncMock(return_value=None)
    mock_patch_mapper = MagicMock()
    mock_patch_mapper.get_patches_for_cve = AsyncMock(return_value=MagicMock(patches=[]))
    mock_patch_mapper.get_cve_ids_for_patch = AsyncMock(return_value=[])
    mock_cve_scanner = MagicMock()
    mock_cve_scanner.get_latest_scan_result = AsyncMock(return_value=make_scan())
    mock_cve_scanner.get_vm_targets_by_ids = AsyncMock(return_value={})

    svc = CVEVMService(
        cve_service=mock_cve_service,
        patch_mapper=mock_patch_mapper,
        cve_scanner=mock_cve_scanner,
        vm_match_repository=mock_vm_match_repo,
    )
    return svc


@pytest.mark.asyncio
async def test_service_accepts_vm_match_repository(service_with_repo, mock_vm_match_repo):
    assert service_with_repo.vm_match_repository is mock_vm_match_repo


@pytest.mark.asyncio
async def test_get_vm_vulnerabilities_calls_repository(service_with_repo, mock_vm_match_repo):
    vm_id = "/subs/s/rg/r/providers/m/virtualMachines/VM1"
    result = await service_with_repo.get_vm_vulnerabilities(vm_id=vm_id, offset=0, limit=100)
    mock_vm_match_repo.get_vm_matches.assert_called_once_with(
        scan_id="scan-1",
        vm_id=vm_id,
        offset=0,
        limit=100,
    )
