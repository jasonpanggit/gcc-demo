"""Unit tests for golden dataset loader and contract validation.

Tests the YAML schema parsing, scenario loading, and contract
validation framework used by golden test scenarios.
"""
import os
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from tests.utils.golden_dataset_loader import (
    GoldenScenario,
    ExpectedContract,
    IntentContract,
    ToolPreference,
    ToolSequence,
    ToolSequenceStep,
    ResponseContract,
    QueryVariation,
    FixtureResponse,
    ContractViolation,
    ContractValidationResult,
    validate_contract,
    load_scenario,
    load_all_scenarios,
)


# ─────────────────────────── Helper Fixtures ────────────────────────────

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"

MINIMAL_SCENARIO_YAML = textwrap.dedent("""\
    scenario:
      name: test_minimal
      description: A minimal test scenario
      domain: test
      priority: normal

    queries:
      - text: "test query"
        canonical: true

    expected_contract:
      tools_required:
        - test_tool
""")

FULL_SCENARIO_YAML = textwrap.dedent("""\
    scenario:
      name: test_full
      description: A fully-featured test scenario
      domain: sre_health
      priority: critical

    queries:
      - text: "check health of container apps"
        canonical: true
      - text: "are my container apps healthy"
      - text: "container app health status"

    expected_contract:
      intent:
        domain: sre_health
        action: health_check
        resource_type: container_app

      tools_required:
        - container_app_list
        - check_container_app_health

      tools_preferred:
        - tool: container_app_list
          over: azure_resource_list
          reason: "More specific tool for container apps"

      tools_excluded:
        - speech
        - app_service

      tool_sequence:
        ordered: true
        steps:
          - tool: container_app_list
            purpose: "Discover container apps"
          - tool: check_container_app_health
            purpose: "Check health of each app"
            depends_on: container_app_list

      response_contract:
        must_contain_concepts:
          - "container app"
          - "health"
        format: structured_report
        min_length: 50

    fixture_responses:
      container_app_list:
        input: {}
        output:
          success: true
          data:
            container_apps:
              - name: "app-test"
                status: "Running"
      check_container_app_health:
        input:
          resource_name: "app-test"
        output:
          success: true
          data:
            health_status: "Healthy"
""")


