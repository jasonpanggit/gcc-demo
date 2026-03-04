"""Tests for routing telemetry system.

Tests verify that routing decisions and execution results are captured
correctly for production monitoring and analysis.
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

try:
    from utils.routing_telemetry import (
        ConfidenceLevel,
        RoutingDecision,
        RoutingTelemetry,
        SelectionMethod,
        ToolCandidate,
        get_routing_telemetry,
    )
except ImportError:
    from app.agentic.eol.utils.routing_telemetry import (
        ConfidenceLevel,
        RoutingDecision,
        RoutingTelemetry,
        SelectionMethod,
        ToolCandidate,
        get_routing_telemetry,
    )


@pytest.fixture
def temp_telemetry_dir():
    """Create temporary directory for telemetry logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def telemetry(temp_telemetry_dir, monkeypatch):
    """Create telemetry instance with temp directory."""
    # Allow telemetry to work in tests by clearing the pytest marker
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    return RoutingTelemetry(
        enabled=True,
        log_dir=temp_telemetry_dir,
        sample_rate=1.0
    )


@pytest.fixture
def sample_candidates():
    """Sample tool candidates for testing."""
    return [
        ToolCandidate(
            tool_name="check_container_app_health",
            base_score=2.0,
            confidence_boost=1.3,
            final_score=2.6,
            matched_phrasing="check container app health",
            match_type="exact_substring"
        ),
        ToolCandidate(
            tool_name="container_app_list",
            base_score=1.0,
            confidence_boost=1.0,
            final_score=1.0,
            matched_phrasing="container app",
            match_type="partial"
        ),
    ]


