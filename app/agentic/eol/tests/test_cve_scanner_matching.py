from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cve_models import CVEAffectedProduct, CVSSScore, UnifiedCVE, VMScanTarget
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