"""
Unit Tests – NSG Rule Evaluator

Tests cover:
* Exact IP match
* CIDR range matching
* Service tags (VirtualNetwork, Internet, AzureLoadBalancer, unknown)
* Port ranges ("*", single port, range, comma-separated mix)
* Protocol matching ("*", TCP, UDP, ICMP, case-insensitive)
* Priority ordering (lower number wins)
* Default deny (no matching rule)
* Edge cases: malformed rules, empty list, None/missing fields
* Recommendation generation (over-permissive source, management ports, wildcard protocol)

Run with:
    pytest tests/test_nsg_rule_evaluator.py -v
    pytest tests/test_nsg_rule_evaluator.py -v --tb=short
"""

from __future__ import annotations

import pytest
from typing import List

# ── subject under test ────────────────────────────────────────────────────
from utils.nsg_rule_evaluator import (
    FlowTuple,
    NSGRule,
    NSGRuleEvaluator,
    RuleVerdict,
)


# ── helpers / fixtures ────────────────────────────────────────────────────

def _rule(
    name: str = "test-rule",
    priority: int = 100,
    action: str = "Allow",
    direction: str = "Inbound",
    source: str = "*",
    dest: str = "*",
    port: str = "*",
    protocol: str = "*",
    description: str = None,
) -> NSGRule:
    """Convenience factory for test rules."""
    return NSGRule(
        name=name,
        priority=priority,
        action=action,
        direction=direction,
        source_address_prefix=source,
        dest_address_prefix=dest,
        dest_port_range=port,
        protocol=protocol,
        description=description,
    )


def _flow(
    source_ip: str = "10.1.2.3",
    dest_ip: str = "192.168.1.10",
    dest_port: int = 80,
    protocol: str = "TCP",
    source_port: int = None,
) -> FlowTuple:
    """Convenience factory for test flows."""
    return FlowTuple(
        source_ip=source_ip,
        dest_ip=dest_ip,
        dest_port=dest_port,
        protocol=protocol,
        source_port=source_port,
    )


@pytest.fixture
def ev() -> NSGRuleEvaluator:
    """Shared evaluator instance (stateless – safe to reuse)."""
    return NSGRuleEvaluator()


# ══════════════════════════════════════════════════════════════════════════
# FlowTuple & NSGRule dataclasses
# ══════════════════════════════════════════════════════════════════════════

class TestDataclasses:
    """Sanity checks on FlowTuple and NSGRule construction."""

    def test_flow_tuple_required_fields(self):
        flow = FlowTuple(source_ip="1.2.3.4", dest_ip="5.6.7.8", dest_port=443, protocol="TCP")
        assert flow.source_ip == "1.2.3.4"
        assert flow.dest_ip == "5.6.7.8"
        assert flow.dest_port == 443
        assert flow.protocol == "TCP"
        assert flow.source_port is None  # optional default

    def test_flow_tuple_optional_source_port(self):
        flow = FlowTuple(source_ip="1.2.3.4", dest_ip="5.6.7.8", dest_port=80, protocol="TCP", source_port=12345)
        assert flow.source_port == 12345

    def test_nsg_rule_required_fields(self):
        rule = _rule()
        assert rule.name == "test-rule"
        assert rule.priority == 100
        assert rule.action == "Allow"
        assert rule.direction == "Inbound"
        assert rule.description is None  # optional default

    def test_rule_verdict_defaults(self):
        verdict = RuleVerdict(action="DefaultDeny")
        assert verdict.matched_rule is None
        assert verdict.evaluation_chain == []
        assert verdict.recommendations == []


# ══════════════════════════════════════════════════════════════════════════
# IP matching – _ip_matches_prefix
# ══════════════════════════════════════════════════════════════════════════

