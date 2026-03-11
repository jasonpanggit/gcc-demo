"""Client helper for the CVE MCP server."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .tool_registry import get_tool_registry

logger = logging.getLogger(__name__)


class CVEMCPDisabledError(RuntimeError):
    """Raised when the CVE MCP server is disabled by configuration."""


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_falsy(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off", "disable", "disabled"}


def _is_cve_mcp_disabled() -> bool:
    enabled_flag = os.getenv("CVE_MCP_ENABLED")
    if enabled_flag is not None:
        return _is_falsy(enabled_flag)
    disabled_flag = os.getenv("CVE_MCP_DISABLED")
    if disabled_flag is not None:
        return _is_truthy(disabled_flag)
    return False


class CVEMCPClient:
    """Wraps the CVE MCP server and exposes its tool set."""

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None

    async def initialize(self) -> bool:
        if self._initialized:
            return True

        if _is_cve_mcp_disabled():
            logger.info("CVE MCP server disabled via environment settings; skipping startup.")
            return False

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "cve_mcp_server.py"
        if not server_script.is_file():
            logger.error("CVE MCP server script not found at %s", server_script)
            return False

        params = StdioServerParameters(command=sys.executable, args=[str(server_script)], env=os.environ.copy())

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

            logger.info("Initialized CVE MCP server with %d tools", len(self.available_tools))
            self._initialized = True
            await self._register_with_registry()
            return True
        except Exception as exc:
            logger.error("Failed to start CVE MCP server: %s", exc)
            await self.cleanup()
            return False

    async def _register_with_registry(self) -> None:
        try:
            registry = get_tool_registry()
            await registry.register_server(label="cve", client=self, domain="security", priority=10, auto_discover=True)
            logger.debug("Registered CVE MCP client with tool registry")
        except ValueError as exc:
            if "already registered" in str(exc):
                logger.debug("CVE MCP client already registered with tool registry")
            else:
                raise
        except Exception as exc:
            logger.warning("Failed to register CVE MCP client with tool registry: %s", exc, exc_info=True)

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

    def is_initialized(self) -> bool:
        return self._initialized

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return self.available_tools

    async def close(self) -> None:
        await self.cleanup()

    async def aclose(self) -> None:
        await self.cleanup()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._initialized or not self.session:
            raise RuntimeError("CVE MCP client not initialized")

        try:
            logger.info("CVE MCP calling tool '%s' with arguments: %s", tool_name, json.dumps(arguments, default=str))
            result = await self.session.call_tool(tool_name, arguments)

            raw_content: List[Any] = []
            if isinstance(result.content, list):
                for item in result.content:
                    raw_content.append(item.text if hasattr(item, "text") else str(item))
            elif hasattr(result.content, "text"):
                raw_content.append(result.content.text)
            else:
                raw_content.append(str(result.content))

            parsed_payload: Optional[Dict[str, Any]] = None
            for entry in raw_content:
                if not isinstance(entry, str):
                    continue
                try:
                    candidate = json.loads(entry)
                    if isinstance(candidate, dict):
                        parsed_payload = candidate
                        break
                except json.JSONDecodeError:
                    continue

            result_is_error = getattr(result, "isError", False)
            success = parsed_payload.get("success", not result_is_error) if parsed_payload and "success" in parsed_payload else not result_is_error

            return {
                "success": success,
                "tool_name": tool_name,
                "content": raw_content,
                "parsed": parsed_payload,
                "is_error": result_is_error or not success,
            }
        except Exception as exc:
            logger.error("Error executing CVE tool '%s': %s", tool_name, exc)
            return {"success": False, "tool_name": tool_name, "error": str(exc), "is_error": True}


_cve_mcp_client: Optional[CVEMCPClient] = None


async def get_cve_mcp_client(config: Optional[Dict[str, Any]] = None) -> CVEMCPClient:
    """Get or create the global CVE MCP client instance."""
    global _cve_mcp_client
    if _cve_mcp_client is None:
        if _is_cve_mcp_disabled():
            raise CVEMCPDisabledError("CVE MCP server is disabled. Set CVE_MCP_ENABLED=true to enable.")
        _cve_mcp_client = CVEMCPClient()
        if not await _cve_mcp_client.initialize():
            raise RuntimeError("Failed to initialize CVE MCP client")
    return _cve_mcp_client


async def cleanup_cve_mcp_client() -> None:
    global _cve_mcp_client
    if _cve_mcp_client:
        await _cve_mcp_client.cleanup()
        _cve_mcp_client = None
