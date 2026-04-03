"""Tests for the tiered fetch pipeline.

Validates:
1. Sequential tier execution
2. Early termination when confidence >= threshold
3. Per-adapter timeout handling (SRC-05)
4. Exception isolation within tiers
5. Best-effort return when all tiers below threshold
6. All-miss returns None
7. Tier progression logging
"""

import asyncio
import pytest
from typing import Optional
from unittest.mock import AsyncMock

import sys
import os

# Ensure app root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.source_adapter import AdapterRegistry, SourceResult
from pipeline import create_default_registry
from pipeline.tiered_fetch_pipeline import TieredFetchPipeline
from utils.normalization import NormalizedQuery


class MockAdapter:
    """Test adapter with configurable behavior."""

    def __init__(
        self,
        name: str,
        tier: int,
        timeout: int = 10,
        result: Optional[SourceResult] = None,
        delay: float = 0.0,
        raise_error: bool = False,
    ):
        self.name = name
        self.tier = tier
        self.timeout = timeout
        self._result = result
        self._delay = delay
        self._raise_error = raise_error
        self.fetch_called = False
        self.fetch_count = 0

    async def fetch(self, query: NormalizedQuery) -> Optional[SourceResult]:
        self.fetch_called = True
        self.fetch_count += 1
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._raise_error:
            raise RuntimeError(f"Mock error in {self.name}")
        return self._result


def _make_result(
    source: str = "test",
    tier: int = 1,
    eol_date: str = "2025-12-31",
    support_end_date: str = "2025-06-30",
    release_date: str = "2020-01-01",
    source_url: str = "https://example.com",
) -> SourceResult:
    """Create a SourceResult with full data for scoring."""
    return SourceResult(
        software_name="TestSoftware",
        version="1.0",
        eol_date=eol_date,
        support_end_date=support_end_date,
        release_date=release_date,
        source=source,
        source_url=source_url,
        confidence=0.0,
        tier=tier,
        raw_data={
            "success": True,
            "data": {
                "eol_date": eol_date,
                "support_end_date": support_end_date,
                "release_date": release_date,
                "source_url": source_url,
            },
        },
    )


@pytest.fixture
def query():
    return NormalizedQuery.from_software("python", "3.9")


class TestTierExecution:
    """Test sequential tier execution order."""

    @pytest.mark.asyncio
    async def test_tier_1_success_skips_later_tiers(self, query):
        """Tier 1 result with high confidence skips Tiers 2-4."""
        t1 = MockAdapter("t1", tier=1, result=_make_result(source="t1", tier=1))
        t2 = MockAdapter("t2", tier=2, result=_make_result(source="t2", tier=2))

        registry = AdapterRegistry()
        registry.register(t1)
        registry.register(t2)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t1"
        assert result.confidence >= 0.80
        assert t1.fetch_called is True
        assert t2.fetch_called is False  # Tier 2 never invoked

    @pytest.mark.asyncio
    async def test_tier_1_miss_falls_through_to_tier_2(self, query):
        """Tier 1 returns None -> pipeline tries Tier 2."""
        t1 = MockAdapter("t1", tier=1, result=None)
        t2 = MockAdapter("t2", tier=2, result=_make_result(source="t2", tier=2))

        registry = AdapterRegistry()
        registry.register(t1)
        registry.register(t2)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.50)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t2"
        assert t1.fetch_called is True
        assert t2.fetch_called is True


class TestTimeoutHandling:
    """Test per-adapter timeout (SRC-05)."""

    @pytest.mark.asyncio
    async def test_adapter_timeout_treated_as_miss(self, query):
        """Adapter exceeding timeout returns None, pipeline continues."""
        # Tier 1 adapter sleeps longer than its timeout
        t1_slow = MockAdapter(
            "t1_slow", tier=1, timeout=1, delay=5.0, result=_make_result(tier=1)
        )
        t2 = MockAdapter("t2", tier=2, result=_make_result(source="t2", tier=2))

        registry = AdapterRegistry()
        registry.register(t1_slow)
        registry.register(t2)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.50)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t2"  # Fell through to Tier 2
        assert t1_slow.fetch_called is True
        assert t2.fetch_called is True

    @pytest.mark.asyncio
    async def test_timeout_does_not_block_other_tier_adapters(self, query):
        """In the same tier, one timeout doesn't block the other adapter."""
        t1_slow = MockAdapter(
            "t1_slow", tier=1, timeout=1, delay=5.0, result=_make_result(tier=1)
        )
        t1_fast = MockAdapter(
            "t1_fast", tier=1, timeout=10, result=_make_result(source="t1_fast", tier=1)
        )

        registry = AdapterRegistry()
        registry.register(t1_slow)
        registry.register(t1_fast)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.50)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t1_fast"


