"""Tier 1 adapter wrapping EndOfLifeAgent (endoflife.date API)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from utils.normalization import NormalizedQuery
from pipeline.source_adapter import SourceAdapter, SourceResult

logger = logging.getLogger(__name__)


class EndoflifeAdapter:
    """Thin adapter wrapping EndOfLifeAgent for the tiered pipeline.

    Tier 1: Structured API source (endoflife.date).
    Translates agent success/failure responses into SourceResult.
    """

    name: str = "endoflife"
    tier: int = 1
    timeout: int = 10

    def __init__(self, agent: Any) -> None:
        """Initialize with an EndOfLifeAgent instance.

        Args:
            agent: An EndOfLifeAgent with async get_eol_data(name, version).
        """
        self._agent = agent

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        """Fetch EOL data from endoflife.date API via the wrapped agent.

        Passes raw_name/raw_version to the agent (agents do their own
        internal normalization). Returns None on failure.
        """
        start = time.monotonic()
        try:
            result = await self._agent.get_eol_data(
                query.raw_name, query.raw_version
            )
            duration_ms = (time.monotonic() - start) * 1000

            if not result or not result.get("success") or not result.get("data"):
                logger.debug(
                    "EndoflifeAdapter: no result for %s %s",
                    query.raw_name,
                    query.raw_version,
                )
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
                confidence=0.0,  # Pipeline scores this via ConfidenceScorer
                tier=self.tier,
                raw_data=result,
                status=data.get("status"),
                risk_level=data.get("risk_level"),
                agent_used=data.get("agent_used", self.name),
                fetch_duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            logger.warning(
                "EndoflifeAdapter: error for %s: %s", query.raw_name, exc
            )
            return None
