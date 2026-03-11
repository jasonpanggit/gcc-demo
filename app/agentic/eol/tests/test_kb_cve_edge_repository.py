from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.cve_models import CVEReference, CVEVendorMetadata, UnifiedCVE
from utils.cve_cache import CVECache
from utils.cve_service import CVEService
from utils.kb_cve_edge_repository import InMemoryKBCVEEdgeRepository
from utils.normalization import extract_kb_ids, normalize_kb_id


def _build_cve(*, cve_id="CVE-2026-5000", kb_values=None, advisory_id=None, references=None):
    return UnifiedCVE(
        cve_id=cve_id,
        description="Test CVE",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_modified_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
        references=references or [],
        vendor_metadata=[
            CVEVendorMetadata(
                source="microsoft",
                advisory_id=advisory_id,
                kb_numbers=kb_values or [],
                update_id="2026-Feb",
                document_title="February 2026 Security Updates",
                cvrf_url="https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2026-Feb",
                severity="Important",
            )
        ],
        sources=["nvd", "microsoft"],
        last_synced=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )


def test_normalize_kb_id_accepts_explicit_and_numeric_forms():
    assert normalize_kb_id("KB5050001") == "KB5050001"
    assert normalize_kb_id("kb-5050001") == "KB5050001"
    assert normalize_kb_id("5050001") == "KB5050001"
    assert normalize_kb_id("not-a-kb") is None


def test_extract_kb_ids_deduplicates_and_preserves_order():
    assert extract_kb_ids("Install KB5050001 then KB5050002 and KB5050001") == ["KB5050001", "KB5050002"]
    assert extract_kb_ids(["KB5050001", "5050002"], allow_bare_numeric=True) == ["KB5050001", "KB5050002"]


@pytest.mark.asyncio
async def test_in_memory_kb_edge_repository_syncs_and_replaces_stale_edges():
    repo = InMemoryKBCVEEdgeRepository()
    await repo.initialize()

    original = _build_cve(
        kb_values=["KB5050001", "kb5050002"],
        references=[CVEReference(url="https://support.microsoft.com/help/KB5050003", source="microsoft")],
    )
    await repo.sync_cve_edges(original)

    assert await repo.get_cve_ids_for_kb("5050001") == ["CVE-2026-5000"]
    assert await repo.get_cve_ids_for_kb("KB5050002") == ["CVE-2026-5000"]
    assert await repo.get_cve_ids_for_kb("KB5050003") == ["CVE-2026-5000"]

    updated = _build_cve(
        kb_values=["KB5059999"],
        references=[],
    )
    await repo.sync_cve_edges(updated)

    assert await repo.get_cve_ids_for_kb("KB5050001") == []
    assert await repo.get_cve_ids_for_kb("KB5059999") == ["CVE-2026-5000"]


@pytest.mark.asyncio
async def test_cve_service_persists_kb_edges_when_cve_is_fetched():
    cache = CVECache(maxsize=8, ttl=60)
    repository = AsyncMock()
    repository.get_cve.return_value = None
    aggregator = MagicMock()
    aggregator.fetch_and_merge_cve = AsyncMock(return_value=_build_cve(kb_values=["KB5050001"], advisory_id="KB5050002"))
    kb_repo = InMemoryKBCVEEdgeRepository()
    await kb_repo.initialize()

    service = CVEService(
        cache=cache,
        repository=repository,
        aggregator=aggregator,
        kb_cve_edge_repository=kb_repo,
    )

    result = await service.get_cve("CVE-2026-5000")

    assert result is not None
    repository.upsert_cve.assert_awaited_once()
    assert await kb_repo.get_cve_ids_for_kb("KB5050001") == ["CVE-2026-5000"]
    assert await kb_repo.get_cve_ids_for_kb("KB5050002") == ["CVE-2026-5000"]