class TestRoutingTelemetry:
    """Test routing telemetry capture and logging."""

    def test_telemetry_initialization_enabled(self, temp_telemetry_dir, monkeypatch):
        """Test telemetry initializes correctly when enabled."""
        # Allow telemetry in tests
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        telemetry = RoutingTelemetry(
            enabled=True,
            log_dir=temp_telemetry_dir,
            sample_rate=1.0
        )

        assert telemetry.enabled is True
        assert telemetry.sample_rate == 1.0
        assert Path(temp_telemetry_dir).exists()

    def test_telemetry_initialization_disabled(self, temp_telemetry_dir):
        """Test telemetry can be disabled."""
        telemetry = RoutingTelemetry(
            enabled=False,
            log_dir=temp_telemetry_dir,
            sample_rate=1.0
        )

        assert telemetry.enabled is False

    def test_telemetry_disabled_in_test_env(self, temp_telemetry_dir, monkeypatch):
        """Test telemetry automatically disables in test environment."""
        # Mock config to return test environment
        class MockConfig:
            class app:
                env = "test"

        try:
            monkeypatch.setattr("utils.routing_telemetry.config", MockConfig())
        except:
            monkeypatch.setattr("app.agentic.eol.utils.routing_telemetry.config", MockConfig())

        telemetry = RoutingTelemetry(
            enabled=True,  # Try to enable
            log_dir=temp_telemetry_dir,
            sample_rate=1.0
        )

        # Should be disabled due to test environment
        assert telemetry.enabled is False

    def test_log_routing_decision(self, telemetry, temp_telemetry_dir, sample_candidates):
        """Test routing decision is logged correctly."""
        query = "check container app health"
        selected_tools = ["container_app_list", "check_container_app_health"]
        prerequisite_chains = {
            "check_container_app_health": ["container_app_list"]
        }

        telemetry.log_routing_decision(
            query=query,
            selected_tools=selected_tools,
            candidates=sample_candidates,
            selection_method=SelectionMethod.METADATA_MATCH,
            prerequisite_chains=prerequisite_chains,
            session_id="test-session-123"
        )

        # Verify log file was created
        log_files = list(Path(temp_telemetry_dir).glob("routing_*.jsonl"))
        assert len(log_files) == 1

        # Read and verify log entry
        with open(log_files[0]) as f:
            log_entry = json.loads(f.read())

        assert log_entry["query"] == query
        assert log_entry["selected_tools"] == selected_tools
        assert log_entry["selection_method"] == "metadata_match"
        assert log_entry["prerequisite_injection"] == prerequisite_chains
        assert log_entry["session_id"] == "test-session-123"
        assert log_entry["confidence_level"] == "high"  # top score >= 2.0
        assert len(log_entry["candidates"]) == 2

    def test_confidence_classification_high(self, telemetry):
        """Test high confidence classification (score >= 2.0)."""
        candidates = [
            ToolCandidate("tool1", 2.0, 1.5, 3.0, "match", "exact")
        ]

        confidence = telemetry._classify_confidence(candidates)
        assert confidence == ConfidenceLevel.HIGH

    def test_confidence_classification_medium(self, telemetry):
        """Test medium confidence classification (1.5 <= score < 2.0)."""
        candidates = [
            ToolCandidate("tool1", 1.5, 1.2, 1.8, "match", "exact")
        ]

        confidence = telemetry._classify_confidence(candidates)
        assert confidence == ConfidenceLevel.MEDIUM

    def test_confidence_classification_low(self, telemetry):
        """Test low confidence classification (score < 1.5)."""
        candidates = [
            ToolCandidate("tool1", 1.0, 1.0, 1.0, "match", "partial")
        ]

        confidence = telemetry._classify_confidence(candidates)
        assert confidence == ConfidenceLevel.LOW

    def test_confidence_classification_empty(self, telemetry):
        """Test confidence classification with no candidates."""
        confidence = telemetry._classify_confidence([])
        assert confidence == ConfidenceLevel.LOW

    def test_log_execution_result(self, telemetry, temp_telemetry_dir):
        """Test execution result is logged correctly."""
        query = "check health"

        telemetry.log_execution_result(
            query=query,
            success=True,
            execution_time_ms=1250,
            session_id="test-session-123"
        )

        # Verify execution log file was created
        log_files = list(Path(temp_telemetry_dir).glob("execution_*.jsonl"))
        assert len(log_files) == 1

        # Read and verify log entry
        with open(log_files[0]) as f:
            log_entry = json.loads(f.read())

        assert log_entry["event_type"] == "execution_result"
        assert log_entry["query"] == query
        assert log_entry["success"] is True
        assert log_entry["execution_time_ms"] == 1250
        assert log_entry["session_id"] == "test-session-123"

    def test_log_user_correction(self, telemetry, temp_telemetry_dir):
        """Test user correction is logged correctly."""
        query = "check health"
        original_tool = "check_resource_health"
        corrected_tool = "check_container_app_health"

        telemetry.log_user_correction(
            query=query,
            original_tool=original_tool,
            corrected_tool=corrected_tool,
            session_id="test-session-123"
        )

        # Verify correction log file was created
        log_files = list(Path(temp_telemetry_dir).glob("corrections_*.jsonl"))
        assert len(log_files) == 1

        # Read and verify log entry
        with open(log_files[0]) as f:
            log_entry = json.loads(f.read())

        assert log_entry["event_type"] == "user_correction"
        assert log_entry["query"] == query
        assert log_entry["original_tool"] == original_tool
        assert log_entry["corrected_tool"] == corrected_tool
        assert log_entry["session_id"] == "test-session-123"

    def test_sampling_rate_zero(self, temp_telemetry_dir):
        """Test that sample_rate=0 prevents all logging."""
        telemetry = RoutingTelemetry(
            enabled=True,
            log_dir=temp_telemetry_dir,
            sample_rate=0.0  # Never log
        )

        # Try to log
        telemetry.log_routing_decision(
            query="test",
            selected_tools=["tool1"],
            candidates=[],
            selection_method=SelectionMethod.METADATA_MATCH
        )

        # No log files should be created
        log_files = list(Path(temp_telemetry_dir).glob("*.jsonl"))
        assert len(log_files) == 0

    def test_multiple_log_entries_same_day(self, telemetry, temp_telemetry_dir, sample_candidates):
        """Test multiple entries are appended to same daily log file."""
        for i in range(3):
            telemetry.log_routing_decision(
                query=f"query {i}",
                selected_tools=["tool1"],
                candidates=sample_candidates,
                selection_method=SelectionMethod.METADATA_MATCH
            )

        # Should have one log file
        log_files = list(Path(temp_telemetry_dir).glob("routing_*.jsonl"))
        assert len(log_files) == 1

        # Should have 3 entries
        with open(log_files[0]) as f:
            entries = [json.loads(line) for line in f]

        assert len(entries) == 3
        assert entries[0]["query"] == "query 0"
        assert entries[1]["query"] == "query 1"
        assert entries[2]["query"] == "query 2"

    def test_telemetry_when_disabled(self, temp_telemetry_dir, sample_candidates):
        """Test that no logs are created when telemetry is disabled."""
        telemetry = RoutingTelemetry(
            enabled=False,
            log_dir=temp_telemetry_dir,
            sample_rate=1.0
        )

        # Try to log
        telemetry.log_routing_decision(
            query="test",
            selected_tools=["tool1"],
            candidates=sample_candidates,
            selection_method=SelectionMethod.METADATA_MATCH
        )

        telemetry.log_execution_result(
            query="test",
            success=True,
            execution_time_ms=100
        )

        # No log files should be created
        log_files = list(Path(temp_telemetry_dir).glob("*.jsonl"))
        assert len(log_files) == 0

    def test_get_routing_telemetry_singleton(self, monkeypatch):
        """Test that get_routing_telemetry returns singleton instance."""
        # Allow telemetry in tests
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Set environment variables
        monkeypatch.setenv("ROUTING_TELEMETRY_ENABLED", "true")
        monkeypatch.setenv("ROUTING_TELEMETRY_LOG_DIR", "./test_logs")
        monkeypatch.setenv("ROUTING_TELEMETRY_SAMPLE_RATE", "0.5")

        # Reset singleton
        try:
            import utils.routing_telemetry as rt_module
        except ImportError:
            import app.agentic.eol.utils.routing_telemetry as rt_module
        rt_module._telemetry = None

        # Get instance
        telemetry1 = get_routing_telemetry()
        telemetry2 = get_routing_telemetry()

        # Should be same instance
        assert telemetry1 is telemetry2
        assert telemetry1.enabled is True
        assert telemetry1.sample_rate == 0.5

    def test_prerequisite_chains_none_handling(self, telemetry, temp_telemetry_dir, sample_candidates):
        """Test that None prerequisite chains are handled correctly."""
        telemetry.log_routing_decision(
            query="test",
            selected_tools=["tool1"],
            candidates=sample_candidates,
            selection_method=SelectionMethod.METADATA_MATCH,
            prerequisite_chains=None  # Explicitly None
        )

        # Read log entry
        log_files = list(Path(temp_telemetry_dir).glob("routing_*.jsonl"))
        with open(log_files[0]) as f:
            log_entry = json.loads(f.read())

        # Should be empty dict, not None
        assert log_entry["prerequisite_injection"] == {}

    def test_error_handling_in_log_writing(self, telemetry, sample_candidates, monkeypatch):
        """Test that logging errors are caught and logged."""
        # Make directory read-only to force write error
        import builtins
        original_open = builtins.open

        def failing_open(*args, **kwargs):
            if 'routing_' in str(args[0]):
                raise PermissionError("Cannot write")
            return original_open(*args, **kwargs)

        monkeypatch.setattr(builtins, 'open', failing_open)

        # Should not raise, just log error
        telemetry.log_routing_decision(
            query="test",
            selected_tools=["tool1"],
            candidates=sample_candidates,
            selection_method=SelectionMethod.METADATA_MATCH
        )


