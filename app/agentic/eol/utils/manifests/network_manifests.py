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
        tool_name="private_endpoint_list",
        source="network",
        domains=frozenset({"network", "azure_management"}),
        tags=frozenset({"private_endpoint", "private_ip", "network", "list", "ip_address"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list all private endpoints",
            "show private endpoints and their IP addresses",
            "what is the private IP of my private endpoint",
            "show all private endpoints with IPs",
            "get private endpoint IP address",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "private_endpoint_list is the preferred tool for listing private endpoints and their IPs. "
            "It correctly resolves IPs via the attached NIC when customDnsConfigs is empty "
            "(which happens for DNS-zone-integrated endpoints). "
            "Use azure_cli_execute_command only when you need a JMESPath projection not available here."
        ),
        preferred_over=frozenset({"azure_cli_execute_command"}),
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
        tool_name="nsg_list",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"nsg", "network", "security_group", "list"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list my network security groups",
            "show all NSGs",
            "show all network security groups in my subscription",
            "what network security groups do I have",
        ),
        conflicts_with=frozenset({"inspect_nsg_rules"}),
        conflict_note=(
            "nsg_list is the PRIMARY tool for listing NSGs. "
            "Use nsg_list when the user wants to discover/enumerate NSGs. "
            "Only use inspect_nsg_rules when the user wants to see the rules/ports of a SPECIFIC NSG."
        ),
        preferred_over=frozenset({"inspect_nsg_rules"}),
    ),
    ToolManifest(
        tool_name="inspect_nsg_rules",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"nsg", "network", "security_rules", "firewall", "ports"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "show rules for my NSG",
            "what ports are allowed in my NSG",
            "inspect inbound rules for network security group",
            "show outbound NSG rules",
        ),
        conflicts_with=frozenset({"nsg_list"}),
        conflict_note=(
            "inspect_nsg_rules requires a specific NSG resource_id. "
            "Do NOT use it to list or enumerate NSGs — use nsg_list for that."
        ),
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
