#!/usr/bin/env python3
"""AsyncAzureOpenAI-powered orchestrator for Azure MCP Server tools."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager, nullcontext
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

try:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.cache_stats_manager import cache_stats_manager
    from app.agentic.eol.utils.response_formatter import ResponseFormatter
except ModuleNotFoundError:  # pragma: no cover - packaged runtime fallback
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

try:
    from app.agentic.eol.utils.mcp_composite_client import CompositeMCPClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from utils.mcp_composite_client import CompositeMCPClient  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        CompositeMCPClient = None  # type: ignore[assignment]

try:
    from app.agentic.eol.agents.monitor_agent import MonitorAgent  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from agents.monitor_agent import MonitorAgent  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        MonitorAgent = None  # type: ignore[assignment]


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

import html

logger = get_logger(__name__, level=os.getenv("LOG_LEVEL", "DEBUG"))


# Shared formatter instance
_response_formatter = ResponseFormatter()


# Log package availability at module load time
logger.info(
    "MCP Orchestrator dependencies: Azure Identity=%s",
    _DEFAULT_CREDENTIAL_AVAILABLE,
)


class MCPOrchestratorAgent:
    """High-level Azure MCP orchestrator using AsyncAzureOpenAI with ReAct loop."""

    _SYSTEM_PROMPT = """You are the Azure modernization co-pilot for enterprise operations teams.
You have access to Azure MCP tools that provide REAL-TIME data from Azure services.
Each tool's description tells you WHEN to use it — follow those descriptions to pick the right tool.

CRITICAL RULE — NO FABRICATION:
You MUST call a tool before presenting ANY Azure resource data.
NEVER generate fake subscription IDs, resource names, or example data.
If no tool exists for the request, say so — do NOT invent a response.
If a tool call fails, report the error — do NOT substitute made-up data.

SAFETY — DESTRUCTIVE OPERATIONS:
Before executing any tool that creates, updates, deletes, or deploys resources:
1. Gather all required information first (via tool calls or intelligent defaults).
2. Present a COMPLETE plan to the user in ONE message.
3. Ask for confirmation ONCE and WAIT — do NOT execute without approval.

WORKFLOW — READ OPERATIONS:
1. Call the appropriate MCP tool(s) FIRST to fetch real data.
2. Wait for tool results before responding.
3. Format ONLY the data returned by tools into your response.

SRE OPERATIONS:
When users ask about resource health, incidents, troubleshooting, performance issues, or remediation:
→ Use Azure SRE Agent tools (31 tools available) for specialized SRE operations.

RESOURCE CONFIGURATION DISCOVERY:
→ Bulk queries across resources: Use query_app_service_configuration, query_container_app_configuration, query_aks_configuration, query_apim_configuration
→ Example prompts: "Which apps have Dapr enabled?", "Show me all web apps running .NET 6", "Which AKS clusters have autoscaling enabled?"

HEALTH CHECKS & DIAGNOSTICS:
→ Resource health: Use check_resource_health (requires full resource ID). For Container Apps: use check_container_app_health. For AKS: use check_aks_cluster_health.
→ Service-specific diagnostics: Use diagnose_app_service for App Service issues, diagnose_apim for APIM issues
→ Diagnostic logs: Use get_diagnostic_logs (requires workspace_id and resource_id)
→ Performance metrics: Use get_performance_metrics and identify_bottlenecks

INCIDENT RESPONSE:
→ Automated triage: Use triage_incident for incident analysis, log correlation, and root cause investigation
→ Log analysis: Use search_logs_by_error for pattern-based log search
→ Alert correlation: Use correlate_alerts for temporal and resource-based correlation
→ Incident reporting: Use generate_incident_summary for structured reports

SELF-DOCUMENTATION:
→ If users ask "What can you help me with?" or "What are your capabilities?": Use describe_capabilities
→ If users ask for example prompts: Use get_prompt_examples with category (app_service, container_apps, aks, apim, incident_response, performance, configuration, all)

