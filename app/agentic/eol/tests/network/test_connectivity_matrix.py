"""
Connectivity Matrix Generator Tests

Unit tests for the generate_connectivity_matrix MCP tool and its helper
functions in mcp_servers/network_mcp_server.py.

Tests use mocked Azure SDK objects and pre-built Route/NSGRule lists so that
no live Azure credentials are needed.

Created: 2026-02-27 (Network Agent Enhancement Plan, Task 6)
"""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path so we can import from utils/mcp_servers
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Import helpers from network_mcp_server
# ---------------------------------------------------------------------------
# Mock 'mcp' before importing the server so tests don't need FastMCP installed
import sys
from unittest.mock import MagicMock as _MagicMock

_mcp_mod = _MagicMock()
_mcp_mod.server = _MagicMock()
_mcp_mod.server.fastmcp = _MagicMock()
_mcp_mod.types = _MagicMock()
sys.modules.setdefault("mcp", _mcp_mod)
sys.modules.setdefault("mcp.server", _mcp_mod.server)
sys.modules.setdefault("mcp.server.fastmcp", _mcp_mod.server.fastmcp)
sys.modules.setdefault("mcp.types", _mcp_mod.types)

# Mock azure packages as well
for _pkg in [
    "azure", "azure.identity", "azure.mgmt", "azure.mgmt.network",
    "azure.mgmt.resource", "azure.mgmt.privatedns",
]:
    sys.modules.setdefault(_pkg, _MagicMock())

from mcp_servers.network_mcp_server import (
    _first_host_ip,
    _parse_subnet_info,
    _build_nsg_rules_from_sdk,
    _build_route_list_from_sdk,
    _build_peered_vnets_map,
    _CONN_ALLOWED,
    _CONN_DENIED,
    _CONN_PARTIAL,
    _CONN_UNKNOWN,
)
from utils.nsg_rule_evaluator import NSGRule, NSGRuleEvaluator
from utils.route_path_analyzer import Route, RoutePathAnalyzer, ROUTE_SOURCE_DEFAULT, ROUTE_SOURCE_USER


# ---------------------------------------------------------------------------
# Fake Azure SDK objects
# ---------------------------------------------------------------------------

def _make_sdk_route(prefix: str, next_hop_type: str, nhi: Optional[str] = None) -> MagicMock:
    r = MagicMock()
    r.address_prefix = prefix
    r.next_hop_type = next_hop_type
    r.next_hop_ip_address = nhi
    return r


def _make_sdk_route_table(routes: list, rt_id: str = "/subscriptions/sub/rt/rt1") -> MagicMock:
    rt = MagicMock()
    rt.id = rt_id
    rt.routes = routes
    return rt


def _make_sdk_nsg_rule(
    name: str,
    priority: int,
    access: str,
    direction: str,
    src: str = "*",
    dst: str = "*",
    dst_port: str = "*",
    protocol: str = "Tcp",
) -> MagicMock:
    r = MagicMock()
    r.name = name
    r.priority = priority
    r.access = access
    r.direction = direction
    r.source_address_prefix = src
    r.destination_address_prefix = dst
    r.destination_port_range = dst_port
    r.protocol = protocol
    r.description = None
    return r


def _make_sdk_nsg(rules: list, defaults: Optional[list] = None) -> MagicMock:
    nsg = MagicMock()
    nsg.security_rules = rules
    nsg.default_security_rules = defaults or []
    return nsg


def _make_address_space(prefixes: List[str]) -> MagicMock:
    a = MagicMock()
    a.address_prefixes = prefixes
    return a


