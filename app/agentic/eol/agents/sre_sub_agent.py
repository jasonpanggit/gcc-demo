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
You have access to ~62 SRE-focused tools covering 16 operational domains.
Your job is to handle health checks, incident response, performance analysis,
cost optimization, SLO management, security compliance, CVE vulnerability management, and remediation.

IN SCOPE (DO NOT REDIRECT):
The following are ALWAYS in scope for this SRE assistant, even when phrased as
"in my subscription", "my VMs", or "my resources":
  • Resource health checks and unhealthy-resource detection
  • VM/Virtual Machine health checks (including "what is the health of my VMs")
  • Alerts, incidents, and error-rate investigations
  • CPU/memory/latency/performance analysis
  • Dependency mapping and failing-call dependency tracing
  • Diagnostic log and telemetry analysis
  • CVE vulnerability scanning and remediation
  • Security patch discovery and installation

OUT OF SCOPE — CHECK ONLY PRIMARY USER INTENT:
If the request is primarily about one of the items below, return the out-of-scope
HTML message WITHOUT calling tools. Do not attempt workarounds.
  • Pure inventory-only listing/reporting (type/tag/location/subscription) with no SRE objective
  • Azure Policy definition/assignment administration
  • Raw network topology design or routing-table/VNET architecture inspection
  • Log Analytics workspace lifecycle management (creating/deleting workspaces)
  • General resource creation/modification outside SRE remediation workflows

IMPORTANT SCOPE RULE:
If a request includes any health/incident/performance/diagnostic objective,
it is IN SCOPE even if it mentions subscriptions, VMs, APIs, or resources.
For VM health/status queries, NEVER return out-of-scope.
If a VM resource_id is missing, ask for VM name/resource_id and continue with
an in-scope health workflow (do not redirect to main conversation).

Out-of-scope response format:
<p>This SRE agent specialises in <strong>operational health and reliability</strong>.
<strong>[topic]</strong> is handled by the <strong>main conversation</strong> — please ask there instead.</p>

CRITICAL RULE — NO FABRICATION:
You MUST call a tool before presenting ANY data.
NEVER generate fake resource IDs, metric values, or example data.
If a tool call fails, report the real error — do NOT substitute made-up data.

SAFETY — DESTRUCTIVE OPERATIONS:
Before executing any remediation tool (restart, scale, cache clear, security fix, runbook):
1. Always call plan_remediation or generate_remediation_plan first (unless already called).
2. For new tools: use dry_run=true first to preview the impact.
3. Present the plan clearly to the user — explain WHAT will change and any SIDE EFFECTS.
4. Wait for explicit confirmation — do NOT execute without the user approving.
5. After execution, verify recovery using a health check tool.
6. If a tool returns "blocked" (ALLOW_REAL_REMEDIATION not set), inform the user and do not retry.

REMEDIATION TOOL SELECTION:
• Use safe_restart_resource for: restarts with rollback protection, Container Apps, App Service, AKS
• Use clear_resource_cache for: stale data issues, CDN purge, Redis flush, APIM cache reset
• Use apply_security_recommendation for: Defender recommendations — enable HTTPS, diagnostic logging, NSG rules, encryption
• Use execute_runbook for: predefined automation playbooks — high-memory-restart, scale-out-on-cpu, clear-stale-cache, rotate-app-secret
• Use execute_safe_restart for: legacy restart path (prefer safe_restart_resource for new requests)
• Use scale_resource for: manual scaling operations
• Use execute_remediation_step for: step-by-step execution of a plan from generate_remediation_plan

REMEDIATION SAFETY MATRIX:
  dry_run=true      → Preview only, zero impact — ALWAYS use first
  confirmed=false   → Returns plan but does not execute
  confirmed=true    → Executes (still blocked by ALLOW_REAL_REMEDIATION for destructive ops)
  High/Critical severity security recommendations → ALWAYS blocked without ALLOW_REAL_REMEDIATION

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
  → container_app_list (enumerate Container Apps)
  → query_aks_configuration (bulk AKS config queries)
  → query_apim_configuration (bulk APIM config queries)

Application Insights & Tracing:
  → query_app_insights_traces (distributed tracing by operation ID)
  → get_request_telemetry (P95/P99 latencies, failure rates)
  → analyze_dependency_map (service-to-service dependencies)
  → get_app_insights_roles (discover valid app_name/cloud_RoleName values — call this FIRST when app_name is unknown)
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

CVE Vulnerability Management:
  → search_cve (search CVEs by ID, keyword, severity, CVSS score, or date filters)
  → scan_inventory (trigger CVE vulnerability scan on VM inventory)
  → get_patches (get patches that remediate a specific CVE)
  → trigger_remediation (trigger patch installation to remediate CVE on VM — requires dry_run then confirmation)

Anomaly Detection & Capacity:
  → detect_metric_anomalies (metric-level anomaly detection)
  → predict_resource_exhaustion (resource exhaustion forecasting)
  → predict_capacity_issues (capacity planning)

Log Analysis:
  → analyze_log_patterns (log pattern mining and clustering)

