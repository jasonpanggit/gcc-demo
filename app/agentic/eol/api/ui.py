"""
HTML UI Endpoints Module

This module provides HTML template-based user interface endpoints for the EOL
Multi-Agent Application. Each endpoint serves a different page of the web UI:

- Homepage (/) - Main dashboard
- Inventory (/inventory) - Software/OS inventory management
- EOL Search (/eol-search) - End-of-life date lookup
- EOL History (/eol-searches) - Historical search results
- Inventory Assistant (/inventory-assistant) - Agent Framework conversational interface
- Alerts (/alerts) - Alert configuration and management
- Cache (/cache) - Cache statistics and management
- Cache Details (/agent-cache-details) - Detailed per-agent cache metrics
- Agents (/agents) - Agent configuration management
- Visualizations (/visualizations) - Data visualization demos and showcase

All endpoints return HTMLResponse with rendered Jinja2 templates.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import TemplateNotFound

# Import decorators and utilities
from utils.endpoint_decorators import with_timeout_and_stats
from utils.cache_stats_manager import cache_stats_manager
from utils.config import config

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Create router
router = APIRouter(tags=["UI & HTML Pages"])


@router.get("/", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="index_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def index(request: Request):
    """
    Main dashboard landing page (fast route for warm-up).
    
    Serves the primary application dashboard with minimal processing
    to ensure fast initial page load times.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered index.html template.
    """
    try:
        return templates.TemplateResponse(request, "index.html")
    except Exception:
        return HTMLResponse("EOL Multi-Agent App", status_code=200)


@router.get("/inventory", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="inventory_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def inventory_ui(request: Request):
    """
    Inventory management page.
    
    Serves the software and OS inventory management interface with Azure
    integration details.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered inventory.html template and Azure config.
    """
    try:
        return templates.TemplateResponse(request, "inventory.html", {
            "subscription_id": config.azure.subscription_id,
            "resource_group": config.azure.resource_group_name
        })
    except TemplateNotFound:
        logger.warning("Inventory template not found; returning fallback HTML")
        content = "<h1>Inventory</h1><p>Template not available in this environment.</p>"
        return HTMLResponse(content, status_code=200)


@router.get("/eol-search", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="eol_search_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def eol_ui(request: Request):
    """
    EOL search page.
    
    Serves the end-of-life search interface for querying software lifecycle
    information across multiple agent sources.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered eol.html template.
    """
    try:
        return templates.TemplateResponse(request, "eol.html")
    except TemplateNotFound:
        logger.warning("EOL template not found; returning fallback HTML")
        return HTMLResponse("<h1>EOL Search</h1><p>Template unavailable.</p>", status_code=200)


@router.get("/eol-searches", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="eol_history_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def eol_searches_ui(request: Request):
    """
    EOL search history page.
    
    Serves the historical EOL search results interface for reviewing
    past queries and cached responses.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered eol-searches.html template.
    """
    return templates.TemplateResponse(request, "eol-searches.html")


@router.get("/eol-inventory", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="eol_inventory_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def eol_inventory_ui(request: Request):
    """EOL Cosmos inventory browser page."""
    return templates.TemplateResponse(request, "eol-inventory.html")


@router.get("/eol-management", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="eol_management_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def eol_management_ui(request: Request):
    """OS EOL management dashboard with tables and charts."""
    return templates.TemplateResponse(request, "eol-management.html")


@router.get("/inventory-assistant", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="inventory_assistant_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def inventory_assistant_ui(request: Request):
    """
    Inventory assistant interface page.
    
    Serves the Microsoft Agent Framework conversational interface for natural language
    queries about inventory and EOL information.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered inventory_asst.html template.
    """
    return templates.TemplateResponse(request, "inventory_asst.html")


@router.get("/alerts", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="alerts_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def get_alerts_page(request: Request):
    """
    Alert management interface page.
    
    Serves the alerts configuration and management UI for configuring
    email notifications and alert thresholds.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered alerts.html template.
    """
    try:
        return templates.TemplateResponse(request, "alerts.html")
    except TemplateNotFound:
        logger.warning("Alerts template not found; returning fallback HTML")
        return HTMLResponse("<h1>Alerts</h1><p>Template unavailable.</p>", status_code=200)
    except Exception as e:
        logger.error(f"❌ Error serving alerts page: {e}")
        return HTMLResponse("<h1>Alerts</h1><p>Error loading page.</p>", status_code=200)


@router.get("/cache", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="cache_page",
    timeout_seconds=15,
    track_cache=False,
    auto_wrap_response=False
)
async def cache_ui(request: Request):
    """
    Cache management interface page with enhanced agent statistics.
    
    Serves the cache management dashboard showing agent-level cache statistics,
    inventory cache status, Cosmos DB cache info, and performance metrics.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered cache.html template and comprehensive cache stats.
    """
    try:
        # Get comprehensive cache statistics
        all_stats = cache_stats_manager.get_all_statistics()
        
        # Get agent stats (UI will handle display name conversion)
        agents_stats = all_stats.get("agent_stats", {})
        
        # Restructure for template compatibility
        cache_stats = {
            "agents": agents_stats,
            "inventory": all_stats.get("inventory_stats", {}),
            "cosmos": all_stats.get("cosmos_stats", {}),
            "performance": all_stats.get("performance_summary", {}),
            "last_updated": all_stats.get("last_updated")
        }
        
        return templates.TemplateResponse(request, "cache.html", {
            "cache_stats": cache_stats
        })
    except TemplateNotFound:
        logger.warning("Cache template not found; returning fallback HTML")
        return HTMLResponse("<h1>Cache Dashboard</h1><p>Template unavailable.</p>", status_code=200)
    except Exception as e:
        logger.error(f"Error loading cache UI: {e}")
        return HTMLResponse(f"<h1>Cache Dashboard</h1><p>{e}</p>", status_code=200)


@router.get("/agent-cache-details", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="agent_cache_details_page",
    timeout_seconds=15,
    track_cache=False,
    auto_wrap_response=False
)
async def agent_cache_details(request: Request, agent_name: Optional[str] = None):
    """
    Agent cache details page with granular URL performance monitoring.
    
    Serves detailed cache statistics for individual agents including URL-level
    performance metrics, hit rates, and response times.
    
    Args:
        request: FastAPI Request object
        agent_name: Optional agent name to filter statistics
    
    Returns:
        HTMLResponse with rendered agent-cache-details.html template and agent stats.
    """
    try:
        # Get detailed agent statistics
        all_stats = cache_stats_manager.get_all_statistics()
        agent_stats_data = all_stats.get("agent_stats", {})
        
        # If specific agent requested, filter to that agent
        if agent_name:
            # Use the agent name directly (no conversion needed - UI will handle display names)
            agent_name_normalized = agent_name.lower().replace(' ', '_').replace('-', '_')
            
            if agent_name_normalized in agent_stats_data.get("agents", {}):
                filtered_stats = {
                    "agents": {agent_name_normalized: agent_stats_data["agents"][agent_name_normalized]},
                    "summary": agent_stats_data.get("summary", {})
                }
            else:
                filtered_stats = {"error": f"Agent '{agent_name}' not found"}
        else:
            filtered_stats = agent_stats_data.copy()
        
        return templates.TemplateResponse(request, "agent-cache-details.html", {
            "agent_stats": filtered_stats,
            "selected_agent": agent_name
        })
    except Exception as e:
        logger.error(f"Error loading agent cache details: {e}")
        return templates.TemplateResponse(request, "agent-cache-details.html", {
            "agent_stats": {"error": str(e)},
            "selected_agent": agent_name
        })


@router.get("/agents", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="agents_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def agent_management_ui(request: Request):
    """
    Agent management interface page.
    
    Serves the agent configuration UI for managing EOL agents, custom URLs,
    and agent enable/disable settings.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        HTMLResponse with rendered agents.html template.
    """
    return templates.TemplateResponse(request, "agents.html")


@router.get("/azure-mcp", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="azure_mcp_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def azure_mcp_ui(request: Request):
    """
    Azure MCP Server integration page.

    Serves the Azure MCP Server management interface for interacting with
    Azure resources through the Model Context Protocol.

    Args:
        request: FastAPI Request object

    Returns:
        HTMLResponse with rendered azure-mcp.html template.
    """
    return templates.TemplateResponse(request, "azure-mcp.html")


@router.get("/azure-ai-sre", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="azure_ai_sre_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def azure_ai_sre_ui(request: Request):
    """
    Azure AI SRE Agent page.

    Serves the Azure AI SRE Agent interface for intelligent Site Reliability
    Engineering operations powered by Azure AI Agent Service (gccsreagent).

    Args:
        request: FastAPI Request object

    Returns:
        HTMLResponse with rendered azure-ai-sre.html template.
    """
    return templates.TemplateResponse(request, "azure-ai-sre.html")


@router.get("/resource-inventory", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="resource_inventory_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def resource_inventory_ui(request: Request):
    """
    Azure Resource Inventory Browser page.

    Serves the resource inventory management interface for browsing, filtering,
    and exploring Azure resources discovered via Azure Resource Graph with
    dual-layer caching (L1 in-memory + L2 Cosmos DB).

    Args:
        request: FastAPI Request object

    Returns:
        HTMLResponse with rendered resource_inventory.html template.
    """
    return templates.TemplateResponse(request, "resource_inventory.html")


@router.get("/visualizations", response_class=HTMLResponse)
@with_timeout_and_stats(
    agent_name="visualizations_page",
    timeout_seconds=10,
    track_cache=False,
    auto_wrap_response=False
)
async def visualizations_ui(request: Request):
    """
    Data Visualizations Demo page.

    Serves a comprehensive showcase of enhanced data visualizations including:
    - Chart.js themed charts
    - Sparklines for inline data display
    - Agent metrics dashboard
    - Token usage analytics
    - EOL risk heatmaps

    Args:
        request: FastAPI Request object

    Returns:
        HTMLResponse with rendered visualizations.html template.
    """
    return templates.TemplateResponse(request, "visualizations.html")
