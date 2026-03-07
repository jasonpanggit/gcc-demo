"""
CVE data models.
"""
from __future__ import annotations

try:
    from models.cve_models import (
        CVSSScore,
        CVEAffectedProduct,
        CVEReference,
        CVEVendorMetadata,
        UnifiedCVE
    )
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import (
        CVSSScore,
        CVEAffectedProduct,
        CVEReference,
        CVEVendorMetadata,
        UnifiedCVE
    )


__all__ = [
    "CVSSScore",
    "CVEAffectedProduct",
    "CVEReference",
    "CVEVendorMetadata",
    "UnifiedCVE"
]
