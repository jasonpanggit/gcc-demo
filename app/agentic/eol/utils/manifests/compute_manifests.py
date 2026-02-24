"""Tool manifests for the Compute MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="virtual_machine_list",
        source="compute",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"vm", "compute", "iaas", "virtual_machine"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list my virtual machines",
            "show all VMs",
            "show all VMs in my subscription",
            "what virtual machines do I have",
            "list VMs in resource group",
        ),
        conflicts_with=frozenset({"virtual_machines"}),
        conflict_note=(
            "virtual_machine_list is the PRIMARY tool for listing Azure VMs. "
            "It returns structured per-VM data (size, OS, power state). "
            "Do NOT use 'virtual_machines' (Azure MCP namespace group) for listing."
        ),
        preferred_over=frozenset({"virtual_machines"}),
    ),
]
