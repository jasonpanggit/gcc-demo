"""Pipeline ResponseComposer — Stage 6 (final) of the MCP orchestrator pipeline.

Produces the final HTML response from:
  - The original user query
  - All step results from the Executor
  - The VerificationResult (knows about blocked/skipped steps)

Design goals:
  - 1 LLM call, temperature=0.3, no tools
  - Instructs the LLM to produce raw HTML (same format as legacy ReAct loop)
  - Includes Chart.js for time-series data; HTML tables for structured data
  - When destructive steps were blocked: includes a clear confirmation prompt
    so the user knows exactly what they need to confirm to proceed
  - Graceful fallback: if LLM unavailable, builds a static HTML summary

Usage::

    composer = ResponseComposer()
    html = await composer.compose(query, execution_result, verification_result)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

try:
    from app.agentic.eol.utils.executor import ExecutionResult, StepResult
    from app.agentic.eol.utils.verifier import VerificationResult
    from app.agentic.eol.utils.planner import ToolAffordance
except ModuleNotFoundError:
    from utils.executor import ExecutionResult, StepResult  # type: ignore[import-not-found]
    from utils.verifier import VerificationResult  # type: ignore[import-not-found]
    from utils.planner import ToolAffordance  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_COMPOSER_SYSTEM_PROMPT = """You are the Azure Operations Report Composer.

Given a user query and the results of one or more tool executions, write a
complete, accurate HTML response for display in a web dashboard.

## Rules

1. Output ONLY valid HTML — no markdown, no backticks, no prose outside HTML.
2. Your entire response must be valid HTML that can be inserted into a webpage.
3. Use HTML <table> for structured data (resource lists, metrics, rules).
4. For time-series metrics (multiple timestamps) render a Chart.js line chart:
   - Use a unique canvas id (e.g. "chart-<tool_name>").
   - Colors: CPU=#2196F3, Memory=#4CAF50, Disk=#FF9800, Network=#9C27B0,
     Requests=#E91E63, Latency=#00BCD4.
5. For single-value metrics use a colored <div> progress bar.
6. Each section should start with an <h3> heading.
7. If a step failed, include a styled error <div> with the error text.
8. If no data was returned, say so clearly — NEVER invent data.
9. End with a concise <p> summary.
10. For effective-route outputs, render ALL route rows returned by tools (do not sample or collapse).

## Confirmation prompts (destructive steps)

If the BLOCKED STEPS section is non-empty, include at the end a styled
confirmation section:
  <div class="confirmation-required" style="border: 2px solid #f44336; padding: 12px; border-radius: 6px; margin-top: 16px;">
    <strong>⚠️ Action Required — Confirmation Needed</strong>
    <p>The following operations require explicit confirmation before they can run:</p>
    <ul>...</ul>
    <p>To proceed, reply: <code>confirm: yes</code></p>
  </div>
