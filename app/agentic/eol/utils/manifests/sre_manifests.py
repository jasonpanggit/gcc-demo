"""Tool manifests for SRE MCP server tools.

Seeded from utils/sre_tool_registry.py domain lists and sre_mcp_server.py docstrings.

Tool name verification against sre_tool_registry.py _DOMAIN_TOOLS:
  HEALTH:       check_resource_health, check_container_app_health, check_aks_cluster_health,
                diagnose_app_service, diagnose_apim, analyze_resource_configuration,
                                get_diagnostic_logs, get_resource_dependencies, container_app_list,
                describe_capabilities
  INCIDENT:     triage_incident, search_logs_by_error, correlate_alerts, analyze_activity_log,
                generate_incident_summary, query_app_insights_traces, get_request_telemetry,
                get_audit_trail, describe_capabilities
  PERFORMANCE:  get_performance_metrics, identify_bottlenecks, detect_metric_anomalies,
                compare_baseline_metrics, analyze_dependency_map, predict_resource_exhaustion,
                detect_performance_anomalies, monitor_slo_burn_rate, describe_capabilities,
                define_slo, calculate_error_budget, get_slo_dashboard
  COST_SECURITY: get_cost_analysis, identify_orphaned_resources, get_cost_recommendations,
                analyze_cost_anomalies, get_security_score, list_security_recommendations,
                check_compliance_status, describe_capabilities, define_slo,
                calculate_error_budget, get_slo_dashboard
  RCA:          perform_root_cause_analysis, trace_dependency_chain, analyze_log_patterns,
                predict_capacity_issues, generate_postmortem, calculate_mttr_metrics,
                detect_performance_anomalies, describe_capabilities
  REMEDIATION:  plan_remediation, generate_remediation_plan, execute_safe_restart,
                scale_resource, clear_cache, execute_remediation_step,
                send_teams_notification, send_teams_alert, send_sre_status_update,
                describe_capabilities
"""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    # ---- Health ----
    ToolManifest(
        tool_name="check_resource_health",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "diagnostics", "resource"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check health of my container app",
            "is my VM healthy",
            "what is the health status of my AKS cluster",
        ),
        conflicts_with=frozenset({"resourcehealth"}),
        conflict_note=(
            "check_resource_health (SRE) provides deep diagnostics with remediation planning. "
            "resourcehealth (Azure MCP) provides basic platform availability only. "
            "Prefer check_resource_health for actionable SRE insights."
        ),
        preferred_over=frozenset({"resourcehealth"}),
        # Phase 3 metadata
        primary_phrasings=(
            "check health of my resource",
            "is my resource healthy",
            "health status of my service",
            "resource health check",
            "diagnose my Azure resource",
            "health diagnostics for my app",
            "what is wrong with my resource",
            "SRE health check",
            "is my service up",
            "run health check on my resource",
        ),
        avoid_phrasings=(
            "is there an Azure outage",          # → resourcehealth (platform status)
            "check container app health",        # → check_container_app_health (more specific)
            "check AKS cluster health",          # → check_aks_cluster_health (more specific)
            "list my resources",                 # → inventory tools
            "platform availability status",      # → resourcehealth
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("resourcehealth", "speech"),
    ),
    ToolManifest(
        tool_name="check_container_app_health",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "container", "containerapp"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check health of my container app prod-api",
            "is my container app running",
            "container app health status",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "check health of my container app",
            "container app health status",
            "is my container app healthy",
            "container app running status",
            "health check for container app",
            "container app diagnostics",
            "is my container app up",
            "why is my container app failing",
            "what is the health of my container apps",
            "diagnose container app failures",
        ),
        avoid_phrasings=(
            "list my container apps",            # → container_app_list
            "show all container apps",           # → container_app_list
            "restart container app",             # → execute_safe_restart
            "deploy container app",              # → azure_deploy
            "list container app replicas",       # → container_app_list
        ),
        confidence_boost=1.4,
        requires_sequence=("container_app_list",),
        preferred_over_list=("check_resource_health", "resourcehealth"),
    ),
    ToolManifest(
        tool_name="check_aks_cluster_health",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "aks", "kubernetes"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check AKS cluster health",
            "is my kubernetes cluster healthy",
            "AKS node pool status",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "check AKS cluster health",
            "is my kubernetes cluster healthy",
            "AKS node pool status",
            "Kubernetes cluster health check",
            "AKS health diagnostics",
            "check my K8s cluster",
            "are my AKS nodes healthy",
            "AKS cluster status",
            "AKS cluster operational status",
        ),
        avoid_phrasings=(
            "list AKS clusters",                 # → virtual_machine_list or azure MCP
            "scale AKS node pool",               # → scale_resource
            "upgrade AKS cluster",               # → write/deploy tool
            "deploy to AKS",                     # → azure_deploy
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("check_resource_health",),
    ),
    ToolManifest(
        tool_name="diagnose_app_service",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "appservice", "webapp"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "diagnose my app service",
            "why is my web app slow",
            "app service diagnostic logs",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "diagnose my app service",
            "why is my web app slow",
            "app service health check",
            "troubleshoot my web app",
            "why is my App Service failing",
            "app service diagnostic report",
            "check my web app health",
            "App Service deep diagnostics",
        ),
        avoid_phrasings=(
            "list app services",                 # → app_service (Azure MCP)
            "show all web apps",                 # → app_service (Azure MCP)
            "restart app service",               # → execute_safe_restart
            "scale app service plan",            # → scale_resource
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("app_service",),
    ),
    ToolManifest(
        tool_name="diagnose_apim",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "apim", "api_management"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "diagnose API Management",
            "why is my APIM gateway failing",
            "APIM health check",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "diagnose my API Management gateway",
            "why is my APIM failing",
            "APIM health check",
            "API Management gateway diagnostics",
            "troubleshoot APIM errors",
            "APIM gateway is returning errors",
            "check API Management health",
            "why are my APIM APIs failing",
            "APIM deep diagnostics",
        ),
        avoid_phrasings=(
            "list API Management instances",     # → azure MCP (resource listing)
            "configure APIM policies",           # → write/configuration tool
            "APIM developer portal",             # → unrelated
            "check app service health",          # → diagnose_app_service
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("check_resource_health",),
    ),
    ToolManifest(
        tool_name="analyze_resource_configuration",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"health", "configuration", "best_practices"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "analyze resource configuration",
            "check configuration best practices",
            "configuration review for my container app",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "analyze resource configuration",
            "check configuration best practices for my resource",
            "configuration review for my container app",
            "is my resource correctly configured",
            "configuration compliance check",
            "review my resource settings",
            "check if my resource follows best practices",
            "configuration analysis for my service",
            "analyze my Azure resource configuration",
        ),
        avoid_phrasings=(
            "check compliance policy",           # → check_compliance_status (policy compliance)
            "check resource health",             # → check_resource_health (health status)
            "show security recommendations",     # → list_security_recommendations
            "list resource properties",          # → azure MCP (raw resource listing)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("check_resource_health",),
    ),
    ToolManifest(
        tool_name="get_diagnostic_logs",
        source="sre",
        domains=frozenset({"sre_health", "sre_incident"}),
        tags=frozenset({"logs", "diagnostics"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show diagnostic logs",
            "get logs for my resource",
            "recent error logs",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show diagnostic logs",
            "get logs for my resource",
            "recent diagnostic logs",
            "show logs from my container app",
            "download diagnostic logs",
            "retrieve logs for troubleshooting",
            "get system diagnostic output",
            "fetch diagnostic logs from resource",
        ),
        avoid_phrasings=(
            "search logs for errors",            # → search_logs_by_error (error-targeted)
            "query Application Insights",        # → query_app_insights_traces
            "show audit trail",                  # → get_audit_trail
            "show activity log",                 # → analyze_activity_log
            "analyze log patterns",              # → analyze_log_patterns (RCA)
        ),
        confidence_boost=1.1,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="get_resource_dependencies",
        source="sre",
        domains=frozenset({"sre_health", "sre_rca"}),
        tags=frozenset({"dependencies", "topology", "rca"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "what does my container app depend on",
            "show resource dependencies",
            "dependency map for my VM",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "what does my resource depend on",
            "show resource dependencies",
            "what services does my container app depend on",
            "dependency list for my resource",
            "what are the dependencies of my app",
            "show downstream dependencies",
            "resource dependency graph",
            "what does my service call",
            "list dependencies for my Azure resource",
        ),
        avoid_phrasings=(
            "analyze dependency map",            # → analyze_dependency_map (full map analysis)
            "trace dependency chain",            # → trace_dependency_chain (RCA-focused)
            "show all resources",                # → inventory tools
            "service topology map",              # → analyze_dependency_map
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: analyze_dependency_map already prefers over get_resource_dependencies
    ),
    ToolManifest(
        tool_name="container_app_list",
        source="sre",
        domains=frozenset({"sre_health"}),
        tags=frozenset({"containerapp", "list", "inventory"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all container apps",
            "show my container apps",
            "what container apps are running",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset({"app_service", "function_app", "container_registries"}),
        # Phase 3 metadata
        primary_phrasings=(
            "list my container apps",
            "show all container apps",
            "what container apps do I have",
            "display container apps in subscription",
            "get all container apps in resource group",
            "show me my container apps",
            "list container apps in my environment",
            "enumerate container apps",
            "what container apps are running",
            "show container apps in my subscription",
        ),
        avoid_phrasings=(
            "check health of container apps",    # → check_container_app_health
            "restart container app",             # → execute_safe_restart
            "deploy container app",              # → azure_deploy
            "list container registries",         # → container_registries (ACR)
            "list app services",                 # → app_service (Web Apps)
            "what is the health of my container apps",  # → check_container_app_health
        ),
        confidence_boost=1.4,
        requires_sequence=None,
        preferred_over_list=("app_service", "function_app", "container_registries"),
    ),
    # ---- Incident ----
    ToolManifest(
        tool_name="triage_incident",
        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"incident", "triage", "alert"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "triage the incident for my API",
            "why is my service down",
            "investigate the alert",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "triage the incident",
            "why is my service down",
            "investigate this alert",
            "what caused the outage",
            "service is not responding",
            "my app is throwing 500 errors",
            "something is wrong with my service",
            "incident triage for my resource",
            "help me debug this production issue",
            "my service is experiencing errors",
        ),
        avoid_phrasings=(
            "perform root cause analysis",       # → perform_root_cause_analysis (deeper RCA)
            "generate postmortem",               # → generate_postmortem
            "correlate alerts",                  # → correlate_alerts
            "predict capacity issues",           # → predict_capacity_issues
        ),
        confidence_boost=1.2,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="search_logs_by_error",
        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"logs", "errors", "search"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show last 10 errors",
            "search logs for 502 errors",
            "find exception in logs",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset({"search"}),
        # Phase 3 metadata
        primary_phrasings=(
            "search logs for errors",
            "find error logs",
            "show recent exceptions",
            "search logs for 500 errors",
            "find 4xx errors in logs",
            "show error messages from my app",
            "search application logs for failures",
            "find exceptions in recent logs",
            "what errors have occurred",
            "show me recent error log entries",
        ),
        avoid_phrasings=(
            "search Azure Cognitive Search",     # → search (Azure MCP)
            "query Application Insights",        # → query_app_insights_traces
            "analyze log patterns",              # → analyze_log_patterns (RCA)
            "show audit trail",                  # → get_audit_trail
            "show all diagnostic logs",          # → get_diagnostic_logs
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("search",),
    ),
    ToolManifest(
        tool_name="correlate_alerts",
        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"alerts", "correlation", "incident"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "correlate my alerts",
            "which alerts are related",
            "alert correlation for my resource",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "correlate my alerts",
            "which alerts are related to each other",
            "group related alerts",
            "find root alert causing cascade",
            "alert correlation analysis",
            "cluster my firing alerts",
            "which alerts are connected",
            "show me correlated alerts",
            "identify alert storm root cause",
        ),
        avoid_phrasings=(
            "list all alerts",                   # → Azure MCP monitor or get_service_monitor_resources
            "configure alert rules",             # → monitor (Azure MCP) — configuration
            "triage the incident",               # → triage_incident (broader incident scope)
            "search for specific alert",         # → search_logs_by_error or Azure MCP
        ),
        confidence_boost=1.2,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="analyze_activity_log",
        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"activity", "audit", "incident"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show activity log for my resource",
            "what changed recently",
            "audit log analysis",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show activity log for my resource",
            "what changed recently in my subscription",
            "analyze activity logs",
            "who changed my resource",
            "show recent activity in my Azure environment",
            "activity log analysis for incident",
            "what operations were performed on my resource",
            "show Azure activity history",
            "recent changes in my resource group",
            "activity log review for my service",
        ),
        avoid_phrasings=(
            "show audit trail",                  # → get_audit_trail (audit-specific)
            "search logs for errors",            # → search_logs_by_error
            "show diagnostic logs",              # → get_diagnostic_logs
            "query Application Insights",        # → query_app_insights_traces
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("get_audit_trail",),
    ),
    ToolManifest(
        tool_name="generate_incident_summary",
        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"incident", "summary", "report"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "generate incident summary",
            "create incident report",
            "summarize the outage",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "generate incident summary",
            "create incident report",
            "summarize the outage",
            "write up the incident",
            "generate an incident report for stakeholders",
            "summarize what happened during the incident",
            "create a summary of the production incident",
            "incident summary for my service outage",
            "generate SRE incident write-up",
        ),
        avoid_phrasings=(
            "generate postmortem",               # → generate_postmortem (deeper RCA report)
            "triage the incident",               # → triage_incident (investigation phase)
            "perform root cause analysis",       # → perform_root_cause_analysis
            "send incident notification",        # → send_sre_status_update or send_teams_alert
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("generate_postmortem",),
    ),
    ToolManifest(
        tool_name="get_audit_trail",        source="sre",
        domains=frozenset({"sre_incident"}),
        tags=frozenset({"audit", "trail", "compliance", "incident"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show audit trail",
            "who made changes to my resource",
            "audit history for my subscription",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show audit trail",
            "who made changes to my resource",
            "audit history for my subscription",
            "show who accessed my resource",
            "get compliance audit trail",
            "audit log for my resource group",
            "show access history for my resource",
            "who deleted my resource",
            "security audit trail for my environment",
            "show historical changes for compliance",
        ),
        avoid_phrasings=(
            "show activity log",                 # → analyze_activity_log (recent activity)
            "check compliance status",           # → check_compliance_status (policy compliance)
            "search logs for errors",            # → search_logs_by_error
            "show diagnostic logs",              # → get_diagnostic_logs
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: analyze_activity_log already prefers over get_audit_trail
    ),
    # ---- Performance ----
    ToolManifest(
        tool_name="get_performance_metrics",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"performance", "metrics", "cpu", "memory"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show CPU and memory metrics",
            "performance metrics for my container app",
            "what are the resource utilisation trends",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset({"monitor"}),
        # Phase 3 metadata
        primary_phrasings=(
            "show CPU and memory metrics",
            "performance metrics for my resource",
            "what is my CPU utilisation",
            "memory usage trends for my app",
            "show resource utilisation",
            "performance graphs for my service",
            "how is my container app performing",
            "resource performance statistics",
            "show me performance metrics",
            "get CPU and memory usage for my resource",
        ),
        avoid_phrasings=(
            "configure Azure Monitor",           # → monitor (Azure MCP)
            "identify performance bottlenecks",  # → identify_bottlenecks (deeper analysis)
            "detect anomalies",                  # → detect_metric_anomalies
            "show SLO",                          # → get_slo_dashboard
            "show alert rules",                  # → monitor (Azure MCP)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("monitor",),
    ),
    ToolManifest(
        tool_name="identify_bottlenecks",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"performance", "bottleneck", "latency"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "identify performance bottlenecks",
            "what is causing high latency",
            "find the slow component",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "identify performance bottlenecks",
            "what is causing high latency",
            "find the slow component in my system",
            "why is my service slow",
            "bottleneck analysis",
            "what is slowing down my app",
            "performance degradation analysis",
            "find the bottleneck",
            "analyze slow response times",
        ),
        avoid_phrasings=(
            "show CPU metrics",                  # → get_performance_metrics (raw metrics)
            "detect metric anomalies",           # → detect_metric_anomalies
            "perform root cause analysis",       # → perform_root_cause_analysis (broader RCA)
            "SLO burn rate",                     # → monitor_slo_burn_rate
        ),
        confidence_boost=1.2,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="detect_metric_anomalies",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"performance", "anomaly", "metrics"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "detect anomalies in metrics",
            "is there unusual activity in my metrics",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "detect anomalies in my metrics",
            "is there unusual activity in my metrics",
            "metric anomaly detection",
            "are my metrics behaving abnormally",
            "show metric spikes and dips",
            "detect unusual metric patterns",
            "find anomalous metric values",
            "my metrics look abnormal",
            "statistical anomaly detection on metrics",
            "identify outliers in my performance metrics",
        ),
        avoid_phrasings=(
            "show performance metrics",          # → get_performance_metrics (raw metrics)
            "detect performance anomalies",      # → detect_performance_anomalies (performance-specific)
            "identify bottlenecks",              # → identify_bottlenecks (latency analysis)
            "monitor SLO burn rate",             # → monitor_slo_burn_rate
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("monitor", "get_performance_metrics"),
    ),
    ToolManifest(
        tool_name="compare_baseline_metrics",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"performance", "baseline", "comparison"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "compare metrics to baseline",
            "how does current performance compare to last week",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "compare metrics to baseline",
            "how does current performance compare to last week",
            "baseline comparison for my service",
            "is my performance worse than normal",
            "compare today's metrics to historical baseline",
            "performance regression analysis",
            "how are my metrics trending vs baseline",
            "compare current metrics against last month",
            "baseline drift analysis for my resource",
        ),
        avoid_phrasings=(
            "show performance metrics",          # → get_performance_metrics (raw metrics)
            "detect metric anomalies",           # → detect_metric_anomalies
            "SLO compliance check",              # → calculate_error_budget
            "identify bottlenecks",              # → identify_bottlenecks
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("get_performance_metrics",),
    ),
    ToolManifest(
        tool_name="analyze_dependency_map",
        source="sre",
        domains=frozenset({"sre_performance", "sre_rca"}),
        tags=frozenset({"dependencies", "map", "performance"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show the dependency map",
            "analyze service dependencies",
            "what services does my app call",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show the dependency map",
            "analyze service dependencies",
            "what services does my app call",
            "show full service dependency graph",
            "map out all dependencies for my application",
            "visualize my service topology",
            "analyze upstream and downstream dependencies",
            "dependency impact analysis",
            "trace all dependencies for my service",
            "show me the full dependency chain",
        ),
        avoid_phrasings=(
            "list resource dependencies",        # → get_resource_dependencies (simple list)
            "trace request call chain",          # → trace_dependency_chain (RCA-focused)
            "check resource health",             # → check_resource_health
            "show network topology",             # → network tools
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("get_resource_dependencies", "trace_dependency_chain"),
    ),
    ToolManifest(
        tool_name="get_app_insights_roles",
        source="sre",
        domains=frozenset({"sre_performance", "sre_incident"}),
        tags=frozenset({"appinsights", "discovery", "roles", "telemetry"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "what app names are in App Insights",
            "discover application roles in my workspace",
            "list cloud role names in Application Insights",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "what app names are in App Insights",
            "discover application roles in my workspace",
            "list cloud role names in Application Insights",
            "what apps are sending telemetry to this workspace",
            "find valid app_name values for dependency map",
            "which applications are instrumented in App Insights",
            "show me available app names for telemetry queries",
            "list Application Insights role names",
            "what cloud_RoleName values exist in my workspace",
        ),
        avoid_phrasings=(
            "analyze service dependencies",              # → analyze_dependency_map
            "show request telemetry",                    # → get_request_telemetry
            "query Application Insights traces",         # → query_app_insights_traces
            "show performance metrics",                  # → get_performance_metrics
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),
    ),
    ToolManifest(
        tool_name="predict_resource_exhaustion",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"performance", "prediction", "capacity"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "when will my resource run out of capacity",
            "predict resource exhaustion",
            "capacity forecast",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "when will my resource run out of capacity",
            "predict resource exhaustion",
            "capacity forecast for my service",
            "when will I need to scale up",
            "forecast storage exhaustion",
            "predict when my disk will fill up",
            "capacity planning forecast",
            "how long until my resource hits capacity limits",
            "predict memory exhaustion for my container app",
            "resource capacity runway estimate",
        ),
        avoid_phrasings=(
            "predict capacity issues",           # → predict_capacity_issues (RCA domain)
            "scale my resource",                 # → scale_resource (remediation)
            "show performance metrics",          # → get_performance_metrics
            "identify bottlenecks",              # → identify_bottlenecks
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("predict_capacity_issues",),
    ),
    ToolManifest(
        tool_name="detect_performance_anomalies",
        source="sre",
        domains=frozenset({"sre_performance", "sre_rca"}),
        tags=frozenset({"performance", "anomaly", "rca"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "detect performance anomalies",
            "are there any unusual performance patterns",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "detect performance anomalies",
            "are there any unusual performance patterns",
            "performance anomaly detection",
            "has my service performance degraded unexpectedly",
            "find abnormal latency spikes",
            "detect unusual throughput patterns",
            "identify performance regressions",
            "something is causing performance degradation",
            "find performance anomalies for RCA",
            "unusual performance behavior in my app",
        ),
        avoid_phrasings=(
            "detect metric anomalies",           # → detect_metric_anomalies (metrics-specific)
            "show performance metrics",          # → get_performance_metrics (raw metrics)
            "identify bottlenecks",              # → identify_bottlenecks (latency analysis)
            "SLO burn rate",                     # → monitor_slo_burn_rate
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("detect_metric_anomalies", "identify_bottlenecks"),
    ),
    ToolManifest(
        tool_name="monitor_slo_burn_rate",
        source="sre",
        domains=frozenset({"sre_performance"}),
        tags=frozenset({"slo", "burn_rate", "error_budget"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "what is the SLO burn rate",
            "check error budget consumption",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "what is the SLO burn rate",
            "check error budget consumption",
            "how fast is my error budget burning",
            "monitor SLO burn rate",
            "is my error budget burning too fast",
            "check SLO burn rate alert",
            "SLO burn rate analysis",
            "are we burning error budget too quickly",
            "show error budget burn trend",
            "current SLO burn rate for my service",
        ),
        avoid_phrasings=(
            "calculate error budget",            # → calculate_error_budget (budget calculation)
            "show SLO dashboard",                # → get_slo_dashboard (overview)
            "define SLO",                        # → define_slo (creation)
            "show performance metrics",          # → get_performance_metrics
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("calculate_error_budget", "get_slo_dashboard"),
    ),
    # ---- Cost / Security ----
    ToolManifest(
        tool_name="get_cost_analysis",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"cost", "spending", "billing"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show cost by resource group",
            "how much am I spending this month",
            "Azure cost breakdown",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "get_cost_analysis queries Azure Cost Management for real spending data. "
            "NOT for Azure resource pricing estimates."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show cost by resource group",
            "how much am I spending this month",
            "Azure cost breakdown",
            "show my Azure spending",
            "what is my cloud spend",
            "cost analysis for my subscription",
            "show billing details for my resource group",
            "Azure cost management report",
            "monthly cloud cost breakdown",
            "show my current Azure costs",
        ),
        avoid_phrasings=(
            "identify orphaned resources",       # → identify_orphaned_resources (waste)
            "show cost recommendations",         # → get_cost_recommendations (optimization)
            "detect cost anomalies",             # → analyze_cost_anomalies (spikes)
            "Azure pricing calculator",          # → not a tool (informational query)
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("analyze_cost_anomalies", "get_cost_recommendations"),
    ),
    ToolManifest(
        tool_name="identify_orphaned_resources",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"cost", "orphaned", "waste"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "find orphaned resources",
            "show unused disks and IPs",
            "identify cloud waste",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "find orphaned resources",
            "show unused disks and IPs",
            "identify cloud waste",
            "what resources are not being used",
            "find unattached disks",
            "show unassigned public IPs",
            "identify idle resources I can delete",
            "find resources wasting money",
            "cloud waste analysis",
            "show unused Azure resources",
        ),
        avoid_phrasings=(
            "show cost analysis",                # → get_cost_analysis (spending totals)
            "cost recommendations",              # → get_cost_recommendations (optimization tips)
            "detect cost anomalies",             # → analyze_cost_anomalies (spikes)
            "list all resources",                # → inventory tools
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("get_cost_analysis",),
    ),
    ToolManifest(
        tool_name="get_cost_recommendations",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"cost", "recommendations", "savings"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show cost saving recommendations",
            "how can I reduce Azure costs",
            "cost optimisation suggestions",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show cost saving recommendations",
            "how can I reduce Azure costs",
            "cost optimisation suggestions",
            "give me Azure cost saving tips",
            "how do I cut my cloud spending",
            "rightsizing recommendations",
            "Azure Advisor cost recommendations",
            "show me opportunities to save on Azure",
            "cost optimization recommendations for my subscription",
            "how can I lower my Azure bill",
        ),
        avoid_phrasings=(
            "show current costs",                # → get_cost_analysis (spending data)
            "find orphaned resources",           # → identify_orphaned_resources (waste)
            "detect cost spike",                 # → analyze_cost_anomalies
            "security recommendations",          # → list_security_recommendations
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("identify_orphaned_resources",),  # Removed get_cost_analysis: it already prefers over get_cost_recommendations
    ),
    ToolManifest(
        tool_name="analyze_cost_anomalies",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"cost", "anomaly", "spike"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "detect cost anomalies",
            "why did my costs spike",
            "unusual spending patterns",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "detect cost anomalies",
            "why did my costs spike",
            "unusual spending patterns in my subscription",
            "analyze cost spikes",
            "why is my Azure bill higher than usual",
            "cost anomaly detection",
            "unexpected cost increase analysis",
            "what caused my spending to jump",
            "identify abnormal cost patterns",
            "cost spike root cause analysis",
        ),
        avoid_phrasings=(
            "show current costs",                # → get_cost_analysis (spending breakdown)
            "cost saving recommendations",       # → get_cost_recommendations
            "find orphaned resources",           # → identify_orphaned_resources
            "detect performance anomalies",      # → detect_performance_anomalies
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: get_cost_analysis already prefers over analyze_cost_anomalies
    ),
    ToolManifest(
        tool_name="get_security_score",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"security", "score", "defender"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "what is my security score",
            "show Defender for Cloud score",
            "security posture",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "what is my security score",
            "show my Defender for Cloud score",
            "security posture score",
            "how secure is my Azure environment",
            "check my security score",
            "what is my Microsoft Defender score",
            "security health score",
            "show security posture rating",
        ),
        avoid_phrasings=(
            "list security recommendations",     # → list_security_recommendations
            "check compliance status",           # → check_compliance_status
            "network security posture",          # → assess_network_security_posture
            "check resource health",             # → check_resource_health (SRE)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="list_security_recommendations",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"security", "recommendations", "defender"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list security recommendations",
            "show Defender for Cloud findings",
            "what security issues do I have",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "list security recommendations",
            "show Defender for Cloud findings",
            "what security issues do I have",
            "show my security findings",
            "Azure security recommendations",
            "list security vulnerabilities",
            "show open security issues in my environment",
            "Defender for Cloud recommendations",
            "security improvement recommendations",
            "what security controls are failing",
        ),
        avoid_phrasings=(
            "what is my security score",         # → get_security_score (score only)
            "check compliance status",           # → check_compliance_status (policy)
            "network security posture",          # → assess_network_security_posture
            "cost recommendations",              # → get_cost_recommendations
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("get_security_score",),
    ),
    ToolManifest(
        tool_name="check_compliance_status",
        source="sre",
        domains=frozenset({"sre_cost_security"}),
        tags=frozenset({"compliance", "policy", "security"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check compliance status",
            "are my resources compliant",
            "show policy compliance",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "check compliance status",
            "are my resources compliant",
            "show policy compliance",
            "Azure Policy compliance report",
            "are my resources meeting compliance requirements",
            "check regulatory compliance status",
            "show PCI DSS compliance status",
            "compliance posture for my subscription",
            "which resources are non-compliant",
            "check CIS benchmark compliance",
        ),
        avoid_phrasings=(
            "show security recommendations",     # → list_security_recommendations
            "what is my security score",         # → get_security_score
            "show audit trail",                  # → get_audit_trail
            "check network security",            # → assess_network_security_posture
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("list_security_recommendations",),
    ),
    # ---- Remediation ----
    ToolManifest(
        tool_name="plan_remediation",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "plan", "fix"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "plan remediation for my resource",
            "generate a fix plan",
            "how to remediate this issue",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "plan remediation for my resource",
            "generate a fix plan",
            "how to remediate this issue",
            "create a remediation plan",
            "what steps do I take to fix this",
            "SRE remediation planning",
            "generate an action plan for this incident",
            "plan how to fix the degraded service",
            "remediation strategy for my issue",
        ),
        avoid_phrasings=(
            "generate detailed remediation plan",  # → generate_remediation_plan (detailed steps)
            "execute remediation step",            # → execute_remediation_step (execution)
            "perform root cause analysis",         # → perform_root_cause_analysis
            "generate postmortem",                 # → generate_postmortem
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("generate_remediation_plan",),
    ),
    ToolManifest(
        tool_name="generate_remediation_plan",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "plan", "steps"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "generate detailed remediation plan",
            "create step-by-step fix plan",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "generate detailed remediation plan",
            "create step-by-step fix plan",
            "generate a step-by-step remediation guide",
            "create detailed remediation steps",
            "detailed SRE remediation plan",
            "generate runbook for fixing this issue",
            "step-by-step plan to resolve the incident",
            "create detailed action items for remediation",
            "generate remediation playbook",
        ),
        avoid_phrasings=(
            "plan remediation",                  # → plan_remediation (high-level planning)
            "execute remediation step",          # → execute_remediation_step (execution)
            "generate postmortem",               # → generate_postmortem (retrospective)
            "perform root cause analysis",       # → perform_root_cause_analysis
        ),
        confidence_boost=1.3,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="execute_safe_restart",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "restart", "destructive"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "restart my container app safely",
            "reboot the virtual machine with safety checks",
            "perform safe restart of my Azure service",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
        # Phase 3 metadata
        primary_phrasings=(
            "restart my container app safely",
            "reboot my virtual machine with safety checks",
            "perform safe restart of my Azure service",
            "safe restart for my resource",
            "restart with pre-flight checks",
            "graceful restart of my service",
            "restart my app with rollback protection",
            "SRE-safe restart procedure",
            "restart my resource using SRE controls",
        ),
        avoid_phrasings=(
            "scale my resource",                 # → scale_resource
            "execute remediation step",          # → execute_remediation_step
            "clear cache",                       # → clear_cache
            "check resource health before restart",  # → check_resource_health (diagnostic)
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("execute_remediation_step",),
    ),
    ToolManifest(
        tool_name="scale_resource",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "scale", "destructive"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "scale up my AKS cluster",
            "increase container app replicas",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
        # Phase 3 metadata
        primary_phrasings=(
            "scale up my AKS cluster",
            "increase container app replicas",
            "scale out my resource to handle load",
            "scale my service to resolve capacity issue",
            "add more replicas to my container app",
            "scale up to meet demand",
            "increase node count for my AKS cluster",
            "auto-scale my service",
            "scale my resource as remediation action",
        ),
        avoid_phrasings=(
            "predict resource exhaustion",       # → predict_resource_exhaustion (forecasting)
            "restart my resource",               # → execute_safe_restart
            "execute remediation step",          # → execute_remediation_step
            "check resource health",             # → check_resource_health
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("execute_remediation_step",),
    ),
    ToolManifest(
        tool_name="clear_cache",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "cache", "destructive"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "clear the Redis cache for my service",
            "flush cache for my application completely",
            "reset cache to resolve performance issues",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
        # Phase 3 metadata
        primary_phrasings=(
            "clear the Redis cache for my service",
            "flush cache for my application",
            "reset cache to resolve performance issues",
            "clear application cache",
            "flush all cache entries",
            "purge the cache for my service",
            "clear cache as remediation action",
            "wipe cache to fix stale data issue",
            "reset Redis cache",
        ),
        avoid_phrasings=(
            "restart my service",                # → execute_safe_restart
            "scale my resource",                 # → scale_resource
            "execute remediation step",          # → execute_remediation_step
            "check cache health",                # → check_resource_health
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("execute_remediation_step",),
    ),
    ToolManifest(
        tool_name="execute_remediation_step",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "execute", "step"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "execute the next remediation step",
            "run remediation step",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
        # Phase 3 metadata
        primary_phrasings=(
            "execute the next remediation step",
            "run remediation step",
            "execute step from my remediation plan",
            "perform the remediation action",
            "run the next step in the fix plan",
            "execute remediation action",
            "carry out the remediation step",
            "apply remediation step to my resource",
            "execute the prescribed fix for this incident",
        ),
        avoid_phrasings=(
            "generate remediation plan",         # → generate_remediation_plan (planning phase)
            "plan remediation",                  # → plan_remediation (high-level)
            "restart my service",                # → execute_safe_restart (specific action)
            "scale my resource",                 # → scale_resource (specific action)
            "clear cache",                       # → clear_cache (specific action)
        ),
        confidence_boost=1.2,
        requires_sequence=("generate_remediation_plan",),
    ),
    ToolManifest(
        tool_name="send_teams_notification",
        source="sre",
        domains=frozenset({"sre_remediation", "sre_incident"}),
        tags=frozenset({"notifications", "teams", "messaging"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "send Teams notification to my channel",
            "notify the team via Microsoft Teams now",
            "send a message to my Teams channel",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "send Teams notification to my channel",
            "notify the team via Microsoft Teams",
            "send a message to my Teams channel",
            "send notification to Teams",
            "post update to Teams channel",
            "notify team via Teams",
            "send Teams message",
            "broadcast message to Teams channel",
            "send SRE update to Teams",
        ),
        avoid_phrasings=(
            "send Teams alert",                  # → send_teams_alert (alert-specific)
            "send SRE status update",            # → send_sre_status_update (structured update)
            "send email notification",           # → not an SRE tool
            "page on-call engineer",             # → send_teams_alert (urgency implied)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("send_sre_status_update",),
    ),
    ToolManifest(
        tool_name="send_teams_alert",
        source="sre",
        domains=frozenset({"sre_remediation", "sre_incident"}),
        tags=frozenset({"notifications", "teams", "alert"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "send Teams alert to on-call engineer",
            "alert the on-call team via Microsoft Teams",
            "send urgent alert notification to Teams",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "send Teams alert to on-call engineer",
            "alert the on-call team via Microsoft Teams",
            "send urgent alert notification to Teams",
            "page the on-call via Teams",
            "fire P1 alert to Teams channel",
            "send critical incident alert to Teams",
            "alert engineering team about outage via Teams",
            "send high severity alert to Teams",
            "notify on-call SRE via Teams alert",
        ),
        avoid_phrasings=(
            "send Teams notification",           # → send_teams_notification (non-urgent)
            "send SRE status update",            # → send_sre_status_update (structured)
            "correlate alerts",                  # → correlate_alerts (analysis, not notification)
            "broadcast routine update",          # → send_teams_notification
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("send_teams_notification", "send_sre_status_update"),
    ),
    ToolManifest(
        tool_name="send_sre_status_update",
        source="sre",
        domains=frozenset({"sre_remediation", "sre_incident"}),
        tags=frozenset({"notifications", "status", "update"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "send SRE status update",
            "broadcast incident status to stakeholders",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "send SRE status update",
            "broadcast incident status to stakeholders",
            "send structured status update to stakeholders",
            "post SRE incident status update",
            "send incident timeline update",
            "broadcast remediation progress to management",
            "send status page update for the incident",
            "notify stakeholders of incident status",
            "publish SRE status to Teams",
            "send structured incident update",
        ),
        avoid_phrasings=(
            "send Teams alert",                  # → send_teams_alert (urgent alerts)
            "send Teams notification",           # → send_teams_notification (general messages)
            "generate incident summary",         # → generate_incident_summary (report generation)
            "generate postmortem",               # → generate_postmortem
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: send_teams_notification already prefers over send_sre_status_update
    ),
    # ---- RCA ----
    ToolManifest(
        tool_name="perform_root_cause_analysis",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "root_cause", "analysis"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "perform root cause analysis",
            "what caused the outage",
            "root cause for my incident",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "perform root cause analysis",
            "what caused the outage",
            "root cause analysis for my incident",
            "find the root cause",
            "why did the incident happen",
            "RCA for my service failure",
            "deep dive into the failure cause",
            "root cause investigation",
            "investigate the root cause of the failure",
        ),
        avoid_phrasings=(
            "triage the incident",               # → triage_incident (initial investigation)
            "generate postmortem",               # → generate_postmortem (report generation)
            "trace dependency chain",            # → trace_dependency_chain (specific tool)
            "detect log anomalies",              # → analyze_log_patterns
        ),
        confidence_boost=1.2,
        requires_sequence=None,
    ),
    ToolManifest(
        tool_name="trace_dependency_chain",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "trace", "dependencies"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "trace dependency chain for my service",
            "show the call chain",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "trace dependency chain for my service",
            "show the call chain",
            "trace the request through my microservices",
            "trace dependency chain for RCA",
            "which dependency caused the failure",
            "trace the failure through my service graph",
            "dependency chain trace for incident",
            "follow the call chain to find the failure",
            "trace upstream failure propagation",
            "trace request path through services",
        ),
        avoid_phrasings=(
            "show dependency map",               # → analyze_dependency_map (full topology)
            "list resource dependencies",        # → get_resource_dependencies (simple list)
            "perform root cause analysis",       # → perform_root_cause_analysis (broader RCA)
            "show Application Insights traces",  # → query_app_insights_traces
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("get_resource_dependencies",),  # Removed circular: analyze_dependency_map already prefers over trace_dependency_chain
    ),
    ToolManifest(
        tool_name="analyze_log_patterns",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "logs", "patterns"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "analyze log patterns",
            "find recurring error patterns in logs",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "analyze log patterns",
            "find recurring error patterns in logs",
            "detect log pattern anomalies",
            "what are the common error patterns in my logs",
            "log pattern analysis for RCA",
            "analyze recurring failures in log data",
            "identify error pattern trends",
            "cluster log errors by pattern",
            "find systematic log failure patterns",
            "log-based RCA pattern detection",
        ),
        avoid_phrasings=(
            "search logs for errors",            # → search_logs_by_error (error search)
            "show diagnostic logs",              # → get_diagnostic_logs (raw logs)
            "query Application Insights",        # → query_app_insights_traces
            "show activity log",                 # → analyze_activity_log
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("search_logs_by_error", "get_diagnostic_logs"),
    ),
    ToolManifest(
        tool_name="predict_capacity_issues",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "capacity", "prediction"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "predict capacity issues for my resources",
            "will my resources run out of capacity soon",
            "forecast when I'll need more capacity",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "predict capacity issues for my resources",
            "will my resources run out of capacity soon",
            "forecast when I will need more capacity",
            "capacity issue prediction",
            "is my service at risk of capacity exhaustion",
            "predict future capacity bottlenecks",
            "capacity risk analysis for my service",
            "which resources are close to capacity limits",
            "capacity headroom analysis",
            "predict capacity failures before they happen",
        ),
        avoid_phrasings=(
            "predict resource exhaustion",       # → predict_resource_exhaustion (performance domain)
            "show capacity metrics",             # → get_performance_metrics
            "scale my resource",                 # → scale_resource (remediation)
            "identify bottlenecks",              # → identify_bottlenecks
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: predict_resource_exhaustion already prefers over predict_capacity_issues
    ),
    ToolManifest(
        tool_name="generate_postmortem",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "postmortem", "report"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "generate postmortem report",
            "create a postmortem for the outage",
            "write incident postmortem",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "generate postmortem report",
            "create a postmortem for the outage",
            "write incident postmortem",
            "generate a blameless postmortem",
            "create post-incident review document",
            "write the incident retrospective",
            "generate PIR for the outage",
            "create RCA postmortem report",
            "generate incident follow-up document",
            "write up the post-incident analysis",
        ),
        avoid_phrasings=(
            "generate incident summary",         # → generate_incident_summary (during incident)
            "triage the incident",               # → triage_incident (active investigation)
            "perform root cause analysis",       # → perform_root_cause_analysis (analysis phase)
            "send incident status update",       # → send_sre_status_update
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=(),  # Removed circular: generate_incident_summary already prefers over generate_postmortem
    ),
    ToolManifest(
        tool_name="calculate_mttr_metrics",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "mttr", "dora", "reliability"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "calculate MTTR",
            "show DORA metrics",
            "mean time to recovery",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "calculate MTTR",
            "show DORA metrics",
            "mean time to recovery",
            "calculate mean time to restore service",
            "show reliability engineering metrics",
            "DORA metrics for my team",
            "calculate MTTD and MTTR",
            "reliability KPIs for my service",
            "show incident recovery time metrics",
            "calculate DORA four key metrics",
        ),
        avoid_phrasings=(
            "calculate error budget",            # → calculate_error_budget (SLO compliance)
            "show SLO dashboard",                # → get_slo_dashboard
            "generate postmortem",               # → generate_postmortem
            "show performance metrics",          # → get_performance_metrics
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("calculate_error_budget",),
    ),
    # ---- App Insights (shared: incident + performance) ----
    ToolManifest(
        tool_name="query_app_insights_traces",
        source="sre",
        domains=frozenset({"sre_incident", "sre_performance"}),
        tags=frozenset({"appinsights", "traces", "telemetry"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show Application Insights traces",
            "query app insights for errors",
            "traces from my app",
        ),
        conflicts_with=frozenset({"applicationinsights"}),
        conflict_note=(
            "query_app_insights_traces (SRE) queries telemetry data. "
            "applicationinsights (Azure MCP) configures Application Insights resources. "
            "For data retrieval use query_app_insights_traces."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show Application Insights traces",
            "query app insights for errors",
            "traces from my app",
            "query Application Insights telemetry",
            "search Application Insights for failures",
            "show traces from Application Insights",
            "query AI traces for incident investigation",
            "Application Insights trace query",
            "show distributed traces from my app",
            "query telemetry data from Application Insights",
        ),
        avoid_phrasings=(
            "configure Application Insights",    # → applicationinsights (Azure MCP)
            "search logs for errors",            # → search_logs_by_error
            "show request telemetry",            # → get_request_telemetry (request-specific)
            "get diagnostic logs",               # → get_diagnostic_logs
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("applicationinsights", "search_logs_by_error"),
    ),
    ToolManifest(
        tool_name="get_request_telemetry",
        source="sre",
        domains=frozenset({"sre_incident", "sre_performance"}),
        tags=frozenset({"appinsights", "requests", "telemetry"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show request telemetry",
            "what is the request success rate",
            "HTTP request statistics",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show request telemetry",
            "what is the request success rate",
            "HTTP request statistics",
            "show API request failure rate",
            "request duration and success rate",
            "HTTP 5xx and 4xx rate for my service",
            "show request throughput telemetry",
            "request performance telemetry",
            "what is my service request error rate",
            "show inbound request metrics",
        ),
        avoid_phrasings=(
            "show Application Insights traces",  # → query_app_insights_traces (trace query)
            "show performance metrics",          # → get_performance_metrics (resource metrics)
            "detect anomalies",                  # → detect_metric_anomalies
            "show diagnostic logs",              # → get_diagnostic_logs
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("query_app_insights_traces", "get_performance_metrics"),
    ),
    # ---- SLO (shared: performance + cost_security) ----
    ToolManifest(
        tool_name="define_slo",
        source="sre",
        domains=frozenset({"sre_performance", "sre_cost_security"}),
        tags=frozenset({"slo", "availability", "latency"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "define an SLO for my service",
            "set availability target",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "define_slo stores SLO definitions in Cosmos DB. "
            "Use calculate_error_budget to check compliance after defining."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "define an SLO for my service",
            "set availability target for my service",
            "create a service level objective",
            "set latency SLO for my API",
            "define SLO targets",
            "configure SLO for my service",
            "set up error budget for my service",
            "define availability and latency targets",
            "create SLO definition",
            "set reliability targets for my service",
        ),
        avoid_phrasings=(
            "calculate error budget",            # → calculate_error_budget (compliance check)
            "show SLO dashboard",                # → get_slo_dashboard (view existing SLOs)
            "monitor SLO burn rate",             # → monitor_slo_burn_rate (monitoring)
            "show compliance status",            # → check_compliance_status
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("calculate_error_budget", "get_slo_dashboard"),
    ),
    ToolManifest(
        tool_name="calculate_error_budget",
        source="sre",
        domains=frozenset({"sre_performance", "sre_cost_security"}),
        tags=frozenset({"slo", "error_budget", "compliance"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "calculate error budget",
            "how much error budget remains",
            "SLO compliance check",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "calculate_error_budget requires an SLO defined via define_slo first."
        ),
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "calculate error budget",
            "how much error budget remains",
            "SLO compliance check",
            "how much error budget do I have left",
            "calculate remaining error budget for my service",
            "SLO error budget status",
            "error budget consumption for my service",
            "what percentage of error budget is remaining",
            "how is my SLO compliance",
            "error budget analysis for my service",
        ),
        avoid_phrasings=(
            "define SLO",                        # → define_slo (creation)
            "show SLO dashboard",                # → get_slo_dashboard (overview)
            "monitor SLO burn rate",             # → monitor_slo_burn_rate (burn rate monitoring)
            "check compliance status",           # → check_compliance_status (policy)
        ),
        confidence_boost=1.3,
        requires_sequence=("define_slo",),
        preferred_over_list=(),  # Removed circular: monitor_slo_burn_rate already prefers over calculate_error_budget
    ),
    ToolManifest(
        tool_name="get_slo_dashboard",
        source="sre",
        domains=frozenset({"sre_performance", "sre_cost_security"}),
        tags=frozenset({"slo", "dashboard", "overview"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show SLO dashboard",
            "overview of all SLOs",
            "SLO status across services",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "show SLO dashboard",
            "overview of all SLOs",
            "SLO status across services",
            "show all my SLOs",
            "SLO health overview",
            "give me a summary of all SLOs",
            "show SLO compliance across my services",
            "SLO dashboard for all services",
            "overview of service level objectives",
            "show me the SLO status page",
        ),
        avoid_phrasings=(
            "calculate error budget",            # → calculate_error_budget (specific budget)
            "monitor SLO burn rate",             # → monitor_slo_burn_rate (burn monitoring)
            "define SLO",                        # → define_slo (creation)
            "show compliance status",            # → check_compliance_status (policy)
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=("calculate_error_budget",),  # Removed monitor_slo_burn_rate: it already prefers over get_slo_dashboard
    ),
    # ---- Cross-domain utility ----
    ToolManifest(
        tool_name="describe_capabilities",
        source="sre",
        domains=frozenset({"sre_health", "sre_incident", "sre_performance",
                           "sre_cost_security", "sre_rca", "sre_remediation"}),
        tags=frozenset({"capabilities", "help", "discovery"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "what can you do",
            "describe SRE capabilities",
            "what SRE tools are available",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        # Phase 3 metadata
        primary_phrasings=(
            "what can you do",
            "describe SRE capabilities",
            "what SRE tools are available",
            "what can the SRE agent help with",
            "show me available SRE tools",
            "what SRE operations are supported",
            "list SRE capabilities",
            "what can the SRE MCP server do",
            "help me understand SRE capabilities",
            "what SRE domains are covered",
        ),
        avoid_phrasings=(
            "check resource health",             # → check_resource_health (specific action)
            "triage incident",                   # → triage_incident (specific action)
            "list my resources",                 # → inventory tools
            "show Azure documentation",          # → documentation (Azure MCP)
        ),
        confidence_boost=1.1,
        requires_sequence=None,
    ),
]

SRE_TOOL_MANIFESTS = MANIFESTS
