"""
Correlation ID Utility

Provides correlation ID generation and context propagation for distributed tracing
across async operations.

Created: 2026-02-27 (Phase 2, Day 4)
"""

import contextvars
from uuid import uuid4
from typing import Optional


# Context variable for storing correlation ID across async boundaries
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id',
    default=None
)


def generate_correlation_id() -> str:
    """
    Generate a new unique correlation ID.

    Returns:
        A UUID4-based correlation ID string
    """
    return str(uuid4())


def set_correlation_id(cid: str) -> None:
    """
    Set the correlation ID in the current async context.

    Args:
        cid: The correlation ID to set
    """
    correlation_id_var.set(cid)


def get_correlation_id() -> Optional[str]:
    """
    Get the current correlation ID from async context.

    Returns:
        The correlation ID if set, None otherwise
    """
    return correlation_id_var.get()


def ensure_correlation_id() -> str:
    """
    Get the current correlation ID, or generate and set a new one if none exists.

    Returns:
        The correlation ID (existing or newly generated)
    """
    cid = get_correlation_id()
    if cid is None:
        cid = generate_correlation_id()
        set_correlation_id(cid)
    return cid


def clear_correlation_id() -> None:
    """
    Clear the correlation ID from the current async context.

    Useful for testing or explicit context boundaries.
    """
    correlation_id_var.set(None)
