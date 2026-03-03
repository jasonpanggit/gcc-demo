"""Tool manifest index for the MCP orchestrator pipeline.

Provides per-tool metadata (affordance, tags, conflicts, examples) that was
previously scattered across _TOOL_DISAMBIGUATION strings and _SOURCE_GUIDANCE
dicts in mcp_composite_client.py.

Usage:
    from app.agentic.eol.utils.tool_manifest_index import (
        ToolManifestIndex, ToolAffordance, get_tool_manifest_index
    )
    index = get_tool_manifest_index()
    affordance = index.get_affordance("azure_cli_execute_command")
    note = index.build_conflict_note_for_context(["check_resource_health", "resourcehealth"])
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ToolAffordance(str, Enum):
    """Mutability classification for a tool."""

    READ = "read"           # Safe read-only query — no confirmation needed
    WRITE = "write"         # Mutating but reversible — present plan, require confirmation
    DESTRUCTIVE = "destructive"  # Irreversible or high blast-radius — explicit confirmation + gate
    DEPLOY = "deploy"       # Deployment lifecycle — pre-flight + validation required


@dataclass(frozen=True)
class ToolManifest:
    """Static metadata for a single MCP tool.

    All fields are immutable. Loaded once at import time from the manifests/
    package and registered in ToolManifestIndex.

    Phase 3 fields (all optional with safe defaults for backward compatibility):
        primary_phrasings: Positive example queries used for semantic routing boost.
        avoid_phrasings: Queries that should NOT trigger this tool (negative examples).
        confidence_boost: Score multiplier applied during retrieval (1.0 = no change).
        requires_sequence: Ordered list of tool names that must run before this one.
        preferred_over_list: Extended set of lower-priority tool names (tuple variant
            for manifest authoring convenience; supplements the core FrozenSet field).

    Note: ``preferred_over`` (FrozenSet[str]) is the original immutable field kept
    for backward compatibility.  The Phase 3 ``primary_phrasings``,
    ``avoid_phrasings``, ``requires_sequence``, and ``preferred_over_list`` fields
    use ``field(default=...)`` with frozen-dataclass-compatible defaults (immutable
    or None).
    """

    tool_name: str
    source: str                             # "azure" | "sre" | "monitor" | "inventory" | "os_eol" | "azure_cli" | "network"
    domains: FrozenSet[str]                 # UnifiedDomain values
    tags: FrozenSet[str]                    # Semantic boost tags: ["health", "container", "aks"]
    affordance: ToolAffordance
    example_queries: Tuple[str, ...]        # 2–4 NL queries for embedding boost
    conflicts_with: FrozenSet[str]          # Tool names the LLM confuses this with
    conflict_note: str                      # Injected only when conflicts_with tools are in context
    preferred_over: FrozenSet[str]          # Tools this should be chosen over
    requires_confirmation: bool = False
    deprecated: bool = False
    output_schema: Dict = field(default_factory=dict)  # Used by Verifier for schema validation

    # ── Phase 3: Intelligent Routing fields ──────────────────────────────────
    # Frozen dataclasses require hashable defaults. Tuples are used instead of
    # lists so the dataclass remains hashable while still supporting iteration.

    primary_phrasings: Tuple[str, ...] = field(default=())
    """Positive example queries that strongly indicate this tool should be used.

    Unlike ``example_queries`` (used for embedding similarity), these are used
    during retrieval scoring to boost confidence when a user's query closely
    matches one of these phrases.  Aim for 5–10 diverse natural-language
    phrasings covering common user intents.

    Example::

        primary_phrasings=(
            "list my container apps",
            "show all container apps",
            "what container apps do I have",
        )
    """

    avoid_phrasings: Tuple[str, ...] = field(default=())
    """Negative example queries that should NOT trigger this tool.

    Used to suppress false-positive matches during retrieval.  Include queries
    that superficially resemble this tool's purpose but actually belong to a
    different tool.

    Example::

        avoid_phrasings=(
            "check health of container apps",   # → check_container_app_health
            "restart container app",            # → execute_safe_restart
        )
    """

    confidence_boost: float = 1.0
    """Score multiplier applied to this tool's retrieval score (range 1.0–2.0).

    Values > 1.0 make this tool rank higher for matching queries.  Use this to
    express that a more specialised tool should be preferred over a generic one
    without hard-coding keyword rules.

    Typical values:
        1.0 – no preference (default)
        1.1 – mild preference (slightly more specialised)
        1.2 – moderate preference (clearly the right tool for its domain)
        1.5 – strong preference (specialised tool; generic alternatives exist)
    """

    requires_sequence: Optional[Tuple[str, ...]] = None
    """Ordered list of tool names that must execute before this tool.

    When the router encounters a query whose plan would include this tool, it
    will inject the prerequisite tools earlier in the plan if they are not
    already present.  Use this to encode deterministic chaining patterns that
    previously lived as hard-coded rules in router.py.

    ``None`` (default) means no prerequisites.

    Example (container app health requires listing first)::

        requires_sequence=("container_app_list",)
    """

    preferred_over_list: Tuple[str, ...] = field(default=())
    """Extended set of lower-priority tool names (list/tuple variant for manifest
    authoring convenience).

    Complements the core ``preferred_over`` FrozenSet field.  Use this Phase 3
    field to declare additional tool names that this tool should be ranked above
    during retrieval scoring, beyond the static conflict-resolution set in
    ``preferred_over``.

    The router merges ``preferred_over`` and ``preferred_over_list`` when
    computing final tool ranking.  Using this field avoids reconstructing
    frozen sets in manifests and keeps the authoring syntax uniform with the
    other Phase 3 tuple fields.

    ``()`` (default) means no additional preference declarations.

    Example::

        preferred_over_list=(
            "azure_cli_execute_command",
            "generic_resource_query",
        )
    """


class ToolManifestIndex:
    """Registry of ToolManifest entries.

    Provides:
    - O(1) affordance and manifest lookups by tool name
    - Context-aware conflict note generation (only active conflicts)
    """

    def __init__(self) -> None:
        self._manifests: Dict[str, ToolManifest] = {}

    def register(self, manifest: ToolManifest) -> None:
        """Register a single tool manifest."""
        self._manifests[manifest.tool_name] = manifest

    def register_all(self, manifests: List[ToolManifest]) -> None:
        """Register a list of tool manifests."""
        for m in manifests:
            self._manifests[m.tool_name] = m

    def get(self, tool_name: str) -> Optional[ToolManifest]:
        """Return the manifest for *tool_name*, or None if not registered."""
        return self._manifests.get(tool_name)

    def get_affordance(self, tool_name: str) -> ToolAffordance:
        """Return the affordance for *tool_name*.

        Defaults to READ for unknown tools (conservative — unknown tools are
        treated as read-only until a manifest is authored for them).
        """
        manifest = self._manifests.get(tool_name)
        if manifest is None:
            return ToolAffordance.READ
        return manifest.affordance

    def build_conflict_note_for_context(self, tool_names: List[str]) -> str:
        """Return disambiguation notes for conflicts active in the current tool set.

        Only emits notes for tools that are *both* present in *tool_names* and have
        a non-empty conflict_note. This avoids polluting every LLM call with all
        30+ disambiguation entries.

        Args:
            tool_names: Tool names currently in the LLM context window.

        Returns:
            Concatenated conflict notes (empty string if none apply).
        """
        name_set = set(tool_names)
        notes: List[str] = []
        seen: set[str] = set()

        for name in tool_names:
            manifest = self._manifests.get(name)
            if manifest is None:
                continue
            if not manifest.conflict_note:
                continue
            # Only emit if at least one conflicting tool is also in the active set
            active_conflicts = manifest.conflicts_with & name_set
            if active_conflicts and name not in seen:
                notes.append(f"[{name}] {manifest.conflict_note}")
                seen.add(name)

        return "\n".join(notes)

    def all_tool_names(self) -> List[str]:
        return list(self._manifests.keys())

    def get_requires_sequence(self, tool_name: str) -> Optional[Tuple[str, ...]]:
        """Return the requires_sequence for *tool_name*, or None if not set.

        Allows the ToolRetriever to inject prerequisite tools based on manifest
        metadata rather than hard-coded intent detection.
        """
        manifest = self._manifests.get(tool_name)
        if manifest is None:
            return None
        return manifest.requires_sequence

    def find_tools_matching_query(self, query: str) -> List[str]:
        """Return tool names whose primary_phrasings match the query.

        Matching strategy (descending priority):
          1. Exact substring: phrasing ⊆ query OR query ⊆ phrasing (+2 per phrasing)
          2. Significant-word overlap: ≥2 key tokens shared between query and phrasing (+1)

        Returns tools sorted by descending score (best match first).

        This replaces hard-coded keyword intent checks (e.g. ``_is_container_app_health_intent``
        and ``_expected_tools_for_query_intent``) with data-driven manifest lookups.

        Args:
            query: User's natural-language message.

        Returns:
            List of tool names with at least one matching primary_phrasing,
            sorted by descending match quality.
        """
        if not query:
            return []
        _STOP = frozenset({
            "a", "an", "the", "my", "your", "our", "its", "i", "me", "we",
            "is", "are", "was", "do", "does", "have", "has", "will", "can",
            "in", "on", "at", "by", "for", "of", "to", "from", "with", "and",
            "or", "but", "show", "list", "get", "display", "what", "how",
        })
        import re as _re
        q_lower = query.lower()
        q_tokens = {
            tok for tok in _re.sub(r"[^a-z0-9]", " ", q_lower).split()
            if len(tok) > 2 and tok not in _STOP
        }

        hits: List[Tuple[int, str]] = []  # (score, tool_name)
        for tool_name, manifest in self._manifests.items():
            if not manifest.primary_phrasings:
                continue
            score = 0
            for phrasing in manifest.primary_phrasings:
                p_lower = phrasing.lower()
                # Tier 1: substring containment
                if p_lower in q_lower or q_lower in p_lower:
                    score += 2
                    continue
                # Tier 2: significant token overlap (≥2 shared content words)
                if q_tokens:
                    p_tokens = {
                        tok for tok in _re.sub(r"[^a-z0-9]", " ", p_lower).split()
                        if len(tok) > 2 and tok not in _STOP
                    }
                    overlap = len(q_tokens & p_tokens)
                    if overlap >= 2:
                        score += 1
            if score > 0:
                hits.append((score, tool_name))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [tool_name for _, tool_name in hits]

    def get_prerequisite_tools(self, tool_names: List[str]) -> List[str]:
        """Return all prerequisite tool names for a list of tools, in order.

        Reads requires_sequence from manifests to replace hard-coded injection
        logic.  Only returns prerequisites not already present in *tool_names*.

        Args:
            tool_names: Tools currently in the retrieval result.

        Returns:
            Additional tool names that should be injected as prerequisites.
        """
        tool_set = set(tool_names)
        prerequisites: List[str] = []
        seen: set[str] = set()
        for tool_name in tool_names:
            seq = self.get_requires_sequence(tool_name)
            if not seq:
                continue
            for prereq in seq:
                if prereq not in tool_set and prereq not in seen:
                    prerequisites.append(prereq)
                    seen.add(prereq)
        return prerequisites

    def is_action_tool(self, tool_name: str) -> bool:
        """Return True when *tool_name* has a mutating/action affordance.

        Replaces the hard-coded ``_ACTION_TOOL_PREFIXES`` name-prefix check in
        ToolRetriever with a manifest-driven affordance lookup.  Falls back to
        name-prefix heuristics for tools without a manifest (backward compat).

        Args:
            tool_name: Tool name to classify.

        Returns:
            True if the tool mutates state (WRITE / DESTRUCTIVE / DEPLOY).
        """
        manifest = self._manifests.get(tool_name)
        if manifest is not None:
            return manifest.affordance in (
                ToolAffordance.WRITE,
                ToolAffordance.DESTRUCTIVE,
                ToolAffordance.DEPLOY,
            )
        # Fallback: name-prefix heuristic for tools without a manifest
        _ACTION_PREFIXES = (
            "test_", "check_", "create_", "delete_", "update_", "restart_",
            "trigger_", "enable_", "disable_", "assign_", "run_", "execute_",
            "invoke_", "start_", "stop_", "reset_", "patch_", "deploy_",
        )
        return any(tool_name.lower().startswith(p) for p in _ACTION_PREFIXES)

    def __len__(self) -> int:
        return len(self._manifests)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_index: Optional[ToolManifestIndex] = None


def get_tool_manifest_index() -> ToolManifestIndex:
    """Return the singleton ToolManifestIndex, loading manifests on first call."""
    global _index
    if _index is None:
        _index = _build_index()
    return _index


def _build_index() -> ToolManifestIndex:
    """Import all manifest modules and populate the index.

    Each manifest leaf name is tried under two prefixes so the index loads
    correctly regardless of whether uvicorn is started from the repository
    root (prefix = ``app.agentic.eol.utils.manifests``) **or** from the
    ``app/agentic/eol`` subdirectory (prefix = ``utils.manifests``).
    """
    index = ToolManifestIndex()
    _manifest_leaves = [
        "azure_manifests",
        "sre_manifests",
        "monitor_manifests",
        "inventory_manifests",
        "cli_manifests",
        "network_manifests",
        "compute_manifests",
        "storage_manifests",
    ]
    _prefixes = [
        "utils.manifests",
        "app.agentic.eol.utils.manifests",
    ]
    for leaf in _manifest_leaves:
        loaded = False
        last_exc: Optional[Exception] = None
        for prefix in _prefixes:
            module_path = f"{prefix}.{leaf}"
            try:
                module = importlib.import_module(module_path)
                manifests: List[ToolManifest] = getattr(module, "MANIFESTS", [])
                index.register_all(manifests)
                logger.debug("Loaded %d manifests from %s", len(manifests), module_path)
                loaded = True
                break
            except ImportError as exc:
                last_exc = exc
        if not loaded:
            logger.warning("Could not load manifest module '%s': %s", leaf, last_exc)
    logger.info("ToolManifestIndex: %d tool manifests loaded", len(index))
    return index
