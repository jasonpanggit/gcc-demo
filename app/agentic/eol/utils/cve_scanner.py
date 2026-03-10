"""CVE Scanner Engine

Discovers VMs, extracts OS/package data, and matches CVEs to vulnerable systems.

Key capabilities:
- Discover Azure and Arc VMs via Resource Graph
- Extract OS version and installed packages
- Match CVEs to VMs using applicability rules
- Calculate exposure scores (vulnerable VM count per CVE)
- Async scan execution with progress tracking
- Scan result persistence to Cosmos DB
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

try:
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest
    from models.cve_models import (
        VMScanTarget, CVEMatch, ScanResult, CVEScanRequest,
        UnifiedCVE
    )
    from utils.cve_service import CVEService
    from utils.logging_config import get_logger
    from utils.normalization import normalize_os_name_version
except ModuleNotFoundError:
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest
    from app.agentic.eol.models.cve_models import (
        VMScanTarget, CVEMatch, ScanResult, CVEScanRequest,
        UnifiedCVE
    )
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.normalization import normalize_os_name_version

logger = get_logger(__name__)

SCAN_CVE_PAGE_SIZE = 1000
SCAN_CVE_MAX_RESULTS = 10000


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""

    normalized = value.lower().strip()
    normalized = normalized.replace("_", " ").replace("-", " ")
    normalized = normalized.replace("microsoft ", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_release_year(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    match = re.search(r"(20\d{2}|19\d{2})", value)
    return match.group(1) if match else None


class CVEScanRepository:
    """Repository for CVE scan result persistence."""

    def __init__(self, cosmos_client, database_name: str, container_name: str):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self.container = None

    async def initialize(self):
        """Initialize Cosmos container reference."""
        try:
            database = self.cosmos_client.get_database_client(self.database_name)
            self.container = database.get_container_client(self.container_name)
            logger.info(f"CVEScanRepository initialized: {self.container_name}")
        except Exception as e:
            logger.error(f"Failed to initialize CVEScanRepository: {e}")
            raise

    async def save(self, scan_result: ScanResult):
        """Save scan result to Cosmos."""
        try:
            item = scan_result.dict()
            item["id"] = scan_result.scan_id
            await asyncio.to_thread(
                self.container.upsert_item,
                body=item
            )
            logger.info(f"Saved scan result: {scan_result.scan_id}")
        except Exception as e:
            logger.error(f"Failed to save scan result {scan_result.scan_id}: {e}")
            raise

    async def get(self, scan_id: str) -> Optional[ScanResult]:
        """Get scan result by ID."""
        try:
            item = await asyncio.to_thread(
                self.container.read_item,
                item=scan_id,
                partition_key=scan_id
            )
            return ScanResult(**item)
        except Exception as e:
            logger.debug(f"Scan {scan_id} not found: {e}")
            return None

    async def query(self, query: str, parameters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Execute Cosmos SQL query."""
        try:
            items = await asyncio.to_thread(
                lambda: list(self.container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True
                ))
            )
            return items
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    async def get_status_summary(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """Get a lightweight status projection for a scan using a point read."""
        try:
            item = await asyncio.to_thread(
                self.container.read_item,
                item=scan_id,
                partition_key=scan_id,
            )
        except Exception as e:
            logger.debug(f"Scan status summary for {scan_id} not found: {e}")
            return None

        return {
            "scan_id": item.get("scan_id", scan_id),
            "started_at": item.get("started_at"),
            "completed_at": item.get("completed_at"),
            "status": item.get("status", "pending"),
            "total_vms": int(item.get("total_vms", 0) or 0),
            "scanned_vms": int(item.get("scanned_vms", 0) or 0),
            "total_matches": int(item.get("total_matches", 0) or 0),
            "error": item.get("error"),
        }

    async def list_status_summaries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent scans using a lightweight status projection."""
        query = f"""
        SELECT TOP {limit} VALUE {{
            "scan_id": c.scan_id,
            "started_at": c.started_at,
            "completed_at": c.completed_at,
            "status": c.status,
            "total_vms": c.total_vms,
            "scanned_vms": c.scanned_vms,
            "total_matches": c.total_matches,
            "error": c.error
        }}
        FROM c
        ORDER BY c.started_at DESC
        """
        return await self.query(query)

    async def delete(self, scan_id: str) -> bool:
        """Delete scan result."""
        try:
            await asyncio.to_thread(
                self.container.delete_item,
                item=scan_id,
                partition_key=scan_id
            )
            logger.info(f"Deleted scan result: {scan_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete scan {scan_id}: {e}")
            return False


class CVEScanner:
    """CVE scanning engine for VM inventory vulnerability assessment.

    Discovers VMs from Azure Resource Graph, extracts OS and package information,
    matches CVEs to affected systems, and calculates exposure scores.
    """

    def __init__(
        self,
        cve_service: CVEService,
        resource_graph_client: ResourceGraphClient,
        scan_repository: CVEScanRepository,
        subscription_id: str,
        max_vms: int = 1000,
        scan_timeout_minutes: int = 30
    ):
        self.cve_service = cve_service
        self.resource_graph_client = resource_graph_client
        self.scan_repository = scan_repository
        self.subscription_id = subscription_id
        self.max_vms = max_vms
        self.scan_timeout_minutes = scan_timeout_minutes
        self._active_scans: Dict[str, asyncio.Task] = {}
        self._scan_status_cache: Dict[str, Dict[str, Any]] = {}
        self.linux_advisory_sync = None   # LinuxAdvisorySyncService, injected in main.py
        self.patch_gap_compute_service = None  # PatchGapComputeService, injected in main.py
        self.on_scan_complete_hooks: List[Any] = []  # extensible hook registry
        logger.info("CVEScanner initialized")

    def _build_status_summary(self, scan_result: ScanResult) -> Dict[str, Any]:
        return {
            "scan_id": scan_result.scan_id,
            "started_at": scan_result.started_at,
            "completed_at": scan_result.completed_at,
            "status": scan_result.status,
            "total_vms": int(scan_result.total_vms or 0),
            "scanned_vms": int(scan_result.scanned_vms or 0),
            "total_matches": int(scan_result.total_matches or 0),
            "error": scan_result.error,
        }

    def _cache_status_summary(self, scan_result: ScanResult) -> Dict[str, Any]:
        summary = self._build_status_summary(scan_result)
        self._scan_status_cache[scan_result.scan_id] = summary
        return summary

    def _get_progress_update_interval(self, total_vms: int) -> int:
        """Choose a progress update cadence that stays responsive for small scans."""
        if total_vms <= 10:
            return 1
        if total_vms <= 50:
            return 5
        return 10

    async def start_scan(self, request: CVEScanRequest) -> str:
        """Start async CVE scan and return scan_id immediately.

        Args:
            request: Scan configuration

        Returns:
            scan_id for status polling
        """
        scan_id = str(uuid.uuid4())
        logger.info(f"Starting CVE scan: {scan_id}")

        # Create initial scan result
        scan_result = ScanResult(
            scan_id=scan_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="pending",
            total_vms=0,
            scanned_vms=0,
            total_matches=0
        )
        await self.scan_repository.save(scan_result)
        self._cache_status_summary(scan_result)

        # Start background scan task
        task = asyncio.create_task(self._execute_scan(scan_id, request))
        self._active_scans[scan_id] = task

        return scan_id

    async def get_scan_status(self, scan_id: str) -> Optional[ScanResult]:
        """Get current scan status.

        Args:
            scan_id: Scan identifier

        Returns:
            ScanResult or None if not found
        """
        return await self.scan_repository.get(scan_id)

    async def get_scan_status_summary(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """Get a lightweight scan status summary for polling endpoints."""
        cached = self._scan_status_cache.get(scan_id)
        if cached is not None:
            return dict(cached)
        return await self.scan_repository.get_status_summary(scan_id)

    async def list_recent_scans(self, limit: int = 10) -> List[ScanResult]:
        """List recent scans ordered by start time.

        Args:
            limit: Maximum number of scans to return

        Returns:
            List of ScanResult models
        """
        items = await self.scan_repository.list_status_summaries(limit=limit)
        return [ScanResult(**item) for item in items]

    async def delete_scan(self, scan_id: str) -> bool:
        """Delete a scan result.

        Args:
            scan_id: Scan identifier

        Returns:
            True if deleted, False if not found
        """
        return await self.scan_repository.delete(scan_id)

    async def test_connectivity(self) -> bool:
        """Test Resource Graph connectivity.

        Returns:
            True if accessible, False otherwise
        """
        try:
            query = "Resources | take 1"
            subscriptions = [self.subscription_id]
            query_request = QueryRequest(
                subscriptions=subscriptions,
                query=query
            )
            await asyncio.to_thread(
                self.resource_graph_client.resources,
                query_request
            )
            return True
        except Exception as e:
            logger.error(f"Resource Graph connectivity test failed: {e}")
            return False

    async def _execute_scan(self, scan_id: str, request: CVEScanRequest):
        """Execute CVE scan in background.

        Updates scan status in Cosmos as it progresses.
        """
        try:
            # Update status to running
            scan_result = await self.scan_repository.get(scan_id)
            if not scan_result:
                logger.error(f"Scan {scan_id} not found in repository")
                return

            scan_result.status = "running"
            await self.scan_repository.save(scan_result)
            self._cache_status_summary(scan_result)

            # Discover VMs
            logger.info(f"Scan {scan_id}: Discovering VMs...")
            vms = await self._discover_vms(
                request.subscription_ids,
                request.resource_groups,
                request.include_arc
            )

            scan_result.total_vms = len(vms)
            await self.scan_repository.save(scan_result)
            self._cache_status_summary(scan_result)
            logger.info(f"Scan {scan_id}: Found {len(vms)} VMs")

            # Match CVEs to VMs
            all_matches = []
            vm_match_summaries: Dict[str, Dict[str, Any]] = {}
            progress_update_interval = self._get_progress_update_interval(len(vms))
            for i, vm in enumerate(vms):
                try:
                    matches = await self._match_cves_to_vm(vm, request.cve_filters)
                    all_matches.extend(matches)
                    vm_match_summaries[vm.vm_id.lower()] = self._build_vm_match_summary(vm, matches)

                    # Per-VM OS family + package enrichment
                    os_family = self._get_os_family(vm.os_name)
                    scan_result.vm_os_family[vm.vm_id] = os_family

                    if vm.os_type == "Windows":
                        pass  # KB extraction handled by cve_patch_mapper / kb_cve_edge_repo
                    elif vm.os_type == "Linux":
                        packages = await self._extract_packages(vm.vm_id, vm.subscription_id, os_family)
                        scan_result.vm_installed_packages[vm.vm_id] = packages

                    # Keep small scans responsive while limiting write frequency for larger scans.
                    if (i + 1) % progress_update_interval == 0 or (i + 1) == len(vms):
                        scan_result.scanned_vms = i + 1
                        scan_result.total_matches = len(all_matches)
                        scan_result.matches = all_matches[:1000]  # Limit to avoid doc size
                        scan_result.vm_match_summaries = vm_match_summaries
                        await self.scan_repository.save(scan_result)
                        self._cache_status_summary(scan_result)
                        logger.info(f"Scan {scan_id}: Progress {i + 1}/{len(vms)}, {len(all_matches)} matches")

                except Exception as e:
                    logger.error(f"Scan {scan_id}: Error scanning VM {vm.name}: {e}")
                    continue

            # Mark scan complete
            scan_result.status = "completed"
            scan_result.completed_at = datetime.now(timezone.utc).isoformat()
            scan_result.scanned_vms = len(vms)
            scan_result.total_matches = len(all_matches)
            scan_result.matches = all_matches[:1000]  # Limit stored matches
            scan_result.vm_match_summaries = vm_match_summaries
            await self.scan_repository.save(scan_result)
            self._cache_status_summary(scan_result)

            logger.info(f"Scan {scan_id}: Complete. {len(all_matches)} CVE matches found")

            # Fire scan completion hooks
            for hook in self.on_scan_complete_hooks:
                asyncio.create_task(self._supervised_task(hook(scan_result)))

            # Linux advisory sync hook
            if self.linux_advisory_sync is not None:
                asyncio.create_task(
                    self._supervised_task(
                        self.linux_advisory_sync.sync_for_scan_result(scan_result)
                    )
                )

            # Patch gap compute hook
            if self.patch_gap_compute_service is not None:
                asyncio.create_task(
                    self._supervised_task(
                        self.patch_gap_compute_service.compute_and_store(scan_result)
                    )
                )

        except Exception as e:
            logger.error(f"Scan {scan_id} failed: {e}")
            # Mark scan as failed
            try:
                scan_result = await self.scan_repository.get(scan_id)
                if scan_result:
                    scan_result.status = "failed"
                    scan_result.error = str(e)
                    scan_result.completed_at = datetime.now(timezone.utc).isoformat()
                    await self.scan_repository.save(scan_result)
                    self._cache_status_summary(scan_result)
            except Exception as save_error:
                logger.error(f"Failed to save error state: {save_error}")

        finally:
            # Remove from active scans
            if scan_id in self._active_scans:
                del self._active_scans[scan_id]

    async def _supervised_task(self, coro) -> None:
        """Wrapper for fire-and-forget tasks that logs exceptions instead of silently swallowing."""
        try:
            await coro
        except Exception as e:
            logger.error("Supervised background task failed: %s", e, exc_info=True)

    async def _discover_vms(
        self,
        subscription_ids: Optional[List[str]],
        resource_groups: Optional[List[str]],
        include_arc: bool
    ) -> List[VMScanTarget]:
        """Discover VMs from Azure Resource Graph.

        Args:
            subscription_ids: Subscriptions to scan (None = default subscription)
            resource_groups: Resource groups to filter (None = all)
            include_arc: Include Arc-enabled VMs

        Returns:
            List of VMScanTarget models
        """
        # Build KQL query
        type_filter = "(type =~ 'microsoft.compute/virtualmachines'"
        if include_arc:
            type_filter += " or type =~ 'microsoft.hybridcompute/machines'"
        type_filter += ")"

        query = f"""
        Resources
        | where {type_filter}
        """

        if resource_groups:
            rg_filter = " or ".join([f"resourceGroup =~ '{rg}'" for rg in resource_groups])
            query += f" | where {rg_filter}"

        query += """
        | project id, name, resourceGroup, subscriptionId, location, properties, tags, type
        | limit 1000
        """

        # Execute query
        try:
            subscriptions = subscription_ids or [self.subscription_id]
            query_request = QueryRequest(
                subscriptions=subscriptions,
                query=query
            )

            response = await asyncio.to_thread(
                self.resource_graph_client.resources,
                query_request
            )

            # Parse VM data
            vms = []
            for vm_data in response.data:
                try:
                    vm = await self._extract_vm_details(vm_data)
                    vms.append(vm)
                except Exception as e:
                    logger.error(f"Failed to parse VM {vm_data.get('name', 'unknown')}: {e}")
                    continue

            logger.info(f"Discovered {len(vms)} VMs from Resource Graph")
            return vms[:self.max_vms]  # Enforce limit

        except Exception as e:
            logger.error(f"VM discovery failed: {e}")
            return []

    async def get_vm_targets(
        self,
        subscription_ids: Optional[List[str]] = None,
        resource_groups: Optional[List[str]] = None,
        include_arc: bool = True,
    ) -> List[VMScanTarget]:
        """Public wrapper for VM discovery used by downstream services."""
        return await self._discover_vms(subscription_ids, resource_groups, include_arc)

    async def get_vm_targets_by_ids(self, vm_ids: List[str]) -> Dict[str, VMScanTarget]:
        """Return current VM inventory metadata for a set of resource IDs."""
        if not vm_ids:
            return {}

        normalized_vm_ids = []
        seen_ids = set()
        for vm_id in vm_ids:
            if not vm_id:
                continue
            vm_id_lower = vm_id.lower()
            if vm_id_lower in seen_ids:
                continue
            seen_ids.add(vm_id_lower)
            normalized_vm_ids.append(vm_id)

        if not normalized_vm_ids:
            return {}

        escaped_ids = ", ".join("'{}'".format(vm_id.replace("'", "''")) for vm_id in normalized_vm_ids)
        query = f"""
        Resources
        | where id in~ ({escaped_ids})
        | project id, name, resourceGroup, subscriptionId, location, properties, tags, type
        """

        subscriptions = sorted({
            parts[2]
            for vm_id in normalized_vm_ids
            for parts in [vm_id.split("/")]
            if len(parts) > 2 and parts[1].lower() == "subscriptions"
        }) or [self.subscription_id]

        try:
            query_request = QueryRequest(
                subscriptions=subscriptions,
                query=query,
            )
            response = await asyncio.to_thread(
                self.resource_graph_client.resources,
                query_request,
            )

            inventory: Dict[str, VMScanTarget] = {}
            for vm_data in response.data:
                try:
                    vm = await self._extract_vm_details(vm_data)
                    inventory[vm.vm_id.lower()] = vm
                except Exception as e:
                    logger.warning(f"Failed to enrich VM inventory for {vm_data.get('id', 'unknown')}: {e}")

            return inventory

        except Exception as e:
            logger.error(f"VM lookup by ID failed: {e}")
            return {}

    def is_vm_affected_by_cve(self, vm: VMScanTarget, cve: UnifiedCVE) -> bool:
        """Public wrapper for normalized CVE-to-VM matching."""
        return self._is_vm_affected(vm, cve)

    async def _extract_vm_details(self, vm_data: Dict[str, Any]) -> VMScanTarget:
        """Extract VM details from Resource Graph result.

        Args:
            vm_data: Raw VM data from Resource Graph

        Returns:
            VMScanTarget model
        """
        vm_type = "arc" if "hybridcompute" in vm_data.get("type", "").lower() else "azure"
        properties = vm_data.get("properties", {})

        # Extract OS information
        if vm_type == "azure":
            # Azure VM
            storage_profile = properties.get("storageProfile", {})
            os_disk = storage_profile.get("osDisk", {})
            os_type = os_disk.get("osType", "Unknown")

            # Try to get OS name from image reference
            image_ref = storage_profile.get("imageReference", {})
            os_name = image_ref.get("offer") or None
            os_version = image_ref.get("sku") or None

            if os_name and os_name.lower() == "windowsserver":
                release_year = _extract_release_year(os_version)
                os_name = "Windows Server"
                os_version = release_year or os_version
        else:
            # Arc VM payloads often expose a generic osName (for example "windows")
            # but a specific osSku (for example "Windows Server 2025 Standard").
            os_name = properties.get("osSku") or properties.get("osName") or None
            os_version = properties.get("osVersion") or None
            os_type = properties.get("osType", "Unknown")

        # Extract packages (best-effort)
        raw_os_name = os_name if vm_type == "azure" else properties.get("osSku") or properties.get("osName") or os_name
        os_family = self._get_os_family(raw_os_name)
        installed_packages = await self._extract_packages(vm_data["id"], vm_data["subscriptionId"], os_family)

        return VMScanTarget(
            vm_id=vm_data["id"],
            name=vm_data["name"],
            resource_group=vm_data["resourceGroup"],
            subscription_id=vm_data["subscriptionId"],
            os_type=os_type,
            os_name=os_name,
            os_version=os_version,
            installed_packages=installed_packages,
            tags=vm_data.get("tags") or {},
            location=vm_data["location"],
            vm_type=vm_type
        )

    def _get_vm_os_identity(self, vm: VMScanTarget) -> tuple[str, Optional[str]]:
        """Return normalized OS family and version for VM matching."""
        raw_name = vm.os_name or vm.os_type or ""
        raw_version = vm.os_version

        if raw_name.lower() == "windowsserver":
            release_year = _extract_release_year(raw_version)
            raw_name = "Windows Server"
            raw_version = release_year or raw_version

        normalized_name, normalized_version = normalize_os_name_version(raw_name, raw_version)
        normalized_name = _normalize_text(normalized_name)
        normalized_version = _extract_release_year(normalized_version) or normalized_version
        return normalized_name, normalized_version

    def _get_product_identity(self, product_name: Optional[str], product_version: Optional[str]) -> tuple[str, Optional[str]]:
        """Return normalized product family and version for CVE product matching."""
        normalized_product_name = _normalize_text(product_name)
        normalized_product_version = _normalize_text(product_version)

        normalized_name, normalized_version = normalize_os_name_version(
            normalized_product_name,
            normalized_product_version or None
        )
        normalized_name = _normalize_text(normalized_name)

        release_year = (
            _extract_release_year(product_name)
            or _extract_release_year(product_version)
            or _extract_release_year(normalized_version)
        )

        if normalized_name == "windowsserver":
            normalized_name = "windows server"

        return normalized_name, release_year or normalized_version or None

    def _versions_match(self, vm_version: Optional[str], product_version: Optional[str]) -> bool:
        if not vm_version or not product_version:
            return True

        vm_normalized = _normalize_text(vm_version)
        product_normalized = _normalize_text(product_version)

        vm_year = _extract_release_year(vm_normalized)
        product_year = _extract_release_year(product_normalized)
        if vm_year and product_year:
            return vm_year == product_year

        return (
            vm_normalized == product_normalized
            or vm_normalized in product_normalized
            or product_normalized in vm_normalized
        )

    def _product_matches_vm(self, vm: VMScanTarget, product_name: Optional[str], product_version: Optional[str]) -> bool:
        vm_name, vm_version = self._get_vm_os_identity(vm)
        product_family, normalized_product_version = self._get_product_identity(product_name, product_version)

        if not vm_name or not product_family:
            return False

        same_family = (
            vm_name == product_family
            or vm_name in product_family
            or product_family in vm_name
        )

        if not same_family:
            return False

        return self._versions_match(vm_version, normalized_product_version)

    def _build_cve_search_filters(self, vm: VMScanTarget, cve_filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build search filters that can hit both cache and live keyword search paths."""
        filters: Dict[str, Any] = {}
        if cve_filters:
            filters.update(cve_filters)

        normalized_name, normalized_version = self._get_vm_os_identity(vm)
        if not normalized_name:
            return filters

        vendor_map = {
            "ubuntu": "ubuntu",
            "windows server": "microsoft",
            "windows": "microsoft",
            "rhel": "redhat",
            "centos": "centos",
            "debian": "debian",
        }

        vendor = vendor_map.get(normalized_name)
        if vendor:
            filters["vendor"] = vendor

        keyword_parts = [normalized_name]
        if normalized_version:
            keyword_parts.append(normalized_version)
        filters["keyword"] = " ".join(keyword_parts)

        return filters

    def _get_os_family(self, os_name: Optional[str]) -> str:
        """Normalize os_name to os_family string."""
        if not os_name:
            return "linux"
        name = os_name.lower()
        if "ubuntu" in name:
            return "ubuntu"
        if "red hat" in name or "rhel" in name:
            return "rhel"
        if "centos" in name:
            return "centos"
        if "debian" in name:
            return "debian"
        if "windows" in name:
            return "windows"
        return "linux"

    async def _extract_packages(self, vm_id: str, subscription_id: str, os_family: str) -> List[str]:
        """Extract installed Linux package names from ARG patchassessmentresources.

        Uses same ARG table as Windows KB extraction:
        - filter: osType=Linux, kbId=null/empty, patchName non-empty
        - returns: list of package names (e.g. ["openssl", "curl", "libc6"])
        """
        vm_id_lower = vm_id.lower()
        # Azure VM type
        azure_query = f"""
            patchassessmentresources
            | where type =~ 'microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches'
            | where tolower(id) startswith tolower('{vm_id_lower}')
            | where properties.osType =~ 'Linux'
            | where isnull(properties.kbId) or tostring(properties.kbId) == ''
            | where tostring(properties.patchName) != ''
            | project patchName = tostring(properties.patchName)
            | distinct patchName
        """
        # Arc VM type
        arc_query = f"""
            patchassessmentresources
            | where type =~ 'microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches'
            | where tolower(id) startswith tolower('{vm_id_lower}')
            | where properties.osType =~ 'Linux'
            | where isnull(properties.kbId) or tostring(properties.kbId) == ''
            | where tostring(properties.patchName) != ''
            | project patchName = tostring(properties.patchName)
            | distinct patchName
        """

        packages: set = set()
        for query in [azure_query, arc_query]:
            try:
                query_request = QueryRequest(
                    subscriptions=[subscription_id],
                    query=query,
                )
                response = await asyncio.to_thread(
                    self.resource_graph_client.resources,
                    query_request,
                )
                for r in (response.data or []):
                    pkg = (r.get("patchName") or "").strip()
                    if pkg:
                        packages.add(pkg)
            except Exception as e:
                logger.debug("ARG package query failed for %s: %s", vm_id, e)

        return sorted(packages)

    async def _match_cves_to_vm(
        self,
        vm: VMScanTarget,
        cve_filters: Optional[Dict[str, Any]] = None
    ) -> List[CVEMatch]:
        """Match CVEs to a VM based on OS and packages.

        Args:
            vm: VM to scan
            cve_filters: Optional filters to limit CVE search

        Returns:
            List of CVE matches
        """
        matches = []

        try:
            filters = self._build_cve_search_filters(vm, cve_filters)

            cves: List[UnifiedCVE] = []
            offset = 0
            while offset < SCAN_CVE_MAX_RESULTS:
                page = await self.cve_service.search_cves(
                    filters=filters,
                    limit=SCAN_CVE_PAGE_SIZE,
                    offset=offset,
                    allow_live_fallback=False,
                )
                if not page:
                    break

                cves.extend(page)
                if len(page) < SCAN_CVE_PAGE_SIZE:
                    break

                offset += len(page)

            # Match each CVE to VM
            for cve in cves:
                if self._is_vm_affected(vm, cve):
                    match = CVEMatch(
                        cve_id=cve.cve_id,
                        vm_id=vm.vm_id,
                        vm_name=vm.name,
                        match_reason=self._get_match_reason(vm, cve),
                        cvss_score=cve.cvss_v3.base_score if cve.cvss_v3 else (cve.cvss_v2.base_score if cve.cvss_v2 else None),
                        severity=cve.cvss_v3.base_severity if cve.cvss_v3 else (cve.cvss_v2.base_severity if cve.cvss_v2 else None),
                        published_date=cve.published_date.isoformat()
                    )
                    matches.append(match)

        except Exception as e:
            logger.error(f"CVE matching failed for VM {vm.name}: {e}")

        return matches

    def _build_vm_match_summary(self, vm: VMScanTarget, matches: List[CVEMatch]) -> Dict[str, Any]:
        """Build a compact per-VM summary that survives raw match truncation."""
        summary = {
            "vm_id": vm.vm_id,
            "vm_name": vm.name,
            "total_cves": len(matches),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }

        for match in matches:
            severity = str(match.severity or "UNKNOWN").upper()
            if severity == "CRITICAL":
                summary["critical"] += 1
            elif severity == "HIGH":
                summary["high"] += 1
            elif severity == "MEDIUM":
                summary["medium"] += 1
            else:
                summary["low"] += 1

        return summary

    def _is_vm_affected(self, vm: VMScanTarget, cve: UnifiedCVE) -> bool:
        """Check if VM is affected by CVE.

        Args:
            vm: VM to check
            cve: CVE to match

        Returns:
            True if VM is affected
        """
        # Check OS-level match
        for product in cve.affected_products:
            if self._product_matches_vm(vm, product.product, product.version):
                return True

        # Check package-level match
        for package in vm.installed_packages:
            for product in cve.affected_products:
                if _normalize_text(package) in _normalize_text(product.product):
                    return True

        return False

    def _get_match_reason(self, vm: VMScanTarget, cve: UnifiedCVE) -> str:
        """Generate human-readable match reason.

        Args:
            vm: Matched VM
            cve: Matched CVE

        Returns:
            Match reason string
        """
        # Find the product that matched
        for product in cve.affected_products:
            if self._product_matches_vm(vm, product.product, product.version):
                version_part = f" {vm.os_version}" if vm.os_version else ""
                return f"OS {vm.os_name}{version_part} affected"

        for package in vm.installed_packages:
            for product in cve.affected_products:
                if _normalize_text(package) in _normalize_text(product.product):
                    return f"Package {package} affected"

        return "Matched by product"

    async def _calculate_exposure_scores(self, matches: List[CVEMatch]) -> Dict[str, int]:
        """Calculate exposure score for each CVE.

        Exposure score = number of unique VMs affected by the CVE.

        Args:
            matches: All CVE matches from scan

        Returns:
            Dict mapping cve_id to vulnerable VM count
        """
        exposure = {}
        for match in matches:
            if match.cve_id not in exposure:
                exposure[match.cve_id] = set()
            exposure[match.cve_id].add(match.vm_id)

        # Convert sets to counts
        return {cve_id: len(vm_set) for cve_id, vm_set in exposure.items()}

    # ========================================================================
    # Query Helper Methods (Phase 7)
    # ========================================================================

    async def get_latest_scan_result(self) -> Optional[ScanResult]:
        """Get latest completed scan result.

        Public method to query the most recent completed scan.
        Used by CVEVMService and other components needing scan data.

        Returns:
            Latest completed ScanResult or None if no scans found
        """
        try:
            # Query latest completed scan ordered by completion time
            query = """
            SELECT * FROM c
            WHERE c.status = 'completed'
            ORDER BY c.completed_at DESC
            OFFSET 0 LIMIT 1
            """
            items = await self.scan_repository.query(query)

            if items:
                return ScanResult(**items[0])

            logger.debug("No completed scans found")
            return None

        except Exception as e:
            logger.error(f"Failed to get latest scan result: {e}")
            return None

    async def get_vm_cve_matches(self, vm_id: str) -> List[CVEMatch]:
        """Get all CVE matches for a specific VM.

        Args:
            vm_id: VM identifier

        Returns:
            List of CVEMatch models for this VM, empty list if none found
        """
        try:
            scan = await self.get_latest_scan_result()
            if not scan:
                logger.debug(f"No scan data available for VM {vm_id}")
                return []

            # Filter matches for this VM
            matches = [m for m in scan.matches if m.vm_id == vm_id]
            logger.debug(f"Found {len(matches)} CVE matches for VM {vm_id}")
            return matches

        except Exception as e:
            logger.error(f"Failed to get CVE matches for VM {vm_id}: {e}")
            return []

    async def get_cve_vm_matches(self, cve_id: str) -> List[CVEMatch]:
        """Get all VM matches for a specific CVE.

        Args:
            cve_id: CVE identifier

        Returns:
            List of CVEMatch models for this CVE, empty list if none found
        """
        try:
            cve_id = cve_id.upper()
            scan = await self.get_latest_scan_result()
            if not scan:
                logger.debug(f"No scan data available for CVE {cve_id}")
                return []

            # Filter matches for this CVE
            matches = [m for m in scan.matches if m.cve_id == cve_id]
            logger.debug(f"Found {len(matches)} VM matches for CVE {cve_id}")
            return matches

        except Exception as e:
            logger.error(f"Failed to get VM matches for CVE {cve_id}: {e}")
            return []


# Singleton pattern
_cve_scanner_instance: Optional['CVEScanner'] = None


async def get_cve_scanner() -> 'CVEScanner':
    """Get the global CVE scanner instance, initializing if needed.

    Returns:
        Initialized CVEScanner instance
    """
    global _cve_scanner_instance

    if _cve_scanner_instance is None:
        from utils.cve_scan_repository import CVEScanRepository
        repository = CVEScanRepository()
        await repository.ensure_initialized()
        _cve_scanner_instance = CVEScanner(repository=repository)
        logger.info("CVE scanner singleton initialized")

    return _cve_scanner_instance
