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
        """Initialise SRESubAgent with tools from SRE + CVE MCP servers.

        Merges SRE and CVE tools into a unified catalog for SRESubAgent.
        Creates a routing tool invoker that dispatches to the correct MCP client.
        """
        if SRESubAgent is None:
            logger.warning("SRESubAgent class not available — skipping init")
            return

        # Initialize SRE MCP client
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

        # Initialize CVE MCP client and get CVE tools
        cve_tools = []
        cve_client = None
        try:
            from main import get_cve_mcp_client
            cve_client = await get_cve_mcp_client()
            # Get CVE tools from the MCP server
            cve_tool_names = ["search_cve", "scan_inventory", "get_patches", "trigger_remediation"]
            for tool_name in cve_tool_names:
                # Build tool definition matching MCP format
                tool_def = {
                    "name": tool_name,
                    "description": self._get_cve_tool_description(tool_name),
                    "inputSchema": self._get_cve_tool_schema(tool_name)
                }
                cve_tools.append(tool_def)
            logger.info("✅ CVE MCP client integrated with %d CVE tools", len(cve_tools))
        except Exception as exc:
            logger.warning("CVE MCP client init failed: %s — continuing without CVE tools", exc)

        # Merge SRE and CVE tools
        all_tools = sre_tools + cve_tools
        logger.info("📦 Merged tool catalog: %d SRE + %d CVE = %d total tools",
                   len(sre_tools), len(cve_tools), len(all_tools))

        # Create unified tool invoker that routes to correct MCP client
        async def unified_tool_invoker(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            """Route tool calls to correct MCP client based on tool name."""
            cve_tool_names = {"search_cve", "scan_inventory", "get_patches", "trigger_remediation"}
            if tool_name in cve_tool_names:
                if cve_client is None:
                    return {
                        "success": False,
                        "error": "CVE MCP client not available"
                    }
                # Route to CVE MCP client
                result = await cve_client.mcp.call_tool(tool_name, arguments=arguments)
                # Parse MCP response
                if hasattr(result, 'text'):
                    return json.loads(result.text)
                return result
            else:
                # Route to SRE MCP client
                return await sre_client.call_tool(tool_name, arguments)

        self._sre_sub_agent = SRESubAgent(
            tool_definitions=all_tools,
            tool_invoker=unified_tool_invoker,
            event_callback=None,
        )
        self._sre_tool_invoker = unified_tool_invoker
        logger.info("✅ SRESubAgent initialised with %d total tools (%d SRE + %d CVE)",
                   len(all_tools), len(sre_tools), len(cve_tools))

    def _get_cve_tool_description(self, tool_name: str) -> str:
        """Get description for CVE tool."""
        descriptions = {
            "search_cve": "Search CVEs by ID, keyword, severity, CVSS score, or date filters. Returns CVE summaries with metadata.",
            "scan_inventory": "Trigger CVE vulnerability scan on VM inventory. Scans VMs for known CVEs and returns scan status.",
            "get_patches": "Get patches that remediate a specific CVE. Returns patch list with KB numbers and affected VMs.",
            "trigger_remediation": "Trigger patch installation to remediate a CVE on a VM. Supports dry_run and requires confirmation."
        }
        return descriptions.get(tool_name, "CVE management tool")

    def _get_cve_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get input schema for CVE tool."""
        schemas = {
            "search_cve": {
                "type": "object",
                "properties": {
                    "cve_id": {"type": "string", "description": "CVE ID (e.g. CVE-2024-1234)"},
                    "keyword": {"type": "string", "description": "Keyword search"},
                    "severity": {"type": "string", "description": "Severity filter: CRITICAL, HIGH, MEDIUM, LOW"},
                    "cvss_min": {"type": "number", "description": "Minimum CVSS score"},
                    "cvss_max": {"type": "number", "description": "Maximum CVSS score"},
                    "published_after": {"type": "string", "description": "ISO date"},
                    "published_before": {"type": "string", "description": "ISO date"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                }
            },
            "scan_inventory": {
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string", "description": "Azure subscription ID"},
                    "resource_group": {"type": "string", "description": "Resource group (optional)"},
                    "vm_name": {"type": "string", "description": "Specific VM name (optional)"}
                },
                "required": ["subscription_id"]
            },
            "get_patches": {
                "type": "object",
                "properties": {
                    "cve_id": {"type": "string", "description": "CVE ID"},
                    "subscription_ids": {"type": "array", "items": {"type": "string"}, "description": "Subscription IDs (optional)"}
                },
                "required": ["cve_id"]
            },
            "trigger_remediation": {
                "type": "object",
                "properties": {
                    "cve_id": {"type": "string", "description": "CVE ID"},
                    "vm_name": {"type": "string", "description": "VM name"},
                    "subscription_id": {"type": "string", "description": "Subscription ID"},
                    "resource_group": {"type": "string", "description": "Resource group"},
                    "dry_run": {"type": "boolean", "description": "Preview only (default true)"},
                    "confirmed": {"type": "boolean", "description": "Execute remediation (requires confirmation)"}
                },
                "required": ["cve_id", "vm_name", "subscription_id", "resource_group"]
            }
        }
        return schemas.get(tool_name, {"type": "object"})

    async def _run_via_sre_sub_agent(
        self,
        query: str,
        workflow_id: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the query through SRESubAgent’s ReAct loop."""
        await self._ensure_inventory_grounding_context()

        # ---- Pre-flight resource validation (Phase 4) ----
        # When the user asks about a specific named resource, verify it exists in
        # inventory before spinning up the LLM ReAct loop. This saves tokens and
        # gives a fast, friendly error with suggestions when the resource is missing.
        resource_name, resource_type = self._extract_resource_name_and_type(query)
        if resource_name and self._inventory_grounding_context:
            exists, friendly_msg = self._check_specific_resource_exists(resource_name, resource_type)
            if not exists:
                if self._context_store:
                    await self._context_store.update_workflow_context(
                        workflow_id,
                        {"metadata": {"status": "completed", "intent": "resource_not_found", "tools_executed": 0}},
                    )
                return self._build_resource_not_found_response(query, workflow_id, friendly_msg)

        # ---- Deterministic workflows for specific query patterns ----
        # Cost analysis queries: route directly to cost workflow to avoid unhelpful errors
        if self._is_cost_analysis_query(query):
            logger.info("🔍 Detected cost analysis query, routing to deterministic workflow")
            forced = await self._run_cost_analysis_deterministic_workflow(query, workflow_id, context)
            if forced:
                return forced

        # Diagnostic logging queries: route directly to diagnostic workflow
        if self._is_diagnostic_logging_query(query):
            logger.info("🔍 Detected diagnostic logging query, routing to deterministic workflow")
            forced = await self._run_diagnostic_logging_deterministic_workflow(query, workflow_id, context)
            if forced:
                return forced

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
                f"[Azure grounding context]\n{self._inventory_grounding_context}\n"
                "[IMPORTANT] Only the resources listed above exist in this Azure environment. "
                "Do NOT call tools for resource names that are not in this list. "
                "If the user asks about a resource not listed above, respond that it was not found "
                "and suggest they list available resources.\n\n{enriched}"
            ).replace("{enriched}", enriched)

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

    async def _run_cost_analysis_deterministic_workflow(
        self,
        query: str,
        workflow_id: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Deterministic workflow for cost analysis queries.

        Steps:
        1. Validate subscription access via inventory
        2. Extract subscription_id from resources
        3. Route to specific cost tool based on query keywords
        4. Return formatted results or friendly error
        """
        logger.info("[SREOrchestrator] Running cost analysis deterministic workflow")

        # Step 1: Validate we have inventory access
        try:
            inventory_result = await self._discover_resources_by_type("all", {})

            if not inventory_result or len(inventory_result) == 0:
                response_html = self._format_no_resources_message(
                    "cost analysis",
                    "No Azure resources found in inventory. Cost analysis requires active subscription access."
                )
                return self._build_deterministic_response(
                    query, workflow_id, response_html, 0, "cost_analysis_no_resources"
                )

            # Extract subscription_id from first resource
            first_resource = inventory_result[0]
            subscription_id = self._extract_subscription_id(first_resource.get("id", ""))

            if not subscription_id:
                response_html = self._format_error_message(
                    "Cost Analysis",
                    "Unable to determine subscription ID from inventory."
                )
                return self._build_deterministic_response(
                    query, workflow_id, response_html, 0, "cost_analysis_error"
                )

        except Exception as e:
            logger.error(f"Inventory validation failed: {e}")
            response_html = self._format_error_message(
                "Cost Analysis",
                f"Failed to validate Azure subscription access: {str(e)}"
            )
            return self._build_deterministic_response(
                query, workflow_id, response_html, 0, "cost_analysis_error"
            )

        # Step 2: Route to specific cost tool
        query_lower = query.lower()
        tool_calls = 0

        try:
            if "orphaned resource" in query_lower or "idle resource" in query_lower:
                response_html, tool_calls = await self._execute_orphaned_resources_check(subscription_id)
            elif "recommendation" in query_lower or "rightsizing" in query_lower:
                response_html, tool_calls = await self._execute_cost_recommendations(subscription_id)
            elif "anomal" in query_lower or "spending anomal" in query_lower:
                response_html, tool_calls = await self._execute_cost_anomaly_analysis(subscription_id)
            else:
                # Default: cost by resource group or spend trend
                response_html, tool_calls = await self._execute_cost_by_resource_group(subscription_id)

            return self._build_deterministic_response(
                query, workflow_id, response_html, tool_calls, "cost_analysis"
            )

        except Exception as e:
            logger.error(f"Cost analysis execution failed: {e}")
            response_html = self._format_error_message(
                "Cost Analysis",
                f"Cost analysis failed: {str(e)}. Verify Azure Cost Management permissions."
            )
            return self._build_deterministic_response(
                query, workflow_id, response_html, tool_calls, "cost_analysis_error"
            )

    async def _execute_cost_by_resource_group(self, subscription_id: str) -> tuple[str, int]:
        """Execute get_cost_analysis for resource group breakdown."""
        params = {
            "scope": f"/subscriptions/{subscription_id}",
            "time_range": "last_30_days",
            "group_by": "ResourceGroup"
        }

        result = await self._sre_tool_invoker("get_cost_analysis", params)

        if not result or "error" in str(result).lower():
            return self._format_no_data_message(
                "Cost Analysis",
                "No cost data available. This may be a new subscription or Cost Management may not be enabled."
            ), 1

        return self._format_cost_analysis_results(result), 1

    async def _execute_orphaned_resources_check(self, subscription_id: str) -> tuple[str, int]:
        """Execute identify_orphaned_resources tool."""
        params = {"subscription_id": subscription_id}
        result = await self._sre_tool_invoker("identify_orphaned_resources", params)

        if not result or len(result) == 0:
            return self._format_success_message(
                "Orphaned Resources Check",
                "✅ No orphaned resources found. Your subscription is clean!"
            ), 1

        return self._format_orphaned_resources_results(result), 1

    async def _execute_cost_recommendations(self, subscription_id: str) -> tuple[str, int]:
        """Execute get_cost_recommendations tool."""
        params = {"subscription_id": subscription_id}
        result = await self._sre_tool_invoker("get_cost_recommendations", params)

        if not result or len(result) == 0:
            return self._format_success_message(
                "Cost Recommendations",
                "✅ No cost optimization recommendations at this time."
            ), 1

        return self._format_cost_recommendations_results(result), 1

    async def _execute_cost_anomaly_analysis(self, subscription_id: str) -> tuple[str, int]:
        """Execute analyze_cost_anomalies tool."""
        params = {
            "scope": f"/subscriptions/{subscription_id}",
            "time_range": "last_30_days"
        }
        result = await self._sre_tool_invoker("analyze_cost_anomalies", params)

        if not result or len(result) == 0:
            return self._format_success_message(
                "Cost Anomaly Analysis",
                "✅ No cost anomalies detected in the last 30 days."
            ), 1

        return self._format_cost_anomaly_results(result), 1

    def _extract_subscription_id(self, resource_id: str) -> str:
        """Extract subscription ID from Azure resource ID.

        Format: /subscriptions/{subscription_id}/resourceGroups/...
        """
        parts = resource_id.split("/")
        try:
            sub_index = parts.index("subscriptions")
            return parts[sub_index + 1]
        except (ValueError, IndexError):
            return ""

    def _build_deterministic_response(
        self,
        query: str,
        workflow_id: str,
        response_html: str,
        tool_calls: int,
        intent: str,
    ) -> Dict[str, Any]:
        """Build standardized response for deterministic workflows."""
        return {
            "workflow_id": workflow_id,
            "intent": intent,
            "tools_executed": tool_calls,
            "results": {
                "summary": {
                    "total_tools": tool_calls,
                    "successful": tool_calls,
                    "failed": 0,
                    "skipped": 0,
                    "needs_input": 0,
                    "intent": intent,
                },
                "results": [],
                "agent_content": response_html,
                "formatted_response": response_html,
            },
            "agent_metadata": {
                "thread_id": None,
                "run_id": None,
                "tools_called": [],
                "execution_source": "deterministic_workflow",
                "latency_ms": 0,
                "token_usage": {},
            },
        }

    async def _run_diagnostic_logging_deterministic_workflow(
        self,
        query: str,
        workflow_id: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Deterministic workflow for diagnostic logging queries.

        Provides examples of resources that support diagnostic logging
        with CLI commands to enable it.
        """
        logger.info("[SREOrchestrator] Running diagnostic logging deterministic workflow")

        # Discover all resources
        try:
            all_resources = await self._discover_resources_by_type("all", {})

            if not all_resources or len(all_resources) == 0:
                response_html = self._format_no_resources_message(
                    "diagnostic logging examples",
                    "No Azure resources found. Deploy resources first to enable diagnostic logging."
                )
                return self._build_deterministic_response(
                    query, workflow_id, response_html, 0, "diagnostic_logging_no_resources"
                )

        except Exception as e:
            logger.error(f"Resource discovery failed: {e}")
            response_html = self._format_error_message(
                "Diagnostic Logging",
                f"Failed to discover resources: {str(e)}"
            )
            return self._build_deterministic_response(
                query, workflow_id, response_html, 0, "diagnostic_logging_error"
            )

        # Filter resources that support diagnostic logging
        supported_types = [
            "microsoft.compute/virtualmachines",
            "microsoft.web/sites",
            "microsoft.apimanagement/service",
            "microsoft.storage/storageaccounts",
            "microsoft.sql/servers",
            "microsoft.containerservice/managedclusters",
            "microsoft.network/applicationgateways",
            "microsoft.app/containerapps"
        ]

        diagnostic_resources = [
            r for r in all_resources
            if r.get("type", "").lower() in supported_types
        ]

        if not diagnostic_resources:
            response_html = self._format_info_message(
                "Diagnostic Logging",
                f"Found {len(all_resources)} resources, but none support diagnostic logging. "
                "Deploy resources like VMs, App Services, or Container Apps to enable diagnostics."
            )
            return self._build_deterministic_response(
                query, workflow_id, response_html, 0, "diagnostic_logging_no_supported"
            )

        response_html = self._format_diagnostic_logging_examples(diagnostic_resources)
        return self._build_deterministic_response(
            query, workflow_id, response_html, 0, "diagnostic_logging"
        )

    def _format_diagnostic_logging_examples(self, resources: list) -> str:
        """Format diagnostic logging examples as HTML with CLI commands."""
        html_parts = [
            "<div class='diagnostic-examples'>",
            "<h3>🔍 Resources Supporting Diagnostic Logging</h3>",
            f"<p>Found {len(resources)} resources that can have diagnostic logging enabled:</p>",
            "<table class='table table-sm'>",
            "<thead><tr><th>Resource Name</th><th>Type</th><th>Resource Group</th><th>Example CLI Command</th></tr></thead>",
            "<tbody>"
        ]

        for resource in resources[:10]:  # Limit to 10 examples
            name = html.escape(resource.get("name", "Unknown"))
            rg = html.escape(resource.get("resourceGroup", "Unknown"))
            resource_id = html.escape(resource.get("id", ""))
            resource_type = html.escape(resource.get("type", "Unknown"))

            # Generate example CLI command
            cli_example = f"az monitor diagnostic-settings create --resource {resource_id} --workspace {{workspace-id}} --logs '[{{\"category\":\"AuditEvent\",\"enabled\":true}}]'"

            html_parts.append(
                f"<tr>"
                f"<td><code>{name}</code></td>"
                f"<td>{resource_type}</td>"
                f"<td>{rg}</td>"
                f"<td><small><code>{html.escape(cli_example)}</code></small></td>"
                f"</tr>"
            )

        html_parts.extend([
            "</tbody></table>",
            f"<p><em>Showing {min(len(resources), 10)} of {len(resources)} resources.</em></p>",
            f"<p><strong>Next steps:</strong></p>",
            "<ol>",
            "<li>Create or identify a Log Analytics workspace</li>",
            "<li>Replace <code>{{workspace-id}}</code> with your workspace resource ID</li>",
            "<li>Adjust log categories based on resource type</li>",
            "<li>Run the command via Azure CLI or Cloud Shell</li>",
            "</ol>",
            "</div>"
        ])

        return "".join(html_parts)

    @staticmethod
    def _is_out_of_scope_redirect(response_text: str) -> bool:
        """Detect common out-of-scope redirect wording from sub-agent responses."""
        text = str(response_text or "").lower()
        return (
            "main conversation" in text
            and ("out-of-scope" in text or "out of scope" in text or "please ask there" in text)
        )

    # ------------------------------------------------------------------
    # HTML Formatting Helpers
    # ------------------------------------------------------------------

    def _format_no_resources_message(self, query_type: str, message: str) -> str:
        """Format friendly message when no resources exist."""
        return f"""
        <div class='alert alert-info' role='alert'>
            <h4 class='alert-heading'><i class='fas fa-info-circle me-2'></i>No Resources Available</h4>
            <p><strong>Query:</strong> {html.escape(query_type)}</p>
            <p>{html.escape(message)}</p>
            <hr>
            <p class='mb-0'><em>Tip: Deploy Azure resources first, then retry this query.</em></p>
        </div>
        """

    def _format_no_data_message(self, title: str, message: str) -> str:
        """Format friendly message when data is not available."""
        return f"""
        <div class='alert alert-warning' role='alert'>
            <h4 class='alert-heading'><i class='fas fa-exclamation-triangle me-2'></i>No Data Available</h4>
            <p><strong>Context:</strong> {html.escape(title)}</p>
            <p>{html.escape(message)}</p>
            <hr>
            <p class='mb-0'><em>Tip: Check Azure Cost Management access and subscription permissions.</em></p>
        </div>
        """

    def _format_success_message(self, title: str, message: str) -> str:
        """Format success message."""
        return f"""
        <div class='alert alert-success' role='alert'>
            <h4 class='alert-heading'><i class='fas fa-check-circle me-2'></i>{html.escape(title)}</h4>
            <p>{html.escape(message)}</p>
        </div>
        """

    def _format_error_message(self, title: str, message: str) -> str:
        """Format error message."""
        return f"""
        <div class='alert alert-danger' role='alert'>
            <h4 class='alert-heading'><i class='fas fa-times-circle me-2'></i>Error: {html.escape(title)}</h4>
            <p>{html.escape(message)}</p>
            <hr>
            <p class='mb-0'><em>Tip: Verify Azure credentials and permissions in the MCP server configuration.</em></p>
        </div>
        """

    def _format_info_message(self, title: str, message: str) -> str:
        """Format informational message."""
        return f"""
        <div class='alert alert-info' role='alert'>
            <h4 class='alert-heading'><i class='fas fa-info-circle me-2'></i>{html.escape(title)}</h4>
            <p>{html.escape(message)}</p>
        </div>
        """

    def _format_cost_analysis_results(self, result: dict) -> str:
        """Format cost analysis results as HTML table."""
        html_parts = [
            "<div class='cost-analysis-results'>",
            "<h3><i class='fas fa-chart-line me-2'></i>Cost Analysis by Resource Group</h3>"
        ]

        # Parse result (structure from get_cost_analysis tool)
        cost_breakdown = result.get("cost_breakdown", [])
        total = result.get("total_cost", 0)

        if not cost_breakdown:
            return self._format_no_data_message("Cost Analysis", "No cost data available for this subscription.")

        html_parts.extend([
            "<table class='table table-striped table-hover'>",
            "<thead><tr><th>Resource Group</th><th>Cost (USD)</th><th>% of Total</th></tr></thead>",
            "<tbody>"
        ])

        for item in cost_breakdown[:20]:  # Top 20 groups
            name = html.escape(item.get("name", "Unknown"))
            cost = item.get("cost", 0)
            percentage = (cost / total * 100) if total > 0 else 0
            html_parts.append(
                f"<tr>"
                f"<td><strong>{name}</strong></td>"
                f"<td>${cost:.2f}</td>"
                f"<td>{percentage:.1f}%</td>"
                f"</tr>"
            )

        html_parts.extend([
            "</tbody>",
            f"<tfoot><tr><th>Total</th><th>${total:.2f}</th><th>100%</th></tr></tfoot>",
            "</table>",
            "</div>"
        ])

        return "".join(html_parts)

    def _format_orphaned_resources_results(self, result: list) -> str:
        """Format orphaned resources as HTML table."""
        html_parts = [
            "<div class='orphaned-resources-results'>",
            "<h3><i class='fas fa-trash-alt me-2'></i>Orphaned Resources</h3>",
            f"<p>Found {len(result)} orphaned resources that may be safe to delete:</p>",
            "<table class='table table-sm table-striped'>",
            "<thead><tr><th>Resource Name</th><th>Type</th><th>Resource Group</th></tr></thead>",
            "<tbody>"
        ]

        for resource in result[:50]:  # Limit to 50
            name = html.escape(resource.get("name", "Unknown"))
            rtype = html.escape(resource.get("type", "Unknown"))
            rg = html.escape(resource.get("resourceGroup", "Unknown"))
            html_parts.append(f"<tr><td><code>{name}</code></td><td>{rtype}</td><td>{rg}</td></tr>")

        html_parts.extend([
            "</tbody></table>",
            f"<p><em>Showing {min(len(result), 50)} of {len(result)} resources.</em></p>",
            "</div>"
        ])

        return "".join(html_parts)

    def _format_cost_recommendations_results(self, result: list) -> str:
        """Format cost recommendations as HTML list."""
        html_parts = [
            "<div class='cost-recommendations-results'>",
            "<h3><i class='fas fa-lightbulb me-2'></i>Cost Optimization Recommendations</h3>",
            "<ul class='list-group'>"
        ]

        for rec in result[:20]:  # Top 20 recommendations
            title = html.escape(rec.get("title", "Recommendation"))
            impact = html.escape(rec.get("impact", "Unknown"))
            html_parts.append(
                f"<li class='list-group-item'>"
                f"<strong>{title}</strong><br>"
                f"<small class='text-muted'>Potential impact: {impact}</small>"
                f"</li>"
            )

        html_parts.extend([
            "</ul>",
            f"<p class='mt-2'><em>Showing {min(len(result), 20)} of {len(result)} recommendations.</em></p>",
            "</div>"
        ])

        return "".join(html_parts)

    def _format_cost_anomaly_results(self, result: dict) -> str:
        """Format cost anomalies as HTML table."""
        html_parts = [
            "<div class='cost-anomaly-results'>",
            "<h3><i class='fas fa-exclamation-triangle me-2'></i>Cost Anomalies (Last 30 Days)</h3>"
        ]

        anomalies = result.get("anomalies", [])

        if not anomalies:
            return self._format_success_message("Cost Anomaly Analysis", "✅ No cost anomalies detected.")

        html_parts.extend([
            "<table class='table table-sm table-striped'>",
            "<thead><tr><th>Date</th><th>Service</th><th>Expected</th><th>Actual</th><th>Variance</th></tr></thead>",
            "<tbody>"
        ])

        for anomaly in anomalies[:20]:
            date = html.escape(anomaly.get("date", "Unknown"))
            service = html.escape(anomaly.get("service", "Unknown"))
            expected = anomaly.get("expected_cost", 0)
            actual = anomaly.get("actual_cost", 0)
            variance_pct = anomaly.get("variance_percentage", 0)

            color = "text-danger" if variance_pct > 0 else "text-success"
            html_parts.append(
                f"<tr>"
                f"<td>{date}</td>"
                f"<td>{service}</td>"
                f"<td>${expected:.2f}</td>"
                f"<td>${actual:.2f}</td>"
                f"<td class='{color}'><strong>{variance_pct:+.1f}%</strong></td>"
                f"</tr>"
            )

        html_parts.extend([
            "</tbody></table>",
            "</div>"
        ])

        return "".join(html_parts)

    # ------------------------------------------------------------------
    # Resource Validation (Phase 4)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_resource_name_and_type(query: str) -> tuple[Optional[str], Optional[str]]:
        """Extract a specific resource name and type from a user query.

        Returns (resource_name, resource_type) where resource_type is one of
        'container_app', 'vm', or None when no specific resource is identifiable.

        Examples:
            "health of my-app container app"   → ("my-app", "container_app")
            "status of web-vm01"               → ("web-vm01", "vm")
            "show all container apps"          → (None, "container_app")
            "check resource health"            → (None, None)
        """
        q = query.lower()
        generic_name_tokens = {
            "my",
            "our",
            "your",
            "their",
            "the",
            "a",
            "an",
            "all",
            "any",
            "this",
            "that",
            "these",
            "those",
        }

        # -- Container App patterns --
        # "health of <name>" / "status of <name> container app"
        ca_name_patterns = [
            r"(?:health|status|check|diagnose|restart|scale)\s+(?:of\s+)?([a-z0-9][\w-]{1,62})\s+container[\s-]?apps?\b",
            r"container[\s-]?apps?\s+([a-z0-9][\w-]{1,62})\b",
            r"\b([a-z0-9][\w-]{1,62})\s+container[\s-]?apps?\b",
        ]
        for pattern in ca_name_patterns:
            m = re.search(pattern, q)
            if m:
                candidate = m.group(1).strip()
                if candidate in generic_name_tokens:
                    continue
                return candidate, "container_app"

        # -- VM patterns --
        # "health of <name> vm" / "<name>-vm" / "virtual machine <name>"
        vm_name_patterns = [
            r"(?:health|status|check|diagnose)\s+(?:of\s+)?([a-z0-9][\w-]{1,62})\s+(?:vm|virtual[\s-]?machine)",
            r"virtual[\s-]?machine\s+([a-z0-9][\w-]{1,62})\b",
            r"\b([a-z0-9][\w-]{2,62}(?:-vm\d*|vm\d+))\b",
        ]
        for pattern in vm_name_patterns:
            m = re.search(pattern, q)
            if m:
                candidate = m.group(1).strip()
                if candidate in generic_name_tokens:
                    continue
                return candidate, "vm"

        # -- Detect resource type without a specific name --
        if re.search(r"\bcontainer[\s-]?apps?\b|\bcontainerapps?\b", q):
            return None, "container_app"
        if re.search(r"\b(vms?|virtual[\s-]?machines?)\b", q):
            return None, "vm"

        return None, None

    def _check_specific_resource_exists(
        self, resource_name: str, resource_type: Optional[str]
    ) -> tuple[bool, str]:
        """Pre-flight check: verify a named resource is in the cached inventory.

        Uses the in-memory grounding context (populated from resource_inventory_client)
        so this is a zero-cost O(n) string scan — no extra Azure API calls.

        Args:
            resource_name:  Normalised (lower-case) resource name from the query.
            resource_type:  'container_app', 'vm', or None (any type).

        Returns:
            (exists, friendly_message)
            - exists=True means the name was found; caller should proceed normally.
            - exists=False means the name is NOT in inventory; friendly_message is ready
              to return to the user with zero tool calls.
        """
        ctx = self._inventory_grounding_context
        if not ctx:
            # No inventory data — can't validate, let the agent try
            return True, ""

        name_lower = resource_name.lower()

        # Check the grounding context for the resource name
        # The context lines look like:
        #   container_apps (3): my-app (rg=prod-rg), api-svc (rg=prod-rg) …
        #   container_app_resource_ids: my-app=/subscriptions/…
        ctx_lower = ctx.lower()
        if name_lower in ctx_lower:
            return True, ""

        # Not found — build a friendly, informative error
        rtype_label = self._get_resource_type_label(resource_type or "") if resource_type else "resource"

        # Collect known names of the same type from grounding context for suggestions
        known_names: List[str] = []
        if resource_type == "container_app":
            m = re.search(r"container_apps\s*\(\d+\)\s*:\s*([^\n]+)", ctx)
            if m:
                # Parse "name (rg=xxx), name2 (rg=yyy)"
                for part in m.group(1).split(","):
                    part = part.strip()
                    n = re.match(r"([^\s(]+)", part)
                    if n:
                        known_names.append(n.group(1).strip())
        elif resource_type == "vm":
            # VMs may appear in grounding context under cached_resource_types or future lines
            for line in ctx.splitlines():
                if "microsoft.compute/virtualmachines" in line.lower():
                    m = re.search(r"\((\d+)\)", line)
                    if m:
                        known_names.append(f"({m.group(1)} VMs in inventory)")

        # Build message
        msg_parts = [
            f"<p>❌ <strong>{html.escape(resource_name)}</strong> was not found in the current Azure inventory "
            f"({rtype_label}).</p>"
        ]
        if known_names:
            escaped = [html.escape(n) for n in known_names[:6]]
            msg_parts.append(
                f"<p>Known {rtype_label}s in scope: <code>{', '.join(escaped)}</code></p>"
            )
        msg_parts.append(
            "<p>Please verify the resource name and try again, or ask to "
            "<em>list all resources</em> to see what's available.</p>"
        )

        friendly_msg = "\n".join(msg_parts)
        logger.info(
            "Pre-flight resource check: '%s' (%s) not found in inventory — short-circuiting",
            resource_name, resource_type,
        )
        return False, friendly_msg

    def _build_resource_not_found_response(
        self, query: str, workflow_id: str, friendly_msg: str
    ) -> Dict[str, Any]:
        """Build the standard orchestrator response dict for a not-found resource."""
        return {
            "workflow_id": workflow_id,
            "intent": "resource_not_found",
            "tools_executed": 0,
            "results": {
                "summary": {
                    "total_tools": 0,
                    "successful": 0,
                    "failed": 0,
                    "skipped": 1,
                    "needs_input": 0,
                    "intent": "resource_not_found",
                },
                "results": [],
                "agent_content": friendly_msg,
                "formatted_response": friendly_msg,
            },
            "agent_metadata": {
                "thread_id": None,
                "run_id": None,
                "tools_called": [],
                "execution_source": "resource_validation",
                "latency_ms": 0,
                "token_usage": {},
            },
        }

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

    @staticmethod
    def _is_cost_analysis_query(query: str) -> bool:
        """Detect if query requires cost analysis workflow.

        Matches patterns like:
        - "cost by resource group"
        - "30-day spend trend"
        - "cost recommendations"
        - "orphaned resources"
        - "spending anomalies"
        """
        query_lower = query.lower()
        cost_keywords = [
            "cost by resource group",
            "spend trend",
            "cost analysis",
            "spending",
            "cost recommendation",
            "cost optimization",
            "orphaned resource",
            "idle resource",
            "cost anomal",
            "reduce cost",
            "rightsizing",
            "azure spend",
            "total cost",
            "cost breakdown",
        ]
        return any(keyword in query_lower for keyword in cost_keywords)

    @staticmethod
    def _is_diagnostic_logging_query(query: str) -> bool:
        """Detect if query requires diagnostic logging workflow.

        Matches patterns like:
        - "enable diagnostic logging"
        - "diagnostic settings"
        - "check diagnostic"
        """
        query_lower = query.lower()
        diagnostic_keywords = [
            "enable diagnostic",
            "diagnostic logging",
            "diagnostic setting",
            "check diagnostic",
            "configure diagnostic",
            "set up diagnostic",
        ]
        return any(keyword in query_lower for keyword in diagnostic_keywords)

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
