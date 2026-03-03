"""Manifest change impact analyzer.

Compares a "before" and "after" tool manifest state, runs test queries through
both versions, and generates an impact report showing exactly which queries are
affected and how.

Design goals:
- Works **offline** — no Azure, no MCP server connections required.
- Completes in <5 seconds for any single-tool analysis.
- Risk assessment is conservative: any potential regression is flagged.
- Actionable output: every finding comes with a specific recommendation.

Usage
-----
# From app/agentic/eol directory:
    python -m utils.manifest_impact_analyzer check_resource_health \\
        --tags '["health","diagnostics","resource","sre"]'

    python -m utils.manifest_impact_analyzer --before old_manifest.json \\
        --after new_manifest.json

    python -m utils.manifest_impact_analyzer --baseline

    python -m utils.manifest_impact_analyzer container_app_list \\
        --test-query "list my container apps" \\
        --test-query "show container apps"

    python -m utils.manifest_impact_analyzer --baseline --format json
    python -m utils.manifest_impact_analyzer --baseline --format html -o impact.html

    python -m utils.manifest_impact_analyzer --baseline --ci   # exits 1 on regressions

# From repository root:
    python -m app.agentic.eol.utils.manifest_impact_analyzer --baseline
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

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
    from utils.query_patterns import QueryPatterns  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Scoring constants (mirror tool_selection_reporter.py exactly)
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 15

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

_READ_INTENT_RE = re.compile(
    r"^\s*(?:list|show|get|display|fetch|find|describe|enumerate"
    r"|what\s+(?:are|is)\s+(?:my|the)|how\s+many)\b",
    re.IGNORECASE,
)

_ACTION_TOOL_PREFIXES: Tuple[str, ...] = (
    "test_", "check_", "create_", "delete_", "update_", "restart_",
    "trigger_", "enable_", "disable_", "assign_", "run_", "execute_",
    "invoke_", "start_", "stop_", "reset_", "patch_", "deploy_",
)

_CLI_FALLBACK_TOOL = "azure_cli_execute_command"
_CONTAINER_APP_LIST_TOOL = "container_app_list"
_CONTAINER_APP_HEALTH_TOOL = "check_container_app_health"

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
    "general":    ["azure", "sre", "monitor", "inventory", "os_eol", "azure_cli",
                   "compute", "storage", "network"],
}

# Affordance escalation order (READ < WRITE < DEPLOY < DESTRUCTIVE)
_AFFORDANCE_SEVERITY_ORDER = [
    ToolAffordance.READ,
    ToolAffordance.WRITE,
    ToolAffordance.DEPLOY,
    ToolAffordance.DESTRUCTIVE,
]


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScoredTool:
    """Lightweight per-tool scoring result from offline simulation."""
    tool_name: str
    source: str
    total_score: float
    in_final_set: bool = False
    rank: int = 0                   # 1-based position in final selection (0 = not selected)
    excluded: bool = False
    exclusion_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "source": self.source,
            "total_score": round(self.total_score, 2),
            "in_final_set": self.in_final_set,
            "rank": self.rank,
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
        }


@dataclass
class ManifestDiff:
    """Field-level diff between two versions of a ToolManifest.

    Each changed_fields entry is a dict with keys:
        field, before_value, after_value, change_type
    where change_type is one of: "modified", "added", "removed".
    """
    tool_name: str
    changed_fields: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""                   # Human-readable one-liner
    affordance_escalated: bool = False  # True when affordance moves toward DESTRUCTIVE
    tags_removed: List[str] = field(default_factory=list)
    tags_added: List[str] = field(default_factory=list)
    domains_removed: List[str] = field(default_factory=list)
    domains_added: List[str] = field(default_factory=list)
    example_queries_removed: List[str] = field(default_factory=list)
    example_queries_added: List[str] = field(default_factory=list)
    conflicts_removed: List[str] = field(default_factory=list)
    conflicts_added: List[str] = field(default_factory=list)
    is_identical: bool = False          # True when before == after (no real change)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "is_identical": self.is_identical,
            "affordance_escalated": self.affordance_escalated,
            "tags_removed": self.tags_removed,
            "tags_added": self.tags_added,
            "domains_removed": self.domains_removed,
            "domains_added": self.domains_added,
            "example_queries_removed": self.example_queries_removed,
            "example_queries_added": self.example_queries_added,
            "conflicts_removed": self.conflicts_removed,
            "conflicts_added": self.conflicts_added,
            "changed_fields": self.changed_fields,
            "summary": self.summary,
        }


@dataclass
class RankChange:
    """Captures a tool's positional movement between before/after."""
    tool_name: str
    before_rank: int    # 0 = not in final set
    after_rank: int     # 0 = not in final set

    @property
    def delta(self) -> int:
        """Signed rank delta (negative = moved up = better; positive = moved down)."""
        if self.before_rank == 0 and self.after_rank == 0:
            return 0
        if self.before_rank == 0:
            return -self.after_rank   # Entered set (treat as large positive boost)
        if self.after_rank == 0:
            return self.before_rank   # Left set (treat as large positive drop)
        return self.after_rank - self.before_rank

    @property
    def label(self) -> str:
        if self.before_rank == 0 and self.after_rank > 0:
            return f"entered_set@{self.after_rank}"
        if self.before_rank > 0 and self.after_rank == 0:
            return f"left_set@was_{self.before_rank}"
        if self.before_rank > 0 and self.after_rank > 0:
            diff = self.after_rank - self.before_rank
            if diff < 0:
                return f"up_{abs(diff)}_positions"
            elif diff > 0:
                return f"down_{diff}_positions"
            return "unchanged"
        return "unchanged"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "before_rank": self.before_rank,
            "after_rank": self.after_rank,
            "delta": self.delta,
            "label": self.label,
        }


@dataclass
class QueryImpact:
    """How a single query is affected by the manifest change."""
    query: str
    before_tools: List[str] = field(default_factory=list)   # Final selection (before)
    after_tools: List[str] = field(default_factory=list)    # Final selection (after)
    tools_gained: List[str] = field(default_factory=list)   # New entries
    tools_lost: List[str] = field(default_factory=list)     # Dropped entries
    rank_changes: List[RankChange] = field(default_factory=list)
    regression: bool = False            # Required golden tools disappeared
    risk_level: str = "none"            # "high" | "medium" | "low" | "none"
    risk_reasons: List[str] = field(default_factory=list)
    from_golden_scenario: bool = False  # True when sourced from a golden scenario
    scenario_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "before_tools": self.before_tools,
            "after_tools": self.after_tools,
            "tools_gained": self.tools_gained,
            "tools_lost": self.tools_lost,
            "rank_changes": [r.to_dict() for r in self.rank_changes],
            "regression": self.regression,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
            "from_golden_scenario": self.from_golden_scenario,
            "scenario_name": self.scenario_name,
        }


@dataclass
class ImpactReport:
    """Full analysis report for a manifest change.

    Sections mirror the markdown output sections for 1:1 correspondence
    between the dataclass and the rendered report.
    """
    # ── Meta ──────────────────────────────────────────────────────────
    generated_at: str = ""
    tool_name: str = ""          # Primary tool under analysis (may be empty for baseline)
    analysis_mode: str = ""      # "single_tool" | "file_compare" | "baseline"
    duration_ms: float = 0.0

    # ── 1. Manifest Diffs ─────────────────────────────────────────────
    manifest_diffs: List[ManifestDiff] = field(default_factory=list)

    # ── 2. Query Impacts ──────────────────────────────────────────────
    query_impacts: List[QueryImpact] = field(default_factory=list)

    # ── 3. Summary ────────────────────────────────────────────────────
    total_queries_tested: int = 0
    queries_affected: int = 0
    queries_with_regressions: int = 0
    queries_with_gains: int = 0

    # ── 4. Risk Assessment ────────────────────────────────────────────
    risk_assessment: str = "none"       # "high" | "medium" | "low" | "none"
    risk_summary: str = ""

    # ── 5. Regressions ────────────────────────────────────────────────
    regressions: List[Dict[str, Any]] = field(default_factory=list)

    # ── 6. Validation Checklist ───────────────────────────────────────
    validation_checklist: List[str] = field(default_factory=list)

    # ── 7. Recommendations ────────────────────────────────────────────
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "tool_name": self.tool_name,
            "analysis_mode": self.analysis_mode,
            "duration_ms": round(self.duration_ms, 2),
            "manifest_diffs": [d.to_dict() for d in self.manifest_diffs],
            "query_impacts": [qi.to_dict() for qi in self.query_impacts],
            "summary": {
                "total_queries_tested": self.total_queries_tested,
                "queries_affected": self.queries_affected,
                "queries_with_regressions": self.queries_with_regressions,
                "queries_with_gains": self.queries_with_gains,
            },
            "risk_assessment": self.risk_assessment,
            "risk_summary": self.risk_summary,
            "regressions": self.regressions,
            "validation_checklist": self.validation_checklist,
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Offline scoring helpers (identical logic to tool_selection_reporter.py)
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


def _keyword_score(tokens: Set[str], tool_name: str) -> Tuple[float, List[str]]:
    """Score a tool by token overlap with its name."""
    if not tokens:
        return 0.0, []
    name_tokens = set(re.findall(r"[a-z0-9]+", tool_name.lower()))
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
    return score, matched


