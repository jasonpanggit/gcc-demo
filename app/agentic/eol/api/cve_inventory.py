"""CVE Inventory API Router

Provides REST API endpoints for VM vulnerability queries.

Endpoints:
    GET /api/cve/inventory/{vm_id:path} - Get CVEs affecting a VM
    GET /api/cve/{cve_id}/affected-vms - Get VMs affected by a CVE
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

try:
    from models.cve_models import VMVulnerabilityResponse, CVEAffectedVMsResponse
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import VMVulnerabilityResponse, CVEAffectedVMsResponse
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["CVE Inventory"])

# Simple in-memory cache for VM metadata lookups
_vm_metadata_cache: Dict[str, tuple[Dict[str, Any], datetime]] = {}
_VM_CACHE_TTL_SECONDS = 60  # 1 minute TTL



async def _get_cve_vm_service():
    """Lazy import to avoid circular dependency."""
    from main import get_cve_vm_service
    return await get_cve_vm_service()


async def _get_machine_by_id(vm_id: str, days: int = 90) -> Optional[Dict[str, Any]]:
    """Fetch single VM metadata with caching and optimized queries.

    Args:
        vm_id: The resource ID of the VM to fetch
        days: Look-back window for Arc VM inventory

    Returns:
        Machine metadata dict if found, None otherwise
    """
    global _vm_metadata_cache

    # Check cache first
    vm_id_lower = vm_id.lower()
    if vm_id_lower in _vm_metadata_cache:
        cached_data, cached_time = _vm_metadata_cache[vm_id_lower]
        age = (datetime.utcnow() - cached_time).total_seconds()
        if age < _VM_CACHE_TTL_SECONDS:
            logger.debug(f"VM metadata cache hit for {vm_id} (age: {age:.1f}s)")
            return cached_data

    try:
        from main import get_eol_orchestrator
        from utils.resource_inventory_client import get_resource_inventory_client
        from utils.config import config

        # Parallelize Arc and Azure VM lookups
        async def check_arc_inventory():
            """Check Arc-enabled servers from OS inventory."""
            try:
                orchestrator = get_eol_orchestrator()
                os_result = await orchestrator.agents["os_inventory"].get_os_inventory(days=days)
                all_os: List[Dict[str, Any]] = (
                    os_result.get("data", []) if isinstance(os_result, dict) else []
                )
                for item in all_os:
                    if str(item.get("resource_id", "")).lower() == vm_id_lower:
                        if (
                            str(item.get("computer_type", "")).lower() == "arc-enabled server"
                            or "/microsoft.hybridcompute/machines/" in vm_id_lower
                        ):
                            try:
                                from api.patch_management import _normalize_machine_os_fields
                            except ModuleNotFoundError:
                                from app.agentic.eol.api.patch_management import _normalize_machine_os_fields
                            return _normalize_machine_os_fields({**item, "vm_type": "arc"})
            except Exception as exc:
                logger.debug("Failed to check Arc inventory for VM %s: %s", vm_id, exc)
            return None

        async def check_azure_inventory():
            """Check Azure VMs using targeted resource query."""
            try:
                inv_client = get_resource_inventory_client()
                # Use targeted API - much faster than scanning all VMs!
                vm = await inv_client.get_resource_by_id(
                    vm_id,
                    resource_type="Microsoft.Compute/virtualMachines",
                    subscription_id=config.azure.subscription_id
                )

                if vm:
                    try:
                        from api.patch_management import normalize_os_record
                    except ModuleNotFoundError:
                        from app.agentic.eol.api.patch_management import normalize_os_record

                    sp = vm.get("selected_properties") or {}
                    vm_name = vm.get("resource_name") or vm.get("name")
                    normalized_os = normalize_os_record(
                        sp.get("os_image") or sp.get("os_type") or vm.get("os_name") or "",
                        vm.get("os_version"),
                        sp.get("os_type") or vm.get("os_type"),
                    )

                    return {
                        "resource_id": vm.get("resource_id") or vm.get("id"),
                        "computer": vm_name,
                        "name": vm_name,
                        "resource_group": vm.get("resource_group"),
                        "subscription_id": vm.get("subscription_id"),
                        "location": vm.get("location"),
                        "os_type": normalized_os.get("os_type"),
                        "os_name": normalized_os.get("os_name"),
                        "os_version": normalized_os.get("os_version"),
                        "vm_type": "azure",
                    }
            except Exception as exc:
                logger.debug("Failed to check Azure inventory for VM %s: %s", vm_id, exc)
            return None

        # Run both lookups in parallel
        arc_result, azure_result = await asyncio.gather(
            check_arc_inventory(),
            check_azure_inventory(),
            return_exceptions=True
        )

        # Return first non-None, non-exception result
        result = None
        for r in [arc_result, azure_result]:
            if r and not isinstance(r, Exception):
                result = r
                break

        # Cache the result for 60 seconds
        if result:
            _vm_metadata_cache[vm_id_lower] = (result, datetime.utcnow())

        return result
    except Exception as exc:
        logger.warning("Failed to fetch machine %s: %s", vm_id, exc)
        return None


async def _build_vm_vulnerability_response(
    vm_id: str,
    severity_filter: Optional[str],
    min_cvss: Optional[float],
    sort_by: str,
    sort_order: str,
    offset: int = 0,
    limit: int = 100,
):
    """Build the VM vulnerability response payload for either route shape."""
    service = await _get_cve_vm_service()

    # Parallelize independent API calls
    result, machine = await asyncio.gather(
        service.get_vm_vulnerabilities(vm_id, offset=offset, limit=limit),
        _get_machine_by_id(vm_id, days=90)
    )

    if not result:
        raise HTTPException(
            status_code=503,
            detail="No scan data available. Trigger a scan at /api/cve/scan"
        )

    try:
        if machine:
            result.resource_group = machine.get("resource_group")
            result.subscription_id = machine.get("subscription_id")
            result.os_type = machine.get("os_type")
            result.os_name = machine.get("os_name")
            result.os_version = machine.get("os_version")
            result.location = machine.get("location")
            if not result.vm_name or result.vm_name == vm_id:
                result.vm_name = machine.get("computer") or machine.get("name") or result.vm_name
    except Exception as metadata_error:
        logger.warning(f"Failed to enrich VM {vm_id} metadata: {metadata_error}")

    cve_details = result.cve_details

    if severity_filter:
        severity_filter = severity_filter.upper()
        cve_details = [c for c in cve_details if c.severity == severity_filter]

    if min_cvss is not None:
        cve_details = [c for c in cve_details if c.cvss_score and c.cvss_score >= min_cvss]

    reverse = (sort_order.lower() == "desc")

    if sort_by == "cvss_score":
        cve_details.sort(key=lambda x: x.cvss_score or 0.0, reverse=reverse)
    elif sort_by == "published_date":
        cve_details.sort(
            key=lambda x: x.published_date or "",
            reverse=reverse
        )
    elif sort_by == "severity":
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        cve_details.sort(
            key=lambda x: severity_order.get(x.severity, 0),
            reverse=reverse
        )

    result.cve_details = cve_details

    # Only recompute stats from the current page when filters are active.
    # Without filters the service already provides accurate totals (from scan summary /
    # total_matches metadata), so overwriting them with the page count would show wrong numbers.
    filters_active = severity_filter or min_cvss is not None
    if filters_active:
        result.total_cves = len(cve_details)
        severity_counts = {}
        for cve in cve_details:
            severity = cve.severity
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        result.cves_by_severity = severity_counts

    logger.info(
        f"Retrieved {len(cve_details)} CVEs for VM {vm_id} "
        f"(filters: severity={severity_filter}, min_cvss={min_cvss})"
    )

    return StandardResponse.success_response(
        data=[result.dict()],
        metadata={
            "vm_id": vm_id,
            "filters_applied": {
                "severity": severity_filter,
                "min_cvss": min_cvss
            },
            "sort": {
                "by": sort_by,
                "order": sort_order
            }
        }
    )


def _normalize_vm_source(vm_type: Optional[str]) -> str:
    if vm_type == "arc":
        return "Arc-enabled server"
    if vm_type == "azure-vm":
        return "Azure VM"
    return "Virtual machine"


def _calculate_risk_level(
    total_cves: int,
    critical: int,
    high: int,
    medium: int,
    low: int,
    unpatched_critical: int = 0,
    unpatched_high: int = 0,
    total_unpatched: int = 0,
    has_patch_data: bool = False,
) -> str:
    """Calculate risk level, preferring unpatched counts when patch data is available."""
    if has_patch_data:
        if unpatched_critical > 0: return "Critical"
        if unpatched_high > 0:     return "High"
        if total_unpatched > 0:    return "Medium"
        if total_cves > 0:         return "Low"   # all patched
        return "Healthy"
    # Fallback: raw counts (pre-enrichment scans)
    if critical > 0: return "Critical"
    if high > 0:     return "High"
    if medium > 0:   return "Medium"
    if low > 0 or total_cves > 0: return "Low"
    return "Healthy"


@router.get("/cve/inventory/overview", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_overview", timeout_seconds=120)
async def get_vm_vulnerability_overview(
    days: int = Query(default=90, ge=1, le=365, description="Look-back window for Arc VM inventory")
):
    """Return vulnerability counts for all Azure VMs and Arc-enabled servers."""
    try:
        try:
            from api.patch_management import _list_machines_inventory
        except ModuleNotFoundError:
            from app.agentic.eol.api.patch_management import _list_machines_inventory

        service = await _get_cve_vm_service()

        # Parallelize independent API calls
        machine_result, scan = await asyncio.gather(
            _list_machines_inventory(days=days, include_eol=False),
            service.get_latest_scan()
        )
        machines: List[Dict[str, Any]] = machine_result.get("data", []) if isinstance(machine_result, dict) else []

        match_counts: Dict[str, Dict[str, Any]] = {}
        total_matches = 0

        if scan:
            scan_summaries = getattr(scan, "vm_match_summaries", {}) or {}
            if scan_summaries:
                for vm_id, summary in scan_summaries.items():
                    patch_summary = summary.get("patch_summary") or {}
                    match_counts[vm_id] = {
                        "vm_id": vm_id,
                        "vm_name": summary.get("vm_name") or vm_id,
                        "total_cves": int(summary.get("total_cves", 0)),
                        "critical": int(summary.get("critical", 0)),
                        "high": int(summary.get("high", 0)),
                        "medium": int(summary.get("medium", 0)),
                        "low": int(summary.get("low", 0)),
                        "unpatched_critical": int(patch_summary.get("unpatched_critical", 0)),
                        "unpatched_high": int(patch_summary.get("unpatched_high", 0)),
                        "unpatched_medium": int(patch_summary.get("unpatched_medium", 0)),
                        "unpatched_low": int(patch_summary.get("unpatched_low", 0)),
                        "covered_cves": int(patch_summary.get("covered_cves", 0)),
                        "fixable_cves": int(patch_summary.get("fixable_cves", 0)),
                        "total_unpatched": int(patch_summary.get("total_unpatched", 0)),
                        "has_patch_data": bool(patch_summary),
                    }
                total_matches = sum(int(summary.get("total_cves", 0)) for summary in scan_summaries.values())
            else:
                for match in scan.matches:
                    vm_bucket = match_counts.setdefault(
                        match.vm_id,
                        {
                            "vm_id": match.vm_id,
                            "vm_name": match.vm_name or match.vm_id,
                            "total_cves": 0,
                            "critical": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                        }
                    )
                    vm_bucket["total_cves"] += 1
                    total_matches += 1

                    severity = str(match.severity or "UNKNOWN").upper()
                    if severity == "CRITICAL":
                        vm_bucket["critical"] += 1
                    elif severity == "HIGH":
                        vm_bucket["high"] += 1
                    elif severity == "MEDIUM":
                        vm_bucket["medium"] += 1
                    else:
                        vm_bucket["low"] += 1

        zero_match_ids = [
            resource_id
            for resource_id in (str(machine.get("resource_id") or "") for machine in machines)
            if resource_id and not (match_counts.get(resource_id) or match_counts.get(resource_id.lower()))
        ]
        fallback_summaries: Dict[str, Dict[str, Any]] = {}

        if zero_match_ids:
            try:
                fallback_summaries = await service.get_vm_vulnerability_summaries(
                    zero_match_ids,
                    allow_live_cve_fallback=False,
                    scan=scan,
                )
            except Exception as fallback_error:
                logger.warning("Failed batched inventory-backed summaries for overview: %s", fallback_error)
                fallback_summaries = {}

        overview_rows: List[Dict[str, Any]] = []

        for machine in machines:
            resource_id = str(machine.get("resource_id") or "")
            counts = match_counts.pop(resource_id, None) or match_counts.pop(resource_id.lower(), None) or {
                "vm_id": resource_id,
                "vm_name": machine.get("computer") or machine.get("name") or resource_id,
                "total_cves": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }

            if counts["total_cves"] == 0 and resource_id:
                fallback = fallback_summaries.get(resource_id.lower()) or fallback_summaries.get(resource_id)
                if fallback and int(fallback.get("total_cves", 0)) > 0:
                    counts = {
                        **counts,
                        "total_cves": int(fallback.get("total_cves", 0)),
                        "critical": int(fallback.get("critical", 0)),
                        "high": int(fallback.get("high", 0)),
                        "medium": int(fallback.get("medium", 0)),
                        "low": int(fallback.get("low", 0)),
                    }

            risk_level = _calculate_risk_level(
                total_cves=counts.get("total_cves", 0),
                critical=counts.get("critical", 0),
                high=counts.get("high", 0),
                medium=counts.get("medium", 0),
                low=counts.get("low", 0),
                unpatched_critical=counts.get("unpatched_critical", 0),
                unpatched_high=counts.get("unpatched_high", 0),
                total_unpatched=counts.get("total_unpatched", 0),
                has_patch_data=counts.get("has_patch_data", False),
            )

            overview_rows.append(
                {
                    "vm_id": resource_id,
                    "vm_name": machine.get("computer") or machine.get("name") or counts["vm_name"],
                    "resource_group": machine.get("resource_group"),
                    "subscription_id": machine.get("subscription_id"),
                    "location": machine.get("location"),
                    "os_type": machine.get("os_type"),
                    "os_name": machine.get("os_name"),
                    "os_version": machine.get("os_version"),
                    "vm_type": machine.get("vm_type"),
                    "source_label": _normalize_vm_source(machine.get("vm_type")),
                    "total_cves": counts["total_cves"],
                    "critical": counts["critical"],
                    "high": counts["high"],
                    "medium": counts["medium"],
                    "low": counts["low"],
                    "unpatched_critical": counts.get("unpatched_critical", 0),
                    "unpatched_high": counts.get("unpatched_high", 0),
                    "unpatched_medium": counts.get("unpatched_medium", 0),
                    "unpatched_low": counts.get("unpatched_low", 0),
                    "total_unpatched": counts.get("total_unpatched", 0),
                    "covered_cves": counts.get("covered_cves", 0),
                    "fixable_cves": counts.get("fixable_cves", 0),
                    "has_patch_data": counts.get("has_patch_data", False),
                    "risk_level": risk_level,
                    "has_scan_data": scan is not None,
                    "last_synced": (scan.completed_at or scan.started_at) if scan else None,
                }
            )

        for unmatched in match_counts.values():
            risk_level = _calculate_risk_level(
                total_cves=unmatched.get("total_cves", 0),
                critical=unmatched.get("critical", 0),
                high=unmatched.get("high", 0),
                medium=unmatched.get("medium", 0),
                low=unmatched.get("low", 0),
                unpatched_critical=unmatched.get("unpatched_critical", 0),
                unpatched_high=unmatched.get("unpatched_high", 0),
                total_unpatched=unmatched.get("total_unpatched", 0),
                has_patch_data=unmatched.get("has_patch_data", False),
            )
            overview_rows.append(
                {
                    "vm_id": unmatched["vm_id"],
                    "vm_name": unmatched["vm_name"],
                    "resource_group": None,
                    "subscription_id": None,
                    "location": None,
                    "os_type": None,
                    "os_name": None,
                    "os_version": None,
                    "vm_type": None,
                    "source_label": "Virtual machine",
                    "total_cves": unmatched["total_cves"],
                    "critical": unmatched["critical"],
                    "high": unmatched["high"],
                    "medium": unmatched["medium"],
                    "low": unmatched["low"],
                    "unpatched_critical": unmatched.get("unpatched_critical", 0),
                    "unpatched_high": unmatched.get("unpatched_high", 0),
                    "unpatched_medium": unmatched.get("unpatched_medium", 0),
                    "unpatched_low": unmatched.get("unpatched_low", 0),
                    "total_unpatched": unmatched.get("total_unpatched", 0),
                    "covered_cves": unmatched.get("covered_cves", 0),
                    "fixable_cves": unmatched.get("fixable_cves", 0),
                    "has_patch_data": unmatched.get("has_patch_data", False),
                    "risk_level": risk_level,
                    "has_scan_data": True,
                    "last_synced": (scan.completed_at or scan.started_at) if scan else None,
                }
            )

        overview_rows.sort(
            key=lambda item: (
                -int(item.get("total_cves", 0)),
                -int(item.get("critical", 0)),
                -int(item.get("high", 0)),
                str(item.get("vm_name") or "").lower(),
            )
        )

        vulnerable_vms = sum(1 for item in overview_rows if int(item.get("total_cves", 0)) > 0)
        summary = {
            "scan_available": scan is not None,
            "scan_id": scan.scan_id if scan else None,
            "scan_date": (scan.completed_at or scan.started_at) if scan else None,
            "total_vms": len(overview_rows),
            "vulnerable_vms": vulnerable_vms,
            "healthy_vms": len(overview_rows) - vulnerable_vms,
            "total_cves": sum(int(item.get("total_cves", 0)) for item in overview_rows),
            "arc_count": sum(1 for item in overview_rows if item.get("vm_type") == "arc"),
            "azure_vm_count": sum(1 for item in overview_rows if item.get("vm_type") == "azure-vm"),
        }

        return StandardResponse.success_response(data=overview_rows, metadata=summary)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build VM vulnerability overview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerability overview: {str(e)}"
        )


@router.get("/vm-vulnerability-detail", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_vulnerabilities", timeout_seconds=120)
async def get_vm_vulnerabilities_by_query(
    vm_id: str = Query(..., description="Full VM resource ID"),
    severity_filter: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    min_cvss: Optional[float] = Query(None, description="Minimum CVSS score (0.0-10.0)"),
    sort_by: str = Query(default="cvss_score", description="Sort by: cvss_score, published_date, severity"),
    sort_order: str = Query(default="desc", description="Sort order: asc, desc"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
):
    """Get CVEs affecting a specific VM via query parameter to support slash-containing Azure resource IDs."""
    try:
        return await _build_vm_vulnerability_response(vm_id, severity_filter, min_cvss, sort_by, sort_order, offset=offset, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerabilities: {str(e)}"
        )


@router.get("/cve/inventory/{vm_id:path}", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_vulnerabilities", timeout_seconds=120)
async def get_vm_vulnerabilities(
    vm_id: str,
    severity_filter: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    min_cvss: Optional[float] = Query(None, description="Minimum CVSS score (0.0-10.0)"),
    sort_by: str = Query(default="cvss_score", description="Sort by: cvss_score, published_date, severity"),
    sort_order: str = Query(default="desc", description="Sort order: asc, desc"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
):
    """Get CVEs affecting a specific VM.

    Returns enriched CVE details with severity breakdown, patch availability,
    and sorting/filtering options.

    Requirements: CVE-API-05

    Args:
        vm_id: VM identifier
        severity_filter: Filter by severity level
        min_cvss: Minimum CVSS score filter
        sort_by: Sort field (cvss_score, published_date, severity)
        sort_order: Sort direction (asc, desc)

    Returns:
        StandardResponse with VMVulnerabilityResponse containing:
            - vm_id, vm_name, scan metadata
            - total_cves, cves_by_severity breakdown
            - cve_details list with enrichment

    Raises:
        HTTPException: 404 if VM not found, 503 if no scan data available
    """
    try:
        return await _build_vm_vulnerability_response(vm_id, severity_filter, min_cvss, sort_by, sort_order, offset=offset, limit=limit)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerabilities: {str(e)}"
        )


@router.get("/cve/{cve_id}/affected-vms", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_affected_vms", timeout_seconds=45)
async def get_cve_affected_vms(
    cve_id: str,
    subscription_filter: Optional[str] = Query(None, description="Filter by subscription ID"),
    resource_group_filter: Optional[str] = Query(None, description="Filter by resource group"),
    limit: int = Query(default=100, le=1000, ge=1, description="Maximum VMs to return (1-1000)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset")
):
    """Get VMs affected by a specific CVE.

    Returns list of affected VMs with metadata, patch status, and pagination support.

    Args:
        cve_id: CVE identifier (e.g., CVE-2024-1234)
        subscription_filter: Filter by subscription ID
        resource_group_filter: Filter by resource group name
        limit: Maximum VMs to return
        offset: Pagination offset

    Returns:
        StandardResponse with CVEAffectedVMsResponse containing:
            - cve_id, scan metadata
            - total_vms count
            - affected_vms list with VM details and patch status

    Raises:
        HTTPException: 404 if CVE not found, 503 if no scan data available
    """
    try:
        cve_id = cve_id.upper()
        service = await _get_cve_vm_service()
        result = await service.get_cve_affected_vms(cve_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"CVE {cve_id} not found or has no affected VMs"
            )

        # Apply filters
        affected_vms = result.affected_vms

        if subscription_filter:
            affected_vms = [v for v in affected_vms if v.subscription_id == subscription_filter]

        if resource_group_filter:
            affected_vms = [v for v in affected_vms if v.resource_group.lower() == resource_group_filter.lower()]

        # Apply pagination
        total_after_filter = len(affected_vms)
        affected_vms = affected_vms[offset:offset + limit]

        # Update result with filtered/paginated data
        result.affected_vms = affected_vms
        result.total_vms = total_after_filter

        logger.info(
            f"Retrieved {len(affected_vms)} VMs for CVE {cve_id} "
            f"(offset={offset}, limit={limit}, filters: sub={subscription_filter}, rg={resource_group_filter})"
        )

        return StandardResponse.success_response(
            data=[result.dict()],
            metadata={
                "cve_id": cve_id,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "total": total_after_filter,
                    "has_more": (offset + limit) < total_after_filter
                },
                "filters_applied": {
                    "subscription": subscription_filter,
                    "resource_group": resource_group_filter
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get affected VMs for CVE {cve_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve affected VMs: {str(e)}"
        )
