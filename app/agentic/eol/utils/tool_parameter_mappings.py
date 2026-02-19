"""Tool Parameter Mappings for Resource Inventory Integration.

Maps SRE MCP tool names to their parameter requirements and defines how
parameters can be auto-populated from the resource inventory cache.

This module enables the SRE Orchestrator to:
1. Know which parameters each tool requires
2. Resolve parameters from inventory (resource_id, subscription_id, etc.)
3. Determine which resource types are relevant per tool
4. Provide helpful guidance when parameters are missing

Usage:
    from utils.tool_parameter_mappings import (
        TOOL_PARAMETER_MAPPINGS,
        get_tool_mapping,
        get_inventory_populatable_params,
        get_required_params_for_tool,
        get_resource_types_for_tool,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class ParameterMapping:
    """Defines how a single parameter can be resolved.

    Attributes:
        name: Parameter name as expected by the MCP tool.
        required: Whether the tool will fail without this parameter.
        inventory_field: Dot-path into an inventory resource record that can
            supply this value (e.g. "id", "location", "properties.vmSize").
            ``None`` means the parameter cannot come from inventory.
        env_var: Environment variable fallback (checked when neither the
            request nor inventory supplies a value).
        description: Human-readable hint shown when the param is missing.
        default: Optional default value when nothing else resolves.
    """

    name: str
    required: bool = True
    inventory_field: Optional[str] = None
    env_var: Optional[str] = None
    description: str = ""
    default: Optional[Any] = None


@dataclass(frozen=True)
class ToolMapping:
    """Complete parameter mapping for one MCP tool.

    Attributes:
        tool_name: Exact MCP tool name (matches sre_mcp_server registration).
        category: Logical grouping (health, incident, performance, …).
        parameters: Ordered list of parameter mappings.
        resource_types: Azure resource types this tool applies to.  The
            orchestrator uses this to filter inventory when discovering
            resources automatically.  An empty list means the tool is
            resource-type agnostic (e.g. cost analysis at subscription scope).
        description: Short description of the tool for orchestrator routing.
        requires_confirmation: If True, the tool requires ``confirmed=true``
            before executing (remediation tools).
    """

    tool_name: str
    category: str
    parameters: List[ParameterMapping] = field(default_factory=list)
    resource_types: List[str] = field(default_factory=list)
    description: str = ""
    requires_confirmation: bool = False


# ---------------------------------------------------------------------------
# Common parameter definitions (reused across tools)
# ---------------------------------------------------------------------------

_RESOURCE_ID = ParameterMapping(
    name="resource_id",
    required=True,
    inventory_field="id",
    description="Full Azure resource ID (auto-resolved from inventory)",
)

_SUBSCRIPTION_ID = ParameterMapping(
    name="subscription_id",
    required=False,
    inventory_field="subscription_id",
    env_var="AZURE_SUBSCRIPTION_ID",
    description="Azure subscription ID",
)

_SUBSCRIPTION_ID_REQUIRED = ParameterMapping(
    name="subscription_id",
    required=True,
    inventory_field="subscription_id",
    env_var="AZURE_SUBSCRIPTION_ID",
    description="Azure subscription ID (required)",
)

_WORKSPACE_ID = ParameterMapping(
    name="workspace_id",
    required=True,
    inventory_field=None,
    env_var="LOG_ANALYTICS_WORKSPACE_ID",
    description="Log Analytics workspace ID",
)

_WORKSPACE_ID_OPTIONAL = ParameterMapping(
    name="workspace_id",
    required=False,
    inventory_field=None,
    env_var="LOG_ANALYTICS_WORKSPACE_ID",
    description="Log Analytics workspace ID (optional)",
)

_RESOURCE_GROUP = ParameterMapping(
    name="resource_group",
    required=False,
    inventory_field="resource_group",
    env_var="RESOURCE_GROUP_NAME",
    description="Azure resource group name",
)

_HOURS = ParameterMapping(
    name="hours",
    required=False,
    description="Hours to look back",
    default=24,
)

_SCOPE = ParameterMapping(
    name="scope",
    required=True,
    inventory_field=None,
    env_var="AZURE_SUBSCRIPTION_ID",
    description="Cost/compliance scope (subscription or resource group path)",
)


# ---------------------------------------------------------------------------
# Common resource type groups
# ---------------------------------------------------------------------------

_VM_TYPES = [
    "Microsoft.Compute/virtualMachines",
]

_APP_SERVICE_TYPES = [
    "Microsoft.Web/sites",
]

_CONTAINER_APP_TYPES = [
    "Microsoft.App/containerApps",
]

_AKS_TYPES = [
    "Microsoft.ContainerService/managedClusters",
]

_SQL_TYPES = [
    "Microsoft.Sql/servers",
    "Microsoft.Sql/servers/databases",
]

_STORAGE_TYPES = [
    "Microsoft.Storage/storageAccounts",
]

_APIM_TYPES = [
    "Microsoft.ApiManagement/service",
]

_NETWORK_TYPES = [
    "Microsoft.Network/virtualNetworks",
    "Microsoft.Network/loadBalancers",
    "Microsoft.Network/publicIPAddresses",
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Network/networkInterfaces",
]

# All resource types that support Resource Health API
_HEALTH_SUPPORTED_TYPES = (
    _VM_TYPES
    + _APP_SERVICE_TYPES
    + _SQL_TYPES
    + _STORAGE_TYPES
    + [
        "Microsoft.Network/loadBalancers",
        "Microsoft.Network/vpnGateways",
    ]
)

# All commonly monitored resource types
_ALL_COMMON_TYPES = (
    _VM_TYPES
    + _APP_SERVICE_TYPES
    + _CONTAINER_APP_TYPES
    + _AKS_TYPES
    + _SQL_TYPES
    + _STORAGE_TYPES
    + _APIM_TYPES
    + _NETWORK_TYPES
)


# ---------------------------------------------------------------------------
# TOOL_PARAMETER_MAPPINGS — the main registry
# ---------------------------------------------------------------------------

TOOL_PARAMETER_MAPPINGS: Dict[str, ToolMapping] = {}


def _register(*mappings: ToolMapping) -> None:
    """Register one or more tool mappings."""
    for m in mappings:
        TOOL_PARAMETER_MAPPINGS[m.tool_name] = m


# ---- Health & Diagnostics ------------------------------------------------

_register(
    ToolMapping(
        tool_name="check_resource_health",
        category="health",
        description="Check Azure resource health via Resource Health API",
        parameters=[_RESOURCE_ID],
        resource_types=_HEALTH_SUPPORTED_TYPES,
    ),
    ToolMapping(
        tool_name="check_container_app_health",
        category="health",
        description="Check Container App health via Log Analytics",
        parameters=[_WORKSPACE_ID, _RESOURCE_ID],
        resource_types=_CONTAINER_APP_TYPES,
    ),
    ToolMapping(
        tool_name="check_aks_cluster_health",
        category="health",
        description="Check AKS cluster health via Log Analytics",
        parameters=[_WORKSPACE_ID, _RESOURCE_ID],
        resource_types=_AKS_TYPES,
    ),
    ToolMapping(
        tool_name="get_diagnostic_logs",
        category="health",
        description="Retrieve diagnostic logs from Log Analytics",
        parameters=[
            _WORKSPACE_ID,
            _RESOURCE_ID,
            _HOURS,
            ParameterMapping(
                name="severity",
                required=False,
                description="Severity filter: Error, Warning, Informational, Verbose",
            ),
        ],
        resource_types=_ALL_COMMON_TYPES,
    ),
    ToolMapping(
        tool_name="diagnose_app_service",
        category="health",
        description="Comprehensive App Service diagnostics",
        parameters=[
            _RESOURCE_ID,
            _WORKSPACE_ID,
            ParameterMapping(name="check_deployment_logs", required=False, default=True,
                             description="Include Kudu deployment logs"),
            ParameterMapping(name="check_runtime_errors", required=False, default=True,
                             description="Include runtime error analysis"),
            _HOURS,
        ],
        resource_types=_APP_SERVICE_TYPES,
    ),
    ToolMapping(
        tool_name="diagnose_apim",
        category="health",
        description="Comprehensive API Management diagnostics",
        parameters=[
            _RESOURCE_ID,
            _WORKSPACE_ID,
            ParameterMapping(name="check_backend_health", required=False, default=True,
                             description="Include backend health analysis"),
            ParameterMapping(name="check_policy_errors", required=False, default=True,
                             description="Include policy error analysis"),
            _HOURS,
        ],
        resource_types=_APIM_TYPES,
    ),
    ToolMapping(
        tool_name="analyze_resource_configuration",
        category="health",
        description="Analyze resource config against best practices",
        parameters=[_RESOURCE_ID],
        resource_types=_ALL_COMMON_TYPES,
    ),
    ToolMapping(
        tool_name="get_resource_dependencies",
        category="health",
        description="Map resource dependencies via Resource Graph",
        parameters=[_RESOURCE_ID, _SUBSCRIPTION_ID],
        resource_types=_ALL_COMMON_TYPES,
    ),
)

# ---- Incident Response ---------------------------------------------------

_register(
    ToolMapping(
        tool_name="triage_incident",
        category="incident",
        description="Automated incident triage and initial assessment",
        parameters=[
            ParameterMapping(
                name="incident_title",
                required=True,
                description="Incident title or description",
            ),
            ParameterMapping(
                name="affected_resources",
                required=True,
                inventory_field="id",
                description="List of affected resource IDs (resolvable from inventory)",
            ),
            _WORKSPACE_ID_OPTIONAL,
        ],
        resource_types=_ALL_COMMON_TYPES,
    ),
    ToolMapping(
        tool_name="search_logs_by_error",
        category="incident",
        description="Search logs for specific error patterns",
        parameters=[
            _WORKSPACE_ID,
            ParameterMapping(
                name="error_pattern",
                required=True,
                description="Error message or pattern to search for",
            ),
            _HOURS,
        ],
        resource_types=[],  # Workspace-scoped, not resource-specific
    ),
    ToolMapping(
        tool_name="correlate_alerts",
        category="incident",
        description="Find related alerts in a time window",
        parameters=[
            _WORKSPACE_ID,
            ParameterMapping(name="start_time", required=True,
                             description="Start time (ISO format)"),
            ParameterMapping(name="end_time", required=True,
                             description="End time (ISO format)"),
            ParameterMapping(name="resource_id", required=False,
                             inventory_field="id",
                             description="Optional resource ID filter"),
        ],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="analyze_activity_log",
        category="incident",
        description="Analyze Activity Log for platform events",
        parameters=[
            _WORKSPACE_ID,
            ParameterMapping(name="resource_id", required=False,
                             inventory_field="id",
                             description="Optional resource ID filter"),
            _HOURS,
            ParameterMapping(name="operation_types", required=False,
                             description="Filter: Write, Delete, Action"),
        ],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="generate_incident_summary",
        category="incident",
        description="Generate structured incident summary report",
        parameters=[
            ParameterMapping(name="incident_title", required=True,
                             description="Incident title"),
            ParameterMapping(name="affected_resources", required=True,
                             inventory_field="id",
                             description="Affected resource IDs"),
            _WORKSPACE_ID_OPTIONAL,
        ],
        resource_types=_ALL_COMMON_TYPES,
    ),
)

# ---- Performance ---------------------------------------------------------

_register(
    ToolMapping(
        tool_name="get_performance_metrics",
        category="performance",
        description="Query Azure Monitor metrics for a resource",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="metric_names", required=False,
                             description="Metric names (auto-detected if omitted)"),
            ParameterMapping(name="hours", required=False, default=1,
                             description="Hours to look back"),
            ParameterMapping(name="aggregation", required=False, default="Average",
                             description="Average, Maximum, Minimum, Total"),
            ParameterMapping(name="aggregate_interval_minutes", required=False,
                             default=60, description="Bucket size in minutes"),
        ],
        resource_types=_ALL_COMMON_TYPES,
    ),
    ToolMapping(
        tool_name="identify_bottlenecks",
        category="performance",
        description="Identify performance bottlenecks and anomalies",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="hours", required=False, default=24,
                             description="Hours of metrics to analyze"),
        ],
        resource_types=_VM_TYPES + _APP_SERVICE_TYPES + _CONTAINER_APP_TYPES,
    ),
    ToolMapping(
        tool_name="get_capacity_recommendations",
        category="performance",
        description="Generate capacity and scaling recommendations",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="days", required=False, default=7,
                             description="Days of data to analyze"),
        ],
        resource_types=_VM_TYPES + _APP_SERVICE_TYPES + _CONTAINER_APP_TYPES,
    ),
    ToolMapping(
        tool_name="compare_baseline_metrics",
        category="performance",
        description="Compare current metrics against historical baseline",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="metric_name", required=True,
                             description="Metric to compare (e.g. 'Percentage CPU')"),
            ParameterMapping(name="baseline_days", required=False, default=7,
                             description="Days to use for baseline"),
        ],
        resource_types=_VM_TYPES + _APP_SERVICE_TYPES + _CONTAINER_APP_TYPES,
    ),
)

# ---- Cost Optimization ---------------------------------------------------

_register(
    ToolMapping(
        tool_name="get_cost_analysis",
        category="cost",
        description="Query Azure Cost Management for spending breakdown",
        parameters=[
            _SCOPE,
            ParameterMapping(name="time_range", required=False, default="last_30_days",
                             description="last_7_days, last_30_days, this_month, last_month"),
            ParameterMapping(name="group_by", required=False, default="ServiceName",
                             description="ResourceGroup, ServiceName, ResourceType, ResourceLocation"),
        ],
        resource_types=[],  # Subscription-scoped
    ),
    ToolMapping(
        tool_name="identify_orphaned_resources",
        category="cost",
        description="Find unused Azure resources (disks, IPs, NSGs, NICs)",
        parameters=[_SUBSCRIPTION_ID],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="get_cost_recommendations",
        category="cost",
        description="Get Azure Advisor cost optimization recommendations",
        parameters=[_SUBSCRIPTION_ID],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="analyze_cost_anomalies",
        category="cost",
        description="Detect cost spikes and unusual spending patterns",
        parameters=[_SUBSCRIPTION_ID],
        resource_types=[],
    ),
)

# ---- Remediation (all require confirmation) ------------------------------

_register(
    ToolMapping(
        tool_name="plan_remediation",
        category="remediation",
        description="Generate remediation plan with pre-checks and rollback",
        parameters=[
            ParameterMapping(name="issue_description", required=True,
                             description="Description of the issue"),
            _RESOURCE_ID,
            ParameterMapping(name="remediation_type", required=True,
                             description="restart, scale, clear_cache, or custom"),
        ],
        resource_types=_ALL_COMMON_TYPES,
        requires_confirmation=False,  # Planning doesn't need confirmation
    ),
    ToolMapping(
        tool_name="execute_safe_restart",
        category="remediation",
        description="Restart an Azure resource with pre-checks",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="confirmed", required=True, default=False,
                             description="Must be true to execute"),
        ],
        resource_types=_VM_TYPES + _APP_SERVICE_TYPES + _CONTAINER_APP_TYPES + _AKS_TYPES,
        requires_confirmation=True,
    ),
    ToolMapping(
        tool_name="scale_resource",
        category="remediation",
        description="Scale an Azure resource up or down",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="scale_direction", required=True,
                             description="Direction: up or down"),
            ParameterMapping(name="target_capacity", required=False,
                             description="Target capacity/instance count"),
            ParameterMapping(name="confirmed", required=True, default=False,
                             description="Must be true to execute"),
        ],
        resource_types=_VM_TYPES + _APP_SERVICE_TYPES + _CONTAINER_APP_TYPES + _AKS_TYPES,
        requires_confirmation=True,
    ),
    ToolMapping(
        tool_name="clear_cache",
        category="remediation",
        description="Clear application or service caches",
        parameters=[
            _RESOURCE_ID,
            ParameterMapping(name="confirmed", required=True, default=False,
                             description="Must be true to execute"),
        ],
        resource_types=_APP_SERVICE_TYPES + _CONTAINER_APP_TYPES,
        requires_confirmation=True,
    ),
)

# ---- SLO Management ------------------------------------------------------

_register(
    ToolMapping(
        tool_name="define_slo",
        category="slo",
        description="Define a Service Level Objective",
        parameters=[
            ParameterMapping(name="service_name", required=True,
                             description="Name of the service"),
            ParameterMapping(name="sli_type", required=True,
                             description="availability, latency, or error_rate"),
            ParameterMapping(name="target_percentage", required=True,
                             description="Target percentage (e.g. 99.9)"),
            ParameterMapping(name="window_days", required=False, default=30,
                             description="Measurement window in days"),
            _WORKSPACE_ID_OPTIONAL,
        ],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="calculate_error_budget",
        category="slo",
        description="Calculate remaining error budget vs SLO targets",
        parameters=[
            ParameterMapping(name="service_name", required=True,
                             description="Service name"),
            ParameterMapping(name="slo_id", required=False,
                             description="SLO definition ID"),
            ParameterMapping(name="time_range", required=False,
                             description="Override time range in days"),
        ],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="get_slo_dashboard",
        category="slo",
        description="Generate SLO compliance dashboard",
        parameters=[
            ParameterMapping(name="service_name", required=True,
                             description="Service name"),
        ],
        resource_types=[],
    ),
)

# ---- Security & Compliance -----------------------------------------------

_register(
    ToolMapping(
        tool_name="get_security_score",
        category="security",
        description="Get Defender for Cloud secure score",
        parameters=[_SUBSCRIPTION_ID],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="list_security_recommendations",
        category="security",
        description="List Defender for Cloud security recommendations",
        parameters=[
            _SUBSCRIPTION_ID,
            ParameterMapping(name="severity_filter", required=False,
                             description="High, Medium, or Low"),
        ],
        resource_types=[],
    ),
    ToolMapping(
        tool_name="check_compliance_status",
        category="security",
        description="Check Azure Policy compliance status",
        parameters=[
            _SCOPE,
            ParameterMapping(name="policy_definition_name", required=False,
                             description="Policy initiative name filter"),
        ],
        resource_types=[],
    ),
)

# ---- Configuration Discovery ---------------------------------------------

_register(
    ToolMapping(
        tool_name="query_app_service_configuration",
        category="config",
        description="Query App Service configuration across web apps",
        parameters=[_SUBSCRIPTION_ID, _RESOURCE_GROUP],
        resource_types=_APP_SERVICE_TYPES,
    ),
    ToolMapping(
        tool_name="query_container_app_configuration",
        category="config",
        description="Query Container Apps configuration",
        parameters=[_SUBSCRIPTION_ID, _RESOURCE_GROUP],
        resource_types=_CONTAINER_APP_TYPES,
    ),
    ToolMapping(
        tool_name="query_aks_configuration",
        category="config",
        description="Query AKS cluster configuration",
        parameters=[_SUBSCRIPTION_ID, _RESOURCE_GROUP],
        resource_types=_AKS_TYPES,
    ),
    ToolMapping(
        tool_name="query_apim_configuration",
        category="config",
        description="Query API Management configuration",
        parameters=[_SUBSCRIPTION_ID, _RESOURCE_GROUP],
        resource_types=_APIM_TYPES,
    ),
)


# ---------------------------------------------------------------------------
# Public helper functions
# ---------------------------------------------------------------------------

def get_tool_mapping(tool_name: str) -> Optional[ToolMapping]:
    """Return the mapping for a specific tool, or ``None`` if unregistered."""
    return TOOL_PARAMETER_MAPPINGS.get(tool_name)


def get_required_params_for_tool(tool_name: str) -> List[str]:
    """Return list of required parameter names for a tool."""
    mapping = get_tool_mapping(tool_name)
    if not mapping:
        return []
    return [p.name for p in mapping.parameters if p.required]


def get_inventory_populatable_params(tool_name: str) -> List[ParameterMapping]:
    """Return parameters that can be auto-populated from inventory."""
    mapping = get_tool_mapping(tool_name)
    if not mapping:
        return []
    return [p for p in mapping.parameters if p.inventory_field is not None]


def get_env_populatable_params(tool_name: str) -> List[ParameterMapping]:
    """Return parameters that can be resolved from environment variables."""
    mapping = get_tool_mapping(tool_name)
    if not mapping:
        return []
    return [p for p in mapping.parameters if p.env_var is not None]


def get_resource_types_for_tool(tool_name: str) -> List[str]:
    """Return Azure resource types applicable for a given tool.

    An empty list means the tool is resource-type agnostic (subscription-scoped).
    """
    mapping = get_tool_mapping(tool_name)
    if not mapping:
        return []
    return list(mapping.resource_types)


def get_tools_for_resource_type(resource_type: str) -> List[str]:
    """Return all tool names that apply to a given Azure resource type."""
    return [
        name
        for name, m in TOOL_PARAMETER_MAPPINGS.items()
        if resource_type in m.resource_types
    ]


def get_tools_by_category(category: str) -> List[str]:
    """Return all tool names belonging to a category."""
    return [
        name
        for name, m in TOOL_PARAMETER_MAPPINGS.items()
        if m.category == category
    ]


def get_all_categories() -> Set[str]:
    """Return all unique categories."""
    return {m.category for m in TOOL_PARAMETER_MAPPINGS.values()}


def get_confirmation_required_tools() -> List[str]:
    """Return tool names that require user confirmation before execution."""
    return [
        name
        for name, m in TOOL_PARAMETER_MAPPINGS.items()
        if m.requires_confirmation
    ]


def resolve_parameter_from_inventory(
    param: ParameterMapping,
    inventory_resource: Dict[str, Any],
) -> Optional[Any]:
    """Resolve a parameter value from an inventory resource record.

    Supports dot-path notation (e.g. ``"properties.vmSize"``).

    Args:
        param: The parameter mapping to resolve.
        inventory_resource: A resource record from the inventory cache.

    Returns:
        The resolved value, or ``None`` if the field is absent.
    """
    if not param.inventory_field:
        return None

    value: Any = inventory_resource
    for part in param.inventory_field.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def build_parameter_resolution_plan(
    tool_name: str,
    provided_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Analyse what can be resolved and what is still missing.

    Returns a dict with:
        - ``resolved``: params already provided.
        - ``from_inventory``: params that *can* come from inventory.
        - ``from_env``: params that *can* come from env vars.
        - ``missing``: required params not resolvable from any source.
        - ``optional_missing``: optional params not yet resolved.
    """
    mapping = get_tool_mapping(tool_name)
    if not mapping:
        return {
            "resolved": provided_params,
            "from_inventory": [],
            "from_env": [],
            "missing": [],
            "optional_missing": [],
        }

    resolved: List[str] = []
    from_inventory: List[str] = []
    from_env: List[str] = []
    missing: List[str] = []
    optional_missing: List[str] = []

    for param in mapping.parameters:
        if param.name in provided_params:
            resolved.append(param.name)
            continue

        # Check if inventory can supply it
        if param.inventory_field:
            from_inventory.append(param.name)
            continue

        # Check if env var can supply it
        if param.env_var:
            import os
            if os.getenv(param.env_var):
                from_env.append(param.name)
                continue

        # Check if there's a default
        if param.default is not None:
            resolved.append(param.name)
            continue

        # Parameter is unresolvable
        if param.required:
            missing.append(param.name)
        else:
            optional_missing.append(param.name)

    return {
        "resolved": resolved,
        "from_inventory": from_inventory,
        "from_env": from_env,
        "missing": missing,
        "optional_missing": optional_missing,
    }
