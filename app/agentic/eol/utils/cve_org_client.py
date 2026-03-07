"""
CVE.org API v2 client for fetching CVE records.

Implements CVE.org API v2.0 endpoints for CVE 5.0 format data.
API Documentation: https://github.com/CVEProject/cvelistV5
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

try:
    from utils.cve_data_client import BaseCVEClient
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.cve_data_client import BaseCVEClient
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


class CVEOrgClient(BaseCVEClient):
    """Client for CVE.org API v2.

    Fetches CVE records in CVE 5.0 JSON format from the official CVE.org API.
    """

    def __init__(
        self,
        base_url: str = "https://cveawg.mitre.org/api",
        **kwargs
    ):
        # CVE.org doesn't require API key, rate limit is generous
        super().__init__(
            base_url=base_url,
            rate_limit_per_second=kwargs.get('rate_limit_per_second', 10.0),
            request_timeout=kwargs.get('request_timeout', 30),
            max_retries=kwargs.get('max_retries', 3)
        )
        self.cve_api_org = (kwargs.get('cve_api_org') or '').strip()

    async def fetch_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single CVE by ID from CVE.org.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-0001")

        Returns:
            CVE data in CVE 5.0 format, or None if not found

        Example response structure:
        {
            "cveId": "CVE-2024-0001",
            "state": "PUBLISHED",
            "cveMetadata": {
                "cveId": "CVE-2024-0001",
                "assignerOrgId": "...",
                "state": "PUBLISHED",
                "datePublished": "2024-01-15T10:00:00.000Z",
                "dateUpdated": "2024-01-20T15:30:00.000Z"
            },
            "containers": {
                "cna": {
                    "title": "...",
                    "descriptions": [...],
                    "affected": [...],
                    "problemTypes": [...],
                    "references": [...]
                }
            }
        }
        """
        cve_id = cve_id.upper()
        url = f"{self.base_url}/cve/{cve_id}"
        request_kwargs: Dict[str, Any] = {}
        if self.cve_api_org:
            request_kwargs["headers"] = {"CVE-API-ORG": self.cve_api_org}

        try:
            data = await self._request("GET", url, **request_kwargs)
            if data is None:
                return None

            # Extract and normalize CVE data
            return self._normalize_cve(data)

        except Exception as e:
            logger.error(f"Failed to fetch CVE {cve_id} from CVE.org: {e}")
            return None

    async def fetch_cves_since(
        self,
        since_date: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch CVEs modified since a given date.

        Args:
            since_date: Fetch CVEs updated after this date
            limit: Maximum number of CVEs to return (default: 2000, API max per request)

        Returns:
            List of CVE data dicts
        """
        # Format date as ISO 8601
        date_str = since_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        params = {
            "dateUpdated": date_str,
            "state": "PUBLISHED"
        }

        if limit:
            params["resultsPerPage"] = min(limit, 2000)  # API max

        return await self.search_cves(**params)

    async def search_cves(
        self,
        query: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search CVEs with filters.

        Args:
            query: Not used (CVE.org doesn't support text search)
            **filters: API filters:
                - dateUpdated: ISO 8601 date string
                - state: PUBLISHED, REJECTED, etc.
                - resultsPerPage: Max 2000

        Returns:
            List of CVE data dicts
        """
        if not self.cve_api_org:
            logger.info("Skipping CVE.org list search: CVE_API_ORG not configured")
            return []

        # CVE list endpoint (requires CVE-API-ORG header)
        url = f"{self.base_url}/cve"

        # Build query string
        if filters:
            url += "?" + urlencode(filters)

        try:
            data = await self._request("GET", url, headers={"CVE-API-ORG": self.cve_api_org})
            if data is None or not isinstance(data, dict):
                return []

            # CVE.org list responses can vary by deployment shape.
            cves = data.get("cveRecords") or data.get("vulnerabilities") or data.get("cves") or []
            if cves and isinstance(cves[0], dict) and "cve" in cves[0]:
                cves = [row.get("cve") for row in cves if isinstance(row, dict) and row.get("cve")]

            normalized = [self._normalize_cve(cve) for cve in cves if cve]

            # Handle pagination (API returns totalResults and currentPage)
            total = data.get("totalResults", 0)
            results_per_page = filters.get("resultsPerPage", 2000)

            if total > results_per_page:
                logger.warning(
                    f"CVE.org search returned {total} total results, "
                    f"but only fetched {results_per_page}. "
                    f"Implement pagination if more results needed."
                )

            return normalized

        except Exception as e:
            logger.error(f"Failed to search CVEs from CVE.org: {e}")
            return []

    def _normalize_cve(self, cve_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize CVE 5.0 format to internal format.

        Extracts key fields from CVE 5.0 JSON for easier processing.
        """
        if not cve_data:
            return {}

        cve_metadata = cve_data.get("cveMetadata", {})
        containers = cve_data.get("containers", {})
        cna = containers.get("cna", {})  # CVE Numbering Authority data

        # Extract descriptions
        descriptions = cna.get("descriptions", [])
        description = ""
        for desc in descriptions:
            if desc.get("lang") == "en":
                description = desc.get("value", "")
                break
        if not description and descriptions:
            description = descriptions[0].get("value", "")

        # Extract affected products
        affected_products = []
        for affected in cna.get("affected", []):
            vendor = affected.get("vendor", "")
            product = affected.get("product", "")
            versions = affected.get("versions", [])

            for version_info in versions:
                version = version_info.get("version", "")
                affected_products.append({
                    "vendor": vendor,
                    "product": product,
                    "version": version
                })

        # Extract CWE IDs
        cwe_ids = []
        for problem in cna.get("problemTypes", []):
            for desc in problem.get("descriptions", []):
                cwe_id = desc.get("cweId")
                if cwe_id:
                    cwe_ids.append(cwe_id)

        # Extract references
        references = []
        for ref in cna.get("references", []):
            url = ref.get("url", "")
            if url:
                references.append({
                    "url": url,
                    "source": "cve_org",
                    "tags": ref.get("tags", [])
                })

        # Build normalized structure
        return {
            "cve_id": cve_metadata.get("cveId", ""),
            "source": "cve_org",
            "state": cve_metadata.get("state", ""),
            "description": description,
            "published_date": cve_metadata.get("datePublished"),
            "last_modified_date": cve_metadata.get("dateUpdated"),
            "affected_products": affected_products,
            "cwe_ids": cwe_ids,
            "references": references,
            "raw": cve_data  # Preserve original for detailed analysis
        }
