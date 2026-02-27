"""
route_path_analyzer.py - Route Path Tracing and Asymmetric Routing Detection

Provides route path analysis for Azure virtual networks, including:
- Longest Prefix Match (LPM) route resolution
- End-to-end path tracing across VNet peerings and gateways
- Asymmetric routing detection with remediation hints

Usage:
    from app.agentic.eol.utils.route_path_analyzer import RoutePathAnalyzer, Route

    analyzer = RoutePathAnalyzer()
    path = analyzer.trace_path(
        source_subnet_id="/subscriptions/.../subnets/subnet-a",
        dest_ip="10.2.0.5",
        routes=route_list,
        peered_vnets={"10.2.0.0/16": "/subscriptions/.../subnets/subnet-b"}
    )
"""

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HOPS = 10

# Valid next-hop type values
NEXT_HOP_VNET_LOCAL = "VNetLocal"
NEXT_HOP_VNET_PEERING = "VNetPeering"
NEXT_HOP_GATEWAY = "VirtualNetworkGateway"
NEXT_HOP_INTERNET = "Internet"
NEXT_HOP_APPLIANCE = "VirtualAppliance"
NEXT_HOP_NONE = "None"

TERMINAL_HOP_TYPES = {
    NEXT_HOP_VNET_LOCAL,
    NEXT_HOP_GATEWAY,
    NEXT_HOP_INTERNET,
    NEXT_HOP_NONE,
    NEXT_HOP_APPLIANCE,
}

# Route sources
ROUTE_SOURCE_USER = "User"
ROUTE_SOURCE_DEFAULT = "Default"
ROUTE_SOURCE_BGP = "BGP"

# Path status values
STATUS_REACHABLE = "reachable"
STATUS_UNREACHABLE = "unreachable"
STATUS_BLACK_HOLE = "black_hole"
STATUS_INTERNET_EGRESS = "internet_egress"
STATUS_GATEWAY_EGRESS = "gateway_egress"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Route:
    """Represents a single routing table entry in an Azure VNet subnet."""

    address_prefix: str
    next_hop_type: str
    next_hop_ip: Optional[str] = None
    source: str = ROUTE_SOURCE_DEFAULT
    route_table_id: Optional[str] = None

    def __post_init__(self) -> None:
        # Normalize next_hop_type to one of the accepted values
        if self.next_hop_type not in {
            NEXT_HOP_VNET_LOCAL,
            NEXT_HOP_VNET_PEERING,
            NEXT_HOP_GATEWAY,
            NEXT_HOP_INTERNET,
            NEXT_HOP_APPLIANCE,
            NEXT_HOP_NONE,
        }:
            logger.warning(
                "Unknown next_hop_type '%s' for prefix '%s'",
                self.next_hop_type,
                self.address_prefix,
            )


@dataclass
class RouteHop:
    """Represents a single hop in a traced route path."""

    hop_number: int
    location: str  # Subnet ID
    next_hop_type: str
    route_source: str
    address_prefix: str
    next_hop_ip: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "hop_number": self.hop_number,
            "location": self.location,
            "next_hop_type": self.next_hop_type,
            "next_hop_ip": self.next_hop_ip,
            "route_source": self.route_source,
            "address_prefix": self.address_prefix,
        }