class TestToolCandidate:
    """Test ToolCandidate dataclass."""

    def test_tool_candidate_creation(self):
        """Test ToolCandidate can be created with all fields."""
        candidate = ToolCandidate(
            tool_name="test_tool",
            base_score=2.0,
            confidence_boost=1.5,
            final_score=3.0,
            matched_phrasing="test query",
            match_type="exact"
        )

        assert candidate.tool_name == "test_tool"
        assert candidate.base_score == 2.0
        assert candidate.confidence_boost == 1.5
        assert candidate.final_score == 3.0
        assert candidate.matched_phrasing == "test query"
        assert candidate.match_type == "exact"

    def test_tool_candidate_optional_fields(self):
        """Test ToolCandidate with optional fields as None."""
        candidate = ToolCandidate(
            tool_name="test_tool",
            base_score=1.0,
            confidence_boost=1.0,
            final_score=1.0
        )

        assert candidate.matched_phrasing is None
        assert candidate.match_type is None


class TestSelectionMethod:
    """Test SelectionMethod enum."""

    def test_selection_method_values(self):
        """Test all selection method enum values."""
        assert SelectionMethod.METADATA_MATCH.value == "metadata_match"
        assert SelectionMethod.EMBEDDING_FALLBACK.value == "embedding_fallback"
        assert SelectionMethod.CLI_ESCAPE.value == "cli_escape"
        assert SelectionMethod.LLM_PLANNER.value == "llm_planner"


class TestConfidenceLevel:
    """Test ConfidenceLevel enum."""

    def test_confidence_level_values(self):
        """Test all confidence level enum values."""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