"""


# ---------------------------------------------------------------------------
# ResponseComposer
# ---------------------------------------------------------------------------


class ResponseComposer:
    """Produces a final HTML response from pipeline execution results.

    Args:
        None — all dependencies resolved from environment variables.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compose(
        self,
        query: str,
        execution_result: ExecutionResult,
        verification_result: Optional[VerificationResult] = None,
    ) -> str:
        """Produce the final HTML response.

        Args:
            query: Original user query.
            execution_result: Output of ``Executor.execute()``.
            verification_result: Output of ``Verifier.verify()``.  If None,
                blocking information is sourced directly from execution_result.

        Returns:
            HTML string ready to be returned to the user.
        """
        user_prompt = _build_composer_user_prompt(
            query, execution_result, verification_result
        )

        ok, content = await self._call_llm(
            _COMPOSER_SYSTEM_PROMPT, user_prompt, temperature=0.3, max_tokens=2000
        )
        if ok and content.strip():
            logger.info("✍️ ResponseComposer: LLM produced HTML (%d chars)", len(content))
            return content

        # Fallback: static HTML summary
        logger.warning("ResponseComposer: LLM unavailable; using static fallback")
        return _build_static_fallback(query, execution_result, verification_result)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> tuple[bool, str]:
        """Single LLM call (no tools)."""
        try:
            from openai import AsyncAzureOpenAI  # type: ignore[import-not-found]

            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            if not endpoint:
                return False, ""

            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            deployment = (
                os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            )

            async_credential = None
            if api_key:
                client = AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )
            else:
                from azure.identity.aio import (  # type: ignore[import-not-found]
                    DefaultAzureCredential as AsyncDefaultAzureCredential,
                )
                async_credential = AsyncDefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                token = await async_credential.get_token(
                    "https://cognitiveservices.azure.com/.default"
                )
                client = AsyncAzureOpenAI(
                    api_key=token.token,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

            try:
                raw = await client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            finally:
                await client.close()
                if async_credential:
                    await async_credential.close()

            return True, raw.choices[0].message.content or ""

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("ResponseComposer LLM call failed: %s", exc)
            return False, ""


# ---------------------------------------------------------------------------
# User-prompt builder
# ---------------------------------------------------------------------------


def _build_composer_user_prompt(
    query: str,
    execution_result: ExecutionResult,
    verification_result: Optional[VerificationResult],
) -> str:
    """Build the user-prompt for the ResponseComposer LLM call."""
    parts = [f"USER QUERY: {query}", ""]

    # Step results
    parts.append("TOOL EXECUTION RESULTS:")
    for sr in execution_result.step_results:
        if sr.skipped:
            parts.append(
                f"  [{sr.step_id}] {sr.tool_name}: SKIPPED — {sr.skip_reason}"
            )
        elif sr.success:
            result_summary = _summarise_result(sr.result, sr.tool_name)
            parts.append(
                f"  [{sr.step_id}] {sr.tool_name}: SUCCESS\n{result_summary}"
            )
        else:
            parts.append(f"  [{sr.step_id}] {sr.tool_name}: FAILED — {sr.error}")

    # Blocked steps requiring confirmation
    blocked: List[str] = []
    if verification_result:
        blocked = verification_result.blocked_steps
    else:
        blocked = [
            sr.step_id
            for sr in execution_result.skipped_results
        ]

    if blocked:
        parts += [
            "",
            "BLOCKED STEPS (require user confirmation before execution):",
        ]
        step_map = {s.step_id: s for s in execution_result.plan.steps}
        for sid in blocked:
            step = step_map.get(sid)
            if step:
                params_str = json.dumps(step.params, default=str)[:200]
                parts.append(
                    f"  - {sid}: {step.tool_name}(params={params_str})"
                )

    # Verification issues
    if verification_result and verification_result.issues:
        parts += ["", "VALIDATION NOTES:"]
        for issue in verification_result.issues[:10]:
            parts.append(f"  [{issue.severity.upper()}] {issue.step_id}: {issue.message}")

    parts += ["", "Write the HTML response now:"]
    return "\n".join(parts)


def _summarise_result(result: Optional[Dict[str, Any]], tool_name: str = "") -> str:
    """Produce a concise JSON summary of a tool result for the LLM prompt."""
    if result is None:
        return "  (no result)"
    if result.get("_legacy"):
        return "  (handled by legacy ReAct loop)"

    # Preserve complete effective-route data for rendering (avoid truncating to sample rows).
    if tool_name == "get_effective_routes":
        try:
            parsed = result.get("parsed") if isinstance(result, dict) else None
            payload: Optional[Dict[str, Any]] = parsed if isinstance(parsed, dict) else None

            if payload is None and isinstance(result, dict):
                content = result.get("content")
                if isinstance(content, list):
                    for entry in content:
                        if not isinstance(entry, str):
                            continue
                        try:
                            candidate = json.loads(entry)
                        except Exception:
                            continue
                        if isinstance(candidate, dict):
                            payload = candidate
                            break

            if isinstance(payload, dict):
                normalized_rows: List[Dict[str, Any]] = []
                for nic in payload.get("nic_routes") or []:
                    if not isinstance(nic, dict):
                        continue
                    nic_label = nic.get("nic_name") or "unknown"
                    rg_label = nic.get("resource_group") or "unknown"
                    for route in nic.get("routes") or []:
                        if not isinstance(route, dict):
                            continue
                        prefixes = route.get("address_prefix")
                        if isinstance(prefixes, list) and prefixes:
                            prefix_value = ", ".join(str(p) for p in prefixes)
                        elif prefixes is None:
                            prefix_value = ""
                        else:
                            prefix_value = str(prefixes)
                        normalized_rows.append(
                            {
                                "nic_name": nic_label,
                                "resource_group": rg_label,
                                "address_prefix": prefix_value,
                                "next_hop_type": route.get("next_hop_type"),
                                "state": route.get("state"),
                                "source": route.get("source"),
                                "name": route.get("name"),
                            }
                        )

                effective_payload = {
                    "success": payload.get("success"),
                    "vm_name": payload.get("vm_name"),
                    "total_routes": payload.get("total_routes"),
                    "successful_nics": payload.get("successful_nics"),
                    "failed_nics": payload.get("failed_nics"),
                    "effective_routes": normalized_rows,
                }
                return json.dumps(effective_payload, indent=2, default=str)
        except Exception:
            # Fall through to generic summarization
            pass

    try:
        text = json.dumps(result, indent=2, default=str)
        limit = 12000 if tool_name == "get_effective_routes" else 2000
        if len(text) > limit:
            text = text[:limit] + "\n  ... (truncated)"
        return text
    except Exception:
        return str(result)[:500]


# ---------------------------------------------------------------------------
# Static HTML fallback
# ---------------------------------------------------------------------------


def _build_static_fallback(
    query: str,
    execution_result: ExecutionResult,
    verification_result: Optional[VerificationResult],
) -> str:
    """Build a minimal HTML page when the LLM is unavailable."""
    import html as _html

    rows: List[str] = []
    for sr in execution_result.step_results:
        status = "⏭️ Skipped" if sr.skipped else ("✅ OK" if sr.success else "❌ Failed")
        detail = sr.skip_reason or sr.error or ""
        rows.append(
            f"<tr>"
            f"<td>{_html.escape(sr.step_id)}</td>"
            f"<td>{_html.escape(sr.tool_name)}</td>"
            f"<td>{status}</td>"
            f"<td>{_html.escape(detail[:120])}</td>"
            f"</tr>"
        )

    confirmation_html = ""
    blocked: List[str] = []
    if verification_result:
        blocked = verification_result.blocked_steps
    else:
        blocked = [sr.step_id for sr in execution_result.skipped_results]

    if blocked:
        step_map = {s.step_id: s for s in execution_result.plan.steps}
        items = "".join(
            f"<li>{_html.escape(sid)}: <code>{_html.escape(step_map[sid].tool_name if sid in step_map else sid)}</code></li>"
            for sid in blocked
        )
        confirmation_html = (
            "<div style='border:2px solid #f44336;padding:12px;border-radius:6px;margin-top:16px;'>"
            "<strong>⚠️ Action Required — Confirmation Needed</strong>"
            "<p>The following operations require explicit confirmation before they can run:</p>"
            f"<ul>{items}</ul>"
            "<p>To proceed, reply: <code>confirm: yes</code></p>"
            "</div>"
        )

    return (
        f"<h3>Query Results</h3>"
        f"<p><em>Query: {_html.escape(query)}</em></p>"
        f"<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
        f"<thead><tr><th>Step</th><th>Tool</th><th>Status</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
        f"{confirmation_html}"
        f"<p>{'All steps completed successfully.' if execution_result.all_succeeded and not blocked else 'Some steps require attention — see above.'}</p>"
    )
