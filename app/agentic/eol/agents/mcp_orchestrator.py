#!/usr/bin/env python3
"""AsyncAzureOpenAI-powered orchestrator for Azure MCP Server tools.

This orchestrator extends BaseOrchestrator and implements the ReAct loop
pattern with optional pipeline routing modes.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

try:
    from app.agentic.eol.agents.base_orchestrator import BaseOrchestrator
    from app.agentic.eol.agents.orchestrator_models import (
        ExecutionPlan,
        OrchestratorResult,
        PlanStep,
    )
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.cache_stats_manager import cache_stats_manager
    from app.agentic.eol.utils.response_formatter import ResponseFormatter
except ModuleNotFoundError:  # pragma: no cover - packaged runtime fallback
    from agents.base_orchestrator import BaseOrchestrator
    from agents.orchestrator_models import (
        ExecutionPlan,
        OrchestratorResult,
        PlanStep,
    )
    from utils.logger import get_logger  # type: ignore[import-not-found]
    from utils.cache_stats_manager import cache_stats_manager  # type: ignore[import-not-found]
    from utils.response_formatter import ResponseFormatter  # type: ignore[import-not-found]

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

_workbook_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.monitor_mcp_client import get_workbook_mcp_client  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _workbook_mcp_import_error = exc
    try:
        from utils.monitor_mcp_client import get_workbook_mcp_client  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _workbook_mcp_import_error = fallback_exc
        get_workbook_mcp_client = None  # type: ignore[assignment]

_sre_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.sre_mcp_client import get_sre_mcp_client, SREMCPDisabledError  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _sre_mcp_import_error = exc
    try:
        from utils.sre_mcp_client import get_sre_mcp_client, SREMCPDisabledError  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _sre_mcp_import_error = fallback_exc
        get_sre_mcp_client = None  # type: ignore[assignment]

        class SREMCPDisabledError(RuntimeError):  # type: ignore[override]
            """Fallback disabled error when SRE MCP helper is unavailable."""

_network_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.network_mcp_client import get_network_mcp_client, NetworkMCPDisabledError  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _network_mcp_import_error = exc
    try:
        from utils.network_mcp_client import get_network_mcp_client, NetworkMCPDisabledError  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _network_mcp_import_error = fallback_exc
        get_network_mcp_client = None  # type: ignore[assignment]

        class NetworkMCPDisabledError(RuntimeError):  # type: ignore[override]
            """Fallback disabled error when Network MCP helper is unavailable."""

_compute_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.compute_mcp_client import get_compute_mcp_client, ComputeMCPDisabledError  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _compute_mcp_import_error = exc
    try:
        from utils.compute_mcp_client import get_compute_mcp_client, ComputeMCPDisabledError  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _compute_mcp_import_error = fallback_exc
        get_compute_mcp_client = None  # type: ignore[assignment]

        class ComputeMCPDisabledError(RuntimeError):  # type: ignore[override]
            """Fallback disabled error when Compute MCP helper is unavailable."""

_storage_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.storage_mcp_client import get_storage_mcp_client, StorageMCPDisabledError  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _storage_mcp_import_error = exc
    try:
        from utils.storage_mcp_client import get_storage_mcp_client, StorageMCPDisabledError  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _storage_mcp_import_error = fallback_exc
        get_storage_mcp_client = None  # type: ignore[assignment]

        class StorageMCPDisabledError(RuntimeError):  # type: ignore[override]
            """Fallback disabled error when Storage MCP helper is unavailable."""

_patch_mcp_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.patch_mcp_client import get_patch_mcp_client  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _patch_mcp_import_error = exc
    try:
        from utils.patch_mcp_client import get_patch_mcp_client  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _patch_mcp_import_error = fallback_exc
        get_patch_mcp_client = None  # type: ignore[assignment]

_sre_inventory_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.sre_inventory_integration import get_sre_inventory_integration  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _sre_inventory_import_error = exc
    try:
        from utils.sre_inventory_integration import get_sre_inventory_integration  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _sre_inventory_import_error = fallback_exc
        get_sre_inventory_integration = None  # type: ignore[assignment]

_resource_inventory_import_error: Optional[BaseException] = None
try:
    from app.agentic.eol.utils.resource_inventory_client import get_resource_inventory_client  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _resource_inventory_import_error = exc
    try:
        from utils.resource_inventory_client import get_resource_inventory_client  # type: ignore[import-not-found]
    except ModuleNotFoundError as fallback_exc:
        _resource_inventory_import_error = fallback_exc
        get_resource_inventory_client = None  # type: ignore[assignment]

try:
    from app.agentic.eol.utils.mcp_host import MCPHost  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.mcp_host import MCPHost  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        MCPHost = None  # type: ignore[assignment]

try:
    from app.agentic.eol.agents.monitor_agent import MonitorAgent  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from agents.monitor_agent import MonitorAgent  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        MonitorAgent = None  # type: ignore[assignment]

try:
    from app.agentic.eol.agents.sre_sub_agent import SRESubAgent, build_sre_meta_tool  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from agents.sre_sub_agent import SRESubAgent, build_sre_meta_tool  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        SRESubAgent = None  # type: ignore[assignment]
        build_sre_meta_tool = None  # type: ignore[assignment]

try:
    from app.agentic.eol.agents.patch_sub_agent import PatchSubAgent, build_patch_meta_tool  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from agents.patch_sub_agent import PatchSubAgent, build_patch_meta_tool  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        PatchSubAgent = None  # type: ignore[assignment]
        build_patch_meta_tool = None  # type: ignore[assignment]

try:
    from app.agentic.eol.utils.tool_router import ToolRouter  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.tool_router import ToolRouter  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        ToolRouter = None  # type: ignore[assignment]

try:
    from app.agentic.eol.utils.tool_embedder import ToolEmbedder  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.tool_embedder import ToolEmbedder  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        ToolEmbedder = None  # type: ignore[assignment]

# Pipeline Router + ToolRetriever (Phase 4 — shadow mode only when MCP_PIPELINE_SHADOW=true)
_pipeline_router_import_error: Optional[str] = None
try:
    from app.agentic.eol.utils.router import Router as PipelineRouter  # type: ignore[import-not-found]
    from app.agentic.eol.utils.tool_retriever import ToolRetriever as PipelineToolRetriever  # type: ignore[import-not-found]
except ModuleNotFoundError:
    try:
        from utils.router import Router as PipelineRouter  # type: ignore[import-not-found]
        from utils.tool_retriever import ToolRetriever as PipelineToolRetriever  # type: ignore[import-not-found]
    except ModuleNotFoundError as _e:
        PipelineRouter = None  # type: ignore[assignment,misc]
        PipelineToolRetriever = None  # type: ignore[assignment,misc]
        _pipeline_router_import_error = str(_e)

# Phase 6 — full pipeline: Planner + Executor + Verifier + ResponseComposer
_pipeline_full_import_error: Optional[str] = None
try:
    from app.agentic.eol.utils.planner import Planner as PipelinePlanner  # type: ignore[import-not-found]
    from app.agentic.eol.utils.executor import Executor as PipelineExecutor, StepResult as PipelineStepResult, ExecutionResult as PipelineExecutionResult  # type: ignore[import-not-found]
    from app.agentic.eol.utils.verifier import Verifier as PipelineVerifier  # type: ignore[import-not-found]
    from app.agentic.eol.utils.response_composer import ResponseComposer as PipelineResponseComposer  # type: ignore[import-not-found]
    from app.agentic.eol.utils.resource_inventory_service import (  # type: ignore[import-not-found]
        ResourceInventoryService as PipelineInventoryService,
        get_resource_inventory_service as get_pipeline_inventory_service,
    )
except ModuleNotFoundError:
    try:
        from utils.planner import Planner as PipelinePlanner  # type: ignore[import-not-found]
        from utils.executor import Executor as PipelineExecutor, StepResult as PipelineStepResult, ExecutionResult as PipelineExecutionResult  # type: ignore[import-not-found]
        from utils.verifier import Verifier as PipelineVerifier  # type: ignore[import-not-found]
        from utils.response_composer import ResponseComposer as PipelineResponseComposer  # type: ignore[import-not-found]
        from utils.resource_inventory_service import (  # type: ignore[import-not-found]
            ResourceInventoryService as PipelineInventoryService,
            get_resource_inventory_service as get_pipeline_inventory_service,
        )
    except ModuleNotFoundError as _e:
        PipelinePlanner = None  # type: ignore[assignment,misc]
        PipelineExecutor = None  # type: ignore[assignment,misc]
        PipelineStepResult = None  # type: ignore[assignment,misc]
        PipelineExecutionResult = None  # type: ignore[assignment,misc]
        PipelineVerifier = None  # type: ignore[assignment,misc]
        PipelineResponseComposer = None  # type: ignore[assignment,misc]
        PipelineInventoryService = None  # type: ignore[assignment,misc]
        get_pipeline_inventory_service = None  # type: ignore[assignment]
        _pipeline_full_import_error = str(_e)


if TYPE_CHECKING:  # pragma: no cover - typing support only
    from azure.identity import DefaultAzureCredential as DefaultAzureCredentialType  # type: ignore[import-not-found]
else:  # pragma: no cover - runtime branch
    DefaultAzureCredentialType = Any

# Internal message classes used as the common protocol between OpenAI SDK
# responses and the ReAct loop.  These are lightweight data containers.
class TextContent:
    """Lightweight text content container."""
    def __init__(self, text: Optional[str] = None, **_: Any) -> None:
        self.text = text or ""
        self.type = "text"
    
    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        result = {"type": self.type, "text": self.text}
        if exclude_none:
            return {k: v for k, v in result.items() if v is not None}
        return result

class FunctionCallContent:
    """Represents a tool/function call requested by the LLM."""
    def __init__(self, *, call_id: Optional[str] = None, name: str = "", arguments: Any = None, **_: Any) -> None:
        self.call_id = call_id or f"call_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.arguments = arguments or {}
        self.type = "function_call"
    
    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "call_id": self.call_id,
            "name": self.name,
            "arguments": self.arguments
        }
        if exclude_none:
            return {k: v for k, v in result.items() if v is not None}
        return result

class FunctionResultContent:
    """Represents the result returned by a tool/function call."""
    def __init__(self, *, call_id: str, result: Any = None, **_: Any) -> None:
        self.call_id = call_id
        self.result = result
        self.type = "function_result"
    
    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        result_dict = {
            "type": self.type,
            "call_id": self.call_id,
            "result": self.result
        }
        if exclude_none:
            return {k: v for k, v in result_dict.items() if v is not None}
        return result_dict

class ChatMessage:
    """Internal chat message container."""
    def __init__(
        self,
        *,
        role: str,
        text: Optional[str] = None,
        contents: Optional[Sequence[Any]] = None,
        author_name: Optional[str] = None,
        additional_properties: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> None:
        self.role = role
        base_contents = list(contents or [])
        if text:
            base_contents.append(TextContent(text=text))
        self.contents = base_contents
        self.text = text or ""
        self.author_name = author_name
        self.additional_properties = additional_properties or {}

class ChatResponse:
    """Internal chat response wrapper."""
    def __init__(self, messages: Optional[Sequence[ChatMessage]] = None, **_: Any) -> None:
        self.messages = list(messages or [])

try:
    from azure.identity import DefaultAzureCredential  # type: ignore[import]
    _DEFAULT_CREDENTIAL_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    DefaultAzureCredential = None  # type: ignore[assignment]
    _DEFAULT_CREDENTIAL_AVAILABLE = False


logger = get_logger(__name__, level=os.getenv("LOG_LEVEL", "DEBUG"))


# Shared formatter instance
_response_formatter = ResponseFormatter()


# Log package availability at module load time
logger.info(
    "MCP Orchestrator dependencies: Azure Identity=%s",
    _DEFAULT_CREDENTIAL_AVAILABLE,
)


class MCPOrchestratorAgent(BaseOrchestrator):
    """High-level Azure MCP orchestrator using AsyncAzureOpenAI with ReAct loop.

    Extends BaseOrchestrator to leverage shared infrastructure while maintaining
    the sophisticated ReAct loop and pipeline routing capabilities.
    """

    _SYSTEM_PROMPT = """You are the Azure modernization co-pilot for enterprise operations teams.
