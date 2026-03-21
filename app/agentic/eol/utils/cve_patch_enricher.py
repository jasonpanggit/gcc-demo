"""CVEPatchEnricher — bulk patch enrichment for CVE scan pipeline.

Responsibilities:
- Bulk-fetch patch assessments per subscription (one ARG query pair per subscription)
- Map KB IDs → CVE IDs via KBCVEEdgeRepository (batched PostgreSQL queries)
- Cross-reference with a VM's matched CVEs to compute patch_status per CVE
- Return VMPatchEnrichment dataclass with pre-computed summary counts

Designed to be called from CVEScanner._execute_scan:
  1. enricher.prefetch_patch_data(subscription_ids, vms) — before VM loop
  2. enricher.enrich_vm(vm, matches, vm_patch_data) — inside VM loop (pure, no I/O)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from models.cve_models import CVEMatch, VMScanTarget
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVEMatch, VMScanTarget
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class VMPatchEnrichment:
    """Pre-computed patch enrichment result for one VM."""
    installed_kb_ids: List[str] = field(default_factory=list)
    available_kb_ids: List[str] = field(default_factory=list)
    installed_cve_ids: List[str] = field(default_factory=list)   # matched CVEs fixed by installed KBs
    available_cve_ids: List[str] = field(default_factory=list)   # matched CVEs fixable by available KBs
    patch_summary: Dict[str, int] = field(default_factory=lambda: {
        "unpatched_critical": 0,
        "unpatched_high": 0,
        "unpatched_medium": 0,
        "unpatched_low": 0,
        "covered_cves": 0,
        "fixable_cves": 0,
        "total_unpatched": 0,
    })


_EMPTY_ENRICHMENT = VMPatchEnrichment()


class CVEPatchEnricher:
    """Bulk patch enrichment for the CVE scan pipeline.

    Usage:
        enricher = CVEPatchEnricher(patch_mcp_client, kb_cve_edge_repository)

        # Before VM loop — one bulk call per subscription
        patch_map = await enricher.prefetch_patch_data(subscription_ids, vms)

        # Inside VM loop — pure, no I/O
        enrichment = await enricher.enrich_vm(vm, matches, patch_map.get(vm.name.lower()))
    """

    def __init__(self, patch_mcp_client, kb_cve_edge_repository) -> None:
        self.patch_mcp_client = patch_mcp_client
        self.kb_cve_repo = kb_cve_edge_repository

    async def prefetch_patch_data(
        self,
        subscription_ids: List[str],
        vms: List[VMScanTarget],
    ) -> Dict[str, Any]:
        """Bulk-fetch patch assessments for all subscriptions.

        Fires one query_patch_assessments(subscription_id, machine_name=None) per
        subscription in parallel. Each call fetches ALL VMs in that subscription via
        a single ARG query pair, cached with '__all__' key (1hr TTL).

        Returns:
            Dict mapping machine_name.lower() → patch_data dict from the MCP response.
            Returns empty dict on failure (scan continues without patch enrichment).
        """
        if not subscription_ids or not self.patch_mcp_client:
            return {}

        # Collect unique subscription IDs from the discovered VMs
        # (use vm.subscription_id if available, fall back to passed subscription_ids)
        unique_subs = list({
            getattr(vm, "subscription_id", None) or sub
            for vm in vms
            for sub in subscription_ids
        } or subscription_ids)

        async def _fetch_one(sub_id: str) -> Dict[str, Any]:
            try:
                result = await self.patch_mcp_client.query_patch_assessments(
                    subscription_id=sub_id,
                    machine_name=None,   # bulk: fetch all VMs in subscription
                )
                if not result.get("success"):
                    logger.warning("Patch prefetch failed for subscription %s: %s", sub_id, result.get("error"))
                    return {}
                # Build machine_name.lower() → patch_data mapping
                mapping: Dict[str, Any] = {}
                for vm_data in result.get("data") or []:
                    name = (vm_data.get("machine_name") or "").strip().lower()
                    if name:
                        mapping[name] = vm_data
                logger.info("Patch prefetch: %d VMs for subscription %s", len(mapping), sub_id)

                # Persist ARG patch data to available_patches and trigger KB→CVE edge sync
                try:
                    from utils.repositories.patch_repository import PatchRepository
                    from utils.cve_sync_operations import sync_kb_edges_for_kbs
                    from utils.vendor_feed_client import VendorFeedClient
                    from utils.pg_client import postgres_client
                    from utils.config import config

                    _patch_repo = PatchRepository(postgres_client.pool)
                    _all_kb_numbers: List[str] = []

                    for _vm_data in result.get("data") or []:
                        _resource_id = _vm_data.get("resource_id")
                        _patches = ((_vm_data.get("patches") or {}).get("available_patches") or [])
                        if _resource_id and _patches:
                            _count = await _patch_repo.upsert_available_patches(_resource_id, _patches)
                            if _count:
                                _all_kb_numbers.extend([
                                    f"KB{p['kbId']}" if not str(p.get('kbId', '')).upper().startswith('KB')
                                    else str(p['kbId'])
                                    for p in _patches
                                    if p.get('kbId') and str(p.get('kbId', '')).lower() != 'null'
                                ])

                    if _all_kb_numbers and getattr(postgres_client, "pool", None):
                        _cve_cfg = config.cve_data
                        _vendor = VendorFeedClient(
                            redhat_base_url=_cve_cfg.redhat_base_url,
                            ubuntu_base_url=_cve_cfg.ubuntu_base_url,
                            msrc_base_url=_cve_cfg.msrc_base_url,
                            msrc_api_key=_cve_cfg.msrc_api_key or None,
                            request_timeout=_cve_cfg.request_timeout,
                        )

                        async def _kb_edge_sync_task(kb_numbers, vendor, pool):
                            try:
                                await sync_kb_edges_for_kbs(kb_numbers, vendor, pool=pool)
                            finally:
                                await vendor.close()

                        asyncio.create_task(
                            _kb_edge_sync_task(_all_kb_numbers, _vendor, postgres_client.pool)
                        )
                except Exception as _exc:
                    logger.warning("Failed to persist ARG patches or schedule KB edge sync: %s", _exc)

                return mapping
            except Exception as exc:
                logger.warning("Patch prefetch exception for subscription %s: %s", sub_id, exc)
                return {}

        results = await asyncio.gather(*[_fetch_one(s) for s in unique_subs], return_exceptions=False)

        # Merge all subscription mappings into one (machine names should be unique across subs)
        merged: Dict[str, Any] = {}
        for mapping in results:
            merged.update(mapping)
        logger.info("Patch prefetch complete: %d total VMs with patch data", len(merged))
        return merged

    async def enrich_vm(
        self,
        vm: VMScanTarget,
        matches: List[CVEMatch],
        vm_patch_data: Optional[Dict[str, Any]],
    ) -> VMPatchEnrichment:
        """Compute patch enrichment for one VM.

        Maps KB IDs from patch data → CVE IDs, cross-references with matched CVEs,
        and computes unpatched summary counts.

        Args:
            vm: The VM being scanned.
            matches: CVE matches for this VM from _match_cves_to_vm().
            vm_patch_data: Single-VM entry from prefetch_patch_data(), or None if unavailable.

        Returns:
            VMPatchEnrichment with pre-computed counts. Returns empty enrichment on any error.
        """
        if not vm_patch_data or not matches:
            return VMPatchEnrichment()

        try:
            patches = vm_patch_data.get("patches") or {}

            # Extract KB IDs from installed patches (from software inventory via ARG)
            # Note: query_patch_assessments returns available_patches from patchassessmentresources.
            # installed patches are NOT in this ARG table — they come from software inventory.
            # We store available_kb_ids from ARG; installed_kb_ids left empty here (populated
            # separately if software inventory data is available on VMScanTarget).
            available_patches = patches.get("available_patches") or []
            available_kb_ids = sorted({
                kb for p in available_patches
                if (kb := (p.get("kbId") or "").strip())
            })

            # installed_kb_ids: use vm.installed_packages for Windows KB patterns if available
            installed_kb_ids = sorted({
                pkg for pkg in (getattr(vm, "installed_packages", None) or [])
                if pkg.upper().startswith("KB")
            })

            # Batch map all KB IDs → CVE IDs via edge repository
            all_kb_ids = list(set(installed_kb_ids) | set(available_kb_ids))
            kb_to_cves = await self._batch_map_kbs_to_cves(all_kb_ids)

            # Build CVE ID sets from KB mappings
            installed_fixed_cves: set[str] = set()
            for kb in installed_kb_ids:
                installed_fixed_cves.update(kb_to_cves.get(kb, []))

            available_fixes_cves: set[str] = set()
            for kb in available_kb_ids:
                available_fixes_cves.update(kb_to_cves.get(kb, []))

            # Cross-reference with matched CVE IDs
            matched_cve_ids = {m.cve_id.upper() for m in matches if m.cve_id}
            installed_cve_ids = sorted(matched_cve_ids & {c.upper() for c in installed_fixed_cves})
            available_cve_ids = sorted(
                (matched_cve_ids - {c.upper() for c in installed_fixed_cves})
                & {c.upper() for c in available_fixes_cves}
            )

            installed_set = set(installed_cve_ids)
            available_set = set(available_cve_ids)

            # Compute unpatched severity counts
            counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
            covered = 0
            fixable = 0
            for match in matches:
                cve_upper = (match.cve_id or "").upper()
                severity = (match.severity or "LOW").upper()
                if cve_upper in installed_set:
                    covered += 1
                    continue  # covered — not unpatched
                if cve_upper in available_set:
                    fixable += 1
                # Still unpatched (either fixable or no fix)
                bucket = severity if severity in counts else "LOW"
                counts[bucket] += 1

            total_unpatched = sum(counts.values())

            return VMPatchEnrichment(
                installed_kb_ids=installed_kb_ids,
                available_kb_ids=available_kb_ids,
                installed_cve_ids=installed_cve_ids,
                available_cve_ids=available_cve_ids,
                patch_summary={
                    "unpatched_critical": counts["CRITICAL"],
                    "unpatched_high": counts["HIGH"],
                    "unpatched_medium": counts["MEDIUM"],
                    "unpatched_low": counts["LOW"],
                    "covered_cves": covered,
                    "fixable_cves": fixable,
                    "total_unpatched": total_unpatched,
                },
            )

        except Exception as exc:
            logger.warning("Patch enrichment failed for VM %s: %s", getattr(vm, "name", "unknown"), exc)
            return VMPatchEnrichment()

    async def _batch_map_kbs_to_cves(self, kb_ids: List[str]) -> Dict[str, List[str]]:
        """Batch-fetch CVE IDs for a list of KB IDs via PostgreSQL queries.

        Uses asyncio.gather for all lookups in parallel.
        Returns Dict[kb_id → [cve_ids]]. Missing KBs map to [].
        """
        if not kb_ids or not self.kb_cve_repo:
            return {}

        results = await asyncio.gather(
            *[self.kb_cve_repo.get_cve_ids_for_kb(kb) for kb in kb_ids],
            return_exceptions=True,
        )
        return {
            kb: (cves if isinstance(cves, list) else [])
            for kb, cves in zip(kb_ids, results)
        }
