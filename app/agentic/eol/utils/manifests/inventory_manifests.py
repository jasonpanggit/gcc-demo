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
        # Phase 3 metadata
        primary_phrasings=(
            "list Arc servers",
            "show OS inventory for Arc-enabled servers",
            "what operating systems are running on my Arc servers",
            "Arc server OS inventory",
            "get OS details from Arc-connected machines",
            "list Arc-managed servers",
            "show server OS versions via Arc",
            "what OS versions are running on my servers",
        ),
        avoid_phrasings=(
            "list Azure VMs",                    # → virtual_machine_list (native Azure VMs)
            "check EOL status",                  # → os_eol_bulk_lookup (EOL analysis)
            "list software packages",            # → law_get_software_inventory
            "list containers",                   # → container_app_list
        ),
        confidence_boost=1.2,
        requires_sequence=None,
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
        # Phase 3 metadata
        primary_phrasings=(
            "list installed software on Arc servers",
            "software inventory for my servers",
            "what packages are installed on my Arc servers",
            "show software packages on Arc-connected machines",
            "Arc server software inventory",
            "list applications installed on Arc servers",
            "what is installed on my Arc-managed servers",
            "get software list from Arc servers",
        ),
        avoid_phrasings=(
            "list Arc servers",                  # → law_get_os_inventory (OS inventory, not software)
            "check EOL status",                  # → os_eol_bulk_lookup (EOL analysis)
            "list Azure VMs",                    # → virtual_machine_list (native Azure VMs)
            "list containers",                   # → container_app_list
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "which servers are running end-of-life operating systems",
            "check EOL status for my Arc servers",
            "which OS versions are no longer supported",
            "are any of my servers running an unsupported OS",
            "find end-of-life servers",
            "show servers with expired OS support",
            "bulk EOL check for all my servers",
            "which Arc servers have reached end of life",
            "EOL compliance report for my servers",
        ),
        avoid_phrasings=(
            "list Arc servers",                  # → law_get_os_inventory (OS inventory listing)
            "is Ubuntu 18.04 end of life",       # → os_eol_check (single OS lookup)
            "check EOL for one OS version",      # → os_eol_check (single OS lookup)
        ),
        confidence_boost=1.2,
        requires_sequence=("law_get_os_inventory",),
        preferred_over_list=(),
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
        # Phase 3 metadata
        primary_phrasings=(
            "is Ubuntu 18.04 end of life",
            "check EOL for Windows Server 2012",
            "is this OS version supported",
            "when does Windows Server 2019 go end of life",
            "check end-of-life date for a specific OS",
            "is Red Hat Enterprise Linux 7 still supported",
            "EOL date for a single OS version",
            "when does support end for this operating system",
        ),
        avoid_phrasings=(
            "check EOL status for all my Arc servers",   # → os_eol_bulk_lookup (bulk)
            "which servers are running end-of-life OS",  # → os_eol_bulk_lookup (bulk)
            "list Arc servers",                          # → law_get_os_inventory
        ),
        confidence_boost=1.1,
        requires_sequence=None,
        preferred_over_list=(),
    ),
]
