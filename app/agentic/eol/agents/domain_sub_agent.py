"""Base class for domain-specific sub-agents in the hybrid orchestrator.

Generalises the pattern established by MonitorAgent: a focused sub-agent that
owns a *subset* of MCP tools and runs its own ReAct loop with a domain-specific
system prompt.  The orchestrator replaces N domain tools with a single meta-tool
that delegates to the sub-agent.

Sub-classes only need to provide:
- ``_SYSTEM_PROMPT``: domain-specific instructions
- ``_MAX_ITERATIONS``: iteration budget (defaults to 15)
- ``_DOMAIN_NAME``: short label for logging (e.g., "sre", "monitor")
- ``_SUPPORTED_DOMAINS``: list of domain identifiers (defaults to [_DOMAIN_NAME])
- ``_CAPABILITIES``: list of capability descriptions (optional)

Everything else — the ReAct loop, LLM calls, tool invocation, SSE events,
timeout handling — is provided by this base class.

Usage::

    class SRESubAgent(DomainSubAgent):
        _DOMAIN_NAME = "sre"
        _MAX_ITERATIONS = 20
        _SYSTEM_PROMPT = "You are the SRE specialist…"
        _SUPPORTED_DOMAINS = ["sre", "incident_response", "monitoring"]
        _CAPABILITIES = [
            "Health checks and diagnostics",
            "Incident response workflows",
            "Performance monitoring"
        ]

    agent = SRESubAgent(
        tool_definitions=sre_tool_defs,
        tool_invoker=composite_client.call_tool,
        event_callback=push_event,
    )
    result = await agent.run("Check health of my container apps")
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from copy import deepcopy
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

try:
    from agents.orchestrator_models import Capability
except ModuleNotFoundError:
    try:
        from app.agentic.eol.agents.orchestrator_models import Capability
    except ModuleNotFoundError:
        # Fallback for environments without orchestrator_models
        from dataclasses import dataclass, field
        @dataclass
        class Capability:
            name: str
            description: str
            domains: List[str] = field(default_factory=list)
            tool_requirements: List[str] = field(default_factory=list)
            metadata: Dict[str, Any] = field(default_factory=dict)

try:
    from utils.logging_config import get_logger
except ModuleNotFoundError:
    import logging
    def get_logger(name: str, **kwargs: Any) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger(__name__, level=os.getenv("LOG_LEVEL", "DEBUG"))


class DomainSubAgent:
    """Base class for domain-focused sub-agents.

    Each sub-agent:
    - Sees only the tools from its domain (10-50 instead of 140+)
    - Has a concise, domain-specific system prompt (≤ 100 lines)
    - Runs its own ReAct loop with a conservative iteration limit
    - Emits SSE events through the orchestrator's callback
    - Is stateless per-invocation (no persistent conversation history)
    - Advertises its capabilities and supported domains for discovery
    """

    # ── Override in subclass ──────────────────────────────────────────
    _DOMAIN_NAME: str = "generic"
    _SYSTEM_PROMPT: str = "You are a helpful assistant with access to tools."
    _MAX_ITERATIONS: int = 15
    _TIMEOUT_SECONDS: float = 45.0
    _SUPPORTED_DOMAINS: List[str] = []  # Override with ["domain1", "domain2"]
    _CAPABILITIES: List[str] = []  # Override with ["capability1", "capability2"]

    def __init__(
        self,
        tool_definitions: List[Dict[str, Any]],
        tool_invoker: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        event_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        *,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """
        Args:
            tool_definitions: OpenAI function-calling defs for this domain only.
            tool_invoker: ``async (tool_name, arguments) → result_dict`` callback.
            event_callback: Optional SSE emitter ``async (event_type, content, **kw)``.
            conversation_context: Optional prior turns from orchestrator to include.
        """
        self._tool_definitions = tool_definitions
        self._invoke_tool = tool_invoker
        self._push_event = event_callback or self._noop_event
        self._conversation_context = conversation_context or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, user_message: str) -> Dict[str, Any]:
        """Process a request through the domain-specific ReAct loop.

        Returns:
            Dict with keys: success, response, tool_calls_made, iterations, duration_seconds
        """
        start = time.time()
        tool_calls_count = 0
        final_text = ""

        # Build initial messages
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._SYSTEM_PROMPT},
        ]

        # Optionally inject prior conversation context
        if self._conversation_context:
            for ctx in self._conversation_context[-3:]:  # Last 3 turns max
                messages.append(ctx)

        messages.append({"role": "user", "content": user_message})

        await self._push_event(
            "reasoning",
            f"[{self._DOMAIN_NAME}] Analysing request: {user_message[:200]}",
            domain=self._DOMAIN_NAME,
        )

        for iteration in range(1, self._MAX_ITERATIONS + 1):
            elapsed = time.time() - start
            if elapsed > self._TIMEOUT_SECONDS:
                logger.warning(
                    "⏱️ %s sub-agent timeout at %.1fs (iteration %d)",
                    self._DOMAIN_NAME, elapsed, iteration,
                )
                if not final_text:
                    final_text = (
                        f"<p>The {self._DOMAIN_NAME} agent timed out after {elapsed:.0f}s. "
                        "Please try a simpler query.</p>"
                    )
                break

            try:
                llm_result = await self._call_llm(messages)
            except Exception as exc:
                logger.exception("%s sub-agent LLM call failed: %s", self._DOMAIN_NAME, exc)
                return {
                    "success": False,
                    "response": f"LLM error in {self._DOMAIN_NAME} agent: {exc}",
                    "tool_calls_made": tool_calls_count,
                    "iterations": iteration,
                    "duration_seconds": time.time() - start,
                }

            assistant_msg = llm_result.get("message", {})
            tool_calls = llm_result.get("tool_calls", [])

            # Append assistant message to history
            messages.append(assistant_msg)

            if not tool_calls:
                # Final answer
                final_text = assistant_msg.get("content", "") or ""
                break

            # Execute every tool call
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    arguments = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {}

                # Pre-call hook (subclass can override)
                intercept = await self._pre_tool_call(tool_name, arguments)
                if intercept is not None:
                    # Subclass intercepted — use its result
                    result = intercept
                else:
                    try:
                        result = await self._invoke_tool(tool_name, arguments)
                    except Exception as exc:
                        logger.error(
                            "%s tool '%s' failed: %s", self._DOMAIN_NAME, tool_name, exc,
                        )
                        result = {"success": False, "error": str(exc)}

                tool_calls_count += 1

                result_str = json.dumps(result, default=str, ensure_ascii=False)[:8000]
                await self._push_event(
                    "observation",
                    f"[{self._DOMAIN_NAME}] {tool_name} → {len(result_str)} chars",
                    domain=self._DOMAIN_NAME,
                    tool_name=tool_name,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                })

        duration = time.time() - start
        logger.info(
            "✅ %s sub-agent finished: %d tool calls, %d iterations, %.1fs",
            self._DOMAIN_NAME, tool_calls_count, iteration, duration,
        )

        return {
            "success": bool(final_text),
            "response": final_text,
            "tool_calls_made": tool_calls_count,
            "iterations": iteration,
            "duration_seconds": duration,
        }

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    async def _pre_tool_call(
        self, tool_name: str, arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Hook called before each tool invocation.

        Return ``None`` to proceed normally, or a result dict to short-circuit
        the tool call (e.g., for validation or caching).
        """
        return None

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Send messages + domain tools to Azure OpenAI and return parsed result.

        Returns:
            Dict with 'message' (the raw assistant message dict) and 'tool_calls'.
        """
        from openai import AsyncAzureOpenAI

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        )

        client: Optional[AsyncAzureOpenAI] = None
        async_credential = None
        try:
            if api_key:
                client = AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )
            else:
                from utils.azure_client_manager import get_azure_sdk_manager
                async_credential = get_azure_sdk_manager().get_async_credential()
                token = await async_credential.get_token("https://cognitiveservices.azure.com/.default")
                client = AsyncAzureOpenAI(
                    api_key=token.token,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

            create_kwargs: Dict[str, Any] = {
                "model": deployment,
                "messages": messages,
            }
            deployment_lower = (deployment or "").lower()
            if deployment_lower.startswith("gpt-5"):
                # GPT-5 deployments reject `max_tokens` and custom temperature.
                create_kwargs["max_completion_tokens"] = 3000
            else:
                create_kwargs["temperature"] = 0.2
                create_kwargs["max_tokens"] = 3000

            # Build tool payload
            tools_payload = []
            for tool in self._tool_definitions:
                fn = tool.get("function", tool)
                if isinstance(fn, dict) and fn.get("name"):
                    tools_payload.append({"type": "function", "function": fn})
            if tools_payload:
                create_kwargs["tools"] = tools_payload

            response = await client.chat.completions.create(**create_kwargs)
            choice = response.choices[0]

            # Build raw assistant message dict (OpenAI format)
            msg: Dict[str, Any] = {"role": "assistant", "content": choice.message.content or ""}
            tcs: List[Dict[str, Any]] = []
            if choice.message.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]
                tcs = msg["tool_calls"]

            return {"message": msg, "tool_calls": tcs}

        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass
            if async_credential:
                try:
                    await async_credential.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _noop_event(*_args: Any, **_kwargs: Any) -> None:
        """No-op event callback when no SSE emitter is provided."""

    def describe(self) -> Dict[str, Any]:
        """Return metadata about this sub-agent for introspection."""
        return {
            "domain": self._DOMAIN_NAME,
            "system_prompt_length": len(self._SYSTEM_PROMPT),
            "tool_count": len(self._tool_definitions),
            "max_iterations": self._MAX_ITERATIONS,
            "timeout_seconds": self._TIMEOUT_SECONDS,
        }

    def get_supported_domains(self) -> List[str]:
        """Get list of domain identifiers this agent supports.

        Returns:
            List of domain names (e.g., ["sre", "incident_response", "monitoring"])

        Usage:
            This allows orchestrators to discover which domains an agent can handle,
            enabling dynamic routing decisions.

        Example:
            >>> agent = SRESubAgent(...)
            >>> agent.get_supported_domains()
            ['sre', 'incident_response', 'monitoring']
        """
        # If subclass defined supported domains, use those
        if self._SUPPORTED_DOMAINS:
            return self._SUPPORTED_DOMAINS.copy()

        # Otherwise, default to the primary domain name
        return [self._DOMAIN_NAME]

    def get_capabilities(self) -> List[Capability]:
        """Get list of capabilities this agent provides.

        Returns:
            List of Capability objects describing what this agent can do

        Usage:
            This allows orchestrators to discover agent capabilities at runtime,
            enabling capability-based routing and agent selection.

        Example:
            >>> agent = SRESubAgent(...)
            >>> capabilities = agent.get_capabilities()
            >>> for cap in capabilities:
            ...     print(f"{cap.name}: {cap.description}")
            Health Checks: Diagnose and monitor service health
            Incident Response: Handle production incidents
        """
        capabilities = []

        # If subclass defined capability descriptions, convert to Capability objects
        if self._CAPABILITIES:
            for cap_desc in self._CAPABILITIES:
                # Simple string capabilities get converted to structured format
                if isinstance(cap_desc, str):
                    capabilities.append(Capability(
                        name=cap_desc,
                        description=f"{self._DOMAIN_NAME} agent capability: {cap_desc}",
                        domains=self.get_supported_domains(),
                        tool_requirements=[],
                        metadata={"agent": self._DOMAIN_NAME}
                    ))
                elif isinstance(cap_desc, dict):
                    # Allow dict format for more detailed capability specs
                    capabilities.append(Capability(
                        name=cap_desc.get("name", "Unnamed capability"),
                        description=cap_desc.get("description", ""),
                        domains=cap_desc.get("domains", self.get_supported_domains()),
                        tool_requirements=cap_desc.get("tool_requirements", []),
                        metadata=cap_desc.get("metadata", {"agent": self._DOMAIN_NAME})
                    ))

        # If no explicit capabilities defined, create a default based on tools
        if not capabilities:
            tool_names = [t.get("function", {}).get("name", "") for t in self._tool_definitions]
            capabilities.append(Capability(
                name=f"{self._DOMAIN_NAME.title()} Operations",
                description=f"Domain-specific operations using {len(tool_names)} tools",
                domains=self.get_supported_domains(),
                tool_requirements=tool_names[:5],  # First 5 tools as sample
                metadata={
                    "agent": self._DOMAIN_NAME,
                    "tool_count": len(tool_names),
                    "auto_generated": True
                }
            ))

        return capabilities