You have access to Azure MCP tools that provide REAL-TIME data from Azure services.
Each tool's description tells you WHEN to use it — follow those descriptions to pick the right tool.

CRITICAL RULE — NO FABRICATION:
You MUST call a tool before presenting ANY Azure resource data.
NEVER generate fake resource names, subscription IDs, or example data.
If no tool exists for the request, say so. If a tool call fails, report the error.

SAFETY — DESTRUCTIVE OPERATIONS:
Before executing any tool that creates, updates, deletes, or deploys resources:
1. Gather all required information first via tool calls.
2. Present a COMPLETE plan to the user in ONE message.
3. Ask for confirmation ONCE and WAIT — do NOT execute without approval.

WORKFLOW:
1. Call the appropriate tool(s) FIRST to fetch real data.
2. Wait for tool results before responding.
3. Format ONLY the data returned by tools into your response.

LISTING QUERIES (show/list/display my X):
- For any "show my X", "list X", or "display X" request: call ONE list/enumerate tool and immediately respond with that result.
- Do NOT fan out — do NOT loop through each returned item calling per-item detail tools.
- If the user explicitly asks for details on a specific item (by name or ID), THEN call a detail tool for that one item only.

AZURE CLI:
→ For Log Analytics KQL queries use --analytics-query (NOT --query).
→ Container Apps use 'az containerapp' commands via azure_cli_execute_command.
→ VMs do NOT support diagnostic settings — use Azure Monitor Agent (AMA) instead.

FORMATTING:
- Return responses as raw HTML (no markdown, no backticks).
- Use an HTML <table> when presenting structured data; follow with a <p> summary.
- Single-value metrics: use an HTML progress bar with gradient colors.
- Time-series metrics (multiple timestamps): render a Chart.js line chart with a unique canvas id.
  Colors: CPU=#2196F3, Memory=#4CAF50, Disk=#FF9800, Network=#9C27B0, Requests=#E91E63, Latency=#00BCD4.