class TestIPMatchesPrefix:
    """Unit tests for _ip_matches_prefix."""

    def test_wildcard_matches_any_ip(self, ev):
        assert ev._ip_matches_prefix("1.2.3.4", "*") is True
        assert ev._ip_matches_prefix("0.0.0.0", "*") is True

    def test_exact_ip_match(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "10.1.2.3") is True

    def test_exact_ip_no_match(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "10.1.2.4") is False

    def test_cidr_match_host_in_range(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "10.0.0.0/8") is True
        assert ev._ip_matches_prefix("172.16.0.1", "172.16.0.0/12") is True
        assert ev._ip_matches_prefix("192.168.5.99", "192.168.5.0/24") is True

    def test_cidr_no_match_host_outside_range(self, ev):
        assert ev._ip_matches_prefix("11.0.0.1", "10.0.0.0/8") is False
        assert ev._ip_matches_prefix("192.168.6.1", "192.168.5.0/24") is False

    def test_cidr_slash32_exact_match(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "10.1.2.3/32") is True
        assert ev._ip_matches_prefix("10.1.2.4", "10.1.2.3/32") is False

    # --- Service tags ---

    def test_virtualnetwork_tag_private_ip(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "VirtualNetwork") is True
        assert ev._ip_matches_prefix("172.20.0.5", "VirtualNetwork") is True
        assert ev._ip_matches_prefix("192.168.0.1", "VirtualNetwork") is True

    def test_virtualnetwork_tag_public_ip(self, ev):
        assert ev._ip_matches_prefix("8.8.8.8", "VirtualNetwork") is False
        assert ev._ip_matches_prefix("52.1.2.3", "VirtualNetwork") is False

    def test_internet_tag_public_ip(self, ev):
        assert ev._ip_matches_prefix("8.8.8.8", "Internet") is True
        assert ev._ip_matches_prefix("52.1.2.3", "Internet") is True

    def test_internet_tag_private_ip(self, ev):
        assert ev._ip_matches_prefix("10.0.0.1", "Internet") is False
        assert ev._ip_matches_prefix("192.168.1.1", "Internet") is False

    def test_azure_load_balancer_tag(self, ev):
        assert ev._ip_matches_prefix("168.63.129.16", "AzureLoadBalancer") is True
        assert ev._ip_matches_prefix("10.1.2.3", "AzureLoadBalancer") is False

    def test_unknown_service_tag_returns_false(self, ev):
        # Conservative: unknown tag → no match
        assert ev._ip_matches_prefix("10.1.2.3", "SqlManagement") is False
        assert ev._ip_matches_prefix("10.1.2.3", "Storage.EastUS") is False

    def test_empty_ip_returns_false(self, ev):
        assert ev._ip_matches_prefix("", "10.0.0.0/8") is False

    def test_empty_prefix_returns_false(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "") is False

    def test_malformed_cidr_returns_false(self, ev):
        assert ev._ip_matches_prefix("10.1.2.3", "not_a_cidr") is False


# ══════════════════════════════════════════════════════════════════════════
# Port range matching – _port_in_range
# ══════════════════════════════════════════════════════════════════════════

class TestPortInRange:
    """Unit tests for _port_in_range."""

    def test_wildcard_matches_any_port(self, ev):
        assert ev._port_in_range(80, "*") is True
        assert ev._port_in_range(0, "*") is True
        assert ev._port_in_range(65535, "*") is True

    def test_exact_port_match(self, ev):
        assert ev._port_in_range(443, "443") is True

    def test_exact_port_no_match(self, ev):
        assert ev._port_in_range(80, "443") is False

    def test_range_inclusive_low(self, ev):
        assert ev._port_in_range(8000, "8000-9000") is True

    def test_range_inclusive_high(self, ev):
        assert ev._port_in_range(9000, "8000-9000") is True

    def test_range_middle(self, ev):
        assert ev._port_in_range(8500, "8000-9000") is True

    def test_range_below_low(self, ev):
        assert ev._port_in_range(7999, "8000-9000") is False

    def test_range_above_high(self, ev):
        assert ev._port_in_range(9001, "8000-9000") is False

    def test_comma_separated_single_ports(self, ev):
        assert ev._port_in_range(22, "22,80,443") is True
        assert ev._port_in_range(80, "22,80,443") is True
        assert ev._port_in_range(443, "22,80,443") is True
        assert ev._port_in_range(8080, "22,80,443") is False

    def test_comma_separated_mixed(self, ev):
        assert ev._port_in_range(22, "22-23,80,443") is True
        assert ev._port_in_range(23, "22-23,80,443") is True
        assert ev._port_in_range(80, "22-23,80,443") is True
        assert ev._port_in_range(443, "22-23,80,443") is True
        assert ev._port_in_range(24, "22-23,80,443") is False

    def test_empty_range_returns_false(self, ev):
        assert ev._port_in_range(80, "") is False

    def test_malformed_range_segment_skipped(self, ev):
        # Malformed segment "abc" is skipped; valid "80" should still match
        assert ev._port_in_range(80, "abc,80") is True
        # Completely malformed – should return False without crashing
        assert ev._port_in_range(80, "abc-xyz") is False

    def test_invalid_port_value_returns_false(self, ev):
        assert ev._port_in_range(-1, "80") is False
        assert ev._port_in_range(70000, "70000") is False


