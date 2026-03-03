"""Unit tests for utils/router.py — Pipeline Router (Phase 4).

Tests:
- route() returns non-empty list always (GENERAL fallback)
- SRE queries map to SRE_HEALTH / SRE_INCIDENT domains
- Monitoring queries map to OBSERVABILITY
- EOL / inventory queries map to ARC_INVENTORY
- Entity type hints boost correct domain
- Prior tool names with source map add domain context
- Empty query returns GENERAL fallback
- explain() returns structured diagnostic dict
- DomainMatch structure: domain, confidence, matched_signals
"""
from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.router import DomainMatch, Router
    from app.agentic.eol.utils.query_patterns import QueryPatterns
    from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain
    _UTILS_PREFIX = "app.agentic.eol.utils"
except ModuleNotFoundError:
    from utils.router import DomainMatch, Router  # type: ignore[import-not-found]
    from utils.query_patterns import QueryPatterns  # type: ignore[import-not-found]
    from utils.unified_domain_registry import UnifiedDomain  # type: ignore[import-not-found]
    _UTILS_PREFIX = "utils"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_router(entity_types: List[str] | None = None) -> Router:
    """Return a Router with a mocked ResourceInventoryService."""
    from dataclasses import dataclass, field as dc_field

    # Build a minimal EntityHints mock
    try:
        from app.agentic.eol.utils.resource_inventory_service import EntityHints
    except ModuleNotFoundError:
        from utils.resource_inventory_service import EntityHints  # type: ignore[import-not-found]

    hints = EntityHints(
        names=[],
        possible_types=entity_types or [],
    )

    mock_inventory = AsyncMock()
    mock_inventory.extract_entities = AsyncMock(return_value=hints)

    return Router(inventory_service=mock_inventory)


def _domains(matches: List[DomainMatch]) -> List[str]:
    return [m.domain.value for m in matches]


def _get_match(matches: List[DomainMatch], domain: UnifiedDomain) -> DomainMatch | None:
    return next((m for m in matches if m.domain == domain), None)


# ---------------------------------------------------------------------------
# Test: empty query
# ---------------------------------------------------------------------------

class TestRouterEmptyQuery:
    @pytest.mark.asyncio
    async def test_empty_query_returns_general(self):
        router = _make_router()
        matches = await router.route("")
        assert matches, "Should never return empty list"
        assert matches[0].domain == UnifiedDomain.GENERAL

    @pytest.mark.asyncio
    async def test_empty_query_general_confidence(self):
        router = _make_router()
        matches = await router.route("")
        assert matches[0].confidence > 0


# ---------------------------------------------------------------------------
# Test: GENERAL fallback always present
# ---------------------------------------------------------------------------

class TestRouterGeneralFallback:
    @pytest.mark.asyncio
    async def test_general_always_in_results(self):
        router = _make_router()
        matches = await router.route("some completely unrecognized query xyz123")
        assert any(m.domain == UnifiedDomain.GENERAL for m in matches)

    @pytest.mark.asyncio
    async def test_general_lower_confidence_when_other_matches_exist(self):
        router = _make_router()
        matches = await router.route("check health of container app prod-api")
        general = _get_match(matches, UnifiedDomain.GENERAL)
        non_general = [m for m in matches if m.domain != UnifiedDomain.GENERAL]
        if non_general:
            assert general.confidence < max(m.confidence for m in non_general)


# ---------------------------------------------------------------------------
# Test: SRE domain routing
# ---------------------------------------------------------------------------

