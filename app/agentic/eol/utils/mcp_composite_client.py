"""Composite MCP client that aggregates multiple MCP tool sources."""
from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ToolDefinition = Dict[str, Any]
ClientEntry = Tuple[str, Any]

# Source-level routing guidance appended to every tool description so the
# LLM can autonomously select the right tool without a giant system prompt.
_SOURCE_GUIDANCE: Dict[str, str] = {
    "azure": (
        " [Azure MCP Server] For Azure resource management: subscriptions, resource groups, "
        "VMs, storage, networking, etc. NOT for Container Apps."
    ),
    "azure_cli": (
        " [Azure CLI Executor] Run any 'az' command for services without a dedicated tool: "
        "Container Apps, AVD, saved searches, scheduled query alerts, etc. "
        "For destructive operations, present the plan and wait for user confirmation."
    ),
    "os_eol": (
        " [OS EOL Server] Check End-of-Life dates and support status for operating systems. "
        "Use os_eol_bulk_lookup after retrieving inventory to cross-reference EOL status."
    ),
    "inventory": (
        " [Inventory Server] Query OS and software inventory from Log Analytics. "
        "Use these tools to find WHAT is installed. To check if it's end-of-life, "
        "pass results to os_eol tools. To manage the workspace itself, use Azure MCP Server."
    ),
    "monitor": (
        " [Azure Monitor Community] Discover and deploy workbooks, alerts, and KQL queries. "
        "Start with get_service_monitor_resources(keyword) to find ALL resources for a service in one call. "
        "Then deploy: workbooks via deploy_workbook, queries/alerts via get_resource_content then CLI."
    ),
    "sre": (
        " [Azure SRE Agent] For site reliability operations: resource health checks, incident triage, "
        "diagnostics, performance monitoring, and safe remediation actions. "
        "Use check_resource_health for availability status (requires full resource ID). "
        "For troubleshooting, use triage_incident, get_diagnostic_logs, and identify_bottlenecks. "
        "NEVER use the 'speech' tool for SRE operations - call SRE tools directly."
    ),
}

