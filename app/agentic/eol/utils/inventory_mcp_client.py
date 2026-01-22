"""Client helper for the Log Analytics inventory MCP server."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False

try:  # Prefer absolute imports when the project root is on sys.path
    from app.agentic.eol.agents.os_inventory_agent import OSInventoryAgent
    from app.agentic.eol.agents.software_inventory_agent import SoftwareInventoryAgent
except ModuleNotFoundError:  # pragma: no cover - support execution without top-level package
    from agents.os_inventory_agent import OSInventoryAgent  # type: ignore[import-not-found]
    from agents.software_inventory_agent import SoftwareInventoryAgent  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing support only
    from mcp import ClientSession as ClientSessionType  # type: ignore[import-not-found]
else:  # pragma: no cover - runtime when MCP is optional
    ClientSessionType = Any  # type: ignore[misc]


class InventoryFallbackExecutor:
    """Executes inventory lookups in-process when MCP server is unavailable."""

    def __init__(self) -> None:
        self._os_agent: Optional[OSInventoryAgent] = None
        self._software_agent: Optional[SoftwareInventoryAgent] = None
        self._lock = asyncio.Lock()
        self._last_initialization_error: Optional[str] = None
        self._tool_catalog: List[Dict[str, Any]] = [
            self._build_tool(
                name="inventory.os_inventory",
                description="Load operating system inventory records from Azure Log Analytics.",
                parameters={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Lookback window in days.",
                            "default": 90,
                        },
                        "limit": {
                            "type": ["integer", "null"],
                            "description": "Maximum number of rows to return (default 2000, set null for all).",
                            "default": 2000,
                        },
                        "use_cache": {
                            "type": "boolean",
                            "description": "Use cached inventory when available (default true).",
                            "default": True,
                        },
                    },
                    "additionalProperties": False,
                },
                original_name="law_get_os_inventory",
            ),
            self._build_tool(
                name="inventory.os_summary",
                description="Summarize operating system coverage from Log Analytics data.",
                parameters={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Lookback window in days.",
                            "default": 90,
                        }
                    },
                    "additionalProperties": False,
                },
                original_name="law_get_os_summary",
            ),
            self._build_tool(
                name="inventory.software_inventory",
                description="Load software inventory records from Azure Log Analytics ConfigurationData.",
                parameters={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Lookback window in days.",
                            "default": 90,
                        },
                        "limit": {
                            "type": ["integer", "null"],
                            "description": "Maximum number of rows to return (default 10000, set null for all).",
                            "default": 10000,
                        },
                        "software_filter": {
                            "type": ["string", "null"],
                            "description": "Optional substring filter applied to the software name.",
                            "default": None,
                        },
                        "use_cache": {
                            "type": "boolean",
                            "description": "Use cached inventory when available (default true).",
                            "default": True,
                        },
                    },
                    "additionalProperties": False,
                },
                original_name="law_get_software_inventory",
            ),
        ]
        self._handler_map = {
            "inventory.os_inventory": self._handle_os_inventory,
            "law_get_os_inventory": self._handle_os_inventory,
            "inventory.os_summary": self._handle_os_summary,
            "law_get_os_summary": self._handle_os_summary,
            "inventory.software_inventory": self._handle_software_inventory,
            "law_get_software_inventory": self._handle_software_inventory,
        }

    async def initialize(self) -> bool:
        # Warm up agents so that subsequent calls are fast, but tolerate environments
        # where dependencies are missing by deferring initialization until first use.
        results = await asyncio.gather(
            self._ensure_os_agent(optional=True),
            self._ensure_software_agent(optional=True),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):  # pragma: no cover - defensive logging
                self._last_initialization_error = str(result)
                logger.warning(
                    "Inventory fallback agent warm-up reported an error: %s",
                    result,
                )
        return True

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return deepcopy(self._tool_catalog)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handler_map.get(tool_name)
        if handler is None and tool_name.startswith("inventory."):
            handler = self._handler_map.get(tool_name.split(".", 1)[1])
        if handler is None:
            return self._format_response(
                tool_name,
                payload={"success": False, "error": f"Unknown inventory tool: {tool_name}"},
                success=False,
            )
        return await handler(tool_name, arguments or {})

    async def _ensure_os_agent(self, *, optional: bool = False) -> Optional[OSInventoryAgent]:
        if self._os_agent is not None:
            return self._os_agent
        async with self._lock:
            if self._os_agent is None:
                try:
                    logger.info("Starting OS inventory agent for in-process MCP fallback")
                    self._os_agent = OSInventoryAgent()
                    self._last_initialization_error = None
                except Exception as exc:  # pragma: no cover - optional dependency issues
                    self._last_initialization_error = str(exc)
                    if optional:
                        logger.debug("OS inventory agent warm-up failed: %s", exc, exc_info=True)
                    else:
                        logger.error("Failed to start OS inventory agent: %s", exc, exc_info=True)
                        raise
        return self._os_agent

    async def _ensure_software_agent(self, *, optional: bool = False) -> Optional[SoftwareInventoryAgent]:
        if self._software_agent is not None:
            return self._software_agent
        async with self._lock:
            if self._software_agent is None:
                try:
                    logger.info("Starting software inventory agent for in-process MCP fallback")
                    self._software_agent = SoftwareInventoryAgent()
                    self._last_initialization_error = None
                except Exception as exc:  # pragma: no cover - optional dependency issues
                    self._last_initialization_error = str(exc)
                    if optional:
                        logger.debug("Software inventory agent warm-up failed: %s", exc, exc_info=True)
                    else:
                        logger.error("Failed to start software inventory agent: %s", exc, exc_info=True)
                        raise
        return self._software_agent

    @staticmethod
    def _build_tool(name: str, description: str, parameters: Dict[str, Any], original_name: str) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
            "metadata": {
                "original_name": original_name,
                "source": "inventory",
            },
        }

    @staticmethod
    def _format_response(tool_name: str, payload: Dict[str, Any], success: bool) -> Dict[str, Any]:
        return {
            "success": success,
            "tool_name": tool_name,
            "content": [json.dumps(payload, ensure_ascii=False, indent=2)],
            "payload": payload,
            "is_error": not success,
        }

    async def _handle_os_inventory(self, requested_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            agent = await self._ensure_os_agent()
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": f"OS inventory agent unavailable: {exc}",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        if agent is None:
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": "OS inventory agent not available in this environment.",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        days = int(arguments.get("days", 90) or 90)
        limit_raw = arguments.get("limit", 2000)
        limit = None if limit_raw in (None, "all") else int(limit_raw)
        use_cache = bool(arguments.get("use_cache", True))
        result = await agent.get_os_inventory(days=days, limit=limit, use_cache=use_cache)
        success = bool(result.get("success"))
        payload = {
            "success": success,
            "requested": {"days": days, "limit": limit, "use_cache": use_cache},
            "data": result,
        }
        return self._format_response(requested_name, payload, success)

    async def _handle_os_summary(self, requested_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            agent = await self._ensure_os_agent()
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": f"OS inventory agent unavailable: {exc}",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        if agent is None:
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": "OS inventory agent not available in this environment.",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        days = int(arguments.get("days", 90) or 90)
        summary = await agent.get_os_summary(days=days)
        success = bool(summary.get("success", True))
        payload = {
            "success": success,
            "requested": {"days": days},
            "data": summary,
        }
        return self._format_response(requested_name, payload, success)

    async def _handle_software_inventory(self, requested_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            agent = await self._ensure_software_agent()
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": f"Software inventory agent unavailable: {exc}",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        if agent is None:
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": "Software inventory agent not available in this environment.",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        days = int(arguments.get("days", 90) or 90)
        limit_raw = arguments.get("limit", 10000)
        limit = None if limit_raw in (None, "all") else int(limit_raw)
        software_filter = arguments.get("software_filter")
        if isinstance(software_filter, str) and not software_filter.strip():
            software_filter = None
        use_cache = bool(arguments.get("use_cache", True))
        result = await agent.get_software_inventory(
            days=days,
            software_filter=software_filter,
            limit=limit,
            use_cache=use_cache,
        )
        success = bool(result.get("success"))
        payload = {
            "success": success,
            "requested": {
                "days": days,
                "limit": limit,
                "software_filter": software_filter,
                "use_cache": use_cache,
            },
            "data": result,
        }
        return self._format_response(requested_name, payload, success)


class InventoryMCPClient:
    """Wrapper around the inventory MCP server."""

    def __init__(self) -> None:
        self.session: Optional[ClientSessionType] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None
        self._use_fallback = False
        self._fallback_executor: Optional[InventoryFallbackExecutor] = None

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        if not _MCP_AVAILABLE:
            logger.info("MCP package not available; using in-process inventory tools")
            self._fallback_executor = InventoryFallbackExecutor()
            await self._fallback_executor.initialize()
            self.available_tools = self._fallback_executor.get_available_tools()
            self._use_fallback = True
            self._initialized = True
            return True

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "inventory_mcp_server.py"
        if not server_script.is_file():
            logger.error("Inventory MCP server script not found at %s", server_script)
            return await self._enable_fallback(reason="server script missing")

        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[2]
        existing_path = env.get("PYTHONPATH", "")
        path_segments = [str(repo_root)]
        if existing_path:
            path_segments.append(existing_path)
        env["PYTHONPATH"] = os.pathsep.join(path_segments)

        params = None
        if StdioServerParameters is not None:
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(server_script)],
                env=env,
            )
        else:  # pragma: no cover - defensive fallback
            logger.warning("StdioServerParameters unavailable; using in-process inventory tools")
            return await self._enable_fallback(reason="stdio parameters unavailable")

        try:
            self._stdio_context = stdio_client(params)
            self._read, self._write = await self._stdio_context.__aenter__()

            self._session_context = ClientSession(self._read, self._write)
            self.session = await self._session_context.__aenter__()
            await self.session.initialize()

            tools = await self.session.list_tools()
            self.available_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in tools.tools
            ]

            if not self.available_tools:
                logger.warning("Inventory MCP server reported zero tools; switching to in-process fallback")
                await self.cleanup()
                return await self._enable_fallback(reason="no tools registered")

            self._initialized = True
            logger.info(
                "Inventory MCP server initialized with %d tool(s): %s",
                len(self.available_tools),
                ", ".join(tool.get("function", {}).get("name", "<unknown>") for tool in self.available_tools),
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start inventory MCP server: %s", exc)
            await self.cleanup()
            return await self._enable_fallback(reason=str(exc))

    async def _enable_fallback(self, reason: str) -> bool:
        logger.info("Enabling in-process inventory tools fallback (%s)", reason)
        self._fallback_executor = InventoryFallbackExecutor()
        try:
            await self._fallback_executor.initialize()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Inventory fallback initialization failed: %s", exc)
            self._fallback_executor = None
            self.available_tools = []
            self._use_fallback = False
            self._initialized = False
            return False

        self.available_tools = self._fallback_executor.get_available_tools()
        self._use_fallback = True
        self._initialized = True
        logger.info(
            "Inventory MCP fallback enabled with tool(s): %s",
            ", ".join(tool.get("function", {}).get("name", "<unknown>") for tool in self.available_tools),
        )
        return True

    def is_initialized(self) -> bool:
        return self._initialized

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return self.available_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._initialized:
            raise RuntimeError("Inventory MCP client not initialized")

        if self._use_fallback:
            assert self._fallback_executor is not None
            return await self._fallback_executor.call_tool(tool_name, arguments)

        if not self.session:
            raise RuntimeError("Inventory MCP session not available")

        try:
            logger.info("Inventory MCP calling tool '%s'", tool_name)
            result = await self.session.call_tool(tool_name, arguments)
            raw_content: List[Any] = []
            if isinstance(result.content, list):
                for item in result.content:
                    if hasattr(item, "text"):
                        raw_content.append(item.text)
                    else:
                        raw_content.append(str(item))
            elif hasattr(result.content, "text"):
                raw_content.append(result.content.text)
            else:
                raw_content.append(str(result.content))

            parsed_payload: Optional[Dict[str, Any]] = None
            for entry in raw_content:
                if isinstance(entry, str):
                    try:
                        parsed_payload = json.loads(entry)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed_payload, dict):
                        break
                    parsed_payload = None

            success = not getattr(result, "isError", False)
            if parsed_payload is not None:
                success = success and parsed_payload.get("success", True)

            return {
                "success": success,
                "tool_name": tool_name,
                "content": raw_content,
                "payload": parsed_payload,
                "is_error": getattr(result, "isError", False),
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing inventory MCP tool '%s': %s", tool_name, exc)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }

    async def cleanup(self) -> None:
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
        finally:
            self._initialized = False
            self.available_tools = []
            self.session = None
            self._session_context = None
            self._stdio_context = None
            self._read = None
            self._write = None
            self._use_fallback = False
            self._fallback_executor = None


_inventory_client: Optional[InventoryMCPClient] = None


async def get_inventory_mcp_client() -> InventoryMCPClient:
    global _inventory_client
    if _inventory_client is None:
        client = InventoryMCPClient()
        if not await client.initialize():
            raise RuntimeError("Failed to initialize inventory MCP client")
        _inventory_client = client
    return _inventory_client


async def cleanup_inventory_mcp_client() -> None:
    global _inventory_client
    if _inventory_client:
        await _inventory_client.cleanup()
        _inventory_client = None
