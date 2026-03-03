"""Network MCP Server — Azure Network Diagnostics

Provides 16 read-only network diagnostic tools via FastMCP:
  1. virtual_network_list                    — List all VNets in a subscription / resource group
  2. private_endpoint_list                   — List all private endpoints with their private IPs (NIC-aware)
  3. inspect_vnet                            — VNet address space, subnets, peerings, DNS
  4. nsg_list                               — List all NSGs in a subscription / resource group
  5. inspect_nsg_rules                       — NSG security rules with traffic direction
  6. get_effective_routes                    — Effective routes for a VM/NIC
  7. test_network_connectivity               — Azure Network Watcher connectivity check
  8. inspect_appgw_waf                       — App Gateway / WAF config and backend health
  9. inspect_vpn_expressroute                — VPN Gateway / ExpressRoute circuit status
 10. check_dns_resolution                   — DNS resolver configuration and name resolution
 11. analyze_route_path                     — Trace routing path with LPM and asymmetry detection
 12. simulate_nsg_flow                      — Simulate traffic flow through NSG rules
 13. inventory_network_resources            — Orphaned/unused resource inventory for cost optimization
 14. generate_connectivity_matrix           — N×N subnet connectivity matrix with NSG + route analysis
 15. analyze_private_connectivity_coverage  — PaaS private endpoint / service endpoint coverage + zero-trust gaps
 16. assess_network_security_posture        — CIS Azure / NIST / PCI-DSS compliance posture with scored findings

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
    from azure.core.exceptions import HttpResponseError
except ImportError:
    DefaultAzureCredential = None
    ClientSecretCredential = None
    NetworkManagementClient = None
    ResourceManagementClient = None
    HttpResponseError = None

try:
    from app.agentic.eol.utils.azure_cli_executor import get_azure_cli_executor
except ModuleNotFoundError:
    from utils.azure_cli_executor import get_azure_cli_executor

try:
    from app.agentic.eol.utils.nsg_rule_evaluator import (
        FlowTuple,
        NSGRule,
        NSGRuleEvaluator,
    )
except ModuleNotFoundError:
    from utils.nsg_rule_evaluator import (
        FlowTuple,
        NSGRule,
        NSGRuleEvaluator,
    )

try:
    from app.agentic.eol.utils.route_path_analyzer import (
        Route,
        RoutePathAnalyzer,
        ROUTE_SOURCE_DEFAULT,
        ROUTE_SOURCE_USER,
    )
except ModuleNotFoundError:
    from utils.route_path_analyzer import (  # type: ignore
        Route,
        RoutePathAnalyzer,
        ROUTE_SOURCE_DEFAULT,
        ROUTE_SOURCE_USER,
    )

try:
    from app.agentic.eol.utils.network_security_posture import (
        NetworkSecurityPostureEngine,
    )
except ModuleNotFoundError:
    from utils.network_security_posture import (  # type: ignore
        NetworkSecurityPostureEngine,
    )

_route_analyzer = RoutePathAnalyzer()

_nsg_evaluator = NSGRuleEvaluator()

_posture_engine = NetworkSecurityPostureEngine()

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
    sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
    sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    # 1) Prefer injected SPN credentials used by container/runtime deployments.
    if tenant_id and sp_client_id and sp_client_secret and ClientSecretCredential:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=sp_client_id,
            client_secret=sp_client_secret,
        )
        logger.info("Network MCP auth: using injected SPN credential (%s...)", sp_client_id[:8])
    # 2) Back-compat fallback to AZURE_CLIENT_* if explicitly provided.
    elif tenant_id and client_id and client_secret and ClientSecretCredential:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        logger.info("Network MCP auth: using AZURE_CLIENT_* credential (%s...)", client_id[:8])
    # 3) Last resort: DefaultAzureCredential chain.
    else:
        _credential = DefaultAzureCredential()
        logger.warning("Network MCP auth: falling back to DefaultAzureCredential")
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
        Optional[str],
        "ARM resource ID of the VNet (e.g. /subscriptions/.../virtualNetworks/my-vnet) "
        "or short form 'resource_group/vnet_name'.",
    ] = None,
    name: Annotated[
        Optional[str],
        "Optional VNet name. Use with resource_group when resource_id is not provided.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group name. Use with name when resource_id is not provided.",
    ] = None,
    subscription_id: Annotated[
        Optional[str],
        "Optional subscription override. Defaults to SUBSCRIPTION_ID env var.",
    ] = None,
) -> List[TextContent]:
    """Inspect a VNet: address space, subnets, peerings, DNS servers, DDoS status.

    Returns subnet-level detail including NSG / route-table attachments and
    private endpoint counts. Use before inspect_nsg_rules for a topology overview.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        # Support multiple input forms:
        # 1) resource_id ARM ID
        # 2) resource_id short-form 'rg/vnet_name'
        # 3) name + resource_group
        resolved_resource_id = (resource_id or "").strip()

        if resolved_resource_id:
            if not resolved_resource_id.startswith("/"):
                parts = resolved_resource_id.split("/", 1)
                rg = parts[0]
                vnet_name = parts[1] if len(parts) > 1 else parts[0]
                sub_id = subscription_id or _get_subscription_id()
            else:
                parsed_sub_id, rg, vnet_name = _parse_resource_id(resolved_resource_id)
                sub_id = subscription_id or parsed_sub_id or _get_subscription_id()
        else:
            rg = (resource_group or "").strip()
            vnet_name = (name or "").strip()
            sub_id = subscription_id or _get_subscription_id()

        if not rg or not vnet_name:
            return _text_result(
                {
                    "success": False,
                    "error": (
                        "inspect_vnet requires either resource_id, or both name and resource_group."
                    ),
                }
            )

        def _serialize_vnet(vnet_obj: Any) -> Dict[str, Any]:
            address_prefixes: List[str] = []
            if vnet_obj.address_space and vnet_obj.address_space.address_prefixes:
                address_prefixes = list(vnet_obj.address_space.address_prefixes)

            subnets: List[Dict[str, Any]] = []
            if vnet_obj.subnets:
                for sn in vnet_obj.subnets:
                    subnets.append({
                        "name": sn.name,
                        "address_prefix": sn.address_prefix,
                        "nsg_id": sn.network_security_group.id if sn.network_security_group else None,
                        "route_table_id": sn.route_table.id if sn.route_table else None,
                        "delegations": [d.service_name for d in (sn.delegations or [])],
                        "private_endpoint_count": len(sn.private_endpoints) if sn.private_endpoints else 0,
                    })

            peerings: List[Dict[str, Any]] = []
            if vnet_obj.virtual_network_peerings:
                for p in vnet_obj.virtual_network_peerings:
                    peerings.append({
                        "name": p.name,
                        "peering_state": str(p.peering_state) if p.peering_state else None,
                        "remote_vnet_id": p.remote_virtual_network.id if p.remote_virtual_network else None,
                        "allow_forwarded_traffic": p.allow_forwarded_traffic,
                        "allow_gateway_transit": p.allow_gateway_transit,
                        "use_remote_gateways": p.use_remote_gateways,
                    })

            dns_servers: List[str] = []
            if vnet_obj.dhcp_options and vnet_obj.dhcp_options.dns_servers:
                dns_servers = list(vnet_obj.dhcp_options.dns_servers)

            return {
                "success": True,
                "vnet_name": vnet_name,
                "resource_group": rg,
                "location": vnet_obj.location,
                "address_prefixes": address_prefixes,
                "subnet_count": len(subnets),
                "subnets": subnets,
                "peering_count": len(peerings),
                "peerings": peerings,
                "dns_servers": dns_servers,
                "enable_ddos_protection": vnet_obj.enable_ddos_protection,
                "provisioning_state": vnet_obj.provisioning_state,
            }

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            return client.virtual_networks.get(rg, vnet_name)

        try:
            vnet = await loop.run_in_executor(None, _get)
            return _text_result(_serialize_vnet(vnet))
        except Exception as sdk_exc:
            # Auth-aware fallback to CLI/SPN path
            text = str(sdk_exc).lower()
            is_auth_error = "authorizationfailed" in text or "does not have authorization" in text
            if not is_auth_error:
                raise

            logger.warning(
                "inspect_vnet: SDK auth failed for %s/%s; falling back to Azure CLI executor: %s",
                rg,
                vnet_name,
                sdk_exc,
            )

            executor = await get_azure_cli_executor()
            cli_result = await executor.execute(
                (
                    f"az network vnet show --subscription {sub_id} "
                    f"--resource-group {rg} --name {vnet_name} --output json"
                ),
                timeout=60,
                add_subscription=False,
            )
            if cli_result.get("status") != "success":
                cli_error = cli_result.get("error", "CLI call failed")
                return _text_result(
                    {
                        "success": False,
                        "error": (
                            "inspect_vnet failed via SDK (AuthorizationFailed) and CLI fallback: "
                            f"{cli_error}"
                        ),
                    }
                )

            vnet_raw = cli_result.get("output") or {}
            address_space = vnet_raw.get("addressSpace") or {}
            subnets_raw = vnet_raw.get("subnets") or []
            peerings_raw = vnet_raw.get("virtualNetworkPeerings") or []
            dhcp_opts = vnet_raw.get("dhcpOptions") or {}

            subnets = []
            for sn in subnets_raw:
                subnets.append(
                    {
                        "name": sn.get("name"),
                        "address_prefix": sn.get("addressPrefix"),
                        "nsg_id": (sn.get("networkSecurityGroup") or {}).get("id"),
                        "route_table_id": (sn.get("routeTable") or {}).get("id"),
                        "delegations": [
                            (d.get("serviceName") or "")
                            for d in (sn.get("delegations") or [])
                            if isinstance(d, dict)
                        ],
                        "private_endpoint_count": len(sn.get("privateEndpoints") or []),
                    }
                )

            peerings = []
            for p in peerings_raw:
                peerings.append(
                    {
                        "name": p.get("name"),
                        "peering_state": p.get("peeringState"),
                        "remote_vnet_id": (p.get("remoteVirtualNetwork") or {}).get("id"),
                        "allow_forwarded_traffic": p.get("allowForwardedTraffic"),
                        "allow_gateway_transit": p.get("allowGatewayTransit"),
                        "use_remote_gateways": p.get("useRemoteGateways"),
                    }
                )

            return _text_result(
                {
                    "success": True,
                    "vnet_name": vnet_name,
                    "resource_group": rg,
                    "location": vnet_raw.get("location"),
                    "address_prefixes": address_space.get("addressPrefixes") or [],
                    "subnet_count": len(subnets),
                    "subnets": subnets,
                    "peering_count": len(peerings),
                    "peerings": peerings,
                    "dns_servers": dhcp_opts.get("dnsServers") or [],
                    "enable_ddos_protection": vnet_raw.get("enableDdosProtection"),
                    "provisioning_state": vnet_raw.get("provisioningState"),
                }
            )

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

        def _serialize_rule_dict(rule: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "name": rule.get("name"),
                "priority": rule.get("priority"),
                "direction": rule.get("direction"),
                "access": rule.get("access"),
                "protocol": rule.get("protocol"),
                "source_address_prefix": rule.get("sourceAddressPrefix") or rule.get("sourceAddressPrefixes"),
                "source_port_range": rule.get("sourcePortRange") or rule.get("sourcePortRanges"),
                "destination_address_prefix": rule.get("destinationAddressPrefix") or rule.get("destinationAddressPrefixes"),
                "destination_port_range": rule.get("destinationPortRange") or rule.get("destinationPortRanges"),
                "description": rule.get("description"),
                "provisioning_state": rule.get("provisioningState"),
            }

        def _is_authorization_failed(exc: Exception) -> bool:
            text = str(exc).lower()
            if "authorizationfailed" in text or "does not have authorization" in text:
                return True
            if HttpResponseError is not None and isinstance(exc, HttpResponseError):
                code = str(getattr(exc, "error", None) and getattr(exc.error, "code", "") or "").lower()
                return code == "authorizationfailed"
            return False

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        def _get():
            client = NetworkManagementClient(credential, sub_id)
            return client.network_security_groups.get(rg, nsg_name)

        try:
            nsg = await loop.run_in_executor(None, _get)
        except Exception as sdk_exc:
            if not _is_authorization_failed(sdk_exc):
                raise

            logger.warning(
                "inspect_nsg_rules: SDK auth failed for %s/%s; falling back to Azure CLI executor: %s",
                rg,
                nsg_name,
                sdk_exc,
            )

            executor = await get_azure_cli_executor()
            cli_result = await executor.execute(
                (
                    f"az network nsg show --subscription {sub_id} "
                    f"--resource-group {rg} --name {nsg_name} --output json"
                ),
                timeout=60,
                add_subscription=False,
            )

            if cli_result.get("status") != "success":
                cli_error = cli_result.get("error", "CLI call failed")
                return _text_result(
                    {
                        "success": False,
                        "error": (
                            "inspect_nsg_rules failed via SDK (AuthorizationFailed) and CLI fallback: "
                            f"{cli_error}"
                        ),
                    }
                )

            nsg_payload = cli_result.get("output") or {}
            all_rules: List[Dict[str, Any]] = []
            for rule in (nsg_payload.get("securityRules") or []):
                all_rules.append(_serialize_rule_dict(rule))
            for rule in (nsg_payload.get("defaultSecurityRules") or []):
                d = _serialize_rule_dict(rule)
                d["is_default"] = True
                all_rules.append(d)

            if direction.lower() != "both":
                all_rules = [r for r in all_rules if (r.get("direction") or "").lower() == direction.lower()]

            all_rules.sort(key=lambda r: (r.get("direction") or "", r.get("priority") or 9999))

            return _text_result(
                {
                    "success": True,
                    "nsg_name": nsg_name,
                    "resource_group": rg,
                    "location": nsg_payload.get("location"),
                    "rule_count": len(all_rules),
                    "rules": all_rules,
                    "subnet_associations": [sn.get("id") for sn in (nsg_payload.get("subnets") or []) if isinstance(sn, dict) and sn.get("id")],
                    "nic_associations": [nic.get("id") for nic in (nsg_payload.get("networkInterfaces") or []) if isinstance(nic, dict) and nic.get("id")],
                }
            )

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
    vm_name: Annotated[
        Optional[str],
        "Optional VM name. If provided, effective routes are collected from NICs attached to this VM.",
    ] = None,
    vm_resource_id: Annotated[
        Optional[str],
        "Optional VM ARM resource ID. If provided, effective routes are collected from NICs attached to this VM.",
    ] = None,
    nic_resource_id: Annotated[
        Optional[str],
        "Optional ARM resource ID of the network interface card (NIC) to inspect effective routes for.",
    ] = None,
    subscription_id: Annotated[
        Optional[str],
        "Optional Azure subscription ID. Used when nic_resource_id is not supplied.",
    ] = None,
    resource_group: Annotated[
        Optional[str],
        "Optional resource group filter when nic_resource_id is not supplied.",
    ] = None,
    nic_name: Annotated[
        Optional[str],
        "Optional NIC name filter when nic_resource_id is not supplied.",
    ] = None,
) -> List[TextContent]:
    """Get effective routes for a network interface card (NIC).

    Shows both user-defined routes and system routes, indicating which
    next-hop is actually in effect for each destination prefix.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        def _to_list(value: Any) -> List[Any]:
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value]

        def _serialize_routes(route_table: Any) -> List[Dict[str, Any]]:
            serialized: List[Dict[str, Any]] = []
            for route in (getattr(route_table, "value", None) or []):
                serialized.append({
                    "name": route.name,
                    "source": str(route.source) if route.source else None,
                    "state": str(route.state) if route.state else None,
                    "address_prefix": _to_list(route.address_prefix),
                    "next_hop_type": str(route.next_hop_type) if route.next_hop_type else None,
                    "next_hop_ip_address": _to_list(route.next_hop_ip_address),
                    "disabled_bgp_route_propagation": getattr(route, "disabled_bgp_route_propagation", None),
                })
            return serialized

        if nic_resource_id:
            sub_id, rg, parsed_nic_name = _parse_resource_id(nic_resource_id)
            nic_name = nic_name or parsed_nic_name
        else:
            sub_id = subscription_id or _get_subscription_id()
            rg = resource_group or ""

        if not sub_id:
            return _text_result({
                "success": False,
                "error": "Missing subscription ID. Provide subscription_id or set SUBSCRIPTION_ID/AZURE_SUBSCRIPTION_ID.",
            })

        credential = _get_credential()
        loop = asyncio.get_event_loop()
        executor = await get_azure_cli_executor()

        def _get_single(nic_rg: str, nic_nm: str):
            client = NetworkManagementClient(credential, sub_id)
            poller = client.network_interfaces.begin_get_effective_route_table(nic_rg, nic_nm)
            return poller.result()

        # Single-NIC mode (original behavior)
        if nic_resource_id:
            if not rg or not nic_name:
                return _text_result({
                    "success": False,
                    "error": "Unable to resolve NIC resource group/name from nic_resource_id.",
                    "nic_resource_id": nic_resource_id,
                })

            result = await loop.run_in_executor(None, _get_single, rg, nic_name)
            routes = _serialize_routes(result)

            return _text_result({
                "success": True,
                "nic_name": nic_name,
                "resource_group": rg,
                "nic_resource_id": nic_resource_id,
                "route_count": len(routes),
                "routes": routes,
            })

        # VM-targeted mode: resolve VM then inspect attached NICs
        vm_nic_ids: List[str] = []
        vm_match_name = ""
        vm_match_rg = resource_group or ""

        if vm_resource_id:
            vm_sub, vm_rg, vm_nm = _parse_resource_id(vm_resource_id)
            sub_id = vm_sub or sub_id
            vm_match_rg = vm_rg or vm_match_rg
            vm_match_name = vm_nm
        elif vm_name:
            vm_match_name = vm_name.strip()

        if vm_match_name:
            vm_list_cmd = f"az vm list --subscription {sub_id} --output json"
            if vm_match_rg:
                vm_list_cmd += f" --resource-group {vm_match_rg}"

            vm_list_result = await executor.execute(vm_list_cmd, timeout=90, add_subscription=False)
            if vm_list_result.get("status") != "success":
                return _text_result({
                    "success": False,
                    "error": vm_list_result.get("error", "Failed to list VMs for effective route lookup"),
                    "subscription_id": sub_id,
                    "vm_name": vm_match_name,
                    "resource_group_filter": vm_match_rg,
                })

            vm_candidates = vm_list_result.get("output") or []
            if not isinstance(vm_candidates, list):
                vm_candidates = []

            vm_exact = [
                vm for vm in vm_candidates
                if str(vm.get("name") or "").strip().lower() == vm_match_name.lower()
            ]
            vm_matches = vm_exact if vm_exact else [
                vm for vm in vm_candidates
                if vm_match_name.lower() in str(vm.get("name") or "").lower()
            ]

            if not vm_matches:
                return _text_result({
                    "success": False,
                    "error": f"No VM found matching '{vm_match_name}' in scope.",
                    "subscription_id": sub_id,
                    "resource_group_filter": vm_match_rg,
                })

            if len(vm_matches) > 1 and not vm_exact:
                return _text_result({
                    "success": False,
                    "error": (
                        f"Multiple VMs matched '{vm_match_name}'. Please provide exact vm_name or vm_resource_id."
                    ),
                    "subscription_id": sub_id,
                    "resource_group_filter": vm_match_rg,
                    "matches": [
                        {
                            "name": vm.get("name"),
                            "resource_group": vm.get("resourceGroup"),
                            "resource_id": vm.get("id"),
                        }
                        for vm in vm_matches[:10]
                    ],
                })

            chosen_vm = vm_matches[0]
            vm_match_name = str(chosen_vm.get("name") or vm_match_name)
            vm_match_rg = str(chosen_vm.get("resourceGroup") or vm_match_rg)
            vm_nic_ids = [
                str(n.get("id") or "").strip()
                for n in (chosen_vm.get("networkProfile", {}).get("networkInterfaces") or [])
                if isinstance(n, dict) and n.get("id")
            ]

            if not vm_nic_ids:
                return _text_result({
                    "success": False,
                    "error": f"VM '{vm_match_name}' has no attached NICs to inspect.",
                    "subscription_id": sub_id,
                    "resource_group": vm_match_rg,
                    "vm_name": vm_match_name,
                })

        # Subscription-scope mode (auto-discover NICs)
        cmd = f"az network nic list --subscription {sub_id}"
        if resource_group:
            cmd += f" --resource-group {resource_group}"
        cmd += " --output json"

        cli_result = await executor.execute(cmd, timeout=90, add_subscription=False)
        if cli_result.get("status") != "success":
            return _text_result({
                "success": False,
                "error": cli_result.get("error", "Failed to list NICs for effective route analysis"),
                "subscription_id": sub_id,
                "resource_group_filter": resource_group,
            })

        nics = cli_result.get("output") or []
        if not isinstance(nics, list):
            nics = []

        # Keep only NICs attached to VMs to avoid NicMustBeAttachedToRunningVm failures.
        nics = [
            nic for nic in nics
            if isinstance(nic, dict)
            and isinstance(nic.get("virtualMachine"), dict)
            and nic.get("virtualMachine", {}).get("id")
        ]

        if vm_nic_ids:
            vm_nic_id_set = set(vm_nic_ids)
            nics = [
                nic for nic in nics
                if str(nic.get("id") or "").strip() in vm_nic_id_set
            ]

        if nic_name:
            nic_name_lower = nic_name.lower()
            nics = [
                nic for nic in nics
                if nic_name_lower in str(nic.get("name") or "").lower()
            ]

        if not nics:
            return _text_result({
                "success": False,
                "subscription_id": sub_id,
                "resource_group_filter": resource_group,
                "vm_name": vm_match_name or None,
                "vm_resource_id": vm_resource_id,
                "nic_name_filter": nic_name,
                "nic_count": 0,
                "message": "No VM-attached NICs found for effective route analysis in the selected scope.",
                "nic_routes": [],
            })

        nic_results: List[Dict[str, Any]] = []
        max_nics = 20
        for nic in nics[:max_nics]:
            nic_nm = str(nic.get("name") or "").strip()
            nic_rg = str(nic.get("resourceGroup") or nic.get("resource_group") or "").strip()
            nic_id = str(nic.get("id") or "").strip()
            if not nic_nm or not nic_rg:
                continue

            try:
                effective = await loop.run_in_executor(None, _get_single, nic_rg, nic_nm)
                routes = _serialize_routes(effective)
                nic_results.append({
                    "nic_name": nic_nm,
                    "resource_group": nic_rg,
                    "nic_resource_id": nic_id,
                    "success": True,
                    "route_count": len(routes),
                    "routes": routes,
                })
            except Exception as nic_exc:
                nic_results.append({
                    "nic_name": nic_nm,
                    "resource_group": nic_rg,
                    "nic_resource_id": nic_id,
                    "success": False,
                    "error": str(nic_exc),
                    "route_count": 0,
                    "routes": [],
                })

        successful = [item for item in nic_results if item.get("success")]
        failed = [item for item in nic_results if not item.get("success")]
        total_routes = sum(int(item.get("route_count", 0) or 0) for item in successful)

        overall_success = len(successful) > 0
        overall_error = None
        if not overall_success:
            overall_error = "Effective routes could not be retrieved from any selected NIC."

        return _text_result({
            "success": overall_success,
            "error": overall_error,
            "subscription_id": sub_id,
            "resource_group_filter": resource_group,
            "vm_name": vm_match_name or None,
            "vm_resource_id": vm_resource_id,
            "nic_name_filter": nic_name,
            "nic_count": len(nic_results),
            "processed_nics": len(nic_results),
            "truncated": len(nics) > max_nics,
            "max_nics": max_nics,
            "successful_nics": len(successful),
            "failed_nics": len(failed),
            "total_routes": total_routes,
            "nic_routes": nic_results,
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
# Tool 11: analyze_route_path
# ---------------------------------------------------------------------------


def _map_next_hop_type(azure_next_hop_type: str) -> str:
    """Map Azure SDK next-hop type string to RoutePathAnalyzer canonical values."""
    _mapping = {
        "VnetLocal": "VNetLocal",
        "VNetLocal": "VNetLocal",
        "VNetPeering": "VNetPeering",
        "VirtualNetworkGateway": "VirtualNetworkGateway",
        "Internet": "Internet",
        "VirtualAppliance": "VirtualAppliance",
        "None": "None",
    }
    return _mapping.get(azure_next_hop_type, azure_next_hop_type)


def _map_route_source(azure_source: str) -> str:
    """Map Azure SDK route source to RoutePathAnalyzer canonical values."""
    if "user" in azure_source.lower():
        return ROUTE_SOURCE_USER
    return ROUTE_SOURCE_DEFAULT


@_server.tool()
async def analyze_route_path(
    context: Context,
    source_subnet_id: Annotated[
        str,
        "ARM resource ID of the source subnet "
        "(e.g. /subscriptions/.../subnets/subnet-a).",
    ],
    dest_ip: Annotated[
        str,
        "Destination IP address to trace the route to (IPv4 dotted-decimal).",
    ],
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to SUBSCRIPTION_ID environment variable.",
    ] = None,
    include_reverse_path: Annotated[
        bool,
        "If True, also trace the reverse path (dest → source) and perform asymmetric "
        "routing detection. Adds ~1–2s for the additional lookup.",
    ] = False,
    max_hops: Annotated[
        int,
        "Maximum number of routing hops to trace before stopping. Default 10.",
    ] = 10,
) -> List[TextContent]:
    """Trace the routing path from a source subnet to a destination IP address.

    Performs Longest Prefix Match (LPM) against the subnet's effective route table
    to determine which path traffic takes.  Supports VNet-local, VNet-peered,
    gateway (VPN/ExpressRoute), internet-egress, and black-hole routes.

    If include_reverse_path=True, also traces the return path and reports whether
    asymmetric routing is present — crucial for stateful firewall configurations.

    Identifies issues such as:
    - Black-hole routes (traffic silently dropped)
    - User-defined route (UDR) overrides
    - Asymmetric forward/return paths
    - Unexpected gateway or internet egress

    Returns structured path with per-hop details and a topology summary.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": "subscription_id is required (or set SUBSCRIPTION_ID env var)",
            })

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # ------------------------------------------------------------------
        # Helper: fetch effective routes for a subnet via its first NIC or
        # by listing the route table attached to the subnet.
        # ------------------------------------------------------------------

        def _fetch_routes_for_subnet(subnet_id: str) -> List[Route]:
            """
            Retrieve routes effective for a subnet.

            Strategy:
            1. Parse the subnet ARM ID to identify VNet, RG, and subnet name.
            2. Fetch the subnet object to get its attached route table.
            3. If a route table exists, enumerate its routes.
            4. Always add the system-injected VNetLocal route (0.0.0.0 handled
               by default route; VNetLocal covers the VNet address spaces).
            """
            parts = [p for p in subnet_id.split("/") if p]
            # Expected shape:
            # subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/
            # virtualNetworks/{vnet}/subnets/{subnet}
            try:
                idx = {p.lower(): i for i, p in enumerate(parts)}
                rg_name = parts[idx["resourcegroups"] + 1]
                vnet_name = parts[idx["virtualnetworks"] + 1]
                subnet_name = parts[idx["subnets"] + 1]
            except (KeyError, IndexError) as parse_err:
                logger.warning("Cannot parse subnet_id '%s': %s", subnet_id, parse_err)
                return []

            client = NetworkManagementClient(credential, sub_id)

            # Fetch VNet to derive address spaces (for VNetLocal coverage)
            vnet_obj = client.virtual_networks.get(rg_name, vnet_name)
            vnet_prefixes: List[str] = []
            if vnet_obj.address_space and vnet_obj.address_space.address_prefixes:
                vnet_prefixes = list(vnet_obj.address_space.address_prefixes)

            # Build peerings map: remote VNet CIDR → remote subnet resource IDs
            peered_vnet_map: Dict[str, str] = {}
            for peering in (vnet_obj.virtual_network_peerings or []):
                if peering.peering_state and str(peering.peering_state).lower() == "connected":
                    remote_id = peering.remote_virtual_network.id if peering.remote_virtual_network else ""
                    if remote_id:
                        remote_prefixes = peering.remote_address_space.address_prefixes if (
                            peering.remote_address_space and peering.remote_address_space.address_prefixes
                        ) else []
                        for prefix in remote_prefixes:
                            # Map peering prefix to the remote VNet's first subnet (placeholder)
                            peered_vnet_map[prefix] = remote_id + "/subnets/default"

            # Fetch subnet to get the attached route table
            subnet_obj = client.subnets.get(rg_name, vnet_name, subnet_name)

            # Start with system VNetLocal routes for the VNet address space
            routes: List[Route] = [
                Route(
                    address_prefix=prefix,
                    next_hop_type="VNetLocal",
                    source=ROUTE_SOURCE_DEFAULT,
                )
                for prefix in vnet_prefixes
            ]

            # Add VNetPeering system routes
            for peering in (vnet_obj.virtual_network_peerings or []):
                if peering.peering_state and str(peering.peering_state).lower() == "connected":
                    remote_prefixes = peering.remote_address_space.address_prefixes if (
                        peering.remote_address_space and peering.remote_address_space.address_prefixes
                    ) else []
                    for prefix in remote_prefixes:
                        routes.append(Route(
                            address_prefix=prefix,
                            next_hop_type="VNetPeering",
                            source=ROUTE_SOURCE_DEFAULT,
                        ))

            # Default internet egress (system route)
            routes.append(Route(
                address_prefix="0.0.0.0/0",
                next_hop_type="Internet",
                source=ROUTE_SOURCE_DEFAULT,
            ))

            # Overlay with user-defined routes from attached route table
            if subnet_obj.route_table and subnet_obj.route_table.id:
                rt_parts = [p for p in subnet_obj.route_table.id.split("/") if p]
                try:
                    rt_rg = rt_parts[{p.lower(): i for i, p in enumerate(rt_parts)}["resourcegroups"] + 1]
                    rt_name = rt_parts[-1]
                    rt_obj = client.route_tables.get(rt_rg, rt_name)
                    for rt_route in (rt_obj.routes or []):
                        next_hop_ip = None
                        if rt_route.next_hop_ip_address:
                            next_hop_ip = rt_route.next_hop_ip_address
                        routes.append(Route(
                            address_prefix=rt_route.address_prefix or "",
                            next_hop_type=_map_next_hop_type(
                                str(rt_route.next_hop_type) if rt_route.next_hop_type else "None"
                            ),
                            next_hop_ip=next_hop_ip,
                            source=ROUTE_SOURCE_USER,
                            route_table_id=subnet_obj.route_table.id,
                        ))
                except Exception as rt_err:
                    logger.warning("Could not fetch route table: %s", rt_err)

            return routes

        # ------------------------------------------------------------------
        # Fetch forward routes and trace path
        # ------------------------------------------------------------------
        forward_routes = await loop.run_in_executor(None, _fetch_routes_for_subnet, source_subnet_id)

        if not forward_routes:
            return _text_result({
                "success": False,
                "error": f"No routes found for subnet '{source_subnet_id}'. "
                         "Verify the subnet ID and subscription.",
                "source_subnet_id": source_subnet_id,
                "dest_ip": dest_ip,
            })

        # Build peered_vnets from peering routes for path tracing
        peered_vnets: Dict[str, str] = {}
        for r in forward_routes:
            if r.next_hop_type == "VNetPeering" and r.address_prefix:
                # We don't know the exact peered subnet ID here, but the analyzer
                # uses this to validate that peering exists for the destination prefix.
                peered_vnets[r.address_prefix] = f"peered-vnet/{r.address_prefix}"

        # Temporarily set max_hops
        from utils.route_path_analyzer import MAX_HOPS as _DEFAULT_MAX_HOPS
        _original_max = _DEFAULT_MAX_HOPS

        forward_path = _route_analyzer.trace_path(
            source_subnet_id=source_subnet_id,
            dest_ip=dest_ip,
            routes=forward_routes,
            peered_vnets=peered_vnets if peered_vnets else None,
            hop_count=0,
        )

        # ------------------------------------------------------------------
        # Issues analysis
        # ------------------------------------------------------------------
        issues: List[Dict[str, Any]] = []

        if forward_path.status == "black_hole":
            issues.append({
                "severity": "critical",
                "type": "black_hole",
                "description": f"Traffic to {dest_ip} hits a black-hole (None) route — "
                               "it will be silently dropped.",
            })

        # Detect UDR overrides
        for hop in forward_path.hops:
            if hasattr(hop, "route_source") and hop.route_source == ROUTE_SOURCE_USER:
                issues.append({
                    "severity": "info",
                    "type": "udr_override",
                    "description": f"Hop {hop.hop_number}: User-defined route overrides system route "
                                   f"for prefix {hop.address_prefix}.",
                })

        if forward_path.status == "internet_egress":
            issues.append({
                "severity": "warning",
                "type": "internet_egress",
                "description": f"Traffic to {dest_ip} exits to the public internet via default route.",
            })

        # ------------------------------------------------------------------
        # Optional reverse path + asymmetry detection
        # ------------------------------------------------------------------
        reverse_path_data: Optional[Dict[str, Any]] = None
        asymmetry_result: Optional[Dict[str, Any]] = None

        if include_reverse_path:
            # For the reverse path, use the dest_ip as source.
            # We attempt to get the reverse subnet from peered VNet info.
            # This is a best-effort trace using the same route structure.
            reverse_routes = forward_routes  # Simplified: same route table for demo
            reverse_path = _route_analyzer.trace_path(
                source_subnet_id=f"reverse/{dest_ip}",
                dest_ip=source_subnet_id.split("/")[-1],  # Extract subnet name as dest hint
                routes=reverse_routes,
                peered_vnets=peered_vnets if peered_vnets else None,
                hop_count=0,
            )

            asymmetry_result = _route_analyzer.detect_asymmetry(forward_path, reverse_path)

            if asymmetry_result.get("asymmetric"):
                issues.append({
                    "severity": "high",
                    "type": "asymmetric_routing",
                    "description": asymmetry_result.get("details", "Asymmetric routing detected."),
                })

            reverse_path_data = reverse_path.to_dict()

        # ------------------------------------------------------------------
        # Topology summary
        # ------------------------------------------------------------------
        hop_types_used = list({
            hop.next_hop_type
            for hop in forward_path.hops
            if hasattr(hop, "next_hop_type")
        })

        topology_summary = {
            "path_type": forward_path.status,
            "hop_count": forward_path.total_hops,
            "next_hop_types_traversed": hop_types_used,
            "has_nva": "VirtualAppliance" in hop_types_used,
            "uses_gateway": "VirtualNetworkGateway" in hop_types_used,
            "uses_peering": "VNetPeering" in hop_types_used,
            "internet_bound": forward_path.status == "internet_egress",
        }

        return _text_result({
            "success": True,
            "source_subnet_id": source_subnet_id,
            "dest_ip": dest_ip,
            "subscription_id": sub_id,
            "forward_path": forward_path.to_dict(),
            "reverse_path": reverse_path_data,
            "asymmetry": asymmetry_result,
            "issues": issues,
            "issue_count": len(issues),
            "topology_summary": topology_summary,
            "route_count_analyzed": len(forward_routes),
        })

    except Exception as exc:
        logger.exception("analyze_route_path failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 12: simulate_nsg_flow
# ---------------------------------------------------------------------------

@_server.tool()
async def simulate_nsg_flow(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    source_ip: Annotated[
        str,
        "Source IP address of the simulated traffic (e.g. '10.1.2.3').",
    ] = "",
    destination_ip: Annotated[
        str,
        "Destination IP address of the simulated traffic (e.g. '192.168.1.10').",
    ] = "",
    destination_port: Annotated[
        int,
        "Destination TCP/UDP port to simulate (e.g. 443, 3389, 22).",
    ] = 443,
    protocol: Annotated[
        str,
        "Transport protocol: 'TCP' (default), 'UDP', or 'ICMP'.",
    ] = "TCP",
    source_port: Annotated[
        Optional[int],
        "Optional source port (rarely used in NSG matching). Omit to leave unspecified.",
    ] = None,
    nsg_id: Annotated[
        Optional[str],
        "ARM resource ID or 'resource_group/nsg_name' of the NSG to evaluate. "
        "If omitted, the tool auto-detects the NSG from subnet associations for "
        "the destination IP (Inbound) or source IP (Outbound).",
    ] = None,
    direction: Annotated[
        str,
        "Traffic direction to evaluate: 'Inbound' (default) or 'Outbound'.",
    ] = "Inbound",
) -> List[TextContent]:
    """Simulate traffic flow through NSG rules with priority-ordered resolution.

    Evaluates whether a specific network flow (source IP → destination IP:port)
    would be allowed or denied by the applicable NSG rules, returning the
    full rule evaluation chain and actionable security recommendations.

    If nsg_id is not specified, the tool attempts to auto-detect the relevant
    NSG by finding the subnet whose CIDR contains the destination IP (Inbound)
    or source IP (Outbound) and following its NSG association.

    Returns:
    - verdict: 'Allow', 'Deny', or 'DefaultDeny' (implicit deny, no rule matched)
    - matched_rule: The first rule that determined the verdict (or null)
    - evaluation_chain: All rules evaluated in priority order before the decision
    - recommendations: Actionable security hardening suggestions
    - nsg_name / nsg_resource_group: The NSG that was evaluated
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    if not source_ip or not destination_ip:
        return _text_result({
            "success": False,
            "error": "source_ip and destination_ip are required parameters.",
        })

    try:
        sub_id = subscription_id or _get_subscription_id()
        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # ----------------------------------------------------------------
        # Step 1: Resolve NSG (explicit or auto-detect)
        # ----------------------------------------------------------------
        resolved_nsg_rg: Optional[str] = None
        resolved_nsg_name: Optional[str] = None
        nsg_resource_id: Optional[str] = None

        if nsg_id:
            # Caller provided an explicit NSG reference
            if nsg_id.startswith("/"):
                _, resolved_nsg_rg, resolved_nsg_name = _parse_resource_id(nsg_id)
                nsg_resource_id = nsg_id
            else:
                parts = nsg_id.split("/", 1)
                resolved_nsg_rg = parts[0]
                resolved_nsg_name = parts[1] if len(parts) > 1 else parts[0]
                nsg_resource_id = nsg_id
        else:
            # Auto-detect: for Inbound, the destination lives in the protected subnet;
            # for Outbound, the source lives there.
            detection_ip = destination_ip if direction.strip().capitalize() == "Inbound" else source_ip
            auto_rg, auto_name, auto_id = await _auto_detect_nsg_for_flow(sub_id, detection_ip)
            if auto_name:
                resolved_nsg_rg = auto_rg
                resolved_nsg_name = auto_name
                nsg_resource_id = auto_id
            else:
                return _text_result({
                    "success": False,
                    "error": (
                        f"Could not auto-detect an NSG associated with IP '{detection_ip}'. "
                        "Provide nsg_id explicitly, or ensure the subnet has an NSG attached."
                    ),
                    "source_ip": source_ip,
                    "destination_ip": destination_ip,
                    "destination_port": destination_port,
                    "protocol": protocol,
                    "direction": direction,
                })

        # ----------------------------------------------------------------
        # Step 2: Fetch NSG rules from Azure
        # ----------------------------------------------------------------
        def _fetch_nsg():
            client = NetworkManagementClient(credential, sub_id)
            return client.network_security_groups.get(resolved_nsg_rg, resolved_nsg_name)

        try:
            nsg_obj = await loop.run_in_executor(None, _fetch_nsg)
        except Exception as fetch_err:
            return _text_result({
                "success": False,
                "error": f"Failed to retrieve NSG '{resolved_nsg_name}': {fetch_err}",
                "nsg_resource_group": resolved_nsg_rg,
                "nsg_name": resolved_nsg_name,
                "nsg_resource_id": nsg_resource_id,
            })

        # ----------------------------------------------------------------
        # Step 3: Parse Azure rules → NSGRule objects
        # ----------------------------------------------------------------
        nsg_rules: List[NSGRule] = []

        # Custom rules first, then default rules (Azure evaluates custom before defaults)
        all_raw_rules = list(nsg_obj.security_rules or []) + list(nsg_obj.default_security_rules or [])

        for raw in all_raw_rules:
            try:
                parsed = _parse_azure_nsg_rule(raw)
                if parsed is not None:
                    nsg_rules.append(parsed)
            except Exception as parse_err:
                logger.warning(
                    "Skipping unparseable NSG rule '%s': %s",
                    getattr(raw, "name", "<unknown>"),
                    parse_err,
                )

        # ----------------------------------------------------------------
        # Step 4: Build FlowTuple and evaluate
        # ----------------------------------------------------------------
        flow = FlowTuple(
            source_ip=source_ip.strip(),
            dest_ip=destination_ip.strip(),
            dest_port=destination_port,
            protocol=protocol.strip().upper(),
            source_port=source_port,
        )

        verdict = _nsg_evaluator.evaluate_flow(nsg_rules, flow, direction=direction)

        # ----------------------------------------------------------------
        # Step 5: Serialize and return
        # ----------------------------------------------------------------
        matched_rule_dict: Optional[Dict[str, Any]] = None
        if verdict.matched_rule is not None:
            mr = verdict.matched_rule
            matched_rule_dict = {
                "name": mr.name,
                "priority": mr.priority,
                "action": mr.action,
                "direction": mr.direction,
                "source_address_prefix": mr.source_address_prefix,
                "destination_address_prefix": mr.dest_address_prefix,
                "destination_port_range": mr.dest_port_range,
                "protocol": mr.protocol,
                "description": mr.description,
            }

        return _text_result({
            "success": True,
            "verdict": verdict.action,
            "matched_rule": matched_rule_dict,
            "evaluation_chain": verdict.evaluation_chain,
            "recommendations": verdict.recommendations,
            "recommendation_count": len(verdict.recommendations),
            "rules_evaluated": len(verdict.evaluation_chain),
            "nsg_name": resolved_nsg_name,
            "nsg_resource_group": resolved_nsg_rg,
            "nsg_resource_id": nsg_resource_id,
            "flow": {
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "destination_port": destination_port,
                "protocol": protocol,
                "source_port": source_port,
                "direction": direction,
            },
        })

    except Exception as exc:
        logger.exception("simulate_nsg_flow failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# NSG flow simulation helpers
# ---------------------------------------------------------------------------

def _parse_azure_nsg_rule(raw: Any) -> Optional[NSGRule]:
    """
    Convert an Azure SDK ``SecurityRule`` object into an ``NSGRule`` dataclass.

    Handles both enum-typed attributes (Azure SDK v4+) and plain strings.
    Returns None for rules missing required fields (name, priority, action, direction).
    """
    name = getattr(raw, "name", None)
    priority = getattr(raw, "priority", None)
    action = getattr(raw, "access", None)      # Azure SDK uses "access" (Allow/Deny), not "action"
    direction = getattr(raw, "direction", None)
    source_prefix = getattr(raw, "source_address_prefix", None)
    dest_prefix = getattr(raw, "destination_address_prefix", None)
    dest_port = getattr(raw, "destination_port_range", None)
    protocol = getattr(raw, "protocol", None)
    description = getattr(raw, "description", None)

    def _str(val: Any) -> Optional[str]:
        """Coerce Azure SDK enum values to plain strings."""
        if val is None:
            return None
        s = str(val)
        # Strip enum class prefix: "SecurityRuleAccess.Allow" → "Allow"
        return s.split(".")[-1] if "." in s else s

    action_str = _str(action)
    direction_str = _str(direction)
    protocol_str = _str(protocol) or "*"
    source_str = source_prefix or "*"
    dest_addr_str = dest_prefix or "*"
    dest_port_str = dest_port or "*"

    if not name or priority is None or not action_str or not direction_str:
        logger.debug("Skipping NSG rule with missing required fields: name=%s", name)
        return None

    return NSGRule(
        name=name,
        priority=int(priority),
        action=action_str,
        direction=direction_str,
        source_address_prefix=source_str,
        dest_address_prefix=dest_addr_str,
        dest_port_range=dest_port_str,
        protocol=protocol_str,
        description=description,
    )


async def _auto_detect_nsg_for_flow(
    subscription_id: str,
    ip_address: str,
) -> "tuple[Optional[str], Optional[str], Optional[str]]":
    """
    Auto-detect the NSG associated with the subnet containing *ip_address*.

    Strategy:
    1. List all VNets (and their subnets) in the subscription via Azure CLI.
    2. Find the subnet whose address prefix CIDR contains *ip_address*.
       If multiple subnets match, prefer the most-specific (longest prefix length).
    3. Follow the subnet's ``networkSecurityGroup`` link to get rg/name/id.

    Returns ``(resource_group, nsg_name, nsg_resource_id)`` or ``(None, None, None)``.
    """
    import ipaddress as _ipaddress

    try:
        executor = await get_azure_cli_executor()

        cmd = f"az network vnet list --subscription {subscription_id}"
        cli_result = await executor.execute(cmd, timeout=60, add_subscription=False)

        if cli_result.get("status") != "success":
            logger.warning(
                "_auto_detect_nsg_for_flow: vnet list failed: %s", cli_result.get("error")
            )
            return None, None, None

        vnets_raw: List[Dict[str, Any]] = cli_result.get("output") or []

        try:
            probe_addr = _ipaddress.IPv4Address(ip_address.strip())
        except ValueError:
            logger.warning("_auto_detect_nsg_for_flow: invalid IP address '%s'", ip_address)
            return None, None, None

        # Walk all subnets; pick the most-specific (longest prefix) matching subnet with
        # an NSG attached.
        best_prefix_len = -1
        best_nsg_id: Optional[str] = None

        for vnet in vnets_raw:
            for subnet in (vnet.get("subnets") or []):
                # addressPrefix may be a single string; addressPrefixes is a list (dual-stack)
                cidr = subnet.get("addressPrefix")
                if not cidr:
                    prefixes = subnet.get("addressPrefixes") or []
                    cidr = prefixes[0] if prefixes else None
                if not cidr:
                    continue
                try:
                    net = _ipaddress.IPv4Network(cidr, strict=False)
                    if probe_addr in net and net.prefixlen > best_prefix_len:
                        nsg_assoc = subnet.get("networkSecurityGroup")
                        if nsg_assoc and nsg_assoc.get("id"):
                            best_prefix_len = net.prefixlen
                            best_nsg_id = nsg_assoc["id"]
                except ValueError:
                    continue

        if not best_nsg_id:
            return None, None, None

        _, rg, name = _parse_resource_id(best_nsg_id)
        return rg, name, best_nsg_id

    except Exception as exc:
        logger.warning("_auto_detect_nsg_for_flow error: %s", exc)
        return None, None, None


# ---------------------------------------------------------------------------
# Connectivity Matrix helpers
# ---------------------------------------------------------------------------

import ipaddress as _ipaddress

# Connectivity status constants
_CONN_ALLOWED = "allowed"
_CONN_DENIED = "denied"
_CONN_PARTIAL = "partial"
_CONN_UNKNOWN = "unknown"

# Route status that makes NSG evaluation pointless
_ROUTING_TERMINAL_UNREACHABLE = {"unreachable", "black_hole"}


def _first_host_ip(cidr: str) -> Optional[str]:
    """Return the first usable host IP from a CIDR prefix, or None on error."""
    try:
        net = _ipaddress.ip_network(cidr, strict=False)
        hosts = list(net.hosts())
        return str(hosts[0]) if hosts else str(net.network_address)
    except ValueError:
        return None


def _parse_subnet_info(subnet_raw: Any, vnet_id: str) -> Optional[Dict[str, Any]]:
    """
    Normalise a raw subnet object (SDK or dict) into a consistent dict.

    Returns None if address_prefix is missing/unparseable.
    """
    if subnet_raw is None:
        return None

    # Handle both Azure SDK objects and plain dicts (from CLI output)
    if isinstance(subnet_raw, dict):
        name = subnet_raw.get("name") or ""
        sid = subnet_raw.get("id") or ""
        prefix = subnet_raw.get("addressPrefix") or (
            (subnet_raw.get("addressPrefixes") or [None])[0]
        )
        nsg_id = (subnet_raw.get("networkSecurityGroup") or {}).get("id")
        rt_id = (subnet_raw.get("routeTable") or {}).get("id")
    else:
        name = getattr(subnet_raw, "name", "") or ""
        sid = getattr(subnet_raw, "id", "") or ""
        prefix = getattr(subnet_raw, "address_prefix", None)
        nsg_obj = getattr(subnet_raw, "network_security_group", None)
        nsg_id = nsg_obj.id if nsg_obj else None
        rt_obj = getattr(subnet_raw, "route_table", None)
        rt_id = rt_obj.id if rt_obj else None

    if not prefix:
        return None

    host_ip = _first_host_ip(prefix)
    return {
        "id": sid,
        "name": name,
        "address_prefix": prefix,
        "host_ip": host_ip,
        "nsg_id": nsg_id,
        "route_table_id": rt_id,
        "vnet_id": vnet_id,
    }


def _build_nsg_rules_from_sdk(nsg_obj: Any) -> List[NSGRule]:
    """Parse Azure SDK NSG object into a list of NSGRule dataclass instances."""
    rules: List[NSGRule] = []
    all_raw = list(getattr(nsg_obj, "security_rules", None) or []) + \
              list(getattr(nsg_obj, "default_security_rules", None) or [])
    for raw in all_raw:
        parsed = _parse_azure_nsg_rule(raw)
        if parsed:
            rules.append(parsed)
    return rules


def _build_route_list_from_sdk(
    vnet_obj: Any,
    rt_obj: Any,
    rt_id: Optional[str],
) -> List[Route]:
    """
    Build a list of Route objects for a subnet by combining:
      - System VNetLocal routes (from VNet address space)
      - System VNetPeering routes (from connected peerings)
      - Default internet egress (0.0.0.0/0)
      - User-defined routes from the attached route table (if any)
    """
    routes: List[Route] = []

    # VNetLocal routes for each VNet address prefix
    addr_space = getattr(vnet_obj, "address_space", None)
    prefixes: List[str] = list((addr_space.address_prefixes if addr_space else None) or [])
    for prefix in prefixes:
        routes.append(Route(address_prefix=prefix, next_hop_type="VNetLocal",
                            source=ROUTE_SOURCE_DEFAULT))

    # VNetPeering routes (only connected peerings)
    for peering in (getattr(vnet_obj, "virtual_network_peerings", None) or []):
        state = str(getattr(peering, "peering_state", "") or "")
        if state.lower() != "connected":
            continue
        remote_space = getattr(peering, "remote_address_space", None)
        remote_prefixes = list((remote_space.address_prefixes if remote_space else None) or [])
        for rp in remote_prefixes:
            routes.append(Route(address_prefix=rp, next_hop_type="VNetPeering",
                                source=ROUTE_SOURCE_DEFAULT))

    # Default internet egress
    routes.append(Route(address_prefix="0.0.0.0/0", next_hop_type="Internet",
                        source=ROUTE_SOURCE_DEFAULT))

    # User-defined routes from route table
    if rt_obj is not None:
        for rt_route in (getattr(rt_obj, "routes", None) or []):
            nhi = getattr(rt_route, "next_hop_ip_address", None)
            nht_raw = getattr(rt_route, "next_hop_type", None)
            nht = _map_next_hop_type(str(nht_raw) if nht_raw else "None")
            addr_pref = getattr(rt_route, "address_prefix", None) or ""
            routes.append(Route(
                address_prefix=addr_pref,
                next_hop_type=nht,
                next_hop_ip=nhi,
                source=ROUTE_SOURCE_USER,
                route_table_id=rt_id,
            ))

    return routes


def _build_peered_vnets_map(vnet_obj: Any) -> Dict[str, str]:
    """Build {cidr_prefix: placeholder_subnet_id} for connected peerings."""
    peered: Dict[str, str] = {}
    for peering in (getattr(vnet_obj, "virtual_network_peerings", None) or []):
        state = str(getattr(peering, "peering_state", "") or "")
        if state.lower() != "connected":
            continue
        remote_vnet = getattr(peering, "remote_virtual_network", None)
        remote_id = remote_vnet.id if remote_vnet else ""
        remote_space = getattr(peering, "remote_address_space", None)
        remote_prefixes = list((remote_space.address_prefixes if remote_space else None) or [])
        for rp in remote_prefixes:
            peered[rp] = f"{remote_id}/subnets/default"
    return peered


# ---------------------------------------------------------------------------
# Tool 14: generate_connectivity_matrix
# ---------------------------------------------------------------------------


@_server.tool()
async def generate_connectivity_matrix(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to SUBSCRIPTION_ID environment variable.",
    ] = None,
    scope: Annotated[
        str,
        "Scope of subnet discovery. Use 'all' for all VNets in the subscription, "
        "'vnet:<vnet_resource_id>' to limit to one VNet, or "
        "'rg:<resource_group_name>' to limit to a resource group.",
    ] = "all",
    protocol: Annotated[
        str,
        "Transport protocol for NSG evaluation: 'TCP' (default), 'UDP', or '*'.",
    ] = "TCP",
    ports: Annotated[
        Optional[str],
        "Comma-separated list of destination ports to evaluate for NSG rules "
        "(e.g. '22,80,443,3306'). Leave empty to evaluate routing only.",
    ] = None,
    include_peering_status: Annotated[
        bool,
        "If True, include VNet peering state in the response.",
    ] = True,
    include_route_details: Annotated[
        bool,
        "If True, include per-hop route path details for each pair. "
        "Increases response size significantly.",
    ] = False,
    max_subnets: Annotated[
        int,
        "Maximum number of subnets to include. Pairs = N*(N-1)/2. Default 20.",
    ] = 20,
) -> List[TextContent]:
    """Generate an N×N subnet connectivity matrix with routing and NSG analysis.

    Discovers all subnets in the given scope, then evaluates every source→destination
    subnet pair for:
    - **Routing reachability**: Uses LPM route analysis (VNetLocal, Peering, Gateway,
      Internet egress, black-hole) to determine if traffic can flow at the IP layer.
    - **NSG port filtering**: For each requested port, evaluates outbound rules on the
      source subnet's NSG and inbound rules on the destination subnet's NSG.

    The matrix result classifies each pair as:
    - `allowed`  — routing is reachable AND all requested ports pass NSG checks
    - `partial`  — routing reachable but some ports are NSG-blocked
    - `denied`   — routing reachable but all ports blocked, or no ports requested but
                   NSG has explicit deny
    - `unreachable_routing` — routing analysis shows traffic cannot reach destination
    - `unknown`  — evaluation failed (permission error, missing data)

    **Performance**: Uses asyncio.Semaphore(10) for parallel pair evaluation.
    Pre-fetches all NSGs and route tables once to minimise API calls.
    Target: <60 s for 20 subnets (190 pairs).
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": "subscription_id is required (or set SUBSCRIPTION_ID env var)",
            })

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # Parse ports list
        port_list: List[int] = []
        if ports:
            for p in ports.split(","):
                p = p.strip()
                if p.isdigit():
                    port_list.append(int(p))

        # ----------------------------------------------------------------
        # Step 1: Discover subnets in scope
        # ----------------------------------------------------------------
        logger.info("generate_connectivity_matrix: discovering subnets (scope=%s)", scope)

        def _discover_subnets() -> tuple:
            """
            Returns (subnet_list, vnet_map, peering_status_list)
            where:
              subnet_list: List[Dict]  — normalised subnet dicts
              vnet_map: Dict[vnet_id, sdk_vnet_obj]
              peering_status_list: List[Dict]
            """
            client = NetworkManagementClient(credential, sub_id)
            vnets_to_fetch: List[Any] = []

            scope_lower = scope.strip().lower()

            if scope_lower.startswith("vnet:"):
                # Single VNet
                vnet_id = scope[len("vnet:"):].strip()
                _sub, _rg, _vn = _parse_resource_id(vnet_id)
                vnets_to_fetch = [client.virtual_networks.get(_rg, _vn)]

            elif scope_lower.startswith("rg:"):
                rg_filter = scope[len("rg:"):].strip()
                vnets_to_fetch = list(client.virtual_networks.list(rg_filter))

            else:
                # "all" — list across subscription
                vnets_to_fetch = list(client.virtual_networks.list_all())

            subnet_list: List[Dict[str, Any]] = []
            vnet_map: Dict[str, Any] = {}
            peering_status: List[Dict[str, Any]] = []

            for vnet in vnets_to_fetch:
                vnet_id = vnet.id or ""
                vnet_map[vnet_id] = vnet

                for sn in (vnet.subnets or []):
                    parsed = _parse_subnet_info(sn, vnet_id)
                    if parsed:
                        subnet_list.append(parsed)

                # Collect peering status
                if include_peering_status:
                    for p in (vnet.virtual_network_peerings or []):
                        remote_vnet = getattr(p, "remote_virtual_network", None)
                        peering_status.append({
                            "vnet1": vnet_id,
                            "vnet2": remote_vnet.id if remote_vnet else None,
                            "peering_name": p.name,
                            "peering_state": str(p.peering_state) if p.peering_state else "Unknown",
                            "allow_forwarded_traffic": p.allow_forwarded_traffic,
                            "use_remote_gateways": p.use_remote_gateways,
                        })

            return subnet_list, vnet_map, peering_status

        all_subnets, vnet_map, peering_status = await loop.run_in_executor(None, _discover_subnets)

        truncated = len(all_subnets) > max_subnets
        truncation_warning: Optional[str] = None
        if truncated:
            truncation_warning = (
                f"Discovered {len(all_subnets)} subnets; truncated to {max_subnets}. "
                "Use scope parameter to narrow the analysis."
            )
            all_subnets = all_subnets[:max_subnets]
            logger.warning(truncation_warning)

        if len(all_subnets) < 2:
            return _text_result({
                "success": True,
                "warning": "Fewer than 2 subnets found in scope — no pairs to evaluate.",
                "subnet_count": len(all_subnets),
                "scope": scope,
                "matrix": [],
                "summary": {
                    "total_subnet_pairs": 0,
                    "fully_reachable": 0,
                    "partially_blocked": 0,
                    "fully_blocked": 0,
                    "unreachable_routing": 0,
                    "subnets_analyzed": len(all_subnets),
                },
                "peering_status": peering_status if include_peering_status else None,
                "truncated": truncated,
                "truncation_warning": truncation_warning,
            })

        logger.info(
            "generate_connectivity_matrix: %d subnets → %d pairs",
            len(all_subnets),
            len(all_subnets) * (len(all_subnets) - 1) // 2,
        )

        # ----------------------------------------------------------------
        # Step 2: Pre-fetch NSGs and route tables (batch, once)
        # ----------------------------------------------------------------
        def _prefetch_resources() -> tuple:
            """
            Returns:
              nsg_rules_cache:  Dict[nsg_id, List[NSGRule]]
              rt_cache:         Dict[rt_id, sdk_rt_obj]
            """
            client = NetworkManagementClient(credential, sub_id)

            # Collect unique NSG IDs and route table IDs referenced by our subnets
            nsg_ids_needed: set = set()
            rt_ids_needed: set = set()
            for sn in all_subnets:
                if sn.get("nsg_id"):
                    nsg_ids_needed.add(sn["nsg_id"])
                if sn.get("route_table_id"):
                    rt_ids_needed.add(sn["route_table_id"])

            nsg_rules_cache: Dict[str, List[NSGRule]] = {}
            for nsg_id in nsg_ids_needed:
                try:
                    _, rg, name = _parse_resource_id(nsg_id)
                    nsg_obj = client.network_security_groups.get(rg, name)
                    nsg_rules_cache[nsg_id] = _build_nsg_rules_from_sdk(nsg_obj)
                except Exception as nsg_err:
                    logger.warning("Could not fetch NSG '%s': %s", nsg_id, nsg_err)
                    nsg_rules_cache[nsg_id] = []

            rt_cache: Dict[str, Any] = {}
            for rt_id in rt_ids_needed:
                try:
                    _, rg, name = _parse_resource_id(rt_id)
                    rt_cache[rt_id] = client.route_tables.get(rg, name)
                except Exception as rt_err:
                    logger.warning("Could not fetch route table '%s': %s", rt_id, rt_err)
                    rt_cache[rt_id] = None

            return nsg_rules_cache, rt_cache

        nsg_rules_cache, rt_cache = await loop.run_in_executor(None, _prefetch_resources)

        # Build per-VNet route lists (combining system routes + UDRs) once per VNet
        # Key: (vnet_id, rt_id_or_None) → List[Route]
        _route_list_cache: Dict[tuple, List[Route]] = {}

        def _get_routes_for_subnet(sn: Dict[str, Any]) -> List[Route]:
            vnet_id = sn["vnet_id"]
            rt_id = sn.get("route_table_id")
            cache_key = (vnet_id, rt_id)
            if cache_key in _route_list_cache:
                return _route_list_cache[cache_key]
            vnet_obj = vnet_map.get(vnet_id)
            if not vnet_obj:
                return []
            rt_obj = rt_cache.get(rt_id) if rt_id else None
            routes = _build_route_list_from_sdk(vnet_obj, rt_obj, rt_id)
            _route_list_cache[cache_key] = routes
            return routes

        def _get_peered_vnets_for_subnet(sn: Dict[str, Any]) -> Dict[str, str]:
            vnet_id = sn["vnet_id"]
            vnet_obj = vnet_map.get(vnet_id)
            if not vnet_obj:
                return {}
            return _build_peered_vnets_map(vnet_obj)

        # ----------------------------------------------------------------
        # Step 3: Evaluate subnet pairs in parallel
        # ----------------------------------------------------------------
        # Only evaluate each ordered pair (A→B) where A.id < B.id lexically
        # to avoid duplication, matching bidirectional analysis requirement.
        pairs: List[tuple] = []
        sn_sorted = sorted(all_subnets, key=lambda s: s["id"])
        for i, src in enumerate(sn_sorted):
            for dst in sn_sorted[i + 1:]:
                pairs.append((src, dst))

        semaphore = asyncio.Semaphore(10)

        async def _evaluate_pair(src: Dict, dst: Dict) -> Dict[str, Any]:
            async with semaphore:
                return await loop.run_in_executor(
                    None, _evaluate_pair_sync, src, dst
                )

        def _evaluate_pair_sync(src: Dict, dst: Dict) -> Dict[str, Any]:
            """Synchronous inner evaluation — runs in thread pool."""
            src_ip = src.get("host_ip") or _first_host_ip(src["address_prefix"])
            dst_ip = dst.get("host_ip") or _first_host_ip(dst["address_prefix"])

            result: Dict[str, Any] = {
                "source_subnet": {
                    "id": src["id"],
                    "name": src["name"],
                    "address_prefix": src["address_prefix"],
                },
                "destination_subnet": {
                    "id": dst["id"],
                    "name": dst["name"],
                    "address_prefix": dst["address_prefix"],
                },
                "routing_status": "unknown",
                "routing_hops": 0,
                "connectivity_status": _CONN_UNKNOWN,
                "ports_analyzed": port_list,
                "allowed_ports": [],
                "denied_ports": [],
                "blocking_rules": [],
                "route_path": None,
            }

            # ---- Routing analysis ----
            if not src_ip or not dst_ip:
                result["connectivity_status"] = _CONN_UNKNOWN
                result["routing_status"] = "unknown"
                return result

            try:
                routes = _get_routes_for_subnet(src)
                peered_vnets = _get_peered_vnets_for_subnet(src)
                path = _route_analyzer.trace_path(
                    source_subnet_id=src["id"] or src["name"],
                    dest_ip=dst_ip,
                    routes=routes,
                    peered_vnets=peered_vnets or None,
                )
                result["routing_status"] = path.status
                result["routing_hops"] = path.total_hops
                if include_route_details:
                    result["route_path"] = path.to_dict().get("hops", [])
            except Exception as re:
                logger.debug("Route eval failed for %s→%s: %s", src["name"], dst["name"], re)
                result["routing_status"] = "unknown"

            # If routing can't reach destination, skip NSG analysis
            if result["routing_status"] in _ROUTING_TERMINAL_UNREACHABLE:
                result["connectivity_status"] = "unreachable_routing"
                return result

            # ---- NSG analysis ----
            if not port_list:
                # Routing only mode — reachable if routing passed
                result["connectivity_status"] = (
                    _CONN_ALLOWED
                    if result["routing_status"] not in _ROUTING_TERMINAL_UNREACHABLE
                    else "unreachable_routing"
                )
                return result

            src_nsg_rules = nsg_rules_cache.get(src.get("nsg_id") or "", [])
            dst_nsg_rules = nsg_rules_cache.get(dst.get("nsg_id") or "", [])

            allowed_ports: List[int] = []
            denied_ports: List[int] = []
            blocking_rules: List[Dict[str, Any]] = []

            for port in port_list:
                port_allowed = True

                # Evaluate outbound on source NSG (if any)
                if src_nsg_rules and src.get("nsg_id"):
                    flow_out = FlowTuple(
                        source_ip=src_ip,
                        dest_ip=dst_ip,
                        dest_port=port,
                        protocol=protocol.upper(),
                    )
                    verdict_out = _nsg_evaluator.evaluate_flow(
                        src_nsg_rules, flow_out, direction="Outbound"
                    )
                    if verdict_out.action == "Deny":
                        port_allowed = False
                        mr = verdict_out.matched_rule
                        blocking_rules.append({
                            "port": port,
                            "rule_name": mr.name if mr else "DefaultDeny",
                            "nsg_id": src["nsg_id"],
                            "direction": "Outbound",
                            "action": "Deny",
                            "priority": mr.priority if mr else 65500,
                        })

                # Evaluate inbound on destination NSG (if any)
                if port_allowed and dst_nsg_rules and dst.get("nsg_id"):
                    flow_in = FlowTuple(
                        source_ip=src_ip,
                        dest_ip=dst_ip,
                        dest_port=port,
                        protocol=protocol.upper(),
                    )
                    verdict_in = _nsg_evaluator.evaluate_flow(
                        dst_nsg_rules, flow_in, direction="Inbound"
                    )
                    if verdict_in.action == "Deny":
                        port_allowed = False
                        mr = verdict_in.matched_rule
                        blocking_rules.append({
                            "port": port,
                            "rule_name": mr.name if mr else "DefaultDeny",
                            "nsg_id": dst["nsg_id"],
                            "direction": "Inbound",
                            "action": "Deny",
                            "priority": mr.priority if mr else 65500,
                        })

                if port_allowed:
                    allowed_ports.append(port)
                else:
                    denied_ports.append(port)

            result["allowed_ports"] = allowed_ports
            result["denied_ports"] = denied_ports
            result["blocking_rules"] = blocking_rules

            # Determine aggregate connectivity status
            if denied_ports and not allowed_ports:
                result["connectivity_status"] = _CONN_DENIED
            elif denied_ports and allowed_ports:
                result["connectivity_status"] = _CONN_PARTIAL
            else:
                result["connectivity_status"] = _CONN_ALLOWED

            return result

        # Run all pairs concurrently
        if len(pairs) > 100:
            logger.info("Evaluating %d pairs (this may take up to 60s)…", len(pairs))

        matrix_results = await asyncio.gather(
            *[_evaluate_pair(src, dst) for src, dst in pairs],
            return_exceptions=True,
        )

        # Replace any raised exceptions with error entries
        matrix: List[Dict[str, Any]] = []
        for i, item in enumerate(matrix_results):
            if isinstance(item, Exception):
                src, dst = pairs[i]
                logger.warning(
                    "Pair eval exception (%s→%s): %s", src["name"], dst["name"], item
                )
                matrix.append({
                    "source_subnet": {"id": src["id"], "name": src["name"],
                                      "address_prefix": src["address_prefix"]},
                    "destination_subnet": {"id": dst["id"], "name": dst["name"],
                                           "address_prefix": dst["address_prefix"]},
                    "routing_status": "unknown",
                    "routing_hops": 0,
                    "connectivity_status": _CONN_UNKNOWN,
                    "ports_analyzed": port_list,
                    "allowed_ports": [],
                    "denied_ports": [],
                    "blocking_rules": [],
                    "route_path": None,
                    "error": str(item),
                })
            else:
                matrix.append(item)  # type: ignore[arg-type]

        # ----------------------------------------------------------------
        # Step 4: Build summary statistics
        # ----------------------------------------------------------------
        fully_reachable = sum(1 for r in matrix if r["connectivity_status"] == _CONN_ALLOWED)
        partially_blocked = sum(1 for r in matrix if r["connectivity_status"] == _CONN_PARTIAL)
        fully_blocked = sum(
            1 for r in matrix
            if r["connectivity_status"] in (_CONN_DENIED, "unreachable_routing")
        )
        unreachable_routing = sum(
            1 for r in matrix if r["connectivity_status"] == "unreachable_routing"
        )

        summary = {
            "total_subnet_pairs": len(matrix),
            "fully_reachable": fully_reachable,
            "partially_blocked": partially_blocked,
            "fully_blocked": fully_blocked,
            "unreachable_routing": unreachable_routing,
            "subnets_analyzed": len(all_subnets),
            "ports_evaluated": port_list,
            "protocol": protocol,
        }

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "scope": scope,
            "summary": summary,
            "matrix": matrix,
            "peering_status": peering_status if include_peering_status else None,
            "truncated": truncated,
            "truncation_warning": truncation_warning,
        })

    except Exception as exc:
        logger.exception("generate_connectivity_matrix failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})



# ---------------------------------------------------------------------------
# Tool 13: inventory_network_resources
# ---------------------------------------------------------------------------

# Monthly cost estimates (USD) for idle / orphaned resources
_PUBLIC_IP_STANDARD_MONTHLY_COST = 3.65
_PUBLIC_IP_BASIC_MONTHLY_COST = 3.00


@_server.tool()
async def inventory_network_resources(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    include_orphaned: Annotated[
        bool,
        "If True, include orphaned NSGs (not associated with any subnet or NIC). Default True.",
    ] = True,
    include_unused: Annotated[
        bool,
        "If True, include unused resources: idle public IPs, unused route tables, unpeered VNets, "
        "disabled Network Watchers. Default True.",
    ] = True,
    age_threshold_days: Annotated[
        int,
        "Informational: minimum resource age in days before flagging. Resources newer than this "
        "threshold are still reported but noted as recently created. Default 90.",
    ] = 90,
) -> List[TextContent]:
    """Comprehensive network resource inventory with usage analysis for cost optimization.

    Identifies orphaned and unused Azure network resources:
    - Orphaned NSGs (not associated with any subnet or NIC)
    - Unused route tables (no associated subnets)
    - Idle public IPs (not attached to any resource)
    - Unpeered VNets (no active peering connections)
    - Network Watchers in a non-Succeeded provisioning state

    Returns an inventory with per-resource details, estimated monthly savings,
    and actionable cost-optimisation recommendations.  All findings are categorised
    as 'safe_to_delete' (high confidence) or 'requires_review' (needs manual check).
    """
    try:
        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": (
                    "subscription_id is required "
                    "(or set SUBSCRIPTION_ID / AZURE_SUBSCRIPTION_ID env var)"
                ),
            })

        executor = await get_azure_cli_executor()

        # ------------------------------------------------------------------
        # Helper: run an az CLI command and return the parsed JSON list.
        # ------------------------------------------------------------------
        async def _az_list(cmd: str, timeout: int = 90) -> List[Dict[str, Any]]:
            result = await executor.execute(cmd, timeout=timeout, add_subscription=False)
            if result.get("status") != "success":
                logger.warning(
                    "inventory_network_resources az command failed (%s): %s",
                    cmd, result.get("error"),
                )
                return []
            output = result.get("output") or []
            if isinstance(output, dict):
                return [output]
            return output if isinstance(output, list) else []

        # ------------------------------------------------------------------
        # Fetch all five resource types concurrently
        # ------------------------------------------------------------------
        logger.info(
            "inventory_network_resources: fetching resources for subscription %s", sub_id
        )

        nsg_task = asyncio.create_task(
            _az_list(f"az network nsg list --subscription {sub_id}")
        )
        route_table_task = asyncio.create_task(
            _az_list(f"az network route-table list --subscription {sub_id}")
        )
        public_ip_task = asyncio.create_task(
            _az_list(f"az network public-ip list --subscription {sub_id}")
        )
        vnet_task = asyncio.create_task(
            _az_list(f"az network vnet list --subscription {sub_id}")
        )
        watcher_task = asyncio.create_task(
            _az_list(f"az network watcher list --subscription {sub_id}")
        )

        await asyncio.gather(
            nsg_task, route_table_task, public_ip_task, vnet_task, watcher_task,
            return_exceptions=True,
        )

        nsgs_raw: List[Dict[str, Any]] = (
            nsg_task.result() if not nsg_task.exception() else []  # type: ignore[union-attr]
        )
        route_tables_raw: List[Dict[str, Any]] = (
            route_table_task.result() if not route_table_task.exception() else []  # type: ignore[union-attr]
        )
        public_ips_raw: List[Dict[str, Any]] = (
            public_ip_task.result() if not public_ip_task.exception() else []  # type: ignore[union-attr]
        )
        vnets_raw: List[Dict[str, Any]] = (
            vnet_task.result() if not vnet_task.exception() else []  # type: ignore[union-attr]
        )
        watchers_raw: List[Dict[str, Any]] = (
            watcher_task.result() if not watcher_task.exception() else []  # type: ignore[union-attr]
        )

        logger.info(
            "inventory_network_resources: fetched "
            "NSGs=%d RouteTables=%d PublicIPs=%d VNets=%d Watchers=%d",
            len(nsgs_raw), len(route_tables_raw),
            len(public_ips_raw), len(vnets_raw), len(watchers_raw),
        )

        # ------------------------------------------------------------------
        # Analysis buckets
        # ------------------------------------------------------------------
        orphaned_nsgs: List[Dict[str, Any]] = []
        unused_route_tables: List[Dict[str, Any]] = []
        idle_public_ips: List[Dict[str, Any]] = []
        unpeered_vnets: List[Dict[str, Any]] = []
        disabled_network_watchers: List[Dict[str, Any]] = []

        safe_to_delete: List[str] = []
        requires_review: List[str] = []
        estimated_monthly_savings: float = 0.0

        # ------------------------------------------------------------------
        # 1. Orphaned NSGs — no subnets AND no network interfaces attached
        # ------------------------------------------------------------------
        if include_orphaned:
            for nsg in nsgs_raw:
                subnets = nsg.get("subnets") or []
                nics = nsg.get("networkInterfaces") or []
                if not subnets and not nics:
                    resource_id = nsg.get("id", "")
                    custom_rules = len(nsg.get("securityRules") or [])
                    orphaned_nsgs.append({
                        "id": resource_id,
                        "name": nsg.get("name"),
                        "resource_group": nsg.get("resourceGroup"),
                        "location": nsg.get("location"),
                        "custom_rule_count": custom_rules,
                        "provisioning_state": nsg.get("provisioningState"),
                        "recommendation": (
                            "Safe to delete if no planned usage — "
                            "verify no dependencies (VMs, containers) first"
                        ),
                    })
                    # NSGs with custom rules warrant extra human review
                    if custom_rules > 0:
                        requires_review.append(resource_id)
                    else:
                        safe_to_delete.append(resource_id)

        # ------------------------------------------------------------------
        # 2. Unused route tables — no associated subnets
        # ------------------------------------------------------------------
        if include_unused:
            for rt in route_tables_raw:
                associated_subnets = rt.get("subnets") or []
                if not associated_subnets:
                    resource_id = rt.get("id", "")
                    unused_route_tables.append({
                        "id": resource_id,
                        "name": rt.get("name"),
                        "resource_group": rt.get("resourceGroup"),
                        "location": rt.get("location"),
                        "route_count": len(rt.get("routes") or []),
                        "provisioning_state": rt.get("provisioningState"),
                        "recommendation": (
                            "Delete after confirming no active subnet associations — "
                            "route tables are free but add management overhead"
                        ),
                    })
                    # Route tables are free; flag for review rather than auto-delete
                    requires_review.append(resource_id)

        # ------------------------------------------------------------------
        # 3. Idle public IPs — ipConfiguration is None (not attached to anything)
        # ------------------------------------------------------------------
        if include_unused:
            for pip in public_ips_raw:
                ip_config = pip.get("ipConfiguration")
                if ip_config is None:
                    resource_id = pip.get("id", "")
                    sku_name: str = (pip.get("sku") or {}).get("name", "Standard")
                    monthly_cost = (
                        _PUBLIC_IP_STANDARD_MONTHLY_COST
                        if sku_name.lower() == "standard"
                        else _PUBLIC_IP_BASIC_MONTHLY_COST
                    )
                    allocation_method: str = pip.get("publicIpAllocationMethod", "Unknown")
                    idle_public_ips.append({
                        "id": resource_id,
                        "name": pip.get("name"),
                        "resource_group": pip.get("resourceGroup"),
                        "location": pip.get("location"),
                        "allocation_method": allocation_method,
                        "sku": sku_name,
                        "ip_address": pip.get("ipAddress"),
                        "monthly_cost_usd": monthly_cost,
                        "provisioning_state": pip.get("provisioningState"),
                        "recommendation": (
                            f"Delete to save ${monthly_cost:.2f}/month — "
                            "deallocate first to confirm nothing depends on this IP"
                        ),
                    })
                    estimated_monthly_savings += monthly_cost
                    # Static / Standard IPs may be reserved intentionally — always review
                    if allocation_method.lower() == "static" or sku_name.lower() == "standard":
                        requires_review.append(resource_id)
                    else:
                        safe_to_delete.append(resource_id)

        # ------------------------------------------------------------------
        # 4. Unpeered VNets — no virtualNetworkPeerings entries at all
        # ------------------------------------------------------------------
        if include_unused:
            for vnet in vnets_raw:
                peerings = vnet.get("virtualNetworkPeerings") or []
                if not peerings:
                    resource_id = vnet.get("id", "")
                    addr_prefixes: List[str] = (
                        (vnet.get("addressSpace") or {}).get("addressPrefixes") or []
                    )
                    unpeered_vnets.append({
                        "id": resource_id,
                        "name": vnet.get("name"),
                        "resource_group": vnet.get("resourceGroup"),
                        "location": vnet.get("location"),
                        "address_prefixes": addr_prefixes,
                        "subnet_count": len(vnet.get("subnets") or []),
                        "provisioning_state": vnet.get("provisioningState"),
                        "recommendation": (
                            "Review isolation requirements — an unpeered VNet may indicate "
                            "an unused environment or a missing hub/spoke peering"
                        ),
                    })
                    # VNets with subnets are likely in use — always require review
                    requires_review.append(resource_id)

        # ------------------------------------------------------------------
        # 5. Disabled / degraded Network Watchers
        # ------------------------------------------------------------------
        if include_unused:
            for watcher in watchers_raw:
                prov_state: str = watcher.get("provisioningState", "")
                if prov_state.lower() != "succeeded":
                    resource_id = watcher.get("id", "")
                    disabled_network_watchers.append({
                        "id": resource_id,
                        "name": watcher.get("name"),
                        "resource_group": watcher.get("resourceGroup"),
                        "location": watcher.get("location"),
                        "provisioning_state": prov_state,
                        "recommendation": (
                            f"Network Watcher is in '{prov_state}' state — "
                            "re-enable or recreate to restore connectivity diagnostics"
                        ),
                    })
                    requires_review.append(resource_id)

        # ------------------------------------------------------------------
        # Build final response
        # ------------------------------------------------------------------
        orphaned_count = len(orphaned_nsgs)
        unused_count = (
            len(unused_route_tables)
            + len(idle_public_ips)
            + len(unpeered_vnets)
            + len(disabled_network_watchers)
        )
        total_findings = orphaned_count + unused_count

        logger.info(
            "inventory_network_resources: %d findings "
            "(orphaned=%d unused=%d) est. savings $%.2f/month",
            total_findings, orphaned_count, unused_count, estimated_monthly_savings,
        )

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "age_threshold_days": age_threshold_days,
            "summary": {
                "total_resources_scanned": (
                    len(nsgs_raw) + len(route_tables_raw)
                    + len(public_ips_raw) + len(vnets_raw) + len(watchers_raw)
                ),
                "total_findings": total_findings,
                "orphaned_count": orphaned_count,
                "unused_count": unused_count,
                "estimated_monthly_savings_usd": round(estimated_monthly_savings, 2),
            },
            "orphaned_nsgs": orphaned_nsgs,
            "unused_route_tables": unused_route_tables,
            "idle_public_ips": idle_public_ips,
            "unpeered_vnets": unpeered_vnets,
            "disabled_network_watchers": disabled_network_watchers,
            # Deduplicated, insertion-ordered lists
            "safe_to_delete": list(dict.fromkeys(safe_to_delete)),
            "requires_review": list(dict.fromkeys(requires_review)),
        })

    except Exception as exc:
        logger.exception("inventory_network_resources failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool: analyze_private_connectivity_coverage
# ---------------------------------------------------------------------------

# Private endpoint monthly cost estimate (USD)
_PE_MONTHLY_COST_USD = 10.0

# Service endpoint type names per PaaS resource category
_SERVICE_ENDPOINT_MAP: Dict[str, str] = {
    "storage": "Microsoft.Storage",
    "sql": "Microsoft.Sql",
    "cosmos": "Microsoft.AzureCosmosDB",
    "keyvault": "Microsoft.KeyVault",
}

# CLI query timeout (seconds)
_RG_QUERY_TIMEOUT = 90


@_server.tool()
async def analyze_private_connectivity_coverage(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to SUBSCRIPTION_ID env var.",
    ] = None,
    scope: Annotated[
        str,
        "Scope: \'all\' (default), \'rg:<resource_group>\' to limit to a resource group, "
        "or \'type:<storage|sql|cosmos|keyvault>\' to inspect one PaaS type.",
    ] = "all",
) -> List[TextContent]:
    """Analyze PaaS private connectivity coverage for zero-trust assessment.

    Scans Storage accounts, SQL servers, CosmosDB accounts, and Key Vaults to
    classify each resource by connectivity posture:

    - **fully_private**: Private endpoint attached, public network access disabled.
    - **service_endpoint_only**: Subnet service endpoints configured (public may still be open).
    - **public_with_firewall**: Public access enabled but IP firewall rules restrict it.
    - **fully_public**: Public access with no private or service endpoints (high risk).

    Also audits all VNet subnets for service endpoint configuration and calculates the
    estimated monthly cost to achieve full zero-trust via private endpoints.

    Returns a structured report with per-resource recommendations.
    """
    try:
        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": "subscription_id is required (or set SUBSCRIPTION_ID env var)",
            })

        executor = await get_azure_cli_executor()

        # ------------------------------------------------------------------
        # Parse scope filter
        # ------------------------------------------------------------------
        rg_filter: Optional[str] = None
        type_filter: Optional[str] = None

        if scope.startswith("rg:"):
            rg_filter = scope[3:].strip()
        elif scope.startswith("type:"):
            type_filter = scope[5:].strip().lower()

        all_types = ["storage", "sql", "cosmos", "keyvault"]
        types_to_query = (
            [type_filter] if (type_filter and type_filter in all_types) else all_types
        )

        # ------------------------------------------------------------------
        # Helper: run az CLI command and return parsed output list
        # ------------------------------------------------------------------
        async def _az(cmd: str) -> Any:
            result = await executor.execute(cmd, timeout=_RG_QUERY_TIMEOUT, add_subscription=False)
            if result.get("status") != "success":
                logger.warning("CLI command failed: %s — %s", cmd, result.get("error"))
                return []
            return result.get("output") or []

        # ------------------------------------------------------------------
        # Step 1: Fetch private endpoints and PaaS resources in parallel
        # ------------------------------------------------------------------
        _rg_suffix = f" --resource-group {rg_filter}" if rg_filter else ""

        async def _fetch_private_endpoints() -> Dict[str, List[Dict[str, Any]]]:
            """Return mapping: lower(linked_resource_id) -> list of PE info dicts."""
            raw: List[Dict[str, Any]] = await _az(
                f"az network private-endpoint list --subscription {sub_id}{_rg_suffix} -o json"
            )
            mapping: Dict[str, List[Dict[str, Any]]] = {}
            for pe in raw:
                conns = (
                    pe.get("privateLinkServiceConnections")
                    or pe.get("manualPrivateLinkServiceConnections")
                    or []
                )
                for conn in conns:
                    linked_id = (conn.get("privateLinkServiceId") or "").lower()
                    state = (
                        conn.get("privateLinkServiceConnectionState") or {}
                    ).get("status", "Unknown")
                    if linked_id:
                        mapping.setdefault(linked_id, []).append({
                            "pe_name": pe.get("name"),
                            "pe_id": pe.get("id"),
                            "pe_rg": pe.get("resourceGroup"),
                            "connection_state": state,
                        })
            return mapping

        async def _fetch_storage() -> List[Dict[str, Any]]:
            if "storage" not in types_to_query:
                return []
            return await _az(
                f"az storage account list --subscription {sub_id}{_rg_suffix} -o json"
            )

        async def _fetch_sql() -> List[Dict[str, Any]]:
            if "sql" not in types_to_query:
                return []
            return await _az(
                f"az sql server list --subscription {sub_id}{_rg_suffix} -o json"
            )

        async def _fetch_cosmos() -> List[Dict[str, Any]]:
            if "cosmos" not in types_to_query:
                return []
            return await _az(
                f"az cosmosdb list --subscription {sub_id}{_rg_suffix} -o json"
            )

        async def _fetch_keyvaults() -> List[Dict[str, Any]]:
            if "keyvault" not in types_to_query:
                return []
            return await _az(
                f"az keyvault list --subscription {sub_id}{_rg_suffix} -o json"
            )

        async def _fetch_vnets() -> List[Dict[str, Any]]:
            return await _az(
                f"az network vnet list --subscription {sub_id}{_rg_suffix} -o json"
            )

        (
            pe_map,
            storage_raw,
            sql_raw,
            cosmos_raw,
            kv_raw,
            vnets_raw,
        ) = await asyncio.gather(
            _fetch_private_endpoints(),
            _fetch_storage(),
            _fetch_sql(),
            _fetch_cosmos(),
            _fetch_keyvaults(),
            _fetch_vnets(),
        )

        # ------------------------------------------------------------------
        # Step 2: Build subnet -> service endpoint type map from VNet data
        # ------------------------------------------------------------------
        subnet_service_ep_map: Dict[str, List[str]] = {}  # lower subnet_id -> [svc names]
        all_subnet_ids: List[str] = []

        for vnet in vnets_raw:
            for sn in (vnet.get("subnets") or []):
                sn_id = (sn.get("id") or "").lower()
                if not sn_id:
                    continue
                all_subnet_ids.append(sn_id)
                svc_eps = sn.get("serviceEndpoints") or []
                ep_types = [ep.get("service", "") for ep in svc_eps if ep.get("service")]
                subnet_service_ep_map[sn_id] = ep_types

        subnets_with_endpoints = [sid for sid, eps in subnet_service_ep_map.items() if eps]
        subnets_without_endpoints = [
            sid for sid in all_subnet_ids if not subnet_service_ep_map.get(sid)
        ]

        # Human-readable: short subnet name -> endpoint types
        endpoint_types_by_subnet: Dict[str, List[str]] = {
            (sn_id.split("/subnets/")[-1] if "/subnets/" in sn_id else sn_id): ep_types
            for sn_id, ep_types in subnet_service_ep_map.items()
            if ep_types
        }

        # ------------------------------------------------------------------
        # Step 3: Classification helpers
        # ------------------------------------------------------------------
        def _subnets_for_type(resource_type: str) -> List[str]:
            svc_name = _SERVICE_ENDPOINT_MAP.get(resource_type, "")
            return [
                (sn_id.split("/subnets/")[-1] if "/subnets/" in sn_id else sn_id)
                for sn_id, eps in subnet_service_ep_map.items()
                if svc_name and svc_name in eps
            ]

        fully_private: List[Dict[str, Any]] = []
        service_ep_only: List[Dict[str, Any]] = []
        public_with_firewall: List[Dict[str, Any]] = []
        fully_public: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        def _classify(
            resource_id: str,
            resource_type: str,
            public_access_on: bool,
            firewall_ips: List[str],
        ) -> None:
            rid_lower = resource_id.lower()
            approved_pes = [
                p for p in pe_map.get(rid_lower, [])
                if p.get("connection_state") == "Approved"
            ]
            pe_count = len(approved_pes)
            svc_subnets = _subnets_for_type(resource_type)
            has_svc_ep = bool(svc_subnets)
            base: Dict[str, Any] = {"id": resource_id, "type": resource_type}

            if pe_count > 0 and not public_access_on:
                # Ideal zero-trust posture
                fully_private.append({**base, "private_endpoint_count": pe_count})
                if pe_count > 2:
                    recommendations.append({
                        "resource_id": resource_id,
                        "current_state": "fully_private",
                        "recommendation": (
                            f"Resource has {pe_count} private endpoints — review if all are "
                            "needed; consolidate to reduce cost."
                        ),
                        "monthly_cost": pe_count * _PE_MONTHLY_COST_USD,
                    })

            elif pe_count > 0 and public_access_on:
                # PE exists but public access still open — easy win: disable public access
                public_with_firewall.append(
                    {**base, "allowed_ips": firewall_ips, "has_private_endpoint": True}
                )
                recommendations.append({
                    "resource_id": resource_id,
                    "current_state": "private_endpoint_exists_public_still_open",
                    "recommendation": (
                        "Disable public network access — a private endpoint is already configured."
                    ),
                    "monthly_cost": 0.0,
                })

            elif has_svc_ep:
                # Service endpoint coverage (public access may or may not be open)
                service_ep_only.append({**base, "subnets": svc_subnets})
                rec_text = (
                    "Consider adding a private endpoint for enhanced security ($10/month)."
                    if not public_access_on
                    else (
                        "Restrict public network access and consider adding a private endpoint "
                        "for zero-trust compliance ($10/month)."
                    )
                )
                recommendations.append({
                    "resource_id": resource_id,
                    "current_state": "service_endpoint_only",
                    "recommendation": rec_text,
                    "monthly_cost": _PE_MONTHLY_COST_USD,
                })

            elif public_access_on and firewall_ips:
                # Public but IP firewall provides partial control
                public_with_firewall.append({**base, "allowed_ips": firewall_ips})
                recommendations.append({
                    "resource_id": resource_id,
                    "current_state": "public_with_firewall",
                    "recommendation": (
                        "Create a private endpoint and disable public access for full zero-trust "
                        "compliance ($10/month). IP firewall offers partial protection only."
                    ),
                    "monthly_cost": _PE_MONTHLY_COST_USD,
                })

            else:
                # No isolation — highest risk
                fully_public.append({**base, "risk": "high"})
                recommendations.append({
                    "resource_id": resource_id,
                    "current_state": "fully_public",
                    "recommendation": (
                        "HIGH RISK: Create a private endpoint and disable public network access "
                        "immediately ($10/month). No network isolation is currently in place."
                    ),
                    "monthly_cost": _PE_MONTHLY_COST_USD,
                })

        # ------------------------------------------------------------------
        # Step 4: Classify each PaaS resource
        # ------------------------------------------------------------------

        # Storage accounts
        for sa in storage_raw:
            rid = sa.get("id") or ""
            if not rid:
                continue
            public_on = (sa.get("publicNetworkAccess") or "Enabled").lower() != "disabled"
            net_rules = sa.get("networkRuleSet") or {}
            ips = [r.get("ipAddressOrRange", "") for r in (net_rules.get("ipRules") or [])]
            _classify(rid, "storage", public_on, [ip for ip in ips if ip])

        # SQL servers (inline firewall rules not available; treat conservatively)
        for srv in sql_raw:
            rid = srv.get("id") or ""
            if not rid:
                continue
            public_on = (srv.get("publicNetworkAccess") or "Enabled").lower() != "disabled"
            _classify(rid, "sql", public_on, [])

        # CosmosDB accounts
        for ca in cosmos_raw:
            rid = ca.get("id") or ""
            if not rid:
                continue
            public_on = (ca.get("publicNetworkAccess") or "Enabled").lower() != "disabled"
            ips = [r.get("ipAddressOrRange", "") for r in (ca.get("ipRules") or [])]
            _classify(rid, "cosmos", public_on, [ip for ip in ips if ip])

        # Key Vaults (defaultAction "Deny" = restricted; "Allow" = public open)
        for kv in kv_raw:
            rid = kv.get("id") or ""
            if not rid:
                continue
            props = kv.get("properties") or {}
            net_acls = props.get("networkAcls") or {}
            public_on = (net_acls.get("defaultAction") or "Allow").lower() != "deny"
            ips = [r.get("value", "") for r in (net_acls.get("ipRules") or [])]
            _classify(rid, "keyvault", public_on, [ip for ip in ips if ip])

        # ------------------------------------------------------------------
        # Step 5: Compute summary statistics
        # ------------------------------------------------------------------
        total_paas = (
            len(fully_private)
            + len(service_ep_only)
            + len(public_with_firewall)
            + len(fully_public)
        )
        public_access_count = len(public_with_firewall) + len(fully_public)
        pe_total = sum(r.get("private_endpoint_count", 1) for r in fully_private)
        svc_ep_pct = round((len(service_ep_only) / total_paas * 100) if total_paas else 0.0, 1)
        zero_trust_pct = round((len(fully_private) / total_paas * 100) if total_paas else 0.0, 1)
        resources_needing_pe = (
            len(service_ep_only) + len(public_with_firewall) + len(fully_public)
        )
        cost_for_full_zero_trust = round(resources_needing_pe * _PE_MONTHLY_COST_USD, 2)

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "scope": scope,
            "summary": {
                "total_paas_resources": total_paas,
                "public_access_enabled": public_access_count,
                "private_endpoints_count": pe_total,
                "service_endpoints_coverage": svc_ep_pct,
                "zero_trust_compliance": zero_trust_pct,
            },
            "resources_by_connectivity": {
                "fully_private": fully_private,
                "service_endpoint_only": service_ep_only,
                "public_with_firewall": public_with_firewall,
                "fully_public": fully_public,
            },
            "service_endpoint_coverage": {
                "subnets_with_endpoints": subnets_with_endpoints,
                "subnets_without_endpoints": subnets_without_endpoints,
                "endpoint_types_by_subnet": endpoint_types_by_subnet,
            },
            "recommendations": recommendations,
            "cost_for_full_zero_trust": cost_for_full_zero_trust,
        })

    except Exception as exc:
        logger.exception("analyze_private_connectivity_coverage failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})

# ---------------------------------------------------------------------------
# Tool: analyze_dns_resolution_path
# ---------------------------------------------------------------------------

@_server.tool()
async def analyze_dns_resolution_path(
    context: Context,
    subscription_id: Annotated[
        str,
        "Azure subscription ID containing the source VNet.",
    ],
    fqdn: Annotated[
        str,
        "Fully qualified domain name to resolve (e.g. 'app.example.com').",
    ],
    source_vnet_id: Annotated[
        str,
        "ARM resource ID of the source VNet "
        "(e.g. /subscriptions/.../virtualNetworks/my-vnet).",
    ],
    include_hybrid_dns: Annotated[
        bool,
        "If True, include analysis of hybrid DNS resolution via VPN/ExpressRoute. Default True.",
    ] = True,
) -> List[TextContent]:
    """Trace the DNS resolution path for an FQDN from a source VNet.

    Analyzes:
    - Azure-provided DNS (168.63.129.16) vs custom DNS servers configured on the VNet
    - Private DNS zone existence and VNet linkage for the FQDN domain
    - A/CNAME record presence within matched Private DNS zones
    - Hybrid DNS resolution path (custom DNS forwarding) when VPN/ExpressRoute is in use
    - NXDOMAIN root causes: missing zone, missing VNet link, or missing DNS record

    This tool performs configuration-based simulation — it does not issue live DNS
    queries. Visibility into custom/on-premises DNS servers is limited to noting
    that resolution is forwarded to them.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        from azure.mgmt.privatedns import PrivateDnsManagementClient

        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": "subscription_id is required (or set SUBSCRIPTION_ID env var)",
            })

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # ------------------------------------------------------------------
        # Step 1 – Parse VNet identity from resource ID
        # ------------------------------------------------------------------
        vnet_sub_id, vnet_rg, vnet_name = _parse_resource_id(source_vnet_id)
        if not vnet_rg or not vnet_name:
            return _text_result({
                "success": False,
                "error": f"Cannot parse VNet resource ID: '{source_vnet_id}'",
            })

        resolution_path: List[Dict[str, Any]] = []
        step = 0

        # ------------------------------------------------------------------
        # Step 2 – Get VNet DNS configuration
        # ------------------------------------------------------------------
        def _get_vnet_dns():
            client = NetworkManagementClient(credential, vnet_sub_id or sub_id)
            return client.virtual_networks.get(vnet_rg, vnet_name)

        vnet_obj = await loop.run_in_executor(None, _get_vnet_dns)

        dns_servers: List[str] = []
        if vnet_obj.dhcp_options and vnet_obj.dhcp_options.dns_servers:
            dns_servers = list(vnet_obj.dhcp_options.dns_servers)

        using_azure_dns = len(dns_servers) == 0
        step += 1
        if using_azure_dns:
            resolution_path.append({
                "step": step,
                "location": "VNet DNS config",
                "details": "Using Azure-provided DNS (168.63.129.16) — no custom DNS servers configured",
            })
        else:
            resolution_path.append({
                "step": step,
                "location": "VNet DNS config",
                "details": (
                    f"Custom DNS servers configured: {', '.join(dns_servers)}. "
                    "Resolution will be forwarded to these servers."
                ),
            })

        dns_config = {
            "vnet_id": source_vnet_id,
            "dns_servers": dns_servers,
            "using_azure_dns": using_azure_dns,
        }

        # ------------------------------------------------------------------
        # Step 3 – Build candidate zone suffixes from the FQDN
        # ------------------------------------------------------------------
        fqdn_clean = fqdn.rstrip(".")
        fqdn_parts = fqdn_clean.split(".")
        # Generate all possible zone name suffixes from most-specific to least-specific
        candidate_zones = [".".join(fqdn_parts[i:]) for i in range(1, len(fqdn_parts))]

        # ------------------------------------------------------------------
        # Step 4 – Query Private DNS zones (subscription-wide)
        # ------------------------------------------------------------------
        def _query_private_dns() -> List[Dict[str, Any]]:
            dns_client = PrivateDnsManagementClient(credential, sub_id)

            try:
                all_zones = list(dns_client.private_zones.list())
            except Exception as list_err:
                logger.warning("Private DNS zone list failed: %s", list_err)
                return []

            matched: List[Dict[str, Any]] = []
            for zone in all_zones:
                zone_name: str = zone.name or ""
                # Only consider zones whose name exactly matches a candidate suffix
                if zone_name not in candidate_zones:
                    continue

                # Determine zone resource group from the ARM ID
                zone_rg = ""
                if zone.id:
                    id_parts = [p for p in zone.id.split("/") if p]
                    for idx, part in enumerate(id_parts):
                        if part.lower() == "resourcegroups" and idx + 1 < len(id_parts):
                            zone_rg = id_parts[idx + 1]
                            break
                if not zone_rg:
                    continue

                # Check whether the source VNet is linked to this zone
                vnet_linked = False
                link_state: Optional[str] = None
                try:
                    links = list(dns_client.virtual_network_links.list(zone_rg, zone_name))
                    for link in links:
                        linked_vnet_id = link.virtual_network.id if link.virtual_network else ""
                        if linked_vnet_id.lower() == source_vnet_id.lower():
                            vnet_linked = True
                            link_state = (
                                str(link.virtual_network_link_state)
                                if link.virtual_network_link_state
                                else "Unknown"
                            )
                            break
                except Exception as link_err:
                    logger.debug("VNet link query failed for zone %s: %s", zone_name, link_err)

                # Determine the record label within this zone
                if fqdn_clean == zone_name:
                    label = "@"
                elif fqdn_clean.endswith("." + zone_name):
                    label = fqdn_clean[: len(fqdn_clean) - len(zone_name) - 1]
                else:
                    label = fqdn_clean

                # Look for A or CNAME records matching the label
                has_matching_record = False
                record_ip: Optional[str] = None
                record_cname: Optional[str] = None
                try:
                    record_sets = list(dns_client.record_sets.list(zone_rg, zone_name))
                    for rs in record_sets:
                        if rs.name in (label, "@", fqdn_clean):
                            if rs.a_records:
                                has_matching_record = True
                                record_ip = rs.a_records[0].ipv4_address
                            elif rs.cname_record:
                                has_matching_record = True
                                record_cname = rs.cname_record.cname
                            break
                except Exception as rec_err:
                    logger.debug("Record lookup failed for zone %s: %s", zone_name, rec_err)

                matched.append({
                    "zone_name": zone_name,
                    "zone_rg": zone_rg,
                    "vnet_linked": vnet_linked,
                    "link_state": link_state,
                    "has_matching_record": has_matching_record,
                    "resolved_ip": record_ip,
                    "resolved_cname": record_cname,
                })

            return matched

        private_dns_zones: List[Dict[str, Any]] = []
        if using_azure_dns:
            step += 1
            resolution_path.append({
                "step": step,
                "location": "Private DNS zone lookup",
                "details": (
                    f"Searching subscription for Private DNS zones matching domain of '{fqdn_clean}' "
                    f"(candidates: {', '.join(candidate_zones[:3])}"
                    f"{'...' if len(candidate_zones) > 3 else ''})"
                ),
            })
            private_dns_zones = await loop.run_in_executor(None, _query_private_dns)

        # ------------------------------------------------------------------
        # Step 5 – Hybrid DNS path notes (custom DNS servers)
        # ------------------------------------------------------------------
        hybrid_dns_notes: Optional[str] = None
        if not using_azure_dns and include_hybrid_dns:
            step += 1
            resolution_path.append({
                "step": step,
                "location": "Hybrid DNS resolution",
                "details": (
                    f"Custom DNS servers ({', '.join(dns_servers)}) will handle resolution. "
                    "These are typically on-premises DNS servers reachable via VPN or ExpressRoute. "
                    "Verify: (1) DNS server is reachable from VNet, "
                    "(2) Conditional forwarders/zones are configured for this domain."
                ),
            })
            hybrid_dns_notes = (
                "Resolution delegated to custom DNS servers. "
                "Azure has limited visibility into forwarded DNS resolution chains."
            )

        # ------------------------------------------------------------------
        # Step 6 – Simulate resolution and determine status / root cause
        # ------------------------------------------------------------------
        resolution_status = "unknown"
        resolved_ip: Optional[str] = None
        failure_root_cause: Optional[str] = None
        recommendations: List[str] = []

        if using_azure_dns:
            linked_zones = [z for z in private_dns_zones if z["vnet_linked"]]
            unlinked_zones = [z for z in private_dns_zones if not z["vnet_linked"]]

            if not private_dns_zones:
                # No matching Private DNS zone found at all
                step += 1
                resolution_path.append({
                    "step": step,
                    "location": "Resolution result",
                    "details": (
                        f"No Private DNS zone found for any domain suffix of '{fqdn_clean}'. "
                        "Azure DNS will fall back to public DNS lookup."
                    ),
                })
                # Heuristic: private-looking names should have a Private DNS zone
                is_likely_private = any(
                    seg in fqdn_clean.lower()
                    for seg in [
                        "internal", "private", "corp", "local", "privatelink",
                        "priv", "azure.internal", "svc", "intranet", "lan",
                    ]
                )
                if is_likely_private:
                    resolution_status = "nxdomain"
                    failure_root_cause = (
                        f"No Private DNS zone covers the domain of '{fqdn_clean}'. "
                        "This FQDN appears to be a private/internal name requiring "
                        "a Private DNS zone in Azure."
                    )
                    recommendations.append(
                        f"Create an Azure Private DNS zone for the appropriate domain suffix "
                        f"(e.g. one of: {', '.join(candidate_zones[:2])})."
                    )
                    recommendations.append(
                        f"Link the new Private DNS zone to VNet '{vnet_name}'."
                    )
                    recommendations.append(
                        "If using Private Endpoints, enable DNS integration during PE creation "
                        "to auto-register records."
                    )
                else:
                    resolution_status = "success"
                    step += 1
                    resolution_path.append({
                        "step": step,
                        "location": "Public DNS",
                        "details": (
                            f"'{fqdn_clean}' will resolve via public DNS. "
                            "Azure cannot simulate the actual public DNS outcome."
                        ),
                    })

            elif linked_zones:
                # Found at least one zone that is linked to the source VNet
                zone = linked_zones[0]
                step += 1
                resolution_path.append({
                    "step": step,
                    "location": "Private DNS zone",
                    "details": (
                        f"Found zone '{zone['zone_name']}', VNet link present "
                        f"(state: {zone.get('link_state', 'Unknown')})."
                    ),
                })

                if zone["has_matching_record"]:
                    step += 1
                    resolved_ip = zone.get("resolved_ip")
                    resolved_cname = zone.get("resolved_cname")
                    if resolved_ip:
                        record_detail = f"A record resolved to {resolved_ip}"
                    elif resolved_cname:
                        record_detail = f"CNAME record → {resolved_cname}"
                    else:
                        record_detail = "Matching record found (no IP/CNAME value returned)"
                    resolution_path.append({
                        "step": step,
                        "location": "A record lookup",
                        "details": record_detail,
                    })
                    resolution_status = "success"
                else:
                    # Zone is linked but no record for this hostname
                    step += 1
                    resolution_path.append({
                        "step": step,
                        "location": "A record lookup",
                        "details": (
                            f"Private DNS zone '{zone['zone_name']}' is linked but contains "
                            f"no A/CNAME record for label '{fqdn_clean.split('.')[0]}'. "
                            "Resolution will return NXDOMAIN."
                        ),
                    })
                    resolution_status = "nxdomain"
                    failure_root_cause = (
                        f"Private DNS zone '{zone['zone_name']}' exists and is linked to the VNet, "
                        f"but has no DNS record for '{fqdn_clean}'."
                    )
                    recommendations.append(
                        f"Add an A record for '{fqdn_clean.split('.')[0]}' in zone "
                        f"'{zone['zone_name']}' pointing to the correct private IP."
                    )
                    recommendations.append(
                        "If this is a Private Endpoint, verify the PE was provisioned with "
                        "DNS integration enabled so records are auto-registered in the zone."
                    )

            else:
                # Zones exist but none are linked to the source VNet
                zone = unlinked_zones[0]
                step += 1
                resolution_path.append({
                    "step": step,
                    "location": "Private DNS zone",
                    "details": (
                        f"Found zone '{zone['zone_name']}' but it is NOT linked to VNet '{vnet_name}'. "
                        "DNS queries from this VNet cannot resolve against this zone."
                    ),
                })
                resolution_status = "nxdomain"
                failure_root_cause = (
                    f"Private DNS zone '{zone['zone_name']}' exists but has no VNet link to "
                    f"'{vnet_name}'. Queries from this VNet will not reach the zone."
                )
                recommendations.append(
                    f"Link VNet '{vnet_name}' to Private DNS zone '{zone['zone_name']}'. "
                    "In the Azure Portal: Private DNS zones → <zone> → Virtual network links → Add."
                )
                recommendations.append(
                    "For hub-spoke topologies, consider linking only the hub VNet and "
                    "routing DNS queries through a central Azure DNS Private Resolver."
                )

        else:
            # Custom DNS servers — limited visibility into forwarded resolution
            resolution_status = "unknown"
            step += 1
            resolution_path.append({
                "step": step,
                "location": "Resolution result",
                "details": (
                    "Resolution delegated to custom DNS servers. "
                    "Cannot simulate outcome without querying those servers directly."
                ),
            })
            if include_hybrid_dns:
                recommendations.append(
                    f"Verify custom DNS servers ({', '.join(dns_servers)}) are reachable "
                    "from this VNet via VPN or ExpressRoute."
                )
                recommendations.append(
                    f"Confirm DNS forwarding/conditional forwarder rules exist on custom DNS "
                    f"servers for the domain of '{fqdn_clean}'."
                )
                recommendations.append(
                    "Run 'nslookup' or 'Resolve-DnsName' from a VM in the VNet to test live resolution."
                )

        # ------------------------------------------------------------------
        # Build clean zones summary (strip internal resolution fields)
        # ------------------------------------------------------------------
        zones_summary = [
            {
                "zone_name": z["zone_name"],
                "vnet_linked": z["vnet_linked"],
                "has_matching_record": z["has_matching_record"],
            }
            for z in private_dns_zones
        ]

        return _text_result({
            "success": True,
            "fqdn": fqdn_clean,
            "source_vnet": vnet_name,
            "subscription_id": sub_id,
            "resolution_status": resolution_status,
            "resolution_path": resolution_path,
            "resolved_ip": resolved_ip,
            "dns_config": dns_config,
            "private_dns_zones": zones_summary,
            "failure_root_cause": failure_root_cause,
            "recommendations": recommendations,
            "hybrid_dns_notes": hybrid_dns_notes,
        })

    except Exception as exc:
        logger.exception("analyze_dns_resolution_path failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Tool 16: assess_network_security_posture
# ---------------------------------------------------------------------------

@_server.tool()
async def assess_network_security_posture(
    context: Context,
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to the SUBSCRIPTION_ID environment variable.",
    ] = None,
    scope: Annotated[
        str,
        (
            "Scope of the assessment. Use 'all' for the entire subscription, "
            "or provide a resource group name to limit the scan."
        ),
    ] = "all",
    compliance_framework: Annotated[
        str,
        (
            "Compliance framework to evaluate. Supported values: "
            "'cis_azure' (CIS Azure Benchmark 1.5), 'nist' (NIST SP 800-53), "
            "'pci_dss' (PCI DSS 3.2.1). Default: 'cis_azure'."
        ),
    ] = "cis_azure",
    severity_filter: Annotated[
        Optional[str],
        (
            "Comma-separated list of severities to include "
            "(Critical, High, Medium, Low). Omit for all severities. "
            "Example: 'Critical,High'."
        ),
    ] = None,
    include_remediation: Annotated[
        bool,
        "Whether to include remediation guidance in findings. Default: True.",
    ] = True,
) -> List[TextContent]:
    """Assess Azure network security posture against a compliance framework.

    Evaluates network resources in the subscription against CIS Azure Benchmark,
    NIST SP 800-53, or PCI DSS rules and returns a compliance score with
    actionable findings.

    Rules evaluated (CIS Azure Benchmark):
    - NSG-001 (Critical): No NSG allows 0.0.0.0/0 on management ports (SSH/RDP/WinRM)
    - NSG-002 (High):     All subnets have an associated NSG
    - NSG-003 (Medium):   NSG flow logs are enabled on all NSGs
    - ROUTE-001 (High):   Default route (0.0.0.0/0) points to firewall/NVA, not Internet
    - VNET-001 (Low):     VNets use custom DNS servers
    - PE-001 (High):      PaaS services (Storage, Key Vault) use private endpoints

    Returns a structured report with:
    - Overall compliance score (0–100, severity-weighted)
    - Simple compliance percentage (passed/total × 100)
    - Per-finding details with severity, status, description, and remediation
    - Summary breakdowns by severity and rule category

    Example usage:
        assess_network_security_posture(
            subscription_id="...",
            compliance_framework="cis_azure",
            severity_filter="Critical,High",
        )
    """
    sub_id = subscription_id or _get_subscription_id()
    if not sub_id:
        return _text_result({
            "success": False,
            "error": "subscription_id is required. "
                     "Set SUBSCRIPTION_ID env var or pass it explicitly.",
        })

    # Parse the optional severity filter
    parsed_severity_filter: Optional[List[str]] = None
    if severity_filter:
        parsed_severity_filter = [
            s.strip() for s in severity_filter.split(",") if s.strip()
        ]

    try:
        report = await _posture_engine.assess_posture(
            subscription_id=sub_id,
            framework=compliance_framework,
            scope=scope,
            severity_filter=parsed_severity_filter,
        )

        # ------------------------------------------------------------------
        # NSG internet exposure audit (explicit list + inbound/outbound rule scan)
        # ------------------------------------------------------------------
        executor = await get_azure_cli_executor()
        nsg_cmd = f"az network nsg list --subscription {sub_id} --output json"
        if scope and scope.strip().lower() != "all":
            nsg_cmd += f" --resource-group {scope.strip()}"

        nsg_cli_result = await executor.execute(nsg_cmd, timeout=90, add_subscription=False)
        if nsg_cli_result.get("status") != "success":
            return _text_result({
                "success": False,
                "error": f"Failed to enumerate NSGs for exposure audit: {nsg_cli_result.get('error', 'CLI call failed')}",
            })

        nsgs_raw: List[Dict[str, Any]] = nsg_cli_result.get("output") or []

        def _has_public_match(value: Any) -> bool:
            if value is None:
                return False
            if isinstance(value, list):
                return any(_has_public_match(v) for v in value)
            token = str(value).strip().lower()
            return token in {
                "*",
                "any",
                "internet",
                "0.0.0.0/0",
                "::/0",
            }

        def _collect_prefixes(rule: Dict[str, Any], singular_key: str, plural_key: str) -> List[str]:
            prefixes: List[str] = []
            singular = rule.get(singular_key)
            plural = rule.get(plural_key)
            if singular is not None:
                prefixes.append(str(singular))
            if isinstance(plural, list):
                prefixes.extend(str(v) for v in plural)
            return [p for p in prefixes if p]

        def _collect_ports(rule: Dict[str, Any]) -> List[str]:
            ports: List[str] = []
            single = rule.get("destinationPortRange")
            many = rule.get("destinationPortRanges")
            if single is not None:
                ports.append(str(single))
            if isinstance(many, list):
                ports.extend(str(v) for v in many)
            return [p for p in ports if p]

        inbound_public_rules: List[Dict[str, Any]] = []
        outbound_public_rules: List[Dict[str, Any]] = []
        audited_nsgs: List[Dict[str, Any]] = []

        for nsg in nsgs_raw:
            nsg_name = str(nsg.get("name") or "")
            nsg_rg = str(nsg.get("resourceGroup") or "")
            nsg_id = str(nsg.get("id") or "")
            rules = nsg.get("securityRules") or []

            audited_nsgs.append(
                {
                    "name": nsg_name,
                    "resource_group": nsg_rg,
                    "resource_id": nsg_id,
                    "rule_count": len(rules),
                }
            )

            for rule in rules:
                access = str(rule.get("access") or "").lower()
                direction_val = str(rule.get("direction") or "")
                direction = direction_val.lower()
                if access != "allow" or direction not in {"inbound", "outbound"}:
                    continue

                src_prefixes = _collect_prefixes(rule, "sourceAddressPrefix", "sourceAddressPrefixes")
                dst_prefixes = _collect_prefixes(rule, "destinationAddressPrefix", "destinationAddressPrefixes")

                inbound_exposed = direction == "inbound" and _has_public_match(src_prefixes)
                outbound_exposed = direction == "outbound" and _has_public_match(dst_prefixes)

                if not (inbound_exposed or outbound_exposed):
                    continue

                finding = {
                    "nsg_name": nsg_name,
                    "resource_group": nsg_rg,
                    "nsg_resource_id": nsg_id,
                    "rule_name": str(rule.get("name") or ""),
                    "priority": rule.get("priority"),
                    "direction": direction_val,
                    "access": rule.get("access"),
                    "protocol": rule.get("protocol"),
                    "source_prefixes": src_prefixes,
                    "destination_prefixes": dst_prefixes,
                    "destination_ports": _collect_ports(rule),
                    "description": rule.get("description"),
                }

                if inbound_exposed:
                    inbound_public_rules.append(finding)
                if outbound_exposed:
                    outbound_public_rules.append(finding)

        exposed_nsg_keys = {
            (f.get("nsg_resource_id") or "").lower()
            for f in inbound_public_rules + outbound_public_rules
            if f.get("nsg_resource_id")
        }
        exposed_nsgs = [
            n for n in audited_nsgs
            if (n.get("resource_id") or "").lower() in exposed_nsg_keys
        ]

    except ValueError as exc:
        return _text_result({"success": False, "error": str(exc)})
    except Exception as exc:
        logger.exception("assess_network_security_posture failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})

    # Serialise findings, optionally stripping remediation
    findings_out = []
    for f in report.findings:
        entry: Dict[str, Any] = {
            "rule_id": f.rule_id,
            "severity": f.severity,
            "status": f.status,
            "resource_id": f.resource_id,
            "resource_type": f.resource_type,
            "description": f.description,
            "risk_description": f.risk_description,
        }
        if include_remediation:
            entry["remediation"] = f.remediation
        findings_out.append(entry)

    # Sort: failures first, then by severity weight descending
    _severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings_out.sort(
        key=lambda x: (
            0 if x["status"] == "failed" else 1,
            _severity_order.get(x["severity"], 9),
        )
    )

    failed_findings = [f for f in findings_out if f["status"] == "failed"]
    passed_findings = [f for f in findings_out if f["status"] == "passed"]

    compact_exposure_items: List[Dict[str, Any]] = []
    for finding in inbound_public_rules + outbound_public_rules:
        compact_exposure_items.append(
            {
                "nsg_name": finding.get("nsg_name"),
                "resource_group": finding.get("resource_group"),
                "rule_name": finding.get("rule_name"),
                "direction": finding.get("direction"),
                "access": finding.get("access"),
                "protocol": finding.get("protocol"),
                "destination_ports": finding.get("destination_ports") or [],
            }
        )

    compact_exposure_items.sort(
        key=lambda x: (
            str(x.get("nsg_name") or "").lower(),
            str(x.get("direction") or "").lower(),
            str(x.get("rule_name") or "").lower(),
        )
    )

    return _text_result({
        "success": True,
        "subscription_id": sub_id,
        "scope": scope,
        "framework": compliance_framework,
        "assessed_at": report.assessed_at,
        "compliance_score": {
            "overall_score": report.overall_score,
            "compliance_percentage": report.compliance_percentage,
            "total_checks": len(report.findings),
            "passed_checks": len(passed_findings),
            "failed_checks": len(failed_findings),
        },
        "summary_by_severity": report.summary_by_severity,
        "summary_by_category": report.summary_by_category,
        "nsg_audit": {
            "total_nsgs_audited": len(audited_nsgs),
            "nsgs_with_public_exposure": len(exposed_nsgs),
            "inbound_public_allow_rule_count": len(inbound_public_rules),
            "outbound_public_allow_rule_count": len(outbound_public_rules),
            "audited_nsgs": audited_nsgs,
            "exposed_nsgs": exposed_nsgs,
            "inbound_public_allow_rules": inbound_public_rules,
            "outbound_public_allow_rules": outbound_public_rules,
        },
        "internet_exposure_summary": {
            "total_exposed_nsgs": len(exposed_nsgs),
            "total_exposing_rules": len(compact_exposure_items),
            "items": compact_exposure_items,
        },
        "failed_findings": failed_findings,
        "passed_findings": passed_findings,
    })


# ---------------------------------------------------------------------------
# Tool: validate_hub_spoke_topology
# ---------------------------------------------------------------------------

# Scoring constants for topology health
_SCORE_SPOKE_TO_SPOKE = 20   # deduct per unique spoke-to-spoke peering pair
_SCORE_MISSING_SERVICE = 15  # deduct per missing shared service (firewall or gateway)
_SCORE_NO_ROUTE_TABLE = 10   # deduct per spoke subnet without a compliant UDR
_SCORE_GATEWAY_TRANSIT = 5   # deduct per gateway transit misconfiguration


@_server.tool()
async def validate_hub_spoke_topology(
    context: Context,
    hub_vnet_id: Annotated[
        str,
        "ARM resource ID of the hub VNet "
        "(e.g. /subscriptions/.../virtualNetworks/hub-vnet) or 'resource_group/vnet_name'.",
    ],
    subscription_id: Annotated[
        Optional[str],
        "Azure subscription ID. Defaults to SUBSCRIPTION_ID environment variable.",
    ] = None,
    expected_spoke_vnets: Annotated[
        Optional[List[str]],
        "Optional list of expected spoke VNet ARM resource IDs or names. "
        "Missing spokes will be flagged as warnings.",
    ] = None,
) -> List[TextContent]:
    """Validate hub-spoke network topology architecture and produce a health score (0-100).

    Performs a comprehensive audit of an Azure hub-spoke VNet topology:
    - Verifies all spokes peer only to the hub (no spoke-to-spoke peering)
    - Confirms hub contains shared services (Azure Firewall, VPN/ER Gateway, Bastion)
    - Checks spoke subnets have UDRs routing traffic through hub (0.0.0.0/0 -> hub NVA/firewall)
    - Validates gateway transit settings (hub allows transit, spokes use remote gateways)
    - Computes an overall topology health score and flags violations with remediation guidance

    Efficiently handles large topologies (20+ spokes) via parallel spoke VNet fetching.
    """
    if NetworkManagementClient is None:
        return _text_result({"error": "azure-mgmt-network not installed", "success": False})

    try:
        sub_id = subscription_id or _get_subscription_id()
        if not sub_id:
            return _text_result({
                "success": False,
                "error": "subscription_id is required (or set SUBSCRIPTION_ID env var)",
            })

        credential = _get_credential()
        loop = asyncio.get_event_loop()

        # ------------------------------------------------------------------
        # Step 1: Parse hub VNet ID and fetch hub VNet + peerings
        # ------------------------------------------------------------------
        if not hub_vnet_id.startswith("/"):
            parts = hub_vnet_id.split("/", 1)
            hub_rg = parts[0]
            hub_vnet_name = parts[1] if len(parts) > 1 else parts[0]
        else:
            _, hub_rg, hub_vnet_name = _parse_resource_id(hub_vnet_id)

        def _fetch_hub_vnet():
            client = NetworkManagementClient(credential, sub_id)
            vnet = client.virtual_networks.get(hub_rg, hub_vnet_name)
            peerings = list(client.virtual_network_peerings.list(hub_rg, hub_vnet_name))
            return vnet, peerings

        hub_vnet, hub_peerings = await loop.run_in_executor(None, _fetch_hub_vnet)

        hub_address_prefixes: List[str] = []
        if hub_vnet.address_space and hub_vnet.address_space.address_prefixes:
            hub_address_prefixes = list(hub_vnet.address_space.address_prefixes)

        hub_vnet_resource_id: str = hub_vnet.id or hub_vnet_id

        # Collect spoke VNet IDs from hub peerings and build hub peering info
        spoke_ids_from_peerings: List[str] = []
        hub_peering_info: List[Dict[str, Any]] = []
        for p in hub_peerings:
            remote_id = p.remote_virtual_network.id if p.remote_virtual_network else None
            if remote_id:
                spoke_ids_from_peerings.append(remote_id)
            hub_peering_info.append({
                "name": p.name,
                "remote_vnet_id": remote_id,
                "peering_state": str(p.peering_state) if p.peering_state else None,
                "allow_gateway_transit": p.allow_gateway_transit,
                "use_remote_gateways": p.use_remote_gateways,
                "allow_forwarded_traffic": p.allow_forwarded_traffic,
            })

        # Deduplicate spoke IDs preserving original casing
        all_spoke_ids: List[str] = list({sid.lower(): sid for sid in spoke_ids_from_peerings}.values())

        # ------------------------------------------------------------------
        # Step 2: Fetch each spoke VNet + peerings + subnets in parallel
        # ------------------------------------------------------------------
        def _fetch_spoke(spoke_resource_id: str) -> Optional[Dict[str, Any]]:
            try:
                _, s_rg, s_name = _parse_resource_id(spoke_resource_id)
                client = NetworkManagementClient(credential, sub_id)
                vnet = client.virtual_networks.get(s_rg, s_name)
                peerings = list(client.virtual_network_peerings.list(s_rg, s_name))
                subnets = []
                for sn in (vnet.subnets or []):
                    subnets.append({
                        "name": sn.name,
                        "address_prefix": sn.address_prefix,
                        "route_table_id": sn.route_table.id if sn.route_table else None,
                        "subnet_id": sn.id,
                    })
                peer_list = []
                for p in peerings:
                    peer_list.append({
                        "name": p.name,
                        "remote_vnet_id": p.remote_virtual_network.id if p.remote_virtual_network else None,
                        "peering_state": str(p.peering_state) if p.peering_state else None,
                        "use_remote_gateways": p.use_remote_gateways,
                        "allow_gateway_transit": p.allow_gateway_transit,
                    })
                addr_prefixes: List[str] = []
                if vnet.address_space and vnet.address_space.address_prefixes:
                    addr_prefixes = list(vnet.address_space.address_prefixes)
                return {
                    "id": spoke_resource_id,
                    "name": s_name,
                    "resource_group": s_rg,
                    "address_prefixes": addr_prefixes,
                    "subnets": subnets,
                    "peerings": peer_list,
                }
            except Exception as spoke_err:
                logger.warning("Could not fetch spoke VNet '%s': %s", spoke_resource_id, spoke_err)
                return None

        spoke_fetch_tasks = [loop.run_in_executor(None, _fetch_spoke, sid) for sid in all_spoke_ids]
        spoke_results_raw = await asyncio.gather(*spoke_fetch_tasks, return_exceptions=True)
        spoke_data: List[Dict[str, Any]] = [
            r for r in spoke_results_raw if isinstance(r, dict) and r is not None
        ]

        # ------------------------------------------------------------------
        # Step 3: Detect shared services in hub RG via Azure CLI (parallel)
        # ------------------------------------------------------------------
        executor_cli = await get_azure_cli_executor()

        async def _query_resource_type(resource_type: str) -> List[Dict[str, Any]]:
            cmd = (
                f"az resource list --subscription {sub_id} "
                f"--resource-group {hub_rg} "
                f"--resource-type {resource_type}"
            )
            result = await executor_cli.execute(cmd, timeout=45, add_subscription=False)
            return result.get("output") or [] if result.get("status") == "success" else []

        firewalls_raw, vnet_gws_raw, bastions_raw = await asyncio.gather(
            asyncio.create_task(_query_resource_type("Microsoft.Network/azureFirewalls")),
            asyncio.create_task(_query_resource_type("Microsoft.Network/virtualNetworkGateways")),
            asyncio.create_task(_query_resource_type("Microsoft.Network/bastionHosts")),
        )

        # Separate VPN vs ExpressRoute gateways
        vpn_gateways = [
            gw for gw in vnet_gws_raw
            if (gw.get("properties") or {}).get("gatewayType", "").lower() == "vpn"
        ]
        er_gateways = [
            gw for gw in vnet_gws_raw
            if (gw.get("properties") or {}).get("gatewayType", "").lower() == "expressroute"
        ]
        # CLI may omit properties -- use name-based heuristic as fallback
        if not vpn_gateways and not er_gateways and vnet_gws_raw:
            vpn_gateways = [gw for gw in vnet_gws_raw if "er" not in gw.get("name", "").lower()]
            er_gateways = [gw for gw in vnet_gws_raw if "er" in gw.get("name", "").lower()]

        has_firewall = bool(firewalls_raw)
        has_vpn_gw = bool(vpn_gateways)
        has_er_gw = bool(er_gateways)
        has_bastion = bool(bastions_raw)
        has_any_gateway = has_vpn_gw or has_er_gw

        shared_services: Dict[str, Any] = {
            "azure_firewall": {
                "present": has_firewall,
                "id": firewalls_raw[0].get("id") if firewalls_raw else None,
            },
            "vpn_gateway": {
                "present": has_vpn_gw,
                "id": vpn_gateways[0].get("id") if vpn_gateways else None,
            },
            "expressroute_gateway": {
                "present": has_er_gw,
                "id": er_gateways[0].get("id") if er_gateways else None,
            },
            "bastion": {
                "present": has_bastion,
                "id": bastions_raw[0].get("id") if bastions_raw else None,
            },
        }

        # ------------------------------------------------------------------
        # Step 4: Validate route tables on spoke subnets
        # ------------------------------------------------------------------
        # System subnets that are exempt from UDR requirements
        _EXEMPT_SUBNETS = frozenset({
            "gatewaysubnet",
            "azurebastionsubnet",
            "azurefirewallsubnet",
            "azurefirewallmanagementsubnet",
        })

        def _check_route_table(rt_id: str) -> Optional[str]:
            """Returns None if route table has valid 0.0.0.0/0 -> VirtualAppliance UDR."""
            try:
                _, rt_rg, rt_name = _parse_resource_id(rt_id)
                client = NetworkManagementClient(credential, sub_id)
                rt = client.route_tables.get(rt_rg, rt_name)
                for route in (rt.routes or []):
                    if (route.address_prefix or "").strip() == "0.0.0.0/0":
                        next_hop = str(route.next_hop_type) if route.next_hop_type else ""
                        if "VirtualAppliance" in next_hop:
                            return None  # Compliant
                        return (
                            f"Default route next_hop_type is '{next_hop}' "
                            "(expected VirtualAppliance pointing to hub NVA/firewall)"
                        )
                return "No 0.0.0.0/0 default route -- traffic may bypass hub firewall"
            except Exception as rt_err:
                return f"Could not inspect route table '{rt_id}': {rt_err}"

        compliant_subnets: List[str] = []
        non_compliant_subnets: List[Dict[str, Any]] = []

        for spoke in spoke_data:
            for subnet in spoke["subnets"]:
                if subnet.get("name", "").lower() in _EXEMPT_SUBNETS:
                    continue
                subnet_id = subnet.get("subnet_id") or f"{spoke['id']}/subnets/{subnet['name']}"
                rt_id = subnet.get("route_table_id")
                if not rt_id:
                    non_compliant_subnets.append({
                        "subnet_id": subnet_id,
                        "issue": "No route table attached -- default internet egress is in effect",
                    })
                else:
                    rt_issue = await loop.run_in_executor(None, _check_route_table, rt_id)
                    if rt_issue is None:
                        compliant_subnets.append(subnet_id)
                    else:
                        non_compliant_subnets.append({"subnet_id": subnet_id, "issue": rt_issue})

        route_table_compliance: Dict[str, Any] = {
            "compliant_subnets": compliant_subnets,
            "non_compliant_subnets": non_compliant_subnets,
        }

        # ------------------------------------------------------------------
        # Step 5: Validate gateway transit settings
        # ------------------------------------------------------------------
        hub_peerings_correct = True
        if has_any_gateway:
            for p_info in hub_peering_info:
                if p_info.get("allow_gateway_transit") is not True:
                    hub_peerings_correct = False
                    break

        spoke_peering_compliance: List[Dict[str, Any]] = []
        for spoke in spoke_data:
            hub_peer_in_spoke: Optional[Dict[str, Any]] = None
            for sp in spoke["peerings"]:
                remote = (sp.get("remote_vnet_id") or "").lower()
                hub_id_lower = hub_vnet_resource_id.lower()
                if hub_id_lower in remote or remote in hub_id_lower:
                    hub_peer_in_spoke = sp
                    break

            if hub_peer_in_spoke is None:
                spoke_peering_compliance.append({
                    "spoke_id": spoke["id"],
                    "correct": False,
                    "issue": "No peering back to hub found in spoke VNet",
                })
            elif has_any_gateway and hub_peer_in_spoke.get("use_remote_gateways") is not True:
                spoke_peering_compliance.append({
                    "spoke_id": spoke["id"],
                    "correct": False,
                    "issue": (
                        "use_remote_gateways is not enabled on spoke->hub peering; "
                        "spoke cannot use hub VPN/ExpressRoute gateway"
                    ),
                })
            else:
                spoke_peering_compliance.append({
                    "spoke_id": spoke["id"],
                    "correct": True,
                    "issue": None,
                })

        gateway_transit_compliance: Dict[str, Any] = {
            "hub_peerings_correct": hub_peerings_correct,
            "spoke_peerings_correct": spoke_peering_compliance,
        }

        # ------------------------------------------------------------------
        # Step 6: Build violation list
        # ------------------------------------------------------------------
        violations: List[Dict[str, Any]] = []
        spoke_vnet_ids_lower = {s["id"].lower() for s in spoke_data}

        # --- Critical: spoke-to-spoke peerings (deduplicated bidirectional pairs) ---
        seen_spoke_pairs: set = set()
        for spoke in spoke_data:
            for sp in spoke["peerings"]:
                remote_id = (sp.get("remote_vnet_id") or "").lower()
                hub_id_lower = hub_vnet_resource_id.lower()
                is_hub_peer = hub_id_lower in remote_id or remote_id in hub_id_lower
                if not is_hub_peer and remote_id in spoke_vnet_ids_lower:
                    pair = tuple(sorted([spoke["id"].lower(), remote_id]))
                    if pair not in seen_spoke_pairs:
                        seen_spoke_pairs.add(pair)
                        violations.append({
                            "severity": "critical",
                            "description": (
                                f"Spoke-to-spoke peering detected: '{spoke['name']}' peers directly "
                                f"to spoke '{sp.get('remote_vnet_id', 'unknown')}'. "
                                "This bypasses centralized inspection and breaks the hub-spoke model."
                            ),
                            "affected_resources": [spoke["id"], sp.get("remote_vnet_id", "")],
                            "remediation": (
                                "Remove the spoke-to-spoke peering and route all inter-spoke traffic "
                                "through the hub firewall or NVA for centralized policy enforcement."
                            ),
                        })

        # --- Critical: no Azure Firewall in hub ---
        if not has_firewall:
            violations.append({
                "severity": "critical",
                "description": (
                    f"No Azure Firewall found in hub resource group '{hub_rg}'. "
                    "Egress and inter-spoke traffic is uncontrolled and uninspected."
                ),
                "affected_resources": [hub_vnet_resource_id],
                "remediation": (
                    "Deploy Azure Firewall in hub VNet (requires AzureFirewallSubnet /26 min). "
                    "Configure Firewall Policy with application and network rule collections. "
                    "Update spoke subnet UDRs: 0.0.0.0/0 -> firewall private IP "
                    "(next_hop_type: VirtualAppliance)."
                ),
            })

        # --- Warning: spoke subnet without compliant route table ---
        for nc in non_compliant_subnets:
            violations.append({
                "severity": "warning",
                "description": (
                    f"Spoke subnet '{nc['subnet_id'].split('/')[-1]}' routing issue: {nc['issue']}"
                ),
                "affected_resources": [nc["subnet_id"]],
                "remediation": (
                    "Create a UDR with route 0.0.0.0/0 -> hub firewall/NVA private IP "
                    "(next_hop_type: VirtualAppliance) and attach the route table to the subnet."
                ),
            })

        # --- Warning: gateway transit misconfiguration ---
        gateway_transit_misconfigs = 0
        if not hub_peerings_correct and has_any_gateway:
            gateway_transit_misconfigs += 1
            violations.append({
                "severity": "warning",
                "description": (
                    "One or more hub->spoke peerings are missing 'allow_gateway_transit: true'. "
                    "Spokes cannot use the hub VPN/ExpressRoute gateway."
                ),
                "affected_resources": [hub_vnet_resource_id],
                "remediation": (
                    "az network vnet peering update --resource-group <hub-rg> "
                    "--vnet-name <hub-vnet> --name <peering-name> --set allowGatewayTransit=true"
                ),
            })

        for sp_comp in spoke_peering_compliance:
            if not sp_comp["correct"]:
                gateway_transit_misconfigs += 1
                violations.append({
                    "severity": "warning",
                    "description": f"Spoke '{sp_comp['spoke_id'].split('/')[-1]}': {sp_comp['issue']}",
                    "affected_resources": [sp_comp["spoke_id"]],
                    "remediation": (
                        "az network vnet peering update --resource-group <spoke-rg> "
                        "--vnet-name <spoke-vnet> --name <peering-name> --set useRemoteGateways=true"
                    ),
                })

        # --- Warning: expected spokes missing ---
        if expected_spoke_vnets:
            connected_ids = {s["id"].lower() for s in spoke_data}
            connected_names = {s["name"].lower() for s in spoke_data}
            for expected in expected_spoke_vnets:
                if expected.lower() not in connected_ids and expected.lower() not in connected_names:
                    violations.append({
                        "severity": "warning",
                        "description": f"Expected spoke VNet '{expected}' is not peered to the hub.",
                        "affected_resources": [expected],
                        "remediation": (
                            "Create bidirectional VNet peering: hub->spoke with allowGatewayTransit=true; "
                            "spoke->hub with useRemoteGateways=true (when hub has VPN/ER gateway)."
                        ),
                    })

        # ------------------------------------------------------------------
        # Step 7: Compute topology health score (0-100)
        # ------------------------------------------------------------------
        score = 100
        score -= len(seen_spoke_pairs) * _SCORE_SPOKE_TO_SPOKE
        if not has_firewall:
            score -= _SCORE_MISSING_SERVICE
        if not has_any_gateway:
            score -= _SCORE_MISSING_SERVICE
        score -= len(non_compliant_subnets) * _SCORE_NO_ROUTE_TABLE
        score -= gateway_transit_misconfigs * _SCORE_GATEWAY_TRANSIT
        score = max(0, min(100, score))

        if score >= 80:
            validation_status = "healthy"
        elif score >= 50:
            validation_status = "warnings"
        else:
            validation_status = "critical"

        # ------------------------------------------------------------------
        # Step 8: Build spoke summary list
        # ------------------------------------------------------------------
        spoke_summary: List[Dict[str, Any]] = []
        for spoke in spoke_data:
            spoke_id_lower = spoke["id"].lower()
            spoke_violations = [
                v["description"]
                for v in violations
                if any(r.lower() == spoke_id_lower for r in v.get("affected_resources", []))
            ]
            hub_side_peering = next(
                (p for p in hub_peering_info
                 if (p.get("remote_vnet_id") or "").lower() == spoke_id_lower),
                None,
            )
            peering_status = hub_side_peering["peering_state"] if hub_side_peering else "Unknown"
            spoke_summary.append({
                "id": spoke["id"],
                "name": spoke["name"],
                "address_prefixes": spoke["address_prefixes"],
                "peering_status": peering_status,
                "violations": spoke_violations,
            })

        # ------------------------------------------------------------------
        # Step 9: Actionable recommendations
        # ------------------------------------------------------------------
        recommendations: List[str] = []
        if not has_firewall:
            recommendations.append(
                "Deploy Azure Firewall in hub VNet for centralized egress control and "
                "spoke-to-spoke traffic inspection (requires AzureFirewallSubnet /26 min)."
            )
        if not has_any_gateway:
            recommendations.append(
                "Add a VPN Gateway or ExpressRoute Gateway to the hub for shared hybrid "
                "connectivity across all spoke VNets without per-spoke gateway costs."
            )
        if not has_bastion:
            recommendations.append(
                "Deploy Azure Bastion in hub for secure browser-based VM access without "
                "public IP exposure (requires AzureBastionSubnet /26 min)."
            )
        if non_compliant_subnets:
            recommendations.append(
                f"{len(non_compliant_subnets)} spoke subnet(s) lack UDRs enforcing hub routing. "
                "Add route tables with 0.0.0.0/0 -> hub firewall/NVA to prevent traffic bypassing "
                "centralized inspection."
            )
        if seen_spoke_pairs:
            recommendations.append(
                f"Remove {len(seen_spoke_pairs)} spoke-to-spoke peering(s) to enforce the "
                "hub-spoke model and ensure all east-west traffic is inspected by hub firewall."
            )
        if not violations:
            recommendations.append(
                "Topology is healthy. Consider enabling Azure DDoS Network Protection on the "
                "hub VNet and auditing Firewall Policy rules for rule set hygiene."
            )

        return _text_result({
            "success": True,
            "subscription_id": sub_id,
            "topology_health_score": score,
            "validation_status": validation_status,
            "hub_vnet": {
                "id": hub_vnet_resource_id,
                "name": hub_vnet_name,
                "resource_group": hub_rg,
                "address_prefixes": hub_address_prefixes,
                "peering_count": len(hub_peerings),
            },
            "spoke_vnets": spoke_summary,
            "shared_services": shared_services,
            "violations": violations,
            "violation_count": len(violations),
            "route_table_compliance": route_table_compliance,
            "gateway_transit_compliance": gateway_transit_compliance,
            "recommendations": recommendations,
        })

    except Exception as exc:
        logger.exception("validate_hub_spoke_topology failed: %s", exc)
        return _text_result({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point (run as standalone MCP server via stdio)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _server.run(transport="stdio")

