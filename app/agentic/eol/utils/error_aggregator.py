"""
Error Aggregation Utility

Collects and aggregates errors from parallel operations for better error handling
in orchestrators and agents.

Created: 2026-02-27 (Phase 2, Day 4)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict


class ErrorAggregator:
    """Collects and aggregates errors from parallel operations."""

    def __init__(self):
        """Initialize the error aggregator."""
        self.errors: List[Dict[str, Any]] = []
        self._error_counts_by_type: Dict[str, int] = defaultdict(int)

    def add_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add an error with context information.

        Args:
            error: The exception that occurred
            context: Additional context (e.g., agent name, operation, correlation_id)
        """
        error_type = type(error).__name__
        error_entry = {
            "error_type": error_type,
            "error_message": str(error),
            "timestamp": datetime.utcnow().isoformat(),
            "context": context or {}
        }

        self.errors.append(error_entry)
        self._error_counts_by_type[error_type] += 1

    def get_summary(self) -> Dict[str, Any]:
        """
        Get aggregated error summary.

        Returns:
            Dictionary with error statistics and grouped errors
        """
        if not self.errors:
            return {
                "total_errors": 0,
                "error_types": {},
                "errors": []
            }

        return {
            "total_errors": len(self.errors),
            "error_types": dict(self._error_counts_by_type),
            "errors": self.errors
        }

    def get_errors_by_type(self, error_type: str) -> List[Dict[str, Any]]:
        """
        Get all errors of a specific type.

        Args:
            error_type: The exception type name to filter by

        Returns:
            List of error entries matching the type
        """
        return [
            error for error in self.errors
            if error["error_type"] == error_type
        ]

    def has_errors(self) -> bool:
        """
        Check if any errors have been collected.

        Returns:
            True if errors exist, False otherwise
        """
        return len(self.errors) > 0

    def get_error_count(self) -> int:
        """
        Get total number of errors collected.

        Returns:
            Count of errors
        """
        return len(self.errors)

    def clear(self) -> None:
        """Clear all collected errors."""
        self.errors.clear()
        self._error_counts_by_type.clear()

    def get_errors_by_context(self, context_key: str, context_value: Any) -> List[Dict[str, Any]]:
        """
        Get errors filtered by a specific context key-value pair.

        Args:
            context_key: The context key to filter by
            context_value: The value to match

        Returns:
            List of error entries matching the context filter
        """
        return [
            error for error in self.errors
            if error.get("context", {}).get(context_key) == context_value
        ]
