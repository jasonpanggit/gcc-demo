"""
Agent Management API Module

This module provides endpoints for managing and configuring EOL search agents.
Agents are specialized components that query different EOL data sources
(Microsoft, Red Hat, endoflife.date, etc.).

Key Features:
    - Agent status and health monitoring
    - Comprehensive agent listing with statistics
    - Dynamic URL configuration per agent
    - Agent enable/disable functionality
    - Agent usage statistics tracking

Endpoints:
    GET  /api/agents/status - Get health status of all agents
    GET  /api/agents/list - List all agents with URLs and statistics
    POST /api/agents/add-url - Add URL to agent configuration
    POST /api/agents/remove-url - Remove URL from agent
    POST /api/agents/toggle - Enable/disable specific agent

Author: GitHub Copilot
Date: October 2025
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
import logging

from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    readonly_endpoint,
    write_endpoint
)

logger = logging.getLogger(__name__)

# Import main module dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import get_eol_orchestrator

# Create router for agent endpoints
router = APIRouter(tags=["Agent Management"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AgentUrlRequest(BaseModel):
    """Request model for adding/removing agent URLs"""
    agent_name: str
    url: str
    description: Optional[str] = None


class AgentToggleRequest(BaseModel):
    """Request model for toggling agent status"""
    agent_name: str
    active: bool


# ============================================================================
# AGENT STATUS & LISTING ENDPOINTS
# ============================================================================

@router.get("/api/agents/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="agents_status", timeout_seconds=20)
async def agents_status():
    """
    Get readiness/health of all registered agents.
    
    Returns status information for all agents in the EOL orchestrator including
    inventory agents, EOL search agents, and specialized agents.
    
    Returns:
        StandardResponse with agent health status, capabilities, and availability.
    
    Example Response:
        {
            "success": true,
            "agents": {
                "microsoft_lifecycle": {
                    "status": "healthy",
                    "initialized": true,
                    "capabilities": ["windows", "sql_server"],
                    "last_used": "2025-10-15T12:00:00Z"
                },
                "redhat_lifecycle": {
                    "status": "healthy",
                    "initialized": true,
                    "capabilities": ["rhel", "centos"]
                }
            },
            "total_agents": 8,
            "healthy_agents": 7
        }
    """
    return await get_eol_orchestrator().get_agents_status()


@router.get("/api/agents/list", response_model=StandardResponse)
@readonly_endpoint(agent_name="list_agents", timeout_seconds=20)
async def list_agents():
    """
    Get list of all agents with their statistics and URLs.
    
    Retrieves comprehensive information about all registered EOL agents including:
    - Usage statistics (count, confidence, last used)
    - Configured URLs with descriptions and priorities
    - Active/inactive status
    - Agent type information
    
    Returns:
        StandardResponse with dictionary of agent configurations keyed by agent name.
    
    Example Response:
        {
            "success": true,
            "agents": {
                "microsoft_lifecycle": {
                    "statistics": {
                        "usage_count": 125,
                        "average_confidence": 0.92,
                        "last_used": "2025-10-15T12:00:00Z"
                    },
                    "urls": [
                        {
                            "url": "https://learn.microsoft.com/lifecycle",
                            "description": "Microsoft Product Lifecycle",
                            "active": true,
                            "priority": 1
                        }
                    ],
                    "active": true,
                    "type": "MicrosoftLifecycleAgent"
                }
            }
        }
    """
    orchestrator = get_eol_orchestrator()
    agents_data = {}
    
    # Get agent statistics and configuration
    for agent_name, agent in orchestrator.agents.items():
        # Get basic statistics
        stats = {
            "usage_count": getattr(agent, 'usage_count', 0),
            "average_confidence": getattr(agent, 'average_confidence', 0.0),
            "last_used": getattr(agent, 'last_used', None)
        }
        
        # Get agent URLs - try multiple methods
        urls = []
        
        # Method 1: Use get_urls() method if available (for some EOL agents)
        if hasattr(agent, 'get_urls') and callable(getattr(agent, 'get_urls')):
            try:
                urls = agent.get_urls()
            except Exception as e:
                logger.debug(f"Error calling get_urls() for {agent_name}: {e}")
        
        # Method 2: Use urls property if available (for most EOL agents)
        elif hasattr(agent, 'urls') and agent.urls:
            try:
                urls_data = agent.urls
                # If it's already a list of dictionaries, use it directly
                if isinstance(urls_data, list):
                    urls = urls_data
                else:
                    urls = [urls_data]  # Wrap single URL in list
            except Exception as e:
                logger.debug(f"Error accessing urls property for {agent_name}: {e}")
        
        # Method 3: Check for eol_urls dictionary (fallback)
        elif hasattr(agent, 'eol_urls') and agent.eol_urls:
            try:
                # Convert eol_urls dictionary to URL list with metadata
                urls = []
                for key, url_data in agent.eol_urls.items():
                    if isinstance(url_data, dict) and 'url' in url_data:
                        urls.append({
                            'url': url_data['url'],
                            'description': url_data.get('description', f'{key.title()} EOL Information'),
                            'active': url_data.get('active', True),
                            'priority': url_data.get('priority', 1)
                        })
                    elif isinstance(url_data, str):
                        urls.append({
                            'url': url_data,
                            'description': f'{key.title()} EOL Information',
                            'active': True,
                            'priority': 1
                        })
            except Exception as e:
                logger.debug(f"Error extracting eol_urls for {agent_name}: {e}")
        
        # Method 4: Legacy fallbacks
        elif hasattr(agent, 'base_url') and agent.base_url:
            urls = [{'url': agent.base_url, 'description': 'Base URL', 'active': True, 'priority': 1}]
        elif hasattr(agent, 'api_url') and agent.api_url:
            urls = [{'url': agent.api_url, 'description': 'API URL', 'active': True, 'priority': 1}]
        
        # Get agent status
        active = getattr(agent, 'active', True)
        
        agents_data[agent_name] = {
            "statistics": stats,
            "urls": urls,
            "active": active,
            "type": type(agent).__name__
        }
    
    return {
        "success": True,
        "agents": agents_data
    }


# ============================================================================
# AGENT CONFIGURATION ENDPOINTS
# ============================================================================

@router.post("/api/agents/add-url", response_model=StandardResponse)
@write_endpoint(agent_name="add_agent_url", timeout_seconds=30)
async def add_agent_url(request: AgentUrlRequest):
    """
    Add URL to an agent's configuration.
    
    Adds a new URL endpoint to the specified agent's list of EOL data sources.
    Checks for duplicates before adding. URL can include optional description.
    
    Args:
        request: AgentUrlRequest with agent name, URL, and optional description
    
    Returns:
        StandardResponse indicating success or failure with appropriate message.
    
    Example Request:
        {
            "agent_name": "microsoft_lifecycle",
            "url": "https://learn.microsoft.com/lifecycle/api/v2",
            "description": "Microsoft Lifecycle API v2"
        }
    
    Example Response:
        {
            "success": true,
            "message": "URL added to microsoft_lifecycle"
        }
    """
    orchestrator = get_eol_orchestrator()
    
    if request.agent_name not in orchestrator.agents:
        return {
            "success": False,
            "error": f"Agent '{request.agent_name}' not found"
        }
    
    agent = orchestrator.agents[request.agent_name]
    
    # Initialize URLs list if it doesn't exist
    if not hasattr(agent, 'urls'):
        agent.urls = []
    
    # Add URL (check for duplicates)
    url_entry = {
        "url": request.url,
        "description": request.description or ""
    } if request.description else request.url
    
    if request.url not in [u["url"] if isinstance(u, dict) else u for u in agent.urls]:
        agent.urls.append(url_entry)
        logger.info(f"Added URL {request.url} to agent {request.agent_name}")
        
        return {
            "success": True,
            "message": f"URL added to {request.agent_name}"
        }
    else:
        return {
            "success": False,
            "error": "URL already exists for this agent"
        }


@router.post("/api/agents/remove-url", response_model=StandardResponse)
@write_endpoint(agent_name="remove_agent_url", timeout_seconds=30)
async def remove_agent_url(request: AgentUrlRequest):
    """
    Remove URL from an agent's configuration.
    
    Removes the specified URL from the agent's list of EOL data sources.
    Returns error if agent or URL not found.
    
    Args:
        request: AgentUrlRequest with agent name and URL to remove
    
    Returns:
        StandardResponse indicating success or failure with appropriate message.
    
    Example Request:
        {
            "agent_name": "microsoft_lifecycle",
            "url": "https://old-endpoint.microsoft.com"
        }
    
    Example Response:
        {
            "success": true,
            "message": "URL removed from microsoft_lifecycle"
        }
    """
    orchestrator = get_eol_orchestrator()
    
    if request.agent_name not in orchestrator.agents:
        return {
            "success": False,
            "error": f"Agent '{request.agent_name}' not found"
        }
    
    agent = orchestrator.agents[request.agent_name]
    
    if not hasattr(agent, 'urls') or not agent.urls:
        return {
            "success": False,
            "error": "No URLs configured for this agent"
        }
    
    # Remove URL
    original_count = len(agent.urls)
    agent.urls = [u for u in agent.urls if (u["url"] if isinstance(u, dict) else u) != request.url]
    
    if len(agent.urls) < original_count:
        logger.info(f"Removed URL {request.url} from agent {request.agent_name}")
        return {
            "success": True,
            "message": f"URL removed from {request.agent_name}"
        }
    else:
        return {
            "success": False,
            "error": "URL not found for this agent"
        }


@router.post("/api/agents/toggle", response_model=StandardResponse)
@write_endpoint(agent_name="toggle_agent", timeout_seconds=30)
async def toggle_agent(request: AgentToggleRequest):
    """
    Toggle agent active/inactive status.
    
    Enables or disables the specified agent. Disabled agents are not used
    for EOL lookups. Useful for temporarily removing problematic agents
    without deleting their configuration.
    
    Args:
        request: AgentToggleRequest with agent name and active status (true/false)
    
    Returns:
        StandardResponse indicating success with status message.
    
    Example Request:
        {
            "agent_name": "microsoft_lifecycle",
            "active": false
        }
    
    Example Response:
        {
            "success": true,
            "message": "Agent microsoft_lifecycle disabled"
        }
    """
    orchestrator = get_eol_orchestrator()
    
    if request.agent_name not in orchestrator.agents:
        return {
            "success": False,
            "error": f"Agent '{request.agent_name}' not found"
        }
    
    agent = orchestrator.agents[request.agent_name]
    agent.active = request.active
    
    status = "enabled" if request.active else "disabled"
    logger.info(f"Agent {request.agent_name} {status}")
    
    return {
        "success": True,
        "message": f"Agent {request.agent_name} {status}"
    }
