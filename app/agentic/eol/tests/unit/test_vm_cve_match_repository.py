"""Tests for VMCVEMatchRepository."""
import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from models.cve_models import CVEMatch


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.upsert_item = MagicMock(return_value=None)
    container.read_item = MagicMock()
    container.delete_item = MagicMock(return_value=None)
    container.query_items = MagicMock(return_value=[])
    return container


@pytest.fixture
def mock_cosmos_client(mock_container):
    client = MagicMock()
    db = MagicMock()
    db.get_container_client.return_value = mock_container
    client.get_database_client.return_value = db
    return client


@pytest.fixture
def repo(mock_cosmos_client):
    from utils.vm_cve_match_repository import VMCVEMatchRepository
    r = VMCVEMatchRepository(
        cosmos_client=mock_cosmos_client,
        database_name="test-db",
        container_name="cve-scans",
    )
    r.container = mock_cosmos_client.get_database_client("x").get_container_client("y")
    return r


def make_match(cve_id: str) -> CVEMatch:
    return CVEMatch(
        cve_id=cve_id,
        vm_id="/subs/s/rg/r/providers/m/virtualMachines/VM1",
        vm_name="VM1",
        severity="HIGH",
        cvss_score=7.5,
        match_reason=f"OS Windows Server 2019 affected by {cve_id}",
    )


@pytest.mark.asyncio
async def test_build_vm_match_doc_id(repo):
    doc_id = repo._build_vm_match_doc_id(
        scan_id="abc-123",
        vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/WIN-SERVER",
    )
    assert doc_id == "abc-123--WIN-SERVER"


@pytest.mark.asyncio
async def test_build_vm_match_doc_id_bare_name(repo):
    doc_id = repo._build_vm_match_doc_id(scan_id="abc-123", vm_id="WIN-SERVER")
    assert doc_id == "abc-123--WIN-SERVER"


@pytest.mark.asyncio
async def test_save_vm_matches_calls_upsert(repo, mock_container):
    matches = [make_match("CVE-2024-0001"), make_match("CVE-2024-0002")]
    await repo.save_vm_matches(
        scan_id="scan-1",
        vm_id="/subs/s/rg/r/providers/m/virtualMachines/VM1",
        vm_name="VM1",
        matches=matches,
    )
    mock_container.upsert_item.assert_called_once()
    saved_body = mock_container.upsert_item.call_args[1]["body"]
    assert saved_body["id"] == "scan-1--VM1"
    assert saved_body["scan_id"] == "scan-1"
    assert saved_body["total_matches"] == 2


@pytest.mark.asyncio
async def test_get_vm_matches_pagination(repo, mock_container):
    matches_data = [{"cve_id": f"CVE-2024-{i:04d}", "severity": "HIGH", "cvss_score": 7.0,
                     "description": "test", "match_reason": "OS match",
                     "vm_id": "vm-id", "vm_name": "VM1"} for i in range(250)]
    mock_container.read_item.return_value = {
        "id": "scan-1--VM1",
        "scan_id": "scan-1",
        "vm_id": "vm-id",
        "vm_name": "VM1",
        "total_matches": 250,
        "matches": matches_data,
        "created_at": "2026-03-11T00:00:00+00:00",
    }

    result = await repo.get_vm_matches(scan_id="scan-1", vm_id="vm-id", offset=0, limit=100)
    assert result is not None
    assert result["total_matches"] == 250
    assert len(result["matches"]) == 100
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_get_vm_matches_last_page(repo, mock_container):
    matches_data = [{"cve_id": f"CVE-2024-{i:04d}", "severity": "HIGH", "cvss_score": 7.0,
                     "description": "test", "match_reason": "OS match",
                     "vm_id": "vm-id", "vm_name": "VM1"} for i in range(250)]
    mock_container.read_item.return_value = {
        "id": "scan-1--VM1",
        "scan_id": "scan-1",
        "vm_id": "vm-id",
        "vm_name": "VM1",
        "total_matches": 250,
        "matches": matches_data,
        "created_at": "2026-03-11T00:00:00+00:00",
    }

    result = await repo.get_vm_matches(scan_id="scan-1", vm_id="vm-id", offset=200, limit=100)
    assert len(result["matches"]) == 50
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_get_vm_matches_not_found_returns_none(repo, mock_container):
    from azure.core.exceptions import ResourceNotFoundError
    mock_container.read_item.side_effect = ResourceNotFoundError("not found")

    result = await repo.get_vm_matches(scan_id="scan-1", vm_id="missing-vm")
    assert result is None


@pytest.mark.asyncio
async def test_document_size_check_raises_on_oversized(repo):
    big_matches = [make_match(f"CVE-2024-{i:04d}") for i in range(5000)]
    with patch("utils.vm_cve_match_repository.json") as mock_json:
        mock_json.dumps.return_value = "x" * (1_900_000)
        with pytest.raises(ValueError, match="Document too large"):
            await repo.save_vm_matches(
                scan_id="scan-1",
                vm_id="/subs/s/rg/r/providers/m/virtualMachines/BIGVM",
                vm_name="BIGVM",
                matches=big_matches,
            )
