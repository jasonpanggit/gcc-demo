"""
EOL Status Agent - Queries eolstatus.com product pages for EOL information
"""
import re
import json
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from .base_eol_agent import BaseEOLAgent

try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


class EOLStatusAgent(BaseEOLAgent):
    """Agent for extracting EOL data from eolstatus.com"""

    _products_cache: List[str] = []
    _products_cache_ts: Optional[datetime] = None
    _products_cache_ttl = timedelta(hours=6)

    def __init__(self):
        super().__init__("eolstatus")
        self.agent_name = "eolstatus"
        self.base_url = "https://eolstatus.com"
        self.products_url = f"{self.base_url}/products"
        self.timeout = 15

        # Agent-level caching disabled - orchestrator uses eol_inventory as single source of truth
        self.cosmos_cache = None

    async def _get_cached_data(self, software_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        return None

    async def _cache_data(self, software_name: str, version: Optional[str], data: Dict[str, Any]):
        """Agent-level caching disabled - eol_inventory is the single source of truth"""
        pass

    async def purge_cache(self, software_name: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        """Agent-level caching disabled - use eol_inventory for cache management"""
        return {"success": True, "deleted_count": 0, "message": "Agent-level caching disabled - use eol_inventory"}

    async def get_eol_data(self, software_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get EOL data from eolstatus.com using product page JSON-LD"""
        if not software_name:
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="software_name is required",
                error_code="missing_software_name",
            )

        cached_data = await self._get_cached_data(software_name, version)
        if cached_data:
            return cached_data

        slug, match_method = self._find_best_slug(software_name, version)
        if not slug:
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="No matching product found on eolstatus.com",
                error_code="no_match",
            )

        product_url = f"{self.base_url}/product/{slug}"
        html = self._fetch_html(product_url)
        if not html:
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="Failed to retrieve product page",
                error_code="fetch_failed",
            )

        json_ld = self._extract_product_jsonld(html)
        if not json_ld:
            return self.create_failure_response(
                software_name=software_name,
                version=version,
                error_message="No JSON-LD product data found",
                error_code="no_jsonld",
            )

        props = self._extract_additional_properties(json_ld)
        eol_date = self._normalize_date(props.get("end of life date"))
        support_end_date = self._normalize_date(props.get("end of support life date"))
        release_date = self._normalize_date(props.get("release date"))

        status = props.get("status")
        resolved_version = props.get("version") or version
        vendor_name = self._extract_vendor_name(json_ld)
        category = json_ld.get("category")
        minor_versions = self._collect_minor_versions(
            software_name,
            version,
            selected_slug=slug,
            selected_json_ld=json_ld,
        )

        result = self.create_success_response(
            software_name=software_name,
            version=resolved_version,
            eol_date=eol_date,
            support_end_date=support_end_date,
            release_date=release_date,
            status=status,
            confidence=0.7,
            source_url=product_url,
            additional_data={
                "vendor": vendor_name,
                "category": category,
                "product_name": json_ld.get("name"),
                "product_slug": slug,
                "match_method": match_method,
                "days_remaining": props.get("days remaining"),
                "minor_versions": minor_versions,
                "data_source": "eolstatus",
            },
        )

        await self._cache_data(software_name, version, result)
        return result

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning("EOLStatus request failed (%s): %s", response.status_code, url)
                return None
            return response.text
        except Exception as exc:
            logger.warning("EOLStatus request error for %s: %s", url, exc)
            return None

    def _get_product_slugs(self) -> List[str]:
        now = datetime.utcnow()
        if self._products_cache_ts and now - self._products_cache_ts < self._products_cache_ttl:
            return list(self._products_cache)

        html = self._fetch_html(self.products_url)
        if not html:
            return list(self._products_cache)

        slugs = sorted(set(re.findall(r"/product/([a-z0-9-]+)", html)))
        if slugs:
            self._products_cache = slugs
            self._products_cache_ts = now
        return slugs

    def _find_best_slug(self, software_name: str, version: Optional[str]) -> (Optional[str], str):
        slugs = self._get_product_slugs()
        if not slugs:
            return None, "no_index"

        software_norm = self._normalize_for_slug(software_name)
        version_norm = self._normalize_version_for_slug(version)
        best_slug = None
        best_score = -1

        for slug in slugs:
            score = 0
            if software_norm and software_norm in slug:
                score += 3
            name_tokens = [t for t in re.split(r"[-_\s]+", software_norm) if t]
            for token in name_tokens:
                if token in slug:
                    score += 1
            if version_norm and version_norm in slug:
                score += 4

            if score > best_score:
                best_score = score
                best_slug = slug

        if best_score <= 0:
            return None, "no_match"

        match_method = "name" if not version_norm else "name_version"
        if version_norm and version_norm in (best_slug or ""):
            match_method = "name_version"
        return best_slug, match_method

    def _collect_minor_versions(
        self,
        software_name: str,
        version: Optional[str],
        *,
        selected_slug: Optional[str] = None,
        selected_json_ld: Optional[Dict[str, Any]] = None,
        max_results: int = 10,
    ) -> List[str]:
        """Collect minor versions for a major-only query from eolstatus product slugs."""
        if not version or "." in version or "-" in version:
            return []

        major = version.strip()
        if not major.isdigit():
            return []

        slugs = self._get_product_slugs()
        if not slugs:
            return []

        software_norm = self._normalize_for_slug(software_name)
        major_pattern = re.compile(rf"(?:^|-)({re.escape(major)})(?:-|$)")

        candidate_slugs = [
            slug for slug in slugs
            if software_norm and software_norm in slug and major_pattern.search(slug)
        ]

        versions = []
        seen = set()

        for slug in candidate_slugs[:max_results]:
            json_ld = None
            if selected_slug and slug == selected_slug:
                json_ld = selected_json_ld
            if json_ld is None:
                json_ld = self._fetch_product_jsonld(slug)
            if not json_ld:
                continue

            props = self._extract_additional_properties(json_ld)
            cycle_version = props.get("version")
            if not cycle_version:
                continue
            if cycle_version not in seen:
                seen.add(cycle_version)
                versions.append(cycle_version)

        return self._sort_versions(versions)

    def _fetch_product_jsonld(self, slug: str) -> Optional[Dict[str, Any]]:
        product_url = f"{self.base_url}/product/{slug}"
        html = self._fetch_html(product_url)
        if not html:
            return None
        return self._extract_product_jsonld(html)

    def _sort_versions(self, versions: List[str]) -> List[str]:
        def sort_key(value: str):
            parts = re.findall(r"\d+", value)
            numeric = [int(p) for p in parts[:3]] if parts else [0]
            padded = numeric + [0] * (3 - len(numeric))
            return tuple(padded[:3])

        return sorted(versions, key=sort_key)

    def _normalize_for_slug(self, text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower())
        return cleaned.strip("-")

    def _normalize_version_for_slug(self, version: Optional[str]) -> str:
        if not version:
            return ""
        cleaned = version.lower().strip()
        cleaned = cleaned.replace(".", "-")
        cleaned = re.sub(r"\s+", "-", cleaned)
        cleaned = re.sub(r"[^a-z0-9-]+", "", cleaned)
        return cleaned.strip("-")

    def _extract_product_jsonld(self, html: str) -> Optional[Dict[str, Any]]:
        scripts = re.findall(
            r"<script[^>]+type=\"application/ld\+json\"[^>]*>(.*?)</script>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for script in scripts:
            try:
                data = json.loads(script.strip())
            except json.JSONDecodeError:
                continue

            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return None

    def _extract_additional_properties(self, json_ld: Dict[str, Any]) -> Dict[str, str]:
        props: Dict[str, str] = {}
        additional_props = json_ld.get("additionalProperty") or []
        if isinstance(additional_props, dict):
            additional_props = [additional_props]

        for item in additional_props:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if not name or value is None:
                continue
            normalized = name.strip().lower()
            props[normalized] = str(value).strip()
        return props

    def _extract_vendor_name(self, json_ld: Dict[str, Any]) -> Optional[str]:
        brand = json_ld.get("brand")
        if isinstance(brand, dict):
            return brand.get("name")
        return None

    def _normalize_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        candidate = value.strip()
        if not candidate or "not set" in candidate.lower() or "unknown" in candidate.lower():
            return None

        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
        return candidate if re.match(r"\d{4}-\d{2}-\d{2}", candidate) else None
