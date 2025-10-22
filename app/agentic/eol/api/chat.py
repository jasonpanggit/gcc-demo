"""
Chat/AutoGen API Module

This module provides AI-powered conversational endpoints using AutoGen's
multi-agent orchestration system. Enables natural language interaction with
the EOL analysis system through intelligent agent coordination.

Key Features:
    - Multi-agent conversation orchestration
    - Confirmation workflows for complex operations
    - Full conversation transparency and history
    - Inventory-grounded responses
    - Timeout management and error handling

Endpoints:
    POST /api/autogen-chat - Main AutoGen chat endpoint with agent orchestration

Dependencies:
    - AutoGen agents.chat_orchestrator module
    - EOL orchestrator for inventory context
    - FastAPI async support

Author: GitHub Copilot
Date: October 2025
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils import get_logger
from utils.endpoint_decorators import with_timeout_and_stats
from utils.config import config

# Initialize logger
logger = get_logger(__name__)

# Create router for chat endpoints
router = APIRouter(tags=["AI Chat & Conversation"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AutoGenChatRequest(BaseModel):
    """Request model for AutoGen chat endpoint"""
    message: str
    use_autogen: Optional[bool] = True
    confirmed: Optional[bool] = False
    original_message: Optional[str] = None
    timeout_seconds: Optional[int] = 150  # Default 150 seconds timeout


class AutoGenChatResponse(BaseModel):
    """Response model for AutoGen chat with full conversation transparency"""
    response: str
    conversation_messages: List[dict]
    agent_communications: List[dict]
    agents_involved: List[str]
    total_exchanges: int
    session_id: str
    error: Optional[str] = None
    confirmation_required: Optional[bool] = False
    confirmation_declined: Optional[bool] = False
    pending_message: Optional[str] = None
    fast_path: Optional[bool] = False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_chat_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_chat_orchestrator, CHAT_AVAILABLE
    if not CHAT_AVAILABLE:
        return None
    return get_chat_orchestrator()


def _get_eol_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_eol_orchestrator
    return get_eol_orchestrator()


def clean_for_json(obj):
    """
    Clean data to ensure JSON serialization.
    
    Recursively processes objects to ensure all data is JSON-serializable
    and truncates very long strings to prevent parsing issues.
    
    Args:
        obj: Any Python object to clean
        
    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(item) for item in obj]
    elif isinstance(obj, str):
        # Truncate very long strings to prevent JSON parsing issues
        return obj[:10000] if len(obj) > 10000 else obj
    else:
        return str(obj) if obj is not None else None


# Global cache for inventory context (5 minute TTL)
_inventory_context_cache = {"data": None, "timestamp": None, "ttl": 300}


async def _get_optimized_inventory_context() -> str:
    """
    Get optimized inventory context for chat with caching and efficient processing.
    
    Provides a fast summary of inventory data suitable for chat context without
    performing full EOL analysis. Uses 5-minute caching to improve performance.
    
    Returns:
        str: Formatted inventory context string with summary statistics
    """
    try:
        # Check cache first (5 minute TTL)
        current_time = datetime.utcnow().timestamp()
        if (_inventory_context_cache["data"] and 
            _inventory_context_cache["timestamp"] and 
            (current_time - _inventory_context_cache["timestamp"]) < _inventory_context_cache["ttl"]):
            logger.info("📋 Using cached inventory context")
            return _inventory_context_cache["data"]
        
        # First check if we have valid Azure service configuration
        if not config.azure.log_analytics_workspace_id:
            logger.info("Log Analytics not configured - returning service status")
            context = "INVENTORY DATA STATUS: Azure Log Analytics Workspace not configured. Live inventory data unavailable."
            
            # Cache the response
            _inventory_context_cache["data"] = context
            _inventory_context_cache["timestamp"] = current_time
            return context
        
        # Quick connectivity check before full analysis
        try:
            orchestrator = _get_eol_orchestrator()
            
            # Use fast inventory summary for chat context (no EOL enrichment for speed)
            inventory_summary = await asyncio.wait_for(
                orchestrator.agents["inventory"].get_fast_inventory_summary(),
                timeout=15.0
            )
            
            # Also include a brief OS summary from the OS agent for richer grounding
            try:
                os_summary = await asyncio.wait_for(
                    orchestrator.agents["os_inventory"].get_os_summary(),
                    timeout=10.0
                )
            except Exception:
                os_summary = None
            
            # If we have a summary but no items, return status
            if inventory_summary.get('total_software_items', 0) == 0:
                return "INVENTORY DATA STATUS: No software inventory data found in Azure Log Analytics Workspace."
            
            # Generate optimized context from summary
            total_items = inventory_summary.get('total_software_items', 0)
            unique_computers = inventory_summary.get('unique_computers', 0)
            eol_stats = inventory_summary.get('eol_statistics', {})
            sample_items = inventory_summary.get('sample_items', [])
            
            # Create efficient context without full risk analysis
            context_lines = [
                f"LIVE INVENTORY SUMMARY:",
                f"Total Software Items: {total_items}",
                f"Unique Computers: {unique_computers}",
                f"EOL Analysis: {eol_stats.get('items_with_eol_data', 0)} items have EOL data",
                f"Risk Indicators: {eol_stats.get('items_past_eol', 0)} past EOL, {eol_stats.get('items_approaching_eol', 0)} approaching EOL",
                "",
            ]

            # Optionally include OS summary if available
            if os_summary:
                context_lines.extend([
                    "OPERATING SYSTEM SUMMARY:",
                    f"Computers Reported: {os_summary.get('total_computers', 0)}",
                    f"Windows: {os_summary.get('windows_count', 0)} • Linux: {os_summary.get('linux_count', 0)}",
                ])
                top_versions = ", ".join([f"{v.get('name_version')} ({v.get('count')})" for v in os_summary.get('top_versions', [])])
                if top_versions:
                    context_lines.append("Top OS Versions: " + top_versions)
                context_lines.append("")
            
            # Add top 5 sample items for context
            for item in sample_items[:5]:
                software_name = item.get('software_name', 'Unknown')
                version = item.get('software_version', 'N/A')
                computer = item.get('computer_name', 'Unknown')
                eol_date = item.get('eol_date', 'N/A')
                context_lines.append(f"- {software_name} {version} on {computer} (EOL: {eol_date})")
            
            context_lines.extend([
                "",
                "QUICK RECOMMENDATIONS:",
                "• Review items past EOL for immediate action",
                "• Plan upgrades for items approaching EOL",
                "• Ensure compliance for critical systems"
            ])
            
            context = "\n".join(context_lines)
            
            # Cache the successful response
            _inventory_context_cache["data"] = context
            _inventory_context_cache["timestamp"] = current_time
            
            return context
            
        except asyncio.TimeoutError:
            logger.warning("Inventory summary retrieval timed out")
            context = "INVENTORY DATA STATUS: Service timeout - unable to retrieve inventory data within time limit."
            
            # Cache timeout response for shorter period
            _inventory_context_cache["data"] = context
            _inventory_context_cache["timestamp"] = current_time
            _inventory_context_cache["ttl"] = 60  # 1 minute TTL for errors
            
            return context
            
    except Exception as e:
        logger.error(f"Error in optimized inventory context: {e}")
        return "INVENTORY DATA STATUS: Service error - unable to retrieve live inventory data."


