"""CVE Patches API Router

Provides REST API endpoint for CVE-to-patch mapping.

Endpoints:
    GET /api/cve/patches/{cve_id} - Get applicable patches for a CVE
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

try:
    from models.cve_models import CVEPatchMapping
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVEPatchMapping
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["CVE Patches"])


def _get_cve_patch_mapper():
    """Lazy import to avoid circular dependency."""
    from main import get_cve_patch_mapper
    return get_cve_patch_mapper


@router.get("/cve/patches/{cve_id}", response_model=StandardResponse)
@readonly_endpoint(agent_name="cve_patches", timeout_seconds=15)
async def get_cve_patches(
    cve_id: str,
    subscription_ids: Optional[str] = Query(None, description="Comma-separated subscription IDs")
):
    """Get applicable patches for a CVE.

    Returns patches ranked by priority (CVSS score + exposure count).
    Handles multi-patch scenarios where multiple patches fix the same CVE.

    Args:
        cve_id: CVE identifier (e.g., CVE-2024-1234)
        subscription_ids: Optional comma-separated subscription IDs to filter patches

    Returns:
        StandardResponse with CVEPatchMapping containing:
            - patches: List of applicable patches with metadata
            - priority_score: 0-100 priority ranking
            - total_affected_vms: Exposure count from scan data
            - recommendation: Human-readable patching guidance

    Raises:
        HTTPException: If CVE not found or query fails
    """
    try:
        cve_id = cve_id.upper()
        mapper = await _get_cve_patch_mapper()

        # Parse subscription IDs
        subs = subscription_ids.split(",") if subscription_ids else None

        # Get patch mapping
        mapping = await mapper.get_patches_for_cve(cve_id, subs)

        logger.info(f"Retrieved {len(mapping.patches)} patches for {cve_id}")

        return StandardResponse.success(mapping.dict())

    except Exception as e:
        logger.error(f"Failed to get patches for {cve_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve patches: {str(e)}"
        )