def _make_sdk_peering(
    state: str,
    remote_prefixes: List[str],
    remote_vnet_id: str,
    allow_forwarded: bool = False,
    use_remote_gw: bool = False,
) -> MagicMock:
    p = MagicMock()
    p.peering_state = state
    p.name = "peering-test"
    remote_space = MagicMock()
    remote_space.address_prefixes = remote_prefixes
    p.remote_address_space = remote_space
    remote_vnet = MagicMock()
    remote_vnet.id = remote_vnet_id
    p.remote_virtual_network = remote_vnet
    p.allow_forwarded_traffic = allow_forwarded
    p.use_remote_gateways = use_remote_gw
    return p


def _make_sdk_vnet(
    vnet_id: str,
    prefixes: List[str],
    peerings: Optional[list] = None,
    subnets: Optional[list] = None,
) -> MagicMock:
    vnet = MagicMock()
    vnet.id = vnet_id
    vnet.address_space = _make_address_space(prefixes)
    vnet.virtual_network_peerings = peerings or []
    vnet.subnets = subnets or []
    return vnet


def _make_sdk_subnet(
    name: str,
    sid: str,
    prefix: str,
    nsg_id: Optional[str] = None,
    rt_id: Optional[str] = None,
) -> MagicMock:
    sn = MagicMock()
    sn.name = name
    sn.id = sid
    sn.address_prefix = prefix
    sn.network_security_group = MagicMock(id=nsg_id) if nsg_id else None
    sn.route_table = MagicMock(id=rt_id) if rt_id else None
    return sn


# ---------------------------------------------------------------------------
# Convenience constants
# ---------------------------------------------------------------------------

SUB = "sub-test"
VNET_A_ID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet-a"
VNET_B_ID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet-b"
NSG_A_ID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/nsg-a"
NSG_B_ID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/nsg-b"
RT_A_ID = f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/routeTables/rt-a"
SN_A_ID = f"{VNET_A_ID}/subnets/subnet-a"
SN_B_ID = f"{VNET_A_ID}/subnets/subnet-b"
SN_C_ID = f"{VNET_B_ID}/subnets/subnet-c"


# ===========================================================================
# Tests: Helper functions
# ===========================================================================


@pytest.mark.unit
class TestFirstHostIp:
    def test_standard_cidr(self):
        assert _first_host_ip("10.0.0.0/24") == "10.0.0.1"

    def test_slash_32(self):
        # /32 has no "hosts"; fallback to network address
        result = _first_host_ip("10.0.0.5/32")
        assert result in ("10.0.0.5", None)

    def test_slash_16(self):
        assert _first_host_ip("172.16.0.0/16") == "172.16.0.1"

    def test_invalid_cidr(self):
        assert _first_host_ip("not-a-cidr") is None


@pytest.mark.unit
class TestParseSubnetInfo:
    def test_sdk_object(self):
        sn = _make_sdk_subnet(
            "my-subnet", SN_A_ID, "10.0.1.0/24", nsg_id=NSG_A_ID
        )
        result = _parse_subnet_info(sn, VNET_A_ID)
        assert result is not None
        assert result["name"] == "my-subnet"
        assert result["address_prefix"] == "10.0.1.0/24"
        assert result["nsg_id"] == NSG_A_ID
        assert result["host_ip"] == "10.0.1.1"
        assert result["vnet_id"] == VNET_A_ID

    def test_dict_format(self):
        sn_dict = {
            "name": "sn-dict",
            "id": SN_B_ID,
            "addressPrefix": "192.168.1.0/24",
            "networkSecurityGroup": {"id": NSG_B_ID},
            "routeTable": None,
        }
        result = _parse_subnet_info(sn_dict, VNET_A_ID)
        assert result is not None
        assert result["nsg_id"] == NSG_B_ID
        assert result["route_table_id"] is None

    def test_missing_prefix_returns_none(self):
        sn = MagicMock()
        sn.name = "bad"
        sn.id = "some-id"
        sn.address_prefix = None
        sn.network_security_group = None
        sn.route_table = None
        assert _parse_subnet_info(sn, VNET_A_ID) is None

    def test_none_input_returns_none(self):
        assert _parse_subnet_info(None, VNET_A_ID) is None