class TestExceptionIsolation:
    """Test that adapter exceptions don't crash the pipeline."""

    @pytest.mark.asyncio
    async def test_adapter_exception_treated_as_miss(self, query):
        """Adapter raising exception -> pipeline treats as miss, continues."""
        t1_error = MockAdapter("t1_err", tier=1, raise_error=True)
        t2 = MockAdapter("t2", tier=2, result=_make_result(source="t2", tier=2))

        registry = AdapterRegistry()
        registry.register(t1_error)
        registry.register(t2)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.50)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t2"


class TestBestEffortReturn:
    """Test return behavior when no tier meets threshold."""

    @pytest.mark.asyncio
    async def test_below_threshold_returns_best(self, query):
        """All results below threshold -> return best confidence."""
        # Tier 4 result (0.35 base) will be below 0.80 threshold
        t4 = MockAdapter(
            "t4", tier=4, result=_make_result(source="t4", tier=4)
        )

        registry = AdapterRegistry()
        registry.register(t4)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.source == "t4"
        assert result.confidence < 0.80  # Below threshold but still returned

    @pytest.mark.asyncio
    async def test_all_miss_returns_none(self, query):
        """All adapters return None -> pipeline returns None."""
        t1 = MockAdapter("t1", tier=1, result=None)
        t2 = MockAdapter("t2", tier=2, result=None)

        registry = AdapterRegistry()
        registry.register(t1)
        registry.register(t2)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)
        result = await pipeline.fetch(query)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_registry_returns_none(self, query):
        """Empty registry -> pipeline returns None."""
        registry = AdapterRegistry()
        pipeline = TieredFetchPipeline(registry)
        result = await pipeline.fetch(query)

        assert result is None


class TestConfidenceScoring:
    """Test confidence scoring within the pipeline."""

    @pytest.mark.asyncio
    async def test_tier_1_full_data_scores_0_9(self, query):
        """Tier 1 with all fields -> confidence = 0.90 * 1.0 * 1.0 = 0.90."""
        t1 = MockAdapter("t1", tier=1, result=_make_result(tier=1))

        registry = AdapterRegistry()
        registry.register(t1)

        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.50)
        result = await pipeline.fetch(query)

        assert result is not None
        assert result.confidence == 0.9  # 0.90 * 1.0 * 1.0

    @pytest.mark.asyncio
    async def test_tier_4_scores_lower_than_tier_1(self, query):
        """Tier 4 with same data -> lower confidence than Tier 1."""
        t1 = MockAdapter("t1", tier=1, result=_make_result(tier=1))
        t4 = MockAdapter("t4", tier=4, result=_make_result(tier=4))

        registry = AdapterRegistry()
        registry.register(t1)

        pipeline1 = TieredFetchPipeline(registry, confidence_threshold=0.0)
        r1 = await pipeline1.fetch(query)

        registry2 = AdapterRegistry()
        registry2.register(t4)

        pipeline2 = TieredFetchPipeline(registry2, confidence_threshold=0.0)
        r4 = await pipeline2.fetch(query)

        assert r1 is not None and r4 is not None
        assert r1.confidence > r4.confidence


