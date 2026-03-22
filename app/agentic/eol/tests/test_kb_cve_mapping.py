"""Tests for KB→CVE mapping pipeline fixes."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any
from types import SimpleNamespace


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
    mock_vendor.fetch_microsoft_cves_for_kb_sug.assert_not_called()


@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_normalises_kb_prefix():
    """KB numbers without 'KB' prefix should be normalised before MSRC call."""
    mock_vendor = AsyncMock()
    mock_vendor.fetch_microsoft_cves_for_kb_sug = AsyncMock(return_value=["CVE-2025-0001"])

    mock_pool = MagicMock()

    with patch("utils.cve_sync_operations.CVERepository") as MockCVERepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.upsert_kb_cve_edges = AsyncMock(return_value=1)
        MockCVERepo.return_value = mock_repo_instance

        from utils.cve_sync_operations import sync_kb_edges_for_kbs
        await sync_kb_edges_for_kbs(["5052006"], mock_vendor, pool=mock_pool)

    mock_vendor.fetch_microsoft_cves_for_kb_sug.assert_called_once_with("KB5052006")


@pytest.mark.asyncio
async def test_sync_kb_edges_for_kbs_isolates_per_kb_errors():
    """A failed MSRC call for one KB should not abort the batch."""
    mock_vendor = AsyncMock()
    mock_vendor.fetch_microsoft_cves_for_kb_sug = AsyncMock(
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
    mock_vendor.fetch_microsoft_cves_for_kb_sug = AsyncMock(return_value=["CVE-2025-0001"])
    mock_pool = MagicMock()

    with patch("utils.cve_sync_operations.CVERepository") as MockCVERepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.upsert_kb_cve_edges = AsyncMock(return_value=1)
        MockCVERepo.return_value = mock_repo_instance

        from utils.cve_sync_operations import sync_kb_edges_for_kbs
        await sync_kb_edges_for_kbs(
            ["KB5052006", "KB5052006", "KB5052006"], mock_vendor, pool=mock_pool
        )

    assert mock_vendor.fetch_microsoft_cves_for_kb_sug.call_count == 1


@pytest.mark.asyncio
async def test_get_installed_patches_for_vm_skips_placeholder_rows_and_closes_vendor():
    """Zero-edge syncs should return empty CVE lists without writing NULL placeholder rows."""
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=[
        [{"kb_number": "KB5052006", "patch_name": "2025-03 Cumulative Update for Server"}],
        [],
    ])
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock()

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_vendor = MagicMock()
    mock_vendor.close = AsyncMock()

    from utils.repositories.patch_repository import PatchRepository
    repo = PatchRepository(mock_pool)

    cfg = SimpleNamespace(
        cve_data=SimpleNamespace(
            redhat_base_url="https://example.test/redhat",
            ubuntu_base_url="https://example.test/ubuntu",
            msrc_base_url="https://example.test/msrc",
            msrc_api_key=None,
            request_timeout=5,
        )
    )

    with patch("utils.vendor_feed_client.VendorFeedClient", return_value=mock_vendor), \
         patch("utils.cve_sync_operations.sync_kb_edges_for_kbs", new=AsyncMock(return_value=0)), \
         patch("utils.config.get_config", return_value=cfg):
        result = await repo.get_installed_patches_for_vm("/subscriptions/test/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/test-vm")

    assert result == [{
        "patch_id": "KB5052006",
        "kb_ids": ["KB5052006"],
        "patch_name": "2025-03 Cumulative Update for Server",
        "classification": "Installed",
        "cve_ids": [],
    }]
    mock_conn.execute.assert_not_called()
    mock_conn.fetchrow.assert_not_called()
    mock_vendor.close.assert_awaited_once()


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
         patch("utils.cve_scheduler._run_msrc_kb_edge_sync_step", new_callable=AsyncMock, return_value=42) as mock_msrc_step, \
         patch("utils.cve_scheduler._refresh_materialized_views_after_sync", new_callable=AsyncMock), \
         patch("utils.cve_service.get_cve_service", new_callable=AsyncMock, return_value=MagicMock()):

        from utils.cve_scheduler import full_sync_job
        await full_sync_job()

    mock_msrc_step.assert_called_once()


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
         patch("utils.cve_scheduler._run_msrc_kb_edge_sync_step", new_callable=AsyncMock, return_value=0) as mock_msrc_step, \
         patch("utils.cve_scheduler._refresh_materialized_views_after_sync", new_callable=AsyncMock), \
         patch("utils.cve_service.get_cve_service", new_callable=AsyncMock, return_value=MagicMock()):

        from utils.cve_scheduler import incremental_sync_job
        await incremental_sync_job()

    mock_msrc_step.assert_called_once()


# ── Task 5: LAW KQL fix ───────────────────────────────────────────────────

def test_get_software_inventory_kql_includes_windows_update_type():
    """The KQL query must filter ConfigDataType in ('Software', 'WindowsUpdate')."""
    import inspect
    from agents.software_inventory_agent import SoftwareInventoryAgent

    # Get the source of the module to check the KQL string
    import agents.software_inventory_agent as agent_mod
    source = inspect.getsource(agent_mod)

    assert ('WindowsUpdate' in source), "KQL must include WindowsUpdate ConfigDataType"
    assert ('KBNumber' in source or 'KBID' in source or 'kbid' in source.lower()), \
           "KQL must project KB number field"


def test_software_inventory_result_includes_kb_number():
    """Result rows from software inventory must include a kb_number field."""
    import inspect
    from agents.software_inventory_agent import SoftwareInventoryAgent

    import agents.software_inventory_agent as agent_mod
    source = inspect.getsource(agent_mod)

    assert ('"kb_number"' in source or "'kb_number'" in source), \
           "Row parsing must include kb_number key in result dict"


# ── Task 6: Software inventory Postgres persist ───────────────────────────

@pytest.mark.asyncio
async def test_persist_software_inventory_writes_to_postgres():
    """_persist_software_inventory_to_postgres must upsert to inventory_software_cache."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("agents.software_inventory_agent.postgres_client") as mock_pg:
        mock_pg.pool = mock_pool
        mock_pg.is_initialized = True

        from agents.software_inventory_agent import SoftwareInventoryAgent
        agent = SoftwareInventoryAgent()

        results = [{"computer": "PC01", "name": "curl", "version": "8.0", "kb_number": ""}]
        await agent._persist_software_inventory_to_postgres(results)

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    call_sql = call_args[0][0]
    assert "inventory_software_cache" in call_sql


