"""Centralized MCP tool registry for all orchestrators.

This module provides a singleton registry that manages tool registration,
discovery, and invocation across all MCP servers. It eliminates tool
duplication and provides a unified interface for tool access.

Features:
- Dynamic tool discovery via list_tools() protocol
- Server registration with metadata
- Tool name collision handling
- Domain-based filtering
- Source-based filtering
- Notification subscriptions for tool updates
- Thread-safe singleton pattern

Usage:
    # Get registry instance
    registry = get_tool_registry()

    # Register an MCP server
    await registry.register_server("sre", sre_client, domain="sre")

    # Get tools by domain
    sre_tools = registry.get_tools_by_domain("sre")

    # Invoke a tool
    result = await registry.invoke_tool("check_resource_health", {"resource_id": "..."})
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    """Represents a registered tool with full metadata.

    Attributes:
        name: Final tool name (may include collision suffix)
        original_name: Original tool name from server
        description: Tool description for LLM
        parameters: JSON schema for tool parameters
        source_label: Source server label (e.g., "sre", "network")
        domain: Primary domain (e.g., "sre", "monitoring")
        priority: Priority level (lower = higher priority, for collision resolution)
        client: MCP client instance that can invoke this tool
        registered_at: Timestamp when tool was registered
    """
    name: str
    original_name: str
    description: str
    parameters: Dict[str, Any]
    source_label: str
    domain: Optional[str] = None
    priority: int = 100
    client: Any = None
    registered_at: datetime = field(default_factory=datetime.utcnow)

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "x_original_name": self.original_name,
            },
            "metadata": {
                "source": self.source_label,
                "original_name": self.original_name,
                "domain": self.domain,
                "priority": self.priority,
            }
        }


@dataclass
class ServerEntry:
    """Represents a registered MCP server/client.

    Attributes:
        label: Unique server identifier (e.g., "sre", "network")
        client: MCP client instance
        domain: Primary domain for this server's tools
        priority: Priority level (lower = higher priority)
        enabled: Whether server is currently enabled
        registered_at: Timestamp when server was registered
        tool_count: Number of tools registered from this server
    """
    label: str
    client: Any
    domain: Optional[str] = None
    priority: int = 100
    enabled: bool = True
    registered_at: datetime = field(default_factory=datetime.utcnow)
    tool_count: int = 0


class MCPToolRegistry:
    """
    Centralized registry for all MCP tools across all servers.

    This singleton class manages the complete lifecycle of MCP tools:
    - Server registration and management
    - Dynamic tool discovery
    - Tool name collision resolution
    - Domain-based organization
    - Tool invocation routing
    - Notification subscriptions

    The registry uses a singleton pattern to ensure a single source of truth
    for all tool metadata across the application.

    Thread Safety:
        All mutating operations (register_server, discover_tools) are
        protected by an asyncio.Lock to ensure thread-safe operation.

    Example:
        >>> registry = get_tool_registry()
        >>> await registry.register_server("sre", sre_client, domain="sre")
        >>> tools = registry.get_all_tools()
        >>> result = await registry.invoke_tool("check_health", {"resource_id": "123"})
    """

    _instance: Optional['MCPToolRegistry'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Ensure singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize registry data structures.

        Only initializes once (on first instantiation) to maintain singleton pattern.
        """
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self._servers: Dict[str, ServerEntry] = {}
        self._tools: Dict[str, ToolEntry] = {}
        self._tool_sources: Dict[str, str] = {}  # tool_name → source_label
        self._domain_map: Dict[str, Set[str]] = defaultdict(set)  # domain → tool_names
        self._notification_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._initialized = True
        logger.info("MCPToolRegistry initialized (singleton)")

    async def register_server(
        self,
        label: str,
        client: Any,
        domain: Optional[str] = None,
        priority: int = 100,
        auto_discover: bool = True
    ) -> ServerEntry:
        """
        Register an MCP server and optionally auto-discover its tools.

        Args:
            label: Unique identifier for the server (e.g., "sre", "network")
            client: MCP client instance with get_available_tools() and call_tool()
            domain: Primary domain for this server's tools
            priority: Priority level (lower = higher priority, default=100)
            auto_discover: Whether to automatically discover tools (default=True)

        Returns:
            ServerEntry with registration metadata

        Raises:
            ValueError: If label already registered or client invalid

        Example:
            >>> await registry.register_server(
            ...     label="sre",
            ...     client=sre_mcp_client,
            ...     domain="sre",
            ...     priority=1
            ... )
        """
        async with self._lock:
            if label in self._servers:
                raise ValueError(f"Server '{label}' already registered")

            if not hasattr(client, 'get_available_tools'):
                raise ValueError(f"Client must implement get_available_tools() method")

            server = ServerEntry(
                label=label,
                client=client,
                domain=domain,
                priority=priority,
                enabled=True
            )

            self._servers[label] = server
            logger.info(f"Registered MCP server: {label} (domain={domain}, priority={priority})")

            if auto_discover:
                await self.discover_tools(label)

            return server

    async def discover_tools(self, server_label: str) -> List[ToolEntry]:
        """
        Discover and register tools from a specific server.

        Calls the server's get_available_tools() method and registers each
        tool in the registry with appropriate metadata and collision handling.

        Args:
            server_label: Label of the server to discover tools from

        Returns:
            List of discovered ToolEntry objects

        Raises:
            ValueError: If server not registered

        Example:
            >>> tools = await registry.discover_tools("sre")
            >>> print(f"Discovered {len(tools)} tools")
        """
        if server_label not in self._servers:
            raise ValueError(f"Server '{server_label}' not registered")

        server = self._servers[server_label]
        if not server.enabled:
            logger.debug(f"Skipping tool discovery for disabled server: {server_label}")
            return []

        try:
            # Call get_available_tools() from client
            tools_raw = server.client.get_available_tools()
            discovered = []

            for tool_def in tools_raw:
                if not isinstance(tool_def, dict):
                    continue

                function = tool_def.get("function", {})
                if not isinstance(function, dict):
                    continue

                original_name = function.get("name", "").strip()
                if not original_name:
                    continue

                # Handle name collisions
                final_name = self._resolve_collision(original_name, server_label, server.priority)

                tool_entry = ToolEntry(
                    name=final_name,
                    original_name=original_name,
                    description=function.get("description", ""),
                    parameters=function.get("parameters", {}),
                    source_label=server_label,
                    domain=server.domain,
                    priority=server.priority,
                    client=server.client
                )

                # Register in all indexes
                self._tools[final_name] = tool_entry
                self._tool_sources[final_name] = server_label

                if server.domain:
                    self._domain_map[server.domain].add(final_name)

                discovered.append(tool_entry)

            # Update server tool count
            server.tool_count = len(discovered)

            logger.info(
                f"Discovered {len(discovered)} tools from server '{server_label}'"
            )
            return discovered

        except Exception as exc:
            logger.error(
                f"Failed to discover tools from server '{server_label}': {exc}",
                exc_info=True
            )
            return []

    def _resolve_collision(
        self,
        tool_name: str,
        source_label: str,
        priority: int
    ) -> str:
        """
        Resolve tool name collision by appending suffix or using priority.

        Strategy:
        1. If no collision, return original name
        2. If collision with lower priority tool, replace it and suffix the old one
        3. If collision with higher priority tool, suffix the new one

        Args:
            tool_name: Original tool name
            source_label: Source server label
            priority: Priority of new tool (lower = higher priority)

        Returns:
            Final tool name (may have suffix)

        Example:
            >>> # First tool "read_resource" from sre (priority=1)
            >>> final = _resolve_collision("read_resource", "sre", 1)
            >>> # final == "read_resource"
            >>>
            >>> # Second tool "read_resource" from azure (priority=5)
            >>> final = _resolve_collision("read_resource", "azure", 5)
            >>> # final == "read_resource_azure" (lower priority, gets suffix)
        """
        if tool_name not in self._tools:
            return tool_name

        # Collision detected
        existing_tool = self._tools[tool_name]

        # If new tool has higher priority (lower number), it wins
        if priority < existing_tool.priority:
            # Suffix the existing tool and give clean name to new tool
            old_source = existing_tool.source_label
            old_name = tool_name
            new_old_name = f"{old_name}_{old_source}"

            # Ensure the new name for old tool is unique
            suffix = 2
            while new_old_name in self._tools:
                new_old_name = f"{old_name}_{old_source}_{suffix}"
                suffix += 1

            # Move existing tool to new name
            self._tools[new_old_name] = existing_tool
            existing_tool.name = new_old_name
            self._tool_sources[new_old_name] = old_source

            # Remove old mapping
            del self._tools[old_name]
            if old_name in self._tool_sources:
                del self._tool_sources[old_name]

            logger.warning(
                f"Tool collision resolved by priority: '{old_name}' from {old_source} "
                f"(priority={existing_tool.priority}) renamed to '{new_old_name}', "
                f"new tool from {source_label} (priority={priority}) gets clean name"
            )

            return tool_name  # New tool gets the clean name

        # New tool has lower priority, append suffix to it
        candidate = f"{tool_name}_{source_label}"
        suffix = 2

        while candidate in self._tools:
            candidate = f"{tool_name}_{source_label}_{suffix}"
            suffix += 1

        logger.warning(
            f"Tool name collision: '{tool_name}' → '{candidate}' "
            f"(source={source_label}, priority={priority})"
        )
        return candidate

    async def refresh_tool_catalog(self, server_label: Optional[str] = None) -> int:
        """
        Refresh tool catalog for specific server or all servers.

        Re-discovers tools from the specified server(s), updating the registry
        with any changes.

        Args:
            server_label: Specific server to refresh, or None for all servers

        Returns:
            Total number of tools refreshed

        Example:
            >>> # Refresh specific server
            >>> count = await registry.refresh_tool_catalog("sre")
            >>>
            >>> # Refresh all servers
            >>> total = await registry.refresh_tool_catalog()
        """
        if server_label:
            tools = await self.discover_tools(server_label)
            return len(tools)

        # Refresh all servers
        total = 0
        for label in list(self._servers.keys()):
            tools = await self.discover_tools(label)
            total += len(tools)

        logger.info(f"Refreshed tool catalog: {total} tools from {len(self._servers)} servers")
        return total

    def get_tool_by_name(self, tool_name: str) -> Optional[ToolEntry]:
        """Get tool entry by exact name match.

        Args:
            tool_name: Exact tool name to look up

        Returns:
            ToolEntry if found, None otherwise
        """
        return self._tools.get(tool_name)

    def get_tools_by_domain(self, domain: str) -> List[ToolEntry]:
        """Get all tools for a specific domain.

        Args:
            domain: Domain name (e.g., "sre", "monitoring", "network")

        Returns:
            List of ToolEntry objects in the domain
        """
        tool_names = self._domain_map.get(domain, set())
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_tools_by_source(self, source_label: str) -> List[ToolEntry]:
        """Get all tools from a specific source.

        Args:
            source_label: Source server label (e.g., "sre", "network")

        Returns:
            List of ToolEntry objects from the source
        """
        return [
            tool for tool in self._tools.values()
            if tool.source_label == source_label
        ]

    def get_tools_by_sources(self, source_labels: List[str]) -> List[ToolEntry]:
        """Get all tools from multiple sources.

        Args:
            source_labels: List of source server labels

        Returns:
            List of ToolEntry objects from any of the sources
        """
        allowed = set(source_labels)
        return [
            tool for tool in self._tools.values()
            if tool.source_label in allowed
        ]

    def get_all_tools(self) -> List[ToolEntry]:
        """Get all registered tools.

        Returns:
            List of all ToolEntry objects in the registry
        """
        return list(self._tools.values())

    def get_all_tools_openai_format(self) -> List[Dict[str, Any]]:
        """Get all tools in OpenAI function-calling format.

        Returns:
            List of tool definitions in OpenAI format
        """
        return [tool.to_openai_format() for tool in self._tools.values()]

    def get_tools_openai_format(
        self,
        domain: Optional[str] = None,
        sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get filtered tools in OpenAI function-calling format.

        Args:
            domain: Optional domain filter
            sources: Optional source labels filter

        Returns:
            List of tool definitions in OpenAI format
        """
        if domain:
            tools = self.get_tools_by_domain(domain)
        elif sources:
            tools = self.get_tools_by_sources(sources)
        else:
            tools = self.get_all_tools()

        return [tool.to_openai_format() for tool in tools]

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoke a tool by name using its registered client.

        Args:
            tool_name: Name of the tool to invoke
            arguments: Tool arguments dictionary

        Returns:
            Tool execution result dictionary

        Raises:
            ValueError: If tool not found

        Example:
            >>> result = await registry.invoke_tool(
            ...     "check_resource_health",
            ...     {"resource_id": "vm-123"}
            ... )
        """
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        try:
            result = tool.client.call_tool(tool.original_name, arguments)
            if asyncio.iscoroutine(result):
                result = await result

            # Enrich result with metadata
            if isinstance(result, dict):
                result.setdefault("tool_name", tool_name)
                result.setdefault("tool_source", tool.source_label)

            return result

        except (ConnectionError, TimeoutError) as exc:
            # Transient errors - could add retry logic here
            logger.warning(f"Tool invocation failed (transient): {tool_name} - {exc}")
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Connection error: {exc}",
                "is_error": True,
                "retry_suggested": True,
            }
        except Exception as exc:
            # Unexpected errors - log with full traceback
            logger.exception(f"Tool invocation failed (unexpected): {tool_name}")
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }

    def subscribe_notification(
        self,
        event_type: str,
        handler: Callable[[str, Any], None]
    ) -> None:
        """
        Subscribe to registry notification events.

        Supported events:
        - "tools_changed": Fired when tools are added/removed
        - "server_registered": Fired when new server registered
        - "tool_discovered": Fired when new tool discovered

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function to handle event

        Example:
            >>> def on_tools_changed(server_label, tool_count):
            ...     print(f"Tools changed for {server_label}: {tool_count}")
            >>>
            >>> registry.subscribe_notification("tools_changed", on_tools_changed)
        """
        self._notification_handlers[event_type].append(handler)
        logger.debug(f"Subscribed to notification: {event_type}")

    def _notify(self, event_type: str, *args, **kwargs) -> None:
        """Internal method to trigger notification handlers."""
        handlers = self._notification_handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(*args, **kwargs)
            except Exception as exc:
                logger.error(f"Notification handler failed for {event_type}: {exc}")

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dictionary with registry stats including:
            - total_servers: Number of registered servers
            - total_tools: Number of registered tools
            - tools_by_source: Breakdown by source
            - tools_by_domain: Breakdown by domain
        """
        tools_by_source = defaultdict(int)
        for tool in self._tools.values():
            tools_by_source[tool.source_label] += 1

        tools_by_domain = defaultdict(int)
        for domain, tool_names in self._domain_map.items():
            tools_by_domain[domain] = len(tool_names)

        return {
            "total_servers": len(self._servers),
            "total_tools": len(self._tools),
            "tools_by_source": dict(tools_by_source),
            "tools_by_domain": dict(tools_by_domain),
            "servers": {
                label: {
                    "enabled": server.enabled,
                    "domain": server.domain,
                    "tool_count": server.tool_count,
                }
                for label, server in self._servers.items()
            }
        }

    def clear(self) -> None:
        """Clear all registry data. Used primarily for testing."""
        self._servers.clear()
        self._tools.clear()
        self._tool_sources.clear()
        self._domain_map.clear()
        self._notification_handlers.clear()
        logger.info("Registry cleared")


# Global registry instance accessor
_registry_instance: Optional[MCPToolRegistry] = None


def get_tool_registry() -> MCPToolRegistry:
    """
    Get the singleton MCPToolRegistry instance.

    This is the primary way to access the registry throughout the application.

    Returns:
        MCPToolRegistry singleton instance

    Example:
        >>> from utils.tool_registry import get_tool_registry
        >>>
        >>> registry = get_tool_registry()
        >>> tools = registry.get_all_tools()
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MCPToolRegistry()
    return _registry_instance
