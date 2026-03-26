"""EOL pipeline adapters.

Each adapter wraps an existing EOL agent and conforms to the
SourceAdapter protocol for use in the tiered fetch pipeline.
"""

from .endoflife_adapter import EndoflifeAdapter
from .eolstatus_adapter import EolstatusAdapter
from .vendor_adapter import VendorScraperAdapter, DEFAULT_VENDOR_ROUTING
from .web_search_adapter import FallbackAdapter  # Keep class name for backward compat

__all__ = [
    "EndoflifeAdapter",
    "EolstatusAdapter",
    "VendorScraperAdapter",
    "FallbackAdapter",
    "DEFAULT_VENDOR_ROUTING",
]
