"""
CVE Alert History API

API endpoints for querying and managing CVE alert history.
Provides filtering, acknowledge, and dismiss operations.
"""

from fastapi import APIRouter, Query, Request
from typing import Optional, Dict, Any

try:
    from utils.response_models import StandardResponse
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.response_models import StandardResponse
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

router = APIRouter()
logger = get_logger(__name__)


@router.get("/alerts/history")
async def query_alert_history(
    request: Request,
    alert_type: Optional[str] = Query(None, description="Filter by alert type (critical, high, medium, low)"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    dismissed: Optional[bool] = Query(None, description="Filter by dismissed status"),
    start_date: Optional[str] = Query(None, description="Filter by start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (ISO format)"),
    scan_id: Optional[str] = Query(None, description="Filter by scan ID"),
    limit: int = Query(100, description="Max records to return", le=1000),
    offset: int = Query(0, description="Offset for pagination", ge=0)
) -> StandardResponse:
    """
    Query CVE alert history with filters.

    Supports filtering by:
    - alert_type: Severity level (critical, high, medium, low)
    - acknowledged: Acknowledgment status (true/false)
    - dismissed: Dismissal status (true/false)
    - start_date/end_date: Date range
    - scan_id: Specific scan
    - limit/offset: Pagination

    Returns:
        StandardResponse with records array and metadata
    """
    try:
        filters = {}

        if alert_type:
            filters["alert_type"] = alert_type.lower()

        if acknowledged is not None:
            filters["acknowledged"] = acknowledged

        if dismissed is not None:
            filters["dismissed"] = dismissed

        if start_date:
            filters["start_date"] = start_date

        if end_date:
            filters["end_date"] = end_date

        if scan_id:
            filters["scan_id"] = scan_id

        alert_repo = request.app.state.alert_repo
        records = await alert_repo.query_history(filters, limit, offset)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} alert history records",
            data={
                "records": records,
                "count": len(records),
                "limit": limit,
                "offset": offset,
                "filters": filters
            }
        )

    except Exception as e:
        logger.error(f"Failed to query alert history: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Failed to query alert history: {str(e)}"
        )


@router.get("/alerts/history/{record_id}")
async def get_alert_details(request: Request, record_id: str) -> StandardResponse:
    """
    Get full alert history record details.

    Args:
        record_id: Alert history record ID

    Returns:
        StandardResponse with complete record data
    """
    try:
        alert_repo = request.app.state.alert_repo
        record = await alert_repo.get_record(record_id)

        if not record:
            return StandardResponse(
                success=False,
                message=f"Alert {record_id} not found"
            )

        return StandardResponse(
            success=True,
            message="Alert details retrieved",
            data={"record": record}
        )

    except Exception as e:
        logger.error(f"Failed to get alert details {record_id}: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Failed to get alert details: {str(e)}"
        )


@router.post("/alerts/history/{record_id}/acknowledge")
async def acknowledge_alert(
    request: Request,
    record_id: str,
    body: Dict[str, Any]
) -> StandardResponse:
    """
    Acknowledge CVE alert.

    Body parameters:
        user: User acknowledging the alert (required)
        note: Optional acknowledgment note

    Args:
        record_id: Alert history record ID
        body: Request body with user and optional note

    Returns:
        StandardResponse with acknowledgment result
    """
    try:
        user = body.get("user")
        if not user:
            return StandardResponse(
                success=False,
                message="User is required for acknowledgment"
            )

        note = body.get("note")

        alert_repo = request.app.state.alert_repo
        success = await alert_repo.acknowledge(record_id, user, note)

        if not success:
            return StandardResponse(
                success=False,
                message=f"Alert {record_id} not found or already acknowledged"
            )

        logger.info(f"Alert {record_id} acknowledged by {user}")

        return StandardResponse(
            success=True,
            message="Alert acknowledged successfully",
            data={
                "record_id": record_id,
                "acknowledged_by": user,
                "note": note
            }
        )

    except Exception as e:
        logger.error(f"Failed to acknowledge alert {record_id}: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Failed to acknowledge alert: {str(e)}"
        )


@router.post("/alerts/history/{record_id}/dismiss")
async def dismiss_alert(
    request: Request,
    record_id: str,
    body: Dict[str, Any]
) -> StandardResponse:
    """
    Dismiss CVE alert with reason.

    Body parameters:
        reason: Reason for dismissal (required)

    Args:
        record_id: Alert history record ID
        body: Request body with reason

    Returns:
        StandardResponse with dismissal result
    """
    try:
        reason = body.get("reason")
        if not reason:
            return StandardResponse(
                success=False,
                message="Dismissal reason is required"
            )

        alert_repo = request.app.state.alert_repo
        success = await alert_repo.dismiss(record_id, reason)

        if not success:
            return StandardResponse(
                success=False,
                message=f"Alert {record_id} not found or already dismissed"
            )

        logger.info(f"Alert {record_id} dismissed: {reason}")

        return StandardResponse(
            success=True,
            message="Alert dismissed successfully",
            data={
                "record_id": record_id,
                "reason": reason
            }
        )

    except Exception as e:
        logger.error(f"Failed to dismiss alert {record_id}: {e}", exc_info=True)
        return StandardResponse(
            success=False,
            message=f"Failed to dismiss alert: {str(e)}"
        )
