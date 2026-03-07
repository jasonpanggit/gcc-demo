"""
CVE Dashboard API Router

Provides aggregated metrics endpoint for CVE analytics dashboard.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

try:
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import readonly_endpoint
    from utils.logging_config import get_logger
except ImportError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import readonly_endpoint
    from app.agentic.eol.utils.logging_config import get_logger


router = APIRouter()
logger = get_logger(__name__)


# Simple in-memory cache for dashboard data (5-minute TTL)
_dashboard_cache = {}
_cache_ttl = 300  # 5 minutes in seconds


def _get_cache_key(time_range: int, severity: Optional[str]) -> str:
    """Generate cache key for dashboard query."""
    # Round timestamp to 5-minute bucket
    now = datetime.now(timezone.utc)
    bucket = (now.timestamp() // _cache_ttl) * _cache_ttl
    return f"dashboard:{time_range}:{severity}:{bucket}"


def _get_cached_data(cache_key: str) -> Optional[dict]:
    """Get data from cache if available and fresh."""
    if cache_key in _dashboard_cache:
        data, timestamp = _dashboard_cache[cache_key]
        age = datetime.now(timezone.utc).timestamp() - timestamp
        if age < _cache_ttl:
            logger.debug(f"Dashboard cache hit: {cache_key}")
            return data
    return None


def _set_cached_data(cache_key: str, data: dict):
    """Store data in cache with timestamp."""
    _dashboard_cache[cache_key] = (data, datetime.now(timezone.utc).timestamp())

    # Simple cache cleanup: remove old entries (keep last 20)
    if len(_dashboard_cache) > 20:
        oldest_key = min(_dashboard_cache.keys(), key=lambda k: _dashboard_cache[k][1])
        del _dashboard_cache[oldest_key]


@router.get("/dashboard")
@readonly_endpoint(agent_name="cve_dashboard", timeout_seconds=30)
async def get_dashboard_metrics(
    time_range: int = Query(30, description="Days to look back (30, 90, or 365)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, MEDIUM, LOW)")
) -> StandardResponse:
    """
    Get aggregated CVE dashboard metrics.

    Returns comprehensive analytics including:
    - summary: Total and per-severity CVE counts with MTTP
    - trending: CVE count over time (time series)
    - top_cves: Top 10 CVEs by VM exposure
    - vm_posture: Top 20 VMs by vulnerability
    - aging: CVE aging distribution
    - metadata: Timestamp, filters applied

    Args:
        time_range: Days to look back (30, 90, or 365)
        severity: Optional severity filter (CRITICAL, HIGH, MEDIUM, LOW)

    Returns:
        StandardResponse with aggregated dashboard data
    """
    try:
        # Validate query params
        if time_range not in [30, 90, 365]:
            raise HTTPException(
                status_code=400,
                detail="time_range must be 30, 90, or 365"
            )

        if severity and severity not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            raise HTTPException(
                status_code=400,
                detail="severity must be CRITICAL, HIGH, MEDIUM, or LOW"
            )

        # Check cache
        cache_key = _get_cache_key(time_range, severity)
        cached_data = _get_cached_data(cache_key)

        if cached_data:
            return StandardResponse(
                success=True,
                message="Dashboard metrics retrieved from cache",
                data=cached_data,
                cached=True
            )

        # Import analytics service
        from main import get_cve_analytics

        analytics = await get_cve_analytics()

        # Execute all queries in parallel
        logger.info(f"Fetching dashboard metrics: time_range={time_range}, severity={severity}")

        try:
            summary_stats, trending_data, top_cves, vm_posture, aging_dist, mttp = await asyncio.gather(
                analytics.get_summary_stats(time_range, severity),
                analytics.get_trending_data(time_range, severity),
                analytics.get_top_cves_by_exposure(severity, limit=10),
                analytics.get_vm_vulnerability_posture(severity),
                analytics.get_aging_distribution(severity),
                analytics.calculate_mttp(time_range),
                return_exceptions=True  # Don't fail entire request if one query fails
            )

            # Check for exceptions and log them
            errors = []
            if isinstance(summary_stats, Exception):
                logger.error(f"Summary stats query failed: {summary_stats}")
                summary_stats = {"total_cves": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
                errors.append("summary_stats")

            if isinstance(trending_data, Exception):
                logger.error(f"Trending data query failed: {trending_data}")
                trending_data = []
                errors.append("trending_data")

            if isinstance(top_cves, Exception):
                logger.error(f"Top CVEs query failed: {top_cves}")
                top_cves = []
                errors.append("top_cves")

            if isinstance(vm_posture, Exception):
                logger.error(f"VM posture query failed: {vm_posture}")
                vm_posture = []
                errors.append("vm_posture")

            if isinstance(aging_dist, Exception):
                logger.error(f"Aging distribution query failed: {aging_dist}")
                aging_dist = {"0-7_days": 0, "8-30_days": 0, "31-90_days": 0, "90+_days": 0}
                errors.append("aging_distribution")

            if isinstance(mttp, Exception):
                logger.error(f"MTTP calculation failed: {mttp}")
                mttp = 0.0
                errors.append("mttp")

        except Exception as e:
            logger.error(f"Dashboard query execution failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch dashboard metrics: {str(e)}"
            )

        # Add MTTP to summary
        summary_stats["mttp_days"] = mttp

        # Build response
        dashboard_data = {
            "summary": summary_stats,
            "trending": trending_data,
            "top_cves": top_cves,
            "vm_posture": vm_posture,
            "aging": aging_dist,
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "time_range_days": time_range,
                "severity_filter": severity,
                "partial_errors": errors if errors else None
            }
        }

        # Cache result
        _set_cached_data(cache_key, dashboard_data)

        return StandardResponse(
            success=True,
            message="Dashboard metrics retrieved successfully",
            data=dashboard_data,
            cached=False
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Dashboard metrics retrieval failed: {str(e)}"
        )
