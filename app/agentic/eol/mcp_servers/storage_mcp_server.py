"""Storage MCP Server — Azure Storage Account Inventory

Provides read-only storage resource listing tools via FastMCP:
  1. storage_account_list  — List storage accounts in a subscription / resource group

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

_LOG_LEVEL_NAME = os.getenv("STORAGE_MCP_LOG_LEVEL", "INFO")
try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_server = FastMCP(name="azure-storage")


def _default_subscription_id() -> str:
    return os.getenv("SUBSCRIPTION_ID") or os.getenv("AZURE_SUBSCRIPTION_ID") or ""


def _text_result(data: Dict[str, Any]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool 1: storage_account_list
# ---------------------------------------------------------------------------

@_server.tool()
async def storage_account_list(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group name to scope the listing. Omit to list all storage accounts.",
    ] = None,
) -> List[TextContent]:
    """List all storage accounts in a subscription or resource group.

    Returns name, location, SKU, kind, access tier, HTTPS-only flag, and
    resource ID for each storage account.
    """
    try:
        sub_id = subscription_id or _default_subscription_id()
        executor = await get_azure_cli_executor()

        cmd = f"az storage account list --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"

        result = await executor.execute(cmd, timeout=60, add_subscription=False)

        if result.get("status") != "success":
            return _text_result({"success": False, "error": result.get("error", "CLI call failed")})

        accounts_raw: List[Dict] = result.get("output") or []
        accounts = []
        for acct in accounts_raw:
            sku = acct.get("sku") or {}
            accounts.append({
                "name": acct.get("name"),
                "resource_group": acct.get("resourceGroup"),
                "location": acct.get("location"),
                "sku": sku.get("name"),
                "kind": acct.get("kind"),
                "access_tier": acct.get("accessTier"),
                "https_only": acct.get("enableHttpsTrafficOnly"),
                "allow_blob_public_access": acct.get("allowBlobPublicAccess"),
                "provisioning_state": acct.get("provisioningState"),
                "resource_id": acct.get("id"),
            })

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "account_count": len(accounts),
            "storage_accounts": accounts,
        })

    except Exception as exc:
        logger.exception("storage_account_list failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _server.run(transport="stdio")
