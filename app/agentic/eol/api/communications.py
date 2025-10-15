"""
Communications API Module

This module provides endpoints for managing and retrieving communication logs from
the EOL and Chat orchestrators, including real-time agent interaction history.

Features:
- EOL orchestrator communication logs
- Chat orchestrator communication logs
- Session-based communication filtering
- Communication log clearing
- Agent-to-agent interaction tracking
- Debug endpoints for troubleshooting

Endpoints:
    GET  /api/communications/eol - Get EOL orchestrator communications
    GET  /api/communications/chat - Get chat orchestrator communications
    POST /api/communications/clear - Clear EOL orchestrator communications
    POST /api/communications/chat/clear - Clear chat orchestrator communications
    GET  /api/agent-communications/{session_id} - Get session-specific communications
    GET  /api/debug/agent-communications - Debug all agent communications
"""

from fastapi import APIRouter
from datetime import datetime
import logging

from utils.endpoint_decorators import readonly_endpoint, write_endpoint
from utils.standard_response import StandardResponse
from main import get_eol_orchestrator, get_chat_orchestrator, CHAT_AVAILABLE

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/communications/eol", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_communications", timeout_seconds=15)
async def get_eol_communications():
    """
    Get real-time EOL orchestrator communications log.
    
    Retrieves the recent communication history from the EOL orchestrator,
    including agent interactions, search queries, and response details.
    
    Returns:
        StandardResponse with list of recent communications from EOL orchestrator.
        
    Example Response:
        {
            "success": true,
            "communications": [
                {
                    "timestamp": "2025-01-15T10:30:00Z",
                    "agent": "microsoft_agent",
                    "query": "Windows Server 2012",
                    "response": {...}
                }
            ],
            "count": 15,
            "timestamp": "2025-01-15T10:35:00Z"
        }
    """
    orchestrator = get_eol_orchestrator()
    if hasattr(orchestrator, 'get_recent_communications'):
        communications = orchestrator.get_recent_communications()
        return {
            "success": True,
            "communications": communications,
            "count": len(communications),
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "success": False,
            "error": "Communications not available",
            "communications": [],
            "count": 0
        }


@router.get("/api/communications/chat", response_model=StandardResponse)
@readonly_endpoint(agent_name="chat_communications", timeout_seconds=15)
async def get_chat_communications():
    """
    Get real-time chat orchestrator communications log.
    
    Retrieves the communication history from the chat orchestrator,
    including agent interactions and OpenAI API calls.
    
    Returns:
        StandardResponse with list of recent communications from chat orchestrator.
        
    Example Response:
        {
            "success": true,
            "communications": [
                {
                    "timestamp": "2025-01-15T10:30:00Z",
                    "sender": "user_proxy",
                    "recipient": "assistant",
                    "content": "Search for Windows 10 EOL date"
                }
            ],
            "count": 25,
            "timestamp": "2025-01-15T10:35:00Z"
        }
    """
    orchestrator = get_chat_orchestrator()
    if orchestrator and hasattr(orchestrator, 'get_agent_communications'):
        communications = await orchestrator.get_agent_communications()
        return {
            "success": True,
            "communications": communications,
            "count": len(communications),
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "success": False,
            "error": "Chat orchestrator not available or communications not supported",
            "communications": [],
            "count": 0
        }


@router.post("/api/communications/clear", response_model=StandardResponse)
@write_endpoint(agent_name="communications_clear", timeout_seconds=10)
async def clear_communications():
    """
    Clear orchestrator communications log.
    
    Removes all communications from the EOL orchestrator's internal log,
    useful for debugging or starting fresh with a clean state.
    
    Returns:
        StandardResponse with clear operation results.
        
    Example Response:
        {
            "success": true,
            "message": "Communications cleared successfully",
            "cleared_count": 42
        }
    """
    result = get_eol_orchestrator().clear_communications()
    logger.info("Communications cleared: %s", result)
    return result


