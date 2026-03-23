"""Tests for TieredFetchPipeline.fetch_all()."""

import sys
import os

# Ensure app root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pipeline.source_adapter import SourceResult, AdapterRegistry
from pipeline.tiered_fetch_pipeline import TieredFetchPipeline
from utils.normalization import NormalizedQuery


def _make_adapter(name, tier, result=None, timeout=10):
    """Create a mock adapter that returns a given SourceResult or None."""
    adapter = MagicMock()
    adapter.name = name
    adapter.tier = tier
    adapter.timeout = timeout
    if result is not None:
        adapter.fetch = AsyncMock(return_value=result)
    else:
        adapter.fetch = AsyncMock(return_value=None)
    return adapter


def _make_source_result(source, tier, eol_date="2025-12-31"):
    return SourceResult(
        software_name="python",
        version="3.9",
        eol_date=eol_date,
        source=source,
        confidence=0.0,  # pipeline will score
        tier=tier,
        raw_data={"data": {"eol_date": eol_date}},
        agent_used=source,
    )


class TestFetchAll:

    @pytest.mark.asyncio
    async def test_fetch_all_returns_results_from_all_tiers(self):
        """fetch_all() returns results from every tier, not just best."""
        registry = AdapterRegistry()
        sr1 = _make_source_result("endoflife", 1)
        sr2 = _make_source_result("eolstatus", 2)
        registry.register(_make_adapter("endoflife", 1, result=sr1))
        registry.register(_make_adapter("eolstatus", 2, result=sr2))

        pipeline = TieredFetchPipeline(registry)
        query = NormalizedQuery.from_software("python", "3.9")
        results = await pipeline.fetch_all(query)

        assert len(results) == 2
        sources = {r.source for r in results}
        assert "endoflife" in sources
        assert "eolstatus" in sources

    @pytest.mark.asyncio
    async def test_fetch_all_scores_each_result(self):
        """fetch_all() assigns non-zero confidence to results with data."""
        registry = AdapterRegistry()
        sr1 = _make_source_result("endoflife", 1)
        registry.register(_make_adapter("endoflife", 1, result=sr1))

        pipeline = TieredFetchPipeline(registry)
        query = NormalizedQuery.from_software("python", "3.9")
        results = await pipeline.fetch_all(query)

        assert len(results) == 1
        assert results[0].confidence > 0.0  # scored by ConfidenceScorer

    @pytest.mark.asyncio
    async def test_fetch_all_returns_empty_when_all_miss(self):
        """fetch_all() returns empty list when all adapters return None."""
        registry = AdapterRegistry()
        registry.register(_make_adapter("endoflife", 1, result=None))
        registry.register(_make_adapter("eolstatus", 2, result=None))

        pipeline = TieredFetchPipeline(registry)
        query = NormalizedQuery.from_software("unknown_software", "99.99")
        results = await pipeline.fetch_all(query)

        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_all_does_not_early_terminate(self):
        """fetch_all() runs ALL tiers even when Tier 1 has high confidence."""
        registry = AdapterRegistry()
        sr1 = _make_source_result("endoflife", 1)
        sr2 = _make_source_result("eolstatus", 2)
        registry.register(_make_adapter("endoflife", 1, result=sr1))
        registry.register(_make_adapter("eolstatus", 2, result=sr2))

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.01)
        query = NormalizedQuery.from_software("python", "3.9")
        results = await pipeline.fetch_all(query)

        # Even with very low threshold, fetch_all returns both
        assert len(results) == 2
