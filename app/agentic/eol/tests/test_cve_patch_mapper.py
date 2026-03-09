from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cve_models import CVEReference, CVEVendorMetadata, UnifiedCVE
from utils.cve_patch_mapper import CVEPatchMapper
from utils.kb_cve_edge_repository import InMemoryKBCVEEdgeRepository


class _HistoryRepo:
    def __init__(self, records):
        self.records = records

    async def list_completed_since(self, _cutoff_iso):
        return list(self.records)


def _build_cve(*, references=None, vendor_metadata=None):
    return UnifiedCVE(
        cve_id="CVE-2026-4242",
        description="Test CVE",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_modified_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
        references=references or [],
        vendor_metadata=vendor_metadata or [],
        sources=["nvd"],
    )


def _build_named_cve(cve_id: str):
    cve = _build_cve()
    return cve.model_copy(update={"cve_id": cve_id})


@pytest.mark.asyncio
async def test_get_install_history_for_cve_matches_kb_reference():
    cve_service = AsyncMock()
    cve_service.get_cve.return_value = _build_cve(
        references=[
            CVEReference(
                url="https://support.microsoft.com/help/KB5030211",
                source="microsoft",
            )
        ]
    )

    repo = _HistoryRepo([
        {
            "operation_url": "op-1",
            "completed_at": "2026-02-01T00:00:00+00:00",
            "patches": [{"kbId": "KB5030211", "patchName": "2026-02 Cumulative Update"}],
        },
        {
            "operation_url": "op-2",
            "completed_at": "2026-02-02T00:00:00+00:00",
            "patches": [{"kbId": "KB9999999", "patchName": "Other Update"}],
        },
    ])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=MagicMock(),
        patch_mcp_client=MagicMock(),
        patch_install_history_repository=repo,
    )

    records = await mapper.get_install_history_for_cve("CVE-2026-4242", 30)

    assert len(records) == 1
    assert records[0]["operation_url"] == "op-1"


@pytest.mark.asyncio
async def test_get_install_history_for_cve_matches_vendor_package_name():
    cve_service = AsyncMock()
    cve_service.get_cve.return_value = _build_cve(
        vendor_metadata=[
            CVEVendorMetadata(
                source="ubuntu",
                affected_packages=[{"package_name": "openssl"}],
            )
        ]
    )

    repo = _HistoryRepo([
        {
            "operation_url": "op-3",
            "completed_at": "2026-02-03T00:00:00+00:00",
            "patches": [{"patchName": "openssl security update"}],
        },
        {
            "operation_url": "op-4",
            "completed_at": "2026-02-04T00:00:00+00:00",
            "patches": [{"patchName": "nginx bugfix update"}],
        },
    ])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=MagicMock(),
        patch_mcp_client=MagicMock(),
        patch_install_history_repository=repo,
    )

    records = await mapper.get_install_history_for_cve("CVE-2026-4242", 30)

    assert len(records) == 1
    assert records[0]["operation_url"] == "op-3"


@pytest.mark.asyncio
async def test_get_patches_for_cve_reuses_patch_inventory_and_exposure_summary():
    cve_service = AsyncMock()
    cve_service.get_cve.side_effect = [
        _build_named_cve("CVE-2026-1111"),
        _build_named_cve("CVE-2026-2222"),
    ]

    patch_client = AsyncMock()
    patch_client.query_patch_assessments.return_value = {
        "success": True,
        "data": [
            {
                "machine_name": "vm-1",
                "resource_group": "rg-prod",
                "subscription_id": "sub-123",
                "vm_type": "arc",
                "patches": {"available_patches": []},
            }
        ],
    }

    scanner = MagicMock()
    scanner.subscription_id = "sub-123"
    scanner.list_recent_scans = AsyncMock(return_value=[
        SimpleNamespace(
            status="completed",
            matches=[
                SimpleNamespace(cve_id="CVE-2026-1111"),
                SimpleNamespace(cve_id="CVE-2026-2222"),
            ],
        )
    ])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=scanner,
        patch_mcp_client=patch_client,
    )

    await mapper.get_patches_for_cve("CVE-2026-1111")
    await mapper.get_patches_for_cve("CVE-2026-2222")

    assert patch_client.query_patch_assessments.await_count == 2
    patch_client.query_patch_assessments.assert_any_await(
        subscription_id="sub-123",
        vm_type="arc",
    )
    patch_client.query_patch_assessments.assert_any_await(
        subscription_id="sub-123",
        vm_type="azure-vm",
    )
    scanner.list_recent_scans.assert_awaited_once_with(limit=10)


