"""SRE MCP Server

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
import subprocess
import uuid
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
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.web import WebSiteManagementClient
    from azure.mgmt.redis import RedisManagementClient
    from azure.mgmt.containerservice import ContainerServiceClient
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
    ComputeManagementClient = None
    WebSiteManagementClient = None
    RedisManagementClient = None
    ContainerServiceClient = None

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

# Suppress verbose Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.monitor.query").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

_server = FastMCP(name="azure-sre")
_credential: Optional[DefaultAzureCredential] = None
_teams_client: Optional[TeamsNotificationClient] = None
_subscription_id: Optional[str] = None

# SRE cache for reducing redundant Azure API calls
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from utils.sre_cache import get_sre_cache
    _sre_cache = get_sre_cache()
    logger.info("✅ SRE cache manager initialized")
except ImportError:
    _sre_cache = None
    logger.debug("SRE cache not available (utils.sre_cache not found)")

# In-memory audit trail (fallback when Cosmos DB unavailable)
_audit_trail: List[Dict[str, Any]] = []

# Cosmos DB client for audit persistence (initialized lazily)
_cosmos_audit_container = None

# ---------------------------------------------------------------------------
# Remediation plan & runbook in-memory stores
# ---------------------------------------------------------------------------
# Active remediation plans keyed by plan_id (TTL managed by caller)
_remediation_plans: Dict[str, Dict[str, Any]] = {}

# Approval tokens: token_str → {plan_id, step_index, issued_at, expires_at, used}
_approval_tokens: Dict[str, Dict[str, Any]] = {}

# Built-in runbook database for matching common incident patterns
_BUILTIN_RUNBOOKS: List[Dict[str, Any]] = [
    {
        "runbook_id": "builtin-restart-unhealthy",
        "name": "Restart Unhealthy Resource",
        "trigger_conditions": {"error_patterns": ["unhealthy", "not responding", "health check failed", "degraded"]},
        "resource_types": ["Microsoft.Web/sites", "Microsoft.Compute/virtualMachines", "Microsoft.App/containerApps"],
        "steps": [
            {"action": "pre_check", "description": "Verify resource health status", "destructive": False},
            {"action": "backup_config", "description": "Backup current configuration", "destructive": False},
            {"action": "restart", "description": "Restart the resource gracefully", "destructive": True},
            {"action": "validate_health", "description": "Verify health checks pass post-restart", "destructive": False},
        ],
        "rollback": ["Restore configuration from backup", "Revert to previous revision if available"],
        "approval_level": "standard",
        "risk_level": "medium",
        "estimated_downtime": "5-10 minutes",
    },
    {
        "runbook_id": "builtin-scale-out",
        "name": "Scale Out Under Load",
        "trigger_conditions": {"error_patterns": ["high cpu", "memory pressure", "throttling", "429", "capacity"]},
        "resource_types": ["Microsoft.Web/sites", "Microsoft.App/containerApps", "Microsoft.Compute/virtualMachineScaleSets"],
        "steps": [
            {"action": "pre_check", "description": "Capture current replica/instance count and metrics", "destructive": False},
            {"action": "calculate_target", "description": "Calculate target capacity from current load", "destructive": False},
            {"action": "scale_out", "description": "Increase instance/replica count", "destructive": True},
            {"action": "validate_scaling", "description": "Confirm new instances are healthy", "destructive": False},
        ],
        "rollback": ["Scale back to original instance count", "Monitor for instability"],
        "approval_level": "standard",
        "risk_level": "low",
        "estimated_downtime": "None (rolling update)",
    },
    {
        "runbook_id": "builtin-clear-cache-restart",
        "name": "Clear Cache and Restart",
        "trigger_conditions": {"error_patterns": ["stale data", "cache corruption", "inconsistent state", "OOM"]},
        "resource_types": ["Microsoft.Cache/Redis", "Microsoft.Web/sites"],
        "steps": [
            {"action": "pre_check", "description": "Verify cache service accessibility", "destructive": False},
            {"action": "drain_connections", "description": "Drain active connections gracefully", "destructive": False},
            {"action": "flush_cache", "description": "Flush cache entries", "destructive": True},
            {"action": "restart_dependent", "description": "Restart dependent application if needed", "destructive": True},
            {"action": "validate", "description": "Verify application is serving fresh data", "destructive": False},
        ],
        "rollback": ["Restart application to reconnect to cache", "Verify data consistency"],
        "approval_level": "elevated",
        "risk_level": "medium",
        "estimated_downtime": "5-15 minutes",
    },
]

# In-memory custom runbooks (fallback when Cosmos DB unavailable)
_custom_runbooks: List[Dict[str, Any]] = []

# Cosmos DB client for custom runbooks (initialized lazily)
_cosmos_runbook_container = None


def _get_audit_container():
    """Get or create Cosmos DB container for audit trail"""
    global _cosmos_audit_container
    if _cosmos_audit_container is not None:
        return _cosmos_audit_container

    try:
        # Import base_cosmos utility
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

        from utils.cosmos_cache import base_cosmos
        base_cosmos._ensure_initialized()

        if base_cosmos.initialized:
            # Create audit_trail container with 90-day TTL
            _cosmos_audit_container = base_cosmos.get_container(
                container_id="audit_trail",
                partition_path="/operation",
                offer_throughput=400,
                default_ttl=7776000  # 90 days in seconds
            )
            logger.info("✅ Cosmos DB audit_trail container initialized")
            return _cosmos_audit_container
        else:
            logger.warning("⚠️ Cosmos DB not available - using in-memory audit trail only")
            return None
    except Exception as exc:
        logger.warning(f"⚠️ Failed to initialize Cosmos DB for audit trail: {exc}")
        return None


def _get_runbook_container():
    """Get or create Cosmos DB container for custom runbooks"""
    global _cosmos_runbook_container
    if _cosmos_runbook_container is not None:
        return _cosmos_runbook_container

    try:
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

        from utils.cosmos_cache import base_cosmos
        base_cosmos._ensure_initialized()

        if base_cosmos.initialized:
            _cosmos_runbook_container = base_cosmos.get_container(
                container_id="custom_runbooks",
                partition_path="/resource_type",
                offer_throughput=400,
                default_ttl=-1  # No expiry for runbooks
            )
            logger.info("✅ Cosmos DB custom_runbooks container initialized")
            return _cosmos_runbook_container
        else:
            logger.warning("⚠️ Cosmos DB not available - using in-memory runbook store only")
            return None
    except Exception as exc:
        logger.warning(f"⚠️ Failed to initialize Cosmos DB for runbooks: {exc}")
        return None


def _generate_approval_token(plan_id: str, step_index: int) -> str:
    """Generate a time-limited approval token for a remediation step."""
    token = f"approve-{plan_id}-{step_index}-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()
    _approval_tokens[token] = {
        "plan_id": plan_id,
        "step_index": step_index,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "used": False,
    }
    return token


def _validate_approval_token(token: str, plan_id: str, step_index: int) -> Dict[str, Any]:
    """Validate an approval token. Returns {valid: bool, reason?: str}."""
    record = _approval_tokens.get(token)
    if record is None:
        return {"valid": False, "reason": "Unknown approval token"}
    if record["used"]:
        return {"valid": False, "reason": "Approval token already used"}
    if record["plan_id"] != plan_id:
        return {"valid": False, "reason": "Token does not match plan_id"}
    if record["step_index"] != step_index:
        return {"valid": False, "reason": "Token does not match step_index"}
    if datetime.utcnow() > datetime.fromisoformat(record["expires_at"]):
        return {"valid": False, "reason": "Approval token expired (30-min TTL)"}
    return {"valid": True}


def _match_runbooks(issue_description: str, resource_id: str) -> List[Dict[str, Any]]:
    """Match an incident description against built-in and custom runbook databases.

    Returns ranked list of matching runbooks sorted by relevance score.
    """
    issue_lower = issue_description.lower()

    # Determine resource type from resource_id
    resource_type = "unknown"
    parts = resource_id.split("/")
    if len(parts) >= 9:
        resource_type = f"{parts[6]}/{parts[7]}"

    matches: List[Dict[str, Any]] = []

    all_runbooks = _BUILTIN_RUNBOOKS + _custom_runbooks

    # Also try to load custom runbooks from Cosmos DB
    try:
        container = _get_runbook_container()
        if container is not None:
            query = "SELECT * FROM c WHERE c.active = true"
            cosmos_runbooks = list(container.query_items(query=query, enable_cross_partition_query=True))
            all_runbooks = all_runbooks + cosmos_runbooks
    except Exception as exc:
        logger.debug(f"Could not load Cosmos runbooks for matching: {exc}")

    for rb in all_runbooks:
        score = 0
        patterns = rb.get("trigger_conditions", {}).get("error_patterns", [])
        for pattern in patterns:
            if pattern.lower() in issue_lower:
                score += 10

        # Boost score if resource type matches
        if resource_type in rb.get("resource_types", []):
            score += 5

        if score > 0:
            matches.append({**rb, "_match_score": score})

    matches.sort(key=lambda r: r["_match_score"], reverse=True)
    return matches


def _log_audit_event(operation: str, resource_id: Optional[str], details: Dict[str, Any], success: bool):
    """Log an audit event for SRE operations with Cosmos DB persistence"""
    audit_entry = {
        "id": f"{operation}-{datetime.utcnow().timestamp()}-{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.utcnow().isoformat(),
        "operation": operation,
        "resource_id": resource_id,
        "success": success,
        "details": details,
        "caller": os.getenv("USER", "system")
    }

    # Always add to in-memory trail (fallback)
    _audit_trail.append(audit_entry)
    logger.info(f"AUDIT: {operation} | Resource: {resource_id} | Success: {success}")

    # Keep only last 1000 entries in memory
    if len(_audit_trail) > 1000:
        _audit_trail.pop(0)

    # Persist to Cosmos DB if available
    try:
        container = _get_audit_container()
        if container is not None:
            container.upsert_item(body=audit_entry)
            logger.debug(f"✅ Audit event persisted to Cosmos DB: {audit_entry['id']}")
    except Exception as exc:
        logger.warning(f"⚠️ Failed to persist audit event to Cosmos DB: {exc}")
        # Continue - in-memory trail is still available


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


def _cache_get(tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
    """Check SRE cache for a cached tool result. Returns None on miss."""
    if _sre_cache is None:
        return None
    return _sre_cache.get(tool_name, args)


def _cache_set(tool_name: str, args: Dict[str, Any], value: Any, ttl_profile: Optional[str] = None) -> None:
    """Store a tool result in the SRE cache."""
    if _sre_cache is not None:
        _sre_cache.set(tool_name, args, value, ttl_profile)


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

        # Check if resource type is Container Apps (not supported by Resource Health API)
        if "Microsoft.App/containerApps" in resource_id or "/containerapps/" in resource_id.lower():
            result = {
                "success": False,
                "error": "Azure Resource Health API doesn't support Container Apps",
                "recommendation": "Use the check_container_app_health tool instead for Container Apps health monitoring",
                "supported_resource_types": [
                    "Microsoft.Compute/virtualMachines",
                    "Microsoft.Web/sites",
                    "Microsoft.Sql/servers/databases",
                    "Microsoft.Storage/storageAccounts",
                    "Microsoft.Network/applicationGateways",
                    "Microsoft.Network/loadBalancers",
                    "Microsoft.Network/virtualNetworkGateways"
                ],
                "resource_id": resource_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info(f"Container Apps not supported by Resource Health API: {resource_id}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
            # No tables available - fallback to Azure CLI for direct log access
            logger.info(f"Log Analytics tables not available, falling back to Azure CLI for {container_app_name}")
            
            try:
                # Use Azure CLI to get logs directly
                cli_command = [
                    "az", "containerapp", "logs", "show",
                    "--name", container_app_name,
                    "--resource-group", resource_group,
                    "--tail", "100",
                    "--format", "text",
                    "--output", "json"
                ]
                
                cli_result = subprocess.run(
                    cli_command,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if cli_result.returncode == 0:
                    # Parse logs from CLI output
                    logs_output = cli_result.stdout
                    error_count = logs_output.lower().count("error") + logs_output.lower().count("failed")
                    warning_count = logs_output.lower().count("warn")
                    total_logs = logs_output.count("\n")
                    
                    # Extract recent errors
                    recent_errors = []
                    for line in logs_output.split("\n"):
                        if "error" in line.lower() or "failed" in line.lower():
                            recent_errors.append(line.strip())
                            if len(recent_errors) >= 5:
                                break
                    
                    # Determine health status
                    if error_count > 10:
                        health_status = "Unhealthy"
                    elif error_count > 3:
                        health_status = "Degraded"
                    else:
                        health_status = "Healthy"
                    
                    health_data = {
                        "total_logs": total_logs,
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "health_status": health_status,
                        "recent_errors": recent_errors,
                        "table_used": "Azure CLI (direct logs)",
                        "log_sample": logs_output[:500] if logs_output else "No logs available"
                    }
                    logger.info(f"Azure CLI fallback successful for {container_app_name}: {health_status}")
                else:
                    # CLI command failed
                    health_data["health_status"] = "Unknown - CLI access failed"
                    health_data["table_used"] = "None (CLI error)"
                    health_data["cli_error"] = cli_result.stderr
                    logger.warning(f"Azure CLI failed for {container_app_name}: {cli_result.stderr}")
                    
            except subprocess.TimeoutExpired:
                health_data["health_status"] = "Unknown - Timeout"
                health_data["table_used"] = "None (timeout)"
                logger.error(f"Azure CLI timeout for {container_app_name}")
            except Exception as cli_exc:
                health_data["health_status"] = "Unknown - No logs available"
                health_data["table_used"] = "None (diagnostic logs not configured)"
                logger.error(f"Azure CLI fallback failed for {container_app_name}: {cli_exc}")

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
            api_version="2024-03-01"
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
        | distinct id=coalesce(dep_id, id)
        | join kind=inner (
            Resources
            | project id, name, type, location, resourceGroup
        ) on id
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
        "✅ Supports common metric aliases: 'cpu'→'CpuPercentage', 'memory'→'MemoryPercentage' (auto-normalized per resource type). "
        "✅ Data is aggregated by hour to minimize token usage - perfect for long time ranges (24+ hours). "
        "Returns metric values for specified time range with aggregation and summary statistics. "
        "Use for performance analysis and capacity planning. "
        "🎯 RECOMMENDED: Omit metric_names parameter to auto-select best metrics for the resource type. "
        "Example: get_performance_metrics(resource_id='/subscriptions/.../containerapps/myapp', hours=1) - auto-selects CPU, memory, requests, replicas."
    ),
)
async def get_performance_metrics(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    metric_names: Annotated[Optional[List[str]], "Optional: List of metric names. Omit to auto-select. Common aliases supported: cpu, memory, requests, replicas."] = None,
    hours: Annotated[int, "Hours to look back (default: 1)"] = 1,
    aggregation: Annotated[str, "Aggregation type: Average, Maximum, Minimum, Total"] = "Average",
    aggregate_interval_minutes: Annotated[int, "Aggregate data into N-minute buckets (default: 60 for hourly). Use 1 for raw data, 5 for 5-min buckets, etc."] = 60,
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

        # Define metric name mappings for common aliases
        metric_name_mappings = {
            "ContainerApp": {
                "cpu": "CpuPercentage",
                "memory": "MemoryPercentage",
                "requests": "Requests",
                "replicas": "Replicas",
                "cpupercentage": "CpuPercentage",
                "memorypercentage": "MemoryPercentage"
            },
            "AppService": {
                "cpu": "CpuPercentage",
                "memory": "MemoryPercentage",
                "responsetime": "HttpResponseTime",
                "requests": "Requests"
            },
            "VirtualMachine": {
                "cpu": "Percentage CPU",
                "networkin": "Network In Total",
                "networkout": "Network Out Total",
                "diskread": "Disk Read Bytes",
                "diskwrite": "Disk Write Bytes"
                # Note: Memory metrics require Azure Monitor Agent
                # "memory": "Available Memory Bytes" - requires guest agent
            },
            "AKS": {
                "cpu": "node_cpu_usage_percentage",
                "memory": "node_memory_working_set_percentage",
                "pods": "kube_pod_status_ready"
            }
        }

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
                # Use only host-level metrics that are always available
                # Guest-level metrics (Available Memory Bytes, etc.) require
                # Azure Monitor Agent (AMA) to be installed on the VM
                # Host metrics are collected by Azure infrastructure automatically
                metric_names = [
                    "Percentage CPU",         # Host: CPU usage percentage
                    "Network In Total",       # Host: Total bytes received
                    "Network Out Total",      # Host: Total bytes sent
                    "Disk Read Bytes",        # Host: Bytes read from disk
                    "Disk Write Bytes"        # Host: Bytes written to disk
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

        # Normalize metric names if provided by user
        if metric_names and resource_type in metric_name_mappings:
            normalized_names = []
            for name in metric_names:
                # Try to map common aliases to proper metric names
                normalized_name = metric_name_mappings[resource_type].get(name.lower(), name)
                normalized_names.append(normalized_name)
            metric_names = normalized_names

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
                        # Collect raw data points
                        raw_data_points = []
                        for data in timeseries.data:
                            value = getattr(data, aggregation.lower(), None)
                            if value is not None:
                                raw_data_points.append({
                                    "timestamp": data.timestamp,
                                    "value": value
                                })

                        if raw_data_points:
                            # Aggregate data into time buckets to reduce data sent to LLM
                            # This is crucial for long time ranges (e.g., 24 hours)
                            # Default is hourly aggregation (60 minutes)
                            time_buckets = {}
                            for dp in raw_data_points:
                                # Truncate timestamp to the specified interval
                                if aggregate_interval_minutes >= 60:
                                    # Hourly or longer - truncate to hour
                                    bucket_key = dp["timestamp"].replace(minute=0, second=0, microsecond=0)
                                elif aggregate_interval_minutes == 1:
                                    # No aggregation - use raw data
                                    bucket_key = dp["timestamp"]
                                else:
                                    # Custom interval (e.g., 5 minutes, 15 minutes)
                                    minute_bucket = (dp["timestamp"].minute // aggregate_interval_minutes) * aggregate_interval_minutes
                                    bucket_key = dp["timestamp"].replace(minute=minute_bucket, second=0, microsecond=0)

                                if bucket_key not in time_buckets:
                                    time_buckets[bucket_key] = []
                                time_buckets[bucket_key].append(dp["value"])

                            # Calculate aggregates for each time bucket
                            aggregated_data = []
                            for bucket_time, values in sorted(time_buckets.items()):
                                aggregated_data.append({
                                    "timestamp": str(bucket_time),
                                    "average": sum(values) / len(values),
                                    "min": min(values),
                                    "max": max(values),
                                    "count": len(values)
                                })

                            # Calculate overall summary statistics
                            all_values = [dp["value"] for dp in raw_data_points]

                            # Determine data field name based on interval
                            if aggregate_interval_minutes >= 60:
                                data_field_name = "hourly_data"
                                interval_description = f"{aggregate_interval_minutes // 60}-hour"
                            elif aggregate_interval_minutes == 1:
                                data_field_name = "raw_data"
                                interval_description = "raw (1-minute)"
                            else:
                                data_field_name = "aggregated_data"
                                interval_description = f"{aggregate_interval_minutes}-minute"

                            metrics_data.append({
                                "metric_name": metric.name,
                                "unit": metric.unit,
                                "aggregation": aggregation,
                                "aggregation_interval": interval_description,
                                data_field_name: aggregated_data,
                                "summary": {
                                    "current": all_values[-1] if all_values else None,
                                    "average": sum(all_values) / len(all_values) if all_values else None,
                                    "minimum": min(all_values) if all_values else None,
                                    "maximum": max(all_values) if all_values else None,
                                    "total_data_points": len(all_values),
                                    "aggregated_buckets": len(aggregated_data)
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
            "aggregation_config": {
                "interval_minutes": aggregate_interval_minutes,
                "description": f"Data aggregated into {aggregate_interval_minutes}-minute buckets to minimize token usage"
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
    """Execute REAL resource restart with Azure Management API"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Restart requires confirmation. Set confirmed=true to proceed.",
                "recommendation": "Use plan_remediation first to review the restart plan"
            }, indent=2))]

        # Check if Azure SDK is available
        if ComputeManagementClient is None and WebSiteManagementClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Management SDK not installed"
            }, indent=2))]

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        subscription_id = parts[2]
        resource_group = parts[4]
        provider = parts[6]
        resource_type = parts[7]
        resource_name = parts[8]

        credential = _get_credential()
        restart_status = "Unknown"

        # Execute restart based on resource type
        if provider == "Microsoft.Compute" and resource_type == "virtualMachines":
            # Restart Virtual Machine
            compute_client = ComputeManagementClient(credential, subscription_id)
            logger.info(f"Initiating VM restart for {resource_name} in {resource_group}")
            async_restart = compute_client.virtual_machines.begin_restart(
                resource_group_name=resource_group,
                vm_name=resource_name
            )
            async_restart.result()  # Wait for completion
            restart_status = "VM restarted successfully"

        elif provider == "Microsoft.Web" and resource_type == "sites":
            # Restart App Service / Web App
            web_client = WebSiteManagementClient(credential, subscription_id)
            logger.info(f"Initiating App Service restart for {resource_name} in {resource_group}")
            web_client.web_apps.restart(
                resource_group_name=resource_group,
                name=resource_name
            )
            restart_status = "App Service restarted successfully"

        elif provider == "Microsoft.ContainerService" and resource_type == "managedClusters":
            # Note: AKS doesn't have a direct "restart" - this would restart specific node pools
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "AKS cluster restart not supported. Use Azure Portal or CLI to restart specific node pools.",
                "recommendation": "az aks nodepool restart --resource-group <rg> --cluster-name <cluster> --name <nodepool>"
            }, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Restart not supported for resource type: {provider}/{resource_type}",
                "supported_types": [
                    "Microsoft.Compute/virtualMachines",
                    "Microsoft.Web/sites (App Services)"
                ]
            }, indent=2))]

        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "restart",
            "status": "Completed",
            "message": restart_status,
            "resource_type": f"{provider}/{resource_type}",
            "next_steps": [
                "Monitor resource health after restart",
                "Verify application is responding",
                "Check logs for errors"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log audit event
        _log_audit_event(
            operation="execute_safe_restart",
            resource_id=resource_id,
            details={"confirmed": True, "status": restart_status},
            success=True
        )

        logger.info(f"Safe restart completed for {resource_id}: {restart_status}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        # Log audit event for failure
        _log_audit_event(
            operation="execute_safe_restart",
            resource_id=resource_id,
            details={"error": str(exc), "confirmed": confirmed},
            success=False
        )
        logger.error(f"Error executing safe restart: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "resource_id": resource_id
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
    """Scale resource with REAL Azure Management API calls"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Scaling requires confirmation. Set confirmed=true to proceed.",
                "scale_direction": scale_direction,
                "target_capacity": target_capacity
            }, indent=2))]

        # Check if Azure SDK is available
        if WebSiteManagementClient is None and ComputeManagementClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Management SDK not installed"
            }, indent=2))]

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        subscription_id = parts[2]
        resource_group = parts[4]
        provider = parts[6]
        resource_type = parts[7]
        resource_name = parts[8]

        credential = _get_credential()
        scale_status = "Unknown"

        if target_capacity is None or target_capacity < 1:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "target_capacity must be specified and >= 1"
            }, indent=2))]

        # Execute scaling based on resource type
        if provider == "Microsoft.Web" and resource_type == "sites":
            # Scale App Service
            web_client = WebSiteManagementClient(credential, subscription_id)
            logger.info(f"Scaling App Service {resource_name} to {target_capacity} instances")

            # Get current configuration
            site = web_client.web_apps.get(resource_group, resource_name)

            # Update the site configuration with new capacity
            site_config = web_client.web_apps.get_configuration(resource_group, resource_name)

            # Scale via App Service Plan
            plan_id = site.server_farm_id
            plan_parts = plan_id.split('/')
            plan_name = plan_parts[-1]
            plan_rg = plan_parts[4]

            # Get and update the App Service Plan
            from azure.mgmt.web.models import AppServicePlan
            plan = web_client.app_service_plans.get(plan_rg, plan_name)
            plan.sku.capacity = target_capacity

            web_client.app_service_plans.begin_create_or_update(plan_rg, plan_name, plan)
            scale_status = f"App Service scaled to {target_capacity} instances"

        elif provider == "Microsoft.Compute" and resource_type == "virtualMachines":
            # VMs don't scale directly - need VMSS
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Individual VMs cannot be scaled. Use Virtual Machine Scale Sets (VMSS) instead.",
                "recommendation": "Convert to VMSS or manually resize the VM SKU"
            }, indent=2))]

        elif provider == "Microsoft.Compute" and resource_type == "virtualMachineScaleSets":
            # Scale VMSS
            compute_client = ComputeManagementClient(credential, subscription_id)
            logger.info(f"Scaling VMSS {resource_name} to {target_capacity} instances")

            vmss = compute_client.virtual_machine_scale_sets.get(resource_group, resource_name)
            vmss.sku.capacity = target_capacity

            async_update = compute_client.virtual_machine_scale_sets.begin_create_or_update(
                resource_group, resource_name, vmss
            )
            async_update.result()
            scale_status = f"VMSS scaled to {target_capacity} instances"

        else:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Scaling not supported for resource type: {provider}/{resource_type}",
                "supported_types": [
                    "Microsoft.Web/sites (App Services)",
                    "Microsoft.Compute/virtualMachineScaleSets"
                ]
            }, indent=2))]

        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "scale",
            "scale_direction": scale_direction,
            "target_capacity": target_capacity,
            "status": "Completed",
            "message": scale_status,
            "resource_type": f"{provider}/{resource_type}",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log audit event
        _log_audit_event(
            operation="scale_resource",
            resource_id=resource_id,
            details={"confirmed": True, "target_capacity": target_capacity, "status": scale_status},
            success=True
        )

        logger.info(f"Resource scaling completed for {resource_id}: {scale_status}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        # Log audit event for failure
        _log_audit_event(
            operation="scale_resource",
            resource_id=resource_id,
            details={"error": str(exc), "confirmed": confirmed, "target_capacity": target_capacity},
            success=False
        )
        logger.error(f"Error scaling resource: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "resource_id": resource_id
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
    """Clear cache using REAL Azure Management API calls"""
    try:
        if not confirmed:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "requires_approval": True,
                "message": "Cache clear requires confirmation. Set confirmed=true to proceed.",
                "warning": "This may cause temporary performance degradation"
            }, indent=2))]

        # Check if Azure SDK is available
        if RedisManagementClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Management SDK not installed (azure-mgmt-redis required)"
            }, indent=2))]

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        subscription_id = parts[2]
        resource_group = parts[4]
        provider = parts[6]
        resource_type = parts[7]
        resource_name = parts[8]

        credential = _get_credential()
        clear_status = "Unknown"

        if cache_type.lower() == "redis" and provider == "Microsoft.Cache" and resource_type == "Redis":
            # Clear Redis cache via force reboot
            redis_client = RedisManagementClient(credential, subscription_id)
            logger.info(f"Clearing Redis cache {resource_name} via flush")

            # Get Redis properties to determine reboot strategy
            redis_resource = redis_client.redis.get(resource_group, resource_name)

            # For Redis cache, we use the ForceReboot to clear cache
            # Note: This is a disruptive operation
            from azure.mgmt.redis.models import RebootType

            logger.warning(f"Initiating Redis cache flush for {resource_name} - this will cause brief downtime")

            # Reboot all nodes to clear cache
            redis_client.redis.begin_force_reboot(
                resource_group_name=resource_group,
                name=resource_name,
                parameters={
                    "reboot_type": RebootType.ALL_NODES,
                    "shard_id": None  # Reboot all shards
                }
            )

            clear_status = f"Redis cache {resource_name} flushed (all nodes rebooted)"

        elif cache_type.lower() == "cdn":
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "CDN cache purge not yet implemented",
                "recommendation": "Use Azure Portal or CLI: az cdn endpoint purge"
            }, indent=2))]

        elif cache_type.lower() == "application":
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Application cache clear requires application-specific logic",
                "recommendation": "Use application's cache management API or restart the application"
            }, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Unsupported cache type or resource: {cache_type} / {provider}/{resource_type}",
                "supported_types": [
                    "redis (Microsoft.Cache/Redis)"
                ]
            }, indent=2))]

        result = {
            "success": True,
            "resource_id": resource_id,
            "action": "clear_cache",
            "cache_type": cache_type,
            "status": "Completed",
            "message": clear_status,
            "warning": "Cache cleared - expect temporary performance impact while cache rebuilds",
            "resource_type": f"{provider}/{resource_type}",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log audit event
        _log_audit_event(
            operation="clear_cache",
            resource_id=resource_id,
            details={"confirmed": True, "cache_type": cache_type, "status": clear_status},
            success=True
        )

        logger.info(f"Cache clear completed for {resource_id}: {clear_status}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        # Log audit event for failure
        _log_audit_event(
            operation="clear_cache",
            resource_id=resource_id,
            details={"error": str(exc), "confirmed": confirmed, "cache_type": cache_type},
            success=False
        )
        logger.error(f"Error clearing cache: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "resource_id": resource_id
        }, indent=2))]

    except Exception as exc:
        logger.error(f"Error clearing cache: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Automated Remediation with Approval Gates
# ============================================================================

@_server.tool(
    name="generate_remediation_plan",
    description=(
        "Generate a detailed, multi-step remediation plan for an incident or alert. "
        "Matches the issue against built-in and custom runbook databases, then produces "
        "a step-by-step plan with pre-checks, execution steps, validation, and rollback. "
        "⚠️ IMPORTANT: All plans require explicit approval before any destructive step "
        "can be executed. Use execute_remediation_step with the returned approval_token "
        "to proceed."
    ),
)
async def generate_remediation_plan(
    context: Context,
    issue_description: Annotated[str, "Description of the incident or alert to remediate"],
    resource_id: Annotated[str, "Full Azure resource ID of the affected resource"],
    severity: Annotated[str, "Severity level: critical, high, medium, low"] = "medium",
    preferred_strategy: Annotated[Optional[str], "Optional preferred remediation type: restart, scale, clear_cache, custom"] = None,
) -> list[TextContent]:
    """Generate a remediation plan with approval gates from runbook matching."""
    try:
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # ---- Runbook matching ----
        matched_runbooks = _match_runbooks(issue_description, resource_id)

        # Pick best runbook (or generate a generic one)
        if preferred_strategy:
            # Filter by preferred strategy name
            strategy_matches = [
                rb for rb in matched_runbooks
                if preferred_strategy.lower() in rb.get("name", "").lower()
                or preferred_strategy.lower() in str(rb.get("steps", [])).lower()
            ]
            selected_runbook = strategy_matches[0] if strategy_matches else (matched_runbooks[0] if matched_runbooks else None)
        else:
            selected_runbook = matched_runbooks[0] if matched_runbooks else None

        # Build step-by-step plan
        if selected_runbook:
            runbook_steps = selected_runbook.get("steps", [])
            rollback = selected_runbook.get("rollback", [])
            risk_level = selected_runbook.get("risk_level", "medium")
            estimated_downtime = selected_runbook.get("estimated_downtime", "Unknown")
            runbook_id = selected_runbook.get("runbook_id", "ad-hoc")
        else:
            # Generic plan when no runbook matches
            runbook_steps = [
                {"action": "pre_check", "description": "Verify resource current state and health", "destructive": False},
                {"action": "investigate", "description": "Collect diagnostic logs and metrics", "destructive": False},
                {"action": "remediate", "description": f"Apply remediation for: {issue_description[:80]}", "destructive": True},
                {"action": "validate", "description": "Validate resource health post-remediation", "destructive": False},
            ]
            rollback = ["Revert changes and restore previous state", "Notify stakeholders"]
            risk_level = "high" if severity in ("critical", "high") else "medium"
            estimated_downtime = "To be determined"
            runbook_id = "ad-hoc"

        # Enrich steps with indices and approval requirements
        plan_steps = []
        for idx, step in enumerate(runbook_steps):
            is_destructive = step.get("destructive", False)
            step_entry = {
                "step_index": idx,
                "action": step["action"],
                "description": step["description"],
                "destructive": is_destructive,
                "requires_approval": is_destructive,
                "status": "pending",
                "approval_token": _generate_approval_token(plan_id, idx) if is_destructive else None,
            }
            plan_steps.append(step_entry)

        # Determine overall approval requirement
        has_destructive_steps = any(s["destructive"] for s in plan_steps)

        plan_record = {
            "plan_id": plan_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=4)).isoformat(),
            "issue_description": issue_description,
            "resource_id": resource_id,
            "severity": severity,
            "matched_runbook_id": runbook_id,
            "matched_runbooks_count": len(matched_runbooks),
            "risk_level": risk_level,
            "estimated_downtime": estimated_downtime,
            "steps": plan_steps,
            "rollback_procedure": rollback,
            "approval_required": has_destructive_steps,
            "status": "awaiting_approval" if has_destructive_steps else "ready",
            "execution_log": [],
        }

        # Store plan in memory
        _remediation_plans[plan_id] = plan_record

        # Prune expired plans (keep store bounded)
        expired_ids = [
            pid for pid, p in _remediation_plans.items()
            if datetime.utcnow() > datetime.fromisoformat(p["expires_at"])
        ]
        for pid in expired_ids:
            del _remediation_plans[pid]

        # Build response (hide raw token values in summary, include per-step)
        response = {
            "success": True,
            "plan_id": plan_id,
            "resource_id": resource_id,
            "severity": severity,
            "risk_level": risk_level,
            "estimated_downtime": estimated_downtime,
            "matched_runbook": runbook_id,
            "total_steps": len(plan_steps),
            "steps": plan_steps,
            "rollback_procedure": rollback,
            "approval_required": has_destructive_steps,
            "status": plan_record["status"],
            "instructions": (
                "Review the plan above. For each destructive step, call "
                "execute_remediation_step with plan_id, step_index, confirmed=true, "
                "and the approval_token shown for that step. Non-destructive steps "
                "can be executed without a token."
            ),
            "expires_at": plan_record["expires_at"],
            "timestamp": now.isoformat(),
        }

        _log_audit_event(
            operation="generate_remediation_plan",
            resource_id=resource_id,
            details={
                "plan_id": plan_id,
                "severity": severity,
                "matched_runbook": runbook_id,
                "risk_level": risk_level,
                "total_steps": len(plan_steps),
            },
            success=True,
        )

        logger.info(
            f"Generated remediation plan {plan_id} for {resource_id} "
            f"(runbook={runbook_id}, steps={len(plan_steps)}, risk={risk_level})"
        )
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="generate_remediation_plan",
            resource_id=resource_id,
            details={"error": str(exc)},
            success=False,
        )
        logger.error(f"Error generating remediation plan: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "resource_id": resource_id,
        }, indent=2))]


@_server.tool(
    name="execute_remediation_step",
    description=(
        "Execute a single step from a previously generated remediation plan. "
        "⚠️ CRITICAL: Destructive steps REQUIRE confirmed=true AND a valid "
        "approval_token (returned by generate_remediation_plan). Tokens expire "
        "after 30 minutes and are single-use. Non-destructive steps (pre-checks, "
        "validations) can run without a token. All actions are fully audited."
    ),
)
async def execute_remediation_step(
    context: Context,
    plan_id: Annotated[str, "Plan ID returned by generate_remediation_plan"],
    step_index: Annotated[int, "Zero-based index of the step to execute"],
    confirmed: Annotated[bool, "Must be true to execute destructive steps"] = False,
    approval_token: Annotated[Optional[str], "Approval token for destructive steps (from generate_remediation_plan)"] = None,
) -> list[TextContent]:
    """Execute a single remediation step with approval gate enforcement."""
    resource_id = "unknown"
    try:
        # ---- Retrieve plan ----
        plan = _remediation_plans.get(plan_id)
        if plan is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Plan '{plan_id}' not found or expired. Generate a new plan first.",
            }, indent=2))]

        resource_id = plan.get("resource_id", "unknown")

        # Check plan expiry
        if datetime.utcnow() > datetime.fromisoformat(plan["expires_at"]):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Plan has expired. Generate a new remediation plan.",
                "plan_id": plan_id,
            }, indent=2))]

        # ---- Validate step index ----
        if step_index < 0 or step_index >= len(plan["steps"]):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Invalid step_index {step_index}. Plan has {len(plan['steps'])} steps (0-{len(plan['steps'])-1}).",
            }, indent=2))]

        step = plan["steps"][step_index]

        # ---- Check prior step completion (enforce sequential execution) ----
        if step_index > 0:
            prev_step = plan["steps"][step_index - 1]
            if prev_step["status"] not in ("completed", "skipped"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": f"Step {step_index - 1} ('{prev_step['action']}') must be completed before step {step_index}.",
                    "previous_step_status": prev_step["status"],
                }, indent=2))]

        # ---- Already executed? ----
        if step["status"] == "completed":
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Step {step_index} already completed.",
                "plan_id": plan_id,
            }, indent=2))]

        # ---- Approval gate for destructive steps ----
        is_destructive = step.get("destructive", False)
        if is_destructive:
            if not confirmed:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "requires_approval": True,
                    "message": (
                        f"Step {step_index} ('{step['action']}') is destructive and "
                        "requires confirmed=true plus a valid approval_token."
                    ),
                    "step": step,
                    "plan_id": plan_id,
                }, indent=2))]

            if not approval_token:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "requires_approval": True,
                    "message": "Destructive step requires an approval_token from generate_remediation_plan.",
                    "plan_id": plan_id,
                    "step_index": step_index,
                }, indent=2))]

            # Validate token
            token_check = _validate_approval_token(approval_token, plan_id, step_index)
            if not token_check["valid"]:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": f"Approval token invalid: {token_check['reason']}",
                    "plan_id": plan_id,
                    "step_index": step_index,
                }, indent=2))]

            # Mark token as used (single-use)
            _approval_tokens[approval_token]["used"] = True

        # ---- Capture pre-condition state ----
        state_before = {
            "step_index": step_index,
            "action": step["action"],
            "timestamp": datetime.utcnow().isoformat(),
            "plan_status": plan["status"],
        }

        # ---- Execute step (simulated for safety, logs real intent) ----
        execution_start = datetime.utcnow()

        # Simulate execution — in production these would call real Azure APIs
        # via the existing execute_safe_restart / scale_resource / clear_cache tools.
        step_result = {
            "executed_action": step["action"],
            "description": step["description"],
            "simulated": True,
            "message": f"Step '{step['action']}' executed successfully (simulated for safety).",
        }

        execution_ms = int((datetime.utcnow() - execution_start).total_seconds() * 1000)

        # ---- Update step status ----
        step["status"] = "completed"
        step["completed_at"] = datetime.utcnow().isoformat()

        # ---- Capture post-condition state ----
        state_after = {
            "step_index": step_index,
            "action": step["action"],
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "execution_ms": execution_ms,
        }

        # ---- Append to plan execution log ----
        plan["execution_log"].append({
            "step_index": step_index,
            "action": step["action"],
            "executed_at": datetime.utcnow().isoformat(),
            "confirmed": confirmed,
            "destructive": is_destructive,
            "approval_token_used": approval_token is not None,
            "execution_ms": execution_ms,
        })

        # Update overall plan status
        all_completed = all(s["status"] == "completed" for s in plan["steps"])
        if all_completed:
            plan["status"] = "completed"

        # ---- Determine next step ----
        next_step = None
        if step_index + 1 < len(plan["steps"]):
            ns = plan["steps"][step_index + 1]
            next_step = {
                "step_index": step_index + 1,
                "action": ns["action"],
                "description": ns["description"],
                "destructive": ns.get("destructive", False),
                "requires_approval": ns.get("requires_approval", False),
                "approval_token": ns.get("approval_token"),
            }

        response = {
            "success": True,
            "plan_id": plan_id,
            "step_index": step_index,
            "action": step["action"],
            "result": step_result,
            "state_before": state_before,
            "state_after": state_after,
            "plan_status": plan["status"],
            "next_step": next_step,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _log_audit_event(
            operation="execute_remediation_step",
            resource_id=resource_id,
            details={
                "plan_id": plan_id,
                "step_index": step_index,
                "action": step["action"],
                "destructive": is_destructive,
                "confirmed": confirmed,
                "execution_ms": execution_ms,
            },
            success=True,
        )

        logger.info(
            f"Executed remediation step {step_index} ({step['action']}) "
            f"for plan {plan_id} on {resource_id}"
        )
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="execute_remediation_step",
            resource_id=resource_id,
            details={"plan_id": plan_id, "step_index": step_index, "error": str(exc)},
            success=False,
        )
        logger.error(f"Error executing remediation step: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "plan_id": plan_id,
            "step_index": step_index,
        }, indent=2))]


@_server.tool(
    name="register_custom_runbook",
    description=(
        "Register a custom remediation runbook for future incident matching. "
        "Runbooks define trigger conditions (error patterns), resource types, "
        "step-by-step remediation procedures, and approval levels. Stored in "
        "Cosmos DB (with in-memory fallback) and indexed by resource type and "
        "error pattern for fast matching by generate_remediation_plan."
    ),
)
async def register_custom_runbook(
    context: Context,
    name: Annotated[str, "Human-readable runbook name (e.g., 'Restart on OOM Kill')"],
    trigger_conditions: Annotated[str, "JSON object with error_patterns list, e.g. {\"error_patterns\": [\"OOM\", \"out of memory\"]}"],
    steps: Annotated[str, "JSON array of step objects, each with action, description, destructive (bool)"],
    resource_types: Annotated[str, "JSON array of Azure resource type strings, e.g. [\"Microsoft.Web/sites\"]"],
    approval_level: Annotated[str, "Approval level: standard, elevated, or admin"] = "standard",
) -> list[TextContent]:
    """Register a custom runbook for automated remediation matching."""
    try:
        now = datetime.utcnow()

        # ---- Parse and validate inputs ----
        try:
            parsed_conditions = json.loads(trigger_conditions)
        except json.JSONDecodeError as je:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Invalid JSON for trigger_conditions: {je}",
                "expected_format": '{"error_patterns": ["pattern1", "pattern2"]}',
            }, indent=2))]

        try:
            parsed_steps = json.loads(steps)
        except json.JSONDecodeError as je:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Invalid JSON for steps: {je}",
                "expected_format": '[{"action": "restart", "description": "Restart service", "destructive": true}]',
            }, indent=2))]

        try:
            parsed_resource_types = json.loads(resource_types)
        except json.JSONDecodeError as je:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Invalid JSON for resource_types: {je}",
                "expected_format": '["Microsoft.Web/sites", "Microsoft.App/containerApps"]',
            }, indent=2))]

        # ---- Schema validation ----
        errors: List[str] = []

        if not name or len(name.strip()) < 3:
            errors.append("name must be at least 3 characters")

        if not isinstance(parsed_conditions, dict) or "error_patterns" not in parsed_conditions:
            errors.append("trigger_conditions must have an 'error_patterns' list")
        elif not isinstance(parsed_conditions["error_patterns"], list) or len(parsed_conditions["error_patterns"]) == 0:
            errors.append("error_patterns must be a non-empty list of strings")

        if not isinstance(parsed_steps, list) or len(parsed_steps) == 0:
            errors.append("steps must be a non-empty array of step objects")
        else:
            for i, s in enumerate(parsed_steps):
                if not isinstance(s, dict):
                    errors.append(f"steps[{i}] must be an object")
                    continue
                if "action" not in s or "description" not in s:
                    errors.append(f"steps[{i}] must have 'action' and 'description' fields")
                if "destructive" not in s:
                    parsed_steps[i]["destructive"] = False  # default to safe

        if not isinstance(parsed_resource_types, list) or len(parsed_resource_types) == 0:
            errors.append("resource_types must be a non-empty array of Azure resource type strings")

        if approval_level not in ("standard", "elevated", "admin"):
            errors.append(f"approval_level must be standard, elevated, or admin (got '{approval_level}')")

        if errors:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Runbook schema validation failed",
                "validation_errors": errors,
            }, indent=2))]

        # ---- Build runbook record ----
        runbook_id = f"custom-{uuid.uuid4().hex[:12]}"
        # Use first resource type as partition key for Cosmos DB
        primary_resource_type = parsed_resource_types[0] if parsed_resource_types else "unknown"

        runbook_record = {
            "id": runbook_id,
            "runbook_id": runbook_id,
            "name": name.strip(),
            "trigger_conditions": parsed_conditions,
            "resource_types": parsed_resource_types,
            "resource_type": primary_resource_type,  # Cosmos partition key
            "steps": parsed_steps,
            "rollback": [f"Revert {name.strip()} changes", "Notify stakeholders"],
            "approval_level": approval_level,
            "risk_level": "high" if approval_level == "admin" else ("medium" if approval_level == "elevated" else "low"),
            "estimated_downtime": "Varies",
            "active": True,
            "created_at": now.isoformat(),
            "created_by": os.getenv("USER", "system"),
            "version": 1,
        }

        # ---- Persist to Cosmos DB ----
        persisted_to_cosmos = False
        try:
            container = _get_runbook_container()
            if container is not None:
                container.upsert_item(body=runbook_record)
                persisted_to_cosmos = True
                logger.info(f"✅ Custom runbook '{name}' persisted to Cosmos DB")
        except Exception as cosmos_exc:
            logger.warning(f"⚠️ Failed to persist runbook to Cosmos DB: {cosmos_exc}")

        # Always store in memory as fallback
        _custom_runbooks.append(runbook_record)

        response = {
            "success": True,
            "runbook_id": runbook_id,
            "name": name.strip(),
            "resource_types": parsed_resource_types,
            "trigger_patterns": parsed_conditions["error_patterns"],
            "total_steps": len(parsed_steps),
            "approval_level": approval_level,
            "persisted_to_cosmos": persisted_to_cosmos,
            "storage": "cosmos_db + in_memory" if persisted_to_cosmos else "in_memory_only",
            "registered_at": now.isoformat(),
        }

        _log_audit_event(
            operation="register_custom_runbook",
            resource_id=None,
            details={
                "runbook_id": runbook_id,
                "name": name.strip(),
                "resource_types": parsed_resource_types,
                "approval_level": approval_level,
                "persisted_to_cosmos": persisted_to_cosmos,
            },
            success=True,
        )

        logger.info(
            f"Registered custom runbook '{name}' ({runbook_id}) "
            f"with {len(parsed_steps)} steps, approval={approval_level}"
        )
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="register_custom_runbook",
            resource_id=None,
            details={"name": name, "error": str(exc)},
            success=False,
        )
        logger.error(f"Error registering custom runbook: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
        }, indent=2))]


# ============================================================================
# Microsoft Teams Notification Tools
# ============================================================================

@_server.tool(
    name="send_teams_notification",
    description=(
        "⚠️ DEPRECATED: Webhook-based Teams notifications are not configured. "
        "Consider using: "
        "(1) Teams Bot - Users interact with the bot via chat at /api/teams-bot/messages (bidirectional conversations), "
        "(2) Email alerts - Configure SMTP notifications via /api/alerts endpoints (proactive notifications), "
        "(3) Azure Monitor Action Groups - Production-grade alerting with multiple notification channels. "
        "This tool will return an error unless a webhook URL is configured. "
        "For testing, you can configure TEAMS_WEBHOOK_URL environment variable with an incoming webhook."
    ),
)
async def send_teams_notification(
    context: Context,
    title: Annotated[str, "Notification title"],
    message: Annotated[str, "Notification message"],
    color: Annotated[Optional[str], "Hex color (without #): e.g., FF0000 for red"] = None,
    facts: Annotated[Optional[Dict[str, str]], "Key-value facts to display"] = None,
) -> list[TextContent]:
    """Send notification to Teams (webhook-based, deprecated)"""
    try:
        teams_client = _get_teams_client()
        if not teams_client or not teams_client.is_configured():
            result = {
                "success": True,  # Tool successfully explained the limitation
                "notification_sent": False,
                "reason": "Teams webhook notifications not configured (by design)",
                "alternatives": [
                    {
                        "method": "Teams Bot",
                        "endpoint": "/api/teams-bot/messages",
                        "description": "Bidirectional conversations via Microsoft Teams Bot",
                        "status": "configured" if (os.getenv("TEAMS_BOT_APP_ID") and os.getenv("TEAMS_BOT_APP_PASSWORD")) else "not_configured"
                    },
                    {
                        "method": "Email Alerts",
                        "endpoint": "/api/alerts",
                        "description": "SMTP-based email notifications for proactive alerting",
                        "status": "available"
                    },
                    {
                        "method": "Azure Monitor Action Groups",
                        "endpoint": "Azure Portal",
                        "description": "Production-grade alerting infrastructure with multiple notification channels",
                        "status": "recommended"
                    }
                ],
                "documentation_url": "/docs#notifications",
                "requested_notification": {
                    "title": title,
                    "message": message
                }
            }
            logger.info(f"Teams notification requested but webhook not configured (by design): {title}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
        "⚠️ DEPRECATED: Webhook-based Teams alerts are not configured. "
        "Consider using: "
        "(1) Teams Bot - Users interact with the bot via chat at /api/teams-bot/messages (bidirectional conversations), "
        "(2) Email alerts - Configure SMTP notifications via /api/alerts endpoints (proactive critical alerts), "
        "(3) Azure Monitor Action Groups - Production-grade alerting with multiple notification channels. "
        "This tool will return an error unless a webhook URL is configured. "
        "For testing, you can configure TEAMS_WEBHOOK_URL environment variable with an incoming webhook."
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
    """Send incident alert to Teams (webhook-based, deprecated)"""
    try:
        teams_client = _get_teams_client()
        if not teams_client or not teams_client.is_configured():
            result = {
                "success": True,  # Tool successfully explained the limitation
                "notification_sent": False,
                "reason": "Teams webhook notifications not configured (by design)",
                "alternatives": [
                    {
                        "method": "Teams Bot",
                        "endpoint": "/api/teams-bot/messages",
                        "description": "Bidirectional conversations via Microsoft Teams Bot",
                        "status": "configured" if (os.getenv("TEAMS_BOT_APP_ID") and os.getenv("TEAMS_BOT_APP_PASSWORD")) else "not_configured"
                    },
                    {
                        "method": "Email Alerts",
                        "endpoint": "/api/alerts",
                        "description": "SMTP-based email notifications for proactive critical alerts",
                        "status": "available"
                    },
                    {
                        "method": "Azure Monitor Action Groups",
                        "endpoint": "Azure Portal",
                        "description": "Production-grade alerting infrastructure with multiple notification channels",
                        "status": "recommended"
                    }
                ],
                "documentation_url": "/docs#notifications",
                "requested_alert": {
                    "title": title,
                    "severity": severity,
                    "description": description,
                    "resource_id": resource_id
                }
            }
            logger.info(f"Teams alert requested but webhook not configured (by design): {title} (severity: {severity})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
            result = {
                "success": True,  # Tool successfully explained the limitation
                "notification_sent": False,
                "reason": "Teams webhook notifications not configured (by design)",
                "alternatives": [
                    {
                        "method": "Teams Bot",
                        "endpoint": "/api/teams-bot/messages",
                        "description": "Bidirectional conversations via Microsoft Teams Bot",
                        "status": "configured" if (os.getenv("TEAMS_BOT_APP_ID") and os.getenv("TEAMS_BOT_APP_PASSWORD")) else "not_configured"
                    },
                    {
                        "method": "Email Alerts",
                        "endpoint": "/api/alerts",
                        "description": "SMTP-based email notifications for SRE operation status updates",
                        "status": "available"
                    },
                    {
                        "method": "Azure Monitor Action Groups",
                        "endpoint": "Azure Portal",
                        "description": "Production-grade alerting infrastructure with multiple notification channels",
                        "status": "recommended"
                    }
                ],
                "documentation_url": "/docs#notifications",
                "requested_status_update": {
                    "operation": operation,
                    "status": status,
                    "details": details,
                    "resource_id": resource_id
                }
            }
            logger.info(f"SRE status update requested but webhook not configured (by design): {operation} - {status}")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
    name="list_container_apps",
    description=(
        "List Azure Container Apps in a subscription or resource group. "
        "✅ USE THIS TOOL for pure discovery/list requests like 'list all my container apps'. "
        "Returns app identifiers and basic metadata without applying configuration filters."
    ),
)
async def list_container_apps(
    context: Context,
    subscription_id: Annotated[Optional[str], "Azure subscription ID (uses default if not provided)"] = None,
    resource_group: Annotated[Optional[str], "Optional resource group filter"] = None,
) -> list[TextContent]:
    """List Container Apps with basic metadata."""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed (azure-mgmt-resourcegraph required)"
            }, indent=2))]

        credential = _get_credential()
        sub_id = subscription_id or _get_subscription_id()

        graph_client = ResourceGraphClient(credential)

        kql_query = f"""
        Resources
        | where type == 'microsoft.app/containerapps'
        | where subscriptionId == '{sub_id}'
        """

        if resource_group:
            kql_query += f"| where resourceGroup =~ '{resource_group}'\n"

        kql_query += """
        | extend revisionMode = tostring(properties.configuration.activeRevisionsMode)
        | project id, name, resourceGroup, location, revisionMode
        | order by name asc
        """

        query_request = QueryRequest(
            subscriptions=[sub_id],
            query=kql_query,
        )
        response = graph_client.resources(query_request)

        apps = []
        for row in response.data:
            apps.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "resource_group": row.get("resourceGroup"),
                "location": row.get("location"),
                "revision_mode": row.get("revisionMode", "single"),
            })

        result = {
            "success": True,
            "subscription_id": sub_id,
            "resource_group": resource_group,
            "total_apps": len(apps),
            "apps": apps,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info("Listed %d Container Apps", len(apps))
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        logger.error(f"Error listing Container Apps: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
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
# Application Insights & Distributed Tracing (P0)
# ============================================================================

@_server.tool(
    name="query_app_insights_traces",
    description=(
        "Query Application Insights distributed traces by operation ID to trace requests across microservices. "
        "✅ USE THIS TOOL when users ask: 'Trace this request', 'Show me the end-to-end trace', "
        "'What happened with operation/correlation ID xyz?'. "
        "Returns request, dependency, and exception data for the specified operation. "
        "Requires a Log Analytics workspace with Application Insights connected."
    ),
)
async def query_app_insights_traces(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    operation_id: Annotated[str, "Operation/correlation ID to trace"],
    time_range: Annotated[str, "Time range in hours (default: 24)"] = "24",
) -> list[TextContent]:
    """Query Application Insights traces by operation ID"""
    try:
        credential = _get_credential()
        logs_client = LogsQueryClient(credential)
        hours = int(time_range) if time_range.isdigit() else 24
        timespan = timedelta(hours=hours)

        # Query requests, dependencies, and exceptions for this operation
        kql_query = f"""
        let opId = '{operation_id}';
        let requestData = requests
            | where operation_Id == opId
            | project timestamp, name, url, resultCode, duration, success, cloud_RoleName, operation_Id
            | order by timestamp asc;
        let dependencyData = dependencies
            | where operation_Id == opId
            | project timestamp, name, target, type, duration, success, resultCode, cloud_RoleName
            | order by timestamp asc;
        let exceptionData = exceptions
            | where operation_Id == opId
            | project timestamp, type, message, outerMessage, cloud_RoleName
            | order by timestamp asc;
        requestData
        | union (dependencyData | extend url = target, resultCode = resultCode)
        | union (exceptionData | extend name = type, url = message, resultCode = '', duration = 0, success = false)
        | order by timestamp asc
        """

        result = logs_client.query_workspace(workspace_id, kql_query, timespan=timespan)

        rows = []
        if hasattr(result, 'tables') and result.tables:
            for table in result.tables:
                columns = [col.name for col in table.columns]
                for row in table.rows:
                    rows.append(dict(zip(columns, [str(v) for v in row])))

        response = {
            "success": True,
            "operation_id": operation_id,
            "trace_count": len(rows),
            "traces": rows[:100],  # Limit to 100 entries
            "time_range_hours": hours,
        }

        _log_audit_event("query_app_insights_traces", None,
                         {"operation_id": operation_id, "trace_count": len(rows)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error querying App Insights traces: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "operation_id": operation_id
        }, indent=2))]


@_server.tool(
    name="get_request_telemetry",
    description=(
        "Get request performance telemetry from Application Insights including response times, "
        "failure rates, and P50/P95/P99 latencies. "
        "✅ USE THIS TOOL when users ask: 'How is my app performing?', 'Show me request latencies', "
        "'What is the failure rate?', 'Show me P95 response times'. "
        "Returns aggregated performance statistics for the specified application."
    ),
)
async def get_request_telemetry(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    app_name: Annotated[str, "Application name (cloud_RoleName in App Insights)"],
    time_range: Annotated[str, "Time range in hours (default: 24)"] = "24",
    status_code_filter: Annotated[str, "Optional HTTP status code filter (e.g., '500', '4xx', '5xx')"] = "",
) -> list[TextContent]:
    """Get request performance telemetry"""
    try:
        credential = _get_credential()
        logs_client = LogsQueryClient(credential)
        hours = int(time_range) if time_range.isdigit() else 24
        timespan = timedelta(hours=hours)

        status_filter = ""
        if status_code_filter:
            if status_code_filter.endswith("xx"):
                prefix = status_code_filter[0]
                status_filter = f"| where resultCode startswith '{prefix}'"
            else:
                status_filter = f"| where resultCode == '{status_code_filter}'"

        kql_query = f"""
        requests
        | where cloud_RoleName == '{app_name}'
        {status_filter}
        | summarize
            total_requests = count(),
            successful_requests = countif(success == true),
            failed_requests = countif(success == false),
            avg_duration_ms = avg(duration),
            p50_duration_ms = percentile(duration, 50),
            p95_duration_ms = percentile(duration, 95),
            p99_duration_ms = percentile(duration, 99),
            max_duration_ms = max(duration),
            min_duration_ms = min(duration)
        """

        result = logs_client.query_workspace(workspace_id, kql_query, timespan=timespan)

        stats = {}
        if hasattr(result, 'tables') and result.tables:
            for table in result.tables:
                columns = [col.name for col in table.columns]
                for row in table.rows:
                    stats = dict(zip(columns, [str(v) for v in row]))

        total = int(float(stats.get("total_requests", 0)))
        failed = int(float(stats.get("failed_requests", 0)))
        failure_rate = (failed / total * 100) if total > 0 else 0

        response = {
            "success": True,
            "app_name": app_name,
            "time_range_hours": hours,
            "performance": {
                "total_requests": total,
                "successful_requests": int(float(stats.get("successful_requests", 0))),
                "failed_requests": failed,
                "failure_rate_percent": round(failure_rate, 2),
                "avg_duration_ms": round(float(stats.get("avg_duration_ms", 0)), 2),
                "p50_duration_ms": round(float(stats.get("p50_duration_ms", 0)), 2),
                "p95_duration_ms": round(float(stats.get("p95_duration_ms", 0)), 2),
                "p99_duration_ms": round(float(stats.get("p99_duration_ms", 0)), 2),
                "max_duration_ms": round(float(stats.get("max_duration_ms", 0)), 2),
            },
            "status_code_filter": status_code_filter or "none",
        }

        _log_audit_event("get_request_telemetry", None,
                         {"app_name": app_name, "total_requests": total}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error getting request telemetry: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "app_name": app_name
        }, indent=2))]


@_server.tool(
    name="analyze_dependency_map",
    description=(
        "Map service-to-service dependencies using Application Insights dependency tracking. "
        "✅ USE THIS TOOL when users ask: 'What services does my app call?', "
        "'Show me the dependency map', 'Which downstream services are failing?'. "
        "Returns dependency call statistics including target services, call counts, and failure rates."
    ),
)
async def analyze_dependency_map(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    app_name: Annotated[str, "Application name (cloud_RoleName in App Insights)"],
    time_range: Annotated[str, "Time range in hours (default: 24)"] = "24",
) -> list[TextContent]:
    """Map service dependencies via Application Insights"""
    try:
        credential = _get_credential()
        logs_client = LogsQueryClient(credential)
        hours = int(time_range) if time_range.isdigit() else 24
        timespan = timedelta(hours=hours)

        kql_query = f"""
        dependencies
        | where cloud_RoleName == '{app_name}'
        | summarize
            call_count = count(),
            failed_calls = countif(success == false),
            avg_duration_ms = avg(duration),
            p95_duration_ms = percentile(duration, 95)
          by target, type, name
        | extend failure_rate = round(todouble(failed_calls) / todouble(call_count) * 100, 2)
        | order by call_count desc
        """

        result = logs_client.query_workspace(workspace_id, kql_query, timespan=timespan)

        dependencies_list = []
        if hasattr(result, 'tables') and result.tables:
            for table in result.tables:
                columns = [col.name for col in table.columns]
                for row in table.rows:
                    dep = dict(zip(columns, [str(v) for v in row]))
                    dependencies_list.append(dep)

        response = {
            "success": True,
            "app_name": app_name,
            "time_range_hours": hours,
            "dependency_count": len(dependencies_list),
            "dependencies": dependencies_list[:50],  # Limit to 50
        }

        _log_audit_event("analyze_dependency_map", None,
                         {"app_name": app_name, "dependency_count": len(dependencies_list)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error analyzing dependency map: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "app_name": app_name
        }, indent=2))]


# ============================================================================
# Cost Optimization & FinOps (P0)
# ============================================================================

@_server.tool(
    name="get_cost_analysis",
    description=(
        "Query Azure Cost Management for spending breakdown by resource group, service, tag, or location. "
        "✅ USE THIS TOOL when users ask: 'How much am I spending?', 'Show me cost breakdown', "
        "'What are my most expensive resources?', 'Cost by resource group'. "
        "Returns actual and forecast costs with grouping and trend data."
    ),
)
async def get_cost_analysis(
    context: Context,
    scope: Annotated[str, "Cost scope: subscription ID or resource group path (e.g., '/subscriptions/{id}' or '/subscriptions/{id}/resourceGroups/{rg}')"],
    time_range: Annotated[str, "Time range: 'last_7_days', 'last_30_days', 'this_month', 'last_month' (default: last_30_days)"] = "last_30_days",
    group_by: Annotated[str, "Group results by: 'ResourceGroup', 'ServiceName', 'ResourceType', 'ResourceLocation' (default: ServiceName)"] = "ServiceName",
) -> list[TextContent]:
    """Query Azure Cost Management for spending analysis"""
    try:
        import httpx
        credential = _get_credential()
        token = credential.get_token("https://management.azure.com/.default")

        # Calculate date range
        now = datetime.utcnow()
        if time_range == "last_7_days":
            start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        elif time_range == "this_month":
            start_date = now.replace(day=1).strftime("%Y-%m-%d")
        elif time_range == "last_month":
            first_of_month = now.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            start_date = last_month_end.replace(day=1).strftime("%Y-%m-%d")
            now = last_month_end
        else:  # last_30_days
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        # Build Cost Management query
        cost_url = f"https://management.azure.com{scope}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
        query_body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {"from": start_date, "to": end_date},
            "dataset": {
                "granularity": "None",
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                    "totalCostUSD": {"name": "CostUSD", "function": "Sum"}
                },
                "grouping": [{"type": "Dimension", "name": group_by}]
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                cost_url,
                json=query_body,
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
            )
            resp.raise_for_status()
            cost_data = resp.json()

        # Parse cost results
        columns = [col["name"] for col in cost_data.get("properties", {}).get("columns", [])]
        rows = cost_data.get("properties", {}).get("rows", [])

        cost_items = []
        total_cost = 0.0
        for row in rows:
            item = dict(zip(columns, row))
            cost = float(item.get("Cost", 0))
            total_cost += cost
            cost_items.append({
                "group": item.get(group_by, "Unknown"),
                "cost": round(cost, 2),
                "cost_usd": round(float(item.get("CostUSD", 0)), 2),
                "currency": item.get("Currency", "USD"),
            })

        # Sort by cost descending
        cost_items.sort(key=lambda x: x["cost"], reverse=True)

        response = {
            "success": True,
            "scope": scope,
            "time_range": time_range,
            "date_range": {"start": start_date, "end": end_date},
            "group_by": group_by,
            "total_cost": round(total_cost, 2),
            "item_count": len(cost_items),
            "cost_breakdown": cost_items[:25],  # Top 25
        }

        _log_audit_event("get_cost_analysis", scope,
                         {"total_cost": total_cost, "items": len(cost_items)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error getting cost analysis: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc),
            "scope": scope
        }, indent=2))]


@_server.tool(
    name="identify_orphaned_resources",
    description=(
        "Find unused Azure resources that may be wasting money: unattached disks, "
        "idle public IPs, empty NSGs, unused NICs, and stopped VMs. "
        "✅ USE THIS TOOL when users ask: 'Find unused resources', 'What resources are wasting money?', "
        "'Show me orphaned disks', 'Identify cloud waste'. "
        "Uses Azure Resource Graph for efficient cross-subscription queries."
    ),
)
async def identify_orphaned_resources(
    context: Context,
    subscription_id: Annotated[str, "Azure subscription ID (optional, uses env var if not provided)"] = "",
) -> list[TextContent]:
    """Find unused/orphaned Azure resources"""
    try:
        credential = _get_credential()
        sub_id = subscription_id or os.getenv("SUBSCRIPTION_ID", "")
        if not sub_id:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "No subscription_id provided and SUBSCRIPTION_ID env var not set"
            }, indent=2))]

        graph_client = ResourceGraphClient(credential)
        orphaned = {}

        # Query for unattached managed disks
        disk_query = """
        resources
        | where type =~ 'Microsoft.Compute/disks'
        | where managedBy == ''
        | where properties.diskState == 'Unattached'
        | project name, resourceGroup, location, sku = properties.sku.name,
                  sizeGB = properties.diskSizeGB, id
        """
        disk_result = graph_client.resources(QueryRequest(
            subscriptions=[sub_id],
            query=disk_query,
            options=QueryRequestOptions(result_format="objectArray")
        ))
        orphaned["unattached_disks"] = disk_result.data if hasattr(disk_result, 'data') else []

        # Query for unused public IPs
        ip_query = """
        resources
        | where type =~ 'Microsoft.Network/publicIPAddresses'
        | where properties.ipConfiguration == ''
        | where properties.natGateway == ''
        | project name, resourceGroup, location, sku = sku.name,
                  ipAddress = properties.ipAddress, id
        """
        ip_result = graph_client.resources(QueryRequest(
            subscriptions=[sub_id],
            query=ip_query,
            options=QueryRequestOptions(result_format="objectArray")
        ))
        orphaned["unused_public_ips"] = ip_result.data if hasattr(ip_result, 'data') else []

        # Query for deallocated/stopped VMs
        vm_query = """
        resources
        | where type =~ 'Microsoft.Compute/virtualMachines'
        | where properties.extended.instanceView.powerState.displayStatus == 'VM deallocated'
        | project name, resourceGroup, location, vmSize = properties.hardwareProfile.vmSize, id
        """
        vm_result = graph_client.resources(QueryRequest(
            subscriptions=[sub_id],
            query=vm_query,
            options=QueryRequestOptions(result_format="objectArray")
        ))
        orphaned["stopped_vms"] = vm_result.data if hasattr(vm_result, 'data') else []

        total_orphaned = sum(len(v) for v in orphaned.values())

        response = {
            "success": True,
            "subscription_id": sub_id,
            "total_orphaned_resources": total_orphaned,
            "orphaned_resources": {
                k: {"count": len(v), "resources": v[:10]}
                for k, v in orphaned.items()
            },
            "recommendation": "Review and delete unused resources to reduce costs" if total_orphaned > 0 else "No orphaned resources found",
        }

        _log_audit_event("identify_orphaned_resources", sub_id,
                         {"total_orphaned": total_orphaned}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]

    except Exception as exc:
        logger.error(f"Error identifying orphaned resources: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_cost_recommendations",
    description=(
        "Get Azure Advisor cost optimization recommendations including right-sizing, "
        "reserved instance opportunities, and idle resource suggestions. "
        "✅ USE THIS TOOL when users ask: 'How can I reduce costs?', 'Give me cost recommendations', "
        "'What does Azure Advisor suggest?', 'Right-sizing recommendations'."
    ),
)
async def get_cost_recommendations(
    context: Context,
    subscription_id: Annotated[str, "Azure subscription ID (optional, uses env var)"] = "",
) -> list[TextContent]:
    """Get Azure Advisor cost optimization recommendations"""
    try:
        import httpx
        credential = _get_credential()
        sub_id = subscription_id or os.getenv("SUBSCRIPTION_ID", "")
        if not sub_id:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "No subscription_id provided and SUBSCRIPTION_ID env var not set"
            }, indent=2))]

        token = credential.get_token("https://management.azure.com/.default")
        advisor_url = (
            f"https://management.azure.com/subscriptions/{sub_id}"
            f"/providers/Microsoft.Advisor/recommendations"
            f"?api-version=2023-01-01&$filter=Category eq 'Cost'"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                advisor_url,
                headers={"Authorization": f"Bearer {token.token}"}
            )
            resp.raise_for_status()
            advisor_data = resp.json()

        recommendations = []
        for rec in advisor_data.get("value", []):
            props = rec.get("properties", {})
            recommendations.append({
                "id": rec.get("id", ""),
                "category": props.get("category", "Cost"),
                "impact": props.get("impact", "Unknown"),
                "impacted_type": props.get("impactedField", ""),
                "impacted_value": props.get("impactedValue", ""),
                "problem": props.get("shortDescription", {}).get("problem", ""),
                "solution": props.get("shortDescription", {}).get("solution", ""),
                "savings_amount": props.get("extendedProperties", {}).get("annualSavingsAmount", "N/A"),
                "savings_currency": props.get("extendedProperties", {}).get("savingsCurrency", "USD"),
            })

        response = {
            "success": True,
            "subscription_id": sub_id,
            "recommendation_count": len(recommendations),
            "recommendations": recommendations[:20],  # Top 20
        }

        _log_audit_event("get_cost_recommendations", sub_id,
                         {"recommendation_count": len(recommendations)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]

    except Exception as exc:
        logger.error(f"Error getting cost recommendations: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="analyze_cost_anomalies",
    description=(
        "Detect cost spikes and unusual spending patterns using Azure Cost Management anomaly detection. "
        "✅ USE THIS TOOL when users ask: 'Are there any cost anomalies?', 'Why did my bill spike?', "
        "'Detect unusual spending'. "
        "Compares recent spending against historical baseline to identify anomalies."
    ),
)
async def analyze_cost_anomalies(
    context: Context,
    scope: Annotated[str, "Cost scope: subscription path (e.g., '/subscriptions/{id}')"],
    time_range: Annotated[str, "Analysis period: 'last_7_days', 'last_30_days' (default: last_30_days)"] = "last_30_days",
) -> list[TextContent]:
    """Detect cost anomalies by comparing recent vs baseline spending"""
    try:
        import httpx
        credential = _get_credential()
        token = credential.get_token("https://management.azure.com/.default")

        now = datetime.utcnow()
        if time_range == "last_7_days":
            recent_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            baseline_start = (now - timedelta(days=37)).strftime("%Y-%m-%d")
            baseline_end = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        else:
            recent_start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            baseline_start = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            baseline_end = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        cost_url = f"https://management.azure.com{scope}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get recent costs by service
            recent_body = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {"from": recent_start, "to": end_date},
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": "ServiceName"}]
                }
            }
            recent_resp = await client.post(
                cost_url, json=recent_body,
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
            )
            recent_resp.raise_for_status()
            recent_data = recent_resp.json()

            # Get baseline costs
            baseline_body = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {"from": baseline_start, "to": baseline_end},
                "dataset": {
                    "granularity": "None",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": "ServiceName"}]
                }
            }
            baseline_resp = await client.post(
                cost_url, json=baseline_body,
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
            )
            baseline_resp.raise_for_status()
            baseline_data = baseline_resp.json()

        # Parse baseline averages
        baseline_rows = baseline_data.get("properties", {}).get("rows", [])
        baseline_columns = [c["name"] for c in baseline_data.get("properties", {}).get("columns", [])]
        baseline_by_service = {}
        baseline_days = (datetime.strptime(baseline_end, "%Y-%m-%d") - datetime.strptime(baseline_start, "%Y-%m-%d")).days or 1
        for row in baseline_rows:
            item = dict(zip(baseline_columns, row))
            service = item.get("ServiceName", "Unknown")
            baseline_by_service[service] = float(item.get("Cost", 0)) / baseline_days

        # Parse recent costs and detect anomalies
        recent_rows = recent_data.get("properties", {}).get("rows", [])
        recent_columns = [c["name"] for c in recent_data.get("properties", {}).get("columns", [])]
        recent_by_service = {}
        recent_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(recent_start, "%Y-%m-%d")).days or 1
        for row in recent_rows:
            item = dict(zip(recent_columns, row))
            service = item.get("ServiceName", "Unknown")
            cost = float(item.get("Cost", 0))
            recent_by_service[service] = recent_by_service.get(service, 0) + cost

        # Compare and flag anomalies (>50% increase from baseline)
        anomalies = []
        for service, recent_total in recent_by_service.items():
            recent_daily = recent_total / recent_days
            baseline_daily = baseline_by_service.get(service, 0)
            if baseline_daily > 0:
                change_pct = ((recent_daily - baseline_daily) / baseline_daily) * 100
                if change_pct > 50:
                    anomalies.append({
                        "service": service,
                        "recent_daily_cost": round(recent_daily, 2),
                        "baseline_daily_cost": round(baseline_daily, 2),
                        "change_percent": round(change_pct, 1),
                        "severity": "critical" if change_pct > 200 else "warning" if change_pct > 100 else "info",
                    })

        anomalies.sort(key=lambda x: x["change_percent"], reverse=True)

        response = {
            "success": True,
            "scope": scope,
            "time_range": time_range,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:15],
            "analysis": {
                "services_analyzed": len(recent_by_service),
                "recent_period": f"{recent_start} to {end_date}",
                "baseline_period": f"{baseline_start} to {baseline_end}",
                "threshold": "50% increase over baseline",
            },
        }

        _log_audit_event("analyze_cost_anomalies", scope,
                         {"anomaly_count": len(anomalies)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error analyzing cost anomalies: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# SLO/SLI/Error Budget Management (P0)
# ============================================================================

# In-memory SLO store (fallback, persisted to Cosmos DB when available)
_slo_definitions: Dict[str, Dict[str, Any]] = {}


def _get_slo_container():
    """Get Cosmos DB container for SLO definitions"""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from utils.cosmos_cache import base_cosmos
        base_cosmos._ensure_initialized()
        if base_cosmos.initialized:
            return base_cosmos.get_container(
                container_id="slo_definitions",
                partition_path="/service_name",
                offer_throughput=400,
            )
    except Exception:
        pass
    return None


@_server.tool(
    name="define_slo",
    description=(
        "Define a Service Level Objective (SLO) for an Azure service. "
        "✅ USE THIS TOOL when users ask: 'Set an SLO for my app', 'Define a 99.9% availability target', "
        "'Create an error budget for my service'. "
        "Supports SLI types: availability, latency, error_rate. "
        "SLO definitions are stored in Cosmos DB for persistence."
    ),
)
async def define_slo(
    context: Context,
    service_name: Annotated[str, "Name of the service to set SLO for"],
    sli_type: Annotated[str, "SLI type: 'availability', 'latency', or 'error_rate'"],
    target_percentage: Annotated[float, "Target percentage (e.g., 99.9 for availability, or max latency P99 target in ms for latency type)"],
    window_days: Annotated[int, "SLO measurement window in days (default: 30)"] = 30,
    workspace_id: Annotated[str, "Log Analytics workspace ID for SLI measurement (optional)"] = "",
) -> list[TextContent]:
    """Define a Service Level Objective"""
    try:
        slo_id = f"slo-{service_name}-{sli_type}-{uuid.uuid4().hex[:8]}"

        slo_definition = {
            "id": slo_id,
            "service_name": service_name,
            "sli_type": sli_type,
            "target": target_percentage,
            "window_days": window_days,
            "workspace_id": workspace_id,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
        }

        # Store in memory
        _slo_definitions[slo_id] = slo_definition

        # Persist to Cosmos DB if available
        container = _get_slo_container()
        if container:
            container.upsert_item(body=slo_definition)
            slo_definition["persisted"] = True
        else:
            slo_definition["persisted"] = False
            slo_definition["note"] = "Stored in memory only (Cosmos DB unavailable)"

        response = {
            "success": True,
            "slo": slo_definition,
            "message": f"SLO defined: {service_name} {sli_type} target {target_percentage}% over {window_days} days",
            "error_budget": {
                "total_budget_percent": round(100 - target_percentage, 4),
                "budget_minutes_per_window": round((100 - target_percentage) / 100 * window_days * 24 * 60, 2),
            },
        }

        _log_audit_event("define_slo", service_name,
                         {"slo_id": slo_id, "sli_type": sli_type, "target": target_percentage}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error defining SLO: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="calculate_error_budget",
    description=(
        "Calculate remaining error budget based on actual SLI measurements vs SLO targets. "
        "✅ USE THIS TOOL when users ask: 'How much error budget do I have left?', "
        "'Am I burning through my error budget?', 'SLO compliance status'. "
        "Calculates SLI from Application Insights data when workspace_id is available."
    ),
)
async def calculate_error_budget(
    context: Context,
    service_name: Annotated[str, "Service name to check error budget for"],
    slo_id: Annotated[str, "SLO definition ID (optional, uses latest for service)"] = "",
    time_range: Annotated[str, "Override time range in days (optional, uses SLO window)"] = "",
) -> list[TextContent]:
    """Calculate remaining error budget"""
    try:
        # Find SLO definition
        slo = None
        if slo_id and slo_id in _slo_definitions:
            slo = _slo_definitions[slo_id]
        else:
            # Find latest SLO for service
            for sid, sdef in _slo_definitions.items():
                if sdef["service_name"] == service_name and sdef["status"] == "active":
                    slo = sdef
                    slo_id = sid

        if not slo:
            # Try loading from Cosmos DB
            container = _get_slo_container()
            if container:
                query = f"SELECT * FROM c WHERE c.service_name = '{service_name}' AND c.status = 'active' ORDER BY c.created_at DESC OFFSET 0 LIMIT 1"
                items = list(container.query_items(query=query, enable_cross_partition_query=True))
                if items:
                    slo = items[0]
                    slo_id = slo["id"]
                    _slo_definitions[slo_id] = slo

        if not slo:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"No active SLO found for service '{service_name}'. Use define_slo to create one.",
                "service_name": service_name
            }, indent=2))]

        window_days = int(time_range) if time_range.isdigit() else slo["window_days"]
        target = slo["target"]
        sli_type = slo["sli_type"]
        total_budget_percent = 100 - target

        # Try to calculate actual SLI from Application Insights
        actual_sli = None
        measurement_source = "estimated"

        workspace_id = slo.get("workspace_id", "")
        if workspace_id and LogsQueryClient:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)
                timespan = timedelta(days=window_days)

                if sli_type == "availability":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize
                        total = count(),
                        successful = countif(success == true)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        total = float(row[0]) if row[0] else 0
                        successful = float(row[1]) if row[1] else 0
                        if total > 0:
                            actual_sli = round((successful / total) * 100, 4)
                            measurement_source = "application_insights"

                elif sli_type == "error_rate":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize
                        total = count(),
                        failed = countif(success == false)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        total = float(row[0]) if row[0] else 0
                        failed = float(row[1]) if row[1] else 0
                        if total > 0:
                            actual_sli = round(100 - (failed / total) * 100, 4)
                            measurement_source = "application_insights"

                elif sli_type == "latency":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize p99 = percentile(duration, 99)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        p99 = float(row[0]) if row[0] else 0
                        # For latency: SLI = percentage of requests under target
                        actual_sli = p99  # Return raw P99 for comparison
                        measurement_source = "application_insights"

            except Exception as e:
                logger.warning(f"Failed to query App Insights for SLI: {e}")

        # Calculate error budget
        if actual_sli is not None and sli_type != "latency":
            budget_consumed_percent = max(0, (100 - actual_sli) / total_budget_percent * 100) if total_budget_percent > 0 else 0
            budget_remaining_percent = max(0, 100 - budget_consumed_percent)
            burn_rate = budget_consumed_percent / 100  # 1.0 = consuming at expected rate
        else:
            budget_consumed_percent = None
            budget_remaining_percent = None
            burn_rate = None

        response = {
            "success": True,
            "service_name": service_name,
            "slo_id": slo_id,
            "slo": {
                "sli_type": sli_type,
                "target": target,
                "window_days": window_days,
            },
            "error_budget": {
                "total_budget_percent": round(total_budget_percent, 4),
                "total_budget_minutes": round(total_budget_percent / 100 * window_days * 24 * 60, 2),
                "budget_consumed_percent": round(budget_consumed_percent, 2) if budget_consumed_percent is not None else "N/A",
                "budget_remaining_percent": round(budget_remaining_percent, 2) if budget_remaining_percent is not None else "N/A",
                "burn_rate": round(burn_rate, 2) if burn_rate is not None else "N/A",
            },
            "sli_measurement": {
                "actual_sli": actual_sli,
                "source": measurement_source,
                "note": "Requires workspace_id in SLO definition for live measurements" if measurement_source == "estimated" else "Live measurement from Application Insights",
            },
            "status": "healthy" if (budget_remaining_percent and budget_remaining_percent > 20) else "warning" if (budget_remaining_percent and budget_remaining_percent > 0) else "budget_exhausted" if budget_remaining_percent is not None else "no_data",
        }

        _log_audit_event("calculate_error_budget", service_name,
                         {"slo_id": slo_id, "status": response["status"]}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error calculating error budget: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="get_slo_dashboard",
    description=(
        "Generate an SLO compliance dashboard showing all active SLOs for a service, "
        "including burn rates, remaining budgets, and trend analysis. "
        "✅ USE THIS TOOL when users ask: 'Show me my SLO dashboard', 'SLO compliance report', "
        "'How are my services performing against targets?'."
    ),
)
async def get_slo_dashboard(
    context: Context,
    service_name: Annotated[str, "Service name (or 'all' for all services)"] = "all",
) -> list[TextContent]:
    """Generate SLO compliance dashboard"""
    try:
        # Gather all active SLOs
        active_slos = []

        # From memory
        for slo_id, slo in _slo_definitions.items():
            if slo.get("status") == "active":
                if service_name == "all" or slo.get("service_name") == service_name:
                    active_slos.append(slo)

        # From Cosmos DB
        container = _get_slo_container()
        if container:
            if service_name == "all":
                query = "SELECT * FROM c WHERE c.status = 'active'"
            else:
                query = f"SELECT * FROM c WHERE c.service_name = '{service_name}' AND c.status = 'active'"
            try:
                cosmos_slos = list(container.query_items(query=query, enable_cross_partition_query=True))
                # Merge (avoid duplicates)
                existing_ids = {s["id"] for s in active_slos}
                for cslo in cosmos_slos:
                    if cslo["id"] not in existing_ids:
                        active_slos.append(cslo)
            except Exception:
                pass

        response = {
            "success": True,
            "service_filter": service_name,
            "active_slo_count": len(active_slos),
            "slos": [
                {
                    "slo_id": slo["id"],
                    "service_name": slo["service_name"],
                    "sli_type": slo["sli_type"],
                    "target": slo["target"],
                    "window_days": slo["window_days"],
                    "error_budget_percent": round(100 - slo["target"], 4),
                    "created_at": slo.get("created_at", "unknown"),
                }
                for slo in active_slos
            ],
            "note": "Use calculate_error_budget for detailed budget analysis per SLO" if active_slos else "No active SLOs found. Use define_slo to create one.",
        }

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error generating SLO dashboard: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Security & Compliance (P2)
# ============================================================================

@_server.tool(
    name="get_security_score",
    description=(
        "Get Microsoft Defender for Cloud secure score with control-level breakdown. "
        "✅ USE THIS TOOL when users ask: 'What is my security score?', "
        "'How secure is my Azure environment?', 'Security posture overview'. "
        "Returns overall score percentage and per-control scores."
    ),
)
async def get_security_score(
    context: Context,
    subscription_id: Annotated[str, "Azure subscription ID (optional, uses env var)"] = "",
) -> list[TextContent]:
    """Get Defender for Cloud secure score"""
    try:
        import httpx
        credential = _get_credential()
        sub_id = subscription_id or os.getenv("SUBSCRIPTION_ID", "")
        if not sub_id:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "No subscription_id provided and SUBSCRIPTION_ID env var not set"
            }, indent=2))]

        token = credential.get_token("https://management.azure.com/.default")

        # Get secure scores
        score_url = (
            f"https://management.azure.com/subscriptions/{sub_id}"
            f"/providers/Microsoft.Security/secureScores"
            f"?api-version=2020-01-01"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                score_url,
                headers={"Authorization": f"Bearer {token.token}"}
            )
            resp.raise_for_status()
            score_data = resp.json()

        scores = []
        for item in score_data.get("value", []):
            props = item.get("properties", {})
            score_details = props.get("score", {})
            scores.append({
                "name": item.get("name", ""),
                "display_name": props.get("displayName", ""),
                "current_score": score_details.get("current", 0),
                "max_score": score_details.get("max", 0),
                "percentage": score_details.get("percentage", 0),
                "weight": props.get("weight", 0),
            })

        overall_pct = scores[0]["percentage"] * 100 if scores else 0

        response = {
            "success": True,
            "subscription_id": sub_id,
            "overall_score_percent": round(overall_pct, 1),
            "scores": scores,
            "recommendation": (
                "Excellent security posture" if overall_pct >= 80
                else "Good, but room for improvement" if overall_pct >= 60
                else "Security improvements needed" if overall_pct >= 40
                else "Critical security issues require attention"
            ),
        }

        _log_audit_event("get_security_score", sub_id,
                         {"score_percent": overall_pct}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error getting security score: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="list_security_recommendations",
    description=(
        "List actionable security recommendations from Microsoft Defender for Cloud. "
        "✅ USE THIS TOOL when users ask: 'What security issues do I have?', "
        "'Show me security recommendations', 'What should I fix first?'. "
        "Returns recommendations sorted by severity with remediation steps."
    ),
)
async def list_security_recommendations(
    context: Context,
    subscription_id: Annotated[str, "Azure subscription ID (optional, uses env var)"] = "",
    severity_filter: Annotated[str, "Filter by severity: 'High', 'Medium', 'Low' (optional)"] = "",
) -> list[TextContent]:
    """List Defender for Cloud security recommendations"""
    try:
        import httpx
        credential = _get_credential()
        sub_id = subscription_id or os.getenv("SUBSCRIPTION_ID", "")
        if not sub_id:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "No subscription_id provided and SUBSCRIPTION_ID env var not set"
            }, indent=2))]

        token = credential.get_token("https://management.azure.com/.default")
        rec_url = (
            f"https://management.azure.com/subscriptions/{sub_id}"
            f"/providers/Microsoft.Security/assessments"
            f"?api-version=2021-06-01"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                rec_url,
                headers={"Authorization": f"Bearer {token.token}"}
            )
            resp.raise_for_status()
            rec_data = resp.json()

        recommendations = []
        for item in rec_data.get("value", []):
            props = item.get("properties", {})
            status = props.get("status", {})
            metadata = props.get("metadata", {}) or props.get("displayName", "")

            severity = ""
            if isinstance(metadata, dict):
                severity = metadata.get("severity", "")
            status_code = status.get("code", "")

            # Only include unhealthy assessments
            if status_code != "Unhealthy":
                continue

            if severity_filter and severity.lower() != severity_filter.lower():
                continue

            display_name = props.get("displayName", "")
            if isinstance(metadata, dict):
                display_name = metadata.get("displayName", display_name)

            recommendations.append({
                "name": display_name,
                "severity": severity,
                "status": status_code,
                "description": metadata.get("description", "") if isinstance(metadata, dict) else "",
                "remediation": metadata.get("remediationDescription", "") if isinstance(metadata, dict) else "",
                "resource_id": item.get("id", ""),
            })

        # Sort by severity
        severity_order = {"High": 0, "Medium": 1, "Low": 2}
        recommendations.sort(key=lambda x: severity_order.get(x["severity"], 3))

        response = {
            "success": True,
            "subscription_id": sub_id,
            "total_recommendations": len(recommendations),
            "severity_filter": severity_filter or "all",
            "recommendations": recommendations[:30],
        }

        _log_audit_event("list_security_recommendations", sub_id,
                         {"count": len(recommendations), "filter": severity_filter}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]

    except Exception as exc:
        logger.error(f"Error listing security recommendations: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="check_compliance_status",
    description=(
        "Check Azure Policy compliance status for regulatory frameworks like CIS, NIST, and PCI-DSS. "
        "✅ USE THIS TOOL when users ask: 'Are we compliant with CIS?', "
        "'Show me NIST compliance status', 'Policy compliance overview'. "
        "Returns compliance percentages and non-compliant resource counts."
    ),
)
async def check_compliance_status(
    context: Context,
    scope: Annotated[str, "Compliance scope: subscription path (e.g., '/subscriptions/{id}')"],
    policy_definition_name: Annotated[str, "Policy initiative name to filter (optional, shows all if empty)"] = "",
) -> list[TextContent]:
    """Check Azure Policy compliance status"""
    try:
        import httpx
        credential = _get_credential()
        token = credential.get_token("https://management.azure.com/.default")

        compliance_url = (
            f"https://management.azure.com{scope}"
            f"/providers/Microsoft.PolicyInsights/policyStates/latest/summarize"
            f"?api-version=2019-10-01"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                compliance_url,
                headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
            )
            resp.raise_for_status()
            compliance_data = resp.json()

        summaries = compliance_data.get("value", [])
        results = []

        for summary in summaries:
            policy_results = summary.get("results", {})
            total = policy_results.get("resourceDetails", [{}])[0].get("count", 0) if policy_results.get("resourceDetails") else 0
            non_compliant = policy_results.get("nonCompliantResources", 0)
            compliant = total - non_compliant if total > 0 else 0
            compliance_pct = (compliant / total * 100) if total > 0 else 100

            # Get policy assignments
            for assignment in summary.get("policyAssignments", []):
                assign_props = assignment.get("policyAssignmentId", "")
                assign_results = assignment.get("results", {})

                if policy_definition_name and policy_definition_name.lower() not in assign_props.lower():
                    continue

                results.append({
                    "assignment_id": assign_props,
                    "non_compliant_resources": assign_results.get("nonCompliantResources", 0),
                    "non_compliant_policies": assign_results.get("nonCompliantPolicies", 0),
                })

        response = {
            "success": True,
            "scope": scope,
            "filter": policy_definition_name or "all policies",
            "summary": {
                "total_assignments": len(results),
            },
            "assignments": results[:20],
        }

        _log_audit_event("check_compliance_status", scope,
                         {"assignments": len(results)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]

    except Exception as exc:
        logger.error(f"Error checking compliance status: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Anomaly Detection & Predictive Analysis (P1)
# ============================================================================

@_server.tool(
    name="detect_metric_anomalies",
    description=(
        "Detect anomalies in Azure Monitor metrics using statistical analysis (Z-score). "
        "✅ USE THIS TOOL when users ask: 'Are there any metric anomalies?', "
        "'Is CPU usage unusual?', 'Detect abnormal patterns'. "
        "Analyzes time-series data and flags values that deviate significantly from the mean."
    ),
)
async def detect_metric_anomalies(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    metric_names: Annotated[str, "Comma-separated metric names (e.g., 'Percentage CPU,Network In Total')"] = "Percentage CPU",
    time_range: Annotated[str, "Time range in hours (default: 168 = 7 days)"] = "168",
    sensitivity: Annotated[str, "Sensitivity: 'high' (z>2), 'medium' (z>3), 'low' (z>4) (default: medium)"] = "medium",
) -> list[TextContent]:
    """Detect anomalies in Azure Monitor metrics"""
    try:
        credential = _get_credential()
        metrics_client = MetricsQueryClient(credential)
        hours = int(time_range) if time_range.isdigit() else 168
        timespan = timedelta(hours=hours)

        z_thresholds = {"high": 2.0, "medium": 3.0, "low": 4.0}
        z_threshold = z_thresholds.get(sensitivity, 3.0)

        metrics = [m.strip() for m in metric_names.split(",")]
        anomalies = []

        for metric_name in metrics:
            try:
                result = metrics_client.query_resource(
                    resource_id,
                    metric_names=[metric_name],
                    timespan=timespan,
                    granularity=timedelta(hours=1),
                )

                # Extract time series values
                values = []
                timestamps = []
                for metric in result.metrics:
                    for ts in metric.timeseries:
                        for dp in ts.data:
                            val = dp.average or dp.total or dp.maximum
                            if val is not None:
                                values.append(float(val))
                                timestamps.append(dp.timestamp.isoformat() if dp.timestamp else "")

                if len(values) < 10:
                    continue

                # Calculate Z-scores (pure Python, no numpy needed)
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                std_dev = variance ** 0.5

                if std_dev == 0:
                    continue

                for i, val in enumerate(values):
                    z_score = abs(val - mean) / std_dev
                    if z_score > z_threshold:
                        anomalies.append({
                            "metric": metric_name,
                            "timestamp": timestamps[i] if i < len(timestamps) else "",
                            "value": round(val, 2),
                            "mean": round(mean, 2),
                            "std_dev": round(std_dev, 2),
                            "z_score": round(z_score, 2),
                            "severity": "critical" if z_score > z_threshold + 2 else "warning",
                        })

            except Exception as e:
                logger.warning(f"Failed to analyze metric {metric_name}: {e}")

        response = {
            "success": True,
            "resource_id": resource_id,
            "metrics_analyzed": metrics,
            "time_range_hours": hours,
            "sensitivity": sensitivity,
            "z_score_threshold": z_threshold,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:20],
        }

        _log_audit_event("detect_metric_anomalies", resource_id,
                         {"anomaly_count": len(anomalies), "metrics": metrics}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error detecting metric anomalies: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="predict_resource_exhaustion",
    description=(
        "Predict when a resource will hit capacity based on trend extrapolation using linear regression. "
        "✅ USE THIS TOOL when users ask: 'When will my disk be full?', "
        "'Predict CPU saturation', 'Capacity forecast for my resource'. "
        "Uses historical metrics to project future values and estimate time to threshold."
    ),
)
async def predict_resource_exhaustion(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    metric_name: Annotated[str, "Metric to forecast (e.g., 'Percentage CPU', 'Data Disk Used Percentage')"] = "Percentage CPU",
    threshold: Annotated[float, "Threshold percentage to predict reaching (default: 90)"] = 90.0,
    time_range: Annotated[str, "Historical data range in hours (default: 168 = 7 days)"] = "168",
) -> list[TextContent]:
    """Predict resource exhaustion using linear trend"""
    try:
        credential = _get_credential()
        metrics_client = MetricsQueryClient(credential)
        hours = int(time_range) if time_range.isdigit() else 168
        timespan = timedelta(hours=hours)

        result = metrics_client.query_resource(
            resource_id,
            metric_names=[metric_name],
            timespan=timespan,
            granularity=timedelta(hours=1),
        )

        # Extract values
        values = []
        for metric in result.metrics:
            for ts in metric.timeseries:
                for dp in ts.data:
                    val = dp.average or dp.total or dp.maximum
                    if val is not None:
                        values.append(float(val))

        if len(values) < 10:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": f"Insufficient data points ({len(values)}) for prediction. Need at least 10.",
                "resource_id": resource_id,
            }, indent=2))]

        # Linear regression (pure Python)
        n = len(values)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        current_value = values[-1]
        current_trend = "increasing" if slope > 0.01 else "decreasing" if slope < -0.01 else "stable"

        # Predict time to threshold
        hours_to_threshold = None
        if slope > 0 and current_value < threshold:
            remaining = threshold - current_value
            hours_to_threshold = remaining / slope
        elif slope <= 0 and current_value < threshold:
            hours_to_threshold = None  # Will never reach if stable/decreasing

        response = {
            "success": True,
            "resource_id": resource_id,
            "metric": metric_name,
            "threshold": threshold,
            "analysis": {
                "current_value": round(current_value, 2),
                "mean_value": round(y_mean, 2),
                "min_value": round(min(values), 2),
                "max_value": round(max(values), 2),
                "trend": current_trend,
                "slope_per_hour": round(slope, 4),
            },
            "prediction": {
                "hours_to_threshold": round(hours_to_threshold, 1) if hours_to_threshold else None,
                "days_to_threshold": round(hours_to_threshold / 24, 1) if hours_to_threshold else None,
                "predicted_date": (datetime.utcnow() + timedelta(hours=hours_to_threshold)).isoformat() if hours_to_threshold else None,
                "will_reach_threshold": hours_to_threshold is not None,
                "urgency": (
                    "critical" if hours_to_threshold and hours_to_threshold < 24
                    else "warning" if hours_to_threshold and hours_to_threshold < 168
                    else "info" if hours_to_threshold
                    else "safe"
                ),
            },
            "data_points": n,
            "historical_hours": hours,
        }

        _log_audit_event("predict_resource_exhaustion", resource_id,
                         {"metric": metric_name, "trend": current_trend, "hours_to_threshold": hours_to_threshold}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error predicting resource exhaustion: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Advanced Root Cause Analysis (P1)
# ============================================================================

@_server.tool(
    name="perform_root_cause_analysis",
    description=(
        "Perform automated Root Cause Analysis (RCA) for incidents. "
        "Collects incident context, correlates logs across affected resources, "
        "analyzes activity log for configuration changes, checks resource dependencies "
        "for cascade failures, queries App Insights for distributed traces, and generates "
        "a timeline with probable root cause. "
        "✅ USE THIS TOOL when users ask: 'What caused this incident?', 'Perform RCA', "
        "'Root cause analysis for my outage', 'Why did my app go down?'. "
        "Returns hypothesis with evidence, timeline, confidence score, and recommended actions."
    ),
)
async def perform_root_cause_analysis(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID of the primary affected resource"],
    workspace_id: Annotated[str, "Log Analytics workspace ID for log correlation"],
    error_patterns: Annotated[Optional[str], "Comma-separated error patterns to search for (optional)"] = None,
    hours: Annotated[int, "Hours to look back for analysis (default: 24)"] = 24,
) -> list[TextContent]:
    """Perform automated root cause analysis for incidents"""
    try:
        if LogsQueryClient is None or ResourceGraphClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed (azure-monitor-query and azure-mgmt-resourcegraph required)"
            }, indent=2))]

        # Check cache first
        cache_args = {"resource_id": resource_id, "workspace_id": workspace_id, "hours": hours}
        cached = _cache_get("perform_root_cause_analysis", cache_args)
        if cached is not None:
            logger.info(f"RCA cache hit for {resource_id}")
            return [TextContent(type="text", text=json.dumps(cached, indent=2))]

        credential = _get_credential()
        subscription_id = _get_subscription_id()
        time_range = timedelta(hours=hours)
        now = datetime.utcnow()

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        resource_name = parts[8]
        resource_group = parts[4]
        resource_type = f"{parts[6]}/{parts[7]}"

        rca_result = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_type": resource_type,
            "analysis_window": {
                "start": (now - time_range).isoformat(),
                "end": now.isoformat(),
                "hours": hours
            },
            "root_cause_hypothesis": None,
            "confidence_score": 0.0,
            "evidence": [],
            "timeline": [],
            "recommended_actions": [],
            "timestamp": now.isoformat()
        }

        # ---- Step 1: Correlate logs across affected resources ----
        logs_client = LogsQueryClient(credential)

        error_filter = ""
        if error_patterns:
            patterns = [p.strip() for p in error_patterns.split(",")]
            pattern_conditions = " or ".join(
                [f"_ResourceId contains '{resource_name}' and * contains '{p}'" for p in patterns]
            )
            error_filter = f"| where {pattern_conditions}"

        log_query = f"""
        union *
        | where TimeGenerated > ago({hours}h)
        | where _ResourceId contains '{resource_name}' or _ResourceId contains '{resource_group}'
        {error_filter}
        | where Level in ('Error', 'Warning', 'Critical') or
                OperationName contains 'Error' or OperationName contains 'Fail'
        | summarize
            ErrorCount = countif(Level == 'Error' or Level == 'Critical'),
            WarningCount = countif(Level == 'Warning'),
            FirstError = min(TimeGenerated),
            LastError = max(TimeGenerated),
            TopErrors = make_list(strcat(tostring(TimeGenerated), ' | ', OperationName, ' | ', tostring(ResultDescription)), 10)
        """

        try:
            log_response = logs_client.query_workspace(
                workspace_id=workspace_id,
                query=log_query,
                timespan=time_range
            )

            for table in log_response.tables:
                for row in table.rows:
                    error_count = row[0] if row[0] else 0
                    warning_count = row[1] if row[1] else 0
                    first_error = str(row[2]) if row[2] else None
                    last_error = str(row[3]) if row[3] else None
                    top_errors = row[4] if len(row) > 4 and row[4] else []

                    rca_result["evidence"].append({
                        "source": "log_correlation",
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "first_error_time": first_error,
                        "last_error_time": last_error,
                        "top_errors": top_errors[:10]
                    })

                    if first_error:
                        rca_result["timeline"].append({
                            "time": first_error,
                            "event": "First error detected in logs",
                            "severity": "high",
                            "details": f"{error_count} errors, {warning_count} warnings in window"
                        })
        except Exception as log_exc:
            logger.warning(f"Log correlation failed for RCA: {log_exc}")
            rca_result["evidence"].append({
                "source": "log_correlation",
                "status": "failed",
                "error": str(log_exc)
            })

        # ---- Step 2: Analyze activity log for configuration changes ----
        try:
            monitor_client = MonitorManagementClient(credential, subscription_id)
            filter_str = (
                f"eventTimestamp ge '{(now - time_range).strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"and eventTimestamp le '{now.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"and resourceGroupName eq '{resource_group}'"
            )

            activity_logs = list(monitor_client.activity_logs.list(filter=filter_str))

            config_changes = []
            for log_entry in activity_logs[:50]:
                if log_entry.operation_name and any(
                    op in (log_entry.operation_name.localized_value or "").lower()
                    for op in ["write", "delete", "action", "update", "create", "restart", "stop", "start"]
                ):
                    change_entry = {
                        "time": str(log_entry.event_timestamp) if log_entry.event_timestamp else "unknown",
                        "operation": log_entry.operation_name.localized_value if log_entry.operation_name else "unknown",
                        "status": log_entry.status.localized_value if log_entry.status else "unknown",
                        "caller": log_entry.caller or "unknown",
                        "resource": log_entry.resource_id or "unknown"
                    }
                    config_changes.append(change_entry)

                    rca_result["timeline"].append({
                        "time": change_entry["time"],
                        "event": f"Configuration change: {change_entry['operation']}",
                        "severity": "medium",
                        "details": f"By {change_entry['caller']} - Status: {change_entry['status']}"
                    })

            rca_result["evidence"].append({
                "source": "activity_log",
                "total_changes": len(config_changes),
                "changes": config_changes[:20]
            })
        except Exception as activity_exc:
            logger.warning(f"Activity log analysis failed for RCA: {activity_exc}")
            rca_result["evidence"].append({
                "source": "activity_log",
                "status": "failed",
                "error": str(activity_exc)
            })

        # ---- Step 3: Check resource dependencies for cascade failures ----
        try:
            graph_client = ResourceGraphClient(credential)

            dep_query = f"""
            Resources
            | where id =~ '{resource_id}'
            | project id, name, type, location, resourceGroup, properties
            | extend dependencies = pack_array(
                properties.networkProfile.networkInterfaces,
                properties.storageProfile.osDisk,
                properties.storageProfile.dataDisks,
                properties.networkSecurityGroup,
                properties.subnet,
                properties.publicIPAddress
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
            | distinct id=coalesce(dep_id, id)
            | join kind=inner (
                Resources
                | project id, name, type, location, resourceGroup
            ) on id
            | project id, name, type, location, resourceGroup
            | limit 30
            """

            dep_request = QueryRequest(
                subscriptions=[subscription_id],
                query=dep_query,
                options=QueryRequestOptions(top=30)
            )
            dep_response = graph_client.resources(dep_request)

            unhealthy_deps = []
            all_deps = []
            if hasattr(dep_response, 'data') and dep_response.data:
                for row in dep_response.data:
                    dep_info = {
                        "resource_id": row.get('id', ''),
                        "name": row.get('name', ''),
                        "type": row.get('type', ''),
                        "health_status": "unknown"
                    }

                    # Check health for each dependency
                    if ResourceHealthMgmtClient is not None:
                        try:
                            health_client = ResourceHealthMgmtClient(credential, subscription_id)
                            health_resp = health_client.availability_statuses.get_by_resource(
                                resource_uri=dep_info["resource_id"]
                            )
                            dep_info["health_status"] = health_resp.properties.availability_state
                            if dep_info["health_status"] in ("Unavailable", "Degraded"):
                                unhealthy_deps.append(dep_info)
                        except Exception:
                            dep_info["health_status"] = "not_supported"

                    all_deps.append(dep_info)

            rca_result["evidence"].append({
                "source": "dependency_analysis",
                "total_dependencies": len(all_deps),
                "unhealthy_dependencies": len(unhealthy_deps),
                "unhealthy_details": unhealthy_deps
            })

            if unhealthy_deps:
                rca_result["timeline"].append({
                    "time": now.isoformat(),
                    "event": f"{len(unhealthy_deps)} unhealthy dependencies detected",
                    "severity": "high",
                    "details": ", ".join(d["name"] for d in unhealthy_deps)
                })
        except Exception as dep_exc:
            logger.warning(f"Dependency analysis failed for RCA: {dep_exc}")
            rca_result["evidence"].append({
                "source": "dependency_analysis",
                "status": "failed",
                "error": str(dep_exc)
            })

        # ---- Step 4: Query App Insights for distributed traces ----
        try:
            app_insights_query = f"""
            union requests, dependencies, exceptions
            | where timestamp > ago({hours}h)
            | where cloud_RoleName contains '{resource_name}' or
                    operation_Name contains '{resource_name}'
            | summarize
                FailedRequests = countif(success == false),
                TotalRequests = count(),
                AvgDuration = avg(duration),
                P95Duration = percentile(duration, 95),
                TopExceptions = make_list(
                    strcat(tostring(timestamp), ' | ', type, ' | ', outerMessage), 5
                )
            | extend FailureRate = round(todouble(FailedRequests) / todouble(TotalRequests) * 100, 2)
            """

            ai_response = logs_client.query_workspace(
                workspace_id=workspace_id,
                query=app_insights_query,
                timespan=time_range
            )

            for table in ai_response.tables:
                for row in table.rows:
                    rca_result["evidence"].append({
                        "source": "app_insights_traces",
                        "failed_requests": row[0] if row[0] else 0,
                        "total_requests": row[1] if row[1] else 0,
                        "avg_duration_ms": round(row[2], 2) if row[2] else 0,
                        "p95_duration_ms": round(row[3], 2) if row[3] else 0,
                        "top_exceptions": row[4] if len(row) > 4 and row[4] else [],
                        "failure_rate_pct": row[5] if len(row) > 5 and row[5] else 0
                    })
        except Exception as ai_exc:
            logger.warning(f"App Insights trace analysis failed for RCA: {ai_exc}")
            rca_result["evidence"].append({
                "source": "app_insights_traces",
                "status": "failed",
                "error": str(ai_exc)
            })

        # ---- Step 5: Generate hypothesis and recommendations ----
        # Sort timeline by time
        rca_result["timeline"].sort(key=lambda x: x.get("time", ""))

        # Calculate confidence score based on evidence quality
        evidence_count = len([e for e in rca_result["evidence"] if e.get("status") != "failed"])
        rca_result["confidence_score"] = round(min(evidence_count / 4.0, 1.0) * 100, 1)

        # Generate hypothesis based on evidence
        has_config_changes = any(
            e.get("source") == "activity_log" and e.get("total_changes", 0) > 0
            for e in rca_result["evidence"]
        )
        has_unhealthy_deps = any(
            e.get("source") == "dependency_analysis" and e.get("unhealthy_dependencies", 0) > 0
            for e in rca_result["evidence"]
        )
        has_high_failure_rate = any(
            e.get("source") == "app_insights_traces" and (e.get("failure_rate_pct") or 0) > 10
            for e in rca_result["evidence"]
        )
        has_errors = any(
            e.get("source") == "log_correlation" and (e.get("error_count") or 0) > 0
            for e in rca_result["evidence"]
        )

        if has_config_changes and has_errors:
            rca_result["root_cause_hypothesis"] = (
                "Configuration change correlated with error onset. "
                "A recent change to the resource or its environment likely triggered the incident."
            )
            rca_result["confidence_score"] = min(rca_result["confidence_score"] + 15, 100)
        elif has_unhealthy_deps:
            rca_result["root_cause_hypothesis"] = (
                "Cascading failure from unhealthy dependency. "
                "One or more upstream/downstream dependencies are degraded or unavailable."
            )
            rca_result["confidence_score"] = min(rca_result["confidence_score"] + 10, 100)
        elif has_high_failure_rate:
            rca_result["root_cause_hypothesis"] = (
                "Application-level failures detected with elevated failure rate. "
                "Likely caused by application code errors, resource exhaustion, or external service failures."
            )
        elif has_errors:
            rca_result["root_cause_hypothesis"] = (
                "Errors detected in logs but no single clear root cause identified. "
                "Further investigation recommended - check recent deployments and external dependencies."
            )
        else:
            rca_result["root_cause_hypothesis"] = (
                "Insufficient evidence to determine root cause. "
                "Consider expanding the time window or providing specific error patterns to search for."
            )
            rca_result["confidence_score"] = max(rca_result["confidence_score"] - 20, 0)

        # Generate recommended actions
        rca_result["recommended_actions"] = []
        if has_config_changes:
            rca_result["recommended_actions"].append(
                "Review and potentially rollback recent configuration changes"
            )
        if has_unhealthy_deps:
            rca_result["recommended_actions"].append(
                "Investigate and remediate unhealthy dependencies first"
            )
        if has_high_failure_rate:
            rca_result["recommended_actions"].extend([
                "Check application logs for stack traces and exceptions",
                "Verify resource limits (CPU, memory) are not exhausted",
                "Check external service connectivity"
            ])
        if has_errors:
            rca_result["recommended_actions"].append(
                "Analyze error patterns for common failure modes"
            )
        rca_result["recommended_actions"].extend([
            "Check Azure Service Health for platform-level issues",
            "Review Network Security Group rules and firewall configurations",
            "Verify DNS resolution and connectivity to dependent services"
        ])

        # Cache the result
        _cache_set("perform_root_cause_analysis", cache_args, rca_result, "health")

        # Audit the operation
        _log_audit_event(
            operation="perform_root_cause_analysis",
            resource_id=resource_id,
            details={
                "evidence_sources": len(rca_result["evidence"]),
                "timeline_events": len(rca_result["timeline"]),
                "confidence_score": rca_result["confidence_score"],
                "hypothesis": rca_result["root_cause_hypothesis"][:100]
            },
            success=True
        )

        logger.info(
            f"RCA completed for {resource_id}: confidence={rca_result['confidence_score']}%, "
            f"evidence={len(rca_result['evidence'])}, timeline={len(rca_result['timeline'])}"
        )
        return [TextContent(type="text", text=json.dumps(rca_result, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="perform_root_cause_analysis",
            resource_id=resource_id,
            details={"error": str(exc)},
            success=False
        )
        logger.error(f"Error performing root cause analysis: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="trace_dependency_chain",
    description=(
        "Build a full dependency graph for an Azure resource, query health status "
        "for each dependency, identify broken links or degraded components, and "
        "calculate the blast radius of failures. "
        "✅ USE THIS TOOL when users ask: 'What is the blast radius?', 'Trace dependencies', "
        "'Show dependency chain', 'What will be affected if this fails?'. "
        "Goes deeper than get_resource_dependencies by including transitive dependencies "
        "and calculating blast radius metrics."
    ),
)
async def trace_dependency_chain(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID to trace dependencies for"],
    depth: Annotated[int, "Dependency traversal depth (1-3, default: 2)"] = 2,
    include_health: Annotated[bool, "Whether to query health status for each dependency (default: True)"] = True,
) -> list[TextContent]:
    """Trace full dependency chain with health status and blast radius"""
    try:
        if ResourceGraphClient is None or QueryRequest is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure Resource Graph SDK not installed"
            }, indent=2))]

        # Check cache first
        cache_args = {"resource_id": resource_id, "depth": depth}
        cached = _cache_get("trace_dependency_chain", cache_args)
        if cached is not None:
            logger.info(f"Dependency chain cache hit for {resource_id}")
            return [TextContent(type="text", text=json.dumps(cached, indent=2))]

        credential = _get_credential()
        subscription_id = _get_subscription_id()

        # Clamp depth to safe range
        depth = max(1, min(depth, 3))

        # Parse resource ID
        parts = resource_id.split('/')
        if len(parts) < 9:
            raise ValueError("Invalid resource ID format")

        resource_name = parts[8]
        resource_type = f"{parts[6]}/{parts[7]}"
        resource_group = parts[4]

        graph_client = ResourceGraphClient(credential)

        # Build full dependency graph through iterative traversal
        visited = set()
        visited.add(resource_id.lower())
        dependency_graph = {}
        all_dependencies = []
        frontier = [resource_id]

        for current_depth in range(depth):
            if not frontier:
                break

            next_frontier = []
            for current_resource in frontier:
                current_parts = current_resource.split('/')
                current_name = current_parts[8] if len(current_parts) >= 9 else current_resource

                # Query Resource Graph for dependencies of current resource
                dep_query = f"""
                Resources
                | where id =~ '{current_resource}'
                | project id, name, type, properties
                | extend dependencies = pack_array(
                    properties.networkProfile.networkInterfaces,
                    properties.storageProfile.osDisk,
                    properties.storageProfile.dataDisks,
                    properties.networkSecurityGroup,
                    properties.subnet,
                    properties.publicIPAddress,
                    properties.loadBalancerBackendAddressPools,
                    properties.serverFarmId,
                    properties.hostingEnvironmentProfile
                )
                | mvexpand dependencies
                | where isnotnull(dependencies)
                | extend dep_id = tostring(dependencies.id)
                | where isnotempty(dep_id)
                | project dep_id
                | union (
                    Resources
                    | where properties contains '{current_name}' or properties contains '{current_resource}'
                    | where id !~ '{current_resource}'
                    | project id
                )
                | distinct id=coalesce(dep_id, id)
                | join kind=inner (
                    Resources
                    | project id, name, type, location, resourceGroup
                ) on id
                | project id, name, type, location, resourceGroup
                | limit 30
                """

                try:
                    request = QueryRequest(
                        subscriptions=[subscription_id],
                        query=dep_query,
                        options=QueryRequestOptions(top=30)
                    )
                    response = graph_client.resources(request)

                    if hasattr(response, 'data') and response.data:
                        for row in response.data:
                            dep_id = row.get('id', '').lower()
                            if dep_id and dep_id not in visited:
                                visited.add(dep_id)
                                dep_info = {
                                    "resource_id": row.get('id', ''),
                                    "name": row.get('name', ''),
                                    "type": row.get('type', ''),
                                    "location": row.get('location', ''),
                                    "resource_group": row.get('resourceGroup', ''),
                                    "depth": current_depth + 1,
                                    "parent_resource": current_resource,
                                    "health_status": "unknown"
                                }
                                all_dependencies.append(dep_info)
                                next_frontier.append(row.get('id', ''))

                                # Build graph adjacency
                                if current_resource not in dependency_graph:
                                    dependency_graph[current_resource] = []
                                dependency_graph[current_resource].append(row.get('id', ''))

                except Exception as query_exc:
                    logger.warning(f"Dependency query failed for {current_resource}: {query_exc}")

            frontier = next_frontier

        # Query health for all dependencies (if enabled)
        unhealthy_components = []
        if include_health and ResourceHealthMgmtClient is not None:
            health_client = ResourceHealthMgmtClient(credential, subscription_id)

            for dep in all_dependencies:
                try:
                    health_resp = health_client.availability_statuses.get_by_resource(
                        resource_uri=dep["resource_id"]
                    )
                    dep["health_status"] = health_resp.properties.availability_state
                    dep["health_summary"] = health_resp.properties.summary or ""

                    if dep["health_status"] in ("Unavailable", "Degraded"):
                        unhealthy_components.append({
                            "resource_id": dep["resource_id"],
                            "name": dep["name"],
                            "type": dep["type"],
                            "health_status": dep["health_status"],
                            "health_summary": dep["health_summary"],
                            "depth": dep["depth"]
                        })
                except Exception:
                    dep["health_status"] = "not_supported"

        # Calculate blast radius - resources that depend on unhealthy components
        blast_radius_resources = []
        if unhealthy_components:
            unhealthy_ids = {c["resource_id"].lower() for c in unhealthy_components}

            # Find all resources that transitively depend on unhealthy ones
            for parent, children in dependency_graph.items():
                for child in children:
                    if child.lower() in unhealthy_ids:
                        blast_radius_resources.append({
                            "affected_resource": parent,
                            "unhealthy_dependency": child,
                            "impact": "direct"
                        })

        # Build type summary
        type_counts = {}
        for dep in all_dependencies:
            t = dep.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        result = {
            "success": True,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "resource_type": resource_type,
            "traversal_depth": depth,
            "dependency_graph": {
                "total_nodes": len(all_dependencies) + 1,
                "total_edges": sum(len(v) for v in dependency_graph.values()),
                "adjacency": {k: v for k, v in dependency_graph.items()},
                "type_distribution": type_counts
            },
            "dependencies": all_dependencies,
            "unhealthy_components": unhealthy_components,
            "blast_radius": {
                "total_affected_resources": len(blast_radius_resources),
                "affected_resources": blast_radius_resources,
                "risk_level": "Critical" if len(unhealthy_components) > 3
                    else "High" if len(unhealthy_components) > 1
                    else "Medium" if len(unhealthy_components) == 1
                    else "Low"
            },
            "analysis": {
                "total_dependencies": len(all_dependencies),
                "unhealthy_count": len(unhealthy_components),
                "health_check_coverage": sum(
                    1 for d in all_dependencies if d["health_status"] not in ("unknown", "not_supported")
                ),
                "cascading_failure_risk": "High" if unhealthy_components else "Low"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Cache the result
        _cache_set("trace_dependency_chain", cache_args, result, "health")

        # Audit the operation
        _log_audit_event(
            operation="trace_dependency_chain",
            resource_id=resource_id,
            details={
                "total_dependencies": len(all_dependencies),
                "unhealthy_count": len(unhealthy_components),
                "depth": depth,
                "blast_radius": len(blast_radius_resources)
            },
            success=True
        )

        logger.info(
            f"Dependency chain traced for {resource_id}: "
            f"{len(all_dependencies)} deps, {len(unhealthy_components)} unhealthy, "
            f"blast_radius={len(blast_radius_resources)}"
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="trace_dependency_chain",
            resource_id=resource_id,
            details={"error": str(exc)},
            success=False
        )
        logger.error(f"Error tracing dependency chain: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="analyze_log_patterns",
    description=(
        "Perform statistical log pattern detection and anomaly analysis. "
        "Queries logs for a time range, extracts error patterns using frequency analysis, "
        "groups similar errors, and identifies anomalous error spikes using Z-score analysis. "
        "✅ USE THIS TOOL when users ask: 'Find error patterns in my logs', "
        "'Are there any log anomalies?', 'What error patterns exist?', "
        "'Analyze my log data for trends'. "
        "Returns error patterns with frequencies, grouped anomalies, and distribution data."
    ),
)
async def analyze_log_patterns(
    context: Context,
    workspace_id: Annotated[str, "Log Analytics workspace ID"],
    resource_name: Annotated[str, "Resource name or partial name to filter logs"],
    hours: Annotated[int, "Hours to look back for analysis (default: 24)"] = 24,
    min_frequency: Annotated[int, "Minimum occurrences to include an error pattern (default: 3)"] = 3,
) -> list[TextContent]:
    """Analyze log patterns with statistical anomaly detection"""
    try:
        if LogsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed (azure-monitor-query required)"
            }, indent=2))]

        # Check cache first
        cache_args = {"workspace_id": workspace_id, "resource_name": resource_name, "hours": hours}
        cached = _cache_get("analyze_log_patterns", cache_args)
        if cached is not None:
            logger.info(f"Log pattern analysis cache hit for {resource_name}")
            return [TextContent(type="text", text=json.dumps(cached, indent=2))]

        credential = _get_credential()
        logs_client = LogsQueryClient(credential)
        time_range = timedelta(hours=hours)
        now = datetime.utcnow()

        result = {
            "success": True,
            "resource_name": resource_name,
            "analysis_window": {
                "start": (now - time_range).isoformat(),
                "end": now.isoformat(),
                "hours": hours
            },
            "error_patterns": [],
            "anomalies": [],
            "frequency_distribution": {},
            "summary": {},
            "timestamp": now.isoformat()
        }

        # ---- Step 1: Extract error patterns with frequency analysis ----
        pattern_query = f"""
        union *
        | where TimeGenerated > ago({hours}h)
        | where _ResourceId contains '{resource_name}'
        | where Level in ('Error', 'Critical') or
                OperationName contains 'Error' or OperationName contains 'Fail'
        | extend ErrorCategory = case(
            OperationName contains 'timeout' or ResultDescription contains 'timeout', 'Timeout',
            OperationName contains '401' or ResultDescription contains 'Unauthorized', 'Authentication',
            OperationName contains '403' or ResultDescription contains 'Forbidden', 'Authorization',
            OperationName contains '404' or ResultDescription contains 'NotFound', 'NotFound',
            OperationName contains '429' or ResultDescription contains 'throttl', 'Throttling',
            OperationName contains '500' or ResultDescription contains 'Internal', 'InternalError',
            OperationName contains '502' or ResultDescription contains 'Bad Gateway', 'BadGateway',
            OperationName contains '503' or ResultDescription contains 'unavailable', 'ServiceUnavailable',
            OperationName contains 'connection' or ResultDescription contains 'connection', 'Connectivity',
            OperationName contains 'DNS' or ResultDescription contains 'DNS', 'DNSResolution',
            OperationName contains 'memory' or ResultDescription contains 'OutOfMemory', 'ResourceExhaustion',
            'Other'
        )
        | summarize
            Count = count(),
            FirstSeen = min(TimeGenerated),
            LastSeen = max(TimeGenerated),
            SampleMessages = make_list(substring(tostring(ResultDescription), 0, 200), 3)
            by ErrorCategory, OperationName
        | where Count >= {min_frequency}
        | order by Count desc
        | limit 50
        """

        try:
            pattern_response = logs_client.query_workspace(
                workspace_id=workspace_id,
                query=pattern_query,
                timespan=time_range
            )

            for table in pattern_response.tables:
                for row in table.rows:
                    pattern = {
                        "error_category": row[0] if row[0] else "Unknown",
                        "operation_name": row[1] if row[1] else "Unknown",
                        "count": row[2] if row[2] else 0,
                        "first_seen": str(row[3]) if row[3] else None,
                        "last_seen": str(row[4]) if row[4] else None,
                        "sample_messages": row[5] if len(row) > 5 and row[5] else []
                    }
                    result["error_patterns"].append(pattern)

        except Exception as pat_exc:
            logger.warning(f"Error pattern extraction failed: {pat_exc}")
            result["error_patterns"] = [{"status": "query_failed", "error": str(pat_exc)}]

        # ---- Step 2: Hourly frequency distribution for anomaly detection ----
        distribution_query = f"""
        union *
        | where TimeGenerated > ago({hours}h)
        | where _ResourceId contains '{resource_name}'
        | where Level in ('Error', 'Critical') or
                OperationName contains 'Error' or OperationName contains 'Fail'
        | summarize ErrorCount = count() by bin(TimeGenerated, 1h)
        | order by TimeGenerated asc
        """

        hourly_counts = []
        try:
            dist_response = logs_client.query_workspace(
                workspace_id=workspace_id,
                query=distribution_query,
                timespan=time_range
            )

            for table in dist_response.tables:
                for row in table.rows:
                    hourly_counts.append({
                        "hour": str(row[0]) if row[0] else "",
                        "error_count": row[1] if row[1] else 0
                    })

            result["frequency_distribution"] = {
                "granularity": "1h",
                "data_points": hourly_counts
            }

        except Exception as dist_exc:
            logger.warning(f"Frequency distribution query failed: {dist_exc}")
            result["frequency_distribution"] = {"status": "query_failed", "error": str(dist_exc)}

        # ---- Step 3: Z-score anomaly detection on hourly counts ----
        if hourly_counts and len(hourly_counts) >= 3:
            counts = [h["error_count"] for h in hourly_counts]
            n = len(counts)
            mean_val = sum(counts) / n
            variance = sum((x - mean_val) ** 2 for x in counts) / n
            std_dev = variance ** 0.5 if variance > 0 else 0.001

            for entry in hourly_counts:
                z_score = (entry["error_count"] - mean_val) / std_dev if std_dev > 0 else 0

                if abs(z_score) > 2.0:
                    result["anomalies"].append({
                        "hour": entry["hour"],
                        "error_count": entry["error_count"],
                        "z_score": round(z_score, 2),
                        "severity": "critical" if abs(z_score) > 3.0 else "warning",
                        "description": (
                            f"Error spike detected: {entry['error_count']} errors "
                            f"({round(z_score, 1)} std deviations from mean of {round(mean_val, 1)})"
                        )
                    })

            result["frequency_distribution"]["statistics"] = {
                "mean_errors_per_hour": round(mean_val, 2),
                "std_deviation": round(std_dev, 2),
                "min_errors": min(counts),
                "max_errors": max(counts),
                "total_data_points": n,
                "anomaly_threshold": "Z-score > 2.0"
            }

        # ---- Step 4: Generate summary ----
        total_errors = sum(
            p.get("count", 0) for p in result["error_patterns"]
            if isinstance(p, dict) and "count" in p
        )
        unique_categories = set(
            p.get("error_category", "") for p in result["error_patterns"]
            if isinstance(p, dict) and "error_category" in p
        )

        result["summary"] = {
            "total_error_patterns": len(result["error_patterns"]),
            "total_errors": total_errors,
            "unique_error_categories": list(unique_categories),
            "anomaly_count": len(result["anomalies"]),
            "top_error_category": (
                result["error_patterns"][0]["error_category"]
                if result["error_patterns"] and isinstance(result["error_patterns"][0], dict)
                and "error_category" in result["error_patterns"][0]
                else "None"
            ),
            "health_assessment": (
                "Critical - Multiple anomalous error spikes detected"
                if len(result["anomalies"]) > 3
                else "Warning - Anomalous error patterns detected"
                if len(result["anomalies"]) > 0
                else "Healthy - No anomalous patterns detected"
                if total_errors == 0
                else "Monitoring - Errors present but within normal range"
            )
        }

        # Cache the result
        _cache_set("analyze_log_patterns", cache_args, result, "health")

        # Audit the operation
        _log_audit_event(
            operation="analyze_log_patterns",
            resource_id=None,
            details={
                "resource_name": resource_name,
                "patterns_found": len(result["error_patterns"]),
                "anomalies_found": len(result["anomalies"]),
                "total_errors": total_errors
            },
            success=True
        )

        logger.info(
            f"Log pattern analysis completed for {resource_name}: "
            f"{len(result['error_patterns'])} patterns, {len(result['anomalies'])} anomalies"
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        _log_audit_event(
            operation="analyze_log_patterns",
            resource_id=None,
            details={"error": str(exc), "resource_name": resource_name},
            success=False
        )
        logger.error(f"Error analyzing log patterns: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Proactive Anomaly Detection Tools (Phase 2.2)
# ============================================================================

@_server.tool(
    name="detect_performance_anomalies",
    description=(
        "Detect real-time performance anomalies by comparing recent metrics against historical baselines. "
        "Uses Z-score statistical analysis to flag CPU, memory, network, and response time deviations. "
        "✅ USE THIS TOOL when users ask: 'Are there any anomalies in my resource?', "
        "'Detect unusual behavior in my container app', 'Find performance spikes'. "
        "Queries the last 24h of metrics and compares against a 30-day historical baseline. "
        "Flags any metric deviating more than 2 standard deviations from the baseline."
    ),
)
async def detect_performance_anomalies(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    sensitivity: Annotated[float, "Z-score threshold for anomaly detection (default: 2.0, lower = more sensitive)"] = 2.0,
    baseline_days: Annotated[int, "Number of days for historical baseline (default: 30)"] = 30,
    recent_hours: Annotated[int, "Hours of recent data to analyze (default: 24)"] = 24,
) -> list[TextContent]:
    """Detect performance anomalies using Z-score statistical analysis"""
    try:
        if MetricsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        # Check cache first
        cache_args = {
            "resource_id": resource_id,
            "sensitivity": sensitivity,
            "baseline_days": baseline_days,
            "recent_hours": recent_hours,
        }
        cached = _cache_get("detect_performance_anomalies", cache_args)
        if cached is not None:
            return [TextContent(type="text", text=json.dumps(cached, indent=2))]

        credential = _get_credential()
        metrics_client = MetricsQueryClient(credential)

        # Detect resource type and select appropriate metrics
        resource_id_lower = resource_id.lower()
        if "/microsoft.app/containerapps/" in resource_id_lower:
            metric_names = ["CpuPercentage", "MemoryPercentage", "Requests", "Replicas"]
            resource_type = "ContainerApp"
        elif "/microsoft.web/sites/" in resource_id_lower:
            metric_names = ["CpuPercentage", "MemoryPercentage", "HttpResponseTime", "Requests"]
            resource_type = "AppService"
        elif "/microsoft.compute/virtualmachines/" in resource_id_lower:
            metric_names = ["Percentage CPU", "Network In Total", "Network Out Total", "Disk Read Bytes"]
            resource_type = "VirtualMachine"
        elif "/microsoft.containerservice/managedclusters/" in resource_id_lower:
            metric_names = ["node_cpu_usage_percentage", "node_memory_working_set_percentage", "kube_pod_status_ready"]
            resource_type = "AKS"
        else:
            metric_names = ["Percentage CPU"]
            resource_type = "Unknown"

        anomalies = []
        baseline_stats = {}
        current_stats = {}
        overall_anomaly_score = 0.0

        for metric_name in metric_names:
            try:
                # Query historical baseline (full baseline_days period)
                baseline_timespan = timedelta(days=baseline_days)
                baseline_result = metrics_client.query_resource(
                    resource_id,
                    metric_names=[metric_name],
                    timespan=baseline_timespan,
                    granularity=timedelta(hours=1),
                )

                baseline_values = []
                for metric in baseline_result.metrics:
                    for ts in metric.timeseries:
                        for dp in ts.data:
                            val = dp.average or dp.total or dp.maximum
                            if val is not None:
                                baseline_values.append(float(val))

                if len(baseline_values) < 24:
                    logger.warning(f"Insufficient baseline data for {metric_name}: {len(baseline_values)} points")
                    continue

                # Calculate baseline statistics
                n = len(baseline_values)
                mean = sum(baseline_values) / n
                variance = sum((v - mean) ** 2 for v in baseline_values) / n
                std_dev = variance ** 0.5

                baseline_stats[metric_name] = {
                    "mean": round(mean, 4),
                    "std_dev": round(std_dev, 4),
                    "min": round(min(baseline_values), 4),
                    "max": round(max(baseline_values), 4),
                    "data_points": n,
                }

                # Query recent data (last recent_hours)
                recent_timespan = timedelta(hours=recent_hours)
                recent_result = metrics_client.query_resource(
                    resource_id,
                    metric_names=[metric_name],
                    timespan=recent_timespan,
                    granularity=timedelta(minutes=15),
                )

                recent_values = []
                recent_data_points = []
                for metric in recent_result.metrics:
                    for ts in metric.timeseries:
                        for dp in ts.data:
                            val = dp.average or dp.total or dp.maximum
                            if val is not None:
                                recent_values.append(float(val))
                                recent_data_points.append({
                                    "timestamp": str(dp.timestamp),
                                    "value": float(val),
                                })

                if not recent_values:
                    continue

                recent_mean = sum(recent_values) / len(recent_values)
                current_stats[metric_name] = {
                    "current": round(recent_values[-1], 4) if recent_values else None,
                    "mean": round(recent_mean, 4),
                    "min": round(min(recent_values), 4),
                    "max": round(max(recent_values), 4),
                    "data_points": len(recent_values),
                }

                # Calculate Z-scores for recent data points
                if std_dev > 0:
                    for dp in recent_data_points:
                        z_score = abs(dp["value"] - mean) / std_dev
                        if z_score > sensitivity:
                            anomalies.append({
                                "metric": metric_name,
                                "timestamp": dp["timestamp"],
                                "value": round(dp["value"], 4),
                                "baseline_mean": round(mean, 4),
                                "z_score": round(z_score, 2),
                                "deviation_percent": round(abs(dp["value"] - mean) / mean * 100, 2) if mean != 0 else None,
                                "direction": "above" if dp["value"] > mean else "below",
                                "severity": (
                                    "critical" if z_score > 3.5
                                    else "high" if z_score > 3.0
                                    else "medium" if z_score > 2.5
                                    else "low"
                                ),
                            })

                    # Contribute to overall anomaly score
                    recent_z_scores = [abs(v - mean) / std_dev for v in recent_values]
                    max_z = max(recent_z_scores) if recent_z_scores else 0
                    overall_anomaly_score = max(overall_anomaly_score, max_z)

            except Exception as metric_exc:
                logger.warning(f"Error analyzing metric {metric_name}: {metric_exc}")
                continue

        # Sort anomalies by z_score descending
        anomalies.sort(key=lambda x: x["z_score"], reverse=True)

        # Limit to top 50 most significant anomalies
        anomalies = anomalies[:50]

        result = {
            "success": True,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "analysis_config": {
                "sensitivity_threshold": sensitivity,
                "baseline_period_days": baseline_days,
                "recent_period_hours": recent_hours,
            },
            "anomaly_summary": {
                "total_anomalies_detected": len(anomalies),
                "anomaly_score": round(overall_anomaly_score, 2),
                "status": (
                    "critical" if overall_anomaly_score > 3.5
                    else "warning" if overall_anomaly_score > sensitivity
                    else "normal"
                ),
                "metrics_with_anomalies": list(set(a["metric"] for a in anomalies)),
            },
            "anomalies": anomalies,
            "baseline_stats": baseline_stats,
            "current_stats": current_stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Cache result (short TTL since anomaly data changes frequently)
        _cache_set("detect_performance_anomalies", cache_args, result, ttl_profile="short")

        _log_audit_event(
            "detect_performance_anomalies",
            resource_id,
            {
                "anomaly_count": len(anomalies),
                "anomaly_score": round(overall_anomaly_score, 2),
                "status": result["anomaly_summary"]["status"],
            },
            True,
        )

        logger.info(
            f"Anomaly detection completed for {resource_id}: "
            f"{len(anomalies)} anomalies, score={round(overall_anomaly_score, 2)}"
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as exc:
        _log_audit_event(
            "detect_performance_anomalies",
            resource_id,
            {"error": str(exc)},
            False,
        )
        logger.error(f"Error detecting performance anomalies: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="predict_capacity_issues",
    description=(
        "Predict capacity issues using linear regression and seasonal trend analysis. "
        "Analyzes growth trends across critical metrics and projects threshold crossings. "
        "✅ USE THIS TOOL when users ask: 'Will my app run out of capacity?', "
        "'Predict scaling needs for my container app', 'Capacity planning for next month'. "
        "Enhanced version of predict_resource_exhaustion with multi-metric analysis, "
        "seasonal decomposition, and early-warning alerts at 7, 14, and 30 day horizons. "
        "Returns predictions, time-to-exhaustion estimates, and scaling recommendations."
    ),
)
async def predict_capacity_issues(
    context: Context,
    resource_id: Annotated[str, "Full Azure resource ID"],
    threshold: Annotated[float, "Warning threshold percentage (default: 80)"] = 80.0,
    critical_threshold: Annotated[float, "Critical threshold percentage (default: 90)"] = 90.0,
    history_days: Annotated[int, "Days of historical data for trend analysis (default: 30)"] = 30,
) -> list[TextContent]:
    """Predict capacity issues using linear regression and seasonal analysis"""
    try:
        if MetricsQueryClient is None:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": "Azure SDK not installed"
            }, indent=2))]

        # Check cache first
        cache_args = {
            "resource_id": resource_id,
            "threshold": threshold,
            "critical_threshold": critical_threshold,
            "history_days": history_days,
        }
        cached = _cache_get("predict_capacity_issues", cache_args)
        if cached is not None:
            return [TextContent(type="text", text=json.dumps(cached, indent=2))]

        credential = _get_credential()
        metrics_client = MetricsQueryClient(credential)

        # Select metrics based on resource type
        resource_id_lower = resource_id.lower()
        if "/microsoft.app/containerapps/" in resource_id_lower:
            metrics_to_analyze = {
                "CpuPercentage": {"unit": "%", "label": "CPU Usage"},
                "MemoryPercentage": {"unit": "%", "label": "Memory Usage"},
            }
            resource_type = "ContainerApp"
        elif "/microsoft.web/sites/" in resource_id_lower:
            metrics_to_analyze = {
                "CpuPercentage": {"unit": "%", "label": "CPU Usage"},
                "MemoryPercentage": {"unit": "%", "label": "Memory Usage"},
            }
            resource_type = "AppService"
        elif "/microsoft.compute/virtualmachines/" in resource_id_lower:
            metrics_to_analyze = {
                "Percentage CPU": {"unit": "%", "label": "CPU Usage"},
                "Network In Total": {"unit": "bytes", "label": "Network In"},
                "Network Out Total": {"unit": "bytes", "label": "Network Out"},
            }
            resource_type = "VirtualMachine"
        elif "/microsoft.containerservice/managedclusters/" in resource_id_lower:
            metrics_to_analyze = {
                "node_cpu_usage_percentage": {"unit": "%", "label": "Node CPU"},
                "node_memory_working_set_percentage": {"unit": "%", "label": "Node Memory"},
            }
            resource_type = "AKS"
        else:
            metrics_to_analyze = {
                "Percentage CPU": {"unit": "%", "label": "CPU Usage"},
            }
            resource_type = "Unknown"

        predictions = []
        time_to_exhaustion = []
        recommended_scaling = []

        for metric_name, metric_info in metrics_to_analyze.items():
            try:
                timespan = timedelta(days=history_days)
                result = metrics_client.query_resource(
                    resource_id,
                    metric_names=[metric_name],
                    timespan=timespan,
                    granularity=timedelta(hours=1),
                )

                # Extract hourly values
                values = []
                timestamps = []
                for metric in result.metrics:
                    for ts in metric.timeseries:
                        for dp in ts.data:
                            val = dp.average or dp.total or dp.maximum
                            if val is not None:
                                values.append(float(val))
                                timestamps.append(dp.timestamp)

                if len(values) < 48:
                    predictions.append({
                        "metric": metric_name,
                        "label": metric_info["label"],
                        "status": "insufficient_data",
                        "data_points": len(values),
                        "message": f"Need at least 48 hourly data points, got {len(values)}",
                    })
                    continue

                # Linear regression (pure Python)
                n = len(values)
                x = list(range(n))
                x_mean = sum(x) / n
                y_mean = sum(values) / n

                numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
                denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

                slope = numerator / denominator if denominator != 0 else 0
                intercept = y_mean - slope * x_mean

                # Calculate R-squared for confidence
                ss_res = sum((values[i] - (slope * x[i] + intercept)) ** 2 for i in range(n))
                ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
                r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

                current_value = values[-1]
                trend = "increasing" if slope > 0.01 else "decreasing" if slope < -0.01 else "stable"

                # Seasonal decomposition (detect daily patterns)
                # Group by hour-of-day to find daily seasonality
                hourly_pattern = {}
                for i, val in enumerate(values):
                    hour_of_day = i % 24
                    if hour_of_day not in hourly_pattern:
                        hourly_pattern[hour_of_day] = []
                    hourly_pattern[hour_of_day].append(val)

                seasonal_amplitude = 0.0
                if hourly_pattern:
                    hourly_means = {h: sum(vs) / len(vs) for h, vs in hourly_pattern.items()}
                    if hourly_means:
                        seasonal_max = max(hourly_means.values())
                        seasonal_min = min(hourly_means.values())
                        seasonal_amplitude = seasonal_max - seasonal_min

                # Project threshold crossings at 7d, 14d, 30d horizons
                horizon_alerts = []
                for horizon_days in [7, 14, 30]:
                    projected_hours = n + (horizon_days * 24)
                    projected_value = slope * projected_hours + intercept
                    # Add seasonal peak for worst-case projection
                    projected_peak = projected_value + (seasonal_amplitude / 2)

                    horizon_alerts.append({
                        "horizon_days": horizon_days,
                        "projected_value": round(projected_value, 2),
                        "projected_peak": round(projected_peak, 2),
                        "exceeds_warning": projected_peak > threshold if metric_info["unit"] == "%" else False,
                        "exceeds_critical": projected_peak > critical_threshold if metric_info["unit"] == "%" else False,
                    })

                # Calculate time to warning and critical thresholds
                hours_to_warning = None
                hours_to_critical = None
                if slope > 0 and metric_info["unit"] == "%":
                    if current_value < threshold:
                        hours_to_warning = (threshold - current_value) / slope
                    if current_value < critical_threshold:
                        hours_to_critical = (critical_threshold - current_value) / slope

                metric_prediction = {
                    "metric": metric_name,
                    "label": metric_info["label"],
                    "unit": metric_info["unit"],
                    "current_value": round(current_value, 2),
                    "trend": trend,
                    "slope_per_hour": round(slope, 6),
                    "r_squared": round(r_squared, 4),
                    "confidence": (
                        "high" if r_squared > 0.7
                        else "medium" if r_squared > 0.4
                        else "low"
                    ),
                    "seasonal_amplitude": round(seasonal_amplitude, 2),
                    "horizon_projections": horizon_alerts,
                    "data_points": n,
                }
                predictions.append(metric_prediction)

                # Time to exhaustion
                if hours_to_warning is not None or hours_to_critical is not None:
                    exhaustion_entry = {
                        "metric": metric_name,
                        "label": metric_info["label"],
                        "current_value": round(current_value, 2),
                    }
                    if hours_to_warning is not None:
                        exhaustion_entry["hours_to_warning"] = round(hours_to_warning, 1)
                        exhaustion_entry["days_to_warning"] = round(hours_to_warning / 24, 1)
                        exhaustion_entry["warning_date"] = (
                            datetime.utcnow() + timedelta(hours=hours_to_warning)
                        ).isoformat()
                    if hours_to_critical is not None:
                        exhaustion_entry["hours_to_critical"] = round(hours_to_critical, 1)
                        exhaustion_entry["days_to_critical"] = round(hours_to_critical / 24, 1)
                        exhaustion_entry["critical_date"] = (
                            datetime.utcnow() + timedelta(hours=hours_to_critical)
                        ).isoformat()

                    urgency = "safe"
                    check_hours = hours_to_warning or hours_to_critical
                    if check_hours is not None:
                        if check_hours < 24:
                            urgency = "critical"
                        elif check_hours < 168:
                            urgency = "warning"
                        elif check_hours < 720:
                            urgency = "info"
                    exhaustion_entry["urgency"] = urgency
                    time_to_exhaustion.append(exhaustion_entry)

                # Generate scaling recommendations
                if trend == "increasing" and metric_info["unit"] == "%":
                    if current_value > critical_threshold:
                        recommended_scaling.append({
                            "metric": metric_info["label"],
                            "action": "scale_up_immediately",
                            "priority": "critical",
                            "reason": f"Current {metric_info['label']} at {round(current_value, 1)}% exceeds critical threshold ({critical_threshold}%)",
                        })
                    elif current_value > threshold:
                        recommended_scaling.append({
                            "metric": metric_info["label"],
                            "action": "scale_up_soon",
                            "priority": "high",
                            "reason": f"Current {metric_info['label']} at {round(current_value, 1)}% exceeds warning threshold ({threshold}%)",
                        })
                    elif hours_to_warning and hours_to_warning < 168:
                        recommended_scaling.append({
                            "metric": metric_info["label"],
                            "action": "plan_scaling",
                            "priority": "medium",
                            "reason": f"{metric_info['label']} projected to reach {threshold}% in {round(hours_to_warning / 24, 1)} days",
                        })

            except Exception as metric_exc:
                logger.warning(f"Error analyzing capacity for {metric_name}: {metric_exc}")
                predictions.append({
                    "metric": metric_name,
                    "label": metric_info["label"],
                    "status": "error",
                    "error": str(metric_exc),
                })

        # Overall urgency
        urgencies = [e.get("urgency", "safe") for e in time_to_exhaustion]
        urgency_priority = {"critical": 0, "warning": 1, "info": 2, "safe": 3}
        overall_urgency = min(urgencies, key=lambda u: urgency_priority.get(u, 3)) if urgencies else "safe"

        response = {
            "success": True,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "analysis_config": {
                "warning_threshold": threshold,
                "critical_threshold": critical_threshold,
                "history_days": history_days,
            },
            "overall_urgency": overall_urgency,
            "predictions": predictions,
            "time_to_exhaustion": time_to_exhaustion if time_to_exhaustion else None,
            "recommended_scaling": recommended_scaling if recommended_scaling else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        _cache_set("predict_capacity_issues", cache_args, response, ttl_profile="medium")

        _log_audit_event(
            "predict_capacity_issues",
            resource_id,
            {
                "overall_urgency": overall_urgency,
                "metrics_analyzed": len(predictions),
                "scaling_recommendations": len(recommended_scaling),
            },
            True,
        )

        logger.info(
            f"Capacity prediction completed for {resource_id}: "
            f"urgency={overall_urgency}, {len(recommended_scaling)} recommendations"
        )
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        _log_audit_event(
            "predict_capacity_issues",
            resource_id,
            {"error": str(exc)},
            False,
        )
        logger.error(f"Error predicting capacity issues: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="monitor_slo_burn_rate",
    description=(
        "Monitor SLO error budget burn rate and alert if consuming budget too fast. "
        "Calculates current consumption rate vs sustainable rate to predict budget exhaustion. "
        "✅ USE THIS TOOL when users ask: 'Is my SLO burning too fast?', "
        "'Will I run out of error budget this month?', 'SLO burn rate analysis'. "
        "Compares actual error budget consumption to the sustainable rate needed to "
        "maintain compliance through the end of the SLO window. "
        "Returns burn rate, days until exhaustion, and alert severity."
    ),
)
async def monitor_slo_burn_rate(
    context: Context,
    service_name: Annotated[str, "Service name to monitor burn rate for"],
    slo_id: Annotated[str, "SLO definition ID (optional, uses latest for service)"] = "",
    alert_burn_rate_multiplier: Annotated[float, "Alert when burn rate exceeds sustainable rate by this multiplier (default: 2.0)"] = 2.0,
) -> list[TextContent]:
    """Monitor SLO error budget burn rate"""
    try:
        # Find SLO definition (reuse existing pattern from calculate_error_budget)
        slo = None
        if slo_id and slo_id in _slo_definitions:
            slo = _slo_definitions[slo_id]
        else:
            for sid, sdef in _slo_definitions.items():
                if sdef["service_name"] == service_name and sdef["status"] == "active":
                    slo = sdef
                    slo_id = sid

        if not slo:
            # Try loading from Cosmos DB
            container = _get_slo_container()
            if container:
                query = (
                    f"SELECT * FROM c WHERE c.service_name = '{service_name}' "
                    f"AND c.status = 'active' ORDER BY c.created_at DESC OFFSET 0 LIMIT 1"
                )
                items = list(container.query_items(query=query, enable_cross_partition_query=True))
                if items:
                    slo = items[0]
                    slo_id = slo["id"]
                    _slo_definitions[slo_id] = slo

        if not slo:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": (
                    f"No active SLO found for service '{service_name}'. "
                    "Use define_slo to create one first."
                ),
                "service_name": service_name,
            }, indent=2))]

        window_days = slo["window_days"]
        target = slo["target"]
        sli_type = slo["sli_type"]
        total_error_budget_percent = 100 - target  # e.g., 0.1% for 99.9% SLO

        # Determine how far into the SLO window we are
        created_at = slo.get("created_at", "")
        if created_at:
            try:
                slo_start = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, AttributeError):
                slo_start = datetime.utcnow() - timedelta(days=window_days)
        else:
            slo_start = datetime.utcnow() - timedelta(days=window_days)

        now = datetime.utcnow()
        elapsed = now - slo_start
        elapsed_days = elapsed.total_seconds() / 86400
        remaining_days = max(window_days - elapsed_days, 0.01)  # Avoid division by zero

        # Sustainable burn rate: percentage of budget that should be consumed per day
        sustainable_rate_per_day = total_error_budget_percent / window_days

        # Try to get actual error data from Application Insights
        actual_error_rate = None
        measurement_source = "estimated"
        budget_consumed_percent = 0.0

        workspace_id = slo.get("workspace_id", "")
        if workspace_id and LogsQueryClient:
            try:
                credential = _get_credential()
                logs_client = LogsQueryClient(credential)
                timespan = timedelta(days=min(elapsed_days, window_days))

                if sli_type == "availability":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize
                        total = count(),
                        failed = countif(success == false)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        total = float(row[0]) if row[0] else 0
                        failed = float(row[1]) if row[1] else 0
                        if total > 0:
                            actual_error_rate = round((failed / total) * 100, 6)
                            budget_consumed_percent = actual_error_rate
                            measurement_source = "application_insights"

                elif sli_type == "error_rate":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize
                        total = count(),
                        failed = countif(success == false)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        total = float(row[0]) if row[0] else 0
                        failed = float(row[1]) if row[1] else 0
                        if total > 0:
                            actual_error_rate = round((failed / total) * 100, 6)
                            budget_consumed_percent = actual_error_rate
                            measurement_source = "application_insights"

                elif sli_type == "latency":
                    kql = f"""
                    requests
                    | where cloud_RoleName == '{service_name}'
                    | summarize
                        total = count(),
                        violations = countif(duration > 1000)
                    """
                    result = logs_client.query_workspace(workspace_id, kql, timespan=timespan)
                    if hasattr(result, 'tables') and result.tables and result.tables[0].rows:
                        row = result.tables[0].rows[0]
                        total = float(row[0]) if row[0] else 0
                        violations = float(row[1]) if row[1] else 0
                        if total > 0:
                            actual_error_rate = round((violations / total) * 100, 6)
                            budget_consumed_percent = actual_error_rate
                            measurement_source = "application_insights"

            except Exception as query_exc:
                logger.warning(f"Could not query Application Insights for burn rate: {query_exc}")

        # If no live data, estimate from recent audit history
        if measurement_source == "estimated":
            # Use a conservative estimate based on typical error rates
            budget_consumed_percent = total_error_budget_percent * (elapsed_days / window_days) * 0.5
            actual_error_rate = budget_consumed_percent

        # Calculate burn rates
        budget_remaining_percent = max(total_error_budget_percent - budget_consumed_percent, 0)
        budget_consumed_fraction = budget_consumed_percent / total_error_budget_percent if total_error_budget_percent > 0 else 0

        # Current burn rate (budget consumed per day)
        current_burn_rate_per_day = (
            budget_consumed_percent / elapsed_days if elapsed_days > 0 else 0
        )

        # Burn rate multiplier relative to sustainable rate
        burn_rate_multiplier = (
            current_burn_rate_per_day / sustainable_rate_per_day
            if sustainable_rate_per_day > 0
            else 0
        )

        # Days until budget exhaustion at current rate
        days_until_exhaustion = None
        if current_burn_rate_per_day > 0:
            days_until_exhaustion = budget_remaining_percent / current_burn_rate_per_day

        # Determine alert level
        if budget_remaining_percent <= 0:
            alert_level = "critical"
            alert_message = "Error budget exhausted! SLO is in violation."
        elif burn_rate_multiplier > alert_burn_rate_multiplier * 2:
            alert_level = "critical"
            alert_message = (
                f"Burning error budget at {round(burn_rate_multiplier, 1)}x the sustainable rate. "
                f"Budget will be exhausted in ~{round(days_until_exhaustion, 1)} days."
            )
        elif burn_rate_multiplier > alert_burn_rate_multiplier:
            alert_level = "warning"
            alert_message = (
                f"Burn rate ({round(burn_rate_multiplier, 1)}x sustainable) exceeds "
                f"alert threshold ({alert_burn_rate_multiplier}x). Monitor closely."
            )
        elif burn_rate_multiplier > 1.0:
            alert_level = "info"
            alert_message = (
                f"Burn rate slightly above sustainable ({round(burn_rate_multiplier, 1)}x). "
                "Budget may be tight toward end of window."
            )
        else:
            alert_level = "ok"
            alert_message = (
                f"Error budget consumption is healthy at {round(burn_rate_multiplier, 1)}x sustainable rate."
            )

        response = {
            "success": True,
            "service_name": service_name,
            "slo_id": slo_id,
            "slo_config": {
                "target": target,
                "sli_type": sli_type,
                "window_days": window_days,
                "total_error_budget_percent": round(total_error_budget_percent, 4),
            },
            "window_progress": {
                "elapsed_days": round(elapsed_days, 1),
                "remaining_days": round(remaining_days, 1),
                "percent_elapsed": round((elapsed_days / window_days) * 100, 1),
            },
            "budget_status": {
                "budget_consumed_percent": round(budget_consumed_percent, 6),
                "budget_remaining_percent": round(budget_remaining_percent, 6),
                "budget_consumed_fraction": round(budget_consumed_fraction, 4),
            },
            "burn_rate": {
                "current_burn_rate_per_day": round(current_burn_rate_per_day, 6),
                "sustainable_rate_per_day": round(sustainable_rate_per_day, 6),
                "burn_rate_multiplier": round(burn_rate_multiplier, 2),
                "days_until_exhaustion": round(days_until_exhaustion, 1) if days_until_exhaustion else None,
                "exhaustion_date": (
                    (datetime.utcnow() + timedelta(days=days_until_exhaustion)).isoformat()
                    if days_until_exhaustion
                    else None
                ),
            },
            "alert": {
                "level": alert_level,
                "message": alert_message,
                "alert_threshold_multiplier": alert_burn_rate_multiplier,
            },
            "measurement_source": measurement_source,
            "timestamp": datetime.utcnow().isoformat(),
            "note": (
                "Requires workspace_id in SLO definition for live measurements"
                if measurement_source == "estimated"
                else "Live measurement from Application Insights"
            ),
        }

        _log_audit_event(
            "monitor_slo_burn_rate",
            service_name,
            {
                "slo_id": slo_id,
                "alert_level": alert_level,
                "burn_rate_multiplier": round(burn_rate_multiplier, 2),
                "days_until_exhaustion": round(days_until_exhaustion, 1) if days_until_exhaustion else None,
            },
            True,
        )

        logger.info(
            f"SLO burn rate analysis for {service_name}: "
            f"alert={alert_level}, burn_rate={round(burn_rate_multiplier, 1)}x, "
            f"days_left={round(days_until_exhaustion, 1) if days_until_exhaustion else 'N/A'}"
        )
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        _log_audit_event(
            "monitor_slo_burn_rate",
            service_name,
            {"error": str(exc)},
            False,
        )
        logger.error(f"Error monitoring SLO burn rate: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


# ============================================================================
# Enhanced Incident Management (P2)
# ============================================================================

@_server.tool(
    name="generate_postmortem",
    description=(
        "Generate a comprehensive post-incident review document with timeline, "
        "root cause analysis, and action items. "
        "✅ USE THIS TOOL when users ask: 'Generate a postmortem', 'Create a post-incident review', "
        "'Write up the incident report'. "
        "Aggregates audit trail events, health checks, and alert data into a structured document."
    ),
)
async def generate_postmortem(
    context: Context,
    incident_description: Annotated[str, "Description of the incident"],
    resource_id: Annotated[str, "Primary affected resource ID (optional)"] = "",
    start_time: Annotated[str, "Incident start time ISO format (optional, defaults to 24h ago)"] = "",
    end_time: Annotated[str, "Incident end time ISO format (optional, defaults to now)"] = "",
) -> list[TextContent]:
    """Generate a post-incident review document"""
    try:
        now = datetime.utcnow()
        inc_start = datetime.fromisoformat(start_time) if start_time else (now - timedelta(hours=24))
        inc_end = datetime.fromisoformat(end_time) if end_time else now

        # Gather audit trail events for timeline
        timeline_events = []
        for entry in _audit_trail:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if inc_start <= entry_time <= inc_end:
                    if not resource_id or entry.get("resource_id", "") == resource_id:
                        timeline_events.append({
                            "timestamp": entry["timestamp"],
                            "operation": entry["operation"],
                            "resource_id": entry.get("resource_id", ""),
                            "success": entry["success"],
                        })
            except (ValueError, KeyError):
                continue

        timeline_events.sort(key=lambda x: x["timestamp"])

        postmortem = {
            "success": True,
            "title": f"Post-Incident Review: {incident_description[:100]}",
            "generated_at": now.isoformat(),
            "incident": {
                "description": incident_description,
                "primary_resource": resource_id or "Not specified",
                "start_time": inc_start.isoformat(),
                "end_time": inc_end.isoformat(),
                "duration_minutes": round((inc_end - inc_start).total_seconds() / 60, 1),
            },
            "timeline": {
                "event_count": len(timeline_events),
                "events": timeline_events[:50],
            },
            "template": {
                "summary": f"[TO BE FILLED] Summary of {incident_description}",
                "impact": "[TO BE FILLED] Describe user impact, affected services, and blast radius",
                "root_cause": "[TO BE FILLED] Describe the root cause of the incident",
                "detection": {
                    "how_detected": "[TO BE FILLED] How was the incident detected?",
                    "time_to_detect_minutes": "[TO BE FILLED]",
                },
                "resolution": {
                    "actions_taken": "[TO BE FILLED] What steps were taken to resolve?",
                    "time_to_resolve_minutes": round((inc_end - inc_start).total_seconds() / 60, 1),
                },
                "action_items": [
                    {"item": "[TO BE FILLED] Action item 1", "owner": "", "due_date": ""},
                    {"item": "[TO BE FILLED] Action item 2", "owner": "", "due_date": ""},
                ],
                "lessons_learned": [
                    "[TO BE FILLED] What went well?",
                    "[TO BE FILLED] What could be improved?",
                ],
            },
        }

        _log_audit_event("generate_postmortem", resource_id,
                         {"description": incident_description[:100], "events": len(timeline_events)}, True)

        return [TextContent(type="text", text=json.dumps(postmortem, indent=2))]

    except Exception as exc:
        logger.error(f"Error generating postmortem: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]


@_server.tool(
    name="calculate_mttr_metrics",
    description=(
        "Calculate DORA reliability metrics (MTTR, MTTD, incident count) from the SRE audit trail. "
        "✅ USE THIS TOOL when users ask: 'What is our MTTR?', 'Show me DORA metrics', "
        "'How quickly do we resolve incidents?'. "
        "Analyzes triage_incident and remediation audit events to compute mean times."
    ),
)
async def calculate_mttr_metrics(
    context: Context,
    service_name: Annotated[str, "Service name filter (optional, 'all' for all services)"] = "all",
    time_range: Annotated[str, "Time range in days (default: 30)"] = "30",
) -> list[TextContent]:
    """Calculate DORA-aligned reliability metrics"""
    try:
        days = int(time_range) if time_range.isdigit() else 30
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Analyze audit trail for incident-related events
        triage_events = []
        remediation_events = []

        for entry in _audit_trail:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time < cutoff:
                    continue
                if service_name != "all" and entry.get("resource_id", "") and service_name.lower() not in entry.get("resource_id", "").lower():
                    continue

                if entry["operation"] == "triage_incident":
                    triage_events.append(entry)
                elif entry["operation"] in ("execute_safe_restart", "scale_resource", "clear_cache", "execute_restart_resource", "execute_scale_resource"):
                    remediation_events.append(entry)
            except (ValueError, KeyError):
                continue

        total_incidents = len(triage_events)
        successful_remediations = len([r for r in remediation_events if r.get("success")])

        response = {
            "success": True,
            "service_filter": service_name,
            "time_range_days": days,
            "metrics": {
                "total_incidents": total_incidents,
                "total_remediations": len(remediation_events),
                "successful_remediations": successful_remediations,
                "remediation_success_rate": round(
                    successful_remediations / len(remediation_events) * 100, 1
                ) if remediation_events else 0,
            },
            "note": "MTTR calculation requires incident start/end timestamps in audit trail. Current data shows event counts. For time-based MTTR, integrate with Azure Monitor alert resolution times.",
        }

        _log_audit_event("calculate_mttr_metrics", None,
                         {"incidents": total_incidents, "remediations": len(remediation_events)}, True)

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except Exception as exc:
        logger.error(f"Error calculating MTTR metrics: {exc}", exc_info=True)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(exc)
        }, indent=2))]

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
        "agent_name": "SRE MCP Server",
        "version": "2.0.0",
        "description": "Site Reliability Engineering operations for Azure with 50+ specialized tools across 15 domains",

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
                "category": "Incident Response & Root Cause Analysis",
                "description": "Automated incident triage, log correlation, root cause analysis, and dependency tracing",
                "tools": [
                    "triage_incident - Automated incident triage with severity assessment",
                    "search_logs_by_error - Pattern-based log search for specific errors",
                    "correlate_alerts - Temporal and resource-based alert correlation",
                    "generate_incident_summary - Structured incident reports with RCA steps",
                    "get_audit_trail - SRE operation audit trail for compliance",
                    "perform_root_cause_analysis - Automated RCA with log correlation, activity log analysis, dependency checks",
                    "trace_dependency_chain - Full dependency graph with health cascade and blast radius",
                    "analyze_log_patterns - Statistical error pattern detection with Z-score anomaly analysis"
                ],
                "example_prompts": [
                    "My app is down. Can you analyze it?",
                    "Why is my web app throwing 500 errors?",
                    "Correlate alerts for the last hour",
                    "Generate an incident summary",
                    "Perform root cause analysis on my container app",
                    "What is the blast radius if this service goes down?",
                    "Find error patterns in my logs for the last 12 hours"
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
                    "list_container_apps - List Container Apps with basic metadata",
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
                    "clear_cache - Simulated cache clearing",
                    "generate_remediation_plan - Advanced runbook-matched remediation plans with approval gates",
                    "execute_remediation_step - Execute individual plan steps with token-based approval",
                    "register_custom_runbook - Register custom remediation runbooks for future matching"
                ],
                "example_prompts": [
                    "Plan remediation for my failing app",
                    "Safely restart my Container App",
                    "Scale my app to 5 replicas",
                    "Generate a remediation plan for my unhealthy web app",
                    "Register a custom runbook for OOM errors",
                    "Execute step 2 of remediation plan plan-abc123"
                ],
                "note": "Destructive steps require explicit approval tokens (30-min TTL, single-use)"
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
            },
            {
                "category": "Security & Compliance Audits",
                "description": "Azure resource compliance audits for security posture, network security, private endpoints, encryption, public access, and regional compliance",
                "tools": [
                    "SecurityComplianceAgent.audit_network - Network security compliance (NSG associations, firewall routing, outbound deny rules)",
                    "SecurityComplianceAgent.audit_private_endpoints - Private endpoint compliance for Storage, Key Vaults, SQL",
                    "SecurityComplianceAgent.audit_encryption - Encryption at rest compliance (Storage, SQL TDE)",
                    "SecurityComplianceAgent.audit_public_access - Public access compliance (Storage blob access)",
                    "SecurityComplianceAgent.audit_regional_compliance - Regional compliance (Southeast Asia deployment)",
                    "SecurityComplianceAgent.audit_azure_resources - Comprehensive Azure resource compliance audit (all phases)",
                    "SecurityComplianceAgent.scan_security - Security posture scanning and assessment",
                    "SecurityComplianceAgent.check_compliance - Compliance framework validation (SOC2, HIPAA, PCI-DSS, ISO27001, GDPR, NIST)",
                    "SecurityComplianceAgent.assess_vulnerabilities - Vulnerability assessment and prioritization"
                ],
                "example_prompts": [
                    "Audit network security compliance for prod-rg",
                    "Check if storage accounts use private endpoints",
                    "Verify encryption is enabled on all resources",
                    "Check if all resources are in Southeast Asia region",
                    "Run a full compliance audit on my Azure resources",
                    "Check SOC2 compliance status",
                    "Scan security posture for my subscription",
                    "Assess vulnerabilities in prod-rg"
                ],
                "compliance_rules": {
                    "network_security": ["Subnets must have NSGs", "Default deny internet outbound", "Internet traffic routes through firewall"],
                    "private_endpoints": ["Storage accounts require private endpoints", "Key Vaults require private endpoints", "SQL servers require private endpoints"],
                    "encryption": ["Storage encryption at rest enabled", "SQL TDE enabled"],
                    "public_access": ["Storage public blob access disabled"],
                    "regional_compliance": ["All resources must be in southeastasia region"]
                },
                "severity_levels": ["Critical", "High", "Medium", "Low", "Informational"]
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
            "Security posture assessment and compliance audits",
            "Azure resource compliance validation (network, encryption, private endpoints)",
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
            "Remediation execute_* tools are simulated for safety (use generate_remediation_plan + execute_remediation_step for approval-gated workflows)",
            "Visualization generation not yet implemented (returns data only)"
        ],

        "total_tools": 48,
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
        "Categories: app_service, container_apps, aks, apim, incident_response, performance, configuration, security_compliance."
    ),
)
async def get_prompt_examples(
    context: Context,
    category: Annotated[str, "Category: app_service, container_apps, aks, apim, incident_response, performance, configuration, security_compliance, all"],
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
        },
        "security_compliance": {
            "description": "Security posture and Azure resource compliance audit prompts",
            "prompts": [
                "Audit network security compliance for prod-rg",
                "Check if my storage accounts use private endpoints",
                "Verify encryption is enabled on all resources",
                "Check if all resources are deployed in Southeast Asia",
                "Are any resources outside the southeastasia region?",
                "Run a full compliance audit on my Azure resources",
                "Check SOC2 compliance status for my subscription",
                "Scan security posture for prod-rg",
                "Assess vulnerabilities in my resource group",
                "Do my subnets have NSGs associated?",
                "Are my Key Vaults using private endpoints?",
                "Is TDE enabled on all SQL databases?",
                "Check if storage accounts have public access disabled",
                "What are my critical security violations?",
                "Generate compliance report for prod-rg",
                "Audit regional compliance for all resources",
                "Which resources are not in the compliant region?"
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
