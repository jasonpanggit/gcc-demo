"""
CVE Sync Scheduler - APScheduler integration for periodic CVE database refresh.

Schedules automatic full and incremental CVE synchronization using
APScheduler's AsyncIOScheduler. Integrates with:
- CVEService for sync operations
- CVESyncConfig for schedule and behavior settings

Usage from main.py:

    from utils.cve_scheduler import get_cve_scheduler

    scheduler = get_cve_scheduler()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await scheduler.start()
        yield
        await scheduler.stop()
"""
from __future__ import annotations

import time
import warnings
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    IntervalTrigger = None  # type: ignore[assignment,misc]
    APSCHEDULER_AVAILABLE = False

try:
    from utils.logging_config import get_logger
    from utils.config import config
    from utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync, sync_msrc_kb_edges
except ImportError:
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync, sync_msrc_kb_edges

try:
    from utils.repositories.cve_repository import CVERepository
except ImportError:
    from app.agentic.eol.utils.repositories.cve_repository import CVERepository


logger = get_logger(__name__)

# tzlocal emits a benign warning in minimal containers without /etc/localtime.
# We use explicit UTC scheduling below, so suppress this specific noise.
warnings.filterwarnings(
    "ignore",
    message="Can not find any timezone configuration, defaulting to UTC\\.",
    category=UserWarning,
)


# ---------------------------------------------------------------------------
# Phase 8: I-09 column mapping + MV refresh list updated
# ---------------------------------------------------------------------------

