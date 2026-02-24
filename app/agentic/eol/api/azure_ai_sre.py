"""
Azure AI SRE Agent API Router
Provides REST API endpoints for Azure AI SRE Agent (gccsreagent) integration
"""
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils import get_logger
from utils.config import config
from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint, write_endpoint

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class SREQueryRequest(BaseModel):
    """Request model for SRE agent queries"""
    query: str = Field(..., description="SRE query or incident description")
    thread_id: Optional[str] = Field(None, description="Optional conversation thread ID")


class SRECapability(BaseModel):
    """SRE agent capability"""
    name: str
    description: str
    category: str


# ============================================================================
# AZURE AI SRE AGENT ENDPOINTS
# ============================================================================

@router.get("/api/azure-ai-sre/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_ai_sre_status", timeout_seconds=10)
async def get_sre_agent_status():
    """
    Get the status of Azure AI SRE agent connection.

    Returns:
        StandardResponse with agent status and configuration
    """
    try:
        from utils.config import config
        sre_config = config.azure_ai_sre

        # Check if Azure AI SRE is enabled
        if not sre_config.enabled:
            return StandardResponse(
                success=True,
                data={
                    "enabled": False,
                    "message": "Azure AI SRE agent is disabled",
                    "agent_name": sre_config.agent_name
                },
                message="Azure AI SRE agent is disabled"
            )

        # Try to initialize agent and check availability
        agent_available = False
        agent_info = {}

        try:
            from agents.azure_ai_sre_agent import AzureAISREAgent

            agent = AzureAISREAgent(
                project_endpoint=sre_config.project_endpoint,
                agent_name=sre_config.agent_name
            )

            agent_available = agent.is_available()

            agent_info = {
                "enabled": True,
                "available": agent_available,
                "agent_name": sre_config.agent_name,
                "agent_id": sre_config.agent_id,
                "project_endpoint": sre_config.project_endpoint,
                "status": "connected" if agent_available else "not_configured"
            }

            if not agent_available:
                agent_info["message"] = "Azure AI Agent Service not fully configured. Check AZURE_AI_PROJECT_ENDPOINT environment variable."

        except ImportError as e:
            logger.error(f"Failed to import Azure AI SRE Agent: {e}")
            agent_info = {
                "enabled": True,
                "available": False,
                "agent_name": sre_config.agent_name,
                "status": "unavailable",
                "message": "Azure AI Agent Service dependencies not installed"
            }
        except Exception as e:
            logger.error(f"Failed to initialize Azure AI SRE Agent: {e}")
            agent_info = {
                "enabled": True,
                "available": False,
                "agent_name": sre_config.agent_name,
                "status": "error",
                "message": str(e)
            }

        return StandardResponse(
            success=True,
            data=agent_info,
            message=f"Azure AI SRE agent status: {agent_info.get('status', 'unknown')}"
        )

    except Exception as e:
        logger.error(f"Error getting SRE agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/azure-ai-sre/capabilities", response_model=StandardResponse)