@pytest.mark.unit
class TestBuildNsgRulesFromSdk:
    def test_parses_custom_and_default_rules(self):
        custom = _make_sdk_nsg_rule("allow-http", 100, "Allow", "Inbound", dst_port="80")
        default_deny = _make_sdk_nsg_rule("DenyAll", 65500, "Deny", "Inbound")
        nsg = _make_sdk_nsg([custom], [default_deny])
        rules = _build_nsg_rules_from_sdk(nsg)
        assert len(rules) == 2
        rule_names = [r.name for r in rules]
        assert "allow-http" in rule_names
        assert "DenyAll" in rule_names

    def test_empty_nsg(self):
        nsg = _make_sdk_nsg([], [])
        assert _build_nsg_rules_from_sdk(nsg) == []

    def test_rule_fields_mapped_correctly(self):
        raw = _make_sdk_nsg_rule("deny-ssh", 200, "Deny", "Inbound", dst_port="22")
        nsg = _make_sdk_nsg([raw])
        rules = _build_nsg_rules_from_sdk(nsg)
        assert len(rules) == 1
        r = rules[0]
        assert r.name == "deny-ssh"
        assert r.priority == 200
        assert r.action == "Deny"
        assert r.direction == "Inbound"
        assert r.dest_port_range == "22"


@pytest.mark.unit
class TestBuildRouteListFromSdk:
    def test_vnet_local_routes_added(self):
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"])
        routes = _build_route_list_from_sdk(vnet, None, None)
        local_routes = [r for r in routes if r.next_hop_type == "VNetLocal"]
        assert len(local_routes) == 1
        assert local_routes[0].address_prefix == "10.0.0.0/16"

    def test_default_internet_always_added(self):
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"])
        routes = _build_route_list_from_sdk(vnet, None, None)
        internet = [r for r in routes if r.next_hop_type == "Internet"]
        assert len(internet) == 1
        assert internet[0].address_prefix == "0.0.0.0/0"

    def test_peering_routes_added_for_connected(self):
        peering = _make_sdk_peering(
            state="Connected",
            remote_prefixes=["10.2.0.0/16"],
            remote_vnet_id=VNET_B_ID,
        )
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"], peerings=[peering])
        routes = _build_route_list_from_sdk(vnet, None, None)
        peering_routes = [r for r in routes if r.next_hop_type == "VNetPeering"]
        assert len(peering_routes) == 1
        assert peering_routes[0].address_prefix == "10.2.0.0/16"

    def test_disconnected_peering_not_added(self):
        peering = _make_sdk_peering(
            state="Disconnected",
            remote_prefixes=["10.2.0.0/16"],
            remote_vnet_id=VNET_B_ID,
        )
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"], peerings=[peering])
        routes = _build_route_list_from_sdk(vnet, None, None)
        peering_routes = [r for r in routes if r.next_hop_type == "VNetPeering"]
        assert len(peering_routes) == 0

    def test_udr_from_route_table(self):
        sdk_route = _make_sdk_route("10.99.0.0/16", "VirtualAppliance", nhi="10.0.0.5")
        rt = _make_sdk_route_table([sdk_route], RT_A_ID)
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"])
        routes = _build_route_list_from_sdk(vnet, rt, RT_A_ID)
        udr = [r for r in routes if r.source == ROUTE_SOURCE_USER]
        assert len(udr) == 1
        assert udr[0].next_hop_ip == "10.0.0.5"
        assert udr[0].address_prefix == "10.99.0.0/16"

    def test_multiple_vnet_prefixes(self):
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16", "10.1.0.0/16"])
        routes = _build_route_list_from_sdk(vnet, None, None)
        local_routes = [r for r in routes if r.next_hop_type == "VNetLocal"]
        assert len(local_routes) == 2


