"""Tool manifests for Inventory and OS EOL MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="law_get_os_inventory",
        source="inventory",
        domains=frozenset({"arc_inventory"}),
        tags=frozenset({"arc", "inventory", "os", "servers"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list Arc servers",
            "show OS inventory for Arc-enabled servers",
            "what operating systems are running on my Arc servers",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "law_get_os_inventory queries Arc-connected servers via Log Analytics. "
            "ONLY for Arc-enabled servers. For Azure VMs use Azure MCP compute tools."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="law_get_software_inventory",
        source="inventory",
        domains=frozenset({"arc_inventory"}),
        tags=frozenset({"arc", "inventory", "software", "packages"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list installed software on Arc servers",
            "software inventory for my servers",
            "what packages are installed",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "law_get_software_inventory queries software installed on Arc-connected servers. "
            "ONLY for Arc-enabled servers."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="os_eol_bulk_lookup",
        source="os_eol",
        domains=frozenset({"arc_inventory"}),
        tags=frozenset({"eol", "end_of_life", "os", "support"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "which servers are running end-of-life operating systems",
            "check EOL status for my Arc servers",
            "which OS versions are no longer supported",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "os_eol_bulk_lookup cross-references OS inventory with EOL dates. "
            "Use after law_get_os_inventory to check EOL status."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="os_eol_check",
        source="os_eol",
        domains=frozenset({"arc_inventory"}),
        tags=frozenset({"eol", "end_of_life", "single"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "is Ubuntu 18.04 end of life",
            "check EOL for Windows Server 2012",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
]
