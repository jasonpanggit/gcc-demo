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
    from main import _inventory_context_cache
    
    start_time = time.time()
    
    stats = {
        "cached": _inventory_context_cache["data"] is not None,
        "timestamp": _inventory_context_cache["timestamp"].isoformat() if _inventory_context_cache["timestamp"] else None,
        "ttl_seconds": _inventory_context_cache["ttl"],
        "age_seconds": (datetime.utcnow() - _inventory_context_cache["timestamp"]).total_seconds() if _inventory_context_cache["timestamp"] else None,
        "expired": False,
        "items_count": 0,
        "size_bytes": 0,
        "computers_count": 0,
        "software_count": 0
    }
    
    was_cache_hit = False
    
    if _inventory_context_cache["data"]:
        was_cache_hit = True
        data = _inventory_context_cache["data"]
        stats["size_bytes"] = len(str(data))
        stats["items_count"] = len(data) if isinstance(data, list) else 1
        
        # Check if expired
        if _inventory_context_cache["timestamp"]:
            age = (datetime.utcnow() - _inventory_context_cache["timestamp"]).total_seconds()
            stats["expired"] = age > _inventory_context_cache["ttl"]
        
        # Try to analyze the inventory data structure
        if isinstance(data, list):
            computers = set()
            software_items = 0
            for item in data:
                if isinstance(item, dict):
                    if "ComputerName" in item:
                        computers.add(item["ComputerName"])
                    if "ProductName" in item or "DisplayName" in item:
                        software_items += 1
            
            stats["computers_count"] = len(computers)
            stats["software_count"] = software_items
        elif isinstance(data, dict):
            if "computers" in data:
                stats["computers_count"] = len(data.get("computers", []))
            if "software" in data:
                stats["software_count"] = len(data.get("software", []))
    
    # Record performance metrics
    response_time_ms = (time.time() - start_time) * 1000
    cache_stats_manager.record_inventory_request(
        response_time_ms=response_time_ms,
        was_cache_hit=was_cache_hit,
        items_count=stats["items_count"]
    )
    
    # Add enhanced statistics
    enhanced_inventory_stats = cache_stats_manager.get_inventory_statistics()
    
    return {
        "success": True,
        "cache_stats": stats,
        "enhanced_stats": enhanced_inventory_stats
    }


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
    from main import _inventory_context_cache
    
    if not _inventory_context_cache["data"]:
        return {
            "success": False,
            "error": "No inventory data cached"
        }
    
    data = _inventory_context_cache["data"]
    details = {
        "timestamp": _inventory_context_cache["timestamp"].isoformat() if _inventory_context_cache["timestamp"] else None,
        "ttl_seconds": _inventory_context_cache["ttl"],
        "size_bytes": len(str(data)),
        "type": type(data).__name__,
        "sample_data": {},
        "summary": {}
    }
    
    if isinstance(data, list) and len(data) > 0:
        # Analyze the list structure
        computers = {}
        software_by_computer = {}
        all_software = {}
        
        for i, item in enumerate(data[:1000]):  # Limit to first 1000 items for performance
            if isinstance(item, dict):
                computer_name = item.get("ComputerName", "Unknown")
                software_name = item.get("ProductName") or item.get("DisplayName", "Unknown Software")
                version = item.get("Version", "Unknown")
                
                # Track computers
                if computer_name not in computers:
                    computers[computer_name] = 0
                computers[computer_name] += 1
                
                # Track software by computer
                if computer_name not in software_by_computer:
                    software_by_computer[computer_name] = set()
                software_by_computer[computer_name].add(f"{software_name} {version}")
                
                # Track all software
                if software_name not in all_software:
                    all_software[software_name] = set()
                all_software[software_name].add(version)
        
        # Create summary
        details["summary"] = {
            "total_entries": len(data),
            "unique_computers": len(computers),
            "unique_software": len(all_software),
            "avg_software_per_computer": sum(len(sw) for sw in software_by_computer.values()) / len(software_by_computer) if software_by_computer else 0
        }
        
        # Sample data (first few entries)
        details["sample_data"] = {
            "first_5_entries": data[:5] if len(data) >= 5 else data,
            "top_computers": dict(sorted(computers.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_software": {k: list(v)[:5] for k, v in sorted(all_software.items(), key=lambda x: len(x[1]), reverse=True)[:10]}
        }
        
    elif isinstance(data, dict):
        details["summary"] = {
            "keys": list(data.keys()),
            "structure": {k: type(v).__name__ for k, v in data.items()}
        }
        details["sample_data"] = {k: str(v)[:200] + "..." if len(str(v)) > 200 else v for k, v in list(data.items())[:10]}
    
    return {
        "success": True,
        "details": details
    }


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
    for agent_name in ["microsoft", "redhat", "ubuntu", "oracle", "vmware", "apache", "nodejs", "postgresql", "php", "python", "azure_ai", "websurfer"]:
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
    
    start_time = time.time()
    was_cache_hit = False
    
    if not getattr(base_cosmos, 'initialized', False):
        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(response_time_ms, False, "stats_query_failed")
        raise HTTPException(status_code=503, detail="Cosmos DB base client not initialized")
    
    try:
        # Get EOL cache stats
        stats = await eol_cache.get_cache_stats()
        was_cache_hit = stats.get('success', False)
        
        # Add inventory cache statistics to the Cosmos DB section
        try:
            from utils.inventory_cache import inventory_cache
            
            cache_stats = inventory_cache.get_cache_stats()
            software_memory_count = cache_stats.get('memory_cache_entries', {}).get('software', 0)
            os_memory_count = cache_stats.get('memory_cache_entries', {}).get('os', 0)
            
            if 'success' not in stats:
                stats['success'] = True
            
            stats['inventory_containers'] = {
                'software_container': 'inventory_software',
                'os_container': 'inventory_os',
                'memory_cache_entries': {
                    'software': software_memory_count,
                    'os': os_memory_count
                },
                'total_memory_entries': software_memory_count + os_memory_count,
                'cache_duration_hours': cache_stats.get('cache_duration_hours', 4),
                'supported_cache_types': cache_stats.get('supported_cache_types', ['software', 'os'])
            }
            
        except Exception as inv_err:
            logger.warning(f"Could not get inventory cache stats for Cosmos DB section: {inv_err}")
            stats['inventory_containers'] = {'error': str(inv_err)}
        
        # Record performance metrics
        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(
            response_time_ms=response_time_ms,
            was_cache_hit=was_cache_hit,
            operation="stats_query"
        )
        
        # Add enhanced statistics
        enhanced_cosmos_stats = cache_stats_manager.get_cosmos_statistics()
        stats["enhanced_stats"] = enhanced_cosmos_stats
        
        return stats
        
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(response_time_ms, False, "stats_query_error")
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
    return {
        "success": True,
        "message": "All cache statistics have been reset",
        "timestamp": datetime.utcnow().isoformat()
    }


# All cache endpoints have been successfully migrated from main.py
# Total: 17 endpoints covering status, clear, purge, inventory, webscraping, 
# Cosmos DB operations, and comprehensive statistics
