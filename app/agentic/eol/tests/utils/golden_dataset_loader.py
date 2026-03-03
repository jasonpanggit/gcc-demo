"""
Golden Dataset Loader - Loads and validates YAML scenario files for orchestrator testing.

This module provides the infrastructure to:
1. Parse golden scenario YAML files
2. Validate scenario structure
3. Load fixture responses for deterministic testing
4. Validate response contracts against actual orchestrator output
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import yaml


# ---------------------------------------------------------------------------
# Schema dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QueryVariation:
    """A single query phrasing to test."""
    text: str
    canonical: bool = False


@dataclass
class IntentContract:
    """Expected intent classification for the scenario."""
    domain: str
    action: str
    resource_type: str


@dataclass
class ToolPreference:
    """Declares that one tool should be chosen over another."""
    tool: str
    over: str
    reason: str = ""


@dataclass
class ToolSequenceStep:
    """A single step in an expected tool execution sequence."""
    tool: str
    purpose: str = ""
    depends_on: Optional[str] = None


@dataclass
class ToolSequence:
    """Expected tool execution order."""
    ordered: bool = True
    steps: List[ToolSequenceStep] = field(default_factory=list)


@dataclass
class ResponseContract:
    """Expected properties of the final response."""
    must_contain_concepts: List[str] = field(default_factory=list)
    format: str = "any"  # structured_report | list_or_table | any
    min_length: int = 0


@dataclass
class ExpectedContract:
    """Full expected behavior contract for a scenario."""
    intent: Optional[IntentContract] = None
    tools_required: List[str] = field(default_factory=list)
    tools_preferred: List[ToolPreference] = field(default_factory=list)
    tools_excluded: List[str] = field(default_factory=list)
    tool_sequence: Optional[ToolSequence] = None
    response_contract: Optional[ResponseContract] = None


@dataclass
class FixtureResponse:
    """Deterministic response for a single tool call."""
    tool_name: str
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldenScenario:
    """Complete golden test scenario loaded from YAML."""
    name: str
    description: str
    domain: str
    priority: str
    queries: List[QueryVariation]
    expected_contract: ExpectedContract
    fixture_responses: Dict[str, FixtureResponse]

    @property
    def canonical_query(self) -> str:
        """Return the canonical (primary) query text."""
        for q in self.queries:
            if q.canonical:
                return q.text
        return self.queries[0].text if self.queries else ""

    @property
    def all_query_texts(self) -> List[str]:
        """Return all query variation texts."""
        return [q.text for q in self.queries]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _parse_queries(raw: List[Any]) -> List[QueryVariation]:
    """Parse query variations from YAML."""
    queries = []
    for item in raw:
        if isinstance(item, str):
            queries.append(QueryVariation(text=item))
        elif isinstance(item, dict):
            queries.append(QueryVariation(
                text=item["text"],
                canonical=item.get("canonical", False),
            ))
    return queries


def _parse_intent(raw: Optional[Dict[str, Any]]) -> Optional[IntentContract]:
    """Parse intent contract."""
    if not raw:
        return None
    return IntentContract(
        domain=raw.get("domain", ""),
        action=raw.get("action", ""),
        resource_type=raw.get("resource_type", ""),
    )


def _parse_tool_preferences(raw: Optional[List[Dict[str, Any]]]) -> List[ToolPreference]:
    """Parse tool preference declarations."""
    if not raw:
        return []
    return [
        ToolPreference(
            tool=item["tool"],
            over=item["over"],
            reason=item.get("reason", ""),
        )
        for item in raw
    ]


def _parse_tool_sequence(raw: Optional[Dict[str, Any]]) -> Optional[ToolSequence]:
    """Parse expected tool sequence."""
    if not raw:
        return None
    steps = []
    for step in raw.get("steps", []):
        steps.append(ToolSequenceStep(
            tool=step["tool"],
            purpose=step.get("purpose", ""),
            depends_on=step.get("depends_on"),
        ))
    return ToolSequence(
        ordered=raw.get("ordered", True),
        steps=steps,
    )


def _parse_response_contract(raw: Optional[Dict[str, Any]]) -> Optional[ResponseContract]:
    """Parse response contract."""
    if not raw:
        return None
    return ResponseContract(
        must_contain_concepts=raw.get("must_contain_concepts", []),
        format=raw.get("format", "any"),
        min_length=raw.get("min_length", 0),
    )


def _parse_expected_contract(raw: Dict[str, Any]) -> ExpectedContract:
    """Parse the full expected contract from YAML."""
    return ExpectedContract(
        intent=_parse_intent(raw.get("intent")),
        tools_required=raw.get("tools_required", []),
        tools_preferred=_parse_tool_preferences(raw.get("tools_preferred")),
        tools_excluded=raw.get("tools_excluded", []),
        tool_sequence=_parse_tool_sequence(raw.get("tool_sequence")),
        response_contract=_parse_response_contract(raw.get("response_contract")),
    )


def _parse_fixtures(raw: Optional[Dict[str, Any]]) -> Dict[str, FixtureResponse]:
    """Parse fixture responses for tool calls."""
    if not raw:
        return {}
    fixtures = {}
    for tool_name, fixture_data in raw.items():
        fixtures[tool_name] = FixtureResponse(
            tool_name=tool_name,
            input=fixture_data.get("input", {}),
            output=fixture_data.get("output", {}),
        )
    return fixtures


def load_scenario(file_path: str | Path) -> GoldenScenario:
    """Load a single golden scenario from a YAML file.

    Args:
        file_path: Absolute or relative path to the YAML file.

    Returns:
        Parsed GoldenScenario dataclass.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML structure is invalid.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty scenario file: {path}")

    scenario_data = data.get("scenario", {})
    if not scenario_data:
        raise ValueError(f"Missing 'scenario' section in {path}")

    queries = _parse_queries(data.get("queries", []))
    if not queries:
        raise ValueError(f"No queries defined in {path}")

    expected_contract = _parse_expected_contract(data.get("expected_contract", {}))
    fixture_responses = _parse_fixtures(data.get("fixture_responses"))

    return GoldenScenario(
        name=scenario_data.get("name", path.stem),
        description=scenario_data.get("description", ""),
        domain=scenario_data.get("domain", ""),
        priority=scenario_data.get("priority", "normal"),
        queries=queries,
        expected_contract=expected_contract,
        fixture_responses=fixture_responses,
    )


