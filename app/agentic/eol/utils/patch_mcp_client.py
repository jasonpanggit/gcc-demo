"""Client helper for the Azure Patch Management MCP server."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

_log_level_name = os.getenv("PATCH_MCP_LOG_LEVEL")
if _log_level_name:
    try:
        logger.setLevel(getattr(logging, _log_level_name.upper()))
    except AttributeError:
        logger.warning(
            "Invalid PATCH_MCP_LOG_LEVEL '%s'. Falling back to INFO.",
            _log_level_name,
        )
        logger.setLevel(logging.INFO)


class PatchMCPDisabledError(RuntimeError):
    """Raised when the Patch MCP server is explicitly disabled via configuration."""


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_falsy(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off", "disable", "disabled"}


def _is_patch_mcp_disabled() -> bool:
    """Determine whether the Patch MCP server should be disabled based on environment variables."""

    enabled_flag = os.getenv("PATCH_ENABLED")
    if enabled_flag is not None:
        return _is_falsy(enabled_flag)

    disabled_flag = os.getenv("PATCH_DISABLED")
    if disabled_flag is not None:
        return _is_truthy(disabled_flag)

    return False


class PatchMCPClient:
    """Wraps the Azure Patch Management MCP server and exposes its tool set."""

    def __init__(self) -> None:
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self._initialized = False
        self._stdio_context = None
        self._session_context = None
        self._read = None
        self._write = None

    async def initialize(self) -> bool:
        """Start the Python-based Patch MCP server and cache available tools."""
        if self._initialized:
            return True

        if _is_patch_mcp_disabled():
            logger.info("Patch MCP server disabled via environment settings; skipping startup.")
            return False

        server_script = Path(__file__).resolve().parent.parent / "mcp_servers" / "patch_mcp_server.py"
        if not server_script.is_file():
            logger.error("Patch MCP server script not found at %s", server_script)
            return False

        # Pass through all Azure-related environment variables
        env = os.environ.copy()

        # Ensure required Azure env vars are present
        if "SUBSCRIPTION_ID" not in env and "AZURE_SUBSCRIPTION_ID" not in env:
            logger.warning("SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID not set - Patch MCP server may not function properly")

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

            logger.info("✓ Patch MCP server initialized with %d tools", len(self.available_tools))
            self._initialized = True
            return True

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to start Patch MCP server: %s", exc)
            await self.cleanup()
            return False

    async def cleanup(self) -> None:
        """Shut down the Patch MCP server."""
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

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke an MCP tool by name and return the result."""
        if not self.session:
            raise RuntimeError("Patch MCP client not initialized")

        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            if not result or not result.content:
                return {"success": False, "error": "Empty response from tool"}

            # Extract text content from MCP response
            if isinstance(result.content, list) and len(result.content) > 0:
                import json
                content_item = result.content[0]
                if hasattr(content_item, 'text'):
                    try:
                        return json.loads(content_item.text)
                    except json.JSONDecodeError:
                        return {"success": True, "data": content_item.text}

            return {"success": False, "error": "Unexpected response format"}

        except Exception as exc:
            logger.error("Patch MCP tool %s failed: %s", tool_name, exc)
            return {"success": False, "error": str(exc)}

    # ---------------------------------------------------------------------------
    # Tool wrapper methods
    # ---------------------------------------------------------------------------

    async def list_azure_vms(
        self,
        subscription_id: str,
        resource_group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all Azure VMs and Arc-enabled servers in a subscription."""
        return await self.call_tool(
            "list_azure_vms",
            {
                "subscription_id": subscription_id,
                "resource_group": resource_group,
            },
        )

    async def query_patch_assessments(
        self,
        subscription_id: str,
        machine_name: Optional[str] = None,
        vm_type: str = "arc",
    ) -> Dict[str, Any]:
        """Query Azure Resource Graph for historical patch assessment data."""
        return await self.call_tool(
            "query_patch_assessments",
            {
                "subscription_id": subscription_id,
                "machine_name": machine_name,
                "vm_type": vm_type,
            },
        )

    async def assess_vm_patches(
        self,
        machine_name: str,
        subscription_id: str,
        resource_group: str,
        vm_type: str = "arc",
        resource_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a live patch assessment on an Azure VM or Arc server."""
        return await self.call_tool(
            "assess_vm_patches",
            {
                "machine_name": machine_name,
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "vm_type": vm_type,
                "resource_id": resource_id,
            },
        )

    async def get_assessment_result(
        self,
        machine_name: str,
        subscription_id: str,
        vm_type: str = "arc",
    ) -> Dict[str, Any]:
        """Fetch the latest assessment result for a single machine from Azure Resource Graph."""
        return await self.call_tool(
            "get_assessment_result",
            {
                "machine_name": machine_name,
                "subscription_id": subscription_id,
                "vm_type": vm_type,
            },
        )

    async def install_vm_patches(
        self,
        machine_name: str,
        subscription_id: str,
        resource_group: str,
        classifications: List[str] = None,
        vm_type: str = "arc",
        resource_id: Optional[str] = None,
        kb_numbers_to_include: List[str] = None,
        kb_numbers_to_exclude: List[str] = None,
        reboot_setting: str = "IfRequired",
        maximum_duration: str = "PT2H",
        os_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger patch installation on an Azure VM or Arc server."""
        return await self.call_tool(
            "install_vm_patches",
            {
                "machine_name": machine_name,
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "classifications": classifications or ["Critical", "Security"],
                "vm_type": vm_type,
                "resource_id": resource_id,
                "kb_numbers_to_include": kb_numbers_to_include or [],
                "kb_numbers_to_exclude": kb_numbers_to_exclude or [],
                "reboot_setting": reboot_setting,
                "maximum_duration": maximum_duration,
                "os_type": os_type,
            },
        )

    async def get_install_status(
        self,
        operation_url: str,
    ) -> Dict[str, Any]:
        """Check the status of an in-progress or completed patch installation."""
        return await self.call_tool(
            "get_install_status",
            {"operation_url": operation_url},
        )

    async def get_vm_patch_summary(
        self,
        subscription_id: str,
        resource_group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a consolidated patch status summary for all VMs/Arc servers in the subscription."""
        return await self.call_tool(
            "get_vm_patch_summary",
            {
                "subscription_id": subscription_id,
                "resource_group": resource_group,
            },
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client_instance: Optional[PatchMCPClient] = None


async def get_patch_mcp_client() -> PatchMCPClient:
    """Get or create the global Patch MCP client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = PatchMCPClient()
        await _client_instance.initialize()
    return _client_instance