def _tag_score(tokens: Set[str], tags: FrozenSet[str]) -> float:
    """Score a tool by tag overlap with query tokens (+2.0 per match)."""
    if not tokens or not tags:
        return 0.0
    matched = sum(
        1 for tag in tags
        if any(tok in tag.lower() or tag.lower() in tok for tok in tokens)
    )
    return float(matched * 2)


def _example_query_score(tokens: Set[str], example_queries: Tuple[str, ...]) -> float:
    """Score a tool by token overlap across example_queries (+0.5 per unique match)."""
    if not tokens or not example_queries:
        return 0.0
    combined = " ".join(example_queries).lower()
    matched = sum(1 for tok in tokens if tok in combined)
    return float(matched) * 0.5


def _is_action_tool(name: str) -> bool:
    """Return True when a tool name starts with an action-verb prefix."""
    lname = name.lower()
    return any(lname.startswith(p) for p in _ACTION_TOOL_PREFIXES)


def _get_sources_for_query(
    primary_domain: str,
    secondary_domains: List[str],
    relevant_sources: List[str],
) -> Set[str]:
    """Determine which manifest sources to include in the tool pool."""
    sources: Set[str] = set(
        _DOMAIN_LABEL_TO_SOURCES.get(primary_domain, ["general"])
    )
    for sec in secondary_domains:
        for src in _DOMAIN_LABEL_TO_SOURCES.get(sec, []):
            sources.add(src)
    for src in relevant_sources:
        sources.add(src)
    return sources


# ---------------------------------------------------------------------------
# Core analyzer
# ---------------------------------------------------------------------------