# ══════════════════════════════════════════════════════════════════════════
# Protocol matching – _protocol_matches
# ══════════════════════════════════════════════════════════════════════════

class TestProtocolMatches:
    """Unit tests for _protocol_matches."""

    def test_wildcard_matches_tcp(self, ev):
        assert ev._protocol_matches("TCP", "*") is True

    def test_wildcard_matches_udp(self, ev):
        assert ev._protocol_matches("UDP", "*") is True

    def test_wildcard_matches_icmp(self, ev):
        assert ev._protocol_matches("ICMP", "*") is True

    def test_exact_tcp_match(self, ev):
        assert ev._protocol_matches("TCP", "TCP") is True

    def test_exact_udp_match(self, ev):
        assert ev._protocol_matches("UDP", "UDP") is True

    def test_exact_icmp_match(self, ev):
        assert ev._protocol_matches("ICMP", "ICMP") is True

    def test_case_insensitive(self, ev):
        assert ev._protocol_matches("tcp", "TCP") is True
        assert ev._protocol_matches("TCP", "tcp") is True
        assert ev._protocol_matches("Tcp", "tCp") is True

    def test_mismatch_tcp_vs_udp(self, ev):
        assert ev._protocol_matches("TCP", "UDP") is False

    def test_mismatch_udp_vs_icmp(self, ev):
        assert ev._protocol_matches("UDP", "ICMP") is False

    def test_empty_flow_protocol_returns_false(self, ev):
        assert ev._protocol_matches("", "TCP") is False

    def test_empty_rule_protocol_returns_false(self, ev):
        assert ev._protocol_matches("TCP", "") is False

    def test_none_values_return_false(self, ev):
        # Protocol fields should never be None in practice; guard anyway
        assert ev._protocol_matches(None, "TCP") is False
        assert ev._protocol_matches("TCP", None) is False


# ══════════════════════════════════════════════════════════════════════════
# Priority ordering
# ══════════════════════════════════════════════════════════════════════════

