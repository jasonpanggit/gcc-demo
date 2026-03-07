"""CVE VM Service

Service layer for VM vulnerability queries.

Key capabilities:
- Query CVE vulnerabilities for specific VMs
- Query VMs affected by specific CVEs
- Enrich CVE matches with full details and patch availability
- Calculate severity breakdowns
- L1 caching for scan results and CVE details
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from cachetools import TTLCache

try:
    from models.cve_models import (
        VMVulnerabilityResponse, VMCVEDetail, CVEAffectedVMsResponse,
        AffectedVMDetail, ScanResult, CVEMatch, UnifiedCVE
    )
    from utils.cve_service import CVEService
    from utils.cve_patch_mapper import CVEPatchMapper
    from utils.cve_scanner import CVEScanner
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import (
        VMVulnerabilityResponse, VMCVEDetail, CVEAffectedVMsResponse,
        AffectedVMDetail, ScanResult, CVEMatch, UnifiedCVE
    )
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_patch_mapper import CVEPatchMapper
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


class CVEVMService:
    """Service for VM-CVE relationship queries.

    Provides bidirectional CVE ↔ VM queries with enrichment.

    Cache strategy:
    - L1 cache for latest scan result (5 min TTL)
    - L1 cache for CVE details (15 min TTL)
    - Direct queries for VM metadata
    """

    def __init__(
        self,
        cve_service: CVEService,
        patch_mapper: CVEPatchMapper,
        cve_scanner: CVEScanner
    ):
        self.cve_service = cve_service
        self.patch_mapper = patch_mapper
        self.cve_scanner = cve_scanner

        # L1 caches
        self._scan_cache: TTLCache = TTLCache(maxsize=10, ttl=300)  # 5 min TTL
        self._cve_cache: TTLCache = TTLCache(maxsize=1000, ttl=900)  # 15 min TTL

        logger.info("CVEVMService initialized with L1 caching")

    async def get_latest_scan(self) -> Optional[ScanResult]:
        """Return the latest completed CVE scan result."""
        return await self._get_latest_scan()

    async def get_vm_vulnerabilities(self, vm_id: str) -> Optional[VMVulnerabilityResponse]:
        """Get CVEs affecting a specific VM.

        Args:
            vm_id: VM identifier

        Returns:
            VMVulnerabilityResponse with enriched CVE details or None if VM not found
        """
        try:
            # Get latest scan result
            scan = await self._get_latest_scan()
            if not scan:
                logger.warning("No scan results available")
                return None

            # Filter matches for this VM
            vm_matches = [m for m in scan.matches if m.vm_id == vm_id]

            if not vm_matches:
                logger.info(f"No CVE matches found for VM {vm_id}")
                # Return empty response for known VM with no vulnerabilities
                vm_name = vm_id  # Default to vm_id if name not available
                return VMVulnerabilityResponse(
                    vm_id=vm_id,
                    vm_name=vm_name,
                    scan_id=scan.scan_id,
                    scan_date=scan.completed_at or scan.started_at,
                    total_cves=0,
                    cves_by_severity={},
                    cve_details=[]
                )

            # Enrich each match with full CVE details
            enriched_cves: List[VMCVEDetail] = []
            severity_counts: Dict[str, int] = {}

            for match in vm_matches:
                try:
                    detail = await self._enrich_cve_match(match)
                    enriched_cves.append(detail)

                    # Count by severity
                    severity = detail.severity
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1

                except Exception as e:
                    logger.warning(f"Failed to enrich CVE {match.cve_id}: {e}")
                    # Continue with partial results

            # Sort by CVSS score descending
            enriched_cves.sort(key=lambda x: x.cvss_score or 0.0, reverse=True)

            # Get VM name from first match
            vm_name = vm_matches[0].vm_name if vm_matches else vm_id

            response = VMVulnerabilityResponse(
                vm_id=vm_id,
                vm_name=vm_name,
                scan_id=scan.scan_id,
                scan_date=scan.completed_at or scan.started_at,
                total_cves=len(enriched_cves),
                cves_by_severity=severity_counts,
                cve_details=enriched_cves
            )

            logger.info(f"Retrieved {len(enriched_cves)} CVEs for VM {vm_id}")
            return response

        except Exception as e:
            logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
            raise

    async def get_cve_affected_vms(self, cve_id: str) -> Optional[CVEAffectedVMsResponse]:
        """Get VMs affected by a specific CVE.

        Args:
            cve_id: CVE identifier

        Returns:
            CVEAffectedVMsResponse with affected VM list or None if CVE has no matches
        """
        try:
            cve_id = cve_id.upper()

            # Verify CVE exists
            cve = await self.cve_service.get_cve(cve_id)
            if not cve:
                logger.warning(f"CVE {cve_id} not found")
                return None

            # Get latest scan result
            scan = await self._get_latest_scan()
            if not scan:
                logger.warning("No scan results available")
                return None

            # Filter matches for this CVE
            cve_matches = [m for m in scan.matches if m.cve_id == cve_id]

            if not cve_matches:
                logger.info(f"No VMs affected by CVE {cve_id}")
                return CVEAffectedVMsResponse(
                    cve_id=cve_id,
                    scan_id=scan.scan_id,
                    scan_date=scan.completed_at or scan.started_at,
                    total_vms=0,
                    affected_vms=[]
                )

            # Build affected VM details
            affected_vms: List[AffectedVMDetail] = []

            for match in cve_matches:
                try:
                    # Get patch status for this CVE
                    patch_status = await self._get_patch_status(cve_id, match.vm_id)

                    # Extract VM metadata from match
                    # Note: In a real implementation, we might query Resource Graph
                    # for additional VM metadata. For now, use what's in the match.
                    vm_detail = AffectedVMDetail(
                        vm_id=match.vm_id,
                        vm_name=match.vm_name,
                        resource_group="default",  # TODO: Get from Resource Graph
                        subscription_id="default",  # TODO: Get from Resource Graph
                        os_type="Linux",  # TODO: Get from scan target data
                        os_name=None,
                        os_version=None,
                        location="default",  # TODO: Get from Resource Graph
                        match_reason=match.match_reason,
                        patch_status=patch_status
                    )
                    affected_vms.append(vm_detail)

                except Exception as e:
                    logger.warning(f"Failed to process VM {match.vm_id}: {e}")
                    # Continue with partial results

            # Sort by VM name
            affected_vms.sort(key=lambda x: x.vm_name)

            response = CVEAffectedVMsResponse(
                cve_id=cve_id,
                scan_id=scan.scan_id,
                scan_date=scan.completed_at or scan.started_at,
                total_vms=len(affected_vms),
                affected_vms=affected_vms
            )

            logger.info(f"Found {len(affected_vms)} VMs affected by CVE {cve_id}")
            return response

        except Exception as e:
            logger.error(f"Failed to get affected VMs for CVE {cve_id}: {e}")
            raise

    async def _get_latest_scan(self) -> Optional[ScanResult]:
        """Get latest completed scan with L1 caching.

        Returns:
            Latest ScanResult or None if no scans found
        """
        # Check L1 cache
        cache_key = "latest_scan"
        if cache_key in self._scan_cache:
            logger.debug("Latest scan served from L1 cache")
            return self._scan_cache[cache_key]

        # Query latest scan from scanner
        try:
            scan = await self.cve_scanner.get_latest_scan_result()

            if scan and scan.status == "completed":
                # Cache for 5 minutes
                self._scan_cache[cache_key] = scan
                logger.debug(f"Cached latest scan: {scan.scan_id}")
                return scan

            return None

        except Exception as e:
            logger.error(f"Failed to get latest scan: {e}")
            return None

    async def _enrich_cve_match(self, match: CVEMatch) -> VMCVEDetail:
        """Enrich CVE match with full details and patch availability.

        Args:
            match: CVE match from scan

        Returns:
            VMCVEDetail with enriched data
        """
        cve_id = match.cve_id

        # Check L1 cache for CVE
        if cve_id in self._cve_cache:
            cve = self._cve_cache[cve_id]
        else:
            # Fetch from CVE service
            cve = await self.cve_service.get_cve(cve_id)
            if cve:
                self._cve_cache[cve_id] = cve

        # Get patch count
        try:
            patch_mapping = await self.patch_mapper.get_patches_for_cve(cve_id)
            patches_available = len(patch_mapping.patches)
        except Exception as e:
            logger.warning(f"Failed to get patches for {cve_id}: {e}")
            patches_available = 0

        # Build enriched detail
        if cve:
            # Use CVSS v3 if available, fall back to v2
            cvss_score = None
            severity = match.severity or "UNKNOWN"

            if cve.cvss_v3:
                cvss_score = cve.cvss_v3.base_score
                severity = cve.cvss_v3.base_severity
            elif cve.cvss_v2:
                cvss_score = cve.cvss_v2.base_score
                severity = cve.cvss_v2.base_severity

            return VMCVEDetail(
                cve_id=cve_id,
                severity=severity,
                cvss_score=cvss_score,
                published_date=cve.published_date.isoformat() if cve.published_date else None,
                description=cve.description,
                match_reason=match.match_reason,
                patches_available=patches_available
            )
        else:
            # CVE details not available, use match data
            return VMCVEDetail(
                cve_id=cve_id,
                severity=match.severity or "UNKNOWN",
                cvss_score=match.cvss_score,
                published_date=match.published_date,
                description=f"CVE {cve_id}",
                match_reason=match.match_reason,
                patches_available=patches_available
            )

    async def _get_patch_status(self, cve_id: str, vm_id: str) -> Optional[str]:
        """Get patch installation status for CVE on VM.

        Args:
            cve_id: CVE identifier
            vm_id: VM identifier

        Returns:
            Patch status: "available", "installed", "pending", or None
        """
        try:
            # Query patch mapping
            patch_mapping = await self.patch_mapper.get_patches_for_cve(cve_id)

            if not patch_mapping.patches:
                return None

            # Check if any patches are available for this VM
            # TODO: Query actual patch installation status from patch orchestrator
            # For now, return "available" if patches exist
            return "available"

        except Exception as e:
            logger.warning(f"Failed to get patch status for {cve_id} on {vm_id}: {e}")
            return None