@dataclass
class RoutePath:
    """Represents the complete traced path between a source and destination."""

    status: str
    hops: list = field(default_factory=list)
    total_hops: int = 0
    asymmetric: Optional[bool] = None
    asymmetry_details: Optional[str] = None

    def __post_init__(self) -> None:
        if self.total_hops == 0 and self.hops:
            self.total_hops = len(self.hops)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "hops": [h.to_dict() if isinstance(h, RouteHop) else h for h in self.hops],
            "total_hops": self.total_hops,
            "asymmetric": self.asymmetric,
            "asymmetry_details": self.asymmetry_details,
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class RoutePathAnalyzer:
    """
    Analyzes Azure VNet routing to trace end-to-end paths and detect
    asymmetric routing configurations.

    All methods are synchronous (pure logic, no I/O).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trace_path(
        self,
        source_subnet_id: str,
        dest_ip: str,
        routes: list,
        peered_vnets: Optional[dict] = None,
        hop_count: int = 0,
        visited: Optional[set] = None,
    ) -> RoutePath:
        """
        Trace the routing path from source_subnet_id to dest_ip.

        Args:
            source_subnet_id: Azure resource ID of the source subnet.
            dest_ip:          Destination IP address (IPv4 dotted-decimal).
            routes:           List of Route objects applicable to source_subnet_id.
            peered_vnets:     Optional mapping of CIDR prefix → peered subnet ID,
                              used to follow VNetPeering hops.
            hop_count:        Internal recursion depth counter (start at 0).
            visited:          Internal set of already-visited subnet IDs (loop guard).

        Returns:
            RoutePath with status, hops, and asymmetry fields populated.
        """
        if visited is None:
            visited = set()

        if not source_subnet_id or not dest_ip:
            logger.warning("trace_path called with empty source_subnet_id or dest_ip")
            return RoutePath(status=STATUS_UNREACHABLE, hops=[], total_hops=0)

        # Guard: max-hop exceeded
        if hop_count >= MAX_HOPS:
            logger.warning(
                "Max hops (%d) reached; possible routing loop near subnet '%s'",
                MAX_HOPS,
                source_subnet_id,
            )
            return RoutePath(
                status=STATUS_UNREACHABLE,
                hops=[],
                total_hops=hop_count,
            )

        # Guard: loop detection
        if source_subnet_id in visited:
            logger.warning(
                "Loop detected: subnet '%s' already visited in this path",
                source_subnet_id,
            )
            return RoutePath(status=STATUS_UNREACHABLE, hops=[], total_hops=hop_count)

        visited = visited | {source_subnet_id}  # immutable update for recursion safety

        # Validate dest_ip
        try:
            ipaddress.ip_address(dest_ip)
        except ValueError:
            logger.error("Invalid destination IP address: '%s'", dest_ip)
            return RoutePath(status=STATUS_UNREACHABLE, hops=[], total_hops=0)

        # Find best route via LPM
        matched_route = self._longest_prefix_match(dest_ip, routes or [])
        if matched_route is None:
            logger.debug(
                "No matching route found for '%s' at subnet '%s'",
                dest_ip,
                source_subnet_id,
            )
            return RoutePath(status=STATUS_UNREACHABLE, hops=[], total_hops=hop_count)

        current_hop = RouteHop(
            hop_number=hop_count + 1,
            location=source_subnet_id,
            next_hop_type=matched_route.next_hop_type,
            next_hop_ip=matched_route.next_hop_ip,
            route_source=matched_route.source,
            address_prefix=matched_route.address_prefix,
        )

        # --- Terminal conditions -----------------------------------------------

        if matched_route.next_hop_type == NEXT_HOP_NONE:
            logger.debug(
                "Black-hole route matched for '%s' at subnet '%s'",
                dest_ip,
                source_subnet_id,
            )
            return RoutePath(
                status=STATUS_BLACK_HOLE,
                hops=[current_hop],
                total_hops=hop_count + 1,
            )

        if matched_route.next_hop_type == NEXT_HOP_INTERNET:
            logger.debug("Internet egress for '%s'", dest_ip)
            return RoutePath(
                status=STATUS_INTERNET_EGRESS,
                hops=[current_hop],
                total_hops=hop_count + 1,
            )

        if matched_route.next_hop_type == NEXT_HOP_GATEWAY:
            logger.debug("Gateway egress (VPN/ER) for '%s'", dest_ip)
            return RoutePath(
                status=STATUS_GATEWAY_EGRESS,
                hops=[current_hop],
                total_hops=hop_count + 1,
            )

        if matched_route.next_hop_type == NEXT_HOP_VNET_LOCAL:
            logger.debug(
                "Destination '%s' is local to VNet (reachable)", dest_ip
            )
            return RoutePath(
                status=STATUS_REACHABLE,
                hops=[current_hop],
                total_hops=hop_count + 1,
            )

        if matched_route.next_hop_type == NEXT_HOP_APPLIANCE:
            # NVA forwarding — we treat the traffic as reachable with limited visibility
            nva_ip = matched_route.next_hop_ip or "unknown"
            logger.debug(
                "NVA forwarding via '%s' for '%s'; limited path visibility",
                nva_ip,
                dest_ip,
            )
            return RoutePath(
                status=STATUS_REACHABLE,
                hops=[current_hop],
                total_hops=hop_count + 1,
            )

        # --- VNetPeering: recurse into peered VNet ---------------------------

        if matched_route.next_hop_type == NEXT_HOP_VNET_PEERING:
            next_subnet_id = self._resolve_peered_subnet(
                dest_ip, peered_vnets or {}
            )
            if next_subnet_id is None:
                logger.warning(
                    "VNetPeering hop for '%s' but no peered VNet entry found",
                    dest_ip,
                )
                # Still record the hop; treat as reachable since peering exists
                return RoutePath(
                    status=STATUS_REACHABLE,
                    hops=[current_hop],
                    total_hops=hop_count + 1,
                )

            # Recurse into peered subnet using the same route list heuristic.
            # In a real system you'd fetch that subnet's effective routes; here
            # we pass the same routes (caller may provide per-subnet routes).
            deeper = self.trace_path(
                source_subnet_id=next_subnet_id,
                dest_ip=dest_ip,
                routes=routes,
                peered_vnets=peered_vnets,
                hop_count=hop_count + 1,
                visited=visited,
            )

            # If the recursive call cannot determine a deeper path (unreachable due
            # to loop detection or no matching route in the peered context), treat
            # the peering hop itself as reachable — the VNet peering is established
            # and traffic will enter the peered VNet; we just lack deeper route info.
            effective_status = (
                STATUS_REACHABLE
                if deeper.status == STATUS_UNREACHABLE
                else deeper.status
            )
            return RoutePath(
                status=effective_status,
                hops=[current_hop] + deeper.hops,
                total_hops=max(deeper.total_hops, hop_count + 1),
                asymmetric=deeper.asymmetric,
                asymmetry_details=deeper.asymmetry_details,
            )

        # Fallback — unknown next-hop type
        logger.warning(
            "Unhandled next_hop_type '%s'; treating as unreachable",
            matched_route.next_hop_type,
        )
        return RoutePath(
            status=STATUS_UNREACHABLE,
            hops=[current_hop],
            total_hops=hop_count + 1,
        )

    def _longest_prefix_match(self, ip: str, routes: list) -> Optional[Route]:
        """
        Perform Longest Prefix Match (LPM) against a list of Route objects.

        Tie-breaking rules (highest priority wins):
          1. Longer prefix length (more specific route).
          2. User-defined routes beat Default/BGP routes of equal prefix length.

        Args:
            ip:     Destination IPv4 address string.
            routes: List of Route objects to search.

        Returns:
            The best matching Route, or None if no route matches.
        """
        if not ip or not routes:
            return None

        try:
            dest = ipaddress.ip_address(ip)
        except ValueError:
            logger.error("_longest_prefix_match: invalid IP '%s'", ip)
            return None

        best: Optional[Route] = None
        best_prefix_len: int = -1
        best_is_user: bool = False

        for route in routes:
            if not route or not route.address_prefix:
                continue
            try:
                network = ipaddress.ip_network(route.address_prefix, strict=False)
            except ValueError:
                logger.warning(
                    "Skipping malformed address_prefix '%s'", route.address_prefix
                )
                continue

            if dest not in network:
                continue

            prefix_len = network.prefixlen
            is_user = route.source == ROUTE_SOURCE_USER

            # Select if: longer prefix, or same prefix with user-route priority
            if (
                best is None
                or prefix_len > best_prefix_len
                or (prefix_len == best_prefix_len and is_user and not best_is_user)
            ):
                best = route
                best_prefix_len = prefix_len
                best_is_user = is_user

        if best:
            logger.debug(
                "LPM: '%s' matched '%s' (source=%s, prefix_len=%d)",
                ip,
                best.address_prefix,
                best.source,
                best_prefix_len,
            )
        return best

    def detect_asymmetry(
        self, forward_path: RoutePath, reverse_path: RoutePath
    ) -> dict:
        """
        Detect asymmetric routing between a forward and reverse path pair.

        Two paths are considered asymmetric when:
          - The dominant next-hop types differ (e.g., forward via gateway, reverse
            via VNetPeering).
          - Different NVA appliances are traversed in each direction.

        Args:
            forward_path: RoutePath for traffic flowing source → destination.
            reverse_path: RoutePath for traffic flowing destination → source.

        Returns:
            dict with keys:
              - asymmetric (bool): True if asymmetry detected.
              - details (str): Human-readable explanation and remediation hints.
        """
        if not forward_path or not reverse_path:
            return {
                "asymmetric": False,
                "details": "Cannot determine asymmetry: one or both paths are missing.",
            }

        fwd_hops = forward_path.hops or []
        rev_hops = reverse_path.hops or []

        # Gather next-hop types for each direction
        fwd_types = [h.next_hop_type for h in fwd_hops if isinstance(h, RouteHop)]
        rev_types = [h.next_hop_type for h in rev_hops if isinstance(h, RouteHop)]

        # Primary next-hop type (last-hop or most representative)
        fwd_primary = fwd_types[-1] if fwd_types else None
        rev_primary = rev_types[-1] if rev_types else None

        reasons: list = []

        # Check for different terminal next-hop types
        if fwd_primary and rev_primary and fwd_primary != rev_primary:
            reasons.append(
                f"Forward path exits via '{fwd_primary}' "
                f"but return path exits via '{rev_primary}'"
            )

        # Check for NVA mismatch (VirtualAppliance hop IPs differ)
        fwd_nva_ips = {
            h.next_hop_ip
            for h in fwd_hops
            if isinstance(h, RouteHop)
            and h.next_hop_type == NEXT_HOP_APPLIANCE
            and h.next_hop_ip
        }
        rev_nva_ips = {
            h.next_hop_ip
            for h in rev_hops
            if isinstance(h, RouteHop)
            and h.next_hop_type == NEXT_HOP_APPLIANCE
            and h.next_hop_ip
        }

        only_fwd_nva = fwd_nva_ips - rev_nva_ips
        only_rev_nva = rev_nva_ips - fwd_nva_ips

        if only_fwd_nva or only_rev_nva:
            reasons.append(
                f"Different NVAs traversed — "
                f"forward-only: {only_fwd_nva or 'none'}, "
                f"reverse-only: {only_rev_nva or 'none'}"
            )

        # Check for gateway vs peering mismatch (common asymmetry scenario)
        has_gateway_fwd = NEXT_HOP_GATEWAY in fwd_types
        has_gateway_rev = NEXT_HOP_GATEWAY in rev_types
        has_peering_fwd = NEXT_HOP_VNET_PEERING in fwd_types
        has_peering_rev = NEXT_HOP_VNET_PEERING in rev_types

        if has_gateway_fwd and has_peering_rev:
            reasons.append(
                "Forward path uses VirtualNetworkGateway while return path uses "
                "VNetPeering — stateful firewall or gateway may drop return traffic"
            )
        elif has_peering_fwd and has_gateway_rev:
            reasons.append(
                "Forward path uses VNetPeering while return path uses "
                "VirtualNetworkGateway — stateful firewall or gateway may drop return traffic"
            )

        if reasons:
            remediation_hints = self._build_remediation_hints(fwd_types, rev_types)
            details = "; ".join(reasons)
            if remediation_hints:
                details += f". Remediation: {remediation_hints}"
            logger.info("Asymmetric routing detected: %s", details)
            return {"asymmetric": True, "details": details}

        return {
            "asymmetric": False,
            "details": "Forward and return paths use consistent routing.",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_peered_subnet(
        self, dest_ip: str, peered_vnets: dict
    ) -> Optional[str]:
        """
        Given a dest_ip and a mapping of {cidr: subnet_id}, find the
        peered subnet whose CIDR contains dest_ip using LPM.

        Args:
            dest_ip:      Destination IPv4 address.
            peered_vnets: Dict mapping CIDR string → peered subnet resource ID.

        Returns:
            The subnet_id of the most-specific matching peered VNet, or None.
        """
        if not dest_ip or not peered_vnets:
            return None

        try:
            dest = ipaddress.ip_address(dest_ip)
        except ValueError:
            return None

        best_subnet_id: Optional[str] = None
        best_prefix_len: int = -1

        for cidr, subnet_id in peered_vnets.items():
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                logger.warning("Skipping malformed peered VNet CIDR '%s'", cidr)
                continue

            if dest in network and network.prefixlen > best_prefix_len:
                best_prefix_len = network.prefixlen
                best_subnet_id = subnet_id

        return best_subnet_id

    def _build_remediation_hints(
        self, fwd_types: list, rev_types: list
    ) -> str:
        """
        Build actionable remediation hints based on detected asymmetry patterns.

        Args:
            fwd_types: List of next-hop type strings in the forward path.
            rev_types: List of next-hop type strings in the reverse path.

        Returns:
            Remediation hint string, or empty string if no specific hint applies.
        """
        hints: list = []

        gateway_asymmetry = (NEXT_HOP_GATEWAY in fwd_types) != (
            NEXT_HOP_GATEWAY in rev_types
        )
        if gateway_asymmetry:
            hints.append(
                "Review UDR (User-Defined Routes) on both source and destination "
                "subnets to ensure symmetric gateway usage"
            )

        nva_asymmetry = (NEXT_HOP_APPLIANCE in fwd_types) != (
            NEXT_HOP_APPLIANCE in rev_types
        )
        if nva_asymmetry:
            hints.append(
                "Stateful firewall or NVA may drop return traffic; ensure both "
                "directions traverse the same NVA or use stateless inspection"
            )

        if NEXT_HOP_GATEWAY in fwd_types and NEXT_HOP_VNET_PEERING in rev_types:
            hints.append(
                "Check 'Use Remote Gateway' peering flag — mismatched gateway "
                "transit settings can cause asymmetric paths"
            )

        return "; ".join(hints)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

route_path_analyzer = RoutePathAnalyzer()
