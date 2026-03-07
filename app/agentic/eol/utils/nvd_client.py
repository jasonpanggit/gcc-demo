"""
NVD (National Vulnerability Database) API 2.0 client.

Implements NIST NVD API 2.0 for fetching CVE data with CVSS scores.
API Documentation: https://nvd.nist.gov/developers/vulnerabilities
"""
from __future__ import annotations

import os
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


class NVDClient(BaseCVEClient):
    """Client for NVD API 2.0.

    Fetches CVE data with CVSS scores from NIST National Vulnerability Database.

    Rate limits:
    - With API key: 5 requests/second
    - Without API key: 0.6 requests/second (1 request per 6 seconds)
    """

    def __init__(
        self,
        base_url: str = "https://services.nvd.nist.gov/rest/json",
        api_key: Optional[str] = None,
        **kwargs
    ):
        # Determine rate limit based on API key presence
        if api_key:
            rate_limit = 5.0  # 5 requests/sec with key
        else:
            rate_limit = 0.6  # 1 request per 6 seconds without key
            logger.warning(
                "NVD API key not provided (NVD_API_KEY env var). "
                f"Rate limited to {rate_limit} requests/second. "
                "Get a key from https://nvd.nist.gov/developers/request-an-api-key"
            )

        super().__init__(
            base_url=base_url,
            rate_limit_per_second=rate_limit,
            request_timeout=kwargs.get('request_timeout', 30),
            max_retries=kwargs.get('max_retries', 3)
        )
        self.api_key = api_key

    def _add_api_key_header(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Add API key to request headers if available."""
        if self.api_key:
            headers = kwargs.get('headers', {})
            headers['apiKey'] = self.api_key
            kwargs['headers'] = headers
        return kwargs

    async def fetch_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single CVE by ID from NVD with CVSS scores.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-0001")

        Returns:
            CVE data with CVSS v2/v3 scores, or None if not found

        Example response structure:
        {
            "vulnerabilities": [{
                "cve": {
                    "id": "CVE-2024-0001",
                    "descriptions": [...],
                    "metrics": {
                        "cvssMetricV31": [{
                            "cvssData": {
                                "baseScore": 7.5,
                                "baseSeverity": "HIGH",
                                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
                            }
                        }],
                        "cvssMetricV2": [...]
                    },
                    "weaknesses": [...],
                    "configurations": [...],
                    "references": [...]
                }
            }]
        }
        """
        cve_id = cve_id.upper()
        url = f"{self.base_url}/cves/2.0"

        params = {"cveId": cve_id}
        url += "?" + urlencode(params)

        try:
            kwargs = self._add_api_key_header({})
            data = await self._request("GET", url, **kwargs)

            if data is None or not isinstance(data, dict):
                return None

            vulnerabilities = data.get("vulnerabilities", [])
            if not vulnerabilities:
                logger.info(f"CVE {cve_id} not found in NVD")
                return None

            # NVD wraps CVE data in vulnerabilities array
            cve_data = vulnerabilities[0].get("cve", {})
            return self._normalize_cve(cve_data)

        except Exception as e:
            logger.error(f"Failed to fetch CVE {cve_id} from NVD: {e}")
            return None

    async def fetch_cves_since(
        self,
        since_date: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch CVEs modified since a given date.

        Args:
            since_date: Fetch CVEs modified after this date
            limit: Maximum number of CVEs to return (NVD max 2000 per request)

        Returns:
            List of CVE data dicts
        """
        # NVD requires ISO 8601 format with timezone
        date_str = since_date.strftime("%Y-%m-%dT%H:%M:%S.000")

        filters = {"lastModStartDate": date_str}
        if limit:
            filters["resultsPerPage"] = min(limit, 2000)  # NVD max

        return await self.search_cves(**filters)

    async def search_cves(
        self,
        query: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search CVEs with filters.

        Args:
            query: Keyword search (keywordSearch parameter)
            **filters: NVD API filters:
                - lastModStartDate: ISO 8601 date
                - lastModEndDate: ISO 8601 date
                - cvssV3Severity: LOW, MEDIUM, HIGH, CRITICAL
                - resultsPerPage: Max 2000
                - startIndex: Pagination offset

        Returns:
            List of CVE data dicts
        """
        url = f"{self.base_url}/cves/2.0"

        # Build query parameters
        params = {}
        if query:
            params["keywordSearch"] = query
        params.update(filters)

        if params:
            url += "?" + urlencode(params)

        try:
            kwargs = self._add_api_key_header({})
            data = await self._request("GET", url, **kwargs)

            if data is None or not isinstance(data, dict):
                return []

            vulnerabilities = data.get("vulnerabilities", [])
            normalized = []

            for vuln in vulnerabilities:
                cve_data = vuln.get("cve", {})
                if cve_data:
                    normalized.append(self._normalize_cve(cve_data))

            # Handle pagination
            total = data.get("totalResults", 0)
            results_per_page = filters.get("resultsPerPage", 2000)

            if total > results_per_page:
                logger.warning(
                    f"NVD search returned {total} total results, "
                    f"but only fetched {results_per_page}. "
                    f"Use startIndex parameter for pagination."
                )

            return normalized

        except Exception as e:
            logger.error(f"Failed to search CVEs from NVD: {e}")
            return []

    def _normalize_cve(self, cve_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize NVD format to internal format.

        Extracts CVSS scores, CPE configurations, and other NVD-specific data.
        """
        if not cve_data:
            return {}

        # Extract descriptions
        descriptions = cve_data.get("descriptions", [])
        description = ""
        for desc in descriptions:
            if desc.get("lang") == "en":
                description = desc.get("value", "")
                break
        if not description and descriptions:
            description = descriptions[0].get("value", "")

        # Extract CVSS scores
        metrics = cve_data.get("metrics", {})
        cvss_v3 = None
        cvss_v2 = None

        # CVSS v3.1 or v3.0
        for key in ["cvssMetricV31", "cvssMetricV30"]:
            if key in metrics and metrics[key]:
                cvss_data = metrics[key][0].get("cvssData", {})
                cvss_v3 = {
                    "version": "3.1" if key == "cvssMetricV31" else "3.0",
                    "base_score": cvss_data.get("baseScore"),
                    "base_severity": cvss_data.get("baseSeverity"),
                    "vector_string": cvss_data.get("vectorString"),
                    "exploitability_score": metrics[key][0].get("exploitabilityScore"),
                    "impact_score": metrics[key][0].get("impactScore")
                }
                break

        # CVSS v2
        if "cvssMetricV2" in metrics and metrics["cvssMetricV2"]:
            cvss_data = metrics["cvssMetricV2"][0].get("cvssData", {})
            cvss_v2 = {
                "version": "2.0",
                "base_score": cvss_data.get("baseScore"),
                "vector_string": cvss_data.get("vectorString"),
                "exploitability_score": metrics["cvssMetricV2"][0].get("exploitabilityScore"),
                "impact_score": metrics["cvssMetricV2"][0].get("impactScore")
            }
            # Map CVSS v2 score to severity
            score = cvss_v2.get("base_score", 0)
            if score >= 7.0:
                cvss_v2["base_severity"] = "HIGH"
            elif score >= 4.0:
                cvss_v2["base_severity"] = "MEDIUM"
            else:
                cvss_v2["base_severity"] = "LOW"

        # Extract CWE IDs
        cwe_ids = []
        for weakness in cve_data.get("weaknesses", []):
            for desc in weakness.get("description", []):
                cwe_value = desc.get("value", "")
                if cwe_value.startswith("CWE-"):
                    cwe_ids.append(cwe_value)

        # Extract CPE configurations (affected products)
        affected_products = []
        for config in cve_data.get("configurations", []):
            for node in config.get("nodes", []):
                for cpe_match in node.get("cpeMatch", []):
                    if cpe_match.get("vulnerable"):
                        cpe_uri = cpe_match.get("criteria", "")
                        # Parse CPE URI: cpe:2.3:a:vendor:product:version:...
                        parts = cpe_uri.split(":")
                        if len(parts) >= 5:
                            affected_products.append({
                                "vendor": parts[3] if parts[3] != "*" else "",
                                "product": parts[4] if parts[4] != "*" else "",
                                "version": cpe_match.get("versionStartIncluding") or
                                         cpe_match.get("versionEndExcluding") or
                                         parts[5] if len(parts) > 5 and parts[5] != "*" else "",
                                "cpe_uri": cpe_uri
                            })

        # Extract references
        references = []
        for ref in cve_data.get("references", []):
            url = ref.get("url", "")
            if url:
                references.append({
                    "url": url,
                    "source": ref.get("source", "nvd"),
                    "tags": ref.get("tags", [])
                })

        # Extract published/modified dates
        published = cve_data.get("published")
        last_modified = cve_data.get("lastModified")

        return {
            "cve_id": cve_data.get("id", ""),
            "source": "nvd",
            "description": description,
            "published_date": published,
            "last_modified_date": last_modified,
            "cvss_v3": cvss_v3,
            "cvss_v2": cvss_v2,
            "cwe_ids": cwe_ids,
            "affected_products": affected_products,
            "references": references,
            "raw": cve_data  # Preserve original
        }
