"""
Cosmos-backed storage for vendor parser URLs and parse stats.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .cosmos_cache import base_cosmos

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
        self.container = None
        self.initialized = False

    async def initialize(self) -> None:
        if self.initialized:
            return
        try:
            await base_cosmos._initialize_async()
            self.container = base_cosmos.get_container(
                self.container_id,
                partition_path="/vendor",
                offer_throughput=400,
                default_ttl=self.default_ttl_seconds,
            )
            self.initialized = True
            logger.info("✅ Vendor URL container ready (%s)", self.container_id)
        except Exception as exc:
            logger.warning("Vendor URL container init failed: %s", exc)
            self.initialized = False

    def _build_id(self, vendor: str, url: str) -> str:
        return f"{vendor}:{url}"

    async def upsert_vendor_urls(self, vendor: str, urls: List[Dict[str, Any]], software_found: int, parsed_at: str) -> bool:
        await self.initialize()
        if not self.container:
            return False

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

                try:
                    existing = None
                    try:
                        existing = self.container.read_item(item=record_id, partition_key=vendor)
                    except Exception:
                        existing = None

                    if existing:
                        existing_doc = VendorUrlRecord.from_dict(existing).to_dict()
                        existing_doc.update(
                            {
                                "software_found": software_found,
                                "last_parsed_at": parsed_ts,
                                "description": description or existing_doc.get("description"),
                                "updated_at": now,
                            }
                        )
                        self.container.replace_item(item=record_id, body=existing_doc)
                    else:
                        self.container.create_item(body=record.to_dict())
                    wrote_any = True
                except Exception as exc:
                    logger.debug("Vendor URL upsert failed for %s: %s", url_value, exc)
                    continue
            except Exception as exc:
                logger.debug("Error processing vendor URL entry: %s", exc)
                continue

        return wrote_any


vendor_url_inventory = VendorUrlInventory()
