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

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
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
_CONTAINER_APP_HEALTH_TOOL = "check_container_app_health"
_CONTAINER_APP_LIST_TOOL = "container_app_list"  # referenced in health-chain guardrail


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


# ---------------------------------------------------------------------------
# Telemetry: ToolSelectionTrace — Phase 2 observability
# ---------------------------------------------------------------------------

@dataclass
class ToolScoreEntry:
    """Per-tool scoring breakdown for telemetry."""

    tool_name: str
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    boost_reasons: List[str] = field(default_factory=list)
    """Why this tool scored higher (e.g. 'always_include', 'guardrail:container_app_list')."""
    excluded: bool = False
    exclusion_reason: str = ""


@dataclass
class ToolSelectionTrace:
    """Full telemetry for a single retrieve() call.

    Captures why each tool ranked where it did during selection — query text,
    domain classification, pool sizes, per-tool scores, boosts, filters, and
    guardrails.  Serializable via ``to_dict()`` for JSON logging and API responses.
    """

    query: str = ""
    timestamp_ms: float = 0.0
    duration_ms: float = 0.0

    # Domain classification from Router
    domain_classification: List[Dict[str, Any]] = field(default_factory=list)
    """[{domain, confidence, signals}, ...] from Router."""

    # Pool
    sources_queried: List[str] = field(default_factory=list)
    pool_size: int = 0
    pool_tool_names: List[str] = field(default_factory=list)

    # Ranking
    ranking_method: str = ""
    """'semantic', 'keyword', or 'pool_passthrough' (pool ≤ top_k)."""
    top_k: int = 0

    # Per-tool scores (only top tools + notable exclusions)
    tool_scores: List[ToolScoreEntry] = field(default_factory=list)

    # Filters applied
    filters_applied: List[str] = field(default_factory=list)
    """e.g. ['read_intent_filter', 'action_tool_removal']."""
    tools_removed_by_filter: List[str] = field(default_factory=list)

    # Guardrails triggered
    guardrails_triggered: List[str] = field(default_factory=list)
    """e.g. ['cli_fallback_inject', 'container_app_health_inject']."""
    tools_injected_by_guardrail: List[str] = field(default_factory=list)

    # Final ranking
    final_tool_names: List[str] = field(default_factory=list)
    final_tool_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for logging and API responses."""
        d = asdict(self)
        # Convert ToolScoreEntry list to plain dicts (asdict handles this)
        return d


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

    trace: Optional[ToolSelectionTrace] = None
    """Telemetry trace for this retrieval (always populated)."""


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
            ToolRetrievalResult with the scoped tool list, conflict notes, and trace.
        """
        trace_start = time.monotonic()
        trace = ToolSelectionTrace(
            query=query,
            timestamp_ms=time.time() * 1000,
            top_k=self._top_k,
            domain_classification=[
                {
                    "domain": m.domain.value,
                    "confidence": round(m.confidence, 3),
                    "signals": m.matched_signals,
                }
                for m in domain_matches[:5]
            ],
        )

        # Collect all sources across matched domains (skip GENERAL unless it's the only match)
        non_general = [m for m in domain_matches if m.domain != UnifiedDomain.GENERAL]
        candidates = non_general if non_general else domain_matches

        all_sources: Set[str] = set()
        for match in candidates:
            all_sources.update(UnifiedDomainRegistry.get_sources(match.domain))

        sources_list = sorted(all_sources)
        trace.sources_queried = sources_list

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
            trace.pool_size = 0
            trace.duration_ms = (time.monotonic() - trace_start) * 1000
            self._emit_trace(trace)
            return ToolRetrievalResult(
                domain_matches=domain_matches,
                sources_used=sources_list,
                trace=trace,
            )

        pool_size = len(pool)
        trace.pool_size = pool_size
        trace.pool_tool_names = [self._tool_name(t) for t in pool]

        # Stage 2: semantic ranking within the pool
        keyword_scores: Dict[str, float] = {}
        if self._embedder.is_ready and len(pool) > self._top_k:
            trace.ranking_method = "semantic"
            try:
                ranked = await self._embedder.retrieve_from_pool(query, pool, top_k=self._top_k)
            except Exception as exc:
                logger.warning("ToolRetriever: Stage 2 ranking failed (%s); falling back to pool[:top_k]", exc)
                ranked = pool[:self._top_k]
                trace.ranking_method = "semantic_fallback"
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
            ranked, keyword_scores = self._keyword_rank_with_scores(query, pool, self._top_k)
            if not self._embedder.is_ready:
                trace.ranking_method = "keyword"
            else:
                trace.ranking_method = "pool_passthrough"

        # Build per-tool score entries from keyword ranking
        self._populate_tool_scores(trace, pool, keyword_scores, always_include or [])

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
                    trace.filters_applied.append("read_intent_action_removal")
                    trace.tools_removed_by_filter.extend(removed)
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
                    trace.guardrails_triggered.append("cli_fallback_inject")
                    trace.tools_injected_by_guardrail.append(_CLI_FALLBACK_TOOL)
                    logger.debug("ToolRetriever: injected %s as CLI escape-hatch", _CLI_FALLBACK_TOOL)

        # Deterministic guardrail: preserve container-app health tool for
        # list+health chaining plans (planner stage 3 deterministic sequence).
        # container_app_health has requires_sequence=("container_app_list",) in its manifest,
        # so the planner needs both tools available to build the chained plan.
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
                    trace.guardrails_triggered.append("container_app_health_inject")
                    trace.tools_injected_by_guardrail.append(_CONTAINER_APP_HEALTH_TOOL)
                    logger.debug(
                        "ToolRetriever: injected %s for container-app health intent",
                        _CONTAINER_APP_HEALTH_TOOL,
                    )

        # Build conflict notes for active tool set
        tool_names = [self._tool_name(t) for t in ranked]
        conflict_notes = self._manifests.build_conflict_note_for_context(tool_names)

        # Finalize trace
        trace.final_tool_names = tool_names
        trace.final_tool_count = len(ranked)
        trace.duration_ms = (time.monotonic() - trace_start) * 1000

        # Emit structured telemetry log
        self._emit_trace(trace)

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
            trace=trace,
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
        ranked, _ = ToolRetriever._keyword_rank_with_scores(query, pool, top_k)
        return ranked

    @staticmethod
    def _keyword_rank_with_scores(
        query: str,
        pool: List[Dict[str, Any]],
        top_k: int,
    ) -> tuple:
        """Rank *pool* by keyword overlap and return (ranked_tools, scores_dict).

        Returns:
            (ranked_tools, keyword_scores) where keyword_scores maps tool_name → float score.
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
            scores = {
                ToolRetriever._tool_name(t): 0.0 for t in pool
            }
            return pool[:top_k], scores

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
        keyword_scores: Dict[str, float] = {}
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
            keyword_scores[fn.get("name", "")] = float(score)

        scored.sort(key=lambda x: (x[0], x[1]))
        top5 = [(t[2].get("function", {}).get("name", "?"), -t[0]) for t in scored[:5]]
        logger.debug("_keyword_rank: tokens=%s top5(name,score)=%s pool=%d", tokens, top5, len(pool))
        return [t for _, _, t in scored[:top_k]], keyword_scores

    # ------------------------------------------------------------------
    # Telemetry helpers
    # ------------------------------------------------------------------

    def _populate_tool_scores(
        self,
        trace: ToolSelectionTrace,
        pool: List[Dict[str, Any]],
        keyword_scores: Dict[str, float],
        always_include: List[str],
    ) -> None:
        """Populate trace.tool_scores with per-tool scoring breakdown."""
        entries: List[ToolScoreEntry] = []
        for tool in pool:
            name = self._tool_name(tool)
            entry = ToolScoreEntry(
                tool_name=name,
                keyword_score=keyword_scores.get(name, 0.0),
                final_score=keyword_scores.get(name, 0.0),
            )
            if name in always_include:
                entry.boost_reasons.append("always_include")
            entries.append(entry)

        # Sort by score descending, keep top 20 + any with boosts
        entries.sort(key=lambda e: e.final_score, reverse=True)
        # Keep top 20 and all boosted entries for reasonable trace size
        top_entries = entries[:20]
        boosted = [e for e in entries[20:] if e.boost_reasons]
        trace.tool_scores = top_entries + boosted

    @staticmethod
    def _emit_trace(trace: ToolSelectionTrace) -> None:
        """Emit trace as structured JSON log at INFO level."""
        try:
            trace_dict = trace.to_dict()
            # Compact: only include tool_scores for top 10 for log line brevity
            log_dict = {
                "event": "tool_selection_trace",
                "query": trace.query[:100],
                "ranking_method": trace.ranking_method,
                "pool_size": trace.pool_size,
                "final_tool_count": trace.final_tool_count,
                "final_tools": trace.final_tool_names,
                "filters_applied": trace.filters_applied,
                "guardrails_triggered": trace.guardrails_triggered,
                "tools_injected": trace.tools_injected_by_guardrail,
                "tools_removed": trace.tools_removed_by_filter,
                "duration_ms": round(trace.duration_ms, 2),
            }
            logger.info("📊 ToolSelectionTrace: %s", json.dumps(log_dict, ensure_ascii=False))
        except Exception as exc:
            logger.debug("ToolSelectionTrace emit failed: %s", exc)

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
