"""
Debug & Diagnostics API Module

This module provides endpoints for debugging, testing, validation, and diagnostics
of the EOL application components, including notifications management.

Features:
- Tool selection debugging for the Microsoft inventory assistant orchestrator
- Logging functionality testing
- Cosmos DB connection testing
- Comprehensive cache system validation
- Notification history and statistics
- Agent and dependency validation
- Environment variable checks

Endpoints:
    POST /api/debug_tool_selection - Debug inventory assistant tool selection logic
    GET  /api/test-logging - Test logging functionality
    GET  /api/cosmos/test - Test Cosmos DB connection
    GET  /api/validate-cache - Comprehensive cache system validation
    GET  /api/notifications/history - Get notification history with filtering
    GET  /api/notifications/stats - Get notification statistics summary
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
import logging
import sys
import os
import uuid
import re

from pydantic import BaseModel
from utils.endpoint_decorators import readonly_endpoint, write_endpoint
from utils.response_models import StandardResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_eol_orchestrator():
    """Lazy getter to avoid import cycles when pulling the EOL orchestrator."""
    from main import get_eol_orchestrator

    return get_eol_orchestrator()


class DebugRequest(BaseModel):
    """Request model for debug endpoints"""
    query: str


@router.post('/api/debug_tool_selection', response_model=StandardResponse)
@readonly_endpoint(agent_name="debug_tool_selection", timeout_seconds=15)
async def debug_tool_selection(request: DebugRequest):
    """
    Debug endpoint to test tool selection logic for the Microsoft inventory assistant orchestrator.
    
    Tests the pattern matching and tool selection logic used by the inventory assistant orchestrator
    to determine which functions to call based on user queries. Useful for debugging
    and improving tool selection accuracy.
    
    Args:
        request: DebugRequest containing the query to analyze
    
    Returns:
        StandardResponse with detected patterns, keywords, and recommended tool selection.
        
    Example Request:
        POST /api/debug_tool_selection
        {
            "query": "Show me Windows Server 2012 end of life date"
        }
        
    Example Response:
        {
            "query": "Show me Windows Server 2012 end of life date",
            "intent_analysis": {
                "is_inventory_query": false,
                "is_eol_query": true,
                "is_approaching_eol_query": false,
                "matched_eol_patterns": ["eol", "end of life"],
                ...
            },
            "detected_software": "windows",
            "detected_version": "2012",
            "primary_tool": "check_software_eol",
            "tool_choice": {"type": "function", "function": {"name": "check_software_eol"}},
            "would_force_tool": true
        }
    """
    from utils import QueryPatterns
    
    query = request.query
    
    # Use centralized QueryPatterns for analysis
    intent_analysis = QueryPatterns.analyze_query_intent(query)
    
    # Extract matched patterns for backward compatibility
    found_inventory_keywords = intent_analysis["matched_inventory_patterns"]
    found_eol_keywords = intent_analysis["matched_eol_patterns"]
    found_approaching_eol_keywords = intent_analysis["matched_approaching_patterns"]
    
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
    
    # Determine tool choice using centralized intent analysis
    tool_choice = "auto"
    primary_tool = None
    
    if intent_analysis["is_approaching_eol_query"]:
        tool_choice = {"type": "function", "function": {"name": "find_approaching_eol"}}
        primary_tool = "find_approaching_eol"
    elif intent_analysis["is_eol_query"]:
        tool_choice = {"type": "function", "function": {"name": "check_software_eol"}}
        primary_tool = "check_software_eol"
    elif intent_analysis["is_inventory_query"]:
        tool_choice = {"type": "function", "function": {"name": "get_inventory"}}
        primary_tool = "get_inventory"
    
    return {
        'query': query,
        'intent_analysis': intent_analysis,  # Include full analysis
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


@router.get("/api/test-logging", response_model=StandardResponse)
@readonly_endpoint(agent_name="test_logging", timeout_seconds=15)
async def test_logging():
    """
    Test logging functionality for Azure App Service debugging.
    
    Generates test log messages at all levels (debug, info, warning, error)
    and validates logger configuration. Useful for troubleshooting Azure
    App Service log streaming.
    
    Returns:
        StandardResponse with test results, logger configuration, and environment info.
        
    Example Response:
        {
            "test_completed": true,
            "test_id": "a1b2c3d4",
            "timestamp": "2025-01-15T10:30:00Z",
            "environment": "Azure App Service",
            "main_logger": {
                "name": "__main__",
                "level": 20,
                "handler_count": 2
            },
            "message": "Logging test completed. Check Azure App Service logs for messages with ID [a1b2c3d4]"
        }
    """
    timestamp = datetime.utcnow().isoformat()
    test_id = str(uuid.uuid4())[:8]
    
    # Test main app logger
    logger.debug(f"🧪 MAIN-DEBUG Test Log [{test_id}] - {timestamp}")
    logger.info(f"🧪 MAIN-INFO Test Log [{test_id}] - {timestamp}")
    logger.warning(f"🧪 MAIN-WARNING Test Log [{test_id}] - {timestamp}")
    logger.error(f"🧪 MAIN-ERROR Test Log [{test_id}] - {timestamp}")
    
    # Test inventory assistant orchestrator logging if available
    # EOL interface uses only regular orchestrator
    inventory_asst_test_result = None
    
    # Force flush for Azure
    if os.environ.get('WEBSITE_SITE_NAME'):
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
        "inventory_assistant_test": inventory_asst_test_result,
        "message": f"Logging test completed. Check Azure App Service logs for messages with ID [{test_id}]"
    }
    
    logger.info(f"🧪 Logging test result: {result}")
    return result


@router.get("/api/cosmos/test", response_model=StandardResponse)
@readonly_endpoint(agent_name="cosmos_connection_test", timeout_seconds=30)
async def test_cosmos_connection():
    """
    Test Cosmos DB connection for diagnostic purposes.
    
    Performs a comprehensive test of Cosmos DB connectivity including initialization
    check, container access, and basic read operations. Useful for troubleshooting
    Cosmos DB connection issues.
    
    Returns:
        StandardResponse with connection test results and detailed diagnostic information.
        
    Example Response (Success):
        {
            "success": true,
            "message": "Cosmos DB connection successful",
            "details": {
                "initialized": true,
                "test_operation": "Container access successful",
                "note": "NotFound error for test item is expected"
            }
        }
        
    Example Response (Failure):
        {
            "success": false,
            "message": "Cosmos DB initialization failed: Connection timeout",
            "details": {
                "initialized": false,
                "last_error": "Connection timeout",
                "cosmos_client": "<class 'NoneType'>",
                "database": "<class 'NoneType'>"
            }
        }
    """
    from utils.cosmos_cache import base_cosmos
    
    # Check if base client is initialized
    if not base_cosmos.initialized:
        logger.info("🔄 Base Cosmos client not initialized, attempting initialization...")
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
                    "error": str(container_error)
                }
            }
    
    return {
        "success": True,
        "message": "Cosmos DB fully functional",
        "details": {
            "initialized": True,
            "test_operation": "Complete"
        }
    }


@router.get("/api/validate-cache", response_model=StandardResponse)
@readonly_endpoint(agent_name="validate_cache", timeout_seconds=30)
async def validate_cache_system():
    """
    Comprehensive validation of cache system functionality.
    
    Performs thorough validation including:
    - Dependency availability (requests, aiohttp, azure.cosmos, etc.)
    - Cache module status (base_cosmos, eol_cache, inventory_cache)
    - Agent functionality and cache support
    - Environment variable configuration
    - Overall system health scoring
    
    Returns:
        StandardResponse with detailed validation results and component health scores.
        
    Example Response:
        {
            "timestamp": "2025-01-15T10:30:00Z",
            "environment": {
                "python_version": "3.11.5",
                "working_directory": "/app",
                "variables": {
                    "AZURE_COSMOS_ENDPOINT": true,
                    "AZURE_COSMOS_DATABASE": true,
                    "AZURE_COSMOS_CONTAINER": true
                }
            },
            "dependencies": {
                "requests": {"status": "available", "error": null},
                "aiohttp": {"status": "available", "error": null},
                "azure.cosmos": {"status": "available", "error": null},
                ...
            },
            "cache_modules": {
                "base_cosmos": {
                    "status": "available",
                    "initialized": true,
                    "last_error": null
                },
                ...
            },
            "agents": {
                "MicrosoftEOLAgent": {
                    "status": "functional",
                    "cache_support": true,
                    "cache_methods": ["cache_ttl", "get_cached_response"]
                },
                ...
            },
            "summary": {
                "dependencies_score": "100.0%",
                "cache_modules_score": "100.0%",
                "agents_score": "100.0%",
                "overall_score": "100.0%",
                "status": "excellent",
                "working_components": {
                    "dependencies": "6/6",
                    "cache_modules": "3/3",
                    "agents": "6/6"
                }
            }
        }
    """
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
        from utils.eol_inventory import eol_inventory
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
        validation_results["cache_modules"]["eol_inventory"] = {
            "status": "available",
            "initialized": getattr(eol_inventory, 'initialized', False),
            "hits": eol_inventory.get_stats().get("hits", 0) if hasattr(eol_inventory, "get_stats") else 0,
            "misses": eol_inventory.get_stats().get("misses", 0) if hasattr(eol_inventory, "get_stats") else 0,
            "container": getattr(eol_inventory, 'container_id', 'eol_inventory')
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
        ('azure_ai_agent', 'AzureAIAgentEOLAgent')
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


@router.get("/api/eol-cache-stats", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_cache_stats", timeout_seconds=15)
async def get_eol_cache_stats():
    """Expose hit/miss statistics for the Cosmos-backed EOL inventory and legacy cache."""
    try:
        from utils.eol_inventory import eol_inventory
        from utils.eol_cache import eol_cache
        table_stats = eol_inventory.get_stats() if hasattr(eol_inventory, "get_stats") else {"hits": 0, "misses": 0}

        legacy_cache_size = len(getattr(eol_cache, "memory_cache", {})) if hasattr(eol_cache, "memory_cache") else 0
        return {
            "success": True,
            "data": {
                "eol_inventory": {
                    "container": getattr(eol_inventory, "container_id", "eol_inventory"),
                    "initialized": getattr(eol_inventory, "initialized", False),
                    "hits": table_stats.get("hits", 0),
                    "misses": table_stats.get("misses", 0),
                },
                "eol_cache_memory": {
                    "initialized": getattr(eol_cache, "initialized", False),
                    "memory_entries": legacy_cache_size,
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.debug("EOL cache stats failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/api/eol-latency", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_latency", timeout_seconds=15)
async def get_eol_latency(limit: int = 20, agent: Optional[str] = None):
    """Return recent orchestrator EOL timings for quick dashboarding."""
    try:
        orch = _get_eol_orchestrator()
        responses = orch.get_eol_agent_responses() if orch else []

        limit = max(1, min(limit, 100))
        filtered = responses if not agent else [r for r in responses if r.get("agent_name") == agent]
        trimmed = list(reversed(filtered[-limit:]))  # newest first

        latencies = [r.get("response_time") for r in trimmed if isinstance(r.get("response_time"), (int, float))]
        latencies_ms = [round(v * 1000, 2) for v in latencies]

        def percentile(values, pct):
            if not values:
                return None
            sorted_vals = sorted(values)
            k = (len(sorted_vals) - 1) * (pct / 100)
            f = int(k)
            c = min(f + 1, len(sorted_vals) - 1)
            if f == c:
                return sorted_vals[f]
            return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

        stats = {
            "count": len(latencies_ms),
            "avg_ms": round(sum(latencies_ms) / len(latencies_ms), 2) if latencies_ms else None,
            "p50_ms": round(percentile(latencies_ms, 50), 2) if latencies_ms else None,
            "p95_ms": round(percentile(latencies_ms, 95), 2) if latencies_ms else None,
            "max_ms": max(latencies_ms) if latencies_ms else None,
        }

        recent = [
            {
                "timestamp": r.get("timestamp"),
                "agent_name": r.get("agent_name"),
                "software_name": r.get("software_name"),
                "software_version": r.get("software_version"),
                "query_type": r.get("query_type"),
                "success": r.get("success"),
                "response_time_ms": round(r.get("response_time") * 1000, 2) if isinstance(r.get("response_time"), (int, float)) else None,
                "confidence": r.get("confidence"),
            }
            for r in trimmed
        ]

        return {
            "success": True,
            "data": {
                "stats": stats,
                "recent": recent,
                "filter": {"agent": agent, "limit": limit},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.debug("EOL latency stats failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/api/notifications/history", response_model=StandardResponse)
@readonly_endpoint(agent_name="notification_history", timeout_seconds=20)
async def get_notification_history(
    alert_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Get notification history with optional filtering.
    
    Retrieves historical notification records from Cosmos DB with support
    for filtering by alert type and pagination.
    
    Args:
        alert_type: Filter by alert type ('critical', 'warning', 'info') or None for all
        limit: Maximum number of records to return (default: 100, max: 1000)
        offset: Number of records to skip for pagination (default: 0)
    
    Returns:
        StandardResponse with notification list, statistics, and pagination info.
        
    Example Request:
        GET /api/notifications/history?alert_type=critical&limit=50&offset=0
        
    Example Response:
        {
            "success": true,
            "notifications": [
                {
                    "id": "notif_abc123",
                    "alert_type": "critical",
                    "subject": "Critical: Windows Server 2012 EOL",
                    "recipients": ["admin@company.com"],
                    "status": "success",
                    "timestamp": "2025-01-15T10:30:00Z"
                }
            ],
            "statistics": {
                "total_count": 245,
                "successful_count": 240,
                "failed_count": 5,
                "last_notification_date": "2025-01-15T10:30:00Z"
            },
            "pagination": {
                "limit": 50,
                "offset": 0,
                "has_more": true
            }
        }
    """
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