@pytest.mark.asyncio
async def test_get_patches_for_cve_matches_kb_id_from_patch_management_payload():
    cve_service = AsyncMock()
    cve_service.get_cve.return_value = _build_cve(
        references=[
            CVEReference(
                url="https://support.microsoft.com/help/KB5030211",
                source="microsoft",
            )
        ]
    )

    patch_client = AsyncMock()
    patch_client.query_patch_assessments.side_effect = [
        {
            "success": True,
            "data": [],
        },
        {
            "success": True,
            "data": [
                {
                    "machine_name": "vm-2",
                    "resource_group": "rg-prod",
                    "subscription_id": "sub-123",
                    "vm_type": "azure-vm",
                    "patches": {
                        "available_patches": [
                            {
                                "patchName": "2026-02 Cumulative Update",
                                "kbId": "KB5030211",
                                "classifications": ["Security"],
                                "publishedDate": "2026-02-01T00:00:00Z",
                            }
                        ]
                    },
                }
            ],
        },
    ]

    scanner = MagicMock()
    scanner.subscription_id = "sub-123"
    scanner.list_recent_scans = AsyncMock(return_value=[])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=scanner,
        patch_mcp_client=patch_client,
    )

    mapping = await mapper.get_patches_for_cve("CVE-2026-4242")

    assert len(mapping.patches) == 1
    assert mapping.patches[0].patch_id == "KB5030211"
    assert mapping.patches[0].affected_vm_count == 1


@pytest.mark.asyncio
async def test_get_patches_for_cve_uses_msrc_metadata_kb_articles_when_reference_has_no_kb():
    cve_service = AsyncMock()
    cve_service.get_cve.return_value = _build_cve(
        references=[
            CVEReference(
                url="https://portal.msrc.microsoft.com/en-US/security-guidance/advisory/CVE-2026-4242",
                source="microsoft",
            )
        ],
        vendor_metadata=[
            CVEVendorMetadata(
                source="microsoft",
                metadata={"kbArticles": ["KB5030211"]},
            )
        ],
    )

    patch_client = AsyncMock()
    patch_client.query_patch_assessments.side_effect = [
        {"success": True, "data": []},
        {
            "success": True,
            "data": [
                {
                    "machine_name": "vm-2",
                    "resource_group": "rg-prod",
                    "subscription_id": "sub-123",
                    "vm_type": "azure-vm",
                    "patches": {
                        "available_patches": [
                            {
                                "patchName": "2026-02 Cumulative Update",
                                "kbId": "KB5030211",
                                "classifications": ["Security"],
                                "publishedDate": "2026-02-01T00:00:00Z",
                            }
                        ]
                    },
                }
            ],
        },
    ]

    scanner = MagicMock()
    scanner.subscription_id = "sub-123"
    scanner.list_recent_scans = AsyncMock(return_value=[])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=scanner,
        patch_mcp_client=patch_client,
    )

    mapping = await mapper.get_patches_for_cve("CVE-2026-4242")

    assert len(mapping.patches) == 1
    assert mapping.patches[0].patch_id == "KB5030211"


