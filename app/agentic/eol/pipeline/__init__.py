"""EOL tiered fetch pipeline.

Provides a uniform SourceAdapter protocol, adapter registry for
tier-based grouping, a factory for creating the default adapter set,
and the TieredFetchPipeline execution engine.

Phase 2 deliverables:
- SourceAdapter (Protocol): Uniform fetch interface for data sources
- SourceResult (dataclass): Standard result shape from any adapter
- AdapterRegistry: Groups adapters by reliability tier
- create_default_registry: Factory creating the standard 4-adapter set
- TieredFetchPipeline: Sequential tier execution with early termination
"""

from .source_adapter import AdapterRegistry, SourceAdapter, SourceResult
from .tiered_fetch_pipeline import TieredFetchPipeline
from .adapters import (
    DEFAULT_VENDOR_ROUTING,
    EndoflifeAdapter,
    EolstatusAdapter,
    FallbackAdapter,
    VendorScraperAdapter,
)
from .result_aggregator import (
    AggregatedResult,
    DiscrepancyEntry,
    ResultAggregator,
    SourceEntry,
)

from typing import Any, Dict, Optional


def create_default_registry(
    agents: Dict[str, Any],
    vendor_routing: Optional[Dict[str, Any]] = None,
) -> AdapterRegistry:
    """Create an AdapterRegistry with the standard 4-adapter set.

    Registers:
      - EndoflifeAdapter (Tier 1) wrapping agents["endoflife"]
      - EolstatusAdapter (Tier 2) wrapping agents["eolstatus"]
      - VendorScraperAdapter (Tier 3) wrapping vendor agents with routing maps
      - FallbackAdapter (Tier 4) wrapping agents["playwright"]

    Args:
        agents: Dict mapping agent name -> agent instance. Must contain
                at minimum "endoflife". Other keys are optional and adapters
                are registered only when the corresponding agent exists.
        vendor_routing: Optional custom vendor routing map. Defaults to
                       DEFAULT_VENDOR_ROUTING from vendor_adapter.

    Returns:
        Populated AdapterRegistry ready for use by TieredFetchPipeline.
    """
    registry = AdapterRegistry()

    # Tier 1: endoflife.date API
    if "endoflife" in agents:
        registry.register(EndoflifeAdapter(agents["endoflife"]))

    # Tier 2: eolstatus.com JSON-LD
    if "eolstatus" in agents:
        registry.register(EolstatusAdapter(agents["eolstatus"]))

    # Tier 3: Vendor scraper composite (only agents not fully covered by endoflife.date)
    vendor_agent_names = [
        "microsoft", "redhat", "ubuntu",
    ]
    vendor_agents = {
        name: agents[name] for name in vendor_agent_names if name in agents
    }
    if vendor_agents:
        registry.register(
            VendorScraperAdapter(vendor_agents, vendor_routing)
        )

    # Tier 4: Playwright fallback
    if "playwright" in agents:
        registry.register(FallbackAdapter(agents["playwright"]))

    return registry


__all__ = [
    "AdapterRegistry",
    "SourceAdapter",
    "SourceResult",
    "TieredFetchPipeline",
    "create_default_registry",
    "EndoflifeAdapter",
    "EolstatusAdapter",
    "VendorScraperAdapter",
    "FallbackAdapter",
    "DEFAULT_VENDOR_ROUTING",
    "AggregatedResult",
    "DiscrepancyEntry",
    "ResultAggregator",
    "SourceEntry",
]
