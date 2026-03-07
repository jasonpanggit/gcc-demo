"""
CVE API Router

Provides endpoints for CVE search and detail retrieval.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Path

try:
    from models.cve_models import CVESearchRequest, CVESearchResponse, CVEDetailResponse, UnifiedCVE
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ImportError:
    from app.agentic.eol.models.cve_models import CVESearchRequest, CVESearchResponse, CVEDetailResponse, UnifiedCVE
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger


router = APIRouter()
logger = get_logger(__name__)


@router.get("/cve/stats")
@readonly_endpoint(agent_name="cve_stats", timeout_seconds=15)
async def get_cve_stats() -> StandardResponse:
    """Get cached CVE statistics for the UI."""
    try:
        from main import get_cve_service

        cve_service = await get_cve_service()
        cached_count = await cve_service.count_cves({})

        return StandardResponse(
            success=True,
            message="CVE stats retrieved",
            data={
                "cached_count": cached_count,
                "l1_cache": cve_service.get_cache_stats()
            }
        )
    except Exception as e:
        logger.error(f"CVE stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cve/search")
@readonly_endpoint(agent_name="cve_search", timeout_seconds=30)
async def search_cves(request: CVESearchRequest) -> StandardResponse:
    """Search CVEs with advanced filtering.

    Supports multiple filter types:
    - ID: Exact CVE ID match
    - Keyword: Text search in description
    - Severity: Filter by CVSS severity level
    - CVSS Score: Min/max score range
    - Date Range: Published date filters
    - Vendor/Product: Affected product filters
    - Source: Filter by data source
    - Exploit: Filter by exploit availability

    Pagination and sorting supported.

    Args:
        request: CVESearchRequest with filters, pagination, and sorting

    Returns:
        StandardResponse with CVESearchResponse data
    """
    try:
        # Import here to get singleton
        from main import get_cve_service

        cve_service = await get_cve_service()

        # Build filters dict for repository
        filters = {}

        if request.cve_id:
            # Direct ID lookup - use get_cve instead of search
            cve = await cve_service.get_cve(request.cve_id)
            if cve is None:
                return StandardResponse(
                    success=False,
                    message=f"CVE {request.cve_id} not found",
                    data=CVESearchResponse(
                        results=[],
                        total_count=0,
                        offset=0,
                        limit=request.limit,
                        has_more=False
                    ).model_dump()
                )

            return StandardResponse(
                success=True,
                message="CVE found",
                data=CVESearchResponse(
                    results=[cve],
                    total_count=1,
                    offset=0,
                    limit=request.limit,
                    has_more=False
                ).model_dump()
            )

        # Text search
        if request.keyword:
            filters["keyword"] = request.keyword

        # Severity filter
        if request.severity:
            filters["severity"] = request.severity.upper()

        # CVSS score range
        if request.min_score is not None:
            filters["min_score"] = request.min_score
        if request.max_score is not None:
            filters["max_score"] = request.max_score

        # Date range
        if request.published_after:
            filters["published_after"] = request.published_after
        if request.published_before:
            filters["published_before"] = request.published_before

        # Vendor/product filters
        if request.vendor:
            filters["vendor"] = request.vendor
        if request.product:
            filters["product"] = request.product

        # Source filter
        if request.source:
            filters["source"] = request.source

        # Exploit filter (if supported by repository)
        if request.exploit_available is not None:
            filters["exploit_available"] = request.exploit_available

        # Execute search
        results = await cve_service.search_cves(
            filters=filters,
            limit=request.limit,
            offset=request.offset
        )

        total_count = await cve_service.count_cves(filters)
        total_count = max(total_count, request.offset + len(results))
        has_more = request.offset + len(results) < total_count

        response_data = CVESearchResponse(
            results=results,
            total_count=total_count,
            offset=request.offset,
            limit=request.limit,
            has_more=has_more
        )

        logger.info(f"CVE search: {len(results)} results (filters={len(filters)}, offset={request.offset})")

        return StandardResponse(
            success=True,
            message=f"Found {len(results)} CVE(s)",
            data=response_data.model_dump()
        )

    except Exception as e:
        logger.error(f"CVE search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cve/{cve_id}")
@readonly_endpoint(agent_name="cve_detail", timeout_seconds=15)
async def get_cve_detail(
    cve_id: str = Path(..., description="CVE identifier (e.g., CVE-2024-1234)")
) -> StandardResponse:
    """Get detailed information for a specific CVE.

    Uses L1/L2 cache for fast retrieval. Cache hit indicator included in response.

    Args:
        cve_id: CVE identifier

    Returns:
        StandardResponse with CVEDetailResponse data
    """
    try:
        # Import here to get singleton
        from main import get_cve_service

        cve_service = await get_cve_service()
        cve_id = cve_id.upper()

        # Check L1 cache first
        cache_hit = False
        cve = cve_service.cache.get(cve_id)
        if cve:
            cache_hit = True
            logger.debug(f"CVE {cve_id} served from L1 cache")
        else:
            # Will check L2 (Cosmos) and APIs
            cve = await cve_service.get_cve(cve_id)
            # L2 cache hit logged by service

        if cve is None:
            return StandardResponse(
                success=False,
                message=f"CVE {cve_id} not found",
                data=None
            )

        # Find related CVEs (optional - same vendor/product)
        related_cves = []
        if cve.affected_products:
            # Get first product for related search
            first_product = cve.affected_products[0]
            try:
                related = await cve_service.search_cves(
                    filters={
                        "vendor": first_product.vendor,
                        "product": first_product.product
                    },
                    limit=6  # Get 6, exclude self, return 5
                )
                related_cves = [r.cve_id for r in related if r.cve_id != cve_id][:5]
            except Exception as e:
                logger.warning(f"Failed to find related CVEs: {e}")

        response_data = CVEDetailResponse(
            cve=cve,
            related_cves=related_cves,
            cache_hit=cache_hit
        )

        logger.info(f"CVE detail: {cve_id} (cache_hit={cache_hit}, related={len(related_cves)})")

        return StandardResponse(
            success=True,
            message=f"CVE {cve_id} retrieved",
            data=response_data.model_dump()
        )

    except Exception as e:
        logger.error(f"CVE detail retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
