"""
GitHub Security Advisory Database client.

Fetches security advisories with CVE mappings via GitHub GraphQL API.
API Documentation: https://docs.github.com/en/graphql/reference/objects#securityadvisory
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Dict, Any, List
import aiohttp

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)


class GitHubAdvisoryClient:
    """Client for GitHub Security Advisory Database GraphQL API.

    Fetches GHSA (GitHub Security Advisory) records with CVE identifiers.
    """

    QUERY_TEMPLATE = """
    query($first: Int!, $after: String) {
      securityAdvisories(first: $first, after: $after) {
        nodes {
          ghsaId
          summary
          description
          severity
          identifiers {
            type
            value
          }
          references {
            url
          }
          publishedAt
          updatedAt
          withdrawnAt
          vulnerabilities(first: 10) {
            nodes {
              package {
                name
                ecosystem
              }
              vulnerableVersionRange
              firstPatchedVersion {
                identifier
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    def __init__(
        self,
        graphql_url: str = "https://api.github.com/graphql",
        token: Optional[str] = None,
        request_timeout: int = 30
    ):
        self.graphql_url = graphql_url
        self.token = token
        self.request_timeout = request_timeout
        self._session: Optional[aiohttp.ClientSession] = None

        if not token:
            logger.warning(
                "GitHub token not provided (GITHUB_TOKEN env var). "
                "Advisory API access will fail. "
                "Get a token from https://github.com/settings/tokens"
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_advisory_by_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch GitHub advisory by CVE ID.

        Note: GraphQL API doesn't support direct CVE ID lookup.
        This method searches advisories and filters by CVE identifier.

        Args:
            cve_id: CVE identifier

        Returns:
            First matching advisory or None
        """
        advisories = await self.search_advisories(limit=100)

        # Filter by CVE ID
        cve_id = cve_id.upper()
        for advisory in advisories:
            identifiers = advisory.get("identifiers", [])
            for identifier in identifiers:
                if identifier.get("type") == "CVE" and identifier.get("value") == cve_id:
                    return advisory

        logger.debug(f"No GitHub advisory found for {cve_id}")
        return None

    async def search_advisories(
        self,
        limit: int = 100,
        cursor: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search GitHub security advisories.

        Args:
            limit: Max advisories to return (100 max per request)
            cursor: Pagination cursor

        Returns:
            List of normalized advisory dicts
        """
        if not self.token:
            logger.warning("Cannot fetch GitHub advisories without token")
            return []

        variables = {
            "first": min(limit, 100),  # API max
            "after": cursor
        }

        payload = {
            "query": self.QUERY_TEMPLATE,
            "variables": variables
        }

        try:
            session = await self._get_session()

            async with session.post(self.graphql_url, json=payload) as response:
                if response.status == 401:
                    logger.error("GitHub token invalid (401 Unauthorized)")
                    return []

                response.raise_for_status()
                result = await response.json()

                if "errors" in result:
                    logger.error(f"GitHub GraphQL errors: {result['errors']}")
                    return []

                data = result.get("data", {})
                advisories_data = data.get("securityAdvisories", {})
                nodes = advisories_data.get("nodes", [])

                normalized = [self._normalize_advisory(node) for node in nodes if node]

                # Handle pagination
                page_info = advisories_data.get("pageInfo", {})
                if page_info.get("hasNextPage"):
                    logger.info(f"GitHub advisories have more pages (cursor: {page_info.get('endCursor')})")

                return normalized

        except Exception as e:
            logger.error(f"Failed to search GitHub advisories: {e}")
            return []

    def _normalize_advisory(self, advisory: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize GitHub advisory format to internal format."""
        if not advisory:
            return {}

        # Extract CVE IDs from identifiers
        cve_ids = []
        for identifier in advisory.get("identifiers", []):
            if identifier.get("type") == "CVE":
                cve_ids.append(identifier.get("value"))

        # Extract affected packages
        affected_packages = []
        for vuln in advisory.get("vulnerabilities", {}).get("nodes", []):
            package = vuln.get("package", {})
            first_patched = vuln.get("firstPatchedVersion", {})

            affected_packages.append({
                "name": package.get("name", ""),
                "ecosystem": package.get("ecosystem", ""),
                "vulnerable_range": vuln.get("vulnerableVersionRange", ""),
                "first_patched_version": first_patched.get("identifier") if first_patched else None
            })

        # Extract references
        references = []
        for ref in advisory.get("references", []):
            url = ref.get("url", "")
            if url:
                references.append({
                    "url": url,
                    "source": "github",
                    "tags": []
                })

        return {
            "ghsa_id": advisory.get("ghsaId", ""),
            "cve_ids": cve_ids,  # May map to multiple CVEs
            "source": "github",
            "summary": advisory.get("summary", ""),
            "description": advisory.get("description", ""),
            "severity": advisory.get("severity", ""),
            "published_at": advisory.get("publishedAt"),
            "updated_at": advisory.get("updatedAt"),
            "withdrawn_at": advisory.get("withdrawnAt"),
            "affected_packages": affected_packages,
            "references": references,
            "vendor_metadata": {
                "source": "github",
                "ghsa_id": advisory.get("ghsaId"),
                "affected_packages": affected_packages,
                "fix_available": any(p.get("first_patched_version") for p in affected_packages)
            }
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
