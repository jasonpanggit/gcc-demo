"""Client helper for the Azure CLI execution MCP server."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class AzureCliExecutorClient:
    """Wraps the custom Azure CLI MCP server and exposes its tool set."""

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None

    async def initialize(self) -> bool:
        """Start the Python-based Azure CLI MCP server and cache available tools."""
        if self._initialized:
            return True

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "azure_cli_executor_server.py"
        if not server_script.is_file():
            logger.error("Azure CLI executor server script not found at %s", server_script)
            return False

        env = os.environ.copy()

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

            logger.info("Azure CLI executor MCP server initialized with %d tools", len(self.available_tools))
            self._initialized = True
            return True

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start Azure CLI executor MCP server: %s", exc)
            await self.cleanup()
            return False

    async def cleanup(self) -> None:
        """Shut down the CLI MCP server."""
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
        if not self._initialized or not self.session:
            raise RuntimeError("Azure CLI executor client not initialized")

        try:
            result = await self.session.call_tool(tool_name, arguments)
            content: List[Any] = []
            if isinstance(result.content, list):
                for item in result.content:
                    if hasattr(item, "text"):
                        content.append(item.text)
                    else:
                        content.append(str(item))
            elif hasattr(result.content, "text"):
                content.append(result.content.text)
            else:
                content.append(str(result.content))

            return {
                "success": True,
                "tool_name": tool_name,
                "content": content,
                "is_error": getattr(result, "isError", False),
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error executing Azure CLI tool '%s': %s", tool_name, exc)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }


_cli_executor_client: Optional[AzureCliExecutorClient] = None


async def get_cli_executor_client() -> AzureCliExecutorClient:
    global _cli_executor_client
    if _cli_executor_client is None:
        _cli_executor_client = AzureCliExecutorClient()
        if not await _cli_executor_client.initialize():
            raise RuntimeError("Failed to initialize Azure CLI executor MCP client")
    return _cli_executor_client


async def cleanup_cli_executor_client() -> None:
    global _cli_executor_client
    if _cli_executor_client:
        await _cli_executor_client.cleanup()
        _cli_executor_client = None
