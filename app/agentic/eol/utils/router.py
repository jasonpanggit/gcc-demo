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

import logging
import os
from dataclasses import dataclass, field
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


@dataclass
class DomainMatch:
    """A single domain classification result."""

    domain: UnifiedDomain
    confidence: float               # 0.0 – 1.0; 1.0 = exact pattern match
    matched_signals: List[str] = field(default_factory=list)   # which patterns triggered
    from_entity_hint: bool = False  # True if confidence boosted by entity extraction


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
        """
        if not query:
            return [DomainMatch(domain=UnifiedDomain.GENERAL, confidence=0.1,
                                matched_signals=["empty_query"])]

        # Step 1: classify via QueryPatterns (deterministic, <1ms)
        legacy_domains = QueryPatterns.classify_domains(query)
        active_legacy = [d for d, active in legacy_domains.items() if active]

        # Step 2: extract entity hints (regex, no Azure I/O)
        entity_hints = await self._inventory.extract_entities(query)

        # Step 3: build domain matches from legacy classification
        matches: Dict[UnifiedDomain, DomainMatch] = {}

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

        # Step 4: boost confidence from entity type hints
        for resource_type in entity_hints.possible_types:
            boost_domain = _TYPE_DOMAIN_BOOST.get(resource_type)
            if boost_domain:
                if boost_domain not in matches:
                    matches[boost_domain] = DomainMatch(
                        domain=boost_domain,
                        confidence=0.6,
                        matched_signals=[f"entity_type:{resource_type}"],
                        from_entity_hint=True,
                    )
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
            for domain in UnifiedDomainRegistry.all_domains():
                entry = UnifiedDomainRegistry.get_entry(domain)
                if entry.sources & prior_sources and domain not in matches:
                    matches[domain] = DomainMatch(
                        domain=domain,
                        confidence=0.5,
                        matched_signals=[f"prior_source:{s}" for s in prior_sources & entry.sources],
                    )

        # Step 6: ensure GENERAL fallback is always present
        if UnifiedDomain.GENERAL not in matches:
            matches[UnifiedDomain.GENERAL] = DomainMatch(
                domain=UnifiedDomain.GENERAL,
                confidence=0.1 if matches else 0.5,
                matched_signals=["fallback"],
            )

        ranked = sorted(matches.values(), key=lambda m: m.confidence, reverse=True)

        logger.debug(
            "Router: query=%r → %d domain(s): %s",
            query[:80],
            len(ranked),
            [(m.domain.value, f"{m.confidence:.2f}") for m in ranked[:5]],
        )
        return ranked

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
