"""Tests for KB→CVE mapping pipeline fixes."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any


# ── Task 2: PatchRepository.upsert_available_patches ──────────────────────

@pytest.mark.asyncio
async def test_upsert_available_patches_normalises_kb_prefix():
    """kbId without 'KB' prefix should be normalised to 'KB{id}'."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    from utils.repositories.patch_repository import PatchRepository
    repo = PatchRepository(mock_pool)

    patches = [
        {"patchName": "Cumulative Update", "kbId": "5052006",
         "classifications": ["Critical"], "rebootBehavior": "AlwaysRequiresReboot",
         "assessmentState": "Available"},
    ]
    await repo.upsert_available_patches("resource/vm1", patches)

    # Extract the actual rows passed to executemany for a precise assertion
    assert mock_conn.executemany.called, "executemany should have been called"
    rows_arg = mock_conn.executemany.call_args[0][1]  # second positional arg is the list of tuples
    assert len(rows_arg) == 1
    assert rows_arg[0][1] == "KB5052006", f"KB should be normalised to KB5052006, got {rows_arg[0][1]}"


@pytest.mark.asyncio
async def test_upsert_available_patches_skips_empty_kb_ids():
    """Rows with empty/null kbId should not be inserted."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    from utils.repositories.patch_repository import PatchRepository
    repo = PatchRepository(mock_pool)

    patches = [
        {"patchName": "Update", "kbId": "", "classifications": [], "rebootBehavior": "", "assessmentState": ""},
        {"patchName": "Update2", "kbId": None, "classifications": [], "rebootBehavior": "", "assessmentState": ""},
        {"patchName": "Update3", "kbId": "null", "classifications": [], "rebootBehavior": "", "assessmentState": ""},
    ]
    count = await repo.upsert_available_patches("resource/vm1", patches)
    assert count == 0
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_available_patches_returns_count():
    """Returns count of rows upserted."""
    mock_conn = AsyncMock()
    mock_conn.executemany = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    from utils.repositories.patch_repository import PatchRepository
    repo = PatchRepository(mock_pool)

    patches = [
        {"patchName": "Update A", "kbId": "5001111", "classifications": ["Security"],
         "rebootBehavior": "NeverReboots", "assessmentState": "Available"},
        {"patchName": "Update B", "kbId": "5002222", "classifications": ["Critical"],
         "rebootBehavior": "AlwaysRequiresReboot", "assessmentState": "Available"},
    ]
    count = await repo.upsert_available_patches("resource/vm1", patches)
    assert count == 2
