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
