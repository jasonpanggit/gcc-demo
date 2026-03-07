"""CVE Inventory API Router

Provides REST API endpoints for VM vulnerability queries.

Endpoints:
    GET /api/cve/inventory/{vm_id} - Get CVEs affecting a VM
    GET /api/cve/{cve_id}/affected-vms - Get VMs affected by a CVE
"""
from __future__ import annotations

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


def _get_cve_vm_service():
    """Lazy import to avoid circular dependency."""
    from main import get_cve_vm_service
    return get_cve_vm_service


def _normalize_vm_source(vm_type: Optional[str]) -> str:
    if vm_type == "arc":
        return "Arc-enabled server"
    if vm_type == "azure-vm":
        return "Azure VM"
    return "Virtual machine"


def _calculate_risk_level(total_cves: int, critical: int, high: int, medium: int, low: int) -> str:
    if critical > 0:
        return "Critical"
    if high > 0:
        return "High"
    if medium > 0:
        return "Medium"
    if low > 0 or total_cves > 0:
        return "Low"
    return "Healthy"


@router.get("/cve/inventory/overview", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_vm_overview", timeout_seconds=30)
async def get_vm_vulnerability_overview(
    days: int = Query(default=90, ge=1, le=365, description="Look-back window for Arc VM inventory")
):
    """Return vulnerability counts for all Azure VMs and Arc-enabled servers."""
    try:
        try:
            from api.patch_management import list_machines
        except ModuleNotFoundError:
            from app.agentic.eol.api.patch_management import list_machines

        service = await _get_cve_vm_service()
        machine_result = await list_machines(days=days)
        machines: List[Dict[str, Any]] = machine_result.get("data", []) if isinstance(machine_result, dict) else []
        scan = await service.get_latest_scan()

        match_counts: Dict[str, Dict[str, Any]] = {}
        total_matches = 0

        if scan:
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

        overview_rows: List[Dict[str, Any]] = []

        for machine in machines:
            resource_id = str(machine.get("resource_id") or "")
            counts = match_counts.pop(resource_id, None) or {
                "vm_id": resource_id,
                "vm_name": machine.get("computer") or machine.get("name") or resource_id,
                "total_cves": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }

            risk_level = _calculate_risk_level(
                counts["total_cves"],
                counts["critical"],
                counts["high"],
                counts["medium"],
                counts["low"],
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
                    "risk_level": risk_level,
                    "has_scan_data": scan is not None,
                }
            )

        for unmatched in match_counts.values():
            risk_level = _calculate_risk_level(
                unmatched["total_cves"],
                unmatched["critical"],
                unmatched["high"],
                unmatched["medium"],
                unmatched["low"],
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
                    "risk_level": risk_level,
                    "has_scan_data": True,
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
            "total_cves": total_matches,
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

        try:
            try:
                from api.patch_management import list_machines
            except ModuleNotFoundError:
                from app.agentic.eol.api.patch_management import list_machines

            machine_result = await list_machines(days=90)
            machines = machine_result.get("data", []) if isinstance(machine_result, dict) else []
            machine = next((item for item in machines if str(item.get("resource_id") or "") == vm_id), None)
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
