"""
Azure Monitor Community Resources API Module

This module provides endpoints for browsing and managing Azure Monitor Community
resources (workbooks, alerts, queries) from https://github.com/microsoft/AzureMonitorCommunity.

Loads from pre-generated metadata file for fast response without API rate limits or live scraping.

Key Features:
    - List available resource types (workbooks, alerts, queries)
    - Browse categories for each resource type
    - View resources within categories
    - Get detailed resource content
    - Deploy workbooks to Azure

Endpoints:
    GET /api/monitor-community/resources - Get all resources organized by type
    GET /api/monitor-community/types - List available resource types
    GET /api/monitor-community/categories/{resource_type} - List categories for a type
    GET /api/monitor-community/resources/{resource_type}/{category} - List resources in a category

Author: GitHub Copilot
Date: February 2026
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint

logger = logging.getLogger(__name__)

logger.info("Azure Monitor Community API using pre-generated metadata (no API calls needed)")

# Create router for Azure Monitor Community endpoints
router = APIRouter(tags=["Azure Monitor Community"])


def _get_monitor_mcp_client():
    """Get the Azure Monitor Community MCP client from orchestrator."""
    try:
        from main import get_mcp_orchestrator
        orchestrator = get_mcp_orchestrator()
        if orchestrator and hasattr(orchestrator, '_mcp_client'):
            # Get the composite client
            composite_client = orchestrator._mcp_client
            if composite_client and hasattr(composite_client, '_clients'):
                # Find the monitor client
                for label, client in composite_client._clients:
                    if label == "monitor":
                        return client
        return None
    except Exception as exc:
        logger.error("Failed to get Azure Monitor Community MCP client: %s", exc)
        return None


class ResourceTypeInfo(BaseModel):
    """Information about a resource type."""
    name: str = Field(..., description="Resource type name")
    description: str = Field(..., description="Resource type description")
    count: int = Field(0, description="Number of categories available")


class CategoryInfo(BaseModel):
    """Information about a resource category."""
    name: str = Field(..., description="Category name")
    path: str = Field(..., description="GitHub path")
    base_folder: str = Field(..., description="Base folder name")
    resource_count: int = Field(0, description="Number of resources in category")


class ResourceInfo(BaseModel):
    """Information about a specific resource."""
    name: str = Field(..., description="Resource name")
    path: str = Field(..., description="GitHub path")
    category: str = Field(..., description="Category name")
    resource_type: str = Field(..., description="Resource type")
    download_url: str = Field(..., description="Download URL")
    size: int = Field(..., description="File size in bytes")


@router.get(
    "/api/monitor-community/resources",
    summary="Get all Azure Monitor Community resources",
)
@readonly_endpoint(agent_name="monitor_community_resources")
async def get_all_resources():
    """
    Retrieve all available workbooks, alerts, and queries organized by type and category.
    
    Loads from pre-generated metadata file for fast response without live scraping.
    
    Returns:
        Dict with organized resource catalog
    """
    logger.info("=" * 80)
    logger.info("GET /api/monitor-community/resources endpoint called")
    logger.info("=" * 80)
    
    try:
        # Load from pre-generated metadata file
        from pathlib import Path
        
        metadata_file = Path(__file__).parent.parent / "static" / "data" / "azure_monitor_community_metadata.json"
        logger.info(f"Loading metadata from: {metadata_file}")
        
        if not metadata_file.exists():
            logger.warning(f"Metadata file not found: {metadata_file}")
            logger.info("Run: python deploy/update_monitor_community_metadata.py to generate it")
            return {
                "success": False,
                "data": [],
                "count": 0,
                "cached": False,
                "timestamp": datetime.utcnow().isoformat(),
                "error": "Metadata file not found. Run update_monitor_community_metadata.py to generate it.",
                "metadata": {"workbooks": [], "alerts": [], "queries": []}
            }
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Transform metadata format to match expected UI format
        workbooks_data = []
        alerts_data = []
        queries_data = []
        
        for category_data in metadata.get("categories", []):
            category_name = category_data.get("category")
            
            # Extract workbooks
            workbooks = category_data.get("workbooks", {})
            if workbooks.get("count", 0) > 0:
                workbooks_data.append({
                    "category": category_name,
                    "count": workbooks["count"],
                    "path": f"Azure Services/{category_name}/Workbooks",
                    "files": workbooks.get("files", [])
                })
            
            # Extract alerts
            alerts = category_data.get("alerts", {})
            if alerts.get("count", 0) > 0:
                alerts_data.append({
                    "category": category_name,
                    "count": alerts["count"],
                    "path": f"Azure Services/{category_name}/Alerts",
                    "files": alerts.get("files", [])
                })
            
            # Extract queries
            queries = category_data.get("queries", {})
            if queries.get("count", 0) > 0:
                queries_data.append({
                    "category": category_name,
                    "count": queries["count"],
                    "path": f"Azure Services/{category_name}/Queries",
                    "files": queries.get("files", [])
                })
        
        total_categories = len(metadata.get("categories", []))
        total_wb = sum(c["count"] for c in workbooks_data)
        total_alerts = sum(c["count"] for c in alerts_data)
        total_queries = sum(c["count"] for c in queries_data)
        
        result = {
            "success": True,
            "data": [],
            "count": 0,
            "cached": True,  # Mark as cached since loaded from file
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "workbooks": workbooks_data,
                "alerts": alerts_data,
                "queries": queries_data,
                "summary": {
                    "total_categories": total_categories,
                    "workbook_categories": len(workbooks_data),
                    "alert_categories": len(alerts_data),
                    "query_categories": len(queries_data),
                    "total_workbooks": total_wb,
                    "total_alerts": total_alerts,
                    "total_queries": total_queries
                },
                "generated_at": metadata.get("generated_at"),
                "generation_method": metadata.get("method")
            },
            "message": f"Retrieved {len(workbooks_data)} workbook categories, {len(alerts_data)} alert categories, {len(queries_data)} query categories from cached metadata"
        }
        
        logger.info(f"Successfully loaded resources from metadata: {result['message']}")
        return result
        
    except Exception as exc:
        logger.exception("Error in get_all_resources endpoint")
        error_msg = str(exc)
        
        return {
            "success": False,
            "data": [],
            "count": 0,
            "cached": False,
            "timestamp": datetime.utcnow().isoformat(),
            "error": f"Error loading metadata: {error_msg}",
            "metadata": {"workbooks": [], "alerts": [], "queries": []}
        }


@router.get(
    "/api/monitor-community/types",
    response_model=StandardResponse,
    summary="List Azure Monitor Community resource types",
)
@readonly_endpoint(agent_name="monitor_community_types")
async def list_resource_types() -> StandardResponse:
    """
    List all available resource types (workbooks, alerts, queries).
    
    Returns:
        StandardResponse with resource type information
    """
    try:
        client = _get_monitor_mcp_client()
        if not client:
            return StandardResponse(
                success=False,
                message="Azure Monitor Community MCP client not available",
                data={"resource_types": []},
            )

        result = await client.call_tool("list_resource_types", {})
        
        if result.get("success"):
            return StandardResponse(
                success=True,
                message="Resource types retrieved successfully",
                data=result,
            )
        else:
            return StandardResponse(
                success=False,
                message="Failed to retrieve resource types",
                data=result,
            )
        
    except Exception as exc:
        logger.exception("Error listing resource types")
        return StandardResponse(
            success=False,
            message=f"Error listing resource types: {str(exc)}",
            data={},
        )


@router.get(
    "/api/monitor-community/categories/{resource_type}",
    response_model=StandardResponse,
    summary="List categories for a resource type",
)
@readonly_endpoint(agent_name="monitor_community_categories")
async def list_categories(resource_type: str) -> StandardResponse:
    """
    List all categories for a specific resource type.
    
    Args:
        resource_type: The type of resource ('workbooks', 'alerts', or 'queries')
    
    Returns:
        StandardResponse with category list
    """
    try:
        client = _get_monitor_mcp_client()
        if not client:
            return StandardResponse(
                success=False,
                message="Azure Monitor Community MCP client not available",
                data={"categories": []},
            )

        result = await client.call_tool("list_categories", {"resource_type": resource_type})
        
        if result.get("success"):
            return StandardResponse(
                success=True,
                message=f"Retrieved {result.get('count', 0)} categories for {resource_type}",
                data=result,
            )
        else:
            return StandardResponse(
                success=False,
                message=f"Failed to retrieve categories for {resource_type}",
                data=result,
            )
        
    except Exception as exc:
        logger.exception("Error listing categories for %s", resource_type)
        return StandardResponse(
            success=False,
            message=f"Error listing categories: {str(exc)}",
            data={},
        )


@router.get(
    "/api/monitor-community/resources/{resource_type}/{category}",
    response_model=StandardResponse,
    summary="List resources in a category",
)
@readonly_endpoint(agent_name="monitor_community_resources_list")
async def list_resources_in_category(
    resource_type: str,
    category: str,
    base_path: str = Query(..., description="Base folder path from list_categories")
) -> StandardResponse:
    """
    List all resources in a specific category.
    
    Args:
        resource_type: The type of resource ('workbooks', 'alerts', or 'queries')
        category: The category name
        base_path: The base folder path (from list_categories response)
    
    Returns:
        StandardResponse with resource list
    """
    try:
        client = _get_monitor_mcp_client()
        if not client:
            return StandardResponse(
                success=False,
                message="Azure Monitor Community MCP client not available",
                data={"resources": []},
            )

        result = await client.call_tool("list_resources", {
            "resource_type": resource_type,
            "category": category,
            "base_path": base_path
        })
        
        if result.get("success"):
            return StandardResponse(
                success=True,
                message=f"Retrieved {result.get('count', 0)} {resource_type} in {category}",
                data=result,
            )
        else:
            return StandardResponse(
                success=False,
                message=f"Failed to retrieve {resource_type} in {category}",
                data=result,
            )
        
    except Exception as exc:
        logger.exception("Error listing resources in %s/%s", resource_type, category)
        return StandardResponse(
            success=False,
            message=f"Error listing resources: {str(exc)}",
            data={},
        )


@router.get(
    "/api/monitor-community/resource/content",
    response_model=StandardResponse,
    summary="Get resource content details",
)
@readonly_endpoint(agent_name="monitor_community_content")
async def get_resource_content(
    download_url: str = Query(..., description="Download URL from list_resources"),
    resource_type: str = Query(..., description="Resource type")
) -> StandardResponse:
    """
    Get detailed content for a specific resource.
    
    Args:
        download_url: The download URL of the resource
        resource_type: The type of resource
    
    Returns:
        StandardResponse with resource content and parameters
    """
    try:
        client = _get_monitor_mcp_client()
        if not client:
            return StandardResponse(
                success=False,
                message="Azure Monitor Community MCP client not available",
                data={},
            )

        result = await client.call_tool("get_resource_content", {
            "download_url": download_url,
            "resource_type": resource_type
        })
        
        if result.get("success"):
            return StandardResponse(
                success=True,
                message="Resource content retrieved successfully",
                data=result,
            )
        else:
            return StandardResponse(
                success=False,
                message="Failed to retrieve resource content",
                data=result,
            )
        
    except Exception as exc:
        logger.exception("Error getting resource content")
        return StandardResponse(
            success=False,
            message=f"Error getting resource content: {str(exc)}",
            data={},
        )
