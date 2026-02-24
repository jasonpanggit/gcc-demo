"""Pipeline Verifier — Stage 5 of the MCP orchestrator pipeline.

Performs deterministic validation of an ExecutionResult before it is handed
to the ResponseComposer:

  1. Schema validation — checks each step result against the ``output_schema``
     in ``ToolManifest`` (if registered).  Emits warnings; does NOT block.
  2. Destructive gate — steps with ``affordance=DESTRUCTIVE`` that were
     *not* skipped (i.e. skip_destructive=False was passed to Executor) are
     flagged for an explicit confirmation prompt.
  3. Preflight check — calls ``ResourceInventoryService.preflight_check()``
     on each pending step's parameters before composition.

Design goals:
  - No LLM calls — purely deterministic
  - Fail-open: validation failures produce warnings, not hard blocks
    (except the destructive gate which is a hard block by design)
  - Returns a ``VerificationResult`` that the ResponseComposer uses to
    decide whether to include a confirmation prompt in the output

Usage::

    verifier = Verifier(manifest_index=index, inventory_service=service)
    verification = await verifier.verify(plan, execution_result)
    if verification.needs_confirmation:
        # ResponseComposer should ask the user before proceeding
        ...
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

try:
    from app.agentic.eol.utils.planner import ExecutionPlan, PlanStep, ToolAffordance
    from app.agentic.eol.utils.executor import ExecutionResult, StepResult
    from app.agentic.eol.utils.tool_manifest_index import ToolManifestIndex
    from app.agentic.eol.utils.resource_inventory_service import ResourceInventoryService
except ModuleNotFoundError:
    from utils.planner import ExecutionPlan, PlanStep, ToolAffordance  # type: ignore[import-not-found]
    from utils.executor import ExecutionResult, StepResult  # type: ignore[import-not-found]
    from utils.tool_manifest_index import ToolManifestIndex  # type: ignore[import-not-found]
    from utils.resource_inventory_service import ResourceInventoryService  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """A single validation warning or error from the Verifier."""

    step_id: str
    severity: str  # "warning" | "error" | "blocked"
    message: str
    tool_name: str = ""
    field_path: str = ""  # JSON path to the offending field, if schema-related


@dataclass
class VerificationResult:
    """Output of Verifier.verify()."""

    plan: ExecutionPlan
    execution_result: ExecutionResult

    issues: List[ValidationIssue] = field(default_factory=list)
    """All validation issues found (may be empty)."""

    needs_confirmation: bool = False
    """True when at least one destructive step requires user confirmation."""

    blocked_steps: List[str] = field(default_factory=list)
    """step_id values that were hard-blocked (e.g. missing required resource)."""

    preflight_failures: List[str] = field(default_factory=list)
    """step_id values that failed preflight resource check."""

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "needs_confirmation": self.needs_confirmation,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "blocked_steps": self.blocked_steps,
            "preflight_failures": self.preflight_failures,
            "issues": [
                {
                    "step_id": i.step_id,
                    "severity": i.severity,
                    "message": i.message,
                    "tool_name": i.tool_name,
                    "field_path": i.field_path,
                }
                for i in self.issues
            ],
        }


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class Verifier:
    """Deterministic result validation for Phase 6 pipeline.

    Args:
        manifest_index: Optional ``ToolManifestIndex`` for schema validation.
            If None, schema validation is skipped.
        inventory_service: Optional ``ResourceInventoryService`` for preflight
            checks.  If None, preflight checks are skipped (fail-open).
    """

    def __init__(
        self,
        manifest_index: Optional[ToolManifestIndex] = None,
        inventory_service: Optional[ResourceInventoryService] = None,
    ) -> None:
        self._manifest_index = manifest_index
        self._inventory = inventory_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(
        self,
        plan: ExecutionPlan,
        execution_result: ExecutionResult,
    ) -> VerificationResult:
        """Validate an execution result.

        Performs in order:
          1. Destructive gate check
          2. Schema validation of step results
          3. Preflight check for skipped/pending steps

        Args:
            plan: The ``ExecutionPlan`` that was executed.
            execution_result: The ``ExecutionResult`` from ``Executor.execute()``.

        Returns:
            ``VerificationResult`` — always returned, never raises.
        """
        vr = VerificationResult(plan=plan, execution_result=execution_result)

        # Build a map of step_id → PlanStep for quick lookup
        step_map: Dict[str, PlanStep] = {s.step_id: s for s in plan.steps}

        # 1. Destructive gate
        self._check_destructive_gate(vr, step_map, execution_result)

        # 2. Schema validation
        self._validate_schemas(vr, step_map, execution_result)

        # 3. Preflight checks
        await self._run_preflight_checks(vr, step_map, execution_result)

        return vr

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_destructive_gate(
        self,
        vr: VerificationResult,
        step_map: Dict[str, PlanStep],
        execution_result: ExecutionResult,
    ) -> None:
        """Flag any skipped destructive step as needing confirmation."""
        for sr in execution_result.skipped_results:
            step = step_map.get(sr.step_id)
            if step is None:
                continue
            if step.affordance in (ToolAffordance.DESTRUCTIVE, ToolAffordance.DEPLOY):
                vr.needs_confirmation = True
                vr.issues.append(
                    ValidationIssue(
                        step_id=sr.step_id,
                        tool_name=step.tool_name,
                        severity="blocked",
                        message=(
                            f"Step '{step.tool_name}' requires explicit confirmation before execution "
                            f"(affordance={step.affordance.value}). "
                            f"Reason: {sr.skip_reason}"
                        ),
                    )
                )
                vr.blocked_steps.append(sr.step_id)
                logger.info(
                    "🛑 Verifier: destructive step %s (%s) needs confirmation",
                    sr.step_id,
                    step.tool_name,
                )

    def _validate_schemas(
        self,
        vr: VerificationResult,
        step_map: Dict[str, PlanStep],
        execution_result: ExecutionResult,
    ) -> None:
        """Validate successful step results against output_schema in ToolManifest."""
        if self._manifest_index is None:
            return

        for sr in execution_result.successful_results:
            if sr.result is None:
                continue
            step = step_map.get(sr.step_id)
            if step is None:
                continue
            manifest = self._manifest_index.get(step.tool_name)
            if manifest is None or not manifest.output_schema:
                continue

            issues = _validate_against_schema(
                sr.result, manifest.output_schema, sr.step_id, step.tool_name
            )
            vr.issues.extend(issues)
            if issues:
                logger.debug(
                    "Verifier: schema issues for step %s (%s): %s",
                    sr.step_id,
                    step.tool_name,
                    [i.message for i in issues],
                )

    async def _run_preflight_checks(
        self,
        vr: VerificationResult,
        step_map: Dict[str, PlanStep],
        execution_result: ExecutionResult,
    ) -> None:
        """Run preflight resource-existence checks on skipped steps."""
        if self._inventory is None:
            return

        for sr in execution_result.skipped_results:
            step = step_map.get(sr.step_id)
            if step is None:
                continue
            if step.tool_name == "legacy_react":
                continue
            try:
                preflight = await self._inventory.preflight_check(
                    step.tool_name, step.params
                )
                if not preflight.passed:
                    issues = preflight.issues or ["Preflight check failed"]
                    for issue_msg in issues:
                        vr.issues.append(
                            ValidationIssue(
                                step_id=sr.step_id,
                                tool_name=step.tool_name,
                                severity="warning",
                                message=f"Preflight: {issue_msg}",
                            )
                        )
                    vr.preflight_failures.append(sr.step_id)
                    logger.warning(
                        "Verifier: preflight failed for step %s (%s): %s",
                        sr.step_id,
                        step.tool_name,
                        issues,
                    )
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug(
                    "Verifier: preflight exception for step %s (non-fatal): %s",
                    sr.step_id,
                    exc,
                )


# ---------------------------------------------------------------------------
# Schema validation helper
# ---------------------------------------------------------------------------


def _validate_against_schema(
    result: Dict[str, Any],
    schema: Dict[str, Any],
    step_id: str,
    tool_name: str,
) -> List[ValidationIssue]:
    """Minimal JSON-schema-style validation.

    Only checks ``required`` fields and ``type`` constraints for the top-level
    properties dict.  Does NOT recursively validate nested objects.

    Args:
        result: The tool result dict.
        schema: JSON schema dict (``{"type": "object", "properties": {...}, "required": [...]}``)
        step_id: Used in returned ValidationIssue objects.
        tool_name: Used in returned ValidationIssue objects.

    Returns:
        List of ValidationIssue (may be empty if all checks pass).
    """
    issues: List[ValidationIssue] = []

    if not isinstance(schema, dict):
        return issues

    required_fields = schema.get("required") or []
    properties = schema.get("properties") or {}

    for req_field in required_fields:
        if req_field not in result:
            issues.append(
                ValidationIssue(
                    step_id=step_id,
                    tool_name=tool_name,
                    severity="warning",
                    message=f"Required field '{req_field}' missing from tool result.",
                    field_path=req_field,
                )
            )

    for prop_name, prop_schema in properties.items():
        if prop_name not in result:
            continue
        expected_type = prop_schema.get("type")
        if expected_type is None:
            continue
        value = result[prop_name]
        if not _check_json_type(value, expected_type):
            issues.append(
                ValidationIssue(
                    step_id=step_id,
                    tool_name=tool_name,
                    severity="warning",
                    message=(
                        f"Field '{prop_name}' has unexpected type "
                        f"{type(value).__name__!r} (expected {expected_type!r})."
                    ),
                    field_path=prop_name,
                )
            )

    return issues


def _check_json_type(value: Any, expected_type: str) -> bool:
    """Return True when *value* matches the JSON Schema *expected_type*."""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    expected_py = type_map.get(expected_type)
    if expected_py is None:
        return True  # Unknown type — pass
    return isinstance(value, expected_py)