def _write_temp_yaml(content: str, suffix: str = ".yaml") -> Path:
    """Write YAML content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return Path(path)


def _make_scenario(**overrides) -> GoldenScenario:
    """Create a GoldenScenario with sensible defaults, overrideable."""
    defaults = dict(
        name="test_scenario",
        description="Test",
        domain="test",
        priority="normal",
        queries=[QueryVariation(text="test query", canonical=True)],
        expected_contract=ExpectedContract(
            tools_required=["tool_a", "tool_b"],
        ),
        fixture_responses={},
    )
    defaults.update(overrides)
    return GoldenScenario(**defaults)


# ─────────────────────── load_scenario Tests ────────────────────────────


class TestLoadScenario:
    """Test loading individual scenario YAML files."""

    def test_load_minimal_scenario(self):
        path = _write_temp_yaml(MINIMAL_SCENARIO_YAML)
        try:
            scenario = load_scenario(path)
            assert scenario.name == "test_minimal"
            assert scenario.domain == "test"
            assert scenario.priority == "normal"
            assert len(scenario.queries) == 1
            assert scenario.canonical_query == "test query"
            assert "test_tool" in scenario.expected_contract.tools_required
        finally:
            os.unlink(path)

    def test_load_full_scenario(self):
        path = _write_temp_yaml(FULL_SCENARIO_YAML)
        try:
            scenario = load_scenario(path)
            assert scenario.name == "test_full"
            assert scenario.domain == "sre_health"
            assert scenario.priority == "critical"
            assert len(scenario.queries) == 3
            assert scenario.canonical_query == "check health of container apps"

            # Check intent
            assert scenario.expected_contract.intent is not None
            assert scenario.expected_contract.intent.domain == "sre_health"
            assert scenario.expected_contract.intent.action == "health_check"
            assert scenario.expected_contract.intent.resource_type == "container_app"

            # Check tools
            assert "container_app_list" in scenario.expected_contract.tools_required
            assert "check_container_app_health" in scenario.expected_contract.tools_required
            assert "speech" in scenario.expected_contract.tools_excluded

            # Check preferences
            prefs = scenario.expected_contract.tools_preferred
            assert len(prefs) == 1
            assert prefs[0].tool == "container_app_list"
            assert prefs[0].over == "azure_resource_list"

            # Check sequence
            seq = scenario.expected_contract.tool_sequence
            assert seq is not None
            assert seq.ordered is True
            assert len(seq.steps) == 2
            assert seq.steps[0].tool == "container_app_list"
            assert seq.steps[1].depends_on == "container_app_list"

            # Check response contract
            rc = scenario.expected_contract.response_contract
            assert rc is not None
            assert "container app" in rc.must_contain_concepts
            assert rc.min_length == 50
            assert rc.format == "structured_report"

            # Check fixtures
            assert "container_app_list" in scenario.fixture_responses
            assert scenario.fixture_responses["container_app_list"].output["success"] is True
        finally:
            os.unlink(path)

    def test_load_scenario_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_scenario("/nonexistent/path/scenario.yaml")

    def test_load_scenario_empty_file(self):
        path = _write_temp_yaml("")
        try:
            with pytest.raises(ValueError, match="Empty"):
                load_scenario(path)
        finally:
            os.unlink(path)

    def test_load_scenario_missing_scenario_section(self):
        yaml_content = textwrap.dedent("""\
            queries:
              - text: "test"
            expected_contract:
              tools_required:
                - test_tool
        """)
        path = _write_temp_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="Missing 'scenario'"):
                load_scenario(path)
        finally:
            os.unlink(path)

    def test_load_scenario_missing_queries(self):
        yaml_content = textwrap.dedent("""\
            scenario:
              name: no_queries
              description: Missing queries
              domain: test
              priority: normal
            expected_contract:
              tools_required:
                - test_tool
        """)
        path = _write_temp_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="No queries"):
                load_scenario(path)
        finally:
            os.unlink(path)

    def test_queries_string_shorthand(self):
        """Queries can be plain strings (not dicts with text/canonical)."""
        yaml_content = textwrap.dedent("""\
            scenario:
              name: string_queries
              description: String queries
              domain: test
              priority: normal
            queries:
              - "simple query one"
              - "simple query two"
            expected_contract:
              tools_required: []
        """)
        path = _write_temp_yaml(yaml_content)
        try:
            scenario = load_scenario(path)
            assert len(scenario.queries) == 2
            assert scenario.queries[0].text == "simple query one"
            assert scenario.queries[0].canonical is False
        finally:
            os.unlink(path)


# ─────────────────── load_all_scenarios Tests ───────────────────────────


class TestLoadAllScenarios:
    """Test loading all scenarios from a directory."""

    def test_load_from_real_scenarios_dir(self):
        """Load the actual scenarios directory if it exists."""
        if SCENARIOS_DIR.is_dir():
            scenarios = load_all_scenarios(SCENARIOS_DIR)
            assert len(scenarios) >= 1
            # All loaded scenarios should have valid names
            for s in scenarios:
                assert s.name, f"Scenario loaded from {SCENARIOS_DIR} has empty name"
                assert len(s.queries) > 0

    def test_load_from_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write two scenario files
            for name in ["a_scenario", "b_scenario"]:
                content = textwrap.dedent(f"""\
                    scenario:
                      name: {name}
                      description: Test
                      domain: test
                      priority: normal
                    queries:
                      - text: "query for {name}"
                        canonical: true
                    expected_contract:
                      tools_required:
                        - some_tool
                """)
                Path(tmpdir, f"{name}.yaml").write_text(content)

            scenarios = load_all_scenarios(tmpdir)
            assert len(scenarios) == 2
            assert scenarios[0].name == "a_scenario"  # sorted by filename
            assert scenarios[1].name == "b_scenario"

    def test_load_from_missing_dir(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_all_scenarios("/nonexistent/scenarios/")

    def test_load_ignores_non_yaml_files(self):
        """Only .yaml files should be loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # YAML file
            Path(tmpdir, "good.yaml").write_text(textwrap.dedent("""\
                scenario:
                  name: good
                  description: OK
                  domain: test
                  priority: normal
                queries:
                  - "query"
                expected_contract:
                  tools_required: []
            """))
            # Non-YAML file
            Path(tmpdir, "readme.md").write_text("# Not a scenario")

            scenarios = load_all_scenarios(tmpdir)
            assert len(scenarios) == 1
            assert scenarios[0].name == "good"


# ─────────────────── GoldenScenario Property Tests ──────────────────────