class ManifestImpactAnalyzer:
    """Offline manifest change impact analyzer.

    Compares before/after manifest states, simulates tool selection for a set
    of test queries, and produces a structured impact report.

    All analysis is performed **offline** — no Azure credentials, no MCP server
    connections, and no embedding models are required.

    Thread safety: safe to share between calls; ``analyze_impact`` and related
    methods create no shared mutable state between invocations.
    """

    def __init__(self) -> None:
        self._classifier: DomainClassifier = get_domain_classifier()
        self._base_index: ToolManifestIndex = get_tool_manifest_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diff_manifest(
        self,
        before: ToolManifest,
        after: ToolManifest,
    ) -> ManifestDiff:
        """Compare two versions of a tool manifest and return a structured diff.

        Args:
            before: The current (old) manifest.
            after:  The proposed (new) manifest.

        Returns:
            ManifestDiff capturing every field-level change with human-readable
            summaries and computed semantic flags (affordance_escalated, etc.).
        """
        diff = ManifestDiff(tool_name=before.tool_name)
        changed: List[str] = []

        # ── tool_name ─────────────────────────────────────────────────
        if before.tool_name != after.tool_name:
            diff.changed_fields.append({
                "field": "tool_name",
                "before_value": before.tool_name,
                "after_value": after.tool_name,
                "change_type": "modified",
            })
            changed.append("tool_name")

        # ── source ────────────────────────────────────────────────────
        if before.source != after.source:
            diff.changed_fields.append({
                "field": "source",
                "before_value": before.source,
                "after_value": after.source,
                "change_type": "modified",
            })
            changed.append("source")

        # ── affordance ────────────────────────────────────────────────
        if before.affordance != after.affordance:
            diff.changed_fields.append({
                "field": "affordance",
                "before_value": before.affordance.value,
                "after_value": after.affordance.value,
                "change_type": "modified",
            })
            changed.append("affordance")
            # Escalation: moving toward DESTRUCTIVE is high-risk
            before_idx = _AFFORDANCE_SEVERITY_ORDER.index(before.affordance) \
                if before.affordance in _AFFORDANCE_SEVERITY_ORDER else 0
            after_idx = _AFFORDANCE_SEVERITY_ORDER.index(after.affordance) \
                if after.affordance in _AFFORDANCE_SEVERITY_ORDER else 0
            diff.affordance_escalated = after_idx > before_idx

        # ── domains ───────────────────────────────────────────────────
        before_domains = set(before.domains)
        after_domains = set(after.domains)
        removed_domains = sorted(before_domains - after_domains)
        added_domains = sorted(after_domains - before_domains)
        if removed_domains or added_domains:
            diff.domains_removed = removed_domains
            diff.domains_added = added_domains
            diff.changed_fields.append({
                "field": "domains",
                "before_value": sorted(before_domains),
                "after_value": sorted(after_domains),
                "change_type": "modified",
                "removed": removed_domains,
                "added": added_domains,
            })
            changed.append("domains")

        # ── tags ──────────────────────────────────────────────────────
        before_tags = set(before.tags)
        after_tags = set(after.tags)
        removed_tags = sorted(before_tags - after_tags)
        added_tags = sorted(after_tags - before_tags)
        if removed_tags or added_tags:
            diff.tags_removed = removed_tags
            diff.tags_added = added_tags
            diff.changed_fields.append({
                "field": "tags",
                "before_value": sorted(before_tags),
                "after_value": sorted(after_tags),
                "change_type": "modified",
                "removed": removed_tags,
                "added": added_tags,
            })
            changed.append("tags")

        # ── example_queries ───────────────────────────────────────────
        before_eqs = set(before.example_queries)
        after_eqs = set(after.example_queries)
        removed_eqs = sorted(before_eqs - after_eqs)
        added_eqs = sorted(after_eqs - before_eqs)
        if removed_eqs or added_eqs:
            diff.example_queries_removed = removed_eqs
            diff.example_queries_added = added_eqs
            diff.changed_fields.append({
                "field": "example_queries",
                "before_value": list(before.example_queries),
                "after_value": list(after.example_queries),
                "change_type": "modified",
                "removed": removed_eqs,
                "added": added_eqs,
            })
            changed.append("example_queries")

        # ── conflicts_with ────────────────────────────────────────────
        before_conflicts = set(before.conflicts_with)
        after_conflicts = set(after.conflicts_with)
        removed_conflicts = sorted(before_conflicts - after_conflicts)
        added_conflicts = sorted(after_conflicts - before_conflicts)
        if removed_conflicts or added_conflicts:
            diff.conflicts_removed = removed_conflicts
            diff.conflicts_added = added_conflicts
            diff.changed_fields.append({
                "field": "conflicts_with",
                "before_value": sorted(before_conflicts),
                "after_value": sorted(after_conflicts),
                "change_type": "modified",
                "removed": removed_conflicts,
                "added": added_conflicts,
            })
            changed.append("conflicts_with")

        # ── conflict_note ─────────────────────────────────────────────
        if before.conflict_note != after.conflict_note:
            diff.changed_fields.append({
                "field": "conflict_note",
                "before_value": before.conflict_note,
                "after_value": after.conflict_note,
                "change_type": "modified",
            })
            changed.append("conflict_note")

        # ── preferred_over ────────────────────────────────────────────
        if set(before.preferred_over) != set(after.preferred_over):
            diff.changed_fields.append({
                "field": "preferred_over",
                "before_value": sorted(before.preferred_over),
                "after_value": sorted(after.preferred_over),
                "change_type": "modified",
            })
            changed.append("preferred_over")

        # ── requires_confirmation ─────────────────────────────────────
        if before.requires_confirmation != after.requires_confirmation:
            diff.changed_fields.append({
                "field": "requires_confirmation",
                "before_value": before.requires_confirmation,
                "after_value": after.requires_confirmation,
                "change_type": "modified",
            })
            changed.append("requires_confirmation")

        # ── deprecated ────────────────────────────────────────────────
        if before.deprecated != after.deprecated:
            diff.changed_fields.append({
                "field": "deprecated",
                "before_value": before.deprecated,
                "after_value": after.deprecated,
                "change_type": "modified",
            })
            changed.append("deprecated")

        # ── Summary and identical flag ────────────────────────────────
        diff.is_identical = len(changed) == 0
        if diff.is_identical:
            diff.summary = f"{before.tool_name}: no changes"
        else:
            parts: List[str] = []
            if "affordance" in changed:
                b_aff = before.affordance.value
                a_aff = after.affordance.value
                esc = " ⚠ ESCALATION" if diff.affordance_escalated else ""
                parts.append(f"affordance {b_aff}→{a_aff}{esc}")
            if "tags" in changed:
                parts.append(
                    f"tags: -{len(removed_tags)}/+{len(added_tags)}"
                )
            if "domains" in changed:
                parts.append(
                    f"domains: -{len(removed_domains)}/+{len(added_domains)}"
                )
            if "example_queries" in changed:
                parts.append(
                    f"examples: -{len(removed_eqs)}/+{len(added_eqs)}"
                )
            if "conflicts_with" in changed:
                parts.append(
                    f"conflicts: -{len(removed_conflicts)}/+{len(added_conflicts)}"
                )
            if "conflict_note" in changed:
                parts.append("conflict_note updated")
            remaining = [
                c for c in changed
                if c not in {"affordance", "tags", "domains",
                             "example_queries", "conflicts_with", "conflict_note"}
            ]
            if remaining:
                parts.append(", ".join(remaining))
            diff.summary = f"{before.tool_name}: {'; '.join(parts)}"

        return diff

    async def analyze_impact(
        self,
        tool_name: str,
        proposed_manifest: ToolManifest,
        test_queries: Optional[List[str]] = None,
    ) -> ImpactReport:
        """Analyze the impact of changing one tool's manifest.

        Fetches the current manifest from the live index, computes the diff,
        simulates tool selection for test queries under both versions, then
        produces a full ImpactReport.

        Args:
            tool_name:         The tool whose manifest is being changed.
            proposed_manifest: The new (after) version of the manifest.
            test_queries:      Optional extra queries to test (beyond golden scenarios
                               and the tool's own example queries).

        Returns:
            Populated ImpactReport with diffs, per-query impacts, and risk assessment.
        """
        t0 = time.monotonic()

        current_manifest = self._base_index.get(tool_name)

        report = ImpactReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            tool_name=tool_name,
            analysis_mode="single_tool",
        )

        # ── 1. Diff ───────────────────────────────────────────────────
        if current_manifest is None:
            # New tool — treat as diff from empty manifest to proposed
            synthetic_before = _make_empty_manifest(tool_name, proposed_manifest.source)
            diff = self.diff_manifest(synthetic_before, proposed_manifest)
            diff.summary = f"{tool_name}: NEW TOOL (no previous manifest)"
        else:
            diff = self.diff_manifest(current_manifest, proposed_manifest)

        report.manifest_diffs = [diff]

        # ── 2. Build "after" index ────────────────────────────────────
        after_index = _clone_index_with_override(self._base_index, proposed_manifest)

        # ── 3. Gather test queries ────────────────────────────────────
        all_queries: List[Tuple[str, bool, str]] = []  # (query, is_golden, scenario_name)

        # a) Tool's own example queries (both before and after)
        own_queries: Set[str] = set()
        if current_manifest:
            own_queries.update(current_manifest.example_queries)
        own_queries.update(proposed_manifest.example_queries)
        for q in sorted(own_queries):
            all_queries.append((q, False, ""))

        # b) Caller-supplied test queries
        for q in (test_queries or []):
            if q not in own_queries:
                all_queries.append((q, False, ""))

        # c) Golden scenarios
        golden_scenarios = _try_load_all_scenarios()
        for scenario in golden_scenarios:
            for q in scenario.all_query_texts:
                all_queries.append((q, True, scenario.name))

        # Deduplicate while preserving first-seen metadata
        seen_queries: Set[str] = set()
        deduped: List[Tuple[str, bool, str]] = []
        for q, is_golden, sc_name in all_queries:
            if q not in seen_queries:
                seen_queries.add(q)
                deduped.append((q, is_golden, sc_name))
        all_queries = deduped

        # ── 4. Simulate tool selection under before/after ─────────────
        before_index = self._base_index
        query_impacts: List[QueryImpact] = []

        for query, is_golden, sc_name in all_queries:
            before_scored = await self._simulate_tool_selection_async(query, before_index)
            after_scored = await self._simulate_tool_selection_async(query, after_index)

            before_final = [s.tool_name for s in before_scored if s.in_final_set]
            after_final = [s.tool_name for s in after_scored if s.in_final_set]

            impact = _build_query_impact(
                query=query,
                before_tools=before_final,
                after_tools=after_final,
                is_golden=is_golden,
                scenario_name=sc_name,
                golden_scenarios=golden_scenarios,
            )
            query_impacts.append(impact)

        report.query_impacts = query_impacts

        # ── 5. Aggregate summary ──────────────────────────────────────
        _aggregate_summary(report)

        # ── 6. Assess overall risk ────────────────────────────────────
        _assess_overall_risk(report, diff)

        # ── 7. Extract regressions ────────────────────────────────────
        report.regressions = [
            {
                "query": qi.query,
                "tools_lost": qi.tools_lost,
                "scenario": qi.scenario_name,
                "risk_level": qi.risk_level,
                "risk_reasons": qi.risk_reasons,
            }
            for qi in query_impacts
            if qi.regression
        ]

        # ── 8. Build checklist and recommendations ────────────────────
        report.validation_checklist = _build_validation_checklist(report, diff)
        report.recommendations = _build_recommendations(report, diff)

        report.duration_ms = (time.monotonic() - t0) * 1000
        return report

    async def analyze_manifest_file_change(
        self,
        before_path: str,
        after_path: str,
    ) -> ImpactReport:
        """Compare two manifest JSON files and produce an impact report.

        The JSON files should each contain an array of tool manifest objects
        matching the ToolManifest field names (with string values for FrozenSets
        expressed as lists).

        Args:
            before_path: Path to the "before" manifest JSON file.
            after_path:  Path to the "after" manifest JSON file.

        Returns:
            ImpactReport for all tools that differ between the two files.
        """
        t0 = time.monotonic()

        before_manifests = _load_manifests_from_file(before_path)
        after_manifests = _load_manifests_from_file(after_path)

        before_by_name = {m.tool_name: m for m in before_manifests}
        after_by_name = {m.tool_name: m for m in after_manifests}

        all_tool_names = set(before_by_name) | set(after_by_name)

        report = ImpactReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            analysis_mode="file_compare",
        )

        diffs: List[ManifestDiff] = []
        sub_reports: List[ImpactReport] = []

        for name in sorted(all_tool_names):
            before_m = before_by_name.get(name)
            after_m = after_by_name.get(name)

            if before_m is None and after_m is not None:
                # New tool added
                empty = _make_empty_manifest(name, after_m.source)
                diff = self.diff_manifest(empty, after_m)
                diff.summary = f"{name}: NEW TOOL"
                diffs.append(diff)
                sub = await self.analyze_impact(name, after_m)
                sub_reports.append(sub)

            elif before_m is not None and after_m is None:
                # Tool removed
                empty = _make_empty_manifest(name, before_m.source)
                diff = self.diff_manifest(before_m, empty)
                diff.summary = f"{name}: TOOL REMOVED"
                diffs.append(diff)

            elif before_m is not None and after_m is not None:
                diff = self.diff_manifest(before_m, after_m)
                diffs.append(diff)
                if not diff.is_identical:
                    sub = await self.analyze_impact(name, after_m)
                    sub_reports.append(sub)

        # Merge sub-reports
        report.manifest_diffs = diffs

        all_impacts: List[QueryImpact] = []
        seen_qi: Set[str] = set()
        for sub in sub_reports:
            for qi in sub.query_impacts:
                key = qi.query
                if key not in seen_qi:
                    seen_qi.add(key)
                    all_impacts.append(qi)

        report.query_impacts = all_impacts
        _aggregate_summary(report)

        # Synthetic diff for overall risk (use the most severe individual diff)
        if diffs:
            most_severe = max(
                diffs,
                key=lambda d: (
                    d.affordance_escalated,
                    len(d.domains_removed),
                    len(d.tags_removed),
                ),
            )
            _assess_overall_risk(report, most_severe)
        else:
            report.risk_assessment = "none"
            report.risk_summary = "No manifest changes detected."

        report.regressions = [
            {
                "query": qi.query,
                "tools_lost": qi.tools_lost,
                "scenario": qi.scenario_name,
                "risk_level": qi.risk_level,
                "risk_reasons": qi.risk_reasons,
            }
            for qi in report.query_impacts
            if qi.regression
        ]
        report.validation_checklist = _build_validation_checklist(report, diffs[0] if diffs else None)
        report.recommendations = _build_recommendations(report, diffs[0] if diffs else None)

        report.duration_ms = (time.monotonic() - t0) * 1000
        return report

    async def analyze_all_manifests_against_scenarios(self) -> ImpactReport:
        """Baseline check: run all golden scenarios against the current manifest index.

        This is the "no-change" baseline — before and after are identical
        (current index vs. itself).  Any failures reveal existing regressions
        in the current manifest state rather than changes caused by a specific edit.

        Returns:
            ImpactReport in "baseline" mode.  Regressions indicate scenarios that
            are already failing before any changes are applied.
        """
        t0 = time.monotonic()

        report = ImpactReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            analysis_mode="baseline",
        )

        golden_scenarios = _try_load_all_scenarios()
        if not golden_scenarios:
            report.risk_assessment = "none"
            report.risk_summary = "No golden scenarios found — baseline check skipped."
            report.recommendations = [
                "Add golden scenarios to tests/scenarios/*.yaml to enable baseline checks.",
            ]
            report.duration_ms = (time.monotonic() - t0) * 1000
            return report

        index = self._base_index
        query_impacts: List[QueryImpact] = []

        for scenario in golden_scenarios:
            for q in scenario.all_query_texts:
                scored = await self._simulate_tool_selection_async(q, index)
                final_tools = [s.tool_name for s in scored if s.in_final_set]

                # Evaluate against scenario contract
                required = list(scenario.expected_contract.tools_required)
                excluded = list(scenario.expected_contract.tools_excluded)
                final_set = set(final_tools)

                missing = [t for t in required if t not in final_set]
                unexpected = [t for t in excluded if t in final_set]

                regression = bool(missing or unexpected)
                risk_reasons: List[str] = []

                if missing:
                    risk_reasons.append(f"Missing required: {missing}")
                if unexpected:
                    risk_reasons.append(f"Unexpected excluded tools selected: {unexpected}")

                risk_level = "high" if regression else "none"

                qi = QueryImpact(
                    query=q,
                    before_tools=final_tools,    # baseline: before == after
                    after_tools=final_tools,
                    regression=regression,
                    risk_level=risk_level,
                    risk_reasons=risk_reasons,
                    from_golden_scenario=True,
                    scenario_name=scenario.name,
                )
                query_impacts.append(qi)

        report.query_impacts = query_impacts
        _aggregate_summary(report)

        has_regression = any(qi.regression for qi in query_impacts)
        report.risk_assessment = "high" if has_regression else "none"
        report.risk_summary = (
            f"{report.queries_with_regressions} scenario regression(s) detected in current manifests."
            if has_regression
            else f"All {len(golden_scenarios)} golden scenarios pass with current manifests."
        )

        report.regressions = [
            {
                "query": qi.query,
                "tools_lost": [],
                "scenario": qi.scenario_name,
                "risk_level": qi.risk_level,
                "risk_reasons": qi.risk_reasons,
            }
            for qi in query_impacts
            if qi.regression
        ]

        report.validation_checklist = [
            "Review failing scenarios and identify which manifest changes broke them.",
            "Run `python -m utils.tool_selection_reporter --all-scenarios` for per-query traces.",
            "Cross-check against the scenario YAML contracts in tests/scenarios/.",
            "Fix regressions before merging any manifest changes.",
        ]
        report.recommendations = _build_baseline_recommendations(report)
        report.duration_ms = (time.monotonic() - t0) * 1000
        return report

    def _simulate_tool_selection(
        self,
        query: str,
        manifest_index: ToolManifestIndex,
        classification: Optional[DomainClassification] = None,
    ) -> List[ScoredTool]:
        """Offline keyword-based tool selection simulation (synchronous).

        Mirrors the logic in ToolSelectionReporter._score_tools() and
        _apply_filters_and_guardrails() exactly so that before/after comparisons
        reflect the same algorithm used in production.

        Args:
            query:          Natural-language query.
            manifest_index: The manifest index to score against.
            classification: Pre-computed domain classification (optional; if
                            omitted a synchronous fallback classifies against
                            all sources in the general domain).

        Returns:
            List of ScoredTool, with in_final_set and rank populated.
        """
        tokens = _extract_tokens(query)

        # Determine query intent flags
        is_read = bool(_READ_INTENT_RE.match(query.strip()))
        has_list_verb = bool(re.search(
            r"\b(show|list|get|display|enumerate|what\s+are)\b", query, re.I
        ))
        has_ca = bool(re.search(
            r"\bcontainer\s*apps?\b|\bcontainerapps?\b", query, re.I
        ))
        has_health = bool(re.search(
            r"\b(health|healthy|status|degraded|unhealthy|availability)\b", query, re.I
        ))
        is_ca_list = has_list_verb and has_ca
        is_ca_health = has_ca and has_health

        # Determine sources to query
        if classification is not None:
            primary_domain = classification.primary_domain.value
            secondary_domains = [d.value for d in classification.secondary_domains]
        else:
            # Synchronous fallback: use all sources
            primary_domain = "general"
            secondary_domains = []

        # Legacy sources from QueryPatterns
        legacy_sources: Set[str] = set()
        try:
            legacy = QueryPatterns.classify_domains(query)
            active_domains = [d for d, v in legacy.items() if v]
            for d in active_domains:
                for src in QueryPatterns.DOMAIN_SOURCE_MAP.get(d, []):
                    legacy_sources.add(src)
        except Exception:
            pass

        sources = _get_sources_for_query(primary_domain, secondary_domains, list(legacy_sources))

        # Score all tools in matching sources
        all_scored: List[ScoredTool] = []
        for name in manifest_index.all_tool_names():
            manifest = manifest_index.get(name)
            if manifest is None or manifest.deprecated:
                continue
            if manifest.source not in sources:
                continue

            ks, _ = _keyword_score(tokens, name)
            ts = _tag_score(tokens, manifest.tags)
            es = _example_query_score(tokens, manifest.example_queries)
            total = ks + ts + es

            all_scored.append(ScoredTool(
                tool_name=name,
                source=manifest.source,
                total_score=total,
            ))

        all_scored.sort(key=lambda e: e.total_score, reverse=True)
        ranked = all_scored[:_DEFAULT_TOP_K]
        ranked_set: Set[str] = {e.tool_name for e in ranked}

        # ── Read-intent filter ─────────────────────────────────────────
        preserve: Set[str] = set()
        if is_ca_health:
            preserve.add(_CONTAINER_APP_HEALTH_TOOL)

        if is_read:
            filtered: List[ScoredTool] = []
            for e in ranked:
                if _is_action_tool(e.tool_name) and e.tool_name not in preserve:
                    e.excluded = True
                    e.exclusion_reason = "read_intent_action_removal"
                    ranked_set.discard(e.tool_name)
                else:
                    filtered.append(e)
            ranked = filtered
            ranked_set = {e.tool_name for e in ranked}

        # ── CLI fallback guardrail ─────────────────────────────────────
        if _CLI_FALLBACK_TOOL not in ranked_set:
            cli_m = manifest_index.get(_CLI_FALLBACK_TOOL)
            if cli_m and cli_m.source in sources:
                cli_entry = ScoredTool(
                    tool_name=_CLI_FALLBACK_TOOL,
                    source=cli_m.source,
                    total_score=0.0,
                )
                ranked.append(cli_entry)
                ranked_set.add(_CLI_FALLBACK_TOOL)

        # ── Container app list guardrail ───────────────────────────────
        if is_ca_list and _CONTAINER_APP_LIST_TOOL not in ranked_set:
            ca_m = manifest_index.get(_CONTAINER_APP_LIST_TOOL)
            if ca_m:
                if len(ranked) >= _DEFAULT_TOP_K:
                    evicted = ranked.pop()
                    ranked_set.discard(evicted.tool_name)
                ca_entry = ScoredTool(
                    tool_name=_CONTAINER_APP_LIST_TOOL,
                    source=ca_m.source,
                    total_score=0.0,
                )
                ranked.append(ca_entry)
                ranked_set.add(_CONTAINER_APP_LIST_TOOL)

        # ── Container app health guardrail ─────────────────────────────
        if is_ca_health and _CONTAINER_APP_HEALTH_TOOL not in ranked_set:
            ch_m = manifest_index.get(_CONTAINER_APP_HEALTH_TOOL)
            if ch_m:
                if len(ranked) >= _DEFAULT_TOP_K:
                    evicted = ranked.pop()
                    ranked_set.discard(evicted.tool_name)
                ch_entry = ScoredTool(
                    tool_name=_CONTAINER_APP_HEALTH_TOOL,
                    source=ch_m.source,
                    total_score=0.0,
                )
                ranked.append(ch_entry)
                ranked_set.add(_CONTAINER_APP_HEALTH_TOOL)

        # ── Mark final-set membership and ranks ────────────────────────
        for i, e in enumerate(ranked, 1):
            e.in_final_set = True
            e.rank = i

        # Also mark scored-but-not-final entries
        final_names = {e.tool_name for e in ranked}
        for e in all_scored:
            if e.tool_name not in final_names and not e.excluded:
                e.in_final_set = False
                e.rank = 0

        return all_scored + [e for e in ranked if e.tool_name not in {s.tool_name for s in all_scored}]

    async def _simulate_tool_selection_async(
        self,
        query: str,
        manifest_index: ToolManifestIndex,
    ) -> List[ScoredTool]:
        """Async wrapper for _simulate_tool_selection with domain classification."""
        try:
            classification = await self._classifier.classify(query)
        except Exception:
            classification = None
        return self._simulate_tool_selection(query, manifest_index, classification)


