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

# Global flag for chat availability (EOL interface doesn't use chat)
CHAT_AVAILABLE = False


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
            - autogen_available (bool): Whether chat functionality is available
    
    Example Response:
        {
            "status": "ok",
            "timestamp": "2025-10-15T10:30:00.000Z",
            "version": "1.0.0",
            "autogen_available": false
        }
    
    Note:
        This endpoint does NOT wrap response in StandardResponse format
        for maximum compatibility with monitoring tools.
    """
    return {
        "status": "ok", 
        "timestamp": datetime.utcnow().isoformat(),
        "version": config.app.version,
        "autogen_available": CHAT_AVAILABLE
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
            - autogen (Dict): Chat functionality status
    
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
                "autogen": {
                    "available": false,
                    "status": "not_available",
                    "agents_count": 0
                }
            }
        }
    """
    validation = config.validate_config()
    
    # EOL interface uses only regular orchestrator (no chat)
    autogen_status = "not_available"
    autogen_agents_count = 0
    
    health_status = {
        "status": "ok" if validation["valid"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": validation["services"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "autogen": {
            "available": CHAT_AVAILABLE,
            "status": autogen_status,
            "agents_count": autogen_agents_count
        }
    }
    return health_status
