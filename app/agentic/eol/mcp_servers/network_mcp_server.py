"""Network MCP Server — Azure Network Diagnostics

Provides 10 read-only network diagnostic tools via FastMCP:
  1. virtual_network_list     — List all VNets in a subscription / resource group
  2. private_endpoint_list    — List all private endpoints with their private IPs (NIC-aware)
  3. inspect_vnet             — VNet address space, subnets, peerings, DNS
  4. nsg_list                 — List all NSGs in a subscription / resource group
  5. inspect_nsg_rules        — NSG security rules with traffic direction
  6. get_effective_routes     — Effective routes for a VM/NIC
  7. test_network_connectivity — Azure Network Watcher connectivity check
  8. inspect_appgw_waf        — App Gateway / WAF config and backend health
  9. inspect_vpn_expressroute — VPN Gateway / ExpressRoute circuit status
 10. check_dns_resolution     — DNS resolver configuration and name resolution

All tools are read-only diagnostics; none modify Azure resources.
Reuses ResourceDiscoveryEngine._enrich_vnet() for VNet enrichment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent

try:
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.mgmt.network import NetworkManagementClient
    from azure.mgmt.resource import ResourceManagementClient
except ImportError:
    DefaultAzureCredential = None
    ClientSecretCredential = None
    NetworkManagementClient = None
    ResourceManagementClient = None

try:
    from app.agentic.eol.utils.azure_cli_executor import get_azure_cli_executor
except ModuleNotFoundError:
    from utils.azure_cli_executor import get_azure_cli_executor

_LOG_LEVEL_NAME = os.getenv("NETWORK_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO
try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Suppress verbose Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

_server = FastMCP(name="azure-network")
_credential: Optional[Any] = None
_subscription_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def _get_credential() -> Any:
    global _credential
    if _credential is not None:
        return _credential
    if DefaultAzureCredential is None:
        raise RuntimeError("azure-identity package not installed")

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant_id and client_id and client_secret and ClientSecretCredential:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        _credential = DefaultAzureCredential()
    return _credential


def _get_subscription_id() -> str:
    global _subscription_id
    if _subscription_id:
        return _subscription_id
    _subscription_id = (
        os.getenv("SUBSCRIPTION_ID")
        or os.getenv("AZURE_SUBSCRIPTION_ID")
        or ""
    )
    return _subscription_id


def _parse_resource_id(resource_id: str):
    """Parse an ARM resource ID into (subscription_id, resource_group, name)."""
    parts = [p for p in resource_id.split("/") if p]
    sub_id = ""
    rg = ""
    name = parts[-1] if parts else ""
    for i, part in enumerate(parts):
        if part.lower() == "subscriptions" and i + 1 < len(parts):
            sub_id = parts[i + 1]
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            rg = parts[i + 1]
    return sub_id or _get_subscription_id(), rg, name


def _text_result(data: Dict[str, Any]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool 1: virtual_network_list
# ---------------------------------------------------------------------------

@_server.tool()
async def virtual_network_list(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group name to scope the listing. Omit to list all VNets in the subscription.",
    ] = None,
) -> List[TextContent]:
    """List all virtual networks in a subscription or resource group.

    Returns name, location, address prefixes, subnet count, peering count and
    provisioning state for each VNet. Use this before inspect_vnet to discover
    which VNets exist.
    """
    try:
        sub_id = subscription_id or _get_subscription_id()
        executor = await get_azure_cli_executor()

        cmd = f"az network vnet list --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"

        cli_result = await executor.execute(cmd, timeout=60, add_subscription=False)

        if cli_result.get("status") != "success":
            return _text_result({"success": False, "error": cli_result.get("error", "CLI call failed")})

        vnets_raw: List[Dict[str, Any]] = cli_result.get("output") or []
        result = []
        for vnet in vnets_raw:
            addr_space = vnet.get("addressSpace") or {}
            result.append({
                "name": vnet.get("name"),
                "resource_group": vnet.get("resourceGroup"),
                "location": vnet.get("location"),
                "address_prefixes": addr_space.get("addressPrefixes") or [],
                "subnet_count": len(vnet.get("subnets") or []),
                "peering_count": len(vnet.get("virtualNetworkPeerings") or []),
                "provisioning_state": vnet.get("provisioningState"),
                "resource_id": vnet.get("id"),
            })

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "vnet_count": len(result),
            "virtual_networks": result,
        })

    except Exception as exc:
        logger.exception("virtual_network_list failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 2: private_endpoint_list
# ---------------------------------------------------------------------------

@_server.tool()
async def private_endpoint_list(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to SUBSCRIPTION_ID env var.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group filter. Omit to list across the full subscription.",
    ] = None,
) -> List[TextContent]:
    """List all private endpoints in a subscription or resource group, with their private IP addresses.

    Private endpoints linked to Azure private DNS zones do not populate customDnsConfigs.
    This tool explicitly resolves IPs from the attached NIC's ipConfigurations so the IP
    is always present in the output regardless of DNS integration type.

    Returns name, resource_group, location, private_ip, connected_resource_type, and
    connection_state for each endpoint.
    """
    try:
        sub_id = subscription_id or _get_subscription_id()
        executor = await get_azure_cli_executor()

        # Step 1: list all private endpoints
        cmd = f"az network private-endpoint list --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"

        cli_result = await executor.execute(cmd, timeout=60, add_subscription=False)
        if cli_result.get("status") != "success":
            return _text_result({"success": False, "error": cli_result.get("error", "CLI call failed")})

        endpoints_raw: List[Dict[str, Any]] = cli_result.get("output") or []

        # Step 2: for endpoints without customDnsConfigs, resolve IP from NIC
        # Build a list of NIC IDs to fetch in parallel for efficiency
        nic_ids_needed: Dict[str, str] = {}  # nic_id -> endpoint_name
        for ep in endpoints_raw:
            dns_configs = ep.get("customDnsConfigs") or []
            has_ip = any(c.get("ipAddresses") for c in dns_configs)
            if not has_ip:
                nics = ep.get("networkInterfaces") or []
                if nics:
                    nic_id = nics[0].get("id", "")
                    if nic_id:
                        nic_ids_needed[nic_id] = ep.get("name", "")

        # Fetch NIC private IPs in parallel
        async def _fetch_nic_ip(nic_id: str) -> Optional[str]:
            try:
                nic_result = await executor.execute(
                    f"az network nic show --ids '{nic_id}' --query 'ipConfigurations[0].privateIPAddress' -o tsv",
                    timeout=30,
                    add_subscription=False,
                )
                if nic_result.get("status") == "success":
                    raw = nic_result.get("output")
                    if isinstance(raw, str):
                        return raw.strip() or None
                    if isinstance(raw, list) and raw:
                        return str(raw[0]).strip() or None
            except Exception as _exc:
                logger.debug("_fetch_nic_ip failed for %s: %s", nic_id, _exc)
            return None

        nic_tasks = {nic_id: asyncio.create_task(_fetch_nic_ip(nic_id)) for nic_id in nic_ids_needed}
        if nic_tasks:
            await asyncio.gather(*nic_tasks.values(), return_exceptions=True)
        nic_ip_map: Dict[str, Optional[str]] = {
            nic_id: (task.result() if not task.exception() else None)  # type: ignore[union-attr]
            for nic_id, task in nic_tasks.items()
        }

        # Build results
        result = []
        for ep in endpoints_raw:
            name = ep.get("name")
            rg = ep.get("resourceGroup")
            location = ep.get("location")

            # Resolve private IP
            private_ip: Optional[str] = None
            dns_configs = ep.get("customDnsConfigs") or []
            for dns_cfg in dns_configs:
                ips = dns_cfg.get("ipAddresses") or []
                if ips:
                    private_ip = ips[0]
                    break
            if not private_ip:
                nics = ep.get("networkInterfaces") or []
                if nics:
                    nic_id = nics[0].get("id", "")
                    private_ip = nic_ip_map.get(nic_id)

            # Resolve connected resource type
            conn_type: Optional[str] = None
            conns = ep.get("privateLinkServiceConnections") or ep.get("manualPrivateLinkServiceConnections") or []
            if conns:
                service_id = conns[0].get("privateLinkServiceId", "")
                conn_type = service_id.split("/providers/")[-1].split("/")[0] if "/providers/" in service_id else None
                conn_type_parts = service_id.rsplit("/", 2)
                conn_type = "/".join(conn_type_parts[-2:]) if len(conn_type_parts) >= 2 else service_id

            conn_state: Optional[str] = None
            if conns:
                state_obj = conns[0].get("privateLinkServiceConnectionState") or {}
                conn_state = state_obj.get("status")

            result.append({
                "name": name,
                "resource_group": rg,
                "location": location,
                "private_ip": private_ip,
                "connected_resource": conn_type,
                "connection_state": conn_state,
                "provisioning_state": ep.get("provisioningState"),
                "resource_id": ep.get("id"),
            })

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "private_endpoint_count": len(result),
            "private_endpoints": result,
        })

    except Exception as exc:
        logger.exception("private_endpoint_list failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 3: inspect_vnet
# ---------------------------------------------------------------------------

@_server.tool()
async def inspect_vnet(
    context: Context,
    resource_id: Annotated[
        str,
        "ARM resource ID of the VNet (e.g. /subscriptions/.../virtualNetworks/my-vnet) "
        "or short form 'resource_group/vnet_name'.",
    ],
) -> List[TextContent]:
    """Inspect a VNet: address space, subnets, peerings, DNS servers, DDoS status.

    Returns subnet-level detail including NSG / route-table attachments and
    private endpoint counts. Use before inspect_nsg_rules for a topology overview.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        # Support short form 'rg/vnet_name'
        if not resource_id.startswith("/"):
            parts = resource_id.split("/", 1)
            rg = parts[0]
            vnet_name = parts[1] if len(parts) > 1 else parts[0]
            sub_id = _get_subscription_id()
        else:
            sub_id, rg, vnet_name = _parse_resource_id(resource_id)

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            return client.virtual_networks.get(rg, vnet_name)

        vnet = await loop.run_in_executor(None, _get)

        address_prefixes: List[str] = []
        if vnet.address_space and vnet.address_space.address_prefixes:
            address_prefixes = list(vnet.address_space.address_prefixes)

        subnets: List[Dict[str, Any]] = []
        if vnet.subnets:
            for sn in vnet.subnets:
                subnets.append({
                    "name": sn.name,
                    "address_prefix": sn.address_prefix,
                    "nsg_id": sn.network_security_group.id if sn.network_security_group else None,
                    "route_table_id": sn.route_table.id if sn.route_table else None,
                    "delegations": [d.service_name for d in (sn.delegations or [])],
                    "private_endpoint_count": len(sn.private_endpoints) if sn.private_endpoints else 0,
                })

        peerings: List[Dict[str, Any]] = []
        if vnet.virtual_network_peerings:
            for p in vnet.virtual_network_peerings:
                peerings.append({
                    "name": p.name,
                    "peering_state": str(p.peering_state) if p.peering_state else None,
                    "remote_vnet_id": p.remote_virtual_network.id if p.remote_virtual_network else None,
                    "allow_forwarded_traffic": p.allow_forwarded_traffic,
                    "allow_gateway_transit": p.allow_gateway_transit,
                    "use_remote_gateways": p.use_remote_gateways,
                })

        dns_servers: List[str] = []
        if vnet.dhcp_options and vnet.dhcp_options.dns_servers:
            dns_servers = list(vnet.dhcp_options.dns_servers)

        return _text_result({
            "success": True,
            "vnet_name": vnet_name,
            "resource_group": rg,
            "location": vnet.location,
            "address_prefixes": address_prefixes,
            "subnet_count": len(subnets),
            "subnets": subnets,
            "peering_count": len(peerings),
            "peerings": peerings,
            "dns_servers": dns_servers,
            "enable_ddos_protection": vnet.enable_ddos_protection,
            "provisioning_state": vnet.provisioning_state,
        })

    except Exception as exc:
        logger.exception("inspect_vnet failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 3: nsg_list
# ---------------------------------------------------------------------------

@_server.tool()
async def nsg_list(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group name to scope the listing. Omit to list all NSGs in the subscription.",
    ] = None,
) -> List[TextContent]:
    """List all Network Security Groups (NSGs) in a subscription or resource group.

    Returns name, location, resource group, subnet/NIC association counts and
    provisioning state for each NSG. Use nsg_list to discover which NSGs exist,
    then inspect_nsg_rules to examine rules on a specific NSG.
    """
    try:
        sub_id = subscription_id or _get_subscription_id()
        executor = await get_azure_cli_executor()

        cmd = f"az network nsg list --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"

        cli_result = await executor.execute(cmd, timeout=60, add_subscription=False)

        if cli_result.get("status") != "success":
            return _text_result({"success": False, "error": cli_result.get("error", "CLI call failed")})

        nsgs_raw: List[Dict[str, Any]] = cli_result.get("output") or []
        result = []
        for nsg in nsgs_raw:
            result.append({
                "name": nsg.get("name"),
                "resource_group": nsg.get("resourceGroup"),
                "location": nsg.get("location"),
                "subnet_association_count": len(nsg.get("subnets") or []),
                "nic_association_count": len(nsg.get("networkInterfaces") or []),
                "custom_rule_count": len(nsg.get("securityRules") or []),
                "provisioning_state": nsg.get("provisioningState"),
                "resource_id": nsg.get("id"),
            })

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "nsg_count": len(result),
            "network_security_groups": result,
        })

    except Exception as exc:
        logger.exception("nsg_list failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 4: inspect_nsg_rules
# ---------------------------------------------------------------------------

@_server.tool()
async def inspect_nsg_rules(
    context: Context,
    resource_id: Annotated[
        str,
        "ARM resource ID of the NSG or short form 'resource_group/nsg_name'.",
    ],
    direction: Annotated[
        str,
        "Filter rules by direction: 'Inbound', 'Outbound', or 'Both' (default).",
    ] = "Both",
) -> List[TextContent]:
    """List all security rules for a Network Security Group (NSG).

    Returns both custom rules and default rules, sorted by priority.
    Direction filter accepts 'Inbound', 'Outbound', or 'Both'.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        if not resource_id.startswith("/"):
            parts = resource_id.split("/", 1)
            rg = parts[0]
            nsg_name = parts[1] if len(parts) > 1 else parts[0]
            sub_id = _get_subscription_id()
        else:
            sub_id, rg, nsg_name = _parse_resource_id(resource_id)

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            return client.network_security_groups.get(rg, nsg_name)

        nsg = await loop.run_in_executor(None, _get)

        def _serialize_rule(r: Any) -> Dict[str, Any]:
            return {
                "name": r.name,
                "priority": r.priority,
                "direction": str(r.direction) if r.direction else None,
                "access": str(r.access) if r.access else None,
                "protocol": str(r.protocol) if r.protocol else None,
                "source_address_prefix": r.source_address_prefix,
                "source_port_range": r.source_port_range,
                "destination_address_prefix": r.destination_address_prefix,
                "destination_port_range": r.destination_port_range,
                "description": r.description,
                "provisioning_state": r.provisioning_state,
            }

        all_rules: List[Dict[str, Any]] = []
        for rule in (nsg.security_rules or []):
            all_rules.append(_serialize_rule(rule))
        for rule in (nsg.default_security_rules or []):
            d = _serialize_rule(rule)
            d["is_default"] = True
            all_rules.append(d)

        if direction.lower() != "both":
            all_rules = [r for r in all_rules if (r.get("direction") or "").lower() == direction.lower()]

        all_rules.sort(key=lambda r: (r.get("direction") or "", r.get("priority") or 9999))

        return _text_result({
            "success": True,
            "nsg_name": nsg_name,
            "resource_group": rg,
            "location": nsg.location,
            "rule_count": len(all_rules),
            "rules": all_rules,
            "subnet_associations": [
                sn.id for sn in (nsg.subnets or [])
            ],
            "nic_associations": [
                nic.id for nic in (nsg.network_interfaces or [])
            ],
        })

    except Exception as exc:
        logger.exception("inspect_nsg_rules failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 5: get_effective_routes
# ---------------------------------------------------------------------------

@_server.tool()
async def get_effective_routes(
    context: Context,
    nic_resource_id: Annotated[
        str,
        "ARM resource ID of the network interface card (NIC) to inspect effective routes for.",
    ],
) -> List[TextContent]:
    """Get effective routes for a network interface card (NIC).

    Shows both user-defined routes and system routes, indicating which
    next-hop is actually in effect for each destination prefix.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        sub_id, rg, nic_name = _parse_resource_id(nic_resource_id)
        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            poller = client.network_interfaces.begin_get_effective_route_table(rg, nic_name)
            return poller.result()

        result = await loop.run_in_executor(None, _get)

        routes: List[Dict[str, Any]] = []
        for route in (result.value or []):
            routes.append({
                "name": route.name,
                "source": str(route.source) if route.source else None,
                "state": str(route.state) if route.state else None,
                "address_prefix": list(route.address_prefix or []),
                "next_hop_type": str(route.next_hop_type) if route.next_hop_type else None,
                "next_hop_ip_address": list(route.next_hop_ip_address or []),
                "disabled_bgp_route_propagation": route.disabled_bgp_route_propagation,
            })

        return _text_result({
            "success": True,
            "nic_name": nic_name,
            "resource_group": rg,
            "route_count": len(routes),
            "routes": routes,
        })

    except Exception as exc:
        logger.exception("get_effective_routes failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 4: test_network_connectivity
# ---------------------------------------------------------------------------

@_server.tool()
async def test_network_connectivity(
    context: Context,
    source_resource_id: Annotated[
        str,
        "ARM resource ID of the source VM or NIC.",
    ],
    destination_address: Annotated[
        str,
        "Destination IP address, FQDN, or ARM resource ID to test connectivity to.",
    ],
    destination_port: Annotated[
        int,
        "Destination TCP port to test (e.g. 443, 3306, 5432).",
    ] = 443,
    protocol: Annotated[
        str,
        "Protocol to test: 'TCP' (default) or 'HTTP'.",
    ] = "TCP",
) -> List[TextContent]:
    """Test network connectivity between two endpoints using Azure Network Watcher.

    Uses Network Watcher connectivity check to determine reachability,
    hop-by-hop latency, and any network policy blockers between source and
    destination. Requires Network Watcher to be enabled in the region.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        from azure.mgmt.network import NetworkManagementClient as NMC
        from azure.mgmt.network.models import (
            ConnectivityParameters,
            ConnectivitySource,
            ConnectivityDestination,
        )

        sub_id, rg, _ = _parse_resource_id(source_resource_id)
        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _check():
            client = NMC(credential, sub_id)

            # Find the Network Watcher for the subscription (use first available)
            watchers = list(client.network_watchers.list_all())
            if not watchers:
                raise ValueError(
                    "No Network Watcher found in subscription. "
                    "Enable Azure Network Watcher to use connectivity checks."
                )
            watcher = watchers[0]
            watcher_rg = watcher.id.split("/")[4] if watcher.id else rg

            params = ConnectivityParameters(
                source=ConnectivitySource(resource_id=source_resource_id),
                destination=ConnectivityDestination(
                    address=destination_address,
                    port=destination_port,
                ),
                protocol=protocol,
            )
            poller = client.network_watchers.begin_check_connectivity(
                watcher_rg,
                watcher.name,
                params,
            )
            return poller.result()

        result = await loop.run_in_executor(None, _check)

        hops: List[Dict[str, Any]] = []
        for hop in (result.hops or []):
            issues = []
            for issue in (hop.issues or []):
                issues.append({
                    "origin": str(issue.origin) if issue.origin else None,
                    "severity": str(issue.severity) if issue.severity else None,
                    "type": str(issue.type) if issue.type else None,
                    "context": issue.context,
                })
            hops.append({
                "type": str(hop.type) if hop.type else None,
                "id": hop.id,
                "address": hop.address,
                "resource_id": hop.resource_id,
                "round_trip_time_ms": hop.next_hop_ids,
                "issues": issues,
            })

        return _text_result({
            "success": True,
            "connection_status": str(result.connection_status) if result.connection_status else None,
            "avg_latency_ms": result.avg_latency_in_ms,
            "min_latency_ms": result.min_latency_in_ms,
            "max_latency_ms": result.max_latency_in_ms,
            "probes_sent": result.probes_sent,
            "probes_failed": result.probes_failed,
            "hop_count": len(hops),
            "hops": hops,
            "source": source_resource_id,
            "destination": destination_address,
            "port": destination_port,
            "protocol": protocol,
        })

    except Exception as exc:
        logger.exception("test_network_connectivity failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 5: inspect_appgw_waf
# ---------------------------------------------------------------------------

@_server.tool()
async def inspect_appgw_waf(
    context: Context,
    resource_id: Annotated[
        str,
        "ARM resource ID of the Application Gateway or short form 'resource_group/appgw_name'.",
    ],
    include_backend_health: Annotated[
        bool,
        "If True, also retrieve backend health pools status (may add ~5s latency).",
    ] = True,
) -> List[TextContent]:
    """Inspect an Application Gateway / WAF: SKU, listeners, routing rules, backend pools.

    Optionally retrieves backend health to identify unhealthy pool members.
    Useful for diagnosing 502/503 errors from App Gateway.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        if not resource_id.startswith("/"):
            parts = resource_id.split("/", 1)
            rg = parts[0]
            appgw_name = parts[1] if len(parts) > 1 else parts[0]
            sub_id = _get_subscription_id()
        else:
            sub_id, rg, appgw_name = _parse_resource_id(resource_id)

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            gw = client.application_gateways.get(rg, appgw_name)
            backend_health = None
            if include_backend_health:
                try:
                    poller = client.application_gateways.begin_backend_health(rg, appgw_name)
                    backend_health = poller.result()
                except Exception as bhe:
                    logger.warning("Backend health check failed: %s", bhe)
            return gw, backend_health

        gw, backend_health = await loop.run_in_executor(None, _get)

        listeners = [
            {
                "name": l.name,
                "protocol": str(l.protocol) if l.protocol else None,
                "port": l.frontend_port.id.split("/")[-1] if l.frontend_port else None,
                "host_name": l.host_name,
                "require_server_name_indication": l.require_server_name_indication,
            }
            for l in (gw.http_listeners or [])
        ]

        pools = [
            {
                "name": p.name,
                "backend_addresses": [
                    {"fqdn": a.fqdn, "ip": a.ip_address}
                    for a in (p.backend_addresses or [])
                ],
            }
            for p in (gw.backend_address_pools or [])
        ]

        backend_health_summary: Optional[List[Dict[str, Any]]] = None
        if backend_health:
            backend_health_summary = []
            for pool in (backend_health.backend_address_pools or []):
                pool_name = pool.backend_address_pool.id.split("/")[-1] if pool.backend_address_pool else "unknown"
                for http_setting in (pool.backend_http_settings_collection or []):
                    for server in (http_setting.servers or []):
                        backend_health_summary.append({
                            "pool": pool_name,
                            "address": server.address,
                            "health": str(server.health) if server.health else None,
                            "health_probe_log": server.health_probe_log,
                        })

        waf_config = None
        if gw.web_application_firewall_configuration:
            w = gw.web_application_firewall_configuration
            waf_config = {
                "enabled": w.enabled,
                "firewall_mode": str(w.firewall_mode) if w.firewall_mode else None,
                "rule_set_type": w.rule_set_type,
                "rule_set_version": w.rule_set_version,
            }

        return _text_result({
            "success": True,
            "appgw_name": appgw_name,
            "resource_group": rg,
            "sku_name": str(gw.sku.name) if gw.sku else None,
            "sku_tier": str(gw.sku.tier) if gw.sku else None,
            "capacity": gw.sku.capacity if gw.sku else None,
            "operational_state": str(gw.operational_state) if gw.operational_state else None,
            "provisioning_state": gw.provisioning_state,
            "listener_count": len(listeners),
            "listeners": listeners,
            "backend_pool_count": len(pools),
            "backend_pools": pools,
            "waf_config": waf_config,
            "backend_health": backend_health_summary,
        })

    except Exception as exc:
        logger.exception("inspect_appgw_waf failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 6: inspect_vpn_expressroute
# ---------------------------------------------------------------------------

@_server.tool()
async def inspect_vpn_expressroute(
    context: Context,
    resource_group: Annotated[str, "Resource group containing the VPN/ExpressRoute gateway."],
    gateway_name: Annotated[str, "Name of the VPN Gateway or ExpressRoute Gateway."],
    gateway_type: Annotated[
        str,
        "Type of gateway: 'vpn' (VPN Gateway) or 'expressroute' (ExpressRoute Gateway).",
    ] = "vpn",
) -> List[TextContent]:
    """Inspect a VPN Gateway or ExpressRoute gateway: connection status, BGP peers, bandwidth.

    Returns connection state, tunnel status, BGP peer health, and circuit
    peering details for ExpressRoute. Essential for hybrid connectivity issues.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        sub_id = _get_subscription_id()
        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            if gateway_type.lower() == "expressroute":
                gw = client.express_route_gateways.get(resource_group, gateway_name)
                connections = list(client.express_route_connections.list(resource_group, gateway_name).value or [])
                return {"type": "expressroute", "gw": gw, "connections": connections}
            else:
                gw = client.virtual_network_gateways.get(resource_group, gateway_name)
                connections = list(client.virtual_network_gateway_connections.list(resource_group))
                return {"type": "vpn", "gw": gw, "connections": connections}

        data = await loop.run_in_executor(None, _get)
        gw = data["gw"]

        if data["type"] == "expressroute":
            circuits_info = []
            for conn in data["connections"]:
                circuits_info.append({
                    "name": conn.name,
                    "provisioning_state": conn.provisioning_state,
                    "routing_weight": conn.routing_weight,
                    "express_route_circuit_id": conn.express_route_circuit_peering.id if conn.express_route_circuit_peering else None,
                })
            return _text_result({
                "success": True,
                "gateway_type": "expressroute",
                "gateway_name": gateway_name,
                "resource_group": resource_group,
                "provisioning_state": gw.provisioning_state,
                "scale_units": gw.auto_scale_configuration.bounds.min if (gw.auto_scale_configuration and gw.auto_scale_configuration.bounds) else None,
                "circuits": circuits_info,
            })
        else:
            connections_info = []
            for conn in data["connections"]:
                connections_info.append({
                    "name": conn.name,
                    "connection_type": str(conn.connection_type) if conn.connection_type else None,
                    "connection_status": str(conn.connection_status) if conn.connection_status else None,
                    "ingress_bytes": conn.ingress_bytes_transferred,
                    "egress_bytes": conn.egress_bytes_transferred,
                    "enable_bgp": conn.enable_bgp,
                })

            bgp_settings = None
            if gw.bgp_settings:
                bgp_settings = {
                    "asn": gw.bgp_settings.asn,
                    "peering_address": gw.bgp_settings.bgp_peering_address,
                    "peer_weight": gw.bgp_settings.peer_weight,
                }

            return _text_result({
                "success": True,
                "gateway_type": "vpn",
                "gateway_name": gateway_name,
                "resource_group": resource_group,
                "gateway_type_detail": str(gw.gateway_type) if gw.gateway_type else None,
                "vpn_type": str(gw.vpn_type) if gw.vpn_type else None,
                "sku": str(gw.sku.name) if gw.sku else None,
                "provisioning_state": gw.provisioning_state,
                "bgp_settings": bgp_settings,
                "active_active": gw.active_active,
                "enable_bgp": gw.enable_bgp,
                "connections": connections_info,
            })

    except Exception as exc:
        logger.exception("inspect_vpn_expressroute failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 7: check_dns_resolution
# ---------------------------------------------------------------------------

@_server.tool()
async def check_dns_resolution(
    context: Context,
    hostname: Annotated[str, "Hostname or FQDN to resolve (e.g. 'myapp.internal.contoso.com')."],
    resource_group: Annotated[
        str,
        "Resource group to look up Private DNS Zones in. Optional; leave empty to skip Private DNS lookup.",
    ] = "",
    vnet_resource_id: Annotated[
        str,
        "ARM resource ID of the VNet to check Private DNS Zone links for. Optional.",
    ] = "",
) -> List[TextContent]:
    """Check DNS resolution configuration for a hostname.

    Returns:
    - Private DNS Zone records matching the hostname (if resource_group provided)
    - VNet links for the relevant Private DNS Zone (if vnet_resource_id provided)
    - Whether the zone is auto-registered

    Use this when a Container App, Private Endpoint, or VM cannot resolve
    an internal hostname.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        from azure.mgmt.privatedns import PrivateDnsManagementClient

        sub_id = _get_subscription_id()
        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # Extract domain from hostname (e.g. 'myapp.contoso.azure.com' → 'contoso.azure.com')
        hostname_parts = hostname.split(".")
        # Try zone names from the most-specific to least-specific suffix
        possible_zones = [
            ".".join(hostname_parts[i:]) for i in range(1, len(hostname_parts))
        ]

        def _lookup():
            if not resource_group:
                return {"zones_checked": [], "records": [], "vnet_links": []}

            dns_client = PrivateDnsManagementClient(credential, sub_id)

            zones = list(dns_client.private_zones.list_by_resource_group(resource_group))
            matching_zones = [z for z in zones if any(z.name.endswith(pz) for pz in possible_zones)]

            records_found: List[Dict[str, Any]] = []
            vnet_links_found: List[Dict[str, Any]] = []

            for zone in matching_zones:
                # Look for A, CNAME records for the hostname label
                label = hostname[: len(hostname) - len(zone.name) - 1] if hostname.endswith(zone.name) else hostname
                for record_set in dns_client.record_sets.list(resource_group, zone.name):
                    if record_set.name in (label, "@", hostname):
                        entry: Dict[str, Any] = {
                            "zone": zone.name,
                            "name": record_set.name,
                            "type": record_set.type,
                            "ttl": record_set.ttl,
                        }
                        if record_set.a_records:
                            entry["a_records"] = [r.ipv4_address for r in record_set.a_records]
                        if record_set.cname_record:
                            entry["cname"] = record_set.cname_record.cname
                        records_found.append(entry)

                # VNet links for this zone
                if vnet_resource_id:
                    for link in dns_client.virtual_network_links.list(resource_group, zone.name):
                        if vnet_resource_id.lower() in (link.virtual_network.id or "").lower():
                            vnet_links_found.append({
                                "zone": zone.name,
                                "link_name": link.name,
                                "registration_enabled": link.registration_enabled,
                                "virtual_network_link_state": str(link.virtual_network_link_state) if link.virtual_network_link_state else None,
                            })

            return {
                "zones_checked": [z.name for z in matching_zones],
                "records": records_found,
                "vnet_links": vnet_links_found,
            }

        result = await loop.run_in_executor(None, _lookup)

        return _text_result({
            "success": True,
            "hostname": hostname,
            "possible_zone_suffixes": possible_zones[:5],
            "zones_checked": result["zones_checked"],
            "records_found": len(result["records"]),
            "records": result["records"],
            "vnet_links": result["vnet_links"],
        })

    except Exception as exc:
        logger.exception("check_dns_resolution failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point (run as standalone MCP server via stdio)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _server.run(transport="stdio")