# ---------------------------------------------------------------------------
# Private helper functions
# ---------------------------------------------------------------------------

def _make_empty_manifest(tool_name: str, source: str) -> ToolManifest:
    """Create a blank manifest stub representing 'tool did not exist'."""
    return ToolManifest(
        tool_name=tool_name,
        source=source,
        domains=frozenset(),
        tags=frozenset(),
        affordance=ToolAffordance.READ,
        example_queries=(),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    )


def _clone_index_with_override(
    base: ToolManifestIndex,
    override: ToolManifest,
) -> ToolManifestIndex:
    """Return a new ToolManifestIndex with one manifest replaced/added."""
    new_index = ToolManifestIndex()
    for name in base.all_tool_names():
        m = base.get(name)
        if m is not None and m.tool_name != override.tool_name:
            new_index.register(m)
    new_index.register(override)
    return new_index


def _build_query_impact(
    query: str,
    before_tools: List[str],
    after_tools: List[str],
    is_golden: bool,
    scenario_name: str,
    golden_scenarios: List[Any],
) -> QueryImpact:
    """Compute a QueryImpact from before/after tool lists."""
    before_set = set(before_tools)
    after_set = set(after_tools)

    tools_gained = [t for t in after_tools if t not in before_set]
    tools_lost = [t for t in before_tools if t not in after_set]

    # Rank changes (for tools present in both)
    before_rank_map = {t: i + 1 for i, t in enumerate(before_tools)}
    after_rank_map = {t: i + 1 for i, t in enumerate(after_tools)}

    rank_changes: List[RankChange] = []
    for tool in set(before_tools) | set(after_tools):
        br = before_rank_map.get(tool, 0)
        ar = after_rank_map.get(tool, 0)
        if br != ar:
            rank_changes.append(RankChange(tool_name=tool, before_rank=br, after_rank=ar))
    rank_changes.sort(key=lambda rc: abs(rc.delta), reverse=True)

    # Regression: check golden scenario contracts
    regression = False
    risk_reasons: List[str] = []

    if is_golden and golden_scenarios:
        for scenario in golden_scenarios:
            if scenario.name != scenario_name and query not in scenario.all_query_texts:
                continue
            required = list(scenario.expected_contract.tools_required)
            excluded = list(scenario.expected_contract.tools_excluded)
            missing = [t for t in required if t not in after_set]
            unexpected = [t for t in excluded if t in after_set]
            if missing:
                regression = True
                risk_reasons.append(f"[{scenario_name}] Missing required tools: {missing}")
            if unexpected:
                regression = True
                risk_reasons.append(
                    f"[{scenario_name}] Excluded tools selected: {unexpected}"
                )

    # Risk classification
    risk_level = "none"
    if regression:
        risk_level = "high"
        if not risk_reasons:
            risk_reasons.append("Golden scenario contract violated")
    elif tools_lost:
        # Losing tools from the selection is at least medium risk
        risk_level = "medium"
        risk_reasons.append(f"Tools dropped from selection: {tools_lost}")
    elif tools_gained:
        risk_level = "low"
        risk_reasons.append(f"Tools added to selection: {tools_gained}")
    elif rank_changes:
        # Check for significant rank shifts (>3 positions)
        large_shifts = [rc for rc in rank_changes if abs(rc.delta) > 3]
        if large_shifts:
            risk_level = "medium"
            risk_reasons.append(
                f"Significant rank shifts: "
                + ", ".join(f"{rc.tool_name} ({rc.label})" for rc in large_shifts)
            )
        else:
            risk_level = "low"
            risk_reasons.append(
                "Minor rank changes: "
                + ", ".join(f"{rc.tool_name} ({rc.label})" for rc in rank_changes[:3])
            )

    return QueryImpact(
        query=query,
        before_tools=before_tools,
        after_tools=after_tools,
        tools_gained=tools_gained,
        tools_lost=tools_lost,
        rank_changes=rank_changes,
        regression=regression,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        from_golden_scenario=is_golden,
        scenario_name=scenario_name,
    )


