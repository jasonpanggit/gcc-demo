"""
EOL Multi-Agent Application - Optimized Main Module
Provides REST API endpoints for software inventory and EOL analysis
"""
import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

# Import utilities and configuration
from utils import get_logger, config, create_error_response
from utils.cosmos_cache import base_cosmos
from utils.cache_stats_manager import cache_stats_manager
from utils.response_models import StandardResponse, ensure_standard_format
from utils.endpoint_decorators import (
    with_timeout_and_stats,
    standard_endpoint,
    readonly_endpoint,
    write_endpoint
)

# Initialize logger first
logger = get_logger(__name__, config.app.log_level)

# Import multi-agent systems
from agents.eol_orchestrator import EOLOrchestratorAgent
from utils.eol_cache import eol_cache

# Note: Chat orchestrator is available in separate chat.html interface
# This EOL interface uses the standard EOL orchestrator only
CHAT_AVAILABLE = False  # Chat functionality is in separate chat interface

# Create FastAPI app
app = FastAPI(
    title=config.app.title,
    version=config.app.version
)

# Configure logging to prevent duplicate log messages
import logging

# Check if logging is already configured to prevent duplicate handlers  
root_logger = logging.getLogger()
if not root_logger.handlers:
    # Configure root logger only if not already configured
    if os.environ.get('WEBSITE_SITE_NAME'):
        # Running in Azure App Service
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stderr
        )
        
        # Set uvicorn loggers to use stderr
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        uvicorn_logger.handlers = [logging.StreamHandler(sys.stderr)]
        uvicorn_access_logger.handlers = [logging.StreamHandler(sys.stderr)]
    else:
        # Local development - set up basic console logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
    
    # Suppress Azure SDK HTTP logging to reduce noise
    azure_loggers = [
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.core",
        "azure.cosmos",
        "urllib3.connectionpool"
    ]
    for azure_logger_name in azure_loggers:
        azure_logger = logging.getLogger(azure_logger_name)
        azure_logger.setLevel(logging.WARNING)
    
    logger.info("🔧 Azure App Service logging configured - logs will appear in App Service log stream")
else:
    # Also suppress Azure SDK logging in local development
    import logging
    azure_loggers = [
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.core",
        "azure.cosmos",
        "urllib3.connectionpool"
    ]
    for azure_logger_name in azure_loggers:
        azure_logger = logging.getLogger(azure_logger_name)
        azure_logger.setLevel(logging.WARNING)
    
    logger.info("🔧 Local development logging configured")

# Setup static files and templates with absolute paths
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Use managed identity for all Azure service authentication
# Exclude slow/irrelevant credential sources to speed up startup on App Service
cred = DefaultAzureCredential(
    exclude_environment_credential=True,
    exclude_shared_token_cache_credential=True,
    exclude_visual_studio_code_credential=True,
    exclude_powershell_credential=True,
    exclude_cli_credential=True,
    exclude_interactive_browser_credential=True,
)

# Global orchestrator instances - initialized lazily
orchestrator = None
chat_orchestrator = None


def get_eol_orchestrator():
    """Get or initialize the EOL orchestrator instance lazily"""
    global orchestrator
    if orchestrator is None:
        orchestrator = EOLOrchestratorAgent()
    return orchestrator


def get_chat_orchestrator():
    """Get or initialize the Chat orchestrator instance lazily
    
    Note: Chat functionality is in separate chat.html interface.
    This EOL interface does not use chat orchestrator.
    """
    global chat_orchestrator
    if chat_orchestrator is None and CHAT_AVAILABLE:
        try:
            logger.info("🔍 Chat orchestrator not available in EOL interface")
            # Chat orchestrator would be initialized here if available
            return None
        except Exception as e:
            import traceback
            error_msg = f"Failed to initialize Chat orchestrator: {e}"
            logger.error(f"🔍 ERROR in get_chat_orchestrator: {error_msg}")
            logger.debug(f"🔍 TRACEBACK: {traceback.format_exc()}")
            return None
    return chat_orchestrator


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class InventoryItem(BaseModel):
    computer_name: str
    software_name: str
    software_version: Optional[str] = None
    software_type: Optional[str] = None
    eol_date: Optional[str] = None
    publisher: Optional[str] = None
    last_updated: Optional[str] = None
    source: Optional[str] = None


class QueryRequest(BaseModel):
    query: str


class ChatRequest(BaseModel):
    message: str


class AutoGenChatRequest(BaseModel):
    message: str
    use_autogen: Optional[bool] = True
    confirmed: Optional[bool] = False
    original_message: Optional[str] = None
    timeout_seconds: Optional[int] = 150  # Default 150 seconds timeout to match frontend expectations


class AutoGenChatResponse(BaseModel):
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


class MultiAgentResponse(BaseModel):
    session_id: str
    analysis_result: dict
    communication_history: List[dict]
    timestamp: str


class SoftwareSearchRequest(BaseModel):
    software_name: str
    software_version: Optional[str] = None
    search_hints: Optional[dict] = None  # Additional search optimization hints
    search_internet_only: Optional[bool] = False  # Force use of Playwright web search only


# ============================================================================
# STARTUP AND HEALTH ENDPOINTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    try:
        logger.info("🚀 Starting %s v%s", config.app.title, config.app.version)
        
        # Validate configuration
        validation = config.validate_config()
        if not validation["valid"]:
            logger.warning("Configuration validation failed:")
            for error in validation["errors"]:
                logger.error("  - %s", error)
        
        # Log environment summary
        env_summary = config.get_environment_summary()
        logger.info("📊 Environment check:")
        for service, status in env_summary.items():
            logger.info("   - %s: %s", service, status)
        # Initialize base cosmos client and preload caches
        try:
            # import locally to ensure we always reference the shared singleton
            from utils.cosmos_cache import base_cosmos as _base_cosmos
            if getattr(_base_cosmos, 'initialized', False) is False:
                await _base_cosmos._initialize_async()
        except Exception as e:
            logger.warning(f"Cosmos base initialization failed during startup: {e}")

        # Initialize specialized caches
        try:
            await eol_cache.initialize()
            
            # Initialize the unified inventory cache used by agents
            from utils.inventory_cache import inventory_cache
            await inventory_cache.initialize()
        except Exception as e:
            logger.warning(f"Cache initialization warning: {e}")
        
        # Initialize alert manager and load configuration from Cosmos DB
        try:
            from utils.alert_manager import initialize_alert_manager
            await initialize_alert_manager()
        except Exception as e:
            logger.warning(f"Alert manager initialization warning: {e}")
        
        logger.info("✅ App startup completed")
    except Exception as e:
        logger.warning("⚠️ Startup warning: %s", e)
        # Don't fail startup for non-critical issues


class DebugRequest(BaseModel):
    query: str


