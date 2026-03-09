"""Shared CVE sync operations used by API handlers and the scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

try:
    from utils.config import config
except ImportError:
    from app.agentic.eol.utils.config import config


_last_delta_sync_time: Optional[datetime] = None


def get_last_delta_sync_time() -> Optional[datetime]:
    """Return the timestamp of the most recent successful delta-style sync."""
    return _last_delta_sync_time


def resolve_delta_since_date(lookback_days: Optional[int] = None) -> Tuple[datetime, bool]:
    """Resolve the lower-bound timestamp for a delta sync.

    Returns the timestamp and whether a fallback lookback window was used.
    """
    if _last_delta_sync_time is not None:
        return _last_delta_sync_time, False

    window_days = lookback_days if lookback_days is not None else config.cve_sync.sync_lookback_days
    return datetime.now(timezone.utc) - timedelta(days=window_days), True


def mark_delta_sync_completed(completed_at: Optional[datetime] = None) -> datetime:
    """Persist the timestamp of the most recent successful delta sync."""
    global _last_delta_sync_time
    _last_delta_sync_time = completed_at or datetime.now(timezone.utc)
    return _last_delta_sync_time


async def run_inventory_bootstrap_sync(
    *,
    cve_service: Any,
    cve_scanner: Any,
    eol_orchestrator: Any,
    force_resync: bool = False,
    limit_per_os: Optional[int] = None,
) -> Dict[str, Any]:
    """Sync CVEs for inventory-discovered operating systems.

    Default behavior is new-OS-only. Force-resync is kept for non-UI callers.
    """
    try:
        from utils.cve_inventory_sync import sync_inventory_os_cves
    except ImportError:
        from app.agentic.eol.utils.cve_inventory_sync import sync_inventory_os_cves

    return await sync_inventory_os_cves(
        cve_service=cve_service,
        cve_scanner=cve_scanner,
        eol_orchestrator=eol_orchestrator,
        limit_per_os=limit_per_os,
        force_resync=force_resync,
    )


async def run_delta_sync(
    *,
    cve_service: Any,
    limit: Optional[int] = None,
    lookback_days: Optional[int] = None,
    since_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run a delta sync and advance the shared delta-sync watermark."""
    effective_since_date = since_date
    used_fallback_window = False
    if effective_since_date is None:
        effective_since_date, used_fallback_window = resolve_delta_since_date(lookback_days)

    synced_count = await cve_service.sync_recent_cves(
        since_date=effective_since_date,
        limit=limit if limit is not None else config.cve_sync.max_cves_per_sync,
    )
    completed_at = mark_delta_sync_completed()

    return {
        "cve_count": synced_count,
        "since_date": effective_since_date,
        "completed_at": completed_at,
        "used_fallback_window": used_fallback_window,
    }