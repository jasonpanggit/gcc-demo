"""CVE Patch Mapper

Maps CVEs to applicable patches from existing patch management system.

Key capabilities:
- Query available patches via patch MCP client
- Match CVE references to KB numbers (Microsoft)
- Match CVE vendor metadata to package names (Linux)
- Calculate patch priority from CVSS score + exposure count
- Generate patching recommendations
- Handle multi-patch scenarios
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Any

try:
    from models.cve_models import ApplicablePatch, CVEPatchMapping, UnifiedCVE
    from utils.cve_service import CVEService
    from utils.cve_scanner import CVEScanner
    from utils.patch_mcp_client import PatchMCPClient
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import ApplicablePatch, CVEPatchMapping, UnifiedCVE
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.patch_mcp_client import PatchMCPClient
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


class CVEPatchMapper:
    """Maps CVEs to applicable patches using existing patch management system."""

    def __init__(
        self,
        cve_service: CVEService,
        cve_scanner: CVEScanner,
        patch_mcp_client: PatchMCPClient
    ):
        self.cve_service = cve_service
        self.cve_scanner = cve_scanner
        self.patch_mcp_client = patch_mcp_client
        logger.info("CVEPatchMapper initialized")

    async def get_patches_for_cve(
        self,
        cve_id: str,
        subscription_ids: Optional[List[str]] = None
    ) -> CVEPatchMapping:
        """Get applicable patches for a CVE with priority ranking.

        Args:
            cve_id: CVE identifier
            subscription_ids: Subscriptions to query for patches

        Returns:
            CVEPatchMapping with ranked patches and recommendations
        """
        # Get CVE data
        cve = await self.cve_service.get_cve(cve_id)
        if not cve:
            logger.warning(f"CVE {cve_id} not found")
            return CVEPatchMapping(
                cve_id=cve_id,
                patches=[],
                priority_score=0,
                total_affected_vms=0,
                recommendation="CVE not found in database"
            )

        # Query available patches
        patches = await self._query_available_patches(subscription_ids)

        # Match patches to CVE
        matched_patches = await self._match_patches_to_cve(cve, patches)

        # Get exposure count from recent scans
        exposure_count = await self._get_exposure_count(cve_id)

        # Calculate priority
        priority_score = await self._calculate_priority_score(cve, exposure_count)

        # Generate recommendation
        severity = cve.cvss_v3.base_severity if cve.cvss_v3 else (cve.cvss_v2.base_severity if cve.cvss_v2 else "UNKNOWN")
        recommendation = await self._get_recommendation(priority_score, severity)

        return CVEPatchMapping(
            cve_id=cve_id,
            patches=matched_patches,
            priority_score=priority_score,
            total_affected_vms=exposure_count,
            recommendation=recommendation
        )

    async def _query_available_patches(
        self,
        subscription_ids: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """Query available patches via patch MCP client.

        Args:
            subscription_ids: Subscriptions to query

        Returns:
            List of patch data dictionaries
        """
        try:
            # Use patch MCP client to query assessments
            # Note: This calls the query_patch_assessments tool
            result = await self.patch_mcp_client.query_patch_assessments(
                subscription_ids=subscription_ids,
                classification="All"
            )

            if result.get("success"):
                return result.get("patches", [])
            else:
                logger.warning(f"Patch query failed: {result.get('error')}")
                return []

        except Exception as e:
            logger.error(f"Failed to query patches: {e}")
            return []

    async def _match_patches_to_cve(
        self,
        cve: UnifiedCVE,
        patches: List[Dict[str, Any]]
    ) -> List[ApplicablePatch]:
        """Match patches to CVE based on KB numbers or package names.

        Args:
            cve: CVE to match patches for
            patches: Available patches from patch system

        Returns:
            List of matched ApplicablePatch models
        """
        matched = []

        # Extract KB numbers from CVE references (Microsoft patches)
        kb_numbers = set()
        for ref in cve.references:
            # Look for KB numbers in URLs
            kb_match = re.search(r'KB\d+', ref.url, re.IGNORECASE)
            if kb_match:
                kb_numbers.add(kb_match.group().upper())

        logger.debug(f"Extracted KB numbers for {cve.cve_id}: {kb_numbers}")

        # Match patches by KB number
        for patch in patches:
            patch_name = patch.get("patchName", "")

            # Check KB number match
            if kb_numbers:
                for kb in kb_numbers:
                    if kb in patch_name.upper():
                        matched.append(ApplicablePatch(
                            patch_id=patch.get("patchId", patch_name),
                            patch_name=patch_name,
                            vendor="microsoft",
                            severity=patch.get("classification", "Unknown"),
                            release_date=patch.get("publishedDate"),
                            affected_vm_count=len(patch.get("affectedMachines", []))
                        ))
                        break

        # Match Linux packages from vendor metadata
        for vendor_meta in cve.vendor_metadata:
            for affected_pkg in vendor_meta.affected_packages:
                pkg_name = affected_pkg.get("package_name", "")
                if not pkg_name:
                    continue

                for patch in patches:
                    patch_name = patch.get("patchName", "")
                    if pkg_name.lower() in patch_name.lower():
                        matched.append(ApplicablePatch(
                            patch_id=patch.get("patchId", patch_name),
                            patch_name=patch_name,
                            vendor=vendor_meta.source,
                            severity=patch.get("classification", "Unknown"),
                            release_date=patch.get("publishedDate"),
                            affected_vm_count=len(patch.get("affectedMachines", []))
                        ))
                        break

        # Deduplicate by patch_id
        seen = set()
        unique_patches = []
        for patch in matched:
            if patch.patch_id not in seen:
                seen.add(patch.patch_id)
                unique_patches.append(patch)

        # Sort by release date (newest first)
        unique_patches.sort(key=lambda p: p.release_date or "", reverse=True)

        logger.info(f"Matched {len(unique_patches)} patches for {cve.cve_id}")
        return unique_patches

    async def _get_exposure_count(self, cve_id: str) -> int:
        """Get exposure count from most recent scan.

        Args:
            cve_id: CVE identifier

        Returns:
            Number of vulnerable VMs (0 if no scan data)
        """
        try:
            # Get most recent completed scan
            scans = await self.cve_scanner.list_recent_scans(limit=10)

            for scan in scans:
                if scan.status == "completed":
                    # Count VMs affected by this CVE
                    count = sum(1 for match in scan.matches if match.cve_id == cve_id)
                    if count > 0:
                        return count

            logger.debug(f"No exposure data found for {cve_id}")
            return 0

        except Exception as e:
            logger.error(f"Failed to get exposure count for {cve_id}: {e}")
            return 0

    async def _calculate_priority_score(
        self,
        cve: UnifiedCVE,
        exposure_count: int
    ) -> int:
        """Calculate patch priority score (0-100).

        Formula: (CVSS * 10) * 0.7 + min(exposure_count, 100) * 0.3

        Args:
            cve: CVE data
            exposure_count: Number of vulnerable VMs

        Returns:
            Priority score 0-100
        """
        # Get CVSS score (prefer v3, fallback to v2)
        cvss = 5.0  # Default medium severity
        if cve.cvss_v3:
            cvss = cve.cvss_v3.base_score
        elif cve.cvss_v2:
            cvss = cve.cvss_v2.base_score

        # Calculate weighted score
        cvss_component = (cvss * 10) * 0.7  # 70% weight on severity
        exposure_component = min(exposure_count, 100) * 0.3  # 30% weight on exposure

        priority = int(cvss_component + exposure_component)
        return max(0, min(100, priority))  # Clamp to 0-100

    async def _get_recommendation(
        self,
        priority_score: int,
        severity: str
    ) -> str:
        """Generate patching recommendation based on priority.

        Args:
            priority_score: Calculated priority (0-100)
            severity: CVE severity level

        Returns:
            Human-readable recommendation
        """
        if priority_score >= 85 or severity == "CRITICAL":
            return "Install immediately - Critical vulnerability with high exposure"
        elif priority_score >= 70:
            return "Schedule within 24 hours - High priority remediation needed"
        elif priority_score >= 50:
            return "Schedule within 1 week - Medium priority"
        else:
            return "Schedule during next maintenance window - Low priority"


# Singleton pattern
_cve_patch_mapper_instance: Optional['CVEPatchMapper'] = None


async def get_cve_patch_mapper() -> 'CVEPatchMapper':
    """Get the global CVE patch mapper instance, initializing if needed.

    Returns:
        Initialized CVEPatchMapper instance
    """
    global _cve_patch_mapper_instance

    if _cve_patch_mapper_instance is None:
        from utils.cve_service import get_cve_service
        from utils.cve_scanner import get_cve_scanner
        from utils.patch_mcp_client import get_patch_mcp_client

        cve_service = await get_cve_service()
        cve_scanner = await get_cve_scanner()
        patch_client = await get_patch_mcp_client()

        _cve_patch_mapper_instance = CVEPatchMapper(
            cve_service=cve_service,
            cve_scanner=cve_scanner,
            patch_client=patch_client
        )
        logger.info("CVE patch mapper singleton initialized")

    return _cve_patch_mapper_instance