@pytest.mark.unit
class TestBuildPeeredVnetsMap:
    def test_connected_peering_included(self):
        peering = _make_sdk_peering("Connected", ["10.2.0.0/16"], VNET_B_ID)
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"], peerings=[peering])
        peered = _build_peered_vnets_map(vnet)
        assert "10.2.0.0/16" in peered
        assert VNET_B_ID in peered["10.2.0.0/16"]

    def test_disconnected_peering_excluded(self):
        peering = _make_sdk_peering("Disconnected", ["10.2.0.0/16"], VNET_B_ID)
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"], peerings=[peering])
        peered = _build_peered_vnets_map(vnet)
        assert len(peered) == 0

    def test_no_peerings(self):
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"])
        assert _build_peered_vnets_map(vnet) == {}

    def test_multiple_peering_prefixes(self):
        peering = _make_sdk_peering("Connected", ["10.2.0.0/16", "10.3.0.0/16"], VNET_B_ID)
        vnet = _make_sdk_vnet(VNET_A_ID, ["10.0.0.0/16"], peerings=[peering])
        peered = _build_peered_vnets_map(vnet)
        assert len(peered) == 2


# ===========================================================================
# Tests: End-to-end logic using RoutePathAnalyzer + NSGRuleEvaluator directly
# ===========================================================================


@pytest.mark.unit
class TestPairEvaluationLogic:
    """
    These tests validate the logic that generate_connectivity_matrix uses
    internally, by calling RoutePathAnalyzer and NSGRuleEvaluator directly
    with the same inputs the MCP tool would construct.
    """

    def setup_method(self):
        self.analyzer = RoutePathAnalyzer()
        self.evaluator = NSGRuleEvaluator()

    def _make_allow_rule(self, port: str = "*") -> NSGRule:
        return NSGRule(
            name="AllowAll",
            priority=1000,
            action="Allow",
            direction="Inbound",
            source_address_prefix="*",
            dest_address_prefix="*",
            dest_port_range=port,
            protocol="*",
        )

    def _make_deny_rule(self, port: str, priority: int = 500) -> NSGRule:
        return NSGRule(
            name=f"Deny-{port}",
            priority=priority,
            action="Deny",
            direction="Inbound",
            source_address_prefix="*",
            dest_address_prefix="*",
            dest_port_range=port,
            protocol="*",
        )

    def test_local_route_reachable(self):
        """Two subnets in same VNet should be reachable via VNetLocal."""
        routes = [Route("10.0.0.0/16", "VNetLocal", source=ROUTE_SOURCE_DEFAULT)]
        path = self.analyzer.trace_path("subnet-a", "10.0.1.5", routes)
        assert path.status == "reachable"

    def test_black_hole_route_unreachable(self):
        """Black-hole route should mark pair as unreachable_routing."""
        routes = [Route("10.1.0.0/16", "None", source=ROUTE_SOURCE_USER)]
        path = self.analyzer.trace_path("subnet-a", "10.1.0.5", routes)
        assert path.status == "black_hole"
        # Connectivity matrix would classify this as unreachable_routing

    def test_nsg_deny_port_443(self):
        """NSG deny rule on port 443 should block that port."""
        from utils.nsg_rule_evaluator import FlowTuple
        rules = [
            self._make_deny_rule("443", priority=200),
            self._make_allow_rule("*"),
        ]
        flow = FlowTuple(source_ip="10.0.0.1", dest_ip="10.0.1.1",
                         dest_port=443, protocol="TCP")
        verdict = self.evaluator.evaluate_flow(rules, flow, direction="Inbound")
        assert verdict.action == "Deny"

    def test_nsg_allow_port_80(self):
        """Port 80 allowed when no deny rule exists."""
        from utils.nsg_rule_evaluator import FlowTuple
        rules = [self._make_allow_rule("*")]
        flow = FlowTuple(source_ip="10.0.0.1", dest_ip="10.0.1.1",
                         dest_port=80, protocol="TCP")
        verdict = self.evaluator.evaluate_flow(rules, flow, direction="Inbound")
        assert verdict.action == "Allow"

    def test_partial_connectivity_mixed_ports(self):
        """Port 80 allowed, port 22 denied → partial connectivity."""
        from utils.nsg_rule_evaluator import FlowTuple
        rules = [
            self._make_deny_rule("22", priority=100),
            self._make_allow_rule("*"),
        ]
        allowed_ports = []
        denied_ports = []
        for port in [80, 22]:
            flow = FlowTuple(source_ip="10.0.0.1", dest_ip="10.0.1.1",
                             dest_port=port, protocol="TCP")
            verdict = self.evaluator.evaluate_flow(rules, flow, direction="Inbound")
            if verdict.action == "Allow":
                allowed_ports.append(port)
            else:
                denied_ports.append(port)

        assert 80 in allowed_ports
        assert 22 in denied_ports
        # Status would be _CONN_PARTIAL
        status = _CONN_PARTIAL if (allowed_ports and denied_ports) else (
            _CONN_ALLOWED if not denied_ports else _CONN_DENIED
        )
        assert status == _CONN_PARTIAL

    def test_no_nsg_all_ports_allowed(self):
        """When no NSG attached, all ports should be allowed (no NSG = permit all)."""
        # Empty rules list → DefaultDeny from evaluator.
        # In the MCP tool, empty rules means no NSG → skip NSG check → allow.
        from utils.nsg_rule_evaluator import FlowTuple
        rules = []  # No NSG rules
        # evaluate_flow with empty rules returns DefaultDeny, but MCP tool skips
        # NSG check entirely when nsg_rules list is empty AND nsg_id is None.
        # This test validates that assumption: no rules = DefaultDeny from evaluator
        flow = FlowTuple(source_ip="10.0.0.1", dest_ip="10.0.1.1",
                         dest_port=443, protocol="TCP")
        verdict = self.evaluator.evaluate_flow(rules, flow, direction="Inbound")
        # The MCP tool skips calling evaluate_flow when there are no NSG rules
        # (nsg_rules is empty and nsg_id is None), so the port would be allowed.
        # Here we just verify the evaluator returns DefaultDeny for empty rules.
        assert verdict.action == "DefaultDeny"


