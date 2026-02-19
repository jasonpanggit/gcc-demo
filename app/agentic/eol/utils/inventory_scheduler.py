"""
Inventory Scheduler - APScheduler integration for periodic resource discovery.

Schedules automatic full and incremental resource discovery scans using
APScheduler's AsyncIOScheduler. Integrates with:
- ResourceDiscoveryEngine for Azure Resource Graph queries
- ResourceInventoryCache for dual-layer caching
- InventoryConfig for schedule and behaviour settings

Usage from main.py::

    from utils.inventory_scheduler import InventoryScheduler

    scheduler = InventoryScheduler()

    @app.on_event("startup")
    async def startup():
        await scheduler.start()

    @app.on_event("shutdown")
    async def shutdown():
        await scheduler.stop()
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

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
    from app.agentic.eol.utils.logger import get_logger
except ImportError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

try:
    from app.agentic.eol.utils.config import config
except ImportError:
    from utils.config import config  # type: ignore[import-not-found]

try:
    from app.agentic.eol.utils.resource_discovery_engine import ResourceDiscoveryEngine
except ImportError:
    from utils.resource_discovery_engine import ResourceDiscoveryEngine  # type: ignore[import-not-found]

try:
    from app.agentic.eol.utils.resource_inventory_cache import get_resource_inventory_cache
except ImportError:
    from utils.resource_inventory_cache import get_resource_inventory_cache  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Job execution tracking
# ---------------------------------------------------------------------------

_job_stats: Dict[str, Dict[str, Any]] = {
    "full_scan": {
        "last_run": None,
        "next_run": None,
        "last_duration_seconds": None,
        "total_runs": 0,
        "total_errors": 0,
        "last_error": None,
        "last_resource_count": 0,
    },
    "incremental_scan": {
        "last_run": None,
        "next_run": None,
        "last_duration_seconds": None,
        "total_runs": 0,
        "total_errors": 0,
        "last_error": None,
        "last_changes": {"created": 0, "modified": 0, "deleted": 0},
    },
}

# Track resource IDs from last full scan for incremental diffing
_cached_resource_ids: Set[str] = set()
_last_scan_time: Optional[str] = None


def get_scheduler_stats() -> Dict[str, Any]:
    """Return current scheduler job statistics for monitoring APIs."""
    return dict(_job_stats)


# ---------------------------------------------------------------------------
# Job handlers
# ---------------------------------------------------------------------------

async def full_refresh_job() -> None:
    """Execute a full resource discovery scan across all subscriptions.

    - Discovers all accessible subscriptions
    - Runs full_resource_discovery for each subscription
    - Stores results in ResourceInventoryCache
    - Updates the cached resource ID set for incremental diffing
    """
    global _cached_resource_ids, _last_scan_time

    stats = _job_stats["full_scan"]
    stats["last_run"] = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    try:
        inv_config = config.inventory
        engine = ResourceDiscoveryEngine()
        cache = get_resource_inventory_cache()

        subscriptions = await engine.discover_all_subscriptions()
        logger.info("Full scan: discovered %d subscriptions", len(subscriptions))

        total_resources = 0
        new_ids: Set[str] = set()

        for sub in subscriptions:
            # Handle both dict (expected) and string (backward compatibility)
            if isinstance(sub, dict):
                sub_id = sub["subscription_id"]
            else:
                sub_id = str(sub)
            
            try:
                resources = await engine.full_resource_discovery(sub_id)
                total_resources += len(resources)

                # Collect resource IDs for incremental diffing
                for r in resources:
                    rid = r.get("resource_id", "")
                    if rid:
                        new_ids.add(rid)

                # Group by resource type and cache
                by_type: Dict[str, list] = {}
                for r in resources:
                    rtype = r.get("resource_type", "unknown")
                    by_type.setdefault(rtype, []).append(r)

                for rtype, typed_resources in by_type.items():
                    await cache.set(sub_id, rtype, typed_resources)

                logger.info(
                    "Full scan: subscription %s — %d resources (%d types)",
                    sub_id, len(resources), len(by_type),
                )
            except Exception as exc:
                if inv_config.skip_failed_subscriptions:
                    logger.warning(
                        "Full scan: skipping subscription %s due to error: %s",
                        sub_id, exc,
                    )
                else:
                    raise

        _cached_resource_ids = new_ids
        _last_scan_time = datetime.now(timezone.utc).isoformat()

        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["last_resource_count"] = total_resources

        logger.info(
            "Full scan complete: %d resources across %d subscriptions in %.1fs",
            total_resources, len(subscriptions), elapsed,
        )

    except Exception as exc:
        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["total_errors"] += 1
        stats["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.error("Full scan failed after %.1fs: %s", elapsed, exc)


async def incremental_refresh_job() -> None:
    """Execute an incremental discovery scan to detect changes.

    Compares current Resource Graph state against the last full scan
    to identify created, modified, and deleted resources. Only changed
    resources are written to the cache.
    """
    global _last_scan_time

    stats = _job_stats["incremental_scan"]
    stats["last_run"] = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    if not _last_scan_time:
        logger.info("Incremental scan: no previous full scan — triggering full scan instead")
        await full_refresh_job()
        return

    try:
        inv_config = config.inventory
        engine = ResourceDiscoveryEngine()
        cache = get_resource_inventory_cache()

        subscriptions = await engine.discover_all_subscriptions()

        total_created = 0
        total_modified = 0
        total_deleted = 0

        for sub in subscriptions:
            # Handle both dict (expected) and string (backward compatibility)
            if isinstance(sub, dict):
                sub_id = sub["subscription_id"]
            else:
                sub_id = str(sub)
            
            try:
                changes = await engine.incremental_discovery(
                    subscription_id=sub_id,
                    last_scan_time=_last_scan_time,
                    cached_resource_ids=_cached_resource_ids,
                )

                created = changes.get("created", [])
                modified = changes.get("modified", [])
                deleted = changes.get("deleted", [])

                total_created += len(created)
                total_modified += len(modified)
                total_deleted += len(deleted)

                # Cache created/modified resources grouped by type
                changed_resources = created + modified
                if changed_resources:
                    by_type: Dict[str, list] = {}
                    for r in changed_resources:
                        rtype = r.get("resource_type", "unknown")
                        by_type.setdefault(rtype, []).append(r)

                    for rtype, typed_resources in by_type.items():
                        # Merge with existing cache rather than replacing
                        existing = await cache.get(sub_id, rtype) or []
                        existing_by_id = {
                            r.get("resource_id", r.get("id", "")): r
                            for r in existing
                        }
                        for r in typed_resources:
                            rid = r.get("resource_id", "")
                            existing_by_id[rid] = r
                        await cache.set(sub_id, rtype, list(existing_by_id.values()))

                # Handle deletions — invalidate cache entries for deleted resources
                if deleted:
                    deleted_by_type: Dict[str, int] = {}
                    for d in deleted:
                        rid = d.get("resource_id", "")
                        # Remove from tracked IDs
                        _cached_resource_ids.discard(rid)
                    # Invalidate full subscription cache to force re-fetch
                    await cache.invalidate(sub_id)

                if created or modified or deleted:
                    logger.info(
                        "Incremental scan: subscription %s — +%d ~%d -%d",
                        sub_id, len(created), len(modified), len(deleted),
                    )

            except Exception as exc:
                if inv_config.skip_failed_subscriptions:
                    logger.warning(
                        "Incremental scan: skipping subscription %s: %s",
                        sub_id, exc,
                    )
                else:
                    raise

        _last_scan_time = datetime.now(timezone.utc).isoformat()

        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["last_changes"] = {
            "created": total_created,
            "modified": total_modified,
            "deleted": total_deleted,
        }

        logger.info(
            "Incremental scan complete: +%d ~%d -%d in %.1fs",
            total_created, total_modified, total_deleted, elapsed,
        )

    except Exception as exc:
        elapsed = time.monotonic() - start
        stats["last_duration_seconds"] = round(elapsed, 2)
        stats["total_runs"] += 1
        stats["total_errors"] += 1
        stats["last_error"] = f"{type(exc).__name__}: {exc}"
        logger.error("Incremental scan failed after %.1fs: %s", elapsed, exc)


# ---------------------------------------------------------------------------
# InventoryScheduler
# ---------------------------------------------------------------------------

class InventoryScheduler:
    """Manages APScheduler lifecycle for inventory refresh jobs.

    Reads cron/interval schedules from ``config.inventory`` and registers
    ``full_refresh_job`` and ``incremental_refresh_job``.

    Usage::

        scheduler = InventoryScheduler()
        await scheduler.start()    # call in FastAPI startup
        await scheduler.stop()     # call in FastAPI shutdown
    """

    FULL_SCAN_JOB_ID = "inventory_full_scan"
    INCREMENTAL_SCAN_JOB_ID = "inventory_incremental_scan"

    def __init__(self) -> None:
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the scheduler with configured jobs."""
        inv_config = config.inventory

        if not inv_config.enable_inventory:
            logger.info("InventoryScheduler: inventory disabled — not starting")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "InventoryScheduler: apscheduler not installed — "
                "periodic refresh disabled (pip install apscheduler)"
            )
            return

        if self._running:
            logger.warning("InventoryScheduler: already running")
            return

        self._scheduler = AsyncIOScheduler(timezone="UTC")

        # -- Full scan job (cron) -------------------------------------------
        cron_expr = inv_config.full_scan_schedule_cron
        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")
            self._scheduler.add_job(
                full_refresh_job,
                trigger=trigger,
                id=self.FULL_SCAN_JOB_ID,
                name="Inventory Full Scan",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info("Scheduled full scan: cron='%s'", cron_expr)
        except Exception as exc:
            logger.error("Failed to schedule full scan with cron '%s': %s", cron_expr, exc)

        # -- Incremental scan job (interval) --------------------------------
        interval_min = inv_config.incremental_scan_interval_minutes
        try:
            self._scheduler.add_job(
                incremental_refresh_job,
                trigger=IntervalTrigger(minutes=interval_min),
                id=self.INCREMENTAL_SCAN_JOB_ID,
                name="Inventory Incremental Scan",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info("Scheduled incremental scan: every %d minutes", interval_min)
        except Exception as exc:
            logger.error("Failed to schedule incremental scan: %s", exc)

        self._scheduler.start()
        self._running = True

        # Update next_run times
        self._update_next_run_times()

        logger.info("InventoryScheduler started (full=%s, incremental=%dm)", cron_expr, interval_min)

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("InventoryScheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return scheduler status and job statistics for monitoring."""
        self._update_next_run_times()
        return {
            "running": self._running,
            "apscheduler_available": APSCHEDULER_AVAILABLE,
            "inventory_enabled": config.inventory.enable_inventory,
            "full_scan_cron": config.inventory.full_scan_schedule_cron,
            "incremental_interval_minutes": config.inventory.incremental_scan_interval_minutes,
            "jobs": get_scheduler_stats(),
        }

    def _update_next_run_times(self) -> None:
        """Refresh next_run fields from the live scheduler."""
        if not self._scheduler or not self._running:
            return
        for job_id, stats_key in [
            (self.FULL_SCAN_JOB_ID, "full_scan"),
            (self.INCREMENTAL_SCAN_JOB_ID, "incremental_scan"),
        ]:
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                _job_stats[stats_key]["next_run"] = job.next_run_time.isoformat()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler_instance: Optional[InventoryScheduler] = None


def get_inventory_scheduler() -> InventoryScheduler:
    """Get or create the InventoryScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = InventoryScheduler()
    return _scheduler_instance