@pytest.mark.asyncio
async def test_get_patches_for_cve_uses_top_level_vendor_kb_numbers_when_reference_has_no_kb():
    cve_service = AsyncMock()
    cve_service.get_cve.return_value = _build_cve(
        references=[
            CVEReference(
                url="https://portal.msrc.microsoft.com/en-US/security-guidance/advisory/CVE-2026-4242",
                source="microsoft",
            )
        ],
        vendor_metadata=[
            CVEVendorMetadata(
                source="microsoft",
                kb_numbers=["KB5030211"],
                fix_available=True,
            )
        ],
    )

    patch_client = AsyncMock()
    patch_client.query_patch_assessments.side_effect = [
        {"success": True, "data": []},
        {
            "success": True,
            "data": [
                {
                    "machine_name": "vm-2",
                    "resource_group": "rg-prod",
                    "subscription_id": "sub-123",
                    "vm_type": "azure-vm",
                    "patches": {
                        "available_patches": [
                            {
                                "patchName": "2026-02 Cumulative Update",
                                "kbId": "KB5030211",
                                "classifications": ["Security"],
                                "publishedDate": "2026-02-01T00:00:00Z",
                            }
                        ]
                    },
                }
            ],
        },
    ]

    scanner = MagicMock()
    scanner.subscription_id = "sub-123"
    scanner.list_recent_scans = AsyncMock(return_value=[])

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=scanner,
        patch_mcp_client=patch_client,
    )

    mapping = await mapper.get_patches_for_cve("CVE-2026-4242")

    assert len(mapping.patches) == 1
    assert mapping.patches[0].patch_id == "KB5030211"


@pytest.mark.asyncio
async def test_get_cve_ids_for_patch_uses_reverse_kb_edge_repository():
    repo = InMemoryKBCVEEdgeRepository()
    await repo.initialize()
    await repo.sync_cve_edges(
        _build_cve(
            vendor_metadata=[
                CVEVendorMetadata(
                    source="microsoft",
                    kb_numbers=["KB5030211"],
                    update_id="2026-Feb",
                    document_title="February 2026 Security Updates",
                )
            ]
        )
    )

    mapper = CVEPatchMapper(
        cve_service=AsyncMock(),
        cve_scanner=MagicMock(),
        patch_mcp_client=AsyncMock(),
        kb_cve_edge_repository=repo,
    )

    cve_ids = await mapper.get_cve_ids_for_patch({"kbId": "5030211", "patchName": "2026-02 Cumulative Update"})

    assert cve_ids == ["CVE-2026-4242"]


@pytest.mark.asyncio
async def test_get_cve_ids_for_patch_falls_back_to_msrc_bulletin_when_edge_store_is_empty():
    cve_service = AsyncMock()
    cve_service.get_cve.side_effect = [
        _build_cve(
            vendor_metadata=[
                CVEVendorMetadata(
                    source="microsoft",
                    kb_numbers=["KB5075999"],
                    update_id="2026-Feb",
                    document_title="February 2026 Security Updates",
                )
            ]
        ).model_copy(update={"cve_id": "CVE-2026-21510"}),
        _build_cve(
            vendor_metadata=[
                CVEVendorMetadata(
                    source="microsoft",
                    kb_numbers=["KB5075999"],
                    update_id="2026-Feb",
                    document_title="February 2026 Security Updates",
                )
            ]
        ).model_copy(update={"cve_id": "CVE-2026-21513"}),
    ]

    repo = InMemoryKBCVEEdgeRepository()
    await repo.initialize()

    mapper = CVEPatchMapper(
        cve_service=cve_service,
        cve_scanner=MagicMock(),
        patch_mcp_client=AsyncMock(),
        kb_cve_edge_repository=repo,
    )
    fake_vendor_client = SimpleNamespace(
        fetch_microsoft_cves_for_kb=AsyncMock(return_value=["CVE-2026-21510", "CVE-2026-21513"])
    )
    mapper._get_vendor_feed_client = MagicMock(return_value=fake_vendor_client)

    cve_ids = await mapper.get_cve_ids_for_patch({"kbId": "5075999", "patchName": "2026-02 Cumulative Update"})

    assert cve_ids == ["CVE-2026-21510", "CVE-2026-21513"]
    assert await repo.get_cve_ids_for_kb("KB5075999") == ["CVE-2026-21510", "CVE-2026-21513"]
    fake_vendor_client.fetch_microsoft_cves_for_kb.assert_awaited_once()