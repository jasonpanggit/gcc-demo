"""Inventory tool manifests.

Inventory tools currently rely on default manifest behavior. This module exists
so the manifest index can load cleanly without logging a missing-module warning.
"""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolManifest  # type: ignore[import-not-found]


MANIFESTS: list[ToolManifest] = []