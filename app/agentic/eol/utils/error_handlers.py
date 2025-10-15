"""
Standardized Error Handling Decorators
Provides consistent error handling across all API endpoints
"""
import functools
import logging
from typing import Any, Callable, Optional
from fastapi import HTTPException
from datetime import datetime, timezone

from .response_models import StandardResponse

logger = logging.getLogger(__name__)


def handle_api_errors(context: str = "", log_errors: bool = True):
    """
    Decorator for consistent error handling across API endpoints
    
    Args:
        context: Descriptive context for the operation (e.g., "Software inventory fetch")
        log_errors: Whether to log errors (default True)
    
    Returns:
        Decorated function with standardized error handling
    
    Usage:
        @app.get("/api/inventory/software")
        @handle_api_errors("Software inventory fetch")
        async def get_software_inventory():
            return await inventory_agent.get_software_inventory()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTP exceptions without wrapping
                raise
            except Exception as e:
                if log_errors:
                    logger.error(
                        f"❌ {context} error: {e}", 
                        exc_info=True,
                        extra={
                            "context": context,
                            "error_type": type(e).__name__,
                            "function": func.__name__
                        }
                    )
                
                return StandardResponse(
                    success=False,
                    message=f"{context} failed" if context else "Operation failed",
                    data=None,
                    error={
                        "type": type(e).__name__,
                        "message": str(e),
                        "context": context,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ).dict()
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTP exceptions without wrapping
                raise
            except Exception as e:
                if log_errors:
                    logger.error(
                        f"❌ {context} error: {e}", 
                        exc_info=True,
                        extra={
                            "context": context,
                            "error_type": type(e).__name__,
                            "function": func.__name__
                        }
                    )
                
                return StandardResponse(
                    success=False,
                    message=f"{context} failed" if context else "Operation failed",
                    data=None,
                    error={
                        "type": type(e).__name__,
                        "message": str(e),
                        "context": context,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ).dict()
        
        # Return appropriate wrapper based on whether function is async
        if functools.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def handle_agent_errors(agent_name: str = "Unknown"):
    """
    Decorator for consistent error handling in agent methods
    
    Args:
        agent_name: Name of the agent for logging
    
    Returns:
        Decorated function with agent-specific error handling
    
    Usage:
        @handle_agent_errors("Microsoft EOL Agent")
        async def get_eol_data(self, software_name: str):
            # agent logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"❌ {agent_name} error in {func.__name__}: {e}",
                    exc_info=True,
                    extra={
                        "agent": agent_name,
                        "method": func.__name__,
                        "error_type": type(e).__name__
                    }
                )
                
                # Return standardized failure response
                return {
                    "success": False,
                    "source": agent_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__,
                        "agent": agent_name,
                        "method": func.__name__
                    },
                    "data": None
                }
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"❌ {agent_name} error in {func.__name__}: {e}",
                    exc_info=True,
                    extra={
                        "agent": agent_name,
                        "method": func.__name__,
                        "error_type": type(e).__name__
                    }
                )
                
                # Return standardized failure response
                return {
                    "success": False,
                    "source": agent_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__,
                        "agent": agent_name,
                        "method": func.__name__
                    },
                    "data": None
                }
        
        # Return appropriate wrapper based on whether function is async
        if functools.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def retry_on_failure(
    max_retries: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry function on failure with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        delay_seconds: Initial delay between retries
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to catch and retry
    
    Returns:
        Decorated function with retry logic
    
    Usage:
        @retry_on_failure(max_retries=3, delay_seconds=1.0)
        async def fetch_external_api():
            # API call that might fail
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            import asyncio
            
            last_exception = None
            delay = delay_seconds
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"⚠️ {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {delay}s: {e}"
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_multiplier
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            
            # Re-raise the last exception after all retries exhausted
            raise last_exception
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            import time
            
            last_exception = None
            delay = delay_seconds
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"⚠️ {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {delay}s: {e}"
                        )
                        time.sleep(delay)
                        delay *= backoff_multiplier
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            
            # Re-raise the last exception after all retries exhausted
            raise last_exception
        
        # Return appropriate wrapper based on whether function is async
        if functools.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
