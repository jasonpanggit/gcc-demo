"""
In-memory repository for CVE data persistence in mock mode.

# TODO(Phase-11): Replace in-memory repo with mock PostgreSQL fixture.
# This module is required for USE_MOCK_DATA=true mode (main.py line ~659).
# Once mock mode uses a local PostgreSQL instance with the standard
# CVERepository, this file can be deleted.

Implements the same async interface used by CVEService so local/mock runs can
persist sync/search results without external dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from threading import RLock
from typing import Optional, List, Dict, Any

try:
    from models.cve_models import UnifiedCVE
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import UnifiedCVE
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


def _affected_product_keyword_haystack(cve: UnifiedCVE) -> str:
    parts: List[str] = []
    for product in cve.affected_products:
        parts.append(re.sub(r"[_-]+", " ", str(product.vendor or "")))
        parts.append(re.sub(r"[_-]+", " ", str(product.product or "")))
        parts.append(re.sub(r"[_-]+", " ", str(product.version or "")))
    return " ".join(parts).lower()


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
        offset: int = 0,
        sort_by: str = "published_date",
        sort_order: str = "desc",
    ) -> List[UnifiedCVE]:
        with self._lock:
            rows = list(self._items.values())

        rows = self._apply_filters(rows, filters)
        rows = self._sort_rows(rows, sort_by, sort_order)

        if offset < 0:
            offset = 0
        if limit < 0:
            limit = 0

        return rows[offset:offset + limit]

    def _sort_rows(
        self,
        rows: List[UnifiedCVE],
        sort_by: str,
        sort_order: str,
    ) -> List[UnifiedCVE]:
        reverse = str(sort_order).lower() != "asc"
        field = (sort_by or "published_date").lower()
        severity_rank = {
            "UNKNOWN": 0,
            "LOW": 1,
            "MEDIUM": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }

        def score_for(cve: UnifiedCVE) -> float:
            if cve.cvss_v3 and cve.cvss_v3.base_score is not None:
                return cve.cvss_v3.base_score
            if cve.cvss_v2 and cve.cvss_v2.base_score is not None:
                return cve.cvss_v2.base_score
            return -1.0

        def severity_for(cve: UnifiedCVE) -> str:
            if cve.cvss_v3 and cve.cvss_v3.base_severity:
                return cve.cvss_v3.base_severity.upper()
            if cve.cvss_v2 and cve.cvss_v2.base_severity:
                return cve.cvss_v2.base_severity.upper()
            return "UNKNOWN"

        if field == "cve_id":
            key_fn = lambda cve: cve.cve_id
        elif field == "severity":
            key_fn = lambda cve: (severity_rank.get(severity_for(cve), 0), score_for(cve), cve.cve_id)
        elif field == "cvss_score":
            key_fn = lambda cve: (score_for(cve), cve.cve_id)
        elif field == "last_modified_date":
            key_fn = lambda cve: (cve.last_modified_date, cve.cve_id)
        else:
            key_fn = lambda cve: (cve.published_date, cve.cve_id)

        return sorted(rows, key=key_fn, reverse=reverse)

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

        # Apply filter semantics similar to PostgreSQL query behavior.
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
                if keyword in (r.description or "").lower()
                or keyword in r.cve_id.lower()
                or keyword in _affected_product_keyword_haystack(r)
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
