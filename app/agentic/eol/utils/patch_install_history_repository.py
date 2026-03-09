"""Patch install history persistence for MTTP analytics."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_record_id(operation_url: str) -> str:
    return hashlib.sha256(operation_url.encode("utf-8")).hexdigest()


class PatchInstallHistoryRepository:
    """Persist patch install operation state and completed outcomes."""

    def __init__(self, cosmos_client, database_name: str, container_name: str):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.container = None

    async def initialize(self):
        database = self.cosmos_client.get_database_client(self.database_name)
        self.container = database.get_container_client(self.container_name)
        logger.info("PatchInstallHistoryRepository initialized: %s", self.container_name)

    async def upsert_pending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        item = {
            "id": _make_record_id(payload["operation_url"]),
            "record_type": "patch_install",
            "operation_url": payload["operation_url"],
            "machine_name": payload.get("machine_name"),
            "subscription_id": payload.get("subscription_id") or "unknown",
            "resource_group": payload.get("resource_group"),
            "vm_type": payload.get("vm_type") or "arc",
            "os_type": payload.get("os_type"),
            "classifications": payload.get("classifications") or [],
            "requested_patch_ids": payload.get("requested_patch_ids") or [],
            "status": payload.get("status") or "InProgress",
            "is_done": False,
            "installed_patch_count": 0,
            "failed_patch_count": 0,
            "pending_patch_count": 0,
            "patches": [],
            "start_date_time": payload.get("start_date_time"),
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        existing = await self.get_by_operation_url(payload["operation_url"])
        if existing:
            item["created_at"] = existing.get("created_at", now)
            item.update({k: v for k, v in existing.items() if k not in {"updated_at", "status", "is_done", "patches", "installed_patch_count", "failed_patch_count", "pending_patch_count", "completed_at"}})
            item.update({k: v for k, v in payload.items() if v is not None})
            item["updated_at"] = now

        await asyncio.to_thread(self.container.upsert_item, body=item)
        return item

    async def mark_completed(self, operation_url: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = await self.get_by_operation_url(operation_url)
        if not existing:
            logger.warning("No pending patch install record found for operation_url")
            return None

        now = _utc_now_iso()
        existing.update({
            "status": result.get("status") or existing.get("status") or "Unknown",
            "is_done": True,
            "installed_patch_count": result.get("installed_patch_count", 0) or 0,
            "failed_patch_count": result.get("failed_patch_count", 0) or 0,
            "pending_patch_count": result.get("pending_patch_count", 0) or 0,
            "patches": result.get("patches") or [],
            "start_date_time": result.get("start_date_time") or existing.get("start_date_time"),
            "completed_at": result.get("last_modified") or result.get("start_date_time") or now,
            "updated_at": now,
            "reboot_status": result.get("reboot_status"),
            "maintenance_window_exceeded": result.get("maintenance_window_exceeded", False),
            "error": result.get("error"),
        })
        await asyncio.to_thread(self.container.upsert_item, body=existing)
        return existing

    async def get_by_operation_url(self, operation_url: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM c WHERE c.operation_url = @operation_url"
        items = await asyncio.to_thread(
            lambda: list(self.container.query_items(
                query=query,
                parameters=[{"name": "@operation_url", "value": operation_url}],
                enable_cross_partition_query=True,
            ))
        )
        return items[0] if items else None

    async def list_completed_since(self, cutoff_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        query = ["SELECT * FROM c WHERE c.record_type = 'patch_install' AND c.is_done = true"]
        parameters: List[Dict[str, Any]] = []
        if cutoff_iso:
            query.append("AND c.completed_at >= @cutoff_iso")
            parameters.append({"name": "@cutoff_iso", "value": cutoff_iso})
        query.append("ORDER BY c.completed_at DESC")

        return await asyncio.to_thread(
            lambda: list(self.container.query_items(
                query=" ".join(query),
                parameters=parameters,
                enable_cross_partition_query=True,
            ))
        )


class InMemoryPatchInstallHistoryRepository:
    """In-memory fallback for mock mode and tests."""

    def __init__(self):
        self.items: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        return None

    async def upsert_pending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        key = payload["operation_url"]
        existing = self.items.get(key, {})
        item = {
            "id": existing.get("id") or _make_record_id(key),
            "record_type": "patch_install",
            "operation_url": key,
            "machine_name": payload.get("machine_name"),
            "subscription_id": payload.get("subscription_id") or "unknown",
            "resource_group": payload.get("resource_group"),
            "vm_type": payload.get("vm_type") or "arc",
            "os_type": payload.get("os_type"),
            "classifications": payload.get("classifications") or [],
            "requested_patch_ids": payload.get("requested_patch_ids") or [],
            "status": payload.get("status") or "InProgress",
            "is_done": False,
            "installed_patch_count": 0,
            "failed_patch_count": 0,
            "pending_patch_count": 0,
            "patches": [],
            "start_date_time": payload.get("start_date_time"),
            "completed_at": None,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        self.items[key] = item
        return item

    async def mark_completed(self, operation_url: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        item = self.items.get(operation_url)
        if not item:
            return None
        item.update({
            "status": result.get("status") or item.get("status") or "Unknown",
            "is_done": True,
            "installed_patch_count": result.get("installed_patch_count", 0) or 0,
            "failed_patch_count": result.get("failed_patch_count", 0) or 0,
            "pending_patch_count": result.get("pending_patch_count", 0) or 0,
            "patches": result.get("patches") or [],
            "start_date_time": result.get("start_date_time") or item.get("start_date_time"),
            "completed_at": result.get("last_modified") or result.get("start_date_time") or _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "reboot_status": result.get("reboot_status"),
            "maintenance_window_exceeded": result.get("maintenance_window_exceeded", False),
            "error": result.get("error"),
        })
        return item

    async def get_by_operation_url(self, operation_url: str) -> Optional[Dict[str, Any]]:
        return self.items.get(operation_url)

    async def list_completed_since(self, cutoff_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        items = [item for item in self.items.values() if item.get("is_done")]
        if cutoff_iso:
            items = [item for item in items if (item.get("completed_at") or "") >= cutoff_iso]
        return sorted(items, key=lambda item: item.get("completed_at") or "", reverse=True)