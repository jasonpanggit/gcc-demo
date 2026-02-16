"""SRE Orchestrator API Router.

Provides REST API endpoints for the SRE Orchestrator Agent.

Endpoints:
- POST /api/sre-orchestrator/execute - Execute SRE request with natural language
- GET /api/sre-orchestrator/capabilities - List orchestrator capabilities
- GET /api/sre-orchestrator/tools - List all registered tools
- GET /api/sre-orchestrator/tools/{tool_name} - Get specific tool details
- GET /api/sre-orchestrator/agents - List all registered agents
- GET /api/sre-orchestrator/health - Health check
- GET /api/sre-orchestrator/metrics - Orchestrator metrics
- POST /api/sre-orchestrator/incident - Execute incident response workflow
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from app.agentic.eol.agents.sre_orchestrator_agent import SREOrchestratorAgent
    from app.agentic.eol.agents.incident_response_agent import IncidentResponseAgent
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.response_models import StandardResponse
except ModuleNotFoundError:
    from agents.sre_orchestrator_agent import SREOrchestratorAgent
    from agents.incident_response_agent import IncidentResponseAgent
    from utils.agent_registry import get_agent_registry
    from utils.logger import get_logger
    from utils.response_models import StandardResponse


logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/sre-orchestrator",
    tags=["SRE Orchestrator"],
    responses={
        404: {"description": "Resource not found"},
        500: {"description": "Internal server error"}
    }
)


# ============================================================================
# Request/Response Models
# ============================================================================

class SREExecuteRequest(BaseModel):
    """Request model for SRE orchestrator execution."""

    query: str = Field(
        ...,
        description="Natural language query describing the SRE operation",
        example="Check health of all container apps in production"
    )
    context: Optional[Dict[str, Any]] = Field(
        default={},
        description="Optional context parameters (subscription_id, resource_group, etc.)"
    )
    stream: bool = Field(
        default=False,
        description="Enable server-sent events for progress streaming"
    )


class IncidentRequest(BaseModel):
    """Request model for incident response workflow."""

    incident_id: str = Field(
        ...,
        description="Unique incident identifier",
        example="INC-001"
    )
    action: str = Field(
        default="triage",
        description="Action to perform: triage, correlate, impact, rca, remediate, postmortem, full",
        example="triage"
    )
    description: Optional[str] = Field(
        default="",
        description="Incident description",
        example="API gateway returning 500 errors"
    )
    severity: Optional[str] = Field(
        default="medium",
        description="Incident severity: critical, high, medium, low",
        example="high"
    )
    resource_ids: Optional[List[str]] = Field(
        default=[],
        description="Affected Azure resource IDs"
    )
    context: Optional[Dict[str, Any]] = Field(
        default={},
        description="Additional context parameters"
    )


class ToolFilter(BaseModel):
    """Query parameters for filtering tools."""

    category: Optional[str] = Field(
        None,
        description="Filter by category (health, incident, cost, etc.)"
    )
    agent_id: Optional[str] = Field(
        None,
        description="Filter by agent ID"
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/execute", response_model=StandardResponse)
async def execute_sre_request(request: SREExecuteRequest):
    """Execute SRE operation with natural language query.

    This endpoint accepts natural language queries and routes them to the
    appropriate SRE tools. The orchestrator analyzes the intent, selects
    relevant tools, executes them, and returns aggregated results.

    Example queries:
    - "Check health of all container apps"
    - "Find orphaned resources and estimate savings"
    - "Show me performance metrics for the API"
    - "Triage incident #123"
    - "Check SLO compliance for my-service"
    - "Get security recommendations"

    Args:
        request: SRE execution request with query and optional context

    Returns:
        StandardResponse with execution results (may include user interaction prompts)

    Raises:
        HTTPException: If execution fails
    """
    logger.info(f"Executing SRE request: {request.query[:100]}")

    orchestrator = None
    try:
        # Create and initialize orchestrator
        orchestrator = SREOrchestratorAgent()
        initialized = await orchestrator.initialize()

        if not initialized:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize SRE orchestrator"
            )

        # Execute request
        result = await orchestrator.handle_request({
            "query": request.query,
            **request.context
        })

        # Check execution status
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )

        # Extract results
        results_data = result.get("results", {})

        # Check if user interaction is required
        if results_data.get("user_interaction_required"):
            interaction_data = results_data.get("interaction_data", {})

            # Return user interaction prompt
            return StandardResponse(
                success=True,
                data={
                    "interaction_required": True,
                    "interaction_type": interaction_data.get("selection_type", "input"),
                    "message": interaction_data.get("message", "User input required"),
                    "options": interaction_data.get("options", []),
                    "workflow_id": result.get("workflow_id")
                },
                message="User interaction required to complete operation"
            )

        # Check if formatted response exists
        formatted_response = results_data.get("formatted_response")
        if formatted_response:
            # Return formatted HTML response
            return StandardResponse(
                success=True,
                data={
                    "formatted_html": formatted_response,
                    "raw_results": results_data.get("results", []),
                    "summary": results_data.get("summary", {}),
                    "workflow_id": result.get("workflow_id")
                },
                message=f"Successfully processed query: {request.query[:50]}..."
            )

        # Return raw results if no formatting
        return StandardResponse(
            success=True,
            data=results_data,
            message=f"Successfully processed query"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to execute SRE request: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(exc)}"
        )
    finally:
        if orchestrator:
            await orchestrator.cleanup()


@router.get("/capabilities", response_model=StandardResponse)
async def get_capabilities():
    """Get SRE orchestrator capabilities.

    Returns information about the orchestrator's capabilities including:
    - Supported intent categories
    - Available tools by category
    - Total number of agents and tools
    - Orchestrator version

    Returns:
        StandardResponse with capabilities information
    """
    logger.info("Getting orchestrator capabilities")

    orchestrator = None
    try:
        orchestrator = SREOrchestratorAgent()
        await orchestrator.initialize()

        capabilities = orchestrator.get_capabilities()
        
        # Transform tools_by_category into the format expected by frontend
        # Convert tool name strings to objects with name and description
        registry = get_agent_registry()
        all_tools = {tool["name"]: tool for tool in registry.list_tools()}
        
        formatted_categories = {}
        for category, tool_names in capabilities.get("tools_by_category", {}).items():
            formatted_categories[category] = []
            for tool_name in tool_names:
                tool_info = all_tools.get(tool_name, {})
                tool_def = tool_info.get("definition", {})
                func_info = tool_def.get("function", {})
                formatted_categories[category].append({
                    "name": tool_name,
                    "description": func_info.get("description", "No description available"),
                    "agent_id": tool_info.get("agent_id", "unknown")
                })
        
        # Update capabilities with formatted categories
        capabilities["categories"] = formatted_categories
        # Remove tools_by_category as it's now included in categories
        capabilities.pop("tools_by_category", None)

        return StandardResponse(
            success=True,
            data=capabilities,
            message="Orchestrator capabilities retrieved"
        )

    except Exception as exc:
        logger.error(f"Failed to get capabilities: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve capabilities: {str(exc)}"
        )
    finally:
        if orchestrator:
            await orchestrator.cleanup()


@router.get("/tools", response_model=StandardResponse)
async def list_tools(
    category: Optional[str] = Query(None, description="Filter by category"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID")
):
    """List all registered SRE tools.

    Returns a list of all tools registered with the orchestrator, optionally
    filtered by category or agent ID.

    Categories:
    - health: Health monitoring and diagnostics
    - incident: Incident management and triage
    - performance: Performance analysis and optimization
    - cost: Cost analysis and optimization
    - slo: SLO/SLI tracking and error budgets
    - security: Security scanning and compliance
    - remediation: Automated remediation actions
    - config: Configuration management

    Args:
        category: Optional category filter
        agent_id: Optional agent ID filter

    Returns:
        StandardResponse with list of tools
    """
    logger.info(f"Listing tools (category={category}, agent_id={agent_id})")

    try:
        registry = get_agent_registry()

        # Get tools with filters
        tools = registry.list_tools(category=category, agent_id=agent_id)

        # Format tool information
        tool_list = [
            {
                "name": tool["name"],
                "agent_id": tool["agent_id"],
                "agent_type": tool["agent_type"],
                "description": tool["definition"].get("function", {}).get("description", ""),
                "registered_at": tool["registered_at"]
            }
            for tool in tools
        ]

        return StandardResponse(
            success=True,
            data={
                "total": len(tool_list),
                "filters": {"category": category, "agent_id": agent_id},
                "tools": tool_list
            },
            message=f"Found {len(tool_list)} tool(s)"
        )

    except Exception as exc:
        logger.error(f"Failed to list tools: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tools: {str(exc)}"
        )


@router.get("/tools/{tool_name}", response_model=StandardResponse)
async def get_tool_details(tool_name: str):
    """Get detailed information about a specific tool.

    Args:
        tool_name: Name of the tool to retrieve

    Returns:
        StandardResponse with tool details including parameters and schema
    """
    logger.info(f"Getting details for tool: {tool_name}")

    try:
        registry = get_agent_registry()

        # Get tool definition
        tool_info = registry.get_tool(tool_name)

        if not tool_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool '{tool_name}' not found"
            )

        return StandardResponse(
            success=True,
            data=tool_info,
            message=f"Tool details for '{tool_name}'"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get tool details: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tool details: {str(exc)}"
        )


@router.get("/agents", response_model=StandardResponse)
async def list_agents():
    """List all registered agents.

    Returns information about all agents registered with the orchestrator
    including their health status, type, and metadata.

    Returns:
        StandardResponse with list of agents
    """
    logger.info("Listing registered agents")

    try:
        registry = get_agent_registry()

        # Get all agents
        agents = registry.list_agents()

        # Format agent information
        agent_list = [
            {
                "agent_id": agent["agent_id"],
                "agent_type": agent["agent_type"],
                "initialized": agent["initialized"],
                "healthy": agent["health"]["healthy"],
                "status": agent["metadata"].get("status", "unknown"),
                "registered_at": agent["metadata"].get("registered_at", ""),
                "metadata": agent.get("metadata", {})
            }
            for agent in agents
        ]

        return StandardResponse(
            success=True,
            data={
                "total": len(agent_list),
                "agents": agent_list
            },
            message=f"Found {len(agent_list)} agent(s)"
        )

    except Exception as exc:
        logger.error(f"Failed to list agents: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(exc)}"
        )


@router.get("/health", response_model=StandardResponse)
async def health_check():
    """Health check endpoint.

    Checks the health of the orchestrator and its dependencies:
    - Agent registry status
    - Number of registered agents and tools
    - Overall system health

    Returns:
        StandardResponse with health status
    """
    logger.info("Performing health check")

    try:
        registry = get_agent_registry()
        stats = registry.get_registry_stats()

        # Determine health status
        health_status = "healthy"
        if stats["healthy_agents"] == 0:
            health_status = "degraded"
        if stats["total_tools"] == 0:
            health_status = "unhealthy"

        return StandardResponse(
            success=True,
            data={
                "status": health_status,
                "timestamp": datetime.utcnow().isoformat(),
                "registry": {
                    "total_agents": stats["total_agents"],
                    "healthy_agents": stats["healthy_agents"],
                    "total_tools": stats["total_tools"],
                    "tool_categories": stats["tool_categories"]
                }
            },
            message=f"Orchestrator is {health_status}"
        )

    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        return StandardResponse(
            success=False,
            data={
                "status": "unhealthy",
                "error": str(exc)
            },
            message="Health check failed"
        )


@router.get("/metrics", response_model=StandardResponse)
async def get_metrics():
    """Get orchestrator metrics.

    Returns operational metrics for the orchestrator including:
    - Request counts (handled, succeeded, failed)
    - Success rate
    - Average execution time
    - Agent-specific metrics

    Returns:
        StandardResponse with metrics data
    """
    logger.info("Getting orchestrator metrics")

    orchestrator = None
    try:
        orchestrator = SREOrchestratorAgent()
        await orchestrator.initialize()

        metrics = orchestrator.get_metrics()

        return StandardResponse(
            success=True,
            data=metrics,
            message="Orchestrator metrics retrieved"
        )

    except Exception as exc:
        logger.error(f"Failed to get metrics: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(exc)}"
        )
    finally:
        if orchestrator:
            await orchestrator.cleanup()


@router.post("/incident", response_model=StandardResponse)
async def handle_incident(request: IncidentRequest):
    """Execute incident response workflow.

    Handles incident response workflows including:
    - triage: Initial incident triage and severity assessment
    - correlate: Alert correlation and pattern detection
    - impact: Impact assessment and blast radius calculation
    - rca: Root cause analysis
    - remediate: Remediation recommendations
    - postmortem: Postmortem generation
    - full: Complete incident response workflow (all phases)

    Args:
        request: Incident request with action and parameters

    Returns:
        StandardResponse with incident response results
    """
    logger.info(f"Handling incident {request.incident_id} - action: {request.action}")

    agent = None
    try:
        # Create and initialize incident response agent
        agent = IncidentResponseAgent()
        initialized = await agent.initialize()

        if not initialized:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize incident response agent"
            )

        # Execute incident action
        result = await agent.handle_request({
            "action": request.action,
            "incident_id": request.incident_id,
            "description": request.description,
            "severity": request.severity,
            "resource_ids": request.resource_ids,
            **request.context
        })

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )

        return StandardResponse(
            success=True,
            data=result,
            message=f"Incident {request.incident_id} - {request.action} completed"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Incident handling failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Incident handling failed: {str(exc)}"
        )
    finally:
        if agent:
            await agent.cleanup()


@router.get("/categories", response_model=StandardResponse)
async def list_categories():
    """List all tool categories.

    Returns a list of all available tool categories with counts.

    Returns:
        StandardResponse with category information
    """
    logger.info("Listing tool categories")

    try:
        registry = get_agent_registry()
        categories = registry.get_tool_categories()

        # Get count for each category
        category_counts = {}
        for category in categories:
            tools = registry.list_tools(category=category)
            category_counts[category] = len(tools)

        return StandardResponse(
            success=True,
            data={
                "categories": categories,
                "counts": category_counts,
                "total_categories": len(categories)
            },
            message=f"Found {len(categories)} categories"
        )

    except Exception as exc:
        logger.error(f"Failed to list categories: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list categories: {str(exc)}"
        )
