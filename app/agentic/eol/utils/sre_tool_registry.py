"""SRE Tool Registry — single source of truth for domain → tool subset mapping.

Each SRE domain maps to a fixed, curated subset of tools from sre_mcp_server.py.
Tools are selected by operation type, NOT by Azure service — every tool accepts
resource_id/resource_name as input and works across all Azure services.

Domain taxonomy:
  health        — resource availability, service diagnostics
  incident      — triage, log search, alert correlation, incident reports
  performance   — metrics, bottlenecks, anomaly detection, telemetry
  cost_security — cost analysis, orphaned resources, security score, compliance
  rca           — root cause analysis, dependency tracing, log patterns, postmortems
  remediation   — safe restart, scale, cache clear, remediation plans

Usage:
    from utils.sre_tool_registry import SREDomain, SREToolRegistry

    domain = SREDomain.HEALTH
    tool_names = SREToolRegistry.get_tool_names(domain)
    tool_defs = SREToolRegistry.get_tool_definitions(domain, all_tool_defs)
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional


class SREDomain(str, Enum):
    """SRE operation type domains. Service-agnostic — tools accept resource_id."""

    HEALTH = "health"
    INCIDENT = "incident"
    PERFORMANCE = "performance"
    COST_SECURITY = "cost_security"
    RCA = "rca"
    REMEDIATION = "remediation"

    # Default when domain is ambiguous — routes to broad health+incident tools
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Domain → Tool Name Map
# All tool names must exist in mcp_servers/sre_mcp_server.py
# ---------------------------------------------------------------------------

_DOMAIN_TOOLS: Dict[SREDomain, List[str]] = {
    SREDomain.HEALTH: [
        "check_resource_health",
        "check_container_app_health",
        "check_aks_cluster_health",
        "diagnose_app_service",
        "diagnose_apim",
        "analyze_resource_configuration",
        "get_diagnostic_logs",
        "get_resource_dependencies",
        "list_container_apps",
        "describe_capabilities",
    ],
    SREDomain.INCIDENT: [
        "triage_incident",
        "search_logs_by_error",
        "correlate_alerts",
        "analyze_activity_log",
        "generate_incident_summary",
        "query_app_insights_traces",
        "get_request_telemetry",
        "get_audit_trail",
        "describe_capabilities",
    ],
    SREDomain.PERFORMANCE: [
        "get_performance_metrics",
        "identify_bottlenecks",
        "detect_metric_anomalies",
        "compare_baseline_metrics",
        "analyze_dependency_map",
        "predict_resource_exhaustion",
        "detect_performance_anomalies",
        "monitor_slo_burn_rate",
        "describe_capabilities",
    ],
    SREDomain.COST_SECURITY: [
        "get_cost_analysis",
        "identify_orphaned_resources",
        "get_cost_recommendations",
        "analyze_cost_anomalies",
        "get_security_score",
        "list_security_recommendations",
        "check_compliance_status",
        "describe_capabilities",
    ],
    SREDomain.RCA: [
        "perform_root_cause_analysis",
        "trace_dependency_chain",
        "analyze_log_patterns",
        "predict_capacity_issues",
        "generate_postmortem",
        "calculate_mttr_metrics",
        "detect_performance_anomalies",
        "describe_capabilities",
    ],
    SREDomain.REMEDIATION: [
        "plan_remediation",
        "generate_remediation_plan",
        "execute_safe_restart",
        "scale_resource",
        "clear_cache",
        "execute_remediation_step",
        "send_teams_notification",
        "send_teams_alert",
        "send_sre_status_update",
        "describe_capabilities",
    ],
    # General: broad coverage for ambiguous queries — health + incident tools
    SREDomain.GENERAL: [
        "check_resource_health",
        "check_container_app_health",
        "check_aks_cluster_health",
        "triage_incident",
        "search_logs_by_error",
        "get_performance_metrics",
        "get_diagnostic_logs",
        "analyze_resource_configuration",
        "list_container_apps",
        "describe_capabilities",
    ],
}

# SLO tools are shared across domains — add to performance and cost_security
_SLO_TOOLS = ["define_slo", "calculate_error_budget", "get_slo_dashboard"]
_DOMAIN_TOOLS[SREDomain.PERFORMANCE].extend(_SLO_TOOLS)
_DOMAIN_TOOLS[SREDomain.COST_SECURITY].extend(_SLO_TOOLS)


class SREToolRegistry:
    """Static registry mapping SRE domains to curated tool subsets.

    Tools are parameterized by resource_id — not per-service agents.
    This scales to any number of Azure services without adding agents.
    """

    @staticmethod
    def get_tool_names(domain: SREDomain) -> List[str]:
        """Return the list of tool names for the given domain."""
        return list(_DOMAIN_TOOLS.get(domain, _DOMAIN_TOOLS[SREDomain.GENERAL]))

    @staticmethod
    def get_tool_definitions(
        domain: SREDomain,
        all_tool_definitions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter all_tool_definitions to only those in the given domain.

        Args:
            domain: The SRE operation domain.
            all_tool_definitions: Full catalog of tool defs (OpenAI function format).

        Returns:
            Filtered list of tool defs for the domain. Preserves original order
            from all_tool_definitions.
        """
        allowed = set(SREToolRegistry.get_tool_names(domain))
        return [
            t for t in all_tool_definitions
            if _tool_name(t) in allowed
        ]

    @staticmethod
    def all_domains() -> List[SREDomain]:
        """Return all concrete domains (excludes GENERAL)."""
        return [d for d in SREDomain if d != SREDomain.GENERAL]

    @staticmethod
    def all_tool_names() -> List[str]:
        """Return the union of all domain tool names (deduplicated)."""
        seen: set[str] = set()
        result: List[str] = []
        for names in _DOMAIN_TOOLS.values():
            for name in names:
                if name not in seen:
                    seen.add(name)
                    result.append(name)
        return result

    @staticmethod
    def domain_for_tool(tool_name: str) -> Optional[SREDomain]:
        """Return the primary domain for a tool name, or None if not registered.

        When a tool appears in multiple domains, returns the first match in
        the preferred order: health → incident → performance → cost_security
        → rca → remediation → general.
        """
        preferred_order = [
            SREDomain.HEALTH,
            SREDomain.INCIDENT,
            SREDomain.PERFORMANCE,
            SREDomain.COST_SECURITY,
            SREDomain.RCA,
            SREDomain.REMEDIATION,
            SREDomain.GENERAL,
        ]
        for domain in preferred_order:
            if tool_name in _DOMAIN_TOOLS.get(domain, []):
                return domain
        return None


def _tool_name(tool_def: Dict[str, Any]) -> str:
    """Extract tool name from OpenAI function-calling format."""
    return str(tool_def.get("function", {}).get("name", ""))
