"""Client helper for the operating system EOL MCP server."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

try:  # pragma: no cover - optional dependency
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _MCP_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False

try:  # Prefer absolute import when the package root is available
    from app.agentic.eol.agents.eol_orchestrator import EOLOrchestratorAgent
except ModuleNotFoundError:  # pragma: no cover - support execution without top-level package
    from agents.eol_orchestrator import EOLOrchestratorAgent  # type: ignore[import-not-found]

if TYPE_CHECKING:  # pragma: no cover - typing support only
    from mcp import ClientSession as ClientSessionType  # type: ignore[import-not-found]
else:  # pragma: no cover - runtime when MCP is optional
    ClientSessionType = Any  # type: ignore[misc]

logger = logging.getLogger(__name__)


@dataclass
class _BulkOSEntry:
    name: str
    version: Optional[str]
    alias: Optional[str] = None

    @classmethod
    def from_payload(cls, item: Dict[str, Any]) -> "_BulkOSEntry":
        name_value = (
            item.get("os_name")
            or item.get("name")
            or item.get("software")
            or item.get("label")
            or ""
        )
        version_value = item.get("os_version") or item.get("version")
        alias_value = item.get("alias") or item.get("id") or item.get("key")

        name = str(name_value or "").strip()
        version = str(version_value).strip() if version_value is not None else None
        alias = str(alias_value).strip() if alias_value is not None else None
        return cls(name=name, version=version or None, alias=alias or None)

    def is_valid(self) -> bool:
        return bool(self.name)


class OSEOLFallbackExecutor:
    """Executes OS EOL lookups locally when the MCP server is unavailable."""

    def __init__(self) -> None:
        self._orchestrator: Optional[EOLOrchestratorAgent] = None
        self._lock = asyncio.Lock()
        self._last_initialization_error: Optional[str] = None
        self._tool_catalog: List[Dict[str, Any]] = [
            self._build_tool(
                name="os_eol_lookup",
                description="Retrieve end-of-life details for a single operating system.",
                parameters={
                    "type": "object",
                    "properties": {
                        "os_name": {
                            "type": "string",
                            "description": "Operating system name such as 'Windows Server 2016'.",
                        },
                        "os_version": {
                            "type": ["string", "null"],
                            "description": "Optional operating system version string.",
                            "default": None,
                        },
                    },
                    "required": ["os_name"],
                    "additionalProperties": False,
                },
                original_name="os_eol_lookup",
            ),
            self._build_tool(
                name="os_eol_bulk_lookup",
                description="Perform EOL lookup for multiple operating systems in a single call.",
                parameters={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of operating system descriptors.",
                        },
                        "concurrency": {
                            "type": "integer",
                            "description": "Maximum concurrent lookups (default 5, max 10).",
                            "default": 5,
                        },
                    },
                    "required": ["items"],
                    "additionalProperties": False,
                },
                original_name="os_eol_bulk_lookup",
            ),
        ]
        self._handler_map = {
            "os_eol_lookup": self._handle_lookup,
            "os_eol_bulk_lookup": self._handle_bulk_lookup,
        }

    async def initialize(self) -> bool:
        orchestrator = await self._ensure_orchestrator(optional=True)
        if orchestrator is None and self._last_initialization_error:
            logger.warning(
                "OS EOL fallback will initialize lazily due to: %s",
                self._last_initialization_error,
            )
        return True

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return deepcopy(self._tool_catalog)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handler_map.get(tool_name)
        if handler is None:
            return self._format_response(
                tool_name,
                payload={"success": False, "error": f"Unknown OS EOL tool: {tool_name}"},
                success=False,
            )
        return await handler(tool_name, arguments or {})

    async def aclose(self) -> None:
        if self._orchestrator is None:
            return
        try:
            await self._orchestrator.aclose()
        except Exception:  # pragma: no cover - defensive shutdown
            logger.debug("Failed to close fallback EOL orchestrator", exc_info=True)
        finally:
            self._orchestrator = None
            self._last_initialization_error = None

    async def _ensure_orchestrator(self, *, optional: bool = False) -> Optional[EOLOrchestratorAgent]:
        if self._orchestrator is not None:
            return self._orchestrator
        async with self._lock:
            if self._orchestrator is None:
                try:
                    logger.info("Starting EOL orchestrator for in-process MCP fallback")
                    self._orchestrator = EOLOrchestratorAgent()
                    self._last_initialization_error = None
                except Exception as exc:  # pragma: no cover - optional dependency issues
                    self._last_initialization_error = str(exc)
                    if optional:
                        logger.debug("OS EOL orchestrator warm-up failed: %s", exc, exc_info=True)
                    else:
                        logger.error("Failed to start EOL orchestrator: %s", exc, exc_info=True)
                        raise
        return self._orchestrator

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
                "source": "os_eol",
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

    async def _handle_lookup(self, requested_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            orchestrator = await self._ensure_orchestrator()
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": f"OS EOL orchestrator unavailable: {exc}",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        if orchestrator is None:
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": "OS EOL orchestrator not available in this environment.",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        os_name_raw = (
            arguments.get("os_name")
            or arguments.get("name")
            or arguments.get("software")
            or ""
        )
        os_name = str(os_name_raw or "").strip()
        if not os_name:
            return self._format_response(
                requested_name,
                payload={"success": False, "error": "Missing operating system name."},
                success=False,
            )

        os_version_raw = arguments.get("os_version") or arguments.get("version")
        os_version = str(os_version_raw).strip() if os_version_raw is not None else None

        result = await orchestrator.get_autonomous_eol_data(os_name, os_version, item_type="os")
        payload = {
            "success": bool(result.get("success")),
            "requested": {"os_name": os_name, "os_version": os_version},
            "result": result,
        }
        return self._format_response(requested_name, payload, bool(payload["success"]))

    async def _handle_bulk_lookup(self, requested_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            orchestrator = await self._ensure_orchestrator()
        except Exception as exc:  # pragma: no cover - defensive guard
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": f"OS EOL orchestrator unavailable: {exc}",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        if orchestrator is None:
            return self._format_response(
                requested_name,
                payload={
                    "success": False,
                    "error": "OS EOL orchestrator not available in this environment.",
                    "last_error": self._last_initialization_error,
                },
                success=False,
            )
        items = arguments.get("items")
        if not isinstance(items, list) or not items:
            return self._format_response(
                requested_name,
                payload={"success": False, "error": "No OS entries provided.", "results": []},
                success=False,
            )

        concurrency_raw = arguments.get("concurrency", 5)
        try:
            concurrency = int(concurrency_raw)
        except (TypeError, ValueError):
            concurrency = 5
        concurrency = max(1, min(concurrency, 10))

        semaphore = asyncio.Semaphore(concurrency)
        results: List[Dict[str, Any]] = []

        async def _lookup(entry: _BulkOSEntry) -> None:
            if not entry.is_valid():
                results.append(
                    {
                        "success": False,
                        "requested": {"os_name": entry.name, "os_version": entry.version},
                        "error": "Missing operating system name.",
                        "alias": entry.alias,
                    }
                )
                return
            async with semaphore:
                try:
                    lookup = await orchestrator.get_autonomous_eol_data(entry.name, entry.version, item_type="os")
                except Exception as exc:  # pragma: no cover - defensive fallback
                    logger.exception("Bulk OS EOL lookup failed for %s %s", entry.name, entry.version or "")
                    results.append(
                        {
                            "success": False,
                            "requested": {"os_name": entry.name, "os_version": entry.version},
                            "error": str(exc),
                            "alias": entry.alias,
                        }
                    )
                    return

                results.append(
                    {
                        "success": bool(lookup.get("success")),
                        "requested": {"os_name": entry.name, "os_version": entry.version},
                        "result": lookup,
                        "alias": entry.alias,
                    }
                )

        tasks: List[asyncio.Task[Any]] = []
        for raw in items:
            try:
                entry = _BulkOSEntry.from_payload(raw or {})
            except Exception as exc:  # pragma: no cover - defensive parsing
                results.append(
                    {
                        "success": False,
                        "requested": {"os_name": None, "os_version": None},
                        "error": f"Invalid item format: {exc}",
                    }
                )
                continue
            tasks.append(asyncio.create_task(_lookup(entry)))

        if tasks:
            await asyncio.gather(*tasks)

        success = any(item.get("success") for item in results)
        payload = {
            "success": success,
            "requested": {"count": len(items), "concurrency": concurrency},
            "results": results,
            "count": len(results),
        }
        return self._format_response(requested_name, payload, success)


class OSEolMCPClient:
    """Wrapper around the OS EOL MCP server with in-process fallback."""

    def __init__(self) -> None:
        self.session: Optional[ClientSessionType] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None
        self._use_fallback = False
        self._fallback_executor: Optional[OSEOLFallbackExecutor] = None

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        if not _MCP_AVAILABLE:
            logger.info("MCP package not available; using in-process OS EOL tools")
            return await self._enable_fallback(reason="mcp package unavailable")

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "os_eol_mcp_server.py"
        if not server_script.is_file():
            logger.error("OS EOL MCP server script not found at %s", server_script)
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
            logger.warning("StdioServerParameters unavailable; using in-process OS EOL tools")
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
                    "metadata": {
                        "original_name": tool.name,
                        "source": "os_eol",
                    },
                }
                for tool in tools.tools
            ]

            if not self.available_tools:
                logger.warning("OS EOL MCP server reported zero tools; switching to in-process fallback")
                await self.cleanup()
                return await self._enable_fallback(reason="no tools registered")

            self._initialized = True
            logger.info(
                "OS EOL MCP server initialized with %d tool(s): %s",
                len(self.available_tools),
                ", ".join(tool.get("function", {}).get("name", "<unknown>") for tool in self.available_tools),
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start OS EOL MCP server: %s", exc)
            await self.cleanup()
            return await self._enable_fallback(reason=str(exc))

    async def _enable_fallback(self, reason: str) -> bool:
        logger.info("Enabling in-process OS EOL tools fallback (%s)", reason)
        executor = OSEOLFallbackExecutor()
        try:
            await executor.initialize()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("OS EOL fallback initialization failed: %s", exc)
            await executor.aclose()
            self.available_tools = []
            self._fallback_executor = None
            self._use_fallback = False
            self._initialized = False
            return False

        self._fallback_executor = executor
        self.available_tools = executor.get_available_tools()
        self._use_fallback = True
        self._initialized = True
        logger.info(
            "OS EOL MCP fallback enabled with tool(s): %s",
            ", ".join(tool.get("function", {}).get("name", "<unknown>") for tool in self.available_tools),
        )
        return True

    def is_initialized(self) -> bool:
        return self._initialized

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return self.available_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._initialized:
            raise RuntimeError("OS EOL MCP client not initialized")

        if self._use_fallback:
            assert self._fallback_executor is not None
            return await self._fallback_executor.call_tool(tool_name, arguments)

        if not self.session:
            raise RuntimeError("OS EOL MCP session not available")

        try:
            logger.info("OS EOL MCP calling tool '%s'", tool_name)
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
            logger.error("Error executing OS EOL MCP tool '%s': %s", tool_name, exc)
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
            if self._fallback_executor:
                await self._fallback_executor.aclose()
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


_os_eol_client: Optional[OSEolMCPClient] = None


async def get_os_eol_mcp_client() -> OSEolMCPClient:
    global _os_eol_client
    if _os_eol_client is None:
        client = OSEolMCPClient()
        if not await client.initialize():
            raise RuntimeError("Failed to initialize OS EOL MCP client")
        _os_eol_client = client
    return _os_eol_client


async def cleanup_os_eol_mcp_client() -> None:
    global _os_eol_client
    if _os_eol_client:
        await _os_eol_client.cleanup()
        _os_eol_client = None
