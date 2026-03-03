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
    ),
    ToolManifest(
        tool_name="get_audit_trail",
        source="sre",
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
    ),
    ToolManifest(
        tool_name="execute_safe_restart",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "restart", "destructive"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "restart my container app",
            "reboot the VM",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
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
    ),
    ToolManifest(
        tool_name="clear_cache",
        source="sre",
        domains=frozenset({"sre_remediation"}),
        tags=frozenset({"remediation", "cache", "destructive"}),
        affordance=ToolAffordance.DESTRUCTIVE,
        example_queries=(
            "clear the Redis cache",
            "flush cache for my service",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
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
    ),
    ToolManifest(
        tool_name="send_teams_notification",
        source="sre",
        domains=frozenset({"sre_remediation", "sre_incident"}),
        tags=frozenset({"notifications", "teams", "messaging"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "send Teams notification",
            "notify the team via Teams",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="send_teams_alert",
        source="sre",
        domains=frozenset({"sre_remediation", "sre_incident"}),
        tags=frozenset({"notifications", "teams", "alert"}),
        affordance=ToolAffordance.WRITE,
        example_queries=(
            "send Teams alert",
            "alert the on-call team via Teams",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
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
    ),
    ToolManifest(
        tool_name="predict_capacity_issues",
        source="sre",
        domains=frozenset({"sre_rca"}),
        tags=frozenset({"rca", "capacity", "prediction"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "predict capacity issues",
            "will my resources run out",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
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
    ),
]
