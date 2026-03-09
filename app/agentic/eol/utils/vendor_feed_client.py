"""
Vendor security feed clients for Red Hat, Ubuntu, and Microsoft.

Fetches vendor-specific CVE metadata and security bulletins.
"""
from __future__ import annotations

import os
import re
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


MSRC_NAMESPACES = {
    "cvrf": "http://www.icasi.org/CVRF/schema/cvrf/1.1",
    "vuln": "http://www.icasi.org/CVRF/schema/vuln/1.1",
}
KB_PATTERN = re.compile(r"\bKB\d{6,8}\b", re.IGNORECASE)
MSRC_NUMERIC_UPDATE_PATTERN = re.compile(r"\b\d{6,8}\b")
MSRC_UPDATE_ID_PATTERN = re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b")
MSRC_MONTH_ABBREVIATIONS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


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
        self._msrc_update_cache: Dict[str, Dict[str, Any]] = {}
        self._msrc_cvrf_cache: Dict[str, str] = {}

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
            Microsoft CVE metadata or None if not found

        MSRC v3 supports unauthenticated CVE lookup through /updates/{cve_id}.
        The update summary points to the monthly CVRF bulletin that contains the
        detailed remediation and KB data for the vulnerability.
        """
        cve_id = cve_id.upper()
        updates_url = f"{self.msrc_base_url}/updates/{cve_id}"

        try:
            session = await self._get_session()
            headers = self._build_msrc_headers(accept="application/json")

            async with session.get(updates_url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"CVE {cve_id} not found in MSRC database")
                    return None

                response.raise_for_status()

                updates_payload = await response.json()

            updates = updates_payload.get("value") or []
            if not updates:
                logger.debug(f"MSRC returned no bulletin for {cve_id}")
                return None

            cvrf_url = self._extract_cvrf_url(updates[0])
            if not cvrf_url:
                logger.warning(f"MSRC bulletin for {cve_id} did not include a CVRF URL")
                return self._normalize_msrc_cve(updates[0])

            xml_headers = self._build_msrc_headers(accept="application/xml")
            async with session.get(cvrf_url, headers=xml_headers) as response:
                if response.status == 404:
                    logger.debug(f"MSRC CVRF bulletin missing for {cve_id}: {cvrf_url}")
                    return self._normalize_msrc_cve(updates[0])

                response.raise_for_status()
                xml_text = await response.text()

            result = self._parse_msrc_xml(
                xml_text,
                cve_id,
                update_summary=updates[0],
                cvrf_url=cvrf_url,
            )
            vendor_metadata = result.get("vendor_metadata") or {}
            if not vendor_metadata.get("kb_numbers"):
                logger.warning(
                    "MSRC enrichment for %s returned summary-only metadata from %s",
                    cve_id,
                    cvrf_url,
                )
            return result

        except Exception as e:
            logger.warning(f"Failed to fetch {cve_id} from MSRC: {e}")
            return None

    async def fetch_microsoft_cves_for_kb(
        self,
        kb_number: str,
        *,
        update_id: Optional[str] = None,
        patch_name: Optional[str] = None,
        published_date: Optional[str] = None,
    ) -> List[str]:
        """Return CVE IDs from an MSRC monthly bulletin that reference the supplied KB."""
        normalized_kb = self._normalize_single_kb(kb_number)
        if not normalized_kb:
            return []

        resolved_update_id = update_id or self._infer_msrc_update_id(patch_name=patch_name, published_date=published_date)
        if not resolved_update_id:
            logger.debug("Unable to infer MSRC update ID for KB %s", normalized_kb)
            return []

        try:
            update_summary = await self._fetch_msrc_update_summary(resolved_update_id)
            cvrf_url = self._extract_cvrf_url(update_summary)
            if not cvrf_url:
                logger.debug("MSRC update %s did not include a CVRF URL", resolved_update_id)
                return []

            xml_text = await self._fetch_msrc_cvrf_xml(cvrf_url)
            return self._extract_cve_ids_for_kb_from_xml(xml_text, normalized_kb)
        except Exception as e:
            logger.warning("Failed to fetch MSRC CVEs for %s via %s: %s", normalized_kb, resolved_update_id, e)
            return []

    def _build_msrc_headers(self, *, accept: str) -> Dict[str, str]:
        """Build headers for MSRC requests.

        MSRC v3 works without an API key, but if one is configured we send it for
        backward compatibility with older deployments.
        """
        headers = {"Accept": accept}
        if self.msrc_api_key:
            headers["api-key"] = self.msrc_api_key
        return headers

    async def _fetch_msrc_update_summary(self, update_id: str) -> Dict[str, Any]:
        cached = self._msrc_update_cache.get(update_id)
        if cached is not None:
            return cached

        session = await self._get_session()
        headers = self._build_msrc_headers(accept="application/json")
        updates_url = f"{self.msrc_base_url}/updates/{update_id}"

        async with session.get(updates_url, headers=headers) as response:
            response.raise_for_status()
            payload = await response.json()

        updates = payload.get("value") or []
        if not updates:
            raise ValueError(f"MSRC returned no update summary for {update_id}")

        self._msrc_update_cache[update_id] = updates[0]
        return updates[0]

    async def _fetch_msrc_cvrf_xml(self, cvrf_url: str) -> str:
        cached = self._msrc_cvrf_cache.get(cvrf_url)
        if cached is not None:
            return cached

        session = await self._get_session()
        headers = self._build_msrc_headers(accept="application/xml")
        async with session.get(cvrf_url, headers=headers) as response:
            response.raise_for_status()
            xml_text = await response.text()

        self._msrc_cvrf_cache[cvrf_url] = xml_text
        return xml_text

    def _extract_cvrf_url(self, update_summary: Dict[str, Any]) -> Optional[str]:
        """Return the CVRF URL from an MSRC update summary payload."""
        return (
            update_summary.get("CvrfUrl")
            or update_summary.get("cvrfUrl")
            or update_summary.get("url")
        )

    def _normalize_single_kb(self, kb_number: Optional[str]) -> Optional[str]:
        if not kb_number:
            return None

        text = str(kb_number).strip()
        explicit = KB_PATTERN.search(text)
        if explicit:
            return explicit.group(0).upper()

        numeric = MSRC_NUMERIC_UPDATE_PATTERN.search(text)
        if numeric:
            return f"KB{numeric.group(0)}"

        return None

    def _infer_msrc_update_id(
        self,
        *,
        patch_name: Optional[str] = None,
        published_date: Optional[str] = None,
    ) -> Optional[str]:
        if patch_name:
            match = MSRC_UPDATE_ID_PATTERN.search(patch_name)
            if match:
                year = match.group(1)
                month = int(match.group(2))
                return f"{year}-{MSRC_MONTH_ABBREVIATIONS[month]}"

        if published_date:
            parsed = published_date.strip()
            try:
                published = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
                return f"{published.year}-{MSRC_MONTH_ABBREVIATIONS[published.month]}"
            except ValueError:
                return None

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
        kb_numbers = self._normalize_kb_list(data.get("kbArticles", []))
        update_id = data.get("ID") or data.get("Alias")
        return {
            "cve_id": data.get("cveId") or data.get("CVE", ""),
            "source": "microsoft",
            "description": data.get("description", ""),
            "vendor_metadata": {
                "source": "microsoft",
                "fix_available": bool(kb_numbers),
                "advisory_id": update_id,
                "kb_numbers": kb_numbers,
                "severity": data.get("severity"),
                "exploitability": data.get("exploitability", ""),
                "impact": data.get("impact", ""),
                "document_title": data.get("DocumentTitle"),
                "update_id": update_id,
                "cvrf_url": data.get("CvrfUrl") or data.get("cvrfUrl"),
                "metadata": data  # Preserve full response
            }
        }

    def _parse_msrc_xml(
        self,
        xml_text: str,
        cve_id: str,
        *,
        update_summary: Optional[Dict[str, Any]] = None,
        cvrf_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse MSRC CVRF XML format."""
        try:
            root = ET.fromstring(xml_text)
            vulnerability = self._find_vulnerability(root, cve_id)
            if vulnerability is None:
                logger.warning(f"CVE {cve_id} not present in MSRC CVRF bulletin {cvrf_url}")
                logger.debug(f"CVE {cve_id} not present in CVRF bulletin")
                if update_summary:
                    fallback = self._normalize_msrc_cve(update_summary)
                    fallback.setdefault("vendor_metadata", {})["format"] = "cvrf_xml"
                    if cvrf_url:
                        fallback["vendor_metadata"]["cvrf_url"] = cvrf_url
                    return fallback
                return {}

            note_map = self._extract_note_map(vulnerability)
            title = vulnerability.findtext("vuln:Title", namespaces=MSRC_NAMESPACES) or ""
            severity = self._extract_threat_description(vulnerability, "Severity")
            impact = self._extract_threat_description(vulnerability, "Impact")
            exploitability = self._extract_threat_description(vulnerability, "Exploit Status")
            kb_numbers = self._extract_kb_numbers_from_vulnerability(vulnerability)
            update_id = (update_summary or {}).get("ID") or (update_summary or {}).get("Alias")
            document_title = (update_summary or {}).get("DocumentTitle")

            logger.info(
                "MSRC enrichment resolved for %s: update_id=%s kb_count=%d severity=%s",
                cve_id,
                update_id or "unknown",
                len(kb_numbers),
                severity or "unknown",
            )

            return {
                "cve_id": cve_id,
                "source": "microsoft",
                "description": note_map.get("Description") or title or "MSRC CVE data",
                "vendor_metadata": {
                    "source": "microsoft",
                    "fix_available": bool(kb_numbers),
                    "advisory_id": update_id,
                    "title": title,
                    "kb_numbers": kb_numbers,
                    "kbArticles": kb_numbers,
                    "severity": severity,
                    "impact": impact,
                    "exploitability": exploitability,
                    "notes": note_map,
                    "update_id": update_id,
                    "document_title": document_title,
                    "cvrf_url": cvrf_url,
                    "format": "cvrf_xml",
                    "metadata": update_summary or {},
                    "raw_xml": xml_text,
                }
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse MSRC XML for {cve_id}: {e}")
            return {}

    def _find_vulnerability(self, root: ET.Element, cve_id: str) -> Optional[ET.Element]:
        """Locate a vulnerability node by CVE ID."""
        for vulnerability in root.findall('.//vuln:Vulnerability', MSRC_NAMESPACES):
            xml_cve_id = vulnerability.findtext('vuln:CVE', namespaces=MSRC_NAMESPACES)
            if (xml_cve_id or '').upper() == cve_id:
                return vulnerability
        return None

    def _extract_note_map(self, vulnerability: ET.Element) -> Dict[str, str]:
        """Collect the first note value for each MSRC note title."""
        notes: Dict[str, str] = {}
        for note in vulnerability.findall('vuln:Notes/vuln:Note', MSRC_NAMESPACES):
            title = (note.attrib.get('Title') or '').strip()
            text = (''.join(note.itertext()) or '').strip()
            if title and text and title not in notes:
                notes[title] = text
        return notes

    def _extract_threat_description(self, vulnerability: ET.Element, threat_type: str) -> str:
        """Return the first threat description for the requested threat type."""
        for threat in vulnerability.findall('vuln:Threats/vuln:Threat', MSRC_NAMESPACES):
            if (threat.attrib.get('Type') or '').strip().lower() != threat_type.lower():
                continue
            description = threat.findtext('vuln:Description', namespaces=MSRC_NAMESPACES)
            if description:
                return description.strip()
        return ''

    def _extract_kb_numbers_from_vulnerability(self, vulnerability: ET.Element) -> List[str]:
        """Extract unique KB identifiers from the vulnerability XML subtree."""
        kb_numbers = self._extract_explicit_kb_numbers(vulnerability.itertext())
        remediation_kbs = self._extract_kb_numbers_from_remediations(vulnerability)
        for kb_number in remediation_kbs:
            if kb_number not in kb_numbers:
                kb_numbers.append(kb_number)
        return kb_numbers

    def _extract_cve_ids_for_kb_from_xml(self, xml_text: str, kb_number: str) -> List[str]:
        normalized_kb = self._normalize_single_kb(kb_number)
        if not normalized_kb:
            return []

        root = ET.fromstring(xml_text)
        cve_ids: List[str] = []
        seen = set()
        for vulnerability in root.findall('.//vuln:Vulnerability', MSRC_NAMESPACES):
            kb_numbers = self._extract_kb_numbers_from_vulnerability(vulnerability)
            if normalized_kb not in kb_numbers:
                continue

            cve_id = (vulnerability.findtext('vuln:CVE', namespaces=MSRC_NAMESPACES) or '').upper()
            if not cve_id or cve_id in seen:
                continue
            seen.add(cve_id)
            cve_ids.append(cve_id)

        return cve_ids

    def _extract_explicit_kb_numbers(self, texts: Any) -> List[str]:
        """Extract unique explicit KB identifiers from an iterable of strings."""
        kb_numbers: List[str] = []
        seen = set()
        for text in texts:
            for match in KB_PATTERN.findall(text or ''):
                normalized = match.upper()
                if normalized in seen:
                    continue
                seen.add(normalized)
                kb_numbers.append(normalized)
        return kb_numbers

    def _extract_kb_numbers_from_remediations(self, vulnerability: ET.Element) -> List[str]:
        """Extract KB identifiers from remediation nodes, including numeric-only legacy descriptions."""
        kb_numbers: List[str] = []
        seen = set()

        for remediation in vulnerability.findall('vuln:Remediations/vuln:Remediation', MSRC_NAMESPACES):
            subtype = (remediation.findtext('vuln:SubType', namespaces=MSRC_NAMESPACES) or '').strip().lower()
            remediation_type = (remediation.attrib.get('Type') or '').strip().lower()
            if remediation_type != 'vendor fix':
                continue

            description = (remediation.findtext('vuln:Description', namespaces=MSRC_NAMESPACES) or '').strip()
            url = (remediation.findtext('vuln:URL', namespaces=MSRC_NAMESPACES) or '').strip()

            for explicit in self._extract_explicit_kb_numbers([description, url]):
                if explicit not in seen:
                    seen.add(explicit)
                    kb_numbers.append(explicit)

            if kb_numbers and description.upper().startswith('KB'):
                continue

            if subtype not in {
                'security update',
                'security only',
                'monthly rollup',
                'ie cumulative',
                'servicing stack update',
            }:
                continue

            for match in MSRC_NUMERIC_UPDATE_PATTERN.findall(description):
                normalized = f"KB{match}"
                if normalized in seen:
                    continue
                seen.add(normalized)
                kb_numbers.append(normalized)

        return kb_numbers

    def _normalize_kb_list(self, values: Any) -> List[str]:
        """Normalize KB values into a unique, ordered list."""
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return []

        normalized: List[str] = []
        seen = set()
        for value in values:
            for match in KB_PATTERN.findall(str(value) or ""):
                kb_number = match.upper()
                if kb_number in seen:
                    continue
                seen.add(kb_number)
                normalized.append(kb_number)
        return normalized

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
