"""Client helper for the Azure CLI execution MCP server."""
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

_log_level_name = os.getenv("AZURE_CLI_EXECUTOR_LOG_LEVEL")
if _log_level_name:
    try:
        logger.setLevel(getattr(logging, _log_level_name.upper()))
    except AttributeError:
        logger.warning(
            "Invalid AZURE_CLI_EXECUTOR_LOG_LEVEL '%s'. Falling back to INFO.",
            _log_level_name,
        )
        logger.setLevel(logging.INFO)


class AzureCliExecutorDisabledError(RuntimeError):
    """Raised when the Azure CLI executor is explicitly disabled via configuration."""


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_falsy(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off", "disable", "disabled"}


def _is_cli_executor_disabled() -> bool:
    """Determine whether the Azure CLI executor should be disabled based on environment variables."""

    enabled_flag = os.getenv("AZURE_CLI_EXECUTOR_ENABLED")
    if enabled_flag is not None:
        # Any explicit falsey value disables the executor; otherwise default to enabled.
        return _is_falsy(enabled_flag)

    disabled_flag = os.getenv("AZURE_CLI_EXECUTOR_DISABLED")
    if disabled_flag is not None:
        return _is_truthy(disabled_flag)

    return False


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

        if _is_cli_executor_disabled():
            logger.info("Azure CLI executor MCP server disabled via environment settings; skipping startup.")
            return False

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
            logger.info("Azure CLI executor calling tool '%s' with arguments: %s", tool_name, json.dumps(arguments, indent=2, default=str))
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
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and "exit_code" in candidate:
                    parsed_payload = candidate
                    break

            exit_code = parsed_payload.get("exit_code") if parsed_payload else None
            stderr_output = parsed_payload.get("stderr") if parsed_payload else None
            stdout_output = parsed_payload.get("stdout") if parsed_payload else None

            result_is_error = getattr(result, "isError", False)
            logger.info(
                "Azure CLI executor raw content: %s",
                json.dumps(raw_content, indent=2, ensure_ascii=False, default=str),
            )

            logger.info(
                "Parsed CLI execution payload: exit_code=%s, stdout=%s, stderr=%s, result_is_error=%s",
                exit_code,
                (stdout_output or "<none>")[:500],
                (stderr_output or "<none>")[:500],
                result_is_error,
            )

            if exit_code is None:
                success = not result_is_error
            else:
                success = exit_code == 0 and not result_is_error

            if success:
                logger.info(
                    "Azure CLI command '%s' succeeded with exit code 0",
                    arguments.get("command") if isinstance(arguments, dict) else tool_name,
                )
            else:
                logger.warning(
                    "Azure CLI command '%s' failed (exit code=%s, stderr=%s)",
                    arguments.get("command") if isinstance(arguments, dict) else tool_name,
                    exit_code,
                    (stderr_output or "<no stderr>")[:500],
                )

            logger.info(
                "Computed CLI execution success=%s for command '%s'", success, arguments.get("command") if isinstance(arguments, dict) else tool_name
            )

            return {
                "success": success,
                "tool_name": tool_name,
                "content": raw_content,
                "is_error": result_is_error or not success,
                "exit_code": exit_code,
                "stdout": stdout_output,
                "stderr": stderr_output,
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
        if _is_cli_executor_disabled():
            raise AzureCliExecutorDisabledError(
                "Azure CLI executor MCP server is disabled. Set AZURE_CLI_EXECUTOR_ENABLED=true "
                "or unset AZURE_CLI_EXECUTOR_DISABLED to enable it."
            )
        _cli_executor_client = AzureCliExecutorClient()
        if not await _cli_executor_client.initialize():
            raise RuntimeError("Failed to initialize Azure CLI executor MCP client")
    return _cli_executor_client


async def cleanup_cli_executor_client() -> None:
    global _cli_executor_client
    if _cli_executor_client:
        await _cli_executor_client.cleanup()
        _cli_executor_client = None
