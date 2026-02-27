"""
NSG Rule Evaluator - Core Logic

Evaluates Azure Network Security Group (NSG) rules against network flows to
determine whether traffic should be allowed or denied.  Pure Python / no I/O;
all Azure API calls live in the callers (agents / MCP servers).

Key components
--------------
* ``FlowTuple``     – describes the 5-tuple of a single network packet/flow
* ``NSGRule``       – a parsed NSG security rule (matches Azure REST shape)
* ``RuleVerdict``   – the evaluation result, including audit trail and advice

Usage example
-------------
    >>> from utils.nsg_rule_evaluator import NSGRuleEvaluator, FlowTuple, NSGRule
    >>> evaluator = NSGRuleEvaluator()
    >>> rules = [
    ...     NSGRule(
    ...         name="allow-https",
    ...         priority=100,
    ...         action="Allow",
    ...         direction="Inbound",
    ...         source_address_prefix="10.0.0.0/8",
    ...         dest_address_prefix="*",
    ...         dest_port_range="443",
    ...         protocol="TCP",
    ...     )
    ... ]
    >>> flow = FlowTuple(source_ip="10.1.2.3", dest_ip="192.168.1.5", dest_port=443, protocol="TCP")
    >>> verdict = evaluator.evaluate_flow(rules, flow)
    >>> verdict.action
    'Allow'

See ``tests/test_nsg_rule_evaluator.py`` for comprehensive test coverage.

Created: 2026-02-27 (Network Agent Enhancement)
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Management ports that warrant a JIT / hardening recommendation
# ---------------------------------------------------------------------------
_MANAGEMENT_PORTS: frozenset[int] = frozenset({22, 3389, 5985, 5986})

# ---------------------------------------------------------------------------
# RFC-1918 private address space used by the VirtualNetwork service tag
# ---------------------------------------------------------------------------
_PRIVATE_NETWORKS: list[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
]

# Azure Load Balancer probe source
_AZURE_LOAD_BALANCER_IP = "168.63.129.16"


# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------

@dataclass
class FlowTuple:
    """
    Describes a single network flow (packet 5-tuple).

    Attributes
    ----------
    source_ip:   Source IP address (dotted-decimal, e.g. "10.1.2.3").
    dest_ip:     Destination IP address.
    dest_port:   Destination TCP/UDP port (1-65535).
    protocol:    Transport protocol – "TCP", "UDP", or "ICMP".
    source_port: Optional source port; rarely used in NSG matching.
    """

    source_ip: str
    dest_ip: str
    dest_port: int
    protocol: str
    source_port: Optional[int] = None


@dataclass
class NSGRule:
    """
    Represents a parsed Azure NSG security rule.

    Attributes match Azure's ``securityRules`` REST resource properties.

    Attributes
    ----------
    name:                    Rule name (unique within an NSG direction).
    priority:                Evaluation order – lower number evaluated first (100-4096).
    action:                  "Allow" or "Deny".
    direction:               "Inbound" or "Outbound".
    source_address_prefix:   Source CIDR, "*", or service tag.
    dest_address_prefix:     Destination CIDR, "*", or service tag.
    dest_port_range:         Port spec: "*", "80", "8000-9000", or comma-separated list.
    protocol:                "TCP", "UDP", "ICMP", or "*".
    description:             Optional human-readable comment.
    """

    name: str
    priority: int
    action: str                    # "Allow" | "Deny"
    direction: str                 # "Inbound" | "Outbound"
    source_address_prefix: str
    dest_address_prefix: str
    dest_port_range: str
    protocol: str
    description: Optional[str] = None


@dataclass
class RuleVerdict:
    """
    Outcome of evaluating a flow against an ordered list of NSG rules.

    Attributes
    ----------
    action:           "Allow", "Deny", or "DefaultDeny" (implicit deny when no rule matched).
    matched_rule:     The first rule that matched, or ``None`` if no match (DefaultDeny).
    evaluation_chain: Ordered list of dicts describing every rule that was evaluated
                      before a decision was reached. Each dict contains:
                      ``rule_name``, ``priority``, ``action``, ``matched`` (bool).
    recommendations: Actionable security recommendations based on the evaluation.
    """

    action: str                                   # "Allow" | "Deny" | "DefaultDeny"
    matched_rule: Optional[NSGRule] = None
    evaluation_chain: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class NSGRuleEvaluator:
    """
    Stateless evaluator that determines flow disposition against NSG rules.

    All methods are synchronous (no I/O); callers own async boundaries.

    Example
    -------
    >>> ev = NSGRuleEvaluator()
    >>> verdict = ev.evaluate_flow(rules, flow, direction="Inbound")
    >>> print(verdict.action, verdict.matched_rule)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_flow(
        self,
        rules: List[NSGRule],
        flow: FlowTuple,
        direction: str = "Inbound",
    ) -> RuleVerdict:
        """
        Evaluate a network flow against an ordered list of NSG rules.

        Azure NSG rule matching algorithm:
        1. Filter rules to the requested ``direction``.
        2. Sort by ``priority`` ascending (lower number = higher precedence).
        3. Walk rules in order; return the action of the first match.
        4. If no rule matches, return "DefaultDeny" (Azure implicit deny).

        Parameters
        ----------
        rules:     All security rules for the NSG (both directions acceptable).
        flow:      The 5-tuple describing the traffic to evaluate.
        direction: "Inbound" or "Outbound" (case-insensitive).

        Returns
        -------
        RuleVerdict with action, matched rule, full evaluation chain, and
        security recommendations.
        """
        direction_norm = direction.strip().capitalize()  # "Inbound" / "Outbound"

        # Filter to the right direction
        directional_rules = [
            r for r in (rules or [])
            if r.direction.strip().capitalize() == direction_norm
        ]

        # Sort by priority ascending
        sorted_rules = sorted(directional_rules, key=lambda r: r.priority)

        evaluation_chain: List[Dict[str, Any]] = []
        matched_rule: Optional[NSGRule] = None

        for rule in sorted_rules:
            matched = self._match_rule(rule, flow)
            evaluation_chain.append(
                {
                    "rule_name": rule.name,
                    "priority": rule.priority,
                    "action": rule.action,
                    "matched": matched,
                }
            )
            if matched:
                matched_rule = rule
                break  # First match wins

        if matched_rule is not None:
            action = matched_rule.action.strip().capitalize()
        else:
            action = "DefaultDeny"

        recommendations = self._generate_recommendations(
            matched_rule=matched_rule,
            flow=flow,
            action=action,
        )

        return RuleVerdict(
            action=action,
            matched_rule=matched_rule,
            evaluation_chain=evaluation_chain,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Rule-level matching
    # ------------------------------------------------------------------

    def _match_rule(self, rule: NSGRule, flow: FlowTuple) -> bool:
        """
        Return True if *rule* matches the supplied *flow*.

        Checks (all must pass):
        * Source IP vs rule source_address_prefix
        * Destination IP vs rule dest_address_prefix
        * Destination port vs rule dest_port_range
        * Protocol vs rule protocol
        """
        try:
            if not self._ip_matches_prefix(flow.source_ip, rule.source_address_prefix):
                return False
            if not self._ip_matches_prefix(flow.dest_ip, rule.dest_address_prefix):
                return False
            if not self._port_in_range(flow.dest_port, rule.dest_port_range):
                return False
            if not self._protocol_matches(flow.protocol, rule.protocol):
                return False
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Error matching rule '%s' against flow %s->%s:%s: %s",
                rule.name,
                flow.source_ip,
                flow.dest_ip,
                flow.dest_port,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # IP / prefix matching
    # ------------------------------------------------------------------

    def _ip_matches_prefix(self, ip: str, prefix: str) -> bool:
        """
        Determine whether *ip* is covered by *prefix*.

        Supported prefix forms
        ----------------------
        * ``"*"``                   – matches every address
        * CIDR notation             – e.g. ``"10.0.0.0/8"``
        * Single IP                 – e.g. ``"10.1.2.3"`` (treated as /32)
        * Service tags              – ``"VirtualNetwork"``, ``"Internet"``,
                                       ``"AzureLoadBalancer"``

        Unknown service tags log a warning and return ``False`` (conservative).
        """
        if not ip or not prefix:
            logger.debug("_ip_matches_prefix called with empty ip=%r or prefix=%r", ip, prefix)
            return False

        prefix_stripped = prefix.strip()
        ip_stripped = ip.strip()

        # Wildcard
        if prefix_stripped == "*":
            return True

        # Service tags (case-insensitive comparison)
        prefix_lower = prefix_stripped.lower()
        if not self._looks_like_cidr_or_ip(prefix_stripped):
            return self._service_tag_matches(ip_stripped, prefix_stripped, prefix_lower)

        # CIDR or single IP
        try:
            network = ipaddress.IPv4Network(prefix_stripped, strict=False)
            addr = ipaddress.IPv4Address(ip_stripped)
            return addr in network
        except ValueError:
            logger.warning(
                "Cannot parse prefix '%s' as CIDR; treating as no-match.", prefix_stripped
            )
            return False

    def _service_tag_matches(self, ip: str, prefix: str, prefix_lower: str) -> bool:
        """Resolve Azure service tags to boolean match for *ip*."""
        if prefix_lower == "virtualnetwork":
            return self._is_private_ip(ip)

        if prefix_lower == "internet":
            return not self._is_private_ip(ip)

        if prefix_lower == "azureloadbalancer":
            return ip == _AZURE_LOAD_BALANCER_IP

        # Unknown service tag – log and treat conservatively (no match)
        logger.warning(
            "Unrecognised service tag '%s'; treating as no-match for conservative evaluation.",
            prefix,
        )
        return False

    @staticmethod
    def _looks_like_cidr_or_ip(value: str) -> bool:
        """Return True if *value* looks like an IP address or CIDR (not a service tag)."""
        return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$", value))

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        """Return True if *ip* falls within any RFC-1918 private network."""
        try:
            addr = ipaddress.IPv4Address(ip.strip())
            return any(addr in net for net in _PRIVATE_NETWORKS)
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Port range matching
    # ------------------------------------------------------------------

    def _port_in_range(self, port: int, range_str: str) -> bool:
        """
        Return True if *port* is covered by *range_str*.

        Supported forms
        ---------------
        * ``"*"``          – matches any port
        * ``"443"``        – exact port
        * ``"8000-9000"``  – inclusive range
        * ``"22-23,80,443"`` – comma-separated mix of single ports and ranges

        Invalid port numbers or range strings log a warning and return False.
        """
        if not range_str:
            return False

        range_stripped = range_str.strip()

        if range_stripped == "*":
            return True

        if not isinstance(port, int) or not (0 <= port <= 65535):
            logger.warning("Invalid port value: %r", port)
            return False

        # Handle comma-separated segments
        segments = [s.strip() for s in range_stripped.split(",")]
        for segment in segments:
            if not segment:
                continue
            if "-" in segment:
                # Range like "8000-9000"
                parts = segment.split("-", 1)
                try:
                    low = int(parts[0].strip())
                    high = int(parts[1].strip())
                    if low <= port <= high:
                        return True
                except (ValueError, IndexError):
                    logger.warning("Malformed port range segment: '%s'", segment)
                    continue
            else:
                # Single port
                try:
                    if int(segment) == port:
                        return True
                except ValueError:
                    logger.warning("Malformed port value: '%s'", segment)
                    continue

        return False

    # ------------------------------------------------------------------
    # Protocol matching
    # ------------------------------------------------------------------

    @staticmethod
    def _protocol_matches(flow_protocol: str, rule_protocol: str) -> bool:
        """
        Return True if *flow_protocol* is covered by *rule_protocol*.

        ``"*"`` in the rule matches any protocol.
        Comparison is case-insensitive (e.g. "tcp" == "TCP").
        Empty/None values on either side return False.
        """
        if not flow_protocol or not rule_protocol:
            logger.debug(
                "_protocol_matches: empty protocol flow=%r rule=%r", flow_protocol, rule_protocol
            )
            return False

        if rule_protocol.strip() == "*":
            return True

        return flow_protocol.strip().upper() == rule_protocol.strip().upper()

    # ------------------------------------------------------------------
    # Recommendation generation
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self,
        matched_rule: Optional[NSGRule],
        flow: FlowTuple,
        action: str,
    ) -> List[str]:
        """
        Return a list of actionable security recommendations for the verdict.

        Checks performed
        ----------------
        * Over-permissive source (0.0.0.0/0) on an Allow rule
        * Management port exposure (SSH, RDP, WinRM) on an Allow rule
        * Wildcard protocol on an Allow rule
        * DefaultDeny with no explicit deny rule (informational)
        """
        recs: List[str] = []

        if matched_rule is None:
            # DefaultDeny – traffic blocked by implicit rule, no rule to harden
            return recs

        if action != "Allow":
            # Deny rules are fine; no hardening recommendations needed
            return recs

        # --- Over-permissive source ---
        source = (matched_rule.source_address_prefix or "").strip()
        if source in ("*", "0.0.0.0/0", "Internet"):
            recs.append(
                "Restrict source to specific IP ranges rather than allowing all traffic "
                f"(current source: '{source}' on rule '{matched_rule.name}')."
            )

        # --- Management port exposure ---
        if flow.dest_port in _MANAGEMENT_PORTS:
            recs.append(
                f"Management port {flow.dest_port} is publicly reachable via "
                f"rule '{matched_rule.name}'. "
                "Consider using Just-In-Time (JIT) VM access or Azure Bastion instead."
            )

        # --- Wildcard protocol ---
        if (matched_rule.protocol or "").strip() == "*":
            recs.append(
                f"Rule '{matched_rule.name}' uses a wildcard protocol ('*'). "
                "Specify explicit protocols (TCP/UDP/ICMP) to reduce attack surface."
            )

        return recs
