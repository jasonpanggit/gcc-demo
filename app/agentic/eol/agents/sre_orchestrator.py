"""SRE Orchestrator Agent - SRESubAgent (ReAct) with MCP fallback.

Routes all SRE requests through SRESubAgent which runs a ReAct loop over the
SRE MCP server tools, falling back to a scoped message when unavailable.

Architecture:
    User Query → SREOrchestratorAgent.handle_request()
                    ├─→ SRESubAgent (ReAct loop)
                    │   ├─ Grounded with inventory context
                    │   ├─ Iterates tool calls until answer synthesised
                    │   └─ Returns final text response
                    │
                    └─→ MCP Fallback (SRESubAgent unavailable)
                        └─ Returns scoped capability message
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent
    from app.agentic.eol.agents.sre_sub_agent import SRESubAgent  # type: ignore[import-not-found]
    from app.agentic.eol.utils.sre_mcp_client import get_sre_mcp_client, SREMCPDisabledError  # type: ignore[import-not-found]
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
    from agents.base_sre_agent import BaseSREAgent
    from agents.sre_sub_agent import SRESubAgent  # type: ignore[import-not-found]
    from utils.sre_mcp_client import get_sre_mcp_client, SREMCPDisabledError  # type: ignore[import-not-found]
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
    """SRE Orchestrator Agent — SRESubAgent-first architecture.

    Routes ALL user queries through SRESubAgent which runs a ReAct loop over
    SRE MCP server tools. Falls back to a scoped capability message when the
    sub-agent is unavailable.

    Responsibilities:
    - Initialise SRESubAgent from SRE MCP server tools
    - Prepend inventory grounding context before each query
    - Run SRESubAgent ReAct loop and return synthesised response
    - Graceful degradation to informational fallback message

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

        # SRESubAgent — ReAct loop over SRE MCP tools (primary routing brain)
        self._sre_sub_agent: Optional[Any] = None
        self._sre_tool_invoker: Optional[Any] = None

        # SRE routing / memory utilities
        self._gateway = SREGateway()
        self._incident_memory = get_sre_incident_memory()
        self._tool_registry = SREToolRegistry()

        # Unified router (Phase 3) — lazy-initialized
        self.router: Optional[Any] = None
        self._unified_router_initialized: bool = False

        # Resource discovery cache (in-memory, short TTL)
        self.resource_cache: Dict[str, Any] = {}
        self.resource_cache_ttl = 300  # 5 minutes

        # Resource inventory client + grounding context (populated async in _initialize_impl)
        self.resource_inventory_client: Optional[Any] = None
        self._inventory_grounding_context: str = ""  # tenant/sub/resource-group summary for agent context
        self._inventory_grounding_last_refreshed: float = 0.0
        self._inventory_grounding_ttl_seconds: int = int(
            os.getenv("SRE_INVENTORY_GROUNDING_TTL_SECONDS", "300"),
        )

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

        # Initialize SRESubAgent (ReAct loop over SRE MCP tools)
        await self._init_sre_sub_agent()

        # Subscribe to message bus
        await self.message_bus.subscribe(
            self.agent_id,
            message_types=["request.*", "response", "event.*"],
        )

        logger.info(
            "SRE Orchestrator initialized (sre_sub_agent=%s)",
            "ready" if self._sre_sub_agent else "unavailable",
        )

    async def shutdown(self) -> None:
        """Graceful shutdown — no persistent background tasks in SRE orchestrator.

        CQ-07: all orchestrators implement graceful shutdown for API contract parity.
        SREOrchestratorAgent is instantiated per-request; this method is a lightweight
        stub that cancels any incidental background tasks stored in _background_tasks.
        """
        tasks = list(getattr(self, "_background_tasks", set()))
        if tasks:
            logger.debug("Cancelling %d background tasks on SRE shutdown", len(tasks))
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ========================================================================
    # Unified Router Integration (Phase 3)
    # ========================================================================

    def _ensure_unified_router(self) -> None:
        """Lazily wire the unified router onto self.router.

        Called on first use of process_with_routing() to avoid circular
        import issues at module load time.
        """
        if self._unified_router_initialized:
            return
        try:
            try:
                from app.agentic.eol.utils.unified_router import get_unified_router
            except ModuleNotFoundError:
                from utils.unified_router import get_unified_router  # type: ignore[import-not-found]

            self.router = get_unified_router()
            self._unified_router_initialized = True
            logger.debug("SREOrchestratorAgent: unified router wired")
        except Exception as exc:
            logger.warning(
                "SREOrchestratorAgent: failed to wire unified router: %s — "
                "process_with_routing() will raise if called",
                exc,
            )

    async def process_with_routing(
        self,
        query: str,
        strategy: str = "fast",
        context: Optional[Dict[str, Any]] = None,
    ):
        """Route a query using the unified router and return a RoutingPlan.

        This provides the same interface as BaseOrchestrator.process_with_routing()
        so callers can use either orchestrator interchangeably for routing.

        Args:
            query:    User's natural language query.
            strategy: Routing strategy — "fast" | "quality" | "comprehensive".
            context:  Optional context dict passed through to the router.

        Returns:
            RoutingPlan with orchestrator, domain, tools, and timing metadata.

        Raises:
            ValueError: If the unified router cannot be initialized.
        """
        if self.router is None:
            self._ensure_unified_router()
        if self.router is None:
            raise ValueError(
                "UnifiedRouter not available on SREOrchestratorAgent. "
                "Check that unified_router module is importable."
            )
        return await self.router.route(query, context=context, strategy=strategy)

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

        # Log Analytics workspace ID — required for get_diagnostic_logs / search_logs_by_error
        workspace_id = (
            getattr(getattr(config, "azure", None), "log_analytics_workspace_id", "") or
            os.environ.get("LOG_ANALYTICS_WORKSPACE_ID", "")
        )
        if workspace_id:
            lines.append(f"log_analytics_workspace_id: {workspace_id} (use as workspace_id — NOT the subscription_id)")

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

                # Container App name/resource_id hints for resource_id inference
                try:
                    container_apps = await self.resource_inventory_client.get_resources(
                        "Microsoft.App/containerApps", subscription_id=sub
                    )
                    if container_apps:
                        app_hints: List[str] = []
                        app_id_hints: List[str] = []
                        for app in container_apps[:8]:
                            app_name = app.get("resource_name") or app.get("name") or ""
                            rg = app.get("resource_group") or app.get("resourceGroup") or ""
                            rid = app.get("resource_id") or app.get("id") or ""
                            if app_name:
                                app_hints.append(f"{app_name} (rg={rg or 'unknown'})")
                            if app_name and rid:
                                app_id_hints.append(f"{app_name}={rid}")
                        if app_hints:
                            lines.append(
                                f"container_apps ({len(container_apps)}): {', '.join(app_hints[:6])}"
                                + (" …" if len(container_apps) > 6 else "")
                            )
                        if app_id_hints:
                            lines.append(
                                "container_app_resource_ids: "
                                + "; ".join(app_id_hints[:4])
                                + (" …" if len(app_id_hints) > 4 else "")
                            )
                except Exception as exc:
                    logger.debug("SRE grounding: container app lookup failed: %s", exc)

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
            self._inventory_grounding_last_refreshed = asyncio.get_running_loop().time()
            logger.info("🗺️  SRE inventory grounding context refreshed (%d fields)", len(lines))

    async def _ensure_inventory_grounding_context(self) -> None:
        """Refresh inventory grounding when context is empty or stale."""
        now = asyncio.get_running_loop().time()
        is_stale = (now - self._inventory_grounding_last_refreshed) >= self._inventory_grounding_ttl_seconds
        if not self._inventory_grounding_context or is_stale:
            await self._refresh_inventory_grounding()

    async def _cleanup_impl(self) -> None:
        """Clean up orchestrator resources."""
        await self.message_bus.unsubscribe(self.agent_id)

    # ------------------------------------------------------------------
    # Core request handler (agent-first with MCP fallback)
    # ------------------------------------------------------------------

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """SRESubAgent-first execution with MCP fallback.

        1. Run SRESubAgent ReAct loop (grounded with inventory context)
        2. Fall back to scoped capability message if sub-agent unavailable or errors

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

        # 1. Route through SRESubAgent (ReAct loop over SRE MCP tools)
        if self._sre_sub_agent:
            try:
                return await self._run_via_sre_sub_agent(query, workflow_id, context)
            except asyncio.TimeoutError:
                logger.warning("SRESubAgent timeout, falling back")
            except Exception as exc:
                logger.error("SRESubAgent error: %s — falling back", exc, exc_info=True)

        # 2. Fallback: surface scoped message
        return await self._execute_mcp_fallback(request, workflow_id)

    # ------------------------------------------------------------------
    # SRESubAgent initialisation and execution
    # ------------------------------------------------------------------

    async def _init_sre_sub_agent(self) -> None:
        """Initialise SRESubAgent with tools from the SRE MCP server.

        Mirrors the pattern in MCPOrchestratorAgent._init_sre_agent().
        """
        if SRESubAgent is None:
            logger.warning("SRESubAgent class not available — skipping init")
            return

        try:
            sre_client = await get_sre_mcp_client()
        except SREMCPDisabledError:
            logger.info("SRE MCP server disabled — SRESubAgent not initialised")
            return
        except Exception as exc:
            logger.warning("SRE MCP client init failed: %s", exc)
            return

        sre_tools = sre_client.get_available_tools()
        if not sre_tools:
            logger.warning("No SRE tools returned by MCP client — SRESubAgent not initialised")
            return

        self._sre_sub_agent = SRESubAgent(
            tool_definitions=sre_tools,
            tool_invoker=sre_client.call_tool,
            event_callback=None,
        )
        self._sre_tool_invoker = sre_client.call_tool
        logger.info("✅ SRESubAgent initialised with %d SRE tools", len(sre_tools))

    async def _run_via_sre_sub_agent(
        self,
        query: str,
        workflow_id: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the query through SRESubAgent’s ReAct loop."""
        await self._ensure_inventory_grounding_context()

        # Prepend grounding context so the agent can resolve params without extra tool calls
        enriched = query
        if self._is_vm_health_query(query):
            enriched = (
                "[SRE execution rule]\n"
                "VM health requests are IN SCOPE for SRE. "
                "Do NOT respond out-of-scope. "
                "Use check_resource_health for VM resource IDs; if IDs are missing, "
                "ask for VM name/resource_id and continue in-scope.\n\n"
                f"{enriched}"
            )

        if self._inventory_grounding_context:
            enriched = (
                f"[Azure grounding context]\n{self._inventory_grounding_context}\n\n{enriched}"
            )

        logger.info("🏃 SRESubAgent running: %s...", query[:80])
        result = await self._sre_sub_agent.run(enriched)
        response_text = result.get("response", "")
        tools_executed = int(result.get("tool_calls_made", 0) or 0)

        if (
            self._is_vm_health_query(query)
            and tools_executed == 0
            and self._is_out_of_scope_redirect(response_text)
        ):
            logger.warning(
                "SRESubAgent returned out-of-scope for VM health; running deterministic VM health workflow"
            )
            forced = await self._run_vm_health_deterministic_workflow()
            if forced:
                response_text = forced.get("response", response_text)
                tools_executed = int(forced.get("tool_calls", 0) or 0)

        if not response_text:
            return await self._execute_mcp_fallback({"query": query}, workflow_id)

        if self._context_store:
            await self._context_store.update_workflow_context(
                workflow_id,
                {
                    "metadata": {
                        "status": "completed",
                        "intent": "sre_sub_agent",
                        "tools_executed": tools_executed,
                        "execution_source": "sre_sub_agent",
                    }
                },
            )

        return {
            "workflow_id": workflow_id,
            "intent": "sre_sub_agent",
            "tools_executed": tools_executed,
            "results": {
                "summary": {
                    "total_tools": tools_executed,
                    "successful": tools_executed if result.get("success") else 0,
                    "failed": 0 if result.get("success") else 1,
                    "skipped": 0,
                    "needs_input": 0,
                    "intent": "sre_sub_agent",
                },
                "results": [],
                "agent_content": response_text,
                "formatted_response": response_text,
            },
            "agent_metadata": {
                "thread_id": None,
                "run_id": None,
                "tools_called": [],
                "execution_source": "sre_sub_agent",
                "latency_ms": int(result.get("duration_seconds", 0) * 1000),
                "token_usage": {},
            },
        }

    async def _run_vm_health_deterministic_workflow(self) -> Optional[Dict[str, Any]]:
        """Run VM health checks directly when LLM scope handling drifts.

        This path prevents false out-of-scope responses for VM health intents.
        """
        if not self._sre_tool_invoker:
            return {
                "response": (
                    "<p>VM health is in scope for SRE, but the SRE tool invoker is unavailable right now.</p>"
                    "<p>Please retry in a few seconds.</p>"
                ),
                "tool_calls": 0,
            }

        vms = await self._discover_resources_by_type("vm", {})
        if not vms:
            return {
                "response": (
                    "<p>VM health is in scope for SRE, but no VMs were discovered in the current scope.</p>"
                    "<p>Please provide a VM name or resource group and I will run health checks.</p>"
                ),
                "tool_calls": 0,
            }

        rows: List[str] = []
        healthy = 0
        unhealthy = 0
        unknown = 0
        tool_calls = 0

        for vm in vms[:30]:
            vm_name = str(vm.get("name") or "unknown")
            vm_rg = str(vm.get("resource_group") or "unknown")
            resource_id = str(vm.get("id") or vm.get("resource_id") or "").strip()
            if not resource_id:
                continue

            tool_calls += 1
            try:
                tool_result = await self._sre_tool_invoker("check_resource_health", {"resource_id": resource_id})
            except Exception as exc:
                state = "Unknown"
                detail = f"Tool error: {exc}"
            else:
                state, detail = self._parse_vm_health_tool_result(tool_result)

            state_lower = state.lower()
            if state_lower in {"available", "healthy"}:
                healthy += 1
            elif state_lower in {"unavailable", "degraded", "unhealthy"}:
                unhealthy += 1
            else:
                unknown += 1

            rows.append(
                "<tr>"
                f"<td>{html.escape(vm_name)}</td>"
                f"<td>{html.escape(vm_rg)}</td>"
                f"<td>{html.escape(state)}</td>"
                f"<td>{html.escape(detail)}</td>"
                "</tr>"
            )

        if not rows:
            return {
                "response": (
                    "<p>VM health is in scope for SRE, but discovered VMs were missing resource IDs required for health checks.</p>"
                    "<p>Please provide a VM resource ID or VM name + resource group.</p>"
                ),
                "tool_calls": tool_calls,
            }

        response_html = (
            "<h3>VM Health Status</h3>"
            f"<p>Checked {len(rows)} VM(s): Healthy/Available={healthy}, Unhealthy/Degraded={unhealthy}, Unknown={unknown}.</p>"
            "<table>"
            "<thead><tr><th>VM</th><th>Resource Group</th><th>Health</th><th>Details</th></tr></thead>"
            "<tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        return {"response": response_html, "tool_calls": tool_calls}

    @staticmethod
    def _parse_vm_health_tool_result(tool_result: Dict[str, Any]) -> tuple[str, str]:
        """Extract health state + detail from check_resource_health tool response."""
        if not isinstance(tool_result, dict):
            return "Unknown", "Unexpected tool response"

        parsed = tool_result.get("parsed")
        payload: Optional[Dict[str, Any]] = parsed if isinstance(parsed, dict) else None

        if payload is None:
            content = tool_result.get("content")
            entries = content if isinstance(content, list) else [content]
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                try:
                    decoded = json.loads(entry)
                except Exception:
                    continue
                if isinstance(decoded, dict):
                    payload = decoded
                    break

        if not payload:
            err = str(tool_result.get("error") or "No parsed payload")
            return "Unknown", err

        if payload.get("success") is False:
            return "Unknown", str(payload.get("error") or "Health check failed")

        health_status = payload.get("health_status") if isinstance(payload.get("health_status"), dict) else {}
        availability = str(
            health_status.get("availability_state")
            or payload.get("availability_state")
            or payload.get("health_status")
            or "Unknown"
        )
        detail = str(
            health_status.get("summary")
            or health_status.get("detailed_status")
            or payload.get("error")
            or ""
        )
        return availability, detail

    @staticmethod
    def _is_out_of_scope_redirect(response_text: str) -> bool:
        """Detect common out-of-scope redirect wording from sub-agent responses."""
        text = str(response_text or "").lower()
        return (
            "main conversation" in text
            and ("out-of-scope" in text or "out of scope" in text or "please ask there" in text)
        )


    # ------------------------------------------------------------------
    # MCP Fallback Path
    # ------------------------------------------------------------------

    async def _execute_mcp_fallback(
        self,
        request: Dict[str, Any],
        workflow_id: str,
    ) -> Dict[str, Any]:
        """Return a helpful scoped message when SRESubAgent is unavailable."""
        query = request.get("query", request.get("intent", ""))
        logger.warning("MCP fallback (SRESubAgent unavailable) for: %s...", query[:80])

        fallback_html = (
            "<p>The SRE agent is currently unavailable (MCP server may still be starting up).</p>"
            "<p>This conversation specialises in operational SRE tasks:</p>"
            "<ul>"
            "<li>Resource health &amp; diagnostics</li>"
            "<li>Incident response &amp; root-cause analysis</li>"
            "<li>Performance monitoring &amp; anomaly detection</li>"
            "<li>Cost optimisation &amp; SLO management</li>"
            "<li>Security &amp; compliance checks</li>"
            "</ul>"
            "<p>For VM inventory, network topology, or general Azure queries use the "
            "<strong>main conversation</strong> instead.</p>"
        )

        await self._stream_event("progress", {
            "workflow_id": workflow_id,
            "status": "unavailable",
            "intent": "mcp_fallback",
        })

        if self._context_store:
            await self._context_store.update_workflow_context(
                workflow_id,
                {"metadata": {"status": "completed", "intent": "mcp_fallback", "tools_executed": 0}},
            )

        return {
            "workflow_id": workflow_id,
            "intent": "mcp_fallback",
            "tools_executed": 0,
            "results": {
                "summary": {
                    "total_tools": 0, "successful": 0, "failed": 0,
                    "skipped": 0, "needs_input": 0, "intent": "mcp_fallback",
                },
                "results": [],
                "formatted_response": fallback_html,
            },
            "agent_metadata": {
                "thread_id": None, "run_id": None, "tools_called": [],
                "execution_source": "mcp_fallback", "latency_ms": 0, "token_usage": {},
            },
        }

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

    @staticmethod
    def _is_vm_health_query(query: str) -> bool:
        """Return True when a query asks for VM health/status."""
        q = query.lower()
        has_vm = bool(re.search(r"\b(vms?|virtual\s+machines?)\b", q))
        has_health = bool(re.search(r"\b(health|healthy|status|unhealthy|degraded|availability)\b", q))
        return has_vm and has_health

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
    def get_capabilities(self) -> Dict[str, Any]:
        """Get orchestrator capabilities."""
        tools = self.registry.list_tools()
        agents = self.registry.list_agents()

        agent_available = bool(self._sre_sub_agent)

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
                "container_app_list": "List Container Apps in a resource group",
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
            "execution_mode": "sre_sub_agent" if agent_available else "mcp_fallback",
            "agent_diagnostics": None,
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
