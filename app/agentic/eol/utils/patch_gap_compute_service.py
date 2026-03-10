"""Bridges CVE scan results + edge repository → produces PatchGapVMDocs.

Strategy pattern: OsGapStrategy dispatches to WindowsGapStrategy or
LinuxGapStrategy based on vm os_type.  PatchGapComputeService fans out per-VM
computation concurrently (Semaphore(8)) and writes both per-VM docs and the
fleet summary into the provided PatchGapRepository.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

try:
    from models.cve_models import (
        PatchGapCVEItem,
        PatchGapFleetSummary,
        PatchGapKBItem,
        PatchGapVMDoc,
        PatchGapVMItem,
        ScanResult,
    )
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import (
        PatchGapCVEItem,
        PatchGapFleetSummary,
        PatchGapKBItem,
        PatchGapVMDoc,
        PatchGapVMItem,
        ScanResult,
    )
    from app.agentic.eol.utils.logging_config import get_logger


logger = get_logger(__name__)

_SEMAPHORE_LIMIT = 8


# =============================================================================
# Strategy protocol
# =============================================================================

@runtime_checkable
class OsGapStrategy(Protocol):
    """Compute the list of missing patches/advisories for a single VM."""

    async def compute_gap(
        self,
        vm_id: str,
        cve_ids: List[str],
        scan_result: ScanResult,
        edge_repo: Any,
    ) -> List[PatchGapKBItem]: ...


# =============================================================================
# Windows strategy
# =============================================================================

class WindowsGapStrategy:
    """Determine missing KBs for a Windows VM.

    For each CVE matched to the VM, look up the KBs that fix it via the
    edge repository.  Any KB not already installed (from scan_result
    .vm_installed_kbs) is part of the gap.  Results are grouped by
    kb_number and cve_ids are merged.
    """

    async def compute_gap(
        self,
        vm_id: str,
        cve_ids: List[str],
        scan_result: ScanResult,
        edge_repo: Any,
    ) -> List[PatchGapKBItem]:
        installed_kbs = set(scan_result.vm_installed_kbs.get(vm_id, []))

        # kb_number → {cve_ids, severity_set}
        kb_map: Dict[str, Dict[str, Any]] = {}

        for cve_id in cve_ids:
            try:
                kbs = await edge_repo.get_kbs_for_cve(cve_id)
            except Exception as exc:
                logger.warning("Windows gap: get_kbs_for_cve(%s) failed: %s", cve_id, exc)
                continue

            for kb in kbs:
                normalized_kb = kb.upper() if kb else kb
                if not normalized_kb or normalized_kb in installed_kbs:
                    continue
                if normalized_kb not in kb_map:
                    kb_map[normalized_kb] = {"cve_ids": [], "severity": None}
                if cve_id not in kb_map[normalized_kb]["cve_ids"]:
                    kb_map[normalized_kb]["cve_ids"].append(cve_id)

        return [
            PatchGapKBItem(
                kb_number=kb_number,
                advisory_id=kb_number,
                cve_ids=info["cve_ids"],
                severity=info["severity"],
                os_family="windows",
            )
            for kb_number, info in kb_map.items()
        ]


# =============================================================================
# Linux strategy
# =============================================================================

class LinuxGapStrategy:
    """Determine missing advisories for a Linux VM.

    For each CVE matched to the VM, look up advisories that provide fixed
    packages via the edge repository.  An advisory is considered missing if
    ANY of its fixed packages is not present in the VM's installed package list.
    """

    async def compute_gap(
        self,
        vm_id: str,
        cve_ids: List[str],
        scan_result: ScanResult,
        edge_repo: Any,
    ) -> List[PatchGapKBItem]:
        installed_pkgs = set(scan_result.vm_installed_packages.get(vm_id, []))
        os_family = scan_result.vm_os_family.get(vm_id, "linux")

        # advisory_id → {cve_ids, missing_packages}
        advisory_map: Dict[str, Dict[str, Any]] = {}

        for cve_id in cve_ids:
            try:
                # Returns {advisory_id: [fixed_package_names]}
                pkg_map: Dict[str, List[str]] = await edge_repo.get_fixed_packages_for_cve(
                    cve_id, os_family
                )
            except Exception as exc:
                logger.warning(
                    "Linux gap: get_fixed_packages_for_cve(%s, %s) failed: %s",
                    cve_id, os_family, exc,
                )
                continue

            for advisory_id, fixed_packages in pkg_map.items():
                # Gap = advisory has at least one fixed package not yet installed
                missing = [p for p in fixed_packages if p not in installed_pkgs]
                if not missing:
                    continue

                if advisory_id not in advisory_map:
                    advisory_map[advisory_id] = {"cve_ids": [], "missing_packages": []}

                entry = advisory_map[advisory_id]
                if cve_id not in entry["cve_ids"]:
                    entry["cve_ids"].append(cve_id)
                for pkg in missing:
                    if pkg not in entry["missing_packages"]:
                        entry["missing_packages"].append(pkg)

        return [
            PatchGapKBItem(
                kb_number=advisory_id,
                advisory_id=advisory_id,
                cve_ids=info["cve_ids"],
                package_names=info["missing_packages"],
                os_family=os_family,
            )
            for advisory_id, info in advisory_map.items()
        ]


# =============================================================================
# Strategy registry
# =============================================================================

STRATEGIES: Dict[str, OsGapStrategy] = {
    "Windows": WindowsGapStrategy(),
    "Linux": LinuxGapStrategy(),
}


# =============================================================================
# Compute service
# =============================================================================

class PatchGapComputeService:
    """Compute patch gaps for all VMs in a scan result and persist the docs.

    Depends on:
      - kb_cve_repo: KBCVEEdgeRepository (or InMemory equivalent)
      - patch_gap_repo: PatchGapRepository (or InMemory equivalent)
      - config: optional app config (unused directly, accepted for DI compatibility)
    """

    def __init__(self, kb_cve_repo: Any, patch_gap_repo: Any, config: Any = None):
        self.kb_cve_repo = kb_cve_repo
        self.patch_gap_repo = patch_gap_repo
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compute_and_store(self, scan_result: ScanResult) -> None:
        """Compute patch gaps for ALL VMs in *scan_result*, store docs and fleet summary."""
        vm_ids = list({match.vm_id for match in scan_result.matches})
        if not vm_ids:
            logger.info("compute_and_store: no VM IDs in scan result %s", scan_result.scan_id)
            return

        logger.info(
            "compute_and_store: processing %d VMs for scan %s",
            len(vm_ids), scan_result.scan_id,
        )
        await self._fan_out(vm_ids, scan_result)
        await self._compute_and_store_fleet_summary(scan_result)

    async def compute_for_vms(self, vm_ids: List[str], scan_result: ScanResult) -> None:
        """Targeted refresh for specific VMs (e.g. post-patch-install)."""
        if not vm_ids:
            return
        logger.info(
            "compute_for_vms: refreshing %d VMs for scan %s",
            len(vm_ids), scan_result.scan_id,
        )
        await self._fan_out(vm_ids, scan_result)
        await self._compute_and_store_fleet_summary(scan_result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fan_out(self, vm_ids: List[str], scan_result: ScanResult) -> None:
        """Concurrently compute and store per-VM docs, bounded by semaphore."""
        semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

        async def _process_one(vm_id: str) -> None:
            async with semaphore:
                try:
                    await self._compute_and_store_vm(vm_id, scan_result)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "compute_and_store_vm failed for %s: %s", vm_id, exc, exc_info=True
                    )

        await asyncio.gather(*[_process_one(vid) for vid in vm_ids])

    async def _compute_and_store_vm(self, vm_id: str, scan_result: ScanResult) -> None:
        """Compute gap for one VM and upsert the document."""
        summary_info = scan_result.vm_match_summaries.get(vm_id) or {}

        # Determine OS type from vm_match_summaries; fall back to vm_os_family
        os_type = summary_info.get("os_type") or _infer_os_type(
            scan_result.vm_os_family.get(vm_id, "linux")
        )
        vm_name = summary_info.get("vm_name") or vm_id
        os_name = summary_info.get("os_name")
        location = summary_info.get("location")
        resource_group = summary_info.get("resource_group")
        subscription_id = summary_info.get("subscription_id")

        # Collect CVE IDs for this VM
        cve_ids: List[str] = summary_info.get("cve_ids") or [
            match.cve_id
            for match in scan_result.matches
            if match.vm_id == vm_id
        ]

        # Dispatch to the appropriate OS strategy
        strategy = STRATEGIES.get(os_type, STRATEGIES["Linux"])
        available_kbs = await strategy.compute_gap(
            vm_id=vm_id,
            cve_ids=cve_ids,
            scan_result=scan_result,
            edge_repo=self.kb_cve_repo,
        )

        # Derive installed identifiers list
        if os_type == "Windows":
            installed_identifiers = list(scan_result.vm_installed_kbs.get(vm_id, []))
        else:
            installed_identifiers = list(scan_result.vm_installed_packages.get(vm_id, []))

        # CVEs that have at least one available fix
        unpatched_cves = sorted(
            {cve_id for item in available_kbs for cve_id in item.cve_ids}
        )

        # Severity counters (best-effort from match data)
        severity_map = _build_severity_map(scan_result)
        critical_count = sum(
            1 for cve_id in unpatched_cves
            if (severity_map.get(cve_id) or "").upper() == "CRITICAL"
        )
        high_count = sum(
            1 for cve_id in unpatched_cves
            if (severity_map.get(cve_id) or "").upper() == "HIGH"
        )

        doc = PatchGapVMDoc(
            id=vm_id,
            vm_id=vm_id,
            vm_name=vm_name,
            os_type=os_type,
            os_family=scan_result.vm_os_family.get(vm_id),
            os_name=os_name,
            location=location,
            resource_group=resource_group,
            subscription_id=subscription_id,
            scan_id=scan_result.scan_id,
            computed_at=datetime.now(timezone.utc).isoformat(),
            available_kbs=available_kbs,
            unpatched_cves=unpatched_cves,
            installed_identifiers=installed_identifiers,
            total_available_advisories=len(available_kbs),
            total_unpatched_cves=len(unpatched_cves),
            critical_count=critical_count,
            high_count=high_count,
        )

        await self.patch_gap_repo.upsert_vm_gap(doc)
        logger.debug(
            "Stored gap doc for %s: %d advisories, %d unpatched CVEs",
            vm_id, len(available_kbs), len(unpatched_cves),
        )

    async def _compute_and_store_fleet_summary(self, scan_result: ScanResult) -> None:
        """Read back all recent VM docs and aggregate into the fleet summary."""
        vm_docs = await self.patch_gap_repo.get_all_vm_gaps(max_age_hours=48)

        total_vms = len(vm_docs)
        vms_with_gaps = sum(1 for d in vm_docs if d.available_kbs)
        total_advisories = sum(d.total_available_advisories for d in vm_docs)
        total_unpatched = sum(d.total_unpatched_cves for d in vm_docs)
        critical_count = sum(d.critical_count for d in vm_docs)

        # by_vm list
        by_vm: List[PatchGapVMItem] = [
            PatchGapVMItem(
                vm_id=d.vm_id,
                vm_name=d.vm_name,
                os_type=d.os_type,
                os_family=d.os_family,
                os_name=d.os_name,
                location=d.location,
                resource_group=d.resource_group,
                subscription_id=d.subscription_id,
                unpatched_with_fix=d.total_unpatched_cves,
                total_unpatched=d.total_unpatched_cves,
                available_patches=d.total_available_advisories,
            )
            for d in vm_docs
        ]

        # by_kb aggregation: group PatchGapKBItem by kb_number across all VMs,
        # merge affected VM lists and CVE IDs
        kb_agg: Dict[str, Dict[str, Any]] = {}
        for doc in vm_docs:
            for kb_item in doc.available_kbs:
                kb_num = kb_item.kb_number
                if kb_num not in kb_agg:
                    kb_agg[kb_num] = {
                        "advisory_id": kb_item.advisory_id,
                        "cve_ids": set(),
                        "severity": kb_item.severity,
                        "package_names": list(kb_item.package_names or []),
                        "os_family": kb_item.os_family,
                        "highest_cvss": kb_item.highest_cvss,
                    }
                kb_agg[kb_num]["cve_ids"].update(kb_item.cve_ids)

        by_kb: List[PatchGapKBItem] = [
            PatchGapKBItem(
                kb_number=kb_num,
                advisory_id=info["advisory_id"],
                cve_ids=sorted(info["cve_ids"]),
                severity=info["severity"],
                package_names=info["package_names"] or None,
                os_family=info["os_family"],
                highest_cvss=info["highest_cvss"],
            )
            for kb_num, info in kb_agg.items()
        ]

        # by_cve: aggregate vm_ids per CVE across all VMs
        cve_vm_map: Dict[str, List[str]] = defaultdict(list)
        for doc in vm_docs:
            for cve_id in doc.unpatched_cves:
                cve_vm_map[cve_id].append(doc.vm_id)

        severity_map = _build_severity_map(scan_result)
        by_cve: List[PatchGapCVEItem] = [
            PatchGapCVEItem(
                cve_id=cve_id,
                severity=severity_map.get(cve_id),
                available_advisory_ids=sorted(
                    {
                        kb_item.kb_number
                        for doc in vm_docs
                        for kb_item in doc.available_kbs
                        if cve_id in kb_item.cve_ids
                    }
                ),
                vm_ids=sorted(set(vm_ids)),
                vm_count=len(set(vm_ids)),
            )
            for cve_id, vm_ids in cve_vm_map.items()
        ]

        summary = PatchGapFleetSummary(
            id="_fleet_summary",
            computed_at=datetime.now(timezone.utc).isoformat(),
            total_vms=total_vms,
            vms_with_gaps=vms_with_gaps,
            total_outstanding_advisories=total_advisories,
            total_unpatched_cves=total_unpatched,
            critical_cve_count=critical_count,
            stale_vm_count=0,  # freshly computed — none are stale yet
            by_kb=by_kb,
            by_cve=by_cve,
            by_vm=by_vm,
        )

        await self.patch_gap_repo.upsert_fleet_summary(summary)
        logger.info(
            "Fleet summary: %d VMs, %d with gaps, %d advisories, %d unpatched CVEs",
            total_vms, vms_with_gaps, total_advisories, total_unpatched,
        )


# =============================================================================
# Module-level helpers
# =============================================================================

def _infer_os_type(os_family: str) -> str:
    """Map os_family string to canonical os_type ("Windows" | "Linux")."""
    return "Windows" if os_family.lower() == "windows" else "Linux"


def _build_severity_map(scan_result: ScanResult) -> Dict[str, str]:
    """Build a cve_id → severity dict from the matches in *scan_result*."""
    result: Dict[str, str] = {}
    for match in scan_result.matches:
        if match.cve_id not in result and match.severity:
            result[match.cve_id] = match.severity.upper()
    return result
