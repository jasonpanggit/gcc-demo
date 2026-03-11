"""MCP Host that coordinates multiple MCP clients and manages tool registry integration.

This module replaces the former CompositeMCPClient with an MCP spec-aligned
host pattern that manages multiple MCP client connections and integrates with
the centralized MCPToolRegistry.

Key Changes from CompositeMCPClient:
- Renamed to MCPHost (aligns with MCP specification terminology)
- Integrates with MCPToolRegistry for centralized tool management
- Async registration pattern via ensure_registered()
- Maintains backward compatibility with get_available_tools()
"""
from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .tool_registry import get_tool_registry

logger = logging.getLogger(__name__)

ToolDefinition = Dict[str, Any]
ClientEntry = Tuple[str, Any]


async def _get_client_for_label(label: str) -> Any:
    """Return an initialised MCP client instance for *label*, or raise.

    All imports are lazy (inside this function) so that importing
    ``mcp_host`` does not trigger heavy client-module loading.  Each
    factory is only imported when ``MCPHost.from_config()`` actually
    needs that server.

    Raises
    ------
    ValueError
        If *label* has no registered factory.
    Exception
        Any exception raised by the underlying factory function is
        propagated to the caller; ``from_config()`` wraps the call in
        a try/except and logs a WARNING before skipping the server.
    """
    if label == "azure":
        from .azure_mcp_client import get_azure_mcp_client
        return await get_azure_mcp_client()
    elif label == "sre":
        from .sre_mcp_client import get_sre_mcp_client
        return await get_sre_mcp_client()
    elif label == "network":
        from .network_mcp_client import get_network_mcp_client
        return await get_network_mcp_client()
    elif label == "compute":
        from .compute_mcp_client import get_compute_mcp_client
        return await get_compute_mcp_client()
    elif label == "storage":
        from .storage_mcp_client import get_storage_mcp_client
        return await get_storage_mcp_client()
    elif label == "monitor":
        from .monitor_mcp_client import get_workbook_mcp_client
        return await get_workbook_mcp_client()
    elif label == "patch":
        from .patch_mcp_client import get_patch_mcp_client
        return await get_patch_mcp_client()
    elif label == "cve":
        from .cve_mcp_client import get_cve_mcp_client
        return await get_cve_mcp_client()
    elif label == "os_eol":
        from .os_eol_mcp_client import get_os_eol_mcp_client
        return await get_os_eol_mcp_client()
    elif label == "inventory":
        from .inventory_mcp_client import get_inventory_mcp_client
        return await get_inventory_mcp_client()
    elif label == "azure_cli_executor":
        from .azure_cli_executor_client import get_cli_executor_client
        return await get_cli_executor_client()
    else:
        raise ValueError(f"No factory registered for label '{label}'")