def load_all_scenarios(
    scenarios_dir: Optional[str | Path] = None,
) -> List[GoldenScenario]:
    """Load all golden scenarios from the scenarios directory.

    Args:
        scenarios_dir: Directory containing YAML scenario files.
                       Defaults to ``tests/scenarios/`` relative to this file.

    Returns:
        List of parsed GoldenScenario instances, sorted by name.
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent.parent / "scenarios"
    else:
        scenarios_dir = Path(scenarios_dir)

    if not scenarios_dir.is_dir():
        raise FileNotFoundError(f"Scenarios directory not found: {scenarios_dir}")

    scenarios = []
    for yaml_file in sorted(scenarios_dir.glob("*.yaml")):
        scenarios.append(load_scenario(yaml_file))
    return scenarios


# ---------------------------------------------------------------------------
# Contract Validation
# ---------------------------------------------------------------------------

@dataclass
class ContractViolation:
    """A single contract violation found during validation."""
    check: str
    expected: Any
    actual: Any
    message: str
    severity: str = "error"  # error | warning


@dataclass
class ContractValidationResult:
    """Result of validating response against contract."""
    passed: bool
    violations: List[ContractViolation] = field(default_factory=list)
    warnings: List[ContractViolation] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.violations)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> str:
        """Human-readable summary of validation results."""
        if self.passed:
            return f"PASSED ({self.warning_count} warnings)"
        lines = [f"FAILED ({self.error_count} errors, {self.warning_count} warnings)"]
        for v in self.violations:
            lines.append(f"  ERROR [{v.check}]: {v.message}")
        for w in self.warnings:
            lines.append(f"  WARN  [{w.check}]: {w.message}")
        return "\n".join(lines)


def validate_contract(
    scenario: GoldenScenario,
    *,
    tools_called: Sequence[str] = (),
    response_text: str = "",
    tool_call_order: Optional[Sequence[str]] = None,
) -> ContractValidationResult:
    """Validate actual orchestrator output against scenario's expected contract.

    Args:
        scenario:         The golden scenario defining the contract.
        tools_called:     Set of tool names that were invoked.
        response_text:    Final response text from the orchestrator.
        tool_call_order:  Ordered list of tools as they were called (for sequence checks).

    Returns:
        ContractValidationResult with pass/fail and violation details.
    """
    contract = scenario.expected_contract
    violations: List[ContractViolation] = []
    warnings: List[ContractViolation] = []

    called_set: Set[str] = set(tools_called)

    # -- Required tools --
    for required_tool in contract.tools_required:
        if required_tool not in called_set:
            violations.append(ContractViolation(
                check="tools_required",
                expected=required_tool,
                actual=sorted(called_set),
                message=f"Required tool '{required_tool}' was NOT called. "
                        f"Called tools: {sorted(called_set)}",
            ))

    # -- Excluded tools --
    for excluded_tool in contract.tools_excluded:
        if excluded_tool in called_set:
            violations.append(ContractViolation(
                check="tools_excluded",
                expected=f"NOT {excluded_tool}",
                actual=sorted(called_set),
                message=f"Excluded tool '{excluded_tool}' was incorrectly called. "
                        f"This tool should never be selected for this scenario.",
            ))

    # -- Tool preferences (warnings, not errors) --
    for pref in contract.tools_preferred:
        if pref.over in called_set and pref.tool not in called_set:
            warnings.append(ContractViolation(
                check="tools_preferred",
                expected=pref.tool,
                actual=pref.over,
                message=f"Preferred tool '{pref.tool}' was not used; "
                        f"less-preferred '{pref.over}' was used instead. "
                        f"Reason: {pref.reason}",
                severity="warning",
            ))

    # -- Tool sequence (ordered) --
    if contract.tool_sequence and contract.tool_sequence.ordered and tool_call_order:
        expected_order = [s.tool for s in contract.tool_sequence.steps]
        # Filter actual order to only include expected tools
        actual_relevant = [t for t in tool_call_order if t in set(expected_order)]

        if actual_relevant != expected_order:
            violations.append(ContractViolation(
                check="tool_sequence",
                expected=expected_order,
                actual=actual_relevant,
                message=f"Tool execution order mismatch. "
                        f"Expected: {expected_order}, Got: {actual_relevant}",
            ))

    # -- Response contract --
    if contract.response_contract:
        rc = contract.response_contract

        # Min length check
        if rc.min_length and len(response_text) < rc.min_length:
            violations.append(ContractViolation(
                check="response_min_length",
                expected=f">= {rc.min_length} chars",
                actual=f"{len(response_text)} chars",
                message=f"Response too short: {len(response_text)} chars "
                        f"(minimum {rc.min_length})",
            ))

        # Must-contain concepts (case-insensitive substring check)
        response_lower = response_text.lower()
        for concept in rc.must_contain_concepts:
            if concept.lower() not in response_lower:
                violations.append(ContractViolation(
                    check="response_must_contain",
                    expected=concept,
                    actual=response_text[:200],
                    message=f"Response missing required concept: '{concept}'",
                ))

    passed = len(violations) == 0
    return ContractValidationResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
    )
