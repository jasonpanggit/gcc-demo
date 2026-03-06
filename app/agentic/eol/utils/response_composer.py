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

_COMPOSER_NOISY_KEYS = {
    "stdout",
    "stderr",
    "raw",
    "raw_output",
    "content_raw",
    "metadata_raw",
    "debug",
    "trace",
    "stack",
    "exception",
    "template",
    "properties",
    "identity",
    "systemData",
    "delegatedIdentities",
    "outboundIpAddresses",
}

_COMPOSER_PRIORITY_KEYS = [
    "name",
    "id",
    "resource_id",
    "resource_group",
    "resourceGroup",
    "location",
    "type",
    "status",
    "state",
    "severity",
    "summary",
    "message",
    "timestamp",
    "total",
    "count",
]


def _compact_for_composer(value: Any, depth: int = 0) -> Any:
    """Recursively compact tool payloads to reduce prompt tokens.

    Keeps identifiers and status fields, drops known noisy fields, and caps
    list/dict breadth so LLM context remains stable for all tools.
    """
    if depth >= 4:
        if isinstance(value, (dict, list)):
            return "<omitted:depth-limit>"
        return value

    if isinstance(value, str):
        return value if len(value) <= 400 else value[:400] + "..."

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, list):
        max_items = 40
        compact_items = [_compact_for_composer(item, depth + 1) for item in value[:max_items]]
        if len(value) > max_items:
            compact_items.append(f"<omitted:{len(value) - max_items} more items>")
        return compact_items

    if isinstance(value, dict):
        keys = list(value.keys())
        preferred = [k for k in _COMPOSER_PRIORITY_KEYS if k in value]
        remaining = [k for k in keys if k not in preferred and k not in _COMPOSER_NOISY_KEYS]
        ordered = preferred + remaining

        compact_dict: Dict[str, Any] = {}
        max_keys = 40
        for key in ordered[:max_keys]:
            compact_dict[key] = _compact_for_composer(value.get(key), depth + 1)

        if len(ordered) > max_keys:
            compact_dict["_omitted_keys"] = len(ordered) - max_keys
        return compact_dict

    return str(value)


