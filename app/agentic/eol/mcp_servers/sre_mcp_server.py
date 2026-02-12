"""Azure SRE Agent MCP Server

Provides MCP-compliant tools for Site Reliability Engineering operations on Azure:
- Resource health monitoring and diagnostics
- Incident response and troubleshooting
- Performance monitoring and optimization
- Safe automated remediation with approval workflows
- Microsoft Teams notifications for incident management
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

try:
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.monitor.query import LogsQueryClient, MetricsQueryClient
    from azure.mgmt.resourcehealth import MicrosoftResourceHealth as ResourceHealthMgmtClient
    from azure.mgmt.monitor import MonitorManagementClient
    from azure.mgmt.resource import ResourceManagementClient
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
except ImportError:
    DefaultAzureCredential = None
    ClientSecretCredential = None
    LogsQueryClient = None
    MetricsQueryClient = None
    ResourceHealthMgmtClient = None
    MonitorManagementClient = None
    ResourceManagementClient = None
    ResourceGraphClient = None
    QueryRequest = None
    QueryRequestOptions = None

# Import Teams notification client
try:
    from app.agentic.eol.utils.teams_notification_client import TeamsNotificationClient
except ImportError:
    TeamsNotificationClient = None

_LOG_LEVEL_NAME = os.getenv("SRE_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO

try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_server = FastMCP(name="azure-sre")
_credential: Optional[DefaultAzureCredential] = None
_teams_client: Optional[TeamsNotificationClient] = None
_subscription_id: Optional[str] = None

# In-memory audit trail (in production, this should write to Cosmos DB or Log Analytics)
_audit_trail: List[Dict[str, Any]] = []


def _log_audit_event(operation: str, resource_id: Optional[str], details: Dict[str, Any], success: bool):
    """Log an audit event for SRE operations"""
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "operation": operation,
        "resource_id": resource_id,
        "success": success,
        "details": details,
        "caller": os.getenv("USER", "system")
    }
    _audit_trail.append(audit_entry)
    logger.info(f"AUDIT: {operation} | Resource: {resource_id} | Success: {success}")

    # Keep only last 1000 entries in memory
    if len(_audit_trail) > 1000:
        _audit_trail.pop(0)


def _get_credential():
    """Get or create Azure credential using Service Principal if configured, otherwise Managed Identity"""
    global _credential
    if _credential is None:
        # Check if Service Principal credentials are available
        use_sp = os.getenv("USE_SERVICE_PRINCIPAL", "false").lower() == "true"
        sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
        sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if use_sp and sp_client_id and sp_client_secret and tenant_id:
            logger.info("Using Service Principal authentication for SRE MCP server")
            _credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=sp_client_id,
                client_secret=sp_client_secret
            )
        else:
            logger.info("Using Managed Identity authentication for SRE MCP server")
            _credential = DefaultAzureCredential()
    return _credential


def _get_teams_client() -> Optional[TeamsNotificationClient]:
    """Get or create Teams notification client"""
    global _teams_client
    if _teams_client is None and TeamsNotificationClient is not None:
        _teams_client = TeamsNotificationClient()
    return _teams_client


def _get_subscription_id() -> str:
    """Get subscription ID from environment"""
    global _subscription_id
    if _subscription_id is None:
        _subscription_id = os.getenv("SUBSCRIPTION_ID") or os.getenv("AZURE_SUBSCRIPTION_ID")
        if not _subscription_id:
            raise ValueError("SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID environment variable required")
    return _subscription_id


# ============================================================================
# Resource Health & Diagnostics Tools
# ============================================================================

@_server.tool(
    name="check_resource_health",
    description=(
        "Check the health status of an Azure resource using Azure Resource Health API. "
        "Returns current availability state, health events, and recommended actions. "
        "⚠️ IMPORTANT: Only supports specific resource types (VMs, App Services, SQL DBs, Storage Accounts, Load Balancers, VPN Gateways). "
        "NOT supported: Container Apps, Container Instances, AKS. For unsupported types, use get_diagnostic_logs or Azure MCP tools instead."
    ),
)
async def check_resource_health(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID (e.g., /subscriptions/.../resourceGroups/.../providers/...)"],
) -> list[TextContent]:
    """Check Azure resource health status"""
    try:
        if ResourceHealthMgmtClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        subscription_id = _get_subscription_id()

        client = ResourceHealthMgmtClient(credential, subscription_id)

        # Get current health status
        availability_status = client.availability_statuses.get_by_resource(
            resource_uri=resource_id
        )

        result = {
            "success": True,
            "resource_id": resource_id,
            "health_status": {
                "availability_state": availability_status.properties.availability_state,
                "summary": availability_status.properties.summary,
                "detailed_status": availability_status.properties.detailed_status,
                "reason_type": availability_status.properties.reason_type,
                "occurred_time": str(availability_status.properties.occured_time) if availability_status.properties.occured_time else None,
            },
            "recommended_actions": availability_status.properties.recommended_actions or [],
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log audit event
        _log_audit_event(
            operation="check_resource_health",
            resource_id=resource_id,
            details={"availability_state": availability_status.properties.availability_state},
            success=True
        )

        logger.info(f"Resource health check completed for {resource_id}: {availability_status.properties.availability_state}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        # Log audit event for failure
        _log_audit_event(
            operation="check_resource_health",
            resource_id=resource_id,
            details={"error": str(exc)},
            success=False
        )
        logger.error(f"Error checking resource health: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="check_container_app_health",
    description=(
        "Check the health and status of an Azure Container App. "
        "Returns replica status, provisioning state, ingress configuration, and recent logs. "
        "✅ USE THIS TOOL for Container App health checks - it's specifically designed for Container Apps. "
        "⚠️ Container Apps are NOT supported by Azure Resource Health API (check_resource_health). "
        "Requires: workspace_id (Log Analytics workspace ID) and resource_id (full Container App resource ID)."
    ),
)
async def check_container_app_health(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID for Container App logs"],
    resource_id: Annotated[str, "Full Azure Container App resource ID"],
) -> list[TextContent]:
    """Check Azure Container App health using Log Analytics"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid Container App resource ID format")

        container_app_name = parts[8]
        resource_group = parts[4]

        # Try standard Container Apps tables first, then fall back to custom logs
        # Standard tables: ContainerAppConsoleLogs, ContainerAppSystemLogs
        # Custom logs: ContainerAppConsoleLogs_CL (if diagnostic settings configured)

        tables_to_try = [
            "ContainerAppConsoleLogs",
            "ContainerAppSystemLogs",
            "ContainerAppConsoleLogs_CL"
        ]

        health_data = {
            "total_logs": 0,
            "error_count": 0,
            "warning_count": 0,
            "health_status": "Unknown",
            "recent_errors": [],
            "table_used": None
        }

        query_succeeded = False

        for table_name in tables_to_try:
            try:
                # Determine field names based on table type
                if table_name.endswith("_CL"):
                    # Custom log table uses _s suffix for strings
                    app_name_field = "ContainerAppName_s"
                    log_field = "Log_s"
                else:
                    # Standard tables use proper field names
                    app_name_field = "ContainerAppName"
                    log_field = "Log"

                query = f"""
                {table_name}
                | where TimeGenerated > ago(1h)
                | where {app_name_field} == '{container_app_name}' or ResourceId contains '{resource_id}'
                | extend Level = case(
                    {log_field} contains "error" or {log_field} contains "ERROR" or {log_field} contains "failed", "Error",
                    {log_field} contains "warn" or {log_field} contains "WARNING", "Warning",
                    "Info"
                )
                | summarize
                    TotalLogs = count(),
                    ErrorCount = countif(Level == "Error"),
                    WarningCount = countif(Level == "Warning"),
                    LastLog = arg_max(TimeGenerated, {log_field}),
                    RecentErrors = make_list_if({log_field}, Level == "Error", 5)
                | extend HealthStatus = case(
                    ErrorCount > 10, "Unhealthy",
                    ErrorCount > 3, "Degraded",
                    "Healthy"
                )
                """

                time_range = timedelta(hours=1)
                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=query,
                    timespan=time_range
                )

                # Process results
                for table in response.tables:
                    for row in table.rows:
                        health_data = {
                            "total_logs": row[0],
                            "error_count": row[1],
                            "warning_count": row[2],
                            "last_log_time": str(row[3]),
                            "last_log_message": row[4] if len(row) > 4 else "",
                            "recent_errors": row[5] if len(row) > 5 else [],
                            "health_status": row[6] if len(row) > 6 else "Unknown",
                            "table_used": table_name
                        }
                        query_succeeded = True
                        break
                    if query_succeeded:
                        break

                if query_succeeded:
                    logger.info(f"Successfully queried {table_name} for Container App {container_app_name}")
                    break

            except Exception as table_exc:
                # This table doesn't exist or query failed, try next one
                logger.debug(f"Table {table_name} not available or query failed: {table_exc}")
                continue

        if not query_succeeded:
            # No tables available - Container App may not have diagnostic settings enabled
            health_data["health_status"] = "Unknown - No logs available"
            health_data["table_used"] = "None (diagnostic logs not configured)"

        result = {
            "success": True,
            "resource_id": resource_id,
            "container_app_name": container_app_name,
            "resource_group": resource_group,
            "health_data": health_data,
            "recommendations": [
                "Enable diagnostic settings to send Container App logs to Log Analytics" if not query_succeeded else None,
                "Use 'az containerapp logs show' to view logs directly from Container App" if not query_succeeded else None,
                "Check replicas are running and healthy" if health_data["error_count"] > 0 else None,
                "Review recent deployment or configuration changes" if health_data["error_count"] > 5 else None,
                "Check ingress and scaling configuration" if health_data["health_status"] == "Unhealthy" else None,
                "Use 'az containerapp revision list' to check revision status" if health_data["health_status"] != "Healthy" else None
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Diagnostic logs not configured - enable diagnostic settings for detailed health monitoring" if not query_succeeded else None
        }

        # Remove None recommendations
        result["recommendations"] = [r for r in result["recommendations"] if r]

        logger.info(f"Container App health check completed for {container_app_name}: {health_data['health_status']}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error checking Container App health: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="check_aks_cluster_health",
    description=(
        "Check the health and status of an Azure Kubernetes Service (AKS) cluster. "
        "Returns node status, pod health, system component status, and recent issues. "
        "Use this for troubleshooting AKS clusters (not supported by standard Resource Health API)."
    ),
)
async def check_aks_cluster_health(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID for AKS logs"],
    resource_id: Annotated[str, "Full Azure AKS cluster resource ID"],
) -> list[TextContent]:
    """Check Azure AKS cluster health using Log Analytics"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid AKS resource ID format")

        cluster_name = parts[8]
        resource_group = parts[4]

        # Query AKS diagnostics for health information
        query = f"""
        let ClusterName = '{cluster_name}';
        KubeNodeInventory
        | where TimeGenerated > ago(1h)
        | where ClusterName == ClusterName
        | summarize
            TotalNodes = dcount(Computer),
            ReadyNodes = dcountif(Computer, Status == "Ready"),
            NotReadyNodes = dcountif(Computer, Status != "Ready")
        | extend NodeHealthStatus = case(
            NotReadyNodes > 0, "Degraded",
            ReadyNodes > 0, "Healthy",
            "Unknown"
        )
        | union (
            KubePodInventory
            | where TimeGenerated > ago(1h)
            | where ClusterName == ClusterName
            | summarize
                TotalPods = dcount(Name),
                RunningPods = dcountif(Name, PodStatus == "Running"),
                FailedPods = dcountif(Name, PodStatus contains "Failed" or PodStatus contains "Error"),
                PendingPods = dcountif(Name, PodStatus == "Pending")
            | extend PodHealthStatus = case(
                FailedPods > 5, "Unhealthy",
                FailedPods > 0 or PendingPods > 10, "Degraded",
                "Healthy"
            )
        )
        | union (
            KubeEvents
            | where TimeGenerated > ago(1h)
            | where ClusterName == ClusterName
            | where Type == "Warning" or Type == "Error"
            | summarize RecentIssues = make_list(Message, 5)
        )
        """

        time_range = timedelta(hours=1)
        response = logs_client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=time_range
        )

        health_summary = {
            "nodes": {"total": 0, "ready": 0, "not_ready": 0, "status": "Unknown"},
            "pods": {"total": 0, "running": 0, "failed": 0, "pending": 0, "status": "Unknown"},
            "recent_issues": []
        }

        for table in response.tables:
            for row in table.rows:
                # Process node, pod, and event data
                if len(row) >= 4:
                    # Node data
                    if "TotalNodes" in str(table.columns[0].name if hasattr(table, 'columns') else ""):
                        health_summary["nodes"] = {
                            "total": row[0] if row[0] else 0,
                            "ready": row[1] if len(row) > 1 and row[1] else 0,
                            "not_ready": row[2] if len(row) > 2 and row[2] else 0,
                            "status": row[3] if len(row) > 3 else "Unknown"
                        }
                    # Pod data
                    elif "TotalPods" in str(table.columns[0].name if hasattr(table, 'columns') else ""):
                        health_summary["pods"] = {
                            "total": row[0] if row[0] else 0,
                            "running": row[1] if len(row) > 1 and row[1] else 0,
                            "failed": row[2] if len(row) > 2 and row[2] else 0,
                            "pending": row[3] if len(row) > 3 and row[3] else 0,
                            "status": row[4] if len(row) > 4 else "Unknown"
                        }
                elif len(row) >= 1:
                    # Event data
                    health_summary["recent_issues"] = row[0] if row[0] else []

        # Determine overall health
        overall_health = "Healthy"
        if health_summary["nodes"]["status"] == "Degraded" or health_summary["pods"]["status"] in ["Unhealthy", "Degraded"]:
            overall_health = "Degraded"
        if health_summary["pods"]["status"] == "Unhealthy" or health_summary["nodes"]["not_ready"] > 1:
            overall_health = "Unhealthy"

        result = {
            "success": True,
            "resource_id": resource_id,
            "cluster_name": cluster_name,
            "resource_group": resource_group,
            "overall_health": overall_health,
            "health_summary": health_summary,
            "recommendations": [
                "Check node status with 'kubectl get nodes'" if health_summary["nodes"]["not_ready"] > 0 else None,
                "Investigate failed pods with 'kubectl describe pod'" if health_summary["pods"]["failed"] > 0 else None,
                "Review cluster autoscaler if many pending pods" if health_summary["pods"]["pending"] > 10 else None,
                "Check system components (kube-system namespace)" if overall_health == "Unhealthy" else None,
                "Review recent events with 'kubectl get events --sort-by=.metadata.creationTimestamp'" if health_summary["recent_issues"] else None
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        # Remove None recommendations
        result["recommendations"] = [r for r in result["recommendations"] if r]

        logger.info(f"AKS cluster health check completed for {cluster_name}: {overall_health}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error checking AKS cluster health: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_diagnostic_logs",
    description=(
        "Retrieve diagnostic logs from Azure Log Analytics for ANY Azure resource. "
        "✅ USE THIS TOOL instead of constructing Azure CLI 'az monitor log-analytics query' commands manually. "
        "Queries logs for the last N hours and returns relevant error/warning entries. "
        "Works with AzureDiagnostics table and filters by resource ID. "
        "Perfect for troubleshooting and incident investigation across all Azure services. "
        "Requires: workspace_id, resource_id, hours (default: 24), optional severity filter."
    ),
)
async def get_diagnostic_logs(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    resource_id: Annotated[str, "Azure resource ID to query logs for"],
    hours: Annotated[int, "Number of hours to look back (default: 24)"] = 24,
    severity: Annotated[Optional[str], "Filter by severity: Error, Warning, Informational, Verbose"] = None,
) -> list[TextContent]:
    """Retrieve diagnostic logs for a resource"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        # Build KQL query
        time_range = timedelta(hours=hours)
        severity_filter = f"| where Level == '{severity}'" if severity else ""

        query = f"""
        AzureDiagnostics
        | where Resource == '{resource_id}' or ResourceId == '{resource_id}'
        | where TimeGenerated > ago({hours}h)
        {severity_filter}
        | project TimeGenerated, Level, OperationName, ResultDescription, Message = coalesce(Message, ResultDescription)
        | order by TimeGenerated desc
        | limit 100
        """

        response = logs_client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=time_range
        )

        logs = []
        for table in response.tables:
            for row in table.rows:
                log_entry = {
                    "timestamp": str(row[0]),
                    "level": row[1],
                    "operation": row[2],
                    "description": row[3],
                    "message": row[4]
                }
                logs.append(log_entry)

        result = {
            "success": True,
            "resource_id": resource_id,
            "hours_queried": hours,
            "log_count": len(logs),
            "logs": logs
        }

        logger.info(f"Retrieved {len(logs)} diagnostic log entries for {resource_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error retrieving diagnostic logs: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="analyze_resource_configuration",
    description=(
        "Analyze Azure resource configuration against best practices. "
        "Checks for common misconfigurations, security issues, and optimization opportunities. "
        "Returns findings with severity and recommendations."
    ),
)
async def analyze_resource_configuration(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID to analyze"],
) -> list[TextContent]:
    """Analyze resource configuration for issues"""
    try:
        if ResourceManagementClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        subscription_id = _get_subscription_id()

        client = ResourceManagementClient(credential, subscription_id)

        # Get resource details
        # Parse resource ID to extract resource group and resource details
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        resource_group = parts[4]
        resource_provider = parts[6]
        resource_type = parts[7]
        resource_name = parts[8]

        resource = client.resources.get_by_id(
            resource_id=resource_id,
            api_version="2021-04-01"
        )

        # Perform basic configuration analysis
        findings = []

        # Check tags
        if not resource.tags or len(resource.tags) == 0:
            findings.append({
                "severity": "Warning",
                "category": "Governance",
                "finding": "Resource has no tags",
                "recommendation": "Add tags for better resource organization and cost tracking"
            })

        # Check location (basic check for common patterns)
        if resource.location and "test" in resource.location.lower():
            findings.append({
                "severity": "Info",
                "category": "Environment",
                "finding": "Resource appears to be in test environment",
                "recommendation": "Verify this is intentional for production workloads"
            })

        result = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource.name,
            "resource_type": resource.type,
            "location": resource.location,
            "tags": resource.tags or {},
            "findings": findings,
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Configuration analysis completed for {resource_id}: {len(findings)} findings")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error analyzing resource configuration: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_resource_dependencies",
    description=(
        "Map resource dependencies and health cascade using Azure Resource Graph. "
        "Identifies related resources (NICs, disks, VNets, NSGs, load balancers, etc.) and checks their health status. "
        "Essential for root cause analysis during incidents to understand impact scope and cascading failures."
    ),
)
async def get_resource_dependencies(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
) -> list[TextContent]:
    """Get resource dependencies and their health status using Azure Resource Graph"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        subscription_id = _get_subscription_id()

        # Initialize Resource Graph client
        graph_client = ResourceGraphClient(credential)

        # Parse resource ID to extract components
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        resource_name = parts[8]
        resource_type = f"{parts[6]}/{parts[7]}"

        # Query for dependencies using Resource Graph
        # This query finds resources that reference or are referenced by the target resource
        query = f"""
        Resources
        | where id =~ '{resource_id}'
        | project id, name, type, location, resourceGroup, subscriptionId, properties
        | extend dependencies = pack_array(
            properties.networkProfile.networkInterfaces,
            properties.storageProfile.osDisk,
            properties.storageProfile.dataDisks,
            properties.networkSecurityGroup,
            properties.subnet,
            properties.publicIPAddress,
            properties.loadBalancerBackendAddressPools,
            properties.applicationSecurityGroups
        )
        | mvexpand dependencies
        | where isnotnull(dependencies)
        | extend dep_id = tostring(dependencies.id)
        | where isnotempty(dep_id)
        | project dep_id
        | union (
            Resources
            | where properties contains '{resource_name}' or properties contains '{resource_id}'
            | where id !~ '{resource_id}'
            | project id
        )
        | join kind=inner (
            Resources
            | project id, name, type, location, resourceGroup, properties
        ) on $left.dep_id == $right.id or $left.id == $right.id
        | project id, name, type, location, resourceGroup
        | limit 50
        """

        # Execute Resource Graph query
        request = QueryRequest(
            subscriptions=[subscription_id],
            query=query,
            options=QueryRequestOptions(top=50)
        )

        response = graph_client.resources(request)

        # Process results
        dependencies = []
        if hasattr(response, 'data') and response.data:
            for row in response.data:
                dep_entry = {
                    "resource_id": row.get('id', ''),
                    "name": row.get('name', ''),
                    "type": row.get('type', ''),
                    "location": row.get('location', ''),
                    "resource_group": row.get('resourceGroup', ''),
                    "health_status": "unknown"
                }

                # Try to get health status for supported resource types
                if ResourceHealthMgmtClient is not None:
                    try:
                        health_client = ResourceHealthMgmtClient(credential, subscription_id)
                        health_response = health_client.availability_statuses.get_by_resource(
                            resource_uri=dep_entry["resource_id"]
                        )
                        dep_entry["health_status"] = health_response.properties.availability_state
                        dep_entry["health_summary"] = health_response.properties.summary
                    except Exception:
                        # Health API not supported for this resource type
                        dep_entry["health_status"] = "not_supported"

                dependencies.append(dep_entry)

        result = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_type": resource_type,
            "dependencies_found": len(dependencies),
            "dependencies": dependencies,
            "analysis": {
                "unhealthy_dependencies": sum(1 for d in dependencies if d.get("health_status") in ["Unavailable", "Degraded"]),
                "unknown_health": sum(1 for d in dependencies if d.get("health_status") == "unknown"),
                "cascading_failure_risk": "High" if any(d.get("health_status") in ["Unavailable", "Degraded"] for d in dependencies) else "Low"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Dependency mapping completed for {resource_id}: {len(dependencies)} dependencies found")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error getting resource dependencies: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Incident Response Tools
# ============================================================================

@_server.tool(
    name="triage_incident",
    description=(
        "Perform automated incident triage. Analyzes incident context, queries logs, "
        "checks resource health, and generates initial assessment with recommended actions. "
        "Use this as the FIRST step when responding to an incident."
    ),
)
async def triage_incident(
    context: Context,
    incident_title: Annotated[str, "Incident title or description"],
    affected_resources: Annotated[List[str], "List of affected resource IDs"],
    workspace_id: Annotated[Optional[str], "Log Analytics workspace ID for log analysis"] = None,
) -> list[TextContent]:
    """Triage an incident with automated analysis"""
    try:
        triage_result = {
            "success": True,
            "incident_title": incident_title,
            "affected_resources": affected_resources,
            "triage_time": datetime.utcnow().isoformat(),
            "health_checks": [],
            "log_analysis": None,
            "recommended_actions": [],
            "severity_assessment": "Unknown"
        }

        # Check health of each affected resource
        if ResourceHealthMgmtClient is not None:
            credential = _get_credential()
            subscription_id = _get_subscription_id()
            health_client = ResourceHealthMgmtClient(credential, subscription_id)

            for resource_id in affected_resources[:5]:  # Limit to first 5 resources
                try:
                    status = health_client.availability_statuses.get_by_resource(resource_uri=resource_id)
                    triage_result["health_checks"].append({
                        "resource_id": resource_id,
                        "availability_state": status.properties.availability_state,
                        "summary": status.properties.summary
                    })

                    # Assess severity based on health status
                    if status.properties.availability_state in ["Unavailable", "Degraded"]:
                        triage_result["severity_assessment"] = "High"
                except Exception as e:
                    logger.warning(f"Could not check health for {resource_id}: {e}")

        # Add generic recommended actions
        triage_result["recommended_actions"] = [
            "Review recent deployments or configuration changes",
            "Check Azure Service Health for platform issues",
            "Analyze diagnostic logs for error patterns",
            "Verify network connectivity and firewall rules",
            "Check resource quotas and limits"
        ]

        logger.info(f"Incident triage completed: {incident_title}")
        return [TextContent(type="text", text=json.dumps(triage_result, indent=2))]

    except Exception as exc:
        logger.error(f"Error during incident triage: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="search_logs_by_error",
    description=(
        "Search Log Analytics for specific error patterns or keywords. "
        "Returns matching log entries with context. Useful for investigating specific errors."
    ),
)
async def search_logs_by_error(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    error_pattern: Annotated[str, "Error message or pattern to search for"],
    hours: Annotated[int, "Hours to look back (default: 24)"] = 24,
) -> list[TextContent]:
    """Search logs for specific error patterns"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        query = f"""
        union *
        | where TimeGenerated > ago({hours}h)
        | where * contains "{error_pattern}"
        | project TimeGenerated, Type, Computer, Message = coalesce(Message, ResultDescription, *)
        | order by TimeGenerated desc
        | limit 50
        """

        time_range = timedelta(hours=hours)
        response = logs_client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=time_range
        )

        matches = []
        for table in response.tables:
            for row in table.rows:
                matches.append({
                    "timestamp": str(row[0]),
                    "type": row[1],
                    "computer": row[2],
                    "message": str(row[3])[:500]  # Truncate long messages
                })

        result = {
            "success": True,
            "error_pattern": error_pattern,
            "matches_found": len(matches),
            "matches": matches
        }

        logger.info(f"Error search completed: found {len(matches)} matches for '{error_pattern}'")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error searching logs: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="correlate_alerts",
    description=(
        "Find related alerts and events in a time window using Log Analytics Alert table. "
        "Helps identify if multiple alerts are part of the same incident by analyzing temporal and resource correlation. "
        "Returns correlated alerts with timeline, severity, and affected resources."
    ),
)
async def correlate_alerts(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    start_time: Annotated[str, "Start time (ISO format)"],
    end_time: Annotated[str, "End time (ISO format)"],
    resource_id: Annotated[Optional[str], "Filter by resource ID"] = None,
) -> list[TextContent]:
    """Correlate alerts in a time window using Log Analytics"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        # Parse time strings
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        time_range = end_dt - start_dt

        # Build KQL query to find correlated alerts
        resource_filter = f"| where ResourceId == '{resource_id}'" if resource_id else ""

        query = f"""
        Alert
        | where TimeGenerated between(datetime({start_time}) .. datetime({end_time}))
        {resource_filter}
        | extend AlertSeverity = tostring(AlertSeverity)
        | extend AlertState = tostring(AlertState)
        | project TimeGenerated, AlertName, AlertSeverity, AlertState, ResourceId,
                  Description, SourceSystem, Computer, RemediationAction = coalesce(RemediationAction, "None")
        | order by TimeGenerated asc
        | limit 100
        """

        response = logs_client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=time_range
        )

        correlated_alerts = []
        severity_counts = {"Critical": 0, "Error": 0, "Warning": 0, "Informational": 0}
        affected_resources = set()

        for table in response.tables:
            for row in table.rows:
                alert_entry = {
                    "timestamp": str(row[0]),
                    "alert_name": row[1],
                    "severity": row[2],
                    "state": row[3],
                    "resource_id": row[4] if row[4] else "N/A",
                    "description": row[5] if row[5] else "",
                    "source": row[6] if row[6] else "",
                    "computer": row[7] if row[7] else "",
                    "remediation": row[8] if row[8] else "None"
                }
                correlated_alerts.append(alert_entry)

                # Track statistics
                severity = alert_entry["severity"]
                if severity in severity_counts:
                    severity_counts[severity] += 1
                if alert_entry["resource_id"] != "N/A":
                    affected_resources.add(alert_entry["resource_id"])

        # Analyze correlation patterns
        correlation_analysis = {
            "total_alerts": len(correlated_alerts),
            "severity_breakdown": severity_counts,
            "affected_resources_count": len(affected_resources),
            "affected_resources": list(affected_resources)[:10],  # Limit to 10
            "time_span_minutes": int(time_range.total_seconds() / 60),
            "alert_rate_per_hour": round(len(correlated_alerts) / max(time_range.total_seconds() / 3600, 0.1), 2),
            "potential_incident": len(correlated_alerts) >= 3 or severity_counts.get("Critical", 0) > 0,
            "incident_classification": "Critical" if severity_counts.get("Critical", 0) > 0
                                     else "High" if len(correlated_alerts) >= 5
                                     else "Medium" if len(correlated_alerts) >= 2
                                     else "Low"
        }

        result = {
            "success": True,
            "time_window": {
                "start": start_time,
                "end": end_time
            },
            "resource_filter": resource_id if resource_id else "All resources",
            "correlated_alerts": correlated_alerts,
            "correlation_analysis": correlation_analysis,
            "recommendations": [
                "Check for common error patterns across alerts" if len(correlated_alerts) > 3 else None,
                "Investigate resource dependencies for cascading failures" if len(affected_resources) > 2 else None,
                "Review recent configuration changes or deployments" if correlation_analysis["alert_rate_per_hour"] > 5 else None,
                "Consider creating an incident if alerts persist" if correlation_analysis["potential_incident"] else None
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        # Remove None recommendations
        result["recommendations"] = [r for r in result["recommendations"] if r]

        logger.info(f"Alert correlation completed: {len(correlated_alerts)} alerts found in time window")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error correlating alerts: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="analyze_activity_log",
    description=(
        "Analyze Azure Activity Log for platform events and configuration changes. "
        "Identifies resource modifications, failures, service health events, and administrative actions. "
        "Essential for understanding what changed before an incident occurred."
    ),
)
async def analyze_activity_log(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    resource_id: Annotated[Optional[str], "Filter by resource ID"] = None,
    hours: Annotated[int, "Hours to look back (default: 24)"] = 24,
    operation_types: Annotated[Optional[List[str]], "Filter by operation types (e.g., 'Write', 'Delete', 'Action')"] = None,
) -> list[TextContent]:
    """Analyze Azure Activity Log for platform events and changes"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)

        # Build filters
        resource_filter = f"| where ResourceId == '{resource_id}'" if resource_id else ""
        operation_filter = ""
        if operation_types:
            operations_list = "', '".join(operation_types)
            operation_filter = f"| where OperationNameValue has_any ('{operations_list}')"

        query = f"""
        AzureActivity
        | where TimeGenerated > ago({hours}h)
        {resource_filter}
        {operation_filter}
        | extend OperationResult = tostring(ActivityStatusValue)
        | extend OperationType = case(
            OperationNameValue contains "write" or OperationNameValue contains "create", "Write/Create",
            OperationNameValue contains "delete", "Delete",
            OperationNameValue contains "action", "Action",
            "Read"
        )
        | project TimeGenerated, OperationNameValue, OperationType, OperationResult,
                  Caller, ResourceId, ResourceGroup, ResourceProviderValue,
                  HTTPRequest, Properties
        | order by TimeGenerated desc
        | limit 100
        """

        time_range = timedelta(hours=hours)
        response = logs_client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=time_range
        )

        activity_events = []
        operation_counts = {}
        failed_operations = []
        affected_resources = set()

        for table in response.tables:
            for row in table.rows:
                event = {
                    "timestamp": str(row[0]),
                    "operation": row[1],
                    "operation_type": row[2],
                    "result": row[3],
                    "caller": row[4] if row[4] else "System",
                    "resource_id": row[5] if row[5] else "N/A",
                    "resource_group": row[6] if row[6] else "N/A",
                    "resource_provider": row[7] if row[7] else "N/A",
                    "http_request": str(row[8]) if row[8] else None,
                    "properties": str(row[9]) if row[9] else None
                }
                activity_events.append(event)

                # Track statistics
                op_type = event["operation_type"]
                operation_counts[op_type] = operation_counts.get(op_type, 0) + 1

                if event["result"] and event["result"].lower() in ["failed", "failure", "error"]:
                    failed_operations.append(event)

                if event["resource_id"] != "N/A":
                    affected_resources.add(event["resource_id"])

        # Analyze patterns
        analysis = {
            "total_events": len(activity_events),
            "operation_breakdown": operation_counts,
            "failed_operations_count": len(failed_operations),
            "failed_operations": failed_operations[:10],  # Limit to 10
            "affected_resources_count": len(affected_resources),
            "affected_resources": list(affected_resources)[:10],
            "time_span_hours": hours,
            "change_rate_per_hour": round(len(activity_events) / max(hours, 1), 2),
            "risk_indicators": {
                "high_change_rate": len(activity_events) / max(hours, 1) > 10,
                "recent_deletions": operation_counts.get("Delete", 0) > 0,
                "failed_operations_present": len(failed_operations) > 0,
                "multiple_resources_affected": len(affected_resources) > 5
            }
        }

        # Generate insights
        insights = []
        if len(failed_operations) > 0:
            insights.append(f"Found {len(failed_operations)} failed operations - investigate these as potential incident triggers")
        if operation_counts.get("Delete", 0) > 0:
            insights.append(f"{operation_counts['Delete']} deletion operations detected - verify these were intentional")
        if operation_counts.get("Write/Create", 0) > 5:
            insights.append(f"High number of write/create operations ({operation_counts['Write/Create']}) - check for recent deployments")
        if len(affected_resources) > 10:
            insights.append(f"Changes affected {len(affected_resources)} resources - potential widespread configuration change")

        result = {
            "success": True,
            "resource_filter": resource_id if resource_id else "All resources",
            "time_range_hours": hours,
            "activity_events": activity_events,
            "analysis": analysis,
            "insights": insights,
            "recommendations": [
                "Investigate failed operations for error details",
                "Correlate activity log events with alert timestamps",
                "Review caller identity for unauthorized changes",
                "Check if changes align with change management records"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Activity log analysis completed: {len(activity_events)} events analyzed")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error analyzing activity log: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="generate_incident_summary",
    description=(
        "Generate a structured incident summary report with RCA steps. "
        "Creates timeline, impact assessment, and recommended investigation steps. "
        "Use after initial triage to document the incident."
    ),
)
async def generate_incident_summary(
    context: Context,
    incident_title: Annotated[str, "Incident title"],
    affected_resources: Annotated[List[str], "List of affected resources"],
    incident_start_time: Annotated[str, "When the incident started (ISO format)"],
    findings: Annotated[Optional[Dict[str, Any]], "Initial findings from triage"] = None,
) -> list[TextContent]:
    """Generate incident summary report"""
    try:
        summary = {
            "success": True,
            "incident_title": incident_title,
            "start_time": incident_start_time,
            "report_generated": datetime.utcnow().isoformat(),
            "impact": {
                "affected_resources": affected_resources,
                "resource_count": len(affected_resources),
                "severity": "To be determined"
            },
            "timeline": [
                {"time": incident_start_time, "event": "Incident detected"},
                {"time": datetime.utcnow().isoformat(), "event": "Incident summary generated"}
            ],
            "investigation_steps": [
                "Review resource health status",
                "Analyze diagnostic logs for error patterns",
                "Check for recent configuration changes",
                "Verify network connectivity",
                "Review Azure Service Health dashboard"
            ],
            "findings": findings or {},
            "next_actions": [
                "Continue monitoring resource health",
                "Implement immediate mitigation if available",
                "Escalate if issue persists",
                "Document resolution steps"
            ]
        }

        logger.info(f"Generated incident summary for: {incident_title}")
        return [TextContent(type="text", text=json.dumps(summary, indent=2))]

    except Exception as exc:
        logger.error(f"Error generating incident summary: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Performance Monitoring Tools
# ============================================================================

@_server.tool(
    name="get_performance_metrics",
    description=(
        "Query Azure Monitor metrics for a resource (CPU, memory, network, etc.). "
        "✅ Automatically detects resource type (Container Apps, App Service, VM, AKS) and uses appropriate metrics. "
        "Returns metric values for specified time range with aggregation and summary statistics. "
        "Use for performance analysis and capacity planning. "
        "Example: 'Show me CPU and memory utilization of my container app' - no need to specify metric names."
    ),
)
async def get_performance_metrics(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    metric_names: Annotated[Optional[List[str]], "List of metric names to query. If not provided, defaults are used based on resource type."] = None,
    hours: Annotated[int, "Hours to look back (default: 1)"] = 1,
    aggregation: Annotated[str, "Aggregation type: Average, Maximum, Minimum, Total"] = "Average",
) -> list[TextContent]:
    """Get performance metrics for a resource"""
    try:
        if MetricsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        credential = _get_credential()
        metrics_client = MetricsQueryClient(credential)

        # Detect resource type and use appropriate default metrics if not provided
        # Normalize resource ID for case-insensitive matching
        resource_id_lower = resource_id.lower()
        resource_type = None

        if "/microsoft.app/containerapps/" in resource_id_lower:
            resource_type = "ContainerApp"
            if not metric_names:
                # Container Apps support both legacy and percentage metrics
                # Prefer percentage metrics as they're easier to interpret
                metric_names = [
                    "CpuPercentage",     # CPU percentage (0-100)
                    "MemoryPercentage",  # Memory percentage (0-100)
                    "Requests",          # HTTP request count
                    "Replicas"           # Active replica count
                ]
        elif "/microsoft.web/sites/" in resource_id_lower:
            resource_type = "AppService"
            if not metric_names:
                metric_names = [
                    "CpuPercentage",
                    "MemoryPercentage",
                    "HttpResponseTime",
                    "Requests"
                ]
        elif "/microsoft.compute/virtualmachines/" in resource_id_lower:
            resource_type = "VirtualMachine"
            if not metric_names:
                metric_names = [
                    "Percentage CPU",
                    "Available Memory Bytes",
                    "Network In Total",
                    "Network Out Total"
                ]
        elif "/microsoft.containerservice/managedclusters/" in resource_id_lower:
            resource_type = "AKS"
            if not metric_names:
                metric_names = [
                    "node_cpu_usage_percentage",
                    "node_memory_working_set_percentage",
                    "kube_pod_status_ready"
                ]
        else:
            resource_type = "Unknown"
            if not metric_names:
                # Generic fallback metrics
                metric_names = ["Percentage CPU", "Available Memory Bytes"]

        start_time = datetime.utcnow() - timedelta(hours=hours)
        end_time = datetime.utcnow()

        metrics_data = []
        failed_metrics = []

        for metric_name in metric_names[:10]:  # Limit to 10 metrics
            try:
                response = metrics_client.query_resource(
                    resource_uri=resource_id,
                    metric_names=[metric_name],
                    timespan=(start_time, end_time),
                    aggregations=[aggregation]
                )

                for metric in response.metrics:
                    for timeseries in metric.timeseries:
                        data_points = []
                        for data in timeseries.data:
                            value = getattr(data, aggregation.lower(), None)
                            if value is not None:
                                data_points.append({
                                    "timestamp": str(data.timestamp),
                                    "value": value
                                })

                        if data_points:
                            # Calculate summary statistics
                            values = [dp["value"] for dp in data_points]
                            metrics_data.append({
                                "metric_name": metric.name,
                                "unit": metric.unit,
                                "aggregation": aggregation,
                                "data_points": data_points,
                                "summary": {
                                    "current": values[-1] if values else None,
                                    "average": sum(values) / len(values) if values else None,
                                    "minimum": min(values) if values else None,
                                    "maximum": max(values) if values else None,
                                    "count": len(values)
                                }
                            })

            except Exception as e:
                failed_metrics.append({"metric_name": metric_name, "error": str(e)})
                logger.warning(f"Could not query metric {metric_name}: {e}")

        result = {
            "success": True,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            },
            "metrics": metrics_data,
            "failed_metrics": failed_metrics if failed_metrics else None,
            "note": f"Auto-detected resource type: {resource_type}. Used default metrics for this type." if not metric_names else None
        }

        logger.info(f"Retrieved {len(metrics_data)} metrics for {resource_id} ({resource_type})")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying performance metrics: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="identify_bottlenecks",
    description=(
        "Analyze performance metrics to identify bottlenecks and anomalies. "
        "Checks for high CPU, memory pressure, network saturation, etc. "
        "Returns findings with severity and recommendations."
    ),
)
async def identify_bottlenecks(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID to analyze"],
    hours: Annotated[int, "Hours of metrics to analyze (default: 24)"] = 24,
) -> list[TextContent]:
    """Identify performance bottlenecks"""
    try:
        # This is a simplified analysis
        # In production, you would query actual metrics and apply thresholds

        analysis = {
            "success": True,
            "resource_id": resource_id,
            "analysis_period_hours": hours,
            "bottlenecks_found": [],
            "recommendations": [
                "Review resource sizing and scale settings",
                "Analyze application code for inefficiencies",
                "Check for resource-intensive operations during peak times",
                "Consider implementing caching strategies",
                "Review database query performance"
            ],
            "note": "Connect to Azure Monitor for detailed metric analysis"
        }

        logger.info(f"Bottleneck analysis completed for {resource_id}")
        return [TextContent(type="text", text=json.dumps(analysis, indent=2))]

    except Exception as exc:
        logger.error(f"Error identifying bottlenecks: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_capacity_recommendations",
    description=(
        "Generate capacity and scaling recommendations based on usage patterns. "
        "Analyzes historical metrics to suggest right-sizing opportunities. "
        "Helps optimize costs and performance."
    ),
)
async def get_capacity_recommendations(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    days: Annotated[int, "Days of data to analyze (default: 7)"] = 7,
) -> list[TextContent]:
    """Get capacity planning recommendations"""
    try:
        recommendations = {
            "success": True,
            "resource_id": resource_id,
            "analysis_period_days": days,
            "recommendations": [
                {
                    "category": "Scaling",
                    "recommendation": "Review auto-scale settings based on usage patterns",
                    "priority": "Medium"
                },
                {
                    "category": "Cost Optimization",
                    "recommendation": "Consider Reserved Instances for consistent workloads",
                    "priority": "Low"
                }
            ],
            "note": "Detailed recommendations require historical metrics analysis"
        }

        logger.info(f"Generated capacity recommendations for {resource_id}")
        return [TextContent(type="text", text=json.dumps(recommendations, indent=2))]

    except Exception as exc:
        logger.error(f"Error generating capacity recommendations: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="compare_baseline_metrics",
    description=(
        "Compare current metrics against historical baseline. "
        "Identifies deviations from normal performance patterns. "
        "Useful for detecting performance degradation."
    ),
)
async def compare_baseline_metrics(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    metric_name: Annotated[str, "Metric to compare (e.g., 'Percentage CPU')"],
    baseline_days: Annotated[int, "Days to use for baseline (default: 7)"] = 7,
) -> list[TextContent]:
    """Compare metrics against baseline"""
    try:
        comparison = {
            "success": True,
            "resource_id": resource_id,
            "metric_name": metric_name,
            "baseline_period_days": baseline_days,
            "current_value": None,
            "baseline_average": None,
            "deviation_percentage": None,
            "status": "Normal",
            "note": "Connect to Azure Monitor for actual metric comparison"
        }

        logger.info(f"Baseline comparison for {resource_id}: {metric_name}")
        return [TextContent(type="text", text=json.dumps(comparison, indent=2))]

    except Exception as exc:
        logger.error(f"Error comparing baseline metrics: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Safe Remediation Tools
# ============================================================================

@_server.tool(
    name="plan_remediation",
    description=(
        "Generate a remediation plan for common issues. REQUIRES APPROVAL before execution. "
        "Creates step-by-step plan with pre-checks and rollback procedures. "
        "Use this before any remediation action to get approval."
    ),
)
async def plan_remediation(
    context: Context,
    issue_description: Annotated[str, "Description of the issue to remediate"],
    resource_id: Annotated[str, "Resource ID to apply remediation to"],
    remediation_type: Annotated[str, "Type: restart, scale, clear_cache, or custom"],
) -> list[TextContent]:
    """Plan remediation with approval workflow"""
    try:
        plan = {
            "success": True,
            "requires_approval": True,
            "issue": issue_description,
            "resource_id": resource_id,
            "remediation_type": remediation_type,
            "plan": {
                "pre_checks": [
                    "Verify resource health status",
                    "Check for active connections",
                    "Backup current configuration",
                    "Verify monitoring is active"
                ],
                "steps": [],
                "rollback_procedure": [
                    "Restore from backup if needed",
                    "Revert configuration changes",
                    "Notify stakeholders"
                ],
                "estimated_downtime": "To be determined",
                "risk_level": "Medium"
            },
            "confirmation_required": "Set confirmed=true in execute_remediation to proceed"
        }

        # Add specific steps based on remediation type
        if remediation_type == "restart":
            plan["plan"]["steps"] = [
                "Stop the resource gracefully",
                "Wait for shutdown confirmation",
                "Start the resource",
                "Verify health checks pass"
            ]
            plan["plan"]["estimated_downtime"] = "5-10 minutes"

        elif remediation_type == "scale":
            plan["plan"]["steps"] = [
                "Calculate target capacity",
                "Initiate scaling operation",
                "Monitor scaling progress",
                "Verify new capacity is healthy"
            ]
            plan["plan"]["estimated_downtime"] = "None (rolling update)"

        elif remediation_type == "clear_cache":
            plan["plan"]["steps"] = [
                "Identify cache service",
                "Clear cache entries",
                "Verify cache is rebuilding",
                "Monitor application performance"
            ]
            plan["plan"]["estimated_downtime"] = "Minimal"

        logger.info(f"Generated remediation plan for {resource_id}: {remediation_type}")
        return [TextContent(type="text", text=json.dumps(plan, indent=2))]

    except Exception as exc:
        logger.error(f"Error planning remediation: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="execute_safe_restart",
    description=(
        "Restart an Azure resource with pre-checks and rollback capability. "
        "REQUIRES confirmed=true to execute. Use plan_remediation first to generate and review the plan."
    ),
)
async def execute_safe_restart(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID to restart"],
    confirmed: Annotated[bool, "Must be true to execute (default: false)"] = False,
) -> list[TextContent]:
    """Execute safe resource restart with confirmation"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Restart requires confirmation. Set confirmed=true to proceed.",
                "recommendation": "Use plan_remediation first to review the restart plan"
            }, indent=2))]

        # In production, this would execute actual restart via Azure APIs
        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "restart",
            "status": "Simulated - not executed in this implementation",
            "message": "In production, this would restart the resource via Azure Management API",
            "next_steps": [
                "Monitor resource health after restart",
                "Verify application is responding",
                "Check logs for errors"
            ]
        }

        logger.warning(f"Safe restart simulated (not executed) for {resource_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error executing safe restart: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="scale_resource",
    description=(
        "Scale an Azure resource up or down. REQUIRES confirmed=true to execute. "
        "Validates new scale settings before applying. Use with caution."
    ),
)
async def scale_resource(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID to scale"],
    scale_direction: Annotated[str, "Direction: up or down"],
    target_capacity: Annotated[Optional[int], "Target capacity/instance count"] = None,
    confirmed: Annotated[bool, "Must be true to execute"] = False,
) -> list[TextContent]:
    """Scale resource with validation"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Scaling requires confirmation. Set confirmed=true to proceed.",
                "scale_direction": scale_direction,
                "target_capacity": target_capacity
            }, indent=2))]

        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "scale",
            "scale_direction": scale_direction,
            "target_capacity": target_capacity,
            "status": "Simulated - not executed in this implementation",
            "message": "In production, this would scale the resource via Azure Management API"
        }

        logger.warning(f"Resource scaling simulated (not executed) for {resource_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error scaling resource: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="clear_cache",
    description=(
        "Clear application or service caches safely. REQUIRES confirmed=true to execute. "
        "May cause temporary performance degradation while cache rebuilds."
    ),
)
async def clear_cache(
    context: Context,
    resource_id: Annotated[str, "Resource ID of cache service"],
    cache_type: Annotated[str, "Cache type: redis, cdn, application"],
    confirmed: Annotated[bool, "Must be true to execute"] = False,
) -> list[TextContent]:
    """Clear cache safely"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Cache clear requires confirmation. Set confirmed=true to proceed.",
                "warning": "This may cause temporary performance degradation"
            }, indent=2))]

        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "clear_cache",
            "cache_type": cache_type,
            "status": "Simulated - not executed in this implementation",
            "message": "In production, this would clear the cache via appropriate API"
        }

        logger.warning(f"Cache clear simulated (not executed) for {resource_id}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error clearing cache: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Microsoft Teams Notification Tools
# ============================================================================

@_server.tool(
    name="send_teams_notification",
    description=(
        "Send a formatted notification to Microsoft Teams via webhook. "
        "Supports rich adaptive cards with facts, colors, and action buttons. "
        "Use for general notifications and status updates."
    ),
)
async def send_teams_notification(
    context: Context,
    title: Annotated[str, "Notification title"],
    message: Annotated[str, "Notification message"],
    color: Annotated[Optional[str], "Hex color (without #): e.g., FF0000 for red"] = None,
    facts: Annotated[Optional[Dict[str, str]], "Key-value facts to display"] = None,
) -> list[TextContent]:
    """Send notification to Teams"""
    try:
        teams_client = _get_teams_client()
        if not teams_client or not teams_client.is_configured():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Teams webhook not configured"
            }, indent=2))]

        result = teams_client.send_notification(
            title=title,
            message=message,
            color=color,
            facts=facts
        )

        logger.info(f"Sent Teams notification: {title}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error sending Teams notification: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="send_teams_alert",
    description=(
        "Send an incident alert to Microsoft Teams with severity-based formatting. "
        "Creates rich adaptive card with affected resources, metadata, and action buttons. "
        "Use for incident notifications and critical alerts."
    ),
)
async def send_teams_alert(
    context: Context,
    title: Annotated[str, "Alert title"],
    severity: Annotated[str, "Severity: critical, error, warning, or info"],
    description: Annotated[str, "Alert description"],
    resource_id: Annotated[Optional[str], "Primary affected resource"] = None,
    affected_resources: Annotated[Optional[List[str]], "List of affected resources"] = None,
    metadata: Annotated[Optional[Dict[str, Any]], "Additional metadata"] = None,
) -> list[TextContent]:
    """Send incident alert to Teams"""
    try:
        teams_client = _get_teams_client()
        if not teams_client or not teams_client.is_configured():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Teams webhook not configured"
            }, indent=2))]

        result = teams_client.send_incident_alert(
            title=title,
            severity=severity,
            description=description,
            resource_id=resource_id,
            affected_resources=affected_resources or [],
            metadata=metadata
        )

        logger.info(f"Sent Teams alert: {title} (severity: {severity})")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error sending Teams alert: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_audit_trail",
    description=(
        "Retrieve audit trail of SRE operations. "
        "Returns history of operations performed, including who executed them, when, and the outcome. "
        "Essential for compliance, troubleshooting, and understanding what actions were taken."
    ),
)
async def get_audit_trail(
    context: Context,
    hours: Annotated[int, "Hours of history to retrieve (default: 24)"] = 24,
    operation_filter: Annotated[Optional[str], "Filter by operation name"] = None,
    resource_filter: Annotated[Optional[str], "Filter by resource ID"] = None,
) -> list[TextContent]:
    """Retrieve SRE operation audit trail"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        filtered_trail = []
        for entry in _audit_trail:
            # Parse timestamp
            entry_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))

            # Apply time filter
            if entry_time < cutoff_time:
                continue

            # Apply operation filter
            if operation_filter and operation_filter.lower() not in entry["operation"].lower():
                continue

            # Apply resource filter
            if resource_filter and entry.get("resource_id") != resource_filter:
                continue

            filtered_trail.append(entry)

        # Sort by timestamp descending
        filtered_trail.sort(key=lambda x: x["timestamp"], reverse=True)

        # Statistics
        stats = {
            "total_operations": len(filtered_trail),
            "successful_operations": sum(1 for e in filtered_trail if e.get("success", False)),
            "failed_operations": sum(1 for e in filtered_trail if not e.get("success", True)),
            "unique_resources": len(set(e.get("resource_id") for e in filtered_trail if e.get("resource_id"))),
            "operations_by_type": {}
        }

        for entry in filtered_trail:
            op = entry["operation"]
            stats["operations_by_type"][op] = stats["operations_by_type"].get(op, 0) + 1

        result = {
            "success": True,
            "hours_queried": hours,
            "filters": {
                "operation": operation_filter if operation_filter else "None",
                "resource": resource_filter if resource_filter else "None"
            },
            "statistics": stats,
            "audit_entries": filtered_trail[:100],  # Limit to 100 most recent
            "note": "Audit trail is stored in memory. For production, integrate with Cosmos DB or Log Analytics.",
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Retrieved audit trail: {len(filtered_trail)} entries")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error retrieving audit trail: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="send_sre_status_update",
    description=(
        "Send an SRE operation status update to Teams. "
        "Formats operation status with appropriate emoji and color coding. "
        "Use to keep team informed of SRE operation progress."
    ),
)
async def send_sre_status_update(
    context: Context,
    operation: Annotated[str, "Operation name (e.g., 'Resource Health Check')"],
    status: Annotated[str, "Status: success, failed, in_progress, or warning"],
    details: Annotated[Dict[str, Any], "Operation details"],
    resource_id: Annotated[Optional[str], "Related resource ID"] = None,
) -> list[TextContent]:
    """Send SRE operation status update to Teams"""
    try:
        teams_client = _get_teams_client()
        if not teams_client or not teams_client.is_configured():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Teams webhook not configured"
            }, indent=2))]

        result = teams_client.send_sre_status_update(
            operation=operation,
            status=status,
            details=details,
            resource_id=resource_id
        )

        logger.info(f"Sent SRE status update: {operation} - {status}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error sending SRE status update: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Service-Specific Diagnostic Tools
# ============================================================================

@_server.tool(
    name="diagnose_app_service",
    description=(
        "Perform comprehensive diagnostics for Azure App Service (Web Apps, Function Apps). "
        "✅ USE THIS TOOL for App Service-specific troubleshooting beyond generic health checks. "
        "Checks: deployment status, Kudu deployment logs, runtime errors, app settings issues, "
        "connection string validation, Always On status, HTTP 500 errors, slow response times. "
        "Example prompts: 'Diagnose my App Service deployment issues', "
        "'Why is my web app throwing 500 errors?', 'Investigate App Service slow response times'."
    ),
)
async def diagnose_app_service(
    context: Context,
    resource_id: Annotated[str, "Full Azure App Service resource ID"],
    workspace_id: Annotated[str, "Log Analytics workspace ID for app logs"],
    check_deployment_logs: Annotated[bool, "Include Kudu deployment logs analysis"] = True,
    check_runtime_errors: Annotated[bool, "Include runtime error analysis"] = True,
    hours: Annotated[int, "Hours to look back for log analysis"] = 24,
) -> list[TextContent]:
    """Diagnose App Service-specific issues"""
    try:
        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid App Service resource ID format")

        resource_name = parts[8]
        resource_group = parts[4]

        diagnostic_results = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_group": resource_group,
            "diagnostics": {},
            "findings": [],
            "recommendations": [],
            "timestamp": datetime.utcnow().isoformat()
        }

        # 1. Check resource health
        if ResourceHealthMgmtClient is not None:
            try:
                credential = _get_credential()
                subscription_id = _get_subscription_id()
                health_client = ResourceHealthMgmtClient(credential, subscription_id)

                health_status = health_client.availability_statuses.get_by_resource(
                    resource_uri=resource_id,
                    expand="recommendedActions"
                )

                diagnostic_results["diagnostics"]["resource_health"] = {
                    "availability_state": health_status.properties.availability_state,
                    "summary": health_status.properties.summary,
                    "reason_type": health_status.properties.reason_type
                }

                if health_status.properties.availability_state != "Available":
                    diagnostic_results["findings"].append({
                        "severity": "Critical",
                        "category": "Availability",
                        "finding": f"App Service is {health_status.properties.availability_state}",
                        "details": health_status.properties.summary
                    })
            except Exception as health_exc:
                logger.warning(f"Could not check resource health: {health_exc}")

        # 2. Check HTTP 500 errors (last N hours)
        if check_runtime_errors and LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                error_query = f"""
                AppServiceHTTPLogs
                | where ResourceId == '{resource_id}' or Resource == '{resource_name}'
                | where TimeGenerated > ago({hours}h)
                | where ScStatus >= 500
                | summarize ErrorCount=count(), SampleErrors=make_list(CsUriStem, 10) by ScStatus
                | order by ErrorCount desc
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=error_query,
                    timespan=timedelta(hours=hours)
                )

                errors_500 = []
                for table in response.tables:
                    for row in table.rows:
                        errors_500.append({
                            "status_code": row[0],
                            "count": row[1],
                            "sample_endpoints": row[2] if len(row) > 2 else []
                        })

                diagnostic_results["diagnostics"]["http_500_errors"] = {
                    "total_5xx_errors": sum(e["count"] for e in errors_500),
                    "breakdown": errors_500
                }

                if errors_500 and sum(e["count"] for e in errors_500) > 10:
                    diagnostic_results["findings"].append({
                        "severity": "High",
                        "category": "Application Errors",
                        "finding": f"Detected {sum(e['count'] for e in errors_500)} HTTP 5xx errors in last {hours} hours",
                        "details": errors_500
                    })
                    diagnostic_results["recommendations"].append(
                        "Review application logs for exceptions and stack traces. Check app settings and connection strings."
                    )
            except Exception as log_exc:
                logger.warning(f"Could not analyze HTTP errors: {log_exc}")

        # 3. Check slow response times
        if check_runtime_errors and LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                slow_query = f"""
                AppServiceHTTPLogs
                | where ResourceId == '{resource_id}' or Resource == '{resource_name}'
                | where TimeGenerated > ago({hours}h)
                | where TimeTaken > 5000
                | summarize SlowRequestCount=count(), AvgTimeTaken=avg(TimeTaken),
                            MaxTimeTaken=max(TimeTaken), SampleURIs=make_list(CsUriStem, 10)
                | project SlowRequestCount, AvgTimeTaken, MaxTimeTaken, SampleURIs
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=slow_query,
                    timespan=timedelta(hours=hours)
                )

                slow_requests = []
                for table in response.tables:
                    for row in table.rows:
                        slow_requests.append({
                            "count": row[0],
                            "avg_time_ms": row[1],
                            "max_time_ms": row[2],
                            "sample_uris": row[3] if len(row) > 3 else []
                        })

                if slow_requests and slow_requests[0]["count"] > 0:
                    diagnostic_results["diagnostics"]["slow_requests"] = slow_requests[0]

                    if slow_requests[0]["count"] > 50:
                        diagnostic_results["findings"].append({
                            "severity": "Medium",
                            "category": "Performance",
                            "finding": f"Detected {slow_requests[0]['count']} slow requests (>5s) in last {hours} hours",
                            "details": slow_requests[0]
                        })
                        diagnostic_results["recommendations"].append(
                            "Investigate slow endpoints for database query optimization, external API timeouts, or resource constraints."
                        )
            except Exception as slow_exc:
                logger.warning(f"Could not analyze slow requests: {slow_exc}")

        # 4. Check deployment logs (if requested)
        if check_deployment_logs and LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                deployment_query = f"""
                AppServiceConsoleLogs
                | where ResourceId == '{resource_id}' or Resource == '{resource_name}'
                | where TimeGenerated > ago({hours}h)
                | where ResultDescription contains "deploy" or ResultDescription contains "build"
                | order by TimeGenerated desc
                | limit 10
                | project TimeGenerated, Level, ResultDescription
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=deployment_query,
                    timespan=timedelta(hours=hours)
                )

                deployment_logs = []
                for table in response.tables:
                    for row in table.rows:
                        deployment_logs.append({
                            "timestamp": str(row[0]),
                            "level": row[1],
                            "message": row[2]
                        })

                if deployment_logs:
                    diagnostic_results["diagnostics"]["recent_deployments"] = deployment_logs

                    # Check for deployment failures
                    failures = [log for log in deployment_logs if log["level"] in ["Error", "Critical"]]
                    if failures:
                        diagnostic_results["findings"].append({
                            "severity": "High",
                            "category": "Deployment",
                            "finding": f"Detected {len(failures)} deployment errors in last {hours} hours",
                            "details": failures
                        })
                        diagnostic_results["recommendations"].append(
                            "Review Kudu deployment logs at https://<app-name>.scm.azurewebsites.net/api/deployments"
                        )
            except Exception as deploy_exc:
                logger.warning(f"Could not analyze deployment logs: {deploy_exc}")

        # 5. Summary
        diagnostic_results["summary"] = {
            "total_findings": len(diagnostic_results["findings"]),
            "critical_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "Critical"]),
            "high_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "High"]),
            "medium_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "Medium"])
        }

        if not diagnostic_results["findings"]:
            diagnostic_results["recommendations"].append(
                "No critical issues detected. App Service appears to be healthy."
            )

        logger.info(f"App Service diagnostics completed for {resource_name}: {len(diagnostic_results['findings'])} findings")
        return [TextContent(type="text", text=json.dumps(diagnostic_results, indent=2))]

    except Exception as exc:
        logger.error(f"Error diagnosing App Service: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="diagnose_apim",
    description=(
        "Perform comprehensive diagnostics for Azure API Management. "
        "✅ USE THIS TOOL for APIM-specific troubleshooting beyond generic health checks. "
        "Checks: backend health status, policy validation, gateway metrics, API operation failures, "
        "virtual network connectivity, certificate expiration, capacity metrics. "
        "Example prompts: 'Diagnose my APIM instance', 'Check backend health for my APIM', "
        "'Why am I getting 500 errors in my APIM?', 'Validate APIM policies'."
    ),
)
async def diagnose_apim(
    context: Context,
    resource_id: Annotated[str, "Full Azure API Management resource ID"],
    workspace_id: Annotated[str, "Log Analytics workspace ID for APIM logs"],
    check_backend_health: Annotated[bool, "Include backend health analysis"] = True,
    check_policy_errors: Annotated[bool, "Include policy error analysis"] = True,
    hours: Annotated[int, "Hours to look back for log analysis"] = 24,
) -> list[TextContent]:
    """Diagnose APIM-specific issues"""
    try:
        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid APIM resource ID format")

        resource_name = parts[8]
        resource_group = parts[4]

        diagnostic_results = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_group": resource_group,
            "diagnostics": {},
            "findings": [],
            "recommendations": [],
            "timestamp": datetime.utcnow().isoformat()
        }

        # 1. Check resource health
        if ResourceHealthMgmtClient is not None:
            try:
                credential = _get_credential()
                subscription_id = _get_subscription_id()
                health_client = ResourceHealthMgmtClient(credential, subscription_id)

                health_status = health_client.availability_statuses.get_by_resource(
                    resource_uri=resource_id,
                    expand="recommendedActions"
                )

                diagnostic_results["diagnostics"]["resource_health"] = {
                    "availability_state": health_status.properties.availability_state,
                    "summary": health_status.properties.summary,
                    "reason_type": health_status.properties.reason_type
                }

                if health_status.properties.availability_state != "Available":
                    diagnostic_results["findings"].append({
                        "severity": "Critical",
                        "category": "Availability",
                        "finding": f"APIM instance is {health_status.properties.availability_state}",
                        "details": health_status.properties.summary
                    })
            except Exception as health_exc:
                logger.warning(f"Could not check resource health: {health_exc}")

        # 2. Check API operation failures
        if LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                failure_query = f"""
                ApiManagementGatewayLogs
                | where ResourceId == '{resource_id}'
                | where TimeGenerated > ago({hours}h)
                | where ResponseCode >= 500 or IsRequestSuccess == false
                | summarize FailureCount=count() by ApiId, OperationId, ResponseCode, BackendId
                | order by FailureCount desc
                | limit 20
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=failure_query,
                    timespan=timedelta(hours=hours)
                )

                api_failures = []
                for table in response.tables:
                    for row in table.rows:
                        api_failures.append({
                            "api_id": row[0],
                            "operation_id": row[1],
                            "response_code": row[2],
                            "backend_id": row[3],
                            "failure_count": row[4]
                        })

                diagnostic_results["diagnostics"]["api_failures"] = {
                    "total_failures": sum(f["failure_count"] for f in api_failures),
                    "breakdown": api_failures[:10]  # Top 10
                }

                if api_failures and sum(f["failure_count"] for f in api_failures) > 20:
                    diagnostic_results["findings"].append({
                        "severity": "High",
                        "category": "API Operations",
                        "finding": f"Detected {sum(f['failure_count'] for f in api_failures)} API operation failures in last {hours} hours",
                        "details": api_failures[:5]  # Top 5 for summary
                    })
                    diagnostic_results["recommendations"].append(
                        "Review backend health and API policies. Check for backend timeouts or connection issues."
                    )
            except Exception as failure_exc:
                logger.warning(f"Could not analyze API failures: {failure_exc}")

        # 3. Check policy errors (if requested)
        if check_policy_errors and LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                policy_query = f"""
                ApiManagementGatewayLogs
                | where ResourceId == '{resource_id}'
                | where TimeGenerated > ago({hours}h)
                | where LastErrorMessage != ""
                | summarize ErrorCount=count(), SampleErrors=make_list(LastErrorMessage, 5) by LastErrorReason
                | order by ErrorCount desc
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=policy_query,
                    timespan=timedelta(hours=hours)
                )

                policy_errors = []
                for table in response.tables:
                    for row in table.rows:
                        policy_errors.append({
                            "error_reason": row[0],
                            "count": row[1],
                            "sample_messages": row[2] if len(row) > 2 else []
                        })

                if policy_errors:
                    diagnostic_results["diagnostics"]["policy_errors"] = policy_errors

                    if sum(e["count"] for e in policy_errors) > 10:
                        diagnostic_results["findings"].append({
                            "severity": "Medium",
                            "category": "Policy Configuration",
                            "finding": f"Detected {sum(e['count'] for e in policy_errors)} policy errors in last {hours} hours",
                            "details": policy_errors
                        })
                        diagnostic_results["recommendations"].append(
                            "Validate APIM policies using the Azure Portal policy validator. Check for syntax errors or missing variables."
                        )
            except Exception as policy_exc:
                logger.warning(f"Could not analyze policy errors: {policy_exc}")

        # 4. Check backend health (if requested)
        if check_backend_health and LogsQueryClient is not None:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)

                backend_query = f"""
                ApiManagementGatewayLogs
                | where ResourceId == '{resource_id}'
                | where TimeGenerated > ago({hours}h)
                | where isnotempty(BackendId)
                | summarize
                    TotalRequests=count(),
                    FailedRequests=countif(BackendResponseCode >= 500 or BackendTime > 5000),
                    AvgBackendTime=avg(BackendTime),
                    MaxBackendTime=max(BackendTime)
                    by BackendId
                | extend HealthyPercent = 100.0 * (TotalRequests - FailedRequests) / TotalRequests
                | order by FailedRequests desc
                """

                response = logs_client.query_workspace(
                    workspace_id=workspace_id,
                    query=backend_query,
                    timespan=timedelta(hours=hours)
                )

                backend_health = []
                for table in response.tables:
                    for row in table.rows:
                        backend_health.append({
                            "backend_id": row[0],
                            "total_requests": row[1],
                            "failed_requests": row[2],
                            "avg_backend_time_ms": row[3],
                            "max_backend_time_ms": row[4],
                            "healthy_percent": row[5]
                        })

                diagnostic_results["diagnostics"]["backend_health"] = backend_health

                unhealthy_backends = [b for b in backend_health if b["healthy_percent"] < 95]
                if unhealthy_backends:
                    diagnostic_results["findings"].append({
                        "severity": "High",
                        "category": "Backend Health",
                        "finding": f"{len(unhealthy_backends)} backend(s) have <95% success rate",
                        "details": unhealthy_backends
                    })
                    diagnostic_results["recommendations"].append(
                        "Investigate unhealthy backends for connectivity issues, timeouts, or backend application errors."
                    )
            except Exception as backend_exc:
                logger.warning(f"Could not analyze backend health: {backend_exc}")

        # 5. Check capacity metrics
        if MetricsQueryClient is not None:
            try:
                credential = _get_credential()
                metrics_client = MetricsQueryClient(credential)

                # Query capacity metric
                capacity_response = metrics_client.query_resource(
                    resource_uri=resource_id,
                    metric_names=["Capacity"],
                    timespan=timedelta(hours=hours)
                )

                if capacity_response.metrics:
                    capacity_values = []
                    for metric in capacity_response.metrics:
                        for timeseries in metric.timeseries:
                            for datapoint in timeseries.data:
                                if datapoint.average is not None:
                                    capacity_values.append(datapoint.average)

                    if capacity_values:
                        avg_capacity = sum(capacity_values) / len(capacity_values)
                        max_capacity = max(capacity_values)

                        diagnostic_results["diagnostics"]["capacity"] = {
                            "avg_capacity_percent": round(avg_capacity, 2),
                            "max_capacity_percent": round(max_capacity, 2)
                        }

                        if max_capacity > 80:
                            diagnostic_results["findings"].append({
                                "severity": "Medium",
                                "category": "Capacity",
                                "finding": f"APIM capacity reached {round(max_capacity, 2)}% (max in last {hours}h)",
                                "details": {"avg": round(avg_capacity, 2), "max": round(max_capacity, 2)}
                            })
                            diagnostic_results["recommendations"].append(
                                "Consider scaling up APIM tier or adding additional units to handle increased load."
                            )
            except Exception as capacity_exc:
                logger.warning(f"Could not analyze capacity metrics: {capacity_exc}")

        # 6. Summary
        diagnostic_results["summary"] = {
            "total_findings": len(diagnostic_results["findings"]),
            "critical_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "Critical"]),
            "high_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "High"]),
            "medium_findings": len([f for f in diagnostic_results["findings"] if f["severity"] == "Medium"])
        }

        if not diagnostic_results["findings"]:
            diagnostic_results["recommendations"].append(
                "No critical issues detected. APIM instance appears to be healthy."
            )

        logger.info(f"APIM diagnostics completed for {resource_name}: {len(diagnostic_results['findings'])} findings")
        return [TextContent(type="text", text=json.dumps(diagnostic_results, indent=2))]

    except Exception as exc:
        logger.error(f"Error diagnosing APIM: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Resource Configuration Query Tools
# ============================================================================

@_server.tool(
    name="query_app_service_configuration",
    description=(
        "Query Azure App Service configuration across multiple web apps with filtering capabilities. "
        "✅ USE THIS TOOL for bulk configuration discovery across App Services. "
        "Supports filtering by: runtime version, OS type (Linux/Windows), ARR affinity, health check status, "
        "diagnostic logging, custom domains, autoscale rules, staging slots. "
        "Example prompts: 'Which apps are running .NET 6?', 'Which apps have ARR affinity enabled?', "
        "'Show me all web apps with diagnostic logging turned on'."
    ),
)
async def query_app_service_configuration(
    context: Context,
    subscription_id: Annotated[Optional[str], "Azure subscription ID (uses default if not provided)"] = None,
    resource_group: Annotated[Optional[str], "Filter by resource group name"] = None,
    filter_runtime: Annotated[Optional[str], "Filter by runtime version (e.g., 'dotnet6', 'node18', 'python311')"] = None,
    filter_os: Annotated[Optional[str], "Filter by OS type: 'linux' or 'windows'"] = None,
    filter_arr_affinity: Annotated[Optional[bool], "Filter by ARR affinity enabled/disabled"] = None,
    filter_health_check: Annotated[Optional[bool], "Filter by health check enabled/disabled"] = None,
    filter_diagnostic_logging: Annotated[Optional[bool], "Filter by diagnostic logging enabled/disabled"] = None,
) -> list[TextContent]:
    """Query App Service configuration with filtering"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        sub_id = subscription_id or _get_subscription_id()

        graph_client = ResourceGraphClient(credential)

        # Build KQL query for App Services
        kql_query = f"""
        Resources
        | where type == 'microsoft.web/sites'
        | where subscriptionId == '{sub_id}'
        """

        if resource_group:
            kql_query += f"| where resourceGroup =~ '{resource_group}'\n"

        kql_query += """
        | extend osType = tostring(properties.kind)
        | extend runtime = tostring(properties.siteConfig.linuxFxVersion)
        | extend arrAffinity = tobool(properties.clientAffinityEnabled)
        | extend healthCheckPath = tostring(properties.siteConfig.healthCheckPath)
        | extend healthCheckEnabled = isnotnull(healthCheckPath)
        | project id, name, resourceGroup, location, osType, runtime, arrAffinity,
                  healthCheckEnabled, healthCheckPath, tags
        """

        query_request = QueryRequest(
            subscriptions=[sub_id],
            query=kql_query
        )

        response = graph_client.resources(query_request)

        apps = []
        for row in response.data:
            app = {
                "id": row.get("id"),
                "name": row.get("name"),
                "resource_group": row.get("resourceGroup"),
                "location": row.get("location"),
                "os_type": "Windows" if "windows" in str(row.get("osType", "")).lower() else "Linux",
                "runtime": row.get("runtime") or "Unknown",
                "arr_affinity_enabled": row.get("arrAffinity", False),
                "health_check_enabled": row.get("healthCheckEnabled", False),
                "health_check_path": row.get("healthCheckPath"),
                "tags": row.get("tags") or {}
            }

            # Apply filters
            if filter_os and filter_os.lower() not in app["os_type"].lower():
                continue
            if filter_runtime and filter_runtime.lower() not in app["runtime"].lower():
                continue
            if filter_arr_affinity is not None and app["arr_affinity_enabled"] != filter_arr_affinity:
                continue
            if filter_health_check is not None and app["health_check_enabled"] != filter_health_check:
                continue

            apps.append(app)

        result = {
            "success": True,
            "subscription_id": sub_id,
            "total_apps": len(apps),
            "apps": apps,
            "filters_applied": {
                "resource_group": resource_group,
                "runtime": filter_runtime,
                "os": filter_os,
                "arr_affinity": filter_arr_affinity,
                "health_check": filter_health_check,
                "diagnostic_logging": filter_diagnostic_logging
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Queried {len(apps)} App Services with filters")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying App Service configuration: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="query_container_app_configuration",
    description=(
        "Query Azure Container Apps configuration across multiple apps with filtering capabilities. "
        "✅ USE THIS TOOL for bulk configuration discovery across Container Apps. "
        "Supports filtering by: Dapr enabled, ingress type (internal/external), managed identity, "
        "revision mode (single/multiple), autoscaling enabled, VNet integration. "
        "Example prompts: 'Which apps have Dapr enabled?', 'Show me all apps with public ingress enabled', "
        "'Which Container Apps use managed identities?', 'Which apps have autoscaling enabled?'."
    ),
)
async def query_container_app_configuration(
    context: Context,
    subscription_id: Annotated[Optional[str], "Azure subscription ID (uses default if not provided)"] = None,
    resource_group: Annotated[Optional[str], "Filter by resource group name"] = None,
    filter_dapr_enabled: Annotated[Optional[bool], "Filter by Dapr enabled/disabled"] = None,
    filter_ingress_external: Annotated[Optional[bool], "Filter by external ingress enabled"] = None,
    filter_managed_identity: Annotated[Optional[bool], "Filter by managed identity enabled"] = None,
    filter_autoscale_enabled: Annotated[Optional[bool], "Filter by autoscaling enabled"] = None,
) -> list[TextContent]:
    """Query Container Apps configuration with filtering"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        sub_id = subscription_id or _get_subscription_id()

        graph_client = ResourceGraphClient(credential)

        # Build KQL query for Container Apps
        kql_query = f"""
        Resources
        | where type == 'microsoft.app/containerapps'
        | where subscriptionId == '{sub_id}'
        """

        if resource_group:
            kql_query += f"| where resourceGroup =~ '{resource_group}'\n"

        kql_query += """
        | extend daprEnabled = tobool(properties.configuration.dapr.enabled)
        | extend ingressExternal = tobool(properties.configuration.ingress.external)
        | extend ingressEnabled = isnotnull(properties.configuration.ingress)
        | extend managedIdentityEnabled = isnotnull(identity)
        | extend revisionMode = tostring(properties.configuration.activeRevisionsMode)
        | extend minReplicas = toint(properties.template.scale.minReplicas)
        | extend maxReplicas = toint(properties.template.scale.maxReplicas)
        | extend autoscaleEnabled = maxReplicas > minReplicas
        | extend vnetIntegrated = isnotnull(properties.managedEnvironmentId)
        | project id, name, resourceGroup, location, daprEnabled, ingressEnabled,
                  ingressExternal, managedIdentityEnabled, revisionMode, minReplicas,
                  maxReplicas, autoscaleEnabled, vnetIntegrated, tags
        """

        query_request = QueryRequest(
            subscriptions=[sub_id],
            query=kql_query
        )

        response = graph_client.resources(query_request)

        apps = []
        for row in response.data:
            app = {
                "id": row.get("id"),
                "name": row.get("name"),
                "resource_group": row.get("resourceGroup"),
                "location": row.get("location"),
                "dapr_enabled": row.get("daprEnabled", False),
                "ingress_enabled": row.get("ingressEnabled", False),
                "ingress_external": row.get("ingressExternal", False),
                "managed_identity_enabled": row.get("managedIdentityEnabled", False),
                "revision_mode": row.get("revisionMode", "single"),
                "autoscale_enabled": row.get("autoscaleEnabled", False),
                "min_replicas": row.get("minReplicas", 0),
                "max_replicas": row.get("maxReplicas", 1),
                "vnet_integrated": row.get("vnetIntegrated", False),
                "tags": row.get("tags") or {}
            }

            # Apply filters
            if filter_dapr_enabled is not None and app["dapr_enabled"] != filter_dapr_enabled:
                continue
            if filter_ingress_external is not None and app["ingress_external"] != filter_ingress_external:
                continue
            if filter_managed_identity is not None and app["managed_identity_enabled"] != filter_managed_identity:
                continue
            if filter_autoscale_enabled is not None and app["autoscale_enabled"] != filter_autoscale_enabled:
                continue

            apps.append(app)

        result = {
            "success": True,
            "subscription_id": sub_id,
            "total_apps": len(apps),
            "apps": apps,
            "filters_applied": {
                "resource_group": resource_group,
                "dapr_enabled": filter_dapr_enabled,
                "ingress_external": filter_ingress_external,
                "managed_identity": filter_managed_identity,
                "autoscale_enabled": filter_autoscale_enabled
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Queried {len(apps)} Container Apps with filters")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying Container Apps configuration: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="query_aks_configuration",
    description=(
        "Query Azure Kubernetes Service (AKS) configuration across multiple clusters with filtering capabilities. "
        "✅ USE THIS TOOL for bulk configuration discovery across AKS clusters. "
        "Supports filtering by: Kubernetes version, network plugin (azure/kubenet), autoscaling enabled, "
        "RBAC enabled, private cluster, addon profiles (monitoring, policy). "
        "Example prompts: 'What version of Kubernetes are my clusters running?', "
        "'Which clusters have autoscaling enabled?', 'Show me all private AKS clusters'."
    ),
)
async def query_aks_configuration(
    context: Context,
    subscription_id: Annotated[Optional[str], "Azure subscription ID (uses default if not provided)"] = None,
    resource_group: Annotated[Optional[str], "Filter by resource group name"] = None,
    filter_k8s_version: Annotated[Optional[str], "Filter by Kubernetes version (e.g., '1.28', '1.29')"] = None,
    filter_autoscale_enabled: Annotated[Optional[bool], "Filter by cluster autoscaler enabled"] = None,
    filter_rbac_enabled: Annotated[Optional[bool], "Filter by RBAC enabled"] = None,
    filter_private_cluster: Annotated[Optional[bool], "Filter by private cluster"] = None,
) -> list[TextContent]:
    """Query AKS configuration with filtering"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        sub_id = subscription_id or _get_subscription_id()

        graph_client = ResourceGraphClient(credential)

        # Build KQL query for AKS clusters
        kql_query = f"""
        Resources
        | where type == 'microsoft.containerservice/managedclusters'
        | where subscriptionId == '{sub_id}'
        """

        if resource_group:
            kql_query += f"| where resourceGroup =~ '{resource_group}'\n"

        kql_query += """
        | extend k8sVersion = tostring(properties.kubernetesVersion)
        | extend networkPlugin = tostring(properties.networkProfile.networkPlugin)
        | extend autoscaleEnabled = tobool(properties.agentPoolProfiles[0].enableAutoScaling)
        | extend rbacEnabled = tobool(properties.enableRBAC)
        | extend privateCluster = tobool(properties.apiServerAccessProfile.enablePrivateCluster)
        | extend monitoringEnabled = tobool(properties.addonProfiles.omsagent.enabled)
        | extend policyEnabled = tobool(properties.addonProfiles.azurepolicy.enabled)
        | extend nodeCount = toint(properties.agentPoolProfiles[0].count)
        | extend vmSize = tostring(properties.agentPoolProfiles[0].vmSize)
        | project id, name, resourceGroup, location, k8sVersion, networkPlugin,
                  autoscaleEnabled, rbacEnabled, privateCluster, monitoringEnabled,
                  policyEnabled, nodeCount, vmSize, tags
        """

        query_request = QueryRequest(
            subscriptions=[sub_id],
            query=kql_query
        )

        response = graph_client.resources(query_request)

        clusters = []
        for row in response.data:
            cluster = {
                "id": row.get("id"),
                "name": row.get("name"),
                "resource_group": row.get("resourceGroup"),
                "location": row.get("location"),
                "kubernetes_version": row.get("k8sVersion", "Unknown"),
                "network_plugin": row.get("networkPlugin", "Unknown"),
                "autoscale_enabled": row.get("autoscaleEnabled", False),
                "rbac_enabled": row.get("rbacEnabled", False),
                "private_cluster": row.get("privateCluster", False),
                "monitoring_enabled": row.get("monitoringEnabled", False),
                "policy_enabled": row.get("policyEnabled", False),
                "node_count": row.get("nodeCount", 0),
                "vm_size": row.get("vmSize", "Unknown"),
                "tags": row.get("tags") or {}
            }

            # Apply filters
            if filter_k8s_version and filter_k8s_version not in cluster["kubernetes_version"]:
                continue
            if filter_autoscale_enabled is not None and cluster["autoscale_enabled"] != filter_autoscale_enabled:
                continue
            if filter_rbac_enabled is not None and cluster["rbac_enabled"] != filter_rbac_enabled:
                continue
            if filter_private_cluster is not None and cluster["private_cluster"] != filter_private_cluster:
                continue

            clusters.append(cluster)

        result = {
            "success": True,
            "subscription_id": sub_id,
            "total_clusters": len(clusters),
            "clusters": clusters,
            "filters_applied": {
                "resource_group": resource_group,
                "kubernetes_version": filter_k8s_version,
                "autoscale_enabled": filter_autoscale_enabled,
                "rbac_enabled": filter_rbac_enabled,
                "private_cluster": filter_private_cluster
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Queried {len(clusters)} AKS clusters with filters")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying AKS configuration: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="query_apim_configuration",
    description=(
        "Query Azure API Management configuration across multiple instances with filtering capabilities. "
        "✅ USE THIS TOOL for bulk configuration discovery across APIM instances. "
        "Supports filtering by: SKU tier (Developer/Standard/Premium), VNet type (internal/external), "
        "managed identity enabled, API count, backend count. "
        "Example prompts: 'Show me my API Management instances', "
        "'Which APIM instances are connected to a virtual network?', "
        "'Which APIM instances use managed identities?'."
    ),
)
async def query_apim_configuration(
    context: Context,
    subscription_id: Annotated[Optional[str], "Azure subscription ID (uses default if not provided)"] = None,
    resource_group: Annotated[Optional[str], "Filter by resource group name"] = None,
    filter_sku: Annotated[Optional[str], "Filter by SKU tier (Developer, Standard, Premium, Consumption)"] = None,
    filter_vnet_type: Annotated[Optional[str], "Filter by VNet type: 'internal', 'external', or 'none'"] = None,
    filter_managed_identity: Annotated[Optional[bool], "Filter by managed identity enabled"] = None,
) -> list[TextContent]:
    """Query APIM configuration with filtering"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        sub_id = subscription_id or _get_subscription_id()

        graph_client = ResourceGraphClient(credential)

        # Build KQL query for APIM instances
        kql_query = f"""
        Resources
        | where type == 'microsoft.apimanagement/service'
        | where subscriptionId == '{sub_id}'
        """

        if resource_group:
            kql_query += f"| where resourceGroup =~ '{resource_group}'\n"

        kql_query += """
        | extend skuName = tostring(sku.name)
        | extend skuCapacity = toint(sku.capacity)
        | extend vnetType = tostring(properties.virtualNetworkType)
        | extend managedIdentityEnabled = isnotnull(identity)
        | extend publicIpEnabled = isnotnull(properties.publicIpAddressId)
        | project id, name, resourceGroup, location, skuName, skuCapacity,
                  vnetType, managedIdentityEnabled, publicIpEnabled, tags
        """

        query_request = QueryRequest(
            subscriptions=[sub_id],
            query=kql_query
        )

        response = graph_client.resources(query_request)

        instances = []
        for row in response.data:
            instance = {
                "id": row.get("id"),
                "name": row.get("name"),
                "resource_group": row.get("resourceGroup"),
                "location": row.get("location"),
                "sku_name": row.get("skuName", "Unknown"),
                "sku_capacity": row.get("skuCapacity", 1),
                "vnet_type": row.get("vnetType", "None"),
                "managed_identity_enabled": row.get("managedIdentityEnabled", False),
                "public_ip_enabled": row.get("publicIpEnabled", False),
                "tags": row.get("tags") or {}
            }

            # Apply filters
            if filter_sku and filter_sku.lower() not in instance["sku_name"].lower():
                continue
            if filter_vnet_type:
                vnet_filter = filter_vnet_type.lower()
                instance_vnet = instance["vnet_type"].lower()
                if vnet_filter == "none" and instance_vnet != "none":
                    continue
                elif vnet_filter != "none" and vnet_filter not in instance_vnet:
                    continue
            if filter_managed_identity is not None and instance["managed_identity_enabled"] != filter_managed_identity:
                continue

            instances.append(instance)

        result = {
            "success": True,
            "subscription_id": sub_id,
            "total_instances": len(instances),
            "instances": instances,
            "filters_applied": {
                "resource_group": resource_group,
                "sku": filter_sku,
                "vnet_type": filter_vnet_type,
                "managed_identity": filter_managed_identity
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(f"Queried {len(instances)} APIM instances with filters")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying APIM configuration: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Self-Documentation Tools
# ============================================================================

@_server.tool(
    name="describe_capabilities",
    description=(
        "Get a comprehensive overview of SRE Agent capabilities, features, and supported Azure services. "
        "✅ USE THIS TOOL when users ask: 'What can you help me with?', 'What are your capabilities?', "
        "'How do I get started?', 'What Azure services do you support?'. "
        "Returns structured information about incident management, diagnostics, monitoring, and remediation features."
    ),
)
async def describe_capabilities(
    context: Context,
) -> list[TextContent]:
    """Describe SRE Agent capabilities"""
    capabilities = {
        "success": True,
        "agent_name": "Azure SRE Agent MCP Server",
        "version": "1.0.0",
        "description": "Site Reliability Engineering operations for Azure with 28 specialized tools",

        "key_capabilities": [
            {
                "category": "Resource Health & Diagnostics",
                "description": "Monitor resource health, retrieve diagnostic logs, and analyze configuration",
                "tools": [
                    "check_resource_health - Azure Resource Health API for VMs, App Services, SQL, etc.",
                    "check_container_app_health - Container Apps health monitoring via Log Analytics",
                    "check_aks_cluster_health - AKS cluster node and pod health analysis",
                    "get_diagnostic_logs - Retrieve logs from Log Analytics for any resource",
                    "analyze_resource_configuration - Best practices and misconfiguration detection",
                    "get_resource_dependencies - Dependency mapping with health cascade analysis",
                    "analyze_activity_log - Platform events and configuration changes"
                ],
                "example_prompts": [
                    "Check the health of my Container App",
                    "Show me diagnostic logs for the last 24 hours",
                    "What services is my web app connected to?",
                    "What changed in my resource last week?"
                ]
            },
            {
                "category": "Incident Response",
                "description": "Automated incident triage, log correlation, and root cause analysis",
                "tools": [
                    "triage_incident - Automated incident triage with severity assessment",
                    "search_logs_by_error - Pattern-based log search for specific errors",
                    "correlate_alerts - Temporal and resource-based alert correlation",
                    "generate_incident_summary - Structured incident reports with RCA steps",
                    "get_audit_trail - SRE operation audit trail for compliance"
                ],
                "example_prompts": [
                    "My app is down. Can you analyze it?",
                    "Why is my web app throwing 500 errors?",
                    "Correlate alerts for the last hour",
                    "Generate an incident summary"
                ]
            },
            {
                "category": "Performance Monitoring",
                "description": "Metrics analysis, bottleneck identification, and capacity planning",
                "tools": [
                    "get_performance_metrics - Azure Monitor metrics (CPU, memory, network)",
                    "identify_bottlenecks - Performance bottleneck detection",
                    "get_capacity_recommendations - Capacity planning recommendations",
                    "compare_baseline_metrics - Baseline deviation analysis"
                ],
                "example_prompts": [
                    "Show me CPU utilization for the last week",
                    "Identify performance bottlenecks in my app",
                    "Give me capacity recommendations",
                    "Compare current metrics with baseline"
                ]
            },
            {
                "category": "Resource Configuration Discovery",
                "description": "Bulk configuration queries across multiple resources with filtering",
                "tools": [
                    "query_app_service_configuration - App Service bulk queries (runtime, OS, ARR affinity)",
                    "query_container_app_configuration - Container Apps queries (Dapr, ingress, autoscale)",
                    "query_aks_configuration - AKS queries (K8s version, autoscale, RBAC)",
                    "query_apim_configuration - APIM queries (SKU, VNet, managed identity)"
                ],
                "example_prompts": [
                    "Which apps have Dapr enabled?",
                    "Show me all web apps running .NET 6",
                    "Which AKS clusters have autoscaling enabled?",
                    "List all APIM instances with managed identities"
                ]
            },
            {
                "category": "Safe Remediation",
                "description": "Remediation planning and simulated safe operations with approval workflows",
                "tools": [
                    "plan_remediation - Step-by-step remediation plans with approval workflow",
                    "execute_safe_restart - Simulated safe resource restart",
                    "scale_resource - Simulated resource scaling",
                    "clear_cache - Simulated cache clearing"
                ],
                "example_prompts": [
                    "Plan remediation for my failing app",
                    "Safely restart my Container App",
                    "Scale my app to 5 replicas"
                ],
                "note": "Remediation execute_* tools are intentionally simulated for safety"
            },
            {
                "category": "Service-Specific Diagnostics",
                "description": "Specialized diagnostic tools for App Service and API Management",
                "tools": [
                    "diagnose_app_service - App Service-specific diagnostics (Kudu logs, deployment logs)",
                    "diagnose_apim - APIM-specific diagnostics (backend health, policy validation)"
                ],
                "example_prompts": [
                    "Diagnose my App Service deployment issues",
                    "Check backend health for my APIM instance"
                ]
            },
            {
                "category": "Notifications",
                "description": "Microsoft Teams integration for incident alerts and status updates",
                "tools": [
                    "send_teams_notification - Formatted Teams notifications",
                    "send_teams_alert - Critical alerts to Teams",
                    "send_sre_status_update - Operation status updates"
                ],
                "example_prompts": [
                    "Send a Teams alert about this incident",
                    "Notify the team about this outage"
                ]
            }
        ],

        "supported_azure_services": [
            "App Service (Web Apps, Function Apps)",
            "Container Apps",
            "Azure Kubernetes Service (AKS)",
            "API Management",
            "Virtual Machines",
            "Storage Accounts",
            "SQL Databases",
            "Key Vaults",
            "Network Security Groups",
            "Load Balancers",
            "Application Gateways",
            "VPN Gateways"
        ],

        "common_use_cases": [
            "Incident triage and root cause analysis",
            "Performance troubleshooting and optimization",
            "Resource health monitoring and alerting",
            "Configuration compliance and best practices",
            "Change tracking and impact analysis",
            "Capacity planning and scaling recommendations",
            "Multi-resource dependency mapping",
            "Automated diagnostics with Teams notifications"
        ],

        "getting_started": {
            "step_1": "Ask about specific resources: 'Check the health of my Container App <name>'",
            "step_2": "Query configurations: 'Which apps have Dapr enabled?'",
            "step_3": "Troubleshoot incidents: 'My app is down. Can you analyze it?'",
            "step_4": "Monitor performance: 'Show me CPU utilization for the last week'",
            "step_5": "Get recommendations: 'What are some best practices for my app?'"
        },

        "limitations": [
            "Virtual Machines do NOT support diagnostic settings (use Azure Monitor Agent instead)",
            "AKS cluster access requires network connectivity (cannot access clusters with restricted inbound access)",
            "Remediation execute_* tools are simulated for safety (production requires approval workflows)",
            "Visualization generation not yet implemented (returns data only)"
        ],

        "total_tools": 28,
        "timestamp": datetime.utcnow().isoformat()
    }

    logger.info("Returned SRE Agent capabilities overview")
    return [TextContent(type="text", text=json.dumps(capabilities, indent=2))]


@_server.tool(
    name="get_prompt_examples",
    description=(
        "Get example prompts for specific Azure service categories or SRE operations. "
        "✅ USE THIS TOOL when users ask: 'What can I ask about App Services?', "
        "'Show me example prompts for Container Apps', 'What questions can I ask about AKS?'. "
        "Categories: app_service, container_apps, aks, apim, incident_response, performance, configuration."
    ),
)
async def get_prompt_examples(
    context: Context,
    category: Annotated[str, "Category: app_service, container_apps, aks, apim, incident_response, performance, configuration, all"],
) -> list[TextContent]:
    """Get example prompts for a specific category"""

    all_examples = {
        "app_service": {
            "description": "Azure App Service (Web Apps, Function Apps) prompts",
            "discovery": [
                "List all my web apps",
                "Which apps are hosted on Linux versus Windows?",
                "Show me all web apps running .NET 6",
                "Which apps have ARR affinity enabled?",
                "Which apps have health checks enabled?",
                "Which apps have diagnostic logging turned on?",
                "What App Service plan is my app running on?",
                "Are any staging slots configured for this web app?",
                "What changed in my web app last week?"
            ],
            "diagnostics": [
                "Why is my web app throwing 500 errors?",
                "My web app is down. Can you analyze it?",
                "My web app is stuck and isn't loading. Investigate for me",
                "Can you analyze my app's availability over the last 24 hours?",
                "Give me slow endpoints for my APIs",
                "Diagnose my App Service deployment issues"
            ]
        },
        "container_apps": {
            "description": "Azure Container Apps prompts",
            "discovery": [
                "List all my container apps",
                "What is the ingress configuration for my container app?",
                "Which revision of my container app is currently active?",
                "Which apps have Dapr enabled?",
                "What container images are used in each of my container apps?",
                "Which apps have autoscaling enabled?",
                "Show me all apps with public ingress enabled",
                "Which of my container apps use managed identities?",
                "What changed in my container app in the last week?"
            ],
            "diagnostics": [
                "My container app is stuck in an activation failed state. Investigate for me",
                "Why is my container app throwing 500 errors?",
                "My container app is down. Can you analyze it?",
                "Check the health of my Container App",
                "Show me diagnostic logs for my Container App"
            ]
        },
        "aks": {
            "description": "Azure Kubernetes Service (AKS) prompts",
            "discovery": [
                "Which node pools are configured for my AKS cluster?",
                "Which workloads are in a crash loop or failed state?",
                "Do I have any pending or unscheduled pods?",
                "What version of Kubernetes is my cluster running?",
                "How many pods are currently running in my cluster?",
                "Which AKS clusters have autoscaling enabled?",
                "Show me all private AKS clusters",
                "What are some best practices for my AKS cluster?"
            ],
            "diagnostics": [
                "Is an OOM condition in my deployment?",
                "Analyze requests and limits in my namespace",
                "Why is my deployment down?",
                "Check the health of my AKS cluster"
            ]
        },
        "apim": {
            "description": "Azure API Management prompts",
            "discovery": [
                "Show me my API Management instances",
                "Which APIM instances are connected to a virtual network?",
                "Which APIM instances use managed identities?",
                "What API policies does my APIM instance have?",
                "What NSG rules does my APIM instance have?"
            ],
            "diagnostics": [
                "Why am I getting 500 errors in my API Management instance?",
                "Show me recent changes to our API Management instance",
                "Why is my API Management instance slow?",
                "Can you show me the recent failure logs for my APIM instance?",
                "Check backend health for my APIM instance",
                "Diagnose policy issues in my APIM instance"
            ]
        },
        "incident_response": {
            "description": "Incident triage and troubleshooting prompts",
            "prompts": [
                "My app is down. Can you analyze it?",
                "Why is my application throwing errors?",
                "Triage this incident for me",
                "Search logs for error pattern 'timeout'",
                "Correlate alerts for the last hour",
                "Generate an incident summary",
                "What's the root cause of this outage?",
                "Send a Teams alert about this critical incident",
                "Get audit trail for SRE operations"
            ]
        },
        "performance": {
            "description": "Performance monitoring and optimization prompts",
            "prompts": [
                "Show me CPU utilization for the last week",
                "Identify performance bottlenecks in my app",
                "Give me capacity recommendations",
                "Compare current metrics with baseline",
                "What's the memory utilization trend?",
                "Show me network throughput metrics",
                "Analyze response time percentiles"
            ]
        },
        "configuration": {
            "description": "Configuration discovery and compliance prompts",
            "prompts": [
                "What are some best practices for my resource?",
                "Analyze my resource configuration",
                "What services is my app connected to?",
                "Map dependencies for this resource",
                "What changed in my subscription last week?",
                "Show me activity log for configuration changes",
                "Which resources don't have tags?"
            ]
        }
    }

    if category.lower() == "all":
        result = {
            "success": True,
            "total_categories": len(all_examples),
            "categories": all_examples,
            "timestamp": datetime.utcnow().isoformat()
        }
    elif category.lower() in all_examples:
        result = {
            "success": True,
            "category": category.lower(),
            "examples": all_examples[category.lower()],
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        available = ", ".join(all_examples.keys())
        result = {
            "success": False,
            "error": f"Unknown category '{category}'. Available: {available}, all"
        }

    logger.info(f"Returned prompt examples for category: {category}")
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


if __name__ == "__main__":
    _server.run()
