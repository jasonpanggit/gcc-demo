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

import asyncio
import re
from collections import Counter
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import aiohttp
from cachetools import TTLCache

try:
    from models.cve_models import (
        VMVulnerabilityResponse, VMCVEDetail, VMPatchInventoryItem, PatchCoverageSummary, CVEAffectedVMsResponse,
        AffectedVMDetail, ScanResult, CVEMatch, UnifiedCVE
    )
    from utils.cve_service import CVEService
    from utils.cve_patch_mapper import CVEPatchMapper
    from utils.cve_scanner import CVEScanner
    from utils.config import config
    from utils.logging_config import get_logger
    from utils.normalization import normalize_kb_id, normalize_os_name_version
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import (
        VMVulnerabilityResponse, VMCVEDetail, VMPatchInventoryItem, PatchCoverageSummary, CVEAffectedVMsResponse,
        AffectedVMDetail, ScanResult, CVEMatch, UnifiedCVE
    )
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_patch_mapper import CVEPatchMapper
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.normalization import normalize_kb_id, normalize_os_name_version

logger = get_logger(__name__)


def _extract_release_year(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    match = re.search(r"(20\d{2}|19\d{2})", str(value))
    return match.group(1) if match else None


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
        self._vm_patch_context_cache: TTLCache = TTLCache(maxsize=128, ttl=300)

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

            vm_inventory_by_id = await self._get_vm_inventory_by_ids([vm_id])
            vm_inventory = vm_inventory_by_id.get(vm_id.lower())

            # Filter matches for this VM
            vm_matches = [m for m in scan.matches if m.vm_id == vm_id]

            if not vm_matches:
                logger.info(f"No CVE matches found for VM {vm_id}")
                subscription_id, resource_group = self._parse_resource_id(vm_id)
                vm_name = getattr(vm_inventory, "name", None) or vm_id
                os_type = getattr(vm_inventory, "os_type", None)
                location = getattr(vm_inventory, "location", None)
                os_name = None
                os_version = None
                patch_coverage = PatchCoverageSummary()
                enriched_cves: List[VMCVEDetail] = []

                if vm_inventory:
                    subscription_id = vm_inventory.subscription_id or subscription_id
                    resource_group = vm_inventory.resource_group or resource_group
                    os_name, os_version = self._normalize_os_fields(vm_inventory.os_name, vm_inventory.os_version)
                    inventory_matches = await self._build_inventory_fallback_matches(vm_inventory)

                    if inventory_matches:
                        patch_context = await self._get_vm_patch_context(inventory_matches[0])

                        semaphore = asyncio.Semaphore(8)

                        async def enrich_match(match: CVEMatch) -> Optional[VMCVEDetail]:
                            async with semaphore:
                                try:
                                    return await self._enrich_cve_match(match)
                                except Exception as e:
                                    logger.warning(f"Failed to enrich fallback CVE {match.cve_id}: {e}")
                                    return None

                        enriched_results = await asyncio.gather(
                            *(enrich_match(match) for match in inventory_matches),
                            return_exceptions=False,
                        )
                        enriched_cves = [detail for detail in enriched_results if detail]
                        derived_cves = await self._build_patch_derived_cve_details(
                            {detail.cve_id for detail in enriched_cves},
                            patch_context,
                        )
                        enriched_cves.extend(derived_cves)
                    else:
                        synthetic_match = CVEMatch(
                            cve_id="CVE-NONE",
                            vm_id=vm_id,
                            vm_name=vm_name,
                            match_reason="No affecting CVEs found in latest scan",
                        )
                        patch_context = await self._get_vm_patch_context(synthetic_match)
                        enriched_cves = await self._build_patch_derived_cve_details(set(), patch_context)

                    patch_coverage = self._build_patch_coverage_summary(enriched_cves, patch_context)

                severity_counts = dict(Counter(detail.severity for detail in enriched_cves))
                enriched_cves.sort(key=lambda x: x.cvss_score or 0.0, reverse=True)

                return VMVulnerabilityResponse(
                    vm_id=vm_id,
                    vm_name=vm_name,
                    resource_group=resource_group,
                    subscription_id=subscription_id if subscription_id != "unknown" else None,
                    os_type=os_type,
                    os_name=os_name,
                    os_version=os_version,
                    location=location if location != "unknown" else None,
                    scan_id=scan.scan_id,
                    scan_date=scan.completed_at or scan.started_at,
                    total_cves=len(enriched_cves),
                    cves_by_severity=severity_counts,
                    cve_details=enriched_cves,
                    patch_coverage=patch_coverage,
                )

            patch_context = await self._get_vm_patch_context(vm_matches[0])

            # Enrich each match with bounded concurrency to avoid long serial waits.
            enriched_cves: List[VMCVEDetail] = []
            severity_counts: Dict[str, int] = {}
            semaphore = asyncio.Semaphore(8)

            async def enrich_match(match: CVEMatch) -> Optional[VMCVEDetail]:
                async with semaphore:
                    try:
                        return await self._enrich_cve_match(match)
                    except Exception as e:
                        logger.warning(f"Failed to enrich CVE {match.cve_id}: {e}")
                        return None

            enriched_results = await asyncio.gather(
                *(enrich_match(match) for match in vm_matches),
                return_exceptions=False,
            )

            for detail in enriched_results:
                if not detail:
                    continue
                enriched_cves.append(detail)
                severity = detail.severity
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

            derived_cves = await self._build_patch_derived_cve_details(
                {detail.cve_id for detail in enriched_cves},
                patch_context,
            )
            for detail in derived_cves:
                enriched_cves.append(detail)
                severity_counts[detail.severity] = severity_counts.get(detail.severity, 0) + 1

            # Sort by CVSS score descending
            enriched_cves.sort(key=lambda x: x.cvss_score or 0.0, reverse=True)

            # Get VM name from first match
            vm_name = vm_matches[0].vm_name if vm_matches else vm_id

            response = VMVulnerabilityResponse(
                vm_id=vm_id,
                vm_name=vm_name,
                resource_group=getattr(vm_inventory, "resource_group", None),
                subscription_id=getattr(vm_inventory, "subscription_id", None),
                os_type=getattr(vm_inventory, "os_type", None),
                os_name=self._normalize_os_fields(
                    getattr(vm_inventory, "os_name", None),
                    getattr(vm_inventory, "os_version", None),
                )[0] if vm_inventory else None,
                os_version=self._normalize_os_fields(
                    getattr(vm_inventory, "os_name", None),
                    getattr(vm_inventory, "os_version", None),
                )[1] if vm_inventory else None,
                location=getattr(vm_inventory, "location", None),
                scan_id=scan.scan_id,
                scan_date=scan.completed_at or scan.started_at,
                total_cves=len(enriched_cves),
                cves_by_severity=severity_counts,
                cve_details=enriched_cves,
                patch_coverage=self._build_patch_coverage_summary(enriched_cves, patch_context),
            )

            logger.info(f"Retrieved {len(enriched_cves)} CVEs for VM {vm_id}")
            return response

        except Exception as e:
            logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
            raise

    async def get_vm_vulnerability_summary(
        self,
        vm_id: str,
        *,
        allow_live_cve_fallback: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return a lightweight vulnerability summary for overview requests."""
        try:
            scan = await self._get_latest_scan()
            if not scan:
                logger.warning("No scan results available")
                return None

            vm_inventory_by_id = await self._get_vm_inventory_by_ids([vm_id])
            vm_inventory = vm_inventory_by_id.get(vm_id.lower())
            vm_matches = [match for match in scan.matches if match.vm_id == vm_id]

            severity_counts = {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
            }

            if vm_matches:
                for match in vm_matches:
                    severity = str(match.severity or "UNKNOWN").upper()
                    if severity in severity_counts:
                        severity_counts[severity] += 1
                    else:
                        severity_counts["LOW"] += 1
            elif vm_inventory:
                inventory_matches = await self._build_inventory_fallback_matches(
                    vm_inventory,
                    allow_live_cve_fallback=allow_live_cve_fallback,
                )
                for match in inventory_matches:
                    severity = str(match.severity or "UNKNOWN").upper()
                    if severity in severity_counts:
                        severity_counts[severity] += 1
                    else:
                        severity_counts["LOW"] += 1

            total_cves = sum(severity_counts.values())
            if vm_inventory:
                os_name, os_version = self._normalize_os_fields(vm_inventory.os_name, vm_inventory.os_version)
            else:
                os_name, os_version = None, None

            return {
                "vm_id": vm_id,
                "vm_name": getattr(vm_inventory, "name", None) or vm_id,
                "resource_group": getattr(vm_inventory, "resource_group", None),
                "subscription_id": getattr(vm_inventory, "subscription_id", None),
                "os_type": getattr(vm_inventory, "os_type", None),
                "os_name": os_name,
                "os_version": os_version,
                "location": getattr(vm_inventory, "location", None),
                "total_cves": total_cves,
                "critical": severity_counts["CRITICAL"],
                "high": severity_counts["HIGH"],
                "medium": severity_counts["MEDIUM"],
                "low": severity_counts["LOW"],
                "scan_id": scan.scan_id,
                "scan_date": scan.completed_at or scan.started_at,
            }
        except Exception as e:
            logger.error("Failed to build vulnerability summary for VM %s: %s", vm_id, e)
            raise

    async def _build_inventory_fallback_matches(
        self,
        vm_inventory: Any,
        *,
        allow_live_cve_fallback: bool = True,
    ) -> List[CVEMatch]:
        """Build CVE matches directly from inventory-synced cached CVEs for a VM OS identity."""
        if not vm_inventory:
            return []

        filters = self._build_inventory_search_filters(vm_inventory)
        if not filters:
            return []

        try:
            cached_cves = await self.cve_service.search_cves(
                filters=filters,
                limit=10000,
                offset=0,
                allow_live_fallback=allow_live_cve_fallback,
            )
        except Exception as e:
            logger.warning("Inventory-backed CVE lookup failed for VM %s: %s", getattr(vm_inventory, "name", "unknown"), e)
            return []

        os_name, os_version = self._normalize_os_fields(vm_inventory.os_name, vm_inventory.os_version)
        version_part = f" {os_version}" if os_version else ""
        matches: List[CVEMatch] = []
        for cve in cached_cves:
            try:
                if not self.cve_scanner.is_vm_affected_by_cve(vm_inventory, cve):
                    continue

                matches.append(
                    CVEMatch(
                        cve_id=cve.cve_id,
                        vm_id=vm_inventory.vm_id,
                        vm_name=vm_inventory.name,
                        match_reason=f"OS {os_name or vm_inventory.os_type}{version_part} affected",
                        cvss_score=cve.cvss_v3.base_score if cve.cvss_v3 else (cve.cvss_v2.base_score if cve.cvss_v2 else None),
                        severity=cve.cvss_v3.base_severity if cve.cvss_v3 else (cve.cvss_v2.base_severity if cve.cvss_v2 else None),
                        published_date=cve.published_date.isoformat() if cve.published_date else None,
                    )
                )
            except Exception as e:
                logger.warning("Inventory fallback match failed for CVE %s on VM %s: %s", cve.cve_id, vm_inventory.name, e)

        return matches

    def _build_inventory_search_filters(self, vm_inventory: Any) -> Dict[str, Any]:
        raw_name = getattr(vm_inventory, "os_name", None) or getattr(vm_inventory, "os_type", None)
        raw_version = getattr(vm_inventory, "os_version", None)
        if not raw_name:
            return {}

        normalized_name, normalized_version = normalize_os_name_version(raw_name, raw_version)
        if not normalized_name:
            return {}

        normalized_name = normalized_name.strip().lower()
        if normalized_name == "windowsserver":
            normalized_name = "windows server"

        release_year = _extract_release_year(raw_version) or _extract_release_year(normalized_version)
        version = release_year or (normalized_version.strip().lower() if normalized_version else None)

        vendor_map = {
            "ubuntu": "ubuntu",
            "windows server": "microsoft",
            "windows": "microsoft",
            "rhel": "redhat",
            "centos": "centos",
            "debian": "debian",
        }

        keyword_parts = [normalized_name]
        if version:
            keyword_parts.append(version)

        filters: Dict[str, Any] = {"keyword": " ".join(keyword_parts)}
        vendor = vendor_map.get(normalized_name)
        if vendor:
            filters["vendor"] = vendor
        return filters

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

            vm_inventory_by_id = await self._get_vm_inventory_by_ids([m.vm_id for m in cve_matches])

            if not cve_matches:
                fallback_vms = await self._find_affected_vms_by_inventory(cve)
                if not fallback_vms:
                    logger.info(f"No VMs affected by CVE {cve_id}")
                    return CVEAffectedVMsResponse(
                        cve_id=cve_id,
                        scan_id=scan.scan_id,
                        scan_date=scan.completed_at or scan.started_at,
                        total_vms=0,
                        affected_vms=[]
                    )

                response = CVEAffectedVMsResponse(
                    cve_id=cve_id,
                    scan_id=scan.scan_id,
                    scan_date=scan.completed_at or scan.started_at,
                    total_vms=len(fallback_vms),
                    affected_vms=sorted(fallback_vms, key=lambda vm: vm.vm_name.lower())
                )

                logger.info(f"Found {len(fallback_vms)} VMs affected by CVE {cve_id} via inventory fallback")
                return response

            # Build affected VM details
            affected_vms: List[AffectedVMDetail] = []
            patch_status = await self._get_patch_status_for_cve(cve_id)

            for match in cve_matches:
                try:
                    vm_detail = self._build_affected_vm_detail(
                        match=match,
                        patch_status=patch_status,
                        vm_inventory=vm_inventory_by_id.get(match.vm_id.lower()),
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

    async def _get_vm_inventory_by_ids(self, vm_ids: List[str]) -> Dict[str, Any]:
        """Lookup current VM metadata by resource ID for response enrichment."""
        if not vm_ids or not hasattr(self.cve_scanner, "get_vm_targets_by_ids"):
            return {}

        try:
            return await self.cve_scanner.get_vm_targets_by_ids(vm_ids)
        except Exception as e:
            logger.warning(f"Failed to load VM inventory metadata: {e}")
            return {}

    async def _find_affected_vms_by_inventory(self, cve: UnifiedCVE) -> List[AffectedVMDetail]:
        """Fallback matcher that compares current VM inventory to CVE products."""
        if not hasattr(self.cve_scanner, "get_vm_targets") or not hasattr(self.cve_scanner, "is_vm_affected_by_cve"):
            return []

        try:
            vm_targets = await self.cve_scanner.get_vm_targets(include_arc=True)
        except Exception as e:
            logger.warning(f"Failed to discover VM inventory for fallback matching: {e}")
            return []

        affected_vms: List[AffectedVMDetail] = []
        patch_status = await self._get_patch_status_for_cve(cve.cve_id)
        for vm in vm_targets:
            try:
                if not self.cve_scanner.is_vm_affected_by_cve(vm, cve):
                    continue

                os_name, os_version = self._normalize_os_fields(vm.os_name, vm.os_version)
                version_part = f" {os_version}" if os_version else ""
                affected_vms.append(
                    AffectedVMDetail(
                        vm_id=vm.vm_id,
                        vm_name=vm.name,
                        resource_group=vm.resource_group,
                        subscription_id=vm.subscription_id,
                        os_type=vm.os_type or "Unknown",
                        os_name=os_name,
                        os_version=os_version,
                        location=vm.location,
                        match_reason=f"OS {os_name or vm.os_type}{version_part} affected",
                        patch_status=patch_status,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed inventory fallback match for VM {getattr(vm, 'name', 'unknown')}: {e}")

        return affected_vms

    def _build_affected_vm_detail(
        self,
        match: CVEMatch,
        patch_status: Optional[str],
        vm_inventory: Optional[Any] = None,
    ) -> AffectedVMDetail:
        """Build a UI-friendly VM detail using inventory metadata when available."""
        subscription_id, resource_group = self._parse_resource_id(match.vm_id)

        if vm_inventory:
            subscription_id = vm_inventory.subscription_id or subscription_id
            resource_group = vm_inventory.resource_group or resource_group
            os_type = vm_inventory.os_type or self._infer_os_type_from_text(match.match_reason)
            os_name, os_version = self._normalize_os_fields(vm_inventory.os_name, vm_inventory.os_version)
            location = vm_inventory.location or "unknown"
        else:
            inferred_os_name, inferred_os_version = self._extract_os_from_match_reason(match.match_reason)
            os_name, os_version = self._normalize_os_fields(inferred_os_name, inferred_os_version)
            os_type = self._infer_os_type_from_text(os_name or match.match_reason)
            location = "unknown"

        return AffectedVMDetail(
            vm_id=match.vm_id,
            vm_name=match.vm_name,
            resource_group=resource_group,
            subscription_id=subscription_id,
            os_type=os_type,
            os_name=os_name,
            os_version=os_version,
            location=location,
            match_reason=match.match_reason,
            patch_status=patch_status,
        )

    def _parse_resource_id(self, resource_id: str) -> tuple[str, str]:
        parts = [segment for segment in (resource_id or "").split("/") if segment]
        subscription_id = "unknown"
        resource_group = "unknown"

        for index, part in enumerate(parts):
            if part.lower() == "subscriptions" and index + 1 < len(parts):
                subscription_id = parts[index + 1]
            if part.lower() == "resourcegroups" and index + 1 < len(parts):
                resource_group = parts[index + 1]

        return subscription_id, resource_group

    def _extract_os_from_match_reason(self, match_reason: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not match_reason:
            return None, None

        match = re.search(r"OS\s+(.+?)\s+affected$", match_reason.strip(), re.IGNORECASE)
        if not match:
            return None, None

        os_text = match.group(1).strip()
        version_match = re.search(r"(20\d{2}|19\d{2}|\d+(?:\.\d+)*)$", os_text)
        if version_match:
            version = version_match.group(1)
            name = os_text[:version_match.start()].strip()
            return name or os_text, version

        return os_text, None

    def _normalize_os_fields(
        self,
        os_name: Optional[str],
        os_version: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if not os_name:
            return None, os_version

        if os_name.lower() == "windowsserver":
            os_name = "Windows Server"

        normalized_name, normalized_version = normalize_os_name_version(os_name, os_version)
        if normalized_name == "windows server":
            display_name = "Windows Server"
            version_match = re.search(r"(20\d{2}|19\d{2})", os_version or normalized_version or "")
            if version_match:
                normalized_version = version_match.group(1)
        elif normalized_name == "windows":
            display_name = "Windows"
        elif normalized_name == "rhel":
            display_name = "RHEL"
        else:
            display_name = normalized_name.title()

        return display_name, normalized_version

    def _infer_os_type_from_text(self, value: Optional[str]) -> str:
        text = (value or "").lower()
        return "Windows" if "windows" in text else "Linux"

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
        installed_patch_ids: List[str] = []
        available_patch_ids: List[str] = []
        try:
            patch_mapping = await self.patch_mapper.get_patches_for_cve(cve_id)
            patch_context = await self._get_vm_patch_context(match)
            (
                patch_status,
                patches_available,
                installed_patches,
                installed_patch_ids,
                available_patch_ids,
            ) = self._classify_patch_state(
                cve=cve,
                patch_mapping=patch_mapping,
                patch_context=patch_context,
            )
        except Exception as e:
            logger.warning(f"Failed to get patches for {cve_id}: {e}")
            patches_available = 0
            installed_patches = 0
            patch_status = "unknown"
            installed_patch_ids = []
            available_patch_ids = []

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
                patches_available=patches_available,
                patch_status=patch_status,
                installed_patches=installed_patches,
                installed_patch_ids=installed_patch_ids,
                available_patch_ids=available_patch_ids,
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
                patches_available=patches_available,
                patch_status=patch_status,
                installed_patches=installed_patches,
                installed_patch_ids=installed_patch_ids,
                available_patch_ids=available_patch_ids,
            )

    async def _get_vm_patch_context(self, match: CVEMatch) -> Dict[str, Any]:
        cache_key = (match.vm_id or match.vm_name or "").lower()
        cached = self._vm_patch_context_cache.get(cache_key)
        if cached is not None:
            return cached

        installed_identifiers, software_inventory_checked, installed_patches = await self._get_installed_patch_identifiers(match.vm_name)
        available_identifiers, patch_assessment_checked, available_patches = await self._get_available_patch_identifiers(match)
        installed_patch_entries, installed_patch_index = await self._build_patch_inventory_entries(installed_patches, "installed")
        available_patch_entries, available_patch_index = await self._build_patch_inventory_entries(available_patches, "available")
        patch_derived_cve_ids = sorted({
            cve_id
            for entry in (installed_patch_entries + available_patch_entries)
            for cve_id in entry.cve_ids
        })

        context = {
            "installed_identifiers": installed_identifiers,
            "available_identifiers": available_identifiers,
            "software_inventory_checked": software_inventory_checked,
            "patch_assessment_checked": patch_assessment_checked,
            "installed_patches": installed_patches,
            "available_patches": available_patches,
            "installed_patch_entries": installed_patch_entries,
            "available_patch_entries": available_patch_entries,
            "installed_patch_index": installed_patch_index,
            "available_patch_index": available_patch_index,
            "patch_derived_cve_ids": patch_derived_cve_ids,
        }
        self._vm_patch_context_cache[cache_key] = context
        return context

    def _build_patch_coverage_summary(
        self,
        cve_details: List[VMCVEDetail],
        patch_context: Optional[Dict[str, Any]] = None,
    ) -> PatchCoverageSummary:
        patch_context = patch_context or {}
        affecting_cve_ids = sorted({detail.cve_id for detail in cve_details})
        covered_cve_ids = sorted({detail.cve_id for detail in cve_details if detail.patch_status == "installed"})
        not_patched_cve_ids = sorted({detail.cve_id for detail in cve_details if detail.patch_status != "installed"})
        patch_derived_cve_ids = sorted(set(patch_context.get("patch_derived_cve_ids") or []))
        affecting_cve_id_set = set(affecting_cve_ids)
        patch_derived_missing_cve_ids = sorted(
            cve_id for cve_id in patch_derived_cve_ids if cve_id not in affecting_cve_id_set
        )

        return PatchCoverageSummary(
            installed_patch_inventory_available=bool(patch_context.get("software_inventory_checked")),
            available_patch_assessment_available=bool(patch_context.get("patch_assessment_checked")),
            installed_patch_count=len(patch_context.get("installed_patch_entries") or []),
            installed_patch_identifier_count=len(patch_context.get("installed_identifiers") or set()),
            available_patch_identifier_count=len(patch_context.get("available_identifiers") or set()),
            available_patch_count=len(patch_context.get("available_patches") or []),
            covered_cves=len(covered_cve_ids),
            not_patched_cves=len(not_patched_cve_ids),
            patchable_unpatched_cves=sum(1 for detail in cve_details if detail.patch_status == "available"),
            no_patch_evidence_cves=sum(1 for detail in cve_details if detail.patch_status == "none"),
            unknown_patch_status_cves=sum(1 for detail in cve_details if detail.patch_status == "unknown"),
            patch_derived_cves=len(patch_derived_cve_ids),
            patch_derived_missing_cves=len(patch_derived_missing_cve_ids),
            covered_cve_ids=covered_cve_ids,
            not_patched_cve_ids=not_patched_cve_ids,
            patch_derived_cve_ids=patch_derived_cve_ids,
            patch_derived_missing_cve_ids=patch_derived_missing_cve_ids,
            installed_patch_entries=list(patch_context.get("installed_patch_entries") or []),
            available_patch_entries=list(patch_context.get("available_patch_entries") or []),
        )

    async def _get_installed_patch_identifiers(self, vm_name: str) -> tuple[set[str], bool, List[Dict[str, Any]]]:
        if not vm_name:
            return set(), False, []

        try:
            from main import get_eol_orchestrator

            orchestrator = get_eol_orchestrator()
            inventory_agent = orchestrator.agents.get("software_inventory")
            if not inventory_agent:
                return set(), False

            result = await inventory_agent.get_software_inventory(
                days=90,
                computer_filter=vm_name,
                limit=None,
                use_cache=True,
                skip_eol_enrichment=True,
            )
            identifiers: set[str] = set()
            patch_records: List[Dict[str, Any]] = []
            for item in result.get("data") or []:
                software_type = str(item.get("software_type") or "").lower()
                patch_name = str(item.get("name") or item.get("software") or "")
                if software_type != "patch" and not re.search(r'KB\d+', patch_name, re.IGNORECASE):
                    continue
                patch_record = {
                    "patchName": patch_name,
                    "kbId": item.get("kb_id") or item.get("kbId"),
                    "publishedDate": item.get("installed_on") or item.get("install_date") or item.get("collected_at"),
                    "classification": item.get("classification") or item.get("category"),
                }
                identifiers.update(self._extract_patch_identifiers(patch_record))
                patch_records.append(patch_record)

            return identifiers, True, patch_records
        except Exception as e:
            logger.debug("Failed to load installed patch inventory for %s: %s", vm_name, e)
            return set(), False, []

    async def _get_available_patch_identifiers(self, match: CVEMatch) -> tuple[set[str], bool, List[Dict[str, Any]]]:
        subscription_id, _ = self._parse_resource_id(match.vm_id)
        if not subscription_id or subscription_id == "unknown":
            return set(), False, []

        vm_type = self._resolve_vm_type(match.vm_id)

        try:
            result = await self.patch_mapper.patch_mcp_client.get_assessment_result(
                machine_name=match.vm_name,
                subscription_id=subscription_id,
                vm_type=vm_type,
            )
            if result.get("success") and result.get("found"):
                identifiers: set[str] = set()
                available_patches = (result.get("patches") or {}).get("available_patches") or []
                for patch in available_patches:
                    identifiers.update(self._extract_patch_identifiers(patch))

                return identifiers, True, list(available_patches)
        except Exception as e:
            logger.debug("Patch MCP assessment lookup failed for %s: %s", match.vm_name, e)

        fallback = await self._get_available_patch_assessment_via_api(
            machine_name=match.vm_name,
            subscription_id=subscription_id,
            vm_type=vm_type,
        )
        if not fallback.get("success") or not fallback.get("found"):
            return set(), bool(fallback.get("success")), []

        identifiers: set[str] = set()
        available_patches = (fallback.get("patches") or {}).get("available_patches") or []
        for patch in available_patches:
            identifiers.update(self._extract_patch_identifiers(patch))

        return identifiers, True, list(available_patches)

    async def _get_available_patch_assessment_via_api(
        self,
        machine_name: str,
        subscription_id: str,
        vm_type: str,
    ) -> Dict[str, Any]:
        try:
            base_url = (config.app.base_url or "http://localhost:8000").rstrip("/")
            url = f"{base_url}/api/patch-management/last-assessment"
            params = {
                "machine_name": machine_name,
                "subscription_id": subscription_id,
                "vm_type": vm_type,
            }

            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status >= 400:
                        return {
                            "success": False,
                            "found": False,
                            "error": f"HTTP {response.status}",
                        }
                    result = await response.json()
                    return result if isinstance(result, dict) else {"success": False, "found": False}
        except Exception as e:
            logger.debug("Patch assessment API fallback failed for %s: %s", machine_name, e)
            return {"success": False, "found": False, "error": str(e)}

    async def _build_patch_inventory_entries(
        self,
        patches: List[Dict[str, Any]],
        status: str,
    ) -> tuple[List[VMPatchInventoryItem], List[Dict[str, Any]]]:
        if not patches:
            return [], []

        semaphore = asyncio.Semaphore(8)

        async def build_entry(patch: Dict[str, Any]) -> Optional[tuple[VMPatchInventoryItem, Dict[str, Any]]]:
            identifiers = self._extract_patch_identifiers(patch)
            kb_ids = sorted({
                kb for kb in (normalize_kb_id(identifier) for identifier in identifiers) if kb
            })
            patch_name = str(
                patch.get("patchName")
                or patch.get("patch_name")
                or patch.get("name")
                or patch.get("patchId")
                or patch.get("patch_id")
                or (kb_ids[0] if kb_ids else "Unknown Patch")
            ).strip()
            patch_id = kb_ids[0] if kb_ids else patch_name
            async with semaphore:
                try:
                    cve_ids = sorted(set(await self.patch_mapper.get_cve_ids_for_patch(patch)))
                except Exception as e:
                    logger.debug("Failed to derive CVEs from patch payload %s: %s", patch_name, e)
                    cve_ids = []

            entry = VMPatchInventoryItem(
                patch_id=patch_id,
                patch_name=patch_name,
                status=status,
                kb_ids=kb_ids,
                cve_ids=cve_ids,
                classification=patch.get("classification") or patch.get("rebootBehavior") or patch.get("classifications"),
                published_date=patch.get("publishedDate") or patch.get("published_date"),
            )
            return entry, {"entry": entry, "identifiers": identifiers}

        results = await asyncio.gather(*(build_entry(patch) for patch in patches), return_exceptions=False)
        entries: List[VMPatchInventoryItem] = []
        index: List[Dict[str, Any]] = []
        seen_patch_ids = set()
        for result in results:
            if not result:
                continue
            entry, index_row = result
            dedupe_key = (entry.status, entry.patch_id)
            if dedupe_key in seen_patch_ids:
                continue
            seen_patch_ids.add(dedupe_key)
            entries.append(entry)
            index.append(index_row)

        entries.sort(key=lambda item: (item.patch_name.lower(), item.patch_id.lower()))
        index.sort(key=lambda item: (item["entry"].patch_name.lower(), item["entry"].patch_id.lower()))
        return entries, index

    def _resolve_vm_type(self, vm_id: Optional[str]) -> str:
        resource_id = (vm_id or "").lower()
        if "/microsoft.compute/virtualmachines/" in resource_id:
            return "azure-vm"
        return "arc"

    def _extract_patch_identifiers(self, patch: Dict[str, Any]) -> set[str]:
        identifiers = set()
        for key in ("patchName", "patch_name", "kbId", "kb_id", "name", "patchId", "patch_id"):
            value = patch.get(key)
            if not value:
                continue
            text = str(value).strip()
            identifiers.add(text)
            identifiers.add(text.upper())
            identifiers.add(text.lower())
            normalized_kb = normalize_kb_id(text)
            if normalized_kb:
                identifiers.add(normalized_kb)
                identifiers.add(normalized_kb.upper())
                identifiers.add(normalized_kb.lower())
        return identifiers

    def _classify_patch_state(
        self,
        cve: Optional[UnifiedCVE],
        patch_mapping: Any,
        patch_context: Dict[str, Any],
    ) -> tuple[str, int, int, List[str], List[str]]:
        if not cve:
            return "unknown", 0, 0, [], []

        kb_numbers = self.patch_mapper.extract_cve_kb_numbers(cve)
        package_names = self.patch_mapper.extract_cve_package_names(cve)

        software_inventory_checked = bool(patch_context.get("software_inventory_checked"))
        patch_assessment_checked = bool(patch_context.get("patch_assessment_checked"))
        patch_checks_completed = software_inventory_checked or patch_assessment_checked

        installed_patch_ids = self._matching_patch_ids(
            patch_context.get("installed_patch_index") or [],
            kb_numbers,
            package_names,
        )
        available_patch_ids = self._matching_patch_ids(
            patch_context.get("available_patch_index") or [],
            kb_numbers,
            package_names,
        )

        installed_matches = len(installed_patch_ids)
        available_matches = len(available_patch_ids)

        if installed_matches > 0:
            return "installed", available_matches, installed_matches, installed_patch_ids, available_patch_ids
        if available_matches > 0:
            return "available", available_matches, 0, [], available_patch_ids
        if kb_numbers or package_names:
            return ("none", 0, 0, [], []) if patch_checks_completed else ("unknown", 0, 0, [], [])
        if getattr(patch_mapping, "patches", None):
            return "available", len(patch_mapping.patches), 0, [], []
        if patch_checks_completed:
            return "none", 0, 0, [], []
        return "unknown", 0, 0, [], []

    def _count_identifier_matches(
        self,
        patch_identifiers: set[str],
        kb_numbers: set[str],
        package_names: set[str],
    ) -> int:
        matches = 0
        upper_identifiers = {value.upper() for value in patch_identifiers}
        lower_identifiers = {value.lower() for value in patch_identifiers}

        for kb in kb_numbers:
            if kb.upper() in upper_identifiers:
                matches += 1

        for package_name in package_names:
            if any(package_name in identifier for identifier in lower_identifiers):
                matches += 1

        return matches

    def _matching_patch_ids(
        self,
        patch_index: List[Dict[str, Any]],
        kb_numbers: set[str],
        package_names: set[str],
    ) -> List[str]:
        matched_patch_ids: List[str] = []
        for item in patch_index:
            identifiers = item.get("identifiers") or set()
            if self._count_identifier_matches(identifiers, kb_numbers, package_names) > 0:
                matched_patch_ids.append(item["entry"].patch_id)
        return sorted(set(matched_patch_ids))

    async def _build_patch_derived_cve_details(
        self,
        existing_cve_ids: set[str],
        patch_context: Dict[str, Any],
    ) -> List[VMCVEDetail]:
        installed_entries = list(patch_context.get("installed_patch_entries") or [])
        available_entries = list(patch_context.get("available_patch_entries") or [])
        derived_ids = sorted({
            cve_id
            for entry in (installed_entries + available_entries)
            for cve_id in entry.cve_ids
            if cve_id not in existing_cve_ids
        })
        if not derived_ids:
            return []

        semaphore = asyncio.Semaphore(8)

        async def build_detail(cve_id: str) -> VMCVEDetail:
            installed_patch_ids = sorted({entry.patch_id for entry in installed_entries if cve_id in entry.cve_ids})
            available_patch_ids = sorted({entry.patch_id for entry in available_entries if cve_id in entry.cve_ids})
            async with semaphore:
                cve = await self.cve_service.get_cve(cve_id)

            patch_status = "installed" if installed_patch_ids else "available" if available_patch_ids else "unknown"
            match_reason = self._build_patch_derived_match_reason(installed_patch_ids, available_patch_ids)
            description = f"CVE {cve_id}"
            severity = "UNKNOWN"
            cvss_score = None
            published_date = None

            if cve:
                description = cve.description
                published_date = cve.published_date.isoformat() if cve.published_date else None
                if cve.cvss_v3:
                    severity = cve.cvss_v3.base_severity
                    cvss_score = cve.cvss_v3.base_score
                elif cve.cvss_v2:
                    severity = cve.cvss_v2.base_severity
                    cvss_score = cve.cvss_v2.base_score

            return VMCVEDetail(
                cve_id=cve_id,
                severity=severity,
                cvss_score=cvss_score,
                published_date=published_date,
                description=description,
                match_reason=match_reason,
                patches_available=len(available_patch_ids),
                patch_status=patch_status,
                installed_patches=len(installed_patch_ids),
                installed_patch_ids=installed_patch_ids,
                available_patch_ids=available_patch_ids,
            )

        details = await asyncio.gather(*(build_detail(cve_id) for cve_id in derived_ids), return_exceptions=False)
        details.sort(key=lambda item: item.cvss_score or 0.0, reverse=True)
        return details

    def _build_patch_derived_match_reason(
        self,
        installed_patch_ids: List[str],
        available_patch_ids: List[str],
    ) -> str:
        if installed_patch_ids and available_patch_ids:
            return (
                f"Derived from installed patch evidence ({', '.join(installed_patch_ids)}) and pending patch assessment "
                f"({', '.join(available_patch_ids)})"
            )
        if installed_patch_ids:
            return f"Derived from installed patch evidence ({', '.join(installed_patch_ids)})"
        if available_patch_ids:
            return f"Derived from pending patch assessment ({', '.join(available_patch_ids)})"
        return "Derived from patch evidence"

    async def _get_patch_status_for_cve(self, cve_id: str) -> str:
        """Get aggregate patch availability status for a CVE.

        Args:
            cve_id: CVE identifier

        Returns:
            Patch status: "available" when aggregate patch data exists, otherwise "unknown"
        """
        try:
            # Query patch mapping
            patch_mapping = await self.patch_mapper.get_patches_for_cve(cve_id)

            if not patch_mapping.patches:
                return "unknown"

            # Check if any patches are available for this VM
            # TODO: Query actual patch installation status from patch orchestrator
            # For now, return "available" if patches exist
            return "available"

        except Exception as e:
            logger.warning(f"Failed to get patch status for {cve_id}: {e}")
            return "unknown"
