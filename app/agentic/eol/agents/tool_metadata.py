"""Utilities for working with crawled Azure MCP tool metadata."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_METADATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "data"
    / "azure_mcp_tool_metadata.json"
)


class ToolMetadataManager:
    """Load and provide access to Azure MCP tool metadata."""

    def __init__(self, metadata_path: Optional[Path] = None) -> None:
        self._metadata_path = metadata_path or _DEFAULT_METADATA_PATH
        self._metadata: Dict[str, Any] = {}
        self._tools_by_slug: Dict[str, Dict[str, Any]] = {}
        self._tools_by_namespace: Dict[str, Dict[str, Any]] = {}
        self._categories: Dict[str, List[Dict[str, Any]]] = {}
        self._operations_by_tool_name: Dict[str, Dict[str, Any]] = {}
        self._last_mtime: Optional[float] = None
        self._lock = threading.RLock()

    def _load(self) -> None:
        if not self._metadata_path.exists():
            self._metadata = {"tools": []}
            self._tools_by_slug = {}
            self._tools_by_namespace = {}
            self._categories = {}
            self._operations_by_tool_name = {}
            self._last_mtime = None
            return

        mtime = self._metadata_path.stat().st_mtime
        if self._last_mtime and mtime == self._last_mtime:
            return

        content = self._metadata_path.read_text(encoding="utf-8")
        payload = json.loads(content)

        tools = payload.get("tools", []) if isinstance(payload, dict) else []
        self._metadata = {"tools": tools, "source": payload.get("source")}
        self._tools_by_slug = {}
        self._tools_by_namespace = {}
        self._categories = {}
        self._operations_by_tool_name = {}

        for tool in tools:
            slug = tool.get("slug")
            if slug:
                self._tools_by_slug[slug] = tool
            namespace = tool.get("namespace")
            if namespace:
                self._tools_by_namespace[namespace] = tool
            category = tool.get("category", "Uncategorized")
            self._categories.setdefault(category, []).append(tool)

            for operation in tool.get("operations", []) or []:
                op_title = operation.get("title")
                tool_name = self._compose_tool_name(namespace, op_title)
                if tool_name:
                    enriched_operation = dict(operation)
                    enriched_operation["namespace"] = namespace
                    enriched_operation["slug"] = slug
                    enriched_operation["tool_display_name"] = tool.get("display_name")
                    self._operations_by_tool_name[tool_name] = enriched_operation

        self._last_mtime = mtime

    def ensure_loaded(self) -> None:
        with self._lock:
            self._load()

    def get_all_tools(self) -> List[Dict[str, Any]]:
        self.ensure_loaded()
        return list(self._metadata.get("tools", []))

    def get_tool_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        self.ensure_loaded()
        return self._tools_by_slug.get(slug)

    def get_tool_by_namespace(self, namespace: str) -> Optional[Dict[str, Any]]:
        self.ensure_loaded()
        return self._tools_by_namespace.get(namespace)

    def get_categories(self) -> Dict[str, List[Dict[str, Any]]]:
        self.ensure_loaded()
        return self._categories

    def get_source_url(self) -> Optional[str]:
        self.ensure_loaded()
        return self._metadata.get("source")

    def get_operation_by_tool_name(self, tool_name: str) -> Optional[Dict[str, Any]]:
        self.ensure_loaded()
        return self._operations_by_tool_name.get(tool_name)

    @staticmethod
    def _compose_tool_name(namespace: Optional[str], operation_title: Optional[str]) -> Optional[str]:
        if not namespace:
            return None
        if not operation_title:
            return namespace
        slug = ToolMetadataManager._slugify(operation_title)
        return f"{namespace}-{slug}" if slug else namespace

    @staticmethod
    def _slugify(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
        normalized = normalized.strip("-")
        return normalized


_metadata_manager: Optional[ToolMetadataManager] = None
_manager_lock = threading.Lock()


def get_tool_metadata_manager() -> ToolMetadataManager:
    global _metadata_manager
    if _metadata_manager is None:
        with _manager_lock:
            if _metadata_manager is None:
                _metadata_manager = ToolMetadataManager()
    return _metadata_manager
