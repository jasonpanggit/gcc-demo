"""
Azure MCP API Router
Provides REST API endpoints for Azure MCP Server integration
"""
import os
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils import get_logger
from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint, write_endpoint

# Import stdio client for direct MCP communication
from utils.azure_mcp_client import get_azure_mcp_client


def _orchestrator_disabled() -> bool:
    """Skip MCP orchestrator wiring when running under pytest or explicitly disabled."""
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("DISABLE_MCP_ORCHESTRATOR", "").lower() == "true"

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
    """Request model for Azure Resource Graph queries or Kusto queries."""
    query: str
    cluster_uri: Optional[str] = None  # For Kusto queries
    database: Optional[str] = None      # For Kusto queries


async def _load_composite_tool_catalog() -> List[Dict[str, Any]]:
    """Retrieve the full MCP tool catalog with source metadata, using orchestrator when possible."""
    if not _orchestrator_disabled():
        try:
            from agents.mcp_orchestrator import get_mcp_orchestrator

            orchestrator = await get_mcp_orchestrator()
            if await orchestrator.ensure_mcp_ready():
                tool_catalog = await orchestrator.get_tool_catalog()
                source_map = orchestrator.get_tool_source_map()

                formatted: List[Dict[str, Any]] = []
                for tool in tool_catalog:
                    func = tool.get("function", {})
                    metadata = tool.get("metadata", {})
                    name = func.get("name", "unknown")
                    formatted.append({
                        "name": name,
                        "description": func.get("description") or tool.get("description", "No description available"),
                        "parameters": func.get("parameters", {}),
                        "source": metadata.get("source") or source_map.get(name),
                        "original_name": metadata.get("original_name") or func.get("x_original_name"),
                        "metadata": metadata,
                    })

                formatted.sort(key=lambda item: item["name"].lower())
                return formatted
        except Exception as exc:  # pragma: no cover - fallback when orchestrator unavailable
            logger.warning("Unable to load MCP tool catalog via orchestrator: %s", exc)

    client = await get_azure_mcp_client()
    tools = client.get_available_tools()
    formatted: List[Dict[str, Any]] = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        formatted.append({
            "name": name,
            "description": func.get("description", "No description available"),
            "parameters": func.get("parameters", {}),
            "source": "azure",
            "original_name": func.get("name"),
            "metadata": {"source": "azure", "original_name": func.get("name")},
        })

    formatted.sort(key=lambda item: item["name"].lower())
    return formatted


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
        status_info: Dict[str, Any]

        try:
            from agents.mcp_orchestrator import get_mcp_orchestrator

            orchestrator = None
            ready = False
            if not _orchestrator_disabled():
                orchestrator = await get_mcp_orchestrator()
                ready = await orchestrator.ensure_mcp_ready()
        except Exception as orchestrator_exc:  # pragma: no cover - fallback to direct client
            logger.warning("MCP orchestrator unavailable; falling back to Azure MCP client: %s", orchestrator_exc)
            ready = False
            orchestrator = None  # type: ignore[assignment]

        if ready:
            tool_catalog = await orchestrator.get_tool_catalog()  # type: ignore[union-attr]
            tool_counts = orchestrator.summarize_tool_counts()  # type: ignore[union-attr]
            tool_sources = orchestrator.get_tool_source_map()  # type: ignore[union-attr]
            active_clients = orchestrator.get_registered_clients()  # type: ignore[union-attr]

            auth_mode = None
            try:
                azure_client = await get_azure_mcp_client()
                auth_mode = azure_client.get_auth_mode()
            except Exception:
                auth_mode = None

            status_info = {
                "initialized": True,
                "connection_status": "connected",
                "available_tools_count": len(tool_catalog),
                "active_clients": active_clients,
                "tool_counts": tool_counts,
                "tool_sources": tool_sources,
                "auth_mode": auth_mode,
            }
        else:
            client = await get_azure_mcp_client()
            initialized = client.is_initialized()
            tool_count = len(client.get_available_tools()) if initialized else 0
            status_info = {
                "initialized": initialized,
                "connection_status": "connected" if initialized else "disconnected",
                "available_tools_count": tool_count,
                "active_clients": ["azure"] if initialized else [],
                "tool_counts": {"azure": tool_count} if initialized else {},
                "tool_sources": {},
                "auth_mode": client.get_auth_mode(),
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
        formatted_tools = await _load_composite_tool_catalog()
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
    Query Azure Monitor logs using KQL.
    
    This endpoint uses the Azure MCP Server's monitor tool to execute KQL queries
    against Azure Monitor / Log Analytics workspace.
    
    Required environment variables:
    - SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID: Azure subscription ID
    - LOG_ANALYTICS_WORKSPACE_ID: Log Analytics workspace ID
    
    Args:
        request: ResourceQueryRequest with KQL query
    
    Returns:
        StandardResponse with query results from Azure Monitor
    """
    try:
        client = await get_azure_mcp_client()
        result = await client.query_resources(
            query=request.query,
            cluster_uri=request.cluster_uri,
            database=request.database
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
        return StandardResponse.success_response(
            data=[result],
            metadata={
                "agent": "azure_mcp",
                "operation": "query_azure_monitor",
                "tool": "monitor"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying Azure Monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GENERIC TOOL CALL ENDPOINT
# ============================================================================

@router.get("/api/azure-mcp/tools/search", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_mcp_tools_search", timeout_seconds=10)
async def search_azure_mcp_tools(pattern: str):
    """
    Search for Azure MCP tools by name pattern.
    
    Args:
        pattern: Search pattern to match against tool names
    
    Returns:
        StandardResponse with matching tools
    """
    try:
        tools = await _load_composite_tool_catalog()

        pattern_lower = pattern.lower()
        matching_tools: List[Dict[str, Any]] = []

        for tool in tools:
            tool_name = tool.get("name", "")
            tool_desc = tool.get("description", "")

            if pattern_lower in tool_name.lower() or pattern_lower in tool_desc.lower():
                matching_tools.append(tool)

        return StandardResponse.success_response(
            data=matching_tools,
            metadata={
                "agent": "azure_mcp",
                "search_pattern": pattern,
                "matches_found": len(matching_tools)
            }
        )
    except Exception as e:
        logger.error(f"Error searching Azure MCP tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        try:
            from agents.mcp_orchestrator import get_mcp_orchestrator

            orchestrator = None
            ready = False
            if not _orchestrator_disabled():
                orchestrator = await get_mcp_orchestrator()
                ready = await orchestrator.ensure_mcp_ready()
        except Exception as orchestrator_exc:  # pragma: no cover - fallback when orchestrator unavailable
            logger.warning("MCP orchestrator unavailable for tool call; falling back to Azure MCP client: %s", orchestrator_exc)
            ready = False
            orchestrator = None  # type: ignore[assignment]

        if ready:
            result = await orchestrator.execute_tool(request.tool_name, request.arguments)  # type: ignore[union-attr]
        else:
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


# ============================================================================
# MCP CHAT ORCHESTRATOR ENDPOINTS
# ============================================================================

class MCPChatRequest(BaseModel):
    """Request model for MCP chat messages."""
    message: str
    session_id: Optional[str] = None


@router.post("/api/azure-mcp/chat", response_model=StandardResponse)
@write_endpoint(agent_name="mcp_chat", timeout_seconds=60)
async def mcp_chat(request: MCPChatRequest):
    """
    Send a message to the MCP orchestrator and get a response.
    
    Args:
        request: MCPChatRequest with user message
    
    Returns:
        StandardResponse with assistant response and conversation history
    """
    try:
        from agents.mcp_orchestrator import get_mcp_orchestrator
        
        orchestrator = await get_mcp_orchestrator()
        result = await orchestrator.process_message(request.message)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Unknown error occurred")
            )
        
        return StandardResponse.success_response(
            data=[{
                "response": result.get("response"),
                "conversation_history": result.get("conversation_history", []),
                "session_id": result.get("metadata", {}).get("session_id")
            }],
            metadata=result.get("metadata", {})
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in MCP chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/azure-mcp/chat/history", response_model=StandardResponse)
@readonly_endpoint(agent_name="mcp_chat_history", timeout_seconds=10)
async def get_chat_history():
    """
    Get the current MCP chat conversation history.
    
    Returns:
        StandardResponse with conversation history
    """
    try:
        from agents.mcp_orchestrator import get_mcp_orchestrator
        
        orchestrator = await get_mcp_orchestrator()
        history = orchestrator.get_conversation_history()
        
        return StandardResponse.success_response(
            data=[{"history": history}],
            metadata={
                "agent": "mcp_orchestrator",
                "message_count": len(history)
            }
        )
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/azure-mcp/chat/clear", response_model=StandardResponse)
@write_endpoint(agent_name="mcp_chat_clear", timeout_seconds=10)
async def clear_chat():
    """
    Clear the MCP chat conversation history.
    
    Returns:
        StandardResponse confirming the clear operation
    """
    try:
        from agents.mcp_orchestrator import get_mcp_orchestrator
        
        orchestrator = await get_mcp_orchestrator()
        orchestrator.clear_conversation()
        
        return StandardResponse.success_response(
            data=[{"message": "Conversation cleared successfully"}],
            metadata={"agent": "mcp_orchestrator"}
        )
    except Exception as e:
        logger.error(f"Error clearing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AGENT COMMUNICATION STREAMING ENDPOINT
# ============================================================================

from fastapi.responses import StreamingResponse
import json
import asyncio


@router.get("/api/azure-mcp/agent-stream")
async def agent_communication_stream():
    """
    Server-Sent Events (SSE) endpoint for streaming real-time agent communication.
    
    Streams agent reasoning events including:
    - Reasoning phases (what the agent is thinking)
    - Action phases (tools being called with parameters)
    - Observation phases (tool results)
    - Reflection phases (learning from results)
    - Synthesis phases (final answer formulation)
    
    Returns:
        StreamingResponse with text/event-stream content type
    """
    from agents.mcp_orchestrator import get_mcp_orchestrator
    
    async def event_generator():
        """Generate SSE events from agent communication queue."""
        try:
            orchestrator = await get_mcp_orchestrator()
            
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Agent communication stream connected'})}\n\n"
            
            # First, send any buffered events from recent activity
            if hasattr(orchestrator, 'communication_buffer') and orchestrator.communication_buffer:
                logger.info(f"📤 Sending {len(orchestrator.communication_buffer)} buffered events to new SSE client")
                for comm in orchestrator.communication_buffer:
                    # Format and send buffered event
                    event_data = {
                        'type': comm.get('type', 'unknown'),
                        'content': comm.get('content', ''),
                        'iteration': comm.get('iteration'),
                        'timestamp': comm.get('timestamp', '')
                    }
                    
                    # Add type-specific fields
                    if comm.get('type') == 'action':
                        event_data['tool_name'] = comm.get('tool_name')
                        event_data['tool_params'] = comm.get('tool_params')
                    elif comm.get('type') == 'observation':
                        event_data['tool_result'] = comm.get('tool_result')
                        event_data['is_error'] = comm.get('is_error', False)
                    elif comm.get('type') in ['reasoning', 'planning']:
                        event_data['strategy'] = comm.get('strategy')
                    
                    yield f"data: {json.dumps(event_data)}\n\n"
            
            # Poll for agent communications with shorter intervals
            last_keepalive = asyncio.get_event_loop().time()
            keepalive_interval = 15  # seconds
            
            while True:
                # Check if there are any new communications
                if hasattr(orchestrator, 'communication_queue'):
                    try:
                        # Try to get a message with a short timeout
                        comm = await asyncio.wait_for(orchestrator.communication_queue.get(), timeout=0.5)
                        
                        # Format communication event
                        event_data = {
                            'type': comm.get('type', 'unknown'),
                            'content': comm.get('content', ''),
                            'iteration': comm.get('iteration'),
                            'timestamp': comm.get('timestamp', '')
                        }
                        
                        # Add type-specific fields
                        if comm.get('type') == 'action':
                            event_data['tool_name'] = comm.get('tool_name')
                            event_data['tool_params'] = comm.get('tool_params')
                        elif comm.get('type') == 'observation':
                            event_data['tool_result'] = comm.get('tool_result')
                            event_data['is_error'] = comm.get('is_error', False)
                        elif comm.get('type') in ['reasoning', 'planning']:
                            event_data['strategy'] = comm.get('strategy')
                        
                        # Send SSE event immediately
                        logger.info(f"📤 Sending SSE event: {event_data['type']}")
                        yield f"data: {json.dumps(event_data)}\n\n"
                        
                    except asyncio.TimeoutError:
                        # No messages in queue - check if we need to send keepalive
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_keepalive >= keepalive_interval:
                            yield f": keepalive\n\n"
                            last_keepalive = current_time
                    except Exception as e:
                        logger.error(f"Error processing communication: {e}")
                else:
                    # No queue available yet, wait a bit
                    await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            logger.info("Agent communication stream cancelled")
        except Exception as e:
            logger.error(f"Error in agent communication stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
