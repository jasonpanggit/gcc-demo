"""Unified routing pipeline for all query types.

Consolidates 3 parallel routing systems (ToolRouter, ToolEmbedder, direct
orchestrator routing) into a single pipeline with configurable strategies.

Pipeline stages:
    1. Domain Classification  — keyword-based, <5ms
    2. Orchestrator Selection — deterministic domain→orchestrator map
    3. Tool Retrieval         — registry lookup, strategy-aware
    4. Plan Generation        — builds RoutingPlan with timing metadata
    (Execution happens in the calling orchestrator, not here)

Strategies:
    "fast"          — primary domain tools only, capped at 10
    "quality"       — primary + secondary domain tools, ranked, capped at 15
    "comprehensive" — pass empty list (orchestrator uses full catalog)

Performance target: <200ms p90 for full route() call (keyword path is ~1ms).

Usage:
    router = UnifiedRouter(tool_registry, domain_classifier)
    plan   = await router.route("List all NSG rules", strategy="fast")
    # plan.orchestrator == "mcp"
    # plan.domain       == DomainLabel.NETWORK
    # plan.tools        == ["list_nsg_rules", ...]
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

try:
    from app.agentic.eol.utils.domain_classifier import (
        DomainClassifier,
        DomainClassification,
        DomainLabel,
        get_domain_classifier,
    )
    from app.agentic.eol.utils.tool_registry import MCPToolRegistry, get_tool_registry
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.domain_classifier import (  # type: ignore[import-not-found]
        DomainClassifier,
        DomainClassification,
        DomainLabel,
        get_domain_classifier,
    )
    from utils.tool_registry import MCPToolRegistry, get_tool_registry  # type: ignore[import-not-found]
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

# Type alias exported for consumers
RoutingStrategy = Literal["fast", "quality", "comprehensive"]

# Tool count limits per strategy
_FAST_TOOL_LIMIT = 10
_QUALITY_TOOL_LIMIT = 15


@dataclass
class RoutingPlan:
    """Plan produced by UnifiedRouter.route().

    This is the *routing* plan (domain, orchestrator, tools to use).
    It is distinct from agents.orchestrator_models.ExecutionPlan, which
    describes the step-by-step execution inside an orchestrator.

    Attributes:
        orchestrator:         "mcp" or "sre"
        domain:               Primary domain label
        tools:                Tool names to pass to the orchestrator
                              (empty list → orchestrator uses full catalog)
        confidence:           Classification confidence [0.0, 1.0]
        strategy_used:        Which routing strategy was applied
        classification_time_ms: Wall-clock ms for the full route() call
        secondary_domains:    Additional domains detected (informational)
    """
    orchestrator: str
    domain: DomainLabel
    tools: List[str]
    confidence: float
    strategy_used: RoutingStrategy
    classification_time_ms: float
    secondary_domains: List[DomainLabel] = field(default_factory=list)


# Legacy name alias kept for any future code that uses ExecutionPlan from this module.
# Prefer RoutingPlan in new code.
ExecutionPlan = RoutingPlan


class UnifiedRouter:
    """Single routing pipeline for all query types.

    Replaces the three parallel paths that previously existed:
    - ToolRouter (keyword-based)
    - ToolEmbedder (semantic)
    - Direct orchestrator routing (ad-hoc per-orchestrator logic)

    The router itself does NOT execute queries — it returns a RoutingPlan
    that the calling orchestrator uses to set up its tool context.

    Thread safety: stateless after __init__, safe to share across requests.
    """

    # Canonical domain → orchestrator mapping.
    # SRE and MONITORING go to the SRE orchestrator;
    # everything else goes to the MCP orchestrator.
    _DOMAIN_TO_ORCHESTRATOR: Dict[DomainLabel, str] = {
        DomainLabel.SRE: "sre",
        DomainLabel.MONITORING: "sre",
        DomainLabel.NETWORK: "mcp",
        DomainLabel.INVENTORY: "mcp",
        DomainLabel.PATCH: "mcp",
        DomainLabel.COMPUTE: "mcp",
        DomainLabel.STORAGE: "mcp",
        DomainLabel.COST: "mcp",
        DomainLabel.SECURITY: "mcp",
        DomainLabel.GENERAL: "mcp",
    }

    def __init__(
        self,
        tool_registry: MCPToolRegistry,
        domain_classifier: DomainClassifier,
    ) -> None:
        """Initialise the router.

        Args:
            tool_registry:    Populated MCPToolRegistry singleton.
            domain_classifier: DomainClassifier instance (keyword-based).
        """
        self.tool_registry = tool_registry
        self.domain_classifier = domain_classifier

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def route(
        self,
        query: str,
        context: Optional[Dict] = None,
        strategy: RoutingStrategy = "fast",
    ) -> RoutingPlan:
        """Route a user query through the pipeline.

        Args:
            query:    User's natural language query.
            context:  Optional context dict (tenant, subscription, etc.).
                      Not currently used but reserved for future enrichment.
            strategy: Routing strategy — "fast" | "quality" | "comprehensive".

        Returns:
            RoutingPlan with orchestrator, tools, and timing metadata.

        Performance:
            "fast" path (keyword classifier + registry lookup): <10ms typical.
            p90 target: <200ms.
        """
        t0 = time.perf_counter()

        # Stage 1: Domain Classification
        classification: DomainClassification = await self.domain_classifier.classify(query)

        # Stage 2: Orchestrator Selection
        orchestrator = self._select_orchestrator(classification)

        # Stage 3: Tool Retrieval (strategy-dependent)
        tools = await self._retrieve_tools(classification, orchestrator, strategy)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.debug(
            "UnifiedRouter.route: query=%r → domain=%s orchestrator=%s tools=%d strategy=%s (%.1fms)",
            query[:80],
            classification.primary_domain.value,
            orchestrator,
            len(tools),
            strategy,
            elapsed_ms,
        )

        return RoutingPlan(
            orchestrator=orchestrator,
            domain=classification.primary_domain,
            tools=tools,
            confidence=classification.confidence,
            strategy_used=strategy,
            classification_time_ms=elapsed_ms,
            secondary_domains=classification.secondary_domains,
        )

    # ----------------------------------------------------------------
    # Internal pipeline stages
    # ----------------------------------------------------------------

    def _select_orchestrator(self, classification: DomainClassification) -> str:
        """Map primary domain to the appropriate orchestrator label."""
        return self._DOMAIN_TO_ORCHESTRATOR.get(
            classification.primary_domain,
            "mcp",  # Safe default
        )

    async def _retrieve_tools(
        self,
        classification: DomainClassification,
        orchestrator: str,
        strategy: RoutingStrategy,
    ) -> List[str]:
        """Retrieve relevant tool names based on domain and strategy.

        Returns:
            List of tool name strings. Empty list means the orchestrator
            should use its full catalog (comprehensive mode).
        """
        if strategy == "fast":
            # Primary domain only — fast path
            tools = self.tool_registry.get_tools_by_domain(
                classification.primary_domain.value
            )
            return [t.name for t in tools[:_FAST_TOOL_LIMIT]]

        elif strategy == "quality":
            # Primary domain (weight 1.0) + secondary domains (weight 0.5)
            primary_tools = self.tool_registry.get_tools_by_domain(
                classification.primary_domain.value
            )
            weighted: List[tuple] = [(t, 1.0) for t in primary_tools]

            for domain in classification.secondary_domains:
                secondary_tools = self.tool_registry.get_tools_by_domain(domain.value)
                weighted.extend((t, 0.5) for t in secondary_tools)

            # Stable sort: primary tools first, then secondary
            weighted.sort(key=lambda x: x[1], reverse=True)

            # Deduplicate (tool may appear in multiple domains)
            seen: set = set()
            result: List[str] = []
            for tool, _ in weighted:
                if tool.name not in seen:
                    seen.add(tool.name)
                    result.append(tool.name)
                if len(result) >= _QUALITY_TOOL_LIMIT:
                    break
            return result

        else:  # "comprehensive"
            # Empty list → orchestrator uses full available catalog
            return []


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_router_instance: Optional[UnifiedRouter] = None


def get_unified_router() -> UnifiedRouter:
    """Return the module-level UnifiedRouter singleton.

    Initialises with the shared MCPToolRegistry and DomainClassifier singletons
    on first call.
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = UnifiedRouter(
            tool_registry=get_tool_registry(),
            domain_classifier=get_domain_classifier(),
        )
    return _router_instance
