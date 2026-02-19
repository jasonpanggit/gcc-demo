"""
Health Check API Endpoints

This module provides health check and diagnostic endpoints for monitoring
and debugging the EOL Multi-Agent application.

Endpoints:
    GET /api/health/detailed - Detailed health with service status
    GET /api/status - Application status and statistics
    GET /api/test-logging - Logging test for Azure debugging
    GET /health - Fast health check for load balancers
    GET /health/inventory - Resource inventory discovery status

Usage:
    from api.health import router
    app.include_router(router)
"""
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter

from utils import config
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    with_timeout_and_stats,
    readonly_endpoint
)

# Create router for health endpoints
router = APIRouter(tags=["Health & Status"])


def _get_inventory_asst_available():
    """Lazy import to get inventory assistant availability from main module"""
    try:
        from main import INVENTORY_ASST_AVAILABLE
        return INVENTORY_ASST_AVAILABLE
    except Exception:
        return False


@router.get('/health')
@with_timeout_and_stats(
    agent_name="health_check",
    timeout_seconds=5,
    track_cache=False,
    auto_wrap_response=False
)
async def health_check() -> Dict[str, Any]:
    """
    Fast health check endpoint for load balancers and monitoring.
    
    This endpoint provides a quick health status for external monitoring systems,
    load balancers, and health probes. It's optimized for speed with a 5-second
    timeout and minimal processing.
    
    Returns:
        Dict containing:
            - status (str): Application health status ("ok")
            - timestamp (str): Current UTC timestamp in ISO format
            - version (str): Application version from config
            - inventory_asst_available (bool): Whether inventory assistant functionality is available
    
    Example Response:
        {
            "status": "ok",
            "timestamp": "2025-10-15T10:30:00.000Z",
            "version": "1.0.0",
            "inventory_asst_available": true
        }
    
    Note:
        This endpoint does NOT wrap response in StandardResponse format
        for maximum compatibility with monitoring tools.
    """
    return {
        "status": "ok", 
        "timestamp": datetime.utcnow().isoformat(),
        "version": config.app.version,
        "inventory_asst_available": _get_inventory_asst_available()
    }


@router.get("/api/health/detailed", response_model=StandardResponse)
@readonly_endpoint(agent_name="health_check", timeout_seconds=15)
async def detailed_health() -> Dict[str, Any]:
    """
    Detailed health check with comprehensive service status.
    
    Performs thorough validation of application configuration and checks
    the status of all services including:
    - Cosmos DB connectivity
    - Azure services configuration
    - Orchestrator availability
    - Agent initialization
    - Configuration validation
    
    This endpoint provides detailed diagnostics for troubleshooting and
    monitoring dashboards.
    
    Returns:
        StandardResponse with health status containing:
            - status (str): Overall health ("ok", "degraded", or "unhealthy")
            - timestamp (str): Check timestamp
            - services (Dict): Status of each service component
            - errors (List[str]): Any configuration or service errors
            - warnings (List[str]): Non-critical warnings
            - inventory_assistant (Dict): Inventory assistant functionality status
    
    Example Response:
        {
            "success": true,
            "data": {
                "status": "ok",
                "timestamp": "2025-10-15T10:30:00.000Z",
                "services": {
                    "cosmos_db": "available",
                    "azure_openai": "available",
                    "log_analytics": "available"
                },
                "errors": [],
                "warnings": [],
                "inventory_assistant": {
                    "available": false,
                    "status": "not_available",
                    "agents_count": 0
                }
            }
        }
    """
    validation = config.validate_config()
    
    # EOL interface uses only regular orchestrator (no chat)
    inventory_asst_status = "not_available"
    inventory_asst_agents_count = 0
    
    health_status = {
        "status": "ok" if validation["valid"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": validation["services"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "inventory_assistant": {
            "available": _get_inventory_asst_available(),
            "status": inventory_asst_status,
            "agents_count": inventory_asst_agents_count
        }
    }
    return health_status


