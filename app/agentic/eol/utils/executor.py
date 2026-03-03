"""Pipeline Executor — Stage 4 of the MCP orchestrator pipeline.

Executes an ``ExecutionPlan`` produced by the Planner:

  - Per step: resolve parameters via ``ResourceInventoryService``, then call
    the MCP tool through ``CompositeMCPClient``.
  - Independent steps (``is_parallel=True`` and no ``depends_on``) are run
    concurrently via ``asyncio.gather``.
  - Each step is bounded to ``_MAX_STEP_RETRIES`` retries with exponential
    back-off before marking the step as failed.
  - Sub-agent delegation: if the step's domain is registered in
    ``UnifiedDomainRegistry``, forwards to the domain sub-agent instead.
  - Emits SSE-compatible events via the supplied *push_event* callback so the
    UI receives live progress updates.

Design goals:
  - No LLM calls — pure tool execution
  - Graceful degradation: step failure marks the step as failed but does NOT
    abort the whole plan (unless the step is a blocker for later steps)
  - Verifier gates destructive steps before execution

Usage::

    executor = Executor(composite_client=client, inventory_service=service)
    results = await executor.execute(plan)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_STEP_RETRIES = 2
_RETRY_BASE_DELAY = 0.5  # seconds

# Tool name for the Azure MCP CLI generation step
_CLI_GENERATE_TOOL = "azmcp_extension_cli_generate"


def _extract_tool_error_message(tool_result: Dict[str, Any], exit_code: Optional[int]) -> str:
    """Extract a useful error message from wrapped MCP tool results."""
    import json as _json

    direct_error = str(tool_result.get("error") or "").strip()
    if direct_error:
        return direct_error

    stderr = str(tool_result.get("stderr") or "").strip()
    if stderr:
        return stderr

    parsed = tool_result.get("parsed")
    if isinstance(parsed, dict):
        parsed_error = str(parsed.get("error") or parsed.get("message") or "").strip()
        if parsed_error:
            return parsed_error

    content = tool_result.get("content")
    if isinstance(content, list):
        for entry in content:
            if not isinstance(entry, str):
                continue
            try:
                decoded = _json.loads(entry)
            except Exception:
                continue
            if isinstance(decoded, dict):
                embedded_error = str(decoded.get("error") or decoded.get("message") or "").strip()
                if embedded_error:
                    return embedded_error

    return f"Tool returned exit_code={exit_code}"


def _extract_generated_cli_command(tool_result: Dict[str, Any]) -> str:
    """Parse azmcp_extension_cli_generate output and return the az command string.

    The tool returns a nested structure::

        {"content": ['{"results": {"command": "{\\"data\\": [{...}]}"}}'} ]}

    We unwrap two JSON layers to get ``data[0].commandSet[0].example``.
    Returns empty string on any parse/key error (caller keeps the original command).
    """
    import json as _json

    try:
        content = tool_result.get("content", [])
        raw = content[0] if isinstance(content, list) and content else str(content)
        outer = _json.loads(raw) if isinstance(raw, str) else raw
        cmd_str = outer.get("results", {}).get("command", "")
        inner = _json.loads(cmd_str) if isinstance(cmd_str, str) else cmd_str
        example: str = inner["data"][0]["commandSet"][0]["example"]
        logger.info("🔧 CLI Copilot generated command: %s", example)
        return example
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("_extract_generated_cli_command: could not parse result (%s)", exc)
        return ""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

try:
    from app.agentic.eol.utils.planner import ExecutionPlan, PlanStep, ToolAffordance
    from app.agentic.eol.utils.resource_inventory_service import ResourceInventoryService
except ModuleNotFoundError:
    from utils.planner import ExecutionPlan, PlanStep, ToolAffordance  # type: ignore[import-not-found]
    from utils.resource_inventory_service import ResourceInventoryService  # type: ignore[import-not-found]


@dataclass
class StepResult:
    """Result of executing a single PlanStep."""

    step_id: str
    tool_name: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    """Raw tool response dict (or sub-agent text response)."""
    error: str = ""
    """Error message if success=False."""
    elapsed_ms: float = 0.0
    skipped: bool = False
    """True when step was skipped (e.g. blocked by Verifier)."""
    skip_reason: str = ""


@dataclass
class ExecutionResult:
    """Aggregate output of Executor.execute()."""

    plan: ExecutionPlan
    step_results: List[StepResult] = field(default_factory=list)
    all_succeeded: bool = True
    """False when at least one non-skipped step failed."""

    @property
    def successful_results(self) -> List[StepResult]:
        return [r for r in self.step_results if r.success and not r.skipped]

    @property
    def failed_results(self) -> List[StepResult]:
        return [r for r in self.step_results if not r.success and not r.skipped]

    @property
    def skipped_results(self) -> List[StepResult]:
        return [r for r in self.step_results if r.skipped]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

_PushEventCallback = Optional[Callable[..., Coroutine[Any, Any, None]]]


class Executor:
    """Executes an ``ExecutionPlan`` step by step (or in parallel where safe).

    Args:
        composite_client: ``CompositeMCPClient`` instance for tool dispatch.
        inventory_service: ``ResourceInventoryService`` for parameter resolution.
        push_event: Optional coroutine-returning callback with the same
            signature as ``MCPOrchestratorAgent._push_event``.  Used to emit
            SSE progress events to the UI.
    """

    def __init__(
        self,
        composite_client: Optional[Any] = None,
        inventory_service: Optional[ResourceInventoryService] = None,
        push_event: _PushEventCallback = None,
    ) -> None:
        self._client = composite_client
        self._inventory = inventory_service
        self._push_event = push_event

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        skip_destructive: bool = True,
    ) -> ExecutionResult:
        """Execute all steps in *plan*.

        Steps that have no ``depends_on`` and are marked ``is_parallel=True``
        are run concurrently; all others are run sequentially in step_id order.

        Args:
            plan: ``ExecutionPlan`` from Planner.
            skip_destructive: When True (default), steps with
                ``affordance=DESTRUCTIVE`` are skipped rather than executed.
                The Verifier calls this method with skip_destructive=False only
                after explicit user confirmation has been received.

        Returns:
            ``ExecutionResult`` with per-step outcomes.
        """
        result = ExecutionResult(plan=plan)
        completed: Dict[str, StepResult] = {}

        # Separate parallel candidates from sequential steps
        parallel_steps = [
            s for s in plan.steps if s.is_parallel and not s.depends_on
        ]
        sequential_steps = [
            s for s in plan.steps if s not in parallel_steps
        ]

        # Run parallel steps first
        if parallel_steps:
            await self._emit("step_batch_start", f"Running {len(parallel_steps)} parallel step(s)")
            parallel_results = await asyncio.gather(
                *[
                    self._execute_step(s, completed, skip_destructive=skip_destructive)
                    for s in parallel_steps
                ],
                return_exceptions=True,
            )
            for step, res in zip(parallel_steps, parallel_results):
                if isinstance(res, Exception):
                    sr = StepResult(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        error=str(res),
                    )
                else:
                    sr = res  # type: ignore[assignment]
                result.step_results.append(sr)
                completed[step.step_id] = sr

        # Run sequential steps in order
        for step in sequential_steps:
            # Check if any dependency failed
            blocked_by_failure = any(
                dep in completed and not completed[dep].success and not completed[dep].skipped
                for dep in step.depends_on
            )
            if blocked_by_failure:
                sr = StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    skipped=True,
                    skip_reason="Blocked by failed dependency",
                )
                result.step_results.append(sr)
                completed[step.step_id] = sr
                continue

            sr = await self._execute_step(
                step, completed, skip_destructive=skip_destructive
            )
            result.step_results.append(sr)
            completed[step.step_id] = sr

        result.all_succeeded = all(
            r.success or r.skipped for r in result.step_results
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: PlanStep,
        completed: Dict[str, StepResult],
        *,
        skip_destructive: bool,
    ) -> StepResult:
        """Execute a single step with retry logic."""

        # Skip destructive steps when gated
        if skip_destructive and step.affordance in (
            ToolAffordance.DESTRUCTIVE,
            ToolAffordance.DEPLOY,
        ):
            logger.info(
                "⛔ Executor: skipping destructive step %s (tool=%s) — awaiting confirmation",
                step.step_id,
                step.tool_name,
            )
            return StepResult(
                step_id=step.step_id,
                tool_name=step.tool_name,
                success=True,  # not a failure — intentional gate
                skipped=True,
                skip_reason=f"Destructive step gated. Affordance={step.affordance.value}. "
                             "Explicit confirmation required.",
            )

        # Handle legacy_react sentinel
        if step.tool_name == "legacy_react":
            logger.debug("Executor: legacy_react step — no tool call needed")
            return StepResult(
                step_id=step.step_id,
                tool_name="legacy_react",
                success=True,
                result={"_legacy": True, "query": step.params.get("query", "")},
            )

        await self._emit(
            "step_start",
            f"Starting {step.tool_name}",
            step_id=step.step_id,
        )
        t0 = time.monotonic()

        # Parameter resolution
        params = dict(step.params)
        # 1. Resolve $step_N.path references from prior completed steps
        params = self._resolve_step_refs(params, completed)
        if self._inventory:
            try:
                params = await self._inventory.resolve_parameters(step.tool_name, params)
            except Exception as exc:
                logger.debug("resolve_parameters error for %s (non-fatal): %s", step.tool_name, exc)

        unresolved_step_refs = [
            f"{k}={v}" for k, v in params.items()
            if isinstance(v, str) and v.startswith("$step_")
        ]
        if unresolved_step_refs:
            error_message = "Unresolved step reference(s): " + "; ".join(unresolved_step_refs)
            await self._emit(
                "step_error",
                f"Step {step.tool_name} failed: {error_message[:120]}",
                step_id=step.step_id,
            )
            return StepResult(
                step_id=step.step_id,
                tool_name=step.tool_name,
                success=False,
                error=error_message,
            )

        # Fan-out execution: if one parameter resolves to a list (for example
        # $step_1.virtual_machines[*].resource_id), execute once per value and
        # aggregate results.
        fanout_keys = [
            k
            for k, v in params.items()
            if (
                isinstance(v, list)
                and isinstance(step.params.get(k), str)
                and str(step.params.get(k)).startswith("$step_")
            )
        ]
        if fanout_keys:
            if len(fanout_keys) > 1:
                return StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    error=f"Fan-out supports a single list parameter per step; got keys={fanout_keys}",
                )

            fanout_key = fanout_keys[0]
            fanout_values = params.get(fanout_key)
            if not isinstance(fanout_values, list) or not fanout_values:
                return StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    error=f"Fan-out parameter '{fanout_key}' has no values",
                )

            fanout_t0 = time.monotonic()
            successful_results: List[Dict[str, Any]] = []
            failed_results: List[Dict[str, Any]] = []

            for value in fanout_values:
                call_params = dict(params)
                call_params[fanout_key] = value

                call_error = ""
                call_result: Optional[Dict[str, Any]] = None
                for attempt in range(1, _MAX_STEP_RETRIES + 2):
                    try:
                        tool_result = await self._dispatch_tool(step.tool_name, call_params)

                        tool_success = tool_result.get("success", True)
                        exit_code = tool_result.get("exit_code")
                        if exit_code is not None:
                            tool_success = tool_success and (exit_code == 0)

                        if not tool_success:
                            tool_error = _extract_tool_error_message(tool_result, exit_code)
                            raise RuntimeError(f"Tool reported failure: {tool_error}")

                        if step.tool_name == _CLI_GENERATE_TOOL:
                            generated = _extract_generated_cli_command(tool_result)
                            if generated:
                                tool_result["_generated_command"] = generated

                        call_result = tool_result
                        break
                    except Exception as exc:
                        call_error = str(exc)
                        if isinstance(exc, PermissionError):
                            break
                        if attempt <= _MAX_STEP_RETRIES:
                            await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))

                if call_result is not None:
                    successful_results.append({
                        "params": call_params,
                        "result": call_result,
                    })
                else:
                    failed_results.append({
                        "params": call_params,
                        "error": call_error or "Unknown fan-out failure",
                    })

            elapsed_ms = (time.monotonic() - fanout_t0) * 1000
            ok_count = len(successful_results)
            fail_count = len(failed_results)
            total_count = len(fanout_values)

            if ok_count == 0:
                await self._emit(
                    "step_error",
                    f"Step {step.tool_name} fan-out failed for all targets",
                    step_id=step.step_id,
                )
                return StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    error="Fan-out execution failed for all targets",
                    result={
                        "fanout": True,
                        "fanout_key": fanout_key,
                        "total_targets": total_count,
                        "successful_targets": ok_count,
                        "failed_targets": fail_count,
                        "results": successful_results,
                        "errors": failed_results,
                    },
                    elapsed_ms=elapsed_ms,
                )

            await self._emit(
                "step_complete",
                f"Completed {step.tool_name} fan-out ({ok_count}/{total_count})",
                step_id=step.step_id,
                elapsed_ms=elapsed_ms,
            )
            return StepResult(
                step_id=step.step_id,
                tool_name=step.tool_name,
                success=True,
                result={
                    "success": fail_count == 0,
                    "partial_failure": fail_count > 0,
                    "fanout": True,
                    "fanout_key": fanout_key,
                    "total_targets": total_count,
                    "successful_targets": ok_count,
                    "failed_targets": fail_count,
                    "results": successful_results,
                    "errors": failed_results,
                },
                elapsed_ms=elapsed_ms,
            )

        # Execute with retries
        last_error = ""
        for attempt in range(1, _MAX_STEP_RETRIES + 2):
            try:
                tool_result = await self._dispatch_tool(step.tool_name, params)
                elapsed_ms = (time.monotonic() - t0) * 1000

                # Detect tool-level failures reported in the result dict.
                # Applies to CLI executor and any tool that returns {"success": False, ...}.
                tool_success = tool_result.get("success", True)
                exit_code = tool_result.get("exit_code")
                if exit_code is not None:
                    tool_success = tool_success and (exit_code == 0)

                if not tool_success:
                    # Treat as a retryable failure so retry logic applies.
                    tool_error = _extract_tool_error_message(tool_result, exit_code)
                    tool_error_lower = str(tool_error).lower()
                    if (
                        "authorizationfailed" in tool_error_lower
                        or "does not have authorization" in tool_error_lower
                        or "forbidden" in tool_error_lower
                    ):
                        raise PermissionError(f"Tool authorization failure: {tool_error}")
                    raise RuntimeError(f"Tool reported failure: {tool_error}")

                # Post-process CLI generation results: extract the generated command
                # so downstream steps can reference it via $step_N._generated_command.
                if step.tool_name == _CLI_GENERATE_TOOL:
                    generated = _extract_generated_cli_command(tool_result)
                    if generated:
                        tool_result["_generated_command"] = generated

                logger.info(
                    "✅ Executor: step %s (%s) succeeded in %.0fms",
                    step.step_id,
                    step.tool_name,
                    elapsed_ms,
                )
                await self._emit(
                    "step_complete",
                    f"Completed {step.tool_name}",
                    step_id=step.step_id,
                    elapsed_ms=elapsed_ms,
                )
                return StepResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=True,
                    result=tool_result,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Executor: step %s attempt %d/%d failed: %s",
                    step.step_id,
                    attempt,
                    _MAX_STEP_RETRIES + 1,
                    exc,
                )
                if isinstance(exc, PermissionError):
                    break
                if attempt <= _MAX_STEP_RETRIES:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.error(
            "❌ Executor: step %s (%s) failed after %d attempts: %s",
            step.step_id,
            step.tool_name,
            _MAX_STEP_RETRIES + 1,
            last_error,
        )
        await self._emit(
            "step_error",
            f"Step {step.tool_name} failed: {last_error[:120]}",
            step_id=step.step_id,
        )
        return StepResult(
            step_id=step.step_id,
            tool_name=step.tool_name,
            success=False,
            error=last_error,
            elapsed_ms=elapsed_ms,
        )

    async def _dispatch_tool(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch a tool call through the composite MCP client.

        Args:
            tool_name: Exact MCP tool name.
            params: Resolved parameters dict.

        Returns:
            Tool response dict (always contains at least ``success`` key).

        Raises:
            RuntimeError: if client is unavailable or tool call fails.
        """
        if self._client is None:
            raise RuntimeError("CompositeMCPClient not initialised in Executor")

        # CompositeMCPClient exposes call_tool(tool_name, arguments)
        if hasattr(self._client, "call_tool"):
            return await self._client.call_tool(tool_name, params)  # type: ignore[return-value]

        raise RuntimeError(
            f"CompositeMCPClient has no call_tool method (type={type(self._client).__name__})"
        )

    async def _emit(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Forward an event to the push_event callback (if set)."""
        if self._push_event is None:
            return
        try:
            await self._push_event(event_type, message, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Executor: push_event failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Step-reference resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_step_refs(
        params: Dict[str, Any],
        completed: Dict[str, "StepResult"],
    ) -> Dict[str, Any]:
        """Substitute ``$step_N.path[idx].field`` references in *params*.

        Allows the LLM planner to express data-flow between dependent steps.
        For example::

            {"subscription_id": "$step_1.subscriptions[0].subscription_id"}

        If the reference cannot be resolved the original placeholder string is
        kept so the tool can decide how to handle it (e.g. fall back to its
        env-var default).
        """
        import re as _re
        _REF = _re.compile(r'^\$(?P<step_id>step_\d+)\.(?P<path>.+)$')

        def _get_nested(obj: Any, path: str) -> Any:
            """Walk a.b[0].c style paths into dicts/lists."""
            def _camel_to_snake(text: str) -> str:
                text = _re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
                return text.lower()

            def _snake_to_camel(text: str) -> str:
                parts = text.split("_")
                if not parts:
                    return text
                return parts[0] + "".join(p.capitalize() for p in parts[1:])

            parts = [part for part in _re.split(r'[.\[\]]+', path) if part]

            def _walk(current: Any, index: int) -> Any:
                if index >= len(parts):
                    return current

                part = parts[index]

                if isinstance(current, dict):
                    if part in current:
                        return _walk(current.get(part), index + 1)

                    if part == "id" and "resource_id" in current:
                        return _walk(current.get("resource_id"), index + 1)
                    if part == "resource_id" and "id" in current:
                        return _walk(current.get("id"), index + 1)

                    snake_part = _camel_to_snake(part)
                    if snake_part in current:
                        return _walk(current.get(snake_part), index + 1)

                    camel_part = _snake_to_camel(part)
                    if camel_part in current:
                        return _walk(current.get(camel_part), index + 1)

                    return None

                if isinstance(current, list):
                    if part == "*":
                        values = []
                        for item in current:
                            resolved = _walk(item, index + 1)
                            if resolved is not None:
                                values.append(resolved)
                        return values if values else None

                    try:
                        return _walk(current[int(part)], index + 1)
                    except (ValueError, IndexError):
                        return None

                return None

            return _walk(obj, 0)

        def _iter_step_payload_roots(step_result: Optional["StepResult"]) -> List[Any]:
            """Yield candidate payload roots for step-ref resolution.

            MCP clients often wrap the actual tool payload under ``parsed`` and
            keep raw JSON strings under ``content``. Include those roots so
            planner-authored refs like ``$step_1.network_security_groups[0]``
            resolve consistently across client wrappers.
            """
            import json as _json

            roots: List[Any] = []
            if not step_result or not step_result.success or not step_result.result:
                return roots

            root = step_result.result
            roots.append(root)

            if isinstance(root, dict):
                parsed = root.get("parsed")
                if isinstance(parsed, (dict, list)):
                    roots.append(parsed)

                content = root.get("content")
                if isinstance(content, list):
                    for entry in content:
                        if not isinstance(entry, str):
                            continue
                        try:
                            decoded = _json.loads(entry)
                        except Exception:
                            continue
                        if isinstance(decoded, (dict, list)):
                            roots.append(decoded)

            return roots

        result: Dict[str, Any] = {}
        for k, v in params.items():
            if isinstance(v, str):
                m = _REF.match(v)
                if m:
                    dep_step = completed.get(m.group('step_id'))
                    for payload_root in _iter_step_payload_roots(dep_step):
                        resolved = _get_nested(payload_root, m.group('path'))
                        if resolved is not None:
                            logger.debug(
                                "Executor: resolved param %s=%r from %s",
                                k, resolved, v,
                            )
                            result[k] = resolved
                            continue
                    if k in result:
                        continue
                    logger.debug(
                        "Executor: could not resolve step-ref %r for param %s — keeping placeholder",
                        v, k,
                    )
            result[k] = v
        return result