class TestRouterSREDomains:
    @pytest.mark.asyncio
    async def test_health_query_routes_to_sre(self):
        router = _make_router()
        matches = await router.route("check health of my container app")
        sre_domains = {UnifiedDomain.SRE_HEALTH, UnifiedDomain.SRE_INCIDENT,
                       UnifiedDomain.SRE_PERFORMANCE, UnifiedDomain.SRE_RCA}
        found = [m for m in matches if m.domain in sre_domains]
        assert found, f"Expected SRE domain; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_incident_query_routes_to_sre(self):
        router = _make_router()
        matches = await router.route("SRE incident response for application errors and 502s")
        sre_domains = {UnifiedDomain.SRE_HEALTH, UnifiedDomain.SRE_INCIDENT,
                       UnifiedDomain.SRE_PERFORMANCE, UnifiedDomain.SRE_RCA}
        found = [m for m in matches if m.domain in sre_domains]
        assert found, f"Expected SRE domain; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_cost_query_routes_to_cost_security(self):
        router = _make_router()
        matches = await router.route("show cost breakdown by resource group")
        assert any(m.domain == UnifiedDomain.SRE_COST_SECURITY for m in matches), \
            f"Expected SRE_COST_SECURITY; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_sre_query_has_high_confidence(self):
        router = _make_router()
        matches = await router.route("restart the unhealthy container app")
        sre_matches = [m for m in matches if m.domain in (
            UnifiedDomain.SRE_HEALTH, UnifiedDomain.SRE_REMEDIATION,
            UnifiedDomain.SRE_INCIDENT, UnifiedDomain.SRE_PERFORMANCE,
        )]
        if sre_matches:
            assert max(m.confidence for m in sre_matches) >= 0.7


# ---------------------------------------------------------------------------
# Test: VM health routing and scope regression
# ---------------------------------------------------------------------------

class TestRouterVmHealthRouting:
    @pytest.mark.asyncio
    async def test_vm_health_query_routes_to_sre_health(self):
        router = _make_router()
        matches = await router.route("what is the health of my VMs?")
        sre_match = _get_match(matches, UnifiedDomain.SRE_HEALTH)
        assert sre_match is not None, f"Expected SRE_HEALTH; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_vm_health_query_has_intent_boost_signal(self):
        router = _make_router()
        matches = await router.route("show vm status and health in my subscription")
        sre_match = _get_match(matches, UnifiedDomain.SRE_HEALTH)
        assert sre_match is not None, f"Expected SRE_HEALTH; got {_domains(matches)}"
        assert "intent:vm_health" in sre_match.matched_signals


class TestQueryPatternsVmHealth:
    def test_classify_domains_vm_health_sets_sre_true(self):
        result = QueryPatterns.classify_domains("what is the health of my virtual machines")
        assert result["sre"] is True


# ---------------------------------------------------------------------------
# Test: Observability domain routing
# ---------------------------------------------------------------------------

class TestRouterObservability:
    @pytest.mark.asyncio
    async def test_monitor_query_routes_to_observability(self):
        router = _make_router()
        matches = await router.route("deploy AKS workbook from Monitor Community")
        assert any(m.domain == UnifiedDomain.OBSERVABILITY for m in matches), \
            f"Expected OBSERVABILITY; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_metrics_query_routes_to_observability(self):
        router = _make_router()
        matches = await router.route("show me the Azure Monitor metrics for my AKS cluster")
        assert any(m.domain == UnifiedDomain.OBSERVABILITY for m in matches), \
            f"Expected OBSERVABILITY; got {_domains(matches)}"


# ---------------------------------------------------------------------------
# Test: ARC_INVENTORY domain routing
# ---------------------------------------------------------------------------

class TestRouterInventory:
    @pytest.mark.asyncio
    async def test_eol_query_routes_to_arc_inventory(self):
        router = _make_router()
        matches = await router.route("which Arc servers are running EOL operating systems?")
        assert any(m.domain == UnifiedDomain.ARC_INVENTORY for m in matches), \
            f"Expected ARC_INVENTORY; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_inventory_query_routes_to_arc_inventory(self):
        router = _make_router()
        matches = await router.route("get resource inventory for eol analysis")
        assert any(m.domain == UnifiedDomain.ARC_INVENTORY for m in matches), \
            f"Expected ARC_INVENTORY; got {_domains(matches)}"


# ---------------------------------------------------------------------------
# Test: entity type hints boost domain
# ---------------------------------------------------------------------------

