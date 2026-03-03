"""Tests for SREGateway — fast keyword classification + LLM fallback.

Markers:
    unit: No external dependencies required.
    asyncio: Async tests.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.sre_gateway import SREGateway
    from app.agentic.eol.utils.sre_tool_registry import SREDomain
except ModuleNotFoundError:
    from utils.sre_gateway import SREGateway  # type: ignore[import-not-found]
    from utils.sre_tool_registry import SREDomain  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gateway() -> SREGateway:
    """Gateway with LLM fallback disabled for pure keyword tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = False
    return gw


@pytest.fixture
def gateway_with_llm() -> SREGateway:
    """Gateway with LLM fallback enabled for fallback tests."""
    gw = SREGateway()
    gw._llm_fallback_enabled = True
    return gw


# ---------------------------------------------------------------------------
# Domain fixture queries — one canonical query per domain
# ---------------------------------------------------------------------------

DOMAIN_QUERIES = [
    (SREDomain.HEALTH,         "Check health of my container apps"),
    (SREDomain.INCIDENT,       "Triage the recent alerts on my AKS cluster"),
    (SREDomain.PERFORMANCE,    "Show me CPU and memory performance metrics"),
    (SREDomain.COST_SECURITY,  "Analyze my Azure spending and security score"),
    (SREDomain.RCA,            "What is the root cause of the outage yesterday"),
    (SREDomain.REMEDIATION,    "Restart the failing container app"),
]


# ---------------------------------------------------------------------------
# Synchronous keyword classification tests
# ---------------------------------------------------------------------------

class TestSREGatewayKeywordClassification:

    @pytest.mark.unit
    @pytest.mark.parametrize("expected_domain, query", DOMAIN_QUERIES)
    def test_canonical_query_routes_to_correct_domain(self, expected_domain, query, gateway):
        """Each canonical query must classify to the expected domain."""
        domain, score = gateway.classify_sync(query)
        assert domain == expected_domain, (
            f"Query {query!r} → expected {expected_domain.value!r}, got {domain.value!r} (score={score})"
        )
        assert score >= 1, f"Expected positive score for query {query!r}"

    @pytest.mark.unit
    def test_empty_query_returns_general(self, gateway):
        domain, score = gateway.classify_sync("")
        assert domain == SREDomain.GENERAL
        assert score == 0

    @pytest.mark.unit
    def test_completely_unrelated_query_returns_general(self, gateway):
        domain, score = gateway.classify_sync("what is the capital of france")
        assert domain == SREDomain.GENERAL

    @pytest.mark.unit
    def test_health_keywords(self, gateway):
        queries = [
            "is my app service up",
            "check resource health",
            "container app is down",
            "service unavailable 503",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.HEALTH, f"Expected HEALTH for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_incident_keywords(self, gateway):
        queries = [
            "search for error logs",
            "triage the incident",
            "correlate the alerts",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.INCIDENT, f"Expected INCIDENT for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_performance_keywords(self, gateway):
        queries = [
            "show performance metrics for last hour",
            "my app is slow, check latency",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.PERFORMANCE, f"Expected PERFORMANCE for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_cost_security_keywords(self, gateway):
        queries = [
            "analyze my Azure spending this month",
            "show my security score",
            "check compliance status",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.COST_SECURITY, f"Expected COST_SECURITY for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_rca_keywords(self, gateway):
        queries = [
            "what is the root cause of this failure",
            "generate a postmortem for last week outage",
            "calculate mttr for the incident",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.RCA, f"Expected RCA for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_remediation_keywords(self, gateway):
        queries = [
            "restart the failing service",
            "scale the container app",
            "create a remediation plan",
        ]
        for q in queries:
            domain, _ = gateway.classify_sync(q)
            assert domain == SREDomain.REMEDIATION, f"Expected REMEDIATION for {q!r}, got {domain.value!r}"

    @pytest.mark.unit
    def test_score_is_higher_for_more_specific_queries(self, gateway):
        """More specific (more keyword matches) queries should have higher scores."""
        vague = "check health"
        specific = "check resource health status of container app is running"
        _, score_vague = gateway.classify_sync(vague)
        _, score_specific = gateway.classify_sync(specific)
        assert score_specific >= score_vague


# ---------------------------------------------------------------------------
# Async classify() tests — LLM fallback path
# ---------------------------------------------------------------------------

class TestSREGatewayAsync:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_high_confidence_query_skips_llm(self, gateway_with_llm):
        """A clear health query should not call the LLM at all."""
        with patch.object(gateway_with_llm, "_llm_classify", new=AsyncMock()) as mock_llm:
            # Raise threshold to ensure keyword path fires
            gateway_with_llm._AMBIGUITY_THRESHOLD = 1
            result = await gateway_with_llm.classify("check resource health of my app")
        mock_llm.assert_not_called()
        assert result == SREDomain.HEALTH

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ambiguous_query_calls_llm_fallback(self, gateway_with_llm):
        """A query with score=0 should trigger the LLM fallback."""
        gateway_with_llm._AMBIGUITY_THRESHOLD = 99  # Force always-ambiguous
        with patch.object(
            gateway_with_llm,
            "_llm_classify",
            new=AsyncMock(return_value=SREDomain.INCIDENT),
        ) as mock_llm:
            result = await gateway_with_llm.classify("something happened to the system")

        mock_llm.assert_called_once()
        assert result == SREDomain.INCIDENT

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_failure_returns_general(self, gateway_with_llm):
        """When LLM fallback fails and keyword score=0, returns GENERAL."""
        gateway_with_llm._AMBIGUITY_THRESHOLD = 99  # Force ambiguous
        with patch.object(
            gateway_with_llm,
            "_llm_classify",
            new=AsyncMock(return_value=None),  # LLM returned nothing
        ):
            result = await gateway_with_llm.classify("completely unrelated query xyz")
        assert result == SREDomain.GENERAL

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_fallback_disabled_returns_best_keyword_guess(self):
        """With LLM fallback disabled, ambiguous query returns best keyword match or GENERAL."""
        gw = SREGateway()
        gw._llm_fallback_enabled = False
        gw._AMBIGUITY_THRESHOLD = 99  # Force ambiguous
        result = await gw.classify("check resource health")
        # Best keyword match should be health even below threshold
        assert result in (SREDomain.HEALTH, SREDomain.GENERAL)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_canonical_queries_route_correctly_async(self, gateway):
        """End-to-end async classify() for all canonical domain queries."""
        for expected_domain, query in DOMAIN_QUERIES:
            result = await gateway.classify(query)
            assert result == expected_domain, (
                f"Async: query={query!r} → expected {expected_domain.value!r}, got {result.value!r}"
            )
