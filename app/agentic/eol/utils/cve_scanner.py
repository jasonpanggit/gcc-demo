"""CVE Scanner Engine - Updated 2026-03-20

Discovers VMs, extracts OS/package data, and matches CVEs to vulnerable systems.

Key capabilities:
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

import asyncpg

_ARG_MAX_RETRIES = 3
_ARG_BACKOFF_BASE = 5  # seconds; doubled each retry (5 → 10 → 20)

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
    from utils.cve_patch_enricher import CVEPatchEnricher, VMPatchEnrichment
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
    from app.agentic.eol.utils.cve_patch_enricher import CVEPatchEnricher, VMPatchEnrichment

logger = get_logger(__name__)

SCAN_CVE_PAGE_SIZE = 1000
SCAN_CVE_MAX_RESULTS = 100000  # Increased from 10k to allow full OS coverage


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

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def initialize(self):
        logger.info("CVEScanRepository initialized with PostgreSQL")

    @staticmethod
    def _coerce_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _json_or_default(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    @classmethod
    def _row_to_scan_result(cls, row: asyncpg.Record) -> ScanResult:
        data = dict(row)
        return ScanResult(
            scan_id=data["scan_id"],
            started_at=data["started_at"].isoformat() if data.get("started_at") else "",
            completed_at=data["completed_at"].isoformat() if data.get("completed_at") else None,
            status=data.get("status") or "pending",
            total_vms=int(data.get("total_vms") or 0),
            scanned_vms=int(data.get("scanned_vms") or 0),
            total_matches=int(data.get("total_matches") or 0),
            matches=[CVEMatch(**item) for item in cls._json_or_default(data.get("matches"), [])],
            vm_match_summaries=cls._json_or_default(data.get("vm_match_summaries"), {}),
            vm_installed_kbs=cls._json_or_default(data.get("vm_installed_kbs"), {}),
            vm_installed_packages=cls._json_or_default(data.get("vm_installed_packages"), {}),
            vm_os_family=cls._json_or_default(data.get("vm_os_family"), {}),
            truncated=bool(data.get("truncated") or False),
            total_matches_before_truncation=data.get("total_matches_before_truncation"),
            error=data.get("error"),
            matches_stored_separately=bool(data.get("matches_stored_separately") or False),
        )

    async def save(self, scan_result: ScanResult):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cve_scans (
                    scan_id, status, started_at, completed_at,
                    total_vms, scanned_vms, total_matches, matches,
                    vm_match_summaries, vm_installed_kbs, vm_installed_packages,
                    vm_os_family, truncated, total_matches_before_truncation,
                    matches_stored_separately, error, updated_at
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8::jsonb,
                    $9::jsonb, $10::jsonb, $11::jsonb,
                    $12::jsonb, $13, $14,
                    $15, $16, NOW()
                )
                ON CONFLICT (scan_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    total_vms = EXCLUDED.total_vms,
                    scanned_vms = EXCLUDED.scanned_vms,
                    total_matches = EXCLUDED.total_matches,
                    matches = EXCLUDED.matches,
                    vm_match_summaries = EXCLUDED.vm_match_summaries,
                    vm_installed_kbs = EXCLUDED.vm_installed_kbs,
                    vm_installed_packages = EXCLUDED.vm_installed_packages,
                    vm_os_family = EXCLUDED.vm_os_family,
                    truncated = EXCLUDED.truncated,
                    total_matches_before_truncation = EXCLUDED.total_matches_before_truncation,
                    matches_stored_separately = EXCLUDED.matches_stored_separately,
                    error = EXCLUDED.error,
                    updated_at = NOW()
                """,
                scan_result.scan_id,
                scan_result.status,
                self._coerce_timestamp(scan_result.started_at),
                self._coerce_timestamp(scan_result.completed_at),
                scan_result.total_vms,
                scan_result.scanned_vms,
                scan_result.total_matches,
                json.dumps([match.model_dump(mode="json") for match in scan_result.matches]),
                scan_result.vm_match_summaries,  # asyncpg handles JSONB conversion
                scan_result.vm_installed_kbs,    # asyncpg handles JSONB conversion
                scan_result.vm_installed_packages,  # asyncpg handles JSONB conversion
                scan_result.vm_os_family,  # asyncpg handles JSONB conversion
                scan_result.truncated,
                scan_result.total_matches_before_truncation,
                scan_result.matches_stored_separately,
                scan_result.error,
            )
        logger.info(f"Saved scan result: {scan_result.scan_id}")

    async def get(self, scan_id: str) -> Optional[ScanResult]:
        """Get scan result by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT scan_id, status, started_at, completed_at,
                       total_vms, scanned_vms, total_matches, matches,
                       vm_match_summaries, vm_installed_kbs, vm_installed_packages,
                       vm_os_family, truncated, total_matches_before_truncation,
                       error, matches_stored_separately
                FROM cve_scans
                WHERE scan_id = $1
                """,
                scan_id,
            )
        return self._row_to_scan_result(row) if row else None

    async def query(self, query: str, parameters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        args = [parameter.get("value") for parameter in (parameters or [])]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]

    async def get_status_summary(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """Get a lightweight status projection for a scan using a point read."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT scan_id, started_at, completed_at, status,
                       total_vms, scanned_vms, total_matches, error
                FROM cve_scans
                WHERE scan_id = $1
                """,
                scan_id,
            )
        if row is None:
            return None

        return {
            "scan_id": row["scan_id"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "status": row["status"],
            "total_vms": int(row["total_vms"] or 0),
            "scanned_vms": int(row["scanned_vms"] or 0),
            "total_matches": int(row["total_matches"] or 0),
            "error": row["error"],
        }

    async def list_status_summaries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent scans using a lightweight status projection."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT scan_id, status, started_at, completed_at,
                       total_vms, scanned_vms, total_matches, matches,
                       vm_match_summaries, vm_installed_kbs, vm_installed_packages,
                       vm_os_family, truncated, total_matches_before_truncation,
                       error, matches_stored_separately
                FROM cve_scans
                ORDER BY started_at DESC NULLS LAST
                LIMIT $1
                """,
                limit,
            )
        return [self._row_to_scan_result(row).model_dump(mode="json") for row in rows]

    async def delete(self, scan_id: str) -> bool:
        """Delete scan result."""
        async with self.pool.acquire() as conn:
            deleted = await conn.execute(
                "DELETE FROM cve_scans WHERE scan_id = $1",
                scan_id,
            )
        logger.info(f"Deleted scan result: {scan_id}")
        return deleted.endswith("1")


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
        vm_match_repository=None,
        subscription_id: str = "",
        max_vms: int = 1000,
        scan_timeout_minutes: int = 30,
        vm_scan_concurrency: int = 6,
    ):
        self.cve_service = cve_service
        self.resource_graph_client = resource_graph_client
        self.scan_repository = scan_repository
        self.vm_match_repository = vm_match_repository
        self.subscription_id = subscription_id
        self.max_vms = max_vms
        self.scan_timeout_minutes = scan_timeout_minutes
        self.vm_scan_concurrency = max(1, vm_scan_concurrency)
        self._vm_scan_semaphore = asyncio.Semaphore(self.vm_scan_concurrency)
        self._active_scans: Dict[str, asyncio.Task] = {}
        self._scan_status_cache: Dict[str, Dict[str, Any]] = {}
        self.linux_advisory_sync = None   # LinuxAdvisorySyncService, injected in main.py
        self.on_scan_complete_hooks: List[Any] = []  # extensible hook registry
        # Patch enricher — injected at startup; None disables patch enrichment without error
        self.patch_enricher: Optional[CVEPatchEnricher] = None
        logger.info("CVEScanner initialized")

    async def _arg_query_with_retry(self, query_request: "QueryRequest") -> Any:
        """Execute a Resource Graph query with exponential-backoff retry on throttling (429/RateLimiting)."""
        from azure.core.exceptions import HttpResponseError

        last_exc: Optional[Exception] = None
        for attempt in range(_ARG_MAX_RETRIES):
            try:
                return await asyncio.to_thread(
                    self.resource_graph_client.resources,
                    query_request,
                )
            except HttpResponseError as exc:
                last_exc = exc
                if getattr(getattr(exc, "error", None), "code", None) == "RateLimiting":
                    retry_after = _ARG_BACKOFF_BASE * (2 ** attempt)
                    try:
                        header_val = exc.response.headers.get("Retry-After") if exc.response else None
                        if header_val:
                            retry_after = max(retry_after, int(header_val))
                    except Exception:
                        pass
                    logger.warning(
                        "ARG throttled (attempt %d/%d) — sleeping %ds before retry",
                        attempt + 1, _ARG_MAX_RETRIES, retry_after,
                    )
                    await asyncio.sleep(retry_after)
                else:
                    raise

        raise last_exc  # type: ignore[misc]

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
            await self._arg_query_with_retry(query_request)
            return True
        except Exception as e:
            logger.error(f"Resource Graph connectivity test failed: {e}")
            return False

    async def _execute_scan(self, scan_id: str, request: CVEScanRequest):
        """Execute CVE scan in background.

        Updates scan status in PostgreSQL as it progresses.
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
                request.include_arc,
                request.vm_ids,
            )

            scan_result.total_vms = len(vms)
            await self.scan_repository.save(scan_result)
            self._cache_status_summary(scan_result)
            logger.info(f"Scan {scan_id}: Found {len(vms)} VMs")

            # Prefetch patch data for all subscriptions (one bulk ARG call per subscription)
            # Result is an in-memory dict: machine_name.lower() → patch_data
            patch_map: Dict[str, Any] = {}
            if self.patch_enricher and vms:
                try:
                    effective_subs = request.subscription_ids or [self.subscription_id]
                    patch_map = await self.patch_enricher.prefetch_patch_data(effective_subs, vms)
                    logger.info("Scan %s: patch data prefetched for %d VMs", scan_id, len(patch_map))
                except Exception as prefetch_err:
                    logger.warning("Scan %s: patch prefetch failed, continuing without: %s", scan_id, prefetch_err)

            # Match CVEs to VMs
            all_matches = []
            vm_match_summaries: Dict[str, Dict[str, Any]] = {}
            progress_update_interval = self._get_progress_update_interval(len(vms))
            tasks = [
                asyncio.create_task(
                    self._scan_single_vm(vm, request.cve_filters, patch_map)
                )
                for vm in vms
            ]
            completed_vms = 0
            for task in asyncio.as_completed(tasks):
                try:
                    vm, matches, os_family, enrichment = await task
                    all_matches.extend(matches)
                    vm_match_summaries[vm.vm_id.lower()] = self._build_vm_match_summary(vm, matches, enrichment)
                    scan_result.vm_os_family[vm.vm_id] = os_family

                    if vm.os_type == "Linux":
                        scan_result.vm_installed_packages[vm.vm_id] = list(vm.installed_packages)

                    # Save per-VM match document (new storage format)
                    if self.vm_match_repository is not None and matches:
                        try:
                            await self.vm_match_repository.save_vm_matches(
                                scan_id=scan_id,
                                vm_id=vm.vm_id,
                                vm_name=vm.name,
                                matches=matches,
                                installed_kb_ids=enrichment.installed_kb_ids,
                                available_kb_ids=enrichment.available_kb_ids,
                                installed_cve_ids=enrichment.installed_cve_ids,
                                available_cve_ids=enrichment.available_cve_ids,
                                patch_summary=enrichment.patch_summary,
                            )
                        except Exception as save_err:
                            logger.error(f"Failed to save VM match doc for {vm.name}: {save_err}")
                            # Continue — don't fail entire scan on one VM save failure

                except Exception as e:
                    logger.error(f"Scan {scan_id}: Error scanning VM: {e}")
                finally:
                    completed_vms += 1

                # Keep small scans responsive while limiting write frequency for larger scans.
                if completed_vms % progress_update_interval == 0 or completed_vms == len(vms):
                    scan_result.scanned_vms = completed_vms
                    scan_result.total_matches = len(all_matches)
                    scan_result.matches = []
                    scan_result.matches_stored_separately = True
                    scan_result.vm_match_summaries = vm_match_summaries
                    await self.scan_repository.save(scan_result)
                    self._cache_status_summary(scan_result)
                    logger.info(f"Scan {scan_id}: Progress {completed_vms}/{len(vms)}, {len(all_matches)} matches")

            # Mark scan complete
            scan_result.status = "completed"
            scan_result.completed_at = datetime.now(timezone.utc).isoformat()
            scan_result.scanned_vms = len(vms)
            scan_result.total_matches = len(all_matches)
            scan_result.matches = []
            scan_result.matches_stored_separately = True
            scan_result.vm_match_summaries = vm_match_summaries
            await self.scan_repository.save(scan_result)
            self._cache_status_summary(scan_result)

            logger.info(f"Scan {scan_id}: Complete. {len(all_matches)} CVE matches found")

            # Fire scan completion hooks
            for hook in self.on_scan_complete_hooks:
                asyncio.create_task(self._supervised_task(hook(scan_result)))

            # Refresh materialized views after scan completion
            asyncio.create_task(self._supervised_task(self._refresh_views_after_scan()))

            # Linux advisory sync hook
            if self.linux_advisory_sync is not None:
                asyncio.create_task(
                    self._supervised_task(
                        self.linux_advisory_sync.sync_for_scan_result(scan_result)
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

    async def _refresh_views_after_scan(self) -> None:
        """Refresh materialized views after scan completion to ensure data freshness."""
        try:
            logger.info("Refreshing materialized views after scan completion...")

            # Import pg_client to get pool
            try:
                from utils.pg_client import postgres_client
            except ModuleNotFoundError:
                from app.agentic.eol.utils.pg_client import postgres_client

            if not postgres_client.is_configured():
                logger.warning("PostgreSQL not configured, skipping MV refresh")
                return

            pool = postgres_client.pool
            async with pool.acquire() as conn:
                # Refresh VM-related MVs in sequence (concurrent refresh requires unique indexes)
                await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_vm_vulnerability_posture")
                logger.info("✅ Refreshed mv_vm_vulnerability_posture")

                await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_vm_cve_detail")
                logger.info("✅ Refreshed mv_vm_cve_detail")

                await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cve_exposure")
                logger.info("✅ Refreshed mv_cve_exposure")

            logger.info("✅ All materialized views refreshed successfully")

        except Exception as e:
            logger.error(f"Failed to refresh materialized views: {e}")
            # Don't fail the scan if MV refresh fails

    async def _scan_single_vm(
        self,
        vm: VMScanTarget,
        cve_filters: Optional[Dict[str, Any]] = None,
        patch_map: Optional[Dict[str, Any]] = None,   # NEW
    ) -> tuple[VMScanTarget, List[CVEMatch], str, "VMPatchEnrichment"]:
        """Scan one VM with bounded concurrency and return computed data + patch enrichment."""
        async with self._vm_scan_semaphore:
            matches = await self._match_cves_to_vm(vm, cve_filters)
            os_family = self._get_os_family(vm.os_name)

            # Enrich with patch data if available
            enrichment = VMPatchEnrichment()
            if self.patch_enricher and patch_map is not None:
                vm_patch_data = patch_map.get((vm.name or "").lower())
                enrichment = await self.patch_enricher.enrich_vm(vm, matches, vm_patch_data)

            return vm, matches, os_family, enrichment

    async def _discover_vms(
        self,
        subscription_ids: Optional[List[str]],
        resource_groups: Optional[List[str]],
        include_arc: bool,
        vm_ids: Optional[List[str]] = None,   # NEW
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

            response = await self._arg_query_with_retry(query_request)

            # Parse VM data
            semaphore = asyncio.Semaphore(self.vm_scan_concurrency)

            async def _extract_one(vm_data: Dict[str, Any]) -> Optional[VMScanTarget]:
                async with semaphore:
                    try:
                        return await self._extract_vm_details(vm_data)
                    except Exception as e:
                        logger.error(f"Failed to parse VM {vm_data.get('name', 'unknown')}: {e}")
                        return None

            extracted_vms = await asyncio.gather(*[_extract_one(vm_data) for vm_data in response.data])
            vms = [vm for vm in extracted_vms if vm is not None]

            # Deduplicate by vm_id (case-insensitive) — a machine can appear as both
            # an Azure VM and an Arc-enabled server in ARG, which would cause double scanning.
            seen: dict[str, VMScanTarget] = {}
            for vm in vms:
                key = vm.vm_id.lower()
                if key not in seen:
                    seen[key] = vm
            vms = list(seen.values())

            logger.info(f"Discovered {len(vms)} VMs from Resource Graph (after dedup)")

            # Filter to specific VM resource IDs if requested (targeted rescan)
            if vm_ids:
                vm_ids_lower = {v.lower() for v in vm_ids}
                vms = [vm for vm in vms if vm.vm_id.lower() in vm_ids_lower]
                logger.info("Targeted scan: filtered to %d VMs from vm_ids filter", len(vms))

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
            response = await self._arg_query_with_retry(query_request)

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

    def _build_vm_cpe_uri(self, vm: VMScanTarget) -> Optional[str]:
        """Build CPE 2.3 URI for VM's operating system.

        Delegates to cve_inventory_sync._build_inventory_cpe_names for consistency.
        """
        from utils.cve_inventory_sync import _build_inventory_cpe_names

        normalized_name, normalized_version = self._get_vm_os_identity(vm)
        if not normalized_name or not normalized_version:
            logger.warning(f"[DEBUG-CVE-SCAN] VM {vm.name}: Missing OS identity. name={normalized_name}, version={normalized_version}, raw_name={vm.os_name}, raw_version={vm.os_version}")
            return None

        cpe_uris = _build_inventory_cpe_names(normalized_name, normalized_version)
        return cpe_uris[0] if cpe_uris else None

    def _cpe_matches(self, vm_cpe: str, product_cpe: str) -> bool:
        """Check if VM's CPE matches the product's CPE.

        Simple prefix matching - more sophisticated matching could be added.
        """
        if not vm_cpe or not product_cpe:
            return False

        # Exact match
        if vm_cpe == product_cpe:
            return True

        # Wildcard version match: cpe:2.3:o:microsoft:windows_server_2019:* matches our specific CPE
        vm_parts = vm_cpe.split(':')
        product_parts = product_cpe.split(':')

        # Must have at least 6 parts for CPE 2.3 (cpe:2.3:type:vendor:product:version:...)
        if len(vm_parts) < 6 or len(product_parts) < 6:
            return False

        # Match type, vendor, product
        if vm_parts[2:5] != product_parts[2:5]:  # type, vendor, product
            return False

        # Version matching - handle wildcards and ranges
        vm_version = vm_parts[5]
        product_version = product_parts[5]

        # If VM has wildcard/any version, match any product version for same OS
        if vm_version == '*' or vm_version == '-':
            return True

        # If product has wildcard version, match
        if product_version == '*' or product_version == '-':
            return True

        # Exact version match
        return vm_version == product_version

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
        """Build search filters with CPE for accurate CVE matching."""
        filters: Dict[str, Any] = {}
        if cve_filters:
            filters.update(cve_filters)

        normalized_name, normalized_version = self._get_vm_os_identity(vm)
        if not normalized_name:
            return filters

        # Build CPE URI for the VM's OS (primary matching method)
        cpe_uri = self._build_vm_cpe_uri(vm)
        if cpe_uri:
            filters["cpe_name"] = cpe_uri
            logger.info(f"Using CPE search for {vm.name}: {cpe_uri}")

        # Also add keyword as fallback for broader coverage
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
                response = await self._arg_query_with_retry(query_request)
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
            logger.info(f"[CPE-SCAN-2026-03-20] Starting CVE scan for VM: {vm.name}")
            filters = self._build_cve_search_filters(vm, cve_filters)
            cpe_filtered = filters.get("cpe_name") is not None
            logger.info(f"[CPE-SCAN-2026-03-20] CPE filtered={cpe_filtered}, filters={filters.get('cpe_name', 'NONE')}")

            # When CPE filtering is used, get ALL results in one query (no pagination needed)
            # CPE filtering is highly selective and SQL does the matching
            if cpe_filtered:
                cves = await self.cve_service.search_cves(
                    filters=filters,
                    limit=999999,  # No effective limit - get ALL CPE matches
                    offset=0,
                    allow_live_fallback=False,
                )
                logger.info(f"[DEBUG-CVE-SCAN] VM {vm.name}: Retrieved {len(cves)} CVEs via CPE filter. CPE={filters.get('cpe_name')}")
            else:
                # Legacy pagination for non-CPE searches
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
                # When CPE filtered, SQL already matched - accept all
                if cpe_filtered or self._is_vm_affected(vm, cve):
                    # Extract severity directly from CVE object or database fields
                    severity = None
                    cvss_score = None

                    if hasattr(cve, 'cvss_v3') and cve.cvss_v3:
                        severity = cve.cvss_v3.base_severity
                        cvss_score = cve.cvss_v3.base_score
                    elif hasattr(cve, 'cvss_v3_severity'):
                        # Fallback: use flat field from database
                        severity = cve.cvss_v3_severity
                        cvss_score = getattr(cve, 'cvss_v3_score', None)
                    elif hasattr(cve, 'cvss_v2') and cve.cvss_v2:
                        severity = cve.cvss_v2.base_severity
                        cvss_score = cve.cvss_v2.base_score
                    elif hasattr(cve, 'cvss_v2_severity'):
                        # Fallback: use flat field from database
                        severity = cve.cvss_v2_severity
                        cvss_score = getattr(cve, 'cvss_v2_score', None)

                    match = CVEMatch(
                        cve_id=cve.cve_id,
                        vm_id=vm.vm_id,
                        vm_name=vm.name,
                        match_reason=self._get_match_reason(vm, cve),
                        cvss_score=cvss_score,
                        severity=severity,
                        published_date=cve.published_date.isoformat() if hasattr(cve.published_date, 'isoformat') else str(cve.published_date)
                    )
                    matches.append(match)

        except Exception as e:
            logger.error(f"CVE matching failed for VM {vm.name}: {e}")

        return matches

    def _build_vm_match_summary(
        self,
        vm: VMScanTarget,
        matches: List[CVEMatch],
        enrichment: Optional["VMPatchEnrichment"] = None,
    ) -> Dict[str, Any]:
        """Build a compact per-VM summary with patch-aware counts."""
        summary = {
            "vm_id": vm.vm_id,
            "vm_name": vm.name,
            "total_cves": len(matches),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "patch_summary": enrichment.patch_summary if enrichment else {},
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
        """Check if VM is affected by CVE using CPE matching.

        Args:
            vm: VM to check
            cve: CVE to match

        Returns:
            True if VM is affected
        """
        # Build VM's CPE URI for matching
        vm_cpe = self._build_vm_cpe_uri(vm)

        # Check CPE-level match (primary method - most accurate)
        if vm_cpe:
            for product in cve.affected_products:
                cpe_uri = product.cpe_uri if hasattr(product, 'cpe_uri') else None
                if cpe_uri and self._cpe_matches(vm_cpe, cpe_uri):
                    return True

        # Fallback: Check OS-level product name match (legacy behavior)
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
