"""
Unified CVE data models.

Pydantic models for representing CVE data from multiple sources with deduplication.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CVSSScore(BaseModel):
    """CVSS (Common Vulnerability Scoring System) score.

    Supports both CVSS v2 and v3.x formats.
    """
    version: str  # "2.0", "3.0", or "3.1"
    base_score: float  # 0.0 to 10.0
    base_severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"
    vector_string: str  # e.g., "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
    exploitability_score: Optional[float] = None
    impact_score: Optional[float] = None

    class Config:
        frozen = True  # Immutable


class CVEAffectedProduct(BaseModel):
    """Product affected by a CVE.

    Represents vendor/product/version combinations extracted from CVE data.
    """
    vendor: str
    product: str
    version: str  # Can be version range like "< 2.0" or specific "1.5.3"
    cpe_uri: Optional[str] = None  # CPE 2.3 format URI

    class Config:
        frozen = True  # Immutable


class CVEReference(BaseModel):
    """External reference link for a CVE.

    Can be vendor advisories, exploit POCs, patches, or general documentation.
    """
    url: str
    source: str  # Source that provided this reference (cve_org, nvd, redhat, etc.)
    tags: List[str] = Field(default_factory=list)  # e.g., ["Patch", "Vendor Advisory"]

    class Config:
        frozen = True  # Immutable


class CVEVendorMetadata(BaseModel):
    """Vendor-specific CVE metadata.

    Each vendor provides unique metadata (affected packages, fix versions, advisories).
    This model preserves vendor-specific information without normalization.
    """
    source: str  # "redhat", "ubuntu", "microsoft", "github"
    affected_packages: List[Dict[str, Any]] = Field(default_factory=list)
    fix_available: bool = False
    fix_version: Optional[str] = None
    advisory_id: Optional[str] = None  # RHSA-2024-001, USN-1234-1, KB5001234, GHSA-xxxx
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Arbitrary vendor-specific fields


class UnifiedCVE(BaseModel):
    """Unified CVE data model merging all sources.

    Represents a single CVE with data aggregated from multiple sources:
    - CVE.org: Official CVE records
    - NVD: CVSS scores and CPE configurations
    - Red Hat: RHSA and package fix status
    - Ubuntu: USN and affected releases
    - Microsoft: KB numbers and CVRF data
    - GitHub: GHSA and package vulnerabilities

    The `sources` list tracks which APIs contributed data.
    The `vendor_metadata` list preserves vendor-specific details.
    """
    cve_id: str  # Primary key, e.g., "CVE-2024-0001"
    description: str
    published_date: datetime
    last_modified_date: datetime
    cvss_v2: Optional[CVSSScore] = None
    cvss_v3: Optional[CVSSScore] = None
    cwe_ids: List[str] = Field(default_factory=list)  # e.g., ["CWE-79", "CWE-89"]
    affected_products: List[CVEAffectedProduct] = Field(default_factory=list)
    references: List[CVEReference] = Field(default_factory=list)
    vendor_metadata: List[CVEVendorMetadata] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)  # ["cve_org", "nvd", "redhat", ...]
    last_synced: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # Pydantic v2 config
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Export all models
__all__ = [
    "CVSSScore",
    "CVEAffectedProduct",
    "CVEReference",
    "CVEVendorMetadata",
    "UnifiedCVE"
]
