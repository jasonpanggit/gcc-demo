from datetime import datetime, timezone

import pytest

from models.cve_models import CVEAffectedProduct, UnifiedCVE
from utils.cve_in_memory_repository import CVEInMemoryRepository


def _build_cve() -> UnifiedCVE:
    return UnifiedCVE(
        cve_id="CVE-2026-5555",
        description="Security update for Microsoft server platform",
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_modified_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
        affected_products=[
            CVEAffectedProduct(vendor="microsoft", product="windows_server_2022", version="2022"),
        ],
        sources=["nvd"],
    )


@pytest.mark.asyncio
async def test_in_memory_query_matches_keyword_against_affected_products():
    repository = CVEInMemoryRepository()
    await repository.upsert_cve(_build_cve())

    results = await repository.query_cves({"keyword": "windows server 2022", "vendor": "microsoft"})

    assert len(results) == 1
    assert results[0].cve_id == "CVE-2026-5555"