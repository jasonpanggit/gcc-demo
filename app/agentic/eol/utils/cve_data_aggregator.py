"""
CVE data aggregator - merges data from multiple sources.

Fetches CVE data from all sources in parallel and merges into unified model.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

try:
    from models.cve_models import (
        UnifiedCVE,
        CVSSScore,
        CVEAffectedProduct,
        CVEReference,
        CVEVendorMetadata
    )
    from utils.cve_org_client import CVEOrgClient
    from utils.nvd_client import NVDClient
    from utils.vendor_feed_client import VendorFeedClient
    from utils.github_advisory_client import GitHubAdvisoryClient
    from utils.logging_config import get_logger
    from utils.config import get_config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import (
        UnifiedCVE,
        CVSSScore,
        CVEAffectedProduct,
        CVEReference,
        CVEVendorMetadata
    )
    from app.agentic.eol.utils.cve_org_client import CVEOrgClient
    from app.agentic.eol.utils.nvd_client import NVDClient
    from app.agentic.eol.utils.vendor_feed_client import VendorFeedClient
    from app.agentic.eol.utils.github_advisory_client import GitHubAdvisoryClient
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import get_config


logger = get_logger(__name__)


def _ensure_utc_datetime(value: Any) -> Optional[datetime]:
    """Normalize string or datetime input to timezone-aware UTC datetime."""
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


class CVEDataAggregator:
    """Aggregates CVE data from multiple sources into unified model.

    Fetches data in parallel from all sources and merges with:
    - Deduplication (references, products, CWE IDs)
    - Conflict resolution (source priority)
    - Metadata preservation (vendor-specific details)
    """

    def __init__(
        self,
        cve_org_client: CVEOrgClient,
        nvd_client: NVDClient,
        vendor_feed_client: VendorFeedClient,
        github_client: GitHubAdvisoryClient,
        source_priority: Optional[Dict[str, int]] = None
    ):
        self.cve_org_client = cve_org_client
        self.nvd_client = nvd_client
        self.vendor_feed_client = vendor_feed_client
        self.github_client = github_client

        # Default source priority (lower = higher priority)
        self.source_priority = source_priority or {
            "nvd": 1,
            "cve_org": 2,
            "github": 3,
            "redhat": 4,
            "ubuntu": 4,
            "microsoft": 4
        }

    async def fetch_and_merge_cve(self, cve_id: str) -> Optional[UnifiedCVE]:
        """Fetch CVE from all sources and merge into unified model.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-0001")

        Returns:
            Unified CVE model or None if not found in any source
        """
        cve_id = cve_id.upper()
        logger.info(f"Aggregating CVE data for {cve_id} from all sources...")

        # Fetch from all sources in parallel
        results = await asyncio.gather(
            self.cve_org_client.fetch_cve(cve_id),
            self.nvd_client.fetch_cve(cve_id),
            self.vendor_feed_client.fetch_redhat_cve(cve_id),
            self.vendor_feed_client.fetch_microsoft_cve(cve_id),
            self.github_client.fetch_advisory_by_cve(cve_id),
            return_exceptions=True  # Don't fail entire fetch if one source errors
        )

        # Filter out errors and None results
        cve_data_list = []
        source_names = ["cve_org", "nvd", "redhat", "microsoft", "github"]

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Error fetching from {source_names[i]}: {result}")
            elif result is not None:
                cve_data_list.append(result)

        if not cve_data_list:
            logger.warning(f"CVE {cve_id} not found in any source")
            return None

        # Merge data from all sources
        return self.merge_cve_data(cve_data_list)

    async def fetch_cves_since(
        self,
        since_date: datetime,
        limit: Optional[int] = None
    ) -> List[UnifiedCVE]:
        """Fetch CVEs from all sources modified since date.

        Args:
            since_date: Fetch CVEs modified after this date
            limit: Maximum CVEs to return per source

        Returns:
            List of unified CVE models (may contain duplicates from different sources)
        """
        logger.info(f"Fetching CVEs modified since {since_date.isoformat()}...")

        # Fetch from sources that support date-based queries
        results = await asyncio.gather(
            self.cve_org_client.fetch_cves_since(since_date, limit),
            self.nvd_client.fetch_cves_since(since_date, limit),
            return_exceptions=True
        )

        all_cves = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Error fetching CVEs: {result}")
            elif isinstance(result, list):
                all_cves.extend(result)

        # Group by CVE ID and merge duplicates
        cve_dict: Dict[str, List[Dict[str, Any]]] = {}
        for cve_data in all_cves:
            cve_id = cve_data.get("cve_id", "").upper()
            if cve_id:
                cve_dict.setdefault(cve_id, []).append(cve_data)

        # Merge each CVE's data from multiple sources
        unified_cves = []
        for cve_id, cve_list in cve_dict.items():
            try:
                unified = self.merge_cve_data(cve_list)
                unified_cves.append(unified)
            except Exception as e:
                logger.error(f"Failed to merge CVE {cve_id}: {e}")

        logger.info(f"Fetched and merged {len(unified_cves)} CVEs since {since_date.isoformat()}")
        return unified_cves

    async def search_and_merge_cves(
        self,
        query: Optional[str] = None,
        limit: Optional[int] = 100,
        source: Optional[str] = None,
        nvd_filters: Optional[Dict[str, Any]] = None,
    ) -> List[UnifiedCVE]:
        """Run live CVE search and merge source results.

        Current live search support is strongest through NVD's keyword API.
        CVE.org is included only when source is explicitly set to cve_org and
        there is no keyword query (CVE.org API does not support text search).
        """
        requested_source = (source or "").strip().lower()
        nvd_filters = dict(nvd_filters or {})

        source_results: Dict[str, List[Dict[str, Any]]] = {}

        if requested_source in ("", "nvd"):
            nvd_results = await self.nvd_client.search_cves(
                query=query,
                limit=limit,
                **nvd_filters,
            )
            source_results["nvd"] = nvd_results

        if requested_source == "cve_org" and not query and not nvd_filters:
            cve_org_page_size = min(limit or 2000, 2000)
            cve_org_results = await self.cve_org_client.search_cves(
                state="PUBLISHED",
                resultsPerPage=cve_org_page_size,
            )
            source_results["cve_org"] = cve_org_results

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for records in source_results.values():
            for record in records:
                cve_id = (record.get("cve_id") or "").upper()
                if not cve_id:
                    continue
                grouped.setdefault(cve_id, []).append(record)

        merged: List[UnifiedCVE] = []
        for cve_id, data in grouped.items():
            try:
                merged.append(self.merge_cve_data(data))
            except Exception as e:
                logger.warning("Failed to merge live CVE %s: %s", cve_id, e)

        merged.sort(key=lambda c: c.last_modified_date, reverse=True)
        if limit is not None:
            return merged[:limit]
        return merged

    def merge_cve_data(self, cve_data_list: List[Dict[str, Any]]) -> UnifiedCVE:
        """Merge CVE data from multiple sources with conflict resolution.

        Merge strategy:
        - Source priority: nvd > cve_org > github > vendor feeds
        - CVSS scores: Use NVD (most authoritative)
        - Description: Use CVE.org (official source)
        - Dates: Use latest across sources
        - References/Products/CWEs: Deduplicate and merge
        - Vendor metadata: Preserve all (no conflicts)

        Args:
            cve_data_list: List of CVE data dicts from different sources

        Returns:
            Unified CVE model

        Raises:
            ValueError: If no valid CVE ID found
        """
        if not cve_data_list:
            raise ValueError("Cannot merge empty CVE data list")

        # Extract CVE ID (should be same across all sources)
        cve_id = None
        for data in cve_data_list:
            cve_id = data.get("cve_id")
            if cve_id:
                break

        if not cve_id:
            raise ValueError("No CVE ID found in data")

        cve_id = cve_id.upper()

        # Sort sources by priority
        sorted_data = sorted(
            cve_data_list,
            key=lambda d: self.source_priority.get(d.get("source", ""), 999)
        )

        # Merge fields with priority-based conflict resolution
        description = self._merge_field(sorted_data, "description", prefer_source="cve_org")
        published_date = self._merge_date(sorted_data, "published_date", prefer_earliest=True)
        last_modified_date = self._merge_date(sorted_data, "last_modified_date", prefer_latest=True)

        # CVSS scores: Prefer NVD
        cvss_v2 = self._extract_cvss(sorted_data, "cvss_v2", prefer_source="nvd")
        cvss_v3 = self._extract_cvss(sorted_data, "cvss_v3", prefer_source="nvd")

        # Deduplicate and merge lists
        cwe_ids = self._deduplicate_cwe_ids(sorted_data)
        affected_products = self._deduplicate_products(sorted_data)
        references = self._deduplicate_references(sorted_data)
        vendor_metadata = self._extract_vendor_metadata(sorted_data)
        sources = [d.get("source") for d in sorted_data if d.get("source")]

        # Build unified model
        return UnifiedCVE(
            cve_id=cve_id,
            description=description,
            published_date=published_date,
            last_modified_date=last_modified_date,
            cvss_v2=cvss_v2,
            cvss_v3=cvss_v3,
            cwe_ids=cwe_ids,
            affected_products=affected_products,
            references=references,
            vendor_metadata=vendor_metadata,
            sources=sources,
            last_synced=datetime.now(timezone.utc)
        )

    def _merge_field(
        self,
        data_list: List[Dict[str, Any]],
        field: str,
        prefer_source: Optional[str] = None
    ) -> str:
        """Merge a field from multiple sources with preference."""
        if prefer_source:
            # Try preferred source first
            for data in data_list:
                if data.get("source") == prefer_source:
                    value = data.get(field)
                    if value:
                        return value

        # Fallback: use first non-empty value (already sorted by priority)
        for data in data_list:
            value = data.get(field)
            if value:
                return value

        return ""

    def _merge_date(
        self,
        data_list: List[Dict[str, Any]],
        field: str,
        prefer_earliest: bool = False,
        prefer_latest: bool = False
    ) -> datetime:
        """Merge date field, preferring earliest or latest."""
        dates = []
        for data in data_list:
            value = data.get(field)
            normalized = _ensure_utc_datetime(value)
            if normalized is not None:
                dates.append(normalized)

        if not dates:
            return datetime.now(timezone.utc)

        if prefer_latest:
            return max(dates)

        return min(dates) if prefer_earliest else max(dates)

    def _extract_cvss(
        self,
        data_list: List[Dict[str, Any]],
        field: str,
        prefer_source: str = "nvd"
    ) -> Optional[CVSSScore]:
        """Extract CVSS score, preferring NVD."""
        # Try preferred source first
        for data in data_list:
            if data.get("source") == prefer_source:
                cvss_data = data.get(field)
                if cvss_data:
                    return CVSSScore(**cvss_data)

        # Fallback: use first available
        for data in data_list:
            cvss_data = data.get(field)
            if cvss_data:
                return CVSSScore(**cvss_data)

        return None

    def _deduplicate_cwe_ids(self, data_list: List[Dict[str, Any]]) -> List[str]:
        """Deduplicate CWE IDs across sources.

        Normalizes "CWE-79" and "79" to "CWE-79".
        """
        cwe_set = set()
        for data in data_list:
            for cwe_id in data.get("cwe_ids", []):
                # Normalize: ensure "CWE-" prefix
                cwe_id = cwe_id.strip()
                if cwe_id and not cwe_id.startswith("CWE-"):
                    cwe_id = f"CWE-{cwe_id}"
                cwe_set.add(cwe_id)

        return sorted(cwe_set)

    def _deduplicate_products(self, data_list: List[Dict[str, Any]]) -> List[CVEAffectedProduct]:
        """Deduplicate affected products across sources.

        Uses (vendor, product, version) as uniqueness key.
        """
        product_dict: Dict[tuple, Dict[str, Any]] = {}

        for data in data_list:
            for product in data.get("affected_products", []):
                vendor = product.get("vendor", "").lower()
                product_name = product.get("product", "").lower()
                version = product.get("version", "")

                key = (vendor, product_name, version)

                # Keep first occurrence or one with CPE URI
                if key not in product_dict or product.get("cpe_uri"):
                    product_dict[key] = product

        # Convert to CVEAffectedProduct models
        products = []
        for product_data in product_dict.values():
            try:
                products.append(CVEAffectedProduct(**product_data))
            except Exception as e:
                logger.warning(f"Failed to create affected product model: {e}")

        return products

    def _deduplicate_references(self, data_list: List[Dict[str, Any]]) -> List[CVEReference]:
        """Deduplicate references across sources.

        Normalizes URLs (lowercase domain, strip trailing slash) for deduplication.
        """
        ref_dict: Dict[str, Dict[str, Any]] = {}

        for data in data_list:
            for ref in data.get("references", []):
                url = ref.get("url", "")
                if not url:
                    continue

                # Normalize URL for deduplication
                normalized_url = self._normalize_url(url)

                # Keep first occurrence or merge tags
                if normalized_url not in ref_dict:
                    ref_dict[normalized_url] = ref
                else:
                    # Merge tags from multiple sources
                    existing_tags = set(ref_dict[normalized_url].get("tags", []))
                    new_tags = set(ref.get("tags", []))
                    ref_dict[normalized_url]["tags"] = list(existing_tags | new_tags)

        # Convert to CVEReference models
        references = []
        for ref_data in ref_dict.values():
            try:
                references.append(CVEReference(**ref_data))
            except Exception as e:
                logger.warning(f"Failed to create reference model: {e}")

        return references

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication.

        - Lowercase domain
        - Strip trailing slash
        - Keep path and query as-is
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path.rstrip('/')
            normalized = f"{parsed.scheme}://{domain}{path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized
        except Exception:
            return url.rstrip('/').lower()

    def _extract_vendor_metadata(self, data_list: List[Dict[str, Any]]) -> List[CVEVendorMetadata]:
        """Extract vendor-specific metadata from all sources.

        Preserves vendor metadata without merging (each source is separate).
        """
        metadata_list = []

        for data in data_list:
            vendor_data = data.get("vendor_metadata")
            if vendor_data:
                try:
                    # Handle dict or pre-built model
                    if isinstance(vendor_data, dict):
                        metadata_list.append(CVEVendorMetadata(**vendor_data))
                    elif isinstance(vendor_data, CVEVendorMetadata):
                        metadata_list.append(vendor_data)
                except Exception as e:
                    logger.warning(f"Failed to extract vendor metadata from {data.get('source')}: {e}")

        return metadata_list

    async def close(self):
        """Close all client sessions."""
        await asyncio.gather(
            self.cve_org_client.close(),
            self.nvd_client.close(),
            self.vendor_feed_client.close(),
            self.github_client.close(),
            return_exceptions=True
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


async def create_aggregator(config: Optional[Any] = None) -> CVEDataAggregator:
    """Factory function to create CVE data aggregator with configured clients.

    Args:
        config: Optional config object (uses get_config() if not provided)

    Returns:
        Configured CVEDataAggregator instance
    """
    if config is None:
        config = get_config()

    cve_config = config.cve_data

    # Create clients
    cve_org_client = CVEOrgClient(
        base_url=cve_config.cve_org_base_url,
        rate_limit_per_second=10.0,
        request_timeout=cve_config.request_timeout,
        max_retries=cve_config.max_retries,
        cve_api_org=cve_config.cve_org_api_org or None
    )

    nvd_client = NVDClient(
        base_url=cve_config.nvd_base_url,
        api_key=cve_config.nvd_api_key or None,
        request_timeout=cve_config.request_timeout,
        max_retries=cve_config.max_retries
    )

    vendor_client = VendorFeedClient(
        redhat_base_url=cve_config.redhat_base_url,
        ubuntu_base_url=cve_config.ubuntu_base_url,
        msrc_base_url=cve_config.msrc_base_url,
        msrc_api_key=cve_config.msrc_api_key or None,
        request_timeout=cve_config.request_timeout,
        max_retries=cve_config.max_retries
    )

    github_client = GitHubAdvisoryClient(
        graphql_url=cve_config.github_graphql_url,
        token=cve_config.github_token or None,
        request_timeout=cve_config.request_timeout
    )

    return CVEDataAggregator(
        cve_org_client=cve_org_client,
        nvd_client=nvd_client,
        vendor_feed_client=vendor_client,
        github_client=github_client,
        source_priority=cve_config.source_priority
    )
