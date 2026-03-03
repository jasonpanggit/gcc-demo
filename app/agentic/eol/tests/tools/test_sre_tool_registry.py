"""Tests for SREToolRegistry — domain → tool subset mapping.

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import pytest

try:
    from app.agentic.eol.utils.sre_tool_registry import SREDomain, SREToolRegistry
except ModuleNotFoundError:
    from utils.sre_tool_registry import SREDomain, SREToolRegistry  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# All tool names defined in mcp_servers/sre_mcp_server.py (ground truth list)
# ---------------------------------------------------------------------------
KNOWN_SRE_TOOLS = {
    "check_resource_health",
    "check_container_app_health",
    "check_aks_cluster_health",
    "get_diagnostic_logs",
    "analyze_resource_configuration",
    "get_resource_dependencies",
    "triage_incident",
    "search_logs_by_error",
    "correlate_alerts",
    "analyze_activity_log",
    "generate_incident_summary",
    "get_performance_metrics",
    "identify_bottlenecks",
    "get_capacity_recommendations",
    "compare_baseline_metrics",
    "plan_remediation",
    "execute_safe_restart",
    "scale_resource",
    "clear_cache",
    "generate_remediation_plan",
    "execute_remediation_step",
    "register_custom_runbook",
    "send_teams_notification",
    "send_teams_alert",
    "get_audit_trail",
    "send_sre_status_update",
    "diagnose_app_service",
    "diagnose_apim",
    "query_app_service_configuration",
    "query_container_app_configuration",
    "container_app_list",
    "query_aks_configuration",
    "query_apim_configuration",
    "query_app_insights_traces",
    "get_request_telemetry",
    "analyze_dependency_map",
    "get_cost_analysis",
    "identify_orphaned_resources",
    "get_cost_recommendations",
    "analyze_cost_anomalies",
    "define_slo",
    "calculate_error_budget",
    "get_slo_dashboard",
    "get_security_score",
    "list_security_recommendations",
    "check_compliance_status",
    "detect_metric_anomalies",
    "predict_resource_exhaustion",
    "perform_root_cause_analysis",
    "trace_dependency_chain",
    "analyze_log_patterns",
    "detect_performance_anomalies",
    "predict_capacity_issues",
    "monitor_slo_burn_rate",
    "generate_postmortem",
    "calculate_mttr_metrics",
    "describe_capabilities",
    "get_prompt_examples",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_def(name: str) -> dict:
    """Create a minimal OpenAI function-calling format tool definition."""
    return {"type": "function", "function": {"name": name, "description": f"Tool {name}"}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSREDomain:
    """Basic enum sanity checks."""

    @pytest.mark.unit
    def test_all_domains_exist(self):
        for expected in ["health", "incident", "performance", "cost_security", "rca", "remediation"]:
            assert SREDomain(expected) is not None

    @pytest.mark.unit
    def test_general_domain_exists(self):
        assert SREDomain.GENERAL == "general"


class TestSREToolRegistryToolNames:
    """Tool name coverage and integrity tests."""

    @pytest.mark.unit
    @pytest.mark.parametrize("domain", [
        SREDomain.HEALTH,
        SREDomain.INCIDENT,
        SREDomain.PERFORMANCE,
        SREDomain.COST_SECURITY,
        SREDomain.RCA,
        SREDomain.REMEDIATION,
    ])
    def test_domain_has_minimum_tools(self, domain):
        """Each concrete domain must have at least 6 tools."""
        names = SREToolRegistry.get_tool_names(domain)
        assert len(names) >= 6, (
            f"Domain {domain.value!r} only has {len(names)} tools — minimum is 6"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("domain", [
        SREDomain.HEALTH,
        SREDomain.INCIDENT,
        SREDomain.PERFORMANCE,
        SREDomain.COST_SECURITY,
        SREDomain.RCA,
        SREDomain.REMEDIATION,
    ])
    def test_domain_does_not_exceed_maximum_tools(self, domain):
        """No domain should have more than 15 tools (token budget constraint)."""
        names = SREToolRegistry.get_tool_names(domain)
        assert len(names) <= 15, (
            f"Domain {domain.value!r} has {len(names)} tools — exceeds maximum of 15"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("domain", list(SREDomain))
    def test_all_tool_names_exist_in_sre_server(self, domain):
        """Every tool name in the registry must exist in sre_mcp_server.py."""
        names = SREToolRegistry.get_tool_names(domain)
        for name in names:
            assert name in KNOWN_SRE_TOOLS, (
                f"Tool {name!r} in domain {domain.value!r} is not defined in sre_mcp_server.py"
            )

    @pytest.mark.unit
    def test_no_duplicate_names_within_domain(self):
        """Tool names within a single domain must be unique."""
        for domain in SREDomain:
            names = SREToolRegistry.get_tool_names(domain)
            assert len(names) == len(set(names)), (
                f"Domain {domain.value!r} has duplicate tool names: {names}"
            )

    @pytest.mark.unit
    def test_all_tool_names_returns_superset(self):
        """all_tool_names() must include every tool from every domain."""
        all_names = set(SREToolRegistry.all_tool_names())
        for domain in SREDomain:
            for name in SREToolRegistry.get_tool_names(domain):
                assert name in all_names, (
                    f"Tool {name!r} from domain {domain.value!r} missing from all_tool_names()"
                )

    @pytest.mark.unit
    def test_all_domains_excludes_general(self):
        """all_domains() should not include GENERAL."""
        domains = SREToolRegistry.all_domains()
        assert SREDomain.GENERAL not in domains
        assert len(domains) == 6

    @pytest.mark.unit
    def test_domain_for_tool_known_tool(self):
        """domain_for_tool() returns a domain for a known tool."""
        result = SREToolRegistry.domain_for_tool("check_resource_health")
        assert result == SREDomain.HEALTH

    @pytest.mark.unit
    def test_domain_for_tool_unknown_returns_none(self):
        """domain_for_tool() returns None for an unregistered tool."""
        result = SREToolRegistry.domain_for_tool("nonexistent_tool_xyz")
        assert result is None


class TestSREToolRegistryFilterDefinitions:
    """Tests for get_tool_definitions() — filters OpenAI-format tool defs."""

    @pytest.mark.unit
    def test_filters_to_domain_tools_only(self):
        """get_tool_definitions() returns only tools in the requested domain."""
        health_names = SREToolRegistry.get_tool_names(SREDomain.HEALTH)
        # Create a mixed catalog: 3 health tools + 3 non-health tools
        catalog = [
            _make_tool_def(health_names[0]),
            _make_tool_def(health_names[1]),
            _make_tool_def(health_names[2]),
            _make_tool_def("get_cost_analysis"),          # cost_security
            _make_tool_def("triage_incident"),             # incident
            _make_tool_def("generate_postmortem"),         # rca
        ]
        result = SREToolRegistry.get_tool_definitions(SREDomain.HEALTH, catalog)
        result_names = {t["function"]["name"] for t in result}
        assert result_names == {health_names[0], health_names[1], health_names[2]}

    @pytest.mark.unit
    def test_empty_catalog_returns_empty(self):
        result = SREToolRegistry.get_tool_definitions(SREDomain.INCIDENT, [])
        assert result == []

    @pytest.mark.unit
    def test_preserves_original_order(self):
        """Filtered results preserve the order from the input catalog."""
        names = SREToolRegistry.get_tool_names(SREDomain.HEALTH)
        # Reverse the order in catalog
        catalog = [_make_tool_def(n) for n in reversed(names)]
        result = SREToolRegistry.get_tool_definitions(SREDomain.HEALTH, catalog)
        result_names = [t["function"]["name"] for t in result]
        # Should match reversed order (same as catalog order)
        assert result_names == list(reversed(names))

    @pytest.mark.unit
    def test_general_domain_returns_tools(self):
        """GENERAL domain returns a non-empty result."""
        names = SREToolRegistry.get_tool_names(SREDomain.GENERAL)
        catalog = [_make_tool_def(n) for n in names]
        result = SREToolRegistry.get_tool_definitions(SREDomain.GENERAL, catalog)
        assert len(result) > 0
