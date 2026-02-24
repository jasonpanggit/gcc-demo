"""SRE Orchestrator Agent - Agent-first architecture with MCP fallback.

Routes all SRE requests through the Azure AI SRE Agent (gccsreagent) for
intelligent reasoning and tool selection, falling back to direct MCP execution
when the agent is unavailable.

Architecture:
    User Query → SREOrchestratorAgent.handle_request()
                    ├─→ AzureAISREAgent (PRIMARY BRAIN)
                    │   ├─ Maintains conversation thread per workflow
                    │   ├─ Reasons about user intent
                    │   ├─ Selects appropriate tools
                    │   └─ Synthesizes final response
                    │
                    └─→ SRE MCP Server (EXECUTION LAYER / FALLBACK)
                        ├─ Resource health checks
                        ├─ Incident response
                        ├─ Performance analysis
                        ├─ Cost optimization
                        ├─ Security & compliance
                        └─ RCA, anomaly detection, remediation
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from app.agentic.eol.agents.azure_ai_sre_agent import (
        AzureAISREAgent,
        AgentPerformanceConfig,
    )
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.agent_context_store import get_context_store
    from app.agentic.eol.utils.agent_message_bus import get_message_bus
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.azure_cli_executor import get_azure_cli_executor
    from app.agentic.eol.utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from app.agentic.eol.utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
    from app.agentic.eol.utils.sre_inventory_integration import get_sre_inventory_integration
    from app.agentic.eol.utils.resource_inventory_client import get_resource_inventory_client
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.sre_gateway import SREGateway
    from app.agentic.eol.utils.sre_incident_memory import get_sre_incident_memory
    from app.agentic.eol.utils.sre_tool_registry import SREToolRegistry
    from app.agentic.eol.utils.query_patterns import classify_sre_domain
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from agents.azure_ai_sre_agent import (
        AzureAISREAgent,
        AgentPerformanceConfig,
    )
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.agent_message_bus import get_message_bus
    from utils.logger import get_logger
    from utils.azure_cli_executor import get_azure_cli_executor
    from utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
    from utils.sre_inventory_integration import get_sre_inventory_integration
    from utils.resource_inventory_client import get_resource_inventory_client  # type: ignore[import-not-found]
    from utils.config import config
    from utils.sre_gateway import SREGateway  # type: ignore[import-not-found]
    from utils.sre_incident_memory import get_sre_incident_memory  # type: ignore[import-not-found]
    from utils.sre_tool_registry import SREToolRegistry  # type: ignore[import-not-found]
    from utils.query_patterns import classify_sre_domain  # type: ignore[import-not-found]


logger = get_logger(__name__)

try:
    from agent_framework import Message as ChatMessage, ChatResponse  # type: ignore[import]  # ChatMessage renamed to Message in RC1
    _HYBRID_CHAT_TYPES_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _HYBRID_CHAT_TYPES_AVAILABLE = False

    @dataclass
    class ChatMessage:  # type: ignore[no-redef]
        role: str
        text: str

    @dataclass
    class ChatResponse:  # type: ignore[no-redef]
        messages: List[ChatMessage]
        content: Optional[str] = None

try:
    from app.agentic.eol.utils.agent_framework_clients import (  # type: ignore[import]
        build_chat_options,
        create_chat_client,
    )
except ModuleNotFoundError:
    try:
        from utils.agent_framework_clients import (  # type: ignore[import]
            build_chat_options,
            create_chat_client,
        )
    except Exception:  # pragma: no cover - optional dependency fallback
        build_chat_options = None  # type: ignore[assignment]
        create_chat_client = None  # type: ignore[assignment]


class SREOrchestratorAgent(BaseSREAgent):
    """SRE Orchestrator Agent — agent-first architecture.

    Routes ALL user queries through the Azure AI SRE Agent (gccsreagent) which
    handles intent analysis, tool selection, and response synthesis. Falls back
    to direct MCP execution when the agent is unavailable.

    Responsibilities:
    - Manage conversation threads per workflow_id
    - Forward queries to gccsreagent for reasoning
    - Execute tool calls requested by the agent (parallel when possible)
    - Submit results back to agent for synthesis
    - Format final HTML responses via SREResponseFormatter
    - Graceful degradation to direct MCP execution

    The orchestrator coordinates 48+ SRE tools across:
    - Resource health & diagnostics
    - Incident response & RCA
    - Performance monitoring & anomaly detection
    - Safe remediation with approval gates
    - Cost optimization
    - SLO management
    - Security & compliance
    """

    def __init__(self):
        """Initialize SRE Orchestrator Agent."""
        super().__init__(
            agent_type="sre-orchestrator",
            agent_id="sre-orchestrator-main",
            max_retries=2,
            timeout=300,
        )

        self.registry = get_agent_registry()
        self.message_bus = get_message_bus()
        self._context_store = None

        # Response formatting
        self.formatter = SREResponseFormatter()
        self.interaction_handler = None  # Initialized in _initialize_impl

        # Azure AI SRE Agent (the primary brain)
        self.azure_sre_agent: Optional[AzureAISREAgent] = None

        # SRE routing / memory utilities
        self._gateway = SREGateway()
        self._incident_memory = get_sre_incident_memory()
        self._tool_registry = SREToolRegistry()

        # Resource discovery cache (in-memory, short TTL)
        self.resource_cache: Dict[str, Any] = {}
        self.resource_cache_ttl = 300  # 5 minutes

        # Resource inventory client + grounding context (populated async in _initialize_impl)
        self.resource_inventory_client: Optional[Any] = None
        self._inventory_grounding_context: str = ""  # tenant/sub/resource-group summary for agent context

        # Hybrid formatting (deterministic stats + optional LLM narrative)
        self.hybrid_formatting_enabled = os.getenv(
            "SRE_HYBRID_FORMATTING_ENABLED", "false",
        ).lower() == "true"
        self.hybrid_narrative_timeout_seconds = int(
            os.getenv("SRE_HYBRID_TIMEOUT_SECONDS", "15"),
        )
        self.hybrid_narrative_max_tokens = int(
            os.getenv("SRE_HYBRID_MAX_TOKENS", "240"),
        )
        self._hybrid_chat_client = None
        self.disable_response_formatting = os.getenv(
            "SRE_DISABLE_FORMAT_RESPONSE", "false",
        ).lower() == "true"

    async def _initialize_impl(self) -> None:
        """Initialize orchestrator-specific resources."""
        # Initialize context store
        self._context_store = await get_context_store()

        # Initialize interaction handler with Azure CLI executor
        self.interaction_handler = get_interaction_handler(
            azure_cli_executor=self._execute_azure_cli
        )

        # Resource inventory integration
        try:
            strict_inventory_mode = os.environ.get(
                "SRE_INVENTORY_STRICT_MODE", "true"
            ).lower() == "true"
            self.inventory_integration = get_sre_inventory_integration(
                strict_mode=strict_inventory_mode
            )
            logger.info(
                "SRE orchestrator inventory integration initialized "
                "(strict_mode=%s)", strict_inventory_mode
            )
        except Exception as e:
            logger.warning("Inventory integration not available: %s", e)
            self.inventory_integration = None

        # Resource inventory client (for grounding context)
        try:
            self.resource_inventory_client = get_resource_inventory_client()
            logger.info("SRE orchestrator resource inventory client initialized")
        except Exception as exc:
            logger.warning("Resource inventory client unavailable in SRE orchestrator: %s", exc)
            self.resource_inventory_client = None

        # Build tenant/subscription/resource-inventory grounding for agent context
        await self._refresh_inventory_grounding()

        if self.hybrid_formatting_enabled:
            if not _HYBRID_CHAT_TYPES_AVAILABLE or create_chat_client is None or build_chat_options is None:
                logger.warning(
                    "Hybrid formatting enabled but Agent Framework chat dependencies are unavailable",
                )
            else:
                self._hybrid_chat_client = create_chat_client()
                if self._hybrid_chat_client:
                    logger.info("Hybrid formatting enabled (deterministic + LLM narrative)")
                else:
                    logger.warning("Hybrid formatting enabled but chat client initialization failed")

        # Initialize Azure AI SRE Agent
        try:
            sre_cfg = config.azure_ai_sre
            if sre_cfg.enabled:
                self.azure_sre_agent = AzureAISREAgent(
                    project_endpoint=sre_cfg.project_endpoint,
                    agent_name=sre_cfg.agent_name or "gccsreagent",
                )
                # If a pre-provisioned agent ID exists, use it instead of creating
                if sre_cfg.agent_id:
                    # Attach to existing agent in Azure AI Foundry
                    if await self.azure_sre_agent.is_available():
                        try:
                            agent_obj = self.azure_sre_agent.get_agent(sre_cfg.agent_id)
                            self.azure_sre_agent.agent = agent_obj
                            logger.info(
                                "Attached to pre-provisioned agent: %s",
                                sre_cfg.agent_id,
                            )
                        except Exception as e:
                            err_text = str(e)
                            if "404" in err_text or "Resource not found" in err_text:
                                logger.info(
                                    "Pre-provisioned agent not found in Azure AI Project (%s): %s — "
                                    "creating on-demand",
                                    sre_cfg.agent_id,
                                    err_text,
                                )
                            else:
                                logger.warning(
                                    "Could not attach to agent %s: %s — "
                                    "creating on-demand",
                                    sre_cfg.agent_id,
                                    err_text,
                                )

                            try:
                                await self.azure_sre_agent.create_agent()
                            except Exception as create_exc:
                                logger.warning(
                                    "On-demand SRE agent creation failed after attach miss: %s",
                                    create_exc,
                                )
                else:
                    # Create agent on-demand
                    if await self.azure_sre_agent.is_available():
                        await self.azure_sre_agent.create_agent()
            else:
                logger.info("Azure AI SRE Agent disabled via config")
        except Exception as e:
            logger.warning("Azure AI SRE Agent initialization failed: %s", e)
            self.azure_sre_agent = None

        # Subscribe to message bus
        await self.message_bus.subscribe(
            self.agent_id,
            message_types=["request.*", "response", "event.*"],
        )

        # Initialize incident memory (best-effort — degrades to in-memory fallback)
        try:
            await self._incident_memory.initialize()
            logger.info("SRE incident memory initialized")
        except Exception as e:
            logger.warning("Incident memory initialization failed: %s", e)

        agent_status = "connected" if (
            self.azure_sre_agent and await self.azure_sre_agent.is_available()
        ) else "fallback_mode"
        logger.info("SRE Orchestrator initialized (agent_status=%s)", agent_status)

    async def _refresh_inventory_grounding(self) -> None:
        """Build a compact resource-inventory summary for agent context grounding.

        Populates self._inventory_grounding_context with tenant ID, subscription ID,
        resource-group names, and cached resource-type counts so the agent can resolve
        tool parameters (subscription_id, resource_group, etc.) without extra tool calls.
        """
        lines: List[str] = []

        # -- Tenant / subscription from config / env --
        tenant_id = (
            getattr(getattr(config, "azure", None), "tenant_id", "") or
            os.environ.get("AZURE_TENANT_ID", os.environ.get("TENANT_ID", ""))
        )
        subscription_id = (
            getattr(getattr(config, "azure", None), "subscription_id", "") or
            os.environ.get("SUBSCRIPTION_ID", os.environ.get("AZURE_SUBSCRIPTION_ID", ""))
        )

        if tenant_id:
            lines.append(f"tenant_id: {tenant_id}")
        if subscription_id:
            lines.append(f"subscription_id: {subscription_id} (use directly — do NOT call subscription-list tools to discover it)")

        if self.resource_inventory_client:
            try:
                sub = subscription_id or self.resource_inventory_client._default_subscription()

                # Resource groups
                try:
                    rgs = await self.resource_inventory_client.get_resources(
                        "Microsoft.Resources/resourceGroups", subscription_id=sub
                    )
                    if rgs:
                        rg_names = sorted({
                            r.get("name") or r.get("resource_group", "")
                            for r in rgs if r.get("name") or r.get("resource_group")
                        })
                        lines.append(
                            f"resource_groups ({len(rg_names)}): {', '.join(rg_names[:10])}"
                            + (" …" if len(rg_names) > 10 else "")
                        )
                except Exception as exc:
                    logger.debug("SRE grounding: RG lookup failed: %s", exc)

                # Resource type counts from L1 cache (no network call)
                try:
                    cache = self.resource_inventory_client._cache
                    prefix = f"resource_inv:{sub}:"
                    type_counts: Dict[str, int] = {}
                    with cache._l1_lock:
                        for key, resources in cache._l1.items():
                            if key.startswith(prefix):
                                rtype = key[len(prefix):]
                                if rtype and isinstance(resources, list):
                                    type_counts[rtype] = len(resources)
                    if type_counts:
                        top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:8]
                        lines.append(
                            "cached_resource_types: "
                            + "; ".join(f"{t} ({n})" for t, n in top_types)
                        )
                except Exception as exc:
                    logger.debug("SRE grounding: type counts failed: %s", exc)

            except Exception as exc:
                logger.debug("SRE inventory grounding refresh failed (non-fatal): %s", exc)

        if lines:
            self._inventory_grounding_context = "\n".join(lines)
            logger.info("🗺️  SRE inventory grounding context refreshed (%d fields)", len(lines))

    async def _cleanup_impl(self) -> None:
        """Clean up orchestrator resources."""
        await self.message_bus.unsubscribe(self.agent_id)

    # ------------------------------------------------------------------
    # Core request handler (agent-first with MCP fallback)
    # ------------------------------------------------------------------

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Agent-first execution with MCP fallback.

        1. Try gccsreagent first — let it reason about intent and select tools
        2. Execute any tool calls the agent requests (in parallel)
        3. Send results back to agent for synthesis
        4. Fall back to direct MCP execution if agent unavailable or errors

        Args:
            request: Dict with 'query', optional 'context', 'workflow_id', etc.

        Returns:
            Orchestrated result with formatted_response, agent_metadata, etc.
        """
        query = request.get("query", request.get("intent", ""))
        workflow_id = request.get("workflow_id") or uuid.uuid4().hex
        context = request.get("context", {})

        logger.info("Handling request: %s... (workflow=%s)", query[:80], workflow_id[:12])

        # Create workflow context
        if self._context_store:
            await self._context_store.create_workflow_context(
                workflow_id,
                initial_data={"query": query, "request": request},
            )

        # 1. Try gccsreagent first
        if self.azure_sre_agent and await self.azure_sre_agent.is_available():
            try:
                return await self._execute_via_agent(
                    query, workflow_id, context, request,
                )
            except asyncio.TimeoutError:
                logger.warning("Agent timeout, falling back to MCP direct")
            except Exception as exc:
                logger.error("Agent error: %s — falling back to MCP", exc, exc_info=True)

        # 2. Fallback: Direct MCP execution
        return await self._execute_mcp_fallback(request, workflow_id)

    async def _execute_via_agent(
        self,
        query: str,
        workflow_id: str,
        context: Dict[str, Any],
        request: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute request via Azure AI SRE Agent.

        Args:
            query: User query
            workflow_id: Workflow identifier
            context: Request context
            request: Full original request

        Returns:
            Formatted result dict
        """
        agent = self.azure_sre_agent

        # Get or create conversation thread for this workflow
        thread_id = await agent.get_or_create_thread(workflow_id)
        if not thread_id:
            raise RuntimeError("Failed to create agent thread")

        # Build enriched context for the agent
        enriched_context = {**context}
        enriched_context["tenant_id"] = (
            context.get("tenant_id")
            or getattr(getattr(config, "azure", None), "tenant_id", "")
            or os.environ.get("AZURE_TENANT_ID", os.environ.get("TENANT_ID", ""))
        )
        enriched_context["subscription_id"] = (
            context.get("subscription_id")
            or os.environ.get("SUBSCRIPTION_ID", "")
        )
        enriched_context["workspace_id"] = (
            context.get("workspace_id")
            or os.environ.get("LOG_ANALYTICS_WORKSPACE_ID", "")
        )
        enriched_context["resource_group"] = (
            context.get("resource_group")
            or os.environ.get("RESOURCE_GROUP_NAME", "")
        )
        # Inject inventory grounding so agent can resolve tool params without extra tool calls
        if self._inventory_grounding_context:
            enriched_context["azure_grounding"] = self._inventory_grounding_context

        # Classify domain (fast keyword path, no LLM cost)
        try:
            domain = await self._gateway.classify(query)
        except Exception:
            domain = None  # type: ignore[assignment]

        # Inject similar-incident context prefix
        try:
            memory_prefix = await self._incident_memory.get_context_prefix(
                query, domain=domain
            )
            if memory_prefix:
                enriched_context["incident_history"] = memory_prefix
        except Exception as mem_exc:
            logger.debug("Incident memory lookup failed: %s", mem_exc)

        # Build domain-narrow tool subset to reduce prompt token cost
        tool_subset: Optional[List[Dict[str, Any]]] = None
        try:
            all_tool_defs = self._get_registered_tools()
            if all_tool_defs and domain is not None:
                subset = self._tool_registry.get_tool_definitions(domain, all_tool_defs)
                if subset:
                    tool_subset = subset
        except Exception as ts_exc:
            logger.debug("Tool subset build failed: %s", ts_exc)

        # Send query to agent
        agent_response = await agent.chat(
            thread_id=thread_id,
            message=query,
            context=enriched_context,
            tool_subset=tool_subset,
            slim_prompt=True,
        )

        # Handle errors
        if agent_response.get("error"):
            raise RuntimeError(agent_response["error"])

        # Execute any tool calls requested by agent
        tool_calls = agent_response.get("tool_calls")
        tools_executed = []

        if tool_calls:
            # Execute tools in parallel
            tool_results = await agent.execute_tool_calls_parallel(
                tool_calls=tool_calls,
                executor_fn=self._execute_agent_tool_call,
                workflow_id=workflow_id,
            )
            tools_executed = tool_results

            # Send results back to agent for synthesis
            run_id = agent_response.get("run_id", "")
            final_response = await agent.submit_tool_results(
                thread_id=thread_id,
                run_id=run_id,
                tool_results=tool_results,
            )

            if final_response.get("error"):
                raise RuntimeError(final_response["error"])

            formatted = self._format_agent_response(
                final_response, workflow_id, tools_executed,
            )
            # Store resolved incident in memory for future context
            await self._store_incident_memory(
                query, workflow_id, domain, tools_executed, final_response
            )
            return formatted

        # Agent responded directly without tool calls
        if self._should_force_mcp_fallback(query, agent_response.get("content", "")):
            logger.info(
                "Agent returned non-actionable guidance for operational query; "
                "forcing MCP fallback execution",
            )
            return await self._execute_mcp_fallback(request, workflow_id)

        formatted = self._format_agent_response(
            agent_response, workflow_id, tools_executed,
        )
        await self._store_incident_memory(
            query, workflow_id, domain, tools_executed, agent_response
        )
        return formatted

    @staticmethod
    def _should_force_mcp_fallback(query: str, content: str) -> bool:
        """Detect generic portal-style guidance for operational requests.

        If the user asked for operational analysis/remediation and the agent
        responds with navigation instructions instead of executing tools,
        prefer deterministic MCP execution.
        """
        if not content:
            return True

        q = query.lower()
        c = content.lower()

        operational_markers = (
            "cost", "analysis", "diagnos", "incident", "alert", "kql",
            "health", "latency", "restart", "scale", "resource", "inventory",
        )
        portal_markers = (
            "azure portal", "in the portal", "go to the portal", "navigate to",
            "open the portal", "click", "menu", "blade",
        )

        is_operational_query = any(marker in q for marker in operational_markers)
        is_portal_guidance = any(marker in c for marker in portal_markers)
        return is_operational_query and is_portal_guidance

    async def _execute_agent_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single tool call requested by the agent.

        This is the executor_fn passed to execute_tool_calls_parallel().

        Args:
            tool_name: MCP tool name
            arguments: Tool arguments from agent

        Returns:
            Tool execution result
        """
        # Get tool info from registry
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            return {"error": f"Tool {tool_name} not registered", "success": False}

        agent_id = tool_info["agent_id"]
        agent = self.registry.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not available", "success": False}

        # Preflight resource check
        if self.inventory_integration and arguments:
            try:
                preflight = await self.inventory_integration.preflight_resource_check(
                    tool_name, arguments,
                )
                if not preflight.get("ok", True):
                    error_msg = preflight.get("result", {}).get("error", "Preflight failed")
                    return {"error": error_msg, "success": False, "preflight_failed": True}
            except Exception as e:
                logger.warning("Preflight check error: %s", e)

        # Execute via the registered agent
        try:
            tool_result = await agent.handle_request({
                "tool": tool_name,
                "parameters": arguments,
            })
            return tool_result.get("result", tool_result)
        except Exception as e:
            logger.error("Tool %s execution failed: %s", tool_name, e)
            return {"error": str(e), "success": False}

    def _format_agent_response(
        self,
        agent_response: Dict[str, Any],
        workflow_id: str,
        tools_executed: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Format agent response into the standard orchestrator output.

        Args:
            agent_response: Response from AzureAISREAgent.chat() or submit_tool_results()
            workflow_id: Workflow identifier
            tools_executed: Optional list of tool execution results

        Returns:
            Formatted result dict with formatted_response HTML and metadata
        """
        content = agent_response.get("content", "")
        token_usage = agent_response.get("token_usage", {})
        latency_ms = agent_response.get("latency_ms", 0)

        # Build tool execution summary for response formatting
        tools_called = []
        tool_results_list = []
        if tools_executed:
            for tr in tools_executed:
                tools_called.append(tr.get("name", "unknown"))
                tool_results_list.append({
                    "tool": tr.get("name", "unknown"),
                    "status": "success" if tr.get("success") else "error",
                    "result": tr.get("result", {}),
                    "latency_ms": tr.get("latency_ms", 0),
                })

        # Build aggregated results structure (compatible with existing API)
        results = {
            "summary": {
                "total_tools": len(tools_executed or []),
                "successful": sum(1 for t in (tools_executed or []) if t.get("success")),
                "failed": sum(1 for t in (tools_executed or []) if not t.get("success")),
                "skipped": 0,
                "needs_input": 0,
                "intent": "agent_routed",
            },
            "results": tool_results_list,
            "agent_content": content,
        }

        if not self.disable_response_formatting:
            results["formatted_response"] = self._build_agent_html_response(
                content, tool_results_list,
            )

        return {
            "workflow_id": workflow_id,
            "intent": "agent_routed",
            "tools_executed": len(tools_executed or []),
            "results": results,
            "agent_metadata": {
                "thread_id": agent_response.get("thread_id"),
                "run_id": agent_response.get("run_id"),
                "tools_called": tools_called,
                "execution_source": "agent",
                "latency_ms": latency_ms,
                "token_usage": token_usage,
            },
        }

    def _build_agent_html_response(
        self,
        agent_content: str,
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """Build HTML from agent content and tool results.

        Args:
            agent_content: Text response from the agent
            tool_results: List of tool result dicts

        Returns:
            HTML string
        """
        html_parts = []

        # Agent synthesis
        if agent_content:
            # Convert markdown-like content to HTML
            escaped = html.escape(agent_content)
            # Basic markdown → HTML conversion for agent output
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
            escaped = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_parts.append(f"<div class='agent-response'><p>{escaped}</p></div>")

        # Tool execution details (collapsible)
        if tool_results:
            successful = [r for r in tool_results if r.get("status") == "success"]
            failed = [r for r in tool_results if r.get("status") != "success"]

            if successful:
                html_parts.append(
                    f"<p><small>Tools executed: {len(successful)} successful"
                    f"{f', {len(failed)} failed' if failed else ''}</small></p>"
                )

            # Format individual tool results
            for result in tool_results:
                tool_name = result.get("tool", "Unknown")
                tool_result = result.get("result", {})
                formatted = format_tool_result(tool_name, tool_result)
                html_parts.append(f"<hr>{formatted}")

        return "\n".join(html_parts) if html_parts else "<p>No results available.</p>"

    def _get_registered_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Get tool definitions for agent registration.

        Returns None to use the agent's built-in tool definitions.
        """
        # The AzureAISREAgent already has comprehensive tool definitions.
        # Return None to let the agent use its own tools.
        return None

    async def _store_incident_memory(
        self,
        query: str,
        workflow_id: str,
        domain: Any,
        tools_executed: List[Dict[str, Any]],
        agent_response: Dict[str, Any],
    ) -> None:
        """Persist resolved incident to incident memory (best-effort)."""
        try:
            resolution = agent_response.get("content", "")[:500]
            if not resolution:
                return
            tools_used = [t.get("name", "") for t in (tools_executed or [])]
            await self._incident_memory.store(
                workflow_id=workflow_id,
                query=query,
                domain=domain,
                tools_used=tools_used,
                resolution=resolution,
                outcome="resolved",
            )
        except Exception as e:
            logger.debug("Incident memory store failed: %s", e)

    # ------------------------------------------------------------------
    # MCP Fallback Path
    # ------------------------------------------------------------------

    async def _execute_mcp_fallback(
        self,
        request: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        """Execute request via direct MCP tool routing (graceful degradation).

        This is the fallback path when gccsreagent is unavailable. It uses
        simple keyword matching to select tools and executes them directly.

        Args:
            request: Original request
            workflow_id: Workflow identifier

        Returns:
            Result dict in standard orchestrator format
        """
        query = request.get("query", request.get("intent", ""))
        logger.info("MCP fallback execution for: %s...", query[:80])

        # Simple keyword-based tool selection (fallback only)
        tools = self._select_fallback_tools(query)

        # Stream progress
        await self._stream_event("progress", {
            "workflow_id": workflow_id,
            "status": "routing",
            "intent": "mcp_fallback",
            "tools": tools,
        })

        # Execute tools
        results = await self._execute_tools(tools, request, workflow_id)

        # Aggregate results
        aggregated = self._aggregate_results(results, "mcp_fallback")

        hybrid_narrative = await self._generate_hybrid_narrative(query, aggregated)
        if hybrid_narrative:
            aggregated["hybrid_narrative"] = hybrid_narrative

        # Update workflow context
        if self._context_store:
            await self._context_store.update_workflow_context(
                workflow_id,
                {
                    "metadata": {
                        "status": "completed",
                        "intent": "mcp_fallback",
                        "tools_executed": len(results),
                        "execution_source": "mcp_fallback",
                    }
                },
            )

        # Format response unless disabled (raw payload mode)
        if (
            not self.disable_response_formatting
            and aggregated.get("results")
            and not aggregated.get("user_interaction_required")
        ):
            formatted_html = self.format_response(aggregated, "mcp_fallback")
            aggregated["formatted_response"] = formatted_html

        return {
            "workflow_id": workflow_id,
            "intent": "mcp_fallback",
            "tools_executed": len(results),
            "results": aggregated,
            "agent_metadata": {
                "thread_id": None,
                "run_id": None,
                "tools_called": [r.get("tool") for r in results],
                "execution_source": "mcp_fallback",
                "latency_ms": 0,
                "token_usage": {},
            },
        }

    def _select_fallback_tools(self, query: str) -> List[str]:
        """Simple keyword-based tool selection for MCP fallback.

        This replaces the old regex intent patterns with a minimal
        keyword matcher. The agent handles the smart routing in
        the primary path.

        Args:
            query: User query string

        Returns:
            List of tool names to execute
        """
        q = query.lower()

        # Container Apps explicit routing (covers list/revision/outage prompts)
        if self._is_container_app_query(q):
            if any(kw in q for kw in ("performance", "metrics", "cpu", "memory", "latency", "utilization")):
                return ["get_performance_metrics"]

            if any(kw in q for kw in ("list", "show", "all", "which", "what")):
                if "revision" in q or "active" in q:
                    return ["query_container_app_configuration"]
                return ["list_container_apps"]

            if any(kw in q for kw in ("down", "outage", "unavailable", "failing", "failed")):
                return ["check_container_app_health"]

            if any(kw in q for kw in ("analyze", "diagnose", "troubleshoot", "investigate", "availability")):
                return ["check_container_app_health"]

        # Health checks
        if any(kw in q for kw in ("health", "status", "check")):
            if "container" in q:
                return ["check_container_app_health"]
            if any(kw in q for kw in ("aks", "kubernetes", "k8s", "cluster")):
                return ["check_aks_cluster_health"]
            return ["check_resource_health"]

        # Incident/troubleshooting
        if any(kw in q for kw in ("incident", "triage", "troubleshoot", "investigate")):
            return ["triage_incident"]

        # Performance
        if any(kw in q for kw in ("performance", "metrics", "cpu", "memory", "bottleneck")):
            if self._is_container_app_query(q):
                return ["get_performance_metrics"]
            return ["get_performance_metrics", "identify_bottlenecks"]

        # Cost
        if any(kw in q for kw in ("cost", "spending", "budget", "savings")):
            return ["get_cost_analysis", "get_cost_recommendations"]

        if any(kw in q for kw in ("orphaned", "unused", "idle", "waste")):
            return ["identify_orphaned_resources"]

        # SLO
        if any(kw in q for kw in ("slo", "error budget", "service level")):
            return ["calculate_error_budget", "get_slo_dashboard"]

        # Security
        if any(kw in q for kw in ("security", "secure score", "vulnerability")):
            return ["get_security_score", "list_security_recommendations"]
        if any(kw in q for kw in ("compliance", "policy", "cis", "nist")):
            return ["check_compliance_status"]

        # Remediation
        if any(kw in q for kw in ("restart", "reboot", "fix")):
            return ["plan_remediation"]
        if any(kw in q for kw in ("scale", "resize")):
            return ["scale_resource"]

        # Logs
        if any(kw in q for kw in ("log", "error", "diagnostic")):
            return ["get_diagnostic_logs", "search_logs_by_error"]

        # Config
        if "config" in q:
            if "container" in q:
                return ["query_container_app_configuration"]
            if any(kw in q for kw in ("aks", "kubernetes")):
                return ["query_aks_configuration"]
            if "apim" in q or "api management" in q:
                return ["query_apim_configuration"]
            return ["query_app_service_configuration"]

        # Default
        return ["describe_capabilities"]

    @staticmethod
    def _is_container_app_query(query: str) -> bool:
        """Return True when a query clearly targets Azure Container Apps."""
        q = query.lower()
        q = re.sub(r"[’']s\b", "", q)
        q = re.sub(r"[^a-z0-9\s_-]", " ", q)
        q = re.sub(r"\s+", " ", q).strip()

        patterns = (
            r"\bcontainer[\s_-]*apps?\b",
            r"\bcontainerapps?\b",
            r"\bcontainre[\s_-]*apps?\b",
        )
        return any(re.search(pattern, q) for pattern in patterns)

    # ------------------------------------------------------------------
    # Legacy execute() — delegates to handle_request()
    # ------------------------------------------------------------------

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute orchestrator logic (legacy interface).

        Delegates to handle_request() which uses agent-first routing.

        Args:
            request: Request with 'query' or 'intent' field
            context: Optional workflow context

        Returns:
            Orchestrated result
        """
        # Merge context into request if provided separately
        if context:
            request = {**request, "context": {**request.get("context", {}), **context}}
        return await self.handle_request(request)

    # ------------------------------------------------------------------
    # Tool execution (shared between agent path and fallback path)
    # ------------------------------------------------------------------

    async def _execute_tools(
        self,
        tool_names: List[str],
        request: Dict[str, Any],
        workflow_id: str,
    ) -> List[Dict[str, Any]]:
        """Execute multiple tools sequentially.

        Used by the MCP fallback path. The agent path uses parallel execution
        through AzureAISREAgent.execute_tool_calls_parallel().

        Args:
            tool_names: List of tool names to execute
            request: Original request
            workflow_id: Workflow identifier

        Returns:
            List of tool results
        """
        results = []
        for tool_name in tool_names:
            try:
                result = await self._execute_single_tool(
                    tool_name, request, workflow_id,
                )
                results.append(result)
            except Exception as exc:
                logger.error("Tool %s failed: %s", tool_name, exc)
                results.append({
                    "tool": tool_name,
                    "status": "error",
                    "error": str(exc),
                })
        return results

    async def _execute_single_tool(
        self,
        tool_name: str,
        request: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        """Execute a single tool.

        Args:
            tool_name: Tool name
            request: Request data
            workflow_id: Workflow identifier

        Returns:
            Tool execution result
        """
        # Get tool info from registry
        tool_info = self.registry.get_tool(tool_name)
        if not tool_info:
            logger.warning("Tool %s not found in registry", tool_name)
            return {
                "tool": tool_name,
                "status": "not_found",
                "error": f"Tool {tool_name} not registered",
            }

        agent_id = tool_info["agent_id"]

        # Stream progress
        await self._stream_event("progress", {
            "workflow_id": workflow_id,
            "status": "executing_tool",
            "tool": tool_name,
            "agent": agent_id,
        })

        # Get agent
        agent = self.registry.get_agent(agent_id)
        if not agent:
            return {
                "tool": tool_name,
                "status": "error",
                "error": f"Agent {agent_id} not available",
            }

        # Prepare tool parameters
        parameters = await self._prepare_tool_parameters(
            tool_name, tool_info, request,
        )

        # Preflight resource check
        if self.inventory_integration and parameters:
            try:
                preflight = await self.inventory_integration.preflight_resource_check(
                    tool_name, parameters,
                )
                if not preflight.get("ok", True):
                    error_msg = preflight.get("result", {}).get("error", "Preflight check failed")
                    suggestion = preflight.get("result", {}).get("suggestion", "")
                    logger.info("Preflight check failed for %s: %s", tool_name, error_msg)
                    return {
                        "tool": tool_name,
                        "agent": agent_id,
                        "status": "not_found",
                        "result": {
                            "success": False,
                            "error": error_msg,
                            "suggestion": suggestion,
                            "preflight_failed": True,
                            "message": (
                                f"Resource not found in inventory. {suggestion}"
                                if suggestion
                                else "Resource not found in inventory."
                            ),
                        },
                    }
                if "warning" in preflight:
                    logger.warning("Preflight warning: %s", preflight["warning"])
            except Exception as e:
                logger.warning("Preflight check failed: %s", e)

        # Check if user input is needed
        if isinstance(parameters, dict) and parameters.get("status") == "needs_user_input":
            return {
                "tool": tool_name,
                "agent": agent_id,
                "status": "needs_user_input",
                "result": parameters,
            }

        # Skip tool if required parameters not available
        if parameters is None:
            logger.info("Skipping %s - required parameters not available", tool_name)
            return {
                "tool": tool_name,
                "agent": agent_id,
                "status": "skipped",
                "result": {
                    "success": False,
                    "message": "Tool requires parameters that are not available in current context",
                },
            }

        # Execute tool via agent
        tool_result = await agent.handle_request({
            "tool": tool_name,
            "parameters": parameters,
            **request,
        })

        # Enrich error messages with diagnostic info for performance tools
        if tool_name in ("get_performance_metrics", "identify_bottlenecks"):
            wrapped_result = tool_result.get("result", {}) if isinstance(tool_result, dict) else {}
            parsed_result = wrapped_result.get("parsed", {}) if isinstance(wrapped_result, dict) else {}
            metrics = []
            if isinstance(parsed_result, dict):
                metrics = parsed_result.get("metrics", []) or []
            if not metrics and isinstance(wrapped_result, dict):
                metrics = wrapped_result.get("metrics", []) or []
            if not metrics:
                resource_id = parameters.get("resource_id", "")
                diagnostic_info = await self._diagnose_no_metrics(resource_id, tool_result)
                tool_result["diagnostic_info"] = diagnostic_info

        # Record in workflow context
        if self._context_store:
            await self._context_store.add_step_result(
                workflow_id,
                step_id=f"tool-{tool_name}",
                agent_id=agent_id,
                result=tool_result,
            )

        return {
            "tool": tool_name,
            "agent": agent_id,
            "status": "success" if tool_result.get("success") else tool_result.get("status", "error"),
            "inventory_integration": {
                "enabled": self.inventory_integration is not None,
                "statistics": (
                    self.inventory_integration.get_statistics()
                    if self.inventory_integration
                    else None
                ),
            },
            "result": tool_result.get("result", tool_result),
        }

    # ------------------------------------------------------------------
    # Parameter preparation (kept from original)
    # ------------------------------------------------------------------

    async def _prepare_tool_parameters(
        self,
        tool_name: str,
        tool_info: Dict[str, Any],
        request: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Prepare parameters for tool execution.

        Merges parameters from:
        1. Request parameters
        2. Request context
        3. Environment defaults
        4. Resource discovery if needed
        5. User prompts for ambiguous selections

        Args:
            tool_name: Name of the tool
            tool_info: Tool metadata from registry
            request: Original request

        Returns:
            Parameters dict, None if unavailable, or dict with needs_user_input status
        """
        # Start with request parameters
        parameters = dict(request.get("parameters", {}))

        # Merge context parameters
        context = request.get("context", {})
        parameters.update({
            k: v for k, v in context.items()
            if k not in parameters and v is not None
        })

        # Apply environment defaults
        if "subscription_id" not in parameters:
            sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
            if sub_id:
                parameters["subscription_id"] = sub_id

        if "workspace_id" not in parameters:
            ws_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID")
            if ws_id:
                parameters["workspace_id"] = ws_id

        # Resolve/validate scope-based tools
        if self._tool_requires_scope(tool_name):
            normalized_scope = self._normalize_scope(
                parameters.get("scope"),
                parameters.get("subscription_id"),
            )
            if normalized_scope:
                parameters["scope"] = normalized_scope
            else:
                logger.info(
                    "Cannot execute %s - missing valid scope", tool_name,
                )
                return None

        # Check for ambiguous parameters in interactive mode
        query = request.get("query", "")
        stream_enabled = request.get("stream", False)

        if query and self.interaction_handler and stream_enabled:
            ambiguity_check = await self._check_and_handle_ambiguous_params(
                tool_name, parameters, query,
            )
            if ambiguity_check:
                if ambiguity_check.get("auto_selected"):
                    resource = ambiguity_check.get("resource", {})
                    if resource.get("id"):
                        parameters["resource_id"] = resource["id"]
                    if resource.get("name"):
                        parameters["resource_name"] = resource["name"]
                    if resource.get("resource_group"):
                        parameters["resource_group"] = resource["resource_group"]
                    logger.info("Auto-selected resource: %s", resource.get("name"))
                else:
                    return ambiguity_check

        # Tool-specific parameter preparation
        tool_def = tool_info.get("definition", {}).get("function", {})
        required_params = self._get_required_parameters(tool_def)

        # For health/performance tools, try resource discovery if resource_id missing
        discovery_tools = {
            "check_resource_health", "check_container_app_health",
            "check_aks_cluster_health", "get_performance_metrics",
            "identify_bottlenecks", "get_capacity_recommendations",
            "compare_baseline_metrics",
        }
        if "resource_type" not in parameters and self._is_container_app_query(query):
            parameters["resource_type"] = "container_app"

        if tool_name in discovery_tools and "resource_id" not in parameters:
            discovered = await self._discover_resources_for_tool(tool_name, parameters)
            if discovered:
                parameters["resource_id"] = discovered[0]
                logger.info("Discovered resource for %s: %s", tool_name, discovered[0])
            else:
                logger.info("Cannot execute %s - no resource_id and discovery failed", tool_name)
                return None

        # Check required parameters
        missing = [p for p in required_params if p not in parameters]
        if missing:
            logger.info("Tool %s missing required params: %s", tool_name, missing)
            return None

        # Enrich with inventory
        if self.inventory_integration:
            try:
                parameters = await self.inventory_integration.enrich_tool_parameters(
                    tool_name, parameters, context,
                )
            except Exception as e:
                logger.warning("Parameter enrichment failed: %s", e)

        return parameters

    def _get_required_parameters(self, tool_def: Dict[str, Any]) -> List[str]:
        """Extract required parameters from tool definition."""
        parameters = tool_def.get("parameters", {})
        return parameters.get("required", [])

    def _tool_requires_scope(self, tool_name: str) -> bool:
        """Return True when the tool requires an ARM scope parameter."""
        return tool_name in {
            "get_cost_analysis", "analyze_cost_anomalies", "check_compliance_status",
        }

    def _normalize_scope(
        self,
        scope_value: Optional[Any],
        subscription_id: Optional[Any],
    ) -> Optional[str]:
        """Normalize scope to an ARM path."""
        raw_scope = str(scope_value).strip() if scope_value else ""
        raw_subscription = str(subscription_id).strip() if subscription_id else ""
        candidate = raw_scope or raw_subscription
        if not candidate:
            return None
        if candidate.startswith("/subscriptions/"):
            return candidate
        if candidate.startswith("subscriptions/"):
            return f"/{candidate}"
        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            candidate,
        ):
            return f"/subscriptions/{candidate}"
        return None

    # ------------------------------------------------------------------
    # Resource discovery (kept from original)
    # ------------------------------------------------------------------

    async def _discover_resources_for_tool(
        self, tool_name: str, parameters: Dict[str, Any],
    ) -> List[str]:
        """Discover resources for a tool."""
        subscription_id = parameters.get("subscription_id", "default")
        resource_group = parameters.get("resource_group", "all")
        cache_key = f"{tool_name}_{subscription_id}_{resource_group}"

        if cache_key in self.resource_cache:
            cache_entry = self.resource_cache[cache_key]
            now = datetime.now(timezone.utc)
            if now - cache_entry["timestamp"] < timedelta(seconds=self.resource_cache_ttl):
                return cache_entry["data"]

        discovery_map = {
            "check_container_app_health": self._discover_container_apps,
            "check_aks_cluster_health": self._discover_aks_clusters,
            "check_resource_health": self._discover_generic_resources,
            "get_performance_metrics": self._discover_vms,
            "identify_bottlenecks": self._discover_vms,
            "get_capacity_recommendations": self._discover_vms,
            "compare_baseline_metrics": self._discover_vms,
        }

        performance_tools = {
            "get_performance_metrics",
            "identify_bottlenecks",
            "get_capacity_recommendations",
            "compare_baseline_metrics",
        }
        resource_type_hint = str(parameters.get("resource_type", "")).lower()
        if tool_name in performance_tools and resource_type_hint in {
            "container_app", "container app", "containerapp",
        }:
            discovery_map[tool_name] = self._discover_container_apps

        if tool_name not in discovery_map:
            return []

        try:
            resources = await discovery_map[tool_name](parameters)
            if resources:
                self.resource_cache[cache_key] = {
                    "data": resources,
                    "timestamp": datetime.now(timezone.utc),
                }
                return resources
            return []
        except Exception as exc:
            logger.error("Resource discovery failed for %s: %s", tool_name, exc)
            return []

    async def _discover_container_apps(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover Container Apps."""
        rg = parameters.get("resource_group")
        cmd = (
            f'az containerapp list --resource-group {rg} --query "[].id" -o json'
            if rg
            else 'az containerapp list --query "[].id" -o json'
        )
        result = await self._execute_azure_cli(cmd)
        if result.get("status") == "success":
            output = result.get("output", [])
            return output if isinstance(output, list) else []
        return []

    async def _discover_aks_clusters(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover AKS clusters."""
        rg = parameters.get("resource_group")
        cmd = (
            f'az aks list --resource-group {rg} --query "[].id" -o json'
            if rg
            else 'az aks list --query "[].id" -o json'
        )
        result = await self._execute_azure_cli(cmd)
        if result.get("status") == "success":
            output = result.get("output", [])
            return output if isinstance(output, list) else []
        return []

    async def _discover_generic_resources(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover generic Azure resources supporting Resource Health API."""
        resource_types = [
            "Microsoft.Compute/virtualMachines",
            "Microsoft.Web/sites",
            "Microsoft.Sql/servers/databases",
            "Microsoft.Storage/storageAccounts",
            "Microsoft.Network/loadBalancers",
        ]
        rg = parameters.get("resource_group")
        all_resources = []

        for rt in resource_types:
            cmd = (
                f'az resource list --resource-group {rg} --resource-type {rt} --query "[].id" -o json'
                if rg
                else f'az resource list --resource-type {rt} --query "[].id" -o json'
            )
            result = await self._execute_azure_cli(cmd)
            if result.get("status") == "success":
                output = result.get("output", [])
                if isinstance(output, list):
                    all_resources.extend(output)

        return all_resources[:10]

    async def _discover_vms(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover Virtual Machines for performance analysis."""
        rg = parameters.get("resource_group")
        cmd = (
            f'az vm list --resource-group {rg} --query "[].id" -o json'
            if rg
            else 'az vm list --query "[].id" -o json'
        )
        result = await self._execute_azure_cli(cmd)
        if result.get("status") == "success":
            output = result.get("output", [])
            return output[:10] if isinstance(output, list) else []
        return []

    # ------------------------------------------------------------------
    # Result aggregation (kept from original)
    # ------------------------------------------------------------------

    def _aggregate_results(
        self,
        results: List[Dict[str, Any]],
        intent_category: str,
    ) -> Dict[str, Any]:
        """Aggregate results from multiple tools."""
        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") in ("error", "not_found")]
        skipped = [r for r in results if r.get("status") == "skipped"]
        needs_input = [r for r in results if r.get("status") == "needs_user_input"]

        aggregated = {
            "summary": {
                "total_tools": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "skipped": len(skipped),
                "needs_input": len(needs_input),
                "intent": intent_category,
            },
            "results": successful,
            "errors": failed if failed else None,
            "skipped": skipped if skipped else None,
            "needs_input": needs_input if needs_input else None,
        }

        # If user input needed, prioritize that
        if needs_input:
            first_input = needs_input[0].get("result", {})
            aggregated["user_interaction_required"] = True
            aggregated["interaction_data"] = first_input
            aggregated["message"] = first_input.get("message", "User input required")
            return aggregated

        # Handle all-preflight-failed case
        not_found = [
            r for r in failed
            if r.get("result", {}).get("preflight_failed", False)
        ]
        if not_found and len(not_found) == len(results):
            aggregated["message"] = self.formatter.format_error_message(
                "Resources not found in inventory.",
                suggestions=[
                    "Verify the resource exists in the Azure subscription",
                    "Check that resource discovery is running",
                    "Provide the full resource ID if recently created",
                    "Run 'list all resources' to see available resources",
                ],
            )
            return aggregated

        # Handle all-skipped case
        if len(skipped) == len(results) and intent_category in ("health", "mcp_fallback"):
            aggregated["message"] = self.formatter.format_error_message(
                "Health check tools require specific resource information.",
                suggestions=[
                    "Provide a resource name: 'Check health of container app my-app'",
                    "Specify a resource group: 'Check health in resource-group prod-rg'",
                    "List available resources first: 'List all container apps'",
                ],
            )

        # Category-specific summaries
        if intent_category == "health":
            aggregated["health_summary"] = self._summarize_health(successful)
        elif intent_category == "cost":
            aggregated["cost_summary"] = self._summarize_cost(successful)
        elif intent_category == "performance":
            perf_summary = self._summarize_performance(successful)
            aggregated["performance_summary"] = perf_summary
            if not perf_summary.get("has_data") and successful:
                aggregated["message"] = self._build_no_metrics_message(successful)

        return aggregated

    # ------------------------------------------------------------------
    # Summary helpers (kept from original)
    # ------------------------------------------------------------------

    def _summarize_health(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize health check results."""
        healthy_count = 0
        unhealthy_count = 0
        unhealthy_details: List[Dict[str, Any]] = []

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue
            parsed_data = result_data.get("parsed", {})
            if not isinstance(parsed_data, dict):
                parsed_data = {}

            health_data = (
                parsed_data.get("health_data")
                or result_data.get("health_status")
                or result_data.get("health_data")
                or {}
            )
            if not isinstance(health_data, dict):
                health_data = {}

            status = (
                health_data.get("availability_state")
                or health_data.get("health_status")
                or parsed_data.get("availability_state")
                or "unknown"
            )
            resource_id = parsed_data.get("resource_id", "")
            resource_name = (
                parsed_data.get("container_app_name")
                or parsed_data.get("resource_name")
                or (resource_id.split("/")[-1] if resource_id else "Unknown Resource")
            )

            if str(status).lower() in ("available", "healthy"):
                healthy_count += 1
                continue

            unhealthy_count += 1
            reason = (
                health_data.get("reason_type")
                or health_data.get("summary")
                or parsed_data.get("note")
                or "No additional diagnostic details"
            )
            recent_errors = health_data.get("recent_errors") or []
            recent_error = recent_errors[0] if isinstance(recent_errors, list) and recent_errors else ""
            unhealthy_details.append({
                "resource_name": str(resource_name),
                "status": str(status),
                "reason": str(reason),
                "recent_error": str(recent_error) if recent_error else "",
            })

        return {
            "healthy_resources": healthy_count,
            "unhealthy_resources": unhealthy_count,
            "total_checked": len(results),
            "unhealthy_details": unhealthy_details,
        }

    def _summarize_cost(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize cost analysis results."""
        def _to_float(value: Any) -> float:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip().replace(",", "")
            if not text or text.upper() == "N/A":
                return 0.0
            try:
                return float(text)
            except ValueError:
                return 0.0

        total_savings = 0.0
        orphaned = 0

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue
            parsed = result_data.get("parsed", {})
            if not isinstance(parsed, dict):
                parsed = {}
            payload = parsed or result_data

            total_savings += _to_float(payload.get("potential_savings", 0.0))

            recs = payload.get("recommendations", [])
            if isinstance(recs, list):
                for rec in recs:
                    if not isinstance(rec, dict):
                        continue
                    monthly = _to_float(
                        rec.get("monthly_savings_amount")
                        or rec.get("monthly_savings")
                        or rec.get("estimated_monthly_savings")
                    )
                    if monthly > 0:
                        total_savings += monthly
                        continue
                    annual = _to_float(rec.get("savings_amount") or rec.get("annual_savings_amount"))
                    if annual > 0:
                        total_savings += annual / 12.0

            total_orphaned = payload.get("total_orphaned_resources")
            if isinstance(total_orphaned, int):
                orphaned += total_orphaned
            else:
                orph = payload.get("orphaned_resources", {})
                if isinstance(orph, dict):
                    orphaned += sum(
                        int(v.get("count", 0)) for v in orph.values() if isinstance(v, dict)
                    )
                elif isinstance(orph, list):
                    orphaned += len(orph)

        return {
            "potential_savings": f"${total_savings:,.2f}",
            "orphaned_resources": orphaned,
            "tools_analyzed": len(results),
        }

    def _summarize_performance(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize performance analysis results."""
        bottlenecks_found = 0
        capacity_recs = 0
        metrics_count = 0
        has_data = False

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue
            parsed = result_data.get("parsed", {})
            if not isinstance(parsed, dict):
                parsed = {}

            bottlenecks = parsed.get("bottlenecks_found") or result_data.get("bottlenecks") or []
            recs = parsed.get("recommendations") or result_data.get("recommendations") or []
            metrics = parsed.get("metrics") or result_data.get("metrics") or []

            bottlenecks_found += len(bottlenecks)
            capacity_recs += len(recs)
            if metrics:
                metrics_count += len(metrics)
                has_data = True

        return {
            "bottlenecks_identified": bottlenecks_found,
            "capacity_recommendations": capacity_recs,
            "metrics_count": metrics_count,
            "has_data": has_data,
            "tools_analyzed": len(results),
        }

    def _build_no_metrics_message(self, results: List[Dict[str, Any]]) -> str:
        """Build a helpful message when no metrics are found."""
        diagnostic_details = []
        recommendations = []
        for result in results:
            if "diagnostic_info" in result:
                diag = result["diagnostic_info"]
                if diag.get("issues_found"):
                    diagnostic_details.extend(diag["issues_found"])
                recommendations.extend(diag.get("recommendations", []))

        if diagnostic_details:
            issues_html = "<br>".join(f"&bull; {i}" for i in diagnostic_details[:3])
            msg = (
                f"No performance metrics found. <strong>Issues detected:</strong><br>"
                f"{issues_html}<br><br>"
            )
            if recommendations:
                rec_html = "<br>".join(f"&bull; {r}" for r in recommendations[:5])
                msg += f"<strong>Recommendations:</strong><br>{rec_html}"
            return msg

        return (
            "No performance metrics found for the specified resources. "
            "This could be because:<br>"
            "&bull; The VM or resource is stopped/deallocated<br>"
            "&bull; Monitoring agent is not installed or configured<br>"
            "&bull; Metrics collection hasn't started yet (wait 3-5 minutes)<br>"
            "&bull; The resource doesn't support the requested metrics<br><br>"
            "<strong>Tip:</strong> Ensure resources are running and have Azure Monitor configured."
        )

    # ------------------------------------------------------------------
    # Diagnostics helper (kept from original)
    # ------------------------------------------------------------------

    async def _diagnose_no_metrics(
        self, resource_id: str, tool_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Diagnose why there are no metrics for a resource."""
        diagnostics: Dict[str, Any] = {"issues_found": [], "recommendations": []}
        if not resource_id:
            diagnostics["issues_found"].append("No resource ID provided")
            diagnostics["recommendations"].append("Specify a resource ID to diagnose")
            return diagnostics

        resource_name = resource_id.split("/")[-1]
        resource_type = "VM" if "/virtualMachines/" in resource_id else "resource"

        resource_group = "unknown"
        try:
            parts = resource_id.split("/")
            rg_index = parts.index("resourceGroups") + 1
            resource_group = parts[rg_index]
        except (ValueError, IndexError):
            pass

        # Check VM power state via resource health
        if "/virtualMachines/" in resource_id:
            try:
                proxy_agent = self.registry.get_agent("sre-mcp-server")
                if proxy_agent:
                    health_result = await proxy_agent.handle_request({
                        "tool": "get_resource_health",
                        "parameters": {"resource_id": resource_id},
                    })
                    if health_result.get("status") == "success":
                        wrapper = health_result.get("result", {})
                        health_data = wrapper.get("result", wrapper) if isinstance(wrapper, dict) else {}
                        state = health_data.get("availability_state", "unknown")
                        if state.lower() in ("unavailable", "degraded"):
                            reason = health_data.get("reason_type", "")
                            diagnostics["issues_found"].append(
                                f"VM '{resource_name}' is {state}: {reason}"
                            )
                            if resource_group != "unknown":
                                diagnostics["recommendations"].append(
                                    f"Start the VM: <code>az vm start -g {resource_group} -n {resource_name}</code>"
                                )
                            diagnostics["recommendations"].append(
                                "Wait 3-5 minutes after starting for metrics to populate"
                            )
                            return diagnostics
            except Exception as e:
                logger.debug("Could not check resource health: %s", e)

        diagnostics["issues_found"].append(
            f"No metrics data available for {resource_type} '{resource_name}'"
        )
        diagnostics["recommendations"].extend([
            "Verify the resource is running and operational",
            "Check if Azure Monitor diagnostic settings are configured",
        ])
        if resource_type == "VM":
            diagnostics["recommendations"].append(
                "Ensure Azure Monitor agent or diagnostic extension is installed"
            )
            if resource_group != "unknown":
                diagnostics["recommendations"].append(
                    f"Check VM status: <code>az vm get-instance-view -g {resource_group} -n {resource_name}</code>"
                )
        diagnostics["recommendations"].append(
            "Allow 3-5 minutes for metrics to populate after resource starts"
        )
        return diagnostics

    # ------------------------------------------------------------------
    # Capabilities & routing
    # ------------------------------------------------------------------

    async def route_to_specialist(
        self,
        specialist_type: str,
        request: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        """Route request to a specialist agent."""
        specialist = self.registry.get_agent_by_type(specialist_type)
        if not specialist:
            return {"status": "error", "error": f"Specialist {specialist_type} not available"}

        try:
            response = await self.message_bus.send_request(
                from_agent=self.agent_id,
                to_agent=specialist.agent_id,
                request_type="execute",
                payload={"request": request, "workflow_id": workflow_id},
                timeout=60.0,
            )
            return response
        except Exception as exc:
            logger.error("Failed to route to specialist %s: %s", specialist_type, exc)
            return {"status": "error", "error": str(exc)}

    def get_capabilities(self) -> Dict[str, Any]:
        """Get orchestrator capabilities."""
        tools = self.registry.list_tools()
        agents = self.registry.list_agents()

        agent_available = bool(
            self.azure_sre_agent
            and self.azure_sre_agent.agents_client
            and self.azure_sre_agent.credential
        )

        # Build per-domain category map from the static SRE tool registry
        try:
            try:
                from app.agentic.eol.utils.sre_tool_registry import SREToolRegistry, SREDomain
            except ModuleNotFoundError:
                from utils.sre_tool_registry import SREToolRegistry, SREDomain  # type: ignore[import-not-found]

            _domain_labels: Dict[str, str] = {
                SREDomain.HEALTH: "Health & Diagnostics",
                SREDomain.INCIDENT: "Incident Management",
                SREDomain.PERFORMANCE: "Performance & SLO",
                SREDomain.COST_SECURITY: "Cost & Security",
                SREDomain.RCA: "Root Cause Analysis",
                SREDomain.REMEDIATION: "Remediation",
            }
            _tool_descriptions: Dict[str, str] = {
                "check_resource_health": "Check the health status of any Azure resource",
                "check_container_app_health": "Diagnose Container App availability and replicas",
                "check_aks_cluster_health": "Verify AKS cluster node and pod health",
                "diagnose_app_service": "Run diagnostics on App Service or Function App",
                "diagnose_apim": "Inspect API Management gateway health",
                "analyze_resource_configuration": "Review resource configuration for misconfigurations",
                "get_diagnostic_logs": "Retrieve diagnostic logs for a resource",
                "get_resource_dependencies": "Map resource dependency relationships",
                "list_container_apps": "List Container Apps in a resource group",
                "triage_incident": "Analyze and triage an active incident",
                "search_logs_by_error": "Search Log Analytics for error patterns",
                "correlate_alerts": "Correlate active alerts to identify root signals",
                "analyze_activity_log": "Inspect Azure Activity Log for changes",
                "generate_incident_summary": "Generate a structured incident summary report",
                "query_app_insights_traces": "Query Application Insights traces",
                "get_request_telemetry": "Retrieve HTTP request telemetry and latency",
                "get_audit_trail": "Retrieve audit trail for compliance investigation",
                "get_performance_metrics": "Fetch CPU, memory, and custom metrics",
                "identify_bottlenecks": "Identify performance bottlenecks across the stack",
                "detect_metric_anomalies": "Detect anomalies via statistical analysis",
                "compare_baseline_metrics": "Compare current metrics against baseline",
                "analyze_dependency_map": "Analyze App Insights dependency map",
                "predict_resource_exhaustion": "Forecast when resources will be exhausted",
                "detect_performance_anomalies": "ML-based anomaly detection on perf data",
                "monitor_slo_burn_rate": "Track SLO error budget burn rate",
                "define_slo": "Define or update a service level objective",
                "calculate_error_budget": "Calculate remaining error budget",
                "get_slo_dashboard": "Retrieve SLO compliance dashboard summary",
                "get_cost_analysis": "Analyze Azure spend by resource/group",
                "identify_orphaned_resources": "Find unused or orphaned resources",
                "get_cost_recommendations": "Get Azure Advisor cost savings recommendations",
                "analyze_cost_anomalies": "Detect unexpected cost spikes",
                "get_security_score": "Retrieve Microsoft Defender security score",
                "list_security_recommendations": "List Defender for Cloud recommendations",
                "check_compliance_status": "Evaluate compliance against policies",
                "perform_root_cause_analysis": "Deep-dive root cause analysis",
                "trace_dependency_chain": "Trace failure across service dependencies",
                "analyze_log_patterns": "Surface recurring patterns in logs",
                "predict_capacity_issues": "Predict upcoming capacity constraints",
                "generate_postmortem": "Draft a structured post-mortem document",
                "calculate_mttr_metrics": "Calculate MTTR and incident frequency",
                "plan_remediation": "Generate a prioritized remediation plan",
                "generate_remediation_plan": "Create step-by-step remediation runbook",
                "execute_safe_restart": "Safely restart a resource with health checks",
                "scale_resource": "Scale a resource up or down",
                "clear_cache": "Flush cache for a service",
                "execute_remediation_step": "Execute a single remediation step",
                "send_teams_notification": "Send notification to Teams channel",
                "send_teams_alert": "Send alert to Teams with severity context",
                "send_sre_status_update": "Broadcast SRE status update to stakeholders",
            }

            seen: set[str] = set()
            categories: Dict[str, List[Dict[str, str]]] = {}
            for domain in SREToolRegistry.all_domains():
                label = _domain_labels.get(domain, domain.value.replace("_", " ").title())
                items = []
                for tool_name in SREToolRegistry.get_tool_names(domain):
                    if tool_name == "describe_capabilities" or tool_name in seen:
                        continue
                    seen.add(tool_name)
                    items.append({
                        "name": tool_name.replace("_", " ").title(),
                        "description": _tool_descriptions.get(tool_name, ""),
                    })
                if items:
                    categories[label] = items
        except Exception:
            categories = {}

        return {
            "orchestrator_version": "2.0.0",
            "total_tools": len(tools),
            "total_agents": len(agents),
            "agent_routing": agent_available,
            "execution_mode": "agent_first" if agent_available else "mcp_fallback",
            "agent_diagnostics": (
                self.azure_sre_agent.get_diagnostics()
                if self.azure_sre_agent
                else None
            ),
            "categories": categories,
        }

    # ------------------------------------------------------------------
    # Azure CLI execution
    # ------------------------------------------------------------------

    async def _execute_azure_cli(self, command: str) -> Dict[str, Any]:
        """Execute Azure CLI command using singleton executor."""
        try:
            executor = await get_azure_cli_executor()
            return await executor.execute(command, timeout=30, add_subscription=True)
        except Exception as exc:
            logger.error("Azure CLI execution failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Interaction handling (kept from original)
    # ------------------------------------------------------------------

    async def _check_and_handle_ambiguous_params(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        query: str,
    ) -> Optional[Dict[str, Any]]:
        """Check if parameters are ambiguous and prompt user."""
        if not self.interaction_handler:
            return None

        missing_check = self.interaction_handler.check_required_params(
            tool_name, parameters,
        )
        if missing_check:
            resource_type = self.interaction_handler.needs_resource_discovery(
                tool_name, parameters, query,
            )
            if resource_type:
                resources = await self._discover_resources_by_type(resource_type, parameters)
                if resources:
                    if len(resources) > 1:
                        return self.interaction_handler.format_selection_prompt(
                            resources,
                            self._get_resource_type_label(resource_type),
                            action="use for this operation",
                        )
                    elif len(resources) == 1:
                        await self._stream_event("info", {
                            "message": f"Found {self._get_resource_type_label(resource_type)}: {resources[0].get('name')}"
                        })
                        return {"auto_selected": True, "resource": resources[0]}
            return missing_check
        return None

    async def _discover_resources_by_type(
        self, resource_type: str, context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Discover resources by type."""
        if not self.interaction_handler:
            return []

        rg = context.get("resource_group")
        name_filter = context.get("name_filter")

        try:
            if resource_type == "container_app":
                return await self.interaction_handler.discover_container_apps(rg, name_filter)
            elif resource_type == "vm":
                return await self.interaction_handler.discover_virtual_machines(rg, name_filter)
            elif resource_type == "resource_group":
                return await self.interaction_handler.discover_resource_groups(
                    context.get("subscription_id"),
                )
            elif resource_type == "workspace":
                return await self.interaction_handler.discover_log_analytics_workspaces(rg)
            else:
                logger.warning("Unknown resource type for discovery: %s", resource_type)
                return []
        except Exception as exc:
            logger.error("Resource discovery failed for %s: %s", resource_type, exc)
            return []

    def _get_resource_type_label(self, resource_type: str) -> str:
        """Get user-friendly label for a resource type."""
        labels = {
            "container_app": "Container App",
            "vm": "Virtual Machine",
            "resource_group": "Resource Group",
            "workspace": "Log Analytics Workspace",
        }
        return labels.get(resource_type, resource_type.replace("_", " ").title())

    # ------------------------------------------------------------------
    # Response formatting (kept from original, enhanced)
    # ------------------------------------------------------------------

    def format_response(
        self,
        aggregated_results: Dict[str, Any],
        intent_category: str,
    ) -> str:
        """Format aggregated results into user-friendly HTML."""
        html_parts = []

        summary = aggregated_results.get("summary", {})
        successful = summary.get("successful", 0)
        total = summary.get("total_tools", 0)

        if successful > 0:
            html_parts.append(
                f"<h3>Operation Complete</h3>"
                f"<p>Successfully executed {successful} out of {total} operations.</p>"
            )
        else:
            html_parts.append(
                f"<h3>Results</h3>"
                f"<p>Processed {total} operation(s).</p>"
            )

        # Format individual results
        results = aggregated_results.get("results", [])
        for result in results:
            tool_name = result.get("tool", "Unknown Tool")
            tool_result = result.get("result", {})
            html_parts.append("<hr>")
            formatted = format_tool_result(tool_name, tool_result)
            html_parts.append(formatted)

        # Category-specific summaries
        if intent_category == "health":
            health_summary = aggregated_results.get("health_summary", {})
            if health_summary:
                html_parts.append("<hr>")
                html_parts.append(
                    f"<h4>Health Summary</h4>"
                    f"<p><strong>Healthy:</strong> {health_summary.get('healthy_resources', 0)}</p>"
                    f"<p><strong>Unhealthy:</strong> {health_summary.get('unhealthy_resources', 0)}</p>"
                )
                unhealthy_details = health_summary.get("unhealthy_details", [])
                if unhealthy_details:
                    html_parts.append("<p><strong>Unhealthy Resource Details:</strong></p><ul>")
                    for detail in unhealthy_details:
                        name = html.escape(detail.get("resource_name", "Unknown"))
                        status = html.escape(detail.get("status", "Unknown"))
                        reason = html.escape(detail.get("reason", ""))
                        recent_error = html.escape(detail.get("recent_error", ""))
                        html_parts.append(
                            f"<li><strong>{name}</strong> — Status: {status}<br>Reason: {reason}"
                        )
                        if recent_error:
                            html_parts.append(f"<br>Recent error: {recent_error}")
                        html_parts.append("</li>")
                    html_parts.append("</ul>")

        elif intent_category == "cost":
            cost_summary = aggregated_results.get("cost_summary", {})
            if cost_summary:
                html_parts.append("<hr>")
                html_parts.append(
                    f"<h4>Cost Summary</h4>"
                    f"<p><strong>Potential Savings:</strong> {cost_summary.get('potential_savings', '$0.00')}</p>"
                    f"<p><strong>Orphaned Resources:</strong> {cost_summary.get('orphaned_resources', 0)}</p>"
                )

        hybrid_narrative = aggregated_results.get("hybrid_narrative")
        if hybrid_narrative:
            html_parts.append("<hr>")
            html_parts.append("<h4>AI Narrative</h4>")
            html_parts.append(
                "<div class='alert alert-secondary'>"
                f"<p>{html.escape(str(hybrid_narrative)).replace(chr(10), '<br>')}</p>"
                "</div>"
            )

        # Add message if present
        message = aggregated_results.get("message")
        if message:
            html_parts.append(
                f"<div class='alert alert-info'>"
                f"<p><strong>Tip:</strong> {message}</p>"
                f"</div>"
            )

        return "\n".join(html_parts)

    async def _generate_hybrid_narrative(
        self,
        query: str,
        aggregated_results: Dict[str, Any],
    ) -> Optional[str]:
        """Optionally generate an LLM narrative on top of deterministic SRE stats."""
        if not self.hybrid_formatting_enabled:
            return None

        if self._hybrid_chat_client is None and create_chat_client is not None:
            self._hybrid_chat_client = create_chat_client()

        if self._hybrid_chat_client is None or build_chat_options is None:
            return None

        facts = self._build_hybrid_facts(aggregated_results)
        if not facts:
            return None

        try:
            system_prompt = (
                "You are an SRE assistant. Produce a concise operational narrative based ONLY on provided facts. "
                "Do not invent numbers. Use plain text, max 3 short bullets. "
                "Mention CPU/memory explicitly when present and call out any risk thresholds (CPU>80 or Memory>80)."
            )
            payload = {
                "user_query": query,
                "facts": facts,
            }
            messages = [
                ChatMessage(role="system", text=system_prompt),
                ChatMessage(role="user", text=json.dumps(payload, default=str)),
            ]
            chat_kwargs = build_chat_options(
                conversation_id=f"sre-hybrid-{uuid.uuid4().hex[:8]}",
                allow_multiple_tool_calls=False,
                store=False,
                temperature=0.1,
                max_tokens=self.hybrid_narrative_max_tokens,
            )
            response = await asyncio.wait_for(
                self._hybrid_chat_client.get_response(messages=messages, **chat_kwargs),
                timeout=self.hybrid_narrative_timeout_seconds,
            )
            text = self._extract_hybrid_response_text(response)
            if text:
                return text[:1200]
        except Exception as exc:
            logger.warning("Hybrid narrative generation failed: %s", exc)

        return None

    def _build_hybrid_facts(self, aggregated_results: Dict[str, Any]) -> Dict[str, Any]:
        """Collect deterministic facts for optional hybrid narrative generation."""
        facts: Dict[str, Any] = {
            "summary": aggregated_results.get("summary", {}),
            "performance": [],
        }

        results = aggregated_results.get("results", [])
        if not isinstance(results, list):
            return facts

        for item in results:
            if not isinstance(item, dict):
                continue
            if item.get("tool") != "get_performance_metrics":
                continue

            result_data = item.get("result", {})
            if not isinstance(result_data, dict):
                continue

            parsed = result_data.get("parsed", {}) if isinstance(result_data.get("parsed"), dict) else result_data
            if not isinstance(parsed, dict):
                continue

            resource_id = parsed.get("resource_id", "")
            resource_name = resource_id.split("/")[-1] if isinstance(resource_id, str) and resource_id else "unknown"
            perf_entry: Dict[str, Any] = {
                "resource_name": resource_name,
                "resource_type": parsed.get("resource_type"),
                "metrics": {},
            }

            metrics = parsed.get("metrics", [])
            if not isinstance(metrics, list):
                continue

            for metric in metrics[:8]:
                if not isinstance(metric, dict):
                    continue
                metric_name_raw = str(metric.get("metric_name", "")).strip()
                metric_name = re.sub(r"[^a-z0-9]", "", metric_name_raw.lower())
                summary = metric.get("summary", {}) if isinstance(metric.get("summary"), dict) else {}
                if metric_name in {"cpupercentage", "percentagecpu", "cpu"}:
                    perf_entry["metrics"]["cpu_percent"] = summary
                elif metric_name in {"memorypercentage", "memory", "memoryusage"}:
                    perf_entry["metrics"]["memory_percent"] = summary
                else:
                    perf_entry["metrics"][metric_name_raw or metric_name] = summary

            if perf_entry["metrics"]:
                facts["performance"].append(perf_entry)

        return facts

    def _extract_hybrid_response_text(self, response: Optional[ChatResponse]) -> str:
        """Normalize Agent Framework responses into a text payload."""
        if response is None:
            return ""

        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        messages = getattr(response, "messages", None)
        if isinstance(messages, list):
            for message in reversed(messages):
                role = getattr(message, "role", None)
                if role not in {"assistant", "system"}:
                    continue

                text = getattr(message, "text", None)
                if isinstance(text, str) and text.strip():
                    return text.strip()

        return ""
