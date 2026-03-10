"""CVE Scan API Router

Provides REST API endpoints for triggering CVE scans and checking scan status.

Endpoints:
    POST /api/cve/scan - Trigger async CVE scan
    GET /api/cve/scan/{scan_id}/status - Get scan status
    GET /api/cve/scan/recent - List recent scans
    DELETE /api/cve/scan/{scan_id} - Delete scan result
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError

try:
    from models.cve_models import CVEScanRequest, CVEScanStatusResponse, ScanResult
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint, write_endpoint
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVEScanRequest, CVEScanStatusResponse, ScanResult
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint, write_endpoint
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)
router = APIRouter(tags=["CVE Scanning"])


async def _get_cve_scanner():
    """Lazy import to avoid circular dependency."""
    from main import get_cve_scanner
    return await get_cve_scanner()


async def _get_scan_repository():
    """Lazy import of the lightweight scan repository for polling endpoints."""
    from main import get_cve_scan_repository
    return await get_cve_scan_repository()


@router.post("/cve/scan", response_model=StandardResponse)
@write_endpoint(agent_name="cve_scan_trigger", timeout_seconds=10)
async def trigger_cve_scan(request: Request):
    """Trigger async CVE inventory scan.

    Returns scan_id immediately. Poll /api/cve/scan/{scan_id}/status for progress.

    Args:
        request: FastAPI request containing scan configuration JSON

    Returns:
        StandardResponse with scan_id and status

    Raises:
        HTTPException: If scanner is disabled or scan fails to start
    """
    if not config.cve_scanner.enable_scanner:
        raise HTTPException(
            status_code=503,
            detail="CVE scanner is disabled. Set CVE_SCANNER_ENABLED=true to enable."
        )

    try:
        payload = await request.json()
        scan_request = CVEScanRequest.model_validate(payload)

        scanner = await _get_cve_scanner()
        scan_id = await scanner.start_scan(scan_request)

        logger.info(f"CVE scan triggered: {scan_id}")

        return StandardResponse(
            success=True,
            data={
                "scan_id": scan_id,
                "status": "pending",
                "message": f"Scan initiated. Check status at /api/cve/scan/{scan_id}/status"
            },
            message="CVE scan initiated"
        )

    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Failed to trigger CVE scan: {e}")
        raise HTTPException(status_code=500, detail=f"Scan failed to start: {str(e)}")


@router.get("/cve/scan/{scan_id}/status", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_scan_status", timeout_seconds=15)
async def get_scan_status(scan_id: str):
    """Get CVE scan status and progress.

    Args:
        scan_id: Scan identifier from trigger_cve_scan

    Returns:
        StandardResponse with scan status, progress, and match count

    Raises:
        HTTPException: If scan not found
    """
    try:
        repository = await _get_scan_repository()
        result = await repository.get_status_summary(scan_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

        # Calculate progress percentage
        progress = 0
        if result["total_vms"] > 0:
            progress = int((result["scanned_vms"] / result["total_vms"]) * 100)

        response = CVEScanStatusResponse(
            scan_id=result["scan_id"],
            status=result["status"],
            progress=progress,
            total_vms=result["total_vms"],
            scanned_vms=result["scanned_vms"],
            matches_found=result["total_matches"],
            started_at=result["started_at"],
            completed_at=result.get("completed_at"),
            error=result.get("error")
        )

        return StandardResponse(
            success=True,
            data=response.dict(),
            message=f"Retrieved status for scan {scan_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan status for {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve scan status: {str(e)}")


@router.get("/cve/scan/recent", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_scan_list", timeout_seconds=15)
async def list_recent_scans(limit: int = Query(default=10, le=100, ge=1)):
    """List recent CVE scans.

    Args:
        limit: Maximum number of scans to return (1-100, default 10)

    Returns:
        StandardResponse with list of recent scans
    """
    try:
        repository = await _get_scan_repository()
        scans = await repository.list_status_summaries(limit=limit)

        return StandardResponse(
            success=True,
            data={
                "scans": list(scans),
                "count": len(scans)
            },
            message="Recent CVE scans retrieved"
        )

    except Exception as e:
        logger.error(f"Failed to list recent scans: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list scans: {str(e)}")


@router.delete("/cve/scan/{scan_id}", response_model=StandardResponse)
@write_endpoint(agent_name="cve_scan_delete", timeout_seconds=5)
async def delete_scan(scan_id: str):
    """Delete a CVE scan result.

    Args:
        scan_id: Scan identifier to delete

    Returns:
        StandardResponse with deletion confirmation

    Raises:
        HTTPException: If scan not found
    """
    try:
        repository = await _get_scan_repository()
        deleted = await repository.delete(scan_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

        logger.info(f"Deleted scan: {scan_id}")

        return StandardResponse(
            success=True,
            data={
                "message": f"Scan {scan_id} deleted successfully"
            },
            message=f"Deleted scan {scan_id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete scan: {str(e)}")