class TestRouterEntityHints:
    @pytest.mark.asyncio
    async def test_vnet_entity_type_boosts_network(self):
        router = _make_router(entity_types=["Microsoft.Network/virtualNetworks"])
        matches = await router.route("inspect my vnet connectivity")
        network_match = _get_match(matches, UnifiedDomain.NETWORK)
        assert network_match is not None, f"NETWORK not in {_domains(matches)}"
        assert network_match.from_entity_hint is True

    @pytest.mark.asyncio
    async def test_container_app_entity_type_boosts_sre_health(self):
        router = _make_router(entity_types=["Microsoft.App/containerApps"])
        matches = await router.route("why is my app slow?")
        sre_match = _get_match(matches, UnifiedDomain.SRE_HEALTH)
        assert sre_match is not None, f"SRE_HEALTH not in {_domains(matches)}"
        assert sre_match.from_entity_hint is True

    @pytest.mark.asyncio
    async def test_nsg_entity_type_boosts_network(self):
        router = _make_router(entity_types=["Microsoft.Network/networkSecurityGroups"])
        matches = await router.route("check my NSG rules")
        network_match = _get_match(matches, UnifiedDomain.NETWORK)
        assert network_match is not None, f"NETWORK not in {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_entity_hint_raises_confidence(self):
        """An entity hint on a domain that already matched should raise confidence."""
        # SRE query + ContainerApp entity type both point to SRE_HEALTH
        router = _make_router(entity_types=["Microsoft.App/containerApps"])
        matches = await router.route("health check container app prod-api")
        sre_match = _get_match(matches, UnifiedDomain.SRE_HEALTH)
        if sre_match:
            assert sre_match.confidence >= 0.8


# ---------------------------------------------------------------------------
# Test: prior tool names add domain context
# ---------------------------------------------------------------------------

class TestRouterPriorTools:
    @pytest.mark.asyncio
    async def test_prior_sre_tools_add_context(self):
        router = _make_router()
        matches = await router.route(
            "what's wrong with it?",
            prior_tool_names=["get_container_health", "check_restart_count"],
            tool_source_map={
                "get_container_health": "sre",
                "check_restart_count": "sre",
            },
        )
        # Should have some SRE-related domain
        sre_domains = {UnifiedDomain.SRE_HEALTH, UnifiedDomain.SRE_INCIDENT,
                       UnifiedDomain.SRE_PERFORMANCE, UnifiedDomain.SRE_RCA,
                       UnifiedDomain.SRE_REMEDIATION}
        found = [m for m in matches if m.domain in sre_domains]
        assert found, f"Expected SRE context from prior tools; got {_domains(matches)}"

    @pytest.mark.asyncio
    async def test_prior_tools_without_source_map_ok(self):
        """Should not crash when tool_source_map is None."""
        router = _make_router()
        matches = await router.route(
            "what next?",
            prior_tool_names=["some_tool"],
            tool_source_map=None,
        )
        assert matches


# ---------------------------------------------------------------------------
# Test: result structure
# ---------------------------------------------------------------------------

class TestRouterResultStructure:
    @pytest.mark.asyncio
    async def test_results_sorted_by_confidence_desc(self):
        router = _make_router()
        matches = await router.route("check SRE health and cost metrics")
        confidences = [m.confidence for m in matches]
        assert confidences == sorted(confidences, reverse=True), \
            "Results should be sorted by confidence descending"

    @pytest.mark.asyncio
    async def test_confidence_range(self):
        router = _make_router()
        matches = await router.route("restart the failing container app")
        for m in matches:
            assert 0.0 <= m.confidence <= 1.0, f"Confidence out of range: {m.confidence}"

    @pytest.mark.asyncio
    async def test_matched_signals_not_empty(self):
        router = _make_router()
        matches = await router.route("check health of container app")
        for m in matches:
            assert m.matched_signals, f"matched_signals should be non-empty for {m.domain.value}"

    @pytest.mark.asyncio
    async def test_no_duplicate_domains(self):
        router = _make_router()
        matches = await router.route("check SRE health and monitor metrics")
        domains = [m.domain for m in matches]
        assert len(domains) == len(set(domains)), "Duplicate domains in result"


# ---------------------------------------------------------------------------
# Test: explain() synchronous method
# ---------------------------------------------------------------------------

class TestRouterExplain:
    def test_explain_returns_dict(self):
        router = _make_router()
        result = router.explain("check health of container app")
        assert isinstance(result, dict)
        assert "query" in result
        assert "legacy_active_domains" in result
        assert "relevant_sources" in result
        assert "unified_domains" in result

    def test_explain_health_query_has_sre_source(self):
        router = _make_router()
        result = router.explain("check health of container app")
        assert "sre" in result["relevant_sources"] or result["legacy_active_domains"]

    def test_explain_empty_query(self):
        router = _make_router()
        result = router.explain("")
        assert isinstance(result, dict)
