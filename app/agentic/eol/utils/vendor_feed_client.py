"""
Vendor security feed clients for Red Hat, Ubuntu, and Microsoft.

Fetches vendor-specific CVE metadata and security bulletins.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import aiohttp

try:
    from utils.cve_data_client import BaseCVEClient
    from utils.logging_config import get_logger
    from utils.config import get_config
except ModuleNotFoundError:
    from app.agentic.eol.utils.cve_data_client import BaseCVEClient
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import get_config


logger = get_logger(__name__)


class VendorFeedClient:
    """Client for vendor-specific security feeds.

    Fetches CVE metadata from Red Hat, Ubuntu, and Microsoft security APIs.
    Each vendor has unique format and authentication requirements.
    """

    def __init__(
        self,
        redhat_base_url: str,
        ubuntu_base_url: str,
        msrc_base_url: str,
        msrc_api_key: Optional[str] = None,
        request_timeout: int = 30,
        max_retries: int = 3
    ):
        self.redhat_base_url = redhat_base_url.rstrip('/')
        self.ubuntu_base_url = ubuntu_base_url.rstrip('/')
        self.msrc_base_url = msrc_base_url.rstrip('/')
        self.msrc_api_key = msrc_api_key
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_redhat_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch CVE metadata from Red Hat Security Data API.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-0001")

        Returns:
            Red Hat CVE metadata or None if not found/not affecting Red Hat products

        Example response:
        {
            "CVE": "CVE-2024-0001",
            "severity": "Important",
            "public_date": "2024-01-15T00:00:00",
            "bugzilla": {"description": "...", "id": "123456"},
            "affected_packages": [...],
            "package_state": [...]
        }
        """
        cve_id = cve_id.upper()
        url = f"{self.redhat_base_url}/cve/{cve_id}.json"

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 404:
                    logger.debug(f"CVE {cve_id} not found in Red Hat database")
                    return None

                response.raise_for_status()
                data = await response.json()

                return self._normalize_redhat_cve(data)

        except Exception as e:
            logger.warning(f"Failed to fetch {cve_id} from Red Hat: {e}")
            return None

    async def fetch_ubuntu_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch CVE metadata from Ubuntu Security Notices.

        Note: Ubuntu API requires USN ID, not CVE ID. This method is a placeholder
        for future implementation that would:
        1. Scrape USN RSS feed for CVE-to-USN mappings
        2. Fetch USN details by USN ID

        Args:
            cve_id: CVE identifier

        Returns:
            None (not implemented - requires RSS scraping)
        """
        logger.debug(f"Ubuntu CVE lookup not implemented (requires USN mapping): {cve_id}")
        return None

    async def fetch_microsoft_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch CVE metadata from Microsoft Security Response Center (MSRC) API.

        Args:
            cve_id: CVE identifier

        Returns:
            Microsoft CVE metadata or None if not found/API key missing

        Note: MSRC API returns CVRF (Common Vulnerability Reporting Framework) XML format
        """
        if not self.msrc_api_key:
            logger.debug(f"MSRC API key not configured, skipping Microsoft lookup for {cve_id}")
            return None

        cve_id = cve_id.upper()
        # MSRC API endpoint format
        url = f"{self.msrc_base_url}/cvrf/{cve_id}"

        try:
            session = await self._get_session()
            headers = {"Accept": "application/json", "api-key": self.msrc_api_key}

            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"CVE {cve_id} not found in MSRC database")
                    return None

                if response.status == 401:
                    logger.error("MSRC API key invalid (401 Unauthorized)")
                    return None

                response.raise_for_status()

                # MSRC can return JSON or XML depending on Accept header
                content_type = response.headers.get('Content-Type', '')

                if 'json' in content_type:
                    data = await response.json()
                    return self._normalize_msrc_cve(data)
                elif 'xml' in content_type:
                    xml_text = await response.text()
                    return self._parse_msrc_xml(xml_text, cve_id)
                else:
                    logger.warning(f"Unexpected MSRC content type: {content_type}")
                    return None

        except Exception as e:
            logger.warning(f"Failed to fetch {cve_id} from MSRC: {e}")
            return None

    def _normalize_redhat_cve(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Red Hat CVE format to internal format."""
        if not data:
            return {}

        # Extract affected packages
        affected_packages = []
        for pkg_state in data.get("package_state", []):
            package_name = pkg_state.get("package_name", "")
            fix_state = pkg_state.get("fix_state", "")
            affected_packages.append({
                "name": package_name,
                "fix_state": fix_state,
                "product_name": pkg_state.get("product_name", "")
            })

        # Extract RHSA references
        advisories = []
        for detail in data.get("details", []):
            if detail.startswith("RH"):
                advisories.append(detail)

        return {
            "cve_id": data.get("CVE", ""),
            "source": "redhat",
            "severity": data.get("severity", ""),
            "public_date": data.get("public_date"),
            "description": data.get("bugzilla", {}).get("description", ""),
            "vendor_metadata": {
                "source": "redhat",
                "affected_packages": affected_packages,
                "advisories": advisories,
                "bugzilla_id": data.get("bugzilla", {}).get("id"),
                "fix_available": any(p.get("fix_state") == "Fixed" for p in affected_packages)
            }
        }

    def _normalize_msrc_cve(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Microsoft MSRC JSON format to internal format."""
        if not data:
            return {}

        # MSRC JSON structure varies - extract what's available
        return {
            "cve_id": data.get("cveId") or data.get("CVE", ""),
            "source": "microsoft",
            "description": data.get("description", ""),
            "vendor_metadata": {
                "source": "microsoft",
                "kb_numbers": data.get("kbArticles", []),
                "exploitability": data.get("exploitability", ""),
                "impact": data.get("impact", ""),
                "metadata": data  # Preserve full response
            }
        }

    def _parse_msrc_xml(self, xml_text: str, cve_id: str) -> Dict[str, Any]:
        """Parse MSRC CVRF XML format."""
        try:
            root = ET.fromstring(xml_text)

            # CVRF XML is complex - extract basics for now
            # Full parser would need namespace handling and deep traversal
            return {
                "cve_id": cve_id,
                "source": "microsoft",
                "description": "MSRC CVE data (XML format)",
                "vendor_metadata": {
                    "source": "microsoft",
                    "format": "cvrf_xml",
                    "raw_xml": xml_text  # Preserve for detailed parsing if needed
                }
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse MSRC XML for {cve_id}: {e}")
            return {}

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
