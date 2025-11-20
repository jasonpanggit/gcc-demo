"""Composite MCP client that aggregates multiple MCP tool sources."""
from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ToolDefinition = Dict[str, Any]
ClientEntry = Tuple[str, Any]


class CompositeMCPClient:
    """Aggregates multiple MCP clients behind a single interface."""

    def __init__(self, clients: Sequence[ClientEntry]) -> None:
        self._clients: List[ClientEntry] = [(label, client) for label, client in clients if client]
        self._tool_definitions: List[ToolDefinition] = []
        self._tool_map: Dict[str, Tuple[Any, str]] = {}
        self._tool_sources: Dict[str, str] = {}
        self._build_catalog()

    def _build_catalog(self) -> None:
        self._tool_definitions.clear()
        self._tool_map.clear()
        self._tool_sources.clear()

        for label, client in self._clients:
            get_tools = getattr(client, "get_available_tools", None)
            if not callable(get_tools):
                logger.debug("Client '%s' has no get_available_tools method", label)
                continue

            try:
                tools: Iterable[Any] = get_tools()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Failed to list tools for client '%s': %s", label, exc)
                continue

            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                function = tool.get("function") if isinstance(tool.get("function"), dict) else None
                if not function:
                    continue
                original_name = str(function.get("name") or "").strip()
                if not original_name:
                    continue

                final_name = original_name
                suffix = 1
                while final_name in self._tool_map:
                    suffix += 1
                    final_name = f"{original_name}_{suffix}"

                tool_definition = deepcopy(tool)
                tool_definition.setdefault("function", {})["name"] = final_name
                tool_definition.setdefault("function", {})["x_original_name"] = original_name
                metadata_block = tool_definition.setdefault("metadata", {})
                metadata_block.setdefault("source", label)
                metadata_block.setdefault("original_name", original_name)

                self._tool_map[final_name] = (client, original_name)
                self._tool_sources[final_name] = label
                self._tool_definitions.append(tool_definition)
                logger.debug(
                    "Registered MCP tool '%s' (original '%s') from client '%s'",
                    final_name,
                    original_name,
                    label,
                )

        if self._tool_definitions:
            counts: Dict[str, int] = {}
            for source_label in self._tool_sources.values():
                counts[source_label] = counts.get(source_label, 0) + 1
            ordered = ", ".join(f"{label}={count}" for label, count in counts.items())
            logger.info(
                "Composite MCP catalog built with %d tool(s) [%s]",
                len(self._tool_definitions),
                ordered or "no sources",
            )
        else:
            logger.info("Composite MCP catalog is empty; no tools registered from %d client(s)", len(self._clients))

    def get_available_tools(self) -> List[ToolDefinition]:
        return deepcopy(self._tool_definitions)

    def get_tool_sources(self) -> Dict[str, str]:
        return dict(self._tool_sources)

    def get_client_labels(self) -> List[str]:
        return [label for label, _ in self._clients]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        entry = self._tool_map.get(tool_name)
        if not entry:
            logger.warning("Requested MCP tool '%s' not found", tool_name)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Tool '{tool_name}' not available in composite client.",
                "is_error": True,
            }

        client, original_name = entry
        call_method = getattr(client, "call_tool", None)
        if not callable(call_method):
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Client for tool '{tool_name}' does not support call_tool().",
                "is_error": True,
            }

        try:
            result = call_method(original_name, arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Composite MCP call failed for '%s'", tool_name)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }

        if isinstance(result, dict):
            result.setdefault("tool_name", tool_name)
            result.setdefault("client_tool_name", original_name)
            tool_source = self._tool_sources.get(tool_name)
            if tool_source:
                result.setdefault("tool_source", tool_source)
            return result

        return {
            "success": False,
            "tool_name": tool_name,
            "error": "Tool call returned unexpected payload",
            "payload": json.dumps(result, default=str),
            "is_error": True,
        }

    async def aclose(self) -> None:
        for label, client in self._clients:
            close_methods = ("aclose", "close", "cleanup")
            for method_name in close_methods:
                closer = getattr(client, method_name, None)
                if not callable(closer):
                    continue
                try:
                    result = closer()
                    if asyncio.iscoroutine(result):
                        await result
                    logger.debug("Closed MCP client '%s' via %s", label, method_name)
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    logger.debug(
                        "Failed to close MCP client '%s' via %s: %s",
                        label,
                        method_name,
                        exc,
                    )
                    continue