class TestGoldenScenarioProperties:
    """Test GoldenScenario computed properties."""

    def test_canonical_query_returns_canonical(self):
        scenario = _make_scenario(queries=[
            QueryVariation(text="query A", canonical=False),
            QueryVariation(text="query B", canonical=True),
            QueryVariation(text="query C", canonical=False),
        ])
        assert scenario.canonical_query == "query B"

    def test_canonical_query_fallback_to_first(self):
        """When no canonical is set, returns first query."""
        scenario = _make_scenario(queries=[
            QueryVariation(text="first query", canonical=False),
            QueryVariation(text="second query", canonical=False),
        ])
        assert scenario.canonical_query == "first query"

    def test_canonical_query_empty_queries(self):
        scenario = _make_scenario(queries=[])
        assert scenario.canonical_query == ""

    def test_all_query_texts(self):
        scenario = _make_scenario(queries=[
            QueryVariation(text="alpha", canonical=True),
            QueryVariation(text="beta"),
            QueryVariation(text="gamma"),
        ])
        assert scenario.all_query_texts == ["alpha", "beta", "gamma"]


# ──────────────────── validate_contract Tests ───────────────────────────


class TestValidateContract:
    """Test the contract validation framework."""

    def test_all_required_tools_present_passes(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_required=["tool_a", "tool_b"],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["tool_a", "tool_b", "tool_c"],
        )
        assert result.passed
        assert result.error_count == 0

    def test_missing_required_tool_fails(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_required=["tool_a", "tool_b"],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["tool_a"],
        )
        assert not result.passed
        assert result.error_count == 1
        assert "tool_b" in result.violations[0].message

    def test_excluded_tool_present_fails(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_excluded=["bad_tool"],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["good_tool", "bad_tool"],
        )
        assert not result.passed
        assert result.error_count == 1
        assert "bad_tool" in result.violations[0].message

    def test_excluded_tool_absent_passes(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_excluded=["bad_tool"],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["good_tool"],
        )
        assert result.passed

    def test_tool_preference_violation_is_warning(self):
        """Tool preference violations produce warnings, not errors."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_preferred=[
                    ToolPreference(
                        tool="preferred_tool",
                        over="less_preferred_tool",
                        reason="Better data",
                    )
                ],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["less_preferred_tool"],
        )
        # Preferences are warnings, not errors
        assert result.passed  # warnings don't cause failure
        assert result.warning_count == 1
        assert "preferred_tool" in result.warnings[0].message

    def test_tool_preference_satisfied(self):
        """When preferred tool is used, no warning."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_preferred=[
                    ToolPreference(tool="good", over="bad", reason="")
                ],
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["good"],
        )
        assert result.passed
        assert result.warning_count == 0

    def test_tool_sequence_correct_order_passes(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tool_sequence=ToolSequence(
                    ordered=True,
                    steps=[
                        ToolSequenceStep(tool="step_1"),
                        ToolSequenceStep(tool="step_2"),
                        ToolSequenceStep(tool="step_3"),
                    ],
                ),
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["step_1", "step_2", "step_3"],
            tool_call_order=["step_1", "step_2", "step_3"],
        )
        assert result.passed

    def test_tool_sequence_wrong_order_fails(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tool_sequence=ToolSequence(
                    ordered=True,
                    steps=[
                        ToolSequenceStep(tool="step_1"),
                        ToolSequenceStep(tool="step_2"),
                    ],
                ),
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["step_2", "step_1"],
            tool_call_order=["step_2", "step_1"],
        )
        assert not result.passed
        assert any("sequence" in v.check.lower() or "order" in v.message.lower()
                    for v in result.violations)

    def test_tool_sequence_with_extra_tools_passes(self):
        """Extra tools between sequence steps should be ignored."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tool_sequence=ToolSequence(
                    ordered=True,
                    steps=[
                        ToolSequenceStep(tool="first"),
                        ToolSequenceStep(tool="second"),
                    ],
                ),
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["first", "helper", "second"],
            tool_call_order=["first", "helper", "second"],
        )
        assert result.passed

    def test_response_contract_min_length_pass(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                response_contract=ResponseContract(min_length=10),
            )
        )
        result = validate_contract(
            scenario,
            response_text="This response is long enough to pass.",
        )
        assert result.passed

    def test_response_contract_min_length_fail(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                response_contract=ResponseContract(min_length=100),
            )
        )
        result = validate_contract(
            scenario,
            response_text="Short",
        )
        assert not result.passed
        assert any("too short" in v.message.lower() for v in result.violations)

    def test_response_contract_must_contain_concepts_pass(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                response_contract=ResponseContract(
                    must_contain_concepts=["container app", "health"],
                ),
            )
        )
        result = validate_contract(
            scenario,
            response_text="The container app health status shows everything is fine.",
        )
        assert result.passed

    def test_response_contract_must_contain_concepts_fail(self):
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                response_contract=ResponseContract(
                    must_contain_concepts=["container app", "missing_concept"],
                ),
            )
        )
        result = validate_contract(
            scenario,
            response_text="The container app is running fine.",
        )
        assert not result.passed
        assert any("missing_concept" in v.message for v in result.violations)

    def test_response_contract_case_insensitive(self):
        """Concept matching should be case-insensitive."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                response_contract=ResponseContract(
                    must_contain_concepts=["Container App"],
                ),
            )
        )
        result = validate_contract(
            scenario,
            response_text="the container app is running",
        )
        assert result.passed

    def test_empty_contract_passes(self):
        """An empty contract (no requirements) should always pass."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract()
        )
        result = validate_contract(
            scenario,
            tools_called=[],
            response_text="",
        )
        assert result.passed

    def test_combined_violations(self):
        """Multiple violations from different checks."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_required=["needed_tool"],
                tools_excluded=["forbidden_tool"],
                response_contract=ResponseContract(min_length=1000),
            )
        )
        result = validate_contract(
            scenario,
            tools_called=["forbidden_tool"],
            response_text="Short",
        )
        assert not result.passed
        assert result.error_count >= 3  # missing tool, excluded tool, short response

    def test_summary_output(self):
        """summary() should produce human-readable output."""
        scenario = _make_scenario(
            expected_contract=ExpectedContract(
                tools_required=["needed"],
            )
        )
        result = validate_contract(scenario, tools_called=[])
        assert "FAILED" in result.summary()
        assert "needed" in result.summary()

    def test_summary_passed(self):
        scenario = _make_scenario(expected_contract=ExpectedContract())
        result = validate_contract(scenario, tools_called=[])
        assert "PASSED" in result.summary()


