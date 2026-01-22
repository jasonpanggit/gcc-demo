"""
Cosmos-backed table for standardized EOL results.
Stores and retrieves normalized EOL responses before invoking agents.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from .cosmos_cache import base_cosmos

logger = logging.getLogger(__name__)


@dataclass
class EolRecord:
    id: str
    software_key: str
    version_key: str
    software_name: str
    version: Optional[str]
    eol_date: Optional[str]
    support_end_date: Optional[str]
    release_date: Optional[str]
    status: Optional[str]
    risk_level: Optional[str]
    confidence: Optional[float]
    source: Optional[str]
    source_url: Optional[str]
    agent_used: Optional[str]
    data: Dict[str, Any]
    created_at: str
    updated_at: Optional[str] = None
    ttl: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        doc = asdict(self)
        if self.ttl is None:
            doc.pop("ttl", None)
        return doc

    @classmethod
    def from_dict(cls, doc: Dict[str, Any]) -> "EolRecord":
        filtered = {
            k: v for k, v in doc.items() if not k.startswith("_") and k != "expires_at"
        }
        return cls(**filtered)

    def to_cached_response(self) -> Dict[str, Any]:
        """Return orchestrator-friendly cached response."""
        response_data = self.data or {}
        if isinstance(response_data, dict):
            response_data.setdefault("agent_used", self.agent_used or self.source)
        return {
            "success": True,
            "source": self.source or "eol_inventory",
            "agent_used": self.agent_used or self.source or "eol_inventory",
            "timestamp": datetime.utcnow().isoformat(),
            "cached": True,
            "cache_source": "cosmos_eol_table",
            "cache_created_at": self.created_at,
            "data": response_data,
        }


class EolInventory:
    """Lightweight Cosmos helper for standardized EOL records."""

    def __init__(self, container_id: str = "eol_table", default_ttl_days: int = 30):
        self.container_id = container_id
        self.default_ttl_days = default_ttl_days
        # Disable TTL-based expiration in Cosmos; keep defaults for backward compatibility.
        self.default_ttl_seconds: Optional[int] = None
        self.container = None
        self.initialized = False
        self.hit_count = 0
        self.miss_count = 0

    async def initialize(self) -> None:
        if self.initialized:
            return
        try:
            await base_cosmos._initialize_async()
            self.container = base_cosmos.get_container(
                self.container_id,
                partition_path="/software_key",
                offer_throughput=400,
                default_ttl=self.default_ttl_seconds,
            )
            self.initialized = True
            logger.info("✅ EOL table ready (container %s)", self.container_id)
        except Exception as exc:
            logger.warning("EOL table initialization failed: %s", exc)
            self.initialized = False

    def _normalize_name(self, name: str) -> str:
        return (name or "").strip().lower()

    def _normalize_version(self, version: Optional[str]) -> str:
        return (version or "any").strip().lower()

    def _build_id(self, software_name: str, version: Optional[str]) -> str:
        return f"{self._normalize_name(software_name)}:{self._normalize_version(version)}"

    def _confidence_value(self, value: Optional[float]) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _standardize_data(self, software_name: str, version: Optional[str], result: Dict[str, Any]) -> Optional[EolRecord]:
        if not result or not result.get("success"):
            return None

        data = result.get("data") or {}
        if not isinstance(data, dict):
            return None

        software_key = self._normalize_name(data.get("software_name") or software_name)
        version_key = self._normalize_version(data.get("version") or version)
        now = datetime.now(timezone.utc)
        record = EolRecord(
            id=self._build_id(software_name, version),
            software_key=software_key,
            version_key=version_key,
            software_name=data.get("software_name") or software_name,
            version=data.get("version") or version,
            eol_date=data.get("eol_date"),
            support_end_date=data.get("support_end_date") or data.get("support"),
            release_date=data.get("release_date"),
            status=data.get("status"),
            risk_level=data.get("risk_level"),
            confidence=data.get("confidence") or result.get("confidence"),
            source=data.get("source") or result.get("source"),
            source_url=data.get("source_url") or result.get("source_url"),
            agent_used=data.get("agent_used") or result.get("agent_used"),
            data=data,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            ttl=None,
        )
        return record

    async def get(self, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        await self.initialize()
        if not self.container:
            return None
        try:
            software_key = self._normalize_name(software_name)
            version_key = self._normalize_version(version)
            query = (
                "SELECT * FROM c WHERE c.software_key = @software_key "
                "AND c.version_key = @version_key"
            )
            params = [
                {"name": "@software_key", "value": software_key},
                {"name": "@version_key", "value": version_key},
            ]
            items = list(
                self.container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                self.miss_count += 1
                logger.debug("EOL table miss for %s %s", software_name, version or "(any)")
                return None

            items.sort(key=lambda doc: doc.get("created_at", ""), reverse=True)
            record = EolRecord.from_dict(items[0])
            # Basic expiration check in case TTL is not enforced yet
            self.hit_count += 1
            logger.debug("EOL table hit for %s %s", software_name, version or "(any)")
            return record.to_cached_response()
        except Exception as exc:
            logger.debug("EOL table read failed: %s", exc)
            return None

    async def upsert(self, software_name: str, version: Optional[str], result: Dict[str, Any]) -> bool:
        await self.initialize()
        if not self.container:
            logger.warning("EOL table upsert skipped: container not initialized")
            return False

        record = self._standardize_data(software_name, version, result)
        if not record:
            return False

        try:
            existing = None
            try:
                existing = self.container.read_item(
                    item=record.id,
                    partition_key=record.software_key,
                )
            except Exception:
                existing = None

            if existing:
                existing_confidence = self._confidence_value(existing.get("confidence"))
                incoming_confidence = self._confidence_value(record.confidence)
                if incoming_confidence <= existing_confidence:
                    return True

            record_dict = record.to_dict()
            if existing:
                record_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.container.replace_item(item=record.id, body=record_dict)
            else:
                self.container.upsert_item(record_dict)
            return True
        except Exception as exc:
            logger.debug("EOL table upsert failed: %s", exc)
            return False

    async def update_record(self, record_id: str, software_key: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.initialize()
        if not self.container:
            return None

        allowed = {
            "software_name",
            "version",
            "eol_date",
            "support_end_date",
            "release_date",
            "status",
            "risk_level",
            "confidence",
            "source",
            "source_url",
            "agent_used",
        }

        try:
            doc = self.container.read_item(item=record_id, partition_key=software_key)
        except Exception as exc:
            logger.debug("EOL table update read failed: %s", exc)
            return None

        for key, value in updates.items():
            if key in allowed:
                doc[key] = value
                if isinstance(doc.get("data"), dict):
                    doc["data"][key] = value

        doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            self.container.replace_item(item=record_id, body=doc)
            record = EolRecord.from_dict(doc)
            return {
                "id": record.id,
                "software_key": record.software_key,
                "software_name": record.software_name,
                "version": record.version,
                "eol_date": record.eol_date,
                "support_end_date": record.support_end_date,
                "release_date": record.release_date,
                "status": record.status,
                "risk_level": record.risk_level,
                "confidence": record.confidence,
                "source": record.source,
                "source_url": record.source_url,
                "agent_used": record.agent_used,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        except Exception as exc:
            logger.debug("EOL table update failed: %s", exc)
            return None

    async def delete_record(self, record_id: str, software_key: str) -> bool:
        await self.initialize()
        if not self.container:
            return False
        try:
            self.container.delete_item(item=record_id, partition_key=software_key)
            return True
        except Exception as exc:
            logger.debug("EOL table delete failed: %s", exc)
            return False

    async def delete_records(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        await self.initialize()
        if not self.container:
            return {
                "deleted": 0,
                "failed": [
                    {"item": item, "error": "Container not initialized"}
                    for item in items
                ],
            }

        deleted = 0
        failed = []
        for item in items:
            record_id = item.get("record_id") if isinstance(item, dict) else None
            software_key = item.get("software_key") if isinstance(item, dict) else None
            if not record_id or not software_key:
                failed.append({"item": item, "error": "Missing record_id or software_key"})
                continue
            try:
                self.container.delete_item(item=record_id, partition_key=software_key)
                deleted += 1
            except Exception as exc:
                logger.debug("EOL table bulk delete failed for %s: %s", record_id, exc)
                failed.append({"item": item, "error": str(exc)})

        return {"deleted": deleted, "failed": failed}

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hit_count, "misses": self.miss_count}

    async def list_recent(
        self,
        *,
        limit: int = 100,
        software_name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """Return recent EOL records for UI/debug views."""
        await self.initialize()
        if not self.container:
            return []

        safe_limit = max(1, min(limit, 500))

        conditions = []
        params = []

        if software_name:
            software_key = self._normalize_name(software_name)
            conditions.append("c.software_key = @software_key")
            params.append({"name": "@software_key", "value": software_key})

        if version:
            version_key = self._normalize_version(version)
            conditions.append("c.version_key = @version_key")
            params.append({"name": "@version_key", "value": version_key})

        query = "SELECT * FROM c"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY c._ts DESC"

        records: list[Dict[str, Any]] = []
        try:
            items_iter = self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )

            for idx, doc in enumerate(items_iter):
                if idx >= safe_limit:
                    break

                try:
                    record = EolRecord.from_dict(doc)
                    records.append(
                        {
                            "id": record.id,
                            "software_key": record.software_key,
                            "version_key": record.version_key,
                            "software_name": record.software_name,
                            "version": record.version,
                            "eol_date": record.eol_date,
                            "support_end_date": record.support_end_date,
                            "release_date": record.release_date,
                            "status": record.status,
                            "risk_level": record.risk_level,
                            "confidence": record.confidence,
                            "source": record.source,
                            "source_url": record.source_url,
                            "agent_used": record.agent_used,
                            "created_at": record.created_at,
                            "updated_at": record.updated_at,
                        }
                    )
                except Exception as record_exc:
                    logger.debug("EOL table record parse failed: %s", record_exc)
                    continue
        except Exception as exc:
            logger.debug("EOL table query failed: %s", exc)

        return records


eol_inventory = EolInventory()
