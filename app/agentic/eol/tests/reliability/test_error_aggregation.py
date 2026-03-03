"""
Error Aggregation Tests

Tests for error aggregation utility.
Created: 2026-02-27 (Phase 1, Task 3.2)
Updated: 2026-02-27 (Phase 2, Day 4)
"""

import pytest
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
class TestErrorAggregation:
    """Tests for error aggregation utility."""

    def test_error_aggregation_collect_errors(self):
        """Test collecting multiple errors from parallel operations."""
        aggregator = ErrorAggregator()

        # Add multiple errors
        error1 = ValueError("Invalid input")
        error2 = KeyError("Missing key")
        error3 = ValueError("Another value error")

        aggregator.add_error(error1, {"agent": "agent1", "operation": "fetch"})
        aggregator.add_error(error2, {"agent": "agent2", "operation": "parse"})
        aggregator.add_error(error3, {"agent": "agent3", "operation": "validate"})

        assert aggregator.has_errors()
        assert aggregator.get_error_count() == 3

    def test_error_aggregation_format_summary(self):
        """Test formatting aggregated errors into summary."""
        aggregator = ErrorAggregator()

        # Add errors
        aggregator.add_error(ValueError("error1"), {"agent": "agent1"})
        aggregator.add_error(KeyError("error2"), {"agent": "agent2"})

        summary = aggregator.get_summary()

        assert summary["total_errors"] == 2
        assert "ValueError" in summary["error_types"]
        assert "KeyError" in summary["error_types"]
        assert summary["error_types"]["ValueError"] == 1
        assert summary["error_types"]["KeyError"] == 1
        assert len(summary["errors"]) == 2

    def test_error_aggregation_by_type(self):
        """Test grouping errors by exception type."""
        aggregator = ErrorAggregator()

        # Add multiple errors of different types
        aggregator.add_error(ValueError("error1"), {"agent": "agent1"})
        aggregator.add_error(ValueError("error2"), {"agent": "agent2"})
        aggregator.add_error(KeyError("error3"), {"agent": "agent3"})

        value_errors = aggregator.get_errors_by_type("ValueError")
        key_errors = aggregator.get_errors_by_type("KeyError")

        assert len(value_errors) == 2
        assert len(key_errors) == 1
        assert all(e["error_type"] == "ValueError" for e in value_errors)
        assert all(e["error_type"] == "KeyError" for e in key_errors)

    def test_error_aggregation_context_preservation(self):
        """Test that error context (correlation IDs, timestamps) is preserved."""
        aggregator = ErrorAggregator()

        context = {
            "correlation_id": "test-123",
            "agent": "microsoft_agent",
            "operation": "query_eol"
        }

        error = RuntimeError("Test error")
        aggregator.add_error(error, context)

        summary = aggregator.get_summary()
        error_entry = summary["errors"][0]

        assert error_entry["context"]["correlation_id"] == "test-123"
        assert error_entry["context"]["agent"] == "microsoft_agent"
        assert error_entry["context"]["operation"] == "query_eol"
        assert "timestamp" in error_entry

    def test_error_aggregation_partial_success_handling(self):
        """Test handling scenarios where some operations succeed and some fail."""
        aggregator = ErrorAggregator()

        # Simulate 3 operations where 2 fail
        operations = [
            {"name": "op1", "success": True},
            {"name": "op2", "success": False, "error": ValueError("Failed op2")},
            {"name": "op3", "success": False, "error": KeyError("Failed op3")},
        ]

        for op in operations:
            if not op["success"]:
                aggregator.add_error(op["error"], {"operation": op["name"]})

        # Should only have 2 errors from failed operations
        assert aggregator.get_error_count() == 2
        assert aggregator.has_errors()

        summary = aggregator.get_summary()
        assert summary["total_errors"] == 2

    def test_error_aggregation_empty_state(self):
        """Test aggregator in empty state."""
        aggregator = ErrorAggregator()

        assert not aggregator.has_errors()
        assert aggregator.get_error_count() == 0

        summary = aggregator.get_summary()
        assert summary["total_errors"] == 0
        assert summary["error_types"] == {}
        assert summary["errors"] == []

    def test_error_aggregation_clear(self):
        """Test clearing collected errors."""
        aggregator = ErrorAggregator()

        aggregator.add_error(ValueError("error1"), {"agent": "agent1"})
        aggregator.add_error(KeyError("error2"), {"agent": "agent2"})

        assert aggregator.has_errors()

        aggregator.clear()

        assert not aggregator.has_errors()
        assert aggregator.get_error_count() == 0

    def test_error_aggregation_filter_by_context(self):
        """Test filtering errors by context."""
        aggregator = ErrorAggregator()

        aggregator.add_error(ValueError("error1"), {"agent": "agent1", "vendor": "microsoft"})
        aggregator.add_error(ValueError("error2"), {"agent": "agent2", "vendor": "redhat"})
        aggregator.add_error(KeyError("error3"), {"agent": "agent3", "vendor": "microsoft"})

        microsoft_errors = aggregator.get_errors_by_context("vendor", "microsoft")
        redhat_errors = aggregator.get_errors_by_context("vendor", "redhat")

        assert len(microsoft_errors) == 2
        assert len(redhat_errors) == 1
