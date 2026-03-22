"""Integration tests for orchestrator rewiring (ORCH-01, ORCH-02, SRC-01, RES-01).

Verifies:
- All 5 public method signatures are unchanged
- Legacy dispatch methods are removed
- Response shape includes sources and discrepancies
- OrchestratorAgent backward-compat alias works
- Orchestrator file is under 500 lines
"""
import inspect
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.eol_orchestrator import EOLOrchestratorAgent, OrchestratorAgent


class TestMethodSignatures:
    """ORCH-02: All 5 public method signatures must be unchanged."""

    def test_get_autonomous_eol_data_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.get_autonomous_eol_data)
        params = list(sig.parameters.keys())
        assert params == [
            "self", "software_name", "version", "item_type",
            "search_internet_only", "search_include_internet",
            "search_ignore_cache", "search_agent_only",
        ]

    def test_get_eol_data_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.get_eol_data)
        params = list(sig.parameters.keys())
        assert params == ["self", "software_name", "version"]

    def test_search_software_eol_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.search_software_eol)
        params = list(sig.parameters.keys())
        assert params == [
            "self", "software_name", "software_version", "search_hints",
            "search_include_internet", "search_ignore_cache", "search_agent_only",
        ]

    def test_get_os_inventory_with_eol_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.get_os_inventory_with_eol)
        params = list(sig.parameters.keys())
        assert params == ["self", "days"]

    def test_health_check_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.health_check)
        params = list(sig.parameters.keys())
        assert params == ["self"]


class TestBackwardCompat:
    """Backward compatibility checks."""

    def test_orchestrator_agent_alias_exists(self):
        assert OrchestratorAgent is EOLOrchestratorAgent

    def test_search_software_eol_internet_exists(self):
        assert hasattr(EOLOrchestratorAgent, "search_software_eol_internet")

    def test_search_software_eol_internet_signature(self):
        sig = inspect.signature(EOLOrchestratorAgent.search_software_eol_internet)
        params = list(sig.parameters.keys())
        assert "search_ignore_cache" in params
        assert "search_internet_only" not in params  # internal param, not exposed


class TestResponseShape:
    """Verify response dict keys include sources and discrepancies."""

    @pytest.mark.asyncio
    async def test_empty_name_response_shape(self):
        """Empty software_name returns error with correct keys."""
        orch = EOLOrchestratorAgent.__new__(EOLOrchestratorAgent)
        import datetime
        orch._comms_log = []
        orch.session_id = "test-session"
        orch.start_time = datetime.datetime.now(datetime.timezone.utc)
        orch.eol_agent_responses = []
        orch.eol_cache = {}

        result = await orch.get_autonomous_eol_data("")
        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    def test_sources_key_in_success_response_shape(self):
        """sources and discrepancies must be listed as required response keys."""
        # Verify the method body uses the correct keys by inspecting source
        import inspect as ins
        src = ins.getsource(EOLOrchestratorAgent.get_autonomous_eol_data)
        assert '"sources"' in src
        assert '"discrepancies"' in src
        assert "sources_as_dicts()" in src
        assert "discrepancies_as_dicts()" in src


class TestLegacyMethodsRemoved:
    """Verify legacy dispatch methods are gone (SRC-01, ORCH-01)."""

    def test_no_route_to_agents(self):
        assert not hasattr(EOLOrchestratorAgent, "_route_to_agents")

    def test_no_calculate_confidence_v1(self):
        assert not hasattr(EOLOrchestratorAgent, "_calculate_confidence_v1")

    def test_no_calculate_confidence(self):
        assert not hasattr(EOLOrchestratorAgent, "_calculate_confidence")

    def test_no_invoke_agent(self):
        assert not hasattr(EOLOrchestratorAgent, "_invoke_agent")

    def test_no_agent_tier(self):
        assert not hasattr(EOLOrchestratorAgent, "_agent_tier")

    def test_no_normalize_software_name(self):
        assert not hasattr(EOLOrchestratorAgent, "_normalize_software_name")

    def test_no_software_name_matches(self):
        assert not hasattr(EOLOrchestratorAgent, "_software_name_matches")

    def test_no_version_matches_exact(self):
        assert not hasattr(EOLOrchestratorAgent, "_version_matches_exact")


class TestPipelineWired:
    """Verify pipeline attributes are present after __init__."""

    def test_pipeline_attributes_exist(self):
        """Class must define the three pipeline attributes."""
        import inspect as ins
        src = ins.getsource(EOLOrchestratorAgent.__init__)
        assert "_pipeline_registry" in src
        assert "_pipeline" in src
        assert "_aggregator" in src

    def test_no_vendor_routing_on_init(self):
        """self.vendor_routing is no longer set by __init__."""
        import inspect as ins
        src = ins.getsource(EOLOrchestratorAgent.__init__)
        assert "self.vendor_routing" not in src


class TestOrchestratorLineCount:
    """ORCH-01: Orchestrator should be <500 lines."""

    def test_file_under_500_lines(self):
        filepath = os.path.join(os.path.dirname(__file__), "..", "agents", "eol_orchestrator.py")
        with open(filepath) as f:
            line_count = sum(1 for _ in f)
        assert line_count < 500, f"Orchestrator is {line_count} lines (target: <500)"
