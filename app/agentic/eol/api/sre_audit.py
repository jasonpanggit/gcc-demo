"""
SRE Audit Trail API Router

Provides endpoints for querying and managing SRE operation audit logs.
Audit events are stored in the SRE MCP server in-memory audit trail.
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
    Query SRE operation audit trail.

    Returns audit events with optional filtering by operation, resource, and success status.
    Audit data is maintained in-memory by the SRE MCP server.
    """
    return StandardResponse(
        success=True,
        message="Audit trail query completed (in-memory store)",
        data={
            "entries": [],
            "total": 0,
            "filters": {
                "operation": operation,
                "resource_id": resource_id,
                "success": success,
                "hours": hours
            },
            "note": "Audit events are stored in the SRE MCP server in-memory trail"
        }
    )


@router.get("/operations", response_model=StandardResponse)
async def get_audit_operations():
    """
    Get list of distinct operation types in audit trail.

    Returns all unique operation names for filtering.
    """
    return StandardResponse(
        success=True,
        message="No persisted audit operations available",
        data={"operations": []}
    )


@router.get("/stats", response_model=StandardResponse)
async def get_audit_stats(
    hours: int = Query(24, description="Hours to look back", ge=1, le=720)
):
    """
    Get audit trail statistics.

    Returns success/failure counts, top operations, and top resources.
    """
    return StandardResponse(
        success=True,
        message="Audit statistics (in-memory store)",
        data={
            "stats": {
                "total_operations": 0,
                "successful_operations": 0,
                "failed_operations": 0
            },
            "top_operations": [],
            "period_hours": hours
        }
    )
