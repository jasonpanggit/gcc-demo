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


# ── Task 3: sync_kb_edges_for_kbs ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_returns_zero_when_pool_is_none():
    """If pool is None, return 0 immediately without calling vendor."""
    mock_vendor = AsyncMock()

    from utils.cve_sync_operations import sync_kb_edges_for_kbs
    result = await sync_kb_edges_for_kbs(["KB5052006"], mock_vendor, pool=None)

    assert result == 0
    mock_vendor.fetch_microsoft_cves_for_kb.assert_not_called()


@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_normalises_kb_prefix():
    """KB numbers without 'KB' prefix should be normalised before MSRC call."""
    mock_vendor = AsyncMock()
    mock_vendor.fetch_microsoft_cves_for_kb = AsyncMock(return_value=["CVE-2025-0001"])

    mock_pool = MagicMock()

    with patch("utils.cve_sync_operations.CVERepository") as MockCVERepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.upsert_kb_cve_edges = AsyncMock(return_value=1)
        MockCVERepo.return_value = mock_repo_instance

        from utils.cve_sync_operations import sync_kb_edges_for_kbs
        await sync_kb_edges_for_kbs(["5052006"], mock_vendor, pool=mock_pool)

    mock_vendor.fetch_microsoft_cves_for_kb.assert_called_once_with("KB5052006")


@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_isolates_per_kb_errors():
    """A failed MSRC call for one KB should not abort the batch."""
    mock_vendor = AsyncMock()
    mock_vendor.fetch_microsoft_cves_for_kb = AsyncMock(
        side_effect=[Exception("MSRC timeout"), ["CVE-2025-0002"]]
    )
    mock_pool = MagicMock()

    with patch("utils.cve_sync_operations.CVERepository") as MockCVERepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.upsert_kb_cve_edges = AsyncMock(return_value=1)
        MockCVERepo.return_value = mock_repo_instance

        from utils.cve_sync_operations import sync_kb_edges_for_kbs
        result = await sync_kb_edges_for_kbs(
            ["KB5000001", "KB5000002"], mock_vendor, pool=mock_pool
        )

    # KB5000002 returns 1 CVE → 1 edge; KB5000001 failed and is skipped
    # upsert_kb_cve_edges mock returns 1 — function now returns that count
    assert result == 1
    mock_repo_instance.upsert_kb_cve_edges.assert_called_once()


@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_deduplicates_input():
    """Duplicate KB numbers in input should only trigger one MSRC call each."""
    mock_vendor = AsyncMock()
    mock_vendor.fetch_microsoft_cves_for_kb = AsyncMock(return_value=["CVE-2025-0001"])
    mock_pool = MagicMock()

    with patch("utils.cve_sync_operations.CVERepository") as MockCVERepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.upsert_kb_cve_edges = AsyncMock(return_value=1)
        MockCVERepo.return_value = mock_repo_instance

        from utils.cve_sync_operations import sync_kb_edges_for_kbs
        await sync_kb_edges_for_kbs(
            ["KB5052006", "KB5052006", "KB5052006"], mock_vendor, pool=mock_pool
        )

    assert mock_vendor.fetch_microsoft_cves_for_kb.call_count == 1


# ── Task 4: Scheduler wiring ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_sync_job_calls_sync_msrc_kb_edges():
    """full_sync_job must call sync_msrc_kb_edges after run_delta_sync."""
    # run_delta_sync returns {"cve_count": N, "since_date": ..., "completed_at": ..., "used_fallback_window": ...}
    delta_result = {"cve_count": 0, "since_date": None, "completed_at": None, "used_fallback_window": False}
    inventory_result = {"discovered_os_count": 0, "new_os_count": 0, "processed_os_count": 0}

    import sys
    mock_main = MagicMock()
    mock_main.get_cve_scanner = AsyncMock(return_value=MagicMock())
    mock_main.get_eol_orchestrator = MagicMock(return_value=MagicMock())
    sys.modules["main"] = mock_main

    with patch("utils.cve_scheduler.run_inventory_bootstrap_sync", new_callable=AsyncMock, return_value=inventory_result), \
         patch("utils.cve_scheduler.run_delta_sync", new_callable=AsyncMock, return_value=delta_result), \
         patch("utils.cve_scheduler.sync_msrc_kb_edges", new_callable=AsyncMock, return_value=42) as mock_msrc, \
         patch("utils.cve_scheduler._refresh_materialized_views_after_sync", new_callable=AsyncMock), \
         patch("utils.cve_service.get_cve_service", new_callable=AsyncMock, return_value=MagicMock()), \
         patch("utils.vendor_feed_client.VendorFeedClient", return_value=MagicMock()):

        from utils.cve_scheduler import full_sync_job
        await full_sync_job()

    mock_msrc.assert_called_once()


@pytest.mark.asyncio
async def test_incremental_sync_job_calls_sync_msrc_kb_edges():
    """incremental_sync_job must call sync_msrc_kb_edges after run_delta_sync."""
    delta_result = {"cve_count": 0, "since_date": None, "completed_at": None, "used_fallback_window": False}
    inventory_result = {"discovered_os_count": 0, "new_os_count": 0, "processed_os_count": 0}

    import sys
    mock_main = MagicMock()
    mock_main.get_cve_scanner = AsyncMock(return_value=MagicMock())
    mock_main.get_eol_orchestrator = MagicMock(return_value=MagicMock())
    sys.modules["main"] = mock_main

    with patch("utils.cve_scheduler.run_inventory_bootstrap_sync", new_callable=AsyncMock, return_value=inventory_result), \
         patch("utils.cve_scheduler.run_delta_sync", new_callable=AsyncMock, return_value=delta_result), \
         patch("utils.cve_scheduler.sync_msrc_kb_edges", new_callable=AsyncMock, return_value=0) as mock_msrc, \
         patch("utils.cve_scheduler._refresh_materialized_views_after_sync", new_callable=AsyncMock), \
         patch("utils.cve_service.get_cve_service", new_callable=AsyncMock, return_value=MagicMock()), \
         patch("utils.vendor_feed_client.VendorFeedClient", return_value=MagicMock()):

        from utils.cve_scheduler import incremental_sync_job
        await incremental_sync_job()

    mock_msrc.assert_called_once()
