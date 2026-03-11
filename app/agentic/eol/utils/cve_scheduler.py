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
    from utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync
except ImportError:
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.cve_sync_operations import run_delta_sync, run_inventory_bootstrap_sync


logger = get_logger(__name__)

# tzlocal emits a benign warning in minimal containers without /etc/localtime.
# We use explicit UTC scheduling below, so suppress this specific noise.
warnings.filterwarnings(
    "ignore",
    message="Can not find any timezone configuration, defaulting to UTC\\.",
    category=UserWarning,
)

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

    Fetches CVEs modified in the last N days (from config.cve_sync.sync_lookback_days)
    and updates the Cosmos DB repository.
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
