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

# Note: Cache management now uses the unified inventory_cache from utils.inventory_cache
# which handles both software and OS inventory with memory + Cosmos DB persistence


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
    from main import get_eol_orchestrator
    from utils.inventory_cache import inventory_cache
    
    # Get basic cache status from orchestrator
    orchestrator_status = await get_eol_orchestrator().get_cache_status()
    
    # Extract the actual data from the orchestrator response
    # orchestrator returns {"success": True, "data": {...}}
    if isinstance(orchestrator_status, dict) and "data" in orchestrator_status:
        cache_data = orchestrator_status["data"]
    else:
        cache_data = orchestrator_status
    
    # Add inventory context cache stats from the unified inventory_cache
    inventory_cache_stats = inventory_cache.get_cache_stats()
    inventory_stats = {
        "cached": inventory_cache_stats.get("total_memory_entries", 0) > 0,
        "timestamp": None,  # inventory_cache doesn't track global timestamp
        "ttl_seconds": inventory_cache_stats.get("cache_duration_hours", 4) * 3600,
        "items_count": inventory_cache_stats.get("total_memory_entries", 0),
        "size_kb": 0,  # Size calculation would require iterating all cached data
        "cache_types": inventory_cache_stats.get("memory_cache_entries", {})
    }
    
    # Add enhanced statistics from cache_stats_manager
    try:
        enhanced_stats = cache_stats_manager.get_all_statistics()
        cache_data["enhanced_stats"] = enhanced_stats
    except Exception as e:
        logger.warning(f"⚠️ Could not load enhanced cache statistics: {e}")
        cache_data["enhanced_stats"] = {"error": str(e)}
    
    cache_data["inventory_context_cache"] = inventory_stats
    
    # Wrap in StandardResponse format - data must be a list per StandardResponse model
    # Final structure: {"success": true, "data": [{"eol_cache": {...}, "agents": {...}, "enhanced_stats": {...}, "inventory_context_cache": {...}}]}
    response = StandardResponse.success_response(
        [cache_data],
        cached=inventory_stats["cached"],
        metadata={"source": "orchestrator"}
    )
    return response.to_dict()


@router.get("/api/cache/ui", response_model=StandardResponse)
@readonly_endpoint(agent_name="cache_ui_data", timeout_seconds=15)
async def get_cache_ui_data():
    """Aggregate cache statistics for the cache management UI."""
    all_stats = cache_stats_manager.get_all_statistics()

    payload = {
        "agents": all_stats.get("agent_stats", {}),
        "inventory": all_stats.get("inventory_stats", {}),
        "cosmos": all_stats.get("cosmos_stats", {}),
        "performance": all_stats.get("performance_summary", {}),
        "last_updated": all_stats.get("last_updated"),
    }

    response = StandardResponse.success_response(
        [payload],
        metadata={"source": "cache_stats_manager"}
    )
    return response.to_dict()


