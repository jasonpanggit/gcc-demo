"""
FastAPI middleware for request tracking and observability.

Provides:
- Request ID injection and propagation
- Structured logging helpers with correlation IDs
- Basic metrics collection hooks
"""
import uuid
import time
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    - Injects or propagates X-Request-ID header
    - Stores request_id on request.state for use in handlers
    - Adds request_id to response headers
    - Logs request/response timing
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate request ID
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Store start time for duration calculation
        start_time = time.perf_counter()

        # Log incoming request
        logger.info(
            f"Incoming request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown",
            },
        )

        try:
            # Call the next middleware or route handler
            response = await call_next(request)
        except Exception as exc:
            # Log exception with request context
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Request failed with exception: {exc}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": f"{duration_ms:.2f}",
                },
                exc_info=True,
            )
            raise

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add request ID to response headers
        response.headers["x-request-id"] = request_id

        # Log response
        logger.info(
            f"Response completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": f"{duration_ms:.2f}",
            },
        )

        return response


def get_request_id(request: Request) -> str:
    """Helper to get request ID from request.state or generate a new one."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def log_with_request_context(
    request: Request, level: str, message: str, **extra_fields
):
    """
    Log a message with request context automatically included.

    Args:
        request: Starlette request object
        level: logging level ("info", "warning", "error", etc.)
        message: log message
        **extra_fields: additional fields to include in log
    """
    request_id = get_request_id(request)
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(
        message,
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            **extra_fields,
        },
    )
