"""SRE domain sub-agent — collapses ~58 SRE tools behind a single meta-tool.

Inherits from DomainSubAgent and provides an SRE-specific system prompt that
covers all 15 SRE domains: health, incidents, performance, cost, SLOs,
App Insights, security, remediation, configuration discovery, diagnostics,
anomaly detection, capacity planning, log analysis, and notifications.

The orchestrator replaces all SRE-source tools with a single ``sre_agent``
meta-tool.  When invoked, the orchestrator delegates to this agent which
runs its own ReAct loop over the full SRE tool set.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Coroutine, Dict, List, Optional

try:
    from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
except (ModuleNotFoundError, ImportError):
    try:
        # Direct module import — avoids agents/__init__.py cascade
        import importlib.util as _ilu
        import pathlib as _pl
        _dsap = _pl.Path(__file__).resolve().parent / "domain_sub_agent.py"
        _spec = _ilu.spec_from_file_location("domain_sub_agent", _dsap)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        DomainSubAgent = _mod.DomainSubAgent
    except Exception:
        raise ImportError("Cannot import DomainSubAgent from agents.domain_sub_agent")


class SRESubAgent(DomainSubAgent):
    """Focused sub-agent for Site Reliability Engineering operations.

    Owns ~58 SRE tools across 15 operational domains.  Has a concise
    domain-specific system prompt so the LLM only needs to reason about
    SRE tool selection — no container registry, speech, or storage confusion.
    """

    _DOMAIN_NAME = "sre"
    _MAX_ITERATIONS = 20   # SRE workflows can be multi-step (triage → logs → remediate)
    _TIMEOUT_SECONDS = 50.0

    _SYSTEM_PROMPT = """\
You are the Azure SRE (Site Reliability Engineering) specialist agent.
You have access to ~58 SRE-focused tools covering 15 operational domains.
Your job is to handle health checks, incident response, performance analysis,
cost optimization, SLO management, security compliance, and remediation.

CRITICAL RULE — NO FABRICATION:
You MUST call a tool before presenting ANY data.
NEVER generate fake resource IDs, metric values, or example data.
If a tool call fails, report the real error — do NOT substitute made-up data.

SAFETY — DESTRUCTIVE OPERATIONS:
Before executing any remediation tool (restart, scale, clear_cache):
1. Call plan_remediation or generate_remediation_plan first.
2. Present the plan to the user.
3. Wait for confirmation — do NOT execute without approval.

TOOL SELECTION BY DOMAIN:

Health & Diagnostics:
  → check_resource_health (generic, needs full resource ID)
  → check_container_app_health (Container Apps specific)
  → check_aks_cluster_health (AKS specific)
  → diagnose_app_service (App Service diagnostics)
  → diagnose_apim (API Management diagnostics)
  → get_diagnostic_logs (requires workspace_id + resource_id)
  → analyze_resource_configuration (resource config analysis)
  → get_resource_dependencies (dependency graph)

Incident Response:
  → triage_incident (automated triage + root cause)
  → search_logs_by_error (pattern-based log search)
  → correlate_alerts (temporal + resource alert correlation)
  → analyze_activity_log (Azure Activity Log analysis)
  → generate_incident_summary (structured incident report)
  → perform_root_cause_analysis (deep RCA with evidence chain)
  → generate_postmortem (comprehensive post-incident review)
  → calculate_mttr_metrics (DORA metrics)

Performance:
  → get_performance_metrics (auto-calculates time ranges — ALWAYS prefer this over CLI)
  → identify_bottlenecks (pattern analysis)
  → get_capacity_recommendations (scaling advice)
  → compare_baseline_metrics (before/after analysis)
  → detect_performance_anomalies (ML-based detection)

Configuration Discovery:
  → query_app_service_configuration (bulk App Service config queries)
  → query_container_app_configuration (bulk Container Apps queries)
  → list_container_apps (enumerate Container Apps)
  → query_aks_configuration (bulk AKS config queries)
  → query_apim_configuration (bulk APIM config queries)

Application Insights & Tracing:
  → query_app_insights_traces (distributed tracing by operation ID)
  → get_request_telemetry (P95/P99 latencies, failure rates)
  → analyze_dependency_map (service-to-service dependencies)
  → trace_dependency_chain (full dependency chain analysis)

Cost Optimization:
  → get_cost_analysis (cost breakdown by RG, service, tag, location)
  → identify_orphaned_resources (unattached disks, idle IPs, empty NSGs)
  → get_cost_recommendations (Azure Advisor suggestions)
  → analyze_cost_anomalies (spending pattern anomalies)

