"""Shared CVE sync operations used by API handlers and the scheduler."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from utils.config import config
    from utils.logging_config import get_logger
except ImportError:
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.logging_config import get_logger

try:
    from utils.repositories.cve_repository import CVERepository
except ImportError:
    from app.agentic.eol.utils.repositories.cve_repository import CVERepository

logger = get_logger(__name__)


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
    os_summary_repo: Optional[Any] = None,
) -> Dict[str, Any]:
    """Sync CVEs for inventory-discovered operating systems.

    Default behavior is new-OS-only. Force-resync is kept for non-UI callers.

    Args:
        os_summary_repo: Optional repository for persisting OS sync summaries
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
        os_summary_repo=os_summary_repo,
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


async def sync_msrc_kb_edges(
    vendor_client,
    kb_cve_repo,
    n_months: int = 3,
    *,
    pool=None,
) -> int:
    """Sync recent N months of MSRC KB-CVE edges into PostgreSQL kb_cve_edges table.

    Phase 8: Rewired from legacy bulk_upsert() to
    CVERepository.upsert_kb_cve_edges().
    Called after run_delta_sync() completes. Non-blocking -- errors are caught
    and logged.

    Args:
        vendor_client: MSRC vendor feed client.
        kb_cve_repo: PostgreSQL-backed repository.
        n_months: Number of months of MSRC data to fetch.
        pool: asyncpg.Pool for PostgreSQL writes. Uses CVERepository when set.

    Returns count of edges upserted.
    """
    try:
        month_map = await vendor_client.fetch_recent_months_kb_cve_map(n_months)
        edges: List[Dict[str, Any]] = []
        for kb_number, cve_ids in month_map.items():
            # Map kb_id to kb_number for PG schema compatibility (I-01 resolution)
            kb_with_prefix = (
                f"KB{kb_number}"
                if not kb_number.upper().startswith("KB")
                else kb_number
            )
            for cve_id in cve_ids:
                edges.append({
                    "kb_number": kb_with_prefix,
                    "cve_id": cve_id.upper(),
                    "source": "microsoft",
                    "severity": None,
                    "title": None,
                    "fixed_version": None,
                    "last_seen": datetime.now(timezone.utc),
                })

        if not edges:
            return 0

        # Phase 8: Prefer PostgreSQL via CVERepository when pool is available
        if pool is not None:
            cve_repo = CVERepository(pool)
            count = await cve_repo.upsert_kb_cve_edges(edges)
            logger.info(
                "MSRC SUG sync: upserted %d KB-CVE edges to PostgreSQL (%d months)",
                count,
                n_months,
            )

            # Refresh bootstrap MVs after successful sync
            result = await cve_repo.refresh_materialized_views()
            logger.info("MV refresh after MSRC sync: %s", result)

            return count

        # PostgreSQL repository fallback path
        try:
            from models.cve_models import PatchAdvisoryEdge
        except ImportError:
            from app.agentic.eol.models.cve_models import PatchAdvisoryEdge

        legacy_edges: List[Any] = []
        for edge in edges:
            legacy_edges.append(
                PatchAdvisoryEdge(
                    id=f"microsoft:{edge['kb_number']}:{edge['cve_id']}",
                    kb_number=edge["kb_number"],
                    advisory_id=edge["kb_number"],
                    cve_id=edge["cve_id"],
                    source="microsoft",
                    os_family="windows",
                )
            )
        count = await kb_cve_repo.bulk_upsert(legacy_edges)
        logger.info(
            "MSRC SUG sync (legacy): upserted %d KB-CVE edges (%d months)",
            count,
            n_months,
        )
        return count

    except Exception as e:
        logger.warning("MSRC SUG KB-edge sync failed (non-fatal): %s", e)
        return 0


async def sync_kb_edges_for_kbs(
    kb_numbers: List[str],
    vendor_client,
    *,
    pool=None,
    batch_size: int = 10,
) -> int:
    """Fetch CVE mappings from MSRC for a specific list of KB numbers and upsert into kb_cve_edges.

    Called after ARG or LAW KB discovery to immediately populate edges for
    newly discovered KB numbers without waiting for the scheduled full sync.

    Args:
        kb_numbers: List of KB numbers (with or without 'KB' prefix — normalised internally).
        vendor_client: VendorFeedClient instance.
        pool: asyncpg connection pool. If None, returns 0 immediately (safe no-op).
        batch_size: Number of concurrent MSRC calls per gather batch (default 10).

    Returns:
        Total number of CVE edges upserted across all KB numbers.
    """
    if pool is None:
        logger.warning("sync_kb_edges_for_kbs: pool is None — skipping edge sync")
        return 0

    # Normalise and deduplicate — uppercase the whole token so "kb5052006" → "KB5052006"
    normalised = list({
        kb.upper() if kb.upper().startswith("KB") else f"KB{kb.upper()}"
        for kb in kb_numbers
        if kb
    })
    if not normalised:
        return 0

    logger.info(f"sync_kb_edges_for_kbs: syncing {len(normalised)} KB numbers")

    all_edges: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)  # timezone-aware; matches existing sync_msrc_kb_edges convention

    # Process in batches with per-KB error isolation
    for i in range(0, len(normalised), batch_size):
        batch = normalised[i:i + batch_size]
        results = await asyncio.gather(
            *[vendor_client.fetch_microsoft_cves_for_kb_sug(kb) for kb in batch],
            return_exceptions=True,
        )
        for kb, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.warning(f"sync_kb_edges_for_kbs: MSRC lookup failed for {kb}: {result}")
                continue
            for cve_id in result:
                all_edges.append({
                    "kb_number": kb,
                    "cve_id": cve_id.upper(),
                    "source": "microsoft",
                    "severity": None,
                    "title": None,
                    "fixed_version": None,
                    "last_seen": now,
                })

    if not all_edges:
        return 0

    try:
        cve_repo = CVERepository(pool)
        count = await cve_repo.upsert_kb_cve_edges(all_edges)
        logger.info(f"sync_kb_edges_for_kbs: upserted {count} edges")
        return count
    except Exception as e:
        logger.error(f"sync_kb_edges_for_kbs: failed to upsert edges: {e}")
        return 0