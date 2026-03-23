"""Generic vendor parsing utilities.

Provides a unified interface for vendor URL parsing that works across
all vendor agents without vendor-specific code branches.
"""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def parse_vendor_urls_generic(
    agent: Any,
    vendor_key: str,
    active_urls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generic vendor URL parsing that works for any agent.

    This function attempts multiple strategies to extract EOL data from
    vendor agent URLs, trying the most efficient methods first:

    1. fetch_all_from_url() - returns multiple versions per URL (preferred)
    2. fetch_from_url() - returns single version per URL (fallback)
    3. Direct get_eol_data() call with software hint (last resort)

    Args:
        agent: The vendor agent instance (must have eol_urls attribute)
        vendor_key: Vendor identifier (e.g., "microsoft", "redhat")
        active_urls: List of active URL dicts from agent.urls

    Returns:
        List of parsing run dictionaries with software_name, version, eol_date, etc.
    """
    runs: List[Dict[str, Any]] = []

    for url_entry in active_urls:
        url = url_entry.get("url")
        description = url_entry.get("description", "")

        # Infer software hint from URL or description
        software_hint = _infer_software_hint(url, description, vendor_key)

        # Strategy 1: Try fetch_all_from_url (returns multiple versions)
        if hasattr(agent, "fetch_all_from_url") and callable(agent.fetch_all_from_url):
            try:
                records = await agent.fetch_all_from_url(url, software_hint)
                if records:  # Only skip fallback if we got actual data
                    for record in records:
                        runs.append(_format_vendor_record(
                            record=record,
                            software_hint=software_hint,
                            url=url,
                            vendor_key=vendor_key,
                            mode="fetch_all_from_url"
                        ))
                    logger.info(f"Parsed {len(records)} records from {url} via fetch_all_from_url")
                    continue  # Skip to next URL only if records found
            except Exception as exc:
                logger.warning(f"fetch_all_from_url failed for {url}: {exc}")

        # If fetch_all_from_url returned empty list, fall through to Strategy 2/3

        # Strategy 2: Try fetch_from_url (returns single version)
        if hasattr(agent, "fetch_from_url") and callable(agent.fetch_from_url):
            try:
                result = await agent.fetch_from_url(url, software_hint)
                if result and result.get("success"):
                    data_block = result.get("data", {})
                    runs.append({
                        "software_name": data_block.get("software_name") or software_hint,
                        "version": data_block.get("version"),
                        "eol_date": data_block.get("eol_date"),
                        "support_end_date": data_block.get("support_end_date"),
                        "agent_used": vendor_key,
                        "confidence": data_block.get("confidence") or result.get("confidence") or 0.85,
                        "source_url": url,
                        "success": True,
                        "mode": "fetch_from_url",
                        "raw": result,
                    })
                    logger.info(f"Parsed 1 record from {url} via fetch_from_url")
                    continue
            except Exception as exc:
                logger.warning(f"fetch_from_url failed for {url}: {exc}")

        # Strategy 3: Fallback to get_eol_data with software hint
        if hasattr(agent, "get_eol_data") and callable(agent.get_eol_data):
            try:
                result = await agent.get_eol_data(software_hint, version=None)
                if result and result.get("success"):
                    data_block = result.get("data", {})
                    runs.append({
                        "software_name": data_block.get("software_name") or software_hint,
                        "version": data_block.get("version"),
                        "eol_date": data_block.get("eol_date"),
                        "support_end_date": data_block.get("support_end_date"),
                        "agent_used": vendor_key,
                        "confidence": data_block.get("confidence") or result.get("confidence") or 0.75,
                        "source_url": url,
                        "success": True,
                        "mode": "get_eol_data_fallback",
                        "raw": result,
                    })
                    logger.info(f"Parsed 1 record via get_eol_data fallback for {software_hint}")
            except Exception as exc:
                logger.warning(f"get_eol_data fallback failed for {software_hint}: {exc}")

        # If all strategies failed, record failure
        if not any(run.get("source_url") == url for run in runs):
            runs.append({
                "software_name": software_hint,
                "version": None,
                "eol_date": None,
                "support_end_date": None,
                "agent_used": vendor_key,
                "confidence": None,
                "source_url": url,
                "success": False,
                "mode": "all_strategies_failed",
                "error": "No parsing strategy succeeded",
                "raw": None,
            })

    return runs


def _infer_software_hint(url: str, description: str, vendor_key: str) -> str:
    """Infer software name from URL, description, or vendor key.

    Args:
        url: The URL being parsed
        description: URL description from eol_urls
        vendor_key: Vendor identifier

    Returns:
        Software name hint for the parser
    """
    url_lower = url.lower()
    desc_lower = description.lower()

    # Common patterns across vendors
    SOFTWARE_PATTERNS = {
        "windows-server": ["windows-server", "windows server"],
        "windows-11": ["windows11", "windows 11"],
        "windows-10": ["windows-10", "windows 10"],
        "sql-server": ["sql-server", "sql server"],
        "office": ["microsoft-365", "office", "m365"],
        ".net": ["dotnet", ".net"],
        "visual-studio": ["visualstudio", "visual studio"],
        "nodejs": ["nodejs", "node.js", "node js"],
        "npm": ["npm"],
        "yarn": ["yarn"],
        "rhel": ["rhel", "enterprise linux"],
        "centos": ["centos"],
        "fedora": ["fedora"],
        "ubuntu": ["ubuntu"],
        "postgresql": ["postgresql", "postgres"],
        "php": ["php"],
        "python": ["python"],
        "apache": ["httpd", "apache"],
        "oracle": ["oracle"],
    }

    # Check URL and description for known patterns
    for software_name, patterns in SOFTWARE_PATTERNS.items():
        if any(pattern in url_lower or pattern in desc_lower for pattern in patterns):
            return software_name

    # Fallback to vendor key
    return vendor_key


def _format_vendor_record(
    record: Dict[str, Any],
    software_hint: str,
    url: str,
    vendor_key: str,
    mode: str,
) -> Dict[str, Any]:
    """Format a vendor parsing record into standard structure.

    Args:
        record: Raw record from fetch_all_from_url
        software_hint: Software name hint
        url: Source URL
        vendor_key: Vendor identifier
        mode: Parsing mode identifier

    Returns:
        Standardized record dict
    """
    confidence = record.get("confidence")
    if confidence is None:
        confidence = 0.85  # Default for scraped data

    return {
        "software_name": record.get("software_name") or software_hint,
        "version": record.get("version") or record.get("cycle"),
        "eol_date": record.get("eol"),
        "support_end_date": record.get("support"),
        "agent_used": vendor_key,
        "confidence": confidence,
        "source_url": url,
        "success": True,
        "mode": mode,
        "raw": record,
    }