@router.get("/api/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="api_status", timeout_seconds=5)
async def api_status() -> Dict[str, Any]:
    """
    Application status endpoint showing running state and version.

    Returns basic application status information including runtime state,
    version, and service message. This is a lightweight status check that
    provides quick confirmation the API is operational.

    Returns:
        StandardResponse with status data containing:
            - status (str): Runtime status ("running")
            - version (str): Application version
            - message (str): Service identifier
            - timestamp (str): Current UTC timestamp

    Example Response:
        {
            "success": true,
            "data": [{
                "status": "running",
                "version": "1.0.0",
                "message": "EOL Multi-Agent App",
                "timestamp": "2025-10-15T10:30:00.000Z"
            }],
            "count": 1
        }
    """
    status_data = {
        "status": "running",
        "version": config.app.version,
        "message": "EOL Multi-Agent App",
        "timestamp": datetime.utcnow().isoformat()
    }
    return status_data

@router.get('/health/inventory')
@with_timeout_and_stats(
    agent_name="inventory_health",
    timeout_seconds=5,
    track_cache=False,
    auto_wrap_response=False
)
async def inventory_health_check() -> Dict[str, Any]:
    """
    Resource inventory discovery health endpoint.

    Shows discovery status per subscription, last successful scan,
    error counts, and cache statistics. Used by monitoring dashboards
    and deployment health probes.

    Returns:
        Dict containing:
            - enabled (bool): Whether inventory discovery is enabled
            - status (str): Overall discovery status
            - subscriptions (Dict): Per-subscription discovery details
            - started_at (str): When discovery started
            - completed_at (str): When discovery finished
            - error_count (int): Number of failed subscriptions
            - cache_statistics (Dict): L1/L2 cache hit rates and counts
            - cosmos_status (Dict): Cosmos DB container readiness
            - config (Dict): Current inventory configuration summary

    Example Response:
        {
            "enabled": true,
            "status": "completed",
            "subscriptions": {
                "abc-123": {
                    "display_name": "Production",
                    "status": "completed",
                    "resource_count": 1247,
                    "error": null
                }
            },
            "error_count": 0,
            "cache_statistics": {
                "l1_entries": 42,
                "hits_l1": 150,
                "hit_rate_percent": 87.5
            },
            "config": {
                "enable_inventory": true,
                "startup_blocking": false
            }
        }

    Note:
        This endpoint does NOT wrap response in StandardResponse format
        for maximum compatibility with monitoring tools.
    """
    try:
        from main import _inventory_discovery_status
        status = dict(_inventory_discovery_status)
        # Deep copy subscriptions to avoid mutation
        if "subscriptions" in status:
            status["subscriptions"] = dict(status["subscriptions"])
    except Exception:
        status = {"enabled": False, "status": "unavailable"}

    # Add cache statistics if available
    try:
        from utils.resource_inventory_cache import get_resource_inventory_cache
        cache = get_resource_inventory_cache()
        status["cache_statistics"] = cache.get_statistics()
    except Exception:
        status["cache_statistics"] = {"error": "unavailable"}

    # Add Cosmos DB container status
    try:
        from utils.resource_inventory_cosmos import resource_inventory_setup
        status["cosmos_status"] = resource_inventory_setup.get_status()
    except Exception:
        status["cosmos_status"] = {"error": "unavailable"}

    # Add config summary
    status["config"] = {
        "enable_inventory": config.inventory.enable_inventory,
        "startup_blocking": config.inventory.startup_blocking,
        "default_l1_ttl": config.inventory.default_l1_ttl,
        "default_l2_ttl": config.inventory.default_l2_ttl,
        "full_scan_cron": config.inventory.full_scan_schedule_cron,
    }

    # Add scheduler status if available
    try:
        from utils.inventory_scheduler import get_inventory_scheduler
        scheduler = get_inventory_scheduler()
        status["scheduler"] = {
            "running": scheduler.running if hasattr(scheduler, 'running') else "unknown",
        }
    except Exception:
        status["scheduler"] = {"status": "unavailable"}

    return status