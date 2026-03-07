"""
In-memory repository for CVE data persistence in mock mode.

Implements the same async interface used by CVEService so local/mock runs can
persist sync/search results without Cosmos DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional, List, Dict, Any

try:
    from models.cve_models import UnifiedCVE
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


class CVEInMemoryRepository:
    """Mock-mode in-memory CVE repository with repository-compatible methods."""

    def __init__(self):
        self._items: Dict[str, UnifiedCVE] = {}
        self._lock = RLock()

    async def upsert_cve(self, cve: UnifiedCVE) -> None:
        cve_id = cve.cve_id.upper()
        with self._lock:
            self._items[cve_id] = cve

    async def get_cve(self, cve_id: str) -> Optional[UnifiedCVE]:
        key = cve_id.upper()
        with self._lock:
            return self._items.get(key)

    async def query_cves(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0
    ) -> List[UnifiedCVE]:
        with self._lock:
            rows = list(self._items.values())

        rows = self._apply_filters(rows, filters)
        rows.sort(key=lambda r: r.last_modified_date, reverse=True)

        if offset < 0:
            offset = 0
        if limit < 0:
            limit = 0

        return rows[offset:offset + limit]

    async def count_cves(self, filters: Dict[str, Any]) -> int:
        with self._lock:
            rows = list(self._items.values())

        return len(self._apply_filters(rows, filters))

    def _apply_filters(
        self,
        rows: List[UnifiedCVE],
        filters: Dict[str, Any]
    ) -> List[UnifiedCVE]:
        """Apply repository-like filters in-memory for search and count."""

        # Apply filter semantics close to Cosmos query behavior.
        severity = filters.get("severity")
        if severity:
            target = str(severity).upper()
            rows = [
                r for r in rows
                if r.cvss_v3 is not None and (r.cvss_v3.base_severity or "").upper() == target
            ]

        min_score = filters.get("min_score")
        if min_score is not None:
            min_score = float(min_score)
            rows = [
                r for r in rows
                if r.cvss_v3 is not None and r.cvss_v3.base_score is not None and r.cvss_v3.base_score >= min_score
            ]

        max_score = filters.get("max_score")
        if max_score is not None:
            max_score = float(max_score)
            rows = [
                r for r in rows
                if r.cvss_v3 is not None and r.cvss_v3.base_score is not None and r.cvss_v3.base_score <= max_score
            ]

        published_after = self._parse_datetime(filters.get("published_after"))
        if published_after is not None:
            rows = [r for r in rows if r.published_date >= published_after]

        published_before = self._parse_datetime(filters.get("published_before"))
        if published_before is not None:
            rows = [r for r in rows if r.published_date <= published_before]

        keyword = (filters.get("keyword") or "").strip().lower()
        if keyword:
            rows = [
                r for r in rows
                if keyword in (r.description or "").lower() or keyword in r.cve_id.lower()
            ]

        source = (filters.get("source") or "").strip()
        if source:
            rows = [r for r in rows if source in r.sources]

        vendor = (filters.get("vendor") or "").strip().lower()
        if vendor:
            rows = [
                r for r in rows
                if any(vendor in (p.vendor or "").lower() for p in r.affected_products)
            ]

        product = (filters.get("product") or "").strip().lower()
        if product:
            rows = [
                r for r in rows
                if any(product in (p.product or "").lower() for p in r.affected_products)
            ]

        return rows

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
