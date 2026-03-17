"""Tool manifests for Azure MCP server tools.

Seeded from _TOOL_DISAMBIGUATION in the former mcp_composite_client module and
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
        # Phase 3 metadata
        primary_phrasings=(
            "list my Azure subscriptions",
            "show all subscriptions",
            "what subscriptions do I have access to",
            "which Azure subscriptions are available",
            "show me my subscription IDs",
            "list subscriptions I can manage",
            "what Azure accounts do I have",
            "enumerate all subscriptions",
        ),
        avoid_phrasings=(
            "show role assignments",          # → role (RBAC management, not subscriptions)
            "deploy my application with azd", # → azd (developer CLI deployment)
            "list resource groups",           # → groups (resource group listing)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("role", "azd"),
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
        # Phase 3 metadata
        primary_phrasings=(
            "show role assignments in subscription",
            "list Azure RBAC permissions",
            "who has contributor access to my resources",
            "what permissions does this user have",
            "show IAM role definitions",
            "list access control assignments",
            "which users have owner role",
            "check user permissions on resource group",
        ),
        avoid_phrasings=(
            "list my Azure subscriptions",    # → subscriptions (account listing)
            "list resource groups",           # → groups
            "show subscription IDs",          # → subscriptions
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "list all resource groups",
            "show resource groups in my subscription",
            "what resource groups do I have",
            "enumerate resource groups",
            "which resource groups exist in this subscription",
            "show me all RGs",
            "list resource group names and locations",
            "what Azure resource groups are available",
        ),
        avoid_phrasings=(
            "list my subscriptions",          # → subscriptions (not RGs)
            "list all VMs in resource group", # → virtual_machines (compute resources in RG)
            "list resources in resource group", # → more specific tool by resource type
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Azure Developer CLI ----
    ToolManifest(
        tool_name="azd",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"azd", "developer", "deploy"}),
        affordance=ToolAffordance.DEPLOY,
        example_queries=(
            "deploy my application with Azure Developer CLI",
            "provision Azure resources using azd",
            "manage my azd deployment pipelines",
        ),
        conflicts_with=frozenset({"subscriptions", "groups"}),
        conflict_note=(
            "azd is for Azure Developer CLI (developer workflows: provision, deploy, manage). "
            "NOT for listing subscriptions (use 'subscriptions') or resource groups (use 'groups')."
        ),
        preferred_over=frozenset(),
        requires_confirmation=True,  # DEPLOY affordance requires explicit user confirmation
        # Phase 3 metadata
        primary_phrasings=(
            "deploy with Azure Developer CLI",
            "provision infrastructure using azd",
            "run azd up to deploy my app",
            "use azd to manage my deployment environment",
            "set up developer environment with azd",
            "deploy application template with azd",
            "azd provision and deploy",
        ),
        avoid_phrasings=(
            "list my subscriptions",          # → subscriptions
            "list resource groups",           # → groups
            "deploy ARM template",            # → azure_deploy (ARM/Bicep templates)
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "find Azure documentation for this service",
            "show Microsoft Learn articles about AKS",
            "get code samples for Azure Functions",
            "look up Azure best practices documentation",
            "find MS docs for Cosmos DB",
            "show Azure architecture guidance",
            "get quickstart documentation for Azure Storage",
            "find Azure SDK examples and tutorials",
        ),
        avoid_phrasings=(
            "list my Azure resources",        # → subscriptions/groups/specific resource tools
            "show Azure resource health",     # → resourcehealth or check_resource_health
            "configure Azure Monitor",        # → monitor (resource management, not docs)
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Container Services Disambiguation ----
    ToolManifest(
        tool_name="container_registries",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"acr", "container", "registry"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all container registries in my subscription",
            "show ACR repositories and container images",
            "what container registries do I have in Azure",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "container_registries is for Azure Container REGISTRY (ACR). "
            "NOT for Azure Container Apps — use azure_cli_execute_command with 'az containerapp' for Container Apps."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list container registries",
            "show ACR repositories",
            "what container registries do I have",
            "list Azure Container Registry instances",
            "show Docker image repositories in ACR",
            "list all ACR resources in subscription",
            "show container registry images and tags",
        ),
        avoid_phrasings=(
            "list container apps",            # → container_app_list (Container Apps, not ACR)
            "check container app health",     # → check_container_app_health
            "show AKS clusters",              # → virtual_machines or azure_cli_execute_command
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    ToolManifest(
        tool_name="app_service",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"webapp", "appservice"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all app services in my subscription",
            "show web apps running on app service plans",
            "what Azure web apps do I have deployed",
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
            "list all function apps in my subscription",
            "show Azure Functions serverless resources",
            "what function apps do I have deployed currently",
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
            "list all app configuration stores in subscription",
            "show feature flags and configuration settings",
            "what Azure App Configuration stores do I have",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "app_configuration is for Azure App CONFIGURATION stores. "
            "NOT for Azure Container Apps."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list App Configuration stores",
            "show Azure App Configuration resources",
            "what App Configuration stores do I have",
            "show feature flags in App Configuration",
            "list configuration key-value stores",
            "show Azure App Config stores in subscription",
            "what feature flag stores are deployed",
        ),
        avoid_phrasings=(
            "list container apps",                # → container_app_list
            "configure Azure Monitor",            # → monitor
            "show app service configuration",     # → app_service (App Service settings, not App Config)
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "is there an Azure outage",
            "check Azure platform health status",
            "show resource availability status",
            "is my Azure region experiencing issues",
            "check service health advisory for my subscription",
            "show planned maintenance events",
            "what Azure services are impacted by outages",
            "check Azure service health",
        ),
        avoid_phrasings=(
            "diagnose my container app health",   # → check_container_app_health (deep SRE)
            "triage incident for resource",       # → triage_incident (SRE workflow)
            "get resource performance metrics",   # → get_performance_metrics (SRE)
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Monitor configuration ----
    ToolManifest(
        tool_name="monitor",
        source="azure",
        domains=frozenset({"azure_management", "observability"}),
        tags=frozenset({"monitor", "alerts", "diagnostics"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "configure Azure Monitor for my resources",
            "set up diagnostic settings and alerts",
            "manage Azure Monitor configuration settings",
        ),
        conflicts_with=frozenset({"get_service_monitor_resources", "get_performance_metrics"}),
        conflict_note=(
            "monitor (Azure MCP) configures Azure Monitor resources. "
            "For Monitor Community workbooks/alerts use monitor_agent or get_service_monitor_resources. "
            "For performance metrics use SRE: get_performance_metrics."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "configure Azure Monitor",
            "set up diagnostic settings for my resources",
            "manage alert rules in Azure Monitor",
            "create Azure Monitor workspace",
            "configure Log Analytics workspace",
            "set up Azure Monitor alerts",
            "manage diagnostic settings and activity logs",
        ),
        avoid_phrasings=(
            "get performance metrics for my app",   # → get_performance_metrics (SRE)
            "search Monitor community workbooks",   # → search_categories (monitor agent)
            "get resource monitoring data",         # → get_performance_metrics (SRE)
        ),
        confidence_boost=1.05,  # Generic config tool; low boost to defer to specific SRE tools
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "configure Application Insights resource",
            "create new Application Insights instance",
            "manage Application Insights settings",
            "set up Application Insights for my app",
            "list Application Insights resources",
            "show Application Insights instrumentation keys",
        ),
        avoid_phrasings=(
            "query application insights traces",     # → query_app_insights_traces (SRE data query)
            "get request telemetry from app insights", # → get_request_telemetry (SRE)
            "show app performance traces",           # → query_app_insights_traces
        ),
        confidence_boost=1.05,  # Config tool; low boost to defer to SRE query tools
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Compute ----
    ToolManifest(
        tool_name="virtual_machines",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"vm", "compute", "iaas"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all virtual machines in subscription",
            "show VMs running in my resource groups",
            "what virtual machines do I have deployed",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list all virtual machines in subscription",
            "show VMs running in my Azure environment",
            "what VMs do I have deployed",
            "list Azure IaaS compute instances",
            "show virtual machine names and sizes",
            "enumerate all VMs across resource groups",
            "list running and stopped virtual machines",
            "show compute resources in my subscription",
        ),
        avoid_phrasings=(
            "list container apps",                  # → container_app_list
            "list AKS clusters",                    # → azure_cli_execute_command with az aks
            "check VM health",                      # → check_resource_health (SRE)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Storage Disambiguation ----
    ToolManifest(
        tool_name="storage",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"storage", "blobs", "accounts"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all storage accounts in my subscription",
            "show Azure Storage resources and blob containers",
            "what storage accounts do I have deployed",
        ),
        conflicts_with=frozenset({"fileshares", "storagesync"}),
        conflict_note=(
            "storage is for Azure Storage Accounts (general). "
            "For specific file shares: use 'fileshares'. "
            "For Azure File Sync: use 'storagesync'."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list all storage accounts",
            "show Azure Storage resources",
            "what storage accounts do I have",
            "list blob storage containers",
            "show storage account names and tiers",
            "enumerate storage accounts in subscription",
            "show Azure Blob Storage resources",
            "list storage accounts and their SKUs",
        ),
        avoid_phrasings=(
            "list Azure file shares",           # → fileshares (Azure Files specifically)
            "show SMB file shares",             # → fileshares
            "list storage account queues",      # use azure_cli_execute_command for queue-level ops
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    ToolManifest(
        tool_name="fileshares",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"storage", "fileshare", "smb", "nfs"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all Azure File Shares in subscription",
            "show SMB and NFS file shares available",
            "what Azure Files resources do I have",
        ),
        conflicts_with=frozenset({"storage"}),
        conflict_note=(
            "fileshares is for Azure Files (SMB/NFS file shares). "
            "For general storage accounts: use 'storage'."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list Azure file shares",
            "show SMB and NFS file shares",
            "what Azure Files resources do I have",
            "list all file shares in storage accounts",
            "show Azure Files NFS shares",
            "enumerate Azure Files SMB shares",
            "list file shares and their quotas",
        ),
        avoid_phrasings=(
            "list all storage accounts",       # → storage (general storage, not just file shares)
            "list blob containers",            # → storage (blob-specific ops, not file shares)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    # ---- Search / AI Disambiguation ----
    ToolManifest(
        tool_name="search",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"cognitive_search", "search_service"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "manage my Azure Cognitive Search services",
            "list all search services in subscription",
            "show Azure AI Search resources available",
        ),
        conflicts_with=frozenset({"search_logs_by_error", "search_categories"}),
        conflict_note=(
            "search is Azure COGNITIVE SEARCH service management, NOT general search. "
            "For searching logs: use search_logs_by_error (SRE). "
            "For searching Monitor community resources: use search_categories."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list Azure Cognitive Search services",
            "show Azure AI Search resources",
            "manage my search service indexes",
            "list search service instances in subscription",
            "show Azure AI Search service names and tiers",
            "configure Azure Cognitive Search",
        ),
        avoid_phrasings=(
            "search logs for errors",           # → search_logs_by_error (SRE log search)
            "search for monitor workbooks",     # → search_categories (monitor community search)
            "find resources in my subscription", # → groups or specific resource tool
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "manage Azure Speech Services",
            "configure speech-to-text service",
            "list Azure AI Speech resources",
            "set up Azure Cognitive Speech service",
            "show speech recognition service configuration",
            "manage text-to-speech resources in Azure",
        ),
        avoid_phrasings=(
            "check resource health",            # → resourcehealth or check_resource_health (not speech)
            "show Azure outage status",         # → resourcehealth
            "diagnose application issues",      # → diagnose_app_service or triage_incident
        ),
        confidence_boost=1.4,  # Highly specialized — prevent misrouting
        requires_sequence=None,
        preferred_over_list=(),
    ),
    ToolManifest(
        tool_name="foundry",
        source="azure",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"ai_foundry", "ai_services"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "manage my Azure AI Foundry projects",
            "list all AI Foundry projects in subscription",
            "show Azure AI Foundry resources available",
        ),
        conflicts_with=frozenset({"speech"}),
        conflict_note=(
            "foundry is for Azure AI Foundry project management. "
            "NOT for Azure AI Speech Services (use 'speech' tool for that)."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "manage Azure AI Foundry projects",
            "list AI Foundry hubs and projects",
            "show Azure AI Foundry resources",
            "what AI Foundry deployments do I have",
            "list AI model deployments in Foundry",
            "show Azure AI Foundry project configuration",
            "enumerate AI Foundry resources in subscription",
        ),
        avoid_phrasings=(
            "manage Azure Speech Services",     # → speech (audio AI, not Foundry)
            "configure Application Insights",   # → applicationinsights
            "list AI models",                   # → foundry is project-level, not model-level
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "deploy ARM template to Azure",
            "deploy Bicep template to resource group",
            "run Azure infrastructure deployment",
            "provision resources using ARM template",
            "deploy infrastructure as code template",
            "create resources from Bicep file",
        ),
        avoid_phrasings=(
            "deploy application with azd",      # → azd or azure_developer_cli (developer workflow)
            "validate Bicep template syntax",   # → azure_bicep_schema (validation only)
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "run azd deploy for my project",
            "provision using Azure Developer CLI",
            "use azd to set up full-stack deployment",
            "run azure developer cli provision",
            "azd up for my application template",
            "deploy developer template with azd",
        ),
        avoid_phrasings=(
            "deploy ARM template",              # → azure_deploy (template deployment)
            "validate Bicep schema",            # → azure_bicep_schema
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    ToolManifest(
        tool_name="azure_bicep_schema",
        source="azure",
        domains=frozenset({"deployment"}),
        tags=frozenset({"bicep", "schema", "validation"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "validate my Bicep template syntax",
            "get the Bicep schema definition",
            "check Bicep template for errors",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "validate Bicep template syntax",
            "get Bicep schema definition",
            "check Bicep template for errors",
            "verify my Bicep file is valid",
            "show Bicep resource type schema",
            "get allowed properties for Bicep resource type",
        ),
        avoid_phrasings=(
            "deploy Bicep template",            # → azure_deploy (actual deployment)
            "deploy ARM template",              # → azure_deploy
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
    ),
]
