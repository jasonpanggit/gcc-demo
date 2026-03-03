"""Pipeline Router — Stage 1 of the MCP orchestrator pipeline.

Classifies a user query into operational domains and produces entity hints
(resource names / types mentioned in the query) that downstream components
(ToolRetriever, Planner) can use without extra Azure API calls.

Design goals:
- No LLM calls — purely deterministic, <1ms
- Wraps the existing ToolRouter / QueryPatterns infrastructure unchanged
- Emits structured DomainMatch objects instead of raw source lists
- Entity hints are extracted by ResourceInventoryService (regex-only, no I/O)

Usage:
    router = Router()
    matches = await router.route(query)
    # matches: [DomainMatch(domain=SRE_HEALTH, confidence=0.9, ...), ...]
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

try:
    from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain, UnifiedDomainRegistry
    from app.agentic.eol.utils.query_patterns import QueryPatterns
    from app.agentic.eol.utils.resource_inventory_service import (
        EntityHints,
        ResourceInventoryService,
        get_resource_inventory_service,
    )
except ModuleNotFoundError:
    from utils.unified_domain_registry import UnifiedDomain, UnifiedDomainRegistry  # type: ignore[import-not-found]
    from utils.query_patterns import QueryPatterns  # type: ignore[import-not-found]
    from utils.resource_inventory_service import (  # type: ignore[import-not-found]
        EntityHints,
        ResourceInventoryService,
        get_resource_inventory_service,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping from QueryPatterns legacy domain strings → UnifiedDomain
# This preserves backward compatibility with QueryPatterns.classify_domains()
# output while expressing results in the new domain vocabulary.
# ---------------------------------------------------------------------------

_LEGACY_TO_UNIFIED: Dict[str, List[UnifiedDomain]] = {
    "sre":               [UnifiedDomain.SRE_HEALTH, UnifiedDomain.SRE_INCIDENT,
                          UnifiedDomain.SRE_PERFORMANCE, UnifiedDomain.SRE_RCA],
    "cost":              [UnifiedDomain.SRE_COST_SECURITY],
    "security":          [UnifiedDomain.SRE_COST_SECURITY],
    "slo":               [UnifiedDomain.SRE_PERFORMANCE],
    "app_insights":      [UnifiedDomain.SRE_INCIDENT, UnifiedDomain.SRE_PERFORMANCE],
    "monitoring":        [UnifiedDomain.OBSERVABILITY],
    "eol":               [UnifiedDomain.ARC_INVENTORY],
    "inventory":         [UnifiedDomain.ARC_INVENTORY],
    "resource_management": [UnifiedDomain.AZURE_MANAGEMENT],
    "network":           [UnifiedDomain.NETWORK, UnifiedDomain.AZURE_MANAGEMENT],
    "cli":               [UnifiedDomain.DEPLOYMENT],
    "capabilities":      [UnifiedDomain.DOCUMENTATION],
}

# Entity type → domain hint (used to boost domain confidence from entity hints)
_TYPE_DOMAIN_BOOST: Dict[str, UnifiedDomain] = {
    "Microsoft.App/containerApps":              UnifiedDomain.SRE_HEALTH,
    "Microsoft.ContainerService/managedClusters": UnifiedDomain.SRE_HEALTH,
    "Microsoft.Compute/virtualMachines":        UnifiedDomain.AZURE_MANAGEMENT,
    "Microsoft.Storage/storageAccounts":        UnifiedDomain.AZURE_MANAGEMENT,
    "Microsoft.KeyVault/vaults":                UnifiedDomain.AZURE_MANAGEMENT,
    "Microsoft.Web/sites":                      UnifiedDomain.SRE_HEALTH,
    "Microsoft.DocumentDB/databaseAccounts":    UnifiedDomain.AZURE_MANAGEMENT,
    "Microsoft.Cache/redis":                    UnifiedDomain.AZURE_MANAGEMENT,
    "Microsoft.Network/virtualNetworks":        UnifiedDomain.NETWORK,
    "Microsoft.Network/networkSecurityGroups":  UnifiedDomain.NETWORK,
    "Microsoft.ApiManagement/service":          UnifiedDomain.SRE_INCIDENT,
    "Microsoft.Sql/servers":                    UnifiedDomain.AZURE_MANAGEMENT,
}


# ---------------------------------------------------------------------------
# Telemetry: RoutingDecisionLog — Phase 2 observability
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecisionLog:
    """Full telemetry for a single route() call.

    Captures the complete routing decision pipeline: query classification,
    entity extraction, domain matching, confidence boosting, and guardrail
    activations.  Serializable via ``to_dict()`` for JSON logging and API responses.
    """

    query: str = ""
    timestamp_ms: float = 0.0
    duration_ms: float = 0.0

    # Step 1: Legacy classification
    legacy_domains_active: List[str] = field(default_factory=list)
    legacy_domains_inactive: List[str] = field(default_factory=list)

    # Step 2: Entity extraction
    entity_names: List[str] = field(default_factory=list)
    entity_types: List[str] = field(default_factory=list)

    # Step 3: Domain matching
    routing_path: str = ""
    """'pattern_match', 'entity_boost', 'prior_source', or 'fallback'."""
    domain_matches_with_confidence: List[Dict[str, Any]] = field(default_factory=list)
    """[{domain, confidence, signals, from_entity_hint}, ...]."""

    # Deterministic guardrails triggered
    guardrails_triggered: List[str] = field(default_factory=list)
    """e.g. ['container_app_list_boost', 'vm_health_boost']."""

    # Entity-type boosts applied
    entity_type_boosts: List[Dict[str, Any]] = field(default_factory=list)
    """[{resource_type, boosted_domain, confidence_delta}, ...]."""

    # Prior-source continuity
    prior_sources_used: List[str] = field(default_factory=list)
    domains_from_prior: List[str] = field(default_factory=list)

    # Final output
    final_domain_count: int = 0
    top_domain: str = ""
    top_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for logging and API responses."""
        return asdict(self)


