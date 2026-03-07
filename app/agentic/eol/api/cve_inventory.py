"""CVE Inventory API Router

Provides REST API endpoints for VM vulnerability queries.

Endpoints:
    GET /api/cve/inventory/{vm_id} - Get CVEs affecting a VM
    GET /api/cve/{cve_id}/affected-vms - Get VMs affected by a CVE
"""
from __future__ import annotations

from typing import Optional
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


def _get_cve_vm_service():
    """Lazy import to avoid circular dependency."""
    from main import get_cve_vm_service
    return get_cve_vm_service


@router.get("/cve/inventory/{vm_id}", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_vulnerabilities", timeout_seconds=30)
async def get_vm_vulnerabilities(
    vm_id: str,
    severity_filter: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    min_cvss: Optional[float] = Query(None, description="Minimum CVSS score (0.0-10.0)"),
    sort_by: str = Query(default="cvss_score", description="Sort by: cvss_score, published_date, severity"),
    sort_order: str = Query(default="desc", description="Sort order: asc, desc")
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
        service = await _get_cve_vm_service()
        result = await service.get_vm_vulnerabilities(vm_id)

        if not result:
            raise HTTPException(
                status_code=503,
                detail="No scan data available. Trigger a scan at /api/cve/scan"
            )

        # Apply filters
        cve_details = result.cve_details

        if severity_filter:
            severity_filter = severity_filter.upper()
            cve_details = [c for c in cve_details if c.severity == severity_filter]

        if min_cvss is not None:
            cve_details = [c for c in cve_details if c.cvss_score and c.cvss_score >= min_cvss]

        # Apply sorting
        reverse = (sort_order.lower() == "desc")

        if sort_by == "cvss_score":
            cve_details.sort(key=lambda x: x.cvss_score or 0.0, reverse=reverse)
        elif sort_by == "published_date":
            cve_details.sort(
                key=lambda x: x.published_date or "",
                reverse=reverse
            )
        elif sort_by == "severity":
            # Sort by severity priority: CRITICAL > HIGH > MEDIUM > LOW
            severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
            cve_details.sort(
                key=lambda x: severity_order.get(x.severity, 0),
                reverse=reverse
            )

        # Update result with filtered/sorted data
        result.cve_details = cve_details
        result.total_cves = len(cve_details)

        # Recalculate severity breakdown after filtering
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get vulnerabilities for VM {vm_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve VM vulnerabilities: {str(e)}"
        )


@router.get("/cve/{cve_id}/affected-vms", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_affected_vms", timeout_seconds=30)
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
