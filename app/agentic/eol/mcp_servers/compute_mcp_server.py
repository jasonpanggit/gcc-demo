"""Compute MCP Server — Azure Virtual Machine Inventory

Provides read-only compute resource listing tools via FastMCP:
  1. virtual_machine_list  — List VMs in a subscription / resource group

Uses AzureCLIExecutor (service principal) instead of the Python SDK so that
no extra RBAC assignment is required beyond what the SP already holds.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

try:
    from app.agentic.eol.utils.azure_cli_executor import get_azure_cli_executor
except ModuleNotFoundError:
    from utils.azure_cli_executor import get_azure_cli_executor

_LOG_LEVEL_NAME = os.getenv("COMPUTE_MCP_LOG_LEVEL", "INFO")
try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_server = FastMCP(name="azure-compute")


def _require_injected_spn() -> str:
    """Validate injected SPN env vars and return client_id for logging."""
    client_id = os.getenv("AZURE_SP_CLIENT_ID")
    client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    if not (client_id and client_secret and tenant_id):
        raise RuntimeError(
            "Injected SPN credentials are required. "
            "Set AZURE_SP_CLIENT_ID, AZURE_SP_CLIENT_SECRET, and AZURE_TENANT_ID."
        )
    return client_id


def _default_subscription_id() -> str:
    return os.getenv("SUBSCRIPTION_ID") or os.getenv("AZURE_SUBSCRIPTION_ID") or ""


def _text_result(data: Dict[str, Any]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool 1: virtual_machine_list
# ---------------------------------------------------------------------------

@_server.tool()
async def virtual_machine_list(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group name to scope the listing. Omit to list all VMs in the subscription.",
    ] = None,
) -> List[TextContent]:
    """List all virtual machines in a subscription or resource group.

    Returns name, location, VM size, OS type, power state, and resource ID for
    each VM. Use this to discover which VMs exist before inspecting one in detail.
    """
    try:
        sp_client_id = _require_injected_spn()
        logger.info("Compute MCP auth: using injected SPN credential (%s...)", sp_client_id[:8])

        sub_id = subscription_id or _default_subscription_id()
        executor = await get_azure_cli_executor()

        # -d flag adds powerState, publicIps, privateIps to each VM record
        cmd = f"az vm list -d --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"

        result = await executor.execute(cmd, timeout=90, add_subscription=False)

        if result.get("status") != "success":
            return _text_result({"success": False, "error": result.get("error", "CLI call failed")})

        vms_raw: List[Dict] = result.get("output") or []
        vms = []
        for vm in vms_raw:
            hw = vm.get("hardwareProfile") or {}
            sp = vm.get("storageProfile") or {}
            os_disk = sp.get("osDisk") or {}
            vms.append({
                "name": vm.get("name"),
                "resource_group": vm.get("resourceGroup"),
                "location": vm.get("location"),
                "vm_size": hw.get("vmSize"),
                "os_type": os_disk.get("osType"),
                "power_state": vm.get("powerState"),
                "provisioning_state": vm.get("provisioningState"),
                "resource_id": vm.get("id"),
            })

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "vm_count": len(vms),
            "virtual_machines": vms,
        })

    except Exception as exc:
        logger.exception("virtual_machine_list failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _server.run(transport="stdio")
