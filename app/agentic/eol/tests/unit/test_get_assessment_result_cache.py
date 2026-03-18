"""Tests that get_assessment_result reads from and writes to the assessment cache."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


CACHED_RESULT = {
    "success": True,
    "found": True,
    "machine_name": "WIN-JBC7MM2NO8J",
    "vm_type": "arc",
    "patches": {"available_patches": [], "total_count": 0},
}


@pytest.mark.asyncio
async def test_get_assessment_result_returns_cached_data():
    """get_assessment_result should return cached result without calling ARG."""
    mock_repo = AsyncMock()
    mock_repo.get_assessment.return_value = CACHED_RESULT

    with patch(
        "mcp_servers.patch_mcp_server.get_patch_assessment_repository",
        new_callable=AsyncMock,
        return_value=mock_repo,
    ), patch("mcp_servers.patch_mcp_server._query_arg", new_callable=AsyncMock) as mock_arg:
        import mcp_servers.patch_mcp_server as mod
        result = await mod.get_assessment_result(
            machine_name="WIN-JBC7MM2NO8J",
            subscription_id="sub-123",
            vm_type="arc",
        )

    assert result == CACHED_RESULT
    mock_repo.get_assessment.assert_called_once_with("sub-123", "WIN-JBC7MM2NO8J", "arc")
    mock_arg.assert_not_called()


@pytest.mark.asyncio
async def test_get_assessment_result_stores_to_cache_on_arg_hit():
    """get_assessment_result should store fresh ARG result to the assessment cache."""
    mock_repo = AsyncMock()
    mock_repo.get_assessment.return_value = None  # cache miss

    summary_row = {
        "machineName": "WIN-JBC7MM2NO8J",
        "resourceGroup": "test-rg",
        "subscriptionId": "sub-123",
        "status": "Succeeded",
        "lastModified": "2026-03-11T00:00:00Z",
        "criticalCount": 2,
        "otherCount": 1,
        "osType": "Windows",
        "rebootPending": False,
    }

    with patch(
        "mcp_servers.patch_mcp_server.get_patch_assessment_repository",
        new_callable=AsyncMock,
        return_value=mock_repo,
    ), patch(
        "mcp_servers.patch_mcp_server._query_arg",
        new_callable=AsyncMock,
        side_effect=[[summary_row], []],
    ):
        import mcp_servers.patch_mcp_server as mod
        result = await mod.get_assessment_result(
            machine_name="WIN-JBC7MM2NO8J",
            subscription_id="sub-123",
            vm_type="arc",
        )

    assert result["success"] is True
    assert result["found"] is True
    mock_repo.store_assessment.assert_called_once()
    stored_call = mock_repo.store_assessment.call_args
    assert stored_call.args[1] == "WIN-JBC7MM2NO8J"


@pytest.mark.asyncio
async def test_get_assessment_result_cache_miss_falls_through_to_arg():
    """On cache miss, get_assessment_result should call ARG."""
    mock_repo = AsyncMock()
    mock_repo.get_assessment.return_value = None  # cache miss

    with patch(
        "mcp_servers.patch_mcp_server.get_patch_assessment_repository",
        new_callable=AsyncMock,
        return_value=mock_repo,
    ), patch(
        "mcp_servers.patch_mcp_server._query_arg",
        new_callable=AsyncMock,
        return_value=[],  # no ARG results = not found
    ) as mock_arg:
        import mcp_servers.patch_mcp_server as mod
        result = await mod.get_assessment_result(
            machine_name="MISSING-VM",
            subscription_id="sub-123",
            vm_type="arc",
        )

    assert result["found"] is False
    assert mock_arg.called
