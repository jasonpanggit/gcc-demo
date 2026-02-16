"""
SRE Audit Trail API Router

Provides endpoints for querying and managing SRE operation audit logs.
Audit events are persisted to Cosmos DB with 90-day TTL.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

try:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.response_models import StandardResponse
except ModuleNotFoundError:
    from utils.logger import get_logger
    from utils.response_models import StandardResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sre-audit", tags=["SRE Audit Trail"])


class AuditEntry(BaseModel):
    """Audit log entry model"""
    id: str
    timestamp: str
    operation: str
    resource_id: Optional[str]
    success: bool
    details: dict
    caller: str


@router.get("/trail", response_model=StandardResponse)
async def get_audit_trail(
    operation: Optional[str] = Query(None, description="Filter by operation type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    hours: int = Query(24, description="Hours to look back (default: 24)", ge=1, le=720),
    limit: int = Query(100, description="Maximum entries to return", ge=1, le=1000)
):
    """
    Query SRE operation audit trail from Cosmos DB

    Returns audit events with optional filtering by operation, resource, and success status.
    """
    try:
        # Import cosmos_cache to query audit_trail container
        try:
            from app.agentic.eol.utils.cosmos_cache import cosmos_cache
        except ModuleNotFoundError:
            from utils.cosmos_cache import cosmos_cache

        cosmos_cache._ensure_initialized()

        if not cosmos_cache.initialized:
            return StandardResponse(
                success=False,
                message="Cosmos DB not available",
                data={
                    "note": "Audit trail requires Cosmos DB configuration",
                    "entries": []
                }
            )

        # Get audit_trail container
        container = cosmos_cache.get_container(
            container_id="audit_trail",
            partition_path="/operation",
            offer_throughput=400,
            default_ttl=7776000  # 90 days
        )

        # Build query
        query_parts = ["SELECT * FROM c"]
        query_params = []
        conditions = []

        # Add time filter
        cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        conditions.append("c.timestamp >= @cutoff_time")
        query_params.append({"name": "@cutoff_time", "value": cutoff_time})

        # Add operation filter
        if operation:
            conditions.append("c.operation = @operation")
            query_params.append({"name": "@operation", "value": operation})

        # Add resource_id filter
        if resource_id:
            conditions.append("CONTAINS(c.resource_id, @resource_id)")
            query_params.append({"name": "@resource_id", "value": resource_id})

        # Add success filter
        if success is not None:
            conditions.append("c.success = @success")
            query_params.append({"name": "@success", "value": success})

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        # Add ordering and limit
        query_parts.append("ORDER BY c.timestamp DESC")
        query_parts.append(f"OFFSET 0 LIMIT {limit}")

        query = " ".join(query_parts)

        # Execute query
        items = list(container.query_items(
            query=query,
            parameters=query_params,
            enable_cross_partition_query=True
        ))

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(items)} audit entries",
            data={
                "entries": items,
                "total": len(items),
                "filters": {
                    "operation": operation,
                    "resource_id": resource_id,
                    "success": success,
                    "hours": hours
                }
            }
        )

    except Exception as e:
        logger.error(f"Error querying audit trail: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Error querying audit trail: {str(e)}",
            data={"entries": []}
        )


@router.get("/operations", response_model=StandardResponse)
async def get_audit_operations():
    """
    Get list of distinct operation types in audit trail

    Returns all unique operation names for filtering.
    """
    try:
        from app.agentic.eol.utils.cosmos_cache import cosmos_cache

        cosmos_cache._ensure_initialized()

        if not cosmos_cache.initialized:
            return StandardResponse(
                success=False,
                message="Cosmos DB not available",
                data={"operations": []}
            )

        container = cosmos_cache.get_container(
            container_id="audit_trail",
            partition_path="/operation",
            offer_throughput=400,
            default_ttl=7776000
        )

        # Query distinct operations
        query = "SELECT DISTINCT VALUE c.operation FROM c"
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))

        return StandardResponse(
            success=True,
            message=f"Found {len(items)} distinct operations",
            data={"operations": sorted(items)}
        )

    except Exception as e:
        logger.error(f"Error querying operations: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Error querying operations: {str(e)}",
            data={"operations": []}
        )


@router.get("/stats", response_model=StandardResponse)
async def get_audit_stats(
    hours: int = Query(24, description="Hours to look back", ge=1, le=720)
):
    """
    Get audit trail statistics

    Returns success/failure counts, top operations, and top resources.
    """
    try:
        from app.agentic.eol.utils.cosmos_cache import cosmos_cache

        cosmos_cache._ensure_initialized()

        if not cosmos_cache.initialized:
            return StandardResponse(
                success=False,
                message="Cosmos DB not available",
                data={"stats": {}}
            )

        container = cosmos_cache.get_container(
            container_id="audit_trail",
            partition_path="/operation",
            offer_throughput=400,
            default_ttl=7776000
        )

        cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        # Query statistics
        stats_query = """
        SELECT
            COUNT(1) as total_operations,
            SUM(c.success ? 1 : 0) as successful_operations,
            SUM(c.success ? 0 : 1) as failed_operations
        FROM c
        WHERE c.timestamp >= @cutoff_time
        """

        stats_result = list(container.query_items(
            query=stats_query,
            parameters=[{"name": "@cutoff_time", "value": cutoff_time}],
            enable_cross_partition_query=True
        ))

        stats = stats_result[0] if stats_result else {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0
        }

        # Query top operations
        top_ops_query = """
        SELECT TOP 10 c.operation, COUNT(1) as count
        FROM c
        WHERE c.timestamp >= @cutoff_time
        GROUP BY c.operation
        ORDER BY COUNT(1) DESC
        """

        top_operations = list(container.query_items(
            query=top_ops_query,
            parameters=[{"name": "@cutoff_time", "value": cutoff_time}],
            enable_cross_partition_query=True
        ))

        return StandardResponse(
            success=True,
            message="Audit statistics retrieved",
            data={
                "stats": stats,
                "top_operations": top_operations,
                "period_hours": hours
            }
        )

    except Exception as e:
        logger.error(f"Error querying audit stats: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Error querying audit stats: {str(e)}",
            data={"stats": {}}
        )
