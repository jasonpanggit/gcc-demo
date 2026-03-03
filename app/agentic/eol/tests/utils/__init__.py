"""Test utilities for golden dataset loading and contract validation.

This package provides:
- YAML schema definition for golden test scenarios
- Loader for parsing and validating scenario files
- Contract validation framework for tool selection assertions

Usage:
    from tests.utils import GoldenDatasetLoader, validate_contract

    scenarios = load_all_scenarios("tests/scenarios/")
    for scenario in scenarios:
        result = validate_contract(
            scenario,
            tools_called=["container_app_list", "check_container_app_health"],
            response_text="Container apps are healthy...",
            tool_call_order=["container_app_list", "check_container_app_health"],
        )
        assert result.passed, result.summary()
"""

from .golden_dataset_loader import (
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

__all__ = [
    "GoldenScenario",
    "ExpectedContract",
    "IntentContract",
    "ToolPreference",
    "ToolSequence",
    "ToolSequenceStep",
    "ResponseContract",
    "QueryVariation",
    "FixtureResponse",
    "ContractViolation",
    "ContractValidationResult",
    "validate_contract",
    "load_scenario",
    "load_all_scenarios",
]
