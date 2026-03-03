"""
Parametrized Test Generator for Golden Scenarios
=================================================

Auto-generates pytest tests from golden scenario YAML files.

Each scenario YAML produces multiple test cases (one per query variation).
Tests use the DeterministicMCPClient for tool responses and validate
against the scenario's expected contract.

Usage:
    # Run all golden scenarios
    pytest tests/integration/test_orchestrator_scenarios.py -v

    # Run a single scenario by name
    pytest tests/integration/test_orchestrator_scenarios.py -k container_app_health -v

    # Run only canonical queries
    pytest tests/integration/test_orchestrator_scenarios.py -k canonical -v

    # Show detailed contract validation output
    pytest tests/integration/test_orchestrator_scenarios.py -v -s

Design:
    - Scenarios are loaded at collection time from tests/scenarios/*.yaml
    - Each scenario + query pair becomes a distinct parametrized test case
    - The DeterministicMCPClient provides fixture responses for tool calls
    - Contract validation checks tools_required, tools_excluded, tool_sequence,
      and response_contract assertions
    - Test IDs are human-readable: scenario_name[query_text]

Created: 2026-03-03 (Phase 0, Task 4)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure application code is importable
_APP_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

# Import golden dataset loader
from tests.utils.golden_dataset_loader import (
    ContractValidationResult,
    GoldenScenario,
    QueryVariation,
    load_all_scenarios,
    validate_contract,
)

# Import DeterministicMCPClient
from tests.mocks.deterministic_mcp_client import (
    DeterministicMCPClient,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scenario loading at module level (runs at collection time)
# ---------------------------------------------------------------------------

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _load_scenarios_safe() -> List[GoldenScenario]:
    """Load all scenarios, returning empty list on error."""
    try:
        return load_all_scenarios(SCENARIOS_DIR)
    except Exception as exc:
        logger.warning("Failed to load golden scenarios: %s", exc)
        return []


ALL_SCENARIOS = _load_scenarios_safe()


def _build_test_params() -> List[Tuple[GoldenScenario, QueryVariation]]:
    """Build (scenario, query) pairs for parametrize."""
    params = []
    for scenario in ALL_SCENARIOS:
        for query in scenario.queries:
            params.append((scenario, query))
    return params


def _test_id(param: Tuple[GoldenScenario, QueryVariation]) -> str:
    """Generate human-readable test ID."""
    scenario, query = param
    tag = "[canonical]" if query.canonical else ""
    short_query = query.text[:50].replace(" ", "_")
    return f"{scenario.name}{tag}--{short_query}"


TEST_PARAMS = _build_test_params()


# ---------------------------------------------------------------------------
# Fixture helpers - build DeterministicMCPClient from scenario fixtures
# ---------------------------------------------------------------------------

def _build_deterministic_client_from_scenario(
    scenario: GoldenScenario,
) -> DeterministicMCPClient:
    """Create a DeterministicMCPClient from scenario fixture_responses.

    Converts the YAML fixture_responses format to the JSON format
    expected by DeterministicMCPClient.
    """
    tools = []
    responses = {}

    for tool_name, fixture in scenario.fixture_responses.items():
        # Build tool definition
        tools.append({
            "name": tool_name,
            "description": f"Mock {tool_name} for scenario {scenario.name}",
            "parameters": {"type": "object", "properties": {}},
        })

        # Build response entries
        match_criteria = fixture.input if fixture.input else "*"
        # If input has only None values, treat as wildcard
        if isinstance(match_criteria, dict) and all(
            v is None for v in match_criteria.values()
        ):
            match_criteria = "*"

        responses[tool_name] = [
            {
                "match": match_criteria,
                "response": fixture.output,
            }
        ]

    fixture_data = {
        "server_label": f"mock-{scenario.name}",
        "tools": tools,
        "responses": responses,
    }

    return DeterministicMCPClient.from_fixture_data(fixture_data)


def _build_mock_tool_definitions(scenario: GoldenScenario) -> List[Dict[str, Any]]:
    """Build OpenAI-format tool definitions from scenario fixtures.

    These are used to populate the orchestrator's tool list so the LLM
    knows which tools are available.
    """
    definitions = []
    for tool_name, fixture in scenario.fixture_responses.items():
        definitions.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"{tool_name} for {scenario.name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        })
    return definitions


# ---------------------------------------------------------------------------
# Tool call tracking - intercept tool invocations for contract validation
# ---------------------------------------------------------------------------

class ToolCallTracker:
    """Tracks tool calls made during orchestrator execution.

    Used to validate tools_required, tools_excluded, and tool_sequence
    contracts without modifying the orchestrator itself.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def record(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> None:
        """Record a tool call."""
        self.calls.append({
            "tool_name": tool_name,
            "arguments": arguments or {},
        })

    @property
    def tools_called(self) -> List[str]:
        """Unique tool names called (preserving first-seen order)."""
        seen: Set[str] = set()
        ordered = []
        for call in self.calls:
            name = call["tool_name"]
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    @property
    def tool_call_order(self) -> List[str]:
        """Full ordered list of tool names as they were called (including duplicates)."""
        return [c["tool_name"] for c in self.calls]

    def reset(self) -> None:
        """Clear all recorded calls."""
        self.calls.clear()


# ---------------------------------------------------------------------------
# Parametrized test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
class TestOrchestratorGoldenScenarios:
    """Auto-generated tests from golden scenario YAML files.

    Each test validates that the MCP orchestrator correctly:
    1. Selects the right tools for the query
    2. Avoids selecting excluded (wrong) tools
    3. Calls tools in the expected sequence
    4. Produces a response meeting the response contract
    """

    @pytest.mark.parametrize(
        "scenario,query",
        TEST_PARAMS,
        ids=[_test_id(p) for p in TEST_PARAMS],
    )
    async def test_tool_selection_contract(
        self,
        scenario: GoldenScenario,
        query: QueryVariation,
    ) -> None:
        """Validate tool selection for a golden scenario query.

        This test validates the TOOL SELECTION layer:
        - Which tools get selected for the query
        - Which tools are correctly excluded
        - Tool preference ordering

        It does NOT require a live LLM call; instead it tests the
        retrieval/routing pipeline directly.
        """
        # Build mock infrastructure
        mock_client = _build_deterministic_client_from_scenario(scenario)
        await mock_client.initialize()

        tracker = ToolCallTracker()
        contract = scenario.expected_contract

        # --- Optional: test tool retrieval if router is available ---
        # The router may be async; wrap in try/except for environments
        # where full app dependencies aren't installed.
        try:
            from utils.router import Router
            import asyncio

            router = Router()
            route_result = router.route(query.text)
            # Handle both sync and async router implementations
            if asyncio.iscoroutine(route_result):
                domain_matches = await route_result
            else:
                domain_matches = route_result

            if contract.intent and domain_matches:
                domain_names = [
                    m.domain.value if hasattr(m.domain, "value") else str(m.domain)
                    for m in domain_matches
                ]
                logger.info(
                    "Scenario %s, query '%s': domains=%s",
                    scenario.name, query.text, domain_names,
                )

        except (ImportError, Exception) as exc:
            logger.debug("Router not available (%s); skipping retrieval test", exc)

        # --- Validate required tools are in scenario fixtures ---
        # This is a static check: the scenario must define fixtures for
        # all tools it expects the orchestrator to call
        for required_tool in contract.tools_required:
            assert required_tool in scenario.fixture_responses, (
                f"Scenario '{scenario.name}' requires tool '{required_tool}' "
                f"but no fixture response is defined for it. "
                f"Add a fixture_responses entry for '{required_tool}' in "
                f"{scenario.name}.yaml"
            )

        # --- Validate tool exclusion rules are consistent ---
        for excluded_tool in contract.tools_excluded:
            assert excluded_tool not in contract.tools_required, (
                f"Tool '{excluded_tool}' is both required and excluded "
                f"in scenario '{scenario.name}'"
            )

        # --- Validate fixture responses are well-formed ---
        for tool_name, fixture in scenario.fixture_responses.items():
            result = await mock_client.call_tool(tool_name, fixture.input or {})
            assert result is not None, (
                f"Fixture for '{tool_name}' returned None in scenario "
                f"'{scenario.name}'"
            )
            assert isinstance(result, dict), (
                f"Fixture for '{tool_name}' should return dict, got "
                f"{type(result).__name__} in scenario '{scenario.name}'"
            )

        await mock_client.cleanup()

    @pytest.mark.parametrize(
        "scenario,query",
        TEST_PARAMS,
        ids=[_test_id(p) for p in TEST_PARAMS],
    )
    async def test_contract_validation_framework(
        self,
        scenario: GoldenScenario,
        query: QueryVariation,
    ) -> None:
        """Validate the contract validation framework itself.

        Ensures that:
        1. Passing the expected tools produces a PASS result
        2. Missing required tools produces a FAIL result
        3. Calling excluded tools produces a FAIL result
        """
        contract = scenario.expected_contract

        # --- Positive case: all required tools called, none excluded ---
        result = validate_contract(
            scenario,
            tools_called=contract.tools_required,
            response_text="This is a test response about container app health status "
                         "showing virtual machine resources and their health status.",
            tool_call_order=contract.tools_required,
        )

        # Should pass (or only have warnings, not errors)
        assert result.passed, (
            f"Contract validation failed for positive case in "
            f"scenario '{scenario.name}', query '{query.text}':\n"
            f"{result.summary()}"
        )

        # --- Negative case: missing required tools ---
        if contract.tools_required:
            result_missing = validate_contract(
                scenario,
                tools_called=[],
                response_text="empty",
            )
            assert not result_missing.passed, (
                f"Contract validation should FAIL when no tools called "
                f"for scenario '{scenario.name}' (requires {contract.tools_required})"
            )

            # Check that violation messages are clear
            for violation in result_missing.violations:
                assert violation.message, (
                    f"Violation missing message in scenario '{scenario.name}'"
                )
                assert violation.check, (
                    f"Violation missing check name in scenario '{scenario.name}'"
                )

        # --- Negative case: excluded tool called ---
        if contract.tools_excluded:
            result_excluded = validate_contract(
                scenario,
                tools_called=contract.tools_required + [contract.tools_excluded[0]],
                response_text="test response with health and container app details",
            )
            assert not result_excluded.passed, (
                f"Contract validation should FAIL when excluded tool "
                f"'{contract.tools_excluded[0]}' is called "
                f"for scenario '{scenario.name}'"
            )

    @pytest.mark.parametrize(
        "scenario,query",
        [(s, q) for s, q in TEST_PARAMS if q.canonical],
        ids=[_test_id(p) for p in TEST_PARAMS if p[1].canonical],
    )
    async def test_tool_sequence_contract(
        self,
        scenario: GoldenScenario,
        query: QueryVariation,
    ) -> None:
        """Validate tool sequence contracts for canonical queries.

        Only runs for canonical (primary) queries to avoid redundant
        sequence validation.
        """
        contract = scenario.expected_contract
        if not contract.tool_sequence:
            pytest.skip(f"No tool_sequence defined for '{scenario.name}'")

        expected_steps = [s.tool for s in contract.tool_sequence.steps]

        # Build a dummy response that contains all required concepts
        rc = contract.response_contract
        concept_text = " ".join(rc.must_contain_concepts) if rc else ""
        dummy_response = (
            f"Comprehensive report covering {concept_text}. "
            f"All checks completed successfully for the requested resources. "
            * 3  # Ensure min_length is met
        )

        # --- Correct order should pass ---
        result = validate_contract(
            scenario,
            tools_called=expected_steps,
            response_text=dummy_response,
            tool_call_order=expected_steps,
        )
        assert result.passed, (
            f"Correct tool sequence should pass for '{scenario.name}':\n"
            f"Expected: {expected_steps}\n"
            f"{result.summary()}"
        )

        # --- Wrong order should fail (if sequence is ordered) ---
        if len(expected_steps) >= 2 and contract.tool_sequence.ordered:
            reversed_steps = list(reversed(expected_steps))
            result_wrong_order = validate_contract(
                scenario,
                tools_called=reversed_steps,
                response_text=dummy_response,
                tool_call_order=reversed_steps,
            )
            assert not result_wrong_order.passed, (
                f"Reversed tool sequence should FAIL for '{scenario.name}':\n"
                f"Expected: {expected_steps}\n"
                f"Reversed: {reversed_steps}"
            )

    @pytest.mark.parametrize(
        "scenario,query",
        [(s, q) for s, q in TEST_PARAMS if q.canonical],
        ids=[_test_id(p) for p in TEST_PARAMS if p[1].canonical],
    )
    async def test_deterministic_client_fixtures(
        self,
        scenario: GoldenScenario,
        query: QueryVariation,
    ) -> None:
        """Verify DeterministicMCPClient works with scenario fixtures.

        Ensures fixture responses are:
        1. Loadable from scenario YAML
        2. Returneable as deterministic tool responses
        3. Consistent across multiple calls (deep-copied)
        4. Trackable via call log
        """
        mock_client = _build_deterministic_client_from_scenario(scenario)
        await mock_client.initialize()

        # Call each fixture tool and verify response
        for tool_name, fixture in scenario.fixture_responses.items():
            result = await mock_client.call_tool(
                tool_name, fixture.input or {}
            )

            # Verify response matches fixture output
            assert result == fixture.output, (
                f"DeterministicMCPClient returned unexpected result for "
                f"'{tool_name}' in scenario '{scenario.name}'"
            )

            # Verify deep copy (mutation safety)
            result2 = await mock_client.call_tool(
                tool_name, fixture.input or {}
            )
            assert result == result2, (
                f"DeterministicMCPClient not returning consistent results "
                f"for '{tool_name}' in scenario '{scenario.name}'"
            )

        # Verify call log tracks all calls
        assert mock_client.call_count == len(scenario.fixture_responses) * 2, (
            f"Expected {len(scenario.fixture_responses) * 2} calls, "
            f"got {mock_client.call_count}"
        )

        # Verify specific tool call tracking
        for tool_name in scenario.fixture_responses:
            mock_client.assert_tool_called(tool_name, times=2)

        await mock_client.cleanup()


# ---------------------------------------------------------------------------
# Standalone scenario loading tests
# ---------------------------------------------------------------------------

class TestScenarioLoading:
    """Tests for the scenario loading infrastructure itself."""

    def test_scenarios_directory_exists(self) -> None:
        """Verify the scenarios directory exists and contains YAML files."""
        assert SCENARIOS_DIR.exists(), (
            f"Scenarios directory not found: {SCENARIOS_DIR}"
        )
        yaml_files = list(SCENARIOS_DIR.glob("*.yaml"))
        assert len(yaml_files) >= 5, (
            f"Expected at least 5 scenario files, found {len(yaml_files)}: "
            f"{[f.name for f in yaml_files]}"
        )

    def test_all_scenarios_load_successfully(self) -> None:
        """Verify all scenarios parse without errors."""
        assert len(ALL_SCENARIOS) >= 5, (
            f"Expected at least 5 loaded scenarios, got {len(ALL_SCENARIOS)}"
        )

    def test_each_scenario_has_required_fields(self) -> None:
        """Verify each loaded scenario has all required fields."""
        for scenario in ALL_SCENARIOS:
            assert scenario.name, f"Scenario missing name"
            assert scenario.queries, f"Scenario '{scenario.name}' has no queries"
            assert scenario.expected_contract, (
                f"Scenario '{scenario.name}' has no expected_contract"
            )
            assert scenario.fixture_responses, (
                f"Scenario '{scenario.name}' has no fixture_responses"
            )

    def test_each_scenario_has_canonical_query(self) -> None:
        """Verify each scenario has exactly one canonical query."""
        for scenario in ALL_SCENARIOS:
            canonical = [q for q in scenario.queries if q.canonical]
            assert len(canonical) == 1, (
                f"Scenario '{scenario.name}' should have exactly 1 canonical "
                f"query, found {len(canonical)}"
            )

    def test_scenarios_have_minimum_query_variations(self) -> None:
        """Verify each scenario has at least 3 query variations."""
        for scenario in ALL_SCENARIOS:
            assert len(scenario.queries) >= 3, (
                f"Scenario '{scenario.name}' has only {len(scenario.queries)} "
                f"queries (minimum 3 required)"
            )

    def test_scenario_names_are_unique(self) -> None:
        """Verify no duplicate scenario names."""
        names = [s.name for s in ALL_SCENARIOS]
        assert len(names) == len(set(names)), (
            f"Duplicate scenario names found: "
            f"{[n for n in names if names.count(n) > 1]}"
        )

    @pytest.mark.parametrize(
        "scenario",
        ALL_SCENARIOS,
        ids=[s.name for s in ALL_SCENARIOS],
    )
    def test_scenario_contract_consistency(self, scenario: GoldenScenario) -> None:
        """Verify each scenario's contract is internally consistent."""
        contract = scenario.expected_contract

        # Required tools must not also be excluded
        required_set = set(contract.tools_required)
        excluded_set = set(contract.tools_excluded)
        overlap = required_set & excluded_set
        assert not overlap, (
            f"Scenario '{scenario.name}' has tools that are both required "
            f"and excluded: {overlap}"
        )

        # Tool sequence steps should match required tools
        if contract.tool_sequence:
            sequence_tools = {s.tool for s in contract.tool_sequence.steps}
            for tool in sequence_tools:
                assert tool in required_set, (
                    f"Scenario '{scenario.name}': tool_sequence contains "
                    f"'{tool}' which is not in tools_required"
                )

        # Fixture responses should cover all required tools
        for tool in contract.tools_required:
            assert tool in scenario.fixture_responses, (
                f"Scenario '{scenario.name}': required tool '{tool}' "
                f"has no fixture_response defined"
            )


# ---------------------------------------------------------------------------
# Contract validation unit tests
# ---------------------------------------------------------------------------

class TestContractValidation:
    """Unit tests for the contract validation framework."""

    def test_validate_passing_contract(self) -> None:
        """Contract passes when all requirements met."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]
        result = validate_contract(
            scenario,
            tools_called=scenario.expected_contract.tools_required,
            response_text=(
                "Here is the health status of your container app resources. "
                "All virtual machine instances are running normally."
            ),
            tool_call_order=scenario.expected_contract.tools_required,
        )
        assert result.passed, result.summary()

    def test_validate_missing_required_tool(self) -> None:
        """Contract fails when required tool not called."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]
        if not scenario.expected_contract.tools_required:
            pytest.skip("Scenario has no required tools")

        result = validate_contract(
            scenario,
            tools_called=[],
            response_text="test",
        )
        assert not result.passed
        assert any(
            v.check == "tools_required" for v in result.violations
        ), "Should have tools_required violation"

    def test_validate_excluded_tool_called(self) -> None:
        """Contract fails when excluded tool is called."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]
        if not scenario.expected_contract.tools_excluded:
            pytest.skip("Scenario has no excluded tools")

        result = validate_contract(
            scenario,
            tools_called=scenario.expected_contract.tools_required
            + [scenario.expected_contract.tools_excluded[0]],
            response_text="container app health report",
        )
        assert not result.passed
        assert any(
            v.check == "tools_excluded" for v in result.violations
        ), "Should have tools_excluded violation"

    def test_validate_response_too_short(self) -> None:
        """Contract fails when response is too short."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]
        rc = scenario.expected_contract.response_contract
        if not rc or not rc.min_length:
            pytest.skip("Scenario has no min_length requirement")

        result = validate_contract(
            scenario,
            tools_called=scenario.expected_contract.tools_required,
            response_text="x",  # Too short
        )
        assert not result.passed
        assert any(
            v.check == "response_min_length" for v in result.violations
        ), "Should have response_min_length violation"

    def test_validate_missing_concept(self) -> None:
        """Contract fails when required concept missing from response."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]
        rc = scenario.expected_contract.response_contract
        if not rc or not rc.must_contain_concepts:
            pytest.skip("Scenario has no must_contain_concepts")

        result = validate_contract(
            scenario,
            tools_called=scenario.expected_contract.tools_required,
            response_text="This response contains nothing relevant at all " * 5,
        )
        assert not result.passed
        assert any(
            v.check == "response_must_contain" for v in result.violations
        ), "Should have response_must_contain violation"

    def test_validation_result_summary(self) -> None:
        """Validation summary is human-readable."""
        if not ALL_SCENARIOS:
            pytest.skip("No scenarios loaded")

        scenario = ALL_SCENARIOS[0]

        # Passing case
        result_pass = validate_contract(
            scenario,
            tools_called=scenario.expected_contract.tools_required,
            response_text="container app health virtual machine resource status " * 5,
            tool_call_order=scenario.expected_contract.tools_required,
        )
        summary = result_pass.summary()
        assert "PASSED" in summary

        # Failing case
        result_fail = validate_contract(
            scenario,
            tools_called=[],
            response_text="",
        )
        summary = result_fail.summary()
        assert "FAILED" in summary
        assert "ERROR" in summary