def _extract_payload_dict(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract the most useful dict payload from nested tool wrappers."""
    if not isinstance(result, dict):
        return None

    if isinstance(result.get("parsed"), dict):
        return result.get("parsed")

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        if isinstance(nested_result.get("parsed"), dict):
            return nested_result.get("parsed")
        return nested_result

    nested_data = result.get("data")
    if isinstance(nested_data, dict):
        return nested_data

    return result


def _is_list_style_tool(tool_name: str) -> bool:
    lowered = (tool_name or "").lower()
    return (
        lowered.endswith("_list")
        or lowered.startswith("list_")
        or "_list_" in lowered
        or lowered in {"subscription_list", "resource_group_list", "container_app_list"}
    )


def _compact_list_tool_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compact list-tool payloads into deterministic render fields."""
    list_candidates = [
        payload.get("apps"),
        payload.get("items"),
        payload.get("resources"),
        payload.get("value"),
        payload.get("data"),
        payload.get("result"),
    ]

    items_list: Optional[List[Any]] = None
    for candidate in list_candidates:
        if isinstance(candidate, list):
            items_list = candidate
            break

    if not isinstance(items_list, list):
        return None

    compact_items: List[Dict[str, Any]] = []
    for item in items_list:
        if not isinstance(item, dict):
            continue
        compact_items.append(
            {
                "name": item.get("name") or item.get("resource_name") or item.get("display_name"),
                "resource_group": item.get("resource_group") or item.get("resourceGroup"),
                "location": item.get("location"),
                "type": item.get("type") or item.get("resource_type"),
                "status": item.get("status") or item.get("state") or item.get("provisioning_state") or item.get("provisioningState"),
                "id": item.get("id") or item.get("resource_id"),
            }
        )

    if not compact_items and items_list:
        # Non-dict list entries (for example, simple strings)
        compact_items = [{"value": str(v)} for v in items_list]

    total_items = (
        payload.get("total_apps")
        or payload.get("total_items")
        or payload.get("total")
        or payload.get("count")
        or len(items_list)
    )

    return {
        "success": payload.get("success"),
        "total_items": total_items,
        "items": compact_items,
    }


def _is_detail_style_tool(tool_name: str) -> bool:
    """Whether a tool is likely to return detailed non-list payloads."""
    lowered = (tool_name or "").lower()
    detail_markers = (
        "configuration",
        "diagnostic",
        "dependency",
        "health",
        "metric",
        "log",
        "compliance",
        "performance",
        "security",
    )
    return any(marker in lowered for marker in detail_markers)


def _compact_detail_tool_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compact detail/diagnostic payloads while preserving key semantics."""
    top_keys = [
        "success",
        "status",
        "summary",
        "message",
        "resource_name",
        "resource_group",
        "resource_id",
        "resource_type",
        "time_range",
        "count",
        "total",
        "healthy",
        "unhealthy",
    ]

    compact: Dict[str, Any] = {}
    for key in top_keys:
        if key in payload:
            compact[key] = _compact_for_composer(payload.get(key), depth=1)

    # Preserve common analysis buckets in compact form.
    candidate_sections = [
        "configuration",
        "settings",
        "properties",
        "findings",
        "issues",
        "recommendations",
        "dependencies",
        "alerts",
        "metrics",
        "routes",
        "logs",
        "results",
    ]
    for section in candidate_sections:
        if section in payload:
            compact[section] = _compact_for_composer(payload.get(section), depth=1)

    # Keep a small, generic tail of extra keys so we do not lose unique tool data.
    if len(compact) < 12:
        for key, value in payload.items():
            if key in compact or key in _COMPOSER_NOISY_KEYS:
                continue
            compact[key] = _compact_for_composer(value, depth=1)
            if len(compact) >= 12:
                break

    return compact


def _tool_result_source(result: Optional[Dict[str, Any]]) -> str:
    """Best-effort extraction of source marker from tool result payload."""
    payload = _extract_payload_dict(result)
    if not isinstance(payload, dict):
        return ""

    source = payload.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip()

    nested_data = payload.get("data")
    if isinstance(nested_data, dict):
        nested_source = nested_data.get("source")
        if isinstance(nested_source, str) and nested_source.strip():
            return nested_source.strip()

    return ""


def _should_use_deterministic_renderer(execution_result: "ExecutionResult") -> bool:
    """Return True when code-based rendering should bypass the LLM composer.

    This path is designed for structured inventory/list outputs where LLM
    summarization adds cost without adding value.
    """
    successful = [sr for sr in execution_result.step_results if sr.success and not sr.skipped]
    if not successful:
        return False

    known_structured_tools = {
        "container_app_list",
        "law_get_os_summary",
        "azure_resource_get_os_summary",
        "inventory_cached_discovery",
    }
    cache_sources = {
        "resource_inventory_cache",
        "azure_resource_inventory",
    }

    for sr in successful:
        if sr.tool_name in known_structured_tools:
            continue
        if _tool_result_source(sr.result) in cache_sources:
            continue
        return False

    return True


def _extract_completion_text(raw: Any) -> str:
    """Extract assistant text from chat-completions style responses.

    Supports both legacy string ``message.content`` and newer structured
    content-part payloads returned by GPT-5-family models.
    """
    try:
        # Some Azure/OpenAI SDK variants expose a direct output_text field.
        direct_output_text = getattr(raw, "output_text", None)
        if isinstance(direct_output_text, str) and direct_output_text.strip():
            return direct_output_text

        choices = getattr(raw, "choices", None) or []
        if choices:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            content = getattr(message, "content", "") if message is not None else ""

            # Some SDK builds expose plain text directly on the choice.
            choice_text = getattr(first_choice, "text", None)
            if isinstance(choice_text, str) and choice_text.strip():
                return choice_text

            if isinstance(content, str):
                return content

            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                        continue

                    text_value: Optional[str] = None
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            text_value = text
                        elif isinstance(text, dict):
                            nested = text.get("value")
                            if isinstance(nested, str):
                                text_value = nested
                        if text_value is None:
                            # Additional content-part shape: {"content": "..."} or {"value": "..."}
                            alt_content = item.get("content")
                            if isinstance(alt_content, str):
                                text_value = alt_content
                            elif isinstance(alt_content, dict):
                                nested = alt_content.get("value")
                                if isinstance(nested, str):
                                    text_value = nested
                            elif isinstance(alt_content, list):
                                nested_parts = [str(p) for p in alt_content if isinstance(p, str)]
                                if nested_parts:
                                    text_value = "\n".join(nested_parts)
                        if text_value is None and isinstance(item.get("value"), str):
                            text_value = item.get("value")
                    else:
                        obj_text = getattr(item, "text", None)
                        if isinstance(obj_text, str):
                            text_value = obj_text
                        elif isinstance(obj_text, dict):
                            nested = obj_text.get("value")
                            if isinstance(nested, str):
                                text_value = nested
                        if text_value is None:
                            obj_content = getattr(item, "content", None)
                            if isinstance(obj_content, str):
                                text_value = obj_content
                            elif isinstance(obj_content, dict):
                                nested = obj_content.get("value")
                                if isinstance(nested, str):
                                    text_value = nested
                        if text_value is None:
                            obj_value = getattr(item, "value", None)
                            if isinstance(obj_value, str):
                                text_value = obj_value

                    if text_value:
                        parts.append(text_value)

                if parts:
                    return "\n".join(parts)

            # Last-resort fallback for unknown object payloads.
            if content is not None:
                content_str = str(content)
                if content_str and content_str != "None":
                    return content_str

    except Exception:
        pass

    return ""

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
     - For VM utilization queries, if metrics include both "Percentage CPU" and
         "Available Memory Bytes", render BOTH. Show memory as available GiB
         (convert bytes to GiB where useful) and do not omit memory.
5. For single-value metrics use a colored <div> progress bar.
6. Each section should start with an <h3> heading.
7. If a step failed, include a styled error <div> with the error text.
8. If no data was returned, say so clearly — NEVER invent data.
9. End with a concise <p> summary.
10. For effective-route outputs, render ALL route rows returned by tools (do not sample or collapse).
11. For list/discovery outputs (for example, container app inventory), include ALL returned items unless the user explicitly asks for a subset (such as top 5).
12. If OS summary data is present from Arc and/or Azure inventory, use explicit section labels:
    - <h3>Arc-Enabled Servers OS Summary</h3> for law_get_os_summary output.
    - <h3>Azure Virtual Machines OS Summary (Resource Inventory)</h3> for azure_resource_get_os_summary output.

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
        if _should_use_deterministic_renderer(execution_result):
            logger.info(
                "ResponseComposer: using deterministic renderer (cache-backed/structured outputs)",
            )
            return _build_static_fallback(
                query,
                execution_result,
                verification_result,
                include_step_table=False,
            )

        user_prompt = _build_composer_user_prompt(
            query, execution_result, verification_result
        )

        ok, content = await self._call_llm(
            _COMPOSER_SYSTEM_PROMPT, user_prompt, temperature=0.3, max_tokens=2000
        )
        if ok and content.strip():
            logger.info("✍️ ResponseComposer: LLM produced HTML (%d chars)", len(content))
            return content

        if ok and not content.strip():
            logger.warning("ResponseComposer: LLM call succeeded but returned empty content")
        elif not ok:
            logger.warning("ResponseComposer: LLM call reported failure")

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
                logger.warning("ResponseComposer: AZURE_OPENAI_ENDPOINT is not configured")
                return False, ""

            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            deployment = (
                os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            )
            logger.info(
                "ResponseComposer: invoking Azure OpenAI deployment=%s api_version=%s endpoint_set=%s",
                deployment,
                api_version,
                bool(endpoint),
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
                # GPT-5 deployments reject `max_tokens`; use `max_completion_tokens`.
                completion_kwargs = {
                    "model": deployment,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }

                deployment_lower = (deployment or "").lower()
                if deployment_lower.startswith("gpt-5"):
                    # Azure GPT-5 currently only supports default temperature behavior.
                    completion_kwargs["max_completion_tokens"] = max_tokens
                else:
                    completion_kwargs["temperature"] = temperature
                    completion_kwargs["max_tokens"] = max_tokens

                raw = await client.chat.completions.create(
                    **completion_kwargs,
                )
            finally:
                await client.close()
                if async_credential:
                    await async_credential.close()

            extracted = _extract_completion_text(raw)
            if not extracted.strip():
                try:
                    choices = getattr(raw, "choices", None) or []
                    first = choices[0] if choices else None
                    message = getattr(first, "message", None) if first is not None else None
                    content_obj = getattr(message, "content", None) if message is not None else None
                    logger.warning(
                        "ResponseComposer: empty extracted text (raw_type=%s, has_choices=%s, content_type=%s)",
                        type(raw).__name__,
                        bool(choices),
                        type(content_obj).__name__ if content_obj is not None else "None",
                    )
                except Exception:
                    logger.warning("ResponseComposer: empty extracted text (unable to inspect raw shape)")

            return True, extracted

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
    has_arc_os_summary = False
    has_azure_os_summary = False

    # Step results
    parts.append("TOOL EXECUTION RESULTS:")
    for sr in execution_result.step_results:
        if sr.success and sr.tool_name == "law_get_os_summary":
            has_arc_os_summary = True
        if sr.success and sr.tool_name == "azure_resource_get_os_summary":
            has_azure_os_summary = True

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

    if has_arc_os_summary or has_azure_os_summary:
        parts += ["", "SPECIAL LABELING REQUIREMENT:"]
        if has_arc_os_summary:
            parts.append("  - Include section heading exactly: Arc-Enabled Servers OS Summary")
        if has_azure_os_summary:
            parts.append("  - Include section heading exactly: Azure Virtual Machines OS Summary (Resource Inventory)")

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

    if _is_list_style_tool(tool_name):
        try:
            payload = _extract_payload_dict(result)
            if isinstance(payload, dict):
                compact_list_payload = _compact_list_tool_payload(payload)
                if compact_list_payload is not None:
                    text = json.dumps(compact_list_payload, indent=2, default=str)
                    if len(text) > 12000:
                        text = text[:12000] + "\n  ... (truncated)"
                    return text
        except Exception:
            # Fall through to tool-specific or generic summarization
            pass

    if _is_detail_style_tool(tool_name):
        try:
            payload = _extract_payload_dict(result)
            if isinstance(payload, dict):
                compact_detail = _compact_detail_tool_payload(payload)
                text = json.dumps(compact_detail, indent=2, default=str)
                if len(text) > 10000:
                    text = text[:10000] + "\n  ... (truncated)"
                return text
        except Exception:
            # Fall through to tool-specific or generic summarization
            pass

    if tool_name == "get_performance_metrics":
        try:
            def _extract_metric_values(metric_item: Dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[float]]:
                summary = metric_item.get("summary") if isinstance(metric_item.get("summary"), dict) else {}
                current = summary.get("current") if isinstance(summary.get("current"), (int, float)) else None
                average = summary.get("average") if isinstance(summary.get("average"), (int, float)) else None
                maximum = summary.get("maximum") if isinstance(summary.get("maximum"), (int, float)) else None
                return (
                    float(current) if current is not None else None,
                    float(average) if average is not None else None,
                    float(maximum) if maximum is not None else None,
                )

            def _extract_metric_summary(metrics_payload: Any) -> Dict[str, Any]:
                cpu_percent: Optional[float] = None
                memory_available_bytes: Optional[float] = None

                if isinstance(metrics_payload, list):
                    for metric_item in metrics_payload:
                        if not isinstance(metric_item, dict):
                            continue
                        metric_name = str(metric_item.get("metric_name") or metric_item.get("name") or "").lower()
                        current, average, _maximum = _extract_metric_values(metric_item)
                        representative = current if current is not None else average

                        if representative is None:
                            continue
                        if "cpu" in metric_name and "percent" in metric_name:
                            cpu_percent = representative
                        if "available" in metric_name and "memory" in metric_name and "byte" in metric_name:
                            memory_available_bytes = representative

                memory_available_gib = (
                    (memory_available_bytes / (1024 ** 3))
                    if isinstance(memory_available_bytes, (int, float))
                    else None
                )

                return {
                    "cpu_percent": round(cpu_percent, 2) if isinstance(cpu_percent, (int, float)) else None,
                    "memory_available_bytes": round(memory_available_bytes, 2) if isinstance(memory_available_bytes, (int, float)) else None,
                    "memory_available_gib": round(memory_available_gib, 2) if isinstance(memory_available_gib, (int, float)) else None,
                }

            if result.get("fanout") is True and isinstance(result.get("results"), list):
                normalized_items: List[Dict[str, Any]] = []
                for item in result.get("results", []):
                    if not isinstance(item, dict):
                        continue
                    params = item.get("params") if isinstance(item.get("params"), dict) else {}
                    payload = item.get("result") if isinstance(item.get("result"), dict) else {}
                    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else None
                    metric_payload = (
                        parsed.get("metrics") if isinstance(parsed, dict)
                        else payload.get("metrics")
                    )
                    metric_summary = _extract_metric_summary(metric_payload)

                    normalized_items.append(
                        {
                            "resource_id": params.get("resource_id") or payload.get("resource_id"),
                            "resource_name": (
                                parsed.get("resource_name") if isinstance(parsed, dict)
                                else payload.get("resource_name")
                            ),
                            "resource_type": (
                                parsed.get("resource_type") if isinstance(parsed, dict)
                                else payload.get("resource_type")
                            ),
                            "metrics": (
                                parsed.get("metrics") if isinstance(parsed, dict)
                                else payload.get("metrics")
                            ),
                            "metric_summary": metric_summary,
                            "time_range": (
                                parsed.get("time_range") if isinstance(parsed, dict)
                                else payload.get("time_range")
                            ),
                        }
                    )

                compact = {
                    "success": result.get("success"),
                    "partial_failure": result.get("partial_failure"),
                    "fanout": True,
                    "total_targets": result.get("total_targets"),
                    "successful_targets": result.get("successful_targets"),
                    "failed_targets": result.get("failed_targets"),
                    "performance_metrics": normalized_items,
                }

                text = json.dumps(compact, indent=2, default=str)
                if len(text) > 12000:
                    text = text[:12000] + "\n  ... (truncated)"
                return text
        except Exception:
            # Fall through to generic summarization
            pass

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

    # Keep container-app list prompts compact and deterministic. Passing large
    # raw payloads can degrade model reliability even when the tool succeeds.
    if tool_name == "container_app_list":
        try:
            payload: Optional[Dict[str, Any]] = None
            if isinstance(result, dict):
                if isinstance(result.get("parsed"), dict):
                    payload = result.get("parsed")
                elif isinstance(result.get("result"), dict):
                    nested_result = result.get("result")
                    if isinstance(nested_result.get("parsed"), dict):
                        payload = nested_result.get("parsed")
                    else:
                        payload = nested_result
                else:
                    payload = result

            apps_raw = payload.get("apps") if isinstance(payload, dict) else None
            if isinstance(apps_raw, list):
                compact_apps: List[Dict[str, Any]] = []
                for app in apps_raw:
                    if not isinstance(app, dict):
                        continue
                    compact_apps.append(
                        {
                            "name": app.get("name"),
                            "resource_group": app.get("resource_group") or app.get("resourceGroup"),
                            "location": app.get("location"),
                            "provisioning_state": app.get("provisioning_state") or app.get("provisioningState"),
                        }
                    )

                compact_payload = {
                    "success": payload.get("success") if isinstance(payload, dict) else None,
                    "total_apps": payload.get("total_apps") if isinstance(payload, dict) else len(compact_apps),
                    "apps": compact_apps,
                }
                text = json.dumps(compact_payload, indent=2, default=str)
                if len(text) > 12000:
                    text = text[:12000] + "\n  ... (truncated)"
                return text
        except Exception:
            # Fall through to generic summarization
            pass

    try:
        compact_result = _compact_for_composer(result)
        text = json.dumps(compact_result, indent=2, default=str)
        large_result_limits: Dict[str, int] = {
            "get_effective_routes": 12000,
            "get_performance_metrics": 12000,
            "container_app_list": 12000,
        }
        limit = large_result_limits.get(tool_name, 6000)
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
    include_step_table: bool = True,
) -> str:
    """Build a minimal HTML page when the LLM is unavailable."""
    import html as _html

    rows: List[str] = []
    container_app_html = ""
    arc_os_html = ""
    azure_os_html = ""

    def _extract_payload(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict):
            return None

        # Some wrappers nest the parsed payload one level down.
        for nested_key in ("result", "data"):
            nested = result.get(nested_key)
            if isinstance(nested, dict):
                if isinstance(nested.get("apps"), list):
                    return nested
                if isinstance(nested.get("parsed"), dict):
                    return nested.get("parsed")

        if isinstance(result.get("parsed"), dict):
            return result.get("parsed")

        content = result.get("content")
        if isinstance(content, list):
            for entry in content:
                candidate_text: Optional[str] = None
                if isinstance(entry, str):
                    candidate_text = entry
                elif isinstance(entry, dict):
                    text_value = entry.get("text")
                    if isinstance(text_value, str):
                        candidate_text = text_value
                else:
                    text_value = getattr(entry, "text", None)
                    if isinstance(text_value, str):
                        candidate_text = text_value

                if not candidate_text:
                    continue
                try:
                    parsed = json.loads(candidate_text)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    return parsed

        return result

    def _extract_summary_data(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(payload.get("os_breakdown"), list):
            return payload
        return None

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

        if sr.success and sr.tool_name == "container_app_list":
            payload = _extract_payload(sr.result)
            apps = payload.get("apps") if isinstance(payload, dict) else None
            if isinstance(apps, list) and apps:
                app_rows: List[str] = []
                for app in apps:
                    if not isinstance(app, dict):
                        continue
                    name = _html.escape(str(app.get("name", "")))
                    rg = _html.escape(str(app.get("resource_group", "")))
                    location = _html.escape(str(app.get("location", "")))
                    app_rows.append(
                        f"<tr><td>{name}</td><td>{rg}</td><td>{location}</td></tr>"
                    )

                if app_rows:
                    total_apps = payload.get("total_apps") if isinstance(payload, dict) else len(app_rows)
                    container_app_html = (
                        "<h3>Container Apps</h3>"
                        f"<p>Retrieved <strong>{_html.escape(str(total_apps))}</strong> container app(s).</p>"
                        "<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
                        "<thead><tr><th>Name</th><th>Resource Group</th><th>Location</th></tr></thead>"
                        f"<tbody>{''.join(app_rows)}</tbody>"
                        "</table>"
                    )

        if sr.success and sr.tool_name == "law_get_os_summary":
            payload = _extract_summary_data(_extract_payload(sr.result))
            os_summary = payload.get("os_summary") if isinstance(payload, dict) else None
            os_versions = payload.get("os_versions") if isinstance(payload, dict) else None
            total_computers = payload.get("total_computers") if isinstance(payload, dict) else None

            version_rows: List[str] = []
            if isinstance(os_versions, list):
                for item in os_versions:
                    if not isinstance(item, dict):
                        continue
                    name = _html.escape(str(item.get("os_type", "Unknown")))
                    version = _html.escape(str(item.get("version", "Unknown")))
                    count = _html.escape(str(item.get("count", 0)))
                    version_rows.append(
                        f"<tr><td>{name}</td><td>{version}</td><td>{count}</td></tr>"
                    )

            summary_rows: List[str] = []
            if isinstance(os_summary, dict):
                for k, v in sorted(os_summary.items(), key=lambda item: str(item[0]).lower()):
                    summary_rows.append(
                        f"<tr><td>{_html.escape(str(k))}</td><td>{_html.escape(str(v))}</td></tr>"
                    )

            details_html = ""
            if version_rows:
                details_html += (
                    "<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
                    "<thead><tr><th>OS</th><th>Version</th><th>Count</th></tr></thead>"
                    f"<tbody>{''.join(version_rows)}</tbody>"
                    "</table>"
                )
            elif summary_rows:
                details_html += (
                    "<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
                    "<thead><tr><th>OS</th><th>Count</th></tr></thead>"
                    f"<tbody>{''.join(summary_rows)}</tbody>"
                    "</table>"
                )

            if details_html:
                arc_os_html = (
                    "<h3>Arc-Enabled Servers OS Summary</h3>"
                    f"<p>Total Arc computers: <strong>{_html.escape(str(total_computers or 0))}</strong></p>"
                    f"{details_html}"
                )

        if sr.success and sr.tool_name == "azure_resource_get_os_summary":
            payload = _extract_summary_data(_extract_payload(sr.result))
            os_breakdown = payload.get("os_breakdown") if isinstance(payload, dict) else None
            total_vms = payload.get("total_virtual_machines") if isinstance(payload, dict) else None

            azure_rows: List[str] = []
            if isinstance(os_breakdown, list):
                for item in os_breakdown:
                    if not isinstance(item, dict):
                        continue
                    os_name = _html.escape(str(item.get("os", "Unknown")))
                    count = _html.escape(str(item.get("count", 0)))
                    azure_rows.append(f"<tr><td>{os_name}</td><td>{count}</td></tr>")

            if azure_rows:
                azure_os_html = (
                    "<h3>Azure Virtual Machines OS Summary (Resource Inventory)</h3>"
                    f"<p>Total Azure VMs: <strong>{_html.escape(str(total_vms or 0))}</strong></p>"
                    "<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
                    "<thead><tr><th>OS</th><th>Count</th></tr></thead>"
                    f"<tbody>{''.join(azure_rows)}</tbody>"
                    "</table>"
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

    step_table_html = (
        f"<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>"
        f"<thead><tr><th>Step</th><th>Tool</th><th>Status</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
    ) if include_step_table else ""

    status_html = (
        f"<p>{'All steps completed successfully.' if execution_result.all_succeeded and not blocked else 'Some steps require attention — see above.'}</p>"
    ) if include_step_table else ""

    return (
        f"<h3>Query Results</h3>"
        f"<p><em>Query: {_html.escape(query)}</em></p>"
        f"{arc_os_html}"
        f"{azure_os_html}"
        f"{container_app_html}"
        f"{step_table_html}"
        f"{confirmation_html}"
        f"{status_html}"
    )
