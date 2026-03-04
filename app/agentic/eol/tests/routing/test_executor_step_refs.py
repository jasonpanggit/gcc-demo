"""Regression tests for step-ref resolution in pipeline Executor."""
from __future__ import annotations

import pytest

try:
    from app.agentic.eol.utils.executor import Executor, StepResult
    from app.agentic.eol.utils.planner import PlanStep, ToolAffordance
except ModuleNotFoundError:
    from utils.executor import Executor, StepResult  # type: ignore[import-not-found]
    from utils.planner import PlanStep, ToolAffordance  # type: ignore[import-not-found]


def test_resolve_step_refs_handles_camel_case_and_id_aliases() -> None:
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="nsg_list",
            success=True,
            result={
                "network_security_groups": [
                    {
                        "resource_id": "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Network/networkSecurityGroups/nsg-a",
                        "resource_group": "rg-a",
                    }
                ]
            },
        )
    }

    params = {
        "resource_id": "$step_1.networkSecurityGroups[0].id",
        "resource_group": "$step_1.networkSecurityGroups[0].resourceGroup",
    }

    resolved = Executor._resolve_step_refs(params, completed)

    assert resolved["resource_id"].endswith("/networkSecurityGroups/nsg-a")
    assert resolved["resource_group"] == "rg-a"


def test_resolve_step_refs_supports_wildcard_list_selection() -> None:
    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="virtual_machine_list",
            success=True,
            result={
                "virtual_machines": [
                    {"resource_id": "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a"},
                    {"resource_id": "/subscriptions/sub-1/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-b"},
                ]
            },
        )
    }

    params = {
        "resource_id": "$step_1.virtual_machines[*].resource_id",
    }

    resolved = Executor._resolve_step_refs(params, completed)

    assert isinstance(resolved["resource_id"], list)
    assert len(resolved["resource_id"]) == 2
    assert resolved["resource_id"][0].endswith("/virtualMachines/vm-a")
    assert resolved["resource_id"][1].endswith("/virtualMachines/vm-b")


@pytest.mark.asyncio
async def test_execute_step_fails_fast_on_unresolved_step_refs() -> None:
    executor = Executor(composite_client=None)
    step = PlanStep(
        step_id="step_2",
        tool_name="inspect_nsg_rules",
        params={"resource_id": "$step_1.networkSecurityGroups[0].id"},
        affordance=ToolAffordance.READ,
        depends_on=["step_1"],
    )

    result = await executor._execute_step(step, completed={}, skip_destructive=False)

    assert result.success is False
    assert "Unresolved step reference" in result.error


@pytest.mark.asyncio
async def test_execute_step_fanout_executes_once_per_resolved_value() -> None:
    class _StubClient:
        def __init__(self) -> None:
            self.calls = []

        async def call_tool(self, tool_name: str, params: dict) -> dict:
            self.calls.append((tool_name, dict(params)))
            return {
                "success": True,
                "resource_id": params.get("resource_id"),
            }

    client = _StubClient()
    executor = Executor(composite_client=client)

    completed = {
        "step_1": StepResult(
            step_id="step_1",
            tool_name="virtual_machine_list",
            success=True,
            result={
                "virtual_machines": [
                    {"resource_id": "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a"},
                    {"resource_id": "/subscriptions/sub-1/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-b"},
                ]
            },
        )
    }

    step = PlanStep(
        step_id="step_2",
        tool_name="get_performance_metrics",
        params={
            "resource_id": "$step_1.virtual_machines[*].resource_id",
            "metric_names": ["Percentage CPU", "Available Memory Bytes"],
        },
        affordance=ToolAffordance.READ,
        depends_on=["step_1"],
    )

    result = await executor._execute_step(step, completed=completed, skip_destructive=False)

    assert result.success is True
    assert result.result is not None
    assert result.result.get("fanout") is True
    assert result.result.get("total_targets") == 2
    assert result.result.get("successful_targets") == 2
    assert len(result.result.get("results", [])) == 2
    assert len(client.calls) == 2
    assert client.calls[0][1]["resource_id"].endswith("/virtualMachines/vm-a")
    assert client.calls[1][1]["resource_id"].endswith("/virtualMachines/vm-b")