REMEDIATION & NOTIFICATIONS:
→ For destructive remediation actions (restart, scale, clear_cache), ALWAYS present a plan with plan_remediation and wait for approval.
→ Use send_teams_notification or send_teams_alert to notify teams about critical incidents.

IMPORTANT AZURE CLI USAGE:
→ When using azure_cli_execute_command for Log Analytics queries, use --analytics-query (NOT --query) for KQL queries.
→ NEVER use the 'speech' tool for SRE operations - it's only for Azure AI Services Speech (speech-to-text).

AZURE DIAGNOSTIC SETTINGS:
When users ask to enable diagnostic settings or logging for Azure resources:
→ ⚠️ Virtual Machines (Microsoft.Compute/virtualMachines) do NOT support diagnostic settings for platform logs/metrics.
→ For VMs: Use Azure Monitor Agent (AMA) for guest OS metrics, logs, and performance counters instead of diagnostic settings.
→ For other resources: Use 'az monitor diagnostic-settings list --resource <resource-id>' to discover supported log/metric categories BEFORE creating settings.
→ Common resources supporting diagnostic settings: Storage Accounts, Key Vaults, App Services, Container Apps, AKS, SQL Databases, Network Security Groups.
→ Always verify supported categories first - attempting to configure unsupported categories will fail with BadRequest error.

FORMATTING:
- Return responses as raw HTML (no markdown code blocks, no backticks).
- Include at least one HTML <table> when presenting structured data.
- After tables, add a brief <p> summary of key findings.
- For utilization/performance data (CPU, memory, disk, network metrics):

  CRITICAL: When you receive time-series data with multiple data points over time (timestamps with values), you MUST create ASCII/Unicode line charts.
  DO NOT create summary tables showing Average/Current/Min/Max - users want to SEE the trend visually.

  * **Current/snapshot metrics** (single point in time): Use HTML progress bars with gradient colors
  * **Time-series/historical metrics** (multiple data points over time): MUST use ASCII/Unicode line charts to visualize trends

- Example progress bar format for current resource utilization (single value):
  <div style="margin: 10px 0;">
    <strong>CPU Usage:</strong> 65%
    <div style="background: #e0e0e0; border-radius: 4px; height: 20px; width: 100%; margin: 5px 0;">
      <div style="background: linear-gradient(90deg, #4CAF50 0%, #FFC107 70%, #F44336 90%); height: 100%; width: 65%; border-radius: 4px;"></div>
    </div>
  </div>

- Example line chart format for time-series utilization data (REQUIRED when you have timestamps):
  <pre style="font-family: monospace; line-height: 1.2; background: #f5f5f5; padding: 10px; border-radius: 4px;">
  CPU Usage Over Time (%)
  100 │
   90 │                    ╭─╮
   80 │                ╭───╯ ╰─╮
   70 │            ╭───╯       ╰──╮
   60 │        ╭───╯              ╰──╮
   50 │    ╭───╯                     ╰──╮
   40 │╭───╯                            ╰──╮
   30 ││                                   ╰──╮
   20 ││                                      ╰─╮
   10 ││                                        ╰─╮
    0 ╰─────────────────────────────────────────╯
      15:00  15:15  15:30  15:45  16:00  16:15

  Memory Usage Over Time (%)
  100 │                              ╭───╮
   90 │                          ╭───╯   ╰─╮
   80 │                      ╭───╯         ╰──╮
   70 │                  ╭───╯                ╰──╮
   60 │              ╭───╯                       ╰─╮
   50 │          ╭───╯                             ╰─╮
   40 │      ╭───╯                                   ╰─╮
   30 │  ╭───╯                                         ╰─╮
   20 │╭─╯                                              ╰─╮
   10 ││                                                 ╰─╮
    0 ╰─────────────────────────────────────────────────╯
      15:00  15:15  15:30  15:45  16:00  16:15
  </pre>

