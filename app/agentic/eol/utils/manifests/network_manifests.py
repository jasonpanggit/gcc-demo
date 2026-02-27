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
    # ── New capabilities (Phase 3+) ──────────────────────────────────────────
    ToolManifest(
        tool_name="analyze_route_path",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"route", "path", "network", "lpm", "routing", "trace"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "analyze route path from my subnet",
            "trace routing path to destination IP",
            "which route does traffic take from subnet-a to 10.1.0.5",
            "show route from my subnet to the database",
        ),
        conflicts_with=frozenset({"get_effective_routes_and_rules"}),
        conflict_note=(
            "analyze_route_path traces a specific source→destination path using LPM. "
            "Use get_effective_routes_and_rules when the user wants all effective routes for a NIC."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="simulate_nsg_flow",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"nsg", "flow", "simulate", "traffic", "allow", "deny", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "simulate NSG traffic flow",
            "will my VM be allowed to reach port 443",
            "simulate traffic flow through NSG rules",
            "check if traffic from my VM is allowed by NSG",
        ),
        conflicts_with=frozenset({"inspect_nsg_rules"}),
        conflict_note=(
            "simulate_nsg_flow evaluates whether specific traffic is allowed/denied. "
            "Use inspect_nsg_rules to list all rules for an NSG without traffic simulation."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="generate_connectivity_matrix",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"connectivity", "matrix", "subnet", "network", "analysis"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "generate connectivity matrix for my subnets",
            "show which subnets can talk to each other",
            "subnet connectivity matrix",
            "can all my subnets reach each other",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="inventory_network_resources",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"inventory", "network", "resources", "cost", "unused"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "inventory my network resources",
            "show all network resources in my subscription",
            "find unused network resources",
            "network resource inventory for cost optimization",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="analyze_private_connectivity_coverage",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"private", "endpoint", "connectivity", "zero_trust", "paas", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "analyze private endpoint coverage",
            "check zero-trust private connectivity",
            "which PaaS services are not using private endpoints",
            "assess private connectivity for zero-trust",
        ),
        conflicts_with=frozenset({"private_endpoint_list"}),
        conflict_note=(
            "analyze_private_connectivity_coverage is a full zero-trust posture assessment. "
            "Use private_endpoint_list to simply enumerate existing private endpoints."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="analyze_dns_resolution_path",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"dns", "resolution", "path", "fqdn", "vnet", "trace", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "trace DNS resolution path for api.example.com",
            "analyze DNS path from my VNet",
            "how does DNS resolve for my FQDN",
            "debug DNS resolution chain from vnet-prod",
        ),
        conflicts_with=frozenset({"check_dns_resolution"}),
        conflict_note=(
            "analyze_dns_resolution_path traces the full resolution chain from a source VNet. "
            "Use check_dns_resolution for simple DNS checks without source VNet context."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="assess_network_security_posture",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"security", "posture", "cis", "nist", "pci", "compliance", "network", "audit"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "assess my network security posture",
            "run CIS Azure network compliance check",
            "security posture assessment for my network",
            "check network compliance against NIST",
            "network security audit",
        ),
        conflicts_with=frozenset({"nsg_list", "inspect_nsg_rules"}),
        conflict_note=(
            "assess_network_security_posture is a full CIS/NIST/PCI compliance scan — "
            "never use it for simple NSG listing or rule inspection queries."
        ),
        preferred_over=frozenset(),
    ),
    ToolManifest(
        tool_name="validate_hub_spoke_topology",
        source="network",
        domains=frozenset({"network"}),
        tags=frozenset({"hub", "spoke", "topology", "validate", "architecture", "network"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "validate my hub-spoke topology",
            "check hub-spoke network architecture",
            "is my hub-spoke topology healthy",
            "validate hub and spoke VNet peering",
        ),
        conflicts_with=frozenset(),
        conflict_note="",
        preferred_over=frozenset(),
    ),
]
