"""
Metrics API endpoint for observability.
Provides access to system metrics collected by the metrics collector.
"""
from fastapi import APIRouter
from utils.metrics import metrics_collector
from utils.response_models import StandardResponse

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics")
async def get_metrics():
    """
    Get all collected metrics (counters and histograms).

    Returns:
        StandardResponse containing counters and histograms with statistics.
    """
    try:
        metrics_data = metrics_collector.get_all_metrics()
        return StandardResponse(
            success=True,
            data=[metrics_data],
            count=1,
            metadata={"agent": "metrics_endpoint"},
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            data=[],
            count=0,
            error=f"Failed to retrieve metrics: {str(e)}",
        )


@router.post("/metrics/reset")
async def reset_metrics():
    """
    Reset all metrics to zero.

    Returns:
        StandardResponse with reset confirmation.
    """
    try:
        metrics_collector.reset()
        return StandardResponse(
            success=True,
            data=[{"message": "Metrics reset successfully"}],
            count=1,
            metadata={"agent": "metrics_endpoint"},
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            data=[],
            count=0,
            error=f"Failed to reset metrics: {str(e)}",
        )