async def _get_inventory_context() -> str:
    """
    Get detailed inventory context for chat with full EOL risk analysis.
    
    Performs comprehensive EOL risk analysis on inventory data. More expensive
    than _get_optimized_inventory_context() but provides detailed risk breakdown.
    
    Returns:
        str: Formatted inventory context with detailed risk analysis
    """
    try:
        analysis = await _get_eol_orchestrator().analyze_inventory_eol_risks()
        
        risk_summary = analysis.get('risk_summary', {})
        software_list = analysis.get('software_analysis', [])
        recommendations = analysis.get('recommendations', [])
        
        # Create detailed software inventory context
        software_details = []
        for software in software_list[:10]:
            software_name = software.get('software_name', 'Unknown')
            version = software.get('version', 'N/A')
            computer = software.get('computer', 'Unknown')
            risk_level = software.get('risk_level', 'unknown')
            eol_date = software.get('eol_date', 'N/A')
            software_details.append(f"- {software_name} {version} on {computer} (Risk: {risk_level}, EOL: {eol_date})")
        
        return f"""
CURRENT SOFTWARE INVENTORY ANALYSIS:
Total Software Items: {analysis.get('analyzed_count', 0)}
Risk Breakdown: Critical={risk_summary.get('critical', 0)}, High={risk_summary.get('high', 0)}, Medium={risk_summary.get('medium', 0)}, Low={risk_summary.get('low', 0)}

TOP SOFTWARE INVENTORY:
{chr(10).join(software_details[:10])}

KEY RECOMMENDATIONS:
{chr(10).join([f"• {rec}" for rec in recommendations[:5]])}
"""
    except Exception as e:
        logger.warning(f"Could not get inventory context: {e}")
        return "INVENTORY DATA STATUS: Unable to retrieve live inventory data."


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================

