"""Shared OS inventory merge logic.

Merges OS inventory data from two sources:

1. **Log Analytics Heartbeat** (via ``OSInventoryAgent.get_os_inventory()``)
   — returns ALL machines that have a Log Analytics / Azure Monitor agent installed,
   covering both Azure VMs and Arc-connected servers.

2. **Azure Resource Graph** (via ``resource_inventory_client.get_resources()``)
   — returns Azure VMs discovered via ARM.  Used as a gap-fill for Azure VMs that do
   NOT have a Log Analytics agent (and therefore have no Heartbeat entry).

The merged result contains every machine visible from either source with no
duplicates.

This module is consumed by:
- ``agents/inventory_orchestrator.py`` (inventory assistant path)
- ``mcp_servers/inventory_mcp_server.py`` ``get_full_os_inventory`` tool (MCP path)

Both paths previously diverged: the inventory assistant path had the merge logic
inline while the MCP tool only called the Heartbeat source, silently dropping
Azure VMs that lack a Log Analytics agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from utils.logger import get_logger
    from utils.config import config
    from utils.normalization import normalize_os_record
    from utils.resource_inventory_client import get_resource_inventory_client
except ModuleNotFoundError:
    from app.agentic.eol.utils.logger import get_logger  # type: ignore[import-not-found]
    from app.agentic.eol.utils.config import config  # type: ignore[import-not-found]
    from app.agentic.eol.utils.normalization import normalize_os_record  # type: ignore[import-not-found]
    from app.agentic.eol.utils.resource_inventory_client import get_resource_inventory_client  # type: ignore[import-not-found]

logger = get_logger(__name__)


def _normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Apply OS name/version normalization to a single inventory record (in-place copy)."""
    if not isinstance(item, dict):
        return item

    normalized = normalize_os_record(
        item.get("os_name") or item.get("name"),
        item.get("os_version") or item.get("version"),
        item.get("os_type"),
    )

    out = dict(item)
    out.setdefault("raw_os_name", normalized.get("raw_os_name"))
    out.setdefault("raw_os_version", normalized.get("raw_os_version"))
    out["os_name"] = normalized["os_name"]
    out["name"] = normalized["os_name"]
    out["os_version"] = normalized.get("os_version")
    out["version"] = normalized.get("os_version")
    # Preserve any pre-existing normalized values (set upstream)
    out["normalized_os_name"] = (
        str(item.get("normalized_os_name") or "").strip().lower() or normalized.get("normalized_os_name")
    )
    out["normalized_os_version"] = (
        str(item.get("normalized_os_version") or "").strip().lower() or normalized.get("normalized_os_version")
    )
    out["os_type"] = normalized.get("os_type") or item.get("os_type")
    return out


