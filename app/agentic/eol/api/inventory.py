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

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
import logging

from utils.config import config
from utils.normalization import normalize_os_record
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    with_timeout_and_stats,
    readonly_endpoint,
    write_endpoint,
    standard_endpoint
)

logger = logging.getLogger(__name__)

# Create router for inventory endpoints
router = APIRouter(tags=["Inventory Management"])


def _apply_os_inventory_normalization(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize OS identity fields on an inventory row in place."""
    if not isinstance(item, dict):
        return item

    normalized = normalize_os_record(
        item.get("os_name") or item.get("name"),
        item.get("os_version") or item.get("version"),
        item.get("os_type"),
    )

    item.setdefault("raw_os_name", normalized.get("raw_os_name"))
    item.setdefault("raw_os_version", normalized.get("raw_os_version"))
    item["os_name"] = normalized["os_name"]
    item["os_version"] = normalized.get("os_version")
    item["normalized_os_name"] = normalized.get("normalized_os_name")
    item["normalized_os_version"] = normalized.get("normalized_os_version")
    item["os_type"] = normalized.get("os_type") or item.get("os_type")
    if item.get("software_type") == "operating system":
        if "name" in item:
            item["name"] = normalized["os_name"]
        if "version" in item:
            item["version"] = normalized.get("os_version")
    return item


def _get_eol_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_eol_orchestrator
    return get_eol_orchestrator()


async def _merge_azure_vm_os_inventory(os_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge Azure VMs from resource inventory into OS inventory results."""
    if not isinstance(os_items, list):
        return os_items

    try:
        from utils.resource_inventory_client import get_resource_inventory_client

        inv_client = get_resource_inventory_client()
        azure_vms = await inv_client.get_resources(
            "Microsoft.Compute/virtualMachines",
            subscription_id=config.azure.subscription_id,
        )

        existing_resource_ids = {
            str(item.get("resource_id") or item.get("resourceId") or "").lower()
            for item in os_items
            if str(item.get("resource_id") or item.get("resourceId") or "").strip()
        }
        existing_computer_names = {
            str(item.get("computer_name") or item.get("computer") or "").strip().lower()
            for item in os_items
            if str(item.get("computer_name") or item.get("computer") or "").strip()
        }

        for vm in azure_vms:
            selected = vm.get("selected_properties") or {}
            resource_id = str(vm.get("resource_id") or vm.get("id") or "")
            if not resource_id:
                continue
            if resource_id.lower() in existing_resource_ids:
                continue

            vm_name = str(vm.get("resource_name") or vm.get("name") or "").strip()
            if not vm_name or vm_name.lower() in existing_computer_names:
                continue

            normalized_os = normalize_os_record(
                selected.get("os_image") or selected.get("os_type") or vm.get("os_name") or "Unknown",
                vm.get("os_version"),
                selected.get("os_type") or vm.get("os_type"),
            )

            os_items.append({
                "computer_name": vm_name,
                "computer": vm_name,
                "os_name": normalized_os["os_name"],
                "name": normalized_os["os_name"],
                "os_version": normalized_os.get("os_version"),
                "version": normalized_os.get("os_version"),
                "os_type": normalized_os.get("os_type") or "Unknown",
                "raw_os_name": normalized_os.get("raw_os_name"),
                "raw_os_version": normalized_os.get("raw_os_version"),
                "normalized_os_name": normalized_os.get("normalized_os_name"),
                "normalized_os_version": normalized_os.get("normalized_os_version"),
                "vendor": "Unknown",
                "computer_environment": "Azure",
                "computer_type": "Azure VM",
                "resource_group": vm.get("resource_group") or vm.get("resourceGroup") or "",
                "resource_id": resource_id,
                "last_heartbeat": None,
                "source": "resource_inventory",
                "software_type": "operating system",
                "vm_type": "azure-vm",
            })
            existing_resource_ids.add(resource_id.lower())
            existing_computer_names.add(vm_name.lower())
    except Exception as exc:
        logger.warning("Failed to merge Azure VMs into OS inventory: %s", exc)

    return os_items


async def _enrich_missing_os_eol(items: List[Dict[str, Any]]) -> None:
    """Populate EOL fields only for OS rows that were added without enrichment."""
    if not isinstance(items, list) or not items:
        return

    candidates = [
        item for item in items
        if isinstance(item, dict)
        and not item.get("eol_date")
        and item.get("source") == "resource_inventory"
    ]

    if not candidates:
        return

    orchestrator = _get_eol_orchestrator()
    semaphore = asyncio.Semaphore(4)

    async def enrich_item(item: Dict[str, Any]) -> None:
        lookup_name = item.get("os_name") or item.get("name") or ""
        lookup_version = item.get("os_version") or item.get("version")
        if not lookup_name:
            return

        async with semaphore:
            try:
                eol_result = await orchestrator.get_autonomous_eol_data(
                    lookup_name,
                    lookup_version,
                    item_type="os",
                )
            except Exception:
                return

        if not eol_result or not eol_result.get("success"):
            return

        data_block = eol_result.get("data") if isinstance(eol_result, dict) else None
        if not isinstance(data_block, dict):
            return

        if data_block.get("eol_date"):
            item["eol_date"] = data_block.get("eol_date")
        if data_block.get("support_end_date") or data_block.get("support"):
            item["support_end_date"] = data_block.get("support_end_date") or data_block.get("support")
        item["eol_source"] = data_block.get("source") or data_block.get("agent_used")
        item["eol_confidence"] = data_block.get("confidence")

    await asyncio.gather(*(enrich_item(item) for item in candidates), return_exceptions=True)


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
    result = await _get_eol_orchestrator().get_software_inventory(
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
    summary = await _get_eol_orchestrator().agents["inventory"].get_inventory_summary()
    return {
        "status": "ok",
        "log_analytics_available": bool(config.azure.log_analytics_workspace_id),
        "summary": summary
    }


@router.get("/api/os", response_model=StandardResponse)
@standard_endpoint(agent_name="os_inventory", timeout_seconds=30)
async def get_os(request: Request):
    """
    Get operating system inventory with EOL status via single PostgreSQL JOIN.

    Replaces the former orchestrator + normalization + merge + N+1 EOL enrichment
    path (BH-005) with a single inventory_repo query that bulk-JOINs eol_records.

    Returns:
        StandardResponse with paginated OS inventory including VM names, OS types,
        versions, and EOL status.
    """
    inventory_repo = request.app.state.inventory_repo

    # Extract query params
    subscription_id = request.query_params.get("subscription_id")
    os_search = request.query_params.get("os_search")
    limit = int(request.query_params.get("limit", "50"))
    offset = int(request.query_params.get("offset", "0"))

    # Single query replaces: orchestrator + normalization + merge + N+1 EOL enrichment
    results, total = await asyncio.gather(
        inventory_repo.get_vm_inventory_with_eol(
            subscription_id=subscription_id,
            os_search=os_search,
            limit=limit,
            offset=offset,
        ),
        inventory_repo.count_vm_inventory(
            subscription_id=subscription_id,
            os_search=os_search,
        ),
    )

    return StandardResponse(
        success=True,
        data={
            "items": results,
            "total": total,
            "offset": offset,
            "limit": limit,
        },
        count=len(results),
        message=f"Retrieved {len(results)} OS inventory records" if results else "No OS inventory data available",
    )


@router.get("/api/os/summary", response_model=StandardResponse)
@readonly_endpoint(agent_name="os_summary", timeout_seconds=30)
async def get_os_summary(request: Request):
    """
    Get summarized OS counts and top versions.

    Aggregates OS inventory from inventory_repo (PostgreSQL) instead of
    calling the orchestrator agent. Groups VMs by os_name with EOL status.

    Returns:
        StandardResponse with OS summary statistics including counts by OS type
        and EOL status.
    """
    inventory_repo = request.app.state.inventory_repo

    # Get all VMs with EOL info (no pagination, we need full set for summary)
    all_vms = await inventory_repo.get_vm_inventory_with_eol(limit=10000, offset=0)

    # Aggregate summary by OS name
    os_summary = {}
    for vm in all_vms:
        os_name = vm.get("os_name") or "Unknown"
        if os_name not in os_summary:
            os_summary[os_name] = {
                "os_name": os_name,
                "vm_count": 0,
                "is_eol": vm.get("is_eol"),
                "eol_date": str(vm.get("eol_date")) if vm.get("eol_date") else None,
            }
        os_summary[os_name]["vm_count"] += 1

    summary_list = sorted(os_summary.values(), key=lambda x: x["vm_count"], reverse=True)

    return StandardResponse(
        success=True,
        data=summary_list,
        count=len(summary_list),
        message=f"Retrieved {len(summary_list)} OS summary records",
    )


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
    inventory_agent = _get_eol_orchestrator().agents.get("software_inventory")
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
    inventory_agent = _get_eol_orchestrator().agents.get("os_inventory")
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

    if result.get("success") and isinstance(result.get("data"), list):
        result["data"] = await _merge_azure_vm_os_inventory(result["data"])
        result["count"] = len(result["data"])

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
    result = await _get_eol_orchestrator().reload_inventory_from_law(days=days)
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
    orch = _get_eol_orchestrator()
    
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