@router.post("/api/autogen-chat", response_model=AutoGenChatResponse)
@with_timeout_and_stats(
    agent_name="autogen_chat",
    timeout_seconds=180,  # 3 minutes for complex multi-agent conversations
    track_cache=False,  # Don't track cache stats for chat
    auto_wrap_response=False  # Use custom AutoGenChatResponse model
)
async def autogen_chat(req: AutoGenChatRequest):
    """
    AutoGen-powered multi-agent conversation endpoint.
    
    Enables transparent agent-to-agent communication for inventory and EOL analysis
    using AutoGen's multi-agent orchestration. Supports confirmation workflows for
    complex operations and provides full conversation transparency.
    
    The endpoint orchestrates multiple specialized agents:
    - OSInventoryAnalyst: Discovers and analyzes operating systems
    - SoftwareInventoryAnalyst: Discovers and analyzes software installations
    - Microsoft/Python/NodeJS/etc EOL Specialists: Check EOL dates for specific technologies
    - WebSurfer: Performs web searches for EOL information
    
    Features:
    - **Natural Language**: Accepts conversational queries about inventory and EOL
    - **Confirmation Workflow**: Requests confirmation for destructive operations
    - **Full Transparency**: Returns complete agent conversation history
    - **Timeout Management**: Configurable timeouts with safety buffers
    - **Error Handling**: Graceful degradation with helpful error messages
    
    Args:
        req: AutoGenChatRequest containing:
            - message: Natural language query or command
            - timeout_seconds: Max time for operation (default: 150s)
            - confirmed: Whether user confirmed a previous operation
            - original_message: Original message if this is a confirmation response
    
    Returns:
        AutoGenChatResponse with:
            - response: Human-readable response text
            - conversation_messages: Full AutoGen conversation history
            - agent_communications: Inter-agent communication log
            - agents_involved: List of agents that participated
            - total_exchanges: Number of agent-to-agent exchanges
            - session_id: Unique session identifier
            - confirmation_required: Whether confirmation is needed
            - error: Error message if operation failed
    
    Raises:
        HTTPException: 503 if chat orchestrator unavailable
        HTTPException: 408 if operation times out
    
    Example Request:
        {
            "message": "Show me all Windows Server 2016 installations",
            "timeout_seconds": 120
        }
    
    Example Response:
        {
            "response": "Found 5 Windows Server 2016 installations across 3 computers...",
            "conversation_messages": [...],
            "agent_communications": [...],
            "agents_involved": ["OSInventoryAnalyst", "MicrosoftEOLSpecialist"],
            "total_exchanges": 12,
            "session_id": "chat_20251015_143022_abc123"
        }
    
    Note:
        This endpoint uses a custom response model (AutoGenChatResponse) rather than
        StandardResponse to support detailed conversation tracking and agent transparency.
    """
    # Check if chat orchestrator is available
    from main import CHAT_AVAILABLE
    
    if not CHAT_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="Chat orchestrator is not available. Multi-agent chat functionality requires the chat_orchestrator module."
        )
    
    # Get the chat orchestrator instance
    chat_orch = _get_chat_orchestrator()
    if chat_orch is None:
        raise HTTPException(
            status_code=503, 
            detail="Chat orchestrator is not available. Multi-agent chat functionality requires the chat_orchestrator module."
        )
    
    logger.info(f"🤖 AutoGen Chat Request: {req.message[:100]}... (timeout: {req.timeout_seconds}s)")
    
    # Start multi-agent conversation with confirmation support and timeout
    # Use the minimum of the FastAPI timeout (3 minutes) and the requested timeout
    effective_timeout = min(req.timeout_seconds, 170)  # Leave 10s buffer for FastAPI
    
    try:
        result = await asyncio.wait_for(
            chat_orch.chat_with_confirmation(
                req.message, 
                confirmed=req.confirmed or False,
                original_message=req.original_message,
                timeout_seconds=req.timeout_seconds
            ),
            timeout=effective_timeout + 10  # Add buffer for FastAPI timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"❌ AutoGen Chat Timeout after {effective_timeout}s")
        raise HTTPException(
            status_code=408,
            detail=f"Chat operation timed out after {effective_timeout} seconds. Try a more specific query or increase timeout."
        )

    # Ensure all data is JSON serializable and limit size to prevent parsing issues
    cleaned_result = clean_for_json(result)
    
    # Return full conversation transparency with increased limits for inventory data
    response = AutoGenChatResponse(
        response=cleaned_result.get("response", "No response generated")[:100000],  # Increased limit for large inventories
        conversation_messages=cleaned_result.get("conversation_messages", [])[:200],  # Increased message count
        agent_communications=cleaned_result.get("agent_communications", [])[-100:],  # Last 100 communications
        agents_involved=cleaned_result.get("agents_involved", [])[:20],  # Increased agent list
        total_exchanges=cleaned_result.get("total_exchanges", 0),
        session_id=cleaned_result.get("session_id", "unknown"),
        error=cleaned_result.get("error"),
        confirmation_required=cleaned_result.get("confirmation_required", False),
        confirmation_declined=cleaned_result.get("confirmation_declined", False),
        pending_message=cleaned_result.get("pending_message"),
        fast_path=cleaned_result.get("fast_path", False)
    )
    
    logger.info(f"✅ AutoGen Chat Complete - Agents: {response.agents_involved}, Exchanges: {response.total_exchanges}")
    logger.info(f"[DEBUG] Agent communications count: {len(response.agent_communications)}")
    logger.info(f"[DEBUG] Raw agents_involved from result: {cleaned_result.get('agents_involved', [])}")
    if response.agent_communications:
        logger.info(f"[DEBUG] First agent communication: {response.agent_communications[0]}")
        # Debug: show agent_name field specifically
        first_comm = response.agent_communications[0]
        if isinstance(first_comm, dict) and 'agent_name' in first_comm:
            logger.info(f"[DEBUG] First agent_name: {first_comm['agent_name']}")
    
    return response


# Chat API module complete - single powerful endpoint for multi-agent conversations