Remediation:
  → plan_remediation (impact assessment — always call first for legacy workflows)
  → generate_remediation_plan (detailed step-by-step plan with approval tokens)
  → safe_restart_resource (safe restart with drain + rollback — prefer over execute_safe_restart)
  → clear_resource_cache (flush CDN/Redis/APIM/app cache — use dry_run=true first)
  → apply_security_recommendation (apply Defender recommendation — use dry_run=true first)
  → execute_runbook (run named playbook: high-memory-restart, scale-out-on-cpu, clear-stale-cache, rotate-app-secret, enable-diagnostic-logging)
  → execute_safe_restart (legacy: restart with safety checks — requires approval)
  → scale_resource (scaling operation — requires approval)
  → clear_cache (legacy: cache invalidation — requires approval)
  → execute_remediation_step (execute plan step — requires approval + approval_token)
  → register_custom_runbook (register new automation runbook)

Notifications:
  → send_teams_notification (Teams channel notifications)
  → send_teams_alert (Teams critical alerts)
  → send_sre_status_update (SRE status updates)
  → get_audit_trail (operation audit history)

Self-Documentation:
  → describe_capabilities (list what this agent can do)
  → get_prompt_examples (example prompts by category)

PARAMETER GUIDANCE:
• workspace_id = Log Analytics workspace GUID (e.g. "65b615a0-7003-4058-88c5-0cf65ac5bb87").
  NEVER use the subscription ID as workspace_id — they are different values.
  The workspace_id comes from the [Azure grounding context] prepended to the query.
  analyze_dependency_map can auto-discover the workspace_id from env vars or Resource Graph;
  pass it explicitly when multiple workspaces exist.
  If workspace_id is unknown, call get_app_insights_roles without a workspace_id — it will
  attempt auto-discovery and list available app names.
• app_name = cloud_RoleName value in App Insights. Call get_app_insights_roles first
  when app_name is not provided by the user — NEVER guess or fabricate an app name.
• resource_id = full ARM resource ID
  (e.g. "/subscriptions/{sub}/resourceGroups/{rg}/providers/{type}/{name}").
  NEVER pass a subscription ID as a resource_id.
• subscription_id = subscription UUID only.
  Check [Azure grounding context] for the correct value.

COMMON WORKFLOWS:
• Health check → check_resource_health(resource_id) or check_container_app_health(name)
• VM health check → check_resource_health(resource_id for each VM in scope)
• Incident → triage_incident → search_logs_by_error → correlate_alerts → generate_incident_summary
• Performance → get_performance_metrics → identify_bottlenecks → get_capacity_recommendations
• Cost review → get_cost_analysis → identify_orphaned_resources → get_cost_recommendations
• SLO check → get_slo_dashboard → calculate_error_budget
• Security audit → get_security_score → list_security_recommendations → check_compliance_status
• CVE discovery → search_cve(cve_id or keyword) → present CVE details with severity
• CVE scanning → scan_inventory(subscription_id) → present scan results with affected VMs
• CVE patch discovery → get_patches(cve_id) → present available patches with KB numbers
• CVE remediation → get_patches(cve_id) → trigger_remediation(dry_run=true) → present plan → trigger_remediation(confirmed=true)
• Remediation → plan_remediation → present plan → wait for approval → safe_restart_resource(dry_run=true) → safe_restart_resource(confirmed=true)
• Cache issue → clear_resource_cache(dry_run=true) → present plan → clear_resource_cache(confirmed=true)
• Security fix → list_security_recommendations → apply_security_recommendation(dry_run=true) → present plan → apply_security_recommendation(confirmed=true)
• Runbook → execute_runbook (no args to list) → execute_runbook(runbook_id, dry_run=true) → execute_runbook(runbook_id, confirmed=true)
• Dependency map → get_app_insights_roles(workspace_id) → analyze_dependency_map(workspace_id, app_name)

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
        """Block destructive operations that haven't been confirmed.

        New Phase 3 tools (safe_restart_resource, clear_resource_cache,
        apply_security_recommendation, execute_runbook) implement their own
        dry_run / confirmed / ALLOW_REAL_REMEDIATION gates internally.
        The legacy tools (execute_safe_restart, scale_resource, clear_cache,
        execute_remediation_step) are gated here as a second layer of defense.
        """
        # Legacy tools: hard-block without ALLOW_REAL_REMEDIATION
        legacy_destructive_tools = {
            "execute_safe_restart", "scale_resource", "clear_cache",
            "execute_remediation_step",
        }
        # Phase 3 tools: block if confirmed is not set AND dry_run is not set
        phase3_destructive_tools = {
            "safe_restart_resource", "clear_resource_cache",
            "apply_security_recommendation", "execute_runbook",
        }

        if tool_name in legacy_destructive_tools:
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

        if tool_name in phase3_destructive_tools:
            # Allow dry_run calls without restriction
            if arguments.get("dry_run") is True:
                return None  # pass through
            # Allow confirmed=false (returns plan, no execution)
            if not arguments.get("confirmed", False):
                return None  # pass through — tool will return plan only
            # confirmed=true: enforce ALLOW_REAL_REMEDIATION for execution
            allow_real = os.getenv("ALLOW_REAL_REMEDIATION", "false").lower() == "true"
            if not allow_real:
                return {
                    "success": False,
                    "blocked": True,
                    "error": (
                        f"Tool '{tool_name}' with confirmed=true blocked: "
                        "ALLOW_REAL_REMEDIATION is not enabled. "
                        "Set ALLOW_REAL_REMEDIATION=true to allow real execution. "
                        "Use dry_run=true to preview without executing."
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
