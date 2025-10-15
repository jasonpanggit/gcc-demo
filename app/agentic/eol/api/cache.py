"""
Cache Management API Endpoints

This module provides comprehensive cache management endpoints for the EOL
Multi-Agent application, including cache status, clearing, statistics, and
Cosmos DB cache operations.

Endpoints:
    GET  /api/cache/status - Get cache status across all agents
    POST /api/cache/clear - Clear inventory caches
    POST /api/cache/purge - Purge specific cache entries
    GET  /api/cache/stats/* - Various cache statistics endpoints
    GET  /api/cache/cosmos/* - Cosmos DB cache operations
    POST /api/cache-eol-result - Manually cache EOL results
    GET  /cache - Cache management UI page
    GET  /agent-cache-details - Agent cache details page

Note: This module extracts 17+ cache-related endpoints from main.py
"""
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from utils import get_logger
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    with_timeout_and_stats,
    write_endpoint,
    readonly_endpoint
)
from utils.cache_stats_manager import cache_stats_manager

# Initialize logger
logger = get_logger(__name__)

# Create router for cache endpoints
router = APIRouter(tags=["Cache Management"])

# Note: This module will be populated with cache endpoints from main.py
# Keeping this structure for now to establish the pattern

# Placeholder for inventory context cache (will be imported from main module state)
_inventory_context_cache = {
    "data": None,
    "timestamp": None,
    "ttl": 3600  # 1 hour
}


@router.get("/api/cache/status", response_model=StandardResponse)
@with_timeout_and_stats(agent_name="cache_status", timeout_seconds=20, track_cache=False, auto_wrap_response=False)
async def get_cache_status():
    """
    Get comprehensive cache status across all agents.
    
    Retrieves detailed cache status including:
    - Agent-level cache information
    - Inventory context cache stats
    - Enhanced performance metrics
    - Cache hit rates and response times
    
    This endpoint consolidates cache information from multiple sources:
    - EOL orchestrator agent caches
    - Inventory context cache
    - Cache statistics manager
    
    Returns:
        StandardResponse containing:
            - agents_with_cache: List of agents with cache data
            - inventory_context_cache: Inventory cache statistics
            - enhanced_stats: Performance metrics and statistics
            - cache_summary: Overall cache health
    
    Example Response:
        {
            "success": true,
            "data": [{
                "agents_with_cache": [
                    {
                        "name": "microsoft_agent",
                        "cache_count": 45,
                        "usage_count": 230,
                        "cache_hit_rate": 0.85,
                        "avg_response_time_ms": 120
                    }
                ],
                "inventory_context_cache": {
                    "cached": true,
                    "timestamp": "2025-10-15T10:30:00Z",
                    "ttl_seconds": 3600,
                    "items_count": 150
                }
            }]
        }
    """
    # Import here to avoid circular dependency
    from main import get_eol_orchestrator, _inventory_context_cache
    
    # Get basic cache status from orchestrator
    cache_status = await get_eol_orchestrator().get_cache_status()
    
    # Add inventory context cache stats
    inventory_stats = {
        "cached": _inventory_context_cache["data"] is not None,
        "timestamp": _inventory_context_cache["timestamp"].isoformat() if _inventory_context_cache["timestamp"] else None,
        "ttl_seconds": _inventory_context_cache["ttl"],
        "items_count": len(_inventory_context_cache["data"]) if _inventory_context_cache["data"] else 0,
        "size_kb": len(str(_inventory_context_cache["data"])) // 1024 if _inventory_context_cache["data"] else 0
    }
    
    # Add enhanced statistics from cache_stats_manager
    try:
        enhanced_stats = cache_stats_manager.get_all_statistics()
        
        # Merge enhanced agent stats with existing agent data
        if "agents_with_cache" in cache_status and "agent_stats" in enhanced_stats:
            for agent_data in cache_status["agents_with_cache"]:
                agent_name = agent_data.get("name") or agent_data.get("agent")
                if agent_name in enhanced_stats["agent_stats"]["agents"]:
                    enhanced_agent_data = enhanced_stats["agent_stats"]["agents"][agent_name]
                    agent_data.update({
                        "usage_count": enhanced_agent_data["request_count"],
                        "cache_hit_rate": enhanced_agent_data["cache_hit_rate"],
                        "avg_response_time_ms": enhanced_agent_data["avg_response_time_ms"],
                        "error_count": enhanced_agent_data["error_count"],
                        "last_used": enhanced_agent_data["last_request_time"]
                    })
        
        # Add performance summary to cache status
        cache_status["enhanced_stats"] = enhanced_stats
        
    except Exception as e:
        logger.warning(f"⚠️ Could not load enhanced cache statistics: {e}")
        cache_status["enhanced_stats"] = {"error": str(e)}
    
    cache_status["inventory_context_cache"] = inventory_stats
    
    # Manually wrap complex dict structure in StandardResponse format
    return StandardResponse.success_response(
        data=[cache_status],
        metadata={"agent": "cache_status", "complex_structure": True}
    )


