"""
Unified CVE data models.

Pydantic models for representing CVE data from multiple sources with deduplication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import re
from pydantic import BaseModel, Field, model_validator


KB_PATTERN = re.compile(r"\bKB\d{6,8}\b", re.IGNORECASE)


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
    kb_numbers: List[str] = Field(default_factory=list)
    severity: Optional[str] = None
    impact: Optional[str] = None
    exploitability: Optional[str] = None
    title: Optional[str] = None
    document_title: Optional[str] = None
    update_id: Optional[str] = None
    cvrf_url: Optional[str] = None
    notes: Dict[str, str] = Field(default_factory=dict)
    format: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Arbitrary vendor-specific fields

    @model_validator(mode="after")
    def _hydrate_microsoft_fields(self) -> "CVEVendorMetadata":
        """Backfill Microsoft fields from legacy metadata-only records."""
        if self.source != "microsoft":
            return self

        metadata = self.metadata or {}

        if not self.update_id:
            self.update_id = metadata.get("ID") or metadata.get("Alias")
        if not self.advisory_id:
            self.advisory_id = self.update_id
        if not self.document_title:
            self.document_title = metadata.get("DocumentTitle")
        if not self.cvrf_url:
            self.cvrf_url = metadata.get("CvrfUrl") or metadata.get("cvrfUrl")
        if not self.severity:
            self.severity = metadata.get("Severity") or metadata.get("severity")
        if not self.kb_numbers:
            self.kb_numbers = self._extract_kb_numbers(metadata)
        if not self.fix_available and self.kb_numbers:
            self.fix_available = True

        return self

    @staticmethod
    def _extract_kb_numbers(metadata: Dict[str, Any]) -> List[str]:
        """Extract KB numbers from common Microsoft metadata fields."""
        values: List[str] = []

        for field in ("kbArticles", "kb_numbers", "kbNumbers"):
            raw_value = metadata.get(field)
            if isinstance(raw_value, list):
                values.extend(str(item) for item in raw_value)
            elif raw_value:
                values.append(str(raw_value))

        raw_text = metadata.get("raw_xml") or metadata.get("RawXml")
        if raw_text:
            values.append(str(raw_text))

        kb_numbers: List[str] = []
        seen = set()
        for value in values:
            for match in KB_PATTERN.findall(value):
                kb_number = match.upper()
                if kb_number in seen:
                    continue
                seen.add(kb_number)
                kb_numbers.append(kb_number)

        return kb_numbers


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


class PatchAdvisoryEdge(BaseModel):
    """Unified advisory↔CVE edge for Windows and Linux.

    Windows:  kb_number="KB5034441",      source="microsoft", os_family="windows"
    RHEL:     kb_number="RHSA-2024:1234", source="redhat",    os_family="rhel"
    Ubuntu:   kb_number="USN-6789-1",     source="ubuntu",    os_family="ubuntu"
    """
    id: str                                         # "{source}:{kb_number}:{cve_id}"
    kb_number: str                                  # Windows KB / RHSA ID / USN ID
    cve_id: str
    source: str = "microsoft"                       # "microsoft" | "redhat" | "ubuntu"
    os_family: str = "windows"                      # "windows" | "rhel" | "ubuntu" | "centos"
    advisory_id: Optional[str] = None               # Same as kb_number; explicit alias for UI
    affected_packages: Optional[List[str]] = None   # Linux: packages fixed by this advisory
    fixed_packages: Optional[List[str]] = None      # Linux: packages that deliver the fix
    update_id: Optional[str] = None
    document_title: Optional[str] = None
    cvrf_url: Optional[str] = None
    severity: Optional[str] = None
    published_date: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)


# Backward-compat alias — all existing consumers of KBCVEEdge continue to work
KBCVEEdge = PatchAdvisoryEdge


class MsrcKbCveRecord(BaseModel):
    """Internal record from MSRC SUG affectedProduct API — not stored, used for mapping."""
    cve_number: str           # "CVE-2024-21413"
    kb_article_name: str      # "5002537" (bare numeric, no KB prefix)
    product_family: str       # "Windows" | "Azure" | "Mariner"
    severity: str = ""        # "Critical" | "Important" | ""
    release_number: str = ""  # "2025-Jan"
    is_mariner: bool = False  # True = Azure Linux only, skip for Windows-only KB handling


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
    patch_status: Optional[str] = None  # "installed", "available", "none", or None = unknown


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
    vm_match_summaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # Windows: vm_id → list of installed KB IDs (e.g. ["KB5034441", "KB5050009"])
    vm_installed_kbs: Dict[str, List[str]] = Field(default_factory=dict)
    # Linux: vm_id → list of installed package names (e.g. ["openssl", "curl"])
    vm_installed_packages: Dict[str, List[str]] = Field(default_factory=dict)
    # vm_id → os_family ("windows" | "ubuntu" | "rhel" | "centos")
    vm_os_family: Dict[str, str] = Field(default_factory=dict)
    # Truncation metadata (when match list exceeds limit)
    truncated: bool = False
    total_matches_before_truncation: Optional[int] = None
    error: Optional[str] = None
    # True when per-VM CVE match documents are stored separately (see VMCVEMatchDocument)
    matches_stored_separately: bool = False


class VMCVEMatchDocument(BaseModel):
    """Per-VM CVE match document stored separately in Cosmos DB.

    Document ID format: "{scan_id}--{vm_name}"
    Partition key: scan_id (same partition as main scan document)
    """
    id: str           # "{scan_id}--{vm_name}"
    scan_id: str      # Partition key
    vm_id: str
    vm_name: str
    total_matches: int
    matches: List[CVEMatch] = Field(default_factory=list)   # Lightweight CVEMatch objects
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CVEScanRequest(BaseModel):
    """Request to trigger CVE scan."""
    subscription_ids: Optional[List[str]] = None  # None = all subscriptions
    resource_groups: Optional[List[str]] = None
    include_arc: bool = True
    cve_filters: Optional[Dict[str, Any]] = None  # Optional: only scan for specific CVEs
    vm_ids: Optional[List[str]] = None  # NEW — target specific VMs by resource ID; None = all VMs


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
    patch_status: str = "unknown"  # installed, available, none, unknown
    installed_patches: int = 0  # Count of matching installed patches observed via inventory
    installed_patch_ids: List[str] = Field(default_factory=list)
    available_patch_ids: List[str] = Field(default_factory=list)
    fix_kb_ids: List[str] = Field(default_factory=list)  # Known KBs that fix this CVE when patch_status='none'


class VMPatchInventoryItem(BaseModel):
    """Patch evidence shown on the VM vulnerability detail page."""
    patch_id: str
    patch_name: str
    status: str  # installed, available
    kb_ids: List[str] = Field(default_factory=list)
    cve_ids: List[str] = Field(default_factory=list)
    classification: Optional[str] = None
    published_date: Optional[str] = None


class PatchCoverageSummary(BaseModel):
    """Comparison of affecting CVEs versus installed patch evidence for a VM."""
    installed_patch_inventory_available: bool = False
    available_patch_assessment_available: bool = False
    installed_patch_count: int = 0
    installed_patch_identifier_count: int = 0
    available_patch_identifier_count: int = 0
    available_patch_count: int = 0
    covered_cves: int = 0
    not_patched_cves: int = 0
    patchable_unpatched_cves: int = 0
    no_patch_evidence_cves: int = 0
    unknown_patch_status_cves: int = 0
    patch_derived_cves: int = 0
    patch_derived_missing_cves: int = 0
    covered_cve_ids: List[str] = Field(default_factory=list)
    not_patched_cve_ids: List[str] = Field(default_factory=list)
    patch_derived_cve_ids: List[str] = Field(default_factory=list)
    patch_derived_missing_cve_ids: List[str] = Field(default_factory=list)
    installed_patch_entries: List[VMPatchInventoryItem] = Field(default_factory=list)
    available_patch_entries: List[VMPatchInventoryItem] = Field(default_factory=list)


class VMVulnerabilityResponse(BaseModel):
    """Response for GET /api/cve/inventory/{vm_id}."""
    vm_id: str
    vm_name: str
    resource_group: Optional[str] = None
    subscription_id: Optional[str] = None
    os_type: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    location: Optional[str] = None
    scan_id: str
    scan_date: str
    total_cves: int
    cves_by_severity: Dict[str, int]  # {"CRITICAL": 5, "HIGH": 12, ...}
    cve_details: List[VMCVEDetail]
    patch_coverage: PatchCoverageSummary = Field(default_factory=PatchCoverageSummary)
    pagination: Optional[Dict[str, Any]] = None  # {offset, limit, total, has_more}
    unpatched_by_severity: Dict[str, int] = Field(default_factory=dict)  # NEW — pre-computed from scan


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
    patch_status: str = "unknown"  # available, installed, pending, none, unknown


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
    "PatchAdvisoryEdge",
    "KBCVEEdge",          # backward-compat alias for PatchAdvisoryEdge
    "MsrcKbCveRecord",
    "CVESearchRequest",
    "CVESearchResponse",
    "CVEDetailResponse",
    "VMScanTarget",
    "CVEMatch",
    "ScanResult",
    "VMCVEMatchDocument",
    "CVEScanRequest",
    "CVEScanStatusResponse",
    "ApplicablePatch",
    "CVEPatchMapping",
    "CVEPatchRequest",
    "VMCVEDetail",
    "VMPatchInventoryItem",
    "PatchCoverageSummary",
    "VMVulnerabilityResponse",
    "AffectedVMDetail",
    "CVEAffectedVMsResponse",
]
