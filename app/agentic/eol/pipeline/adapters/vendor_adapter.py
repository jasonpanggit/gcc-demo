"""Tier 3 composite adapter wrapping legacy vendor HTML scraper agents.

Contains the vendor routing maps (moved from eol_orchestrator.py per ORCH-03)
and fans out to matched vendor agents concurrently within a single Tier 3 unit.
These scrapers are retained as a lower-confidence fallback behind structured
sources such as endoflife.date and eolstatus.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from utils.normalization import NormalizedQuery
from pipeline.source_adapter import SourceAdapter, SourceResult

logger = logging.getLogger(__name__)

# Vendor routing map — moved from eol_orchestrator.py DEFAULT_VENDOR_ROUTING
DEFAULT_VENDOR_ROUTING: Dict[str, List[str]] = {
    # Microsoft ecosystem
    "microsoft": [
        "windows",
        "office",
        "sql server",
        "iis",
        "visual studio",
        ".net",
        "azure",
        "sharepoint",
        "exchange",
        "teams",
        "power bi",
        "dynamics",
    ],
    # Red Hat ecosystem
    "redhat": ["red hat", "rhel", "centos", "fedora", "openshift", "ansible"],
    # Ubuntu ecosystem
    "ubuntu": ["ubuntu", "canonical", "snap"],
}


class VendorScraperAdapter:
    """Composite Tier 3 adapter wrapping all vendor HTML scraper agents.

    The pipeline sees this as a single Tier 3 adapter. Internally it
    routes to the appropriate vendor agent(s) using keyword matching
    (algorithm moved from eol_orchestrator._route_to_agents) and runs
    matched agents concurrently via asyncio.gather.
    """

    name: str = "vendor_scraper"
    tier: int = 3
    timeout: int = 20

    def __init__(
        self,
        agents: Dict[str, Any],
        vendor_routing: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Initialize with vendor agent instances and routing map.

        Args:
            agents: Dict mapping vendor name -> agent instance.
                    Keys should match DEFAULT_VENDOR_ROUTING keys
                    (e.g., "microsoft", "redhat", "ubuntu", etc.).
            vendor_routing: Custom vendor routing map. Defaults to
                           DEFAULT_VENDOR_ROUTING.
        """
        self._agents = agents
        self._vendor_routing = vendor_routing or DEFAULT_VENDOR_ROUTING

    def _route_to_agents(
        self, software_name_lower: str, item_type: str = "software"
    ) -> List[str]:
        """Determine which vendor agents to invoke for a query.

        Algorithm copied from eol_orchestrator._route_to_agents (ORCH-03).

        Args:
            software_name_lower: Lowercase software name.
            item_type: "software" or "os".

        Returns:
            Deduplicated, ordered list of vendor agent names to invoke.
        """
        target_agents: List[str] = []

        # Vendor-specific routing for higher accuracy
        for vendor, keywords in self._vendor_routing.items():
            if any(keyword in software_name_lower for keyword in keywords):
                target_agents.append(vendor)

        # Special handling for OS items
        if item_type == "os":
            if "windows" in software_name_lower:
                target_agents.insert(0, "microsoft")
            elif any(
                linux in software_name_lower
                for linux in ["ubuntu", "debian", "linux"]
            ):
                target_agents.insert(0, "ubuntu")
            elif any(
                rh in software_name_lower
                for rh in ["red hat", "rhel", "centos", "fedora"]
            ):
                target_agents.insert(0, "redhat")

        # Remove duplicates while preserving order
        seen: set = set()
        unique_agents: List[str] = []
        for agent_name in target_agents:
            if agent_name not in seen:
                seen.add(agent_name)
                unique_agents.append(agent_name)

        return unique_agents

    async def _invoke_single(
        self,
        agent_name: str,
        query: NormalizedQuery,
    ) -> Optional[SourceResult]:
        """Invoke a single vendor agent and translate the response."""
        agent = self._agents.get(agent_name)
        if agent is None:
            return None

        start = time.monotonic()
        try:
            result = await agent.get_eol_data(query.raw_name, query.raw_version)
            duration_ms = (time.monotonic() - start) * 1000

            if not result or not result.get("success") or not result.get("data"):
                return None

            data: Dict[str, Any] = result["data"]
            return SourceResult(
                software_name=data.get("software_name", query.raw_name),
                version=data.get("version", query.raw_version),
                eol_date=data.get("eol_date"),
                support_end_date=data.get("support_end_date"),
                release_date=data.get("release_date"),
                source=self.name,
                source_url=data.get("source_url"),
                confidence=0.0,  # Pipeline scores this
                tier=self.tier,
                raw_data=result,
                status=data.get("status"),
                risk_level=data.get("risk_level"),
                agent_used=data.get("agent_used", agent_name),
                fetch_duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            logger.warning(
                "VendorScraperAdapter: agent %s error for %s: %s",
                agent_name,
                query.raw_name,
                exc,
            )
            return None

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        """Route to matching vendor agents and return the best result.

        1. Determine item_type from query.query_type.
        2. Run _route_to_agents to find matching vendors.
        3. Invoke matched agents concurrently via asyncio.gather.
        4. Return the result with the most complete data (has eol_date preferred).
           Confidence is 0.0 here -- the pipeline re-scores.
        """
        item_type = query.query_type  # "os" or "software"
        matched = self._route_to_agents(query.raw_name.lower(), item_type)

        if not matched:
            logger.debug(
                "VendorScraperAdapter: no vendor match for %s", query.raw_name
            )
            return None

        logger.debug(
            "VendorScraperAdapter: routing %s to agents %s",
            query.raw_name,
            matched,
        )

        # Run matched vendor agents concurrently
        tasks = [self._invoke_single(name, query) for name in matched]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter to successful SourceResults
        successes: List[SourceResult] = []
        for r in results:
            if isinstance(r, SourceResult):
                successes.append(r)
            elif isinstance(r, Exception):
                logger.warning("VendorScraperAdapter: gather exception: %s", r)

        if not successes:
            return None

        # Prefer results that have eol_date, then most fields present
        def _rank(sr: SourceResult) -> int:
            score = 0
            if sr.eol_date:
                score += 4
            if sr.support_end_date:
                score += 2
            if sr.release_date:
                score += 1
            if sr.source_url:
                score += 1
            return score

        return max(successes, key=_rank)
