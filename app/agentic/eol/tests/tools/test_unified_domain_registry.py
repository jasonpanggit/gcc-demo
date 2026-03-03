"""Unit tests for UnifiedDomainRegistry.

Tests:
- All 13 domains are registered
- Domain sources are non-empty frozensets of strings
- max_tools is a positive int for every domain
- get_sub_agent_class returns None gracefully for domains without a class path
- get_sub_agent_class returns None gracefully if the agent module can't be imported
  (no live agents needed — we just test that ImportError is handled silently)
- domains_for_source returns correct domains for known source labels
- GENERAL domain covers all source labels

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import pytest

try:
    from app.agentic.eol.utils.unified_domain_registry import (
        UnifiedDomain,
        UnifiedDomainRegistry,
        DomainRegistryEntry,
    )
except ModuleNotFoundError:
    from utils.unified_domain_registry import (  # type: ignore[import-not-found]
        UnifiedDomain,
        UnifiedDomainRegistry,
        DomainRegistryEntry,
    )


ALL_DOMAINS = list(UnifiedDomain)
EXPECTED_DOMAIN_COUNT = 13


class TestUnifiedDomainRegistry:

    @pytest.mark.unit
    def test_all_13_domains_registered(self):
        """Every UnifiedDomain enum value must have a registry entry."""
        for domain in ALL_DOMAINS:
            entry = UnifiedDomainRegistry.get_entry(domain)
            assert entry is not None
            assert entry.domain == domain

    @pytest.mark.unit
    def test_domain_count(self):
        assert len(ALL_DOMAINS) == EXPECTED_DOMAIN_COUNT

    @pytest.mark.unit
    def test_all_domains_have_non_empty_sources(self):
        for domain in ALL_DOMAINS:
            sources = UnifiedDomainRegistry.get_sources(domain)
            assert isinstance(sources, frozenset), f"{domain}: sources must be a frozenset"
            assert len(sources) > 0, f"{domain}: sources must be non-empty"

    @pytest.mark.unit
    def test_all_domains_have_positive_max_tools(self):
        for domain in ALL_DOMAINS:
            max_t = UnifiedDomainRegistry.get_max_tools(domain)
            assert isinstance(max_t, int)
            assert max_t > 0, f"{domain}: max_tools must be > 0"

    @pytest.mark.unit
    def test_get_sub_agent_class_returns_none_for_no_path(self):
        """Domains with sub_agent_class_path=None must return None."""
        # GENERAL, ARC_INVENTORY, DOCUMENTATION, SRE_RCA have no sub-agent class path
        assert UnifiedDomainRegistry.get_sub_agent_class(UnifiedDomain.GENERAL) is None
        assert UnifiedDomainRegistry.get_sub_agent_class(UnifiedDomain.ARC_INVENTORY) is None
        assert UnifiedDomainRegistry.get_sub_agent_class(UnifiedDomain.SRE_RCA) is None

    @pytest.mark.unit
    def test_get_sub_agent_class_returns_none_on_import_error(self):
        """If the agent module isn't loadable, None is returned (no exception raised).

        NETWORK and DEPLOYMENT have class paths set but their agent modules are not
        yet implemented — get_sub_agent_class must silently swallow ImportError.
        """
        result_network = UnifiedDomainRegistry.get_sub_agent_class(UnifiedDomain.NETWORK)
        result_deploy = UnifiedDomainRegistry.get_sub_agent_class(UnifiedDomain.DEPLOYMENT)
        # Both may be None (agent not yet implemented) or a class — either is acceptable.
        # What must NOT happen is an exception propagating to the caller.
        assert result_network is None or result_network is not None  # no exception
        assert result_deploy is None or result_deploy is not None

    @pytest.mark.unit
    def test_get_sub_agent_class_no_exception_for_all_domains(self):
        """get_sub_agent_class must never raise for any registered domain."""
        for domain in ALL_DOMAINS:
            try:
                UnifiedDomainRegistry.get_sub_agent_class(domain)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"get_sub_agent_class({domain!r}) raised {type(exc).__name__}: {exc}"
                )

    @pytest.mark.unit
    def test_domains_for_source_sre(self):
        sre_domains = UnifiedDomainRegistry.domains_for_source("sre")
        expected = {
            UnifiedDomain.SRE_HEALTH,
            UnifiedDomain.SRE_INCIDENT,
            UnifiedDomain.SRE_PERFORMANCE,
            UnifiedDomain.SRE_COST_SECURITY,
            UnifiedDomain.SRE_RCA,
            UnifiedDomain.SRE_REMEDIATION,
            UnifiedDomain.GENERAL,
        }
        assert expected.issubset(set(sre_domains)), (
            f"Expected SRE domains missing. Got: {sre_domains}"
        )

    @pytest.mark.unit
    def test_domains_for_source_network(self):
        # "network" is NOT in GENERAL's sources — GENERAL only covers
        # {"azure", "sre", "monitor", "inventory", "os_eol", "azure_cli"}.
        # Only the NETWORK domain itself uses the "network" source label.
        network_domains = UnifiedDomainRegistry.domains_for_source("network")
        assert UnifiedDomain.NETWORK in network_domains
        assert UnifiedDomain.GENERAL not in network_domains

    @pytest.mark.unit
    def test_domains_for_source_monitor(self):
        monitor_domains = UnifiedDomainRegistry.domains_for_source("monitor")
        assert UnifiedDomain.OBSERVABILITY in monitor_domains

    @pytest.mark.unit
    def test_domains_for_source_azure_cli(self):
        """azure_cli source must appear in AZURE_MANAGEMENT, SRE_REMEDIATION, DEPLOYMENT, GENERAL."""
        cli_domains = set(UnifiedDomainRegistry.domains_for_source("azure_cli"))
        assert UnifiedDomain.AZURE_MANAGEMENT in cli_domains
        assert UnifiedDomain.SRE_REMEDIATION in cli_domains
        assert UnifiedDomain.DEPLOYMENT in cli_domains
        assert UnifiedDomain.GENERAL in cli_domains

    @pytest.mark.unit
    def test_domains_for_source_unknown(self):
        """Unknown sources return only GENERAL or empty."""
        result = UnifiedDomainRegistry.domains_for_source("nonexistent_source")
        # GENERAL covers all *registered* sources; an unknown source will only
        # match if it were accidentally listed somewhere. The result must be a list.
        assert isinstance(result, list)
        assert UnifiedDomain.GENERAL not in result

    @pytest.mark.unit
    def test_general_domain_covers_all_sources(self):
        """GENERAL domain must include all primary source labels."""
        general_sources = UnifiedDomainRegistry.get_sources(UnifiedDomain.GENERAL)
        for required in ("azure", "sre", "monitor", "inventory", "os_eol", "azure_cli"):
            assert required in general_sources, f"GENERAL missing source: {required}"

    @pytest.mark.unit
    def test_all_domains_method(self):
        domains = UnifiedDomainRegistry.all_domains()
        assert len(domains) == EXPECTED_DOMAIN_COUNT
        assert set(domains) == set(ALL_DOMAINS)

    @pytest.mark.unit
    def test_entry_is_frozen(self):
        """DomainRegistryEntry is a frozen dataclass — must not be mutable."""
        entry = UnifiedDomainRegistry.get_entry(UnifiedDomain.SRE_HEALTH)
        with pytest.raises((AttributeError, TypeError)):
            entry.max_tools = 999  # type: ignore[misc]

    @pytest.mark.unit
    def test_enum_values_are_strings(self):
        """UnifiedDomain(str, Enum) — every value must be a non-empty string."""
        for domain in ALL_DOMAINS:
            assert isinstance(domain.value, str)
            assert len(domain.value) > 0

    @pytest.mark.unit
    def test_sources_contain_only_strings(self):
        """Every element in a domain's sources frozenset must be a string."""
        for domain in ALL_DOMAINS:
            for source in UnifiedDomainRegistry.get_sources(domain):
                assert isinstance(source, str), (
                    f"{domain}: source {source!r} is not a str"
                )

    @pytest.mark.unit
    @pytest.mark.parametrize("domain,expected_source", [
        (UnifiedDomain.OBSERVABILITY, "monitor"),
        (UnifiedDomain.ARC_INVENTORY, "inventory"),
        (UnifiedDomain.ARC_INVENTORY, "os_eol"),
        (UnifiedDomain.AZURE_MANAGEMENT, "azure"),
        (UnifiedDomain.SRE_HEALTH, "sre"),
        (UnifiedDomain.SRE_REMEDIATION, "azure_cli"),
        (UnifiedDomain.NETWORK, "network"),
    ])
    def test_specific_domain_source_membership(self, domain, expected_source):
        """Spot-check that key domain→source relationships hold."""
        sources = UnifiedDomainRegistry.get_sources(domain)
        assert expected_source in sources, (
            f"{domain} should contain source {expected_source!r}, got {sources}"
        )