# Per-tool disambiguation: extra text appended to specific tools that the LLM
# frequently confuses with other Azure services.  Keyed by tool name substring.
_TOOL_DISAMBIGUATION: Dict[str, str] = {
    # === Container Services Disambiguation ===
    "container_registries": (
        " ⚠️ This is for Azure Container REGISTRY (ACR), NOT Azure Container Apps. "
        "For Container Apps use azure_cli_execute_command with 'az containerapp'."
    ),
    "app_service": (
        " ⚠️ This is for Azure App SERVICE (Web Apps), NOT Azure Container Apps."
    ),
    "app_configuration": (
        " ⚠️ This is for Azure App CONFIGURATION stores, NOT Azure Container Apps."
    ),
    "function_app": (
        " ⚠️ This is for Azure FUNCTION Apps, NOT Azure Container Apps."
    ),

    # === Resource Health & Monitoring Disambiguation ===
    "resourcehealth": (
        " [Azure Resource Health API] Basic resource availability status from Azure platform. "
        "For deeper SRE operations (diagnostics, incident triage, performance analysis, remediation), "
        "use SRE tools: check_resource_health, triage_incident, get_diagnostic_logs, etc."
    ),
    "check_resource_health": (
        " [SRE Deep Health Check] Comprehensive resource health with diagnostics and remediation planning. "
        "For basic platform health status only, you can also use 'resourcehealth' (Azure MCP). "
        "This SRE tool is preferred when you need actionable insights or follow-up diagnostics."
    ),
    "monitor": (
        " [Azure Monitor Configuration] This Azure MCP tool is for configuring Azure Monitor resources. "
        "For Azure Monitor Community workbooks/alerts/queries, use monitor_agent or get_service_monitor_resources. "
        "For performance metrics and diagnostics, use SRE tools: get_performance_metrics, get_diagnostic_logs."
    ),
    "applicationinsights": (
        " [Application Insights Configuration] This is for configuring Application Insights resources. "
        "For retrieving diagnostic logs or performance data, use SRE tools: get_diagnostic_logs, get_performance_metrics."
    ),

    # === Search Disambiguation ===
    "search": (
        " ⚠️ This is Azure COGNITIVE SEARCH service management, NOT general search functionality. "
        "For searching logs: use search_logs_by_error (SRE tool). "
        "For searching Azure Monitor community resources: use search_categories (Monitor MCP)."
    ),
    "search_categories": (
        " [Monitor Community Search] Search Azure Monitor Community categories for workbooks/alerts/queries. "
        "NOT for Azure Cognitive Search or log searching."
    ),
    "search_logs_by_error": (
        " [SRE Log Search] Search Azure diagnostic logs for specific error messages. "
        "NOT for Azure Cognitive Search or Monitor Community resources."
    ),

    # === Speech & AI Services Disambiguation ===
    "speech": (
        " ⚠️ CRITICAL: This is Azure AI Services SPEECH tool (speech-to-text, text-to-speech, audio processing). "
        "This is NOT for Azure resource health, diagnostics, SRE operations, or any infrastructure management! "
        "For resource health: use check_resource_health (SRE) or resourcehealth (Azure MCP). "
        "For AI services management: use 'foundry' (Azure AI Foundry). "
        "NEVER route resource operations through 'speech'."
    ),
    "foundry": (
        " [Azure AI Foundry] For Azure AI Foundry project management and AI services. "
        "NOT for Azure AI Speech Services (use 'speech' tool for that)."
    ),

    # === Storage Disambiguation ===
    "storage": (
        " [Azure Storage Accounts] General Azure Storage account operations. "
        "For specific file share operations: use 'fileshares'. "
        "For Azure File Sync: use 'storagesync'."
    ),
    "fileshares": (
        " [Azure File Shares] Specific to Azure Files (SMB/NFS file shares). "
        "For general storage accounts: use 'storage'. "
        "For sync operations: use 'storagesync'."
    ),
    "storagesync": (
        " [Azure File Sync] For Azure File Sync service (hybrid cloud sync). "
        "For file share management: use 'fileshares'. "
        "For storage accounts: use 'storage'."
    ),

    # === Database Services Disambiguation ===
    "cosmos": (
        " [Azure Cosmos DB] For Cosmos DB (NoSQL) operations. "
        "For relational databases: use 'sql' (Azure SQL), 'mysql', or 'postgres'."
    ),
    "sql": (
        " [Azure SQL Database] For Azure SQL (relational DB). "
        "For Cosmos DB (NoSQL): use 'cosmos'. "
        "For MySQL: use 'mysql'. For PostgreSQL: use 'postgres'."
    ),
    "mysql": (
        " [Azure MySQL] For MySQL database service. "
        "For Azure SQL: use 'sql'. For Cosmos DB: use 'cosmos'. For PostgreSQL: use 'postgres'."
    ),
    "postgres": (
        " [Azure PostgreSQL] For PostgreSQL database service. "
        "For Azure SQL: use 'sql'. For Cosmos DB: use 'cosmos'. For MySQL: use 'mysql'."
    ),

    # === Cache Services Disambiguation ===
    "redis": (
        " [Azure Redis Cache] For Azure Cache for Redis service management. "
        "For clearing application caches: use clear_cache (SRE tool)."
    ),
    "clear_cache": (
        " [SRE Cache Clear] For clearing application-level caches (requires user approval). "
        "For Azure Redis Cache service management: use 'redis' (Azure MCP)."
    ),

    # === Deprecated Monitor Community Tools ===
    "list_resource_types": (
        " ⚠️ DEPRECATED: This only returns 3 generic type names (workbooks, alerts, queries). "
        "Use get_service_monitor_resources(keyword) to get ACTUAL resources for a service."
    ),
    "list_workbook_categories": (
        " ⚠️ DEPRECATED: Use list_categories(resource_type='workbooks') instead."
    ),
    "list_workbooks": (
        " ⚠️ DEPRECATED: Use list_resources(resource_type='workbooks', category=...) instead."
    ),
    "get_workbook_details": (
        " ⚠️ DEPRECATED: Use get_resource_content(download_url, resource_type='workbooks') instead."
    ),
}


