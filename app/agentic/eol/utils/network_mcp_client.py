"""Client helper for the Azure Network MCP server."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

_log_level_name = os.getenv("NETWORK_MCP_LOG_LEVEL")
if _log_level_name:
    try:
        logger.setLevel(getattr(logging, _log_level_name.upper()))
    except AttributeError:
        logger.warning(
            "Invalid NETWORK_MCP_LOG_LEVEL '%s'. Falling back to INFO.",
            _log_level_name,
        )
        logger.setLevel(logging.INFO)


class NetworkMCPDisabledError(RuntimeError):
    """Raised when the Network MCP server is explicitly disabled via configuration."""


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_falsy(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off", "disable", "disabled"}


def _is_network_mcp_disabled() -> bool:
    """Determine whether the Network MCP server should be disabled."""
    enabled_flag = os.getenv("NETWORK_MCP_ENABLED")
    if enabled_flag is not None:
        return _is_falsy(enabled_flag)

    disabled_flag = os.getenv("NETWORK_MCP_DISABLED")
    if disabled_flag is not None:
        return _is_truthy(disabled_flag)

    return False


class NetworkMCPClient:
    """Wraps the Azure Network MCP server and exposes its tool set."""

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None

    async def initialize(self) -> bool:
        """Start the Python-based Network MCP server and cache available tools."""
        if self._initialized:
            return True

        if _is_network_mcp_disabled():
            logger.info("Network MCP server disabled via environment settings; skipping startup.")
            return False

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "network_mcp_server.py"
        if not server_script.is_file():
            logger.error("Network MCP server script not found at %s", server_script)
            return False

        env = os.environ.copy()

        if "SUBSCRIPTION_ID" not in env and "AZURE_SUBSCRIPTION_ID" not in env:
            logger.warning(
                "SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID not set - "
                "Network MCP server may not function properly"
            )

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(server_script)],
            env=env,
        )

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

            logger.info("✓ Network MCP server initialized with %d tools", len(self.available_tools))
            self._initialized = True
            return True

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start Network MCP server: %s", exc)
            await self.cleanup()
            return False

    async def cleanup(self) -> None:
        """Shut down the Network MCP server."""
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
        """Alias for cleanup() — used by orchestrator's _maybe_aclose."""
        await self.cleanup()

    async def aclose(self) -> None:
        """Alias for cleanup() — used by orchestrator's _maybe_aclose."""
        await self.cleanup()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a network tool and return structured result."""
        if not self._initialized or not self.session:
            raise RuntimeError("Network MCP client not initialized")

        try:
            logger.info(
                "Network MCP calling tool '%s' with arguments: %s",
                tool_name,
                json.dumps(arguments, indent=2, default=str),
            )
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

            if parsed_payload and "success" in parsed_payload:
                success = parsed_payload["success"]
            else:
                success = not result_is_error

            logger.info("Network tool '%s' completed with success=%s", tool_name, success)

            return {
                "success": success,
                "tool_name": tool_name,
                "content": raw_content,
                "parsed": parsed_payload,
                "is_error": result_is_error or not success,
            }

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing Network tool '%s': %s", tool_name, exc)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }


_network_mcp_client: Optional[NetworkMCPClient] = None


async def get_network_mcp_client(
    config: Optional[Dict[str, Any]] = None,
) -> NetworkMCPClient:
    """Get or create the global Network MCP client instance.

    Args:
        config: Optional configuration dict (currently unused, for future extensibility)

    Returns:
        Initialized NetworkMCPClient instance

    Raises:
        NetworkMCPDisabledError: If Network MCP is disabled via environment
        RuntimeError: If initialization fails
    """
    global _network_mcp_client
    if _network_mcp_client is None:
        if _is_network_mcp_disabled():
            raise NetworkMCPDisabledError(
                "Network MCP server is disabled. Set NETWORK_MCP_ENABLED=true "
                "or unset NETWORK_MCP_DISABLED to enable it."
            )
        _network_mcp_client = NetworkMCPClient()
        if not await _network_mcp_client.initialize():
            raise RuntimeError("Failed to initialize Network MCP client")
    return _network_mcp_client


async def cleanup_network_mcp_client() -> None:
    """Clean up the global Network MCP client instance."""
    global _network_mcp_client
    if _network_mcp_client:
        await _network_mcp_client.cleanup()
        _network_mcp_client = None