@router.post("/api/communications/chat/clear", response_model=StandardResponse)
@write_endpoint(agent_name="clear_chat_comms", timeout_seconds=30)
async def clear_chat_communications():
    """
    Clear chat orchestrator communications log.
    
    Removes all communication history from the chat orchestrator,
    freeing up memory and resetting the conversation context.
    
    Returns:
        StandardResponse indicating success of the clear operation.
        
    Example Response:
        {
            "success": true,
            "message": "Chat communications cleared successfully"
        }
    """
    orchestrator = get_chat_orchestrator()
    if orchestrator and hasattr(orchestrator, 'clear_communications'):
        result = await orchestrator.clear_communications()
        logger.info("Chat communications cleared: %s", result)
        return result
    else:
        return {
            "success": False,
            "error": "Chat orchestrator not available or clear not supported"
        }


@router.get("/api/agent-communications/{session_id}", response_model=StandardResponse)
@readonly_endpoint(agent_name="agent_communications", timeout_seconds=15)
async def get_agent_communications(session_id: str):
    """
    Get agent communication history for a specific session.
    
    Retrieves all agent-to-agent communications for a specific chat session,
    useful for debugging AutoGen conversations and understanding agent interactions.
    
    Args:
        session_id: Unique identifier for the chat session
    
    Returns:
        StandardResponse with filtered communications for the session and debug info.
        
    Example Request:
        GET /api/agent-communications/session-abc123
        
    Example Response:
        {
            "session_id": "session-abc123",
            "communications": [
                {
                    "timestamp": "2025-01-15T10:30:00Z",
                    "sender": "user_proxy",
                    "recipient": "assistant",
                    "content": "Search for Ubuntu 18.04 EOL",
                    "session_id": "session-abc123"
                }
            ],
            "total_count": 8,
            "all_communications_count": 50,
            "debug_all_communications": [...]
        }
    """
    if not CHAT_AVAILABLE:
        return {"error": "Chat orchestrator not available in EOL interface", "communications": []}
    
    # Get the chat orchestrator instance
    chat_orch = get_chat_orchestrator()
    if chat_orch is None:
        return {"error": "Chat orchestrator not available in EOL interface", "communications": []}
    
    # Get ALL communications for debugging
    all_communications = await chat_orch.get_agent_communications()
    
    # Filter communications by session_id
    session_communications = [
        comm for comm in all_communications 
        if comm.get("session_id") == session_id
    ]
    
    return {
        "session_id": session_id,
        "communications": session_communications,
        "total_count": len(session_communications),
        "all_communications_count": len(all_communications),
        "debug_all_communications": all_communications[-5:] if all_communications else []  # Last 5 for debugging
    }


@router.get("/api/debug/agent-communications", response_model=StandardResponse)
@readonly_endpoint(agent_name="debug_agent_communications", timeout_seconds=15)
async def debug_agent_communications():
    """
    Debug endpoint to check all agent communications across all sessions.
    
    Returns complete history of agent-to-agent communications from AutoGen
    chat orchestrator, useful for troubleshooting and monitoring agent interactions.
    
    Returns:
        StandardResponse with all communications and orchestrator session info.
        
    Example Response:
        {
            "total_communications": 150,
            "communications": [
                {
                    "timestamp": "2025-01-15T10:30:00Z",
                    "sender": "user_proxy",
                    "recipient": "assistant",
                    "content": "...",
                    "session_id": "session-abc123"
                }
            ],
            "orchestrator_session_id": "main-session-xyz"
        }
    """
    if not CHAT_AVAILABLE:
        return {"error": "Chat orchestrator not available in EOL interface", "communications": []}
    
    # Get the chat orchestrator instance
    chat_orch = get_chat_orchestrator()
    if chat_orch is None:
        return {"error": "Chat orchestrator not available in EOL interface", "communications": []}
    
    all_communications = await chat_orch.get_agent_communications()
    
    return {
        "total_communications": len(all_communications),
        "communications": all_communications,
        "orchestrator_session_id": chat_orch.session_id if hasattr(chat_orch, 'session_id') else 'unknown'
    }
