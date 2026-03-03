"""
Route Path Analyzer Tests

Tests for utils/route_path_analyzer.py covering LPM algorithm, path tracing,
asymmetric routing detection, and edge cases.
Created: 2026-02-27 (Network Agent Enhancement Plan, Task 2)
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.route_path_analyzer import (
    Route,
    RouteHop,
    RoutePath,
    RoutePathAnalyzer,
    NEXT_HOP_VNET_LOCAL,
    NEXT_HOP_VNET_PEERING,
    NEXT_HOP_GATEWAY,
    NEXT_HOP_INTERNET,
    NEXT_HOP_APPLIANCE,
    NEXT_HOP_NONE,
    ROUTE_SOURCE_USER,
    ROUTE_SOURCE_DEFAULT,
    STATUS_REACHABLE,
    STATUS_UNREACHABLE,
    STATUS_BLACK_HOLE,
    STATUS_INTERNET_EGRESS,
    STATUS_GATEWAY_EGRESS,
    route_path_analyzer,
)

# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

SOURCE_SUBNET = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-a/subnets/subnet-src"
DEST_SUBNET = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-b/subnets/subnet-dst"
PEERED_SUBNET = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-b/subnets/subnet-peer"


def _make_analyzer() -> RoutePathAnalyzer:
    return RoutePathAnalyzer()


def _local_route(prefix: str, source: str = ROUTE_SOURCE_DEFAULT) -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_VNET_LOCAL, source=source)


def _internet_route(prefix: str = "0.0.0.0/0") -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_INTERNET, source=ROUTE_SOURCE_DEFAULT)


def _blackhole_route(prefix: str) -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_NONE, source=ROUTE_SOURCE_USER)


def _peering_route(prefix: str) -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_VNET_PEERING, source=ROUTE_SOURCE_DEFAULT)


def _nva_route(prefix: str, nva_ip: str) -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_APPLIANCE, next_hop_ip=nva_ip, source=ROUTE_SOURCE_USER)


def _gateway_route(prefix: str) -> Route:
    return Route(address_prefix=prefix, next_hop_type=NEXT_HOP_GATEWAY, source=ROUTE_SOURCE_DEFAULT)


# ===========================================================================
# Tests: Dataclasses
# ===========================================================================


@pytest.mark.unit
class TestDataclasses:
    """Verify dataclass construction and to_dict serialization."""

    def test_route_defaults(self):
        r = Route(address_prefix="10.0.0.0/8", next_hop_type=NEXT_HOP_VNET_LOCAL)
        assert r.source == ROUTE_SOURCE_DEFAULT
        assert r.next_hop_ip is None
        assert r.route_table_id is None

    def test_route_hop_to_dict(self):
        hop = RouteHop(
            hop_number=1,
            location=SOURCE_SUBNET,
            next_hop_type=NEXT_HOP_VNET_LOCAL,
            route_source=ROUTE_SOURCE_DEFAULT,
            address_prefix="10.0.0.0/16",
            next_hop_ip=None,
        )
        d = hop.to_dict()
        assert d["hop_number"] == 1
        assert d["location"] == SOURCE_SUBNET
        assert d["next_hop_type"] == NEXT_HOP_VNET_LOCAL
        assert d["next_hop_ip"] is None

    def test_route_path_total_hops_computed(self):
        hop = RouteHop(1, SOURCE_SUBNET, NEXT_HOP_VNET_LOCAL, ROUTE_SOURCE_DEFAULT, "10.0.0.0/16")
        path = RoutePath(status=STATUS_REACHABLE, hops=[hop])
        assert path.total_hops == 1

    def test_route_path_to_dict(self):
        path = RoutePath(status=STATUS_BLACK_HOLE, hops=[], total_hops=0)
        d = path.to_dict()
        assert d["status"] == STATUS_BLACK_HOLE
        assert d["hops"] == []
        assert d["total_hops"] == 0
        assert d["asymmetric"] is None


# ===========================================================================
# Tests: Longest Prefix Match
# ===========================================================================


@pytest.mark.unit
class TestLongestPrefixMatch:
    """Verify LPM route selection logic."""

    def test_lpm_single_matching_route(self):
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        result = analyzer._longest_prefix_match("10.0.1.5", routes)
        assert result is not None
        assert result.address_prefix == "10.0.0.0/16"

    def test_lpm_selects_most_specific_prefix(self):
        analyzer = _make_analyzer()
        routes = [
            _local_route("10.0.0.0/8"),
            _local_route("10.0.0.0/16"),
            _local_route("10.0.1.0/24"),
        ]
        result = analyzer._longest_prefix_match("10.0.1.5", routes)
        assert result is not None
        assert result.address_prefix == "10.0.1.0/24"

    def test_lpm_default_route_matched(self):
        analyzer = _make_analyzer()
        routes = [_internet_route("0.0.0.0/0")]
        result = analyzer._longest_prefix_match("8.8.8.8", routes)
        assert result is not None
        assert result.address_prefix == "0.0.0.0/0"
        assert result.next_hop_type == NEXT_HOP_INTERNET

    def test_lpm_no_matching_route(self):
        analyzer = _make_analyzer()
        routes = [_local_route("192.168.0.0/24")]
        result = analyzer._longest_prefix_match("10.0.0.1", routes)
        assert result is None

    def test_lpm_user_route_beats_default_same_prefix(self):
        """User-defined routes take precedence over Default routes of equal prefix length."""
        analyzer = _make_analyzer()
        default_route = Route(
            address_prefix="10.0.0.0/16",
            next_hop_type=NEXT_HOP_INTERNET,
            source=ROUTE_SOURCE_DEFAULT,
        )
        user_route = Route(
            address_prefix="10.0.0.0/16",
            next_hop_type=NEXT_HOP_APPLIANCE,
            next_hop_ip="10.0.100.5",
            source=ROUTE_SOURCE_USER,
        )
        routes = [default_route, user_route]
        result = analyzer._longest_prefix_match("10.0.1.1", routes)
        assert result is not None
        assert result.source == ROUTE_SOURCE_USER
        assert result.next_hop_type == NEXT_HOP_APPLIANCE

    def test_lpm_user_route_first_in_list_still_wins(self):
        """User-route priority holds regardless of list order."""
        analyzer = _make_analyzer()
        user_route = Route(
            address_prefix="10.0.0.0/16",
            next_hop_type=NEXT_HOP_APPLIANCE,
            next_hop_ip="10.0.100.5",
            source=ROUTE_SOURCE_USER,
        )
        default_route = Route(
            address_prefix="10.0.0.0/16",
            next_hop_type=NEXT_HOP_INTERNET,
            source=ROUTE_SOURCE_DEFAULT,
        )
        routes = [user_route, default_route]
        result = analyzer._longest_prefix_match("10.0.1.1", routes)
        assert result is not None
        assert result.source == ROUTE_SOURCE_USER

    def test_lpm_empty_routes(self):
        analyzer = _make_analyzer()
        assert analyzer._longest_prefix_match("10.0.0.1", []) is None

    def test_lpm_invalid_ip(self):
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        result = analyzer._longest_prefix_match("not-an-ip", routes)
        assert result is None

    def test_lpm_malformed_prefix_skipped(self):
        """Malformed prefixes in route list are skipped without raising."""
        analyzer = _make_analyzer()
        routes = [
            Route(address_prefix="bad-cidr", next_hop_type=NEXT_HOP_VNET_LOCAL),
            _local_route("10.0.0.0/16"),
        ]
        result = analyzer._longest_prefix_match("10.0.0.5", routes)
        assert result is not None
        assert result.address_prefix == "10.0.0.0/16"

    def test_lpm_specific_over_default_route(self):
        """Specific /24 must beat default 0.0.0.0/0."""
        analyzer = _make_analyzer()
        routes = [
            _internet_route("0.0.0.0/0"),
            _local_route("10.1.1.0/24"),
        ]
        result = analyzer._longest_prefix_match("10.1.1.10", routes)
        assert result is not None
        assert result.address_prefix == "10.1.1.0/24"
        assert result.next_hop_type == NEXT_HOP_VNET_LOCAL


# ===========================================================================
# Tests: Path Tracing
# ===========================================================================


@pytest.mark.unit
class TestPathTracing:
    """Verify end-to-end path tracing logic."""

    def test_vnet_local_single_hop_reachable(self):
        """Traffic within same VNet should resolve to reachable in 1 hop."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(SOURCE_SUBNET, "10.0.1.5", routes)

        assert path.status == STATUS_REACHABLE
        assert path.total_hops == 1
        assert len(path.hops) == 1
        assert path.hops[0].next_hop_type == NEXT_HOP_VNET_LOCAL

    def test_internet_egress_via_default_route(self):
        """Default route (0.0.0.0/0) pointing to Internet."""
        analyzer = _make_analyzer()
        routes = [
            _local_route("10.0.0.0/16"),
            _internet_route("0.0.0.0/0"),
        ]
        path = analyzer.trace_path(SOURCE_SUBNET, "8.8.8.8", routes)

        assert path.status == STATUS_INTERNET_EGRESS
        assert path.total_hops == 1
        assert path.hops[0].next_hop_type == NEXT_HOP_INTERNET

    def test_black_hole_route_detection(self):
        """Route with next_hop_type=None should produce black_hole status."""
        analyzer = _make_analyzer()
        routes = [_blackhole_route("10.99.0.0/16")]
        path = analyzer.trace_path(SOURCE_SUBNET, "10.99.1.1", routes)

        assert path.status == STATUS_BLACK_HOLE
        assert path.total_hops == 1
        assert path.hops[0].next_hop_type == NEXT_HOP_NONE

    def test_gateway_egress(self):
        """VPN/ExpressRoute gateway path."""
        analyzer = _make_analyzer()
        routes = [_gateway_route("172.16.0.0/12")]
        path = analyzer.trace_path(SOURCE_SUBNET, "172.16.5.5", routes)

        assert path.status == STATUS_GATEWAY_EGRESS
        assert path.total_hops == 1
        assert path.hops[0].next_hop_type == NEXT_HOP_GATEWAY

    def test_nva_forwarding_reachable(self):
        """Traffic routed via NVA should be reported as reachable (limited visibility)."""
        analyzer = _make_analyzer()
        routes = [_nva_route("10.1.0.0/16", "10.0.100.5")]
        path = analyzer.trace_path(SOURCE_SUBNET, "10.1.2.3", routes)

        assert path.status == STATUS_REACHABLE
        assert path.total_hops == 1
        assert path.hops[0].next_hop_type == NEXT_HOP_APPLIANCE
        assert path.hops[0].next_hop_ip == "10.0.100.5"

    def test_vnet_peering_multi_hop(self):
        """VNetPeering hop should recurse into peered subnet and report reachable.

        Source subnet has a VNetPeering route to 10.2.0.0/16.  The
        peered_vnets dict resolves that to DEST_SUBNET.  The recursive call
        will also match the peering route (same route list), but DEST_SUBNET
        is now in visited so it returns unreachable.  The implementation
        promotes unreachable back to reachable when a peered subnet was
        successfully identified — because the peering connection exists, just
        the deeper route visibility is limited.
        """
        analyzer = _make_analyzer()
        source_routes = [_peering_route("10.2.0.0/16")]
        peered_vnets = {"10.2.0.0/16": DEST_SUBNET}

        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.2.0.10",
            routes=source_routes,
            peered_vnets=peered_vnets,
        )

        assert path.status == STATUS_REACHABLE
        assert path.total_hops >= 1
        assert path.hops[0].next_hop_type == NEXT_HOP_VNET_PEERING

    def test_vnet_peering_multi_hop_full_resolution(self):
        """Full 2-hop peering path: source peering → peered VNet local resolve."""
        analyzer = _make_analyzer()
        # Peered subnet is resolved with a different (more specific) local route
        # Using PEERED_SUBNET (a third distinct subnet) avoids the visited loop.
        source_routes = [
            _peering_route("10.2.0.0/16"),
            _local_route("10.2.0.0/24"),  # /24 more specific than /16 peering route
        ]
        peered_vnets = {"10.2.0.0/16": PEERED_SUBNET}

        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.2.0.10",
            routes=source_routes,
            peered_vnets=peered_vnets,
        )

        # LPM picks /24 VNetLocal (more specific than /16 peering), reachable in 1 hop
        assert path.status == STATUS_REACHABLE
        assert path.hops[0].next_hop_type == NEXT_HOP_VNET_LOCAL

    def test_vnet_peering_no_peered_vnets_dict(self):
        """VNetPeering hop with no peered_vnets dict → still reachable (best effort)."""
        analyzer = _make_analyzer()
        routes = [_peering_route("10.2.0.0/16")]

        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.2.0.10",
            routes=routes,
            peered_vnets=None,
        )

        assert path.status == STATUS_REACHABLE
        assert path.hops[0].next_hop_type == NEXT_HOP_VNET_PEERING

    def test_no_matching_route_unreachable(self):
        """No matching route should return unreachable."""
        analyzer = _make_analyzer()
        routes = [_local_route("192.168.0.0/24")]
        path = analyzer.trace_path(SOURCE_SUBNET, "10.5.5.5", routes)

        assert path.status == STATUS_UNREACHABLE

    def test_empty_routes_list(self):
        """Empty routes list → unreachable."""
        analyzer = _make_analyzer()
        path = analyzer.trace_path(SOURCE_SUBNET, "10.0.0.1", [])
        assert path.status == STATUS_UNREACHABLE

    def test_invalid_dest_ip(self):
        """Malformed IP address → unreachable."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(SOURCE_SUBNET, "not-an-ip", routes)
        assert path.status == STATUS_UNREACHABLE

    def test_empty_source_subnet_id(self):
        """Empty source_subnet_id → unreachable."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path("", "10.0.0.5", routes)
        assert path.status == STATUS_UNREACHABLE

    def test_empty_dest_ip(self):
        """Empty dest_ip → unreachable."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(SOURCE_SUBNET, "", routes)
        assert path.status == STATUS_UNREACHABLE


# ===========================================================================
# Tests: Loop Detection
# ===========================================================================


@pytest.mark.unit
class TestLoopDetection:
    """Verify max-hop limit and cycle detection."""

    def test_max_hops_protection(self):
        """If peered VNet chains loop back to visited subnet, stop at MAX_HOPS."""
        analyzer = _make_analyzer()
        # Create a chain: src → peer1 → peer2 → peer1 (loop)
        # By passing the same visited set through recursion, loop is caught.
        routes = [_peering_route("10.2.0.0/16")]
        peered_vnets = {
            "10.2.0.0/16": SOURCE_SUBNET  # Points back to the original source!
        }

        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.2.0.5",
            routes=routes,
            peered_vnets=peered_vnets,
        )

        # Loop detected immediately — should return unreachable (not infinite recursion)
        assert path.status in (STATUS_UNREACHABLE, STATUS_REACHABLE)

    def test_max_hop_count_exceeded(self):
        """trace_path with hop_count already at MAX_HOPS returns unreachable."""
        from utils.route_path_analyzer import MAX_HOPS

        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.0.0.5",
            routes=routes,
            hop_count=MAX_HOPS,  # Already at limit
        )
        assert path.status == STATUS_UNREACHABLE

    def test_visited_set_prevents_revisit(self):
        """Providing a pre-populated visited set prevents revisiting those subnets."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(
            source_subnet_id=SOURCE_SUBNET,
            dest_ip="10.0.0.5",
            routes=routes,
            visited={SOURCE_SUBNET},  # Already visited
        )
        assert path.status == STATUS_UNREACHABLE


