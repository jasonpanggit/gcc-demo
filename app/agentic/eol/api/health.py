"""
Health Check API Endpoints

This module provides health check and diagnostic endpoints for monitoring
and debugging the EOL Multi-Agent application.

Endpoints:
    GET /health - Fast health check for load balancers
    GET /api/health/detailed - Detailed health with service status
    GET /api/test-logging - Logging test for Azure debugging
    GET /api/status - Application status and statistics

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
