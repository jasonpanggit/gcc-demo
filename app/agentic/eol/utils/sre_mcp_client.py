"""Client helper for the Azure SRE MCP server."""
from __future__ import annotations

import logging
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

_log_level_name = os.getenv("SRE_MCP_LOG_LEVEL")
if _log_level_name:
    try:
        logger.setLevel(getattr(logging, _log_level_name.upper()))
    except AttributeError:
        logger.warning(
            "Invalid SRE_MCP_LOG_LEVEL '%s'. Falling back to INFO.",
            _log_level_name,
        )
        logger.setLevel(logging.INFO)


class SREMCPDisabledError(RuntimeError):
    """Raised when the SRE MCP server is explicitly disabled via configuration."""


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_falsy(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off", "disable", "disabled"}


def _is_sre_mcp_disabled() -> bool:
    """Determine whether the SRE MCP server should be disabled based on environment variables."""

    enabled_flag = os.getenv("SRE_ENABLED")
    if enabled_flag is not None:
        # Any explicit falsey value disables the server; otherwise default to enabled.
        return _is_falsy(enabled_flag)

    disabled_flag = os.getenv("SRE_DISABLED")
    if disabled_flag is not None:
        return _is_truthy(disabled_flag)

    return False


class SREMCPClient:
    """Wraps the Azure SRE MCP server and exposes its tool set."""

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None

    async def initialize(self) -> bool:
        """Start the Python-based SRE MCP server and cache available tools."""
        if self._initialized:
            return True

        if _is_sre_mcp_disabled():
            logger.info("SRE MCP server disabled via environment settings; skipping startup.")
            return False

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "sre_mcp_server.py"
        if not server_script.is_file():
            logger.error("SRE MCP server script not found at %s", server_script)
            return False

        # Pass through all Azure-related environment variables
        env = os.environ.copy()

        # Ensure required Azure env vars are present
        required_env_vars = [
            "SUBSCRIPTION_ID",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_TENANT_ID",
            "TEAMS_WEBHOOK_URL",
        ]

        missing_vars = []
        for var in required_env_vars:
            if var not in env and not any(alt in env for alt in [v for v in required_env_vars if v != var]):
                missing_vars.append(var)

        # Only SUBSCRIPTION_ID (or AZURE_SUBSCRIPTION_ID) is truly required
        if "SUBSCRIPTION_ID" not in env and "AZURE_SUBSCRIPTION_ID" not in env:
            logger.warning("SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID not set - SRE MCP server may not function properly")

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

            logger.info("✓ SRE MCP server initialized with %d tools", len(self.available_tools))
            self._initialized = True
            return True

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start SRE MCP server: %s", exc)
            await self.cleanup()
            return False

    async def cleanup(self) -> None:
        """Shut down the SRE MCP server."""
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

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an SRE tool and return structured result."""
        if not self._initialized or not self.session:
            raise RuntimeError("SRE MCP client not initialized")

        try:
            logger.info("SRE MCP calling tool '%s' with arguments: %s", tool_name, json.dumps(arguments, indent=2, default=str))
            result = await self.session.call_tool(tool_name, arguments)

            # Extract text content from result
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

            # Try to parse as JSON
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

            # Check if result indicates error
            result_is_error = getattr(result, "isError", False)

            # Determine success from parsed payload or result error flag
            if parsed_payload and "success" in parsed_payload:
                success = parsed_payload["success"]
            else:
                success = not result_is_error

            logger.info(
                "SRE tool '%s' completed with success=%s",
                tool_name,
                success,
            )

            return {
                "success": success,
                "tool_name": tool_name,
                "content": raw_content,
                "parsed": parsed_payload,
                "is_error": result_is_error or not success,
            }

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing SRE tool '%s': %s", tool_name, exc)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }


_sre_mcp_client: Optional[SREMCPClient] = None


async def get_sre_mcp_client(config: Optional[Dict[str, Any]] = None) -> SREMCPClient:
    """
    Get or create the global SRE MCP client instance.

    Args:
        config: Optional configuration dict (currently unused, for future extensibility)

    Returns:
        Initialized SREMCPClient instance

    Raises:
        SREMCPDisabledError: If SRE MCP is disabled via environment
        RuntimeError: If initialization fails
    """
    global _sre_mcp_client
    if _sre_mcp_client is None:
        if _is_sre_mcp_disabled():
            raise SREMCPDisabledError(
                "SRE MCP server is disabled. Set SRE_ENABLED=true "
                "or unset SRE_DISABLED to enable it."
            )
        _sre_mcp_client = SREMCPClient()
        if not await _sre_mcp_client.initialize():
            raise RuntimeError("Failed to initialize SRE MCP client")
    return _sre_mcp_client


async def cleanup_sre_mcp_client() -> None:
    """Clean up the global SRE MCP client instance."""
    global _sre_mcp_client
    if _sre_mcp_client:
        await _sre_mcp_client.cleanup()
        _sre_mcp_client = None