class TestDefaultRegistry:
    """Test default registry priority with real adapter wiring."""

    @pytest.mark.asyncio
    async def test_partial_tier_1_result_skips_vendor_fallback(self):
        mock_endoflife = AsyncMock()
        mock_endoflife.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "source_url": "https://endoflife.date/api/windows-server.json",
                "agent_used": "endoflife",
            },
        }

        mock_microsoft = AsyncMock()
        mock_microsoft.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "source_url": "https://example.invalid/vendor/windows-server-2019",
                "agent_used": "microsoft",
            },
        }

        registry = create_default_registry(
            {
                "endoflife": mock_endoflife,
                "microsoft": mock_microsoft,
            }
        )
        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)

        result = await pipeline.fetch(query=NormalizedQuery.from_software("Windows Server", "2019"))

        assert result is not None
        assert result.source == "endoflife"
        assert result.confidence < 0.80
        mock_endoflife.get_eol_data.assert_awaited_once()
        mock_microsoft.get_eol_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_structured_source_success_skips_vendor_fallback(self):
        mock_endoflife = AsyncMock()
        mock_endoflife.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09",
                "release_date": "2018-11-13",
                "source_url": "https://endoflife.date/api/windows-server.json",
                "agent_used": "endoflife",
            },
        }

        mock_eolstatus = AsyncMock()
        mock_eolstatus.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09",
                "release_date": "2018-11-13",
                "source_url": "https://eolstatus.com/product/windows-server-2019",
                "agent_used": "eolstatus",
            },
        }

        mock_microsoft = AsyncMock()
        mock_microsoft.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "source_url": "https://example.invalid/vendor/windows-server-2019",
                "agent_used": "microsoft",
            },
        }

        registry = create_default_registry(
            {
                "endoflife": mock_endoflife,
                "eolstatus": mock_eolstatus,
                "microsoft": mock_microsoft,
            }
        )
        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)

        result = await pipeline.fetch(query=NormalizedQuery.from_software("Windows Server", "2019"))

        assert result is not None
        assert result.source == "endoflife"
        mock_endoflife.get_eol_data.assert_awaited_once()
        mock_eolstatus.get_eol_data.assert_not_awaited()
        mock_microsoft.get_eol_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tier_2_structured_result_skips_vendor_fallback(self):
        mock_endoflife = AsyncMock()
        mock_endoflife.get_eol_data.return_value = None

        mock_eolstatus = AsyncMock()
        mock_eolstatus.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Ubuntu",
                "version": "22.04 LTS",
                "cycle": "22.04 LTS",
                "eol_date": "2032-04-21",
                "support_end_date": "2027-04-21",
                "release_date": "2022-04-21",
                "source_url": "https://eolstatus.com/product/ubuntu-22-04",
                "agent_used": "eolstatus",
            },
        }

        mock_ubuntu = AsyncMock()
        mock_ubuntu.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Ubuntu",
                "version": "22.04",
                "eol_date": "2032-04-21",
                "source_url": "https://example.invalid/vendor/ubuntu-22-04",
                "agent_used": "ubuntu",
            },
        }

        registry = create_default_registry(
            {
                "endoflife": mock_endoflife,
                "eolstatus": mock_eolstatus,
                "ubuntu": mock_ubuntu,
            }
        )
        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)

        result = await pipeline.fetch(query=NormalizedQuery.from_software("Ubuntu", "22.04"))

        assert result is not None
        assert result.source == "eolstatus"
        assert result.confidence < 0.80
        mock_endoflife.get_eol_data.assert_awaited_once()
        mock_eolstatus.get_eol_data.assert_awaited_once()
        mock_ubuntu.get_eol_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tier_2_version_mismatch_does_not_skip_vendor_fallback(self):
        mock_endoflife = AsyncMock()
        mock_endoflife.get_eol_data.return_value = None

        mock_eolstatus = AsyncMock()
        mock_eolstatus.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "RHEL",
                "version": "17",
                "cycle": "17",
                "eol_date": "2030-01-01",
                "support_end_date": "2029-01-01",
                "release_date": "2024-01-01",
                "source_url": "https://eolstatus.com/product/rhel-17",
                "agent_used": "eolstatus",
            },
        }

        mock_redhat = AsyncMock()
        mock_redhat.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "RHEL",
                "version": "7",
                "eol_date": "2024-06-30",
                "source_url": "https://example.invalid/vendor/rhel-7",
                "agent_used": "redhat",
            },
        }

        registry = create_default_registry(
            {
                "endoflife": mock_endoflife,
                "eolstatus": mock_eolstatus,
                "redhat": mock_redhat,
            }
        )
        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.80)

        result = await pipeline.fetch(query=NormalizedQuery.from_software("RHEL", "7"))

        assert result is not None
        mock_endoflife.get_eol_data.assert_awaited_once()
        mock_eolstatus.get_eol_data.assert_awaited_once()
        mock_redhat.get_eol_data.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_versionless_query_does_not_short_circuit_structured_result(self):
        mock_endoflife = AsyncMock()
        mock_endoflife.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "source_url": "https://endoflife.date/api/windows-server.json",
                "agent_used": "endoflife",
            },
        }

        mock_microsoft = AsyncMock()
        mock_microsoft.get_eol_data.return_value = {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "source_url": "https://example.invalid/vendor/windows-server-2019",
                "agent_used": "microsoft",
            },
        }

        registry = create_default_registry(
            {
                "endoflife": mock_endoflife,
                "microsoft": mock_microsoft,
            }
        )
        pipeline = TieredFetchPipeline(registry, confidence_threshold=0.95)

        result = await pipeline.fetch(query=NormalizedQuery.from_software("Windows Server"))

        assert result is not None
        mock_endoflife.get_eol_data.assert_awaited_once()
        mock_microsoft.get_eol_data.assert_awaited_once()


class TestStructuredVersionAlignment:
    """Direct tests for structured-source version alignment logic."""

    @pytest.mark.parametrize(
        ("query_version", "result_version", "expected"),
        [
            ("7", "17", False),
            ("8.5", "8", False),
            ("22.04", "22.04 LTS", True),
            ("8", "8.10", True),
            ("2012 r2", "2012", False),
            ("2012", "2012 r2", True),
        ],
    )
    def test_structured_result_version_alignment(self, query_version, result_version, expected):
        pipeline = TieredFetchPipeline(AdapterRegistry())
        query = NormalizedQuery.from_software("TestSoftware", query_version)
        result = SourceResult(
            software_name="TestSoftware",
            version=result_version,
            eol_date="2030-01-01",
            source="eolstatus",
            confidence=0.0,
            tier=2,
            raw_data={"data": {"version": result_version}},
        )

        assert pipeline._structured_result_version_aligned(query, result) is expected
