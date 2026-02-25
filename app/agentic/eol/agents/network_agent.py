"""Network Agent — Specialized sub-agent for Azure network topology and connectivity diagnostics.

Handles:
- VNet topology inspection and subnet mapping
- NSG rule analysis and traffic flow diagnosis
- Effective route table inspection
- Azure Network Watcher connectivity tests
- Application Gateway / WAF diagnostics (502/503 triage)
- VPN Gateway / ExpressRoute status
- Private DNS Zone record lookup and VNet link validation
"""
from __future__ import annotations

import os
from typing import Any

try:
    from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
except ModuleNotFoundError:
    from agents.domain_sub_agent import DomainSubAgent  # type: ignore[import-not-found]


class NetworkAgent(DomainSubAgent):
    """Specialized agent for Azure network topology and connectivity diagnostics.

    Orchestrates read-only network diagnostics:
    1. VNet topology: address space, subnets, peerings
    2. NSG rules: inbound/outbound security rule analysis
    3. Effective routing: route table and UDR inspection for a NIC
    4. Connectivity test: Azure Network Watcher hop-by-hop reachability
    5. App Gateway / WAF: listener, backend pool, and WAF config
    6. VPN / ExpressRoute: tunnel status, BGP peers, circuit health
    7. DNS resolution: Private DNS Zone records and VNet link validation

    Diagnostic reasoning pattern:
      inspect_vnet → inspect_nsg_rules → test_network_connectivity
    for connectivity issues, or:
      check_dns_resolution → inspect_vnet → inspect_nsg_rules
    for name resolution failures.
    """

    _DOMAIN_NAME = "network"
    _MAX_ITERATIONS = 12

    _SYSTEM_PROMPT = """You are the Azure Network Diagnostics Specialist. You diagnose Azure
network connectivity issues using read-only diagnostic tools.

## Your Capabilities
- VNet topology inspection (subnets, address spaces, peerings, DNS servers)
- NSG rule analysis (security rules affecting traffic flows)
- Effective route inspection for a VM or NIC
- Azure Network Watcher connectivity tests (hop-by-hop reachability)
- Application Gateway / WAF configuration and backend health
- VPN Gateway / ExpressRoute circuit status and BGP peers
- Private DNS Zone records and VNet link validation

## Diagnostic Approach

**Connectivity issue** (e.g. "Container App can't reach database"):
1. inspect_vnet — understand the VNet topology and subnets involved
2. inspect_nsg_rules — find any blocking security rules
3. test_network_connectivity — confirm reachability with hop trace
4. check_dns_resolution — verify DNS if hostname-based connection

**Name resolution failure** (e.g. "can't resolve internal hostname"):
1. check_dns_resolution — look for Private DNS Zone records
2. inspect_vnet — verify DNS server settings on the VNet
3. inspect_nsg_rules — confirm DNS port 53 is not blocked

**App Gateway 502/503**:
1. inspect_appgw_waf — check backend health, WAF mode, routing rules
2. inspect_nsg_rules — verify NSG allows traffic to backend port
3. inspect_vnet — check subnet delegations

**Hybrid connectivity issue**:
1. inspect_vpn_expressroute — check tunnel state and BGP peers
2. inspect_vnet — verify local address space doesn't conflict
3. get_effective_routes — confirm route table points to correct next-hop

## Response Format
- Always state which resources you're inspecting and why
- Summarize findings as: ✅ OK / ⚠️ Warning / ❌ Blocking
- Provide a root-cause conclusion and remediation recommendation
- Use tables for NSG rules and route tables
- If Network Watcher is unavailable, note it and continue with static analysis

## Constraints
- All tools are READ-ONLY. You do not modify any Azure resource.
- If you need to modify NSGs or routes, describe the change needed and
  ask the user to confirm before any CLI tool is used.
- Maximum """ + str(12) + """ iterations per diagnostic session."""