def apply_i09_column_mapping(cve_data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply I-09 column mapping from migration-011 names to bootstrap schema.

    # Column mapping (I-09): severity->cvss_v3_severity, cvss_score->cvss_v3_score,
    # vendor+product->affected_products JSONB, cached_at->synced_at
    """
    mapped = dict(cve_data)

    # severity -> cvss_v3_severity
    if "severity" in mapped and "cvss_v3_severity" not in mapped:
        mapped["cvss_v3_severity"] = mapped.pop("severity")

    # cvss_score -> cvss_v3_score
    if "cvss_score" in mapped and "cvss_v3_score" not in mapped:
        mapped["cvss_v3_score"] = mapped.pop("cvss_score")

    # vendor + product -> affected_products JSONB
    if ("vendor" in mapped or "product" in mapped) and "affected_products" not in mapped:
        vendor = mapped.pop("vendor", None)
        product = mapped.pop("product", None)
        if vendor or product:
            affected = {}
            if vendor:
                affected["vendor"] = vendor
            if product:
                affected["product"] = product
            mapped["affected_products"] = [affected]

    # cached_at -> synced_at
    if "cached_at" in mapped and "synced_at" not in mapped:
        mapped["synced_at"] = mapped.pop("cached_at")

    return mapped


async def _refresh_materialized_views_after_sync(pool) -> None:
    """Refresh bootstrap MVs after sync completes.

    Uses CVERepository.refresh_materialized_views() which refreshes only
    bootstrap MV names (not the 3 dropped migration-011 MVs).
    """
    if pool is None:
        return
    try:
        cve_repo = CVERepository(pool)
        result = await cve_repo.refresh_materialized_views()
        logger.info("Post-sync MV refresh: %s", result)
    except Exception as exc:
        logger.warning("Post-sync MV refresh failed (non-fatal): %s", exc)

# ---------------------------------------------------------------------------
# Job execution tracking
# ---------------------------------------------------------------------------

_job_stats: Dict[str, Dict[str, Any]] = {
    "full_sync": {
        "last_run": None,
        "next_run": None,
        "last_duration_seconds": None,
        "total_runs": 0,
        "total_errors": 0,
        "last_error": None,
        "cve_count_processed": 0,
        "cve_count_updated": 0,
        "cve_count_new": 0,
        "cve_count_errors": 0,
        "inventory_os_discovered": 0,
        "inventory_os_new": 0,
        "inventory_os_processed": 0,
    },
    "incremental_sync": {
        "last_run": None,
        "next_run": None,
        "last_duration_seconds": None,
        "total_runs": 0,
        "total_errors": 0,
        "last_error": None,
        "cve_count_processed": 0,
        "cve_count_updated": 0,
        "cve_count_new": 0,
        "cve_count_errors": 0,
        "inventory_os_discovered": 0,
        "inventory_os_new": 0,
        "inventory_os_processed": 0,
    },
}


def get_scheduler_stats() -> Dict[str, Any]:
    """Return current scheduler job statistics for monitoring APIs."""
    return dict(_job_stats)


# ---------------------------------------------------------------------------
# Job handlers
# ---------------------------------------------------------------------------

async def full_sync_job() -> None:
    """Execute a full CVE sync for the configured lookback period.

    Phase 8: Writes CVE data to PostgreSQL via CVERepository. I-09 column
    mapping applied by CVEService. MV refresh after sync uses bootstrap-only
    MV list (no migration-011 MV names).
    """
    stats = _job_stats["full_sync"]
    stats["last_run"] = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    try:
        # Import here to avoid circular dependency
        from main import get_cve_scanner, get_eol_orchestrator
        from utils.cve_service import get_cve_service

        cve_service = await get_cve_service()
        cve_scanner = await get_cve_scanner()
        eol_orchestrator = get_eol_orchestrator()
        sync_config = config.cve_sync

        inventory_sync = await run_inventory_bootstrap_sync(
            cve_service=cve_service,
            cve_scanner=cve_scanner,
            eol_orchestrator=eol_orchestrator,
            limit_per_os=None,
            force_resync=False,
        )
        stats["inventory_os_discovered"] = inventory_sync.get("discovered_os_count", 0)
        stats["inventory_os_new"] = inventory_sync.get("new_os_count", 0)
        stats["inventory_os_processed"] = inventory_sync.get("processed_os_count", 0)

        # Calculate lookback date
        lookback_date = datetime.now(timezone.utc) - timedelta(days=sync_config.sync_lookback_days)
        logger.info(f"Full CVE sync: fetching CVEs since {lookback_date.isoformat()}")

        # Sync CVEs from external sources
        delta_sync = await run_delta_sync(
            cve_service=cve_service,
            since_date=lookback_date,
            limit=sync_config.max_cves_per_sync,
        )

        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["cve_count_processed"] = delta_sync["cve_count"]
        stats["cve_count_new"] = delta_sync["cve_count"]

        logger.info(
            "Full CVE sync complete: %s CVEs in %.1fs (inventory OS discovered=%s, new=%s, processed=%s)",
            delta_sync["cve_count"],
            elapsed,
            stats["inventory_os_discovered"],
            stats["inventory_os_new"],
            stats["inventory_os_processed"],
        )

        # Sync MSRC KB→CVE edges for the last 3 months.
        # Note: sync_msrc_kb_edges does an internal MV refresh when pool is set;
        # the _refresh_materialized_views_after_sync below is a second pass
        # that picks up any CVE changes from run_delta_sync. This double-refresh
        # is intentional and idempotent.
        try:
            from utils.pg_client import postgres_client
        except ImportError:
            from app.agentic.eol.utils.pg_client import postgres_client
        try:
            from utils.vendor_feed_client import VendorFeedClient
        except ImportError:
            from app.agentic.eol.utils.vendor_feed_client import VendorFeedClient
        try:
            cve_config = config.cve_data
            _vendor_client = VendorFeedClient(
                redhat_base_url=cve_config.redhat_base_url,
                ubuntu_base_url=cve_config.ubuntu_base_url,
                msrc_base_url=cve_config.msrc_base_url,
                msrc_api_key=cve_config.msrc_api_key or None,
                request_timeout=cve_config.request_timeout,
                max_retries=cve_config.max_retries,
            )
            msrc_edge_count = await sync_msrc_kb_edges(
                vendor_client=_vendor_client,
                kb_cve_repo=None,
                n_months=3,
                pool=postgres_client.pool if postgres_client.is_initialized else None,
            )
            logger.info(f"sync_msrc_kb_edges completed: {msrc_edge_count} edges upserted")
        except Exception as e:
            logger.warning(f"sync_msrc_kb_edges failed: {e}")

        # Phase 8: Refresh bootstrap MVs after successful sync
        try:
            from utils.pg_client import postgres_client
        except ImportError:
            from app.agentic.eol.utils.pg_client import postgres_client
        await _refresh_materialized_views_after_sync(
            postgres_client.pool if postgres_client.is_initialized else None
        )

    except Exception as exc:
        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["total_errors"] += 1
        stats["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.error(f"Full CVE sync failed after {elapsed:.1f}s: {exc}")


async def incremental_sync_job() -> None:
    """Execute an incremental CVE sync.

    Fetches CVEs modified since the last successful delta-style sync.
    Also bootstraps CVEs for newly discovered OS inventory identities.

    Phase 8: MV refresh after sync uses bootstrap-only MV list.
    """
    stats = _job_stats["incremental_sync"]
    stats["last_run"] = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    try:
        from main import get_cve_scanner, get_eol_orchestrator
        from utils.cve_service import get_cve_service

        cve_service = await get_cve_service()
        cve_scanner = await get_cve_scanner()
        eol_orchestrator = get_eol_orchestrator()
        sync_config = config.cve_sync

        inventory_sync = await run_inventory_bootstrap_sync(
            cve_service=cve_service,
            cve_scanner=cve_scanner,
            eol_orchestrator=eol_orchestrator,
            limit_per_os=None,
            force_resync=False,
        )
        stats["inventory_os_discovered"] = inventory_sync.get("discovered_os_count", 0)
        stats["inventory_os_new"] = inventory_sync.get("new_os_count", 0)
        stats["inventory_os_processed"] = inventory_sync.get("processed_os_count", 0)

        delta_sync = await run_delta_sync(
            cve_service=cve_service,
            lookback_days=sync_config.sync_lookback_days,
            limit=sync_config.max_cves_per_sync,
        )

        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["cve_count_processed"] = delta_sync["cve_count"]
        stats["cve_count_updated"] = delta_sync["cve_count"]

        logger.info(
            "Incremental CVE sync complete: %s CVEs in %.1fs (inventory OS new=%s, processed=%s)",
            delta_sync["cve_count"],
            elapsed,
            stats["inventory_os_new"],
            stats["inventory_os_processed"],
        )

        # Sync MSRC KB→CVE edges for the last 3 months.
        # Note: sync_msrc_kb_edges does an internal MV refresh when pool is set;
        # the _refresh_materialized_views_after_sync below is a second pass
        # that picks up any CVE changes from run_delta_sync. This double-refresh
        # is intentional and idempotent.
        try:
            from utils.pg_client import postgres_client
        except ImportError:
            from app.agentic.eol.utils.pg_client import postgres_client
        try:
            from utils.vendor_feed_client import VendorFeedClient
        except ImportError:
            from app.agentic.eol.utils.vendor_feed_client import VendorFeedClient
        try:
            cve_config = config.cve_data
            _vendor_client = VendorFeedClient(
                redhat_base_url=cve_config.redhat_base_url,
                ubuntu_base_url=cve_config.ubuntu_base_url,
                msrc_base_url=cve_config.msrc_base_url,
                msrc_api_key=cve_config.msrc_api_key or None,
                request_timeout=cve_config.request_timeout,
                max_retries=cve_config.max_retries,
            )
            msrc_edge_count = await sync_msrc_kb_edges(
                vendor_client=_vendor_client,
                kb_cve_repo=None,
                n_months=3,
                pool=postgres_client.pool if postgres_client.is_initialized else None,
            )
            logger.info(f"sync_msrc_kb_edges completed: {msrc_edge_count} edges upserted")
        except Exception as e:
            logger.warning(f"sync_msrc_kb_edges failed: {e}")

        # Phase 8: Refresh bootstrap MVs after successful sync
        try:
            from utils.pg_client import postgres_client
        except ImportError:
            from app.agentic.eol.utils.pg_client import postgres_client
        await _refresh_materialized_views_after_sync(
            postgres_client.pool if postgres_client.is_initialized else None
        )

    except Exception as exc:
        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["total_errors"] += 1
        stats["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.error(f"Incremental CVE sync failed after {elapsed:.1f}s: {exc}")


# ---------------------------------------------------------------------------
# CVEScheduler
# ---------------------------------------------------------------------------

class CVEScheduler:
    """Manages APScheduler lifecycle for CVE sync jobs.

    Reads cron/interval schedules from config.cve_sync and registers
    full_sync_job and incremental_sync_job.

    Usage:

        scheduler = CVEScheduler()
        await scheduler.start()    # call in FastAPI startup
        await scheduler.stop()     # call in FastAPI shutdown
    """

    FULL_SYNC_JOB_ID = "cve_full_sync"
    INCREMENTAL_SYNC_JOB_ID = "cve_incremental_sync"

    def __init__(self) -> None:
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the scheduler with configured jobs."""
        sync_config = config.cve_sync

        if not sync_config.enable_cve_sync:
            logger.info("CVEScheduler: CVE sync disabled — not starting")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "CVEScheduler: apscheduler not installed — "
                "periodic sync disabled (pip install apscheduler)"
            )
            return

        if self._running:
            logger.warning("CVEScheduler: already running")
            return

        self._scheduler = AsyncIOScheduler(timezone=timezone.utc)

        # -- Full sync job (cron) -------------------------------------------
        cron_expr = sync_config.full_sync_schedule_cron
        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone=timezone.utc)
            self._scheduler.add_job(
                full_sync_job,
                trigger=trigger,
                id=self.FULL_SYNC_JOB_ID,
                name="CVE Full Sync",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info(f"Scheduled full CVE sync: cron='{cron_expr}'")
        except Exception as exc:
            logger.error(f"Failed to schedule full CVE sync with cron '{cron_expr}': {exc}")

        # -- Incremental sync job (interval) --------------------------------
        interval_hours = sync_config.incremental_sync_interval_hours
        try:
            self._scheduler.add_job(
                incremental_sync_job,
                trigger=IntervalTrigger(hours=interval_hours, timezone=timezone.utc),
                id=self.INCREMENTAL_SYNC_JOB_ID,
                name="CVE Incremental Sync",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info(f"Scheduled incremental CVE sync: every {interval_hours} hours")
        except Exception as exc:
            logger.error(f"Failed to schedule incremental CVE sync: {exc}")

        # -- Materialized view refresh job (every 15 min) ------------------
        try:
            self._scheduler.add_job(
                self._refresh_materialized_views_job,
                trigger=IntervalTrigger(minutes=15, timezone=timezone.utc),
                id="mv_refresh_job",
                name="Materialized View Refresh",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,  # 5 min grace
            )
            logger.info("Scheduled materialized view refresh: every 15 minutes")
        except Exception as exc:
            logger.error(f"Failed to schedule MV refresh job: {exc}")

        self._scheduler.start()
        self._running = True

        # Update next_run times
        self._update_next_run_times()

        logger.info(f"CVEScheduler started (full={cron_expr}, incremental={interval_hours}h)")

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("CVEScheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return scheduler status and job statistics for monitoring."""
        self._update_next_run_times()
        return {
            "running": self._running,
            "apscheduler_available": APSCHEDULER_AVAILABLE,
            "cve_sync_enabled": config.cve_sync.enable_cve_sync,
            "full_sync_cron": config.cve_sync.full_sync_schedule_cron,
            "incremental_interval_hours": config.cve_sync.incremental_sync_interval_hours,
            "sync_lookback_days": config.cve_sync.sync_lookback_days,
            "jobs": get_scheduler_stats(),
        }

    async def _refresh_materialized_views_job(self) -> None:
        """Scheduled job: refresh materialized views every 15 minutes."""
        try:
            logger.info("Starting scheduled materialized view refresh...")

            # Import pg_client
            try:
                from utils.pg_client import postgres_client
            except ModuleNotFoundError:
                from app.agentic.eol.utils.pg_client import postgres_client

            if not postgres_client.is_configured():
                logger.warning("PostgreSQL not configured, skipping MV refresh")
                return

            pool = postgres_client.pool
            async with pool.acquire() as conn:
                # Refresh all MVs except mv_cve_dashboard_summary (now a regular VIEW)
                views_to_refresh = [
                    "mv_vm_vulnerability_posture",
                    "mv_vm_cve_detail",
                    "mv_cve_exposure",
                    "mv_cve_trending",
                    "mv_cve_top_by_score",
                ]

                for view_name in views_to_refresh:
                    try:
                        await conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}")
                        logger.info(f"✅ Refreshed {view_name}")
                    except Exception as view_error:
                        logger.error(f"Failed to refresh {view_name}: {view_error}")

            logger.info("✅ Scheduled materialized view refresh completed")

        except Exception as e:
            logger.error(f"Scheduled MV refresh failed: {e}")

    def _update_next_run_times(self) -> None:
        """Refresh next_run fields from the live scheduler."""
        if not self._scheduler or not self._running:
            return
        for job_id, stats_key in [
            (self.FULL_SYNC_JOB_ID, "full_sync"),
            (self.INCREMENTAL_SYNC_JOB_ID, "incremental_sync"),
        ]:
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                _job_stats[stats_key]["next_run"] = job.next_run_time.isoformat()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler_instance: Optional[CVEScheduler] = None


def get_cve_scheduler() -> CVEScheduler:
    """Get or create the CVEScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CVEScheduler()
    return _scheduler_instance