def _aggregate_summary(report: ImpactReport) -> None:
    """Populate report summary counters from query_impacts."""
    report.total_queries_tested = len(report.query_impacts)
    report.queries_affected = sum(
        1 for qi in report.query_impacts
        if qi.tools_gained or qi.tools_lost or qi.rank_changes
    )
    report.queries_with_regressions = sum(
        1 for qi in report.query_impacts if qi.regression
    )
    report.queries_with_gains = sum(
        1 for qi in report.query_impacts if qi.tools_gained and not qi.regression
    )


def _assess_overall_risk(report: ImpactReport, diff: Optional[ManifestDiff]) -> None:
    """Compute report.risk_assessment and report.risk_summary."""
    reasons: List[str] = []

    # High: any regression
    if report.queries_with_regressions > 0:
        report.risk_assessment = "high"
        reasons.append(
            f"{report.queries_with_regressions} query regression(s) detected"
        )

    # High: affordance escalation toward DESTRUCTIVE
    if diff and diff.affordance_escalated:
        report.risk_assessment = "high"
        aff_change = next(
            (f["after_value"] for f in diff.changed_fields if f["field"] == "affordance"),
            "DESTRUCTIVE",
        )
        reasons.append(f"Affordance escalated to {aff_change}")

    # Medium: domains removed (tool may become invisible for certain queries)
    if diff and diff.domains_removed:
        if report.risk_assessment not in ("high",):
            report.risk_assessment = "medium"
        reasons.append(f"Domains removed: {diff.domains_removed}")

    # Medium: significant rank shifts
    medium_impacts = [
        qi for qi in report.query_impacts if qi.risk_level == "medium"
    ]
    if medium_impacts and report.risk_assessment not in ("high",):
        report.risk_assessment = "medium"
        reasons.append(f"{len(medium_impacts)} query impact(s) at medium risk")

    # Low: only minor changes
    low_impacts = [qi for qi in report.query_impacts if qi.risk_level == "low"]
    if low_impacts and report.risk_assessment == "none":
        report.risk_assessment = "low"
        reasons.append(f"{len(low_impacts)} query impact(s) at low risk")

    if not report.risk_assessment or report.risk_assessment == "none":
        report.risk_assessment = "none"
        report.risk_summary = "No observable impact on tool selection."
    else:
        report.risk_summary = "; ".join(reasons)


def _build_validation_checklist(
    report: ImpactReport,
    diff: Optional[ManifestDiff],
) -> List[str]:
    """Generate a validation checklist based on detected changes."""
    checklist: List[str] = []

    checklist.append(
        "Run `python -m utils.manifest_quality_analyzer` to confirm the change "
        "does not drop the overall quality score below target."
    )

    if diff and not diff.is_identical:
        checklist.append(
            "Run `python -m utils.tool_selection_reporter --all-scenarios` and "
            "verify all scenario contracts still pass."
        )

    if diff and diff.affordance_escalated:
        checklist.append(
            "⚠ Affordance escalated — confirm `requires_confirmation=True` is set "
            "on the updated manifest."
        )
        checklist.append(
            "⚠ Notify stakeholders: this tool now requires explicit user confirmation "
            "before execution."
        )

    if diff and diff.domains_removed:
        checklist.append(
            f"Verify that removing domains {diff.domains_removed} is intentional. "
            "Queries in those domains will no longer see this tool."
        )

    if diff and diff.tags_removed:
        checklist.append(
            f"Verify that removing tags {diff.tags_removed} is intentional. "
            "Test keyword-scoring for queries that used those tags."
        )

    if diff and diff.example_queries_removed:
        checklist.append(
            f"Test the {len(diff.example_queries_removed)} removed example query/queries "
            "to confirm the tool is still selected correctly without them."
        )

    if report.queries_with_regressions > 0:
        checklist.append(
            f"🚨 Fix {report.queries_with_regressions} regression(s) before merging. "
            "See the Regressions Detected section for details."
        )

    checklist.append(
        "Deploy to a staging environment and run "
        "`./run_tests.sh` to confirm no integration test failures."
    )

    return checklist


def _build_recommendations(
    report: ImpactReport,
    diff: Optional[ManifestDiff],
) -> List[str]:
    """Generate actionable recommendations from the analysis."""
    recs: List[str] = []

    if report.queries_with_regressions > 0:
        recs.append(
            f"BLOCK MERGE: {report.queries_with_regressions} golden scenario regression(s) detected. "
            "Revise the change until all regressions are resolved."
        )

    if diff and diff.affordance_escalated:
        recs.append(
            "Set `requires_confirmation=True` on the updated manifest since the affordance "
            "now requires explicit user approval before execution."
        )

    if diff and diff.tags_removed:
        recs.append(
            f"Before removing tags {diff.tags_removed}, add equivalent example queries "
            "covering the same semantic surface to compensate for reduced tag matching."
        )

    if diff and diff.domains_removed:
        recs.append(
            f"Removing domain(s) {diff.domains_removed} will hide this tool from queries "
            "in those domains. Add specific example queries covering that domain's "
            "canonical phrasings to ensure the tool is still surfaced via scoring."
        )

    if diff and diff.example_queries_removed:
        recs.append(
            f"Removing {len(diff.example_queries_removed)} example query/queries reduces "
            "the tool's example-query score. Offset this by either keeping them or adding "
            "higher-quality replacements."
        )

    if diff and diff.conflicts_added:
        recs.append(
            f"New conflicts declared with {diff.conflicts_added}. Add or update "
            "`conflict_note` to explain disambiguation to the LLM planner."
        )

    # Positive: safe changes
    if (report.risk_assessment in ("none", "low") and
            report.queries_with_regressions == 0):
        recs.append(
            "Change appears safe to merge. No regressions detected and risk is "
            f"'{report.risk_assessment}'. Standard code review is sufficient."
        )

    return recs


def _build_baseline_recommendations(report: ImpactReport) -> List[str]:
    """Generate recommendations for baseline (no-change) analysis."""
    recs: List[str] = []

    if report.queries_with_regressions > 0:
        failing_scenarios = sorted({qi.scenario_name for qi in report.query_impacts if qi.regression})
        recs.append(
            f"Fix existing regressions in {len(failing_scenarios)} scenario(s) before making "
            f"any manifest changes: {', '.join(failing_scenarios)}"
        )
        recs.append(
            "Run `python -m utils.tool_selection_reporter --all-scenarios` for per-query traces "
            "on each failing scenario."
        )
        recs.append(
            "Check manifest example_queries and tags for tools in the `tools_required` contracts "
            "of failing scenarios."
        )
    else:
        recs.append(
            "All golden scenarios pass. The manifest index is in a healthy baseline state."
        )
        recs.append(
            "Consider adding more golden scenarios to increase regression coverage before "
            "authoring manifest changes."
        )

    return recs


# ---------------------------------------------------------------------------
# Golden scenario loader (lazy import — optional dependency on tests/ package)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JSON manifest file I/O
# ---------------------------------------------------------------------------

