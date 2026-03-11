"""Tests that CVEVMService deduplicates get_assessment_result calls via L1 cache."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


def make_service():
    """Build a minimal CVEVMService with mocked dependencies."""
    try:
        from utils.cve_vm_service import CVEVMService
    except ModuleNotFoundError:
        from app.agentic.eol.utils.cve_vm_service import CVEVMService

    cve_service = AsyncMock()
    patch_mapper = AsyncMock()
    patch_mapper.patch_mcp_client = AsyncMock()
    cve_scanner = AsyncMock()
    return CVEVMService(cve_service, patch_mapper, cve_scanner)


ASSESSMENT_RESULT = {
    "success": True,
    "found": True,
    "patches": {
        "available_patches": [
            {"patchName": "KB5034441", "kbId": "5034441", "classifications": ["Critical"]}
        ],
    },
}


@pytest.mark.asyncio
async def test_patch_assessment_cache_deduplicates_concurrent_calls():
    """Concurrent _get_available_patch_identifiers calls for the same VM
    should only call get_assessment_result once."""
    service = make_service()
    service.patch_mapper.patch_mcp_client.get_assessment_result = AsyncMock(
        return_value=ASSESSMENT_RESULT
    )

    try:
        from models.cve_models import CVEMatch
    except ModuleNotFoundError:
        from app.agentic.eol.models.cve_models import CVEMatch

    match = CVEMatch(
        cve_id="CVE-2024-1234",
        vm_id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.HybridCompute/machines/WIN-JBC7MM2NO8J",
        vm_name="WIN-JBC7MM2NO8J",
        match_reason="test",
    )

    # Fire 5 concurrent calls for the same VM
    results = await asyncio.gather(*[
        service._get_available_patch_identifiers(match)
        for _ in range(5)
    ])

    # All should succeed - each returns (identifiers, bool, patches) tuple
    assert all(len(r) == 3 for r in results)

    # get_assessment_result should only have been called ONCE
    call_count = service.patch_mapper.patch_mcp_client.get_assessment_result.call_count
    assert call_count == 1, f"Expected 1 call but got {call_count}"


@pytest.mark.asyncio
async def test_patch_assessment_cache_returns_cached_on_second_call():
    """Second call for same VM should hit L1 cache, not call get_assessment_result again."""
    service = make_service()
    service.patch_mapper.patch_mcp_client.get_assessment_result = AsyncMock(
        return_value=ASSESSMENT_RESULT
    )

    try:
        from models.cve_models import CVEMatch
    except ModuleNotFoundError:
        from app.agentic.eol.models.cve_models import CVEMatch

    match = CVEMatch(
        cve_id="CVE-2024-1234",
        vm_id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.HybridCompute/machines/WIN-TEST",
        vm_name="WIN-TEST",
        match_reason="test",
    )

    # First call — should hit ARG (via mocked get_assessment_result)
    await service._get_available_patch_identifiers(match)
    assert service.patch_mapper.patch_mcp_client.get_assessment_result.call_count == 1

    # Second call — should hit L1 cache, NOT call get_assessment_result again
    await service._get_available_patch_identifiers(match)
    assert service.patch_mapper.patch_mcp_client.get_assessment_result.call_count == 1  # still 1
