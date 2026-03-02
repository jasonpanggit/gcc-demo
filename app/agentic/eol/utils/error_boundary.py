"""
Error Boundary Wrapper

Provides error boundary pattern for async functions with fallback support
and structured error logging.

Created: 2026-02-27 (Phase 2, Day 6)
"""

import logging
from typing import Any, Callable, Optional, TypeVar, Awaitable
from functools import wraps

try:
    from utils.correlation_id import get_correlation_id
    CORRELATION_ID_AVAILABLE = True
except ImportError:
    CORRELATION_ID_AVAILABLE = False

try:
    from utils.error_aggregator import ErrorAggregator
    ERROR_AGGREGATOR_AVAILABLE = True
except ImportError:
    ERROR_AGGREGATOR_AVAILABLE = False


logger = logging.getLogger(__name__)

T = TypeVar('T')


async def with_error_boundary(
    func: Callable[..., Awaitable[T]],
    fallback: Optional[Callable[..., Awaitable[T]]] = None,
    context: Optional[dict] = None,
    suppress: bool = False
) -> Optional[T]:
    """
    Execute an async function within an error boundary.

    Provides centralized error handling with:
    - Correlation ID tracking
    - Structured error logging
    - Optional fallback execution
    - Error suppression option

    Args:
        func: The async function to execute
        fallback: Optional fallback function to call on error
        context: Additional context for error logging (e.g., {"operation": "fetch_data"})
        suppress: If True, suppress exceptions and return None on error

    Returns:
        Result from func, or fallback result, or None if suppressed

    Raises:
        Exception: Re-raises the original exception if not suppressed and no fallback

    Example:
        >>> async def fetch_data():
        ...     return await api_call()
        ...
        >>> async def fallback_data():
        ...     return cached_data()
        ...
        >>> result = await with_error_boundary(
        ...     fetch_data,
        ...     fallback=fallback_data,
        ...     context={"operation": "fetch", "source": "api"}
        ... )
    """
    try:
        return await func()
    except Exception as e:
        # Build error context
        error_context = context or {}
        if CORRELATION_ID_AVAILABLE:
            cid = get_correlation_id()
            if cid:
                error_context["correlation_id"] = cid

        # Log the error with context
        logger.error(
            f"Error boundary caught: {type(e).__name__}: {str(e)}",
            extra=error_context,
            exc_info=True
        )

        # Execute fallback if provided
        if fallback:
            try:
                logger.warning("Executing fallback handler", extra=error_context)
                return await fallback()
            except Exception as fallback_error:
                logger.error(
                    f"Fallback handler failed: {type(fallback_error).__name__}: {str(fallback_error)}",
                    extra=error_context,
                    exc_info=True
                )
                if not suppress:
                    raise

        # Suppress or re-raise
        if suppress:
            logger.warning("Error suppressed by error boundary", extra=error_context)
            return None
        raise


def error_boundary(
    fallback: Optional[Callable[..., Awaitable[T]]] = None,
    context: Optional[dict] = None,
    suppress: bool = False
):
    """
    Decorator version of with_error_boundary.

    Args:
        fallback: Optional fallback function
        context: Additional context for error logging
        suppress: If True, suppress exceptions

    Example:
        >>> @error_boundary(fallback=get_cached_result, context={"service": "api"})
        >>> async def fetch_from_api():
        ...     return await api.get("/data")
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Optional[T]:
            async def bound_func():
                return await func(*args, **kwargs)

            return await with_error_boundary(
                bound_func,
                fallback=fallback,
                context=context,
                suppress=suppress
            )
        return wrapper
    return decorator


async def with_error_aggregation(
    func: Callable[..., Awaitable[T]],
    error_aggregator: Any,
    context: Optional[dict] = None,
    fallback: Optional[Callable[..., Awaitable[T]]] = None
) -> Optional[T]:
    """
    Execute function with error boundary and aggregate errors.

    Combines error boundary pattern with error aggregation for
    collecting errors from parallel operations.

    Args:
        func: The async function to execute
        error_aggregator: ErrorAggregator instance to collect errors
        context: Context for error aggregation
        fallback: Optional fallback function

    Returns:
        Result from func, fallback result, or None

    Example:
        >>> from utils.error_aggregator import ErrorAggregator
        >>>
        >>> agg = ErrorAggregator()
        >>> async def agent_call():
        ...     return await call_agent()
        ...
        >>> result = await with_error_aggregation(
        ...     agent_call,
        ...     agg,
        ...     context={"agent": "microsoft", "operation": "eol_query"}
        ... )
    """
    try:
        return await func()
    except Exception as e:
        # Add to error aggregator if available
        if ERROR_AGGREGATOR_AVAILABLE and hasattr(error_aggregator, 'add_error'):
            error_aggregator.add_error(e, context or {})

        # Build error context for logging
        error_context = context or {}
        if CORRELATION_ID_AVAILABLE:
            cid = get_correlation_id()
            if cid:
                error_context["correlation_id"] = cid

        logger.error(
            f"Error in aggregated operation: {type(e).__name__}: {str(e)}",
            extra=error_context,
            exc_info=True
        )

        # Execute fallback if provided
        if fallback:
            try:
                return await fallback()
            except Exception as fallback_error:
                logger.error(
                    f"Fallback failed: {type(fallback_error).__name__}",
                    extra=error_context
                )
                # Don't re-raise - error is already in aggregator
                return None

        # Return None - errors tracked in aggregator
        return None
