"""
CVE Sync API Router

Provides endpoints for manual CVE sync operations and scheduler monitoring.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import with_timeout_and_stats, write_endpoint, readonly_endpoint
    from utils.logging_config import get_logger
    from utils.cve_scheduler import get_cve_scheduler
    from utils.config import config
except ImportError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import with_timeout_and_stats, write_endpoint, readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.cve_scheduler import get_cve_scheduler
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
@write_endpoint(agent_name="cve_sync_trigger", timeout_seconds=300)
async def trigger_full_sync(
    lookback_days: int = Query(default=7, description="Fetch CVEs modified in last N days")
) -> StandardResponse:
    """Manually trigger full CVE sync.

    Admin-only endpoint. Fetches CVEs modified in the last N days
    and updates Cosmos DB.

    Args:
        lookback_days: How many days back to sync (default 7)

    Returns:
        StandardResponse with sync results (CVE count, duration)
    """
    try:
        # Import here to get singleton
        from main import get_cve_service

        cve_service = await get_cve_service()

        # Calculate lookback date
        since_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        logger.info(f"Manual full sync triggered: lookback={lookback_days} days")

        # Execute sync
        import time
        start = time.monotonic()
        synced_count = await cve_service.sync_recent_cves(
            since_date=since_date,
            limit=config.cve_sync.max_cves_per_sync
        )
        duration = round(time.monotonic() - start, 2)

        logger.info(f"Manual full sync complete: {synced_count} CVEs in {duration}s")

        return StandardResponse(
            success=True,
            message=f"Full sync completed: {synced_count} CVEs synced",
            data={
                "cve_count": synced_count,
                "lookback_days": lookback_days,
                "duration_seconds": duration,
                "since_date": since_date.isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Manual full sync failed: {e}")
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
@write_endpoint(agent_name="cve_sync_incremental", timeout_seconds=300)
async def trigger_incremental_sync() -> StandardResponse:
    """Manually trigger incremental CVE sync.

    Admin-only endpoint. Syncs CVEs modified since last full sync.

    Returns:
        StandardResponse with sync results (CVE count, duration)
    """
    try:
        # Import here to avoid circular dependency
        from utils.cve_scheduler import _last_full_sync_time
        from main import get_cve_service

        if _last_full_sync_time is None:
            # No baseline, trigger full sync instead
            logger.info("Manual incremental sync: no baseline — triggering full sync")
            lookback_days = config.cve_sync.sync_lookback_days
            since_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        else:
            since_date = _last_full_sync_time
            logger.info(f"Manual incremental sync triggered: since {since_date.isoformat()}")

        cve_service = await get_cve_service()

        # Execute sync
        import time
        start = time.monotonic()
        synced_count = await cve_service.sync_recent_cves(
            since_date=since_date,
            limit=config.cve_sync.max_cves_per_sync
        )
        duration = round(time.monotonic() - start, 2)

        logger.info(f"Manual incremental sync complete: {synced_count} CVEs in {duration}s")

        return StandardResponse(
            success=True,
            message=f"Incremental sync completed: {synced_count} CVEs synced",
            data={
                "cve_count": synced_count,
                "duration_seconds": duration,
                "since_date": since_date.isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Manual incremental sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
