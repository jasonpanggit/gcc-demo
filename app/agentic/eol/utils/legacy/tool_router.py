"""Intent-based tool pre-filtering for the MCP orchestrator.

.. deprecated::
    ToolRouter is superseded by :class:`utils.unified_router.UnifiedRouter`
    (Phase 3 — unified routing pipeline).

    **Migration:**
    Replace ``ToolRouter.filter_tools_for_query()`` with::

        from utils.unified_router import get_unified_router
        plan = await get_unified_router().route(query, strategy="fast")

    ToolRouter remains functional for backward compatibility with
    MCPOrchestratorAgent's legacy ReAct path. New code should use
    UnifiedRouter. See ``utils/legacy/README.md`` for full migration guide.

Sits between the user query and the LLM call to reduce the number of tools
sent to the model.  Instead of shipping ~140 tools on every request, the router
classifies the query into operational domains and returns only the tools from
relevant MCP sources — typically 10-25 tools.

When classification is ambiguous (no domain matches), a bounded heuristic
subset is returned (never full-catalog fail-open).

Usage:
    router = ToolRouter(composite_client)
    filtered_tools = router.filter_tools_for_query(user_message, all_tools, source_map)
    # On iteration 2+, pass prior used tools to pin the domain:
    filtered_tools = router.filter_tools_for_query(
        user_message, all_tools, source_map,
        prior_tool_names=["check_resource_health", "get_diagnostic_logs"]
    )
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set

try:
    from app.agentic.eol.utils.query_patterns import QueryPatterns
except ModuleNotFoundError:
    from utils.query_patterns import QueryPatterns  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


class ToolRouter:
    """Pre-filter tool catalog based on query intent classification.

    Design goals:
    - Low latency: uses substring matching (no LLM call, no embeddings)
    - Bounded fallback: when intent is unclear, returns best-match subset
    - Composable: works with the existing CompositeMCPClient source filtering
    - Observable: logs which domains matched and how many tools were pruned

    The router does NOT replace the system prompt or tool descriptions — it only
    reduces the *number* of tools the LLM sees, keeping everything else intact.
    """

    # Meta-tools that should always be included regardless of domain
    _META_TOOLS = frozenset({
        "monitor_agent",
        "sre_agent",
        "describe_capabilities",
        "get_prompt_examples",
    })

    # Minimum tools to include even after filtering — safety net for edge cases
    _MIN_TOOL_COUNT = int(os.getenv("TOOL_ROUTER_MIN_TOOLS", "8"))

    # Hard cap for number of tools returned by router (tunable via env var)
    _MAX_TOOL_COUNT = int(os.getenv("TOOL_ROUTER_MAX_TOOLS", "32"))

    # When enabled, the router logs full domain classification on every query
    _DEBUG = os.getenv("TOOL_ROUTER_DEBUG", "").lower() in ("1", "true", "yes")

    def __init__(
        self,
        composite_client: Optional[Any] = None,
        *,
        min_tool_count: Optional[int] = None,
    ) -> None:
        """
        Args:
            composite_client: The CompositeMCPClient instance — used to access
                ``get_tools_by_sources()`` for source-level filtering.  If None,
                the router falls back to tool-name-based filtering on the
                pre-built tool definitions list.
            min_tool_count: Override the minimum tool count safety net.
        """
        self._client = composite_client
        if min_tool_count is not None:
            self._MIN_TOOL_COUNT = max(min_tool_count, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _tool_name(self, tool: Dict[str, Any]) -> str:
        return str(tool.get("function", {}).get("name", ""))

    def _tool_text(self, tool: Dict[str, Any]) -> str:
        function = tool.get("function", {}) if isinstance(tool.get("function", {}), dict) else {}
        name = str(function.get("name", ""))
        description = str(function.get("description", ""))
        return f"{name} {description}".lower()

    def _heuristic_select_tools(self, query: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select a compact subset by lexical overlap with query.

        Scoring:
        - +1 per query token found anywhere in the tool's name+description text
        - +4 if a query token exactly matches the tool name (strongest signal)
        - +2 if a query token is a prefix of the tool name
        - +1 bonus for read-oriented tool name prefixes (list_, get_, etc.)
        - +3 bonus for meta-tools (always highly relevant)

        Never returns the full catalog.
        """
        if not all_tools:
            return []

        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9_]+", (query or "").lower())
            if len(token) >= 3
        }

        scored: List[tuple[int, Dict[str, Any]]] = []
        for tool in all_tools:
            text = self._tool_text(tool)
            score = 0
            name = self._tool_name(tool)
            name_lower = name.lower()

            if query_tokens and text:
                score += sum(1 for token in query_tokens if token in text)

            # Strong bonuses when query tokens match the tool name directly
            if query_tokens:
                for token in query_tokens:
                    if token == name_lower:
                        score += 4  # Exact name match — strongest signal
                    elif name_lower.startswith(token):
                        score += 2  # Name starts with the token

            if name.startswith(("list_", "get_", "search_", "describe_")):
                score += 1

            if name in self._META_TOOLS:
                score += 3

            scored.append((score, tool))

        scored.sort(key=lambda item: item[0], reverse=True)

        selected = [tool for score, tool in scored if score > 0]
        if not selected:
            selected = [tool for _, tool in scored[: self._MIN_TOOL_COUNT]]

        return selected[: self._MAX_TOOL_COUNT]

    def filter_tools_for_query(
        self,
        query: str,
        all_tools: List[Dict[str, Any]],
        tool_source_map: Dict[str, str],
        prior_tool_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return the subset of *all_tools* relevant to *query*.

        Args:
            query: The user's natural-language message.
            all_tools: Full tool catalog (OpenAI function-calling format).
            tool_source_map: Mapping of tool_name → source label.
            prior_tool_names: Tool names used in prior iterations of this
                request.  When provided their source labels are added to the
                relevant set, keeping the LLM focused on the same domain it
                is already working in.

        Returns:
            Filtered list of tool definitions. Guaranteed to include:
            1. All meta-tools (monitor_agent, describe_capabilities, …)
            2. At least ``_MIN_TOOL_COUNT`` tools when available
        """
        if not all_tools:
            return []
        if not query:
            return self._heuristic_select_tools("", all_tools)

        domains = QueryPatterns.classify_domains(query)
        active_domains = [d for d, active in domains.items() if active]

        if self._DEBUG:
            logger.info(
                "🔍 ToolRouter domain classification: query=%r → domains=%s",
                query[:120],
                active_domains or "(none — heuristic subset)",
            )

        # Collect relevant source labels from domain classification
        relevant_sources: Set[str] = set()
        for domain in active_domains:
            for src in QueryPatterns.DOMAIN_SOURCE_MAP.get(domain, []):
                relevant_sources.add(src)

        # Expand sources from prior tool calls to keep the model focused
        if prior_tool_names:
            for name in prior_tool_names:
                src = tool_source_map.get(name, "")
                if src:
                    relevant_sources.add(src)
            if self._DEBUG:
                logger.info(
                    "🔍 ToolRouter prior tools=%s added sources=%s",
                    prior_tool_names,
                    sorted(relevant_sources),
                )

        # No domain matched AND no prior tool hints → bounded heuristic subset
        if not active_domains and not relevant_sources:
            selected = self._heuristic_select_tools(query, all_tools)
            logger.info(
                "🎯 ToolRouter: no domain match — selected %d/%d heuristic tools",
                len(selected),
                len(all_tools),
            )
            return selected

        if not relevant_sources:
            selected = self._heuristic_select_tools(query, all_tools)
            logger.info(
                "🎯 ToolRouter: no source match — selected %d/%d heuristic tools",
                len(selected),
                len(all_tools),
            )
            return selected

        # Filter tools by source label
        filtered: List[Dict[str, Any]] = []
        for tool in all_tools:
            tool_name = self._tool_name(tool)

            # Always include meta-tools
            if tool_name in self._META_TOOLS:
                filtered.append(tool)
                continue

            source = tool_source_map.get(tool_name, "")
            if source in relevant_sources:
                filtered.append(tool)

        # Safety net: if filtering was too aggressive, pad from heuristic subset
        if len(filtered) < self._MIN_TOOL_COUNT:
            padded = list(filtered)
            existing_names = {self._tool_name(t) for t in padded}
            for tool in self._heuristic_select_tools(query, all_tools):
                name = self._tool_name(tool)
                if name and name not in existing_names:
                    padded.append(tool)
                    existing_names.add(name)
                if len(padded) >= self._MIN_TOOL_COUNT:
                    break
            filtered = padded

        if len(filtered) > self._MAX_TOOL_COUNT:
            filtered = filtered[: self._MAX_TOOL_COUNT]

        reduction_pct = (1 - len(filtered) / len(all_tools)) * 100 if all_tools else 0
        logger.info(
            "🎯 ToolRouter: %d/%d tools selected (%.0f%% reduction) for domains=%s, sources=%s",
            len(filtered),
            len(all_tools),
            reduction_pct,
            active_domains,
            sorted(relevant_sources),
        )

        return filtered

    def add_meta_tool(self, tool_name: str) -> None:
        """Register an additional meta-tool name that should always be included."""
        # _META_TOOLS is a frozenset, so we replace it
        self._META_TOOLS = frozenset(self._META_TOOLS | {tool_name})

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def explain(self, query: str, prior_tool_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return a diagnostic dict explaining how a query would be routed.

        Useful for testing and debugging without running the full orchestrator.
        """
        domains = QueryPatterns.classify_domains(query)
        active = [d for d, v in domains.items() if v]

        sources: Set[str] = set()
        for d in active:
            for src in QueryPatterns.DOMAIN_SOURCE_MAP.get(d, []):
                sources.add(src)

        return {
            "query": query,
            "domains": domains,
            "active_domains": active,
            "relevant_sources": sorted(sources),
            "prior_tool_names": prior_tool_names or [],
            "would_filter": True,
        }
