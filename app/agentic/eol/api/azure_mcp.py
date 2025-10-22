"""
Azure MCP API Router
Provides REST API endpoints for Azure MCP Server integration
"""
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils import get_logger
from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint, write_endpoint
from utils.azure_mcp_client import get_azure_mcp_client

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ToolCallRequest(BaseModel):
    """Request model for calling an Azure MCP tool."""
    tool_name: str
    arguments: Dict[str, Any] = {}


class ResourceQueryRequest(BaseModel):
    """Request model for Azure Resource Graph queries."""
    query: str


# ============================================================================
# AZURE MCP STATUS & INFO ENDPOINTS
# ============================================================================

@router.get("/api/azure-mcp/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_status", timeout_seconds=10)
async def get_azure_mcp_status():
    """
    Get the status of Azure MCP Server connection.
    
    Returns:
        StandardResponse with connection status and available tools count
    """
    try:
        client = await get_azure_mcp_client()
        
        status_info = {
            "initialized": client.is_initialized(),
            "available_tools_count": len(client.get_available_tools()),
            "connection_status": "connected" if client.is_initialized() else "disconnected"
        }
        
        return StandardResponse.success_response(
            data=[status_info],
            metadata={"agent": "azure_mcp"}
        )
    except Exception as e:
        logger.error(f"Error getting Azure MCP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/azure-mcp/tools", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_tools", timeout_seconds=10)
async def list_azure_mcp_tools():
    """
    List all available Azure MCP Server tools.
    
    Returns:
        StandardResponse with list of available tools and their descriptions
    """
    try:
        client = await get_azure_mcp_client()
        tools = client.get_available_tools()
        
        # Format tools for display
        formatted_tools = []
        for tool in tools:
            func = tool.get("function", {})
            formatted_tools.append({
                "name": func.get("name", "unknown"),
                "description": func.get("description", "No description available"),
                "parameters": func.get("parameters", {})
            })
        
        return StandardResponse.success_response(
            data=formatted_tools,
            metadata={"agent": "azure_mcp", "total_tools": len(formatted_tools)}
        )
    except Exception as e:
        logger.error(f"Error listing Azure MCP tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AZURE RESOURCE MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/api/azure-mcp/resource-groups", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_resource_groups", timeout_seconds=30)
async def list_resource_groups():
    """
    List all Azure resource groups in the subscription.
    
    Returns:
        StandardResponse with resource group information
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.list_resource_groups()
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return StandardResponse.success_response(
            data=[result],
            metadata={"agent": "azure_mcp", "operation": "list_resource_groups"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing resource groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/azure-mcp/storage-accounts", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_storage_accounts", timeout_seconds=30)
async def list_storage_accounts(resource_group: Optional[str] = None):
    """
    List Azure storage accounts.
    
    Args:
        resource_group: Optional resource group name to filter by
    
    Returns:
        StandardResponse with storage account information
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.list_storage_accounts(resource_group)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return StandardResponse.success_response(
            data=[result],
            metadata={
                "agent": "azure_mcp",
                "operation": "list_storage_accounts",
                "resource_group": resource_group
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing storage accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/azure-mcp/resources/{resource_id:path}", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_get_resource", timeout_seconds=30)
async def get_resource(resource_id: str):
    """
    Get details of a specific Azure resource by ID.
    
    Args:
        resource_id: The Azure resource ID
    
    Returns:
        StandardResponse with resource details
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.get_resource_by_id(resource_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return StandardResponse.success_response(
            data=[result],
            metadata={"agent": "azure_mcp", "operation": "get_resource"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/azure-mcp/query", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_query", timeout_seconds=60)
async def query_azure_resources(request: ResourceQueryRequest):
    """
    Query Azure resources using Azure Resource Graph.
    
    Args:
        request: ResourceQueryRequest with KQL query
    
    Returns:
        StandardResponse with query results
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.query_resources(request.query)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return StandardResponse.success_response(
            data=[result],
            metadata={"agent": "azure_mcp", "operation": "query_resources"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying Azure resources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GENERIC TOOL CALL ENDPOINT
# ============================================================================

@router.post("/api/azure-mcp/call-tool", response_model=StandardResponse)
@write_endpoint(agent_name="azure_mcp_call_tool", timeout_seconds=60)
async def call_azure_mcp_tool(request: ToolCallRequest):
    """
    Call any Azure MCP Server tool with custom arguments.
    
    Args:
        request: ToolCallRequest with tool name and arguments
    
    Returns:
        StandardResponse with tool execution result
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.call_tool(request.tool_name, request.arguments)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Tool call failed: {result.get('error', 'Unknown error')}"
            )
        
        return StandardResponse.success_response(
            data=[result],
            metadata={
                "agent": "azure_mcp",
                "operation": "call_tool",
                "tool_name": request.tool_name
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling Azure MCP tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))
