#!/usr/bin/env python3
"""Microsoft Agent Framework powered orchestrator for Azure MCP Server tools."""

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

# Agent Framework message classes - using fallbacks since they're not in the installed version
_AGENT_FRAMEWORK_AVAILABLE = False
_AGENT_FRAMEWORK_IMPORT_ERROR = None

# We'll use our fallback classes defined below
ChatMessage = None
ChatResponse = None
FunctionCallContent = None
FunctionResultContent = None
TextContent = None

# Try to import ChatAgent - it's available in agent_framework root module
_CHAT_AGENT_AVAILABLE = False
_CHAT_AGENT_IMPORT_ERROR = None
ChatAgent = None
try:
    from agent_framework import ChatAgent  # type: ignore[import-not-found]
    _CHAT_AGENT_AVAILABLE = True
except (ModuleNotFoundError, ImportError, AttributeError) as exc:
    _CHAT_AGENT_IMPORT_ERROR = exc
    ChatAgent = None  # type: ignore[assignment]

# Always define fallback message classes - they're used even when ChatAgent is available
# because agent_framework doesn't export these message classes in the installed version
class TextContent:  # minimal fallback matching agent_framework interface
    def __init__(self, text: Optional[str] = None, **_: Any) -> None:
        self.text = text or ""
        self.type = "text"  # Required by agent_framework
    
    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        result = {"type": self.type, "text": self.text}
        if exclude_none:
            return {k: v for k, v in result.items() if v is not None}
        return result

class FunctionCallContent:  # minimal fallback matching agent_framework interface
    def __init__(self, *, call_id: Optional[str] = None, name: str = "", arguments: Any = None, **_: Any) -> None:
        self.call_id = call_id or f"call_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.arguments = arguments or {}
        self.type = "function_call"  # Required by agent_framework
    
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

class FunctionResultContent:  # minimal fallback matching agent_framework interface
    def __init__(self, *, call_id: str, result: Any = None, **_: Any) -> None:
        self.call_id = call_id
        self.result = result
        self.type = "function_result"  # Required by agent_framework
    
    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        result_dict = {
            "type": self.type,
            "call_id": self.call_id,
            "result": self.result
        }
        if exclude_none:
            return {k: v for k, v in result_dict.items() if v is not None}
        return result_dict

class ChatMessage:  # minimal fallback matching agent_framework interface
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
        self.author_name = author_name  # Required by agent_framework
        self.additional_properties = additional_properties or {}  # Required by agent_framework

class ChatResponse:  # minimal fallback matching agent_framework interface
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

# Log package availability at module load time
logger.info(
    "MCP Orchestrator dependencies: Chat Client=%s, Azure Identity=%s",
    _AGENT_FRAMEWORK_CHAT_AVAILABLE,
    _DEFAULT_CREDENTIAL_AVAILABLE,
)

# Log ChatAgent import error if it failed (informational only - we don't use it)
if not _CHAT_AGENT_AVAILABLE and _CHAT_AGENT_IMPORT_ERROR:
    logger.debug("ChatAgent not available (we use CompositeMCPClient instead): %s", _CHAT_AGENT_IMPORT_ERROR)


