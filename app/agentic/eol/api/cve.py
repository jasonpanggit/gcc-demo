"""
CVE API Router

Provides endpoints for CVE search and detail retrieval.
"""
import asyncio
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Request

try:
    from models.cve_models import CVESearchRequest, CVESearchResponse, CVEDetailResponse, UnifiedCVE
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import CVESearchRequest, CVESearchResponse, CVEDetailResponse, UnifiedCVE
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger


router = APIRouter()
logger = get_logger(__name__)


def _format_os_display_name(normalized_name: str, fallback_key: Optional[str] = None) -> str:
    normalized_name = str(normalized_name or "").strip()
    if normalized_name == "windows server":
        return "Windows Server"
    if normalized_name == "windows":
        return "Windows"
    if normalized_name == "ubuntu":
        return "Ubuntu"
    if normalized_name == "rhel":
        return "RHEL"
    if normalized_name == "centos":
        return "CentOS"
    if normalized_name == "debian":
        return "Debian"
    if normalized_name:
        return " ".join(part.capitalize() for part in normalized_name.split())

    key = str(fallback_key or "").strip()
    if "::" in key:
        name_part, _ = key.split("::", 1)
        return " ".join(part.capitalize() for part in name_part.split())
    return key or "Unknown OS"


def _build_inventory_cached_filters(identity: dict) -> dict:
    normalized_name = str(identity.get("normalized_name") or "").strip().lower()
    normalized_version = str(identity.get("normalized_version") or "").strip()

    keyword_parts = [part for part in [normalized_name, normalized_version] if part]
    filters = {"keyword": " ".join(keyword_parts).strip()}

    vendor_map = {
        "ubuntu": "ubuntu",
        "windows server": "microsoft",
        "windows": "microsoft",
        "rhel": "redhat",
        "centos": "centos",
        "debian": "debian",
    }
    vendor = vendor_map.get(normalized_name)
    if vendor:
        filters["vendor"] = vendor
    return filters


@router.get("/cve/stats")
@readonly_endpoint(agent_name="cve_stats", timeout_seconds=15)
async def get_cve_stats(request: Request) -> StandardResponse:
    """Get cached CVE statistics for the UI."""
    cve_repo = request.app.state.cve_repo

    summary, os_breakdown = await asyncio.gather(
        cve_repo.get_dashboard_summary(),
        cve_repo.get_os_cve_breakdown(),
        return_exceptions=True,
    )

    errors = []
    if isinstance(summary, Exception):
        logger.error("Summary query failed: %s", summary, exc_info=True)
        summary = {"total_cves": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        errors.append("summary")

    if isinstance(os_breakdown, Exception):
        logger.error("OS breakdown query failed: %s", os_breakdown, exc_info=True)
        os_breakdown = []
        errors.append("os_breakdown")

    # Build per-OS identity stats from os_breakdown (replaces N+1 count_cves)
    os_identities = []
    for entry in os_breakdown:
        os_identities.append({
            "key": entry.get("os_name", "Unknown"),
            "display_name": _format_os_display_name(entry.get("os_name", "")),
            "cached_cve_count": entry.get("total_cve_count", 0),
            "vm_count": entry.get("vm_count", 0),
            "critical_count": entry.get("critical_count", 0),
            "high_count": entry.get("high_count", 0),
        })

    response_data = {
        "cached_count": summary.get("total_cves", 0) if isinstance(summary, dict) else 0,
        "severity_breakdown": {
            "critical": summary.get("critical", 0) if isinstance(summary, dict) else 0,
            "high": summary.get("high", 0) if isinstance(summary, dict) else 0,
            "medium": summary.get("medium", 0) if isinstance(summary, dict) else 0,
            "low": summary.get("low", 0) if isinstance(summary, dict) else 0,
        },
        "os_identities": os_identities,
        "metadata": {
            "partial_errors": errors if errors else None,
        },
    }

    msg = "CVE statistics retrieved (partial data)" if errors else "CVE statistics retrieved"
    return StandardResponse(success=True, data=response_data, message=msg)


@router.post("/cve/search")
@readonly_endpoint(agent_name="cve_search", timeout_seconds=30)
async def search_cves(search_request: CVESearchRequest, request: Request) -> StandardResponse:
    """Search CVEs with advanced filtering.

    Supports multiple filter types:
    - ID: Exact CVE ID match
    - Keyword: Text search in description
    - Severity: Filter by CVSS severity level
    - CVSS Score: Min/max score range
    - Date Range: Published date filters
    - Vendor/Product: Affected product filters
    - Source: Filter by data source

    Pagination supported.

    Args:
        search_request: CVESearchRequest with filters, pagination, and sorting
        request: FastAPI request for app.state access

    Returns:
        StandardResponse with search results
    """
    cve_repo = request.app.state.cve_repo

    # Extract filters from search_request (CVESearchRequest Pydantic model)
    keyword = search_request.keyword
    severity = search_request.severity.upper() if search_request.severity else None
    min_score = search_request.min_score
    vendor = search_request.vendor
    product = search_request.product
    date_from = search_request.published_after
    date_to = search_request.published_before
    source = search_request.source
    limit = search_request.limit or 100
    offset = search_request.offset or 0

    # Parallel: search + count
    results, total = await asyncio.gather(
        cve_repo.search_cves(
            keyword=keyword, severity=severity, min_score=min_score,
            vendor=vendor, product=product,
            date_from=date_from, date_to=date_to,
            source=source, limit=limit, offset=offset,
        ),
        cve_repo.count_cves(
            keyword=keyword, severity=severity, min_score=min_score,
            vendor=vendor, product=product,
            date_from=date_from, date_to=date_to,
            source=source,
        ),
    )

    return StandardResponse(
        success=True,
        data={
            "items": results,
            "total": total,
            "offset": offset,
            "limit": limit,
        },
        count=len(results),
        message=f"Retrieved {len(results)} CVEs" if results else "No CVEs found matching your criteria",
    )


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