class CompositeMCPClient:
    """Aggregates multiple MCP clients behind a single interface."""

    def __init__(self, clients: Sequence[ClientEntry]) -> None:
        self._clients: List[ClientEntry] = [(label, client) for label, client in clients if client]
        self._tool_definitions: List[ToolDefinition] = []
        self._tool_map: Dict[str, Tuple[Any, str]] = {}
        self._tool_sources: Dict[str, str] = {}
        self._build_catalog()

    def _build_catalog(self) -> None:
        self._tool_definitions.clear()
        self._tool_map.clear()
        self._tool_sources.clear()

        for label, client in self._clients:
            get_tools = getattr(client, "get_available_tools", None)
            if not callable(get_tools):
                logger.debug("Client '%s' has no get_available_tools method", label)
                continue

            try:
                tools: Iterable[Any] = get_tools()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Failed to list tools for client '%s': %s", label, exc)
                continue

            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                function = tool.get("function") if isinstance(tool.get("function"), dict) else None
                if not function:
                    continue
                original_name = str(function.get("name") or "").strip()
                if not original_name:
                    continue

                final_name = original_name
                suffix = 1
                while final_name in self._tool_map:
                    suffix += 1
                    final_name = f"{original_name}_{suffix}"

                tool_definition = deepcopy(tool)
                tool_definition.setdefault("function", {})["name"] = final_name
                tool_definition.setdefault("function", {})["x_original_name"] = original_name
                metadata_block = tool_definition.setdefault("metadata", {})
                metadata_block.setdefault("source", label)
                metadata_block.setdefault("original_name", original_name)

                # Enrich tool description with source-aware routing guidance
                guidance = _SOURCE_GUIDANCE.get(label, "")
                if guidance:
                    existing_desc = tool_definition["function"].get("description", "")
                    tool_definition["function"]["description"] = (existing_desc + guidance).strip()

                # Add per-tool disambiguation for commonly confused tools
                lower_name = final_name.lower()
                for pattern, disambiguation in _TOOL_DISAMBIGUATION.items():
                    if pattern in lower_name:
                        tool_definition["function"]["description"] += disambiguation
                        break

                self._tool_map[final_name] = (client, original_name)
                self._tool_sources[final_name] = label
                self._tool_definitions.append(tool_definition)
                # logger.debug(
                #     "Registered MCP tool '%s' (original '%s') from client '%s'",
                #     final_name,
                #     original_name,
                #     label,
                # )

        if self._tool_definitions:
            counts: Dict[str, int] = {}
            for source_label in self._tool_sources.values():
                counts[source_label] = counts.get(source_label, 0) + 1
            ordered = ", ".join(f"{label}={count}" for label, count in counts.items())
            logger.info(
                "Composite MCP catalog built with %d tool(s) [%s]",
                len(self._tool_definitions),
                ordered or "no sources",
            )
        else:
            logger.info("Composite MCP catalog is empty; no tools registered from %d client(s)", len(self._clients))

    def get_available_tools(self) -> List[ToolDefinition]:
        return deepcopy(self._tool_definitions)

    def get_tools_by_sources(self, sources: Sequence[str]) -> List[ToolDefinition]:
        """Return tool definitions filtered to only tools from the given source labels."""
        allowed = set(sources)
        return deepcopy([
            td for td in self._tool_definitions
            if self._tool_sources.get(td.get("function", {}).get("name", "")) in allowed
        ])

    def get_tools_excluding_sources(self, sources: Sequence[str]) -> List[ToolDefinition]:
        """Return tool definitions excluding tools from the given source labels."""
        excluded = set(sources)
        return deepcopy([
            td for td in self._tool_definitions
            if self._tool_sources.get(td.get("function", {}).get("name", "")) not in excluded
        ])

    def get_tool_sources(self) -> Dict[str, str]:
        return dict(self._tool_sources)

    def get_client_labels(self) -> List[str]:
        return [label for label, _ in self._clients]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        entry = self._tool_map.get(tool_name)
        if not entry:
            logger.warning("Requested MCP tool '%s' not found", tool_name)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Tool '{tool_name}' not available in composite client.",
                "is_error": True,
            }

        client, original_name = entry
        call_method = getattr(client, "call_tool", None)
        if not callable(call_method):
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Client for tool '{tool_name}' does not support call_tool().",
                "is_error": True,
            }

        try:
            result = call_method(original_name, arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Composite MCP call failed for '%s'", tool_name)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": str(exc),
                "is_error": True,
            }

        if isinstance(result, dict):
            result.setdefault("tool_name", tool_name)
            result.setdefault("client_tool_name", original_name)
            tool_source = self._tool_sources.get(tool_name)
            if tool_source:
                result.setdefault("tool_source", tool_source)
            return result

        return {
            "success": False,
            "tool_name": tool_name,
            "error": "Tool call returned unexpected payload",
            "payload": json.dumps(result, default=str),
            "is_error": True,
        }

    async def aclose(self) -> None:
        for label, client in self._clients:
            close_methods = ("aclose", "close", "cleanup")
            for method_name in close_methods:
                closer = getattr(client, method_name, None)
                if not callable(closer):
                    continue
                try:
                    result = closer()
                    if asyncio.iscoroutine(result):
                        await result
                    logger.debug("Closed MCP client '%s' via %s", label, method_name)
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    logger.debug(
                        "Failed to close MCP client '%s' via %s: %s",
                        label,
                        method_name,
                        exc,
                    )
                    continue