- NEVER nest <script> inside <pre> or markdown — emit live HTML only.
- Your entire response must be valid HTML insertable into a webpage."""

    def _build_dynamic_system_prompt(self, tool_definitions: List[Dict[str, Any]], tool_source_map: Dict[str, str]) -> str:
        """Build a dynamic system prompt appending tenant/subscription grounding and tool-source summary.

        Grounding order:
          1. AZURE CONTEXT — tenant_id + subscription_id injected from env/config so the LLM
             never needs to fabricate or discover them via a tool call.
          2. RESOURCE INVENTORY CONTEXT — compact resource-group / resource-type summary.
          3. AVAILABLE TOOL SOURCES — counts only (~50 tokens).
        """
        base_prompt = MCPOrchestratorAgent._SYSTEM_PROMPT

        # ── 0. AZURE CONTEXT — tenant / subscription grounding ────────────
        try:
            from utils.config import config as _cfg
        except ModuleNotFoundError:
            try:
                from app.agentic.eol.utils.config import config as _cfg  # type: ignore[import-not-found]
            except ModuleNotFoundError:
                _cfg = None  # type: ignore[assignment]

        azure_context_lines: List[str] = []
        if _cfg is not None:
            tenant_id = getattr(getattr(_cfg, "azure", None), "tenant_id", "") or os.getenv("AZURE_TENANT_ID", os.getenv("TENANT_ID", ""))
            subscription_id = getattr(getattr(_cfg, "azure", None), "subscription_id", "") or os.getenv("SUBSCRIPTION_ID", os.getenv("AZURE_SUBSCRIPTION_ID", ""))
        else:
            tenant_id = os.getenv("AZURE_TENANT_ID", os.getenv("TENANT_ID", ""))
            subscription_id = os.getenv("SUBSCRIPTION_ID", os.getenv("AZURE_SUBSCRIPTION_ID", ""))

        if tenant_id:
            azure_context_lines.append(f"  • Tenant ID: {tenant_id}")
        if subscription_id:
            azure_context_lines.append(f"  • Default Subscription ID: {subscription_id}")

        if azure_context_lines:
            azure_context_section = (
                "\n\nAZURE CONTEXT (pre-resolved from environment — trust these values):\n"
                + "\n".join(azure_context_lines)
                + "\n  • subscription_id is auto-populated into tool arguments by the orchestrator — you do NOT need to call a subscriptions/list tool solely to obtain the subscription ID."
            )
        else:
            azure_context_section = ""

        # ── 1. RESOURCE INVENTORY CONTEXT (async-populated, may be empty on first call) ──
        inventory_section = ""
        grounding = getattr(self, "_inventory_grounding_context", "")
        if grounding:
            inventory_section = "\n\nRESOURCE INVENTORY CONTEXT (use to resolve tool parameters without extra tool calls):\n" + grounding

        if not tool_definitions:
            return base_prompt + azure_context_section + inventory_section

        # ── 2. Group tools by source ──────────────────────────────────────
        source_labels = {
            "azure":     "Azure MCP Server",
            "azure_cli": "Azure CLI Executor",
            "os_eol":    "OS EOL Server",
            "inventory": "Inventory Server",
            "monitor":   "Azure Monitor Community",
            "sre":       "Azure SRE Agent",
            "meta":      "Orchestration Meta-tools",
        }

        tools_by_source: Dict[str, List[Dict[str, Any]]] = {}
        for tool in tool_definitions:
            fn = tool.get("function", {})
            name = fn.get("name", "")
            source = tool_source_map.get(name, "unknown")
            tools_by_source.setdefault(source, []).append(tool)

        # ── 3. AVAILABLE TOOL SOURCES summary (counts only, ~50 tokens) ──
        catalog_lines = [
            f"  • {source_labels.get(src, src)}: {len(tools)} tools"
            for src, tools in tools_by_source.items()
        ]
        catalog_section = "\n\nAVAILABLE TOOL SOURCES:\n" + "\n".join(catalog_lines)

        return base_prompt + azure_context_section + inventory_section + catalog_section

    def _build_openai_tools_payload(self, tool_definitions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build OpenAI tool payload from all available tool definitions."""
        if not tool_definitions:
            return []

        payload: List[Dict[str, Any]] = []
        for tool in tool_definitions:
            function_schema = tool.get("function", tool)
            if not isinstance(function_schema, dict) or not function_schema.get("name"):
                continue
            payload.append({"type": "function", "function": function_schema})

        if len(payload) > self._max_openai_tools:
            logger.warning(
                "⚠️ Tool payload exceeds Azure OpenAI limit (%d > %d); truncating payload",
                len(payload),
                self._max_openai_tools,
            )
            payload = payload[: self._max_openai_tools]

        logger.info("Tool catalog: %d tools loaded", len(payload))
        return payload

    def _select_compact_tools_for_query(
        self,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Pick a compact, relevance-biased subset of candidate tools.

        .. deprecated::
            Routing now goes through :meth:`_get_active_tools_for_iteration`
            which delegates to :class:`ToolRouter`.  This method is kept only
            as a local heuristic fallback when the ToolRouter is unavailable.
        """
        if not candidates:
            return []

        import re

        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9_]+", (query or "").lower())
            if len(token) >= 3
        }

        scored: List[Tuple[int, Dict[str, Any]]] = []
        for tool in candidates:
            function = tool.get("function", tool)
            if not isinstance(function, dict):
                continue

            name = str(function.get("name", ""))
            description = str(function.get("description", ""))
            corpus = f"{name} {description}".lower()

            score = 0
            if query_tokens and corpus:
                score += sum(1 for token in query_tokens if token in corpus)

            if name.startswith(("list_", "get_", "search_", "describe_")):
                score += 1
            if name in {"monitor_agent", "sre_agent", "describe_capabilities", "get_prompt_examples"}:
                score += 2

            scored.append((score, tool))

        if not scored:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        return [tool for _, tool in scored[: max(1, limit)]]

    def _enforce_routed_tool_budget(
        self,
        active_tools: Sequence[Dict[str, Any]],
        full_catalog_count: int,
    ) -> List[Dict[str, Any]]:
        """Hard-cap routed tools to ``_routed_tool_budget``.

        The ToolRouter already performs quality-based selection; this method
        only applies the final budget ceiling so we never exceed the configured
        maximum regardless of the router's own ``_MAX_TOOL_COUNT``.
        """
        tools = list(active_tools or [])
        if not tools:
            return []

        if len(tools) <= self._routed_tool_budget:
            return tools

        original_count = len(tools)
        tools = tools[: self._routed_tool_budget]
        logger.warning(
            "⚠️ Routed tool set exceeded budget (%d/%d from catalog %d); capped to %d",
            original_count,
            self._routed_tool_budget,
            full_catalog_count,
            len(tools),
        )
        return tools

    def _get_active_tools_for_iteration(
        self,
        user_message: str,
        prior_tool_names: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Return the tool subset to send to the LLM for this iteration.

        Routing pipeline (in order):
        1. ToolRouter intent-based filtering with per-iteration domain pinning.
        2. If router returns nothing + prior tools exist → reuse prior sources.
        3. If router unavailable → local heuristic fallback.
        4. Apply ``_routed_tool_budget`` hard cap.
        5. Return ``[]`` if no tools available (logs a warning).
        """
        if not self._tool_definitions:
            return []

        active_tools: List[Dict[str, Any]] = []

        if self._tool_router:
            active_tools = list(
                self._tool_router.filter_tools_for_query(
                    user_message,
                    self._tool_definitions,
                    self._tool_source_map,
                    prior_tool_names=list(prior_tool_names or []),
                ) or []
            )
            # If router returned nothing but we have prior tools, fall back to
            # reusing their sources so the model can continue its current task.
            if not active_tools and prior_tool_names:
                prior_requested = set(prior_tool_names)
                active_tools = [
                    tool for tool in self._tool_definitions
                    if isinstance(tool, dict)
                    and isinstance(tool.get("function", tool), dict)
                    and (tool.get("function", tool).get("name") in prior_requested)
                ]
                if active_tools:
                    logger.info(
                        "🔁 Router returned no tools; reusing %d prior requested tool(s): %s",
                        len(active_tools),
                        ", ".join(sorted(prior_requested)),
                    )
        else:
            # ToolRouter unavailable — use local heuristic as fallback
            logger.warning("⚠️ ToolRouter unavailable; using local heuristic fallback")
            active_tools = self._select_compact_tools_for_query(
                user_message,
                self._tool_definitions,
                self._routed_tool_budget,
            )

        if not active_tools:
            logger.warning(
                "⚠️ Routing produced no tools for query (strict mode); LLM will answer without tools"
            )
            return []

        return self._enforce_routed_tool_budget(
            active_tools,
            len(self._tool_definitions),
        )

    async def _get_active_tools_for_iteration_async(
        self,
        user_message: str,
        prior_tool_names: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Async version of _get_active_tools_for_iteration.

        Phase 5 routing path (MCP_AGENT_PIPELINE=routing):
            1. Router.route()            → List[DomainMatch]
            2. ToolRetriever.retrieve()  → ≤15 semantically ranked tools
            Falls back to legacy path if pipeline not initialized.

        Legacy path (default / MCP_AGENT_PIPELINE not set):
            Runs the synchronous ToolRouter pass first, then enriches the result with
            semantic retrieval from ToolEmbedder when available.  Falls back to the
            synchronous method result when the embedder is not ready.
        """
        # Phase 5: new routing pipeline path
        if (
            self._pipeline_routing
            and self._pipeline_router is not None
            and self._pipeline_retriever is not None
        ):
            try:
                tool_source_map = self._mcp_client.get_tool_sources() if self._mcp_client else {}
                domain_matches = await self._pipeline_router.route(
                    user_message,
                    prior_tool_names=list(prior_tool_names or []),
                    tool_source_map=tool_source_map,
                )
                retrieval_result = await self._pipeline_retriever.retrieve(
                    user_message,
                    domain_matches,
                )
                if retrieval_result.tools:
                    logger.debug(
                        "🗺️ [ROUTING] %d tools returned (pool=%d) | domains=%s",
                        len(retrieval_result.tools),
                        retrieval_result.pool_size,
                        [m.domain.value for m in domain_matches[:3]],
                    )
                    return retrieval_result.tools
                # Fall through to legacy path if pipeline returned nothing
                logger.warning(
                    "🗺️ [ROUTING] pipeline returned 0 tools; falling back to legacy router"
                )
            except Exception as _pipe_exc:
                logger.warning(
                    "🗺️ [ROUTING] pipeline error (%s); falling back to legacy router", _pipe_exc
                )

        # Legacy path: ToolRouter (sync) + ToolEmbedder merge
        router_tools = self._get_active_tools_for_iteration(user_message, prior_tool_names)

        # Semantic enrichment (only when embedder index is ready)
        if self._tool_embedder and self._tool_embedder.is_ready and user_message:
            try:
                semantic_tools = await self._tool_embedder.retrieve(
                    user_message, top_k=self._routed_tool_budget
                )
                if semantic_tools:
                    # Union of router + semantic, keeping router order first
                    router_names = {
                        t.get("function", {}).get("name") for t in router_tools
                    }
                    for t in semantic_tools:
                        name = (t.get("function") or {}).get("name")
                        if name and name not in router_names:
                            router_tools.append(t)
                            router_names.add(name)
                    router_tools = self._enforce_routed_tool_budget(
                        router_tools, len(self._tool_definitions)
                    )
                    logger.debug(
                        "ToolEmbedder merged %d semantic tools; final subset=%d",
                        len(semantic_tools),
                        len(router_tools),
                    )
            except Exception as emb_exc:
                logger.debug("ToolEmbedder retrieval skipped: %s", emb_exc)

        return router_tools

    async def _run_full_pipeline_async(
        self,
        user_message: str,
        start_time: float,
    ) -> Optional[Dict[str, Any]]:
        """Execute the full 6-stage pipeline: Route→Retrieve→Plan→Execute→Verify→Compose.

        Called by ``process_message()`` when ``MCP_AGENT_PIPELINE=true``.

        Returns a final response dict (same shape as the legacy path) on success,
        or None when the pipeline cannot run (missing components, router error, etc.)
        — the caller must then fall back to the legacy ReAct loop.

        Args:
            user_message: The raw user query string.
            start_time: ``time.time()`` snapshot from process_message() for elapsed tracking.

        Returns:
            Response dict with ``success``, ``response``, ``elapsed_seconds`` keys,
            or None on pipeline failure.
        """
        if (
            self._pipeline_router is None
            or self._pipeline_retriever is None
            or self._pipeline_planner is None
            or self._pipeline_executor is None
            or self._pipeline_verifier is None
            or self._pipeline_composer is None
        ):
            logger.debug("_run_full_pipeline_async: pipeline not fully initialised; skipping")
            return None

        try:
            # Stage 1+2: Route + Retrieve
            tool_source_map = self._mcp_client.get_tool_sources() if self._mcp_client else {}
            domain_matches = await self._pipeline_router.route(
                user_message,
                prior_tool_names=[],
                tool_source_map=tool_source_map,
            )
            retrieval_result = await self._pipeline_retriever.retrieve(
                user_message, domain_matches
            )
            logger.info(
                "🚀 [PIPELINE] Stage 1+2: %d tools retrieved (pool=%d) | domains=[%s]",
                len(retrieval_result.tools),
                retrieval_result.pool_size,
                ", ".join(m.domain.value for m in domain_matches[:5]),
            )

            # Stage 3: Plan
            grounding_summary = None
            if self._pipeline_inventory is not None:
                try:
                    grounding_summary = await self._pipeline_inventory.get_grounding_summary()
                except Exception as _gs_exc:
                    logger.debug("Pipeline grounding summary unavailable: %s", _gs_exc)

            plan = await self._pipeline_planner.plan(
                user_message, retrieval_result, grounding_summary,
                inventory_context=self._inventory_grounding_context,
            )
            logger.info(
                "🚀 [PIPELINE] Stage 3: plan=%d step(s) fast_path=%s | %s",
                len(plan.steps),
                plan.is_fast_path,
                [s.tool_name for s in plan.steps],
            )
            await self._push_event(
                "pipeline_plan",
                f"Execution plan: {len(plan.steps)} step(s)",
                plan=plan.to_dict(),
            )

            # Check for legacy_react sentinel — fall back to ReAct loop
            if plan.steps and plan.steps[0].tool_name == "legacy_react":
                logger.warning("🚀 [PIPELINE] Plan requested legacy_react fallback")
                return None

            # Stage 4: Execute
            execution_result = await self._pipeline_executor.execute(plan)
            logger.info(
                "🚀 [PIPELINE] Stage 4: %d steps OK / %d failed / %d skipped",
                len(execution_result.successful_results),
                len(execution_result.failed_results),
                len(execution_result.skipped_results),
            )

            # Stage 4.5: CLI fallback — retry any failed steps via azure_cli_execute_command
            if execution_result.failed_results:
                cli_replacements = await self._cli_fallback_retry(
                    user_message, plan, execution_result
                )
                if cli_replacements:
                    replaced = {r.step_id for r in cli_replacements}
                    execution_result.step_results = [
                        r for r in execution_result.step_results if r.step_id not in replaced
                    ] + cli_replacements
                    execution_result.all_succeeded = all(
                        r.success for r in execution_result.step_results if not r.skipped
                    )
                    logger.info(
                        "🚀 [PIPELINE] Stage 4.5: CLI fallback replaced %d failed step(s)",
                        len(cli_replacements),
                    )

            # Stage 5: Verify
            verification_result = await self._pipeline_verifier.verify(plan, execution_result)
            logger.info(
                "🚀 [PIPELINE] Stage 5: needs_confirmation=%s issues=%d",
                verification_result.needs_confirmation,
                len(verification_result.issues),
            )

            # Stage 6: Compose
            final_html = await self._pipeline_composer.compose(
                user_message, execution_result, verification_result
            )
            logger.info(
                "🚀 [PIPELINE] Stage 6: response composed (%d chars)", len(final_html)
            )

            elapsed = time.time() - start_time
            return {
                "success": True,
                "response": final_html,
                "session_id": self.session_id,
                "elapsed_seconds": round(elapsed, 2),
                "pipeline": "full",
                "pipeline_stages": {
                    "domains": [m.domain.value for m in domain_matches[:5]],
                    "tools_retrieved": len(retrieval_result.tools),
                    "plan_tool_names": [s.tool_name for s in plan.steps],
                    "plan_steps": len(plan.steps),
                    "steps_succeeded": len(execution_result.successful_results),
                    "steps_failed": len(execution_result.failed_results),
                    "steps_skipped": len(execution_result.skipped_results),
                    "needs_confirmation": verification_result.needs_confirmation,
                },
            }

        except Exception as exc:
            logger.warning(
                "🚀 [PIPELINE] full pipeline error (%s); falling back to legacy ReAct loop",
                exc,
            )
            return None

    def __init__(
        self,
        *,
        chat_client: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
        tool_definitions: Optional[Sequence[Dict[str, Any]]] = None,
        max_reasoning_iterations: Optional[int] = None,
        default_temperature: Optional[float] = None,
    ) -> None:
        # Initialize BaseOrchestrator
        super().__init__(
            orchestrator_id=f"mcp_orch_{uuid.uuid4().hex[:8]}",
            enable_streaming=True,
            max_retries=3,
            timeout_seconds=120.0,
        )

        # MCPOrchestratorAgent-specific initialization
        self.session_id = self._new_session_id()
        self._chat_client: Optional[Any] = chat_client
        self._default_credential: Optional[DefaultAzureCredentialType] = None
        self._mcp_client: Optional[Any] = mcp_client
        self._tool_definitions: List[Dict[str, Any]] = list(tool_definitions or [])
        self._message_log: List[ChatMessage] = []
        self._last_tool_failure: Optional[Dict[str, str]] = None
        self._last_tool_request: Optional[List[str]] = None
        self._last_tool_output: Optional[Dict[str, Any]] = None
        self._registered_client_labels: List[str] = []
        self._tool_source_map: Dict[str, str] = {}
        self._dynamic_system_prompt: str = self._SYSTEM_PROMPT  # Will be updated when tools are loaded
        self._monitor_agent: Optional[Any] = None  # Lazy-initialized MonitorAgent
        self._monitor_history: List[Dict[str, str]] = []  # Prior monitor delegation request/response pairs
        self._sre_agent: Optional[Any] = None  # Lazy-initialized SRESubAgent
        self._sre_history: List[Dict[str, str]] = []  # Prior SRE delegation request/response pairs
        self._tool_router: Optional[Any] = None  # Lazy-initialized ToolRouter (keyword fallback)
        self._tool_embedder: Optional[Any] = None  # Lazy-initialized ToolEmbedder (semantic primary)
        self._pipeline_router: Optional[Any] = None   # Phase 4/5 pipeline Router
        self._pipeline_retriever: Optional[Any] = None  # Phase 4/5 pipeline ToolRetriever

        # Unified router (Phase 3) — set lazily on first use to avoid circular import issues
        self._unified_router_initialized: bool = False
        self._pipeline_shadow: bool = os.getenv("MCP_PIPELINE_SHADOW", "").lower() in ("1", "true", "yes")
        # Phase 7: MCP_AGENT_PIPELINE defaults to "true" — full 6-stage pipeline is the default.
        # Set MCP_AGENT_PIPELINE=false (or "legacy") to fall back to the legacy ReAct loop.
        _pipeline_mode = os.getenv("MCP_AGENT_PIPELINE", "true").lower()
        self._pipeline_routing: bool = _pipeline_mode in ("routing", "true", "1", "yes")
        # Full pipeline (Route→Retrieve→Plan→Execute→Verify→Compose)
        self._pipeline_full: bool = _pipeline_mode in ("true", "1", "yes", "full")
        self._pipeline_planner: Optional[Any] = None      # Phase 6 Planner
        self._pipeline_executor: Optional[Any] = None     # Phase 6 Executor
        self._pipeline_verifier: Optional[Any] = None     # Phase 6 Verifier
        self._pipeline_composer: Optional[Any] = None     # Phase 6 ResponseComposer
        self._pipeline_inventory: Optional[Any] = None    # Phase 6 ResourceInventoryService
        self.inventory_integration: Optional[Any] = None
        self.resource_inventory_client: Optional[Any] = None
        self._inventory_grounding_context: str = ""  # Populated async on first message (tenant/sub/resource summary)
        self._initialise_message_log()

        # Resource inventory grounding (same integration strategy as SRE orchestrator)
        if get_sre_inventory_integration is not None:
            try:
                self.inventory_integration = get_sre_inventory_integration()
                logger.info("MCP orchestrator inventory integration initialized")
            except Exception as exc:
                logger.warning("Inventory integration unavailable in MCP orchestrator: %s", exc)
                self.inventory_integration = None
        else:
            logger.debug(
                "SRE inventory integration helper unavailable; proceeding without grounding (error=%s)",
                _sre_inventory_import_error,
            )

        if get_resource_inventory_client is not None:
            try:
                self.resource_inventory_client = get_resource_inventory_client()
                logger.info("MCP orchestrator resource inventory client initialized")
            except Exception as exc:
                logger.warning("Resource inventory client unavailable in MCP orchestrator: %s", exc)
                self.resource_inventory_client = None
        else:
            logger.debug(
                "Resource inventory client helper unavailable; CLI discovery interception disabled (error=%s)",
                _resource_inventory_import_error,
            )

        # Initialize communication queue lazily to avoid event loop issues
        self.communication_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
        self.communication_buffer: List[Dict[str, Any]] = []
        self.max_buffer_size = 100
        # Background task tracking (GC prevention — fire-and-forget pattern)
        self._background_tasks: Set[asyncio.Task] = set()
        # High safety limit to allow complex multi-step reasoning without artificial constraints
        # Time-based warnings will notify user of long-running operations
        configured_iterations = max_reasoning_iterations or int(os.getenv("MCP_AGENT_MAX_ITERATIONS", "50"))
        self._max_reasoning_iterations = max(configured_iterations, 1)
        self._max_openai_tools = max(1, int(os.getenv("MCP_AGENT_MAX_OPENAI_TOOLS", "128")))
        self._routed_tool_budget = max(1, int(os.getenv("MCP_AGENT_ROUTED_TOOL_BUDGET", "48")))
        self._default_temperature = float(default_temperature or os.getenv("MCP_AGENT_TEMPERATURE", "0.2"))

    def _ensure_communication_queue(self) -> None:
        """Ensure communication queue is initialized (lazy initialization)."""
        if self.communication_queue is None:
            self.communication_queue = asyncio.Queue()

    # ------------------------------------------------------------------
    # Public API consumed by FastAPI endpoints
    # ------------------------------------------------------------------
    async def plan_for_query(self, user_message: str) -> Dict[str, Any]:
        """Dry-run stages 1-3 (Route → Retrieve → Plan) without executing tools.

        Returns a dict with:
            domains: list of matched domain names (confidence-ordered)
            retrieved_tools: list of tool names surfaced by ToolRetriever
            plan_steps: list of {step_id, tool_name, params, rationale, is_fast_path}
            is_fast_path: True when the planner used the heuristic fast-path
            error: set when pipeline is not available or a stage fails
        """
        if (
            self._pipeline_router is None
            or self._pipeline_retriever is None
            or self._pipeline_planner is None
        ):
            return {
                "error": "Pipeline not initialised — ensure MCP_AGENT_PIPELINE=true"
            }

        try:
            tool_source_map = self._mcp_client.get_tool_sources() if self._mcp_client else {}
            domain_matches = await self._pipeline_router.route(
                user_message,
                prior_tool_names=[],
                tool_source_map=tool_source_map,
            )
            retrieval_result = await self._pipeline_retriever.retrieve(
                user_message, domain_matches
            )

            grounding_summary = None
            if self._pipeline_inventory is not None:
                try:
                    grounding_summary = await self._pipeline_inventory.get_grounding_summary()
                except Exception:
                    pass

            plan = await self._pipeline_planner.plan(
                user_message, retrieval_result, grounding_summary,
                inventory_context=self._inventory_grounding_context,
            )

            return {
                "domains": [
                    {"domain": m.domain.value, "confidence": round(m.confidence, 3)}
                    for m in domain_matches[:5]
                ],
                "retrieved_tools": [t.get("name", "") for t in retrieval_result.tools],
                "pool_size": retrieval_result.pool_size,
                "plan_steps": [
                    {
                        "step_id": s.step_id,
                        "tool_name": s.tool_name,
                        "params": s.params,
                        "rationale": s.rationale,
                        "depends_on": s.depends_on,
                        "is_parallel": getattr(s, "is_parallel", False),
                    }
                    for s in plan.steps
                ],
                "is_fast_path": plan.is_fast_path,
            }
        except Exception as exc:
            logger.warning("plan_for_query failed: %s", exc)
            return {"error": str(exc)}

    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """Process a conversational turn, invoking MCP tools when requested."""
        self._ensure_communication_queue()
        start_time = time.time()
        iteration = 0
        tool_calls_made = 0
        _tool_invocation_counts: dict = {}  # stagnation guard: tracks per-tool call count
        reasoning_trace: List[Dict[str, Any]] = []
        last_iteration_requested_tool = False
        final_text = ""
        error_detail = None
        success = True
        self._last_tool_failure = None
        self._last_tool_request = None
        self._last_tool_output = None

        await self._push_event("reasoning", f"Analyzing request: {user_message}", iteration=iteration, user_message=user_message)

        if not await self._ensure_chat_client():
            error_msg = (
                "Azure OpenAI chat client is not available. "
                "Please ensure AZURE_OPENAI_ENDPOINT and authentication credentials "
                "(AZURE_OPENAI_API_KEY or DefaultAzureCredential) are configured."
            )
            logger.warning(error_msg)
            return self._build_failure_response(
                user_message=user_message,
                elapsed=time.time() - start_time,
                error=error_msg,
            )

        mcp_ready = await self._ensure_mcp_client()
        if not mcp_ready:
            logger.warning("Azure MCP client unavailable; continuing without tool execution")

        # Populate inventory grounding on first message so the LLM knows
        # resource names/groups without needing extra list tool calls.
        if not self._inventory_grounding_context and self.resource_inventory_client:
            try:
                await asyncio.wait_for(self._populate_inventory_grounding(), timeout=8.0)
            except asyncio.TimeoutError:
                logger.warning("Inventory grounding timed out; continuing without it")
            except Exception as _ig_exc:
                logger.warning("Inventory grounding failed: %s", _ig_exc)

        # Log tool availability for this request
        tool_count = len(self._tool_definitions) if self._tool_definitions else 0
        logger.info(f"🛠️  Processing message with {tool_count} tools available (mcp_ready={mcp_ready})")
        logger.info(f"💬 Session {self.session_id}: Processing message #{len(self._message_log)} (history: {len(self._message_log)-1} messages)")

        # Phase 6: full pipeline delegation (MCP_AGENT_PIPELINE=true|full|1|yes)
        # Runs Router→Retrieve→Plan→Execute→Verify→Compose in place of the ReAct loop.
        # Falls back to legacy ReAct loop on any pipeline error.
        if self._pipeline_full:
            full_pipeline_result = await self._run_full_pipeline_async(user_message, start_time)
            if full_pipeline_result is not None:
                # Append the user message and a synthetic assistant message to history
                user_chat = ChatMessage(role="user", text=user_message)
                self._message_log.append(user_chat)
                assistant_chat = ChatMessage(
                    role="assistant", text=full_pipeline_result.get("response", "")
                )
                self._message_log.append(assistant_chat)
                await self._push_event(
                    "complete",
                    "Pipeline complete",
                    elapsed_seconds=full_pipeline_result.get("elapsed_seconds", 0),
                )
                return full_pipeline_result
            # Pipeline returned None → fall through to legacy ReAct loop
            logger.info("🚀 [PIPELINE] falling back to legacy ReAct loop")

        # Phase 4/5 shadow mode: run new Router+ToolRetriever and log comparison.
        # MCP_PIPELINE_SHADOW=true → log only (result NOT used).
        # MCP_AGENT_PIPELINE=routing → result is used by _get_active_tools_for_iteration_async.
        if (self._pipeline_shadow or self._pipeline_routing) and self._pipeline_router is not None and self._pipeline_retriever is not None:
            try:
                tool_source_map = self._mcp_client.get_tool_sources() if self._mcp_client else {}
                domain_matches = await self._pipeline_router.route(
                    user_message,
                    prior_tool_names=list(tool_source_map.keys()),
                    tool_source_map=tool_source_map,
                )
                retrieval_result = await self._pipeline_retriever.retrieve(
                    user_message,
                    domain_matches,
                )
                domains_str = ", ".join(m.domain.value for m in domain_matches[:5])
                _mode_tag = "ROUTING" if self._pipeline_routing else "SHADOW"
                logger.info(
                    "🔬 [%s] pipeline: %d tools (pool=%d) vs legacy: %d tools | domains=[%s]",
                    _mode_tag,
                    len(retrieval_result.tools),
                    retrieval_result.pool_size,
                    tool_count,
                    domains_str,
                )
                if retrieval_result.conflict_notes:
                    logger.debug("🔬 [%s] conflict_notes: %s", _mode_tag, retrieval_result.conflict_notes[:200])
            except Exception as _shadow_exc:
                logger.debug("🔬 [PIPELINE] pipeline error (ignored): %s", _shadow_exc)

        # NOTE: Legacy ReAct loop removed in Phase 7.
        # The full pipeline (Router→Retrieve→Plan→Execute→Verify→Compose) handles all queries.
        # This fallback path only runs when MCP_AGENT_PIPELINE=false or pipeline init fails.
        # When the fallback is reached here, final_text is empty and success=True,
        # so the post-loop handler below will convert it to a failure response.

        duration = time.time() - start_time

        if not final_text and success:
            success = False
            final_text = (
                f"The request required more than {self._max_reasoning_iterations} reasoning iterations to complete. "
                "This may indicate a very complex query. Please try breaking it into smaller requests."
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
            "timeout_approaching": duration > 50,  # Flag for UI to show "continue" option
            "agent_framework_enabled": True,  # Direct OpenAI SDK
            "reasoning_trace": reasoning_trace,
            "error": error_detail,
            "last_tool_failure": self._last_tool_failure,
            "last_tool_request": self._last_tool_request,
            "last_tool_output": self._last_tool_output,
        }

        # Log session summary
        session_log = {
            "session_id": self.session_id,
            "tool_calls_made": tool_calls_made,
            "iterations": iteration,
            "last_tool_request": self._last_tool_request,
            "last_tool_failure": self._last_tool_failure,
        }
        logger.info("📊 MCP session summary: %s", json.dumps(session_log, ensure_ascii=False))

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
            output_str = json.dumps(self._last_tool_output, ensure_ascii=False)[:2000]
            logger.info("MCP orchestrator tool output (session=%s): %s", self.session_id, output_str)

        # Format and deduplicate the response
        final_text = _response_formatter.deduplicate(final_text)
        final_text = _response_formatter.format(final_text)

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
        """Expose the conversation log in a serializable format (excluding system and tool messages)."""
        history: List[Dict[str, Any]] = []
        for message in self._message_log:
            role = self._get_message_role(message) or "assistant"
            # Skip system messages and tool result messages (which are internal to the LLM context)
            # Tool results are already formatted by the assistant in its response
            if role in ("system", "tool"):
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
        self._monitor_history.clear()
        if self.communication_queue:
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
        """Validate that Azure OpenAI credentials are available.

        Uses the direct OpenAI SDK, so this just verifies that the
        required env vars exist and sets ``self._chat_client`` to a
        truthy sentinel.
        """
        if self._chat_client:
            return True

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        has_credential = _DEFAULT_CREDENTIAL_AVAILABLE and DefaultAzureCredential is not None

        if not endpoint:
            logger.warning("AZURE_OPENAI_ENDPOINT not set — chat client unavailable")
            return False
        if not api_key and not has_credential:
            logger.warning("No Azure OpenAI API key or DefaultAzureCredential available")
            return False

        # Store a truthy sentinel so subsequent calls short-circuit.
        self._chat_client = True  # type: ignore[assignment]
        deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        logger.info(
            "✅ Azure OpenAI credentials verified (deployment=%s, endpoint_configured=True)",
            deployment,
        )
        return True

    def _build_openai_messages(self) -> List[Dict[str, Any]]:
        """Convert internal message history to OpenAI chat-completion format.

        Includes a safety pass that drops orphaned ``tool`` messages whose
        ``tool_call_id`` does not match any preceding assistant ``tool_calls``
        entry.  This prevents 400 errors from the OpenAI API.
        """
        openai_messages: List[Dict[str, Any]] = []
        for msg in self._message_log:
            role = self._get_message_role(msg)

            if role == "tool":
                for content in msg.contents:
                    if hasattr(content, "call_id") and content.call_id:
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": content.call_id,
                            "content": self._message_to_text(msg) or "Success",
                        })
            elif role == "assistant" and any(
                hasattr(c, "name") and hasattr(c, "call_id") for c in msg.contents
            ):
                tool_calls = []
                for content in msg.contents:
                    if hasattr(content, "name") and hasattr(content, "call_id"):
                        tool_calls.append({
                            "id": content.call_id,
                            "type": "function",
                            "function": {
                                "name": content.name,
                                "arguments": json.dumps(content.arguments) if hasattr(content, "arguments") else "{}",
                            },
                        })
                if tool_calls:
                    openai_messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls,
                    })
            else:
                text = self._message_to_text(msg)
                if text:
                    openai_messages.append({"role": role, "content": text})

        # --- Safety pass: drop orphaned tool messages ---
        # Collect all tool_call ids from assistant messages
        valid_tool_call_ids: set = set()
        for m in openai_messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    valid_tool_call_ids.add(tc.get("id"))

        original_count = len(openai_messages)
        openai_messages = [
            m for m in openai_messages
            if m.get("role") != "tool" or m.get("tool_call_id") in valid_tool_call_ids
        ]
        dropped = original_count - len(openai_messages)
        if dropped:
            logger.warning(
                "🧹 Dropped %d orphaned tool message(s) to maintain valid message sequence",
                dropped,
            )

        return openai_messages

    async def _summarize_old_messages(self) -> None:
        """Summarize older conversation turns to keep context window manageable.

        When the message log exceeds a threshold, the middle section
        (everything except the system prompt and the last N messages) is
        replaced with a compact summary message.

        IMPORTANT: The tail boundary is adjusted so that tool_calls /
        tool message pairs are never split.  The OpenAI API requires
        every ``role: tool`` message to be preceded by an assistant
        message containing the matching ``tool_calls`` entry.
        """
        # Keep system prompt (index 0) + last 6 messages
        KEEP_TAIL = 6
        MIN_MESSAGES_BEFORE_SUMMARY = 12

        if len(self._message_log) < MIN_MESSAGES_BEFORE_SUMMARY:
            return

        # --- Determine a safe split index that does not orphan tool messages ---
        candidate_split = len(self._message_log) - KEEP_TAIL  # first index of tail

        # Walk backwards from the candidate split to find a safe boundary.
        # A safe boundary is one where the message at the split index is NOT
        # a 'tool' role (orphaned response) and is NOT an 'assistant' with
        # tool_calls whose tool responses would fall across the boundary.
        while candidate_split > 1:
            msg_at_split = self._message_log[candidate_split]
            role = self._get_message_role(msg_at_split)
            if role == "tool":
                # This tool message would be orphaned — include its parent too
                candidate_split -= 1
                continue
            # If the message just before the split is an assistant with
            # tool_calls, its tool responses might be at or after the split.
            # Check the message before the split.
            prev_msg = self._message_log[candidate_split - 1]
            prev_role = self._get_message_role(prev_msg)
            if prev_role == "assistant" and any(
                hasattr(c, "name") and hasattr(c, "call_id")
                for c in getattr(prev_msg, "contents", [])
            ):
                # The assistant tool_calls msg is at candidate_split-1, which
                # would be summarized, but its tool responses start at
                # candidate_split — that's an orphan.  Pull it into the tail.
                candidate_split -= 1
                continue
            break  # safe boundary found

        to_summarize = self._message_log[1:candidate_split]
        if not to_summarize:
            return

        # Build a compact textual summary of the earlier conversation
        summary_parts: List[str] = []
        for msg in to_summarize:
            role = self._get_message_role(msg)
            text = self._message_to_text(msg)
            if role == "tool":
                # Truncate verbose tool results
                text = text[:300] + "..." if len(text) > 300 else text
            if text:
                summary_parts.append(f"[{role}]: {text[:200]}")

        summary_text = (
            "CONVERSATION SUMMARY (older messages condensed):\n"
            + "\n".join(summary_parts[-10:])  # keep last 10 snippets max
        )

        summary_message = ChatMessage(role="system", text=summary_text)
        # Replace: keep system prompt + summary + safe tail
        self._message_log = (
            [self._message_log[0], summary_message]
            + self._message_log[candidate_split:]
        )
        logger.info(
            "📝 Summarized %d older messages into compact summary (%d messages remain)",
            len(to_summarize),
            len(self._message_log),
        )

    async def _ensure_mcp_client(self) -> bool:
        if self._mcp_client:
            if not self._tool_definitions:
                await self._refresh_tool_definitions()
            else:
                self._update_tool_metadata()
            return True

        # Initialize MCPHost using declarative configuration
        try:
            self._mcp_client = await MCPHost.from_config()
            self._registered_client_labels = self._mcp_client.get_client_labels()
        except Exception as exc:
            logger.error("MCPHost.from_config() failed: %s", exc)
            self._mcp_client = None
            self._registered_client_labels = []
            self._tool_source_map = {}
            return False

        if not self._mcp_client:
            logger.error("No MCP clients available; tool execution disabled")
            return False

        await self._refresh_tool_definitions()
        if self._tool_definitions:
            logger.info("✅ Loaded %d MCP tools via from_config()", len(self._tool_definitions))
            return True

        logger.warning("MCP clients initialised but no tools were registered")
        return False

    async def _invoke_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Intercept the monitor_agent meta-tool
        if tool_name == "monitor_agent":
            return await self._handle_monitor_delegation(arguments)

        # Intercept the sre_agent meta-tool
        if tool_name == "sre_agent":
            return await self._handle_sre_delegation(arguments)

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

    async def _handle_monitor_delegation(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate a request to the MonitorAgent sub-agent, injecting prior monitor context."""
        user_request = arguments.get("request", "")
        if not user_request:
            return {"success": False, "error": "No 'request' argument provided to monitor_agent."}

        if not self._monitor_agent:
            # Try to initialise on first use
            self._init_monitor_agent()

        if not self._monitor_agent:
            return {"success": False, "error": "Monitor agent not available — monitor MCP server may not be running."}

        # Build context-enriched message from prior monitor interactions
        enriched_request = user_request
        if self._monitor_history:
            # Include up to the last 3 monitor interactions for context
            recent = self._monitor_history[-3:]
            context_parts = []
            for i, entry in enumerate(recent, 1):
                context_parts.append(
                    f"--- Previous monitor interaction {i} ---\n"
                    f"User request: {entry['request']}\n"
                    f"Agent response: {entry['response'][:2000]}\n"
                )
            context_block = "\n".join(context_parts)
            enriched_request = (
                f"CONTEXT FROM PRIOR MONITOR INTERACTIONS (use this to resolve references like "
                f"'the first query', 'deploy it', resource names, download URLs, etc.):\n\n"
                f"{context_block}\n"
                f"--- Current request ---\n{user_request}"
            )
            logger.info(
                "🔀 MonitorAgent delegation with %d prior interactions as context",
                len(recent),
            )

        logger.info("🔀 Delegating to MonitorAgent: %s", user_request[:200])
        try:
            result = await self._monitor_agent.run(enriched_request)
            response_text = result.get("response", "")

            # Save this interaction for future context
            self._monitor_history.append({
                "request": user_request,
                "response": response_text,
            })
            # Keep history bounded
            if len(self._monitor_history) > 10:
                self._monitor_history = self._monitor_history[-10:]

            # Wrap the sub-agent's HTML response as a successful tool result
            return {
                "success": result.get("success", False),
                "response": response_text,
                "tool_calls_made": result.get("tool_calls_made", 0),
                "agent": "monitor",
            }
        except Exception as exc:
            logger.exception("MonitorAgent delegation failed: %s", exc)
            return {"success": False, "error": f"Monitor agent error: {exc}"}

    def _init_monitor_agent(self) -> None:
        """Initialise the MonitorAgent with monitor + CLI tools from the composite client."""
        if MonitorAgent is None:
            logger.warning("MonitorAgent class not available — skipping initialization")
            return

        if not self._mcp_client:
            logger.warning("Cannot init MonitorAgent — no MCP client")
            return

        # Get monitor + azure_cli tools only
        get_by_sources = getattr(self._mcp_client, "get_tools_by_sources", None)
        if not callable(get_by_sources):
            logger.warning("CompositeMCPClient missing get_tools_by_sources — cannot init MonitorAgent")
            return

        monitor_tools = get_by_sources(["monitor", "azure_cli"])
        if not monitor_tools:
            logger.warning("No monitor/CLI tools found — MonitorAgent will not be initialised")
            return

        self._monitor_agent = MonitorAgent(
            tool_definitions=monitor_tools,
            tool_invoker=self._mcp_client.call_tool,
            event_callback=self._push_event,
        )
        logger.info(
            "✅ MonitorAgent initialised with %d tools (monitor + CLI)",
            len(monitor_tools),
        )

    async def _handle_sre_delegation(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate a request to the SRESubAgent, injecting prior SRE context."""
        user_request = arguments.get("request", "")
        if not user_request:
            return {"success": False, "error": "No 'request' argument provided to sre_agent."}

        if not self._sre_agent:
            self._init_sre_agent()

        if not self._sre_agent:
            return {"success": False, "error": "SRE agent not available — SRE MCP server may not be running."}

        # Build context-enriched message from prior SRE interactions
        enriched_request = user_request
        if self._sre_history:
            recent = self._sre_history[-3:]
            context_parts = []
            for i, entry in enumerate(recent, 1):
                context_parts.append(
                    f"--- Previous SRE interaction {i} ---\n"
                    f"User request: {entry['request']}\n"
                    f"Agent response: {entry['response'][:2000]}\n"
                )
            context_block = "\n".join(context_parts)
            enriched_request = (
                f"CONTEXT FROM PRIOR SRE INTERACTIONS (use this to resolve references "
                f"like 'that resource', 'check it again', resource IDs, etc.):\n\n"
                f"{context_block}\n"
                f"--- Current request ---\n{user_request}"
            )
            logger.info(
                "🔀 SRESubAgent delegation with %d prior interactions as context",
                len(recent),
            )

        logger.info("🔀 Delegating to SRESubAgent: %s", user_request[:200])
        try:
            result = await self._sre_agent.run(enriched_request)
            response_text = result.get("response", "")

            # Save this interaction for future context
            self._sre_history.append({
                "request": user_request,
                "response": response_text,
            })
            # Keep history bounded
            if len(self._sre_history) > 10:
                self._sre_history = self._sre_history[-10:]

            return {
                "success": result.get("success", False),
                "response": response_text,
                "tool_calls_made": result.get("tool_calls_made", 0),
                "agent": "sre",
            }
        except Exception as exc:
            logger.exception("SRESubAgent delegation failed: %s", exc)
            return {"success": False, "error": f"SRE agent error: {exc}"}

    def _init_sre_agent(self) -> None:
        """Initialise the SRESubAgent with SRE + CLI tools from the composite client."""
        if SRESubAgent is None:
            logger.warning("SRESubAgent class not available — skipping initialization")
            return

        if not self._mcp_client:
            logger.warning("Cannot init SRESubAgent — no MCP client")
            return

        get_by_sources = getattr(self._mcp_client, "get_tools_by_sources", None)
        if not callable(get_by_sources):
            logger.warning("CompositeMCPClient missing get_tools_by_sources — cannot init SRESubAgent")
            return

        sre_tools = get_by_sources(["sre", "azure_cli"])
        if not sre_tools:
            logger.warning("No SRE/CLI tools found — SRESubAgent will not be initialised")
            return

        self._sre_agent = SRESubAgent(
            tool_definitions=sre_tools,
            tool_invoker=self._mcp_client.call_tool,
            event_callback=self._push_event,
        )
        logger.info(
            "✅ SRESubAgent initialised with %d tools (SRE + CLI)",
            len(sre_tools),
        )

    def _spawn_background(self, coro, *, name: Optional[str] = None) -> asyncio.Task:
        """Schedule coro as a background task, tracking it to prevent GC.

        The task is added to _background_tasks and automatically removed
        (via discard callback) when it completes or raises. Exceptions are
        logged at DEBUG level — they never propagate to callers.

        Args:
            coro: Awaitable to run in background
            name: Optional task name for debugging

        Returns:
            The created asyncio.Task (caller may ignore it)
        """
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    logger.debug(
                        "Background task %r raised: %s: %s",
                        t.get_name(), type(exc).__name__, exc,
                    )

        task.add_done_callback(_on_done)
        return task

    # ========================================================================
    # BaseOrchestrator Abstract Method Implementations
    # ========================================================================

    async def route_query(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> ExecutionPlan:
        """Route a user query and determine execution strategy.

        This is a minimal implementation that wraps the existing process_message
        logic. The actual routing happens inside process_message based on
        pipeline mode settings.

        Args:
            query: User's natural language query
            context: Additional context parameters

        Returns:
            ExecutionPlan describing the routing strategy
        """
        # Determine strategy based on pipeline mode
        if self._pipeline_full:
            strategy = "pipeline"
        elif self._pipeline_routing:
            strategy = "routing"
        else:
            strategy = "react"

        # Create minimal execution plan
        # Note: The actual execution happens in process_message, so this
        # is primarily for compatibility with BaseOrchestrator interface
        return ExecutionPlan(
            strategy=strategy,
            domains=["azure", "mcp"],  # This orchestrator handles Azure MCP tools
            tools=[],  # Tools determined dynamically during execution
            steps=[
                PlanStep(
                    step_number=1,
                    action="process_message",
                    target="mcp_orchestrator",
                    parameters={"query": query},
                    description=f"Execute {strategy} loop for query"
                )
            ],
            context=context,
        )

    async def execute_plan(
        self,
        plan: ExecutionPlan,
    ) -> OrchestratorResult:
        """Execute an execution plan and return results.

        This is a minimal implementation that delegates to the existing
        process_message method which handles the full ReAct loop and
        pipeline execution.

        Args:
            plan: Execution plan from route_query()

        Returns:
            OrchestratorResult with execution outcome
        """
        import time
        start_time = time.time()

        # Extract query from plan
        query = plan.steps[0].parameters.get("query", "") if plan.steps else ""

        # Execute via existing process_message method
        result_dict = await self.process_message(query)

        # Map to OrchestratorResult format
        duration_ms = (time.time() - start_time) * 1000

        # Extract formatted response
        formatted_response = result_dict.get("formatted_response", "")
        if not formatted_response:
            # Fallback to generating response from result
            formatted_response = self.format_response(result_dict, format="formatted_html")

        return OrchestratorResult(
            success=result_dict.get("success", True),
            content=str(result_dict.get("result", "")),
            formatted_response=formatted_response,
            metadata=result_dict.get("metadata", {}),
            tools_called=result_dict.get("tools_called", []),
            duration_ms=duration_ms,
            interaction_required=result_dict.get("interaction_required", False),
            interaction_data=result_dict.get("interaction_data"),
        )

    # ========================================================================
    # Lifecycle Management
    # ========================================================================

    async def shutdown(self) -> None:
        """Cancel all pending background tasks and wait for cancellation."""
        if self._background_tasks:
            tasks = list(self._background_tasks)
            logger.debug("Cancelling %d background tasks on shutdown", len(tasks))
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._background_tasks.clear()

    async def aclose(self) -> None:
        """Release network clients and credentials."""
        await self.shutdown()
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
            logger.warning("⚠️  Cannot refresh tool definitions - no MCP client available")
            return

        catalog_accessor = getattr(self._mcp_client, "get_available_tools", None)
        if not callable(catalog_accessor):
            self._tool_definitions = []
            self._tool_source_map = {}
            logger.warning("⚠️  MCP client has no get_available_tools method")
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
                logger.warning("⚠️  Tool catalog is not a list or tuple: %s", type(tools))
            
            logger.info("✅ Loaded %d MCP tools total", len(self._tool_definitions))

            # --- Hybrid architecture: filter monitor tools out, add meta-tool ---
            # The MonitorAgent handles all monitor tools internally.
            # The orchestrator only sees a single 'monitor_agent' delegation tool.
            get_excl = getattr(self._mcp_client, "get_tools_excluding_sources", None)
            if callable(get_excl) and MonitorAgent is not None:
                non_monitor_tools = get_excl(["monitor"])
                monitor_count = len(self._tool_definitions) - len(non_monitor_tools)
                if monitor_count > 0:
                    self._tool_definitions = non_monitor_tools
                    # Inject the monitor_agent meta-tool
                    meta_tool = {
                        "function": {
                            "name": "monitor_agent",
                            "description": (
                                "Delegate to the Azure Monitor specialist agent. Use this tool whenever the user "
                                "asks about Azure Monitor resources, workbooks, alerts, KQL queries, or monitoring "
                                "for ANY Azure service. Pass the user's FULL request as-is. "
                                "The monitor agent handles discovery, listing, and deployment of monitor resources "
                                "autonomously. Do NOT try to call monitor tools directly. "
                                "IMPORTANT: When referring to a previously discovered resource (e.g., 'deploy the first query'), "
                                "include the resource name and download URL from the earlier response in your request text "
                                "so the monitor agent has full context."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "request": {
                                        "type": "string",
                                        "description": (
                                            "The user's full request about Azure Monitor resources. "
                                            "Include the original user message AND any relevant details from "
                                            "prior responses (resource names, download URLs, categories). "
                                            "For deployment follow-ups, include the resource name, download URL, "
                                            "and any parameters the user has provided."
                                        ),
                                    }
                                },
                                "required": ["request"],
                            },
                        }
                    }
                    self._tool_definitions.append(meta_tool)
                    logger.info(
                        "🔀 Hybrid mode: replaced %d monitor tools with monitor_agent meta-tool (%d tools for orchestrator)",
                        monitor_count,
                        len(self._tool_definitions),
                    )
                    # Initialize the MonitorAgent now
                    self._init_monitor_agent()

            # --- Hybrid architecture: filter SRE tools out, add sre_agent meta-tool ---
            # The SRESubAgent handles all SRE tools internally (~58 tools → 1 meta-tool).
            get_excl_sre = getattr(self._mcp_client, "get_tools_excluding_sources", None)
            if callable(get_excl_sre) and SRESubAgent is not None and build_sre_meta_tool is not None:
                # Count SRE tools currently in the catalog
                sre_tool_names = [
                    t.get("function", {}).get("name", "")
                    for t in self._tool_definitions
                    if self._tool_source_map.get(t.get("function", {}).get("name", "")) == "sre"
                ]
                if sre_tool_names:
                    # Remove SRE tools and inject the meta-tool
                    self._tool_definitions = [
                        t for t in self._tool_definitions
                        if self._tool_source_map.get(t.get("function", {}).get("name", "")) != "sre"
                    ]
                    self._tool_definitions.append(build_sre_meta_tool())
                    logger.info(
                        "🔀 Hybrid mode: replaced %d SRE tools with sre_agent meta-tool (%d tools for orchestrator)",
                        len(sre_tool_names),
                        len(self._tool_definitions),
                    )
                    # Initialize the SRESubAgent now
                    self._init_sre_agent()

            # --- Initialize ToolRouter for intent-based pre-filtering ---
            if ToolRouter is not None and self._tool_router is None:
                self._tool_router = ToolRouter(composite_client=self._mcp_client)
                logger.info("🎯 ToolRouter initialized for intent-based tool pre-filtering")

            # --- Initialize ToolEmbedder for semantic retrieval ---
            if ToolEmbedder is not None and self._tool_embedder is None:
                self._tool_embedder = ToolEmbedder()
                logger.info("📐 ToolEmbedder initialized for semantic tool retrieval")

            # --- Initialize Phase 4/5 pipeline Router + ToolRetriever ---
            # Activated by: MCP_PIPELINE_SHADOW=true (shadow/log only)
            #            or: MCP_AGENT_PIPELINE=routing (active routing path)
            if (
                (self._pipeline_shadow or self._pipeline_routing)
                and PipelineRouter is not None
                and PipelineToolRetriever is not None
                and self._pipeline_router is None
            ):
                self._pipeline_router = PipelineRouter()
                self._pipeline_retriever = PipelineToolRetriever(
                    composite_client=self._mcp_client,
                    embedder=self._tool_embedder,
                )
                mode = "active routing" if self._pipeline_routing else "shadow"
                logger.info("🔬 PipelineRouter + ToolRetriever initialized (%s mode)", mode)

            # --- Initialize Phase 6 full pipeline components ---
            # Activated by: MCP_AGENT_PIPELINE=true|full|1|yes
            if (
                self._pipeline_full
                and PipelinePlanner is not None
                and PipelineExecutor is not None
                and PipelineVerifier is not None
                and PipelineResponseComposer is not None
                and self._pipeline_planner is None
            ):
                # Inventory service (shared across all Phase 6 components)
                if get_pipeline_inventory_service is not None:
                    try:
                        self._pipeline_inventory = get_pipeline_inventory_service()
                    except Exception as _inv_exc:
                        logger.warning("Phase 6 inventory service unavailable: %s", _inv_exc)

                # Retrieve manifest index from ToolRetriever if already init'd
                manifest_index = None
                if self._pipeline_retriever is not None:
                    manifest_index = getattr(self._pipeline_retriever, "_manifest_index", None)

                self._pipeline_planner = PipelinePlanner(manifest_index=manifest_index)
                self._pipeline_executor = PipelineExecutor(
                    composite_client=self._mcp_client,
                    inventory_service=self._pipeline_inventory,
                    push_event=self._push_event,
                )
                self._pipeline_verifier = PipelineVerifier(
                    manifest_index=manifest_index,
                    inventory_service=self._pipeline_inventory,
                )
                self._pipeline_composer = PipelineResponseComposer()
                logger.info("🚀 Phase 6 full pipeline initialized (Planner+Executor+Verifier+Composer)")

            if self._tool_definitions:
                tool_names = [t.get("function", {}).get("name", "unknown") for t in self._tool_definitions[:5]]
                logger.info(f"   Sample tools: {', '.join(tool_names)}{' ...' if len(self._tool_definitions) > 5 else ''}")
            else:
                logger.warning("⚠️  No tools loaded from MCP clients - agent will not be able to call tools!")
        except Exception as exc:  # pragma: no cover - defensive refresh
            logger.exception("Unable to refresh MCP tool catalog: %s", exc)
            self._tool_definitions = []
        finally:
            self._update_tool_metadata()
            # Refresh system prompt with updated tool information
            if self._tool_definitions:
                self._refresh_system_prompt()
            # Build semantic index in a fire-and-forget background task so it never
            # blocks the calling request (embedding 140+ tools can take seconds).
            if self._tool_embedder and self._tool_definitions:
                self._spawn_background(self._build_embedding_index_bg(), name="embedding_index_build")

    async def _build_embedding_index_bg(self) -> None:
        """Background task: build ToolEmbedder semantic index without blocking callers."""
        try:
            await self._tool_embedder.build_index(self._tool_definitions)
        except Exception as emb_exc:
            logger.debug("ToolEmbedder index build failed (non-fatal): %s", emb_exc)

    async def _cli_fallback_retry(
        self,
        user_message: str,
        plan: Any,
        execution_result: Any,
    ) -> List[Any]:
        """Stage 4.5: for failed steps, synthesize equivalent az CLI commands and re-run.

        Uses a lightweight LLM call to derive the Azure CLI commands, then executes
        them via azure_cli_execute_command.  Read-only az commands (az * list/show)
        are classified as safe by the server and run without requiring confirmation.

        Returns a list of replacement StepResult objects (one per recovered step).
        """
        failed = execution_result.failed_results
        if not failed:
            return []

        if PipelineStepResult is None:  # type: ignore[truthy-function]
            return []

        # Build a concise prompt asking for az CLI equivalents
        failed_lines = "\n".join(
            f"  step_id={r.step_id} tool={r.tool_name} error={r.error[:150]}"
            for r in failed
        )
        synthesis_prompt = (
            f"User query: {user_message}\n\n"
            "The following MCP tool calls failed. For each, provide an equivalent Azure CLI "
            "command that accomplishes the same goal.\n"
            f"{failed_lines}\n\n"
            "Output ONLY a JSON array, no prose.  Example format:\n"
            '[{"step_id": "step_1", "command": "az network vnet list --output json"}]\n'
            "Use --output json on every command. If no CLI equivalent exists, omit that step."
        )

        try:
            from openai import AsyncAzureOpenAI  # type: ignore[import-not-found]

            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

            if not endpoint:
                return []

            if api_key:
                oai_client = AsyncAzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
                token_provider = None
            else:
                try:
                    from azure.identity.aio import DefaultAzureCredential as _DAC  # type: ignore[import-not-found]
                    _cred = _DAC(exclude_interactive_browser_credential=True)
                    _token = await _cred.get_token("https://cognitiveservices.azure.com/.default")
                    oai_client = AsyncAzureOpenAI(api_key=_token.token, azure_endpoint=endpoint, api_version=api_version)
                    token_provider = _cred
                except Exception:
                    return []

            try:
                resp = await oai_client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": "You are an Azure CLI expert. Output only valid JSON."},
                        {"role": "user", "content": synthesis_prompt},
                    ],
                    temperature=0,
                    max_tokens=400,
                )
                raw = (resp.choices[0].message.content or "").strip()
                # Strip markdown fences if present
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                commands: List[Dict[str, Any]] = json.loads(raw)
            finally:
                await oai_client.close()
                if token_provider is not None:
                    try:
                        await token_provider.close()
                    except Exception:
                        pass

        except Exception as exc:
            logger.warning("_cli_fallback_retry: LLM synthesis failed (%s)", exc)
            return []

        results: List[Any] = []
        for entry in commands:
            step_id = str(entry.get("step_id", ""))
            command = str(entry.get("command", "")).strip()
            if not step_id or not command:
                continue
            try:
                logger.warning("🔀 CLI fallback: step=%s → %s", step_id, command)
                tool_result = await self._invoke_mcp_tool(
                    "azure_cli_execute_command", {"command": command}
                )
                results.append(
                    PipelineStepResult(
                        step_id=step_id,
                        tool_name="azure_cli_execute_command",
                        success=True,
                        result=tool_result,
                    )
                )
            except Exception as exc:
                logger.warning("_cli_fallback_retry: CLI execution failed for step=%s: %s", step_id, exc)
                results.append(
                    PipelineStepResult(
                        step_id=step_id,
                        tool_name="azure_cli_execute_command",
                        success=False,
                        error=str(exc),
                    )
                )
        return results

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

        # Register meta-tool sources for ToolRouter filtering
        if self._monitor_agent:
            self._tool_source_map["monitor_agent"] = "meta"
        if self._sre_agent:
            self._tool_source_map["sre_agent"] = "meta"

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
        result = await self._ensure_mcp_client()
        # Also wire the unified router once MCP is ready
        if result and not self._unified_router_initialized:
            self._ensure_unified_router()
        return result

    def _ensure_unified_router(self) -> None:
        """Lazily wire the unified router onto self.router (BaseOrchestrator attribute).

        Called once after MCP clients are ready so the tool_registry is
        populated before router.route() is ever called.
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
            logger.debug("MCPOrchestratorAgent: unified router wired")
        except Exception as exc:
            logger.warning(
                "MCPOrchestratorAgent: failed to wire unified router: %s — "
                "process_with_routing() will raise if called",
                exc,
            )

    async def get_tool_catalog(self) -> List[Dict[str, Any]]:
        await self._ensure_mcp_client()
        return deepcopy(self._tool_definitions)

    def get_registered_clients(self) -> List[str]:
        return list(dict.fromkeys(self._registered_client_labels))

    def get_tool_source_map(self) -> Dict[str, str]:
        return dict(self._tool_source_map)

    def summarize_tool_counts(self) -> Dict[str, int]:
        counts = {label: 0 for label in set(self._registered_client_labels)}
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

    def _plan_tool_execution(self, tool_calls: List[FunctionCallContent]) -> List[List[FunctionCallContent]]:
        """
        Analyze tool dependencies and group tools into execution batches.
        Returns a list of groups where each group can be executed in parallel.
        """
        if len(tool_calls) <= 1:
            return [[call] for call in tool_calls]
        
        # Parse all tool arguments
        tool_data = []
        for call in tool_calls:
            arguments = self._parse_call_arguments(call)
            tool_data.append({
                "call": call,
                "name": call.name or "unknown",
                "arguments": arguments,
                "arg_strings": self._extract_argument_strings(arguments),
            })
        
        # Build dependency graph
        dependencies = {}  # tool_index -> list of tool_indices it depends on
        for i, tool_info in enumerate(tool_data):
            dependencies[i] = []
            
            # Check if this tool's arguments reference other tools' likely outputs
            for j, other_tool in enumerate(tool_data):
                if i == j:
                    continue
                
                # Check for common dependency patterns
                if self._has_dependency(tool_info, other_tool):
                    dependencies[i].append(j)
        
        # Group tools into execution batches using topological sort
        execution_groups = []
        executed = set()
        
        while len(executed) < len(tool_data):
            # Find all tools that can be executed now (all dependencies met)
            ready = []
            for i in range(len(tool_data)):
                if i in executed:
                    continue
                if all(dep in executed for dep in dependencies[i]):
                    ready.append(tool_data[i]["call"])
            
            if not ready:
                # Circular dependency or error - execute remaining sequentially
                for i in range(len(tool_data)):
                    if i not in executed:
                        execution_groups.append([tool_data[i]["call"]])
                        executed.add(i)
                break
            
            # Add this batch and mark as executed
            execution_groups.append(ready)
            for i in range(len(tool_data)):
                if tool_data[i]["call"] in ready:
                    executed.add(i)
        
        return execution_groups
    
    def _extract_argument_strings(self, arguments: Dict[str, Any]) -> List[str]:
        """Extract all string values from arguments for dependency checking."""
        strings = []
        
        def extract(obj):
            if isinstance(obj, str):
                strings.append(obj.lower())
            elif isinstance(obj, dict):
                for value in obj.values():
                    extract(value)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    extract(item)
        
        extract(arguments)
        return strings
    
    def _has_dependency(self, tool_info: Dict[str, Any], potential_provider: Dict[str, Any]) -> bool:
        """
        Check if tool_info depends on outputs from potential_provider.
        Uses heuristics to detect dependencies.
        """
        tool_args = tool_info["arg_strings"]
        provider_name = potential_provider["name"].lower()
        
        # Pattern 1: Tool arguments reference provider's name
        # e.g., vm_get after vm_list, or storage_get after storage_list
        if provider_name in " ".join(tool_args):
            return True
        
        # Pattern 2: List operations typically come before get/detail operations
        if "list" in provider_name or "search" in provider_name:
            tool_name = tool_info["name"].lower()
            if any(op in tool_name for op in ["get", "show", "detail", "describe"]):
                # Check if they're related to the same resource type
                provider_parts = set(provider_name.split("_"))
                tool_parts = set(tool_name.split("_"))
                common = provider_parts & tool_parts
                # If they share resource type words (excluding common verbs)
                if common - {"get", "list", "show", "detail", "describe", "create", "delete", "update"}:
                    return True
        
        # Pattern 3: Specific Azure resource patterns
        # e.g., operations on specific resource groups/subscriptions
        provider_args = potential_provider["arguments"]
        if isinstance(provider_args, dict):
            # If provider lists/searches resources, dependent tools might need those IDs
            if any(key in provider_args for key in ["subscription_id", "resource_group", "location"]):
                tool_args_dict = tool_info["arguments"]
                if isinstance(tool_args_dict, dict):
                    # Check for resource-specific operations
                    if any(key in tool_args_dict for key in ["resource_id", "vm_name", "storage_account", "id", "name"]):
                        return True
        
        return False

    def _get_tool_schema_params(self, tool_name: str) -> Optional[set]:
        """Return the set of declared parameter names for a tool, or None if unknown.

        Used to strip inventory-injected params that the tool doesn't accept.
        """
        for tool_def in self._tool_definitions:
            fn = tool_def.get("function", {})
            if fn.get("name") == tool_name:
                props = fn.get("parameters", {}).get("properties", {})
                if props:
                    return set(props.keys())
        return None

    async def _prepare_tool_arguments_with_inventory(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Optional[str], Optional[Dict[str, Any]]]:
        """Ground tool arguments using cached inventory and run preflight checks.

        Returns:
            Tuple(enriched_arguments, warning_message, blocked_result)
        """
        prepared_args = dict(arguments or {})
        if not self.inventory_integration:
            return prepared_args, None, None

        warning_message: Optional[str] = None
        blocked_result: Optional[Dict[str, Any]] = None

        try:
            prepared_args = await self.inventory_integration.enrich_tool_parameters(
                tool_name,
                prepared_args,
                {
                    "query": self._message_to_text(self._message_log[-1]) if self._message_log else "",
                },
            )

            # Strip out any parameters the inventory injected that this tool
            # doesn't actually declare in its schema.  The most common case is
            # `subscription_id` / `resource_group` being stamped onto tools
            # that only accept an `intent` string (e.g. azd, documentation).
            allowed_params = self._get_tool_schema_params(tool_name)
            if allowed_params is not None:
                original_keys = set(arguments.keys())
                injected_unknown = {
                    k for k in prepared_args
                    if k not in original_keys and k not in allowed_params
                }
                if injected_unknown:
                    for k in injected_unknown:
                        del prepared_args[k]
                    logger.debug(
                        "🧹 Stripped %d inventory-injected param(s) not in schema for tool '%s': %s",
                        len(injected_unknown),
                        tool_name,
                        sorted(injected_unknown),
                    )

            preflight = await self.inventory_integration.preflight_resource_check(
                tool_name,
                prepared_args,
            )

            if not preflight.get("ok", True):
                blocked_result = preflight.get("result") or {
                    "success": False,
                    "tool_name": tool_name,
                    "error": "Inventory preflight check failed",
                }
            warning_message = preflight.get("warning")
        except Exception as exc:  # pragma: no cover - inventory is best-effort
            logger.debug("Inventory grounding skipped for tool '%s': %s", tool_name, exc)

        return prepared_args, warning_message, blocked_result
    
    async def _execute_single_tool(
        self,
        call: FunctionCallContent,
        arguments: Dict[str, Any],
        tool_name: str,
        iteration: int,
        tool_number: int,
    ) -> Dict[str, Any]:
        """Execute a single tool and return its result with logging."""
        prepared_arguments, inventory_warning, blocked_result = await self._prepare_tool_arguments_with_inventory(
            tool_name,
            arguments,
        )

        try:
            serialized_args = json.dumps(prepared_arguments, ensure_ascii=False)[:500]
        except (TypeError, ValueError):
            serialized_args = str(prepared_arguments)
        
        logger.info(
            "🧰 Tool request %d: %s args=%s",
            tool_number,
            tool_name,
            serialized_args,
        )

        if inventory_warning:
            logger.info("Inventory preflight note for '%s': %s", tool_name, inventory_warning)

        if blocked_result is not None:
            tool_result = blocked_result
        elif tool_name == "azure_cli_execute_command":
            tool_result = await self._maybe_handle_inventory_cli_discovery(prepared_arguments)
            if tool_result is None:
                tool_result = await self._invoke_mcp_tool(tool_name, prepared_arguments)
        else:
            tool_result = await self._invoke_mcp_tool(tool_name, prepared_arguments)
        
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
            except Exception:
                logger.info("MCP tool '%s' response: %s", tool_name, tool_result)
        
        observation_success = bool(tool_result.get("success")) if isinstance(tool_result, dict) else False
        
        # Handle errors
        if isinstance(tool_result, dict):
            if observation_success:
                self._last_tool_failure = None
                logger.debug("Tool '%s' succeeded", tool_name)
            else:
                error_text = self._extract_error_text(tool_result)
                self._last_tool_failure = {"tool": tool_name, "error": error_text}
                logger.warning("MCP tool '%s' failed: %s", tool_name, error_text)
                await self._push_event(
                    "error",
                    f"Tool '{tool_name}' failed",
                    iteration=iteration,
                    tool_name=tool_name,
                    error=error_text,
                )
        
        # Extract CLI command if applicable
        cli_command = None
        if tool_name == "azure_cli_execute_command" and isinstance(prepared_arguments, dict):
            cli_command = prepared_arguments.get("command")
        
        await self._push_event(
            "observation",
            "Tool execution completed",
            iteration=iteration,
            tool_name=tool_name,
            tool_parameters=prepared_arguments,
            cli_command=cli_command,
            tool_result=tool_result,
            is_error=not observation_success,
        )
        
        return tool_result

    async def _maybe_handle_inventory_cli_discovery(
        self,
        prepared_arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Intercept selected az list commands and answer from cached resource inventory."""
        if not self.resource_inventory_client:
            return None

        command = str(prepared_arguments.get("command") or "").strip()
        if not command:
            return None

        command_lower = command.lower()
        resource_type: Optional[str] = None
        source_hint: Optional[str] = None

        if "az containerapp list" in command_lower:
            resource_type = "Microsoft.App/containerApps"
            source_hint = "containerapps"
        elif "az vm list" in command_lower:
            resource_type = "Microsoft.Compute/virtualMachines"
            source_hint = "virtualmachines"
        elif "az resource list" in command_lower:
            if "microsoft.app/containerapps" in command_lower:
                resource_type = "Microsoft.App/containerApps"
                source_hint = "containerapps"
            elif "microsoft.compute/virtualmachines" in command_lower:
                resource_type = "Microsoft.Compute/virtualMachines"
                source_hint = "virtualmachines"

        if not resource_type:
            return None

        filters: Dict[str, Any] = {}
        resource_group = prepared_arguments.get("resource_group")
        if (not isinstance(resource_group, str) or not resource_group.strip()) and "az resource list" in command_lower:
            resource_group = self._extract_cli_option_value(command, ["--resource-group", "-g"])
        if isinstance(resource_group, str) and resource_group.strip():
            filters["resource_group"] = resource_group.strip()

        subscription_id = prepared_arguments.get("subscription_id")
        if (not isinstance(subscription_id, str) or not subscription_id.strip()) and "az resource list" in command_lower:
            subscription_id = self._extract_cli_option_value(command, ["--subscription"])
        if not isinstance(subscription_id, str) or not subscription_id.strip():
            subscription_id = None

        try:
            resources = await self.resource_inventory_client.get_resources(
                resource_type=resource_type,
                subscription_id=subscription_id,
                filters=filters if filters else None,
            )
        except Exception as exc:  # pragma: no cover - inventory should be best-effort
            logger.debug("Inventory discovery interception failed for command '%s': %s", command, exc)
            return None

        logger.info(
            "Inventory-first routing: intercepted CLI discovery command '%s' and returned %d cached resources",
            command,
            len(resources),
        )

        return {
            "success": True,
            "tool_name": "inventory_cached_discovery",
            "source": "resource_inventory_cache",
            "intercepted_cli_command": command,
            "resource_type": resource_type,
            "resource_count": len(resources),
            "items": resources,
            "note": (
                f"Resolved {source_hint or 'resources'} from cached resource inventory instead of CLI discovery."
            ),
        }

    @staticmethod
    def _extract_cli_option_value(command: str, option_names: Sequence[str]) -> Optional[str]:
        """Extract a CLI option value from a command string.

        Supports both `--option value` and `--option=value` forms.
        """
        try:
            tokens = shlex.split(command)
        except Exception:
            tokens = command.split()

        options = set(option_names)
        for idx, token in enumerate(tokens):
            for opt in options:
                if token == opt and idx + 1 < len(tokens):
                    next_token = tokens[idx + 1]
                    if not next_token.startswith("-"):
                        return next_token
                if token.startswith(f"{opt}="):
                    value = token.split("=", 1)[1]
                    return value.strip("\"'") if value else None
        return None

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
            return False, "Azure OpenAI chat client unavailable."
        try:
            from openai import AsyncAzureOpenAI

            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

            async_credential = None
            if api_key:
                client = AsyncAzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
            else:
                from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
                async_credential = AsyncDefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                token = await async_credential.get_token("https://cognitiveservices.azure.com/.default")
                client = AsyncAzureOpenAI(api_key=token.token, azure_endpoint=endpoint, api_version=api_version)

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

            content = raw.choices[0].message.content or ""
            return True, content
        except Exception as exc:  # pragma: no cover - network/service dependency
            logger.error("Prompt execution failed: %s", exc)
            return False, str(exc)

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
                        error_text = self._extract_error_text(result)
                        return {"tool": tool_name, "error": error_text}
        return None

    def _extract_error_text(self, result: Dict[str, Any]) -> str:
        direct_error = result.get("error")
        if direct_error:
            return str(direct_error)

        parsed = result.get("parsed")
        if isinstance(parsed, dict):
            parsed_error = parsed.get("error") or parsed.get("message")
            if parsed_error:
                return str(parsed_error)

        # CLI executor returns stderr as a top-level key
        stderr = result.get("stderr")
        if stderr:
            return str(stderr).strip()

        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, str):
                    continue
                try:
                    parsed_item = json.loads(item)
                except Exception:
                    continue
                if isinstance(parsed_item, dict):
                    # Check nested stderr first (CLI executor payload format)
                    nested_stderr = parsed_item.get("stderr")
                    if nested_stderr:
                        return str(nested_stderr).strip()
                    nested_error = parsed_item.get("error") or parsed_item.get("message")
                    if nested_error:
                        return str(nested_error)

        return "Unknown error"

    def _summarize_message(self, message: ChatMessage) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "role": self._get_message_role(message) or "unknown",
            "text": (getattr(message, "text", "") or "")[:200],
            "content_types": [type(content).__name__ for content in getattr(message, "contents", []) or []],
        }
        result_previews = []
        for content in getattr(message, "contents", []) or []:
            if isinstance(content, FunctionResultContent) and hasattr(content, "result"):
                result = content.result
                if result is not None:
                    serialized = json.dumps(result, ensure_ascii=False)[:200]
                    result_previews.append(serialized)
        if result_previews:
            summary["result_preview"] = result_previews
        return summary

    def _extract_tool_calls(self, message: ChatMessage) -> List[FunctionCallContent]:
        """Extract tool calls from message contents and attributes."""
        tool_calls: List[FunctionCallContent] = []
        
        def _get_call_id(data: Dict[str, Any]) -> str:
            """Extract or generate call ID from various dict formats."""
            return (data.get("call_id") or data.get("id") or 
                   (data.get("function", {}) or {}).get("call_id") or 
                   f"call_{uuid.uuid4().hex[:8]}")
        
        # Extract from contents
        for content in getattr(message, "contents", []) or []:
            if isinstance(content, FunctionCallContent):
                tool_calls.append(content)
            elif isinstance(content, dict):
                name = content.get("name") or content.get("function", {}).get("name")
                arguments = content.get("arguments") or content.get("function", {}).get("arguments")
                tool_calls.append(FunctionCallContent(
                    call_id=_get_call_id(content),
                    name=name or "",
                    arguments=arguments,
                ))
        
        # Extract from tool_calls attribute
        for call in getattr(message, "tool_calls", None) or []:
            if isinstance(call, FunctionCallContent):
                tool_calls.append(call)
            elif isinstance(call, dict):
                tool_calls.append(FunctionCallContent(
                    call_id=_get_call_id(call),
                    name=str(call.get("name") or ""),
                    arguments=call.get("arguments"),
                ))
        
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
        if self.communication_queue:
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
        """Initialize message log with system prompt. Use dynamic prompt if tools are available."""
        system_prompt = self._dynamic_system_prompt if hasattr(self, '_dynamic_system_prompt') else self._SYSTEM_PROMPT
        self._message_log = [ChatMessage(role="system", text=system_prompt)]
    
    async def _populate_inventory_grounding(self) -> None:
        """Build a compact resource inventory summary and inject it into the system prompt.

        Queries the resource inventory client for the most operationally
        relevant Azure resource types, then formats a lightweight grounding
        block that the LLM can use to resolve tool parameters (name, resource
        group, subscription) without needing an extra list/enumerate call.

        The result is stored in ``self._inventory_grounding_context`` and the
        system prompt is refreshed so every subsequent LLM call sees it.
        """
        # Resource types to surface, with short display labels.
        RESOURCE_TYPES: List[tuple] = [
            ("Microsoft.App/containerApps",               "Container Apps"),
            ("Microsoft.Compute/virtualMachines",          "Virtual Machines"),
            ("Microsoft.Network/virtualNetworks",          "Virtual Networks"),
            ("Microsoft.Network/privateEndpoints",         "Private Endpoints"),
            ("Microsoft.Network/networkSecurityGroups",    "NSGs"),
            ("Microsoft.Storage/storageAccounts",          "Storage Accounts"),
            ("Microsoft.ContainerService/managedClusters", "AKS Clusters"),
            ("Microsoft.KeyVault/vaults",                  "Key Vaults"),
            ("Microsoft.Web/sites",                        "App Services"),
            ("Microsoft.Network/privateDnsZones",          "Private DNS Zones"),
            ("Microsoft.Network/loadBalancers",            "Load Balancers"),
        ]

        MAX_PER_TYPE = 15  # cap to keep token count reasonable

        lines: List[str] = []
        for resource_type, label in RESOURCE_TYPES:
            try:
                resources = await self.resource_inventory_client.get_resources(resource_type)
            except Exception as exc:
                logger.debug("Inventory grounding: skipping %s (%s)", resource_type, exc)
                continue

            if not resources:
                continue

            entries = []
            for r in resources[:MAX_PER_TYPE]:
                name = r.get("resource_name") or r.get("name", "")
                rg   = r.get("resource_group") or r.get("resourceGroup", "")
                if name:
                    entries.append(f"{name} ({rg})" if rg else name)

            if entries:
                suffix = f" … +{len(resources) - MAX_PER_TYPE} more" if len(resources) > MAX_PER_TYPE else ""
                lines.append(f"  • {label}: {', '.join(entries)}{suffix}")

        if lines:
            self._inventory_grounding_context = "\n".join(lines)
            logger.info(
                "📦 Inventory grounding populated: %d resource type(s), %d chars",
                len(lines),
                len(self._inventory_grounding_context),
            )
            self._refresh_system_prompt()
        else:
            logger.info("📦 Inventory grounding: no cached resources found yet")

    def _refresh_system_prompt(self) -> None:
        """Refresh the system prompt with current tool information."""
        self._dynamic_system_prompt = self._build_dynamic_system_prompt(
            self._tool_definitions,
            self._tool_source_map
        )
        # Update the system message in the log
        if self._message_log and self._message_log[0].role == "system":
            self._message_log[0] = ChatMessage(role="system", text=self._dynamic_system_prompt)
        else:
            self._message_log.insert(0, ChatMessage(role="system", text=self._dynamic_system_prompt))
        
        logger.info("🔄 System prompt refreshed with tool catalog information")

    def _new_session_id(self) -> str:
        return f"maf-mcp-{uuid.uuid4()}"

    def _build_success_response(
        self,
        user_message: str,
        final_text: str,
        elapsed: float,
        reasoning: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a successful response dictionary."""
        metadata = {
            "session_id": self.session_id,
            "duration_seconds": elapsed,
            "tool_calls_made": 0,
            "available_tools": len(self._tool_definitions),
            "message_count": max(len(self._message_log) - 1, 0),
            "reasoning_iterations": len(reasoning),
            "max_iterations_reached": False,
            "agent_framework_enabled": True,  # Direct OpenAI SDK
            "reasoning_trace": reasoning,
            "error": None,
            "last_tool_failure": None,
            "last_tool_request": None,
            "last_tool_output": None,
        }
        
        history = self.get_conversation_history()
        history.append(
            {
                "role": "assistant",
                "content": final_text,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        
        cache_stats_manager.record_agent_request(
            agent_name="mcp_orchestrator",
            response_time_ms=elapsed * 1000,
            was_cache_hit=False,
            had_error=False,
            software_name="azure_mcp_orchestrator",
            version="maf_preview",
            url="/api/azure-mcp/chat",
        )
        
        return {
            "success": True,
            "response": final_text,
            "conversation_history": history,
            "metadata": metadata,
        }

    def _build_failure_response(self, user_message: str, elapsed: float, error: str) -> Dict[str, Any]:
        fallback = (
            "The MCP orchestration service is not available right now. "
            "Ensure AZURE_OPENAI_ENDPOINT and authentication are configured, then retry."
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
