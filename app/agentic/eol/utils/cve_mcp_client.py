"""CVE MCP client wrapper for orchestrator integration."""
from typing import Any, Dict, Optional, List
import json


class CVEMCPClient:
    """Client wrapper for CVE MCP server."""

    def __init__(self):
        self.mcp = None  # Will hold FastMCP instance

    async def initialize(self):
        """Initialize MCP server connection."""
        from mcp_servers.cve_mcp_server import mcp as cve_mcp
        self.mcp = cve_mcp
        # FastMCP servers don't need explicit start in in-process mode

    async def search_cve(
        self,
        cve_id: Optional[str] = None,
        keyword: Optional[str] = None,
        severity: Optional[str] = None,
        cvss_min: Optional[float] = None,
        cvss_max: Optional[float] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Search CVEs by ID, keyword, or filters."""
        result = await self.mcp.call_tool(
            "search_cve",
            arguments={
                "cve_id": cve_id,
                "keyword": keyword,
                "severity": severity,
                "cvss_min": cvss_min,
                "cvss_max": cvss_max,
                "published_after": published_after,
                "published_before": published_before,
                "limit": limit
            }
        )
        return json.loads(result.text) if hasattr(result, 'text') else result

    async def scan_inventory(
        self,
        subscription_id: str,
        resource_group: Optional[str] = None,
        vm_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trigger CVE scan on VM inventory."""
        result = await self.mcp.call_tool(
            "scan_inventory",
            arguments={
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "vm_name": vm_name
            }
        )
        return json.loads(result.text) if hasattr(result, 'text') else result

    async def get_patches(
        self,
        cve_id: str,
        subscription_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get patches for a CVE."""
        result = await self.mcp.call_tool(
            "get_patches",
            arguments={
                "cve_id": cve_id,
                "subscription_ids": subscription_ids
            }
        )
        return json.loads(result.text) if hasattr(result, 'text') else result

    async def trigger_remediation(
        self,
        cve_id: str,
        vm_name: str,
        subscription_id: str,
        resource_group: str,
        dry_run: bool = True,
        confirmed: bool = False
    ) -> Dict[str, Any]:
        """Trigger patch installation for CVE."""
        result = await self.mcp.call_tool(
            "trigger_remediation",
            arguments={
                "cve_id": cve_id,
                "vm_name": vm_name,
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "dry_run": dry_run,
                "confirmed": confirmed
            }
        )
        return json.loads(result.text) if hasattr(result, 'text') else result


# Singleton factory
_cve_mcp_client: Optional[CVEMCPClient] = None


async def get_cve_mcp_client() -> CVEMCPClient:
    """Get or create CVE MCP client singleton."""
    global _cve_mcp_client
    if _cve_mcp_client is None:
        _cve_mcp_client = CVEMCPClient()
        await _cve_mcp_client.initialize()
    return _cve_mcp_client
