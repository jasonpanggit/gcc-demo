import pytest

from utils.planner import Planner
from utils.tool_retriever import ToolRetrievalResult


def _retrieval_result(tool_names):
    return ToolRetrievalResult(
        tools=[{"function": {"name": tool_name, "description": ""}} for tool_name in tool_names],
        conflict_notes="",
    )


@pytest.mark.asyncio
async def test_vm_utilization_query_uses_vm_metrics_sequence_fast_path():
    planner = Planner()
    retrieval_result = _retrieval_result(
        ["virtual_machine_list", "get_performance_metrics", "monitor"]
    )

    plan = await planner.plan(
        query="show CPU and memory utilization of these VMs",
        retrieval_result=retrieval_result,
    )

    assert plan.is_fast_path is True
    assert [step.tool_name for step in plan.steps] == [
        "virtual_machine_list",
        "get_performance_metrics",
    ]
    assert plan.steps[1].depends_on == ["step_1"]
    assert plan.steps[1].params["resource_id"] == "$step_1.virtual_machines[*].resource_id"
    assert plan.steps[1].params["metric_names"] == ["Percentage CPU", "Available Memory Bytes"]


@pytest.mark.asyncio
async def test_plain_vm_list_query_stays_single_step_list_override():
    planner = Planner()
    retrieval_result = _retrieval_result(
        ["virtual_machine_list", "get_performance_metrics", "monitor"]
    )

    plan = await planner.plan(
        query="show my VMs",
        retrieval_result=retrieval_result,
    )

    assert plan.is_fast_path is True
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "virtual_machine_list"
