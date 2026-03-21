"""
Admin API Router for Materialized View Refresh

Provides manual refresh endpoints for materialized views to ensure data freshness.
"""
from fastapi import APIRouter, Request, HTTPException
import asyncio

try:
    from utils.response_models import StandardResponse
    from utils.endpoint_decorators import write_endpoint
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.endpoint_decorators import write_endpoint
    from app.agentic.eol.utils.logging_config import get_logger


router = APIRouter(prefix="/api/admin", tags=["Admin"])
logger = get_logger(__name__)


# Materialized views that need refreshing (mv_cve_dashboard_summary is now a regular VIEW)
MV_DEFINITIONS = {
    "vm_posture": {
        "name": "mv_vm_vulnerability_posture",
        "description": "VM vulnerability overview (used by /vm-vulnerability overview table)",
        "concurrent": True,
    },
    "vm_detail": {
        "name": "mv_vm_cve_detail",
        "description": "Per-VM CVE details with patch status (used by /vm-vulnerability detail view)",
        "concurrent": True,
    },
    "cve_exposure": {
        "name": "mv_cve_exposure",
        "description": "Affected VMs count per CVE",
        "concurrent": True,
    },
    "cve_trending": {
        "name": "mv_cve_trending",
        "description": "CVE publication trend (time-series)",
        "concurrent": True,
    },
    "cve_top_by_score": {
        "name": "mv_cve_top_by_score",
        "description": "Top CVEs by CVSS score",
        "concurrent": True,
    },
}


@router.post("/refresh-views")
@write_endpoint(agent_name="admin_refresh_views", timeout_seconds=120)
async def refresh_materialized_views(
    request: Request,
) -> StandardResponse:
    """
    Manually refresh materialized views.

    Body (optional):
        ["vm_posture", "vm_detail"]  // If empty list or omitted, refreshes all

    Returns:
        StandardResponse with refresh status for each view
    """
    try:
        # Parse request body
        body = await request.json() if request.headers.get("content-type") == "application/json" else []
        views_to_refresh = body if isinstance(body, list) else list(MV_DEFINITIONS.keys())

        # Get PostgreSQL pool via cve_repo
        cve_repo = request.app.state.cve_repo
        pool = cve_repo.pool

        if not pool:
            raise HTTPException(
                status_code=500,
                detail="PostgreSQL connection not available"
            )

        # Validate view names
        invalid_views = [v for v in views_to_refresh if v not in MV_DEFINITIONS]
        if invalid_views:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid view names: {invalid_views}. Valid: {list(MV_DEFINITIONS.keys())}"
            )

        logger.info(f"Starting materialized view refresh for: {views_to_refresh}")

        # Refresh each view
        results = {}
        for view_key in views_to_refresh:
            view_def = MV_DEFINITIONS[view_key]
            view_name = view_def["name"]
            concurrent = view_def["concurrent"]

            try:
                async with pool.acquire() as conn:
                    sql = f"REFRESH MATERIALIZED VIEW {'CONCURRENTLY' if concurrent else ''} {view_name}"
                    logger.info(f"Refreshing {view_name}...")

                    start_time = asyncio.get_event_loop().time()
                    await conn.execute(sql)
                    elapsed = asyncio.get_event_loop().time() - start_time

                    results[view_key] = {
                        "status": "success",
                        "view": view_name,
                        "description": view_def["description"],
                        "elapsed_seconds": round(elapsed, 2),
                    }
                    logger.info(f"✅ Refreshed {view_name} in {elapsed:.2f}s")

            except Exception as e:
                logger.error(f"Failed to refresh {view_name}: {e}")
                results[view_key] = {
                    "status": "failed",
                    "view": view_name,
                    "description": view_def["description"],
                    "error": str(e),
                }

        # Summary
        success_count = sum(1 for r in results.values() if r["status"] == "success")
        total_count = len(results)

        return StandardResponse(
            success=success_count == total_count,
            message=f"Refreshed {success_count}/{total_count} materialized views",
            data={
                "results": results,
                "summary": {
                    "total": total_count,
                    "success": success_count,
                    "failed": total_count - success_count,
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MV refresh failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh views: {str(e)}"
        )


@router.get("/refresh-views/status")
async def get_mv_refresh_status(request: Request) -> StandardResponse:
    """
    Get current materialized view metadata (last refresh time, size, etc).

    Returns:
        StandardResponse with MV status for all views
    """
    try:
        cve_repo = request.app.state.cve_repo
        pool = cve_repo.pool

        if not pool:
            raise HTTPException(
                status_code=500,
                detail="PostgreSQL connection not available"
            )

        async with pool.acquire() as conn:
            # Query pg_matviews for metadata
            rows = await conn.fetch("""
                SELECT
                    matviewname,
                    schemaname,
                    ispopulated,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) AS size
                FROM pg_matviews
                WHERE schemaname = 'public'
                  AND matviewname LIKE 'mv_%'
                ORDER BY matviewname;
            """)

            mv_status = {}
            for row in rows:
                mv_name = row["matviewname"]
                # Find matching key in MV_DEFINITIONS
                view_key = next((k for k, v in MV_DEFINITIONS.items() if v["name"] == mv_name), None)

                mv_status[mv_name] = {
                    "key": view_key,
                    "populated": row["ispopulated"],
                    "size": row["size"],
                    "description": MV_DEFINITIONS[view_key]["description"] if view_key else "Unknown",
                }

            # Note about mv_cve_dashboard_summary
            mv_status["mv_cve_dashboard_summary"] = {
                "key": "dashboard_summary",
                "type": "regular_view",
                "description": "Replaced with regular VIEW - always fresh, no refresh needed",
                "populated": True,
            }

            return StandardResponse(
                success=True,
                message="Materialized view status retrieved",
                data={"views": mv_status}
            )

    except Exception as e:
        logger.error(f"Failed to get MV status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get view status: {str(e)}"
        )