@router.post("/api/cache/clear", response_model=StandardResponse)
@write_endpoint(agent_name="cache_clear", timeout_seconds=30)
async def clear_cache():
    """
    Clear all inventory caches (software and OS).
    
    This endpoint clears both in-memory and Cosmos DB caches for inventory data.
    EOL agent caches are managed separately via /api/cache/purge endpoint.
    
    The clear operation:
    - Clears software inventory cache
    - Clears OS inventory cache
    - Resets inventory context cache
    - Does NOT affect EOL agent caches
    
    Returns:
        StandardResponse with clear operation results
    
    Example Response:
        {
            "success": true,
            "message": "Inventory caches cleared successfully",
            "data": {
                "software_cache_cleared": true,
                "os_cache_cleared": true,
                "timestamp": "2025-10-15T10:30:00Z"
            }
        }
    
    Note:
        Use /api/cache/purge to clear specific EOL agent caches
    """
    from utils.inventory_cache import inventory_cache
    from main import _inventory_context_cache
    
    try:
        # Clear software and OS inventory caches
        await inventory_cache.clear_cache(cache_type="software")
        await inventory_cache.clear_cache(cache_type="os")
        
        # Clear inventory context cache
        _inventory_context_cache["data"] = None
        _inventory_context_cache["timestamp"] = None
        
        return {
            "success": True,
            "message": "Inventory caches cleared successfully",
            "data": {
                "software_cache_cleared": True,
                "os_cache_cleared": True,
                "context_cache_cleared": True,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"❌ Error clearing caches: {e}")
        return StandardResponse.error_response(
            error_message=f"Failed to clear caches: {str(e)}",
            details={"error_type": type(e).__name__}
        )


@router.post("/api/cache/purge", response_model=StandardResponse)
@write_endpoint(agent_name="cache_purge", timeout_seconds=30)
async def purge_cache(agent_type: Optional[str] = None, software_name: Optional[str] = None, version: Optional[str] = None):
    """
    Purge web scraping cache for specific agent or all agents.
    
    This endpoint allows selective clearing of EOL agent web scraping caches.
    Unlike /api/cache/clear which clears inventory caches, this purges
    cached web scraping results from EOL specialist agents.
    
    Args:
        agent_type: Type of agent to purge cache for (e.g., "microsoft", "endoflife", "python")
        software_name: Specific software name to purge from cache
        version: Specific version to purge from cache
    
    Returns:
        StandardResponse with purge results including number of items removed.
    
    Example Response:
        {
            "success": true,
            "data": {
                "purged_count": 15,
                "agent_type": "microsoft",
                "software_name": "Windows Server",
                "timestamp": "2025-10-15T10:30:00Z"
            }
        }
    
    Usage Examples:
        - Purge all caches: POST /api/cache/purge
        - Purge Microsoft agent: POST /api/cache/purge?agent_type=microsoft
        - Purge specific software: POST /api/cache/purge?software_name=Windows Server 2016
    """
    from main import get_eol_orchestrator
    
    result = await get_eol_orchestrator().purge_web_scraping_cache(agent_type, software_name, version)
    logger.info(f"Cache purged: agent_type={agent_type}, software={software_name}, version={version}, result={result}")
    return result


# Additional cache endpoints will be added here as we extract them from main.py
# This establishes the pattern and structure for the cache API module
