"""Azure Monitor Community MCP Client for workbooks, alerts, and queries."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class WorkbookMCPClient:
    """Client for interacting with Azure Monitor Community resources (workbooks, alerts, queries) MCP server."""

    def __init__(self) -> None:
        self.available_tools: List[Dict[str, Any]] = []
        self._stdio_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self.session: Optional[ClientSession] = None
        self._read: Optional[Any] = None
        self._write: Optional[Any] = None

    async def initialize(self) -> None:
        """Start the MCP server process using the MCP SDK."""
        server_script = Path(__file__).parent.parent / "mcp_servers" / "monitor_mcp_server.py"
        
        if not server_script.exists():
            raise RuntimeError(f"Azure Monitor Community MCP server script not found: {server_script}")

        logger.info("Starting Azure Monitor Community MCP server from %s", server_script)

        # Prepare server parameters
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd())

        params = StdioServerParameters(
            command="python3",
            args=[str(server_script)],
            env=env,
        )

        try:
            # Create stdio client context
            self._stdio_context = stdio_client(params)
            self._read, self._write = await self._stdio_context.__aenter__()

            # Create session
            self._session_context = ClientSession(self._read, self._write)
            self.session = await self._session_context.__aenter__()
            await self.session.initialize()

            # List available tools
            tools = await self.session.list_tools()
            self.available_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in tools.tools
            ]

            if not self.available_tools:
                logger.warning("No tools returned from Azure Monitor Community MCP server")
            else:
                logger.info("Azure Monitor Community MCP server initialized with %d tools", len(self.available_tools))

        except Exception as exc:
            logger.error("Failed to start Azure Monitor Community MCP server: %s", exc)
            await self.cleanup()
            raise

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Return available tools in OpenAI format."""
        return self.available_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool on the MCP server."""
        if not self.session:
            return {
                "success": False,
                "error": "MCP session not initialized",
            }

        try:
            logger.debug("Calling tool %s with arguments: %s", tool_name, arguments)
            result = await self.session.call_tool(tool_name, arguments)
            logger.debug("Tool %s returned result type: %s", tool_name, type(result))

            # Convert MCP result format to our expected format
            if result and hasattr(result, "content"):
                # Extract text content from MCP response
                content_text = ""
                if result.content:
                    for content_item in result.content:
                        if hasattr(content_item, "text"):
                            content_text += content_item.text
                
                logger.debug("Tool %s returned content length: %d", tool_name, len(content_text))

                # Try to parse as JSON
                if content_text.strip():
                    try:
                        parsed_content = json.loads(content_text)
                        logger.debug("Tool %s parsed content successfully", tool_name)
                        # If it's a dict, return it directly (it should have success, etc.)
                        if isinstance(parsed_content, dict):
                            return parsed_content
                    except json.JSONDecodeError as jde:
                        # Not JSON, return as text result
                        logger.warning("Tool %s returned non-JSON content: %s", tool_name, jde)
                        return {
                            "success": True,
                            "result": content_text,
                        }

                # Return as success with text content
                return {
                    "success": True,
                    "result": content_text,
                }

            return {
                "success": False,
                "error": "No result from MCP server",
            }

        except Exception as exc:
            logger.error("Error calling tool %s with arguments %s: %s", 
                        tool_name, arguments, exc, exc_info=True)
            # Include more details in the error response
            error_details = {
                "success": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "tool_name": tool_name,
                "arguments": arguments,
            }
            return error_details

    async def cleanup(self) -> None:
        """Cleanup MCP server resources."""
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
                self._session_context = None
                self.session = None

            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
                self._stdio_context = None
                self._read = None
                self._write = None

            logger.debug("Azure Monitor Community MCP client cleaned up")
        except Exception as exc:
            logger.warning("Error during MCP client cleanup: %s", exc)

    async def aclose(self) -> None:
        """Cleanup the MCP server process (alias for cleanup)."""
        await self.cleanup()


async def get_workbook_mcp_client() -> WorkbookMCPClient:
    """Factory function to create and initialize a Workbook MCP client."""
    client = WorkbookMCPClient()
    await client.initialize()
    return client

