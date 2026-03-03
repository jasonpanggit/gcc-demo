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
        # Phase 3 metadata
        primary_phrasings=(
            "list my virtual machines",
            "show all VMs in my subscription",
            "what virtual machines do I have",
            "list VMs in resource group",
            "show running VMs",
            "enumerate virtual machines",
            "display all Azure VMs",
            "show stopped VMs",
            "list compute resources",
            "get all VMs",
            # Abbreviation variants — replaces hard-coded vm/vms expansion in tool_retriever.py
            "list my VMs",
            "show my VMs",
            "all VMs",
            "my VMs",
            "list VMs",
        ),
        avoid_phrasings=(
            "check VM health",                   # → check_resource_health
            "VM performance metrics",            # → get_performance_metrics
            "restart the VM",                    # → execute_safe_restart
            "scale VM",                          # → scale_resource
            "list AKS clusters",                 # → azure MCP (AKS is not VMs)
        ),
        confidence_boost=1.3,
        requires_sequence=None,
        preferred_over_list=("virtual_machines",),
    ),
]