@app.post('/api/debug_tool_selection')
async def debug_tool_selection(request: DebugRequest):
    """Debug endpoint to test tool selection logic"""
    try:
        query = request.query
        
        # Test the tool selection logic
        import re
        
        # Check if keywords are found
        get_inventory_patterns = [
            r'show\s+(?:me\s+)?(?:the\s+)?inventory',
            r'(?:get|retrieve|fetch)\s+(?:the\s+)?inventory',
            r'what\s+software',
            r'list\s+(?:all\s+)?(?:the\s+)?(?:installed\s+)?software',
            r'inventory\s+(?:of|for)',
            r'software\s+(?:inventory|list)',
            r'show\s+(?:all\s+)?applications',
            r'what\s+(?:is\s+)?installed'
        ]
        
        eol_patterns = [
            'end of life', 'end-of-life', 'eol', 'support status', 
            'lifecycle', 'when does', 'reach end', 'support end',
            'retire', 'deprecated', 'sunset', 'maintenance end'
        ]
        
        approaching_eol_patterns = [
            'approaching end', 'approaching eol', 'software approaching',
            'expiring soon', 'ending support', 'near end of life',
            'within a year', 'next year', 'soon to expire',
            'what software is approaching', 'which software is ending'
        ]
        
        found_inventory_keywords = []
        found_eol_keywords = []
        found_approaching_eol_keywords = []
        
        for pattern in get_inventory_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                found_inventory_keywords.append(pattern)
        
        for pattern in eol_patterns:
            if pattern.lower() in query.lower():
                found_eol_keywords.append(pattern)
                
        for pattern in approaching_eol_patterns:
            if pattern.lower() in query.lower():
                found_approaching_eol_keywords.append(pattern)
        
        # Test filter detection logic
        query_lower = query.lower()
        detected_filter = None
        detected_software = None
        detected_version = None
        
        if 'windows' in query_lower and 'server' in query_lower:
            detected_filter = "windows server"
        elif 'windows' in query_lower:
            detected_filter = "windows"
        elif 'server' in query_lower:
            detected_filter = "server"
        elif 'linux' in query_lower:
            detected_filter = "linux"
        
        # Test EOL software/version detection
        import re
        eol_patterns_regex = [
            r'(ubuntu)\s+(\d+\.\d+)',
            r'(windows)\s+(\d+)',
            r'(centos)\s+(\d+)',
            r'(java)\s+(\d+)',
            r'(\w+)\s+(\d+\.\d+)'
        ]
        
        for pattern in eol_patterns_regex:
            match = re.search(pattern, query_lower)
            if match:
                detected_software = match.group(1)
                detected_version = match.group(2)
                break
        
        # Determine tool choice
        tool_choice = "auto"
        primary_tool = None
        
        if found_approaching_eol_keywords:
            tool_choice = {"type": "function", "function": {"name": "find_approaching_eol"}}
            primary_tool = "find_approaching_eol"
        elif found_eol_keywords:
            tool_choice = {"type": "function", "function": {"name": "check_software_eol"}}
            primary_tool = "check_software_eol"
        elif found_inventory_keywords:
            tool_choice = {"type": "function", "function": {"name": "get_inventory"}}
            primary_tool = "get_inventory"
        
        return {
            'query': query,
            'found_inventory_keywords': found_inventory_keywords,
            'found_eol_keywords': found_eol_keywords,
            'found_approaching_eol_keywords': found_approaching_eol_keywords,
            'detected_filter': detected_filter,
            'detected_software': detected_software,
            'detected_version': detected_version,
            'primary_tool': primary_tool,
            'tool_choice': tool_choice,
            'would_force_tool': primary_tool is not None
        }
        
    except Exception as e:
        logger.error(f"Error in debug tool selection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/health')
async def health_check():
    """Fast health check endpoint"""
    return {
        "status": "ok", 
        "timestamp": datetime.utcnow().isoformat(),
        "version": config.app.version,
        "autogen_available": CHAT_AVAILABLE
    }


@app.get("/api/health/detailed")
async def detailed_health():
    """Detailed health check with service status"""
    try:
        validation = config.validate_config()
        
        # EOL interface uses only regular orchestrator
        autogen_status = "not_available"
        autogen_agents_count = 0
        
        health_status = {
            "status": "ok" if validation["valid"] else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "services": validation["services"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "autogen": {
                "available": CHAT_AVAILABLE,
                "status": autogen_status,
                "agents_count": autogen_agents_count
            }
        }
        return health_status
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return create_error_response(e, "health_check")


@app.get("/api/test-logging")
async def test_logging():
    """Test logging functionality - especially useful for Azure App Service debugging"""
    try:
        timestamp = datetime.utcnow().isoformat()
        test_id = str(uuid.uuid4())[:8]
        
        # Test main app logger
        logger.debug(f"🧪 MAIN-DEBUG Test Log [{test_id}] - {timestamp}")
        logger.info(f"🧪 MAIN-INFO Test Log [{test_id}] - {timestamp}")
        logger.warning(f"🧪 MAIN-WARNING Test Log [{test_id}] - {timestamp}")
        logger.error(f"🧪 MAIN-ERROR Test Log [{test_id}] - {timestamp}")
        
        # Test Chat orchestrator logging if available
        # EOL interface uses only regular orchestrator
        autogen_test_result = None
        
        # Force flush for Azure
        if os.environ.get('WEBSITE_SITE_NAME'):
            import sys
            sys.stderr.flush()
            sys.stdout.flush()
        
        result = {
            "test_completed": True,
            "test_id": test_id,
            "timestamp": timestamp,
            "environment": "Azure App Service" if os.environ.get('WEBSITE_SITE_NAME') else "Local",
            "main_logger": {
                "name": logger.name,
                "level": logger.level,
                "handler_count": len(logger.handlers)
            },
            "autogen_test": autogen_test_result,
            "message": f"Logging test completed. Check Azure App Service logs for messages with ID [{test_id}]"
        }
        
        logger.info(f"🧪 Logging test result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Logging test failed: {e}")
        return create_error_response(e, "logging_test")


# ============================================================================
# MAIN ENDPOINTS
# ============================================================================

@app.get("/api/status")
async def status():
    """Status endpoint - for health checks"""
    return {
        "message": config.app.title, 
        "status": "running",
        "version": config.app.version
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Fast index route to improve warm-up."""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        return HTMLResponse("EOL Multi-Agent App", status_code=200)


@app.get("/api/inventory", response_model=StandardResponse)
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


@app.get("/api/inventory/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="inventory_status", timeout_seconds=30)
async def inventory_status():
    """
    Get inventory data status and summary.
    
    Returns the current status of the inventory system including Log Analytics
    availability and summary statistics.
    """
    summary = await get_eol_orchestrator().agents["inventory"].get_inventory_summary()
    return {
        "status": "ok",
        "log_analytics_available": bool(config.azure.log_analytics_workspace_id),
        "summary": summary
    }


@app.get("/api/os", response_model=StandardResponse)
@standard_endpoint(agent_name="os_inventory", timeout_seconds=30)
async def get_os(days: int = 90):
    """
    Get operating system inventory from Heartbeat via OS agent.
    
    Args:
        days: Number of days to look back for OS data (default: 90)
    
    Returns:
        StandardResponse with OS inventory including computer names, OS types,
        versions, and EOL status.
    """
    return await get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days)


@app.get("/api/os/summary", response_model=StandardResponse)
@readonly_endpoint(agent_name="os_summary", timeout_seconds=30)
async def get_os_summary(days: int = 90):
    """
    Get summarized OS counts and top versions.
    
    Args:
        days: Number of days to look back for OS data (default: 90)
    
    Returns:
        StandardResponse with OS summary statistics including counts by OS type,
        version distributions, and EOL risk levels.
    """
    summary = await get_eol_orchestrator().agents["os_inventory"].get_os_summary(days=days)
    return {"status": "ok", "summary": summary}


@app.get("/api/inventory/raw/software")
async def get_raw_software_inventory(days: int = 90, limit: int = 1000, force_refresh: bool = False):
    """
    Get raw software inventory data directly from Log Analytics ConfigurationData table
    Returns clean JSON response with validation and error handling
    """
    try:
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
        result = await asyncio.wait_for(
            inventory_agent.get_software_inventory(days=days, limit=limit, use_cache=use_cache),
            timeout=60.0  # 1 minute timeout for raw data queries
        )
        
        # Handle case where result might be a string instead of dict
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
        
    except asyncio.TimeoutError:
        logger.error("Raw software inventory request timed out after 60 seconds")
        return {
            "success": False,
            "error": "Raw software inventory request timed out after 60 seconds",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving raw software inventory: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Error retrieving raw software inventory: {str(e)}",
            "error_type": type(e).__name__,
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }


@app.get("/api/inventory/raw/os")
async def get_raw_os_inventory(days: int = 90, limit: int = 2000, force_refresh: bool = False):
    """
    Get raw operating system inventory data directly from Log Analytics Heartbeat table
    Returns clean JSON response with validation and error handling
    
    Caching is handled automatically by the inventory agent using InventoryRawCache.
    """
    try:
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
        # Agent's built-in caching will handle cache hits/misses
        use_cache = not force_refresh
        result = await asyncio.wait_for(
            inventory_agent.get_os_inventory(days=days, limit=limit, use_cache=use_cache),
            timeout=60.0  # 1 minute timeout for raw data queries
        )
        
        # Handle case where result might be a string instead of dict
        if isinstance(result, str):
            logger.warning(f"Raw OS inventory returned string instead of dict: {result}")
            error_result = {
                "success": False,
                "error": f"Invalid response format: {result}",
                "data": [],
                "count": 0,
                "query_days": days,
                "query_limit": limit
            }
            return error_result
        elif not isinstance(result, dict):
            logger.warning(f"Raw OS inventory returned unexpected type {type(result)}: {result}")
            error_result = {
                "success": False,
                "error": f"Invalid response type: {type(result).__name__}",
                "data": [],
                "count": 0,
                "query_days": days,
                "query_limit": limit
            }
            return error_result
        
        logger.info(f"✅ Raw OS inventory result: success={result.get('success')}, count={result.get('count', 0)}")
        
        return result
        
    except asyncio.TimeoutError:
        logger.error("Raw OS inventory request timed out after 60 seconds")
        return {
            "success": False,
            "error": "Raw OS inventory request timed out after 60 seconds",
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving raw OS inventory: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Error retrieving raw OS inventory: {str(e)}",
            "error_type": type(e).__name__,
            "data": [],
            "count": 0,
            "query_days": days,
            "query_limit": limit
        }


@app.get("/api/agents/status")
async def agents_status():
    """Get readiness/health of registered agents, including the new OS agent"""
    try:
        status = await asyncio.wait_for(get_eol_orchestrator().get_agents_status(), timeout=20.0)
        return status
    except asyncio.TimeoutError:
        return {"status": "timeout", "error": "Agents status timed out"}
    except Exception as e:
        logger.error("Error retrieving agents status: %s", e)
        return create_error_response(e, "agents_status")


@app.get("/api/eol")
async def get_eol(name: str, version: Optional[str] = None):
    """Get EOL data using multi-agent system with prioritized sources"""
    try:
        eol_data = await get_eol_orchestrator().get_eol_data(name, version)
        
        if not eol_data.get("data"):
            raise HTTPException(status_code=404, detail=f"No EOL data found for {name}")
        
        return {
            "software_name": name,
            "version": version,
            "primary_source": eol_data["primary_source"],
            "eol_data": eol_data["data"],
            "all_sources": eol_data.get("all_sources", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving EOL data for %s: %s", name, e)
        raise HTTPException(status_code=500, detail=f"Error retrieving EOL data: {str(e)}")


@app.get("/alerts", response_class=HTMLResponse)
async def get_alerts_page(request: Request):
    """Serve the alerts management page"""
    try:
        return templates.TemplateResponse("alerts.html", {"request": request})
    except Exception as e:
        logger.error(f"Error serving alerts page: {e}")
        return HTMLResponse("Alert Management - Page not found", status_code=404)


# ============================================================================
# ALERT MANAGEMENT API ENDPOINTS
# ============================================================================

@app.get("/api/alerts/config")
async def get_alert_configuration():
    """Get current alert configuration"""
    try:
        from utils.alert_manager import alert_manager
        config = await alert_manager.load_configuration()
        return {
            "success": True,
            "data": config.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting alert configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {str(e)}")


@app.post("/api/alerts/config")
async def save_alert_configuration(config_data: dict):
    """Save alert configuration"""
    try:
        from utils.alert_manager import alert_manager, AlertConfiguration
        config = AlertConfiguration(**config_data)
        success = await alert_manager.save_configuration(config)
        
        if success:
            return {
                "success": True,
                "message": "Configuration saved successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
            
    except Exception as e:
        logger.error(f"Error saving alert configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")


@app.post("/api/alerts/config/reload")
async def reload_alert_configuration():
    """Reload alert configuration from Cosmos DB (force refresh)"""
    try:
        from utils.alert_manager import alert_manager
        
        # Clear cached configuration to force reload
        alert_manager._config = None
        
        # Load fresh configuration from Cosmos DB
        config = await alert_manager.load_configuration()
        
        return {
            "success": True,
            "message": "Configuration reloaded successfully from Cosmos DB",
            "data": config.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error reloading alert configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Error reloading configuration: {str(e)}")


@app.get("/api/cosmos/test")
async def test_cosmos_connection():
    """Test Cosmos DB connection for diagnostic purposes"""
    try:
        from utils.cosmos_cache import base_cosmos
        
        # Check if base client is initialized
        if not base_cosmos.initialized:
            logger.info("Base Cosmos client not initialized, attempting initialization...")
            await base_cosmos._initialize_async()
        
        if not base_cosmos.initialized:
            return {
                "success": False,
                "message": f"Cosmos DB initialization failed: {base_cosmos.last_error}",
                "details": {
                    "initialized": False,
                    "last_error": base_cosmos.last_error,
                    "cosmos_client": str(type(base_cosmos.cosmos_client)),
                    "database": str(type(base_cosmos.database))
                }
            }
        
        # Try to create/get a test container
        try:
            test_container = base_cosmos.get_container(
                container_id="test_connection",
                partition_path="/test_key",
                offer_throughput=400
            )
            
            # Try a simple operation
            test_result = test_container.read_item(
                item="nonexistent",
                partition_key="test"
            )
            
        except Exception as container_error:
            # This is expected for nonexistent item, but it proves connection works
            if "NotFound" in str(container_error) or "404" in str(container_error):
                return {
                    "success": True,
                    "message": "Cosmos DB connection successful",
                    "details": {
                        "initialized": True,
                        "test_operation": "Container access successful",
                        "note": "NotFound error for test item is expected"
                    }
                }
            else:
                return {
                    "success": False,
                    "message": f"Cosmos DB container operation failed: {str(container_error)}",
                    "details": {
                        "initialized": True,
                        "container_error": str(container_error)
                    }
                }
        
        return {
            "success": True,
            "message": "Cosmos DB connection and operations successful",
            "details": {
                "initialized": True,
                "test_operation": "Full test successful"
            }
        }
        
    except Exception as e:
        logger.error(f"Error testing Cosmos DB connection: {e}")
        return {
            "success": False,
            "message": f"Cosmos DB test failed: {str(e)}",
            "details": {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        }


@app.get("/api/alerts/preview")
async def get_alert_preview(days: int = 90):
    """Get preview of alerts based on current configuration
    
    Caching is handled automatically by the OS inventory agent using InventoryRawCache.
    """
    try:
        from utils.alert_manager import alert_manager
        
        # Get OS inventory data using agent's built-in caching
        logger.debug(f"🔄 Fetching OS inventory for alert preview (days={days})")
        os_data = await asyncio.wait_for(
            get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days, use_cache=True),
            timeout=30.0,
        )
        
        # Extract inventory data from standardized response
        if isinstance(os_data, dict) and os_data.get("success"):
            inventory_data = os_data.get("data", [])
        elif isinstance(os_data, list):
            inventory_data = os_data
        else:
            logger.warning(f"Invalid OS data format: {type(os_data)}")
            inventory_data = []
        
        # Load configuration and generate preview
        config = await alert_manager.load_configuration()
        alert_items, summary = await alert_manager.generate_alert_preview(inventory_data, config)
        
        return {
            "success": True,
            "data": {
                "alerts": [item.dict() for item in alert_items],
                "summary": summary.dict(),
                "config": config.dict()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating alert preview: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")


@app.post("/api/alerts/smtp/test")
async def test_smtp_connection(smtp_data: dict):
    """Test SMTP connection with provided settings and detailed debugging"""
    try:
        logger.info("=== SMTP TEST ENDPOINT CALLED ===")
        logger.info(f"SMTP test data received: {smtp_data}")
        
        from utils.alert_manager import alert_manager, SMTPSettings
        
        # Create settings and log them (masking password)
        smtp_settings = SMTPSettings(**smtp_data)
        logger.info(f"SMTP settings created - server: {smtp_settings.server}:{smtp_settings.port}")
        logger.info(f"SMTP settings - SSL: {smtp_settings.use_ssl}, TLS: {smtp_settings.use_tls}")
        logger.info(f"SMTP settings - username: {smtp_settings.username}")
        logger.info(f"SMTP settings - password provided: {'Yes' if smtp_settings.password else 'No'}")
        
        # Execute the test
        logger.info("Calling alert_manager.test_smtp_connection...")
        success, message = await alert_manager.test_smtp_connection(smtp_settings)
        
        result = {
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "debug_info": {
                "server": smtp_settings.server,
                "port": smtp_settings.port,
                "use_ssl": smtp_settings.use_ssl,
                "use_tls": smtp_settings.use_tls,
                "username": smtp_settings.username,
                "has_password": bool(smtp_settings.password),
                "is_gmail": smtp_settings.is_gmail_config()
            }
        }
        
        logger.info(f"SMTP test result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"=== SMTP TEST ENDPOINT ERROR === Error testing SMTP connection: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {repr(e)}")
        logger.error(f"SMTP data that caused error: {smtp_data}")
        return {
            "success": False,
            "message": f"Error testing connection: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
            "error_type": type(e).__name__
        }


@app.post("/api/alerts/send")
async def send_test_alert(request_data: dict):
    """Send a test alert email with detailed debugging"""
    try:
        logger.info("=== SEND TEST ALERT ENDPOINT CALLED ===")
        logger.info(f"Request data: {request_data}")
        
        from utils.alert_manager import alert_manager
        
        logger.info("Loading alert configuration...")
        config = await alert_manager.load_configuration()
        recipients = request_data.get("recipients", config.email_recipients)
        alert_level = request_data.get("level", "info")
        
        logger.info(f"Alert level: {alert_level}")
        logger.info(f"Recipients: {recipients}")
        logger.info(f"SMTP enabled: {config.smtp_settings.enabled}")
        
        if not recipients:
            logger.error("No email recipients specified")
            raise HTTPException(status_code=400, detail="No email recipients specified")
        
        # Create test alert
        custom_subject = request_data.get("custom_subject")
        custom_body = request_data.get("custom_body")
        is_html = request_data.get("is_html", False)
        
        if custom_subject:
            subject = custom_subject
            logger.info(f"Using custom subject: {subject}")
        else:
            subject = f"Test EOL {alert_level.capitalize()} Alert"
            logger.info(f"Using default subject: {subject}")
        
        if custom_body:
            # Check if content is already HTML or if is_html flag is set
            if is_html or custom_body.strip().startswith('<!DOCTYPE') or custom_body.strip().startswith('<html'):
                html_content = custom_body
                logger.info(f"Using custom HTML body (length: {len(custom_body)} chars)")
            else:
                # Wrap plain text in HTML
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                        .header {{ background-color: #2563eb; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                        .content {{ margin: 20px 0; white-space: pre-line; }}
                        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 0.9em; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h1>End-of-Life Alert</h1>
                    </div>
                    <div class="content">
                        {custom_body}
                    </div>
                    <div class="footer">
                        <p>This is an automated alert from the End-of-Life Monitoring System.</p>
                        <p>Timestamp: {datetime.utcnow().isoformat()}</p>
                    </div>
                </body>
                </html>
                """
                logger.info(f"Wrapped plain text in HTML (length: {len(custom_body)} chars)")
        else:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background-color: #2563eb; color: white; padding: 20px; border-radius: 8px; }}
                    .content {{ margin: 20px 0; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Test EOL Alert</h1>
                    <p>This is a test email from the EOL Alert Management System.</p>
                </div>
                <div class="content">
                    <p>If you received this email, your SMTP configuration is working correctly.</p>
                    <p>Alert Level: {alert_level.capitalize()}</p>
                    <p>Timestamp: {datetime.utcnow().isoformat()}</p>
                </div>
            </body>
            </html>
            """
            logger.info("Using default test email body")
        
        logger.info("Calling alert_manager.send_alert_email...")
        success, message = await alert_manager.send_alert_email(
            config.smtp_settings, recipients, subject, html_content
        )
        
        result = {
            "success": success,
            "message": message,
            "recipients_count": len(recipients),
            "timestamp": datetime.utcnow().isoformat(),
            "debug_info": {
                "alert_level": alert_level,
                "subject": subject,
                "content_length": len(html_content),
                "smtp_server": config.smtp_settings.server,
                "smtp_enabled": config.smtp_settings.enabled
            }
        }
        
        logger.info(f"Send alert result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"=== SEND ALERT ENDPOINT ERROR === Error sending test alert: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {repr(e)}")
        logger.error(f"Request data that caused error: {request_data}")
        raise HTTPException(status_code=500, detail=f"Error sending alert: {str(e)}")


@app.post("/api/analyze")
async def analyze_inventory_eol():
    """Comprehensive EOL risk analysis using multi-agent orchestration"""
    try:
        analysis = await get_eol_orchestrator().analyze_inventory_eol_risks()
        communications = await get_eol_orchestrator().get_communication_history()
        
        return MultiAgentResponse(
            session_id=get_eol_orchestrator().session_id,
            analysis_result=analysis,
            communication_history=communications,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error("Error analyzing inventory: %s", e)
        raise HTTPException(status_code=500, detail=f"Error analyzing inventory: {str(e)}")


@app.post("/api/search/eol")
async def search_software_eol(request: SoftwareSearchRequest):
    """Search for end-of-life information for specific software using the orchestrator agent"""
    start_time = time.time()
    agent_name = "orchestrator"
    
    try:
        # Log the enhanced search request
        version_display = f" v{request.software_version}" if request.software_version else " (no version)"
        search_mode = " [Internet Only]" if request.search_internet_only else ""
        logger.info(f"EOL search request: {request.software_name}{version_display}{search_mode}")
        if request.search_hints:
            logger.info(f"Search hints: {request.search_hints}")
        if request.search_internet_only:
            logger.info("🌐 Internet-only search mode enabled (Playwright only)")
        
        # Route through regular orchestrator which will select appropriate agent
        result = await get_eol_orchestrator().get_autonomous_eol_data(
            software_name=request.software_name,
            version=request.software_version,
            search_internet_only=request.search_internet_only
        )
        
        # Debug logging to understand what the orchestrator returns
        logger.info(f"Orchestrator returned: {type(result)} - {result}")
        
        # Record cache performance metrics
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        cache_hit = bool(result and result.get("cached", False))
        
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=cache_hit
        )
        
        # Extract the actual EOL data from the orchestrator response
        # The orchestrator returns {"success": bool, "data": {...}} but frontend expects the data directly
        actual_eol_data = None
        if result and result.get("success") and result.get("data"):
            actual_eol_data = result["data"]
            logger.info(f"Extracted EOL data from orchestrator result: {actual_eol_data}")
        elif result and result.get("success") == False:
            # Handle case where orchestrator indicates failure
            logger.info(f"Orchestrator indicated failure: {result.get('error', 'Unknown error')}")
            actual_eol_data = None
        elif result:
            # Handle case where result is already the direct data (backward compatibility)
            logger.info("Using orchestrator result directly (backward compatibility)")
            actual_eol_data = result
        else:
            logger.info("No result from orchestrator")
            actual_eol_data = None
        
        # Get simple communication history from orchestrator if available
        communications = []
        if hasattr(get_eol_orchestrator(), 'get_recent_communications'):
            try:
                communications = get_eol_orchestrator().get_recent_communications()
            except Exception as comm_error:
                logger.warning(f"Failed to get communications from orchestrator: {comm_error}")
        
        return {
            "result": actual_eol_data,
            "session_id": get_eol_orchestrator().session_id,
            "agent_communications": communications,
            "communication_history": communications,  # Backward compatibility
            "communications": communications,  # Another backward compatibility alias
            "timestamp": datetime.utcnow().isoformat(),
            "search_request": {
                "software_name": request.software_name,
                "software_version": request.software_version,
                "search_hints": request.search_hints
            }
        }
        
    except Exception as e:
        # Record error in performance statistics
        response_time = (time.time() - start_time) * 1000
        cache_stats_manager.record_agent_request(
            agent_name=agent_name,
            response_time_ms=response_time,
            was_cache_hit=False,
            had_error=True
        )
        
        logger.error("EOL search failed for %s: %s", request.software_name, e)
        # Communication history not implemented in current orchestrator version
        communications = []
            
        return create_error_response(e, f"eol_search_{request.software_name}")


# ============================================================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/cache/status")
async def get_cache_status():
    """Get status of cached data across all agents with enhanced statistics"""
    try:
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
            logger.warning(f"Could not load enhanced cache statistics: {e}")
            cache_status["enhanced_stats"] = {"error": str(e)}
        
        cache_status["inventory_context_cache"] = inventory_stats
        return cache_status
    except Exception as e:
        logger.error("Error getting cache status: %s", e)
        raise HTTPException(status_code=500, detail=f"Error getting cache status: {str(e)}")


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all inventory caches (software and OS)
    
    This clears both memory and Cosmos DB caches for inventory data.
    EOL agent caches are managed separately via /api/cache/purge
    """
    try:
        # Clear inventory caches via orchestrator agents
        software_agent = get_eol_orchestrator().agents.get("software_inventory")
        os_agent = get_eol_orchestrator().agents.get("os_inventory")
        
        cleared_items = []
        
        if software_agent and hasattr(software_agent, 'clear_cache'):
            await software_agent.clear_cache()
            cleared_items.append("software_inventory")
        
        if os_agent and hasattr(os_agent, 'clear_cache'):
            await os_agent.clear_cache()
            cleared_items.append("os_inventory")
        
        logger.info(f"🧹 Cleared inventory caches: {cleared_items}")
        
        return {
            "success": True,
            "status": "success",
            "message": f"Inventory caches cleared: {', '.join(cleared_items)}",
            "cleared_caches": cleared_items,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"Error clearing cache: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


@app.post("/api/cache/purge")
async def purge_cache(agent_type: Optional[str] = None, software_name: Optional[str] = None, version: Optional[str] = None):
    """Purge web scraping cache for specific agent or all agents"""
    try:
        result = await get_eol_orchestrator().purge_web_scraping_cache(agent_type, software_name, version)
        logger.info("Cache purged: %s", result)
        return result
    except Exception as e:
        logger.error("Error purging cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error purging cache: {str(e)}")


@app.post("/api/communications/clear")
async def clear_communications():
    """Clear orchestrator communications log"""
    try:
        result = get_eol_orchestrator().clear_communications()
        logger.info("Communications cleared: %s", result)
        return result
    except Exception as e:
        logger.error("Error clearing communications: %s", e)
        raise HTTPException(status_code=500, detail=f"Error clearing communications: {str(e)}")


@app.get("/api/communications/eol")
async def get_eol_communications():
    """Get real-time EOL orchestrator communications"""
    try:
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
    except Exception as e:
        logger.error("Error getting EOL communications: %s", e)
        return {
            "success": False,
            "error": str(e),
            "communications": [],
            "count": 0
        }


@app.get("/api/communications/chat")
async def get_chat_communications():
    """Get real-time chat orchestrator communications"""
    try:
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
    except Exception as e:
        logger.error("Error getting chat communications: %s", e)
        return {
            "success": False,
            "error": str(e),
            "communications": [],
            "count": 0
        }


@app.get("/api/eol-agent-responses")
async def get_eol_agent_responses():
    """Get all tracked EOL agent responses from both Chat and EOL orchestrators"""
    try:
        all_responses = []
        
        # Get responses from Chat orchestrator
        chat_orchestrator = get_chat_orchestrator()
        if chat_orchestrator and hasattr(chat_orchestrator, 'get_eol_agent_responses'):
            chat_responses = chat_orchestrator.get_eol_agent_responses()
            # Mark these as from chat orchestrator
            for response in chat_responses:
                response['orchestrator_type'] = 'chat_orchestrator'
            all_responses.extend(chat_responses)
            logger.info(f"🔍 [API] Chat orchestrator returned {len(chat_responses)} EOL responses")
        else:
            logger.warning("🔍 [API] Chat orchestrator not available or missing get_eol_agent_responses method")
        
        # Get responses from EOL orchestrator
        eol_orchestrator = get_eol_orchestrator()
        if eol_orchestrator and hasattr(eol_orchestrator, 'get_eol_agent_responses'):
            eol_responses = eol_orchestrator.get_eol_agent_responses()
            # Mark these as from eol orchestrator
            for response in eol_responses:
                response['orchestrator_type'] = 'eol_orchestrator'
            all_responses.extend(eol_responses)
            logger.info(f"🔍 [API] EOL orchestrator returned {len(eol_responses)} EOL responses")
        else:
            logger.warning("🔍 [API] EOL orchestrator not available or missing get_eol_agent_responses method")
        
        # Sort by timestamp (newest first)
        all_responses.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        logger.info(f"🔍 [API] Total EOL responses returned: {len(all_responses)}")
        
        return {
            "success": True,
            "responses": all_responses,
            "count": len(all_responses),
            "timestamp": datetime.utcnow().isoformat(),
            "sources": {
                "chat_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'chat_orchestrator']),
                "eol_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'eol_orchestrator'])
            }
        }
        
    except Exception as e:
        logger.error("Error getting EOL agent responses: %s", e)
        return {
            "success": False,
            "error": str(e),
            "responses": [],
            "count": 0
        }


@app.post("/api/eol-agent-responses/clear")
async def clear_eol_agent_responses():
    """Clear all tracked EOL agent responses from both orchestrators"""
    try:
        cleared_count = 0
        
        # Clear from Chat orchestrator
        chat_orchestrator = get_chat_orchestrator()
        if chat_orchestrator and hasattr(chat_orchestrator, 'clear_eol_agent_responses'):
            chat_responses_before = len(chat_orchestrator.get_eol_agent_responses()) if hasattr(chat_orchestrator, 'get_eol_agent_responses') else 0
            chat_orchestrator.clear_eol_agent_responses()
            cleared_count += chat_responses_before
        
        # Clear from EOL orchestrator
        eol_orchestrator = get_eol_orchestrator()
        if eol_orchestrator and hasattr(eol_orchestrator, 'clear_eol_agent_responses'):
            eol_responses_before = len(eol_orchestrator.get_eol_agent_responses()) if hasattr(eol_orchestrator, 'get_eol_agent_responses') else 0
            eol_orchestrator.clear_eol_agent_responses()
            cleared_count += eol_responses_before
        
        return {
            "success": True,
            "message": f"EOL agent responses cleared successfully. {cleared_count} responses cleared.",
            "cleared_count": cleared_count
        }
        
    except Exception as e:
        logger.error("Error clearing EOL agent responses: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/communications/chat/clear")
async def clear_chat_communications():
    """Clear chat orchestrator communications log"""
    try:
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
    except Exception as e:
        logger.error("Error clearing chat communications: %s", e)
        raise HTTPException(status_code=500, detail=f"Error clearing chat communications: {str(e)}")


@app.get("/api/cache/inventory/stats")
async def get_inventory_cache_stats():
    """Get detailed inventory context cache statistics with enhanced metrics"""
    try:
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
    except Exception as e:
        # Record error
        response_time_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
        cache_stats_manager.record_inventory_request(response_time_ms, False, 0)
        
        logger.error("Error getting inventory cache stats: %s", e)
        return {
            "success": False,
            "error": str(e),
            "cache_stats": {
                "cached": False,
                "timestamp": None,
                "ttl_seconds": 300,
                "items_count": 0,
                "size_bytes": 0
            },
            "enhanced_stats": {"error": str(e)}
        }


@app.get("/api/cache/inventory/details")
async def get_inventory_cache_details():
    """Get detailed inventory context cache content for viewing"""
    try:
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
        
    except Exception as e:
        logger.error("Error getting inventory cache details: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/cache/webscraping/details")
async def get_webscraping_cache_details():
    """Get detailed web scraping cache information"""
    try:
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
        
    except Exception as e:
        logger.error("Error getting web scraping cache details: %s", e)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/cache/cosmos/stats")
async def get_cosmos_cache_stats():
    """Get Cosmos DB cache statistics with enhanced metrics"""
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
            # Get statistics from the unified inventory cache system
            from utils.inventory_cache import inventory_cache
            
            # Get stats from unified inventory cache
            cache_stats = inventory_cache.get_cache_stats()
            
            # Calculate memory cache entries from the unified cache system
            software_memory_count = cache_stats.get('memory_cache_entries', {}).get('software', 0)
            os_memory_count = cache_stats.get('memory_cache_entries', {}).get('os', 0)
            
            # Add inventory cache info to the stats
            if 'success' not in stats:
                stats['success'] = True
            
            # Add inventory container information with actual counts from unified cache
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
            logger.warning("Could not get inventory cache stats for Cosmos DB section: %s", inv_err)
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
        # Record error
        response_time_ms = (time.time() - start_time) * 1000
        cache_stats_manager.record_cosmos_request(response_time_ms, False, "stats_query_error")
        
        logger.error("Error getting Cosmos cache stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Error getting cache stats: {str(e)}")


@app.post("/api/cache/cosmos/clear")
async def clear_cosmos_cache(agent_name: Optional[str] = None, software_name: Optional[str] = None):
    """Clear Cosmos DB cache with optional filters"""
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    if not getattr(base_cosmos, 'initialized', False):
        raise HTTPException(status_code=503, detail="Cosmos DB base client not initialized")
    try:
        result = await eol_cache.clear_cache(software_name=software_name, agent_name=agent_name)
        logger.info("Cosmos cache cleared: %s", result)
        return result
    except Exception as e:
        logger.error("Error clearing Cosmos cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")


@app.post("/api/cache/cosmos/initialize")
async def initialize_cosmos_cache():
    """Initialize Cosmos DB cache manually"""
    try:
        from utils.cosmos_cache import base_cosmos
        from utils.eol_cache import eol_cache
        if getattr(base_cosmos, 'initialized', False):
            return {"success": True, "message": "Cosmos DB base client already initialized"}
        await base_cosmos._initialize_async()
        # initialize specialized caches
        try:
            await eol_cache.initialize()
        except Exception:
            pass
        if getattr(base_cosmos, 'initialized', False):
            return {"success": True, "message": "Cosmos DB base client initialized successfully"}
        return {"success": False, "error": "Failed to initialize Cosmos DB base client"}
            
    except Exception as e:
        logger.error("Error initializing Cosmos cache: %s", e)
        return {"success": False, "error": f"Initialization error: {str(e)}"}


@app.get("/api/cache/cosmos/config")
async def get_cosmos_config():
    """Get Cosmos DB configuration and status"""
    try:
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
        
        # Include any structured details present on base_cosmos (backwards compatible)
        if getattr(base_cosmos, 'last_error_details', None):
            try:
                cosmos_config["debug"] = base_cosmos.last_error_details
            except Exception:
                cosmos_config["debug"] = {"note": "Failed to serialize last_error_details"}
            
        return cosmos_config
        
    except Exception as e:
        logger.error("Error getting Cosmos config: %s", e)
        return {
            "endpoint": None,
            "database": None,
            "container": None,
            "auth_method": "Unknown",
            "initialized": False,
            "error": f"Configuration error: {str(e)}"
        }

@app.get("/api/cache/cosmos/debug")
async def get_cosmos_debug_info():
    """Get debug information about Cosmos DB container caching"""
    try:
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
        
    except Exception as e:
        logger.error("Error getting Cosmos debug info: %s", e)
        return {
            "error": f"Debug info error: {str(e)}"
        }


class CachedEOLRequest(BaseModel):
    """Request model for testing cache retrieval"""
    software_name: str
    version: Optional[str] = None
    agent_name: str


class CacheEOLRequest(BaseModel):
    """Request model for manually caching EOL result"""
    software_name: str
    software_version: Optional[str] = None
    agent_name: str


class VerifyEOLRequest(BaseModel):
    """Request model for verifying EOL result"""
    software_name: str
    software_version: Optional[str] = None
    agent_name: str
    source_url: Optional[str] = None


# Enhanced Cache Statistics Endpoints

@app.get("/api/cache/stats/enhanced")
async def get_enhanced_cache_stats():
    """Get comprehensive cache statistics with real performance data"""
    try:
        from utils.cache_stats_manager import cache_stats_manager
        return cache_stats_manager.get_all_statistics()
    except Exception as e:
        logger.error("Error getting enhanced cache stats: %s", e)
        return {
            "success": False,
            "error": str(e),
            "agent_stats": {"agents": {}, "summary": {}},
            "inventory_stats": {"error": str(e)},
            "cosmos_stats": {"error": str(e)},
            "performance_summary": {"error": str(e)}
        }


@app.get("/api/cache/stats/agents")
async def get_agent_cache_stats():
    """Get detailed agent cache statistics"""
    try:
        from utils.cache_stats_manager import cache_stats_manager
        return cache_stats_manager.get_agent_statistics()
    except Exception as e:
        logger.error("Error getting agent cache stats: %s", e)
        return {"success": False, "error": str(e)}


@app.get("/api/cache/stats/performance")
async def get_cache_performance_stats():
    """Get cache performance summary"""
    try:
        from utils.cache_stats_manager import cache_stats_manager
        return cache_stats_manager.get_performance_summary()
    except Exception as e:
        logger.error("Error getting cache performance stats: %s", e)
        return {"success": False, "error": str(e)}


@app.post("/api/cache/stats/reset")
async def reset_cache_stats():
    """Reset all cache statistics (for testing or fresh start)"""
    try:
        from utils.cache_stats_manager import cache_stats_manager
        cache_stats_manager.reset_statistics()
        return {
            "success": True,
            "message": "Cache statistics reset successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Error resetting cache stats: %s", e)
        return {"success": False, "error": str(e)}
    verification_status: Optional[str] = "verified"  # "verified" or "failed"


@app.post("/api/verify-eol-result")
async def verify_eol_result(request: VerifyEOLRequest):
    """Mark EOL result as verified or failed and cache with appropriate priority"""
    try:
        verification_status = request.verification_status or "verified"
        is_verified = verification_status == "verified"
        is_failed = verification_status == "failed"
        
        # Get the orchestrator to perform the search 
        result = await get_eol_orchestrator().get_autonomous_eol_data(
            software_name=request.software_name,
            version=request.software_version
        )
        
        # If we have a result, cache it with appropriate verification status
        if result.get('success') and result.get('data'):
            # Use eol_cache to handle verification status
            from utils.cosmos_cache import base_cosmos
            from utils.eol_cache import eol_cache
            if getattr(base_cosmos, 'initialized', False):
                if is_failed:
                    # For failed verifications, delete the cache entry to clear it completely
                    await eol_cache.delete_failed_cache_entry(
                        software_name=request.software_name,
                        version=request.software_version,
                        agent_name=request.agent_name
                    )
                else:
                    # For verified results, update the cache with verification status
                    await eol_cache.cache_response(
                        software_name=request.software_name,
                        version=request.software_version,
                        agent_name=request.agent_name,
                        response_data=result,
                        verified=is_verified,
                        source_url=request.source_url,
                        verification_status=verification_status
                    )
            
            # Return appropriate response based on verification status
            if is_failed:
                return {
                    "success": True,
                    "message": f"EOL result marked as FAILED for {request.software_name}",
                    "software_name": request.software_name,
                    "software_version": request.software_version,
                    "agent_used": result.get('agent_used'),
                    "verified": False,
                    "failed": True,
                    "verification_status": "failed",
                    "source_url": request.source_url,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": True,
                    "message": f"EOL result verified for {request.software_name}",
                    "software_name": request.software_name,
                    "software_version": request.software_version,
                    "agent_used": result.get('agent_used'),
                    "verified": True,
                    "failed": False,
                    "verification_status": "verified",
                    "source_url": request.source_url,
                    "timestamp": datetime.utcnow().isoformat()
                }
        else:
            return {
                "success": False,
                "message": f"Failed to find EOL data for {request.software_name}",
                "error": "No EOL data found to verify"
            }
            
    except Exception as e:
        logger.error("Error verifying EOL result: %s", e)
        return {
            "success": False,
            "message": f"Error verifying EOL result: {str(e)}",
            "error": str(e)
        }


@app.post("/api/cache-eol-result")
async def cache_eol_result(request: CacheEOLRequest):
    """Manually cache EOL result for user validation"""
    try:
        # Get the orchestrator to perform the search and cache it
        result = await get_eol_orchestrator().get_autonomous_eol_data(
            software_name=request.software_name,
            version=request.software_version
        )
        
        # If we have a result, the caching should have been handled by the agent
        if result.get('success') and result.get('data'):
            return {
                "success": True,
                "message": f"EOL result cached for {request.software_name}",
                "software_name": request.software_name,
                "software_version": request.software_version,
                "agent_used": result.get('agent_used'),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "message": f"Failed to find EOL data for {request.software_name}",
                "error": "No EOL data found to cache"
            }
            
    except Exception as e:
        logger.error("Error caching EOL result: %s", e)
        return {
            "success": False,
            "message": f"Error caching EOL result: {str(e)}",
            "error": str(e)
        }


@app.post("/api/cache/cosmos/test")
async def test_cosmos_cache(req: CachedEOLRequest):
    """Test Cosmos DB cache retrieval for a specific request"""
    from utils.cosmos_cache import base_cosmos
    from utils.eol_cache import eol_cache
    if not getattr(base_cosmos, 'initialized', False):
        raise HTTPException(status_code=503, detail="Cosmos DB base client not initialized")

    try:
        cached_data = await eol_cache.get_cached_response(
            req.software_name,
            req.version,
            req.agent_name
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
    except Exception as e:
        logger.error("Error testing Cosmos cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error testing cache: {str(e)}")


@app.post("/api/inventory/reload")
async def reload_inventory(days: int = 90):
    """Reload inventory data from Log Analytics Workspace with EOL enrichment and refresh cache"""
    try:
        result = await get_eol_orchestrator().reload_inventory_from_law(days=days)
        logger.info("Inventory reloaded: %s items", result.get("total_items", 0))
        return result
    except Exception as e:
        logger.error("Error reloading inventory: %s", e)
        raise HTTPException(status_code=500, detail=f"Error reloading inventory: {str(e)}")


@app.post("/api/inventory/clear-cache")
async def clear_inventory_cache():
    """Clear the raw inventory data cache to force fresh data from Log Analytics Workspace"""
    try:
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
        
        result = {
            "success": True,
            "message": "Inventory cache clear requested",
            "software": software_result,
            "os": os_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info("Inventory cache cleared successfully")
        return result
        
    except Exception as e:
        logger.error("Error clearing inventory cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Error clearing inventory cache: {str(e)}")


# ============================================================================
# CHAT ENDPOINTS (Optional - only if Azure OpenAI is configured)
# ============================================================================

# @app.post("/chat")
# async def chat(req: ChatRequest):
#     """Enhanced AI chat with intelligent routing between OpenAI and specialized EOL agents"""
#     try:
#         if not config.azure.aoai_endpoint:
#             raise HTTPException(status_code=400, detail="Azure OpenAI not configured")
        
#         logger.info(f"Processing chat request: {req.message[:100]}...")
        
#         # Initialize orchestrator
#         orchestrator = EOLOrchestratorAgent()
        
#         # Handle the chat message with intelligent routing
#         logger.info("Calling orchestrator.handle_chat_message...")
#         result = await orchestrator.handle_chat_message(req.message)
#         logger.info(f"Orchestrator result: {result}")
        
#         # Communication history not implemented in current orchestrator version
#         logger.info("Communications not available in current orchestrator")
#         recent_comms = []
        
#         # Format communications for frontend
#         agent_communications = []
#         try:
#             for comm in recent_comms:
#                 agent_communications.append({
#                     "message": f"{comm.get('agent_name', 'System')}: {comm.get('action', 'action')} - {comm.get('data', {})}",
#                     "type": "agent",
#                     "timestamp": comm.get("timestamp")
#                 })
#         except Exception as e:
#             logger.error(f"Error formatting communications: {e}")
#             agent_communications = []
        
#         response_data = {
#             "response": result.get("response", "No response available"),
#             "agent_used": result.get("agent_used", "unknown"),
#             "intent": result.get("intent", "unknown"),
#             "agent_communications": agent_communications,
#             "function_calls": result.get("function_calls")
#         }
        
#         logger.info(f"Returning response: {len(response_data.get('response', ''))} chars")
#         return response_data
        
#     except Exception as e:
#         logger.error(f"Chat service error: {str(e)}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Chat service error: {str(e)}")


# API alias for frontend compatibility
# @app.post("/api/chat")
# async def api_chat(req: ChatRequest):
#     """API alias for chat endpoint to maintain frontend compatibility"""
#     return await chat(req)


# New AutoGen multi-agent chat endpoint
@app.post("/api/autogen-chat", response_model=AutoGenChatResponse)
async def autogen_chat(req: AutoGenChatRequest):
    """
    AutoGen-powered multi-agent conversation endpoint
    Enables transparent agent-to-agent communication for inventory and EOL analysis
    """
    try:
        if not CHAT_AVAILABLE:
            raise HTTPException(
                status_code=503, 
                detail="Chat orchestrator is not available. Multi-agent chat functionality requires the chat_orchestrator module."
            )
        
        # Get the chat orchestrator instance
        chat_orch = get_chat_orchestrator()
        if chat_orch is None:
            raise HTTPException(
                status_code=503, 
                detail="Chat orchestrator is not available. Multi-agent chat functionality requires the chat_orchestrator module."
            )
        
        logger.info(f"🤖 AutoGen Chat Request: {req.message[:100]}... (timeout: {req.timeout_seconds}s)")
        
        # Start multi-agent conversation with confirmation support and timeout
        # Use the minimum of the FastAPI timeout (3 minutes) and the requested timeout
        effective_timeout = min(req.timeout_seconds, 170)  # Leave 10s buffer for FastAPI
        
        result = await asyncio.wait_for(
            chat_orch.chat_with_confirmation(
                req.message, 
                confirmed=req.confirmed or False,
                original_message=req.original_message,
                timeout_seconds=req.timeout_seconds
            ),
            timeout=effective_timeout + 10  # Add buffer for FastAPI timeout
        )

        # Ensure all data is JSON serializable and limit size to prevent parsing issues
        def clean_for_json(obj):
            # logger.info("**************[Line 2496]Processing obj: %s", obj)
        
            """Clean data to ensure JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            elif isinstance(obj, str):
                # Truncate very long strings to prevent JSON parsing issues
                return obj[:10000] if len(obj) > 10000 else obj
            else:
                return str(obj) if obj is not None else None
        
        # Clean and limit the result data
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
        
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.error("AutoGen chat request timed out after 3 minutes")
        return AutoGenChatResponse(
            response="The request timed out after 3 minutes. For inventory-only requests, try using the direct inventory endpoints instead.",
            conversation_messages=[],
            agent_communications=[],
            agents_involved=[],
            total_exchanges=0,
            session_id="timeout",
            error="Request timed out after 180 seconds"
        )
    except Exception as e:
        logger.error(f"AutoGen chat error: {str(e)}", exc_info=True)
        
        # Return error response with transparency
        return AutoGenChatResponse(
            response="I encountered an error processing your request. Please try again.",
            conversation_messages=[],
            agent_communications=[],
            agents_involved=[],
            total_exchanges=0,
            session_id="error",
            error=str(e)[:1000]  # Limit error message size
        )


# Agent communications endpoint for UI
@app.get("/api/agent-communications/{session_id}")
async def get_agent_communications(session_id: str):
    """Get agent communication history for a specific session"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error retrieving agent communications: {str(e)}")
        return {"error": str(e), "communications": []}


# Debug endpoint to check agent communications
@app.get("/api/debug/agent-communications")
async def debug_agent_communications():
    """Debug endpoint to check all agent communications"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error in debug agent communications: {str(e)}")
        return {"error": str(e), "communications": []}


# Global cache for inventory context (5 minute TTL)
_inventory_context_cache = {"data": None, "timestamp": None, "ttl": 300}

async def _get_optimized_inventory_context() -> str:
    """Get optimized inventory context for chat with caching and efficient processing"""
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
            orchestrator = get_eol_orchestrator()
            
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
        logger.error("Error in optimized inventory context: %s", e)
        return "INVENTORY DATA STATUS: Service error - unable to retrieve live inventory data."


async def _get_inventory_context() -> str:
    """Get inventory context for chat"""
    try:
        analysis = await get_eol_orchestrator().analyze_inventory_eol_risks()
        
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
        logger.warning("Could not get inventory context: %s", e)
        return "INVENTORY DATA STATUS: Unable to retrieve live inventory data."


# ============================================================================
# WEB UI ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_ui(request: Request):
    """Inventory management page"""
    return templates.TemplateResponse("inventory.html", {
        "request": request,
        "subscription_id": config.azure.subscription_id,
        "resource_group": config.azure.resource_group_name
    })


@app.get("/eol-search", response_class=HTMLResponse)
async def eol_ui(request: Request):
    """EOL search page"""
    return templates.TemplateResponse("eol.html", {"request": request})


@app.get("/eol-searches", response_class=HTMLResponse)
async def eol_searches_ui(request: Request):
    """EOL search history page"""
    return templates.TemplateResponse("eol-searches.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    """Chat interface page"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/cache", response_class=HTMLResponse)
async def cache_ui(request: Request):
    """Cache management interface page with enhanced agent statistics"""
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
        
        return templates.TemplateResponse("cache.html", {
            "request": request,
            "cache_stats": cache_stats
        })
    except Exception as e:
        logger.error(f"Error loading cache UI: {e}")
        return templates.TemplateResponse("cache.html", {
            "request": request,
            "cache_stats": {"error": str(e)}
        })


@app.get("/agent-cache-details", response_class=HTMLResponse)
async def agent_cache_details(request: Request, agent_name: Optional[str] = None):
    """Agent cache details page with granular URL performance monitoring"""
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
        
        return templates.TemplateResponse("agent-cache-details.html", {
            "request": request,
            "agent_stats": filtered_stats,
            "selected_agent": agent_name
        })
    except Exception as e:
        logger.error(f"Error loading agent cache details: {e}")
        return templates.TemplateResponse("agent-cache-details.html", {
            "request": request,
            "agent_stats": {"error": str(e)},
            "selected_agent": agent_name
        })


@app.get("/agents", response_class=HTMLResponse)
async def agent_management_ui(request: Request):
    """Agent management interface page"""
    return templates.TemplateResponse("agents.html", {"request": request})


# ============================================================================
# AGENT MANAGEMENT API ENDPOINTS
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


@app.get("/api/agents/list")
async def list_agents():
    """Get list of all agents with their statistics and URLs"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/agents/add-url")
async def add_agent_url(request: AgentUrlRequest):
    """Add URL to an agent"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error adding URL to agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/agents/remove-url")
async def remove_agent_url(request: AgentUrlRequest):
    """Remove URL from an agent"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error removing URL from agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/agents/toggle")
async def toggle_agent(request: AgentToggleRequest):
    """Toggle agent active status"""
    try:
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
        
    except Exception as e:
        logger.error(f"Error toggling agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/validate-cache")
async def validate_cache_system():
    """Remote validation endpoint for cache system functionality"""
    import sys
    import os
    from datetime import datetime
    
    validation_results = {
        "timestamp": datetime.now().isoformat(),
        "environment": {
            "python_version": sys.version,
            "working_directory": os.getcwd()
        },
        "dependencies": {},
        "cache_modules": {},
        "agents": {},
        "summary": {}
    }
    
    # Test dependencies
    dependencies = ['requests', 'aiohttp', 'beautifulsoup4', 'azure.cosmos', 'azure.identity', 'fastapi']
    working_deps = 0
    
    for dep in dependencies:
        try:
            if '.' in dep:
                parts = dep.split('.')
                module = __import__(parts[0])
                for part in parts[1:]:
                    module = getattr(module, part)
            else:
                __import__(dep)
            validation_results["dependencies"][dep] = {"status": "available", "error": None}
            working_deps += 1
        except ImportError as e:
            validation_results["dependencies"][dep] = {"status": "missing", "error": str(e)}
    
    # Test cache modules
    cache_results = {}
    
    try:
        from utils.cosmos_cache import base_cosmos
        from utils.eol_cache import eol_cache
        validation_results["cache_modules"]["base_cosmos"] = {
            "status": "available",
            "initialized": getattr(base_cosmos, 'initialized', False),
            "last_error": getattr(base_cosmos, 'last_error', None)
        }
        validation_results["cache_modules"]["eol_cache"] = {
            "status": "available",
            "initialized": getattr(eol_cache, 'initialized', False),
            "memory_cache_size": len(getattr(eol_cache, 'memory_cache', {}))
        }
        cache_results['cosmos'] = True
    except Exception as e:
        validation_results["cache_modules"]["base_cosmos"] = {
            "status": "failed",
            "error": str(e)
        }
        cache_results['cosmos'] = False
    
    try:
        from utils.inventory_cache import inventory_cache
        validation_results["cache_modules"]["inventory_cache"] = {
            "status": "working",
            "initialized": getattr(inventory_cache, 'initialized', False),
            "details": {
                "cache_duration_hours": getattr(inventory_cache, 'cache_duration_hours', 'N/A')
            }
        }
        cache_results['inventory'] = True
    except Exception as e:
        validation_results["cache_modules"]["inventory_cache"] = {
            "status": "failed",
            "error": str(e)
        }
        cache_results['inventory'] = False
    
    # Test agents
    agents = [
        ('microsoft_agent', 'MicrosoftEOLAgent'),
        ('endoflife_agent', 'EndOfLifeAgent'),
        ('ubuntu_agent', 'UbuntuEOLAgent'),
        ('redhat_agent', 'RedHatEOLAgent'),
        ('azure_ai_agent', 'AzureAIAgentEOLAgent'),
        ('websurfer_agent', 'WebsurferEOLAgent')
    ]
    
    working_agents = 0
    for module_name, class_name in agents:
        try:
            module = __import__(f'agents.{module_name}', fromlist=[class_name])
            agent_class = getattr(module, class_name)
            agent = agent_class()
            
            # Check cache support
            cache_attributes = ['cache_ttl', 'cache_duration_hours', '_cache', 'get_cached_response']
            found_cache_methods = [attr for attr in cache_attributes if hasattr(agent, attr)]
            
            validation_results["agents"][class_name] = {
                "status": "functional",
                "cache_support": len(found_cache_methods) > 0,
                "cache_methods": found_cache_methods
            }
            working_agents += 1
        except Exception as e:
            validation_results["agents"][class_name] = {
                "status": "failed",
                "error": str(e)
            }
    
    # Environment variables
    env_vars = ['AZURE_COSMOS_ENDPOINT', 'AZURE_COSMOS_DATABASE', 'AZURE_COSMOS_CONTAINER']
    env_status = {}
    for var in env_vars:
        env_status[var] = bool(os.getenv(var))
    
    validation_results["environment"]["variables"] = env_status
    
    # Calculate summary scores
    dep_score = working_deps / len(dependencies) * 100
    cache_score = sum(cache_results.values()) / len(cache_results) * 100
    agent_score = working_agents / len(agents) * 100
    overall_score = (dep_score + cache_score + agent_score) / 3
    
    validation_results["summary"] = {
        "dependencies_score": f"{dep_score:.1f}%",
        "cache_modules_score": f"{cache_score:.1f}%", 
        "agents_score": f"{agent_score:.1f}%",
        "overall_score": f"{overall_score:.1f}%",
        "status": "excellent" if overall_score >= 80 else "good" if overall_score >= 60 else "partial" if overall_score >= 40 else "critical",
        "working_components": {
            "dependencies": f"{working_deps}/{len(dependencies)}",
            "cache_modules": f"{sum(cache_results.values())}/{len(cache_results)}",
            "agents": f"{working_agents}/{len(agents)}"
        }
    }
    
    return validation_results


# ============================================================================
# NOTIFICATION HISTORY API ENDPOINTS
# ============================================================================

@app.get("/api/notifications/history")
async def get_notification_history(
    alert_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Get notification history with optional filtering.
    
    Args:
        alert_type: Filter by alert type ('critical', 'warning', 'info') or None for all
        limit: Maximum number of records to return (default: 100, max: 1000)
        offset: Number of records to skip for pagination (default: 0)
    """
    try:
        # Import alert manager
        from utils.alert_manager import alert_manager
        
        # Validate parameters
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 1
        if offset < 0:
            offset = 0
        if alert_type and alert_type not in ['critical', 'warning', 'info']:
            raise HTTPException(status_code=400, detail="Invalid alert_type. Must be 'critical', 'warning', or 'info'")
        
        # Get notification history
        history = await alert_manager.get_notification_history(
            alert_type=alert_type,
            limit=limit,
            offset=offset
        )
        
        return {
            "success": True,
            "notifications": [notification.dict() for notification in history.notifications],
            "statistics": {
                "total_count": history.total_count,
                "successful_count": history.successful_count,
                "failed_count": history.failed_count,
                "last_notification_date": history.last_notification_date
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(history.notifications) == limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving notification history: {e}")
        return create_error_response(
            f"Failed to retrieve notification history: {str(e)}", 
            500
        )

@app.get("/api/notifications/stats")
async def get_notification_stats():
    """
    Get notification statistics summary.
    """
    try:
        from utils.alert_manager import alert_manager
        
        # Get recent history for stats calculation
        history = await alert_manager.get_notification_history(limit=1000)
        
        # Calculate additional statistics
        now = datetime.utcnow()
        last_7_days = [n for n in history.notifications 
                      if (now - datetime.fromisoformat(n.timestamp.replace('Z', ''))).days <= 7]
        last_30_days = [n for n in history.notifications 
                       if (now - datetime.fromisoformat(n.timestamp.replace('Z', ''))).days <= 30]
        
        stats_by_type = {}
        for alert_type in ['critical', 'warning', 'info']:
            type_notifications = [n for n in history.notifications if n.alert_type == alert_type]
            stats_by_type[alert_type] = {
                "total": len(type_notifications),
                "successful": len([n for n in type_notifications if n.status == 'success']),
                "failed": len([n for n in type_notifications if n.status == 'failed']),
                "last_sent": type_notifications[0].timestamp if type_notifications else None
            }
        
        return {
            "success": True,
            "overall": {
                "total_notifications": history.total_count,
                "successful_notifications": history.successful_count,
                "failed_notifications": history.failed_count,
                "success_rate": round((history.successful_count / max(history.total_count, 1)) * 100, 1),
                "last_notification_date": history.last_notification_date
            },
            "recent_activity": {
                "last_7_days": len(last_7_days),
                "last_30_days": len(last_30_days)
            },
            "by_alert_type": stats_by_type
        }
        
    except Exception as e:
        logger.error(f"Error retrieving notification stats: {e}")
        return create_error_response(
            f"Failed to retrieve notification statistics: {str(e)}", 
            500
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
