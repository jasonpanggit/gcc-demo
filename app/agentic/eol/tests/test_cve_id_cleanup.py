from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import AsyncMock

import pytest

from utils.cve_service import CVEService
from utils.cve_vm_service import CVEVMService


class _Cache:
    def get(self, _key):
        return None

    def set(self, _key, _value):
        return None


@pytest.mark.asyncio
async def test_cve_service_skips_external_fetch_for_non_standard_cve_ids():
    repository = AsyncMock()
    repository.get_cve = AsyncMock(return_value=None)
    aggregator = AsyncMock()

    service = CVEService(cache=_Cache(), repository=repository, aggregator=aggregator)

    result = await service.get_cve("PATCH-GAPS")

    assert result is None
    aggregator.fetch_and_merge_cve.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_derived_cve_details_ignore_invalid_ids():
    service = CVEVMService(AsyncMock(), AsyncMock(), AsyncMock())
    service.cve_service.get_cve = AsyncMock(return_value=None)

    details = await service._build_patch_derived_cve_details(
        existing_cve_ids=set(),
        patch_context={
            "installed_patch_entries": [],
            "available_patch_entries": [
                SimpleNamespace(patch_id="KB5075999", cve_ids=["PATCH-GAPS", "CVE-2026-21510"]),
            ],
        },
    )

    assert [detail.cve_id for detail in details] == ["CVE-2026-21510"]
    service.cve_service.get_cve.assert_awaited_once_with("CVE-2026-21510")