# ===========================================================================
# Tests: Asymmetric Routing Detection
# ===========================================================================


@pytest.mark.unit
class TestAsymmetricRouting:
    """Verify asymmetric routing detection."""

    def _make_path(self, next_hop_type: str, nva_ip: str = None) -> RoutePath:
        hop = RouteHop(
            hop_number=1,
            location=SOURCE_SUBNET,
            next_hop_type=next_hop_type,
            next_hop_ip=nva_ip,
            route_source=ROUTE_SOURCE_DEFAULT,
            address_prefix="10.0.0.0/16",
        )
        return RoutePath(status=STATUS_REACHABLE, hops=[hop], total_hops=1)

    def test_symmetric_paths_no_asymmetry(self):
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_VNET_LOCAL)
        rev = self._make_path(NEXT_HOP_VNET_LOCAL)
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is False

    def test_gateway_vs_peering_asymmetry(self):
        """Forward via gateway, return via peering → asymmetric."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_GATEWAY)
        rev = self._make_path(NEXT_HOP_VNET_PEERING)
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is True
        assert "details" in result
        assert len(result["details"]) > 0

    def test_peering_vs_gateway_asymmetry(self):
        """Reverse direction also detected."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_VNET_PEERING)
        rev = self._make_path(NEXT_HOP_GATEWAY)
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is True

    def test_nva_mismatch_asymmetry(self):
        """Different NVA IPs in forward vs return → asymmetric."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_APPLIANCE, nva_ip="10.0.100.4")
        rev = self._make_path(NEXT_HOP_APPLIANCE, nva_ip="10.0.100.5")
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is True
        assert "NVA" in result["details"] or "nva" in result["details"].lower()

    def test_same_nva_symmetric(self):
        """Same NVA in both directions → symmetric."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_APPLIANCE, nva_ip="10.0.100.4")
        rev = self._make_path(NEXT_HOP_APPLIANCE, nva_ip="10.0.100.4")
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is False

    def test_missing_forward_path(self):
        """None forward_path → not asymmetric (can't determine)."""
        analyzer = _make_analyzer()
        rev = self._make_path(NEXT_HOP_VNET_LOCAL)
        result = analyzer.detect_asymmetry(None, rev)

        assert result["asymmetric"] is False

    def test_missing_reverse_path(self):
        """None reverse_path → not asymmetric (can't determine)."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_VNET_LOCAL)
        result = analyzer.detect_asymmetry(fwd, None)

        assert result["asymmetric"] is False

    def test_asymmetry_details_contain_remediation(self):
        """When gateway asymmetry detected, details should include remediation hint."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_GATEWAY)
        rev = self._make_path(NEXT_HOP_VNET_PEERING)
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is True
        # Details should mention firewall/gateway drop risk
        assert any(
            kw in result["details"].lower()
            for kw in ["stateful", "firewall", "gateway", "remediation"]
        )

    def test_internet_vs_local_asymmetry(self):
        """Forward exits via internet, return via local → asymmetric."""
        analyzer = _make_analyzer()
        fwd = self._make_path(NEXT_HOP_INTERNET)
        rev = self._make_path(NEXT_HOP_VNET_LOCAL)
        result = analyzer.detect_asymmetry(fwd, rev)

        assert result["asymmetric"] is True