- For line charts: Use Unicode box-drawing characters (│ ─ ╭ ╮ ╰ ╯) to create visual trend lines
- Map each data point to the appropriate y-axis position based on its percentage value
- Include timestamps on the x-axis showing the time range
- Use color coding for progress bars: Green (0-60%), Yellow (60-80%), Red (80-100%)
- NEVER use summary tables (Average/Current/Min/Max) for time-series metrics - always create line charts
- Your entire response must be valid HTML insertable into a webpage."""

    @staticmethod
    def _build_dynamic_system_prompt(tool_definitions: List[Dict[str, Any]], tool_source_map: Dict[str, str]) -> str:
        """Build a dynamic system prompt with a concise tool catalog summary.

        Tool routing logic now lives in each tool's description (set by
        CompositeMCPClient), so this only adds a short inventory section.
        """
        base_prompt = MCPOrchestratorAgent._SYSTEM_PROMPT

        if not tool_definitions:
            return base_prompt

        # Group tools by source for a compact summary
        tools_by_source: Dict[str, int] = {}
        for tool in tool_definitions:
            tool_name = tool.get("function", {}).get("name", "")
            source = tool_source_map.get(tool_name, "unknown")
            tools_by_source[source] = tools_by_source.get(source, 0) + 1

        source_labels = {
            "azure": "Azure MCP Server",
            "azure_cli": "Azure CLI Executor",
            "os_eol": "OS EOL Server",
            "inventory": "Inventory Server",
            "monitor": "Azure Monitor Community",
            "sre": "Azure SRE Agent",
        }

        catalog_lines = [f"  • {source_labels.get(src, src)}: {count} tools" for src, count in tools_by_source.items()]
        catalog_section = "\n\nAVAILABLE TOOL SOURCES:\n" + "\n".join(catalog_lines)

        # Disambiguation for commonly confused Azure services
        disambiguation = (
            "\n\nSERVICE DISAMBIGUATION (read carefully):"
            "\n• 'Container Apps' (Azure Container Apps) → use azure_cli_execute_command with 'az containerapp list'. "
            "Do NOT use ACR, App Service, App Config, or Function App tools."
            "\n• 'Container Registry' (ACR) → use the acr/container_registries tools."
            "\n• 'App Service' (Web Apps) → use the appservice tools."
            "\n• 'App Configuration' → use the appconfig tools."
            "\n• 'Function Apps' → use the functionapp tools."
            "\n\n⚠️ CRITICAL TOOL ROUTING:"
            "\n• The 'speech' tool is ONLY for Azure AI Services Speech (speech-to-text, text-to-speech)."
            "\n• NEVER use 'speech' for resource health, diagnostics, SRE operations, or Azure resource management."
            "\n• For resource health checks: use check_resource_health (SRE) or resourcehealth (Azure MCP)."
            "\n• For SRE operations: use the sre_* tools (check_resource_health, triage_incident, get_diagnostic_logs, etc.)."
            "\n\nMONITOR RESOURCES:"
            "\nWhen the user asks about Azure Monitor resources, workbooks, alerts, queries, or monitoring for any service:"
            "\n→ Call the monitor_agent tool with the user's full request. It handles discovery AND deployment."
            "\n→ Do NOT try to call monitor tools directly — always delegate to monitor_agent."
            "\n\nSRE OPERATIONS:"
            "\nWhen the user asks about resource health, incidents, diagnostics, troubleshooting, performance issues, or remediation:"
            "\n→ Use check_resource_health (SRE tool) for Azure resource availability and health status (requires full resource ID)."
            "\n→ Use triage_incident for incident analysis, log correlation, and root cause investigation."
            "\n→ Use get_performance_metrics and identify_bottlenecks for performance analysis."
            "\n→ Use get_diagnostic_logs and search_logs_by_error for log analysis and error tracking."
            "\n→ For remediation: plan_remediation (returns plan), execute_safe_restart, scale_resource (require approval)."
            "\n→ Use send_teams_alert or send_teams_notification to notify on-call teams about critical incidents."
            "\n→ ALWAYS require user confirmation before executing destructive SRE operations (restart, scale, remediation)."
            "\n\nCOMMON SRE WORKFLOWS:"
            "\n• Health check for Container Apps → First: azure_cli_execute_command('az containerapp list'), Then: check_resource_health(resource_id)"
            "\n• Health check for any Azure resource → If you don't have the resource ID, list/search resources first, Then: check_resource_health(resource_id)"
            "\n• Incident investigation → triage_incident (auto-gathers logs and correlates events), Then: get_diagnostic_logs for detailed analysis"
            "\n• Performance issue → get_performance_metrics (last 24h by default), Then: identify_bottlenecks to analyze patterns"
            "\n• Service restart → plan_remediation first (shows impact), Then: execute_safe_restart with user approval"
        )

        return base_prompt + catalog_section + disambiguation

    def __init__(
        self,
        *,
        chat_client: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
        tool_definitions: Optional[Sequence[Dict[str, Any]]] = None,
        max_reasoning_iterations: Optional[int] = None,
        default_temperature: Optional[float] = None,
    ) -> None:
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
        self._initialise_message_log()

        # Initialize communication queue lazily to avoid event loop issues
        self.communication_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
        self.communication_buffer: List[Dict[str, Any]] = []
        self.max_buffer_size = 100
        # High safety limit to allow complex multi-step reasoning without artificial constraints
        # Time-based warnings will notify user of long-running operations
        configured_iterations = max_reasoning_iterations or int(os.getenv("MCP_AGENT_MAX_ITERATIONS", "50"))
        self._max_reasoning_iterations = max(configured_iterations, 1)
        self._default_temperature = float(default_temperature or os.getenv("MCP_AGENT_TEMPERATURE", "0.2"))

    def _ensure_communication_queue(self) -> None:
        """Ensure communication queue is initialized (lazy initialization)."""
        if self.communication_queue is None:
            self.communication_queue = asyncio.Queue()

    # ------------------------------------------------------------------
    # Public API consumed by FastAPI endpoints
    # ------------------------------------------------------------------
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """Process a conversational turn, invoking MCP tools when requested."""
        self._ensure_communication_queue()
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
        
        # Log tool availability for this request
        tool_count = len(self._tool_definitions) if self._tool_definitions else 0
        logger.info(f"🛠️  Processing message with {tool_count} tools available (mcp_ready={mcp_ready})")
        logger.info(f"💬 Session {self.session_id}: Processing message #{len(self._message_log)} (history: {len(self._message_log)-1} messages)")

        # Append user message and enter the ReAct loop
        user_chat = ChatMessage(role="user", text=user_message)
        self._message_log.append(user_chat)

        for iteration in range(1, self._max_reasoning_iterations + 1):
            # Summarize older messages to keep context window manageable
            await self._summarize_old_messages()

            # Check for timeout before each iteration (50s threshold for 60s timeout)
            elapsed = time.time() - start_time
            if elapsed > 50:
                logger.warning(
                    "⏱️ Approaching timeout limit (%.1fs elapsed) - returning partial results",
                    elapsed
                )
                await self._push_event(
                    "timeout_warning",
                    "Approaching response timeout - returning current results",
                    iteration=iteration,
                    elapsed_seconds=elapsed
                )
                success = True  # Mark as success since we're returning partial results
                if final_text:
                    final_text += "\n\n<p><em>Note: Processing stopped to avoid timeout. Results may be incomplete.</em></p>"
                else:
                    final_text = "<p>Processing is taking longer than expected. Please try breaking your request into smaller parts or simplifying the query.</p>"
                break
            
            # Send progress updates at time thresholds
            if elapsed > 40 and iteration > 1:
                await self._push_event(
                    "progress",
                    f"Still processing (40s elapsed, iteration {iteration}) - will timeout at 60s...",
                    iteration=iteration,
                    elapsed_seconds=elapsed
                )
            elif elapsed > 30 and iteration > 1:
                await self._push_event(
                    "progress",
                    f"Processing complex request (30s elapsed, iteration {iteration})...",
                    iteration=iteration,
                    elapsed_seconds=elapsed
                )
            elif elapsed > 10 and iteration > 1:
                await self._push_event(
                    "progress",
                    f"Continuing analysis (10s elapsed, iteration {iteration})...",
                    iteration=iteration,
                    elapsed_seconds=elapsed
                )
            
            try:
                # Unified LLM path: always use direct OpenAI SDK for full
                # control over tool execution via the ReAct loop.
                from openai import AsyncAzureOpenAI

                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
                deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

                direct_client = None
                try:
                    # Convert message history to OpenAI format
                    openai_messages = self._build_openai_messages()

                    # Authenticate
                    if api_key:
                        direct_client = AsyncAzureOpenAI(
                            api_key=api_key,
                            azure_endpoint=endpoint,
                            api_version=api_version,
                        )
                    elif _DEFAULT_CREDENTIAL_AVAILABLE and DefaultAzureCredential:
                        from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
                        credential = AsyncDefaultAzureCredential(
                            exclude_interactive_browser_credential=True,
                            exclude_shared_token_cache_credential=True,
                            exclude_visual_studio_code_credential=True,
                            exclude_powershell_credential=True,
                        )
                        token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                        direct_client = AsyncAzureOpenAI(
                            api_key=token.token,
                            azure_endpoint=endpoint,
                            api_version=api_version,
                        )
                    else:
                        raise RuntimeError("No authentication method available")

                    # Build request kwargs
                    create_kwargs: Dict[str, Any] = {
                        "model": deployment,
                        "messages": openai_messages,
                        "temperature": self._default_temperature,
                        "max_tokens": 3000,
                    }
                    if self._tool_definitions:
                        create_kwargs["tools"] = [
                            {"type": "function", "function": t.get("function", t)}
                            for t in self._tool_definitions
                        ]

                    raw_response = await direct_client.chat.completions.create(**create_kwargs)

                    # Convert to internal message format
                    choice = raw_response.choices[0]
                    if choice.message.tool_calls:
                        tool_call_contents = []
                        for tc in choice.message.tool_calls:
                            try:
                                arguments = json.loads(tc.function.arguments) if tc.function.arguments else {}
                            except json.JSONDecodeError as json_err:
                                logger.error(
                                    "Failed to parse tool call arguments: %s (tool=%s, args_preview=%s...)",
                                    json_err,
                                    tc.function.name,
                                    tc.function.arguments[:200] if tc.function.arguments else "None",
                                )
                                await self._push_event("error", f"Malformed tool call for {tc.function.name}", tool_name=tc.function.name, error=str(json_err))
                                continue

                            tool_call_contents.append(FunctionCallContent(
                                call_id=tc.id,
                                name=tc.function.name,
                                arguments=arguments,
                            ))

                        if tool_call_contents:
                            response = ChatResponse(messages=[ChatMessage(
                                role="assistant",
                                contents=tool_call_contents,
                            )])
                        else:
                            response = ChatResponse(messages=[ChatMessage(
                                role="assistant",
                                text="I encountered an error generating the tool call. Please try simplifying your request.",
                            )])
                    else:
                        response = ChatResponse(messages=[ChatMessage(
                            role="assistant",
                            text=choice.message.content or "",
                        )])
                finally:
                    if direct_client:
                        try:
                            await direct_client.close()
                        except Exception:  # pragma: no cover
                            pass
                
                logger.debug(
                    "LLM returned %d message(s) for iteration %d",
                    len(response.messages),
                    iteration,
                )
                try:
                    for idx, raw_message in enumerate(response.messages, start=1):
                        logger.info(
                            "🗂️ LLM message %d/%d: %s",
                            idx,
                            len(response.messages),
                            self._summarize_message(raw_message),
                        )
                except Exception:  # pragma: no cover - defensive logging
                    logger.debug("Unable to log LLM messages", exc_info=True)
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
            # Extract tool calls from the FIRST assistant message before AF error handling
            first_assistant_message: Optional[ChatMessage] = None
            for candidate in response.messages:
                if self._get_message_role(candidate) != "assistant":
                    continue
                if first_assistant_message is None:
                    first_assistant_message = candidate
                    # Try to extract tool calls from the first assistant message
                    first_calls = self._extract_tool_calls(candidate)
                    if first_calls:
                        logger.info("✅ Extracted %d tool calls from first assistant message", len(first_calls))
                        tool_calls = first_calls
                        assistant_message = candidate
                        break
                assistant_message = candidate
                candidate_calls = self._extract_tool_calls(candidate)
                if candidate_calls:
                    tool_calls = candidate_calls
                    break
            if not assistant_message:
                if self._last_tool_failure:
                    logger.error(
                        "LLM response contained no assistant message after tool failure",
                        extra={"tool_failure": self._last_tool_failure},
                    )
                else:
                    logger.error(
                        "LLM response contained no assistant message; raw messages: %s",
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
                    "🛎️ LLM requested %d tool(s) this iteration: %s",
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

                # Guard against hallucinated data: if this is the first
                # iteration (no tools called yet) and the response already
                # contains structured data (tables), the LLM is fabricating.
                # Inject a correction and force another iteration.
                if (
                    iteration == 1
                    and tool_calls_made == 0
                    and mcp_ready
                    and self._tool_definitions
                    and final_text
                    and any(marker in final_text.lower() for marker in ["<table", "| ---", "|---", "subscription id"])
                ):
                    logger.warning(
                        "⚠️ LLM returned structured data on first iteration without calling any tools — likely hallucination. Forcing retry."
                    )
                    # Replace the assistant message with a correction prompt
                    self._message_log.append(ChatMessage(
                        role="user",
                        text=(
                            "STOP. You returned data without calling any tools first. "
                            "That data is fabricated. You MUST call the appropriate MCP tool(s) "
                            "to fetch real Azure data before responding. Try again."
                        ),
                    ))
                    continue
                
                # Check if this is a confirmation question - if so, stop immediately to avoid duplicates
                confirmation_indicators = [
                    "reply 'yes' to",
                    "do you want to proceed",
                    "please confirm",
                    "type 'yes' to confirm",
                    "reply yes to",
                    "[pick one by typing",
                ]
                is_confirmation_request = any(indicator in final_text.lower() for indicator in confirmation_indicators)
                
                if is_confirmation_request:
                    logger.info(f"🛑 Detected confirmation request at iteration {iteration} - stopping to wait for user response")
                
                await self._push_event(
                    "synthesis",
                    final_text or "Response ready",
                    iteration=iteration,
                )
                break

            # Create detailed tool list for display
            tool_names = [call.name for call in tool_calls]
            tool_details = []
            tool_calls_details = []
            for call in tool_calls:
                args_preview = self._parse_call_arguments(call)
                args_str = json.dumps(args_preview, ensure_ascii=False)[:200]
                tool_details.append(f"{call.name}({args_str})")
                
                # Store full tool call details for UI display
                tool_calls_details.append({
                    "tool_name": call.name,
                    "parameters": args_preview
                })
            
            await self._push_event(
                "action",
                f"Invoking {len(tool_calls)} Azure MCP tool(s): {', '.join(tool_names)}",
                iteration=iteration,
                tool_names=tool_names,
                tool_details=tool_details,
                tool_calls=tool_calls_details,
            )

            logger.info(
                "🚀 Iteration %d invoking Azure MCP tools: %s",
                iteration,
                ", ".join(tool_names),
            )

            # Analyze dependencies and group tools for parallel execution
            execution_groups = self._plan_tool_execution(tool_calls)
            
            for group_idx, tool_group in enumerate(execution_groups):
                if len(tool_group) > 1:
                    logger.info(
                        "⚡ Executing %d independent tools in parallel (group %d/%d)",
                        len(tool_group),
                        group_idx + 1,
                        len(execution_groups),
                    )
                    # Execute tools in parallel
                    tasks = []
                    for call in tool_group:
                        arguments = self._parse_call_arguments(call)
                        tool_name = call.name or "unknown_tool"
                        tasks.append(self._execute_single_tool(call, arguments, tool_name, iteration, tool_calls_made + len(tasks)))
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Process results and append to message log
                    for call, result in zip(tool_group, results):
                        tool_calls_made += 1
                        if isinstance(result, Exception):
                            logger.error("Tool execution failed with exception: %s", result)
                            error_result = {"success": False, "error": str(result)}
                            result_message = self._create_tool_result_message(call.call_id, error_result)
                        else:
                            result_message = self._create_tool_result_message(call.call_id, result)
                        self._message_log.append(result_message)
                else:
                    # Single tool - execute sequentially
                    call = tool_group[0]
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

                    # Extract CLI command if this is azure_cli_execute_command
                    cli_command = None
                    if tool_name == "azure_cli_execute_command" and isinstance(arguments, dict):
                        cli_command = arguments.get("command")

                    await self._push_event(
                        "observation",
                        "Tool execution completed",
                        iteration=iteration,
                        tool_name=tool_name,
                        tool_parameters=arguments,
                        cli_command=cli_command,
                        tool_result=tool_result,
                        is_error=not observation_success,
                    )

                    result_message = self._create_tool_result_message(call.call_id, tool_result)
                    self._message_log.append(result_message)

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

        if get_workbook_mcp_client is not None:
            try:
                workbook_client = await get_workbook_mcp_client()
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("Azure Monitor Community MCP server unavailable: %s", exc)
            else:
                logger.debug(
                    "Azure Monitor Community MCP client initialised; catalog size hint=%s",
                    len(getattr(workbook_client, "available_tools", []) or []),
                )
                client_entries.append(("monitor", workbook_client))
        else:
            logger.debug(
                "Azure Monitor Community MCP client import resolved to None; skipping registration (error=%s)",
                _workbook_mcp_import_error,
            )

        if get_sre_mcp_client is not None:
            try:
                sre_client = await get_sre_mcp_client()
            except SREMCPDisabledError:
                logger.info("SRE MCP server disabled via configuration; skipping registration")
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("SRE MCP server unavailable: %s", exc)
            else:
                logger.debug(
                    "SRE MCP client initialised; catalog size hint=%s",
                    len(getattr(sre_client, "available_tools", []) or []),
                )
                client_entries.append(("sre", sre_client))
        else:
            logger.debug(
                "SRE MCP client import resolved to None; skipping registration (error=%s)",
                _sre_mcp_import_error,
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
        # Intercept the monitor_agent meta-tool
        if tool_name == "monitor_agent":
            return await self._handle_monitor_delegation(arguments)

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
    
    async def _execute_single_tool(
        self,
        call: FunctionCallContent,
        arguments: Dict[str, Any],
        tool_name: str,
        iteration: int,
        tool_number: int,
    ) -> Dict[str, Any]:
        """Execute a single tool and return its result with logging."""
        try:
            serialized_args = json.dumps(arguments, ensure_ascii=False)[:500]
        except (TypeError, ValueError):
            serialized_args = str(arguments)
        
        logger.info(
            "🧰 Tool request %d: %s args=%s",
            tool_number,
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
            except Exception:
                logger.info("MCP tool '%s' response: %s", tool_name, tool_result)
        
        observation_success = bool(tool_result.get("success")) if isinstance(tool_result, dict) else False
        
        # Handle errors
        if isinstance(tool_result, dict):
            if observation_success:
                self._last_tool_failure = None
                logger.debug("Tool '%s' succeeded", tool_name)
            else:
                error_text = str(tool_result.get("error") or "Unknown error")
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
        if tool_name == "azure_cli_execute_command" and isinstance(arguments, dict):
            cli_command = arguments.get("command")
        
        await self._push_event(
            "observation",
            "Tool execution completed",
            iteration=iteration,
            tool_name=tool_name,
            tool_parameters=arguments,
            cli_command=cli_command,
            tool_result=tool_result,
            is_error=not observation_success,
        )
        
        return tool_result

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

            if api_key:
                client = AsyncAzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
            else:
                from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
                credential = AsyncDefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                token = await credential.get_token("https://cognitiveservices.azure.com/.default")
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
                        error_text = str(result.get("error") or "Unknown error")
                        return {"tool": tool_name, "error": error_text}
        return None

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
