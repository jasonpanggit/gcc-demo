"""Tests for SREIncidentMemory — PostgreSQL-backed incident store.

Markers:
    unit: No Azure dependencies — uses in-memory fallback.
    asyncio: Async tests.
    azure: Tests that require a live database connection.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.sre_incident_memory import (
        IncidentRecord,
        SREIncidentMemory,
        get_sre_incident_memory,
    )
except ModuleNotFoundError:
    from utils.sre_incident_memory import (  # type: ignore[import-not-found]
        IncidentRecord,
        SREIncidentMemory,
        get_sre_incident_memory,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memory_with_fallback() -> SREIncidentMemory:
    """Return an initialized SREIncidentMemory that uses the in-memory fallback."""
    m = SREIncidentMemory()
    m._initialized = True          # Skip async init
    m._container = None            # Force in-memory fallback
    return m


async def _populate(memory: SREIncidentMemory, records: list[dict]) -> None:
    """Store multiple incident records into the given memory instance."""
    for r in records:
        await memory.store(**r)


# ---------------------------------------------------------------------------
# IncidentRecord unit tests
# ---------------------------------------------------------------------------

class TestIncidentRecord:

    @pytest.mark.unit
    def test_round_trip_serialization(self):
        """IncidentRecord → dict → IncidentRecord must be lossless."""
        rec = IncidentRecord(
            id="abc-123",
            workflow_id="wf-1",
            query="container app is down",
            domain="health",
            tools_used=["check_container_app_health"],
            resolution="Restarted revision",
            outcome="resolved",
            timestamp="2026-02-24T00:00:00+00:00",
        )
        restored = IncidentRecord.from_dict(rec.to_dict())
        assert restored == rec

    @pytest.mark.unit
    def test_from_dict_with_missing_fields(self):
        """from_dict must not raise when optional fields are absent."""
        rec = IncidentRecord.from_dict({"id": "x", "query": "test"})
        assert rec.id == "x"
        assert rec.domain == "general"
        assert rec.tools_used == []


# ---------------------------------------------------------------------------
# SREIncidentMemory — in-memory fallback (unit tests, no Azure)
# ---------------------------------------------------------------------------

class TestSREIncidentMemoryFallback:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_store_returns_record_id(self):
        memory = _make_memory_with_fallback()
        record_id = await memory.store(
            workflow_id="wf-1",
            query="my app is returning 503",
            domain="health",
            tools_used=["check_container_app_health"],
            resolution="Restarted revision",
        )
        assert record_id is not None
        assert isinstance(record_id, str)
        assert len(record_id) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stored_record_is_retrievable(self):
        memory = _make_memory_with_fallback()
        await memory.store(
            workflow_id="wf-1",
            query="container app health check failed",
            domain="health",
            tools_used=["check_container_app_health"],
            resolution="Scaled up replica count",
        )
        results = await memory.retrieve_similar("container app health check")
        assert len(results) == 1
        assert results[0].query == "container app health check failed"
        assert results[0].domain == "health"
        assert results[0].outcome == "resolved"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_similar_returns_most_relevant_first(self):
        memory = _make_memory_with_fallback()
        await _populate(memory, [
            {
                "workflow_id": "wf-1",
                "query": "container app returning 503 errors health check",
                "domain": "health",
                "tools_used": ["check_container_app_health"],
                "resolution": "Restarted container app revision",
                "outcome": "resolved",
            },
            {
                "workflow_id": "wf-2",
                "query": "AKS node pool out of memory error",
                "domain": "performance",
                "tools_used": ["get_performance_metrics"],
                "resolution": "Added node pool capacity",
                "outcome": "resolved",
            },
            {
                "workflow_id": "wf-3",
                "query": "App service plan CPU utilization high",
                "domain": "performance",
                "tools_used": ["get_performance_metrics", "identify_bottlenecks"],
                "resolution": "Scaled out app service plan",
                "outcome": "resolved",
            },
        ])

        results = await memory.retrieve_similar(
            "my container app health is failing with 503", top_k=3
        )
        assert len(results) >= 1
        # Most relevant (container app + 503 + health) should be first
        assert "container app" in results[0].query.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_list(self):
        memory = _make_memory_with_fallback()
        results = await memory.retrieve_similar("anything")
        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self):
        memory = _make_memory_with_fallback()
        for i in range(5):
            await memory.store(
                workflow_id=f"wf-{i}",
                query=f"health check failed on app {i}",
                domain="health",
                tools_used=["check_resource_health"],
                resolution=f"Fixed app {i}",
            )
        results = await memory.retrieve_similar("health check failed", top_k=2)
        assert len(results) <= 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fallback_store_bounded_at_100(self):
        """In-memory fallback must not grow beyond 100 entries."""
        memory = _make_memory_with_fallback()
        for i in range(105):
            await memory.store(
                workflow_id=f"wf-{i}",
                query=f"incident {i}",
                domain="health",
                tools_used=[],
                resolution="fixed",
            )
        assert len(memory._fallback_store) <= 100

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_persistence_failure_falls_back_to_memory(self):
        """When persistence raises, store() silently falls back to in-memory."""
        memory = _make_memory_with_fallback()
        broken_container = MagicMock()
        broken_container.upsert_item.side_effect = RuntimeError("Database unavailable")
        memory._container = broken_container

        record_id = await memory.store(
            workflow_id="wf-err",
            query="something went wrong",
            domain="incident",
            tools_used=[],
            resolution="none",
        )
        # Should still return an ID (stored in fallback)
        assert record_id is not None
        assert len(memory._fallback_store) == 1


# ---------------------------------------------------------------------------
# Context prefix generation
# ---------------------------------------------------------------------------

class TestSREIncidentMemoryContextPrefix:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_context_prefix_with_matching_incidents(self):
        memory = _make_memory_with_fallback()
        await memory.store(
            workflow_id="wf-1",
            query="container app health check is failing",
            domain="health",
            tools_used=["check_container_app_health"],
            resolution="Restarted the app revision",
            outcome="resolved",
        )
        prefix = await memory.get_context_prefix("container app health")
        assert prefix.startswith("Similar past incidents:")
        assert "health" in prefix.lower()
        assert "Restarted" in prefix

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_context_prefix_empty_when_no_matches(self):
        memory = _make_memory_with_fallback()
        prefix = await memory.get_context_prefix("unrelated query xyz 12345")
        assert prefix == ""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_context_prefix_within_char_limit(self):
        memory = _make_memory_with_fallback()
        # Store many long records
        for i in range(10):
            await memory.store(
                workflow_id=f"wf-{i}",
                query=f"container app health check failing incident number {i} " * 5,
                domain="health",
                tools_used=["check_container_app_health"],
                resolution="Fixed by restarting the revision " * 5,
            )
        prefix = await memory.get_context_prefix("container app health check")
        assert len(prefix) <= 1_300  # Slightly above limit to account for truncation chars


# ---------------------------------------------------------------------------
# Jaccard similarity unit tests
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:

    @pytest.mark.unit
    def test_identical_strings_score_1(self):
        score = SREIncidentMemory._jaccard_similarity("hello world", "hello world")
        assert score == 1.0

    @pytest.mark.unit
    def test_disjoint_strings_score_0(self):
        score = SREIncidentMemory._jaccard_similarity("apple banana", "xyz qrs")
        assert score == 0.0

    @pytest.mark.unit
    def test_partial_overlap(self):
        score = SREIncidentMemory._jaccard_similarity("container app health", "container app down")
        assert 0.0 < score < 1.0

    @pytest.mark.unit
    def test_empty_string_returns_0(self):
        assert SREIncidentMemory._jaccard_similarity("", "hello") == 0.0
        assert SREIncidentMemory._jaccard_similarity("hello", "") == 0.0

    @pytest.mark.unit
    def test_more_overlap_gives_higher_score(self):
        close = SREIncidentMemory._jaccard_similarity(
            "container app 503 health check", "container app 503 returning errors"
        )
        far = SREIncidentMemory._jaccard_similarity(
            "container app 503 health check", "database connection pool exhausted"
        )
        assert close > far


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

class TestGetSREIncidentMemorySingleton:

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        m1 = get_sre_incident_memory()
        m2 = get_sre_incident_memory()
        assert m1 is m2

    @pytest.mark.unit
    def test_singleton_is_sre_incident_memory(self):
        assert isinstance(get_sre_incident_memory(), SREIncidentMemory)