def _load_manifests_from_file(path: str) -> List[ToolManifest]:
    """Load a list of ToolManifest objects from a JSON file.

    The JSON file should be either:
    - An array of manifest objects, OR
    - An object with a "manifests" key containing the array.

    Each manifest object uses the ToolManifest field names.  Set-typed fields
    (domains, tags, conflicts_with, preferred_over) may be JSON arrays.
    The example_queries field should be a JSON array of strings.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    raw = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(raw, dict) and "manifests" in raw:
        raw = raw["manifests"]

    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array of manifest objects in {path}")

    manifests: List[ToolManifest] = []
    for obj in raw:
        try:
            manifests.append(_dict_to_manifest(obj))
        except Exception as exc:
            tool = obj.get("tool_name", "<unknown>")
            raise ValueError(f"Error loading manifest for '{tool}': {exc}") from exc

    return manifests


def _dict_to_manifest(obj: Dict[str, Any]) -> ToolManifest:
    """Convert a plain dict (from JSON) to a ToolManifest dataclass."""
    affordance_str = obj.get("affordance", "read")
    try:
        affordance = ToolAffordance(affordance_str)
    except ValueError:
        affordance = ToolAffordance.READ

    return ToolManifest(
        tool_name=obj["tool_name"],
        source=obj.get("source", ""),
        domains=frozenset(obj.get("domains", [])),
        tags=frozenset(obj.get("tags", [])),
        affordance=affordance,
        example_queries=tuple(obj.get("example_queries", [])),
        conflicts_with=frozenset(obj.get("conflicts_with", [])),
        conflict_note=obj.get("conflict_note", ""),
        preferred_over=frozenset(obj.get("preferred_over", [])),
        requires_confirmation=bool(obj.get("requires_confirmation", False)),
        deprecated=bool(obj.get("deprecated", False)),
        output_schema=obj.get("output_schema", {}),
    )


def _manifest_to_dict(m: ToolManifest) -> Dict[str, Any]:
    """Convert a ToolManifest to a JSON-serialisable dict."""
    return {
        "tool_name": m.tool_name,
        "source": m.source,
        "domains": sorted(m.domains),
        "tags": sorted(m.tags),
        "affordance": m.affordance.value,
        "example_queries": list(m.example_queries),
        "conflicts_with": sorted(m.conflicts_with),
        "conflict_note": m.conflict_note,
        "preferred_over": sorted(m.preferred_over),
        "requires_confirmation": m.requires_confirmation,
        "deprecated": m.deprecated,
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_json(report: ImpactReport) -> str:
    """Render the impact report as pretty-printed JSON."""
    return json.dumps(report.to_dict(), indent=2, default=str)


def format_markdown(report: ImpactReport) -> str:
    """Render the impact report as human-readable Markdown.

    Sections:
        1. Summary
        2. Manifest Diff Details
        3. Query Impact Analysis
        4. Regressions Detected
        5. Risk Assessment
        6. Validation Checklist
        7. Recommendations
    """
    lines: List[str] = []

    # ── Header ────────────────────────────────────────────────────────
    lines.append("# Manifest Change Impact Report")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    if report.tool_name:
        lines.append(f"**Tool Under Analysis:** `{report.tool_name}`")
    lines.append(f"**Analysis Mode:** {report.analysis_mode}")
    lines.append(f"**Duration:** {report.duration_ms:.1f}ms")
    lines.append("")

    # ── 1. Summary ────────────────────────────────────────────────────
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "✅"}.get(
        report.risk_assessment, "•"
    )
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Overall Risk | {risk_emoji} **{report.risk_assessment.upper()}** |")
    lines.append(f"| Queries Tested | {report.total_queries_tested} |")
    lines.append(f"| Queries Affected | {report.queries_affected} |")
    lines.append(f"| Regressions | {report.queries_with_regressions} |")
    lines.append(f"| Queries with Gains | {report.queries_with_gains} |")
    lines.append(f"| Manifest Diffs | {len(report.manifest_diffs)} |")
    lines.append("")
    if report.risk_summary:
        lines.append(f"**Risk Summary:** {report.risk_summary}")
        lines.append("")

    # ── 2. Manifest Diff Details ──────────────────────────────────────
    lines.append("## 2. Manifest Diff Details")
    lines.append("")
    if not report.manifest_diffs:
        lines.append("_No manifest changes detected._")
        lines.append("")
    else:
        for diff in report.manifest_diffs:
            if diff.is_identical:
                lines.append(f"### `{diff.tool_name}` — No Changes")
                lines.append("")
                continue

            esc_note = " 🚨 AFFORDANCE ESCALATION" if diff.affordance_escalated else ""
            lines.append(f"### `{diff.tool_name}`{esc_note}")
            lines.append("")
            lines.append(f"**Summary:** {diff.summary}")
            lines.append("")

            if diff.changed_fields:
                lines.append("| Field | Before | After | Change |")
                lines.append("|-------|--------|-------|--------|")
                for cf in diff.changed_fields:
                    before_val = _truncate(str(cf.get("before_value", "")), 60)
                    after_val = _truncate(str(cf.get("after_value", "")), 60)
                    change_type = cf.get("change_type", "modified")
                    lines.append(
                        f"| `{cf['field']}` | {before_val} | {after_val} | {change_type} |"
                    )
                lines.append("")

    # ── 3. Query Impact Analysis ──────────────────────────────────────
    lines.append("## 3. Query Impact Analysis")
    lines.append("")
    affected = [qi for qi in report.query_impacts if qi.risk_level != "none"]
    unaffected = [qi for qi in report.query_impacts if qi.risk_level == "none"]

    if not affected:
        lines.append(
            f"_No query impacts detected across {report.total_queries_tested} tested queries._"
        )
        lines.append("")
    else:
        lines.append(
            f"**{len(affected)} of {report.total_queries_tested} queries impacted** "
            f"({len(unaffected)} unaffected)."
        )
        lines.append("")
        lines.append("| Risk | Query | Tools Lost | Tools Gained | Regression |")
        lines.append("|------|-------|-----------|--------------|------------|")
        for qi in sorted(affected, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.risk_level, 3)):
            risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(qi.risk_level, "•")
            lost_str = ", ".join(f"`{t}`" for t in qi.tools_lost) if qi.tools_lost else "—"
            gained_str = ", ".join(f"`{t}`" for t in qi.tools_gained) if qi.tools_gained else "—"
            regression_str = "**Yes** 🚨" if qi.regression else "No"
            q_short = _truncate(qi.query, 55)
            lines.append(
                f"| {risk_icon} {qi.risk_level} | {q_short} "
                f"| {lost_str} | {gained_str} | {regression_str} |"
            )
        lines.append("")

        # Detail section for high-risk impacts
        high_impacts = [qi for qi in affected if qi.risk_level == "high"]
        if high_impacts:
            lines.append("### High-Risk Query Details")
            lines.append("")
            for qi in high_impacts:
                lines.append(f"**Query:** `{qi.query}`")
                if qi.scenario_name:
                    lines.append(f"**Scenario:** `{qi.scenario_name}`")
                if qi.tools_lost:
                    lines.append(f"**Tools Lost:** {', '.join(f'`{t}`' for t in qi.tools_lost)}")
                if qi.tools_gained:
                    lines.append(f"**Tools Gained:** {', '.join(f'`{t}`' for t in qi.tools_gained)}")
                if qi.risk_reasons:
                    lines.append("**Reasons:**")
                    for r in qi.risk_reasons:
                        lines.append(f"  - {r}")
                lines.append("")

    # ── 4. Regressions Detected ───────────────────────────────────────
    lines.append("## 4. Regressions Detected")
    lines.append("")
    if not report.regressions:
        lines.append("_No regressions detected. All golden scenario contracts satisfied._")
        lines.append("")
    else:
        lines.append(f"**{len(report.regressions)} regression(s) detected:**")
        lines.append("")
        for reg in report.regressions:
            lines.append(f"- **Query:** `{reg['query']}`")
            if reg.get("scenario"):
                lines.append(f"  - **Scenario:** `{reg['scenario']}`")
            if reg.get("tools_lost"):
                lines.append(f"  - **Tools Lost:** {', '.join(f'`{t}`' for t in reg['tools_lost'])}")
            if reg.get("risk_reasons"):
                for reason in reg["risk_reasons"]:
                    lines.append(f"  - {reason}")
        lines.append("")

    # ── 5. Risk Assessment ────────────────────────────────────────────
    lines.append("## 5. Risk Assessment")
    lines.append("")
    risk_desc = {
        "high": (
            "🔴 **HIGH** — Required tools are lost from golden scenario selections, "
            "or the affordance escalated toward DESTRUCTIVE. **Do not merge without fixing regressions.**"
        ),
        "medium": (
            "🟡 **MEDIUM** — Tool ranks shifted significantly, domains were removed, or tools "
            "dropped from selection without golden scenario coverage. Review carefully."
        ),
        "low": (
            "🟢 **LOW** — Minor changes with limited query impact. "
            "Standard code review and testing is sufficient."
        ),
        "none": (
            "✅ **NONE** — No observable impact on tool selection for any tested query. "
            "Change is safe to proceed."
        ),
    }
    lines.append(risk_desc.get(report.risk_assessment, f"**{report.risk_assessment.upper()}**"))
    lines.append("")
    if report.risk_summary:
        lines.append(f"**Detail:** {report.risk_summary}")
        lines.append("")

    # Per-query risk breakdown
    risk_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for qi in report.query_impacts:
        risk_counts[qi.risk_level] = risk_counts.get(qi.risk_level, 0) + 1
    lines.append("| Risk Level | Query Count |")
    lines.append("|-----------|-------------|")
    for level in ("high", "medium", "low", "none"):
        lines.append(f"| {level} | {risk_counts.get(level, 0)} |")
    lines.append("")

    # ── 6. Validation Checklist ───────────────────────────────────────
    lines.append("## 6. Validation Checklist")
    lines.append("")
    if report.validation_checklist:
        for item in report.validation_checklist:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("_No specific validation steps required._")
    lines.append("")

    # ── 7. Recommendations ────────────────────────────────────────────
    lines.append("## 7. Recommendations")
    lines.append("")
    if report.recommendations:
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append("_No recommendations — change appears safe._")
    lines.append("")

    return "\n".join(lines)


def format_html(report: ImpactReport) -> str:
    """Render the impact report as a styled standalone HTML page."""
    lines: List[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html lang='en'><head>")
    lines.append("<meta charset='utf-8'>")
    tool_label = _html_escape(report.tool_name or report.analysis_mode)
    lines.append(f"<title>Manifest Impact Report – {tool_label}</title>")
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
        .risk-high        { background: #fee2e2; color: #991b1b; }
        .risk-medium      { background: #fef3c7; color: #92400e; }
        .risk-low         { background: #d1fae5; color: #065f46; }
        .risk-none        { background: #f3f4f6; color: #374151; }
        .regression-yes   { color: #dc2626; font-weight: bold; }
        .regression-no    { color: #6b7280; }
        .alert-high   { background: #fee2e2; border-left: 4px solid #dc2626;
                        padding: 12px 16px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .alert-medium { background: #fef3c7; border-left: 4px solid #f59e0b;
                        padding: 12px 16px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .alert-low    { background: #d1fae5; border-left: 4px solid #10b981;
                        padding: 12px 16px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .alert-none   { background: #f3f4f6; border-left: 4px solid #9ca3af;
                        padding: 12px 16px; margin: 8px 0; border-radius: 0 6px 6px 0; }
        .checklist li { list-style: none; padding-left: 0; margin: 0.4em 0; }
        .checklist li::before { content: '☐  '; color: #6b7280; }
        ul, ol { padding-left: 1.5em; }
        li { margin: 0.25em 0; }
        .diff-table td:first-child { font-family: 'SF Mono', Consolas, monospace;
                                      font-size: 0.85em; }
        .esc-warn { color: #dc2626; font-weight: bold; font-size: 0.9em; }
    """))
    lines.append("</style></head><body>")

    # ── Header ────────────────────────────────────────────────────────
    lines.append("<h1>Manifest Change Impact Report</h1>")
    lines.append(
        f"<p class='meta'>"
        f"<strong>Generated:</strong> {_html_escape(report.generated_at)} &nbsp;|&nbsp; "
        f"<strong>Mode:</strong> {_html_escape(report.analysis_mode)} &nbsp;|&nbsp; "
        f"<strong>Duration:</strong> {report.duration_ms:.1f}ms"
        f"</p>"
    )
    if report.tool_name:
        lines.append(f"<p><strong>Tool:</strong> <code>{_html_escape(report.tool_name)}</code></p>")

    # ── 1. Summary ────────────────────────────────────────────────────
    risk_class = f"risk-{report.risk_assessment}"
    lines.append("<h2>1. Summary</h2>")
    lines.append(
        f"<div class='alert-{report.risk_assessment}'>"
        f"<strong>Overall Risk: <span class='{risk_class}'>"
        f"{report.risk_assessment.upper()}</span></strong>"
    )
    if report.risk_summary:
        lines.append(f"<br><em>{_html_escape(report.risk_summary)}</em>")
    lines.append("</div>")

    lines.append("<table class='prop-table'>")
    lines.append("<tr><th>Metric</th><th>Value</th></tr>")
    _html_row(lines, "Queries Tested", str(report.total_queries_tested))
    _html_row(lines, "Queries Affected", str(report.queries_affected))
    _html_row(
        lines, "Regressions",
        f"<span class='{'regression-yes' if report.queries_with_regressions else 'regression-no'}'>"
        f"{report.queries_with_regressions}</span>"
    )
    _html_row(lines, "Queries with Gains", str(report.queries_with_gains))
    _html_row(lines, "Manifest Diffs", str(len(report.manifest_diffs)))
    lines.append("</table>")

    # ── 2. Manifest Diff Details ──────────────────────────────────────
    lines.append("<h2>2. Manifest Diff Details</h2>")
    if not report.manifest_diffs:
        lines.append("<p><em>No manifest changes detected.</em></p>")
    else:
        for diff in report.manifest_diffs:
            if diff.is_identical:
                lines.append(
                    f"<h3><code>{_html_escape(diff.tool_name)}</code> — No Changes</h3>"
                )
                continue

            esc = (" &nbsp;<span class='esc-warn'>⚠ AFFORDANCE ESCALATION</span>"
                   if diff.affordance_escalated else "")
            lines.append(f"<h3><code>{_html_escape(diff.tool_name)}</code>{esc}</h3>")
            lines.append(f"<p><strong>Summary:</strong> {_html_escape(diff.summary)}</p>")

            if diff.changed_fields:
                lines.append(
                    "<table class='diff-table'>"
                    "<tr><th>Field</th><th>Before</th><th>After</th><th>Change</th></tr>"
                )
                for cf in diff.changed_fields:
                    bv = _html_escape(_truncate(str(cf.get("before_value", "")), 80))
                    av = _html_escape(_truncate(str(cf.get("after_value", "")), 80))
                    ct = cf.get("change_type", "modified")
                    lines.append(
                        f"<tr><td><code>{_html_escape(cf['field'])}</code></td>"
                        f"<td>{bv}</td><td>{av}</td><td>{ct}</td></tr>"
                    )
                lines.append("</table>")

    # ── 3. Query Impact Analysis ──────────────────────────────────────
    lines.append("<h2>3. Query Impact Analysis</h2>")
    affected = [qi for qi in report.query_impacts if qi.risk_level != "none"]
    if not affected:
        lines.append(
            f"<p><em>No query impacts detected across "
            f"{report.total_queries_tested} tested queries.</em></p>"
        )
    else:
        lines.append(
            f"<p><strong>{len(affected)}</strong> of "
            f"<strong>{report.total_queries_tested}</strong> queries impacted.</p>"
        )
        lines.append(
            "<table><tr><th>Risk</th><th>Query</th>"
            "<th>Tools Lost</th><th>Tools Gained</th><th>Regression</th></tr>"
        )
        for qi in sorted(
            affected, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.risk_level, 3)
        ):
            rc = f"risk-{qi.risk_level}"
            lost_html = (
                " ".join(f"<code>{_html_escape(t)}</code>" for t in qi.tools_lost)
                if qi.tools_lost else "—"
            )
            gained_html = (
                " ".join(f"<code>{_html_escape(t)}</code>" for t in qi.tools_gained)
                if qi.tools_gained else "—"
            )
            reg_html = (
                "<span class='regression-yes'>🚨 Yes</span>"
                if qi.regression
                else "<span class='regression-no'>No</span>"
            )
            lines.append(
                f"<tr>"
                f"<td><span class='badge {rc}'>{qi.risk_level}</span></td>"
                f"<td><code>{_html_escape(_truncate(qi.query, 60))}</code></td>"
                f"<td>{lost_html}</td>"
                f"<td>{gained_html}</td>"
                f"<td>{reg_html}</td>"
                f"</tr>"
            )
        lines.append("</table>")

    # ── 4. Regressions Detected ───────────────────────────────────────
    lines.append("<h2>4. Regressions Detected</h2>")
    if not report.regressions:
        lines.append(
            "<p><em>No regressions detected. "
            "All golden scenario contracts satisfied.</em></p>"
        )
    else:
        lines.append(f"<p><strong>{len(report.regressions)} regression(s):</strong></p>")
        lines.append("<ul>")
        for reg in report.regressions:
            lines.append(f"<li><strong>Query:</strong> <code>{_html_escape(reg['query'])}</code>")
            if reg.get("scenario"):
                lines.append(f"<br><strong>Scenario:</strong> <code>{_html_escape(reg['scenario'])}</code>")
            if reg.get("tools_lost"):
                lost_html = " ".join(f"<code>{_html_escape(t)}</code>" for t in reg["tools_lost"])
                lines.append(f"<br><strong>Tools Lost:</strong> {lost_html}")
            if reg.get("risk_reasons"):
                lines.append("<ul>")
                for reason in reg["risk_reasons"]:
                    lines.append(f"<li>{_html_escape(reason)}</li>")
                lines.append("</ul>")
            lines.append("</li>")
        lines.append("</ul>")

    # ── 5. Risk Assessment ────────────────────────────────────────────
    risk_descriptions = {
        "high": (
            "🔴 HIGH — Required tools are lost from golden scenario selections, "
            "or affordance escalated toward DESTRUCTIVE. Do not merge without fixing regressions."
        ),
        "medium": (
            "🟡 MEDIUM — Tool ranks shifted significantly, domains were removed, or tools "
            "dropped from selection without golden scenario coverage. Review carefully."
        ),
        "low": (
            "🟢 LOW — Minor changes with limited query impact. "
            "Standard code review and testing is sufficient."
        ),
        "none": (
            "✅ NONE — No observable impact on tool selection for any tested query. "
            "Change is safe to proceed."
        ),
    }
    lines.append("<h2>5. Risk Assessment</h2>")
    lines.append(
        f"<div class='alert-{report.risk_assessment}'>"
        f"{_html_escape(risk_descriptions.get(report.risk_assessment, report.risk_assessment))}"
        f"</div>"
    )

    # Per-query breakdown
    risk_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for qi in report.query_impacts:
        risk_counts[qi.risk_level] = risk_counts.get(qi.risk_level, 0) + 1
    lines.append("<table><tr><th>Risk Level</th><th>Query Count</th></tr>")
    for level in ("high", "medium", "low", "none"):
        lines.append(
            f"<tr><td><span class='badge risk-{level}'>{level}</span></td>"
            f"<td>{risk_counts.get(level, 0)}</td></tr>"
        )
    lines.append("</table>")

    # ── 6. Validation Checklist ───────────────────────────────────────
    lines.append("<h2>6. Validation Checklist</h2>")
    if report.validation_checklist:
        lines.append("<ul class='checklist'>")
        for item in report.validation_checklist:
            lines.append(f"<li>{_html_escape(item)}</li>")
        lines.append("</ul>")
    else:
        lines.append("<p><em>No specific validation steps required.</em></p>")

    # ── 7. Recommendations ────────────────────────────────────────────
    lines.append("<h2>7. Recommendations</h2>")
    if report.recommendations:
        lines.append("<ol>")
        for rec in report.recommendations:
            lines.append(f"<li>{_html_escape(rec)}</li>")
        lines.append("</ol>")
    else:
        lines.append("<p><em>No recommendations — change appears safe.</em></p>")

    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML helpers
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


