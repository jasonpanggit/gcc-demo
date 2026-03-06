"""Routing Analytics API Router.

Provides REST API endpoints for the Routing Analytics Dashboard.
Reads telemetry data from JSON log files and provides aggregated statistics.

Endpoints:
- GET /api/routing-analytics/summary - Overall routing accuracy summary
- GET /api/routing-analytics/tool-usage - Tool usage statistics
- GET /api/routing-analytics/timeseries - Time-series data for charts
- GET /api/routing-analytics/low-confidence - Low confidence queries
- GET /api/routing-analytics/corrections - User corrections list
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from utils.logger import get_logger
    from utils.response_models import StandardResponse
except ModuleNotFoundError:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.response_models import StandardResponse


logger = get_logger(__name__)

# Prevent repeating the same missing-dir warning on every analytics request.
_LOG_DIR_WARNING_EMITTED = False

router = APIRouter(
    prefix="/api/routing-analytics",
    tags=["Routing Analytics"],
    responses={
        404: {"description": "Resource not found"},
        500: {"description": "Internal server error"}
    }
)


# ============================================================================
# Response Models
# ============================================================================

class RoutingSummary(BaseModel):
    """Overall routing accuracy summary."""
    total_queries: int = Field(..., description="Total queries processed")
    routing_accuracy: float = Field(..., description="Percentage of successful routes (0.0-1.0)")
    avg_execution_time_ms: float = Field(..., description="Average execution time in milliseconds")
    confidence_distribution: Dict[str, float] = Field(..., description="Confidence level distribution")
    user_corrections: int = Field(..., description="Number of user corrections")
    date_range: Dict[str, str] = Field(..., description="Date range of data")


class ToolUsageItem(BaseModel):
    """Tool usage statistics item."""
    tool_name: str
    count: int
    percentage: float


class UserCorrectionItem(BaseModel):
    """User correction item."""
    query: str
    original_tool: str
    corrected_tool: str
    timestamp: str
    count: int = Field(default=1, description="Number of times this correction occurred")


class LowConfidenceQuery(BaseModel):
    """Low confidence query item."""
    query: str
    selected_tools: List[str]
    confidence_level: str
    final_score: float
    timestamp: str


class TimeseriesDataPoint(BaseModel):
    """Time-series data point."""
    timestamp: str
    queries: int
    accuracy: float
    avg_confidence: float


# ============================================================================
# Helper Functions
# ============================================================================

def _get_log_dir() -> Path:
    """Get a usable routing logs directory from environment or default.

    Tries the configured directory first and creates it if missing. If that
    fails (for example due to filesystem permissions), falls back to a local
    ``./routing_logs`` directory to keep analytics endpoints functional.
    """
    configured = Path(os.getenv("ROUTING_TELEMETRY_LOG_DIR", "./routing_logs"))
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except Exception as exc:
        fallback = Path("./routing_logs")
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If fallback also fails, return configured so callers still behave
            # deterministically and can report an accurate path.
            return configured

        global _LOG_DIR_WARNING_EMITTED
        if not _LOG_DIR_WARNING_EMITTED:
            logger.warning(
                "Unable to use ROUTING_TELEMETRY_LOG_DIR=%s (%s); falling back to %s",
                configured,
                exc,
                fallback,
            )
            _LOG_DIR_WARNING_EMITTED = True
        return fallback


def _read_routing_logs(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict]:
    """Read routing decision logs from JSON files.

    Args:
        start_date: Start date filter (inclusive)
        end_date: End date filter (inclusive)

    Returns:
        List of routing decision dictionaries
    """
    log_dir = _get_log_dir()
    if not log_dir.exists():
        global _LOG_DIR_WARNING_EMITTED
        if not _LOG_DIR_WARNING_EMITTED:
            logger.warning("Routing logs directory does not exist: %s", log_dir)
            _LOG_DIR_WARNING_EMITTED = True
        return []

    routing_logs = []
    for log_file in log_dir.glob("routing_*.jsonl"):
        try:
            with open(log_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)

                    # Parse timestamp
                    timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))

                    # Apply date filters
                    if start_date and timestamp < start_date:
                        continue
                    if end_date and timestamp > end_date:
                        continue

                    routing_logs.append(entry)
        except Exception as e:
            logger.error(f"Failed to read routing log {log_file}: {e}")

    return routing_logs


def _read_execution_logs(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict]:
    """Read execution result logs from JSON files.

    Args:
        start_date: Start date filter (inclusive)
        end_date: End date filter (inclusive)

    Returns:
        List of execution result dictionaries
    """
    log_dir = _get_log_dir()
    if not log_dir.exists():
        return []

    execution_logs = []
    for log_file in log_dir.glob("execution_*.jsonl"):
        try:
            with open(log_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)

                    # Parse timestamp
                    timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))

                    # Apply date filters
                    if start_date and timestamp < start_date:
                        continue
                    if end_date and timestamp > end_date:
                        continue

                    execution_logs.append(entry)
        except Exception as e:
            logger.error(f"Failed to read execution log {log_file}: {e}")

    return execution_logs


def _read_correction_logs(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[Dict]:
    """Read user correction logs from JSON files.

    Args:
        start_date: Start date filter (inclusive)
        end_date: End date filter (inclusive)

    Returns:
        List of user correction dictionaries
    """
    log_dir = _get_log_dir()
    if not log_dir.exists():
        return []

    correction_logs = []
    for log_file in log_dir.glob("corrections_*.jsonl"):
        try:
            with open(log_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)

                    # Parse timestamp
                    timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))

                    # Apply date filters
                    if start_date and timestamp < start_date:
                        continue
                    if end_date and timestamp > end_date:
                        continue

                    correction_logs.append(entry)
        except Exception as e:
            logger.error(f"Failed to read correction log {log_file}: {e}")

    return correction_logs


def _parse_date_filters(
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse API date filters, making date-only end dates inclusive.

    UI inputs are usually ``YYYY-MM-DD`` (no time). For those values we expand:
    - ``start_date`` to start of day (00:00:00)
    - ``end_date`` to end of day (23:59:59.999999)
    """
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        if len(start_date) == 10:  # YYYY-MM-DD
            start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if end_date:
        end_dt = datetime.fromisoformat(end_date)
        if len(end_date) == 10:  # YYYY-MM-DD
            end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_dt, end_dt


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/summary", response_model=StandardResponse)
async def get_routing_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Get overall routing accuracy summary.

    Returns aggregated statistics including:
    - Total queries processed
    - Routing accuracy percentage
    - Average execution time
    - Confidence distribution
    - User corrections count

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        StandardResponse with RoutingSummary data
    """
    try:
        # Parse dates (date-only end_date is inclusive through end-of-day)
        start_dt, end_dt = _parse_date_filters(start_date, end_date)

        # Read logs
        routing_logs = _read_routing_logs(start_dt, end_dt)
        execution_logs = _read_execution_logs(start_dt, end_dt)
        correction_logs = _read_correction_logs(start_dt, end_dt)

        if not routing_logs:
            # No data available
            return StandardResponse(
                success=True,
                data={
                    "total_queries": 0,
                    "routing_accuracy": 0.0,
                    "avg_execution_time_ms": 0.0,
                    "confidence_distribution": {"high": 0.0, "medium": 0.0, "low": 0.0},
                    "user_corrections": 0,
                    "date_range": {
                        "start": start_date or "N/A",
                        "end": end_date or "N/A"
                    }
                },
                message="No routing data available for the specified date range"
            )

        # Calculate statistics
        total_queries = len(routing_logs)

        # Confidence distribution
        confidence_counts = Counter(log.get("confidence_level", "low") for log in routing_logs)
        confidence_distribution = {
            "high": confidence_counts.get("high", 0) / total_queries if total_queries > 0 else 0.0,
            "medium": confidence_counts.get("medium", 0) / total_queries if total_queries > 0 else 0.0,
            "low": confidence_counts.get("low", 0) / total_queries if total_queries > 0 else 0.0
        }

        # Execution time
        execution_times = [log.get("execution_time_ms", 0) for log in execution_logs if log.get("execution_time_ms")]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0

        # Routing accuracy (successful executions / total queries)
        successful = sum(1 for log in execution_logs if log.get("success", False))
        routing_accuracy = successful / len(execution_logs) if execution_logs else 0.0

        # User corrections
        user_corrections_count = len(correction_logs)

        # Date range
        timestamps = [datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")) for log in routing_logs]
        date_range = {
            "start": min(timestamps).isoformat() if timestamps else "N/A",
            "end": max(timestamps).isoformat() if timestamps else "N/A"
        }

        return StandardResponse(
            success=True,
            data={
                "total_queries": total_queries,
                "routing_accuracy": round(routing_accuracy, 3),
                "avg_execution_time_ms": round(avg_execution_time, 1),
                "confidence_distribution": {k: round(v, 3) for k, v in confidence_distribution.items()},
                "user_corrections": user_corrections_count,
                "date_range": date_range
            },
            message="Successfully retrieved routing summary"
        )

    except Exception as e:
        logger.error(f"Failed to generate routing summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")


@router.get("/tool-usage", response_model=StandardResponse)
async def get_tool_usage(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(10, ge=1, le=100, description="Number of top tools to return")
):
    """Get tool usage statistics.

    Returns the most frequently selected tools with counts and percentages.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Maximum number of tools to return (default: 10)

    Returns:
        StandardResponse with list of ToolUsageItem
    """
    try:
        # Parse dates (date-only end_date is inclusive through end-of-day)
        start_dt, end_dt = _parse_date_filters(start_date, end_date)

        # Read logs
        routing_logs = _read_routing_logs(start_dt, end_dt)

        if not routing_logs:
            return StandardResponse(
                success=True,
                data=[],
                message="No routing data available"
            )

        # Count tool usage
        tool_counts = Counter()
        for log in routing_logs:
            for tool in log.get("selected_tools", []):
                tool_counts[tool] += 1

        # Calculate total
        total_selections = sum(tool_counts.values())

        # Build response
        tool_usage = [
            {
                "tool_name": tool,
                "count": count,
                "percentage": round(count / total_selections, 3) if total_selections > 0 else 0.0
            }
            for tool, count in tool_counts.most_common(limit)
        ]

        return StandardResponse(
            success=True,
            data=tool_usage,
            message=f"Retrieved top {len(tool_usage)} tools"
        )

    except Exception as e:
        logger.error(f"Failed to get tool usage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get tool usage: {str(e)}")


@router.get("/timeseries", response_model=StandardResponse)
async def get_timeseries_data(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("hour", description="Time interval: hour, day, week")
):
    """Get time-series data for routing metrics.

    Returns query counts, accuracy, and confidence scores over time.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        interval: Time interval for aggregation (hour, day, week)

    Returns:
        StandardResponse with list of TimeseriesDataPoint
    """
    try:
        # Parse dates (date-only end_date is inclusive through end-of-day)
        start_dt, end_dt = _parse_date_filters(start_date, end_date)

        # Read logs
        routing_logs = _read_routing_logs(start_dt, end_dt)
        execution_logs = _read_execution_logs(start_dt, end_dt)

        if not routing_logs:
            return StandardResponse(
                success=True,
                data=[],
                message="No routing data available"
            )

        # Group by time interval
        timeseries_data = defaultdict(lambda: {"queries": 0, "successful": 0, "scores": []})

        for log in routing_logs:
            timestamp = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))

            # Round to interval
            if interval == "hour":
                bucket = timestamp.replace(minute=0, second=0, microsecond=0)
            elif interval == "day":
                bucket = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            elif interval == "week":
                bucket = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                bucket -= timedelta(days=bucket.weekday())
            else:
                bucket = timestamp.replace(minute=0, second=0, microsecond=0)

            bucket_key = bucket.isoformat()
            timeseries_data[bucket_key]["queries"] += 1

            # Extract score from first candidate
            candidates = log.get("candidates", [])
            if candidates and len(candidates) > 0:
                first_score = candidates[0].get("final_score", 0.0)
                timeseries_data[bucket_key]["scores"].append(first_score)

        # Match with execution logs
        for log in execution_logs:
            timestamp = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))

            # Round to interval
            if interval == "hour":
                bucket = timestamp.replace(minute=0, second=0, microsecond=0)
            elif interval == "day":
                bucket = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            elif interval == "week":
                bucket = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                bucket -= timedelta(days=bucket.weekday())
            else:
                bucket = timestamp.replace(minute=0, second=0, microsecond=0)

            bucket_key = bucket.isoformat()
            if log.get("success", False):
                timeseries_data[bucket_key]["successful"] += 1

        # Build response
        result = []
        for bucket_key in sorted(timeseries_data.keys()):
            data = timeseries_data[bucket_key]
            queries = data["queries"]
            successful = data["successful"]
            scores = data["scores"]

            result.append({
                "timestamp": bucket_key,
                "queries": queries,
                "accuracy": round(successful / queries, 3) if queries > 0 else 0.0,
                "avg_confidence": round(sum(scores) / len(scores), 3) if scores else 0.0
            })

        return StandardResponse(
            success=True,
            data=result,
            message=f"Retrieved {len(result)} time-series data points"
        )

    except Exception as e:
        logger.error(f"Failed to get timeseries data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get timeseries data: {str(e)}")


@router.get("/low-confidence", response_model=StandardResponse)
async def get_low_confidence_queries(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Number of queries to return")
):
    """Get low confidence queries that may need metadata improvements.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Maximum number of queries to return

    Returns:
        StandardResponse with list of LowConfidenceQuery
    """
    try:
        # Parse dates (date-only end_date is inclusive through end-of-day)
        start_dt, end_dt = _parse_date_filters(start_date, end_date)

        # Read logs
        routing_logs = _read_routing_logs(start_dt, end_dt)

        if not routing_logs:
            return StandardResponse(
                success=True,
                data=[],
                message="No routing data available"
            )

        # Filter low confidence queries
        low_confidence = []
        for log in routing_logs:
            if log.get("confidence_level") in ["low", "medium"]:
                candidates = log.get("candidates", [])
                first_score = candidates[0].get("final_score", 0.0) if candidates else 0.0

                low_confidence.append({
                    "query": log.get("query", ""),
                    "selected_tools": log.get("selected_tools", []),
                    "confidence_level": log.get("confidence_level", "low"),
                    "final_score": round(first_score, 3),
                    "timestamp": log.get("timestamp", "")
                })

        # Sort by score (lowest first) and limit
        low_confidence.sort(key=lambda x: x["final_score"])
        low_confidence = low_confidence[:limit]

        return StandardResponse(
            success=True,
            data=low_confidence,
            message=f"Retrieved {len(low_confidence)} low confidence queries"
        )

    except Exception as e:
        logger.error(f"Failed to get low confidence queries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get low confidence queries: {str(e)}")


@router.get("/corrections", response_model=StandardResponse)
async def get_user_corrections(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Number of corrections to return")
):
    """Get user corrections showing misrouted queries.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Maximum number of corrections to return

    Returns:
        StandardResponse with list of UserCorrectionItem
    """
    try:
        # Parse dates (date-only end_date is inclusive through end-of-day)
        start_dt, end_dt = _parse_date_filters(start_date, end_date)

        # Read logs
        correction_logs = _read_correction_logs(start_dt, end_dt)

        if not correction_logs:
            return StandardResponse(
                success=True,
                data=[],
                message="No user corrections available"
            )

        # Group by correction pattern
        correction_patterns = defaultdict(lambda: {"count": 0, "latest": ""})
        for log in correction_logs:
            key = (log.get("query", ""), log.get("original_tool", ""), log.get("corrected_tool", ""))
            correction_patterns[key]["count"] += 1
            correction_patterns[key]["latest"] = log.get("timestamp", "")

        # Build response
        corrections = [
            {
                "query": query,
                "original_tool": original,
                "corrected_tool": corrected,
                "timestamp": data["latest"],
                "count": data["count"]
            }
            for (query, original, corrected), data in correction_patterns.items()
        ]

        # Sort by count (most frequent first) and limit
        corrections.sort(key=lambda x: x["count"], reverse=True)
        corrections = corrections[:limit]

        return StandardResponse(
            success=True,
            data=corrections,
            message=f"Retrieved {len(corrections)} user corrections"
        )

    except Exception as e:
        logger.error(f"Failed to get user corrections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get user corrections: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint for routing analytics API."""
    log_dir = _get_log_dir()
    log_dir_exists = log_dir.exists()

    # Count log files
    routing_logs = len(list(log_dir.glob("routing_*.jsonl"))) if log_dir_exists else 0
    execution_logs = len(list(log_dir.glob("execution_*.jsonl"))) if log_dir_exists else 0
    correction_logs = len(list(log_dir.glob("corrections_*.jsonl"))) if log_dir_exists else 0

    return StandardResponse(
        success=True,
        data={
            "status": "healthy",
            "log_directory": str(log_dir),
            "log_directory_exists": log_dir_exists,
            "log_file_counts": {
                "routing": routing_logs,
                "execution": execution_logs,
                "corrections": correction_logs
            }
        },
        message="Routing analytics API is healthy"
    )