@router.get("/api/notifications/stats", response_model=StandardResponse)
@readonly_endpoint(agent_name="notification_stats", timeout_seconds=20)
async def get_notification_stats():
    """
    Get notification statistics summary.
    
    Calculates comprehensive statistics about notification history including
    success rates, activity trends, and breakdowns by alert type.
    
    Returns:
        StandardResponse with overall stats, recent activity, and per-type statistics.
        
    Example Response:
        {
            "success": true,
            "overall": {
                "total_notifications": 1250,
                "successful_notifications": 1235,
                "failed_notifications": 15,
                "success_rate": 98.8,
                "last_notification_date": "2025-01-15T10:30:00Z"
            },
            "recent_activity": {
                "last_7_days": 45,
                "last_30_days": 180
            },
            "by_alert_type": {
                "critical": {
                    "total": 120,
                    "successful": 118,
                    "failed": 2,
                    "last_sent": "2025-01-15T10:30:00Z"
                },
                "warning": {
                    "total": 580,
                    "successful": 575,
                    "failed": 5,
                    "last_sent": "2025-01-15T09:15:00Z"
                },
                "info": {
                    "total": 550,
                    "successful": 542,
                    "failed": 8,
                    "last_sent": "2025-01-15T08:00:00Z"
                }
            }
        }
    """
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
