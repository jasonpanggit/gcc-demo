"""
Endpoint Decorators for FastAPI
Provides reusable decorators for common endpoint functionality like
timeout handling, error handling, and cache statistics tracking.
"""
import asyncio
import time
from functools import wraps
from typing import Any, Callable, Optional

from fastapi import HTTPException

from utils import get_logger
from utils.cache_stats_manager import cache_stats_manager
from utils.response_models import StandardResponse, create_standard_response, create_error_response

logger = get_logger(__name__)


def with_timeout_and_stats(
    agent_name: str,
    timeout_seconds: int = 30,
    track_cache: bool = True,
    auto_wrap_response: bool = True
):
    """
    Decorator to add timeout, error handling, and cache statistics to async endpoints.
    
    This decorator:
    1. Wraps the endpoint function with timeout protection
    2. Records cache statistics for performance tracking
    3. Handles common errors consistently
    4. Optionally wraps results in StandardResponse format
    
    Args:
        agent_name: Name of the agent/service for logging and stats
        timeout_seconds: Maximum execution time before timeout
        track_cache: Whether to record cache statistics
        auto_wrap_response: Whether to automatically wrap non-StandardResponse returns
    
    Usage:
        @app.get("/api/example")
        @with_timeout_and_stats(agent_name="example", timeout_seconds=30)
        async def example_endpoint():
            result = await some_async_operation()
            return result  # Will be wrapped in StandardResponse automatically
    
    Returns:
        Decorated async function with timeout and error handling
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            cache_hit = False
            had_error = False
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
                
                # Detect cache hit from result
                if isinstance(result, dict):
                    cache_hit = result.get("cached", False) or result.get("cache_hit", False)
                
                # Record statistics
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=cache_hit,
                        had_error=False
                    )
                
                # Wrap in StandardResponse if requested and not already wrapped
                if auto_wrap_response:
                    if isinstance(result, StandardResponse):
                        return result
                    elif isinstance(result, dict) and "success" in result:
                        # Already has success field, keep as-is
                        return result
                    else:
                        # Wrap in standard format
                        return create_standard_response(
                            data=result,
                            message=f"{agent_name} operation completed successfully"
                        )
                else:
                    return result
                    
            except asyncio.TimeoutError:
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False,
                        had_error=True
                    )
                
                logger.error(f"{agent_name} request timed out after {timeout_seconds}s")
                raise HTTPException(
                    status_code=504,
                    detail=f"{agent_name} request timed out after {timeout_seconds} seconds"
                )
                
            except HTTPException:
                # Re-raise HTTP exceptions without modification
                raise
                
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                if track_cache:
                    cache_stats_manager.record_agent_request(
                        agent_name=agent_name,
                        response_time_ms=response_time,
                        was_cache_hit=False,
                        had_error=True
                    )
                
                logger.error(f"Error in {agent_name}: {str(e)}", exc_info=True)
                
                if auto_wrap_response:
                    # Return error in StandardResponse format
                    return create_error_response(
                        error=e,
                        context=agent_name,
                        include_traceback=False
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error in {agent_name}: {str(e)}"
                    )
        
        return wrapper
    return decorator


def with_cache_tracking(agent_name: str):
    """
    Lightweight decorator that only tracks cache statistics without timeout/error handling.
    
    Use this for endpoints that need custom error handling but still want cache tracking.
    
    Args:
        agent_name: Name of the agent/service for stats tracking
    
    Usage:
        @app.get("/api/example")
        @with_cache_tracking(agent_name="example")
        async def example_endpoint():
            # Your custom error handling here
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                
                # Detect cache hit from result
                cache_hit = False
                if isinstance(result, dict):
                    cache_hit = result.get("cached", False) or result.get("cache_hit", False)
                
                # Record statistics
                response_time = (time.time() - start_time) * 1000
                cache_stats_manager.record_agent_request(
                    agent_name=agent_name,
                    response_time_ms=response_time,
                    was_cache_hit=cache_hit,
                    had_error=False
                )
                
                return result
                
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                cache_stats_manager.record_agent_request(
                    agent_name=agent_name,
                    response_time_ms=response_time,
                    was_cache_hit=False,
                    had_error=True
                )
                raise
        
        return wrapper
    return decorator


def require_service(
    service_name: str,
    check_func: Callable[[], bool],
    error_message: Optional[str] = None
):
    """
    Decorator to check if a required service is available before executing endpoint.
    
    Args:
        service_name: Name of the service for error messages
        check_func: Function that returns True if service is available
        error_message: Custom error message (optional)
    
    Usage:
        @app.get("/api/example")
        @require_service(
            service_name="Cosmos DB",
            check_func=lambda: base_cosmos.is_available(),
            error_message="Cosmos DB is not configured"
        )
        async def example_endpoint():
            # Service is guaranteed to be available here
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not check_func():
                message = error_message or f"{service_name} is not available"
                logger.warning(f"Service check failed: {message}")
                raise HTTPException(status_code=503, detail=message)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Convenience decorator combinations for common use cases
def standard_endpoint(agent_name: str, timeout_seconds: int = 30):
    """
    Standard endpoint configuration with timeout, stats, and response wrapping.
    This is the recommended decorator for most endpoints.
    
    Usage:
        @app.get("/api/example", response_model=StandardResponse)
        @standard_endpoint(agent_name="example")
        async def example_endpoint():
            return result
    """
    return with_timeout_and_stats(
        agent_name=agent_name,
        timeout_seconds=timeout_seconds,
        track_cache=True,
        auto_wrap_response=True
    )


def readonly_endpoint(agent_name: str, timeout_seconds: int = 20):
    """
    Configuration for read-only endpoints with shorter timeout.
    
    Usage:
        @app.get("/api/status")
        @readonly_endpoint(agent_name="status")
        async def status_endpoint():
            return result
    """
    return with_timeout_and_stats(
        agent_name=agent_name,
        timeout_seconds=timeout_seconds,
        track_cache=False,  # Status endpoints typically don't use cache
        auto_wrap_response=True
    )


def write_endpoint(agent_name: str, timeout_seconds: int = 60):
    """
    Configuration for write/mutating endpoints with longer timeout.
    
    Usage:
        @app.post("/api/update")
        @write_endpoint(agent_name="update")
        async def update_endpoint():
            return result
    """
    return with_timeout_and_stats(
        agent_name=agent_name,
        timeout_seconds=timeout_seconds,
        track_cache=False,  # Write operations don't benefit from cache tracking
        auto_wrap_response=True
    )
