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
except ModuleNotFoundError:
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest
    from app.agentic.eol.models.cve_models import (
        VMScanTarget, CVEMatch, ScanResult, CVEScanRequest,
        UnifiedCVE
    )
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


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

    async def query(self, query: str) -> List[Dict[str, Any]]:
        """Execute Cosmos SQL query."""
        try:
            items = await asyncio.to_thread(
                lambda: list(self.container.query_items(
                    query=query,
                    enable_cross_partition_query=True
                ))
            )
            return items
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

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
        logger.info("CVEScanner initialized")

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

    async def list_recent_scans(self, limit: int = 10) -> List[ScanResult]:
        """List recent scans ordered by start time.

        Args:
            limit: Maximum number of scans to return

        Returns:
            List of ScanResult models
        """
        query = f"SELECT TOP {limit} * FROM c ORDER BY c.started_at DESC"
        items = await self.scan_repository.query(query)
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

            # Discover VMs
            logger.info(f"Scan {scan_id}: Discovering VMs...")
            vms = await self._discover_vms(
                request.subscription_ids,
                request.resource_groups,
                request.include_arc
            )

            scan_result.total_vms = len(vms)
            await self.scan_repository.save(scan_result)
            logger.info(f"Scan {scan_id}: Found {len(vms)} VMs")

            # Match CVEs to VMs
            all_matches = []
            for i, vm in enumerate(vms):
                try:
                    matches = await self._match_cves_to_vm(vm, request.cve_filters)
                    all_matches.extend(matches)

                    # Update progress every 10 VMs
                    if (i + 1) % 10 == 0 or (i + 1) == len(vms):
                        scan_result.scanned_vms = i + 1
                        scan_result.total_matches = len(all_matches)
                        scan_result.matches = all_matches[:1000]  # Limit to avoid doc size
                        await self.scan_repository.save(scan_result)
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
            await self.scan_repository.save(scan_result)

            logger.info(f"Scan {scan_id}: Complete. {len(all_matches)} CVE matches found")

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
            except Exception as save_error:
                logger.error(f"Failed to save error state: {save_error}")

        finally:
            # Remove from active scans
            if scan_id in self._active_scans:
                del self._active_scans[scan_id]

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
        else:
            # Arc VM
            os_name = properties.get("osName") or None
            os_version = properties.get("osVersion") or None
            os_type = properties.get("osType", "Unknown")

        # Extract packages (best-effort)
        installed_packages = await self._extract_packages(vm_data)

        return VMScanTarget(
            vm_id=vm_data["id"],
            name=vm_data["name"],
            resource_group=vm_data["resourceGroup"],
            subscription_id=vm_data["subscriptionId"],
            os_type=os_type,
            os_name=os_name,
            os_version=os_version,
            installed_packages=installed_packages,
            tags=vm_data.get("tags", {}),
            location=vm_data["location"],
            vm_type=vm_type
        )

    async def _extract_packages(self, vm_data: Dict[str, Any]) -> List[str]:
        """Extract installed packages from VM.

        Best-effort extraction from VM extensions or Arc policies.
        Falls back to empty list if unavailable.

        Args:
            vm_data: Raw VM data from Resource Graph

        Returns:
            List of package names/versions
        """
        # TODO: Implement package extraction from:
        # - Log Analytics ConfigurationData table (OMS agent)
        # - Arc Guest Configuration extension
        # - Azure Monitor metrics
        # For now, return empty list (OS-only CVE matching)
        return []

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
            # Build search filters
            filters = {}
            if cve_filters:
                filters.update(cve_filters)

            # Search for CVEs with OS/product matching
            # For efficiency, filter by vendor or product if we know OS
            if vm.os_name:
                # Try to map OS name to vendor
                vendor_map = {
                    "Ubuntu": "ubuntu",
                    "WindowsServer": "microsoft",
                    "RedHat": "redhat",
                    "CentOS": "centos",
                    "Debian": "debian"
                }
                for os_name_part, vendor in vendor_map.items():
                    if os_name_part.lower() in (vm.os_name or "").lower():
                        filters["vendor"] = vendor
                        break

            # Search CVEs (limit to reduce processing time)
            cves = await self.cve_service.search_cves(
                filters=filters,
                limit=500,  # Process top 500 CVEs
                offset=0
            )

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
            # Match OS name
            if vm.os_name and product.product.lower() in vm.os_name.lower():
                # Check version if available
                if vm.os_version:
                    # Simple version matching (exact or prefix)
                    if vm.os_version in product.version or product.version in vm.os_version:
                        return True
                else:
                    # No version info, assume affected if OS name matches
                    return True

        # Check package-level match
        for package in vm.installed_packages:
            for product in cve.affected_products:
                if package.lower() in product.product.lower():
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
            if vm.os_name and product.product.lower() in vm.os_name.lower():
                version_part = f" {vm.os_version}" if vm.os_version else ""
                return f"OS {vm.os_name}{version_part} affected"

        for package in vm.installed_packages:
            for product in cve.affected_products:
                if package.lower() in product.product.lower():
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
