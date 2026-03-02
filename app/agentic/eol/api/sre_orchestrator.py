"""SRE Orchestrator API Router.

Provides REST API endpoints for the SRE Orchestrator Agent with agent-first
architecture. Queries are routed through the Azure AI SRE Agent (gccsreagent)
for intelligent reasoning and tool selection, with MCP fallback.

Endpoints:
- POST /api/sre-orchestrator/execute - Execute SRE request (JSON response)
- POST /api/sre-orchestrator/execute-stream - Execute SRE request (SSE streaming)
- GET  /api/sre-orchestrator/capabilities - List orchestrator capabilities
- GET  /api/sre-orchestrator/tools - List all registered tools
- GET  /api/sre-orchestrator/tools/{tool_name} - Get specific tool details
- GET  /api/sre-orchestrator/agents - List all registered agents
- GET  /api/sre-orchestrator/health - Health check
- GET  /api/sre-orchestrator/metrics - Orchestrator metrics
- POST /api/sre-orchestrator/incident - Execute incident response workflow
- GET  /api/sre-orchestrator/threads/{workflow_id} - Retrieve thread history
- DELETE /api/sre-orchestrator/threads/{workflow_id} - Clear thread context
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from app.agentic.eol.agents.sre_orchestrator import SREOrchestratorAgent
    from app.agentic.eol.agents.incident_response_agent import IncidentResponseAgent
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.response_models import StandardResponse
except ModuleNotFoundError:
    from agents.sre_orchestrator import SREOrchestratorAgent
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
    workflow_id: Optional[str] = Field(
        default=None,
        description="Optional workflow ID for conversation continuity. If not provided, a new one is generated."
    )
    stream: bool = Field(
        default=False,
        description="Enable server-sent events for progress streaming"
    )
    response_format: str = Field(
        default="formatted_html",
        description="Response format: 'formatted_html' or 'raw_json'"
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
async def execute_sre_request(request: SREExecuteRequest, response: Response):
    """Execute SRE operation with natural language query.

    Routes the query through the Azure AI SRE Agent (gccsreagent) for
    intelligent reasoning and tool selection. Falls back to direct MCP
    execution when the agent is unavailable.

    Example queries:
    - "Check health of all container apps"
    - "Find orphaned resources and estimate savings"
    - "Show me performance metrics for the API"
    - "Triage incident #123"
    - "Check SLO compliance for my-service"
    - "Get security recommendations"

    Args:
        request: SRE execution request with query, optional context and workflow_id

    Returns:
        StandardResponse with execution results including agent_metadata

    Raises:
        HTTPException: If execution fails
    """
    logger.info("Executing SRE request: %s", request.query[:100])

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

        # Build request payload
        request_payload = {
            "query": request.query,
            "context": request.context or {},
            "stream": request.stream,
        }
        if request.workflow_id:
            request_payload["workflow_id"] = request.workflow_id

        # Collect routing metadata (best-effort, non-blocking)
        routing_meta: dict = {}
        try:
            plan = await orchestrator.process_with_routing(
                request.query, strategy="fast"
            )
            routing_meta = {
                "routing_domain": plan.domain.value,
                "routing_orchestrator": plan.orchestrator,
                "routing_strategy": plan.strategy_used,
                "routing_confidence": round(plan.confidence, 3),
                "routing_time_ms": round(plan.classification_time_ms, 1),
            }
        except Exception as routing_exc:
            logger.debug("SRE routing metadata collection skipped: %s", routing_exc)

        # Execute request
        result = await orchestrator.handle_request(request_payload)

        # --- Telemetry response headers ---
        _set_sre_headers(response, result)

        # Check execution status
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )

        # Extract results from BaseSREAgent wrapper payload
        # BaseSREAgent.handle_request() returns the agent output under "result"
        # (not "results"). Keep a fallback to "results" for compatibility.
        results_data = result.get("result") or result.get("results", {})

        # Extract agent_metadata from result or results_data
        agent_metadata = (
            result.get("agent_metadata")
            or results_data.get("agent_metadata")
            or {}
        )

        # Check if user interaction is required
        if results_data.get("user_interaction_required"):
            interaction_data = results_data.get("interaction_data", {})

            return StandardResponse(
                success=True,
                data={
                    "interaction_required": True,
                    "interaction_type": interaction_data.get("selection_type", "input"),
                    "message": interaction_data.get("message", "User input required"),
                    "options": interaction_data.get("options", []),
                    "workflow_id": result.get("workflow_id"),
                    "agent_metadata": agent_metadata,
                    "routing": routing_meta if routing_meta else None,
                },
                message="User interaction required to complete operation"
            )

        # Check if formatted response exists
        formatted_response = results_data.get("formatted_response")
        if not formatted_response and isinstance(results_data.get("results"), dict):
            formatted_response = results_data["results"].get("formatted_response")

        # If raw_json requested, return raw results
        if request.response_format == "raw_json":
            return StandardResponse(
                success=True,
                data={
                    "results": results_data,
                    "workflow_id": result.get("workflow_id") or results_data.get("workflow_id"),
                    "agent_metadata": agent_metadata,
                    "routing": routing_meta if routing_meta else None,
                },
                message="Successfully processed query"
            )

        if formatted_response:
            # Return formatted HTML response with agent metadata
            return StandardResponse(
                success=True,
                data={
                    "formatted_html": formatted_response,
                    "raw_results": (
                        results_data.get("results", [])
                        if isinstance(results_data.get("results"), list)
                        else results_data.get("results", {}).get("results", [])
                    ),
                    "summary": (
                        results_data.get("summary", {})
                        if isinstance(results_data.get("summary"), dict)
                        else results_data.get("results", {}).get("summary", {})
                    ),
                    "workflow_id": result.get("workflow_id") or results_data.get("workflow_id"),
                    "agent_metadata": agent_metadata,
                    "routing": routing_meta if routing_meta else None,
                },
                message=f"Successfully processed query: {request.query[:50]}..."
            )

        # Return raw results if no formatting
        return StandardResponse(
            success=True,
            data={
                **results_data,
                "agent_metadata": agent_metadata,
                "routing": routing_meta if routing_meta else None,
            },
            message="Successfully processed query"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to execute SRE request: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(exc)}"
        )
    finally:
        if orchestrator:
            await orchestrator.cleanup()


@router.post("/execute-stream")
async def execute_sre_request_stream(request: SREExecuteRequest):
    """Execute SRE operation with Server-Sent Events (SSE) streaming.

    Streams progress events and results as the orchestrator processes the query.
    Events are formatted as SSE with the following event types:

    - `status`: Processing status updates (routing, agent_thinking, executing_tools, etc.)
    - `tool_progress`: Individual tool execution progress
    - `agent_response`: Agent text content (may arrive in chunks)
    - `result`: Final formatted result (HTML or JSON)
    - `error`: Error events
    - `done`: Stream completion marker

    Each event is a JSON object:
    ```
    data: {"event": "status", "message": "Agent is analysing your query..."}
    data: {"event": "tool_progress", "tool": "check_container_app_health", "status": "executing"}
    data: {"event": "result", "formatted_html": "...", "agent_metadata": {...}}
    data: {"event": "done"}
    ```

    Args:
        request: SRE execution request with query and optional context

    Returns:
        StreamingResponse with SSE events
    """
    logger.info("Streaming SRE request: %s", request.query[:100])

    # Mutable container for telemetry headers computed inside the generator
    _stream_headers: Dict[str, str] = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Agent-Used": "unknown",
    }

    async def sse_event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for the SRE request."""
        orchestrator = None
        start_time = time.time()

        try:
            # Emit initialization status
            yield _sse_event("status", {
                "message": "Initializing SRE orchestrator...",
                "phase": "init",
            })

            # Create and initialize orchestrator
            orchestrator = SREOrchestratorAgent()
            initialized = await orchestrator.initialize()

            if not initialized:
                yield _sse_event("error", {
                    "message": "Failed to initialize SRE orchestrator",
                })
                return

            yield _sse_event("status", {
                "message": "Processing query via SRE agent...",
                "phase": "routing",
            })

            # Build request payload
            request_payload = {
                "query": request.query,
                "context": request.context or {},
                "stream": True,
            }
            if request.workflow_id:
                request_payload["workflow_id"] = request.workflow_id

            # Execute request
            result = await orchestrator.handle_request(request_payload)

            # Populate telemetry headers from result metadata
            _stream_headers.update(_extract_sre_header_values(result))

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Check for errors
            if result.get("status") == "error":
                yield _sse_event("error", {
                    "message": result.get("error", "Unknown error"),
                    "elapsed_ms": elapsed_ms,
                })
                return

            # Extract results
            results_data = result.get("result") or result.get("results", {})
            agent_metadata = (
                result.get("agent_metadata")
                or results_data.get("agent_metadata")
                or {}
            )
            agent_metadata["elapsed_ms"] = elapsed_ms

            # Check for user interaction
            if results_data.get("user_interaction_required"):
                interaction_data = results_data.get("interaction_data", {})
                yield _sse_event("interaction", {
                    "interaction_type": interaction_data.get("selection_type", "input"),
                    "message": interaction_data.get("message", "User input required"),
                    "options": interaction_data.get("options", []),
                    "workflow_id": result.get("workflow_id"),
                })
                yield _sse_event("done", {})
                return

            # Emit agent content if available
            agent_content = results_data.get("agent_content", "")
            if agent_content:
                yield _sse_event("agent_response", {
                    "content": agent_content,
                })

            # Emit tool results
            tool_results = results_data.get("results", [])
            if isinstance(tool_results, list):
                for tr in tool_results:
                    yield _sse_event("tool_progress", {
                        "tool": tr.get("tool", "unknown"),
                        "status": tr.get("status", "unknown"),
                        "latency_ms": tr.get("latency_ms", 0),
                    })

            # Emit formatted result
            formatted_html = results_data.get("formatted_response")
            if not formatted_html and isinstance(results_data.get("results"), dict):
                formatted_html = results_data["results"].get("formatted_response")

            yield _sse_event("result", {
                "formatted_html": formatted_html or "",
                "summary": (
                    results_data.get("summary", {})
                    if isinstance(results_data.get("summary"), dict)
                    else results_data.get("results", {}).get("summary", {})
                    if isinstance(results_data.get("results"), dict)
                    else {}
                ),
                "workflow_id": result.get("workflow_id") or results_data.get("workflow_id"),
                "agent_metadata": agent_metadata,
            })

            yield _sse_event("done", {})

        except asyncio.CancelledError:
            logger.info("SSE stream cancelled by client")
            yield _sse_event("error", {"message": "Stream cancelled"})
        except Exception as exc:
            logger.error("SSE stream error: %s", exc, exc_info=True)
            yield _sse_event("error", {
                "message": f"Execution failed: {str(exc)}",
            })
        finally:
            if orchestrator:
                await orchestrator.cleanup()

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers=_stream_headers,
    )


