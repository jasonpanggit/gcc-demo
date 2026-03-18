"""
In-memory storage for vendor parser URLs and parse stats.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VendorUrlRecord:
    id: str
    vendor: str
    url: str
    description: Optional[str]
    software_found: int
    last_parsed_at: str
    created_at: str
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, doc: Dict[str, Any]) -> "VendorUrlRecord":
        filtered = {k: v for k, v in doc.items() if not k.startswith("_") and k != "expires_at"}
        return cls(**filtered)


class VendorUrlInventory:
    def __init__(self, container_id: str = "vendor_urls", default_ttl_seconds: Optional[int] = None):
        self.container_id = container_id
        self.default_ttl_seconds = default_ttl_seconds
        self._store: Dict[str, Dict[str, Any]] = {}  # In-memory store
        self.initialized = False

    async def initialize(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        logger.info("Vendor URL inventory initialized (in-memory)")

    def _build_id(self, vendor: str, url: str) -> str:
        safe_vendor = re.sub(r"[^a-zA-Z0-9_-]", "_", (vendor or "unknown").strip())
        url_hash = hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:32]
        return f"{safe_vendor}:{url_hash}"

    async def upsert_vendor_urls(self, vendor: str, urls: List[Dict[str, Any]], software_found: int, parsed_at: str) -> bool:
        await self.initialize()

        now = datetime.now(timezone.utc).isoformat()
        parsed_ts = parsed_at or now
        wrote_any = False

        for entry in urls:
            try:
                url_value = entry.get("url") if isinstance(entry, dict) else None
                if not url_value:
                    continue

                record_id = self._build_id(vendor, url_value)
                description = None
                if isinstance(entry, dict):
                    description = entry.get("description")

                existing = self._store.get(record_id)

                if existing:
                    existing.update(
                        {
                            "software_found": software_found,
                            "last_parsed_at": parsed_ts,
                            "description": description or existing.get("description"),
                            "updated_at": now,
                        }
                    )
                    self._store[record_id] = existing
                else:
                    record = VendorUrlRecord(
                        id=record_id,
                        vendor=vendor,
                        url=url_value,
                        description=description,
                        software_found=software_found,
                        last_parsed_at=parsed_ts,
                        created_at=now,
                        updated_at=now,
                    )
                    self._store[record_id] = record.to_dict()
                wrote_any = True
            except Exception as exc:
                logger.debug("Error processing vendor URL entry: %s", exc)
                continue

        return wrote_any


vendor_url_inventory = VendorUrlInventory()
