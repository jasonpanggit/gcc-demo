"""Pipeline ToolRetriever — Stage 2 of the MCP orchestrator pipeline.

Given a list of DomainMatch results from the Router, retrieves a focused set of
≤15 semantically ranked tools for the Planner / Executor to work with.

Two-stage retrieval:
  Stage 1 (source filter): CompositeMCPClient.get_tools_by_sources(sources)
                           → domain pool (all tools for the matched domains)
  Stage 2 (semantic rank): ToolEmbedder.retrieve_from_pool(query, pool, top_k)
                           → ≤top_k best-matching tools

Falls back gracefully:
  - If ToolEmbedder is not ready → Stage 1 pool capped at top_k
  - If no tools found in Stage 1 → returns empty list

Usage:
    retriever = ToolRetriever(composite_client, embedder)
    result = await retriever.retrieve(query, domain_matches)
    # result.tools: List[Dict] — ≤15 tools for the LLM
    # result.conflict_notes: str — disambiguation text (only active conflicts)
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

try:
    from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain, UnifiedDomainRegistry
    from app.agentic.eol.utils.tool_manifest_index import ToolManifestIndex, get_tool_manifest_index
    from app.agentic.eol.utils.router import DomainMatch
    from app.agentic.eol.utils.tool_embedder import ToolEmbedder, get_tool_embedder
except ModuleNotFoundError:
    from utils.unified_domain_registry import UnifiedDomain, UnifiedDomainRegistry  # type: ignore[import-not-found]
    from utils.tool_manifest_index import ToolManifestIndex, get_tool_manifest_index  # type: ignore[import-not-found]
    from utils.router import DomainMatch  # type: ignore[import-not-found]
    from utils.tool_embedder import ToolEmbedder, get_tool_embedder  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = int(os.getenv("TOOL_RETRIEVER_TOP_K", "15"))

# Regex matching read-only query intents (list / show / get / what are …)
_READ_INTENT_RE = re.compile(
    r"^\s*(?:list|show|get|display|fetch|find|describe|enumerate|what\s+(?:are|is)\s+(?:my|the)|how\s+many)\b",
    re.IGNORECASE,
)

# Tool name prefixes that indicate an action tool inappropriate for read queries.
# These are verb-prefixed tools that require specific src/dst arguments or mutate state.
_ACTION_TOOL_PREFIXES = (
    "test_",
    "check_",
    "create_",
    "delete_",
    "update_",
    "restart_",
    "trigger_",
    "enable_",
    "disable_",
    "assign_",
    "run_",
    "execute_",
    "invoke_",
    "start_",
    "stop_",
    "reset_",
    "patch_",
    "deploy_",
)


# Azure/network domains that should always have azure_cli_execute_command available
# as an escape-hatch fallback.  Appended LAST so fast-path never picks it (score=0
# for list queries), but the LLM planner can choose it when no dedicated tool fits.
_CLI_FALLBACK_DOMAINS = frozenset({
    UnifiedDomain.AZURE_MANAGEMENT,
    UnifiedDomain.NETWORK,
    UnifiedDomain.DEPLOYMENT,
    UnifiedDomain.SRE_REMEDIATION,
})
_CLI_FALLBACK_TOOL = "azure_cli_execute_command"
_CONTAINER_APP_LIST_TOOL = "container_app_list"
_CONTAINER_APP_HEALTH_TOOL = "check_container_app_health"


def _is_container_app_list_intent(query: str) -> bool:
    """Return True for explicit container-app list/discovery queries."""
    if not query:
        return False
    return bool(
        re.search(r"\b(show|list|get|display|enumerate|what\s+are)\b", query, re.I)
        and re.search(r"\bcontainer\s*apps?\b|\bcontainerapps?\b", query, re.I)
    )


def _is_container_app_health_intent(query: str) -> bool:
    """Return True when query asks for container app health/status."""
    if not query:
        return False
    return bool(
        re.search(r"\bcontainer\s*apps?\b|\bcontainerapps?\b", query, re.I)
        and re.search(r"\b(health|healthy|status|degraded|unhealthy|availability)\b", query, re.I)
    )


def _is_action_tool(name: str) -> bool:
    """Return True when a tool name starts with an action verb prefix."""
    lname = name.lower()
    return any(lname.startswith(p) for p in _ACTION_TOOL_PREFIXES)


@dataclass
class ToolRetrievalResult:
    """Output of a ToolRetriever.retrieve() call."""

    tools: List[Dict[str, Any]] = field(default_factory=list)
    """≤top_k tool definitions for the LLM (OpenAI function-calling format)."""

    domain_matches: List[DomainMatch] = field(default_factory=list)
    """Domain matches that drove this retrieval."""

    sources_used: List[str] = field(default_factory=list)
    """MCP source labels that were queried in Stage 1."""

    conflict_notes: str = ""
    """Disambiguation text for active tool conflicts in *tools* (may be empty)."""

    pool_size: int = 0
    """Number of tools in the Stage 1 domain pool before Stage 2 ranking."""


class ToolRetriever:
    """Two-stage tool retrieval: source-filter → semantic rank.

    This component replaces the ad-hoc ToolRouter + ToolEmbedder wiring that
    lived inside ``MCPOrchestratorAgent._get_active_tools_for_iteration*()``.
    It is completely stateless between calls.
    """

    def __init__(
        self,
        composite_client: Any,
        embedder: Optional[ToolEmbedder] = None,
        manifest_index: Optional[ToolManifestIndex] = None,
        top_k: int = _DEFAULT_TOP_K,
    ) -> None:
        """
        Args:
            composite_client:  CompositeMCPClient instance with
                               ``get_tools_by_sources(sources)`` available.
            embedder:          ToolEmbedder instance for Stage 2 semantic ranking.
                               Defaults to the module singleton.
            manifest_index:    ToolManifestIndex for conflict-note generation.
                               Defaults to the module singleton.
            top_k:             Maximum tools to return after Stage 2 ranking.
        """
        self._client = composite_client
        self._embedder = embedder or get_tool_embedder()
        self._manifests = manifest_index or get_tool_manifest_index()
        self._top_k = top_k

    async def retrieve(
        self,
        query: str,
        domain_matches: List[DomainMatch],
        *,
        always_include: Optional[List[str]] = None,
    ) -> ToolRetrievalResult:
        """Retrieve the best ≤top_k tools for *query* given *domain_matches*.

        Args:
            query:          User's natural-language message.
            domain_matches: Ranked domain list from Router.route().
            always_include: Tool names that must be included regardless of ranking
                            (e.g. meta-tools like "describe_capabilities").

        Returns:
            ToolRetrievalResult with the scoped tool list and conflict notes.
        """
        # Collect all sources across matched domains (skip GENERAL unless it's the only match)
        non_general = [m for m in domain_matches if m.domain != UnifiedDomain.GENERAL]
        candidates = non_general if non_general else domain_matches

        all_sources: Set[str] = set()
        for match in candidates:
            all_sources.update(UnifiedDomainRegistry.get_sources(match.domain))

        sources_list = sorted(all_sources)

        # Stage 1: source-level filter — get the domain pool
        pool = self._get_pool(sources_list)

        # Always-include tools: add any that are missing from pool
        if always_include:
            pool_names = {self._tool_name(t) for t in pool}
            for tool_name in always_include:
                if tool_name not in pool_names:
                    extra = self._get_tool_by_name(tool_name)
                    if extra:
                        pool.append(extra)

        if not pool:
            logger.warning("ToolRetriever: empty pool for sources=%s", sources_list)
            return ToolRetrievalResult(
                domain_matches=domain_matches,
                sources_used=sources_list,
            )

        pool_size = len(pool)

        # Stage 2: semantic ranking within the pool
        if self._embedder.is_ready and len(pool) > self._top_k:
            try:
                ranked = await self._embedder.retrieve_from_pool(query, pool, top_k=self._top_k)
            except Exception as exc:
                logger.warning("ToolRetriever: Stage 2 ranking failed (%s); falling back to pool[:top_k]", exc)
                ranked = pool[:self._top_k]
            # Ensure always_include tools survive ranking
            if always_include:
                ranked_names = {self._tool_name(t) for t in ranked}
                for tool_name in always_include:
                    if tool_name not in ranked_names:
                        extra = next(
                            (t for t in pool if self._tool_name(t) == tool_name), None
                        )
                        if extra:
                            ranked.append(extra)
        else:
            # Embedding disabled — use keyword scoring so relevant tools surface
            # instead of relying on registration order.
            ranked = self._keyword_rank(query, pool, self._top_k)

        # Intent filter: for read queries, remove action-verb tools so they
        # never reach the planner (neither fast-path nor LLM path).
        if _READ_INTENT_RE.match(query.strip()):
            preserve_action_tools: Set[str] = set()
            if _is_container_app_health_intent(query):
                preserve_action_tools.add(_CONTAINER_APP_HEALTH_TOOL)

            filtered = [
                t for t in ranked
                if (not _is_action_tool(self._tool_name(t)))
                or (self._tool_name(t) in preserve_action_tools)
            ]

            # Keep prior safety behavior for generic read intents, but allow
            # explicit preserved action tools for health-intent chaining.
            if len(filtered) >= 2 or preserve_action_tools:
                removed = [self._tool_name(t) for t in ranked if t not in filtered]
                if removed:
                    logger.debug(
                        "ToolRetriever: intent-filter removed action tools for read query: %s",
                        removed,
                    )
                ranked = filtered

        # CLI escape-hatch: always include azure_cli_execute_command at the END for
        # azure/network domains.  The LLM planner can choose it when no specialised
        # tool fits; fast-path never picks it (keyword score=0 for list queries).
        if any(m.domain in _CLI_FALLBACK_DOMAINS for m in domain_matches):
            ranked_names = {self._tool_name(t) for t in ranked}
            if _CLI_FALLBACK_TOOL not in ranked_names:
                cli_tool = self._get_tool_by_name(_CLI_FALLBACK_TOOL)
                if cli_tool:
                    ranked.append(cli_tool)
                    logger.debug("ToolRetriever: injected %s as CLI escape-hatch", _CLI_FALLBACK_TOOL)

        # Deterministic guardrail: keep explicit container-app list tool in final set
        # so Planner list-intent override can always select it when available.
        if _is_container_app_list_intent(query):
            ranked_names = {self._tool_name(t) for t in ranked}
            if _CONTAINER_APP_LIST_TOOL not in ranked_names:
                container_list_tool = next(
                    (t for t in pool if self._tool_name(t) == _CONTAINER_APP_LIST_TOOL),
                    None,
                )
                if container_list_tool:
                    if len(ranked) >= self._top_k:
                        ranked = ranked[:-1]
                    ranked.append(container_list_tool)
                    logger.debug(
                        "ToolRetriever: injected %s for container-app list intent",
                        _CONTAINER_APP_LIST_TOOL,
                    )

        # Deterministic guardrail: preserve container-app health tool for
        # list+health chaining plans (planner stage 3 deterministic sequence).
        if _is_container_app_health_intent(query):
            ranked_names = {self._tool_name(t) for t in ranked}
            if _CONTAINER_APP_HEALTH_TOOL not in ranked_names:
                health_tool = next(
                    (t for t in pool if self._tool_name(t) == _CONTAINER_APP_HEALTH_TOOL),
                    None,
                )
                if health_tool:
                    if len(ranked) >= self._top_k:
                        ranked = ranked[:-1]
                    ranked.append(health_tool)
                    logger.debug(
                        "ToolRetriever: injected %s for container-app health intent",
                        _CONTAINER_APP_HEALTH_TOOL,
                    )

        # Build conflict notes for active tool set
        tool_names = [self._tool_name(t) for t in ranked]
        conflict_notes = self._manifests.build_conflict_note_for_context(tool_names)

        logger.info(
            "ToolRetriever: %d tools (pool=%d, sources=%s, top_k=%d)%s",
            len(ranked),
            pool_size,
            sources_list,
            self._top_k,
            f" | conflicts: {len(conflict_notes)} chars" if conflict_notes else "",
        )

        return ToolRetrievalResult(
            tools=ranked,
            domain_matches=domain_matches,
            sources_used=sources_list,
            conflict_notes=conflict_notes,
            pool_size=pool_size,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_rank(
        query: str,
        pool: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rank *pool* by keyword overlap with *query* when embedding is disabled.

        Scoring (higher = better match):
          +3  query token appears in tool name
          +1  query token appears in tool description

        Ties broken by original pool position so frequently-used tools
        with no overlap still appear in a stable order.
        """
        _STOP = frozenset({
            "a", "an", "the", "my", "your", "our", "its", "their",
            "i", "me", "we", "you", "he", "she", "it", "they",
            "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "can", "may", "might",
            "in", "on", "at", "by", "for", "of", "to", "from",
            "with", "about", "and", "or", "but",
            "show", "list", "get", "display", "fetch", "find",
            "describe", "what", "how", "many",
        })
        tokens = {
            tok for tok in re.sub(r"[^a-z0-9]", " ", query.lower()).split()
            if len(tok) > 2 and tok not in _STOP
        }
        if not tokens:
            return pool[:top_k]

        # Expand common Azure abbreviations: 'virtual'+'network' → also 'vnet', etc.
        if "virtual" in tokens and ("network" in tokens or "networks" in tokens):
            tokens.add("vnet")
        if "virtual" in tokens and ("machine" in tokens or "machines" in tokens):
            tokens.add("vm")
        if "network" in tokens and "security" in tokens:
            tokens.add("nsg")
        # Reverse-expand: abbreviated forms → full tokens so specialised list
        # tools (e.g. virtual_network_list) out-score generic inspect tools
        if "vnet" in tokens or "vnets" in tokens:
            tokens.add("virtual")
            tokens.add("network")
        if "vm" in tokens or "vms" in tokens:
            tokens.add("virtual")
            tokens.add("machine")
        if "nsg" in tokens or "nsgs" in tokens:
            tokens.add("network")
            tokens.add("security")

        scored: List[tuple] = []
        for idx, tool in enumerate(pool):
            fn = tool.get("function", {})
            name = fn.get("name", "").lower()
            desc = fn.get("description", "").lower()
            # Split tool name on _ and - into discrete tokens so that
            # 'virtual' matches 'virtual_network_list' but NOT 'virtualdesktop'.
            name_tokens = set(re.findall(r"[a-z0-9]+", name))
            score = 0
            for tok in tokens:
                # Build plural/singular variants for this token
                variants = {tok}
                if tok.endswith("s") and len(tok) > 3:
                    variants.add(tok[:-1])  # subscriptions → subscription
                else:
                    variants.add(tok + "s")  # subscription → subscriptions
                # +3 for exact token match in tool name, +1 for substring in description
                if any(v in name_tokens for v in variants):
                    score += 3
                elif any(v in desc for v in variants):
                    score += 1
            scored.append((-score, idx, tool))  # negative so sort is descending

        scored.sort(key=lambda x: (x[0], x[1]))
        top5 = [(t[2].get("function", {}).get("name", "?"), -t[0]) for t in scored[:5]]
        logger.debug("_keyword_rank: tokens=%s top5(name,score)=%s pool=%d", tokens, top5, len(pool))
        return [t for _, _, t in scored[:top_k]]

    def _get_pool(self, sources: List[str]) -> List[Dict[str, Any]]:
        """Stage 1: fetch all tools from the matched source labels."""
        if not sources:
            return []
        try:
            # CompositeMCPClient.get_tools_by_sources() already exists
            return list(self._client.get_tools_by_sources(sources))
        except AttributeError:
            # Fallback: if composite_client doesn't support get_tools_by_sources,
            # filter from the full catalog using the source map
            try:
                all_tools = self._client.get_tool_definitions()
                source_map = self._client.get_tool_sources()
                source_set = set(sources)
                return [t for t in all_tools if source_map.get(self._tool_name(t)) in source_set]
            except Exception as exc:
                logger.warning("ToolRetriever._get_pool fallback failed: %s", exc)
                return []

    def _get_tool_by_name(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Look up a single tool definition by name from the composite client."""
        try:
            all_tools = self._client.get_tool_definitions()
            return next((t for t in all_tools if self._tool_name(t) == tool_name), None)
        except Exception:
            return None

    @staticmethod
    def _tool_name(tool: Dict[str, Any]) -> str:
        return str(tool.get("function", {}).get("name", ""))