def _html_row(lines: List[str], label: str, value: str) -> None:
    lines.append(f"<tr><td>{_html_escape(label)}</td><td>{value}</td></tr>")


def _truncate(text: str, max_len: int) -> str:
    """Truncate a string to max_len characters with an ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: C901 — CLI functions are intentionally long
    """Run the manifest impact analyzer from the command line."""
    parser = argparse.ArgumentParser(
        prog="manifest_impact_analyzer",
        description=(
            "Analyze the impact of tool manifest changes on query tool selection. "
            "Works offline — no Azure or MCP connections required."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          # Baseline: run all golden scenarios against current manifests
          python -m utils.manifest_impact_analyzer --baseline

          # Check a specific tool with proposed tag changes
          python -m utils.manifest_impact_analyzer check_resource_health \\
              --tags '["health","diagnostics","resource","sre"]'

          # Compare before/after manifest JSON files
          python -m utils.manifest_impact_analyzer \\
              --before old_manifest.json --after new_manifest.json

          # Add custom test queries for a specific tool
          python -m utils.manifest_impact_analyzer container_app_list \\
              --test-query "list my container apps" \\
              --test-query "show container apps"

          # Output formats
          python -m utils.manifest_impact_analyzer --baseline --format json
          python -m utils.manifest_impact_analyzer --baseline --format html -o impact.html

          # CI mode: exits 1 if regressions detected (JSON to stdout)
          python -m utils.manifest_impact_analyzer --baseline --ci
        """),
    )

    # ── Mode selection ─────────────────────────────────────────────────
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "tool_name",
        nargs="?",
        help="Tool name to analyze (compares current manifest vs. proposed changes)",
    )
    mode_group.add_argument(
        "--baseline",
        action="store_true",
        help="Run all golden scenarios against current manifests (no-change baseline check)",
    )

    # ── File-compare mode ──────────────────────────────────────────────
    parser.add_argument(
        "--before",
        metavar="PATH",
        help="Path to 'before' manifest JSON file (use with --after)",
    )
    parser.add_argument(
        "--after",
        metavar="PATH",
        help="Path to 'after' manifest JSON file (use with --before)",
    )

    # ── Proposed field overrides (single-tool mode) ────────────────────
    parser.add_argument(
        "--tags",
        metavar="JSON",
        help='Proposed tags as JSON array, e.g. \'["health","sre"]\'',
    )
    parser.add_argument(
        "--domains",
        metavar="JSON",
        help='Proposed domains as JSON array, e.g. \'["sre_health"]\'',
    )
    parser.add_argument(
        "--example-queries",
        metavar="JSON",
        help='Proposed example queries as JSON array',
    )
    parser.add_argument(
        "--affordance",
        choices=["read", "write", "deploy", "destructive"],
        help="Proposed affordance value",
    )
    parser.add_argument(
        "--manifest-json",
        metavar="JSON",
        help="Full proposed manifest as inline JSON object (overrides other field flags)",
    )

    # ── Test queries ───────────────────────────────────────────────────
    parser.add_argument(
        "--test-query",
        metavar="QUERY",
        action="append",
        dest="test_queries",
        default=[],
        help="Additional test query to run (may be repeated)",
    )

    # ── Output options ─────────────────────────────────────────────────
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
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress messages on stderr",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            "CI mode: output JSON to stdout and exit 1 if any regressions detected. "
            "Overrides --format."
        ),
    )

    args = parser.parse_args()

    # ── Validate args ──────────────────────────────────────────────────
    if args.before and not args.after:
        parser.error("--before requires --after")
    if args.after and not args.before:
        parser.error("--after requires --before")

    analyzer = ManifestImpactAnalyzer()

    # ── Execute requested mode ─────────────────────────────────────────

    # File-compare mode
    if args.before and args.after:
        if not args.quiet:
            print(
                f"Comparing manifests: {args.before} → {args.after}",
                file=sys.stderr,
            )
        report = asyncio.run(
            analyzer.analyze_manifest_file_change(args.before, args.after)
        )

    # Baseline mode
    elif args.baseline:
        if not args.quiet:
            print("Running baseline check against all golden scenarios…", file=sys.stderr)
        report = asyncio.run(analyzer.analyze_all_manifests_against_scenarios())

    # Single-tool mode
    elif args.tool_name:
        tool_name = args.tool_name
        index = get_tool_manifest_index()
        current = index.get(tool_name)

        # Build proposed manifest from current + overrides
        if args.manifest_json:
            try:
                proposed_dict = json.loads(args.manifest_json)
                proposed_dict.setdefault("tool_name", tool_name)
                if current:
                    # Fill missing fields from current manifest
                    full_dict = _manifest_to_dict(current)
                    full_dict.update(proposed_dict)
                    proposed = _dict_to_manifest(full_dict)
                else:
                    proposed = _dict_to_manifest(proposed_dict)
            except json.JSONDecodeError as exc:
                print(f"Error: Invalid JSON in --manifest-json: {exc}", file=sys.stderr)
                sys.exit(2)
        elif current is not None:
            # Apply individual field overrides to current manifest
            current_dict = _manifest_to_dict(current)
            if args.tags:
                try:
                    current_dict["tags"] = json.loads(args.tags)
                except json.JSONDecodeError:
                    print("Error: --tags must be a valid JSON array", file=sys.stderr)
                    sys.exit(2)
            if args.domains:
                try:
                    current_dict["domains"] = json.loads(args.domains)
                except json.JSONDecodeError:
                    print("Error: --domains must be a valid JSON array", file=sys.stderr)
                    sys.exit(2)
            if args.example_queries:
                try:
                    current_dict["example_queries"] = json.loads(args.example_queries)
                except json.JSONDecodeError:
                    print("Error: --example-queries must be a valid JSON array", file=sys.stderr)
                    sys.exit(2)
            if args.affordance:
                current_dict["affordance"] = args.affordance
            proposed = _dict_to_manifest(current_dict)
        else:
            # Tool not found in index — check if any field overrides were provided
            if not any([args.tags, args.domains, args.example_queries,
                        args.affordance, args.manifest_json]):
                print(
                    f"Error: Tool '{tool_name}' not found in manifest index. "
                    f"Use --manifest-json to supply a full proposed manifest.",
                    file=sys.stderr,
                )
                sys.exit(2)
            # Build minimal manifest from provided overrides
            minimal_dict: Dict[str, Any] = {
                "tool_name": tool_name,
                "source": "",
                "domains": json.loads(args.domains) if args.domains else [],
                "tags": json.loads(args.tags) if args.tags else [],
                "affordance": args.affordance or "read",
                "example_queries": json.loads(args.example_queries) if args.example_queries else [],
                "conflicts_with": [],
                "conflict_note": "",
                "preferred_over": [],
            }
            proposed = _dict_to_manifest(minimal_dict)

        if not args.quiet:
            print(
                f"Analyzing impact for '{tool_name}'…",
                file=sys.stderr,
            )

        report = asyncio.run(
            analyzer.analyze_impact(tool_name, proposed, test_queries=args.test_queries or None)
        )

    else:
        # No mode selected — show help
        parser.print_help()
        sys.exit(0)

    # ── Progress summary ───────────────────────────────────────────────
    if not args.quiet and not args.ci:
        print(
            f"Done. Queries={report.total_queries_tested}, "
            f"Affected={report.queries_affected}, "
            f"Regressions={report.queries_with_regressions}, "
            f"Risk={report.risk_assessment.upper()}, "
            f"Duration={report.duration_ms:.1f}ms",
            file=sys.stderr,
        )

    # ── CI mode: always JSON, exit 1 on regressions ────────────────────
    if args.ci:
        output = format_json(report)
        print(output)
        sys.exit(1 if report.queries_with_regressions > 0 else 0)

    # ── Normal output ──────────────────────────────────────────────────
    if args.format == "json":
        output = format_json(report)
    elif args.format == "html":
        output = format_html(report)
    else:
        output = format_markdown(report)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        if not args.quiet:
            print(f"Report written to: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
