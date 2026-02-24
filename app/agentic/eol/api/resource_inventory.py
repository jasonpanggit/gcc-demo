"""
Resource Inventory API Router

FastAPI router for managing Azure resource inventory:
  - Trigger full / incremental discovery refreshes
  - Query cached resources with filters and pagination
  - View discovered subscriptions
  - Cache statistics and health checks
  - Monitoring metrics endpoint for dashboards

All endpoints are async and follow the project's one-router-per-domain pattern.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

try:
    from utils.logger import get_logger
    from utils.config import config
    from utils.helpers import create_error_response
    from utils.resource_inventory_client import get_resource_inventory_client
    from utils.resource_inventory_cache import get_resource_inventory_cache
    from utils.resource_discovery_engine import ResourceDiscoveryEngine
    from utils.inventory_metrics import get_inventory_metrics
except ImportError:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.helpers import create_error_response
    from app.agentic.eol.utils.resource_inventory_client import get_resource_inventory_client
    from app.agentic.eol.utils.resource_inventory_cache import get_resource_inventory_cache
    from app.agentic.eol.utils.resource_discovery_engine import ResourceDiscoveryEngine
    from app.agentic.eol.utils.inventory_metrics import get_inventory_metrics

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/resource-inventory",
    tags=["resource-inventory"],
)

# Health-check lives at a different prefix so it can be mounted alongside /healthz
health_router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    """Body for manual refresh trigger."""
    subscription_id: Optional[str] = Field(
        None, description="Target subscription (defaults to config)",
    )
    resource_types: Optional[List[str]] = Field(
        None, description="Limit to specific resource types",
    )
    mode: str = Field(
        "full", description="Discovery mode: 'full' or 'incremental'",
    )


class StandardResponse(BaseModel):
    """Uniform API response envelope."""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_subscription() -> str:
    sub = getattr(config.azure, "subscription_id", None)
    return sub or os.getenv("AZURE_SUBSCRIPTION_ID", "")


def _paginate(items: List[Any], offset: int, limit: int) -> Dict[str, Any]:
    """Return a slice of *items* plus pagination metadata."""
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


# =====================================================================
# Endpoints
# =====================================================================

@router.post("/refresh", response_model=StandardResponse)
async def refresh_inventory(body: RefreshRequest):
    """Trigger a manual full or incremental resource discovery.

    - **full** mode discovers all resources in the subscription via Resource Graph.
    - **incremental** mode detects changes since the last scan (created/modified/deleted).
    """
    start = time.time()
    metrics = get_inventory_metrics()
    sub = body.subscription_id or _default_subscription()

    if not sub:
        return StandardResponse(
            success=False,
            error="No subscription_id provided and none configured",
        )

    try:
        engine = ResourceDiscoveryEngine()
        client = get_resource_inventory_client()
        cache = get_resource_inventory_cache()

        async with metrics.track_discovery_async(sub):
            if body.mode == "incremental":
                result = await engine.full_resource_discovery(sub, resource_types=body.resource_types)
                by_type: Dict[str, List[Dict[str, Any]]] = {}
                for r in result:
                    rtype = r.get("resource_type", "unknown")
                    by_type.setdefault(rtype, []).append(r)
                for rtype, resources in by_type.items():
                    await cache.set(sub, rtype, resources)

                # Record discovered resource counts in metrics
                type_counts = {k: len(v) for k, v in by_type.items()}
                metrics.record_discovery_resources(sub, len(result), type_counts)

                duration = (time.time() - start) * 1000
                return StandardResponse(
                    data={
                        "mode": "incremental",
                        "subscription_id": sub,
                        "resources_discovered": len(result),
                        "resource_types": len(by_type),
                    },
                    message=f"Incremental refresh completed: {len(result)} resources",
                    duration_ms=round(duration, 1),
                )
            else:
                # Full discovery
                result = await engine.full_resource_discovery(sub, resource_types=body.resource_types)
                by_type = {}
                for r in result:
                    rtype = r.get("resource_type", "unknown")
                    by_type.setdefault(rtype, []).append(r)
                for rtype, resources in by_type.items():
                    await cache.set(sub, rtype, resources)

                # Record discovered resource counts in metrics
                type_counts = {k: len(v) for k, v in by_type.items()}
                metrics.record_discovery_resources(sub, len(result), type_counts)

                duration = (time.time() - start) * 1000
                return StandardResponse(
                    data={
                        "mode": "full",
                        "subscription_id": sub,
                        "resources_discovered": len(result),
                        "resource_types": len(by_type),
                        "type_breakdown": type_counts,
                    },
                    message=f"Full refresh completed: {len(result)} resources across {len(by_type)} types",
                    duration_ms=round(duration, 1),
                )

    except Exception as exc:
        logger.error("Refresh failed for %s: %s", sub, exc)
        duration = (time.time() - start) * 1000
        return StandardResponse(
            success=False,
            error=str(exc),
            message="Resource discovery refresh failed",
            duration_ms=round(duration, 1),
        )


@router.get("/stats", response_model=StandardResponse)
async def get_cache_stats():
    """Return cache statistics: hit/miss rates, entry counts, TTL config."""
    start = time.time()
    try:
        cache = get_resource_inventory_cache()
        client = get_resource_inventory_client()

        stats = client.get_statistics()
        duration = (time.time() - start) * 1000

        return StandardResponse(
            data=stats,
            message="Cache statistics retrieved",
            duration_ms=round(duration, 1),
        )
    except Exception as exc:
        logger.error("Failed to retrieve cache stats: %s", exc)
        return StandardResponse(
            success=False,
            error=str(exc),
        )


@router.get("/resources", response_model=StandardResponse)
async def query_resources(
    subscription_id: Optional[str] = Query(None, description="Target subscription"),
    resource_type: Optional[str] = Query(None, description="Azure resource type (e.g. Microsoft.Compute/virtualMachines)"),
    resource_group: Optional[str] = Query(None, description="Filter by resource group"),
    location: Optional[str] = Query(None, description="Filter by Azure region"),
    name: Optional[str] = Query(None, description="Filter by resource name (substring)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Page size (max 500)"),
    refresh: bool = Query(False, description="Force live discovery if cache is empty"),
):
    """Query cached resources with filters and pagination.

    Returns paginated results with total count and type breakdown.
    """
    start = time.time()
    sub = subscription_id or _default_subscription()

    if not sub:
        return StandardResponse(
            success=False,
            error="No subscription_id provided and none configured",
        )

    if not resource_type:
        return StandardResponse(
            success=False,
            error="resource_type query parameter is required",
        )

    try:
        client = get_resource_inventory_client()
        metrics = get_inventory_metrics()

        # Build filter dict from query params
        filters: Dict[str, Any] = {}
        if resource_group:
            filters["resource_group"] = resource_group
        if location:
            filters["location"] = location
        if name:
            filters["name"] = name

        async with metrics.track_query_async("get_resources"):
            resources = await client.get_resources(
                resource_type=resource_type,
                subscription_id=sub,
                filters=filters or None,
                refresh=refresh,
            )

        duration = (time.time() - start) * 1000
        paginated = _paginate(resources, offset, limit)

        return StandardResponse(
            data=paginated,
            message=f"Found {paginated['total']} resources of type {resource_type}",
            duration_ms=round(duration, 1),
        )

    except Exception as exc:
        logger.error("Resource query failed: %s", exc)
        duration = (time.time() - start) * 1000
        return StandardResponse(
            success=False,
            error=str(exc),
            duration_ms=round(duration, 1),
        )


@router.get("/subscriptions", response_model=StandardResponse)
async def list_subscriptions():
    """List all Azure subscriptions accessible to the current credential."""
    start = time.time()
    metrics = get_inventory_metrics()
    try:
        engine = ResourceDiscoveryEngine()
        async with metrics.track_query_async("discover_subscriptions"):
            subs = await engine.discover_all_subscriptions()
        duration = (time.time() - start) * 1000

        return StandardResponse(
            data={
                "subscriptions": subs,
                "count": len(subs),
            },
            message=f"Discovered {len(subs)} subscriptions",
            duration_ms=round(duration, 1),
        )

    except Exception as exc:
        logger.error("Subscription discovery failed: %s", exc)
        duration = (time.time() - start) * 1000
        return StandardResponse(
            success=False,
            error=str(exc),
            message="Failed to discover subscriptions",
            duration_ms=round(duration, 1),
        )


# ---------------------------------------------------------------------------
# Monitoring Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=StandardResponse)
async def get_inventory_metrics_endpoint(
    detail: bool = Query(False, description="Return full dashboard metrics (default: summary)"),
):
    """Return monitoring metrics for the resource inventory system.

    Provides cache hit rates, discovery stats, query performance, and error counts.
    Use ``?detail=true`` for the full dashboard-ready payload.
    """
    start = time.time()
    try:
        metrics = get_inventory_metrics()

        if detail:
            data = metrics.get_dashboard_metrics()
        else:
            data = metrics.get_summary_metrics()

        duration = (time.time() - start) * 1000
        return StandardResponse(
            data=data,
            message="Inventory metrics retrieved",
            duration_ms=round(duration, 1),
        )
    except Exception as exc:
        logger.error("Failed to retrieve inventory metrics: %s", exc)
        return StandardResponse(
            success=False,
            error=str(exc),
            message="Failed to retrieve inventory metrics",
        )


@router.post("/metrics/reset", response_model=StandardResponse)
async def reset_inventory_metrics_endpoint():
    """Reset all inventory monitoring metrics counters.

    Useful for testing or after a known-good deployment.
    """
    try:
        metrics = get_inventory_metrics()
        metrics.reset()
        return StandardResponse(
            message="Inventory metrics reset successfully",
        )
    except Exception as exc:
        logger.error("Failed to reset inventory metrics: %s", exc)
        return StandardResponse(
            success=False,
            error=str(exc),
        )


@router.get("/status", response_model=StandardResponse)
async def get_inventory_status():
    """Get the status of the resource inventory system.

    Returns discovery status, cache statistics, and system health.
    Also available at /healthz/inventory for health checks.
    """
    start = time.time()
    
    try:
        # Import discovery status from main
        try:
            from main import get_inventory_discovery_status
            discovery_status = get_inventory_discovery_status()
        except ImportError:
            from app.agentic.eol.main import get_inventory_discovery_status
            discovery_status = get_inventory_discovery_status()
        
        cache = get_resource_inventory_cache()
        cache_stats = cache.get_statistics()
        
        engine_available = False
        try:
            engine = ResourceDiscoveryEngine()
            engine_available = True
        except Exception:
            pass
        
        inv_config = config.inventory
        duration = (time.time() - start) * 1000
        
        return StandardResponse(
            data={
                "enabled": inv_config.enable_inventory,
                "status": discovery_status.get("status", "unknown"),
                "engine_available": engine_available,
                "discovery": {
                    "status": discovery_status.get("status", "not_started"),
                    "started_at": discovery_status.get("started_at"),
                    "completed_at": discovery_status.get("completed_at"),
                    "subscriptions": discovery_status.get("subscriptions", {}),
                    "error_count": discovery_status.get("error_count", 0),
                },
                "cache": {
                    "l1_entries": cache_stats.get("l1_entries", 0),
                    "l1_valid": cache_stats.get("l1_valid_entries", 0),
                    "l2_ready": cache_stats.get("l2_ready", False),
                    "hit_rate_percent": cache_stats.get("hit_rate_percent", 0),
                },
                "config": {
                    "enable_inventory": inv_config.enable_inventory,
                    "default_l1_ttl": inv_config.default_l1_ttl,
                    "default_l2_ttl": inv_config.default_l2_ttl,
                    "full_scan_schedule": inv_config.full_scan_schedule_cron,
                    "incremental_interval_min": inv_config.incremental_scan_interval_minutes,
                },
            },
            message="Resource inventory status",
            duration_ms=round(duration, 1),
        )
    except Exception as exc:
        logger.error("Failed to retrieve inventory status: %s", exc)
        duration = (time.time() - start) * 1000
        return StandardResponse(
            success=False,
            error=str(exc),
            message="Failed to retrieve inventory status",
            duration_ms=round(duration, 1),
        )


# ---------------------------------------------------------------------------
# Health check (mounted separately at /healthz/inventory)
# ---------------------------------------------------------------------------

@health_router.get("/healthz/inventory", response_model=StandardResponse)
async def inventory_health():
    """Health check for the resource inventory subsystem.

    Reports discovery engine availability, cache status, and last refresh time.
    """
    start = time.time()

    cache = get_resource_inventory_cache()
    cache_stats = cache.get_statistics()

    engine_available = False
    try:
        engine = ResourceDiscoveryEngine()
        engine_available = True
    except Exception:
        pass

    inv_config = config.inventory
    duration = (time.time() - start) * 1000

    return StandardResponse(
        data={
            "status": "healthy" if engine_available else "degraded",
            "engine_available": engine_available,
            "cache": {
                "l1_entries": cache_stats.get("l1_entries", 0),
                "l1_valid": cache_stats.get("l1_valid_entries", 0),
                "l2_ready": cache_stats.get("l2_ready", False),
                "hit_rate_percent": cache_stats.get("hit_rate_percent", 0),
            },
            "config": {
                "enable_inventory": inv_config.enable_inventory,
                "default_l1_ttl": inv_config.default_l1_ttl,
                "default_l2_ttl": inv_config.default_l2_ttl,
                "full_scan_schedule": inv_config.full_scan_schedule_cron,
                "incremental_interval_min": inv_config.incremental_scan_interval_minutes,
            },
        },
        message="Resource inventory health check",
        duration_ms=round(duration, 1),
    )
