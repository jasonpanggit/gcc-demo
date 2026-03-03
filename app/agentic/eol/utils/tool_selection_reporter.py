"""Tool selection trace reporter.

Generates comprehensive markdown, JSON, or HTML diagnostic reports showing the
complete tool-selection trace for any natural-language query.  Designed to run
**offline** (no Azure API calls, no MCP server connections required) using only
the in-process DomainClassifier, Router.explain(), ToolManifestIndex, and
keyword-scoring logic that mirrors ToolRetriever._keyword_rank_with_scores().

Use-cases
---------
* Debug why a specific query picked the wrong tools
* Validate manifest improvements against canonical queries
* Regression-check golden scenarios after routing changes
* Generate onboarding material showing the routing pipeline end-to-end

Usage
-----
# From app/agentic/eol directory:
    python -m utils.tool_selection_reporter "list my container apps"
    python -m utils.tool_selection_reporter "check VM health" --format json
    python -m utils.tool_selection_reporter "show all VMs" --format html -o report.html
    python -m utils.tool_selection_reporter --scenario container_app_health
    python -m utils.tool_selection_reporter --all-scenarios

# From repository root:
    python -m app.agentic.eol.utils.tool_selection_reporter "list my container apps"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Dual-prefix imports (works from both repo root and eol/ directory)
# ---------------------------------------------------------------------------
try:
    from app.agentic.eol.utils.domain_classifier import (
        DomainClassification,
        DomainClassifier,
        DomainLabel,
        get_domain_classifier,
    )
    from app.agentic.eol.utils.tool_manifest_index import (
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )
    from app.agentic.eol.utils.router import DomainMatch, Router
    from app.agentic.eol.utils.query_patterns import QueryPatterns
except ModuleNotFoundError:
    from utils.domain_classifier import (  # type: ignore[import-not-found]
        DomainClassification,
        DomainClassifier,
        DomainLabel,
        get_domain_classifier,
    )
    from utils.tool_manifest_index import (  # type: ignore[import-not-found]
        ToolAffordance,
        ToolManifest,
        ToolManifestIndex,
        get_tool_manifest_index,
    )
    from utils.router import DomainMatch, Router  # type: ignore[import-not-found]
    from utils.query_patterns import QueryPatterns  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Constants mirroring ToolRetriever behaviour
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 15

# Keywords that are too generic to be useful for keyword scoring
_STOP_WORDS: frozenset = frozenset({
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

# Read-intent regex (mirrors ToolRetriever._READ_INTENT_RE)
_READ_INTENT_RE = re.compile(
    r"^\s*(?:list|show|get|display|fetch|find|describe|enumerate"
    r"|what\s+(?:are|is)\s+(?:my|the)|how\s+many)\b",
    re.IGNORECASE,
)

# Action-verb tool prefixes (mirrors ToolRetriever._ACTION_TOOL_PREFIXES)
_ACTION_TOOL_PREFIXES: Tuple[str, ...] = (
    "test_", "check_", "create_", "delete_", "update_", "restart_",
    "trigger_", "enable_", "disable_", "assign_", "run_", "execute_",
    "invoke_", "start_", "stop_", "reset_", "patch_", "deploy_",
)

# Domains that always get the CLI fallback (mirrors ToolRetriever._CLI_FALLBACK_DOMAINS)
_CLI_FALLBACK_SOURCE_LABELS: frozenset = frozenset({"azure_cli", "azure", "sre"})
_CLI_FALLBACK_TOOL = "azure_cli_execute_command"
_CONTAINER_APP_LIST_TOOL = "container_app_list"
_CONTAINER_APP_HEALTH_TOOL = "check_container_app_health"


# ---------------------------------------------------------------------------
# Domain → manifest source label mapping
# (mirrors UnifiedDomainRegistry entries and QueryPatterns.DOMAIN_SOURCE_MAP)
# ---------------------------------------------------------------------------

_DOMAIN_LABEL_TO_SOURCES: Dict[str, List[str]] = {
    "sre":        ["sre"],
    "monitoring": ["monitor", "sre"],
    "network":    ["network", "azure"],
    "inventory":  ["inventory", "os_eol"],
    "patch":      ["sre", "azure_cli"],
    "compute":    ["compute", "azure"],
    "storage":    ["storage", "azure"],
    "cost":       ["sre"],
    "security":   ["sre"],
    "general":    ["azure", "sre", "monitor", "inventory", "os_eol", "azure_cli", "compute", "storage", "network"],
}

# Map manifest source string → human-readable display label
_SOURCE_DISPLAY: Dict[str, str] = {
    "sre":              "SRE MCP",
    "azure":            "Azure MCP",
    "monitor":          "Monitor MCP",
    "inventory":        "Inventory MCP",
    "os_eol":           "OS/EOL MCP",
    "azure_cli":        "Azure CLI Executor",
    "compute":          "Compute MCP",
    "storage":          "Storage MCP",
    "network":          "Network MCP",
}

# Affordance → display string + colour (for HTML)
_AFFORDANCE_DISPLAY: Dict[ToolAffordance, Tuple[str, str]] = {
    ToolAffordance.READ:        ("READ",        "#0d652d"),
    ToolAffordance.WRITE:       ("WRITE",       "#b45309"),
    ToolAffordance.DESTRUCTIVE: ("DESTRUCTIVE", "#dc2626"),
    ToolAffordance.DEPLOY:      ("DEPLOY",      "#6d28d9"),
}


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ToolPoolEntry:
    """Metadata for a single tool in the domain pool."""
    tool_name: str
    source: str
    domains: List[str]
    affordance: str
    tags: List[str]
    example_queries: List[str]
    has_conflicts: bool
    requires_confirmation: bool
    deprecated: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "source": self.source,
            "domains": self.domains,
            "affordance": self.affordance,
            "tags": self.tags,
            "example_queries": self.example_queries,
            "has_conflicts": self.has_conflicts,
            "requires_confirmation": self.requires_confirmation,
            "deprecated": self.deprecated,
        }


@dataclass
class ScoredToolEntry:
    """Per-tool scoring breakdown produced by the reporter."""
    tool_name: str
    source: str
    keyword_score: float
    tag_match_score: float
    example_query_score: float
    total_score: float
    matched_tokens: List[str] = field(default_factory=list)
    matched_tags: List[str] = field(default_factory=list)
    boost_reasons: List[str] = field(default_factory=list)
    excluded: bool = False
    exclusion_reason: str = ""
    in_final_set: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "source": self.source,
            "keyword_score": round(self.keyword_score, 2),
            "tag_match_score": round(self.tag_match_score, 2),
            "example_query_score": round(self.example_query_score, 2),
            "total_score": round(self.total_score, 2),
            "matched_tokens": self.matched_tokens,
            "matched_tags": self.matched_tags,
            "boost_reasons": self.boost_reasons,
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
            "in_final_set": self.in_final_set,
        }


@dataclass
class GuardrailEvent:
    """A single guardrail that fired during tool selection."""
    name: str
    description: str
    tools_injected: List[str] = field(default_factory=list)
    tools_removed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tools_injected": self.tools_injected,
            "tools_removed": self.tools_removed,
        }


@dataclass
class ManifestSuggestion:
    """An actionable manifest improvement suggestion."""
    tool_name: str
    severity: str           # "high" | "medium" | "low"
    field_name: str
    message: str
    suggestion: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "severity": self.severity,
            "field": self.field_name,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class ScenarioComparison:
    """Expected vs actual tool selection when run against a golden scenario."""
    scenario_name: str
    canonical_query: str
    tools_required: List[str]
    tools_excluded: List[str]
    tools_selected: List[str]
    missing_required: List[str] = field(default_factory=list)
    unexpected_excluded: List[str] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "canonical_query": self.canonical_query,
            "tools_required": self.tools_required,
            "tools_excluded": self.tools_excluded,
            "tools_selected": self.tools_selected,
            "missing_required": self.missing_required,
            "unexpected_excluded": self.unexpected_excluded,
            "passed": self.passed,
        }


@dataclass
class QueryReport:
    """Complete tool-selection trace report for a single query.

    Sections correspond 1-to-1 with the markdown/HTML sections rendered by the
    formatters.  All fields are plain-Python so ``to_dict()`` is trivially JSON
    serialisable.
    """

    # ── Meta ──────────────────────────────────────────────────────────────
    generated_at: str = ""
    query: str = ""
    strategy: str = "fast"
    duration_ms: float = 0.0

    # ── 1. Query Analysis ─────────────────────────────────────────────────
    detected_intent: str = ""           # "read" | "action" | "ambiguous"
    is_read_intent: bool = False
    is_container_app_list_intent: bool = False
    is_container_app_health_intent: bool = False
    legacy_active_domains: List[str] = field(default_factory=list)
    relevant_sources: List[str] = field(default_factory=list)

    # ── 2. Domain Classification ──────────────────────────────────────────
    primary_domain: str = ""
    primary_confidence: float = 0.0
    secondary_domains: List[str] = field(default_factory=list)
    classification_reasoning: str = ""
    router_explain: Dict[str, Any] = field(default_factory=dict)

    # ── 3. Tool Pool Composition ──────────────────────────────────────────
    sources_queried: List[str] = field(default_factory=list)
    pool_size: int = 0
    pool: List[ToolPoolEntry] = field(default_factory=list)

    # ── 4. Scoring Details ────────────────────────────────────────────────
    ranking_method: str = "keyword"
    query_tokens: List[str] = field(default_factory=list)
    scored_tools: List[ScoredToolEntry] = field(default_factory=list)

    # ── 5. Final Tool Selection ───────────────────────────────────────────
    top_k: int = _DEFAULT_TOP_K
    final_tools: List[str] = field(default_factory=list)
    final_tool_count: int = 0

    # ── 6. Filters Applied ────────────────────────────────────────────────
    filters_applied: List[str] = field(default_factory=list)
    tools_removed_by_filter: List[str] = field(default_factory=list)

    # ── 7. Guardrails Triggered ───────────────────────────────────────────
    guardrails: List[GuardrailEvent] = field(default_factory=list)

    # ── 8. Conflict Notes Active ──────────────────────────────────────────
    conflict_notes: str = ""

    # ── 9. Manifest Improvement Suggestions ──────────────────────────────
    suggestions: List[ManifestSuggestion] = field(default_factory=list)

    # ── 10. Scenario Comparison (optional) ───────────────────────────────
    scenario_comparison: Optional[ScenarioComparison] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "generated_at": self.generated_at,
            "query": self.query,
            "strategy": self.strategy,
            "duration_ms": round(self.duration_ms, 2),
            "query_analysis": {
                "detected_intent": self.detected_intent,
                "is_read_intent": self.is_read_intent,
                "is_container_app_list_intent": self.is_container_app_list_intent,
                "is_container_app_health_intent": self.is_container_app_health_intent,
                "legacy_active_domains": self.legacy_active_domains,
                "relevant_sources": self.relevant_sources,
            },
            "domain_classification": {
                "primary_domain": self.primary_domain,
                "primary_confidence": round(self.primary_confidence, 3),
                "secondary_domains": self.secondary_domains,
                "reasoning": self.classification_reasoning,
                "router_explain": self.router_explain,
            },
            "tool_pool": {
                "sources_queried": self.sources_queried,
                "pool_size": self.pool_size,
                "tools": [t.to_dict() for t in self.pool],
            },
            "scoring": {
                "ranking_method": self.ranking_method,
                "query_tokens": self.query_tokens,
                "scored_tools": [s.to_dict() for s in self.scored_tools],
            },
            "final_selection": {
                "top_k": self.top_k,
                "final_tools": self.final_tools,
                "final_tool_count": self.final_tool_count,
            },
            "filters": {
                "applied": self.filters_applied,
                "tools_removed": self.tools_removed_by_filter,
            },
            "guardrails": [g.to_dict() for g in self.guardrails],
            "conflict_notes": self.conflict_notes,
            "manifest_suggestions": [s.to_dict() for s in self.suggestions],
        }
        if self.scenario_comparison:
            d["scenario_comparison"] = self.scenario_comparison.to_dict()
        return d


# ---------------------------------------------------------------------------
# Core reporter class
# ---------------------------------------------------------------------------

class ToolSelectionReporter:
    """Offline diagnostic reporter for the tool-selection pipeline.

    Works without running MCP servers or Azure credentials.  Initialises
    DomainClassifier and ToolManifestIndex singletons, then simulates the
    routing + retrieval pipeline deterministically.

    Thread safety: safe to share after ``__init__``; ``generate_report()``
    creates no shared mutable state between calls.
    """

    def __init__(self) -> None:
        self._classifier: DomainClassifier = get_domain_classifier()
        self._manifests: ToolManifestIndex = get_tool_manifest_index()
        # Router is stateless after init (uses ResourceInventoryService regex-only path)
        try:
            self._router: Optional[Router] = Router()
        except Exception:
            self._router = None

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def generate_report(
        self,
        query: str,
        strategy: str = "fast",
    ) -> QueryReport:
        """Run the routing/classification pipeline and build a full report.

        Args:
            query:    Natural-language user query to analyse.
            strategy: Routing strategy hint — "fast" | "quality" | "comprehensive".
                      Currently used only for labelling (offline mode doesn't
                      change the manifest pool by strategy).

        Returns:
            Populated QueryReport ready for formatting.
        """
        t0 = time.monotonic()
        report = QueryReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            query=query,
            strategy=strategy,
        )

        # ── 1. Query Analysis ─────────────────────────────────────────
        self._analyse_query_intent(report, query)

        # ── 2. Domain Classification ──────────────────────────────────
        await self._classify_domain(report, query)

        # ── 3. Build Tool Pool ────────────────────────────────────────
        self._build_tool_pool(report)

        # ── 4. Score Tools ────────────────────────────────────────────
        self._score_tools(report, query)

        # ── 5–7. Apply Filters + Guardrails → Final Set ───────────────
        self._apply_filters_and_guardrails(report, query)

        # ── 8. Conflict Notes ─────────────────────────────────────────
        report.conflict_notes = self._manifests.build_conflict_note_for_context(
            report.final_tools
        )

        # ── 9. Manifest Improvement Suggestions ──────────────────────
        self._generate_suggestions(report)

        report.duration_ms = (time.monotonic() - t0) * 1000
        return report

    # ----------------------------------------------------------------
    # Pipeline stages
    # ----------------------------------------------------------------

    def _analyse_query_intent(self, report: QueryReport, query: str) -> None:
        """Populate query analysis section."""
        report.is_read_intent = bool(_READ_INTENT_RE.match(query.strip()))

        # Container App intents
        has_list_verb = bool(re.search(
            r"\b(show|list|get|display|enumerate|what\s+are)\b", query, re.I
        ))
        has_ca = bool(re.search(
            r"\bcontainer\s*apps?\b|\bcontainerapps?\b", query, re.I
        ))
        has_health = bool(re.search(
            r"\b(health|healthy|status|degraded|unhealthy|availability)\b", query, re.I
        ))
        report.is_container_app_list_intent = has_list_verb and has_ca
        report.is_container_app_health_intent = has_ca and has_health

        # Detect intent label
        if report.is_read_intent:
            report.detected_intent = "read"
        elif any(
            query.lower().startswith(v)
            for v in ("check ", "create ", "delete ", "update ", "restart ",
                      "deploy ", "execute ", "run ", "patch ")
        ):
            report.detected_intent = "action"
        else:
            report.detected_intent = "ambiguous"

        # Legacy domain classification (QueryPatterns)
        try:
            legacy = QueryPatterns.classify_domains(query)
            report.legacy_active_domains = [d for d, v in legacy.items() if v]
            sources: Set[str] = set()
            for d in report.legacy_active_domains:
                for src in QueryPatterns.DOMAIN_SOURCE_MAP.get(d, []):
                    sources.add(src)
            report.relevant_sources = sorted(sources)
        except Exception:
            pass

    async def _classify_domain(self, report: QueryReport, query: str) -> None:
        """Populate domain classification section using DomainClassifier + Router."""
        # DomainClassifier (keyword-based)
        try:
            classification: DomainClassification = await self._classifier.classify(query)
            report.primary_domain = classification.primary_domain.value
            report.primary_confidence = classification.confidence
            report.secondary_domains = [d.value for d in classification.secondary_domains]
            report.classification_reasoning = classification.reasoning or ""
        except Exception as exc:
            report.primary_domain = "general"
            report.primary_confidence = 0.5
            report.classification_reasoning = f"Classification failed: {exc}"

        # Router.explain() — synchronous, no entity hints
        if self._router is not None:
            try:
                report.router_explain = self._router.explain(query)
            except Exception:
                pass

    def _build_tool_pool(self, report: QueryReport) -> None:
        """Collect all manifest-registered tools for the detected domain(s)."""
        # Determine which sources to query
        primary_sources = set(
            _DOMAIN_LABEL_TO_SOURCES.get(report.primary_domain, ["general"])
        )
        for sec in report.secondary_domains:
            for src in _DOMAIN_LABEL_TO_SOURCES.get(sec, []):
                primary_sources.add(src)

        # Also include sources from Router's legacy classification
        for src in report.relevant_sources:
            primary_sources.add(src)

        report.sources_queried = sorted(primary_sources)

        # Collect all manifests whose source matches the queried sources
        pool_entries: List[ToolPoolEntry] = []
        for name in self._manifests.all_tool_names():
            manifest = self._manifests.get(name)
            if manifest is None or manifest.deprecated:
                continue
            if manifest.source in primary_sources:
                pool_entries.append(ToolPoolEntry(
                    tool_name=manifest.tool_name,
                    source=manifest.source,
                    domains=sorted(manifest.domains),
                    affordance=manifest.affordance.value,
                    tags=sorted(manifest.tags),
                    example_queries=list(manifest.example_queries),
                    has_conflicts=bool(manifest.conflicts_with),
                    requires_confirmation=manifest.requires_confirmation,
                    deprecated=manifest.deprecated,
                ))

        report.pool = sorted(pool_entries, key=lambda e: (e.source, e.tool_name))
        report.pool_size = len(report.pool)

    def _score_tools(self, report: QueryReport, query: str) -> None:
        """Score every tool in the pool using keyword + tag + example-query matching."""
        # Extract query tokens (mirrors ToolRetriever logic)
        tokens = _extract_tokens(query)
        report.query_tokens = sorted(tokens)
        report.ranking_method = "keyword"

        scored: List[ScoredToolEntry] = []
        for entry in report.pool:
            manifest = self._manifests.get(entry.tool_name)
            if manifest is None:
                continue

            ks, matched_name_tokens = _keyword_score(tokens, entry.tool_name, "")
            tag_score, matched_tags = _tag_score(tokens, manifest.tags)
            eq_score = _example_query_score(tokens, manifest.example_queries)

            total = ks + tag_score + eq_score
            scored.append(ScoredToolEntry(
                tool_name=entry.tool_name,
                source=entry.source,
                keyword_score=ks,
                tag_match_score=tag_score,
                example_query_score=eq_score,
                total_score=total,
                matched_tokens=matched_name_tokens,
                matched_tags=matched_tags,
            ))

        scored.sort(key=lambda e: e.total_score, reverse=True)
        report.scored_tools = scored

    def _apply_filters_and_guardrails(self, report: QueryReport, query: str) -> None:
        """Apply read-intent filter + guardrails, then build final_tools list."""
        report.top_k = _DEFAULT_TOP_K

        # Start with top-k scored (non-excluded) tools
        ranked_names: List[str] = [
            e.tool_name for e in report.scored_tools
            if not e.excluded
        ][:report.top_k]
        ranked_set: Set[str] = set(ranked_names)

        # ── Read-intent filter ────────────────────────────────────────
        if report.is_read_intent:
            preserve: Set[str] = set()
            if report.is_container_app_health_intent:
                preserve.add(_CONTAINER_APP_HEALTH_TOOL)

            removed: List[str] = []
            filtered: List[str] = []
            for name in ranked_names:
                if _is_action_tool(name) and name not in preserve:
                    removed.append(name)
                    ranked_set.discard(name)
                    # Mark in scored_tools
                    for e in report.scored_tools:
                        if e.tool_name == name:
                            e.excluded = True
                            e.exclusion_reason = "read_intent_action_removal"
                else:
                    filtered.append(name)

            if removed:
                report.filters_applied.append("read_intent_action_removal")
                report.tools_removed_by_filter.extend(removed)
            ranked_names = filtered
            ranked_set = set(ranked_names)

        # ── CLI fallback guardrail ────────────────────────────────────
        if _CLI_FALLBACK_TOOL not in ranked_set:
            cli_manifest = self._manifests.get(_CLI_FALLBACK_TOOL)
            if cli_manifest and cli_manifest.source in set(report.sources_queried):
                ranked_names.append(_CLI_FALLBACK_TOOL)
                ranked_set.add(_CLI_FALLBACK_TOOL)
                report.guardrails.append(GuardrailEvent(
                    name="cli_fallback_inject",
                    description=(
                        "azure_cli_execute_command appended as escape-hatch fallback "
                        "for azure/network/deployment domains."
                    ),
                    tools_injected=[_CLI_FALLBACK_TOOL],
                ))

        # ── Container app list guardrail ──────────────────────────────
        if report.is_container_app_list_intent and _CONTAINER_APP_LIST_TOOL not in ranked_set:
            ca_manifest = self._manifests.get(_CONTAINER_APP_LIST_TOOL)
            if ca_manifest:
                if len(ranked_names) >= report.top_k:
                    evicted = ranked_names.pop()
                    ranked_set.discard(evicted)
                ranked_names.append(_CONTAINER_APP_LIST_TOOL)
                ranked_set.add(_CONTAINER_APP_LIST_TOOL)
                report.guardrails.append(GuardrailEvent(
                    name="container_app_list_inject",
                    description=(
                        "container_app_list injected because query matches the "
                        "container-app list/discovery intent pattern."
                    ),
                    tools_injected=[_CONTAINER_APP_LIST_TOOL],
                ))

        # ── Container app health guardrail ────────────────────────────
        if report.is_container_app_health_intent and _CONTAINER_APP_HEALTH_TOOL not in ranked_set:
            ch_manifest = self._manifests.get(_CONTAINER_APP_HEALTH_TOOL)
            if ch_manifest:
                if len(ranked_names) >= report.top_k:
                    evicted = ranked_names.pop()
                    ranked_set.discard(evicted)
                ranked_names.append(_CONTAINER_APP_HEALTH_TOOL)
                ranked_set.add(_CONTAINER_APP_HEALTH_TOOL)
                report.guardrails.append(GuardrailEvent(
                    name="container_app_health_inject",
                    description=(
                        "check_container_app_health injected to support the "
                        "deterministic container-app health chaining plan."
                    ),
                    tools_injected=[_CONTAINER_APP_HEALTH_TOOL],
                ))

        # Mark final-set membership in scored_tools
        for entry in report.scored_tools:
            entry.in_final_set = entry.tool_name in ranked_set

        report.final_tools = ranked_names
        report.final_tool_count = len(ranked_names)

    def _generate_suggestions(self, report: QueryReport) -> None:
        """Produce actionable manifest improvement hints based on this query."""
        suggestions: List[ManifestSuggestion] = []

        for entry in report.scored_tools:
            if entry.excluded or not entry.in_final_set:
                continue  # Focus on final-set tools only for coverage analysis

            manifest = self._manifests.get(entry.tool_name)
            if manifest is None:
                continue

            # Low keyword score despite being in final set
            if entry.keyword_score == 0 and entry.total_score == 0:
                suggestions.append(ManifestSuggestion(
                    tool_name=entry.tool_name,
                    severity="high",
                    field_name="example_queries + tags",
                    message=(
                        f"'{entry.tool_name}' scored 0 for query {report.query!r}. "
                        "It was included via guardrail or domain inclusion, not relevance scoring."
                    ),
                    suggestion=(
                        "Add example queries that cover this use-case and tags that match "
                        f"terms like: {', '.join(report.query_tokens[:5])}."
                    ),
                ))

            # No matching tags for any query token
            if entry.tag_match_score == 0 and entry.matched_tokens:
                suggestions.append(ManifestSuggestion(
                    tool_name=entry.tool_name,
                    severity="medium",
                    field_name="tags",
                    message=(
                        f"'{entry.tool_name}' matched via name/description tokens "
                        f"({entry.matched_tokens}) but has no matching tags."
                    ),
                    suggestion=(
                        f"Add tags: {', '.join(entry.matched_tokens[:4])} to improve "
                        "semantic retrieval when embeddings are disabled."
                    ),
                ))

            # Conflicts declared but no conflict_note
            if manifest.conflicts_with and not manifest.conflict_note:
                suggestions.append(ManifestSuggestion(
                    tool_name=entry.tool_name,
                    severity="medium",
                    field_name="conflict_note",
                    message=(
                        f"'{entry.tool_name}' declares conflicts_with={set(manifest.conflicts_with)} "
                        "but has no conflict_note."
                    ),
                    suggestion=(
                        "Add a conflict_note explaining when to prefer this tool over "
                        f"{set(manifest.conflicts_with)}."
                    ),
                ))

        # Check tools that scored well but didn't make it into the final set
        near_misses = [
            e for e in report.scored_tools
            if not e.in_final_set and not e.excluded and e.total_score > 0
        ][:3]
        for entry in near_misses:
            suggestions.append(ManifestSuggestion(
                tool_name=entry.tool_name,
                severity="low",
                field_name="example_queries",
                message=(
                    f"'{entry.tool_name}' scored {entry.total_score:.1f} but didn't make "
                    f"top-{report.top_k}. Consider if it should be selected for this query."
                ),
                suggestion=(
                    "If this tool is more relevant than those selected, add more specific "
                    f"example queries matching the pattern: {report.query!r}"
                ),
            ))

        report.suggestions = suggestions


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _extract_tokens(query: str) -> Set[str]:
    """Extract meaningful tokens from a query (mirrors ToolRetriever logic)."""
    raw_tokens = {
        tok for tok in re.sub(r"[^a-z0-9]", " ", query.lower()).split()
        if len(tok) > 2 and tok not in _STOP_WORDS
    }
    # Expand Azure abbreviations
    if "virtual" in raw_tokens and ("network" in raw_tokens or "networks" in raw_tokens):
        raw_tokens.add("vnet")
    if "virtual" in raw_tokens and ("machine" in raw_tokens or "machines" in raw_tokens):
        raw_tokens.add("vm")
    if "network" in raw_tokens and "security" in raw_tokens:
        raw_tokens.add("nsg")
    # Reverse-expand abbreviations
    if "vnet" in raw_tokens or "vnets" in raw_tokens:
        raw_tokens.update({"virtual", "network"})
    if "vm" in raw_tokens or "vms" in raw_tokens:
        raw_tokens.update({"virtual", "machine"})
    if "nsg" in raw_tokens or "nsgs" in raw_tokens:
        raw_tokens.update({"network", "security"})
    return raw_tokens


def _keyword_score(
    tokens: Set[str],
    tool_name: str,
    description: str,
) -> Tuple[float, List[str]]:
    """Score a tool by token overlap with its name (and optionally description).

    Returns:
        (score, matched_name_tokens) — matched_name_tokens is the list of query
        tokens that matched the tool name components.
    """
    if not tokens:
        return 0.0, []
    name_tokens = set(re.findall(r"[a-z0-9]+", tool_name.lower()))
    desc_lower = description.lower()

    score = 0.0
    matched: List[str] = []
    for tok in tokens:
        variants = {tok}
        if tok.endswith("s") and len(tok) > 3:
            variants.add(tok[:-1])
        else:
            variants.add(tok + "s")
        if any(v in name_tokens for v in variants):
            score += 3.0
            matched.append(tok)
        elif desc_lower and any(v in desc_lower for v in variants):
            score += 1.0
    return score, matched


def _tag_score(
    tokens: Set[str],
    tags: FrozenSet,
) -> Tuple[float, List[str]]:
    """Score a tool by tag overlap with query tokens.

    Each matching tag contributes +2.0 to the score.
    """
    if not tokens or not tags:
        return 0.0, []
    matched: List[str] = []
    for tag in tags:
        tag_lower = tag.lower()
        if any(
            tok in tag_lower or tag_lower in tok
            for tok in tokens
        ):
            matched.append(tag)
    return float(len(matched) * 2), matched


def _example_query_score(
    tokens: Set[str],
    example_queries: Tuple[str, ...],
) -> float:
    """Score a tool by token overlap across its example_queries.

    Each unique token found in any example query contributes +0.5.
    """
    if not tokens or not example_queries:
        return 0.0
    combined = " ".join(example_queries).lower()
    matched = sum(1 for tok in tokens if tok in combined)
    return float(matched) * 0.5


def _is_action_tool(name: str) -> bool:
    """Return True when a tool name starts with an action-verb prefix."""
    lname = name.lower()
    return any(lname.startswith(p) for p in _ACTION_TOOL_PREFIXES)


# ---------------------------------------------------------------------------
# Scenario helpers (lazy import — optional dependency on tests/ package)
# ---------------------------------------------------------------------------

def _try_load_scenario(name: str) -> Optional[Any]:
    """Load a golden scenario by stem name; returns None on any failure."""
    try:
        try:
            from app.agentic.eol.tests.utils.golden_dataset_loader import load_scenario
        except ModuleNotFoundError:
            # Construct path relative to this file (utils/ → tests/)
            import importlib.util as _ilu
            import sys as _sys
            _base = Path(__file__).parent.parent / "tests" / "utils" / "golden_dataset_loader.py"
            if not _base.exists():
                return None
            _mod_name = "golden_dataset_loader"
            spec = _ilu.spec_from_file_location(_mod_name, _base)
            mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
            # Register in sys.modules BEFORE exec so dataclass annotation resolution works
            _sys.modules[_mod_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            load_scenario = mod.load_scenario

        # Locate the YAML file
        scenarios_dir = Path(__file__).parent.parent / "tests" / "scenarios"
        yaml_path = scenarios_dir / f"{name}.yaml"
        if not yaml_path.exists():
            return None
        return load_scenario(yaml_path)
    except Exception:
        return None


def _try_load_all_scenarios() -> List[Any]:
    """Load all golden scenarios; returns empty list on failure."""
    try:
        try:
            from app.agentic.eol.tests.utils.golden_dataset_loader import load_all_scenarios
        except ModuleNotFoundError:
            import importlib.util as _ilu
            import sys as _sys
            _base = Path(__file__).parent.parent / "tests" / "utils" / "golden_dataset_loader.py"
            if not _base.exists():
                return []
            _mod_name = "golden_dataset_loader"
            # Reuse cached module if already loaded (e.g. by _try_load_scenario)
            if _mod_name not in _sys.modules:
                spec = _ilu.spec_from_file_location(_mod_name, _base)
                mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
                _sys.modules[_mod_name] = mod
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
            load_all_scenarios = _sys.modules[_mod_name].load_all_scenarios

        scenarios_dir = Path(__file__).parent.parent / "tests" / "scenarios"
        return load_all_scenarios(scenarios_dir)
    except Exception:
        return []


def _attach_scenario_comparison(report: QueryReport, scenario: Any) -> None:
    """Attach expected-vs-actual comparison from a golden scenario."""
    contract = scenario.expected_contract
    required = list(contract.tools_required)
    excluded = list(contract.tools_excluded)
    selected = list(report.final_tools)
    selected_set = set(selected)

    missing = [t for t in required if t not in selected_set]
    unexpected = [t for t in excluded if t in selected_set]

    report.scenario_comparison = ScenarioComparison(
        scenario_name=scenario.name,
        canonical_query=scenario.canonical_query,
        tools_required=required,
        tools_excluded=excluded,
        tools_selected=selected,
        missing_required=missing,
        unexpected_excluded=unexpected,
        passed=(not missing and not unexpected),
    )


# ---------------------------------------------------------------------------
# FrozenSet type hint (for _tag_score signature readability)
# ---------------------------------------------------------------------------
from typing import FrozenSet  # noqa: E402  (re-import for annotation use above)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_json(report: QueryReport) -> str:
    """Render the report as pretty-printed JSON."""
    return json.dumps(report.to_dict(), indent=2, default=str)


def format_markdown(report: QueryReport) -> str:
    """Render the report as human-readable Markdown.

    Sections:
        1. Query Analysis
        2. Domain Classification
        3. Tool Pool Composition
        4. Scoring Details
        5. Final Tool Selection
        6. Alternative Tools Considered
        7. Excluded Tools and Why
        8. Conflict Notes Active
        9. Guardrails Triggered
        10. Manifest Improvement Suggestions
        11. Scenario Comparison (if present)
    """
    lines: List[str] = []

    # ── Header ───────────────────────────────────────────────────────
    lines.append("# Tool Selection Trace Report")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Query:** `{report.query}`")
    lines.append(f"**Strategy:** {report.strategy}")
    lines.append(f"**Duration:** {report.duration_ms:.1f}ms")
    lines.append("")

    # ── 1. Query Analysis ─────────────────────────────────────────────
    lines.append("## 1. Query Analysis")
    lines.append("")
    lines.append(f"| Property | Value |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Detected Intent | `{report.detected_intent}` |")
    lines.append(f"| Read Intent | {'Yes ✓' if report.is_read_intent else 'No'} |")
    lines.append(f"| Container App List Intent | {'Yes ✓' if report.is_container_app_list_intent else 'No'} |")
    lines.append(f"| Container App Health Intent | {'Yes ✓' if report.is_container_app_health_intent else 'No'} |")
    if report.legacy_active_domains:
        lines.append(f"| Active Legacy Domains | {', '.join(f'`{d}`' for d in report.legacy_active_domains)} |")
    if report.relevant_sources:
        lines.append(f"| Relevant Sources | {', '.join(f'`{s}`' for s in report.relevant_sources)} |")
    if report.query_tokens:
        lines.append(f"| Query Tokens | {', '.join(f'`{t}`' for t in sorted(report.query_tokens))} |")
    lines.append("")

    # ── 2. Domain Classification ──────────────────────────────────────
    lines.append("## 2. Domain Classification")
    lines.append("")
    lines.append(f"**Primary:** `{report.primary_domain}` (confidence: {report.primary_confidence:.0%})")
    if report.secondary_domains:
        lines.append(f"**Secondary:** {', '.join(f'`{d}`' for d in report.secondary_domains)}")
    if report.classification_reasoning:
        lines.append(f"**Reasoning:** {report.classification_reasoning}")
    lines.append("")

    # Router explain details
    re_data = report.router_explain
    if re_data:
        lines.append("### Router Diagnostic (QueryPatterns.classify_domains)")
        lines.append("")
        unified = re_data.get("unified_domains", [])
        if unified:
            lines.append(f"**Unified Domains:** {', '.join(f'`{d}`' for d in unified)}")
        legacy_active = re_data.get("legacy_active_domains", [])
        if legacy_active:
            lines.append(f"**Legacy Active Domains:** {', '.join(f'`{d}`' for d in legacy_active)}")
        router_sources = re_data.get("relevant_sources", [])
        if router_sources:
            lines.append(f"**Router Sources:** {', '.join(f'`{s}`' for s in router_sources)}")
        lines.append("")

    # ── 3. Tool Pool Composition ──────────────────────────────────────
    lines.append("## 3. Tool Pool Composition")
    lines.append("")
    lines.append(f"**Sources Queried:** {', '.join(f'`{s}`' for s in report.sources_queried)}")
    lines.append(f"**Pool Size:** {report.pool_size} tools")
    lines.append("")

    if report.pool:
        # Group by source for readability
        by_source: Dict[str, List[ToolPoolEntry]] = {}
        for entry in report.pool:
            by_source.setdefault(entry.source, []).append(entry)

        for src in sorted(by_source):
            display_src = _SOURCE_DISPLAY.get(src, src)
            tools_in_src = by_source[src]
            lines.append(f"### Source: {display_src} ({len(tools_in_src)} tools)")
            lines.append("")
            lines.append("| Tool | Affordance | Tags | Examples |")
            lines.append("|------|-----------|------|---------|")
            for t in tools_in_src:
                tags_str = ", ".join(t.tags) if t.tags else "—"
                ex_count = len(t.example_queries)
                confirm_note = " ⚠ confirm" if t.requires_confirmation else ""
                lines.append(
                    f"| `{t.tool_name}` | {t.affordance}{confirm_note} "
                    f"| {tags_str} | {ex_count} |"
                )
            lines.append("")

    # ── 4. Scoring Details ────────────────────────────────────────────
    lines.append("## 4. Scoring Details")
    lines.append("")
    lines.append(f"**Ranking Method:** {report.ranking_method}")
    lines.append(f"**Top-K Limit:** {report.top_k}")
    lines.append("")

    scored_sorted = sorted(report.scored_tools, key=lambda e: e.total_score, reverse=True)
    if scored_sorted:
        lines.append("| Tool | Source | KW Score | Tag Score | EQ Score | Total | In Final |")
        lines.append("|------|--------|----------|-----------|----------|-------|----------|")
        for e in scored_sorted:
            final_marker = "✓" if e.in_final_set else ("~~excl~~" if e.excluded else "–")
            kw = f"{e.keyword_score:.1f}"
            tag = f"{e.tag_match_score:.1f}"
            eq = f"{e.example_query_score:.1f}"
            total = f"**{e.total_score:.1f}**" if e.total_score > 0 else "0.0"
            lines.append(
                f"| `{e.tool_name}` | {e.source} | {kw} | {tag} | {eq} | {total} | {final_marker} |"
            )
        lines.append("")

    # ── 5. Final Tool Selection ───────────────────────────────────────
    lines.append("## 5. Final Tool Selection")
    lines.append("")
    lines.append(f"**{report.final_tool_count} tools selected**")
    lines.append("")
    if report.final_tools:
        for i, name in enumerate(report.final_tools, 1):
            manifest = get_tool_manifest_index().get(name)
            src = manifest.source if manifest else "unknown"
            aff = manifest.affordance.value if manifest else "?"
            # Find the score entry
            score_entry = next(
                (e for e in report.scored_tools if e.tool_name == name), None
            )
            rationale_parts: List[str] = []
            if score_entry:
                if score_entry.total_score > 0:
                    rationale_parts.append(f"score={score_entry.total_score:.1f}")
                if score_entry.matched_tokens:
                    rationale_parts.append(f"name-match: {score_entry.matched_tokens}")
                if score_entry.matched_tags:
                    rationale_parts.append(f"tag-match: {score_entry.matched_tags}")
                rationale_parts.extend(score_entry.boost_reasons)
            rationale = "; ".join(rationale_parts) if rationale_parts else "domain pool inclusion"
            lines.append(f"{i}. `{name}` ({src}, {aff}) — {rationale}")
    else:
        lines.append("_No tools selected._")
    lines.append("")

    # ── 6. Alternative Tools Considered ──────────────────────────────
    alternatives = [
        e for e in scored_sorted
        if not e.in_final_set and not e.excluded and e.total_score > 0
    ]
    if alternatives:
        lines.append("## 6. Alternative Tools Considered (Scored but Not Selected)")
        lines.append("")
        lines.append("| Tool | Source | Total Score | Why Not Selected |")
        lines.append("|------|--------|-------------|-----------------|")
        for e in alternatives:
            lines.append(
                f"| `{e.tool_name}` | {e.source} | {e.total_score:.1f} "
                f"| Outside top-{report.top_k} or filtered |"
            )
        lines.append("")

    # ── 7. Excluded Tools and Why ─────────────────────────────────────
    excluded_tools = [e for e in report.scored_tools if e.excluded]
    if excluded_tools or report.tools_removed_by_filter:
        lines.append("## 7. Excluded Tools")
        lines.append("")
        if report.filters_applied:
            lines.append(f"**Filters Applied:** {', '.join(f'`{f}`' for f in report.filters_applied)}")
            lines.append("")
        if excluded_tools:
            lines.append("| Tool | Source | Reason |")
            lines.append("|------|--------|--------|")
            for e in excluded_tools:
                lines.append(f"| `{e.tool_name}` | {e.source} | {e.exclusion_reason or 'unknown'} |")
            lines.append("")

    # ── 8. Conflict Notes Active ──────────────────────────────────────
    lines.append("## 8. Conflict Notes Active")
    lines.append("")
    if report.conflict_notes:
        for note in report.conflict_notes.splitlines():
            lines.append(f"> {note}")
    else:
        lines.append("_No conflict notes active for the selected tool set._")
    lines.append("")

    # ── 9. Guardrails Triggered ───────────────────────────────────────
    lines.append("## 9. Guardrails Triggered")
    lines.append("")
    if report.guardrails:
        for g in report.guardrails:
            injected = (
                f" → injected: {', '.join(f'`{t}`' for t in g.tools_injected)}"
                if g.tools_injected else ""
            )
            removed = (
                f" → removed: {', '.join(f'`{t}`' for t in g.tools_removed)}"
                if g.tools_removed else ""
            )
            lines.append(f"- **{g.name}**{injected}{removed}")
            lines.append(f"  _{g.description}_")
    else:
        lines.append("_No guardrails fired for this query._")
    lines.append("")

    # ── 10. Manifest Improvement Suggestions ─────────────────────────
    lines.append("## 10. Manifest Improvement Suggestions")
    lines.append("")
    if report.suggestions:
        for s in sorted(report.suggestions, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.severity]):
            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "•")
            lines.append(f"### {sev_emoji} {s.tool_name} — `{s.field_name}`")
            lines.append(f"**Issue:** {s.message}")
            lines.append(f"**Fix:** {s.suggestion}")
            lines.append("")
    else:
        lines.append("_No improvement suggestions for the tools selected by this query._")
    lines.append("")

    # ── 11. Scenario Comparison ───────────────────────────────────────
    if report.scenario_comparison:
        sc = report.scenario_comparison
        status = "✅ PASSED" if sc.passed else "❌ FAILED"
        lines.append(f"## 11. Scenario Comparison — {status}")
        lines.append("")
        lines.append(f"**Scenario:** `{sc.scenario_name}`")
        lines.append(f"**Canonical Query:** `{sc.canonical_query}`")
        lines.append("")

        if sc.tools_required:
            lines.append(f"**Required tools:** {', '.join(f'`{t}`' for t in sc.tools_required)}")
        if sc.tools_excluded:
            lines.append(f"**Excluded tools:** {', '.join(f'`{t}`' for t in sc.tools_excluded)}")
        lines.append("")

        if sc.missing_required:
            lines.append("### ❌ Missing Required Tools")
            lines.append("")
            for t in sc.missing_required:
                lines.append(f"- `{t}` — was **not** selected but is **required**")
            lines.append("")

        if sc.unexpected_excluded:
            lines.append("### ❌ Unexpected Excluded Tools Selected")
            lines.append("")
            for t in sc.unexpected_excluded:
                lines.append(f"- `{t}` — was **selected** but should be **excluded**")
            lines.append("")

        if sc.passed:
            lines.append("All required tools selected, all excluded tools absent. ✅")
            lines.append("")

    return "\n".join(lines)


def format_html(report: QueryReport) -> str:
    """Render the report as a standalone HTML page.

    Follows the same visual style as manifest_quality_analyzer.py with
    richer colour coding for scoring and guardrails.
    """
    lines: List[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html lang='en'><head>")
    lines.append("<meta charset='utf-8'>")
    lines.append(f"<title>Tool Selection Report – {_html_escape(report.query[:60])}</title>")
    lines.append("<style>")
    lines.append(textwrap.dedent("""\
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 1400px; margin: 40px auto; padding: 0 24px; color: #1f2937; }
        h1 { color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px;
             margin-bottom: 8px; }
        h2 { color: #111827; margin-top: 2.5em; border-bottom: 1px solid #e5e7eb;
             padding-bottom: 6px; }
        h3 { color: #374151; margin-top: 1.5em; }
        .meta { color: #6b7280; font-size: 0.9em; margin-bottom: 1.5em; }
        table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }
        th, td { border: 1px solid #d1d5db; padding: 7px 12px; text-align: left;
                 vertical-align: top; }
        th { background: #f3f4f6; font-weight: 600; }
        tr:nth-child(even) { background: #f9fafb; }
        code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px;
               font-size: 0.88em; font-family: 'SF Mono', Consolas, monospace; color: #be185d; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 999px;
                 font-size: 0.82em; font-weight: 600; }
        .badge-read        { background: #d1fae5; color: #065f46; }
        .badge-write       { background: #fef3c7; color: #92400e; }
        .badge-destructive { background: #fee2e2; color: #991b1b; }
        .badge-deploy      { background: #ede9fe; color: #5b21b6; }
        .badge-pass        { background: #d1fae5; color: #065f46; }
        .badge-fail        { background: #fee2e2; color: #991b1b; }
        .score-high  { color: #0d652d; font-weight: 600; }
        .score-mid   { color: #b45309; font-weight: 600; }
        .score-zero  { color: #9ca3af; }
        .final-yes   { color: #0d652d; font-weight: bold; }
        .final-no    { color: #9ca3af; }
        .final-excl  { color: #dc2626; text-decoration: line-through; }
        .guard       { background: #fef3c7; border-left: 4px solid #f59e0b;
                       padding: 8px 12px; margin: 6px 0; border-radius: 0 6px 6px 0; }
        .conflict    { background: #f0f9ff; border-left: 4px solid #0ea5e9;
                       padding: 8px 12px; margin: 6px 0; border-radius: 0 6px 6px 0;
                       font-family: 'SF Mono', Consolas, monospace; font-size: 0.88em; }
        .sug-high    { border-left: 4px solid #dc2626; background: #fff5f5;
                       padding: 10px 14px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .sug-medium  { border-left: 4px solid #f59e0b; background: #fffbeb;
                       padding: 10px 14px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .sug-low     { border-left: 4px solid #10b981; background: #f0fdf4;
                       padding: 10px 14px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .scenario-pass { background: #d1fae5; padding: 12px 16px; border-radius: 8px; }
        .scenario-fail { background: #fee2e2; padding: 12px 16px; border-radius: 8px; }
        ul { padding-left: 1.5em; }
        li { margin: 0.25em 0; }
        .prop-table td:first-child { font-weight: 600; width: 220px; }
    """))
    lines.append("</style></head><body>")

    # ── Header ───────────────────────────────────────────────────────
    lines.append(f"<h1>Tool Selection Trace Report</h1>")
    lines.append(
        f"<p class='meta'>"
        f"<strong>Generated:</strong> {_html_escape(report.generated_at)} &nbsp;|&nbsp; "
        f"<strong>Strategy:</strong> {_html_escape(report.strategy)} &nbsp;|&nbsp; "
        f"<strong>Duration:</strong> {report.duration_ms:.1f}ms"
        f"</p>"
    )
    lines.append(f"<p><strong>Query:</strong> <code>{_html_escape(report.query)}</code></p>")

    # ── 1. Query Analysis ─────────────────────────────────────────────
    lines.append("<h2>1. Query Analysis</h2>")
    lines.append("<table class='prop-table'><tr><th>Property</th><th>Value</th></tr>")
    _html_row(lines, "Detected Intent", f"<code>{report.detected_intent}</code>")
    _html_row(lines, "Read Intent", "Yes ✓" if report.is_read_intent else "No")
    _html_row(lines, "Container App List Intent", "Yes ✓" if report.is_container_app_list_intent else "No")
    _html_row(lines, "Container App Health Intent", "Yes ✓" if report.is_container_app_health_intent else "No")
    if report.legacy_active_domains:
        _html_row(lines, "Active Legacy Domains", _code_list(report.legacy_active_domains))
    if report.relevant_sources:
        _html_row(lines, "Relevant Sources", _code_list(report.relevant_sources))
    if report.query_tokens:
        _html_row(lines, "Query Tokens", _code_list(sorted(report.query_tokens)))
    lines.append("</table>")

    # ── 2. Domain Classification ──────────────────────────────────────
    lines.append("<h2>2. Domain Classification</h2>")
    lines.append("<table class='prop-table'><tr><th>Property</th><th>Value</th></tr>")
    conf_cls = "score-high" if report.primary_confidence >= 0.7 else (
        "score-mid" if report.primary_confidence >= 0.4 else "score-zero"
    )
    _html_row(
        lines, "Primary Domain",
        f"<code>{_html_escape(report.primary_domain)}</code> "
        f"<span class='{conf_cls}'>{report.primary_confidence:.0%} confidence</span>",
    )
    if report.secondary_domains:
        _html_row(lines, "Secondary Domains", _code_list(report.secondary_domains))
    if report.classification_reasoning:
        _html_row(lines, "Reasoning", _html_escape(report.classification_reasoning))
    re_data = report.router_explain
    if re_data:
        if re_data.get("unified_domains"):
            _html_row(lines, "Unified Domains", _code_list(re_data["unified_domains"]))
        if re_data.get("relevant_sources"):
            _html_row(lines, "Router Sources", _code_list(re_data["relevant_sources"]))
    lines.append("</table>")

    # ── 3. Tool Pool Composition ──────────────────────────────────────
    lines.append("<h2>3. Tool Pool Composition</h2>")
    lines.append(
        f"<p><strong>Sources:</strong> {_code_list(report.sources_queried)} "
        f"&nbsp;|&nbsp; <strong>Pool Size:</strong> {report.pool_size} tools</p>"
    )
    if report.pool:
        by_source: Dict[str, List[ToolPoolEntry]] = {}
        for entry in report.pool:
            by_source.setdefault(entry.source, []).append(entry)

        for src in sorted(by_source):
            display_src = _SOURCE_DISPLAY.get(src, src)
            tools_in_src = by_source[src]
            lines.append(f"<h3>{_html_escape(display_src)} ({len(tools_in_src)} tools)</h3>")
            lines.append("<table><tr><th>Tool</th><th>Affordance</th><th>Tags</th><th>Examples</th></tr>")
            for t in tools_in_src:
                aff_class = f"badge-{t.affordance.lower()}"
                tags_str = ", ".join(f"<code>{_html_escape(tag)}</code>" for tag in t.tags) or "—"
                confirm_badge = " <span class='badge badge-write'>⚠ confirm</span>" if t.requires_confirmation else ""
                lines.append(
                    f"<tr><td><code>{_html_escape(t.tool_name)}</code></td>"
                    f"<td><span class='badge {aff_class}'>{t.affordance}</span>{confirm_badge}</td>"
                    f"<td>{tags_str}</td>"
                    f"<td>{len(t.example_queries)}</td></tr>"
                )
            lines.append("</table>")

    # ── 4. Scoring Details ────────────────────────────────────────────
    lines.append("<h2>4. Scoring Details</h2>")
    lines.append(
        f"<p><strong>Ranking Method:</strong> {_html_escape(report.ranking_method)} "
        f"&nbsp;|&nbsp; <strong>Top-K:</strong> {report.top_k}</p>"
    )
    scored_sorted = sorted(report.scored_tools, key=lambda e: e.total_score, reverse=True)
    if scored_sorted:
        lines.append(
            "<table><tr><th>Tool</th><th>Source</th><th>KW Score</th>"
            "<th>Tag Score</th><th>EQ Score</th><th>Total</th><th>In Final</th></tr>"
        )
        for e in scored_sorted:
            total_cls = "score-high" if e.total_score >= 6 else ("score-mid" if e.total_score >= 2 else "score-zero")
            if e.in_final_set:
                final_cell = "<span class='final-yes'>✓</span>"
            elif e.excluded:
                final_cell = "<span class='final-excl'>excl</span>"
            else:
                final_cell = "<span class='final-no'>—</span>"
            lines.append(
                f"<tr><td><code>{_html_escape(e.tool_name)}</code></td>"
                f"<td>{_html_escape(e.source)}</td>"
                f"<td>{e.keyword_score:.1f}</td>"
                f"<td>{e.tag_match_score:.1f}</td>"
                f"<td>{e.example_query_score:.1f}</td>"
                f"<td class='{total_cls}'><strong>{e.total_score:.1f}</strong></td>"
                f"<td>{final_cell}</td></tr>"
            )
        lines.append("</table>")

    # ── 5. Final Tool Selection ───────────────────────────────────────
    lines.append(f"<h2>5. Final Tool Selection ({report.final_tool_count} tools)</h2>")
    if report.final_tools:
        lines.append("<ol>")
        manifest_index = get_tool_manifest_index()
        for name in report.final_tools:
            manifest = manifest_index.get(name)
            src = manifest.source if manifest else "unknown"
            aff = manifest.affordance.value if manifest else "?"
            aff_cls = f"badge-{aff.lower()}"
            score_entry = next(
                (e for e in report.scored_tools if e.tool_name == name), None
            )
            details: List[str] = [
                f"<span class='badge {aff_cls}'>{aff}</span>",
                f"<em>{_html_escape(src)}</em>",
            ]
            if score_entry and score_entry.total_score > 0:
                details.append(f"score={score_entry.total_score:.1f}")
            if score_entry and score_entry.matched_tokens:
                details.append(f"name-match: {score_entry.matched_tokens}")
            if score_entry and score_entry.matched_tags:
                details.append(f"tag-match: {score_entry.matched_tags}")
            if score_entry and score_entry.boost_reasons:
                details.extend(score_entry.boost_reasons)
            lines.append(
                f"<li><code>{_html_escape(name)}</code> — "
                + " &nbsp; ".join(details) + "</li>"
            )
        lines.append("</ol>")
    else:
        lines.append("<p><em>No tools selected.</em></p>")

    # ── 6. Alternative Tools Considered ──────────────────────────────
    alternatives = [
        e for e in scored_sorted
        if not e.in_final_set and not e.excluded and e.total_score > 0
    ]
    if alternatives:
        lines.append("<h2>6. Alternative Tools Considered</h2>")
        lines.append("<table><tr><th>Tool</th><th>Source</th><th>Total Score</th><th>Why Not Selected</th></tr>")
        for e in alternatives:
            lines.append(
                f"<tr><td><code>{_html_escape(e.tool_name)}</code></td>"
                f"<td>{_html_escape(e.source)}</td>"
                f"<td>{e.total_score:.1f}</td>"
                f"<td>Outside top-{report.top_k} or filtered</td></tr>"
            )
        lines.append("</table>")

    # ── 7. Excluded Tools ─────────────────────────────────────────────
    excluded_tools = [e for e in report.scored_tools if e.excluded]
    if excluded_tools or report.tools_removed_by_filter:
        lines.append("<h2>7. Excluded Tools</h2>")
        if report.filters_applied:
            lines.append(f"<p><strong>Filters:</strong> {_code_list(report.filters_applied)}</p>")
        if excluded_tools:
            lines.append("<table><tr><th>Tool</th><th>Source</th><th>Reason</th></tr>")
            for e in excluded_tools:
                lines.append(
                    f"<tr><td><code>{_html_escape(e.tool_name)}</code></td>"
                    f"<td>{_html_escape(e.source)}</td>"
                    f"<td>{_html_escape(e.exclusion_reason or 'unknown')}</td></tr>"
                )
            lines.append("</table>")

    # ── 8. Conflict Notes ─────────────────────────────────────────────
    lines.append("<h2>8. Conflict Notes Active</h2>")
    if report.conflict_notes:
        for note in report.conflict_notes.splitlines():
            lines.append(f"<div class='conflict'>{_html_escape(note)}</div>")
    else:
        lines.append("<p><em>No conflict notes active for the selected tool set.</em></p>")

    # ── 9. Guardrails ─────────────────────────────────────────────────
    lines.append("<h2>9. Guardrails Triggered</h2>")
    if report.guardrails:
        for g in report.guardrails:
            injected = (
                f" <strong>Injected:</strong> {_code_list(g.tools_injected)}"
                if g.tools_injected else ""
            )
            removed = (
                f" <strong>Removed:</strong> {_code_list(g.tools_removed)}"
                if g.tools_removed else ""
            )
            lines.append(
                f"<div class='guard'>"
                f"<strong>{_html_escape(g.name)}</strong>{injected}{removed}<br>"
                f"<em>{_html_escape(g.description)}</em>"
                f"</div>"
            )
    else:
        lines.append("<p><em>No guardrails fired for this query.</em></p>")

    # ── 10. Manifest Improvement Suggestions ─────────────────────────
    lines.append("<h2>10. Manifest Improvement Suggestions</h2>")
    if report.suggestions:
        for s in sorted(report.suggestions, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.severity]):
            sev_class = f"sug-{s.severity}"
            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "•")
            lines.append(
                f"<div class='{sev_class}'>"
                f"<strong>{sev_emoji} {_html_escape(s.tool_name)}</strong> "
                f"— <code>{_html_escape(s.field_name)}</code><br>"
                f"<strong>Issue:</strong> {_html_escape(s.message)}<br>"
                f"<strong>Fix:</strong> {_html_escape(s.suggestion)}"
                f"</div>"
            )
    else:
        lines.append("<p><em>No improvement suggestions for this query.</em></p>")

    # ── 11. Scenario Comparison ───────────────────────────────────────
    if report.scenario_comparison:
        sc = report.scenario_comparison
        status_class = "scenario-pass" if sc.passed else "scenario-fail"
        status_text = "✅ PASSED" if sc.passed else "❌ FAILED"
        lines.append(f"<h2>11. Scenario Comparison — {status_text}</h2>")
        lines.append(f"<div class='{status_class}'>")
        lines.append(f"<p><strong>Scenario:</strong> <code>{_html_escape(sc.scenario_name)}</code></p>")
        lines.append(f"<p><strong>Canonical Query:</strong> <code>{_html_escape(sc.canonical_query)}</code></p>")
        if sc.tools_required:
            lines.append(f"<p><strong>Required:</strong> {_code_list(sc.tools_required)}</p>")
        if sc.tools_excluded:
            lines.append(f"<p><strong>Excluded:</strong> {_code_list(sc.tools_excluded)}</p>")
        if sc.missing_required:
            lines.append(f"<p>❌ <strong>Missing required tools:</strong> {_code_list(sc.missing_required)}</p>")
        if sc.unexpected_excluded:
            lines.append(f"<p>❌ <strong>Unexpected excluded tools selected:</strong> {_code_list(sc.unexpected_excluded)}</p>")
        if sc.passed:
            lines.append("<p>All required tools selected, all excluded tools absent.</p>")
        lines.append("</div>")

    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML helper utilities
# ---------------------------------------------------------------------------

def _html_escape(text: str) -> str:
    """Minimal HTML entity escaping."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _code_list(items: List[str]) -> str:
    """Render a list of strings as inline HTML code tags."""
    return " ".join(f"<code>{_html_escape(i)}</code>" for i in items)


def _html_row(lines: List[str], label: str, value: str) -> None:
    lines.append(f"<tr><td>{_html_escape(label)}</td><td>{value}</td></tr>")


# ---------------------------------------------------------------------------
# Multi-scenario summary formatters
# ---------------------------------------------------------------------------

def format_all_scenarios_markdown(
    reports: List[Tuple[str, QueryReport]],
) -> str:
    """Generate a summary markdown for all-scenarios mode."""
    lines: List[str] = []
    lines.append("# Tool Selection Reporter — All Scenarios Summary")
    lines.append("")
    lines.append(f"**Scenarios Run:** {len(reports)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"**Generated:** {now}")
    lines.append("")

    passed = [r for _, r in reports if r.scenario_comparison and r.scenario_comparison.passed]
    failed = [r for _, r in reports if r.scenario_comparison and not r.scenario_comparison.passed]

    lines.append(f"**Results:** {len(passed)} passed / {len(failed)} failed / "
                 f"{len(reports) - len(passed) - len(failed)} no-contract")
    lines.append("")

    # Summary table
    lines.append("| Scenario | Query | Status | Missing | Unexpected |")
    lines.append("|----------|-------|--------|---------|------------|")
    for name, r in reports:
        sc = r.scenario_comparison
        if sc:
            status = "✅ PASS" if sc.passed else "❌ FAIL"
            missing = ", ".join(sc.missing_required) or "—"
            unexpected = ", ".join(sc.unexpected_excluded) or "—"
            query_short = (r.query[:50] + "…") if len(r.query) > 50 else r.query
            lines.append(f"| {name} | {query_short} | {status} | {missing} | {unexpected} |")
        else:
            query_short = (r.query[:50] + "…") if len(r.query) > 50 else r.query
            lines.append(f"| {name} | {query_short} | (no contract) | — | — |")
    lines.append("")

    # Per-scenario detail
    lines.append("---")
    lines.append("")
    for name, r in reports:
        lines.append(f"## Scenario: {name}")
        lines.append("")
        lines.append(format_markdown(r))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the tool selection reporter from the command line."""
    parser = argparse.ArgumentParser(
        prog="tool_selection_reporter",
        description="Generate tool-selection trace reports for debugging and manifest analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          python -m utils.tool_selection_reporter "list my container apps"
          python -m utils.tool_selection_reporter "check VM health" --format json
          python -m utils.tool_selection_reporter "show all VMs" --format html -o report.html
          python -m utils.tool_selection_reporter --scenario container_app_health
          python -m utils.tool_selection_reporter --all-scenarios
          python -m utils.tool_selection_reporter --all-scenarios --format html -o all.html
        """),
    )

    # Mutually exclusive query source
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument(
        "query",
        nargs="?",
        help="Natural-language query to analyse",
    )
    query_group.add_argument(
        "--scenario",
        metavar="NAME",
        help="Load a golden scenario by name and run its canonical query",
    )
    query_group.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run against all golden scenarios and produce a summary report",
    )

    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--strategy",
        choices=["fast", "quality", "comprehensive"],
        default="fast",
        help="Routing strategy label for the report header (default: fast)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress messages on stderr",
    )

    args = parser.parse_args()

    reporter = ToolSelectionReporter()

    if not args.quiet:
        print("Initialising reporter (loading manifest index)…", file=sys.stderr)

    # ── Single query mode ─────────────────────────────────────────────
    if args.query:
        if not args.quiet:
            print(f"Analysing query: {args.query!r}", file=sys.stderr)

        report = asyncio.run(reporter.generate_report(args.query, strategy=args.strategy))

        if not args.quiet:
            print(
                f"Done. Pool={report.pool_size}, Final={report.final_tool_count}, "
                f"Duration={report.duration_ms:.1f}ms",
                file=sys.stderr,
            )

        output = _format_single(report, args.format)
        _write_output(output, args.output, args.quiet)

    # ── Single scenario mode ──────────────────────────────────────────
    elif args.scenario:
        scenario = _try_load_scenario(args.scenario)
        if scenario is None:
            print(
                f"Error: Could not load scenario '{args.scenario}'. "
                f"Check that tests/scenarios/{args.scenario}.yaml exists.",
                file=sys.stderr,
            )
            sys.exit(1)

        query = scenario.canonical_query
        if not args.quiet:
            print(f"Scenario: {scenario.name}", file=sys.stderr)
            print(f"Canonical query: {query!r}", file=sys.stderr)

        report = asyncio.run(reporter.generate_report(query, strategy=args.strategy))
        _attach_scenario_comparison(report, scenario)

        if not args.quiet:
            sc = report.scenario_comparison
            status = "PASS" if sc and sc.passed else "FAIL"
            print(
                f"Result: {status}. Pool={report.pool_size}, Final={report.final_tool_count}, "
                f"Duration={report.duration_ms:.1f}ms",
                file=sys.stderr,
            )

        output = _format_single(report, args.format)
        _write_output(output, args.output, args.quiet)

    # ── All-scenarios mode ────────────────────────────────────────────
    else:
        scenarios = _try_load_all_scenarios()
        if not scenarios:
            print(
                "Error: Could not load any scenarios. "
                "Ensure tests/scenarios/*.yaml files exist.",
                file=sys.stderr,
            )
            sys.exit(1)

        if not args.quiet:
            print(f"Running {len(scenarios)} scenarios…", file=sys.stderr)

        named_reports: List[Tuple[str, QueryReport]] = []
        for scenario in scenarios:
            query = scenario.canonical_query
            if not args.quiet:
                print(f"  [{scenario.name}] {query!r}", file=sys.stderr)

            report = asyncio.run(reporter.generate_report(query, strategy=args.strategy))
            _attach_scenario_comparison(report, scenario)
            named_reports.append((scenario.name, report))

        passed = sum(
            1 for _, r in named_reports
            if r.scenario_comparison and r.scenario_comparison.passed
        )
        total = len(named_reports)
        if not args.quiet:
            print(f"Scenarios: {passed}/{total} passed.", file=sys.stderr)

        if args.format == "json":
            output = json.dumps(
                [{"scenario": name, "report": r.to_dict()} for name, r in named_reports],
                indent=2,
                default=str,
            )
        elif args.format == "html":
            # Build HTML from markdown summary
            md_summary = format_all_scenarios_markdown(named_reports)
            output = _markdown_to_minimal_html(md_summary, title="All Scenarios Summary")
        else:
            output = format_all_scenarios_markdown(named_reports)

        _write_output(output, args.output, args.quiet)


def _format_single(report: QueryReport, fmt: str) -> str:
    if fmt == "json":
        return format_json(report)
    elif fmt == "html":
        return format_html(report)
    return format_markdown(report)


def _write_output(output: str, path: Optional[str], quiet: bool) -> None:
    if path:
        Path(path).write_text(output, encoding="utf-8")
        if not quiet:
            print(f"Report written to: {path}", file=sys.stderr)
    else:
        print(output)


def _markdown_to_minimal_html(md: str, title: str = "Report") -> str:
    """Wrap markdown in a minimal HTML page (no markdown rendering — preformatted)."""
    return (
        f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{_html_escape(title)}</title>"
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "max-width:1200px;margin:40px auto;padding:0 20px;color:#333;}"
        "pre{background:#f5f5f5;padding:20px;border-radius:8px;overflow-x:auto;"
        "font-size:0.9em;line-height:1.5;}"
        "</style>"
        "</head><body>"
        f"<pre>{_html_escape(md)}</pre>"
        "</body></html>"
    )


if __name__ == "__main__":
    main()
