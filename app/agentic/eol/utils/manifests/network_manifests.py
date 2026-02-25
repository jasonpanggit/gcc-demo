"""Tool manifests for the Network MCP server tools (Phase 3 — placeholder).

These manifests are registered now so the ToolManifestIndex can classify
network tools before the server is implemented.
"""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="virtual_network_list",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"vnet", "network", "list", "virtual_networks"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list my virtual networks",
            "show all VNets in my subscription",
            "what virtual networks do I have",
            "show my vnets",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset({"inspect_vnet"}),
    ),
    ToolManifest(
        tool_name="inspect_vnet",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"vnet", "network", "subnets", "peering"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "inspect virtual network",
            "show VNet address space and subnets",
            "VNet peering status",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="inspect_nsg_rules",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"nsg", "network", "security_rules", "firewall"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list NSG rules",
            "show network security group rules",
            "what ports are allowed in my NSG",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="get_effective_routes_and_rules",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"routes", "effective_rules", "nic", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "get effective routes for my NIC",
            "show effective NSG rules",
            "what routing rules apply to my VM",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="test_network_connectivity",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"connectivity", "network", "ip_flow", "troubleshoot"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "test network connectivity",
            "can my container app reach the database",
            "test IP flow between resources",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="inspect_appgw_waf",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"appgateway", "waf", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check Application Gateway health",
            "show WAF policy",
            "Application Gateway backend health",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="inspect_vpn_expressroute",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"vpn", "expressroute", "network", "gateway"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check VPN gateway status",
            "show ExpressRoute circuit state",
            "VPN connection health",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="check_dns_resolution",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"dns", "network", "resolution"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "check DNS resolution",
            "list private DNS zones",
            "does my hostname resolve correctly",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
]