async def merge_os_inventory(
    heartbeat_records: List[Dict[str, Any]],
    subscription_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Merge Heartbeat-sourced OS records with Azure Resource Graph VM records.

    Args:
        heartbeat_records: OS inventory records from Log Analytics Heartbeat.
            Covers all machines (Azure VMs + Arc servers) that have a Log
            Analytics / Azure Monitor agent sending heartbeats.
        subscription_id: Optional Azure subscription ID override.  Defaults to
            the value from ``config.azure.subscription_id`` or env vars.

    Returns:
        Deduplicated list of OS inventory records.  Records already present in
        ``heartbeat_records`` (matched by resource_id OR computer_name) are not
        duplicated.  Azure VMs without a Log Analytics agent are appended with
        ``source="resource_inventory"`` and ``computer_type="Azure VM"``.
    """
    # Normalize all incoming Heartbeat records
    merged: List[Dict[str, Any]] = [_normalize_record(item) for item in heartbeat_records if isinstance(item, dict)]

    try:
        inv_client = get_resource_inventory_client()
        sub_id = subscription_id or getattr(getattr(config, "azure", None), "subscription_id", None)
        azure_vms = await inv_client.get_resources(
            "Microsoft.Compute/virtualMachines",
            subscription_id=sub_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to fetch Azure VMs for OS inventory merge: %s", exc)
        return merged

    existing_resource_ids = {
        str(item.get("resource_id") or item.get("resourceId") or "").lower()
        for item in merged
        if str(item.get("resource_id") or item.get("resourceId") or "").strip()
    }
    existing_computer_names = {
        str(item.get("computer_name") or item.get("computer") or "").strip().lower()
        for item in merged
        if str(item.get("computer_name") or item.get("computer") or "").strip()
    }

    added = 0
    for vm in azure_vms:
        selected = vm.get("selected_properties") or {}
        resource_id = str(vm.get("resource_id") or vm.get("id") or "")
        if not resource_id or resource_id.lower() in existing_resource_ids:
            continue

        vm_name = str(vm.get("resource_name") or vm.get("name") or "").strip()
        if not vm_name or vm_name.lower() in existing_computer_names:
            continue

        normalized_os = normalize_os_record(
            selected.get("os_image") or selected.get("os_type") or vm.get("os_name") or "Unknown",
            vm.get("os_version"),
            selected.get("os_type") or vm.get("os_type"),
        )

        merged.append(
            {
                "computer_name": vm_name,
                "computer": vm_name,
                "os_name": normalized_os["os_name"],
                "name": normalized_os["os_name"],
                "os_version": normalized_os.get("os_version"),
                "version": normalized_os.get("os_version"),
                "os_type": normalized_os.get("os_type") or "Unknown",
                "raw_os_name": normalized_os.get("raw_os_name"),
                "raw_os_version": normalized_os.get("raw_os_version"),
                "normalized_os_name": normalized_os.get("normalized_os_name"),
                "normalized_os_version": normalized_os.get("normalized_os_version"),
                "vendor": "Unknown",
                "computer_environment": "Azure",
                "computer_type": "Azure VM",
                "resource_group": vm.get("resource_group") or vm.get("resourceGroup") or "",
                "resource_id": resource_id,
                "last_heartbeat": None,
                "source": "resource_inventory",
                "software_type": "operating system",
                "vm_type": "azure-vm",
            }
        )
        existing_resource_ids.add(resource_id.lower())
        existing_computer_names.add(vm_name.lower())
        added += 1

    if added:
        logger.debug("OS inventory merge: added %d Azure VM(s) from Resource Graph (no Heartbeat)", added)

    return merged


async def get_merged_os_inventory(
    os_agent: Any,
    *,
    days: int = 90,
    limit: Optional[int] = None,
    use_cache: bool = True,
    subscription_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch and merge OS inventory from Heartbeat + Resource Graph.

    Convenience wrapper used by both the inventory orchestrator and the MCP
    server ``get_full_os_inventory`` tool.

    Args:
        os_agent: An ``OSInventoryAgent`` instance with a ``get_os_inventory()``
            method.
        days: Heartbeat lookback window in days.
        limit: Maximum Heartbeat records to fetch (``None`` = no limit).
        use_cache: Whether to use cached Heartbeat data when available.
        subscription_id: Optional Azure subscription ID override for the
            Resource Graph gap-fill query.

    Returns:
        ``(records, from_cache)`` where ``records`` is the merged list and
        ``from_cache`` reflects whether the Heartbeat data came from cache.
    """
    import asyncio

    kwargs: Dict[str, Any] = {"use_cache": use_cache, "days": days}
    if limit is not None:
        kwargs["limit"] = limit

    try:
        result = await asyncio.wait_for(
            os_agent.get_os_inventory(**kwargs),
            timeout=25.0,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("OS inventory agent failed: %s", exc)
        return [], False

    raw_data = result.get("data") if isinstance(result, dict) else []
    heartbeat_records: List[Dict[str, Any]] = [
        item for item in (raw_data if isinstance(raw_data, list) else [])
        if isinstance(item, dict)
    ]
    from_cache = bool(result.get("from_cache")) if isinstance(result, dict) else False

    merged = await merge_os_inventory(heartbeat_records, subscription_id=subscription_id)
    return merged, from_cache