class MCPHost:
    """
    MCP Host that coordinates multiple MCP clients.

    This class acts as the primary coordinator for multiple MCP server connections,
    following the Model Context Protocol specification's host pattern. It manages
    client lifecycle, tool aggregation, and registry integration.

    The host maintains both:
    1. Legacy tool catalog (for backward compatibility)
    2. Registry integration (for Phase 1+ functionality)

    Thread Safety:
        Client registration is async and should be awaited via ensure_registered()
        before accessing tools from the registry.

    Example:
        >>> host = MCPHost(clients=[
        ...     ("sre", sre_client),
        ...     ("network", network_client)
        ... ])
        >>> await host.ensure_registered()  # Register with tool registry
        >>> tools = host.get_available_tools()  # Legacy method
        >>> # Or use registry directly
        >>> registry = get_tool_registry()
        >>> tools = registry.get_all_tools_openai_format()
    """

    def __init__(self, clients: Sequence[ClientEntry]) -> None:
        """
        Initialize MCP host with client connections.

        Args:
            clients: Sequence of (label, client) tuples where:
                - label: Unique identifier (e.g., "sre", "network")
                - client: MCP client instance with get_available_tools() and call_tool()

        Note:
            This is synchronous initialization. Call ensure_registered() afterward
            to register clients with the tool registry asynchronously.
        """
        self._clients: List[ClientEntry] = [(label, client) for label, client in clients if client]
        self._registry = get_tool_registry()
        self._registration_task: Optional[asyncio.Task] = None
        self._registration_complete = False

        # Legacy catalog (for backward compatibility)
        self._tool_definitions: List[ToolDefinition] = []
        self._tool_map: Dict[str, Tuple[Any, str]] = {}
        self._tool_sources: Dict[str, str] = {}
        self._build_catalog()

    @classmethod
    async def from_config(
        cls,
        config_path: Optional[str] = None,
    ) -> "MCPHost":
        """Create a fully initialised MCPHost from ``mcp_servers.yaml``.

        Reads the enabled server list from the YAML config (via
        :class:`~utils.mcp_config_loader.MCPConfigLoader`), calls each
        server's factory function, and returns a registered
        :class:`MCPHost` instance.

        **Graceful degradation:** If a factory raises, that server is
        skipped (WARNING log) and initialisation continues.  Unknown
        labels (present in YAML but not in the factory mapping) are also
        skipped with a WARNING.

        Parameters
        ----------
        config_path:
            Optional path to ``mcp_servers.yaml``.  Defaults to
            ``<eol-root>/config/mcp_servers.yaml``.

        Returns
        -------
        MCPHost
            Initialised host with all successfully created clients
            registered in the tool registry.
        """
        # Lazy import to avoid circular-import risk at module load time.
        from .mcp_config_loader import MCPConfigLoader

        loader = MCPConfigLoader(config_path)
        server_configs = loader.get_enabled_servers()
        n = len(server_configs)
        logger.info("Initializing MCPHost from config: %d enabled servers", n)

        clients: List[ClientEntry] = []
        for server_cfg in server_configs:
            label = server_cfg.label
            try:
                client = await _get_client_for_label(label)
                clients.append((label, client))
            except ValueError as exc:
                # Label not in factory mapping
                logger.warning("Skipping server '%s': %s", label, exc)
            except Exception as exc:  # pylint: disable=broad-except
                # Factory raised — log and continue (graceful degradation)
                logger.warning("Skipping server '%s': %s", label, exc)

        m = len(clients)
        logger.info(
            "MCPHost.from_config() complete: %d/%d servers initialized", m, n
        )

        host = cls(clients)
        await host.ensure_registered()
        return host

    def _build_catalog(self) -> None:
        """
        Build legacy tool catalog for backward compatibility.

        This maintains the original CompositeMCPClient behavior while we
        transition to registry-based tool management.
        """
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

        if self._tool_definitions:
            counts: Dict[str, int] = {}
            for source_label in self._tool_sources.values():
                counts[source_label] = counts.get(source_label, 0) + 1
            ordered = ", ".join(f"{label}={count}" for label, count in counts.items())
            logger.info(
                "MCP Host catalog built with %d tool(s) [%s]",
                len(self._tool_definitions),
                ordered or "no sources",
            )
        else:
            logger.info("MCP Host catalog is empty; no tools from %d client(s)", len(self._clients))

    async def _register_clients(self) -> None:
        """
        Register all clients with the tool registry.

        This is called automatically by ensure_registered(). It registers each
        client with the global tool registry for centralized tool management.
        """
        for label, client in self._clients:
            get_tools = getattr(client, "get_available_tools", None)
            if not callable(get_tools):
                logger.debug(
                    "Skipping registry registration for client '%s': get_available_tools() not implemented",
                    label,
                )
                continue

            try:
                await self._registry.register_server(
                    label=label,
                    client=client,
                    domain=label,  # Use label as default domain
                    priority=100,  # Default priority
                    auto_discover=True
                )
                logger.info(f"Registered MCP client '{label}' with tool registry")
            except ValueError as exc:
                # Already registered - this is OK
                if "already registered" in str(exc):
                    logger.debug(f"Client '{label}' already registered with tool registry")
                else:
                    raise
            except Exception as exc:
                logger.error(
                    f"Failed to register client '{label}' with tool registry: {exc}",
                    exc_info=True
                )

        self._registration_complete = True

    async def ensure_registered(self) -> None:
        """
        Ensure all clients are registered with the tool registry.

        This method is safe to call multiple times - it will only register once.
        Call this after initialization and before accessing tools via the registry.

        Example:
            >>> host = MCPHost(clients)
            >>> await host.ensure_registered()
            >>> # Now safe to use registry
            >>> registry = get_tool_registry()
            >>> tools = registry.get_all_tools()
        """
        if self._registration_complete:
            return

        if self._registration_task is None:
            self._registration_task = asyncio.create_task(self._register_clients())

        await self._registration_task

    def get_available_tools(self) -> List[ToolDefinition]:
        """
        Get available tools (legacy method for backward compatibility).

        Returns tools from the legacy catalog. For new code, prefer using
        the tool registry directly via get_tool_registry().

        Returns:
            List of tool definitions in OpenAI format
        """
        return deepcopy(self._tool_definitions)

    def get_tools_from_registry(
        self,
        domain: Optional[str] = None,
        sources: Optional[List[str]] = None
    ) -> List[ToolDefinition]:
        """
        Get tools from the centralized registry (new method).

        This is the preferred way to access tools in Phase 1+. It queries the
        centralized tool registry instead of the legacy catalog.

        Args:
            domain: Optional domain filter
            sources: Optional source labels filter

        Returns:
            List of tool definitions in OpenAI format
        """
        return self._registry.get_tools_openai_format(domain=domain, sources=sources)

    def get_tools_by_sources(self, sources: Sequence[str]) -> List[ToolDefinition]:
        """Return tool definitions filtered to only tools from the given source labels."""
        allowed = set(sources)
        return deepcopy([
            td for td in self._tool_definitions
            if self._tool_sources.get(td.get("function", {}).get("name", "")) in allowed
        ])

    def get_tools_excluding_sources(self, sources: Sequence[str]) -> List[ToolDefinition]:
        """Return tool definitions excluding tools from the given source labels."""
        excluded = set(sources)
        return deepcopy([
            td for td in self._tool_definitions
            if self._tool_sources.get(td.get("function", {}).get("name", "")) not in excluded
        ])

    def get_tool_sources(self) -> Dict[str, str]:
        """Get mapping of tool names to their source labels."""
        return dict(self._tool_sources)

    def get_client_labels(self) -> List[str]:
        """Get list of registered client labels."""
        return [label for label, _ in self._clients]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool by name using the legacy catalog.

        For new code, prefer using registry.invoke_tool() directly.

        Args:
            tool_name: Name of tool to invoke
            arguments: Tool arguments dictionary

        Returns:
            Tool execution result
        """
        entry = self._tool_map.get(tool_name)
        if not entry:
            logger.warning("Requested MCP tool '%s' not found", tool_name)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Tool '{tool_name}' not available in MCP host.",
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
            logger.exception("MCP Host call failed for '%s'", tool_name)
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
        """Close all managed MCP client connections."""
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


# Backward compatibility alias
CompositeMCPClient = MCPHost
