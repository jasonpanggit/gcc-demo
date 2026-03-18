"""Patch install history persistence for MTTP analytics."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

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

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self):
        logger.info("PatchInstallHistoryRepository initialized with PostgreSQL")

    @staticmethod
    def _coerce_timestamp(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _row_to_item(row: asyncpg.Record) -> Dict[str, Any]:
        item = dict(row)
        item.setdefault("classifications", [])
        item.setdefault("requested_patch_ids", [])
        item.setdefault("patches", [])
        item["id"] = item.get("install_id")
        return item

    async def upsert_pending(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        install_id = _make_record_id(payload["operation_url"])
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO patch_installs (
                    install_id, resource_id, operation_url, machine_name,
                    subscription_id, resource_group, vm_type, os_type,
                    classifications, requested_patch_ids, status, is_done,
                    installed_patch_count, failed_patch_count, pending_patch_count,
                    patches, start_date_time, completed_at, reboot_status,
                    maintenance_window_exceeded, error, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8,
                    $9, $10, $11, FALSE,
                    0, 0, 0,
                    $12::jsonb, $13, NULL, NULL,
                    FALSE, NULL, NOW(), NOW()
                )
                ON CONFLICT (operation_url) DO UPDATE SET
                    resource_id = COALESCE(EXCLUDED.resource_id, patch_installs.resource_id),
                    machine_name = COALESCE(EXCLUDED.machine_name, patch_installs.machine_name),
                    subscription_id = COALESCE(EXCLUDED.subscription_id, patch_installs.subscription_id),
                    resource_group = COALESCE(EXCLUDED.resource_group, patch_installs.resource_group),
                    vm_type = COALESCE(EXCLUDED.vm_type, patch_installs.vm_type),
                    os_type = COALESCE(EXCLUDED.os_type, patch_installs.os_type),
                    classifications = COALESCE(EXCLUDED.classifications, patch_installs.classifications),
                    requested_patch_ids = COALESCE(EXCLUDED.requested_patch_ids, patch_installs.requested_patch_ids),
                    status = COALESCE(EXCLUDED.status, patch_installs.status),
                    start_date_time = COALESCE(EXCLUDED.start_date_time, patch_installs.start_date_time),
                    updated_at = NOW()
                RETURNING install_id, resource_id, operation_url, machine_name,
                          subscription_id, resource_group, vm_type, os_type,
                          classifications, requested_patch_ids, status, is_done,
                          installed_patch_count, failed_patch_count, pending_patch_count,
                          patches, start_date_time, completed_at, reboot_status,
                          maintenance_window_exceeded, error, created_at, updated_at
                """,
                install_id,
                payload.get("resource_id"),
                payload["operation_url"],
                payload.get("machine_name"),
                payload.get("subscription_id") or "unknown",
                payload.get("resource_group"),
                payload.get("vm_type") or "arc",
                payload.get("os_type"),
                payload.get("classifications") or [],
                payload.get("requested_patch_ids") or [],
                payload.get("status") or "InProgress",
                json.dumps([]),
                self._coerce_timestamp(payload.get("start_date_time")),
            )
        return self._row_to_item(row)

    async def mark_completed(self, operation_url: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE patch_installs
                SET status = COALESCE($2, status, 'Unknown'),
                    is_done = TRUE,
                    installed_patch_count = COALESCE($3, 0),
                    failed_patch_count = COALESCE($4, 0),
                    pending_patch_count = COALESCE($5, 0),
                    patches = $6::jsonb,
                    start_date_time = COALESCE($7, start_date_time),
                    completed_at = COALESCE($8, start_date_time, completed_at, NOW()),
                    updated_at = NOW(),
                    reboot_status = $9,
                    maintenance_window_exceeded = COALESCE($10, FALSE),
                    error = $11
                WHERE operation_url = $1
                RETURNING install_id, resource_id, operation_url, machine_name,
                          subscription_id, resource_group, vm_type, os_type,
                          classifications, requested_patch_ids, status, is_done,
                          installed_patch_count, failed_patch_count, pending_patch_count,
                          patches, start_date_time, completed_at, reboot_status,
                          maintenance_window_exceeded, error, created_at, updated_at
                """,
                operation_url,
                result.get("status"),
                result.get("installed_patch_count", 0) or 0,
                result.get("failed_patch_count", 0) or 0,
                result.get("pending_patch_count", 0) or 0,
                json.dumps(result.get("patches") or []),
                self._coerce_timestamp(result.get("start_date_time")),
                self._coerce_timestamp(result.get("last_modified") or result.get("start_date_time")),
                result.get("reboot_status"),
                result.get("maintenance_window_exceeded", False),
                result.get("error"),
            )
        if row is None:
            logger.warning("No pending patch install record found for operation_url")
            return None
        return self._row_to_item(row)

    async def get_by_operation_url(self, operation_url: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT install_id, resource_id, operation_url, machine_name,
                       subscription_id, resource_group, vm_type, os_type,
                       classifications, requested_patch_ids, status, is_done,
                       installed_patch_count, failed_patch_count, pending_patch_count,
                       patches, start_date_time, completed_at, reboot_status,
                       maintenance_window_exceeded, error, created_at, updated_at
                FROM patch_installs
                WHERE operation_url = $1
                LIMIT 1
                """,
                operation_url,
            )
        return self._row_to_item(row) if row else None

    async def list_completed_since(self, cutoff_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        cutoff = self._coerce_timestamp(cutoff_iso)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT install_id, resource_id, operation_url, machine_name,
                       subscription_id, resource_group, vm_type, os_type,
                       classifications, requested_patch_ids, status, is_done,
                       installed_patch_count, failed_patch_count, pending_patch_count,
                       patches, start_date_time, completed_at, reboot_status,
                       maintenance_window_exceeded, error, created_at, updated_at
                FROM patch_installs
                WHERE is_done = TRUE
                  AND ($1::timestamptz IS NULL OR completed_at >= $1)
                ORDER BY completed_at DESC NULLS LAST, updated_at DESC
                """,
                cutoff,
            )
        return [self._row_to_item(row) for row in rows]


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