class TestPriorityOrdering:
    """Lower priority number (higher precedence) wins."""

    def test_lower_priority_allow_overrides_higher_deny(self, ev):
        rules = [
            _rule("deny-all", priority=200, action="Deny", port="80"),
            _rule("allow-http", priority=100, action="Allow", port="80"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        assert verdict.action == "Allow"
        assert verdict.matched_rule.name == "allow-http"

    def test_lower_priority_deny_overrides_higher_allow(self, ev):
        rules = [
            _rule("deny-http", priority=100, action="Deny", port="80"),
            _rule("allow-http", priority=200, action="Allow", port="80"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        assert verdict.action == "Deny"
        assert verdict.matched_rule.name == "deny-http"

    def test_multiple_matching_rules_first_wins(self, ev):
        rules = [
            _rule("rule-a", priority=110, action="Deny", port="443"),
            _rule("rule-b", priority=100, action="Allow", port="443"),
            _rule("rule-c", priority=120, action="Deny", port="443"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=443))
        assert verdict.action == "Allow"
        assert verdict.matched_rule.name == "rule-b"

    def test_evaluation_chain_ordered_by_priority(self, ev):
        rules = [
            _rule("rule-300", priority=300, action="Allow", port="80"),
            _rule("rule-100", priority=100, action="Allow", port="80"),
            _rule("rule-200", priority=200, action="Deny", port="80"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        priorities_in_chain = [e["priority"] for e in verdict.evaluation_chain]
        assert priorities_in_chain == sorted(priorities_in_chain)


# ══════════════════════════════════════════════════════════════════════════
# evaluate_flow – integration scenarios
# ══════════════════════════════════════════════════════════════════════════

class TestEvaluateFlow:
    """Full evaluate_flow integration tests."""

    def test_exact_ip_match_allow(self, ev):
        rules = [_rule(source="10.1.2.3", port="80", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.1.2.3", dest_port=80))
        assert verdict.action == "Allow"

    def test_exact_ip_no_match_default_deny(self, ev):
        rules = [_rule(source="10.1.2.3", port="80", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.1.2.4", dest_port=80))
        assert verdict.action == "DefaultDeny"
        assert verdict.matched_rule is None

    def test_cidr_allow(self, ev):
        rules = [_rule(source="10.0.0.0/8", port="443", action="Allow", protocol="TCP")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.5.6.7", dest_port=443, protocol="TCP"))
        assert verdict.action == "Allow"

    def test_cidr_deny(self, ev):
        rules = [_rule(source="10.0.0.0/8", port="443", action="Deny", protocol="TCP")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.5.6.7", dest_port=443, protocol="TCP"))
        assert verdict.action == "Deny"

    def test_default_deny_when_no_rules(self, ev):
        verdict = ev.evaluate_flow([], _flow())
        assert verdict.action == "DefaultDeny"
        assert verdict.matched_rule is None
        assert verdict.evaluation_chain == []

    def test_direction_filter_inbound(self, ev):
        """Outbound rules must not affect Inbound evaluation."""
        rules = [
            _rule("outbound-deny", direction="Outbound", action="Deny"),
            _rule("inbound-allow", direction="Inbound", action="Allow"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(), direction="Inbound")
        assert verdict.action == "Allow"
        assert verdict.matched_rule.name == "inbound-allow"

    def test_direction_filter_outbound(self, ev):
        """Inbound rules must not affect Outbound evaluation."""
        rules = [
            _rule("inbound-allow", direction="Inbound", action="Allow"),
            _rule("outbound-deny", direction="Outbound", action="Deny"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(), direction="Outbound")
        assert verdict.action == "Deny"
        assert verdict.matched_rule.name == "outbound-deny"

    def test_case_insensitive_direction(self, ev):
        rules = [_rule("allow-all", direction="Inbound", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(), direction="inbound")
        assert verdict.action == "Allow"

    def test_evaluation_chain_records_all_evaluated_rules(self, ev):
        rules = [
            _rule("rule-100", priority=100, action="Allow", port="443"),
            _rule("rule-200", priority=200, action="Allow", port="80"),
        ]
        # Port 80 – rule-100 won't match (port=443), rule-200 will match
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        assert len(verdict.evaluation_chain) == 2
        names = [e["rule_name"] for e in verdict.evaluation_chain]
        assert "rule-100" in names
        assert "rule-200" in names
        # Only rule-200 matched
        chain_by_name = {e["rule_name"]: e for e in verdict.evaluation_chain}
        assert chain_by_name["rule-100"]["matched"] is False
        assert chain_by_name["rule-200"]["matched"] is True

    def test_evaluation_chain_stops_at_first_match(self, ev):
        rules = [
            _rule("rule-100", priority=100, action="Allow", port="80"),
            _rule("rule-200", priority=200, action="Deny", port="80"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        # Chain should stop at first match (rule-100); rule-200 never evaluated
        assert len(verdict.evaluation_chain) == 1
        assert verdict.evaluation_chain[0]["rule_name"] == "rule-100"

    def test_virtualnetwork_source_tag(self, ev):
        rules = [_rule(source="VirtualNetwork", port="443", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="192.168.10.5", dest_port=443))
        assert verdict.action == "Allow"

    def test_internet_source_tag_blocks_private_ip(self, ev):
        """If source tag is Internet, a private-IP source won't match the rule → DefaultDeny."""
        rules = [_rule(source="Internet", port="80", action="Deny")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.0.0.1", dest_port=80))
        assert verdict.action == "DefaultDeny"

    def test_none_rules_list_returns_default_deny(self, ev):
        verdict = ev.evaluate_flow(None, _flow())
        assert verdict.action == "DefaultDeny"

    def test_verdict_has_matched_rule_reference(self, ev):
        rule = _rule("named-rule", priority=100, action="Allow")
        verdict = ev.evaluate_flow([rule], _flow())
        assert verdict.matched_rule is rule


# ══════════════════════════════════════════════════════════════════════════
# Recommendation generation
# ══════════════════════════════════════════════════════════════════════════

class TestRecommendations:
    """Tests for _generate_recommendations and verify they surface in evaluate_flow."""

    def test_no_recommendations_for_deny_verdict(self, ev):
        rules = [_rule("deny-all", action="Deny")]
        verdict = ev.evaluate_flow(rules, _flow())
        assert verdict.recommendations == []

    def test_no_recommendations_for_default_deny(self, ev):
        verdict = ev.evaluate_flow([], _flow())
        assert verdict.recommendations == []

    def test_over_permissive_wildcard_source(self, ev):
        rules = [_rule("allow-all", source="*", action="Allow", port="80")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80))
        assert any("Restrict source" in r for r in verdict.recommendations)

    def test_over_permissive_cidr_all(self, ev):
        rules = [_rule("allow-all-cidr", source="0.0.0.0/0", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow())
        assert any("Restrict source" in r for r in verdict.recommendations)

    def test_over_permissive_internet_tag(self, ev):
        rules = [_rule("allow-internet", source="Internet", action="Allow")]
        # Public IP source to trigger Internet tag match
        verdict = ev.evaluate_flow(rules, _flow(source_ip="8.8.8.8"))
        assert any("Restrict source" in r for r in verdict.recommendations)

    def test_ssh_port_recommendation(self, ev):
        rules = [_rule("allow-ssh", source="*", port="22", action="Allow", protocol="TCP")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=22, protocol="TCP"))
        assert any("22" in r and "JIT" in r for r in verdict.recommendations)

    def test_rdp_port_recommendation(self, ev):
        rules = [_rule("allow-rdp", source="*", port="3389", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=3389))
        assert any("3389" in r for r in verdict.recommendations)

    def test_winrm_port_recommendation(self, ev):
        rules = [_rule("allow-winrm", source="*", port="5985", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=5985))
        assert any("5985" in r for r in verdict.recommendations)

    def test_winrm_https_port_recommendation(self, ev):
        rules = [_rule("allow-winrm-https", source="*", port="5986", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=5986))
        assert any("5986" in r for r in verdict.recommendations)

    def test_wildcard_protocol_recommendation(self, ev):
        rules = [_rule("allow-any-proto", source="*", protocol="*", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow())
        assert any("wildcard protocol" in r.lower() or "explicit protocols" in r.lower()
                   for r in verdict.recommendations)

    def test_non_management_port_no_port_rec(self, ev):
        rules = [_rule("allow-https", source="10.0.0.0/8", port="443", action="Allow", protocol="TCP")]
        verdict = ev.evaluate_flow(rules, _flow(source_ip="10.1.2.3", dest_port=443, protocol="TCP"))
        # No management port recommendation
        assert not any("JIT" in r for r in verdict.recommendations)

    def test_multiple_recommendations_combined(self, ev):
        """Wildcard source + management port + wildcard protocol → 3 recommendations."""
        rules = [_rule("over-permissive", source="*", port="22", protocol="*", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=22))
        assert len(verdict.recommendations) >= 3


# ══════════════════════════════════════════════════════════════════════════
# Edge cases / robustness
# ══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Robustness – malformed input should not crash the evaluator."""

    def test_malformed_rule_does_not_crash(self, ev):
        """A rule with an unparseable CIDR should be skipped (no match), not raise."""
        bad_rule = NSGRule(
            name="bad-rule",
            priority=100,
            action="Allow",
            direction="Inbound",
            source_address_prefix="not_an_ip",
            dest_address_prefix="*",
            dest_port_range="80",
            protocol="TCP",
        )
        verdict = ev.evaluate_flow([bad_rule], _flow(dest_port=80, protocol="TCP"))
        # Malformed source → no match → DefaultDeny
        assert verdict.action == "DefaultDeny"

    def test_empty_port_range_no_match(self, ev):
        rule = _rule(port="")
        verdict = ev.evaluate_flow([rule], _flow(dest_port=80))
        assert verdict.action == "DefaultDeny"

    def test_malformed_port_range_skipped(self, ev):
        rule = _rule(port="abc-xyz")
        verdict = ev.evaluate_flow([rule], _flow(dest_port=80))
        assert verdict.action == "DefaultDeny"

    def test_empty_protocol_no_match(self, ev):
        rule = _rule(protocol="")
        verdict = ev.evaluate_flow([rule], _flow(protocol="TCP"))
        assert verdict.action == "DefaultDeny"

    def test_rules_with_mixed_directions_only_inbound_evaluated(self, ev):
        rules = [
            _rule("outbound-allow", direction="Outbound", action="Allow"),
        ]
        verdict = ev.evaluate_flow(rules, _flow(), direction="Inbound")
        assert verdict.action == "DefaultDeny"

    def test_single_allow_all_rule(self, ev):
        rules = [_rule("allow-all", source="*", dest="*", port="*", protocol="*", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow())
        assert verdict.action == "Allow"

    def test_single_deny_all_rule(self, ev):
        rules = [_rule("deny-all", source="*", dest="*", port="*", protocol="*", action="Deny")]
        verdict = ev.evaluate_flow(rules, _flow())
        assert verdict.action == "Deny"

    def test_many_non_matching_rules_returns_default_deny(self, ev):
        rules = [_rule(f"rule-{i}", priority=i * 100, port=str(i + 1)) for i in range(1, 10)]
        # Flow port 9999 matches none of the rules
        verdict = ev.evaluate_flow(rules, _flow(dest_port=9999))
        assert verdict.action == "DefaultDeny"
        assert len(verdict.evaluation_chain) == len(rules)

    def test_evaluation_chain_contains_rule_name_priority_action_matched(self, ev):
        rule = _rule("test-rule", priority=100, action="Allow")
        verdict = ev.evaluate_flow([rule], _flow())
        assert len(verdict.evaluation_chain) == 1
        entry = verdict.evaluation_chain[0]
        assert "rule_name" in entry
        assert "priority" in entry
        assert "action" in entry
        assert "matched" in entry

    def test_protocol_case_insensitive_in_flow(self, ev):
        rules = [_rule(protocol="TCP", port="80", action="Allow")]
        verdict = ev.evaluate_flow(rules, _flow(dest_port=80, protocol="tcp"))
        assert verdict.action == "Allow"

    def test_direction_case_insensitive_rule(self, ev):
        """Rules with mixed-case direction should still be picked up."""
        rule = NSGRule(
            name="mixed-case-dir",
            priority=100,
            action="Allow",
            direction="INBOUND",
            source_address_prefix="*",
            dest_address_prefix="*",
            dest_port_range="*",
            protocol="*",
        )
        verdict = ev.evaluate_flow([rule], _flow(), direction="Inbound")
        assert verdict.action == "Allow"

    def test_azure_loadbalancer_probe_allowed(self, ev):
        rules = [_rule("allow-alb", source="AzureLoadBalancer", port="80", action="Allow")]
        flow = _flow(source_ip="168.63.129.16", dest_port=80)
        verdict = ev.evaluate_flow(rules, flow)
        assert verdict.action == "Allow"

    def test_azure_loadbalancer_non_probe_denied(self, ev):
        rules = [_rule("allow-alb", source="AzureLoadBalancer", port="80", action="Allow")]
        flow = _flow(source_ip="10.1.2.3", dest_port=80)
        verdict = ev.evaluate_flow(rules, flow)
        assert verdict.action == "DefaultDeny"