SLO/SLI Management:
  → define_slo (create service level objectives)
  → calculate_error_budget (remaining budget vs targets)
  → get_slo_dashboard (compliance overview + burn rate)
  → monitor_slo_burn_rate (real-time burn rate tracking)

Security & Compliance:
  → get_security_score (Defender for Cloud secure score)
  → list_security_recommendations (actionable findings by severity)
  → check_compliance_status (Azure Policy — CIS, NIST, PCI-DSS)

Anomaly Detection & Capacity:
  → detect_metric_anomalies (metric-level anomaly detection)
  → predict_resource_exhaustion (resource exhaustion forecasting)
  → predict_capacity_issues (capacity planning)

Log Analysis:
  → analyze_log_patterns (log pattern mining and clustering)

Remediation:
  → plan_remediation (impact assessment — always call first)
  → generate_remediation_plan (detailed step-by-step plan)
  → execute_safe_restart (restart with safety checks — requires approval)
  → scale_resource (scaling operation — requires approval)
  → clear_cache (cache invalidation — requires approval)
  → execute_remediation_step (execute plan step — requires approval)
  → register_custom_runbook (register automation runbook)

Notifications:
  → send_teams_notification (Teams channel notifications)
  → send_teams_alert (Teams critical alerts)
  → send_sre_status_update (SRE status updates)
  → get_audit_trail (operation audit history)

Self-Documentation:
  → describe_capabilities (list what this agent can do)
  → get_prompt_examples (example prompts by category)

COMMON WORKFLOWS:
• Health check → check_resource_health(resource_id) or check_container_app_health(name)
• Incident → triage_incident → search_logs_by_error → correlate_alerts → generate_incident_summary
• Performance → get_performance_metrics → identify_bottlenecks → get_capacity_recommendations
• Cost review → get_cost_analysis → identify_orphaned_resources → get_cost_recommendations
• SLO check → get_slo_dashboard → calculate_error_budget
• Security audit → get_security_score → list_security_recommendations → check_compliance_status
• Remediation → plan_remediation → present plan → wait for approval → execute_safe_restart/scale_resource

FORMATTING:
- Return responses as raw HTML (no markdown, no backticks).
- Use <table> for structured data.
- For time-series data, include Chart.js line chart configuration.
- For single-value metrics, use progress bars.
- NEVER use summary tables (Avg/Min/Max) for time-series — always Chart.js."""

    def __init__(
        self,
        tool_definitions: List[Dict[str, Any]],
        tool_invoker: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        event_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        *,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        super().__init__(
            tool_definitions=tool_definitions,
            tool_invoker=tool_invoker,
            event_callback=event_callback,
            conversation_context=conversation_context,
        )
        # Track prior SRE interactions for context continuity
        self._sre_history: List[Dict[str, str]] = []

    async def _pre_tool_call(
        self, tool_name: str, arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Block destructive operations that haven't been confirmed."""
        destructive_tools = {
            "execute_safe_restart", "scale_resource", "clear_cache",
            "execute_remediation_step",
        }
        if tool_name in destructive_tools:
            allow_real = os.getenv("ALLOW_REAL_REMEDIATION", "false").lower() == "true"
            if not allow_real:
                return {
                    "success": False,
                    "blocked": True,
                    "error": (
                        f"Tool '{tool_name}' blocked: ALLOW_REAL_REMEDIATION is not enabled. "
                        "Set ALLOW_REAL_REMEDIATION=true to allow destructive operations."
                    ),
                }
        return None


def build_sre_meta_tool() -> Dict[str, Any]:
    """Return the OpenAI function-calling definition for the sre_agent meta-tool.

    This is injected into the orchestrator's tool catalog in place of
    the ~58 individual SRE tools.
    """
    return {
        "function": {
            "name": "sre_agent",
            "description": (
                "Delegate to the Azure SRE specialist agent. Use this tool for ANY question about: "
                "resource health, incidents, troubleshooting, diagnostics, performance metrics, "
                "bottlenecks, cost analysis, orphaned resources, cost optimization, "
                "SLOs, error budgets, Application Insights traces, request telemetry, "
                "security scores, compliance, remediation, restarts, scaling, "
                "configuration discovery (App Service, Container Apps, AKS, APIM), "
                "anomaly detection, capacity planning, log analysis, postmortems, DORA metrics, "
                "or Teams notifications. "
                "Pass the user's FULL request as-is. The SRE agent handles tool selection internally."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": (
                            "The user's full request about SRE operations. "
                            "Include any resource names, IDs, time ranges, or context from "
                            "prior conversation turns. Be specific and include all details."
                        ),
                    }
                },
                "required": ["request"],
            },
        }
    }
