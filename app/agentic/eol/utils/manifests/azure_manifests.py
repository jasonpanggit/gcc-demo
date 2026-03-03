"""Tool manifests for Azure MCP server tools.

Seeded from _TOOL_DISAMBIGUATION in mcp_composite_client.py and
static/data/azure_mcp_tool_metadata.json.
"""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    # ---- Subscriptions / RBAC ----
    ToolManifest(
        tool_name="subscriptions",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"subscriptions", "account"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list my Azure subscriptions",
            "show subscriptions",
            "what subscriptions do I have",
        ),
        conflicts_with=frozenset({"role", "azd"}),
        conflict_note=(
            "subscriptions is the PRIMARY tool for listing Azure subscriptions. "
            "Do NOT use 'role' (RBAC) or 'azd' (developer CLI) to list subscriptions."
        ),
        preferred_over=frozenset({"role", "azd"}),
    ),
    ToolManifest(
        tool_name="role",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"rbac", "iam", "permissions"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show role assignments",
            "list permissions for user",
            "who has contributor access",
        ),
        conflicts_with=frozenset({"subscriptions"}),
        conflict_note=(
            "role is for Azure RBAC assignments and role definitions (IAM/identity). "
            "NOT for listing subscriptions — use the 'subscriptions' tool for that."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Resource groups ----
    ToolManifest(
        tool_name="groups",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"resource_groups", "rg"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list resource groups",
            "show all resource groups",
            "what resource groups do I have",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    # ---- Azure Developer CLI ----
    ToolManifest(
        tool_name="azd",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"azd", "developer", "deploy"}),
        affordance=ToolAffordance.DEPLOY,
        example_queries=(
            "deploy with Azure Developer CLI",
            "azd provision my environment",
            "manage azd pipelines",
        ),
        conflicts_with=frozenset({"subscriptions", "groups"}),
        conflict_note=(
            "azd is for Azure Developer CLI (developer workflows: provision, deploy, manage). "
            "NOT for listing subscriptions (use 'subscriptions') or resource groups (use 'groups')."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Documentation ----
    ToolManifest(
        tool_name="documentation",
        source="azure",
        domains=frozenset({"documentation"}),
        tags=frozenset({"docs", "learn", "samples"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "find documentation for Azure Functions",
            "show code samples for Cosmos DB",
            "MS Learn article about AKS",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "documentation fetches Microsoft Learn/Azure docs and code samples. "
            "NOT for Azure resource operations — only for looking up documentation."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Container Services Disambiguation ----
    ToolManifest(
        tool_name="container_registries",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"acr", "container", "registry"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list container registries",
            "show ACR repositories",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "container_registries is for Azure Container REGISTRY (ACR). "
            "NOT for Azure Container Apps — use azure_cli_execute_command with 'az containerapp' for Container Apps."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="app_service",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"webapp", "appservice"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list app services",
            "show web apps",
        ),
        conflicts_with=frozenset({"container_app_list", "function_app"}),
        conflict_note=(
            "app_service is for Azure App SERVICE (Web Apps on App Service Plans). "
            "NOT for Azure Container Apps — use container_app_list for those. "
            "NOT for Function Apps — use function_app for those."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list app services",
            "show web apps",
            "list Azure web apps on app service plan",
            "show App Service resources",
            "what app services do I have",
            "enumerate app service web apps",
            "show all web applications",
        ),
        avoid_phrasings=(
            "list container apps",               # → container_app_list (Container Apps, not App Service)
            "list function apps",                # → function_app
            "diagnose app service",              # → diagnose_app_service (SRE deep diagnostics)
            "app service health check",          # → diagnose_app_service
        ),
        confidence_boost=1.1,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="function_app",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"functions", "serverless"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list function apps",
            "show Azure Functions",
        ),
        conflicts_with=frozenset({"container_app_list", "app_service"}),
        conflict_note=(
            "function_app is for Azure FUNCTION Apps (serverless/consumption). "
            "NOT for Azure Container Apps — use container_app_list for those. "
            "NOT for App Service web apps — use app_service for those."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list function apps",
            "show Azure Functions",
            "what function apps do I have",
            "list serverless functions",
            "show Azure Functions resources",
            "enumerate function apps in subscription",
            "show all Azure Function Apps",
        ),
        avoid_phrasings=(
            "list container apps",               # → container_app_list
            "list app services",                 # → app_service
            "function app health check",         # → check_resource_health
        ),
        confidence_boost=1.1,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="app_configuration",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"configuration", "feature_flags"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list app configuration stores",
            "show feature flags",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "app_configuration is for Azure App CONFIGURATION stores. "
            "NOT for Azure Container Apps."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Resource Health ----
    ToolManifest(
        tool_name="resourcehealth",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"health", "availability", "platform"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check Azure platform health",
            "is there an Azure outage",
            "resource availability status",
        ),
        conflicts_with=frozenset({"check_resource_health"}),
        conflict_note=(
            "resourcehealth provides basic Azure platform availability status. "
            "For deeper SRE diagnostics (triage, remediation), use check_resource_health (SRE tool)."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Monitor configuration ----
    ToolManifest(
        tool_name="monitor",
        source="azure",
        domains=frozenset({"azure_management", "observability"}),
        tags=frozenset({"monitor", "alerts", "diagnostics"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "configure Azure Monitor",
            "set up diagnostic settings",
        ),
        conflicts_with=frozenset({"get_service_monitor_resources", "get_performance_metrics"}),
        conflict_note=(
            "monitor (Azure MCP) configures Azure Monitor resources. "
            "For Monitor Community workbooks/alerts use monitor_agent or get_service_monitor_resources. "
            "For performance metrics use SRE: get_performance_metrics."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="applicationinsights",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"appinsights", "configuration"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "configure Application Insights",
            "create Application Insights resource",
        ),
        conflicts_with=frozenset({"query_app_insights_traces", "get_request_telemetry"}),
        conflict_note=(
            "applicationinsights (Azure MCP) configures Application Insights resources. "
            "For retrieving traces/telemetry data use SRE: query_app_insights_traces, get_request_telemetry."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Compute ----
    ToolManifest(
        tool_name="virtual_machines",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"vm", "compute", "iaas"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list virtual machines",
            "show VMs in resource group",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    # ---- Storage Disambiguation ----
    ToolManifest(
        tool_name="storage",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"storage", "blobs", "accounts"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list storage accounts",
            "show Azure Storage resources",
        ),
        conflicts_with=frozenset({"fileshares", "storagesync"}),
        conflict_note=(
            "storage is for Azure Storage Accounts (general). "
            "For specific file shares: use 'fileshares'. "
            "For Azure File Sync: use 'storagesync'."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="fileshares",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"storage", "fileshare", "smb", "nfs"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list Azure File Shares",
            "show SMB file shares",
        ),
        conflicts_with=frozenset({"storage"}),
        conflict_note=(
            "fileshares is for Azure Files (SMB/NFS file shares). "
            "For general storage accounts: use 'storage'."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Search / AI Disambiguation ----
    ToolManifest(
        tool_name="search",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"cognitive_search", "search_service"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "manage Azure Cognitive Search",
            "list search services",
        ),
        conflicts_with=frozenset({"search_logs_by_error", "search_categories"}),
        conflict_note=(
            "search is Azure COGNITIVE SEARCH service management, NOT general search. "
            "For searching logs: use search_logs_by_error (SRE). "
            "For searching Monitor community resources: use search_categories."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="speech",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"speech", "ai_services", "audio"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "manage Azure Speech Services",
            "configure speech-to-text",
        ),
        conflicts_with=frozenset({"check_resource_health", "resourcehealth"}),
        conflict_note=(
            "CRITICAL: speech is Azure AI Services SPEECH tool (audio processing). "
            "NOT for Azure resource health, diagnostics, SRE operations, or infrastructure management. "
            "For resource health: use check_resource_health (SRE) or resourcehealth (Azure MCP)."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="foundry",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"ai_foundry", "ai_services"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "manage Azure AI Foundry",
            "list AI Foundry projects",
        ),
        conflicts_with=frozenset({"speech"}),
        conflict_note=(
            "foundry is for Azure AI Foundry project management. "
            "NOT for Azure AI Speech Services (use 'speech' tool for that)."
        ),
        preferred_over=frozenset(),
    ),
    # ---- Azure deploy tools ----
    ToolManifest(
        tool_name="azure_deploy",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"deploy", "arm", "bicep"}),
        affordance=ToolAffordance.DEPLOY,
        example_queries=(
            "deploy ARM template",
            "deploy Bicep template",
            "run Azure deployment",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
    ),
    ToolManifest(
        tool_name="azure_developer_cli",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"azd", "deploy", "provision"}),
        affordance=ToolAffordance.DEPLOY,
        example_queries=(
            "run azd deploy",
            "provision Azure Developer CLI project",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
    ),
    ToolManifest(
        tool_name="azure_bicep_schema",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"bicep", "schema", "validation"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "validate Bicep template",
            "get Bicep schema",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
]
