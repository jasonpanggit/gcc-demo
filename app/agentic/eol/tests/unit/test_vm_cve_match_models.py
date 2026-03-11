"""Tests for VM CVE match storage models."""
from models.cve_models import VMCVEMatchDocument, ScanResult, VMCVEDetail


def test_vm_cve_match_document_id_format():
    doc = VMCVEMatchDocument(
        id="abc123--WIN-SERVER",
        scan_id="abc123",
        vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/WIN-SERVER",
        vm_name="WIN-SERVER",
        total_matches=5,
        matches=[],
        created_at="2026-03-11T00:00:00+00:00",
    )
    assert doc.id == "abc123--WIN-SERVER"
    assert doc.scan_id == "abc123"
    assert doc.total_matches == 5


def test_scan_result_has_matches_stored_separately_flag():
    scan = ScanResult(
        scan_id="test-123",
        started_at="2026-03-11T00:00:00+00:00",
        status="completed",
        total_vms=1,
        scanned_vms=1,
        total_matches=100,
        matches_stored_separately=True,
    )
    assert scan.matches_stored_separately is True
    assert scan.matches == []


def test_scan_result_defaults_matches_stored_separately_false():
    scan = ScanResult(
        scan_id="test-456",
        started_at="2026-03-11T00:00:00+00:00",
        status="completed",
        total_vms=0,
        scanned_vms=0,
        total_matches=0,
    )
    assert scan.matches_stored_separately is False