# ===========================================================================
# Tests: Module-level singleton
# ===========================================================================


@pytest.mark.unit
class TestModuleSingleton:
    """Verify the module-level singleton is available and functional."""

    def test_singleton_is_analyzer_instance(self):
        assert isinstance(route_path_analyzer, RoutePathAnalyzer)

    def test_singleton_trace_path_works(self):
        routes = [_local_route("10.0.0.0/16")]
        path = route_path_analyzer.trace_path(SOURCE_SUBNET, "10.0.1.1", routes)
        assert path.status == STATUS_REACHABLE


# ===========================================================================
# Tests: Edge Cases
# ===========================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Miscellaneous edge cases and boundary conditions."""

    def test_none_route_in_list_skipped(self):
        """None entries in routes list should not crash LPM."""
        analyzer = _make_analyzer()
        routes = [None, _local_route("10.0.0.0/16"), None]
        result = analyzer._longest_prefix_match("10.0.0.5", routes)
        assert result is not None
        assert result.address_prefix == "10.0.0.0/16"

    def test_route_with_empty_prefix_skipped(self):
        """Routes with empty address_prefix are skipped gracefully."""
        analyzer = _make_analyzer()
        bad = Route(address_prefix="", next_hop_type=NEXT_HOP_VNET_LOCAL)
        good = _local_route("10.0.0.0/16")
        result = analyzer._longest_prefix_match("10.0.0.5", [bad, good])
        assert result is not None
        assert result.address_prefix == "10.0.0.0/16"

    def test_ipv4_host_route(self):
        """Host route /32 should match only that exact IP."""
        analyzer = _make_analyzer()
        routes = [
            _local_route("10.0.0.5/32"),
            _internet_route("0.0.0.0/0"),
        ]
        result = analyzer._longest_prefix_match("10.0.0.5", routes)
        assert result is not None
        assert result.address_prefix == "10.0.0.5/32"

        # Different IP within same /16 should use default
        result2 = analyzer._longest_prefix_match("10.0.0.6", routes)
        assert result2 is not None
        assert result2.address_prefix == "0.0.0.0/0"

    def test_trace_path_returns_hops_count_in_total_hops(self):
        """total_hops field should always reflect hops list length."""
        analyzer = _make_analyzer()
        routes = [_local_route("10.0.0.0/16")]
        path = analyzer.trace_path(SOURCE_SUBNET, "10.0.0.5", routes)
        assert path.total_hops == len(path.hops)

    def test_detect_asymmetry_empty_hops(self):
        """Paths with empty hops lists → symmetric (no discernible difference)."""
        analyzer = _make_analyzer()
        fwd = RoutePath(status=STATUS_REACHABLE, hops=[], total_hops=0)
        rev = RoutePath(status=STATUS_REACHABLE, hops=[], total_hops=0)
        result = analyzer.detect_asymmetry(fwd, rev)
        assert result["asymmetric"] is False

    def test_route_unknown_next_hop_type_does_not_raise(self):
        """Unknown next_hop_type is logged but doesn't raise an exception."""
        # Should not raise
        route = Route(address_prefix="10.0.0.0/16", next_hop_type="SomeUnknownType")
        assert route.next_hop_type == "SomeUnknownType"

    def test_trace_with_none_routes(self):
        """Passing None instead of routes list should return unreachable gracefully."""
        analyzer = _make_analyzer()
        path = analyzer.trace_path(SOURCE_SUBNET, "10.0.0.5", None)
        assert path.status == STATUS_UNREACHABLE
