"""Patch Gap Analysis API Router

Provides REST API endpoint for fleet-level patch gap analysis.

Endpoints:
    GET /api/cve/patch-gaps - Fleet-level patch gap analysis across all VMs
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Request

try:
    from models.cve_models import PatchGapFleetSummary, PatchGapVMDoc
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import PatchGapFleetSummary, PatchGapVMDoc
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Patch Gaps"])

SEVERITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "": 0}


def _empty_summary_response() -> StandardResponse:
    """Return an empty fleet summary with stale=True when no scan data exists."""
    return StandardResponse.success_response(
        data={
            "summary": {
                "total_vms": 0,
                "vms_with_gaps": 0,
                "total_outstanding_advisories": 0,
                "total_unpatched_cves": 0,
                "critical_cve_count": 0,
                "stale_vm_count": 0,
            },
            "by_kb": [],
            "by_cve": [],
            "by_vm": [],
        },
        metadata={
            "stale": True,
            "message": "No scan data yet. Run a CVE scan to populate.",
        },
    )


def _build_summary_from_docs(docs: List[PatchGapVMDoc]) -> Dict[str, Any]:
    """Build a basic fleet summary dict from VM gap documents when no stored summary exists."""
    total_vms = len(docs)
    vms_with_gaps = sum(1 for d in docs if d.available_kbs)
    total_outstanding_advisories = sum(d.total_available_advisories for d in docs)
    total_unpatched_cves = sum(d.total_unpatched_cves for d in docs)
    critical_cve_count = sum(d.critical_count for d in docs)
    return {
        "total_vms": total_vms,
        "vms_with_gaps": vms_with_gaps,
        "total_outstanding_advisories": total_outstanding_advisories,
        "total_unpatched_cves": total_unpatched_cves,
        "critical_cve_count": critical_cve_count,
        "stale_vm_count": 0,
    }


@router.get("/cve/patch-gaps", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_patch_gaps", timeout_seconds=60)
async def get_patch_gaps(
    subscription_id: Optional[str] = Query(None, description="Filter by Azure subscription ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: Critical|High|Medium|Low"),
    os_type: Optional[str] = Query(None, description="Filter by OS type: Windows|Linux"),
    days: int = Query(default=90, ge=1, le=365, description="Look-back window for scan data in days"),
    request: Request = None,
):
    """Fleet-level patch gap analysis.

    Returns pre-computed patch gap data aggregated across all VMs.
    Falls back gracefully if no scan has run yet (returns empty with metadata.stale=true).

    Args:
        subscription_id: Optional filter by Azure subscription ID
        severity: Optional filter by advisory severity (Critical, High, Medium, Low)
        os_type: Optional filter by OS type (Windows, Linux)
        days: Look-back window — only include docs computed within this many days
        request: FastAPI Request used to access app.state.patch_gap_repo

    Returns:
        StandardResponse with keys: summary, by_kb, by_cve, by_vm
    """
    try:
        patch_gap_repo = request.app.state.patch_gap_repo

        docs: List[PatchGapVMDoc] = await patch_gap_repo.get_all_vm_gaps(max_age_hours=days * 24)

        if not docs:
            return _empty_summary_response()

        # ------------------------------------------------------------------
        # Apply filters in Python
        # ------------------------------------------------------------------
        if subscription_id:
            docs = [d for d in docs if d.subscription_id == subscription_id]

        if severity:
            docs = [
                d for d in docs
                if any(item.severity == severity for item in d.available_kbs)
            ]

        if os_type:
            docs = [d for d in docs if d.os_type == os_type]

        if not docs:
            return _empty_summary_response()

        # ------------------------------------------------------------------
        # Fleet summary — prefer stored singleton, fall back to computed
        # ------------------------------------------------------------------
        fleet_summary_dict: Dict[str, Any]
        try:
            fleet_summary: Optional[PatchGapFleetSummary] = await patch_gap_repo.get_fleet_summary()
            if fleet_summary is not None:
                fleet_summary_dict = fleet_summary.model_dump(mode="json")
                # Strip aggregated sub-lists — we build those below from filtered docs
                fleet_summary_dict.pop("by_kb", None)
                fleet_summary_dict.pop("by_cve", None)
                fleet_summary_dict.pop("by_vm", None)
                fleet_summary_dict.pop("id", None)
            else:
                fleet_summary_dict = _build_summary_from_docs(docs)
        except Exception as summary_error:
            logger.warning("Failed to retrieve fleet summary, building from docs: %s", summary_error)
            fleet_summary_dict = _build_summary_from_docs(docs)

        # ------------------------------------------------------------------
        # Build by_kb: aggregate advisories across all filtered VM docs
        # ------------------------------------------------------------------
        kb_index: Dict[str, Dict[str, Any]] = {}
        for doc in docs:
            for kb in doc.available_kbs:
                key = kb.kb_number
                if key not in kb_index:
                    kb_index[key] = {
                        "kb_number": kb.kb_number,
                        "advisory_id": kb.advisory_id,
                        "severity": kb.severity or "",
                        "os_family": kb.os_family,
                        "cve_ids": list(kb.cve_ids),
                        "cve_count": len(kb.cve_ids),
                        "highest_cvss": kb.highest_cvss,
                        "package_names": list(kb.package_names) if kb.package_names else [],
                        "vm_count": 1,
                    }
                else:
                    entry = kb_index[key]
                    entry["vm_count"] += 1
                    # Merge CVE IDs without duplicates
                    existing_cves = set(entry["cve_ids"])
                    new_cves = [c for c in kb.cve_ids if c not in existing_cves]
                    entry["cve_ids"].extend(new_cves)
                    entry["cve_count"] = len(entry["cve_ids"])
                    # Track highest CVSS across VMs
                    if kb.highest_cvss is not None:
                        if entry["highest_cvss"] is None or kb.highest_cvss > entry["highest_cvss"]:
                            entry["highest_cvss"] = kb.highest_cvss

        by_kb = sorted(
            kb_index.values(),
            key=lambda x: (
                SEVERITY_ORDER.get(x.get("severity") or "", 0),
                x.get("cve_count", 0),
            ),
            reverse=True,
        )

        # ------------------------------------------------------------------
        # Build by_cve: aggregate CVEs across all filtered VM docs
        # ------------------------------------------------------------------
        cve_index: Dict[str, Dict[str, Any]] = {}
        for doc in docs:
            for kb in doc.available_kbs:
                for cve_id in kb.cve_ids:
                    if cve_id not in cve_index:
                        cve_index[cve_id] = {
                            "cve_id": cve_id,
                            "severity": kb.severity or "",
                            "cvss_score": kb.highest_cvss,
                            "available_advisory_ids": [kb.advisory_id],
                            "vm_ids": [doc.vm_id],
                            "vm_count": 1,
                        }
                    else:
                        entry = cve_index[cve_id]
                        # Merge advisories without duplicates
                        if kb.advisory_id not in entry["available_advisory_ids"]:
                            entry["available_advisory_ids"].append(kb.advisory_id)
                        # Merge VMs without duplicates
                        if doc.vm_id not in entry["vm_ids"]:
                            entry["vm_ids"].append(doc.vm_id)
                            entry["vm_count"] = len(entry["vm_ids"])
                        # Update CVSS if higher found
                        if kb.highest_cvss is not None:
                            if entry["cvss_score"] is None or kb.highest_cvss > entry["cvss_score"]:
                                entry["cvss_score"] = kb.highest_cvss
                        # Propagate most severe severity seen
                        if SEVERITY_ORDER.get(kb.severity or "", 0) > SEVERITY_ORDER.get(entry["severity"] or "", 0):
                            entry["severity"] = kb.severity

        by_cve = sorted(
            cve_index.values(),
            key=lambda x: (
                SEVERITY_ORDER.get(x.get("severity") or "", 0),
                x.get("cvss_score") or 0.0,
            ),
            reverse=True,
        )

        # ------------------------------------------------------------------
        # Build by_vm: one row per filtered VM doc
        # ------------------------------------------------------------------
        by_vm: List[Dict[str, Any]] = sorted(
            [
                {
                    "vm_id": doc.vm_id,
                    "vm_name": doc.vm_name,
                    "os_type": doc.os_type,
                    "os_family": doc.os_family,
                    "os_name": doc.os_name,
                    "location": doc.location,
                    "resource_group": doc.resource_group,
                    "subscription_id": doc.subscription_id,
                    "unpatched_with_fix": len(doc.available_kbs),
                    "total_unpatched": doc.total_unpatched_cves,
                    "available_patches": doc.total_available_advisories,
                }
                for doc in docs
            ],
            key=lambda x: x.get("total_unpatched", 0),
            reverse=True,
        )

        logger.info(
            "Patch gap query: %d VMs, %d KBs, %d CVEs "
            "(filters: sub=%s, severity=%s, os_type=%s, days=%d)",
            len(by_vm), len(by_kb), len(by_cve),
            subscription_id, severity, os_type, days,
        )

        return StandardResponse.success_response(
            data={
                "summary": fleet_summary_dict,
                "by_kb": list(by_kb),
                "by_cve": list(by_cve),
                "by_vm": by_vm,
            },
            metadata={
                "stale": False,
                "filters_applied": {
                    "subscription_id": subscription_id,
                    "severity": severity,
                    "os_type": os_type,
                    "days": days,
                },
                "counts": {
                    "vms": len(by_vm),
                    "advisories": len(by_kb),
                    "cves": len(by_cve),
                },
            },
        )

    except Exception as e:
        logger.error("Failed to retrieve patch gap data: %s", e)
        return StandardResponse.error_response(error=str(e))