@pytest.mark.asyncio
async def test_persist_software_inventory_skips_when_pool_none():
    """Must not raise if postgres_client.pool is None."""
    with patch("agents.software_inventory_agent.postgres_client") as mock_pg:
        mock_pg.pool = None
        mock_pg.is_initialized = False

        from agents.software_inventory_agent import SoftwareInventoryAgent
        agent = SoftwareInventoryAgent()

        # Should not raise
        await agent._persist_software_inventory_to_postgres([{"computer": "PC01"}])


# ── Task 7: ARG patch upsert call site ────────────────────────────────────

@pytest.mark.asyncio
async def test_arg_patch_fetch_triggers_upsert_available_patches():
    """After query_patch_assessments, upsert_available_patches must be called for each VM.

    Primary call site: utils/cve_patch_enricher.py CVEPatchEnricher.prefetch_patch_data()
    Result structure: {"success": True, "data": [{"machine_name": ..., "resource_id": ...,
                        "patches": {"available_patches": [...]}}]}
    """
    # Build a realistic ARG response with one VM and two patches
    sample_patches = [
        {"patchName": "Security Update", "kbId": "5052006",
         "classifications": ["Critical"], "rebootBehavior": "AlwaysRequiresReboot",
         "assessmentState": "Available"},
        {"patchName": "Cumulative Update", "kbId": "5048667",
         "classifications": ["Security"], "rebootBehavior": "NeverReboots",
         "assessmentState": "Available"},
    ]
    mock_qpa_result = {
        "success": True,
        "data": [
            {
                "machine_name": "vm-prod-01",
                "resource_id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm-prod-01",
                "patches": {"available_patches": sample_patches},
            }
        ],
    }

    mock_patch_mcp = AsyncMock()
    mock_patch_mcp.query_patch_assessments = AsyncMock(return_value=mock_qpa_result)

    mock_kb_cve_repo = MagicMock()

    mock_vendor = MagicMock()
    mock_vendor.close = AsyncMock()

    # Patch PatchRepository.upsert_available_patches and the downstream dependencies
    with patch("utils.pg_client.postgres_client") as mock_pg, \
         patch("utils.repositories.patch_repository.PatchRepository.upsert_available_patches",
               new_callable=AsyncMock, return_value=2) as mock_upsert, \
         patch("utils.cve_sync_operations.sync_kb_edges_for_kbs", new=AsyncMock(return_value=0)) as mock_sync, \
         patch("utils.vendor_feed_client.VendorFeedClient", return_value=mock_vendor):

        mock_pg.pool = MagicMock()  # truthy pool so KB sync branch fires

        from utils.cve_patch_enricher import CVEPatchEnricher
        enricher = CVEPatchEnricher(mock_patch_mcp, mock_kb_cve_repo)

        result_map = await enricher.prefetch_patch_data(["sub1"], [])

    # The mapping should contain the VM
    assert "vm-prod-01" in result_map, "prefetch_patch_data should return vm-prod-01 in mapping"

    # upsert_available_patches must have been called once (one VM)
    assert mock_upsert.called, "upsert_available_patches should be called after query_patch_assessments"
    call_args = mock_upsert.call_args
    assert call_args[0][0] == mock_qpa_result["data"][0]["resource_id"], \
        "upsert_available_patches should receive the VM resource_id"
    assert call_args[0][1] == sample_patches, \
        "upsert_available_patches should receive the available_patches list"

    # KB→CVE sync should run for the discovered KB numbers and close the vendor client.
    mock_sync.assert_awaited_once()
    assert mock_sync.await_args.args[0] == ["KB5052006", "KB5048667"]
    assert mock_sync.await_args.kwargs["pool"] is mock_pg.pool
    mock_vendor.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_arg_patch_fetch_upsert_failure_does_not_block_main_flow():
    """If upsert_available_patches raises, prefetch_patch_data must still return the mapping."""
    mock_qpa_result = {
        "success": True,
        "data": [
            {
                "machine_name": "vm-test",
                "resource_id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/virtualMachines/vm-test",
                "patches": {"available_patches": [
                    {"patchName": "Update", "kbId": "5000001",
                     "classifications": ["Critical"], "rebootBehavior": "AlwaysRequiresReboot",
                     "assessmentState": "Available"},
                ]},
            }
        ],
    }

    mock_patch_mcp = AsyncMock()
    mock_patch_mcp.query_patch_assessments = AsyncMock(return_value=mock_qpa_result)

    with patch("utils.pg_client.postgres_client") as mock_pg, \
         patch("utils.repositories.patch_repository.PatchRepository.upsert_available_patches",
               new_callable=AsyncMock, side_effect=RuntimeError("DB unavailable")):

        mock_pg.pool = MagicMock()

        from utils.cve_patch_enricher import CVEPatchEnricher
        enricher = CVEPatchEnricher(mock_patch_mcp, MagicMock())

        result_map = await enricher.prefetch_patch_data(["sub1"], [])

    # Main flow must not be blocked — mapping still returned
    assert "vm-test" in result_map, "prefetch_patch_data must return VM mapping even if upsert fails"


# ── Task 8: CVEPatchMapper factory fix ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_cve_patch_mapper_has_kb_cve_edge_repository():
    """Factory-created CVEPatchMapper must have kb_cve_edge_repository injected."""
    import utils.cve_patch_mapper as mapper_mod

    # Reset singleton so factory runs fresh
    mapper_mod._cve_patch_mapper_instance = None

    with patch("utils.cve_service.get_cve_service", new_callable=AsyncMock), \
         patch("utils.cve_scanner.get_cve_scanner", new_callable=AsyncMock), \
         patch("utils.patch_mcp_client.get_patch_mcp_client", new_callable=AsyncMock), \
         patch("utils.cve_patch_mapper.postgres_client") as mock_pg:

        mock_pg.pool = MagicMock()  # non-None pool

        from utils.cve_patch_mapper import get_cve_patch_mapper
        mapper = await get_cve_patch_mapper()

    assert mapper.kb_cve_edge_repository is not None, \
        "kb_cve_edge_repository must be injected into CVEPatchMapper"
