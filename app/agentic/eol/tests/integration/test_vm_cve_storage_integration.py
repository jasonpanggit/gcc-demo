"""Integration test: scanner saves per-VM docs, service reads them back.

Tests the full pipeline from VMCVEMatchRepository.save_vm_matches()
through VMCVEMatchRepository.get_vm_matches() with an in-memory Cosmos mock.
"""
import asyncio
import pytest
from unittest.mock import MagicMock
from models.cve_models import CVEMatch, VMScanTarget


def make_vm(name: str = "VM1") -> VMScanTarget:
    return VMScanTarget(
        vm_id=f"/subs/sub/rg/rg1/providers/Microsoft.Compute/virtualMachines/{name}",
        name=name,
        resource_group="rg1",
        subscription_id="sub",
        os_type="Windows",
        os_name="Windows Server",
        os_version="2019",
        location="eastus",
        vm_type="azure",
    )


def make_match(vm: VMScanTarget, cve_id: str) -> CVEMatch:
    return CVEMatch(
        cve_id=cve_id,
        vm_id=vm.vm_id,
        vm_name=vm.name,
        match_reason="OS Windows Server 2019 affected",
        cvss_score=7.5,
        severity="HIGH",
    )


@pytest.mark.asyncio
async def test_scanner_saves_and_service_reads():
    """Full pipeline: scanner saves match docs, service reads with pagination."""
    from utils.vm_cve_match_repository import VMCVEMatchRepository

    # In-memory Cosmos mock
    stored_docs: dict = {}

    def mock_upsert(body):
        stored_docs[body["id"]] = body

    def mock_read_item(item, partition_key):
        if item not in stored_docs:
            from azure.core.exceptions import ResourceNotFoundError
            raise ResourceNotFoundError(f"{item} not found")
        return stored_docs[item]

    mock_container = MagicMock()
    mock_container.upsert_item = MagicMock(side_effect=mock_upsert)
    mock_container.read_item = MagicMock(side_effect=mock_read_item)
    mock_cosmos = MagicMock()
    mock_cosmos.get_database_client.return_value.get_container_client.return_value = mock_container

    # Set up repository (bypass initialize(), inject container directly)
    repo = VMCVEMatchRepository(mock_cosmos, "db", "cve-scans")
    repo.container = mock_container

    # Simulate scanner saving 150 matches for VM1
    vm = make_vm("VM1")
    scan_id = "test-scan-001"
    matches = [make_match(vm, f"CVE-2024-{i:04d}") for i in range(150)]
    await repo.save_vm_matches(scan_id, vm.vm_id, vm.name, matches)

    # Verify document was stored with expected ID and match count
    doc_id = f"{scan_id}--VM1"
    assert doc_id in stored_docs, f"Expected doc {doc_id} to be stored"
    assert stored_docs[doc_id]["total_matches"] == 150

    # Simulate service reading page 1 (offset=0, limit=100)
    page1 = await repo.get_vm_matches(scan_id, vm.vm_id, offset=0, limit=100)
    assert page1 is not None, "Page 1 should not be None"
    assert len(page1["matches"]) == 100, f"Expected 100 matches, got {len(page1['matches'])}"
    assert page1["has_more"] is True, "Should have more after page 1"
    assert page1["total_matches"] == 150

    # Simulate service reading page 2 (offset=100, limit=100)
    page2 = await repo.get_vm_matches(scan_id, vm.vm_id, offset=100, limit=100)
    assert page2 is not None, "Page 2 should not be None"
    assert len(page2["matches"]) == 50, f"Expected 50 remaining matches, got {len(page2['matches'])}"
    assert page2["has_more"] is False, "Should have no more after page 2"

    # Verify no overlap between pages
    page1_ids = {m["cve_id"] for m in page1["matches"]}
    page2_ids = {m["cve_id"] for m in page2["matches"]}
    assert len(page1_ids & page2_ids) == 0, "Pages should not overlap"

    # Verify combined pages cover all 150 matches
    all_ids = page1_ids | page2_ids
    assert len(all_ids) == 150, f"Combined pages should cover all 150 matches, got {len(all_ids)}"
