"""
MSRC Security Update Guide (SUG) affectedProduct OData client.

Fetches KB→CVE and CVE→KB mappings from the MSRC SUG v2.0 OData API.
Handles pagination via @odata.nextLink and caches monthly dumps (TTL 3600s).

Live-validated behaviour:
  - KB article names are bare 7-digit numeric strings ("5050009"), no "KB" prefix.
  - Monthly Windows dump ~2,556 records; requires ~6 paginated requests ($top=500).
  - One KB → many records (per-product variant); deduplicate by cveNumber.
  - Optional MSRC_API_KEY env var accepted in Ocp-Apim-Subscription-Key header.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

import aiohttp

try:
    from models.cve_models import MsrcKbCveRecord
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import MsrcKbCveRecord
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)

_BASE_URL = "https://api.msrc.microsoft.com/sug/v2.0/en-US"
_PAGE_SIZE = 500
_CACHE_TTL = 3600  # seconds

# Month abbreviations matching the MSRC releaseNumber format ("2025-Jan")
_MONTH_ABBREV = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _strip_kb_prefix(kb_number: str) -> str:
    """Return bare numeric KB string, stripping any 'KB' prefix."""
    stripped = kb_number.strip()
    if stripped.upper().startswith("KB"):
        return stripped[2:]
    return stripped


def _patch_tuesday(year: int, month: int) -> date:
    """Return the second Tuesday of the given year/month."""
    # Find the first Tuesday
    first_day = date(year, month, 1)
    # weekday(): Monday=0, Tuesday=1
    days_until_tuesday = (1 - first_day.weekday()) % 7
    first_tuesday = first_day + timedelta(days=days_until_tuesday)
    return first_tuesday + timedelta(weeks=1)


def _last_n_patch_tuesday_months(n: int) -> List[str]:
    """Return the last N Patch Tuesday month strings in 'YYYY-Mon' format."""
    today = date.today()
    months: List[str] = []
    year, month = today.year, today.month

    for _ in range(n):
        # Step back one month if we haven't reached this month's Patch Tuesday yet
        pt = _patch_tuesday(year, month)
        if pt > today and months == []:
            # Current month's PT is in the future; go back one
            month -= 1
            if month == 0:
                month = 12
                year -= 1
            pt = _patch_tuesday(year, month)

        months.append(f"{year}-{_MONTH_ABBREV[month]}")

        # Move to previous month
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return months


class MsrcSugClient:
    """Async client for the MSRC Security Update Guide affectedProduct OData API.

    Usage::

        async with MsrcSugClient() as client:
            cves = await client.fetch_kb_to_cves("KB5050009")
            kbs  = await client.fetch_cve_to_kbs("CVE-2024-21413")
            monthly_map = await client.fetch_monthly_kb_cve_map("2025-Jan")
            recent_map  = await client.fetch_recent_months(n_months=3)
    """

    def __init__(
        self,
        base_url: str = _BASE_URL,
        api_key: Optional[str] = None,
        request_timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or os.environ.get("MSRC_API_KEY")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._session: Optional[aiohttp.ClientSession] = None

        # In-memory TTL cache: (month, product_family) → (timestamp, {kb: {cve, ...}})
        self._monthly_cache: Dict[Tuple[str, str], Tuple[float, Dict[str, Set[str]]]] = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers: Dict[str, str] = {}
            if self._api_key:
                headers["Ocp-Apim-Subscription-Key"] = self._api_key
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers=headers,
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_kb_to_cves(self, kb_number: str) -> List[str]:
        """Return deduplicated CVE IDs that reference the given KB.

        Args:
            kb_number: KB identifier with or without "KB" prefix (e.g. "KB5050009"
                       or "5050009"). The "KB" prefix is stripped before querying.

        Returns:
            Sorted list of unique CVE ID strings (e.g. ["CVE-2024-21413", ...]).
        """
        bare = _strip_kb_prefix(kb_number)
        filter_expr = f"kbArticles/any(kb:kb/articleName eq '{bare}')"
        url = f"{self._base_url}/affectedProduct?$filter={filter_expr}"

        records = await self._fetch_all_pages(url)
        cve_ids: Set[str] = {r.cve_number for r in records if r.cve_number}
        result = sorted(cve_ids)

        logger.info(
            "fetch_kb_to_cves kb=%s pages_fetched records=%d distinct_cves=%d",
            bare,
            len(records),
            len(result),
        )
        return result

    async def fetch_cve_to_kbs(self, cve_id: str) -> List[str]:
        """Return deduplicated bare-numeric KB article names for the given CVE.

        Filters to productFamily eq 'Windows' to exclude Azure/Mariner-only entries.

        Args:
            cve_id: CVE identifier (e.g. "CVE-2024-21413").

        Returns:
            Sorted list of bare numeric KB strings (e.g. ["5002537", "5050009"]).
        """
        cve_upper = cve_id.strip().upper()
        filter_expr = (
            f"cveNumber eq '{cve_upper}' and productFamily eq 'Windows'"
        )
        url = f"{self._base_url}/affectedProduct?$filter={filter_expr}"

        records = await self._fetch_all_pages(url)
        kb_names: Set[str] = {r.kb_article_name for r in records if r.kb_article_name}
        result = sorted(kb_names)

        logger.info(
            "fetch_cve_to_kbs cve=%s records=%d distinct_kbs=%d",
            cve_upper,
            len(records),
            len(result),
        )
        return result

    async def fetch_monthly_kb_cve_map(
        self,
        month: str,
        product_family: str = "Windows",
    ) -> Dict[str, Set[str]]:
        """Return a mapping of KB article name → set of CVE IDs for a release month.

        Results are cached in memory for ``_CACHE_TTL`` seconds per
        (month, product_family) key.

        Args:
            month: Release number string in "YYYY-Mon" format (e.g. "2025-Jan").
            product_family: OData productFamily filter (default "Windows").

        Returns:
            Dict mapping bare numeric KB strings to sets of CVE ID strings.
            Example: {"5050009": {"CVE-2024-21413", "CVE-2025-0001"}, ...}
        """
        cache_key = (month, product_family)
        cached = self._monthly_cache.get(cache_key)
        if cached is not None:
            ts, data = cached
            if time.monotonic() - ts < _CACHE_TTL:
                logger.debug(
                    "fetch_monthly_kb_cve_map cache hit month=%s family=%s",
                    month,
                    product_family,
                )
                return data

        filter_expr = (
            f"releaseNumber eq '{month}' and productFamily eq '{product_family}'"
        )
        url = (
            f"{self._base_url}/affectedProduct"
            f"?$filter={filter_expr}&$top={_PAGE_SIZE}"
        )

        records = await self._fetch_all_pages(url)
        kb_cve_map: Dict[str, Set[str]] = {}
        for record in records:
            if not record.kb_article_name or not record.cve_number:
                continue
            kb_cve_map.setdefault(record.kb_article_name, set()).add(record.cve_number)

        self._monthly_cache[cache_key] = (time.monotonic(), kb_cve_map)

        logger.info(
            "fetch_monthly_kb_cve_map month=%s family=%s records=%d kbs=%d",
            month,
            product_family,
            len(records),
            len(kb_cve_map),
        )
        return kb_cve_map

    async def fetch_recent_months(
        self,
        n_months: int = 3,
        product_family: str = "Windows",
    ) -> Dict[str, Set[str]]:
        """Fetch and merge KB→CVE maps for the last N Patch Tuesday months.

        Months are fetched in parallel via ``asyncio.gather``.

        Args:
            n_months: Number of recent Patch Tuesday months to fetch (default 3).
            product_family: OData productFamily filter (default "Windows").

        Returns:
            Merged dict of bare numeric KB string → set of CVE ID strings.
            If the same KB appears in multiple months its CVE sets are unioned.
        """
        months = _last_n_patch_tuesday_months(n_months)
        logger.info(
            "fetch_recent_months n=%d family=%s months=%s",
            n_months,
            product_family,
            months,
        )

        results: List[Dict[str, Set[str]]] = await asyncio.gather(
            *[self.fetch_monthly_kb_cve_map(m, product_family) for m in months]
        )

        merged: Dict[str, Set[str]] = {}
        for monthly_map in results:
            for kb, cves in monthly_map.items():
                merged.setdefault(kb, set()).update(cves)

        logger.info(
            "fetch_recent_months merged distinct_kbs=%d total_cves=%d",
            len(merged),
            sum(len(v) for v in merged.values()),
        )
        return merged

    # ------------------------------------------------------------------
    # Internal pagination helpers
    # ------------------------------------------------------------------

    async def _fetch_all_pages(self, initial_url: str) -> List[MsrcKbCveRecord]:
        """Follow @odata.nextLink pagination and collect all MsrcKbCveRecord items."""
        session = await self._get_session()
        records: List[MsrcKbCveRecord] = []
        url: Optional[str] = initial_url
        page = 0

        while url:
            page += 1
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
            except aiohttp.ClientResponseError as exc:
                logger.error(
                    "_fetch_all_pages HTTP error url=%s status=%s page=%d",
                    url,
                    exc.status,
                    page,
                )
                break
            except Exception as exc:
                logger.error(
                    "_fetch_all_pages request failed url=%s page=%d error=%s",
                    url,
                    page,
                    exc,
                )
                break

            page_records = self._parse_page(payload)
            records.extend(page_records)
            logger.debug(
                "_fetch_all_pages page=%d fetched=%d cumulative=%d",
                page,
                len(page_records),
                len(records),
            )

            url = payload.get("@odata.nextLink") or payload.get("odata.nextLink")

        return records

    def _parse_page(self, payload: dict) -> List[MsrcKbCveRecord]:
        """Parse a single OData page into a list of MsrcKbCveRecord objects."""
        items = payload.get("value") or []
        records: List[MsrcKbCveRecord] = []

        for item in items:
            try:
                cve_number = (item.get("cveNumber") or "").strip().upper()
                if not cve_number:
                    continue

                # Collect bare numeric KB article names from the kbArticles array
                kb_articles: List[str] = item.get("kbArticles") or []
                # Flatten: each element may be a dict with articleName or a plain string
                kb_names: List[str] = []
                for kb in kb_articles:
                    if isinstance(kb, dict):
                        name = (kb.get("articleName") or "").strip()
                    else:
                        name = _strip_kb_prefix(str(kb)).strip()
                    if name:
                        kb_names.append(name)

                product_family = (item.get("productFamily") or "").strip()
                severity = (item.get("severity") or "").strip()
                release_number = (item.get("releaseNumber") or "").strip()
                product_name = (item.get("product") or item.get("productName") or "").lower()
                is_mariner = "mariner" in product_name or "azure linux" in product_name

                # Emit one record per KB article name (preserves the 1-KB-many-records
                # structure for downstream deduplication)
                if kb_names:
                    for kb_name in kb_names:
                        records.append(
                            MsrcKbCveRecord(
                                cve_number=cve_number,
                                kb_article_name=kb_name,
                                product_family=product_family,
                                severity=severity,
                                release_number=release_number,
                                is_mariner=is_mariner,
                            )
                        )
                else:
                    # No KB articles on this record; still capture the CVE metadata
                    records.append(
                        MsrcKbCveRecord(
                            cve_number=cve_number,
                            kb_article_name="",
                            product_family=product_family,
                            severity=severity,
                            release_number=release_number,
                            is_mariner=is_mariner,
                        )
                    )
            except Exception as exc:
                logger.warning("_parse_page skipping malformed item error=%s item=%s", exc, item)

        return records

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MsrcSugClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
