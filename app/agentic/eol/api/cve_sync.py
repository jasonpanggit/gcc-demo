"""
CVE Sync API Router

Provides endpoints for manual CVE sync operations and scheduler monitoring.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import with_timeout_and_stats, write_endpoint, readonly_endpoint
    from utils.logging_config import get_logger
    from utils.cve_scheduler import get_cve_scheduler
    from utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync, sync_msrc_kb_edges
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import with_timeout_and_stats, write_endpoint, readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.cve_scheduler import get_cve_scheduler
    from app.agentic.eol.utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync, sync_msrc_kb_edges
    from app.agentic.eol.utils.config import config


router = APIRouter()
logger = get_logger(__name__)


@router.get("/cve-sync/status")
@readonly_endpoint(agent_name="cve_sync_status", timeout_seconds=5)
async def get_sync_status() -> StandardResponse:
    """Get CVE sync scheduler status and job statistics.

    Returns:
        StandardResponse with scheduler status, job stats, and next run times
    """
    try:
        scheduler = get_cve_scheduler()
        status = scheduler.get_status()

        return StandardResponse(
            success=True,
            message="CVE sync scheduler status retrieved",
            data=status
        )
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TriggerSyncRequest(BaseModel):
    """Request model for manual sync trigger."""
    lookback_days: Optional[int] = 7


@router.post("/cve-sync/trigger")
@write_endpoint(agent_name="cve_sync_trigger", timeout_seconds=10)
async def trigger_full_sync(
    lookback_days: int = Query(default=7, description="Fetch CVEs modified in last N days"),
    force_inventory_resync: bool = Query(
        default=False,
        description="Deprecated. Full sync now only bootstraps CVEs for newly discovered OS inventory identities.",
    ),
) -> StandardResponse:
    """Manually trigger full CVE sync (fire-and-forget).

    Admin-only endpoint. Kicks off inventory + delta sync as a background task
    and returns immediately.

    Args:
        lookback_days: How many days back to sync (default 7)

    Returns:
        StandardResponse confirming the background sync was started
    """
    try:
        from main import get_cve_scanner, get_cve_service, get_eol_orchestrator, get_os_summary_repo

        cve_service = await get_cve_service()
        cve_scanner = await get_cve_scanner()
        eol_orchestrator = get_eol_orchestrator()
        os_summary_repo = await get_os_summary_repo()

        since_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        inventory_force_resync = False
        if force_inventory_resync:
            logger.info(
                "Manual full sync received deprecated force_inventory_resync=true; ignoring and running new-OS-only inventory bootstrap"
            )
        logger.info(
            "Manual full sync enqueued: lookback=%s days, inventory_sync_mode=%s",
            lookback_days,
            "new-only",
        )

        async def _run_full_sync() -> None:
            import time
            start = time.monotonic()
            try:
                inventory_sync = await run_inventory_bootstrap_sync(
                    cve_service=cve_service,
                    cve_scanner=cve_scanner,
                    eol_orchestrator=eol_orchestrator,
                    limit_per_os=None,
                    force_resync=inventory_force_resync,
                    os_summary_repo=os_summary_repo,
                )
                delta_sync = await run_delta_sync(
                    cve_service=cve_service,
                    since_date=since_date,
                    limit=config.cve_sync.max_cves_per_sync,
                )
                duration = round(time.monotonic() - start, 2)
                logger.info(
                    "Background full sync complete: %s CVEs, %s OS in %ss",
                    delta_sync["cve_count"],
                    inventory_sync.get("processed_os_count", 0),
                    duration,
                )
            except Exception as exc:
                logger.error(
                    "Background full sync failed after %.1fs: %s",
                    time.monotonic() - start,
                    exc,
                    exc_info=True
                )

        asyncio.create_task(_run_full_sync())

        return StandardResponse(
            success=True,
            message="Full sync started in background",
            data={
                "lookback_days": lookback_days,
                "inventory_sync_mode": "new-only",
                "status": "running",
            }
        )
    except Exception as e:
        logger.error(f"Manual full sync failed to start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve-sync/trigger/{cve_id}")
@write_endpoint(agent_name="cve_sync_single", timeout_seconds=60)
async def trigger_single_cve_sync(cve_id: str) -> StandardResponse:
    """Manually sync a single CVE by ID.

    Admin-only endpoint. Forces refresh from external APIs.

    Args:
        cve_id: CVE identifier (e.g., CVE-2024-1234)

    Returns:
        StandardResponse with CVE data
    """
    try:
        # Import here to get singleton
        from main import get_cve_service

        cve_service = await get_cve_service()
        cve_id = cve_id.upper()

        logger.info(f"Manual single CVE sync triggered: {cve_id}")

        # Execute sync (force_refresh=True)
        import time
        start = time.monotonic()
        cve = await cve_service.sync_cve(cve_id)
        duration = round(time.monotonic() - start, 2)

        if cve is None:
            logger.warning(f"CVE {cve_id} not found in any source")
            return StandardResponse(
                success=False,
                message=f"CVE {cve_id} not found",
                data={"cve_id": cve_id, "duration_seconds": duration}
            )

        logger.info(f"Manual single CVE sync complete: {cve_id} in {duration}s")

        return StandardResponse(
            success=True,
            message=f"CVE {cve_id} synced successfully",
            data={
                "cve_id": cve_id,
                "duration_seconds": duration,
                "sources": cve.sources,
                "severity": cve.cvss_v3.base_severity if cve.cvss_v3 else None
            }
        )
    except Exception as e:
        logger.error(f"Manual single CVE sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve-sync/incremental")
@write_endpoint(agent_name="cve_sync_incremental", timeout_seconds=10)
async def trigger_incremental_sync() -> StandardResponse:
    """Manually trigger incremental CVE sync (fire-and-forget).

    Admin-only endpoint. Syncs CVEs modified since last full sync
    as a background task and returns immediately.

    Returns:
        StandardResponse confirming the background sync was started
    """
    try:
        from main import get_cve_service, get_cve_scanner, get_eol_orchestrator, get_os_summary_repo

        cve_service = await get_cve_service()
        cve_scanner = await get_cve_scanner()
        eol_orchestrator = get_eol_orchestrator()
        os_summary_repo = await get_os_summary_repo()

        logger.info("Manual incremental sync enqueued: inventory_sync_mode=new-only")

        async def _run_incremental_sync() -> None:
            import time
            start = time.monotonic()
            try:
                inventory_sync = await run_inventory_bootstrap_sync(
                    cve_service=cve_service,
                    cve_scanner=cve_scanner,
                    eol_orchestrator=eol_orchestrator,
                    limit_per_os=None,
                    force_resync=False,
                    os_summary_repo=os_summary_repo,
                )
                delta_sync = await run_delta_sync(
                    cve_service=cve_service,
                    lookback_days=config.cve_sync.sync_lookback_days,
                    limit=config.cve_sync.max_cves_per_sync,
                )
                duration = round(time.monotonic() - start, 2)
                logger.info(
                    "Background incremental sync complete: %s CVEs, %s OS in %ss",
                    delta_sync["cve_count"],
                    inventory_sync.get("processed_os_count", 0),
                    duration,
                )
            except Exception as exc:
                logger.error(
                    "Background incremental sync failed after %.1fs: %s",
                    time.monotonic() - start,
                    exc,
                    exc_info=True
                )

        asyncio.create_task(_run_incremental_sync())

        return StandardResponse(
            success=True,
            message="Incremental sync started in background",
            data={
                "inventory_sync_mode": "new-only",
                "status": "running",
            }
        )
    except Exception as e:
        logger.error(f"Manual incremental sync failed to start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve-sync/msrc-kb-edges")
@write_endpoint(agent_name="msrc_kb_edge_sync", timeout_seconds=120)
async def trigger_msrc_kb_sync(
    n_months: int = Query(default=6, ge=1, le=24, description="Number of months to sync")
) -> StandardResponse:
    """Trigger MSRC KB-to-CVE edge sync.

    Fetches KB-to-CVE mappings from Microsoft Security Update Guide
    for the last N months and populates the kb_cve_edges table.

    Args:
        n_months: Number of months of MSRC data to fetch (default: 6, max: 24)

    Returns:
        StandardResponse with count of edges synced
    """
    try:
        from main import get_cve_service
        from utils.kb_cve_edge_repository import KBCVEEdgeRepository
        from utils.pg_client import postgres_client

        cve_service = await get_cve_service()
        vendor_client = cve_service.aggregator.vendor_feed_client
        pool = postgres_client.pool
        kb_cve_repo = KBCVEEdgeRepository(pool)

        logger.info(f"Starting MSRC KB-CVE edge sync for {n_months} months")

        edge_count = await sync_msrc_kb_edges(
            vendor_client=vendor_client,
            kb_cve_repo=kb_cve_repo,
            n_months=n_months,
            pool=pool,
        )

        return StandardResponse(
            success=True,
            message=f"MSRC KB-CVE sync completed: {edge_count} edges upserted",
            data={
                "edge_count": edge_count,
                "months_synced": n_months,
            }
        )
    except Exception as e:
        logger.error(f"MSRC KB-CVE sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
