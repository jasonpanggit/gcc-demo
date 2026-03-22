"""Tier 2 adapter wrapping EOLStatusAgent (eolstatus.com JSON-LD)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from utils.normalization import NormalizedQuery
from pipeline.source_adapter import SourceAdapter, SourceResult

logger = logging.getLogger(__name__)


class EolstatusAdapter:
    """Thin adapter wrapping EOLStatusAgent for the tiered pipeline.

    Tier 2: JSON-LD extraction source (eolstatus.com).
    """

    name: str = "eolstatus"
    tier: int = 2
    timeout: int = 15

    def __init__(self, agent: Any) -> None:
        """Initialize with an EOLStatusAgent instance.

        Args:
            agent: An EOLStatusAgent with async get_eol_data(name, version).
        """
        self._agent = agent

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        """Fetch EOL data from eolstatus.com via the wrapped agent.

        Returns None on failure.
        """
        start = time.monotonic()
        try:
            result = await self._agent.get_eol_data(
                query.raw_name, query.raw_version
            )
            duration_ms = (time.monotonic() - start) * 1000

            if not result or not result.get("success") or not result.get("data"):
                logger.debug(
                    "EolstatusAdapter: no result for %s %s",
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
                "EolstatusAdapter: error for %s: %s", query.raw_name, exc
            )
            return None