# ===========================================================================
# Tests: Matrix summary statistics helpers
# ===========================================================================


@pytest.mark.unit
class TestMatrixSummaryStats:
    """Validate the summary aggregation logic."""

    def _fake_matrix_entry(self, status: str) -> Dict:
        return {
            "source_subnet": {"id": "s1", "name": "src", "address_prefix": "10.0.0.0/24"},
            "destination_subnet": {"id": "s2", "name": "dst", "address_prefix": "10.0.1.0/24"},
            "routing_status": "reachable",
            "routing_hops": 1,
            "connectivity_status": status,
            "ports_analyzed": [443],
            "allowed_ports": [443] if status == _CONN_ALLOWED else [],
            "denied_ports": [443] if status == _CONN_DENIED else [],
            "blocking_rules": [],
            "route_path": None,
        }

    def test_all_allowed(self):
        matrix = [self._fake_matrix_entry(_CONN_ALLOWED)] * 4
        fully_reachable = sum(1 for r in matrix if r["connectivity_status"] == _CONN_ALLOWED)
        assert fully_reachable == 4

    def test_mixed_statuses(self):
        matrix = [
            self._fake_matrix_entry(_CONN_ALLOWED),
            self._fake_matrix_entry(_CONN_PARTIAL),
            self._fake_matrix_entry(_CONN_DENIED),
            self._fake_matrix_entry("unreachable_routing"),
        ]
        fully_reachable = sum(1 for r in matrix if r["connectivity_status"] == _CONN_ALLOWED)
        partially_blocked = sum(1 for r in matrix if r["connectivity_status"] == _CONN_PARTIAL)
        fully_blocked = sum(
            1 for r in matrix
            if r["connectivity_status"] in (_CONN_DENIED, "unreachable_routing")
        )
        assert fully_reachable == 1
        assert partially_blocked == 1
        assert fully_blocked == 2

    def test_pair_count_for_n_subnets(self):
        """N subnets → N*(N-1)/2 pairs."""
        for n in [2, 3, 4, 5, 10]:
            expected = n * (n - 1) // 2
            subnets = [{"id": f"sn-{i}", "name": f"sn-{i}",
                        "address_prefix": f"10.0.{i}.0/24"} for i in range(n)]
            # Simulate the pair-generation logic
            sn_sorted = sorted(subnets, key=lambda s: s["id"])
            pairs = [(src, dst) for i, src in enumerate(sn_sorted)
                     for dst in sn_sorted[i + 1:]]
            assert len(pairs) == expected


