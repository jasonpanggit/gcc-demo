"""
Inventory Management API Module

This module provides endpoints for retrieving and managing software and OS inventory data.
It interfaces with Azure Log Analytics to fetch configuration data and heartbeat information,
enriching the raw data with End-of-Life (EOL) status analysis.

Key Features:
    - Software inventory retrieval with EOL enrichment
    - Operating system inventory from heartbeat data
    - Raw data access for troubleshooting
    - Cache management and forced refresh
    - Inventory reload from Log Analytics

Endpoints:
    GET  /api/inventory - Get software inventory with EOL analysis
    GET  /api/inventory/status - Get inventory system status
    GET  /api/os - Get operating system inventory
    GET  /api/os/summary - Get summarized OS statistics
    GET  /api/inventory/raw/software - Get raw software data
    GET  /api/inventory/raw/os - Get raw OS data
    POST /api/inventory/reload - Reload inventory from Log Analytics
    POST /api/inventory/clear-cache - Clear inventory caches

Author: GitHub Copilot
Date: October 2025
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
import logging

from utils.config import config
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    with_timeout_and_stats,
    readonly_endpoint,
    write_endpoint,
    standard_endpoint
)

logger = logging.getLogger(__name__)

# Import main module dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import get_eol_orchestrator

# Create router for inventory endpoints
router = APIRouter(tags=["Inventory Management"])


@router.get("/api/inventory", response_model=StandardResponse)
@with_timeout_and_stats(
    agent_name="inventory",
    timeout_seconds=config.app.timeout,
    track_cache=True,
    auto_wrap_response=False  # Keep original response format for now
)
async def get_inventory(limit: int = 5000, days: int = 90, use_cache: bool = True):
    """
    Get software inventory using multi-agent system.
    
    Retrieves software installation data from Azure Log Analytics and analyzes
    it for EOL status. Results are cached for performance.
    
    Args:
        limit: Maximum number of records to return (default: 5000)
        days: Number of days to look back for inventory data (default: 90)
        use_cache: Whether to use cached data if available (default: True)
    
    Returns:
        StandardResponse with software inventory data including computer names,
        software names, versions, publishers, and EOL status.
    
    Example Response:
        {
            "success": true,
            "data": [
                {
                    "computer": "SERVER-01",
                    "software_name": "Windows Server 2012 R2",
                    "version": "6.3.9600",
                    "publisher": "Microsoft",
                    "eol_status": "expired",
                    "eol_date": "2023-10-10"
                }
            ],
            "count": 1,
            "timestamp": "2025-10-15T10:30:00Z"
        }
    """
    result = await get_eol_orchestrator().get_software_inventory(
        days=days,
        use_cache=use_cache
    )
    
    # Apply limit if specified
    if limit and limit > 0 and isinstance(result, dict) and "data" in result:
        result["data"] = result["data"][:limit]
        result["count"] = len(result["data"])
    elif limit and limit > 0 and isinstance(result, list):
        # Legacy format support
        result = result[:limit]
    
    return result


@router.get("/api/inventory/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="inventory_status", timeout_seconds=30)
async def inventory_status():
    """
    Get inventory data status and summary.
    
    Returns the current status of the inventory system including Log Analytics
    availability and summary statistics.
    
    Returns:
        StandardResponse with status information including:
        - Log Analytics availability
        - Summary statistics (total items, last update, etc.)
        - Agent health status
    
    Example Response:
        {
            "success": true,
            "status": "ok",
            "log_analytics_available": true,
            "summary": {
                "total_software": 1250,
                "total_os": 85,
                "last_update": "2025-10-15T09:00:00Z"
            }
        }
    """
    summary = await get_eol_orchestrator().agents["inventory"].get_inventory_summary()
    return {
        "status": "ok",
        "log_analytics_available": bool(config.azure.log_analytics_workspace_id),
        "summary": summary
    }


@router.get("/api/os", response_model=StandardResponse)
@standard_endpoint(agent_name="os_inventory", timeout_seconds=30)
async def get_os(days: int = 90):
    """
    Get operating system inventory from Heartbeat via OS agent.
    
    Retrieves OS information from Log Analytics Heartbeat table and enriches
    it with EOL status for supported operating systems.
    
    Args:
        days: Number of days to look back for OS data (default: 90)
    
    Returns:
        StandardResponse with OS inventory including computer names, OS types,
        versions, and EOL status.
    
    Example Response:
        {
            "success": true,
            "data": [
                {
                    "computer": "WEB-SERVER-01",
                    "os_name": "Windows Server 2019",
                    "os_version": "10.0.17763",
                    "last_heartbeat": "2025-10-15T10:25:00Z",
                    "eol_status": "active",
                    "eol_date": "2029-01-09"
                }
            ],
            "count": 1
        }
    """
    return await get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days)


@router.get("/api/os/summary", response_model=StandardResponse)
@readonly_endpoint(agent_name="os_summary", timeout_seconds=30)
async def get_os_summary(days: int = 90):
    """
    Get summarized OS counts and top versions.
    
    Provides aggregated statistics about operating systems in the environment
    including version distributions, EOL risk levels, and top OS families.
    
    Args:
        days: Number of days to look back for OS data (default: 90)
    
    Returns:
        StandardResponse with OS summary statistics including counts by OS type,
        version distributions, and EOL risk levels.
    
    Example Response:
        {
            "success": true,
            "status": "ok",
            "summary": {
                "total_systems": 85,
                "os_families": {
                    "Windows Server": 45,
                    "Windows 10": 30,
                    "Linux": 10
                },
                "eol_risk": {
                    "high": 5,
                    "medium": 10,
                    "low": 70
                }
            }
        }
    """
    summary = await get_eol_orchestrator().agents["os_inventory"].get_os_summary(days=days)
    return {"status": "ok", "summary": summary}


@router.get("/api/inventory/raw/software", response_model=StandardResponse)
@with_timeout_and_stats(
    agent_name="software_inventory_raw",
    timeout_seconds=60,
    track_cache=True,
    auto_wrap_response=False
)
async def get_raw_software_inventory(days: int = 90, limit: int = 1000, force_refresh: bool = False):
    """
    Get raw software inventory data directly from Log Analytics ConfigurationData table.
    
    Returns unprocessed inventory data with comprehensive validation and error handling.
    Supports forced cache refresh for troubleshooting.
    
    Args:
        days: Number of days to look back for inventory data (default: 90)
        limit: Maximum number of records to return (default: 1000)
        force_refresh: Clear cache and fetch fresh data (default: False)
    
    Returns:
        StandardResponse with raw software inventory data including computer names,
        software details, publishers, and installation timestamps.
    
    Example Response:
        {
            "success": true,
            "data": [
                {
                    "computer": "SERVER-01",
                    "software": "Microsoft SQL Server 2016",
                    "version": "13.0.5026.0",
                    "publisher": "Microsoft Corporation",
                    "install_date": "2023-05-15"
                }
            ],
            "count": 1,
            "query_days": 90,
            "query_limit": 1000
        }
    """
    logger.info(f"📊 Raw inventory request: days={days}, limit={limit}, force_refresh={force_refresh}")
    
    # Get the software inventory agent directly
    inventory_agent = get_eol_orchestrator().agents.get("software_inventory")
    if not inventory_agent:
        raise HTTPException(
            status_code=503, 
            detail="Software inventory agent is not available"
        )
    
    # If force refresh is requested, clear cache first
    if force_refresh:
        logger.info("🔄 Force refresh requested - clearing software inventory cache")
        try:
            await inventory_agent.clear_cache()
            logger.info("✅ Software inventory cache cleared successfully")
        except Exception as cache_error:
            logger.warning(f"⚠️ Failed to clear software inventory cache: {cache_error}")
    
    # Call the software inventory method with appropriate cache setting
    use_cache = not force_refresh
    result = await inventory_agent.get_software_inventory(days=days, limit=limit, use_cache=use_cache)
    
    # Validate result type
    if isinstance(result, str):
        logger.warning(f"Raw software inventory returned string instead of dict: {result}")
        return {
            "success": False,
            "error": f"Invalid response format: {result}",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    elif not isinstance(result, dict):
        logger.warning(f"Raw software inventory returned unexpected type {type(result)}: {result}")
        return {
            "success": False,
            "error": f"Invalid response type: {type(result).__name__}",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }

    logger.info(f"✅ Raw software inventory result: success={result.get('success')}, count={result.get('count', 0)}")
    return result


@router.get("/api/inventory/raw/os", response_model=StandardResponse)
@with_timeout_and_stats(
    agent_name="os_inventory_raw",
    timeout_seconds=60,
    track_cache=True,
    auto_wrap_response=False
)
async def get_raw_os_inventory(days: int = 90, limit: int = 2000, force_refresh: bool = False):
    """
    Get raw operating system inventory data directly from Log Analytics Heartbeat table.
    
    Returns unprocessed OS inventory data with validation. Caching is handled
    automatically by the inventory agent using InventoryRawCache.
    
    Args:
        days: Number of days to look back for OS data (default: 90)
        limit: Maximum number of records to return (default: 2000)
        force_refresh: Clear cache and fetch fresh data (default: False)
    
    Returns:
        StandardResponse with raw OS inventory including computer names, OS types,
        versions, last heartbeat times, and health status.
    
    Example Response:
        {
            "success": true,
            "data": [
                {
                    "computer": "DB-SERVER-02",
                    "os": "Microsoft Windows Server 2022",
                    "os_version": "10.0.20348",
                    "computer_environment": "Azure",
                    "last_heartbeat": "2025-10-15T10:20:00Z"
                }
            ],
            "count": 1,
            "query_days": 90,
            "query_limit": 2000
        }
    """
    logger.info(f"📊 Raw OS inventory request: days={days}, limit={limit}, force_refresh={force_refresh}")
    
    # Get the inventory agent directly
    inventory_agent = get_eol_orchestrator().agents.get("os_inventory")
    if not inventory_agent:
        raise HTTPException(
            status_code=503, 
            detail="OS inventory agent is not available"
        )
    
    # If force refresh is requested, clear cache first
    if force_refresh:
        logger.info("🔄 Force refresh requested - clearing OS inventory cache")
        try:
            await inventory_agent.clear_cache()
            logger.info("✅ OS inventory cache cleared successfully")
        except Exception as cache_error:
            logger.warning(f"⚠️ Failed to clear OS inventory cache: {cache_error}")
    
    # Call the OS inventory method with appropriate cache setting
    use_cache = not force_refresh
    result = await inventory_agent.get_os_inventory(days=days, limit=limit, use_cache=use_cache)
    
    # Validate result type
    if isinstance(result, str):
        logger.warning(f"Raw OS inventory returned string instead of dict: {result}")
        return {
            "success": False,
            "error": f"Invalid response format: {result}",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    elif not isinstance(result, dict):
        logger.warning(f"Raw OS inventory returned unexpected type {type(result)}: {result}")
        return {
            "success": False,
            "error": f"Invalid response type: {type(result).__name__}",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    
    logger.info(f"✅ Raw OS inventory result: success={result.get('success')}, count={result.get('count', 0)}")
    return result


@router.post("/api/inventory/reload", response_model=StandardResponse)
@write_endpoint(agent_name="inventory_reload", timeout_seconds=120)
async def reload_inventory(days: int = 90):
    """
    Reload inventory data from Log Analytics Workspace with EOL enrichment.
    
    Refreshes cached inventory data by querying Log Analytics, enriching with
    EOL information, and updating caches. Long-running operation (up to 2 minutes).
    
    Args:
        days: Number of days of data to reload (default: 90)
    
    Returns:
        StandardResponse with reload results including total items and processing time.
    
    Example Response:
        {
            "success": true,
            "total_items": 1250,
            "processing_time_seconds": 45.2,
            "timestamp": "2025-10-15T10:30:00Z"
        }
    """
    result = await get_eol_orchestrator().reload_inventory_from_law(days=days)
    logger.info("Inventory reloaded: %s items", result.get("total_items", 0))
    return result


@router.post("/api/inventory/clear-cache", response_model=StandardResponse)
@write_endpoint(agent_name="inventory_clear_cache", timeout_seconds=30)
async def clear_inventory_cache():
    """
    Clear the raw inventory data cache to force fresh data from Log Analytics.
    
    Clears both software and OS inventory caches, forcing next query to retrieve
    fresh data from Log Analytics Workspace rather than using cached data.
    
    Returns:
        StandardResponse with clear results for software and OS caches.
    
    Example Response:
        {
            "success": true,
            "software_cache_cleared": true,
            "os_cache_cleared": true,
            "timestamp": "2025-10-15T10:35:00Z"
        }
    """
    # Get orchestrator to access inventory agents
    orch = get_eol_orchestrator()
    
    # Clear both software and OS inventory caches
    software_result = {"software_cache_cleared": False}
    os_result = {"os_cache_cleared": False}
    
    try:
        # Access the software inventory agent through the inventory agent
        if hasattr(orch, 'inventory_agent') and orch.inventory_agent:
            if hasattr(orch.inventory_agent, 'software_inventory_agent'):
                await orch.inventory_agent.software_inventory_agent.clear_cache()
                software_result["software_cache_cleared"] = True
                logger.info("Software inventory cache cleared")
    except Exception as e:
        logger.warning(f"Error clearing software cache: {e}")
        software_result["error"] = str(e)
    
    try:
        # Access the OS inventory agent directly and through inventory agent
        if hasattr(orch, 'os_agent') and orch.os_agent:
            await orch.os_agent.clear_cache()
            os_result["os_cache_cleared"] = True
            logger.info("OS inventory cache cleared")
        elif hasattr(orch, 'inventory_agent') and orch.inventory_agent:
            if hasattr(orch.inventory_agent, 'os_inventory_agent'):
                await orch.inventory_agent.os_inventory_agent.clear_cache()
                os_result["os_cache_cleared"] = True
                logger.info("OS inventory cache cleared via inventory agent")
    except Exception as e:
        logger.warning(f"Error clearing OS cache: {e}")
        os_result["error"] = str(e)
    
    # Merge results
    result = {**software_result, **os_result}
    result["success"] = (
        software_result.get("software_cache_cleared", False) or 
        os_result.get("os_cache_cleared", False)
    )
    
    return result
