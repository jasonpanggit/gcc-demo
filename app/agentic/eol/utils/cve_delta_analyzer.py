"""
CVE Delta Analyzer

Compares current CVE scan against baseline to identify new vulnerabilities,
resolved CVEs, and severity changes for alerting.
"""

from typing import Optional, List, Set, Dict, Any
from datetime import datetime, timezone

try:
    from models.cve_alert_models import CVEDelta, CVEAlertItem
    from models.cve_models import ScanResult, CVEMatch
    from utils.cve_service import CVEService
    from utils.cve_patch_mapper import CVEPatchMapper
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_alert_models import CVEDelta, CVEAlertItem
    from app.agentic.eol.models.cve_models import ScanResult, CVEMatch
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_patch_mapper import CVEPatchMapper
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)


class CVEDeltaAnalyzer:
    """Analyzes differences between CVE scans to detect new vulnerabilities."""

    def __init__(self, scan_repository, cve_service: CVEService, patch_mapper: CVEPatchMapper):
        """
        Initialize delta analyzer.

        Args:
            scan_repository: CVEScanRepository instance for querying scans
            cve_service: CVEService for fetching CVE details
            patch_mapper: CVEPatchMapper for checking patch availability
        """
        self.scan_repository = scan_repository
        self.cve_service = cve_service
        self.patch_mapper = patch_mapper

    async def detect_new_cves(self, current_scan_id: str) -> CVEDelta:
        """
        Compare current scan against most recent baseline to identify new CVE exposures.

        Algorithm:
        1. Fetch baseline scan (most recent scan before current)
        2. Extract CVE ID sets from both scans
        3. Calculate set differences (new, resolved)
        4. Enrich new CVEs with details and affected VM info
        5. Check for severity increases on existing CVEs

        Args:
            current_scan_id: ID of current completed scan

        Returns:
            CVEDelta with new_cves, resolved_cves, severity_changes
        """
        try:
            # Fetch current scan
            current_scan = await self.scan_repository.get(current_scan_id)
            if not current_scan:
                logger.error(f"Current scan {current_scan_id} not found")
                return self._empty_delta(current_scan_id)

            # Fetch baseline scan (most recent before current)
            baseline_scan = await self._get_baseline_scan(current_scan.started_at)

            # First scan case - no baseline to compare
            if not baseline_scan:
                logger.info("First scan detected - no baseline for comparison")
                return CVEDelta(
                    new_cves=[],
                    resolved_cves=[],
                    severity_changes=[],
                    is_first_scan=True,
                    current_scan_id=current_scan_id,
                    current_timestamp=current_scan.started_at
                )

            # Extract CVE ID sets
            baseline_cve_ids = {match.cve_id for match in baseline_scan.matches}
            current_cve_ids = {match.cve_id for match in current_scan.matches}

            # Calculate deltas
            new_cve_ids = current_cve_ids - baseline_cve_ids
            resolved_cve_ids = baseline_cve_ids - current_cve_ids

            logger.info(f"Delta analysis: {len(new_cve_ids)} new, {len(resolved_cve_ids)} resolved")

            # Enrich new CVEs with details
            new_cves = await self._enrich_new_cves(new_cve_ids, current_scan.matches)

            # Check for severity changes
            severity_changes = await self._detect_severity_changes(
                baseline_scan.matches,
                current_scan.matches
            )

            return CVEDelta(
                new_cves=new_cves,
                resolved_cves=list(resolved_cve_ids),
                severity_changes=severity_changes,
                is_first_scan=False,
                baseline_scan_id=baseline_scan.scan_id,
                current_scan_id=current_scan_id,
                baseline_timestamp=baseline_scan.started_at,
                current_timestamp=current_scan.started_at
            )

        except Exception as e:
            logger.error(f"Delta detection failed: {e}", exc_info=True)
            return self._empty_delta(current_scan_id)

    async def _get_baseline_scan(self, current_scan_time: str) -> Optional[ScanResult]:
        """
        Query Cosmos for most recent scan before current.

        Args:
            current_scan_time: ISO timestamp of current scan

        Returns:
            Most recent completed scan before current, or None if first scan
        """
        try:
            query = f"""
                SELECT * FROM c
                WHERE c.status = 'completed'
                AND c.started_at < '{current_scan_time}'
                ORDER BY c.started_at DESC
                OFFSET 0 LIMIT 1
            """

            items = await self.scan_repository.query(query)

            if not items:
                logger.info("No baseline scan found - this is the first scan")
                return None

            return ScanResult(**items[0])

        except Exception as e:
            logger.warning(f"Failed to fetch baseline scan: {e}")
            return None

    async def _enrich_new_cves(
        self,
        new_cve_ids: Set[str],
        current_matches: List[CVEMatch]
    ) -> List[CVEAlertItem]:
        """
        Enrich new CVE IDs with full details and affected VM information.

        Args:
            new_cve_ids: Set of CVE IDs that are new in current scan
            current_matches: All CVE matches from current scan

        Returns:
            List of enriched CVEAlertItem objects
        """
        enriched_cves = []

        for cve_id in new_cve_ids:
            try:
                # Get affected VMs from current scan matches
                affected_matches = [m for m in current_matches if m.cve_id == cve_id]
                affected_vm_ids = [m.vm_id for m in affected_matches]
                affected_vm_names = [m.vm_name for m in affected_matches]

                # Fetch CVE details
                cve_details = await self.cve_service.get_cve(cve_id)

                # Check patch availability
                patch_info = await self.patch_mapper.get_patches_for_cve(cve_id)
                patch_available = bool(patch_info and patch_info.get("available_patches"))
                patch_kb_ids = [p.get("kb_id", "") for p in patch_info.get("available_patches", [])] if patch_info else []

                # Determine severity and CVSS score
                cvss_score = 0.0
                severity = "UNKNOWN"
                if cve_details:
                    if hasattr(cve_details, 'cvss_score') and cve_details.cvss_score:
                        cvss_score = cve_details.cvss_score
                    elif hasattr(cve_details, 'cvss_v3_score'):
                        cvss_score = cve_details.cvss_v3_score or 0.0

                    if hasattr(cve_details, 'severity'):
                        severity = cve_details.severity or self._score_to_severity(cvss_score)
                    else:
                        severity = self._score_to_severity(cvss_score)

                # Use first match for published_date if available
                published_date = affected_matches[0].published_date if affected_matches and affected_matches[0].published_date else ""

                # Get description from CVE details
                description = None
                if cve_details and hasattr(cve_details, 'description'):
                    description = cve_details.description

                alert_item = CVEAlertItem(
                    cve_id=cve_id,
                    severity=severity,
                    cvss_score=cvss_score,
                    affected_vms=affected_vm_ids,
                    affected_vm_names=affected_vm_names,
                    published_date=published_date,
                    patch_available=patch_available,
                    patch_kb_ids=patch_kb_ids,
                    description=description
                )

                enriched_cves.append(alert_item)

            except Exception as e:
                logger.warning(f"Failed to enrich CVE {cve_id}: {e}")
                # Include minimal item even if enrichment fails
                enriched_cves.append(CVEAlertItem(
                    cve_id=cve_id,
                    severity="UNKNOWN",
                    cvss_score=0.0,
                    affected_vms=affected_vm_ids if 'affected_vm_ids' in locals() else [],
                    affected_vm_names=affected_vm_names if 'affected_vm_names' in locals() else [],
                    published_date="",
                    patch_available=False
                ))

        return enriched_cves

    async def _detect_severity_changes(
        self,
        baseline_matches: List[CVEMatch],
        current_matches: List[CVEMatch]
    ) -> List[Dict[str, Any]]:
        """
        Detect CVEs where severity increased between scans.

        Args:
            baseline_matches: CVE matches from baseline scan
            current_matches: CVE matches from current scan

        Returns:
            List of severity change records
        """
        severity_changes = []

        # Build maps of CVE ID to CVSS score
        baseline_scores = {}
        for match in baseline_matches:
            if match.cvss_score and match.cve_id not in baseline_scores:
                baseline_scores[match.cve_id] = match.cvss_score

        current_scores = {}
        for match in current_matches:
            if match.cvss_score and match.cve_id not in current_scores:
                current_scores[match.cve_id] = match.cvss_score

        # Find CVEs with increased scores
        for cve_id in set(baseline_scores.keys()) & set(current_scores.keys()):
            baseline_score = baseline_scores[cve_id]
            current_score = current_scores[cve_id]

            if current_score > baseline_score:
                severity_changes.append({
                    "cve_id": cve_id,
                    "baseline_cvss": baseline_score,
                    "current_cvss": current_score,
                    "baseline_severity": self._score_to_severity(baseline_score),
                    "current_severity": self._score_to_severity(current_score)
                })

        if severity_changes:
            logger.info(f"Detected {len(severity_changes)} severity increases")

        return severity_changes

    def _score_to_severity(self, cvss_score: float) -> str:
        """Convert CVSS score to severity level."""
        if cvss_score >= 9.0:
            return "CRITICAL"
        elif cvss_score >= 7.0:
            return "HIGH"
        elif cvss_score >= 4.0:
            return "MEDIUM"
        else:
            return "LOW"

    def _empty_delta(self, current_scan_id: str) -> CVEDelta:
        """Return empty delta for error cases."""
        return CVEDelta(
            new_cves=[],
            resolved_cves=[],
            severity_changes=[],
            is_first_scan=False,
            current_scan_id=current_scan_id,
            current_timestamp=datetime.now(timezone.utc).isoformat()
        )
