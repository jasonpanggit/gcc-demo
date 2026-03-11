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
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from cachetools import TTLCache

try:
    from models.cve_models import ApplicablePatch, CVEPatchMapping, UnifiedCVE
    from utils.cve_id_utils import filter_valid_cve_ids, is_valid_cve_id
    from utils.cve_service import CVEService
    from utils.cve_scanner import CVEScanner
    from utils.patch_mcp_client import PatchMCPClient
    from utils.vendor_feed_client import VendorFeedClient
    from utils.config import config
    from utils.logging_config import get_logger
    from utils.normalization import extract_kb_ids, normalize_kb_id
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import ApplicablePatch, CVEPatchMapping, UnifiedCVE
    from app.agentic.eol.utils.cve_id_utils import filter_valid_cve_ids, is_valid_cve_id
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.patch_mcp_client import PatchMCPClient
    from app.agentic.eol.utils.vendor_feed_client import VendorFeedClient
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.normalization import extract_kb_ids, normalize_kb_id

logger = get_logger(__name__)


class CVEPatchMapper:
    """Maps CVEs to applicable patches using existing patch management system."""

    def __init__(
        self,
        cve_service: CVEService,
        cve_scanner: CVEScanner,
        patch_mcp_client: PatchMCPClient,
        patch_install_history_repository=None,
        kb_cve_edge_repository=None,
    ):
        self.cve_service = cve_service
        self.cve_scanner = cve_scanner
        self.patch_mcp_client = patch_mcp_client
        self.patch_install_history_repository = patch_install_history_repository
        self.kb_cve_edge_repository = kb_cve_edge_repository
        self.supports_install_history = patch_install_history_repository is not None
        self._mapping_cache: TTLCache = TTLCache(maxsize=256, ttl=300)
        self._available_patches_cache: TTLCache = TTLCache(maxsize=32, ttl=300)
        self._exposure_summary_cache: TTLCache = TTLCache(maxsize=4, ttl=300)
        self._reverse_lookup_cache: TTLCache = TTLCache(maxsize=128, ttl=3600)
        self._vendor_feed_client: Optional[VendorFeedClient] = None
        logger.info("CVEPatchMapper initialized")

    def _get_vendor_feed_client(self) -> VendorFeedClient:
        if self._vendor_feed_client is None:
            self._vendor_feed_client = VendorFeedClient(
                redhat_base_url=config.cve_data.redhat_base_url,
                ubuntu_base_url=config.cve_data.ubuntu_base_url,
                msrc_base_url=config.cve_data.msrc_base_url,
                msrc_api_key=config.cve_data.msrc_api_key,
                request_timeout=config.cve_data.request_timeout,
                max_retries=config.cve_data.max_retries,
            )
        return self._vendor_feed_client

    def _infer_msrc_update_id_from_patch(self, patch: Dict[str, Any]) -> Optional[str]:
        patch_name = str(patch.get("patchName") or patch.get("patch_name") or "").strip()
        published_date = str(patch.get("publishedDate") or patch.get("published_date") or "").strip()

        if patch_name:
            match = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b", patch_name)
            if match:
                month_abbrev = {
                    "01": "Jan",
                    "02": "Feb",
                    "03": "Mar",
                    "04": "Apr",
                    "05": "May",
                    "06": "Jun",
                    "07": "Jul",
                    "08": "Aug",
                    "09": "Sep",
                    "10": "Oct",
                    "11": "Nov",
                    "12": "Dec",
                }[match.group(2)]
                return f"{match.group(1)}-{month_abbrev}"

        if published_date:
            try:
                published = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                return published.strftime("%Y-%b")
            except ValueError:
                return None

        return None

    async def _hydrate_reverse_edges(self, cve_ids: List[str]) -> None:
        if not self.kb_cve_edge_repository:
            return

        for cve_id in filter_valid_cve_ids(cve_ids):
            cve = await self.cve_service.get_cve(cve_id)
            if cve:
                await self.kb_cve_edge_repository.sync_cve_edges(cve)

    async def _get_vendor_cve_ids_for_patch(self, patch: Dict[str, Any], kb_number: str) -> List[str]:
        update_id = self._infer_msrc_update_id_from_patch(patch)
        cache_key = f"{kb_number}:{update_id or ''}"
        cached = self._reverse_lookup_cache.get(cache_key)
        if cached is not None:
            return cached

        vendor_client = self._get_vendor_feed_client()
        cve_ids = await vendor_client.fetch_microsoft_cves_for_kb(
            kb_number,
            update_id=update_id,
            patch_name=patch.get("patchName") or patch.get("patch_name"),
            published_date=patch.get("publishedDate") or patch.get("published_date"),
        )
        resolved = sorted(set(cve_ids))
        if resolved:
            await self._hydrate_reverse_edges(resolved)

        self._reverse_lookup_cache[cache_key] = resolved
        return resolved

    def _normalize_subscription_ids(self, subscription_ids: Optional[List[str]]) -> List[str]:
        normalized = [sub for sub in (subscription_ids or []) if sub]
        if normalized:
            return sorted(normalized)

        default_subscription = getattr(self.cve_scanner, "subscription_id", None)
        return [default_subscription] if default_subscription else []

    def _extract_patch_identifiers(self, patch: Dict[str, Any]) -> set[str]:
        identifiers = set()
        for key in ("patchName", "patch_name", "kbId", "kb_id", "name", "patchId", "patch_id"):
            value = patch.get(key)
            if value:
                text = str(value).strip()
                identifiers.add(text)
                identifiers.add(text.upper())
                normalized_kb = normalize_kb_id(text)
                if normalized_kb:
                    identifiers.add(normalized_kb)
        return identifiers

    def _append_machine_context(self, collected_patches: List[Dict[str, Any]], machine: Dict[str, Any], patch: Dict[str, Any]) -> None:
        normalized_patch = dict(patch)
        normalized_patch.setdefault("classification", ", ".join(patch.get("classifications") or []))
        normalized_patch.setdefault("affectedMachines", [])
        normalized_patch["affectedMachines"].append({
            "machineName": machine.get("machine_name"),
            "resourceGroup": machine.get("resource_group"),
            "subscriptionId": machine.get("subscription_id"),
            "vmType": machine.get("vm_type"),
        })
        collected_patches.append(normalized_patch)

    def _extract_cve_kb_numbers(self, cve: UnifiedCVE) -> set[str]:
        kb_numbers: set[str] = set()

        for ref in cve.references:
            kb_numbers.update(extract_kb_ids(ref.url))

        for vendor_meta in cve.vendor_metadata:
            advisory_id = normalize_kb_id(vendor_meta.advisory_id)
            if advisory_id:
                kb_numbers.add(advisory_id)

            kb_numbers.update(extract_kb_ids(vendor_meta.kb_numbers, allow_bare_numeric=True))

            metadata = vendor_meta.metadata or {}
            for field in ("kbArticles", "kb_numbers", "kbNumbers"):
                kb_numbers.update(extract_kb_ids(metadata.get(field), allow_bare_numeric=True))

        return kb_numbers

    def extract_cve_kb_numbers(self, cve: UnifiedCVE) -> set[str]:
        return self._extract_cve_kb_numbers(cve)

    def extract_cve_package_names(self, cve: UnifiedCVE) -> set[str]:
        return {
            str(pkg.get("package_name", "")).strip().lower()
            for vendor_meta in cve.vendor_metadata
            for pkg in vendor_meta.affected_packages
            if pkg.get("package_name")
        }

    async def get_install_history_for_cve(
        self,
        cve_id: str,
        time_range_days: int,
    ) -> List[Dict[str, Any]]:
        if not self.patch_install_history_repository:
            return []

        cve = await self.cve_service.get_cve(cve_id)
        if not cve:
            return []

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)
        install_records = await self.patch_install_history_repository.list_completed_since(cutoff_date.isoformat())
        matched_records: List[Dict[str, Any]] = []

        kb_numbers = self._extract_cve_kb_numbers(cve)

        vendor_packages = self.extract_cve_package_names(cve)

        for record in install_records:
            for patch in record.get("patches") or []:
                identifiers = self._extract_patch_identifiers(patch)
                if kb_numbers and any(kb in identifiers for kb in kb_numbers):
                    matched_records.append(record)
                    break

                patch_name = str(patch.get("patchName") or patch.get("patch_name") or "").lower()
                if patch_name and any(pkg in patch_name for pkg in vendor_packages):
                    matched_records.append(record)
                    break

        return matched_records

    async def get_cve_ids_for_kb(self, kb_number: str) -> List[str]:
        """Return cached CVE IDs mapped to a KB article when reverse edges are available."""
        if not self.kb_cve_edge_repository:
            return []
        return await self.kb_cve_edge_repository.get_cve_ids_for_kb(kb_number)

    async def get_cve_ids_for_patch(self, patch: Dict[str, Any]) -> List[str]:
        """Return cached CVE IDs mapped to a patch payload via normalized KB identifiers."""
        cve_ids = set()
        normalized_kbs = set()
        for identifier in self._extract_patch_identifiers(patch):
            kb_number = normalize_kb_id(identifier)
            if not kb_number:
                continue

            normalized_kbs.add(kb_number)
            if self.kb_cve_edge_repository:
                cve_ids.update(await self.kb_cve_edge_repository.get_cve_ids_for_kb(kb_number))

        if cve_ids:
            return sorted(cve_ids)

        for kb_number in normalized_kbs:
            cve_ids.update(await self._get_vendor_cve_ids_for_patch(patch, kb_number))

        return sorted(cve_ids)

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
        if not is_valid_cve_id(cve_id):
            logger.warning("Skipping patch lookup for non-standard CVE identifier %s", cve_id)
            return CVEPatchMapping(
                cve_id=cve_id,
                patches=[],
                priority_score=0,
                total_affected_vms=0,
                recommendation="Invalid CVE identifier"
            )

        normalized_subscriptions = self._normalize_subscription_ids(subscription_ids)
        cache_key = f"{cve_id.upper()}::{','.join(normalized_subscriptions)}"
        cached_mapping = self._mapping_cache.get(cache_key)
        if cached_mapping is not None:
            logger.debug("Patch mapping cache hit for %s", cve_id)
            return cached_mapping

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
        patches = await self._query_available_patches(normalized_subscriptions)

        # Match patches to CVE
        matched_patches = await self._match_patches_to_cve(cve, patches)

        # Get exposure count from recent scans
        exposure_count = await self._get_exposure_count(cve_id)

        # Calculate priority
        priority_score = await self._calculate_priority_score(cve, exposure_count)

        # Generate recommendation
        severity = cve.cvss_v3.base_severity if cve.cvss_v3 else (cve.cvss_v2.base_severity if cve.cvss_v2 else "UNKNOWN")
        recommendation = await self._get_recommendation(priority_score, severity)

        mapping = CVEPatchMapping(
            cve_id=cve_id,
            patches=matched_patches,
            priority_score=priority_score,
            total_affected_vms=exposure_count,
            recommendation=recommendation
        )
        self._mapping_cache[cache_key] = mapping
        return mapping

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
            subscriptions = self._normalize_subscription_ids(subscription_ids)
            cache_key = ",".join(subscriptions)
            cached_patches = self._available_patches_cache.get(cache_key)
            if cached_patches is not None:
                logger.debug("Available patches cache hit for subscriptions %s", cache_key)
                return cached_patches

            collected_patches: List[Dict[str, Any]] = []

            for subscription_id in subscriptions:
                for vm_type in ("arc", "azure-vm"):
                    result = await self.patch_mcp_client.query_patch_assessments(
                        subscription_id=subscription_id,
                        vm_type=vm_type,
                    )

                    if not result.get("success"):
                        logger.warning(
                            "Patch query failed for subscription %s vm_type %s: %s",
                            subscription_id,
                            vm_type,
                            result.get("error")
                        )
                        continue

                    for machine in result.get("data", []):
                        patch_info = machine.get("patches") or {}
                        available_patches = patch_info.get("available_patches") or []

                        for patch in available_patches:
                            self._append_machine_context(collected_patches, machine, patch)

            self._available_patches_cache[cache_key] = collected_patches
            return collected_patches

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
        kb_numbers = self._extract_cve_kb_numbers(cve)

        logger.debug(f"Extracted KB numbers for {cve.cve_id}: {kb_numbers}")

        # Match patches by KB number
        for patch in patches:
            patch_name = patch.get("patchName", "")
            patch_identifiers = self._extract_patch_identifiers(patch)

            # Check KB number match
            if kb_numbers:
                for kb in kb_numbers:
                    if kb in patch_identifiers or kb in patch_name.upper():
                        matched.append(ApplicablePatch(
                            patch_id=patch.get("patchId") or patch.get("kbId") or patch_name,
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
                            patch_id=patch.get("patchId") or patch.get("kbId") or patch_name,
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

        # logger.info(f"Matched {len(unique_patches)} patches for {cve.cve_id}")
        return unique_patches

    async def _get_exposure_count(self, cve_id: str) -> int:
        """Get exposure count from most recent scan.

        Args:
            cve_id: CVE identifier

        Returns:
            Number of vulnerable VMs (0 if no scan data)
        """
        try:
            cache_key = "latest_completed_scan_exposure_counts"
            exposure_counts = self._exposure_summary_cache.get(cache_key)

            if exposure_counts is None:
                exposure_counts = {}
                scans = await self.cve_scanner.list_recent_scans(limit=10)

                for scan in scans:
                    if scan.status != "completed":
                        continue

                    for match in scan.matches:
                        exposure_counts[match.cve_id] = exposure_counts.get(match.cve_id, 0) + 1
                    break

                self._exposure_summary_cache[cache_key] = exposure_counts

            count = exposure_counts.get(cve_id, 0)
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
            patch_mcp_client=patch_client
        )
        logger.info("CVE patch mapper singleton initialized")

    return _cve_patch_mapper_instance
