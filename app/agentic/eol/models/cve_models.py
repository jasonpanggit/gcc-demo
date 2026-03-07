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


# ============================================================================
# API Request/Response Models (Phase 3)
# ============================================================================

class CVESearchRequest(BaseModel):
    """Request model for CVE search API.

    Supports multiple filter types for flexible CVE discovery.
    """
    # Identity filters
    cve_id: Optional[str] = None

    # Text search
    keyword: Optional[str] = None

    # Severity filters
    severity: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    min_score: Optional[float] = None  # CVSS minimum score (0.0-10.0)
    max_score: Optional[float] = None  # CVSS maximum score (0.0-10.0)

    # Date filters
    published_after: Optional[str] = None  # ISO date string
    published_before: Optional[str] = None  # ISO date string

    # Product filters
    vendor: Optional[str] = None
    product: Optional[str] = None

    # Source filter
    source: Optional[str] = None  # nvd, cve_org, github, redhat, ubuntu, microsoft

    # Exploit filter
    exploit_available: Optional[bool] = None

    # Pagination
    limit: int = 100
    offset: int = 0

    # Sorting
    sort_by: str = "published_date"  # published_date, last_modified_date, cvss_score
    sort_order: str = "desc"  # asc, desc


class CVESearchResponse(BaseModel):
    """Response model for CVE search API."""
    results: List[UnifiedCVE]
    total_count: int
    offset: int
    limit: int
    has_more: bool


class CVEDetailResponse(BaseModel):
    """Response model for CVE detail API."""
    cve: UnifiedCVE
    related_cves: List[str] = []  # CVE IDs of related vulnerabilities
    cache_hit: bool = False  # Whether result came from L1/L2 cache


# ============================================================================
# CVE Scanning Models (Phase 5)
# ============================================================================

class VMScanTarget(BaseModel):
    """VM target for CVE scanning."""
    vm_id: str
    name: str
    resource_group: str
    subscription_id: str
    os_type: str  # "Linux" or "Windows"
    os_name: Optional[str] = None  # e.g., "Ubuntu", "Windows Server"
    os_version: Optional[str] = None  # e.g., "20.04", "2019"
    installed_packages: List[str] = Field(default_factory=list)  # Package names/versions
    tags: Dict[str, str] = Field(default_factory=dict)
    location: str
    vm_type: str  # "azure" or "arc"


class CVEMatch(BaseModel):
    """CVE matched to a VM."""
    cve_id: str
    vm_id: str
    vm_name: str
    match_reason: str  # e.g., "OS Ubuntu 20.04 affected"
    cvss_score: Optional[float] = None
    severity: Optional[str] = None
    published_date: Optional[str] = None


class ScanResult(BaseModel):
    """Result of CVE scan."""
    scan_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str  # "pending", "running", "completed", "failed"
    total_vms: int
    scanned_vms: int
    total_matches: int
    matches: List[CVEMatch] = Field(default_factory=list)
    error: Optional[str] = None


class CVEScanRequest(BaseModel):
    """Request to trigger CVE scan."""
    subscription_ids: Optional[List[str]] = None  # None = all subscriptions
    resource_groups: Optional[List[str]] = None
    include_arc: bool = True
    cve_filters: Optional[Dict[str, Any]] = None  # Optional: only scan for specific CVEs


class CVEScanStatusResponse(BaseModel):
    """Response for scan status check."""
    scan_id: str
    status: str
    progress: int  # 0-100
    total_vms: int
    scanned_vms: int
    matches_found: int
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# CVE-to-Patch Mapping Models (Phase 6)
# ============================================================================

class ApplicablePatch(BaseModel):
    """Patch applicable to a CVE."""
    patch_id: str  # KB number or package name
    patch_name: str
    vendor: str  # "microsoft", "ubuntu", "redhat", etc.
    severity: str  # Patch severity classification
    release_date: Optional[str] = None
    affected_vm_count: int  # How many VMs need this patch
    installation_status: Optional[str] = None  # "available", "installed", "pending"


class CVEPatchMapping(BaseModel):
    """CVE-to-patch mapping result."""
    cve_id: str
    patches: List[ApplicablePatch]
    priority_score: int  # 0-100, calculated from CVSS + exposure
    total_affected_vms: int
    recommendation: str  # "Install immediately", "Schedule maintenance", etc.


class CVEPatchRequest(BaseModel):
    """Request to get patches for CVE."""
    cve_id: str
    subscription_ids: Optional[List[str]] = None
    include_installed: bool = False  # Include already-installed patches


# ============================================================================
# Inventory Vulnerability Models (Phase 7)
# ============================================================================

class VMCVEDetail(BaseModel):
    """Enriched CVE details for VM view."""
    cve_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: Optional[float] = None
    published_date: Optional[str] = None
    description: str
    match_reason: str  # Why this CVE affects this VM
    patches_available: int = 0  # Count of patches that fix this CVE


class VMVulnerabilityResponse(BaseModel):
    """Response for GET /api/cve/inventory/{vm_id}."""
    vm_id: str
    vm_name: str
    scan_id: str
    scan_date: str
    total_cves: int
    cves_by_severity: Dict[str, int]  # {"CRITICAL": 5, "HIGH": 12, ...}
    cve_details: List[VMCVEDetail]


class AffectedVMDetail(BaseModel):
    """VM affected by a CVE."""
    vm_id: str
    vm_name: str
    resource_group: str
    subscription_id: str
    os_type: str  # "Linux" or "Windows"
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    location: str
    match_reason: str
    patch_status: Optional[str] = None  # "available", "installed", "pending"


class CVEAffectedVMsResponse(BaseModel):
    """Response for GET /api/cve/{cve_id}/affected-vms."""
    cve_id: str
    scan_id: str
    scan_date: str
    total_vms: int
    affected_vms: List[AffectedVMDetail]


# Export all models
__all__ = [
    "CVSSScore",
    "CVEAffectedProduct",
    "CVEReference",
    "CVEVendorMetadata",
    "UnifiedCVE",
    "CVESearchRequest",
    "CVESearchResponse",
    "CVEDetailResponse",
    "VMScanTarget",
    "CVEMatch",
    "ScanResult",
    "CVEScanRequest",
    "CVEScanStatusResponse",
    "ApplicablePatch",
    "CVEPatchMapping",
    "CVEPatchRequest",
    "VMCVEDetail",
    "VMVulnerabilityResponse",
    "AffectedVMDetail",
    "CVEAffectedVMsResponse"
]
