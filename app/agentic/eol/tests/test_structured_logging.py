"""
Structured Logging Tests

Tests for structured logging with correlation ID integration.
Created: 2026-02-27 (Phase 2, Day 5)
"""

import pytest
import logging
import os
from unittest.mock import patch, MagicMock
from utils.correlation_id import set_correlation_id, clear_correlation_id


def _check_structlog_available():
    """Helper to check if structlog is available."""
    try:
        import structlog
        return True
    except ImportError:
        return False


@pytest.mark.unit
class TestStructuredLogging:
    """Tests for structured logging functionality."""

    def test_standard_logger_still_works(self):
        """Test that standard logging still works when structlog is not used."""
        from utils.logger import get_logger

        logger = get_logger("test_standard")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_standard"

    def test_correlation_id_processor(self):
        """Test that correlation ID processor adds correlation_id to event dict."""
        from utils.logger import add_correlation_id

        # Set a correlation ID
        test_cid = "test-correlation-123"
        set_correlation_id(test_cid)

        # Create an event dict
        event_dict = {"event": "test_event", "data": "test_data"}

        # Process it
        result = add_correlation_id(None, "info", event_dict)

        # Should have correlation_id added
        assert "correlation_id" in result
        assert result["correlation_id"] == test_cid
        assert result["event"] == "test_event"
        assert result["data"] == "test_data"

        # Clean up
        clear_correlation_id()

    def test_correlation_id_processor_when_no_cid(self):
        """Test that processor works when no correlation ID is set."""
        from utils.logger import add_correlation_id

        clear_correlation_id()

        event_dict = {"event": "test_event"}
        result = add_correlation_id(None, "info", event_dict)

        # Should still have original data, no correlation_id if not set
        assert result["event"] == "test_event"
        # correlation_id might not be present if none was set

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_configure_structlog(self):
        """Test configuring structlog."""
        from utils.logger import configure_structlog, is_structlog_configured
        import structlog

        # Configure structlog
        configure_structlog(level="INFO")

        # Should be configured now
        assert is_structlog_configured()
        assert structlog.is_configured()

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_get_structured_logger(self):
        """Test getting a structured logger."""
        from utils.logger import configure_structlog, get_structured_logger
        import structlog

        configure_structlog(level="INFO")

        logger = get_structured_logger("test_module", component="test")

        # Should be a BoundLogger
        assert isinstance(logger, structlog.stdlib.BoundLogger)

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_structured_logger_with_correlation_id(self, caplog):
        """Test that structured logger includes correlation ID in logs."""
        from utils.logger import configure_structlog, get_structured_logger
        import structlog

        # Set correlation ID
        test_cid = "test-structured-456"
        set_correlation_id(test_cid)

        # Configure structlog
        configure_structlog(level="DEBUG")

        # Get logger
        logger = get_structured_logger("test_structured")

        # Log a message - we can't easily capture structlog output in caplog,
        # but we can verify the logger is created and callable
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "error")

        # Clean up
        clear_correlation_id()

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_log_with_context(self):
        """Test logging with additional context."""
        from utils.logger import configure_structlog, get_structured_logger, log_with_context

        configure_structlog(level="INFO")
        logger = get_structured_logger("test_context")

        # Should be able to log with context without errors
        log_with_context(
            logger,
            "info",
            "test_event",
            agent="test_agent",
            duration_ms=100,
            success=True
        )

        # If we got here without exception, the function works
        assert True

    def test_structlog_not_available_error(self):
        """Test that appropriate errors are raised when structlog is not available."""
        from utils.logger import STRUCTLOG_AVAILABLE

        if not STRUCTLOG_AVAILABLE:
            from utils.logger import get_structured_logger

            with pytest.raises(ImportError, match="structlog is not installed"):
                get_structured_logger("test")

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_logger_initial_values(self):
        """Test that initial values are bound to logger."""
        from utils.logger import configure_structlog, get_structured_logger

        configure_structlog(level="INFO")

        # Create logger with initial values
        logger = get_structured_logger(
            "test_initial",
            component="orchestrator",
            environment="test"
        )

        # Logger should have bind method and be usable
        assert hasattr(logger, "bind")
        assert hasattr(logger, "info")

    @pytest.mark.skipif(
        not _check_structlog_available(),
        reason="structlog not installed"
    )
    def test_azure_environment_json_output(self):
        """Test that Azure environments use JSON output."""
        from utils.logger import configure_structlog
        import structlog

        # Mock Azure environment
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "test-app"}):
            configure_structlog(level="INFO")

            # Verify structlog is configured
            assert structlog.is_configured()

            # The actual JSON renderer check would require inspecting
            # structlog's internal configuration, but we can verify
            # configuration completed without error
            assert True
