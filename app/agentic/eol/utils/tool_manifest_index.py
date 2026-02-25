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