@dataclass
class DomainMatch:
    """A single domain classification result."""

    domain: UnifiedDomain
    confidence: float               # 0.0 – 1.0; 1.0 = exact pattern match
    matched_signals: List[str] = field(default_factory=list)   # which patterns triggered
    from_entity_hint: bool = False  # True if confidence boosted by entity extraction
    routing_log: Optional[RoutingDecisionLog] = None
    """Attached to the first DomainMatch in the ranked list for downstream access."""


class Router:
    """Pipeline Router — deterministic query → domain classification.

    Wraps ``ToolRouter`` / ``QueryPatterns`` as Stage 1 of the new pipeline.
    Adds:
    - Structured ``DomainMatch`` output (domain + confidence + signals)
    - Entity-hint-aware domain boosting via ``ResourceInventoryService``
    - ``UnifiedDomain`` vocabulary (vs. legacy string domain names)

    Falls back gracefully: if ``QueryPatterns`` finds no match, returns
    ``[DomainMatch(GENERAL, 0.1)]`` so the pipeline always has at least one domain.
    """

    def __init__(
        self,
        inventory_service: Optional[ResourceInventoryService] = None,
    ) -> None:
        self._inventory = inventory_service or get_resource_inventory_service()

    async def route(
        self,
        query: str,
        prior_tool_names: Optional[List[str]] = None,
        tool_source_map: Optional[Dict[str, str]] = None,
    ) -> List[DomainMatch]:
        """Classify *query* into a ranked list of operational domains.

        Args:
            query:           User's natural-language message.
            prior_tool_names: Tool names used in prior iterations — used to
                              maintain domain focus across ReAct steps.
            tool_source_map:  Optional mapping of tool_name → source label (same
                              as used by ToolRouter) — used to derive additional
                              domain hints from prior tool names.

        Returns:
            Non-empty list of DomainMatch, ranked by confidence (highest first).
            Always contains at least GENERAL as the final fallback.
            The first DomainMatch carries a ``routing_log`` with full telemetry.
        """
        route_start = time.monotonic()
        rlog = RoutingDecisionLog(
            query=query,
            timestamp_ms=time.time() * 1000,
        )

        if not query:
            rlog.routing_path = "empty_query"
            rlog.duration_ms = (time.monotonic() - route_start) * 1000
            rlog.final_domain_count = 1
            rlog.top_domain = UnifiedDomain.GENERAL.value
            rlog.top_confidence = 0.1
            self._emit_routing_log(rlog)
            result = DomainMatch(
                domain=UnifiedDomain.GENERAL, confidence=0.1,
                matched_signals=["empty_query"], routing_log=rlog,
            )
            return [result]

        # Step 1: classify via QueryPatterns (deterministic, <1ms)
        legacy_domains = QueryPatterns.classify_domains(query)
        active_legacy = [d for d, active in legacy_domains.items() if active]
        inactive_legacy = [d for d, active in legacy_domains.items() if not active]
        rlog.legacy_domains_active = active_legacy
        rlog.legacy_domains_inactive = inactive_legacy

        # Step 2: extract entity hints (regex, no Azure I/O)
        entity_hints = await self._inventory.extract_entities(query)
        rlog.entity_names = list(getattr(entity_hints, "possible_names", []) or [])
        rlog.entity_types = list(getattr(entity_hints, "possible_types", []) or [])

        # Step 3: build domain matches from legacy classification
        matches: Dict[UnifiedDomain, DomainMatch] = {}
        routing_path_parts: List[str] = []

        for legacy in active_legacy:
            unified_list = _LEGACY_TO_UNIFIED.get(legacy, [])
            for unified in unified_list:
                if unified not in matches:
                    matches[unified] = DomainMatch(
                        domain=unified,
                        confidence=0.8,
                        matched_signals=[legacy],
                    )
                else:
                    # Multiple legacy domains pointing here → higher confidence
                    existing = matches[unified]
                    existing.confidence = min(1.0, existing.confidence + 0.1)
                    if legacy not in existing.matched_signals:
                        existing.matched_signals.append(legacy)

        if active_legacy:
            routing_path_parts.append("pattern_match")

        # Step 3b: deterministic intent boost for Container Apps list/discovery.
        # This ensures SRE list tools (e.g., container_app_list) are available
        # even when QueryPatterns classifies the query as deployment/cli only.
        if re.search(r"\b(show|list|get|display|enumerate|what\s+are)\b", query, re.I) and re.search(
            r"\bcontainer\s*apps?\b|\bcontainerapps?\b", query, re.I
        ):
            rlog.guardrails_triggered.append("container_app_list_boost")
            existing = matches.get(UnifiedDomain.SRE_HEALTH)
            if existing is None:
                matches[UnifiedDomain.SRE_HEALTH] = DomainMatch(
                    domain=UnifiedDomain.SRE_HEALTH,
                    confidence=0.9,
                    matched_signals=["intent:container_app_list"],
                    from_entity_hint=False,
                )
            else:
                existing.confidence = min(1.0, max(existing.confidence, 0.9))
                if "intent:container_app_list" not in existing.matched_signals:
                    existing.matched_signals.append("intent:container_app_list")

        # Step 3c: deterministic intent boost for VM health/status queries.
        # Keep VM operational health in SRE scope while preserving general VM
        # inventory and management routing in Azure Management.
        if re.search(r"\b(vms?|virtual\s+machines?)\b", query, re.I) and re.search(
            r"\b(health|healthy|status|unhealthy|degraded|availability)\b", query, re.I
        ):
            rlog.guardrails_triggered.append("vm_health_boost")
            existing = matches.get(UnifiedDomain.SRE_HEALTH)
            if existing is None:
                matches[UnifiedDomain.SRE_HEALTH] = DomainMatch(
                    domain=UnifiedDomain.SRE_HEALTH,
                    confidence=0.95,
                    matched_signals=["intent:vm_health"],
                    from_entity_hint=False,
                )
            else:
                existing.confidence = min(1.0, max(existing.confidence, 0.95))
                if "intent:vm_health" not in existing.matched_signals:
                    existing.matched_signals.append("intent:vm_health")

        # Step 4: boost confidence from entity type hints
        for resource_type in entity_hints.possible_types:
            boost_domain = _TYPE_DOMAIN_BOOST.get(resource_type)
            if boost_domain:
                confidence_delta = 0.15 if boost_domain in matches else 0.6
                rlog.entity_type_boosts.append({
                    "resource_type": resource_type,
                    "boosted_domain": boost_domain.value,
                    "confidence_delta": round(confidence_delta, 3),
                })
                if boost_domain not in matches:
                    matches[boost_domain] = DomainMatch(
                        domain=boost_domain,
                        confidence=0.6,
                        matched_signals=[f"entity_type:{resource_type}"],
                        from_entity_hint=True,
                    )
                    routing_path_parts.append("entity_boost")
                else:
                    existing = matches[boost_domain]
                    existing.confidence = min(1.0, existing.confidence + 0.15)
                    existing.matched_signals.append(f"entity_type:{resource_type}")
                    existing.from_entity_hint = True

        # Step 5: incorporate prior tool sources to maintain domain focus
        if prior_tool_names and tool_source_map:
            prior_sources: Set[str] = set()
            for tool_name in prior_tool_names:
                src = tool_source_map.get(tool_name, "")
                if src:
                    prior_sources.add(src)
            rlog.prior_sources_used = sorted(prior_sources)
            for domain in UnifiedDomainRegistry.all_domains():
                entry = UnifiedDomainRegistry.get_entry(domain)
                if entry.sources & prior_sources and domain not in matches:
                    matches[domain] = DomainMatch(
                        domain=domain,
                        confidence=0.5,
                        matched_signals=[f"prior_source:{s}" for s in prior_sources & entry.sources],
                    )
                    rlog.domains_from_prior.append(domain.value)
            if rlog.domains_from_prior:
                routing_path_parts.append("prior_source")

        # Step 6: ensure GENERAL fallback is always present
        if UnifiedDomain.GENERAL not in matches:
            matches[UnifiedDomain.GENERAL] = DomainMatch(
                domain=UnifiedDomain.GENERAL,
                confidence=0.1 if matches else 0.5,
                matched_signals=["fallback"],
            )
            if not routing_path_parts:
                routing_path_parts.append("fallback")

        ranked = sorted(matches.values(), key=lambda m: m.confidence, reverse=True)

        # Finalize routing log
        rlog.routing_path = "+".join(routing_path_parts) if routing_path_parts else "fallback"
        rlog.domain_matches_with_confidence = [
            {
                "domain": m.domain.value,
                "confidence": round(m.confidence, 3),
                "signals": m.matched_signals,
                "from_entity_hint": m.from_entity_hint,
            }
            for m in ranked
        ]
        rlog.final_domain_count = len(ranked)
        if ranked:
            rlog.top_domain = ranked[0].domain.value
            rlog.top_confidence = round(ranked[0].confidence, 3)
        rlog.duration_ms = (time.monotonic() - route_start) * 1000

        # Attach log to the first match for downstream access
        ranked[0].routing_log = rlog

        # Emit structured telemetry
        self._emit_routing_log(rlog)

        logger.debug(
            "Router: query=%r → %d domain(s): %s",
            query[:80],
            len(ranked),
            [(m.domain.value, f"{m.confidence:.2f}") for m in ranked[:5]],
        )
        return ranked

    @staticmethod
    def _emit_routing_log(rlog: RoutingDecisionLog) -> None:
        """Emit routing decision as structured JSON log at INFO level."""
        try:
            log_dict = {
                "event": "routing_decision_log",
                "query": rlog.query[:100],
                "routing_path": rlog.routing_path,
                "legacy_active": rlog.legacy_domains_active,
                "entity_types": rlog.entity_types,
                "guardrails": rlog.guardrails_triggered,
                "top_domain": rlog.top_domain,
                "top_confidence": rlog.top_confidence,
                "domain_count": rlog.final_domain_count,
                "duration_ms": round(rlog.duration_ms, 2),
            }
            logger.info("📊 RoutingDecisionLog: %s", json.dumps(log_dict, ensure_ascii=False))
        except Exception as exc:
            logger.debug("RoutingDecisionLog emit failed: %s", exc)

    def explain(self, query: str) -> Dict[str, Any]:
        """Return a synchronous diagnostic dict (no entity hints — sync only)."""
        legacy_domains = QueryPatterns.classify_domains(query)
        active = [d for d, v in legacy_domains.items() if v]
        sources: Set[str] = set()
        for d in active:
            for src in QueryPatterns.DOMAIN_SOURCE_MAP.get(d, []):
                sources.add(src)
        return {
            "query": query,
            "legacy_active_domains": active,
            "relevant_sources": sorted(sources),
            "unified_domains": [
                ud.value
                for d in active
                for ud in _LEGACY_TO_UNIFIED.get(d, [])
            ],
        }
