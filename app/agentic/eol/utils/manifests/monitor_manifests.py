"""Tool manifests for Azure Monitor Community MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="get_service_monitor_resources",
        source="monitor",
        domains=frozenset({"observability"}),
        tags=frozenset({"monitor", "workbooks", "alerts", "kql"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "find monitor resources for AKS",
            "get workbooks for Container Apps",
            "find KQL queries for my service",
        ),
        conflicts_with=frozenset({"monitor"}),
        conflict_note=(
            "get_service_monitor_resources (Monitor Community) discovers workbooks/alerts/KQL. "
            "NOT the same as Azure MCP 'monitor' which configures Azure Monitor resources."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="deploy_workbook",
        source="monitor",
        domains=frozenset({"observability"}),
        tags=frozenset({"monitor", "workbooks", "deploy"}),
        affordance=ToolAffordance.DEPLOY,
        example_queries=(
            "deploy AKS workbook",
            "install Container Apps monitoring workbook",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
        requires_confirmation=True,
    ),
    ToolManifest(
        tool_name="get_resource_content",
        source="monitor",
        domains=frozenset({"observability"}),
        tags=frozenset({"monitor", "kql", "alerts"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "get content of a monitor resource",
            "show the KQL query for an alert",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="list_monitor_categories",
        source="monitor",
        domains=frozenset({"observability"}),
        tags=frozenset({"monitor", "catalog"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list monitor categories",
            "what monitoring resources are available",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="search_categories",
        source="monitor",
        domains=frozenset({"observability"}),
        tags=frozenset({"monitor", "search", "categories"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "search monitor categories",
            "find Azure Monitor community resources by keyword",
        ),
        conflicts_with=frozenset({"search"}),
        conflict_note=(
            "search_categories searches Azure Monitor Community categories for workbooks/alerts/queries. "
            "NOT for Azure Cognitive Search or log searching."
        ),
        preferred_over=frozenset(),
    ),
]