@readonly_endpoint(agent_name="azure_ai_sre_capabilities", timeout_seconds=10)
async def get_sre_capabilities():
    """
    Get the list of SRE agent capabilities.

    Returns:
        StandardResponse with list of SRE capabilities
    """
    try:
        # Define SRE capabilities (based on SRE MCP server tools)
        capabilities = [
            # Resource Health & Diagnostics
            {
                "name": "check_resource_health",
                "description": "Check health status of Azure resources (VMs, App Services, SQL, Storage, Load Balancers, VPN Gateways)",
                "category": "diagnostics"
            },
            {
                "name": "check_container_app_health",
                "description": "Monitor Container Apps health via Log Analytics",
                "category": "diagnostics"
            },
            {
                "name": "check_aks_cluster_health",
                "description": "Analyze AKS cluster node and pod health",
                "category": "diagnostics"
            },
            {
                "name": "get_diagnostic_logs",
                "description": "Retrieve diagnostic logs from Log Analytics",
                "category": "diagnostics"
            },
            {
                "name": "analyze_resource_configuration",
                "description": "Analyze resource configuration best practices",
                "category": "diagnostics"
            },
            {
                "name": "get_resource_dependencies",
                "description": "Map resource dependencies using Azure Resource Graph",
                "category": "diagnostics"
            },
            {
                "name": "analyze_activity_log",
                "description": "Track platform events and configuration changes from Activity Log",
                "category": "diagnostics"
            },

            # Incident Response
            {
                "name": "triage_incident",
                "description": "Automated incident triage with health checks and severity assessment",
                "category": "incident_response"
            },
            {
                "name": "search_logs_by_error",
                "description": "Pattern-based log search for specific errors",
                "category": "incident_response"
            },
            {
                "name": "correlate_alerts",
                "description": "Alert correlation using Log Analytics Alert table with temporal analysis",
                "category": "incident_response"
            },
            {
                "name": "generate_incident_summary",
                "description": "Structured incident reports with RCA steps",
                "category": "incident_response"
            },
            {
                "name": "get_audit_trail",
                "description": "Retrieve SRE operation audit trail for compliance",
                "category": "incident_response"
            },

            # Performance Monitoring
            {
                "name": "get_performance_metrics",
                "description": "Azure Monitor metrics (CPU, memory, network, etc.)",
                "category": "performance"
            },
            {
                "name": "identify_bottlenecks",
                "description": "Performance bottleneck detection",
                "category": "performance"
            },
            {
                "name": "get_capacity_recommendations",
                "description": "Capacity planning recommendations",
                "category": "performance"
            },
            {
                "name": "compare_baseline_metrics",
                "description": "Baseline deviation analysis",
                "category": "performance"
            },

            # Remediation
            {
                "name": "plan_remediation",
                "description": "Step-by-step remediation plans with approval workflow",
                "category": "remediation"
            },
            {
                "name": "execute_safe_restart",
                "description": "Simulated safe resource restart",
                "category": "remediation"
            },
            {
                "name": "scale_resource",
                "description": "Simulated resource scaling",
                "category": "remediation"
            },
            {
                "name": "clear_cache",
                "description": "Simulated cache clearing",
                "category": "remediation"
            },

            # Notifications
            {
                "name": "send_teams_notification",
                "description": "Send formatted Teams notifications",
                "category": "notifications"
            },
            {
                "name": "send_teams_alert",
                "description": "Send critical alerts to Teams",
                "category": "notifications"
            },
            {
                "name": "send_sre_status_update",
                "description": "Operation status updates to Teams",
                "category": "notifications"
            },

            # Application Insights & Tracing
            {
                "name": "query_app_insights_traces",
                "description": "Distributed tracing by operation ID across microservices",
                "category": "observability"
            },
            {
                "name": "get_request_telemetry",
                "description": "Request performance analysis (P95/P99 latencies, failure rates)",
                "category": "observability"
            },
            {
                "name": "analyze_dependency_map",
                "description": "Service-to-service dependency visualization via App Insights",
                "category": "observability"
            },

            # Cost Optimization
            {
                "name": "get_cost_analysis",
                "description": "Cost breakdown by resource group, service, tag, or location",
                "category": "cost_optimization"
            },
            {
                "name": "identify_orphaned_resources",
                "description": "Find unused Azure resources (unattached disks, idle IPs, empty NSGs)",
                "category": "cost_optimization"
            },
            {
                "name": "get_cost_recommendations",
                "description": "Azure Advisor cost savings suggestions (right-sizing, reserved instances)",
                "category": "cost_optimization"
            },
            {
                "name": "analyze_cost_anomalies",
                "description": "Detect unusual spending patterns and cost spikes",
                "category": "cost_optimization"
            },

            # SLO/SLI Management
            {
                "name": "define_slo",
                "description": "Define service level objectives (availability, latency, error rate targets)",
                "category": "slo_management"
            },
            {
                "name": "calculate_error_budget",
                "description": "Calculate remaining error budget based on SLI vs SLO",
                "category": "slo_management"
            },
            {
                "name": "get_slo_dashboard",
                "description": "SLO compliance report with burn rate and trend analysis",
                "category": "slo_management"
            },

            # Security & Compliance
            {
                "name": "get_security_score",
                "description": "Microsoft Defender for Cloud secure score with control breakdown",
                "category": "security"
            },
            {
                "name": "list_security_recommendations",
                "description": "Actionable security findings by severity from Defender for Cloud",
                "category": "security"
            },
            {
                "name": "check_compliance_status",
                "description": "Azure Policy compliance for regulatory frameworks (CIS, NIST, PCI-DSS)",
                "category": "security"
            },

            # Anomaly Detection
            {
                "name": "detect_metric_anomalies",
                "description": "Statistical anomaly detection in Azure Monitor metrics (Z-score/IQR)",
                "category": "anomaly_detection"
            },
            {
                "name": "predict_resource_exhaustion",
                "description": "Predict when resources will hit capacity based on trend extrapolation",
                "category": "anomaly_detection"
            },

            # Enhanced Incident Management
            {
                "name": "generate_postmortem",
                "description": "Generate comprehensive post-incident review documents",
                "category": "incident_response"
            },
            {
                "name": "calculate_mttr_metrics",
                "description": "Calculate DORA metrics (MTTR, MTTD, MTTF) from incident history",
                "category": "incident_response"
            },
        ]

        # Group by category
        categories = {}
        for cap in capabilities:
            category = cap["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(cap)

        return StandardResponse(
            success=True,
            data={
                "capabilities": capabilities,
                "categories": categories,
                "total_count": len(capabilities)
            },
            message=f"Retrieved {len(capabilities)} SRE capabilities"
        )

    except Exception as e:
        logger.error(f"Error getting SRE capabilities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/azure-ai-sre/query")
async def query_sre_agent(request: SREQueryRequest):
    """
    Send a query to Azure AI SRE agent and stream the response.

    Args:
        request: SREQueryRequest with query and optional thread_id

    Returns:
        StreamingResponse with SSE events
    """
    try:
        from utils.config import config
        sre_config = config.azure_ai_sre

        # Check if Azure AI SRE is enabled
        if not sre_config.enabled:
            async def error_stream():
                yield f"data: {{'error': 'Azure AI SRE agent is disabled'}}\n\n"

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        # Import agent
        try:
            from agents.azure_ai_sre_agent import AzureAISREAgent
        except ImportError as e:
            logger.error(f"Failed to import Azure AI SRE Agent: {e}")
            async def error_stream():
                yield f"data: {{'error': 'Azure AI Agent Service dependencies not installed'}}\n\n"

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        async def sre_response_stream():
            """Stream SRE agent responses as SSE events"""
            try:
                # Initialize agent
                yield f"data: {{'event': 'status', 'message': 'Initializing Azure AI SRE agent...'}}\n\n"

                agent = AzureAISREAgent(
                    project_endpoint=sre_config.project_endpoint,
                    agent_name=sre_config.agent_name
                )

                if not agent.is_available():
                    yield f"data: {{'error': 'Azure AI Agent Service not available. Check AZURE_AI_PROJECT_ENDPOINT configuration.'}}\n\n"
                    return

                # Connect to existing gccsreagent (don't create new)
                yield f"data: {{'event': 'status', 'message': 'Connecting to {sre_config.agent_name}...'}}\n\n"

                # Send message to agent
                yield f"data: {{'event': 'query', 'query': '{request.query}'}}\n\n"

                response = await agent.send_message(
                    message=request.query,
                    thread_id=request.thread_id
                )

                if response and "response" in response:
                    # Stream the response
                    yield f"data: {{'event': 'response', 'content': {response['response']!r}, 'thread_id': '{response.get('thread_id', '')}', 'run_id': '{response.get('run_id', '')}'}}\n\n"
                elif response and "error" in response:
                    yield f"data: {{'error': '{response['error']}'}}\n\n"
                else:
                    yield f"data: {{'error': 'No response from agent'}}\n\n"

                yield f"data: {{'event': 'done'}}\n\n"

            except Exception as e:
                logger.error(f"Error in SRE response stream: {e}")
                yield f"data: {{'error': '{str(e)}'}}\n\n"

        return StreamingResponse(
            sre_response_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"Error querying SRE agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))