class MCPOrchestratorAgent:
    """High-level Azure MCP orchestrator built on the Microsoft Agent Framework."""

    _SYSTEM_PROMPT = """You are the Azure modernization co-pilot for enterprise operations teams.
You have access to Azure Model Context Protocol (MCP) tools that provide REAL-TIME data from Azure services.

🚨 CRITICAL REQUIREMENT - USER CONFIRMATION FOR DESTRUCTIVE OPERATIONS 🚨
BEFORE executing ANY tool that creates, updates, deletes, or deploys resources, you MUST:
1. Gather all necessary information FIRST (via tool calls or intelligent defaults)
2. Present a COMPLETE plan to the user in ONE message showing:
   - What action will be taken
   - What resources will be affected
   - What values/parameters will be used
3. Ask for confirmation ONCE: "Do you want to proceed? Reply 'yes' to confirm."
4. WAIT for user confirmation - DO NOT execute without approval
5. DO NOT ask the same questions multiple times - gather info first, then ask for approval once

Destructive operations include tools with names containing:
- create, deploy, provision, add, insert, new
- update, modify, change, edit, patch, set, configure
- delete, remove, destroy, terminate, drop

Example: "I will deploy the 'Virtual Machine Overview' workbook with these settings:
- Subscription: Production (12345-abcd)
- Resource Group: monitoring-rg
- Location: eastus
Do you want to proceed? Reply 'yes' to confirm."

🚨 CRITICAL REQUIREMENT - YOU MUST CALL TOOLS FIRST (for read operations) 🚨
For READ-ONLY operations (list, get, show, describe, query), you are FORBIDDEN from responding without calling tools first.
Your response process for read operations MUST be:
1. FIRST: Call the appropriate MCP tool(s) to fetch real data
2. THEN: Wait for the tool results
3. ONLY AFTER receiving tool results: Format the data into an HTML response

DO NOT:
- ❌ Say "I will call the tool" without actually calling it
- ❌ Say "Calling the tool now..." and then respond with text
- ❌ Generate mock, example, or placeholder data (no "Subscription A", "xxxx-xxxx-xxxx", etc.)
- ❌ Create fake tables with sample data
- ❌ Respond with any text before calling and receiving tool results FOR READ OPERATIONS
- ❌ Execute destructive operations without user confirmation

Tool Usage Rules:
- For questions about Azure resources (subscriptions, resource groups, workspaces, storage, VMs, etc.) → Call Azure MCP Server tools
- For querying OS/software inventory DATA within a Log Analytics Workspace → Call Inventory Server tools (law_get_*)
- For EOL (End of Life) queries → Call OS EOL tools
- IMPORTANT: Log Analytics Workspace is an Azure resource - use Azure MCP Server to list/show workspaces
- IMPORTANT: Different Azure compute services are NOT interchangeable:
  * Virtual Machines (VMs) ≠ App Services ≠ Container Apps ≠ AKS ≠ Azure Virtual Desktop
  * Container Apps are managed containerized applications (separate from App Services)
  * Use the correct specific tool or Azure CLI command for each service type
- When in doubt → Call Azure CLI Executor to run 'az' commands for any Azure service

Formatting guidance (ONLY AFTER tool results received):
- Return responses as raw HTML only (NO markdown code blocks, NO backticks, NO ```html)
- Always include at least one HTML table in the final response using <table>, <thead>, and <tbody>
- When an Azure MCP tool returns structured data, render it as a concise table with intuitive columns
- Paginate large result sets by showing only the first few rows
- After the table(s), add a brief <p> summary highlighting the most important findings
- Your entire response should be valid HTML that can be inserted directly into a webpage

REMEMBER: Tool call FIRST, response SECOND. Never respond without calling tools."""

    @staticmethod
    def _load_monitor_community_resources() -> str:
        """Load Azure Monitor Community resources metadata and format for system prompt."""
        try:
            from pathlib import Path
            import json
            
            # Load metadata file
            metadata_file = Path(__file__).parent.parent / "static" / "data" / "azure_monitor_community_metadata.json"
            
            if not metadata_file.exists():
                return ""
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            summary = metadata.get("summary", {})
            categories = metadata.get("categories", [])
            
            # Build resource catalog
            resource_info = f"""

AZURE MONITOR COMMUNITY RESOURCES (Available for Reference):
- Total Resources Available: {summary.get('total_resources', 0)} across {summary.get('total_categories', 0)} Azure services
- Workbooks: {summary.get('total_workbooks', 0)} across {summary.get('total_categories', 0)} categories
- Alerts: {summary.get('total_alerts', 0)} 
- Queries: {summary.get('total_queries', 0)} KQL queries for Log Analytics

Top Categories with Resources:
"""
            # Show top 15 categories by total resources
            categories_with_totals = []
            for cat in categories:
                total = cat.get("total_resources", 0)
                if total > 0:
                    categories_with_totals.append((cat["category"], total, 
                                                   cat.get("workbooks", {}).get("count", 0),
                                                   cat.get("alerts", {}).get("count", 0),
                                                   cat.get("queries", {}).get("count", 0)))
            
            categories_with_totals.sort(key=lambda x: x[1], reverse=True)
            
            for cat_name, total, wb, alerts, queries in categories_with_totals[:15]:
                resource_info += f"  • {cat_name}: {total} resources ({wb} workbooks, {alerts} alerts, {queries} queries)\n"
            
            if len(categories_with_totals) > 15:
                resource_info += f"  ... and {len(categories_with_totals) - 15} more categories\n"
            
            resource_info += """
When users ask about Azure monitoring, workbooks, alerts, or KQL queries:
- Use search_categories to find categories by keyword (e.g., "gateway" → "Application gateways", "VPN Gateway")
- Use list_resource_types to see available types
- Use list_categories with 'workbooks', 'alerts', or 'queries' to browse all categories
- Use list_resources to see specific items in a category
- Recommend relevant queries from categories like Application Insights, Virtual machines, Storage accounts, etc.

IMPORTANT: When users ask about a specific Azure service (e.g., "app gateway", "storage", "VM"), 
ALWAYS use search_categories first to find the exact category name before calling list_resources.
"""
            return resource_info
            
        except Exception as e:
            # Silently fail if metadata not available
            return ""

    @staticmethod
    def _build_dynamic_system_prompt(tool_definitions: List[Dict[str, Any]], tool_source_map: Dict[str, str]) -> str:
        """Build a dynamic system prompt based on available tools."""
        
        # Group tools by source
        tools_by_source: Dict[str, List[Dict[str, Any]]] = {}
        for tool in tool_definitions:
            tool_name = tool.get("function", {}).get("name", "")
            source = tool_source_map.get(tool_name, "unknown")
            if source not in tools_by_source:
                tools_by_source[source] = []
            tools_by_source[source].append(tool)
        
        # MCP server descriptions
        server_descriptions = {
            "azure": "Azure MCP Server - Provides access to Azure resource management (subscriptions, resource groups, VMs, storage, networking, etc.)",
            "azure_cli": "Azure CLI Executor - Executes any Azure CLI command for advanced operations not covered by other tools",
            "os_eol": "OS EOL Server - Checks End-of-Life dates for operating systems",
            "inventory": "Inventory Server - Queries Log Analytics Workspace for OS and software inventory data",
            "monitor": "Azure Monitor Community - Discover, view, and deploy workbooks, alerts, and queries from https://github.com/microsoft/AzureMonitorCommunity"
        }
        
        tool_catalog = []
        for source in ["azure", "azure_cli", "os_eol", "inventory", "monitor"]:
            if source not in tools_by_source:
                continue
            
            tools = tools_by_source[source]
            tool_catalog.append(f"\n{server_descriptions.get(source, source)}:")
            tool_catalog.append(f"  Available tools ({len(tools)}): {', '.join(t.get('function', {}).get('name', '') for t in tools[:10])}")
            if len(tools) > 10:
                tool_catalog.append(f"  ... and {len(tools) - 10} more")
        
        base_prompt = MCPOrchestratorAgent._SYSTEM_PROMPT
        
        if tool_catalog:
            dynamic_section = f"""

AVAILABLE MCP SERVERS AND TOOLS:
{''.join(tool_catalog)}

TOOL SELECTION STRATEGY:
1. For Azure resource operations (list, show, create, delete workspaces, subscriptions, resource groups, storage, networking, VMs) → Use Azure MCP Server tools
2. For querying OS/software inventory DATA inside a Log Analytics Workspace → Use Inventory Server tools (law_get_os_inventory, law_get_software_inventory)
3. For EOL date checking → Use OS EOL Server tools
4. For Azure Monitor resources (workbooks, alerts, queries) → Use Azure Monitor Community tools:
   - list_resource_types → See available types (workbooks, alerts, queries)
   - list_categories → Get categories for a resource type
   - list_resources → List resources in a category
   - get_resource_content → View content and parameters
   - search_categories → Find categories by keyword (e.g., search for "gateway" to find Application gateways)
   
   AZURE MONITOR RECOMMENDATIONS:
   When users ask about monitoring, observability, or insights for their Azure resources, you can:
   - Determine and recommend appropriate Azure Monitor resources based on the resource type
   - Use search_categories to find monitoring solutions for specific Azure services
   - Discover pre-built workbooks, alert templates, and queries from Azure Monitor Community
   - Recommend relevant monitoring best practices:
     * Virtual Machines → VM Insights workbook, performance alerts, diagnostic logs
     * Storage Accounts → Storage workbooks, capacity alerts, transaction metrics
     * Application Gateway → Application gateway workbooks, health alerts, request metrics
     * Container Apps → Container monitoring workbooks, resource consumption alerts
   - Suggest Log Analytics queries and KQL patterns for specific resource types
   - Proactively recommend diagnostic settings and Log Analytics Workspace integration
   Example: User asks "How do I monitor my VMs?" → Search for VM categories, recommend VM Insights workbook, suggest performance alerts

5. For Azure services WITHOUT specific tools → Use Azure CLI Executor
6. For complex operations or custom queries → Use Azure CLI Executor
{MCPOrchestratorAgent._load_monitor_community_resources()}
AZURE MONITOR COMMUNITY WORKFLOW:
When user asks to deploy workbooks, alerts, or queries:
1. FIRST: If user mentions a specific Azure service, use search_categories to find the exact category name
   Example: User says "app gateway" → Call search_categories(keyword="gateway") → Find "Application gateways"
2. THEN: Call list_resource_types to see what's available
3. THEN: Call list_categories with the resource type (workbooks/alerts/queries) OR use search results from step 1
4. THEN: Call list_resources to see items in a category (includes descriptions)
5. THEN: Call get_resource_content to view full content and deployment parameters
6. FOR WORKBOOKS DEPLOYMENT: Follow this EXACT workflow to avoid repeating questions:
   Step A - Gather ALL Information First (via tools, NOT by asking user):
   - Call subscription_list to get available subscriptions (pick first one if user didn't specify)
   - Call resource_group_list to get available resource groups
   - Use 'australiaeast' or region closest to user's resources as default location
   - Call list_resources to get the workbook download_url (you'll need this for deployment)
   - Optionally call get_resource_content to view parameters (but DON'T pass the content to deploy_workbook)
   
   Step B - Present Complete Plan ONCE and Ask for Confirmation:
   - Create ONE message showing the COMPLETE deployment plan:
     * Workbook name
     * Subscription (with name and ID)
     * Resource group: If user didn't specify one, format the question clearly:
       "**Resource Group**: [Pick one by typing its name]
        Available: rg-prod, rg-dev, rg-test"
       OR if you can infer the right one (e.g., named resource group like 'main-rg'), use it as default:
       "**Resource Group**: main-rg (change by typing a different name)"
     * Location (with default and option to change)
     * Any workbook-specific parameters
   - End with clear call to action:
     "Reply 'yes' to deploy, or type a different resource group name to change it."
   - IMPORTANT: Make it clear the user should TYPE their response in the chat
   - CRITICAL: After presenting this plan, STOP IMMEDIATELY. Do NOT make any more tool calls. Do NOT send another message. 
     The conversation MUST end here until the user responds. Your response should contain ONLY the deployment plan.
   - WAIT for user response (this means END YOUR TURN after presenting the plan)
   
   Step C - Handle User Response and Deploy:
   - If user confirms ("yes", "proceed", "confirm", "deploy", etc.) → Call deploy_workbook with:
     * download_url: The workbook's download URL from list_resources
     * subscription_id, resource_group, workbook_name, location: As gathered/confirmed
     * parameters: JSON string of parameter values if workbook requires them
   - IMPORTANT: Pass the download_url, NOT the workbook content JSON
   - If user provides a resource group name → Update the parameter and ask for confirmation again
   - If user declines ("no", "cancel", "stop") → Acknowledge and stop
   
   CRITICAL DEPLOYMENT RULES:
   - Present the deployment plan EXACTLY ONCE per user message
   - After presenting the plan, END YOUR TURN immediately (no more tool calls, no more text)
   - DO NOT repeat the plan in the same response
   - DO NOT ask for parameters separately before showing the complete plan
   - Wait for the user's explicit response before proceeding
   
7. FOR ALERTS/QUERIES: Display content for user review
7. FOR SEARCH: When users ask "what resources for X service", use list_categories and list_resources

AZURE CLI EXECUTOR USAGE:
- This tool can execute ANY Azure CLI command (az ...) 
- Use it as fallback when no specific tool exists
- Use it for complex queries not covered by existing tools
- Examples of services that may need Azure CLI:
  * Container Apps: az containerapp list
  * Azure Virtual Desktop: az desktopvirtualization
  * Specific configurations not covered by generic tools
- ⚠️ MANDATORY: Ask user for confirmation BEFORE executing any command that creates, modifies, or deletes resources
- For Azure CLI destructive commands, describe impact and WAIT for explicit user approval

CRITICAL: Always try to find a specific tool first. Only use Azure CLI Executor if:
- No specific tool exists for the requested Azure service
- You need to perform a complex operation not covered by existing tools
- The user explicitly asks for Azure CLI commands"""
            
            return base_prompt + dynamic_section
        
        return base_prompt

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
        self._dynamic_system_prompt: str = self._SYSTEM_PROMPT  # Will be updated when tools are loaded
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
                f"AzureOpenAIChatClient available: {_AGENT_FRAMEWORK_CHAT_AVAILABLE}, "
                f"Agent Framework base classes available: {_AGENT_FRAMEWORK_AVAILABLE}. "
                "Please ensure the azure-ai-agent-openai package is installed and Azure OpenAI credentials are configured."
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

        # Use proven CompositeMCPClient approach with manual tool execution
        # This is more robust than MCPStdioTool because:
        # - Properly filters stdout noise (via wrapper)
        # - Works with local MCP servers
        # - No JSON-RPC parsing errors
        # - Full control over tool execution
        
        # Fallback to direct get_response() with manual tool execution
        user_chat = ChatMessage(role="user", text=user_message)
        self._message_log.append(user_chat)

        for iteration in range(1, self._max_reasoning_iterations + 1):
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
                # Use direct OpenAI client to avoid AF auto-executing tools
                # AF auto-executes when tools are passed, but our tool_map is empty
                # Direct client gives us full control over tool execution
                if self._tool_definitions:
                    from openai import AsyncAzureOpenAI
                    
                    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                    api_key = os.getenv("AZURE_OPENAI_API_KEY")
                    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
                    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
                    
                    direct_client = None
                    try:
                        # Convert AF message history to OpenAI format
                        openai_messages = []
                        for msg in self._message_log:
                            role = self._get_message_role(msg)
                            
                            # Handle tool messages specially
                            if role == "tool":
                                # Tool messages need tool_call_id
                                for content in msg.contents:
                                    if hasattr(content, 'call_id') and content.call_id:
                                        openai_messages.append({
                                            "role": "tool",
                                            "tool_call_id": content.call_id,
                                            "content": self._message_to_text(msg) or "Success"
                                        })
                            elif role == "assistant" and any(hasattr(c, 'name') and hasattr(c, 'call_id') for c in msg.contents):
                                # Assistant message with tool calls
                                tool_calls = []
                                for content in msg.contents:
                                    if hasattr(content, 'name') and hasattr(content, 'call_id'):
                                        tool_calls.append({
                                            "id": content.call_id,
                                            "type": "function",
                                            "function": {
                                                "name": content.name,
                                                "arguments": json.dumps(content.arguments) if hasattr(content, 'arguments') else "{}"
                                            }
                                        })
                                if tool_calls:
                                    openai_messages.append({
                                        "role": "assistant",
                                        "content": None,
                                        "tool_calls": tool_calls
                                    })
                            else:
                                # Regular message
                                content = self._message_to_text(msg)
                                if content:
                                    openai_messages.append({"role": role, "content": content})
                        
                        # Call OpenAI directly with proper authentication
                        if api_key:
                            direct_client = AsyncAzureOpenAI(
                                api_key=api_key,
                                azure_endpoint=endpoint,
                                api_version=api_version,
                            )
                        else:
                            # Use DefaultAzureCredential
                            if _DEFAULT_CREDENTIAL_AVAILABLE and DefaultAzureCredential:
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
                            
                            # Call OpenAI with tools
                            raw_response = await direct_client.chat.completions.create(
                                model=deployment,
                                messages=openai_messages,
                                tools=[{"type": "function", "function": t.get("function", t)} for t in self._tool_definitions],
                                temperature=self._default_temperature,
                                max_tokens=3000,
                            )
                            
                            # Convert to AF format
                            choice = raw_response.choices[0]
                            if choice.message.tool_calls:
                                tool_call_contents = []
                                for tc in choice.message.tool_calls:
                                    # Parse tool call arguments with robust error handling
                                    try:
                                        if tc.function.arguments:
                                            arguments = json.loads(tc.function.arguments)
                                        else:
                                            arguments = {}
                                    except json.JSONDecodeError as json_err:
                                        logger.error(
                                            "Failed to parse tool call arguments: %s (tool=%s, args_preview=%s...)",
                                            json_err,
                                            tc.function.name,
                                            tc.function.arguments[:200] if tc.function.arguments else "None"
                                        )
                                        # Send error information to user via SSE
                                        await self._send_sse_event("error", {
                                            "phase": "tool_call_parsing",
                                            "tool_name": tc.function.name,
                                            "error": f"LLM generated malformed JSON: {str(json_err)}",
                                            "hint": "The model may be trying to pass too much data. Try simplifying the request or breaking it into steps."
                                        })
                                        # Skip this malformed tool call
                                        continue
                                    
                                    tool_call_contents.append(FunctionCallContent(
                                        call_id=tc.id,
                                        name=tc.function.name,
                                        arguments=arguments
                                    ))
                                
                                if tool_call_contents:
                                    response = ChatResponse(messages=[ChatMessage(
                                        role="assistant",
                                        contents=tool_call_contents
                                    )])
                                else:
                                    # All tool calls failed parsing - return error message
                                    response = ChatResponse(messages=[ChatMessage(
                                        role="assistant",
                                        text="I encountered an error generating the tool call. The response was too complex or contained invalid characters. Please try simplifying your request or breaking it into smaller steps."
                                    )])
                            else:
                                response = ChatResponse(messages=[ChatMessage(
                                    role="assistant",
                                    text=choice.message.content or ""
                                )])
                    finally:
                        if direct_client:
                            try:
                                await direct_client.close()
                            except Exception as close_exc:
                                logger.debug("Error closing direct client: %s", close_exc)
                else:
                    # No tools - use AF
                    response: ChatResponse = await self._chat_client.get_response(
                        self._message_log,
                        options={
                            "temperature": self._default_temperature,
                            "max_tokens": 3000,
                        },
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
            "agent_framework_enabled": _AGENT_FRAMEWORK_AVAILABLE and _AGENT_FRAMEWORK_CHAT_AVAILABLE,
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

        # Deduplicate response text to avoid showing the same content multiple times
        final_text = self._deduplicate_response_text(final_text)

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
        if self._chat_client:
            return True
        # Check if we have the chat client class available (the critical dependency)
        if not _AGENT_FRAMEWORK_CHAT_AVAILABLE or AzureOpenAIChatClient is None:
            logger.warning(
                "AzureOpenAIChatClient not available. Chat Client: %s, Agent Framework base classes: %s",
                _AGENT_FRAMEWORK_CHAT_AVAILABLE,
                _AGENT_FRAMEWORK_AVAILABLE,
            )
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
            
            logger.info("✅ Loaded %d MCP tools for agent framework", len(self._tool_definitions))
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

    def _deduplicate_response_text(self, text: str) -> str:
        """Remove duplicate paragraphs/sections from response text."""
        if not text or len(text) < 100:
            return text
        
        # Split text into paragraphs (by double newline or major sections)
        paragraphs = []
        current = []
        
        for line in text.split('\n'):
            if line.strip():
                current.append(line)
            elif current:
                # Empty line - end of paragraph
                paragraphs.append('\n'.join(current))
                current = []
        if current:
            paragraphs.append('\n'.join(current))
        
        # Deduplicate paragraphs while preserving order
        seen = set()
        unique_paragraphs = []
        
        for para in paragraphs:
            # Normalize for comparison (remove extra whitespace, lowercase)
            normalized = ' '.join(para.split()).lower()
            
            # Skip if we've seen this paragraph (or very similar content)
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_paragraphs.append(para)
            elif not normalized:
                # Keep empty lines for formatting
                unique_paragraphs.append(para)
        
        deduplicated = '\n\n'.join(unique_paragraphs)
        
        if len(deduplicated) < len(text) * 0.9:
            logger.info(f"📝 Deduplicated response: {len(text)} → {len(deduplicated)} chars (removed {len(text) - len(deduplicated)} duplicate chars)")
        
        return deduplicated

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
            "agent_framework_enabled": _AGENT_FRAMEWORK_AVAILABLE and _AGENT_FRAMEWORK_CHAT_AVAILABLE,
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
