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
        # Phase 3 metadata
        primary_phrasings=(
            "find monitor resources for AKS",
            "get workbooks for Container Apps",
            "find KQL queries for my service",
            "discover available monitoring workbooks",
            "what monitoring resources are available for my service",
            "find alerts and workbooks for my Azure service",
            "get community workbooks for monitoring",
            "show monitoring resources for my resource type",
        ),
        avoid_phrasings=(
            "deploy a workbook",                       # → deploy_workbook
            "list monitor categories",                 # → list_monitor_categories
            "search for monitor categories by keyword",  # → search_categories
        ),
        confidence_boost=1.2,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "deploy AKS workbook",
            "install Container Apps monitoring workbook",
            "deploy monitoring workbook to my workspace",
            "install a workbook for monitoring",
            "deploy community workbook",
            "set up monitoring workbook for my service",
            "push workbook to Azure Monitor",
        ),
        avoid_phrasings=(
            "find available workbooks",                # → get_service_monitor_resources
            "list monitoring categories",              # → list_monitor_categories
            "get content of a workbook",               # → get_resource_content
        ),
        confidence_boost=1.2,
        requires_sequence=("get_service_monitor_resources",),
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "get content of a monitor resource",
            "show the KQL query for an alert",
            "retrieve workbook content",
            "show the definition of a monitoring alert",
            "get the KQL for a monitor query",
            "show workbook JSON definition",
            "retrieve alert rule content",
        ),
        avoid_phrasings=(
            "find monitoring resources",               # → get_service_monitor_resources
            "deploy a workbook",                       # → deploy_workbook
            "search monitor categories",               # → search_categories
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "list monitor categories",
            "what monitoring resources are available",
            "show Azure Monitor community categories",
            "what categories exist in Azure Monitor community",
            "list all monitoring resource categories",
            "enumerate monitoring categories",
            "what types of monitor resources are there",
        ),
        avoid_phrasings=(
            "find workbooks for my service",           # → get_service_monitor_resources
            "search for monitoring resources by keyword",  # → search_categories
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "search monitor categories",
            "find Azure Monitor community resources by keyword",
            "search for monitoring workbooks by name",
            "find monitoring resources containing a keyword",
            "search Azure Monitor community for AKS resources",
            "keyword search in Monitor Community categories",
            "find all monitoring resources matching a term",
        ),
        avoid_phrasings=(
            "list all monitor categories",             # → list_monitor_categories (full list)
            "find workbooks for a specific service",   # → get_service_monitor_resources
            "deploy a workbook",                       # → deploy_workbook
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
    ),
]
