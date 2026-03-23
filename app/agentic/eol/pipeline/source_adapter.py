"""Source adapter protocol, result dataclass, and adapter registry.

Defines the uniform interface that all EOL data source adapters must
implement, the data shape they return, and the registry that groups
adapters by reliability tier for the tiered fetch pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from utils.normalization import NormalizedQuery

logger = logging.getLogger(__name__)


@dataclass
class SourceResult:
    """Uniform result from any source adapter.

    Fields are translated from the agent's success response dict.
    Confidence is computed by the pipeline (via ConfidenceScorer),
    NOT copied from the agent's self-reported value.
    """

    software_name: str
    version: Optional[str]
    eol_date: Optional[str]
    support_end_date: Optional[str] = None
    release_date: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    confidence: float = 0.0
    tier: int = 4
    raw_data: Dict[str, Any] = field(default_factory=dict)
    status: Optional[str] = None
    risk_level: Optional[str] = None
    agent_used: Optional[str] = None
    fetch_duration_ms: float = 0.0


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol that all EOL data source adapters must implement.

    Adapters are thin wrappers around existing agents. They translate
    the agent's response dict into a SourceResult. The pipeline handles
    timeouts, exception catching, and confidence scoring.

    Attributes:
        name: Adapter identifier (e.g., "endoflife", "eolstatus").
        tier: Source reliability tier (1-4). Self-declared by adapter.
        timeout: Per-adapter timeout in seconds for fetch() calls.
    """

    name: str
    tier: int
    timeout: int

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        """Fetch EOL data for the given normalized query.

        Returns SourceResult on success, None on miss/failure.
        Must not raise -- all exceptions should be caught internally
        and return None.
        """
        ...


class AdapterRegistry:
    """Registry that collects adapters and groups them by tier.

    Adapters are registered explicitly via register(). The registry
    auto-groups them by their self-declared tier attribute.
    """

    def __init__(self) -> None:
        self._adapters: List[SourceAdapter] = []
        self._by_tier: Dict[int, List[SourceAdapter]] = {}

    def register(self, adapter: SourceAdapter) -> None:
        """Register an adapter. Validates it implements the protocol."""
        if not isinstance(adapter, SourceAdapter):
            raise TypeError(
                f"{type(adapter).__name__} does not implement SourceAdapter protocol"
            )
        self._adapters.append(adapter)
        self._by_tier.setdefault(adapter.tier, []).append(adapter)
        logger.info(
            "Registered adapter %s (tier=%d, timeout=%ds)",
            adapter.name,
            adapter.tier,
            adapter.timeout,
        )

    def get_tier(self, tier: int) -> List[SourceAdapter]:
        """Return all adapters registered at the given tier."""
        return list(self._by_tier.get(tier, []))

    def all_tiers(self) -> List[int]:
        """Return sorted list of tiers that have registered adapters."""
        return sorted(self._by_tier.keys())

    def all_adapters(self) -> List[SourceAdapter]:
        """Return all registered adapters in registration order."""
        return list(self._adapters)