# ────────────────── Real Scenario Integration Tests ─────────────────────


class TestRealScenarios:
    """Integration tests loading the actual scenario YAML files."""

    @pytest.mark.skipif(
        not SCENARIOS_DIR.is_dir(),
        reason="Scenarios directory not found",
    )
    def test_all_scenarios_parseable(self):
        """Every YAML file in scenarios/ should parse without errors."""
        scenarios = load_all_scenarios(SCENARIOS_DIR)
        assert len(scenarios) >= 1
        for scenario in scenarios:
            assert scenario.name
            assert len(scenario.queries) >= 1
            assert scenario.expected_contract is not None

    @pytest.mark.skipif(
        not SCENARIOS_DIR.is_dir(),
        reason="Scenarios directory not found",
    )
    def test_all_scenarios_have_canonical_query(self):
        """Every scenario should have at least one query (canonical or fallback)."""
        scenarios = load_all_scenarios(SCENARIOS_DIR)
        for scenario in scenarios:
            cq = scenario.canonical_query
            assert cq, f"Scenario '{scenario.name}' has no canonical query"

    @pytest.mark.skipif(
        not SCENARIOS_DIR.is_dir(),
        reason="Scenarios directory not found",
    )
    def test_container_app_health_scenario(self):
        """Validate the critical container_app_health scenario."""
        path = SCENARIOS_DIR / "container_app_health.yaml"
        if not path.exists():
            pytest.skip("container_app_health.yaml not found")

        scenario = load_scenario(path)
        assert scenario.name == "container_app_health"
        assert scenario.priority == "critical"
        assert "container_app_list" in scenario.expected_contract.tools_required
        assert "check_container_app_health" in scenario.expected_contract.tools_required
        assert scenario.expected_contract.tool_sequence is not None
        assert scenario.expected_contract.tool_sequence.ordered is True

    @pytest.mark.skipif(
        not SCENARIOS_DIR.is_dir(),
        reason="Scenarios directory not found",
    )
    def test_list_vms_scenario_prefers_specific_tool(self):
        """Validate list_vms scenario tool preferences."""
        path = SCENARIOS_DIR / "list_vms.yaml"
        if not path.exists():
            pytest.skip("list_vms.yaml not found")

        scenario = load_scenario(path)
        assert scenario.name == "list_vms"
        prefs = scenario.expected_contract.tools_preferred
        assert any(
            p.tool == "virtual_machine_list" and p.over == "virtual_machines"
            for p in prefs
        ), "Expected preference for virtual_machine_list over virtual_machines"
