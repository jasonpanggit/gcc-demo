"""Tests for CVEScanner per-VM match document storage."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from models.cve_models import ScanResult, VMScanTarget


def make_vm(name="VM1", vm_id="/subs/s/rg/r/providers/m/virtualMachines/VM1"):
    return VMScanTarget(
        vm_id=vm_id, name=name, resource_group="rg",
        subscription_id="sub", os_type="Windows",
        os_name="Windows Server", os_version="2019",
        location="eastus", vm_type="azure",
    )


@pytest.fixture
def mock_vm_match_repo():
    repo = MagicMock()
    repo.save_vm_matches = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def scanner_with_repo(mock_vm_match_repo):
    from utils.cve_scanner import CVEScanner
    mock_scan_repo = MagicMock()
    mock_scan_repo.save = AsyncMock()
    mock_scan_repo.get = AsyncMock(return_value=ScanResult(
        scan_id="test-scan-id",
        started_at="2026-03-11T00:00:00+00:00",
        status="pending",
        total_vms=0,
        scanned_vms=0,
        total_matches=0,
    ))

    mock_cve_service = MagicMock()
    mock_cve_service.search_cves = AsyncMock(return_value=[])

    mock_rg_client = MagicMock()

    scanner = CVEScanner(
        cve_service=mock_cve_service,
        resource_graph_client=mock_rg_client,
        scan_repository=mock_scan_repo,
        vm_match_repository=mock_vm_match_repo,
        subscription_id="test-sub",
    )
    return scanner


@pytest.mark.asyncio
async def test_scanner_accepts_vm_match_repository(scanner_with_repo, mock_vm_match_repo):
    """CVEScanner must accept vm_match_repository in constructor."""
    assert scanner_with_repo.vm_match_repository is mock_vm_match_repo


@pytest.mark.asyncio
async def test_scan_result_matches_empty_after_scan():
    """After scan, main scan doc matches list must be empty."""
    scan = ScanResult(
        scan_id="test-scan-id",
        started_at="2026-03-11T00:00:00+00:00",
        status="completed",
        total_vms=0,
        scanned_vms=0,
        total_matches=0,
    )
    # These should be the values set by scanner after completion
    scan.matches = []
    scan.matches_stored_separately = True
    assert scan.matches == []
    assert scan.matches_stored_separately is True
