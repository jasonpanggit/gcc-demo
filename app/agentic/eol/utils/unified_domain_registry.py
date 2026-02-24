"""Unified domain registry for the MCP orchestrator pipeline.

Defines the 13 operational domains, their MCP source labels, sub-agent classes,
and tool budgets. Used by Router, ToolRetriever, and Executor to scope tool
selection and delegate to specialist agents.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, List, Optional, Type


class UnifiedDomain(str, Enum):
    """Operational domains recognised by the MCP orchestrator pipeline."""

    AZURE_MANAGEMENT = "azure_management"
    SRE_HEALTH = "sre_health"
    SRE_INCIDENT = "sre_incident"
    SRE_PERFORMANCE = "sre_performance"
    SRE_COST_SECURITY = "sre_cost_security"
    SRE_RCA = "sre_rca"
    SRE_REMEDIATION = "sre_remediation"
    OBSERVABILITY = "observability"
    ARC_INVENTORY = "arc_inventory"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    NETWORK = "network"
    GENERAL = "general"


@dataclass(frozen=True)
class DomainRegistryEntry:
    """Configuration for a single operational domain."""

    domain: UnifiedDomain
    sources: FrozenSet[str]           # MCP source labels (matches CompositeMCPClient labels)
    max_tools: int                    # Max tools sent to LLM for this domain
    sub_agent_class_path: Optional[str] = None  # "module.ClassName" — lazy-imported
    notes: str = ""


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_ENTRIES: List[DomainRegistryEntry] = [
    DomainRegistryEntry(
        domain=UnifiedDomain.AZURE_MANAGEMENT,
        sources=frozenset({"azure", "azure_cli", "compute", "storage"}),
        max_tools=15,
        sub_agent_class_path=None,  # Direct execution via semantic retrieval
        notes="Azure resource management: VMs, RGs, storage, identity, AI. "
              "Semantic retrieval from ~85 tools.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_HEALTH,
        sources=frozenset({"sre"}),
        max_tools=10,
        sub_agent_class_path="app.agentic.eol.agents.health_monitoring_agent.HealthMonitoringAgent",
        notes="Health checks, diagnostics, configuration analysis.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_INCIDENT,
        sources=frozenset({"sre"}),
        max_tools=9,
        sub_agent_class_path="app.agentic.eol.agents.incident_response_agent.IncidentResponseAgent",
        notes="Incident triage, log search, alert correlation.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_PERFORMANCE,
        sources=frozenset({"sre"}),
        max_tools=11,
        sub_agent_class_path="app.agentic.eol.agents.performance_analysis_agent.PerformanceAnalysisAgent",
        notes="Metrics, bottlenecks, SLO / error budget analysis.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_COST_SECURITY,
        sources=frozenset({"sre"}),
        max_tools=11,
        sub_agent_class_path="app.agentic.eol.agents.cost_optimization_agent.CostOptimizationAgent",
        notes="Cost analysis, Defender alerts, compliance checks. "
              "SecurityComplianceAgent also covers this domain.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_RCA,
        sources=frozenset({"sre"}),
        max_tools=8,
        sub_agent_class_path=None,  # SRESubAgent fallback; no dedicated RCA agent yet
        notes="Root cause analysis, dependency tracing, postmortems. "
              "Uses SRESubAgent as fallback — spans health + incident + performance.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.SRE_REMEDIATION,
        sources=frozenset({"sre", "azure_cli"}),
        max_tools=8,
        sub_agent_class_path="app.agentic.eol.agents.remediation_agent.RemediationAgent",
        notes="Restart, scale, cache clear. DESTRUCTIVE gate required.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.OBSERVABILITY,
        sources=frozenset({"monitor"}),
        max_tools=8,
        sub_agent_class_path="app.agentic.eol.agents.monitor_agent.MonitorAgent",
        notes="Azure Monitor Community: workbooks, alerts, KQL queries.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.ARC_INVENTORY,
        sources=frozenset({"inventory", "os_eol"}),
        max_tools=9,
        sub_agent_class_path=None,  # Simple tools, direct execution
        notes="Arc server OS/software inventory and EOL lookups.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.DEPLOYMENT,
        sources=frozenset({"azure_cli", "azure"}),
        max_tools=8,
        sub_agent_class_path="app.agentic.eol.agents.deployment_agent.DeploymentAgent",
        notes="Deploy/validate/rollback chains: azure_cli + azure_deploy + azd. "
              "DeploymentAgent not yet implemented (Phase 6).",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.DOCUMENTATION,
        sources=frozenset({"azure"}),
        max_tools=5,
        sub_agent_class_path=None,
        notes="MS Learn, Azure best practices, architecture guidance. Direct execution.",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.NETWORK,
        sources=frozenset({"network"}),
        max_tools=8,
        sub_agent_class_path="app.agentic.eol.agents.network_agent.NetworkAgent",
        notes="Network topology, NSG rules, connectivity diagnostics. "
              "7 read-only diagnostic tools via NetworkAgent (Phase 3).",
    ),
    DomainRegistryEntry(
        domain=UnifiedDomain.GENERAL,
        sources=frozenset({"azure", "sre", "monitor", "inventory", "os_eol", "azure_cli", "compute", "storage"}),
        max_tools=32,  # Fallback: broad coverage
        sub_agent_class_path=None,
        notes="Fallback domain when no specific domain matches.",
    ),
]

_REGISTRY: dict[UnifiedDomain, DomainRegistryEntry] = {e.domain: e for e in _ENTRIES}


# ---------------------------------------------------------------------------
# Registry accessors
# ---------------------------------------------------------------------------

class UnifiedDomainRegistry:
    """Read-only registry for domain → sources / sub-agent / budget lookups."""

    @staticmethod
    def get_entry(domain: UnifiedDomain) -> DomainRegistryEntry:
        return _REGISTRY[domain]

    @staticmethod
    def get_sources(domain: UnifiedDomain) -> FrozenSet[str]:
        return _REGISTRY[domain].sources

    @staticmethod
    def get_max_tools(domain: UnifiedDomain) -> int:
        return _REGISTRY[domain].max_tools

    @staticmethod
    def get_sub_agent_class(domain: UnifiedDomain) -> Optional[Type]:
        """Lazily import and return the sub-agent class for *domain*, or None."""
        path = _REGISTRY[domain].sub_agent_class_path
        if not path:
            return None
        try:
            module_path, class_name = path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError):
            return None

    @staticmethod
    def all_domains() -> List[UnifiedDomain]:
        return list(_REGISTRY.keys())

    @staticmethod
    def domains_for_source(source: str) -> List[UnifiedDomain]:
        """Return all domains that include *source* in their sources set."""
        return [
            entry.domain
            for entry in _ENTRIES
            if source in entry.sources
        ]
