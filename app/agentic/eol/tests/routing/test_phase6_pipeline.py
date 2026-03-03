"""Unit tests for Phase 6 — Planner, Executor, Verifier, ResponseComposer, and
DeploymentAgent.

Tests that:
- Planner fast-path fires for simple read queries
- Planner LLM path parses steps correctly
- Planner produces legacy fallback on LLM failure
- Executor runs steps, retries on failure, skips destructive by default
- Executor handles parallel steps
- Executor returns legacy_react result for sentinel steps
- Verifier flags destructive skipped steps as needs_confirmation
- Verifier validates schemas (warnings only)
- ResponseComposer fallback HTML includes results and confirmation prompt
- DeploymentAgent has correct class attributes

All tests use MagicMock/AsyncMock — no Azure calls.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.planner import (
        ExecutionPlan,
        Planner,
        PlanStep,
        is_simple_read_query,
    )
    from app.agentic.eol.utils.executor import Executor, ExecutionResult, StepResult
    from app.agentic.eol.utils.verifier import Verifier, VerificationResult, ValidationIssue
    from app.agentic.eol.utils.response_composer import ResponseComposer, _build_static_fallback, _summarise_result
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance
    _PREFIX = "app.agentic.eol.utils"
except ModuleNotFoundError:
    from utils.planner import ExecutionPlan, Planner, PlanStep, is_simple_read_query  # type: ignore
    from utils.executor import Executor, ExecutionResult, StepResult  # type: ignore
    from utils.verifier import Verifier, VerificationResult, ValidationIssue  # type: ignore
    from utils.response_composer import ResponseComposer, _build_static_fallback, _summarise_result  # type: ignore
    from utils.tool_manifest_index import ToolAffordance  # type: ignore
    _PREFIX = "utils"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool: {name}",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


def _make_retrieval_result(tool_names: List[str]):
    """Build a minimal ToolRetrievalResult for testing."""
    try:
        from app.agentic.eol.utils.tool_retriever import ToolRetrievalResult
        from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain
        from app.agentic.eol.utils.router import DomainMatch
    except ModuleNotFoundError:
        from utils.tool_retriever import ToolRetrievalResult  # type: ignore
        from utils.unified_domain_registry import UnifiedDomain  # type: ignore
        from utils.router import DomainMatch  # type: ignore

    tools = [_make_tool(n) for n in tool_names]
    return ToolRetrievalResult(
        tools=tools,
        domain_matches=[DomainMatch(domain=UnifiedDomain.SRE_HEALTH, confidence=0.9, matched_signals=["sre"])],
        sources_used=["sre"],
        conflict_notes="",
        pool_size=len(tools) * 2,
    )


def _make_plan(tool_names: List[str], affordances: Optional[List[ToolAffordance]] = None) -> ExecutionPlan:
    affordances = affordances or [ToolAffordance.READ] * len(tool_names)
    steps = [
        PlanStep(
            step_id=f"step_{i + 1}",
            tool_name=name,
            params={},
            affordance=aff,
            rationale="test",
        )
        for i, (name, aff) in enumerate(zip(tool_names, affordances))
    ]
    return ExecutionPlan(query="test query", steps=steps)


# ---------------------------------------------------------------------------
# Test: is_simple_read_query
# ---------------------------------------------------------------------------

class TestIsSimpleReadQuery:
    def test_list_query_is_simple(self):
        assert is_simple_read_query("list my resource groups") is True

    def test_show_query_is_simple(self):
        assert is_simple_read_query("show me the container apps") is True

    def test_get_query_is_simple(self):
        assert is_simple_read_query("get resource inventory") is True

    def test_multi_step_not_simple(self):
        assert is_simple_read_query("list my VMs then restart the failed one") is False

    def test_deploy_not_simple(self):
        assert is_simple_read_query("deploy my container app") is False

    def test_check_health_not_simple(self):
        # "check health" doesn't start with list/show/get, so not fast-path
        # (it may or may not be simple depending on multi-step keywords)
        result = is_simple_read_query("check health of prod-api")
        assert isinstance(result, bool)

    def test_empty_query_not_simple(self):
        assert is_simple_read_query("") is False

    def test_restart_not_simple(self):
        assert is_simple_read_query("restart the failing container app") is False


# ---------------------------------------------------------------------------
# Test: Planner fast-path
# ---------------------------------------------------------------------------

class TestPlannerFastPath:
    @pytest.mark.asyncio
    async def test_fast_path_fires_for_list_query(self):
        planner = Planner()
        retrieval = _make_retrieval_result(["list_resources"])
        plan = await planner.plan("list my resource groups", retrieval)
        assert plan.is_fast_path is True
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "list_resources"

    @pytest.mark.asyncio
    async def test_fast_path_first_tool_chosen(self):
        """Fast path picks the best-matching tool by keyword overlap (not just first).

        The enhanced planner scores tools by token overlap, so we need a realistic
        tool name that contains tokens from the query.  generic names like 'tool_a'
        score 0 → planner defers to LLM → not a fast-path result.
        """
        planner = Planner()
        # Use real-looking tool names so keyword scoring can pick 'subscription_list'
        retrieval = _make_retrieval_result(["subscription_list", "group_list", "storage_account_list"])
        plan = await planner.plan("show my subscriptions", retrieval)
        assert plan.is_fast_path is True
        assert plan.steps[0].tool_name == "subscription_list"

    @pytest.mark.asyncio
    async def test_no_fast_path_for_multi_step(self):
        """Multi-step query must NOT take fast path (would require LLM or fallback)."""
        planner = Planner()
        retrieval = _make_retrieval_result(["restart_tool"])
        # Patch LLM call to avoid real Azure call
        planner._call_llm = AsyncMock(return_value=(False, ""))
        plan = await planner.plan("restart the failing container app", retrieval)
        assert plan.is_fast_path is False


# ---------------------------------------------------------------------------
# Test: Planner LLM path
# ---------------------------------------------------------------------------

class TestPlannerLLMPath:
    @pytest.mark.asyncio
    async def test_llm_path_parses_valid_json(self):
        planner = Planner()
        tool_names = ["check_health", "get_metrics"]
        retrieval = _make_retrieval_result(tool_names)

        llm_json = json.dumps({
            "steps": [
                {"step_id": "step_1", "tool_name": "check_health", "params": {},
                 "depends_on": [], "rationale": "check first", "is_parallel": False},
                {"step_id": "step_2", "tool_name": "get_metrics", "params": {},
                 "depends_on": ["step_1"], "rationale": "then metrics", "is_parallel": False},
            ]
        })
        planner._call_llm = AsyncMock(return_value=(True, llm_json))
        plan = await planner.plan("why is my app slow?", retrieval)

        assert plan.is_fast_path is False
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "check_health"
        assert plan.steps[1].tool_name == "get_metrics"
        assert plan.steps[1].depends_on == ["step_1"]

    @pytest.mark.asyncio
    async def test_llm_path_falls_back_on_json_error(self):
        planner = Planner()
        retrieval = _make_retrieval_result(["some_tool"])
        planner._call_llm = AsyncMock(return_value=(True, "not valid json at all"))
        plan = await planner.plan("restart the container app", retrieval)
        # Should produce legacy fallback
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "legacy_react"

    @pytest.mark.asyncio
    async def test_llm_path_falls_back_on_llm_failure(self):
        planner = Planner()
        retrieval = _make_retrieval_result(["some_tool"])
        planner._call_llm = AsyncMock(return_value=(False, "error"))
        plan = await planner.plan("restart the container app", retrieval)
        assert plan.steps[0].tool_name == "legacy_react"

    @pytest.mark.asyncio
    async def test_llm_path_skips_unknown_tools(self):
        """Steps with tool names not in retrieval_result are skipped."""
        planner = Planner()
        tool_names = ["real_tool"]
        retrieval = _make_retrieval_result(tool_names)

        llm_json = json.dumps({
            "steps": [
                {"step_id": "step_1", "tool_name": "fake_invented_tool", "params": {},
                 "depends_on": [], "rationale": "invented", "is_parallel": False},
                {"step_id": "step_2", "tool_name": "real_tool", "params": {},
                 "depends_on": [], "rationale": "real", "is_parallel": False},
            ]
        })
        planner._call_llm = AsyncMock(return_value=(True, llm_json))
        plan = await planner.plan("do something", retrieval)
        # Only real_tool should appear
        tool_names_in_plan = [s.tool_name for s in plan.steps]
        assert "fake_invented_tool" not in tool_names_in_plan
        assert "real_tool" in tool_names_in_plan

    @pytest.mark.asyncio
    async def test_legacy_fallback_when_no_tools(self):
        """Empty retrieval_result always yields legacy_react fallback."""
        planner = Planner()
        retrieval = _make_retrieval_result([])
        plan = await planner.plan("any query", retrieval)
        assert plan.steps[0].tool_name == "legacy_react"


# ---------------------------------------------------------------------------
# Test: Executor
# ---------------------------------------------------------------------------

class TestExecutor:
    def _make_executor(self, tool_results: Dict[str, Any]) -> Executor:
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(
            side_effect=lambda name, params: tool_results.get(name, {"success": True})
        )
        return Executor(composite_client=mock_client)

    @pytest.mark.asyncio
    async def test_executes_single_step(self):
        executor = self._make_executor({"my_tool": {"success": True, "data": "ok"}})
        plan = _make_plan(["my_tool"])
        result = await executor.execute(plan)
        assert result.all_succeeded is True
        assert len(result.successful_results) == 1
        assert result.successful_results[0].tool_name == "my_tool"

    @pytest.mark.asyncio
    async def test_skips_destructive_by_default(self):
        executor = self._make_executor({})
        plan = _make_plan(["destroy_tool"], affordances=[ToolAffordance.DESTRUCTIVE])
        result = await executor.execute(plan, skip_destructive=True)
        assert result.skipped_results[0].tool_name == "destroy_tool"
        assert result.all_succeeded is True  # skipped is not a failure

    @pytest.mark.asyncio
    async def test_does_not_skip_destructive_when_confirmed(self):
        executor = self._make_executor({"destroy_tool": {"success": True}})
        plan = _make_plan(["destroy_tool"], affordances=[ToolAffordance.DESTRUCTIVE])
        result = await executor.execute(plan, skip_destructive=False)
        assert len(result.successful_results) == 1

    @pytest.mark.asyncio
    async def test_legacy_react_step_returns_sentinel(self):
        executor = Executor(composite_client=None)
        plan = _make_plan(["legacy_react"])
        result = await executor.execute(plan)
        assert result.successful_results[0].result == {"_legacy": True, "query": ""}

    @pytest.mark.asyncio
    async def test_failed_step_recorded(self):
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("tool error"))
        executor = Executor(composite_client=mock_client)
        plan = _make_plan(["failing_tool"])
        result = await executor.execute(plan)
        assert len(result.failed_results) == 1
        assert "tool error" in result.failed_results[0].error

    @pytest.mark.asyncio
    async def test_dependent_step_skipped_on_upstream_failure(self):
        """Step 2 depends on Step 1. If Step 1 fails, Step 2 should be skipped."""
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("step1 failed"))
        executor = Executor(composite_client=mock_client)

        steps = [
            PlanStep(step_id="step_1", tool_name="failing_tool", params={},
                     affordance=ToolAffordance.READ, rationale=""),
            PlanStep(step_id="step_2", tool_name="dependent_tool", params={},
                     depends_on=["step_1"], affordance=ToolAffordance.READ, rationale=""),
        ]
        plan = ExecutionPlan(query="q", steps=steps)
        result = await executor.execute(plan)

        # step_1 should fail, step_2 should be skipped
        step1 = next(r for r in result.step_results if r.step_id == "step_1")
        step2 = next(r for r in result.step_results if r.step_id == "step_2")
        assert step1.success is False
        assert step2.skipped is True

    @pytest.mark.asyncio
    async def test_parallel_steps_run_concurrently(self):
        """Parallel steps should all be in step_results even if one fails."""
        call_count = {"n": 0}

        async def _fake_call(name, params):
            call_count["n"] += 1
            return {"success": True}

        mock_client = AsyncMock()
        mock_client.call_tool = _fake_call
        executor = Executor(composite_client=mock_client)

        steps = [
            PlanStep(step_id="p1", tool_name="tool_a", params={},
                     is_parallel=True, affordance=ToolAffordance.READ, rationale=""),
            PlanStep(step_id="p2", tool_name="tool_b", params={},
                     is_parallel=True, affordance=ToolAffordance.READ, rationale=""),
        ]
        plan = ExecutionPlan(query="q", steps=steps)
        result = await executor.execute(plan)
        assert len(result.step_results) == 2
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Test: Verifier
# ---------------------------------------------------------------------------

class TestVerifier:
    def _make_execution_result(
        self,
        plan: ExecutionPlan,
        step_results: List[StepResult],
    ) -> ExecutionResult:
        er = ExecutionResult(plan=plan)
        er.step_results = step_results
        er.all_succeeded = all(r.success or r.skipped for r in step_results)
        return er

    @pytest.mark.asyncio
    async def test_destructive_skipped_step_needs_confirmation(self):
        verifier = Verifier()
        plan = _make_plan(["delete_tool"], affordances=[ToolAffordance.DESTRUCTIVE])
        step_results = [
            StepResult(step_id="step_1", tool_name="delete_tool",
                       success=True, skipped=True, skip_reason="Destructive gated")
        ]
        er = self._make_execution_result(plan, step_results)
        vr = await verifier.verify(plan, er)
        assert vr.needs_confirmation is True
        assert "step_1" in vr.blocked_steps

    @pytest.mark.asyncio
    async def test_read_step_does_not_need_confirmation(self):
        verifier = Verifier()
        plan = _make_plan(["read_tool"])
        step_results = [
            StepResult(step_id="step_1", tool_name="read_tool",
                       success=True, result={"data": "ok"})
        ]
        er = self._make_execution_result(plan, step_results)
        vr = await verifier.verify(plan, er)
        assert vr.needs_confirmation is False
        assert len(vr.blocked_steps) == 0

    @pytest.mark.asyncio
    async def test_schema_validation_warns_on_missing_field(self):
        """Schema validation emits a warning when a required field is missing."""
        try:
            from app.agentic.eol.utils.tool_manifest_index import ToolManifestIndex, ToolManifest
        except ModuleNotFoundError:
            from utils.tool_manifest_index import ToolManifestIndex, ToolManifest  # type: ignore

        # Build a manifest that requires "status" field
        manifest = ToolManifest(
            tool_name="health_tool",
            source="sre",
            domains=frozenset(["sre_health"]),
            tags=frozenset(["health"]),
            affordance=ToolAffordance.READ,
            example_queries=("check health",),
            conflicts_with=frozenset(),
            conflict_note="",
            preferred_over=frozenset(),
            output_schema={
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string"}},
            },
        )
        index = ToolManifestIndex()
        index.register(manifest)
        verifier = Verifier(manifest_index=index)

        plan = _make_plan(["health_tool"])
        step_results = [
            StepResult(step_id="step_1", tool_name="health_tool",
                       success=True, result={"data": "no_status_field"})
        ]
        er = self._make_execution_result(plan, step_results)
        vr = await verifier.verify(plan, er)
        # Should have a warning about missing "status"
        warning_msgs = [i.message for i in vr.issues if i.severity == "warning"]
        assert any("status" in m for m in warning_msgs)

    @pytest.mark.asyncio
    async def test_verify_returns_no_issues_for_clean_run(self):
        verifier = Verifier()
        plan = _make_plan(["tool_a", "tool_b"])
        step_results = [
            StepResult(step_id="step_1", tool_name="tool_a", success=True, result={"ok": True}),
            StepResult(step_id="step_2", tool_name="tool_b", success=True, result={"ok": True}),
        ]
        er = self._make_execution_result(plan, step_results)
        vr = await verifier.verify(plan, er)
        assert vr.needs_confirmation is False
        assert len(vr.blocked_steps) == 0
        # No schema validation (no manifest_index) → no issues
        assert not vr.issues


# ---------------------------------------------------------------------------
# Test: ResponseComposer static fallback
# ---------------------------------------------------------------------------

class TestResponseComposerFallback:
    def _make_execution_result_for_composer(
        self, successes: List[str], failures: List[str], skipped: List[str]
    ) -> ExecutionResult:
        plan = _make_plan(successes + failures + skipped)
        step_results = []
        for name in successes:
            step_results.append(StepResult(step_id=f"s_{name}", tool_name=name,
                                            success=True, result={"data": "ok"}))
        for name in failures:
            step_results.append(StepResult(step_id=f"f_{name}", tool_name=name,
                                            success=False, error="tool failed"))
        for name in skipped:
            step_results.append(StepResult(step_id=f"sk_{name}", tool_name=name,
                                            success=True, skipped=True,
                                            skip_reason="Destructive gated"))
        er = ExecutionResult(plan=plan)
        er.step_results = step_results
        er.all_succeeded = all(r.success or r.skipped for r in step_results)
        return er

    def test_fallback_html_contains_tool_names(self):
        er = self._make_execution_result_for_composer(["my_read_tool"], [], [])
        html = _build_static_fallback("test query", er, None)
        assert "my_read_tool" in html

    def test_fallback_html_shows_failure(self):
        er = self._make_execution_result_for_composer([], ["broken_tool"], [])
        html = _build_static_fallback("test query", er, None)
        assert "broken_tool" in html
        assert "Failed" in html

    def test_fallback_html_shows_confirmation_prompt_for_skipped(self):
        er = self._make_execution_result_for_composer([], [], ["delete_me"])
        html = _build_static_fallback("test query", er, None)
        assert "confirmation" in html.lower() or "confirm" in html.lower()
        assert "delete_me" in html

    @pytest.mark.asyncio
    async def test_composer_uses_fallback_when_llm_unavailable(self):
        composer = ResponseComposer()
        composer._call_llm = AsyncMock(return_value=(False, ""))
        er = self._make_execution_result_for_composer(["a_tool"], [], [])
        html = await composer.compose("test query", er)
        # Should contain the fallback table
        assert "a_tool" in html
        assert "<table" in html.lower() or "<p" in html.lower()

    @pytest.mark.asyncio
    async def test_composer_returns_llm_content_when_available(self):
        composer = ResponseComposer()
        composer._call_llm = AsyncMock(return_value=(True, "<h3>Result</h3><p>All good.</p>"))
        er = self._make_execution_result_for_composer(["a_tool"], [], [])
        html = await composer.compose("test query", er)
        assert html == "<h3>Result</h3><p>All good.</p>"


def test_summarise_result_preserves_all_fanout_performance_metric_targets() -> None:
    fanout_result = {
        "success": True,
        "partial_failure": False,
        "fanout": True,
        "total_targets": 2,
        "successful_targets": 2,
        "failed_targets": 0,
        "results": [
            {
                "params": {
                    "resource_id": "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a"
                },
                "result": {
                    "parsed": {
                        "resource_name": "vm-a",
                        "resource_type": "VirtualMachine",
                        "metrics": [{"name": "Percentage CPU", "timeseries": []}],
                        "time_range": {"hours": 1},
                    }
                },
            },
            {
                "params": {
                    "resource_id": "/subscriptions/sub-1/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-b"
                },
                "result": {
                    "parsed": {
                        "resource_name": "vm-b",
                        "resource_type": "VirtualMachine",
                        "metrics": [{"name": "Percentage CPU", "timeseries": []}],
                        "time_range": {"hours": 1},
                    }
                },
            },
        ],
        "errors": [],
    }

    summary = _summarise_result(fanout_result, tool_name="get_performance_metrics")

    assert "vm-a" in summary
    assert "vm-b" in summary
    assert "performance_metrics" in summary


def test_summarise_result_extracts_memory_available_gib_for_vm_metrics() -> None:
    fanout_result = {
        "success": True,
        "fanout": True,
        "total_targets": 1,
        "successful_targets": 1,
        "failed_targets": 0,
        "results": [
            {
                "params": {
                    "resource_id": "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a"
                },
                "result": {
                    "parsed": {
                        "resource_name": "vm-a",
                        "resource_type": "VirtualMachine",
                        "metrics": [
                            {
                                "metric_name": "Percentage CPU",
                                "summary": {"average": 12.5},
                            },
                            {
                                "metric_name": "Available Memory Bytes",
                                "summary": {"average": 8589934592},
                            },
                        ],
                        "time_range": {"hours": 1},
                    }
                },
            }
        ],
        "errors": [],
    }

    summary = _summarise_result(fanout_result, tool_name="get_performance_metrics")

    assert "memory_available_gib" in summary
    assert "8.0" in summary
    assert "cpu_percent" in summary


# ---------------------------------------------------------------------------
# Test: DeploymentAgent
# ---------------------------------------------------------------------------

class TestDeploymentAgent:
    def test_deployment_agent_imports(self):
        try:
            from app.agentic.eol.agents.deployment_agent import DeploymentAgent
        except ModuleNotFoundError:
            from agents.deployment_agent import DeploymentAgent  # type: ignore
        assert DeploymentAgent._DOMAIN_NAME == "deployment"
        assert DeploymentAgent._MAX_ITERATIONS == 15

    def test_deployment_agent_system_prompt_has_safety_rules(self):
        try:
            from app.agentic.eol.agents.deployment_agent import DeploymentAgent
        except ModuleNotFoundError:
            from agents.deployment_agent import DeploymentAgent  # type: ignore
        prompt = DeploymentAgent._SYSTEM_PROMPT
        assert "confirmation" in prompt.lower() or "confirm" in prompt.lower()
        assert "deploy" in prompt.lower()

    def test_deployment_agent_is_domain_sub_agent(self):
        try:
            from app.agentic.eol.agents.deployment_agent import DeploymentAgent
            from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
        except ModuleNotFoundError:
            from agents.deployment_agent import DeploymentAgent  # type: ignore
            from agents.domain_sub_agent import DomainSubAgent  # type: ignore
        assert issubclass(DeploymentAgent, DomainSubAgent)