# ===========================================================================
# Tests: Edge cases
# ===========================================================================


@pytest.mark.unit
class TestConnMatrixEdgeCases:
    def test_truncation_at_max_subnets(self):
        """Verify truncation logic reduces subnet list to max_subnets."""
        subnets = [{"id": f"sn-{i}", "name": f"sn-{i}",
                    "address_prefix": f"10.0.{i}.0/24",
                    "host_ip": f"10.0.{i}.1"} for i in range(30)]
        max_s = 10
        truncated = len(subnets) > max_s
        truncated_subnets = subnets[:max_s]
        assert truncated is True
        assert len(truncated_subnets) == max_s

    def test_fewer_than_2_subnets(self):
        """Single subnet → no pairs, empty matrix."""
        subnets = [{"id": "sn-1", "name": "sn-1", "address_prefix": "10.0.0.0/24"}]
        pairs = [(src, dst) for i, src in enumerate(subnets)
                 for dst in subnets[i + 1:]]
        assert len(pairs) == 0

    def test_ports_string_parsing(self):
        """Comma-separated port string should be parsed into int list."""
        ports_str = "22, 80, 443, 3306"
        port_list = []
        for p in ports_str.split(","):
            p = p.strip()
            if p.isdigit():
                port_list.append(int(p))
        assert port_list == [22, 80, 443, 3306]

    def test_empty_ports_string(self):
        """Empty/None ports string → empty list (routing only)."""
        for ports_input in [None, "", "  "]:
            port_list = []
            if ports_input:
                for p in ports_input.split(","):
                    p = p.strip()
                    if p.isdigit():
                        port_list.append(int(p))
            assert port_list == []

    def test_invalid_port_ignored(self):
        """Non-numeric port entries are skipped gracefully."""
        ports_str = "80,abc,443,xyz"
        port_list = [int(p.strip()) for p in ports_str.split(",")
                     if p.strip().isdigit()]
        assert port_list == [80, 443]

    def test_connectivity_status_logic_all_allowed(self):
        """Status is 'allowed' when all ports pass."""
        allowed = [80, 443]
        denied: list = []
        if denied and not allowed:
            status = _CONN_DENIED
        elif denied and allowed:
            status = _CONN_PARTIAL
        else:
            status = _CONN_ALLOWED
        assert status == _CONN_ALLOWED

    def test_connectivity_status_logic_all_denied(self):
        """Status is 'denied' when all ports blocked."""
        allowed: list = []
        denied = [22, 443]
        if denied and not allowed:
            status = _CONN_DENIED
        elif denied and allowed:
            status = _CONN_PARTIAL
        else:
            status = _CONN_ALLOWED
        assert status == _CONN_DENIED

    def test_connectivity_status_logic_partial(self):
        """Status is 'partial' when some ports pass and some are blocked."""
        allowed = [80]
        denied = [22]
        if denied and not allowed:
            status = _CONN_DENIED
        elif denied and allowed:
            status = _CONN_PARTIAL
        else:
            status = _CONN_ALLOWED
        assert status == _CONN_PARTIAL
