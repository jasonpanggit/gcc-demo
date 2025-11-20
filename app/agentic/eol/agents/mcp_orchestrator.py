#!/usr/bin/env python3
"""Microsoft Agent Framework powered orchestrator for Azure MCP Server tools."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

try:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.cache_stats_manager import cache_stats_manager
except ModuleNotFoundError:  # pragma: no cover - packaged runtime fallback
    from utils.logger import get_logger  # type: ignore[import-not-found]
    from utils.cache_stats_manager import cache_stats_manager  # type: ignore[import-not-found]

try:
    from app.agentic.eol.utils.azure_mcp_client import get_azure_mcp_client
    _AZURE_MCP_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.azure_mcp_client import get_azure_mcp_client  # type: ignore[import-not-found]
        _AZURE_MCP_AVAILABLE = True
    except ModuleNotFoundError:
        get_azure_mcp_client = None  # type: ignore[assignment]
        _AZURE_MCP_AVAILABLE = False

try:
    from app.agentic.eol.utils.azure_cli_executor_client import (  # type: ignore[import-not-found]
        AzureCliExecutorDisabledError,
        get_cli_executor_client,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.azure_cli_executor_client import (  # type: ignore[import-not-found]
            AzureCliExecutorDisabledError,
            get_cli_executor_client,
        )
    except ModuleNotFoundError:
        get_cli_executor_client = None  # type: ignore[assignment]

        class AzureCliExecutorDisabledError(RuntimeError):  # type: ignore[override]
            """Fallback disabled error when CLI executor helper is unavailable."""

_os_eol_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.os_eol_mcp_client import get_os_eol_mcp_client  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _os_eol_mcp_import_error = exc
    try:
        from utils.os_eol_mcp_client import get_os_eol_mcp_client  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _os_eol_mcp_import_error = fallback_exc
        get_os_eol_mcp_client = None  # type: ignore[assignment]

_inventory_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.inventory_mcp_client import get_inventory_mcp_client  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _inventory_mcp_import_error = exc
    try:
        from utils.inventory_mcp_client import get_inventory_mcp_client  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _inventory_mcp_import_error = fallback_exc
        get_inventory_mcp_client = None  # type: ignore[assignment]

try:
    from app.agentic.eol.utils.mcp_composite_client import CompositeMCPClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.mcp_composite_client import CompositeMCPClient  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        CompositeMCPClient = None  # type: ignore[assignment]


if TYPE_CHECKING:  # pragma: no cover - typing support only
    from agent_framework.azure import AzureOpenAIChatClient as AzureOpenAIChatClientType  # type: ignore[import-not-found]
    from azure.identity import DefaultAzureCredential as DefaultAzureCredentialType  # type: ignore[import-not-found]
else:  # pragma: no cover - runtime branch
    AzureOpenAIChatClientType = Any
    DefaultAzureCredentialType = Any

try:
    from agent_framework import (  # type: ignore[import-not-found]
        ChatMessage,
        ChatResponse,
        FunctionCallContent,
        FunctionResultContent,
        TextContent,
    )
    _AGENT_FRAMEWORK_AVAILABLE = True
except (ModuleNotFoundError, ImportError):  # pragma: no cover - fallback when preview package missing
    _AGENT_FRAMEWORK_AVAILABLE = False

    class TextContent:  # minimal fallback
        def __init__(self, text: Optional[str] = None, **_: Any) -> None:
            self.text = text or ""

    class FunctionCallContent:  # minimal fallback
        def __init__(self, *, call_id: Optional[str] = None, name: str = "", arguments: Any = None, **_: Any) -> None:
            self.call_id = call_id or f"call_{uuid.uuid4().hex[:8]}"
            self.name = name
            self.arguments = arguments or {}

    class FunctionResultContent:  # minimal fallback
        def __init__(self, *, call_id: str, result: Any = None, **_: Any) -> None:
            self.call_id = call_id
            self.result = result

    class ChatMessage:  # minimal fallback
        def __init__(
            self,
            *,
            role: str,
            text: Optional[str] = None,
            contents: Optional[Sequence[Any]] = None,
            **_: Any,
        ) -> None:
            self.role = role
            base_contents = list(contents or [])
            if text:
                base_contents.append(TextContent(text=text))
            self.contents = base_contents
            self.text = text or ""

    class ChatResponse:  # minimal fallback
        def __init__(self, messages: Optional[Sequence[ChatMessage]] = None, **_: Any) -> None:
            self.messages = list(messages or [])

try:
    from agent_framework.azure import AzureOpenAIChatClient  # type: ignore[import]
    _AGENT_FRAMEWORK_CHAT_AVAILABLE = True
except (ModuleNotFoundError, ImportError):  # pragma: no cover - preview package not installed
    AzureOpenAIChatClient = None  # type: ignore[assignment]
    _AGENT_FRAMEWORK_CHAT_AVAILABLE = False

try:
    from azure.identity import DefaultAzureCredential  # type: ignore[import]
    _DEFAULT_CREDENTIAL_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    DefaultAzureCredential = None  # type: ignore[assignment]
    _DEFAULT_CREDENTIAL_AVAILABLE = False

logger = get_logger(__name__, level=os.getenv("LOG_LEVEL", "DEBUG"))


class MCPOrchestratorAgent:
    """High-level Azure MCP orchestrator built on the Microsoft Agent Framework."""

    _SYSTEM_PROMPT = """You are the Azure modernization co-pilot for enterprise operations teams.
