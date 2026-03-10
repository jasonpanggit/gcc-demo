"""
Linux advisory↔CVE edge sync service.

Syncs RHSA (Red Hat) and USN (Ubuntu) advisory edges into the edge store for
CVEs found on Linux VMs during a scan.  Mirrors the role of the MSRC SUG sync
for Windows — called from cve_scanner._execute_scan() after a scan completes.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, TYPE_CHECKING

try:
    from models.cve_models import PatchAdvisoryEdge, ScanResult
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import PatchAdvisoryEdge, ScanResult
    from app.agentic.eol.utils.logging_config import get_logger

if TYPE_CHECKING:
    from utils.vendor_feed_client import VendorFeedClient
    from utils.kb_cve_edge_repository import KBCVEEdgeRepository

logger = get_logger(__name__)

# OS families that map to the Red Hat Security API
_REDHAT_FAMILIES = frozenset({"rhel", "centos"})
# OS families that map to the Ubuntu Security API
_UBUNTU_FAMILIES = frozenset({"ubuntu"})

# Maximum concurrent vendor API fetches
_DEFAULT_CONCURRENCY = 5


class LinuxAdvisorySyncService:
    """Syncs Linux advisory↔CVE edges for CVEs found on Linux VMs.

    Called from cve_scanner._execute_scan() after scan completes,
    same hook pattern as the MSRC SUG sync.
    """

    def __init__(
        self,
        vendor_feed_client: "VendorFeedClient",
        edge_repo: "KBCVEEdgeRepository",
        config: Optional[object] = None,
    ) -> None:
        self._vendor = vendor_feed_client
        self._edge_repo = edge_repo
        self._concurrency = _DEFAULT_CONCURRENCY

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def sync_for_scan_result(self, scan_result: ScanResult) -> Dict[str, int]:
        """Sync advisory edges for all Linux VMs in this scan result.

        Steps:
        1. Identify Linux VM IDs from scan_result.vm_os_family.
        2. Collect CVE IDs that affect those VMs from scan_result.matches.
        3. Determine which os_families are present (ubuntu, rhel, centos).
        4. Delegate to sync_cve_list() for the collected CVEs + os_families.

        Returns:
            {"redhat": N, "ubuntu": M} upserted-edge counts.
        """
        # Step 1 — Linux VM IDs and their os_families
        linux_vm_ids: Dict[str, str] = {
            vm_id: family
            for vm_id, family in scan_result.vm_os_family.items()
            if family.lower() in (_REDHAT_FAMILIES | _UBUNTU_FAMILIES)
        }

        if not linux_vm_ids:
            logger.debug(
                "scan %s: no Linux VMs found, skipping advisory sync",
                scan_result.scan_id,
            )
            return {"redhat": 0, "ubuntu": 0}

        # Step 2 — CVE IDs that touched at least one Linux VM
        cve_ids: List[str] = sorted(
            {
                match.cve_id
                for match in scan_result.matches
                if match.vm_id in linux_vm_ids
            }
        )

        if not cve_ids:
            logger.debug(
                "scan %s: Linux VMs present but no CVE matches, skipping advisory sync",
                scan_result.scan_id,
            )
            return {"redhat": 0, "ubuntu": 0}

        # Step 3 — which os_families are actually present
        present_families: List[str] = sorted(set(linux_vm_ids.values()))

        logger.info(
            "scan %s: syncing %d CVE(s) for Linux VMs; families=%s",
            scan_result.scan_id,
            len(cve_ids),
            present_families,
        )

        # Step 4 — delegate
        return await self.sync_cve_list(cve_ids, present_families)

    # ------------------------------------------------------------------
    # Core sync logic
    # ------------------------------------------------------------------

    async def sync_cve_list(
        self,
        cve_ids: List[str],
        os_families: List[str],
    ) -> Dict[str, int]:
        """Fetch advisory edges for each CVE × relevant os_family.

        - For rhel/centos: fetch_redhat_cve() → parse_redhat_advisory()
        - For ubuntu:      fetch_ubuntu_cve() → parse_ubuntu_advisory()
        - Upserts via edge_repo.upsert_linux_edges()
        - Rate-limited to _DEFAULT_CONCURRENCY concurrent vendor API calls.
        - Per-CVE errors are caught and logged; the batch continues.

        Returns:
            {"redhat": N, "ubuntu": M} upserted-edge counts.
        """
        lower_families = {f.lower() for f in os_families}
        need_redhat = bool(lower_families & _REDHAT_FAMILIES)
        need_ubuntu = bool(lower_families & _UBUNTU_FAMILIES)

        if not need_redhat and not need_ubuntu:
            logger.debug("sync_cve_list: no recognised Linux families in %s", os_families)
            return {"redhat": 0, "ubuntu": 0}

        semaphore = asyncio.Semaphore(self._concurrency)
        totals: Dict[str, int] = {"redhat": 0, "ubuntu": 0}

        async def _sync_one(cve_id: str) -> None:
            async with semaphore:
                if need_redhat:
                    totals["redhat"] += await self._sync_redhat(cve_id)
                if need_ubuntu:
                    totals["ubuntu"] += await self._sync_ubuntu(cve_id)

        await asyncio.gather(*(_sync_one(cve_id) for cve_id in cve_ids))

        logger.info(
            "sync_cve_list complete: %d CVE(s) processed; redhat=%d ubuntu=%d",
            len(cve_ids),
            totals["redhat"],
            totals["ubuntu"],
        )
        return totals

    # ------------------------------------------------------------------
    # Per-vendor helpers
    # ------------------------------------------------------------------

    async def _sync_redhat(self, cve_id: str) -> int:
        """Fetch Red Hat advisory data for one CVE and upsert edges.

        Returns the number of edges upserted (0 on error or no data).
        """
        try:
            data = await self._vendor.fetch_redhat_cve(cve_id)
            if not data:
                return 0
            edge_dicts = self._vendor.parse_redhat_advisory(cve_id, data)
            if not edge_dicts:
                return 0
            edges = [PatchAdvisoryEdge(**d) for d in edge_dicts]
            return await self._edge_repo.upsert_linux_edges(edges)
        except Exception as exc:
            logger.warning(
                "linux_advisory_sync: redhat fetch/parse failed for %s: %s",
                cve_id,
                exc,
            )
            return 0

    async def _sync_ubuntu(self, cve_id: str) -> int:
        """Fetch Ubuntu advisory data for one CVE and upsert edges.

        Returns the number of edges upserted (0 on error or no data).
        """
        try:
            data = await self._vendor.fetch_ubuntu_cve(cve_id)
            if not data:
                return 0
            edge_dicts = self._vendor.parse_ubuntu_advisory(cve_id, data)
            if not edge_dicts:
                return 0
            edges = [PatchAdvisoryEdge(**d) for d in edge_dicts]
            return await self._edge_repo.upsert_linux_edges(edges)
        except Exception as exc:
            logger.warning(
                "linux_advisory_sync: ubuntu fetch/parse failed for %s: %s",
                cve_id,
                exc,
            )
            return 0