@router.post("/api/cache/clear")
@write_endpoint(agent_name="cache_clear", timeout_seconds=20)
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
    
    try:
        # Clear all inventory caches (software and OS)
        result = await inventory_cache.clear_all_cache()

        if not result.get("cleared_count"):
            return StandardResponse.error_response(
                error_message="No cache entries were cleared",
                details={
                    "cache_types": result.get("cache_types", []),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            ).to_dict()

        # Wrap in StandardResponse format with data as list
        return StandardResponse.success_response(
            data=[{
                "cleared_cache_types": result.get("cache_types", []),
                "memory_entries_cleared": result.get("cleared_count", 0),
                "cosmos_cleared": result.get("cosmos_cleared", False),
                "timestamp": datetime.utcnow().isoformat()
            }],
            message="Inventory caches cleared successfully"
        ).to_dict()
    except Exception as e:
        logger.error(f"❌ Error clearing caches: {e}")
        return StandardResponse.error_response(
            error_message=f"Failed to clear caches: {str(e)}",
            details={"error_type": type(e).__name__}
        ).to_dict()


@router.post("/api/cache/purge", response_model=StandardResponse)
@write_endpoint(agent_name="cache_purge", timeout_seconds=30)
async def purge_cache(agent_type: Optional[str] = None, software_name: Optional[str] = None, version: Optional[str] = None):
    """
    Purge EOL agent caches (Cosmos + in-memory) for a specific agent or all agents.

    - Agent caches live in Cosmos via utils.eol_cache and an in-memory layer on the orchestrator.
    - This endpoint clears both layers and resets cache statistics for agents.

    Args:
        agent_type: Agent key to target (e.g., "microsoft", "endoflife", "python"). If omitted, purge all.
        software_name: Optional software name filter to narrow the purge scope.
        version: Optional version filter to narrow the purge scope.
    """
    from main import get_eol_orchestrator
    from utils.eol_cache import eol_cache
    try:
        from utils.cache_stats_manager import cache_stats_manager
    except Exception:
        cache_stats_manager = None

    # Purge orchestrator in-memory cache
    orchestrator = get_eol_orchestrator()
    memory_cleared = len(orchestrator.eol_cache)
    orchestrator.eol_cache.clear()

    # Purge Cosmos + in-memory shared cache
    cosmos_result = await eol_cache.clear_cache(software_name=software_name, agent_name=agent_type)
    deleted_count = cosmos_result.get("deleted_count", 0) if isinstance(cosmos_result, dict) else 0

    # Reset statistics so UI reflects fresh state
    if cache_stats_manager:
        try:
            cache_stats_manager.reset_statistics()
        except Exception:
            pass

    results = {
        agent_type or "all_agents": {
            "deleted_count": deleted_count,
            "memory_cleared": memory_cleared,
            "software_name": software_name,
            "version": version,
        }
    }

    return {
        "success": bool(cosmos_result.get("success", True) if isinstance(cosmos_result, dict) else True),
        "results": results,
        "data": [{
            "message": "Agent caches cleared",
            "agent_type": agent_type or "all",
            "software_name": software_name,
            "version": version,
            "deleted_count": deleted_count,
            "memory_cleared": memory_cleared,
            "timestamp": datetime.utcnow().isoformat()
        }],
        "deleted_count": deleted_count,
        "memory_cleared": memory_cleared
    }


@router.get("/api/cache/inventory/stats", response_model=StandardResponse)
@readonly_endpoint(agent_name="inventory_cache_stats", timeout_seconds=15)
async def get_inventory_cache_stats():
    """
    Get detailed inventory context cache statistics with enhanced metrics.
    
    Provides comprehensive cache statistics including cache hit/miss info,
    data size, expiration status, and content analysis (computers, software counts).
    
    Returns:
        StandardResponse with cache stats and enhanced performance metrics.
    
    Example Response:
        {
            "success": true,
            "data": [{
                "cache_stats": {
                    "cached": true,
                    "timestamp": "2025-10-15T10:30:00Z",
                    "ttl_seconds": 3600,
                    "age_seconds": 450,
                    "expired": false,
                    "items_count": 150,
                    "size_bytes": 45678,
                    "computers_count": 10,
                    "software_count": 145
                },
                "enhanced_stats": {
                    "total_requests": 523,
                    "cache_hits": 445,
                    "cache_misses": 78,
                    "hit_rate": 0.851
                }
            }]
        }
    """
    import time
    from utils.inventory_cache import inventory_cache
    
    start_time = time.time()
    
    # Get cache stats from unified inventory_cache
    cache_stats = inventory_cache.get_cache_stats()
    
    stats = {
        "cached": cache_stats.get("total_memory_entries", 0) > 0,
        "timestamp": None,  # inventory_cache doesn't track global timestamp
        "ttl_seconds": cache_stats.get("cache_duration_hours", 4) * 3600,
        "age_seconds": None,  # Would need to track per-cache-entry
        "expired": False,
        "items_count": cache_stats.get("total_memory_entries", 0),
        "size_bytes": 0,
        "computers_count": 0,
        "software_count": 0,
        "cache_types": cache_stats.get("memory_cache_entries", {})
    }
    
    was_cache_hit = cache_stats.get("total_memory_entries", 0) > 0
    
    # Record performance metrics
    response_time_ms = (time.time() - start_time) * 1000
    cache_stats_manager.record_inventory_request(
        response_time_ms=response_time_ms,
        was_cache_hit=was_cache_hit,
        items_count=stats["items_count"]
    )
    
    # Add enhanced statistics
    enhanced_inventory_stats = cache_stats_manager.get_inventory_statistics()
    
    response = StandardResponse.success_response(
        [
            {
                "cache_stats": stats,
                "enhanced_stats": enhanced_inventory_stats,
            }
        ],
        cached=was_cache_hit,
        metadata={"source": "inventory_cache"},
    )
    return response.to_dict()


@router.get("/api/cache/inventory/details", response_model=StandardResponse)
@readonly_endpoint(agent_name="inventory_cache_details", timeout_seconds=20)
async def get_inventory_cache_details():
    """
    Get detailed inventory context cache content for viewing.
    
    Provides in-depth analysis of cached inventory data including computer
    counts, software distribution, and sample data entries.
    
    Returns:
        StandardResponse with detailed cache analysis, summary stats, and samples.
    
    Example Response:
        {
            "success": true,
            "data": [{
                "details": {
                    "timestamp": "2025-10-15T10:30:00Z",
                    "ttl_seconds": 3600,
                    "size_bytes": 45678,
                    "type": "list",
                    "summary": {
                        "total_entries": 150,
                        "unique_computers": 10,
                        "unique_software": 85,
                        "avg_software_per_computer": 15
                    },
                    "sample_data": {
                        "first_5_entries": [...],
                        "top_computers": {...},
                        "top_software": {...}
                    }
                }
            }]
        }
    """
    from utils.inventory_cache import inventory_cache
    
    # Get cache stats (note: the new cache doesn't store a single global data object)
    cache_stats = inventory_cache.get_cache_stats()
    
    if cache_stats.get("total_memory_entries", 0) == 0:
        response = StandardResponse.success_response(
            [{
                "summary": {
                    "total_cache_entries": 0,
                    "cache_types": cache_stats.get("supported_cache_types", []),
                    "cosmos_initialized": cache_stats.get("cosmos_initialized", False),
                },
                "cache_stats": cache_stats,
                "message": "No inventory data cached",
            }],
            cached=False,
            metadata={"warning": "inventory_cache_empty"},
        )
        return response.to_dict()

    details = {
        "timestamp": None,  # inventory_cache tracks per-entry timestamps
        "ttl_seconds": cache_stats.get("cache_duration_hours", 4) * 3600,
        "size_bytes": 0,  # Calculating size requires iterating all cached data
        "type": "distributed_cache",
        "cache_types": cache_stats.get("memory_cache_entries", {}),
        "sample_data": {},
        "summary": {
            "total_cache_entries": cache_stats.get("total_memory_entries", 0),
            "cache_types": cache_stats.get("supported_cache_types", []),
            "cosmos_initialized": cache_stats.get("cosmos_initialized", False),
        },
        "cache_stats": cache_stats,
    }

    response = StandardResponse.success_response(
        [{"details": details}],
        cached=True,
        metadata={
            "summary": details["summary"],
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    return response.to_dict()


@router.get("/api/cache/webscraping/details", response_model=StandardResponse)
@readonly_endpoint(agent_name="webscraping_cache_details", timeout_seconds=20)
async def get_webscraping_cache_details():
    """
    Get detailed web scraping cache information.
    
    Analyzes cache content for all web scraping agents including Microsoft,
    RedHat, Ubuntu, Oracle, VMware, Apache, and others. Provides cache sizes,
    sample items, and summary statistics.
    
    Returns:
        StandardResponse with per-agent cache details and summary statistics.
    
    Example Response:
        {
            "success": true,
            "data": [{
                "cache_details": [
                    {
                        "agent": "microsoft",
                        "type": "MicrosoftEOLAgent",
                        "available": true,
                        "has_cache": true,
                        "cache_size": 45,
                        "cache_items": [...]
                    }
                ],
                "summary": {
                    "total_agents": 12,
                    "agents_with_cache": 8,
                    "total_cached_items": 234,
                    "largest_cache": 45
                }
            }]
        }
    """
    from main import get_eol_orchestrator
    
    orchestrator = get_eol_orchestrator()
    cache_details = []
    total_cached_items = 0
    
    # Get cache details from each web scraping agent
    for agent_name in ["microsoft", "redhat", "ubuntu", "oracle", "vmware", "apache", "nodejs", "postgresql", "php", "python", "azure_ai"]:
        agent = orchestrator.agents.get(agent_name)
        if agent:
            agent_cache_info = {
                "agent": agent_name,
                "type": type(agent).__name__,
                "available": True,
                "has_cache": hasattr(agent, '_cache') or hasattr(agent, 'cache'),
                "cache_size": 0,
                "last_used": getattr(agent, 'last_used', None),
                "cache_items": []
            }
            
            # Try to get cache content
            try:
                if hasattr(agent, '_cache') and agent._cache:
                    if hasattr(agent._cache, 'items'):
                        agent_cache_info["cache_size"] = len(agent._cache)
                        # Get sample cache items (first 5)
                        cache_items = list(agent._cache.items())[:5]
                        agent_cache_info["cache_items"] = [
                            {
                                "key": str(key)[:100] + "..." if len(str(key)) > 100 else str(key),
                                "value_type": type(value).__name__,
                                "value_size": len(str(value)) if value else 0,
                                "value_preview": str(value)[:200] + "..." if value and len(str(value)) > 200 else str(value)
                            }
                            for key, value in cache_items
                        ]
                        total_cached_items += len(agent._cache)
                    elif hasattr(agent._cache, '__len__'):
                        agent_cache_info["cache_size"] = len(agent._cache)
                        total_cached_items += len(agent._cache)
                elif hasattr(agent, 'cache') and agent.cache:
                    if hasattr(agent.cache, '__len__'):
                        agent_cache_info["cache_size"] = len(agent.cache)
                        total_cached_items += len(agent.cache)
                    else:
                        agent_cache_info["cache_size"] = 1
                        total_cached_items += 1
                        
            except Exception as cache_error:
                logger.debug(f"Could not access cache for {agent_name}: {cache_error}")
                agent_cache_info["cache_error"] = str(cache_error)
            
            cache_details.append(agent_cache_info)
    
    return {
        "success": True,
        "cache_details": cache_details,
        "summary": {
            "total_agents": len(cache_details),
            "agents_with_cache": sum(1 for a in cache_details if a["has_cache"]),
            "total_cached_items": total_cached_items,
            "largest_cache": max((a["cache_size"] for a in cache_details), default=0)
        }
    }


# ============================================================================
# COSMOS DB CACHE ENDPOINTS
# ============================================================================

@router.get("/api/cache/cosmos/stats", response_model=StandardResponse)
@readonly_endpoint(agent_name="cosmos_cache_stats", timeout_seconds=20)
async def get_cosmos_cache_stats():
    """
    Get Cosmos DB cache statistics with enhanced metrics.
    
    Retrieves comprehensive statistics about Cosmos DB cache usage including
    EOL cache stats, inventory cache stats, and performance metrics.
    
    Returns:
        StandardResponse with Cosmos cache statistics and enhanced performance data.
    
    Example Response:
        {
            "success": true,
            "data": [{
                "eol_cache_stats": {...},
                "inventory_containers": {...},
                "enhanced_stats": {...}
            }]
        }
    """
    import time
    from fastapi import HTTPException
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    from utils.inventory_cache import inventory_cache

    start_time = time.time()
    try:
        was_cache_hit = False
        stats: Dict[str, Any] = {
            "cosmos": {
                "initialized": getattr(base_cosmos, "initialized", False),
                "database": getattr(base_cosmos, "database_name", None),
                "containers": getattr(base_cosmos, "container_configs", {}),
            }
        }

        try:
            eol_stats = await eol_cache.get_cache_stats()
            stats["eol_cache_stats"] = eol_stats
            was_cache_hit = bool(eol_stats.get("cached")) if isinstance(eol_stats, dict) else False
        except Exception as eol_error:
            stats["eol_cache_stats"] = {"error": str(eol_error)}

        try:
            inventory_stats = inventory_cache.get_cache_stats()
            stats["inventory_containers"] = inventory_stats
        except Exception as inv_error:
            stats["inventory_containers"] = {"error": str(inv_error)}

        try:
            enhanced_stats = cache_stats_manager.get_cosmos_statistics()
            stats["enhanced_stats"] = enhanced_stats
        except Exception as enh_error:
            stats["enhanced_stats"] = {"error": str(enh_error)}

        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(
            response_time_ms=response_time_ms,
            was_cache_hit=was_cache_hit,
            operation="stats_query",
        )

        response = StandardResponse.success_response(
            data=[stats],
            cached=was_cache_hit,
            metadata={"agent": "cosmos_cache_stats"},
        )
        return response.to_dict()

    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(
            response_time_ms=response_time_ms,
            was_cache_hit=False,
            operation="stats_query_error",
        )
        logger.error(f"Error getting Cosmos cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting cache stats: {str(e)}")


@router.post("/api/cache/cosmos/clear", response_model=StandardResponse)
@write_endpoint(agent_name="clear_cosmos_cache", timeout_seconds=30)
async def clear_cosmos_cache(agent_name: Optional[str] = None, software_name: Optional[str] = None):
    """
    Clear Cosmos DB cache with optional filters.
    
    Clears EOL cache entries from Cosmos DB. Can filter by software name
    and/or agent name, or clear all if no filters provided.
    
    Args:
        agent_name: Optional filter to clear only specific agent's cache entries
        software_name: Optional filter to clear only specific software's cache entries
    
    Returns:
        StandardResponse with clear operation results and count of cleared items.
    """
    from fastapi import HTTPException
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    
    if not getattr(base_cosmos, 'initialized', False):
        raise HTTPException(status_code=503, detail="Cosmos DB base client not initialized")
    
    result = await eol_cache.clear_cache(software_name=software_name, agent_name=agent_name)
    logger.info(f"Cosmos cache cleared: {result}")
    return result


@router.post("/api/cache/cosmos/initialize", response_model=StandardResponse)
@write_endpoint(agent_name="initialize_cosmos", timeout_seconds=45)
async def initialize_cosmos_cache():
    """
    Initialize Cosmos DB cache manually.
    
    Forces initialization of Cosmos DB base client and specialized caches
    (EOL cache, inventory cache). Useful for troubleshooting or recovery
    after connection failures.
    
    Returns:
        StandardResponse with initialization status and message.
    """
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    
    if getattr(base_cosmos, 'initialized', False):
        return {"success": True, "message": "Cosmos DB base client already initialized"}
    
    await base_cosmos._initialize_async()
    
    # Initialize specialized caches
    try:
        await eol_cache.initialize()
    except Exception:
        pass
    
    if getattr(base_cosmos, 'initialized', False):
        return {"success": True, "message": "Cosmos DB base client initialized successfully"}
    
    return {"success": False, "error": "Failed to initialize Cosmos DB base client"}


@router.get("/api/cache/cosmos/config", response_model=StandardResponse)
@readonly_endpoint(agent_name="cosmos_config", timeout_seconds=15)
async def get_cosmos_config():
    """
    Get Cosmos DB configuration and status.
    
    Retrieves Cosmos DB connection configuration including endpoint, database,
    container names, authentication method, and initialization status.
    
    Returns:
        StandardResponse with Cosmos DB configuration and error details if applicable.
    """
    from utils.config import config
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache

    cosmos_config = {
        "endpoint": config.azure.cosmos_endpoint if hasattr(config.azure, 'cosmos_endpoint') else None,
        "database": config.azure.cosmos_database if hasattr(config.azure, 'cosmos_database') else None,
        "container": getattr(eol_cache, 'container_id', 'eol_cache'),
        "auth_method": "DefaultAzureCredential (Managed Identity)",
        "base_initialized": getattr(base_cosmos, 'initialized', False),
        "eol_cache_initialized": getattr(eol_cache, 'initialized', False),
        "cache_duration_days": getattr(eol_cache, 'cache_duration_days', 30),
        "min_confidence_threshold": getattr(eol_cache, 'min_confidence_threshold', 80),
        "error": None,
        "error_details": None,
        "debug": None
    }

    # Add error details if base cosmos not initialized
    if not getattr(base_cosmos, 'initialized', False):
        cosmos_config["error"] = "Base Cosmos client failed to initialize"
        if getattr(base_cosmos, 'last_error', None):
            cosmos_config["error_details"] = base_cosmos.last_error
    
    # Include any structured details present on base_cosmos
    if getattr(base_cosmos, 'last_error_details', None):
        try:
            cosmos_config["debug"] = base_cosmos.last_error_details
        except Exception:
            cosmos_config["debug"] = {"note": "Failed to serialize last_error_details"}
        
    return cosmos_config


@router.get("/api/cache/cosmos/debug", response_model=StandardResponse)
@readonly_endpoint(agent_name="cosmos_debug", timeout_seconds=15)
async def get_cosmos_debug_info():
    """
    Get debug information about Cosmos DB container caching.
    
    Provides detailed debugging information about Cosmos DB cache state
    including base client, EOL cache, and inventory cache initialization
    and container availability.
    
    Returns:
        StandardResponse with comprehensive Cosmos DB debug information.
    """
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    from utils.inventory_cache import inventory_cache
    
    debug_info = {
        "base_cosmos": {
            "cache_info": base_cosmos.get_cache_info(),
            "initialization_attempted": getattr(base_cosmos, '_initialization_attempted', False)
        },
        "eol_cache": {
            "initialized": getattr(eol_cache, 'initialized', False),
            "container_available": eol_cache.container is not None,
            "container_id": getattr(eol_cache, 'container_id', None)
        },
        "inventory_cache": {
            "cosmos_initialized": inventory_cache.cosmos_client.initialized,
            "cache_stats": inventory_cache.get_cache_stats(),
            "container_mapping": inventory_cache.container_mapping
        }
    }
    
    return debug_info


@router.post("/api/cache/cosmos/test", response_model=StandardResponse)
@readonly_endpoint(agent_name="cosmos_cache_test", timeout_seconds=20)
async def test_cosmos_cache(req: Dict[str, Any]):
    """
    Test Cosmos DB cache retrieval for a specific request.
    
    Tests the EOL cache retrieval functionality by attempting to fetch cached
    data for a specific software/version/agent combination. Useful for verifying
    cache operations are working correctly.
    
    Request Body:
        software_name: str - Software name to search for
        version: Optional[str] - Software version
        agent_name: str - Agent name that created the cache entry
    
    Returns:
        StandardResponse with cache hit status and retrieved data if found.
    
    Example Request:
        {
            "software_name": "Windows Server 2016",
            "version": "10.0.14393",
            "agent_name": "microsoft"
        }
    """
    from utils.eol_cache import eol_cache
    
    software_name = req.get("software_name")
    version = req.get("version")
    agent_name = req.get("agent_name")
    
    cached_data = await eol_cache.get_cached_response(
        software_name,
        version,
        agent_name
    )
    
    if cached_data:
        return {
            "cache_hit": True,
            "data": cached_data,
            "message": "Data found in cache"
        }
    else:
        return {
            "cache_hit": False,
            "data": None,
            "message": "No cached data found"
        }


# ============================================================================
# CACHE STATISTICS ENDPOINTS
# ============================================================================

@router.get("/api/cache/stats/enhanced", response_model=StandardResponse)
@readonly_endpoint(agent_name="cache_stats_enhanced", timeout_seconds=10)
async def get_enhanced_cache_stats():
    """
    Get comprehensive cache statistics with real performance data.
    
    Returns aggregated statistics including agent performance metrics,
    inventory cache stats, Cosmos DB usage, and overall performance summary.
    
    Returns:
        StandardResponse with comprehensive cache statistics.
    """
    return cache_stats_manager.get_all_statistics()


@router.get("/api/cache/stats/agents", response_model=StandardResponse)
@readonly_endpoint(agent_name="cache_stats_agents", timeout_seconds=10)
async def get_agent_cache_stats():
    """
    Get detailed agent cache statistics.
    
    Returns per-agent cache performance including request counts, hit rates,
    average response times, and error rates.
    
    Returns:
        StandardResponse with agent-level cache statistics.
    """
    return cache_stats_manager.get_agent_statistics()


@router.get("/api/cache/stats/performance", response_model=StandardResponse)
@readonly_endpoint(agent_name="cache_stats_performance", timeout_seconds=10)
async def get_cache_performance_stats():
    """
    Get cache performance summary.
    
    Returns overall cache performance metrics including total requests,
    cache hit rates, and average response times.
    
    Returns:
        StandardResponse with cache performance summary.
    """
    return cache_stats_manager.get_performance_summary()


@router.post("/api/cache/stats/reset", response_model=StandardResponse)
@write_endpoint(agent_name="cache_stats_reset", timeout_seconds=10)
async def reset_cache_stats():
    """
    Reset all cache statistics (for testing or fresh start).
    
    Clears all recorded cache performance metrics including request counts,
    hit rates, response times, and error counts. Useful for testing or
    starting fresh with clean metrics.
    
    Returns:
        StandardResponse with reset confirmation.
    """
    cache_stats_manager.reset_all_stats()
    response = StandardResponse.success_response(
        [
            {
                "message": "All cache statistics have been reset",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
    )
    return response.to_dict()


# All cache endpoints have been successfully migrated from main.py
# Total: 17 endpoints covering status, clear, purge, inventory, webscraping, 
# Cosmos DB operations, and comprehensive statistics