You can plan and execute multi-step investigations using Azure Model Context Protocol tools.
When tools are required, think through the plan, call the most relevant tools, and summarize
clear, actionable insights drawn from the observed results.

Formatting guidance:
- Return responses as HTML fragments suitable for direct rendering in the Azure MCP UI. Do not wrap content in Markdown fences or Markdown tables.
- Always include at least one HTML table in the final response. Use <table>, <thead>, and <tbody>, with concise column headers.
- When an Azure MCP tool returns structured data (arrays of subscriptions, resource groups, VMs, etc.), render it as a concise table with intuitive columns (Name, Id, Location, State, Tags, or other key fields).
- For unstructured or textual findings, construct a two-column summary table (for example Key and Details) that captures the salient insights instead of plain paragraphs.
- Paginate large result sets by showing only the first few rows in the table and append a short note indicating how many additional records are available.
- After the table(s), add a brief <p> summary highlighting the most important findings or recommended next steps."""

    def __init__(
        self,
        *,
        chat_client: Optional[AzureOpenAIChatClientType] = None,
        mcp_client: Optional[Any] = None,
        tool_definitions: Optional[Sequence[Dict[str, Any]]] = None,
        max_reasoning_iterations: Optional[int] = None,
        default_temperature: Optional[float] = None,
    ) -> None:
        self.session_id = self._new_session_id()
        self._chat_client: Optional[AzureOpenAIChatClientType] = chat_client
        self._default_credential: Optional[DefaultAzureCredentialType] = None
        self._mcp_client: Optional[Any] = mcp_client
        self._tool_definitions: List[Dict[str, Any]] = list(tool_definitions or [])
        self._message_log: List[ChatMessage] = []
        self._last_tool_failure: Optional[Dict[str, str]] = None
        self._last_tool_request: Optional[List[str]] = None
        self._last_tool_output: Optional[Dict[str, Any]] = None
        self._registered_client_labels: List[str] = []
        self._tool_source_map: Dict[str, str] = {}
        self._initialise_message_log()

        self.communication_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.communication_buffer: List[Dict[str, Any]] = []
        self.max_buffer_size = 100
        configured_iterations = (
            max_reasoning_iterations
            if max_reasoning_iterations is not None
            else int(os.getenv("MCP_AGENT_MAX_ITERATIONS", "4"))
        )
        self._max_reasoning_iterations = max(int(configured_iterations), 1)
        if default_temperature is not None:
            self._default_temperature = float(default_temperature)
        else:
            self._default_temperature = float(os.getenv("MCP_AGENT_TEMPERATURE", "0.2"))

    # ------------------------------------------------------------------
    # Public API consumed by FastAPI endpoints
    # ------------------------------------------------------------------
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """Process a conversational turn, invoking MCP tools when requested."""

        start_time = time.time()
        iteration = 0
        tool_calls_made = 0
        reasoning_trace: List[Dict[str, Any]] = []
        last_iteration_requested_tool = False
        final_text = ""
        error_detail = None
        success = True
        self._last_tool_failure = None
        self._last_tool_request = None
        self._last_tool_output = None

        await self._push_event("reasoning", "Analyzing request", iteration=iteration)

        if not await self._ensure_chat_client():
            logger.warning("Microsoft Agent Framework chat client is not available; returning fallback response")
            return self._build_failure_response(
                user_message=user_message,
                elapsed=time.time() - start_time,
                error="Microsoft Agent Framework preview package is not installed.",
            )

        mcp_ready = await self._ensure_mcp_client()
        if not mcp_ready:
            logger.warning("Azure MCP client unavailable; continuing without tool execution")

        user_chat = ChatMessage(role="user", text=user_message)
        self._message_log.append(user_chat)

        for iteration in range(1, self._max_reasoning_iterations + 1):
            try:
                response: ChatResponse = await self._chat_client.get_response(
                    self._message_log,
                    tools=self._tool_definitions if mcp_ready else None,
                    tool_choice="auto",
                    temperature=self._default_temperature,
                    max_tokens=1200,
                )
                logger.debug(
                    "Agent Framework returned %d message(s) for iteration %d",
                    len(response.messages),
                    iteration,
                )
                try:
                    for idx, raw_message in enumerate(response.messages, start=1):
                        logger.info(
                            "🗂️ AF message %d/%d: %s",
                            idx,
                            len(response.messages),
                            self._summarize_message(raw_message),
                        )
                except Exception:  # pragma: no cover - defensive logging
                    logger.debug("Unable to log Agent Framework messages", exc_info=True)
            except Exception as exc:  # pragma: no cover - network/service dependency
                logger.exception("Azure OpenAI request failed: %s", exc)
                success = False
                error_detail = str(exc)
                final_text = (
                    "I could not reach Azure OpenAI to process that request. "
                    "Please verify your credentials and try again."
                )
                break

            assistant_message: Optional[ChatMessage] = None
            tool_calls: List[FunctionCallContent] = []
            for candidate in response.messages:
                if self._get_message_role(candidate) != "assistant":
                    continue
                assistant_message = candidate
                candidate_calls = self._extract_tool_calls(candidate)
                if candidate_calls:
                    tool_calls = candidate_calls
                    break
            if not assistant_message:
                if self._last_tool_failure:
                    logger.error(
                        "Agent Framework response contained no assistant message after tool failure",
                        extra={"tool_failure": self._last_tool_failure},
                    )
                else:
                    logger.error(
                        "Agent Framework response contained no assistant message; raw messages: %s",
                        [self._summarize_message(msg) for msg in response.messages],
                    )
                    failure_info = self._extract_failure_from_messages(response)
                    if failure_info and not self._last_tool_failure:
                        self._last_tool_failure = failure_info
                        logger.warning(
                            "Inferred tool failure from response: %s",
                            failure_info,
                        )
                success = False
                failure_info = self._last_tool_failure or {}
                error_detail = failure_info.get("error") or "Azure OpenAI returned an empty response."
                if failure_info:
                    tool_name = failure_info.get("tool") or "unknown tool"
                    final_text = (
                        "I could not complete the request because the tool "
                        f"`{tool_name}` returned an error: {error_detail}. "
                        "Please review the tool configuration or try again."
                    )
                else:
                    final_text = (
                        "I was unable to generate a response for that request. "
                        "Please retry in a moment."
                    )
                break

            self._message_log.append(assistant_message)

            try:
                contents_preview = []
                for idx, content in enumerate(getattr(assistant_message, "contents", []) or []):
                    preview = {
                        "index": idx,
                        "type": type(content).__name__,
                        "attrs": {
                            "name": getattr(content, "name", None),
                            "call_id": getattr(content, "call_id", None),
                            "arguments": getattr(content, "arguments", None),
                            "text": getattr(content, "text", None),
                            "type_attr": getattr(content, "type", None),
                        },
                    }
                    contents_preview.append(preview)
                logger.info(
                    "🧩 Assistant message summary: %s | contents=%s",
                    self._summarize_message(assistant_message),
                    contents_preview,
                )
                tool_calls_attr = getattr(assistant_message, "tool_calls", None)
                if tool_calls_attr:
                    logger.info(
                        "🧩 assistant_message.tool_calls detected: %s",
                        tool_calls_attr,
                    )
            except Exception:  # pragma: no cover - defensive logging
                logger.debug("Unable to summarize assistant message", exc_info=True)

            text_fragments = self._collect_text_fragments(assistant_message)
            if not tool_calls:
                tool_calls = self._extract_tool_calls(assistant_message)
            last_iteration_requested_tool = bool(tool_calls)
            if tool_calls:
                logger.info(
                    "🛎️ Agent Framework requested %d tool(s) this iteration: %s",
                    len(tool_calls),
                    ", ".join(call.name or "<unnamed>" for call in tool_calls),
                )
            else:
                logger.debug("No tool calls extracted for iteration %d", iteration)
            if tool_calls:
                self._last_tool_request = [call.name or "unknown_tool" for call in tool_calls]
                logger.info(
                    "Iteration %d requested %d tool call(s): %s",
                    iteration,
                    len(tool_calls),
                    ", ".join(self._last_tool_request),
                )

            reasoning_trace.append(
                {
                    "type": "reasoning",
                    "iteration": iteration,
                    "tool_requests": [call.name for call in tool_calls],
                    "summary": " ".join(text_fragments)[:400],
                }
            )

            if not tool_calls or not mcp_ready:
                final_text = "\n".join(text_fragments).strip()
                await self._push_event(
                    "synthesis",
                    final_text or "Response ready",
                    iteration=iteration,
                )
                break

            await self._push_event(
                "action",
                f"Invoking {len(tool_calls)} Azure MCP tool(s)",
                iteration=iteration,
                tool_names=[call.name for call in tool_calls],
            )

            logger.info(
                "🚀 Iteration %d invoking Azure MCP tools: %s",
                iteration,
                ", ".join(self._last_tool_request or []),
            )

            for call in tool_calls:
                tool_calls_made += 1
                arguments = self._parse_call_arguments(call)
                tool_name = call.name or "unknown_tool"
                logger.debug(
                    "Invoking MCP tool '%s' with arguments: %s",
                    tool_name,
                    json.dumps(arguments, ensure_ascii=False)[:500],
                )
                try:
                    serialized_args = json.dumps(arguments, ensure_ascii=False)[:500]
                except (TypeError, ValueError):  # pragma: no cover - defensive guard
                    serialized_args = str(arguments)
                logger.info(
                    "🧰 Tool request %d: %s args=%s",
                    tool_calls_made,
                    tool_name,
                    serialized_args,
                )
                tool_result = await self._invoke_mcp_tool(tool_name, arguments)
                if isinstance(tool_result, dict):
                    self._last_tool_output = {
                        "tool": tool_name,
                        "result": tool_result,
                    }
                    try:
                        logger.info(
                            "MCP tool '%s' response: %s",
                            tool_name,
                            json.dumps(tool_result, ensure_ascii=False)[:2000],
                        )
                    except Exception:  # pragma: no cover - logging safety
                        logger.info("MCP tool '%s' response: %s", tool_name, tool_result)
                observation_success = bool(tool_result.get("success")) if isinstance(tool_result, dict) else False

                if isinstance(tool_result, dict):
                    if observation_success:
                        self._last_tool_failure = None
                        logger.debug("Tool '%s' succeeded", tool_name)
                    else:
                        error_text = str(tool_result.get("error") or "Unknown error")
                        self._last_tool_failure = {
                            "tool": tool_name,
                            "error": error_text,
                        }
                        logger.warning("MCP tool '%s' failed: %s", tool_name, error_text)
                        await self._push_event(
                            "error",
                            f"Tool '{tool_name}' failed",
                            iteration=iteration,
                            tool_name=tool_name,
                            error=error_text,
                        )
                else:
                    if observation_success:
                        self._last_tool_failure = None
                        logger.debug("Tool '%s' succeeded", tool_name)
                    else:
                        error_text = str(tool_result)
                        self._last_tool_failure = {"tool": tool_name, "error": error_text}
                        logger.warning("MCP tool '%s' failed: %s", tool_name, error_text)
                        await self._push_event(
                            "error",
                            f"Tool '{tool_name}' failed",
                            iteration=iteration,
                            tool_name=tool_name,
                            error=error_text,
                        )

                reasoning_trace.append(
                    {
                        "type": "observation",
                        "iteration": iteration,
                        "tool": tool_name,
                        "success": observation_success,
                    }
                )

                await self._push_event(
                    "observation",
                    "Tool execution completed",
                    iteration=iteration,
                    tool_name=tool_name,
                    tool_result=tool_result,
                    is_error=not observation_success,
                )

                result_message = self._create_tool_result_message(call.call_id, tool_result)
                self._message_log.append(result_message)

        duration = time.time() - start_time

        if not final_text and success:
            success = False
            final_text = (
                "I reached the configured reasoning limit before producing a complete answer. "
                "Try refining the request or enabling more iterations."
            )

        if error_detail:
            await self._push_event("error", error_detail)

        self._record_cache_stats(duration, success)

        metadata = {
            "session_id": self.session_id,
            "duration_seconds": duration,
            "tool_calls_made": tool_calls_made,
            "available_tools": len(self._tool_definitions),
            "message_count": max(len(self._message_log) - 1, 0),
            "reasoning_iterations": iteration,
            "max_iterations_reached": last_iteration_requested_tool and success is False,
            "agent_framework_enabled": _AGENT_FRAMEWORK_AVAILABLE and _AGENT_FRAMEWORK_CHAT_AVAILABLE,
            "reasoning_trace": reasoning_trace,
            "error": error_detail,
            "last_tool_failure": self._last_tool_failure,
            "last_tool_request": self._last_tool_request,
            "last_tool_output": self._last_tool_output,
        }

        try:
            session_log_snapshot = {
                "session_id": metadata["session_id"],
                "tool_calls_made": metadata["tool_calls_made"],
                "iterations": metadata["reasoning_iterations"],
                "last_tool_request": metadata.get("last_tool_request"),
                "last_tool_failure": metadata.get("last_tool_failure"),
            }
            logger.info("📊 MCP session summary: %s", json.dumps(session_log_snapshot, ensure_ascii=False))
        except Exception:  # pragma: no cover - defensive logging
            logger.info("📊 MCP session summary: session_id=%s tool_calls=%s", self.session_id, tool_calls_made)

        if not success:
            logger.error(
                "MCP orchestrator request failed (session=%s, iterations=%s, tool_request=%s, tool_failure=%s, error=%s, tool_output=%s)",
                self.session_id,
                iteration,
                self._last_tool_request,
                self._last_tool_failure,
                error_detail,
                self._last_tool_output,
            )
        elif self._last_tool_output:
            try:
                logger.info(
                    "MCP orchestrator tool output (session=%s): %s",
                    self.session_id,
                    json.dumps(self._last_tool_output, ensure_ascii=False)[:2000],
                )
            except Exception:  # pragma: no cover - logging safety
                logger.info(
                    "MCP orchestrator tool output (session=%s): %s",
                    self.session_id,
                    self._last_tool_output,
                )

        return {
            "success": success,
            "response": final_text,
            "conversation_history": self.get_conversation_history(),
            "metadata": metadata,
        }

    async def stream_message(self, user_message: str):
        """Stream a response for compatibility with SSE consumers."""
        result = await self.process_message(user_message)
        if not result.get("success"):
            yield {
                "type": "error",
                "error": result.get("metadata", {}).get("error") or "Processing error",
                "timestamp": datetime.utcnow().isoformat(),
            }
            return

        yield {
            "type": "message",
            "content": result["response"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        yield {
            "type": "complete",
            "session_id": result.get("metadata", {}).get("session_id", self.session_id),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def explain_reasoning(self, user_message: str) -> Dict[str, Any]:
        """Run the request and attach a human-readable reasoning summary."""
        result = await self.process_message(user_message)
        trace = result.get("metadata", {}).get("reasoning_trace", [])
        if trace:
            explanation_lines = ["🧠 Agentic reasoning summary:"]
            for step in trace:
                step_type = step.get("type")
                iteration = step.get("iteration")
                if step_type == "reasoning":
                    tools = step.get("tool_requests") or []
                    tool_text = f" → tools: {', '.join(tools)}" if tools else ""
                    explanation_lines.append(f"  • Iteration {iteration}: reasoning{tool_text}")
                elif step_type == "observation":
                    status = "success" if step.get("success") else "error"
                    explanation_lines.append(
                        f"  • Iteration {iteration}: observation from {step.get('tool')} ({status})"
                    )
                elif step_type == "synthesis":
                    explanation_lines.append(f"  • Iteration {iteration}: synthesis")
            result["reasoning_explanation"] = "\n".join(explanation_lines)
        return result

    async def create_plan(self, user_message: str) -> Dict[str, Any]:
        """Generate a step-by-step execution plan without performing tool calls."""
        system_prompt = (
            "You are an Azure planning specialist. Produce a structured JSON plan with steps, tools, "
            "parameters, expected outcomes, risks, and fallback strategies."
        )
        success, response_text = await self._run_single_prompt(system_prompt, user_message, temperature=0.25)
        if not success:
            return {"success": False, "error": response_text}

        try:
            plan = json.loads(response_text)
        except json.JSONDecodeError:
            plan = {"plan_summary": "Execution plan", "plan_text": response_text}

        plan["note"] = "This plan is advisory only. Use process_message() to execute actions."
        return {"success": True, "plan": plan, "session_id": self.session_id}

    async def analyze_task_complexity(self, user_message: str) -> Dict[str, Any]:
        """Assess the complexity of a user task and recommend an approach."""
        system_prompt = (
            "You are an Azure task analyst. Return JSON with fields: complexity (simple|moderate|complex|very_complex), "
            "estimated_tool_calls, estimated_time_seconds, required_services, challenges, recommended_approach, "
            "success_probability (0-1), reasoning."
        )
        success, response_text = await self._run_single_prompt(system_prompt, user_message, temperature=0.2)
        if not success:
            return {"success": False, "error": response_text}

        try:
            analysis = json.loads(response_text)
        except json.JSONDecodeError:
            analysis = {"complexity": "unknown", "analysis_text": response_text}

        return {"success": True, "analysis": analysis, "session_id": self.session_id}

    async def list_available_tools(self) -> Dict[str, Any]:
        """Return the cached Azure MCP tool catalog."""
        if not await self._ensure_mcp_client():
            return {"success": False, "error": "Azure MCP client unavailable", "tools": [], "count": 0}

        categorized = self._categorize_tools()
        return {
            "success": True,
            "tools": self._tool_definitions,
            "count": len(self._tool_definitions),
            "categories": categorized,
            "session_id": self.session_id,
        }

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Expose the conversation log in a serializable format (excluding system message)."""
        history: List[Dict[str, Any]] = []
        for message in self._message_log:
            role = self._get_message_role(message) or "assistant"
            if role == "system":
                continue
            history.append(
                {
                    "role": role,
                    "content": self._message_to_text(message),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        return history

    def clear_conversation(self) -> None:
        """Reset the orchestrator session and clear cached events."""
        self.session_id = self._new_session_id()
        self._initialise_message_log()
        self.communication_buffer.clear()
        try:
            while True:
                self.communication_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        logger.info("🔄 MCP orchestrator conversation cleared (session=%s)", self.session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _ensure_chat_client(self) -> bool:
        if self._chat_client:
            return True
        if not (_AGENT_FRAMEWORK_AVAILABLE and _AGENT_FRAMEWORK_CHAT_AVAILABLE):
            return False

        deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

        client_kwargs: Dict[str, Any] = {}
        if deployment:
            client_kwargs["deployment_name"] = deployment
        if endpoint:
            client_kwargs["endpoint"] = endpoint
        if api_version:
            client_kwargs["api_version"] = api_version
        if api_key:
            client_kwargs["api_key"] = api_key
        elif _DEFAULT_CREDENTIAL_AVAILABLE and DefaultAzureCredential is not None:
            try:
                self._default_credential = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                client_kwargs["credential"] = self._default_credential
            except Exception as exc:  # pragma: no cover - credential edge cases
                logger.warning("Unable to create DefaultAzureCredential: %s", exc)

        try:
            self._chat_client = AzureOpenAIChatClient(**client_kwargs)
            try:
                config = getattr(self._chat_client, "function_invocation_config", None)
                if config is not None and getattr(config, "enabled", True):
                    config.enabled = False
                    logger.debug("Disabled built-in function auto-invocation for Azure OpenAI client")
            except Exception:  # pragma: no cover - defensive guard around preview SDK internals
                logger.debug("Unable to adjust function invocation config", exc_info=True)
            logger.info(
                "✅ MCP orchestrator chat client ready (deployment=%s, endpoint_configured=%s)",
                deployment,
                bool(endpoint),
            )
            return True
        except Exception as exc:  # pragma: no cover - network/service dependency
            logger.error("Failed to initialise AzureOpenAIChatClient: %s", exc)
            self._chat_client = None
            return False

    async def _ensure_mcp_client(self) -> bool:
        if self._mcp_client:
            if not self._tool_definitions:
                await self._refresh_tool_definitions()
            else:
                self._update_tool_metadata()
            return True
        client_entries: List[Tuple[str, Any]] = []

        if _AZURE_MCP_AVAILABLE and get_azure_mcp_client is not None:
            try:
                azure_client = await get_azure_mcp_client()
            except Exception as exc:  # pragma: no cover - service dependency
                logger.warning("Azure MCP client unavailable: %s", exc)
            else:
                client_entries.append(("azure", azure_client))

        if get_cli_executor_client is not None:
            try:
                cli_client = await get_cli_executor_client()
            except AzureCliExecutorDisabledError:
                logger.info("Azure CLI MCP server disabled via configuration; skipping registration")
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("Azure CLI MCP server unavailable: %s", exc)
            else:
                client_entries.append(("azure_cli", cli_client))

        if get_os_eol_mcp_client is not None:
            try:
                os_eol_client = await get_os_eol_mcp_client()
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("OS EOL MCP server unavailable: %s", exc)
            else:
                logger.debug("OS EOL MCP client initialised; catalog size hint=%s", len(getattr(os_eol_client, "available_tools", []) or []))
                client_entries.append(("os_eol", os_eol_client))
        else:
            logger.debug(
                "OS EOL MCP client import resolved to None; skipping registration (error=%s)",
                _os_eol_mcp_import_error,
            )

        if get_inventory_mcp_client is not None:
            try:
                inventory_client = await get_inventory_mcp_client()
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("Inventory MCP server unavailable: %s", exc)
            else:
                logger.debug(
                    "Inventory MCP client initialised; catalog size hint=%s",
                    len(getattr(inventory_client, "available_tools", []) or []),
                )
                client_entries.append(("inventory", inventory_client))
        else:
            logger.debug(
                "Inventory MCP client import resolved to None; skipping registration (error=%s)",
                _inventory_mcp_import_error,
            )

        if not client_entries or CompositeMCPClient is None:
            logger.error("No MCP clients available; tool execution disabled")
            self._mcp_client = None
            self._registered_client_labels = []
            self._tool_source_map = {}
            return False

        self._mcp_client = CompositeMCPClient(client_entries)
        self._registered_client_labels = [label for label, _ in client_entries]
        logger.info(
            "MCP clients registered: %s",
            ", ".join(label for label, _ in client_entries),
        )
        await self._refresh_tool_definitions()
        if self._tool_definitions:
            logger.info("✅ Loaded %d MCP tools", len(self._tool_definitions))
            return True

        logger.warning("MCP clients initialised but no tools were registered")
        return False

    async def _invoke_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self._mcp_client:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": "Azure MCP client unavailable",
            }
        try:
            return await self._mcp_client.call_tool(tool_name, arguments)
        except Exception as exc:  # pragma: no cover - tool execution edge cases
            logger.exception("Azure MCP tool '%s' execution failed: %s", tool_name, exc)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
            }

    async def aclose(self) -> None:
        """Release network clients and credentials."""

        await self._maybe_aclose(self._chat_client)
        await self._maybe_aclose(self._mcp_client)
        await self._maybe_aclose(self._default_credential)
        self._chat_client = None
        self._mcp_client = None
        self._default_credential = None

    async def _refresh_tool_definitions(self) -> None:
        if not self._mcp_client:
            self._tool_definitions = []
            self._tool_source_map = {}
            if not self._registered_client_labels:
                self._registered_client_labels = []
            return

        catalog_accessor = getattr(self._mcp_client, "get_available_tools", None)
        if not callable(catalog_accessor):
            self._tool_definitions = []
            self._tool_source_map = {}
            return

        try:
            tools = catalog_accessor()
            if asyncio.iscoroutine(tools):
                tools = await tools
            if isinstance(tools, list):
                self._tool_definitions = tools
            elif isinstance(tools, tuple):
                self._tool_definitions = list(tools)
            else:
                self._tool_definitions = []
        except Exception as exc:  # pragma: no cover - defensive refresh
            logger.debug("Unable to refresh MCP tool catalog: %s", exc)
            self._tool_definitions = []
        finally:
            self._update_tool_metadata()

    def _update_tool_metadata(self) -> None:
        if not self._mcp_client:
            self._tool_source_map = {}
            if not self._registered_client_labels:
                self._registered_client_labels = []
            return

        source_lookup = getattr(self._mcp_client, "get_tool_sources", None)
        if callable(source_lookup):
            try:
                self._tool_source_map = source_lookup() or {}
            except Exception:  # pragma: no cover - defensive guard
                logger.debug("Failed to obtain MCP tool source map", exc_info=True)
                self._tool_source_map = {}
        else:
            self._tool_source_map = {}

        client_lookup = getattr(self._mcp_client, "get_client_labels", None)
        if callable(client_lookup):
            try:
                labels = client_lookup() or []
                self._registered_client_labels = list(dict.fromkeys(labels))
            except Exception:  # pragma: no cover - defensive guard
                logger.debug("Failed to obtain MCP client labels", exc_info=True)
        elif not self._registered_client_labels:
            self._registered_client_labels = []

    async def ensure_mcp_ready(self) -> bool:
        return await self._ensure_mcp_client()

    async def get_tool_catalog(self) -> List[Dict[str, Any]]:
        await self._ensure_mcp_client()
        return deepcopy(self._tool_definitions)

    def get_registered_clients(self) -> List[str]:
        return list(dict.fromkeys(self._registered_client_labels))

    def get_tool_source_map(self) -> Dict[str, str]:
        return dict(self._tool_source_map)

    def summarize_tool_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for label in self._registered_client_labels:
            counts.setdefault(label, 0)
        for label in self._tool_source_map.values():
            counts[label] = counts.get(label, 0) + 1
        return counts

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not await self._ensure_mcp_client():
            return {
                "success": False,
                "tool_name": tool_name,
                "error": "MCP client unavailable",
            }
        return await self._invoke_mcp_tool(tool_name, arguments)

    async def _maybe_aclose(self, resource: Any) -> None:
        if not resource:
            return

        for method_name, extra_args in (
            ("aclose", ()),
            ("close", ()),
            ("__aexit__", (None, None, None)),
        ):
            closer = getattr(resource, method_name, None)
            if not callable(closer):
                continue

            try:
                result = closer(*extra_args)  # type: ignore[arg-type]
                if asyncio.iscoroutine(result):
                    await result
            except TypeError:
                continue
            except Exception as exc:  # pragma: no cover - cleanup best effort
                logger.debug("Resource close failed via %s: %s", method_name, exc)
            break

    async def _run_single_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> Tuple[bool, str]:
        if not await self._ensure_chat_client():
            return False, "Microsoft Agent Framework chat client unavailable."
        try:
            response: ChatResponse = await self._chat_client.get_response(
                [
                    ChatMessage(role="system", text=system_prompt),
                    ChatMessage(role="user", text=user_prompt),
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # pragma: no cover - network/service dependency
            logger.error("Prompt execution failed: %s", exc)
            return False, str(exc)

        assistant = self._select_assistant_message(response)
        if not assistant:
            return False, "The model returned an empty response."
        return True, self._message_to_text(assistant)

    def _select_assistant_message(self, response: ChatResponse) -> Optional[ChatMessage]:
        for message in reversed(response.messages):
            if self._get_message_role(message) == "assistant":
                return message
        return None

    def _collect_text_fragments(self, message: ChatMessage) -> List[str]:
        fragments: List[str] = []
        for content in getattr(message, "contents", []) or []:
            text_value = getattr(content, "text", None)
            if text_value:
                fragments.append(str(text_value))
        if getattr(message, "text", None):
            fragments.append(str(message.text))
        return [fragment for fragment in fragments if fragment]

    def _get_message_role(self, message: ChatMessage) -> str:
        role = getattr(message, "role", "")
        if hasattr(role, "value"):
            try:
                return str(role.value)
            except Exception:  # pragma: no cover - defensive guard
                return str(role)
        return str(role)

    def _extract_failure_from_messages(self, response: ChatResponse) -> Optional[Dict[str, str]]:
        for message in response.messages:
            if self._get_message_role(message) != "tool":
                continue
            for content in getattr(message, "contents", []) or []:
                if isinstance(content, FunctionResultContent):
                    result = getattr(content, "result", None)
                    if isinstance(result, dict) and not bool(result.get("success")):
                        tool_name = str(
                            result.get("tool_name")
                            or result.get("tool")
                            or result.get("name")
                            or getattr(content, "call_id", "unknown_tool")
                        )
                        error_text = str(result.get("error") or "Unknown error")
                        return {"tool": tool_name, "error": error_text}
        return None

    def _summarize_message(self, message: ChatMessage) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "role": self._get_message_role(message) or "unknown",
            "text": (getattr(message, "text", "") or "")[:200],
            "content_types": [type(content).__name__ for content in getattr(message, "contents", []) or []],
        }
        result_previews: List[str] = []
        for content in getattr(message, "contents", []) or []:
            if isinstance(content, FunctionResultContent):
                result = getattr(content, "result", None)
                if result is not None:
                    try:
                        serialized = json.dumps(result, ensure_ascii=False)[:200]
                    except (TypeError, ValueError):  # pragma: no cover - defensive
                        serialized = str(result)[:200]
                    result_previews.append(serialized)
        if result_previews:
            summary["result_preview"] = result_previews
        return summary

    def _extract_tool_calls(self, message: ChatMessage) -> List[FunctionCallContent]:
        tool_calls: List[FunctionCallContent] = []
        contents = getattr(message, "contents", []) or []
        for idx, content in enumerate(contents):
            if isinstance(content, FunctionCallContent):
                tool_calls.append(content)
                continue
            # Support newer ChatMessage format where function calls are embedded as dicts
            if isinstance(content, dict):
                name = content.get("name") or content.get("function", {}).get("name")
                arguments = content.get("arguments") or content.get("function", {}).get("arguments")
                call_id = (
                    content.get("call_id")
                    or content.get("id")
                    or (content.get("function", {}) or {}).get("call_id")
                    or f"call_{uuid.uuid4().hex[:8]}"
                )
                tool_calls.append(
                    FunctionCallContent(
                        call_id=call_id,
                        name=name or "",
                        arguments=arguments,
                    )
                )

        attr_calls = getattr(message, "tool_calls", None)
        if attr_calls:
            for call in attr_calls:
                if isinstance(call, FunctionCallContent):
                    tool_calls.append(call)
                    continue
                if isinstance(call, dict):
                    call_id = call.get("call_id") or call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    tool_calls.append(
                        FunctionCallContent(
                            call_id=call_id,
                            name=str(call.get("name") or ""),
                            arguments=call.get("arguments"),
                        )
                    )
        return tool_calls

    def _parse_call_arguments(self, call: FunctionCallContent) -> Dict[str, Any]:
        arguments = getattr(call, "arguments", {})
        if isinstance(arguments, dict):
            return dict(arguments)
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except json.JSONDecodeError:
                logger.debug("Unable to parse JSON arguments for tool %s", call.name)
        return {}

    def _create_tool_result_message(self, call_id: str, result: Dict[str, Any]) -> ChatMessage:
        return ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id=call_id, result=result)],
        )

    def _message_to_text(self, message: ChatMessage) -> str:
        fragments: List[str] = []
        for content in getattr(message, "contents", []) or []:
            if hasattr(content, "text") and getattr(content, "text"):
                fragments.append(str(content.text))
            elif hasattr(content, "result") and getattr(content, "result") is not None:
                fragments.append(json.dumps(content.result, ensure_ascii=False, indent=2))
        if getattr(message, "text", None):
            fragments.append(str(message.text))
        return "\n".join(fragments).strip()

    async def _push_event(self, event_type: str, content: str, **metadata: Any) -> None:
        event = {
            "type": event_type,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        event.update({key: value for key, value in metadata.items() if value is not None})
        self.communication_buffer.append(event)
        if len(self.communication_buffer) > self.max_buffer_size:
            self.communication_buffer.pop(0)
        try:
            await self.communication_queue.put(event)
        except Exception as exc:  # pragma: no cover - queue closed
            logger.debug("Unable to enqueue communication event: %s", exc)

    def _record_cache_stats(self, duration: float, success: bool) -> None:
        try:
            cache_stats_manager.record_agent_request(
                agent_name="mcp_orchestrator",
                response_time_ms=duration * 1000,
                was_cache_hit=False,
                had_error=not success,
                software_name="azure_mcp_orchestrator",
                version="maf_preview",
                url="/api/azure-mcp/chat",
            )
        except Exception as exc:  # pragma: no cover - telemetry best effort
            logger.debug("Failed to record cache stats: %s", exc)

    def _categorize_tools(self) -> Dict[str, List[str]]:
        categories = {
            "Resource Management": [],
            "Storage": [],
            "Compute": [],
            "Databases": [],
            "Networking": [],
            "Security": [],
            "Monitoring": [],
            "AI/ML": [],
            "DevOps": [],
            "Other": [],
        }

        for tool in self._tool_definitions:
            function = tool.get("function", {}) if isinstance(tool, dict) else {}
            name = str(function.get("name", "")).lower()
            target_bucket = "Other"
            if any(keyword in name for keyword in ("group", "subscription", "resource")):
                target_bucket = "Resource Management"
            elif any(keyword in name for keyword in ("storage", "blob", "table", "queue")):
                target_bucket = "Storage"
            elif any(keyword in name for keyword in ("vm", "compute", "app", "function", "aks", "container")):
                target_bucket = "Compute"
            elif any(keyword in name for keyword in ("sql", "cosmos", "mysql", "postgres", "redis", "database")):
                target_bucket = "Databases"
            elif any(keyword in name for keyword in ("network", "vnet", "subnet", "eventhub", "servicebus")):
                target_bucket = "Networking"
            elif any(keyword in name for keyword in ("keyvault", "security", "rbac", "confidential")):
                target_bucket = "Security"
            elif any(keyword in name for keyword in ("monitor", "insight", "log", "metric", "alert")):
                target_bucket = "Monitoring"
            elif any(keyword in name for keyword in ("ai", "cognitive", "openai", "search", "speech", "foundry")):
                target_bucket = "AI/ML"
            elif any(keyword in name for keyword in ("deploy", "bicep", "terraform", "cli", "devops")):
                target_bucket = "DevOps"
            categories[target_bucket].append(name)

        return {key: value for key, value in categories.items() if value}

    def _initialise_message_log(self) -> None:
        self._message_log = [ChatMessage(role="system", text=self._SYSTEM_PROMPT)]

    def _new_session_id(self) -> str:
        return f"maf-mcp-{uuid.uuid4()}"

    def _build_failure_response(self, user_message: str, elapsed: float, error: str) -> Dict[str, Any]:
        fallback = (
            "The MCP orchestration service is not available right now. "
            "Install the Microsoft Agent Framework preview packages and retry."
        )
        metadata = {
            "session_id": self.session_id,
            "duration_seconds": elapsed,
            "tool_calls_made": 0,
            "available_tools": len(self._tool_definitions),
            "message_count": max(len(self._message_log) - 1, 0),
            "reasoning_iterations": 0,
            "max_iterations_reached": False,
            "agent_framework_enabled": False,
            "reasoning_trace": [],
            "error": error,
        }
        history = self.get_conversation_history()
        history.append(
            {
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        cache_stats_manager.record_agent_request(
            agent_name="mcp_orchestrator",
            response_time_ms=elapsed * 1000,
            was_cache_hit=False,
            had_error=True,
            software_name="azure_mcp_orchestrator",
            version="maf_preview",
            url="/api/azure-mcp/chat",
        )
        return {"success": False, "response": fallback, "conversation_history": history, "metadata": metadata}


_mcp_orchestrator_instance: Optional[MCPOrchestratorAgent] = None


async def get_mcp_orchestrator() -> MCPOrchestratorAgent:
    """Factory that returns a singleton MCP orchestrator instance."""
    global _mcp_orchestrator_instance
    if _mcp_orchestrator_instance is None:
        _mcp_orchestrator_instance = MCPOrchestratorAgent()
    return _mcp_orchestrator_instance
