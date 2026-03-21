"""CVE Inventory API Router

Provides REST API endpoints for VM vulnerability queries.

Endpoints:
    GET /api/cve/inventory/{vm_id:path} - Get CVEs affecting a VM
    GET /api/cve/{cve_id}/affected-vms - Get VMs affected by a CVE
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, Depends

try:
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
    from utils.repository_state import get_or_init_repository
    from utils.normalization import normalize_os_record
except ModuleNotFoundError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.repository_state import get_or_init_repository
    from app.agentic.eol.utils.normalization import normalize_os_record

logger = get_logger(__name__)
router = APIRouter(tags=["CVE Inventory"])



async def _build_vm_vulnerability_response(
    request: Request,
    vm_id: str,
    severity_filter: Optional[str],
    min_cvss: Optional[float],
    sort_by: str,
    sort_order: str,
    offset: int = 0,
    limit: int = 100,
):
    """Build the VM vulnerability response payload using cve_repo + inventory_repo.

    Eliminates BH-003 (dual Arc+Azure parallel lookup) by using inventory_repo.get_vm_by_id()
    and cve_repo.get_vm_cve_matches() directly.
    """
    cve_repo = get_or_init_repository(request.app, "cve_repo")
    inventory_repo = get_or_init_repository(request.app, "inventory_repo")

    # Fetch VM metadata from inventory_repo PK lookup
    vm_data = await inventory_repo.get_vm_by_id(vm_id)
    if vm_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"VM {vm_id} not found",
        )

    # Normalize severity filter for SQL
    severity_sql = severity_filter.upper() if severity_filter else None

    # Parallel: fetch CVE matches + total count
    matches_result, total_result = await asyncio.gather(
        cve_repo.get_vm_cve_matches(vm_id, severity=severity_sql, limit=limit, offset=offset),
        cve_repo.count_vm_cve_matches(vm_id, severity=severity_sql),
    )

    matches: List[Dict[str, Any]] = matches_result
    total: int = total_result

    # Apply min_cvss filter (not supported at SQL level)
    if min_cvss is not None:
        matches = [m for m in matches if (m.get("cvss_score") or 0.0) >= min_cvss]

    # Apply sort
    reverse = sort_order.lower() == "desc"
    if sort_by == "cvss_score":
        matches.sort(key=lambda x: x.get("cvss_score") or 0.0, reverse=reverse)
    elif sort_by == "published_date":
        matches.sort(key=lambda x: x.get("published_date") or "", reverse=reverse)
    elif sort_by == "severity":
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        matches.sort(
            key=lambda x: severity_order.get(str(x.get("severity", "UNKNOWN")).upper(), 0),
            reverse=reverse,
        )

    logger.info(
        "Retrieved %d CVEs for VM %s (filters: severity=%s, min_cvss=%s)",
        len(matches), vm_id, severity_filter, min_cvss,
    )

    # Calculate pagination metadata
    has_more = (offset + limit) < total

    response_data = {
        "vm_id": vm_data["resource_id"],
        "vm_name": vm_data.get("vm_name", ""),
        "os_name": vm_data.get("os_name", ""),
        "os_version": vm_data.get("os_version", ""),
        "os_type": vm_data.get("os_type", ""),
        "resource_group": vm_data.get("resource_group", ""),
        "subscription_id": vm_data.get("subscription_id", ""),
        "location": vm_data.get("location", ""),
        "scan_date": vm_data.get("last_scan_date"),
        # JavaScript expects these field names
        "cve_details": matches,
        "total_cves": total,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        },
        "patch_coverage": {
            "installed_patch_entries": [],  # TODO: fetch from patch repository
            "available_patch_entries": [],
        },
        # Keep legacy fields for backward compatibility
        "items": matches,
        "total": total,
        "offset": offset,
        "limit": limit,
    }

    return StandardResponse.success_response(
        data=response_data,
        metadata={
            "vm_id": vm_id,
            "filters_applied": {
                "severity": severity_filter,
                "min_cvss": min_cvss,
            },
            "sort": {
                "by": sort_by,
                "order": sort_order,
            },
        },
    )


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


@router.get("/inventory/overview")
# TODO: Re-enable decorator after fixing FastAPI signature inspection issue
# @readonly_endpoint(agent_name="cve_vm_overview", timeout_seconds=120)
async def get_vm_vulnerability_overview(
    request: Request,
) -> StandardResponse:
    """Return vulnerability counts for all Azure VMs and Arc-enabled servers.

    Uses mv_vm_vulnerability_posture materialized view via cve_repo.
    Eliminates BH-002 (3-query aggregate with O(N) in-memory loop) and
    BH-003 (dual Arc+Azure parallel lookup).

    Query Parameters:
        days: Look-back window (kept for API compat) - currently unused
    """
    try:
        cve_repo = request.app.state.cve_repo

        # Parallel MV reads -- partial success pattern
        posture_result, os_breakdown_result = await asyncio.gather(
            cve_repo.get_vm_posture_summary(limit=500),
            cve_repo.get_os_cve_breakdown(),
            return_exceptions=True,
        )

        errors: List[str] = []

        if isinstance(posture_result, Exception):
            logger.error("VM posture query failed: %s", posture_result)
            posture_result = []
            errors.append("vm_posture")

        if isinstance(os_breakdown_result, Exception):
            logger.error("OS CVE breakdown query failed: %s", os_breakdown_result)
            os_breakdown_result = []
            errors.append("os_breakdown")

        posture_data: List[Dict[str, Any]] = posture_result

        # Build frozen-key response: machines list with OS normalization
        machines: List[Dict[str, Any]] = []
        for row in posture_data:
            risk_level = row.get("risk_level") or _calculate_risk_level(
                total_cves=row.get("total_cves", 0),
                critical=row.get("critical", 0),
                high=row.get("high", 0),
                medium=row.get("medium", 0),
                low=row.get("low", 0),
            )

            # Apply OS normalization like patch management does
            normalized = normalize_os_record(
                row.get("os_name"),
                row.get("os_version"),
                row.get("os_type"),
            )

            machines.append({
                "vm_id": row.get("vm_id", ""),
                "vm_name": row.get("vm_name", ""),
                "os_name": row.get("os_name", ""),
                "normalized_os_name": normalized.get("normalized_os_name"),
                "normalized_os_version": normalized.get("normalized_os_version"),
                "risk_level": risk_level,
                "total_cves": row.get("total_cves", 0),
                "critical": row.get("critical", 0),
                "high": row.get("high", 0),
                "eol_status": row.get("eol_status"),
            })

        # Build scan_summary aggregate
        scan_summary: Dict[str, Any] = {
            "total_machines": len(posture_data),
            "total_cves": sum(m.get("total_cves", 0) for m in posture_data),
            "critical": sum(m.get("critical", 0) for m in posture_data),
            "high": sum(m.get("high", 0) for m in posture_data),
        }

        response_data: Dict[str, Any] = {
            "machines": machines,
            "scan_summary": scan_summary,
            "total_machines": len(posture_data),
        }

        msg = "VM vulnerability overview retrieved"
        if errors:
            msg += " (partial data)"

        return StandardResponse(
            success=True,
            data=response_data,
            message=msg,
            metadata={
                "partial_errors": errors if errors else None,
                "os_breakdown": os_breakdown_result,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to build VM vulnerability overview: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerability overview: {str(e)}",
        )


@router.get("/vm-vulnerability-detail", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_vulnerabilities", timeout_seconds=120)
async def get_vm_vulnerabilities_by_query(
    request: Request,
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
        return await _build_vm_vulnerability_response(request, vm_id, severity_filter, min_cvss, sort_by, sort_order, offset=offset, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerabilities: {str(e)}"
        )


@router.get("/inventory/{vm_id:path}", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_vulnerabilities", timeout_seconds=120)
async def get_vm_vulnerabilities(
    request: Request,
    vm_id: str,
    severity_filter: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    min_cvss: Optional[float] = Query(None, description="Minimum CVSS score (0.0-10.0)"),
    sort_by: str = Query(default="cvss_score", description="Sort by: cvss_score, published_date, severity"),
    sort_order: str = Query(default="desc", description="Sort order: asc, desc"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
):
    """Get CVEs affecting a specific VM.

    Returns CVE match details from mv_vm_cve_detail with severity breakdown,
    sorting/filtering options, and pagination.

    Args:
        request: FastAPI request for app.state access
        vm_id: VM identifier (Azure resource ID)
        severity_filter: Filter by severity level
        min_cvss: Minimum CVSS score filter
        sort_by: Sort field (cvss_score, published_date, severity)
        sort_order: Sort direction (asc, desc)

    Returns:
        StandardResponse with vm_id, vm_name, os_name, items list, total, offset, limit

    Raises:
        HTTPException: 404 if VM not found
    """
    try:
        return await _build_vm_vulnerability_response(request, vm_id, severity_filter, min_cvss, sort_by, sort_order, offset=offset, limit=limit)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerabilities: {str(e)}"
        )


@router.get("/{cve_id}/affected-vms", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_affected_vms", timeout_seconds=45)
async def get_cve_affected_vms(
    request: Request,
    cve_id: str,
    subscription_filter: Optional[str] = Query(None, alias="subscription_id", description="Filter by subscription ID"),
    resource_group_filter: Optional[str] = Query(None, alias="resource_group", description="Filter by resource group"),
    limit: int = Query(default=100, le=1000, ge=1, description="Maximum VMs to return (1-1000)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """Get VMs affected by a specific CVE.

    Uses cve_repo.get_cve_affected_vms() which reads from mv_vm_cve_detail + vms
    with server-side filtering by subscription_id and resource_group.

    Args:
        request: FastAPI request for app.state access
        cve_id: CVE identifier (e.g., CVE-2024-1234)
        subscription_filter: Filter by subscription ID
        resource_group_filter: Filter by resource group name
        limit: Maximum VMs to return
        offset: Pagination offset

    Returns:
        StandardResponse with items list, cve_id, total, offset, limit

    Raises:
        HTTPException: 404 if CVE not found
    """
    try:
        cve_id = cve_id.upper()
        cve_repo = request.app.state.cve_repo

        vms = await cve_repo.get_cve_affected_vms(
            cve_id,
            subscription_id=subscription_filter,
            resource_group=resource_group_filter,
            limit=limit,
            offset=offset,
        )

        logger.info(
            "Retrieved %d affected VMs for CVE %s (offset=%d, limit=%d)",
            len(vms), cve_id, offset, limit,
        )

        response_data = {
            "items": vms,
            "total": len(vms),
            "offset": offset,
            "limit": limit,
            "cve_id": cve_id,
        }

        return StandardResponse(
            success=True,
            data=response_data,
            message=f"Retrieved {len(vms)} affected VMs",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get affected VMs for CVE %s: %s", cve_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve affected VMs: {str(e)}",
        )