def _extract_sre_header_values(result: Dict[str, Any]) -> Dict[str, str]:
    """Extract X-Token-Count and X-Agent-Used values from an orchestrator result."""
    headers: Dict[str, str] = {}
    agent_meta = result.get("agent_metadata") or (result.get("result") or {}).get("agent_metadata") or {}
    token_usage = agent_meta.get("token_usage") or {}
    total_tokens = (
        token_usage.get("total_tokens")
        or (token_usage.get("prompt_tokens", 0) + token_usage.get("completion_tokens", 0))
        or 0
    )
    if total_tokens:
        headers["X-Token-Count"] = str(total_tokens)
    execution_source = agent_meta.get("execution_source") or "unknown"
    headers["X-Agent-Used"] = execution_source
    return headers


def _set_sre_headers(response: Response, result: Dict[str, Any]) -> None:
    """Set SRE telemetry headers on a FastAPI Response object."""
    for key, value in _extract_sre_header_values(result).items():
        response.headers[key] = value


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event.

    Args:
        event_type: Event type (status, tool_progress, result, error, done)
        data: Event payload

    Returns:
        SSE-formatted string
    """
    payload = {"event": event_type, **data}
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.get("/capabilities", response_model=StandardResponse)
async def get_capabilities():
    """Get SRE orchestrator capabilities.

    Returns information about the orchestrator's capabilities including:
    - Agent status (connected vs fallback mode)
    - Available tools and agent diagnostics
    - Total number of agents and tools
    - Orchestrator version and execution mode

    Returns:
        StandardResponse with capabilities information
    """
    logger.info("Getting orchestrator capabilities")

    orchestrator = None
    try:
        orchestrator = SREOrchestratorAgent()
        await orchestrator.initialize()

        capabilities = orchestrator.get_capabilities()

        return StandardResponse(
            success=True,
            data=capabilities,
            message="Orchestrator capabilities retrieved"
        )

    except Exception as exc:
        logger.error("Failed to get capabilities: %s", exc, exc_info=True)
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


# ============================================================================
# Thread Management Endpoints (removed — SRESubAgent is stateless)
# ============================================================================

@router.get("/threads/{workflow_id}", response_model=StandardResponse)
async def get_thread_history(workflow_id: str):
    """Thread history endpoint — removed.

    The SRE agent now uses SRESubAgent (stateless ReAct loop) which does not
    maintain persistent conversation threads.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Thread history is no longer available. The SRE agent uses a stateless ReAct loop."
    )


@router.delete("/threads/{workflow_id}", response_model=StandardResponse)
async def delete_thread(workflow_id: str):
    """Thread deletion endpoint — removed.

    The SRE agent now uses SRESubAgent (stateless ReAct loop) which does not
    maintain persistent conversation threads.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Thread management is no longer available. The SRE agent uses a stateless ReAct loop."
    )
