"""CVE Management MCP Server

Provides MCP-compliant tools for CVE management operations:
- CVE search by ID, keyword, or filters
- VM inventory CVE scanning
- CVE-to-patch mapping
- Patch remediation triggering with safety workflow
"""
from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

_LOG_LEVEL_NAME = os.getenv("CVE_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO

try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(name="azure-cve")


@mcp.tool()
async def search_cve(
    cve_id: Annotated[Optional[str], "CVE identifier (e.g., CVE-2024-1234)"] = None,
    keyword: Annotated[Optional[str], "Keyword to search in description"] = None,
    severity: Annotated[Optional[str], "Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"] = None,
    cvss_min: Annotated[Optional[float], "Minimum CVSS score (0.0-10.0)"] = None,
    cvss_max: Annotated[Optional[float], "Maximum CVSS score (0.0-10.0)"] = None,
    published_after: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    published_before: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    limit: Annotated[int, "Maximum results to return"] = 20
) -> TextContent:
    """Search CVEs by ID, keyword, or filters.

    Use this for:
    - "Search for CVE-2024-1234"
    - "Find critical CVEs affecting Ubuntu"
    - "Show CVEs published last 30 days"
    - "What is CVE-2024-5678?"

    Returns CVE summaries with ID, severity, CVSS, description.
    """
    try:
        from utils.cve_service import get_cve_service

        cve_service = await get_cve_service()

        # If cve_id provided, do direct lookup
        if cve_id:
            cve = await cve_service.get_cve(cve_id)
            if not cve:
                return TextContent(
                    type="text",
                    text=json.dumps({
                        "success": False,
                        "error": f"CVE {cve_id} not found",
                        "tool_name": "search_cve"
                    }, indent=2)
                )
            results = [cve.dict()]
        else:
            # Build search filters
            filters = {}
            if keyword:
                filters["keyword"] = keyword
            if severity:
                filters["severity"] = severity.upper()
            if cvss_min is not None:
                filters["cvss_min"] = cvss_min
            if cvss_max is not None:
                filters["cvss_max"] = cvss_max
            if published_after:
                filters["published_after"] = published_after
            if published_before:
                filters["published_before"] = published_before

            cves = await cve_service.search_cves(filters, limit=limit, offset=0)
            results = [cve.dict() for cve in cves]

        return TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "count": len(results),
                "cves": results,
                "tool_name": "search_cve"
            }, indent=2)
        )
    except Exception as e:
        return TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": str(e),
                "tool_name": "search_cve"
            }, indent=2)
        )


@mcp.tool()
async def scan_inventory(
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[Optional[str], "Optional resource group filter"] = None,
    vm_name: Annotated[Optional[str], "Optional VM name filter"] = None
) -> TextContent:
    """Trigger CVE scan on Azure VM inventory.

    Use this for:
    - "Scan my VMs for CVEs"
    - "Check what CVEs affect my infrastructure"
    - "Run vulnerability scan on vm-prod-01"

    Returns scan ID and status. Scan runs asynchronously (1-3 minutes).
    Check results at /cve-vm-detail page or call get_scan_result later.
    """
    # Implementation will be added in task 3
    pass


@mcp.tool()
async def get_patches(
    cve_id: Annotated[str, "CVE identifier (e.g., CVE-2024-1234)"],
    subscription_ids: Annotated[Optional[List[str]], "Optional subscription IDs to filter affected VMs"] = None
) -> TextContent:
    """Get patches that remediate a CVE.

    Use this for:
    - "What patches fix CVE-2024-1234?"
    - "Show me available patches for this CVE"
    - "How do I remediate CVE-2024-5678?"

    Returns list of applicable patches with KB numbers, package names,
    priority ranking, and affected VM count.
    """
    # Implementation will be added in task 4
    pass


@mcp.tool()
async def trigger_remediation(
    cve_id: Annotated[str, "CVE identifier to remediate"],
    vm_name: Annotated[str, "VM name to apply patches"],
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[str, "Resource group containing VM"],
    dry_run: Annotated[bool, "If True, show plan without executing"] = True,
    confirmed: Annotated[bool, "Must be True to execute real patch installation"] = False
) -> TextContent:
    """Trigger patch installation to remediate a CVE.

    SAFETY WORKFLOW:
    1. First call with dry_run=True to see installation plan
    2. Review plan with user
    3. Call again with confirmed=True to execute

    Use this for:
    - "Install patches for CVE-2024-1234 on vm-prod-01"
    - "Remediate this CVE on my affected VMs"
    - "Apply security updates to fix CVE-2024-5678"

    Returns installation plan (dry_run) or operation URL (confirmed).
    """
    # Implementation will be added in task 5
    pass
